#!/usr/bin/env python3
"""PROVED OFFLINE capacity census of NFL 2K5 PLAY books (b777 pb4).

Answers "how many plays can one team book hold" from the books themselves and the retail executable:

* the fixed body layout (``nfl2k5_playbook_inspector``): 50 formation records, 270 play records, 26 personnel groups,
  3,500 eight-byte nodes, the UTF-16 name pool from 0x10840 (the coach_ai tail starts at 0x13000), 36 menu links per
  formation, link play ids of 9 bits (0x1FF = empty);
* per book: formations and play records by kind (offense / defense / special teams), offense menu links (the plays a
  user can call), the largest formation menu, nodes and name units used;
* with ``--xbe``: every place the retail code names one of the layout constants as a 32-bit immediate (where a larger
  body would have to be re-laid out).

Books are wrapped PLAY resources (``*.bin`` or ``*.play``) in one or more folders, e.g. extracted from a disc with
``OuterImage.read_entry``.  Nothing is written except the optional ``--json`` receipt.

    python3 pb/v2/capacity.py RETAIL_BOOKS [MORE_BOOKS ...] [--xbe default.xbe] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402

UTILITY = ("Editor", "PRACTICE", "reference", "GEN", "WCO")
NAME_END = 0x13000          # coach_ai profile tail 0x13000-0x1337F (nfl2k5_coach_ai)
LAYOUT_CONSTANTS = {
    "body size (slot stride 0xE2F10, loader)": insp.BODY_SIZE,
    "string pool base": insp.STRING_BASE,
    "pool count word": 0x1083C,
    "category table": insp.CATEGORY_BASE,
    "node table": insp.NODE_BASE,
    "play table": insp.PLAY_BASE,
    "formation aux (links) table": insp.FORMATION_AUX_BASE,
}


def format_caps() -> dict:
    return dict(body_bytes=insp.BODY_SIZE, formations=insp.FORMATION_CAPACITY, plays=insp.PLAY_CAPACITY,
                categories=insp.CATEGORY_CAPACITY, nodes=(0x1083C - insp.NODE_BASE) // insp.NODE_SIZE,
                name_units_before_coach_tail=(NAME_END - insp.STRING_BASE) // 2,
                links_per_formation=insp.FORMATION_PLAY_LINKS, link_play_id_bits=9,
                page_size=insp.PLAYCALL_PLAYS_PER_PAGE)


def census(raw: bytes) -> dict:
    book = insp.parse_playbook_resource(raw)
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    kind = {f.index: lib.formation_record(body, f.index).type_code for f in book.formations}
    off_forms = [f for f in book.formations if kind[f.index] < 4]
    def_forms = [f for f in book.formations if 4 <= kind[f.index] < 8]
    links = [len(f.play_links) for f in off_forms]
    linked = {l.play_index for f in off_forms for l in f.play_links}
    fam = [p.family_id for p in book.plays]
    pool = struct.unpack_from("<I", body, 0x1083C)[0]
    return dict(book=book.book_name, formations=len(book.formations), offense_formations=len(off_forms),
                defense_formations=len(def_forms), special_formations=len(book.formations) - len(off_forms) - len(def_forms),
                plays=len(book.plays), offense_records=sum(1 for f in fam if f == 0),
                defense_records=sum(1 for f in fam if f == 1), special_records=sum(1 for f in fam if f >= 2),
                offense_links=sum(links), offense_records_linked=len(linked),
                links_per_record=round(sum(links) / max(1, len(linked)), 2), max_offense_menu=max(links, default=0),
                max_any_menu=max((len(f.play_links) for f in book.formations), default=0),
                categories=len(book.categories), nodes=book.node_count, name_units=pool,
                free_play_records=insp.PLAY_CAPACITY - len(book.plays),
                free_formation_records=insp.FORMATION_CAPACITY - len(book.formations))


def xbe_sites(xbe: bytes) -> dict:
    base = struct.unpack_from("<I", xbe, 0x104)[0]
    sh = struct.unpack_from("<I", xbe, 0x120)[0] - base
    _fl, va, vs, ra, rs = struct.unpack_from("<5I", xbe, sh)
    out = {}
    for label, value in LAYOUT_CONSTANTS.items():
        pat, hits, i = struct.pack("<I", value), [], ra
        while True:
            i = xbe.find(pat, i, ra + rs)
            if i < 0:
                break
            hits.append(hex(va + i - ra))
            i += 1
        out[label] = dict(value=hex(value), text_imm32_hits=len(hits), sites=hits)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("--xbe", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    receipt = dict(schema="pb_v2_capacity/v1", status="PROVED OFFLINE", caps=format_caps(), sets={})
    for folder in args.folders:
        rows = {}
        for p in sorted([*folder.glob("*.bin"), *folder.glob("*.play")]):
            if p.stem in UTILITY:
                continue
            rows[p.stem] = census(p.read_bytes())
        n = max(1, len(rows))
        mean = {k: round(sum(r[k] for r in rows.values()) / n, 1) for k in
                ("offense_formations", "offense_records", "defense_records", "special_records", "offense_links",
                 "max_offense_menu", "nodes", "name_units", "plays", "formations")}
        receipt["sets"][folder.name] = dict(books=len(rows), mean=mean, teams=rows)
        print(f"{folder.name}: {len(rows)} books, mean {mean}")
    if args.xbe:
        receipt["xbe_layout_sites"] = xbe_sites(args.xbe.read_bytes())
        for label, row in receipt["xbe_layout_sites"].items():
            print(f"  {label} {row['value']}: {row['text_imm32_hits']} .text imm32 hits {row['sites'][:8]}")
    if args.json:
        args.json.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
