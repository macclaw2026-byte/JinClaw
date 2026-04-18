from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path("/Users/mac_claw/.openclaw/workspace/skills/prospect-data-engine/scripts/backfill_google_maps_missing_fields.py")
MODULE_PARENT = str(MODULE_PATH.parent)
if MODULE_PARENT not in sys.path:
    sys.path.insert(0, MODULE_PARENT)
SPEC = importlib.util.spec_from_file_location("backfill_google_maps_missing_fields", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GoogleMapsMissingFieldBackfillTest(unittest.TestCase):
    def test_extract_place_detail_prefers_business_link_and_phone(self) -> None:
        detail = MODULE._extract_place_detail(
            {
                "body": "Abbott & Son Construction Add website Phone: (603) 817-0374",
                "links": [
                    {
                        "href": "https://support.google.com/local-listings",
                        "text": "About this data",
                        "aria": "About this data",
                        "dataItemId": "",
                    },
                    {
                        "href": "https://example-construction.com/",
                        "text": "Website",
                        "aria": "Website",
                        "dataItemId": "authority",
                    },
                    {
                        "href": "tel:+16038170374",
                        "text": "",
                        "aria": "Call phone number",
                        "dataItemId": "",
                    },
                ],
                "buttons": [],
            }
        )
        self.assertEqual(detail["website"], "https://example-construction.com/")
        self.assertEqual(detail["phone"], "(603) 817-0374")
        self.assertTrue(detail["maps_missing_website_prompt"])

    def test_merge_place_detail_only_fills_missing_fields(self) -> None:
        item = {
            "company_name": "Sample Co",
            "website": "",
            "website_root_domain": "",
            "phone": "",
            "signals": ["google_maps_search"],
        }
        merged, changed = MODULE._merge_place_detail(
            item,
            {
                "website": "https://sampleco.com/",
                "phone": "(401) 555-1234",
                "maps_missing_website_prompt": False,
            },
        )
        self.assertEqual(set(changed), {"website", "phone"})
        self.assertEqual(merged["website"], "https://sampleco.com/")
        self.assertEqual(merged["website_root_domain"], "sampleco.com")
        self.assertEqual(merged["phone"], "(401) 555-1234")
        self.assertIn("google_maps_targeted_place_backfill", merged["signals"])

    def test_merge_search_website_records_source_and_evidence(self) -> None:
        item = {
            "company_name": "Abbott & Son Construction",
            "website": "",
            "website_root_domain": "",
            "signals": ["google_maps_search", "google_maps_prompt_add_website"],
        }
        merged, changed = MODULE._merge_search_website(
            item,
            {
                "website": "https://www.abbottandsonconstruction.com/",
                "provider": "duckduckgo",
                "query": "\"Abbott & Son Construction\" NH official website",
                "score": 8.4,
                "evidence": ["phone_match", "full_name_match", "host_overlap:abbott"],
            },
        )
        self.assertEqual(changed, ["website"])
        self.assertEqual(merged["website"], "https://www.abbottandsonconstruction.com/")
        self.assertEqual(merged["website_root_domain"], "abbottandsonconstruction.com")
        self.assertEqual(merged["website_source"], "external_search_fallback")
        self.assertEqual(merged["website_source_provider"], "duckduckgo")
        self.assertAlmostEqual(float(merged["website_search_confidence"]), 8.4)
        self.assertIn("external_search_website_backfill", merged["signals"])
        self.assertIn("external_search_provider_duckduckgo", merged["signals"])

    def test_search_match_confidence_requires_strong_evidence(self) -> None:
        self.assertTrue(MODULE._is_search_match_confident(6.2, ["full_name_match", "token_hits:abbott"]))
        self.assertTrue(MODULE._is_search_match_confident(6.1, ["host_overlap:abbott", "token_hits:abbott,son"]))
        self.assertFalse(MODULE._is_search_match_confident(4.9, ["token_hits:design"]))
        self.assertFalse(MODULE._is_search_match_confident(6.0, ["account_type_match"]))


if __name__ == "__main__":
    unittest.main()
