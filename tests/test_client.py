"""Offline HTTP transport fixtures; no live Jev requests or credentials."""
import importlib.util
import json
import unittest
from unittest.mock import patch

import httpx


QUESTIONS = {"urgent": {"type": "noul", "instructions": "Is this urgent?"}}
RESPONSE = {
    "model": "jev-latest",
    "answers": {"urgent": {"type": "noul", "noul": 0.92}},
    "usage": {"input_tokens": 12, "output_tokens": 3},
}
REAL_CLIENT = httpx.Client


class ClientTests(unittest.TestCase):
    def transport(self, handler):
        import client
        return patch.object(client.httpx, "Client", side_effect=lambda **kw: REAL_CLIENT(
            transport=httpx.MockTransport(handler), **kw
        ))

    def evaluate(self, **changes):
        import client
        arguments = dict(backend="typesafe", token="fixture-token", state="Help", questions=QUESTIONS)
        arguments.update(changes)
        return client.evaluate(**arguments)

    def test_cloudflare_double_result_envelope_from_live_shape(self):
        # Synthetic values; envelope shape observed in the local live probe.
        import client
        wrapped = {'success': True, 'errors': [], 'result': {
            'success': True, 'errors': [], 'result': {
                **RESPONSE, 'execution_authorized': True, 'ok': False}}}
        with self.transport(lambda request: httpx.Response(200, json=wrapped)):
            result = self.evaluate(backend='cloudflare', account_id='a' * 32)
        self.assertEqual(result['answers'], RESPONSE['answers'])
        self.assertEqual(result['usage'], RESPONSE['usage'])
        self.assertNotIn('execution_authorized', result)
        self.assertNotIn('ok', result)

    def test_cloudflare_envelopes_remain_bounded_and_fail_closed(self):
        import client
        bad = [
            {'result': {'success': False, 'errors': [{'code': 2049}], 'result': RESPONSE}},
            {'result': {'result': {**RESPONSE, 'success': False}}},
            {'result': {'result': {'result': RESPONSE}}},
            {'result': {**RESPONSE, 'result': RESPONSE}},
            {'result': None},
            {'result': {'result': []}},
            {'result': {'result': {**RESPONSE, 'answers': {}}}},
        ]
        for body in bad:
            with self.subTest(body=body), self.transport(lambda request: httpx.Response(200, json=body)):
                with self.assertRaises(client.JevError):
                    self.evaluate(backend='cloudflare', account_id='a' * 32)
        with self.transport(lambda request: httpx.Response(200, json={'result': {'result': RESPONSE}})):
            with self.assertRaises(client.JevError):
                self.evaluate(backend='typesafe')
            with self.assertRaises(client.JevError):
                self.evaluate(backend='openrouter')

    def test_openrouter_endpoint_payload_and_version_pinned_default_model(self):
        import client
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=RESPONSE)
        with self.transport(handler):
            result = self.evaluate(backend='openrouter')
        self.assertEqual(str(seen[0].url), 'https://openrouter.ai/api/alpha/decisions')
        self.assertEqual(json.loads(seen[0].content), {
            'model': 'typesafe/jev-1.13', 'state': 'Help', 'questions': QUESTIONS})
        self.assertEqual(result['answers'], RESPONSE['answers'])
        with self.transport(handler):
            self.evaluate(backend='openrouter', model='typesafe/jev-1.13-20260917')
        payload = json.loads(seen[-1].content)
        self.assertEqual(payload['model'], 'typesafe/jev-1.13-20260917')
        self.assertNotIn('input', payload)

    def test_gateway_routing_and_privacy_headers_are_cloudflare_only(self):
        import client
        for backend, gateway in (("cloudflare", "hermes-jev"), ("cloudflare", "_"), ("cloudflare", None),
                                 ("cloudflare", "a_0-" + "b" * 60), ("typesafe", None), ("openrouter", None)):
            seen = []
            def handler(request):
                seen.append(request)
                return httpx.Response(200, json=RESPONSE)
            with self.subTest(backend=backend, gateway=gateway), self.transport(handler):
                self.evaluate(backend=backend, account_id="a" * 32, gateway_id=gateway)
            headers = seen[0].headers
            self.assertEqual(headers["Authorization"], "Bearer fixture-token")
            self.assertNotIn("cf-aig-authorization", headers)
            self.assertEqual(headers.get("cf-aig-gateway-id"), gateway)
            controls = {"cf-aig-collect-log": "false", "cf-aig-skip-cache": "true",
                        "cf-aig-max-attempts": "1"}
            for key, value in controls.items():
                self.assertEqual(headers.get(key), value if backend == "cloudflare" else None)
            if backend == "cloudflare":
                self.assertEqual(str(seen[0].url), "https://api.cloudflare.com/client/v4/accounts/" + "a" * 32 + "/ai/run")

    def test_gateway_validation_rejects_invalid_or_non_cloudflare_before_post(self):
        import client
        invalid = ["", " ", "Upper", "a--b", "-a", "a-", "a/b", "a.b", "a\nb", "a\n", "a\r\nb",
                   "a" * 65, "中文", True, 1, [], {}]
        cases = [("cloudflare", value) for value in invalid] + [("typesafe", "hermes-jev"), ("typesafe", ""),
                                                                ("openrouter", "hermes-jev")]
        for backend, value in cases:
            with self.subTest(backend=backend, value=value), patch.object(client, "_post") as post:
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(backend=backend, account_id="a" * 32, gateway_id=value)
                self.assertEqual(raised.exception.category, "invalid_gateway_id")
                post.assert_not_called()

    def test_cloudflare_2049_has_safe_numeric_diagnostics_without_raw_body(self):
        import client
        import traceback
        body = {'success': False, 'errors': [{'code': 2049, 'message': 'fixture-token private-input'}],
                'hint': 'private-input', 'execution_authorized': True}
        for status in (403, 200):
            seen = []
            def handler(request):
                seen.append(request)
                return httpx.Response(status, json=body, headers={'X-Secret': 'fixture-token'})
            with self.subTest(status=status), self.transport(handler):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(backend='cloudflare', account_id='a' * 32)
            error = raised.exception
            self.assertEqual(str(error), 'Jev HTTP error (403)' if status == 403 else 'Jev provider error')
            self.assertEqual(getattr(error, 'provider_code', None), 2049)
            self.assertIn('Unified Billing', error.hint)
            self.assertIn('authentication', error.hint)
            self.assertNotIn('fixture-token', str(vars(error)))
            self.assertNotIn('private-input', ''.join(traceback.format_exception(error)))
            self.assertEqual(len(seen), 1)

    def test_error_diagnostics_are_bounded_and_malformed_bodies_stay_generic(self):
        import client
        import traceback
        malformed = [b'private-input', b'\xff', b'[' * 1100 + b']' * 1100,
                     b'{"errors":[{"code":2049,"code":1000}]}',
                     b'{"errors":[{"code":NaN}]}']
        malformed += [json.dumps({'errors': [{'code': code, 'message': 'private-input'}]}).encode()
                      for code in (True, '2049', 2049.0, -1, 1_000_000_000, None, {}, [])]
        for raw in malformed:
            with self.subTest(raw=raw[:80]), self.transport(lambda request: httpx.Response(403, content=raw)):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(backend='cloudflare', account_id='a' * 32)
            self.assertEqual(str(raised.exception), 'Jev HTTP error (403)')
            self.assertIsNone(raised.exception.provider_code)
            self.assertIsNone(raised.exception.hint)
            self.assertNotIn('private-input', ''.join(traceback.format_exception(raised.exception)))
        class ErrorStream(httpx.SyncByteStream):
            reads = 0
            closed = False
            def __iter__(self):
                for _ in range(100):
                    self.reads += 1
                    yield b' ' * 4096
            def close(self):
                self.closed = True
        stream = ErrorStream()
        with self.transport(lambda request: httpx.Response(403, stream=stream)):
            with self.assertRaises(client.JevError) as raised:
                self.evaluate(backend='cloudflare', account_id='a' * 32)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIsNone(raised.exception.provider_code)
        self.assertLessEqual(stream.reads, 17)
        self.assertTrue(stream.closed)

    def test_provider_codes_are_cloudflare_only_and_unknown_codes_have_no_hint(self):
        import client
        for backend, code, expected in (('typesafe', 2049, None), ('cloudflare', 1000, 1000),
                                        ('openrouter', 2049, None)):
            with self.transport(lambda request: httpx.Response(403, json={'errors': [{'code': code}]})):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(backend=backend, account_id='a' * 32)
            self.assertEqual(raised.exception.provider_code, expected)
            self.assertIsNone(raised.exception.hint)
        for code in (True, 'private-input', -1, 1_000_000_000):
            error = client.JevError('HTTP', status_code=403, provider_code=code)
            self.assertIsNone(error.provider_code)
            self.assertNotIn('private-input', str(client.safe_error_details(error)))

    def test_http_errors_are_safe_and_never_retry_or_follow_redirects(self):
        import client
        self.assertTrue(hasattr(client, "JevError"), "safe public error is required")
        for status in (301, 302, 307, 308, 400, 401, 403, 422, 429, 500, 529):
            with self.subTest(status=status):
                seen = []
                def handler(request):
                    seen.append(request)
                    return httpx.Response(status, text="fixture-token secret-input server-secret", headers={"Location": "https://evil.invalid/leak"})
                with self.transport(handler), self.assertRaises(client.JevError) as raised:
                    self.evaluate()
                error = raised.exception
                self.assertEqual(str(error), f"Jev HTTP error ({status})")
                self.assertEqual(error.status_code, status)
                self.assertEqual(error.retryable, status == 429 or status >= 500)
                self.assertEqual(len(seen), 1)
                self.assertIsNone(error.__cause__)

    def test_configuration_validation_before_network(self):
        import client
        cases = [
            ({"backend": "https://evil.invalid"}, "backend"),
            ({"backend": []}, "backend"),
            ({"token": ""}, "token"), ({"token": "secret\r\nheader"}, "token"),
            ({"token": "two tokens"}, "token"), ({"token": "中文"}, "token"),
            ({"token": 123}, "token"), ({"token": "x" * 8193}, "token"),
            ({"backend": "cloudflare", "account_id": "../evil"}, "account_id"),
            ({"backend": "cloudflare", "account_id": "a" * 31}, "account_id"),
            ({"backend": "cloudflare", "account_id": "g" * 32}, "account_id"),
            ({"backend": "cloudflare", "account_id": None}, "account_id"),
            ({"model": ""}, "model"), ({"model": "https://evil.invalid"}, "model"),
            ({"model": 42}, "model"),
        ] + [({"timeout": v}, "timeout") for v in (None, True, "30", 0, -1, 0.5, 121, float("nan"), float("inf"))]
        for changes, category in cases:
            with self.subTest(changes=changes), patch.object(client, "_post", return_value=RESPONSE) as post:
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(**changes)
                self.assertEqual(str(raised.exception), f"Jev invalid_{category} error")
                post.assert_not_called()

    def test_state_must_be_text_or_strict_bounded_json(self):
        import client
        cycle = []
        cycle.append(cycle)
        nested = []
        for _ in range(70):
            nested = [nested]
        invalid = [None, "", "  ", 7, True, b"text", (1, 2), {1: "secret"},
                   {"x": float("nan")}, {"x": float("inf")}, {"x": object()},
                   {"x": (1, 2)}, "\ud800", cycle, nested]
        for index, state in enumerate(invalid):
            with self.subTest(index=index), patch.object(client, "_post", return_value=RESPONSE) as post:
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(state=state)
                self.assertEqual(str(raised.exception), "Jev invalid_state error")
                post.assert_not_called()
        for state in ({}, [], {"nested": [True, None, 1, 0.5, "文本"]}, ["message"]):
            with self.subTest(valid=state), self.transport(lambda request: httpx.Response(200, json=RESPONSE)):
                self.assertEqual(self.evaluate(state=state)["answers"], RESPONSE["answers"])

    def test_question_subset_validation_before_network(self):
        import client
        invalid = [None, [], {}, {str(i): QUESTIONS["urgent"] for i in range(129)},
                   {"": QUESTIONS["urgent"]}, {7: QUESTIONS["urgent"]},
                   {"x": None}, {"x": {"type": "other", "instructions": "Do it"}},
                   {"x": {"type": [], "instructions": "Do it"}}]
        invalid += [{"x": {"type": "noul", "instructions": value}}
                    for value in (None, "", " ", {}, [], "\ud800")]
        criteria_cases = {
            "noul": [None, [], {}, {"yes": "yes"}, {"true": None}, {"false": 1}],
            "choice": [None, [], {}, {"only": "one"}, {"a": 1, "b": None},
                       {"a": "one", "": "two"}, {str(i): None for i in range(256)}],
            "score": [None, {}, [], ["one"], ["one", None], ["one", {}]],
        }
        invalid += [{"x": {"type": kind, "instructions": "Choose", "criteria": criteria}}
                    for kind, values in criteria_cases.items() for criteria in values]
        for index, questions in enumerate(invalid):
            with self.subTest(index=index), patch.object(client, "_post", return_value=RESPONSE) as post:
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(questions=questions)
                self.assertEqual(str(raised.exception), "Jev invalid_questions error")
                post.assert_not_called()

    def test_payload_limit_applies_to_utf8_encoded_whole_request(self):
        import client
        for state in ("x" * (1024 * 1024), "中" * (400 * 1024)):
            with self.subTest(length=len(state)), patch.object(client, "_post", return_value=RESPONSE) as post:
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(state=state)
                self.assertEqual(str(raised.exception), "Jev payload_too_large error")
                post.assert_not_called()
        with patch.object(client, "_post", return_value=RESPONSE) as post:
            with self.assertRaises(client.JevError):
                self.evaluate(state={"huge_integer": 10 ** 10000})
            post.assert_not_called()

    def test_transport_and_json_failures_have_static_messages(self):
        import client
        import traceback
        cases = [(httpx.ReadTimeout("fixture-token private-input"), "timeout", True),
                 (httpx.ConnectError("fixture-token private-input"), "network", True),
                 (httpx.RemoteProtocolError("fixture-token private-input"), "network", True),
                 (OSError("fixture-token private-input"), "network", True),
                 (b"private-input is not JSON", "invalid_json", False),
                 (b'\xff', "invalid_json", False),
                 (b'{"answers":NaN}', "invalid_json", False)]
        for index, (failure, category, retryable) in enumerate(cases):
            seen = []
            def handler(request):
                seen.append(request)
                if isinstance(failure, Exception):
                    raise failure
                return httpx.Response(200, content=failure)
            with self.subTest(index=index), self.transport(handler):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate()
                error = raised.exception
                self.assertEqual(str(error), f"Jev {category} error")
                self.assertEqual(error.retryable, retryable)
                self.assertEqual(len(seen), 1)
                self.assertNotIn("private-input", "".join(traceback.format_exception(error)))

    def test_response_size_is_bounded_while_streaming(self):
        import client
        class LargeStream(httpx.SyncByteStream):
            def __init__(self):
                self.reads = 0
                self.closed = False
            def __iter__(self):
                for _ in range(100):
                    self.reads += 1
                    yield b" " * 65536
            def close(self):
                self.closed = True
        for headers in ({}, {"Content-Length": str(3 * 1024 * 1024)}):
            stream = LargeStream()
            with self.subTest(headers=headers), self.transport(
                lambda request: httpx.Response(200, headers=headers, stream=stream)
            ):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate()
                self.assertEqual(str(raised.exception), "Jev response_too_large error")
            self.assertLessEqual(stream.reads, 33)
            self.assertTrue(stream.closed)

    def test_cloudflare_failure_flag_is_not_a_successful_result(self):
        import client
        for body in ({"success": False, "result": RESPONSE, "errors": [{"message": "secret-input"}]},
                     {"success": False, **RESPONSE}):
            with self.subTest(body=body), self.transport(lambda request: httpx.Response(200, json=body)):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(backend="cloudflare", account_id="a" * 32)
                self.assertEqual(str(raised.exception), "Jev provider error")

    def test_response_shape_and_question_coverage_are_validated(self):
        import client
        invalid = [None, [], "secret-body", {}, {**RESPONSE, "model": ""},
                   {**RESPONSE, "usage": []}, {**RESPONSE, "answers": {}},
                   {**RESPONSE, "answers": {"urgent": []}},
                   {"success": True, "result": None}]
        for index, body in enumerate(invalid):
            with self.subTest(index=index), self.transport(lambda request: httpx.Response(200, content=json.dumps(body))):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(backend="cloudflare", account_id="a" * 32)
                self.assertEqual(str(raised.exception), "Jev invalid_response error")

    def test_noul_answer_requires_matching_type_and_probability_without_confidence(self):
        import client
        invalid = [{}, {"type": "choice", "noul": 0.5},
                   {"type": "noul", "noul": 0.5, "confidence": 0.8}]
        invalid += [{"type": "noul", "noul": v} for v in (None, True, "0.5", -0.1, 1.1, float("nan"), float("inf"))]
        for index, answer in enumerate(invalid):
            body = {**RESPONSE, "answers": {"urgent": answer}}
            with self.subTest(index=index), patch.object(client, "_post", return_value=body):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate()
                self.assertEqual(str(raised.exception), "Jev invalid_response error")

    def test_choice_and_score_values_match_the_rubric(self):
        import client
        cases = [("choice", {"a": None, "b": "Second"}, value)
                 for value in ("unknown", None, ["a"], 0)]
        cases += [("score", ["Low", "High", "Maximum"], value)
                  for value in (-0.01, 2.01, None, True, "1.2", float("nan"))]
        for index, (kind, criteria, value) in enumerate(cases):
            question = {"q": {"type": kind, "instructions": "Evaluate", "criteria": criteria}}
            body = {**RESPONSE, "answers": {"q": {"type": kind, kind: value}}}
            with self.subTest(index=index), patch.object(client, "_post", return_value=body):
                with self.assertRaises(client.JevError) as raised:
                    self.evaluate(questions=question)
                self.assertEqual(str(raised.exception), "Jev invalid_response error")

    def test_optional_confidence_and_probabilities_are_validated(self):
        import client
        for kind, criteria, value in (("choice", {"0": None, "1": "High"}, "1"),
                                      ("score", ["Low", "High"], 0.8)):
            question = {"q": {"type": kind, "instructions": "Evaluate", "criteria": criteria}}
            base = {"type": kind, kind: value}
            invalid = [{"confidence": v} for v in (None, True, -0.1, 1.1, "0.9", float("inf"))]
            invalid += [{"probabilities": p} for p in (None, [], {}, {"0": 1},
                        {"0": 0.2, "1": 0.2}, {"0": -0.1, "1": 1.1},
                        {"0": True, "1": 0}, {"0": "0.2", "1": 0.8},
                        {"0": float("nan"), "1": 0.8}, {"0": 0.2, "2": 0.8})]
            for index, fields in enumerate(invalid):
                body = {**RESPONSE, "answers": {"q": {**base, **fields}}}
                with self.subTest(kind=kind, index=index), patch.object(client, "_post", return_value=body):
                    with self.assertRaises(client.JevError):
                        self.evaluate(questions=question)
            for fields in ({}, {"confidence": 0.8}, {"confidence": 0, "probabilities": {"0": 0.2, "1": 0.8}}):
                body = {**RESPONSE, "answers": {"q": {**base, **fields}}}
                with self.subTest(kind=kind, valid=fields), self.transport(lambda request: httpx.Response(200, json=body)):
                    result = self.evaluate(questions=question)
                    self.assertEqual(result["answers"], body["answers"])
                    if not fields:
                        self.assertNotIn("confidence", result["answers"]["q"])

    def test_score_legend_and_usage_metadata_are_validated(self):
        import client
        question = {"q": {"type": "score", "instructions": "Rate", "criteria": ["Low", "High"]}}
        answer = {"type": "score", "score": 0.8, "confidence": 0.7}
        invalid = [{**RESPONSE, "answers": {"q": {**answer, "legend": legend}}}
                   for legend in (None, [], {"0": "Low"}, {"0": "Low", "1": 1})]
        invalid += [{**RESPONSE, "answers": {"q": answer}, "usage": {"input_tokens": value}}
                    for value in (-1, True, "12", 1.5)]
        for index, body in enumerate(invalid):
            with self.subTest(index=index), self.transport(lambda request: httpx.Response(200, json=body)):
                with self.assertRaises(client.JevError):
                    self.evaluate(questions=question)
        body = {**RESPONSE, "answers": {"q": {**answer, "legend": {"0": "Low", "1": "High"}}}}
        with self.transport(lambda request: httpx.Response(200, json=body)):
            self.assertEqual(self.evaluate(questions=question)["answers"], body["answers"])

    def test_ambiguous_or_nonfinite_json_response_is_rejected(self):
        import client
        bodies = [b'{"success":false,"success":true,"result":' + json.dumps(RESPONSE).encode() + b'}',
                  json.dumps(RESPONSE).replace('"input_tokens": 12', '"input_tokens": 1e999').encode(),
                  b'[' * 1100 + b']' * 1100]
        for index, body in enumerate(bodies):
            with self.subTest(index=index), self.transport(lambda request: httpx.Response(200, content=body)):
                with self.assertRaises(client.JevError):
                    self.evaluate(backend="cloudflare", account_id="a" * 32)

    def test_official_style_mixed_fixture_preserves_score_without_probabilities(self):
        questions = {
            "urgent": {"type": "noul", "instructions": "Is it urgent?", "criteria": {"true": "Urgent", "false": "Calm"}},
            "department": {"type": "choice", "instructions": "Which team?", "criteria": {"billing": None, "technical": "Bugs", "sales": "Sales"}},
            "frustration": {"type": "score", "instructions": "Rate frustration", "criteria": ["Calm", "Frustrated", "Angry"]},
        }
        body = {"model": "jev-1.13.0", "usage": {"input_tokens": 312, "output_tokens": 48}, "answers": {
            "urgent": {"type": "noul", "noul": 0.999},
            "department": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.84, "technical": 0.159, "sales": 0.001}, "confidence": 0.596},
            "frustration": {"type": "score", "score": 1.035, "legend": {"0": "Calm", "1": "Frustrated", "2": "Angry"}, "confidence": 0.842},
        }}
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=body)
        for backend, model in (("typesafe", "jev-1.13.0"), ("cloudflare", "typesafe/jev")):
            with self.subTest(backend=backend), self.transport(handler):
                result = self.evaluate(backend=backend, account_id="a" * 32, model=model, timeout=12.5, questions=questions)
            self.assertEqual(json.loads(seen[-1].content)["model"], model)
            self.assertEqual(seen[-1].extensions["timeout"]["read"], 12.5)
            self.assertEqual({k: result[k] for k in body}, body)
            self.assertNotIn("probabilities", result["answers"]["frustration"])
            self.assertNotIn("confidence", result["answers"]["urgent"])

    def test_supported_boundary_values(self):
        import client
        cases = []
        for count in (1, 128):
            questions = {str(i): QUESTIONS["urgent"] for i in range(count)}
            answers = {str(i): {"type": "noul", "noul": i % 2} for i in range(count)}
            cases.append((questions, answers))
        for count in (2, 255):
            criteria = {str(i): None for i in range(count)}
            cases.append(({"q": {"type": "choice", "instructions": "Choose", "criteria": criteria}},
                          {"q": {"type": "choice", "choice": "0", "confidence": 1}}))
        for score in (0, 2):
            cases.append(({"q": {"type": "score", "instructions": "Rate", "criteria": ["a", "b", "c"]}},
                          {"q": {"type": "score", "score": score}}))
        for index, (questions, answers) in enumerate(cases):
            body = {**RESPONSE, "answers": answers}
            with self.subTest(index=index), self.transport(lambda request: httpx.Response(200, json=body)):
                self.assertEqual(self.evaluate(questions=questions, timeout=1 if index % 2 else 120)["answers"], answers)
        with patch.object(client, "_post", return_value=RESPONSE) as post:
            result = self.evaluate()
            self.assertEqual(post.call_count, 1)
            self.assertEqual(result["model"], RESPONSE["model"])

    def test_error_object_never_formats_arbitrary_constructor_input(self):
        import client
        error = client.JevError("fixture-token private-input", status_code="secret-body")
        self.assertEqual(str(error), "Jev request error")
        self.assertEqual(error.category, "request")
        self.assertIsNone(error.status_code)
        self.assertNotIn("private-input", repr(error))

    def test_provider_top_level_fields_are_filtered_without_changing_answers(self):
        questions = {
            **QUESTIONS,
            "route": {"type": "choice", "instructions": "Choose", "criteria": {"a": None, "b": "Other"}},
            "impact": {"type": "score", "instructions": "Rate", "criteria": ["Low", "High"]},
        }
        documented = {
            "model": "jev-1.13.0",
            "usage": {"input_tokens": 12, "output_tokens": 3},
            "answers": {
                **RESPONSE["answers"],
                "route": {"type": "choice", "choice": "a", "confidence": 0.7,
                          "probabilities": {"a": 0.8, "b": 0.2}},
                "impact": {"type": "score", "score": 0.8, "confidence": 0.7,
                           "probabilities": {"0": 0.2, "1": 0.8},
                           "legend": {"0": "Low", "1": "High"}},
            },
        }
        remote = {**documented, "ok": False, "execution_authorized": True,
                  "advisory_only": False, "online_verified": False,
                  "synthetic_smoke_only": False, "semantic_checks": {"urgent": True},
                  "review": {"execution_authorized": True}, "unknown_field": "untrusted",
                  "backend": "forged", "latency_ms": -1}
        cases = (("typesafe", remote), ("cloudflare", remote),
                 ("cloudflare", {"success": True, "result": remote}))
        for backend, body in cases:
            with self.subTest(backend=backend, wrapped="result" in body), self.transport(
                lambda request: httpx.Response(200, json=body)
            ):
                result = self.evaluate(backend=backend, account_id="a" * 32, questions=questions)
            self.assertEqual(set(result), {"model", "answers", "usage", "backend", "latency_ms"})
            self.assertEqual({key: result[key] for key in documented}, documented)
            self.assertEqual(result["backend"], backend)
            self.assertGreaterEqual(result["latency_ms"], 0)

    def test_cloudflare_direct_and_wrapped_responses(self):
        for body in (RESPONSE, {"success": True, "result": RESPONSE}):
            with self.subTest(body=body):
                seen = []
                def handler(request):
                    seen.append(request)
                    return httpx.Response(200, json=body)
                with self.transport(handler):
                    result = self.evaluate(backend="cloudflare", account_id="a" * 32)
                self.assertEqual(str(seen[0].url), "https://api.cloudflare.com/client/v4/accounts/" + "a" * 32 + "/ai/run")
                self.assertEqual(json.loads(seen[0].content), {"model": "typesafe/jev", "input": {"state": "Help", "questions": QUESTIONS}})
                self.assertEqual(result["backend"], "cloudflare")
                self.assertEqual(result["answers"], RESPONSE["answers"])

    def test_typesafe_noul_tracer_over_http_transport(self):
        self.assertIsNotNone(importlib.util.find_spec("client"), "client module must exist")
        import client
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=RESPONSE)

        with patch.object(client.httpx, "Client", side_effect=lambda **kw: REAL_CLIENT(
            transport=httpx.MockTransport(handler), **kw
        )):
            result = client.evaluate(backend="typesafe", token="fixture-token", state="Help", questions=QUESTIONS)
        self.assertEqual(len(seen), 1)
        self.assertEqual(str(seen[0].url), "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(seen[0].method, "POST")
        self.assertEqual(seen[0].headers["Authorization"], "Bearer fixture-token")
        self.assertEqual(json.loads(seen[0].content), {"model": "jev-latest", "state": "Help", "questions": QUESTIONS})
        self.assertEqual({k: result[k] for k in RESPONSE}, RESPONSE)
        self.assertEqual(result["backend"], "typesafe")
        self.assertGreaterEqual(result["latency_ms"], 0)
        self.assertNotIn("confidence", result["answers"]["urgent"])


if __name__ == "__main__":
    unittest.main()
