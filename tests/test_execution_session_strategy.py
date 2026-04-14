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

from action_executor import _resolve_execution_session_binding  # noqa: E402
from conversation_context import conversation_focus_path  # noqa: E402
from manager import find_link_by_task_id, link_path, task_dir  # noqa: E402
from telegram_binding import bind_telegram_message  # noqa: E402


class ExecutionSessionStrategyTest(unittest.TestCase):
    def setUp(self):
        self.created = []
        self.cleanup_paths = []

    def tearDown(self):
        for path in self.cleanup_paths:
            if path.exists():
                path.unlink()
        for path in self.cleanup_paths:
            parent = path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        for task_id in self.created:
            d = task_dir(task_id)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    def _seed_route(self, conversation_id: str, text: str) -> tuple[str, dict]:
        provider = 'telegram'
        self.cleanup_paths.extend(
            [
                conversation_focus_path(provider, conversation_id),
                link_path(provider, conversation_id),
            ]
        )
        result = bind_telegram_message(
            chat_id=conversation_id,
            chat_type='group',
            sender_id='user',
            sender_name='unit-user',
            message_id=f'{conversation_id}-msg',
            text=text,
        )
        task_id = str(((result.get('brain_route', {}) or {}).get('task_id', '')).strip())
        self.assertTrue(task_id)
        self.created.append(task_id)
        return task_id, find_link_by_task_id(task_id)

    def test_mission_runtime_uses_autonomy_session(self):
        task_id, link = self._seed_route(
            'unit-mission-session-strategy',
            '用 ziniao 浏览器打开 Temu 店铺后台，进入对账中心并导出三月份账务明细',
        )
        binding = _resolve_execution_session_binding(link, task_id)
        self.assertEqual(binding['runtime_mode'], 'mission_runtime')
        self.assertEqual(binding['execution_session_strategy'], 'autonomy_derived_session')
        self.assertEqual(binding['execution_session_key'], f"{binding['linked_session_key']}:autonomy:{task_id}")

    def test_interactive_session_reuses_linked_session(self):
        task_id, link = self._seed_route(
            'unit-interactive-session-strategy',
            '请排查并修复 runtime dispatch path 的一个 bug，然后补回归测试',
        )
        binding = _resolve_execution_session_binding(link, task_id)
        self.assertEqual(binding['runtime_mode'], 'interactive_session')
        self.assertEqual(binding['execution_session_strategy'], 'linked_session')
        self.assertEqual(binding['execution_session_key'], binding['linked_session_key'])


if __name__ == '__main__':
    unittest.main()
