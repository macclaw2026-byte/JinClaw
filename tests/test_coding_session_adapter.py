import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

from orchestrator import build_control_center_package  # noqa: E402
from context_builder import build_stage_context  # noqa: E402
from coding_session_adapter import build_coding_session_payload  # noqa: E402


class CodingSessionAdapterTest(unittest.TestCase):
    def test_coding_payload_injects_gstack_prompt(self):
        package = build_control_center_package(
            'test-coding-session-adapter',
            'Implement a code fix and add regression tests for the runtime verifier',
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
            'current_stage': 'execute',
            'status': 'running',
            'next_action': 'start_stage:execute',
            'blockers': [],
            'stages': {'execute': {'attempts': 1, 'completed_subtasks': []}},
            'metadata': {},
        }
        stage_context = build_stage_context('test-coding-session-adapter', 'execute', contract, state)
        payload = build_coding_session_payload(contract, stage_context)
        self.assertEqual(payload['recommended_runtime'], 'acp')
        self.assertTrue(payload['requires_prompt_injection'])
        self.assertIn('## Lifecycle', payload['final_prompt'])
        self.assertIn('JinClaw coding execution request', payload['final_prompt'])
        self.assertIn('Goal:', payload['base_prompt'])

    def test_non_coding_payload_stays_native(self):
        package = build_control_center_package(
            'test-non-coding-session-adapter',
            'Research marketplace competitors and summarize findings',
            source='unit-test',
        )
        contract = {
            'user_goal': package['goal'],
            'done_definition': package['done_definition'],
            'allowed_tools': package['allowed_tools'],
            'stages': package['stages'],
            'metadata': package['metadata'],
        }
        payload = build_coding_session_payload(contract, None)
        self.assertFalse(payload['requires_prompt_injection'])
        self.assertEqual(payload['methodology']['methodology'], 'jinclaw-native')
        self.assertNotIn('## Lifecycle', payload['final_prompt'])


if __name__ == '__main__':
    unittest.main()
