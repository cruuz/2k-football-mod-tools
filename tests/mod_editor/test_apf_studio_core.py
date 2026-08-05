from __future__ import annotations

import hashlib
import json
import os
import pathlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

from mod_editor.apf_studio.catalog import (
    _apply_external_audio_catalog_policy,
    _category_for,
)
from mod_editor.apf_studio.models import (
    ApfAsset,
    ApfCategory,
    ApfStatus,
    ExternalAudioBankIdentity,
    ExternalAudioBankOwner,
    Modification,
)
from mod_editor.apf_studio.project import ProjectError, load_project, save_project
from mod_editor.apf_studio.source import SourceManager
from mod_editor.apf_studio.uniform_targets import (
    EXPECTED_CATALOG_SHA256,
    FAMILIES,
    UniformTargetError,
    load_targets,
    target_record,
)


class UniformTargetCatalogTests(unittest.TestCase):
    def test_crowd_visuals_are_stadium_assets_not_audio(self) -> None:
        self.assertIs(_category_for("crowd_lower", "TXTR"), ApfCategory.STADIUMS)
        self.assertIs(_category_for("crowd_render", "SCNE"), ApfCategory.STADIUMS)
        self.assertIs(_category_for("crowd_pants_color", "TXTR"), ApfCategory.STADIUMS)
        self.assertIs(_category_for("crowd_cheer", "AUDO"), ApfCategory.AUDIO)
        self.assertIs(_category_for("lines.bin", "XMA1_BANK"), ApfCategory.AUDIO)

    def test_external_audio_policy_names_and_routes_all_physical_banks(self) -> None:
        assets = tuple(
            ApfAsset(
                asset_id=f"apf:outer:{index}",
                outer_index=index,
                inner_index=None,
                name=f"outer_{index:04d}",
                type_name="NON_IFF",
                asset_class="opaque_outer_resource",
                category=ApfCategory.ALL_ASSETS,
                status=ApfStatus.EXPORT_ONLY,
                decoded_size=2_048 * (index + 1),
                outer_size=2_048 * (index + 1),
                part_count=1,
                metadata={"name_id": f"0x{1_000 + index:08x}"},
            )
            for index in range(19)
        )
        identities = tuple(
            ExternalAudioBankIdentity(
                external_filename=f"bank_{index}.bin",
                outer_table_index=index,
                name_id=1_000 + index,
                encoded_size=2_048 * (index + 1),
                owners=(
                    ExternalAudioBankOwner(
                        descriptor_outer_index=100,
                        descriptor_inner_index=index,
                        bank_name=f"bank_{index}",
                        substream_count=index + 1,
                        sample_rate=48_000,
                        channel_count=2,
                    ),
                ),
            )
            for index in range(19)
        )

        routed = _apply_external_audio_catalog_policy(assets, identities)

        self.assertEqual(len(routed), 19)
        first = routed[0]
        self.assertEqual(first.name, "bank_0.bin")
        self.assertEqual(first.type_name, "XMA1_BANK")
        self.assertEqual(first.asset_class, "external_xma1_packet_bank")
        self.assertIs(first.category, ApfCategory.AUDIO)
        self.assertEqual(first.export_label, "Original external XMA1 bank (.bin)")
        self.assertEqual(first.metadata["descriptor_owner_count"], 1)
        self.assertIn("multi-cue", " ".join(first.notes))

    def test_catalog_is_small_metadata_only_and_complete(self) -> None:
        targets = load_targets()
        self.assertEqual(tuple(targets), FAMILIES)
        self.assertEqual({family: len(rows) for family, rows in targets.items()}, {
            "jersey": 24,
            "pants": 24,
            "helmet": 24,
            "shoulder": 24,
        })
        outer_indices: set[int] = set()
        for family, rows in targets.items():
            for index, row in enumerate(rows):
                self.assertEqual(row["asset_index"], index)
                self.assertEqual(row["outer_name"], f"uniform_{family}_{index:02d}.iff")
                self.assertEqual(
                    set(row),
                    {
                        "asset_index",
                        "outer_name",
                        "outer_name_id",
                        "outer_table_index",
                        "outer_allocation",
                        "inner_file",
                    },
                )
                self.assertEqual(set(row["outer_allocation"]), {"size", "sha256"})
                self.assertEqual(set(row["inner_file"]), {"index", "texture_sha256"})
                outer_indices.add(row["outer_table_index"])
        self.assertEqual(len(outer_indices), 96)

        catalog_path = Path(__file__).resolve().parents[2] / "mod_editor" / "data" / "apf2k8_uniform_targets.v1.json"
        data = catalog_path.read_bytes()
        self.assertLess(len(data), 50_000)
        self.assertEqual(hashlib.sha256(data).hexdigest(), EXPECTED_CATALOG_SHA256)
        document = json.loads(data)
        forbidden = {
            "rgba",
            "pixels",
            "physical",
            "pack_offset",
            "team_bank_uses",
            "controlled_fixture",
            "decoded_sha256",
            "stored_sha256",
        }

        def visit(value: object) -> None:
            if isinstance(value, dict):
                self.assertTrue(forbidden.isdisjoint(value))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(document)

    def test_target_bounds_are_human_readable(self) -> None:
        with self.assertRaisesRegex(UniformTargetError, "0..23"):
            target_record("jersey", 24)
        with self.assertRaisesRegex(UniformTargetError, "Unsupported"):
            target_record("socks", 0)


