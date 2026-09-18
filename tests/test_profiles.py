"""Real Hermes config/secret-scope integration, isolated temporary homes only."""
import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('hermes_jev')
package.__path__ = [str(ROOT)]
sys.modules.setdefault('hermes_jev', package)


@unittest.skipUnless(importlib.util.find_spec('hermes_constants'), 'Hermes runtime needed for profile integration')
class ProfileTests(unittest.TestCase):
    def test_real_context_and_secrets_follow_a_b_a_without_leak(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_cli.plugins import PluginContext, PluginManager
        from hermes_cli.plugins_manifest import PluginManifest
        from agent.secret_scope import set_secret_scope, reset_secret_scope, set_multiplex_active, is_multiplex_active
        Service = importlib.import_module('hermes_jev.service').Service
        prior = is_multiplex_active()
        set_multiplex_active(True)
        try:
            with tempfile.TemporaryDirectory(prefix='jev-profile-test-') as temp:
                homes = [Path(temp) / name for name in ('a', 'b')]
                for home in homes:
                    home.mkdir()
                    (home / 'config.yaml').write_text('model:\n  default: unchanged\n')
                ctx = PluginContext(PluginManifest(name='jev', key='jev'), PluginManager())
                seen = []
                def evaluate(**kwargs):
                    seen.append((kwargs['backend'], kwargs['token']))
                    return {'answers': {'q': {'type': 'noul', 'noul': 0.9}}}
                service = Service(ctx, evaluator=evaluate)
                for index in (0, 1, 0):
                    h = set_hermes_home_override(homes[index])
                    backend = ('typesafe', 'cloudflare')[index]
                    key = ('TYPESAFE_API_KEY', 'CLOUDFLARE_JEV_API_TOKEN')[index]
                    s = set_secret_scope({key: f'fixture-{index}'})
                    try:
                        ctx.set_config('connection', {'backend': backend, 'account_id': 'a' * 32})
                        self.assertEqual(ctx.get_config('connection')['backend'], backend)
                        self.assertTrue(service.run({'state': 'x', 'questions': {'q': {'type': 'noul', 'instructions': 'Is x present?'}}})['ok'])
                        empty = set_secret_scope({})
                        try:
                            self.assertEqual(service.run({'state': 'x', 'preset': 'task_triage'})['error'], 'missing_credential')
                        finally:
                            reset_secret_scope(empty)
                        import yaml
                        self.assertEqual(yaml.safe_load((homes[index] / 'config.yaml').read_text())['model']['default'], 'unchanged')
                    finally:
                        reset_secret_scope(s)
                        reset_hermes_home_override(h)
                self.assertEqual(seen, [('typesafe', 'fixture-0'), ('cloudflare', 'fixture-1'), ('typesafe', 'fixture-0')])
        finally:
            set_multiplex_active(prior)


if __name__ == '__main__':
    unittest.main()
