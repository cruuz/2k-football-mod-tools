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

A fourth difference is *ownership*, and it is the sharpest example of the
fail-closed policy below.  Every private-cache guard in this product asserts
``info.st_uid == os.getuid()`` so a staging directory or an inventory planted by
*another* user can never be consumed.  Windows has neither :func:`os.getuid` nor
a meaningful ``st_uid`` -- Python reports ``0`` there for every file -- so
porting that comparison naively would silently turn a real security check into
one that always passes.  :func:`describe_ownership` answers the same question
with each platform's own ownership model instead: on POSIX the uid comparison,
unchanged; on Windows a comparison of the file's *owner SID* against the calling
process token's user SID, which is the exact Win32 analogue of uid equality.
Which mechanism actually ran is reported in :attr:`OwnershipCheck.mechanism`, so
callers and tests can assert the platform difference instead of trusting it.

A fifth difference lives here too: durability.  POSIX lets ``fsync`` run on a
descriptor opened ``O_RDONLY`` (and on a *directory* descriptor).  Windows
implements ``os.fsync`` as ``FlushFileBuffers``, which the kernel only honours
on a handle carrying ``GENERIC_WRITE``, so the same call raises
``OSError(EBADF)`` there; and Windows cannot open a directory through the CRT at
all.  :func:`fsync_path`, :func:`fsync_fd`, :func:`fsync_directory` and
:func:`fsync_directory_fd` concentrate that difference so no call site has to
know it -- the first two preserve the flush by opening with the access mode the
platform requires, the last two report ``False`` where no directory-flush
primitive exists at all.

A sixth difference is *privacy*, and it is the one behind the ``438 != 384`` and
``292 != 256`` mode assertions this port had to answer.  Everything derived from
the user's own game image lives in a private cache whose confidentiality is
expressed purely in POSIX mode bits -- ``0o700`` directories, ``0o600`` staging
files, ``0o400`` sealed files -- each re-verified after creation.  Windows
implements none of them: ``os.chmod`` toggles a single attribute (read-only), so
a file created ``0o600`` reads back ``0o666``, a sealed ``0o400`` file reads back
``0o444``, and a directory always reports ``0o777``.  Re-verifying the POSIX
numbers therefore fails there, and it fails *correctly* -- the POSIX guarantee
genuinely is not in force.  :func:`privacy_guarantee` states what each platform
does enforce, and the ``private``/``verify`` helpers below apply and re-verify
exactly that: unchanged mode bits on POSIX; on Windows the read-only attribute
for sealed files plus placement under the per-user profile root, whose inherited
ACL is what actually keeps other accounts out.  The weaker guarantee is named in
the returned :class:`PrivacyGuarantee`, never hidden behind a skipped check.

Fail-closed policy: where a Linux hardening primitive is unavailable we degrade
to the strongest available equivalent and make the degradation observable --
never a silent skip.  Concretely, :func:`seal_readonly` still guarantees the
staged bytes are immutable-in-practice by making the file read-only and
returning their hash so the caller can re-verify; :func:`exclusive_nonblocking_lock`
still fails immediately (never blocks) and still refuses when the lock is held;
:func:`try_reflink` reports ``False`` so the caller uses its verified plain
copy instead of silently skipping the copy; and :func:`fsync_directory` reports
``False`` on the one platform that has no directory-flush primitive at all,
rather than pretending the metadata was committed.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
from types import ModuleType


IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Names for the two ownership models :func:`describe_ownership` can use.  They
# are public because the guarantee differs between them and every caller/test is
# entitled to assert which one ran rather than assume.
OWNERSHIP_POSIX_UID = "posix-uid"
OWNERSHIP_WINDOWS_OWNER_SID = "windows-owner-sid"

# <accctrl.h> SE_FILE_OBJECT and <winnt.h> OWNER_SECURITY_INFORMATION /
# TOKEN_QUERY, plus the TokenUser TOKEN_INFORMATION_CLASS.  Only meaningful on
# Windows; declared here so the ctypes calls read like the Win32 documentation.
_SE_FILE_OBJECT = 1
_OWNER_SECURITY_INFORMATION = 0x00000001
_TOKEN_QUERY = 0x0008
_TOKEN_USER_CLASS = 1
_ERROR_SUCCESS = 0

# ``FICLONE`` from <linux/fs.h>: _IOW(0x94, 9, int).  Only meaningful on Linux.
_FICLONE = 0x40049409
_READONLY_MODE = 0o400
_HASH_BLOCK = 1 << 20

# Names for the two privacy models :func:`privacy_guarantee` can report.  Public
# for the same reason as the ownership mechanisms: they guarantee different
# things and no caller or test should have to guess which one is in force.
PRIVACY_POSIX_MODE_BITS = "posix-mode-bits"
PRIVACY_WINDOWS_USER_PROFILE_ACL = "windows-user-profile-acl"

# What a private path is *created* as, and what it must read back as, on each
# platform.  The POSIX triple is the historical contract, unchanged.  The Windows
# triple is not a relaxation of it -- it is what NTFS through the CRT actually
# reports: directories have no mode at all, and a file is either writable
# (``0o666``) or carries the read-only attribute (``0o444``).
POSIX_PRIVATE_DIRECTORY_MODE = 0o700
POSIX_PRIVATE_FILE_MODE = 0o600
POSIX_SEALED_FILE_MODE = _READONLY_MODE
WINDOWS_DIRECTORY_MODE = 0o777
WINDOWS_WRITABLE_FILE_MODE = 0o666
WINDOWS_READ_ONLY_FILE_MODE = 0o444

# The one permission bit every supported platform really implements.
_OWNER_WRITE_BIT = 0o200

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


class PrivatePathError(RuntimeError):
    """A path that must be private to the current user demonstrably is not.

    Raised by the ``verify_private_*`` helpers when a path fails the privacy
    contract *its own platform* promises -- a POSIX cache directory that is not
    ``0o700``, a Windows sealed file whose read-only attribute did not stick, a
    symlink where a real directory was required.  It is never raised merely
    because a platform is weaker than Linux: that difference is reported through
    :func:`privacy_guarantee`, not through an exception.
    """


class OwnershipCheckError(RuntimeError):
    """An ownership question could not even be *asked* on this platform.

    Raised only for a caller mistake -- asking "do I own this?" on a platform
    with no ``st_uid`` while supplying neither a descriptor nor a path, which
    leaves nothing to interrogate.  A *failed* lookup is never this error: it is
    reported as :attr:`OwnershipCheck.owned` ``False`` so the caller fails
    closed instead of aborting with an unhandled exception.
    """


