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

    def _fresh_doctor_result(self):
        return {
            'checked_at': '2026-04-13T18:15:00+00:00',
            'acquisition_health': {
                'enabled': True,
                'adapter_coverage': {
                    'sites_total': 4,
                    'sites_production_ready': 3,
                    'sites_attention_required': 1,
                    'available_adapter_total': 12,
                    'validation_family_total': 6,
                    'validation_families': ['official', 'browser', 'static'],
                    'source_trust_tier_total': 6,
                    'source_trust_tiers': ['official_source', 'public_fetch'],
                    'browser_runtime_ready_total': 5,
                    'browser_execution_profiles': ['dom_capture', 'stealth_scroll_capture'],
                    'stability_score': 72.5,
                },
                'attention_sites': [],
            },
            'integration_health': {
                'single_doctor_rule': True,
                'authoritative_doctor': 'tools/openmoss/control_center/system_doctor.py',
                'coding_chain': 'ok',
                'noncoding_chain': 'ok',
                'acquisition_chain': 'ok',
                'acquisition_hand': {
                    'field_synthesis_contract': True,
                    'delivery_requirements_contract': True,
                    'source_trust_contract': True,
                    'release_governance_contract': True,
                    'release_disclosure_contract': True,
                    'answer_synthesis_contract': True,
                    'answer_response_contract': True,
                    'response_handoff_contract': True,
                    'browser_execution_contract': True,
                    'validation_family_contract': True,
                },
                'ok': True,
            },
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

    def test_doctor_runtime_summary_refreshes_incomplete_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            last_run = tmp / 'last_run.json'
            self._write_json(
                last_run,
                {
                    'checked_at': '2026-04-13T18:00:00+00:00',
                    'integration_health': {
                        'ok': True,
                        'coding_chain': 'ok',
                        'noncoding_chain': 'ok',
                    },
                },
            )
            fresh = self._fresh_doctor_result()
            with patch.object(jinclaw_ops, 'DOCTOR_LAST_RUN_PATH', last_run), patch.object(
                jinclaw_ops,
                '_run_canonical_doctor_refresh',
                return_value={'ok': True, 'payload': fresh, 'error': ''},
            ), patch.object(
                jinclaw_ops,
                'utc_now',
                return_value=datetime(2026, 4, 13, 18, 10, 0, tzinfo=timezone.utc),
            ):
                summary = jinclaw_ops._doctor_runtime_summary(refresh_policy='if_needed')

            self.assertEqual(summary['last_run_at'], fresh['checked_at'])
            self.assertEqual(summary['integration_health']['acquisition_chain'], 'ok')
            self.assertTrue(summary['acquisition_health']['field_synthesis_contract'])
            self.assertTrue(summary['acquisition_health']['response_handoff_contract'])
            self.assertTrue(summary['acquisition_health']['browser_execution_contract'])
            self.assertTrue(summary['acquisition_health']['validation_family_contract'])
            self.assertTrue(summary['refresh']['attempted'])
            self.assertTrue(summary['refresh']['ok'])
            self.assertEqual(summary['refresh']['reason'], 'incomplete')
            self.assertEqual(summary['refresh']['source'], 'canonical_refresh')
            self.assertTrue(summary['refresh']['payload_complete'])

    def test_doctor_payload_requests_fresh_canonical_doctor(self):
        summary = {
            'sessions_index_exists': True,
            'telegram_session_count': 1,
            'latest_user_at': '',
            'user_wait_seconds': None,
            'assistant_after_latest_user': False,
            'assistant_substantive_after_latest_user': False,
            'internal_flow_leak_detected': False,
        }
        mock_status = self._base_status_payload(summary)
        with patch.object(jinclaw_ops, 'status_payload', return_value=mock_status) as mocked_status:
            payload = jinclaw_ops.doctor_payload()

        mocked_status.assert_called_once_with(refresh_doctor=True)
        self.assertTrue(payload['ok'])

    def test_upgrade_check_requests_fresh_doctor_payload(self):
        watch_payload = {
            'checked_at': '2026-04-13T18:10:00+00:00',
            'repo_count': 0,
            'fetch_mode': 'fresh',
            'degraded': False,
            'degraded_sources': [],
        }
        with patch.object(
            jinclaw_ops,
            'run_cmd',
            return_value={
                'ok': True,
                'returncode': 0,
                'stdout': json.dumps(watch_payload, ensure_ascii=False),
                'stderr': '',
            },
        ), patch.object(jinclaw_ops, 'doctor_payload', return_value={'ok': True}) as mocked_doctor, patch.object(
            jinclaw_ops, 'git_summary', return_value={'branch': 'test'}
        ), patch.object(
            jinclaw_ops, 'UPSTREAM_WATCH_STATE_PATH', Path('/tmp/does-not-exist.json')
        ), patch.object(
            jinclaw_ops, 'UPSTREAM_WATCH_REPORT_PATH', Path('/tmp/does-not-exist.md')
        ):
            payload = jinclaw_ops.upgrade_check_payload()

        mocked_doctor.assert_called_once_with(refresh_doctor=True)
        self.assertTrue(payload['watch_run']['ok'])
        self.assertTrue(payload['doctor']['ok'])

    def test_upgrade_check_surfaces_degraded_watch_run_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            state_path = tmp / 'state.json'
            report_path = tmp / 'latest-report.md'

            self._write_json(
                state_path,
                {
                    'checked_at': '2026-04-13T18:00:00+00:00',
                    'repos': {
                        'playwright': {
                            'repo': 'microsoft/playwright',
                            'pushed_at': '2026-04-13T16:45:00Z',
                            'latest_release': {'tag_name': 'v1.59.1'},
                        }
                    },
                },
            )
            report_path.write_text('# cached report\n', encoding='utf-8')

            watch_payload = {
                'checked_at': '2026-04-13T18:10:00+00:00',
                'repo_count': 1,
                'fetch_mode': 'cached_fallback',
                'degraded': True,
                'degraded_sources': [
                    {
                        'id': 'playwright',
                        'repo': 'microsoft/playwright',
                        'reason': 'github_api_rate_limited',
                        'used_cached_snapshot': True,
                    }
                ],
            }

            with patch.object(
                jinclaw_ops,
                'run_cmd',
                return_value={
                    'ok': True,
                    'returncode': 0,
                    'stdout': json.dumps(watch_payload, ensure_ascii=False),
                    'stderr': '',
                },
            ), patch.object(jinclaw_ops, 'doctor_payload', return_value={'ok': True}), patch.object(
                jinclaw_ops, 'git_summary', return_value={'branch': 'test'}
            ), patch.object(
                jinclaw_ops, 'UPSTREAM_WATCH_STATE_PATH', state_path
            ), patch.object(
                jinclaw_ops, 'UPSTREAM_WATCH_REPORT_PATH', report_path
            ):
                payload = jinclaw_ops.upgrade_check_payload()

            self.assertTrue(payload['watch_run']['ok'])
            self.assertTrue(payload['watch_run']['degraded'])
            self.assertEqual(payload['watch_run']['fetch_mode'], 'cached_fallback')
            self.assertEqual(payload['watch_run']['repo_count'], 1)
            self.assertEqual(payload['watch_run']['degraded_sources'][0]['reason'], 'github_api_rate_limited')


if __name__ == '__main__':
    unittest.main()
