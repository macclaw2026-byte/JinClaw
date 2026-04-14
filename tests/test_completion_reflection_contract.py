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
from runtime_service import _write_task_postmortem  # noqa: E402
from task_contract import StageContract, TaskContract  # noqa: E402
from task_status_snapshot import build_task_status_snapshot  # noqa: E402


class CompletionReflectionContractTest(unittest.TestCase):
    def setUp(self):
        self.task_id = 'unit-completion-reflection-contract'
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)

    def tearDown(self):
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)

    def test_terminal_task_writes_outcome_evaluation_and_reflection_report(self):
        contract = TaskContract(
            task_id=self.task_id,
            user_goal='Verify completion reflection artifacts are written for terminal tasks.',
            done_definition='Outcome evaluation and reflection are both visible in snapshot',
            stages=[
                StageContract(name='understand', goal='understand'),
                StageContract(name='plan', goal='plan'),
                StageContract(name='execute', goal='execute'),
                StageContract(name='verify', goal='verify'),
                StageContract(name='learn', goal='learn'),
            ],
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
            stage.summary = f'{name} completed in unit reflection test'
            if name == 'verify':
                stage.verification_status = 'passed'
        state.metadata['business_outcome'] = {
            'goal_satisfied': True,
            'user_visible_result_confirmed': True,
            'proof_summary': 'unit completion reflection proof',
        }
        state.learning_backlog = ['promote reusable rule']
        save_state(state)

        _write_task_postmortem(self.task_id, reason='unit_completion_reflection')
        snapshot = build_task_status_snapshot(self.task_id)

        outcome = snapshot.get('outcome_evaluation', {}) or {}
        reflection = snapshot.get('reflection_report', {}) or {}
        self.assertTrue(outcome.get('enabled'))
        self.assertEqual(outcome.get('outcome_status'), 'goal_reached')
        self.assertGreater(float(outcome.get('completion_score', 0.0) or 0.0), 0.0)
        self.assertTrue(Path(str(outcome.get('path', '')).strip()).exists())
        self.assertTrue(reflection.get('enabled'))
        self.assertTrue(reflection.get('optimization_proposals'))
        self.assertTrue(reflection.get('reusable_rules'))
        self.assertTrue(Path(str(reflection.get('path', '')).strip()).exists())
        self.assertIn('Outcome evaluation is goal_reached', snapshot.get('authoritative_summary', ''))
        self.assertIn('Reflection report has', snapshot.get('authoritative_summary', ''))


if __name__ == '__main__':
    unittest.main()
