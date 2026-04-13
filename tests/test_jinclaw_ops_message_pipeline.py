import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
OPS = ROOT / 'tools/openmoss/ops'
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))

import jinclaw_ops  # noqa: E402


class JinclawOpsMessagePipelineTest(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def _write_jsonl(self, path: Path, items) -> None:
        lines = [json.dumps(item, ensure_ascii=False) for item in items]
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def _message(self, timestamp: str, role: str, content):
        return {
            'type': 'message',
            'timestamp': timestamp,
            'message': {
                'role': role,
                'content': content,
            },
        }

    def _assistant_text(self, text: str):
        return [{'type': 'text', 'text': text}]

    def _assistant_tool_call(self):
        return [{'type': 'toolCall', 'toolName': 'search', 'toolCallId': 'call-1', 'args': {}}]

    def _base_status_payload(self, message_pipeline):
        return {
            'gateway': {
                'service_running': True,
                'rpc_ok': True,
                'telegram_configured': True,
                'telegram_probe_ok': True,
                'telegram_operational': True,
            },
            'launch_agents': {
                key: {'loaded': True}
                for key in jinclaw_ops.LAUNCH_AGENTS
            },
            'runtime': {
                'selfheal_state_exists': True,
                'selfheal_recent': True,
                'upstream_watch_state_exists': True,
                'upstream_watch_recent': True,
                'main_link_exists': True,
                'brain_route_count': 1,
            },
            'message_pipeline': message_pipeline,
            'doctor_runtime': {
                'last_run_exists': True,
                'last_run_recent': True,
                'integration_health': {
                    'ok': True,
                    'coding_chain': 'ok',
                    'noncoding_chain': 'ok',
                    'acquisition_chain': 'ok',
                },
            },
            'project_scheduler_policy': {},
        }

    def test_message_pipeline_reconciles_telegram_user_with_main_reply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sessions_index = tmp / 'sessions.json'
            telegram_file = tmp / 'telegram.jsonl'
            main_file = tmp / 'main.jsonl'

            self._write_jsonl(
                telegram_file,
                [
                    self._message('2026-04-13T15:50:25+00:00', 'user', 'Nightly heartbeat'),
                ],
            )
            self._write_jsonl(
                main_file,
                [
                    self._message('2026-04-13T15:50:35+00:00', 'assistant', self._assistant_tool_call()),
                    self._message(
                        '2026-04-13T15:50:47+00:00',
                        'assistant',
                        self._assistant_text('Amazon premium wholesale 夜报已完成，结果如下。'),
                    ),
                ],
            )
            self._write_json(
                sessions_index,
                {
                    'agent:main:main': {
                        'sessionFile': str(main_file),
                        'updatedAt': 1776096767452,
                    },
                    'agent:main:telegram:group:999001': {
                        'sessionFile': str(telegram_file),
                        'updatedAt': 1776096719950,
                    },
                },
            )

            with patch.object(jinclaw_ops, 'SESSIONS_INDEX_PATH', sessions_index), patch.object(
                jinclaw_ops,
                'utc_now',
                return_value=datetime(2026, 4, 13, 16, 0, 0, tzinfo=timezone.utc),
            ):
                summary = jinclaw_ops.message_pipeline_summary()

            self.assertTrue(summary['assistant_after_latest_user'])
            self.assertTrue(summary['assistant_substantive_after_latest_user'])
            self.assertEqual(summary['latest_user_source_session'], 'telegram')
            self.assertEqual(summary['reply_source_session'], 'main')
            self.assertTrue(summary['cross_session_reply_detected'])
            self.assertEqual(summary['reply_gap_seconds'], 22)

            with patch.object(jinclaw_ops, 'status_payload', return_value=self._base_status_payload(summary)):
                payload = jinclaw_ops.doctor_payload()
            self.assertNotIn('telegram_user_message_without_substantive_reply', payload['issues'])

    def test_message_pipeline_keeps_issue_when_only_internal_flow_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sessions_index = tmp / 'sessions.json'
            telegram_file = tmp / 'telegram.jsonl'
            main_file = tmp / 'main.jsonl'

            self._write_jsonl(
                telegram_file,
                [
                    self._message('2026-04-13T15:50:25+00:00', 'user', 'Nightly heartbeat'),
                ],
            )
            self._write_jsonl(
                main_file,
                [
                    self._message('2026-04-13T15:50:35+00:00', 'assistant', self._assistant_tool_call()),
                ],
            )
            self._write_json(
                sessions_index,
                {
                    'agent:main:main': {
                        'sessionFile': str(main_file),
                        'updatedAt': 1776096767452,
                    },
                    'agent:main:telegram:group:999001': {
                        'sessionFile': str(telegram_file),
                        'updatedAt': 1776096719950,
                    },
                },
            )

            with patch.object(jinclaw_ops, 'SESSIONS_INDEX_PATH', sessions_index), patch.object(
                jinclaw_ops,
                'utc_now',
                return_value=datetime(2026, 4, 13, 16, 0, 0, tzinfo=timezone.utc),
            ):
                summary = jinclaw_ops.message_pipeline_summary()

            self.assertTrue(summary['assistant_after_latest_user'])
            self.assertFalse(summary['assistant_substantive_after_latest_user'])
            self.assertTrue(summary['internal_flow_leak_detected'])

            with patch.object(jinclaw_ops, 'status_payload', return_value=self._base_status_payload(summary)):
                payload = jinclaw_ops.doctor_payload()
            self.assertIn('telegram_user_message_without_substantive_reply', payload['issues'])


if __name__ == '__main__':
    unittest.main()
