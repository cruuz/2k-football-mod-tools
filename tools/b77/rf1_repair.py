#!/usr/bin/env python3
"""rf1: apply the 2025-26 NFL officials natively to a copy of a SOFTDRINK disc.

The disc is copied (the input is opened read only and must match --input-sha256), then the Studio's own module
(mod_editor/core/nfl2k5_modern_officials.py) compiles every part it owns from the copy's own bytes and writes it in
place: the referee scene (gamedata.iff SCNE ``referee``: shirt, pants, the UV plan), the caps TSET (rhat_white and
rhat_black) and the seven number TXTR chunks (ref_R .. ref_BJ, HL drawn as DJ), each a fixed span found through the
copy's own outer and chunk tables. Receipts:

  disc_write.json            every part, before/after SHA-256, absolute image ranges, changed bytes
  disc_replay.json           a second pass plans and writes nothing (idempotent)
  disc_scope.json            full byte compare of input and output: every changed byte inside an owned range
  disc_studio_equality.json  each written span equals the Studio's compile from the RETAIL disc (and its pin)

  python3 tools/b77/rf1_repair.py --input IN.iso --input-sha256 HEX --output OUT.iso --receipts DIR --retail RETAIL.iso
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_officials as mo  # noqa: E402

BLOCK = 1 << 20
EXPECTED_INPUTS = {
    # the co2 disc Noah played on 2026-10-12 (the v0.6.1 candidate the evening fixes start from)
    "d735215760ff08bceeff2a3860baccf0a84885422a4205e966154e948812103e": "SOFTDRINK_2K28_v0.6.1-co2",
}


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(BLOCK * 8), b""):
            h.update(block)
    return h.hexdigest()


def owned_ranges(image: Path, rows: list[dict]) -> list[tuple[int, int, str]]:
    out = []
    with mo._outer_image()(image) as archive:
        for r in rows:
            for pack, pack_offset, length in archive._segments(r["virtual_offset"], r["size"]):
                start = pack.image_offset + pack_offset
                out.append((start, start + length, r["part"], pack.name))
    return sorted((s, e, f"{label}@vc_53450030/{pack}") for s, e, label, pack in out)


def changed_runs(a: Path, b: Path) -> list[tuple[int, int]]:
    import numpy as np
    runs = []
    with open(a, "rb") as fa, open(b, "rb") as fb:
        offset = 0
        while True:
            x, y = fa.read(BLOCK), fb.read(BLOCK)
            if not x and not y:
                break
            if x != y:
                n = min(len(x), len(y))
                d = np.frombuffer(x[:n], np.uint8) != np.frombuffer(y[:n], np.uint8)
                edges = np.flatnonzero(np.diff(np.concatenate([[0], d.view(np.int8), [0]])))
                for i, j in zip(edges[0::2], edges[1::2]):
                    i, j = int(i), int(j)
                    if runs and runs[-1][1] == offset + i:
                        runs[-1] = (runs[-1][0], offset + j)
                    else:
                        runs.append((offset + i, offset + j))
                if len(x) != len(y):
                    runs.append((offset + n, offset + max(len(x), len(y))))
            offset += len(x)
    return runs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--input-sha256", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--receipts", type=Path, required=True)
    ap.add_argument("--retail", type=Path, required=True, help="retail USA image: the Studio-equality template")
    a = ap.parse_args(argv)
    if a.input_sha256 not in EXPECTED_INPUTS:
        raise SystemExit(f"{a.input_sha256} is not a known input disc; refusing")
    a.receipts.mkdir(parents=True, exist_ok=True)
    digest = file_sha(a.input)
    if digest != a.input_sha256:
        raise SystemExit(f"input is {digest}, not the expected {a.input_sha256}")
    if a.output.exists():
        raise SystemExit(f"{a.output} exists; refusing to overwrite")
    tmp = a.output.with_name(a.output.name + ".partial")
    shutil.copyfile(a.input, tmp)
    if file_sha(tmp) != digest:
        raise SystemExit("the copy differs from the input")
    os.replace(tmp, a.output)
    before_status = mo.resource_states(a.output)
    if set(before_status.values()) != {"retail"}:
        raise SystemExit(f"the input's officials parts are not all retail: {before_status}")
    plan, rows = mo.plan_image(a.output, progress=lambda m, d, t: print(m, flush=True))
    with mo._outer_image()(a.output, writable=True) as archive:
        mo._write_all(archive, plan)
    after_status = mo.image_status(a.output)
    if after_status != "applied":
        raise SystemExit(f"read-back state is {after_status}")
    ranges = owned_ranges(a.output, rows)
    for r in rows:
        r["image_ranges"] = [[s, e, label.split("@")[1]] for s, e, label in ranges if label.split("@")[0] == r["part"]]
    files = sorted({label.split("@")[1] for _s, _e, label in ranges})
    write_receipt = dict(schema="b77_rf1_disc_write/v1", input=str(a.input), input_sha256=digest,
                         input_name=EXPECTED_INPUTS[digest], output=str(a.output), status_before=before_status,
                         status_after=after_status, written=len(plan), xiso_files_changed=files,
                         changed_bytes=sum(r["changed_bytes"] for r in rows), parts=rows)
    (a.receipts / "disc_write.json").write_text(json.dumps(write_receipt, indent=1) + "\n", newline="\n")
    replay_plan, replay_rows = mo.plan_image(a.output)
    (a.receipts / "disc_replay.json").write_text(json.dumps(dict(
        schema="b77_rf1_disc_replay/v1", planned_writes=len(replay_plan),
        states=sorted({r["state_before"] for r in replay_rows})), indent=1) + "\n", newline="\n")
    if replay_plan:
        raise SystemExit("the replay planned writes: not idempotent")
    runs = changed_runs(a.input, a.output)
    outside = []
    for s, e in runs:
        pos = s
        while pos < e:
            hit = [(rs, re_) for rs, re_, _l in ranges if rs <= pos < re_]
            if not hit:
                outside.append(pos)
                pos += 1
            else:
                pos = min(e, hit[0][1])
    changed = sum(e - s for s, e in runs)
    out_sha = file_sha(a.output)
    scope = dict(schema="b77_rf1_disc_scope/v1", input_sha256=digest, output_sha256=out_sha,
                 changed_runs=len(runs), changed_bytes=changed, owned_ranges=len(ranges),
                 owned_bytes=sum(e - s for s, e, _l in ranges), changed_outside_owned=len(outside),
                 first_outside=outside[:10], xiso_files_changed=files)
    (a.receipts / "disc_scope.json").write_text(json.dumps(scope, indent=1) + "\n", newline="\n")
    if outside:
        raise SystemExit(f"{len(outside)} changed bytes outside the owned ranges")
    eq = []
    document = mo.pins()
    with mo._outer_image()(a.retail) as retail, mo._outer_image()(a.output) as out:
        _er, raw_r = mo._archive_bytes(retail)
        _eo, raw_o = mo._archive_bytes(out)
        for row in document["parts"]:
            cr, co = mo._find_chunk(raw_r, row), mo._find_chunk(raw_o, row)
            span_r = raw_r[cr.offset:cr.offset + row["span_size"]]
            span_o = raw_o[co.offset:co.offset + row["span_size"]]
            studio, _detail = mo.compile_part(row, span_r)
            eq.append(dict(part=row["part"], retail_sha256=mo.sha(span_r), studio_sha256=mo.sha(studio),
                           disc_sha256=mo.sha(span_o), pin=row["applied_sha256"],
                           equal=studio == span_o and mo.sha(span_o) == row["applied_sha256"]
                           and mo.sha(span_r) == row["retail_sha256"]))
    (a.receipts / "disc_studio_equality.json").write_text(json.dumps(dict(
        schema="b77_rf1_disc_studio_equality/v1", retail=str(a.retail), parts=eq,
        all_equal=all(r["equal"] for r in eq)), indent=1) + "\n", newline="\n")
    if not all(r["equal"] for r in eq):
        raise SystemExit("a disc part differs from the Studio compile")
    a.output.with_name(a.output.name + ".sha256").write_text(f"{out_sha}  {a.output.name}\n", newline="\n")
    print(f"APPLIED {len(plan)} writes, {write_receipt['changed_bytes']} changed bytes; replay 0 writes")
    print(f"SCOPE {len(runs)} runs, {changed} bytes changed, {len(outside)} outside {len(ranges)} owned ranges")
    print(f"XISO FILES CHANGED {', '.join(files)}")
    print(f"STUDIO EQUALITY {sum(r['equal'] for r in eq)}/{len(eq)} parts equal")
    print(f"OUTPUT {a.output} {out_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
