"""Headless product tests for the NFL 2K5 batch audio replacement pack."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import tempfile
from typing import Sequence
import unittest
from unittest import mock
import wave
import zipfile

import mod_editor.studio.audio_replacement_pack as audio_pack_module
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_audio_catalog import (
    MAX_AUDIO_REPLACEMENT_WAV_BYTES,
    MENU_BACK_SELECTOR,
    Nfl2k5AudioService,
    Nfl2k5StreamingAudioRange,
)
from mod_editor.core.nfl2k5_audo_fixed_slots import (
    CAPACITY_REPORT,
    EDITABLE_CLASSIFICATION,
)
from mod_editor.gui.audio_panel_qt import AudioPanel, CatalogAudioPanelHost
from mod_editor.studio.audio_replacement_pack import (
    AUDIO_CUE_MAP,
    AUDIO_CUE_MAP_SCHEMA,
    AUDIO_REPLACEMENT_GUIDE,
    AUDIO_REPLACEMENT_MANIFEST,
    AUDIO_REPLACEMENT_PACK_SCHEMA,
    AUDIO_REPLACEMENT_PACK_V2_SCHEMA,
    AUDIO_REPLACEMENT_PACK_V3_SCHEMA,
    AUDIO_REPLACEMENT_PACK_V4_SCHEMA,
    EXPECTED_COMPLETE_STANDALONE_COUNT,
    MAX_ARCHIVE_MEMBERS,
    MAX_MANIFEST_BYTES,
    MAX_PREFLIGHT_CHANGED_ROWS,
    MAX_REPLACEMENT_WAV_BYTES,
    MAX_SELECTED_AUDIO_COUNT,
    REPLACEMENTS_DIRECTORY,
    AudioReplacementPackPreflightResult,
    AudioReplacementPackService,
    complete_standalone_pack_path,
    standalone_runtime_meaning_status,
)
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.project_archive import save_project_archive
from mod_editor.studio.session import AudioSessionEdit, StudioSession
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture



def _plain_path(value: object) -> Path:
    """Compare paths the session may hand to os.replace with the Windows extended prefix stripped."""
    text = os.fspath(value)
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\"):
        if text.startswith(prefix):
            text = ("\\\\" + text[len(prefix):]) if prefix.endswith("UNC\\") else text[len(prefix):]
            break
    return Path(text)

def _menu_wav(path: Path, sample: int) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(int(sample).to_bytes(2, "little", signed=True) * 5_696)
    return path


def _exact_wav(path: Path, asset: object, sample: int) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(asset.channels)  # type: ignore[attr-defined]
        stream.setsampwidth(2)
        stream.setframerate(asset.sample_rate)  # type: ignore[attr-defined]
        stream.writeframes(
            int(sample).to_bytes(2, "little", signed=True)
            * asset.frame_count  # type: ignore[attr-defined]
            * asset.channels  # type: ignore[attr-defined]
        )
    return path


def _declared_wav(template: Path) -> Path:
    manifest = json.loads((template / AUDIO_REPLACEMENT_MANIFEST).read_text())
    return template.joinpath(*Path(manifest["assets"][0]["path"]).parts)


def _file_tree(root: Path) -> dict[str, bytes]:
    """Capture every private session file so transaction debris is visible."""

    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class AudioReplacementPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="audio-pack-test-")
        self.root = Path(self.temporary.name)
        source = self.root / "source"
        source.mkdir()
        self.fixture = AudioFixture(source)
        self.catalog = self.fixture.catalog()
        self.audio = Nfl2k5AudioService(self.fixture.cache, self.catalog)
        self.session = StudioSession(
            self.fixture.cache,
            object(),
            root=self.root / "sessions",
            session_id="active",
        )
        self.session.attach_audio_service(self.audio)
        self.service = AudioReplacementPackService(
            self.catalog, self.session, expected_editable_count=1
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_complete_pack_path_helper_uses_canonical_public_order(self) -> None:
        first, second = self.catalog.assets
        self.assertEqual(
            complete_standalone_pack_path(self.catalog, first.asset_id),
            "replacements/001__selected-audio.wav",
        )
        self.assertEqual(
            complete_standalone_pack_path(self.catalog, second.asset_id),
            "replacements/002__selected-audio.wav",
        )
        self.assertIsNone(complete_standalone_pack_path(self.catalog, "unknown"))
        self.assertIsNone(complete_standalone_pack_path(self.catalog, ""))
        self.assertEqual(
            standalone_runtime_meaning_status(first),
            "provisional_label_runtime_meaning_unproved",
        )
        self.assertEqual(
            standalone_runtime_meaning_status(second),
            "menu_back_route_runtime_unproved",
        )

    def _install_complete_standalone_catalog(self) -> tuple[object, ...]:
        """Expand the two-cue fixture to a canonical, metadata-only 850 rows."""

        generic = self.catalog.assets[0]
        menu_back = self.catalog.assets[1]
        synthetic = tuple(
            replace(
                generic,
                asset_id=f"nfl2k5.audio.audo.o{10 + index:04d}.c0000",
                name=f"Synthetic standalone cue {index + 1}",
                outer_index=10 + index,
                chunk_index=0,
                classification=(
                    EDITABLE_CLASSIFICATION
                    if index < 152
                    else generic.classification
                ),
            )
            for index in range(EXPECTED_COMPLETE_STANDALONE_COUNT - 1)
        )
        assets = (menu_back, *synthetic)
        self.catalog.assets = assets
        self.catalog._by_id = {  # noqa: SLF001
            asset.asset_id: asset for asset in assets
        }
        self.catalog._by_selector = {  # noqa: SLF001
            asset.selector: asset for asset in assets
        }
        return assets

    def test_legacy_v1_ordered_id_set_stays_rc14_compatible(self) -> None:
        report = json.loads(CAPACITY_REPORT.read_bytes())
        synthetic_assets = []
        for row in report["records"]:
            _outer, outer_text, _chunk, chunk_text = row["key"].split("_")
            selector = int(outer_text), int(chunk_text)
            synthetic_assets.append(SimpleNamespace(
                asset_id=(
                    f"nfl2k5.audio.audo.o{selector[0]:04d}."
                    f"c{selector[1]:04d}"
                ),
                legacy_complete_pack_editable=(
                    selector == MENU_BACK_SELECTOR
                    or row["classification"] == EDITABLE_CLASSIFICATION
                ),
                selector=selector,
            ))
        selected = audio_pack_module._editable_assets(  # noqa: SLF001
            SimpleNamespace(assets=tuple(synthetic_assets)),
            expected_editable_count=153,
        )
        ordered_ids = json.dumps(
            [asset.asset_id for asset in selected], separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(ordered_ids).hexdigest(),
            "156c3a02e4ef27ee1a245a0946a3033575dc3d30872f1664b2adf1dfbd488ecc",
        )

    def test_folder_and_zip_templates_are_deterministic_metadata_only(self) -> None:
        folder = self.root / "template"
        result = self.service.export_template(folder, container="folder")
        self.assertEqual(result.asset_count, 1)
        self.assertEqual(result.retail_audio_file_count, 0)
        self.assertTrue((folder / "replacements").is_dir())
        self.assertEqual(
            {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()},
            {AUDIO_REPLACEMENT_GUIDE, AUDIO_REPLACEMENT_MANIFEST},
        )
        self.assertFalse(self.audio.original_path(self.catalog.assets[1]).exists())
        manifest_payload = (folder / AUDIO_REPLACEMENT_MANIFEST).read_bytes()
        manifest = json.loads(manifest_payload)
        self.assertTrue(all(asset.editable for asset in self.catalog.assets))
        self.assertFalse(self.catalog.assets[0].legacy_complete_pack_editable)
        self.assertTrue(self.catalog.assets[1].legacy_complete_pack_editable)
        self.assertEqual(
            [row["asset_id"] for row in manifest["assets"]],
            [self.catalog.assets[1].asset_id],
        )
        self.assertEqual(
            manifest["schema"], "2k5_mod_studio_audio_replacement_pack/v1"
        )
        self.assertEqual(manifest["schema"], AUDIO_REPLACEMENT_PACK_SCHEMA)
        self.assertEqual(
            manifest["payload_policy"],
            "metadata-only-template; zero-retail-audio-by-construction",
        )
        self.assertFalse(
            manifest["capability_boundary"]["streaming_bank_replacement_supported"]
        )
        self.assertEqual(manifest["assets"][0]["route"]["kind"], "menu_back")
        self.assertNotIn(b"RIFF", manifest_payload)
        self.assertNotIn(str(self.root), manifest_payload.decode("utf-8"))

        left = self.root / "left.zip"
        right = self.root / "right.zip"
        self.service.export_template(left, container="zip")
        self.service.export_template(right, container="zip", asset_ids=None)
        self.assertEqual(left.read_bytes(), right.read_bytes())
        with zipfile.ZipFile(left) as archive:
            self.assertEqual(
                archive.namelist(),
                [AUDIO_REPLACEMENT_GUIDE, AUDIO_REPLACEMENT_MANIFEST, "replacements/"],
            )
            self.assertFalse(any(name.endswith(".wav") for name in archive.namelist()))

    def test_export_uses_dirhandle_when_posix_fd_paths_are_unavailable(self) -> None:
        """Hosted macOS need not expose a usable /proc/self/fd or /dev/fd alias."""

        folder = self.root / "macos-fallback-folder"
        archive_path = self.root / "macos-fallback.zip"
        with mock.patch.object(
            audio_pack_module, "_pinned_staging_root", return_value=None
        ):
            self.service.export_template(folder, container="folder")
            self.service.export_template(archive_path, container="zip")

        self.assertTrue((folder / REPLACEMENTS_DIRECTORY).is_dir())
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    AUDIO_REPLACEMENT_GUIDE,
                    AUDIO_REPLACEMENT_MANIFEST,
                    f"{REPLACEMENTS_DIRECTORY}/",
                ],
            )
        self.assertFalse(
            any(".audio-pack-" in path.name for path in self.root.iterdir())
        )

    def test_v1_v2_zip_bytes_remain_rc15_compatible(self) -> None:
        legacy = self.root / "legacy-v1.zip"
        selected = self.root / "selected-v2.zip"
        self.service.export_template(legacy, container="zip")
        self.service.export_template(
            selected,
            container="zip",
            asset_ids=(
                self.catalog.assets[0].asset_id,
                self.catalog.streaming_ranges[0].asset_id,
            ),
        )
        self.assertEqual(
            hashlib.sha256(legacy.read_bytes()).hexdigest(),
            "ec8afb6aaa0372ea70a3cb124ba7ecb2fb86adadad915e3acb13fd89e2b451c4",
        )
        self.assertEqual(
            hashlib.sha256(selected.read_bytes()).hexdigest(),
            "788427d3ecc9e79c2b7eb16020a287c998512b94a1352c64ba4648f54edd3cb0",
        )

    def test_v3_complete_folder_and_zip_are_deterministic_public_metadata(self) -> None:
        assets = self._install_complete_standalone_catalog()
        folder = self.root / "complete-v3"
        left = self.root / "complete-left.zip"
        right = self.root / "complete-right.zip"

        exported = self.service.export_template(
            folder, container="folder", complete_standalone=True
        )
        self.service.export_template(
            left, container="zip", complete_standalone=True
        )
        self.service.export_template(
            right, container="zip", complete_standalone=True
        )

        self.assertEqual(MAX_ARCHIVE_MEMBERS, 854)
        self.assertEqual(exported.asset_count, EXPECTED_COMPLETE_STANDALONE_COUNT)
        self.assertEqual(exported.fixed_audo_count, 849)
        self.assertEqual(exported.menu_back_count, 1)
        self.assertEqual(exported.streaming_range_count, 0)
        self.assertEqual(exported.retail_audio_file_count, 0)
        self.assertEqual(left.read_bytes(), right.read_bytes())
        self.assertEqual(
            hashlib.sha256(left.read_bytes()).hexdigest(),
            "e9c47aa2454d37ef2365cb8508eed9e75ffac0b3c04d8e7618e0a820cff3d862",
        )
        self.assertEqual(
            {
                path.relative_to(folder).as_posix()
                for path in folder.rglob("*")
                if path.is_file()
            },
            {AUDIO_REPLACEMENT_GUIDE, AUDIO_REPLACEMENT_MANIFEST},
        )

        manifest_payload = (folder / AUDIO_REPLACEMENT_MANIFEST).read_bytes()
        guide_payload = (folder / AUDIO_REPLACEMENT_GUIDE).read_bytes()
        manifest = json.loads(manifest_payload)
        self.assertEqual(manifest["schema"], AUDIO_REPLACEMENT_PACK_V3_SCHEMA)
        self.assertEqual(
            manifest["counts"],
            {
                "complete_standalone_cues": 850,
                "fixed_audo_cues": 849,
                "menu_back_cues": 1,
                "replacement_wavs_in_template": 0,
            },
        )
        self.assertEqual(
            [row["asset_id"] for row in manifest["assets"]],
            [asset.asset_id for asset in assets],
        )
        self.assertEqual(len({row["asset_id"] for row in manifest["assets"]}), 850)
        self.assertEqual(
            sum(asset.selector == MENU_BACK_SELECTOR for asset in assets), 1
        )
        self.assertTrue(all(asset.editable for asset in assets))
        self.assertTrue(
            all(
                set(row)
                == {
                    "asset_id",
                    "contract",
                    "logical_aliases",
                    "path",
                    "working_baseline",
                }
                for row in manifest["assets"]
            )
        )
        self.assertTrue(
            all(
                row["logical_aliases"]
                == {"asset_ids": [row["asset_id"]], "count": 1}
                for row in manifest["assets"]
            )
        )
        self.assertIn(b"complete 850-cue standalone", guide_payload)
        self.assertIn(b"697 provisional", guide_payload)
        self.assertIn(b"physical slot", guide_payload)
        self.assertNotIn(b"RIFF", manifest_payload)
        public_text = manifest_payload.decode("utf-8")
        self.assertNotIn(str(self.root), public_text)
        for forbidden_key in (
            "physical_id",
            "canonical_id",
            "external_filename",
            "external_outer_index",
            "outer_index",
            "chunk_index",
            "range_start",
            "range_end",
            "offset",
            "fingerprint",
            "pack_path",
            "source_original_path",
        ):
            self.assertNotIn(f'"{forbidden_key}"', public_text)
        with zipfile.ZipFile(left) as archive:
            self.assertEqual(
                archive.namelist(),
                [AUDIO_REPLACEMENT_GUIDE, AUDIO_REPLACEMENT_MANIFEST, "replacements/"],
            )
            self.assertEqual(archive.read(AUDIO_REPLACEMENT_GUIDE), guide_payload)
            self.assertEqual(
                archive.read(AUDIO_REPLACEMENT_MANIFEST), manifest_payload
            )

    def test_v4_mapped_complete_pack_is_deterministic_safe_public_metadata(
        self,
    ) -> None:
        assets = list(self._install_complete_standalone_catalog())
        assets[1] = replace(
            assets[1],
            name='   =SUM(1,2), "quoted"\r\n next line',
        )
        canonical = tuple(assets)
        self.catalog.assets = canonical
        self.catalog._by_id = {  # noqa: SLF001
            asset.asset_id: asset for asset in canonical
        }
        self.catalog._by_selector = {  # noqa: SLF001
            asset.selector: asset for asset in canonical
        }
        folder = self.root / "mapped-complete"
        left = self.root / "mapped-left.zip"
        right = self.root / "mapped-right.zip"

        exported = self.service.export_template(
            folder,
            container="folder",
            complete_standalone=True,
            with_authoring_map=True,
        )
        self.service.export_template(
            left,
            container="zip",
            complete_standalone=True,
            with_authoring_map=True,
        )
        self.service.export_template(
            right,
            container="zip",
            complete_standalone=True,
            with_authoring_map=True,
        )

        self.assertEqual(exported.asset_count, 850)
        self.assertEqual(exported.retail_audio_file_count, 0)
        self.assertEqual(left.read_bytes(), right.read_bytes())
        self.assertEqual(
            {
                path.relative_to(folder).as_posix()
                for path in folder.rglob("*")
                if path.is_file()
            },
            {
                AUDIO_CUE_MAP,
                AUDIO_REPLACEMENT_GUIDE,
                AUDIO_REPLACEMENT_MANIFEST,
            },
        )
        manifest_payload = (folder / AUDIO_REPLACEMENT_MANIFEST).read_bytes()
        guide_payload = (folder / AUDIO_REPLACEMENT_GUIDE).read_bytes()
        map_payload = (folder / AUDIO_CUE_MAP).read_bytes()
        manifest = json.loads(manifest_payload)
        self.assertEqual(manifest["schema"], AUDIO_REPLACEMENT_PACK_V4_SCHEMA)
        self.assertEqual(
            manifest["cue_map"],
            {
                "path": AUDIO_CUE_MAP,
                "row_count": 850,
                "schema": AUDIO_CUE_MAP_SCHEMA,
                "sha256": hashlib.sha256(map_payload).hexdigest(),
            },
        )
        self.assertIn(b"copy it outside this pack", guide_payload)
        self.assertFalse(map_payload.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", map_payload)
        self.assertNotIn(b"RIFF", map_payload)
        map_text = map_payload.decode("utf-8")
        self.assertEqual(map_text.count("\n"), 851)
        rows = list(csv.DictReader(map_text.splitlines()))
        self.assertEqual(len(rows), 850)
        self.assertEqual(
            tuple(rows[0]),
            (
                "ordinal",
                "asset_id",
                "replacement_path",
                "display_name",
                "family_id",
                "family_label",
                "channels",
                "sample_rate_hz",
                "exact_frame_count",
                "duration_seconds",
                "product_edit_status",
                "writer_route",
                "legacy_v1_pack_member",
                "alias_status",
                "runtime_meaning_status",
            ),
        )
        self.assertEqual(
            [row["asset_id"] for row in rows],
            [asset.asset_id for asset in canonical],
        )
        self.assertEqual(
            [row["replacement_path"] for row in rows],
            [row["path"] for row in manifest["assets"]],
        )
        self.assertEqual(rows[1]["display_name"], "'=SUM(1,2), \"quoted\" next line")
        self.assertIn('""quoted""', map_text)
        self.assertTrue(
            all(
                not value.lstrip().startswith(("=", "+", "-", "@"))
                for row in rows
                for value in row.values()
            )
        )
        self.assertTrue(
            all(re.fullmatch(r"\d+\.\d{6}", row["duration_seconds"])
                for row in rows)
        )
        meaning_counts = {
            status: sum(row["runtime_meaning_status"] == status for row in rows)
            for status in {
                "menu_back_route_runtime_unproved",
                "reviewed_label_runtime_meaning_unproved",
                "provisional_label_runtime_meaning_unproved",
            }
        }
        self.assertEqual(
            meaning_counts,
            {
                "menu_back_route_runtime_unproved": 1,
                "reviewed_label_runtime_meaning_unproved": 152,
                "provisional_label_runtime_meaning_unproved": 697,
            },
        )
        self.assertEqual(
            sum(row["legacy_v1_pack_member"] == "true" for row in rows), 153
        )
        self.assertEqual(sum(row["writer_route"] == "menu_back" for row in rows), 1)
        self.assertTrue(all(row["product_edit_status"] == "Editable" for row in rows))
        self.assertNotIn(str(self.root), map_text)
        for forbidden_field in (
            "classification",
            "selector",
            "outer_index",
            "chunk_index",
            "offset",
            "pack_path",
            "source",
            "sha256",
            "payload",
            "resource_body",
            "group_id",
        ):
            self.assertNotIn(forbidden_field, map_text)
        with zipfile.ZipFile(left) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    AUDIO_REPLACEMENT_GUIDE,
                    AUDIO_REPLACEMENT_MANIFEST,
                    AUDIO_CUE_MAP,
                    "replacements/",
                ],
            )
            self.assertEqual(archive.read(AUDIO_CUE_MAP), map_payload)

    def test_v4_one_changed_wav_imports_atomically_and_undoes(self) -> None:
        assets = self._install_complete_standalone_catalog()
        menu_back = assets[0]
        template = self.root / "mapped-complete-edited"
        self.service.export_template(
            template,
            complete_standalone=True,
            with_authoring_map=True,
        )
        supplied = _declared_wav(template)
        supplied.parent.mkdir(exist_ok=True)
        _menu_wav(supplied, -2_468)
        source_before = hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest()

        def authorize(_asset: object, snapshot: object) -> object:
            return SimpleNamespace(
                wav_bytes=snapshot.wav_bytes,  # type: ignore[attr-defined]
                wav_sha256=snapshot.metadata.wav_sha256,  # type: ignore[attr-defined]
            )

        with mock.patch.object(
            self.audio,
            "authorize_replacement_snapshot",
            side_effect=authorize,
        ):
            preview = self.service.preflight_edited(template)
            imported = self.service.import_edited(
                template, confirmation_token=preview.confirmation_token
            )
            self.assertEqual(imported.supplied_count, 1)
            self.assertEqual(imported.changed_count, 1)
            self.assertEqual(self.session.modified_audio_asset_ids, {menu_back.asset_id})
            self.assertEqual(self.session.undo(), "Import audio replacement pack")
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)
        self.assertEqual(
            hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest(), source_before
        )

    def test_v4_refuses_changed_missing_or_extra_map_content_without_mutation(
        self,
    ) -> None:
        self._install_complete_standalone_catalog()
        cases = ("altered", "missing", "extra-row", "extra-file")
        for case in cases:
            with self.subTest(case=case):
                template = self.root / f"mapped-invalid-{case}"
                self.service.export_template(
                    template,
                    complete_standalone=True,
                    with_authoring_map=True,
                )
                cue_map = template / AUDIO_CUE_MAP
                if case == "altered":
                    cue_map.write_bytes(cue_map.read_bytes().replace(b"ordinal", b"orderxx", 1))
                elif case == "missing":
                    cue_map.unlink()
                elif case == "extra-row":
                    cue_map.write_bytes(cue_map.read_bytes() + b"851,unexpected\n")
                else:
                    (template / "UNDECLARED-NOTES.csv").write_text("notes\n")
                before = _file_tree(self.session.root)

                with self.assertRaises(ValidationError):
                    self.service.import_edited(template)
                self.assertEqual(_file_tree(self.session.root), before)
                self.assertEqual(self.session.modified_count, 0)
                self.assertFalse(self.session.can_undo)

    def test_v4_zip_accepts_854_members_and_refuses_855_before_staging(
        self,
    ) -> None:
        self._install_complete_standalone_catalog()
        at_limit = self.root / "mapped-at-member-limit.zip"
        self.service.export_template(
            at_limit,
            container="zip",
            complete_standalone=True,
            with_authoring_map=True,
        )
        with zipfile.ZipFile(at_limit, "r") as archive:
            self.assertEqual(len(archive.infolist()), 4)
            manifest = json.loads(archive.read(AUDIO_REPLACEMENT_MANIFEST))
        with zipfile.ZipFile(at_limit, "a") as archive:
            for row in manifest["assets"]:
                archive.writestr(row["path"], b"x")
        with zipfile.ZipFile(at_limit, "r") as archive:
            self.assertEqual(len(archive.infolist()), MAX_ARCHIVE_MEMBERS)

        with self.assertRaises(ValidationError) as at_limit_error:
            self.service.import_edited(at_limit)
        self.assertNotIn("too many members", str(at_limit_error.exception))
        self.assertEqual(self.session.modified_count, 0)

        over_limit = self.root / "mapped-over-member-limit.zip"
        over_limit.write_bytes(at_limit.read_bytes())
        with zipfile.ZipFile(over_limit, "a") as archive:
            archive.writestr("undeclared-extra.wav", b"x")
        with zipfile.ZipFile(over_limit, "r") as archive:
            self.assertEqual(len(archive.infolist()), MAX_ARCHIVE_MEMBERS + 1)
        with self.assertRaisesRegex(ValidationError, "too many members"):
            self.service.import_edited(over_limit)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_v3_one_changed_wav_imports_atomically_and_undoes(self) -> None:
        assets = self._install_complete_standalone_catalog()
        menu_back = assets[0]
        template = self.root / "complete-edited"
        self.service.export_template(template, complete_standalone=True)
        supplied = _declared_wav(template)
        supplied.parent.mkdir(exist_ok=True)
        _menu_wav(supplied, 2_468)
        source_before = hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest()

        def authorize(_asset: object, snapshot: object) -> object:
            return SimpleNamespace(
                wav_bytes=snapshot.wav_bytes,  # type: ignore[attr-defined]
                wav_sha256=snapshot.metadata.wav_sha256,  # type: ignore[attr-defined]
            )

        with mock.patch.object(
            self.audio,
            "authorize_replacement_snapshot",
            side_effect=authorize,
        ):
            preview = self.service.preflight_edited(template)
            imported = self.service.import_edited(
                template, confirmation_token=preview.confirmation_token
            )
            self.assertEqual(imported.supplied_count, 1)
            self.assertEqual(imported.changed_count, 1)
            self.assertEqual(imported.unchanged_count, 0)
            self.assertEqual(self.session.modified_count, 1)
            self.assertEqual(
                self.session.modified_audio_asset_ids, {menu_back.asset_id}
            )
            self.assertEqual(
                self.session.current_audio_path(menu_back).read_bytes(),
                supplied.read_bytes(),
            )
            self.assertEqual(self.session.undo(), "Import audio replacement pack")
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)
        self.assertEqual(
            hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest(), source_before
        )

    def test_v3_zip_preserves_853_member_pack_below_the_new_v4_ceiling(
        self,
    ) -> None:
        self._install_complete_standalone_catalog()
        at_limit = self.root / "complete-at-member-limit.zip"
        self.service.export_template(
            at_limit,
            container="zip",
            complete_standalone=True,
        )
        with zipfile.ZipFile(at_limit, "r") as archive:
            manifest = json.loads(archive.read(AUDIO_REPLACEMENT_MANIFEST))
        with zipfile.ZipFile(at_limit, "a") as archive:
            for row in manifest["assets"]:
                archive.writestr(row["path"], b"x")
        with zipfile.ZipFile(at_limit, "r") as archive:
            self.assertEqual(len(archive.infolist()), MAX_ARCHIVE_MEMBERS - 1)

        with self.assertRaises(ValidationError) as at_limit_error:
            self.service.import_edited(at_limit)
        self.assertNotIn("too many members", str(at_limit_error.exception))
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

        at_new_limit = self.root / "complete-at-new-member-limit.zip"
        at_new_limit.write_bytes(at_limit.read_bytes())
        with zipfile.ZipFile(at_new_limit, "a") as archive:
            archive.writestr("undeclared-extra.wav", b"x")
        with zipfile.ZipFile(at_new_limit, "r") as archive:
            self.assertEqual(len(archive.infolist()), MAX_ARCHIVE_MEMBERS)
        with self.assertRaises(ValidationError) as at_new_limit_error:
            self.service.import_edited(at_new_limit)
        self.assertNotIn("too many members", str(at_new_limit_error.exception))

        over_limit = self.root / "complete-over-member-limit.zip"
        over_limit.write_bytes(at_new_limit.read_bytes())
        with zipfile.ZipFile(over_limit, "a") as archive:
            archive.writestr("second-undeclared-extra.wav", b"x")
        with zipfile.ZipFile(over_limit, "r") as archive:
            self.assertEqual(len(archive.infolist()), MAX_ARCHIVE_MEMBERS + 1)
        with self.assertRaisesRegex(ValidationError, "too many members"):
            self.service.import_edited(over_limit)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_v3_refuses_malformed_reordered_missing_and_extra_rows_without_mutation(
        self,
    ) -> None:
        self._install_complete_standalone_catalog()
        cases = ("malformed", "reordered", "missing", "extra")
        for case in cases:
            with self.subTest(case=case):
                template = self.root / f"complete-invalid-{case}"
                self.service.export_template(template, complete_standalone=True)
                manifest_path = template / AUDIO_REPLACEMENT_MANIFEST
                document = json.loads(manifest_path.read_text())
                if case == "malformed":
                    document["assets"][0] = "not an asset row"
                elif case == "reordered":
                    document["assets"][0], document["assets"][1] = (
                        document["assets"][1],
                        document["assets"][0],
                    )
                elif case == "missing":
                    document["assets"].pop()
                else:
                    document["assets"].append(dict(document["assets"][-1]))
                manifest_path.write_bytes(audio_pack_module._canonical_json(document))
                before = _file_tree(self.session.root)

                with self.assertRaises(ValidationError):
                    self.service.import_edited(template)
                self.assertEqual(_file_tree(self.session.root), before)
                self.assertEqual(self.session.modified_count, 0)
                self.assertFalse(self.session.can_undo)

    def test_complete_and_selected_export_modes_are_mutually_exclusive(self) -> None:
        destination = self.root / "ambiguous-v3"
        with self.assertRaisesRegex(ValidationError, "either the complete"):
            self.service.export_template(
                destination,
                complete_standalone=True,
                asset_ids=(self.catalog.assets[1].asset_id,),
            )
        self.assertFalse(destination.exists())
        self.assertEqual(self.session.modified_count, 0)

        for label, kwargs in (
            ("map-without-complete", {"with_authoring_map": True}),
            (
                "map-with-selected",
                {
                    "with_authoring_map": True,
                    "asset_ids": (self.catalog.assets[1].asset_id,),
                },
            ),
            (
                "map-complete-and-selected",
                {
                    "complete_standalone": True,
                    "with_authoring_map": True,
                    "asset_ids": (self.catalog.assets[1].asset_id,),
                },
            ),
            ("map-non-boolean", {"with_authoring_map": 1}),
        ):
            with self.subTest(label=label):
                rejected = self.root / f"ambiguous-{label}"
                with self.assertRaises(ValidationError):
                    self.service.export_template(rejected, **kwargs)  # type: ignore[arg-type]
                self.assertFalse(rejected.exists())
                self.assertEqual(self.session.modified_count, 0)

    def test_v3_refuses_invalid_complete_catalog_boundaries_before_publication(
        self,
    ) -> None:
        canonical = self._install_complete_standalone_catalog()
        cases = {
            "incomplete": canonical[:-1],
            "noncanonical": (*canonical[:-2], canonical[-1], canonical[-2]),
            "duplicate-id": (
                *canonical[:-1],
                replace(canonical[-1], asset_id=canonical[-2].asset_id),
            ),
            "duplicate-selector": (
                *canonical[:-1],
                replace(
                    canonical[-1],
                    outer_index=canonical[-2].outer_index,
                    chunk_index=canonical[-2].chunk_index,
                ),
            ),
            "missing-menu-back": (
                replace(
                    canonical[0],
                    asset_id="nfl2k5.audio.audo.o0002.c0000",
                    outer_index=2,
                    chunk_index=0,
                ),
                *canonical[1:],
            ),
            "not-editable": (
                *canonical[:-1],
                replace(canonical[-1], replacement_contract=None),
            ),
        }
        for label, assets in cases.items():
            with self.subTest(label=label):
                self.catalog.assets = assets
                self.catalog._by_id = {  # noqa: SLF001
                    asset.asset_id: asset for asset in assets
                }
                self.catalog._by_selector = {  # noqa: SLF001
                    asset.selector: asset for asset in assets
                }
                destination = self.root / f"invalid-boundary-{label}"
                with self.assertRaises(ValidationError):
                    self.service.export_template(
                        destination, complete_standalone=True
                    )
                self.assertFalse(destination.exists())
                self.assertEqual(self.session.modified_count, 0)

    def test_folder_import_stages_true_changes_once_and_global_undo_restores(self) -> None:
        template = self.root / "edited"
        self.service.export_template(template)
        supplied = _declared_wav(template)
        supplied.parent.mkdir(exist_ok=True)
        _menu_wav(supplied, 1_234)
        source_before = hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest()

        preview = self.service.preflight_edited(template)
        result = self.service.import_edited(
            template, confirmation_token=preview.confirmation_token
        )
        asset = self.catalog.assets[1]
        self.assertEqual(result.supplied_count, 1)
        self.assertEqual(result.changed_count, 1)
        self.assertEqual(result.unchanged_count, 0)
        self.assertEqual(self.session.modified_audio_asset_ids, {asset.asset_id})
        self.assertEqual(self.session.current_audio_path(asset).read_bytes(), supplied.read_bytes())
        self.assertEqual(
            hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest(), source_before
        )
        project = self.root / "authored-audio-only.2k5mod"
        self.session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            wav_members = [name for name in archive.namelist() if name.endswith(".wav")]
            self.assertEqual(len(wav_members), 1)
            self.assertEqual(archive.read(wav_members[0]), supplied.read_bytes())
            self.assertNotEqual(
                archive.read(wav_members[0]), self.audio.ensure_original(asset).read_bytes()
            )
        self.assertEqual(self.session.undo(), "Import audio replacement pack")
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_v2_selected_mixed_pack_is_retail_free_and_one_undo(self) -> None:
        # The first row is alias-related and was Export-only before RC15. It is
        # now safe to author by exact physical identity in a selected v2 pack.
        standalone = self.catalog.assets[0]
        self.assertTrue(standalone.editable)
        self.assertFalse(standalone.legacy_complete_pack_editable)
        streaming = self.catalog.streaming_ranges[0]
        template = self.root / "selected-mixed"

        exported = self.service.export_template(
            template,
            asset_ids=(standalone.asset_id, streaming.asset_id),
        )
        self.assertEqual(exported.asset_count, 2)
        self.assertEqual(exported.menu_back_count, 0)
        self.assertEqual(exported.streaming_range_count, 1)
        self.assertEqual(exported.retail_audio_file_count, 0)
        self.assertEqual(MAX_REPLACEMENT_WAV_BYTES, MAX_AUDIO_REPLACEMENT_WAV_BYTES)
        self.assertEqual(
            {
                path.relative_to(template).as_posix()
                for path in template.rglob("*")
                if path.is_file()
            },
            {AUDIO_REPLACEMENT_GUIDE, AUDIO_REPLACEMENT_MANIFEST},
        )

        manifest_payload = (template / AUDIO_REPLACEMENT_MANIFEST).read_bytes()
        manifest = json.loads(manifest_payload)
        self.assertEqual(
            manifest["schema"], "2k5_mod_studio_audio_replacement_pack/v2"
        )
        self.assertEqual(manifest["schema"], AUDIO_REPLACEMENT_PACK_V2_SCHEMA)
        self.assertEqual(
            [row["asset_id"] for row in manifest["assets"]],
            [standalone.asset_id, streaming.asset_id],
        )
        self.assertEqual(
            set(manifest["assets"][0]),
            {"asset_id", "contract", "logical_aliases", "path", "working_baseline"},
        )
        self.assertEqual(
            manifest["assets"][0]["logical_aliases"],
            {"asset_ids": [standalone.asset_id], "count": 1},
        )
        self.assertEqual(
            manifest["assets"][1]["logical_aliases"],
            {"asset_ids": [streaming.asset_id], "count": 1},
        )
        self.assertEqual(manifest["source"], {"sha256": "f" * 64})
        self.assertNotIn(b"RIFF", manifest_payload)
        public_text = manifest_payload.decode("utf-8")
        self.assertNotIn(str(self.root), public_text)
        for forbidden_key in (
            "physical_id",
            "canonical_id",
            "external_filename",
            "external_outer_index",
            "outer_index",
            "chunk_index",
            "range_start",
            "range_end",
            "offset",
            "fingerprint",
        ):
            self.assertNotIn(f'"{forbidden_key}"', public_text)

        first_path = template.joinpath(*Path(manifest["assets"][0]["path"]).parts)
        second_path = template.joinpath(*Path(manifest["assets"][1]["path"]).parts)
        first_path.parent.mkdir(exist_ok=True)
        _exact_wav(first_path, standalone, 1_234)
        _exact_wav(second_path, streaming, -2_345)
        source_before = hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest()

        preview = self.service.preflight_edited(template)
        imported = self.service.import_edited(
            template, confirmation_token=preview.confirmation_token
        )
        self.assertEqual(imported.supplied_count, 2)
        self.assertEqual(imported.changed_count, 2)
        self.assertEqual(imported.unchanged_count, 0)
        self.assertEqual(self.session.modified_count, 2)
        self.assertEqual(
            self.session.modified_audio_asset_ids,
            {standalone.asset_id, streaming.asset_id},
        )
        self.assertEqual(
            hashlib.sha256(self.fixture.pack0.read_bytes()).hexdigest(), source_before
        )
        self.assertEqual(self.session.undo(), "Import audio replacement pack")
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_v2_invalid_second_wav_leaves_session_byte_identical(self) -> None:
        standalone = self.catalog.assets[1]
        streaming = self.catalog.streaming_ranges[0]
        template = self.root / "invalid-second"
        self.service.export_template(
            template,
            asset_ids=(standalone.asset_id, streaming.asset_id),
        )
        manifest = json.loads((template / AUDIO_REPLACEMENT_MANIFEST).read_text())
        first_path = template.joinpath(*Path(manifest["assets"][0]["path"]).parts)
        second_path = template.joinpath(*Path(manifest["assets"][1]["path"]).parts)
        first_path.parent.mkdir(exist_ok=True)
        _exact_wav(first_path, standalone, 1_111)
        second_path.write_bytes(b"not a WAV")
        before = _file_tree(self.session.root)

        with self.assertRaisesRegex(ValidationError, "needs a canonical"):
            self.service.import_edited(template)
        self.assertEqual(_file_tree(self.session.root), before)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_v2_shared_aliases_collapse_or_reject_atomically(self) -> None:
        first = self.catalog.streaming_ranges[0]
        alias_bank = replace(
            first.bank,
            asset_id="nfl2k5.audio.ausb.o0003.c0103",
            chunk_index=103,
            shared_external_descriptor_count=2,
        )
        alias = Nfl2k5StreamingAudioRange(
            alias_bank, first.range_index, first.start, first.end
        )
        self.catalog.streaming_banks += (alias_bank,)
        self.catalog._streaming_by_id[alias_bank.asset_id] = alias_bank  # noqa: SLF001
        self.catalog.streaming_ranges += (alias,)
        self.catalog._streaming_range_by_id[alias.asset_id] = alias  # noqa: SLF001
        for private in (self.fixture.cache.root / "derived").glob(
            "audio-source-pcm-*.json"
        ):
            private.unlink()
        self.fixture._ensure_private_audio_inventories(self.catalog)  # noqa: SLF001

        template = self.root / "selected-aliases"
        self.service.export_template(
            template, asset_ids=(first.asset_id, alias.asset_id)
        )
        manifest = json.loads((template / AUDIO_REPLACEMENT_MANIFEST).read_text())
        expected_aliases = [first.asset_id, alias.asset_id]
        for row in manifest["assets"]:
            self.assertEqual(
                row["logical_aliases"],
                {"asset_ids": expected_aliases, "count": 2},
            )
        first_path = template.joinpath(*Path(manifest["assets"][0]["path"]).parts)
        second_path = template.joinpath(*Path(manifest["assets"][1]["path"]).parts)
        first_path.parent.mkdir(exist_ok=True)
        _exact_wav(first_path, first, 2_222)
        _exact_wav(second_path, alias, -3_333)
        before = _file_tree(self.session.root)

        with self.assertRaisesRegex(ValidationError, "different WAVs"):
            self.service.import_edited(template)
        self.assertEqual(_file_tree(self.session.root), before)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

        second_path.write_bytes(first_path.read_bytes())
        preview = self.service.preflight_edited(template)
        self.assertEqual(preview.supplied_count, 2)
        self.assertEqual(preview.would_change_count, 2)
        self.assertEqual(preview.unique_physical_change_count, 1)
        self.assertEqual(preview.affected_alias_count, 1)
        self.assertEqual(preview.resulting_modified_count, 2)
        self.assertEqual(
            preview.changed_rows[0].affected_asset_ids,
            (first.asset_id, alias.asset_id),
        )
        imported = self.service.import_edited(
            template, confirmation_token=preview.confirmation_token
        )
        self.assertEqual(imported.supplied_count, 2)
        self.assertEqual(imported.changed_count, 2)
        self.assertEqual(imported.unchanged_count, 0)
        self.assertEqual(self.session.modified_count, 1)
        self.assertEqual(
            self.session.modified_audio_asset_ids,
            {first.asset_id, alias.asset_id},
        )
        self.assertEqual(self.session.undo(), "Import audio replacement pack")
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_v2_rejects_invalid_selected_ids_before_publication(self) -> None:
        editable = self.catalog.assets[1].asset_id
        cases: tuple[tuple[str, Sequence[str]], ...] = (
            ("empty", ()),
            (
                "over-limit",
                tuple(f"nfl2k5.audio.synthetic.{index:03d}"
                      for index in range(MAX_SELECTED_AUDIO_COUNT + 1)),
            ),
            ("unknown", ("nfl2k5.audio.unknown",)),
            ("duplicate", (editable, editable)),
            ("whole-bank", (self.catalog.streaming_banks[0].asset_id,)),
        )
        for label, asset_ids in cases:
            with self.subTest(label=label):
                destination = self.root / f"rejected-{label}"
                with self.assertRaises(ValidationError):
                    self.service.export_template(
                        destination, asset_ids=asset_ids
                    )
                self.assertFalse(destination.exists())
                self.assertEqual(self.session.modified_count, 0)
                self.assertFalse(self.session.can_undo)

    def test_folder_export_race_preserves_foreign_destination(self) -> None:
        before_reservation = self.root / "before-reservation"

        def create_before_reservation(
            stage: str, _completed: int, _total: int
        ) -> None:
            if stage == "Publishing retail-free audio template":
                before_reservation.mkdir()

        with self.assertRaisesRegex(ValidationError, "already exists"):
            self.service.export_template(
                before_reservation,
                container="folder",
                progress=create_before_reservation,
            )
        self.assertTrue(before_reservation.is_dir())
        self.assertEqual(tuple(before_reservation.iterdir()), ())

    def test_folder_export_final_rename_refuses_raced_destination(self) -> None:
        destination = self.root / "final-call-race"
        real_rename_noreplace = audio_pack_module._rename_noreplace
        reached_final_call = False

        def race_at_final_call(
            parent_descriptor: object, source_name: str, destination_name: str
        ) -> None:
            nonlocal reached_final_call
            reached_final_call = True
            flags = (
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
            ) | getattr(os, "O_BINARY", 0)
            destination_handle = None
            if isinstance(parent_descriptor, int):
                os.mkdir(destination_name, mode=0o700, dir_fd=parent_descriptor)
                marker = os.open(
                    f"{destination_name}/foreign.txt",
                    flags,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            else:
                parent_descriptor.mkdir(destination_name, 0o700)  # type: ignore[attr-defined]
                destination_handle = parent_descriptor.open_dir(  # type: ignore[attr-defined]
                    destination_name
                )
                marker = destination_handle.open("foreign.txt", flags, 0o600)
            try:
                os.write(marker, b"foreign destination survives")
            finally:
                os.close(marker)
                if destination_handle is not None:
                    destination_handle.close()
            real_rename_noreplace(
                parent_descriptor, source_name, destination_name
            )  # type: ignore[arg-type]

        with (
            mock.patch.object(
                audio_pack_module,
                "_rename_noreplace",
                side_effect=race_at_final_call,
            ),
            self.assertRaisesRegex(ValidationError, "already exists"),
        ):
            self.service.export_template(destination, container="folder")
        self.assertTrue(reached_final_call)
        self.assertEqual(
            (destination / "foreign.txt").read_bytes(),
            b"foreign destination survives",
        )
        self.assertFalse(
            any(path.name.startswith(f".{destination.name}.audio-pack-")
                for path in self.root.iterdir())
        )

    def test_descriptor_reader_is_maximum_plus_one_bounded_and_rejects_links(
        self,
    ) -> None:
        supplied = self.root / "bounded.bin"
        supplied.write_bytes(b"descriptor payload")
        real_fdopen = audio_pack_module.os.fdopen
        requested_sizes: list[int] = []

        class RecordingReader:
            def __init__(self, stream: object) -> None:
                self.stream = stream

            def __enter__(self) -> "RecordingReader":
                self.stream.__enter__()  # type: ignore[attr-defined]
                return self

            def __exit__(self, *args: object) -> object:
                return self.stream.__exit__(*args)  # type: ignore[attr-defined]

            def read(self, size: int) -> bytes:
                requested_sizes.append(size)
                return self.stream.read(size)  # type: ignore[attr-defined,no-any-return]

            def fileno(self) -> int:
                return self.stream.fileno()  # type: ignore[attr-defined,no-any-return]

        def recording_fdopen(*args: object, **kwargs: object) -> RecordingReader:
            return RecordingReader(real_fdopen(*args, **kwargs))

        with mock.patch.object(
            audio_pack_module.os, "fdopen", side_effect=recording_fdopen
        ):
            payload = audio_pack_module._read_regular_file(
                supplied, "Bounded fixture", maximum=64
            )
        self.assertEqual(payload, b"descriptor payload")
        self.assertEqual(requested_sizes, [65])

        linked = self.root / "hard-linked.bin"
        os.link(supplied, linked)
        with self.assertRaisesRegex(ValidationError, "hard-linked"):
            audio_pack_module._read_regular_file(
                supplied, "Bounded fixture", maximum=64
            )
        linked.unlink()
        symbolic = self.root / "symbolic.bin"
        symbolic.symlink_to(supplied)
        with self.assertRaisesRegex(ValidationError, "folder or link"):
            audio_pack_module._read_regular_file(
                symbolic, "Bounded fixture", maximum=64
            )
        oversized = self.root / "oversized.bin"
        oversized.write_bytes(b"x" * 65)
        with self.assertRaisesRegex(ValidationError, "empty or too large"):
            audio_pack_module._read_regular_file(
                oversized, "Bounded fixture", maximum=64
            )

    def test_folder_import_rejects_oversized_guide_without_staging(self) -> None:
        template = self.root / "oversized-guide"
        self.service.export_template(template)
        guide = template / AUDIO_REPLACEMENT_GUIDE
        with guide.open("r+b") as stream:
            stream.truncate(MAX_MANIFEST_BYTES + 1)

        with self.assertRaisesRegex(ValidationError, "empty or too large"):
            self.service.import_edited(template)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

    def test_main_facade_pins_catalog_and_session_for_export_and_import(self) -> None:
        calls: list[tuple[object, object]] = []

        def factory(catalog: object, session: object) -> AudioReplacementPackService:
            calls.append((catalog, session))
            return self.service

        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
            audio_replacement_pack_factory=factory,  # type: ignore[arg-type]
        )
        facade._cache = self.fixture.cache
        facade._audio_catalog = self.catalog
        facade._audio_service = self.audio
        facade._session = self.session
        self.assertEqual(
            facade.audio_complete_pack_path(self.catalog.assets[0].asset_id),
            "replacements/001__selected-audio.wav",
        )
        self.assertIsNone(facade.audio_complete_pack_path("unknown"))
        template = self.root / "facade-template"
        selected_ids = (self.catalog.assets[1].asset_id,)
        exported = facade.export_audio_replacement_template(
            template,
            container="folder",
            progress=lambda *_args: None,
            asset_ids=selected_ids,
        )
        self.assertEqual(exported.path, template.resolve())
        self.assertEqual(
            json.loads((template / AUDIO_REPLACEMENT_MANIFEST).read_text())["schema"],
            AUDIO_REPLACEMENT_PACK_V2_SCHEMA,
        )
        supplied = _declared_wav(template)
        supplied.parent.mkdir(exist_ok=True)
        _menu_wav(supplied, 321)
        # First-use preparation/race binding has a dedicated facade suite; this
        # test isolates that the pack factory receives the exact pinned objects.
        with mock.patch.object(facade, "prepare_audio_editing"):
            preview = facade.preflight_audio_replacement_pack(
                template, lambda *_args: None
            )
            imported = facade.import_audio_replacement_pack(
                template,
                lambda *_args: None,
                confirmation_token=preview.confirmation_token,
            )
        self.assertIsInstance(preview, AudioReplacementPackPreflightResult)
        self.assertEqual(imported.changed_count, 1)
        self.assertEqual(
            calls,
            [
                (self.catalog, self.session),
                (self.catalog, self.session),
                (self.catalog, self.session),
            ],
        )

    def test_main_facade_forwards_complete_standalone_mode_without_gui_ids(
        self,
    ) -> None:
        service = mock.Mock()
        destination = self.root / "complete-facade.zip"
        expected = SimpleNamespace(path=destination)
        service.export_template.return_value = expected
        factory_calls: list[tuple[object, object]] = []

        def factory(catalog: object, session: object) -> object:
            factory_calls.append((catalog, session))
            return service

        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
            audio_replacement_pack_factory=factory,  # type: ignore[arg-type]
        )
        facade._cache = self.fixture.cache
        facade._audio_catalog = self.catalog
        facade._audio_service = self.audio
        facade._session = self.session

        progress = lambda *_args: None
        result = facade.export_audio_replacement_template(
            destination,
            container="zip",
            progress=progress,
            complete_standalone=True,
            asset_ids=None,
        )

        self.assertIs(result, expected)
        self.assertEqual(factory_calls, [(self.catalog, self.session)])
        service.export_template.assert_called_once_with(
            destination,
            container="zip",
            progress=progress,
            complete_standalone=True,
            asset_ids=None,
        )

        service.export_template.reset_mock()
        selected_ids = (self.catalog.assets[1].asset_id,)
        facade.export_audio_replacement_template(
            destination,
            container="zip",
            progress=progress,
            asset_ids=selected_ids,
        )
        service.export_template.assert_called_once_with(
            destination,
            container="zip",
            progress=progress,
            asset_ids=selected_ids,
        )

        service.export_template.reset_mock()
        facade.export_audio_replacement_template(
            destination,
            container="zip",
            progress=progress,
            asset_ids=None,
        )
        service.export_template.assert_called_once_with(
            destination,
            container="zip",
            progress=progress,
            asset_ids=None,
        )

        service.export_template.reset_mock()
        facade.export_audio_replacement_template(
            destination,
            container="zip",
            progress=progress,
            complete_standalone=True,
            asset_ids=selected_ids,
        )
        service.export_template.assert_called_once_with(
            destination,
            container="zip",
            progress=progress,
            complete_standalone=True,
            asset_ids=selected_ids,
        )

    def test_edited_zip_import_uses_the_same_atomic_contract(self) -> None:
        template = self.root / "edited.zip"
        self.service.export_template(template, container="zip")
        with zipfile.ZipFile(template, "r") as archive:
            manifest = json.loads(archive.read(AUDIO_REPLACEMENT_MANIFEST))
        authored = _menu_wav(self.root / "authored.wav", 777).read_bytes()
        with zipfile.ZipFile(template, "a") as archive:
            archive.writestr(manifest["assets"][0]["path"], authored)

        preview = self.service.preflight_edited(template)
        result = self.service.import_edited(
            template, confirmation_token=preview.confirmation_token
        )
        self.assertEqual(result.changed_count, 1)
        self.assertEqual(result.path, template.resolve())
        self.assertEqual(self.session.undo(), "Import audio replacement pack")
        self.assertEqual(self.session.modified_count, 0)

    def test_pack_can_restore_source_audio_and_undo_recovers_the_user_wav(self) -> None:
        asset = self.catalog.assets[1]
        authored = _menu_wav(self.root / "first-user.wav", 555)
        self.session.replace_audio(asset, authored)
        template = self.root / "restore-pack"
        self.service.export_template(template)
        supplied = _declared_wav(template)
        supplied.parent.mkdir(exist_ok=True)
        supplied.write_bytes(self.audio.ensure_original(asset).read_bytes())

        preview = self.service.preflight_edited(template)
        result = self.service.import_edited(
            template, confirmation_token=preview.confirmation_token
        )
        self.assertEqual(result.changed_count, 1)
        self.assertEqual(result.modified_count, 0)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.undo(), "Import audio replacement pack")
        self.assertEqual(self.session.current_audio_path(asset).read_bytes(), authored.read_bytes())

    def test_unknown_invalid_duplicate_stale_and_unchanged_only_packs_never_partially_stage(
        self,
    ) -> None:
        asset = self.catalog.assets[1]

        unknown = self.root / "unknown"
        self.service.export_template(unknown)
        wav = _declared_wav(unknown)
        wav.parent.mkdir(exist_ok=True)
        _menu_wav(wav, 10)
        (unknown / "surprise.wav").write_bytes(b"RIFF unknown")
        with self.assertRaisesRegex(ValidationError, "undeclared or unknown"):
            self.service.import_edited(unknown)
        self.assertEqual(self.session.modified_count, 0)

        (unknown / "surprise.wav").unlink()
        wav.write_bytes(b"not a WAV")
        with self.assertRaisesRegex(ValidationError, "[Mm]enu(?:-| )Back.*needs"):
            self.service.import_edited(unknown)
        self.assertEqual(self.session.modified_count, 0)

        empty_directory = self.root / "empty-directory"
        self.service.export_template(empty_directory)
        empty_wav = _declared_wav(empty_directory)
        empty_wav.parent.mkdir(exist_ok=True)
        _menu_wav(empty_wav, 20)
        (empty_directory / "editor-backups").mkdir()
        with self.assertRaisesRegex(ValidationError, "unknown directory"):
            self.service.import_edited(empty_directory)
        self.assertEqual(self.session.modified_count, 0)

        unchanged = self.root / "unchanged"
        self.service.export_template(unchanged)
        original = self.audio.ensure_original(asset).read_bytes()
        unchanged_wav = _declared_wav(unchanged)
        unchanged_wav.parent.mkdir(exist_ok=True)
        unchanged_wav.write_bytes(original)
        with self.assertRaisesRegex(ValidationError, "already matches the current project"):
            self.service.import_edited(unchanged)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

        duplicate = self.root / "duplicate.zip"
        self.service.export_template(duplicate, container="zip")
        with zipfile.ZipFile(duplicate, "a") as archive:
            with self.assertWarns(UserWarning):
                archive.writestr(
                    AUDIO_REPLACEMENT_MANIFEST,
                    archive.read(AUDIO_REPLACEMENT_MANIFEST),
                )
        with self.assertRaisesRegex(ValidationError, "duplicate paths"):
            self.service.import_edited(duplicate)
        self.assertEqual(self.session.modified_count, 0)

        corrupt = self.root / "corrupt.zip"
        self.service.export_template(corrupt, container="zip")
        with zipfile.ZipFile(corrupt, "r") as archive:
            member = archive.getinfo(AUDIO_REPLACEMENT_MANIFEST)
            filename_size = len(member.filename.encode("utf-8"))
            data_offset = member.header_offset + 30 + filename_size + len(member.extra)
        damaged = bytearray(corrupt.read_bytes())
        damaged[data_offset] ^= 0x01
        corrupt.write_bytes(damaged)
        with self.assertRaisesRegex(ValidationError, "Could not read audio pack ZIP member"):
            self.service.import_edited(corrupt)
        self.assertEqual(self.session.modified_count, 0)

        stale = self.root / "stale"
        self.service.export_template(stale)
        stale_wav = _declared_wav(stale)
        stale_wav.parent.mkdir(exist_ok=True)
        _menu_wav(stale_wav, 30)
        current = _menu_wav(self.root / "newer.wav", 40)
        self.session.replace_audio(asset, current)
        with self.assertRaisesRegex(ValidationError, "state changed after"):
            self.service.import_edited(stale)
        self.assertEqual(self.session.current_audio_path(asset).read_bytes(), current.read_bytes())

    def test_preflight_is_frozen_read_only_and_confirmation_revalidates(self) -> None:
        asset = self.catalog.assets[1]
        template = self.root / "preflight-selected"
        self.service.export_template(template, asset_ids=(asset.asset_id,))
        supplied = _declared_wav(template)
        supplied.parent.mkdir(exist_ok=True)
        _exact_wav(supplied, asset, 1_357)
        before = _file_tree(self.session.root)
        revision = self.session.mutation_revision

        preview = self.service.preflight_edited(template)

        self.assertIsInstance(preview, AudioReplacementPackPreflightResult)
        self.assertEqual(preview.schema, AUDIO_REPLACEMENT_PACK_V2_SCHEMA)
        self.assertEqual(preview.pack_kind, "selected_audio")
        self.assertEqual(preview.supplied_count, 1)
        self.assertEqual(preview.would_change_count, 1)
        self.assertEqual(preview.unique_physical_change_count, 1)
        self.assertEqual(preview.already_current_count, 0)
        self.assertEqual(preview.would_restore_original_count, 0)
        self.assertEqual(preview.unique_physical_restore_count, 0)
        self.assertEqual(preview.affected_alias_count, 0)
        self.assertEqual(preview.resulting_modified_count, 1)
        self.assertTrue(preview.can_apply)
        self.assertEqual(len(preview.changed_rows), 1)
        self.assertEqual(preview.changed_rows[0].asset_id, asset.asset_id)
        self.assertEqual(preview.changed_rows[0].action, "stage_replacement")
        self.assertEqual(preview.changed_rows[0].affected_asset_ids, (asset.asset_id,))
        self.assertEqual(preview.omitted_changed_count, 0)
        self.assertRegex(preview.confirmation_token, r"^2k5apf1\.[0-9a-f]{64}$")
        self.assertNotIn(str(self.root), preview.confirmation_token)
        self.assertNotIn(self.fixture.cache.source.sha256, preview.confirmation_token)
        self.assertNotIn(hashlib.sha256(supplied.read_bytes()).hexdigest(),
                         preview.confirmation_token)
        self.assertNotIn(preview.confirmation_token, repr(preview))
        self.assertFalse(hasattr(preview, "path"))
        self.assertEqual(_file_tree(self.session.root), before)
        self.assertEqual(self.session.mutation_revision, revision)
        self.assertEqual(self.session.modified_count, 0)
        self.assertFalse(self.session.can_undo)

        with self.assertRaisesRegex(ValidationError, "Preview.*confirm"):
            self.service.import_edited(template)
        self.assertEqual(_file_tree(self.session.root), before)
        self.assertEqual(self.session.mutation_revision, revision)
        self.assertFalse(self.session.can_undo)

        imported = self.service.import_edited(
            template, confirmation_token=preview.confirmation_token
        )
        self.assertEqual(imported.changed_count, 1)
        self.assertEqual(self.session.modified_audio_asset_ids, {asset.asset_id})
        self.assertGreater(self.session.mutation_revision, revision)

    def test_preflight_reports_already_current_and_restore_without_mutation(self) -> None:
        asset = self.catalog.assets[1]
        authored = self.root / "initial-author.wav"
        _exact_wav(authored, asset, -1_246)
        self.session.replace_audio(asset, authored)

        unchanged_pack = self.root / "preflight-unchanged"
        self.service.export_template(
            unchanged_pack, asset_ids=(asset.asset_id,)
        )
        unchanged_wav = _declared_wav(unchanged_pack)
        unchanged_wav.parent.mkdir(exist_ok=True)
        unchanged_wav.write_bytes(authored.read_bytes())
        before = _file_tree(self.session.root)
        revision = self.session.mutation_revision
        unchanged = self.service.preflight_edited(unchanged_pack)
        self.assertFalse(unchanged.can_apply)
        self.assertEqual(unchanged.would_change_count, 0)
        self.assertEqual(unchanged.already_current_count, 1)
        self.assertEqual(unchanged.resulting_modified_count, 1)
        self.assertEqual(unchanged.changed_rows, ())
        self.assertEqual(_file_tree(self.session.root), before)
        self.assertEqual(self.session.mutation_revision, revision)

        restore_pack = self.root / "preflight-restore"
        self.service.export_template(restore_pack, asset_ids=(asset.asset_id,))
        restore_wav = _declared_wav(restore_pack)
        restore_wav.parent.mkdir(exist_ok=True)
        restore_wav.write_bytes(self.audio.audio_original_path(asset).read_bytes())
        before_restore = _file_tree(self.session.root)
        restore = self.service.preflight_edited(restore_pack)
        self.assertTrue(restore.can_apply)
        self.assertEqual(restore.would_change_count, 1)
        self.assertEqual(restore.would_restore_original_count, 1)
        self.assertEqual(restore.unique_physical_restore_count, 1)
        self.assertEqual(restore.resulting_modified_count, 0)
        self.assertEqual(restore.changed_rows[0].action, "restore_original")
        self.assertEqual(_file_tree(self.session.root), before_restore)
        imported = self.service.import_edited(
            restore_pack, confirmation_token=restore.confirmation_token
        )
        self.assertEqual(imported.changed_count, 1)
        self.assertEqual(imported.modified_count, 0)
        self.assertEqual(self.session.modified_audio_asset_ids, frozenset())

    def test_preflight_token_rejects_pack_project_and_session_changes(self) -> None:
        selected = self.catalog.assets[1]
        template = self.root / "token-bound"
        self.service.export_template(template, asset_ids=(selected.asset_id,))
        supplied = _declared_wav(template)
        supplied.parent.mkdir(exist_ok=True)
        _exact_wav(supplied, selected, 1_111)
        preview = self.service.preflight_edited(template)
        before = _file_tree(self.session.root)

        _exact_wav(supplied, selected, 2_222)
        with self.assertRaisesRegex(ValidationError, "changed after preflight"):
            self.service.import_edited(
                template, confirmation_token=preview.confirmation_token
            )
        self.assertEqual(_file_tree(self.session.root), before)

        _exact_wav(supplied, selected, 1_111)
        project_preview = self.service.preflight_edited(template)
        other = self.catalog.assets[0]
        other_wav = self.root / "other-project-change.wav"
        _exact_wav(other_wav, other, -2_222)
        self.session.replace_audio(other, other_wav)
        after_project_change = _file_tree(self.session.root)
        with self.assertRaisesRegex(ValidationError, "changed after preflight"):
            self.service.import_edited(
                template, confirmation_token=project_preview.confirmation_token
            )
        self.assertEqual(_file_tree(self.session.root), after_project_change)

        second_session = StudioSession(
            self.fixture.cache,
            object(),
            root=self.root / "sessions",
            session_id="second-preflight-session",
        )
        second_session.attach_audio_service(self.audio)
        second_service = AudioReplacementPackService(
            self.catalog, second_session, expected_editable_count=1
        )
        with self.assertRaisesRegex(ValidationError, "changed after preflight"):
            second_service.import_edited(
                template, confirmation_token=preview.confirmation_token
            )
        self.assertEqual(second_session.modified_count, 0)
        self.assertFalse(second_session.can_undo)

    def test_preflight_bounds_changed_rows_and_runs_origin_gate(self) -> None:
        standalone = self.catalog.assets[1]
        streaming = self.catalog.streaming_ranges[0]
        template = self.root / "bounded-preflight"
        self.service.export_template(
            template, asset_ids=(standalone.asset_id, streaming.asset_id)
        )
        manifest = json.loads((template / AUDIO_REPLACEMENT_MANIFEST).read_text())
        first = template.joinpath(*Path(manifest["assets"][0]["path"]).parts)
        second = template.joinpath(*Path(manifest["assets"][1]["path"]).parts)
        first.parent.mkdir(exist_ok=True)
        _exact_wav(first, standalone, 1_010)
        _exact_wav(second, streaming, -2_020)
        before = _file_tree(self.session.root)
        revision = self.session.mutation_revision

        with mock.patch.object(audio_pack_module, "MAX_PREFLIGHT_CHANGED_ROWS", 1):
            preview = self.service.preflight_edited(template)
        self.assertEqual(MAX_PREFLIGHT_CHANGED_ROWS, 32)
        self.assertEqual(preview.supplied_count, 2)
        self.assertEqual(preview.would_change_count, 2)
        self.assertEqual(preview.unique_physical_change_count, 2)
        self.assertEqual(len(preview.changed_rows), 1)
        self.assertEqual(preview.omitted_changed_count, 1)
        self.assertEqual(_file_tree(self.session.root), before)
        self.assertEqual(self.session.mutation_revision, revision)

        with (
            mock.patch.object(
                self.audio,
                "authorize_replacement_snapshot",
                side_effect=ValidationError("synthetic origin rejection"),
            ),
            self.assertRaisesRegex(ValidationError, "origin rejection"),
        ):
            self.service.preflight_edited(template)
        self.assertEqual(_file_tree(self.session.root), before)
        self.assertEqual(self.session.mutation_revision, revision)


@dataclass(frozen=True)
class _FakeAsset:
    asset_id: str
    name: str
    editable: bool = True


class _FakeCatalog:
    def __init__(self, assets: tuple[_FakeAsset, ...]) -> None:
        self.assets = assets
        self._by_id = {asset.asset_id: asset for asset in assets}

    def get_asset(self, value: object) -> _FakeAsset:
        asset_id = value.asset_id if hasattr(value, "asset_id") else value
        try:
            selected = self._by_id[asset_id]
        except (KeyError, TypeError) as exc:
            raise ValidationError(f"Unknown fake audio asset: {asset_id}") from exc
        if hasattr(value, "asset_id") and value != selected:
            raise ValidationError("Foreign fake audio metadata")
        return selected


class _FakeAudioService:
    def __init__(self, cache: object, root: Path) -> None:
        self.cache = cache
        self.catalog = _FakeCatalog((
            _FakeAsset("audio.a", "Cue A"),
            _FakeAsset("audio.b", "Cue B"),
        ))
        self.originals: dict[str, Path] = {}
        for asset in self.catalog.assets:
            path = root / f"original-{asset.asset_id}.wav"
            path.write_bytes(f"RIFF-original-{asset.asset_id}".encode())
            self.originals[asset.asset_id] = path

    def validate_replacement(self, asset: object, path: Path) -> object:
        selected = self.catalog.get_asset(asset)
        supplied = Path(path)
        if supplied.suffix != ".wav" or not supplied.is_file() or supplied.is_symlink():
            raise ValidationError(f"Bad WAV for {selected.name}")
        payload = supplied.read_bytes()
        if not payload.startswith(b"RIFF-"):
            raise ValidationError(f"Bad WAV for {selected.name}")
        return SimpleNamespace(
            wav_path=supplied.resolve(),
            wav_size=len(payload),
            wav_sha256=hashlib.sha256(payload).hexdigest(),
        )

    def validate_user_replacement(self, asset: object, path: Path) -> object:
        metadata = self.validate_replacement(asset, path)
        payload = metadata.wav_path.read_bytes()
        for original in self.originals.values():
            if payload == original.read_bytes():
                raise ValidationError(
                    "Retail-derived audio cannot be stored in a shareable project"
                )
        return metadata

    def ensure_original(self, asset: object) -> Path:
        return self.originals[self.catalog.get_asset(asset).asset_id]


class AudioBatchSessionAtomicTests(unittest.TestCase):
    def test_cross_cue_source_audio_cannot_stage_save_or_load(self) -> None:
        with tempfile.TemporaryDirectory(prefix="audio-source-boundary-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            fixture = AudioFixture(source)
            service = _FakeAudioService(fixture.cache, root)
            session = StudioSession(
                fixture.cache, object(), root=root / "sessions", session_id="source"
            )
            session.attach_audio_service(service)  # type: ignore[arg-type]
            first, second = service.catalog.assets
            cross_cue = service.ensure_original(first)

            with self.assertRaisesRegex(ValidationError, "Retail-derived audio"):
                session.replace_audio(second, cross_cue)
            with self.assertRaisesRegex(ValidationError, "Retail-derived audio"):
                session.replace_audio_batch(((second, cross_cue),))
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)

            unsafe = session.replacements / "legacy-cross-cue.wav"
            unsafe.write_bytes(cross_cue.read_bytes())
            digest = hashlib.sha256(unsafe.read_bytes()).hexdigest()
            session._audio_edits[second.asset_id] = AudioSessionEdit(  # noqa: SLF001
                second.asset_id, unsafe, digest
            )
            with self.assertRaisesRegex(ValidationError, "Retail-derived audio"):
                session.save_shareable_project(root / "unsafe-save.2k5mod")
            session._audio_edits.clear()  # noqa: SLF001
            unsafe.unlink()

            archive = root / "unsafe-load.2k5mod"
            valid_first = root / "valid-first.wav"
            valid_first.write_bytes(b"RIFF-user-audio.a-shareable")
            save_project_archive(
                catalog=object(),
                asset_io=object(),
                edits=(),
                destination=archive,
                audio_edits=(
                    SimpleNamespace(
                        asset_id=first.asset_id,
                        replacement_path=valid_first,
                        replacement_sha256=hashlib.sha256(
                            valid_first.read_bytes()
                        ).hexdigest(),
                    ),
                    SimpleNamespace(
                        asset_id=second.asset_id,
                        replacement_path=cross_cue,
                        replacement_sha256=hashlib.sha256(
                            cross_cue.read_bytes()
                        ).hexdigest(),
                    ),
                ),
            )
            with self.assertRaisesRegex(ValidationError, "Retail-derived audio"):
                session.load_shareable_project(archive)
            self.assertEqual(session.modified_count, 0)

    def test_post_validation_staged_state_mutation_is_never_imported_over(self) -> None:
        with tempfile.TemporaryDirectory(prefix="audio-baseline-race-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            fixture = AudioFixture(source)
            service = _FakeAudioService(fixture.cache, root)
            session = StudioSession(
                fixture.cache, object(), root=root / "sessions", session_id="race"
            )
            session.attach_audio_service(service)  # type: ignore[arg-type]
            first = service.catalog.assets[0]
            initial = root / "initial.wav"
            initial.write_bytes(b"RIFF-user-audio.initial")
            incoming = root / "incoming.wav"
            incoming.write_bytes(b"RIFF-user-audio.incoming")
            session.replace_audio(first, initial)
            destination = session.current_audio_path(first)
            manifest_before = (session.root / "session.json").read_bytes()
            raced_payload = b"RIFF-user-audio.external-race"
            real_validate = service.validate_user_replacement
            mutation_happened = False

            def mutate_after_transaction_validation(
                asset: object, path: Path
            ) -> object:
                nonlocal mutation_happened
                result = real_validate(asset, path)
                if (
                    not mutation_happened
                    and Path(path).name.startswith(".audio-pack-")
                ):
                    destination.write_bytes(raced_payload)
                    mutation_happened = True
                return result

            with (
                mock.patch.object(
                    service,
                    "validate_user_replacement",
                    side_effect=mutate_after_transaction_validation,
                ),
                self.assertRaisesRegex(ValidationError, "changed after validation"),
            ):
                session.replace_audio_batch(((first, incoming),))

            self.assertTrue(mutation_happened)
            self.assertEqual(destination.read_bytes(), raced_payload)
            self.assertNotEqual(destination.read_bytes(), incoming.read_bytes())
            self.assertEqual(
                (session.root / "session.json").read_bytes(), manifest_before
            )
            self.assertEqual(session.modified_audio_asset_ids, {first.asset_id})
            self.assertFalse(
                any(
                    path.name.startswith(".audio-pack-")
                    for path in session.replacements.iterdir()
                )
            )

    def test_snapshot_interposition_refuses_commit_and_keeps_undo_unchanged(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="audio-snapshot-race-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            fixture = AudioFixture(source)
            service = _FakeAudioService(fixture.cache, root)
            session = StudioSession(
                fixture.cache, object(), root=root / "sessions", session_id="snapshot"
            )
            session.attach_audio_service(service)  # type: ignore[arg-type]
            first = service.catalog.assets[0]
            baseline_a = root / "baseline-a.wav"
            baseline_a.write_bytes(b"RIFF-user-audio.baseline-a")
            incoming_b = root / "incoming-b.wav"
            incoming_b.write_bytes(b"RIFF-user-audio.incoming-b")
            session.replace_audio(first, baseline_a)
            destination = session.current_audio_path(first)
            raced_c = b"RIFF-user-audio.raced-c"
            edits_before = dict(session._audio_edits)  # noqa: SLF001
            undo_before = tuple(session._audio_undo)  # noqa: SLF001
            order_before = tuple(session._undo_order)  # noqa: SLF001
            sequence_before = session._history_sequence  # noqa: SLF001
            manifest_before = (session.root / "session.json").read_bytes()
            history_before = tuple(sorted(session.history.iterdir()))
            real_snapshot = session._snapshot_audio  # noqa: SLF001
            mutation_happened = False

            def mutate_inside_snapshot(asset_id: str) -> Path | None:
                nonlocal mutation_happened
                destination.write_bytes(raced_c)
                mutation_happened = True
                return real_snapshot(asset_id)

            with (
                mock.patch.object(
                    session,
                    "_snapshot_audio",
                    side_effect=mutate_inside_snapshot,
                ),
                self.assertRaisesRegex(ValidationError, "changed after validation"),
            ):
                session.replace_audio_batch(((first, incoming_b),))

            self.assertTrue(mutation_happened)
            self.assertEqual(destination.read_bytes(), raced_c)
            self.assertNotEqual(destination.read_bytes(), incoming_b.read_bytes())
            self.assertEqual(session._audio_edits, edits_before)  # noqa: SLF001
            self.assertEqual(tuple(session._audio_undo), undo_before)  # noqa: SLF001
            self.assertEqual(tuple(session._undo_order), order_before)  # noqa: SLF001
            self.assertEqual(session._history_sequence, sequence_before)  # noqa: SLF001
            self.assertEqual(
                (session.root / "session.json").read_bytes(), manifest_before
            )
            self.assertEqual(tuple(sorted(session.history.iterdir())), history_before)
            self.assertFalse(
                any(
                    path.name.startswith(".audio-pack-")
                    for path in session.replacements.iterdir()
                )
            )

    def test_validate_all_single_undo_duplicate_and_commit_rollback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="audio-batch-session-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            fixture = AudioFixture(source)
            service = _FakeAudioService(fixture.cache, root)
            session = StudioSession(
                fixture.cache, object(), root=root / "sessions", session_id="batch"
            )
            session.attach_audio_service(service)  # type: ignore[arg-type]
            first, second = service.catalog.assets
            a1 = root / "a1.wav"
            a1.write_bytes(b"RIFF-user-audio.a-one")
            b1 = root / "b1.wav"
            b1.write_bytes(b"RIFF-user-audio.b-one")
            bad = root / "bad.wav"
            bad.write_bytes(b"broken")

            with self.assertRaisesRegex(ValidationError, "Bad WAV for Cue B"):
                session.replace_audio_batch(((first, a1), (second, bad)))
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)
            with self.assertRaisesRegex(ValidationError, "more than once"):
                session.replace_audio_batch(((first, a1), (first, a1)))

            tree_before_failed_import_validation = _file_tree(session.root)
            real_validate = service.validate_user_replacement
            import_validation_count = 0

            def fail_second_import_validation(asset: object, path: Path):
                nonlocal import_validation_count
                if path.name.startswith(".audio-pack-"):
                    import_validation_count += 1
                    if import_validation_count == 2:
                        raise ValidationError(
                            "synthetic second-import validation failure"
                        )
                return real_validate(asset, path)

            with mock.patch.object(
                service,
                "validate_user_replacement",
                side_effect=fail_second_import_validation,
            ):
                with self.assertRaisesRegex(
                    ValidationError,
                    "synthetic second-import validation failure",
                ):
                    session.replace_audio_batch(((first, a1), (second, b1)))
            self.assertEqual(import_validation_count, 2)
            self.assertEqual(
                _file_tree(session.root), tree_before_failed_import_validation
            )
            self.assertFalse(
                any(
                    path.name.startswith(".audio-pack-")
                    for path in session.replacements.iterdir()
                )
            )

            tree_before_failed_import = _file_tree(session.root)
            real_replace = os.replace
            import_commit_count = 0

            def fail_second_import_commit(
                source_path: object, destination: object
            ) -> None:
                nonlocal import_commit_count
                source_name = Path(source_path).name
                if source_name.startswith(".audio-pack-"):
                    import_commit_count += 1
                    if import_commit_count == 2:
                        raise OSError("synthetic second-import failure")
                real_replace(source_path, destination)

            with mock.patch(
                "mod_editor.studio.session.os.replace",
                side_effect=fail_second_import_commit,
            ):
                with self.assertRaisesRegex(
                    OSError, "synthetic second-import failure"
                ):
                    session.replace_audio_batch(((first, a1), (second, b1)))
            self.assertEqual(import_commit_count, 2)
            self.assertEqual(_file_tree(session.root), tree_before_failed_import)
            self.assertFalse(
                any(
                    path.name.startswith(".audio-pack-")
                    for path in session.replacements.iterdir()
                )
            )
            self.assertEqual(session.modified_count, 0)
            self.assertFalse(session.can_undo)

            result = session.replace_audio_batch(((first, a1), (second, b1)))
            self.assertEqual(result.changed_asset_ids, (first.asset_id, second.asset_id))

            a2 = root / "a2.wav"
            a2.write_bytes(b"RIFF-user-audio.a-two")
            b2 = root / "b2.wav"
            b2.write_bytes(b"RIFF-user-audio.b-two")
            session.replace_audio_batch(((first, a2), (second, b2)))
            before_payloads = {
                first.asset_id: session.current_audio_path(first).read_bytes(),
                second.asset_id: session.current_audio_path(second).read_bytes(),
            }
            manifest_before = (session.root / "session.json").read_bytes()
            tree_before_failed_undo = _file_tree(session.root)
            second_destination = session.current_audio_path(second)

            real_validate = service.validate_user_replacement
            undo_restore_validation_count = 0

            def fail_second_undo_restore_validation(asset: object, path: Path):
                nonlocal undo_restore_validation_count
                if path.name.endswith("-restore.wav"):
                    undo_restore_validation_count += 1
                    if undo_restore_validation_count == 2:
                        raise ValidationError(
                            "synthetic second-Undo validation failure"
                        )
                return real_validate(asset, path)

            with mock.patch.object(
                service,
                "validate_user_replacement",
                side_effect=fail_second_undo_restore_validation,
            ):
                with self.assertRaisesRegex(
                    ValidationError,
                    "synthetic second-Undo validation failure",
                ):
                    session.undo()
            self.assertEqual(undo_restore_validation_count, 2)
            self.assertTrue(session.can_undo)
            self.assertEqual(_file_tree(session.root), tree_before_failed_undo)
            self.assertFalse(
                any(
                    path.name.startswith(".audio-undo-")
                    for path in session.replacements.iterdir()
                )
            )

            real_replace = os.replace
            tripped = False

            def fail_second_restore(source_path: object, destination: object) -> None:
                nonlocal tripped
                source_name = Path(source_path).name
                if (
                    not tripped
                    and "audio-undo-" in source_name
                    and source_name.endswith("-restore.wav")
                    and _plain_path(destination) == second_destination
                ):
                    tripped = True
                    raise OSError("synthetic second-restore failure")
                real_replace(source_path, destination)

            with mock.patch(
                "mod_editor.studio.session.os.replace",
                side_effect=fail_second_restore,
            ):
                with self.assertRaisesRegex(
                    OSError, "synthetic second-restore failure"
                ):
                    session.undo()
            self.assertTrue(tripped)
            self.assertTrue(session.can_undo)
            self.assertEqual(_file_tree(session.root), tree_before_failed_undo)
            self.assertFalse(
                any(
                    path.name.startswith(".audio-undo-")
                    for path in session.replacements.iterdir()
                )
            )
            self.assertEqual(
                (session.root / "session.json").read_bytes(), manifest_before
            )
            for asset in (first, second):
                self.assertEqual(
                    session.current_audio_path(asset).read_bytes(),
                    before_payloads[asset.asset_id],
                )

            self.assertEqual(session.undo(), "Import audio replacement pack")
            self.assertEqual(session.current_audio_path(first).read_bytes(), a1.read_bytes())
            self.assertEqual(session.current_audio_path(second).read_bytes(), b1.read_bytes())
            self.assertEqual(session.undo(), "Import audio replacement pack")
            self.assertEqual(session.modified_count, 0)

            session.replace_audio(first, a1)
            before = session.current_audio_path(first).read_bytes()
            with mock.patch.object(
                session,
                "_write_manifest",
                side_effect=(OSError("synthetic disk failure"), None),
            ):
                with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                    session.replace_audio_batch(((first, a2), (second, b2)))
            self.assertEqual(session.modified_audio_asset_ids, {first.asset_id})
            self.assertEqual(session.current_audio_path(first).read_bytes(), before)
            self.assertEqual(session.undo(), "Replace Cue A")
            self.assertEqual(session.modified_count, 0)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offscreen Qt only")
class AudioReplacementPackGuiTests(unittest.TestCase):
    @staticmethod
    def _gui_preview(*, would_change: int) -> SimpleNamespace:
        return SimpleNamespace(
            pack_kind="selected_audio",
            supplied_count=2,
            would_change_count=would_change,
            unique_physical_change_count=would_change,
            already_current_count=2 - would_change,
            would_restore_original_count=0,
            unique_physical_restore_count=0,
            affected_alias_count=0,
            resulting_modified_count=would_change,
            confirmation_token="2k5apf1." + "e" * 64,
            changed_rows=(),
            omitted_changed_count=0,
        )

    def test_preflight_worker_drains_before_apply_and_commits_once(self) -> None:
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix="audio-pack-drain-gui-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            selected_pack = root / "edited-pack"
            selected_pack.mkdir()
            fixture = AudioFixture(source)
            catalog = fixture.catalog()
            audio = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, audio, root / "replacements")
            calls: list[tuple[object, ...]] = []

            def preview(path: Path, progress: object) -> object:
                calls.append(("preview", path))
                progress("Preview ready", 1, 1)  # type: ignore[operator]
                return self._gui_preview(would_change=1)

            def apply(
                path: Path,
                progress: object,
                *,
                confirmation_token: str,
            ) -> object:
                calls.append(("apply", path, confirmation_token))
                progress("Import ready", 1, 1)  # type: ignore[operator]
                return SimpleNamespace(
                    changed_count=1,
                    unchanged_count=1,
                    message=(
                        "Imported 1 changed audio cue as one Undo action; "
                        "1 supplied cue was already current."
                    ),
                )

            host.preflight_audio_replacement_pack = preview  # type: ignore[attr-defined]
            host.import_audio_replacement_pack = apply  # type: ignore[attr-defined]
            panel = AudioPanel(host)
            states: list[bool] = []
            question_busy: list[bool] = []
            panel.operation_state_changed.connect(states.append)

            def answer(*_args: object) -> object:
                question_busy.append(panel.operation_in_progress)
                return QMessageBox.Apply

            with (
                mock.patch.object(
                    QFileDialog,
                    "getExistingDirectory",
                    return_value=str(selected_pack),
                ),
                mock.patch.object(QMessageBox, "question", side_effect=answer) as question,
                mock.patch.object(QMessageBox, "information") as information,
            ):
                panel._import_audio_replacement_pack()
                for _attempt in range(400):
                    application.processEvents()
                    if information.called and not panel.operation_in_progress:
                        break
                    QTest.qWait(5)
                else:
                    self.fail("Audio-pack preview/apply workers did not finish")

            self.assertEqual(question.call_count, 1)
            self.assertEqual(question_busy, [False])
            self.assertEqual(states, [True, False, True, False])
            self.assertEqual(calls[0], ("preview", selected_pack))
            self.assertEqual(
                calls[1],
                ("apply", selected_pack, "2k5apf1." + "e" * 64),
            )
            self.assertEqual(len(calls), 2)
            panel.deleteLater()
            application.processEvents()

    def test_preflight_cancel_and_unchanged_preview_never_import(self) -> None:
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix="audio-pack-cancel-gui-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            selected_pack = root / "edited-pack"
            selected_pack.mkdir()
            fixture = AudioFixture(source)
            catalog = fixture.catalog()
            audio = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, audio, root / "replacements")
            preview_result = [self._gui_preview(would_change=1)]
            imports: list[str] = []

            host.preflight_audio_replacement_pack = (  # type: ignore[attr-defined]
                lambda _path, _progress: preview_result[0]
            )
            host.import_audio_replacement_pack = (  # type: ignore[attr-defined]
                lambda *_args, **_kwargs: imports.append("imported")
            )
            panel = AudioPanel(host)

            with (
                mock.patch.object(
                    QFileDialog,
                    "getExistingDirectory",
                    return_value=str(selected_pack),
                ),
                mock.patch.object(
                    QMessageBox, "question", return_value=QMessageBox.Cancel
                ) as question,
                mock.patch.object(QMessageBox, "information") as information,
            ):
                panel._import_audio_replacement_pack()
                for _attempt in range(400):
                    application.processEvents()
                    if question.called and not panel.operation_in_progress:
                        break
                    QTest.qWait(5)
                else:
                    self.fail("Canceled audio-pack preview did not finish")
                self.assertEqual(imports, [])
                self.assertFalse(information.called)

                question.reset_mock()
                preview_result[0] = self._gui_preview(would_change=0)
                panel._import_audio_replacement_pack()
                for _attempt in range(400):
                    application.processEvents()
                    if information.called and not panel.operation_in_progress:
                        break
                    QTest.qWait(5)
                else:
                    self.fail("Unchanged audio-pack preview did not finish")
                question.assert_not_called()
                self.assertEqual(imports, [])
                self.assertIn("already current", panel.progress_label.text())

            panel.deleteLater()
            application.processEvents()

    def test_mixed_import_reports_changed_and_unchanged_counts(self) -> None:
        from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix="audio-pack-gui-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            fixture = AudioFixture(source)
            catalog = fixture.catalog()
            audio = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, audio, root / "replacements")
            calls: list[tuple[object, ...]] = []

            def export(
                destination: Path,
                *,
                container: str,
                progress: object,
                **options: object,
            ) -> object:
                calls.append(
                    (
                        "export",
                        destination,
                        container,
                        options,
                    )
                )
                progress("Template ready", 1, 1)  # type: ignore[operator]
                return SimpleNamespace(path=destination)

            def preflight_pack(source_path: Path, progress: object) -> object:
                calls.append(("preflight", source_path))
                progress("Preview ready", 1, 1)  # type: ignore[operator]
                return SimpleNamespace(
                    pack_kind="selected_audio",
                    supplied_count=2,
                    would_change_count=1,
                    unique_physical_change_count=1,
                    already_current_count=1,
                    would_restore_original_count=0,
                    unique_physical_restore_count=0,
                    affected_alias_count=0,
                    resulting_modified_count=1,
                    confirmation_token="2k5apf1." + "e" * 64,
                    changed_rows=(),
                    omitted_changed_count=0,
                )

            def import_pack(
                source_path: Path,
                progress: object,
                *,
                confirmation_token: str,
            ) -> object:
                calls.append(("import", source_path, confirmation_token))
                progress("Pack ready", 2, 2)  # type: ignore[operator]
                return SimpleNamespace(
                    changed_count=1,
                    unchanged_count=1,
                    message=(
                        "Imported 1 changed audio cue as one Undo action; "
                        "1 supplied cue was already current."
                    ),
                )

            host.export_audio_replacement_template = export  # type: ignore[attr-defined]
            host.preflight_audio_replacement_pack = preflight_pack  # type: ignore[attr-defined]
            host.import_audio_replacement_pack = import_pack  # type: ignore[attr-defined]
            panel = AudioPanel(host)

            def run(operation: object, complete: object) -> None:
                complete(operation(lambda *_args: None))  # type: ignore[operator]
                continuation = panel._post_operation_continuation
                panel._post_operation_continuation = None
                if continuation is not None:
                    continuation()

            panel._run = run  # type: ignore[method-assign]
            changed: list[int] = []
            panel.audio_batch_imported.connect(changed.append)
            application.processEvents()
            self.assertTrue(panel.export_replacement_template_button.isEnabled())
            self.assertTrue(panel.import_replacement_pack_button.isEnabled())
            self.assertIn("zero retail", panel.replacement_pack_note.text())
            self.assertIn("streaming ranges", panel.replacement_pack_note.text())
            self.assertIn("stay excluded", panel.replacement_pack_note.text())
            self.assertEqual(
                tuple(
                    panel.replacement_pack_contents.itemText(index)
                    for index in range(panel.replacement_pack_contents.count())
                ),
                (
                    "All standalone sounds (850)",
                    "Selected shortlist (1–256)",
                    "Legacy 153-cue pack",
                ),
            )
            self.assertEqual(
                panel.replacement_pack_contents.currentData(), "all_standalone"
            )
            self.assertEqual(
                panel.replacement_pack_contents.accessibleName(),
                "Audio replacement pack contents",
            )
            self.assertTrue(
                panel.replacement_pack_contents.accessibleDescription()
            )
            self.assertEqual(
                panel.replacement_pack_shortlist_count.text(),
                "Shortlist: 0 selected",
            )
            self.assertEqual(
                panel.replacement_pack_shortlist_count.accessibleName(),
                "Replacement pack shortlist count",
            )
            self.assertIn(
                "automatically detects",
                panel.import_replacement_pack_button.toolTip(),
            )

            export_path = root / "metadata-template"
            with (
                mock.patch.object(
                    QFileDialog, "getSaveFileName", return_value=(str(export_path), "")
                ),
                mock.patch.object(QMessageBox, "information"),
            ):
                panel._export_audio_replacement_template()
            self.assertEqual(
                calls[-1],
                (
                    "export",
                    export_path,
                    "folder",
                    {
                        "complete_standalone": True,
                        "with_authoring_map": True,
                        "asset_ids": None,
                    },
                ),
            )

            panel.replacement_pack_contents.setCurrentIndex(
                panel.replacement_pack_contents.findData("standalone")
            )
            application.processEvents()
            legacy_path = root / "legacy-template"
            with (
                mock.patch.object(
                    QFileDialog,
                    "getSaveFileName",
                    return_value=(str(legacy_path), ""),
                ),
                mock.patch.object(QMessageBox, "information"),
            ):
                panel._export_audio_replacement_template()
            self.assertEqual(
                calls[-1],
                ("export", legacy_path, "folder", {"asset_ids": None}),
            )

            import_path = root / "edited-pack"
            with (
                mock.patch.object(
                    QFileDialog, "getExistingDirectory", return_value=str(import_path)
                ),
                mock.patch.object(
                    QMessageBox, "question", return_value=QMessageBox.Apply
                ) as question,
                mock.patch.object(QMessageBox, "information") as information,
            ):
                panel._import_audio_replacement_pack()
            self.assertEqual(calls[-2], ("preflight", import_path))
            self.assertEqual(
                calls[-1],
                ("import", import_path, "2k5apf1." + "e" * 64),
            )
            question.assert_called_once()
            self.assertEqual(changed, [1])
            self.assertIn("1 supplied cue was already current", panel.progress_label.text())
            self.assertIn(
                "1 supplied cue was already current",
                information.call_args.args[2],
            )
            panel.deleteLater()
            application.processEvents()

    def test_shortlist_template_preserves_mixed_order_and_refuses_empty(self) -> None:
        from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(prefix="audio-shortlist-pack-gui-") as name:
            root = Path(name)
            source = root / "source"
            source.mkdir()
            fixture = AudioFixture(source)
            catalog = fixture.catalog()
            audio = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, audio, root / "replacements")
            calls: list[tuple[Path, str, dict[str, object]]] = []

            def export(
                destination: Path,
                *,
                container: str,
                progress: object,
                **options: object,
            ) -> object:
                calls.append((destination, container, options))
                progress("Template ready", 1, 1)  # type: ignore[operator]
                return SimpleNamespace(path=destination)

            host.export_audio_replacement_template = export  # type: ignore[attr-defined]
            host.import_audio_replacement_pack = lambda *_args: None  # type: ignore[attr-defined]
            panel = AudioPanel(host, page_size=2)
            panel._run = lambda operation, complete: complete(  # type: ignore[method-assign]
                operation(lambda *_args: None)
            )
            panel.replacement_pack_contents.setCurrentIndex(
                panel.replacement_pack_contents.findData("shortlist")
            )
            application.processEvents()

            # Never silent-gray: export stays clickable; disableReason teaches empty shortlist.
            self.assertTrue(panel.export_replacement_template_button.isEnabled())
            tip = panel.export_replacement_template_button.toolTip()
            reason = str(
                panel.export_replacement_template_button.property("disableReason") or ""
            )
            self.assertTrue(reason.strip() or tip.strip())
            with mock.patch.object(QFileDialog, "getSaveFileName") as choose:
                panel._export_audio_replacement_template()
            choose.assert_not_called()
            # Busy/empty wall is taught via progress_label (no modal hang).
            self.assertTrue(
                "1–256" in panel.progress_label.text()
                or "Add" in panel.progress_label.text()
                or reason in panel.progress_label.text()
                or reason.strip()
            )
            self.assertEqual(calls, [])

            # RC15 promotes alias-related rows by exact physical identity. The
            # semantic warning remains visible, but the row can enter a v2 pack.
            panel.table.selectRow(0)
            application.processEvents()
            standalone = panel._selected_asset()
            self.assertTrue(standalone.editable)
            self.assertFalse(standalone.legacy_complete_pack_editable)
            self.assertIn("physical slot", standalone.action_note)
            panel._toggle_audio_shortlist()
            self.assertEqual(
                panel.replacement_pack_shortlist_count.text(),
                "Shortlist: 1 selected",
            )
            self.assertTrue(panel.export_replacement_template_button.isEnabled())
            standalone_id = standalone.asset_id
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            application.processEvents()
            range_id = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            ordered_ids = (standalone_id, range_id)

            self.assertEqual(panel._shortlisted_audio_ids(), ordered_ids)
            self.assertEqual(
                panel.replacement_pack_shortlist_count.text(),
                "Shortlist: 2 selected",
            )
            self.assertIn(
                "2 sounds are currently selected",
                panel.replacement_pack_shortlist_count.accessibleDescription(),
            )
            self.assertTrue(panel.export_replacement_template_button.isEnabled())
            self.assertEqual(
                panel.export_replacement_template_button.text(),
                "Export shortlist template (2)…",
            )

            destination = root / "ordered-mixed-template"
            with (
                mock.patch.object(
                    QFileDialog,
                    "getSaveFileName",
                    return_value=(str(destination), ""),
                ),
                mock.patch.object(QMessageBox, "information"),
            ):
                panel._export_audio_replacement_template()
            self.assertEqual(
                calls,
                [(destination, "folder", {"asset_ids": ordered_ids})],
            )
            panel.deleteLater()
            application.processEvents()


if __name__ == "__main__":
    unittest.main()
