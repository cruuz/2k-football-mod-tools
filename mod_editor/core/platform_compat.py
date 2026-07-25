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
``OSError(EBADF)`` there; and the CRT cannot open a directory at all, though
Win32 ``CreateFileW(FILE_FLAG_BACKUP_SEMANTICS)`` can.  :func:`fsync_path`,
:func:`fsync_fd`, :func:`fsync_directory` and :func:`fsync_directory_fd`
concentrate that difference so no call site has to know it -- the first two
preserve the flush by opening with the access mode the platform requires;
:func:`fsync_directory` flushes a Win32 directory handle with
``FlushFileBuffers`` on Windows and returns whether that genuinely happened,
while :func:`fsync_directory_fd` reports ``False`` there because a directory
*descriptor* (which it flushes on POSIX) cannot exist on Windows.  Each returns
a bool the caller acts on rather than a silently dropped flush.

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
never a silent skip.  Concretely, where kernel write-seals exist (Linux
``memfd``) :func:`seal_readonly` makes the staged bytes genuinely immutable; where
they do not, it is honest that the read-only fallback is *reversible by the owner*
(``sealed=False``, ``reverify_before_use=True``) and returns the bytes' hash so
the caller re-verifies immediately before use -- :func:`reverify_sealed_before_exec`
re-hashes the exact file and hands back a held descriptor right before a
subprocess opens it, so a swap after the seal is caught rather than executed;
:func:`exclusive_nonblocking_lock`
still fails immediately (never blocks) and still refuses when the lock is held;
:func:`try_reflink` reports ``False`` so the caller uses its verified plain
copy instead of silently skipping the copy; and :func:`fsync_directory` returns
a bool -- ``True`` only when the directory metadata was genuinely committed
(always on POSIX, and on Windows when the ``GENERIC_WRITE`` directory handle
``FlushFileBuffers`` needs is obtainable), ``False`` where it was not -- rather
than pretending the metadata was committed.
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
import tempfile
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
_DACL_SECURITY_INFORMATION = 0x00000004
_TOKEN_QUERY = 0x0008
_TOKEN_USER_CLASS = 1
# TOKEN_INFORMATION_CLASS.TokenOwner: the SID Windows stamps on objects this
# token creates.  Equal to the user SID for an ordinary token; BUILTIN\\Administrators
# for an elevated one.
_TOKEN_OWNER_CLASS = 4
_ERROR_SUCCESS = 0

# <winnt.h> ACE AceType values.  Only the "allowed" variants grant access; a
# DENIED ace only ever restricts, so it can never widen who may read a private
# cache and is ignored by the DACL privacy check below.
_ACCESS_ALLOWED_ACE_TYPE = 0x00
_ACCESS_DENIED_ACE_TYPE = 0x01
_ACCESS_ALLOWED_OBJECT_ACE_TYPE = 0x05

# <winnt.h> access-mask bits that let a holder actually see or alter the bytes
# (read/list/traverse/write/execute, or a GENERIC/ALL grant).  A foreign SID
# granted ANY of these defeats owner-only privacy.  Pure SYNCHRONIZE/READ_CONTROL
# (metadata-only) grants are deliberately excluded so a benign inherited ace does
# not produce a false refusal, while every content-visibility bit does.
_WIN_FILE_READ_DATA = 0x00000001        # also FILE_LIST_DIRECTORY
_WIN_FILE_WRITE_DATA = 0x00000002       # also FILE_ADD_FILE
_WIN_FILE_APPEND_DATA = 0x00000004      # also FILE_ADD_SUBDIRECTORY
_WIN_FILE_READ_EA = 0x00000008
_WIN_FILE_EXECUTE = 0x00000020          # also FILE_TRAVERSE
_WIN_FILE_READ_ATTRIBUTES = 0x00000080
_WIN_GENERIC_ALL_ACCESS = 0x10000000
_WIN_GENERIC_EXECUTE_ACCESS = 0x20000000
_WIN_GENERIC_WRITE_ACCESS = 0x40000000
_WIN_GENERIC_READ_ACCESS = 0x80000000
# WRITE_DAC and WRITE_OWNER from <winnt.h>.  Neither reads a byte on its own,
# which is exactly why omitting them was a hole: WRITE_DAC is the right to
# REWRITE the DACL, so a foreign SID holding it can grant itself full read
# access and then read the cache, and WRITE_OWNER lets it take ownership and do
# the same.  A DACL that hands either to a foreign account is not owner-only, so
# they belong in the visibility mask alongside the direct read rights.
_WIN_WRITE_DAC = 0x00040000
_WIN_WRITE_OWNER = 0x00080000

_ACCESS_MASK_CONFERS_VISIBILITY = (
    _WIN_FILE_READ_DATA
    | _WIN_FILE_WRITE_DATA
    | _WIN_FILE_APPEND_DATA
    | _WIN_FILE_READ_EA
    | _WIN_FILE_EXECUTE
    | _WIN_FILE_READ_ATTRIBUTES
    | _WIN_WRITE_DAC
    | _WIN_WRITE_OWNER
    | _WIN_GENERIC_ALL_ACCESS
    | _WIN_GENERIC_EXECUTE_ACCESS
    | _WIN_GENERIC_WRITE_ACCESS
    | _WIN_GENERIC_READ_ACCESS
)

# Well-known SIDs whose presence in a DACL never breaks owner-only privacy: the
# machine's LocalSystem and the local Administrators group are root-equivalent
# (they can access every file regardless of ACL, so refusing them would be
# security theatre), and CREATOR OWNER / OWNER RIGHTS resolve to the file's own
# owner.  Every *other* SID that is granted a visibility bit -- Everyone
# (S-1-1-0), Users (S-1-5-32-545), Authenticated Users (S-1-5-11), a different
# user account, ... -- is a foreign grant and refused.
# The only symlinked ancestors tolerated by :func:`is_canonical_absolute_path`,
# enumerated rather than inferred: macOS ships /var, /tmp and /etc as symlinks
# into /private, so every canonical temporary or cache path on that OS crosses
# one.  A tolerated alias must still resolve exactly where the OS says it does;
# a symlink that merely shares one of these names anywhere else is refused.
#
# What this does NOT establish: that a tolerated name is genuinely the OS's own.
# The table checks the name and its target, not the mount or its owner, so a
# bind mount, an alternate mount namespace or a chroot could present a different
# /var -- and any ancestor could in principle be swapped AFTER it was inspected,
# since this predicate answers about the moment it ran and not for all time.
# Both are outside what a path predicate can enforce; callers needing a stronger
# answer hold a pinned DirHandle rather than re-resolving a name.
_SYSTEM_PATH_ALIASES = {
    "/var": "/private/var",
    "/tmp": "/private/tmp",
    "/etc": "/private/etc",
}

