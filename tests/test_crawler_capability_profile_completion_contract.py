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


class CrawlerCapabilityProfileCompletionContractTest(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def test_completion_contract_counts_governed_authenticated_site_as_complete_width(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sites_root = tmp / 'site-profiles'
            reports_root = tmp / 'reports'
            history_path = tmp / 'history.json'
            profile_path = tmp / 'profile.json'

            self._write_json(
                sites_root / 'amazon.json',
                {
                    'site': 'amazon',
                    'mode': 'anonymous_ready',
                    'confidence': 'high',
                    'tested_tools': ['curl-cffi'],
                    'usable_tools': ['curl-cffi'],
                    'blocked_tools': [],
                    'selected_tool': 'curl-cffi',
                    'task_output_fields': {'title': 'Mouse', 'price': '$19.99', 'link': 'https://example.com/a'},
                },
            )
            self._write_json(
                reports_root / 'amazon-latest-run.json',
                {
                    'site': 'amazon',
                    'bestStatus': 'usable',
                    'bestTool': 'curl-cffi',
                    'taskReadySummary': {'notes': ['ok']},
                },
            )
            self._write_json(
                reports_root / 'amazon-contract.json',
                {
                    'comparison_summary': {'best_tool': 'curl-cffi', 'best_status': 'usable', 'usable_tools': ['curl-cffi']},
                    'task_ready_fields': {'title': 'Mouse', 'price': '$19.99', 'link': 'https://example.com/a'},
                },
            )

            self._write_json(
                sites_root / '1688.json',
                {
                    'site': '1688',
                    'mode': 'anonymous_truth_check_only',
                    'confidence': 'low',
                    'tested_tools': ['playwright'],
                    'usable_tools': [],
                    'blocked_tools': ['playwright'],
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

            memory_overview = {
                'tasks_total': 2,
                'target_counts': {'project': 2},
                'source_counts': {'crawler_remediation_cycle': 1, 'seller_bulk_cycle': 1},
                'recent_items': [
                    {'task_id': 'project-crawler-remediation-cycle', 'last_entry': {'source': 'crawler_remediation_cycle', 'targets': ['project']}},
                    {'task_id': 'project-neosgo-seller-bulk', 'last_entry': {'source': 'seller_bulk_cycle', 'targets': ['project']}},
                ],
            }

            with patch.object(profile_module, 'SITE_PROFILES_ROOT', sites_root), patch.object(
                profile_module, 'REPORTS_ROOT', reports_root
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_HISTORY_PATH', history_path
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_PROFILE_PATH', profile_path
            ), patch.object(
                profile_module, 'summarize_project_memory_writebacks', return_value=memory_overview
            ):
                profile = profile_module.build_crawler_capability_profile()

            contract = profile['completion_contract']
            self.assertEqual(profile['summary']['width_score'], 50.0)
            self.assertEqual(profile['summary']['governed_width_score'], 100.0)
            self.assertEqual(profile['summary']['effective_width_score'], 100.0)
            self.assertEqual(contract['status'], 'complete')
            self.assertTrue(contract['goal_reached'])
            self.assertEqual(contract['completion_score'], 100.0)
            self.assertFalse(contract['blockers'])


if __name__ == '__main__':
    unittest.main()
