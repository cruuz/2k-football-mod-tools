"""Beta 72.1: a difference only in the change time is not a project or Build refusal.

A Windows 11 tester could not open his project on beta 72: "The project changed
outside Mod Studio while it was opening: changed_ns", with identical path, size,
mtime_ns, SHA-256 and file ID. The open compared two fd stats of the .2k5mod
taken on two descriptors minutes apart. On Windows, Python 3.12 os.fstat reports
FILE_BASIC_INFO.ChangeTime as st_ctime, and backup, antivirus, indexing and sync
software move it without touching a byte. The Build's receipt check compared the
same field across the build and verify processes.

Linux reproduces the shape with os.chmod to the mode a file already has (Windows
with a read-only toggle), and the reported pair is also replayed through a patched
identity reader. Every negative test proves a real content change (size, mtime,
SHA-256 or file ID) still refuses. Synthetic inputs only; no retail bytes.
"""

from contextlib import redirect_stdout
import dataclasses
import hashlib
import importlib.util
import io
import math
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]

from mod_editor.core.equipment_staging import _verified_art
from mod_editor.core.errors import ValidationError
from mod_editor.core import nfl2k5_music_archive as music_archive
from mod_editor.core import nfl2k5_music_banks as music_banks
from mod_editor.core import nfl2k5_music_build as music_build
from mod_editor.studio import music_service as music_service_module
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.project_archive import (
    ProjectTargetIdentity,
    _publish_archive,
    project_target_identity,
)

# The two ctime_ns values from the tester's screenshot; nothing else differed.
REPORTED_BEFORE_CTIME_NS = 1789783449403525400
REPORTED_AFTER_CTIME_NS = 1789833271400819200
REPORTED_DELTA_NS = REPORTED_AFTER_CTIME_NS - REPORTED_BEFORE_CTIME_NS


def fd_stat(path: Path) -> os.stat_result:
    """The stat family the project identity uses: os.fstat of a fresh descriptor."""

    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        return os.fstat(descriptor)
    finally:
        os.close(descriptor)


