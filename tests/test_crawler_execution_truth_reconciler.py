import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import crawler_execution_truth_reconciler as reconciler  # noqa: E402
import crawler_remediation_executor as remediation_executor  # noqa: E402
from crawler.logic.crawler_contract import SiteContract  # noqa: E402


class CrawlerExecutionTruthReconcilerTest(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def _contract(self, site: str, *, best_tool: str | None, best_status: str, required_fields_met: bool, missing_fields=None):
        return SiteContract(
            site=site,
            query='wireless mouse',
            mode='best_single_tool_output' if best_tool else 'insufficient-evidence-or-blocked',
            first_run_rule='run-all',
            repeat_run_rule='repeat',
            auth_policy={},
            tested_tools=['local-agent-browser-cli', 'crawl4ai-cli'],
            preferred_tool_order=['local-agent-browser-cli', 'crawl4ai-cli'],
            blocked_tools=[] if best_tool else ['local-agent-browser-cli'],
            comparison_summary={
                'best_tool': best_tool,
                'best_status': best_status,
                'best_score': 75 if best_tool else 0,
                'required_fields_met': required_fields_met,
                'missing_required_fields': list(missing_fields or []),
                'disqualified_tools': [],
                'usable_tools': [{'tool': best_tool}] if best_tool else [],
                'all_tools': [{'tool': best_tool, 'status': best_status}] if best_tool else [],
            },
            task_ready_fields={
                'title': 'Amazon.com : wireless mouse' if best_tool else '',
                'price': '',
                'rating': '',
                'reviews': '',
                'link': 'https://www.amazon.com/s?k=wireless+mouse' if best_tool else '',
                'promo': '',
                'evidence_excerpt': ['Amazon.com : wireless mouse'],
            },
            generated_at='2026-04-13T12:00:00+00:00',
            evidence_sources=[],
        )

    def test_reconcile_site_execution_truth_applies_safe_alignment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reports_root = tmp / 'reports'
            site_profiles_root = tmp / 'site-profiles'
            legacy_path = tmp / 'site_profiles.json'

            self._write_json(
                reports_root / 'amazon-latest-run.json',
                {'bestTool': 'local-agent-browser-cli', 'bestStatus': 'usable'},
            )
            self._write_json(
                reports_root / 'amazon-contract.json',
                {'comparison_summary': {'best_tool': 'crawl4ai-cli', 'best_status': 'usable'}},
            )
            self._write_json(
                site_profiles_root / 'amazon.json',
                {
                    'site': 'amazon',
                    'mode': 'anonymous_public_crawl',
                    'confidence': 'high',
                    'selected_tool': 'curl-cffi',
                    'usable_tools': ['curl-cffi'],
                    'notes': ['legacy profile'],
                },
            )

            with patch.object(reconciler, 'REPORTS_ROOT', reports_root), patch.object(
                reconciler, 'SITE_PROFILES_ROOT', site_profiles_root
            ), patch.object(
                reconciler, 'LEGACY_SITE_PROFILES_PATH', legacy_path
            ), patch.object(
                reconciler, 'build_contract', return_value=self._contract('amazon', best_tool='local-agent-browser-cli', best_status='usable', required_fields_met=True)
            ):
                result = reconciler.reconcile_site_execution_truth('amazon')

            updated_profile = json.loads((site_profiles_root / 'amazon.json').read_text(encoding='utf-8'))
            updated_contract = json.loads((reports_root / 'amazon-contract.json').read_text(encoding='utf-8'))
            legacy = json.loads(legacy_path.read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'applied')
            self.assertEqual(updated_profile['selected_tool'], 'local-agent-browser-cli')
            self.assertEqual(updated_contract['comparison_summary']['best_tool'], 'local-agent-browser-cli')
            self.assertEqual(legacy['amazon']['preferredTools'][0], 'local-agent-browser-cli')

    def test_reconcile_site_execution_truth_refuses_unsafe_downgrade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reports_root = tmp / 'reports'
            site_profiles_root = tmp / 'site-profiles'
            legacy_path = tmp / 'site_profiles.json'

            self._write_json(
                reports_root / 'temu-latest-run.json',
                {'bestTool': 'local-agent-browser-cli', 'bestStatus': 'usable'},
            )
            self._write_json(
                reports_root / 'temu-contract.json',
                {'comparison_summary': {'best_tool': 'local-agent-browser-cli', 'best_status': 'usable'}},
            )
            self._write_json(
                site_profiles_root / 'temu.json',
                {
                    'site': 'temu',
                    'mode': 'browser_first_anonymous',
                    'confidence': 'medium',
                    'selected_tool': 'local-agent-browser-cli',
                    'usable_tools': ['local-agent-browser-cli'],
                },
            )

            with patch.object(reconciler, 'REPORTS_ROOT', reports_root), patch.object(
                reconciler, 'SITE_PROFILES_ROOT', site_profiles_root
            ), patch.object(
                reconciler, 'LEGACY_SITE_PROFILES_PATH', legacy_path
            ), patch.object(
                reconciler,
                'build_contract',
                return_value=self._contract('temu', best_tool=None, best_status='blocked', required_fields_met=False, missing_fields=['price', 'link']),
            ):
                result = reconciler.reconcile_site_execution_truth('temu')

            updated_profile = json.loads((site_profiles_root / 'temu.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'needs_revalidation')
            self.assertEqual(updated_profile['selected_tool'], 'local-agent-browser-cli')
            self.assertFalse(legacy_path.exists())

    def test_reconcile_site_execution_truth_applies_partial_route_when_required_fields_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reports_root = tmp / 'reports'
            site_profiles_root = tmp / 'site-profiles'
            legacy_path = tmp / 'site_profiles.json'

            self._write_json(
                reports_root / 'walmart-latest-run.json',
                {'bestTool': 'direct-http-html', 'bestStatus': 'partial'},
            )
            self._write_json(
                reports_root / 'walmart-contract.json',
                {'comparison_summary': {'best_tool': 'direct-http-html', 'best_status': 'partial'}},
            )
            self._write_json(
                site_profiles_root / 'walmart.json',
                {
                    'site': 'walmart',
                    'mode': 'anonymous_public_crawl',
                    'confidence': 'low',
                    'selected_tool': '',
                    'usable_tools': [],
                },
            )

            partial_contract = self._contract('walmart', best_tool='direct-http-html', best_status='partial', required_fields_met=True)
            partial_contract.task_ready_fields['price'] = '$47.67'
            partial_contract.task_ready_fields['link'] = '/ip/Logitech-Advanced-Combo-Wireless-Keyboard-and-Mouse-Black/1998877576'

            with patch.object(reconciler, 'REPORTS_ROOT', reports_root), patch.object(
                reconciler, 'SITE_PROFILES_ROOT', site_profiles_root
            ), patch.object(
                reconciler, 'LEGACY_SITE_PROFILES_PATH', legacy_path
            ), patch.object(
                reconciler, 'build_contract', return_value=partial_contract
            ):
                result = reconciler.reconcile_site_execution_truth('walmart')

            updated_profile = json.loads((site_profiles_root / 'walmart.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'applied')
            self.assertEqual(updated_profile['selected_tool'], 'direct-http-html')
            self.assertEqual(updated_profile['confidence'], 'high')
            self.assertEqual(updated_profile['preferred_tool_order'][0], 'direct-http-html')
            self.assertEqual(updated_profile['first_choice_extraction_mode'], 'best_single_tool_output')

    def test_executor_handles_execution_truth_reconcile_inline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            plan_path = tmp / 'plan.json'
            execution_path = tmp / 'execution.json'
            self._write_json(
                plan_path,
                {
                    'items': [
                        {
                            'id': 'crawler-remediation-9',
                            'priority': 'high',
                            'execution_type': 'execution_truth_reconcile',
                            'site': 'amazon',
                        }
                    ]
                },
            )
            with patch.object(remediation_executor, 'CRAWLER_REMEDIATION_PLAN_PATH', plan_path), patch.object(
                remediation_executor, 'CRAWLER_REMEDIATION_EXECUTION_PATH', execution_path
            ), patch.object(
                remediation_executor,
                'reconcile_execution_truth_batch',
                return_value={'applied_total': 1, 'needs_revalidation_total': 0, 'sites': [{'site': 'amazon', 'status': 'applied'}]},
            ):
                payload = remediation_executor.execute_crawler_remediation_plan(start_tasks=False)

            self.assertEqual(payload['inline_reconciled_total'], 1)
            self.assertEqual(payload['items'][0]['status'], 'inline_reconciled')
            self.assertEqual(payload['items'][0]['reconciliation']['sites'][0]['site'], 'amazon')


if __name__ == '__main__':
    unittest.main()
