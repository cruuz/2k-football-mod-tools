#!/usr/bin/env python3
"""Inspect and safely patch APF 2K8 per-team playbook assignments.

This edits the two assignment pointers stored in each team record.  It does
*not* rewrite the plays or formations in ``playbook_master.iff``.  Xbox 360
``CON `` packages are deliberately inspect-only: changing their payload bytes
without rebuilding the STFS hashes/signature would produce a corrupt save.

For writes, provide an extracted/raw roster payload and reinject/resign the
result with a save manager you trust.  The writer creates a new file, checks
every changed byte, reparses the result, and emits an independently verifiable
receipt.  It never overwrites the source or an existing output.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any


SCHEMA = "apf2k8_save_playbook_assignments/v1"
MANIFEST_SCHEMA = "apf2k8_save_playbook_assignment_patch/v1"
TEAM_COUNT = 40
TEAM_STRIDE = 384
OFFENSE_FIELD = 0xE0
DEFENSE_FIELD = 0xE4
PLAYBOOK_COUNT = 69
PLAYBOOK_STRIDE = 12
OFFENSE_SIDE = 0
DEFENSE_SIDE = 0x01000000


class SaveError(RuntimeError):
    """The input is not a supported, internally consistent APF save."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveError(message)


@dataclass(frozen=True)
class Layout:
    name: str
    team_start: int
    playbook_start: int
    assignment_pointer_bias: int
    signed_container: bool


RAW_LAYOUT = Layout(
    name="raw_roster_payload",
    team_start=0x0B8078,
    playbook_start=0x1D31DC,
    assignment_pointer_bias=0,
    signed_container=False,
)
CON_LAYOUT = Layout(
    name="xbox_360_con_stfs",
    team_start=0x0C9078,
    playbook_start=0x1E61DC,
    assignment_pointer_bias=8192,
    signed_container=True,
)


@dataclass(frozen=True)
class Playbook:
    playbook_id: int
    offset: int
    name: str
    kind: str
    side: int

    @property
    def side_name(self) -> str:
        return "offense" if self.side == OFFENSE_SIDE else "defense"


@dataclass(frozen=True)
class TeamAssignments:
    team_index: int
    offensive_playbook_id: int
    defensive_playbook_id: int
    offense_field_offset: int
    defense_field_offset: int


@dataclass(frozen=True)
class ParsedSave:
    layout: Layout
    playbooks: tuple[Playbook, ...]
    teams: tuple[TeamAssignments, ...]


def _open_regular_read_only(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SaveError(f"cannot open source read-only: {path}: {exc}") from exc
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        os.close(descriptor)
        raise SaveError(f"source is not a regular file: {path}")
    return descriptor


def read_source(path: Path) -> bytes:
    descriptor = _open_regular_read_only(path)
    try:
        size = os.fstat(descriptor).st_size
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), f"short read from source: {path}")
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def detect_layout(data: bytes) -> Layout:
    layout = CON_LAYOUT if data.startswith(b"CON ") else RAW_LAYOUT
    minimum = max(
        layout.team_start + TEAM_COUNT * TEAM_STRIDE,
        layout.playbook_start + PLAYBOOK_COUNT * PLAYBOOK_STRIDE,
    )
    require(len(data) >= minimum,
            f"file is too short for {layout.name}: {len(data)} < {minimum}")
    return layout


def _be32(data: bytes, offset: int) -> int:
    require(0 <= offset <= len(data) - 4, f"32-bit field is outside file: 0x{offset:X}")
    return struct.unpack_from(">I", data, offset)[0]


def _relative_target(field_offset: int, stored: int, bias: int = 0) -> int:
    return field_offset + stored + bias - 1


def _read_utf16be(data: bytes, target: int, label: str) -> str:
    require(0 <= target <= len(data) - 2, f"{label} pointer is outside file")
    require(target % 2 == 0, f"{label} pointer is not UTF-16 aligned: 0x{target:X}")
    end = target
    # These are short labels.  A cap prevents a corrupt pointer from scanning
    # an arbitrary amount of retail data looking for a terminator.
    while end <= len(data) - 2 and end - target <= 256:
        if data[end:end + 2] == b"\0\0":
            raw = data[target:end]
            try:
                text = raw.decode("utf-16-be", errors="strict")
            except UnicodeDecodeError as exc:
                raise SaveError(f"{label} is not valid UTF-16BE") from exc
            require(bool(text), f"{label} is empty")
            require(all(character.isprintable() for character in text),
                    f"{label} contains control characters")
            return text
        end += 2
    raise SaveError(f"{label} has no nearby UTF-16BE terminator")


