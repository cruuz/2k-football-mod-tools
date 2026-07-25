"""Private, source-bound CSV import workflow for APF player base ratings.

The CSV is a local editing aid derived from the user's game.  It is never
copied into a project.  Imports stage only semantic ``player_base_rating``
replacement payloads (or remove them when the requested value is the source
value), so shareable projects remain authored-values-only.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping, Protocol

from .player_ratings import PlayerRatingSchema, load_player_rating_schema


PLAYER_RATING_SHEET_SCHEMA = "apf2k8_private_player_rating_sheet/v2"
EXPECTED_PLAYER_COUNT = 2_254
MAX_SHEET_BYTES = 64 * 1024 * 1024
MAX_ISSUE_SAMPLES = 24
PLAYER_RATING_SCHEMA = load_player_rating_schema()
RATING_COLUMNS = tuple(
    f"rating.{item.field_id}" for item in PLAYER_RATING_SCHEMA.fields
)
PLAYER_RATING_SHEET_FIELDS = (
    "schema",
    "source_sha256",
    "player_index",
    "first_name",
    "last_name",
    "display_name",
    "position_code",
    "position_abbreviation",
    "position_name",
    "team_names",
    "native_rating_minimum",
    "native_rating_maximum",
    "stock_observed_minimum",
    "stock_observed_maximum",
    *RATING_COLUMNS,
)
_CANONICAL_INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,2})\Z")
_SOURCE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PlayerRatingSheetError(ValueError):
    """A private ratings spreadsheet problem a modder can correct."""


class _RatingSession(Protocol):
    source: object

    def player_base_rating_source_value(
        self, player_index: int, field_id: str
    ) -> int: ...

    def player_base_rating_value(self, player_index: int, field_id: str) -> int: ...

    def player_rating_edit_fingerprint(self) -> str: ...

    def apply_player_base_rating_batch(
        self,
        replacements: Mapping[tuple[int, str], int],
        *,
        revert_targets: tuple[tuple[int, str], ...],
    ) -> int: ...


@dataclass(frozen=True)
class PlayerRatingSheetIssue:
    kind: str
    message: str
    row_number: int | None = None
    player_index: int | None = None
    field_id: str | None = None


@dataclass(frozen=True)
class PlayerRatingSheetConflict:
    player_index: int
    player_name: str
    field_id: str
    field_label: str
    source_value: int
    current_value: int
    desired_value: int
    action: str
    message: str


@dataclass(frozen=True)
class _RatingOperation:
    player_index: int
    field_id: str
    desired_value: int
    action: str


@dataclass(frozen=True)
class PlayerRatingSheetPreviewReceipt:
    source: Path
    file_sha256: str
    plan_token: str
    row_count: int
    cell_count: int
    changed_count: int
    replacement_count: int
    revert_count: int
    unchanged_count: int
    conflict_count: int
    source_conflict_count: int
    project_conflict_count: int
    error_count: int
    conflicts: tuple[PlayerRatingSheetConflict, ...]
    source_conflicts: tuple[PlayerRatingSheetIssue, ...]
    errors: tuple[PlayerRatingSheetIssue, ...]
    active_edit_fingerprint: str
    private_data: bool = field(default=True, init=False)
    _operations: tuple[_RatingOperation, ...] = field(
        default=(), repr=False, compare=False
    )

    @property
    def can_apply_without_confirmation(self) -> bool:
        return (
            self.changed_count > 0
            and self.error_count == 0
            and self.source_conflict_count == 0
            and self.project_conflict_count == 0
        )

    @property
    def requires_conflict_confirmation(self) -> bool:
        return (
            self.changed_count > 0
            and self.error_count == 0
            and self.source_conflict_count == 0
            and self.project_conflict_count > 0
        )


@dataclass(frozen=True)
class PlayerRatingSheetApplyReceipt:
    source: Path
    file_sha256: str
    row_count: int
    changed_count: int
    applied_count: int
    replacement_count: int
    revert_count: int
    conflict_count: int
    undo_action_count: int
    private_data: bool = field(default=True, init=False)


def safe_text_cell(value: object) -> str:
    """Make source-owned labels literal when a spreadsheet opens the CSV."""

    return "'" + str(value)


def _source_sha256(session: _RatingSession) -> str:
    value = getattr(session.source, "source_sha256", None)
    if not isinstance(value, str) or not _SOURCE_SHA256.fullmatch(value):
        raise PlayerRatingSheetError(
            "The loaded game does not have a valid source fingerprint"
        )
    return value


def _read_private_sheet(source: Path) -> tuple[str, str]:
    """Read one stable regular file snapshot and return text plus SHA-256."""

    source = source.expanduser()
    try:
        supplied = source.lstat()
    except FileNotFoundError as exc:
        raise PlayerRatingSheetError(f"The ratings sheet does not exist: {source}") from exc
    if (
        not stat.S_ISREG(supplied.st_mode)
        or stat.S_ISLNK(supplied.st_mode)
        or supplied.st_nlink != 1
    ):
        raise PlayerRatingSheetError(
            "The ratings sheet must be a regular, non-linked CSV file"
        )
    if not 0 < supplied.st_size <= MAX_SHEET_BYTES:
        raise PlayerRatingSheetError("The ratings sheet is empty or unexpectedly large")
    descriptor = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            supplied.st_dev,
            supplied.st_ino,
            supplied.st_size,
        ):
            raise PlayerRatingSheetError("The ratings sheet changed while it was opened")
        data = bytearray()
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise PlayerRatingSheetError("The ratings sheet ended early")
            data.extend(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise PlayerRatingSheetError("The ratings sheet grew while it was read")
        after = os.fstat(descriptor)
        # ``opened`` and ``after`` are both os.fstat of this one descriptor.
        # Two fd stats agree on st_ctime_ns on every platform, Windows
        # included, so it stays in the fingerprint here and the
        # metadata-only-change signal is not lost on any platform.
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
            opened.st_nlink,
        ):
            raise PlayerRatingSheetError("The ratings sheet changed while it was read")
    finally:
        os.close(descriptor)
    payload = bytes(data)
    try:
        return payload.decode("utf-8"), hashlib.sha256(payload).hexdigest()
    except UnicodeDecodeError as exc:
        raise PlayerRatingSheetError("The ratings sheet must be UTF-8 CSV") from exc


def _player_rows(model: object) -> dict[int, object]:
    raw_rows = getattr(model, "rows", ())
    players = [row for row in raw_rows if getattr(row, "kind", None) == "player"]
    if len(players) != EXPECTED_PLAYER_COUNT:
        raise PlayerRatingSheetError(
            f"The loaded roster exposes {len(players):,} players; expected exactly "
            f"{EXPECTED_PLAYER_COUNT:,}"
        )
    output: dict[int, object] = {}
    for row in players:
        fields = getattr(row, "fields", {})
        index = fields.get("player_index") if isinstance(fields, Mapping) else None
        if type(index) is not int or not 0 <= index < EXPECTED_PLAYER_COUNT:
            raise PlayerRatingSheetError("The loaded roster has an invalid player index")
        if index in output:
            raise PlayerRatingSheetError(
                f"The loaded roster lists player index {index} more than once"
            )
        output[index] = row
    if set(output) != set(range(EXPECTED_PLAYER_COUNT)):
        raise PlayerRatingSheetError("The loaded roster is missing a player index")
    return output


def _literal_identity(value: object) -> str:
    return safe_text_cell(value)


def _identity_expectations(row: object) -> dict[str, str]:
    fields = getattr(row, "fields")
    team_names = fields.get("team_names", ())
    if not isinstance(team_names, (tuple, list)) or not all(
        isinstance(item, str) for item in team_names
    ):
        raise PlayerRatingSheetError("The loaded roster has malformed team labels")
    return {
        "first_name": _literal_identity(fields.get("first_name", "")),
        "last_name": _literal_identity(fields.get("last_name", "")),
        "display_name": _literal_identity(getattr(row, "title", "")),
        "position_code": str(fields.get("position_code", "")),
        "position_abbreviation": _literal_identity(
            fields.get("position_abbreviation", "")
        ),
        "position_name": _literal_identity(fields.get("position_name", "")),
        "team_names": _literal_identity(" | ".join(team_names)),
        "native_rating_minimum": str(PLAYER_RATING_SCHEMA.native_minimum),
        "native_rating_maximum": str(PLAYER_RATING_SCHEMA.native_maximum),
        "stock_observed_minimum": str(
            PLAYER_RATING_SCHEMA.stock_observed_minimum
        ),
        "stock_observed_maximum": str(
            PLAYER_RATING_SCHEMA.stock_observed_maximum
        ),
    }


def _empty_preview(
    source: Path,
    *,
    message: str,
    file_sha256: str = "",
    active_fingerprint: str = "",
) -> PlayerRatingSheetPreviewReceipt:
    issue = PlayerRatingSheetIssue("error", message)
    return PlayerRatingSheetPreviewReceipt(
        source=source.expanduser(),
        file_sha256=file_sha256,
        plan_token="",
        row_count=0,
        cell_count=0,
        changed_count=0,
        replacement_count=0,
        revert_count=0,
        unchanged_count=0,
        conflict_count=0,
        source_conflict_count=0,
        project_conflict_count=0,
        error_count=1,
        conflicts=(),
        source_conflicts=(),
        errors=(issue,),
        active_edit_fingerprint=active_fingerprint,
    )


def preview_player_rating_sheet(
    session: _RatingSession,
    model: object,
    source: Path,
) -> PlayerRatingSheetPreviewReceipt:
    """Parse and compare a complete sheet without mutating the project."""

    source = source.expanduser()
    try:
        document, file_sha256 = _read_private_sheet(source)
        source_sha256 = _source_sha256(session)
        players = _player_rows(model)
        active_fingerprint = session.player_rating_edit_fingerprint()
    except (OSError, PlayerRatingSheetError, ValueError) as exc:
        return _empty_preview(source, message=str(exc))

    errors: list[PlayerRatingSheetIssue] = []
    source_conflicts: list[PlayerRatingSheetIssue] = []
    conflicts: list[PlayerRatingSheetConflict] = []
    error_count = 0
    source_conflict_count = 0
    project_conflict_count = 0

    def add_error(issue: PlayerRatingSheetIssue) -> None:
        nonlocal error_count
        error_count += 1
        if len(errors) < MAX_ISSUE_SAMPLES:
            errors.append(issue)

    def add_source_conflict(issue: PlayerRatingSheetIssue) -> None:
        nonlocal source_conflict_count
        source_conflict_count += 1
        if len(source_conflicts) < MAX_ISSUE_SAMPLES:
            source_conflicts.append(issue)

    try:
        reader = csv.DictReader(StringIO(document, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != PLAYER_RATING_SHEET_FIELDS:
            return _empty_preview(
                source,
                message=(
                    "This CSV does not have the complete APF Ratings Sheet v2 "
                    "columns. Export a fresh sheet and copy only rating edits into it."
                ),
                file_sha256=file_sha256,
                active_fingerprint=active_fingerprint,
            )
        rows = list(reader)
    except csv.Error as exc:
        return _empty_preview(
            source,
            message=f"The CSV structure is invalid: {exc}",
            file_sha256=file_sha256,
            active_fingerprint=active_fingerprint,
        )

    if len(rows) != EXPECTED_PLAYER_COUNT:
        add_error(
            PlayerRatingSheetIssue(
                "row_count",
                f"The ratings sheet has {len(rows):,} player rows; expected exactly "
                f"{EXPECTED_PLAYER_COUNT:,}",
            )
        )
    seen: set[int] = set()
    operations: list[_RatingOperation] = []
    replacement_count = 0
    revert_count = 0
    unchanged_count = 0
    valid_cell_count = 0
    source_mismatch_reported = False

    for row_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            add_error(
                PlayerRatingSheetIssue(
                    "columns", f"Row {row_number} has missing or extra columns", row_number
                )
            )
            continue
        raw_index = row["player_index"]
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,3})", raw_index):
            add_error(
                PlayerRatingSheetIssue(
                    "player_index",
                    f"Row {row_number} player_index must be a whole number from 0 to 2253",
                    row_number,
                )
            )
            continue
        player_index = int(raw_index)
        if not 0 <= player_index < EXPECTED_PLAYER_COUNT:
            add_error(
                PlayerRatingSheetIssue(
                    "player_index",
                    f"Row {row_number} player_index is outside 0..2253",
                    row_number,
                    player_index,
                )
            )
            continue
        if player_index in seen:
            add_error(
                PlayerRatingSheetIssue(
                    "duplicate_player",
                    f"Player index {player_index} is listed more than once",
                    row_number,
                    player_index,
                )
            )
            continue
        seen.add(player_index)
        if row["schema"] != PLAYER_RATING_SHEET_SCHEMA:
            add_error(
                PlayerRatingSheetIssue(
                    "schema",
                    f"Row {row_number} has an unsupported ratings-sheet version",
                    row_number,
                    player_index,
                )
            )
        if row["source_sha256"] != source_sha256 and not source_mismatch_reported:
            source_mismatch_reported = True
            add_source_conflict(
                PlayerRatingSheetIssue(
                    "source_fingerprint",
                    "This ratings sheet belongs to a different game dump. Load that exact game or export a fresh sheet.",
                    row_number,
                    player_index,
                )
            )
        live_row = players[player_index]
        try:
            expectations = _identity_expectations(live_row)
        except PlayerRatingSheetError as exc:
            add_error(
                PlayerRatingSheetIssue(
                    "source_identity", str(exc), row_number, player_index
                )
            )
            continue
        for column, expected in expectations.items():
            if row[column] != expected:
                add_source_conflict(
                    PlayerRatingSheetIssue(
                        "source_metadata",
                        f"Row {row_number} source column {column} changed. Edit only rating.* columns.",
                        row_number,
                        player_index,
                    )
                )
        player_name = str(getattr(live_row, "title", f"Player {player_index}"))
        for rating_field in PLAYER_RATING_SCHEMA.fields:
            field_id = rating_field.field_id
            raw_value = row[f"rating.{field_id}"]
            if not _CANONICAL_INTEGER.fullmatch(raw_value):
                add_error(
                    PlayerRatingSheetIssue(
                        "rating_value",
                        f"Row {row_number} {rating_field.label} must be a plain whole number from 0 to 99",
                        row_number,
                        player_index,
                        field_id,
                    )
                )
                continue
            desired = int(raw_value)
            try:
                source_value = session.player_base_rating_source_value(
                    player_index, field_id
                )
                current_value = session.player_base_rating_value(player_index, field_id)
            except (ValueError, OSError) as exc:
                add_error(
                    PlayerRatingSheetIssue(
                        "rating_source",
                        f"Could not read player {player_index} {rating_field.label}: {exc}",
                        row_number,
                        player_index,
                        field_id,
                    )
                )
                continue
            valid_cell_count += 1
            if desired == 100 and source_value != 100:
                add_error(
                    PlayerRatingSheetIssue(
                        "native_100",
                        f"Row {row_number} {rating_field.label}=100 is allowed only to keep or revert an existing source 100",
                        row_number,
                        player_index,
                        field_id,
                    )
                )
                continue
            if desired > 100:
                add_error(
                    PlayerRatingSheetIssue(
                        "rating_value",
                        f"Row {row_number} {rating_field.label} must be from 0 to 99",
                        row_number,
                        player_index,
                        field_id,
                    )
                )
                continue
            if desired == current_value:
                unchanged_count += 1
                continue
            action = "revert" if desired == source_value else "replace"
            operations.append(
                _RatingOperation(player_index, field_id, desired, action)
            )
            if action == "revert":
                revert_count += 1
            else:
                replacement_count += 1
            if current_value != source_value and desired != current_value:
                project_conflict_count += 1
                if len(conflicts) < MAX_ISSUE_SAMPLES:
                    conflicts.append(
                        PlayerRatingSheetConflict(
                            player_index=player_index,
                            player_name=player_name,
                            field_id=field_id,
                            field_label=rating_field.label,
                            source_value=source_value,
                            current_value=current_value,
                            desired_value=desired,
                            action=action,
                            message=(
                                f"{player_name} · {rating_field.label}: project "
                                f"{current_value} → sheet {desired} (source {source_value})"
                            ),
                        )
                    )

    missing = sorted(set(range(EXPECTED_PLAYER_COUNT)) - seen)
    for player_index in missing:
        add_error(
            PlayerRatingSheetIssue(
                "missing_player",
                f"Player index {player_index} is missing from the ratings sheet",
                player_index=player_index,
            )
        )
    final_fingerprint = session.player_rating_edit_fingerprint()
    if final_fingerprint != active_fingerprint:
        add_error(
            PlayerRatingSheetIssue(
                "project_changed",
                "The active rating edits changed during preview. Preview the sheet again.",
            )
        )
    token_payload = json.dumps(
        {
            "file_sha256": file_sha256,
            "source_sha256": source_sha256,
            "active_edit_fingerprint": active_fingerprint,
            "operations": [
                [item.player_index, item.field_id, item.desired_value, item.action]
                for item in operations
            ],
            "error_count": error_count,
            "source_conflict_count": source_conflict_count,
            "project_conflict_count": project_conflict_count,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    plan_token = hashlib.sha256(token_payload).hexdigest()
    return PlayerRatingSheetPreviewReceipt(
        source=source,
        file_sha256=file_sha256,
        plan_token=plan_token,
        row_count=len(rows),
        cell_count=valid_cell_count,
        changed_count=len(operations),
        replacement_count=replacement_count,
        revert_count=revert_count,
        unchanged_count=unchanged_count,
        conflict_count=source_conflict_count + project_conflict_count,
        source_conflict_count=source_conflict_count,
        project_conflict_count=project_conflict_count,
        error_count=error_count,
        conflicts=tuple(conflicts),
        source_conflicts=tuple(source_conflicts),
        errors=tuple(errors),
        active_edit_fingerprint=active_fingerprint,
        _operations=tuple(operations),
    )


def apply_player_rating_sheet(
    session: _RatingSession,
    model: object,
    preview: PlayerRatingSheetPreviewReceipt,
    *,
    allow_conflicts: bool = False,
) -> PlayerRatingSheetApplyReceipt:
    """Revalidate a preview and stage its semantic changes as one Undo action."""

    if not isinstance(preview, PlayerRatingSheetPreviewReceipt):
        raise PlayerRatingSheetError("Preview the ratings sheet before applying it")
    current = preview_player_rating_sheet(session, model, preview.source)
    if not current.file_sha256 or current.file_sha256 != preview.file_sha256:
        raise PlayerRatingSheetError(
            "The ratings sheet changed after preview. Preview it again before applying."
        )
    if current.plan_token != preview.plan_token:
        raise PlayerRatingSheetError(
            "The game or active rating edits changed after preview. Preview the sheet again."
        )
    if current.error_count:
        detail = current.errors[0].message if current.errors else "The sheet is invalid"
        raise PlayerRatingSheetError(detail)
    if current.source_conflict_count:
        detail = (
            current.source_conflicts[0].message
            if current.source_conflicts
            else "The sheet does not match the loaded game"
        )
        raise PlayerRatingSheetError(detail)
    if current.project_conflict_count and not allow_conflicts:
        raise PlayerRatingSheetError(
            f"The sheet conflicts with {current.project_conflict_count:,} active "
            "rating edits. Confirm that those edits may be replaced or reverted."
        )
    replacements = {
        (item.player_index, item.field_id): item.desired_value
        for item in current._operations
        if item.action == "replace"
    }
    reverts = tuple(
        (item.player_index, item.field_id)
        for item in current._operations
        if item.action == "revert"
    )
    applied = 0
    if replacements or reverts:
        applied = session.apply_player_base_rating_batch(
            replacements, revert_targets=reverts
        )
    return PlayerRatingSheetApplyReceipt(
        source=current.source,
        file_sha256=current.file_sha256,
        row_count=current.row_count,
        changed_count=current.changed_count,
        applied_count=applied,
        replacement_count=current.replacement_count,
        revert_count=current.revert_count,
        conflict_count=current.project_conflict_count,
        undo_action_count=1 if applied else 0,
    )


__all__ = [
    "EXPECTED_PLAYER_COUNT",
    "MAX_SHEET_BYTES",
    "PLAYER_RATING_SHEET_FIELDS",
    "PLAYER_RATING_SHEET_SCHEMA",
    "RATING_COLUMNS",
    "PlayerRatingSheetApplyReceipt",
    "PlayerRatingSheetConflict",
    "PlayerRatingSheetError",
    "PlayerRatingSheetIssue",
    "PlayerRatingSheetPreviewReceipt",
    "apply_player_rating_sheet",
    "preview_player_rating_sheet",
    "safe_text_cell",
]
