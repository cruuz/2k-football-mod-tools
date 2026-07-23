from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch
import warnings
import wave
import zipfile

from PIL import Image

from mod_editor.apf_studio.asset_io import (
    ApfAssetIO,
    AssetIoError,
    AudioPreviewCancelled,
)
from mod_editor.apf_studio.build import (
    BUILD_SPACE_MARGIN,
    EXPECTED_TREE,
    ApfBuildService,
    BuildError,
)
from mod_editor.apf_studio.catalog import CatalogBuilder, CatalogError
from mod_editor.apf_studio.launcher import LaunchError, XeniaLauncher, XeniaSettings
from mod_editor.apf_studio.inspectors import ExportIdentity, _row
from mod_editor.apf_studio.models import (
    ApfAsset,
    ApfCategory,
    ApfSource,
    ApfStatus,
    ExternalAudioBankIdentity,
    ExternalAudioBankOwner,
    Modification,
)
from mod_editor.apf_studio.project import ProjectError, load_project, save_project
from mod_editor.apf_studio.session import ApfSession
from mod_editor.apf_studio.source import EXPECTED_0A_SHA256


def _source(root: Path) -> ApfSource:
    return ApfSource(
        selected_path=root,
        game_root=root,
        index_0a=root / "0A",
        source_sha256=EXPECTED_0A_SHA256,
        source_size=0,
        xex_sha256="x" * 64,
        display_name="APF safety fixture",
    )


def _png(path: Path, size: tuple[int, int] = (8, 8)) -> bytes:
    Image.new("RGBA", size, (10, 20, 30, 255)).save(path, format="PNG")
    return path.read_bytes()


def _modification(path: Path, asset_id: str = "apf:uniform:jersey:00") -> Modification:
    data = path.read_bytes()
    return Modification(
        asset_id=asset_id,
        kind="uniform",
        replacement_path=path,
        replacement_sha256=hashlib.sha256(data).hexdigest(),
        metadata={
            "family": "jersey",
            "asset_index": 0,
            "outer_index": 1,
            "inner_index": 1,
        },
    )


