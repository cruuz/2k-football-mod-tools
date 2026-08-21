"""Field Art UI must name stock endzones vs proved writable slots.

Package 6 was described as a **shared** endzone layer in the category blurb and
in ``docs/product/APF_FIELD_ART_STOCK_NFL_WALL.md``. Decoding it shows bespoke
per-team artwork -- two figures in wide-brimmed hats with bandoliers and
revolvers, a masked figure, a hitching rail -- structurally identical to the
other 117 packages (2048x512, DXT1, the same l0/l1 split). It is the package
whose writer was proved first, nothing more. The old wording told users that
editing it changed a common layer when it repaints one specific team's endzone,
which is the kind of error found only after someone ships a mod (davidhbui,
Beta 38).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mod_editor.apf_studio import field_art
from mod_editor.apf_studio.field_art import (
    ENDZONE_IDENTITY_NOTE,
    ENDZONE_LABELS,
    ENDZONE_MASK_CONTRACT,
    _NAME_CONTRACTS,
    endzone_team_labels,
)
from mod_editor.apf_studio.gui import CATEGORY_BLURBS, FIELD_ART_COVERED_TARGETS
from mod_editor.apf_studio.models import ApfCategory


WALL_DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/product/APF_FIELD_ART_STOCK_NFL_WALL.md"
)
_FIELD_EXTRA_TARGETS = (
    Path(__file__).resolve().parents[2]
    / "mod_editor"
    / "data"
    / "apf2k8_field_extra_targets.v1.json"
)
_WRITABLE_XENOS_FORMATS = frozenset({6, 18, 20})


class FieldArtStockLabelTests(unittest.TestCase):
    def test_inventory_contract_counts_stock_endzones(self) -> None:
        self.assertEqual(_NAME_CONTRACTS["endzone_l0"].count, 118)
        self.assertEqual(_NAME_CONTRACTS["endzone_l1"].count, 117)

    def test_writable_slots_keep_the_original_six_and_add_derived_families(self) -> None:
        names = {target.name for target in FIELD_ART_COVERED_TARGETS}
        # 6 core + 21 weave/dirt (fmt 6/18/20) + 194 extra format-18 endzones.
        self.assertGreaterEqual(len(FIELD_ART_COVERED_TARGETS), 6 + 21 + 194)
        for required in (
            "endzone_l0",
            "endzone_l1",
            "pc_field_goal",
            "Field_Pass_text",
            "Stride_number_field",
            "divots",
            "weave_jersey0",
            "dirtmap_helmet",
        ):
            self.assertIn(required, names)

    def test_category_blurb_names_stock_and_writable_bound(self) -> None:
        help_text = CATEGORY_BLURBS[ApfCategory.FIELD_ART]
        folded = help_text.casefold()
        # 118 is the inventory l0 count, not a writable-team claim.
        self.assertIn("118", help_text)
        self.assertIn("stock", folded)
        self.assertTrue(
            "six" in folded or "6" in help_text,
            help_text,
        )
        self.assertIn("format-18", folded)
        self.assertIn("format-59", folded)
        self.assertIn("browse-only", folded)
        self.assertNotIn("all 118 teams", folded)
        self.assertNotIn("every team", folded)


class OuterSixIsNotSharedTests(unittest.TestCase):
    """No surface may call package 6 a shared layer again."""

    def test_the_category_blurb_withdraws_the_shared_claim(self) -> None:
        blurb = CATEGORY_BLURBS[ApfCategory.FIELD_ART]
        self.assertNotIn("shared outer-6", blurb)
        self.assertIn("not a shared layer", blurb)
        self.assertIn("region mask", blurb.casefold())

    def test_writable_endzones_are_not_shared_layers(self) -> None:
        endzone_targets = [
            target
            for target in FIELD_ART_COVERED_TARGETS
            if str(target.name).startswith("endzone_")
        ]
        # 196 format-18 layers: every l0 plus the 78 format-18 l1 siblings.
        # 39 format-59 l1 layers stay out, so this is not all 235 inventory rows.
        self.assertEqual(len(endzone_targets), 196)
        self.assertEqual(
            sum(1 for target in endzone_targets if target.name == "endzone_l0"),
            118,
        )
        self.assertEqual(
            sum(1 for target in endzone_targets if target.name == "endzone_l1"),
            78,
        )
        package_six = [t for t in endzone_targets if t.entry_index == 6]
        self.assertEqual({t.name for t in package_six}, {"endzone_l0", "endzone_l1"})
        for target in endzone_targets:
            with self.subTest(key=target.key):
                self.assertIn("not a shared layer", target.note.casefold())

    def test_format_59_endzones_are_refused_and_copy_stays_honest(self) -> None:
        document = json.loads(_FIELD_EXTRA_TARGETS.read_text(encoding="utf-8"))
        fmt59 = [
            (int(row["entry_index"]), int(row["file_index"]))
            for row in document["endzones"]
            if int(row["format"]) == 59
        ]
        writable_extras = [
            (int(row["entry_index"]), int(row["file_index"]))
            for group in ("package_659", "endzones")
            for row in document[group]
            if int(row["format"]) in _WRITABLE_XENOS_FORMATS
        ]
        self.assertEqual(len(fmt59), 39)
        self.assertEqual(
            {row["name"] for row in document["endzones"] if int(row["format"]) == 59},
            {"endzone_l1"},
        )
        offered = {target.key for target in FIELD_ART_COVERED_TARGETS}
        for key in writable_extras:
            self.assertIn(key, offered)
        for key in fmt59:
            self.assertNotIn(key, offered)
        self.assertNotIn((78, 1), offered)

    def test_the_wall_document_records_the_correction(self) -> None:
        text = WALL_DOC.read_text(encoding="utf-8")
        self.assertIn("outer 6 is not a shared layer", text.casefold())
        self.assertIn("region masks, not artwork", text.casefold())
        self.assertNotIn("shared endzone layers outer 6", text)


class EndzoneLabelTableTests(unittest.TestCase):
    """A package nobody identified stays an index, never a guess."""

    def test_every_label_is_a_distinct_real_package_index(self) -> None:
        labels = endzone_team_labels()
        self.assertGreaterEqual(len(labels), 31)
        self.assertLessEqual(len(labels), 118)
        for outer, team in labels.items():
            with self.subTest(outer=outer):
                self.assertIsInstance(outer, int)
                self.assertGreaterEqual(outer, 0)
                self.assertLess(outer, 1543)
                self.assertTrue(team.strip())

    def test_the_verified_identifications_are_the_ones_that_were_decoded(self) -> None:
        labels = endzone_team_labels()
        for outer, team in (
            (1533, "Redcoats"),
            (1139, "Pharaohs"),
            (1258, "Biohazard"),
            (753, "Gorillas"),
            (802, "A's"),
            (1360, "Z's"),
        ):
            with self.subTest(outer=outer):
                self.assertEqual(labels[outer], team)

    def test_package_six_is_not_labelled_shared(self) -> None:
        self.assertNotIn("shared", endzone_team_labels().get(6, "").casefold())

    def test_every_row_credits_who_identified_it(self) -> None:
        document = json.loads(ENDZONE_LABELS.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], field_art.ENDZONE_LABELS_SCHEMA)
        for row in document["labels"]:
            with self.subTest(outer=row["outer_index"]):
                self.assertTrue(str(row["source"]).strip())
                self.assertIn(row["kind"], {"nickname", "alphabet"})


class EndzoneDiscoveryCopyTests(unittest.TestCase):
    """Say why search cannot work, rather than shipping a search that cannot."""

    def test_the_mask_contract_states_the_authoring_rules(self) -> None:
        contract = ENDZONE_MASK_CONTRACT.casefold()
        self.assertIn("region mask", contract)
        self.assertIn("anti-aliasing", contract)
        self.assertIn("dxt1", contract)

    def test_the_identity_note_explains_why_a_name_search_cannot_work(self) -> None:
        note = ENDZONE_IDENTITY_NOTE
        self.assertIn("Roster.ROS", note)
        self.assertIn("default.xex", note)
        self.assertIn("contact sheet", note.casefold())


if __name__ == "__main__":
    unittest.main()
