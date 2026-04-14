import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
AUTONOMY = ROOT / 'tools/openmoss/autonomy'
for p in [str(CONTROL_CENTER), str(AUTONOMY)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from manager import create_task_from_contract, load_state, save_state, task_dir  # noqa: E402
from runtime_service import _enforce_goal_continuation_gate  # noqa: E402
from task_contract import StageContract, TaskContract  # noqa: E402
from task_status_snapshot import build_task_status_snapshot  # noqa: E402


class GoalContinuationContractTest(unittest.TestCase):
    def setUp(self):
        self.task_id = 'unit-goal-continuation-contract'
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)

    def tearDown(self):
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)

    def test_strict_continuation_reopens_completed_task_without_goal_proof(self):
        contract = TaskContract(
            task_id=self.task_id,
            user_goal='Finish the full mission and do not stop at a partial checkpoint.',
            done_definition='Task only ends when goal proof exists',
            stages=[
                StageContract(name='understand', goal='understand'),
                StageContract(name='plan', goal='plan'),
                StageContract(name='execute', goal='execute'),
                StageContract(name='verify', goal='verify'),
                StageContract(name='learn', goal='learn'),
            ],
            metadata={
                'control_center': {
                    'strict_continuation_required': True,
                    'operating_discipline': {
                        'completion_guard': {
                            'default_stop_condition': 'goal_complete_or_boundary',
                            'requires_goal_completion_proof': True,
                            'treat_pr_as_milestone_only': True,
                            'treat_round_as_milestone_only': True,
                            'non_terminal_milestones': ['tests_green', 'pr_opened'],
                            'terminal_boundaries': ['governance_boundary', 'permission_boundary', 'safety_boundary'],
                        }
                    },
                }
            },
        )
        create_task_from_contract(contract)
        state = load_state(self.task_id)
        state.status = 'completed'
        state.current_stage = 'learn'
        state.next_action = 'noop'
        for name in state.stage_order:
            stage = state.stages.get(name)
            self.assertIsNotNone(stage)
            stage.status = 'completed'
            stage.summary = f'{name} completed before final proof'
        state.metadata['business_outcome'] = {
            'goal_satisfied': False,
            'user_visible_result_confirmed': False,
            'proof_summary': '',
        }
        save_state(state)

        reopened = _enforce_goal_continuation_gate(self.task_id)
        self.assertIsNotNone(reopened)
        self.assertEqual(reopened['action'], 'goal_continuation_reopened_for_missing_goal_proof')

        state = load_state(self.task_id)
        self.assertEqual(state.status, 'planning')
        self.assertEqual(state.current_stage, 'verify')
        self.assertEqual(state.next_action, 'start_stage:verify')

        snapshot = build_task_status_snapshot(self.task_id)
        continuation = snapshot.get('goal_continuation', {}) or {}
        self.assertTrue(continuation.get('enabled'))
        self.assertTrue(continuation.get('continuation_required'))
        self.assertIn('pr_opened', continuation.get('non_terminal_milestones', []))
        self.assertIn('Continuation is still required', snapshot.get('authoritative_summary', ''))


if __name__ == '__main__':
    unittest.main()
