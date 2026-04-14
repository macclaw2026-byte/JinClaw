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

from brain_router import route_instruction  # noqa: E402
from conversation_context import (  # noqa: E402
    conversation_focus_path,
    instruction_envelope_path,
    load_conversation_focus,
)
from manager import link_path, task_dir  # noqa: E402
from route_guardrails import persist_route, reroot_route_if_needed  # noqa: E402


class ConversationContextKernelTest(unittest.TestCase):
    def setUp(self):
        self.provider = 'unit-focus'
        self.conversation_id = 'ctx-kernel'
        self.session_key = 'agent:main:unit-focus:ctx-kernel'
        self.task_ids = set()

    def tearDown(self):
        for path in [
            conversation_focus_path(self.provider, self.conversation_id),
            instruction_envelope_path(self.provider, self.conversation_id),
            link_path(self.provider, self.conversation_id),
        ]:
            if path.exists():
                path.unlink()
        for task_id in self.task_ids:
            d = task_dir(task_id)
            if d.exists():
                shutil.rmtree(d)

    def _route(self, text: str, message_id: str):
        route = route_instruction(
            provider=self.provider,
            conversation_id=self.conversation_id,
            conversation_type='direct',
            text=text,
            source='unit-test',
            sender_id='user',
            sender_name='unit-user',
            message_id=message_id,
            session_key=self.session_key,
        )
        route = reroot_route_if_needed(
            route=route,
            provider=self.provider,
            conversation_id=self.conversation_id,
            conversation_type='direct',
            goal=str(route.get('goal') or text),
            session_key=self.session_key,
        )
        persist_route(self.provider, self.conversation_id, route)
        task_id = str(route.get('task_id', '')).strip()
        if task_id:
            self.task_ids.add(task_id)
        return route

    def test_status_followup_recovers_from_focus_when_link_is_missing(self):
        seed = self._route(
            '用 ziniao 浏览器打开已绑定店铺，进入对账中心导出三月份账务明细，并在导出历史确认结果',
            'm-1',
        )
        self.assertTrue(str(seed.get('task_id', '')).strip())
        self.assertEqual(seed.get('conversation_runtime_mode'), 'mission_runtime')
        focus = load_conversation_focus(self.provider, self.conversation_id)
        self.assertTrue(focus.get('context_ready'))
        self.assertEqual(focus.get('resolved_mode'), 'mission_runtime')
        link = link_path(self.provider, self.conversation_id)
        if link.exists():
            link.unlink()

        followup = self._route('然后呢？', 'm-2')
        envelope = followup.get('instruction_envelope', {}) or {}
        self.assertTrue(followup.get('focus_restored_link'))
        self.assertEqual(envelope.get('explicit_intent_type'), 'status_followup')
        self.assertTrue(envelope.get('resolved_with_focus'))
        self.assertEqual(followup.get('mode'), 'authoritative_task_status')
        self.assertEqual(followup.get('conversation_runtime_mode'), 'mission_runtime')
        self.assertTrue(instruction_envelope_path(self.provider, self.conversation_id).exists())
        self.assertTrue(conversation_focus_path(self.provider, self.conversation_id).exists())

    def test_contextual_followup_binds_short_modifier_to_current_goal(self):
        self._route(
            '打开 ziniao 中已绑定的 Temu 店铺后台，进入 对账中心 -> 财务明细，筛选 3 月并导出',
            'm-1',
        )
        followup = self._route('还是三月', 'm-2')
        envelope = followup.get('instruction_envelope', {}) or {}
        self.assertEqual(envelope.get('explicit_intent_type'), 'contextual_followup')
        self.assertIn('当前任务目标', str(envelope.get('contextual_goal', '')))
        self.assertEqual(envelope.get('requested_mode'), 'mission_runtime')
        focus = load_conversation_focus(self.provider, self.conversation_id)
        self.assertEqual((focus.get('recent_user_goals', []) or [])[-1], '还是三月')
        self.assertTrue(focus.get('context_ready'))
        self.assertEqual(focus.get('resolved_mode'), 'mission_runtime')

    def test_contextual_followup_survives_after_status_followup(self):
        self._route(
            '打开 ziniao 中已绑定的 Temu 店铺后台，进入 对账中心 -> 财务明细，筛选 3 月并导出',
            'm-1',
        )
        self._route('然后呢？', 'm-2')
        followup = self._route('还是三月', 'm-3')
        envelope = followup.get('instruction_envelope', {}) or {}
        self.assertEqual(envelope.get('explicit_intent_type'), 'contextual_followup')
        self.assertIn('当前任务目标', str(envelope.get('contextual_goal', '')))
        focus = load_conversation_focus(self.provider, self.conversation_id)
        self.assertIn('筛选 3 月并导出', str(focus.get('current_goal', '')))
        self.assertEqual(followup.get('conversation_runtime_mode'), 'mission_runtime')

    def test_system_optimization_prefers_interactive_session_mode(self):
        route = self._route(
            '继续优化 Telegram 与直连的上下文内核，排查为什么 reply chain 还会漂移',
            'm-4',
        )
        envelope = route.get('instruction_envelope', {}) or {}
        self.assertEqual(envelope.get('requested_mode'), 'interactive_session')
        self.assertEqual(route.get('conversation_runtime_mode'), 'interactive_session')
        focus = load_conversation_focus(self.provider, self.conversation_id)
        self.assertEqual(focus.get('resolved_mode'), 'interactive_session')


if __name__ == '__main__':
    unittest.main()
