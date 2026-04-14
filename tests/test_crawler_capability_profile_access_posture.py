import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL = ROOT / 'tools/openmoss/control_center'
if str(CONTROL) not in sys.path:
    sys.path.insert(0, str(CONTROL))

import crawler_capability_profile as profile_module  # noqa: E402


class CrawlerCapabilityProfileAccessPostureTest(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def test_authenticated_truth_check_site_becomes_governed_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sites_root = tmp / 'site-profiles'
            reports_root = tmp / 'reports'
            history_path = tmp / 'history.json'
            profile_path = tmp / 'profile.json'

            self._write_json(
                sites_root / '1688.json',
                {
                    'site': '1688',
                    'mode': 'anonymous_truth_check_only',
                    'confidence': 'low',
                    'tested_tools': ['curl-cffi', 'playwright'],
                    'usable_tools': [],
                    'blocked_tools': ['curl-cffi', 'playwright'],
                    'authenticated_mode': {'supported': True},
                    'task_output_fields': {},
                },
            )
            (sites_root / '1688-auth-policy.md').write_text('# auth policy\n', encoding='utf-8')
            self._write_json(
                reports_root / '1688-latest-run.json',
                {
                    'site': '1688',
                    'bestStatus': 'blocked',
                    'bestTool': '',
                    'taskReadySummary': {'notes': ['auth required']},
                },
            )

            with patch.object(profile_module, 'SITE_PROFILES_ROOT', sites_root), patch.object(
                profile_module, 'REPORTS_ROOT', reports_root
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_HISTORY_PATH', history_path
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_PROFILE_PATH', profile_path
            ), patch.object(
                profile_module, 'summarize_project_memory_writebacks', return_value={'tasks_total': 0, 'target_counts': {}, 'source_counts': {}, 'recent_items': []}
            ):
                profile = profile_module.build_crawler_capability_profile()

            site = profile['sites'][0]
            summary = profile['summary']
            self.assertEqual(site['readiness'], 'governed_ready')
            self.assertTrue(site['governed_ready'])
            self.assertEqual(site['access_posture'], 'governed_authenticated_ready')
            self.assertEqual(site['preferred_access_route'], 'authorized_session')
            self.assertGreaterEqual(site['depth_score'], 60.0)
            self.assertGreaterEqual(site['stability_score'], 60.0)
            self.assertEqual(summary['sites_production_ready'], 0)
            self.assertEqual(summary['sites_attention_required'], 0)
            self.assertEqual(summary['sites_governed_ready'], 1)
            self.assertEqual(summary['sites_authorized_session_ready'], 1)
            self.assertEqual(summary['governed_width_score'], 100.0)


if __name__ == '__main__':
    unittest.main()
