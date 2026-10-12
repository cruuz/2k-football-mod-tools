#!/usr/bin/env python3
"""co2: apply the 2026 head coaches (bodies, Reid on the Reid model, faces) natively to a copy of a SOFTDRINK disc.

The disc is copied (the input is opened read only and must match --input-sha256), then the Studio's own module
(mod_editor/core/nfl2k5_modern_coaches.py) compiles every part it owns and writes it in place: the 32 coach scenes
(cNN.iff chunk 0, fixed spans; a scene that holds the co1 version is compiled from the RETAIL image's scene, so the
result equals a Studio build from retail), the 16-bit body id at +0x18 of each re-bodied club's coach record, and the
co1 parts (coachshirt chunks, portraits 7031/7034, two photo ids) when they are not already applied. Receipts:

  disc_write.json        every part, before/after SHA-256, absolute byte ranges, changed bytes
  disc_replay.json       a second pass plans and writes nothing (idempotent)
  disc_scope.json        full byte compare of input and output: every changed byte inside an owned range
  disc_studio_equality.json  each written span equals the Studio's compile from the RETAIL disc (pins included)

  python3 tools/b77/co2_repair.py --input IN.iso --input-sha256 HEX --output OUT.iso --receipts DIR --retail RETAIL.iso
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402

BLOCK = 1 << 20


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(BLOCK * 8), b""):
            h.update(block)
    return h.hexdigest()


def owned_ranges(image: Path, parts: list[dict]) -> list[tuple[int, int, str]]:
    out = []
    with mc._outer_image()(image) as archive:
        for p in parts:
            for pack, pack_offset, length in archive._segments(p["virtual_offset"], p["size"]):
                start = pack.image_offset + pack_offset
                out.append((start, start + length, f"{p['kind']}:{p['team']}"))
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
    ap.add_argument("--retail", type=Path, required=True,
                    help="retail USA image: the template for coach scenes that hold the co1 version, and the "
                         "Studio-equality receipt")
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
    before_status = mc.resource_states(a.output)
    plan, rows = mc.plan_image(a.output, retail=a.retail)
    with mc._outer_image()(a.output, writable=True) as archive:
        mc._write_all(archive, plan)
    after_status = mc.image_status(a.output)
    if after_status != "applied":
        raise SystemExit(f"read-back state is {after_status}")
    ranges = owned_ranges(a.output, rows)
    for r in rows:
        r["image_ranges"] = [[s, e] for s, e, label in ranges if label == f"{r['kind']}:{r['team']}"]
    write_receipt = dict(schema="b77_co2_disc_write/v1", input=str(a.input), input_sha256=digest, output=str(a.output),
                         status_before=before_status, status_after=after_status, written=len(plan),
                         changed_bytes=sum(r["changed_bytes"] for r in rows), parts=rows)
    (a.receipts / "disc_write.json").write_text(json.dumps(write_receipt, indent=1) + "\n", newline="\n")
    replay_plan, replay_rows = mc.plan_image(a.output, retail=a.retail)
    (a.receipts / "disc_replay.json").write_text(json.dumps(dict(
        schema="b77_co2_disc_replay/v1", planned_writes=len(replay_plan),
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
    scope = dict(schema="b77_co2_disc_scope/v1", input_sha256=digest, output_sha256=file_sha(a.output),
                 changed_runs=len(runs), changed_bytes=changed, owned_ranges=len(ranges),
                 owned_bytes=sum(e - s for s, e, _l in ranges), changed_outside_owned=len(outside),
                 first_outside=outside[:10])
    (a.receipts / "disc_scope.json").write_text(json.dumps(scope, indent=1) + "\n", newline="\n")
    if outside:
        raise SystemExit(f"{len(outside)} changed bytes outside the owned ranges")
    if a.retail:
        eq = []
        pins = mc.pins()
        with mc._outer_image()(a.retail) as retail, mc._outer_image()(a.output) as out:
            entries_r = {e.name_id: e for e in retail.entries}
            entries_o = {e.name_id: e for e in out.entries}
            for row in pins["teams"]:
                er, eo = entries_r[mc.name_id(row["archive"])], entries_o[mc.name_id(row["archive"])]
                studio, _detail = mc.compile_archive(retail.read(er.virtual_offset, er.size), row)
                span_s = studio[row["span_offset"]:row["span_offset"] + row["span_size"]]
                span_o = out.read(eo.virtual_offset + row["span_offset"], row["span_size"])
                whole_o = out.read(eo.virtual_offset, eo.size)
                eq.append(dict(part=f"coach:{row['team']}", studio_sha256=mc.sha(span_s), disc_sha256=mc.sha(span_o),
                               pin=row["applied_sha256"], equal=span_s == span_o and mc.sha(span_o) == row["applied_sha256"],
                               whole_archive_equal=whole_o == studio))
                for pkg in row["sideline"]:
                    _at_r, span_r = mc._package_span(retail, entries_r, pkg["package"], pkg["chunk_index"])
                    _at_o, span_o = mc._package_span(out, entries_o, pkg["package"], pkg["chunk_index"])
                    studio, _d = mc.compile_sideline(span_r, mc._rgba(mc.art_path(row["team"], pkg["design"]), 256, 256),
                                                     int(pkg["sideline_palette_max"]))
                    eq.append(dict(part=f"sideline:{row['team']}:{pkg['package']}", studio_sha256=mc.sha(studio),
                                   disc_sha256=mc.sha(span_o), pin=pkg["applied_sha256"],
                                   equal=studio == span_o and mc.sha(span_o) == pkg["applied_sha256"]))
            for row in pins["teams"]:
                if row["body_code"] != row["team_code"]:
                    _site, value = mc._coach_body_site(out, row["team"])
                    _site_r, value_r = mc._coach_body_site(retail, row["team"])
                    eq.append(dict(part=f"body_id:{row['team']}", retail_value=value_r, disc_value=value,
                                   expected=int(row["body_code"]), equal=value == int(row["body_code"])))
            for row in pins["portraits"]:
                at_r = retail.entries[row["outer_index"]].virtual_offset + row["chunk_offset"]
                at_o = out.entries[row["outer_index"]].virtual_offset + row["chunk_offset"]
                span_s = mc.portrait_span(retail.read(at_r, row["span_size"]), mc._rgba(mc.DATA_DIR / row["png"], 128, 128))
                span_o = out.read(at_o, row["span_size"])
                eq.append(dict(part=f"portrait:{row['team']}:{row['portrait_id']}", studio_sha256=mc.sha(span_s),
                               disc_sha256=mc.sha(span_o), pin=row["applied_sha256"], equal=span_s == span_o))
                site, value = mc._coach_photo_site(out, row["team"])
                eq.append(dict(part=f"photo_id:{row['team']}", disc_value=value, expected=int(row["portrait_id"]),
                               equal=value == int(row["portrait_id"])))
        (a.receipts / "disc_studio_equality.json").write_text(json.dumps(dict(
            schema="b77_co2_disc_studio_equality/v1", retail=str(a.retail), parts=eq,
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
