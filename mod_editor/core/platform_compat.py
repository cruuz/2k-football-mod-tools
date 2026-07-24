"""Single, typed home for the editor's OS-specific hardening primitives.

The shipped editor was written against three Linux-only kernel features: btrfs/
XFS reflink cloning (``FICLONE``), ``memfd`` write-seals, and advisory
``flock``.  Two of those are absent on macOS and all three are absent on
Windows, and every call site imported :mod:`fcntl` at module scope -- which does
not exist on Windows, so the modules failed to even import there.

This module concentrates every such platform difference behind a small, typed
API so the rest of the codebase never imports :mod:`fcntl` or :mod:`msvcrt`
directly.  Those two modules are imported *lazily* here (inside the functions
that need them, guarded by a platform check) precisely because an unconditional
``import fcntl`` is the portability bug we are removing.

The module is deliberately dependency-free (standard library only) so it can be
a leaf imported by any core module without risking an import cycle.

Fail-closed policy: where a Linux hardening primitive is unavailable we degrade
to the strongest available equivalent and make the degradation observable --
never a silent skip.  Concretely, :func:`seal_readonly` still guarantees the
staged bytes are immutable-in-practice by making the file read-only and
returning their hash so the caller can re-verify; :func:`exclusive_nonblocking_lock`
still fails immediately (never blocks) and still refuses when the lock is held;
and :func:`try_reflink` reports ``False`` so the caller uses its verified plain
copy instead of silently skipping the copy.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
import sys
from types import ModuleType


IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# ``FICLONE`` from <linux/fs.h>: _IOW(0x94, 9, int).  Only meaningful on Linux.
_FICLONE = 0x40049409
_READONLY_MODE = 0o400
_HASH_BLOCK = 1 << 20

# Reflink refusals that mean "this pair cannot be cloned" rather than a real I/O
# fault; the caller must fall through to a verified byte copy on any of these.
_REFLINK_UNSUPPORTED_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOTTY", None),
        getattr(errno, "EXDEV", None),
        getattr(errno, "EINVAL", None),
        getattr(errno, "ENOSYS", None),
    )
    if value is not None
)

# ``msvcrt.locking`` reports contention through these; normalise them to
# :class:`BlockingIOError` so callers can treat every platform identically.
_LOCK_CONTENTION_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "EACCES", None),
        getattr(errno, "EAGAIN", None),
        getattr(errno, "EWOULDBLOCK", None),
        getattr(errno, "EDEADLK", None),
        getattr(errno, "EDEADLOCK", None),
    )
    if value is not None
)


class SealIntegrityError(RuntimeError):
    """A staged descriptor could not be made verifiably immutable."""


@dataclass(frozen=True)
class SealResult:
    """Outcome of :func:`seal_readonly`.

    ``sealed`` is ``True`` only when kernel write-seals were applied (a Linux
    ``memfd``); on other platforms the file is made read-only instead and
    ``read_only`` reports that.  ``sha256`` is the hex digest of the staged
    bytes as read back *after* the descriptor was hardened, so the caller can
    fail closed if it does not match the bytes it intended to stage.
    """

    sealed: bool
    read_only: bool
    mechanism: str
    sha256: str


def _optional_fcntl() -> ModuleType | None:
    """Return :mod:`fcntl` if present (POSIX), else ``None``; never raises."""

    try:
        import fcntl
    except ImportError:
        return None
    return fcntl


def _require_fcntl() -> ModuleType:
    """Return :mod:`fcntl` or fail closed on a platform that lacks it."""

    fcntl = _optional_fcntl()
    if fcntl is None:
        raise RuntimeError(
            "This POSIX operation requires the fcntl module, which is absent on "
            "this platform"
        )
    return fcntl


def _require_msvcrt() -> ModuleType:
    """Return :mod:`msvcrt` or fail closed on a platform that lacks it."""

    try:
        import msvcrt
    except ImportError as exc:
        raise RuntimeError(
            "This Windows operation requires the msvcrt module, which is absent "
            "on this platform"
        ) from exc
    return msvcrt


def supports_reflink() -> bool:
    """Whether a copy-on-write reflink clone can even be *attempted* here.

    A ``True`` result does not promise the destination filesystem supports
    reflinks -- only :func:`try_reflink` learns that, by attempting the clone.
    """

    if not IS_LINUX:
        return False
    fcntl = _optional_fcntl()
    return fcntl is not None and hasattr(fcntl, "ioctl")


def supports_sealed_memfd() -> bool:
    """Whether an anonymous, write-sealed ``memfd`` is available (Linux only)."""

    if not IS_LINUX:
        return False
    if not all(
        hasattr(os, name)
        for name in ("memfd_create", "MFD_CLOEXEC", "MFD_ALLOW_SEALING")
    ):
        return False
    fcntl = _optional_fcntl()
    if fcntl is None:
        return False
    return all(
        hasattr(fcntl, name)
        for name in (
            "F_ADD_SEALS",
            "F_GET_SEALS",
            "F_SEAL_GROW",
            "F_SEAL_SEAL",
            "F_SEAL_SHRINK",
            "F_SEAL_WRITE",
        )
    )


def try_reflink(destination_fd: int, source_fd: int) -> bool:
    """Attempt a copy-on-write clone of ``source_fd`` into ``destination_fd``.

    Returns ``True`` when the whole file was cloned and ``False`` when reflinks
    are unavailable on this platform or filesystem -- in which case the caller
    must perform its own verified byte copy.  A genuine I/O error (an errno that
    does not merely mean "unsupported") is re-raised so it is never mistaken for
    a successful or a skipped copy.
    """

    if not IS_LINUX:
        return False
    fcntl = _optional_fcntl()
    if fcntl is None or not hasattr(fcntl, "ioctl"):
        return False
    try:
        fcntl.ioctl(destination_fd, _FICLONE, source_fd)
    except OSError as exc:
        if exc.errno in _REFLINK_UNSUPPORTED_ERRNOS:
            return False
        raise
    return True


def exclusive_nonblocking_lock(fd: int) -> None:
    """Take an exclusive advisory lock on ``fd`` without ever blocking.

    Raises :class:`BlockingIOError` if another holder already owns the lock, on
    every platform.  On POSIX this is ``flock(LOCK_EX | LOCK_NB)``; on Windows
    it is ``msvcrt.locking(LK_NBLCK, 1)`` on the first byte, whose contention
    error is normalised to :class:`BlockingIOError` so callers stay identical.
    """

    if IS_WINDOWS:
        msvcrt = _require_msvcrt()
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in _LOCK_CONTENTION_ERRNOS:
                raise BlockingIOError(
                    exc.errno or errno.EACCES,
                    "advisory lock is held by another holder",
                ) from exc
            raise
        return
    fcntl = _require_fcntl()
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def release_lock(fd: int) -> None:
    """Release the advisory lock taken by :func:`exclusive_nonblocking_lock`."""

    if IS_WINDOWS:
        msvcrt = _require_msvcrt()
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    fcntl = _require_fcntl()
    fcntl.flock(fd, fcntl.LOCK_UN)


def pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read that never moves the descriptor offset.

    Uses :func:`os.pread` where available (POSIX) and falls back to a
    seek/read/restore sequence on Windows, returning the same bytes for the same
    ``(fd, count, offset)``.
    """

    preader = getattr(os, "pread", None)
    if preader is not None:
        return preader(fd, count, offset)
    return _pread_via_seek(fd, count, offset)


