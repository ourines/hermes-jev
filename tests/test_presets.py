import importlib
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PresetTests(unittest.TestCase):
    def test_task_triage_is_atomic_and_keeps_unknown_route(self):
        self.assertIsNotNone(importlib.util.find_spec('presets'), 'Decision presets not implemented')
        presets = importlib.import_module('presets')
        questions = presets.questions_for('task_triage')
        self.assertEqual(questions['category']['type'], 'choice')
        self.assertIn('unknown', questions['category']['criteria'])
        self.assertEqual(questions['requires_approval']['type'], 'noul')
        questions['category']['criteria'].clear()
        self.assertIn('unknown', presets.questions_for('task_triage')['category']['criteria'])

    def test_step_relevance_and_uncertainty_never_authorize(self):
        presets = importlib.import_module('presets')
        self.assertIn('ask_user', presets.questions_for('next_step')['next_step']['criteria'])
        self.assertEqual(presets.questions_for('relevance')['relevance']['type'], 'score')
        report = presets.assess({'answers': {
            'route': {'type': 'choice', 'choice': 'unknown', 'confidence': 0.99},
            'ambiguous': {'type': 'noul', 'noul': 0.5},
            'clear_no': {'type': 'noul', 'noul': 0.02},
            'risk': {'type': 'score', 'score': 1.1},
        }}, threshold=0.85)
        self.assertEqual(set(report['review_questions']), {'route', 'ambiguous', 'risk'})
        self.assertTrue(report['advisory_only'])
        self.assertFalse(report['execution_authorized'])
        self.assertNotIn('confidence', report['signals']['ambiguous'])
        with self.assertRaises(ValueError):
            presets.assess({'answers': {}}, threshold=float('nan'))
        with self.assertRaises(ValueError):
            presets.questions_for('not-a-preset')

    def test_review_threshold_is_opt_in(self):
        presets = importlib.import_module('presets')
        result = {'answers': {'choice': {'type': 'choice', 'choice': 'a', 'confidence': 0.1},
                              'yes': {'type': 'noul', 'noul': 0.5}}}
        report = presets.assess(result)
        self.assertFalse(report['review_policy_enabled'])
        self.assertEqual(report['review_questions'], [])
        self.assertIsNone(report['signals']['yes']['needs_review'])
        self.assertFalse(report['execution_authorized'])


if __name__ == '__main__':
    unittest.main()