_WELL_KNOWN_PRIVACY_SAFE_SIDS = frozenset(
    {
        "S-1-5-18",      # LocalSystem
        "S-1-5-32-544",  # BUILTIN\\Administrators
        "S-1-3-0",       # CREATOR OWNER (resolves to the owner)
        "S-1-3-4",       # OWNER RIGHTS
    }
)

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

    ``reverify_before_use`` is the load-bearing honesty field.  It is ``False``
    only for the kernel ``memfd`` seal, which even the owning process cannot undo,
    so the sealed bytes are immutable for the descriptor's life and need no
    re-check.  It is ``True`` for the non-memfd read-only fallback, because the
    read-only attribute is *reversible by the owner* (or another same-user
    process): between this hash and any later use the bytes can be made writable
    and replaced.  A ``True`` value is a contract, not a hint -- the caller MUST
    re-hash the file against ``sha256`` immediately before it hands the path to a
    subprocess (see :func:`reverify_sealed_before_exec`) and fail closed on any
    mismatch; the read-only mode alone is defence-in-depth, not the guarantee.
    """

    sealed: bool
    read_only: bool
    mechanism: str
    sha256: str
    reverify_before_use: bool = True


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


# The Linux-only ``memfd`` write-seal constants from <linux/fcntl.h>.  macOS *has*
# :mod:`fcntl` but not these (they are a Linux kernel feature) and Windows has no
# ``fcntl`` at all.  Named once so the advertised gate (:func:`supports_sealed_memfd`)
# and the fail-closed enforcement (:func:`_require_seal_fcntl`) can never drift.
_MEMFD_SEAL_ATTRS = (
    "F_ADD_SEALS",
    "F_GET_SEALS",
    "F_SEAL_GROW",
    "F_SEAL_SEAL",
    "F_SEAL_SHRINK",
    "F_SEAL_WRITE",
)


def _require_seal_fcntl() -> ModuleType:
    """Return :mod:`fcntl` only when it carries the ``memfd`` write-seal constants.

    The seal primitives (:func:`write_seal_mask`, :func:`read_seals`,
    :func:`add_seals`) read ``fcntl.F_SEAL_*`` / ``F_GET_SEALS`` / ``F_ADD_SEALS``,
    which exist only on Linux.  ``fcntl`` itself imports fine on macOS but lacks
    them, so touching one raises an opaque ``AttributeError: module 'fcntl' has no
    attribute 'F_GET_SEALS'`` instead of this module's fail-closed contract.
    Routing every such access through here means the absent constant is never
    touched: the seal path is unreachable unless the support
    :func:`supports_sealed_memfd` advertises is genuinely present, and where it is
    not this raises the same typed :class:`RuntimeError` the missing-``fcntl`` path
    (Windows) already raises -- never a silent skip.  On Linux the constants are
    present, so this returns the identical ``fcntl`` the primitives used before and
    their behaviour is byte-for-byte unchanged.
    """

    fcntl = _require_fcntl()
    if not all(hasattr(fcntl, name) for name in _MEMFD_SEAL_ATTRS):
        raise RuntimeError(
            "This operation requires the Linux memfd write-seal constants "
            "(F_ADD_SEALS / F_GET_SEALS / F_SEAL_*), which this platform's fcntl "
            "does not provide; kernel write seals are unavailable here"
        )
    return fcntl


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
    # The reverse conversion plus the membership test, used to answer "is the
    # SID that owns this object an identity my own token holds?" -- the question
    # an elevated process must ask, because Windows stamps its new files
    # BUILTIN\Administrators rather than with the user SID.
    advapi32.ConvertStringSidToSidW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.ConvertStringSidToSidW.restype = boolean
    advapi32.CheckTokenMembership.argtypes = [
        handle,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
    ]
    advapi32.CheckTokenMembership.restype = boolean
    # GetAce(PACL, DWORD index, LPVOID *pAce): fills a pointer to the ACE at
    # ``index`` *inside* the DACL, used by the owner-only privacy check to walk
    # every ACE and refuse a foreign visibility grant.
    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        dword,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetAce.restype = boolean
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


def _windows_token_sid(information_class: int, label: str) -> str:
    """One SID out of the current process token (TokenUser or TokenOwner).

    ``TOKEN_USER`` and ``TOKEN_OWNER`` both begin with the ``PSID`` we want -- the
    former as the first member of a ``SID_AND_ATTRIBUTES``, the latter on its own
    -- so a single reader serves both classes.
    """

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
            token, information_class, None, 0, ctypes.byref(size)
        )
        if size.value == 0:
            raise OwnershipCheckError(
                f"Win32 reported an empty process-token {label} record"
            )
        buffer = ctypes.create_string_buffer(size.value)
        if not api.advapi32.GetTokenInformation(
            token, information_class, buffer, size.value, ctypes.byref(size)
        ):
            raise OwnershipCheckError(
                f"Win32 refused to read the current process-token {label}"
            )
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents
        return _windows_string_sid(api, sid)
    finally:
        api.kernel32.CloseHandle(token)


def _windows_current_user_sid() -> str:
    """The user SID of the process token, i.e. "who am I" on Windows."""

    return _windows_token_sid(_TOKEN_USER_CLASS, "user")


def _windows_token_holds_sid(sid_text: str) -> bool:
    """Whether the current process token carries ``sid_text`` as an identity.

    ``CheckTokenMembership(NULL, sid, ...)`` asks Windows the question that
    matters here: is the account this process is running as a member of the
    group that owns the object?  It is needed because an elevated process's new
    files are frequently stamped ``BUILTIN\\Administrators`` -- an identity the
    token genuinely holds, but which is neither its ``TokenUser`` nor its
    ``TokenOwner`` SID.  Returns ``False``, never raises, when the SID cannot be
    converted or the membership cannot be established: an unanswerable
    membership question is not a match.
    """

    try:
        api = _windows_security_api()
    except OwnershipCheckError:
        return False
    convert = getattr(api.advapi32, "ConvertStringSidToSidW", None)
    check = getattr(api.advapi32, "CheckTokenMembership", None)
    if convert is None or check is None:
        return False
    sid = ctypes.c_void_p()
    try:
        if not convert(ctypes.c_wchar_p(sid_text), ctypes.byref(sid)):
            return False
    except (OSError, TypeError, ValueError):
        return False
    try:
        member = ctypes.c_int(0)
        if not check(None, sid, ctypes.byref(member)):
            return False
        return bool(member.value)
    except (OSError, TypeError, ValueError):
        return False
    finally:
        free = getattr(api.kernel32, "LocalFree", None)
        if free is not None:
            try:
                free(sid)
            except OSError:
                pass


def _windows_default_owner_sid() -> str | None:
    """The token's ``TokenOwner``: the SID Windows stamps on objects we create.

    For an ordinary token this is the user SID.  For an *elevated* token it is
    ``BUILTIN\\Administrators`` -- Windows' own answer to "who owns what this
    process creates" -- which is why a file this process just made can come back
    owned by a SID that is not the user SID.  Returns ``None`` if the token
    cannot be read, so the caller falls back to the user SID alone rather than
    treating an unanswerable question as a match.
    """

    try:
        return _windows_token_sid(_TOKEN_OWNER_CLASS, "owner")
    except OwnershipCheckError:
        return None


def _windows_owner_sid(
    *,
    fd: int | None = None,
    path: str | os.PathLike[str] | None = None,
    win_handle: int | None = None,
) -> str:
    """The owner SID of a held Win32 handle, an open descriptor, or a named path.

    ``win_handle`` (preferred, and the strongest) is a raw Win32 ``HANDLE`` this
    module already holds open -- a :class:`DirHandle`'s pinned directory handle --
    so ``GetSecurityInfo`` interrogates the very object that is pinned, with no
    reopen and no name resolution in between.  ``fd`` is a CRT descriptor,
    translated to its Win32 handle; it is race-free for the same reason.  ``path``
    is a last resort that resolves the name afresh through ``GetNamedSecurityInfoW``
    and is therefore *not* bound to any handle the caller validated -- a caller
    that needs handle-bound identity must supply ``win_handle`` or ``fd``.
    """

    api = _windows_security_api()
    owner = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    if win_handle is not None:
        # The object we already hold pinned: GetSecurityInfo on the HANDLE, never
        # a fresh name resolution, so the owner answered for is exactly the pinned
        # inode -- the race a path lookup would reopen is closed.
        status = api.advapi32.GetSecurityInfo(
            ctypes.c_void_p(win_handle),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION,
            ctypes.byref(owner),
            None,
            None,
            None,
            ctypes.byref(descriptor),
        )
    elif fd is not None:
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
            "an owner-SID lookup needs a held handle, a descriptor or a path"
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


# ---------------------------------------------------------------------------
# Windows DACL privacy: does this directory's ACL restrict access to me alone?
#
# The confidentiality of a Windows private cache is NOT a mode bit -- it is the
# directory's DACL.  Asserting privacy without reading that DACL (the shipped
# behaviour: a hard-coded ``profile_root_acl=True`` and an
# ``is_private_directory_mode`` that always returned ``True`` on Windows) let a
# pre-existing ``%LOCALAPPDATA%``/``%TEMP%`` directory carrying an inherited
# Everyone/Users ACE -- or a custom ``LOCALAPPDATA`` pointing at a shared tree --
# pass every check, so another account could read game-derived bytes.  These
# helpers actually query the DACL (``GetNamedSecurityInfoW`` /
# ``GetSecurityInfo`` with ``DACL_SECURITY_INFORMATION``), walk every ACE, and
# refuse if any Everyone/Users/other-account SID is granted a visibility bit.
#
# The ctypes-touching leaf (:func:`_windows_directory_dacl_aces`) is isolated and
# monkeypatchable exactly like the owner-SID leaves above, so the *decision* logic
# is exercisable under a shim on a POSIX host; the pure classifier
# (:func:`_windows_sid_is_privacy_safe`) is unit-testable directly.
# ---------------------------------------------------------------------------


class _ACL(ctypes.Structure):
    """<winnt.h> ACL header.  ``AceCount`` bounds the :func:`GetAce` walk."""

    _fields_ = [
        ("AclRevision", ctypes.c_uint8),
        ("Sbz1", ctypes.c_uint8),
        ("AclSize", ctypes.c_uint16),
        ("AceCount", ctypes.c_uint16),
        ("Sbz2", ctypes.c_uint16),
    ]


class _ACE_HEADER(ctypes.Structure):
    """<winnt.h> ACE_HEADER: ``AceType`` decides whether an ACE grants or denies."""

    _fields_ = [
        ("AceType", ctypes.c_uint8),
        ("AceFlags", ctypes.c_uint8),
        ("AceSize", ctypes.c_uint16),
    ]


class _ACCESS_ALLOWED_ACE(ctypes.Structure):
    """<winnt.h> ACCESS_ALLOWED_ACE.  The SID begins at ``SidStart``'s offset.

    Only valid for the non-object allowed/denied ACE types, whose SID immediately
    follows the mask.  Object ACEs interpose variable GUID fields before the SID,
    so they are handled conservatively (treated as an unparseable foreign grant)
    rather than misparsed here.
    """

    _fields_ = [
        ("Header", _ACE_HEADER),
        ("Mask", ctypes.c_uint32),
        ("SidStart", ctypes.c_uint32),
    ]


def _windows_security_mechanism_available() -> bool:
    """Whether a real Win32 security subsystem exists to query on this host.

    ``True`` only where ``ctypes.windll`` is present -- i.e. genuine Windows.  In
    a POSIX-hosted Windows *simulation* (:data:`IS_WINDOWS` flipped for a test)
    there is no ACL subsystem at all, so a DACL is neither queryable nor a real
    security boundary, and this returns ``False`` so the callers do not treat the
    simulation as an unenforceable real ACL.  Monkeypatchable so a shim can drive
    the real query logic on a POSIX host.
    """

    return getattr(ctypes, "windll", None) is not None


def _windows_dacl_enforced() -> bool:
    """Whether owner-only-DACL enforcement is a real, applicable boundary here.

    A thin alias for :func:`_windows_security_mechanism_available`, named for the
    call sites: the privacy verifiers enforce the DACL only when this is ``True``
    (real Windows, or a shim standing in for it), and skip enforcement in a bare
    POSIX simulation that cannot present an ACL -- never weakening a real Windows
    boundary, only avoiding a phantom refusal where no ACL exists to read.
    """

    return _windows_security_mechanism_available()


def _windows_sid_is_privacy_safe(sid: str | None, current_user_sid: str | None) -> bool:
    """Whether granting a visibility right to ``sid`` is compatible with owner-only.

    ``True`` only for the current user's own SID and the root-equivalent
    well-known SIDs in :data:`_WELL_KNOWN_PRIVACY_SAFE_SIDS`.  An unparseable SID
    (``None`` -- e.g. an object ACE whose layout this module does not decode) is
    treated as unsafe, because privacy that cannot be proven must fail closed.
    """

    if not sid:
        return False
    if current_user_sid and sid == current_user_sid:
        return True
    return sid in _WELL_KNOWN_PRIVACY_SAFE_SIDS


def _windows_directory_dacl_aces(
    *,
    fd: int | None = None,
    path: str | os.PathLike[str] | None = None,
    win_handle: int | None = None,
) -> list[tuple[int, str | None, int]] | None:
    """Read a Windows object's DACL and return its ACEs, or ``None`` if unreadable.

    Each returned tuple is ``(ace_type, sid_string_or_None, access_mask)``.  A
    ``None`` DACL (which in Windows means *everyone* has full access, the opposite
    of private) is reported as a single synthetic Everyone-allow ACE so the caller
    refuses it.  Returns ``None`` only when the DACL genuinely could not be read
    (a Win32 error, or no ``ctypes.windll``), which the caller treats as
    unqueryable and fails closed on a real boundary.  Monkeypatchable: a shim
    replaces this to drive the classifier on a POSIX host.
    """

    if not _windows_security_mechanism_available():
        return None
    api = _windows_security_api()
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    info = _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION
    if win_handle is not None:
        status = api.advapi32.GetSecurityInfo(
            ctypes.c_void_p(win_handle),
            _SE_FILE_OBJECT,
            info,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
    elif fd is not None:
        try:
            msvcrt = _require_msvcrt()
            native_handle = msvcrt.get_osfhandle(fd)
        except (RuntimeError, OSError, ValueError):
            return None
        status = api.advapi32.GetSecurityInfo(
            ctypes.c_void_p(native_handle),
            _SE_FILE_OBJECT,
            info,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
    elif path is not None:
        status = api.advapi32.GetNamedSecurityInfoW(
            os.fsdecode(path),
            _SE_FILE_OBJECT,
            info,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
    else:
        return None
    if status != _ERROR_SUCCESS:
        return None
    try:
        if not dacl.value:
            # A NULL DACL grants everyone full access: the least private state
            # possible.  Surface it as an Everyone (S-1-1-0) full-access ACE so
            # the classifier refuses it rather than reading "no ACEs" as private.
            return [(_ACCESS_ALLOWED_ACE_TYPE, "S-1-1-0", _WIN_GENERIC_ALL_ACCESS)]
        acl = ctypes.cast(dacl, ctypes.POINTER(_ACL)).contents
        aces: list[tuple[int, str | None, int]] = []
        for index in range(acl.AceCount):
            ace_pointer = ctypes.c_void_p()
            if not api.advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)):
                # A DACL we cannot fully enumerate is not provably restrictive.
                return None
            header = ctypes.cast(
                ace_pointer, ctypes.POINTER(_ACE_HEADER)
            ).contents
            ace_type = int(header.AceType)
            if ace_type == _ACCESS_ALLOWED_ACE_TYPE:
                allowed = ctypes.cast(
                    ace_pointer, ctypes.POINTER(_ACCESS_ALLOWED_ACE)
                ).contents
                sid_pointer = ctypes.c_void_p(
                    ctypes.cast(ace_pointer, ctypes.c_void_p).value
                    + _ACCESS_ALLOWED_ACE.SidStart.offset
                )
                try:
                    sid_text: str | None = _windows_string_sid(api, sid_pointer)
                except OwnershipCheckError:
                    sid_text = None
                aces.append((ace_type, sid_text, int(allowed.Mask)))
            elif ace_type == _ACCESS_ALLOWED_OBJECT_ACE_TYPE:
                # Object ACEs place variable GUID fields before the SID; rather
                # than misparse one, record it as an unparseable allowed grant so
                # the classifier fails closed on it.
                allowed = ctypes.cast(
                    ace_pointer, ctypes.POINTER(_ACCESS_ALLOWED_ACE)
                ).contents
                aces.append((ace_type, None, int(allowed.Mask)))
            elif ace_type != _ACCESS_DENIED_ACE_TYPE:
                # Everything that is not a plain DENIED ACE is treated as an
                # unparseable ALLOWED grant.  Assuming "every other ACE type only
                # restricts access" was false: the callback variants
                # (ACCESS_ALLOWED_CALLBACK_ACE, type 0x09, and its object form
                # 0x0B) DO grant rights, and skipping them silently let a foreign
                # grant through unread.  Recording them with an unparseable SID
                # makes the classifier fail closed on a DACL it cannot fully
                # decode, which is the only safe reading of one.
                allowed = ctypes.cast(
                    ace_pointer, ctypes.POINTER(_ACCESS_ALLOWED_ACE)
                ).contents
                aces.append((ace_type, None, int(allowed.Mask)))
        return aces
    finally:
        api.kernel32.LocalFree(descriptor)


@dataclass(frozen=True)
class WindowsDaclVerdict:
    """The result of reading a Windows object's DACL for owner-only privacy.

    ``mechanism_available`` is ``False`` off real Windows (no ACL subsystem to
    read).  ``queried`` is ``True`` only when a DACL was actually enumerated for
    the object.  ``restricted_to_current_user`` is the security answer -- ``True``
    only when *no* foreign SID is granted a visibility right -- and is meaningful
    only when ``queried`` is ``True``.  ``permissive_sids`` names the offending
    grants (for a diagnosable refusal) and ``detail`` carries any Win32 failure.
    """

    mechanism_available: bool
    queried: bool
    restricted_to_current_user: bool
    permissive_sids: tuple[str, ...]
    detail: str


def windows_directory_privacy(
    *,
    fd: int | None = None,
    path: str | os.PathLike[str] | None = None,
    win_handle: int | None = None,
) -> WindowsDaclVerdict:
    """Query a Windows object's DACL and judge whether it is private to this user.

    Reads the object's DACL (preferring a held ``win_handle``, then a descriptor
    ``fd``, then a ``path``), enumerates every ACE, and reports
    ``restricted_to_current_user`` ``True`` only when no Everyone/Users/other-SID
    ACE grants a read/list/traverse/write/execute right -- the real, queried
    replacement for the shipped hard-coded ``True``.  Off real Windows (no ACL
    subsystem) it reports ``mechanism_available`` ``False`` and the callers skip
    enforcement rather than refuse a simulation that has no ACL to present; on a
    real boundary an unreadable DACL is reported ``queried`` ``False`` so the
    callers fail closed.
    """

    if not _windows_security_mechanism_available():
        return WindowsDaclVerdict(
            mechanism_available=False,
            queried=False,
            restricted_to_current_user=False,
            permissive_sids=(),
            detail="no Win32 security subsystem on this host (not real Windows)",
        )
    try:
        current_sid: str | None = _windows_current_user_sid()
    except OwnershipCheckError as exc:
        current_sid = None
        current_detail = f"current-user SID unavailable: {exc}"
    else:
        current_detail = ""
    aces = _windows_directory_dacl_aces(fd=fd, path=path, win_handle=win_handle)
    if aces is None:
        return WindowsDaclVerdict(
            mechanism_available=True,
            queried=False,
            restricted_to_current_user=False,
            permissive_sids=(),
            detail=current_detail or "the object's DACL could not be read",
        )
    if current_sid is None:
        # The DACL was read, but without knowing who "I" am every allowed SID is
        # potentially foreign; fail closed rather than guess.
        return WindowsDaclVerdict(
            mechanism_available=True,
            queried=False,
            restricted_to_current_user=False,
            permissive_sids=(),
            detail=current_detail or "current-user SID unavailable",
        )
    permissive: list[str] = []
    for ace_type, sid, mask in aces:
        # Every ACE the collector kept is an allowed grant, or one whose type it
        # could not decode and recorded as an unparseable grant; plain DENIED
        # ACEs are dropped there and never reach this loop.  Re-filtering by an
        # allow-list of types here would re-open the hole the collector just
        # closed, by skipping exactly the callback ACEs it deliberately kept.
        if ace_type == _ACCESS_DENIED_ACE_TYPE:
            continue
        if not (mask & _ACCESS_MASK_CONFERS_VISIBILITY):
            continue
        if not _windows_sid_is_privacy_safe(sid, current_sid):
            permissive.append(sid or "<unparseable-allowed-ace>")
    restricted = not permissive
    return WindowsDaclVerdict(
        mechanism_available=True,
        queried=True,
        restricted_to_current_user=restricted,
        permissive_sids=tuple(permissive),
        detail=(
            "DACL restricts visibility to the current user and root-equivalent "
            "accounts"
            if restricted
            else "DACL grants visibility to foreign SIDs: "
            + ", ".join(permissive)
        ),
    )


# ---------------------------------------------------------------------------
# Win32 directory handles (kernel32).
#
# The premise "Windows has no directory descriptors" is false: CreateFileW with
# FILE_FLAG_BACKUP_SEMANTICS opens a real directory HANDLE, Windows refuses to
# rename or delete a directory while a handle to it is open (as long as the share
# mode withholds FILE_SHARE_DELETE), and GetFileInformationByHandle yields a
# stable identity (dwVolumeSerialNumber + nFileIndex{High,Low}) for it.  That is
# the Windows analogue of a POSIX O_DIRECTORY descriptor, and :class:`DirHandle`
# holds one for its lifetime so the pinned directory cannot be swapped out from
# under it.  These helpers concentrate the ctypes so the POSIX path never touches
# them and the Windows path is exercisable under a ctypes shim.
# ---------------------------------------------------------------------------

# CreateFileW dwDesiredAccess / dwShareMode / dwCreationDisposition and the
# FILE_FLAG_* / FILE_ATTRIBUTE_* bits from <winbase.h>/<winnt.h>.  Only meaningful
# on Windows; named here so the ctypes calls read like the Win32 documentation.
_WIN_GENERIC_WRITE = 0x40000000
_WIN_FILE_SHARE_READ = 0x00000001
_WIN_FILE_SHARE_WRITE = 0x00000002
_WIN_FILE_SHARE_DELETE = 0x00000004
_WIN_OPEN_EXISTING = 3
_WIN_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_WIN_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_WIN_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_WIN_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
# The pinned directory handle withholds FILE_SHARE_DELETE precisely so Windows
# refuses a rename/delete of that directory while the handle lives; it still
# shares read+write so ordinary child operations inside the directory proceed.
_WIN_DIR_PIN_SHARE_MODE = _WIN_FILE_SHARE_READ | _WIN_FILE_SHARE_WRITE

# GENERIC_READ, for the sealed-module exec pin (:func:`reverify_sealed_before_exec`).
_WIN_GENERIC_READ = 0x80000000
# READ_CONTROL from <winnt.h>: the standard right to read an object's SECURITY
# DESCRIPTOR (owner + DACL) and nothing else -- no data access whatsoever.
# GetSecurityInfo requires it on the handle it is given, so a directory handle
# opened with access 0 cannot answer the ownership question the pinned
# transactions ask of it.
_WIN_READ_CONTROL = 0x00020000
# The exec pin shares READ only -- withholding FILE_SHARE_WRITE and
# FILE_SHARE_DELETE -- so while the pin handle lives no same-user process can
# rewrite, truncate or delete THOSE BYTES, yet the subprocess (which only needs
# read) can still open it.  It is NOT the Windows analogue of handing the child
# a descriptor: it pins the file, not the NAME.  A same-user process can still
# rebind the pathname with SetFileInformationByHandle(FileRenameInfoEx,
# POSIX_SEMANTICS | REPLACE_IF_EXISTS), which succeeds even against open
# handles -- those handles keep the old file while every later open resolves to
# the replacement -- and the child opens by name.  So this narrows the
# check-to-use window rather than closing it, which is why the Windows branch
# reports SealedExecHandle.inode_pinned=False.
_WIN_EXEC_PIN_SHARE_MODE = _WIN_FILE_SHARE_READ

# CREATE_NEW is the Win32 spelling of ``O_CREAT | O_EXCL``: it fails with
# ERROR_FILE_EXISTS rather than opening or truncating an existing name, so a
# staging file created with it is exclusively ours exactly as ``mkstemp``'s is.
_WIN_CREATE_NEW = 1
_WIN_FILE_ATTRIBUTE_NORMAL = 0x00000080
_WIN_ERROR_FILE_EXISTS = 80
_WIN_ERROR_ALREADY_EXISTS = 183
# A private staging file is the one place we deliberately GRANT FILE_SHARE_DELETE
# (the pinned directory and exec pins withhold it).  Windows refuses to rename a
# file while any handle without that share bit is open, and the CRT's own
# open()/mkstemp() never sets it -- which is why the publish step failed with
# ERROR_SHARING_VIOLATION.  The descriptor is the integrity proof here: the
# publisher writes, fsyncs, stats and finally re-reads the published bytes
# *through the same descriptor*, so closing it early to placate Windows would
# drop the guarantee rather than degrade it.  Sharing delete keeps the exact
# POSIX shape -- one descriptor held across the rename -- and grants no other
# process anything it could not already do with the file's DACL.
_WIN_STAGE_SHARE_MODE = (
    _WIN_FILE_SHARE_READ | _WIN_FILE_SHARE_WRITE | _WIN_FILE_SHARE_DELETE
)


def _win_invalid_handle() -> int:
    """``INVALID_HANDLE_VALUE`` as the int a ``c_void_p`` restype returns for it."""

    return ctypes.c_void_p(-1).value


def _win_reset_last_error() -> None:
    """Zero the Win32 last-error before a call (no-op where ctypes lacks it).

    ``ctypes.set_last_error`` exists only on Windows; guarding it keeps the real
    Windows behaviour intact while letting a ctypes shim exercise these paths on a
    POSIX host, where the last-error is only used for a diagnostic message.
    """

    setter = getattr(ctypes, "set_last_error", None)
    if setter is not None:
        setter(0)


def _win_last_error() -> int:
    """The Win32 last-error after a failed call, or ``0`` where unavailable."""

    getter = getattr(ctypes, "get_last_error", None)
    return getter() if getter is not None else 0


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    """<fileapi.h> BY_HANDLE_FILE_INFORMATION, filled by GetFileInformationByHandle.

    A real :class:`ctypes.Structure` so both the genuine Win32 call and the ctypes
    shim populate the identical fields; identity is
    ``(dwVolumeSerialNumber, nFileIndexHigh << 32 | nFileIndexLow)``.
    """

    _fields_ = [
        ("dwFileAttributes", ctypes.c_uint32),
        ("ftCreationTime", _FILETIME),
        ("ftLastAccessTime", _FILETIME),
        ("ftLastWriteTime", _FILETIME),
        ("dwVolumeSerialNumber", ctypes.c_uint32),
        ("nFileSizeHigh", ctypes.c_uint32),
        ("nFileSizeLow", ctypes.c_uint32),
        ("nNumberOfLinks", ctypes.c_uint32),
        ("nFileIndexHigh", ctypes.c_uint32),
        ("nFileIndexLow", ctypes.c_uint32),
    ]


@dataclass(frozen=True)
class _WindowsKernelApi:
    """kernel32 with argtypes applied for the directory-handle primitives.

    Prepared once and cached, for the same reason as :class:`_WindowsSecurityApi`:
    leaving ``argtypes``/``restype`` unset would let ctypes truncate 64-bit
    ``HANDLE`` values to ``int`` and compare the wrong bytes.
    """

    kernel32: ctypes.CDLL


_windows_kernel_api_cache: _WindowsKernelApi | None = None


def _windows_kernel_api() -> _WindowsKernelApi:
    """Load and type the kernel32 directory-handle entry points, or fail closed.

    Raises :class:`DirectoryTransactionUnavailable` where ``ctypes.windll`` does
    not exist -- i.e. off Windows -- so a caller on the Windows branch fails closed
    rather than pretending it pinned a handle it never opened.  Monkeypatchable so
    a ctypes shim can exercise the Windows path on a POSIX host.
    """

    global _windows_kernel_api_cache
    cached = _windows_kernel_api_cache
    if cached is not None:
        return cached
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise DirectoryTransactionUnavailable(
            "Win32 directory handles require ctypes.windll, which only exists on "
            "Windows"
        )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = ctypes.c_void_p
    dword = ctypes.c_ulong
    boolean = ctypes.c_int
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,  # lpFileName
        dword,             # dwDesiredAccess
        dword,             # dwShareMode
        ctypes.c_void_p,   # lpSecurityAttributes
        dword,             # dwCreationDisposition
        dword,             # dwFlagsAndAttributes
        handle,            # hTemplateFile
    ]
    kernel32.CreateFileW.restype = handle
    kernel32.GetFileInformationByHandle.argtypes = [
        handle,
        ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION),
    ]
    kernel32.GetFileInformationByHandle.restype = boolean
    kernel32.FlushFileBuffers.argtypes = [handle]
    kernel32.FlushFileBuffers.restype = boolean
    kernel32.CloseHandle.argtypes = [handle]
    kernel32.CloseHandle.restype = boolean
    prepared = _WindowsKernelApi(kernel32=kernel32)
    _windows_kernel_api_cache = prepared
    return prepared


def _win_open_directory_handle(
    api: _WindowsKernelApi,
    path: str | os.PathLike[str],
    *,
    for_flush: bool,
    nofollow: bool,
) -> int:
    """CreateFileW a directory handle; raise :class:`OSError` if the OS refuses.

    ``for_flush`` requests ``GENERIC_WRITE`` (which ``FlushFileBuffers`` needs);
    otherwise ``READ_CONTROL`` alone, which is what
    :func:`GetFileInformationByHandle` needs (it needs no access at all) *plus*
    what ``GetSecurityInfo`` requires to read the object's owner and DACL.
    Requesting access ``0`` here was a real defect, not a tightening: the pinned
    handle is the very thing :meth:`DirHandle.describe_ownership` interrogates,
    and without ``READ_CONTROL`` that query fails for every private-cache
    transaction, which then fails closed and aborts.  ``READ_CONTROL`` conveys no
    data access -- it permits reading the security descriptor and nothing else --
    so a second, identity-only handle still coexists with the pinned one.
    ``nofollow`` adds ``FILE_FLAG_OPEN_REPARSE_POINT`` so a symlinked directory
    opens as the reparse point itself and can be refused rather than silently
    followed.
    """

    access = _WIN_GENERIC_WRITE if for_flush else _WIN_READ_CONTROL
    flags = _WIN_FILE_FLAG_BACKUP_SEMANTICS
    if nofollow:
        flags |= _WIN_FILE_FLAG_OPEN_REPARSE_POINT
    _win_reset_last_error()
    raw = api.kernel32.CreateFileW(
        os.fspath(path),
        access,
        _WIN_DIR_PIN_SHARE_MODE,
        None,
        _WIN_OPEN_EXISTING,
        flags,
        None,
    )
    handle = raw if raw is not None else 0
    if handle == 0 or handle == _win_invalid_handle():
        err = _win_last_error()
        raise OSError(
            0,
            f"CreateFileW could not open a directory handle for "
            f"{os.fspath(path)!r} (WinError {err})",
        )
    return handle


def _win_file_identity(
    api: _WindowsKernelApi, handle: int
) -> tuple[int, int, int]:
    """``(dwVolumeSerialNumber, file_index, dwFileAttributes)`` of a handle."""

    info = _BY_HANDLE_FILE_INFORMATION()
    if not api.kernel32.GetFileInformationByHandle(handle, ctypes.pointer(info)):
        err = _win_last_error()
        raise OSError(
            0, f"GetFileInformationByHandle failed (WinError {err})"
        )
    file_index = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
    return (int(info.dwVolumeSerialNumber), file_index, int(info.dwFileAttributes))


def _win_close_handle(api: _WindowsKernelApi, handle: int) -> None:
    """Best-effort ``CloseHandle``; never raises (used on cleanup paths)."""

    try:
        api.kernel32.CloseHandle(handle)
    except OSError:
        pass


def _win_open_pinned_directory(
    path: str | os.PathLike[str], *, nofollow: bool
) -> tuple[int, tuple[int, int]]:
    """Open the held directory handle and capture its identity, or refuse.

    Returns ``(handle, (volume_serial, file_index))``.  A symlinked directory
    (``nofollow`` true) is refused with :class:`DirectoryTransactionRefused`
    (``ELOOP``), a non-directory with ``ENOTDIR``.  The returned handle is held
    open by the caller for the pin's lifetime.
    """

    api = _windows_kernel_api()
    handle = _win_open_directory_handle(
        api, path, for_flush=False, nofollow=nofollow
    )
    try:
        volume, index, attrs = _win_file_identity(api, handle)
    except OSError:
        _win_close_handle(api, handle)
        raise
    if nofollow and (attrs & _WIN_FILE_ATTRIBUTE_REPARSE_POINT):
        _win_close_handle(api, handle)
        raise DirectoryTransactionRefused(
            errno.ELOOP,
            "refusing to pin a symlinked directory",
            os.fspath(path),
        )
    if not (attrs & _WIN_FILE_ATTRIBUTE_DIRECTORY):
        _win_close_handle(api, handle)
        raise DirectoryTransactionRefused(
            errno.ENOTDIR,
            "the path to pin is not a real directory",
            os.fspath(path),
        )
    return handle, (volume, index)


def _win_reverify_identity(
    path: str | os.PathLike[str],
    *,
    expected: tuple[int, int],
) -> None:
    """Refuse unless ``path`` currently resolves to the pinned handle's identity.

    Opens a fresh, short-lived handle on the *current* path and compares its
    ``(volume, file_index)`` against ``expected`` (the held handle's identity), so
    a grandparent swap that redirects the pinned realpath to a different inode is
    caught -- not merely a realpath string compare.  Raises
    :class:`DirectoryTransactionRefused` (``ESTALE``) on any mismatch, symlink, or
    disappearance.
    """

    api = _windows_kernel_api()
    try:
        handle = _win_open_directory_handle(
            api, path, for_flush=False, nofollow=True
        )
    except OSError as exc:
        raise DirectoryTransactionRefused(
            errno.ESTALE,
            f"the pinned directory is gone or unreadable: {exc}",
            os.fspath(path),
        ) from exc
    try:
        volume, index, attrs = _win_file_identity(api, handle)
    except OSError as exc:
        raise DirectoryTransactionRefused(
            errno.ESTALE,
            f"the pinned directory could not be re-identified: {exc}",
            os.fspath(path),
        ) from exc
    finally:
        _win_close_handle(api, handle)
    if (
        (attrs & _WIN_FILE_ATTRIBUTE_REPARSE_POINT)
        or not (attrs & _WIN_FILE_ATTRIBUTE_DIRECTORY)
        or (volume, index) != expected
    ):
        raise DirectoryTransactionRefused(
            errno.ESTALE,
            "the pinned directory was swapped, relinked or replaced",
            os.fspath(path),
        )


def _windows_flush_directory(
    path: str | os.PathLike[str],
    *,
    expected: tuple[int, int] | None = None,
) -> bool:
    """Flush a directory's metadata via ``FlushFileBuffers`` on a write handle.

    Returns ``True`` when the directory was genuinely flushed and ``False`` when
    the platform cannot -- no ``ctypes.windll`` at all, or the OS refuses the
    write handle (a directory whose ACL denies this account ``FILE_WRITE_DATA``).
    The ``False`` is the observable signal the caller acts on; it never pretends a
    flush that did not happen.

    ``expected`` is the ``(volume serial, file index)`` identity the caller has
    pinned.  When given, the freshly opened write handle is compared against it
    and the flush is refused on a mismatch.  Without that comparison a caller
    that had just re-verified its pin could still flush a *different* directory:
    this function resolves the name again, so an ancestor swap in between made
    ``True`` mean "some directory was committed", not "the pinned directory was
    committed".  ``nofollow`` is likewise requested so a directory symlink is
    opened as the reparse point and fails the identity comparison rather than
    being followed.
    """

    try:
        api = _windows_kernel_api()
    except DirectoryTransactionUnavailable:
        return False
    try:
        handle = _win_open_directory_handle(
            api, path, for_flush=True, nofollow=expected is not None
        )
    except OSError:
        return False
    try:
        if expected is not None:
            try:
                serial, index, _attributes = _win_file_identity(api, handle)
            except OSError:
                return False
            if (serial, index) != expected:
                return False
        return bool(api.kernel32.FlushFileBuffers(handle))
    except OSError:
        return False
    finally:
        _win_close_handle(api, handle)


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
    win_handle: int | None = None,
) -> OwnershipCheck:
    """Answer "does the account running this process own this object?".

    On POSIX this is exactly the historical check, ``info.st_uid ==
    os.getuid()``, and ``fd``/``path``/``win_handle`` are ignored: nothing about
    Linux or macOS behaviour changes.

    On Windows ``info.st_uid`` is a meaningless ``0`` for every file, so trusting
    it would convert a real guard against another user's planted cache into a
    check that always passes.  The Win32 equivalent is used instead -- the
    object's owner SID compared against the process token's user SID -- which is
    the same guarantee expressed in the platform's own ownership model.  That
    needs something to interrogate, so at least one of ``win_handle`` (preferred:
    the very handle already held pinned, queried through ``GetSecurityInfo`` with
    no name resolution), ``fd`` (a CRT descriptor, likewise race-free) or ``path``
    must be supplied; supplying none is a caller bug and raises
    :class:`OwnershipCheckError` rather than guessing.

    Residual, documented: the ``path``-only form resolves the name afresh through
    ``GetNamedSecurityInfoW`` and so is *not* bound to any handle the caller
    validated -- a name-based ownership answer, correct at the instant it is
    taken but not pinned to a specific inode.  Callers that need handle-bound
    identity (a :class:`DirHandle`) pass ``win_handle``; those with only a name
    accept that residual.

    A Win32 lookup that fails (access denied, a network filesystem with no owner
    information, a handle without ``READ_CONTROL``) is reported as *not owned*.
    That is deliberate: an unanswerable ownership question must fail closed, and
    :attr:`OwnershipCheck.detail` carries the Win32 error so the refusal is
    diagnosable.

    Known, documented difference: an owner SID is not an exact synonym for a uid.
    Windows stamps a new object's owner from the creating token's ``TokenOwner``,
    which for an *elevated* token is ``BUILTIN\\Administrators`` rather than the
    user SID -- so a file this very process just created can come back owned by a
    SID that is not its user SID.  Comparing against the user SID alone therefore
    does not "err safe": it refuses the process's own files and makes every
    private-cache operation impossible for an administrator, while proving
    nothing.  So the token's own ``TokenOwner`` is accepted as well.  That is the
    platform's real ownership model, not a relaxation of ours -- but it is a
    genuinely wider identity when the token is elevated (any administrator on the
    machine matches, though any administrator can already take ownership of
    anything), so which SID matched is spelled out in :attr:`OwnershipCheck.detail`
    rather than hidden.  Only those two SIDs are accepted; any other owner is
    still refused.
    """

    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        current_uid = getuid()
        return OwnershipCheck(
            owned=info.st_uid == current_uid,
            mechanism=OWNERSHIP_POSIX_UID,
            detail=f"st_uid={info.st_uid} current uid={current_uid}",
        )
    if fd is None and path is None and win_handle is None:
        raise OwnershipCheckError(
            "Ownership cannot be established on a platform without os.getuid "
            "unless a held handle, a descriptor or a path is supplied to "
            "interrogate"
        )
    try:
        if win_handle is not None:
            owner_sid = _windows_owner_sid(win_handle=win_handle)
        else:
            owner_sid = _windows_owner_sid(fd=fd, path=path)
        current_sid = _windows_current_user_sid()
    except OwnershipCheckError as exc:
        return OwnershipCheck(
            owned=False,
            mechanism=OWNERSHIP_WINDOWS_OWNER_SID,
            detail=f"owner SID unavailable: {exc}",
        )
    # The token's default owner, which is what Windows actually stamps on the
    # objects this process creates (see the note above).  None when the token
    # cannot be read: an unanswerable question never counts as a match.
    default_owner_sid = _windows_default_owner_sid()
    if owner_sid == current_sid:
        matched = "current user SID"
    elif default_owner_sid is not None and owner_sid == default_owner_sid:
        matched = "token default-owner SID"
    elif _windows_token_holds_sid(owner_sid):
        # An elevated process's new files are commonly stamped
        # BUILTIN\Administrators, which is neither TokenUser nor TokenOwner but
        # IS an identity this token holds.  Asking CheckTokenMembership is the
        # platform's own answer to "is this mine?"; refusing here would refuse
        # the process's own files and make the private cache unusable for an
        # administrator while proving nothing.
        matched = "token group membership"
    else:
        matched = None
    return OwnershipCheck(
        owned=matched is not None,
        mechanism=OWNERSHIP_WINDOWS_OWNER_SID,
        detail=(
            f"owner SID={owner_sid} current user SID={current_sid} "
            f"token default-owner SID={default_owner_sid} "
            f"matched={matched or 'none'}"
        ),
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


def supports_change_time_identity() -> bool:
    """Whether ``st_ctime_ns`` is a stable cross-call identity component here.

    ``True`` on POSIX (Linux and macOS), where every ``stat`` family call reads
    the same inode field: ``os.stat``, ``os.lstat``, ``os.fstat`` and a
    ``dir_fd``-relative stat of one file all report an identical ``st_ctime_ns``,
    so the guards may compare a *path* stat against an *fd* stat of the same file
    and treat a difference as proof the file changed.

    ``False`` on Windows, and this is the load-bearing platform difference.
    There a path stat and an fd stat of the *same, untouched* file do not agree
    on ``st_ctime``: the two calls reach the field through different Win32
    information classes, so the number differs while ``st_dev``, ``st_ino``,
    ``st_size`` and ``st_mtime_ns`` all still match.  A guard that puts
    ``st_ctime_ns`` in an identity tuple therefore reports "this file changed"
    for a file nothing touched -- a spurious, fail-closed refusal of the user's
    own untouched data, not a detection.  The field cannot serve as identity on
    that platform, so it is dropped there rather than compared.

    What survives the drop, and what does not, stated plainly:

    * Identity is unaffected.  Every tuple that reaches this helper carries
      ``st_dev``/``st_ino``, which are what actually answer "is this the same
      file", so a swapped, relinked or renamed-over file still fails the
      comparison.  That is an invariant of the call sites, not of this function:
      it holds because the helper is used ONLY where a path stat is compared
      against an fd stat, and every such guard in this codebase pins identity.
      A same-family comparison (path/path or fd/fd) has no divergence to work
      around and keeps its raw ``st_ctime_ns`` on every platform -- do not
      route one through here.
    * Content change is unaffected where ``st_size``/``st_mtime_ns`` are present,
      which is the usual case, so a rewritten or truncated file is still caught.
      ``st_mtime_ns`` is settable, so this detects accident and ordinary races,
      not an adversary who restores the timestamp after a same-size rewrite.
    * What is genuinely lost on Windows is the *metadata-only* change signal --
      a permission, attribute or ownership edit that leaves the bytes, the size
      and the modification time untouched.  On POSIX ``st_ctime_ns`` catches
      that.  Windows DOES maintain an equivalent (``ChangeTime`` in
      ``FILE_BASIC_INFO``, distinct from ``LastWriteTime``), but Python does not
      surface it: ``os.stat`` there reports the creation time in ``st_ctime``,
      deprecated since 3.12 in favour of ``st_birthtime``.  Reading ``ChangeTime``
      would mean a Win32 call on both sides of every comparison, which nothing in
      this codebase does today.  So the signal is not unavailable on the
      platform, it is unavailable to this guard -- and until that call is made
      the check is strictly weaker on Windows.  Callers needing a
      metadata-change guarantee do not have one here.
    """

    return not IS_WINDOWS


def change_time_identity(info: os.stat_result) -> tuple[int, ...]:
    """``(info.st_ctime_ns,)`` where that field is stable, else ``()``.

    The one spelling every identity tuple in this codebase uses for its change
    time, so a tuple stays byte-identical on POSIX -- the returned one-tuple
    splices back exactly the ``info.st_ctime_ns`` element it replaced, in the
    same position -- while on Windows every tuple loses that one element and
    nothing else.  Both sides of a comparison must be built through this helper,
    or the tuples will differ in length on Windows and the guard will refuse
    everything.

    See :func:`supports_change_time_identity` for why the field is unusable on
    Windows and for the metadata-only-change signal that is lost there.
    """

    if not supports_change_time_identity():
        return ()
    return (info.st_ctime_ns,)


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
    return all(hasattr(fcntl, name) for name in _MEMFD_SEAL_ATTRS)


def write_seal_mask() -> int:
    """The full ``memfd`` write-seal set: ``GROW | SEAL | SHRINK | WRITE``.

    Exposed so a caller that must apply or re-verify kernel seals itself (the
    pinned XISO verifier seals an *executable* copy, with its own mode and hash
    contract, so it cannot reuse :func:`seal_readonly`) never has to import
    :mod:`fcntl` at module scope -- the exact portability bug this module exists
    to remove.  Fails closed where seals do not exist.
    """

    fcntl = _require_seal_fcntl()
    return (
        fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_SEAL
        | fcntl.F_SEAL_SHRINK
        | fcntl.F_SEAL_WRITE
    )


def read_seals(fd: int) -> int:
    """Report the seals currently set on ``fd`` (Linux ``F_GET_SEALS``)."""

    fcntl = _require_seal_fcntl()
    return fcntl.fcntl(fd, fcntl.F_GET_SEALS)


def add_seals(fd: int, seals: int) -> None:
    """Apply ``seals`` to ``fd`` and prove they stuck, or fail closed.

    The read-back is not paranoia: ``F_ADD_SEALS`` silently succeeds on a
    descriptor that was never opened ``MFD_ALLOW_SEALING`` in some kernels, and
    an unsealed "sealed" copy is precisely the integrity hole these seals exist
    to close.
    """

    fcntl = _require_seal_fcntl()
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

    Windows non-atomicity caveat: :func:`os.pread` is a single positional syscall,
    but the Windows fallback is ``lseek`` + ``read`` + ``lseek``-restore, which is
    *not* atomic with respect to the descriptor's file position.  Under a
    descriptor shared between threads or processes a concurrent seek/read could
    interleave and read from -- or leave -- the wrong offset.  This is safe only
    because every shipped caller drives a single-owner, synchronous descriptor (a
    file this process just opened and reads sequentially); it is not a
    general-purpose positional primitive on Windows.  Guard the descriptor with a
    lock before sharing it across owners.
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

    Windows non-atomicity caveat: like :func:`pread`, the Windows fallback is
    ``lseek`` + ``write`` + ``lseek``-restore and is *not* atomic with respect to
    the descriptor's position, so it is positional only under a single-owner,
    synchronous descriptor -- exactly what every shipped caller uses.  Guard the
    descriptor with a lock before sharing it across threads or processes.
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

    Windows non-atomicity caveat: when an explicit ``offset_*`` is supplied, the
    user-space fallback routes through :func:`pread`/:func:`pwrite` and therefore
    inherits their Windows caveat -- the positional access is a seek/IO/restore
    sequence that is not atomic against the descriptor's position.  As with those
    helpers this is safe only because every shipped caller drives single-owner,
    synchronous descriptors; guard a descriptor with a lock before sharing it.
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
    """Whether a *guaranteed* directory-metadata flush exists on this platform.

    POSIX exposes a directory as an ``O_RDONLY`` descriptor that ``fsync`` always
    commits, which is how a rename or hard link is made durable -- a guaranteed
    capability, so this is ``True``.  It stays ``False`` on Windows: the CRT
    refuses to ``open`` a directory and the flush there is best-effort, depending
    on whether the account can obtain the ``GENERIC_WRITE`` directory handle
    ``FlushFileBuffers`` needs.  That best-effort attempt still runs -- see
    :func:`fsync_directory`, whose bool return (``True`` when the flush genuinely
    happened) is the authority for a specific directory; this function reports
    only whether the flush is a guaranteed platform primitive, which on Windows it
    is not.
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

    ``follow_symlinks=False`` refuses to flush through a symlink on every
    platform.  On POSIX it adds ``O_NOFOLLOW``.  Windows has no ``O_NOFOLLOW`` and
    ``os.open`` follows a reparse point there, so the refusal is enforced by
    identity instead: the name is ``lstat``-ed first and refused with
    :class:`DurabilityError` if it is a symlink, and after the file is opened the
    opened object's ``(st_dev, st_ino)`` is compared against that pre-open
    ``lstat`` -- a link swapped in during the window, which ``os.open`` would
    silently follow, resolves to a different identity and is refused rather than
    published.  A file whose identity cannot be established on either side fails
    closed.  This closes the gap where a caller that opened "without following"
    then hard-linked the result could publish a swapped target.

    Raises :class:`DurabilityError` on Windows when the file carries the
    read-only attribute, because that attribute makes the writable open -- and
    hence any flush at all -- impossible there.  Clearing the attribute behind
    the caller's back would momentarily un-protect a file the caller
    deliberately hardened, so this fails loudly instead.  No shipped call site
    flushes an already-read-only file: every one of them flushes a private
    staging file (mode ``0o600``/``0o644``) *before* it is sealed or published.
    """

    flags = _flush_open_flags(follow_symlinks=follow_symlinks)
    enforce_windows_nofollow = IS_WINDOWS and not follow_symlinks
    link_identity: tuple[int, int] | None = None
    if enforce_windows_nofollow:
        # Windows os.open has no O_NOFOLLOW, so catch a symlink by identity: refuse
        # a link outright, and pin the pre-open (st_dev, st_ino) to compare against
        # the opened object below.
        link_info = os.lstat(path)
        if stat.S_ISLNK(link_info.st_mode):
            raise DurabilityError(
                f"Refusing to flush {os.fspath(path)!r}: it is a symlink and "
                "follow_symlinks=False, but Windows has no O_NOFOLLOW so the open "
                "would follow it"
            )
        link_identity = (link_info.st_dev, link_info.st_ino)
    try:
        # open_no_follow is a real non-following open on both platforms: POSIX
        # O_NOFOLLOW, and on Windows CreateFileW(FILE_FLAG_OPEN_REPARSE_POINT)
        # plus an attribute check on the opened handle.  The previous
        # lstat-then-os.open-then-fstat sequence could not deliver that: a link
        # planted in the window was followed, and the fstat then described the
        # target rather than the traversal, so follow_symlinks=False was not
        # actually enforced there.
        descriptor = (
            open_no_follow(path, flags)
            if not follow_symlinks
            else os.open(path, flags)
        )
    except PermissionError as exc:
        if not IS_WINDOWS:
            raise
        raise DurabilityError(
            f"Cannot flush {os.fspath(path)!r} to disk: Windows needs a writable "
            "handle for FlushFileBuffers, and this file is marked read-only"
        ) from exc
    try:
        if link_identity is not None:
            opened = os.fstat(descriptor)
            # Identity equality alone does not prove no traversal happened: a
            # racer can rename the target aside and drop a link with the original
            # name pointing at it, so os.open follows a NEW link and still lands
            # on the SAME inode.  The opened object's own attributes settle it,
            # and they also catch the non-symlink reparse tags (junctions, mount
            # points) that S_ISLNK never reports.
            attributes = getattr(opened, "st_file_attributes", 0)
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if attributes and reparse_flag and attributes & reparse_flag:
                raise DurabilityError(
                    f"{os.fspath(path)!r} resolved to a reparse point, which "
                    "follow_symlinks=False refuses"
                )
            if not (link_identity[1] and opened.st_ino):
                raise DurabilityError(
                    f"Cannot prove {os.fspath(path)!r} was not a reparse point: "
                    "this filesystem reports no file identity"
                )
            if (opened.st_dev, opened.st_ino) != link_identity:
                raise DurabilityError(
                    f"{os.fspath(path)!r} was followed through a reparse point "
                    "or swapped between the check and the open"
                )
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

    On Windows the CRT cannot ``os.open`` a directory, but Win32 can: a directory
    handle from ``CreateFileW(FILE_FLAG_BACKUP_SEMANTICS)`` opened with
    ``GENERIC_WRITE`` accepts ``FlushFileBuffers``, which commits the directory's
    metadata.  This attempts exactly that and returns ``True`` when the flush
    genuinely happened.  It returns ``False`` -- the honest, observable signal a
    caller acts on, never a pretended success -- where the platform cannot: no
    ``ctypes.windll`` at all, or an ACL that denies this account the write handle
    ``FlushFileBuffers`` requires.  The bool return, not
    :func:`supports_directory_fsync`, is the authority on whether a given
    directory was committed: the latter still reports the *guaranteed* POSIX
    primitive and stays ``False`` on Windows, where the flush is best-effort.
    """

    if IS_WINDOWS:
        return _windows_flush_directory(path)
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


def available_bytes(path: str | os.PathLike[str]) -> int:
    """Free bytes usable by this user on the filesystem holding ``path``.

    ``os.statvfs`` is POSIX-only, so the capacity pre-checks route through here.
    :func:`shutil.disk_usage` computes ``f_bavail * f_frsize`` on POSIX -- the
    same conservative "available to an unprivileged user" figure the statvfs call
    sites used, so the Linux number is unchanged -- and calls
    ``GetDiskFreeSpaceExW`` on Windows, which likewise reports the space
    available to the *calling user* (quota-aware), not the raw volume free space.
    """

    return shutil.disk_usage(os.fspath(path)).free


# ---------------------------------------------------------------------------
# Private paths: create, harden, and re-verify "only this user may read this".
#
# One place decides what privacy means per platform, so no call site has to.
# Ownership ("does this belong to me?") is a *separate* question answered by
# :func:`describe_ownership`; a complete guard on a cache directory asks both.
# ---------------------------------------------------------------------------


def _is_link_or_reparse(info: os.stat_result) -> bool:
    """Whether ``info`` describes a symlink (POSIX) or any reparse point (Windows).

    On POSIX this is exactly ``stat.S_ISLNK(info.st_mode)`` and nothing more, so
    Linux and macOS behaviour is byte-for-byte unchanged.  On Windows a directory
    **junction** is a reparse point that ``lstat`` does *not* report as a symlink
    (``S_ISLNK`` is ``False``), so the historical ``S_ISLNK``-only guard let a
    junction planted as a private cache redirect derived bytes and lock files to a
    shared or attacker-controlled tree.  ``os.lstat`` exposes ``st_reparse_tag`` on
    Windows -- non-zero for a junction, a symlink, or any other reparse point --
    which is the reliable signal (``Path.is_junction`` reads the same field), so a
    non-zero tag is refused here in addition to ``S_ISLNK``.  The attribute is
    absent on POSIX, where ``getattr(..., 0)`` yields ``0`` and this stays a pure
    ``S_ISLNK`` test.
    """

    if stat.S_ISLNK(info.st_mode):
        return True
    return getattr(info, "st_reparse_tag", 0) != 0


def is_reparse_point(path: str | os.PathLike[str]) -> bool:
    """Whether ``path`` is a symlink (POSIX) or any reparse point incl. a junction (Windows).

    The path-taking companion to :func:`_is_link_or_reparse`, for callers that
    guard a directory before handing it to the private-cache machinery and must
    refuse a Windows **junction** as well as a symlink -- ``Path.is_symlink`` alone
    misses junctions, which is exactly how a junction bypasses a symlink-only
    check.  Returns ``False`` (rather than raising) when the path cannot be
    ``lstat``-ed, so a caller pairs it with an existence check; a genuine
    inability to inspect a path is not the same question as "is it a link".
    """

    try:
        return _is_link_or_reparse(os.lstat(path))
    except OSError:
        return False


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


def is_private_directory_mode(
    info: os.stat_result,
    *,
    fd: int | None = None,
    path: str | os.PathLike[str] | None = None,
    win_handle: int | None = None,
) -> bool:
    """Whether a directory satisfies this platform's owner-only privacy.

    This is the portable replacement for the ``info.st_mode & 0o077 == 0`` guard
    the private-cache directory checks used to assert inline -- "no group or other
    access at all".  It answers the same question with each platform's real
    mechanism, and never as a silent skip:

    * POSIX: byte-for-byte ``info.st_mode & 0o077 == 0``, ignoring the Windows-only
      locators.  Group and other must carry no access bit; the kernel enforces it,
      and this is exactly the confidentiality the ``0o700`` cache directories rely
      on.  Linux and macOS behaviour is unchanged.
    * Windows: a directory has no mode there -- it always reports ``0o777`` -- so
      that number is not a privacy signal.  Confidentiality is the directory's
      **DACL**, so this now *queries it* (via a ``win_handle``, an ``fd`` or a
      ``path``) through :func:`windows_directory_privacy` and returns ``True`` only
      when the DACL genuinely restricts access to the current user and
      root-equivalent accounts -- no Everyone/Users/other-account visibility grant.
      A permissive or unreadable DACL, or no locator to read one from, returns
      ``False`` (fail closed): the shipped hard-coded ``True`` is gone.  Where no
      real ACL subsystem exists (a POSIX-hosted Windows simulation) the DACL is
      not a real boundary and cannot be read, so this returns ``True`` for the
      simulation exactly as before -- the enforcement applies on a real Windows
      host, where ``ctypes.windll`` is present.
    """

    if privacy_guarantee().posix_mode_privacy:
        return info.st_mode & 0o077 == 0
    if not _windows_dacl_enforced():
        return True
    verdict = windows_directory_privacy(fd=fd, path=path, win_handle=win_handle)
    return verdict.queried and verdict.restricted_to_current_user


def is_private_file_mode(info: os.stat_result) -> bool:
    """Whether a private (writable) file's mode satisfies this platform's privacy.

    The portable replacement for the ``info.st_mode & 0o077 == 0`` guard the
    private-inventory / staging-file checks used to assert inline:

    * POSIX: byte-for-byte ``info.st_mode & 0o077 == 0`` -- the ``0o600`` staging
      and inventory files, with no group or other access.
    * Windows: owner-write is the only permission bit that platform honours, so
      the same private file reads back exactly ``0o666`` (:func:`private_file_mode`).
      That honest value is asserted -- proving the file is a normal, writable
      private file rather than one left read-only (which on Windows cannot even be
      deleted) -- while its confidentiality comes from the cache root's ACL,
      exactly as :func:`verify_private_file` does.  Never a silent skip: the mode
      is still checked, against the number that platform actually produces.
    """

    if privacy_guarantee().posix_mode_privacy:
        return info.st_mode & 0o077 == 0
    return stat.S_IMODE(info.st_mode) == private_file_mode()


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


def is_canonical_absolute_path(
    path: str | os.PathLike[str],
    expected_resolved: str | os.PathLike[str],
) -> bool:
    """Whether ``path`` is absolute and canonically identical to ``expected_resolved``.

    This is the portable replacement for the ``p.absolute() == p.resolve()``
    idiom the audio-source guards used to assert "the caller passed an
    already-canonical, absolute directory, not a relative path, a ``..``-laden
    one, or one redirected through a symlink".  That idiom is correct on Linux but
    *spuriously rejects* legitimate canonical paths on the other two platforms,
    because it compares an **un**-resolved form against a **resolved** one:
    :meth:`~pathlib.Path.absolute` never expands symlinks or short names, while
    :meth:`~pathlib.Path.resolve` does.

    * macOS keeps per-user temporary and cache directories under ``/var``, which
      is a symlink to ``/private/var``.  ``resolve()`` expands it and
      ``absolute()`` does not, so the two forms of a perfectly canonical cache
      path differ and the equality check fails.
    * Windows exposes 8.3 short names (``RUNNER~1``) that ``resolve()`` expands to
      their long form (``runneradmin``) while ``absolute()`` leaves untouched,
      with the same spurious result.

    The security intent is preserved *and* restored.  Realpath-ing both sides is
    what tolerates the two legitimate expansions above, but on its own it also
    silently *accepts* a symlinked or ``..``-laden root the old idiom rejected --
    because it canonicalises the very redirection it should refuse.  So three
    properties the old ``absolute()==resolve()`` enforced are asserted again,
    without re-breaking macOS/Windows:

    * absolute (never relative);
    * already canonically spelled -- ``os.path.normpath(text) == text`` -- so a
      ``..`` or ``.`` component, or a non-normalised spelling, is refused (a
      canonical path is unchanged by ``normpath``; a ``..``-laden one is not);
    * reached through no symlink the caller controls -- the final component is
      ``lstat``-ed and refused if it is a symlink (the redirected *root*), and so
      is any ancestor that ``path`` shares name-for-name with its own realpath
      (the user-controlled tail).  The *leading* divergence between ``path`` and
      its realpath -- exactly a macOS ``/var -> /private/var`` system alias or a
      Windows 8.3 ``RUNNER~1 -> runneradmin`` expansion, neither of which is a
      symlink in the final or shared components -- is what the realpath equality
      is here to tolerate, so it is not walked.

    ``realpath`` (not ``Path.resolve(strict=True)``) keeps a not-yet-existing but
    canonically-placed target comparable instead of raising: a leaf that does not
    exist is not a symlink, so it passes the ``lstat`` check.  Legitimate paths
    still pass on Linux, macOS and Windows; a relative, ``..``-laden or
    symlink-rooted path is refused.

    Linux is NOT byte-identical to the pre-port behaviour here, and the change is
    deliberate: the original matching-tail walk stopped at the first name
    divergence and therefore never inspected a symlinked ancestor whose name
    differed from its target's, which an independent audit demonstrated.  Every
    lexical ancestor is now inspected, so some paths Linux used to accept are
    refused.  That is the behaviour this function always documented; the walk
    simply did not deliver it.
    """

    text = os.fspath(path)
    if not os.path.isabs(text):
        return False
    if os.path.normpath(text) != text:
        return False
    real_path = os.path.realpath(text)
    real_expected = os.path.realpath(os.fspath(expected_resolved))
    if os.path.normcase(real_path) != os.path.normcase(real_expected):
        return False
    # Refuse a symlinked leaf -- the redirected root the realpath comparison alone
    # would accept.  A not-yet-existing leaf, an 8.3 short name or a /var-style
    # system alias is a real object rather than a link and is tolerated.
    try:
        if stat.S_ISLNK(os.lstat(text).st_mode):
            return False
    except FileNotFoundError:
        pass
    except OSError:
        return False
    # Refuse a symlink among the ancestors path shares, name for name, with its
    # own realpath (the user-controlled tail); stop at the leading divergence,
    # which is the system alias / short-name expansion the equality tolerates.
    #
    # Every lexical ancestor is inspected -- not a tail walk that stops at the
    # first name divergence.  That walk had two holes an independent audit
    # demonstrated: ``/home/me/cache -> /home/me/private`` diverges at
    # ``cache`` vs ``private`` and the loop exited BEFORE ever lstat-ing
    # ``cache``, and a symlink merely outside ``$HOME`` was tolerated outright,
    # so ``/srv/a/cache -> /srv/b/cache`` passed.  Neither is acceptable: the
    # question is not where a symlink sits relative to a home directory, it is
    # whether a symlink is on the path at all.
    #
    # The single exception is the handful of aliases the OS itself ships and
    # owns, which are enumerated rather than inferred: macOS resolves /var,
    # /tmp and /etc into /private, so EVERY canonical macOS temporary or cache
    # path crosses one and refusing them would refuse the platform.  An
    # enumerated alias is tolerated only when it still resolves where that OS
    # says it should; anything else -- including a symlink of the same NAME
    # somewhere else -- is refused.  Creating a real /var requires the
    # privilege this check could not defend against in any case.
    system_aliases = _SYSTEM_PATH_ALIASES if IS_MACOS else ()
    p_parts = Path(text).parts
    for index in range(len(p_parts), 0, -1):
        prefix = str(Path(*p_parts[:index]))
        try:
            linked = stat.S_ISLNK(os.lstat(prefix).st_mode)
        except FileNotFoundError:
            continue
        except OSError:
            return False
        if not linked:
            # A Windows JUNCTION is a reparse point that S_ISLNK does not
            # report, and it redirects a directory exactly as a symlink does,
            # so the scan has to ask the reparse question too or it walks
            # straight through one.
            if IS_WINDOWS and is_reparse_point(prefix):
                return False
            continue
        normalised = os.path.normcase(prefix)
        expected = system_aliases.get(normalised) if system_aliases else None
        if expected is None:
            return False
        try:
            if os.path.normcase(os.path.realpath(prefix)) != expected:
                return False
        except OSError:
            return False
    return True


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

    Windows: the ``mode=0o700`` is passed deliberately, not ignored -- Python
    3.13+ translates it into a security descriptor that restricts the new
    directory to the current user and administrators, the strongest primitive the
    platform offers at creation.  Where that translation is absent (an older
    interpreter) the directory instead inherits the per-user profile root's ACL.
    Either way creation alone is not trusted: :func:`harden_private_directory` and
    the ``verify_private_*`` helpers query the resulting DACL and fail closed if it
    is not actually owner-only, so ``exist_ok=True`` reusing a pre-existing
    directory with a permissive inherited ACE cannot slip through.
    """

    Path(path).mkdir(
        mode=POSIX_PRIVATE_DIRECTORY_MODE,
        parents=parents,
        exist_ok=exist_ok,
    )


def harden_private_directory(path: str | os.PathLike[str]) -> None:
    """Force an existing directory to the platform's private permissions, and verify.

    POSIX: ``chmod 0o700`` -- byte for byte the historical call, and the step
    that defeats a permissive ``umask`` or a directory created by an older build.

    Windows: ``os.chmod`` cannot set an ACL there (it toggles only the read-only
    attribute, which confers no privacy and makes a directory harder to delete),
    so hardening is instead a *verification*: the directory's DACL is queried and
    this raises :class:`PrivatePathError` unless it genuinely restricts access to
    the current user and root-equivalent accounts -- fail closed on a permissive
    or unreadable ACL rather than the shipped silent no-op that let an inherited
    Everyone/Users ACE stand.  A newly created directory is expected to satisfy
    this (``create_private_directory`` passes ``mode=0o700``, which Python 3.13+
    translates to a current-user/admin-only ACL, and ``%LOCALAPPDATA%`` inherits
    one on every supported build); a pre-existing directory with a permissive ACL
    is refused here.  Where no real ACL subsystem exists (a POSIX-hosted Windows
    simulation) there is nothing to verify and this returns, exactly as before.
    """

    if IS_WINDOWS:
        if not _windows_dacl_enforced():
            return
        verdict = windows_directory_privacy(path=path)
        if not (verdict.queried and verdict.restricted_to_current_user):
            raise PrivatePathError(
                f"Cannot confirm an owner-only ACL on {os.fspath(path)!r}: "
                f"{verdict.detail}"
            )
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

    Checked on Windows instead of the (meaningless) mode: the directory's **DACL**
    genuinely restricts access to the current user and root-equivalent accounts.
    Every directory there reports ``0o777`` and the number means nothing, but its
    ACL does, so this queries it (:func:`windows_directory_privacy`, via the held
    ``fd`` when supplied, else the path) and raises unless it is owner-only -- no
    Everyone/Users/other-account visibility grant.  That, not a mode, is the
    confidentiality guarantee, and it is verified here rather than assumed: a
    pre-existing cache directory carrying an inherited permissive ACE is refused.
    The non-reparse check above additionally stops a child being redirected out of
    the protected tree by a symlink **or a junction**.  Where no ACL subsystem
    exists (a POSIX-hosted Windows simulation) there is nothing to query and the
    DACL step is skipped; on a real Windows host ``ctypes.windll`` is present and
    it runs.  :func:`privacy_guarantee` reports the difference so a caller or a
    test asserts the platform-appropriate expectation instead of skipping it.
    """

    info = _lstat_private(path, label, fd=fd)
    if not stat.S_ISDIR(info.st_mode) or _is_link_or_reparse(info):
        raise PrivatePathError(
            f"{label} must be a real, non-link directory (nor, on Windows, a "
            f"reparse point such as a junction) at {os.fspath(path)!r}"
        )
    if privacy_guarantee().posix_mode_privacy:
        observed = stat.S_IMODE(info.st_mode)
        if observed != POSIX_PRIVATE_DIRECTORY_MODE:
            raise PrivatePathError(
                f"{label} must be an owner-only, mode-0700 directory at "
                f"{os.fspath(path)!r}; it is mode 0o{observed:o}"
            )
    elif _windows_dacl_enforced():
        verdict = windows_directory_privacy(fd=fd, path=os.fspath(path))
        if not (verdict.queried and verdict.restricted_to_current_user):
            raise PrivatePathError(
                f"{label} must be restricted to the current user by its DACL at "
                f"{os.fspath(path)!r}; {verdict.detail}"
            )
    return info


def verify_private_root_placement(path: str | os.PathLike[str], label: str) -> None:
    """Assert a private *tree root* sits where this OS makes it private.

    This is the Windows half of the privacy contract and the reason
    :func:`verify_private_directory` does not assert a mode there: a cache root
    created under :func:`user_private_root` (``%LOCALAPPDATA%``) inherits an ACL
    that excludes other accounts, and every file and directory created beneath it
    inherits that ACL in turn.

    Placement alone is necessary but not sufficient, and asserting it *alone* was
    the hole: a pre-existing ``%LOCALAPPDATA%`` subtree carrying an inherited
    Everyone/Users ACE, or a custom ``LOCALAPPDATA`` pointed at a shared tree
    (where the candidate simply *is* the "trusted" root), satisfied the containment
    test while granting other accounts access.  So on Windows this now also
    **queries the root's DACL** (:func:`windows_directory_privacy`) and raises
    unless it genuinely restricts access to the current user and root-equivalent
    accounts -- the ACL the placement check only ever *assumed* is now read and
    enforced, and being the root itself buys no free pass.  Where no ACL subsystem
    exists (a POSIX-hosted Windows simulation) the DACL cannot be read and only the
    placement check runs, exactly as before; on a real Windows host both run.

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
    if not os.path.exists(path):
        # A root that has not been created yet has no DACL to read, and
        # "unreadable" must not be conflated with "readable and permissive":
        # that would make this raise for every first run, before the very
        # directory whose ACL it wants to inspect exists.  Placement -- all that
        # can be asserted about a name -- has been asserted above, and the ACL
        # itself is established at creation by :func:`create_private_directory` /
        # :func:`harden_private_directory` and re-checked by
        # :func:`verify_private_directory` on every subsequent open.
        return
    if _windows_dacl_enforced():
        verdict = windows_directory_privacy(path=os.fspath(path))
        if not (verdict.queried and verdict.restricted_to_current_user):
            raise PrivatePathError(
                f"{label} at {os.fspath(path)!r} is placed under the profile root "
                f"but its DACL does not restrict access to the current user; "
                f"{verdict.detail}"
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
    if not stat.S_ISREG(info.st_mode) or _is_link_or_reparse(info):
        raise PrivatePathError(
            f"{label} must be a real, non-link regular file (nor, on Windows, a "
            f"reparse point) at {os.fspath(path)!r}"
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
    if not stat.S_ISREG(info.st_mode) or _is_link_or_reparse(info):
        raise PrivatePathError(
            f"{label} must be a real, non-link regular file (nor, on Windows, a "
            f"reparse point) at {os.fspath(path)!r}"
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
    if _is_link_or_reparse(named):
        raise PrivatePathError(
            f"{label} is a symlink or reparse point (e.g. a junction) at "
            f"{os.fspath(path)!r}; a private path is never reached through a link"
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

    On platforms without ``memfd`` seals the read-only mode is NOT an immutability
    guarantee -- it is reversible by the owner, so a same-user process can clear it
    and replace the bytes.  The honest guarantee is therefore stated in the result:
    ``sealed=False`` and ``reverify_before_use=True``.  The bytes' digest is
    returned in :attr:`SealResult.sha256`, and the caller MUST re-hash the file
    against it *immediately before every use* -- notably right before handing the
    path to a subprocess -- via :func:`reverify_sealed_before_exec`, which re-opens
    the exact file, re-hashes it, and hands back a held descriptor (and, where the
    platform allows, an exec path bound to that descriptor's inode) so a swap
    between the hash and the exec is caught.  That re-verification, not the
    reversible read-only bit, is what makes the non-memfd degradation safe.

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
            # A kernel write-seal cannot be undone even by this process, so the
            # bytes are immutable for the descriptor's life: no re-verify needed.
            reverify_before_use=False,
        )
    return SealResult(
        sealed=False,
        read_only=True,
        mechanism="chmod-readonly-reversible-rehash-before-use",
        sha256=_hash_fd(fd),
        # The read-only attribute is reversible by the owner, so this hash is only
        # a snapshot: the caller must re-hash immediately before exec.
        reverify_before_use=True,
    )


# ---------------------------------------------------------------------------
# Re-verify a non-memfd sealed file immediately before it is executed.
#
# The memfd path hands a subprocess an anonymous, kernel-write-sealed descriptor
# through /proc/self/fd, so the exact bytes verified are the exact bytes run.  The
# non-memfd fallback (macOS/Windows, or a Linux kernel without memfd) has only a
# reversible read-only file on disk: between :func:`seal_readonly`'s hash and the
# subprocess opening that path, the owner -- or another same-user process -- can
# clear the attribute and REPLACE the bytes, and the swapped bytes run.  These
# helpers close that check-to-use window: re-open the exact file, re-hash it,
# compare to the sealed digest, fail closed on any mismatch, and hold a descriptor
# (or a share-locked handle) open so the caller executes the very bytes it just
# verified -- via a path bound to that descriptor's inode where the platform
# exposes one (Linux /proc/<pid>/fd/N), or a deny-write/deny-delete share lock
# that forbids replacement for the handle's lifetime (Windows).  macOS has neither
# a cross-process fd path nor a mandatory share lock, so its residual is named
# honestly rather than hidden.
# ---------------------------------------------------------------------------

# Names for the exec-pin mechanisms.  Public because the guarantee differs between
# them and a caller or test is entitled to assert which one is in force.
SEALED_EXEC_PROCFS_INODE_PIN = "procfs-fd-inode-pin"
SEALED_EXEC_REVERIFIED_PATH = "reverified-path-residual-window"
SEALED_EXEC_WINDOWS_SHARE_PIN = "windows-share-deny-write-delete"


class SealedExecHandle:
    """A re-verified sealed module held open for the instant it is executed.

    Returned by :func:`reverify_sealed_before_exec`.  ``exec_path`` is the path the
    caller hands the subprocess; ``sha256`` is the digest it was re-verified
    against (equal to the sealed digest, or the call would have failed closed).
    ``inode_pinned`` is the load-bearing field: ``True`` means opening
    ``exec_path`` is guaranteed to yield the exact bytes verified here -- only
    Linux ``/proc/<pid>/fd/N``, which names the held descriptor's inode rather
    than any directory entry, so a post-hash swap cannot be executed at all.
    ``False`` (macOS *and* Windows) means the re-hash still ran immediately
    before exec, but the child opens a NAME and a same-user process can still
    rebind that name -- on Windows through ``FileRenameInfoEx`` with
    ``POSIX_SEMANTICS``, which replaces a name whose file has open handles.  A
    Windows share pin does forbid rewriting the bytes it holds, which is why the
    pin is still taken and reported through ``mechanism``; it simply is not the
    same guarantee as executing from a descriptor.

    The caller MUST keep this handle open until the subprocess has finished with
    the module (a blocking ``subprocess.run`` keeps it open for the child's whole
    life), then :meth:`close` it -- releasing the descriptor and, on Windows, the
    share lock.  It is a context manager for exactly that.
    """

    __slots__ = ("_fd", "_win_handle", "_owns_fd", "exec_path", "sha256", "inode_pinned", "mechanism")

    def __init__(
        self,
        *,
        fd: int | None,
        win_handle: int | None,
        owns_fd: bool,
        exec_path: str,
        sha256: str,
        inode_pinned: bool,
        mechanism: str,
    ) -> None:
        self._fd = fd
        self._win_handle = win_handle
        self._owns_fd = owns_fd
        self.exec_path = exec_path
        self.sha256 = sha256
        self.inode_pinned = inode_pinned
        self.mechanism = mechanism

    @property
    def descriptor(self) -> int:
        """The held POSIX descriptor, or ``-1`` where the pin is a Win32 handle.

        On POSIX this is the read-only descriptor whose inode ``exec_path`` names
        (via ``/proc``); on Windows the pin is a deny-share Win32 handle held
        internally and there is no POSIX descriptor, so this is ``-1``.
        """

        return self._fd if self._fd is not None else -1

    def close(self) -> None:
        """Release the held descriptor and/or Win32 share lock; idempotent."""

        if self._owns_fd and self._fd is not None:
            os.close(self._fd)
        self._fd = None
        if self._win_handle is not None:
            handle = self._win_handle
            self._win_handle = None
            _win_close_exec_pin(handle)

    def __enter__(self) -> "SealedExecHandle":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"SealedExecHandle(mechanism={self.mechanism!r}, "
            f"inode_pinned={self.inode_pinned!r}, exec_path={self.exec_path!r})"
        )


def _win_open_exec_pin(path: str) -> int:
    """Open a deny-write/deny-delete Win32 read handle on ``path``; refuse a reparse point.

    The pin the Windows branch of :func:`reverify_sealed_before_exec` holds: a
    ``CreateFileW(GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING,
    FILE_FLAG_OPEN_REPARSE_POINT)`` handle.  Sharing READ only withholds write and
    delete, so while it lives no same-user process can rewrite, truncate or
    delete the file -- pinning the exact bytes.  It does NOT pin the pathname:
    a POSIX-semantics rename can still rebind the name the subprocess opens (see
    the section header above), so this is a narrowing, not a closure.  ``FILE_FLAG_OPEN_REPARSE_POINT`` opens a symlink/junction as the reparse
    point itself, which is then refused rather than silently followed.
    Monkeypatchable so a shim can drive the Windows branch on a POSIX host.
    """

    api = _windows_kernel_api()
    _win_reset_last_error()
    raw = api.kernel32.CreateFileW(
        path,
        _WIN_GENERIC_READ,
        _WIN_EXEC_PIN_SHARE_MODE,
        None,
        _WIN_OPEN_EXISTING,
        _WIN_FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    handle = raw if raw is not None else 0
    if handle == 0 or handle == _win_invalid_handle():
        err = _win_last_error()
        raise SealIntegrityError(
            f"CreateFileW could not pin the sealed module {path!r} for execution "
            f"(WinError {err})"
        )
    try:
        _volume, _index, attrs = _win_file_identity(api, handle)
    except OSError as exc:
        _win_close_handle(api, handle)
        raise SealIntegrityError(
            f"could not identify the pinned sealed module {path!r}: {exc}"
        ) from exc
    if attrs & _WIN_FILE_ATTRIBUTE_REPARSE_POINT:
        _win_close_handle(api, handle)
        raise SealIntegrityError(
            f"refusing to execute a reparse-point (symlink/junction) sealed module "
            f"at {path!r}"
        )
    if attrs & _WIN_FILE_ATTRIBUTE_DIRECTORY:
        _win_close_handle(api, handle)
        raise SealIntegrityError(
            f"the sealed module at {path!r} is a directory, not an executable file"
        )
    return handle


def _win_close_exec_pin(handle: int) -> None:
    """Best-effort ``CloseHandle`` on an exec pin; never raises."""

    try:
        _win_close_handle(_windows_kernel_api(), handle)
    except DirectoryTransactionUnavailable:
        pass


def _posix_exec_path_for(fd: int, fallback: str, info: os.stat_result) -> tuple[str, bool, str]:
    """The path to hand a subprocess for a held descriptor, and whether it pins the inode.

    Where the kernel exposes the held descriptor's inode as a path -- Linux
    ``/proc/<pid>/fd/N`` -- and that path currently resolves to the very inode the
    descriptor holds, return it: the subprocess opens the exact verified bytes and
    a post-hash swap of the on-disk name cannot redirect it.  Otherwise (macOS,
    which has no such cross-process path) return the real path with
    ``inode_pinned`` ``False`` and the residual named -- the immediately preceding
    re-hash still ran, but the child re-opens by name.
    """

    proc_path = f"/proc/{os.getpid()}/fd/{fd}"
    try:
        proc_info = os.stat(proc_path)
    except OSError:
        return fallback, False, SEALED_EXEC_REVERIFIED_PATH
    if (proc_info.st_dev, proc_info.st_ino) == (info.st_dev, info.st_ino):
        return proc_path, True, SEALED_EXEC_PROCFS_INODE_PIN
    return fallback, False, SEALED_EXEC_REVERIFIED_PATH


def _reverify_sealed_before_exec_posix(
    target: str, expected_sha256: str, expected_size: int | None
) -> SealedExecHandle:
    """POSIX half of :func:`reverify_sealed_before_exec` (Linux + macOS)."""

    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        # O_NOFOLLOW makes a symlinked final component fail with ELOOP; a missing
        # or unreadable file fails here too.  Either way it is a fail-closed
        # refusal, surfaced as SealIntegrityError like every other mismatch.
        fd = os.open(target, flags)
    except OSError as exc:
        raise SealIntegrityError(
            f"could not open the sealed module {target!r} for pre-exec "
            f"re-verification (a symlink, a removed file, or unreadable): {exc}"
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or _is_link_or_reparse(info):
            raise SealIntegrityError(
                f"the sealed module at {target!r} is not a real regular file "
                "immediately before execution"
            )
        if expected_size is not None and info.st_size != expected_size:
            raise SealIntegrityError(
                f"the sealed module at {target!r} changed size before execution: "
                f"{info.st_size} != expected {expected_size}"
            )
        digest = _hash_fd(fd)
        if digest != expected_sha256:
            raise SealIntegrityError(
                f"the sealed module at {target!r} no longer matches its sealed hash "
                "immediately before execution: it was replaced after sealing"
            )
        exec_path, pinned, mechanism = _posix_exec_path_for(fd, target, info)
    except BaseException:
        os.close(fd)
        raise
    return SealedExecHandle(
        fd=fd,
        win_handle=None,
        owns_fd=True,
        exec_path=exec_path,
        sha256=digest,
        inode_pinned=pinned,
        mechanism=mechanism,
    )


def _reverify_sealed_before_exec_windows(
    target: str, expected_sha256: str, expected_size: int | None
) -> SealedExecHandle:
    """Windows half of :func:`reverify_sealed_before_exec`.

    Holds a deny-write/deny-delete share pin, re-hashes the pinned file through
    an ordinary read descriptor (the pin guarantees it is the same inode), and
    fails closed on any mismatch.

    ``inode_pinned`` is ``False`` here, and that is not pessimism.  The share pin
    genuinely protects the INODE: while this handle lives nothing can rewrite,
    truncate or delete those bytes.  What it does not protect is the NAME the
    child will open.  Windows ``SetFileInformationByHandle(FileRenameInfoEx)``
    with ``POSIX_SEMANTICS | REPLACE_IF_EXISTS`` can rebind a name over a file
    that has open handles: the existing handles stay attached to the old file
    while every subsequent open resolves to the replacement.  Since the child
    receives a PATH and opens it itself, a same-user process can still make it
    open different bytes -- so claiming an exec pin equivalent to a held
    descriptor would overstate what Windows enforces.  The re-hash immediately
    before launch still runs and still fails closed, exactly as on macOS, and
    :data:`SEALED_EXEC_WINDOWS_SHARE_PIN` names which mechanism produced this.
    """

    pin = _win_open_exec_pin(target)
    try:
        read_fd = os.open(
            target, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            info = os.fstat(read_fd)
            if not stat.S_ISREG(info.st_mode) or _is_link_or_reparse(info):
                raise SealIntegrityError(
                    f"the sealed module at {target!r} is not a real regular file "
                    "immediately before execution"
                )
            if expected_size is not None and info.st_size != expected_size:
                raise SealIntegrityError(
                    f"the sealed module at {target!r} changed size before "
                    f"execution: {info.st_size} != expected {expected_size}"
                )
            digest = _hash_fd(read_fd)
        finally:
            os.close(read_fd)
        if digest != expected_sha256:
            raise SealIntegrityError(
                f"the sealed module at {target!r} no longer matches its sealed hash "
                "immediately before execution: it was replaced after sealing"
            )
    except BaseException:
        _win_close_exec_pin(pin)
        raise
    return SealedExecHandle(
        fd=None,
        win_handle=pin,
        owns_fd=False,
        exec_path=target,
        sha256=digest,
        # The share pin holds the inode, not the pathname the child opens; see
        # the note above on POSIX-semantics rename.
        inode_pinned=False,
        mechanism=SEALED_EXEC_WINDOWS_SHARE_PIN,
    )


def reverify_sealed_before_exec(
    path: str | os.PathLike[str],
    expected_sha256: str,
    *,
    expected_size: int | None = None,
) -> SealedExecHandle:
    """Re-open and re-hash a non-memfd sealed file immediately before executing it.

    Call this from the non-memfd (``sealed=False`` / ``reverify_before_use=True``)
    path right before handing ``path`` to a subprocess.  It re-opens the exact file
    refusing a symlink or junction, ``fstat``s it, re-hashes the bytes *through the
    held descriptor* and fails closed with :class:`SealIntegrityError` unless the
    digest equals ``expected_sha256`` (and the size equals ``expected_size`` when
    given) and the object is a real regular file -- so a swap or rewrite performed
    after :func:`seal_readonly` is caught here instead of executed.

    On success it returns a :class:`SealedExecHandle` holding the file open.  Hand
    the subprocess :attr:`SealedExecHandle.exec_path`, keep the handle open until
    the subprocess has finished (a blocking ``subprocess.run`` does this), then
    close it.  Where :attr:`SealedExecHandle.inode_pinned` is ``True`` the child
    opens the exact verified inode -- only the Linux ``/proc`` fd path, which
    names a descriptor rather than a directory entry.  Where it is ``False``
    (macOS *and* Windows) the re-hash still ran immediately before exec but the
    child re-opens by NAME, and a same-user process can rebind that name, a
    residual the field states rather than hides.  This helper is for the non-memfd
    fallback only -- the Linux memfd path already executes from a sealed
    ``/proc/self/fd`` descriptor and needs no re-hash.
    """

    target = os.fspath(path)
    if IS_WINDOWS:
        return _reverify_sealed_before_exec_windows(
            target, expected_sha256, expected_size
        )
    return _reverify_sealed_before_exec_posix(
        target, expected_sha256, expected_size
    )


# ---------------------------------------------------------------------------
# Atomic, no-clobber publication.
#
# The private source-audio inventory, the replacement-template ZIP and folder,
# the aggregate validation report and the build output all end the same way: a
# fully staged, verified file or folder is made to appear at its final name in a
# single step that MUST refuse to overwrite anything already there.  On Linux
# that step is a Linux-only kernel primitive -- ``renameat2(RENAME_NOREPLACE)``
# for a staged name, or ``O_TMPFILE`` + ``linkat(AT_EMPTY_PATH)`` (spelled
# ``os.link`` through ``/proc/self/fd``) for an anonymous stage.  Both are absent
# on macOS and Windows, where the shipped publishers failed closed with a
# "cannot publish ... atomically" error.
#
# These helpers concentrate that OS-primitive layer so every publisher keeps its
# own fail-closed checks unchanged and only *how the name appears* differs:
#
#   * Linux keeps ``renameat2(RENAME_NOREPLACE)`` and the ``O_TMPFILE`` stage
#     byte for byte -- the identical ctypes call, the identical
#     ``os.link('/proc/self/fd/N', ...)`` publish -- so the suite proves nothing
#     about Linux behaviour changed.
#   * macOS / any POSIX kernel or filesystem without ``renameat2`` publishes a
#     FILE with ``os.link(staging, destination)``: that call is atomic and raises
#     ``FileExistsError`` when the destination already exists, which *is* an
#     atomic no-replace on one filesystem, after which the staging name is
#     unlinked so the published inode carries the single link ``renameat2`` would
#     have left.  It publishes a FOLDER with macOS ``renameatx_np(RENAME_EXCL)`` --
#     a single atomic exclusive rename that fails ``EEXIST`` if the destination
#     exists, the genuine directory analogue of ``renameat2(RENAME_NOREPLACE)``,
#     reported ``atomic_no_clobber=True``.  ONLY where that primitive is absent
#     (a Linux filesystem without ``renameat2``, or a macOS volume that rejects
#     ``RENAME_EXCL``) does it fall back to reserving the name with ``os.mkdir``
#     -- atomic, ``FileExistsError`` if the name exists -- and then
#     ``os.rename``-ing the staged folder onto that placeholder: two steps with an
#     observable empty placeholder in between, so that fallback is reported
#     ``atomic_no_clobber=False`` rather than pretending to be a single atomic
#     no-clobber.  The anonymous stage becomes a private ``O_EXCL`` temp file
#     created in the destination's own directory (same filesystem), so the later
#     ``os.link`` publish is a same-filesystem link.
#   * Windows has neither primitive and cannot open a directory descriptor, but
#     its own ``os.rename`` already refuses to overwrite an existing destination
#     (unlike POSIX, where it would clobber a file), so a path-based file or
#     folder is published with a single ``os.rename`` -- atomic and no-clobber.
#     (The POSIX ``mkdir``-reserve fallback below is the one mechanism that is
#     neither; it says so through ``atomic_no_clobber=False``.)
#     A publish that can only be addressed through a directory descriptor is
#     genuinely impossible on Windows and fails closed with
#     :class:`NoReplacePublishUnavailable`, never by silently degrading to a
#     path-based publish that would drop the ``dir_fd`` anti-swap guarantee.
#
# Which mechanism ran is returned in :class:`NoReplacePublication`, exactly so a
# caller or a test can assert the guarantee that is actually in force on the
# running platform.  No branch below ever overwrites an existing destination.
# ---------------------------------------------------------------------------

# ``AT_FDCWD`` and ``RENAME_NOREPLACE`` from <fcntl.h>/<linux/fs.h>: used only by
# the Linux ctypes primitive, declared here so it reads like the kernel headers.
_PUBLISH_AT_FDCWD = -100
_RENAME_NOREPLACE = 1

# ``AT_FDCWD`` (Darwin's value is -2, NOT Linux's -100) and ``RENAME_EXCL`` from
# macOS <sys/fcntl.h>/<stdio.h>: used only by the macOS ctypes primitive.
# ``renameatx_np(from, to, RENAME_EXCL)`` is a single atomic rename that fails
# with ``EEXIST`` if the destination exists -- a genuine atomic no-clobber, unlike
# the mkdir-reserve + rename dance it replaces for directory publishes.
_DARWIN_AT_FDCWD = -2
_RENAME_EXCL = 0x00000004

# renameat2 refusals that mean "this kernel/filesystem does not implement
# RENAME_NOREPLACE" -- not a real fault -- so the portable primitive is used
# instead.  Every other errno (EEXIST, EXDEV, EACCES, ...) is meaningful and is
# translated or re-raised, never swallowed.
_RENAMEAT2_UNSUPPORTED_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "ENOSYS", None),
        getattr(errno, "EINVAL", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOTTY", None),
    )
    if value is not None
)

# renameatx_np refusals that mean "this macOS volume/filesystem does not
# implement RENAME_EXCL" -- not a real fault -- so the caller falls back to the
# (honestly non-atomic) mkdir-reserve.  EEXIST is meaningful and handled
# separately; every other errno is re-raised, never swallowed.
_RENAMEATX_UNSUPPORTED_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOSYS", None),
        getattr(errno, "EINVAL", None),
    )
    if value is not None
)

# Whether ``os.link`` accepts a non-default ``follow_symlinks`` here.  It does on
# Linux; on macOS the ``linkat`` no-follow path is not exposed, and passing
# ``follow_symlinks=False`` there raises ``NotImplementedError``.  The staging
# name a publish links is always a regular file this process just created under a
# pinned directory descriptor -- never a symlink -- so on a platform without the
# flag the default (follow) link is exactly as safe; the flag is passed only for
# the extra belt-and-suspenders refusal where the platform supports it.
_LINK_SUPPORTS_FOLLOW_SYMLINKS = os.link in getattr(
    os, "supports_follow_symlinks", frozenset()
)

# Names for the publication mechanisms.  Public because the guarantee differs
# between them and every caller or test is entitled to assert which one ran.
PUBLISH_LINUX_RENAMEAT2 = "linux-renameat2-noreplace"
PUBLISH_LINUX_O_TMPFILE_LINKAT = "linux-o-tmpfile-linkat"
PUBLISH_POSIX_LINK = "posix-link-then-unlink"
PUBLISH_POSIX_MKDIR_RESERVE = "posix-mkdir-reserve-then-rename"
PUBLISH_MACOS_RENAMEX_EXCL = "macos-renamex-np-exclusive"
PUBLISH_WINDOWS_RENAME = "windows-rename-noreplace"

# Names for the two private-staging mechanisms :func:`open_private_stage` uses.
STAGE_LINUX_O_TMPFILE = "linux-o-tmpfile-anonymous"
STAGE_POSIX_NAMED_TEMP = "posix-exclusive-named-temp"

# Names for the two mechanisms :func:`create_private_staging_file` uses.  Public
# for the same reason: a caller or test is entitled to assert which one ran.
STAGING_FILE_POSIX_MKSTEMP = "posix-mkstemp"
STAGING_FILE_WINDOWS_SHARE_DELETE = "windows-create-new-share-delete"


class NoReplacePublishUnavailable(RuntimeError):
    """No atomic no-clobber publish mechanism exists for this request here.

    Raised only when the running platform genuinely cannot honour the guarantee
    with the standard library -- concretely, a Windows publish that can only be
    addressed through a directory descriptor, because Windows cannot open one.
    It is never raised merely to signal a *weaker* guarantee (that is reported in
    :class:`NoReplacePublication`), and it is never a silent skip: the caller
    turns it into its own fail-closed "cannot publish" error, exactly as it did
    before a portable path existed.
    """


@dataclass(frozen=True)
class NoReplacePublication:
    """Outcome of a no-clobber publish, with the mechanism that produced it.

    ``mechanism`` is one of the ``PUBLISH_*`` constants and says how the name was
    made to appear.  ``kind`` is ``"file"`` or ``"directory"``.

    ``atomic_no_clobber`` is the load-bearing field and is *not* uniformly
    ``True``.  It is ``True`` only where a single atomic operation both publishes
    and refuses a pre-existing destination -- ``renameat2(RENAME_NOREPLACE)`` on
    Linux, macOS ``renameatx_np(RENAME_EXCL)``, ``os.link`` for a file (fails
    ``FileExistsError``), or Windows ``os.rename`` (which natively refuses an
    existing destination).  It is ``False`` for the
    :data:`PUBLISH_POSIX_MKDIR_RESERVE` directory fallback (a Linux filesystem
    without ``renameat2``, or a macOS volume without ``RENAME_EXCL``): that path
    reserves the name with ``os.mkdir`` and then ``os.rename``\\ s the staged
    folder onto the placeholder in two steps, so a concurrent reader can observe
    the empty placeholder.  It is not a *single* atomic no-clobber step, and --
    this is the part an earlier revision of this docstring got wrong -- it is
    not unconditionally no-overwrite either: ``os.rename`` replaces an empty
    destination directory, so a same-user racer that removes the reserved
    placeholder and installs its own in the remaining window IS overwritten.
    The placeholder identity is re-checked immediately before the swap and every
    observed replacement is refused, but that check cannot be made atomic with
    the rename.  ``False`` here therefore means "do not rely on no-clobber":
    a caller whose correctness depends on it must branch on this field and
    refuse, rather than treat a successful return as proof.  ``detail`` records the per-mechanism nuance for
    diagnostics and logs; never branch on it.
    """

    mechanism: str
    kind: str
    atomic_no_clobber: bool
    detail: str


@dataclass(frozen=True)
class PrivateStage:
    """A private staging descriptor opened for a later no-clobber publish.

    ``descriptor`` is an open, writable ``0o600`` file on the same filesystem as
    its eventual destination.  ``staging_name`` is ``None`` when the stage is an
    anonymous Linux ``O_TMPFILE`` (nothing to unlink, and ``link_count`` is
    ``0``) and otherwise the relative name of an ``O_EXCL`` temp file the caller
    must unlink if it abandons the publish (``link_count`` is ``1``).
    ``mechanism`` is :data:`STAGE_LINUX_O_TMPFILE` or
    :data:`STAGE_POSIX_NAMED_TEMP`.
    """

    descriptor: int
    staging_name: str | None
    mechanism: str
    link_count: int


# ---------------------------------------------------------------------------
# Portable directory-transaction handles.
#
# A seventh platform difference, and the sharpest anti-race one: the private-
# cache transactions never address their working directory by *path*.  They open
# the parent directory once as a descriptor
# (``os.open(dir, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)``) and then
# perform every step -- ``stat``, ``open``, ``mkdir``, ``link``, ``rename``,
# ``unlink``, ``rmdir`` -- *relative to that descriptor* with ``dir_fd=``.  That
# pins the operations to a specific directory **inode**: an attacker who swaps or
# relinks the parent *path* between a check and the use that follows it (a classic
# TOCTOU race) still cannot redirect the operation, because the kernel resolves it
# against the pinned inode, not the mutated name.  It is a real, kernel-enforced
# anti-race, anti-symlink guarantee.
#
# The CRT cannot open a directory descriptor on Windows -- ``os.open`` on a
# directory raises ``PermissionError`` and ``dir_fd=`` is unsupported on every
# ``os`` function (``os.supports_dir_fd`` is empty), so the shipped ``dir_fd``
# code cannot run.  But the premise "Windows has no directory handles" is false:
# Win32 ``CreateFileW(FILE_FLAG_BACKUP_SEMANTICS)`` opens a real directory HANDLE,
# and while it is held (share mode withholding ``FILE_SHARE_DELETE``) Windows
# refuses to rename or delete THAT directory -- which restores the anti-swap pin
# for the directory itself.
#
# :func:`open_dir_handle` returns a :class:`DirHandle` that concentrates the
# difference so no call site has to know it:
#
#   * POSIX: the handle wraps a real directory descriptor opened exactly as the
#     call sites did by hand, and every at-operation is the identical ``dir_fd=``
#     call.  The kernel-enforced inode pin is unchanged and Linux/macOS behaviour
#     is byte-for-byte what it was.
#   * Windows: the handle holds a genuine Win32 directory handle (via ctypes) for
#     its lifetime, so the kernel refuses to rename/delete the pinned directory
#     -- ``pinned_by_descriptor`` is True.  It captures that handle's
#     ``(dwVolumeSerialNumber, file-index)`` identity and on *every* at-operation
#     (a) re-verifies the current path still resolves to that held-handle identity
#     -- refusing with :class:`DirectoryTransactionRefused` on a grandparent swap,
#     relink or replacement -- (b) refuses a symlinked child (the ``O_NOFOLLOW``
#     equivalent, since Windows has no such flag), and (c) performs the step with
#     a path-based, no-clobber atomic (``os.replace`` / ``os.link`` / ``os.mkdir``).
#     What the held handle does NOT provide is an ``openat`` for the CHILD name:
#     the child lookup stays path-based (re-verified but not kernel-resolved
#     against the inode), so ``kernel_enforced_against_swap`` is False and a
#     sub-millisecond child-NAME check-to-use window remains
#     (``residual_local_race`` True) -- weaker than the POSIX pin, which a local
#     attacker already able to write inside the per-user private tree could win.
#     Which mechanism is in force is reported by :func:`directory_transaction_guarantee`
#     and :attr:`DirHandle.mechanism`, and the exact residual by that guarantee's
#     fields, so callers and tests assert the platform difference rather than
#     trust it -- exactly as :func:`describe_ownership` and
#     :func:`privacy_guarantee` already do for their guarantees.
#
# Where an at-operation's safety genuinely cannot be provided with the stdlib on
# Windows -- notably the anonymous ``O_TMPFILE`` stage, which has no named,
# pinnable equivalent -- the handle offers no method for it at all rather than a
# silently weaker one, so a caller that needs it must fail closed instead of
# degrading.  In the same spirit :attr:`DirHandle.dir_fd` raises
# :class:`DirectoryTransactionUnavailable` rather than hand back a directory
# descriptor that does not exist, and a directory publish that can only be
# addressed through a descriptor still raises :class:`NoReplacePublishUnavailable`
# (see :func:`publish_no_replace`).  Never a silent weaker path that pretends to
# be as safe.
# ---------------------------------------------------------------------------

# Names for the two directory-transaction mechanisms.  Public because the
# guarantee differs between them and every caller or test is entitled to assert
# which one ran rather than assume.
DIRHANDLE_POSIX_DIR_FD = "posix-dir-fd"
DIRHANDLE_WINDOWS_REALPATH_PIN = "windows-realpath-pin"


class DirectoryTransactionUnavailable(RuntimeError):
    """A dir_fd-relative capability does not exist on this platform.

    Raised only when the running platform genuinely cannot provide the primitive
    with the standard library -- concretely, asking a Windows realpath-pinned
    handle for the raw directory descriptor it does not have (:attr:`DirHandle.dir_fd`),
    or for the absolute path of a borrowed descriptor that was adopted without one.
    It is never raised to signal a merely *weaker* guarantee (that is reported by
    :func:`directory_transaction_guarantee`), and it is never a silent skip: the
    caller turns it into its own fail-closed error, exactly as it must when a
    transaction cannot be expressed safely here.
    """


class DirectoryTransactionRefused(OSError):
    """A realpath-pinned at-operation refused because the directory changed.

    Raised only on the Windows realpath-pin path, when the per-operation
    re-verification catches the very race the descriptor pin makes impossible on
    POSIX: the pinned directory now resolves to a different inode (it was swapped,
    relinked, deleted or replaced by a symlink), or the child named for the
    operation is itself a symlink the ``O_NOFOLLOW`` equivalent must not follow.

    It subclasses :class:`OSError` and carries a meaningful ``errno`` -- ``ESTALE``
    for a changed parent, ``ELOOP`` for a symlinked child, ``ENOTDIR`` for a child
    that is not the directory it must be -- precisely so it flows into the same
    ``except OSError`` blocks the shipped transactions already wrap their
    ``dir_fd=`` calls in, turning into each store's own "directory changed during
    X" refusal.  Tests can still assert the type and ``errno`` to prove the
    Windows pin, not a generic fault, did the refusing.
    """


@dataclass(frozen=True)
class DirectoryTransactionGuarantee:
    """Exactly what a :class:`DirHandle`'s inode pin means on the running OS.

    Read as a contract, not a description.  ``pinned_by_descriptor`` is the
    load-bearing field: when it is ``True`` (POSIX) the directory is pinned by an
    open descriptor and the kernel resolves every at-operation against that inode,
    so a swap of the parent *path* cannot redirect it -- ``kernel_enforced_against_swap``
    is ``True`` and there is no residual race.  When it is ``False`` (Windows) the
    directory is pinned by its ``realpath`` and ``(st_dev, st_ino)`` identity,
    re-verified before each operation (``reverifies_each_operation``); that refuses
    an observed swap or a symlinked child but leaves a sub-millisecond
    check-to-use window a determined local attacker inside the same per-user tree
    could still win (``residual_local_race`` is ``True``).  ``summary`` states the
    difference in words for a log line or a support report.
    """

    mechanism: str
    pinned_by_descriptor: bool
    reverifies_each_operation: bool
    refuses_symlinked_child: bool
    kernel_enforced_against_swap: bool
    residual_local_race: bool
    summary: str


def _directory_transaction_guarantee_for(windows: bool) -> DirectoryTransactionGuarantee:
    """Build the guarantee for a specific platform branch (see :func:`directory_transaction_guarantee`)."""

    if windows:
        return DirectoryTransactionGuarantee(
            mechanism=DIRHANDLE_WINDOWS_REALPATH_PIN,
            pinned_by_descriptor=True,
            reverifies_each_operation=True,
            refuses_symlinked_child=True,
            kernel_enforced_against_swap=False,
            residual_local_race=True,
            summary=(
                "Windows DOES have directory handles: CreateFileW with "
                "FILE_FLAG_BACKUP_SEMANTICS opens a real one, held for the "
                "handle's lifetime, and while it is open (share mode withholds "
                "FILE_SHARE_DELETE) Windows refuses to rename or delete THAT "
                "directory -- a kernel-enforced pin against swapping the pinned "
                "directory itself, so pinned_by_descriptor is True. Each at-op "
                "additionally re-verifies the current path resolves to the held "
                "handle's (dwVolumeSerialNumber, file-index) identity and refuses "
                "a symlinked child. That identity is the 64-bit file index from "
                "GetFileInformationByHandle, which Microsoft documents as NOT "
                "guaranteed unique on ReFS (which identifies files by 128 bits), "
                "so on a ReFS volume the re-verification is a strong check rather "
                "than a proof of non-replacement. What it CANNOT do is resolve the child name "
                "against the handle (Windows has no openat), so the child lookup "
                "stays path-based: kernel_enforced_against_swap is False and a "
                "sub-millisecond child-NAME check-to-use window remains "
                "(residual_local_race True) that a local attacker already able to "
                "write inside the per-user private tree could win. Confidentiality "
                "of that tree still comes from the per-user profile-root ACL (see "
                "privacy_guarantee)."
            ),
        )
    return DirectoryTransactionGuarantee(
        mechanism=DIRHANDLE_POSIX_DIR_FD,
        pinned_by_descriptor=True,
        reverifies_each_operation=False,
        refuses_symlinked_child=True,
        kernel_enforced_against_swap=True,
        residual_local_race=False,
        summary=(
            "POSIX pins the directory by an open O_DIRECTORY|O_NOFOLLOW descriptor; "
            "the kernel resolves every dir_fd-relative at-operation against that "
            "inode, so swapping or relinking the parent path cannot redirect it. "
            "The pin is kernel-enforced with no residual race."
        ),
    )


def directory_transaction_guarantee() -> DirectoryTransactionGuarantee:
    """State what a :class:`DirHandle` guarantees on this OS.

    Computed per call (from :data:`IS_WINDOWS`) rather than frozen at import so a
    test can flip the platform flag and assert the *other* contract without
    re-importing the module -- exactly as :func:`privacy_guarantee` does.
    """

    return _directory_transaction_guarantee_for(IS_WINDOWS)


def _directory_open_flags(*, nofollow: bool) -> int:
    """The flags a directory descriptor is opened with, as the call sites had them.

    ``O_RDONLY | O_DIRECTORY | O_CLOEXEC`` plus ``O_NOFOLLOW`` when asked.  On a
    platform missing any of these (``O_DIRECTORY``/``O_NOFOLLOW`` on Windows) the
    ``getattr`` yields ``0``, exactly as every shipped ``_DIRECTORY_OPEN_FLAGS``
    definition does, so this is a faithful single home for that idiom.
    """

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    if nofollow:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def _reject_non_component(name: str) -> str:
    """Return ``name`` if it is a single path component, else refuse.

    A Windows at-operation joins the child name onto the pinned realpath, so a
    name carrying a separator or a ``..`` would escape the pinned directory --
    the very redirection the descriptor pin makes impossible on POSIX.  Both
    Windows separators are rejected regardless of the host that runs this (the
    simulation runs on Linux), so the guard is faithful under test.
    """

    text = os.fspath(name)
    if (
        not text
        or text in (os.curdir, os.pardir)
        or "/" in text
        or "\\" in text
        or (os.sep and os.sep in text)
        or (os.altsep and os.altsep in text)
    ):
        raise DirectoryTransactionRefused(
            errno.EINVAL,
            "a realpath-pinned at-operation needs a single path component",
            text,
        )
    return text


class DirHandle:
    """A directory pinned for a sequence of race-free at-operations.

    Obtain one from :func:`open_dir_handle` (or :meth:`open_dir` for a child) and
    address every step through it -- :meth:`stat`, :meth:`open`, :meth:`mkdir`,
    :meth:`link`, :meth:`rename`, :meth:`unlink`, :meth:`rmdir`, :meth:`scandir`,
    plus :meth:`publish_no_replace`, :meth:`fsync` and the ownership helpers --
    instead of building a path and hoping it still means what it meant a moment
    ago.

    On POSIX the handle holds a real directory descriptor and every method is the
    identical ``dir_fd=``-relative call the shipped transactions made by hand, so
    Linux and macOS behaviour is byte-for-byte unchanged.  On Windows, where no
    such descriptor exists, it pins the directory by realpath and inode identity
    and re-verifies that pin (and refuses a symlinked child) before each step; see
    the module section header and :func:`directory_transaction_guarantee` for the
    exact, and deliberately weaker, guarantee that applies there.  :attr:`mechanism`
    names which one is in force.
    """

    __slots__ = (
        "_fd",
        "_realpath",
        "_identity",
        "_windows",
        "_owns_fd",
        "_win_handle",
    )

    def __init__(
        self,
        *,
        fd: int | None,
        realpath: str | None,
        identity: tuple[int, int] | None,
        windows: bool,
        owns_fd: bool,
        win_handle: int | None = None,
    ) -> None:
        self._fd = fd
        self._realpath = realpath
        self._identity = identity
        self._windows = windows
        self._owns_fd = owns_fd
        # A real Win32 directory HANDLE held for this handle's lifetime on the
        # Windows branch (None on POSIX and for a borrowed descriptor).  Holding
        # it is what makes Windows refuse to rename/delete the pinned directory,
        # and it is the object ownership and re-verification interrogate.
        self._win_handle = win_handle

    # -- construction ------------------------------------------------------
    @classmethod
    def _borrow_posix_fd(cls, fd: int) -> "DirHandle":
        """Wrap an already-open, borrowed POSIX directory descriptor.

        Used by this module's own publish helpers to route their ``dir_fd=`` at-
        operations through the same abstraction the consumers will, without taking
        ownership: :meth:`close` will *not* close a borrowed descriptor, and the
        realpath/identity are unused because the POSIX branch never consults them.
        POSIX-only by construction -- there is no borrowed handle on Windows,
        because there is no descriptor to borrow.
        """

        return cls(
            fd=fd, realpath=None, identity=None, windows=False, owns_fd=False
        )

    # -- introspection -----------------------------------------------------
    @property
    def mechanism(self) -> str:
        """:data:`DIRHANDLE_POSIX_DIR_FD` or :data:`DIRHANDLE_WINDOWS_REALPATH_PIN`."""

        return (
            DIRHANDLE_WINDOWS_REALPATH_PIN
            if self._windows
            else DIRHANDLE_POSIX_DIR_FD
        )

    @property
    def guarantee(self) -> DirectoryTransactionGuarantee:
        """The guarantee *this handle* enforces, fixed at the platform it was opened on."""

        return _directory_transaction_guarantee_for(self._windows)

    @property
    def realpath(self) -> str | None:
        """The canonical directory this handle is pinned to, or ``None`` if borrowed."""

        return self._realpath

    @property
    def dir_fd(self) -> int:
        """The raw POSIX directory descriptor, for helpers not yet routed through the handle.

        POSIX-only escape hatch.  On Windows there is no descriptor, so this fails
        closed with :class:`DirectoryTransactionUnavailable` rather than hand back
        a value that cannot exist -- a caller that needs a ``dir_fd`` must be
        migrated onto the handle's own at-operations instead.
        """

        if self._windows or self._fd is None:
            raise DirectoryTransactionUnavailable(
                "this directory handle has no POSIX descriptor (Windows realpath "
                "pin, or an already-closed handle); route the operation through "
                "the handle's own at-methods instead"
            )
        return self._fd

    def fspath(self, name: str) -> str:
        """The absolute path of a child ``name`` under the pinned directory.

        Used where an operation genuinely needs a path -- passing a name to a
        path-based helper such as :func:`is_owned_by_current_user`.  Refuses a
        borrowed handle (which has no path) with :class:`DirectoryTransactionUnavailable`,
        and, like every Windows child reference, refuses a name that is not a
        single component.
        """

        if self._realpath is None:
            raise DirectoryTransactionUnavailable(
                "a borrowed directory handle has no path to resolve a child against"
            )
        return os.path.join(self._realpath, _reject_non_component(name))

    # -- Windows pin re-verification --------------------------------------
    def _reverify(self) -> None:
        """Refuse if the pinned directory is no longer the inode we opened (Windows).

        A no-op on POSIX: the descriptor *is* the pin, so nothing is re-checked
        and the at-operation stays byte-identical.  On Windows the held Win32
        handle already makes the kernel refuse to rename or delete the pinned
        directory itself; this catches the remaining vector -- a grandparent swap
        that redirects the pinned realpath to a *different* inode -- by opening a
        fresh handle on the current path and comparing its
        (dwVolumeSerialNumber, file-index) identity against the held handle's,
        refusing on any mismatch, symlink or disappearance.  That is a genuine
        identity re-verification, not a realpath string compare.
        """

        if not self._windows:
            return
        _win_reverify_identity(self._realpath, expected=self._identity)

    def _child(self, name: str) -> str:
        """Re-verify the pin, then return the validated child path (Windows only)."""

        self._reverify()
        return os.path.join(self._realpath, _reject_non_component(name))

    def _refuse_symlinked_child(self, child: str, verb: str) -> None:
        """Refuse a child that is a symlink or junction -- the Windows ``O_NOFOLLOW`` equivalent.

        On Windows a directory **junction** is a reparse point that ``lstat`` does
        not report as a symlink, so a symlink-only refusal let a junction planted
        as a child redirect the operation out of the pinned tree; both are refused
        here (:func:`_is_link_or_reparse` reads ``st_reparse_tag``).  On POSIX this
        stays a pure symlink refusal.  The residual race the module header
        documents lives in the gap between this ``lstat`` and the operation that
        follows; it is genuine but bounded to the per-user private tree, and it is
        the reason the Windows guarantee is reported as weaker rather than equal.
        """

        try:
            info = os.lstat(child)
        except FileNotFoundError:
            return
        if _is_link_or_reparse(info):
            raise DirectoryTransactionRefused(
                errno.ELOOP,
                f"refusing to {verb} a symlinked or reparse-point child",
                child,
            )

    # -- at-operations -----------------------------------------------------
    def stat(self, name: str, *, follow: bool = False) -> os.stat_result:
        """``stat`` a child relative to the pinned directory (``lstat`` when ``follow`` is false).

        POSIX: the identical ``os.stat(name, dir_fd=fd, follow_symlinks=follow)``.
        Windows: re-verify the pin, then ``os.stat`` the joined child path.

        With ``follow=False`` a symlinked child is deliberately NOT refused: the
        call returns the link's own ``stat`` exactly as the POSIX one does, so
        the caller's ``S_ISLNK``/``S_ISREG`` check (which every consumer already
        performs) still makes the decision.  With ``follow=True`` it IS refused
        on Windows, because that form resolves the link and would hand back the
        target's ``stat`` while
        :attr:`DirectoryTransactionGuarantee.refuses_symlinked_child` claims the
        transaction refuses symlinked children -- the field has to be true of
        every method, not only of the mutating ones.
        """

        if not self._windows:
            return os.stat(name, dir_fd=self._fd, follow_symlinks=follow)
        child = self._child(name)
        if follow:
            self._refuse_symlinked_child(child, "stat")
        return os.stat(child, follow_symlinks=follow)

    def open(self, name: str, flags: int, mode: int = 0o777) -> int:
        """Open a child relative to the pinned directory; return the file descriptor.

        POSIX: the identical ``os.open(name, flags, mode, dir_fd=fd)`` -- ``flags``
        already carry the caller's ``O_NOFOLLOW``/``O_BINARY``/``O_EXCL`` as
        before.  Windows: re-verify the pin, refuse a symlinked child (the
        ``O_NOFOLLOW`` equivalent, since ``O_NOFOLLOW`` does not exist there), then
        open the joined child path.  Windows *can* open a file by path -- only a
        directory descriptor is impossible -- so the returned descriptor is a
        normal file descriptor the caller reads, ``fstat``s and closes as today.
        """

        if not self._windows:
            return os.open(name, flags, mode, dir_fd=self._fd)
        child = self._child(name)
        self._refuse_symlinked_child(child, "open")
        return os.open(child, flags, mode)

    def open_staging_child(
        self, name: str, flags: int, mode: int = 0o600
    ) -> int:
        """:meth:`open` a child that will be PUBLISHED while this fd stays open.

        Identical to :meth:`open` on POSIX -- the same ``os.open(..., dir_fd=fd)``
        call, byte for byte.  It exists because Windows refuses to rename a file
        while a handle lacking ``FILE_SHARE_DELETE`` is open on it, and the CRT
        never sets that bit: a staging file opened through :meth:`open` cannot
        later be published without first closing the descriptor that proves what
        was written.  This variant creates the child with
        ``CreateFileW(CREATE_NEW, ... | FILE_SHARE_DELETE)`` instead, so the
        held-descriptor proof survives the publish.  ``flags`` must request
        exclusive creation (``O_CREAT | O_EXCL``); anything else is a caller bug,
        because CREATE_NEW is the only Win32 disposition with those semantics.
        """

        if not self._windows:
            return self.open(name, flags, mode)
        required = os.O_CREAT | os.O_EXCL
        if flags & required != required:
            raise ValueError(
                "open_staging_child creates an exclusive new file; its flags "
                "must include O_CREAT | O_EXCL"
            )
        child = self._child(name)
        self._refuse_symlinked_child(child, "open")
        return _win_create_share_delete_child(child)

    def open_dir(self, name: str, *, nofollow: bool = True) -> "DirHandle":
        """Open a child *directory* as its own pinned :class:`DirHandle`.

        The portable form of ``os.open(child, O_DIRECTORY..., dir_fd=fd)``.  POSIX
        opens a real child descriptor relative to this one (the nested-descriptor
        pattern the containment and build stores use) and returns an owning handle
        the caller must :meth:`close`.  Windows re-verifies this handle's pin,
        refuses a symlinked or non-directory child, and returns a realpath-pinned
        child handle -- never opening a directory descriptor, which the platform
        forbids.
        """

        if not self._windows:
            flags = _directory_open_flags(nofollow=nofollow)
            child_fd = os.open(name, flags, dir_fd=self._fd)
            try:
                info = os.fstat(child_fd)
            except OSError:
                os.close(child_fd)
                raise
            child_realpath = (
                os.path.join(self._realpath, os.fspath(name))
                if self._realpath is not None
                else None
            )
            return DirHandle(
                fd=child_fd,
                realpath=child_realpath,
                identity=(info.st_dev, info.st_ino),
                windows=False,
                owns_fd=True,
            )
        child = self._child(name)
        # Open a real Win32 directory handle on the child, held for the child
        # handle's lifetime; it refuses a symlinked (nofollow) or non-directory
        # child and captures the identity future re-verifications compare against.
        handle, identity = _win_open_pinned_directory(child, nofollow=nofollow)
        return DirHandle(
            fd=None,
            realpath=child,
            identity=identity,
            windows=True,
            owns_fd=False,
            win_handle=handle,
        )

    def mkdir(self, name: str, mode: int = 0o777) -> None:
        """Create a child directory relative to the pinned directory.

        POSIX: the identical ``os.mkdir(name, mode, dir_fd=fd)``.  Windows:
        re-verify the pin, then ``os.mkdir`` the joined child path -- which, like
        POSIX, fails with :class:`FileExistsError` if the name is already taken, so
        a reserve-then-swap publish keeps what no-clobber guarantee it has (see
        :class:`NoReplacePublication`: the reserve-then-swap fallback reports
        ``atomic_no_clobber=False`` and is not unconditionally no-overwrite).
        """

        if not self._windows:
            os.mkdir(name, mode, dir_fd=self._fd)
            return
        os.mkdir(self._child(name), mode)

    def unlink(self, name: str) -> None:
        """Remove a child name relative to the pinned directory.

        POSIX: the identical ``os.unlink(name, dir_fd=fd)``.  Windows: re-verify
        the pin, then ``os.unlink`` the joined child path.  ``unlink`` removes the
        name itself and never follows it, so no symlink refusal is needed here --
        it matches the POSIX semantics exactly.
        """

        if not self._windows:
            os.unlink(name, dir_fd=self._fd)
            return
        os.unlink(self._child(name))

    def rmdir(self, name: str) -> None:
        """Remove a child directory relative to the pinned directory.

        POSIX: the identical ``os.rmdir(name, dir_fd=fd)``.  Windows: re-verify the
        pin, then ``os.rmdir`` the joined child path.
        """

        if not self._windows:
            os.rmdir(name, dir_fd=self._fd)
            return
        os.rmdir(self._child(name))

    def rename(self, src: str, dst: str) -> None:
        """Rename one child onto another within the pinned directory.

        POSIX: the identical ``os.rename(src, dst, src_dir_fd=fd, dst_dir_fd=fd)``,
        which replaces an existing ``dst`` -- the reserve-then-swap publisher
        relies on that.  Windows: re-verify the pin, then ``os.replace`` the joined
        child paths, which is the platform's replace-existing rename.  (Windows
        ``replace`` refuses a *directory* target that already contains entries;
        the no-clobber directory publish therefore routes through
        :meth:`publish_no_replace`, which uses the platform-correct primitive, not
        through this method.)
        """

        if not self._windows:
            os.rename(src, dst, src_dir_fd=self._fd, dst_dir_fd=self._fd)
            return
        self._reverify()
        os.replace(
            os.path.join(self._realpath, _reject_non_component(src)),
            os.path.join(self._realpath, _reject_non_component(dst)),
        )

    def link(self, src: str, dst: str) -> None:
        """Hard-link one child to a new child name within the pinned directory.

        POSIX: the identical ``os.link(src, dst, src_dir_fd=fd, dst_dir_fd=fd,
        follow_symlinks=False)`` where the platform exposes that flag (Linux), and
        the plain ``dir_fd`` link where it does not (macOS ``linkat`` no-follow is
        unexposed) -- the staged source is a regular file this process just
        created, never a symlink, so the follow default is exactly as safe.  Either
        way it fails with :class:`FileExistsError` if ``dst`` exists, the atomic
        no-clobber publish.  Windows: re-verify the pin, refuse a symlinked source,
        then ``os.link`` the joined child paths (which also fails if ``dst``
        exists).
        """

        if not self._windows:
            if _LINK_SUPPORTS_FOLLOW_SYMLINKS:
                os.link(
                    src,
                    dst,
                    src_dir_fd=self._fd,
                    dst_dir_fd=self._fd,
                    follow_symlinks=False,
                )
            else:
                os.link(src, dst, src_dir_fd=self._fd, dst_dir_fd=self._fd)
            return
        self._reverify()
        source = os.path.join(self._realpath, _reject_non_component(src))
        self._refuse_symlinked_child(source, "hard-link")
        os.link(source, os.path.join(self._realpath, _reject_non_component(dst)))

    def scandir(self) -> list[os.DirEntry[str]]:
        """Enumerate the pinned directory's entries, bound to the pin.

        POSIX: ``os.scandir`` on the held descriptor (``fdopendir``), so the
        enumeration is kernel-resolved against the pinned inode and cannot be
        redirected -- the race-free replacement for enumerating ``realpath`` by
        name.  Windows: re-verify the held handle's identity, then ``os.scandir``
        the pinned realpath; the check-then-enumerate gap is the same documented
        child-name residual as every other Windows at-operation (see
        :func:`directory_transaction_guarantee`).

        The entries are materialised into a list so the transient scandir handle
        is closed before returning; the caller then iterates and, for each name it
        acts on, re-addresses it through this handle (``stat``/``open``) so the
        per-entry operation is itself pinned.  A borrowed POSIX handle enumerates
        its descriptor exactly as an owning one does.
        """

        if not self._windows:
            with os.scandir(self._fd) as iterator:
                return list(iterator)
        self._reverify()
        with os.scandir(self._realpath) as iterator:
            return list(iterator)

    # -- higher-level operations routed through platform_compat ------------
    def publish_no_replace(
        self,
        staging: str,
        destination: str,
        *,
        is_directory: bool = False,
        require_atomic: bool = False,
    ) -> NoReplacePublication:
        """Publish ``staging`` to ``destination`` without overwriting an existing name.

        Atomic and unconditionally no-clobber for every mechanism EXCEPT the
        POSIX ``mkdir``-reserve directory fallback, which is two steps and
        reports ``atomic_no_clobber=False``; see :class:`NoReplacePublication`
        for what that concedes.

        POSIX: the identical ``publish_no_replace(staging, destination,
        dir_fd=fd, is_directory=...)`` -- ``renameat2(RENAME_NOREPLACE)`` where the
        kernel has it, else the link/reserve fallback, all addressed through the
        pinned descriptor.  Windows: re-verify the pin, then publish by *path*
        (``publish_no_replace`` with the joined names and no ``dir_fd``), which
        uses that platform's native no-clobber ``os.rename``.  This is why routing
        a Windows publish through the handle *succeeds* with the weaker realpath
        pin where the raw ``dir_fd`` publish had to fail closed: the safety now
        comes from the re-verified pin, and the atomicity from the path-based
        rename, instead of from a descriptor that cannot exist.
        """

        if not self._windows:
            return publish_no_replace(
                staging,
                destination,
                dir_fd=self._fd,
                is_directory=is_directory,
            require_atomic=require_atomic,
            )
        self._reverify()
        return publish_no_replace(
            os.path.join(self._realpath, _reject_non_component(staging)),
            os.path.join(self._realpath, _reject_non_component(destination)),
            dir_fd=None,
            is_directory=is_directory,
            require_atomic=require_atomic,
        )

    def fsync(self) -> bool:
        """Commit the pinned directory's entries, reporting whether that happened.

        POSIX: :func:`fsync_directory_fd` on the held descriptor -- the same single
        ``fsync`` the transactions issued -- returning ``True``.  Windows:
        re-verify the pin, then flush the pinned directory's metadata with
        ``FlushFileBuffers`` on a ``GENERIC_WRITE`` directory handle (see
        :func:`fsync_directory`), returning ``True`` when it genuinely happened and
        ``False`` where the platform cannot -- the honest, observable signal,
        never a skipped flush read as a completed one.
        """

        if self._windows:
            self._reverify()
            # Pass the pinned identity: the flush helper resolves the name
            # again, so without it a namespace swap in the documented
            # check-to-use interval would flush a different directory and still
            # report True.
            return _windows_flush_directory(
                self._realpath, expected=self._identity
            )
        return fsync_directory_fd(self._fd)

    def describe_ownership(
        self, info: os.stat_result | None = None
    ) -> OwnershipCheck:
        """Ownership of the pinned directory itself, via the platform's own model.

        Routes to :func:`describe_ownership` with the held descriptor on POSIX
        (race-free) and with the held Win32 directory HANDLE on Windows -- a
        ``GetSecurityInfo`` query on the very object pinned, tied to the handle
        rather than to a freshly resolved name -- so the historical
        ``is_owned_by_current_user(dir_info, fd=dir_fd)`` call sites keep working
        on both and neither reopens a race.  ``info`` is the directory's ``stat``
        (only POSIX consults it, for the uid comparison); when omitted it is taken
        from :meth:`fstat`.
        """

        resolved = info if info is not None else self.fstat()
        if self._windows:
            return describe_ownership(resolved, win_handle=self._win_handle)
        return describe_ownership(resolved, fd=self._fd)

    def is_owned_by_current_user(
        self, info: os.stat_result | None = None
    ) -> bool:
        """Boolean shorthand for :meth:`describe_ownership`."""

        return self.describe_ownership(info).owned

    def fstat(self) -> os.stat_result:
        """``stat`` the pinned directory itself.

        POSIX: ``os.fstat(fd)`` on the held descriptor, the identical call the
        transactions used to prove the directory they opened is still the one they
        verified.  Windows: re-verify the pin, then ``lstat`` the pinned realpath
        (which has no symlinked final component, so it is the directory's own
        ``stat``).
        """

        if not self._windows:
            return os.fstat(self._fd)
        self._reverify()
        return os.lstat(self._realpath)

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        """Release what this handle holds -- descriptor or Win32 handle; idempotent.

        POSIX: closes the directory descriptor when this handle owns one (a
        borrowed handle, :meth:`_borrow_posix_fd`, does not and is left alone).
        Windows: closes the held Win32 directory handle with ``CloseHandle`` --
        which is what *releases* the kernel's refusal to rename/delete the pinned
        directory, so it must run on cleanup.  Idempotent: a second call closes
        nothing.
        """

        if self._owns_fd and self._fd is not None:
            os.close(self._fd)
        self._fd = None
        if self._win_handle is not None:
            handle = self._win_handle
            self._win_handle = None
            try:
                _win_close_handle(_windows_kernel_api(), handle)
            except DirectoryTransactionUnavailable:
                # No Win32 API to close through (a POSIX-simulation fiction that
                # never truly opened one); nothing to release.
                pass

    def __enter__(self) -> "DirHandle":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"DirHandle(mechanism={self.mechanism!r}, "
            f"realpath={self._realpath!r})"
        )


def open_dir_handle(
    path: str | os.PathLike[str], *, nofollow: bool = True
) -> DirHandle:
    """Pin a directory for a sequence of race-free at-operations.

    POSIX: open the directory ``O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC``
    -- byte-for-byte the descriptor the shipped transactions opened by hand -- and
    return an owning :class:`DirHandle` the caller must :meth:`~DirHandle.close`
    (or use as a context manager).

    Windows: the directory cannot be opened as a descriptor, so pin it by realpath
    and inode identity instead.  ``nofollow`` is honoured against the *named* final
    component (the ``O_NOFOLLOW`` equivalent): a symlinked directory is refused
    with :class:`DirectoryTransactionRefused` rather than silently followed.  No
    directory descriptor is ever opened, so this runs where the raw ``dir_fd`` code
    raised ``PermissionError``.

    The mechanism in force is :attr:`DirHandle.mechanism`; the guarantee it carries
    is :func:`directory_transaction_guarantee`.
    """

    if IS_WINDOWS:
        original = os.fspath(path)
        # Open a genuine Win32 directory handle and hold it: while it lives Windows
        # refuses to rename/delete this directory, and its captured identity is
        # what every at-operation re-verifies against.  A symlinked final
        # component (nofollow) is refused, a non-directory too.
        handle, identity = _win_open_pinned_directory(original, nofollow=nofollow)
        realpath = os.path.realpath(original)
        return DirHandle(
            fd=None,
            realpath=realpath,
            identity=identity,
            windows=True,
            owns_fd=False,
            win_handle=handle,
        )
    flags = _directory_open_flags(nofollow=nofollow)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        realpath = os.path.realpath(path)
    except OSError:
        os.close(fd)
        raise
    return DirHandle(
        fd=fd,
        realpath=realpath,
        identity=(info.st_dev, info.st_ino),
        windows=False,
        owns_fd=True,
    )


def _macos_renameatx_np():
    """Return a typed ``renameatx_np`` callable on macOS, else ``None``.

    Isolated (and monkeypatchable) so a ctypes shim can simulate macOS while
    running on Linux.  ``renameatx_np`` is macOS-only (10.12+); the ``dir_fd``-
    relative *at* form is used so the directory-transaction publishers keep their
    descriptor pin, exactly as the Linux ``renameat2`` path does.
    """

    if not IS_MACOS:
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except OSError:
        return None
    renameatx = getattr(libc, "renameatx_np", None)
    if renameatx is None:
        return None
    renameatx.argtypes = [
        ctypes.c_int,     # int fromfd
        ctypes.c_char_p,  # const char *from
        ctypes.c_int,     # int tofd
        ctypes.c_char_p,  # const char *to
        ctypes.c_uint,    # unsigned int flags
    ]
    renameatx.restype = ctypes.c_int
    return renameatx


def _renameatx_np_excl(
    renameatx,
    staging: str,
    destination: str,
    dir_fd: int | None,
) -> bool:
    """Run ``renameatx_np(RENAME_EXCL)``; return whether it published.

    ``True`` -- the atomic exclusive rename succeeded, a genuine atomic
    no-clobber.  ``False`` -- the volume/filesystem does not implement
    ``RENAME_EXCL`` and the caller must fall back (and report
    ``atomic_no_clobber=False``).  ``FileExistsError`` -- the destination already
    existed (the no-clobber refusal).  Any other errno is re-raised as
    :class:`OSError`.
    """

    fd = _DARWIN_AT_FDCWD if dir_fd is None else dir_fd
    ctypes.set_errno(0)
    result = renameatx(
        fd,
        os.fsencode(staging),
        fd,
        os.fsencode(destination),
        _RENAME_EXCL,
    )
    if result == 0:
        return True
    value = ctypes.get_errno()
    if value == errno.EEXIST:
        raise FileExistsError(value, os.strerror(value), os.fspath(destination))
    if value in _RENAMEATX_UNSUPPORTED_ERRNOS:
        return False
    raise OSError(value, os.strerror(value), os.fspath(destination))


def _linux_renameat2():
    """Return a typed ``renameat2`` callable on Linux, else ``None``.

    Isolated (and monkeypatchable) so tests can simulate a kernel without
    ``renameat2`` -- i.e. macOS -- while running on Linux.  The lookup and the
    ``argtypes``/``restype`` wiring match the per-publisher ctypes blocks this
    consolidates, so the syscall issued on Linux is byte-for-byte the historical
    one.
    """

    if not IS_LINUX:
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except OSError:
        return None
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        return None
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    return renameat2


def _renameat2_noreplace(
    renameat2,
    staging: str,
    destination: str,
    dir_fd: int | None,
) -> bool:
    """Run ``renameat2(RENAME_NOREPLACE)``; return whether it published.

    ``True`` -- the atomic no-replace rename succeeded.  ``False`` -- the kernel
    or filesystem does not implement ``RENAME_NOREPLACE`` and the caller must use
    the portable primitive.  ``FileExistsError`` -- the destination already
    existed (the no-clobber refusal).  Any other errno is re-raised as
    :class:`OSError`, unchanged from the shipped publishers.
    """

    fd = _PUBLISH_AT_FDCWD if dir_fd is None else dir_fd
    ctypes.set_errno(0)
    result = renameat2(
        fd,
        os.fsencode(staging),
        fd,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return True
    value = ctypes.get_errno()
    if value == errno.EEXIST:
        raise FileExistsError(value, os.strerror(value), os.fspath(destination))
    if value in _RENAMEAT2_UNSUPPORTED_ERRNOS:
        return False
    raise OSError(value, os.strerror(value), os.fspath(destination))


def _publish_file_via_link(
    staging: str,
    destination: str,
    dir_fd: int | None,
) -> NoReplacePublication:
    """Publish one staged FILE with the strongest non-``renameat2`` primitive."""

    if IS_WINDOWS:
        if dir_fd is not None:
            raise NoReplacePublishUnavailable(
                "Windows cannot publish a file through a directory descriptor: "
                "it has no dir_fd, so this transaction cannot run there"
            )
        # Windows os.rename refuses to overwrite an existing destination, so it
        # is itself an atomic no-replace publish; it also consumes the staging
        # name, matching renameat2's post-state exactly.
        os.rename(staging, destination)
        return NoReplacePublication(
            mechanism=PUBLISH_WINDOWS_RENAME,
            kind="file",
            atomic_no_clobber=True,
            detail="os.rename (Windows: fails if destination exists)",
        )
    # POSIX, incl. macOS: os.link is atomic and fails with FileExistsError if the
    # destination exists -- an atomic no-replace on one filesystem -- then the
    # staging name is removed so the published inode has a single link, exactly
    # the state renameat2 would have left.  The dir_fd-relative form routes
    # through a borrowed DirHandle so this module's own publish uses the same
    # abstraction the consumers will; the borrowed handle issues the identical
    # dir_fd= link+unlink on POSIX, so Linux/macOS behaviour is byte-for-byte
    # unchanged.
    if dir_fd is not None:
        handle = DirHandle._borrow_posix_fd(dir_fd)
        handle.link(staging, destination)
        handle.unlink(staging)
    else:
        os.link(staging, destination)
        os.unlink(staging)
    return NoReplacePublication(
        mechanism=PUBLISH_POSIX_LINK,
        kind="file",
        atomic_no_clobber=True,
        detail="os.link then unlink staging (link fails if destination exists)",
    )


def _publish_directory_via_reserve(
    staging: str,
    destination: str,
    dir_fd: int | None,
    *,
    require_atomic: bool = False,
) -> NoReplacePublication:
    """Publish one staged FOLDER with the strongest non-``renameat2`` primitive."""

    if IS_WINDOWS:
        if dir_fd is not None:
            raise NoReplacePublishUnavailable(
                "Windows cannot publish a folder through a directory descriptor: "
                "it has no dir_fd, so this transaction cannot run there"
            )
        os.rename(staging, destination)
        return NoReplacePublication(
            mechanism=PUBLISH_WINDOWS_RENAME,
            kind="directory",
            atomic_no_clobber=True,
            detail="os.rename (Windows: fails if destination exists)",
        )
    # macOS: renameatx_np(RENAME_EXCL) IS a single atomic exclusive rename of the
    # staged folder -- it fails with EEXIST if the destination exists and leaves
    # no observable intermediate, so it is a genuine atomic no-clobber (the
    # mkdir-reserve below is NOT).  Preferred wherever the volume supports it.
    renameatx = _macos_renameatx_np()
    if renameatx is not None:
        if _renameatx_np_excl(renameatx, staging, destination, dir_fd):
            return NoReplacePublication(
                mechanism=PUBLISH_MACOS_RENAMEX_EXCL,
                kind="directory",
                atomic_no_clobber=True,
                detail=(
                    "renameatx_np(RENAME_EXCL): a single atomic exclusive "
                    "directory rename that fails with EEXIST if the destination "
                    "exists"
                ),
            )
        # RENAME_EXCL unsupported on this volume -> fall through to mkdir-reserve,
        # which is reported honestly as NOT a single atomic no-clobber step.
    # POSIX generic fallback (macOS without RENAME_EXCL, or a Linux filesystem
    # without renameat2).  A plain os.rename of a directory would *replace* an
    # existing empty destination, so it is not a no-replace on its own.  Reserve
    # the destination name with os.mkdir instead: that is atomic and raises
    # FileExistsError if anything is already there -- the no-clobber refusal --
    # after which os.rename swaps the staged folder onto the placeholder.  But
    # this is TWO steps with an observable empty placeholder in between, so it is
    # NOT a single atomic no-clobber publish and atomic_no_clobber is reported
    # False: a concurrent reader can observe the empty placeholder even though no
    # pre-existing destination is ever overwritten.
    # The dir_fd-relative mkdir/rename/rmdir route through a borrowed DirHandle
    # (byte-identical dir_fd= calls on POSIX), unifying this module's own publish
    # with the abstraction the consumers use.
    if require_atomic:
        # Every atomic mechanism has now been tried and none was available, so
        # what remains is the two-step reserve-then-swap.  Refuse HERE, before
        # it runs: reporting atomic_no_clobber=False on the way out is too late
        # to help a caller that cannot tolerate an overwrite, because the swap
        # has already happened by the time it reads the field.  The Windows and
        # macOS RENAME_EXCL branches above are genuine atomic no-clobber
        # publishes and are never refused by this gate.
        raise NoReplacePublishUnavailable(
            "no single atomic no-clobber directory publish is available here "
            "(this filesystem offers neither renameat2(RENAME_NOREPLACE) nor "
            "renamex_np(RENAME_EXCL)); the mkdir-reserve fallback is two steps "
            "and can overwrite a directory a concurrent process placed at the "
            "destination, so it was refused rather than run"
        )
    handle = DirHandle._borrow_posix_fd(dir_fd) if dir_fd is not None else None
    if handle is not None:
        handle.mkdir(destination, POSIX_PRIVATE_DIRECTORY_MODE)
    else:
        os.mkdir(destination, POSIX_PRIVATE_DIRECTORY_MODE)
    # Identity of the placeholder we just reserved.  os.rename REPLACES an empty
    # destination directory, so without this a racer could rmdir our placeholder,
    # create its own directory at the same name, and have it silently overwritten
    # by the swap -- the "no pre-existing destination is overwritten" promise
    # would then be false.  Re-checking immediately before the swap does not make
    # the two steps atomic (nothing available here can), but it refuses the
    # observed replacement instead of overwriting it.
    try:
        reserved = (
            handle.stat(destination, follow=False)
            if handle is not None
            else os.lstat(destination)
        )
        reserved_identity: tuple[int, int] | None = (
            reserved.st_dev,
            reserved.st_ino,
        )
    except OSError:
        reserved_identity = None
    try:
        if reserved_identity is not None:
            current = (
                handle.stat(destination, follow=False)
                if handle is not None
                else os.lstat(destination)
            )
            if (current.st_dev, current.st_ino) != reserved_identity:
                raise FileExistsError(
                    errno.EEXIST,
                    "the reserved destination was replaced by another process "
                    "before the staged folder could be swapped in",
                    destination,
                )
        if handle is not None:
            handle.rename(staging, destination)
        else:
            os.rename(staging, destination)
    except BaseException:
        # Roll back the placeholder so an abandoned publish leaves no stub.  Only
        # our own empty directory is removed; if a racer populated it (making the
        # swap fail) the rmdir fails too and the original error propagates.
        try:
            if handle is not None:
                handle.rmdir(destination)
            else:
                os.rmdir(destination)
        except OSError:
            pass
        raise
    return NoReplacePublication(
        mechanism=PUBLISH_POSIX_MKDIR_RESERVE,
        kind="directory",
        atomic_no_clobber=False,
        detail=(
            "os.mkdir reserves the name atomically (fails if it exists), then "
            "os.rename swaps the staged folder onto the placeholder. This is NOT "
            "a single atomic no-clobber step and it is NOT unconditionally "
            "no-overwrite: os.rename replaces an empty destination directory, so "
            "a same-user racer that removes the placeholder and installs its own "
            "empty directory in the remaining window CAN be overwritten. The "
            "placeholder identity is re-checked immediately before the swap, "
            "which refuses every replacement it observes, but the check cannot "
            "be atomic with the rename and a racer that wins after it still "
            "succeeds. Callers that require a true no-clobber publish must "
            "branch on atomic_no_clobber, which is False here, and refuse"
        ),
    )


def publish_no_replace(
    staging: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    dir_fd: int | None = None,
    is_directory: bool = False,
    require_atomic: bool = False,
) -> NoReplacePublication:
    """Publish ``staging`` to ``destination`` atomically, never overwriting it.

    ``require_atomic`` is for callers whose correctness depends on no-clobber:
    it refuses up front rather than falling back to the two-step
    ``mkdir``-reserve directory publish, which can overwrite a concurrently
    created destination.  Checking :attr:`NoReplacePublication.atomic_no_clobber`
    afterwards cannot substitute for it -- by then the swap has happened.

    ``staging`` is consumed exactly as ``renameat2`` would consume it: on success
    ``destination`` names the staged inode (a file with a single link, or the
    staged directory) and the staging name is gone.  When ``dir_fd`` is given,
    ``staging`` and ``destination`` are names resolved relative to that directory
    descriptor -- the ``dir_fd``-relative model the private-cache publishers use
    to pin the directory they verified; when it is ``None`` they are paths.

    Raises :class:`FileExistsError` if ``destination`` already exists -- the
    no-clobber refusal, on every platform.  One qualification, and it is the
    reason :attr:`NoReplacePublication.atomic_no_clobber` exists: the
    :data:`PUBLISH_POSIX_MKDIR_RESERVE` directory fallback (a Linux filesystem
    without ``renameat2``, or a macOS volume without ``RENAME_EXCL``) publishes
    in two steps, and a same-user racer that replaces the reserved placeholder
    between them can have its directory overwritten by the swap. That mechanism
    reports ``atomic_no_clobber=False``; a caller whose correctness depends on
    no-clobber must branch on that field rather than on this function returning
    successfully.  Raises
    :class:`NoReplacePublishUnavailable` only where the platform truly offers no
    mechanism (a Windows ``dir_fd`` publish), never as a silent clobbering
    fallback.  See the module section header for the per-OS mechanism; the one
    that ran is returned so a caller or test can assert it.
    """

    staging_name = os.fspath(staging)
    destination_name = os.fspath(destination)
    renameat2 = _linux_renameat2()
    if renameat2 is not None:
        if _renameat2_noreplace(renameat2, staging_name, destination_name, dir_fd):
            return NoReplacePublication(
                mechanism=PUBLISH_LINUX_RENAMEAT2,
                kind="directory" if is_directory else "file",
                atomic_no_clobber=True,
                detail="renameat2(RENAME_NOREPLACE)",
            )
    if is_directory:
        return _publish_directory_via_reserve(
            staging_name, destination_name, dir_fd, require_atomic=require_atomic
        )
    return _publish_file_via_link(staging_name, destination_name, dir_fd)


def no_replace_publish_mechanism(*, is_directory: bool, dir_fd: bool) -> str:
    """Name the mechanism :func:`publish_no_replace` will use here, side-effect free.

    ``dir_fd`` is whether the caller will address the publish through a directory
    descriptor.  Lets a caller or test assert the platform-appropriate guarantee
    before publishing; the value equals the ``mechanism`` the call returns.  One
    documented caveat: on macOS this predicts :data:`PUBLISH_MACOS_RENAMEX_EXCL`
    for a directory whenever ``renameatx_np`` is present, but a specific volume
    that rejects ``RENAME_EXCL`` at runtime falls back to
    :data:`PUBLISH_POSIX_MKDIR_RESERVE` -- a prediction this side-effect-free call
    cannot make without attempting the rename.
    """

    if _linux_renameat2() is not None:
        return PUBLISH_LINUX_RENAMEAT2
    if IS_WINDOWS:
        if dir_fd:
            raise NoReplacePublishUnavailable(
                "Windows cannot publish through a directory descriptor"
            )
        return PUBLISH_WINDOWS_RENAME
    if is_directory:
        if _macos_renameatx_np() is not None:
            return PUBLISH_MACOS_RENAMEX_EXCL
        return PUBLISH_POSIX_MKDIR_RESERVE
    return PUBLISH_POSIX_LINK


def open_private_stage(
    dir_fd: int,
    *,
    prefix: str,
    mode: int = POSIX_PRIVATE_FILE_MODE,
) -> PrivateStage:
    """Open a private, same-directory staging descriptor for a later publish.

    On Linux this is the anonymous ``O_TMPFILE`` the aggregate-report publisher
    used -- byte for byte -- so it has no name and no link, and is published by
    linking it out of ``/proc/self/fd`` (see :func:`publish_private_stage`).

    Where ``O_TMPFILE`` is absent (macOS, Windows) it is instead a private temp
    file created ``O_CREAT | O_EXCL`` under ``dir_fd`` -- the "stage in a private
    directory on the same filesystem then os.link" degradation -- with a
    ``0o600`` mode and one link.  It is on the same filesystem as its
    destination by construction, so the eventual publish is a same-filesystem
    link (POSIX) or rename (Windows).

    The caller owns the returned descriptor and, when ``staging_name`` is not
    ``None``, must unlink that name if it abandons the publish.
    """

    anonymous_flag = getattr(os, "O_TMPFILE", 0)
    if anonymous_flag:
        descriptor = os.open(
            ".",
            os.O_RDWR | anonymous_flag | getattr(os, "O_CLOEXEC", 0),
            mode,
            dir_fd=dir_fd,
        )
        return PrivateStage(
            descriptor=descriptor,
            staging_name=None,
            mechanism=STAGE_LINUX_O_TMPFILE,
            link_count=0,
        )
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    last_error: OSError | None = None
    for _attempt in range(64):
        candidate = f"{prefix}{os.urandom(8).hex()}.tmp"
        try:
            descriptor = os.open(candidate, flags, mode, dir_fd=dir_fd)
        except FileExistsError as exc:
            last_error = exc
            continue
        return PrivateStage(
            descriptor=descriptor,
            staging_name=candidate,
            mechanism=STAGE_POSIX_NAMED_TEMP,
            link_count=1,
        )
    if last_error is not None:
        raise last_error
    raise OSError(
        errno.EEXIST,
        "could not create a unique private staging file",
        prefix,
    )


def publish_private_stage(
    stage: PrivateStage,
    destination: str,
    *,
    dir_fd: int,
) -> NoReplacePublication:
    """Publish an :func:`open_private_stage` descriptor to ``destination``.

    For an anonymous Linux stage this is the historical ``os.link`` out of
    ``/proc/self/fd`` -- an atomic ``linkat`` that fails with
    :class:`FileExistsError` if the destination exists.  For a named stage it is
    the portable file publish (:func:`publish_no_replace`), which links the temp
    to the destination and unlinks the temp.  Either way ``destination`` ends
    with a single link to the staged bytes and no existing name is overwritten.
    """

    if stage.staging_name is None:
        try:
            os.link(
                f"/proc/self/fd/{stage.descriptor}",
                destination,
                dst_dir_fd=dir_fd,
                follow_symlinks=True,
            )
        except FileExistsError:
            raise
        return NoReplacePublication(
            mechanism=PUBLISH_LINUX_O_TMPFILE_LINKAT,
            kind="file",
            atomic_no_clobber=True,
            detail="os.link('/proc/self/fd/N', ...) (fails if destination exists)",
        )
    return publish_no_replace(
        stage.staging_name,
        destination,
        dir_fd=dir_fd,
        is_directory=False,
    )


def private_staging_file_mechanism() -> str:
    """Name the mechanism :func:`create_private_staging_file` uses here.

    Side-effect free, so a caller or test can assert the platform difference
    instead of assuming it.
    """

    return (
        STAGING_FILE_WINDOWS_SHARE_DELETE
        if IS_WINDOWS
        else STAGING_FILE_POSIX_MKSTEMP
    )


def _win_create_share_delete_child(path: str) -> int:
    """``CreateFileW(CREATE_NEW, FILE_SHARE_DELETE)`` one file, as a CRT fd.

    ``mkstemp``/``os.open`` would do everything this does except grant
    ``FILE_SHARE_DELETE``, and without that bit Windows fails the eventual
    publish with ERROR_SHARING_VIOLATION while the caller still holds the
    descriptor it wrote and verified through.  The handle is handed to the CRT
    with :func:`msvcrt.open_osfhandle`, so the returned descriptor is an ordinary
    fd: ``os.write``/``os.read``/``os.lseek``/``os.fstat``/``os.fsync`` all work
    on it and closing the fd closes the handle exactly once.

    Exclusivity is unchanged from ``O_CREAT | O_EXCL``: ``CREATE_NEW`` fails
    rather than open or truncate an existing name, and that failure is raised as
    :class:`FileExistsError` so an existing retry loop behaves identically.
    """

    msvcrt = _require_msvcrt()
    api = _windows_kernel_api()
    _win_reset_last_error()
    raw = api.kernel32.CreateFileW(
        path,
        _WIN_GENERIC_READ | _WIN_GENERIC_WRITE,
        _WIN_STAGE_SHARE_MODE,
        None,
        _WIN_CREATE_NEW,
        _WIN_FILE_ATTRIBUTE_NORMAL,
        None,
    )
    handle = raw if raw is not None else 0
    if handle == 0 or handle == _win_invalid_handle():
        err = _win_last_error()
        if err in (_WIN_ERROR_FILE_EXISTS, _WIN_ERROR_ALREADY_EXISTS):
            raise FileExistsError(errno.EEXIST, "File exists", path)
        raise OSError(
            0,
            f"CreateFileW could not create the private staging file "
            f"{path!r} (WinError {err})",
        )
    try:
        # O_NOINHERIT: the CRT descriptor is inheritable by default, and every
        # caller here asks for O_CLOEXEC on POSIX -- a staging descriptor must
        # not leak into a child process on either platform.  Nothing else may be
        # passed: _open_osfhandle rejects _O_BINARY and an access mode with
        # EBADF, taking the access mode from the handle and defaulting to binary.
        return msvcrt.open_osfhandle(handle, getattr(os, "O_NOINHERIT", 0))
    except BaseException:
        # BaseException, not OSError: open_osfhandle emits an audit event, so an
        # installed audit hook can raise anything at all here.  If ownership of
        # the handle was not transferred to the CRT, this frame still owns it and
        # must close it or leak it.
        _win_close_handle(api, handle)
        raise


_WIN_OPEN_ALWAYS = 4


def open_no_follow(
    path: str | os.PathLike[str],
    flags: int,
    mode: int = POSIX_PRIVATE_FILE_MODE,
) -> int:
    """Open ``path`` without ever traversing a symlink or reparse point.

    ``O_NOFOLLOW`` carries the entire no-follow guarantee on POSIX, and it is
    ``0`` on Windows -- so an ``os.open`` there silently follows a planted link,
    and any check made *after* that open describes the target rather than the
    traversal that reached it.  ``lstat``-then-open does not fix it either: the
    link can be planted in the window between the two, and the post-open
    ``fstat`` still reports the innocent target it was redirected to.

    So on Windows the open itself is made non-following.
    ``CreateFileW(..., FILE_FLAG_OPEN_REPARSE_POINT)`` opens a reparse point *as
    itself* rather than resolving it, and the resulting handle's own
    ``dwFileAttributes`` then says whether one was hit -- atomically, about the
    object actually opened, with no window.  If it was, the handle is closed and
    the call fails with ``ELOOP``, exactly as ``O_NOFOLLOW`` does.  POSIX takes
    the identical ``os.open`` it always took.

    On Windows the proven object is then bound to an ordinary CRT descriptor by
    comparing identities rather than by handing the Win32 handle to the CRT:
    ``_open_osfhandle`` rejects a handle opened this way with ``EBADF``, and a
    descriptor the caller cannot use would be no guarantee at all.  A racer who
    swaps the name between the two steps yields a different (volume, file index)
    and is refused; one who relinks it back to the very object just proven has
    changed nothing the caller cares about.

    Scope, precisely: this refuses a link at the FINAL component, which is what
    ``O_NOFOLLOW`` refuses and no more.  Ancestor directories are still resolved
    normally by both platforms; a caller that also needs its ancestors proven
    uses :func:`is_canonical_absolute_path` or a pinned :class:`DirHandle`.

    ``flags`` is the POSIX flag set the caller would have given :func:`os.open`,
    and on POSIX it is passed through verbatim -- including ``O_TRUNC``, which
    that branch therefore DOES honour.  The Windows branch maps only the access
    mode and the ``O_CREAT``/``O_EXCL`` disposition; ``O_TRUNC``, ``O_APPEND``
    and any other flag are not translated there.  A caller that wants behaviour
    identical on both platforms must therefore leave ``O_TRUNC`` out and empty
    the file through the returned descriptor -- which is also the safer order,
    since nothing is destroyed before the refusal can fire.
    """

    if not IS_WINDOWS:
        return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)

    try:
        api = _windows_kernel_api()
    except DirectoryTransactionUnavailable:
        # ctypes.windll always exists on a real Windows host, so reaching this
        # means IS_WINDOWS was monkeypatched True on a POSIX host to exercise
        # the Windows branch; that host's own open really does carry O_NOFOLLOW.
        # sys.platform is consulted rather than IS_WINDOWS precisely because
        # IS_WINDOWS is the mutable thing the simulation flips: on a real
        # Windows interpreter this re-raises instead of degrading, so a missing
        # primitive there fails closed and can never become a following open.
        if sys.platform.startswith("win"):
            raise
        return os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)

    write = bool(flags & (os.O_WRONLY | os.O_RDWR))
    access = _WIN_GENERIC_READ
    if write:
        access |= _WIN_GENERIC_WRITE
    if flags & os.O_CREAT and flags & os.O_EXCL:
        disposition = _WIN_CREATE_NEW
    elif flags & os.O_CREAT:
        disposition = _WIN_OPEN_ALWAYS
    else:
        disposition = _WIN_OPEN_EXISTING

    # Step 1: prove the name does not resolve through a reparse point, using an
    # open that genuinely does not follow one.  FILE_FLAG_OPEN_REPARSE_POINT
    # opens a link AS the link, so the handle's own attributes answer the
    # question about the object actually reached -- no lstat/open window.
    _win_reset_last_error()
    raw = api.kernel32.CreateFileW(
        os.fspath(path),
        access,
        _WIN_FILE_SHARE_READ | _WIN_FILE_SHARE_WRITE,
        None,
        disposition,
        _WIN_FILE_ATTRIBUTE_NORMAL | _WIN_FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    handle = raw if raw is not None else 0
    if handle == 0 or handle == _win_invalid_handle():
        err = _win_last_error()
        if err in (_WIN_ERROR_FILE_EXISTS, _WIN_ERROR_ALREADY_EXISTS):
            raise FileExistsError(errno.EEXIST, "File exists", os.fspath(path))
        raise OSError(
            0,
            f"CreateFileW could not open {os.fspath(path)!r} without following "
            f"a reparse point (WinError {err})",
        )
    try:
        serial, index, attributes = _win_file_identity(api, handle)
        if attributes & _WIN_FILE_ATTRIBUTE_REPARSE_POINT:
            raise OSError(
                errno.ELOOP,
                "refusing to follow a reparse point",
                os.fspath(path),
            )
    finally:
        _win_close_handle(api, handle)

    # Step 2: take the ordinary CRT descriptor the caller needs, then BIND it to
    # the object step 1 proved by comparing identities.  The Win32 handle is not
    # handed to the CRT: _open_osfhandle refuses handles opened this way with
    # EBADF, and a descriptor the caller cannot use is no guarantee at all.
    #
    # The remaining window is narrow and closed by the comparison, not ignored:
    # a racer who swaps the name between the two steps produces a DIFFERENT
    # (volume, file index) and is refused here.  A racer who relinks the name
    # back to the very object step 1 proved changes nothing -- the descriptor
    # names those proven bytes, which is exactly what the caller asked for.
    descriptor = os.open(path, flags & ~getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (serial, index):
            raise OSError(
                errno.ELOOP,
                "the path was replaced between its no-follow check and its open",
                os.fspath(path),
            )
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _win_create_share_delete_staging_file(
    directory: str | os.PathLike[str],
    *,
    prefix: str,
    suffix: str,
) -> tuple[int, str]:
    """The ``mkstemp``-shaped wrapper around :func:`_win_create_share_delete_child`."""

    parent = os.fspath(directory)
    for _attempt in range(64):
        candidate = os.path.join(parent, f"{prefix}{os.urandom(8).hex()}{suffix}")
        try:
            return _win_create_share_delete_child(candidate), candidate
        except FileExistsError:
            continue
    raise OSError(
        errno.EEXIST,
        "could not create a unique private staging file",
        parent,
    )


def create_private_staging_file(
    directory: str | os.PathLike[str],
    *,
    prefix: str,
    suffix: str = ".tmp",
) -> tuple[int, str]:
    """Create a private staging file that can still be published while open.

    Returns ``(descriptor, path)`` exactly as :func:`tempfile.mkstemp` does, and
    on POSIX it *is* ``tempfile.mkstemp`` -- byte-for-byte the call the private-
    cache publishers already made, so Linux and macOS behaviour is unchanged.

    The difference is Windows, and it is not cosmetic.  These publishers hold the
    staging descriptor across the publish on purpose: they write through it,
    ``fsync`` it, assert its identity, rename it into place, and then re-read the
    published bytes back *through that same descriptor* -- the descriptor is what
    proves the bytes that landed are the bytes that were verified.  Windows
    refuses to rename a file that has an open handle lacking
    ``FILE_SHARE_DELETE``, and the CRT never sets that bit, so on Windows the
    file is created with :func:`CreateFileW` instead, with ``CREATE_NEW`` (the
    ``O_CREAT | O_EXCL`` equivalent) and a share mode that permits the rename.
    Nothing is relaxed: the alternative would have been to close the descriptor
    before publishing and re-open the destination by name afterwards, which
    silently swaps a held-descriptor proof for a name lookup.  The caller owns the
    descriptor and must unlink ``path`` if it abandons the publish.
    """

    if IS_WINDOWS:
        return _win_create_share_delete_staging_file(
            directory, prefix=prefix, suffix=suffix
        )
    return tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=directory)


__all__ = [
    "DIRHANDLE_POSIX_DIR_FD",
    "DIRHANDLE_WINDOWS_REALPATH_PIN",
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
    "PUBLISH_LINUX_O_TMPFILE_LINKAT",
    "PUBLISH_LINUX_RENAMEAT2",
    "PUBLISH_MACOS_RENAMEX_EXCL",
    "PUBLISH_POSIX_LINK",
    "PUBLISH_POSIX_MKDIR_RESERVE",
    "PUBLISH_WINDOWS_RENAME",
    "SEALED_EXEC_PROCFS_INODE_PIN",
    "SEALED_EXEC_REVERIFIED_PATH",
    "SEALED_EXEC_WINDOWS_SHARE_PIN",
    "STAGE_LINUX_O_TMPFILE",
    "STAGE_POSIX_NAMED_TEMP",
    "STAGING_FILE_POSIX_MKSTEMP",
    "STAGING_FILE_WINDOWS_SHARE_DELETE",
    "WINDOWS_DIRECTORY_MODE",
    "WINDOWS_READ_ONLY_FILE_MODE",
    "WINDOWS_WRITABLE_FILE_MODE",
    "DirHandle",
    "DirectoryTransactionGuarantee",
    "DirectoryTransactionRefused",
    "DirectoryTransactionUnavailable",
    "DurabilityError",
    "NoReplacePublication",
    "NoReplacePublishUnavailable",
    "OwnershipCheck",
    "OwnershipCheckError",
    "PrivacyGuarantee",
    "PrivatePathError",
    "PrivateStage",
    "SealIntegrityError",
    "SealResult",
    "SealedExecHandle",
    "WindowsDaclVerdict",
    "add_seals",
    "available_bytes",
    "change_time_identity",
    "copy_file_range",
    "create_private_directory",
    "create_private_staging_file",
    "describe_ownership",
    "directory_transaction_guarantee",
    "exclusive_nonblocking_lock",
    "fchmod",
    "fchmod_readonly",
    "fsync_directory",
    "fsync_directory_fd",
    "fsync_fd",
    "fsync_path",
    "harden_private_directory",
    "harden_private_file",
    "is_canonical_absolute_path",
    "is_owned_by_current_user",
    "is_private_directory_mode",
    "is_private_file_mode",
    "is_reparse_point",
    "is_within_user_private_root",
    "no_replace_publish_mechanism",
    "open_no_follow",
    "open_dir_handle",
    "open_private_stage",
    "ownership_mechanism",
    "pread",
    "privacy_guarantee",
    "private_directory_mode",
    "private_file_mode",
    "private_staging_file_mechanism",
    "publish_no_replace",
    "publish_private_stage",
    "pwrite",
    "read_seals",
    "release_lock",
    "remove_private_tree",
    "reverify_sealed_before_exec",
    "seal_readonly",
    "sealed_file_mode",
    "supports_change_time_identity",
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
    "windows_directory_privacy",
    "write_seal_mask",
]
