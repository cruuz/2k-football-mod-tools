"""Read-only open-file probes and bounded, transactional image copying.

POSIX probes are a snapshot, not a lock against a noncooperating future opener.
Linux inspects visible processes owned by the current user; macOS uses lsof.
Windows asks the kernel for a temporary read handle with no sharing.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

from .errors import ValidationError
from .platform_compat import long_path, publish_no_replace


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
    path = Path(image).expanduser()
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValidationError(f"Choose a regular disc image, not a link: {path}")
    path = path.resolve(strict=True)
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
    target = Path(target)
    if target.is_symlink():
        raise ValidationError("The output image must not be a symbolic link.")
    if not target.exists():
        return None
    assert_image_available(target)
    if not overwrite:
        raise FileExistsError(target)
    return target.stat()


def publish_image(staging: Path, target: Path, previous) -> None:
    """Publish completed bytes; refuse a newly appeared, changed or open target."""
    if previous is None:
        publish_no_replace(staging, target)
        return
    assert_image_available(target)
    now = target.stat()
    if (now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns) != (
            previous.st_dev, previous.st_ino, previous.st_size, previous.st_mtime_ns):
        raise ValidationError("The output image changed during copying; retry with a new output path.")
    os.replace(long_path(staging), long_path(target))


def copy_image(source: Path, target: Path, *, overwrite: bool = False) -> None:
    """Stream a new image, then publish after rechecking the old destination.

    All readers/writers close before publication. Failure removes only our temp.
    Source may be open for reading; an existing destination may not be in use.
    """
    source = Path(source).expanduser().resolve(strict=True)
    requested = Path(target).expanduser().absolute()
    if requested.is_symlink():
        raise ValidationError("The output image must not be a symbolic link.")
    target = requested.resolve(strict=False)
    if target == source or (target.exists() and os.path.samefile(source, target)):
        raise ValidationError("Choose an output image separate from the source.")
    previous = check_image_destination(target, overwrite=overwrite)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".image-", suffix=".copying", dir=target.parent)
    temporary = Path(name).resolve()
    try:
        with os.fdopen(fd, "wb") as writer, source.open("rb") as reader:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        publish_image(temporary, target, previous)
    finally:
        temporary.unlink(missing_ok=True)
