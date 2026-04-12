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


stage5 = load_module(
    "run_stage5_final_export",
    PROJECT_ROOT / "scripts/run_stage5_final_export.py",
)


class Stage5FinalExportTests(unittest.TestCase):
    def test_sort_key_prefers_higher_opportunity_then_competition(self):
        row_a = {"opportunity_score": "70.0", "competition_score": "60.0", "demand_score": "90.0"}
        row_b = {"opportunity_score": "68.0", "competition_score": "90.0", "demand_score": "90.0"}
        self.assertLess(stage5.sort_key(row_a), stage5.sort_key(row_b))

    def test_build_export_row_keeps_required_fields(self):
        row = {
            "keyword": "garden kneeler and seat",
            "decision": "qualified",
            "opportunity_score": "68.5",
            "representative_product_url": "https://www.amazon.com/dp/B0BVVDC3KH",
            "reason_summary": "test reason",
        }
        result = stage5.build_export_row(row, 1)
        self.assertEqual(result["final_rank"], 1)
        self.assertEqual(result["keyword"], "garden kneeler and seat")
        self.assertEqual(result["representative_product_url"], "https://www.amazon.com/dp/B0BVVDC3KH")


if __name__ == "__main__":
    unittest.main()
