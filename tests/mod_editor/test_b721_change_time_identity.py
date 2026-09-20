"""Beta 72.1: st_ctime decides nothing, on either platform, in either direction.

A Windows 11 tester could not open his project on beta 72: "The project changed
outside Mod Studio while it was opening: changed_ns", with identical path, size,
mtime_ns, SHA-256 and file ID. The open compared two fd stats of the .2k5mod
taken on two descriptors minutes apart, and the Build compared the same field
across its own span and across the build and verify processes.

The field cannot carry those decisions:

* POSIX moves it with no byte changed (a chmod, an xattr write, a restored
  mtime), which is what refused his untouched project.
* Windows never moves it for a change at all. Python reports the file's
  CREATION time in st_ctime there, so a same-size rewrite that puts the
  modification time back leaves every stat field identical, and a stat-only
  check accepts the changed bytes. Software that rewrites or restores a file
  can also reset the creation time, which is the drift he saw.

So a moved change time never refuses on its own, and an equal one never
reassures: every project identity now includes a full-file SHA-256, compared always. Both
directions are exercised on every platform here, the Windows side through
``windows_change_time`` (one frozen st_ctime from every stat call) rather than
by hoping a real touch is visible. APF 2K8 Mod Studio has the same project open
and fast save, so it is covered too. Synthetic inputs only; no retail bytes.
"""

import contextlib
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

from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.project import (
    ProjectError as ApfProjectError,
    ProjectTargetIdentity as ApfProjectTargetIdentity,
    _publish_archive as apf_publish_archive,
    project_target_identity as apf_project_target_identity,
)
from mod_editor.core.equipment_staging import _verified_art
from mod_editor.core.errors import ValidationError
from mod_editor.core import platform_compat
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


