from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path("/Users/mac_claw/.openclaw/workspace/tools/bin/neosgo-seller-bulk-runner.py")
SPEC = importlib.util.spec_from_file_location("neosgo_seller_bulk_runner", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NeosgoSellerPricingTest(unittest.TestCase):
    def test_pick_import_template_price_prefers_platform_cost_derived_template_price(self) -> None:
        listing = {
            "basePrice": "63.8",
            "pricing": {
                "platformUnitCost": "58",
                "retailUnitPrice": "63.8",
            },
        }
        self.assertEqual(MODULE.pick_import_template_price(listing), 63.8)
        self.assertEqual(MODULE.pick_submission_price(listing), 88.8)

    def test_pick_submission_price_is_idempotent_for_already_marked_up_listing(self) -> None:
        listing = {
            "basePrice": "88.8",
            "price": "88.8",
            "pricing": {
                "platformUnitCost": "58",
                "retailUnitPrice": "88.8",
            },
        }
        self.assertEqual(MODULE.pick_import_template_price(listing), 63.8)
        self.assertEqual(MODULE.pick_submission_price(listing), 88.8)

    def test_pick_submission_price_falls_back_to_retail_price_when_platform_cost_missing(self) -> None:
        listing = {
            "pricing": {
                "retailUnitPrice": "71.39",
            },
        }
        self.assertEqual(MODULE.pick_import_template_price(listing), 71.39)
        self.assertEqual(MODULE.pick_submission_price(listing), 96.39)


if __name__ == "__main__":
    unittest.main()
