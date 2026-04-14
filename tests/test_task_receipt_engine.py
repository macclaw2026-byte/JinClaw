import json
import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

from paths import BRAIN_RECEIPTS_ROOT  # noqa: E402
from conversation_events import conversation_event_path, load_conversation_events  # noqa: E402
from task_receipt_engine import emit_route_receipt  # noqa: E402


class TaskReceiptEngineTest(unittest.TestCase):
    def test_emit_route_receipt_persists_reply_projection(self):
        provider = 'unit-test-reply-projection'
        conversation_id = 'conversation-1'
        receipt_path = BRAIN_RECEIPTS_ROOT / provider / f'{conversation_id}.json'
        event_path = conversation_event_path(provider, conversation_id)
        if receipt_path.exists():
            receipt_path.unlink()
        if event_path.exists():
            event_path.unlink()
        route = {
            'mode': 'authoritative_task_status',
            'task_id': 'receipt-projection-task',
            'authoritative_task_status': {
                'task_id': 'receipt-projection-task',
                'authoritative_summary': '当前任务状态已刷新。',
                'reply_contract': {
                    'acquisition_response': {
                        'enabled': True,
                        'response_mode': 'guarded_answer',
                        'preview_lines': ['amazon: title=Mouse'],
                        'disclosure_lines': ['字段来自公开抓取证据。'],
                        'blocker_reasons': [],
                        'recommended_next_actions': [],
                        'requires_disclosure': True,
                        'requires_user_confirmation': False,
                    }
                },
                'delivery_contract': {
                    'enabled': True,
                    'delivery_mode': 'guarded_answer',
                    'channel': provider,
                    'cadence': 'event_driven',
                    'prefer_attachment_delivery': False,
                },
                'milestone_progress': {},
                'governance': {},
                'blocked_runtime_state': {},
                'memory': {},
            },
        }
        try:
            receipt = emit_route_receipt(route, provider=provider, conversation_id=conversation_id, session_key='')
            self.assertIn('reply_projection', receipt)
            projection = receipt['reply_projection']
            self.assertEqual(projection['message_kind'], 'task_status')
            self.assertEqual(projection['flags']['response_mode'], 'guarded_answer')
            self.assertEqual(receipt['text'], projection['rendered_text'])
            persisted = json.loads(receipt_path.read_text())
            self.assertIn('reply_projection', persisted)
            self.assertIn('delivery_contract', persisted)
            self.assertEqual(persisted['reply_projection']['message_kind'], 'task_status')
            self.assertEqual(persisted['delivery_contract']['delivery_mode'], 'guarded_answer')
            events = load_conversation_events(provider, conversation_id, limit=10)
            self.assertTrue(any(item.get('event_type') == 'reply_projection_emitted' for item in events))
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            if event_path.exists():
                event_path.unlink()
            parent = receipt_path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
            event_parent = event_path.parent
            if event_parent.exists() and not any(event_parent.iterdir()):
                event_parent.rmdir()


if __name__ == '__main__':
    unittest.main()
