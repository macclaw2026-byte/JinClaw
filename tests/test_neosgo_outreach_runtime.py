import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
SCRIPT_PATH = ROOT / "projects/neosgo-marketing-suite/scripts/run_outreach_cycle.py"


def _load_outreach_module():
    spec = importlib.util.spec_from_file_location("neosgo_outreach_cycle_for_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class NeosgoOutreachRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_outreach_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_priority_regions_follow_project_config(self) -> None:
        config_path = self.tmp_path / "project-config.json"
        config_path.write_text(
            json.dumps({"project": {"priority_regions": ["MA", "NY", "CA"]}}),
            encoding="utf-8",
        )

        with patch.object(self.module, "PROJECT_CONFIG_PATH", config_path):
            self.assertEqual(self.module._priority_regions(), ["MA", "NY", "CA"])

    def test_candidate_supply_summary_counts_remaining_and_pending_batch(self) -> None:
        contacts_payload = {
            "items": [
                {
                    "company_name": "Fresh Lead",
                    "source_url": "fresh",
                    "geo": "MA / new_england",
                    "website": "https://fresh.example.com",
                    "email": "hello@fresh.example.com",
                    "email_validation_reason": "domain_match",
                    "website_fit_status": "approved",
                    "contact_form_detected": False,
                    "contact_form_signals": [],
                },
                {
                    "company_name": "Touched Lead",
                    "source_url": "touched",
                    "geo": "MA / new_england",
                    "website": "https://touched.example.com",
                    "email": "hello@touched.example.com",
                    "email_validation_reason": "domain_match",
                    "website_fit_status": "approved",
                    "contact_form_detected": False,
                    "contact_form_signals": [],
                },
                {
                    "company_name": "Pending Lead",
                    "source_url": "pending",
                    "geo": "MA / new_england",
                    "website": "https://pending.example.com",
                    "email": "",
                    "email_validation_reason": "pending_batch",
                    "website_fit_status": "pending_batch",
                    "contact_form_detected": False,
                    "contact_form_signals": [],
                },
                {
                    "company_name": "Outside Region",
                    "source_url": "outside",
                    "geo": "CA / west",
                    "website": "https://outside.example.com",
                    "email": "hello@outside.example.com",
                    "email_validation_reason": "domain_match",
                    "website_fit_status": "approved",
                    "contact_form_detected": False,
                    "contact_form_signals": [],
                },
            ]
        }
        state = {
            "targets": {
                "touched": {
                    "status": "email_sent_local_only",
                }
            }
        }

        with patch.object(self.module, "LEAD_REFILL_STATE_PATH", self.tmp_path / "lead-refill-state.json"):
            summary = self.module._candidate_supply_summary(
                state,
                contacts_payload=contacts_payload,
                priority_regions=["MA"],
            )

        self.assertEqual(summary["approved_total"], 2)
        self.assertEqual(summary["approved_usable_total"], 2)
        self.assertEqual(summary["approved_usable_remaining_total"], 1)
        self.assertEqual(summary["pending_batch_total"], 1)
        self.assertEqual(summary["status"], "ready")

    def test_yaml_to_json_uses_matching_cache_on_timeout(self) -> None:
        yaml_path = self.tmp_path / "content.yaml"
        yaml_path.write_text("sender_identity:\n  full_name: Test Sender\n", encoding="utf-8")
        cache_path = self.tmp_path / "campaign-content-cache.json"
        signature = self.module._file_signature(yaml_path)
        cached_payload = {"sender_identity": {"full_name": "Cached Sender"}}
        cache_path.write_text(
            json.dumps(
                {
                    "source": signature,
                    "payload": cached_payload,
                }
            ),
            encoding="utf-8",
        )

        with patch.object(self.module, "CONTENT_CACHE_PATH", cache_path):
            with patch.object(
                self.module.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd=["/usr/bin/ruby"], timeout=30),
            ):
                payload = self.module._yaml_to_json(yaml_path)

        self.assertEqual(payload, cached_payload)

    def test_replenishment_runs_enrichment_when_supply_is_empty(self) -> None:
        refill_path = self.tmp_path / "lead-refill-state.json"
        enrichment_script = self.tmp_path / "enrich_google_maps_website_contacts.py"
        enrichment_script.write_text("# test", encoding="utf-8")
        before = {
            "approved_usable_total": 2,
            "approved_usable_remaining_total": 0,
            "pending_batch_total": 12,
        }
        after = {
            "approved_usable_total": 5,
            "approved_usable_remaining_total": 3,
            "pending_batch_total": 6,
        }
        result = {
            "ok": True,
            "returncode": 0,
            "stdout": "{}",
            "stderr": "",
            "payload": {
                "checked_site_count": 40,
                "deferred_count": 6,
            },
        }

        with patch.object(self.module, "LEAD_REFILL_STATE_PATH", refill_path):
            with patch.object(self.module, "ENRICHMENT_SCRIPT", enrichment_script):
                with patch.object(self.module, "_candidate_supply_summary", side_effect=[before, after]):
                    with patch.object(self.module, "_run_json_subprocess", return_value=result):
                        event = self.module._maybe_replenish_candidate_supply({"targets": {}})

        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "lead_supply_replenished")
        self.assertEqual(event["newly_available_to_outreach"], 3)
        state = json.loads(refill_path.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["checked_sites"], 40)
        self.assertEqual(state["newly_available_to_outreach"], 3)


if __name__ == "__main__":
    unittest.main()