class IsoExtractionTests(unittest.TestCase):
    def test_clean_iso_extraction_keeps_system_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = root / "extract-xiso"
            tool.write_bytes(b"fixture executable")
            tool.chmod(0o755)
            iso = root / "game.iso"
            iso.write_bytes(b"fixture iso")
            cache = root / "cache"
            commands: list[list[str]] = []

            def fake_run(command: list[str], **_kwargs: object):
                commands.append(command)
                destination = Path(command[command.index("-d") + 1])
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "0A").write_bytes(b"fixture")
                (destination / "$SystemUpdate").mkdir()
                (destination / "$SystemUpdate" / "su20076000_00000000").write_bytes(
                    b"fixture update"
                )
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            manager = SourceManager(cache_root=cache, extract_xiso=tool)
            with patch("mod_editor.apf_studio.source.subprocess.run", side_effect=fake_run):
                output = manager._extract_iso(iso, "a" * 64, lambda *_args: None)

            self.assertTrue((output / "0A").is_file())
            self.assertTrue((output / "$SystemUpdate" / "su20076000_00000000").is_file())
            self.assertEqual(len(commands), 1)
            self.assertNotIn("-s", commands[0])
            self.assertIn("-q", commands[0])
            self.assertIn("-d", commands[0])


class RetailFreeProjectTests(unittest.TestCase):
    @staticmethod
    def _png(path: Path) -> bytes:
        Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(path, format="PNG")
        return path.read_bytes()

    def test_project_roundtrip_contains_only_declared_user_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "replacement.png"
            data = self._png(png)
            digest = hashlib.sha256(data).hexdigest()
            modification = Modification(
                asset_id="apf:uniform:jersey:00",
                kind="uniform",
                replacement_path=png,
                replacement_sha256=digest,
                metadata={"family": "jersey", "asset_index": 0},
            )
            project = save_project(
                root / "sample.apf2k8mod",
                source_sha256="d" * 64,
                modifications=(modification,),
            )
            with zipfile.ZipFile(project) as archive:
                names = set(archive.namelist())
                self.assertEqual(len(names), 2)
                self.assertIn("project.json", names)
                self.assertFalse(any("original" in name or "preimage" in name for name in names))
                manifest = json.loads(archive.read("project.json"))
                self.assertFalse(manifest["distribution"]["contains_original_game_bytes"])
                self.assertFalse(manifest["distribution"]["contains_original_preimages"])
                payload_name = manifest["replacements"][0]["payload"]
                self.assertEqual(archive.read(payload_name), data)

            manifest, loaded, _annotations = load_project(
                project,
                expected_source_sha256="d" * 64,
                destination_dir=root / "loaded",
            )
            self.assertEqual(manifest["replacement_count"], 1)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].replacement_path.read_bytes(), data)

    def test_project_loader_rejects_undeclared_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "unsafe.apf2k8mod"
            manifest = {
                "schema": "apf2k8_mod_project/v1",
                "game": "apf2k8_xbox360",
                "source": {"sha256": "d" * 64},
                "replacement_count": 0,
                "replacements": [],
                "distribution": {
                    "contains_original_game_bytes": False,
                    "contains_original_preimages": False,
                },
            }
            with zipfile.ZipFile(project, "w") as archive:
                archive.writestr("project.json", json.dumps(manifest))
                archive.writestr("retail-preimage.bin", b"must never be accepted")
            with self.assertRaisesRegex(ProjectError, "undeclared"):
                load_project(
                    project,
                    expected_source_sha256="d" * 64,
                    destination_dir=root / "loaded",
                )


