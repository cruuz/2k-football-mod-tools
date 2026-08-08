"""Field Art UI must name stock NFL endzones vs proved writable slots."""

from __future__ import annotations

import unittest
from pathlib import Path

from mod_editor.apf_studio.field_art import _NAME_CONTRACTS
from mod_editor.apf_studio.gui import CATEGORY_BLURBS, FIELD_ART_COVERED_TARGETS
from mod_editor.apf_studio.models import ApfCategory


class FieldArtStockLabelTests(unittest.TestCase):
    def test_inventory_contract_counts_stock_endzones(self) -> None:
        self.assertEqual(_NAME_CONTRACTS["endzone_l0"].count, 118)
        self.assertEqual(_NAME_CONTRACTS["endzone_l1"].count, 117)

    def test_writable_slots_are_six_proved_bases(self) -> None:
        self.assertEqual(len(FIELD_ART_COVERED_TARGETS), 6)

    def test_category_blurb_names_stock_nfl_and_writable_bound(self) -> None:
        help_text = CATEGORY_BLURBS[ApfCategory.FIELD_ART]
        self.assertIn("118", help_text)
        self.assertIn("stock", help_text.casefold())
        self.assertTrue(
            "six" in help_text.casefold() or "6" in help_text,
            help_text,
        )


if __name__ == "__main__":
    unittest.main()