class AssetExportSafetyTests(unittest.TestCase):
    @staticmethod
    def _write_pcm_wav(path: Path) -> None:
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(22_050)
            output.writeframes(b"\x00\x00" * 128)

    def test_large_outer_export_is_streamed_in_bounded_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = ApfAssetIO(_source(root), SimpleNamespace(), cache_root=root / "cache")
            entry = SimpleNamespace(size=16 * 1024 * 1024 + 7)
            archive = SimpleNamespace(entries=[entry])
            calls: list[tuple[int, int]] = []

            class Reader:
                def __init__(self, _archive: object):
                    pass

                def __enter__(self) -> "Reader":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def read(self, _entry: object, offset: int, size: int) -> bytes:
                    calls.append((offset, size))
                    return b"x" * size

            asset = ApfAsset(
                asset_id="apf:outer:0",
                outer_index=0,
                inner_index=None,
                name="large",
                type_name="NON_IFF",
                asset_class="opaque",
                category=ApfCategory.ALL_ASSETS,
                status=ApfStatus.EXPORT_ONLY,
                decoded_size=entry.size,
                outer_size=entry.size,
                part_count=1,
            )
            destination = root / "large.bin"
            with patch(
                "mod_editor.apf_studio.asset_io.apf_outer.parse_archive",
                return_value=archive,
            ), patch(
                "mod_editor.apf_studio.asset_io.apf_inner.ArchiveReader", Reader
            ):
                io._export_outer_raw(asset, destination)
            self.assertEqual(destination.stat().st_size, entry.size)
            self.assertEqual(
                calls,
                [
                    (0, 8 * 1024 * 1024),
                    (8 * 1024 * 1024, 8 * 1024 * 1024),
                    (16 * 1024 * 1024, 7),
                ],
            )
            self.assertEqual(list(root.glob("*.exporting")), [])

    def test_external_audio_bank_export_is_typed_streamed_and_source_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source(root)
            source.index_0a.write_bytes(b"source sentinel")
            source_before = source.index_0a.read_bytes()
            entry = SimpleNamespace(
                table_index=0,
                name_id=0x12345678,
                head_hex="08000000",
                size=8 * 1024 * 1024 + 3,
            )
            archive = SimpleNamespace(entries=[entry])
            asset = ApfAsset(
                asset_id="apf:outer:0",
                outer_index=0,
                inner_index=None,
                name="lines.bin",
                type_name="XMA1_BANK",
                asset_class="external_xma1_packet_bank",
                category=ApfCategory.AUDIO,
                status=ApfStatus.EXPORT_ONLY,
                decoded_size=entry.size,
                outer_size=entry.size,
                part_count=1,
                metadata={"name_id": "0x12345678"},
            )
            catalog = SimpleNamespace(
                get=lambda asset_id: asset
                if asset_id == asset.asset_id
                else (_ for _ in ()).throw(ValueError(asset_id))
            )
            identity = ExternalAudioBankIdentity(
                external_filename="lines.bin",
                outer_table_index=0,
                name_id=entry.name_id,
                encoded_size=entry.size,
                owners=(
                    ExternalAudioBankOwner(
                        descriptor_outer_index=1310,
                        descriptor_inner_index=143,
                        bank_name="lines",
                        substream_count=31_826,
                        sample_rate=22_050,
                        channel_count=1,
                    ),
                ),
            )
            calls: list[tuple[int, int]] = []
            progress: list[tuple[int, int]] = []

            class Reader:
                def __init__(self, _archive: object):
                    pass

                def __enter__(self) -> "Reader":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

                def read(self, _entry: object, offset: int, size: int) -> bytes:
                    calls.append((offset, size))
                    return b"x" * size

            io = ApfAssetIO(source, catalog, cache_root=root / "cache")
            destination = root / "lines.bin"
            with patch(
                "mod_editor.apf_studio.asset_io.apf_outer.parse_archive",
                return_value=archive,
            ), patch(
                "mod_editor.apf_studio.asset_io.apf_inner.ArchiveReader", Reader
            ):
                exported = io.export_external_audio_bank(
                    identity,
                    destination,
                    progress=lambda completed, total: progress.append(
                        (completed, total)
                    ),
                )

            self.assertEqual(exported, destination)
            self.assertEqual(destination.stat().st_size, entry.size)
            self.assertEqual(
                calls,
                [(0, 8 * 1024 * 1024), (8 * 1024 * 1024, 3)],
            )
            self.assertEqual(
                progress,
                [(0, entry.size), (8 * 1024 * 1024, entry.size), (entry.size, entry.size)],
            )
            self.assertEqual(source.index_0a.read_bytes(), source_before)

            with self.assertRaises(FileExistsError):
                io.export_external_audio_bank(identity, destination)
            with self.assertRaisesRegex(AssetIoError, r"\.bin"):
                io.export_external_audio_bank(identity, root / "lines.wav")

            mismatch = ExternalAudioBankIdentity(
                external_filename=identity.external_filename,
                outer_table_index=identity.outer_table_index,
                name_id=identity.name_id,
                encoded_size=identity.encoded_size + 1,
                owners=identity.owners,
            )
            with self.assertRaisesRegex(AssetIoError, "no longer matches"):
                io.export_external_audio_bank(mismatch, root / "mismatch.bin")

    def test_wav_export_never_uses_or_deletes_a_user_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source(root)
            io = ApfAssetIO(source, SimpleNamespace(), cache_root=root / "cache")
            asset = ApfAsset(
                asset_id="apf:outer:5:inner:9",
                outer_index=5,
                inner_index=9,
                name="fixture_sound",
                type_name="AUDO",
                asset_class="audio",
                category=ApfCategory.AUDIO,
                status=ApfStatus.EXPORT_ONLY,
                decoded_size=1,
                outer_size=1,
                part_count=1,
            )
            destination = root / "sound.wav"
            old_sidecar = root / ".sound.wav.source.xma"
            old_sidecar.write_bytes(b"user file")

            def fake_export(
                _source: Path,
                _outer: int,
                _inner: int,
                xma: Path,
                wav: Path | None,
                _limit: int,
            ) -> dict[str, object]:
                xma.write_bytes(b"xma")
                assert wav is not None
                wav.write_bytes(b"wav")
                return {"wav": {"status": "decoder_verified_fixture"}}

            with patch(
                "mod_editor.apf_studio.asset_io.apf_audio.export_selected",
                side_effect=fake_export,
            ):
                io._export_audo(asset, destination)

            self.assertEqual(destination.read_bytes(), b"wav")
            self.assertEqual(old_sidecar.read_bytes(), b"user file")

    def test_audio_export_preserves_a_destination_created_during_decode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = ApfAssetIO(_source(root), SimpleNamespace(), cache_root=root / "cache")
            destination = root / "race.xma"

            def fake_export(
                _source: Path,
                _outer: int,
                _inner: int,
                xma: Path,
                _wav: Path | None,
                _limit: int,
            ) -> dict[str, object]:
                destination.write_bytes(b"concurrent user file")
                xma.write_bytes(b"generated")
                return {}

            identity = SimpleNamespace(
                kind="audo",
                outer_table_index=5,
                inner_file_index=9,
                substream_index=None,
                suggested_basename="fixture",
                supported_extensions=(".xma", ".wav"),
            )
            with patch(
                "mod_editor.apf_studio.asset_io.apf_audio.export_selected",
                side_effect=fake_export,
            ), self.assertRaises(FileExistsError):
                io.export_audio_identity(identity, destination)
            self.assertEqual(destination.read_bytes(), b"concurrent user file")

    def test_private_audio_preview_rejects_tamper_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = ApfAssetIO(_source(root), SimpleNamespace(), cache_root=root / "cache")
            identity = ExportIdentity("audo", 5, 9, None, "fixture")

            def fake_export(_identity: ExportIdentity, destination: Path) -> Path:
                self._write_pcm_wav(destination)
                return destination

            with patch.object(io, "export_audio_identity", side_effect=fake_export):
                preview = io.prepare_audio_preview(identity, root / "previews")
                self.assertEqual(preview, io.prepare_audio_preview(identity, root / "previews"))
                preview.write_bytes(preview.read_bytes() + b"tamper")
                with self.assertRaisesRegex(AssetIoError, "changed"):
                    io.prepare_audio_preview(identity, root / "previews")

            other = ExportIdentity("audo", 5, 10, None, "other")
            unsafe = root / "previews" / "audo-o0005-i0010.wav"
            outside = root / "outside.wav"
            self._write_pcm_wav(outside)
            unsafe.symlink_to(outside)
            with self.assertRaisesRegex(AssetIoError, "unreceipted"):
                io.prepare_audio_preview(other, root / "previews")

            session = ApfSession(
                _source(root), SimpleNamespace(), cache_root=root / "session-cache"
            )
            working_root = session.working_root
            with patch.object(
                session.asset_io, "export_audio_identity", side_effect=fake_export
            ):
                private_preview = session.prepare_audio_preview(identity)
            self.assertTrue(private_preview.is_file())
            session.close()
            self.assertFalse(working_root.exists())

    def test_cancelled_audio_preview_publishes_no_wav_or_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = ApfAssetIO(_source(root), SimpleNamespace(), cache_root=root / "cache")
            identity = ExportIdentity("audo", 5, 9, None, "fixture")
            cancelled = threading.Event()

            def fake_export(
                _identity: ExportIdentity,
                destination: Path,
                *,
                cancel_requested: object = None,
            ) -> Path:
                self._write_pcm_wav(destination)
                cancelled.set()
                return destination

            preview = root / "previews" / "audo-o0005-i0009.wav"
            with patch.object(io, "export_audio_identity", side_effect=fake_export):
                with self.assertRaises(AudioPreviewCancelled):
                    io.prepare_audio_preview(
                        identity,
                        root / "previews",
                        cancel_requested=cancelled.is_set,
                    )
            self.assertFalse(preview.exists())
            self.assertNotIn(preview, io._audio_preview_receipts)

    def test_cancelled_cached_audio_preview_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = ApfAssetIO(_source(root), SimpleNamespace(), cache_root=root / "cache")
            identity = ExportIdentity("audo", 5, 9, None, "fixture")

            def fake_export(_identity: ExportIdentity, destination: Path) -> Path:
                self._write_pcm_wav(destination)
                return destination

            with patch.object(io, "export_audio_identity", side_effect=fake_export):
                preview = io.prepare_audio_preview(identity, root / "previews")
            receipt = io._audio_preview_receipts[preview]
            with self.assertRaises(AudioPreviewCancelled):
                io.prepare_audio_preview(
                    identity,
                    root / "previews",
                    cancel_requested=lambda: True,
                )
            self.assertTrue(preview.is_file())
            self.assertEqual(io._audio_preview_receipts[preview], receipt)

    def test_bounded_audio_bank_zip_is_transactional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = ApfAssetIO(_source(root), SimpleNamespace(), cache_root=root / "cache")
            identities = tuple(
                ExportIdentity("ausb_substream", 10, 4, index, f"bank-{index}")
                for index in range(3)
            )

            def fake_export(identity: ExportIdentity, destination: Path) -> Path:
                destination.write_bytes(f"xma-{identity.substream_index}".encode("ascii"))
                return destination

            destination = root / "bank.zip"
            with patch.object(io, "export_audio_identity", side_effect=fake_export):
                io.export_audio_bank(
                    identities,
                    destination,
                    bank_name="jukeboxmusic",
                )
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(
                    archive.namelist(),
                    [
                        "manifest.json",
                        "playlist.m3u8",
                        "audio/001-jukeboxmusic.xma",
                        "audio/002-jukeboxmusic.xma",
                        "audio/003-jukeboxmusic.xma",
                    ],
                )
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["substream_count"], 3)
                self.assertEqual(manifest["playlist"], "playlist.m3u8")
                self.assertEqual(manifest["playlist_record_count"], 3)
                self.assertEqual(
                    archive.read("playlist.m3u8").decode("utf-8").splitlines()[:6],
                    [
                        "#EXTM3U",
                        "#PLAYLIST:jukeboxmusic",
                        "#EXTINF:-1,jukeboxmusic Track 001",
                        "audio/001-jukeboxmusic.xma",
                        "#EXTINF:-1,jukeboxmusic Track 002",
                        "audio/002-jukeboxmusic.xma",
                    ],
                )

            failed = root / "failed.zip"

            def fail_second(identity: ExportIdentity, destination: Path) -> Path:
                if identity.substream_index == 1:
                    raise AssetIoError("fixture decode failure")
                destination.write_bytes(b"first")
                return destination

            with patch.object(io, "export_audio_identity", side_effect=fail_second):
                with self.assertRaisesRegex(AssetIoError, "fixture"):
                    io.export_audio_bank(
                        identities,
                        failed,
                        bank_name="jukeboxmusic",
                    )
            self.assertFalse(failed.exists())

    def test_filtered_audio_bundle_is_mixed_bounded_and_transactional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            io = ApfAssetIO(_source(root), SimpleNamespace(), cache_root=root / "cache")
            rows = (
                _row(
                    "apf:audio:audo:5:1",
                    "audo",
                    "menu_back",
                    "AUDIO",
                    {
                        "role_id": "ui_menu_sfx",
                        "role_label": "UI & Menu SFX",
                        "sample_rate": 22_050,
                        "derived_channel_count": 1,
                        "duration_seconds": 1.25,
                    },
                    export_identity=ExportIdentity(
                        "audo", 5, 1, None, "menu-back"
                    ),
                ),
                _row(
                    "apf:audio:ausb:8:2:substream:7",
                    "ausb_substream",
                    "Commentary line 00007",
                    "XMA packets",
                    {
                        "role_id": "commentary_speech",
                        "role_label": "Commentary & Speech",
                        "bank_name": "lines",
                        "sample_rate": 32_000,
                        "derived_channel_count": 1,
                        "duration_seconds_candidate": 2.5,
                    },
                    export_identity=ExportIdentity(
                        "ausb_substream", 8, 2, 7, "lines-00007"
                    ),
                ),
            )

            def fake_export(identity: ExportIdentity, destination: Path) -> Path:
                destination.write_bytes(
                    f"{identity.kind}:{identity.substream_index}".encode("ascii")
                )
                return destination

            progress: list[tuple[int, int]] = []
            destination = root / "matching.zip"
            with patch.object(io, "export_audio_identity", side_effect=fake_export):
                io.export_audio_bundle(
                    rows,
                    destination,
                    bundle_name="Commentary / menu selection",
                    progress=lambda completed, total: progress.append(
                        (completed, total)
                    ),
                )
            self.assertEqual(progress, [(0, 2), (1, 2), (2, 2)])
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(
                    archive.namelist(),
                    [
                        "manifest.json",
                        "playlist.m3u8",
                        "audio/001-menu-back.xma",
                        "audio/002-lines-00007.xma",
                    ],
                )
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(
                    manifest["schema"],
                    "apf2k8_mod_studio_audio_bundle_export/v1",
                )
                self.assertEqual(manifest["sound_count"], 2)
                self.assertEqual(manifest["format"], "xma")
                self.assertEqual(manifest["playlist"], "playlist.m3u8")
                self.assertEqual(manifest["playlist_record_count"], 2)
                self.assertEqual(manifest["records"][1]["bank_name"], "lines")
                self.assertEqual(manifest["records"][1]["substream_index"], 7)
                self.assertEqual(
                    archive.read("playlist.m3u8").decode("utf-8").splitlines(),
                    [
                        "#EXTM3U",
                        "#PLAYLIST:Commentary - menu selection",
                        "#EXTINF:1.25,menu_back",
                        "audio/001-menu-back.xma",
                        "#EXTINF:2.5,Commentary line 00007",
                        "audio/002-lines-00007.xma",
                    ],
                )

            with self.assertRaisesRegex(AssetIoError, "1–256"):
                io.export_audio_bundle(
                    rows * 129,
                    root / "too-many.zip",
                    bundle_name="too many",
                )

            failed = root / "failed-bundle.zip"

            def fail_second(identity: ExportIdentity, destination: Path) -> Path:
                if identity.kind == "ausb_substream":
                    raise AssetIoError("fixture WAV decode failed")
                destination.write_bytes(b"first")
                return destination

            with patch.object(io, "export_audio_identity", side_effect=fail_second):
                with self.assertRaisesRegex(AssetIoError, "fixture WAV"):
                    io.export_audio_bundle(
                        rows,
                        failed,
                        bundle_name="all or nothing",
                        output_extension=".wav",
                    )
            self.assertFalse(failed.exists())

            existing = root / "existing.zip"
            existing.write_bytes(b"keep me")
            with self.assertRaises(FileExistsError):
                io.export_audio_bundle(rows, existing, bundle_name="refuse")
            self.assertEqual(existing.read_bytes(), b"keep me")


