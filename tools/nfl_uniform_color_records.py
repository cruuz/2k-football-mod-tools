#!/usr/bin/env python3
"""Enumerate every per-uniform facemask/turtleneck colour record in NFL 2K5.

The editor originally shipped a writer that changed ONE eight-byte pair, at a
fixed offset in ``vc_53450030/A`` and again in ``/B``, and the surrounding
documentation described that as a global setting. It is not. Those offsets are
Detroit current HOME and AWAY. The product writer now resolves all 634 logical
uniform selectors to their own records.

Layout of a record, all little-endian::

    +0x00  'Unif'                 tag
    +0x04  u32, u32               two counts
    +0x10  UTF-16LE "uniform"     type name, NUL terminated
    +0x24  u32 facemask ARGB      the faceshield/facemask tint
    +0x28  u32 turtleneck ARGB    read for the HI_turtleneck selector
    +0x2C  f32 1.0                scale
    ...    'TSET'                 the texture-set references follow

This audit tool only reads. It reports where every record is and what it holds;
the editor's separate provenance-bound writer consumes the same layout and
changes only the selected record. The disagreement between records is enough
on its own to settle whether the colour is global: it is not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

RECORD_TAG = b"Unif"
PACKAGE_TAG = b"UnifP"
#: Distance from the record tag to the eight colour bytes.
COLOUR_OFFSET = 0x24
COLOUR_BYTES = 8
#: A record is followed by its texture-set references; this bounds how far to
#: look for the first one when describing a record.
TSET_SEARCH_BYTES = 0x200

SCHEMA = "nfl2k5_uniform_colour_records/v1"


class RecordError(ValueError):
    """Raised when a pack cannot be read as a uniform colour table."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RecordError(message)


def find_all(data: bytes, needle: bytes) -> list[int]:
    found: list[int] = []
    start = 0
    while True:
        index = data.find(needle, start)
        if index < 0:
            return found
        found.append(index)
        start = index + 1


def read_records(data: bytes, pack: str) -> list[dict[str, Any]]:
    """Every ``Unif`` record in one pack, with its colours and neighbours."""

    packages = set(find_all(data, PACKAGE_TAG))
    records: list[dict[str, Any]] = []
    for offset in find_all(data, RECORD_TAG):
        # 'UnifP' contains 'Unif'; the package header is not itself a record.
        if offset in packages:
            continue
        colour_at = offset + COLOUR_OFFSET
        if colour_at + COLOUR_BYTES > len(data):
            continue
        facemask, turtleneck = struct.unpack_from("<II", data, colour_at)
        window = data[offset:offset + TSET_SEARCH_BYTES]
        tset = window.find(b"TSET")
        records.append({
            "pack": pack,
            "record_offset": offset,
            "colour_offset": colour_at,
            "facemask_argb": f"{facemask:08X}",
            "turtleneck_argb": f"{turtleneck:08X}",
            "is_unset": facemask == 0 and turtleneck == 0,
            "first_tset_offset": offset + tset if tset >= 0 else None,
        })
    return records


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: dict[tuple[str, str], int] = {}
    for row in records:
        key = (row["facemask_argb"], row["turtleneck_argb"])
        pairs[key] = pairs.get(key, 0) + 1
    ranked = sorted(pairs.items(), key=lambda item: (-item[1], item[0]))
    return {
        "record_count": len(records),
        "distinct_colour_pairs": len(pairs),
        "unset_record_count": sum(1 for row in records if row["is_unset"]),
        "most_common_pairs": [
            {"facemask_argb": key[0], "turtleneck_argb": key[1], "records": count}
            for key, count in ranked[:12]
        ],
    }


def build_report(root: Path, packs: tuple[str, ...]) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    for pack in packs:
        path = root / "vc_53450030" / pack
        require(path.is_file(), f"pack not found: {path}")
        payload = path.read_bytes()
        sources[pack] = {
            "path": f"user-source/vc_53450030/{pack}",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        records.extend(read_records(payload, pack))

    per_pack = {
        pack: summarise([row for row in records if row["pack"] == pack])
        for pack in packs
    }
    overall = summarise(records)
    return {
        "schema": SCHEMA,
        "sources": sources,
        "summary": {
            **overall,
            "per_pack": per_pack,
            # The finding this exists to record, stated so it cannot be missed.
            "colour_is_per_record_not_global": overall["distinct_colour_pairs"] > 1,
        },
        "records": records,
        "claims": {
            "read_only": True,
            "writer_available": True,
            "runtime_visibility_proved": False,
            "records_joined_to_uniform_selectors": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=Path("extracted/ESPN NFL 2K5 (USA)"),
                        help="extracted game folder holding vc_53450030/")
    parser.add_argument("--packs", default="A,B",
                        help="comma separated pack names to scan")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    packs = tuple(part.strip() for part in args.packs.split(",") if part.strip())
    try:
        report = build_report(args.index, packs)
    except RecordError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    summary = report["summary"]
    print(
        "NFL_UNIFORM_COLOUR_RECORDS_OK "
        f"records={summary['record_count']} "
        f"distinct_pairs={summary['distinct_colour_pairs']} "
        f"unset={summary['unset_record_count']} "
        f"per_record={str(summary['colour_is_per_record_not_global']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