class DurabilityError(RuntimeError):
    """A file we own could not be flushed to stable storage.

    Raised only when the flush is genuinely impossible -- never to paper over a
    platform difference.  Every call site treats it as fatal, because the whole
    reason these flushes exist is to get an archive onto the platter *before* it
    is published (hard-linked or renamed) into its final name.
    """


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


@dataclass(frozen=True)
class OwnershipCheck:
    """Outcome of :func:`describe_ownership`, with the mechanism that produced it.

    ``owned`` is the security answer: ``True`` only when the object really does
    belong to the account running this process.  ``mechanism`` is
    :data:`OWNERSHIP_POSIX_UID` or :data:`OWNERSHIP_WINDOWS_OWNER_SID` and exists
    so a caller -- or a test -- can assert *how* the answer was reached, because
    the two mechanisms guarantee subtly different things and the difference must
    never be invisible.  ``detail`` carries the compared identities (uids, or SID
    strings, or the Win32 failure) purely for diagnostics; never branch on it.
    """

    owned: bool
    mechanism: str
    detail: str


@dataclass(frozen=True)
class PrivacyGuarantee:
    """Exactly what "private to the current user" means on the running OS.

    Read this as a contract, not a description.  ``posix_mode_privacy`` is the
    load-bearing field: when it is ``True`` the three ``*_mode`` values are
    *enforced* confidentiality -- ``0o700``/``0o600`` really do lock other
    accounts out, and the ``verify_private_*`` helpers re-check them.  When it is
    ``False`` (Windows) the same three values are only what ``stat`` will report;
    they carry no privacy at all, and confidentiality comes instead from
    ``profile_root_acl`` -- the inherited ACL of the per-user profile directory
    the private cache is created under.

    ``sealed_read_only`` is the one guarantee both platforms genuinely share: a
    sealed file has no owner-write bit, so it cannot be modified in place without
    an explicit, deliberate permission change.  ``summary`` exists so a log line
    or a support report can state the difference in words.
    """

    mechanism: str
    posix_mode_privacy: bool
    profile_root_acl: bool
    sealed_read_only: bool
    directory_mode: int
    file_mode: int
    sealed_file_mode: int
    summary: str


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


@dataclass(frozen=True)
class _WindowsSecurityApi:
    """The two Win32 DLLs used for owner-SID lookups, with argtypes applied.

    Prepared once and cached: leaving ``argtypes``/``restype`` unset would let
    ctypes truncate 64-bit ``HANDLE`` and ``PSID`` values to ``int``, which is
    exactly the class of bug that silently compares the wrong bytes.
    """

    advapi32: ctypes.CDLL
    kernel32: ctypes.CDLL


_windows_security_api_cache: _WindowsSecurityApi | None = None


def _windows_security_api() -> _WindowsSecurityApi:
    """Load and type the Win32 security entry points, or fail closed."""

    global _windows_security_api_cache
    cached = _windows_security_api_cache
    if cached is not None:
        return cached
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise OwnershipCheckError(
            "Owner-SID ownership requires ctypes.windll, which only exists on "
            "Windows"
        )

    advapi32 = windll.advapi32
    kernel32 = windll.kernel32
    handle = ctypes.c_void_p
    dword = ctypes.c_ulong
    boolean = ctypes.c_int
    handle_out = ctypes.POINTER(ctypes.c_void_p)
    # GetSecurityInfo/GetNamedSecurityInfoW share every parameter after the
    # object they name, so declare that tail once.
    security_tail = [
        ctypes.c_int,   # SE_OBJECT_TYPE ObjectType
        dword,          # SECURITY_INFORMATION SecurityInfo
        handle_out,     # PSID *ppsidOwner
        handle_out,     # PSID *ppsidGroup
        handle_out,     # PACL *ppDacl
        handle_out,     # PACL *ppSacl
        handle_out,     # PSECURITY_DESCRIPTOR *ppSecurityDescriptor
    ]

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = handle
    kernel32.CloseHandle.argtypes = [handle]
    kernel32.CloseHandle.restype = boolean
    kernel32.LocalFree.argtypes = [handle]
    kernel32.LocalFree.restype = handle

    advapi32.OpenProcessToken.argtypes = [handle, dword, handle_out]
    advapi32.OpenProcessToken.restype = boolean
    advapi32.GetTokenInformation.argtypes = [
        handle,
        ctypes.c_int,
        handle,
        dword,
        ctypes.POINTER(dword),
    ]
    advapi32.GetTokenInformation.restype = boolean
    advapi32.ConvertSidToStringSidW.argtypes = [
        handle,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    advapi32.ConvertSidToStringSidW.restype = boolean
    advapi32.GetSecurityInfo.argtypes = [handle, *security_tail]
    advapi32.GetSecurityInfo.restype = dword
    advapi32.GetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, *security_tail]
    advapi32.GetNamedSecurityInfoW.restype = dword

    prepared = _WindowsSecurityApi(advapi32=advapi32, kernel32=kernel32)
    _windows_security_api_cache = prepared
    return prepared


def _windows_string_sid(api: _WindowsSecurityApi, sid: ctypes.c_void_p) -> str:
    """Render a ``PSID`` as its canonical ``S-1-...`` string.

    Comparing the textual form rather than calling ``EqualSid`` keeps the
    compared identities printable, which is what makes an ownership refusal
    diagnosable on a machine we cannot debug.
    """

    text = ctypes.c_wchar_p()
    if not api.advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise OwnershipCheckError(
            "Win32 could not render a security identifier as text"
        )
    try:
        rendered = text.value
    finally:
        # The string was allocated by Win32; free it through LocalFree even if
        # reading it raised, or the process leaks it on every ownership check.
        api.kernel32.LocalFree(text)
    if not rendered:
        raise OwnershipCheckError("Win32 rendered an empty security identifier")
    return rendered


