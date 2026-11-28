"""Read-only open-file probes and bounded, transactional image copying.

POSIX probes are a snapshot, not a lock against a noncooperating future opener.
Linux inspects visible processes owned by the current user; macOS uses lsof.
Windows asks the kernel for a temporary read handle with no sharing.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from .errors import ValidationError
from .platform_compat import absolute_path, io_path, long_path, paths_alias, publish_no_replace, validate_output_path


def _busy(path: Path, detail: str = "") -> ValidationError:
    return ValidationError(
        f"The disc image is open in another process{detail}: {path}. "
        "Eject the disc and close both emulators, then retry. "
        "Mod Studio did not change the image."
    )


def _windows_probe(path: Path) -> None:
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    handle = create(long_path(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        code = ctypes.get_last_error()
        if code in (32, 33):
            raise _busy(path)
        raise ValidationError(f"Could not check whether the disc is in use (Windows error {code}): {path}")
    close(handle)


def _linux_probe(path: Path, identity: os.stat_result) -> None:
    proc = Path("/proc")
    if not proc.is_dir():
        raise ValidationError("Cannot check open disc handles: /proc is unavailable. Close emulators and use a new output path.")
    for process in proc.iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            owner = getattr(os, "getuid", None)  # POSIX only; this probe never runs on Windows
            if owner is not None and process.stat().st_uid != owner():
                continue
            for fd in (process / "fd").iterdir():
                try:
                    info = fd.stat()
                except FileNotFoundError:
                    continue
                if (info.st_dev, info.st_ino) == (identity.st_dev, identity.st_ino):
                    raise _busy(path, f" (PID {process.name})")
            # A process can close its fd and retain a mapped image.
            with (process / "maps").open() as stream:
                for line in stream:
                    parts = line.split(None, 5)
                    if len(parts) < 5 or not parts[4].isdigit():
                        continue
                    major, minor = (int(value, 16) for value in parts[3].split(":"))
                    if (os.makedev(major, minor), int(parts[4])) == (identity.st_dev, identity.st_ino):
                        raise _busy(path, f" (PID {process.name}, mapped)")
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            # Sandboxed same-user processes (browser renderers, flatpaks) hide their
            # descriptors; they are skipped rather than blocking every build. Linux
            # visibility is a documented limitation, not a mandatory-lock claim.
            continue


def assert_image_available(image: Path) -> None:
    """Refuse an observed reader/mapping; never write or eject the image."""
    path = io_path(absolute_path(image))
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValidationError(f"Choose a regular disc image, not a link: {path}")
    if sys.platform == "win32":
        _windows_probe(path)
    elif sys.platform.startswith("linux"):
        _linux_probe(path, info)
    elif sys.platform == "darwin":
        executable = shutil.which("lsof")
        if not executable:
            raise ValidationError("Cannot check open disc handles because lsof is unavailable.")
        try:
            result = subprocess.run([executable, "-F", "p", "--", str(path)],
                                    capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValidationError(f"Could not check open disc handles: {exc}") from exc
        pids = [line[1:] for line in result.stdout.splitlines() if line.startswith("p")]
        if any(pid != str(os.getpid()) for pid in pids):
            raise _busy(path)
        if result.returncode not in (0, 1) or result.stderr.strip():
            raise ValidationError("Could not completely inspect open disc handles with lsof.")
    else:
        raise ValidationError("Open disc handle checking is unavailable on this platform.")


def check_image_destination(target: Path, *, overwrite: bool = False):
    """Capture an available destination before expensive work starts."""
    validate_output_path(target)
    target = io_path(target)
    if target.is_symlink():
        raise ValidationError("The output image must not be a symbolic link.")
    if not target.exists():
        return None
    assert_image_available(target)
    if not overwrite:
        raise FileExistsError(target)
    return target.stat()


#: beta 77 (E2): a freshly written 6 GB image is exactly what antivirus, the search indexer and cloud-sync clients open
#: for a while, and Windows then refuses the rename with "being used by another process" (WinError 32) or "Access is
#: denied" (WinError 5). Before this the build failed on the spot, after every other step had finished. About a minute
#: of patience, the same one the compaction swap uses; a different error (a destination that exists, a read-only
#: folder) is never retried.
PUBLISH_HELD_ATTEMPTS = 240
PUBLISH_HELD_WAIT_SECONDS = 0.25
_WINDOWS_HELD = frozenset({5, 32})


def _held_by_another_program(exc: OSError) -> bool:
    """True only for the refusals Windows itself gives for a file another program has open."""
    return isinstance(exc, PermissionError) and getattr(exc, "winerror", None) in _WINDOWS_HELD


def _publish_when_released(publish, target: Path) -> None:
    for attempt in range(PUBLISH_HELD_ATTEMPTS):
        try:
            publish()
            return
        except PermissionError as exc:
            if not _held_by_another_program(exc):
                raise
            if attempt == PUBLISH_HELD_ATTEMPTS - 1:
                raise ValidationError(
                    f"Windows is still holding the finished disc open, so it could not be saved as {target.name}. "
                    "Antivirus, the search indexer, an emulator or a cloud-sync program usually lets go within a "
                    "minute: pause it for this folder or choose another output folder, then make the disc again. "
                    "Nothing was published.") from exc
            time.sleep(PUBLISH_HELD_WAIT_SECONDS)


def _file_state(info):
    return None if info is None else [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def receipt_states(target, suffixes):
    """Snapshot the paths that a completed build will publish or retire."""
    states = {}
    for suffix in suffixes:
        path = io_path(str(target) + suffix)
        try:
            info = path.lstat()
        except FileNotFoundError:
            states[suffix] = None
            continue
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValidationError(f"The output receipt must be a regular file: {path}. Choose another output filename.")
        states[suffix] = _file_state(info)
    return states


@contextmanager
def _publication_lock(target):
    from . import platform_compat
    from .nfl2k5_source_cache import default_cache_root
    key = hashlib.sha256(os.fsencode(os.path.normcase(os.path.realpath(target)))).hexdigest()
    locks = default_cache_root() / "publication-locks"
    locks.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (locks / key).open("a+b") as lock:
        try:
            platform_compat.exclusive_nonblocking_lock(lock.fileno())
        except BlockingIOError as exc:
            raise ValidationError("Another build is publishing this destination. Choose a different output filename.") from exc
        try:
            yield target.parent / (".2k5-publish-" + key[:24])
        finally:
            platform_compat.release_lock(lock.fileno())


def _finish_publication(target, journal, suffixes):
    """Reconcile a failed or interrupted commit. The disc rename occurs after every sidecar."""
    if not journal.exists():
        return
    if journal.is_symlink() or not journal.is_dir():
        raise ValidationError(f"A publication recovery path is occupied: {journal}")
    manifest = journal / "commit.json"
    if not manifest.exists():
        # No receipt can have moved before the journal is finalized.
        if {f.name for f in journal.iterdir()} <= {"commit.tmp"}:
            (journal / "commit.tmp").unlink(missing_ok=True)
            journal.rmdir()
            return
        raise ValidationError(f"Unrecognized files in publication recovery folder: {journal}")
    if manifest.is_symlink() or manifest.stat().st_size > 16384:
        raise ValidationError(f"Unreadable publication recovery record: {manifest}")
    doc = json.loads(manifest.read_bytes())
    if set(doc["old"]) != set(suffixes) or set(doc["new"]) != set(suffixes) or doc["target"] != target.name:
        raise ValidationError(f"The publication recovery record does not belong to {target.name}.")
    committed = receipt_states(target, ("",))[""] == doc["disc_after"]
    states = receipt_states(target, suffixes)
    for number, suffix in enumerate(sorted(suffixes)):
        backup = journal / str(number)
        old, new, current = doc["old"][suffix], doc["new"][suffix], states[suffix]
        if not committed:
            dest = io_path(str(target) + suffix)
            if current not in (None, old, new):
                raise ValidationError(f"The output receipt changed during recovery. Your previous receipt is in {journal}.")
            if backup.exists():
                if receipt_states(backup, ("",))[""] != old:
                    raise ValidationError(f"Previous receipt changed in {journal}.")
                _publish_when_released(lambda: os.replace(backup, dest), dest)
            elif old is None and current is not None:
                _publish_when_released(dest.unlink, dest)
            elif current != old:
                raise ValidationError(f"Cannot verify the previous receipt for {target.name}. Recovery files are in {journal}.")
        else:
            backup.unlink(missing_ok=True)
    manifest.unlink()
    journal.rmdir()


#: Every private staging folder Studio makes beside an output carries this marker, opened and locked for as long as the
#: folder is in use. A folder with an unlocked marker was left by a Studio that stopped (a crash, a kill or a power cut)
#: and is removed by the next operation in the same output folder. Nothing without the exact marker is ever touched.
STAGING_MARKER = ".2k5-studio-staging"
STAGING_MARKER_TEXT = (b"2K5 Mod Studio private staging folder. Studio removes it when no Studio is using it.\n")
#: A folder that holds a user's previous file (the save writers' rollback copy) is renamed to this marker instead and
#: is never removed automatically: it may be the only copy left after an interrupted replacement.
RECOVERY_MARKER = ".2k5-studio-recovery"
#: The file name the save writers use for the previous output they may restore. A stale folder holding one is kept.
ROLLBACK_NAME = "original"


class StudioStaging:
    """One marked staging folder. Set ``keep`` (with a reason) to leave it on disk for the user."""

    def __init__(self, path: Path):
        self.path = path
        self.keep = False


def _stale_staging_folder(entry: Path) -> bool:
    try:
        info = entry.lstat()
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    marker = entry / STAGING_MARKER
    try:
        marker_info = marker.lstat()
        if not stat.S_ISREG(marker_info.st_mode) or marker_info.st_size != len(STAGING_MARKER_TEXT):
            return False
        if any(child.name == ROLLBACK_NAME for child in entry.iterdir()):
            return False
        from . import platform_compat
        with open(marker, "r+b") as handle:
            try:
                platform_compat.exclusive_nonblocking_lock(handle.fileno())
            except BlockingIOError:
                return False            # a running Studio owns it
            try:
                return handle.read(len(STAGING_MARKER_TEXT) + 1) == STAGING_MARKER_TEXT
            finally:
                platform_compat.release_lock(handle.fileno())
    except OSError:
        return False


def recover_studio_staging(parent, prefix: str) -> list[str]:
    """Remove stale marked staging folders named ``prefix*`` directly inside ``parent``. Returns their names."""
    removed = []
    try:
        entries = sorted(Path(parent).iterdir())
    except OSError:
        return removed
    for entry in entries:
        if not entry.name.startswith(prefix) or not _stale_staging_folder(entry):
            continue
        try:
            _remove_staging(entry)
        except OSError:
            continue
        removed.append(entry.name)
    return removed


def _remove_staging(entry: Path) -> None:
    """Remove a staging folder's contents, then its marker, then the folder: a partial removal is retried later."""
    for child in entry.iterdir():
        if child.name == STAGING_MARKER:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    (entry / STAGING_MARKER).unlink(missing_ok=True)
    entry.rmdir()


