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

    def test_pick_import_template_price_seeds_from_fresh_listing_fields(self) -> None:
        listing = {
            "basePrice": "63.8",
            "pricing": {
                "platformUnitCost": "58",
                "retailUnitPrice": "63.8",
            },
        }
        self.assertEqual(MODULE.pick_import_template_price(listing, product_id="p1", sku="s1"), 63.8)
        self.assertEqual(MODULE.pick_submission_price(listing, product_id="p1", sku="s1"), 88.8)

    def test_pick_submission_price_is_idempotent_for_already_marked_up_listing(self) -> None:
        seeded_listing = {
            "basePrice": "63.8",
            "pricing": {
                "platformUnitCost": "58",
                "retailUnitPrice": "63.8",
            },
        }
        drifted_listing = {
            "basePrice": "88.8",
            "price": "88.8",
            "pricing": {
                "platformUnitCost": "58",
                "retailUnitPrice": "88.8",
            },
        }
        self.assertEqual(MODULE.pick_submission_price(seeded_listing, product_id="p2", sku="s2"), 88.8)
        self.assertEqual(MODULE.pick_import_template_price(drifted_listing, product_id="p2", sku="s2"), 63.8)
        self.assertEqual(MODULE.pick_submission_price(drifted_listing, product_id="p2", sku="s2"), 88.8)

    def test_pick_submission_price_prefers_active_platform_cost_for_noneditable_listing_without_history(self) -> None:
        listing = {
            "status": "APPROVED",
            "isActive": True,
            "editableViaAutomation": False,
            "pricing": {
                "platformUnitCost": "64",
                "retailUnitPrice": "70.4",
            },
            "basePrice": "95.4",
            "price": "95.4",
        }
        self.assertEqual(
            MODULE.pick_submission_price(listing, product_id="p3", sku="s3", prefer_active_noneditable=True),
            64.0,
        )

    def test_pick_submission_price_blocks_when_no_live_seed_exists(self) -> None:
        listing = {"pricing": {}}
        with self.assertRaisesRegex(ValueError, "missing_submission_price_baseline"):
            MODULE.pick_submission_price(listing, product_id="p4", sku="s4")


if __name__ == "__main__":
    unittest.main()