def _windows_current_user_sid() -> str:
    """The user SID of the process token, i.e. "who am I" on Windows."""

    api = _windows_security_api()
    token = ctypes.c_void_p()
    if not api.advapi32.OpenProcessToken(
        api.kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise OwnershipCheckError(
            "Win32 refused to open the current process token"
        )
    try:
        size = ctypes.c_ulong(0)
        # First call is the documented size probe and is expected to fail with
        # ERROR_INSUFFICIENT_BUFFER; only the reported size matters.
        api.advapi32.GetTokenInformation(
            token, _TOKEN_USER_CLASS, None, 0, ctypes.byref(size)
        )
        if size.value == 0:
            raise OwnershipCheckError(
                "Win32 reported an empty process-token user record"
            )
        buffer = ctypes.create_string_buffer(size.value)
        if not api.advapi32.GetTokenInformation(
            token, _TOKEN_USER_CLASS, buffer, size.value, ctypes.byref(size)
        ):
            raise OwnershipCheckError(
                "Win32 refused to read the current process-token user"
            )
        # TOKEN_USER is a single SID_AND_ATTRIBUTES whose first member is the
        # PSID, so the pointer we want is the first pointer in the buffer.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents
        return _windows_string_sid(api, sid)
    finally:
        api.kernel32.CloseHandle(token)


def _windows_owner_sid(
    *,
    fd: int | None,
    path: str | os.PathLike[str] | None,
) -> str:
    """The owner SID of an open descriptor (preferred) or a named path.

    The descriptor form is preferred wherever the caller has one because it
    interrogates the very object it already validated, closing the
    stat-then-open race that a name-based lookup would reopen.
    """

    api = _windows_security_api()
    owner = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    if fd is not None:
        try:
            msvcrt = _require_msvcrt()
            native_handle = msvcrt.get_osfhandle(fd)
        except (RuntimeError, OSError, ValueError) as exc:
            raise OwnershipCheckError(
                f"no Win32 handle backs descriptor {fd}: {exc}"
            ) from exc
        status = api.advapi32.GetSecurityInfo(
            ctypes.c_void_p(native_handle),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION,
            ctypes.byref(owner),
            None,
            None,
            None,
            ctypes.byref(descriptor),
        )
    elif path is None:
        raise OwnershipCheckError(
            "an owner-SID lookup needs either a descriptor or a path"
        )
    else:
        status = api.advapi32.GetNamedSecurityInfoW(
            os.fsdecode(path),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION,
            ctypes.byref(owner),
            None,
            None,
            None,
            ctypes.byref(descriptor),
        )
    if status != _ERROR_SUCCESS:
        raise OwnershipCheckError(
            f"Win32 owner lookup failed with error {status}"
        )
    try:
        return _windows_string_sid(api, owner)
    finally:
        # ``owner`` points *into* this security descriptor, so it may only be
        # freed after the SID has been rendered.
        api.kernel32.LocalFree(descriptor)


def supports_posix_uid_ownership() -> bool:
    """Whether ``st_uid`` versus :func:`os.getuid` is a meaningful question here.

    ``False`` on Windows, where :func:`os.getuid` does not exist and ``st_uid``
    is a constant ``0`` placeholder for every file -- which is precisely why the
    comparison must not be ported literally.
    """

    return getattr(os, "getuid", None) is not None


def ownership_mechanism() -> str:
    """Name the model :func:`describe_ownership` will use on this platform."""

    if supports_posix_uid_ownership():
        return OWNERSHIP_POSIX_UID
    return OWNERSHIP_WINDOWS_OWNER_SID


def describe_ownership(
    info: os.stat_result,
    *,
    fd: int | None = None,
    path: str | os.PathLike[str] | None = None,
) -> OwnershipCheck:
    """Answer "does the account running this process own this object?".

    On POSIX this is exactly the historical check, ``info.st_uid ==
    os.getuid()``, and ``fd``/``path`` are ignored: nothing about Linux or macOS
    behaviour changes.

    On Windows ``info.st_uid`` is a meaningless ``0`` for every file, so trusting
    it would convert a real guard against another user's planted cache into a
    check that always passes.  The Win32 equivalent is used instead -- the
    object's owner SID compared against the process token's user SID -- which is
    the same guarantee expressed in the platform's own ownership model.  That
    needs something to interrogate, so at least one of ``fd`` (preferred, and
    race-free) or ``path`` must be supplied; supplying neither is a caller bug
    and raises :class:`OwnershipCheckError` rather than guessing.

    A Win32 lookup that fails (access denied, a network filesystem with no owner
    information, a handle without ``READ_CONTROL``) is reported as *not owned*.
    That is deliberate: an unanswerable ownership question must fail closed, and
    :attr:`OwnershipCheck.detail` carries the Win32 error so the refusal is
    diagnosable.

    Known, documented difference: an owner SID is not an exact synonym for a uid.
    A file created by a process running elevated is owned by the local
    Administrators group rather than by the user, so this returns ``False`` for
    it -- a false refusal, never a false acceptance.  It errs in the safe
    direction, which is the only direction a security check may err.
    """

    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        current_uid = getuid()
        return OwnershipCheck(
            owned=info.st_uid == current_uid,
            mechanism=OWNERSHIP_POSIX_UID,
            detail=f"st_uid={info.st_uid} current uid={current_uid}",
        )
    if fd is None and path is None:
        raise OwnershipCheckError(
            "Ownership cannot be established on a platform without os.getuid "
            "unless a descriptor or a path is supplied to interrogate"
        )
    try:
        owner_sid = _windows_owner_sid(fd=fd, path=path)
        current_sid = _windows_current_user_sid()
    except OwnershipCheckError as exc:
        return OwnershipCheck(
            owned=False,
            mechanism=OWNERSHIP_WINDOWS_OWNER_SID,
            detail=f"owner SID unavailable: {exc}",
        )
    return OwnershipCheck(
        owned=owner_sid == current_sid,
        mechanism=OWNERSHIP_WINDOWS_OWNER_SID,
        detail=f"owner SID={owner_sid} current user SID={current_sid}",
    )


def is_owned_by_current_user(
    info: os.stat_result,
    *,
    fd: int | None = None,
    path: str | os.PathLike[str] | None = None,
) -> bool:
    """Whether ``info``'s object belongs to the account running this process.

    The boolean shorthand for :func:`describe_ownership`; see it for the full
    contract, including why ``fd`` or ``path`` is mandatory on Windows and why a
    failed Win32 lookup is reported as *not owned*.
    """

    return describe_ownership(info, fd=fd, path=path).owned


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


def write_seal_mask() -> int:
    """The full ``memfd`` write-seal set: ``GROW | SEAL | SHRINK | WRITE``.

    Exposed so a caller that must apply or re-verify kernel seals itself (the
    pinned XISO verifier seals an *executable* copy, with its own mode and hash
    contract, so it cannot reuse :func:`seal_readonly`) never has to import
    :mod:`fcntl` at module scope -- the exact portability bug this module exists
    to remove.  Fails closed where seals do not exist.
    """

    fcntl = _require_fcntl()
    return (
        fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_SEAL
        | fcntl.F_SEAL_SHRINK
        | fcntl.F_SEAL_WRITE
    )


def read_seals(fd: int) -> int:
    """Report the seals currently set on ``fd`` (Linux ``F_GET_SEALS``)."""

    fcntl = _require_fcntl()
    return fcntl.fcntl(fd, fcntl.F_GET_SEALS)


def add_seals(fd: int, seals: int) -> None:
    """Apply ``seals`` to ``fd`` and prove they stuck, or fail closed.

    The read-back is not paranoia: ``F_ADD_SEALS`` silently succeeds on a
    descriptor that was never opened ``MFD_ALLOW_SEALING`` in some kernels, and
    an unsealed "sealed" copy is precisely the integrity hole these seals exist
    to close.
    """

    fcntl = _require_fcntl()
    try:
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
    except OSError as exc:
        raise SealIntegrityError(
            "Kernel write seals could not be applied to the staged descriptor"
        ) from exc
    if read_seals(fd) & seals != seals:
        raise SealIntegrityError(
            "Kernel write seals did not stick to the staged descriptor"
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


def pwrite(fd: int, data: bytes, offset: int) -> int:
    """Positional write that never moves the descriptor offset.

    Uses :func:`os.pwrite` where available (POSIX) and falls back to a
    seek/write/restore sequence on Windows, writing the same bytes at the same
    ``offset`` and leaving the descriptor position where it found it.  Returns
    the number of bytes written.
    """

    pwriter = getattr(os, "pwrite", None)
    if pwriter is not None:
        return pwriter(fd, data, offset)
    return _pwrite_via_seek(fd, data, offset)


def _pwrite_via_seek(fd: int, data: bytes, offset: int) -> int:
    """Windows fallback for :func:`os.pwrite`; matches its bytes and offset."""

    if not data:
        return 0
    saved = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(fd, view[written:])
            if count == 0:
                break
            written += count
        return written
    finally:
        os.lseek(fd, saved, os.SEEK_SET)


def copy_file_range(
    src: int,
    dst: int,
    count: int,
    *,
    offset_src: int | None = None,
    offset_dst: int | None = None,
) -> int:
    """Copy up to ``count`` bytes from ``src`` to ``dst``: a portable drop-in.

    Semantics and return value match :func:`os.copy_file_range` exactly -- the
    number of bytes actually copied is returned, which may be short and is ``0``
    at end of source, so a caller's ``while copied < size`` loop behaves the same
    whichever platform runs it.  Position handling matches per descriptor too: an
    ``offset_*`` of ``None`` reads from / writes at that descriptor's current
    position and advances it, while a supplied offset leaves that position
    untouched.

    On Linux this *is* :func:`os.copy_file_range` -- when both offsets are
    ``None`` it is invoked in the identical three-argument form the historical
    call sites used -- so the in-kernel copy (and any reflink or server-side
    acceleration the kernel can apply) runs byte for byte, and every ``OSError``
    it may raise, including the ``EXDEV`` / ``EINVAL`` / ``ENOSYS`` a caller
    catches to fall back to a plain copy, propagates unchanged.

    macOS and Windows have no ``os.copy_file_range`` at all -- it is a Linux-only
    syscall, not merely a slow path -- so the same byte range is copied in user
    space through :func:`pread` / :func:`pwrite`, which are themselves
    Windows-safe.  It is not a weaker copy: the identical bytes are transferred
    and the identical count returned; only the venue (user space versus kernel)
    differs.  That is the fail-closed "degrade to the strongest available
    equivalent" rule applied to a performance primitive -- nothing is skipped.
    """

    kernel_copy = getattr(os, "copy_file_range", None)
    if kernel_copy is not None:
        if offset_src is None and offset_dst is None:
            return kernel_copy(src, dst, count)
        return kernel_copy(
            src, dst, count, offset_src=offset_src, offset_dst=offset_dst
        )
    return _copy_file_range_via_rw(
        src, dst, count, offset_src=offset_src, offset_dst=offset_dst
    )


def _copy_file_range_via_rw(
    src: int,
    dst: int,
    count: int,
    *,
    offset_src: int | None,
    offset_dst: int | None,
) -> int:
    """User-space stand-in for :func:`os.copy_file_range` where it is absent.

    Reads one chunk of at most ``count`` bytes from ``src`` and writes exactly
    those bytes to ``dst``, returning the number copied (``0`` at end of source)
    so the caller's loop terminates identically to the kernel call.  Each
    descriptor's position is handled the way :func:`os.copy_file_range` documents:
    ``None`` reads/writes at -- and advances -- the current offset (via
    :func:`os.read` / :func:`os.write`); a supplied offset uses :func:`pread` /
    :func:`pwrite`, which do not move it.  Short writes are looped until the whole
    chunk that was read is on disk, so the bytes copied are always exactly the
    bytes read.
    """

    if count <= 0:
        return 0
    if offset_src is None:
        data = os.read(src, count)
    else:
        data = pread(src, count, offset_src)
    if not data:
        return 0
    view = memoryview(data)
    written = 0
    while view:
        if offset_dst is None:
            amount = os.write(dst, view)
        else:
            amount = pwrite(dst, view, offset_dst + written)
        if amount <= 0:
            raise OSError(
                errno.EIO,
                "short write while emulating os.copy_file_range",
            )
        view = view[amount:]
        written += amount
    return written


def supports_directory_fsync() -> bool:
    """Whether a directory's own metadata can be flushed on this platform.

    POSIX exposes a directory as an ``O_RDONLY`` descriptor that ``fsync`` will
    commit, which is how a rename or hard link is made durable.  Windows has no
    equivalent: the CRT refuses to ``open`` a directory, and ``FlushFileBuffers``
    takes a file handle.  Callers use the result to report the difference rather
    than to silently drop the flush.
    """

    return not IS_WINDOWS


def _flush_open_flags(*, follow_symlinks: bool) -> int:
    """Flags for opening a regular file we own purely in order to flush it.

    The access mode is the whole point.  POSIX keeps ``O_RDONLY`` -- byte for
    byte the mode the hand-rolled call sites used, so nothing about Linux or
    macOS behaviour changes.  Windows must use ``O_RDWR`` because ``os.fsync``
    is ``FlushFileBuffers`` there and the kernel rejects it (``EBADF``) on a
    handle that lacks ``GENERIC_WRITE``.  Read-write is the *minimum* access
    that permits the flush, not a relaxation: the file is one we just wrote and
    still own privately, and no byte is written through the extra access.
    """

    flags = os.O_RDWR if IS_WINDOWS else os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    if not follow_symlinks:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def fsync_path(
    path: str | os.PathLike[str],
    *,
    follow_symlinks: bool = True,
) -> None:
    """Flush a file we own to stable storage, addressed by path.

    This replaces the ``open(path, "rb")`` / ``os.fsync(handle.fileno())`` idiom
    the codebase used before publishing an archive.  On POSIX the file is opened
    ``O_RDONLY`` and ``os.fsync`` is called on it -- identical syscalls, in the
    same order, as the code it replaces.  On Windows the same file is opened
    ``O_RDWR`` instead, because ``FlushFileBuffers`` requires a writable handle;
    the flush itself, and therefore the durability guarantee, is unchanged.

    ``follow_symlinks=False`` adds ``O_NOFOLLOW`` where the platform has it, for
    the call sites that already refused to flush through a symlink.  Windows has
    no ``O_NOFOLLOW``, so on that platform the refusal is not available and the
    caller's other identity checks (``lstat``/``st_ino``) carry that guarantee.

    Raises :class:`DurabilityError` on Windows when the file carries the
    read-only attribute, because that attribute makes the writable open -- and
    hence any flush at all -- impossible there.  Clearing the attribute behind
    the caller's back would momentarily un-protect a file the caller
    deliberately hardened, so this fails loudly instead.  No shipped call site
    flushes an already-read-only file: every one of them flushes a private
    staging file (mode ``0o600``/``0o644``) *before* it is sealed or published.
    """

    flags = _flush_open_flags(follow_symlinks=follow_symlinks)
    try:
        descriptor = os.open(path, flags)
    except PermissionError as exc:
        if not IS_WINDOWS:
            raise
        raise DurabilityError(
            f"Cannot flush {os.fspath(path)!r} to disk: Windows needs a writable "
            "handle for FlushFileBuffers, and this file is marked read-only"
        ) from exc
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_fd(fd: int, *, path: str | os.PathLike[str] | None = None) -> None:
    """Flush an already-open descriptor, tolerating the one Windows refusal.

    ``os.fsync(fd)`` is attempted first on every platform, so a writable
    descriptor takes exactly one syscall everywhere and POSIX behaviour -- including
    which errors propagate -- is untouched.

    Only on Windows, and only for ``EBADF``, is a fallback taken: that errno is
    precisely how ``FlushFileBuffers`` reports "this handle has no write access",
    which happens whenever the caller opened the file ``O_RDONLY`` (legal and
    flushable on POSIX).  The fallback reopens the *same file* by ``path`` with
    write access and flushes that handle.  Reopening by name would otherwise
    re-introduce a time-of-check window, so the reopened file's
    ``(st_dev, st_ino)`` is compared against the caller's descriptor and a
    mismatch raises :class:`DurabilityError` -- the caller held that descriptor
    open exactly to pin the inode it verified, and that guarantee is preserved,
    not dropped.  A ``path`` is required for this fallback; without one the
    descriptor cannot be flushed at all and :class:`DurabilityError` is raised
    rather than the flush being skipped.
    """

    try:
        os.fsync(fd)
        return
    except OSError as exc:
        if not IS_WINDOWS or exc.errno != errno.EBADF:
            raise
        refusal = exc
    if path is None:
        raise DurabilityError(
            "Cannot flush a read-only descriptor on Windows without a path to "
            "reopen it with write access"
        ) from refusal
    pinned = os.fstat(fd)
    reopened = os.open(path, _flush_open_flags(follow_symlinks=False))
    try:
        fresh = os.fstat(reopened)
        if not (pinned.st_ino and fresh.st_ino):
            raise DurabilityError(
                f"Cannot prove {os.fspath(path)!r} still names the descriptor "
                "being flushed: this filesystem reports no file identity"
            ) from refusal
        if (fresh.st_dev, fresh.st_ino) != (pinned.st_dev, pinned.st_ino):
            raise DurabilityError(
                f"{os.fspath(path)!r} no longer names the file being flushed"
            ) from refusal
        os.fsync(reopened)
    finally:
        os.close(reopened)


def fsync_directory(path: str | os.PathLike[str]) -> bool:
    """Commit a directory's own entries, returning whether that really happened.

    On POSIX this is the standard "make the rename/link durable" step: open the
    directory ``O_RDONLY | O_DIRECTORY`` and ``fsync`` it, exactly as the call
    sites did by hand, and return ``True``.

    On Windows it returns ``False`` without touching the filesystem, because the
    platform offers no directory-flush primitive at any level the CRT exposes:
    ``os.open`` on a directory fails outright, and ``FlushFileBuffers`` is
    defined only for file handles.  The strongest available equivalent is the
    one the callers already perform -- flushing the *file* before renaming or
    hard-linking it, which NTFS and ReFS journal the directory entry alongside.
    The ``False`` return makes that gap explicit and assertable instead of
    letting a dropped flush look like a completed one.
    """

    if not supports_directory_fsync():
        return False
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return True


def fsync_directory_fd(fd: int) -> bool:
    """Commit an already-open directory descriptor, reporting whether it worked.

    The publish transactions in the audio-source stores hold one directory
    descriptor open for their whole duration and address every step through it
    (``dir_fd=``-relative ``stat``, ``rename``, ``unlink``), precisely so the
    directory they verified cannot be swapped underneath them.  Re-opening that
    directory by name to flush it would throw that guarantee away, so this
    flushes the descriptor the caller already holds.

    POSIX flushes it and returns ``True`` -- the same single ``os.fsync(fd)``
    call this replaced.  Windows returns ``False``: it has no directory-flush
    primitive, and in fact cannot produce a directory descriptor at all, so on
    that platform this line is reached only if the caller obtained one by some
    other means.  Reporting ``False`` keeps the missing guarantee visible rather
    than letting a skipped flush read as a completed one.
    """

    if not supports_directory_fsync():
        return False
    os.fsync(fd)
    return True


def fchmod_readonly(fd: int, path: str | None) -> None:
    """Remove every write permission this platform implements, and verify it.

    POSIX: ``fchmod(fd, 0o400)`` -- byte for byte the historical call -- leaves
    the file readable only by its owner and writable by nobody.

    Windows: there is no ``os.fchmod``, so ``os.chmod(path, 0o400)`` is used on
    the same file.  Only one bit of that mode exists there: clearing owner-write
    sets the read-only attribute.  The file therefore reads back as ``0o444``,
    not ``0o400`` -- it stays readable by anyone who can reach the path, because
    Windows has no group/other mode bits to remove.  Confidentiality on that
    platform comes from the ACL of the per-user profile root the private cache
    lives under (see :func:`privacy_guarantee`), not from this call.

    What this call guarantees identically on both platforms is *immutability in
    place*: the owner-write bit is gone.  That is re-read from the file
    afterwards and a platform that ignored the request raises
    :class:`SealIntegrityError` rather than letting an unenforced chmod pass for
    a seal.
    """

    fchmod = getattr(os, "fchmod", None)
    if fchmod is not None:
        fchmod(fd, _READONLY_MODE)
        _verify_read_only_descriptor(fd, path)
        return
    if path is None:
        raise RuntimeError(
            "Cannot make a descriptor read-only without a path on a platform "
            "that lacks os.fchmod"
        )
    os.chmod(path, _READONLY_MODE)
    _verify_read_only_descriptor(fd, path)


def _verify_read_only_descriptor(fd: int, path: str | None) -> None:
    """Fail closed unless the owner-write bit is really gone from the file.

    Read back through the descriptor where possible so the check interrogates
    the exact object that was hardened rather than whatever the name points at
    now; a descriptor that can no longer be stat-ed falls back to the path.
    """

    try:
        observed = os.fstat(fd).st_mode
    except OSError:
        if path is None:
            raise
        observed = os.stat(path).st_mode
    if stat.S_IMODE(observed) & _OWNER_WRITE_BIT:
        raise SealIntegrityError(
            "The read-only permission did not stick to the staged file: its mode "
            f"is 0o{stat.S_IMODE(observed):o} and still carries owner-write"
        )


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


# ---------------------------------------------------------------------------
# Private paths: create, harden, and re-verify "only this user may read this".
#
# One place decides what privacy means per platform, so no call site has to.
# Ownership ("does this belong to me?") is a *separate* question answered by
# :func:`describe_ownership`; a complete guard on a cache directory asks both.
# ---------------------------------------------------------------------------


def privacy_guarantee() -> PrivacyGuarantee:
    """State exactly what a private path is guaranteed to be, on this OS.

    Computed per call rather than frozen at import so a test can flip
    :data:`IS_WINDOWS` and assert the *other* platform's contract without
    re-importing the module.
    """

    if IS_WINDOWS:
        return PrivacyGuarantee(
            mechanism=PRIVACY_WINDOWS_USER_PROFILE_ACL,
            posix_mode_privacy=False,
            profile_root_acl=True,
            sealed_read_only=True,
            directory_mode=WINDOWS_DIRECTORY_MODE,
            file_mode=WINDOWS_WRITABLE_FILE_MODE,
            sealed_file_mode=WINDOWS_READ_ONLY_FILE_MODE,
            summary=(
                "Windows has no POSIX mode bits: a private directory reports "
                "0o777 and a private file 0o666, and neither number confers any "
                "privacy. Confidentiality comes from the per-user profile root "
                "(%LOCALAPPDATA%), whose inherited ACL excludes other accounts. "
                "Sealed files additionally carry the read-only attribute and "
                "report 0o444."
            ),
        )
    return PrivacyGuarantee(
        mechanism=PRIVACY_POSIX_MODE_BITS,
        posix_mode_privacy=True,
        profile_root_acl=False,
        sealed_read_only=True,
        directory_mode=POSIX_PRIVATE_DIRECTORY_MODE,
        file_mode=POSIX_PRIVATE_FILE_MODE,
        sealed_file_mode=POSIX_SEALED_FILE_MODE,
        summary=(
            "POSIX mode bits are enforced by the kernel: private directories are "
            "0o700, private files 0o600 and sealed files 0o400, each re-verified "
            "after creation."
        ),
    )


def private_directory_mode() -> int:
    """The mode a private directory must read back as on this platform."""

    return privacy_guarantee().directory_mode


def private_file_mode() -> int:
    """The mode a private (still writable) staging file must read back as."""

    return privacy_guarantee().file_mode


def sealed_file_mode() -> int:
    """The mode a sealed, read-only file must read back as on this platform."""

    return privacy_guarantee().sealed_file_mode


def user_private_root() -> Path:
    """The per-user tree this OS keeps private without any mode bits.

    On Windows this is ``%LOCALAPPDATA%`` -- the per-user, non-roaming
    application-data directory, whose ACL grants only the owning account (and
    administrators) access, and which every child inherits.  That inheritance is
    the Windows equivalent of a ``0o700`` cache root, so private caches are
    created beneath it.

    On POSIX it is the home directory; privacy there comes from the mode bits on
    the cache directory itself, so this is only used to keep caches out of shared
    locations such as ``/tmp``.
    """

    if IS_WINDOWS:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata)
        return Path.home() / "AppData" / "Local"
    return Path.home()


def is_within_user_private_root(path: str | os.PathLike[str]) -> bool:
    """Whether ``path`` lies inside :func:`user_private_root`.

    Used to assert *placement* -- the guarantee Windows actually offers.  A
    symlink-free comparison of fully resolved paths, so a link out of the profile
    root cannot pass.  Returns ``False`` rather than raising when either path
    cannot be resolved: an unanswerable placement question must fail closed.
    """

    try:
        resolved = Path(path).resolve()
        root = user_private_root().resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def create_private_directory(
    path: str | os.PathLike[str],
    *,
    parents: bool = False,
    exist_ok: bool = False,
) -> None:
    """Create a directory intended to be readable only by the current user.

    POSIX: ``mkdir`` with mode ``0o700``, exactly as the call sites did by hand.
    The mode is still subject to ``umask`` at creation, which is why
    :func:`harden_private_directory` follows it at every call site.

    Windows: the mode argument is accepted and ignored by the OS -- directories
    there have no mode.  The directory is created identically, and its privacy
    comes from the ACL it inherits from :func:`user_private_root`.
    """

    Path(path).mkdir(
        mode=POSIX_PRIVATE_DIRECTORY_MODE,
        parents=parents,
        exist_ok=exist_ok,
    )


def harden_private_directory(path: str | os.PathLike[str]) -> None:
    """Force an existing directory to the platform's private permissions.

    POSIX: ``chmod 0o700`` -- byte for byte the historical call, and the step
    that defeats a permissive ``umask`` or a directory created by an older build.

    Windows: a deliberate no-op.  ``os.chmod`` on a directory there can only
    toggle the read-only attribute, which does not restrict reading, does not
    exclude any account, and does make the directory harder to delete -- so
    applying it would trade a guarantee we never gain for a cleanup failure we
    would.  Directory privacy on Windows is the inherited profile-root ACL
    instead, asserted once at the tree root by
    :func:`verify_private_root_placement`.
    """

    if IS_WINDOWS:
        return
    os.chmod(path, POSIX_PRIVATE_DIRECTORY_MODE)


def harden_private_file(path: str | os.PathLike[str]) -> None:
    """Force an existing file to the platform's private (writable) permissions.

    POSIX: ``chmod 0o600``.  Windows: ``chmod 0o600`` too, where the only bit
    that lands is owner-write -- it *clears* the read-only attribute, leaving the
    file writable, and the file reads back ``0o666``.  Nothing about the call
    confers privacy there; it exists so a staging file is never accidentally left
    read-only, which on Windows would make it undeletable.
    """

    os.chmod(path, POSIX_PRIVATE_FILE_MODE)


def verify_private_directory(
    path: str | os.PathLike[str],
    label: str,
    *,
    fd: int | None = None,
) -> os.stat_result:
    """Re-verify a private directory, raising :class:`PrivatePathError` if it is not.

    Checked on every platform: the name resolves to a real directory and is not a
    symlink (on Windows, not a reparse point), because a link is how a private
    cache gets redirected somewhere world-readable.

    Checked on POSIX only: the mode is exactly ``0o700``.  That assertion is the
    confidentiality guarantee and is unchanged from the code this replaces.

    NOT checked on Windows, explicitly: any mode at all.  Every directory reports
    ``0o777`` there and the number means nothing, so asserting it would only
    dress a missing guarantee up as a passing check.  Windows confidentiality is
    the ACL inherited from the tree root, which is a property of *where the root
    was created* -- asserted once, at that root, by
    :func:`verify_private_root_placement`.  Every directory beneath it inherits
    that ACL, and the non-link check above is what stops a child being redirected
    out of the protected tree.  :func:`privacy_guarantee` reports the difference
    so a caller or a test asserts the platform-appropriate expectation instead of
    skipping the question.
    """

    info = _lstat_private(path, label, fd=fd)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PrivatePathError(
            f"{label} must be a real, non-link directory at {os.fspath(path)!r}"
        )
    if privacy_guarantee().posix_mode_privacy:
        observed = stat.S_IMODE(info.st_mode)
        if observed != POSIX_PRIVATE_DIRECTORY_MODE:
            raise PrivatePathError(
                f"{label} must be an owner-only, mode-0700 directory at "
                f"{os.fspath(path)!r}; it is mode 0o{observed:o}"
            )
    return info


def verify_private_root_placement(path: str | os.PathLike[str], label: str) -> None:
    """Assert a private *tree root* sits where this OS makes it private.

    This is the Windows half of the privacy contract and the reason
    :func:`verify_private_directory` does not assert a mode there: a cache root
    created under :func:`user_private_root` (``%LOCALAPPDATA%``) inherits an ACL
    that excludes other accounts, and every file and directory created beneath it
    inherits that ACL in turn.

    On POSIX this is a no-op by design.  Confidentiality there is carried by the
    ``0o700`` mode on the directory itself, which holds wherever the tree lives,
    so requiring a location as well would reject legitimate cache roots (an
    ``XDG_CACHE_HOME`` on another volume, a test's temporary directory) without
    adding any guarantee.
    """

    if not IS_WINDOWS:
        return
    if not is_within_user_private_root(path):
        raise PrivatePathError(
            f"{label} must be created under this user's private profile root "
            f"({user_private_root()}) on Windows, which is where its "
            f"other-users-excluded ACL comes from; it is at {os.fspath(path)!r}"
        )


def verify_private_file(
    path: str | os.PathLike[str],
    label: str,
    *,
    fd: int | None = None,
) -> os.stat_result:
    """Re-verify a private, still-writable staging file.

    Checked everywhere: a real, non-link regular file that the owner may still
    write (a staging file that lost its write bit cannot be completed, and on
    Windows cannot even be deleted).

    Checked on POSIX: the mode is exactly ``0o600`` -- unchanged.  On Windows the
    mode is asserted to be exactly ``0o666`` instead, which is what the CRT
    reports for a writable file: an honest, platform-specific expectation rather
    than a skipped check.  It confers no privacy, and
    :attr:`PrivacyGuarantee.posix_mode_privacy` says so.
    """

    info = _lstat_private(path, label, fd=fd)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PrivatePathError(
            f"{label} must be a real, non-link regular file at {os.fspath(path)!r}"
        )
    observed = stat.S_IMODE(info.st_mode)
    expected = private_file_mode()
    if observed != expected:
        raise PrivatePathError(
            f"{label} must be a mode-0{expected:o} private file at "
            f"{os.fspath(path)!r}; it is mode 0o{observed:o}"
        )
    return info


def verify_sealed_file(
    path: str | os.PathLike[str],
    label: str,
    *,
    fd: int | None = None,
) -> os.stat_result:
    """Re-verify a sealed file: no owner-write bit, on any platform.

    The owner-write bit is the single permission every supported OS really
    implements, so its absence is asserted everywhere and is the guarantee that
    a sealed cache file cannot be rewritten in place.

    The exact mode is asserted too, against :func:`sealed_file_mode`: ``0o400``
    on POSIX (owner-read only) and ``0o444`` on Windows (the read-only
    attribute).  The Windows value is weaker -- it is still readable by anyone
    who can reach the path -- and that is exactly why it is asserted explicitly
    instead of being loosened away for both platforms.
    """

    info = _lstat_private(path, label, fd=fd)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise PrivatePathError(
            f"{label} must be a real, non-link regular file at {os.fspath(path)!r}"
        )
    observed = stat.S_IMODE(info.st_mode)
    if observed & _OWNER_WRITE_BIT:
        raise PrivatePathError(
            f"{label} is not sealed: mode 0o{observed:o} still carries owner-write "
            f"at {os.fspath(path)!r}"
        )
    expected = sealed_file_mode()
    if observed != expected:
        raise PrivatePathError(
            f"{label} must be a mode-0{expected:o} sealed file at "
            f"{os.fspath(path)!r}; it is mode 0o{observed:o}"
        )
    return info


def _lstat_private(
    path: str | os.PathLike[str],
    label: str,
    *,
    fd: int | None,
) -> os.stat_result:
    """Inspect a private path, proving the name and the descriptor are one object.

    The name is always ``lstat``-ed, so a symlink is visible as a symlink.  When
    the caller also holds a descriptor it was opened from that name, the two are
    required to report the same ``(st_dev, st_ino)`` and the returned result is
    the descriptor's -- so the permissions that get asserted belong to the object
    the caller actually holds, not to whatever the name points at now.

    That pairing matters most on Windows.  ``O_NOFOLLOW`` does not exist there,
    so a call site that opened a private file "without following symlinks" did
    follow one; this check refuses the substitution afterwards, which is the
    strongest equivalent available on that platform.
    """

    try:
        named = os.lstat(path)
    except OSError as exc:
        raise PrivatePathError(
            f"{label} could not be inspected at {os.fspath(path)!r}: {exc}"
        ) from exc
    if fd is None:
        return named
    try:
        opened = os.fstat(fd)
    except OSError as exc:
        raise PrivatePathError(
            f"{label} could not be inspected through its descriptor at "
            f"{os.fspath(path)!r}: {exc}"
        ) from exc
    if stat.S_ISLNK(named.st_mode):
        raise PrivatePathError(
            f"{label} is a symlink at {os.fspath(path)!r}; a private path is "
            "never reached through a link"
        )
    if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
        raise PrivatePathError(
            f"{label} at {os.fspath(path)!r} no longer names the object that was "
            "opened"
        )
    return opened


def remove_private_tree(
    path: str | os.PathLike[str],
    *,
    ignore_errors: bool = False,
) -> None:
    """Delete a private staging tree, including the files we deliberately sealed.

    POSIX: exactly ``shutil.rmtree`` and nothing else.  Unlinking there is
    governed by the *directory's* write bit, so a ``0o400`` sealed file inside a
    ``0o700`` staging directory already removes cleanly and no behaviour changes.

    Windows: a file carrying the read-only attribute cannot be deleted at all --
    ``DeleteFileW`` fails ``ERROR_ACCESS_DENIED``, which surfaces as the
    ``PermissionError [Errno 13]`` that wedged every temporary directory holding
    a sealed cache file.  The attribute is therefore cleared bottom-up first and
    the tree is then removed.  That weakens nothing: the seal exists to stop the
    bytes being *altered* behind the user's back, and these bytes are being
    destroyed in the same call, by the code that owns them.
    """

    if IS_WINDOWS:
        _clear_read_only_tree(path)
    shutil.rmtree(path, ignore_errors=ignore_errors)


def _clear_read_only_tree(path: str | os.PathLike[str]) -> None:
    """Best-effort clearing of the Windows read-only attribute, depth first.

    Failures are swallowed deliberately: this only prepares for the removal that
    follows, and :func:`shutil.rmtree` is what reports a tree that truly cannot
    be deleted (or swallows it, when the caller passed ``ignore_errors``).
    """

    for parent, directories, files in os.walk(path, topdown=False):
        for name in files + directories:
            entry = os.path.join(parent, name)
            try:
                if not os.path.islink(entry):
                    os.chmod(entry, POSIX_PRIVATE_FILE_MODE)
            except OSError:
                continue
    try:
        os.chmod(path, POSIX_PRIVATE_DIRECTORY_MODE)
    except OSError:
        pass


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

    :attr:`SealResult.read_only` is a verified fact, not an assumption:
    :func:`fchmod_readonly` reads the mode back and refuses a platform that
    ignored the request.  The resulting mode differs per platform -- ``0o400``
    where POSIX bits exist, ``0o444`` on Windows, which has no group/other bits
    to clear -- and :func:`sealed_file_mode` is the single place that says which,
    so callers and tests assert the real value instead of a Linux-only constant.
    """

    fchmod_readonly(fd, path)
    if supports_sealed_memfd():
        add_seals(fd, write_seal_mask())
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
    "OWNERSHIP_POSIX_UID",
    "OWNERSHIP_WINDOWS_OWNER_SID",
    "POSIX_PRIVATE_DIRECTORY_MODE",
    "POSIX_PRIVATE_FILE_MODE",
    "POSIX_SEALED_FILE_MODE",
    "PRIVACY_POSIX_MODE_BITS",
    "PRIVACY_WINDOWS_USER_PROFILE_ACL",
    "WINDOWS_DIRECTORY_MODE",
    "WINDOWS_READ_ONLY_FILE_MODE",
    "WINDOWS_WRITABLE_FILE_MODE",
    "DurabilityError",
    "OwnershipCheck",
    "OwnershipCheckError",
    "PrivacyGuarantee",
    "PrivatePathError",
    "SealIntegrityError",
    "SealResult",
    "add_seals",
    "copy_file_range",
    "create_private_directory",
    "describe_ownership",
    "exclusive_nonblocking_lock",
    "fchmod",
    "fchmod_readonly",
    "fsync_directory",
    "fsync_directory_fd",
    "fsync_fd",
    "fsync_path",
    "harden_private_directory",
    "harden_private_file",
    "is_owned_by_current_user",
    "is_within_user_private_root",
    "ownership_mechanism",
    "pread",
    "privacy_guarantee",
    "private_directory_mode",
    "private_file_mode",
    "pwrite",
    "read_seals",
    "release_lock",
    "remove_private_tree",
    "seal_readonly",
    "sealed_file_mode",
    "supports_directory_fsync",
    "supports_posix_uid_ownership",
    "supports_reflink",
    "supports_sealed_memfd",
    "try_reflink",
    "user_private_root",
    "verify_private_directory",
    "verify_private_file",
    "verify_private_root_placement",
    "verify_sealed_file",
    "write_seal_mask",
]
