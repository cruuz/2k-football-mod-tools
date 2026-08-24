"""Backend-adapter tests without retail files or a display."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_build_service import BuildResult
from mod_editor.core.nfl2k5_stadium_studio import StadiumGltfTextureWriteBack
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.project_archive import (
    ProjectTargetIdentity,
    project_target_identity,
)
from mod_editor.studio.session import StadiumProjectPreparationRequired


class _Catalog:
    pass


class _Session:
    def __init__(self, cache: object, catalog: object) -> None:
        self.cache = cache
        self.catalog = catalog
        self.modified_asset_ids = frozenset()
        self.modified_count = 0
        self.can_undo = False
        self.discarded = False

    def current_path(self, asset: object) -> Path:
        return Path(asset.path)

    def export_asset(self, _asset: object, destination: Path) -> Path:
        destination.write_bytes(b"user export")
        return destination

    def replace(self, asset: object, _path: Path) -> object:
        self.modified_asset_ids = frozenset({asset.asset_id})
        self.modified_count = 1
        self.can_undo = True
        return SimpleNamespace(message="Replacement ready")

    def revert(self, _asset: object) -> bool:
        self.modified_asset_ids = frozenset()
        self.modified_count = 0
        return True

    def undo(self) -> str:
        return "Replace Test"

    def revert_all(self) -> int:
        count = self.modified_count
        self.modified_asset_ids = frozenset()
        self.modified_count = 0
        return count

    def save_shareable_project(self, destination: Path, *, replace: bool = False) -> Path:
        destination.write_bytes(b"user replacements only")
        return destination

    def load_shareable_project(self, source: Path) -> int:
        self.modified_asset_ids = frozenset({"asset.one"})
        self.modified_count = 1
        return 1

    def discard_private_workspace(self) -> None:
        self.discarded = True


class _SourceCache:
    def __init__(self, cache: object) -> None:
        self.cache = cache
        self.calls: list[Path] = []

    def index(self, path: Path, progress: object) -> object:
        self.calls.append(path)
        progress("Game index ready", 1, 1)
        return self.cache


class _BuildService:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.calls = 0

    def build(self, _cache: object, _session: object, destination: Path,
              progress: object) -> BuildResult:
        self.calls += 1
        destination.write_bytes(b"synthetic verified output")
        event = SimpleNamespace(message="Build complete", completed=4, total=4)
        progress(event)
        return BuildResult(destination, destination.stat().st_size, "a" * 64, 1, 9)


class _UniversalIndex:
    asset_count = 2

    def kinds(self) -> tuple[tuple[str, int], ...]:
        return (("TEST", 2),)

    def query(self, **_kwargs: object) -> tuple[object, ...]:
        return (SimpleNamespace(asset_id="resource.one", suggested_filename="one.bin"),)

    def export_raw(self, _asset: object, destination: Path) -> Path:
        destination.write_bytes(b"raw user export")
        return destination


class _TextCatalog:
    def __init__(self) -> None:
        self.text_asset = SimpleNamespace(asset_id="text.current.first")
        self.number_asset = SimpleNamespace(asset_id="number.current.jersey")

    def get_asset(self, asset_id: str) -> object:
        if asset_id != self.text_asset.asset_id:
            raise KeyError(asset_id)
        return self.text_asset

    def get_number_asset(self, asset_id: str) -> object:
        if asset_id != self.number_asset.asset_id:
            raise KeyError(asset_id)
        return self.number_asset


class _TextSession(_Session):
    def text_value(self, asset_id: str) -> str:
        if asset_id != "text.current.first":
            raise KeyError(asset_id)
        return "Staged Name"

    def number_value(self, asset_id: str) -> int:
        if asset_id != "number.current.jersey":
            raise KeyError(asset_id)
        return 88


class _PlaybookInspector:
    def __init__(self, index: _UniversalIndex) -> None:
        self.index = index
        self.load_calls: list[str] = []
        self._records = tuple(
            SimpleNamespace(asset_id=f"private.play.{number}")
            for number in range(2)
        )
        self._books = {
            "private.play.0": SimpleNamespace(
                asset_id="private.play.0",
                book_name="Synthetic Offense",
                formations=(SimpleNamespace(name="I Pro"),),
                plays=(SimpleNamespace(name="Quick Test", family_label="Offense"),),
                categories=(SimpleNamespace(name="Run"),),
            ),
            "private.play.1": SimpleNamespace(
                asset_id="private.play.1",
                book_name="Synthetic Defense",
                formations=(SimpleNamespace(name="Nickel"),),
                plays=(SimpleNamespace(name="Cover Test", family_label="Defense"),),
                categories=(SimpleNamespace(name="Zone"),),
            ),
        }

    def records(self) -> tuple[object, ...]:
        return self._records

    def load(self, asset_or_record: object) -> object:
        asset_id = (
            asset_or_record
            if isinstance(asset_or_record, str)
            else getattr(asset_or_record, "asset_id")
        )
        self.load_calls.append(str(asset_id))
        try:
            return self._books[str(asset_id)]
        except KeyError as exc:
            raise ValidationError(f"Unknown indexed playbook: {asset_id}") from exc


class _StadiumCoordinator:
    def load_existing(self, _cache: object) -> None:
        return None

    def ensure(self, _cache: object, _progress: object) -> object:
        raise AssertionError("synthetic facade tests do not prepare stadium assets")


class _PreparedStadiumCoordinator(_StadiumCoordinator):
    def __init__(self) -> None:
        self.ensure_calls = 0

    def ensure(self, _cache: object, progress: object) -> object:
        self.ensure_calls += 1
        progress("Synthetic stadium cache ready", 1, 1)
        return SimpleNamespace(scene_count=477)


class _StadiumStudio:
    def list_scenes(self, *, search: str) -> tuple[str, ...]:
        return (f"stadium:{search}",)


class _TextureWriteBackStudio(_StadiumStudio):
    """Hands back one receipt per mapped glTF image and proves the facade lock."""

    SCENE_ID = "nfl2k5.stadium.o0042.c0003.scene0077"

    def __init__(self, lock: object) -> None:
        self.lock = lock
        self.calls: list[tuple[object, Path]] = []
        self.receipts = (
            StadiumGltfTextureWriteBack(
                texture_id=f"{self.SCENE_ID}.texture0000",
                scene_id=self.SCENE_ID,
                texture_index=0,
                supplied_png_sha256="a" * 64,
                write_result=SimpleNamespace(message="Stadium texture replaced"),
            ),
            StadiumGltfTextureWriteBack(
                texture_id=f"{self.SCENE_ID}.texture0001",
                scene_id=self.SCENE_ID,
                texture_index=1,
                supplied_png_sha256="b" * 64,
                write_result=SimpleNamespace(message="Stadium texture replaced"),
            ),
        )

    def replace_textures_from_gltf(
        self, scene_or_id: object, edited_gltf: Path
    ) -> tuple[StadiumGltfTextureWriteBack, ...]:
        checker = getattr(self.lock, "_is_owned", None)
        if callable(checker) and not checker():
            raise AssertionError(
                "stadium texture write-back escaped the facade source lock"
            )
        self.calls.append((scene_or_id, edited_gltf))
        return self.receipts


class _CribCatalog:
    def __init__(self) -> None:
        self.assets = (
            SimpleNamespace(
                asset_id="nfl2k5.crib.aggregate.00_photo_00",
                label="Team Photo 00 / variant 00",
            ),
        )


class _CribIO:
    def __init__(self, cache: object, catalog: _CribCatalog) -> None:
        self.cache = cache
        self.catalog = catalog
        self.preview = Path(cache.source.selected_path).with_name("crib-preview.png")
        self.preview.write_bytes(b"synthetic crib png")


class _CribSession(_Session):
    def __init__(self, cache: object, catalog: object) -> None:
        super().__init__(cache, catalog)
        self.crib_catalog: _CribCatalog | None = None
        self.crib_io: _CribIO | None = None
        self.modified_crib_asset_ids = frozenset()

    def attach_crib(self, catalog: _CribCatalog, crib_io: _CribIO) -> None:
        self.crib_catalog = catalog
        self.crib_io = crib_io

    def current_crib_path(self, _asset_id: str) -> Path:
        assert self.crib_io is not None
        return self.crib_io.preview

    def export_crib(self, _asset_id: str, destination: Path) -> Path:
        assert self.crib_io is not None
        destination.write_bytes(self.crib_io.preview.read_bytes())
        return destination

    def replace_crib(self, asset_id: str, _supplied_png: Path) -> object:
        self.modified_crib_asset_ids = frozenset({asset_id})
        self.modified_asset_ids = frozenset({asset_id})
        self.modified_count = 1
        self.can_undo = True
        return SimpleNamespace(message="Team Photo replacement staged")

    def revert_crib(self, _asset_id: str) -> bool:
        self.modified_crib_asset_ids = frozenset()
        self.modified_asset_ids = frozenset()
        self.modified_count = 0
        return True


class _StadiumProjectSession(_Session):
    def __init__(self, cache: object, catalog: object) -> None:
        super().__init__(cache, catalog)
        self.stadium_ready = False
        self.project_load_attempts = 0

    def load_shareable_project(self, source: Path) -> int:
        self.project_load_attempts += 1
        if not self.stadium_ready:
            raise StadiumProjectPreparationRequired(
                "Synthetic project needs the private Stadium cache."
            )
        return super().load_shareable_project(source)


class StudioFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="studio-facade-test-")
        # Resolve the temp root so paths the facade canonicalises compare equal
        # to ours where the OS temp dir sits under a symlink (macOS /private/var)
        # or a short name (Windows).
        self.root = Path(self.temporary.name).resolve()
        source = SimpleNamespace(selected_path=str(self.root / "NFL2K5.iso"))
        self.cache = SimpleNamespace(source=source, resource_count=86882)
        self.catalog = _Catalog()
        self.source_cache = _SourceCache(self.cache)
        self.output = self.root / "modded.iso"
        self.build_service = _BuildService(self.output)
        self.launches: list[tuple[str, ...]] = []

        def launcher(argv: object, **_kwargs: object) -> object:
            self.launches.append(tuple(argv))
            return object()

        self.facade = Nfl2k5StudioFacade(
            uniform_catalog=self.catalog,  # type: ignore[arg-type]
            source_cache=self.source_cache,  # type: ignore[arg-type]
            build_service=self.build_service,  # type: ignore[arg-type]
            session_factory=_Session,  # type: ignore[arg-type]
            xemu_command=("/usr/bin/xemu-test",),
            process_launcher=launcher,
            universal_index_factory=lambda _cache: _UniversalIndex(),  # type: ignore[arg-type]
            stadium_cache_coordinator=_StadiumCoordinator(),  # type: ignore[arg-type]
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _make_crib_facade(
        self,
    ) -> tuple[Nfl2k5StudioFacade, _CribCatalog, list[_CribSession]]:
        crib_catalog = _CribCatalog()
        sessions: list[_CribSession] = []

        def session_factory(cache: object, catalog: object) -> _CribSession:
            session = _CribSession(cache, catalog)
            sessions.append(session)
            return session

        facade = Nfl2k5StudioFacade(
            uniform_catalog=self.catalog,  # type: ignore[arg-type]
            source_cache=self.source_cache,  # type: ignore[arg-type]
            build_service=self.build_service,  # type: ignore[arg-type]
            session_factory=session_factory,  # type: ignore[arg-type]
            xemu_command=(),
            universal_index_factory=lambda _cache: _UniversalIndex(),  # type: ignore[arg-type]
            stadium_cache_coordinator=_StadiumCoordinator(),  # type: ignore[arg-type]
            crib_catalog_factory=lambda: crib_catalog,  # type: ignore[arg-type]
            crib_io_factory=_CribIO,  # type: ignore[arg-type]
        )
        return facade, crib_catalog, sessions

    def test_full_facade_flow_and_xemu_argv(self) -> None:
        events: list[tuple[str, int, int]] = []
        progress = lambda stage, done, total: events.append((stage, done, total))
        result = self.facade.load_source(self.root / "NFL2K5.iso", progress)
        self.assertIn("86,882", result.message)
        self.assertTrue(self.facade.source_ready)
        self.assertEqual(self.facade.source_display_name, "NFL2K5.iso")

        preview = self.root / "preview.png"
        preview.write_bytes(b"preview")
        asset = SimpleNamespace(
            asset_id="asset.one", label="Test", width=2, height=2, path=preview
        )
        self.assertEqual(self.facade.preview_asset(asset, progress), preview)
        replacement = self.root / "replacement.png"
        replacement.write_bytes(b"mine")
        self.assertEqual(
            self.facade.replace_asset(asset, replacement, progress).message,
            "Replacement ready",
        )
        self.assertEqual(set(self.facade.modified_asset_ids), {"asset.one"})
        self.assertTrue(self.facade.can_undo)

        built = self.facade.build_iso(self.output, progress)
        self.assertEqual(built.output_xiso, self.output)
        self.assertTrue(self.facade.can_launch_xemu)
        launched = self.facade.launch_xemu(progress)
        self.assertIn("xemu launched", launched.message)
        self.assertEqual(
            self.launches,
            [("/usr/bin/xemu-test", "-dvd_path", str(self.output))],
        )
        self.assertIn(("Build complete", 4, 4), events)
        self.assertEqual(self.facade.resource_kinds(progress), (("TEST", 2),))
        rows, count = self.facade.browse_resources(
            search="", kind=None, offset=0, limit=250, progress=progress
        )
        self.assertEqual((len(rows), count), (1, 2))
        raw = self.root / "resource.bin"
        self.assertEqual(
            self.facade.export_resource(rows[0], raw, progress).read_bytes(),
            b"raw user export",
        )

    def test_loading_a_new_source_clears_last_build(self) -> None:
        progress = lambda *_args: None
        self.facade.load_source(self.root / "NFL2K5.iso", progress)
        self.facade.build_iso(self.output, progress)
        self.assertTrue(self.facade.can_launch_xemu)
        self.facade.load_source(self.root / "NFL2K5.iso", progress)
        self.assertFalse(self.facade.can_launch_xemu)

    def test_playbook_viewer_is_lazy_source_bound_and_exports_universal_raw(self) -> None:
        inspectors: list[_PlaybookInspector] = []

        def inspector_factory(index: _UniversalIndex) -> _PlaybookInspector:
            inspector = _PlaybookInspector(index)
            inspectors.append(inspector)
            return inspector

        facade = Nfl2k5StudioFacade(
            uniform_catalog=self.catalog,  # type: ignore[arg-type]
            source_cache=self.source_cache,  # type: ignore[arg-type]
            build_service=self.build_service,  # type: ignore[arg-type]
            session_factory=_Session,  # type: ignore[arg-type]
            xemu_command=(),
            universal_index_factory=lambda _cache: _UniversalIndex(),  # type: ignore[arg-type]
            playbook_inspector_factory=inspector_factory,  # type: ignore[arg-type]
            stadium_cache_coordinator=_StadiumCoordinator(),  # type: ignore[arg-type]
        )
        events: list[tuple[str, int, int]] = []
        progress = lambda stage, done, total: events.append((stage, done, total))
        facade.load_source(self.root / "NFL2K5.iso", progress)
        self.assertTrue(facade.playbook_available)
        self.assertEqual(inspectors, [])

        books = facade.browse_playbooks("nickel defense", progress)
        self.assertEqual([book.asset_id for book in books], ["private.play.1"])
        self.assertEqual(len(inspectors), 1)
        self.assertIn(("Reading private PLAY structure", 2, 2), events)

        exported = self.root / "synthetic-play.bin"
        self.assertEqual(
            facade.export_playbook("private.play.1", exported, progress),
            exported,
        )
        self.assertEqual(exported.read_bytes(), b"raw user export")
        self.assertEqual(facade.modified_count, 0)
        project = self.root / "playbook-viewer.2k5mod"
        facade.save_project(project, progress)
        self.assertNotIn(b"Synthetic", project.read_bytes())
        self.assertNotIn(b"private.play", project.read_bytes())

        # Loading another source invalidates the decoded private service. A new
        # inspector is not constructed until the tab is used again.
        facade.load_source(self.root / "NFL2K5.iso", progress)
        self.assertEqual(len(inspectors), 1)
        facade.browse_playbooks("", progress)
        self.assertEqual(len(inspectors), 2)

    def test_stadium_cache_is_prepared_lazily_on_first_browse(self) -> None:
        coordinator = _PreparedStadiumCoordinator()
        facade = Nfl2k5StudioFacade(
            uniform_catalog=self.catalog,  # type: ignore[arg-type]
            source_cache=self.source_cache,  # type: ignore[arg-type]
            build_service=self.build_service,  # type: ignore[arg-type]
            session_factory=_Session,  # type: ignore[arg-type]
            xemu_command=(),
            universal_index_factory=lambda _cache: _UniversalIndex(),  # type: ignore[arg-type]
            stadium_cache_coordinator=coordinator,  # type: ignore[arg-type]
        )
        progress = lambda *_args: None
        facade.load_source(self.root / "NFL2K5.iso", progress)
        self.assertTrue(facade.stadium_available)
        self.assertEqual(coordinator.ensure_calls, 0)
        facade._studio_from_stadium_cache = lambda _result: _StadiumStudio()  # type: ignore[method-assign]

        self.assertEqual(facade.stadium_scenes("giants", progress), ("stadium:giants",))
        self.assertEqual(coordinator.ensure_calls, 1)
        self.assertEqual(facade.stadium_scenes("jets", progress), ("stadium:jets",))
        self.assertEqual(coordinator.ensure_calls, 1)

    def test_replace_stadium_textures_from_gltf_routes_to_the_studio(self) -> None:
        progress = lambda *_args: None
        self.facade.load_source(self.root / "NFL2K5.iso", progress)
        studio = _TextureWriteBackStudio(self.facade._lock)
        self.facade._stadium_studio = studio  # type: ignore[assignment]
        edited = self.root / "edited-stadium.gltf"
        edited.write_bytes(b"edited stadium gltf")
        events: list[tuple[str, int, int]] = []
        progress = lambda stage, done, total: events.append((stage, done, total))

        receipts = self.facade.replace_stadium_textures_from_gltf(
            _TextureWriteBackStudio.SCENE_ID, edited, progress
        )

        self.assertEqual(studio.calls, [(_TextureWriteBackStudio.SCENE_ID, edited)])
        self.assertEqual(receipts, studio.receipts)
        self.assertEqual(
            [receipt.texture_id for receipt in receipts],
            [
                f"{_TextureWriteBackStudio.SCENE_ID}.texture0000",
                f"{_TextureWriteBackStudio.SCENE_ID}.texture0001",
            ],
        )
        self.assertIn(("Applying edited stadium textures", 0, 1), events)
        self.assertIn(("Edited stadium textures applied", 1, 1), events)

        # Fail-closed: an unprepared studio is a readable refusal, not a crash.
        self.facade._stadium_studio = None
        with self.assertRaisesRegex(ValidationError, "Stadium previews"):
            self.facade.replace_stadium_textures_from_gltf(
                _TextureWriteBackStudio.SCENE_ID, edited, progress
            )

    def test_shareable_project_save_and_load_swap_the_working_session(self) -> None:
        progress = lambda *_args: None
        self.facade.load_source(self.root / "NFL2K5.iso", progress)
        project = self.root / "shared.2k5mod"
        saved = self.facade.save_project(project, progress)
        self.assertEqual(saved.output, project)
        self.assertEqual(saved.project_identity.path, project)
        loaded = self.facade.load_project(project, progress)
        self.assertIn("Loaded 1 replacement", loaded.message)
        self.assertEqual(loaded.project_identity, saved.project_identity)
        self.assertEqual(set(self.facade.modified_asset_ids), {"asset.one"})

    def test_project_identity_race_discards_candidate_and_keeps_active_session(
        self,
    ) -> None:
        sessions: list[_Session] = []

        def session_factory(cache: object, catalog: object) -> _Session:
            session = _Session(cache, catalog)
            sessions.append(session)
            return session

        facade = Nfl2k5StudioFacade(
            uniform_catalog=self.catalog,  # type: ignore[arg-type]
            source_cache=self.source_cache,  # type: ignore[arg-type]
            build_service=self.build_service,  # type: ignore[arg-type]
            session_factory=session_factory,  # type: ignore[arg-type]
            xemu_command=(),
            universal_index_factory=lambda _cache: _UniversalIndex(),  # type: ignore[arg-type]
            stadium_cache_coordinator=_StadiumCoordinator(),  # type: ignore[arg-type]
        )
        progress = lambda *_args: None
        facade.load_source(self.root / "NFL2K5.iso", progress)
        active = sessions[0]
        project = self.root / "raced.2k5mod"
        project.write_bytes(b"first")
        opened = project_target_identity(project)
        changed = ProjectTargetIdentity(
            opened.path,
            opened.device,
            opened.inode,
            opened.size + 1,
            opened.modified_ns + 1,
            opened.changed_ns + 1,
        )

        with mock.patch(
            "mod_editor.studio.facade.project_target_identity",
            side_effect=(opened, changed),
        ), self.assertRaisesRegex(ValidationError, "changed outside"):
            facade.load_project(project, progress)

        self.assertEqual(len(sessions), 2)
        self.assertIs(facade._session, active)
        self.assertFalse(active.discarded)
        self.assertTrue(sessions[1].discarded)

    def test_text_and_number_exports_publish_staged_values_without_overwrite(self) -> None:
        catalog = _TextCatalog()
        self.facade._text_catalog = catalog  # type: ignore[assignment]
        self.facade._session = _TextSession(self.cache, self.catalog)  # type: ignore[assignment]
        events: list[tuple[str, int, int]] = []
        progress = lambda stage, done, total: events.append((stage, done, total))

        text_destination = self.root / "staged-name.txt"
        number_destination = self.root / "staged-number.txt"
        self.assertEqual(
            self.facade.export_text(
                "text.current.first", text_destination, progress
            ).read_bytes(),
            b"Staged Name\n",
        )
        self.assertEqual(
            self.facade.export_number(
                "number.current.jersey", number_destination, progress
            ).read_bytes(),
            b"88\n",
        )
        self.assertIn(("Text exported", 1, 1), events)
        self.assertIn(("Jersey number exported", 1, 1), events)
        with self.assertRaisesRegex(ValidationError, "already exists"):
            self.facade.export_number(
                "number.current.jersey", number_destination, progress
            )
        self.assertEqual(number_destination.read_bytes(), b"88\n")

    def test_stadium_project_prepares_private_cache_then_retries_atomically(self) -> None:
        coordinator = _PreparedStadiumCoordinator()
        sessions: list[_StadiumProjectSession] = []

        def session_factory(cache: object, catalog: object) -> _StadiumProjectSession:
            session = _StadiumProjectSession(cache, catalog)
            sessions.append(session)
            return session

        facade = Nfl2k5StudioFacade(
            uniform_catalog=self.catalog,  # type: ignore[arg-type]
            source_cache=self.source_cache,  # type: ignore[arg-type]
            build_service=self.build_service,  # type: ignore[arg-type]
            session_factory=session_factory,  # type: ignore[arg-type]
            xemu_command=(),
            universal_index_factory=lambda _cache: _UniversalIndex(),  # type: ignore[arg-type]
            stadium_cache_coordinator=coordinator,  # type: ignore[arg-type]
        )
        progress = lambda *_args: None
        facade.load_source(self.root / "NFL2K5.iso", progress)
        project = self.root / "stadium-project.2k5mod"
        project.write_bytes(b"synthetic project")

        def bind_stadium(
            result: object, _cache: object, session: _StadiumProjectSession,
        ) -> _StadiumStudio:
            self.assertEqual(result.scene_count, 477)
            session.stadium_ready = True
            return _StadiumStudio()

        facade._studio_for_session = bind_stadium  # type: ignore[method-assign]
        loaded = facade.load_project(project, progress)

        self.assertIn("Loaded 1 replacement", loaded.message)
        self.assertEqual(coordinator.ensure_calls, 1)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[1].project_load_attempts, 2)
        self.assertEqual(set(facade.modified_asset_ids), {"asset.one"})

    def test_crib_catalog_callbacks_and_unified_build_dispatch(self) -> None:
        facade, crib_catalog, sessions = self._make_crib_facade()
        progress = lambda *_args: None
        self.assertEqual(tuple(facade.list_crib_assets()), ())

        facade.load_source(self.root / "NFL2K5.iso", progress)
        self.assertEqual(tuple(facade.list_crib_assets()), crib_catalog.assets)
        self.assertIs(sessions[0].crib_catalog, crib_catalog)
        self.assertIsNotNone(sessions[0].crib_io)

        asset_id = crib_catalog.assets[0].asset_id
        preview = facade.preview_crib_asset(asset_id, progress)
        self.assertEqual(preview.read_bytes(), b"synthetic crib png")
        exported = self.root / "crib-export.png"
        self.assertEqual(
            facade.export_crib_asset(asset_id, exported, progress), exported
        )
        replacement = self.root / "crib-replacement.png"
        replacement.write_bytes(b"user replacement")
        facade.replace_crib_photo(asset_id, replacement, progress)
        self.assertEqual(set(facade.modified_crib_asset_ids), {asset_id})

        project = self.root / "crib-project.2k5mod"
        self.assertEqual(facade.save_project(project, progress).output, project)
        self.assertEqual(
            facade.build_iso(self.output, progress).output_xiso, self.output
        )

        facade.revert_crib_photo(asset_id, progress)
        self.assertEqual(set(facade.modified_crib_asset_ids), set())
        second_output = self.root / "second-output.xiso.iso"
        self.assertEqual(
            facade.build_iso(second_output, progress).output_xiso, second_output
        )

    def test_project_session_reuses_source_bound_crib_services(self) -> None:
        facade, crib_catalog, sessions = self._make_crib_facade()
        progress = lambda *_args: None
        facade.load_source(self.root / "NFL2K5.iso", progress)
        original_io = sessions[0].crib_io
        project = self.root / "shared-crib.2k5mod"
        project.write_bytes(b"synthetic project")

        facade.load_project(project, progress)

        self.assertEqual(len(sessions), 2)
        self.assertIs(sessions[1].crib_catalog, crib_catalog)
        self.assertIs(sessions[1].crib_io, original_io)


if __name__ == "__main__":
    unittest.main()