@contextmanager
def studio_staging(parent, prefix: str):
    """A private, marked staging folder on the output's own volume (so the final rename never crosses volumes).

    Stale folders with the same prefix are recovered first. The folder is removed afterwards unless ``keep`` is set,
    in which case it is marked for the user and never removed automatically."""
    from . import platform_compat
    parent = Path(parent)
    recover_studio_staging(parent, prefix)
    stage = StudioStaging(Path(tempfile.mkdtemp(prefix=prefix, dir=parent)))
    marker = stage.path / STAGING_MARKER
    handle = None
    locked = False
    try:
        handle = open(marker, "xb")
        handle.write(STAGING_MARKER_TEXT)
        handle.flush()
        try:
            platform_compat.exclusive_nonblocking_lock(handle.fileno())
            locked = True
        except OSError:
            # Some network volumes have no advisory locks. Recovery cannot lock there either, so it never removes this.
            pass
        yield stage
    finally:
        if handle is not None:
            if locked:
                try:
                    platform_compat.release_lock(handle.fileno())
                except OSError:
                    pass
            handle.close()
        if stage.keep:
            try:
                os.replace(marker, stage.path / RECOVERY_MARKER)
            except OSError:
                pass
        else:
            try:
                _remove_staging(stage.path)
            except OSError:
                pass    # Windows can hold a just-closed file for a moment; the unlocked marker lets the next run finish