def parse_save(data: bytes) -> ParsedSave:
    layout = detect_layout(data)
    playbooks: list[Playbook] = []
    for playbook_id in range(PLAYBOOK_COUNT):
        offset = layout.playbook_start + playbook_id * PLAYBOOK_STRIDE
        name_pointer = _be32(data, offset)
        kind_pointer = _be32(data, offset + 4)
        side = _be32(data, offset + 8)
        require(side in (OFFENSE_SIDE, DEFENSE_SIDE),
                f"playbook {playbook_id} has invalid side 0x{side:08X}")
        # Unlike the cross-region team pointers, these strings and their
        # pointer fields occupy the same STFS data region, so no CON bias is
        # applied here.  The real raw and CON fixtures have identical values.
        name_target = _relative_target(offset, name_pointer)
        kind_target = _relative_target(offset + 4, kind_pointer)
        playbooks.append(Playbook(
            playbook_id=playbook_id,
            offset=offset,
            name=_read_utf16be(data, name_target, f"playbook {playbook_id} name"),
            kind=_read_utf16be(data, kind_target, f"playbook {playbook_id} type"),
            side=side,
        ))

    require(sum(row.side == OFFENSE_SIDE for row in playbooks) == 36,
            "playbook table does not contain exactly 36 offensive records")
    require(sum(row.side == DEFENSE_SIDE for row in playbooks) == 33,
            "playbook table does not contain exactly 33 defensive records")
    by_offset = {row.offset: row for row in playbooks}

    teams: list[TeamAssignments] = []
    for team_index in range(TEAM_COUNT):
        record = layout.team_start + team_index * TEAM_STRIDE
        offense_field = record + OFFENSE_FIELD
        defense_field = record + DEFENSE_FIELD
        offense_target = _relative_target(
            offense_field, _be32(data, offense_field), layout.assignment_pointer_bias)
        defense_target = _relative_target(
            defense_field, _be32(data, defense_field), layout.assignment_pointer_bias)
        offense = by_offset.get(offense_target)
        defense = by_offset.get(defense_target)
        require(offense is not None,
                f"team {team_index} offense pointer does not target a playbook record")
        require(defense is not None,
                f"team {team_index} defense pointer does not target a playbook record")
        require(offense.side == OFFENSE_SIDE,
                f"team {team_index} offense pointer targets a defensive playbook")
        require(defense.side == DEFENSE_SIDE,
                f"team {team_index} defense pointer targets an offensive playbook")
        teams.append(TeamAssignments(
            team_index=team_index,
            offensive_playbook_id=offense.playbook_id,
            defensive_playbook_id=defense.playbook_id,
            offense_field_offset=offense_field,
            defense_field_offset=defense_field,
        ))
    return ParsedSave(layout=layout, playbooks=tuple(playbooks), teams=tuple(teams))


def inspection(data: bytes) -> dict[str, Any]:
    parsed = parse_save(data)
    return {
        "schema": SCHEMA,
        "layout": parsed.layout.name,
        "signed_container": parsed.layout.signed_container,
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "playbooks": [
            {
                "playbook_id": row.playbook_id,
                "name": row.name,
                "type": row.kind,
                "side": row.side_name,
            }
            for row in parsed.playbooks
        ],
        "teams": [
            {
                "team_index": row.team_index,
                "offensive_playbook_id": row.offensive_playbook_id,
                "defensive_playbook_id": row.defensive_playbook_id,
            }
            for row in parsed.teams
        ],
        "claims": {
            "assignment_table_parsed": True,
            "play_contents_edited": False,
            "runtime_in_game_proved": False,
            "signed_container_writable": False,
        },
    }


