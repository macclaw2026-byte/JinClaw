import importlib.util
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
MARKETING_SCRIPTS = ROOT / 'projects/neosgo-marketing-suite/scripts'
SEO_GEO_SCRIPTS = ROOT / 'projects/neosgo-seo-geo-engine/scripts'
LEAD_ENGINE_SCRIPTS = ROOT / 'skills/neosgo-lead-engine/scripts'
if str(MARKETING_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MARKETING_SCRIPTS))
if str(SEO_GEO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SEO_GEO_SCRIPTS))
if str(LEAD_ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(LEAD_ENGINE_SCRIPTS))

import refresh_lead_engine_daily_report  # noqa: E402
import run_neosgo_admin_ops_watcher  # noqa: E402


def _load_seller_bulk_runner():
    path = ROOT / 'tools/bin/neosgo-seller-bulk-runner.py'
    spec = importlib.util.spec_from_file_location('neosgo_seller_bulk_runner', path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


neosgo_seller_bulk_runner = _load_seller_bulk_runner()


def _load_rebuild_lead_engine():
    path = ROOT / 'skills/neosgo-lead-engine/scripts/rebuild_lead_engine_phased.py'
    spec = importlib.util.spec_from_file_location('rebuild_lead_engine_phased_for_tests', path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    original = sys.modules.get('duckdb')
    sys.modules['duckdb'] = types.SimpleNamespace()
    try:
        spec.loader.exec_module(module)
    finally:
        if original is None:
            sys.modules.pop('duckdb', None)
        else:
            sys.modules['duckdb'] = original
    return module


rebuild_lead_engine_phased = _load_rebuild_lead_engine()


class NeosgoOpsHardeningTest(unittest.TestCase):
    def test_refresh_views_passes_resource_knobs_into_subprocess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / 'lead_engine.duckdb'
            sql_path = tmp / 'views.sql'
            db_path.write_text('', encoding='utf-8')
            sql_path.write_text('select 1;', encoding='utf-8')

            with patch.object(
                refresh_lead_engine_daily_report.subprocess,
                'run',
                return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout='', stderr=''),
            ) as mocked_run:
                refresh_lead_engine_daily_report._refresh_views(
                    Path('/usr/bin/python3'),
                    db_path,
                    sql_path,
                    threads=6,
                    memory_limit='12GB',
                    preserve_insertion_order=True,
                )

        args = mocked_run.call_args.args[0]
        self.assertEqual(args[-3:], ['6', '12GB', 'true'])

    def test_poll_once_marks_transient_network_errors_as_degraded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor = Path(tmpdir) / 'cursor.txt'
            with patch.object(run_neosgo_admin_ops_watcher, 'CURSOR_PATH', cursor), patch.object(
                run_neosgo_admin_ops_watcher,
                '_poll_events',
                side_effect=run_neosgo_admin_ops_watcher.OpsWatcherError('GET /events network error: timed out'),
            ), patch.object(
                run_neosgo_admin_ops_watcher,
                '_network_diagnostics',
                return_value={'host': 'mc.neosgo.com', 'dns_ok': True},
            ):
                result = run_neosgo_admin_ops_watcher._poll_once(
                    {
                        'NEOSGO_ADMIN_AUTOMATION_KEY': 'secret',
                        'NEOSGO_ADMIN_BASE_URL': 'https://mc.neosgo.com',
                    }
                )

        self.assertTrue(result['ok'])
        self.assertTrue(result['degraded'])
        self.assertEqual(result['network_diagnostics']['host'], 'mc.neosgo.com')
        self.assertFalse(result['telegram_sent'])
        self.assertFalse(result['cursor_updated'])

    def test_seller_bulk_runner_guard_audit_explains_skip_reasons(self):
        candidate = {
            'sku': 'SKU-1',
            'canImport': False,
            'candidateStatus': 'existing',
            'uploadStatus': 'UPLOADED',
            'importStatus': 'DONE',
            'status': 'READY',
        }

        audit = neosgo_seller_bulk_runner.evaluate_candidate_guards(candidate, {'SKU-1'})

        self.assertIn('canImport=false', audit['reasons'])
        self.assertIn('not-new-import', audit['reasons'])
        self.assertIn('draft-listing-sku-exists', audit['reasons'])
        self.assertTrue(audit['draftListingSkuExists'])

    def test_rebuild_lead_engine_uses_structural_email_validation(self):
        sql = rebuild_lead_engine_phased.PHASES['normalized_contacts']

        self.assertIn("strpos(email, '@') > 1", sql)
        self.assertIn("strpos(split_part(email, '@', 2), '.') > 1", sql)
        self.assertIn("email not like '% %'", sql)
        self.assertNotIn("email ~", sql)


if __name__ == '__main__':
    unittest.main()
