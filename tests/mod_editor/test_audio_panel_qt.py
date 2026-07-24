"""Retail-free tests for the isolated PyQt5 Audio panel contract."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_audio_catalog import (
    EDITABLE_CLASSIFICATION,
    EXPECTED_PLAYABLE_AUDIO_COUNT,
    Nfl2k5AudioCatalogError,
    Nfl2k5AudioService,
    PLAYABLE_AUDIO_SCOPE_ID,
)
from mod_editor.core.nfl2k5_universal_asset_index import UniversalAssetRecord
from mod_editor.gui.audio_panel_qt import (
    AUDIO_PLAYABLE_DEFAULT_SCOPE_CONTRACT,
    AUDIO_TOOLBAR_TARGET_WIDTH,
    AudioPage,
    AudioPanel,
    AudioPanelHost,
    CatalogAudioPanelHost,
    PYQT5_AVAILABLE,
    audio_player_command,
    filter_audio_assets,
    filter_audio_banks,
    filter_audio_ranges,
    paginate_audio_assets,
)
from mod_editor.studio import facade as facade_module
from mod_editor.studio.facade import Nfl2k5StudioFacade, StudioAudioPage
from mod_editor.studio.session import StudioSession
from tests.mod_editor.test_nfl2k5_audio_catalog import (
    AudioFixture,
    FIRST_RANGE_SIZE,
    _valid_menu_wav,
)


_RAW_CONTAINER_COORDINATES = (
    ("BANK", 510, 0, "0x35fa6c06", "BANK", 0, 160),
    ("BANK", 511, 0, "0x767eba11", "BANK", 0, 128),
    ("BANK", 512, 0, "0xa3b6d03f", "BANK", 0, 256),
    ("ABNK", 3116, 0, "0xb96b765e", "ABNK", 0, 656),
    ("WBNK", 3116, 1, "0xb96b765e", "ABNK", 688, 70_776),
    ("ABNK", 3117, 0, "0x2f27ca67", "ABNK", 0, 6_848),
    ("WBNK", 3117, 1, "0x2f27ca67", "ABNK", 6_880, 411_552),
    ("ABNK", 3118, 0, "0x6ca31c70", "ABNK", 0, 1_728),
    ("WBNK", 3118, 1, "0x6ca31c70", "ABNK", 1_760, 1_518_732),
)


def _authorize_synthetic_fixture_audio(service: Nfl2k5AudioService) -> None:
    """Keep UI tests retail-free without manufacturing private scan documents.

    The origin gates have dedicated hostile tests.  These panel tests need an
    issued object only to exercise current-WAV, alias, and widget state paths.
    """

    def authorize(_asset: object, snapshot: object) -> object:
        metadata = snapshot.metadata  # type: ignore[attr-defined]
        return SimpleNamespace(
            wav_bytes=snapshot.wav_bytes,  # type: ignore[attr-defined]
            wav_sha256=metadata.wav_sha256,
        )

    service.authorize_replacement_snapshot = authorize  # type: ignore[method-assign]


def _exact_streaming_range_wav(path: Path, asset: object, sample: int) -> Path:
    """Write one canonical, non-source PCM16 fixture for an AUSB range."""

    channels = int(getattr(asset, "channels"))
    frame_count = int(getattr(asset, "frame_count"))
    sample_rate = int(getattr(asset, "sample_rate"))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        frame = int(sample).to_bytes(2, "little", signed=True) * channels
        stream.writeframes(frame * frame_count)
    return path


def _exact_standalone_wav(path: Path, asset: object, sample: int) -> Path:
    """Write one canonical PCM16 fixture for an exact standalone slot."""

    return _exact_streaming_range_wav(path, asset, sample)


def _reviewed_standalone_assets(
    base: object, count: int, *, start_chunk: int = 1_000
) -> tuple[object, ...]:
    """Build deterministic retail-free metadata rows for bulk-selection tests."""

    return tuple(
        replace(
            base,
            asset_id=f"nfl2k5.audio.audo.o0003.c{start_chunk + index:04d}",
            name=f"reviewed-cue-{index + 1:03d}",
            outer_index=3,
            chunk_index=start_chunk + index,
            classification=EDITABLE_CLASSIFICATION,
            classification_reasons=("retail-free bulk-selection fixture",),
            duplicate_name=None,
        )
        for index in range(count)
    )


class _RawResourceIndex:
    """Metadata-only stand-in using the pinned retail container coordinates."""

    def __init__(self, *, omit_last: bool = False) -> None:
        rows = []
        for kind, outer, chunk, outer_id, outer_head, offset, stored in (
            _RAW_CONTAINER_COORDINATES[:-1]
            if omit_last else _RAW_CONTAINER_COORDINATES
        ):
            raw_size = stored + 0x20
            rows.append(
                UniversalAssetRecord(
                    asset_id=(
                        f"nfl2k5.resource.o{outer:04d}.c{chunk:04d}."
                        f"k{kind.encode('ascii').hex()}"
                    ),
                    outer_index=outer,
                    outer_id=outer_id,
                    outer_head=outer_head,
                    outer_size=offset + raw_size,
                    chunk_index=chunk,
                    chunk_offset=offset,
                    zero_padding_before=0,
                    kind=kind,
                    stored_size=stored,
                    end_offset=offset + raw_size,
                    word_08=0,
                    word_0c=0,
                    word_10="0x00000000",
                    word_14=0,
                )
            )
        self.records = tuple(rows)
        self.asset_count = len(self.records)
        self.exports: list[str] = []

    def query(
        self,
        *,
        search: str = "",
        kind: str | None = None,
        offset: int = 0,
        limit: int = 250,
    ) -> tuple[UniversalAssetRecord, ...]:
        needle = search.casefold()
        rows = tuple(
            row for row in self.records
            if (kind is None or row.kind == kind)
            and (not needle or needle in row.asset_id.casefold())
        )
        return rows[offset:offset + limit]

    def export_raw(
        self, asset: UniversalAssetRecord | str, destination: Path
    ) -> Path:
        selected = next(
            (
                row for row in self.records
                if row.asset_id == (
                    asset if isinstance(asset, str) else asset.asset_id
                )
            ),
            None,
        )
        if selected is None or (
            isinstance(asset, UniversalAssetRecord) and asset != selected
        ):
            raise ValidationError("That raw container is not in the source index")
        if destination.exists() or destination.is_symlink():
            raise ValidationError("The export destination already exists")
        destination.write_bytes(
            selected.kind.encode("ascii") + b" synthetic private fixture"
        )
        self.exports.append(selected.asset_id)
        return destination.resolve()


class AudioPanelBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source_root = self.root / "source"
        source_root.mkdir()
        self.fixture = AudioFixture(source_root)
        self.catalog = self.fixture.catalog()
        self.service = Nfl2k5AudioService(self.fixture.cache, self.catalog)
        _authorize_synthetic_fixture_audio(self.service)
        self.host = CatalogAudioPanelHost(
            self.catalog, self.service, self.root / "user-replacements"
        )
        self.progress: list[tuple[str, int, int]] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _progress(self, stage: str, completed: int, total: int) -> None:
        self.progress.append((stage, completed, total))

    def test_host_protocol_search_status_and_pagination_cover_catalog(self) -> None:
        self.assertIsInstance(self.host, AudioPanelHost)
        self.assertEqual(
            self.host.audio_complete_pack_path(self.catalog.assets[0].asset_id),
            "replacements/001__selected-audio.wav",
        )
        self.assertEqual(
            self.host.audio_complete_pack_path(self.catalog.assets[1].asset_id),
            "replacements/002__selected-audio.wav",
        )
        self.assertIsNone(
            self.host.audio_complete_pack_path(
                self.catalog.streaming_banks[0].asset_id
            )
        )
        self.assertIsNone(self.host.audio_complete_pack_path("unknown.audio"))
        first = self.host.browse_audio(search="", status=None, offset=0, limit=1)
        self.assertEqual(first.total, 2)
        self.assertEqual(len(first.assets), 1)
        self.assertFalse(first.has_previous)
        self.assertTrue(first.has_next)
        second = self.host.browse_audio(search="", status=None, offset=1, limit=1)
        self.assertTrue(second.has_previous)
        self.assertFalse(second.has_next)
        self.assertTrue(second.assets[0].editable)

        editable = self.host.browse_audio(
            search="menu 16000", status="Editable", offset=0, limit=50
        )
        self.assertEqual(editable.total, 2)
        self.assertTrue(all(asset.editable for asset in editable.assets))
        self.assertEqual(
            self.host.browse_audio(
                search="export-only", status=None, offset=0, limit=50
            ).total,
            0,
        )
        export_only = filter_audio_assets(
            self.catalog.assets, status="Export-only"
        )
        self.assertEqual(len(export_only), 0)
        clamped = paginate_audio_assets(self.catalog.assets, offset=99, limit=1)
        self.assertEqual(clamped.offset, 1)
        with self.assertRaises(ValidationError):
            self.host.browse_audio(search="", status="Unsafe", offset=0, limit=50)
        with self.assertRaisesRegex(ValidationError, "family"):
            self.host.browse_audio(
                search="", status=None, offset=0, limit=50,
                scope="streaming", family="made-up",
            )

        banks = self.host.browse_audio(
            search="soundtrack music raw",
            status="Export-only",
            offset=0,
            limit=50,
            scope="streaming",
            family="music",
        )
        self.assertEqual(banks.total, 1)
        self.assertEqual(banks.assets[0].name, "femusic")
        self.assertEqual(
            filter_audio_banks(self.catalog.streaming_banks, search="commentary"),
            (),
        )
        ranges = self.host.browse_audio(
            search=f"r00001 {FIRST_RANGE_SIZE}",
            status="Editable",
            offset=0,
            limit=50,
            scope="streaming_ranges",
            family="music",
        )
        self.assertEqual(ranges.total, 1)
        self.assertEqual(ranges.assets[0].range_index, 1)
        self.assertEqual(
            filter_audio_ranges(
                self.catalog.streaming_ranges,
                search="soundtrack playable xbox",
                family="music",
            ),
            self.catalog.streaming_ranges,
        )
        playable = self.host.browse_audio(
            search="", status=None, offset=0, limit=50,
            scope=PLAYABLE_AUDIO_SCOPE_ID,
        )
        self.assertEqual(playable.assets, self.catalog.playable_assets)
        self.assertEqual(playable.total, len(self.catalog.playable_assets))
        self.assertEqual(
            self.host.browse_audio(
                search="soundtrack playable", status="Editable", offset=0,
                limit=50, scope=PLAYABLE_AUDIO_SCOPE_ID, family="music",
            ).assets,
            self.catalog.streaming_ranges,
        )

    def test_meaning_confidence_filter_counts_paginate_and_refuse_wrong_scope(
        self,
    ) -> None:
        provisional_base, menu_back = self.catalog.assets
        reviewed = tuple(
            replace(
                provisional_base,
                asset_id=f"fixture.audio.reviewed.{index:03d}",
                name=f"Reviewed label {index + 1}",
                outer_index=4,
                chunk_index=index,
                classification=EDITABLE_CLASSIFICATION,
            )
            for index in range(152)
        )
        provisional = tuple(
            replace(
                provisional_base,
                asset_id=f"fixture.audio.provisional.{index:03d}",
                name=f"Provisional label {index + 1}",
                outer_index=5,
                chunk_index=index,
            )
            for index in range(697)
        )
        self.host.catalog.assets = (menu_back, *reviewed, *provisional)

        all_audio = self.host.browse_audio(
            search="", status=None, offset=0, limit=50
        )
        self.assertEqual(all_audio.total, 850)
        menu_page = self.host.browse_audio(
            search="",
            status=None,
            offset=0,
            limit=50,
            meaning_status="menu_back_route_runtime_unproved",
        )
        self.assertEqual(menu_page.total, 1)
        self.assertEqual(menu_page.assets, (menu_back,))
        reviewed_page = self.host.browse_audio(
            search="",
            status=None,
            offset=999,
            limit=50,
            meaning_status="reviewed_label_runtime_meaning_unproved",
        )
        self.assertEqual(reviewed_page.total, 152)
        self.assertEqual(reviewed_page.offset, 150)
        self.assertEqual(len(reviewed_page.assets), 2)
        provisional_page = self.host.browse_audio(
            search="",
            status=None,
            offset=650,
            limit=50,
            meaning_status="provisional_label_runtime_meaning_unproved",
        )
        self.assertEqual(provisional_page.total, 697)
        self.assertEqual(provisional_page.offset, 650)
        self.assertEqual(len(provisional_page.assets), 47)

        with self.assertRaisesRegex(ValidationError, "meaning-confidence"):
            self.host.browse_audio(
                search="",
                status=None,
                offset=0,
                limit=50,
                meaning_status="reviewed-ish",
            )
        with self.assertRaisesRegex(ValidationError, "only to standalone"):
            self.host.browse_audio(
                search="",
                status=None,
                offset=0,
                limit=50,
                scope="streaming",
                meaning_status="menu_back_route_runtime_unproved",
            )
        refused = self.root / "wrong-scope.zip"
        with self.assertRaisesRegex(ValidationError, "only to standalone"):
            self.host.export_audio_bundle(
                search="",
                status=None,
                scope="streaming_ranges",
                family=None,
                meaning_status="provisional_label_runtime_meaning_unproved",
                destination=refused,
                output_format="wav",
                bundle_name="Wrong scope",
                progress=self._progress,
            )
        self.assertFalse(refused.exists())

    def test_raw_streaming_bank_export_is_separate_from_wav_playback(self) -> None:
        bank = self.catalog.streaming_banks[0]
        destination = self.root / bank.suggested_filename
        exported = self.host.export_audio_bank(
            bank.asset_id, destination, self._progress
        )
        self.assertEqual(exported, destination.resolve())
        self.assertEqual(exported.read_bytes(), self.fixture.bank_payload)
        with self.assertRaises(Nfl2k5AudioCatalogError):
            self.host.prepare_audio(bank.asset_id, self._progress)

        item = self.catalog.streaming_ranges[0]
        range_destination = self.root / item.suggested_filename
        exported_range = self.host.export_audio_range(
            item.asset_id, range_destination, self._progress
        )
        self.assertEqual(exported_range, range_destination.resolve())
        self.assertEqual(
            exported_range.read_bytes(), self.fixture.bank_payload[:FIRST_RANGE_SIZE]
        )
        self.assertIn(
            ("Raw streaming range exported", item.stored_size, item.stored_size),
            self.progress,
        )
        playable = self.host.prepare_audio(item.asset_id, self._progress)
        self.assertEqual(
            playable, self.service.streaming_range_original_path(item)
        )
        with wave.open(str(playable), "rb") as stream:
            self.assertEqual(stream.getnchannels(), item.channels)
            self.assertEqual(stream.getframerate(), item.sample_rate)
            self.assertEqual(stream.getnframes(), item.frame_count)
        wav_destination = self.root / item.suggested_wav_filename
        self.assertEqual(
            self.host.export_audio_range_wav(
                item.asset_id, wav_destination, self._progress
            ),
            wav_destination.resolve(),
        )
        self.assertEqual(wav_destination.read_bytes(), playable.read_bytes())

    def test_main_facade_pages_and_exports_streaming_audio(self) -> None:
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
        )
        facade._audio_catalog = self.catalog
        facade._audio_service = self.service
        modified_id = self.catalog.assets[1].asset_id
        facade._session = SimpleNamespace(
            modified_audio_asset_ids=(modified_id,),
            current_audio_path=lambda asset: self.service.audio_playback_path(asset),
            export_audio=lambda asset, destination: (
                self.service.export_streaming_range_wav(asset, destination)
            ),
        )
        modified_page = facade.browse_audio(
            search="", status="Modified", offset=0, limit=50
        )
        self.assertEqual(modified_page.total, 1)
        self.assertEqual(modified_page.assets[0].asset_id, modified_id)
        self.assertEqual(
            facade.browse_audio(
                search="",
                status=None,
                offset=0,
                limit=50,
                meaning_status="menu_back_route_runtime_unproved",
            ).assets,
            (self.catalog.assets[1],),
        )
        self.assertEqual(
            facade.browse_audio(
                search="",
                status=None,
                offset=0,
                limit=50,
                meaning_status="provisional_label_runtime_meaning_unproved",
            ).assets,
            (self.catalog.assets[0],),
        )
        with self.assertRaisesRegex(ValidationError, "meaning-confidence"):
            facade.browse_audio(
                search="",
                status=None,
                offset=0,
                limit=50,
                meaning_status=[],  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValidationError, "only to standalone"):
            facade.browse_audio(
                search="",
                status=None,
                offset=0,
                limit=50,
                scope="streaming",
                meaning_status="menu_back_route_runtime_unproved",
            )
        self.assertEqual(
            facade.browse_audio(
                search="", status="Modified", offset=0, limit=50,
                scope="streaming",
            ).total,
            0,
        )
        page = facade.browse_audio(
            search="soundtrack",
            status="Export-only",
            offset=0,
            limit=50,
            scope="streaming",
            family="music",
        )
        self.assertEqual((page.first_number, page.last_number), (1, 1))
        bank = page.assets[0]
        output = self.root / "facade-bank.bin"
        self.assertEqual(
            facade.export_audio_bank(bank.asset_id, output, self._progress),
            output.resolve(),
        )
        self.assertEqual(output.read_bytes(), self.fixture.bank_payload)

        range_page = facade.browse_audio(
            search="r00000 raw",
            status="Editable",
            offset=0,
            limit=50,
            scope="streaming_ranges",
            family="music",
        )
        self.assertEqual((range_page.first_number, range_page.last_number), (1, 1))
        item = range_page.assets[0]
        range_output = self.root / "facade-range.bin"
        self.assertEqual(
            facade.export_audio_range(item.asset_id, range_output, self._progress),
            range_output.resolve(),
        )
        self.assertEqual(
            range_output.read_bytes(), self.fixture.bank_payload[:FIRST_RANGE_SIZE]
        )
        wav_output = self.root / "facade-range.wav"
        self.assertEqual(
            facade.export_audio_range_wav(
                item.asset_id, wav_output, self._progress
            ),
            wav_output.resolve(),
        )
        self.assertTrue(wav_output.is_file())
        self.assertEqual(
            facade.prepare_audio(item.asset_id, self._progress).read_bytes(),
            wav_output.read_bytes(),
        )

    def test_main_facade_builds_audio_search_text_only_once_per_catalog(self) -> None:
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
        )
        facade._audio_catalog = self.catalog
        facade._session = SimpleNamespace(modified_audio_asset_ids=())
        expected_rows = (
            len(self.catalog.assets)
            + len(self.catalog.streaming_banks)
            + len(self.catalog.streaming_ranges)
        )
        with patch.object(
            facade_module,
            "_audio_search_haystack",
            wraps=facade_module._audio_search_haystack,
        ) as haystack:
            first = facade.browse_audio(
                search="soundtrack playable",
                status="Editable",
                offset=0,
                limit=50,
                scope="streaming_ranges",
                family="music",
            )
            self.assertEqual(first.total, len(self.catalog.streaming_ranges))
            self.assertEqual(haystack.call_count, expected_rows)
            second = facade.browse_audio(
                search="r00001 raw",
                status="Editable",
                offset=0,
                limit=50,
                scope="streaming_ranges",
                family="music",
            )
            self.assertEqual(second.total, 1)
            self.assertEqual(haystack.call_count, expected_rows)

    def test_main_facade_discards_audio_search_index_when_catalog_changes(self) -> None:
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
        )
        facade._audio_catalog = self.catalog
        facade._session = SimpleNamespace(modified_audio_asset_ids=())
        self.assertEqual(
            facade.browse_audio(
                search="export-only", status=None, offset=0, limit=50
            ).total,
            0,
        )
        self.assertEqual(
            facade.browse_audio(
                search="catalog b only", status=None, offset=0, limit=50
            ).total,
            0,
        )

        renamed = replace(self.catalog.assets[0], name="Catalog B Only")
        catalog_b = SimpleNamespace(
            assets=(renamed, *self.catalog.assets[1:]),
            streaming_banks=self.catalog.streaming_banks,
            streaming_ranges=self.catalog.streaming_ranges,
        )
        facade._audio_catalog = catalog_b
        refreshed = facade.browse_audio(
            search="catalog b only", status=None, offset=0, limit=50
        )
        self.assertEqual(refreshed.total, 1)
        self.assertEqual(refreshed.assets[0].name, "Catalog B Only")

    def test_replace_export_build_plan_and_revert_are_strict_and_reversible(self) -> None:
        duplicate, fixed = self.catalog.assets
        supplied = _valid_menu_wav(self.root / "mine.wav")
        duplicate_wav = _exact_standalone_wav(
            self.root / "alias-related.wav", duplicate, 1_111
        )
        duplicate_metadata = self.host.replace_audio(
            duplicate.asset_id, duplicate_wav, self._progress
        )
        self.assertEqual(duplicate_metadata.wav_path.read_bytes(), duplicate_wav.read_bytes())
        self.assertEqual(self.host.modified_audio_asset_ids, (duplicate.asset_id,))
        self.assertTrue(self.host.revert_audio(duplicate.asset_id, self._progress))

        self.assertEqual(
            self.host.browse_audio(
                search="", status="Modified", offset=0, limit=50
            ).total,
            0,
        )

        metadata = self.host.replace_audio(fixed.asset_id, supplied, self._progress)
        self.assertEqual(self.host.modified_audio_asset_ids, (fixed.asset_id,))
        modified = self.host.browse_audio(
            search="", status="Modified", offset=0, limit=50
        )
        self.assertEqual(modified.total, 1)
        self.assertEqual(modified.assets[0].asset_id, fixed.asset_id)
        self.assertEqual(
            self.host.browse_audio(
                search="", status="Modified", offset=0, limit=50,
                scope="streaming",
            ).total,
            0,
        )
        staged = self.host.prepare_audio(fixed.asset_id, self._progress)
        self.assertNotEqual(staged, supplied)
        self.assertTrue(staged.is_file())
        self.assertEqual(staged.read_bytes(), supplied.read_bytes())
        # metadata.wav_path is canonicalised by the backend while prepare_audio
        # returns the path as staged; resolve both so "the metadata points at the
        # staged file" holds under a symlinked (macOS) or short-name (Windows)
        # temp root.
        self.assertEqual(metadata.wav_path.resolve(), staged.resolve())
        self.assertTrue(
            any(stage == "Replacement staged" for stage, _done, _total in self.progress)
        )

        exported = self.root / "exported-current.wav"
        self.assertEqual(
            self.host.export_audio(fixed.asset_id, exported, self._progress),
            exported.resolve(),
        )
        self.assertEqual(exported.read_bytes(), supplied.read_bytes())
        plan = self.host.create_build_plan(
            self.root / "menu-back.recipe.json",
            purpose="Synthetic Audio panel project",
        )
        self.assertEqual(plan.asset.asset_id, fixed.asset_id)
        self.assertTrue(plan.recipe_path.is_file())

        self.assertTrue(self.host.revert_audio(fixed.asset_id, self._progress))
        self.assertEqual(self.host.modified_audio_asset_ids, ())
        self.assertEqual(
            self.host.browse_audio(
                search="", status="Modified", offset=0, limit=50
            ).total,
            0,
        )
        self.assertFalse(staged.exists())
        original = self.host.prepare_audio(fixed.asset_id, self._progress)
        self.assertEqual(original, self.service.original_path(fixed))
        self.assertTrue(original.is_file())
        self.assertFalse(self.host.revert_audio(fixed.asset_id, self._progress))

    def test_staged_tamper_and_export_overwrite_fail_closed(self) -> None:
        fixed = self.catalog.assets[1]
        supplied = _valid_menu_wav(self.root / "mine.wav")
        self.host.replace_audio(fixed.asset_id, supplied, self._progress)
        staged = self.host.prepare_audio(fixed.asset_id, self._progress)
        staged.write_bytes(staged.read_bytes()[:-2])
        with self.assertRaises(ValidationError):
            self.host.create_build_plan(
                self.root / "tampered.recipe.json", purpose="must fail"
            )
        destination = self.root / "exists.wav"
        destination.write_bytes(b"mine")
        with self.assertRaises(ValidationError):
            self.host.export_audio(fixed.asset_id, destination, self._progress)

    def test_collection_export_labels_current_replacement_and_never_mutates_project(
        self,
    ) -> None:
        fixed = self.catalog.assets[1]
        supplied = _valid_menu_wav(self.root / "collection-edit.wav")
        session = StudioSession(
            self.fixture.cache,
            object(),  # Audio-only projects do not consult the visual catalog.
            root=self.root / "sessions",
            session_id="audio-collection",
        )
        session.attach_audio_service(self.service)
        self.assertTrue(session.replace_audio(fixed, supplied).modified)
        before = (
            session.modified_count,
            session.modified_audio_asset_ids,
            session.can_undo,
        )
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
        )
        facade._audio_catalog = self.catalog
        facade._audio_service = self.service
        facade._session = session

        destination = self.root / "modified-audio.zip"
        self.assertEqual(
            facade.export_audio_bundle(
                search="",
                status="Modified",
                scope="standalone",
                family=None,
                meaning_status="menu_back_route_runtime_unproved",
                destination=destination,
                output_format="wav",
                bundle_name="Modified project audio",
                progress=self._progress,
            ),
            destination.resolve(),
        )
        self.assertEqual(
            (
                session.modified_count,
                session.modified_audio_asset_ids,
                session.can_undo,
            ),
            before,
        )
        with zipfile.ZipFile(destination) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["record_count"], 1)
            self.assertEqual(manifest["artifact_kind"], "local_audio_collection")
            self.assertFalse(manifest["shareable_project"])
            self.assertFalse(manifest["contains_retail_derived"])
            self.assertTrue(manifest["contains_user_replacements"])
            record = manifest["records"][0]
            self.assertEqual(record["stable_id"], fixed.asset_id)
            self.assertEqual(record["content_origin"], "user_replacement")
            self.assertEqual(record["metadata"]["current_status"], "Modified")
            self.assertEqual(archive.read(record["path"]), supplied.read_bytes())

        project = self.root / "after-collection.2k5mod"
        # Token sealing has its own hostile suite; this UI fixture issues a
        # minimal in-memory stand-in so the archive UX can stay retail-free.
        with patch(
            "mod_editor.studio.project_archive.require_authorized_pcm16_wav",
            side_effect=lambda token: token,
        ):
            session.save_shareable_project(project)
        with zipfile.ZipFile(project) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 2)
            self.assertNotIn("manifest.json", names)
            self.assertFalse(any("collection" in name for name in names))
            project_wav = next(name for name in names if name.endswith(".wav"))
            self.assertEqual(archive.read(project_wav), supplied.read_bytes())

        staged = session.current_audio_path(fixed)
        staged.write_bytes(staged.read_bytes()[:-2])
        refused = self.root / "tampered-current.wav"
        with self.assertRaisesRegex(ValidationError, "changed outside Mod Studio"):
            session.export_audio(fixed, refused)
        self.assertFalse(refused.exists())

    def test_exact_audio_selection_mixes_ordered_current_wavs_without_project_mutation(
        self,
    ) -> None:
        original, fixed = self.catalog.assets
        audio_range = self.catalog.streaming_ranges[0]
        supplied = _valid_menu_wav(self.root / "shortlist-edit.wav")
        range_supplied = _exact_streaming_range_wav(
            self.root / "shortlist-range-edit.wav", audio_range, 1_337
        )
        session = StudioSession(
            self.fixture.cache,
            object(),  # Audio-only projects do not consult the visual catalog.
            root=self.root / "selection-sessions",
            session_id="audio-selection",
        )
        session.attach_audio_service(self.service)
        self.assertTrue(session.replace_audio(fixed, supplied).modified)
        self.assertTrue(session.replace_audio(audio_range, range_supplied).modified)
        before = (
            session.modified_count,
            session.modified_audio_asset_ids,
            session.can_undo,
        )
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
        )
        facade._audio_catalog = self.catalog
        facade._audio_service = self.service
        facade._session = session

        selected_ids = (
            audio_range.asset_id,
            fixed.asset_id,
            original.asset_id,
        )
        destination = self.root / "ordered-selection.zip"
        self.assertEqual(
            facade.export_audio_selection(
                selected_ids,
                destination,
                bundle_name="Ordered audio shortlist",
                progress=self._progress,
            ),
            destination.resolve(),
        )
        self.assertEqual(
            (
                session.modified_count,
                session.modified_audio_asset_ids,
                session.can_undo,
            ),
            before,
        )
        with zipfile.ZipFile(destination) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["bundle_name"], "Ordered audio shortlist")
            self.assertFalse(manifest["shareable_project"])
            self.assertTrue(manifest["contains_retail_derived"])
            self.assertTrue(manifest["contains_user_replacements"])
            records = manifest["records"]
            self.assertEqual(
                tuple(record["stable_id"] for record in records), selected_ids
            )
            self.assertEqual(
                tuple(record["content_origin"] for record in records),
                ("user_replacement", "user_replacement", "retail_derived"),
            )
            self.assertEqual({record["format"] for record in records}, {"wav"})
            for record in records:
                self.assertEqual(archive.read(record["path"])[:4], b"RIFF")
            self.assertEqual(
                archive.read(records[0]["path"]), range_supplied.read_bytes()
            )
            self.assertEqual(archive.read(records[1]["path"]), supplied.read_bytes())

        matching_destination = self.root / "modified-range-selection.zip"
        self.assertEqual(
            facade.export_audio_bundle(
                search="",
                status="Modified",
                scope="streaming_ranges",
                family=None,
                destination=matching_destination,
                output_format="wav",
                bundle_name="Modified streaming audio",
                progress=self._progress,
            ),
            matching_destination.resolve(),
        )
        with zipfile.ZipFile(matching_destination) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["record_count"], 1)
            self.assertFalse(manifest["contains_retail_derived"])
            self.assertTrue(manifest["contains_user_replacements"])
            record = manifest["records"][0]
            self.assertEqual(record["stable_id"], audio_range.asset_id)
            self.assertEqual(record["content_origin"], "user_replacement")
            self.assertEqual(archive.read(record["path"]), range_supplied.read_bytes())

    def test_modified_streaming_collection_refuses_missing_staged_wav(self) -> None:
        audio_range = self.catalog.streaming_ranges[0]
        supplied = _exact_streaming_range_wav(
            self.root / "missing-range-edit.wav", audio_range, -2_048
        )
        session = StudioSession(
            self.fixture.cache,
            object(),
            root=self.root / "missing-range-sessions",
            session_id="missing-range",
        )
        session.attach_audio_service(self.service)
        self.assertTrue(session.replace_audio(audio_range, supplied).modified)
        session.current_audio_path(audio_range).unlink()
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
        )
        facade._audio_catalog = self.catalog
        facade._audio_service = self.service
        facade._session = session

        destination = self.root / "must-not-publish-missing-range.zip"
        with self.assertRaisesRegex(ValidationError, "changed outside Mod Studio"):
            facade.export_audio_selection(
                (audio_range.asset_id,),
                destination,
                bundle_name="Must not publish",
                progress=self._progress,
            )
        self.assertFalse(destination.exists())
        self.assertEqual(
            list(self.root.glob(".must-not-publish-missing-range.zip.exporting-*")),
            [],
        )

    def test_audio_selection_rejects_invalid_ids_before_creating_output(self) -> None:
        session = StudioSession(
            self.fixture.cache,
            object(),  # Audio-only projects do not consult the visual catalog.
            root=self.root / "selection-validation-sessions",
            session_id="audio-selection-validation",
        )
        session.attach_audio_service(self.service)
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
        )
        facade._audio_catalog = self.catalog
        facade._audio_service = self.service
        facade._session = session
        sound_id = self.catalog.assets[0].asset_id
        bank_id = self.catalog.streaming_banks[0].asset_id
        cases = (
            ((), "between 1 and 256"),
            ((sound_id, sound_id), "duplicate"),
            ((bank_id,), "complete streaming bank"),
            (("nfl2k5.audio.unknown",), "Unknown shortlisted"),
            (tuple(f"too-many-{index}" for index in range(257)), "between 1 and 256"),
        )
        exporters = (
            ("catalog", self.host.export_audio_selection),
            ("facade", facade.export_audio_selection),
        )
        for exporter_name, exporter in exporters:
            for case_index, (asset_ids, message) in enumerate(cases):
                destination = self.root / f"{exporter_name}-{case_index}.zip"
                with self.subTest(exporter=exporter_name, case=case_index):
                    with self.assertRaisesRegex(ValidationError, message):
                        exporter(
                            asset_ids,
                            destination,
                            bundle_name="Must not publish",
                            progress=self._progress,
                        )
                    self.assertFalse(destination.exists())

    def test_audio_selection_keeps_transactional_failure_and_no_overwrite_contract(
        self,
    ) -> None:
        original = self.catalog.assets[0]
        audio_range = self.catalog.streaming_ranges[0]
        existing = self.root / "existing-selection.zip"
        existing.write_bytes(b"keep me")
        with self.assertRaises(FileExistsError):
            self.host.export_audio_selection(
                (original.asset_id,),
                existing,
                bundle_name="No overwrite",
                progress=self._progress,
            )
        self.assertEqual(existing.read_bytes(), b"keep me")

        failed = self.root / "failed-selection.zip"
        with patch.object(
            self.host,
            "export_audio_range_wav",
            side_effect=ValidationError("synthetic decode failure"),
        ):
            with self.assertRaisesRegex(ValidationError, "synthetic decode failure"):
                self.host.export_audio_selection(
                    (original.asset_id, audio_range.asset_id),
                    failed,
                    bundle_name="Transactional failure",
                    progress=self._progress,
                )
        self.assertFalse(failed.exists())
        self.assertEqual(list(self.root.glob(".failed-selection.zip.exporting-*")), [])

    def test_streaming_collection_exports_every_filtered_range_as_verified_wav(
        self,
    ) -> None:
        destination = self.root / "soundtrack-ranges.zip"
        self.assertEqual(
            self.host.export_audio_bundle(
                search="",
                status=None,
                scope="streaming_ranges",
                family="music",
                destination=destination,
                output_format="wav",
                bundle_name="Soundtrack and music ranges",
                progress=self._progress,
            ),
            destination.resolve(),
        )
        with zipfile.ZipFile(destination) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["record_count"], 2)
            self.assertFalse(manifest["shareable_project"])
            self.assertTrue(manifest["contains_retail_derived"])
            self.assertFalse(manifest["contains_user_replacements"])
            self.assertEqual(
                {row["content_origin"] for row in manifest["records"]},
                {"retail_derived"},
            )
            for row in manifest["records"]:
                with archive.open(row["path"]) as payload:
                    self.assertEqual(payload.read(4), b"RIFF")

    def test_panel_uses_the_products_existing_pyqt5_binding(self) -> None:
        from PyQt5.QtWidgets import QWidget

        self.assertTrue(PYQT5_AVAILABLE)
        self.assertTrue(issubclass(AudioPanel, QWidget))

    def test_play_uses_only_a_controllable_no_terminal_helper(self) -> None:
        path = self.root / "preview.wav"

        def ffplay_only(name: str) -> str | None:
            return "/usr/bin/ffplay" if name == "ffplay" else None

        self.assertEqual(
            audio_player_command(path, ffplay_only),
            (
                "/usr/bin/ffplay",
                ("-nodisp", "-autoexit", "-loglevel", "error", str(path)),
            ),
        )
        self.assertIsNone(audio_player_command(path, lambda _name: None))


class AudioPanelOffscreenTests(unittest.TestCase):
    def test_widget_populates_pages_and_gates_edit_controls(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            _authorize_synthetic_fixture_audio(service)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            clipboard_patcher = patch(
                "mod_editor.gui.audio_panel_qt.QApplication.clipboard"
            )
            clipboard = clipboard_patcher.start()
            self.addCleanup(clipboard_patcher.stop)
            panel = AudioPanel(host, page_size=1)
            application.processEvents()
            clipboard.assert_not_called()
            self.assertTrue(panel.labeled_only_filter.isHidden())
            self.assertFalse(panel.labeled_only_filter.isEnabled())
            self.assertEqual(
                AUDIO_PLAYABLE_DEFAULT_SCOPE_CONTRACT,
                "default_mixed_54421_standalone_then_streaming_ranges",
            )
            self.assertEqual(panel.scope_filter.currentIndex(), 0)
            self.assertEqual(panel.scope_filter.currentData(), PLAYABLE_AUDIO_SCOPE_ID)
            self.assertEqual(
                panel.scope_filter.currentText(), "All Playable Audio (54,421)"
            )
            self.assertIn("850 standalone cues first", panel.scope_filter.accessibleDescription())
            self.assertIn("53,571 playable streaming ranges", panel.scope_filter.accessibleDescription())
            self.assertFalse(panel.meaning_filter.isEnabled())
            combined_families = {
                panel.family_filter.itemData(index): panel.family_filter.itemText(index)
                for index in range(1, panel.family_filter.count())
            }
            self.assertEqual(
                combined_families,
                {
                    "frontend_ui": "Frontend & franchise UI (36)",
                    "field_crowd_player": "On-field, crowd & player state (13)",
                    "team_crowd": "Team crowd variations (680)",
                    "crib_minigames": "Crib, minigames & trivia (121)",
                    "music": "Soundtrack & music (136)",
                    "commentary": "Commentary & speech (52,940)",
                    "stadium": "Stadium, PA & coach (9)",
                    "presentation": "Broadcast & presentation (482)",
                    "ambient": "Ambient & diagnostics (4)",
                },
            )
            self.assertTrue(panel.subtitle_label.wordWrap())
            self.assertIn("play cues and ranges", panel.subtitle_label.text())
            self.assertEqual(panel.layout().itemAt(0).layout().stretch(0), 1)
            self.assertIn(
                "QPushButton#audioPrimaryButton:disabled", panel.styleSheet()
            )
            self.assertEqual(panel.table.rowCount(), 1)
            self.assertEqual(panel.page.total, 4)
            self.assertEqual(
                panel.count_label.text(),
                "4 shown • 54,421 playable",
            )
            for column in range(panel.table.columnCount()):
                item = panel.table.item(0, column)
                self.assertIn(item.text(), item.toolTip())
            self.assertTrue(panel._selected_asset().editable)
            self.assertTrue(panel.replace_button.isEnabled())
            self.assertFalse(panel.pack_path_card.isHidden())
            self.assertEqual(
                panel.pack_path_label.text(),
                "replacements/001__selected-audio.wav",
            )
            self.assertTrue(panel.copy_pack_path_button.isEnabled())
            self.assertEqual(
                panel.copy_pack_path_button.accessibleName(),
                "Copy the all-850 audio replacement pack path",
            )
            self.assertEqual(
                panel.copy_pack_path_button.shortcut().toString(),
                "Ctrl+Shift+C",
            )
            panel.copy_pack_path_button.click()
            clipboard.assert_called_once_with()
            clipboard.return_value.setText.assert_called_once_with(
                "replacements/001__selected-audio.wav"
            )
            self.assertEqual(
                panel.progress_label.text(),
                "Copied all-850 replacement pack path",
            )
            self.assertIn("physical slot", panel.note_label.text())
            self.assertIn("exact physical slot", panel.table.item(0, 5).toolTip())
            self.assertIn("runtime cue meaning unproved", panel.table.item(0, 5).toolTip())
            panel._next_page()
            application.processEvents()
            clipboard.assert_called_once_with()
            self.assertTrue(panel._selected_asset().editable)
            self.assertTrue(panel.replace_button.isEnabled())
            self.assertEqual(
                panel.pack_path_label.text(),
                "replacements/002__selected-audio.wav",
            )
            self.assertIn("exact Menu Back slot", panel.table.item(0, 5).toolTip())
            self.assertFalse(panel.revert_button.isEnabled())
            self.assertGreaterEqual(panel.status_filter.findData("Modified"), 0)
            self.assertIn("staged WAVs", panel.status_filter.toolTip())
            panel._next_page()
            application.processEvents()
            self.assertEqual(panel._selected_asset(), catalog.streaming_ranges[0])
            self.assertTrue(panel.play_button.isEnabled())
            self.assertTrue(panel.export_button.isEnabled())
            self.assertTrue(panel.replace_button.isEnabled())
            self.assertFalse(panel.revert_button.isEnabled())
            self.assertTrue(panel.load_waveform_button.isEnabled())
            self.assertEqual(panel.export_button.text(), "Export WAV / Raw")
            panel.family_filter.setCurrentIndex(
                panel.family_filter.findData("music")
            )
            application.processEvents()
            self.assertEqual(panel.page.total, len(catalog.streaming_ranges))
            self.assertEqual(panel._selected_asset(), catalog.streaming_ranges[0])
            self.assertEqual(host._replacements, {})
            panel.deleteLater()
            application.processEvents()

    def test_meaning_filter_is_accessible_scope_bound_and_review_stable(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)

            self.assertEqual(panel.meaning_filter.count(), 4)
            self.assertEqual(
                panel.meaning_filter.accessibleName(),
                "Standalone audio meaning confidence filter",
            )
            self.assertIn("Separate from edit status", panel.meaning_filter.accessibleDescription())
            self.assertEqual(panel.meaning_filter.itemText(0), "All meaning confidence (850)")
            self.assertEqual(
                panel.meaning_filter.itemData(1),
                "menu_back_route_runtime_unproved",
            )
            self.assertEqual(
                panel.meaning_filter.itemData(2),
                "reviewed_label_runtime_meaning_unproved",
            )
            self.assertEqual(
                panel.meaning_filter.itemData(3),
                "provisional_label_runtime_meaning_unproved",
            )
            self.assertEqual(panel.scope_filter.currentData(), PLAYABLE_AUDIO_SCOPE_ID)
            self.assertFalse(panel.meaning_filter.isEnabled())
            self.assertIsNone(panel.meaning_filter.currentData())

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("standalone")
            )
            application.processEvents()
            self.assertTrue(panel.meaning_filter.isEnabled())

            panel.meaning_filter.setCurrentIndex(1)
            application.processEvents()
            self.assertEqual(panel.page.total, 1)
            self.assertEqual(
                panel.meaning_filter.currentData(),
                "menu_back_route_runtime_unproved",
            )
            panel._toggle_audio_shortlist()
            panel._toggle_audio_shortlist_review()
            self.assertTrue(panel._shortlist_reviewing)
            self.assertFalse(panel.meaning_filter.isEnabled())
            self.assertEqual(
                panel.meaning_filter.currentData(),
                "menu_back_route_runtime_unproved",
            )
            panel._toggle_audio_shortlist_review()
            self.assertFalse(panel._shortlist_reviewing)
            self.assertTrue(panel.meaning_filter.isEnabled())
            self.assertEqual(
                panel.meaning_filter.currentData(),
                "menu_back_route_runtime_unproved",
            )

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming")
            )
            application.processEvents()
            self.assertFalse(panel.meaning_filter.isEnabled())
            self.assertIsNone(panel.meaning_filter.currentData())
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("standalone")
            )
            application.processEvents()
            self.assertTrue(panel.meaning_filter.isEnabled())
            self.assertIsNone(panel.meaning_filter.currentData())
            panel.deleteLater()
            application.processEvents()

    def test_add_all_matching_builds_reviewed_152_in_canonical_v2_order(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            rows = _reviewed_standalone_assets(catalog.assets[0], 152)
            browse_calls: list[dict[str, object]] = []
            template_calls: list[dict[str, object]] = []

            def browse_audio(**kwargs: object) -> StudioAudioPage:
                browse_calls.append(dict(kwargs))
                meaning = kwargs["meaning_status"]
                filtered = rows if meaning in (
                    None, "reviewed_label_runtime_meaning_unproved"
                ) else ()
                offset = int(kwargs["offset"])
                limit = int(kwargs["limit"])
                return StudioAudioPage(
                    tuple(filtered[offset:offset + limit]),
                    len(filtered),
                    offset if filtered else 0,
                    limit,
                )

            def export_template(
                destination: Path, **kwargs: object
            ) -> SimpleNamespace:
                template_calls.append({"destination": destination, **kwargs})
                return SimpleNamespace(path=destination)

            host.browse_audio = browse_audio  # type: ignore[method-assign]
            host.export_audio_replacement_template = export_template  # type: ignore[attr-defined]
            panel = AudioPanel(host, page_size=50)
            project_mutations: list[tuple[str, str]] = []
            panel.audio_modified.connect(
                lambda asset_id: project_mutations.append(("modified", asset_id))
            )
            panel.audio_reverted.connect(
                lambda asset_id: project_mutations.append(("reverted", asset_id))
            )

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("standalone")
            )
            application.processEvents()

            panel.meaning_filter.setCurrentIndex(
                panel.meaning_filter.findData(
                    "reviewed_label_runtime_meaning_unproved"
                )
            )
            application.processEvents()
            self.assertEqual(panel.page.total, 152)
            self.assertEqual(
                panel.shortlist_matching_button.accessibleName(),
                "Add every matching playable sound to the audio shortlist",
            )
            self.assertTrue(panel.shortlist_matching_button.isEnabled())
            self.assertEqual(
                panel.shortlist_matching_button.text(), "Add all matching (152)"
            )
            panel.shortlist_matching_button.click()
            self.assertEqual(
                panel._shortlisted_audio_ids(),
                tuple(asset.asset_id for asset in rows),
            )
            self.assertEqual(browse_calls[-1]["offset"], 0)
            self.assertEqual(browse_calls[-1]["limit"], 256)
            self.assertEqual(browse_calls[-1]["scope"], "standalone")
            self.assertEqual(
                browse_calls[-1]["meaning_status"],
                "reviewed_label_runtime_meaning_unproved",
            )
            self.assertIn("★ Selected", panel.table.item(0, 5).text())
            self.assertEqual(project_mutations, [])
            self.assertEqual(host._replacements, {})

            panel.replacement_pack_contents.setCurrentIndex(
                panel.replacement_pack_contents.findData("shortlist")
            )
            self.assertTrue(panel.export_replacement_template_button.isEnabled())
            self.assertEqual(
                panel.export_replacement_template_button.text(),
                "Export shortlist template (152)…",
            )
            destination = root / "reviewed-152-template"

            def run_now(operation: object, complete: object) -> None:
                value = operation(lambda *_args: None)  # type: ignore[operator]
                complete(value)  # type: ignore[operator]

            panel._run = run_now  # type: ignore[method-assign]
            with patch(
                "mod_editor.gui.audio_panel_qt.QFileDialog.getSaveFileName",
                return_value=(str(destination), "New template folder (*)"),
            ), patch("mod_editor.gui.audio_panel_qt.QMessageBox.information"):
                panel._export_audio_replacement_template()
            self.assertEqual(
                template_calls[-1]["asset_ids"],
                tuple(asset.asset_id for asset in rows),
            )
            self.assertNotIn("complete_standalone", template_calls[-1])
            self.assertEqual(project_mutations, [])
            self.assertEqual(host._replacements, {})
            panel.deleteLater()
            application.processEvents()

    def test_add_all_matching_collapses_existing_ids_and_is_cap_atomic(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            project_mutations: list[tuple[str, str]] = []
            panel.audio_modified.connect(
                lambda asset_id: project_mutations.append(("modified", asset_id))
            )
            panel.audio_reverted.connect(
                lambda asset_id: project_mutations.append(("reverted", asset_id))
            )

            first_id = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            panel._add_all_matching_audio_to_shortlist()
            self.assertEqual(
                panel._shortlisted_audio_ids(),
                tuple(asset.asset_id for asset in catalog.playable_assets),
            )
            self.assertEqual(panel._shortlisted_audio_ids().count(first_id), 1)
            self.assertEqual(project_mutations, [])

            panel._clear_audio_shortlist()
            fillers = _reviewed_standalone_assets(
                catalog.assets[0], 255, start_chunk=2_000
            )
            panel._audio_shortlist.update(
                (asset.asset_id, asset) for asset in fillers
            )
            panel._update_audio_shortlist_actions()
            before = panel._shortlisted_audio_ids()
            self.assertTrue(panel.shortlist_matching_button.isEnabled())
            with patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.information"
            ) as information:
                panel._add_all_matching_audio_to_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), before)
            self.assertIn("No sounds were added", information.call_args.args[2])
            self.assertEqual(host._replacements, {})
            panel.deleteLater()
            application.processEvents()

    def test_add_all_matching_disables_over_256_and_wrong_scopes(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(
                catalog,
                service,
                root / "replacements",
                universal_index=_RawResourceIndex(),  # type: ignore[arg-type]
            )
            panel = AudioPanel(host, page_size=2)

            panel.page = AudioPage(panel.page.assets, 257, 0, panel.page.limit)
            panel._update_audio_shortlist_actions()
            self.assertFalse(panel.shortlist_matching_button.isEnabled())
            self.assertIn("narrow search", panel.shortlist_matching_button.toolTip())
            self.assertIn("256 or fewer", panel.shortlist_matching_button.toolTip())

            for scope, tooltip_text in (
                ("streaming", "Complete streaming banks"),
                ("raw_containers", "Raw BANK/ABNK/WBNK"),
            ):
                panel.scope_filter.setCurrentIndex(
                    panel.scope_filter.findData(scope)
                )
                application.processEvents()
                self.assertFalse(panel.shortlist_matching_button.isEnabled())
                self.assertIn(tooltip_text, panel.shortlist_matching_button.toolTip())
                before = panel._shortlisted_audio_ids()
                panel._add_all_matching_audio_to_shortlist()
                self.assertEqual(panel._shortlisted_audio_ids(), before)
            panel.deleteLater()
            application.processEvents()

    def test_add_all_matching_refuses_hostile_count_duplicates_and_types(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            original_browse = host.browse_audio
            original_ids = panel._shortlisted_audio_ids()
            hostile_pages = (
                StudioAudioPage((catalog.assets[0],), 1, 0, 256),
                StudioAudioPage(
                    (catalog.assets[0], catalog.assets[0]), 2, 0, 256
                ),
                StudioAudioPage((catalog.streaming_banks[0],) * 2, 2, 0, 256),
            )

            with patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.warning"
            ) as warning:
                for hostile in hostile_pages:
                    host.browse_audio = (  # type: ignore[method-assign]
                        lambda **_kwargs: hostile
                    )
                    panel._add_all_matching_audio_to_shortlist()
                    self.assertEqual(panel._shortlisted_audio_ids(), original_ids)
            self.assertEqual(warning.call_count, len(hostile_pages))
            self.assertEqual(host._replacements, {})
            host.browse_audio = original_browse  # type: ignore[method-assign]
            panel.deleteLater()
            application.processEvents()

    def test_add_all_matching_is_disabled_during_review_busy_and_source_reset(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            panel._add_all_matching_audio_to_shortlist()
            selected = panel._shortlisted_audio_ids()

            panel._toggle_audio_shortlist_review()
            self.assertTrue(panel._shortlist_reviewing)
            self.assertFalse(panel.shortlist_matching_button.isEnabled())
            self.assertIn("Return to the audio browser", panel.shortlist_matching_button.toolTip())
            panel._add_all_matching_audio_to_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), selected)
            panel._toggle_audio_shortlist_review()

            panel._busy = True
            panel._update_audio_shortlist_actions()
            self.assertFalse(panel.shortlist_matching_button.isEnabled())
            self.assertIn("current audio task", panel.shortlist_matching_button.toolTip())
            panel._busy = False
            panel.reset_for_source()
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertTrue(panel.shortlist_matching_button.isEnabled())

            host.source_ready = False
            panel._update_audio_shortlist_actions()
            self.assertFalse(panel.shortlist_matching_button.isEnabled())
            self.assertIn("Load your NFL 2K5 XISO", panel.shortlist_matching_button.toolTip())
            self.assertEqual(host._replacements, {})
            panel.deleteLater()
            application.processEvents()

    def test_matching_export_forwards_meaning_filter_and_names_bundle(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("standalone")
            )
            application.processEvents()
            panel.meaning_filter.setCurrentIndex(
                panel.meaning_filter.findData(
                    "menu_back_route_runtime_unproved"
                )
            )
            application.processEvents()
            self.assertEqual(panel.page.total, 1)
            self.assertTrue(panel.export_matching_button.isEnabled())
            destination = root / "menu-back-filter.zip"

            def run_now(operation: object, complete: object) -> None:
                result = operation(lambda *_args: None)  # type: ignore[operator]
                complete(result)  # type: ignore[operator]

            panel._run = run_now  # type: ignore[method-assign]
            with patch.object(
                host, "export_audio_bundle", return_value=destination
            ) as export_bundle, patch(
                "mod_editor.gui.audio_panel_qt.QFileDialog.getSaveFileName",
                return_value=(str(destination), "Current WAV audio ZIP (*.zip)"),
            ), patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.information"
            ):
                panel._export_matching_audio()
            export_bundle.assert_called_once()
            call = export_bundle.call_args.kwargs
            self.assertEqual(
                call["meaning_status"], "menu_back_route_runtime_unproved"
            )
            self.assertEqual(call["scope"], "standalone")
            self.assertIn("Menu Back route (1)", call["bundle_name"])
            self.assertNotIn("All meaning confidence", call["bundle_name"])
            panel.deleteLater()
            application.processEvents()

    def test_streaming_rows_show_compact_truth_with_full_tooltips(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming")
            )
            application.processEvents()
            bank = panel._selected_asset()
            self.assertEqual(panel.table.item(0, 2).text(), "Raw bank (.bin)")
            self.assertIn("Indexed Xbox IMA bank", panel.table.item(0, 2).toolTip())
            self.assertEqual(panel.table.item(0, 5).text(), "Export-only")
            self.assertEqual(
                panel.table.item(0, 5).toolTip(),
                "Export-only • Replace Coming Soon",
            )
            self.assertFalse(panel.replace_button.isEnabled())
            self.assertTrue(panel.pack_path_card.isHidden())
            self.assertFalse(panel.copy_pack_path_button.isEnabled())
            self.assertNotEqual(panel.note_label.text(), bank.action_note)
            self.assertEqual(panel.note_label.toolTip(), bank.action_note)

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            application.processEvents()
            audio_range = panel._selected_asset()
            self.assertEqual(
                panel.table.item(0, 2).text(), f"WAV • {audio_range.channels}ch"
            )
            self.assertIn("Hz", panel.table.item(0, 2).toolTip())
            self.assertTrue(panel.replace_button.isEnabled())
            self.assertTrue(panel.pack_path_card.isHidden())
            self.assertFalse(panel.copy_pack_path_button.isEnabled())
            self.assertEqual(panel.note_label.text(), audio_range.action_note)
            self.assertEqual(panel.note_label.toolTip(), audio_range.action_note)
            self.assertEqual(panel.table.item(0, 5).text(), "Editable")
            for column in range(panel.table.columnCount()):
                self.assertTrue(panel.table.item(0, column).toolTip())

            panel.deleteLater()
            application.processEvents()

    def test_dense_detail_scrolls_with_actions_pinned_and_resets_on_selection(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            owner_tail = tuple(
                "nfl2k5.audio.fixture.logical-owner."
                f"{index:02d}.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                for index in range(30)
            )

            def affected(asset_id: str) -> tuple[str, ...]:
                return (asset_id, *owner_tail)

            service.audio_affected_asset_ids = affected  # type: ignore[method-assign]
            host = CatalogAudioPanelHost(
                catalog, service, root / "replacements"
            )
            panel = AudioPanel(host, page_size=2)
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            application.processEvents()

            scroll = panel.detail_scroll
            content = scroll.widget()
            self.assertTrue(scroll.widgetResizable())
            self.assertEqual(
                scroll.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff
            )
            for label in (
                panel.asset_title,
                panel.status_label,
                panel.metadata_label,
                panel.ownership_label,
                panel.note_label,
                panel.pack_path_card,
            ):
                self.assertTrue(content.isAncestorOf(label))
            for pinned in (
                panel.drop_zone,
                panel.play_button,
                panel.export_button,
                panel.replace_button,
                panel.revert_button,
            ):
                self.assertFalse(content.isAncestorOf(pinned))
            for label in (
                panel.asset_title,
                panel.metadata_label,
                panel.ownership_label,
                panel.note_label,
                panel.pack_path_label,
            ):
                flags = label.textInteractionFlags()
                self.assertTrue(flags & Qt.TextSelectableByMouse)
                self.assertTrue(flags & Qt.TextSelectableByKeyboard)

            self.assertIn(owner_tail[-1], panel.ownership_label.text())
            self.assertLessEqual(panel.detail_card.minimumSizeHint().width(), 380)
            self.assertLessEqual(panel.detail_card.minimumSizeHint().height(), 420)

            scroll.setFixedSize(320, 180)
            panel.show()
            application.processEvents()
            bar = scroll.verticalScrollBar()
            self.assertGreater(bar.maximum(), 0)

            before = host.modified_audio_asset_ids
            bar.setValue(bar.maximum())
            panel.table.selectRow(1)
            application.processEvents()

            self.assertGreater(bar.maximum(), 0)
            self.assertEqual(bar.value(), 0)
            self.assertEqual(host.modified_audio_asset_ids, before)
            self.assertTrue(panel.replace_button.isEnabled())

            panel.close()
            panel.deleteLater()
            application.processEvents()

    def test_audio_toolbars_reflow_within_the_minimum_window_workspace(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtCore import QRect
        from PyQt5.QtWidgets import QApplication, QGridLayout

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(
                catalog, service, root / "replacements"
            )
            panel = AudioPanel(host, page_size=2)
            panel.show()
            application.processEvents()

            self.assertIsInstance(panel.filters_layout, QGridLayout)
            self.assertIsInstance(panel.shortlist_actions_layout, QGridLayout)
            filter_positions = {
                panel.search: (0, 0, 1, 2),
                panel.scope_filter: (0, 2, 1, 1),
                panel.family_filter: (1, 0, 1, 1),
                panel.status_filter: (1, 1, 1, 1),
                panel.meaning_filter: (1, 2, 1, 1),
            }
            shortlist_positions = {
                panel.shortlist_toggle_button: (0, 0, 1, 1),
                panel.shortlist_page_button: (0, 1, 1, 1),
                panel.shortlist_matching_button: (0, 2, 1, 2),
                panel.shortlist_review_button: (1, 0, 1, 1),
                panel.shortlist_count_label: (1, 1, 1, 1),
                panel.shortlist_clear_button: (1, 2, 1, 1),
                panel.export_shortlist_button: (1, 3, 1, 1),
            }
            for widget, expected in filter_positions.items():
                index = panel.filters_layout.indexOf(widget)
                self.assertGreaterEqual(index, 0)
                self.assertEqual(
                    panel.filters_layout.getItemPosition(index), expected
                )
            for widget, expected in shortlist_positions.items():
                index = panel.shortlist_actions_layout.indexOf(widget)
                self.assertGreaterEqual(index, 0)
                self.assertEqual(
                    panel.shortlist_actions_layout.getItemPosition(index),
                    expected,
                )

            longest_labels = {
                panel.shortlist_toggle_button: "Remove selected sound",
                panel.shortlist_page_button: "Add this page (200)",
                panel.shortlist_matching_button: "Add all matching (256)",
                panel.shortlist_review_button: "Review selected (256)",
                panel.shortlist_count_label: "Selected 256 / 256",
                panel.shortlist_clear_button: "Undo",
                panel.export_shortlist_button: "Export selected WAVs (256)…",
            }
            for widget, label in longest_labels.items():
                widget.setText(label)
                widget.updateGeometry()
            panel.filters_layout.invalidate()
            panel.shortlist_actions_layout.invalidate()
            panel.layout().invalidate()
            panel.updateGeometry()
            application.processEvents()
            panel.adjustSize()
            application.processEvents()

            self.assertLessEqual(
                panel.minimumSizeHint().width(), AUDIO_TOOLBAR_TARGET_WIDTH
            )
            panel.resize(
                AUDIO_TOOLBAR_TARGET_WIDTH,
                max(950, panel.minimumSizeHint().height()),
            )
            panel.layout().setGeometry(
                QRect(0, 0, panel.width(), panel.height())
            )
            panel.filters_layout.activate()
            panel.shortlist_actions_layout.activate()
            application.processEvents()

            expected_inner_width = AUDIO_TOOLBAR_TARGET_WIDTH - 48
            self.assertEqual(
                panel.filters_layout.geometry().width(), expected_inner_width
            )
            self.assertEqual(
                panel.shortlist_actions_layout.geometry().width(),
                expected_inner_width,
            )
            controls = tuple(filter_positions) + tuple(shortlist_positions)
            for widget in controls:
                self.assertFalse(widget.isHidden())
                self.assertGreaterEqual(
                    widget.width(), widget.minimumSizeHint().width()
                )
                self.assertTrue(panel.rect().contains(widget.geometry()))
            for index, first in enumerate(controls):
                for second in controls[index + 1:]:
                    self.assertFalse(
                        first.geometry().intersects(second.geometry()),
                        f"{first.objectName()} overlaps {second.objectName()}",
                    )

            panel.close()
            panel.deleteLater()
            application.processEvents()

    def test_preview_callbacks_are_bound_to_selection_and_source_epoch(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(
                catalog, service, root / "replacements"
            )
            panel = AudioPanel(host, page_size=2)
            queued: list[tuple[object, object, object]] = []
            panel._run = (  # type: ignore[method-assign]
                lambda operation, complete, **kwargs: queued.append(
                    (operation, complete, kwargs["on_error"])
                )
            )

            first_id = panel.selected_asset_id
            self.assertIsNotNone(first_id)
            with patch(
                "mod_editor.gui.audio_panel_qt.audio_player_command"
            ) as player, patch.object(
                panel._audio_process, "start"
            ) as start, patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.warning"
            ) as warning:
                panel._play_selected()
                first_request = panel._preview_request
                self.assertIsNotNone(first_request)
                self.assertEqual(first_request[1], first_id)
                self.assertEqual(len(queued), 1)

                panel.table.selectRow(1)
                application.processEvents()
                panel.table.selectRow(0)
                application.processEvents()
                self.assertEqual(panel.selected_asset_id, first_id)
                self.assertIsNone(panel._preview_request)
                queued[0][1](root / "stale-after-aba.wav")  # type: ignore[operator]
                queued[0][2]("stale ABA preparation error")  # type: ignore[operator]
                player.assert_not_called()
                start.assert_not_called()
                warning.assert_not_called()

                panel._play_selected()
                second_request = panel._preview_request
                self.assertIsNotNone(second_request)
                self.assertEqual(second_request[1], first_id)
                self.assertGreater(second_request[0], first_request[0])
                self.assertEqual(len(queued), 2)
                panel.invalidate_preview_for_source_change()
                self.assertEqual(panel.selected_asset_id, first_id)
                self.assertIsNone(panel._preview_request)
                queued[1][1](root / "stale-after-source.wav")  # type: ignore[operator]
                queued[1][2]("stale source preparation error")  # type: ignore[operator]
                player.assert_not_called()
                start.assert_not_called()
                warning.assert_not_called()

            panel.deleteLater()
            application.processEvents()

    def test_same_selection_refresh_preserves_preview_and_new_row_stops_it(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtCore import QProcess
        from PyQt5.QtWidgets import QApplication

        player = shutil.which("sleep")
        if player is None:
            self.skipTest("sleep helper is unavailable")
        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            panel = AudioPanel(
                CatalogAudioPanelHost(catalog, service, root / "replacements"),
                page_size=2,
            )
            panel._preview_epoch += 1
            request = (panel._preview_epoch, str(panel.selected_asset_id))
            panel._preview_request = request
            panel._playing_preview_request = request
            panel._audio_process.start(player, ["10"])
            self.assertTrue(panel._audio_process.waitForStarted(2_000))
            panel.play_button.setText("Stop")

            panel.refresh(keep_selection=True)
            application.processEvents()
            self.assertEqual(panel._audio_process.state(), QProcess.Running)
            self.assertEqual(panel._preview_request, request)

            panel.table.selectRow(1)
            application.processEvents()
            if panel._audio_process.state() != QProcess.NotRunning:
                panel._audio_process.waitForFinished(2_000)
            application.processEvents()
            self.assertEqual(panel._audio_process.state(), QProcess.NotRunning)
            self.assertIsNone(panel._preview_request)
            self.assertEqual(panel.play_button.text(), "Play")

            panel.deleteLater()
            application.processEvents()

    def test_new_selection_queues_one_click_play_until_old_process_stops(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtCore import QProcess
        from PyQt5.QtWidgets import QApplication

        class FakeProcess:
            def __init__(self) -> None:
                self.current_state = QProcess.Running
                self.kills = 0
                self.starts: list[tuple[str, list[str]]] = []

            def state(self) -> object:
                return self.current_state

            def kill(self) -> None:
                self.kills += 1

            def start(self, program: str, arguments: list[str]) -> None:
                self.starts.append((program, arguments))
                self.current_state = QProcess.Running

            def errorString(self) -> str:
                return ""

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            panel = AudioPanel(
                CatalogAudioPanelHost(catalog, service, root / "replacements"),
                page_size=2,
            )
            old_request = (1, str(panel.selected_asset_id))
            panel._preview_epoch = 1
            panel._preview_request = old_request
            panel._playing_preview_request = old_request
            fake = FakeProcess()
            panel._audio_process = fake  # type: ignore[assignment]

            panel.table.selectRow(1)
            application.processEvents()
            new_id = panel.selected_asset_id
            self.assertNotEqual(new_id, old_request[1])
            self.assertGreaterEqual(fake.kills, 1)
            panel._run = (  # type: ignore[method-assign]
                lambda _operation, complete, **_kwargs: complete(root / "ready.wav")
            )
            with patch(
                "mod_editor.gui.audio_panel_qt.audio_player_command",
                return_value=("/fixture/player", ("--play",)),
            ):
                panel._play_selected()
            new_request = panel._preview_request
            self.assertIsNotNone(new_request)
            self.assertEqual(new_request[1], new_id)
            self.assertEqual(fake.starts, [])
            self.assertIsNotNone(panel._prepared_preview)

            # FailedToStart reaches NotRunning and emits errorOccurred without
            # a later finished signal. The stale old request must still drain
            # and start the already-prepared current request.
            fake.current_state = QProcess.NotRunning
            panel._audio_process_failed(object())
            self.assertEqual(
                fake.starts, [("/fixture/player", ["--play"])]
            )
            self.assertEqual(panel._playing_preview_request, new_request)
            self.assertEqual(panel.play_button.text(), "Stop")

            # A normal killed/crashed old player does emit finished. Repeat the
            # switch in the other direction and prove that queue-drain path too.
            panel.table.selectRow(0)
            application.processEvents()
            next_id = panel.selected_asset_id
            with patch(
                "mod_editor.gui.audio_panel_qt.audio_player_command",
                return_value=("/fixture/player", ("--play-next",)),
            ):
                panel._play_selected()
            next_request = panel._preview_request
            self.assertIsNotNone(next_request)
            self.assertEqual(next_request[1], next_id)
            self.assertEqual(len(fake.starts), 1)
            self.assertIsNotNone(panel._prepared_preview)

            fake.current_state = QProcess.NotRunning
            panel._audio_process_finished()
            self.assertEqual(
                fake.starts,
                [
                    ("/fixture/player", ["--play"]),
                    ("/fixture/player", ["--play-next"]),
                ],
            )
            self.assertEqual(panel._playing_preview_request, next_request)

            panel.deleteLater()
            application.processEvents()

    def test_missing_controllable_player_fails_actionably_without_starting(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            panel = AudioPanel(
                CatalogAudioPanelHost(catalog, service, root / "replacements"),
                page_size=2,
            )
            errors: list[str] = []
            panel.error_raised.connect(errors.append)
            panel._run = (  # type: ignore[method-assign]
                lambda _operation, complete, **_kwargs: complete(root / "ready.wav")
            )
            with patch(
                "mod_editor.gui.audio_panel_qt.audio_player_command",
                return_value=None,
            ), patch.object(panel._audio_process, "start") as start, patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.warning"
            ) as warning:
                panel._play_selected()

            start.assert_not_called()
            warning.assert_called_once()
            self.assertEqual(len(errors), 1)
            self.assertIn("Install ffplay, paplay, or aplay", errors[0])
            self.assertIn("cannot stop", errors[0])
            self.assertIsNone(panel._preview_request)
            self.assertEqual(panel.play_button.text(), "Play")

            panel.deleteLater()
            application.processEvents()

    def test_preview_preparation_error_clears_pending_lifecycle_state(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            panel = AudioPanel(
                CatalogAudioPanelHost(catalog, service, root / "replacements"),
                page_size=2,
            )

            def fail(
                _operation: object,
                _complete: object,
                *,
                on_error: object,
            ) -> None:
                on_error("fixture preview preparation failed")  # type: ignore[operator]

            panel._run = fail  # type: ignore[method-assign]
            with patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.warning"
            ) as warning:
                panel._play_selected()

            warning.assert_called_once()
            self.assertIn(
                "fixture preview preparation failed", warning.call_args.args[2]
            )
            self.assertIsNone(panel._preview_request)
            self.assertIsNone(panel._prepared_preview)
            self.assertEqual(panel.play_button.text(), "Play")

            panel.deleteLater()
            application.processEvents()

    def test_raw_bank_containers_use_universal_index_and_safe_export(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            index = _RawResourceIndex()
            host = CatalogAudioPanelHost(
                catalog,
                service,
                root / "replacements",
                universal_index=index,  # type: ignore[arg-type]
            )
            panel = AudioPanel(host, page_size=2)
            project_mutations: list[tuple[str, str]] = []
            panel.audio_modified.connect(
                lambda asset_id: project_mutations.append(("modified", asset_id))
            )
            panel.audio_reverted.connect(
                lambda asset_id: project_mutations.append(("reverted", asset_id))
            )

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("raw_containers")
            )
            application.processEvents()
            self.assertEqual(panel.page.total, 9)
            self.assertEqual(panel.table.rowCount(), 2)
            self.assertEqual(
                {kind: sum(row.kind == kind for row in panel._raw_audio_containers)
                 for kind in ("BANK", "ABNK", "WBNK")},
                {"BANK": 3, "ABNK": 3, "WBNK": 3},
            )
            self.assertEqual(
                panel.count_label.text(),
                "9 shown • 9 raw BANK / ABNK / WBNK containers",
            )
            selected = panel._selected_asset()
            self.assertIsInstance(selected, UniversalAssetRecord)
            self.assertEqual(selected.asset_id, index.records[0].asset_id)
            self.assertEqual(panel.table.item(0, 2).text(), "Raw BANK")
            self.assertEqual(panel.table.item(0, 3).text(), "192 bytes")
            self.assertIn(selected.asset_id, panel.table.item(0, 0).toolTip())
            self.assertEqual(panel.table.item(0, 5).text(), "Export-only")
            self.assertFalse(panel.play_button.isEnabled())
            self.assertFalse(panel.replace_button.isEnabled())
            self.assertTrue(panel.pack_path_card.isHidden())
            self.assertFalse(panel.copy_pack_path_button.isEnabled())
            self.assertFalse(panel.shortlist_toggle_button.isEnabled())
            self.assertFalse(panel.shortlist_page_button.isEnabled())
            self.assertEqual(panel.export_button.text(), "Export Raw Container")
            self.assertIn("cannot be played", panel.note_label.text())

            panel._next_page()
            self.assertEqual(panel.offset, 2)
            self.assertTrue(panel.previous_button.isEnabled())
            panel.family_filter.setCurrentIndex(
                panel.family_filter.findData("WBNK")
            )
            application.processEvents()
            self.assertEqual(panel.page.total, 3)
            panel.search.setText("o3118")
            panel._filters_changed()
            application.processEvents()
            self.assertEqual(panel.page.total, 1)
            selected = panel._selected_asset()
            self.assertEqual(selected.kind, "WBNK")
            self.assertEqual(selected.outer_index, 3118)
            self.assertIn(selected.asset_id, panel.metadata_label.text())
            panel.status_filter.setCurrentIndex(
                panel.status_filter.findData("Editable")
            )
            application.processEvents()
            self.assertEqual(panel.page.total, 0)
            panel.status_filter.setCurrentIndex(
                panel.status_filter.findData("Export-only")
            )
            application.processEvents()
            selected = panel._selected_asset()

            def run_now(operation: object, complete: object) -> None:
                result = operation(lambda *_args: None)  # type: ignore[operator]
                complete(result)  # type: ignore[operator]

            panel._run = run_now  # type: ignore[method-assign]
            destination_without_suffix = root / "raw-wbnk"
            with patch(
                "mod_editor.gui.audio_panel_qt.QFileDialog.getSaveFileName",
                return_value=(
                    str(destination_without_suffix),
                    "Raw BANK/ABNK/WBNK resource (*.bin)",
                ),
            ):
                panel._export_selected()
            destination = destination_without_suffix.with_suffix(".bin")
            self.assertTrue(destination.is_file())
            self.assertTrue(destination.read_bytes().startswith(b"WBNK"))
            self.assertEqual(index.exports, [selected.asset_id])
            self.assertEqual(host.modified_audio_asset_ids, ())
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertEqual(project_mutations, [])
            before = destination.read_bytes()
            with self.assertRaisesRegex(ValidationError, "already exists"):
                host.export_resource(selected, destination, lambda *_args: None)
            self.assertEqual(destination.read_bytes(), before)

            panel.reset_for_source()
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertEqual(host.modified_audio_asset_ids, ())
            panel.deleteLater()
            application.processEvents()

    def test_raw_bank_container_scope_refuses_an_incomplete_universal_index(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(
                catalog,
                service,
                root / "replacements",
                universal_index=_RawResourceIndex(omit_last=True),  # type: ignore[arg-type]
            )
            panel = AudioPanel(host)
            try:
                with self.assertRaisesRegex(
                    ValidationError, "exactly three indexed WBNK"
                ):
                    panel._load_raw_audio_containers()
                with patch(
                    "mod_editor.gui.audio_panel_qt.QMessageBox.warning"
                ) as warning:
                    panel.scope_filter.setCurrentIndex(
                        panel.scope_filter.findData("raw_containers")
                    )
                    application.processEvents()
                self.assertEqual(panel.table.rowCount(), 0)
                self.assertEqual(
                    panel.count_label.text(), "Raw bank inventory unavailable"
                )
                self.assertEqual(
                    panel.range_label.text(), "No raw containers were assumed"
                )
                self.assertIn(
                    "exactly three indexed WBNK", warning.call_args.args[2]
                )
            finally:
                panel.deleteLater()
                application.processEvents()

    def test_soundtrack_quick_view_and_transactional_matching_export(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            self.assertEqual(
                panel.soundtrack_button.text(),
                "Soundtrack && music (136)",
            )
            panel._show_soundtrack()
            application.processEvents()

            self.assertEqual(panel.scope_filter.currentData(), "streaming_ranges")
            self.assertEqual(panel.family_filter.currentData(), "music")
            self.assertEqual(panel.status_filter.currentData(), None)
            self.assertEqual(panel.search.text(), "")
            self.assertEqual(panel.page.total, 2)
            self.assertTrue(panel.export_matching_button.isEnabled())
            self.assertEqual(
                panel.export_matching_button.text(),
                "Export soundtrack && music (2)…",
            )
            destination = root / "soundtrack.zip"
            operations: list[object] = []

            def run_now(operation: object, complete: object) -> None:
                operations.append(operation)
                result = operation(lambda *_args: None)  # type: ignore[operator]
                complete(result)  # type: ignore[operator]

            panel._run = run_now  # type: ignore[method-assign]
            with patch(
                "mod_editor.gui.audio_panel_qt.QFileDialog.getSaveFileName",
                return_value=(
                    str(destination),
                    "Decoded WAV audio ZIP (*.zip)",
                ),
            ) as dialog, patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.information"
            ) as information:
                panel._export_matching_audio()
            self.assertEqual(len(operations), 1)
            self.assertTrue(destination.is_file())
            self.assertTrue(dialog.call_args.args[2].endswith(
                "nfl2k5-soundtrack-music-wav.zip"
            ))
            self.assertTrue(dialog.call_args.args[3].startswith("Decoded WAV"))
            self.assertIn("not a shareable", information.call_args.args[2])

            panel.page = AudioPage((), 257, 0, 1)
            panel._update_collection_actions()
            self.assertFalse(panel.export_matching_button.isEnabled())
            self.assertIn("256 or fewer", panel.export_matching_button.toolTip())
            panel.deleteLater()
            application.processEvents()

    def test_pending_debounced_search_disables_page_bound_actions_until_refresh(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            old_selected = panel._selected_asset().asset_id

            self.assertTrue(panel.next_button.isEnabled())
            self.assertTrue(panel.export_matching_button.isEnabled())
            self.assertTrue(panel.shortlist_page_button.isEnabled())
            self.assertTrue(panel.shortlist_matching_button.isEnabled())
            panel.search.setText("c0101")

            self.assertTrue(panel._search_timer.isActive())
            self.assertEqual(panel._selected_asset().asset_id, old_selected)
            self.assertEqual(panel.count_label.text(), "Updating audio results…")
            self.assertFalse(panel.previous_button.isEnabled())
            self.assertFalse(panel.next_button.isEnabled())
            self.assertFalse(panel.export_matching_button.isEnabled())
            self.assertFalse(panel.shortlist_page_button.isEnabled())
            self.assertFalse(panel.shortlist_matching_button.isEnabled())
            self.assertTrue(panel.play_button.isEnabled())
            self.assertTrue(panel.export_button.isEnabled())
            self.assertTrue(panel.replace_button.isEnabled())
            self.assertTrue(panel.shortlist_toggle_button.isEnabled())

            panel._filters_changed()
            self.assertFalse(panel._search_timer.isActive())
            self.assertEqual(panel.page.total, 1)
            self.assertTrue(panel._catalog_query_is_current())
            self.assertTrue(panel.export_matching_button.isEnabled())
            self.assertTrue(panel.shortlist_page_button.isEnabled())
            self.assertTrue(panel.shortlist_matching_button.isEnabled())
            panel.deleteLater()
            application.processEvents()

    def test_add_this_page_refuses_stale_query_atomically_then_adds_new_page_after_refresh(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            expected = catalog.assets[1].asset_id

            panel.search.setText("c0101")
            panel._add_visible_audio_to_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), ())

            panel._filters_changed()
            self.assertEqual(
                tuple(asset.asset_id for asset in panel.page.assets), (expected,)
            )
            panel._add_visible_audio_to_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), (expected,))
            panel.deleteLater()
            application.processEvents()

    def test_search_round_trip_to_applied_query_restores_actions_immediately(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            original_count = panel.count_label.text()
            original_range = panel.range_label.text()

            panel.search.setText("c0101")
            self.assertTrue(panel._search_timer.isActive())
            self.assertFalse(panel.next_button.isEnabled())
            panel.search.clear()

            self.assertFalse(panel._search_timer.isActive())
            self.assertTrue(panel._catalog_query_is_current())
            self.assertEqual(panel.count_label.text(), original_count)
            self.assertEqual(panel.range_label.text(), original_range)
            self.assertTrue(panel.next_button.isEnabled())
            self.assertTrue(panel.export_matching_button.isEnabled())
            self.assertTrue(panel.shortlist_page_button.isEnabled())
            self.assertTrue(panel.shortlist_matching_button.isEnabled())
            panel.deleteLater()
            application.processEvents()

    def test_failed_source_change_restores_current_or_pending_old_catalog(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            panel._add_visible_audio_to_shortlist()
            shortlist = panel._shortlisted_audio_ids()
            selection = panel.selected_asset_id
            original_epoch = panel._catalog_source_epoch

            panel.invalidate_preview_for_source_change()
            self.assertTrue(panel._catalog_query_is_current())
            panel.recover_after_source_change_failure()
            self.assertEqual(panel._catalog_source_epoch, original_epoch)
            self.assertTrue(panel._catalog_query_is_current())
            self.assertEqual(panel.selected_asset_id, selection)
            self.assertEqual(panel._shortlisted_audio_ids(), shortlist)
            self.assertTrue(panel.export_matching_button.isEnabled())

            panel.search.setText("c0101")
            self.assertTrue(panel._search_timer.isActive())
            panel.invalidate_preview_for_source_change()
            self.assertFalse(panel._search_timer.isActive())
            self.assertFalse(panel._catalog_query_is_current())
            panel.recover_after_source_change_failure()
            self.assertEqual(panel.page.total, 1)
            self.assertEqual(panel.page.offset, 0)
            self.assertEqual(panel.selected_asset_id, catalog.assets[1].asset_id)
            self.assertEqual(panel._shortlisted_audio_ids(), shortlist)
            self.assertTrue(panel._catalog_query_is_current())
            self.assertTrue(panel.export_matching_button.isEnabled())
            panel.deleteLater()
            application.processEvents()

    def test_export_matching_refuses_stale_query_before_dialog_then_uses_refreshed_count_and_query(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            destination = root / "one-match.zip"
            captured: dict[str, object] = {}

            def export_bundle(**kwargs: object) -> Path:
                captured.update(kwargs)
                return Path(kwargs["destination"])

            def run_now(operation: object, complete: object) -> None:
                result = operation(lambda *_args: None)  # type: ignore[operator]
                complete(result)  # type: ignore[operator]

            host.export_audio_bundle = export_bundle  # type: ignore[method-assign]
            panel._run = run_now  # type: ignore[method-assign]
            panel.search.setText("c0101")
            with patch(
                "mod_editor.gui.audio_panel_qt.QFileDialog.getSaveFileName"
            ) as stale_dialog:
                panel._export_matching_audio()
            stale_dialog.assert_not_called()
            self.assertEqual(captured, {})

            panel._filters_changed()
            with patch(
                "mod_editor.gui.audio_panel_qt.QFileDialog.getSaveFileName",
                return_value=(str(destination), "Current WAV audio ZIP (*.zip)"),
            ) as fresh_dialog, patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.information"
            ) as information:
                panel._export_matching_audio()
            fresh_dialog.assert_called_once()
            self.assertEqual(captured["search"], "c0101")
            self.assertEqual(captured["scope"], PLAYABLE_AUDIO_SCOPE_ID)
            self.assertEqual(captured["output_format"], "wav")
            self.assertIsNone(captured["meaning_status"])
            self.assertEqual(host._replacements, {})
            self.assertIn("Saved 1 audio rows", information.call_args.args[2])
            panel.deleteLater()
            application.processEvents()

    def test_add_all_matching_does_not_requery_or_warn_while_page_token_is_stale(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            errors: list[str] = []
            panel.error_raised.connect(errors.append)

            with patch.object(
                host, "browse_audio", wraps=host.browse_audio
            ) as browse, patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.information"
            ) as information:
                panel.search.setText("c0101")
                panel._add_all_matching_audio_to_shortlist()
            browse.assert_not_called()
            information.assert_not_called()
            self.assertEqual(errors, [])
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            panel.deleteLater()
            application.processEvents()

    def test_pending_search_blocks_pagination_without_offset_or_selection_change_then_timer_applies_page_zero(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            original_offset = panel.offset
            original_selection = panel.selected_asset_id

            panel.search.setText("c0101")
            panel._next_page()
            panel._previous_page()
            self.assertEqual(panel.offset, original_offset)
            self.assertEqual(panel.selected_asset_id, original_selection)

            QTest.qWait(300)
            application.processEvents()
            self.assertFalse(panel._search_timer.isActive())
            self.assertEqual(panel.offset, 0)
            self.assertEqual(panel.page.offset, 0)
            self.assertEqual(panel.page.total, 1)
            self.assertEqual(panel.selected_asset_id, catalog.assets[1].asset_id)
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_crosses_filters_pages_families_and_scopes(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            project_mutations: list[tuple[str, str]] = []
            panel.audio_modified.connect(
                lambda asset_id: project_mutations.append(("modified", asset_id))
            )
            panel.audio_reverted.connect(
                lambda asset_id: project_mutations.append(("reverted", asset_id))
            )

            first_id = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), (first_id,))
            self.assertIn("★ Selected", panel.table.item(0, 5).text())
            panel._next_page()
            second_id = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            self.assertEqual(
                panel._shortlisted_audio_ids(), (first_id, second_id)
            )

            panel.search.setText("menu-back")
            panel._filters_changed()
            panel.family_filter.setCurrentIndex(
                panel.family_filter.findData("frontend_ui")
            )
            application.processEvents()
            self.assertEqual(
                panel._shortlisted_audio_ids(), (first_id, second_id)
            )

            panel.search.clear()
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming")
            )
            application.processEvents()
            self.assertFalse(panel.shortlist_toggle_button.isEnabled())
            self.assertFalse(panel.shortlist_page_button.isEnabled())
            self.assertIn("Complete banks", panel.shortlist_page_button.toolTip())
            panel._toggle_audio_shortlist()
            self.assertEqual(
                panel._shortlisted_audio_ids(), (first_id, second_id)
            )

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            panel.family_filter.setCurrentIndex(
                panel.family_filter.findData("music")
            )
            application.processEvents()
            range_id = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            self.assertEqual(
                panel._shortlisted_audio_ids(), (first_id, second_id, range_id)
            )
            panel.refresh(keep_selection=False)
            self.assertEqual(
                panel._shortlisted_audio_ids(), (first_id, second_id, range_id)
            )
            self.assertEqual(panel.shortlist_count_label.text(), "Selected 3 / 256")

            panel.reset_for_source()
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertEqual(panel.shortlist_count_label.text(), "Selected 0 / 256")
            self.assertFalse(panel.export_shortlist_button.isEnabled())
            self.assertEqual(project_mutations, [])
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_add_page_is_atomic_at_256_and_excludes_banks(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)

            panel._add_visible_audio_to_shortlist()
            self.assertEqual(
                panel._shortlisted_audio_ids(),
                tuple(asset.asset_id for asset in catalog.assets),
            )
            panel._clear_audio_shortlist()
            panel._audio_shortlist.update(
                (f"synthetic-{index}", catalog.assets[0])
                for index in range(255)
            )
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            application.processEvents()
            self.assertTrue(panel.shortlist_page_button.isEnabled())
            self.assertIn("1 spaces remain", panel.shortlist_page_button.toolTip())
            before = panel._shortlisted_audio_ids()
            with patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.information"
            ) as information:
                panel._add_visible_audio_to_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), before)
            self.assertIn("No sounds were added", information.call_args.args[2])

            panel._clear_audio_shortlist()
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming")
            )
            application.processEvents()
            panel._add_visible_audio_to_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertFalse(panel.shortlist_page_button.isEnabled())
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_clear_has_one_level_exact_ordered_undo(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            expected = tuple(asset.asset_id for asset in catalog.assets)

            panel._add_visible_audio_to_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), expected)
            panel._clear_audio_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertEqual(
                tuple(asset_id for asset_id, _asset in panel._cleared_audio_shortlist),
                expected,
            )
            self.assertEqual(panel.shortlist_clear_button.text(), "Undo")
            self.assertTrue(panel.shortlist_clear_button.isEnabled())
            self.assertIn("Undo is available", panel.progress_label.text())

            panel._clear_audio_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), expected)
            self.assertEqual(panel._cleared_audio_shortlist, ())
            self.assertEqual(panel.shortlist_clear_button.text(), "Clear")
            self.assertIn("Restored 2 cleared sounds", panel.progress_label.text())
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_clear_from_review_returns_to_browser_and_undoes(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            expected = tuple(asset.asset_id for asset in catalog.assets)

            panel._add_visible_audio_to_shortlist()
            panel._toggle_audio_shortlist_review()
            self.assertTrue(panel._shortlist_reviewing)
            panel._clear_audio_shortlist()
            self.assertFalse(panel._shortlist_reviewing)
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertEqual(panel.shortlist_clear_button.text(), "Undo")

            panel._clear_audio_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), expected)
            self.assertFalse(panel._shortlist_reviewing)
            self.assertTrue(panel.shortlist_review_button.isEnabled())
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_clear_undo_restores_mixed_256_without_project_mutation(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)
            assets = (
                *_reviewed_standalone_assets(
                    catalog.assets[0], 254, start_chunk=2_000
                ),
                *catalog.streaming_ranges[:2],
            )
            expected = tuple(asset.asset_id for asset in assets)
            self.assertEqual(len(expected), 256)
            self.assertEqual(len(set(expected)), 256)
            project_events: list[tuple[str, object]] = []
            panel.audio_modified.connect(
                lambda asset_id: project_events.append(("modified", asset_id))
            )
            panel.audio_reverted.connect(
                lambda asset_id: project_events.append(("reverted", asset_id))
            )
            panel.audio_batch_imported.connect(
                lambda count: project_events.append(("batch", count))
            )
            modified_before = host.modified_audio_asset_ids
            panel._audio_shortlist = {
                asset.asset_id: asset for asset in assets
            }
            panel._update_audio_shortlist_actions()

            panel._clear_audio_shortlist()
            self.assertEqual(panel.shortlist_clear_button.text(), "Undo")
            self.assertIn("256", panel.shortlist_clear_button.accessibleName())
            panel._clear_audio_shortlist()

            self.assertEqual(panel._shortlisted_audio_ids(), expected)
            self.assertEqual(project_events, [])
            self.assertEqual(host.modified_audio_asset_ids, modified_before)
            self.assertEqual(panel._tasks, set())
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_clear_undo_expires_on_mutation_and_source_reset(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=2)

            panel._add_visible_audio_to_shortlist()
            panel._clear_audio_shortlist()
            self.assertTrue(panel._cleared_audio_shortlist)
            panel._toggle_audio_shortlist()
            self.assertEqual(panel._cleared_audio_shortlist, ())
            panel._toggle_audio_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertFalse(panel.shortlist_clear_button.isEnabled())
            panel._clear_audio_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), ())

            panel._add_visible_audio_to_shortlist()
            panel._clear_audio_shortlist()
            self.assertTrue(panel._cleared_audio_shortlist)
            panel.reset_for_source()
            self.assertEqual(panel._cleared_audio_shortlist, ())
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertFalse(panel.shortlist_clear_button.isEnabled())
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_review_reorders_removes_and_restores_browser_state(
        self,
    ) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            panel = AudioPanel(host, page_size=1)
            project_mutations: list[tuple[str, str]] = []
            panel.audio_modified.connect(
                lambda asset_id: project_mutations.append(("modified", asset_id))
            )
            panel.audio_reverted.connect(
                lambda asset_id: project_mutations.append(("reverted", asset_id))
            )

            first_standalone = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            panel._next_page()
            second_standalone = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()

            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            panel.family_filter.setCurrentIndex(
                panel.family_filter.findData("music")
            )
            panel.status_filter.setCurrentIndex(
                panel.status_filter.findData("Editable")
            )
            panel.search.setText("soundtrack")
            panel._filters_changed()
            application.processEvents()
            first_range = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            panel._next_page()
            second_range = panel._selected_asset().asset_id
            panel._toggle_audio_shortlist()
            original_order = (
                first_standalone,
                second_standalone,
                first_range,
                second_range,
            )
            self.assertEqual(panel._shortlisted_audio_ids(), original_order)
            browser_state = (
                panel.search.text(),
                panel.scope_filter.currentData(),
                panel.family_filter.currentData(),
                panel.status_filter.currentData(),
                panel.offset,
                panel.selected_asset_id,
            )

            panel._toggle_audio_shortlist_review()
            self.assertTrue(panel._shortlist_reviewing)
            self.assertFalse(panel.search.isEnabled())
            self.assertFalse(panel.scope_filter.isEnabled())
            self.assertEqual(panel.table.rowCount(), 1)
            self.assertEqual(panel._selected_asset().asset_id, first_standalone)
            self.assertEqual(panel.count_label.text(), "Reviewing 4 selected sounds")
            self.assertEqual(panel.shortlist_review_button.text(), "Back to browser")
            self.assertTrue(panel.shortlist_move_down_button.isEnabled())
            self.assertFalse(panel.shortlist_move_up_button.isEnabled())

            panel._move_shortlisted_audio(1)
            reordered = (
                second_standalone,
                first_standalone,
                first_range,
                second_range,
            )
            self.assertEqual(panel._shortlisted_audio_ids(), reordered)
            self.assertEqual(panel._selected_asset().asset_id, first_standalone)
            self.assertEqual(panel.offset, 1)
            self.assertTrue(panel.shortlist_move_up_button.isEnabled())

            panel._next_page()
            self.assertEqual(panel._selected_asset().asset_id, first_range)
            panel._toggle_audio_shortlist()
            self.assertEqual(
                panel._shortlisted_audio_ids(),
                (second_standalone, first_standalone, second_range),
            )
            self.assertTrue(panel._shortlist_reviewing)
            self.assertEqual(panel._selected_asset().asset_id, second_range)

            panel._toggle_audio_shortlist_review()
            self.assertFalse(panel._shortlist_reviewing)
            self.assertTrue(panel.search.isEnabled())
            self.assertEqual(
                (
                    panel.search.text(),
                    panel.scope_filter.currentData(),
                    panel.family_filter.currentData(),
                    panel.status_filter.currentData(),
                    panel.offset,
                    panel.selected_asset_id,
                ),
                browser_state,
            )

            panel._toggle_audio_shortlist_review()
            panel._clear_audio_shortlist()
            self.assertFalse(panel._shortlist_reviewing)
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertFalse(panel.shortlist_review_button.isEnabled())

            panel._toggle_audio_shortlist()
            self.assertEqual(panel._shortlisted_audio_ids(), (second_range,))
            panel._toggle_audio_shortlist_review()
            panel._toggle_audio_shortlist()
            self.assertFalse(panel._shortlist_reviewing)
            self.assertEqual(panel._shortlisted_audio_ids(), ())

            panel._toggle_audio_shortlist()
            panel._toggle_audio_shortlist_review()
            panel.reset_for_source()
            self.assertFalse(panel._shortlist_reviewing)
            self.assertEqual(panel._shortlisted_audio_ids(), ())
            self.assertEqual(panel.offset, 0)
            self.assertTrue(panel.search.isEnabled())
            self.assertEqual(project_mutations, [])
            panel.deleteLater()
            application.processEvents()

    def test_audio_shortlist_export_uses_exact_ids_not_current_bank_filter(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = Nfl2k5AudioService(fixture.cache, catalog)
            _authorize_synthetic_fixture_audio(service)
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            supplied = _valid_menu_wav(root / "shortlisted-current.wav")
            host.replace_audio(catalog.assets[1].asset_id, supplied, lambda *_args: None)
            panel = AudioPanel(host, page_size=2)

            panel.table.selectRow(1)
            panel._toggle_audio_shortlist()
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            application.processEvents()
            panel._toggle_audio_shortlist()
            selected_ids = panel._shortlisted_audio_ids()
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming")
            )
            application.processEvents()
            self.assertNotIn(panel._selected_asset().asset_id, selected_ids)
            self.assertEqual(panel.shortlist_count_label.text(), "Selected 2 / 256")
            self.assertEqual(
                panel.export_shortlist_button.text(), "Export selected WAVs (2)…"
            )

            panel._toggle_audio_shortlist_review()
            self.assertEqual(panel._selected_asset().asset_id, selected_ids[0])
            panel._move_shortlisted_audio(1)
            selected_ids = panel._shortlisted_audio_ids()

            destination = root / "selected.zip"

            def run_now(operation: object, complete: object) -> None:
                result = operation(lambda *_args: None)  # type: ignore[operator]
                complete(result)  # type: ignore[operator]

            panel._run = run_now  # type: ignore[method-assign]
            with patch(
                "mod_editor.gui.audio_panel_qt.QFileDialog.getSaveFileName",
                return_value=(str(destination), "Decoded WAV audio ZIP (*.zip)"),
            ) as dialog, patch(
                "mod_editor.gui.audio_panel_qt.QMessageBox.information"
            ) as information:
                panel._export_shortlisted_audio()
            self.assertTrue(dialog.call_args.args[2].endswith(
                "nfl2k5-selected-sounds-wav.zip"
            ))
            self.assertIn("not a shareable", information.call_args.args[2])
            with zipfile.ZipFile(destination) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                records = manifest["records"]
                self.assertEqual(
                    tuple(record["stable_id"] for record in records), selected_ids
                )
                self.assertEqual(
                    tuple(record["content_origin"] for record in records),
                    ("retail_derived", "user_replacement"),
                )
                self.assertEqual(archive.read(records[0]["path"])[:4], b"RIFF")
                self.assertEqual(archive.read(records[1]["path"]), supplied.read_bytes())
            panel.deleteLater()
            application.processEvents()


if __name__ == "__main__":
    unittest.main()
