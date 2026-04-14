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
from context_builder import build_stage_context  # noqa: E402
from coding_session_adapter import build_coding_session_payload  # noqa: E402
from acp_dispatch_builder import build_acp_dispatch_request  # noqa: E402
from manager import create_task_from_contract, task_dir  # noqa: E402
from task_contract import TaskContract  # noqa: E402
from action_executor import _dispatch_prompt  # noqa: E402
from paths import APPROVALS_ROOT, FETCH_ROUTES_ROOT, MISSIONS_ROOT  # noqa: E402


class ZiniaoSkillPlanningTest(unittest.TestCase):
    def tearDown(self):
        task_ids = [
            'test-ziniao-plan',
            'test-ziniao-dispatch',
            'test-marketplace-image-plan',
        ]
        for task_id in task_ids:
            for root in [MISSIONS_ROOT, APPROVALS_ROOT, FETCH_ROUTES_ROOT]:
                path = root / f'{task_id}.json'
                if path.exists():
                    path.unlink()
            d = task_dir(task_id)
            if d.exists():
                shutil.rmtree(d)
        cache_dir = ROOT / 'tools/openmoss/runtime/control_center/cache/stage_context'
        if cache_dir.exists():
            shutil.rmtree(cache_dir)

    def _create_task(self, task_id: str, goal: str):
        package = build_control_center_package(task_id, goal, source='unit-test')
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
        return package

    def test_ziniao_goal_selects_bridge_plan_and_skill_guidance(self):
        package = build_control_center_package(
            'test-ziniao-plan',
            '用 ziniao 浏览器登录 Temu 店铺后台，进入对账中心导出三月份账务明细，并在导出历史确认结果',
            source='unit-test',
        )
        cc = package['metadata']['control_center']
        self.assertEqual(cc['selected_plan']['plan_id'], 'ziniao_bridge_ops')
        self.assertTrue(cc['skill_guidance']['enabled'])
        self.assertIn('ziniao-assistant', cc['skill_guidance']['matched_skill_names'])
        self.assertTrue(cc['skill_guidance']['matched_skills'][0]['reference_paths'])
        self.assertTrue(cc['skill_action_plane']['enabled'])
        self.assertEqual(cc['skill_action_plane']['preferred_skill_name'], 'ziniao-assistant')
        self.assertEqual(cc['skill_action_plane']['preferred_action_id'], 'temu_finance_export_history_confirmation')
        self.assertIn('curl', package['allowed_tools'])

    def test_runtime_dispatch_prompt_includes_skill_guidance_for_non_coding_ziniao_task(self):
        package = self._create_task(
            'test-ziniao-dispatch',
            '打开 ziniao 中已绑定的 Temu 店铺后台，进入 对账中心 -> 财务明细，筛选 3 月并导出',
        )
        prompt = _dispatch_prompt('test-ziniao-dispatch', 'execute')
        self.assertIn('[Autonomy runtime execution request]', prompt)
        self.assertIn('skill_guidance:', prompt)
        self.assertIn('skill_action_plane:', prompt)
        self.assertIn('GET /zclaw/tools', prompt)
        self.assertIn('ziniao-assistant', prompt)
        self.assertIn('temu_finance_export_history_confirmation', prompt)
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
        context = build_stage_context('test-ziniao-dispatch', 'execute', contract, state)
        payload = build_coding_session_payload(contract, context)
        request = build_acp_dispatch_request(contract, context)
        self.assertTrue(context['skill_guidance']['enabled'])
        self.assertTrue(context['skill_action_plane']['enabled'])
        self.assertIn('Skill guidance:', payload['base_prompt'])
        self.assertIn('Skill action plane:', payload['base_prompt'])
        self.assertTrue(request['metadata']['skill_guidance_enabled'])
        self.assertTrue(request['metadata']['skill_action_plane_enabled'])
        self.assertIn('ziniao-assistant', request['metadata']['matched_skill_names'])
        self.assertEqual(request['metadata']['preferred_skill_action_id'], 'temu_finance_export_history_confirmation')

    def test_marketplace_without_image_no_longer_forces_image_pipeline(self):
        package = build_control_center_package(
            'test-marketplace-image-plan',
            'Research marketplace competitor pricing and produce a structured seller report',
            source='unit-test',
        )
        self.assertNotEqual(package['metadata']['control_center']['selected_plan']['plan_id'], 'local_image_pipeline')


if __name__ == '__main__':
    unittest.main()
