import json
import plistlib
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
OPS = ROOT / 'tools/openmoss/ops'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))

import system_doctor  # noqa: E402
import jinclaw_ops  # noqa: E402


class NeosgoOutreachDoctorCoverageTest(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def _write_plist(self, path: Path, payload) -> None:
        path.write_bytes(plistlib.dumps(payload))

    def _touch_source_files(self, tmp: Path):
        for name in ['run_outreach_cycle.py', 'send_outreach_progress_telegram.py', 'doctor.py']:
            (tmp / name).write_text('# test\n', encoding='utf-8')

    def _build_paths(self, tmp: Path):
        cycle_script = tmp / 'run_outreach_cycle.py'
        summary_script = tmp / 'send_outreach_progress_telegram.py'
        doctor_file = tmp / 'doctor.py'
        cycle_plist = tmp / 'cycle.plist'
        summary_plist = tmp / 'summary.plist'
        state_path = tmp / 'state.json'
        summary_path = tmp / 'latest-summary.json'
        events_path = tmp / 'events.jsonl'
        refill_path = tmp / 'lead-refill-state.json'
        telegram_state_path = tmp / 'telegram-summary-state.json'
        return {
            'cycle_script': cycle_script,
            'summary_script': summary_script,
            'doctor_file': doctor_file,
            'cycle_plist': cycle_plist,
            'summary_plist': summary_plist,
            'state_path': state_path,
            'summary_path': summary_path,
            'events_path': events_path,
            'refill_path': refill_path,
            'telegram_state_path': telegram_state_path,
        }

    def _patch_runtime(self, paths):
        return patch.multiple(
            system_doctor,
            NEOSGO_OUTREACH_REQUIRED_FILES=[
                paths['cycle_script'],
                paths['summary_script'],
                paths['cycle_plist'],
                paths['summary_plist'],
                paths['doctor_file'],
            ],
            NEOSGO_OUTREACH_STATE_PATH=paths['state_path'],
            NEOSGO_OUTREACH_SUMMARY_PATH=paths['summary_path'],
            NEOSGO_OUTREACH_EVENTS_PATH=paths['events_path'],
            NEOSGO_OUTREACH_REFILL_STATE_PATH=paths['refill_path'],
            NEOSGO_OUTREACH_TELEGRAM_STATE_PATH=paths['telegram_state_path'],
            NEOSGO_OUTREACH_CYCLE_PLIST_PATH=paths['cycle_plist'],
            NEOSGO_OUTREACH_SUMMARY_PLIST_PATH=paths['summary_plist'],
        )

    def _seed_common_files(self, paths, *, summary_generated_at: str, target_updated_at: str, candidate_status: str, approved_remaining: int, pending_batch: int, email_pending: bool = False, refill_attempted_at: str = '') -> None:
        self._write_plist(
            paths['cycle_plist'],
            {
                'Label': 'ai.jinclaw.neosgo-outreach-cycle-hourly',
                'StartInterval': 600,
                'ProgramArguments': ['/usr/bin/env', 'python3', str(paths['cycle_script'])],
            },
        )
        self._write_plist(
            paths['summary_plist'],
            {
                'Label': 'ai.jinclaw.neosgo-outreach-summary-3h',
                'StartInterval': 10800,
                'ProgramArguments': ['/usr/bin/env', 'python3', str(paths['summary_script'])],
            },
        )
        self._write_json(
            paths['state_path'],
            {
                'campaign_id': 'neosgo-test',
                'email_delivery_pending': email_pending,
                'last_email_sent_at': target_updated_at,
                'targets': {
                    'lead-1': {
                        'company_name': 'Lead One',
                        'status': 'email_sent_local_only',
                        'updated_at': target_updated_at,
                    }
                },
            },
        )
        self._write_json(
            paths['summary_path'],
            {
                'generated_at': summary_generated_at,
                'campaign_id': 'neosgo-test',
                'total_touched': 1,
                'candidate_supply': {
                    'status': candidate_status,
                    'approved_usable_remaining_total': approved_remaining,
                    'pending_batch_total': pending_batch,
                    'last_replenishment': {
                        'attempted_at': refill_attempted_at,
                        'status': 'ok' if refill_attempted_at else '',
                    },
                },
            },
        )
        self._write_json(
            paths['telegram_state_path'],
            {
                'last_generated_at': summary_generated_at,
                'delivery': {'returncode': 0},
            },
        )
        paths['events_path'].write_text(
            json.dumps({'type': 'email_sent_local_only', 'at': target_updated_at}, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )

    def test_neosgo_outreach_integration_ok_with_recent_progress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._touch_source_files(tmp)
            paths = self._build_paths(tmp)
            now = datetime.now(timezone.utc)
            recent = (now - timedelta(minutes=8)).isoformat()
            self._seed_common_files(
                paths,
                summary_generated_at=recent,
                target_updated_at=recent,
                candidate_status='ready',
                approved_remaining=4,
                pending_batch=200,
            )
            with self._patch_runtime(paths):
                result = system_doctor._run_neosgo_outreach_integration_checks()

        self.assertTrue(result.get('ok'))
        self.assertEqual(result.get('health_status'), 'active_recent')
        self.assertTrue(result.get('runtime_state_contract'))
        self.assertTrue(result.get('schedule_contract'))
        self.assertTrue(result.get('progress_liveness_contract'))
        self.assertTrue(result.get('stoppage_classification_contract'))

    def test_neosgo_outreach_integration_flags_stalled_ready_supply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self._touch_source_files(tmp)
            paths = self._build_paths(tmp)
            now = datetime.now(timezone.utc)
            stale = (now - timedelta(hours=2, minutes=5)).isoformat()
            self._seed_common_files(
                paths,
                summary_generated_at=stale,
                target_updated_at=stale,
                candidate_status='ready',
                approved_remaining=6,
                pending_batch=120,
            )
            with self._patch_runtime(paths):
                result = system_doctor._run_neosgo_outreach_integration_checks()

        self.assertFalse(result.get('ok'))
        self.assertEqual(result.get('health_status'), 'stalled_ready_supply')
        self.assertIn('neosgo_outreach_progress_stalled_with_ready_supply', result.get('errors', []))
        self.assertFalse(result.get('progress_liveness_contract'))

    def test_ops_doctor_surfaces_outreach_stall_issue(self):
        message_pipeline = {
            'sessions_index_exists': True,
            'telegram_session_count': 1,
            'latest_user_at': '',
            'user_wait_seconds': None,
            'assistant_after_latest_user': False,
            'assistant_substantive_after_latest_user': False,
            'internal_flow_leak_detected': False,
        }
        status = {
            'gateway': {
                'service_running': True,
                'rpc_ok': True,
                'telegram_configured': True,
                'telegram_probe_ok': True,
                'telegram_operational': True,
            },
            'launch_agents': {key: {'loaded': True, 'expected_loaded': True, 'disabled': False, 'disabled_runtime_process': {'running': False}} for key in jinclaw_ops.LAUNCH_AGENTS},
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
                'refresh': {'attempted': False, 'ok': True},
                'integration_health': {
                    'ok': False,
                    'neosgo_outreach': {
                        'health_status': 'stalled_ready_supply',
                        'summary_matches_runtime_state': True,
                    },
                },
            },
            'project_scheduler_policy': {},
        }
        with patch.object(jinclaw_ops, 'status_payload', return_value=status):
            payload = jinclaw_ops.doctor_payload()

        self.assertIn('neosgo_outreach_progress_stalled', payload['issues'])


if __name__ == '__main__':
    unittest.main()
