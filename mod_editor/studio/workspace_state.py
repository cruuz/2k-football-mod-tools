"""Private recent-file and crash-recovery state for 2K5 Mod Studio.

This module deliberately stores only local path metadata, source hashes, and a
path to a normal replacement-only ``.2k5mod`` archive.  It never copies an
XISO, extracted resource, retail preview, or original asset into workspace
state.  The recovery archive is produced by the same validated project writer
as a user-requested project, so recovering a session cannot quietly introduce
a second, less-safe persistence format.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Iterable
from uuid import uuid4

from mod_editor.core.errors import ValidationError


WORKSPACE_STATE_SCHEMA = "2k5_mod_studio_workspace_state/v1"
RECOVERY_PROJECT_NAME = "unsaved-recovery.2k5mod"
MAX_RECENT_ITEMS = 8
MAX_STATE_BYTES = 256 * 1024


def default_workspace_state_root() -> Path:
    """Return the XDG-compatible private state directory used by the app."""

    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(configured).expanduser() if configured else (
        Path.home() / ".local" / "state"
    )
    return base / "2k5-mod-studio"


def _canonical_path(path: Path, *, must_exist: bool) -> Path:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        supplied = Path.cwd() / supplied
    supplied = Path(os.path.abspath(os.fspath(supplied)))
    return supplied.resolve(strict=True) if must_exist else supplied


def _validate_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValidationError("Workspace source SHA-256 metadata is invalid.")
    return normalized


def _unique_recent(paths: Iterable[str], newest: str) -> tuple[str, ...]:
    result = [newest]
    for value in paths:
        if isinstance(value, str) and value and value != newest:
            result.append(value)
        if len(result) >= MAX_RECENT_ITEMS:
            break
    return tuple(result)


@dataclass(frozen=True)
class RecoveryCandidate:
    source_path: Path
    source_sha256: str | None
    project_path: Path


@dataclass(frozen=True)
class WorkspaceState:
    recent_sources: tuple[str, ...] = ()
    recent_projects: tuple[str, ...] = ()
    recovery_source_path: str | None = None
    recovery_source_sha256: str | None = None
    recovery_project_path: str | None = None

    @property
    def has_recovery_metadata(self) -> bool:
        return bool(self.recovery_source_path and self.recovery_project_path)


class WorkspaceStateStore:
    """Atomic, private persistence for recent paths and recovery metadata."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = _canonical_path(root or default_workspace_state_root(), must_exist=False)
        self._ensure_root()
        self.root = self.root.resolve(strict=True)
        self.state_path = self.root / "workspace-state.json"
        self.recovery_path = self.root / RECOVERY_PROJECT_NAME

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValidationError(
                "The 2K5 Mod Studio state location must be a private folder, not a link."
            )
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            # Some mounted filesystems do not implement Unix mode bits. The
            # no-symlink and atomic-publication checks still apply.
            pass

    def read(self) -> WorkspaceState:
        if not self.state_path.exists():
            return WorkspaceState()
        try:
            info = self.state_path.lstat()
        except FileNotFoundError:
            return WorkspaceState()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_nlink != 1
            or not 0 < info.st_size <= MAX_STATE_BYTES
        ):
            raise ValidationError("2K5 Mod Studio workspace state is unsafe or corrupt.")
        try:
            document = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not read workspace state: {exc}") from exc
        if not isinstance(document, dict) or set(document) != {
            "recent_projects", "recent_sources", "recovery", "schema",
        } or document.get("schema") != WORKSPACE_STATE_SCHEMA:
            raise ValidationError("2K5 Mod Studio workspace state has an unknown format.")
        recent_sources = document.get("recent_sources")
        recent_projects = document.get("recent_projects")
        recovery = document.get("recovery")
        if not isinstance(recent_sources, list) or not isinstance(recent_projects, list):
            raise ValidationError("Workspace recent-file metadata is malformed.")
        if (
            len(recent_sources) > MAX_RECENT_ITEMS
            or len(recent_projects) > MAX_RECENT_ITEMS
            or any(not isinstance(value, str) or not value for value in recent_sources)
            or any(not isinstance(value, str) or not value for value in recent_projects)
        ):
            raise ValidationError("Workspace recent-file metadata is outside its limits.")
        if recovery is None:
            return WorkspaceState(tuple(recent_sources), tuple(recent_projects))
        if not isinstance(recovery, dict) or set(recovery) != {
            "project_path", "source_path", "source_sha256",
        }:
            raise ValidationError("Workspace recovery metadata is malformed.")
        source_path = recovery.get("source_path")
        project_path = recovery.get("project_path")
        source_sha256 = recovery.get("source_sha256")
        if (
            not isinstance(source_path, str)
            or not source_path
            or not isinstance(project_path, str)
            or not project_path
            or source_sha256 is not None and not isinstance(source_sha256, str)
        ):
            raise ValidationError("Workspace recovery metadata is incomplete.")
        return WorkspaceState(
            tuple(recent_sources),
            tuple(recent_projects),
            source_path,
            _validate_sha256(source_sha256),
            project_path,
        )

    def record_source(self, path: Path, source_sha256: str | None = None) -> None:
        selected = _canonical_path(path, must_exist=True)
        info = selected.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValidationError("A recent NFL 2K5 source must be a regular file.")
        _validate_sha256(source_sha256)
        state = self.read()
        self._write(WorkspaceState(
            _unique_recent(state.recent_sources, os.fspath(selected)),
            state.recent_projects,
            state.recovery_source_path,
            state.recovery_source_sha256,
            state.recovery_project_path,
        ))

    def record_project(self, path: Path) -> None:
        selected = _canonical_path(path, must_exist=True)
        info = selected.lstat()
        if (
            selected.suffix.casefold() != ".2k5mod"
            or not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
        ):
            raise ValidationError("A recent project must be a regular .2k5mod file.")
        state = self.read()
        self._write(WorkspaceState(
            state.recent_sources,
            _unique_recent(state.recent_projects, os.fspath(selected)),
            state.recovery_source_path,
            state.recovery_source_sha256,
            state.recovery_project_path,
        ))

    def register_recovery(
        self,
        *,
        source_path: Path,
        source_sha256: str | None,
        project_path: Path,
    ) -> RecoveryCandidate:
        source = _canonical_path(source_path, must_exist=True)
        project = _canonical_path(project_path, must_exist=True)
        project_info = project.lstat()
        if (
            project != self.recovery_path
            or project.suffix.casefold() != ".2k5mod"
            or not stat.S_ISREG(project_info.st_mode)
            or stat.S_ISLNK(project_info.st_mode)
            or project_info.st_nlink != 1
        ):
            raise ValidationError(
                "Recovery must use Mod Studio's private replacement-only project path."
            )
        digest = _validate_sha256(source_sha256)
        state = self.read()
        self._write(WorkspaceState(
            _unique_recent(state.recent_sources, os.fspath(source)),
            state.recent_projects,
            os.fspath(source),
            digest,
            os.fspath(project),
        ))
        return RecoveryCandidate(source, digest, project)

    def recovery_candidate(self, *, require_source: bool = True) -> RecoveryCandidate | None:
        state = self.read()
        if not state.has_recovery_metadata:
            return None
        assert state.recovery_source_path is not None
        assert state.recovery_project_path is not None
        project = Path(state.recovery_project_path)
        try:
            project_info = project.lstat()
        except FileNotFoundError:
            return None
        if (
            project != self.recovery_path
            or not stat.S_ISREG(project_info.st_mode)
            or stat.S_ISLNK(project_info.st_mode)
            or project_info.st_nlink != 1
            or project.suffix.casefold() != ".2k5mod"
        ):
            return None
        source = Path(state.recovery_source_path)
        if require_source:
            try:
                source_info = source.lstat()
            except FileNotFoundError:
                return None
            if not stat.S_ISREG(source_info.st_mode) or stat.S_ISLNK(source_info.st_mode):
                return None
        return RecoveryCandidate(
            source, state.recovery_source_sha256, project
        )

    def clear_recovery(self, *, delete_archive: bool = True) -> None:
        state = self.read()
        if delete_archive:
            try:
                info = self.recovery_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise ValidationError(
                        "Recovery archive is not a regular private file; it was not removed."
                    )
                self.recovery_path.unlink()
        self._write(WorkspaceState(
            state.recent_sources,
            state.recent_projects,
        ))

    def _write(self, state: WorkspaceState) -> None:
        recovery: dict[str, str | None] | None = None
        if state.has_recovery_metadata:
            recovery = {
                "project_path": state.recovery_project_path,
                "source_path": state.recovery_source_path,
                "source_sha256": state.recovery_source_sha256,
            }
        payload = (json.dumps({
            "recent_projects": list(state.recent_projects),
            "recent_sources": list(state.recent_sources),
            "recovery": recovery,
            "schema": WORKSPACE_STATE_SCHEMA,
        }, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if len(payload) > MAX_STATE_BYTES:
            raise ValidationError("Workspace state exceeds its size limit.")
        temporary = self.state_path.with_name(
            f".{self.state_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self.state_path.exists():
                current = self.state_path.lstat()
                if not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
                    raise ValidationError("Workspace state destination is unsafe.")
            os.replace(temporary, self.state_path)
        finally:
            temporary.unlink(missing_ok=True)


__all__ = [
    "MAX_RECENT_ITEMS",
    "RECOVERY_PROJECT_NAME",
    "RecoveryCandidate",
    "WorkspaceState",
    "WorkspaceStateStore",
    "default_workspace_state_root",
]
