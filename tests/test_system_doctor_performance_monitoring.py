import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

import system_doctor  # noqa: E402


class SystemDoctorPerformanceMonitoringTest(unittest.TestCase):
    def test_derive_performance_summary_flags_stdout_leak_as_degraded(self):
        summary = system_doctor._derive_doctor_performance_summary(
            '2026-04-17T12:00:00+00:00',
            total_seconds=48.0,
            phase_timings=[
                {
                    'phase': 'integration_health_checks',
                    'elapsed_seconds': 7.2,
                    'captured_stdout_chars': 320,
                    'stdout_leak_detected': True,
                    'stdout_head': '{"payload": "too large"}',
                }
            ],
            history_entries=[],
        )

        self.assertTrue(summary['stdout_leak_detected'])
        self.assertEqual(summary['regression']['status'], 'degraded')
        self.assertIn('unexpected_stdout_output_detected', summary['regression']['reasons'])
        self.assertEqual(summary['stdout_sources'][0]['phase'], 'integration_health_checks')

    def test_derive_performance_summary_flags_runtime_regression_from_history(self):
        history_entries = [
            {
                'checked_at': '2026-04-17T10:00:00+00:00',
                'total_seconds': 40.0,
                'stdout_leak_detected': False,
                'phase_elapsed_seconds': {
                    'control_plane_build': 10.0,
                    'doctor_queue_processing': 6.0,
                },
                'regression': {'status': 'ok', 'degraded': False},
            },
            {
                'checked_at': '2026-04-17T10:30:00+00:00',
                'total_seconds': 42.0,
                'stdout_leak_detected': False,
                'phase_elapsed_seconds': {
                    'control_plane_build': 9.5,
                    'doctor_queue_processing': 6.4,
                },
                'regression': {'status': 'ok', 'degraded': False},
            },
            {
                'checked_at': '2026-04-17T11:00:00+00:00',
                'total_seconds': 41.0,
                'stdout_leak_detected': False,
                'phase_elapsed_seconds': {
                    'control_plane_build': 9.8,
                    'doctor_queue_processing': 6.2,
                },
                'regression': {'status': 'ok', 'degraded': False},
            },
        ]
        summary = system_doctor._derive_doctor_performance_summary(
            '2026-04-17T12:00:00+00:00',
            total_seconds=63.0,
            phase_timings=[
                {
                    'phase': 'control_plane_build',
                    'elapsed_seconds': 18.5,
                    'captured_stdout_chars': 0,
                    'stdout_leak_detected': False,
                    'stdout_head': '',
                },
                {
                    'phase': 'doctor_queue_processing',
                    'elapsed_seconds': 13.0,
                    'captured_stdout_chars': 0,
                    'stdout_leak_detected': False,
                    'stdout_head': '',
                },
            ],
            history_entries=history_entries,
        )

        self.assertEqual(summary['regression']['status'], 'degraded')
        self.assertIn('doctor_total_runtime_regressed', summary['regression']['reasons'])
        self.assertEqual(len(summary['regression']['slow_phases']), 2)
        self.assertGreater(summary['history']['baseline']['median_total_seconds'], 0.0)


if __name__ == '__main__':
    unittest.main()
