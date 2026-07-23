"""Synthetic contract tests for the retail-free APF Field Art inventory."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest

from mod_editor.apf_studio.catalog import ApfCatalog
from mod_editor.apf_studio.field_art import (
    FIELD_ART_PACKAGE_COUNT,
    FIELD_ART_RECORD_COUNT,
    FieldArtInventoryError,
    FieldArtKind,
    build_field_art_inventory,
)
from mod_editor.apf_studio.models import ApfAsset, ApfCategory, ApfStatus


def _asset(
    outer_index: int,
    inner_index: int,
    name: str,
    type_name: str,
    asset_class: str,
) -> ApfAsset:
    return ApfAsset(
        asset_id=f"apf:outer:{outer_index}:inner:{inner_index}",
        outer_index=outer_index,
        inner_index=inner_index,
        name=name,
        type_name=type_name,
        asset_class=asset_class,
        category=ApfCategory.FIELD_ART,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=1,
        outer_size=1,
        part_count=1,
    )


def _synthetic_catalog() -> ApfCatalog:
    assets: list[ApfAsset] = []

    # 117 paired packages plus one l0-only package.
    for outer_index in range(118):
        assets.append(_asset(outer_index, 0, "endzone_l0", "TXTR", "texture"))
        if outer_index < 117:
            assets.append(_asset(outer_index, 1, "endzone_l1", "TXTR", "texture"))

    # Four package-local field/field_radiance pairs; only three have divots.
    for ordinal, outer_index in enumerate(range(200, 204)):
        assets.append(_asset(outer_index, 0, "field", "SCNE", "scene_model_package"))
        assets.append(_asset(outer_index, 1, "field_radiance", "TXTR", "texture"))
        if ordinal < 3:
            assets.append(_asset(outer_index, 2, "divots", "TXTR", "texture"))

    shared_outer = 300
    for inner_index, name in enumerate(
        (
            "divot_GrassRain",
            "divot_GrassSnow",
            "divot_GrassDry",
            "pc_field_goal",
            "Field_Pass_text",
            "Stride_number_field",
        )
    ):
        assets.append(_asset(shared_outer, inner_index, name, "TXTR", "texture"))
    for inner_index, name in enumerate(("divotb1", "field_pass01", "divota1"), 6):
        assets.append(
            _asset(shared_outer, inner_index, name, "SCNE", "scene_model_package")
        )

    assets.append(
        _asset(301, 0, "tc2_footballField", "SCNE", "scene_model_package")
    )
    assets.extend(
        (
            _asset(
                302,
                0,
                "there_is_a_penalty_onthe_field",
                "CurveAnim",
                "animation_curve",
            ),
            _asset(
                302,
                1,
                "penalty_onthe_field",
                "CurveAnim",
                "animation_curve",
            ),
        )
    )
    assert len(assets) == FIELD_ART_RECORD_COUNT
    return ApfCatalog(
        source_sha256="a" * 64,
        outer_count=1543,
        iff_count=1473,
        non_iff_count=70,
        inner_count=10_394,
        assets=tuple(assets),
        uniform_assets=(),
        capabilities=(),
        audio_selection_manifest=Path("synthetic-inner-selection.json"),
    )


class ApfFieldArtInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = _synthetic_catalog()

    def test_exact_semantic_and_package_totals(self) -> None:
        inventory = build_field_art_inventory(self.catalog)

        self.assertEqual(len(inventory.records), FIELD_ART_RECORD_COUNT)
        self.assertEqual(len(inventory.package_groups), FIELD_ART_PACKAGE_COUNT)
        self.assertEqual(len(inventory.semantic_groups), 7)
        self.assertEqual(
            dict(inventory.summary),
            {
                "semantic_records": 258,
                "semantic_groups": 7,
                "archive_packages": 125,
                "txtr_records": 248,
                "scne_records": 8,
                "curve_anim_records": 2,
                "editable_records": 0,
            },
        )
        self.assertEqual(
            {
                group.kind: len(group.records)
                for group in inventory.semantic_groups
            },
            {
                FieldArtKind.ENDZONE_TEXTURE: 235,
                FieldArtKind.FIELD_SCENE: 4,
                FieldArtKind.FIELD_RADIANCE: 4,
                FieldArtKind.DIVOT_WEATHER_TEXTURE: 6,
                FieldArtKind.PRACTICE_FIELD_OVERLAY: 3,
                FieldArtKind.PRACTICE_SCENE: 4,
                FieldArtKind.PENALTY_ANIMATION: 2,
            },
        )

    def test_endzone_pairing_and_package_ownership_are_explicit_but_bounded(self) -> None:
        inventory = build_field_art_inventory(self.catalog)
        endzones = inventory.semantic_group(FieldArtKind.ENDZONE_TEXTURE)
        paired = [
            group
            for group in inventory.package_groups
            if {record.name for record in group.records}
            == {"endzone_l0", "endzone_l1"}
        ]
        l0_only = [
            group
            for group in inventory.package_groups
            if tuple(record.name for record in group.records) == ("endzone_l0",)
        ]

        self.assertEqual(len(endzones.package_ids), 118)
        self.assertEqual(len(paired), 117)
        self.assertEqual(len(l0_only), 1)
        self.assertIn("co-location only", paired[0].ownership_note)
        for unproved_owner in ("team", "stadium", "field-material", "runtime"):
            self.assertIn(unproved_owner, paired[0].ownership_note)
        self.assertIn("not yet proved", endzones.author_note)

    def test_curve_rows_remain_visible_without_being_called_field_textures(self) -> None:
        inventory = build_field_art_inventory(self.catalog)
        penalties = inventory.semantic_group(FieldArtKind.PENALTY_ANIMATION)

        self.assertEqual(len(penalties.records), 2)
        self.assertEqual(
            {record.type_name for record in penalties.records}, {"CurveAnim"}
        )
        self.assertIn("not field textures", penalties.author_note)
        self.assertIn("universal catalog coverage", penalties.author_note)

    def test_records_groups_and_summary_are_immutable(self) -> None:
        inventory = build_field_art_inventory(self.catalog)
        with self.assertRaises(TypeError):
            inventory.summary["semantic_records"] = 0  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            inventory.records[0].name = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            inventory.semantic_groups[0].title = "changed"  # type: ignore[misc]

    def test_fails_closed_on_missing_unknown_or_reclassified_row(self) -> None:
        with self.assertRaisesRegex(FieldArtInventoryError, "exactly 258"):
            build_field_art_inventory(
                replace(self.catalog, assets=self.catalog.assets[:-1])
            )

        renamed = list(self.catalog.assets)
        renamed[0] = replace(renamed[0], name="mystery_endzone")
        with self.assertRaisesRegex(FieldArtInventoryError, "names changed"):
            build_field_art_inventory(replace(self.catalog, assets=tuple(renamed)))

        editable = list(self.catalog.assets)
        editable[0] = replace(editable[0], status=ApfStatus.EDITABLE)
        with self.assertRaisesRegex(FieldArtInventoryError, "status changed"):
            build_field_art_inventory(replace(self.catalog, assets=tuple(editable)))

    def test_fails_closed_when_package_relationships_drift(self) -> None:
        assets = list(self.catalog.assets)
        index = next(
            position
            for position, asset in enumerate(assets)
            if asset.name == "field_radiance"
        )
        original = assets[index]
        assets[index] = replace(
            original,
            asset_id=f"apf:outer:999:inner:{original.inner_index}",
            outer_index=999,
        )
        with self.assertRaisesRegex(FieldArtInventoryError, "relationships changed"):
            build_field_art_inventory(replace(self.catalog, assets=tuple(assets)))


if __name__ == "__main__":
    unittest.main()