def touch_metadata(path: Path) -> bool:
    """Change metadata without touching a byte; report whether st_ctime moved.

    The touch itself is what sync, backup and antivirus software does: a chmod
    to the mode the file already has (a read-only toggle on Windows). POSIX
    answers it with a new st_ctime, after the coarse file clock ticks. Windows
    reports a creation time there and answers with nothing at all, so callers
    assert on the return value rather than assuming the platform showed them
    anything. Whatever the answer, no operation may refuse because of it.
    """

    path = Path(path)
    before = fd_stat(path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    attempts = 2 if os.name == "nt" else 100
    for attempt in range(attempts):
        if attempt:
            time.sleep(0.011)
        if os.name == "nt":
            os.chmod(path, stat.S_IREAD)
        os.chmod(path, mode)
        after = fd_stat(path)
        if after.st_ctime_ns != before.st_ctime_ns:
            if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                    before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
                raise AssertionError("the metadata touch changed more than the change time")
            return True
    return False


FROZEN_CHANGE_TIME_NS = 1_600_000_000_000_000_000


@contextlib.contextmanager
def windows_change_time():
    """Report one constant st_ctime_ns from every stat call, as Windows does.

    Windows puts the creation time in st_ctime, so it stays put through the
    rewrites and metadata touches a POSIX st_ctime would answer. Freezing the
    field is that platform's semantics, and it lets the Windows cases run, and
    fail honestly, on the machine this suite is developed on.
    """

    real = {name: getattr(os, name) for name in ("stat", "lstat", "fstat")}

    def frozen(info: os.stat_result) -> os.stat_result:
        extra = {"st_atime_ns": info.st_atime_ns, "st_mtime_ns": info.st_mtime_ns,
                 "st_ctime_ns": FROZEN_CHANGE_TIME_NS}
        for name in ("st_blksize", "st_blocks", "st_rdev", "st_flags", "st_gen",
                     "st_birthtime", "st_file_attributes", "st_reparse_tag"):
            value = getattr(info, name, None)
            if value is not None:
                extra[name] = value
        return os.stat_result(tuple(info)[:10], extra)

    def wrap(name):
        inner = real[name]

        def call(*args, **kwargs):
            return frozen(inner(*args, **kwargs))

        return call

    with mock.patch.multiple(os, **{name: wrap(name) for name in real}):
        yield


def rewrite_same_size_keep_mtime(path: Path, offset: int = 0) -> None:
    """Flip one byte and restore the old mtime.

    Size, mtime and file ID are unchanged afterwards, and on Windows so is
    st_ctime, so the stat fields say nothing happened. Only the bytes moved.
    """

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


def stat_identity(path: Path) -> tuple:
    """The five fields the staged-art cache keys on, read the way it reads them."""

    info = Path(path).lstat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


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

    def test_open_accepts_a_metadata_touch_while_the_project_was_opening(self) -> None:
        opened = project_target_identity(self.project)
        moved: list[bool] = []
        result = self.load(lambda path: moved.append(touch_metadata(path)))
        self.assertIn("Loaded 1 replacement", result.message)
        self.assertIs(self.facade._session, self.sessions[-1])
        self.assertFalse(self.sessions[-1].discarded)
        # The returned identity is the fresh one, so the next fast save compares
        # against the change time the file has now. Windows shows no move at
        # all, which is why the reported pair below is replayed explicitly.
        if moved[0]:
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


class ProjectIdentityFullHashTests(unittest.TestCase):
    def test_full_sha256_includes_every_byte_with_windows_positional_reader(self) -> None:
        # CRLF and control-Z must survive the binary descriptor on Windows;
        # multiple blocks and the tail must agree with an independent digest.
        payload = bytes(range(256)) * 8193
        with tempfile.TemporaryDirectory(prefix="b74-identity-") as temporary:
            for suffix, capture in ((".2k5mod", project_target_identity),
                                    (".apf2k8mod", apf_project_target_identity)):
                with self.subTest(suffix=suffix), windows_change_time():
                    path = Path(temporary) / ("project" + suffix)
                    path.write_bytes(payload)
                    with mock.patch.object(platform_compat, "pread",
                                           side_effect=platform_compat._pread_via_seek):
                        identity = capture(path)
                    self.assertEqual(identity.sha256, sha256(payload))

    def test_identity_accepts_metadata_only_touch_during_hash(self) -> None:
        real_hash = platform_compat._hash_fd
        with tempfile.TemporaryDirectory(prefix="b74-identity-") as temporary:
            for suffix, capture in ((".2k5mod", project_target_identity),
                                    (".apf2k8mod", apf_project_target_identity)):
                with self.subTest(suffix=suffix):
                    path = Path(temporary) / ("project" + suffix)
                    path.write_bytes(b"same project bytes")
                    before = capture(path)
                    moved = []

                    def hash_then_touch(fd):
                        digest = real_hash(fd)
                        moved.append(touch_metadata(path))
                        return digest

                    with mock.patch.object(platform_compat, "_hash_fd", side_effect=hash_then_touch):
                        after = capture(path)
                    self.assertEqual(before.changed_ns != after.changed_ns, moved[0])
                    self.assertTrue(before.matches_apart_from_change_time(after))

    def test_identity_refuses_size_or_name_change_during_hash(self) -> None:
        real_hash = platform_compat._hash_fd
        with tempfile.TemporaryDirectory(prefix="b74-identity-") as temporary:
            for suffix, capture, error in ((".2k5mod", project_target_identity, ValidationError),
                    (".apf2k8mod", apf_project_target_identity, ApfProjectError)):
                for change in ("truncate", "grow", "replace"):
                    with self.subTest(suffix=suffix, change=change), windows_change_time():
                        path = Path(temporary) / ("project" + suffix)
                        path.write_bytes(b"project bytes")

                        def hash_then_change(fd):
                            digest = real_hash(fd)
                            if change == "replace":
                                twin = path.with_suffix(".twin")
                                shutil.copyfile(path, twin)
                                info = path.stat()
                                os.utime(twin, ns=(info.st_atime_ns, info.st_mtime_ns))
                                try:
                                    os.replace(twin, path)
                                except PermissionError:
                                    # Some Windows filesystems prohibit replacing an open
                                    # file. Report that answer; the OS prevented this race.
                                    self.skipTest("filesystem refused replacement of the open project")
                            else:
                                with path.open("r+b") as stream:
                                    stream.truncate(3 if change == "truncate" else 100)
                            return digest

                        with mock.patch.object(platform_compat, "_hash_fd", side_effect=hash_then_change):
                            with self.assertRaisesRegex(error, "changed while Mod Studio checked it"):
                                capture(path)


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
        moved = touch_metadata(self.target)
        current = project_target_identity(self.target)
        self.assertEqual(current.changed_ns != self.expected.changed_ns, moved)
        self.assertTrue(self.expected.matches_apart_from_change_time(current))
        _publish_archive(self.pending, self.target, replace=True, expected_target=self.expected)
        self.assertEqual(self.target.read_bytes(), b"project saved now")

    def test_fast_save_full_sha256_refuses_same_size_rewrite_restored_mtime(self) -> None:
        # Probe beyond the first hash block as well as both ends. A prefix or
        # sampled check must not masquerade as the full-file SHA-256 contract.
        original = bytes(range(256)) * 8193
        for windows in (False, True):
            for offset in (0, 1024 * 1024 + 17, len(original) - 1):
                with self.subTest(windows=windows, offset=offset), contextlib.ExitStack() as stack:
                    if windows:
                        stack.enter_context(windows_change_time())
                    self.target.write_bytes(original)
                    self.pending.write_bytes(b"pending project bytes")
                    expected = project_target_identity(self.target)
                    before = stat_identity(self.target)
                    rewrite_same_size_keep_mtime(self.target, offset)
                    after = stat_identity(self.target)
                    self.assertEqual(before[:4], after[:4])
                    if windows:
                        self.assertEqual(before, after)
                    external = self.target.read_bytes()
                    self.assertNotEqual(sha256(external), sha256(original))
                    with self.assertRaises(ValidationError) as caught:
                        _publish_archive(self.pending, self.target, replace=True,
                                         expected_target=expected)
                    self.assertEqual(str(caught.exception),
                        "The active project changed outside Mod Studio. It was not "
                        "overwritten; use Save Project As or reopen it first.")
                    self.assertEqual(self.target.read_bytes(), external)
                    self.assertTrue(self.pending.is_file())

    def test_fast_save_still_refuses_only_a_moved_mtime(self) -> None:
        original = self.target.read_bytes()
        info = self.target.stat()
        os.utime(self.target, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
        self.assertNotEqual(fd_stat(self.target).st_mtime_ns, info.st_mtime_ns)
        with self.assertRaisesRegex(ValidationError, "active project changed outside Mod Studio"):
            _publish_archive(self.pending, self.target, replace=True,
                             expected_target=self.expected)
        self.assertEqual(self.target.read_bytes(), original)

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
        original = self.target.read_bytes()
        with windows_change_time():
            before = stat_identity(self.target)
            twin = self.target.with_suffix(".twin")
            twin.write_bytes(original)
            os.utime(twin, ns=(self.target.stat().st_atime_ns, before[3]))
            os.replace(twin, self.target)
            after = stat_identity(self.target)
            self.assertEqual(before[2:], after[2:])
            self.assertNotEqual(before[:2], after[:2])
            with self.assertRaisesRegex(ValidationError, "active project changed outside Mod Studio"):
                _publish_archive(self.pending, self.target, replace=True, expected_target=self.expected)
        self.assertEqual(self.target.read_bytes(), original)



# --------------------------------------------------------------------------
# Build: the build's own snapshot pair, and the receipt check between the
# build and verify processes


class _BuildFixture(unittest.TestCase):
    """The real backend over the synthetic b661 source; one build takes about 0.5 s."""

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

    def build(self) -> dict:
        with redirect_stdout(io.StringIO()):
            result = self.tool.build(self.project, self.source, self.output, self.manifest,
                                     self.artifacts, self.root / "0",
                                     self.root / "inventory.json")
        self.receipt = self.tool.file_digest(self.manifest)
        return result

    def verify(self) -> dict:
        return self.tool.verify_written(self.project, self.source, self.output,
                                        self.manifest, self.artifacts, self.receipt)

    def whole_file_hashes(self):
        size = self.source.stat().st_size
        calls = []
        real = self.tool.common.sha256_fd

        def counting(descriptor, offset=0, length=None):
            if offset == 0 and length == size:
                calls.append(descriptor)
            return real(descriptor, offset, length)

        return calls, mock.patch.object(self.tool.common, "sha256_fd", side_effect=counting)

    def after_union(self, action):
        """Run ``action`` inside build(), after the union pass and before its final check."""

        real = self.tool.verify_union

        def union_then(*args, **kwargs):
            result = real(*args, **kwargs)
            action()
            return result

        return mock.patch.object(self.tool, "verify_union", side_effect=union_then)


def fd_snapshot(path: Path) -> list[int]:
    info = fd_stat(path)
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


class BuildSnapshotChangeTimeTests(_BuildFixture):
    """The build's own snapshot pair spans compile, copy and the union pass."""

    def test_build_accepts_a_metadata_touch_mid_build(self) -> None:
        calls, counting = self.whole_file_hashes()
        seen: dict[str, list[int]] = {}
        moved: list[bool] = []

        def touch_both() -> None:
            for key, path in (("source_stat", self.source), ("output_stat", self.output)):
                moved.append(touch_metadata(path))
                seen[key] = fd_snapshot(path)

        with self.after_union(touch_both), counting:
            result = self.build()
        # POSIX shows the touch and the gate settles it by hashing; Windows
        # reports a creation time and shows nothing, so the gate passes without
        # a read. Neither refuses, and the receipt records what the gate saw.
        self.assertEqual(len(calls), 2 if all(moved) else 0)
        self.assertEqual({key: result["written_receipt"][key] for key in seen}, seen)
        self.assertTrue(self.verify()["written_spans_verified"])

    def test_build_accepts_the_reported_shape_mid_build(self) -> None:
        real = self.tool.file_snapshot
        union_done: list[bool] = []
        real_rows: list[list[int]] = []

        def drifted(descriptor):
            row = real(descriptor)
            if not union_done:
                return row
            real_rows.append(row)
            return [*row[:4], row[4] + REPORTED_DELTA_NS]

        with self.after_union(lambda: union_done.append(True)), \
                mock.patch.object(self.tool, "file_snapshot", side_effect=drifted):
            result = self.build()
        recorded = result["written_receipt"]["output_stat"]
        self.assertEqual(recorded[:4], fd_snapshot(self.output)[:4])
        self.assertIn(recorded[4] - REPORTED_DELTA_NS, {row[4] for row in real_rows})
        self.assertTrue(self.output.is_file())

    def assert_build_refused(self) -> None:
        with self.assertRaisesRegex(self.tool.ProjectError,
                                    "source or output changed before final manifest commit"):
            self.build()
        self.assertFalse(self.output.exists(), "a refused build publishes no output")
        self.assertFalse(self.manifest.exists())

    def test_build_refuses_new_bytes_with_the_old_mtime_where_the_change_time_moves(self) -> None:
        # POSIX semantics: the rewrite moves st_ctime, so the build's own gate
        # hashes the file against the union pass and refuses there.
        for name in ("output", "source"):
            with self.subTest(file=name):
                self.setUp()
                path = getattr(self, name)
                real = self.tool.file_snapshot
                union_done: list[bool] = []

                def moved(descriptor):
                    row = real(descriptor)
                    return [*row[:4], row[4] + 1] if union_done else row

                def tamper() -> None:
                    union_done.append(True)
                    rewrite_same_size_keep_mtime(path, 128)

                with self.after_union(tamper), \
                        mock.patch.object(self.tool, "file_snapshot", side_effect=moved):
                    self.assert_build_refused()

    def test_new_bytes_the_stat_cannot_see_are_refused_before_publication(self) -> None:
        # Windows semantics: nothing in the stat moves, so the build's gate has
        # nothing to see and the manifest is written. The verifier hashes both
        # files against that receipt before anything is published, and refuses.
        for name in ("output", "source"):
            with self.subTest(file=name):
                self.setUp()
                path = getattr(self, name)
                with windows_change_time():
                    with self.after_union(lambda: rewrite_same_size_keep_mtime(path, 128)):
                        self.build()
                    self.assertTrue(self.output.is_file(), "the build itself sees nothing")
                    with self.assertRaisesRegex(
                            self.tool.ProjectError,
                            "build files changed during receipt verification"):
                        self.verify()

    def test_build_refuses_a_moved_mtime_mid_build_without_rehashing(self) -> None:
        real = self.tool.file_snapshot
        union_done: list[bool] = []

        def touched(descriptor):
            row = real(descriptor)
            return [*row[:3], row[3] + 1, row[4]] if union_done else row

        calls, counting = self.whole_file_hashes()
        with self.after_union(lambda: union_done.append(True)), counting, \
                mock.patch.object(self.tool, "file_snapshot", side_effect=touched):
            self.assert_build_refused()
        self.assertEqual(calls, [])


class BuildReceiptChangeTimeTests(_BuildFixture):
    """The verifier process on new descriptors, against the build's receipt."""

    def setUp(self) -> None:
        super().setUp()
        self.build()

    def test_receipt_check_accepts_a_metadata_touch(self) -> None:
        touch_metadata(self.output)
        touch_metadata(self.source)
        calls, counting = self.whole_file_hashes()
        with counting:
            result = self.verify()
        self.assertTrue(result["written_spans_verified"])
        self.assertEqual(result["output_sha256"], self.tool.file_digest(self.output))
        self.assertEqual(len(calls), 2, "source and output are each hashed once")

    def test_receipt_check_always_proves_the_content(self) -> None:
        # Nothing moved at all, and both files are still hashed in full: an
        # equal stat is not proof on Windows, so it is never taken as one.
        calls, counting = self.whole_file_hashes()
        with counting:
            self.assertTrue(self.verify()["written_spans_verified"])
        self.assertEqual(len(calls), 2)
        with windows_change_time():
            calls, counting = self.whole_file_hashes()
            with counting:
                self.assertTrue(self.verify()["written_spans_verified"])
            self.assertEqual(len(calls), 2)

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

    def test_receipt_check_refuses_a_rewrite_that_restored_the_mtime(self) -> None:
        # Size, mtime and file ID all still match the receipt, and on Windows
        # so does st_ctime. The bytes are what refuses, on either platform.
        for frozen in (False, True):
            for name in ("output", "source"):
                with self.subTest(windows=frozen, file=name):
                    self.setUp()
                    with contextlib.ExitStack() as stack:
                        if frozen:
                            stack.enter_context(windows_change_time())
                        rewrite_same_size_keep_mtime(getattr(self, name), 128)
                        with self.assertRaisesRegex(
                                self.tool.ProjectError,
                                "build files changed during receipt verification"):
                            self.verify()

    def during_verify(self, action):
        """Run ``action`` inside verify_written, after its first check, before its last."""

        real = self.tool.verify_input_pin

        def pin_then(pin):
            real(pin)
            action()

        return mock.patch.object(self.tool, "verify_input_pin", side_effect=pin_then)

    def test_receipt_check_accepts_a_change_time_move_while_verifying(self) -> None:
        def touch_both() -> None:
            touch_metadata(self.source)
            touch_metadata(self.output)

        calls, counting = self.whole_file_hashes()
        with self.during_verify(touch_both), counting:
            self.assertTrue(self.verify()["written_spans_verified"])
        self.assertEqual(len(calls), 2, "the final recheck hashes source and output once")

    def test_receipt_check_still_refuses_new_bytes_while_verifying(self) -> None:
        for frozen in (False, True):
            with self.subTest(windows=frozen):
                self.setUp()
                with contextlib.ExitStack() as stack:
                    if frozen:
                        stack.enter_context(windows_change_time())
                    stack.enter_context(
                        self.during_verify(lambda: rewrite_same_size_keep_mtime(self.output, 128)))
                    with self.assertRaisesRegex(
                            self.tool.ProjectError,
                            "build files changed during receipt verification"):
                        self.verify()

    def test_receipt_check_still_refuses_a_moved_mtime_while_verifying(self) -> None:
        real = self.tool.file_snapshot
        pinned: list[bool] = []

        def touched(descriptor):
            row = real(descriptor)
            return [*row[:3], row[3] + 1, row[4]] if pinned else row

        calls, counting = self.whole_file_hashes()
        with self.during_verify(lambda: pinned.append(True)), counting, \
                mock.patch.object(self.tool, "file_snapshot", side_effect=touched), \
                self.assertRaisesRegex(self.tool.ProjectError,
                                       "build files changed during receipt verification"):
            self.verify()
        self.assertEqual(calls, [])


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
            touch_metadata(output)
            touch_metadata(root / "source.iso")
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

    def test_staged_equipment_art_survives_a_metadata_touch(self) -> None:
        session = SimpleNamespace()
        self.assertEqual(_verified_art(session, self.png, expected=self.digest), self.digest)
        touch_metadata(self.png)
        self.assertEqual(_verified_art(session, self.png, expected=self.digest), self.digest)
        time.sleep(0.02)
        self.png.write_bytes(b"different staged art")
        with self.assertRaisesRegex(
                ValidationError, "staged equipment PNG changed outside Mod Studio"):
            _verified_art(session, self.png, expected=self.digest)

    def test_staged_art_identity_cache_and_the_rewrite_it_cannot_see(self) -> None:
        """The beta 72 speed contract, and what it costs on Windows.

        test_b72_equipment_speed pins that an unchanged staged PNG is never
        re-read, which is what made a 600-item project open in under a second
        for the tester whose opens used to take hours. The cache key carries
        st_ctime, so a POSIX rewrite that restores the modification time still
        invalidates it. Windows reports a creation time, nothing in the key
        moves, and the cached digest answers for bytes that are not the same.
        Re-reading every staged PNG there would take back the fix that platform
        needed most, so Build reads and hashes every image it compiles instead:
        the disc matches the file on disk, and what is lost is the studio
        saying so first.

        Both answers are asserted, whichever one this platform gives, and
        neither is skipped. When beta 73 hardens this, the Windows half below
        starts failing and has to become the refusal.
        """

        session = SimpleNamespace()
        self.assertEqual(_verified_art(session, self.png, expected=self.digest), self.digest)
        before = stat_identity(self.png)
        rewrite_same_size_keep_mtime(self.png, 20)
        self.assertNotEqual(sha256(self.png.read_bytes()), self.digest)
        if stat_identity(self.png) != before:
            with self.assertRaisesRegex(
                    ValidationError, "staged equipment PNG changed outside Mod Studio"):
                _verified_art(session, self.png, expected=self.digest)
        else:
            self.assertEqual(
                _verified_art(session, self.png, expected=self.digest), self.digest,
                "this platform shows the rewrite, so the cache must refuse it")

        # And the Windows answer on every platform, including this one.
        self.setUp()
        with windows_change_time():
            session = SimpleNamespace()
            self.assertEqual(_verified_art(session, self.png, expected=self.digest), self.digest)
            rewrite_same_size_keep_mtime(self.png, 20)
            self.assertEqual(_verified_art(session, self.png, expected=self.digest), self.digest)
        self.assertNotEqual(sha256(self.png.read_bytes()), self.digest)

    def test_build_input_pin_ignores_change_time_and_refuses_new_bytes(self) -> None:
        tool = load_backend()
        resolved, payload, identity = tool.read_regular_bounded(
            self.png, 1024 * 1024, "project media input")
        pin = tool.InputPin(resolved, payload, len(payload), tool.digest(payload), identity)
        touch_metadata(self.png)
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
            touch_metadata(path)
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
                               side_effect=copy_then(touch_metadata)):
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
        touch_metadata(path)
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
        result = run(drifted, lambda: (touch_metadata(source), touch_metadata(authored)))
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


# --------------------------------------------------------------------------
# APF 2K8 Mod Studio: the same project open and fast save


class ApfProjectOpenChangeTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="b721-apf-open-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / "My APF 2K8 Mod.apf2k8mod"
        self.project.write_bytes(b"PK\x03\x04 synthetic APF project bytes " * 64)
        self.facade = ApfStudioFacade(cache_root=self.root / "cache")
        self.facade.source = SimpleNamespace(source_sha256="a" * 64)
        self.facade.catalog = object()  # type: ignore[assignment]
        self.active = mock.Mock()
        self.facade.session = self.active

    def load(self, during_load=None, identities=None):
        candidate = mock.Mock()

        def load_project(source):
            if during_load is not None:
                during_load(Path(source))
            return 2

        candidate.load_project.side_effect = load_project
        self.candidate = candidate
        with mock.patch("mod_editor.apf_studio.facade.ApfSession", return_value=candidate):
            if identities is None:
                return self.facade.load_project(self.project)
            with mock.patch("mod_editor.apf_studio.facade.project_target_identity",
                            side_effect=identities):
                return self.facade.load_project(self.project)

    def assert_opened(self, count: int) -> None:
        self.assertEqual(count, 2)
        self.assertIs(self.facade.session, self.candidate)
        self.active.close.assert_called_once()
        self.candidate.close.assert_not_called()

    def test_apf_open_accepts_a_metadata_touch_while_opening(self) -> None:
        opened = apf_project_target_identity(self.project)
        moved: list[bool] = []
        self.assert_opened(self.load(lambda path: moved.append(touch_metadata(path))))
        current = self.facade.last_project_identity
        if moved[0]:
            self.assertNotEqual(current.changed_ns, opened.changed_ns)
        self.assertEqual(dataclasses.replace(current, changed_ns=opened.changed_ns), opened)

    def test_apf_open_accepts_the_reported_windows_identity_pair(self) -> None:
        opened = apf_project_target_identity(self.project)
        before = dataclasses.replace(opened, changed_ns=REPORTED_BEFORE_CTIME_NS)
        after = dataclasses.replace(opened, changed_ns=REPORTED_AFTER_CTIME_NS)
        self.assert_opened(self.load(identities=(before, after)))
        self.assertEqual(self.facade.last_project_identity, after)

    def assert_refused_and_kept(self, during_load) -> None:
        with self.assertRaises(ApfProjectError) as caught:
            self.load(during_load)
        self.assertEqual(str(caught.exception),
            "The project changed outside Mod Studio while it was opening. "
            "The current workspace was kept; open the project again.")
        self.assertIs(self.facade.session, self.active)
        self.active.close.assert_not_called()
        self.candidate.close.assert_called_once()

    def test_apf_open_full_sha256_refuses_same_size_rewrite_restored_mtime(self) -> None:
        original = bytes(range(256)) * 8193
        for windows in (False, True):
            for offset in (0, 1024 * 1024 + 17, len(original) - 1):
                with self.subTest(windows=windows, offset=offset), contextlib.ExitStack() as stack:
                    if windows:
                        stack.enter_context(windows_change_time())
                    self.project.write_bytes(original)
                    self.facade.session = self.active
                    self.facade.last_project_identity = None
                    self.active.reset_mock()

                    def rewrite(path):
                        before = stat_identity(path)
                        rewrite_same_size_keep_mtime(path, offset)
                        after = stat_identity(path)
                        self.assertEqual(before[:4], after[:4])
                        if windows:
                            self.assertEqual(before, after)
                        self.assertNotEqual(sha256(path.read_bytes()), sha256(original))

                    self.assert_refused_and_kept(rewrite)
                    self.assertIsNone(self.facade.last_project_identity)

    def test_apf_open_still_refuses_new_bytes(self) -> None:
        def grow(path: Path) -> None:
            with path.open("ab") as stream:
                stream.write(b"!")

        self.assert_refused_and_kept(grow)

    def test_apf_open_still_refuses_a_moved_mtime(self) -> None:
        def touch(path: Path) -> None:
            info = os.stat(path)
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))

        self.assert_refused_and_kept(touch)

    def test_apf_open_still_refuses_a_replacement_file_with_identical_bytes(self) -> None:
        def swap(path: Path) -> None:
            info = os.stat(path)
            twin = path.with_name(path.name + ".twin")
            twin.write_bytes(path.read_bytes())
            os.utime(twin, ns=(info.st_atime_ns, info.st_mtime_ns))
            os.replace(twin, path)

        self.assert_refused_and_kept(swap)


class ApfFastSaveChangeTimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="b721-apf-save-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.target = self.root / "saved.apf2k8mod"
        self.target.write_bytes(b"APF project saved earlier")
        self.expected = apf_project_target_identity(self.target)
        self.pending = self.root / ".pending-save"
        self.pending.write_bytes(b"APF project saved now")

    def publish(self, expected_target) -> None:
        apf_publish_archive(self.pending, self.target, replace=True,
                            expected_target=expected_target)

    def test_apf_fast_save_accepts_a_change_time_only_difference(self) -> None:
        moved = touch_metadata(self.target)
        current = apf_project_target_identity(self.target)
        self.assertEqual(current.changed_ns != self.expected.changed_ns, moved)
        self.assertTrue(self.expected.matches_apart_from_change_time(current))
        self.publish(self.expected)
        self.assertEqual(self.target.read_bytes(), b"APF project saved now")

    def test_apf_fast_save_full_sha256_refuses_same_size_rewrite_restored_mtime(self) -> None:
        # Probe beyond the first hash block as well as both ends. A prefix or
        # sampled check must not masquerade as the full-file SHA-256 contract.
        original = bytes(range(256)) * 8193
        for windows in (False, True):
            for offset in (0, 1024 * 1024 + 17, len(original) - 1):
                with self.subTest(windows=windows, offset=offset), contextlib.ExitStack() as stack:
                    if windows:
                        stack.enter_context(windows_change_time())
                    self.target.write_bytes(original)
                    self.pending.write_bytes(b"pending project bytes")
                    expected = apf_project_target_identity(self.target)
                    before = stat_identity(self.target)
                    rewrite_same_size_keep_mtime(self.target, offset)
                    after = stat_identity(self.target)
                    self.assertEqual(before[:4], after[:4])
                    if windows:
                        self.assertEqual(before, after)
                    external = self.target.read_bytes()
                    self.assertNotEqual(sha256(external), sha256(original))
                    with self.assertRaises(ApfProjectError) as caught:
                        apf_publish_archive(self.pending, self.target, replace=True,
                                         expected_target=expected)
                    self.assertEqual(str(caught.exception),
                        "The active project changed outside Mod Studio. It was not "
                        "overwritten; use Save Project As or reopen it first.")
                    self.assertEqual(self.target.read_bytes(), external)
                    self.assertTrue(self.pending.is_file())

    def test_apf_fast_save_still_refuses_only_a_moved_mtime(self) -> None:
        original = self.target.read_bytes()
        info = self.target.stat()
        os.utime(self.target, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
        self.assertNotEqual(fd_stat(self.target).st_mtime_ns, info.st_mtime_ns)
        with self.assertRaisesRegex(ApfProjectError, "active project changed outside Mod Studio"):
            apf_publish_archive(self.pending, self.target, replace=True,
                             expected_target=self.expected)
        self.assertEqual(self.target.read_bytes(), original)

    def test_apf_fast_save_accepts_the_reported_windows_pair(self) -> None:
        drifted = dataclasses.replace(
            self.expected, changed_ns=self.expected.changed_ns + REPORTED_DELTA_NS)
        with mock.patch("mod_editor.apf_studio.project.project_target_identity",
                        return_value=drifted):
            self.publish(self.expected)
        self.assertEqual(self.target.read_bytes(), b"APF project saved now")

    def test_apf_fast_save_still_refuses_a_content_change(self) -> None:
        time.sleep(0.02)
        self.target.write_bytes(b"APF project saved elsewhere!")
        with self.assertRaisesRegex(ApfProjectError, "active project changed outside Mod Studio"):
            self.publish(self.expected)
        self.assertEqual(self.target.read_bytes(), b"APF project saved elsewhere!")

    def test_apf_fast_save_still_refuses_another_file_at_the_same_path(self) -> None:
        original = self.target.read_bytes()
        with windows_change_time():
            before = stat_identity(self.target)
            twin = self.target.with_suffix(".twin")
            twin.write_bytes(original)
            os.utime(twin, ns=(self.target.stat().st_atime_ns, before[3]))
            os.replace(twin, self.target)
            after = stat_identity(self.target)
            self.assertEqual(before[2:], after[2:])
            self.assertNotEqual(before[:2], after[:2])
            with self.assertRaisesRegex(ApfProjectError, "active project changed outside Mod Studio"):
                self.publish(self.expected)
        self.assertEqual(self.target.read_bytes(), original)



if __name__ == "__main__":
    unittest.main()
