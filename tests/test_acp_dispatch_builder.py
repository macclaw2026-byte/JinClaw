import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

from orchestrator import build_control_center_package  # noqa: E402
from context_builder import build_stage_context  # noqa: E402
from acp_dispatch_builder import build_acp_dispatch_request  # noqa: E402


class AcpDispatchBuilderTest(unittest.TestCase):
    def test_coding_task_dispatch_request_contains_injected_prompt(self):
        package = build_control_center_package(
            'test-acp-dispatch-builder',
            'Implement a code fix and add regression tests for the dispatch verifier',
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
        stage_context = build_stage_context('test-acp-dispatch-builder', 'execute', contract, state)
        request = build_acp_dispatch_request(contract, stage_context)
        self.assertEqual(request['runtime'], 'acp')
        self.assertEqual(request['mode'], 'session')
        self.assertTrue(request['thread'])
        self.assertEqual(request['env']['OPENCLAW_SESSION'], '1')
        self.assertEqual(request['env']['JINCLAW_CODING_METHODOLOGY'], 'jinclaw-gstack-lite')
        self.assertTrue(request['prompt_components']['methodology_prompt_included'])
        self.assertIn('## Lifecycle', request['prompt'])
        self.assertIn('JinClaw coding execution request', request['prompt'])
        self.assertIn('think', request['metadata']['coding_lifecycle'])

    def test_non_coding_task_dispatch_request_stays_native(self):
        package = build_control_center_package(
            'test-acp-dispatch-builder-noncoding',
            'Research Amazon competitor listings and summarize findings',
            source='unit-test',
        )
        contract = {
            'user_goal': package['goal'],
            'done_definition': package['done_definition'],
            'allowed_tools': package['allowed_tools'],
            'stages': package['stages'],
            'metadata': package['metadata'],
        }
        request = build_acp_dispatch_request(contract, None)
        self.assertEqual(request['env']['JINCLAW_CODING_METHODOLOGY'], 'jinclaw-native')
        self.assertFalse(request['prompt_components']['methodology_prompt_included'])
        self.assertNotIn('## Lifecycle', request['prompt'])


if __name__ == '__main__':
    unittest.main()
