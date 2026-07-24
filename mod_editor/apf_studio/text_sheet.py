"""Private CSV workflow for APF's bounded TXT/STRG allocations.

The application ships only this code.  A sheet is created locally from the
user's selected game and may contain retail strings, so it is a private editing
work file rather than a shareable ``.apf2k8mod`` project.  Import stages only
replacement text; unchanged source strings never enter a project payload.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO, TextIOWrapper
import os
from pathlib import Path
import stat
from typing import Protocol


TEXT_SHEET_SCHEMA = "apf2k8_mod_studio_text_sheet/v1"
MAX_SHEET_BYTES = 32 * 1024 * 1024
TEXT_SHEET_FIELDS = (
    "schema",
    "source_sha256",
    "asset_id",
    "action",
    "original_text",
    "replacement_text",
    "maximum_utf16_units",
    "editable",
    "table_name",
    "outer_index",
    "inner_index",
    "pool_index",
    "reference_count",
    "note",
)


class TextSheetError(ValueError):
    """A spreadsheet problem a modder can correct without technical knowledge."""


class _TextSession(Protocol):
    source: object

    def localization_text_allocations(self) -> tuple[object, ...]: ...

    def localization_text_value(self, asset_id: str) -> str: ...

    def modification(self, asset_id: str) -> object | None: ...

    def apply_localization_text_batch(
        self,
        replacements: dict[str, str],
        *,
        revert_asset_ids: tuple[str, ...],
    ) -> int: ...


@dataclass(frozen=True)
class TextSheetExportReceipt:
    destination: Path
    allocation_count: int
    editable_count: int
    active_replacement_count: int


@dataclass(frozen=True)
class TextSheetImportReceipt:
    source: Path
    row_count: int
    replacement_count: int
    revert_count: int
    changed_count: int


def _safe_text_cell(value: str) -> str:
    """Force spreadsheet programs to treat every text cell as literal text."""

    return "'" + value


def _decode_text_cell(value: str, *, row_number: int, column: str) -> str:
    if not value.startswith("'"):
        raise TextSheetError(
            f"Row {row_number} column {column} lost its leading apostrophe. "
            "Put the apostrophe back so spreadsheet formulas cannot run."
        )
    return value[1:]


def _source_sha256(session: _TextSession) -> str:
    value = getattr(session.source, "source_sha256", None)
    if not isinstance(value, str) or len(value) != 64:
        raise TextSheetError("The loaded game does not have a valid source fingerprint")
    return value


def export_text_sheet(
    session: _TextSession,
    destination: Path,
) -> TextSheetExportReceipt:
    """Write a new, non-overwriting UTF-8 CSV from the selected game."""

    allocations = session.localization_text_allocations()
    source_sha256 = _source_sha256(session)
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    active_count = 0
    try:
        descriptor = os.open(destination, flags | getattr(os, "O_BINARY", 0), 0o600)
        with TextIOWrapper(
            os.fdopen(descriptor, "wb", closefd=True),
            encoding="utf-8",
            newline="",
        ) as stream:
            descriptor = None
            writer = csv.DictWriter(
                stream,
                fieldnames=TEXT_SHEET_FIELDS,
                lineterminator="\n",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()
            for allocation in allocations:
                asset_id = str(getattr(allocation, "asset_id"))
                modification = session.modification(asset_id)
                active = modification is not None and getattr(
                    modification, "kind", None
                ) == "localization_text"
                active_count += int(active)
                writer.writerow(
                    {
                        "schema": TEXT_SHEET_SCHEMA,
                        "source_sha256": source_sha256,
                        "asset_id": asset_id,
                        "action": "replace" if active else "auto",
                        "original_text": _safe_text_cell(
                            str(getattr(allocation, "text"))
                        ),
                        "replacement_text": _safe_text_cell(
                            session.localization_text_value(asset_id)
                        ),
                        "maximum_utf16_units": str(
                            getattr(allocation, "maximum_utf16_units")
                        ),
                        "editable": "1" if getattr(allocation, "editable") else "0",
                        "table_name": _safe_text_cell(
                            str(getattr(allocation, "table_name"))
                        ),
                        "outer_index": str(getattr(allocation, "outer_index")),
                        "inner_index": str(getattr(allocation, "inner_index")),
                        "pool_index": str(getattr(allocation, "pool_index")),
                        "reference_count": str(
                            getattr(allocation, "reference_count")
                        ),
                        "note": _safe_text_cell(str(getattr(allocation, "note", ""))),
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise TextSheetError(
            "That text sheet already exists. Choose a new filename; exports never overwrite."
        ) from exc
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        destination.unlink(missing_ok=True)
        raise
    return TextSheetExportReceipt(
        destination=destination,
        allocation_count=len(allocations),
        editable_count=sum(bool(getattr(row, "editable")) for row in allocations),
        active_replacement_count=active_count,
    )


def _read_private_sheet(source: Path) -> str:
    source = source.expanduser()
    try:
        supplied = source.lstat()
    except FileNotFoundError as exc:
        raise TextSheetError(f"The text sheet does not exist: {source}") from exc
    if (
        not stat.S_ISREG(supplied.st_mode)
        or stat.S_ISLNK(supplied.st_mode)
        or supplied.st_nlink != 1
    ):
        raise TextSheetError("The text sheet must be a regular, non-linked CSV file")
    if supplied.st_size > MAX_SHEET_BYTES:
        raise TextSheetError("The text sheet is unexpectedly large")
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
            raise TextSheetError("The text sheet changed while it was opened")
        blocks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise TextSheetError("The text sheet ended early")
            blocks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise TextSheetError("The text sheet grew while it was read")
        after = os.fstat(descriptor)
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
            raise TextSheetError("The text sheet changed while it was read")
    finally:
        os.close(descriptor)
    try:
        return b"".join(blocks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TextSheetError("The text sheet must be UTF-8 CSV") from exc


def import_text_sheet(
    session: _TextSession,
    source: Path,
) -> TextSheetImportReceipt:
    """Validate a sheet completely, then stage all requested rows together."""

    document = _read_private_sheet(source)
    reader = csv.DictReader(StringIO(document, newline=""), strict=True)
    if tuple(reader.fieldnames or ()) != TEXT_SHEET_FIELDS:
        raise TextSheetError(
            "This CSV does not have the APF Text Sheet columns. Export a fresh sheet and copy your edits into it."
        )
    allocations = {
        str(getattr(row, "asset_id")): row
        for row in session.localization_text_allocations()
    }
    source_sha256 = _source_sha256(session)
    replacements: dict[str, str] = {}
    reverts: list[str] = []
    seen: set[str] = set()
    row_count = 0
    try:
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            if row_count > max(5_000, len(allocations)):
                raise TextSheetError("The text sheet contains too many rows")
            if None in row or any(value is None for value in row.values()):
                raise TextSheetError(f"Row {row_number} has missing or extra columns")
            if row["schema"] != TEXT_SHEET_SCHEMA:
                raise TextSheetError(f"Row {row_number} has an unsupported sheet version")
            if row["source_sha256"] != source_sha256:
                raise TextSheetError(
                    f"Row {row_number} belongs to a different game dump. Load that exact game or export a new sheet."
                )
            asset_id = row["asset_id"]
            if asset_id in seen:
                raise TextSheetError(f"Text allocation is listed twice: {asset_id}")
            seen.add(asset_id)
            try:
                allocation = allocations[asset_id]
            except KeyError as exc:
                raise TextSheetError(
                    f"Row {row_number} names a text allocation that is not in this game: {asset_id}"
                ) from exc
            exact_fields = {
                "maximum_utf16_units": getattr(allocation, "maximum_utf16_units"),
                "editable": 1 if getattr(allocation, "editable") else 0,
                "outer_index": getattr(allocation, "outer_index"),
                "inner_index": getattr(allocation, "inner_index"),
                "pool_index": getattr(allocation, "pool_index"),
                "reference_count": getattr(allocation, "reference_count"),
            }
            for field, expected in exact_fields.items():
                if row[field] != str(expected):
                    raise TextSheetError(
                        f"Row {row_number} target metadata changed in column {field}. Export a fresh sheet."
                    )
            table_name = _decode_text_cell(
                row["table_name"], row_number=row_number, column="table_name"
            )
            if table_name != str(getattr(allocation, "table_name")):
                raise TextSheetError(
                    f"Row {row_number} table ownership changed. Export a fresh sheet."
                )
            original = _decode_text_cell(
                row["original_text"], row_number=row_number, column="original_text"
            )
            if original != str(getattr(allocation, "text")):
                raise TextSheetError(
                    f"Row {row_number} original text changed. Edit only replacement_text."
                )
            replacement = _decode_text_cell(
                row["replacement_text"],
                row_number=row_number,
                column="replacement_text",
            )
            action = row["action"].strip().casefold()
            if action not in {"auto", "replace", "revert", "skip"}:
                raise TextSheetError(
                    f"Row {row_number} action must be auto, replace, revert, or skip"
                )
            editable = bool(getattr(allocation, "editable"))
            requested_change = action in {"replace", "revert"} or (
                action == "auto" and replacement != original
            )
            if requested_change and not editable:
                raise TextSheetError(
                    f"Row {row_number} is read-only and cannot be changed"
                )
            if action == "revert" or (action == "replace" and replacement == original):
                reverts.append(asset_id)
            elif action == "replace" or (action == "auto" and replacement != original):
                replacements[asset_id] = replacement
    except csv.Error as exc:
        raise TextSheetError(f"The CSV structure is invalid: {exc}") from exc
    if row_count == 0:
        raise TextSheetError("The text sheet has no allocation rows")
    changed = session.apply_localization_text_batch(
        replacements,
        revert_asset_ids=tuple(reverts),
    )
    return TextSheetImportReceipt(
        source=source.expanduser(),
        row_count=row_count,
        replacement_count=len(replacements),
        revert_count=len(reverts),
        changed_count=changed,
    )


__all__ = [
    "MAX_SHEET_BYTES",
    "TEXT_SHEET_FIELDS",
    "TEXT_SHEET_SCHEMA",
    "TextSheetError",
    "TextSheetExportReceipt",
    "TextSheetImportReceipt",
    "export_text_sheet",
    "import_text_sheet",
]
