#!/usr/bin/env python3
"""Offline probe for 0xB4 formation bytes and PLAY node operands.

No game bytes are written; it only dumps what the private cache already holds
so the 4-fixture X/Y vs route-type isolation can be overlaid later.
"""
from __future__ import annotations
import argparse
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.nfl2k5_playbook_inspector import (
    FORMATION_BASE, FORMATION_SIZE,
    FORMATION_AUX_BASE, FORMATION_AUX_SIZE,
    PLAY_BASE, PLAY_SIZE,
    RESOURCE_HEADER_SIZE,
    parse_playbook_resource,
)
from mod_editor.core.nfl2k5_universal_asset_index import Nfl2k5UniversalAssetIndex
from nfl_outer import FormatError, read_entry_range


def _hexdump(data: bytes, base: int = 0, width: int = 16) -> str:
    lines = []
    for off in range(0, len(data), width):
        chunk = data[off:off+width]
        hx = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base+off:04x}: {hx:<{width*3}} |{asc}|")
    return "\n".join(lines)


def dump_formations(index_path: pathlib.Path, inventory_path: pathlib.Path, asset_id: str, a: int, b: int) -> None:
    sidecar = inventory_path.parent / "universal-assets-v1.sqlite3"
    idx = Nfl2k5UniversalAssetIndex(inventory_path, index_path, sidecar)
    rec = idx.get(asset_id)
    entry = idx.archive.entries[rec.outer_index]
    raw = read_entry_range(idx.archive, entry, rec.chunk_offset, rec.raw_size)
    book = parse_playbook_resource(raw, asset_id=asset_id)
    body_off = RESOURCE_HEADER_SIZE
    fa = FORMATION_BASE + a * FORMATION_SIZE
    fb = FORMATION_BASE + b * FORMATION_SIZE
    aa = FORMATION_AUX_BASE + a * FORMATION_AUX_SIZE
    ab = FORMATION_AUX_BASE + b * FORMATION_AUX_SIZE
    ra = raw[body_off + fa : body_off + fa + FORMATION_SIZE]
    rb = raw[body_off + fb : body_off + fb + FORMATION_SIZE]
    print(f"# {asset_id} formations {a} vs {b} — {len(book.formations)} total, {len(book.plays)} plays")
    print(f"# formation {a} name={book.formations[a].name!r} plays={len(book.formations[a].play_links)}")
    print(f"# formation {b} name={book.formations[b].name!r} plays={len(book.formations[b].play_links)}")
    print(f"\n## 0xB4 diff: formation {a} @ {fa:#x} vs {b} @ {fb:#x}")
    for i in range(0, FORMATION_SIZE, 16):
        ca = ra[i:i+16]; cb = rb[i:i+16]
        if ca != cb:
            print(f"{i:03x}: {ca.hex(' ')}  -> {cb.hex(' ')}  | diff")
        else:
            # dot for identical to keep output short, still countable
            pass
    print("\n## full 0xB4 hexdump a")
    print(_hexdump(ra, base=fa))
    print("\n## full 0xB4 hexdump b")
    print(_hexdump(rb, base=fb))
    # also dump aux for context — proves it is NOT coordinate storage
    axa = raw[body_off + aa : body_off + aa + FORMATION_AUX_SIZE]
    axb = raw[body_off + ab : body_off + ab + FORMATION_AUX_SIZE]
    print(f"\n## 0x50 aux a @ {aa:#x}: {axa.hex()}")
    print(f"## 0x50 aux b @ {ab:#x}: {axb.hex()}")


def dump_play_slot(index_path: pathlib.Path, inventory_path: pathlib.Path, asset_id: str, play: int, slot: int) -> None:
    from mod_editor.core.nfl2k5_playbook_inspector import NODE_BASE, NODE_SIZE

    sidecar = inventory_path.parent / "universal-assets-v1.sqlite3"
    idx = Nfl2k5UniversalAssetIndex(inventory_path, index_path, sidecar)
    rec = idx.get(asset_id)
    entry = idx.archive.entries[rec.outer_index]
    raw = read_entry_range(idx.archive, entry, rec.chunk_offset, rec.raw_size)
    book = parse_playbook_resource(raw, asset_id=asset_id)
    p = book.plays[play]
    ass = p.assignments[slot]
    print(f"# {asset_id} play {play}={p.name!r} slot {slot} descriptor={ass.descriptor_word:#x} chain_start={ass.chain_start_index}")
    # dump raw play bytes with pointer fields highlighted
    body_off = RESOURCE_HEADER_SIZE
    po = PLAY_BASE + play * PLAY_SIZE
    rp = raw[body_off + po : body_off + po + PLAY_SIZE]
    print(f"# play raw @ {po:#x} size {PLAY_SIZE:#x}")
    print(_hexdump(rp, base=po))
    # walk NODE pool 8-byte nodes from chain_start until terminal bit (byte1 & 0x02)
    try:
        start = ass.chain_start_index
        print(f"# chain walk from node {start} at NODE_BASE {NODE_BASE:#x} (NODE_SIZE {NODE_SIZE})")
        for step in range(32):  # cap to avoid runaway
            off = NODE_BASE + (start + step) * NODE_SIZE
            node = raw[body_off + off : body_off + off + NODE_SIZE]
            if len(node) < NODE_SIZE:
                print(f"#  truncated at step {step}")
                break
            b0, b1 = node[0], node[1]
            term = " TERM" if (b1 & 0x02) else ""
            print(f"  node {start+step:4d} @ {off:#06x}: {node.hex(' ')}  b0={b0:#04x} b1={b1:#04x}{term}")
            if b1 & 0x02:
                break
        else:
            print("#  chain hit 32-step cap without terminal")
    except Exception as e:
        print(f"# chain dump failed: {e}")
        import traceback; traceback.print_exc()


def main() -> int:
    ap = argparse.ArgumentParser(description="Dump formation 0xB4 and play node bytes for X/Y isolation")
    ap.add_argument("--index", type=pathlib.Path, required=False, help="pack0 file (vc_53450030/0)")
    ap.add_argument("--inventory", type=pathlib.Path, required=False, help="indexes/nfl2k5_resource_chunks_v2.json")
    ap.add_argument("--book", type=str, default="nfl2k5.resource.o0308.c0000.k504c4159", help="PLAY asset_id")
    ap.add_argument("--formation", type=int, default=0)
    ap.add_argument("--compare", type=int, default=1)
    ap.add_argument("--play", type=int, default=0)
    ap.add_argument("--slot", type=int, default=0)
    ap.add_argument("--dump-nodes", action="store_true")
    args = ap.parse_args()
    # default cache discovery
    if args.index is None:
        cands = list(pathlib.Path("/home/noah/.cache/2k5-mod-studio").glob("*/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
        if not cands:
            print("no pack0 found; pass --index", file=sys.stderr)
            return 2
        args.index = cands[0]
    if args.inventory is None:
        cands = list(pathlib.Path("/home/noah/.cache/2k5-mod-studio").glob("*/indexes/nfl2k5_resource_chunks_v2.json"))
        if not cands:
            print("no inventory found; pass --inventory", file=sys.stderr)
            return 2
        args.inventory = cands[0]
    dump_formations(args.index, args.inventory, args.book, args.formation, args.compare)
    if args.dump_nodes:
        print("\n" + "="*72 + "\n")
        dump_play_slot(args.index, args.inventory, args.book, args.play, args.slot)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