def _pread_via_seek(fd: int, count: int, offset: int) -> bytes:
    """Windows fallback for :func:`os.pread`; matches its bytes and offset."""

    if count <= 0:
        return b""
    saved = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.lseek(fd, saved, os.SEEK_SET)


def fchmod_readonly(fd: int, path: str | None) -> None:
    """Make the backing file owner-read-only (mode ``0o400``).

    Uses :func:`os.fchmod` where available (POSIX) and falls back to
    :func:`os.chmod` on ``path`` on Windows, where ``fchmod`` is absent.  The
    ``path`` must be supplied on platforms without ``fchmod``.
    """

    fchmod = getattr(os, "fchmod", None)
    if fchmod is not None:
        fchmod(fd, _READONLY_MODE)
        return
    if path is None:
        raise RuntimeError(
            "Cannot make a descriptor read-only without a path on a platform "
            "that lacks os.fchmod"
        )
    os.chmod(path, _READONLY_MODE)


def fchmod(fd: int, mode: int, path: str | None = None) -> None:
    """Set the mode bits on a descriptor's backing file, portably.

    Uses :func:`os.fchmod` on POSIX.  On Windows -- which has no ``os.fchmod``
    and honours only the owner-write (read-only) bit -- it falls back to
    :func:`os.chmod` on ``path`` when one is supplied; the remaining POSIX bits
    are inert there.  When no path is available on such a platform this is a
    deliberate no-op: these modes (e.g. ``0o644`` / ``0o600`` set on a freshly
    created, private staging file) are defensive hardening, not an integrity
    seal.  The fail-closed seal is :func:`seal_readonly`, which is handled
    separately and is never silently skipped, so degrading these cosmetic perm
    sets to a no-op on Windows does not weaken any security guarantee.
    """

    fchmod_fn = getattr(os, "fchmod", None)
    if fchmod_fn is not None:
        fchmod_fn(fd, mode)
        return
    if path is not None:
        os.chmod(path, mode)