def recover_image_publication(target, suffixes):
    """Recover an interrupted build before taking a fresh snapshot of the destination."""
    with _publication_lock(target) as journal:
        _finish_publication(target, journal, suffixes)


def publish_image_with_receipts(staging, target, previous, previous_receipts):
    """Commit the verified files together. Keep rollback data until the new disc has its final name."""
    from . import platform_compat
    with _publication_lock(target) as journal:
        _finish_publication(target, journal, previous_receipts)
        if receipt_states(target, previous_receipts) != previous_receipts:
            raise ValidationError("The output receipts changed while building. Choose another output filename.")
        staged = receipt_states(staging, previous_receipts)
        if not any(previous_receipts.values()) and not any(staged.values()):
            publish_image(staging, target, previous)
            return
        doc = dict(target=target.name, disc_after=_file_state(staging.stat()), old=previous_receipts, new=staged)
        journal.mkdir(mode=0o700)
        try:
            draft = journal / "commit.tmp"
            with draft.open("xb") as writer:
                writer.write(json.dumps(doc).encode())
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(draft, journal / "commit.json")
            platform_compat.fsync_directory(journal)
            platform_compat.fsync_directory(target.parent)
            for number, suffix in enumerate(sorted(previous_receipts)):
                dest = io_path(str(target) + suffix)
                if previous_receipts[suffix] is not None:
                    _publish_when_released(lambda: os.replace(dest, journal / str(number)), dest)
                if staged[suffix] is not None:
                    new = io_path(str(staging) + suffix)
                    _publish_when_released(lambda: publish_no_replace(new, dest), dest)
            platform_compat.fsync_directory(journal)
            platform_compat.fsync_directory(target.parent)
            publish_image(staging, target, previous)
        except BaseException:
            _finish_publication(target, journal, previous_receipts)
            raise
        # An OS lock on a backup may delay housekeeping. The committed image and its receipts are already usable.
        try:
            _finish_publication(target, journal, previous_receipts)
        except OSError:
            pass


