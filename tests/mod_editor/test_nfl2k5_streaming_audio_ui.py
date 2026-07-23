"""Focused headless product tests for editable NFL 2K5 streaming audio."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_audio_catalog import (
    EXPECTED_PLAYABLE_AUDIO_COUNT,
    PLAYABLE_AUDIO_FAMILIES,
    PLAYABLE_AUDIO_SCOPE_ID,
)
from mod_editor.gui.audio_panel_qt import AudioPanel, CatalogAudioPanelHost
from mod_editor.studio import facade as facade_module
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.project_archive import ProjectTargetIdentity
from mod_editor.studio.session import AudioProjectPreparationRequired
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture


class _Preparation:
    def __init__(self, *, blocking: bool = False) -> None:
        self.blocking = blocking
        self.entered = threading.Event()
        self.release = threading.Event()
        self.prepare_calls = 0

    def is_ready(self, _cache: object) -> bool:
        return False

    def prepare(
        self,
        _cache: object,
        progress: object,
        _cancelled: object = None,
    ) -> object:
        self.prepare_calls += 1
        progress("Synthetic private audio scan", 0, 1)  # type: ignore[operator]
        self.entered.set()
        if self.blocking and not self.release.wait(3):
            raise AssertionError("test did not release audio preparation")
        progress("Synthetic private audio scan", 1, 1)  # type: ignore[operator]
        return SimpleNamespace(prepared=True)


class _PreparationService:
    def __init__(self) -> None:
        self.audio_origin_ready = False
        self.preflight_ids: list[str] = []
        self.load_calls = 0

    def read_replacement_snapshot(self, asset_id: str, _wav: Path) -> object:
        self.preflight_ids.append(asset_id)
        return SimpleNamespace()

    def load_private_origin_inventories(self) -> tuple[object, object]:
        self.load_calls += 1
        self.audio_origin_ready = True
        return object(), object()


class _ReplaceSession:
    modified_audio_asset_ids: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.replace_calls: list[str] = []

    def replace_audio(self, asset_id: str, _wav: Path) -> object:
        self.replace_calls.append(asset_id)
        return SimpleNamespace(modified=True)


class _ProjectCandidate:
    modified_count = 0
    can_undo = False

    def __init__(self, *, needs_audio: bool) -> None:
        self.needs_audio = needs_audio
        self.load_calls = 0
        self.audio_service: object | None = None

    def attach_audio_service(self, service: object) -> None:
        self.audio_service = service

    def load_shareable_project(self, _source: Path) -> int:
        self.load_calls += 1
        if self.needs_audio and self.load_calls == 1:
            raise AudioProjectPreparationRequired("prepare fixture audio")
        return 2


class StreamingAudioFacadeTests(unittest.TestCase):
    def _facade(self, preparation: _Preparation) -> Nfl2k5StudioFacade:
        return Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
            audio_origin_preparation=preparation,  # type: ignore[arg-type]
        )

    def test_playable_scope_is_domain_prefixed_search_reusing_and_global(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary) / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            standalone = catalog.assets
            ranges = catalog.streaming_ranges

            self.assertEqual(EXPECTED_PLAYABLE_AUDIO_COUNT, 54_421)
            self.assertEqual(PLAYABLE_AUDIO_SCOPE_ID, "playable")
            self.assertEqual(catalog.playable_count, 4)
            self.assertEqual(catalog.playable_assets, standalone + ranges)
            self.assertFalse(any(
                item in catalog.playable_assets for item in catalog.streaming_banks
            ))
            self.assertEqual(
                tuple(value for value, _label in PLAYABLE_AUDIO_FAMILIES),
                (
                    "frontend_ui", "field_crowd_player", "team_crowd",
                    "crib_minigames", "music", "commentary", "stadium",
                    "presentation", "ambient", "unknown",
                ),
            )

            with patch.object(
                facade_module,
                "_audio_search_haystack",
                wraps=facade_module._audio_search_haystack,
            ) as haystack:
                index = facade_module._build_audio_search_index(catalog)
            self.assertEqual(
                haystack.call_count,
                len(standalone) + len(catalog.streaming_banks) + len(ranges),
            )
            self.assertIs(index["playable"][0], index["standalone"][0])
            self.assertIs(
                index["playable"][len(standalone)],
                index["streaming_ranges"][0],
            )

            modified_ids = (standalone[1].asset_id, ranges[1].asset_id)
            facade = self._facade(_Preparation())
            facade._audio_catalog = catalog
            facade._session = SimpleNamespace(modified_audio_asset_ids=modified_ids)
            page = facade.browse_audio(
                search="", status=None, offset=0, limit=3, scope="playable"
            )
            self.assertEqual(page.total, 4)
            self.assertEqual(page.assets, (*standalone, ranges[0]))
            second = facade.browse_audio(
                search="", status=None, offset=3, limit=3, scope="playable"
            )
            self.assertEqual(second.assets, (ranges[1],))
            modified = facade.browse_audio(
                search="", status="Modified", offset=0, limit=50,
                scope="playable",
            )
            self.assertEqual(
                tuple(item.asset_id for item in modified.assets), modified_ids
            )
            self.assertEqual(
                facade.browse_audio(
                    search="menu-back", status=None, offset=0, limit=50,
                    scope="playable", family="frontend_ui",
                ).assets,
                standalone,
            )
            self.assertEqual(
                facade.browse_audio(
                    search="soundtrack playable", status=None, offset=0, limit=50,
                    scope="playable", family="music",
                ).assets,
                ranges,
            )
            with self.assertRaisesRegex(ValidationError, "only to standalone"):
                facade.browse_audio(
                    search="", status=None, offset=0, limit=50,
                    scope="playable",
                    meaning_status="reviewed_label_runtime_meaning_unproved",
                )

    def test_playable_matching_bundle_is_wav_only_and_retail_labeled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = facade_module.Nfl2k5AudioService(fixture.cache, catalog)

            class CurrentSession:
                modified_audio_asset_ids: tuple[str, ...] = ()

                @staticmethod
                def audio_content_origin(_asset: object) -> str:
                    return "retail_derived"

                @staticmethod
                def export_audio(asset: object, destination: Path) -> Path:
                    if getattr(asset, "scope_id") == "standalone":
                        return service.export_wav(asset, destination)
                    return service.export_streaming_range_wav(asset, destination)

            facade = self._facade(_Preparation())
            facade._audio_catalog = catalog
            facade._audio_service = service
            facade._session = CurrentSession()  # type: ignore[assignment]
            destination = root / "all-playable.zip"
            self.assertEqual(
                facade.export_audio_bundle(
                    search="", status=None, scope="playable", family=None,
                    destination=destination, output_format="wav",
                    bundle_name="All playable fixture audio",
                    progress=lambda *_args: None,
                ),
                destination.resolve(),
            )
            with zipfile.ZipFile(destination) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["record_count"], 4)
                self.assertFalse(manifest["shareable_project"])
                self.assertTrue(manifest["contains_retail_derived"])
                self.assertFalse(manifest["contains_user_replacements"])
                self.assertEqual(manifest["playlist_record_count"], 4)
                records = manifest["records"]
                self.assertEqual(
                    tuple(record["stable_id"] for record in records),
                    tuple(item.asset_id for item in catalog.playable_assets),
                )
                self.assertEqual(
                    tuple(record["metadata"]["scope_id"] for record in records),
                    ("standalone", "standalone", "streaming_ranges", "streaming_ranges"),
                )
                self.assertEqual({record["format"] for record in records}, {"wav"})
                for record in records:
                    self.assertEqual(archive.read(record["path"])[:4], b"RIFF")

            refused = root / "all-playable-raw.zip"
            with self.assertRaisesRegex(ValidationError, "All Playable Audio"):
                facade.export_audio_bundle(
                    search="", status=None, scope="playable", family=None,
                    destination=refused, output_format="bin",
                    bundle_name="Refused raw mixed bundle",
                    progress=lambda *_args: None,
                )
            self.assertFalse(refused.exists())

    def test_modified_range_play_and_wav_export_use_session_current_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = facade_module.Nfl2k5AudioService(fixture.cache, catalog)
            selected = catalog.streaming_ranges[0]
            authored = root / "authored-current.wav"
            authored.write_bytes(b"RIFF-user-authored-current")

            class CurrentSession:
                modified_audio_asset_ids = (selected.asset_id,)

                @staticmethod
                def current_audio_path(_asset: object) -> Path:
                    return authored

                @staticmethod
                def export_audio(_asset: object, destination: Path) -> Path:
                    destination.write_bytes(authored.read_bytes())
                    return destination.resolve()

            facade = self._facade(_Preparation())
            facade._audio_catalog = catalog
            facade._audio_service = service
            facade._session = CurrentSession()  # type: ignore[assignment]

            page = facade.browse_audio(
                search="",
                status="Modified",
                offset=0,
                limit=50,
                scope="streaming_ranges",
            )
            self.assertEqual(tuple(row.asset_id for row in page.assets), (
                selected.asset_id,
            ))
            self.assertEqual(
                facade.prepare_audio(selected.asset_id, lambda *_args: None),
                authored,
            )
            destination = root / "current-export.wav"
            self.assertEqual(
                facade.export_audio_range_wav(
                    selected.asset_id, destination, lambda *_args: None
                ),
                destination.resolve(),
            )
            self.assertEqual(destination.read_bytes(), authored.read_bytes())

    def test_modified_range_raw_export_stays_labeled_retail_derived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = facade_module.Nfl2k5AudioService(fixture.cache, catalog)
            selected = catalog.streaming_ranges[0]
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            host._replacement_owners = {"physical": (selected.asset_id,)}
            destination = root / "modified-raw-range.zip"
            host.export_audio_bundle(
                search=f"r{selected.range_index:05d}",
                status="Modified",
                scope="streaming_ranges",
                family=None,
                destination=destination,
                output_format="bin",
                bundle_name="Raw range safety label",
                progress=lambda *_args: None,
            )
            with zipfile.ZipFile(destination) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertTrue(manifest["contains_retail_derived"])
                self.assertFalse(manifest["contains_user_replacements"])
                self.assertEqual(
                    manifest["records"][0]["content_origin"], "retail_derived"
                )

    def test_replace_releases_facade_lock_and_rejects_project_switch(self) -> None:
        preparation = _Preparation(blocking=True)
        service = _PreparationService()
        original_session = _ReplaceSession()
        replacement_session = _ReplaceSession()
        facade = self._facade(preparation)
        facade._cache = object()  # type: ignore[assignment]
        facade._audio_service = service  # type: ignore[assignment]
        facade._session = original_session  # type: ignore[assignment]
        failures: list[BaseException] = []

        def replace() -> None:
            try:
                facade.replace_audio(
                    "nfl2k5.audio.ausb.o0001.c0000.r00000",
                    Path("authored.wav"),
                    lambda *_args: None,
                )
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=replace, daemon=True)
        worker.start()
        self.assertTrue(preparation.entered.wait(1))
        switched = threading.Event()

        def switch_project() -> None:
            with facade._lock:
                facade._session = replacement_session  # type: ignore[assignment]
            switched.set()

        switcher = threading.Thread(target=switch_project, daemon=True)
        switcher.start()
        try:
            self.assertTrue(
                switched.wait(1),
                "the long audio scan held the general facade/UI lock",
            )
        finally:
            preparation.release.set()
        worker.join(3)
        switcher.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(service.preflight_ids, [
            "nfl2k5.audio.ausb.o0001.c0000.r00000"
        ])
        self.assertEqual(service.load_calls, 1)
        self.assertEqual(original_session.replace_calls, [])
        self.assertEqual(replacement_session.replace_calls, [])
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ValidationError)
        self.assertIn("working project changed", str(failures[0]))

    def test_first_pack_import_prepares_then_binds_original_session(self) -> None:
        preparation = _Preparation()
        service = _PreparationService()
        session = _ReplaceSession()
        imported: list[tuple[Path, object]] = []

        class Pack:
            @staticmethod
            def import_edited(source: Path, *, progress: object) -> object:
                imported.append((source, progress))
                return SimpleNamespace(changed_count=1)

        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
            audio_origin_preparation=preparation,  # type: ignore[arg-type]
            audio_replacement_pack_factory=lambda _catalog, owner: (
                Pack() if owner is session else (_ for _ in ()).throw(
                    AssertionError("pack rebound to another session")
                )
            ),
        )
        facade._cache = object()  # type: ignore[assignment]
        facade._session = session  # type: ignore[assignment]
        facade._audio_catalog = object()  # type: ignore[assignment]
        facade._audio_service = service  # type: ignore[assignment]
        progress: list[str] = []
        source = Path("authored-pack.zip")
        result = facade.import_audio_replacement_pack(
            source, lambda stage, _done, _total: progress.append(stage)
        )
        self.assertEqual(result.changed_count, 1)
        self.assertEqual(preparation.prepare_calls, 1)
        self.assertEqual(service.load_calls, 1)
        self.assertEqual(imported[0][0], source)
        self.assertIn("Audio editing ready", progress)

    def test_audio_project_prepares_once_but_visual_project_does_not(self) -> None:
        for needs_audio in (True, False):
            with self.subTest(needs_audio=needs_audio):
                preparation = _Preparation()
                service = _PreparationService()
                candidate = _ProjectCandidate(needs_audio=needs_audio)
                facade = Nfl2k5StudioFacade(
                    uniform_catalog=object(),  # type: ignore[arg-type]
                    visual_catalog=object(),  # type: ignore[arg-type]
                    session_factory=lambda _cache, _catalog: candidate,
                    audio_origin_preparation=preparation,  # type: ignore[arg-type]
                )
                cache = object()
                active = _ReplaceSession()
                facade._cache = cache  # type: ignore[assignment]
                facade._session = active  # type: ignore[assignment]
                facade._audio_service = service  # type: ignore[assignment]
                identity = ProjectTargetIdentity(
                    Path("/tmp/project.2k5mod"), 1, 2, 3, 4, 5
                )
                with patch.object(
                    facade_module,
                    "project_target_identity",
                    return_value=identity,
                ):
                    result = facade.load_project(
                        Path("project.2k5mod"), lambda *_args: None
                    )
                self.assertEqual(result.project_identity, identity)
                self.assertIs(facade._session, candidate)
                self.assertEqual(candidate.load_calls, 2 if needs_audio else 1)
                self.assertEqual(preparation.prepare_calls, 1 if needs_audio else 0)
                self.assertEqual(service.load_calls, 1 if needs_audio else 0)


@unittest.skipUnless(os.environ.get("QT_QPA_PLATFORM") == "offscreen", "offscreen Qt")
class StreamingAudioOffscreenTests(unittest.TestCase):
    def test_unique_and_shared_modified_ranges_have_truthful_status_and_owner_list(
        self,
    ) -> None:
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            source_root.mkdir()
            fixture = AudioFixture(source_root)
            catalog = fixture.catalog()
            service = facade_module.Nfl2k5AudioService(fixture.cache, catalog)
            shared, unique = catalog.streaming_ranges
            linked_id = shared.asset_id.rsplit("r", 1)[0] + "r99999"

            def affected(asset_id: str) -> tuple[str, ...]:
                return (
                    (shared.asset_id, linked_id)
                    if asset_id == shared.asset_id else (unique.asset_id,)
                )

            service.audio_affected_asset_ids = affected  # type: ignore[method-assign]
            host = CatalogAudioPanelHost(catalog, service, root / "replacements")
            host._replacement_owners = {
                "shared": (shared.asset_id, linked_id),
                "unique": (unique.asset_id,),
            }
            panel = AudioPanel(host, page_size=2)
            panel.scope_filter.setCurrentIndex(
                panel.scope_filter.findData("streaming_ranges")
            )
            application.processEvents()

            self.assertEqual(panel.table.item(0, 5).text(), "Modified")
            self.assertIn("shared fixed streaming slot", panel.table.item(0, 5).toolTip())
            self.assertEqual(panel.table.item(1, 5).text(), "Modified")
            self.assertIn("fixed streaming slot", panel.table.item(1, 5).toolTip())
            self.assertNotIn("shared", panel.table.item(1, 5).toolTip())
            self.assertIn("all 2 logical owners", panel.ownership_label.text())
            self.assertIn(shared.asset_id, panel.ownership_label.text())
            self.assertIn(linked_id, panel.ownership_label.text())
            self.assertTrue(panel.replace_button.isEnabled())
            self.assertTrue(panel.revert_button.isEnabled())
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