class ProjectTransactionTests(unittest.TestCase):
    def test_save_preserves_destination_created_at_publish_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "replacement.png"
            _png(png)
            destination = root / "project.apf2k8mod"
            real_link = os.link

            def racing_link(source: Path, target: Path) -> None:
                Path(target).write_bytes(b"concurrent user file")
                real_link(source, target)

            with patch(
                "mod_editor.apf_studio.project.os.link", side_effect=racing_link
            ), self.assertRaises(FileExistsError):
                save_project(
                    destination,
                    source_sha256="d" * 64,
                    modifications=(_modification(png),),
                )
            self.assertEqual(destination.read_bytes(), b"concurrent user file")

    def test_save_rejects_duplicate_asset_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "replacement.png"
            _png(png)
            duplicate = _modification(png)
            with self.assertRaisesRegex(ProjectError, "twice"):
                save_project(
                    root / "duplicate.apf2k8mod",
                    source_sha256="d" * 64,
                    modifications=(duplicate, duplicate),
                )

    def test_project_rejects_opaque_payloads_hidden_in_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "replacement.png"
            _png(png)
            original = _modification(png)
            smuggled = Modification(
                asset_id=original.asset_id,
                kind=original.kind,
                replacement_path=original.replacement_path,
                replacement_sha256=original.replacement_sha256,
                metadata={**original.metadata, "rgba": [0, 1, 2, 3]},
            )
            with self.assertRaisesRegex(ProjectError, "metadata"):
                save_project(
                    root / "unsafe.apf2k8mod",
                    source_sha256="d" * 64,
                    modifications=(smuggled,),
                )

    def test_loader_rejects_project_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "replacement.png"
            _png(png)
            project = save_project(
                root / "real.apf2k8mod",
                source_sha256="d" * 64,
                modifications=(_modification(png),),
            )
            link = root / "linked.apf2k8mod"
            link.symlink_to(project)
            with self.assertRaisesRegex(ProjectError, "non-symlink"):
                load_project(
                    link,
                    expected_source_sha256="d" * 64,
                    destination_dir=root / "loaded",
                )

    def test_loader_rejects_duplicate_zip_member_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "duplicate-member.apf2k8mod"
            manifest = {
                "schema": "apf2k8_mod_project/v1",
                "game": "apf2k8_xbox360",
            }
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(project, "w") as archive:
                    archive.writestr("project.json", json.dumps(manifest))
                    archive.writestr("project.json", json.dumps(manifest))
            with self.assertRaisesRegex(ProjectError, "duplicate"):
                load_project(
                    project,
                    expected_source_sha256="d" * 64,
                    destination_dir=root / "loaded",
                )

    def test_loader_does_not_trust_conflicting_content_addressed_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "replacement.png"
            data = _png(png)
            project = save_project(
                root / "project.apf2k8mod",
                source_sha256="d" * 64,
                modifications=(_modification(png),),
            )
            loaded = root / "loaded"
            loaded.mkdir()
            digest = hashlib.sha256(data).hexdigest()
            conflict = loaded / f"{digest}.png"
            conflict.write_bytes(b"wrong")
            with self.assertRaisesRegex(ProjectError, "conflicts"):
                load_project(
                    project,
                    expected_source_sha256="d" * 64,
                    destination_dir=loaded,
                )
            self.assertEqual(conflict.read_bytes(), b"wrong")

    def test_failed_session_import_removes_unpack_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root), SimpleNamespace(), cache_root=root / "cache"
            )

            def fail_import(
                _source: Path,
                *,
                expected_source_sha256: str,
                destination_dir: Path,
            ) -> tuple[dict[str, object], tuple[Modification, ...]]:
                del expected_source_sha256
                destination_dir.mkdir(parents=True)
                (destination_dir / "partial.png").write_bytes(b"partial")
                raise ProjectError("fixture failure")

            try:
                with patch(
                    "mod_editor.apf_studio.session.read_project_archive",
                    side_effect=fail_import,
                ), self.assertRaisesRegex(ProjectError, "fixture failure"):
                    session.load_project(root / "broken.apf2k8mod")
                self.assertEqual(list(session.working_root.glob("import-*")), [])
            finally:
                session.close()


