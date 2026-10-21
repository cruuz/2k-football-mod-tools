#!/usr/bin/env python3
"""co3: carry the b77 co3 coach-art change into a copy of the v0.6.1 disc, in place, with receipts.

What co3 changes on a disc: only the two Coach Matchup / VIP pictures, portraits 7031 (Dallas, Brian Schottenheimer)
and 7034 (Washington, Dan Quinn). co1's pictures (photo crops) are replaced by authored renders of the game's own
coach (mod_editor/core/nfl2k5_modern_coaches.py pins them as ``superseded_sha256`` -> state ``previous``). The other
two co3 changes write no disc bytes and are proved here instead:

* the accessories atlas now ships only its authored headset half; the shoe and clipboard come from the disc at build
  time (``derive_accessories``). Every coach scene compiled that way from the RETAIL image equals the scene on this
  disc and its pin (the disc bytes did not change);
* the coach AI roster gate decides before a build writes anything; this disc's roster carries the 2026 head coaches,
  so it reads ready (no write).

The image is written in place (the job keeps one disc copy). The input must be the v0.6.1 shortcut disc
(--input-sha256 is fixed below and refused otherwise); an image that already carries this repair is only checked.

Receipts (in --receipts):
  disc_write.json            every planned part with before/after SHA-256, absolute image ranges, changed bytes
  disc_replay.json           a second plan writes nothing
  disc_scope.json            a full byte compare against --original (the untouched input, read only): every changed
                             byte inside the owned ranges
  disc_studio_equality.json  each owned span equals the Studio module's compile from --retail (pins too); every coach
                             scene and sideline chunk on the disc equals its compile from retail
  roster_gate.json           the coach AI roster readiness of the output (read only)

  python3 tools/b77/co3_repair.py --image COPY.iso --original ORIGINAL.iso --retail RETAIL.iso --receipts DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402

INPUT_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"   # SOFTDRINK 2K28 v0.6.1 fixes
INPUT_SIZE = 6_004_408_320
BLOCK = 1 << 23


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb", buffering=0) as f:
        for block in iter(lambda: f.read(BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def refuse(message: str) -> None:
    raise SystemExit(f"co3_repair: REFUSED: {message}")


def owned_ranges(image: Path, rows: list[dict]) -> list[tuple[int, int, str]]:
    out = []
    with mc._outer_image()(image) as archive:
        for r in rows:
            for pack, pack_offset, length in archive._segments(r["virtual_offset"], r["size"]):
                start = pack.image_offset + pack_offset
                out.append((start, start + length, f"{r['kind']}:{r['team']}"))
    return sorted(out)


def changed_runs(a: Path, b: Path) -> list[tuple[int, int]]:
    import numpy as np
    runs = []
    fa = os.open(a, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    fb = os.open(b, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        offset = 0
        while True:
            x, y = os.read(fa, BLOCK), os.read(fb, BLOCK)
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
    finally:
        os.close(fa)
        os.close(fb)
    return runs


def write_json(path: Path, value) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=1) + "\n")


def studio_equality(image: Path, retail: Path) -> list[dict]:
    pins = mc.pins()
    eq = []
    with mc._outer_image()(retail) as r_arc, mc._outer_image()(image) as o_arc:
        entries_r = {e.name_id: e for e in r_arc.entries}
        entries_o = {e.name_id: e for e in o_arc.entries}
        for row in pins["portraits"]:
            at_r = r_arc.entries[row["outer_index"]].virtual_offset + row["chunk_offset"]
            at_o = o_arc.entries[row["outer_index"]].virtual_offset + row["chunk_offset"]
            studio = mc.portrait_span(r_arc.read(at_r, row["span_size"]), mc._rgba(mc.DATA_DIR / row["png"], 128, 128))
            disc = o_arc.read(at_o, row["span_size"])
            eq.append(dict(part=f"portrait:{row['team']}:{row['portrait_id']}", owned_by_co3=True,
                           studio_sha256=mc.sha(studio), disc_sha256=mc.sha(disc), pin=row["applied_sha256"],
                           equal=studio == disc and mc.sha(disc) == row["applied_sha256"]))
            _site, value = mc._coach_photo_site(o_arc, row["team"])
            eq.append(dict(part=f"photo_id:{row['team']}", owned_by_co3=False, disc_value=value,
                           expected=int(row["portrait_id"]), equal=value == int(row["portrait_id"])))
        for row in pins["teams"]:
            er, eo = entries_r[mc.name_id(row["archive"])], entries_o[mc.name_id(row["archive"])]
            studio, detail = mc.compile_archive(r_arc.read(er.virtual_offset, er.size), row)
            span_s = studio[row["span_offset"]:row["span_offset"] + row["span_size"]]
            span_o = o_arc.read(eo.virtual_offset + row["span_offset"], row["span_size"])
            eq.append(dict(part=f"coach:{row['team']}", owned_by_co3=False, archive=row["archive"],
                           headset=detail["textures"]["headset"].get("derived"),
                           studio_sha256=mc.sha(span_s), disc_sha256=mc.sha(span_o), pin=row["applied_sha256"],
                           equal=span_s == span_o and mc.sha(span_o) == row["applied_sha256"]))
            for pkg in row["sideline"]:
                _a, span_r = mc._package_span(r_arc, entries_r, pkg["package"], pkg["chunk_index"])
                _b, span_o = mc._package_span(o_arc, entries_o, pkg["package"], pkg["chunk_index"])
                studio_s, _d = mc.compile_sideline(span_r, mc._rgba(mc.art_path(row["team"], pkg["design"]), 256, 256),
                                                   int(pkg["sideline_palette_max"]))
                eq.append(dict(part=f"sideline:{row['team']}:{pkg['package']}", owned_by_co3=False,
                               studio_sha256=mc.sha(studio_s), disc_sha256=mc.sha(span_o), pin=pkg["applied_sha256"],
                               equal=studio_s == span_o and mc.sha(span_o) == pkg["applied_sha256"]))
    return eq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=Path, required=True, help="this job's copy of the v0.6.1 disc (written in place)")
    ap.add_argument("--original", type=Path, required=True, help="the untouched v0.6.1 disc, read only")
    ap.add_argument("--retail", type=Path, required=True, help="the retail USA image, read only")
    ap.add_argument("--receipts", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.image.resolve() == a.original.resolve():
        refuse("--image must be a copy, not the original")
    a.receipts.mkdir(parents=True, exist_ok=True)
    original_sha = file_sha(a.original)
    if original_sha != INPUT_SHA256 or a.original.stat().st_size != INPUT_SIZE:
        refuse(f"--original is {original_sha}, not the v0.6.1 disc {INPUT_SHA256}")
    image_sha = file_sha(a.image)
    states = mc.resource_states(a.image)
    counts: dict[str, int] = {}
    for value in states.values():
        counts[value] = counts.get(value, 0) + 1
    portrait_states = {k: v for k, v in states.items() if k.startswith("portrait:")}
    others = {k: v for k, v in states.items() if not k.startswith("portrait:")}
    if any(v != "applied" for v in others.values()):
        refuse("a coach scene, sideline chunk, body id or photo id is not the applied v0.6.1 state: "
               + ", ".join(f"{k}={v}" for k, v in others.items() if v != "applied"))
    if image_sha == INPUT_SHA256:
        if set(portrait_states.values()) != {"previous"}:
            refuse(f"the v0.6.1 disc's portraits read {portrait_states}, expected co1's pictures (previous)")
    elif set(portrait_states.values()) != {"applied"}:
        refuse(f"--image is {image_sha}: neither the v0.6.1 disc nor a disc carrying this repair")
    plan, rows = mc.plan_image(a.image)
    planned = [(r["kind"], r["team"]) for r in rows if r.get("written")]
    if image_sha == INPUT_SHA256 and sorted(planned) != [("portrait", "DAL"), ("portrait", "WAS")]:
        refuse(f"the plan is not exactly the two portrait spans: {planned}")
    owned_rows = [r for r in rows if r["kind"] == "portrait"]
    ranges = owned_ranges(a.image, owned_rows)
    with mc._outer_image()(a.image, writable=True) as archive:
        mc._write_all(archive, plan)                       # checks each span against its preflight, reads back
    after_status = mc.image_status(a.image)
    if after_status != "applied":
        refuse(f"read-back state is {after_status}")
    for r in owned_rows:
        r["image_ranges"] = [[s, e] for s, e, label in ranges if label == f"{r['kind']}:{r['team']}"]
    output_sha = file_sha(a.image)
    write_json(a.receipts / "disc_write.json", dict(
        schema="b77_co3_disc_write/v1", image=str(a.image), input_sha256=image_sha, output_sha256=output_sha,
        state_counts_before=counts, portrait_states_before=portrait_states, status_after=after_status,
        written=len(plan), changed_bytes=sum(r["changed_bytes"] for r in rows),
        parts=[dict({k: v for k, v in r.items() if k not in ("row",)}) for r in owned_rows]))
    replay_plan, replay_rows = mc.plan_image(a.image)
    write_json(a.receipts / "disc_replay.json", dict(
        schema="b77_co3_disc_replay/v1", planned_writes=len(replay_plan), written_bytes=0,
        states=sorted({r["state_before"] for r in replay_rows})))
    if replay_plan:
        refuse("the replay planned writes: not idempotent")
    runs = changed_runs(a.original, a.image)
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
    write_json(a.receipts / "disc_scope.json", dict(
        schema="b77_co3_disc_scope/v1", original=str(a.original), original_sha256=original_sha,
        output_sha256=output_sha, compared_bytes=INPUT_SIZE, changed_runs=len(runs), changed_bytes=changed,
        owned_ranges=[[s, e, label] for s, e, label in ranges], owned_bytes=sum(e - s for s, e, _l in ranges),
        changed_outside_owned=len(outside), first_outside=outside[:10]))
    if outside:
        refuse(f"{len(outside)} changed bytes outside the owned ranges")
    eq = studio_equality(a.image, a.retail)
    write_json(a.receipts / "disc_studio_equality.json", dict(
        schema="b77_co3_disc_studio_equality/v1", retail=str(a.retail), parts=eq,
        owned_parts=sum(1 for r in eq if r["owned_by_co3"]), all_equal=all(r["equal"] for r in eq)))
    if not all(r["equal"] for r in eq):
        refuse("a disc part differs from the Studio compile")
    from mod_editor.core import nfl2k5_coach_ai as ai
    gate = ai.roster_readiness(a.image)
    write_json(a.receipts / "roster_gate.json", dict(schema="b77_co3_roster_gate/v1", **gate))
    with open(a.image.with_name(a.image.name + ".sha256"), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{output_sha}  {a.image.name}\n")
    print(f"APPLIED {len(plan)} writes, {sum(r['changed_bytes'] for r in rows)} changed bytes; replay 0 writes")
    print(f"SCOPE {len(runs)} runs, {changed} bytes changed against the original, {len(outside)} outside "
          f"{len(ranges)} owned ranges")
    print(f"STUDIO {sum(1 for r in eq if r['equal'])}/{len(eq)} parts equal the Studio compile from retail "
          f"({sum(1 for r in eq if r['owned_by_co3'])} owned by co3)")
    print(f"ROSTER GATE ready={gate['ready']} checked={gate['checked']}")
    print(f"OUTPUT {a.image} {output_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
