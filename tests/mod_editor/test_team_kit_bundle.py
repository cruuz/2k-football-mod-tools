"""Focused product tests for private, complete NFL 2K5 Team Kit bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_uniform_catalog import (
    ASSETS_PER_SET,
    load_nfl2k5_uniform_catalog,
)
from mod_editor.studio.session import StudioSession
from mod_editor.studio.uniform_bundle import (
    TEAM_KIT_BUNDLE_SCHEMA,
    TEAM_KIT_GUIDE,
    TEAM_KIT_MANIFEST,
    TeamKitBundleError,
    TeamKitBundleService,
    select_team_uniform_sets,
)

from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import encode_rgba_png


def _rgba(asset: object, color: tuple[int, int, int, int]) -> bytes:
    return bytes(color) * (int(getattr(asset, "width")) * int(getattr(asset, "height")))


def _png(asset: object, color: tuple[int, int, int, int]) -> bytes:
    return encode_rgba_png(
        int(getattr(asset, "width")),
        int(getattr(asset, "height")),
        _rgba(asset, color),
    )


class _PngAssetIO:
    """Small private-source stand-in using strict real PNG contracts."""

    def __init__(self, cache: object) -> None:
        self.cache = cache
        self.originals = Path(getattr(cache, "root")) / "originals"
        self.originals.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _color(asset: object) -> tuple[int, int, int, int]:
        digest = hashlib.sha256(str(getattr(asset, "asset_id")).encode()).digest()
        return digest[0], digest[1], digest[2], 255

    def ensure_original(self, asset: object) -> Path:
        name = hashlib.sha256(str(getattr(asset, "asset_id")).encode()).hexdigest()
        path = self.originals / f"{name}.png"
        if not path.exists():
            path.write_bytes(_png(asset, self._color(asset)))
        return path

    @staticmethod
    def validate_replacement(asset: object, path: Path) -> tuple[bytes, bytes]:
        supplied = path.resolve(strict=True)
        payload = supplied.read_bytes()
        try:
            width, height, rgba = decode_rgba_png(
                payload,
                (int(getattr(asset, "width")), int(getattr(asset, "height"))),
            )
        except ValueError as exc:
            raise ValidationError(f"bad synthetic Team Kit PNG: {exc}") from exc
        if (width, height) != (
            int(getattr(asset, "width")), int(getattr(asset, "height"))
        ):
            raise ValidationError("bad synthetic Team Kit dimensions")
        return payload, rgba


class TeamKitBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_uniform_catalog()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="team-kit-test-")
        self.root = Path(self.temporary.name)
        source = SimpleNamespace(sha256="a" * 64)
        self.cache = SimpleNamespace(source=source, root=self.root / "private-cache")
        with mock.patch(
            "mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO
        ):
            self.session = StudioSession(
                self.cache,
                self.catalog,
                root=self.root / "sessions",
                session_id="active",
            )
        self.service = TeamKitBundleService(self.catalog, self.session)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _replace_file(
        self, bundle: Path, asset_id: str, color: tuple[int, int, int, int]
    ) -> Path:
        manifest = json.loads((bundle / TEAM_KIT_MANIFEST).read_text())
        row = next(item for item in manifest["assets"] if item["asset_id"] == asset_id)
        asset = self.catalog.get_asset(asset_id)
        path = bundle / row["path"]
        path.write_bytes(_png(asset, color))
        return path

    def test_side_helper_and_complete_folder_manifest_are_general_not_giants_only(self) -> None:
        giants = select_team_uniform_sets(
            self.catalog, asset_code="18", variant=0, sides="both"
        )
        self.assertEqual([item.selector for item in giants], ["18H0", "18A0"])
        lions = select_team_uniform_sets(
            self.catalog, asset_code="09", variant=0, sides=("away",)
        )
        self.assertEqual([item.selector for item in lions], ["09A0"])

        output = self.root / "giants-current-team-kit"
        result = self.service.export_team(
            asset_code="18", variant=0, sides="BOTH", destination=output
        )
        self.assertEqual(result.container, "folder")
        self.assertEqual(result.set_selectors, ("18H0", "18A0"))
        self.assertEqual(result.asset_count, ASSETS_PER_SET * 2)
        manifest_payload = (output / TEAM_KIT_MANIFEST).read_bytes()
        self.assertEqual(hashlib.sha256(manifest_payload).hexdigest(), result.manifest_sha256)
        manifest = json.loads(manifest_payload)
        self.assertEqual(manifest["schema"], TEAM_KIT_BUNDLE_SCHEMA)
        self.assertIn("do-not-distribute", manifest["payload_policy"])
        self.assertEqual(manifest["source"], {"sha256": "a" * 64})
        self.assertEqual(manifest["counts"], {"assets": 78, "sets": 2})
        self.assertEqual(len({row["path"] for row in manifest["assets"]}), 78)
        self.assertEqual(len(list(output.rglob("*.png"))), 78)
        self.assertTrue((output / TEAM_KIT_GUIDE).is_file())
        torso = next(
            row for row in manifest["assets"]
            if row["asset_id"] == "nfl2k5.uniform.18h0.torso"
        )
        self.assertEqual(torso["dimensions"], {"height": 256, "width": 512})
        self.assertIn("UV atlas", torso["authoring_note"])
        # A modern texture pack normally ships numbers painted into the jersey.
        # 2K5 draws them separately and on top, so baked-in numbers come out
        # doubled -- reported from a real macOS import, and the slot copy has to
        # say so before someone spends an evening on the art.
        self.assertIn("Do not paint jersey numbers", torso["authoring_note"])
        self.assertIn("Jersey Digit 0-9", torso["authoring_note"])
        self.assertIn("appear twice", torso["authoring_note"])
        self.assertIn("independently writable", torso["ownership_note"])
        nameplate = next(
            row for row in manifest["assets"]
            if row["asset_id"].endswith("nameplate")
        )
        # 1024x32 horizontal. The transposed 32x1024 reading came from a TXTR
        # descriptor bug that was fixed in the decoder while this copy kept it,
        # which would send an author to paint a rotated strip.
        self.assertIn("1024×32 horizontal", nameplate["authoring_note"])
        self.assertNotIn("32×1024", nameplate["authoring_note"])
        card = next(
            row for row in manifest["assets"]
            if row["asset_id"].endswith("team-select.helm.128")
        )
        self.assertIn("exact visible timing remains unresolved", card["ownership_note"])
        self.assertNotIn(str(self.root), manifest_payload.decode())

    def test_zip_export_is_deterministic_and_carries_the_same_canonical_manifest(self) -> None:
        first = self.root / "one.zip"
        second = self.root / "two.zip"
        result_one = self.service.export(("09A0",), first)
        result_two = self.service.export(("09A0",), second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(result_one.manifest_sha256, result_two.manifest_sha256)
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(len(archive.namelist()), ASSETS_PER_SET + 2)
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            self.assertEqual(
                json.loads(archive.read(TEAM_KIT_MANIFEST))["counts"],
                {"assets": ASSETS_PER_SET, "sets": 1},
            )
            self.assertTrue(all(row.date_time == (1980, 1, 1, 0, 0, 0)
                                for row in archive.infolist()))

    def test_import_stages_only_pixel_changes_as_one_undo_and_project_is_authored_only(self) -> None:
        bundle = self.root / "working-kit"
        self.service.export(("18H0",), bundle)
        changed_ids = (
            "nfl2k5.uniform.18h0.torso",
            "nfl2k5.uniform.18h0.team-select.unif.256",
        )
        self._replace_file(bundle, changed_ids[0], (255, 20, 40, 255))
        self._replace_file(bundle, changed_ids[1], (40, 220, 80, 170))

        result = self.service.import_edited(bundle)
        self.assertEqual(result.asset_count, ASSETS_PER_SET)
        self.assertEqual(result.changed_count, 2)
        self.assertEqual(result.unchanged_count, ASSETS_PER_SET - 2)
        self.assertIsNotNone(result.batch)
        self.assertEqual(result.batch.changed_asset_ids, changed_ids)  # type: ignore[union-attr]
        self.assertEqual(self.session.modified_asset_ids, set(changed_ids))

        project = self.root / "authored-only.2k5mod"
        self.session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            self.assertEqual(len(archive.namelist()), 3)
            project_manifest = json.loads(archive.read("project.json"))
            self.assertEqual(project_manifest["payload_policy"], "user-replacements-only")
            self.assertEqual(
                {row["asset_id"] for row in project_manifest["edits"]},
                set(changed_ids),
            )

        self.assertEqual(self.session.undo(), "Import Team Kit 18H0")
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_validate_all_rejects_one_bad_png_without_staging_the_other(self) -> None:
        bundle = self.root / "invalid-kit"
        self.service.export(("18A0",), bundle)
        first = "nfl2k5.uniform.18a0.torso"
        second = "nfl2k5.uniform.18a0.sleeve"
        self._replace_file(bundle, first, (1, 2, 3, 255))
        bad = self._replace_file(bundle, second, (4, 5, 6, 255))
        bad.write_bytes(b"not a PNG")

        with self.assertRaisesRegex(ValidationError, "bad synthetic Team Kit PNG"):
            self.service.import_edited(bundle)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)
        self.assertEqual(tuple(self.session.replacements.iterdir()), ())

    def test_stale_baseline_and_manifest_changes_fail_closed(self) -> None:
        bundle = self.root / "stale-kit"
        self.service.export(("09A0",), bundle)
        torso = self.catalog.get_asset("nfl2k5.uniform.09a0.torso")
        newer = self.root / "newer.png"
        newer.write_bytes(_png(torso, (60, 70, 80, 255)))
        self.session.replace(torso, newer)
        with self.assertRaisesRegex(TeamKitBundleError, "working pixels changed"):
            self.service.import_edited(bundle)
        self.assertEqual(self.session.modified_asset_ids, {torso.asset_id})
        self.assertEqual(self.session.undo(), f"Replace {torso.label}")

        manifest_path = bundle / TEAM_KIT_MANIFEST
        manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
        with self.assertRaisesRegex(TeamKitBundleError, "manifest changed"):
            self.service.import_edited(bundle)

    def test_batch_validates_every_input_first_and_rolls_back_a_commit_failure(self) -> None:
        torso = self.catalog.get_asset("nfl2k5.uniform.18h0.torso")
        sleeve = self.catalog.get_asset("nfl2k5.uniform.18h0.sleeve")
        first = self.root / "first.png"
        first.write_bytes(_png(torso, (11, 12, 13, 255)))
        bad = self.root / "bad.png"
        bad.write_bytes(b"bad")
        with self.assertRaisesRegex(ValidationError, "bad synthetic Team Kit PNG"):
            self.session.replace_batch(((torso, first), (sleeve, bad)))
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

        self.session.replace(torso, first)
        before = self.session.current_path(torso).read_bytes()
        second = self.root / "second.png"
        third = self.root / "third.png"
        second.write_bytes(_png(torso, (21, 22, 23, 255)))
        third.write_bytes(_png(sleeve, (31, 32, 33, 255)))
        with mock.patch.object(
            self.session,
            "_write_manifest",
            side_effect=(OSError("synthetic disk failure"), None),
        ):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                self.session.replace_batch(((torso, second), (sleeve, third)))
        self.assertEqual(self.session.modified_asset_ids, {torso.asset_id})
        self.assertEqual(self.session.current_path(torso).read_bytes(), before)
        self.assertFalse(self.session.is_modified(sleeve))
        self.assertEqual(self.session.undo(), f"Replace {torso.label}")
        self.assertEqual(self.session.modified_count, 0)

    def test_existing_destinations_and_undeclared_bundle_files_are_refused(self) -> None:
        destination = self.root / "exists"
        destination.mkdir()
        marker = destination / "mine.txt"
        marker.write_text("keep")
        with self.assertRaisesRegex(TeamKitBundleError, "already exists"):
            self.service.export(("18H0",), destination)
        self.assertEqual(marker.read_text(), "keep")

        bundle = self.root / "extra-file-kit"
        self.service.export(("18H0",), bundle)
        (bundle / "surprise.bin").write_bytes(b"undeclared")
        with self.assertRaisesRegex(TeamKitBundleError, "undeclared"):
            self.service.import_edited(bundle)
        self.assertEqual(self.session.modified_count, 0)


if __name__ == "__main__":
    unittest.main()
