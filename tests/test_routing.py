import importlib
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
package = types.ModuleType('hermes_jev')
package.__path__ = [str(ROOT)]
sys.modules.setdefault('hermes_jev', package)


class Context:
    def __init__(self):
        self.settings = {}
        self.state = State()

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def set_config(self, key, value):
        self.settings[key] = value


class State:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


MODELS = [
    {'id': 'fast', 'model': 'cheap-model', 'description': 'Simple questions, formatting and small edits.',
     'cost_tier': 'low', 'speed_tier': 'fast'},
    {'id': 'deep', 'model': 'reasoning-model', 'description': 'Complex debugging, multi-file changes and long reasoning.',
     'cost_tier': 'high', 'speed_tier': 'slow', 'strengths': ['debugging', 'architecture']},
]


class RoutingTests(unittest.TestCase):
    def test_question_contains_only_safe_candidate_metadata(self):
        routing = importlib.import_module('hermes_jev.routing')
        candidates = routing.validate_candidates(MODELS + [{'id': 'balanced', 'model': 'mid-model', 'description': 'General work.'}])
        question = routing.route_questions(candidates)['model']
        self.assertEqual(set(question['criteria']), {'fast', 'deep', 'balanced'})
        self.assertIn('Complex debugging', question['criteria']['deep'])
        self.assertNotIn('api_key', str(question))

    def test_service_routes_to_selected_model_and_local_flags_win(self):
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        seen = []
        remote = {'model': 'jev-fixture', 'usage': {'input_tokens': 10}, 'latency_ms': 2,
                  'answers': {'model': {'type': 'choice', 'choice': 'deep', 'confidence': 0.91,
                                        'probabilities': {'fast': 0.05, 'deep': 0.95}}},
                  'ok': False, 'execution_authorized': True, 'selected_model': 'attacker-model'}

        def evaluate(**kwargs):
            seen.append(kwargs)
            return remote

        service = Service(ctx, evaluator=evaluate, secret_reader=lambda name: 'fixture-secret')
        result = service.route({'task': '修复跨模块认证故障', 'candidates': MODELS, 'min_confidence': 0.8})
        self.assertTrue(result['ok'])
        self.assertEqual(result['selected_model'], 'reasoning-model')
        self.assertEqual(result['route']['route_id'], 'deep')
        self.assertTrue(result['route_accepted'])
        self.assertFalse(result['route_needs_review'])
        self.assertFalse(result['execution_authorized'])
        self.assertTrue(result['advisory_only'])
        self.assertEqual(result['confidence'], 0.91)
        self.assertNotEqual(result.get('selected_model'), 'attacker-model')
        for field in ('review', 'main_model_changed', 'active_model'):
            self.assertNotIn(field, result)
        self.assertEqual(seen[0]['state'], '修复跨模块认证故障')
        self.assertEqual(seen[0]['questions']['model']['criteria']['fast'], 'Simple questions, formatting and small edits. Cost: low Speed: fast')

    def test_accepted_route_arms_hermes_model_request_middleware(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('jev_plugin_root', ROOT / '__init__.py')
        plugin_root = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin_root)
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        service = Service(ctx, evaluator=lambda **kwargs: {
            'model': 'jev-fixture', 'answers': {'model': {'choice': 'deep', 'confidence': 0.95}},
        }, secret_reader=lambda name: 'fixture-secret')
        result = service.route({
            'task': 'multi-file debugging', 'candidates': MODELS,
            '_runtime': {'session_id': 'session-1', 'provider': 'openai-codex'},
        })
        self.assertTrue(result['model_control']['applied'])
        middleware = plugin_root._model_route_middleware(ctx)
        rewritten = middleware({'model': 'old-model', 'input': []}, session_id='session-1', provider='openai-codex')
        self.assertEqual(rewritten['request']['model'], 'reasoning-model')
        self.assertEqual(rewritten['request']['input'], [])
        self.assertIsNone(middleware({'model': 'old-model'}, session_id='other-session', provider='openai-codex'))
        unchanged = middleware({'model': 'old-model'}, session_id='session-1', provider='anthropic')
        self.assertEqual(unchanged['request']['model'], 'old-model')
        plugin_root._clear_model_route(ctx, session_id='session-1')
        self.assertIsNone(middleware({'model': 'old-model'}, session_id='session-1', provider='openai-codex'))

    def test_low_or_missing_confidence_requires_review_without_guessing(self):
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        for answer in ({'type': 'choice', 'choice': 'fast', 'confidence': 0.5},
                       {'type': 'choice', 'choice': 'fast'}):
            service = Service(ctx, evaluator=lambda **kwargs: {
                'model': 'jev-fixture', 'usage': {}, 'answers': {'model': answer}},
                secret_reader=lambda name: 'fixture-secret')
            result = service.route({'task': 'small task', 'candidates': MODELS, 'min_confidence': 0.8})
            with self.subTest(answer=answer):
                self.assertTrue(result['ok'])
                self.assertFalse(result['route_accepted'])
                self.assertTrue(result['route_needs_review'])
                self.assertIs(result['execution_authorized'], False)

    def test_invalid_candidates_fail_before_secret_or_network(self):
        from unittest.mock import Mock
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        secret = Mock(return_value='fixture-secret')
        evaluator = Mock()
        service = Service(ctx, evaluator=evaluator, secret_reader=secret)
        invalid = [[], MODELS[:1], [MODELS[0], {**MODELS[1], 'id': 'fast'}],
                   [MODELS[0], {**MODELS[1], 'model': 'cheap-model'}],
                   [MODELS[0], {**MODELS[1], 'description': 'x\nsecret'}]]
        for candidates in invalid:
            result = service.route({'task': 'x', 'candidates': candidates})
            with self.subTest(candidates=candidates):
                self.assertFalse(result['ok'])
                self.assertEqual(result['error'], 'routing_failed')
        secret.assert_not_called()
        evaluator.assert_not_called()

    def test_candidate_count_boundaries_are_explicit(self):
        from hermes_jev.routing import validate_candidates
        def candidates(count):
            return [{'id': f'model-{index}', 'model': f'model-{index}', 'description': 'A valid model profile.'}
                    for index in range(count)]
        self.assertEqual(len(validate_candidates(candidates(2))), 2)
        self.assertEqual(len(validate_candidates(candidates(32))), 32)
        for count in (1, 33):
            with self.subTest(count=count), self.assertRaises(ValueError):
                validate_candidates(candidates(count))

    def test_configured_routes_and_offline_cli_route_command(self):
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['model_routes'] = MODELS
        routes = Service(ctx).routes()
        self.assertTrue(routes['configured'])
        self.assertEqual(routes['candidates'][1]['model'], 'reasoning-model')
        self.assertFalse(routes['execution_authorized'])
        self.assertEqual(ctx.settings['model_routes'], MODELS)

        from hermes_jev.cli import build_parser, guide
        import argparse
        parser = argparse.ArgumentParser()
        build_parser(parser)
        self.assertEqual(parser.parse_args(['route', '--file', 'route.json']).jev_command, 'route')
        self.assertEqual(guide()['model_routing']['tool'], 'jev_route')
        self.assertEqual(parser.parse_args(['auto-route', '--enable']).jev_command, 'auto-route')

    def test_discovery_reads_hermes_ids_and_drops_variants(self):
        from hermes_jev.discovery import candidates_from_models
        models = candidates_from_models(
            ['gpt-5.6-luna', 'gpt-5.6-luna-900k', 'gpt-5.6-sol', 'gpt-5.6-sol:batch', 'dall-e-3'],
            provider='openai-codex', current_model='gpt-5.6-luna',
        )
        self.assertEqual([item['model'] for item in models], ['gpt-5.6-luna', 'gpt-5.6-sol'])
        self.assertTrue(all(item['provider'] == 'openai-codex' for item in models))
        self.assertIn('cheaper', models[0]['description'])

    def test_auto_route_is_off_by_default_and_passive_when_enabled(self):
        from hermes_jev.service import Service
        catalog = {'provider': 'openai-codex', 'current_model': 'gpt-5.6-luna',
                   'models': ['gpt-5.6-luna', 'gpt-5.6-sol']}
        ctx = Context()
        ctx.settings['connection'] = {'backend': 'typesafe'}
        seen = []
        service = Service(ctx, evaluator=lambda **kwargs: seen.append(kwargs) or {
            'model': 'jev-fixture', 'answers': {'model': {'choice': 'gpt-5.6-sol', 'confidence': 0.99}},
        }, secret_reader=lambda name: 'fixture-secret', catalog_reader=lambda provider: catalog)
        skipped = service.auto_route_turn('complex architecture review', {'session_id': 's1', 'turn_id': 't1'})
        self.assertEqual(skipped['error'], 'disabled')
        self.assertFalse(seen)
        ctx.set_config('model_route_enabled', True)
        result = service.auto_route_turn('complex architecture review', {
            'session_id': 's1', 'turn_id': 't1', 'provider': 'openai-codex',
        })
        self.assertTrue(result['ok'])
        self.assertEqual(result['selected_model'], 'gpt-5.6-sol')
        self.assertTrue(result['model_control']['applied'])
        self.assertEqual(service.auto_route_turn('/new', {'session_id': 's1', 'turn_id': 't2'})['error'], 'skipped_task')

    def test_auto_route_fails_open_without_raising(self):
        from hermes_jev.service import Service
        ctx = Context()
        ctx.settings['model_route_enabled'] = True
        ctx.settings['connection'] = {'backend': 'typesafe'}
        service = Service(ctx, evaluator=lambda **kwargs: (_ for _ in ()).throw(RuntimeError('paid path')),
                          secret_reader=lambda name: 'fixture-secret',
                          catalog_reader=lambda provider: {'models': ['a', 'b'], 'provider': 'x'})
        result = service.auto_route_turn('task', {'session_id': 's1'})
        self.assertFalse(result['ok'])
        self.assertIn(result['error'], {'auto_route_skipped', 'routing_failed'})
        self.assertFalse(result.get('applied'))


if __name__ == '__main__':
    unittest.main()