class BundledExtractorTests(unittest.TestCase):
    """The vendored extractor that lets a user hand the app a .iso directly."""

    def test_the_bundled_extractor_follows_the_running_platform(self) -> None:
        from mod_editor.core import platform_compat
        from mod_editor.apf_studio.source import bundled_extract_xiso

        saved = platform_compat.IS_WINDOWS
        try:
            platform_compat.IS_WINDOWS = False
            self.assertEqual(bundled_extract_xiso().name, "extract-xiso")
            platform_compat.IS_WINDOWS = True
            self.assertEqual(bundled_extract_xiso().name, "extract-xiso.exe")
        finally:
            platform_compat.IS_WINDOWS = saved
        # The default a SourceManager picks is the one for THIS host, so the
        # app never reaches for a binary the running OS cannot execute.
        expected = "extract-xiso.exe" if platform_compat.IS_WINDOWS else "extract-xiso"
        self.assertEqual(SourceManager().extract_xiso.name, expected)

    def test_bundled_binaries_are_the_pinned_reviewed_builds(self) -> None:
        # All binaries ship in the APF release and are pinned by the release
        # gate; a bundled executable nobody rebuilds at review time is only
        # trustworthy if its bytes are fixed. Assert the shipped files still
        # match those pins, and that each is the image format its platform can
        # actually run.
        import importlib.util

        root = pathlib.Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "_apf2k8_release_pins", root / "packaging/check_apf2k8_mod_studio_release.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        # tools/vendor/ is gitignored in its entirety, so NEITHER binary is in
        # a clean checkout -- they are release-build inputs bundled into the
        # tarball locally, which is why ci.yml's release-gates job skips loudly
        # when they are absent rather than failing. This test follows the same
        # convention: it asserts the pins wherever the binaries actually exist
        # (a maintainer's tree, a release build) and skips where they cannot.
        missing = [
            relative
            for relative in (module.REVIEWED_BINARY, module.REVIEWED_WINDOWS_BINARY)
            if not (root / relative).is_file()
        ]
        if missing:
            self.skipTest(
                "vendored extract-xiso binaries are gitignored release-build "
                f"inputs and are absent from this checkout: {', '.join(missing)}"
            )

        for relative, size, digest, magic in (
            (
                module.REVIEWED_BINARY,
                module.REVIEWED_BINARY_SIZE,
                module.REVIEWED_BINARY_SHA256,
                b"\x7fELF",
            ),
            (
                module.REVIEWED_WINDOWS_BINARY,
                module.REVIEWED_WINDOWS_BINARY_SIZE,
                module.REVIEWED_WINDOWS_BINARY_SHA256,
                b"MZ",
            ),
            (
                module.REVIEWED_H7A_BINARY,
                module.REVIEWED_H7A_BINARY_SIZE,
                module.REVIEWED_H7A_BINARY_SHA256,
                b"\x7fELF",
            ),
        ):
            with self.subTest(binary=relative):
                path = root / relative
                payload = path.read_bytes()
                self.assertEqual(len(payload), size)
                self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)
                self.assertTrue(payload.startswith(magic))


if __name__ == "__main__":
    unittest.main()