def load_edits(path: Path) -> list[dict[str, int]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveError(f"edit list is not readable JSON: {path}") from exc
    rows = value.get("edits") if isinstance(value, dict) else value
    require(isinstance(rows, list) and bool(rows), "edit list must contain at least one edit")
    result: list[dict[str, int]] = []
    seen_fields: set[tuple[int, str]] = set()
    allowed = {"team_index", "offensive_playbook_id", "defensive_playbook_id"}
    for edit_index, row in enumerate(rows):
        require(isinstance(row, dict), f"edit {edit_index} is not an object")
        unknown = set(row) - allowed
        require(not unknown, f"edit {edit_index} has unknown fields: {sorted(unknown)}")
        team_index = row.get("team_index")
        require(isinstance(team_index, int) and not isinstance(team_index, bool),
                f"edit {edit_index} team_index must be an integer")
        require(0 <= team_index < TEAM_COUNT,
                f"edit {edit_index} team_index is outside 0..{TEAM_COUNT - 1}")
        has_assignment = False
        clean: dict[str, int] = {"team_index": team_index}
        for field_name in ("offensive_playbook_id", "defensive_playbook_id"):
            if field_name not in row:
                continue
            value_id = row[field_name]
            require(isinstance(value_id, int) and not isinstance(value_id, bool),
                    f"edit {edit_index} {field_name} must be an integer")
            key = (team_index, field_name)
            require(key not in seen_fields,
                    f"team {team_index} {field_name} is edited more than once")
            seen_fields.add(key)
            clean[field_name] = value_id
            has_assignment = True
        require(has_assignment, f"edit {edit_index} contains no assignment")
        result.append(clean)
    return result


def _reserve(path: Path) -> int:
    require(path.parent.is_dir(), f"output directory does not exist: {path.parent}")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        return os.open(path, flags, 0o600)
    except OSError as exc:
        raise SaveError(f"refusing to overwrite output: {path}: {exc}") from exc


def _write_all(descriptor: int, data: bytes) -> None:
    position = 0
    while position < len(data):
        written = os.write(descriptor, data[position:position + 1024 * 1024])
        require(written > 0, "short write while creating output")
        position += written


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _playbook_table_bytes(data: bytes, layout: Layout) -> bytes:
    start = layout.playbook_start
    return data[start:start + PLAYBOOK_COUNT * PLAYBOOK_STRIDE]


def make_patch(source_data: bytes, edits: list[dict[str, int]]) -> tuple[bytes, dict[str, Any]]:
    parsed = parse_save(source_data)
    require(not parsed.layout.signed_container,
            "Xbox 360 CON/STFS saves are inspect-only; extract the roster payload, "
            "patch that new file, then reinject/resign it with your own save manager")
    playbooks = {row.playbook_id: row for row in parsed.playbooks}
    teams = {row.team_index: row for row in parsed.teams}
    output = bytearray(source_data)
    receipt_edits: list[dict[str, Any]] = []
    declared_spans: set[int] = set()

    for edit in edits:
        team = teams[edit["team_index"]]
        for key, side, field_offset, before_id in (
            ("offensive_playbook_id", OFFENSE_SIDE, team.offense_field_offset,
             team.offensive_playbook_id),
            ("defensive_playbook_id", DEFENSE_SIDE, team.defense_field_offset,
             team.defensive_playbook_id),
        ):
            if key not in edit:
                continue
            after_id = edit[key]
            playbook = playbooks.get(after_id)
            require(playbook is not None, f"unknown playbook id: {after_id}")
            required_side = "offensive" if side == OFFENSE_SIDE else "defensive"
            require(playbook.side == side,
                    f"playbook {after_id} is not {required_side}")
            stored = playbook.offset + 1 - field_offset - parsed.layout.assignment_pointer_bias
            require(0 <= stored <= 0xFFFFFFFF,
                    f"assignment pointer for team {team.team_index} does not fit")
            before_bytes = source_data[field_offset:field_offset + 4]
            after_bytes = struct.pack(">I", stored)
            declared_spans.update(range(field_offset, field_offset + 4))
            output[field_offset:field_offset + 4] = after_bytes
            before_book = playbooks[before_id]
            receipt_edits.append({
                "team_index": team.team_index,
                "side": required_side,
                "field_offset": field_offset,
                "before_playbook_id": before_id,
                "before_name": before_book.name,
                "before_type": before_book.kind,
                "after_playbook_id": after_id,
                "after_name": playbook.name,
                "after_type": playbook.kind,
                "before_pointer_hex": before_bytes.hex().upper(),
                "after_pointer_hex": after_bytes.hex().upper(),
            })

    changed_positions = [
        index for index, (before, after) in enumerate(zip(source_data, output))
        if before != after
    ]
    require(bool(changed_positions), "every requested assignment already matches the source")
    require(set(changed_positions) <= declared_spans,
            "a byte outside a declared assignment field changed")
    output_bytes = bytes(output)
    reparsed = parse_save(output_bytes)
    reparsed_teams = {row.team_index: row for row in reparsed.teams}
    for row in receipt_edits:
        actual = reparsed_teams[row["team_index"]]
        key = ("offensive_playbook_id" if row["side"] == "offensive"
               else "defensive_playbook_id")
        require(getattr(actual, key) == row["after_playbook_id"],
                f"readback mismatch for team {row['team_index']} {row['side']}")
    source_table = _playbook_table_bytes(source_data, parsed.layout)
    output_table = _playbook_table_bytes(output_bytes, reparsed.layout)
    require(source_table == output_table, "playbook record table changed unexpectedly")

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "layout": parsed.layout.name,
        "source_size": len(source_data),
        "output_size": len(output_bytes),
        "source_sha256": hashlib.sha256(source_data).hexdigest(),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "playbook_record_table_sha256": hashlib.sha256(source_table).hexdigest(),
        "changed_byte_count": len(changed_positions),
        "changed_byte_positions": changed_positions,
        "edits": receipt_edits,
        "claims": {
            "source_opened_read_only": True,
            "output_created_new": True,
            "only_declared_assignment_fields_changed": True,
            "playbook_record_table_unchanged": True,
            "play_contents_edited": False,
            "runtime_in_game_proved": False,
            "signed_container_requires_external_reinjection_and_resigning": True,
        },
    }
    return output_bytes, manifest


