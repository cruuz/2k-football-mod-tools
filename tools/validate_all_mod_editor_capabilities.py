#!/usr/bin/env python3
"""Execute every unique validator authorized by the capability registry.

The aggregate gate runs each distinct registry validator once.  It pins the
small repository control plane before every validator and the larger evidence
plane across the complete run.  Retail images, build trees, emulator disks,
and other multi-gigabyte inputs remain the responsibility of the focused
validators that authenticate them.

The snapshots detect ordinary concurrent drift.  They do not make pathname
execution immutable: a hostile writer that swaps and restores a dependency
entirely between two snapshot boundaries remains outside this gate's claim.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import platform_compat  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = Path(__file__).resolve()
WRAPPER_PATH = ROOT / "tools/validate_all_mod_editor_capabilities.sh"
DEFAULT_REGISTRY = ROOT / "mod_editor/capabilities/registry.v1.json"
REGISTRY_VALIDATOR_PATH = ROOT / "mod_editor/capabilities/validate_registry.py"
REGISTRY_SCHEMA_PATH = ROOT / "mod_editor/capabilities/registry.schema.json"
REPORT_SCHEMA = "mod_editor_capability_validation_run/v3"
MANIFEST_SCHEMA = "mod_editor_validation_file_manifest/v1"
REPORT_PUBLICATION_METHOD = "linux_o_tmpfile_procfd_link_no_replace/v1"
REPORT_RESIDUAL_LIMITATION = (
    "Snapshots detect drift at their boundaries but do not make pathname "
    "execution immutable; a swap-and-restore wholly between boundaries is "
    "outside this receipt's claim. Publication checks are point-in-time: a "
    "writer authorized to modify the report directory can replace or remove "
    "the receipt after the final check. A failure or interrupt after the "
    "no-replace link commit can leave a complete receipt even though the "
    "runner does not print its success marker."
)
ALLOWED_LAUNCHERS = {"bash", "python3"}
EXPECTED_CAPABILITIES = 150
EXPECTED_COVERED_CAPABILITIES = 145
EXPECTED_DEFERRED_CAPABILITIES = 5
EXPECTED_UNIQUE_VALIDATORS = 97
EXPECTED_DEFERRED_IDS = (
    "apf2k8.catching_drops.behavior",
    "apf2k8.franchise_restoration_cross_title.mode",
    "apf2k8.saves.profile",
    "nfl2k5.catching_drops.behavior",
    "nfl2k5.franchise_restoration_cross_title.port",
)
def _discover_rg_path() -> Path:
    """Return the host's ripgrep without embedding a workstation path."""

    for directory in (Path("/usr/bin"), Path("/bin")):
        candidate = directory / "rg"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.absolute()
    discovered = shutil.which("rg")
    if discovered is not None:
        # Preserve the PATH lookup leaf.  The provenance capture below records
        # and verifies its complete symlink chain as well as the resolved file.
        return Path(os.path.abspath(discovered))
    # Keep imports usable on hosts without ripgrep so the focused suite can
    # report its existing named skip.  A real run still fails closed when the
    # executable provenance is captured.
    return Path("/usr/bin/rg")


def _isolated_rg_directory(resolved: Path) -> Path:
    """A directory holding ripgrep and nothing else, for the fixed PATH tail.

    The tail of the fixed PATH must expose exactly one command.  When ripgrep
    comes from ``/usr/bin`` that is already true, but a ripgrep discovered
    through ``PATH`` often lives in a shared vendor bin beside other
    executables -- and putting that whole directory on the validation PATH lets
    any of them shadow an audited command.

    So when the discovered directory holds anything besides ripgrep, expose it
    through a private single-entry directory instead.  Any failure falls back to
    the discovered directory, where the caller's own single-entry assertion
    still catches the problem rather than hiding it.
    """

    try:
        siblings = sorted(entry.name for entry in resolved.parent.iterdir())
    except OSError:
        return resolved.parent
    if siblings == [resolved.name]:
        return resolved.parent
    private = Path.home() / ".cache" / "2k-mod-tools" / "validation-bin"
    try:
        private.mkdir(parents=True, exist_ok=True)
        for stale in private.iterdir():
            if stale.name != resolved.name:
                stale.unlink()
        link = private / resolved.name
        if link.is_symlink() or link.exists():
            if link.resolve() == resolved:
                return private
            link.unlink()
        link.symlink_to(resolved)
    except OSError:
        return resolved.parent
    return private


