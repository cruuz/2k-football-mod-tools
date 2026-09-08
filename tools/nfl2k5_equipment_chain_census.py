#!/usr/bin/env python3
"""Reproduce retail-free equipment source pins with bounded archive reads."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import decode_chunk, parse_chunks


def census(index: Path) -> dict:
    archive = parse_archive(index)
    _by_id, groups = writer.load_targets()
    outers = sorted({outer for outer, chunk in groups if chunk in (6, 8, 9)})
    pins, layouts = [], Counter()
    for outer in outers:
        entry = archive.entries[outer]
        if not 0 < entry.size <= writer.MAX_PACKAGE_BYTES:
            raise ValueError("Equipment package exceeds the bounded read size")
        package = read_entry_bytes(archive, entry)
        for chunk in parse_chunks(package, allow_trailing=True):
            if chunk.index not in (6, 8, 9):
                continue
            if chunk.output_size > writer.MAX_DECODED_BYTES:
                raise ValueError("Equipment decoded allocation exceeds the bounded read size")
            rows = groups[(outer, chunk.index)]
            decoded, _info = decode_chunk(package, chunk)
            writer._validate_layout(decoded, chunk, rows)
            span = package[chunk.offset:chunk.end_offset]
            pins.append([outer, chunk.index, hashlib.sha256(span).hexdigest()])
            first = rows[0]
            layouts[(chunk.index, first.width, first.height, first.mip_levels,
                     chunk.system_bytes, chunk.video_bytes, len(rows))] += 1
    return {"schema": "nfl2k5_equipment_chain_pins/v1",
            "retail_payload_bytes": False, "catalog_sha256": writer.CATALOG_SHA256,
            "columns": ["outer_index", "chunk_index", "complete_span_sha256"],
            "rows": sorted(pins),
            "layouts": [dict(zip(
                ("chunk", "width", "height", "mip_levels", "system_bytes", "video_bytes", "variants", "count"),
                (*key, count),
            )) for key, count in sorted(layouts.items())]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = census(args.index)
    payload = (json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n").encode()
    with args.output.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"rows": len(document["rows"]), "bytes": len(payload),
                      "sha256": hashlib.sha256(payload).hexdigest(),
                      "layouts": document["layouts"]}, indent=2))


if __name__ == "__main__":
    main()
