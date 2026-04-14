import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

from response_policy_engine import build_route_receipt_text, build_route_reply_projection, render_reply_projection  # noqa: E402


class ResponsePolicyEngineTest(unittest.TestCase):
    def test_authoritative_status_receipt_surfaces_auto_answer_mode(self):
        route = {
            'mode': 'authoritative_task_status',
            'task_id': 'task-auto-answer',
            'authoritative_task_status': {
                'task_id': 'task-auto-answer',
                'authoritative_summary': (
                    'Authoritative task state says task-auto-answer is running at stage verify '
                    'with next action report_result. Current data answer mode is auto_answer.'
                ),
                'reply_contract': {
                    'acquisition_response': {
                        'enabled': True,
                        'response_mode': 'auto_answer',
                        'preview_lines': ['amazon: title=Wireless Mouse, price=19.99'],
                        'disclosure_lines': [],
                        'blocker_reasons': [],
                        'recommended_next_actions': [],
                        'requires_disclosure': False,
                        'requires_user_confirmation': False,
                    }
                },
                'milestone_progress': {},
                'governance': {},
                'blocked_runtime_state': {},
                'memory': {},
            },
        }
        text = build_route_receipt_text(route)
        self.assertIn('Current data answer mode is auto_answer.', text)
        self.assertIn('amazon: title=Wireless Mouse, price=19.99', text)
        projection = build_route_reply_projection(route)
        self.assertEqual(projection['message_kind'], 'task_status')
        self.assertEqual(projection['source_of_truth'], 'authoritative_task_status')
        self.assertEqual(projection['flags']['response_mode'], 'auto_answer')
        self.assertEqual(render_reply_projection(projection), text)

    def test_authoritative_status_receipt_requests_confirmation_for_guarded_answer(self):
        route = {
            'mode': 'authoritative_task_status',
            'task_id': 'task-guarded-answer',
            'authoritative_task_status': {
                'task_id': 'task-guarded-answer',
                'authoritative_summary': 'Authoritative task state says task-guarded-answer is running at stage verify with next action ask_user.',
                'reply_contract': {
                    'acquisition_response': {
                        'enabled': True,
                        'response_mode': 'confirm_then_guarded_answer',
                        'preview_lines': ['amazon: title=Wireless Mouse, price=19.99'],
                        'disclosure_lines': ['核心字段主要来自 medium-trust 的公开抓取/内容提取证据。'],
                        'blocker_reasons': [],
                        'recommended_next_actions': ['ask_user_to_confirm_guarded_release'],
                        'requires_disclosure': True,
                        'requires_user_confirmation': True,
                    }
                },
                'milestone_progress': {},
                'governance': {},
                'blocked_runtime_state': {},
                'memory': {},
            },
        }
        text = build_route_receipt_text(route)
        self.assertIn('当前数据回答模式是 confirm_then_guarded_answer。', text)
        self.assertIn('继续前需要你确认接受当前 guarded 证据级别。', text)
        projection = build_route_reply_projection(route)
        self.assertTrue(projection['flags']['requires_user_confirmation'])
        self.assertEqual(projection['flags']['response_mode'], 'confirm_then_guarded_answer')
        self.assertEqual(render_reply_projection(projection), text)

    def test_projection_keeps_selection_prefix_separate_from_summary(self):
        route = {
            'mode': 'authoritative_task_status',
            'task_id': 'task-selection-prefix',
            'selection_updated': True,
            'selected_task_alias': '对账任务',
            'authoritative_task_status': {
                'task_id': 'task-selection-prefix',
                'authoritative_summary': '当前任务状态已刷新。',
                'reply_contract': {
                    'acquisition_response': {
                        'enabled': False,
                    }
                },
                'milestone_progress': {},
                'governance': {},
                'blocked_runtime_state': {},
                'memory': {},
            },
        }
        projection = build_route_reply_projection(route)
        self.assertEqual(projection['selection_prefix'], '已切换到任务 对账任务。 ')
        self.assertEqual(projection['segments'][0]['key'], 'selection_prefix')
        self.assertEqual(projection['segments'][1]['key'], 'summary')
        self.assertTrue(render_reply_projection(projection).startswith('已切换到任务 对账任务。 当前任务状态已刷新。'))


if __name__ == '__main__':
    unittest.main()
