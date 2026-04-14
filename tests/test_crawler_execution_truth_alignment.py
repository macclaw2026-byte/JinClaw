import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
CRAWLER_LOGIC = ROOT / 'crawler/logic'
for entry in (CONTROL_CENTER, ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import crawler.logic.crawler_contract as crawler_contract  # noqa: E402
import crawler.logic.crawler_runner as crawler_runner  # noqa: E402
import crawler_capability_profile as profile_module  # noqa: E402


class CrawlerExecutionTruthAlignmentTest(unittest.TestCase):
    def _write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def test_build_contract_rejects_walmart_shell_page_without_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reports_root = tmp / 'reports'
            sites_root = tmp / 'site-profiles'
            self._write_json(
                reports_root / 'walmart-latest-run.json',
                {
                    'site': 'walmart',
                    'query': 'wireless mouse',
                    'preferredOrder': ['direct-http-html', 'crawl4ai-cli'],
                    'taskReadySummary': {'recommendedAction': 'use-best-tool'},
                    'toolResults': [
                        {
                            'tool': 'direct-http-html',
                            'status': 'usable',
                            'score': 75,
                            'product_signal_count': 40,
                            'block_signal_count': 0,
                            'stdout_chars': 300001,
                            'stdout_head': '<!DOCTYPE html><html><head><title>wireless mouse - Walmart.com</title></head><body></body></html>',
                            'stderr_head': '',
                            'notes': 'raw urllib HTTP fetch',
                        },
                        {
                            'tool': 'crawl4ai-cli',
                            'status': 'blocked',
                            'score': 0,
                            'product_signal_count': 0,
                            'block_signal_count': 2,
                            'stdout_chars': 400,
                            'stdout_head': 'Robot or human?',
                            'stderr_head': '',
                            'notes': 'blocked',
                        },
                    ],
                },
            )
            sites_root.mkdir(parents=True, exist_ok=True)
            (sites_root / 'walmart.md').write_text('# walmart\n', encoding='utf-8')

            with patch.object(crawler_contract, 'REPORT_DIR', reports_root), patch.object(
                crawler_contract, 'SITE_PROFILE_DIR', sites_root
            ):
                contract = crawler_contract.build_contract('walmart')

            self.assertEqual(contract.mode, 'insufficient-evidence-or-blocked')
            self.assertIsNone(contract.comparison_summary['best_tool'])
            self.assertEqual(contract.comparison_summary['best_status'], 'blocked')
            self.assertIn('price', contract.comparison_summary['missing_required_fields'])
            self.assertTrue(contract.comparison_summary['disqualified_tools'])

    def test_build_contract_accepts_amazon_browser_dom_with_opened_url_title_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reports_root = tmp / 'reports'
            sites_root = tmp / 'site-profiles'
            self._write_json(
                reports_root / 'amazon-latest-run.json',
                {
                    'site': 'amazon',
                    'query': 'wireless mouse',
                    'preferredOrder': ['local-agent-browser-cli', 'crawl4ai-cli'],
                    'taskReadySummary': {'recommendedAction': 'use-best-tool'},
                    'toolResults': [
                        {
                            'tool': 'local-agent-browser-cli',
                            'status': 'usable',
                            'score': 75,
                            'product_signal_count': 180,
                            'block_signal_count': 0,
                            'stdout_chars': 120000,
                            'stdout_head': 'opened_url=https://www.amazon.com/s?k=wireless+mouse\nAmazon.com : wireless mouse\n- generic',
                            'stderr_head': '',
                            'notes': 'browser DOM capture',
                            'url': 'https://www.amazon.com/s?k=wireless+mouse',
                        },
                        {
                            'tool': 'crawl4ai-cli',
                            'status': 'usable',
                            'score': 75,
                            'product_signal_count': 120,
                            'block_signal_count': 0,
                            'stdout_chars': 130000,
                            'stdout_head': 'Search Amazon\nhttps://www.amazon.com/s?k=wireless+mouse',
                            'stderr_head': '',
                            'notes': 'markdown extract',
                            'url': 'https://www.amazon.com/s?k=wireless+mouse',
                        },
                    ],
                },
            )
            sites_root.mkdir(parents=True, exist_ok=True)
            (sites_root / 'amazon.md').write_text('# amazon\n', encoding='utf-8')

            with patch.object(crawler_contract, 'REPORT_DIR', reports_root), patch.object(
                crawler_contract, 'SITE_PROFILE_DIR', sites_root
            ):
                contract = crawler_contract.build_contract('amazon')

            self.assertEqual(contract.comparison_summary['best_tool'], 'local-agent-browser-cli')
            self.assertTrue(contract.comparison_summary['required_fields_met'])
            self.assertEqual(contract.task_ready_fields['title'], 'Amazon.com : wireless mouse')
            self.assertEqual(contract.task_ready_fields['link'], 'https://www.amazon.com/s?k=wireless+mouse')

    def test_build_contract_prefers_tool_row_task_ready_fields_over_truncated_head(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            reports_root = tmp / 'reports'
            sites_root = tmp / 'site-profiles'
            self._write_json(
                reports_root / 'walmart-latest-run.json',
                {
                    'site': 'walmart',
                    'query': 'wireless mouse',
                    'preferredOrder': ['direct-http-html'],
                    'taskReadySummary': {'recommendedAction': 'use-best-tool'},
                    'toolResults': [
                        {
                            'tool': 'direct-http-html',
                            'status': 'partial',
                            'score': 75,
                            'product_signal_count': 40,
                            'block_signal_count': 0,
                            'stdout_chars': 300001,
                            'stdout_head': '<!DOCTYPE html><html><head><title>wireless mouse - Walmart.com</title></head></html>',
                            'stderr_head': '',
                            'notes': 'full html had richer evidence',
                            'url': 'https://www.walmart.com/search?q=wireless+mouse',
                            'task_ready_fields': {
                                'title': 'wireless mouse - Walmart.com',
                                'price': '$47.67',
                                'rating': '',
                                'reviews': '',
                                'link': '/ip/Logitech-Advanced-Combo-Wireless-Keyboard-and-Mouse-Black/1998877576',
                                'promo': '',
                                'evidence_excerpt': ['wireless mouse - Walmart.com'],
                            },
                        }
                    ],
                },
            )
            sites_root.mkdir(parents=True, exist_ok=True)
            (sites_root / 'walmart.md').write_text('# walmart\n', encoding='utf-8')

            with patch.object(crawler_contract, 'REPORT_DIR', reports_root), patch.object(
                crawler_contract, 'SITE_PROFILE_DIR', sites_root
            ):
                contract = crawler_contract.build_contract('walmart')

            self.assertEqual(contract.comparison_summary['best_tool'], 'direct-http-html')
            self.assertTrue(contract.comparison_summary['required_fields_met'])
            self.assertEqual(contract.task_ready_fields['price'], '$47.67')
            self.assertIn('/ip/', contract.task_ready_fields['link'])

    def test_extract_task_ready_fields_decodes_tracking_link_and_skips_zero_price(self):
        text = """
        <title>wireless mouse - Walmart.com</title>
        $0.00
        wasPrice="$47.67"
        https://www.walmart.com/sp/track?bt=1&amp;rd=https%3A%2F%2Fwww.walmart.com%2Fip%2FLogitech-Advanced-Combo-Wireless-Keyboard-and-Mouse-Black%2F1998877576%3FadsRedirect%3Dtrue
        Add to cart
        out of 5 Stars
        """
        fields = crawler_contract._extract_task_ready_fields(
            'walmart',
            text,
            'https://www.walmart.com/search?q=wireless+mouse',
        )

        self.assertEqual(fields['price'], '$47.67')
        self.assertEqual(
            fields['link'],
            'https://www.walmart.com/ip/Logitech-Advanced-Combo-Wireless-Keyboard-and-Mouse-Black/1998877576?adsRedirect=true',
        )

    def test_choose_best_prefers_candidate_that_meets_required_fields(self):
        rows = [
            {
                'tool': 'local-agent-browser-cli',
                'status': 'usable',
                'score': 75,
                'product_signal_count': 180,
                'block_signal_count': 0,
                'stdout_chars': 100000,
                'stdout_head': '<title>wireless mouse - Amazon.com</title>',
                'stderr_head': '',
            },
            {
                'tool': 'crawl4ai-cli',
                'status': 'usable',
                'score': 75,
                'product_signal_count': 120,
                'block_signal_count': 0,
                'stdout_chars': 120000,
                'stdout_head': 'Wireless Mouse\nPrice: $19.99\nhttps://www.amazon.com/dp/B000TEST01',
                'stderr_head': '',
            },
        ]

        best = crawler_runner.choose_best(rows, site='amazon')
        self.assertIsNotNone(best)
        self.assertEqual(best['tool'], 'crawl4ai-cli')

    def test_capability_profile_prefers_contract_truth_and_flags_drift(self):
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
                    'mode': 'anonymous_public_crawl',
                    'confidence': 'high',
                    'tested_tools': ['curl-cffi', 'crawl4ai-cli', 'local-agent-browser-cli'],
                    'usable_tools': ['curl-cffi'],
                    'blocked_tools': [],
                    'selected_tool': 'curl-cffi',
                    'task_output_fields': {},
                },
            )
            self._write_json(
                reports_root / 'amazon-latest-run.json',
                {
                    'site': 'amazon',
                    'bestStatus': 'usable',
                    'bestTool': 'local-agent-browser-cli',
                    'taskReadySummary': {'notes': ['latest execution chose local browser']},
                },
            )
            self._write_json(
                reports_root / 'amazon-contract.json',
                {
                    'site': 'amazon',
                    'preferred_tool_order': ['crawl4ai-cli', 'local-agent-browser-cli', 'curl-cffi'],
                    'comparison_summary': {
                        'best_tool': 'crawl4ai-cli',
                        'best_status': 'usable',
                        'usable_tools': [{'tool': 'crawl4ai-cli'}, {'tool': 'local-agent-browser-cli'}],
                    },
                    'task_ready_fields': {
                        'title': 'Wireless Mouse',
                        'price': '$19.99',
                        'link': '/dp/B000TEST01',
                        'evidence_excerpt': ['Wireless Mouse'],
                    },
                },
            )

            with patch.object(profile_module, 'SITE_PROFILES_ROOT', sites_root), patch.object(
                profile_module, 'REPORTS_ROOT', reports_root
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_HISTORY_PATH', history_path
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_PROFILE_PATH', profile_path
            ), patch.object(
                profile_module,
                'summarize_project_memory_writebacks',
                return_value={'tasks_total': 0, 'target_counts': {}, 'source_counts': {}, 'recent_items': []},
            ):
                profile = profile_module.build_crawler_capability_profile()

            site = profile['sites'][0]
            summary = profile['summary']
            self.assertEqual(site['selected_tool'], 'crawl4ai-cli')
            self.assertEqual(site['execution_truth_source'], 'contract')
            self.assertEqual(site['route_preference_strength'], 'guarded')
            self.assertEqual((site.get('evidence_alignment', {}) or {}).get('status'), 'execution_conflict_and_profile_stale')
            self.assertEqual(summary['sites_with_evidence_drift'], 1)
            self.assertEqual(summary['evidence_alignment_score'], 0.0)

    def test_capability_profile_treats_none_selected_tool_as_empty_for_blocked_consensus(self):
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
                    'tested_tools': ['curl-cffi'],
                    'usable_tools': [],
                    'blocked_tools': ['curl-cffi'],
                    'selected_tool': '',
                    'task_output_fields': {},
                },
            )
            self._write_json(
                reports_root / '1688-latest-run.json',
                {
                    'site': '1688',
                    'bestStatus': 'blocked',
                    'bestTool': None,
                    'taskReadySummary': {'notes': ['still blocked']},
                },
            )
            self._write_json(
                reports_root / '1688-contract.json',
                {
                    'site': '1688',
                    'preferred_tool_order': ['curl-cffi'],
                    'comparison_summary': {
                        'best_tool': None,
                        'best_status': 'blocked',
                        'usable_tools': [],
                    },
                    'task_ready_fields': {'evidence_excerpt': []},
                },
            )

            with patch.object(profile_module, 'SITE_PROFILES_ROOT', sites_root), patch.object(
                profile_module, 'REPORTS_ROOT', reports_root
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_HISTORY_PATH', history_path
            ), patch.object(
                profile_module, 'CRAWLER_CAPABILITY_PROFILE_PATH', profile_path
            ), patch.object(
                profile_module,
                'summarize_project_memory_writebacks',
                return_value={'tasks_total': 0, 'target_counts': {}, 'source_counts': {}, 'recent_items': []},
            ):
                profile = profile_module.build_crawler_capability_profile()

            site = profile['sites'][0]
            self.assertEqual((site.get('evidence_alignment', {}) or {}).get('status'), 'blocked_consensus')
            self.assertEqual(profile['summary']['sites_with_evidence_drift'], 0)
            self.assertEqual(profile['summary']['evidence_alignment_score'], 100.0)


if __name__ == '__main__':
    unittest.main()