def write_patch_from_edits(
    source: Path,
    output: Path,
    edits: list[dict[str, int]],
    manifest_path: Path,
    *,
    expected_source_sha256: str | None = None,
) -> dict[str, Any]:
    """Create and receipt a patch from already validated application edits.

    ``expected_source_sha256`` binds a GUI inspection to the later write.  The
    comparison happens against the exact bytes already read read-only for this
    build, so a save replaced after the chooser cannot be silently patched.
    """

    require(output != source, "output must not be the source path")
    require(manifest_path not in (source, output), "manifest path must be separate")
    # Reserve both destinations before doing any material work.  This makes an
    # existing file an early, non-destructive failure instead of a late one.
    output_fd = _reserve(output)
    try:
        try:
            manifest_fd = _reserve(manifest_path)
        except Exception:
            os.close(output_fd)
            output_fd = -1
            output.unlink(missing_ok=True)
            raise
        try:
            source_data = read_source(source)
            if expected_source_sha256 is not None:
                require(
                    hashlib.sha256(source_data).hexdigest() == expected_source_sha256,
                    "source save changed after it was inspected; reload it before writing",
                )
            output_data, manifest = make_patch(source_data, edits)
            _write_all(output_fd, output_data)
            os.fsync(output_fd)
            _write_all(manifest_fd, _json_bytes(manifest))
            os.fsync(manifest_fd)
            return manifest
        except Exception:
            # A failed build has no valid receipt and is not useful.  Only the
            # two exact files this call reserved are removed.
            os.close(manifest_fd)
            manifest_fd = -1
            os.close(output_fd)
            output_fd = -1
            manifest_path.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            raise
        finally:
            if manifest_fd >= 0:
                os.close(manifest_fd)
    finally:
        if output_fd >= 0:
            os.close(output_fd)


def write_patch(source: Path, output: Path, edits_path: Path, manifest_path: Path) -> dict[str, Any]:
    return write_patch_from_edits(
        source,
        output,
        load_edits(edits_path),
        manifest_path,
    )


