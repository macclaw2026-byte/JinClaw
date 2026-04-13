import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
AUTONOMY = ROOT / 'tools/openmoss/autonomy'
for p in [str(CONTROL_CENTER), str(AUTONOMY)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from acquisition_adapter_registry import build_acquisition_adapter_registry  # noqa: E402
from acquisition_result_normalizer import build_acquisition_execution_summary  # noqa: E402
from verifier_registry import TASKS_ROOT, run_verifier  # noqa: E402


class AcquisitionExecutionSummaryTest(unittest.TestCase):
    def tearDown(self):
        task_dir = TASKS_ROOT / 'test-acq-summary-verifier'
        if task_dir.exists():
            shutil.rmtree(task_dir)

    def _capabilities(self):
        return {
            'tools': [
                {'name': 'python', 'exists': True, 'provides': ['scrapy']},
                {'name': 'curl_cffi', 'exists': True},
                {'name': 'playwright', 'exists': True},
                {'name': 'playwright_stealth', 'exists': True},
                {'name': 'agent-browser-local', 'exists': True, 'provides': ['browser', 'agent-browser']},
                {'name': 'patchright', 'exists': True},
            ],
            'crawler_capability_profile': {
                'sites': [
                    {
                        'site': 'amazon',
                        'readiness': 'production_ready',
                        'selected_tool': 'curl-cffi',
                    }
                ]
            },
        }

    def _acquisition_hand(self):
        registry = build_acquisition_adapter_registry(self._capabilities())
        return {
            'enabled': True,
            'adapter_registry': registry,
            'route_candidates': [
                {
                    'route_id': 'primary:curl',
                    'adapter_id': 'curl_cffi_http',
                    'route_type': 'static_fetch',
                    'risk_level': 'low',
                },
                {
                    'route_id': 'validate:direct',
                    'adapter_id': 'direct_http_html',
                    'route_type': 'static_fetch',
                    'risk_level': 'low',
                },
            ],
            'execution_strategy': {
                'primary_route_id': 'primary:curl',
                'validation_route_ids': ['validate:direct'],
                'escalation_route_ids': [],
            },
        }

    def _report_payload(self):
        return {
            'generated_at': '2026-04-13T12:00:00+00:00',
            'sites': [
                {
                    'site': 'amazon',
                    'url': 'https://www.amazon.com/s?k=wireless+mouse',
                    'tool_results': [
                        {
                            'tool': 'curl-cffi',
                            'status': 'usable',
                            'arbitration_score': 88,
                            'normalized_task_output': {
                                'field_completeness': 0.6,
                                'populated_fields': ['title', 'price', 'link'],
                                'fields': {
                                    'title': 'Wireless Mouse',
                                    'price': '19.99',
                                    'link': '/dp/B000123456',
                                },
                            },
                            'false_positive': {'reasons': []},
                        },
                        {
                            'tool': 'direct-http-html',
                            'status': 'usable',
                            'arbitration_score': 76,
                            'normalized_task_output': {
                                'field_completeness': 0.6,
                                'populated_fields': ['title', 'price', 'link'],
                                'fields': {
                                    'title': 'Wireless Mouse',
                                    'price': '19.99',
                                    'link': '/dp/B000123456',
                                },
                            },
                            'false_positive': {'reasons': []},
                        },
                    ],
                }
            ],
        }

    def test_adapter_registry_exposes_enabled_and_observed_only_adapters(self):
        registry = build_acquisition_adapter_registry(self._capabilities())
        self.assertIn('curl_cffi_http', registry['available_adapter_ids'])
        self.assertIn('playwright_stealth_browser', registry['available_adapter_ids'])
        self.assertIn('patchright_browser', registry['observed_only_adapter_ids'])
        self.assertEqual(registry['route_to_enabled_adapter_ids']['static_fetch'][0], 'curl_cffi_http')
        self.assertIn('direct_http_html', registry['stack_to_enabled_adapter_ids']['http_static'])

    def test_execution_summary_reports_cross_route_validation(self):
        summary = build_acquisition_execution_summary(
            'test-acq-summary',
            'Collect public Amazon pricing evidence',
            self._report_payload(),
            self._acquisition_hand(),
            report_path='/tmp/crawler-tool-matrix.json',
        )
        self.assertEqual(summary['overall_summary']['consensus_status'], 'cross_route_validated')
        self.assertEqual(summary['site_consensus'][0]['validation_status'], 'cross_validated')
        self.assertFalse(summary['planned_but_not_executed_route_ids'])
        self.assertEqual(summary['route_runs'][0]['evidence_ref'], '/tmp/crawler-tool-matrix.json')

    def test_verifier_accepts_complete_acquisition_summary(self):
        task_id = 'test-acq-summary-verifier'
        task_dir = TASKS_ROOT / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        summary_path = task_dir / 'acquisition-summary.json'
        summary = build_acquisition_execution_summary(
            task_id,
            'Collect public Amazon pricing evidence',
            self._report_payload(),
            self._acquisition_hand(),
            report_path='/tmp/crawler-tool-matrix.json',
        )
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        contract = {
            'metadata': {
                'control_center': {
                    'acquisition_hand': self._acquisition_hand(),
                }
            }
        }
        state = {
            'metadata': {
                'crawler_execution': {
                    'acquisition_summary_json_path': str(summary_path),
                }
            }
        }
        (task_dir / 'contract.json').write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding='utf-8')
        (task_dir / 'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        result = run_verifier({'type': 'acquisition_summary_complete', 'task_id': task_id})
        self.assertTrue(result['ok'])
        self.assertEqual(result['consensus_status'], 'cross_route_validated')


if __name__ == '__main__':
    unittest.main()