def publish_image(staging: Path, target: Path, previous) -> None:
    """Publish completed bytes; refuse a newly appeared, changed or open target."""
    staging, target = io_path(staging), io_path(target)
    if previous is None:
        _publish_when_released(lambda: publish_no_replace(staging, target), target)
        return
    assert_image_available(target)
    now = target.stat()
    if (now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns) != (
            previous.st_dev, previous.st_ino, previous.st_size, previous.st_mtime_ns):
        raise ValidationError("The output image changed during copying; retry with a new output path.")
    _publish_when_released(lambda: os.replace(long_path(staging), long_path(target)), target)


def copy_image(source: Path, target: Path, *, overwrite: bool = False) -> None:
    """Stream a new image, then publish after rechecking the old destination.

    All readers/writers close before publication. Failure removes only our temp.
    Source may be open for reading; an existing destination may not be in use.
    """
    validate_output_path(target)
    source = io_path(absolute_path(source))
    source.stat()
    requested = io_path(absolute_path(target))
    if requested.is_symlink():
        raise ValidationError("The output image must not be a symbolic link.")
    target = requested
    if paths_alias(target, source):
        raise ValidationError("Choose an output image separate from the source.")
    previous = check_image_destination(target, overwrite=overwrite)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".image-", suffix=".copying", dir=target.parent)
    temporary = io_path(name)
    try:
        with os.fdopen(fd, "wb") as writer, source.open("rb") as reader:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        publish_image(temporary, target, previous)
    finally:
        temporary.unlink(missing_ok=True)
