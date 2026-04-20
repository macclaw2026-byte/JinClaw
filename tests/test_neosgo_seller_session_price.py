from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/neosgo_seller_session_client.py")
SPEC = importlib.util.spec_from_file_location("neosgo_seller_session_client", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

RUN_PATH = Path("/Users/mac_claw/.openclaw/workspace/tools/openmoss/ops/run_neosgo_seller_reprice_resubmit_full.py")
RUN_SPEC = importlib.util.spec_from_file_location("run_neosgo_seller_reprice_resubmit_full", RUN_PATH)
assert RUN_SPEC and RUN_SPEC.loader
RUN_MODULE = importlib.util.module_from_spec(RUN_SPEC)
RUN_SPEC.loader.exec_module(RUN_MODULE)


class NeosgoSellerSessionPriceTest(unittest.TestCase):
    def test_default_reason_is_clear_sentence(self) -> None:
        self.assertIn("bulk import template price plus 25 USD", MODULE.DEFAULT_PRICE_CHANGE_REASON)
        self.assertGreater(len(MODULE.DEFAULT_PRICE_CHANGE_REASON.split()), 8)

    def test_active_approved_noneditable_listing_uses_session_patch_route(self) -> None:
        row = {
            "status": "APPROVED",
            "is_active": True,
            "editable_via_automation": False,
        }
        self.assertTrue(RUN_MODULE._should_use_seller_session_patch(row))

    def test_inactive_or_draft_listing_does_not_force_session_patch_route(self) -> None:
        self.assertFalse(RUN_MODULE._should_use_seller_session_patch({"status": "DRAFT", "is_active": False, "editable_via_automation": False}))
        self.assertFalse(RUN_MODULE._should_use_seller_session_patch({"status": "SUBMITTED", "is_active": True, "editable_via_automation": True}))


if __name__ == "__main__":
    unittest.main()
