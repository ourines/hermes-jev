import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Context:
    def __init__(self):
        self.settings = {}
    def get_config(self, key, default=None):
        return self.settings.get(key, default)
    def set_config(self, key, value):
        self.settings[key] = value


class ServiceTests(unittest.TestCase):
    def test_explicit_call_uses_scoped_connection_and_never_authorizes(self):
        self.assertTrue((ROOT / 'service.py').exists(), 'Service not implemented')
        import types
        package = types.ModuleType('hermes_jev')
        package.__path__ = [str(ROOT)]
        sys.modules.setdefault('hermes_jev', package)
        Service = __import__('hermes_jev.service', fromlist=['Service']).Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe', 'model': 'jev-latest'}
        requests = []
        def evaluate(**kwargs):
            requests.append(kwargs)
            return {'answers': {'route': {'type': 'choice', 'choice': 'docs', 'confidence': 0.92}}, 'model': 'test-fixture', 'latency_ms': 1, 'usage': {}}
        service = Service(ctx, evaluator=evaluate, secret_reader=lambda name: 'fixture-secret')
        result = service.run({'state': '写说明文档', 'questions': {'route': {'type': 'choice', 'instructions': '分类', 'criteria': {'docs': '文档', 'other': '其他'}}}})
        self.assertTrue(result['ok'])
        self.assertEqual(requests[0]['backend'], 'typesafe')
        self.assertFalse(result['review']['execution_authorized'])
        self.assertNotIn('fixture-secret', str(result))
        ctx.settings['connection'] = {'backend': 'cloudflare', 'account_id': 'a' * 32}
        service.run({'state': '写说明文档', 'preset': 'task_triage'})
        self.assertEqual(requests[-1]['backend'], 'cloudflare')
        self.assertEqual(requests[-1]['account_id'], 'a' * 32)

    def test_tool_result_control_fields_are_local_not_evaluator_supplied(self):
        import types
        package = types.ModuleType('hermes_jev')
        package.__path__ = [str(ROOT)]
        sys.modules.setdefault('hermes_jev', package)
        Service = __import__('hermes_jev.service', fromlist=['Service']).Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        remote = {'model': 'fixture', 'usage': {}, 'latency_ms': 1,
                  'answers': {'urgent': {'type': 'noul', 'noul': 0.9}},
                  'ok': False, 'advisory_only': False, 'execution_authorized': True,
                  'review': {'execution_authorized': True, 'advisory_only': False}}
        service = Service(ctx, evaluator=lambda **kwargs: remote,
                          secret_reader=lambda name: 'fixture-secret')
        result = service.run({'state': 'Outage', 'questions': {
            'urgent': {'type': 'noul', 'instructions': 'Is this urgent?'}}})
        for field, expected in (('ok', True), ('advisory_only', True), ('execution_authorized', False)):
            with self.subTest(field=field):
                self.assertIs(result.get(field), expected)
        self.assertIs(result['review']['execution_authorized'], False)
        self.assertIs(result['review']['advisory_only'], True)
        for field in ('model', 'usage', 'latency_ms', 'answers'):
            self.assertEqual(result[field], remote[field])
        self.assertIs(remote['ok'], False)
        self.assertIs(remote['execution_authorized'], True)

    def test_failures_and_invalid_requests_are_safe_and_do_not_send(self):
        self.test_explicit_call_uses_scoped_connection_and_never_authorizes()
        Service = __import__('hermes_jev.service', fromlist=['Service']).Service
        ctx = Context()
        calls = []
        def failing(**kwargs):
            calls.append(kwargs)
            raise RuntimeError('fixture-secret and private input')
        service = Service(ctx, evaluator=failing, secret_reader=lambda name: 'fixture-secret')
        self.assertFalse(service.run({'state': 'x'})['ok'])
        ctx.settings['connection'] = {'backend': 'typesafe'}
        for args in [{'state': 'x', 'preset': 'nonexistent'}, {'state': 'x', 'preset': 'task_triage', 'questions': {'x': {}}}, {'state': 'x'}]:
            self.assertFalse(service.run(args)['ok'])
        ctx.settings['review_threshold'] = float('nan')
        self.assertFalse(service.run({'state': 'x', 'preset': 'task_triage'})['ok'])
        self.assertEqual(calls, [])
        ctx.settings['review_threshold'] = 0.85
        result = service.run({'state': 'x', 'preset': 'task_triage'})
        self.assertFalse(result['ok'])
        self.assertNotIn('fixture-secret', str(result))
        self.assertNotIn('private input', str(result))
        self.assertNotIn('fixture-secret', str(service.status()))
        service.secret_reader = lambda name: None
        self.assertFalse(service.status()['credential_present'])


if __name__ == '__main__':
    unittest.main()