def bump_change_time(path: Path) -> os.stat_result:
    """Move only the change time, the way sync, backup or antivirus software does.

    POSIX updates st_ctime on a chmod to the mode the file already has. On
    Windows a read-only toggle is a metadata change that moves ChangeTime, which
    is what Python 3.12 os.fstat reports as st_ctime. The kernel file clock is
    coarse, so the helper retries until the field has really moved.
    """

    path = Path(path)
    before = fd_stat(path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    for _attempt in range(100):
        time.sleep(0.011)
        if os.name == "nt":
            os.chmod(path, stat.S_IREAD)
        os.chmod(path, mode)
        after = fd_stat(path)
        if after.st_ctime_ns != before.st_ctime_ns:
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                    before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
                raise AssertionError("the change-time bump changed more than the change time")
            return after
    raise unittest.SkipTest("this filesystem did not move the change time on a mode change")


def rewrite_same_size_keep_mtime(path: Path, offset: int = 0) -> None:
    """Flip one byte and restore the old mtime: only the bytes and the change time move."""

    info = os.stat(path)
    time.sleep(0.02)
    with Path(path).open("r+b") as stream:
        stream.seek(offset)
        value = stream.read(1)
        stream.seek(offset)
        stream.write(bytes([value[0] ^ 0xFF]))
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_backend():
    spec = importlib.util.spec_from_file_location(
        "_b721_visual_mod_project", ROOT / "tools/nfl2k5_visual_mod_project.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Project open (facade.load_project) and fast save (project_archive)


class _Catalog:
    pass


class _SourceCache:
    def __init__(self, cache: object) -> None:
        self.cache = cache

    def index(self, _path: Path, progress: object) -> object:
        progress("Game index ready", 1, 1)
        return self.cache


class _UniversalIndex:
    asset_count = 0

    def kinds(self) -> tuple:
        return ()

    def query(self, **_kwargs: object) -> tuple:
        return ()


class _StadiumCoordinator:
    def load_existing(self, _cache: object) -> None:
        return None

    def ensure(self, _cache: object, _progress: object) -> object:
        raise AssertionError("no Stadium work in these tests")


class _Session:
    """Stands in for StudioSession; ``during_load`` runs where the archive is read."""

    def __init__(self, cache: object, catalog: object, during_load=None) -> None:
        self.cache = cache
        self.catalog = catalog
        self.during_load = during_load
        self.modified_asset_ids = frozenset()
        self.modified_count = 0
        self.can_undo = False
        self.discarded = False

    def load_shareable_project(self, source: Path) -> int:
        if self.during_load is not None:
            self.during_load(Path(source))
        self.modified_asset_ids = frozenset({"asset.one"})
        self.modified_count = 1
        return 1

    def discard_private_workspace(self) -> None:
        self.discarded = True


class ProjectOpenChangeTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="b721-open-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        config = mock.patch("mod_editor.studio.xemu_settings.config_path",
                            return_value=self.root / "xemu.toml")
        config.start()
        self.addCleanup(config.stop)
        self.sessions: list[_Session] = []
        self.during_load = None

        def factory(cache: object, catalog: object) -> _Session:
            session = _Session(cache, catalog, self.during_load)
            self.sessions.append(session)
            return session

        cache = SimpleNamespace(
            source=SimpleNamespace(selected_path=str(self.root / "NFL2K5.iso")),
            resource_count=86882,
        )
        self.facade = Nfl2k5StudioFacade(
            uniform_catalog=_Catalog(),  # type: ignore[arg-type]
            source_cache=_SourceCache(cache),  # type: ignore[arg-type]
            build_service=SimpleNamespace(),  # type: ignore[arg-type]
            session_factory=factory,  # type: ignore[arg-type]
            xemu_command=(),
            universal_index_factory=lambda _cache: _UniversalIndex(),  # type: ignore[arg-type]
            stadium_cache_coordinator=_StadiumCoordinator(),  # type: ignore[arg-type]
        )
        self.progress = lambda *_args: None
        self.facade.load_source(self.root / "NFL2K5.iso", self.progress)
        self.active = self.facade._session
        self.project = self.root / "My NFL 2K5 Mod - BALTIMORE RAVENS (MOD).2k5mod"
        self.project.write_bytes(b"PK\x03\x04 synthetic project bytes " * 64)

    def load(self, during_load=None):
        self.during_load = during_load
        return self.facade.load_project(self.project, self.progress)

    def test_open_accepts_a_change_time_moved_while_the_project_was_opening(self) -> None:
        opened = project_target_identity(self.project)
        result = self.load(bump_change_time)
        self.assertIn("Loaded 1 replacement", result.message)
        self.assertIs(self.facade._session, self.sessions[-1])
        self.assertFalse(self.sessions[-1].discarded)
        # The returned identity is the fresh one, so the next fast save compares
        # against the change time the file has now.
        self.assertNotEqual(result.project_identity.changed_ns, opened.changed_ns)
        self.assertEqual(
            dataclasses.replace(result.project_identity, changed_ns=opened.changed_ns), opened)

    def test_open_accepts_the_reported_windows_identity_pair(self) -> None:
        opened = project_target_identity(self.project)
        before = dataclasses.replace(opened, changed_ns=REPORTED_BEFORE_CTIME_NS)
        after = dataclasses.replace(opened, changed_ns=REPORTED_AFTER_CTIME_NS)
        with mock.patch("mod_editor.studio.facade.project_target_identity",
                        side_effect=(before, after)):
            result = self.load()
        self.assertIn("Loaded 1 replacement", result.message)
        self.assertEqual(result.project_identity, after)
        self.assertIs(self.facade._session, self.sessions[-1])

    def assert_refused_and_kept(self, during_load, *fields: str) -> str:
        with self.assertRaises(ValidationError) as caught:
            self.load(during_load)
        message = str(caught.exception)
        self.assertIn("The project changed outside Mod Studio while it was opening: ", message)
        for field in fields:
            self.assertIn(field, message.split(".\n", 1)[0])
        self.assertIn("The current workspace was kept.", message)
        self.assertIs(self.facade._session, self.active)
        self.assertTrue(self.sessions[-1].discarded)
        return message

    def test_open_still_refuses_new_bytes(self) -> None:
        def grow(path: Path) -> None:
            with path.open("ab") as stream:
                stream.write(b"!")

        self.assert_refused_and_kept(grow, "size", "SHA-256")

    def test_open_still_refuses_a_same_size_rewrite_that_restored_the_mtime(self) -> None:
        # Size, mtime and file ID all match: only the change time and the
        # SHA-256 differ, and the SHA-256 is what refuses.
        message = self.assert_refused_and_kept(
            lambda path: rewrite_same_size_keep_mtime(path, 40), "SHA-256")
        self.assertNotIn("size", message.split(".\n", 1)[0])

    def test_open_still_refuses_a_replacement_file_with_identical_bytes(self) -> None:
        def swap(path: Path) -> None:
            info = os.stat(path)
            twin = path.with_name(path.name + ".twin")
            twin.write_bytes(path.read_bytes())
            os.utime(twin, ns=(info.st_atime_ns, info.st_mtime_ns))
            os.replace(twin, path)

        self.assert_refused_and_kept(swap, "inode")


class FastSaveChangeTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="b721-save-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.target = self.root / "saved.2k5mod"
        self.target.write_bytes(b"project saved earlier")
        self.expected = project_target_identity(self.target)
        self.pending = self.root / ".pending-save"
        self.pending.write_bytes(b"project saved now")

    def test_fast_save_accepts_a_change_time_only_difference(self) -> None:
        bump_change_time(self.target)
        _publish_archive(self.pending, self.target, replace=True, expected_target=self.expected)
        self.assertEqual(self.target.read_bytes(), b"project saved now")

    def test_fast_save_accepts_the_reported_windows_pair(self) -> None:
        drifted = dataclasses.replace(
            self.expected, changed_ns=self.expected.changed_ns + REPORTED_DELTA_NS)
        with mock.patch("mod_editor.studio.project_archive.project_target_identity",
                        return_value=drifted):
            _publish_archive(self.pending, self.target, replace=True,
                             expected_target=self.expected)
        self.assertEqual(self.target.read_bytes(), b"project saved now")

    def test_fast_save_still_refuses_a_content_change(self) -> None:
        time.sleep(0.02)
        self.target.write_bytes(b"project saved elsewhere!")
        with self.assertRaisesRegex(ValidationError, "active project changed outside Mod Studio"):
            _publish_archive(self.pending, self.target, replace=True,
                             expected_target=self.expected)
        self.assertEqual(self.target.read_bytes(), b"project saved elsewhere!")

    def test_fast_save_still_refuses_another_file_at_the_same_path(self) -> None:
        other = ProjectTargetIdentity(
            self.expected.path, self.expected.device, self.expected.inode + 1,
            self.expected.size, self.expected.modified_ns, self.expected.changed_ns)
        with self.assertRaisesRegex(ValidationError, "active project changed outside Mod Studio"):
            _publish_archive(self.pending, self.target, replace=True, expected_target=other)
        self.assertEqual(self.target.read_bytes(), b"project saved earlier")


# --------------------------------------------------------------------------
# Build: the receipt check between the build and verify processes


class BuildReceiptChangeTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        import b661_build_fixture as fixture

        self.temporary = tempfile.TemporaryDirectory(prefix="b721-build-")
        self.addCleanup(self.temporary.cleanup)
        self.root = root = Path(self.temporary.name).resolve()
        equipment, _ = fixture.create(root)
        self.tool = tool = load_backend()
        fixture.configure(tool, root)
        asset, png = equipment.png(independent=False, rgba=bytes((20, 150, 80, 255)) * 1024)
        self.project = root / "project.json"
        self.project.write_bytes(tool.canonical_json(dict(
            schema=tool.SCHEMA, purpose="72.1 change time proof",
            edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id=asset, png=str(png))])))
        self.source = root / "source.iso"
        self.output = root / "out.iso"
        self.manifest = root / "manifest.json"
        self.artifacts = root / "artifacts"
        with redirect_stdout(io.StringIO()):
            tool.build(self.project, self.source, self.output, self.manifest, self.artifacts,
                       root / "0", root / "inventory.json")
        self.receipt = tool.file_digest(self.manifest)

    def verify(self) -> dict:
        return self.tool.verify_written(self.project, self.source, self.output,
                                        self.manifest, self.artifacts, self.receipt)

    def whole_file_hashes(self):
        size = self.output.stat().st_size
        calls = []
        real = self.tool.common.sha256_fd

        def counting(descriptor, offset=0, length=None):
            if offset == 0 and length == size:
                calls.append(descriptor)
            return real(descriptor, offset, length)

        return calls, mock.patch.object(self.tool.common, "sha256_fd", side_effect=counting)

    def test_receipt_check_rehashes_and_accepts_change_time_drift(self) -> None:
        bump_change_time(self.output)
        bump_change_time(self.source)
        calls, counting = self.whole_file_hashes()
        with counting:
            result = self.verify()
        self.assertTrue(result["written_spans_verified"])
        self.assertEqual(result["output_sha256"], self.tool.file_digest(self.output))
        self.assertEqual(len(calls), 2, "source and output are each hashed once")

    def test_receipt_check_without_drift_keeps_the_fast_path(self) -> None:
        calls, counting = self.whole_file_hashes()
        with counting:
            self.assertTrue(self.verify()["written_spans_verified"])
        self.assertEqual(calls, [])

    def test_receipt_check_accepts_the_reported_shape(self) -> None:
        real = self.tool.file_snapshot

        def drifted(descriptor):
            row = real(descriptor)
            return [*row[:4], row[4] + REPORTED_DELTA_NS]

        with mock.patch.object(self.tool, "file_snapshot", side_effect=drifted):
            self.assertTrue(self.verify()["written_spans_verified"])

    def test_receipt_check_still_refuses_a_moved_mtime(self) -> None:
        real = self.tool.file_snapshot

        def touched(descriptor):
            row = real(descriptor)
            return [*row[:3], row[3] + 1, row[4]]

        with mock.patch.object(self.tool, "file_snapshot", side_effect=touched), \
                self.assertRaisesRegex(self.tool.ProjectError, "changed since the full build check"):
            self.verify()

    def test_receipt_check_still_refuses_a_gap_rewrite(self) -> None:
        time.sleep(0.02)
        with self.output.open("r+b") as stream:
            stream.seek(128)
            stream.write(b"tamper")
        with self.assertRaisesRegex(self.tool.ProjectError, "changed since the full build check"):
            self.verify()

    def test_receipt_check_rehash_refuses_a_rewrite_that_restored_the_mtime(self) -> None:
        # Size, mtime and file ID match the receipt; the change time differs, so
        # the whole file is hashed and the bytes outside every span refuse.
        rewrite_same_size_keep_mtime(self.output, 128)
        with self.assertRaisesRegex(self.tool.ProjectError, "changed since the full build check"):
            self.verify()
        rewrite_same_size_keep_mtime(self.output, 128)
        rewrite_same_size_keep_mtime(self.source, 128)
        with self.assertRaisesRegex(self.tool.ProjectError, "changed since the full build check"):
            self.verify()


