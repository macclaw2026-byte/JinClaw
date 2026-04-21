import importlib.util
import gzip
import sys
import unittest
from pathlib import Path


ROOT = Path("/Users/mac_claw/.openclaw/workspace")
SCRIPT_DIR = ROOT / "skills/prospect-data-engine/scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


capture_cycle = _load_module(SCRIPT_DIR / "run_google_maps_capture_cycle.py", "google_maps_capture_cycle_for_tests")
enrich_runtime = _load_module(SCRIPT_DIR / "enrich_google_maps_website_contacts.py", "google_maps_enrich_runtime_for_tests")


class GoogleMapsCaptureRuntimeTests(unittest.TestCase):
    def test_load_capture_lanes_uses_multi_lane_config(self) -> None:
        lanes = capture_cycle._load_capture_lanes(
            {
                "lanes": [
                    {
                        "lane_key": "interior_designer",
                        "keyword": "interior designer",
                        "query_family": "google_maps_interior_designer",
                        "account_type": "designer",
                        "persona_type": "founder",
                    },
                    {
                        "lane_key": "general_contractor",
                        "keyword": "general contractor",
                        "query_family": "google_maps_general_contractor",
                        "account_type": "contractor",
                        "persona_type": "founder",
                    },
                ]
            }
        )

        self.assertEqual(
            [lane["query_family"] for lane in lanes],
            ["google_maps_interior_designer", "google_maps_general_contractor"],
        )
        self.assertEqual(lanes[1]["account_type"], "contractor")

    def test_select_enrichment_batch_rotates_across_lanes_and_advances_cursor(self) -> None:
        ordered_items = [
            {"company_name": "A1", "source_url": "a1", "website": "https://a1.example.com", "query_family": "google_maps_interior_designer"},
            {"company_name": "A2", "source_url": "a2", "website": "https://a2.example.com", "query_family": "google_maps_interior_designer"},
            {"company_name": "B1", "source_url": "b1", "website": "https://b1.example.com", "query_family": "google_maps_general_contractor"},
            {"company_name": "B2", "source_url": "b2", "website": "https://b2.example.com", "query_family": "google_maps_general_contractor"},
        ]
        selected_keys, next_cursors, meta = enrich_runtime._select_enrichment_batch(
            ordered_items,
            {},
            {"lane_cursors": {"google_maps_interior_designer": 1, "google_maps_general_contractor": 0}},
            max_sites_per_run=2,
        )

        self.assertEqual(selected_keys, {"a2", "b1"})
        self.assertEqual(next_cursors["google_maps_interior_designer"], 0)
        self.assertEqual(next_cursors["google_maps_general_contractor"], 1)
        self.assertEqual(meta["lane_stats"]["google_maps_interior_designer"], 1)
        self.assertEqual(meta["lane_stats"]["google_maps_general_contractor"], 1)

    def test_contractor_website_fit_assessment_approves_general_contractor_site(self) -> None:
        status, reasons = enrich_runtime._website_fit_assessment(
            {
                "https://example.com": "<html><body>Our team is a licensed general contractor offering design-build renovation and custom home builder services.</body></html>"
            },
            account_type="contractor",
            query_family="google_maps_general_contractor",
        )

        self.assertEqual(status, "approved")
        self.assertTrue(reasons)

    def test_email_is_realish_rejects_placeholder_emails(self) -> None:
        self.assertEqual(
            enrich_runtime._email_is_realish("info@mysite.com", "bostondesignandinteriors.com"),
            (False, "blocked_placeholder_domain"),
        )
        self.assertEqual(
            enrich_runtime._email_is_realish("filler@godaddy.com", "ahouserefined.com"),
            (False, "blocked_placeholder_local"),
        )
        self.assertEqual(
            enrich_runtime._email_is_realish("yourname@example.com", "dwr.com"),
            (False, "blocked_placeholder_local"),
        )
        self.assertEqual(
            enrich_runtime._email_is_realish("hello@brandstudio.com", "brandstudio.com"),
            (True, "domain_match"),
        )

    def test_fetch_required_revisits_placeholder_email_even_with_contact_form(self) -> None:
        self.assertTrue(
            enrich_runtime._fetch_required(
                {
                    "email": "info@mysite.com",
                    "email_validation_reason": "domain_resolves",
                    "contact_form_detected": True,
                },
                "https://www.bostondesignandinteriors.com/",
            )
        )
        self.assertFalse(
            enrich_runtime._fetch_required(
                {
                    "email": "hello@brandstudio.com",
                    "email_validation_reason": "domain_match",
                    "contact_form_detected": True,
                },
                "https://www.brandstudio.com/",
            )
        )

    def test_decode_response_bytes_supports_gzip_html(self) -> None:
        raw = gzip.compress(b"<html><body>hello@brandstudio.com</body></html>")
        decoded = enrich_runtime._decode_response_bytes(raw, "gzip")
        self.assertEqual(decoded, b"<html><body>hello@brandstudio.com</body></html>")


if __name__ == "__main__":
    unittest.main()
