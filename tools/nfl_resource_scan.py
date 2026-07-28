#!/usr/bin/env python3
"""Scan bounded resource-chunk prefixes across every NFL 2K5 outer entry."""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import FormatError, parse_archive, read_entry_range


HEADER_SIZE = 0x20
MAX_ZERO_PADDING_SCAN = 0x100000


def printable_fourcc(value: bytes) -> bool:
    return len(value) == 4 and all(0x20 <= byte <= 0x7E for byte in value)


def header_is_bounded(header: bytes, offset: int, entry_size: int) -> bool:
    stored_size = struct.unpack_from("<I", header, 4)[0]
    return (
        printable_fourcc(header[:4])
        and stored_size != 0
        and offset + HEADER_SIZE + stored_size <= entry_size
    )


def find_after_zero_padding(archive: object, entry: object, offset: int) -> int | None:
    """Find one aligned wrapper after a bounded all-zero gap.

    Fixed-slot tables in this title pad each SHAP/SCNE body with zeroes.  Stop
    at the first nonzero byte: accepting only a 0x10-aligned, fully bounded
    resource header avoids searching arbitrary payload data for false FourCCs.
    """
    scan_end = min(entry.size, offset + MAX_ZERO_PADDING_SCAN)
    cursor = offset
    while cursor < scan_end:
        size = min(0x4000, scan_end - cursor)
        block = read_entry_range(archive, entry, cursor, size)
        relative = next((index for index, value in enumerate(block) if value), None)
        if relative is None:
            cursor += size
            continue
        candidate = cursor + relative
        if candidate % 0x10 != 0 or entry.size - candidate < HEADER_SIZE:
            return None
        header = read_entry_range(archive, entry, candidate, HEADER_SIZE)
        return candidate if header_is_bounded(header, candidate, entry.size) else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="path to vc_53450030/0")
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    archive = parse_archive(args.index)
    records: list[dict[str, object]] = []
    trailing: list[dict[str, object]] = []
    kind_counts: Counter[str] = Counter()
    structured_entries = 0
    txtr_entries: set[int] = set()
    txtr_not_first: list[dict[str, object]] = []
    padded_successor_count = 0
    zero_padding_bytes = 0

    for entry in archive.entries:
        offset = 0
        chunk_index = 0
        padding_before = 0
        while entry.size - offset >= HEADER_SIZE:
            header = read_entry_range(archive, entry, offset, HEADER_SIZE)
            kind_bytes = header[:4]
            stored_size = struct.unpack_from("<I", header, 4)[0]
            end_offset = offset + HEADER_SIZE + stored_size
            if not header_is_bounded(header, offset, entry.size):
                successor = find_after_zero_padding(archive, entry, offset)
                if successor is None:
                    break
                padding_before = successor - offset
                zero_padding_bytes += padding_before
                padded_successor_count += 1
                offset = successor
                continue
            kind = kind_bytes.decode("ascii")
            if chunk_index == 0:
                structured_entries += 1
            record = {
                "outer_index": entry.table_index,
                "outer_id": f"0x{entry.name_id:08x}",
                "outer_head": entry.head_ascii,
                "outer_size": entry.size,
                "chunk_index": chunk_index,
                "chunk_offset": offset,
                "zero_padding_before": padding_before,
                "kind": kind,
                "stored_size": stored_size,
                "end_offset": end_offset,
                "word_08": struct.unpack_from("<I", header, 8)[0],
                "word_0c": struct.unpack_from("<I", header, 0x0C)[0],
                "word_10": f"0x{struct.unpack_from('<I', header, 0x10)[0]:08x}",
                "word_14": struct.unpack_from("<I", header, 0x14)[0],
            }
            records.append(record)
            kind_counts[kind] += 1
            if kind == "TXTR":
                txtr_entries.add(entry.table_index)
                if chunk_index != 0:
                    txtr_not_first.append(record)
            offset = end_offset
            chunk_index += 1
            padding_before = 0

        if chunk_index > 0 and offset != entry.size:
            trailing.append(
                {
                    "outer_index": entry.table_index,
                    "outer_id": f"0x{entry.name_id:08x}",
                    "parsed_end": offset,
                    "trailing_bytes": entry.size - offset,
                    "portme": (
                        f"PORTME: classify 0x{entry.size - offset:x} bytes after "
                        f"structured prefix at 0x{offset:x}"
                    ),
                }
            )

    result = {
        "schema": "nfl2k5_resource_chunk_inventory/v1",
        "source_index": str(args.index),
        "summary": {
            "outer_entry_count": len(archive.entries),
            "structured_prefix_entry_count": structured_entries,
            "resource_chunk_count": len(records),
            "resource_kind_counts": dict(sorted(kind_counts.items())),
            "txtr_chunk_count": kind_counts["TXTR"],
            "txtr_outer_entry_count": len(txtr_entries),
            "txtr_not_first_count": len(txtr_not_first),
            "padded_successor_count": padded_successor_count,
            "zero_padding_bytes_between_chunks": zero_padding_bytes,
            "trailing_region_count": len(trailing),
        },
        "txtr_not_first": txtr_not_first,
        "trailing_regions": trailing,
        "chunks": records,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FormatError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
