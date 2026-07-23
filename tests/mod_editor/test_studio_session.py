"""Retail-free unit tests for the reversible Mod Studio working session."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest import mock
import wave
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_text_catalog import (
    Nfl2k5TextCatalog,
    TextAccess,
    TextAsset,
    TextBank,
)
from mod_editor.studio.session import (
    AudioProjectPreparationRequired,
    BACKEND_SCHEMA,
    SESSION_SCHEMA,
    StadiumProjectPreparationRequired,
    StudioSession,
)
from mod_editor.core.nfl2k5_audio_catalog import (
    MENU_BACK_SELECTOR,
    Nfl2k5AudioService,
    Nfl2k5StreamingAudioRange,
)
from mod_editor.core.nfl2k5_crib import (
    CribAsset,
    CribAssetStatus,
    CribStorage,
    load_nfl2k5_crib_catalog,
)
from mod_editor.core.nfl2k5_stadium_studio import StadiumTexture
from mod_editor.core.nfl2k5_stadium_texture_writer import (
    CompiledStadiumTextureEdit,
    FIXED_ALLOCATION_ERROR,
    TARGET_SCENE_ID,
    TARGET_TEXTURE_ID,
    StadiumTextureWriterError,
)
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture, _valid_menu_wav


@dataclass(frozen=True)
class _Asset:
    asset_id: str = "nfl2k5.uniform.test.torso"
    label: str = "Test Torso"

    def provider_edit(self, png: Path) -> dict[str, object]:
        return {
            "asset_code": "09",
            "clean_png": str(png),
            "kind": "torso",
            "mud_mode": "darken_60",
            "mud_png": None,
            "side": "A",
            "variant": 0,
        }


@dataclass(frozen=True)
class _ScorebugAsset:
    asset_id: str = "nfl2k5.scorebug.score_buga"
    label: str = "Scorebug frame atlas"

    def provider_edit(self, png: Path) -> dict[str, object]:
        return {
            "kind": "scorebug_texture",
            "png": str(png),
            "target": "score_buga",
        }


class _Catalog:
    def __init__(self, asset: _Asset) -> None:
        self.asset = asset

    def get_asset(self, asset_id: str) -> _Asset:
        if asset_id != self.asset.asset_id:
            raise ValidationError("Unknown test asset")
        return self.asset


class _AssetIO:
    original: Path

    def __init__(self, _cache: object) -> None:
        pass

    def ensure_original(self, _asset: _Asset) -> Path:
        return self.original

    @staticmethod
    def validate_replacement(_asset: _Asset, path: Path) -> tuple[bytes, bytes]:
        payload = path.read_bytes()
        if payload == b"ORIGINAL-CONTAINER":
            return payload, b"ORIGINAL-PIXELS"
        if payload == b"USER-A-CONTAINER":
            return payload, b"USER-A-PIXELS"
        if payload == b"USER-B-CONTAINER":
            return payload, b"USER-B-PIXELS"
        if payload == b"REENCODED-ORIGINAL":
            return payload, b"ORIGINAL-PIXELS"
        raise ValidationError("bad synthetic PNG")


class _CribCatalog:
    def __init__(self, asset: CribAsset) -> None:
        self.asset = asset

    def get(self, asset_id: str) -> CribAsset:
        if asset_id != self.asset.asset_id:
            raise ValidationError("Unknown synthetic Crib asset")
        return self.asset


class _CribIO:
    def __init__(self, cache: object, catalog: _CribCatalog, original: Path) -> None:
        self.cache = cache
        self.catalog = catalog
        self.original = original

    def ensure_original(self, _asset: CribAsset) -> Path:
        return self.original

    def export_original(
        self, _asset: CribAsset, destination: Path, *, replace: bool = False
    ) -> Path:
        if destination.exists() and not replace:
            raise ValidationError("destination exists")
        destination.write_bytes(self.original.read_bytes())
        return destination.resolve()

    @staticmethod
    def validate_replacement(_asset: CribAsset, path: Path) -> tuple[bytes, bytes]:
        payload = path.read_bytes()
        if payload == b"CRIB-ORIGINAL-CONTAINER":
            return payload, b"CRIB-ORIGINAL-PIXELS"
        if payload == b"CRIB-USER-CONTAINER":
            return payload, b"CRIB-USER-PIXELS"
        raise ValidationError("bad synthetic Crib PNG")


class _StadiumWriter:
    def __init__(self, cache: object) -> None:
        self.cache = cache
        self.fail = False

    @staticmethod
    def supports(texture: StadiumTexture) -> bool:
        return texture.texture_id == TARGET_TEXTURE_ID

    @staticmethod
    def read_validated_png(
        path: Path, _texture: StadiumTexture | None = None
    ) -> tuple[bytes, bytes]:
        payload = path.read_bytes()
        values = {
            b"STADIUM-STOCK": b"STADIUM-STOCK-RGBA",
            b"STADIUM-USER": b"STADIUM-USER-RGBA",
            b"STADIUM-USER-TWO": b"STADIUM-USER-TWO-RGBA",
        }
        if payload not in values:
            raise ValidationError("bad synthetic Stadium PNG")
        return payload, values[payload]

    @staticmethod
    def texture(_asset_id: str) -> StadiumTexture:
        raise AssertionError("Synthetic attached texture should already be remembered")

    def validated_replacement(
        self, texture: StadiumTexture, path: Path
    ) -> tuple[bytes, bytes, CompiledStadiumTextureEdit]:
        if self.fail:
            raise StadiumTextureWriterError(FIXED_ALLOCATION_ERROR)
        payload, rgba = self.read_validated_png(path)
        preview = b"STADIUM-PREVIEW:" + rgba
        digest = lambda value: hashlib.sha256(value).hexdigest()
        compiled = CompiledStadiumTextureEdit(
            texture_id=texture.texture_id,
            replacement_png_sha256=digest(payload),
            replacement_rgba_sha256=digest(rgba),
            quantized_preview_png_sha256=digest(preview),
            quantized_base_rgba_sha256=digest(rgba),
            mip_rgba_sha256=tuple(digest(rgba + bytes((index,))) for index in range(4)),
            quantization={"palette_entries": 2},
            palette_entries=2,
            decoded_after_sha256=digest(b"decoded"),
            decoded_changed_byte_count=2,
            encoded_sha256=digest(b"encoded"),
            encoded_bytes=100,
            zero_gap_bytes=20,
            minimum_alias_scratch_bytes=16,
            scratch_after=32,
            source_span_sha256=digest(b"source"),
            rebuilt_span_sha256=digest(b"rebuilt"),
            quantized_preview_png=preview,
            rebuilt_span=b"rebuilt",
        )
        return payload, rgba, compiled


class StudioSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="studio-session-test-")
        self.root = Path(self.temporary.name)
        self.asset = _Asset()
        self.catalog = _Catalog(self.asset)
        self.original = self.root / "private-source-cache" / "original.png"
        self.original.parent.mkdir()
        self.original.write_bytes(b"ORIGINAL-CONTAINER")
        _AssetIO.original = self.original
        source = SimpleNamespace(sha256="a" * 64)
        self.cache = SimpleNamespace(source=source, root=self.root / "private-source-cache")
        self.patcher = mock.patch(
            "mod_editor.studio.session.Nfl2k5ProductVisualIO", _AssetIO
        )
        self.patcher.start()
        self.session = StudioSession(
            self.cache, self.catalog, root=self.root / "sessions", session_id="one"
        )

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temporary.cleanup()

    def _user_file(self, name: str, payload: bytes) -> Path:
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_replace_revert_and_undo_are_individually_reversible(self) -> None:
        first = self._user_file("first.png", b"USER-A-CONTAINER")
        second = self._user_file("second.png", b"USER-B-CONTAINER")
        self.assertTrue(self.session.replace(self.asset, first).modified)
        self.assertTrue(self.session.is_modified(self.asset))
        self.assertEqual(self.session.current_path(self.asset).read_bytes(), b"USER-A-CONTAINER")

        self.session.replace(self.asset, second)
        self.assertEqual(self.session.current_path(self.asset).read_bytes(), b"USER-B-CONTAINER")
        self.assertEqual(self.session.undo(), "Replace Test Torso")
        self.assertEqual(self.session.current_path(self.asset).read_bytes(), b"USER-A-CONTAINER")

        self.assertTrue(self.session.revert(self.asset))
        self.assertFalse(self.session.is_modified(self.asset))
        self.assertEqual(self.session.current_path(self.asset), self.original)
        self.assertEqual(self.session.undo(), "Revert Test Torso")
        self.assertEqual(self.session.current_path(self.asset).read_bytes(), b"USER-A-CONTAINER")

    def test_pixel_identical_replacement_is_a_revert_not_retail_project_data(self) -> None:
        reencoded = self._user_file("same.png", b"REENCODED-ORIGINAL")
        result = self.session.replace(self.asset, reencoded)
        self.assertFalse(result.modified)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(list(self.session.replacements.iterdir()), [])
        with self.assertRaisesRegex(ValidationError, "Replace at least one"):
            self.session.canonical_document()

    def test_canonical_build_project_contains_only_the_user_replacement_path(self) -> None:
        supplied = self._user_file("mine.png", b"USER-A-CONTAINER")
        self.session.replace(self.asset, supplied)
        project_path = self.root / "build-project.json"
        self.session.write_canonical_project(project_path)
        payload = project_path.read_bytes()
        value = json.loads(payload)
        self.assertEqual(value["schema"], BACKEND_SCHEMA)
        self.assertEqual(len(value["edits"]), 1)
        replacement = Path(value["edits"][0]["clean_png"])
        self.assertTrue(replacement.is_relative_to(self.session.root))
        self.assertEqual(replacement.read_bytes(), b"USER-A-CONTAINER")
        self.assertNotIn(b"ORIGINAL-CONTAINER", payload)
        with self.assertRaisesRegex(ValidationError, "already exists"):
            self.session.write_canonical_project(project_path)

    def test_manifest_is_metadata_only_and_revert_all_can_be_undone(self) -> None:
        supplied = self._user_file("mine.png", b"USER-A-CONTAINER")
        self.session.replace(self.asset, supplied)
        self.assertEqual(self.session.revert_all(), 1)
        self.assertEqual(self.session.modified_count, 0)
        self.assertEqual(self.session.undo(), "Revert all assets")
        self.assertEqual(self.session.modified_count, 1)
        manifest = (self.session.root / "session.json").read_bytes()
        self.assertEqual(json.loads(manifest)["schema"], SESSION_SCHEMA)
        self.assertNotIn(b"ORIGINAL-CONTAINER", manifest)
        self.assertNotIn(str(self.original).encode(), manifest)

    def test_shareable_project_roundtrip_contains_only_user_replacements(self) -> None:
        supplied = self._user_file("mine.png", b"USER-A-CONTAINER")
        self.session.replace(self.asset, supplied)
        project = self.root / "share.2k5mod"
        self.session.save_shareable_project(project)
        self.assertNotIn(b"ORIGINAL-CONTAINER", project.read_bytes())
        with zipfile.ZipFile(project) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                [
                    "project.json",
                    "replacements/6e70f01727c6202bb46e70fb43d0fe0e1baf9fbd9d04aa23b87962cc5460b827.png",
                ],
            )
            manifest = json.loads(archive.read("project.json"))
            self.assertEqual(manifest["payload_policy"], "user-replacements-only")
            self.assertNotIn("source_sha256", manifest)
            self.assertNotIn("source_path", manifest)

        loaded = StudioSession(
            self.cache, self.catalog, root=self.root / "sessions", session_id="two"
        )
        self.assertEqual(loaded.load_shareable_project(project), 1)
        self.assertEqual(loaded.current_path(self.asset).read_bytes(), b"USER-A-CONTAINER")
        self.assertFalse(loaded.can_undo)

    def test_scorebug_uses_unified_project_and_shareable_png_route(self) -> None:
        asset = _ScorebugAsset()
        catalog = _Catalog(asset)  # type: ignore[arg-type]
        session = StudioSession(
            self.cache, catalog, root=self.root / "sessions", session_id="scorebug"
        )
        supplied = self._user_file("my-scorebug.png", b"USER-A-CONTAINER")
        self.assertTrue(session.replace(asset, supplied).modified)  # type: ignore[arg-type]
        self.assertEqual(
            session.canonical_document()["edits"],
            [{
                "kind": "scorebug_texture",
                "png": str(session.current_path(asset)),  # type: ignore[arg-type]
                "target": "score_buga",
            }],
        )

        project = self.root / "scorebug.2k5mod"
        session.save_shareable_project(project)
        loaded = StudioSession(
            self.cache, catalog, root=self.root / "sessions",
            session_id="scorebug-loaded",
        )
        self.assertEqual(loaded.load_shareable_project(project), 1)
        self.assertEqual(
            loaded.current_path(asset).read_bytes(),  # type: ignore[arg-type]
            b"USER-A-CONTAINER",
        )

    def test_project_refuses_original_pixels_and_undeclared_members(self) -> None:
        reencoded = self._user_file("same.png", b"REENCODED-ORIGINAL")
        self.assertFalse(self.session.replace(self.asset, reencoded).modified)
        with self.assertRaisesRegex(ValidationError, "Make at least one edit"):
            self.session.save_shareable_project(self.root / "empty.2k5mod")

    def test_text_only_build_project_archive_revert_and_undo(self) -> None:
        bank = TextBank(
            "bank.one", "ROST", "Test roster", 1, 0, True, "mixed", 1,
            "Synthetic fixed-allocation bank",
        )
        text = TextAsset(
            "text.team.city", "bank.one", "Team City", "Original Team",
            "utf-16le", 64, 31, 13, TextAccess.EDITABLE,
            "Fixed allocation", 1, 0, "team", 0, "city", 1,
            "roster_team_text", "roster.1.team.0",
        )
        text_catalog = Nfl2k5TextCatalog((bank,), (text,), (), (), ())
        self.session.attach_text_catalog(text_catalog)
        self.assertTrue(self.session.set_text(text, "New City").modified)
        self.assertEqual(self.session.modified_count, 1)
        self.assertEqual(
            self.session.canonical_document()["edits"],
            [{
                "changes": {"city": "New City"},
                "kind": "roster_team_text",
                "resource_outer_index": 1,
                "team_index": 0,
            }],
        )

        project = self.root / "text-only.2k5mod"
        self.session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                ["project.json", "text-replacements.json"],
            )
            replacement = archive.read("text-replacements.json")
            self.assertIn(b"New City", replacement)
            self.assertNotIn(b"Original Team", replacement)

        loaded = StudioSession(
            self.cache, self.catalog, root=self.root / "sessions", session_id="text-two"
        )
        loaded.attach_text_catalog(text_catalog)
        self.assertEqual(loaded.load_shareable_project(project), 1)
        self.assertEqual(loaded.text_value(text.asset_id), "New City")
        self.assertEqual(loaded.revert_all(), 1)
        self.assertEqual(loaded.text_value(text.asset_id), "Original Team")
        self.assertEqual(loaded.undo(), "Revert all assets")
        self.assertEqual(loaded.text_value(text.asset_id), "New City")

    def test_universal_fixed_text_composes_but_public_project_stays_logical(self) -> None:
        bank = TextBank(
            "bank.situ", "SITU", "25th Moments", 10, 0, True,
            "mixed", 150, "Display copy editable; scenario logic Coming Soon.",
        )
        text = TextAsset(
            "nfl2k5.text.situ.moment.0.title", bank.bank_id,
            "25th Anniversary Moment 1 · Title", "Original Moment",
            "utf-16le", 40, 19, 15, TextAccess.EDITABLE,
            "Unique fixed allocation", 10, 0, "situ_text", 0, "title", 1,
            "universal_fixed_text", "situ:moment:0:title",
        )
        catalog = Nfl2k5TextCatalog((bank,), (text,), (), (), ())
        self.session.attach_text_catalog(catalog)
        self.assertTrue(self.session.set_text(text, "MOD").modified)
        self.assertEqual(self.session.canonical_document()["edits"], [{
            "kind": "universal_fixed_text",
            "selector": "situ:moment:0:title",
            "text": "MOD",
        }])

        manifest = json.loads((self.session.root / "session.json").read_bytes())
        replacement = manifest["text_replacements"]["edits"][0]
        self.assertEqual(replacement, {
            "asset_id": text.asset_id,
            "kind": "text",
            "value": "MOD",
        })
        self.assertNotIn("selector", json.dumps(manifest))
        self.assertNotIn("offset", json.dumps(manifest))

        project = self.root / "universal-text.2k5mod"
        self.session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            portable = json.loads(archive.read("text-replacements.json"))
        self.assertEqual(portable["edits"], [replacement])

    def test_audio_composes_with_project_archive_and_global_undo(self) -> None:
        source_root = self.root / "audio-source"
        source_root.mkdir()
        fixture = AudioFixture(source_root)
        catalog = fixture.catalog()
        service = Nfl2k5AudioService(fixture.cache, catalog)
        session = StudioSession(
            fixture.cache, self.catalog,
            root=self.root / "sessions", session_id="audio-one",
        )
        session.attach_audio_service(service)
        alias_related = next(
            item for item in catalog.assets
            if not item.legacy_complete_pack_editable
        )
        self.assertTrue(alias_related.editable)
        self.assertIn("physical slot", alias_related.action_note)
        original_path = session.current_audio_path(alias_related)
        self.assertTrue(original_path.is_file())
        original_export = session.export_audio(
            alias_related, self.root / "alias-related-original.wav"
        )
        self.assertEqual(original_export.read_bytes(), original_path.read_bytes())
        asset = next(
            item for item in catalog.assets if item.selector == MENU_BACK_SELECTOR
        )
        supplied = _valid_menu_wav(self.root / "user-menu-back.wav")
        self.assertTrue(session.replace_audio(asset, supplied).modified)
        self.assertEqual(session.modified_audio_asset_ids, {asset.asset_id})
        self.assertEqual(
            session.canonical_document()["edits"],
            [{
                "kind": "menu_back_audio",
                "wav": str(session.current_audio_path(asset)),
            }],
        )

        project = self.root / "audio-only.2k5mod"
        session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            member = next(name for name in archive.namelist() if name.endswith(".wav"))
            self.assertEqual(archive.read(member), supplied.read_bytes())
            self.assertNotEqual(archive.read(member), service.ensure_original(asset).read_bytes())

        loaded = StudioSession(
            fixture.cache, self.catalog,
            root=self.root / "sessions", session_id="audio-two",
        )
        loaded.attach_audio_service(service)
        self.assertEqual(loaded.load_shareable_project(project), 1)
        self.assertEqual(loaded.current_audio_path(asset).read_bytes(), supplied.read_bytes())
        self.assertEqual(loaded.revert_all(), 1)
        self.assertEqual(loaded.undo(), "Revert all assets")
        self.assertEqual(loaded.current_audio_path(asset).read_bytes(), supplied.read_bytes())

    def test_streaming_alias_is_one_physical_reversible_project_edit(self) -> None:
        source_root = self.root / "streaming-audio-source"
        source_root.mkdir()
        fixture = AudioFixture(source_root)
        catalog = fixture.catalog()
        first = catalog.streaming_ranges[0]
        alias_bank = replace(
            first.bank,
            asset_id="nfl2k5.audio.ausb.o0003.c0103",
            chunk_index=103,
            shared_external_descriptor_count=2,
        )
        alias = Nfl2k5StreamingAudioRange(
            alias_bank, first.range_index, first.start, first.end
        )
        catalog.streaming_banks += (alias_bank,)
        catalog._streaming_by_id[alias_bank.asset_id] = alias_bank  # noqa: SLF001
        catalog.streaming_ranges += (alias,)
        catalog._streaming_range_by_id[alias.asset_id] = alias  # noqa: SLF001
        for private in (fixture.cache.root / "derived").glob("audio-source-pcm-*.json"):
            private.unlink()
        fixture._ensure_private_audio_inventories(catalog)  # noqa: SLF001
        service = Nfl2k5AudioService(fixture.cache, catalog)

        authored = self.root / "streaming-user.wav"
        with wave.open(str(authored), "wb") as stream:
            stream.setnchannels(first.channels)
            stream.setsampwidth(2)
            stream.setframerate(first.sample_rate)
            stream.writeframes(
                (1234).to_bytes(2, "little", signed=True)
                * first.frame_count * first.channels
            )

        session = StudioSession(
            fixture.cache, self.catalog,
            root=self.root / "sessions", session_id="streaming-alias",
        )
        session.attach_audio_service(service)
        result = session.replace_audio_batch(((first, authored), (alias, authored)))
        self.assertEqual(result.requested_asset_ids, (first.asset_id, alias.asset_id))
        self.assertEqual(session.modified_count, 1)
        self.assertEqual(
            session.modified_audio_asset_ids, {first.asset_id, alias.asset_id}
        )
        self.assertEqual(
            session.current_audio_path(alias).read_bytes(), authored.read_bytes()
        )
        document = session.canonical_document()
        self.assertEqual(document["edits"], [{
            "asset_id": first.asset_id,
            "kind": "ausb_audio",
            "wav": str(session.current_audio_path(first)),
        }])
        public_json = json.dumps(document)
        self.assertNotIn("physical", public_json)
        self.assertNotIn("offset", public_json)
        self.assertNotIn("fingerprint", public_json)

        project = session.save_shareable_project(self.root / "streaming.2k5mod")
        with zipfile.ZipFile(project) as archive:
            manifest = json.loads(archive.read("project.json"))
        self.assertEqual(len(manifest["audio_edits"]), 1)
        self.assertEqual(manifest["audio_edits"][0]["asset_id"], first.asset_id)

        cold_service = Nfl2k5AudioService(fixture.cache, catalog)
        imported = StudioSession(
            fixture.cache, self.catalog,
            root=self.root / "sessions", session_id="streaming-import",
        )
        imported.attach_audio_service(cold_service)
        before_import_staging = set(imported.root.glob("project-import-*"))
        with self.assertRaisesRegex(
            AudioProjectPreparationRequired, "Prepare the private audio"
        ):
            imported.load_shareable_project(project)
        self.assertEqual(imported.modified_count, 0)
        self.assertEqual(
            set(imported.root.glob("project-import-*")), before_import_staging
        )
        cold_service.load_private_origin_inventories()
        self.assertEqual(imported.load_shareable_project(project), 1)
        self.assertEqual(imported.modified_count, 1)
        self.assertEqual(
            imported.modified_audio_asset_ids, {first.asset_id, alias.asset_id}
        )

        self.assertTrue(session.revert_audio(alias))
        self.assertEqual(session.modified_audio_asset_ids, frozenset())
        self.assertEqual(session.undo(), f"Revert {alias.name}")
        self.assertEqual(
            session.modified_audio_asset_ids, {first.asset_id, alias.asset_id}
        )
        self.assertEqual(session.revert_all(), 1)
        self.assertEqual(session.modified_count, 0)
        self.assertEqual(session.undo(), "Revert all assets")
        self.assertEqual(session.modified_count, 1)

        divergent = self.root / "streaming-divergent.wav"
        with wave.open(str(divergent), "wb") as stream:
            stream.setnchannels(alias.channels)
            stream.setsampwidth(2)
            stream.setframerate(alias.sample_rate)
            stream.writeframes(
                (-2345).to_bytes(2, "little", signed=True)
                * alias.frame_count * alias.channels
            )
        fresh = StudioSession(
            fixture.cache, self.catalog,
            root=self.root / "sessions", session_id="streaming-divergent",
        )
        fresh.attach_audio_service(service)
        with self.assertRaisesRegex(ValidationError, "different WAVs"):
            fresh.replace_audio_batch(((first, authored), (alias, divergent)))
        self.assertEqual(fresh.modified_count, 0)

    def test_crib_photo_composes_with_project_archive_and_global_undo(self) -> None:
        asset = CribAsset(
            asset_id="nfl2k5.crib.aggregate.15_photo_02",
            selector="crib_team_photo:15_photo_02",
            label="Team Photo 15 / 02",
            group="Team Photos",
            status=CribAssetStatus.EDITABLE,
            storage=CribStorage.TEAM_ITEM_AGGREGATE,
            authoring_note="Synthetic fixed-allocation Team Photo",
            width=128,
            height=128,
            mip_levels=5,
            format_name="P8",
            outer_index=1,
            outer_id="0x01",
            outer_size=23_008,
            chunk_index=0,
            chunk_offset=0,
            stored_size=22_976,
            system_bytes=128,
            video_bytes=22_848,
            descriptor_offset=0,
            pixel_offset=0,
            palette_offset=21_824,
            packed_format=0,
            packed_size=0,
            decoded_sha256="b" * 64,
            rgba_sha256="c" * 64,
            span_sha256="d" * 64,
            xiso_absolute_offset=1,
        )
        catalog = _CribCatalog(asset)
        original = self.root / "private-source-cache" / "crib-original.png"
        original.write_bytes(b"CRIB-ORIGINAL-CONTAINER")
        crib_io = _CribIO(self.cache, catalog, original)
        self.session.attach_crib(catalog, crib_io)  # type: ignore[arg-type]
        supplied = self._user_file("my-crib-photo.png", b"CRIB-USER-CONTAINER")

        self.assertTrue(self.session.replace_crib(asset, supplied).modified)
        self.assertEqual(self.session.modified_crib_asset_ids, {asset.asset_id})
        self.assertEqual(
            self.session.canonical_document()["edits"],
            [{
                "kind": "crib_team_photo",
                "png": str(self.session.current_crib_path(asset)),
                "selector": asset.selector,
            }],
        )
        manifest = json.loads((self.session.root / "session.json").read_bytes())
        self.assertEqual(manifest["crib_edits"][0]["asset_id"], asset.asset_id)
        self.assertEqual(manifest["crib_edits"][0]["selector"], asset.selector)

        project = self.root / "crib-only.2k5mod"
        self.session.save_shareable_project(project)
        self.assertNotIn(b"CRIB-ORIGINAL-CONTAINER", project.read_bytes())
        with zipfile.ZipFile(project) as archive:
            png_member = next(name for name in archive.namelist() if name.endswith(".png"))
            self.assertEqual(archive.read(png_member), b"CRIB-USER-CONTAINER")
            project_manifest = json.loads(archive.read("project.json"))
            self.assertEqual(project_manifest["edits"][0]["selector"], asset.selector)

        loaded = StudioSession(
            self.cache, self.catalog,
            root=self.root / "sessions", session_id="crib-two",
        )
        loaded.attach_crib(catalog, crib_io)  # type: ignore[arg-type]
        self.assertEqual(loaded.load_shareable_project(project), 1)
        self.assertEqual(
            loaded.current_crib_path(asset).read_bytes(), b"CRIB-USER-CONTAINER"
        )
        self.assertEqual(loaded.revert_all(), 1)
        self.assertEqual(loaded.undo(), "Revert all assets")
        self.assertEqual(
            loaded.current_crib_path(asset).read_bytes(), b"CRIB-USER-CONTAINER"
        )

    def test_crib_bar_monitor_composes_as_logical_scene_texture_project(self) -> None:
        asset = load_nfl2k5_crib_catalog().by_selector(
            "crib_scene_texture:room:22"
        )
        catalog = _CribCatalog(asset)
        original = self.root / "private-source-cache" / "bar-monitor-original.png"
        original.write_bytes(b"CRIB-ORIGINAL-CONTAINER")
        crib_io = _CribIO(self.cache, catalog, original)
        self.session.attach_crib(catalog, crib_io)  # type: ignore[arg-type]
        supplied = self._user_file("my-bar-monitor.png", b"CRIB-USER-CONTAINER")

        self.assertTrue(self.session.replace_crib(asset, supplied).modified)
        self.assertEqual(self.session.canonical_document()["edits"], [{
            "kind": "crib_scene_texture",
            "png": str(self.session.current_crib_path(asset)),
            "selector": "crib_scene_texture:room:22",
        }])
        project = self.root / "bar-monitor.2k5mod"
        self.session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            document = json.loads(archive.read("project.json"))
            self.assertEqual(document["payload_policy"], "user-replacements-only")
            self.assertEqual(document["edits"], [{
                "asset_id": asset.asset_id,
                "file": document["edits"][0]["file"],
                "png_sha256": document["edits"][0]["png_sha256"],
                "rgba_sha256": document["edits"][0]["rgba_sha256"],
                "selector": asset.selector,
            }])
            self.assertEqual(
                set(archive.namelist()),
                {"project.json", document["edits"][0]["file"]},
            )
            self.assertNotIn("offset", json.dumps(document).casefold())
            self.assertNotIn("span", json.dumps(document).casefold())
        loaded = StudioSession(
            self.cache, self.catalog,
            root=self.root / "sessions", session_id="bar-monitor-two",
        )
        loaded.attach_crib(catalog, crib_io)  # type: ignore[arg-type]
        self.assertEqual(loaded.load_shareable_project(project), 1)
        self.assertEqual(loaded.canonical_document()["edits"][0]["kind"],
                         "crib_scene_texture")
        self.assertTrue(loaded.revert_crib(asset))
        self.assertEqual(loaded.undo(), f"Revert {asset.label}")
        self.assertEqual(loaded.canonical_document()["edits"][0]["selector"],
                         asset.selector)

    def test_stadium_texture_composes_through_project_build_revert_and_undo(self) -> None:
        stock = self.root / "private-source-cache" / "cement01.png"
        stock.write_bytes(b"STADIUM-STOCK")
        stock_rgba = b"STADIUM-STOCK-RGBA"
        texture = StadiumTexture(
            texture_id=TARGET_TEXTURE_ID,
            scene_id=TARGET_SCENE_ID,
            texture_index=2,
            width=64,
            height=64,
            format_name="P8",
            rgba_sha256=hashlib.sha256(stock_rgba).hexdigest(),
            png_sha256=hashlib.sha256(stock.read_bytes()).hexdigest(),
            png_path=stock,
            mapped_material_names=("cement01",),
            mapped_material_count=1,
            access_status="Editable",
        )
        writer = _StadiumWriter(self.cache)
        visual = self._user_file("uniform.png", b"USER-A-CONTAINER")
        stadium = self._user_file("stadium.png", b"STADIUM-USER")
        self.session.replace(self.asset, visual)
        # Stadium Studio is prepared lazily, so attaching its source-bound
        # writer must remain safe after unrelated project edits already exist.
        self.session.attach_stadium_texture(writer, texture)  # type: ignore[arg-type]
        result = self.session.replace_stadium_texture(texture, stadium)
        self.assertTrue(result.modified)
        self.assertIn("1 linked material", result.message)
        self.assertEqual(self.session.modified_count, 2)
        self.assertEqual(
            self.session.current_stadium_png(texture).read_bytes(),
            b"STADIUM-PREVIEW:STADIUM-USER-RGBA",
        )
        canonical = self.session.canonical_document()["edits"]
        self.assertEqual([row["kind"] for row in canonical], ["torso", "stadium_texture"])
        stadium_row = canonical[1]
        self.assertEqual(stadium_row["target"], TARGET_TEXTURE_ID)
        self.assertEqual(Path(stadium_row["png"]).read_bytes(), b"STADIUM-USER")

        project = self.root / "stadium-and-uniform.2k5mod"
        self.session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            png_payloads = [
                archive.read(name)
                for name in archive.namelist()
                if name.endswith(".png")
            ]
            self.assertCountEqual(
                png_payloads, [b"USER-A-CONTAINER", b"STADIUM-USER"]
            )
            self.assertNotIn(b"STADIUM-STOCK", png_payloads)
            self.assertFalse(any(payload.startswith(b"STADIUM-PREVIEW")
                                 for payload in png_payloads))

        loaded = StudioSession(
            self.cache, self.catalog, root=self.root / "sessions",
            session_id="stadium-loaded",
        )
        with self.assertRaisesRegex(
            StadiumProjectPreparationRequired, "Prepare Stadium Studio"
        ):
            loaded.load_shareable_project(project)
        self.assertEqual(loaded.modified_count, 0)
        self.assertEqual(tuple(loaded.replacements.iterdir()), ())
        loaded.attach_stadium_texture(
            _StadiumWriter(self.cache), texture  # type: ignore[arg-type]
        )
        self.assertEqual(loaded.load_shareable_project(project), 2)
        self.assertEqual(loaded.modified_count, 2)
        self.assertEqual(
            loaded.current_stadium_png(texture).read_bytes(),
            b"STADIUM-PREVIEW:STADIUM-USER-RGBA",
        )
        self.assertTrue(loaded.revert_stadium_texture(texture))
        self.assertEqual(loaded.current_stadium_png(texture), stock)
        self.assertEqual(loaded.undo(), "Revert Stadium texture")
        self.assertEqual(
            loaded.current_stadium_png(texture).read_bytes(),
            b"STADIUM-PREVIEW:STADIUM-USER-RGBA",
        )
        self.assertEqual(loaded.revert_all(), 2)
        self.assertEqual(loaded.undo(), "Revert all assets")
        self.assertEqual(loaded.modified_count, 2)

        previous_preview = self.session.current_stadium_png(texture)
        writer.fail = True
        second = self._user_file("stadium-two.png", b"STADIUM-USER-TWO")
        with self.assertRaisesRegex(
            StadiumTextureWriterError, "fixed SCNE allocation"
        ):
            self.session.replace_stadium_texture(texture, second)
        self.assertEqual(self.session.current_stadium_png(texture), previous_preview)
        self.assertEqual(previous_preview.read_bytes(), b"STADIUM-PREVIEW:STADIUM-USER-RGBA")


if __name__ == "__main__":
    unittest.main()
