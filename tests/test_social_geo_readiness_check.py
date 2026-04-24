import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-seo-geo-engine/scripts/social_geo_readiness_check.py")
SPEC = importlib.util.spec_from_file_location("social_geo_readiness_check", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class SocialGeoReadinessCheckTest(unittest.TestCase):
    def test_build_report_marks_missing_required_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            required_path = tmpdir / "brand-facts-master.json"
            optional_path = tmpdir / "review-targets.json"
            config = {
                "program": {"name": "test"},
                "operator_inputs": [
                    {
                        "key": "brand_facts_master",
                        "required": True,
                        "path": str(required_path),
                        "description": "required",
                    },
                    {
                        "key": "review_monitoring_targets",
                        "required": False,
                        "path": str(optional_path),
                        "description": "optional",
                    },
                ],
                "channels": [
                    {
                        "key": "pinterest",
                        "required_inputs": ["brand_facts_master"],
                        "role": "test",
                    }
                ],
            }
            report = MODULE.build_readiness_report(config)
            self.assertTrue(report["blocked"])
            self.assertIn("brand_facts_master", report["required_missing_inputs"])
            self.assertIn("pinterest", report["blocked_channels"])

    def test_build_report_marks_channel_ready_when_inputs_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            required_path = tmpdir / "brand-facts-master.json"
            required_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
            config = {
                "program": {"name": "test"},
                "operator_inputs": [
                    {
                        "key": "brand_facts_master",
                        "required": True,
                        "path": str(required_path),
                        "description": "required",
                    }
                ],
                "channels": [
                    {
                        "key": "pinterest",
                        "required_inputs": ["brand_facts_master"],
                        "role": "test",
                    }
                ],
            }
            report = MODULE.build_readiness_report(config)
            channel = report["channels"][0]
            self.assertTrue(channel["ready"])
            self.assertEqual(channel["missing_inputs"], [])


if __name__ == "__main__":
    unittest.main()