PINNED_RG_PATH = _discover_rg_path()
# Keep a single-command directory last.  System commands therefore win normal
# lookup, the exact ripgrep executable is still captured and verified before
# and after the validation run, and nothing else on the host can shadow an
# audited command through this entry.
FIXED_PATH = f"/usr/bin:/bin:{_isolated_rg_directory(PINNED_RG_PATH.resolve())}"
FIXED_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": str(Path.home().resolve()),
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": FIXED_PATH,
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
    "PYTHONUTF8": "1",
    "TMPDIR": "/tmp",
    "TZ": "UTC",
}
LAUNCHER_PATHS = {
    "bash": Path("/usr/bin/bash"),
    "python3": Path("/usr/bin/python3").resolve(),
}
AUXILIARY_COMMAND_NAMES = (
    "ar",
    "awk",
    "bash",
    "basename",
    "cc",
    "chmod",
    "clang-18",
    "clang++-18",
    "cmake",
    "cmp",
    "cp",
    "cut",
    "dd",
    "dirname",
    "env",
    "file",
    "find",
    "ffmpeg",
    "ffprobe",
    "g++",
    "gcc",
    "git",
    "grep",
    "head",
    "jq",
    "jsonschema",
    "java",
    "ld",
    "ld.lld-18",
    "ln",
    "make",
    "mkdir",
    "mktemp",
    "mv",
    "nm",
    "objdump",
    "qemu-img",
    "python3",
    "readlink",
    "realpath",
    "rg",
    "rm",
    "sed",
    "sha256sum",
    "sh",
    "sort",
    "stat",
    "strings",
    "tail",
    "tee",
    "touch",
    "tr",
    "truncate",
    "wc",
    "xxd",
)
CONTROL_ROOTS = (
    ROOT / "tools",
    ROOT / "mod_editor",
    ROOT / "tests",
    ROOT / "include",
    ROOT / "src",
    ROOT / "reports/specs",
)
CONTROL_EXPLICIT_FILES = (ROOT / "README.md", ROOT / "CMakeLists.txt")
EVIDENCE_ROOTS = (
    ROOT / "reports",
    ROOT / "docs",
    ROOT / "research",
    ROOT / "assets/fixtures",
    ROOT / "assets/manifests",
    ROOT / "assets/mod",
    ROOT / "assets/raw",
)
ALLOWED_VENDOR_PATHS = (
    Path("tools/vendor/XenonRecomp/XenonUtils"),
    Path("tools/vendor/XenonRecomp/thirdparty/TinySHA1"),
    Path("tools/vendor/XenonRecomp/thirdparty/tiny-AES-c"),
    Path("tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a"),
    Path("tools/vendor/extract-xiso"),
)
CONTROL_POLICY = {
    "include": [
        "README.md",
        "CMakeLists.txt",
        "tools/** (except exclusions)",
        "mod_editor/**",
        "tests/**",
        "include/**",
        "src/**",
        "reports/specs/** and reports/**/*.schema.json",
        "reviewed XenonUtils/TinySHA1/tiny-AES-c/extract-xiso dependencies",
    ],
    "exclude": [
        "**/__pycache__/**",
        "**/*.pyc",
        "**/*.pyo",
        "tools/ghidra-home/**",
        "tools/vendor/** except the reviewed dependencies",
        "tools/vendor/extract-xiso/.git/**",
    ],
}
EVIDENCE_POLICY = {
    "include": [
        "reports/**",
        "docs/**",
        "research/**",
        "assets/fixtures/**",
        "assets/manifests/**",
        "assets/mod/**",
        "assets/raw/**",
    ],
    "exclude": [
        "files already in the control manifest",
        "retail images and extracted game trees",
        "build*/**, .codex-tmp/**, ghidra_projects/**",
        "assets/intermediate/**",
        "external emulator/QCOW/XISO runtime artifacts",
    ],
}
OUTPUT_TAIL_BYTES = 1024 * 1024
TERMINATE_GRACE_SECONDS = 2.0
KILL_GRACE_SECONDS = 2.0

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.capabilities.validate_registry import (  # noqa: E402
    RegistryError,
    validate_data,
)


class ValidationRunError(ValueError):
    """The execution plan, snapshot, or publication boundary is unsafe."""


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    device: int
    inode: int
    link_count: int
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class FileManifest:
    name: str
    files: tuple[FileSnapshot, ...]
    total_bytes: int
    manifest_sha256: str


@dataclass(frozen=True)
class PathLookupSnapshot:
    """Stable lstat identity for an executable lookup leaf or symlink hop."""

    path: Path
    device: int
    inode: int
    link_count: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    symlink_target: str | None


@dataclass(frozen=True)
class ExecutableProvenance:
    """The PATH lookup leaf, complete symlink resolution, and executable bytes."""

    lookup_leaf: PathLookupSnapshot
    symlink_chain: tuple[PathLookupSnapshot, ...]
    resolved_leaf: PathLookupSnapshot
    executable: FileSnapshot


@dataclass(frozen=True)
class ValidationPlanEntry:
    command: str
    argv: tuple[str, ...]
    capability_ids: tuple[str, ...]
    validator_snapshot: FileSnapshot


@dataclass(frozen=True)
class CommandExecution:
    status: str
    returncode: int | None
    output_sha256: str
    output_bytes: int
    final_line: str
    output: str
    output_truncated: bool


@dataclass(frozen=True)
class ValidationResult:
    command: str
    capability_ids: tuple[str, ...]
    status: str
    returncode: int | None
    elapsed_seconds: float
    output_sha256: str
    output_bytes: int
    final_line: str
    output: str
    output_truncated: bool
    validator_snapshot: FileSnapshot


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or path.is_relative_to(parent)


def _require_no_symlink_ancestors(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:-1]:
        current /= part
        try:
            status = current.lstat()
        except FileNotFoundError as exc:
            raise ValidationRunError(f"path ancestor is missing: {current}") from exc
        if stat.S_ISLNK(status.st_mode):
            raise ValidationRunError(f"path ancestor must not be a symlink: {current}")
        if not stat.S_ISDIR(status.st_mode):
            raise ValidationRunError(f"path ancestor must be a directory: {current}")