def _hash_fd(fd: int) -> str:
    """SHA-256 of a descriptor's full contents, read positionally."""

    size = os.fstat(fd).st_size
    digest = hashlib.sha256()
    cursor = 0
    while cursor < size:
        chunk = pread(fd, min(_HASH_BLOCK, size - cursor), cursor)
        if not chunk:
            break
        digest.update(chunk)
        cursor += len(chunk)
    return digest.hexdigest()


def seal_readonly(fd: int, path: str | None) -> SealResult:
    """Make a staged descriptor immutable, or as close to it as the OS allows.

    On Linux the descriptor is expected to be a sealable ``memfd``: it is made
    read-only and given the full set of write-seals (``GROW | SEAL | SHRINK |
    WRITE``), which the kernel enforces even against the owning process; the
    seals are then read back and verified, and a failure raises
    :class:`SealIntegrityError` (fail closed).

    On platforms without ``memfd`` seals the file is made read-only and its
    post-write bytes are hashed and returned in :attr:`SealResult.sha256`.  The
    caller MUST compare that digest against the bytes it intended to stage --
    that hash re-verification is the portable stand-in for a kernel seal, and it
    is why the degradation is safe rather than a dropped check.
    """

    fchmod_readonly(fd, path)
    if supports_sealed_memfd():
        fcntl = _require_fcntl()
        seals = (
            fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_WRITE
        )
        try:
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        except OSError as exc:
            raise SealIntegrityError(
                "Kernel write seals could not be applied to the staged descriptor"
            ) from exc
        if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & seals != seals:
            raise SealIntegrityError(
                "Kernel write seals did not stick to the staged descriptor"
            )
        return SealResult(
            sealed=True,
            read_only=True,
            mechanism="linux-memfd-write-seals",
            sha256=_hash_fd(fd),
        )
    return SealResult(
        sealed=False,
        read_only=True,
        mechanism="chmod-readonly-verified-hash",
        sha256=_hash_fd(fd),
    )


__all__ = [
    "IS_LINUX",
    "IS_MACOS",
    "IS_WINDOWS",
    "SealIntegrityError",
    "SealResult",
    "exclusive_nonblocking_lock",
    "fchmod",
    "fchmod_readonly",
    "pread",
    "release_lock",
    "seal_readonly",
    "supports_reflink",
    "supports_sealed_memfd",
    "try_reflink",
]
