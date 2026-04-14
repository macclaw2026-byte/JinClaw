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
from runtime_service import _run_capability_gap_self_heal  # noqa: E402
from task_contract import StageContract, TaskContract  # noqa: E402
from task_status_snapshot import build_task_status_snapshot  # noqa: E402


class CapabilityGapSelfHealTest(unittest.TestCase):
    def setUp(self):
        self.task_id = 'unit-capability-gap-self-heal'
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)

    def tearDown(self):
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)

    def test_local_dependency_reuse_reopens_stage_before_human_escalation(self):
        contract = TaskContract(
            task_id=self.task_id,
            user_goal='Recover from a missing curl dependency without stopping the mission early.',
            done_definition='Retry the execute stage after capability-gap local reuse is prepared',
            allowed_tools=['curl', 'python', 'search'],
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
        state.status = 'blocked'
        state.current_stage = 'execute'
        state.next_action = 'inspect_runtime_contract_or_environment'
        state.blockers = ['command not found: curl']
        execute_stage = state.stages.get('execute')
        self.assertIsNotNone(execute_stage)
        execute_stage.status = 'failed'
        execute_stage.blocker = 'command not found: curl'
        save_state(state)

        result = _run_capability_gap_self_heal(self.task_id)
        self.assertIsNotNone(result)
        self.assertEqual(result['action'], 'capability_gap_local_reuse_ready')

        state = load_state(self.task_id)
        self.assertEqual(state.status, 'planning')
        self.assertEqual(state.current_stage, 'execute')
        self.assertEqual(state.next_action, 'start_stage:execute')

        snapshot = build_task_status_snapshot(self.task_id)
        capability_gap = snapshot.get('capability_gap', {}) or {}
        self.assertTrue(capability_gap.get('enabled'))
        self.assertEqual(capability_gap.get('selected_path'), 'reuse_local_capability')
        self.assertIn('curl', [item.get('name') for item in capability_gap.get('local_tool_candidates', []) or []])
        tool_evolution_plan = capability_gap.get('tool_evolution_plan', {}) or {}
        self.assertTrue(tool_evolution_plan.get('enabled'))
        self.assertIn('reuse_local_capability', tool_evolution_plan.get('planned_actions', []) or [])
        self.assertIn('Capability-gap loop selected', snapshot.get('authoritative_summary', ''))


if __name__ == '__main__':
    unittest.main()