class BuildBoundaryTests(unittest.TestCase):
    @staticmethod
    def _tiny_game(root: Path) -> dict[str, tuple[int, str]]:
        tree = {
            "0A": (4, "a" * 64),
            "0B": (5, "b" * 64),
            "1A": (6, "c" * 64),
            "1B": (7, "d" * 64),
            "default.xex": (8, "e" * 64),
            "$SystemUpdate/su20076000_00000000": (9, "f" * 64),
        }
        for index, (relative, (size, _digest)) in enumerate(tree.items(), start=1):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes((index,)) * size)
        return tree

    def test_clean_build_publishes_one_complete_atomic_game_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            tree = self._tiny_game(game)
            output = root / "output"
            with patch("mod_editor.apf_studio.build.EXPECTED_TREE", tree), patch(
                "mod_editor.apf_studio.build.sha256_file",
                return_value=EXPECTED_0A_SHA256,
            ), patch(
                "mod_editor.apf_studio.build.apf_outer.parse_archive",
                return_value=SimpleNamespace(entries=[]),
            ), patch.object(
                ApfBuildService,
                "_verify_composed",
                return_value="9" * 64,
            ):
                receipt = ApfBuildService(_source(game)).build((), output)
            self.assertEqual(receipt.output_game, output)
            self.assertTrue(receipt.source_unchanged)
            self.assertEqual(receipt.changed_outer_entries, ())
            for relative in tree:
                self.assertEqual((output / relative).read_bytes(), (game / relative).read_bytes())
                self.assertNotEqual(
                    (output / relative).stat().st_ino,
                    (game / relative).stat().st_ino,
                )
            manifest = json.loads(receipt.manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["mode"], "clean_copy")
            self.assertTrue(manifest["output"]["published_atomically"])

    def test_low_space_is_refused_before_hashing_or_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            output = root / "output"
            required = (
                sum(size for size, _digest in EXPECTED_TREE.values())
                + BUILD_SPACE_MARGIN
            )
            with patch(
                "mod_editor.apf_studio.build.shutil.disk_usage",
                return_value=SimpleNamespace(free=0),
            ), patch(
                "mod_editor.apf_studio.build.sha256_file"
            ) as source_hash, self.assertRaisesRegex(
                BuildError,
                r"enough free space.*choose a different drive.*No output was created",
            ):
                ApfBuildService(_source(game)).build((), output)
            source_hash.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".output.building-*")), [])

            with patch(
                "mod_editor.apf_studio.build.shutil.disk_usage",
                return_value=SimpleNamespace(free=required - 1025),
            ), patch(
                "mod_editor.apf_studio.build.sha256_file"
            ) as source_hash, self.assertRaisesRegex(
                BuildError,
                r"Free another 1\.01 KiB or choose a different drive",
            ):
                ApfBuildService(_source(game)).build((), output)
            source_hash.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".output.building-*")), [])

            with patch(
                "mod_editor.apf_studio.build.shutil.disk_usage",
                return_value=SimpleNamespace(free=required - 1),
            ), patch(
                "mod_editor.apf_studio.build.sha256_file"
            ) as source_hash, self.assertRaisesRegex(
                BuildError,
                r"Free another 1 byte or choose a different drive",
            ):
                ApfBuildService(_source(game)).build((), output)
            source_hash.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".output.building-*")), [])

    def test_failed_build_removes_staging_and_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            tree = self._tiny_game(game)
            output = root / "output"
            with patch("mod_editor.apf_studio.build.EXPECTED_TREE", tree), patch(
                "mod_editor.apf_studio.build.sha256_file",
                return_value=EXPECTED_0A_SHA256,
            ), patch(
                "mod_editor.apf_studio.build.apf_outer.parse_archive",
                return_value=SimpleNamespace(entries=[]),
            ), patch.object(
                ApfBuildService,
                "_verify_composed",
                side_effect=BuildError("fixture verification failure"),
            ), self.assertRaisesRegex(BuildError, "fixture verification failure"):
                ApfBuildService(_source(game)).build((), output)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".output.building-*")), [])

    def test_build_rejects_output_inside_untouched_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "game"
            root.mkdir()
            service = ApfBuildService(_source(root))
            with self.assertRaisesRegex(BuildError, "outside"):
                service.build((), root / "modded")
            self.assertFalse((root / "modded").exists())

    def test_build_rejects_replacement_whose_hash_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            replacement = root / "replacement.png"
            _png(replacement)
            modification = _modification(replacement)
            modification = Modification(
                asset_id=modification.asset_id,
                kind=modification.kind,
                replacement_path=modification.replacement_path,
                replacement_sha256="0" * 64,
                metadata=modification.metadata,
            )

            def fake_hash(path: Path, *_args: object, **_kwargs: object) -> str:
                if Path(path) == game / "0A":
                    return EXPECTED_0A_SHA256
                return hashlib.sha256(Path(path).read_bytes()).hexdigest()

            with patch(
                "mod_editor.apf_studio.build.sha256_file", side_effect=fake_hash
            ), self.assertRaisesRegex(BuildError, "changed after import"):
                ApfBuildService(_source(game)).build(
                    (modification,), root / "output"
                )
            self.assertFalse((root / "output").exists())


