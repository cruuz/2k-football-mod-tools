"""Windows-simulation tests for the caller-side cross-platform pin remediations.

These exercise the *caller* halves of the independent audit's findings 5, 7, 9 and
10 -- the parts that live outside ``platform_compat`` -- on the branch that only
runs on Windows.  Windows cannot run here, so the branch is simulated in-process:

* ``platform_compat.IS_WINDOWS`` is flipped on (and ``IS_LINUX``/``IS_MACOS`` off),
  so every ``DirHandle`` opens its Windows realpath-pin branch and the callers take
  their Windows code paths.
* ``platform_compat._windows_kernel_api`` -- the one seam the core built for exactly
  this -- is replaced with a ctypes-free fake that implements ``CreateFileW`` /
  ``GetFileInformationByHandle`` / ``FlushFileBuffers`` / ``CloseHandle`` against the
  real Linux filesystem, so the held Win32 directory handle and its
  ``(volume, file-index)`` identity re-verification are genuinely driven.  A swap of
  a pinned directory's inode therefore fails the re-verification exactly as it would
  on Windows.

Every real filesystem effect still happens on this host, so what the tests prove is
that the Windows *control flow* -- pinned writes, pinned enumeration, the publish
identity check and the durability warning -- fires when it must.  The POSIX
behaviour is asserted byte-for-byte unchanged by the existing per-file suites.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import os
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

from mod_editor.core import platform_compat
from mod_editor.core.platform_compat import DirectoryTransactionRefused
from mod_editor.core import nfl2k5_audio_source_fingerprints as fingerprints_mod
from mod_editor.core import nfl2k5_build_service as build_service_mod
from mod_editor.apf_studio import audio_replacement_pack as apf_arp
from mod_editor.studio import audio_bundle
from mod_editor.studio import audio_replacement_pack as studio_arp


class _FakeKernel32:
    """A ctypes-free stand-in for the four kernel32 entry points the core uses.

    It resolves every operation against the *real* filesystem this test host runs
    on, so a directory that is renamed or symlink-swapped between opening a handle
    and re-verifying it produces the identity mismatch (or reparse point) the
    Windows pin refuses -- the whole point of the simulation.
    """

    def __init__(self, *, flush_succeeds: bool = True) -> None:
        self._open: dict[int, tuple[str, bool]] = {}
        self._next_handle = 0x1000
        self._flush_succeeds = flush_succeeds

    # kernel32.CreateFileW
    def CreateFileW(  # noqa: N802 - mirrors the Win32 name
        self, path, access, share, security, disposition, flags, template
    ):
        nofollow = bool(flags & platform_compat._WIN_FILE_FLAG_OPEN_REPARSE_POINT)
        try:
            os.lstat(path) if nofollow else os.stat(path)
        except OSError:
            setter = getattr(ctypes, "set_last_error", None)
            if setter is not None:
                setter(2)  # ERROR_FILE_NOT_FOUND
            return platform_compat._win_invalid_handle()
        handle = self._next_handle
        self._next_handle += 1
        self._open[handle] = (os.fspath(path), nofollow)
        return handle

    # kernel32.GetFileInformationByHandle
    def GetFileInformationByHandle(self, handle, info_pointer):  # noqa: N802
        entry = self._open.get(handle)
        if entry is None:
            return 0
        path, nofollow = entry
        try:
            info = os.lstat(path) if nofollow else os.stat(path)
        except OSError:
            return 0
        attributes = 0
        if stat.S_ISDIR(info.st_mode):
            attributes |= platform_compat._WIN_FILE_ATTRIBUTE_DIRECTORY
        if nofollow and stat.S_ISLNK(info.st_mode):
            attributes |= platform_compat._WIN_FILE_ATTRIBUTE_REPARSE_POINT
        block = info_pointer.contents
        block.dwFileAttributes = attributes
        block.dwVolumeSerialNumber = info.st_dev & 0xFFFFFFFF
        block.nFileIndexHigh = (info.st_ino >> 32) & 0xFFFFFFFF
        block.nFileIndexLow = info.st_ino & 0xFFFFFFFF
        return 1

    # kernel32.FlushFileBuffers
    def FlushFileBuffers(self, handle):  # noqa: N802
        if handle not in self._open:
            return 0
        return 1 if self._flush_succeeds else 0

    # kernel32.CloseHandle
    def CloseHandle(self, handle):  # noqa: N802
        self._open.pop(handle, None)
        return 1


@contextlib.contextmanager
def simulated_windows(*, flush_succeeds: bool = True):
    """Run the enclosed block as if it were executing on Windows.

    Flips the platform constants and swaps the monkeypatchable
    ``_windows_kernel_api`` loader for :class:`_FakeKernel32`; every mutation is
    undone on exit so the rest of the process tests the real host again.
    ``flush_succeeds=False`` makes the fake ``FlushFileBuffers`` fail, standing in
    for a directory whose ACL denies this account the ``GENERIC_WRITE`` handle a
    real flush needs -- the case finding 9 must surface rather than discard.
    """

    saved_flags = (
        platform_compat.IS_WINDOWS,
        platform_compat.IS_LINUX,
        platform_compat.IS_MACOS,
    )
    saved_loader = platform_compat._windows_kernel_api
    saved_cache = platform_compat._windows_kernel_api_cache
    fake = platform_compat._WindowsKernelApi(
        kernel32=_FakeKernel32(flush_succeeds=flush_succeeds)
    )
    platform_compat.IS_WINDOWS = True
    platform_compat.IS_LINUX = False
    platform_compat.IS_MACOS = False
    platform_compat._windows_kernel_api_cache = None
    platform_compat._windows_kernel_api = lambda: fake
    try:
        yield fake
    finally:
        (
            platform_compat.IS_WINDOWS,
            platform_compat.IS_LINUX,
            platform_compat.IS_MACOS,
        ) = saved_flags
        platform_compat._windows_kernel_api = saved_loader
        platform_compat._windows_kernel_api_cache = saved_cache


def _swap_directory_inode(path: Path) -> None:
    """Replace ``path`` with a brand-new, empty directory of a *different* inode."""

    displaced = path.with_name(path.name + ".displaced")
    os.rename(path, displaced)
    os.mkdir(path, 0o700)


def _swap_directory_for_symlink(path: Path, target: Path) -> None:
    """Replace the directory ``path`` with a symlink to ``target``."""

    displaced = path.with_name(path.name + ".displaced")
    os.rename(path, displaced)
    os.symlink(target, path)


class SimulationSelfCheck(unittest.TestCase):
    """The fake Win32 layer must itself pin, and refuse a swap, before it can prove
    anything about the callers that ride on it."""

    def test_open_dir_handle_pins_and_reverifies_a_stable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "pinned"
            directory.mkdir()
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    self.assertEqual(
                        handle.mechanism,
                        platform_compat.DIRHANDLE_WINDOWS_REALPATH_PIN,
                    )
                    # An unchanged directory re-verifies without complaint.
                    self.assertTrue(stat.S_ISDIR(handle.fstat().st_mode))
                finally:
                    handle.close()

    def test_reverify_refuses_a_swapped_inode(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "pinned"
            directory.mkdir()
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    _swap_directory_inode(directory)
                    with self.assertRaises(DirectoryTransactionRefused) as caught:
                        handle.fstat()
                    self.assertEqual(caught.exception.errno, errno.ESTALE)
                finally:
                    handle.close()


class Finding7ScandirHandleTests(unittest.TestCase):
    """apf_studio ``_scandir_handle`` must enumerate through the pin and refuse a
    swapped parent on Windows, not scandir a bare realpath."""

    def _populate(self, directory: Path) -> set[str]:
        names = {"manifest.json", "README.txt", "payload"}
        (directory / "manifest.json").write_bytes(b"{}")
        (directory / "README.txt").write_bytes(b"readme")
        (directory / "payload").mkdir()
        return names

    def test_enumerates_through_the_pin_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "pack"
            directory.mkdir()
            expected = self._populate(directory)
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    with apf_arp._scandir_handle(handle) as iterator:
                        seen = {entry.name for entry in iterator}
                finally:
                    handle.close()
        self.assertEqual(seen, expected)

    def test_refuses_a_swapped_parent_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "pack"
            directory.mkdir()
            self._populate(directory)
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    _swap_directory_inode(directory)
                    # The re-verify inside DirHandle.scandir fires BEFORE the walk.
                    with self.assertRaises(DirectoryTransactionRefused):
                        with apf_arp._scandir_handle(handle):
                            pass
                finally:
                    handle.close()

    def test_refuses_a_symlinked_parent_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            directory = root / "pack"
            directory.mkdir()
            self._populate(directory)
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    _swap_directory_for_symlink(directory, elsewhere)
                    with self.assertRaises(DirectoryTransactionRefused):
                        with apf_arp._scandir_handle(handle):
                            pass
                finally:
                    handle.close()


class Finding5StagingPinTests(unittest.TestCase):
    """studio staging writes and enumeration must be bound to the pinned DirHandle
    on Windows -- a bare realpath was the weakening -- and fail closed on a swap."""

    def test_pinned_staging_root_fails_closed_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    with self.assertRaises(
                        studio_arp.AudioReplacementPackError
                    ):
                        studio_arp._pinned_staging_root(handle)
                finally:
                    handle.close()

    def test_write_new_at_writes_through_the_pin(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "stage"
            directory.mkdir(mode=0o700)
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    studio_arp._write_new_at(handle, "EDIT-AUDIO.md", b"payload")
                finally:
                    handle.close()
            written = directory / "EDIT-AUDIO.md"
            self.assertEqual(written.read_bytes(), b"payload")
            self.assertEqual(
                written.stat().st_mode & 0o777,
                platform_compat.private_file_mode(),
            )

    def test_write_new_at_refuses_a_swapped_parent(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "stage"
            directory.mkdir(mode=0o700)
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    studio_arp._write_new_at(handle, "first", b"a")
                    _swap_directory_inode(directory)
                    with self.assertRaises(DirectoryTransactionRefused):
                        studio_arp._write_new_at(handle, "second", b"b")
                finally:
                    handle.close()

    def test_folder_files_at_matches_the_posix_walk_then_refuses_a_swap(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name) / "stage"
            directory.mkdir(mode=0o700)
            (directory / "EDIT-AUDIO.md").write_bytes(b"g")
            (directory / "audio-replacement-pack.json").write_bytes(b"{}")
            (directory / "replacements").mkdir(mode=0o700)
            # The pinned Windows enumeration must reproduce the POSIX os.walk set.
            posix_files = set(studio_arp._folder_files(directory))
            with simulated_windows():
                handle = platform_compat.open_dir_handle(directory)
                try:
                    pinned_files = studio_arp._folder_files_at(handle)
                    self.assertEqual(pinned_files, posix_files)
                    self.assertEqual(
                        pinned_files,
                        {"EDIT-AUDIO.md", "audio-replacement-pack.json"},
                    )
                    _swap_directory_inode(directory)
                    with self.assertRaises(DirectoryTransactionRefused):
                        studio_arp._folder_files_at(handle)
                finally:
                    handle.close()

    def test_publish_zip_template_at_publishes_and_refuses_a_wav(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            parent = Path(name)
            with simulated_windows():
                handle = platform_compat.open_dir_handle(parent)
                try:
                    studio_arp._publish_zip_template_at(
                        handle,
                        ".stage.zip",
                        "template.zip",
                        guide=b"# guide",
                        manifest_payload=b"{}",
                        cue_map_payload=b"cue,map\n",
                    )
                finally:
                    handle.close()
            published = parent / "template.zip"
            self.assertTrue(published.is_file())
            # The temporary staging archive was removed through the handle.
            self.assertFalse((parent / ".stage.zip").exists())

            with zipfile.ZipFile(published, "r") as archive:
                names = archive.namelist()
            self.assertIn("EDIT-AUDIO.md", names)
            self.assertTrue(all(not n.casefold().endswith(".wav") for n in names))


class Finding5ExportTemplateWindowsTests(unittest.TestCase):
    """The full studio export_template must run to completion on Windows, producing
    a real retail-free template through the pinned staging path."""

    def _service(self, root: Path):
        # Imported lazily so the file still loads if the catalog fixture is absent.
        from mod_editor.core.nfl2k5_audio_catalog import Nfl2k5AudioService
        from mod_editor.studio.session import StudioSession
        from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture

        source = root / "source"
        source.mkdir()
        fixture = AudioFixture(source)
        catalog = fixture.catalog()
        audio = Nfl2k5AudioService(fixture.cache, catalog)
        session = StudioSession(
            fixture.cache, object(), root=root / "sessions", session_id="active"
        )
        session.attach_audio_service(audio)
        return studio_arp.AudioReplacementPackService(
            catalog, session, expected_editable_count=1
        )

    def test_export_template_folder_and_zip_on_windows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="win-export-") as name:
            root = Path(name)
            service = self._service(root)
            destination = root / "out"
            destination.mkdir()
            with simulated_windows():
                folder_result = service.export_template(
                    destination / "template", container="folder"
                )
                zip_result = service.export_template(
                    destination / "template.zip", container="zip"
                )
            # Folder template: real directory, the guide + manifest, zero WAVs.
            folder = Path(folder_result.path)
            self.assertTrue(folder.is_dir())
            self.assertTrue((folder / "EDIT-AUDIO.md").is_file())
            self.assertTrue((folder / "audio-replacement-pack.json").is_file())
            self.assertEqual(
                [p for p in folder.rglob("*") if p.suffix.casefold() == ".wav"],
                [],
            )
            # ZIP template: a published archive with no WAV member.

            with zipfile.ZipFile(Path(zip_result.path), "r") as archive:
                names = archive.namelist()
            self.assertIn("audio-replacement-pack.json", names)
            self.assertTrue(all(not n.casefold().endswith(".wav") for n in names))


class Finding10AudioBundleIdentityTests(unittest.TestCase):
    """The audio-bundle publisher must prove, on Windows, that the inode it hard-links
    is the archive it wrote -- not a reparse point swapped in after the flush."""

    def test_exclusive_publish_accepts_the_written_identity(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "complete.zip"
            source.write_bytes(b"zip-bytes")
            destination = root / "bundle.zip"
            with simulated_windows():
                identity = audio_bundle._regular_file_identity(source)
                published = audio_bundle._exclusive_publish(
                    source, destination, expected_identity=identity
                )
            self.assertTrue(Path(published).is_file())
            self.assertEqual(destination.read_bytes(), b"zip-bytes")

    def test_exclusive_publish_refuses_a_symlink_swapped_after_the_flush(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "complete.zip"
            source.write_bytes(b"honest-bytes")
            attacker = root / "attacker.zip"
            attacker.write_bytes(b"attacker-bytes")
            destination = root / "bundle.zip"
            with simulated_windows():
                identity = audio_bundle._regular_file_identity(source)
                # The archive is swapped for a symlink to attacker-controlled bytes
                # between the flush and the publish.
                os.unlink(source)
                os.symlink(attacker, source)
                with self.assertRaises(audio_bundle.AudioBundleError):
                    audio_bundle._exclusive_publish(
                        source, destination, expected_identity=identity
                    )
            self.assertFalse(destination.exists())

    def test_exclusive_publish_refuses_a_different_inode(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "complete.zip"
            source.write_bytes(b"honest-bytes")
            # A separately created file has its own inode; renaming it onto the
            # source name guarantees a different (st_dev, st_ino) than the archive
            # whose identity we captured -- unlink+recreate can reuse the inode.
            replacement = root / "replacement.zip"
            replacement.write_bytes(b"replaced-bytes")
            destination = root / "bundle.zip"
            with simulated_windows():
                identity = audio_bundle._regular_file_identity(source)
                os.replace(replacement, source)
                with self.assertRaises(audio_bundle.AudioBundleError):
                    audio_bundle._exclusive_publish(
                        source, destination, expected_identity=identity
                    )
            self.assertFalse(destination.exists())

    def test_export_audio_bundle_runs_and_publishes_on_windows(self) -> None:
        from mod_editor.studio.audio_bundle import (
            AudioBundleRow,
            export_audio_bundle,
        )

        row = AudioBundleRow(
            stable_id="nfl2k5.audio.win.001",
            display_name="Win fixture",
            suggested_basename="clip.wav",
            extension=".wav",
            predicted_payload_bytes=len(b"payload"),
            content_origin="user_replacement",
            metadata={"scope": "standalone", "family_id": "music"},
        )

        def writer(_row: AudioBundleRow, target: Path) -> Path:
            target.write_bytes(b"payload")
            return target.resolve()

        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / "bundle.zip"
            with simulated_windows():
                published = export_audio_bundle(
                    (row,),
                    destination,
                    bundle_name="Windows bundle",
                    payload_writer=writer,
                )
            self.assertTrue(Path(published).is_file())


class Finding9DurabilitySignalTests(unittest.TestCase):
    """Publishers must consume the directory-flush bool: True is committed, a Windows
    False is surfaced as a warning, never discarded as if committed."""

    def test_commit_directory_is_silent_and_true_on_this_posix_host(self) -> None:
        for module in (fingerprints_mod, apf_arp):
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as name:
                    handle = platform_compat.open_dir_handle(Path(name))
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error")
                            self.assertTrue(module._commit_directory(handle))
                    finally:
                        handle.close()

    def test_commit_directory_warns_when_the_windows_flush_fails(self) -> None:
        for module in (fingerprints_mod, apf_arp):
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as name:
                    directory = Path(name)
                    with simulated_windows(flush_succeeds=False):
                        handle = platform_compat.open_dir_handle(directory)
                        try:
                            with self.assertWarns(RuntimeWarning) as caught:
                                durable = module._commit_directory(handle)
                        finally:
                            handle.close()
                    self.assertFalse(durable)
                    self.assertIn(
                        "could not be flushed", str(caught.warning)
                    )

    def test_commit_directory_reports_true_when_the_windows_flush_succeeds(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as name:
            with simulated_windows(flush_succeeds=True):
                handle = platform_compat.open_dir_handle(Path(name))
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error")
                        self.assertTrue(
                            fingerprints_mod._commit_directory(handle)
                        )
                finally:
                    handle.close()

    def test_build_service_fsync_directory_propagates_the_bool(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            # POSIX host: a real directory flush, always committed.
            self.assertTrue(build_service_mod._fsync_directory(directory))
            # Windows with a denied write handle: the False is returned, not
            # discarded, so the commit path can surface the missing durability.
            with simulated_windows(flush_succeeds=False):
                self.assertFalse(build_service_mod._fsync_directory(directory))
            # Windows with a usable write handle: genuinely committed.
            with simulated_windows(flush_succeeds=True):
                self.assertTrue(build_service_mod._fsync_directory(directory))


if __name__ == "__main__":
    unittest.main()
