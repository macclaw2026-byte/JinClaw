import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
OPS = ROOT / 'tools/openmoss/ops'
CONTROL = ROOT / 'tools/openmoss/control_center'
if str(OPS) not in sys.path:
    sys.path.insert(0, str(OPS))
if str(CONTROL) not in sys.path:
    sys.path.insert(0, str(CONTROL))

import openclaw_selfheal  # noqa: E402
import generate_task_dashboard  # noqa: E402


class OpsRuntimeHardeningTest(unittest.TestCase):
    def test_json_safe_normalizes_runtime_only_values(self):
        payload = {
            'path': Path('/tmp/demo'),
            'when': datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
            'blob': b'hello',
            'tags': {'b', 'a'},
            'items': (1, 2),
        }

        safe = openclaw_selfheal._json_safe(payload)

        self.assertEqual(safe['path'], '/tmp/demo')
        self.assertEqual(safe['blob'], 'hello')
        self.assertEqual(safe['tags'], ['a', 'b'])
        self.assertEqual(safe['items'], [1, 2])
        self.assertTrue(safe['when'].startswith('2026-04-17T12:00:00'))

    def test_render_archived_incident_rows_shows_archived_process_records(self):
        html = generate_task_dashboard._render_archived_incident_rows(
            {
                'archived_process_items': [
                    {
                        'subject_id': 'ai.jinclaw.cross-market-arbitrage',
                        'name': 'Cross-market arbitrage',
                        'severity': 'medium',
                        'status': 'resolved',
                        'reason': 'service disabled by operator',
                        'archived_at': '2026-04-17T01:00:00+00:00',
                        'resolved_at': '2026-04-16T23:50:00+00:00',
                    }
                ]
            }
        )

        self.assertIn('ai.jinclaw.cross-market-arbitrage', html)
        self.assertIn('service disabled by operator', html)
        self.assertIn('2026-04-17T01:00:00+00:00', html)


if __name__ == '__main__':
    unittest.main()
