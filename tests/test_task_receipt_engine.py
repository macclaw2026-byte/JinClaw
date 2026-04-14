import json
import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

from paths import BRAIN_RECEIPTS_ROOT  # noqa: E402
from task_receipt_engine import emit_route_receipt  # noqa: E402


class TaskReceiptEngineTest(unittest.TestCase):
    def test_emit_route_receipt_persists_reply_projection(self):
        provider = 'unit-test-reply-projection'
        conversation_id = 'conversation-1'
        receipt_path = BRAIN_RECEIPTS_ROOT / provider / f'{conversation_id}.json'
        if receipt_path.exists():
            receipt_path.unlink()
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
            self.assertEqual(persisted['reply_projection']['message_kind'], 'task_status')
        finally:
            if receipt_path.exists():
                receipt_path.unlink()
            parent = receipt_path.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()


if __name__ == '__main__':
    unittest.main()
