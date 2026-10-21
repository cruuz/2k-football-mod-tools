#!/usr/bin/env python3
"""fr1: apply the 2026 fans natively to a SOFTDRINK disc, in place on one copy, with byte receipts.

The input is opened read only and must match --input-sha256; it is copied straight to the output name and the
Studio's own module (mod_editor/core/nfl2k5_modern_fans.py) compiles every retail crowd texture from the copy's own
bytes and writes it in place (fixed spans: the 32 clubs' crowd texture sets, four archive families). Receipts:

  disc_write.json            every part, before/after SHA-256, absolute byte ranges, changed bytes
  disc_replay.json           a second pass plans and writes nothing (idempotent)
  disc_scope.json            full byte compare of input and output: every changed byte inside an owned range
  disc_studio_equality.json  each written span equals the Studio's compile from the RETAIL disc (pins included)

  python3 tools/b77/fr1_repair.py --input IN.iso --input-sha256 HEX --output OUT.iso --receipts DIR [--retail RETAIL.iso]
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
from mod_editor.core import nfl2k5_modern_fans as mf  # noqa: E402

BLOCK = 1 << 20


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(BLOCK * 8), b""):
            h.update(block)
    return h.hexdigest()


def owned_ranges(image: Path, parts: list[dict]) -> list[tuple[int, int, str]]:
    out = []
    with mf._outer_image()(image) as archive:
        for p in parts:
            for pack, pack_offset, length in archive._segments(p["virtual_offset"], p["size"]):
                start = pack.image_offset + pack_offset
                out.append((start, start + length, p["key"]))
    return sorted(out)


def changed_runs(a: Path, b: Path) -> list[tuple[int, int]]:
    runs = []
    with open(a, "rb") as fa, open(b, "rb") as fb:
        offset = 0
        while True:
            x, y = fa.read(BLOCK), fb.read(BLOCK)
            if not x and not y:
                break
            if x != y:
                import numpy as np
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
    ap.add_argument("--retail", type=Path, help="retail USA image for the Studio-equality receipt")
    a = ap.parse_args(argv)
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
    before_states = mf.resource_states(a.output)
    plan, rows = mf.plan_image(a.output)
    with mf._outer_image()(a.output, writable=True) as archive:
        mf._write_all(archive, plan)
    after_status = mf.image_status(a.output)
    if after_status != "applied":
        raise SystemExit(f"read-back state is {after_status}")
    ranges = owned_ranges(a.output, rows)
    for r in rows:
        r["image_ranges"] = [[s, e] for s, e, label in ranges if label == r["key"]]
    write_receipt = dict(schema="b77_fr1_disc_write/v1", input=str(a.input), input_sha256=digest, output=str(a.output),
                         states_before=sorted(set(before_states.values())), status_after=after_status,
                         written=len(plan), changed_bytes=sum(r["changed_bytes"] for r in rows), parts=rows)
    (a.receipts / "disc_write.json").write_text(json.dumps(write_receipt, indent=1) + "\n", newline="\n")
    replay_plan, replay_rows = mf.plan_image(a.output)
    (a.receipts / "disc_replay.json").write_text(json.dumps(dict(
        schema="b77_fr1_disc_replay/v1", planned_writes=len(replay_plan),
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
    scope = dict(schema="b77_fr1_disc_scope/v1", input_sha256=digest, output_sha256=file_sha(a.output),
                 changed_runs=len(runs), changed_bytes=changed, owned_ranges=len(ranges),
                 owned_bytes=sum(e - s for s, e, _l in ranges), changed_outside_owned=len(outside),
                 first_outside=outside[:10])
    (a.receipts / "disc_scope.json").write_text(json.dumps(scope, indent=1) + "\n", newline="\n")
    if outside:
        raise SystemExit(f"{len(outside)} changed bytes outside the owned ranges")
    if a.retail:
        eq = []
        with mf._outer_image()(a.retail) as retail, mf._outer_image()(a.output) as out:
            entries_r = {e.name_id: e for e in retail.entries}
            entries_o = {e.name_id: e for e in out.entries}
            cache_r: dict = {}
            cache_o: dict = {}
            memo: dict = {}
            for p in mf.pins()["parts"]:
                _at, span_r = mf._locate(retail, entries_r, p, cache_r)
                _at, span_o = mf._locate(out, entries_o, p, cache_o)
                key = (p["retail_sha256"], p["art_sha256"], p["palette_max"])
                if key not in memo:
                    memo[key] = mf.compile_part(span_r, p)[0]
                studio = memo[key]
                eq.append(dict(part=f"{p['team']}:{p['set']}:{p['name']}", studio_sha256=mf.sha(studio),
                               disc_sha256=mf.sha(span_o), pin=p["applied_sha256"],
                               equal=studio == span_o and mf.sha(span_o) == p["applied_sha256"]))
        (a.receipts / "disc_studio_equality.json").write_text(json.dumps(dict(
            schema="b77_fr1_disc_studio_equality/v1", retail=str(a.retail), parts=eq,
            all_equal=all(r["equal"] for r in eq)), indent=1) + "\n", newline="\n")
        if not all(r["equal"] for r in eq):
            raise SystemExit("a disc part differs from the Studio compile")
    out_sha = scope["output_sha256"]
    a.output.with_name(a.output.name + ".sha256").write_text(f"{out_sha}  {a.output.name}\n", newline="\n")
    print(f"APPLIED {len(plan)} writes, {write_receipt['changed_bytes']} changed bytes; replay 0 writes")
    print(f"SCOPE {len(runs)} runs, {changed} bytes changed, {len(outside)} outside {len(ranges)} owned ranges")
    print(f"OUTPUT {a.output} {out_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