def verify_patch(source_data: bytes, output_data: bytes, manifest: dict[str, Any]) -> dict[str, Any]:
    require(manifest.get("schema") == MANIFEST_SCHEMA, "manifest schema is not supported")
    source = parse_save(source_data)
    output = parse_save(output_data)
    require(source.layout == output.layout, "source/output layouts differ")
    require(not source.layout.signed_container, "a signed CON patch must not be accepted")
    require(manifest.get("source_size") == len(source_data), "source size differs from manifest")
    require(manifest.get("output_size") == len(output_data), "output size differs from manifest")
    require(manifest.get("source_sha256") == hashlib.sha256(source_data).hexdigest(),
            "source SHA-256 differs from manifest")
    require(manifest.get("output_sha256") == hashlib.sha256(output_data).hexdigest(),
            "output SHA-256 differs from manifest")
    changed = [
        index for index, (before, after) in enumerate(zip(source_data, output_data))
        if before != after
    ]
    require(manifest.get("changed_byte_positions") == changed,
            "changed byte positions differ from manifest")
    require(manifest.get("changed_byte_count") == len(changed),
            "changed byte count differs from manifest")
    edits = manifest.get("edits")
    require(isinstance(edits, list) and bool(edits), "manifest contains no edits")
    allowed: set[int] = set()
    source_teams = {row.team_index: row for row in source.teams}
    output_teams = {row.team_index: row for row in output.teams}
    books = {row.playbook_id: row for row in output.playbooks}
    for index, row in enumerate(edits):
        require(isinstance(row, dict), f"manifest edit {index} is invalid")
        team_index = row.get("team_index")
        side = row.get("side")
        require(team_index in source_teams, f"manifest edit {index} has invalid team")
        require(side in ("offensive", "defensive"),
                f"manifest edit {index} has invalid side")
        source_team = source_teams[team_index]
        output_team = output_teams[team_index]
        if side == "offensive":
            field = source_team.offense_field_offset
            before_id = source_team.offensive_playbook_id
            after_id = output_team.offensive_playbook_id
        else:
            field = source_team.defense_field_offset
            before_id = source_team.defensive_playbook_id
            after_id = output_team.defensive_playbook_id
        require(row.get("field_offset") == field,
                f"manifest edit {index} field offset differs")
        require(row.get("before_playbook_id") == before_id,
                f"manifest edit {index} before assignment differs")
        require(row.get("after_playbook_id") == after_id,
                f"manifest edit {index} after assignment differs")
        require(after_id in books, f"manifest edit {index} target is invalid")
        require(row.get("before_pointer_hex") == source_data[field:field + 4].hex().upper(),
                f"manifest edit {index} before pointer differs")
        require(row.get("after_pointer_hex") == output_data[field:field + 4].hex().upper(),
                f"manifest edit {index} after pointer differs")
        allowed.update(range(field, field + 4))
    require(set(changed) <= allowed, "output changes bytes outside manifest assignment fields")
    source_table = _playbook_table_bytes(source_data, source.layout)
    output_table = _playbook_table_bytes(output_data, output.layout)
    require(source_table == output_table, "playbook record table differs")
    require(manifest.get("playbook_record_table_sha256") == hashlib.sha256(source_table).hexdigest(),
            "playbook record table hash differs from manifest")
    return {
        "schema": "apf2k8_save_playbook_assignment_verify/v1",
        "verified": True,
        "changed_byte_count": len(changed),
        "assignment_field_count": len(edits),
        "claims": {
            "only_manifest_assignment_fields_changed": True,
            "playbook_record_table_unchanged": True,
            "runtime_in_game_proved": False,
        },
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveError(f"manifest is not readable JSON: {path}") from exc
    require(isinstance(value, dict), "manifest must be a JSON object")
    return value


def _emit_json(value: dict[str, Any], destination: Path | None) -> None:
    payload = _json_bytes(value)
    if destination is None:
        sys.stdout.buffer.write(payload)
        return
    descriptor = _reserve(destination)
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="list playbooks and team assignments")
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument("--json", type=Path, dest="json_path")

    patch_parser = subparsers.add_parser("patch", help="patch a new raw roster payload")
    patch_parser.add_argument("source", type=Path)
    patch_parser.add_argument("output", type=Path)
    patch_parser.add_argument("--edits", type=Path, required=True)
    patch_parser.add_argument("--manifest", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify", help="independently verify a patch receipt")
    verify_parser.add_argument("source", type=Path)
    verify_parser.add_argument("output", type=Path)
    verify_parser.add_argument("manifest", type=Path)
    verify_parser.add_argument("--json", type=Path, dest="json_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            report = inspection(read_source(args.source))
            _emit_json(report, args.json_path)
        elif args.command == "patch":
            report = write_patch(args.source, args.output, args.edits, args.manifest)
            print(
                "APF_SAVE_PLAYBOOK_PATCH_PASS "
                f"fields={len(report['edits'])} bytes={report['changed_byte_count']}"
            )
        else:
            report = verify_patch(
                read_source(args.source), read_source(args.output), _load_manifest(args.manifest))
            _emit_json(report, args.json_path)
        return 0
    except SaveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
