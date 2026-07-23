"""Retail-free ``.apf2k8mod`` project archives."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
import stat
import struct
import tempfile
from typing import Iterable, Mapping
from uuid import uuid4
import zipfile

from .audio_annotations import (
    AudioAnnotationError,
    AudioCueAnnotation,
    MAX_AUDIO_ANNOTATIONS,
    annotation_document,
    parse_audio_annotation_document,
    validate_audio_cue_annotations,
)
from .models import (
    AUDO_EXACT_SLOT_KIND,
    AUDO_EXACT_SLOT_WRITER_SCHEMA,
    AUSB_EXACT_SLOT_KIND,
    AUSB_EXACT_SLOT_WRITER_SCHEMA,
    DRAFT_LOGO_EDIT_ID,
    DRAFT_LOGO_INNER_INDEX,
    DRAFT_LOGO_OUTER_INDEX,
    Modification,
)
from .player_ratings import PlayerRatingsError, load_player_rating_schema
from .player_positions import PlayerPositionsError, load_player_position_schema


PROJECT_EXTENSION = ".apf2k8mod"
PROJECT_SCHEMA = "apf2k8_mod_project/v1"
TEXT_PAYLOAD_SCHEMA = "apf2k8_text_replacement/v1"
PLAYER_RATING_PAYLOAD_SCHEMA = "apf2k8_player_rating_replacement/v1"
PLAYER_POSITION_PAYLOAD_SCHEMA = "apf2k8_player_position_replacement/v1"
WORKSPACE_STATE_SCHEMA = "apf2k8_mod_studio_workspace_state/v1"
RECOVERY_PROJECT_NAME = "unsaved-recovery.apf2k8mod"
MAX_RECENT_ITEMS = 8
MAX_WORKSPACE_STATE_BYTES = 256 * 1024
# One all-ratings pass (63,112 payloads), every player position (2,254), plus
# all inventoried AUSB substreams (45,514) needs 110,880 replacement members
# before other editable assets are counted. These structural limits leave
# bounded headroom while keeping hostile archives finite.
MAX_PROJECT_FILES = 131_072
MAX_PROJECT_MANIFEST_BYTES = 128 * 1024 * 1024
MAX_REPLACEMENT_BYTES = 24 * 1024 * 1024
MAX_PROJECT_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROJECT_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_AUDIO_ANNOTATIONS_BYTES = 32 * 1024 * 1024
AUDIO_ANNOTATIONS_MEMBER = "audio-annotations.json"
# Backwards-compatible name for callers that treated the old shared bound as
# the on-disk archive limit. Expanded-size checks use the explicit bound above.
MAX_PROJECT_BYTES = MAX_PROJECT_ARCHIVE_BYTES
PROJECT_IO_CHUNK_BYTES = 1024 * 1024
RETAIL_HASHES = frozenset(
    {
        "c45aab61de93773dfe25adbae5749ad5adb3f3369a6c0106b2159ad603b6fe53",
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
        "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53",
        "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
        "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084",
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
        "39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8",
    }
)


class ProjectError(ValueError):
    """Raised when a project is unsafe or structurally invalid."""


def _reject_duplicate_json_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Reject ambiguous duplicate keys at every untrusted JSON depth."""

    accepted: dict[str, object] = {}
    for key, value in pairs:
        if key in accepted:
            raise ProjectError(
                f"Project JSON contains a duplicate object key: {key!r}"
            )
        accepted[key] = value
    return accepted


def _strict_json_document(payload: bytes, label: str) -> object:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_pairs,
        )
    except ProjectError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectError(f"{label} is not valid UTF-8 JSON: {exc}") from exc


def _canonical_audio_annotations_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _prepare_audio_annotations(
    supplied: Mapping[str, object] | Iterable[AudioCueAnnotation],
) -> tuple[tuple[AudioCueAnnotation, ...], bytes | None]:
    try:
        annotations = (
            parse_audio_annotation_document(supplied)
            if isinstance(supplied, Mapping)
            else validate_audio_cue_annotations(supplied)
        )
    except AudioAnnotationError as exc:
        raise ProjectError(str(exc)) from exc
    if not annotations:
        return (), None
    payload = _canonical_audio_annotations_json(annotation_document(annotations))
    if len(payload) > MAX_AUDIO_ANNOTATIONS_BYTES:
        raise ProjectError(
            "Audio annotations exceed the 32 MiB project metadata limit"
        )
    return annotations, payload


def default_workspace_state_root() -> Path:
    """Return the XDG-compatible private state directory used by the app."""

    exact = os.environ.get("APF2K8_MOD_STUDIO_STATE_DIR", "").strip()
    if exact:
        selected = Path(exact).expanduser()
        if not selected.is_absolute():
            raise ProjectError(
                "APF2K8_MOD_STUDIO_STATE_DIR must be an absolute path"
            )
        return selected
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    base = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state"
    )
    return base / "apf2k8-mod-studio"


def _canonical_workspace_path(path: Path, *, must_exist: bool) -> Path:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        supplied = Path.cwd() / supplied
    supplied = Path(os.path.abspath(os.fspath(supplied)))
    return supplied.resolve(strict=True) if must_exist else supplied


def _workspace_supplied_path(path: Path) -> Path:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        supplied = Path.cwd() / supplied
    return Path(os.path.abspath(os.fspath(supplied)))


def _workspace_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ProjectError("Workspace source SHA-256 metadata is invalid")
    return normalized


def _workspace_recent(values: Iterable[str], newest: str) -> tuple[str, ...]:
    result = [newest]
    for value in values:
        if isinstance(value, str) and value and value != newest:
            result.append(value)
        if len(result) >= MAX_RECENT_ITEMS:
            break
    return tuple(result)


def _safe_source_path(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return not stat.S_ISLNK(info.st_mode) and (
        stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)
    )


@dataclass(frozen=True)
class RecoveryCandidate:
    """One private replacement-only autosave bound to its exact source."""

    source_path: Path
    source_sha256: str
    project_path: Path


@dataclass(frozen=True)
class WorkspaceState:
    """Small local metadata document; it never contains retail payload bytes."""

    recent_sources: tuple[str, ...] = ()
    recent_projects: tuple[str, ...] = ()
    recovery_source_path: str | None = None
    recovery_source_sha256: str | None = None
    recovery_project_path: str | None = None

    @property
    def has_recovery_metadata(self) -> bool:
        return bool(
            self.recovery_source_path
            and self.recovery_source_sha256
            and self.recovery_project_path
        )


