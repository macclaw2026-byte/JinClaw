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

from control_plane_builder import build_control_plane  # noqa: E402
from conversation_context import conversation_focus_path, instruction_envelope_path  # noqa: E402
from conversation_events import build_conversation_event_registry, conversation_event_path, load_conversation_events  # noqa: E402
from manager import link_path, task_dir  # noqa: E402
from paths import BRAIN_RECEIPTS_ROOT, BRAIN_ROUTES_ROOT  # noqa: E402
from telegram_binding import bind_telegram_message  # noqa: E402


class ConversationEventKernelTest(unittest.TestCase):
    def setUp(self):
        self.provider = 'telegram'
        self.conversation_id = 'unit-event-kernel'
        self.focus_path = conversation_focus_path(self.provider, self.conversation_id)
        self.envelope_path = instruction_envelope_path(self.provider, self.conversation_id)
        self.event_path = conversation_event_path(self.provider, self.conversation_id)
        self.route_path = BRAIN_ROUTES_ROOT / self.provider / f'{self.conversation_id}.json'
        self.receipt_path = BRAIN_RECEIPTS_ROOT / self.provider / f'{self.conversation_id}.json'
        self.link_file = link_path(self.provider, self.conversation_id)
        self.task_ids = set()

    def tearDown(self):
        for path in [self.focus_path, self.envelope_path, self.event_path, self.route_path, self.receipt_path, self.link_file]:
            if path.exists():
                path.unlink()
        for parent in [self.event_path.parent, self.route_path.parent, self.receipt_path.parent]:
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        for task_id in self.task_ids:
            d = task_dir(task_id)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    def test_telegram_binding_persists_canonical_conversation_event_chain(self):
        result = bind_telegram_message(
            chat_id=self.conversation_id,
            chat_type='group',
            sender_id='user',
            sender_name='unit-user',
            message_id='msg-1',
            text='用 ziniao 浏览器打开已绑定店铺，进入对账中心导出三月份账务明细，并在导出历史确认结果',
        )
        task_id = str(((result.get('brain_route', {}) or {}).get('task_id', ''))).strip()
        if task_id:
            self.task_ids.add(task_id)

        events = load_conversation_events(self.provider, self.conversation_id, limit=10)
        event_types = [str(item.get('event_type', '')).strip() for item in events]
        self.assertIn('ingress_received', event_types)
        self.assertIn('route_resolved', event_types)
        self.assertIn('reply_projection_emitted', event_types)
        self.assertLess(event_types.index('ingress_received'), event_types.index('route_resolved'))
        self.assertLess(event_types.index('route_resolved'), event_types.index('reply_projection_emitted'))

        registry = build_conversation_event_registry()
        row = next(
            item
            for item in (registry.get('items', []) or [])
            if str(item.get('provider', '')).strip() == self.provider and str(item.get('conversation_id', '')).strip() == self.conversation_id
        )
        self.assertTrue(row['has_ingress_event'])
        self.assertTrue(row['has_route_event'])
        self.assertTrue(row['has_reply_event'])

        plane = build_control_plane(stale_after_seconds=300, escalation_after_seconds=900)
        summary = (plane.get('system_snapshot', {}) or {}).get('summary', {}) or {}
        self.assertIn('conversation_event_total', summary)
        self.assertIn('conversation_event_with_reply_total', summary)
        self.assertGreaterEqual(int(summary.get('conversation_event_with_reply_total', 0) or 0), 1)


if __name__ == '__main__':
    unittest.main()
