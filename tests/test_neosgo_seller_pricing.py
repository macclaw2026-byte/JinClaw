from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path("/Users/mac_claw/.openclaw/workspace/tools/bin/neosgo-seller-bulk-runner.py")
SPEC = importlib.util.spec_from_file_location("neosgo_seller_bulk_runner", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NeosgoSellerPricingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self._old_baseline_path = MODULE.PRICE_BASELINE_PATH
        self._old_reports_dir = MODULE.PRICE_BASELINE_REPORTS_DIR
        self._old_cache = MODULE._PRICE_BASELINE_CACHE
        MODULE.PRICE_BASELINE_PATH = Path(self._tempdir.name) / "neosgo-seller-price-baselines.json"
        MODULE.PRICE_BASELINE_REPORTS_DIR = Path(self._tempdir.name) / "reports"
        MODULE.PRICE_BASELINE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        MODULE._PRICE_BASELINE_CACHE = None

    def tearDown(self) -> None:
        MODULE.PRICE_BASELINE_PATH = self._old_baseline_path
        MODULE.PRICE_BASELINE_REPORTS_DIR = self._old_reports_dir
        MODULE._PRICE_BASELINE_CACHE = self._old_cache
        self._tempdir.cleanup()

    def test_pick_submission_price_uses_candidate_price_as_single_truth(self) -> None:
        listing = {
            "source": "GIGA",
            "status": "SUBMITTED",
            "originalPlatform": "Gigacloud",
            "originalPrice": "139",
            "basePrice": "164",
            "price": "164",
            "pricing": {
                "platformUnitCost": "164",
                "retailUnitPrice": None,
            },
        }
        candidate = {
            "sku": "W2287P184402",
            "price": 99,
        }
        self.assertEqual(
            MODULE.pick_import_template_price(listing, product_id="p1", sku="W2287P184402", candidate=candidate),
            99.0,
        )
        self.assertEqual(
            MODULE.pick_submission_price(listing, product_id="p1", sku="W2287P184402", candidate=candidate),
            124.0,
        )

    def test_candidate_truth_overrides_stale_untrusted_baseline(self) -> None:
        baselines = {
            "by_product_id": {
                "p2": {
                    "submission_price_usd": 164.0,
                    "source": "live_listing_original_price",
                }
            },
            "by_sku": {
                "W2287P184402": {
                    "submission_price_usd": 164.0,
                    "source": "live_listing_original_price",
                }
            },
        }
        MODULE.save_price_baselines(baselines)
        listing = {
            "source": "GIGA",
            "status": "SUBMITTED",
            "originalPlatform": "Gigacloud",
        }
        candidate = {
            "sku": "W2287P184402",
            "price": 99,
        }
        submission_price, record = MODULE.resolve_submission_price(
            listing,
            product_id="p2",
            sku="W2287P184402",
            candidate=candidate,
        )
        self.assertEqual(submission_price, 124.0)
        self.assertEqual(record["template_price_usd"], 99.0)
        self.assertTrue(record["source"].startswith(MODULE.TRUSTED_CANDIDATE_BASELINE_SOURCE))

    def test_pick_submission_price_uses_trusted_cached_candidate_baseline_when_candidate_not_present(self) -> None:
        MODULE.save_price_baselines(
            {
                "by_product_id": {
                    "p3": {
                        "template_price_usd": 99.0,
                        "submission_price_usd": 124.0,
                        "source": f"{MODULE.TRUSTED_CANDIDATE_BASELINE_SOURCE}:cached",
                    }
                },
                "by_sku": {},
            }
        )
        listing = {
            "source": "GIGA",
            "status": "APPROVED",
            "originalPlatform": "Gigacloud",
            "basePrice": "164",
        }
        self.assertEqual(MODULE.pick_submission_price(listing, product_id="p3", sku="s3"), 124.0)

    def test_pick_submission_price_blocks_giga_listing_when_candidate_price_missing(self) -> None:
        listing = {
            "source": "GIGA",
            "status": "SUBMITTED",
            "originalPlatform": "Gigacloud",
            "pricing": {},
        }
        with self.assertRaisesRegex(ValueError, "missing_candidate_template_price"):
            MODULE.pick_submission_price(
                listing,
                product_id="p4",
                sku="s4",
                candidate={"sku": "s4"},
            )

    def test_non_giga_listing_can_still_use_live_fallback(self) -> None:
        listing = {
            "status": "SUBMITTED",
            "editableViaAutomation": True,
            "originalPrice": "45.4",
            "pricing": {},
        }
        self.assertEqual(MODULE.pick_submission_price(listing, product_id="p5", sku="s5"), 70.4)


if __name__ == "__main__":
    unittest.main()
