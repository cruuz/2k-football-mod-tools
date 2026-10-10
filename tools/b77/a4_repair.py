#!/usr/bin/env python3
"""Native v0.5 repair for job A4 (+ a4pd): era-correct shotgun use in the Anniversary moments and, per franchise, per down and
distance bin in exhibition, season and franchise games (``default.xbe`` only).

    python3 tools/b77/a4_repair.py --input-dir DIR_WITH_default.xbe --output-dir NEW_DIR [--expected-input-sha256 SHA]
                                   [--eras data/nfl2k5_moment_playbook_eras.json]
                                   [--refit-books DIR --selection-model-dir TREE]

The repair is a function of the bytes the stock book owner ``mod_editor/core/nfl2k5_stock_books.py`` owns (its 1,536 byte
allocation and the one shotgun site it now also installs), so it composes with every other job's ``default.xbe`` edit
(guards are pinned bytes, not whole-file hashes). It accepts the v0.5 executable, its own result (idempotent: the output is the
input), or a stacked integration input named with ``--expected-input-sha256`` (which may already carry the earlier a4 body, one shotgun
weight per franchise: it is completed in place). Exact shipped a4pd bodies are also upgraded in place:
the selector's live-team argument must be dereferenced at +0x1c before accessing roster fields.
The v0.5 stock book resolver must be installed.

What changes (everything else is proved identical, byte for byte):

* the 1,536 bytes of the stock book allocation (no allocation moves, none is added): the resolver body is rebuilt so its 32
  alias rows shrink from 40 to 8 bytes (it composes the same ``E2R-<key>-pb.iff`` string), which frees room for the stub (252 bytes)
  and 51 float32 shotgun weights for the moments;
* the stub also serves every franchise team in exhibition, season and franchise games: a table of 32 x 7 weights (uint16 multiples of
  0.05) fitted to 2025 and 2026 nflverse shotgun rates per down and distance bin (1st; 2nd and 1-3 / 4-7 / 8+; 3rd and 4th and
  1-3 / 4-6 / 7+); historic teams, unknown keys, downs outside 1 to 4, the inside of the 10 and the goal line keep the retail constant;
* the pinned 6 byte site ``fld dword [0x4E6D10]`` at VA 0x207F99 inside the formation weight 0x207EF0 becomes ``call stub; nop``;
* the derived metadata those writes require: the allocator directory page (the SHA-256 seal of the owned code), its header copy and
  the SHA-1 digests of the sections (shared with every other job; whoever applies last recomputes them).

Stack order: independent of the other repairs (no late owner, no allocation); proved to give the same bytes after or before
``a1_repair.py`` and to apply on the f4b-repaired and p9-repaired executables.

Re-run when the final offense and defense books are known: pass the 32 final PLAY entries extracted as ``<KEY>.play``
(``--refit-books``) together with a tree that has ``pb/v2/selection_model.py`` (``--selection-model-dir``); every modern
moment's weight and every franchise's seven bin weights are refitted from those exact bytes and the refitted data file is written next to the output
(``a4_moment_playbook_eras.refit.json``; commit it as ``data/nfl2k5_moment_playbook_eras.json`` to keep the Studio in step).
Without those flags the committed data file is used. Nothing is written next to the inputs; outputs are created exclusively.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_moment_gun_weight as gw  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_stock_books as stock  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

V05_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
MAX_XBE = 16 * 1024 * 1024
SCHEMA = "b77.a4.xbe-repair.v3"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def declared_scopes(after: bytes) -> list[tuple[int, int, str]]:
    found = stock.allocation(after)
    scopes = [(found["raw"], found["raw"] + stock.CODE_SIZE, "stock book resolver allocation (1,536 bytes: body, key rows, stub, 51 moment weights, 32 x 7 bin weights)"),
              (space.SCALE_DIRECTORY, space.SCALE_DIRECTORY + space.PAGE, "allocator directory page (requests and SHA-256 seals)"),
              (space.DIRECTORY, space.LIB_COPY, "allocator header copy of the directory seal")]
    for label, va, retail, _patched in stock.gun_sites(found["va"]):
        off = rdata.offset_of(after, va)
        scopes.append((off, off + len(retail), f"site {label} @ {va:#x}"))
    for section in XbeImage(after).sections:
        scopes.append((section.header + 36, section.header + 56, f"{section.name} section SHA-1"))
    scopes.sort()
    for (a, b, _), (c, d, _) in zip(scopes, scopes[1:]):
        if c < b:
            raise ValueError(f"overlapping repair scopes {a:#x}..{b:#x} / {c:#x}..{d:#x}")
    return scopes


def scope_receipt(before: bytes, after: bytes) -> dict:
    if len(before) != len(after):
        raise ValueError("the repair changed the file size")
    scopes = declared_scopes(after)
    restored = bytearray(after)
    for start, end, _label in scopes:
        restored[start:end] = before[start:end]
    if bytes(restored) != before:
        stray = [i for i in range(len(before)) if restored[i] != before[i]][:8]
        raise ValueError(f"bytes changed outside the declared scope, first at {[hex(i) for i in stray]}")
    rows = []
    for start, end, label in scopes:
        b, a = before[start:end], after[start:end]
        rows.append({"label": label, "file_offset": hex(start), "size": end - start, "changed": b != a,
                     "changed_bytes": sum(x != y for x, y in zip(b, a)),
                     "before_sha256": sha(b), "after_sha256": sha(a),
                     **({"before_hex": b.hex(), "after_hex": a.hex()} if end - start <= 64 and b != a else {})})
    changed = sum(x != y for x, y in zip(before, after))
    return {"before_sha256": sha(before), "after_sha256": sha(after), "size": len(after), "changed_bytes": changed,
            "scopes": rows, "scopes_total": len(rows), "scopes_changed": sum(r["changed"] for r in rows),
            "outside_scope_identical": True, "outside_scope_restored_sha256": sha(bytes(restored))}


def repair_xbe(payload: bytes, values: list[float], team_values: list[list[float]]) -> tuple[bytes, dict]:
    if stock.status(payload) not in ("needs_fix", "applied"):
        raise ValueError("the stock book resolver (Stock playbooks for historic teams) must be installed first, and unchanged elsewhere")
    after, apply_receipt = stock.apply(payload, weights=values, team_weights=team_values)
    receipt = scope_receipt(payload, after)
    old_allocations = space._scale_allocations(space._read_scale_directory(payload))
    new_allocations = space._scale_allocations(space._read_scale_directory(after))
    receipt.update(
        schema=SCHEMA, disc_file="default.xbe", status="already_applied" if after == payload else "applied", owner=stock.OWNER,
        existing_allocations_unchanged=old_allocations == new_allocations,
        owner_allocations=[row for row in new_allocations if row["owner"] == stock.OWNER],
        sites=[{"label": label, "va": hex(va), "size": len(old)} for label, va, old, _new in stock.gun_sites(stock.allocation(after)["va"])],
        weights=[round(v, 4) for v in values],
        team_bin_weights={key: dict(zip(gw.BIN_NAMES, row)) for key, row in zip(stock.key_order(), team_values)},
        live_team_roster_offset=gw.ROSTER_OFFSET,
        corrects_shipped_a4pd_team_pointer=True,
        gameplay_witness=False)
    if not receipt["existing_allocations_unchanged"]:
        raise ValueError("an allocator owner moved")
    return after, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", action="append", default=[],
                        help="sha256 of a stacked integration input (repeatable); the v0.5 executable is always accepted")
    parser.add_argument("--eras", type=Path, default=gw.DATA)
    parser.add_argument("--refit-books", type=Path, help="directory of the final <KEY>.play entries: refit every weight from them")
    parser.add_argument("--selection-model-dir", type=Path, help="tree with pb/v2/selection_model.py (needed with --refit-books)")
    args = parser.parse_args()

    source = args.input_dir / "default.xbe"
    payload = source.read_bytes()
    if len(payload) > MAX_XBE:
        raise SystemExit("input is not a plausible default.xbe")
    accepted = {V05_SHA256, *args.expected_input_sha256}
    if sha(payload) not in accepted and stock.status(payload) != "applied":
        raise SystemExit(f"refused: input sha256 {sha(payload)} is not v0.5 and is not named by --expected-input-sha256")

    data = gw.load(args.eras)
    refit_path = None
    if args.refit_books:
        if not args.selection_model_dir:
            raise SystemExit("--refit-books needs --selection-model-dir")
        from tools.b77 import a4_eras
        data = a4_eras.refit(data, args.refit_books, args.selection_model_dir)
    values = gw.weights(data)
    team_values = gw.team_bin_weights(data, keys=stock.key_order())

    after, receipt = repair_xbe(payload, values, team_values)
    receipt["eras_data_sha256"] = sha(json.dumps(data, sort_keys=True).encode())
    receipt["refit_from_books"] = str(args.refit_books) if args.refit_books else None
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / "default.xbe"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(destination, flags, 0o644), "wb") as handle:
        handle.write(after)
    if args.refit_books:
        refit_path = out_dir / "a4_moment_playbook_eras.refit.json"
        refit_path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    receipt_path = out_dir / "a4_receipt.json"
    with os.fdopen(os.open(receipt_path, flags, 0o644), "wb") as handle:
        handle.write((json.dumps(receipt, indent=1) + "\n").encode())
    print(json.dumps({"status": "DONE", "before_sha256": receipt["before_sha256"], "after_sha256": receipt["after_sha256"],
                      "output": str(destination), "receipt": str(receipt_path), "changed_bytes": receipt["changed_bytes"],
                      "scopes_changed": receipt["scopes_changed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
