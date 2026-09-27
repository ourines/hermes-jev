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
    def test_status_checks_names_only_and_never_claims_online_or_tool_visibility(self):
        import types
        from unittest.mock import Mock, patch
        package = types.ModuleType('hermes_jev')
        package.__path__ = [str(ROOT)]
        sys.modules.setdefault('hermes_jev', package)
        Service = __import__('hermes_jev.service', fromlist=['Service']).Service
        key = 'TYPESAFE_API_KEY'

        class NamesOnly(dict):
            def get(self, *args):
                raise AssertionError('must not read credential values')
            def __getitem__(self, name):
                raise AssertionError('must not read credential values')
            def __contains__(self, name):
                raise AssertionError('iterate names without mapping value access')

        cases = [
            ('typesafe', NamesOnly({key: object()}), NamesOnly(), True, True),
            ('typesafe', NamesOnly(), NamesOnly({key: object()}), True, False),
            ('typesafe', None, NamesOnly({key: object()}), True, False),
            ('typesafe', None, NamesOnly({key: object()}), False, True),
            ('typesafe', NamesOnly(), NamesOnly({key: object()}), False, True),
            ('typesafe', NamesOnly(), NamesOnly(), False, False),
            (None, NamesOnly({key: object()}), NamesOnly(), False, False),
        ]
        for backend, scope, environ, multiplex, present in cases:
            with self.subTest(backend=backend, scoped=scope is not None, multiplex=multiplex, present=present):
                ctx = Context()
                ctx.settings['connection'] = {'backend': backend}
                reader = Mock(side_effect=AssertionError('no secret reader'))
                evaluator = Mock(side_effect=AssertionError('no paid request'))
                service = Service(ctx, evaluator=evaluator, secret_reader=reader)
                scope_module = types.ModuleType('agent.secret_scope')
                scope_module.current_secret_scope = lambda: scope
                scope_module.is_multiplex_active = lambda: multiplex
                with patch.dict(sys.modules, {'agent.secret_scope': scope_module}), \
                        patch('os.environ', environ), \
                        patch('socket.socket', side_effect=AssertionError('no network')):
                    result = service.status()
                self.assertIs(result['credential_present'], present)
                self.assertIs(result['configured'], present)
                self.assertIs(result['online_verified'], False)
                self.assertEqual(result.get('verification_scope'), 'local_configuration_only')
                self.assertEqual(result.get('online_verification'), 'not_checked')
                self.assertEqual(result.get('agent_tool_visibility'), 'not_checked_in_this_cli_process')
                self.assertIn('names_only', result.get('credential_presence_scope', ''))
                self.assertIn('hermes jev test' if present else 'hermes jev setup', result.get('next_step', ''))
                if present:
                    self.assertIn('optional', result['next_step'])
                    self.assertIn('billed', result['next_step'])
                reader.assert_not_called()
                evaluator.assert_not_called()

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
        ctx.settings['connection'] = {'backend': 'openrouter'}
        service.run({'state': '写说明文档', 'preset': 'task_triage'})
        self.assertEqual(requests[-1]['backend'], 'openrouter')
        self.assertEqual(requests[-1]['model'], 'typesafe/jev-1.13')
        self.assertEqual(requests[-1]['account_id'], '')

    def test_each_backend_declares_a_credential_slot_and_a_default_model(self):
        import types
        package = types.ModuleType('hermes_jev')
        package.__path__ = [str(ROOT)]
        sys.modules.setdefault('hermes_jev', package)
        service = __import__('hermes_jev.service', fromlist=['Service'])
        self.assertEqual(set(service.SECRET_NAMES), set(service.MODELS))
        self.assertEqual(set(service.MODELS), {'typesafe', 'cloudflare', 'openrouter'})
        for backend, name in service.SECRET_NAMES.items():
            with self.subTest(backend=backend):
                self.assertNotEqual(name, 'OPENROUTER_API_KEY')
                self.assertTrue(service.MODELS[backend])

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
