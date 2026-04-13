import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

import capability_registry as capability_registry_module  # noqa: E402
from acquisition_adapter_registry import build_acquisition_adapter_registry  # noqa: E402
from crawler_probe_runner import _derive_probe_execution_plan  # noqa: E402


class AcquisitionExecutionPlanningTest(unittest.TestCase):
    def test_capability_registry_detects_matrix_runtime_tools(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            tools_root = tmp / 'tools'
            (tools_root / 'bin').mkdir(parents=True, exist_ok=True)
            (tools_root / 'matrix-venv' / 'bin').mkdir(parents=True, exist_ok=True)
            (tools_root / 'agent-browser-local').mkdir(parents=True, exist_ok=True)
            (tools_root / 'openmoss').mkdir(parents=True, exist_ok=True)
            (tools_root / 'bin' / 'crawl4ai').write_text('#!/bin/sh\n', encoding='utf-8')
            (tools_root / 'matrix-venv' / 'bin' / 'python').write_text('#!/bin/sh\n', encoding='utf-8')

            matrix_packages = {
                'curl_cffi': True,
                'playwright': True,
                'playwright_stealth': True,
                'parsel': True,
                'httpx': False,
                'selectolax': False,
                'nodriver': False,
                'browserforge': False,
                'patchright': False,
                'camoufox': False,
                'undetected_chromedriver': False,
                'selenium': False,
                'seleniumbase': False,
            }
            which_map = {
                'node': '/usr/bin/node',
                'curl': '/usr/bin/curl',
                'chromedriver': '',
                'python': '',
                'python3': '/usr/bin/python3',
            }

            with patch.object(capability_registry_module, 'TOOLS_ROOT', tools_root), patch.object(
                capability_registry_module,
                'TOOLS_BIN_ROOT',
                tools_root / 'bin',
            ), patch.object(
                capability_registry_module,
                'MATRIX_VENV_PYTHON',
                tools_root / 'matrix-venv' / 'bin' / 'python',
            ), patch.object(
                capability_registry_module,
                '_scan_skills',
                return_value=[],
            ), patch.object(
                capability_registry_module,
                '_scan_scripts',
                return_value=[],
            ), patch.object(
                capability_registry_module,
                '_scan_generated_capabilities',
                return_value=[],
            ), patch.object(
                capability_registry_module,
                '_scan_promoted_capabilities',
                return_value=[],
            ), patch.object(
                capability_registry_module,
                'build_crawler_capability_profile',
                return_value={'sites': []},
            ), patch.object(
                capability_registry_module,
                '_python_package_exists',
                return_value=False,
            ), patch.object(
                capability_registry_module,
                '_probe_python_runtime_packages',
                return_value=matrix_packages,
            ), patch.object(
                capability_registry_module.shutil,
                'which',
                side_effect=lambda name: which_map.get(name, ''),
            ):
                registry = capability_registry_module.build_capability_registry()

            tools_by_name = {item['name']: item for item in registry['tools']}
            self.assertTrue(tools_by_name['crawl4ai']['exists'])
            self.assertTrue(tools_by_name['python']['exists'])
            self.assertTrue(tools_by_name['curl_cffi']['exists'])
            self.assertTrue(tools_by_name['playwright']['exists'])
            self.assertTrue(tools_by_name['playwright_stealth']['exists'])
            self.assertTrue(tools_by_name['parsel']['exists'])

            adapter_registry = build_acquisition_adapter_registry(registry)
            for adapter_id in [
                'direct_http_html',
                'curl_cffi_http',
                'scrapy_cffi_extract',
                'crawl4ai_cli',
                'playwright_browser',
                'playwright_stealth_browser',
            ]:
                self.assertIn(adapter_id, adapter_registry['available_adapter_ids'])

    def test_probe_execution_plan_uses_local_routes_when_global_primary_is_nonlocal(self):
        capabilities = {
            'tools': [
                {'name': 'python', 'exists': True, 'provides': ['scrapy', 'direct-http-html']},
                {'name': 'crawl4ai', 'exists': True},
                {'name': 'curl_cffi', 'exists': True},
                {'name': 'playwright', 'exists': True},
                {'name': 'playwright_stealth', 'exists': True},
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
        registry = build_acquisition_adapter_registry(capabilities)
        acquisition_hand = {
            'enabled': True,
            'adapter_registry': registry,
            'route_candidates': [
                {
                    'route_id': 'primary:official',
                    'adapter_id': 'official_api_search',
                    'route_type': 'official_api',
                    'parallel_role': 'primary_delivery',
                },
                {
                    'route_id': 'validate:curl',
                    'adapter_id': 'curl_cffi_http',
                    'route_type': 'static_fetch',
                    'parallel_role': 'validation_probe',
                    'can_run_parallel': True,
                },
                {
                    'route_id': 'backup:direct',
                    'adapter_id': 'direct_http_html',
                    'route_type': 'static_fetch',
                    'parallel_role': 'escalation_backup',
                    'can_run_parallel': True,
                },
            ],
            'execution_strategy': {
                'mode': 'multi_route_consensus',
                'primary_route_id': 'primary:official',
                'validation_route_ids': ['validate:curl'],
                'escalation_route_ids': ['backup:direct'],
                'allow_parallel_validation': True,
            },
        }

        plan = _derive_probe_execution_plan(
            'Collect current public marketplace data and compare multiple local routes',
            {'selected_stack': {}, 'fallback_stacks': []},
            acquisition_hand,
        )

        self.assertEqual(plan['source'], 'acquisition_execution_strategy')
        self.assertEqual(plan['active_route_ids'], ['validate:curl', 'backup:direct'])
        self.assertEqual(plan['tool_ids'], ['curl_cffi', 'direct_http'])
        self.assertIn('primary:official', plan['skipped_route_ids'])


if __name__ == '__main__':
    unittest.main()