class BuildProcessesChangeTimeTests(unittest.TestCase):
    """The studio's own split: one backend process builds, a second one verifies."""

    def test_verify_process_accepts_drift_after_the_build_process_exits(self) -> None:
        import b661_build_fixture as fixture

        with tempfile.TemporaryDirectory(prefix="b721-cli-") as folder:
            root = Path(folder).resolve()
            equipment, _ = fixture.create(root)
            asset, png = equipment.png(independent=False, rgba=bytes((20, 150, 80, 255)) * 1024)
            project = root / "project.json"
            tool = load_backend()
            project.write_bytes(tool.canonical_json(dict(
                schema=tool.SCHEMA, purpose="72.1 two process proof",
                edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id=asset, png=str(png))])))
            output = root / "modded.xiso"
            arguments = ["--project", str(project), "--source-xiso", str(root / "source.iso"),
                         "--output-xiso", str(output), "--manifest", str(root / "receipt.json"),
                         "--artifact-dir", str(root / "artifacts"), "--index", str(root / "0"),
                         "--inventory", str(root / "inventory.json")]
            command = [sys.executable, str(Path(fixture.__file__)), str(root)]
            built = subprocess.run([*command, "build", *arguments], capture_output=True,
                                   text=True, timeout=120, cwd=ROOT)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            receipt = next(token.split("=", 1)[1] for token in built.stdout.split()
                           if token.startswith("receipt_sha256="))
            bump_change_time(output)
            bump_change_time(root / "source.iso")
            verified = subprocess.run(
                [*command, "verify", *arguments, "--receipt-sha256", receipt],
                capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertIn("NFL2K5_VISUAL_MOD_VERIFY_PASS mode=materialized", verified.stdout)
            time.sleep(0.02)
            with output.open("r+b") as stream:
                stream.seek(128)
                stream.write(b"tamper")
            refused = subprocess.run(
                [*command, "verify", *arguments, "--receipt-sha256", receipt],
                capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("source/output changed since the full build check", refused.stderr)


# --------------------------------------------------------------------------
# Staged art: the studio's equipment check and the Build's input pin


class StagedArtChangeTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="b721-art-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.png = self.root / "staged.png"
        self.png.write_bytes(b"\x89PNG\r\n\x1a\n staged equipment art " * 16)
        self.digest = sha256(self.png.read_bytes())

    def test_staged_equipment_art_rehashes_on_change_time_drift(self) -> None:
        session = SimpleNamespace()
        self.assertEqual(_verified_art(session, self.png, expected=self.digest), self.digest)
        bump_change_time(self.png)
        self.assertEqual(_verified_art(session, self.png, expected=self.digest), self.digest)
        rewrite_same_size_keep_mtime(self.png, 20)
        with self.assertRaisesRegex(ValidationError, "staged equipment PNG changed outside Mod Studio"):
            _verified_art(session, self.png, expected=self.digest)

    def test_build_input_pin_ignores_change_time_and_refuses_new_bytes(self) -> None:
        tool = load_backend()
        resolved, payload, identity = tool.read_regular_bounded(
            self.png, 1024 * 1024, "project media input")
        pin = tool.InputPin(resolved, payload, len(payload), tool.digest(payload), identity)
        bump_change_time(self.png)
        tool.verify_input_pin(pin)
        rewrite_same_size_keep_mtime(self.png, 20)
        with self.assertRaisesRegex(tool.ProjectError, "pinned input changed during workflow"):
            tool.verify_input_pin(pin)


# --------------------------------------------------------------------------
# Staged music: the Music page and the music/resource Build passes


def tone(path: Path, frames: int = 1025) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setparams((2, 2, 22050, frames, "NONE", "not compressed"))
        wav.writeframes(b"".join(
            struct.pack("<h", round(7000 * math.sin(i * 0.12))) * 2 for i in range(frames)))
    return path


class MusicChangeTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="b721-music-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def music(self):
        from tests.mod_editor.music_fixtures import MusicDisc, music_session

        service, _fixture = music_session(self.root, MusicDisc(self.root))
        return service

    def test_music_original_survives_change_time_drift_on_the_source_cache(self) -> None:
        service = self.music()
        target = service.catalog.get("cribmusic:28").targets[0]
        first = service.original_path(target)
        packs = [pack.path for pack in service.audio.archive.packs]
        for path in packs:
            bump_change_time(path)
        self.assertEqual(service.original_path(target), first)
        time.sleep(0.02)
        with packs[0].open("ab") as stream:
            stream.write(b"\0")
        with self.assertRaisesRegex(ValueError, "Music original or source cache changed"):
            service.original_path(target)

    def test_adding_a_song_survives_change_time_drift_while_it_is_copied(self) -> None:
        service = self.music()
        song = tone(self.root / "Friday Night.wav")
        real_copy = shutil.copyfile

        def copy_then(after):
            def copy(source, destination, *args, **kwargs):
                result = real_copy(source, destination, *args, **kwargs)
                after(Path(source))
                return result
            return copy

        with mock.patch.object(music_service_module.shutil, "copyfile",
                               side_effect=copy_then(bump_change_time)):
            batch = service.prepare_songs([song])
        self.addCleanup(batch.close)
        self.assertEqual(len(batch.rows), 1)

        def grow(path: Path) -> None:
            with path.open("ab") as stream:
                stream.write(b"\0\0\0\0")

        with mock.patch.object(music_service_module.shutil, "copyfile",
                               side_effect=copy_then(grow)), \
                self.assertRaisesRegex(ValueError, "the file changed; add it again"):
            service.prepare_songs([song])

    def test_music_build_identities_ignore_only_the_change_time(self) -> None:
        path = self.root / "authored.wav"
        path.write_bytes(b"RIFF authored song bytes")

        def identities():
            return (music_archive.identity(path), music_banks._identity(path),
                    music_build._stamp(path))

        before = identities()
        bump_change_time(path)
        self.assertEqual(identities(), before)
        time.sleep(0.02)
        path.write_bytes(b"RIFF authored song bytes, edited")
        for now, then in zip(identities(), before):
            self.assertNotEqual(now, then)

    def test_transactional_copy_accepts_drift_and_refuses_new_input_bytes(self) -> None:
        source = self.root / "source.img"
        source.write_bytes(bytes(range(256)) * 32)
        authored = self.root / "authored.wav"
        authored.write_bytes(b"RIFF authored input" * 8)

        def run(output: Path, during):
            def build(_directory, _staged):
                during()
                return "built"

            return music_archive.transactional_copy(
                source, output, source_sha256=sha256(source.read_bytes()), scratch_bytes=0,
                build=build, verify=lambda _staged, built: built + " and checked",
                inputs=(authored,))

        drifted = self.root / "drifted.img"
        result = run(drifted, lambda: (bump_change_time(source), bump_change_time(authored)))
        self.assertEqual(result, ("built", "built and checked"))
        self.assertEqual(drifted.read_bytes(), source.read_bytes())

        def edit_input():
            time.sleep(0.02)
            with authored.open("ab") as stream:
                stream.write(b"!")

        refused = self.root / "refused.img"
        with self.assertRaisesRegex(ValueError, "authored input changed during build"):
            run(refused, edit_input)
        self.assertFalse(refused.exists())


if __name__ == "__main__":
    unittest.main()
