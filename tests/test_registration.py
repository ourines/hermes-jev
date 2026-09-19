import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RegistrationTests(unittest.TestCase):
    def test_manifest_is_compatible_with_hermes_021_installer(self):
        import re
        # Runtime doctor accepts v2, but the 0.21.3 installer caps at v1.
        manifest = (ROOT / 'plugin.yaml').read_text()
        version = re.search(r'^manifest_version: (\d+)$', manifest, re.MULTILINE)
        self.assertIsNotNone(version)
        self.assertLessEqual(int(version.group(1)), 1)

    def test_tool_cli_and_skill_register_without_network_or_secret(self):
        self.assertTrue((ROOT / '__init__.py').exists(), 'Plugin entrypoint missing')
        spec = importlib.util.spec_from_file_location('jev_plugin_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        class Ctx:
            tools = []
            commands = []
            skills = []
            def get_config(self, key, default=None): return default
            def register_tool(self, **kwargs): self.tools.append(kwargs)
            def register_cli_command(self, **kwargs): self.commands.append(kwargs)
            def register_skill(self, name, path): self.skills.append((name, path))
        ctx = Ctx()
        module.register(ctx)
        self.assertEqual([tool['name'] for tool in ctx.tools], ['jev_evaluate', 'jev_route'])
        result = ctx.tools[0]['handler']({'state': 'hello', 'preset': 'task_triage'})
        self.assertIn('not_configured', result)
        route_result = ctx.tools[1]['handler']({'task': 'hello', 'candidates': [
            {'id': 'fast', 'model': 'cheap', 'description': 'Simple tasks'},
            {'id': 'deep', 'model': 'capable', 'description': 'Complex tasks'},
        ]})
        self.assertIn('not_configured', route_result)
        self.assertTrue(ctx.skills[0][1].is_file())
        command = ctx.commands[0]
        parser = argparse.ArgumentParser()
        command['setup_fn'](parser)
        self.assertEqual(parser.parse_args(['setup', '--backend', 'typesafe']).backend, 'typesafe')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            command['handler_fn'](parser.parse_args(['status']))
        self.assertIn('credential_present', output.getvalue())
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                parser.parse_args(['setup', '--api-key', 'not-allowed'])


if __name__ == '__main__':
    unittest.main()
