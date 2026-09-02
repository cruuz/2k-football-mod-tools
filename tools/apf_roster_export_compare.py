#!/usr/bin/env python3
"""Compare paired APFe-style APF 2K8 text roster exports without guessing.

The exports are pipe-delimited and may contain more row fields than header
labels.  They also contain a duplicated ``RunCoverage`` header in known APFe
exports.  This reader therefore compares by exact position, gives duplicate
labels stable ``#1``/``#2`` suffixes, and names every trailing position as
unlabelled instead of shifting or inventing semantics.

RPCS3 and Xenia exports serialize twenty RGBA colour quads inside
``TeamJerseyBytes`` as RGBA and ARGB respectively.  That exact, bounded
transformation is recognized; no other uniform bytes are ignored.
All output is a local audit report.  This tool does not write roster data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any


SCHEMA = "apf2k8_roster_export_comparison/v1"
TEAM_JERSEY_FIELD = "TeamJerseyBytes"
TEAM_FIELD = "Team"
JERSEY_BLOB_BYTES = 330
COLOUR_REGION_START = 224
COLOUR_REGION_END = 320
COLOUR_BLOCK_SIZE = 48
COLOUR_BYTES_PER_BLOCK = 40
IDENTITY_VARIANT_FIELDS = frozenset({
    "First", "Last", "College", "DOB", "Number", "Photo", "PBP", "Age",
})


class CompareError(RuntimeError):
    """An export is malformed or the comparison cannot be made safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompareError(message)


