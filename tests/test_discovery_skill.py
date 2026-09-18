"""The opt-in ordinary skill is discoverable without plugin namespaces."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DiscoverySkillTests(unittest.TestCase):
    def test_standalone_skill_has_trigger_and_safe_cli_fallback(self):
        path = ROOT / 'skills' / 'jev' / 'SKILL.md'
        self.assertTrue(path.is_file(), 'Missing discoverable companion skill')
        text = path.read_text()
        self.assertTrue(text.startswith('---\n'))
        self.assertRegex(text, r'(?m)^name: jev$')
        description = re.search(r'(?m)^description: "(.+)"$', text).group(1)
        self.assertLessEqual(len(description), 60)
        self.assertIn('Jev', description[:57])
        for instruction in ('hermes jev status', 'hermes jev test', 'hermes jev guide',
                            'hermes jev evaluate --file', 'jev_evaluate',
                            'task_triage', 'next_step', 'relevance', '不计费', '不自动'):
            self.assertIn(instruction, text)
        self.assertNotRegex(text, r'/Users/|/home/')


if __name__ == '__main__':
    unittest.main()
