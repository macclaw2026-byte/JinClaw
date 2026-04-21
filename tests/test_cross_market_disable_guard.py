import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
OPS = ROOT / 'tools/openmoss/ops'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))

import jinclaw_ops  # noqa: E402
import service_disable_registry  # noqa: E402
from project_scheduler_policy import build_project_scheduler_policy  # noqa: E402


def _load_cross_market_cycle_module():
    script = ROOT / 'skills/cross-market-arbitrage-engine/scripts/run_cross_market_arbitrage_cycle.py'
    openpyxl = types.ModuleType('openpyxl')
    openpyxl.Workbook = object
    styles = types.ModuleType('openpyxl.styles')
    styles.Font = object
    styles.PatternFill = object
    utils = types.ModuleType('openpyxl.utils')
    utils.get_column_letter = lambda index: 'A'
    spec = importlib.util.spec_from_file_location('cross_market_cycle_for_test', script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    with patch.dict(
        sys.modules,
        {
            'cross_market_cycle_for_test': module,
            'openpyxl': openpyxl,
            'openpyxl.styles': styles,
            'openpyxl.utils': utils,
        },
    ):
        spec.loader.exec_module(module)
    return module


class CrossMarketDisableGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_disabled_root = service_disable_registry.DISABLED_SERVICES_ROOT
        self.previous_persistent_disabled_root = service_disable_registry.PERSISTENT_DISABLED_SERVICES_ROOT
        service_disable_registry.DISABLED_SERVICES_ROOT = Path(self.tmp.name) / 'disabled_services'
        service_disable_registry.DISABLED_SERVICES_ROOT.mkdir(parents=True, exist_ok=True)
        service_disable_registry.PERSISTENT_DISABLED_SERVICES_ROOT = Path(self.tmp.name) / 'persistent_disabled_services'
        service_disable_registry.PERSISTENT_DISABLED_SERVICES_ROOT.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        service_disable_registry.DISABLED_SERVICES_ROOT = self.previous_disabled_root
        service_disable_registry.PERSISTENT_DISABLED_SERVICES_ROOT = self.previous_persistent_disabled_root
        self.tmp.cleanup()

    def _write_disabled_sentinel(self):
        path = service_disable_registry.disabled_service_path('cross_market_arbitrage')
        path.write_text(
            json.dumps(
                {
                    'service': 'cross_market_arbitrage',
                    'disabled': True,
                    'reason': 'unit_test_disabled',
                    'requires_manual_reenable': True,
                }
            ),
            encoding='utf-8',
        )
        return path

    def _write_persistent_disabled_sentinel(self):
        path = service_disable_registry.persistent_disabled_service_path('cross_market_arbitrage')
        path.write_text(
            json.dumps(
                {
                    'service': 'cross_market_arbitrage',
                    'disabled': True,
                    'reason': 'unit_test_persistent_disabled',
                    'requires_manual_reenable': True,
                }
            ),
            encoding='utf-8',
        )
        return path

    def test_scheduler_policy_fail_closes_cross_market_when_disabled(self):
        sentinel = self._write_disabled_sentinel()
        policy = build_project_scheduler_policy(
            crawler_profile={'feedback': {'coverage_status': 'strong'}, 'summary': {}},
            remediation_execution={'items': []},
            system_summary={},
        )

        cross_market = policy['cross_market_arbitrage']
        self.assertEqual(cross_market['recommended_mode'], 'disabled')
        self.assertFalse(cross_market['start_tasks'])
        self.assertFalse(cross_market['allow_report'])
        self.assertTrue(cross_market['service_disabled'])
        self.assertEqual(cross_market['disabled_service']['path'], str(sentinel))

    def test_scheduler_policy_fail_closes_cross_market_when_persistent_disable_exists(self):
        sentinel = self._write_persistent_disabled_sentinel()
        policy = build_project_scheduler_policy(
            crawler_profile={'feedback': {'coverage_status': 'strong'}, 'summary': {}},
            remediation_execution={'items': []},
            system_summary={},
        )

        cross_market = policy['cross_market_arbitrage']
        self.assertEqual(cross_market['recommended_mode'], 'disabled')
        self.assertFalse(cross_market['start_tasks'])
        self.assertTrue(cross_market['service_disabled'])
        self.assertEqual(cross_market['disabled_service']['path'], str(sentinel))

    def test_cross_market_execution_flags_disable_all_runtime_paths(self):
        cycle = _load_cross_market_cycle_module()
        flags = cycle._execution_flags_from_scheduler_policy(
            {
                'service_disabled': True,
                'start_tasks': True,
                'allow_report': True,
                'repair_mode': 'steady_balance',
            }
        )

        self.assertEqual(
            flags,
            {
                'allow_discovery': False,
                'allow_match': False,
                'allow_report': False,
            },
        )

    def test_doctor_does_not_report_missing_launch_agent_when_disabled(self):
        payload = {
            'gateway': {
                'service_running': True,
                'rpc_ok': True,
                'telegram_configured': True,
                'telegram_probe_ok': True,
                'telegram_operational': True,
            },
            'launch_agents': {
                key: {'loaded': True, 'expected_loaded': True, 'disabled': False}
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
            'message_pipeline': {
                'sessions_index_exists': True,
                'telegram_session_count': 1,
                'latest_user_at': '',
                'user_wait_seconds': None,
                'assistant_substantive_after_latest_user': True,
                'internal_flow_leak_detected': False,
            },
            'doctor_runtime': {
                'last_run_exists': True,
                'last_run_recent': True,
                'integration_health': {'ok': True},
            },
            'project_scheduler_policy': {},
        }
        payload['launch_agents']['cross_market_arbitrage'] = {
            'loaded': False,
            'expected_loaded': False,
            'disabled': True,
            'disabled_runtime_process': {'checked': True, 'running': False, 'items': []},
        }

        with patch.object(jinclaw_ops, 'status_payload', return_value=payload):
            doctor = jinclaw_ops.doctor_payload(refresh_doctor=False)

        self.assertNotIn('launch_agent_missing:cross_market_arbitrage', doctor['issues'])
        self.assertTrue(doctor['ok'])

    def test_doctor_reports_disabled_service_orphan_process(self):
        payload = {
            'gateway': {
                'service_running': True,
                'rpc_ok': True,
                'telegram_configured': True,
                'telegram_probe_ok': True,
                'telegram_operational': True,
            },
            'launch_agents': {
                key: {'loaded': True, 'expected_loaded': True, 'disabled': False}
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
            'message_pipeline': {
                'sessions_index_exists': True,
                'telegram_session_count': 1,
                'latest_user_at': '',
                'user_wait_seconds': None,
                'assistant_substantive_after_latest_user': True,
                'internal_flow_leak_detected': False,
            },
            'doctor_runtime': {
                'last_run_exists': True,
                'last_run_recent': True,
                'integration_health': {'ok': True},
            },
            'project_scheduler_policy': {},
        }
        payload['launch_agents']['cross_market_arbitrage'] = {
            'loaded': False,
            'expected_loaded': False,
            'disabled': True,
            'disabled_runtime_process': {
                'checked': True,
                'running': True,
                'items': [{'pid': 123, 'command': 'run_cross_market_arbitrage_cycle.py --mode daemon'}],
            },
        }

        with patch.object(jinclaw_ops, 'status_payload', return_value=payload):
            doctor = jinclaw_ops.doctor_payload(refresh_doctor=False)

        self.assertIn('disabled_service_process_running:cross_market_arbitrage', doctor['issues'])
        self.assertFalse(doctor['ok'])


if __name__ == '__main__':
    unittest.main()
