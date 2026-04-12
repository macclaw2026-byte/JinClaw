# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import importlib.util
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
PROJECT_ROOT = ROOT / "projects/amazon-product-selection-engine"
CONFIG_PATH = PROJECT_ROOT / "config/project-config.json"
MANIFEST_PATH = PROJECT_ROOT / "config/stage-manifest.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


stage1_runner = load_module(
    "run_stage1_sellersprite_official_export",
    PROJECT_ROOT / "scripts/run_stage1_sellersprite_official_export.py",
)
validator = load_module(
    "validate_stage1_export",
    PROJECT_ROOT / "scripts/validate_stage1_export.py",
)


class AmazonProductSelectionEngineTests(unittest.TestCase):
    def test_project_config_points_to_tracked_manifest(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            config["paths"]["stage_manifest_json"],
            str(MANIFEST_PATH),
        )
        self.assertIn("governance", config)
        self.assertIn("doctor_coverage", config)

    def test_stage_manifest_uses_official_export_contract(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        stage_1 = manifest["stages"][0]
        self.assertEqual(stage_1["id"], "stage_1_sellersprite_export")
        joined = " ".join(stage_1["browser_actions"]).lower()
        self.assertIn("official xlsx", joined)
        self.assertIn("my exported data", joined)

    def test_stage3_manifest_uses_hybrid_doctor_runner(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        stage_3 = manifest["stages"][2]
        self.assertEqual(stage_3["id"], "stage_3_amazon_keyword_collection")
        self.assertTrue(stage_3["automation_contract"]["runner_script"].endswith("run_stage3_hybrid_with_doctor.py"))
        joined = " ".join(stage_3["browser_actions"]).lower()
        self.assertIn("doctor monitoring", joined)
        self.assertIn("amazon search html", joined)

    def test_build_product_research_url_encodes_expected_filters(self):
        parsed = urlparse(stage1_runner.build_product_research_url())
        query = parse_qs(parsed.query)
        self.assertEqual(query["market"], ["US"])
        self.assertEqual(query["monthName"], ["bsr_sales_nearly"])
        self.assertEqual(json.loads(query["sellerTypes"][0]), ["FBM"])
        self.assertEqual(json.loads(query["pkgDimensionTypeList"][0]), ["LS"])

    def test_csv_fixture_passes_stage1_validation(self):
        fixture = PROJECT_ROOT / "tests/fixtures/sellersprite_export_sample.csv"
        report = validator.validate_export(fixture)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["sample_asin"], "B0TEST0001")


if __name__ == "__main__":
    unittest.main()
