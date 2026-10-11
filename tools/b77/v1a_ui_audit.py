#!/usr/bin/env python3
"""Audit extracted shipped books and optionally replay native user play-call panes.

Read-only inputs: default.xbe, entry3.bin and TEAM.play files in one directory.
The output is an evidence receipt, not a repaired disc or a game-play witness.
This tool does not perform native repairs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_playbook_inspector as ip


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(directory, *, native=False, books=None):
    paths = sorted(directory.glob("*.play"))
    if books:
        paths = [p for p in paths if p.stem in books]
        if set(books) != {p.stem for p in paths}:
            raise ValueError("one or more requested books are missing")
    if not paths:
        raise ValueError("no extracted .play files found")
    result = dict(schema="b771-v1a-ui-audit/v1", native=native,
                  gameplay_witness=False, input_directory=str(directory), books=[])
    if native:
        from tests.nfl2k5_user_play_menu_native import UserPlayMenuMachine
        xbe = (directory / "default.xbe").read_bytes()
        fonts = (directory / "entry3.bin").read_bytes()
        result.update(xbe_sha256=sha(xbe), entry3_sha256=sha(fonts),
                      fixture_limitations=UserPlayMenuMachine.__module__)
    for path in paths:
        raw = path.read_bytes()
        row = dict(book=path.stem, sha256=sha(raw), size=len(raw),
                   ui_problems=ip.playcall_ui_problems(raw), native_faults=[],
                   pages=0, formation_pages=0, panes=0, vertices=0)
        if native and not row["ui_problems"]:
            book = ip.parse_playbook_resource(raw)
            m = UserPlayMenuMachine(xbe, raw, fonts)
            current = None
            try:
                for order in m.CATEGORY_ORDERS:
                    categories = m.categories(order)
                    for page in range((len(categories) + 2) // 3):
                        current = dict(category_order=hex(order), page=page)
                        if m.formation_page(order, page) != categories[page*3:page*3+3]:
                            raise AssertionError("native formation page differs")
                        row["formation_pages"] += 1
                for f in book.formations:
                    order, ended = m.walk(f.index)
                    if not ended or order != [link.play_index for link in f.play_links]:
                        raise AssertionError("native menu order differs or cycles")
                    for page in range((len(order) + 2) // 3):
                        current = dict(formation=f.index, page=page)
                        returned, items = m.page_builder(f.index, page)
                        if not returned or items != order[page*3:page*3+3]:
                            raise AssertionError("native three-play page differs")
                        row["pages"] += 1
                    for flip in (0, 1):
                        current = dict(formation=f.index, play=None, flip=flip)
                        m.pane(f.index, flip=flip)
                        row["panes"] += 1
                        for link in f.play_links:
                            current["play"] = link.play_index
                            m.pane(f.index, link.play_index, flip=flip)
                            row["panes"] += 1
                row["vertices"] = m.vertices
                row["native_leaves"] = {hex(va): n for va, n in m.hits.items()}
                row["font_hashes"] = m.font_hashes
            except Exception as exc:
                row["native_faults"].append(dict(case=current, error=str(exc), pc=hex(m.reg("EIP"))))
        # Refuse a concurrently replaced extraction; this tool never writes its input.
        if path.read_bytes() != raw:
            raise ValueError(f"input changed during audit: {path}")
        result["books"].append(row)
        print(path.stem, "UI", len(row["ui_problems"]), "native faults", len(row["native_faults"]),
              "panes", row["panes"], flush=True)
    result["passed"] = all(not r["ui_problems"] and not r["native_faults"] for r in result["books"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--book", action="append")
    args = parser.parse_args()
    # Even an explicitly selected output must not overwrite an input resource.
    if args.out.resolve() in {p.resolve() for p in args.directory.iterdir() if p.is_file()}:
        raise ValueError("receipt must be a separate output file")
    result = audit(args.directory, native=args.native, books=args.book)
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