class CatalogAndLauncherSafetyTests(unittest.TestCase):
    def test_cached_catalog_rejects_corrupt_inner_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            selection = root / "selection.json"
            catalog.write_text(
                json.dumps(
                    {
                        "schema": "apf2k8_mod_studio_live_catalog/v1",
                        "source_sha256": EXPECTED_0A_SHA256,
                        "outer_count": 1543,
                        "iff_count": 1473,
                        "non_iff_count": 70,
                        "inner_count": 10_394,
                        "assets": [],
                    }
                ),
                encoding="utf-8",
            )
            selection.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(CatalogError, "selection"):
                CatalogBuilder(cache_root=root)._load_cached(
                    catalog, selection, _source(root)
                )

    def test_xenia_settings_reject_executable_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "xenia"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            link = root / "xenia-link"
            link.symlink_to(executable)
            settings = XeniaSettings(root / "settings.json")
            with self.assertRaisesRegex(LaunchError, "non-symlink"):
                settings.configure(link)

    def test_xenia_settings_ignore_stale_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "xenia"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            settings_path = root / "settings.json"
            (root / ".settings.json.tmp").write_bytes(b"stale")
            settings = XeniaSettings(settings_path)
            settings.configure(executable)
            self.assertTrue(settings.configured)
            self.assertEqual(json.loads(settings_path.read_text())["xenia_path"], str(executable))

    def test_xenia_launch_does_not_follow_log_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "xenia"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            settings = XeniaSettings(root / "settings.json")
            settings.configure(executable)
            game = root / "game"
            game.mkdir()
            (game / "default.xex").write_bytes(b"fixture")
            data = root / "data"
            launcher = XeniaLauncher(settings, data_root=data)
            run = data / hashlib.sha256(str(game).encode("utf-8")).hexdigest()[:20]
            logs = run / "logs"
            logs.mkdir(parents=True)
            victim = root / "victim.txt"
            victim.write_bytes(b"preserve me")
            (logs / "xenia-latest.log").symlink_to(victim)
            with self.assertRaisesRegex(LaunchError, "could not be started"):
                launcher.launch(game)
            self.assertEqual(victim.read_bytes(), b"preserve me")


if __name__ == "__main__":
    unittest.main()
