#!/usr/bin/env python3
"""FRZ4: scoped X4 (original a4) and X5 (live-team pointer fix) diagnostics.

No emulator or disc copy is run. Use frz_xbe_bisect.py disc for coordinator tests.
X4 deliberately retains a4's bad live-team pointer, to isolate the a4pd change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from tools.b77 import frz_xbe_bisect as b
from tools.b77 import a4_repair
from mod_editor.core import nfl2k5_stock_books as stock
from mod_editor.core import nfl2k5_moment_gun_weight as gun
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

A4_COMMIT = "65254714"


def historical_a4():
    """Read-only historical sources; never checkout, import or write another tree."""
    paths = ("tools/b77/a4_repair.py", "mod_editor/core/nfl2k5_moment_gun_weight.py",
             "data/nfl2k5_moment_playbook_eras.json")
    raw = {p: subprocess.check_output(["git", "show", f"{A4_COMMIT}:{p}"], cwd=ROOT) for p in paths}
    namespace = dict(__name__="mod_editor.core._frz4_a4_reference", __package__="mod_editor.core",
                     __file__=str(ROOT / paths[1]))
    exec(compile(raw[paths[1]], f"{A4_COMMIT}:{paths[1]}", "exec"), namespace)
    return namespace, json.loads(raw[paths[2]]), {p: b.sha(v) for p, v in raw.items()}


def build(final, variant):
    b.require(b.sha(final) == b.V06_HASH and b.digests_ok(final), "requires the exact final v0.6 executable")
    b.require(variant in ("X4", "X5"), "unknown FRZ4 variant")
    allocation = stock.allocation(final)
    va, at = allocation["va"], allocation["raw"]
    image = XbeImage(final)
    moments = gun.decode_table(image.read(va + stock.WEIGHT_OFFSET, gun.TABLE_SIZE))
    bins = gun.decode_bin_table(image.read(va + stock.BIN_TABLE_OFFSET, gun.BIN_TABLE_SIZE))
    evidence = {}
    if variant == "X4":
        legacy, data, hashes = historical_a4()
        teams = legacy["team_weights"](data, keys=stock.key_order())
        body = stock.code_for(va, single_weight=True, weights=moments, team_weights=teams)
        stub = legacy["stub_bytes"](va + stock.STUB_OFFSET, va + stock.SINGLE_WEIGHT_OFFSET,
                                    va + stock.TABLE, va + stock.SINGLE_TEAM_OFFSET)
        b.require(stub == body[stock.STUB_OFFSET:stock.STUB_OFFSET + gun.STUB_SPACE_SINGLE],
                  "single-weight stub differs from a4 reference")
        result = stock._write_body(final, allocation, body)
        evidence = dict(a4_commit=A4_COMMIT, reference_sha256=hashes, stub_matches_a4_exactly=True,
                        single_team_weights=teams, moment_values_preserved=True,
                        retains_live_team_pointer_defect=True)
        payload_ranges = [(stock.STUB_OFFSET, stock.CODE_SIZE - stock.STUB_OFFSET,
                           "a4 stub, relocated moment table, single team table and padding")]
    else:
        result, repair_receipt = a4_repair.repair_xbe(final, moments, bins)
        evidence = dict(repair=repair_receipt, moment_and_bin_tables_identical=True,
                        inserted_instructions="mov eax,[eax+0x1c]; test eax,eax; je ordinary")
        payload_ranges = [(stock.STUB_OFFSET, gun.STUB_SPACE, "fixed per-bin stub")]
    ranges = [dict(file_offset=at + off, va=va + off, size=size, kind="payload", label=label)
              for off, size, label in payload_ranges]
    # Keep all allocator requests and placements. Recompute only their seals.
    metadata = [(b.space.DIRECTORY, b.space.LIB_COPY - b.space.DIRECTORY, "allocator header seals"),
                (b.space.SCALE_DIRECTORY, b.space.PAGE, "allocator page seals")]
    metadata += [(s.header_offset + 36, 20, "section digest " + str(s.index)) for s in b._sections(result)]
    for start, length, label in metadata:
        for off, size in b.changed_ranges(final[start:start + length], result[start:start + length]):
            ranges.append(dict(file_offset=start + off, size=size, kind="derived", label=label))
    restored = b.verify_scope(final, result, ranges)
    b.require(b.space.layout(final)["allocations"] == b.space.layout(result)["allocations"], "placements changed")
    b.require(b.space._read_scale_directory(final) == b.space._read_scale_directory(result), "requests changed")
    b.require(b.digests_ok(result) and b.space.status(result) == "applied", "invalid seals")
    for row in ranges:
        start, size = row["file_offset"], row["size"]
        row.update(before_sha256=b.sha(final[start:start + size]), after_sha256=b.sha(result[start:start + size]),
                   changed_bytes=sum(x != y for x, y in zip(final[start:start + size], result[start:start + size])))
    changes = b.changed_ranges(final, result)
    receipt = dict(schema="b77/frz4-stub/v1", variant=variant, v06_sha256=b.sha(final), sha256=b.sha(result),
                   size=len(result), changed_bytes=sum(n for _, n in changes), changed_ranges=changes, ranges=ranges,
                   outside_scope_identical=True, restored_scope_sha256=restored,
                   allocator_requests_and_placements_unchanged=True, section_digests_valid=True,
                   runtime_witness=False, evidence=evidence)
    return result, receipt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--v06", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    final, _ = b.read_xbe(args.v06)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("X4", "X5"):
        raw, receipt = build(final, name)
        path = args.out_dir / (name + ".default.xbe")
        b.write_new(path, raw)
        b.write_new(path.with_suffix(path.suffix + ".receipt.json"), b.json_bytes(receipt))
        print(name, receipt["sha256"], receipt["changed_bytes"], "changed bytes; scope and seals valid", flush=True)


if __name__ == "__main__":
    main()
