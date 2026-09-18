import argparse
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('hermes_jev')
package.__path__ = [str(ROOT)]
sys.modules.setdefault('hermes_jev', package)


class CLITests(unittest.TestCase):
    def test_gateway_setup_persists_routes_and_reports_nonsecret_id(self):
        cli = importlib.import_module('hermes_jev.cli')
        from test_service import Context
        from hermes_jev.service import Service
        parser = argparse.ArgumentParser()
        cli.build_parser(parser)
        args = parser.parse_args(['setup', '--backend', 'cloudflare', '--account-id', 'a' * 32,
                                  '--gateway-id', 'hermes-jev'])
        ctx, secrets, requests = Context(), {}, []
        def evaluate(**kwargs):
            requests.append(kwargs)
            return {'model': 'fixture', 'answers': {}, 'usage': {}}
        service = Service(ctx, evaluator=evaluate, secret_reader=secrets.get)
        with patch.object(sys.stdin, 'isatty', return_value=True), patch.object(cli.getpass, 'getpass', return_value='fixture-secret'):
            cli.setup(ctx, args, service=service, save_secret=secrets.__setitem__)
        self.assertEqual(ctx.settings['connection']['gateway_id'], 'hermes-jev')
        self.assertEqual(requests[0]['gateway_id'], 'hermes-jev')
        self.assertEqual(service.status()['gateway_id'], 'hermes-jev')
        service.run({'state': 'Outage', 'preset': 'task_triage'})
        self.assertEqual(requests[-1]['gateway_id'], 'hermes-jev')

    def test_invalid_gateway_is_rejected_before_any_secret_or_request(self):
        cli = importlib.import_module('hermes_jev.cli')
        from test_service import Context
        from hermes_jev.service import Service
        from hermes_jev.client import JevError
        from unittest.mock import Mock
        for backend, gateway in (('cloudflare', ''), ('cloudflare', 'bad/id'), ('typesafe', 'hermes-jev')):
            with self.subTest(backend=backend, gateway=gateway):
                ctx = Context()
                ctx.settings['connection'] = {'backend': backend, 'gateway_id': gateway, 'account_id': 'a' * 32}
                reader, evaluator, saver = Mock(), Mock(), Mock()
                service = Service(ctx, evaluator=evaluator, secret_reader=reader)
                args = argparse.Namespace(backend=backend, gateway_id=gateway, account_id='a' * 32, model=None)
                with patch.object(sys.stdin, 'isatty', return_value=True), patch.object(cli.getpass, 'getpass') as hidden:
                    with self.assertRaises(JevError):
                        cli.setup(ctx, args, service=service, save_secret=saver)
                    hidden.assert_not_called()
                self.assertFalse(service.run({'state': 'Outage', 'preset': 'task_triage'})['ok'])
                with self.assertRaises(JevError):
                    cli.smoke_test(service)
                with self.assertRaises(JevError):
                    service.status()
                reader.assert_not_called()
                evaluator.assert_not_called()
                saver.assert_not_called()

    def test_cli_and_tool_errors_expose_only_controlled_diagnostics(self):
        import contextlib
        import io
        import json
        from hermes_jev.client import JevError
        from hermes_jev.service import Service
        from test_service import Context
        cli = importlib.import_module('hermes_jev.cli')
        class UnsafeError(JevError):
            def __str__(self):
                return 'fixture-secret private-input'
        for error in (JevError('HTTP', status_code=403, provider_code=2049),
                      UnsafeError('HTTP', status_code=403, provider_code=2049),
                      RuntimeError('fixture-secret private-input')):
            error.hint = 'fixture-secret private-input'
            ctx = Context()
            ctx.settings['connection'] = {'backend': 'cloudflare', 'gateway_id': 'hermes-jev'}
            def failing(**kwargs):
                raise error
            service = Service(ctx, evaluator=failing, secret_reader=lambda name: 'fixture-secret')
            tool = service.run({'state': 'Outage', 'preset': 'task_triage'})
            output = io.StringIO()
            with patch.object(cli, 'Service', return_value=service), contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as raised:
                    cli.dispatch(ctx, argparse.Namespace(jev_command='test'))
            self.assertEqual(raised.exception.code, 1)
            for result in (tool, json.loads(output.getvalue())):
                with self.subTest(error=type(error).__name__, result=result):
                    self.assertFalse(result['ok'])
                    self.assertIs(result['execution_authorized'], False)
                    self.assertNotIn('fixture-secret', str(result))
                    self.assertNotIn('private-input', str(result))
                    if isinstance(error, JevError):
                        self.assertEqual(result.get('provider_code'), 2049)
                        self.assertEqual(result.get('status_code'), 403)
                        self.assertIn('Unified Billing', result.get('hint', ''))
                    else:
                        self.assertNotIn('provider_code', result)

    def test_smoke_status_and_controls_cannot_be_overridden_by_provider(self):
        cli = importlib.import_module('hermes_jev.cli')
        from test_service import Context
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        for urgent, department, severity in ((0.9, 'technical', 1.9), (0.1, 'technical', 1.9),
                                              (0.9, 'billing', 1.9), (0.9, 'technical', 0.2)):
            checks = {'urgent': urgent > 0.5, 'department': department == 'technical',
                      'severity': severity > 1}
            expected = {'ok': all(checks.values()), 'online_verified': True,
                        'synthetic_smoke_only': True, 'semantic_checks': checks,
                        'advisory_only': True, 'execution_authorized': False}
            remote = {'model': 'fixture', 'usage': {}, 'latency_ms': 1,
                      'answers': {'is_urgent': {'type': 'noul', 'noul': urgent},
                                  'department': {'type': 'choice', 'choice': department},
                                  'severity': {'type': 'score', 'score': severity}},
                      'ok': not expected['ok'], 'online_verified': False,
                      'synthetic_smoke_only': False,
                      'semantic_checks': {key: not value for key, value in checks.items()},
                      'advisory_only': False, 'execution_authorized': True}
            service = Service(ctx, evaluator=lambda **kwargs: remote,
                              secret_reader=lambda name: 'fixture-secret')
            result = cli.smoke_test(service)
            with self.subTest(checks=checks):
                self.assertEqual({field: result.get(field) for field in expected}, expected)
                for field in ('model', 'usage', 'latency_ms', 'answers'):
                    self.assertEqual(result[field], remote[field])
                self.assertIs(remote['ok'], not expected['ok'])

    def test_smoke_semantic_failure_exits_nonzero_despite_provider_ok(self):
        import contextlib
        import io
        import json
        cli = importlib.import_module('hermes_jev.cli')
        from test_service import Context
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        remote = {'model': 'fixture', 'usage': {}, 'ok': True,
                  'execution_authorized': True, 'advisory_only': False,
                  'answers': {'is_urgent': {'type': 'noul', 'noul': 0.1},
                              'department': {'type': 'choice', 'choice': 'technical'},
                              'severity': {'type': 'score', 'score': 1.9}}}
        service = Service(ctx, evaluator=lambda **kwargs: remote,
                          secret_reader=lambda name: 'fixture-secret')
        output = io.StringIO()
        with patch.object(cli, 'Service', return_value=service), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                cli.dispatch(ctx, argparse.Namespace(jev_command='test'))
        self.assertEqual(raised.exception.code, 1)
        result = json.loads(output.getvalue())
        self.assertIs(result['ok'], False)
        self.assertIs(result['semantic_checks']['urgent'], False)
        self.assertIs(result['advisory_only'], True)
        self.assertIs(result['execution_authorized'], False)

    def test_setup_is_masked_validated_then_persisted(self):
        self.assertTrue((ROOT / 'cli.py').exists(), 'Interactive CLI not implemented')
        cli = importlib.import_module('hermes_jev.cli')
        from test_service import Context
        from hermes_jev.service import Service
        ctx, secrets, events = Context(), {}, []
        def evaluate(**kwargs):
            events.append('request')
            return {'model': 'fixture', 'answers': {'is_urgent': {'type': 'noul', 'noul': 0.99}}, 'usage': {}, 'latency_ms': 1}
        service = Service(ctx, evaluator=evaluate, secret_reader=secrets.get)
        def save(name, value):
            events.append('save')
            secrets[name] = value
        args = argparse.Namespace(backend='cloudflare', account_id='a' * 32, model=None)
        with patch.object(sys.stdin, 'isatty', return_value=True), patch.object(cli.getpass, 'getpass', return_value='fixture-secret') as hidden:
            result = cli.setup(ctx, args, service=service, save_secret=save)
        self.assertTrue(result['ok'])
        hidden.assert_called_once()
        self.assertEqual(events, ['request', 'save'])
        self.assertEqual(ctx.settings['connection']['backend'], 'cloudflare')
        self.assertNotIn('fixture-secret', str(result))
        with patch.object(sys.stdin, 'isatty', return_value=False):
            with self.assertRaises(ValueError):
                cli.setup(ctx, args, service=service, save_secret=save)
        self.assertEqual(events, ['request', 'save'])


if __name__ == '__main__':
    unittest.main()
