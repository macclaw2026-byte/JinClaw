import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-seo-geo-engine/scripts")
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from opportunity_registry import build_opportunity_registry
from technical_release_gate import evaluate_release_gate


class SeoGeoReleaseControlTests(unittest.TestCase):
    def test_opportunity_registry_assigns_expected_actions(self) -> None:
        backlog = [
            {"slug": "new-page", "title": "New Page", "topic_key": "pendant"},
            {"slug": "live-page", "title": "Live Page", "topic_key": "bathroom"},
            {"slug": "stale-page", "title": "Stale Page", "topic_key": "living-room"},
        ]
        notes_by_slug = {
            "live-page": {"status": "PUBLISHED", "_count": {"geoVariants": 1, "revisions": 2}, "updatedAt": "2026-04-01T00:00:00Z"},
            "stale-page": {"status": "PUBLISHED", "_count": {"geoVariants": 10, "revisions": 1}, "updatedAt": "2026-01-01T00:00:00Z"},
        }
        feedback_summary = {
            "slug_metrics": {
                "live-page": {"clicks": 0, "impressions": 120},
                "stale-page": {"clicks": 12, "impressions": 240},
            },
            "topic_metrics": {
                "pendant": {"queryImpressions": 30},
                "bathroom": {"queryImpressions": 80},
                "living-room": {"queryImpressions": 50},
            },
        }
        geo_targets = [{"state": "RI"}, {"state": "MA"}, {"state": "CT"}]
        registry = build_opportunity_registry(
            backlog=backlog,
            notes_by_slug=notes_by_slug,
            feedback_summary=feedback_summary,
            geo_targets=geo_targets,
        )
        by_slug = {row["slug"]: row for row in registry["items"]}
        self.assertEqual(by_slug["new-page"]["recommended_action"], "create")
        self.assertEqual(by_slug["live-page"]["recommended_action"], "refresh_ctr")
        self.assertIn(by_slug["stale-page"]["recommended_action"], {"expand", "refresh_content"})

    def test_note_release_gate_blocks_weak_payloads(self) -> None:
        config = {"technical_release_gate": {"min_sections": 4, "min_internal_links": 2, "max_seo_title_length": 80, "max_seo_description_length": 180}}
        weak = {
            "title": "Weak",
            "seoTitle": "",
            "seoDescription": "short",
            "quickAnswer": "",
            "sections": [{"heading": "Only", "body": "One"}],
            "internalLinks": [],
        }
        gate = evaluate_release_gate(weak, config, kind="note")
        self.assertFalse(gate["passed"])
        self.assertIn("seo_title_present", gate["blocking_items"])
        self.assertIn("internal_links_ok", gate["blocking_items"])

    def test_geo_release_gate_requires_location_and_content(self) -> None:
        config = {"technical_release_gate": {"min_sections": 3, "min_internal_links": 2, "max_seo_title_length": 80, "max_seo_description_length": 180}}
        strong = {
            "title": "Kitchen Island Pendant Spacing in Providence",
            "seoTitle": "Kitchen Island Pendant Spacing in Providence | Neosgo",
            "seoDescription": "Providence-focused pendant spacing guide for kitchen islands.",
            "quickAnswer": "In Providence, spacing should balance fixture width and breathing room.",
            "city": "Providence",
            "state": "RI",
            "geoLabel": "Providence, RI",
            "sections": [
                {"heading": "What works well in Providence", "body": "Providence projects reward careful proportion."},
                {"heading": "What to prioritize in Providence", "body": "In Providence, keep scale and finish in sync."},
                {"heading": "Common mistakes in Providence", "body": "Providence rooms can feel crowded if pendants are oversized."},
            ],
            "internalLinks": [
                {"label": "Browse the matching collection", "href": "/products?category=pendant-lights"},
                {"label": "See the Trade Program", "href": "/trade-program"},
            ],
        }
        gate = evaluate_release_gate(strong, config, kind="geo_variant")
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["blocking_items"], [])


if __name__ == "__main__":
    unittest.main()
