# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/amazon-product-selection-engine")
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


analysis = load_module(
    "run_stage4_keyword_analysis",
    PROJECT_ROOT / "scripts/run_stage4_keyword_analysis.py",
)


class Stage4KeywordAnalysisTests(unittest.TestCase):
    def test_smart_scale_is_rejected_for_high_review_average(self):
        row = {
            "keyword_rank": "3",
            "keyword": "smart scale",
            "result_count": "6000",
            "review_avg": "20009.74",
            "sales_30d_avg": "2870.69",
            "sales_30d_min": "50",
            "sales_30d_max": "60000",
            "newest_listing_age_days": "27",
            "launch_date_earliest": "2017-02-20",
            "launch_date_latest": "2026-03-13",
        }
        result = analysis.analyze_row(row)
        self.assertEqual(result["decision"], "reject")
        self.assertIn("首页review均值过高", result["hard_fail_reason"])

    def test_garden_kneeler_is_qualified(self):
        row = {
            "keyword_rank": "2",
            "keyword": "garden kneeler and seat",
            "result_count": "419",
            "review_avg": "1403.69",
            "sales_30d_avg": "610.58",
            "sales_30d_min": "50",
            "sales_30d_max": "6000",
            "newest_listing_age_days": "15",
            "launch_date_earliest": "2017-07-17",
            "launch_date_latest": "2026-03-25",
        }
        result = analysis.analyze_row(row)
        self.assertEqual(result["decision"], "qualified")
        self.assertGreaterEqual(float(result["opportunity_score"]), 65.0)

    def test_low_demand_keyword_falls_to_reject(self):
        row = {
            "keyword_rank": "16",
            "keyword": "shed windows pack",
            "result_count": "6000",
            "review_avg": "141.27",
            "sales_30d_avg": "176.47",
            "sales_30d_min": "50",
            "sales_30d_max": "500",
            "newest_listing_age_days": "56",
            "launch_date_earliest": "2015-08-08",
            "launch_date_latest": "2026-02-12",
        }
        result = analysis.analyze_row(row)
        self.assertEqual(result["decision"], "reject")
        self.assertIn("首页30天销量均值偏低", result["hard_fail_reason"])


if __name__ == "__main__":
    unittest.main()
