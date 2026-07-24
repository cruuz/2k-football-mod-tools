#!/usr/bin/env python3
"""Safe, per-user Linux installer for APF 2K8 Mod Studio.

The installer never needs root privileges and never searches for, copies, or
deletes game data.  It copies only the exact retail-free release allowlist,
publishes the application from a sibling staging directory, and records every
desktop-integration path it owns.  Uninstall removes only paths authenticated
by that record and deliberately preserves projects, exports, caches, settings,
and emulator data.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
import sys
import tempfile
from typing import Iterable, Mapping
import uuid

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import platform_compat  # noqa: E402


APP_ID = "apf2k8-mod-studio"
PRODUCT_NAME = "APF 2K8 Mod Studio"
INSTALL_SCHEMA = "apf2k8_mod_studio_install/v1"
APP_MARKER_SCHEMA = "apf2k8_mod_studio_installed_app/v1"
APP_MARKER_NAME = ".apf2k8-installed-app.json"
INSTALL_RECORD_NAME = "install.json"
ALLOWLIST_RELATIVE = Path("packaging/apf2k8-release-allowlist.txt")
RELEASE_CHECK_RELATIVE = Path("packaging/check_apf2k8_mod_studio_release.py")
DESKTOP_RELATIVE = Path("packaging/apf2k8-mod-studio.desktop")
ICON_RELATIVE = Path("packaging/apf2k8-mod-studio.svg")
LAUNCHER_RELATIVE = Path("tools/launch_apf2k8_mod_studio.sh")
WRAPPER_MARKER = "# APF2K8_MOD_STUDIO_MANAGED_WRAPPER="
MAX_RECORD_BYTES = 64 * 1024
MAX_MANAGED_FILES = 512


class InstallError(ValueError):
    """A per-user installation safety boundary was not satisfied."""


@dataclass(frozen=True)
class InstallPaths:
    home: Path
    data_home: Path
    app_base: Path
    app_dir: Path
    record: Path
    bin_dir: Path
    wrapper: Path
    applications_dir: Path
    desktop: Path
    icon_dir: Path
    icon: Path


@dataclass(frozen=True)
class InstallResult:
    action: str
    paths: InstallPaths
    warnings: tuple[str, ...] = ()


def _absolute_directory_setting(value: str, label: str) -> Path:
    if not value or "\0" in value:
        raise InstallError(f"{label} is empty or invalid")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise InstallError(f"{label} must be an absolute path: {value!r}")
    return candidate.resolve(strict=False)


def _refuse_system_destination(path: Path, label: str) -> None:
    protected = (
        Path("/bin"),
        Path("/boot"),
        Path("/dev"),
        Path("/etc"),
        Path("/lib"),
        Path("/lib64"),
        Path("/opt"),
        Path("/proc"),
        Path("/root"),
        Path("/run"),
        Path("/sbin"),
        Path("/sys"),
        Path("/usr"),
        Path("/var"),
    )
    if path == Path("/") or any(path == item or path.is_relative_to(item) for item in protected):
        raise InstallError(
            f"{label} resolves inside a system location ({path}). "
            "Run without sudo and use your normal per-user XDG directories."
        )


def resolve_install_paths(environment: Mapping[str, str] | None = None) -> InstallPaths:
    env = os.environ if environment is None else environment
    home_value = env.get("HOME", "")
    home = _absolute_directory_setting(home_value, "HOME")
    if home == Path("/"):
        raise InstallError("HOME may not be the filesystem root")
    data_value = env.get("XDG_DATA_HOME")
    data_home = _absolute_directory_setting(
        data_value if data_value else str(home / ".local/share"),
        "XDG_DATA_HOME",
    )
    # XDG does not define a binary directory.  ~/.local/bin is the standard
    # per-user location and remains stable when XDG_DATA_HOME is customized.
    bin_dir = (home / ".local/bin").resolve(strict=False)
    app_base = data_home / APP_ID
    app_dir = app_base / "app"
    applications_dir = data_home / "applications"
    icon_dir = data_home / "icons/hicolor/scalable/apps"
    for label, path in (
        ("application directory", app_base),
        ("launcher directory", bin_dir),
        ("desktop-entry directory", applications_dir),
        ("icon directory", icon_dir),
    ):
        _refuse_system_destination(path, label)
    return InstallPaths(
        home=home,
        data_home=data_home,
        app_base=app_base,
        app_dir=app_dir,
        record=app_base / INSTALL_RECORD_NAME,
        bin_dir=bin_dir,
        wrapper=bin_dir / APP_ID,
        applications_dir=applications_dir,
        desktop=applications_dir / f"{APP_ID}.desktop",
        icon_dir=icon_dir,
        icon=icon_dir / f"{APP_ID}.svg",
    )


def _require_plain_directory(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InstallError(f"{label} does not exist: {path}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise InstallError(f"{label} must be a real directory, not a link: {path}")


def _ensure_directory(path: Path) -> None:
    path.mkdir(mode=0o755, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise InstallError(f"installation directory is not a real directory: {path}")


def _require_regular(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise InstallError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise InstallError(f"{label} must be a regular non-symlink file: {path}")
    if info.st_nlink != 1:
        raise InstallError(f"{label} may not be hardlinked: {path}")
    return info


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_small_regular(path: Path, label: str, maximum: int = MAX_RECORD_BYTES) -> bytes:
    info = _require_regular(path, label)
    if info.st_size > maximum:
        raise InstallError(f"{label} is unexpectedly large: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise InstallError(f"{label} changed while it was opened: {path}")
        chunks: list[bytes] = []
        completed = 0
        while block := os.read(descriptor, min(64 * 1024, maximum + 1 - completed)):
            completed += len(block)
            if completed > maximum:
                raise InstallError(f"{label} is unexpectedly large: {path}")
            chunks.append(block)
        if completed != opened.st_size:
            raise InstallError(f"{label} changed while it was read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: bytes, mode: int) -> None:
    _ensure_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.writing-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        platform_compat.fchmod(descriptor, mode, path=temporary)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _safe_allowlist(path: Path) -> tuple[str, ...]:
    payload = _read_small_regular(path, "release allowlist", maximum=256 * 1024)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError("release allowlist is not UTF-8 text") from exc
    entries: list[str] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\\" in line:
            raise InstallError(f"allowlist line {number} uses a backslash")
        relative = PurePosixPath(line)
        if (
            relative.is_absolute()
            or not relative.parts
            or line.endswith("/")
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise InstallError(f"allowlist line {number} is not an exact safe file")
        value = relative.as_posix()
        if value in entries:
            raise InstallError(f"duplicate release allowlist entry: {value}")
        entries.append(value)
    if not entries or len(entries) > MAX_MANAGED_FILES:
        raise InstallError("release allowlist is empty or unexpectedly large")
    return tuple(entries)


def _audit_release(source_root: Path) -> tuple[tuple[str, ...], str]:
    _require_plain_directory(source_root, "release folder")
    checker = source_root / RELEASE_CHECK_RELATIVE
    allowlist = source_root / ALLOWLIST_RELATIVE
    _require_regular(checker, "release checker")
    entries = _safe_allowlist(allowlist)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    result = subprocess.run(
        [sys.executable, str(checker), str(source_root), "--allowlist", str(allowlist)],
        cwd=source_root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or "APF2K8_MOD_STUDIO_RELEASE_PASS" not in result.stdout:
        detail = (result.stderr or result.stdout).strip().splitlines()
        reason = detail[-1] if detail else "the retail-free release check did not pass"
        raise InstallError(f"Installation refused: {reason}")
    return entries, _sha256_bytes(_read_small_regular(allowlist, "release allowlist", 256 * 1024))


def _copy_release_file(source: Path, destination: Path) -> str:
    source_info = _require_regular(source, "release file")
    _ensure_directory(destination.parent)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, flags | getattr(os, "O_BINARY", 0))
    destination_fd = -1
    digest = hashlib.sha256()
    try:
        opened = os.fstat(source_fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise InstallError(f"release file changed while opening: {source}")
        destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        completed = 0
        while block := os.read(source_fd, 1024 * 1024):
            digest.update(block)
            view = memoryview(block)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
            completed += len(block)
        if completed != opened.st_size or completed != source_info.st_size:
            raise InstallError(f"release file changed while copying: {source}")
        executable = bool(opened.st_mode & stat.S_IXUSR)
        platform_compat.fchmod(destination_fd, 0o755 if executable else 0o644, path=destination)
        os.fsync(destination_fd)
    finally:
        os.close(source_fd)
        if destination_fd >= 0:
            os.close(destination_fd)
    return digest.hexdigest()


def _marker_payload(install_id: str, allowlist_sha256: str) -> bytes:
    return (
        json.dumps(
            {
                "schema": APP_MARKER_SCHEMA,
                "install_id": install_id,
                "allowlist_sha256": allowlist_sha256,
                "contains_retail_game_data": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _load_json_regular(path: Path, label: str) -> dict[str, object]:
    payload = _read_small_regular(path, label)
    try:
        document = json.loads(payload)
    except (UnicodeError, ValueError) as exc:
        raise InstallError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(document, dict):
        raise InstallError(f"{label} has the wrong structure: {path}")
    return document


def _record_paths(paths: InstallPaths) -> dict[str, str]:
    return {
        "app_dir": str(paths.app_dir),
        "wrapper": str(paths.wrapper),
        "desktop": str(paths.desktop),
        "icon": str(paths.icon),
    }


def _validated_record(paths: InstallPaths) -> dict[str, object] | None:
    if not os.path.lexists(paths.record):
        return None
    document = _load_json_regular(paths.record, "installation ownership record")
    required = {
        "schema",
        "product",
        "install_id",
        "installed_at_utc",
        "paths",
        "managed_sha256",
        "release",
        "preserves_user_data_on_uninstall",
        "contains_retail_game_data",
    }
    if set(document) != required or document.get("schema") != INSTALL_SCHEMA:
        raise InstallError("installation ownership record has an unsupported structure")
    install_id = document.get("install_id")
    if not isinstance(install_id, str) or len(install_id) != 36:
        raise InstallError("installation ownership record has an invalid install ID")
    try:
        uuid.UUID(install_id)
    except ValueError as exc:
        raise InstallError("installation ownership record has an invalid install ID") from exc
    if document.get("paths") != _record_paths(paths):
        raise InstallError(
            "installation ownership paths do not match the current per-user locations; "
            "nothing was changed"
        )
    hashes = document.get("managed_sha256")
    if not isinstance(hashes, dict) or set(hashes) != {"wrapper", "desktop", "icon"}:
        raise InstallError("installation ownership hashes are incomplete")
    if not all(isinstance(value, str) and len(value) == 64 for value in hashes.values()):
        raise InstallError("installation ownership hashes are invalid")
    if document.get("contains_retail_game_data") is not False:
        raise InstallError("installation ownership record lost its retail-free declaration")
    return document


def _validate_app_marker(app_dir: Path, install_id: str) -> None:
    marker = _load_json_regular(app_dir / APP_MARKER_NAME, "installed-app marker")
    if (
        set(marker)
        != {"schema", "install_id", "allowlist_sha256", "contains_retail_game_data"}
        or marker.get("schema") != APP_MARKER_SCHEMA
        or marker.get("install_id") != install_id
        or marker.get("contains_retail_game_data") is not False
    ):
        raise InstallError("installed application marker does not match its ownership record")


def _desktop_quote(path: Path) -> str:
    # Desktop Entry Exec quoting has its own grammar.  A fully quoted first
    # token is reliable for spaces; these four characters require escaping
    # inside the quoted token per the specification.
    value = str(path)
    for old, new in (("\\", "\\\\"), ("\"", "\\\""), ("`", "\\`"), ("$", "\\$")):
        value = value.replace(old, new)
    return f'"{value}"'


def _render_desktop(template: bytes, wrapper: Path, install_id: str) -> bytes:
    try:
        text = template.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError("desktop template is not UTF-8 text") from exc
    lines = text.splitlines()
    exec_count = 0
    try_count = 0
    rendered: list[str] = []
    for line in lines:
        if line.startswith("Exec="):
            rendered.append(f"Exec={_desktop_quote(wrapper)}")
            exec_count += 1
        elif line.startswith("TryExec="):
            rendered.append(f"TryExec={wrapper}")
            try_count += 1
        elif line.startswith("X-APF2K8-Mod-Studio-"):
            continue
        else:
            rendered.append(line)
    if exec_count != 1 or try_count != 1:
        raise InstallError("desktop template must contain exactly one Exec and TryExec line")
    rendered.extend(
        (
            "X-APF2K8-Mod-Studio-Managed=true",
            f"X-APF2K8-Mod-Studio-Install-ID={install_id}",
        )
    )
    return ("\n".join(rendered) + "\n").encode("utf-8")


def _wrapper_payload(app_launcher: Path, install_id: str) -> bytes:
    return (
        "#!/bin/sh\n"
        f"{WRAPPER_MARKER}{install_id}\n"
        "# This absolute target is generated by the per-user installer.\n"
        f"exec {shlex.quote(str(app_launcher))} \"$@\"\n"
    ).encode("utf-8")


def _managed_external_payloads(
    source_root: Path,
    paths: InstallPaths,
    install_id: str,
) -> dict[str, tuple[Path, bytes, int]]:
    desktop_template = _read_small_regular(
        source_root / DESKTOP_RELATIVE, "desktop template", maximum=256 * 1024
    )
    icon = _read_small_regular(source_root / ICON_RELATIVE, "application icon", maximum=1024 * 1024)
    return {
        "wrapper": (
            paths.wrapper,
            _wrapper_payload(paths.app_dir / LAUNCHER_RELATIVE, install_id),
            0o755,
        ),
        "desktop": (
            paths.desktop,
            _render_desktop(desktop_template, paths.wrapper, install_id),
            0o644,
        ),
        "icon": (paths.icon, icon, 0o644),
    }


def _preflight_external(
    payloads: Mapping[str, tuple[Path, bytes, int]],
    previous: dict[str, object] | None,
) -> dict[str, tuple[bytes, int] | None]:
    snapshots: dict[str, tuple[bytes, int] | None] = {}
    expected_hashes = previous.get("managed_sha256") if previous else None
    for key, (path, _new_payload, _mode) in payloads.items():
        if not os.path.lexists(path):
            snapshots[key] = None
            continue
        if previous is None:
            raise InstallError(
                f"Installation refused because an unowned file already exists: {path}\n"
                "Move or rename that file, then try again."
            )
        current = _read_small_regular(path, f"installed {key}", maximum=1024 * 1024)
        assert isinstance(expected_hashes, dict)
        if _sha256_bytes(current) != expected_hashes.get(key):
            raise InstallError(
                f"Installation refused because the managed {key} was changed outside the installer: {path}\n"
                "The file was preserved. Restore the prior installed file or uninstall it manually."
            )
        snapshots[key] = (current, stat.S_IMODE(path.stat().st_mode))
    return snapshots


def _record_payload(
    paths: InstallPaths,
    install_id: str,
    allowlist_sha256: str,
    file_count: int,
    payloads: Mapping[str, tuple[Path, bytes, int]],
) -> bytes:
    document = {
        "schema": INSTALL_SCHEMA,
        "product": PRODUCT_NAME,
        "install_id": install_id,
        "installed_at_utc": datetime.now(timezone.utc).isoformat(),
        "paths": _record_paths(paths),
        "managed_sha256": {
            key: _sha256_bytes(payload) for key, (_path, payload, _mode) in payloads.items()
        },
        "release": {
            "allowlist_sha256": allowlist_sha256,
            "file_count": file_count,
        },
        "preserves_user_data_on_uninstall": True,
        "contains_retail_game_data": False,
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _iter_tree_bottom_up(root: Path) -> Iterable[Path]:
    directories: list[Path] = []
    pending = [root]
    file_count = 0
    while pending:
        directory = pending.pop()
        directories.append(directory)
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise InstallError(f"cannot inspect managed application directory: {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise InstallError(f"managed application contains an unexpected symlink: {path}")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                file_count += 1
                if file_count > MAX_MANAGED_FILES + 1:
                    raise InstallError("managed application contains an unexpected number of files")
                yield path
            else:
                raise InstallError(f"managed application contains an unexpected filesystem entry: {path}")
    for directory in reversed(directories):
        yield directory


def _validate_managed_tree(root: Path, app_base: Path, install_id: str | None) -> tuple[Path, ...]:
    if root.parent != app_base or root.name not in {"app"} and not root.name.startswith(
        (".installing-", ".previous-")
    ):
        raise InstallError(f"refusing to operate on an out-of-scope application tree: {root}")
    _require_plain_directory(root, "managed application tree")
    if install_id is not None:
        _validate_app_marker(root, install_id)
    return tuple(_iter_tree_bottom_up(root))


def _remove_validated_tree(entries: Iterable[Path]) -> None:
    for path in entries:
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            path.rmdir()
        elif stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and info.st_nlink == 1:
            path.unlink()
        else:
            raise InstallError(f"managed path changed during cleanup: {path}")


def _remove_new_external(
    payloads: Mapping[str, tuple[Path, bytes, int]],
) -> None:
    for _key, (path, payload, _mode) in payloads.items():
        if not os.path.lexists(path):
            continue
        try:
            current = _read_small_regular(path, "new managed integration file", 1024 * 1024)
        except InstallError:
            continue
        if _sha256_bytes(current) == _sha256_bytes(payload):
            path.unlink()


def _restore_external(
    payloads: Mapping[str, tuple[Path, bytes, int]],
    snapshots: Mapping[str, tuple[bytes, int] | None],
) -> None:
    _remove_new_external(payloads)
    for key, snapshot in snapshots.items():
        if snapshot is None:
            continue
        path = payloads[key][0]
        payload, mode = snapshot
        _atomic_write(path, payload, mode)


def _dependency_warnings() -> tuple[str, ...]:
    environment = os.environ.copy()
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    missing: list[str] = []
    for module, label in (("PyQt5", "PyQt5"), ("PIL", "Pillow")):
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            missing.append(label)
    if not missing:
        return ()
    return (
        "The app was installed, but it cannot open until these system Python packages are present: "
        + ", ".join(missing)
        + ". On Linux Mint/Ubuntu run: sudo apt install python3 python3-pyqt5 python3-pil",
    )


def install(
    source_root: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> InstallResult:
    paths = resolve_install_paths(environment)
    source_root = source_root.expanduser().resolve(strict=True)
    if source_root == paths.app_base or source_root.is_relative_to(paths.app_base):
        raise InstallError("the release folder may not be inside the managed installation directory")
    entries, allowlist_sha256 = _audit_release(source_root)
    previous = _validated_record(paths)
    if previous is None and os.path.lexists(paths.app_dir):
        raise InstallError(
            f"An unowned application directory already exists: {paths.app_dir}\n"
            "It was not changed. Move it aside and try again."
        )
    if previous is not None:
        _validate_app_marker(paths.app_dir, str(previous["install_id"]))

    _ensure_directory(paths.app_base)
    install_id = str(uuid.uuid4())
    payloads = _managed_external_payloads(source_root, paths, install_id)
    snapshots = _preflight_external(payloads, previous)
    record_snapshot = (
        _read_small_regular(paths.record, "installation ownership record") if previous else None
    )
    stage = Path(tempfile.mkdtemp(prefix=".installing-", dir=paths.app_base))
    backup: Path | None = None
    published = False
    committed = False
    try:
        for relative in entries:
            source = source_root / Path(*PurePosixPath(relative).parts)
            destination = stage / Path(*PurePosixPath(relative).parts)
            _copy_release_file(source, destination)
        _atomic_write(stage / APP_MARKER_NAME, _marker_payload(install_id, allowlist_sha256), 0o600)

        if previous is not None:
            backup = paths.app_base / f".previous-{install_id}"
            if os.path.lexists(backup):
                raise InstallError(f"temporary upgrade path already exists: {backup}")
            os.rename(paths.app_dir, backup)
        os.rename(stage, paths.app_dir)
        published = True

        for _key, (path, payload, mode) in payloads.items():
            _atomic_write(path, payload, mode)
        record_payload = _record_payload(
            paths, install_id, allowlist_sha256, len(entries), payloads
        )
        _atomic_write(paths.record, record_payload, 0o600)
        committed = True
    except BaseException:
        if not committed:
            _restore_external(payloads, snapshots)
            if record_snapshot is not None:
                _atomic_write(paths.record, record_snapshot, 0o600)
            elif os.path.lexists(paths.record):
                try:
                    paths.record.unlink()
                except OSError:
                    pass
            if published and os.path.lexists(paths.app_dir):
                try:
                    removable = _validate_managed_tree(paths.app_dir, paths.app_base, install_id)
                    _remove_validated_tree(removable)
                except InstallError:
                    pass
            if backup is not None and os.path.lexists(backup) and not os.path.lexists(paths.app_dir):
                os.rename(backup, paths.app_dir)
        if os.path.lexists(stage):
            try:
                removable = _validate_managed_tree(stage, paths.app_base, None)
                _remove_validated_tree(removable)
            except InstallError:
                pass
        raise

    warnings = list(_dependency_warnings())
    if backup is not None and os.path.lexists(backup):
        try:
            old_id = str(previous["install_id"]) if previous else None
            removable = _validate_managed_tree(backup, paths.app_base, old_id)
            _remove_validated_tree(removable)
        except InstallError as exc:
            warnings.append(
                f"The upgrade succeeded, but the authenticated previous app copy was preserved at {backup}: {exc}"
            )
    return InstallResult(
        action="updated" if previous is not None else "installed",
        paths=paths,
        warnings=tuple(warnings),
    )


def uninstall(*, environment: Mapping[str, str] | None = None) -> InstallResult:
    paths = resolve_install_paths(environment)
    record = _validated_record(paths)
    if record is None:
        raise InstallError(
            f"No managed APF 2K8 Mod Studio installation was found at {paths.app_base}."
        )
    install_id = str(record["install_id"])
    removable = _validate_managed_tree(paths.app_dir, paths.app_base, install_id)
    hashes = record["managed_sha256"]
    assert isinstance(hashes, dict)
    warnings: list[str] = []

    # Validate every integration target before removing the app.  Changed or
    # replaced targets are never deleted; users receive the exact path instead.
    external = {
        "wrapper": paths.wrapper,
        "desktop": paths.desktop,
        "icon": paths.icon,
    }
    deletable: list[Path] = []
    for key, path in external.items():
        if not os.path.lexists(path):
            continue
        try:
            payload = _read_small_regular(path, f"installed {key}", 1024 * 1024)
        except InstallError as exc:
            warnings.append(f"Preserved changed {key} at {path}: {exc}")
            continue
        if _sha256_bytes(payload) != hashes.get(key):
            warnings.append(f"Preserved changed {key} at {path}; its bytes no longer match the installer record.")
            continue
        deletable.append(path)

    _remove_validated_tree(removable)
    for path in deletable:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    paths.record.unlink()
    try:
        paths.app_base.rmdir()
    except OSError:
        # A prior authenticated upgrade backup or an unknown user-created item
        # is never erased merely to make the parent directory disappear.
        warnings.append(f"Preserved non-empty application container: {paths.app_base}")
    return InstallResult(action="uninstalled", paths=paths, warnings=tuple(warnings))


def _print_result(result: InstallResult) -> None:
    if result.action in {"installed", "updated"}:
        print(f"{PRODUCT_NAME} was {result.action} for this user.")
        print(f"Application: {result.paths.app_dir}")
        print(f"App menu shortcut: {result.paths.desktop}")
        print(f"Command: {result.paths.wrapper}")
        print("No retail game data was installed. Open the app and select your own dump.")
    else:
        print(f"{PRODUCT_NAME} was uninstalled for this user.")
        print("Projects, exports, cache, settings, and emulator data were preserved.")
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install", help="install or safely update for this user")
    install_parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="extracted APF 2K8 Mod Studio release folder",
    )
    subparsers.add_parser(
        "uninstall",
        help="remove only installer-owned program files and preserve user data",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print(
            "APF2K8_MOD_STUDIO_INSTALL_REFUSED: Do not use sudo or run this installer as root. "
            "Sign in as the desktop user and run it normally.",
            file=sys.stderr,
        )
        return 1
    try:
        if arguments.command == "install":
            result = install(arguments.source_root)
        else:
            result = uninstall()
    except (InstallError, OSError, subprocess.SubprocessError) as exc:
        print(f"APF2K8_MOD_STUDIO_INSTALL_REFUSED: {exc}", file=sys.stderr)
        return 1
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
