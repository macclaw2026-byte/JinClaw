import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path("/Users/mac_claw/.openclaw/workspace/skills/prospect-data-engine/scripts")
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from google_maps_capture_core import (
    build_keyword_queries,
    derive_query_family,
    discovery_quality_summary,
    enrichment_quality_summary,
    extract_candidate_links,
)


class GoogleMapsCaptureCoreTests(unittest.TestCase):
    def test_build_keyword_queries_includes_templates_without_duplicates(self) -> None:
        queries = build_keyword_queries(
            keyword="lighting showroom",
            state_code="RI",
            state_name="Rhode Island",
            priority_cities=["Providence RI"],
            counties=["Providence County"],
            base_queries=["lighting showroom in Rhode Island", "lighting showroom in Providence RI"],
            templates=[
                "{keyword} in {priority_city}",
                "{keyword} in {county} {state_code}",
            ],
        )
        self.assertIn("lighting showroom in Rhode Island", queries)
        self.assertIn("lighting showroom in Providence RI", queries)
        self.assertIn("lighting showroom in Providence County RI", queries)
        self.assertEqual(len(queries), len(set(queries)))

    def test_extract_candidate_links_prioritizes_contact_like_pages(self) -> None:
        html = """
        <a href="/products">Products</a>
        <a href="/about">About</a>
        <a href="/contact">Contact</a>
        <a href="/team">Team</a>
        """
        links = extract_candidate_links("https://example.com", html, limit=3, extra_hints=["contact"])
        self.assertEqual(links[0], "https://example.com/contact")
        self.assertIn("https://example.com/about", links)
        self.assertIn("https://example.com/team", links)

    def test_quality_summaries_surface_route_and_validation_breakdown(self) -> None:
        discovery = discovery_quality_summary(
            [
                {
                    "generated_from_provider": "google_maps_playwright_browser",
                    "geo": "RI / new_england",
                    "website": "https://studio.example.com",
                    "phone": "(401) 555-1212",
                    "formatted_address": "Providence, RI",
                },
                {
                    "generated_from_provider": "google_maps_markdown_proxy",
                    "geo": "MA / new_england",
                    "website": "",
                    "phone": "",
                    "formatted_address": "",
                },
            ],
            [
                {"ok": True, "route": "playwright_browser", "fallback_used": False},
                {"ok": True, "route": "markdown_proxy", "fallback_used": True},
            ],
        )
        self.assertEqual(discovery["fallback_query_count"], 1)
        self.assertEqual(discovery["provider_counts"]["google_maps_playwright_browser"], 1)
        self.assertEqual(discovery["state_counts"]["RI"], 1)

        enrichment = enrichment_quality_summary(
            [
                {
                    "email": "hello@example.com",
                    "email_validation_reason": "domain_match",
                    "website_fit_status": "approved",
                    "reachability_status": "form_and_email_available",
                    "contact_form_detected": True,
                },
                {
                    "email": "",
                    "email_validation_reason": "no_valid_email_after_validation",
                    "website_fit_status": "review",
                    "reachability_status": "form_available",
                    "contact_form_detected": True,
                },
            ],
            checked_sites=2,
            deferred_count=1,
        )
        self.assertEqual(enrichment["validated_email_count"], 1)
        self.assertEqual(enrichment["contact_form_detected_count"], 2)
        self.assertEqual(enrichment["email_validation_reason_counts"]["domain_match"], 1)

    def test_derive_query_family_normalizes_keyword(self) -> None:
        self.assertEqual(derive_query_family("Interior Designer"), "google_maps_interior_designer")
        self.assertEqual(derive_query_family("Lighting Showroom", "custom_family"), "custom_family")


if __name__ == "__main__":
    unittest.main()
