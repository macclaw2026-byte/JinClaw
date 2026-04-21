import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
SCRIPT_PATH = ROOT / "projects/neosgo-marketing-suite/scripts/run_outreach_cycle.py"
SUMMARY_SCRIPT_PATH = ROOT / "projects/neosgo-marketing-suite/scripts/send_outreach_progress_telegram.py"


def _load_outreach_module():
    spec = importlib.util.spec_from_file_location("neosgo_outreach_cycle_for_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_outreach_summary_module():
    spec = importlib.util.spec_from_file_location("neosgo_outreach_summary_for_test", SUMMARY_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class NeosgoOutreachRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_outreach_module()
        self.summary_module = _load_outreach_summary_module()
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

    def test_load_candidates_interleaves_sources(self) -> None:
        contacts_path = self.tmp_path / "contacts.json"
        contacts_path.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "company_name": "Designer One",
                            "source_url": "designer-1",
                            "geo": "MA / new_england",
                            "website": "https://designer1.example.com",
                            "email": "hi@designer1.example.com",
                            "email_validation_reason": "domain_match",
                            "website_fit_status": "approved",
                            "contact_form_detected": False,
                            "contact_form_signals": [],
                            "query_family": "google_maps_interior_designer",
                            "account_type": "designer",
                            "source_family": "google_maps_places",
                        },
                        {
                            "company_name": "Designer Two",
                            "source_url": "designer-2",
                            "geo": "MA / new_england",
                            "website": "https://designer2.example.com",
                            "email": "hi@designer2.example.com",
                            "email_validation_reason": "domain_match",
                            "website_fit_status": "approved",
                            "contact_form_detected": False,
                            "contact_form_signals": [],
                            "query_family": "google_maps_interior_designer",
                            "account_type": "designer",
                            "source_family": "google_maps_places",
                        },
                        {
                            "company_name": "Contractor One",
                            "source_url": "contractor-1",
                            "geo": "MA / new_england",
                            "website": "https://contractor1.example.com",
                            "email": "hi@contractor1.example.com",
                            "email_validation_reason": "domain_match",
                            "website_fit_status": "approved",
                            "contact_form_detected": False,
                            "contact_form_signals": [],
                            "query_family": "google_maps_general_contractor",
                            "account_type": "contractor",
                            "source_family": "google_maps_places",
                        },
                        {
                            "company_name": "Contractor Two",
                            "source_url": "contractor-2",
                            "geo": "MA / new_england",
                            "website": "https://contractor2.example.com",
                            "email": "hi@contractor2.example.com",
                            "email_validation_reason": "domain_match",
                            "website_fit_status": "approved",
                            "contact_form_detected": False,
                            "contact_form_signals": [],
                            "query_family": "google_maps_general_contractor",
                            "account_type": "contractor",
                            "source_family": "google_maps_places",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        config_path = self.tmp_path / "project-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "project": {"priority_regions": ["MA"]},
                    "prospect_data_engine": {
                        "google_maps_capture": {
                            "lanes": [
                                {"query_family": "google_maps_interior_designer"},
                                {"query_family": "google_maps_general_contractor"},
                            ]
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        with patch.object(self.module, "CONTACTS_PATH", contacts_path), patch.object(self.module, "PROJECT_CONFIG_PATH", config_path):
            candidates = self.module._load_candidates()

        self.assertEqual(
            [item["company_name"] for item in candidates[:4]],
            ["Designer One", "Contractor One", "Designer Two", "Contractor Two"],
        )

    def test_notify_success_respects_disabled_success_policy(self) -> None:
        with patch.object(self.module, "_send_telegram") as send_telegram:
            result = self.module._notify_success(
                "8528973600",
                {"company_name": "Quiet Lead", "geo": "MA / new_england"},
                "contact_form",
                {"reason": "submitted"},
                notification_policy={
                    "notify_on_contact_form_submitted": False,
                    "notify_on_email_sent": False,
                },
            )

        self.assertIsNone(result)
        send_telegram.assert_not_called()

    def test_form_failure_without_email_fallback_notifies_immediately(self) -> None:
        form_result = {"ok": False, "reason": "submission_failed", "errors": ["missing token"]}
        with patch.object(self.module, "_email_is_usable", return_value=False):
            with patch.object(self.module, "_is_retryable_form_result", return_value=False):
                with patch.object(
                    self.module,
                    "_notify_failure",
                    return_value={"returncode": 0, "stdout": "sent"},
                ) as notify_failure:
                    target, event, telegram = self.module._email_fallback_after_form_failure(
                        item={
                            "company_name": "Blocked Lead",
                            "website": "https://blocked.example.com",
                        },
                        state={"targets": {}},
                        content={},
                        adapters={},
                        chat_id="8528973600",
                        no_telegram=False,
                        notification_policy={"notify_on_failure_immediately": True},
                        form_result=form_result,
                    )

        self.assertEqual(target["status"], "contact_form_failed")
        self.assertEqual(event["type"], "contact_form_failed")
        self.assertEqual(telegram, {"returncode": 0, "stdout": "sent"})
        notify_failure.assert_called_once()

    def test_retryable_form_result_prefers_email_without_manual_review_telegram(self) -> None:
        form_result = {"ok": False, "reason": "unknown_result", "errors": []}
        with patch.object(self.module, "_email_is_usable", return_value=True):
            with patch.object(self.module, "_email_send_allowed", return_value=False):
                with patch.object(self.module, "_is_retryable_form_result", return_value=True):
                    with patch.object(self.module, "_notify_manual_review_required") as notify_manual_review_required:
                        target, event, telegram = self.module._email_fallback_after_form_failure(
                            item={
                                "company_name": "Gray Lead",
                                "website": "https://gray.example.com",
                                "email": "hello@gray.example.com",
                            },
                            state={"targets": {}},
                            content={"delivery_rules": {"min_minutes_between_emails": 5}},
                            adapters={},
                            chat_id="8528973600",
                            no_telegram=False,
                            notification_policy={"notify_on_failure_immediately": True},
                            form_result=form_result,
                        )

        self.assertEqual(target["status"], "ready_for_email")
        self.assertEqual(target["force_channel"], "email")
        self.assertEqual(event["type"], "ready_for_email")
        self.assertIsNone(telegram)
        notify_manual_review_required.assert_not_called()

    def test_refresh_target_routing_reroutes_retryable_failures_to_email_when_email_exists(self) -> None:
        state = {
            "targets": {
                "lead-1": {
                    "company_name": "Retry Lead",
                    "status": "contact_form_failed",
                    "website": "https://retry.example.com",
                    "email": "hi@retry.example.com",
                    "contact_form_result": {"reason": "unknown_result", "errors": []},
                }
            }
        }
        with patch.object(self.module, "_email_is_usable", return_value=True):
            with patch.object(self.module, "_is_retryable_form_result", return_value=True):
                events = self.module._refresh_target_routing_from_results(state, {})

        self.assertEqual(state["targets"]["lead-1"]["status"], "ready_for_email")
        self.assertEqual(state["targets"]["lead-1"]["force_channel"], "email")
        self.assertEqual(events[0]["type"], "target_rerouted_for_email")

    def test_summary_script_skips_when_summary_notifications_disabled(self) -> None:
        summary_path = self.tmp_path / "latest-summary.json"
        summary_path.write_text(
            json.dumps({"generated_at": "2026-04-21T12:00:00Z", "total_touched": 1}, ensure_ascii=False),
            encoding="utf-8",
        )
        state_path = self.tmp_path / "telegram-summary-state.json"
        state_path.write_text("{}", encoding="utf-8")

        with patch.object(self.summary_module, "LATEST_SUMMARY_PATH", summary_path):
            with patch.object(self.summary_module, "STATE_PATH", state_path):
                with patch.object(
                    self.summary_module,
                    "_telegram_notification_policy",
                    return_value={"notify_on_campaign_summary": False},
                ):
                    with patch.object(self.summary_module, "_send") as send_message:
                        with patch.object(self.summary_module, "DEFAULT_CHAT", "8528973600"):
                            with patch("sys.argv", ["send_outreach_progress_telegram.py"]):
                                rc = self.summary_module.main()

        self.assertEqual(rc, 0)
        send_message.assert_not_called()

    def test_summary_policy_override_disables_summary_even_if_yaml_enabled(self) -> None:
        override_path = self.tmp_path / "operator-notification-policy.json"
        override_path.write_text(
            json.dumps({"notify_on_campaign_summary": False}, ensure_ascii=False),
            encoding="utf-8",
        )

        with patch.object(
            self.summary_module,
            "_yaml_to_json",
            return_value={"telegram_notifications": {"notify_on_campaign_summary": True}},
        ):
            with patch.object(self.summary_module, "NOTIFICATION_POLICY_OVERRIDE_PATH", override_path):
                policy = self.summary_module._telegram_notification_policy()

        self.assertFalse(policy["notify_on_campaign_summary"])

    def test_candidate_supply_summary_includes_source_summaries(self) -> None:
        contacts_payload = {
            "items": [
                {
                    "company_name": "Designer Fresh",
                    "source_url": "designer-fresh",
                    "geo": "MA / new_england",
                    "website": "https://designer.example.com",
                    "email": "hello@designer.example.com",
                    "email_validation_reason": "domain_match",
                    "website_fit_status": "approved",
                    "contact_form_detected": False,
                    "contact_form_signals": [],
                    "query_family": "google_maps_interior_designer",
                    "account_type": "designer",
                },
                {
                    "company_name": "Contractor Pending",
                    "source_url": "contractor-pending",
                    "geo": "MA / new_england",
                    "website": "https://contractor.example.com",
                    "email": "",
                    "email_validation_reason": "pending_batch",
                    "website_fit_status": "pending_batch",
                    "contact_form_detected": False,
                    "contact_form_signals": [],
                    "query_family": "google_maps_general_contractor",
                    "account_type": "contractor",
                },
            ]
        }

        with patch.object(self.module, "LEAD_REFILL_STATE_PATH", self.tmp_path / "lead-refill-state.json"):
            summary = self.module._candidate_supply_summary(
                {"targets": {}},
                contacts_payload=contacts_payload,
                priority_regions=["MA"],
            )

        self.assertIn("google_maps_interior_designer", summary["source_summaries"])
        self.assertIn("google_maps_general_contractor", summary["source_summaries"])
        self.assertEqual(summary["source_summaries"]["google_maps_interior_designer"]["approved_total"], 1)
        self.assertEqual(summary["source_summaries"]["google_maps_general_contractor"]["pending_batch_total"], 1)


if __name__ == "__main__":
    unittest.main()
