import json
import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

from orchestrator import build_control_center_package  # noqa: E402
from context_builder import build_stage_context  # noqa: E402


class CodingMethodologyInjectionTest(unittest.TestCase):
    def test_code_task_receives_gstack_lite_methodology(self):
        package = build_control_center_package(
            'test-coding-methodology',
            'Build a coding task that implements a new verifier and test the fix',
            source='unit-test',
        )
        cc = package['metadata']['control_center']
        methodology = cc['coding_methodology']
        self.assertTrue(methodology['enabled'])
        self.assertEqual(methodology['methodology'], 'jinclaw-gstack-lite')
        self.assertEqual(methodology['lifecycle'], ['think', 'plan', 'build', 'review', 'test', 'ship', 'reflect'])
        self.assertTrue(methodology['prompt_path'])
        self.assertIn('## Lifecycle', methodology['prompt_text'])

    def test_non_code_task_does_not_receive_coding_methodology(self):
        package = build_control_center_package(
            'test-non-coding-methodology',
            'Research Amazon marketplace competitor data and produce a report',
            source='unit-test',
        )
        methodology = package['metadata']['control_center']['coding_methodology']
        self.assertFalse(methodology['enabled'])
        self.assertEqual(methodology['methodology'], 'jinclaw-native')

    def test_stage_context_exposes_coding_methodology(self):
        package = build_control_center_package(
            'test-stage-context-methodology',
            'Implement a local code fix and add regression test coverage',
            source='unit-test',
        )
        contract = {
            'user_goal': package['goal'],
            'done_definition': package['done_definition'],
            'allowed_tools': package['allowed_tools'],
            'stages': package['stages'],
            'metadata': package['metadata'],
        }
        state = {
            'current_stage': 'plan',
            'status': 'planning',
            'next_action': 'start_stage:plan',
            'blockers': [],
            'stages': {'plan': {'attempts': 1, 'completed_subtasks': []}},
            'metadata': {},
        }
        context = build_stage_context('test-stage-context-methodology', 'plan', contract, state)
        methodology = context['coding_methodology']
        self.assertTrue(methodology['enabled'])
        self.assertEqual(methodology['methodology'], 'jinclaw-gstack-lite')
        self.assertIn('reflect', methodology['lifecycle'])


if __name__ == '__main__':
    unittest.main()