class WorkspaceStateStore:
    """Atomic private recent-file and replacement-only recovery metadata."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = _canonical_workspace_path(
            root or default_workspace_state_root(), must_exist=False
        )
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ProjectError(
                "The APF Mod Studio state location must be a private folder, not a link"
            )
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        self.root = self.root.resolve(strict=True)
        self.state_path = self.root / "workspace-state.json"
        self.recovery_path = self.root / RECOVERY_PROJECT_NAME

    def read(self) -> WorkspaceState:
        try:
            info = self.state_path.lstat()
        except FileNotFoundError:
            return WorkspaceState()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_nlink != 1
            or not 0 < info.st_size <= MAX_WORKSPACE_STATE_BYTES
        ):
            raise ProjectError("APF Mod Studio workspace state is unsafe or corrupt")
        descriptor = os.open(
            self.state_path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (info.st_dev, info.st_ino, info.st_size)
            ):
                raise ProjectError(
                    "APF Mod Studio workspace state changed while it was read"
                )
            chunks: list[bytes] = []
            remaining = MAX_WORKSPACE_STATE_BYTES + 1
            while remaining > 0:
                block = os.read(descriptor, min(64 * 1024, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            data = b"".join(chunks)
            after = os.fstat(descriptor)
            if (
                len(data) > MAX_WORKSPACE_STATE_BYTES
                or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                != (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_size,
                    opened.st_mtime_ns,
                )
            ):
                raise ProjectError(
                    "APF Mod Studio workspace state changed while it was read"
                )
        finally:
            os.close(descriptor)
        try:
            document = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProjectError(f"Could not read APF workspace state: {exc}") from exc
        if (
            not isinstance(document, dict)
            or set(document)
            != {"recent_projects", "recent_sources", "recovery", "schema"}
            or document.get("schema") != WORKSPACE_STATE_SCHEMA
        ):
            raise ProjectError("APF Mod Studio workspace state has an unknown format")
        recent_sources = document.get("recent_sources")
        recent_projects = document.get("recent_projects")
        recovery = document.get("recovery")
        if (
            not isinstance(recent_sources, list)
            or not isinstance(recent_projects, list)
            or len(recent_sources) > MAX_RECENT_ITEMS
            or len(recent_projects) > MAX_RECENT_ITEMS
            or any(not isinstance(value, str) or not value for value in recent_sources)
            or any(not isinstance(value, str) or not value for value in recent_projects)
        ):
            raise ProjectError("APF workspace recent-file metadata is malformed")
        if recovery is None:
            return WorkspaceState(tuple(recent_sources), tuple(recent_projects))
        if (
            not isinstance(recovery, dict)
            or set(recovery) != {"project_path", "source_path", "source_sha256"}
            or not isinstance(recovery.get("project_path"), str)
            or not recovery.get("project_path")
            or not isinstance(recovery.get("source_path"), str)
            or not recovery.get("source_path")
            or not isinstance(recovery.get("source_sha256"), str)
        ):
            raise ProjectError("APF workspace recovery metadata is malformed")
        return WorkspaceState(
            tuple(recent_sources),
            tuple(recent_projects),
            str(recovery["source_path"]),
            _workspace_sha256(str(recovery["source_sha256"])),
            str(recovery["project_path"]),
        )

    def record_source(self, path: Path, source_sha256: str) -> None:
        if _workspace_supplied_path(path).is_symlink():
            raise ProjectError(
                "A recent APF source must be a regular non-linked file or folder"
            )
        selected = _canonical_workspace_path(path, must_exist=True)
        if not _safe_source_path(selected):
            raise ProjectError(
                "A recent APF source must be a regular non-linked file or folder"
            )
        digest = _workspace_sha256(source_sha256)
        assert digest is not None
        state = self.read()
        self._write(WorkspaceState(
            _workspace_recent(state.recent_sources, os.fspath(selected)),
            state.recent_projects,
            state.recovery_source_path,
            state.recovery_source_sha256,
            state.recovery_project_path,
        ))

    def record_project(self, path: Path) -> None:
        if _workspace_supplied_path(path).is_symlink():
            raise ProjectError(
                f"A recent project must be a regular non-linked {PROJECT_EXTENSION} file"
            )
        selected = _canonical_workspace_path(path, must_exist=True)
        info = selected.lstat()
        if (
            selected.suffix.casefold() != PROJECT_EXTENSION
            or not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_nlink != 1
        ):
            raise ProjectError(
                f"A recent project must be a regular non-linked {PROJECT_EXTENSION} file"
            )
        state = self.read()
        self._write(WorkspaceState(
            state.recent_sources,
            _workspace_recent(state.recent_projects, os.fspath(selected)),
            state.recovery_source_path,
            state.recovery_source_sha256,
            state.recovery_project_path,
        ))

    def register_recovery(
        self,
        *,
        source_path: Path,
        source_sha256: str,
        project_path: Path,
    ) -> RecoveryCandidate:
        if (
            _workspace_supplied_path(source_path).is_symlink()
            or _workspace_supplied_path(project_path).is_symlink()
        ):
            raise ProjectError(
                "Recovery must use regular non-linked source and private project paths"
            )
        source = _canonical_workspace_path(source_path, must_exist=True)
        project = _canonical_workspace_path(project_path, must_exist=True)
        if not _safe_source_path(source):
            raise ProjectError("Recovery source is no longer a regular file or folder")
        project_info = project.lstat()
        if (
            project != self.recovery_path
            or project.suffix.casefold() != PROJECT_EXTENSION
            or not stat.S_ISREG(project_info.st_mode)
            or stat.S_ISLNK(project_info.st_mode)
            or project_info.st_nlink != 1
        ):
            raise ProjectError(
                "Recovery must use Mod Studio's private replacement-only project path"
            )
        digest = _workspace_sha256(source_sha256)
        assert digest is not None
        try:
            os.chmod(project, 0o600)
        except OSError:
            pass
        state = self.read()
        candidate = RecoveryCandidate(source, digest, project)
        self._write(WorkspaceState(
            _workspace_recent(state.recent_sources, os.fspath(source)),
            state.recent_projects,
            os.fspath(source),
            digest,
            os.fspath(project),
        ))
        return candidate

    def recovery_candidate(
        self, *, require_source: bool = True
    ) -> RecoveryCandidate | None:
        state = self.read()
        if not state.has_recovery_metadata:
            return None
        assert state.recovery_source_path is not None
        assert state.recovery_source_sha256 is not None
        assert state.recovery_project_path is not None
        project = Path(state.recovery_project_path)
        try:
            project_info = project.lstat()
        except FileNotFoundError:
            return None
        if (
            project != self.recovery_path
            or project.suffix.casefold() != PROJECT_EXTENSION
            or not stat.S_ISREG(project_info.st_mode)
            or stat.S_ISLNK(project_info.st_mode)
            or project_info.st_nlink != 1
        ):
            return None
        source = Path(state.recovery_source_path)
        if require_source and not _safe_source_path(source):
            return None
        return RecoveryCandidate(source, state.recovery_source_sha256, project)

    def clear_recovery(
        self,
        *,
        expected: RecoveryCandidate | None = None,
        delete_archive: bool = True,
    ) -> bool:
        state = self.read()
        if expected is not None:
            current = self.recovery_candidate(require_source=False)
            if current != expected:
                return False
        if delete_archive:
            try:
                info = self.recovery_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if (
                    not stat.S_ISREG(info.st_mode)
                    or stat.S_ISLNK(info.st_mode)
                    or info.st_nlink != 1
                ):
                    raise ProjectError(
                        "Recovery archive is not a regular private file; it was not removed"
                    )
                self.recovery_path.unlink()
        self._write(WorkspaceState(
            state.recent_sources,
            state.recent_projects,
        ))
        return True

    def clear_recovery_for_source(
        self, source_path: Path | None, source_sha256: str | None
    ) -> bool:
        if source_path is None or source_sha256 is None:
            return False
        candidate = self.recovery_candidate(require_source=False)
        if candidate is None:
            return False
        try:
            selected = _canonical_workspace_path(source_path, must_exist=False)
            digest = _workspace_sha256(source_sha256)
        except ProjectError:
            return False
        if candidate.source_path != selected or candidate.source_sha256 != digest:
            return False
        return self.clear_recovery(expected=candidate)

    def _write(self, state: WorkspaceState) -> None:
        recovery: dict[str, str] | None = None
        if state.has_recovery_metadata:
            assert state.recovery_project_path is not None
            assert state.recovery_source_path is not None
            assert state.recovery_source_sha256 is not None
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
        if len(payload) > MAX_WORKSPACE_STATE_BYTES:
            raise ProjectError("APF workspace state exceeds its size limit")
        temporary = self.state_path.with_name(
            f".{self.state_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if os.path.lexists(self.state_path):
                current = self.state_path.lstat()
                if (
                    not stat.S_ISREG(current.st_mode)
                    or stat.S_ISLNK(current.st_mode)
                    or current.st_nlink != 1
                ):
                    raise ProjectError("APF workspace state destination is unsafe")
            os.replace(temporary, self.state_path)
            try:
                parent_descriptor = os.open(
                    self.root,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                )
            except OSError:
                return
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
        finally:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class ProjectTargetIdentity:
    """Private fingerprint for the exact regular project file being edited.

    The fingerprint is kept in memory only.  It lets a named-document fast save
    prove that the destination still names the same single-linked file that Mod
    Studio opened or last published before atomically replacing it.
    """

    path: Path
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


def _project_path(path: Path, *, create_parent: bool) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = Path(os.path.abspath(os.fspath(requested)))
    if requested.suffix.casefold() != PROJECT_EXTENSION:
        raise ProjectError(
            f"APF Mod Studio projects must use the {PROJECT_EXTENSION} extension."
        )
    if create_parent:
        requested.parent.mkdir(parents=True, exist_ok=True)
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise ProjectError("The selected project folder does not exist") from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise ProjectError("Choose a project folder that is a regular, non-linked folder")
    return requested


def project_target_identity(path: Path) -> ProjectTargetIdentity:
    """Capture a fail-closed identity for one named ``.apf2k8mod`` file."""

    requested = _project_path(path, create_parent=False)
    try:
        before = requested.lstat()
    except FileNotFoundError as exc:
        raise ProjectError(
            "The active project file is missing. Use Save Project As to choose "
            "a new destination."
        ) from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ProjectError(
            "The active project target is no longer a regular, non-linked file. "
            "Use Save Project As to choose a safe destination."
        )
    try:
        descriptor = os.open(
            requested,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except FileNotFoundError as exc:
        raise ProjectError(
            "The active project file disappeared. Use Save Project As to choose "
            "a new destination."
        ) from exc
    except OSError as exc:
        raise ProjectError(
            "The active project target could not be opened safely. Use Save "
            "Project As to choose a new destination."
        ) from exc
    try:
        opened = os.fstat(descriptor)
        try:
            resolved = requested.resolve(strict=True)
            after = requested.lstat()
        except FileNotFoundError as exc:
            raise ProjectError(
                "The active project changed while Mod Studio checked it. Use "
                "Save Project As or reopen it."
            ) from exc
        opened_key = (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or stat.S_ISLNK(after.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or after.st_nlink != 1
            or opened_key
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ProjectError(
                "The active project changed while Mod Studio checked it. Use "
                "Save Project As or reopen it."
            )
        return ProjectTargetIdentity(resolved, *opened_key)
    finally:
        os.close(descriptor)


def _publish_archive(
    temporary: Path,
    destination: Path,
    *,
    replace: bool,
    expected_target: ProjectTargetIdentity | None,
) -> None:
    if expected_target is not None:
        if not replace:
            raise ProjectError(
                "Fast-save target protection requires an atomic replacement"
            )
        current = project_target_identity(destination)
        if current != expected_target:
            raise ProjectError(
                "The active project changed outside Mod Studio. It was not "
                "overwritten; use Save Project As or reopen it first."
            )
    if os.path.lexists(destination):
        current = destination.lstat()
        if not replace:
            raise FileExistsError(destination)
        if (
            not stat.S_ISREG(current.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or current.st_nlink != 1
        ):
            raise ProjectError(
                "Project destination must be a regular, non-linked file. Use "
                "Save Project As to choose a safe destination."
            )
        os.replace(temporary, destination)
        return
    try:
        # The private temporary source is a regular file created by us; the
        # destination is created exclusively and therefore needs no link-follow
        # option. Keeping the two-argument call also leaves the publication
        # race easy to exercise in focused tests.
        os.link(temporary, destination)
    except FileExistsError:
        # Preserve the public collision contract used by callers to explain
        # that a new destination appeared after the save dialog was accepted.
        raise


def _payload_name(asset_id: str, kind: str) -> str:
    suffix = (
        ".json"
        if kind in {
            "localization_text",
            "roster_identity_text",
            "player_base_rating",
            "player_position",
        }
        else ".xma1-packets"
        if kind in {AUDO_EXACT_SLOT_KIND, AUSB_EXACT_SLOT_KIND}
        else ".png"
    )
    return f"replacements/{hashlib.sha256(asset_id.encode('utf-8')).hexdigest()}{suffix}"


@dataclass(frozen=True)
class _ValidatedPayloadSource:
    """Small save-plan row that deliberately retains no replacement bytes."""

    asset_id: str
    member: str
    source_path: Path
    sha256: str
    size: int


def _replacement_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _open_replacement_source(
    path: Path,
    asset_id: str,
    *,
    expected_size: int | None = None,
) -> tuple[int, os.stat_result]:
    """Open one regular replacement without following a swapped-in link."""

    try:
        before = path.lstat()
    except OSError as exc:
        raise ProjectError(f"Replacement changed after import: {asset_id}") from exc
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise ProjectError(f"Replacement changed after import: {asset_id}")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ProjectError(f"Replacement changed after import: {asset_id}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _replacement_identity(opened) != _replacement_identity(before)
        ):
            raise ProjectError(f"Replacement changed after import: {asset_id}")
        if expected_size is None:
            if not 0 < opened.st_size <= MAX_REPLACEMENT_BYTES:
                raise ProjectError(f"Replacement payload size is invalid: {asset_id}")
        elif opened.st_size != expected_size:
            raise ProjectError(f"Replacement changed after import: {asset_id}")
        return descriptor, opened
    except BaseException:
        os.close(descriptor)
        raise


def _read_replacement_for_validation(path: Path, asset_id: str) -> bytes:
    """Read at most one bounded replacement for its semantic validation pass."""

    descriptor, opened = _open_replacement_source(path, asset_id)
    try:
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(PROJECT_IO_CHUNK_BYTES, remaining))
            if not block:
                raise ProjectError(f"Replacement changed after import: {asset_id}")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ProjectError(f"Replacement changed after import: {asset_id}")
        after = os.fstat(descriptor)
        if _replacement_identity(after) != _replacement_identity(opened):
            raise ProjectError(f"Replacement changed after import: {asset_id}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_payload_source(
    modification: Modification,
    protected_hashes: frozenset[str],
) -> tuple[_ValidatedPayloadSource, dict[str, object]]:
    """Validate one payload and return only its path, digest, size, and metadata."""

    data = _read_replacement_for_validation(
        modification.replacement_path,
        modification.asset_id,
    )
    digest = hashlib.sha256(data).hexdigest()
    if digest != modification.replacement_sha256:
        raise ProjectError(f"Replacement changed after import: {modification.asset_id}")
    if digest in RETAIL_HASHES or digest in protected_hashes:
        raise ProjectError("A project replacement matches protected source game data")
    if modification.kind in {"localization_text", "roster_identity_text"}:
        decode_text_payload(data, modification.asset_id)
    elif modification.kind == "player_base_rating":
        decode_player_rating_payload(data, modification.asset_id)
    elif modification.kind == "player_position":
        decode_player_position_payload(data, modification.asset_id)
    elif modification.kind in {AUDO_EXACT_SLOT_KIND, AUSB_EXACT_SLOT_KIND}:
        validate_xma1_packet_payload(
            data,
            modification.asset_id,
            expected_size=int(modification.metadata.get("encoded_size", -1)),
        )
    elif not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ProjectError(f"Replacement is not a bounded PNG: {modification.asset_id}")
    metadata = _validated_metadata(
        modification.asset_id,
        modification.kind,
        modification.metadata,
    )
    return (
        _ValidatedPayloadSource(
            asset_id=modification.asset_id,
            member=_payload_name(modification.asset_id, modification.kind),
            source_path=modification.replacement_path,
            sha256=digest,
            size=len(data),
        ),
        metadata,
    )


def _write_payload_member(
    archive: zipfile.ZipFile,
    payload: _ValidatedPayloadSource,
) -> None:
    """Re-read, re-hash, and stream one source into a temporary ZIP member."""

    descriptor, opened = _open_replacement_source(
        payload.source_path,
        payload.asset_id,
        expected_size=payload.size,
    )
    digest = hashlib.sha256()
    remaining = payload.size
    try:
        with archive.open(payload.member, "w", force_zip64=True) as output:
            while remaining:
                block = os.read(
                    descriptor,
                    min(PROJECT_IO_CHUNK_BYTES, remaining),
                )
                if not block:
                    raise ProjectError(
                        f"Replacement changed after import: {payload.asset_id}"
                    )
                digest.update(block)
                output.write(block)
                remaining -= len(block)
            if os.read(descriptor, 1):
                raise ProjectError(
                    f"Replacement changed after import: {payload.asset_id}"
                )
        after = os.fstat(descriptor)
        if (
            _replacement_identity(after) != _replacement_identity(opened)
            or digest.hexdigest() != payload.sha256
        ):
            raise ProjectError(f"Replacement changed after import: {payload.asset_id}")
    finally:
        os.close(descriptor)


def encode_text_payload(value: str) -> bytes:
    """Canonical, user-authored payload used by sessions and projects."""

    if not isinstance(value, str) or "\0" in value:
        raise ProjectError("A text replacement must be text without NUL characters")
    return (
        json.dumps(
            {"schema": TEXT_PAYLOAD_SCHEMA, "text": value},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def decode_text_payload(data: bytes, asset_id: str) -> str:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectError(f"Text replacement is not valid UTF-8 JSON: {asset_id}") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "text"}
        or document.get("schema") != TEXT_PAYLOAD_SCHEMA
        or not isinstance(document.get("text"), str)
    ):
        raise ProjectError(f"Text replacement payload is invalid: {asset_id}")
    value = str(document["text"])
    if encode_text_payload(value) != data:
        raise ProjectError(f"Text replacement payload is not canonical: {asset_id}")
    return value


def decode_player_rating_payload(data: bytes, asset_id: str) -> int:
    """Validate canonical replacement-only JSON for one public 0..99 rating."""

    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectError(
            f"Player-rating replacement is not valid UTF-8 JSON: {asset_id}"
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "value"}
        or document.get("schema") != PLAYER_RATING_PAYLOAD_SCHEMA
        or type(document.get("value")) is not int
        or not 0 <= int(document["value"]) <= 99
    ):
        raise ProjectError(f"Player-rating replacement payload is invalid: {asset_id}")
    value = int(document["value"])
    canonical = (
        json.dumps(
            {"schema": PLAYER_RATING_PAYLOAD_SCHEMA, "value": value},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if canonical != data:
        raise ProjectError(
            f"Player-rating replacement payload is not canonical: {asset_id}"
        )
    return value


def decode_player_position_payload(data: bytes, asset_id: str) -> int:
    """Validate canonical replacement-only JSON for one exact position code."""

    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectError(
            f"Player-position replacement is not valid UTF-8 JSON: {asset_id}"
        ) from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema", "value"}
        or document.get("schema") != PLAYER_POSITION_PAYLOAD_SCHEMA
        or type(document.get("value")) is not int
        or not 0 <= int(document["value"]) <= 16
    ):
        raise ProjectError(
            f"Player-position replacement payload is invalid: {asset_id}"
        )
    value = int(document["value"])
    canonical = (
        json.dumps(
            {"schema": PLAYER_POSITION_PAYLOAD_SCHEMA, "value": value},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if canonical != data:
        raise ProjectError(
            f"Player-position replacement payload is not canonical: {asset_id}"
        )
    return value


def validate_xma1_packet_payload(
    data: bytes,
    asset_id: str,
    *,
    expected_size: int,
) -> bytes:
    """Validate the replacement-only packet body stored in a project.

    The strict source-bound importer performs RIFF, channel/rate, sequence, and
    full-decoder checks before a session creates this payload.  The project
    layer independently preserves the small invariant it can prove without a
    retail source: an exact-size, nonempty sequence of APF-style XMA1 packets.
    """

    if (
        type(expected_size) is not int
        or expected_size <= 0
        or expected_size % 0x800
        or len(data) != expected_size
    ):
        raise ProjectError(
            f"Exact-slot audio payload size is invalid: {asset_id}"
        )
    for offset in range(0, len(data), 0x800):
        word = struct.unpack_from(">I", data, offset)[0]
        metadata = (word >> 26) & 0x3
        packet_skip = word & 0x7FF
        if metadata != 2 or packet_skip != 0:
            raise ProjectError(
                f"Exact-slot audio payload is not APF XMA1 packet data: {asset_id}"
            )
    return data


def _safe_member(name: str) -> bool:
    value = PurePosixPath(name)
    return (
        not value.is_absolute()
        and ".." not in value.parts
        and "" not in value.parts
        and "\\" not in name
    )


@lru_cache(maxsize=1)
def _player_rating_target_contract() -> dict[str, int]:
    try:
        schema = load_player_rating_schema()
    except PlayerRatingsError as exc:
        raise ProjectError(
            f"Player-rating target dictionary is invalid: {exc}"
        ) from exc
    return {field.field_id: field.relative_offset for field in schema.fields}


@lru_cache(maxsize=1)
def _player_position_target_contract() -> tuple[int, int, int, int, int]:
    try:
        schema = load_player_position_schema()
    except PlayerPositionsError as exc:
        raise ProjectError(
            f"Player-position target dictionary is invalid: {exc}"
        ) from exc
    return (
        schema.player_count,
        schema.semantic_relative_offset,
        schema.mirror_relative_offset,
        schema.code_minimum,
        schema.code_maximum,
    )


def _validated_metadata(
    asset_id: str, kind: str, metadata: Mapping[str, object]
) -> dict[str, object]:
    """Allow only small scalar target coordinates in shareable projects."""

    value = dict(metadata)
    if kind == "uniform":
        allowed = {
            "family",
            "asset_index",
            "width",
            "height",
            "outer_index",
            "inner_index",
        }
        if not {"family", "asset_index"}.issubset(value) or not set(value) <= allowed:
            raise ProjectError(f"Uniform project metadata is invalid: {asset_id}")
        family = value.get("family")
        asset_index = value.get("asset_index")
        dimensions = {
            "jersey": (1024, 1024),
            "pants": (512, 512),
            "helmet": (256, 1024),
            "shoulder": (1024, 1024),
        }
        if (
            not isinstance(family, str)
            or family not in dimensions
            or type(asset_index) is not int
            or not 0 <= asset_index < 24
            or asset_id != f"apf:uniform:{family}:{asset_index:02d}"
        ):
            raise ProjectError(f"Uniform project target is invalid: {asset_id}")
        expected_width, expected_height = dimensions[str(family)]
        if "width" in value and value["width"] != expected_width:
            raise ProjectError(f"Uniform project width changed: {asset_id}")
        if "height" in value and value["height"] != expected_height:
            raise ProjectError(f"Uniform project height changed: {asset_id}")
        for key, upper_bound in (("outer_index", 1543), ("inner_index", 32)):
            if key in value and (
                type(value[key]) is not int or not 0 <= value[key] < upper_bound
            ):
                raise ProjectError(f"Uniform project {key} is invalid: {asset_id}")
        return value
    if kind == "digital_font" and asset_id == "apf:presentation:digital_font":
        allowed = {
            "width",
            "height",
            "outer_index",
            "inner_index",
            "stored_channel",
        }
        if not set(value) <= allowed:
            raise ProjectError("digital_font project metadata is invalid")
        fixed = {
            "width": 128,
            "height": 128,
            "outer_index": 1310,
            "inner_index": 246,
            "stored_channel": "alpha",
        }
        if any(key in value and value[key] != expected for key, expected in fixed.items()):
            raise ProjectError("digital_font project target metadata changed")
        return value
    if kind == "draft_logo" and asset_id == DRAFT_LOGO_EDIT_ID:
        fixed = {
            "width": 128,
            "height": 128,
            "outer_index": DRAFT_LOGO_OUTER_INDEX,
            "inner_index": DRAFT_LOGO_INNER_INDEX,
            "format": "BC3",
            "mip_levels": 1,
        }
        if set(value) != set(fixed) or any(
            value[key] != expected for key, expected in fixed.items()
        ):
            raise ProjectError("draft_logo project target metadata changed")
        return value
    if kind == "localization_text":
        allowed = {
            "outer_index",
            "inner_index",
            "pool_index",
            "table_name",
            "maximum_utf16_units",
            "reference_count",
        }
        if set(value) != allowed:
            raise ProjectError(f"Text project metadata is invalid: {asset_id}")
        fields = asset_id.split(":")
        try:
            parsed_outer, parsed_inner, parsed_pool = map(int, fields[2:])
        except (ValueError, TypeError) as exc:
            raise ProjectError(f"Text project target is invalid: {asset_id}") from exc
        table_targets = {
            185: (20, "artist_bio_english"),
            526: (0, "credits_English"),
            810: (87, "strings"),
            1127: (0, "English"),
        }
        target = table_targets.get(parsed_outer)
        if (
            len(fields) != 5
            or fields[:2] != ["apf", "text-pool"]
            or target is None
            or (parsed_inner, value.get("table_name")) != target
            or value.get("outer_index") != parsed_outer
            or value.get("inner_index") != parsed_inner
            or value.get("pool_index") != parsed_pool
            or not 0 <= parsed_pool < 2000
            or type(value.get("maximum_utf16_units")) is not int
            or not 0 <= int(value["maximum_utf16_units"]) <= 4096
            or type(value.get("reference_count")) is not int
            or not 0 <= int(value["reference_count"]) <= 2000
        ):
            raise ProjectError(f"Text project target metadata changed: {asset_id}")
        return value
    if kind == "roster_identity_text":
        allowed = {
            "pool_index",
            "maximum_utf16_units",
            "known_owner_count",
            "owner_fingerprint",
        }
        if set(value) != allowed:
            raise ProjectError(
                f"Roster identity project metadata is invalid: {asset_id}"
            )
        fields = asset_id.split(":")
        try:
            parsed_pool = int(fields[2])
        except (IndexError, ValueError) as exc:
            raise ProjectError(
                f"Roster identity project target is invalid: {asset_id}"
            ) from exc
        fingerprint = value.get("owner_fingerprint")
        if (
            len(fields) != 3
            or fields[:2] != ["apf", "roster-name"]
            or value.get("pool_index") != parsed_pool
            or not 0 <= parsed_pool < 10_000
            or type(value.get("maximum_utf16_units")) is not int
            or not 0 <= int(value["maximum_utf16_units"]) <= 256
            or type(value.get("known_owner_count")) is not int
            or not 1 <= int(value["known_owner_count"]) <= 10_000
            or not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
        ):
            raise ProjectError(
                f"Roster identity project target metadata changed: {asset_id}"
            )
        return value
    if kind == "player_base_rating":
        allowed = {
            "player_index",
            "field_id",
            "record_relative_offset",
            "public_minimum",
            "public_maximum",
        }
        if set(value) != allowed:
            raise ProjectError(
                f"Player-rating project metadata is invalid: {asset_id}"
            )
        fields = asset_id.split(":")
        try:
            parsed_player = int(fields[2])
        except (IndexError, ValueError) as exc:
            raise ProjectError(
                f"Player-rating project target is invalid: {asset_id}"
            ) from exc
        field_id = value.get("field_id")
        relative_offset = (
            _player_rating_target_contract().get(field_id)
            if isinstance(field_id, str)
            else None
        )
        if (
            len(fields) != 4
            or fields[:2] != ["apf", "player-rating"]
            or fields[3] != field_id
            or not 0 <= parsed_player < 2_254
            or value.get("player_index") != parsed_player
            or relative_offset is None
            or value.get("record_relative_offset") != relative_offset
            or value.get("public_minimum") != 0
            or value.get("public_maximum") != 99
        ):
            raise ProjectError(
                f"Player-rating project target metadata changed: {asset_id}"
            )
        return value
    if kind == "player_position":
        allowed = {
            "player_index",
            "semantic_relative_offset",
            "mirror_relative_offset",
            "minimum_code",
            "maximum_code",
            "source_mirror_required",
        }
        if set(value) != allowed:
            raise ProjectError(
                f"Player-position project metadata is invalid: {asset_id}"
            )
        fields = asset_id.split(":")
        try:
            parsed_player = int(fields[2])
        except (IndexError, ValueError) as exc:
            raise ProjectError(
                f"Player-position project target is invalid: {asset_id}"
            ) from exc
        count, semantic, mirror, minimum, maximum = (
            _player_position_target_contract()
        )
        if (
            len(fields) != 3
            or fields[:2] != ["apf", "player-position"]
            or not 0 <= parsed_player < count
            or value.get("player_index") != parsed_player
            or value.get("semantic_relative_offset") != semantic
            or value.get("mirror_relative_offset") != mirror
            or value.get("minimum_code") != minimum
            or value.get("maximum_code") != maximum
            or value.get("source_mirror_required") is not True
        ):
            raise ProjectError(
                f"Player-position project target metadata changed: {asset_id}"
            )
        return value
    if kind == AUDO_EXACT_SLOT_KIND:
        allowed = {
            "outer_table_index",
            "inner_file_index",
            "encoded_size",
            "sample_rate",
            "channel_count",
            "declared_sample_count",
            "packet_count",
            "writer_schema",
        }
        if set(value) != allowed:
            raise ProjectError(
                f"Exact-slot audio project metadata is invalid: {asset_id}"
            )
        fields = asset_id.split(":")
        try:
            outer_index = int(fields[3])
            inner_index = int(fields[4])
        except (IndexError, ValueError) as exc:
            raise ProjectError(
                f"Exact-slot audio project target is invalid: {asset_id}"
            ) from exc
        encoded_size = value.get("encoded_size")
        packet_count = value.get("packet_count")
        if (
            len(fields) != 5
            or fields[:3] != ["apf", "audio", "audo"]
            or not 0 <= outer_index < 1_543
            or not 0 <= inner_index < 100_000
            or value.get("outer_table_index") != outer_index
            or value.get("inner_file_index") != inner_index
            or type(encoded_size) is not int
            or not 0 < int(encoded_size) <= MAX_REPLACEMENT_BYTES
            or int(encoded_size) % 0x800
            or type(packet_count) is not int
            or int(packet_count) != int(encoded_size) // 0x800
            or type(value.get("sample_rate")) is not int
            or not 8_000 <= int(value["sample_rate"]) <= 192_000
            or type(value.get("channel_count")) is not int
            or not 1 <= int(value["channel_count"]) <= 8
            or type(value.get("declared_sample_count")) is not int
            or not 1 <= int(value["declared_sample_count"]) <= 1_000_000_000
            or value.get("writer_schema") != AUDO_EXACT_SLOT_WRITER_SCHEMA
        ):
            raise ProjectError(
                f"Exact-slot audio project target metadata changed: {asset_id}"
            )
        return value
    if kind == AUSB_EXACT_SLOT_KIND:
        allowed = {
            "outer_table_index",
            "inner_file_index",
            "substream_index",
            "encoded_size",
            "sample_rate",
            "channel_count",
            "declared_sample_count",
            "packet_count",
            "shared_owner_asset_ids",
            "owner_fingerprint",
            "writer_schema",
        }
        if set(value) != allowed:
            raise ProjectError(
                f"AUSB exact-slot audio project metadata is invalid: {asset_id}"
            )
        fields = asset_id.split(":")
        try:
            outer_index = int(fields[3])
            inner_index = int(fields[4])
            substream_index = int(fields[5])
        except (IndexError, ValueError) as exc:
            raise ProjectError(
                f"AUSB exact-slot audio project target is invalid: {asset_id}"
            ) from exc
        encoded_size = value.get("encoded_size")
        packet_count = value.get("packet_count")
        owner_asset_ids = value.get("shared_owner_asset_ids")
        owner_fingerprint = value.get("owner_fingerprint")
        try:
            expected_owner_fingerprint = hashlib.sha256(
                "\n".join(owner_asset_ids).encode("ascii")
            ).hexdigest()
        except (AttributeError, TypeError, UnicodeError):
            expected_owner_fingerprint = ""
        if (
            len(fields) != 6
            or fields[:3] != ["apf", "audio", "ausb"]
            or not 0 <= outer_index < 1_543
            or not 0 <= inner_index < 100_000
            or not 0 <= substream_index < 100_000
            or value.get("outer_table_index") != outer_index
            or value.get("inner_file_index") != inner_index
            or value.get("substream_index") != substream_index
            or type(encoded_size) is not int
            or not 0 < int(encoded_size) <= MAX_REPLACEMENT_BYTES
            or int(encoded_size) % 0x800
            or type(packet_count) is not int
            or int(packet_count) != int(encoded_size) // 0x800
            or type(value.get("sample_rate")) is not int
            or not 8_000 <= int(value["sample_rate"]) <= 192_000
            or type(value.get("channel_count")) is not int
            or int(value["channel_count"]) not in (1, 2)
            or type(value.get("declared_sample_count")) is not int
            or not 1 <= int(value["declared_sample_count"]) <= 1_000_000_000
            or not isinstance(owner_asset_ids, list)
            or not 1 <= len(owner_asset_ids) <= 8
            or len(set(owner_asset_ids)) != len(owner_asset_ids)
            or asset_id not in owner_asset_ids
            or any(
                not isinstance(owner, str)
                or len(owner.split(":")) != 6
                or owner.split(":")[:3] != ["apf", "audio", "ausb"]
                for owner in owner_asset_ids
            )
            or not isinstance(owner_fingerprint, str)
            or owner_fingerprint != expected_owner_fingerprint
            or value.get("writer_schema") != AUSB_EXACT_SLOT_WRITER_SCHEMA
        ):
            raise ProjectError(
                f"AUSB exact-slot audio project target metadata changed: {asset_id}"
            )
        return value
    raise ProjectError(f"Unsupported project replacement target: {asset_id}")


def save_project(
    destination: Path,
    *,
    source_sha256: str,
    modifications: Iterable[Modification],
    title: str = "APF 2K8 Mod Project",
    replace: bool = False,
    expected_target: ProjectTargetIdentity | None = None,
    protected_replacement_hashes: Iterable[str] = (),
    audio_annotations: (
        Mapping[str, object] | Iterable[AudioCueAnnotation]
    ) = (),
) -> Path:
    destination = _project_path(destination, create_parent=True)
    if expected_target is not None:
        if not replace:
            raise ProjectError(
                "Fast-save target protection requires an atomic replacement"
            )
        try:
            current_path = destination.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ProjectError(
                "The active project file is missing. Use Save Project As to "
                "choose a new destination."
            ) from exc
        if current_path != expected_target.path:
            raise ProjectError(
                "The fast-save target no longer matches the active project. "
                "Use Save Project As to choose a destination."
            )
    protected_hashes = frozenset(
        str(value).strip().lower() for value in protected_replacement_hashes
    )
    if any(
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in protected_hashes
    ):
        raise ProjectError("Protected replacement hash metadata is invalid")
    annotations, annotations_payload = _prepare_audio_annotations(
        audio_annotations
    )
    reserved_members = 2 if annotations_payload is not None else 1
    pending_modifications: list[Modification] = []
    for modification in modifications:
        if len(pending_modifications) >= MAX_PROJECT_FILES - reserved_members:
            raise ProjectError("Project file count is outside the supported limit")
        pending_modifications.append(modification)
    pending_modifications.sort(key=lambda item: item.asset_id)
    rows: list[dict[str, object]] = []
    payload_sources: list[_ValidatedPayloadSource] = []
    replacement_bytes = 0
    seen_assets: set[str] = set()
    for modification in pending_modifications:
        if modification.asset_id in seen_assets:
            raise ProjectError(
                f"The same asset was added to the project twice: {modification.asset_id}"
            )
        seen_assets.add(modification.asset_id)
        payload, metadata = _validate_payload_source(modification, protected_hashes)
        payload_sources.append(payload)
        replacement_bytes += payload.size
        if replacement_bytes > MAX_PROJECT_EXPANDED_BYTES:
            raise ProjectError("Project expands beyond the supported limit")
        rows.append(
            {
                "asset_id": modification.asset_id,
                "kind": modification.kind,
                "payload": payload.member,
                "sha256": payload.sha256,
                "size": payload.size,
                "metadata": metadata,
            }
        )
    manifest = {
        "schema": PROJECT_SCHEMA,
        "game": "apf2k8_xbox360",
        "title": title.strip()[:160] or "APF 2K8 Mod Project",
        "source": {
            "kind": "user_owned_apf_0a_fingerprint",
            "sha256": source_sha256,
            "retail_bytes_embedded": False,
        },
        "replacement_count": len(rows),
        "replacements": rows,
        "distribution": {
            "contains_original_game_bytes": False,
            "contains_original_preimages": False,
            "payloads": (
                "user-authored PNG, canonical JSON, cue-label metadata, and "
                "validated replacement-only XMA1 packet payloads"
            ),
        },
    }
    if annotations_payload is not None:
        manifest["audio_annotations"] = {
            "count": len(annotations),
            "file": AUDIO_ANNOTATIONS_MEMBER,
            "sha256": hashlib.sha256(annotations_payload).hexdigest(),
            "size": len(annotations_payload),
        }
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(manifest_data) > MAX_PROJECT_MANIFEST_BYTES:
        raise ProjectError("Project manifest is unexpectedly large")
    if (
        replacement_bytes
        + len(manifest_data)
        + (len(annotations_payload) if annotations_payload is not None else 0)
        > MAX_PROJECT_EXPANDED_BYTES
    ):
        raise ProjectError("Project expands beyond the supported limit")
    temporary_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(temporary_descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.unlink()
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            archive.writestr("project.json", manifest_data)
            if annotations_payload is not None:
                archive.writestr(AUDIO_ANNOTATIONS_MEMBER, annotations_payload)
            for payload in payload_sources:
                _write_payload_member(archive, payload)
        if temporary.stat().st_size > MAX_PROJECT_ARCHIVE_BYTES:
            raise ProjectError("Project archive is unexpectedly large")
        _publish_archive(
            temporary,
            destination,
            replace=replace,
            expected_target=expected_target,
        )
        temporary.unlink(missing_ok=True)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def load_project(
    source: Path,
    *,
    expected_source_sha256: str,
    destination_dir: Path,
) -> tuple[
    dict[str, object],
    tuple[Modification, ...],
    tuple[AudioCueAnnotation, ...],
]:
    source = source.expanduser()
    supplied = source.lstat()
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ProjectError("Project must be a regular, non-symlink file")
    source = source.resolve(strict=True)
    if supplied.st_size > MAX_PROJECT_ARCHIVE_BYTES:
        raise ProjectError("Project archive is unexpectedly large")
    destination_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as archive:
        members = archive.infolist()
        if not members or len(members) > MAX_PROJECT_FILES:
            raise ProjectError("Project file count is outside the supported limit")
        if len({item.filename for item in members}) != len(members):
            raise ProjectError("Project contains duplicate archive members")
        if any(not _safe_member(item.filename) for item in members):
            raise ProjectError("Project contains an unsafe path")
        if any((item.external_attr >> 16) & 0o170000 == stat.S_IFLNK for item in members):
            raise ProjectError("Project contains a symbolic link")
        if sum(item.file_size for item in members) > MAX_PROJECT_EXPANDED_BYTES:
            raise ProjectError("Project expands beyond the supported limit")
        names = {item.filename for item in members}
        if "project.json" not in names:
            raise ProjectError("Project is missing project.json")
        manifest_info = archive.getinfo("project.json")
        if manifest_info.file_size > MAX_PROJECT_MANIFEST_BYTES:
            raise ProjectError("Project manifest is unexpectedly large")
        manifest = _strict_json_document(
            archive.read(manifest_info), "Project manifest"
        )
        allowed_manifest_fields = {
            "schema",
            "game",
            "title",
            "source",
            "replacement_count",
            "replacements",
            "distribution",
            "audio_annotations",
        }
        required_manifest_fields = {
            "schema",
            "game",
            "source",
            "replacement_count",
            "replacements",
            "distribution",
        }
        if (
            not isinstance(manifest, dict)
            or not required_manifest_fields.issubset(manifest)
            or not set(manifest).issubset(allowed_manifest_fields)
            or manifest.get("schema") != PROJECT_SCHEMA
            or manifest.get("game") != "apf2k8_xbox360"
        ):
            raise ProjectError("Project is not an APF 2K8 Mod Studio project")
        title = manifest.get("title")
        if title is not None and (
            type(title) is not str or not title.strip() or len(title) > 160
        ):
            raise ProjectError("Project title metadata is invalid")
        source_row = manifest.get("source")
        if (
            not isinstance(source_row, dict)
            or not {"sha256"}.issubset(source_row)
            or not set(source_row).issubset(
                {"kind", "sha256", "retail_bytes_embedded"}
            )
            or source_row.get("sha256") != expected_source_sha256
            or source_row.get("kind", "user_owned_apf_0a_fingerprint")
            != "user_owned_apf_0a_fingerprint"
            or source_row.get("retail_bytes_embedded", False) is not False
        ):
            raise ProjectError("Project targets a different APF game revision")
        distribution = manifest.get("distribution")
        if (
            not isinstance(distribution, dict)
            or not {
                "contains_original_game_bytes",
                "contains_original_preimages",
            }.issubset(distribution)
            or not set(distribution).issubset(
                {
                    "contains_original_game_bytes",
                    "contains_original_preimages",
                    "payloads",
                }
            )
            or distribution.get("contains_original_game_bytes") is not False
            or distribution.get("contains_original_preimages") is not False
            or (
                "payloads" in distribution
                and type(distribution.get("payloads")) is not str
            )
        ):
            raise ProjectError("Project does not declare the retail-free contract")
        rows = manifest.get("replacements")
        replacement_count = manifest.get("replacement_count")
        if (
            not isinstance(rows, list)
            or type(replacement_count) is not int
            or replacement_count != len(rows)
        ):
            raise ProjectError("Project replacement count is inconsistent")
        expected_names = {"project.json"}
        loaded_annotations: tuple[AudioCueAnnotation, ...] = ()
        annotation_meta = manifest.get("audio_annotations")
        if annotation_meta is not None:
            if (
                not isinstance(annotation_meta, dict)
                or set(annotation_meta) != {"count", "file", "sha256", "size"}
                or annotation_meta.get("file") != AUDIO_ANNOTATIONS_MEMBER
            ):
                raise ProjectError("Project audio annotation metadata is malformed")
            annotation_count = annotation_meta.get("count")
            annotation_size = annotation_meta.get("size")
            annotation_sha256 = annotation_meta.get("sha256")
            if (
                type(annotation_count) is not int
                or not 1 <= annotation_count <= MAX_AUDIO_ANNOTATIONS
                or type(annotation_size) is not int
                or not 0 < annotation_size <= MAX_AUDIO_ANNOTATIONS_BYTES
                or type(annotation_sha256) is not str
                or len(annotation_sha256) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in annotation_sha256
                )
            ):
                raise ProjectError(
                    "Project audio annotation count, size, or checksum is invalid"
                )
            try:
                annotation_info = archive.getinfo(AUDIO_ANNOTATIONS_MEMBER)
            except KeyError as exc:
                raise ProjectError("Project audio annotations are missing") from exc
            if annotation_info.file_size != annotation_size:
                raise ProjectError("Project audio annotation size changed")
            annotation_payload = archive.read(annotation_info)
            if hashlib.sha256(annotation_payload).hexdigest() != annotation_sha256:
                raise ProjectError("Project audio annotation checksum failed")
            annotation_value = _strict_json_document(
                annotation_payload, "Project audio annotations"
            )
            try:
                loaded_annotations = parse_audio_annotation_document(
                    annotation_value
                )
            except AudioAnnotationError as exc:
                raise ProjectError(
                    f"Project audio annotations are invalid: {exc}"
                ) from exc
            if len(loaded_annotations) != annotation_count:
                raise ProjectError(
                    "Project audio annotation count does not match its metadata"
                )
            expected_names.add(AUDIO_ANNOTATIONS_MEMBER)
        modifications: list[Modification] = []
        seen_assets: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ProjectError(f"Replacement {index} is malformed")
            asset_id = row.get("asset_id")
            kind = row.get("kind")
            member = row.get("payload")
            digest = row.get("sha256")
            size = row.get("size")
            metadata = row.get("metadata")
            if (
                not isinstance(asset_id, str)
                or asset_id in seen_assets
                or not isinstance(kind, str)
                or member != _payload_name(asset_id, kind)
                or not isinstance(digest, str)
                or not isinstance(size, int)
                or not isinstance(metadata, dict)
            ):
                raise ProjectError(f"Replacement {index} has invalid metadata")
            metadata = _validated_metadata(asset_id, kind, metadata)
            seen_assets.add(asset_id)
            expected_names.add(member)
            try:
                info = archive.getinfo(member)
            except KeyError as exc:
                raise ProjectError(f"Replacement payload is missing: {asset_id}") from exc
            if info.file_size != size or not 0 < size <= MAX_REPLACEMENT_BYTES:
                raise ProjectError(f"Replacement size is invalid: {asset_id}")
            data = archive.read(info)
            actual = hashlib.sha256(data).hexdigest()
            if actual != digest or actual in RETAIL_HASHES:
                raise ProjectError(f"Replacement payload failed validation: {asset_id}")
            if kind in {"localization_text", "roster_identity_text"}:
                decode_text_payload(data, asset_id)
                extension = ".json"
            elif kind == "player_base_rating":
                decode_player_rating_payload(data, asset_id)
                extension = ".json"
            elif kind == "player_position":
                decode_player_position_payload(data, asset_id)
                extension = ".json"
            elif kind in {AUDO_EXACT_SLOT_KIND, AUSB_EXACT_SLOT_KIND}:
                validate_xma1_packet_payload(
                    data,
                    asset_id,
                    expected_size=int(metadata.get("encoded_size", -1)),
                )
                extension = ".xma1-packets"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                extension = ".png"
            else:
                raise ProjectError(f"Replacement payload failed validation: {asset_id}")
            output = destination_dir / f"{actual}{extension}"
            try:
                with output.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                existing = output.lstat()
                if (
                    not stat.S_ISREG(existing.st_mode)
                    or stat.S_ISLNK(existing.st_mode)
                    or hashlib.sha256(output.read_bytes()).hexdigest() != actual
                ):
                    raise ProjectError(
                        f"Imported replacement cache conflicts with {output.name}"
                    )
            modifications.append(
                Modification(
                    asset_id=asset_id,
                    kind=kind,
                    replacement_path=output,
                    replacement_sha256=actual,
                    metadata=metadata,
                )
            )
        if names != expected_names:
            raise ProjectError("Project contains undeclared files")
    return manifest, tuple(modifications), loaded_annotations
