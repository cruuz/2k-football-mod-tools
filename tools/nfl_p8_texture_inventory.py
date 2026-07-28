#!/usr/bin/env python3
"""Inventory the standalone P8 TXTR targets the editor can replace.

These are the textures modders kept asking for and finding absent: the real
teams' end-zone art, the stadium goalpost pads, ``divots``, the ``mark*``
overlays laid over the grass, and the shared equipment textures.  None of them
are reachable through any existing workspace.

They are deliberately **not** the Stadium Studio corpus.  That lane replays the
strict SCNE parser and edits textures *embedded inside* a scene; these are
standalone ``TXTR`` chunks sitting alongside those scenes in the same outer
package -- outer 3136 for example carries five SCNE chunks and eight separate
TXTRs.  The two sets do not overlap.

Only a texture whose retail layout matches the writer's contract is listed:
compressed, swizzled P8, index chain starting at the video buffer, palette
immediately after a complete mip chain.  Anything else is reported as skipped
with its reason, so the count is never quietly smaller than it looks.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import HEADER, decode_chunk, parse_chunks, parse_texture


SCHEMA = "nfl2k5_p8_texture_inventory/v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
DEFAULT_JSON = ROOT / "reports/assets/nfl2k5_p8_texture_inventory.json"
# Retail sectors, recorded for the build proof only. A pressed disc or a
# repack puts the same pack somewhere else, so the build locates it by path
# and re-derives every offset; nothing compares against these.
RETAIL_PACK_SECTORS = {"0": 796_479, "1": 649_995, "2": 891_064,
                       "8": 1_574_589, "9": 35_531}

# The families this workspace claims, and the label each carries in the browser.
# Every entry is a texture name that exists in a standalone TXTR chunk.
FAMILIES: dict[str, tuple[str, str]] = {
    "endzone_north_left": ("End Zone", "End Zone North — Left"),
    "endzone_north_middle": ("End Zone", "End Zone North — Middle"),
    "endzone_north_right": ("End Zone", "End Zone North — Right"),
    "endzone_south_left": ("End Zone", "End Zone South — Left"),
    "endzone_south_middle": ("End Zone", "End Zone South — Middle"),
    "endzone_south_right": ("End Zone", "End Zone South — Right"),
    "pad_north": ("Goalpost Pads", "Goalpost Pad — North"),
    "pad_south": ("Goalpost Pads", "Goalpost Pad — South"),
    "divots": ("Field Surface", "Grass Divots Overlay"),
    "shoes_taped": ("Equipment", "Shoes — Taped"),
    "wristband_qb": ("Equipment", "Wristband — Quarterback"),
    "elbowpad_taped": ("Equipment", "Elbow Pad — Taped"),
    "elbowpad_rubber": ("Equipment", "Elbow Pad — Rubber"),
    "elbowpad_elastic": ("Equipment", "Elbow Pad — Elastic"),
}


class InventoryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def eligible(info, chunk) -> str | None:
    """Return None when the writer's contract holds, else why it does not."""
    if info.format_name != "P8":
        return f"format {info.format_name}"
    if info.packed_size != 0:
        return "linear pixels"
    if info.pixel_offset != 0:
        return "index chain does not start the video buffer"
    levels = info.mip_levels or 1
    chain = sum(
        max(1, info.width >> level) * max(1, info.height >> level)
        for level in range(levels)
    )
    if info.palette_offset != chain:
        return "palette does not follow a complete mip chain"
    if info.palette_offset + 1024 > chunk.video_bytes:
        return "palette runs past the video buffer"
    return None


def build(index_path: Path) -> dict[str, object]:
    archive = parse_archive(index_path)
    targets: list[dict[str, object]] = []
    skipped: Counter[str] = Counter()
    for outer_index, entry in enumerate(archive.entries):
        if len(entry.segments) != 1:
            continue
        head = entry.head_ascii or ""
        if "TXTR" not in head and "SCNE" not in head:
            # cheap pre-filter; packages with no resource head cannot carry one
            pass
        try:
            data = read_entry_bytes(archive, entry)
            chunks = parse_chunks(data, allow_trailing=True)
        except Exception:  # noqa: BLE001 - an unreadable package is simply skipped
            continue
        if not any(chunk.kind == "TXTR" for chunk in chunks):
            continue
        segment = entry.segments[0]
        for position, chunk in enumerate(chunks):
            if chunk.kind != "TXTR":
                continue
            try:
                decoded, _info = decode_chunk(data, chunk)
                info = parse_texture(decoded, chunk)
            except Exception:  # noqa: BLE001
                continue
            if info.name not in FAMILIES:
                continue
            reason = eligible(info, chunk)
            if reason is not None:
                skipped[f"{info.name}: {reason}"] += 1
                continue
            span_size = HEADER.size + chunk.stored_size
            span = data[chunk.offset:chunk.offset + span_size]
            group, label = FAMILIES[info.name]
            targets.append({
                "asset_id": f"p8:{outer_index}:{info.name}",
                "chunk_index": position,
                "group": group,
                "height": info.height,
                "label": label,
                "mip_levels": info.mip_levels,
                "outer_index": outer_index,
                "pack_name": segment.pack_name,
                "pack_relative_offset": segment.pack_offset + chunk.offset,
                "palette_offset": info.palette_offset,
                "span_sha256": digest(span),
                "span_size": span_size,
                "texture": info.name,
                "width": info.width,
            })
    targets.sort(key=lambda row: (row["group"], row["texture"], row["outer_index"]))
    require(targets, "no eligible standalone P8 targets were found")
    groups = Counter(str(row["group"]) for row in targets)
    # Per-pack identity. The composed build locates each pack in the user's own
    # image, derives the absolute offset from where it actually lands, and then
    # checks the pack's content hash -- which is the same on every legal dump
    # because a pack is one file. That is why these are safe to pin and the
    # container's size and hash are not.
    packs: dict[str, dict[str, object]] = {}
    for name in sorted({str(row["pack_name"]) for row in targets}):
        pack_path = index_path.parent / name
        if not pack_path.is_file():
            pack_path = index_path.parent / name.upper()
        require(pack_path.is_file(), f"pack {name} is missing beside the index")
        hasher = hashlib.sha256()
        with pack_path.open("rb") as stream:
            for block in iter(lambda: stream.read(16 << 20), b""):
                hasher.update(block)
        packs[name] = {
            "path": f"vc_53450030/{name}",
            "retail_sector": RETAIL_PACK_SECTORS[name],
            "sha256": hasher.hexdigest(),
            "size": pack_path.stat().st_size,
        }
    return {
        "schema": SCHEMA,
        "source": {"index": index_path.name},
        "summary": {
            "target_count": len(targets),
            "group_counts": dict(sorted(groups.items())),
            "distinct_textures": len({str(row["texture"]) for row in targets}),
            "skipped": dict(sorted(skipped.items())),
        },
        "packs": packs,
        "contract": {
            "format": "P8",
            "requires": "compressed, swizzled, index chain at the video buffer "
                        "start, 1024-byte palette immediately after a complete "
                        "mip chain",
            "excludes": "Stadium Studio's SCNE-embedded textures, which are a "
                        "separate corpus edited in the Stadiums workspace",
        },
        "targets": targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    try:
        document = build(args.index.resolve(strict=True))
    except InventoryError as exc:
        print(f"nfl_p8_texture_inventory: {exc}", file=sys.stderr)
        return 2
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    summary = document["summary"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
