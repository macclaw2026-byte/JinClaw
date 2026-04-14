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

from control_center_schemas import build_execution_handoff_schema  # noqa: E402
from control_plane_builder import build_control_plane  # noqa: E402
from conversation_context import conversation_focus_path, instruction_envelope_path, load_conversation_focus  # noqa: E402
from conversation_events import (  # noqa: E402
    build_conversation_event_registry,
    conversation_event_path,
    load_conversation_events,
    record_execution_handoff_event,
)
from manager import find_link_by_task_id, link_path, load_state, save_state, task_dir  # noqa: E402
from paths import BRAIN_RECEIPTS_ROOT, BRAIN_ROUTES_ROOT  # noqa: E402
from task_status_snapshot import build_task_status_snapshot  # noqa: E402
from telegram_binding import bind_telegram_message  # noqa: E402


class ExecutionEventKernelTest(unittest.TestCase):
    def setUp(self):
        self.provider = 'telegram'
        self.conversation_id = 'unit-execution-kernel'
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

    def test_execution_handoff_persists_into_event_stream_and_snapshot(self):
        result = bind_telegram_message(
            chat_id=self.conversation_id,
            chat_type='group',
            sender_id='user',
            sender_name='unit-user',
            message_id='msg-1',
            text='用 ziniao 浏览器打开已绑定店铺，进入对账中心导出三月份账务明细，并在导出历史确认结果',
        )
        task_id = str(((result.get('brain_route', {}) or {}).get('task_id', ''))).strip()
        self.assertTrue(task_id)
        self.task_ids.add(task_id)

        state = load_state(task_id)
        state.status = 'waiting_external'
        state.current_stage = state.current_stage or 'execute'
        state.next_action = 'poll_run:unit-run-1'
        link = find_link_by_task_id(task_id)
        linked_session_key = str(link.get('session_key', '')).strip()
        state.metadata['active_execution'] = {
            'run_id': 'unit-run-1',
            'stage_name': state.current_stage,
            'session_key': f'{linked_session_key}:autonomy:{task_id}',
            'linked_session_key': linked_session_key,
            'dispatched_at': '2026-04-14T18:00:00+00:00',
        }
        state.metadata['waiting_external'] = {
            'run_id': 'unit-run-1',
            'stage_name': state.current_stage,
            'reason': 'unit_test',
            'wait_status': 'timeout',
            'wait_error': '',
            'last_polled_at': '2026-04-14T18:01:00+00:00',
        }
        save_state(state)

        focus = load_conversation_focus(self.provider, self.conversation_id)
        record_execution_handoff_event(
            provider=self.provider,
            conversation_id=self.conversation_id,
            execution_handoff=build_execution_handoff_schema(
                enabled=True,
                contract_source='unit_test',
                task_id=task_id,
                stage_name='execute',
                handoff_status='waiting_external',
                provider=self.provider,
                conversation_id=self.conversation_id,
                session_key=str(focus.get('session_key', '')).strip(),
                linked_session_key=linked_session_key,
                execution_session_key=f'{linked_session_key}:autonomy:{task_id}',
                run_id='unit-run-1',
                runtime_mode=str(focus.get('resolved_mode', '')).strip(),
                runtime_mode_reason=str(focus.get('resolved_mode_reason', '')).strip(),
                next_action='poll_run:unit-run-1',
                wait_status='timeout',
                dispatched_at='2026-04-14T18:00:00+00:00',
                updated_at='2026-04-14T18:01:00+00:00',
                conversation_focus_ready=bool(focus.get('context_ready')),
            ),
        )

        events = load_conversation_events(self.provider, self.conversation_id, limit=10)
        event_types = [str(item.get('event_type', '')).strip() for item in events]
        self.assertIn('route_resolved', event_types)
        self.assertIn('execution_handoff_updated', event_types)
        self.assertLess(event_types.index('route_resolved'), event_types.index('execution_handoff_updated'))

        snapshot = build_task_status_snapshot(task_id)
        self.assertTrue(snapshot['execution_handoff']['enabled'])
        self.assertEqual(snapshot['execution_handoff']['handoff_status'], 'waiting_external')
        self.assertEqual(snapshot['execution_handoff']['runtime_mode'], 'mission_runtime')
        self.assertEqual(snapshot['execution_handoff']['execution_session_strategy'], 'autonomy_derived_session')
        self.assertEqual(snapshot['reply_contract']['execution_handoff']['handoff_status'], 'waiting_external')
        self.assertIn('Execution handoff is waiting_external via mission_runtime', snapshot['authoritative_summary'])

        registry = build_conversation_event_registry()
        row = next(
            item
            for item in (registry.get('items', []) or [])
            if str(item.get('provider', '')).strip() == self.provider and str(item.get('conversation_id', '')).strip() == self.conversation_id
        )
        self.assertTrue(row['has_execution_event'])
        self.assertEqual(row['latest_execution_status'], 'waiting_external')
        self.assertEqual(row['latest_execution_strategy'], 'autonomy_derived_session')

        plane = build_control_plane(stale_after_seconds=300, escalation_after_seconds=900)
        summary = (plane.get('system_snapshot', {}) or {}).get('summary', {}) or {}
        self.assertIn('conversation_event_with_execution_total', summary)
        self.assertGreaterEqual(int(summary.get('conversation_event_with_execution_total', 0) or 0), 1)


if __name__ == '__main__':
    unittest.main()