def _read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CompareError(f"cannot open export read-only: {path}: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode), f"export is not a regular file: {path}")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), f"short read from export: {path}")
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def positional_labels(header: list[str], row_width: int) -> tuple[list[str], dict[str, int]]:
    require(row_width >= len(header),
            f"rows have fewer positions ({row_width}) than the header ({len(header)})")
    totals = Counter(header)
    occurrences: Counter[str] = Counter()
    labels: list[str] = []
    for label in header:
        occurrences[label] += 1
        labels.append(f"{label}#{occurrences[label]}" if totals[label] > 1 else label)
    labels.extend(f"Unlabelled{index}" for index in range(len(header), row_width))
    return labels, {label: count for label, count in totals.items() if count > 1}


def parse_export(path: Path) -> dict[str, Any]:
    raw = _read_regular(path)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CompareError(f"export is not UTF-8: {path}") from exc
    rows = list(csv.reader(text.splitlines(), delimiter="|", quotechar='"'))
    require(bool(rows), f"export is empty: {path}")
    header = rows[0]
    body = rows[1:]
    require(bool(header) and bool(body), f"export has no header or data rows: {path}")
    widths = Counter(len(row) for row in body)
    require(len(widths) == 1,
            f"data rows do not have one exact width: {dict(sorted(widths.items()))}")
    width = next(iter(widths))
    labels, duplicates = positional_labels(header, width)
    return {
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "header": header,
        "labels": labels,
        "duplicates": duplicates,
        "rows": body,
        "replacement_character_count": text.count("\ufffd"),
    }


def _label_index(labels: list[str], label: str) -> int:
    matches = [index for index, candidate in enumerate(labels) if candidate == label]
    require(len(matches) == 1, f"required field {label!r} is missing or duplicated")
    return matches[0]


def platform_jersey_bytes_equivalent(left: str, right: str) -> bool:
    """Recognize only the observed, bounded RPCS3 RGBA/Xenia ARGB change."""

    try:
        left_bytes = bytes.fromhex(left)
        right_bytes = bytes.fromhex(right)
    except ValueError:
        return False
    if len(left_bytes) != JERSEY_BLOB_BYTES or len(right_bytes) != JERSEY_BLOB_BYTES:
        return False
    if left_bytes[:COLOUR_REGION_START] != right_bytes[:COLOUR_REGION_START]:
        return False
    if left_bytes[COLOUR_REGION_END:] != right_bytes[COLOUR_REGION_END:]:
        return False
    for block in range(COLOUR_REGION_START, COLOUR_REGION_END, COLOUR_BLOCK_SIZE):
        for offset in range(block, block + COLOUR_BYTES_PER_BLOCK, 4):
            rgba = left_bytes[offset:offset + 4]
            if right_bytes[offset:offset + 4] != rgba[3:4] + rgba[:3]:
                return False
        metadata = slice(block + COLOUR_BYTES_PER_BLOCK, block + COLOUR_BLOCK_SIZE)
        if left_bytes[metadata] != right_bytes[metadata]:
            return False
    return True


def compare_exports(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    left_platform: str,
    right_platform: str,
    user_team_labels: set[str] | None = None,
    sentinel_team_labels: set[str] | None = None,
) -> dict[str, Any]:
    require(left["header"] == right["header"], "export headers differ")
    require(left["labels"] == right["labels"], "export positional schemas differ")
    require(len(left["rows"]) == len(right["rows"]),
            "exports contain different row counts")
    labels: list[str] = left["labels"]
    jersey_index = _label_index(labels, TEAM_JERSEY_FIELD)
    team_index = _label_index(labels, TEAM_FIELD)
    user_team_labels = user_team_labels or set()
    sentinel_team_labels = sentinel_team_labels or set()

    classification_counts: Counter[str] = Counter()
    mismatch_counts: Counter[str] = Counter()
    effective_mismatch_counts: Counter[str] = Counter()
    platform_uniform_rows: list[int] = []
    identity_variants: list[dict[str, Any]] = []
    user_team_variants: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []

    for row_index, (left_row, right_row) in enumerate(zip(left["rows"], right["rows"])):
        raw_differences = [
            index for index, (left_value, right_value) in enumerate(zip(left_row, right_row))
            if left_value != right_value
        ]
        for index in raw_differences:
            mismatch_counts[labels[index]] += 1
        jersey_equivalent = (
            jersey_index in raw_differences
            and platform_jersey_bytes_equivalent(
                left_row[jersey_index], right_row[jersey_index])
        )
        effective = [
            index for index in raw_differences
            if not (index == jersey_index and jersey_equivalent)
        ]
        if jersey_equivalent:
            platform_uniform_rows.append(row_index)
        for index in effective:
            effective_mismatch_counts[labels[index]] += 1

        effective_names = {labels[index] for index in effective}
        if not effective:
            classification = "equivalent_after_platform_normalization"
        elif (effective_names == IDENTITY_VARIANT_FIELDS
              and left_row[team_index] == right_row[team_index]):
            classification = "stock_identity_variant"
            identity_variants.append({
                "row_index": row_index,
                "team": left_row[team_index],
                "changes": {
                    labels[index]: {
                        left_platform: left_row[index],
                        right_platform: right_row[index],
                    }
                    for index in effective
                },
            })
        elif (left_row[team_index] == right_row[team_index]
              and left_row[team_index] in user_team_labels):
            classification = "user_team_randomized_roster"
            user_team_variants.append({
                "row_index": row_index,
                "team": left_row[team_index],
                "different_fields": [labels[index] for index in effective],
            })
        else:
            classification = "unexplained"
            unexplained.append({
                "row_index": row_index,
                "left_team": left_row[team_index],
                "right_team": right_row[team_index],
                "different_fields": [labels[index] for index in effective],
            })
        classification_counts[classification] += 1

    sentinel_counts = {
        label: {
            left_platform: sum(row[team_index] == label for row in left["rows"]),
            right_platform: sum(row[team_index] == label for row in right["rows"]),
        }
        for label in sorted(sentinel_team_labels)
    }
    header_count = len(left["header"])
    row_width = len(labels)
    return {
        "schema": SCHEMA,
        "platforms": {"left": left_platform, "right": right_platform},
        "inputs": {
            "left_sha256": left["sha256"],
            "right_sha256": right["sha256"],
            "left_replacement_character_count": left["replacement_character_count"],
            "right_replacement_character_count": right["replacement_character_count"],
        },
        "schema_audit": {
            "header_field_count": header_count,
            "data_field_count": row_width,
            "unlabelled_trailing_field_count": row_width - header_count,
            "duplicate_header_labels": left["duplicates"],
            "positional_labels": labels,
        },
        "row_count": len(left["rows"]),
        "classification_counts": dict(sorted(classification_counts.items())),
        "raw_mismatch_counts_by_position": dict(mismatch_counts.most_common()),
        "effective_mismatch_counts_by_position": dict(effective_mismatch_counts.most_common()),
        "platform_uniform_colour_order": {
            "field": TEAM_JERSEY_FIELD,
            "blob_bytes": JERSEY_BLOB_BYTES,
            "colour_region": [COLOUR_REGION_START, COLOUR_REGION_END],
            "left_order": "RGBA",
            "right_order": "ARGB",
            "colour_quads_per_48_byte_block": 10,
            "metadata_bytes_per_48_byte_block": 8,
            "equivalent_row_count": len(platform_uniform_rows),
            "row_indices": platform_uniform_rows,
        },
        "identity_variants": identity_variants,
        "user_team_variants": {
            "labels": sorted(user_team_labels),
            "row_count": len(user_team_variants),
            "rows": user_team_variants,
        },
        "sentinel_team_counts": sentinel_counts,
        "unexplained_rows": unexplained,
        "claims": {
            "all_values_compared_by_exact_position": True,
            "duplicate_labels_disambiguated": True,
            "unlabelled_trailing_semantics_proved": False,
            "platform_uniform_difference_ignored_without_exact_transform": False,
            "roster_data_written": False,
        },
    }


def _reserve_report(path: Path) -> int:
    require(path.parent.is_dir(), f"report directory does not exist: {path.parent}")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    try:
        return os.open(path, flags, 0o600)
    except OSError as exc:
        raise CompareError(f"refusing to overwrite report: {path}: {exc}") from exc


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if path is None:
        sys.stdout.buffer.write(payload)
        return
    descriptor = _reserve_report(path)
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            require(written > 0, "short write while creating report")
            position += written
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        descriptor = -1
        path.unlink(missing_ok=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--left-platform", default="left")
    parser.add_argument("--right-platform", default="right")
    parser.add_argument("--user-team-label", action="append", default=[])
    parser.add_argument("--sentinel-team-label", action="append", default=[])
    parser.add_argument("--json", type=Path, dest="json_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = compare_exports(
            parse_export(args.left),
            parse_export(args.right),
            left_platform=args.left_platform,
            right_platform=args.right_platform,
            user_team_labels=set(args.user_team_label),
            sentinel_team_labels=set(args.sentinel_team_label),
        )
        _write_report(args.json_path, report)
        if args.json_path is not None:
            print(
                "APF_ROSTER_EXPORT_COMPARE_PASS "
                f"rows={report['row_count']} "
                f"unexplained={len(report['unexplained_rows'])}"
            )
        return 0
    except CompareError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