def read_pinned_file(path: Path, *, allow_empty: bool = False) -> tuple[FileSnapshot, bytes]:
    """Read one exact single-link regular file through a checked descriptor."""

    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationRunError(f"required local file is missing: {path}") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or (before.st_size == 0 and not allow_empty)
    ):
        empty_rule = "" if allow_empty else "nonempty, "
        raise ValidationRunError(
            f"required local file must be {empty_rule}single-link, regular, and "
            f"non-symlink: {path}"
        )
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
        )
        if identity != (
            before.st_dev,
            before.st_ino,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
        ):
            raise ValidationRunError(f"local file changed before open: {path}")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ValidationRunError(f"short read from local file: {path}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValidationRunError(f"local file grew while reading: {path}")
        after_descriptor = os.fstat(descriptor)
        after_path = path.lstat()
        for status in (after_descriptor, after_path):
            if (
                status.st_dev,
                status.st_ino,
                status.st_nlink,
                status.st_size,
                status.st_mtime_ns,
            ) != identity:
                raise ValidationRunError(f"local file changed while reading: {path}")
        payload = b"".join(chunks)
        return (
            FileSnapshot(
                path=path,
                device=opened.st_dev,
                inode=opened.st_ino,
                link_count=opened.st_nlink,
                size=opened.st_size,
                mtime_ns=opened.st_mtime_ns,
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
            payload,
        )
    finally:
        os.close(descriptor)


def verify_snapshot(expected: FileSnapshot) -> None:
    current, _payload = read_pinned_file(expected.path, allow_empty=expected.size == 0)
    if current != expected:
        raise ValidationRunError(f"pinned local file changed during run: {expected.path}")


def public_snapshot(snapshot: FileSnapshot) -> dict[str, Any]:
    try:
        path = str(snapshot.path.relative_to(ROOT))
    except ValueError:
        path = str(snapshot.path)
    return {"path": path, "sha256": snapshot.sha256, "size": snapshot.size}


def _manifest_digest(files: Sequence[FileSnapshot]) -> str:
    payload = canonical_json({"files": [public_snapshot(row) for row in files]})
    return hashlib.sha256(payload).hexdigest()


def capture_manifest(name: str, paths: Iterable[Path]) -> FileManifest:
    ordered = tuple(sorted(set(paths), key=lambda value: str(value)))
    files = tuple(read_pinned_file(path, allow_empty=True)[0] for path in ordered)
    return FileManifest(
        name=name,
        files=files,
        total_bytes=sum(row.size for row in files),
        manifest_sha256=_manifest_digest(files),
    )


def public_manifest(manifest: FileManifest, policy: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "file_count": len(manifest.files),
        "files": [public_snapshot(row) for row in manifest.files],
        "manifest_sha256": manifest.manifest_sha256,
        "name": manifest.name,
        "policy": policy,
        "schema": MANIFEST_SCHEMA,
        "total_bytes": manifest.total_bytes,
    }


def verify_manifest(expected: FileManifest, path_provider: Callable[[], Sequence[Path]]) -> None:
    current = capture_manifest(expected.name, path_provider())
    if current != expected:
        raise ValidationRunError(f"{expected.name} manifest changed during run")


def _control_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if "__pycache__" in relative.parts or path.suffix in (".pyc", ".pyo"):
        return True
    if _is_within(relative, Path("tools/ghidra-home")):
        return True
    extract_git = Path("tools/vendor/extract-xiso/.git")
    if _is_within(relative, extract_git):
        return True
    vendor = Path("tools/vendor")
    if _is_within(relative, vendor):
        for allowed in ALLOWED_VENDOR_PATHS:
            if _is_within(relative, allowed) or _is_within(allowed, relative):
                return False
        return True
    return False


def _walk_regular_files(root: Path, excluded: Callable[[Path], bool]) -> tuple[Path, ...]:
    if excluded(root):
        return ()
    pending = [root]
    output: list[Path] = []
    while pending:
        path = pending.pop()
        if excluded(path):
            continue
        try:
            status = path.lstat()
        except FileNotFoundError as exc:
            raise ValidationRunError(f"snapshot root entry disappeared: {path}") from exc
        if stat.S_ISLNK(status.st_mode):
            raise ValidationRunError(f"snapshot path must not be a symlink: {path}")
        if stat.S_ISREG(status.st_mode):
            output.append(path)
            continue
        if not stat.S_ISDIR(status.st_mode):
            raise ValidationRunError(f"snapshot path is not regular or a directory: {path}")
        with os.scandir(path) as stream:
            children = sorted((Path(entry.path) for entry in stream), reverse=True)
        pending.extend(children)
    return tuple(output)


def control_paths() -> tuple[Path, ...]:
    paths = set(CONTROL_EXPLICIT_FILES)
    for root in CONTROL_ROOTS:
        paths.update(_walk_regular_files(root, _control_excluded))
    for path in _walk_regular_files(ROOT / "reports", lambda _path: False):
        if path.name.endswith(".schema.json"):
            paths.add(path)
    return tuple(sorted(paths, key=lambda value: str(value)))


def evidence_paths() -> tuple[Path, ...]:
    control = set(control_paths())
    paths: set[Path] = set()
    for root in EVIDENCE_ROOTS:
        paths.update(_walk_regular_files(
            root,
            lambda path: "__pycache__" in path.parts
            or path.suffix in (".pyc", ".pyo"),
        ))
    return tuple(sorted(paths - control, key=lambda value: str(value)))


def capture_control_manifest() -> FileManifest:
    return capture_manifest("control", control_paths())


def capture_evidence_manifest() -> FileManifest:
    return capture_manifest("evidence", evidence_paths())


def _capture_lookup_node(path: Path) -> PathLookupSnapshot:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationRunError(f"executable lookup path is missing: {path}") from exc
    if not (
        stat.S_ISREG(before.st_mode)
        or stat.S_ISDIR(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
    ):
        raise ValidationRunError(f"executable lookup path has an unsafe type: {path}")
    target_before = os.readlink(path) if stat.S_ISLNK(before.st_mode) else None
    after = path.lstat()
    target_after = os.readlink(path) if stat.S_ISLNK(after.st_mode) else None
    # ``before`` and ``after`` are both path.lstat() of one pathname: two path
    # stats, which agree on st_ctime_ns on every platform, Windows included, so
    # the change time stays in this fingerprint and a metadata-only edit to the
    # lookup path is still caught everywhere.
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_nlink,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        target_before,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_nlink,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        target_after,
    )
    if identity_after != identity_before:
        raise ValidationRunError(f"executable lookup path changed while reading: {path}")
    return PathLookupSnapshot(
        path=path,
        device=before.st_dev,
        inode=before.st_ino,
        link_count=before.st_nlink,
        mode=before.st_mode,
        size=before.st_size,
        mtime_ns=before.st_mtime_ns,
        ctime_ns=before.st_ctime_ns,
        symlink_target=target_before,
    )


def _resolve_executable_lookup(
    lookup_path: Path,
) -> tuple[Path, tuple[PathLookupSnapshot, ...], PathLookupSnapshot]:
    """Resolve one absolute lookup path while retaining every symlink hop."""

    if not lookup_path.is_absolute() or ".." in lookup_path.parts:
        raise ValidationRunError("executable lookup path must be absolute and normalized")
    pending = list(lookup_path.parts[1:])
    current = Path(lookup_path.anchor)
    symlinks: list[PathLookupSnapshot] = []
    hops = 0
    final_node: PathLookupSnapshot | None = None
    while pending:
        component = pending.pop(0)
        candidate = current / component
        node = _capture_lookup_node(candidate)
        if node.symlink_target is not None:
            symlinks.append(node)
            hops += 1
            if hops > 64:
                raise ValidationRunError(
                    f"executable lookup contains too many symlink hops: {lookup_path}"
                )
            target = Path(node.symlink_target)
            replaced = target if target.is_absolute() else candidate.parent / target
            for remaining in pending:
                replaced /= remaining
            normalized = Path(os.path.normpath(str(replaced)))
            if not normalized.is_absolute():
                raise ValidationRunError(
                    f"executable symlink resolved outside an absolute path: {candidate}"
                )
            current = Path(normalized.anchor)
            pending = list(normalized.parts[1:])
            continue
        if pending and not stat.S_ISDIR(node.mode):
            raise ValidationRunError(
                f"executable lookup traverses a non-directory: {candidate}"
            )
        current = candidate
        final_node = node
    if final_node is None or not stat.S_ISREG(final_node.mode):
        raise ValidationRunError(f"executable lookup did not resolve to a file: {lookup_path}")
    return current, tuple(symlinks), final_node


def _file_matches_lookup_node(snapshot: FileSnapshot, node: PathLookupSnapshot) -> bool:
    return (
        snapshot.path == node.path
        and snapshot.device == node.device
        and snapshot.inode == node.inode
        and snapshot.link_count == node.link_count
        and snapshot.size == node.size
        and snapshot.mtime_ns == node.mtime_ns
    )


def capture_executable_provenance(lookup_path: Path) -> ExecutableProvenance:
    lookup_leaf = _capture_lookup_node(lookup_path)
    if not (
        stat.S_ISREG(lookup_leaf.mode) or stat.S_ISLNK(lookup_leaf.mode)
    ):
        raise ValidationRunError(
            f"executable lookup leaf must be regular or a symlink: {lookup_path}"
        )
    resolved, chain, resolved_node = _resolve_executable_lookup(lookup_path)
    if stat.S_IMODE(resolved_node.mode) & 0o111 == 0:
        raise ValidationRunError(f"executable target lacks execute bits: {resolved}")
    executable, _payload = read_pinned_file(resolved)
    if not _file_matches_lookup_node(executable, resolved_node):
        raise ValidationRunError(f"executable resolution changed before read: {lookup_path}")
    after_leaf = _capture_lookup_node(lookup_path)
    after_resolved, after_chain, after_node = _resolve_executable_lookup(lookup_path)
    if (
        after_leaf != lookup_leaf
        or after_resolved != resolved
        or after_chain != chain
        or after_node != resolved_node
        or not _file_matches_lookup_node(executable, after_node)
    ):
        raise ValidationRunError(f"executable lookup changed while capturing: {lookup_path}")
    return ExecutableProvenance(lookup_leaf, chain, resolved_node, executable)


def verify_executable_provenance(expected: ExecutableProvenance) -> None:
    current = capture_executable_provenance(expected.lookup_leaf.path)
    if current != expected:
        raise ValidationRunError(
            f"pinned executable lookup changed during run: {expected.lookup_leaf.path}"
        )


def public_lookup_snapshot(snapshot: PathLookupSnapshot) -> dict[str, Any]:
    kind = "symlink" if snapshot.symlink_target is not None else (
        "directory" if stat.S_ISDIR(snapshot.mode) else "regular"
    )
    record: dict[str, Any] = {
        "ctime_ns": snapshot.ctime_ns,
        "device": snapshot.device,
        "inode": snapshot.inode,
        "kind": kind,
        "link_count": snapshot.link_count,
        "mode": f"{stat.S_IMODE(snapshot.mode):04o}",
        "mtime_ns": snapshot.mtime_ns,
        "path": str(snapshot.path),
        "size": snapshot.size,
    }
    if snapshot.symlink_target is not None:
        record["symlink_target"] = snapshot.symlink_target
    return record


def public_executable_provenance(provenance: ExecutableProvenance) -> dict[str, Any]:
    return {
        "lookup_leaf": public_lookup_snapshot(provenance.lookup_leaf),
        "resolved_executable": public_snapshot(provenance.executable),
        "resolved_leaf": public_lookup_snapshot(provenance.resolved_leaf),
        "symlink_chain": [public_lookup_snapshot(row) for row in provenance.symlink_chain],
    }


def _find_fixed_command(name: str) -> Path:
    if name == "rg":
        path = PINNED_RG_PATH
    else:
        path = next(
            (Path(directory) / name for directory in ("/usr/bin", "/bin")
             if (Path(directory) / name).exists()),
            None,
        )
        if path is None:
            raise ValidationRunError(f"required auxiliary command is missing: {name}")
    return path


def capture_executables(
) -> tuple[dict[str, FileSnapshot], dict[str, ExecutableProvenance]]:
    launchers = {
        name: read_pinned_file(path.resolve(strict=True))[0]
        for name, path in LAUNCHER_PATHS.items()
    }
    auxiliaries = {
        name: capture_executable_provenance(_find_fixed_command(name))
        for name in AUXILIARY_COMMAND_NAMES
    }
    return launchers, auxiliaries


def verify_executables(*groups: dict[str, FileSnapshot]) -> None:
    seen: set[Path] = set()
    for group in groups:
        for snapshot in group.values():
            if snapshot.path not in seen:
                verify_snapshot(snapshot)
                seen.add(snapshot.path)


def verify_auxiliary_executables(group: dict[str, ExecutableProvenance]) -> None:
    for name in sorted(group):
        verify_executable_provenance(group[name])


def public_executables(group: dict[str, FileSnapshot]) -> dict[str, dict[str, Any]]:
    return {name: public_snapshot(group[name]) for name in sorted(group)}


def public_auxiliary_executables(
    group: dict[str, ExecutableProvenance],
) -> dict[str, dict[str, Any]]:
    return {name: public_executable_provenance(group[name]) for name in sorted(group)}


def load_registry_snapshot(path: Path) -> tuple[dict[str, Any], FileSnapshot]:
    snapshot, payload = read_pinned_file(path)
    try:
        registry = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationRunError(f"capability registry JSON parse failed: {exc}") from exc
    try:
        validate_data(registry, check_files=True)
    except RegistryError as exc:
        raise ValidationRunError(f"capability registry validation failed: {exc}") from exc
    if payload != canonical_json(registry):
        raise ValidationRunError("capability registry is not canonical sorted JSON")
    return registry, snapshot


def parse_validation_command(command: str) -> tuple[str, ...]:
    try:
        argv = tuple(shlex.split(command))
    except ValueError as exc:
        raise ValidationRunError(f"invalid validation command: {exc}") from exc
    if len(argv) != 2:
        raise ValidationRunError(
            "validation commands must contain exactly a launcher and local tool"
        )
    launcher, tool_text = argv
    if launcher not in ALLOWED_LAUNCHERS:
        raise ValidationRunError(f"unsupported validation launcher: {launcher}")
    tool = Path(tool_text)
    if tool.is_absolute() or ".." in tool.parts or not tool.parts:
        raise ValidationRunError("validation tool must be repository-relative")
    if tool.parts[0] != "tools":
        raise ValidationRunError("validation tool must live under tools/")
    expected_suffix = ".sh" if launcher == "bash" else ".py"
    if tool.suffix != expected_suffix:
        raise ValidationRunError(f"{launcher} validation tool must end in {expected_suffix}")
    read_pinned_file(ROOT / tool)
    return argv


def build_validation_plan(
    registry: dict[str, Any], launcher_snapshots: dict[str, FileSnapshot] | None = None,
) -> tuple[tuple[ValidationPlanEntry, ...], tuple[str, ...]]:
    if launcher_snapshots is None:
        launcher_snapshots, _auxiliaries = capture_executables()
    grouped: dict[str, list[str]] = {}
    unvalidated: list[str] = []
    for capability in registry["capabilities"]:
        command = capability["validation_command"]
        if command is None:
            if capability["classification"] not in ("unknown", "unsafe/deferred"):
                raise ValidationRunError(
                    f"active capability lacks a validator: {capability['id']}"
                )
            unvalidated.append(capability["id"])
            continue
        grouped.setdefault(command, []).append(capability["id"])

    entries: list[ValidationPlanEntry] = []
    for command, ids in sorted(grouped.items()):
        parsed = parse_validation_command(command)
        validator_snapshot, _payload = read_pinned_file(ROOT / parsed[1])
        argv = (str(launcher_snapshots[parsed[0]].path), parsed[1])
        entries.append(ValidationPlanEntry(command, argv, tuple(ids), validator_snapshot))
    plan = tuple(entries)
    covered = sum(len(entry.capability_ids) for entry in plan)
    if covered + len(unvalidated) != len(registry["capabilities"]):
        raise ValidationRunError("validation plan does not cover the registry exactly")
    assert_exact_plan(registry, plan, tuple(unvalidated))
    return plan, tuple(unvalidated)


def assert_exact_plan(
    registry: dict[str, Any],
    plan: Sequence[ValidationPlanEntry],
    unvalidated: Sequence[str],
) -> None:
    covered = sum(len(entry.capability_ids) for entry in plan)
    actual = (len(registry["capabilities"]), covered, len(unvalidated), len(plan))
    expected = (
        EXPECTED_CAPABILITIES,
        EXPECTED_COVERED_CAPABILITIES,
        EXPECTED_DEFERRED_CAPABILITIES,
        EXPECTED_UNIQUE_VALIDATORS,
    )
    if actual != expected:
        raise ValidationRunError(
            "canonical capability counts changed: "
            f"actual={actual} expected={expected}"
        )
    if tuple(unvalidated) != EXPECTED_DEFERRED_IDS:
        raise ValidationRunError("canonical deferred capability IDs changed")


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _bounded_stop_process_group(process: subprocess.Popen[Any]) -> None:
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    terminate_deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
    while _process_group_exists(process_group_id):
        remaining = terminate_deadline - time.monotonic()
        if remaining <= 0:
            break
        if process.poll() is None:
            try:
                process.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                pass
        else:
            time.sleep(min(0.01, remaining))
    if _process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        # The direct child can only remain here in an uninterruptible kernel
        # state.  Do not turn a configured timeout into an unbounded wait.
        return


def _execution_from_bytes(status: str, returncode: int | None, payload: bytes) -> CommandExecution:
    output = payload.decode("utf-8", errors="replace")
    lines = [line for line in output.splitlines() if line.strip()]
    return CommandExecution(
        status=status,
        returncode=returncode,
        output_sha256=hashlib.sha256(payload).hexdigest(),
        output_bytes=len(payload),
        final_line=lines[-1] if lines else "",
        output=output,
        output_truncated=False,
    )


def _read_captured_output(descriptor: int) -> CommandExecution:
    size = os.fstat(descriptor).st_size
    digest = hashlib.sha256()
    tail = bytearray()
    offset = 0
    while offset < size:
        chunk = os.pread(descriptor, min(1024 * 1024, size - offset), offset)
        if not chunk:
            raise ValidationRunError("short read from validator output capture")
        digest.update(chunk)
        tail.extend(chunk)
        if len(tail) > OUTPUT_TAIL_BYTES:
            del tail[:-OUTPUT_TAIL_BYTES]
        offset += len(chunk)
    output = bytes(tail).decode("utf-8", errors="replace")
    lines = [line for line in output.splitlines() if line.strip()]
    return CommandExecution(
        status="passed",
        returncode=0,
        output_sha256=digest.hexdigest(),
        output_bytes=size,
        final_line=lines[-1] if lines else "",
        output=output,
        output_truncated=size > len(tail),
    )


def execute_command(
    argv: tuple[str, ...], environment: dict[str, str], timeout_seconds: float,
) -> CommandExecution:
    with tempfile.TemporaryFile(mode="w+b", dir="/tmp") as capture:
        try:
            process = subprocess.Popen(
                argv,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=capture,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            return _execution_from_bytes(
                "failed", None, f"could not start validator: {exc}\n".encode()
            )
        status = "failed"
        returncode: int | None = None
        try:
            process.wait(timeout=timeout_seconds)
            returncode = process.returncode
            status = "passed" if returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            _bounded_stop_process_group(process)
            status = "timed-out"
        except KeyboardInterrupt:
            _bounded_stop_process_group(process)
            raise
        capture.flush()
        observed = _read_captured_output(capture.fileno())
        return CommandExecution(
            status=status,
            returncode=returncode,
            output_sha256=observed.output_sha256,
            output_bytes=observed.output_bytes,
            final_line=observed.final_line,
            output=observed.output,
            output_truncated=observed.output_truncated,
        )


def run_entry(
    entry: ValidationPlanEntry,
    timeout_seconds: float,
    environment: dict[str, str] | None = None,
) -> ValidationResult:
    verify_snapshot(entry.validator_snapshot)
    started = time.monotonic()
    execution = execute_command(
        entry.argv,
        dict(FIXED_ENVIRONMENT if environment is None else environment),
        timeout_seconds,
    )
    elapsed = time.monotonic() - started
    verify_snapshot(entry.validator_snapshot)
    return ValidationResult(
        command=entry.command,
        capability_ids=entry.capability_ids,
        status=execution.status,
        returncode=execution.returncode,
        elapsed_seconds=elapsed,
        output_sha256=execution.output_sha256,
        output_bytes=execution.output_bytes,
        final_line=execution.final_line,
        output=execution.output,
        output_truncated=execution.output_truncated,
        validator_snapshot=entry.validator_snapshot,
    )


def result_record(result: ValidationResult) -> dict[str, Any]:
    return {
        "capability_ids": list(result.capability_ids),
        "command": result.command,
        "elapsed_seconds": round(result.elapsed_seconds, 3),
        "final_line": result.final_line,
        "output_bytes": result.output_bytes,
        "output_sha256": result.output_sha256,
        "output_truncated": result.output_truncated,
        "returncode": result.returncode,
        "status": result.status,
        "validator": public_snapshot(result.validator_snapshot),
    }


def run_plan(
    plan: Sequence[ValidationPlanEntry],
    timeout_seconds: float,
    control_manifest: FileManifest,
    environment: dict[str, str],
) -> tuple[ValidationResult, ...]:
    results: list[ValidationResult] = []
    total = len(plan)
    for index, entry in enumerate(plan, start=1):
        verify_manifest(control_manifest, control_paths)
        print(
            f"[{index:02d}/{total:02d}] RUN  {entry.command} "
            f"capabilities={len(entry.capability_ids)}",
            flush=True,
        )
        result = run_entry(entry, timeout_seconds, environment)
        verify_manifest(control_manifest, control_paths)
        results.append(result)
        print(
            f"[{index:02d}/{total:02d}] {result.status.upper():9s} "
            f"elapsed={result.elapsed_seconds:.3f}s output_sha256={result.output_sha256}",
            flush=True,
        )
        if result.status != "passed" and result.output:
            if result.output_truncated:
                print("[validator output truncated to final 1 MiB]")
            print(result.output, end="" if result.output.endswith("\n") else "\n")
    return tuple(results)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def publication_contract() -> dict[str, str]:
    return {
        "commit_point": "successful exclusive no-replace hard-link creation",
        "destination_mode": "0600",
        "method": REPORT_PUBLICATION_METHOD,
        "post_commit_failure_policy": (
            "leave the destination untouched; a complete receipt may remain "
            "when the runner exits unsuccessfully"
        ),
        "verification_scope": (
            "pinned parent descriptor plus lexical ancestor and final-leaf "
            "identity checks through the post-directory-fsync boundary"
        ),
    }


@dataclass(frozen=True)
class ReportDirectoryPin:
    lexical_path: Path
    component: str
    descriptor: int
    device: int
    inode: int


@dataclass(frozen=True)
class ReportParentPin:
    output_path: Path
    directories: tuple[ReportDirectoryPin, ...]

    @property
    def descriptor(self) -> int:
        return self.directories[-1].descriptor


def _close_descriptors_once(
    descriptors: Sequence[tuple[str, int | None]],
    primary_error: BaseException | None,
) -> None:
    """Close each acquired descriptor once without masking an active error."""

    failures: list[tuple[str, BaseException]] = []
    for label, descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except BaseException as exc:
            failures.append((label, exc))
    if not failures:
        return
    if primary_error is not None:
        for label, failure in failures:
            primary_error.add_note(f"{label} descriptor close failed: {failure}")
        return
    first_label, first_failure = failures[0]
    first_failure.add_note(f"while closing {first_label} descriptor")
    for label, failure in failures[1:]:
        first_failure.add_note(f"{label} descriptor close also failed: {failure}")
    raise first_failure


def _report_parent_close_entries(
    pin: ReportParentPin,
) -> tuple[tuple[str, int], ...]:
    return tuple(
        (f"report directory {row.lexical_path}", row.descriptor)
        for row in reversed(pin.directories)
    )


def _open_checked_report_parent(path: Path) -> ReportParentPin:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.name in ("", ".", "..")
    ):
        raise ValidationRunError("report output must be an absolute normalized path")
    if _is_within(path, ROOT):
        raise ValidationRunError(
            "report output must be outside the repository snapshot tree"
        )
    _require_no_symlink_ancestors(path)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    opened_rows: list[ReportDirectoryPin] = []
    acquired: list[tuple[str, int]] = []
    try:
        root_path = Path(path.anchor)
        root_before = root_path.lstat()
        root_descriptor = os.open(root_path, flags)
        acquired.append((f"report directory {root_path}", root_descriptor))
        root_opened = os.fstat(root_descriptor)
        if (
            not stat.S_ISDIR(root_before.st_mode)
            or stat.S_ISLNK(root_before.st_mode)
            or not stat.S_ISDIR(root_opened.st_mode)
            or (root_opened.st_dev, root_opened.st_ino)
            != (root_before.st_dev, root_before.st_ino)
        ):
            raise ValidationRunError("report root directory identity changed")
        opened_rows.append(
            ReportDirectoryPin(
                root_path,
                "",
                root_descriptor,
                root_opened.st_dev,
                root_opened.st_ino,
            )
        )
        lexical = root_path
        for component in path.parent.parts[1:]:
            lexical /= component
            parent_descriptor = opened_rows[-1].descriptor
            before = os.stat(
                component, dir_fd=parent_descriptor, follow_symlinks=False
            )
            if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
                raise ValidationRunError(
                    f"report ancestor must be a non-symlink directory: {lexical}"
                )
            descriptor = os.open(component, flags, dir_fd=parent_descriptor)
            acquired.append((f"report directory {lexical}", descriptor))
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise ValidationRunError(
                    f"report ancestor identity changed while opening: {lexical}"
                )
            opened_rows.append(
                ReportDirectoryPin(
                    lexical,
                    component,
                    descriptor,
                    opened.st_dev,
                    opened.st_ino,
                )
            )
        pin = ReportParentPin(path, tuple(opened_rows))
        _verify_report_parent(path, pin)
        return pin
    except OSError as exc:
        wrapped = ValidationRunError(
            f"could not pin report directory chain: {exc}"
        )
        _close_descriptors_once(
            tuple(reversed(acquired)),
            wrapped,
        )
        raise wrapped from exc
    except BaseException as exc:
        _close_descriptors_once(
            tuple(reversed(acquired)),
            exc,
        )
        raise


def _verify_report_parent(
    path: Path,
    pin: ReportParentPin,
) -> None:
    if path != pin.output_path:
        raise ValidationRunError("report parent pin belongs to a different output")
    _require_no_symlink_ancestors(path)
    if not pin.directories:
        raise ValidationRunError("report parent descriptor chain is empty")
    for index, row in enumerate(pin.directories):
        opened = os.fstat(row.descriptor)
        expected_identity = (row.device, row.inode)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != expected_identity
        ):
            raise ValidationRunError(
                f"pinned report directory descriptor changed: {row.lexical_path}"
            )
        if index == 0:
            current = row.lexical_path.lstat()
        else:
            previous = pin.directories[index - 1]
            current = os.stat(
                row.component,
                dir_fd=previous.descriptor,
                follow_symlinks=False,
            )
        if (
            not stat.S_ISDIR(current.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or (current.st_dev, current.st_ino) != expected_identity
        ):
            raise ValidationRunError(
                f"report directory chain identity changed: {row.lexical_path}"
            )
    lexical_parent = path.parent.lstat()
    final_pin = pin.directories[-1]
    if (
        not stat.S_ISDIR(lexical_parent.st_mode)
        or stat.S_ISLNK(lexical_parent.st_mode)
        or (lexical_parent.st_dev, lexical_parent.st_ino)
        != (final_pin.device, final_pin.inode)
    ):
        raise ValidationRunError("report parent pathname identity changed")


def _target_exists(parent_descriptor: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def validate_report_output(path: Path) -> None:
    parent = _open_checked_report_parent(path)
    try:
        if _target_exists(parent.descriptor, path.name):
            raise ValidationRunError(f"report output already exists: {path}")
        _verify_report_parent(path, parent)
    finally:
        _close_descriptors_once(_report_parent_close_entries(parent), sys.exception())


def _write_all(descriptor: int, payload: bytes) -> None:
    written = 0
    while written < len(payload):
        count = os.write(descriptor, payload[written:])
        if count <= 0:
            raise OSError("short write while publishing validation receipt")
        written += count


def _verify_report_stage(
    descriptor: int,
    payload: bytes,
    *,
    expected_link_count: int,
) -> os.stat_result:
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    before = os.fstat(descriptor)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != expected_link_count
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size != len(payload)
    ):
        raise ValidationRunError("report staging descriptor metadata differs")
    digest = hashlib.sha256()
    offset = 0
    while offset < len(payload):
        chunk = os.pread(descriptor, min(1024 * 1024, len(payload) - offset), offset)
        if not chunk:
            raise ValidationRunError("short read from report staging descriptor")
        digest.update(chunk)
        offset += len(chunk)
    if os.pread(descriptor, 1, len(payload)):
        raise ValidationRunError("report staging descriptor grew while reading")
    after = os.fstat(descriptor)
    # ``before`` and ``after`` are both os.fstat of this one descriptor: two fd
    # stats, which agree on st_ctime_ns on every platform, Windows included, so
    # the change time stays in this fingerprint.
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_nlink,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_nlink,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_after != identity_before or digest.hexdigest() != expected_sha256:
        raise ValidationRunError("report staging descriptor changed while reading")
    return after


def _verify_published_report(
    parent_descriptor: int,
    name: str,
    staging_descriptor: int,
    payload: bytes,
) -> None:
    staged = _verify_report_stage(
        staging_descriptor, payload, expected_link_count=1
    )
    try:
        published = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise ValidationRunError("published report destination disappeared") from exc
    if (
        not stat.S_ISREG(published.st_mode)
        or published.st_nlink != 1
        or (published.st_dev, published.st_ino) != (staged.st_dev, staged.st_ino)
        or stat.S_IMODE(published.st_mode) != 0o600
        or published.st_size != len(payload)
    ):
        raise ValidationRunError("published report identity, mode, or size differs")


def publish_report(path: Path, payload: bytes) -> None:
    parent = _open_checked_report_parent(path)
    parent_descriptor = parent.descriptor
    stage: platform_compat.PrivateStage | None = None
    try:
        if _target_exists(parent_descriptor, path.name):
            raise ValidationRunError(f"report output already exists: {path}")
        _verify_report_parent(path, parent)
        # Only the OS-primitive layer differs per platform.  Linux stages an
        # anonymous O_TMPFILE and publishes it with os.link out of /proc/self/fd
        # -- byte-for-byte the historical path, including the deliberate refusal
        # to degrade to a named fallback when O_TMPFILE itself is unsupported on
        # the private cache filesystem.  macOS (no O_TMPFILE) stages a private
        # O_EXCL temp in the same directory and publishes it with os.link +
        # unlink.  Windows has no directory descriptor, so this whole transaction
        # is unreachable there and the sibling tests skip it.
        try:
            stage = platform_compat.open_private_stage(
                parent_descriptor, prefix=".validation-report."
            )
        except OSError as exc:
            detail = errno.errorcode.get(exc.errno, str(exc.errno))
            staging_kind = (
                "anonymous O_TMPFILE" if getattr(os, "O_TMPFILE", 0) else "private named"
            )
            raise ValidationRunError(
                f"could not allocate {staging_kind} report staging storage: {detail}"
            ) from exc
        descriptor = stage.descriptor
        os.fchmod(descriptor, 0o600)
        _verify_report_stage(descriptor, b"", expected_link_count=stage.link_count)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        _verify_report_stage(descriptor, payload, expected_link_count=stage.link_count)
        _verify_report_parent(path, parent)
        try:
            platform_compat.publish_private_stage(
                stage, path.name, dir_fd=parent_descriptor
            )
        except FileExistsError as exc:
            raise ValidationRunError(f"report output already exists: {path}") from exc
        except OSError as exc:
            raise ValidationRunError("could not link report staging storage") from exc
        _verify_published_report(parent_descriptor, path.name, descriptor, payload)
        _verify_report_parent(path, parent)
        # Commit through the directory descriptor this publication pinned, never
        # by re-opening the directory by name.  POSIX issues the same single
        # fsync; Windows has no directory-flush primitive and the helper reports
        # that instead of letting a skipped flush look like a completed one.
        platform_compat.fsync_directory_fd(parent_descriptor)
        _verify_report_parent(path, parent)
        _verify_published_report(parent_descriptor, path.name, descriptor, payload)
        _verify_report_parent(path, parent)
    finally:
        staging_descriptor = stage.descriptor if stage is not None else None
        # A named staging temp (the non-O_TMPFILE path) that outlived an aborted
        # publish must be removed so the report directory is left exactly as
        # found.  A successful publish already unlinked it; an anonymous
        # O_TMPFILE stage has no name to remove -- so this never path-unlinks on
        # Linux, which the sibling test asserts.
        if stage is not None and stage.staging_name is not None:
            if _target_exists(parent_descriptor, stage.staging_name):
                try:
                    os.unlink(stage.staging_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
        _close_descriptors_once(
            (
                ("report staging", staging_descriptor),
            ) + _report_parent_close_entries(parent),
            sys.exception(),
        )


def _validate_result_coverage(
    registry: dict[str, Any],
    results: Sequence[ValidationResult],
    unvalidated: Sequence[str],
) -> None:
    if len(results) != EXPECTED_UNIQUE_VALIDATORS:
        raise ValidationRunError("result count differs from the exact validation plan")
    if len({row.command for row in results}) != len(results):
        raise ValidationRunError("duplicate validator results")
    statuses = {row.status for row in results}
    if not statuses <= {"passed", "failed", "timed-out"}:
        raise ValidationRunError("validator result contains an unknown status")
    covered = [identifier for row in results for identifier in row.capability_ids]
    if len(covered) != len(set(covered)) or len(covered) != EXPECTED_COVERED_CAPABILITIES:
        raise ValidationRunError("result capability coverage is not exact")
    registry_ids = {row["id"] for row in registry["capabilities"]}
    if set(covered) | set(unvalidated) != registry_ids:
        raise ValidationRunError("result and deferred capability IDs do not cover registry")


def write_report(
    path: Path,
    registry: dict[str, Any],
    registry_snapshot: FileSnapshot,
    results: Sequence[ValidationResult],
    unvalidated: Sequence[str],
    started_at: str,
    finished_at: str,
    timeout_seconds: float,
    environment: dict[str, str],
    control_manifest: FileManifest,
    evidence_manifest: FileManifest,
    launchers: dict[str, FileSnapshot],
    auxiliaries: dict[str, ExecutableProvenance],
    root_snapshots: dict[str, FileSnapshot],
) -> None:
    validate_report_output(path)
    _validate_result_coverage(registry, results, unvalidated)
    passed = sum(result.status == "passed" for result in results)
    failed = len(results) - passed
    report = {
        "auxiliary_commands": public_auxiliary_executables(auxiliaries),
        "capabilities": len(registry["capabilities"]),
        "capabilities_without_validator": list(unvalidated),
        "control_manifest": public_manifest(control_manifest, CONTROL_POLICY),
        "covered_capabilities": sum(len(result.capability_ids) for result in results),
        "environment": dict(sorted(environment.items())),
        "evidence_manifest": public_manifest(evidence_manifest, EVIDENCE_POLICY),
        "failed_validators": failed,
        "finished_at_utc": finished_at,
        "launchers": public_executables(launchers),
        "overall_status": "passed" if failed == 0 else "failed",
        "passed_validators": passed,
        "publication_contract": publication_contract(),
        "registry": public_snapshot(registry_snapshot),
        "registry_schema": registry["schema"],
        "residual_limitation": REPORT_RESIDUAL_LIMITATION,
        "results": [result_record(result) for result in results],
        "root_of_trust": {
            name: public_snapshot(root_snapshots[name]) for name in sorted(root_snapshots)
        },
        "schema": REPORT_SCHEMA,
        "started_at_utc": started_at,
        "timeout_seconds": timeout_seconds,
        "unique_validators": len(results),
    }
    publish_report(path, canonical_json(report))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--list", action="store_true", dest="list_only")
    args = parser.parse_args(argv)
    if not (0.0 < args.timeout_seconds <= 7200.0):
        parser.error("--timeout-seconds must be greater than 0 and at most 7200")

    registry_path = args.registry if args.registry.is_absolute() else Path.cwd() / args.registry
    registry, registry_snapshot = load_registry_snapshot(registry_path)
    launchers, auxiliaries = capture_executables()
    plan, unvalidated = build_validation_plan(registry, launchers)
    if args.list_only:
        for entry in plan:
            print(f"{entry.command}\t{','.join(entry.capability_ids)}")
        print(
            "MOD_EDITOR_CAPABILITY_VALIDATION_PLAN_OK "
            f"capabilities={len(registry['capabilities'])} "
            f"covered={sum(len(entry.capability_ids) for entry in plan)} "
            f"deferred_without_validator={len(unvalidated)} "
            f"unique_validators={len(plan)}"
        )
        return 0

    report_path: Path | None = None
    if args.report is not None:
        report_path = args.report if args.report.is_absolute() else Path.cwd() / args.report
        validate_report_output(report_path)

    started_at = _now_utc()
    environment = dict(FIXED_ENVIRONMENT)
    control_manifest = capture_control_manifest()
    evidence_manifest = capture_evidence_manifest()
    root_snapshots = {
        "registry_schema": read_pinned_file(REGISTRY_SCHEMA_PATH)[0],
        "registry_validator": read_pinned_file(REGISTRY_VALIDATOR_PATH)[0],
        "runner": read_pinned_file(RUNNER_PATH)[0],
        "wrapper": read_pinned_file(WRAPPER_PATH)[0],
    }
    results = run_plan(plan, args.timeout_seconds, control_manifest, environment)
    verify_manifest(control_manifest, control_paths)
    verify_manifest(evidence_manifest, evidence_paths)
    verify_snapshot(registry_snapshot)
    verify_executables(launchers)
    verify_auxiliary_executables(auxiliaries)
    for snapshot in root_snapshots.values():
        verify_snapshot(snapshot)
    finished_at = _now_utc()
    if report_path is not None:
        write_report(
            report_path,
            registry,
            registry_snapshot,
            results,
            unvalidated,
            started_at,
            finished_at,
            args.timeout_seconds,
            environment,
            control_manifest,
            evidence_manifest,
            launchers,
            auxiliaries,
            root_snapshots,
        )
    passed = sum(result.status == "passed" for result in results)
    failed = len(results) - passed
    marker = "PASS" if failed == 0 else "FAIL"
    print(
        f"MOD_EDITOR_ALL_CAPABILITY_VALIDATION_{marker} "
        f"capabilities={len(registry['capabilities'])} "
        f"covered={sum(len(result.capability_ids) for result in results)} "
        f"deferred_without_validator={len(unvalidated)} "
        f"unique_validators={len(results)} passed={passed} failed={failed}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        status_code = main()
    except ValidationRunError as exc:
        print(f"MOD_EDITOR_ALL_CAPABILITY_VALIDATION_ERROR {exc}", file=sys.stderr)
        status_code = 2
    except KeyboardInterrupt:
        print("MOD_EDITOR_ALL_CAPABILITY_VALIDATION_INTERRUPTED", file=sys.stderr)
        status_code = 130
    raise SystemExit(status_code)
