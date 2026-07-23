"""Retail-free tests for the Phase 2 visual catalog and PNG boundary."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from PIL import Image

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_extended_visual_catalog import (
    ExtendedVisualCatalogError,
    Nfl2k5ExtendedVisualCatalog,
    Nfl2k5ProductVisualCatalog,
    VisualCatalogExpectations,
    VisualReportPaths,
    VisualWriterRoute,
)
from mod_editor.core.nfl2k5_extended_visual_io import (
    Nfl2k5ExtendedVisualIO,
    ORIGINAL_SCHEMA,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _png(path: Path, size: tuple[int, int], *, alpha: int = 255) -> bytes:
    image = Image.new("RGBA", size, (21, 72, 149, alpha))
    image.save(path, format="PNG", interlace=False)
    return path.read_bytes()


class SyntheticReports:
    expectations = VisualCatalogExpectations(
        portrait_count=2,
        face_selector_count=1,
        face_resource_count=3,
        field_package_count=1,
        field_texture_count=2,
        scorebug_count=3,
    )

    def __init__(self, root: Path) -> None:
        self.paths = VisualReportPaths(
            portraits=root / "portraits.json",
            live_faces=root / "faces.json",
            field_art=root / "field.json",
            scorebug=root / "scorebug.json",
        )
        _write_json(self.paths.portraits, {
            "schema": "nfl2k5_player_portrait_compatibility/v1",
            "summary": {"numeric_portrait_count": 2},
            "targets": [
                {"name": "0007", "portrait_id": 7, "selector": "portrait:0007"},
                {"name": "0042", "portrait_id": 42, "selector": "portrait:0042"},
            ],
            "roster_selector_mapping": [
                {
                    "first_name": "Test",
                    "last_name": "Quarterback",
                    "portrait_present": True,
                    "portrait_resource_name": "0042",
                    "team_names": "Synthetic City",
                },
            ],
        })
        _write_json(self.paths.live_faces, {
            "schema": "nfl2k5_live_face_texture_compatibility/v1",
            "summary": {"selector_count": 1, "texture_resource_count": 3},
            "resources": [
                {
                    "face_id": "0042",
                    "family": family,
                    "fixed_span_png_importer_compatible": True,
                    "height": 256,
                    "resource_name": f"{family}0042",
                    "width": 256,
                }
                for family in "fhn"
            ],
        })
        _write_json(self.paths.field_art, {
            "schema": "nfl2k5_create_team_field_art_inventory/v1",
            "summary": {"package_count": 1, "texture_count": 2},
            "textures": [
                {
                    "format_name": "P8",
                    "height": 256,
                    "logo_code": 50,
                    "name": "center_logo",
                    "selector": "50:D:center_logo",
                    "weather_suffix": "D",
                    "width": 256,
                },
                {
                    "format_name": "P8",
                    "height": 128,
                    "logo_code": 50,
                    "name": "pad_north",
                    "selector": "50:S:pad_north",
                    "weather_suffix": "S",
                    "width": 128,
                },
            ],
        })
        _write_json(self.paths.scorebug, {
            "schema": "vc_scorebug_presentation_audit/v1",
            "nfl2k5": {"texture_targets": [
                {
                    "conversion_status": "base_level_supported",
                    "format_name": "P8",
                    "height": height,
                    "name": name,
                    "role": "synthetic role",
                    "width": width,
                }
                for name, width, height in (
                    ("score_buga", 64, 64),
                    ("shield_espn", 128, 64),
                    ("digital_font", 128, 128),
                )
            ]},
        })

    def load(self) -> Nfl2k5ExtendedVisualCatalog:
        return Nfl2k5ExtendedVisualCatalog.from_reports(
            self.paths, expectations=self.expectations
        )


class Nfl2k5ExtendedVisualCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="extended-visual-catalog-")
        self.root = Path(self.temporary.name)
        self.fixture = SyntheticReports(self.root)
        self.catalog = self.fixture.load()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_every_synthetic_target_is_browsable_with_only_logical_metadata(self) -> None:
        self.assertEqual(len(self.catalog.assets), 10)
        self.assertEqual(
            {kind: len(self.catalog.assets_for_kind(kind)) for kind in {
                asset.kind for asset in self.catalog.assets
            }},
            {
                "player_portrait": 2,
                "live_face": 3,
                "create_team_field_art": 2,
                "scorebug_texture": 3,
            },
        )
        self.assertEqual(
            self.catalog.get_asset("nfl2k5.portrait.0042").label,
            "Portrait 0042 — Test Quarterback",
        )
        self.assertEqual(
            {asset.asset_id for asset in self.catalog.search("synthetic city")},
            {
                "nfl2k5.portrait.0042",
                "nfl2k5.live-face.0042.f",
                "nfl2k5.live-face.0042.h",
                "nfl2k5.live-face.0042.n",
            },
        )
        for asset in self.catalog.assets:
            rendered = repr(asset).casefold()
            self.assertNotIn("offset", rendered)
            self.assertNotIn("sha256", rendered)
            self.assertTrue(asset.editable)

    def test_unified_provider_edit_shapes_are_exact_and_named(self) -> None:
        path = Path("project-assets/mine.png")
        self.assertEqual(
            self.catalog.get_asset("nfl2k5.portrait.0042").provider_edit(path),
            {"kind": "player_portrait", "png": str(path), "portrait_id": "0042"},
        )
        self.assertEqual(
            self.catalog.get_asset("nfl2k5.live-face.0042.n").provider_edit(path),
            {"face_id": "0042", "family": "n", "kind": "live_face",
             "png": str(path)},
        )
        self.assertEqual(
            self.catalog.get_asset(
                "nfl2k5.create-field.50.s.pad_north"
            ).provider_edit(path),
            {"kind": "create_team_field_art", "logo_code": 50,
             "png": str(path), "texture": "pad_north", "weather": "S"},
        )

    def test_scorebug_assets_support_unified_and_legacy_typed_routes(self) -> None:
        asset = self.catalog.get_asset("nfl2k5.scorebug.shield_espn")
        self.assertIs(asset.writer_route, VisualWriterRoute.SCOREBUG)
        self.assertEqual(asset.provider_edit("mine.png"), {
            "kind": "scorebug_texture",
            "png": "mine.png",
            "target": "shield_espn",
        })
        recipe = asset.scorebug_recipe_edit("mine.png")
        self.assertEqual((recipe.target, recipe.png), ("shield_espn", Path("mine.png")))
        with self.assertRaisesRegex(ExtendedVisualCatalogError, "unified visual"):
            self.catalog.get_asset("nfl2k5.portrait.0007").scorebug_recipe_edit(
                "mine.png"
            )

    def test_changed_dimensions_and_duplicate_selectors_fail_closed(self) -> None:
        field = json.loads(self.fixture.paths.field_art.read_text(encoding="utf-8"))
        field["textures"][0]["width"] = 255
        _write_json(self.fixture.paths.field_art, field)
        with self.assertRaisesRegex(ExtendedVisualCatalogError, "named writer contract"):
            self.fixture.load()

        # Restore the field report, then duplicate a portrait selector.
        self.fixture = SyntheticReports(self.root)
        portraits = json.loads(self.fixture.paths.portraits.read_text(encoding="utf-8"))
        portraits["targets"][1] = dict(portraits["targets"][0])
        _write_json(self.fixture.paths.portraits, portraits)
        with self.assertRaisesRegex(ExtendedVisualCatalogError, "duplicated"):
            self.fixture.load()

    def test_product_catalog_combines_phase1_and_phase2_asset_lookup(self) -> None:
        uniform = SimpleNamespace(
            asset_id="nfl2k5.uniform.synthetic.torso",
            kind="torso",
        )
        aggregate = Nfl2k5ProductVisualCatalog(
            SimpleNamespace(assets=(uniform,)), self.catalog
        )
        self.assertIs(aggregate.get_asset(uniform.asset_id), uniform)
        self.assertEqual(
            aggregate.get_asset("nfl2k5.portrait.0042").portrait_id, "0042"
        )
        self.assertEqual(len(aggregate.assets), 11)


class Nfl2k5ExtendedVisualIOTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="extended-visual-io-")
        self.root = Path(self.temporary.name)
        self.fixture = SyntheticReports(self.root)
        self.catalog = self.fixture.load()
        self.originals = self.root / "private-user-cache" / "originals"
        self.originals.mkdir(parents=True)
        self.cache = SimpleNamespace(
            originals=self.originals,
            source=SimpleNamespace(sha256="a" * 64),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_strict_validation_accepts_exact_pngs_and_explains_bad_inputs(self) -> None:
        portrait = self.catalog.get_asset("nfl2k5.portrait.0042")
        valid = self.root / "portrait.png"
        payload = _png(valid, portrait.dimensions)
        checked, rgba = Nfl2k5ExtendedVisualIO.validate_replacement(portrait, valid)
        self.assertEqual(checked, payload)
        self.assertEqual(len(rgba), 128 * 128 * 4)

        wrong = self.root / "wrong.png"
        _png(wrong, (64, 64))
        with self.assertRaisesRegex(ValidationError, "128×128"):
            Nfl2k5ExtendedVisualIO.validate_replacement(portrait, wrong)

        not_png = self.root / "portrait.dat"
        not_png.write_bytes(payload)
        with self.assertRaisesRegex(ValidationError, "needs a PNG"):
            Nfl2k5ExtendedVisualIO.validate_replacement(portrait, not_png)

        linked = self.root / "linked.png"
        linked.symlink_to(valid)
        with self.assertRaisesRegex(ValidationError, "not a folder or link"):
            Nfl2k5ExtendedVisualIO.validate_replacement(portrait, linked)

    def test_live_face_alpha_contract_matches_the_existing_importer(self) -> None:
        face = self.catalog.get_asset("nfl2k5.live-face.0042.f")
        transparent = self.root / "transparent.png"
        _png(transparent, face.dimensions, alpha=120)
        with self.assertRaisesRegex(ValidationError, "fully opaque"):
            Nfl2k5ExtendedVisualIO.validate_replacement(face, transparent)
        opaque = self.root / "opaque.png"
        _png(opaque, face.dimensions)
        Nfl2k5ExtendedVisualIO.validate_replacement(face, opaque)

    def test_original_is_private_verified_and_exported_without_report_bytes(self) -> None:
        asset = self.catalog.get_asset("nfl2k5.scorebug.score_buga")
        calls = 0

        def decode(selected):
            nonlocal calls
            calls += 1
            source = self.root / "synthetic-original.png"
            payload = _png(source, selected.dimensions)
            _checked, rgba = Nfl2k5ExtendedVisualIO.validate_replacement(selected, source)
            return payload, rgba

        io = Nfl2k5ExtendedVisualIO(
            self.cache, report_paths=self.fixture.paths, original_decoder=decode
        )
        first = io.ensure_original(asset)
        second = io.ensure_original(asset)
        self.assertEqual(first, second)
        self.assertEqual(calls, 1)
        metadata = json.loads(first.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["schema"], ORIGINAL_SCHEMA)
        self.assertEqual(metadata["asset_id"], asset.asset_id)
        self.assertNotIn("offset", metadata)

        destination = self.root / "user-export.png"
        self.assertEqual(io.export_original(asset, destination), destination.resolve())
        self.assertEqual(destination.read_bytes(), first.read_bytes())
        with self.assertRaisesRegex(ValidationError, "already exists"):
            io.export_original(asset, destination)

    def test_changed_private_original_is_rejected_instead_of_silently_reused(self) -> None:
        asset = self.catalog.get_asset("nfl2k5.portrait.0007")

        def decode(selected):
            source = self.root / "generated.png"
            payload = _png(source, selected.dimensions)
            _checked, rgba = Nfl2k5ExtendedVisualIO.validate_replacement(selected, source)
            return payload, rgba

        io = Nfl2k5ExtendedVisualIO(self.cache, original_decoder=decode)
        original = io.ensure_original(asset)
        original.write_bytes(b"changed outside the app")
        with self.assertRaisesRegex(ValidationError, "changed outside Mod Studio"):
            io.ensure_original(asset)


if __name__ == "__main__":
    unittest.main()
