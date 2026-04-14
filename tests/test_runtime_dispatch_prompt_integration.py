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
from task_contract import TaskContract  # noqa: E402
from manager import create_task_from_contract, task_dir  # noqa: E402
from action_executor import _dispatch_prompt  # noqa: E402
import shutil  # noqa: E402


class RuntimeDispatchPromptIntegrationTest(unittest.TestCase):
    def tearDown(self):
        for task_id in [
            'runtime-dispatch-coding-integration',
            'runtime-dispatch-noncoding-integration',
            'runtime-dispatch-ziniao-integration',
        ]:
            d = task_dir(task_id)
            if d.exists():
                shutil.rmtree(d)

    def _create_task(self, task_id: str, goal: str):
        package = build_control_center_package(task_id, goal, source='unit-test')
        contract = TaskContract.from_dict({
            'task_id': task_id,
            'user_goal': package['goal'],
            'done_definition': package['done_definition'],
            'allowed_tools': package.get('allowed_tools', []),
            'forbidden_actions': package.get('forbidden_actions', []),
            'stages': package['stages'],
            'metadata': package['metadata'],
        })
        create_task_from_contract(contract)
        return package

    def test_runtime_dispatch_prompt_uses_gstack_lite_for_coding_task(self):
        self._create_task(
            'runtime-dispatch-coding-integration',
            'Implement a code fix and add regression tests for the runtime dispatch path',
        )
        prompt = _dispatch_prompt('runtime-dispatch-coding-integration', 'execute')
        self.assertIn('# JinClaw GStack-Lite Coding Discipline', prompt)
        self.assertIn('JinClaw coding execution request', prompt)
        self.assertIn('Goal:', prompt)
        self.assertIn('reflect', prompt)

    def test_runtime_dispatch_prompt_stays_native_for_non_coding_task(self):
        self._create_task(
            'runtime-dispatch-noncoding-integration',
            'Research marketplace competitors and produce a structured report',
        )
        prompt = _dispatch_prompt('runtime-dispatch-noncoding-integration', 'execute')
        self.assertIn('[Autonomy runtime execution request]', prompt)
        self.assertIn('user_goal:', prompt)
        self.assertNotIn('# JinClaw GStack-Lite Coding Discipline', prompt)

    def test_runtime_dispatch_prompt_carries_skill_guidance_for_ziniao_task(self):
        self._create_task(
            'runtime-dispatch-ziniao-integration',
            '用 ziniao 浏览器打开 Temu 店铺后台，进入对账中心并导出三月份账务明细',
        )
        prompt = _dispatch_prompt('runtime-dispatch-ziniao-integration', 'execute')
        self.assertIn('skill_guidance:', prompt)
        self.assertIn('GET /zclaw/tools', prompt)
        self.assertIn('ziniao-assistant', prompt)


if __name__ == '__main__':
    unittest.main()
