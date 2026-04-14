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

from orchestrator import build_control_center_package  # noqa: E402
from manager import create_task_from_contract, task_dir  # noqa: E402
from task_contract import TaskContract  # noqa: E402
from task_status_snapshot import build_task_status_snapshot  # noqa: E402


class SkillActionPlaneContractTest(unittest.TestCase):
    def tearDown(self):
        task_id = 'unit-skill-action-plane-contract'
        d = task_dir(task_id)
        if d.exists():
            shutil.rmtree(d)

    def test_ziniao_skill_action_plane_reaches_snapshot(self):
        package = build_control_center_package(
            'unit-skill-action-plane-contract',
            '用 ziniao 浏览器打开 Temu 店铺后台，进入对账中心并导出三月份账务明细，在导出历史确认结果',
            source='unit-test',
        )
        contract = TaskContract.from_dict({
            'task_id': package['task_id'],
            'user_goal': package['goal'],
            'done_definition': package['done_definition'],
            'allowed_tools': package.get('allowed_tools', []),
            'forbidden_actions': package.get('forbidden_actions', []),
            'stages': package['stages'],
            'metadata': package['metadata'],
        })
        create_task_from_contract(contract)
        snapshot = build_task_status_snapshot('unit-skill-action-plane-contract')
        plane = snapshot.get('skill_action_plane', {}) or {}
        self.assertTrue(plane.get('enabled'))
        self.assertEqual(plane.get('preferred_skill_name'), 'ziniao-assistant')
        self.assertEqual(plane.get('preferred_action_id'), 'temu_finance_export_history_confirmation')
        self.assertIn('Skill action plane prefers', snapshot.get('authoritative_summary', ''))


if __name__ == '__main__':
    unittest.main()
