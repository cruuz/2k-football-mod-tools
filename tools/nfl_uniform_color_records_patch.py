#!/usr/bin/env python3
"""Write facemask/turtleneck colours per uniform record, not one global pair.

The shipped writer changes exactly two eight-byte spans, one in
``vc_53450030/A`` and its mirror in ``/B``, and the documentation around it
called that a global setting. It is not. ``nfl_uniform_color_records.py``
enumerates hundreds of ``Unif`` records whose colour pairs disagree with each
other, which is only possible if the colour is per record. A modder reported
exactly that and was right.

This writer takes any number of those records and changes only their eight
colour bytes. It reuses the copy-and-verify discipline of the two-target
writer rather than reimplementing it: the retail image is opened read-only, the
output is a newly created file, and the built image is re-compared against the
source so that every differing byte is inside a declared colour span.

Runtime visibility is not claimed here. It is claimed only by the separate
capture that shows the change on screen.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nfl_uniform_color_xiso_direct_patch as base  # noqa: E402

SCHEMA = "nfl2k5_uniform_colour_records_patch/v1"
COLOUR_BYTES = 8
PACK_PATHS = {"A": "vc_53450030/a", "B": "vc_53450030/b"}


class PatchError(base.PatchError):
    """Raised when an edit list or the built image fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchError(message)


def parse_colour(value: object, label: str) -> int:
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip().lower().removeprefix("0x")
        require(len(text) == 8 and all(c in "0123456789abcdef" for c in text),
                f"{label} must be eight hex digits, AARRGGBB")
        number = int(text, 16)
    require(0 <= number <= 0xFFFFFFFF, f"{label} must fit in 32 bits")
    return number


def load_edits(path: Path) -> list[dict]:
    """The edit list: which record, and what colours it should hold."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PatchError(f"edit list is not readable JSON: {path}") from exc
    rows = value.get("edits") if isinstance(value, dict) else value
    require(isinstance(rows, list) and rows, "edit list is empty")
    edits = []
    for index, row in enumerate(rows):
        require(isinstance(row, dict), f"edit {index} is not an object")
        pack = str(row.get("pack", "")).upper()
        require(pack in PACK_PATHS, f"edit {index} names an unknown pack: {pack!r}")
        offset = row.get("colour_offset")
        require(isinstance(offset, int) and offset >= 0,
                f"edit {index} has no valid colour_offset")
        facemask = parse_colour(row.get("facemask_argb"), f"edit {index} facemask")
        turtleneck = parse_colour(
            row.get("turtleneck_argb", row.get("facemask_argb")),
            f"edit {index} turtleneck")
        edits.append({
            "pack": pack,
            "colour_offset": offset,
            "facemask_argb": f"{facemask:08X}",
            "turtleneck_argb": f"{turtleneck:08X}",
            "bytes": struct.pack("<II", facemask, turtleneck),
        })
    seen = {(row["pack"], row["colour_offset"]) for row in edits}
    require(len(seen) == len(edits), "the same record is edited twice")
    return edits


def resolve(descriptor: int, size: int) -> dict[str, tuple[int, int]]:
    """Where each pack starts in the image, and how long it is."""

    base_offset = base.locate_xdvdfs_base(descriptor, size)
    entries, _meta = base.parse_xdvdfs(descriptor, size, base_offset)
    located = {}
    for pack, path in PACK_PATHS.items():
        entry = entries.get(path)
        require(entry is not None, f"pack not found on the disc: {path}")
        located[pack] = (entry.byte_offset, entry.size)
    return located


def build(source: Path, output: Path, edits: list[dict]) -> dict:
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        info = os.fstat(source_fd)
        packs = resolve(source_fd, info.st_size)

        planned = []
        for row in edits:
            start, length = packs[row["pack"]]
            require(row["colour_offset"] + COLOUR_BYTES <= length,
                    f"record at 0x{row['colour_offset']:X} lies outside pack "
                    f"{row['pack']}")
            absolute = start + row["colour_offset"]
            before = base.read_exact(source_fd, absolute, COLOUR_BYTES)
            planned.append({**row, "absolute_offset": absolute, "before": before})

        absolutes = [row["absolute_offset"] for row in planned]
        require(len(set(absolutes)) == len(absolutes),
                "two edits resolve to the same place in the image")
        changing = [row for row in planned if row["before"] != row["bytes"]]
        require(changing, "every requested colour already matches retail")

        # Only the bytes that genuinely differ, not the whole eight-byte span.
        # A new colour usually shares some bytes with the old one, the opaque
        # alpha most often, and those bytes will not appear in the comparison.
        # Claiming the full span would then fail the equality check for a
        # correct write.
        allowed = {
            row["absolute_offset"] + index
            for row in changing
            for index in range(COLOUR_BYTES)
            if row["before"][index] != row["bytes"][index]
        }

        owned = base.reserve_file(output)
        base.copy_fd_exact(source_fd, owned.descriptor, info.st_size)
        for row in changing:
            written = base.pwrite(owned.descriptor, row["bytes"], row["absolute_offset"])
            require(written == COLOUR_BYTES,
                    f"short write at 0x{row['absolute_offset']:X}")
            require(base.read_exact(owned.descriptor, row["absolute_offset"],
                                    COLOUR_BYTES) == row["bytes"],
                    f"readback mismatch at 0x{row['absolute_offset']:X}")
        os.fsync(owned.descriptor)

        # The built image has to differ from retail ONLY inside the declared
        # colour spans. This is the property that matters, and it is checked
        # against the image rather than against the writer's intent.
        _after, output_sha, differences = base.compare_and_hash(
            source_fd, owned.descriptor, info.st_size, allowed)
        require(set(differences) <= allowed,
                "a byte outside the declared colour spans changed")
        return {
            "schema": SCHEMA,
            "source": {"path": "user-source/ESPN NFL 2K5.xiso.iso",
                       "size": info.st_size},
            "output_sha256": output_sha,
            "records_requested": len(edits),
            "records_changed": len(changing),
            "changed_byte_count": len(differences),
            "edits": [
                {
                    "pack": row["pack"],
                    "colour_offset": row["colour_offset"],
                    "absolute_offset": row["absolute_offset"],
                    "before_facemask_argb":
                        f"{struct.unpack('<II', row['before'])[0]:08X}",
                    "before_turtleneck_argb":
                        f"{struct.unpack('<II', row['before'])[1]:08X}",
                    "facemask_argb": row["facemask_argb"],
                    "turtleneck_argb": row["turtleneck_argb"],
                }
                for row in changing
            ],
            "claims": {
                "only_declared_spans_changed": True,
                "source_opened_read_only": True,
                "runtime_visibility_proved": False,
            },
        }
    finally:
        os.close(source_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", type=Path, required=True)
    parser.add_argument("--output-xiso", type=Path, required=True)
    parser.add_argument("--edits", type=Path, required=True,
                        help="JSON list of {pack, colour_offset, facemask_argb}")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    try:
        edits = load_edits(args.edits)
        manifest = build(args.source_xiso, args.output_xiso, edits)
    except base.PatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    print(
        "NFL_UNIFORM_COLOUR_RECORDS_PATCH_PASS "
        f"requested={manifest['records_requested']} "
        f"changed={manifest['records_changed']} "
        f"bytes={manifest['changed_byte_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
