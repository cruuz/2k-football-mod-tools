"""User-facing APF save playbook-assignment service.

This surface changes which existing offensive and defensive playbook record a
team points at.  It does not edit the plays/formations themselves.  Raw roster
payloads are writable to a new file.  A signed Xbox 360 CON/STFS source is
hash-tree verified and extracted read-only; output remains an independently
verified raw payload for external reinjection, rehashing, and resigning.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from .backend import ensure_tools_importable


ensure_tools_importable()
import apf_save_playbook_assignments as writer  # type: ignore  # noqa: E402
import apf_stfs_roster_extract as stfs_reader  # type: ignore  # noqa: E402


SIGNED_SAVE_BOUNDARY = (
    "Hash-verified Xbox 360 CON/STFS save detected. Mod Studio can write a "
    "separate, independently verified raw Roster.ROS handoff; it never pretends "
    "to sign the container. Reinject the raw payload and rehash/resign it with "
    "the owner's save manager/keyvault before testing."
)
RAW_SAVE_BOUNDARY = (
    "Raw roster payload detected. Mod Studio will write a separate file and an "
    "independent byte-verification receipt; the selected source is never changed."
)


class SavePlaybookError(ValueError):
    """A save or assignment can be corrected by the modder."""


@dataclass(frozen=True)
class PlaybookChoice:
    playbook_id: int
    name: str
    kind: str
    side: str

    @property
    def label(self) -> str:
        return f"{self.playbook_id:02d} — {self.name} · {self.kind}"


@dataclass(frozen=True)
class TeamPlaybookAssignment:
    team_index: int
    offensive_playbook_id: int
    defensive_playbook_id: int

    @property
    def label(self) -> str:
        return f"Team slot {self.team_index:02d}"


@dataclass(frozen=True)
class SavePlaybookDocument:
    source: Path
    source_sha256: str
    file_size: int
    layout: str
    signed_container: bool
    container_kind: str | None
    payload_path: str | None
    raw_payload_sha256: str
    raw_payload: bytes
    playbooks: tuple[PlaybookChoice, ...]
    teams: tuple[TeamPlaybookAssignment, ...]

    @property
    def offense(self) -> tuple[PlaybookChoice, ...]:
        return tuple(row for row in self.playbooks if row.side == "offense")

    @property
    def defense(self) -> tuple[PlaybookChoice, ...]:
        return tuple(row for row in self.playbooks if row.side == "defense")

    @property
    def write_supported(self) -> bool:
        return True

    @property
    def boundary_message(self) -> str:
        return SIGNED_SAVE_BOUNDARY if self.signed_container else RAW_SAVE_BOUNDARY


@dataclass(frozen=True)
class PlaybookEdit:
    team_index: int
    offensive_playbook_id: int
    defensive_playbook_id: int


@dataclass(frozen=True)
class SavePlaybookWriteReceipt:
    output: Path
    manifest: Path
    output_sha256: str
    changed_byte_count: int
    assignment_field_count: int
    verification_passed: bool
    source_was_signed_container: bool
    external_reinjection_required: bool
    output_is_raw_payload: bool = True
    runtime_in_game_proved: bool = False


def inspect_save(path: Path) -> SavePlaybookDocument:
    source = Path(path)
    try:
        data = writer.read_source(source)
        if data[:4] in stfs_reader.STFS_MAGICS:
            extracted = stfs_reader.extract_roster_payload(data)
            payload = extracted.payload
            signed = True
            container_kind = extracted.package_kind
            payload_path = extracted.entry.path
        else:
            payload = data
            signed = False
            container_kind = payload_path = None
        parsed = writer.parse_save(payload)
    except (writer.SaveError, stfs_reader.StfsRosterError) as exc:
        raise SavePlaybookError(str(exc)) from exc
    books = tuple(
        PlaybookChoice(
            playbook_id=row.playbook_id,
            name=row.name,
            kind=row.kind,
            side=row.side_name,
        )
        for row in parsed.playbooks
    )
    teams = tuple(
        TeamPlaybookAssignment(
            team_index=row.team_index,
            offensive_playbook_id=row.offensive_playbook_id,
            defensive_playbook_id=row.defensive_playbook_id,
        )
        for row in parsed.teams
    )
    if len(teams) != writer.TEAM_COUNT or len(books) != writer.PLAYBOOK_COUNT:
        raise SavePlaybookError("the complete team/playbook table did not parse")
    return SavePlaybookDocument(
        source=source,
        source_sha256=hashlib.sha256(data).hexdigest(),
        file_size=len(data),
        layout=parsed.layout.name,
        signed_container=signed,
        container_kind=container_kind,
        payload_path=payload_path,
        raw_payload_sha256=hashlib.sha256(payload).hexdigest(),
        raw_payload=payload,
        playbooks=books,
        teams=teams,
    )


def stage_edit(
    document: SavePlaybookDocument,
    team_index: int,
    offensive_playbook_id: int,
    defensive_playbook_id: int,
) -> PlaybookEdit | None:
    """Validate both sides; return ``None`` when they equal the loaded source."""

    teams = {row.team_index: row for row in document.teams}
    books = {row.playbook_id: row for row in document.playbooks}
    team = teams.get(team_index)
    if team is None:
        raise SavePlaybookError(f"team slot must be 0..{writer.TEAM_COUNT - 1}")
    offense = books.get(offensive_playbook_id)
    defense = books.get(defensive_playbook_id)
    if offense is None or offense.side != "offense":
        raise SavePlaybookError("choose an offensive playbook for offense")
    if defense is None or defense.side != "defense":
        raise SavePlaybookError("choose a defensive playbook for defense")
    if (
        team.offensive_playbook_id == offensive_playbook_id
        and team.defensive_playbook_id == defensive_playbook_id
    ):
        return None
    return PlaybookEdit(
        team_index=team_index,
        offensive_playbook_id=offensive_playbook_id,
        defensive_playbook_id=defensive_playbook_id,
    )


def default_manifest_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.playbooks.json")


def _reserve(path: Path) -> int:
    if not path.parent.is_dir():
        raise SavePlaybookError(f"output directory does not exist: {path.parent}")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        return os.open(path, flags, 0o600)
    except OSError as exc:
        raise SavePlaybookError(f"refusing to overwrite output: {path}: {exc}") from exc


def _write_all(descriptor: int, data: bytes) -> None:
    position = 0
    while position < len(data):
        written = os.write(descriptor, data[position : position + 1024 * 1024])
        if written <= 0:
            raise SavePlaybookError("short write while creating playbook output")
        position += written
    os.fsync(descriptor)


def write_new_save(
    document: SavePlaybookDocument,
    edits: Iterable[PlaybookEdit],
    output: Path,
    *,
    manifest: Path | None = None,
) -> SavePlaybookWriteReceipt:
    """Write a new raw payload, then independently re-read and verify it."""

    output = Path(output)
    manifest = Path(manifest) if manifest is not None else default_manifest_path(output)
    if output == document.source:
        raise SavePlaybookError("output must not be the selected source")
    if manifest in (document.source, output):
        raise SavePlaybookError("manifest path must be separate from source and output")
    clean: list[dict[str, int]] = []
    seen: set[int] = set()
    for edit in edits:
        if edit.team_index in seen:
            raise SavePlaybookError(f"team slot {edit.team_index:02d} is staged twice")
        seen.add(edit.team_index)
        validated = stage_edit(
            document,
            edit.team_index,
            edit.offensive_playbook_id,
            edit.defensive_playbook_id,
        )
        if validated is not None:
            clean.append({
                "team_index": validated.team_index,
                "offensive_playbook_id": validated.offensive_playbook_id,
                "defensive_playbook_id": validated.defensive_playbook_id,
            })
    if not clean:
        raise SavePlaybookError("stage at least one changed team assignment first")
    try:
        current_source = writer.read_source(document.source)
        if hashlib.sha256(current_source).hexdigest() != document.source_sha256:
            raise SavePlaybookError(
                "source save changed after it was inspected; reload it before writing"
            )
        if hashlib.sha256(document.raw_payload).hexdigest() != document.raw_payload_sha256:
            raise SavePlaybookError("inspected raw playbook payload identity changed")
        output_data, patch_manifest = writer.make_patch(document.raw_payload, clean)
        patch_manifest["container_handoff"] = {
            "source_was_signed_container": document.signed_container,
            "container_kind": document.container_kind,
            "payload_path": document.payload_path,
            "source_container_sha256": document.source_sha256,
            "source_raw_payload_sha256": document.raw_payload_sha256,
            "output_is_raw_payload": True,
            "container_rehashed_or_resigned": False,
            "external_reinjection_required": document.signed_container,
        }
        verification = writer.verify_patch(
            document.raw_payload, output_data, patch_manifest
        )
    except writer.SaveError as exc:
        raise SavePlaybookError(str(exc)) from exc
    if verification.get("verified") is not True:
        raise SavePlaybookError("the independent byte verification did not pass")
    manifest_bytes = (
        json.dumps(patch_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    output_fd = manifest_fd = -1
    output_created = manifest_created = False
    try:
        output_fd = _reserve(output)
        output_created = True
        manifest_fd = _reserve(manifest)
        manifest_created = True
        _write_all(output_fd, output_data)
        _write_all(manifest_fd, manifest_bytes)
    except Exception:
        if output_fd >= 0:
            os.close(output_fd)
            output_fd = -1
        if manifest_fd >= 0:
            os.close(manifest_fd)
            manifest_fd = -1
        if output_created:
            output.unlink(missing_ok=True)
        if manifest_created:
            manifest.unlink(missing_ok=True)
        raise
    finally:
        if output_fd >= 0:
            os.close(output_fd)
        if manifest_fd >= 0:
            os.close(manifest_fd)
    try:
        written = writer.read_source(output)
        reread_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        verification = writer.verify_patch(
            document.raw_payload, written, reread_manifest
        )
    except (OSError, json.JSONDecodeError, writer.SaveError) as exc:
        # Both paths were exclusively created above; an unverifiable handoff is
        # not useful and can be removed without touching pre-existing storage.
        output.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        raise SavePlaybookError(f"written playbook handoff did not reverify: {exc}") from exc
    return SavePlaybookWriteReceipt(
        output=output,
        manifest=manifest,
        output_sha256=str(patch_manifest["output_sha256"]),
        changed_byte_count=int(patch_manifest["changed_byte_count"]),
        assignment_field_count=int(verification["assignment_field_count"]),
        verification_passed=True,
        source_was_signed_container=document.signed_container,
        external_reinjection_required=document.signed_container,
    )


__all__ = [
    "PlaybookChoice",
    "PlaybookEdit",
    "RAW_SAVE_BOUNDARY",
    "SIGNED_SAVE_BOUNDARY",
    "SavePlaybookDocument",
    "SavePlaybookError",
    "SavePlaybookWriteReceipt",
    "TeamPlaybookAssignment",
    "default_manifest_path",
    "inspect_save",
    "stage_edit",
    "write_new_save",
]
