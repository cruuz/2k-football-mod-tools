#!/usr/bin/env python3
"""cm1: carry the b77 cm1 coach-model change into a copy of the v0.6.1 disc, in place, with receipts.

What cm1 changes on a disc: the coach scene (``cNN.iff`` chunk 0, one fixed span each) of nine clubs.

* Washington (Dan Quinn, c29): a bald head (the 2004 hair volume off the scalp, the headset band and the low-detail
  head following), a new head texture (one pale skin tone, his white goatee, no hair layout);
* Dallas (Brian Schottenheimer, c07): a new head texture (a grey, salt-and-pepper beard instead of the dark smudge);
* Cincinnati, Carolina, Green Bay, Tennessee, the Rams, San Francisco, Minnesota (c06, c09, c10, c15, c23, c25, c28):
  a lean body taken from a leaner retail coach of the same mesh family, and a new head texture.

Everything else on the disc is left as it is. The input must be the v0.6.1 shortcut disc, or co3's output of it (the two
Coach Matchup pictures already replaced); any other hash is refused. Those nine scenes must read ``previous`` (the
co2 coaches the v0.6.1 disc carries) and every other coach part ``applied``. The scenes are compiled from the user's
retail image (``--retail``), exactly as a Studio build compiles them.

Receipts (in --receipts):
  disc_write.json            every written span: before/after SHA-256, absolute image ranges, changed bytes, geometry
  disc_replay.json           a second plan writes nothing to these spans
  disc_scope.json            a full byte compare against --original (read only): every changed byte inside the owned
                             ranges
  disc_studio_equality.json  every coach scene on the disc equals the Studio module's compile from --retail and its pin

  python3 tools/b77/cm1_repair.py --image COPY.iso --original ORIGINAL.iso --retail RETAIL.iso --receipts DIR
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

INPUTS = {
    "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4": "SOFTDRINK 2K28 v0.6.1 fixes",
    "d60ea6dd42fac32fa2ffb52a83ccf97d1fa555965b8517a0a2ddd40ab251c3cf": "v0.6.1 + co3 (Coach Matchup pictures)",
}
INPUT_SIZE = 6_004_408_320
OWNED = ("WAS", "DAL", "CIN", "CAR", "GB", "TEN", "LAR", "SF", "MIN")
BLOCK = 1 << 23


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb", buffering=0) as f:
        for block in iter(lambda: f.read(BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def refuse(message: str) -> None:
    raise SystemExit(f"cm1_repair: REFUSED: {message}")


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
    """Every coach scene on the disc against the Studio module's compile from the retail image (and its pin)."""
    eq = []
    with mc._outer_image()(retail) as r_arc, mc._outer_image()(image) as o_arc:
        entries_r = {e.name_id: e for e in r_arc.entries}
        entries_o = {e.name_id: e for e in o_arc.entries}
        for row in mc.pins()["teams"]:
            er, eo = entries_r[mc.name_id(row["archive"])], entries_o[mc.name_id(row["archive"])]
            studio, detail = mc.compile_archive(r_arc.read(er.virtual_offset, er.size), row)
            span_s = studio[row["span_offset"]:row["span_offset"] + row["span_size"]]
            span_o = o_arc.read(eo.virtual_offset + row["span_offset"], row["span_size"])
            eq.append(dict(part=f"coach:{row['team']}", owned_by_cm1=row["team"] in OWNED, archive=row["archive"],
                           geometry=detail["textures"].get("geometry"),
                           studio_sha256=mc.sha(span_s), disc_sha256=mc.sha(span_o), pin=row["applied_sha256"],
                           equal=span_s == span_o and mc.sha(span_o) == row["applied_sha256"]))
    return eq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=Path, required=True, help="this job's copy of the input disc (written in place)")
    ap.add_argument("--original", type=Path, required=True, help="the untouched input disc, read only")
    ap.add_argument("--retail", type=Path, required=True, help="the retail USA image, read only")
    ap.add_argument("--receipts", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.image.resolve() == a.original.resolve():
        refuse("--image must be a copy, not the original")
    a.receipts.mkdir(parents=True, exist_ok=True)
    original_sha = file_sha(a.original)
    if original_sha not in INPUTS or a.original.stat().st_size != INPUT_SIZE:
        refuse(f"--original is {original_sha}, not a supported input ({', '.join(INPUTS)})")
    image_sha = file_sha(a.image)
    states = mc.resource_states(a.image)
    owned_keys = {f"coach:{t}" for t in OWNED}
    others = {k: v for k, v in states.items() if k not in owned_keys and not k.startswith("portrait:")}
    if any(v != "applied" for v in others.values()):
        refuse("a coach part this repair does not own is not applied: "
               + ", ".join(f"{k}={v}" for k, v in others.items() if v != "applied"))
    owned_states = {k: states[k] for k in sorted(owned_keys)}
    if image_sha == original_sha:
        if set(owned_states.values()) != {"previous"}:
            refuse(f"the input's nine coach scenes read {owned_states}, expected the v0.6.1 coaches (previous)")
    elif set(owned_states.values()) != {"applied"}:
        refuse(f"--image is {image_sha}: neither the input disc nor a disc carrying this repair")
    plan, rows = mc.plan_image(a.image, retail=a.retail)
    keep = [i for i, r in enumerate(rows) if r.get("written") and r["kind"] == "coach" and r["team"] in OWNED]
    others_planned = [(r["kind"], r["team"]) for i, r in enumerate(rows) if r.get("written") and i not in keep]
    plan_rows = [r for r in rows if r.get("written")]
    owned_plan = [p for p, r in zip(plan, plan_rows) if r["kind"] == "coach" and r["team"] in OWNED]
    owned_rows = [rows[i] for i in keep]
    if image_sha == original_sha and sorted(r["team"] for r in owned_rows) != sorted(OWNED):
        refuse(f"the plan is not exactly the nine coach scenes: {[r['team'] for r in owned_rows]}")
    ranges = owned_ranges(a.image, owned_rows)
    with mc._outer_image()(a.image, writable=True) as archive:
        mc._write_all(archive, owned_plan)                   # checks each span against its preflight, reads back
    after = mc.resource_states(a.image)
    if any(after[k] != "applied" for k in owned_keys):
        refuse(f"read-back: {[(k, after[k]) for k in owned_keys if after[k] != 'applied']}")
    for r in owned_rows:
        r["image_ranges"] = [[s, e] for s, e, label in ranges if label == f"{r['kind']}:{r['team']}"]
    output_sha = file_sha(a.image)
    write_json(a.receipts / "disc_write.json", dict(
        schema="b77_cm1_disc_write/v1", image=str(a.image), input_sha256=image_sha, input=INPUTS.get(image_sha),
        output_sha256=output_sha, owned_states_before=owned_states, written=len(owned_plan),
        not_written_not_owned=others_planned, changed_bytes=sum(r["changed_bytes"] for r in owned_rows),
        parts=[dict({k: v for k, v in r.items() if k not in ("row",)}) for r in owned_rows]))
    replay_plan, replay_rows = mc.plan_image(a.image, retail=a.retail)
    replay_owned = [r for r in replay_rows if r.get("written") and r["kind"] == "coach" and r["team"] in OWNED]
    write_json(a.receipts / "disc_replay.json", dict(
        schema="b77_cm1_disc_replay/v1", planned_writes_owned=len(replay_owned), written_bytes=0,
        owned_states=sorted({r["state_before"] for r in replay_rows if r["kind"] == "coach" and r["team"] in OWNED})))
    if replay_owned:
        refuse("the replay planned writes to the owned spans: not idempotent")
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
        schema="b77_cm1_disc_scope/v1", original=str(a.original), original_sha256=original_sha,
        output_sha256=output_sha, compared_bytes=INPUT_SIZE, changed_runs=len(runs), changed_bytes=changed,
        owned_ranges=[[s, e, label] for s, e, label in ranges], owned_bytes=sum(e - s for s, e, _l in ranges),
        changed_outside_owned=len(outside), first_outside=outside[:10]))
    if outside:
        refuse(f"{len(outside)} changed bytes outside the owned ranges")
    eq = studio_equality(a.image, a.retail)
    write_json(a.receipts / "disc_studio_equality.json", dict(
        schema="b77_cm1_disc_studio_equality/v1", retail=str(a.retail), parts=eq,
        owned_parts=sum(1 for r in eq if r["owned_by_cm1"]), all_equal=all(r["equal"] for r in eq)))
    if not all(r["equal"] for r in eq):
        refuse("a coach scene on the disc differs from the Studio compile")
    with open(a.image.with_name(a.image.name + ".sha256"), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{output_sha}  {a.image.name}\n")
    print(f"APPLIED {len(owned_plan)} writes, {sum(r['changed_bytes'] for r in owned_rows)} changed bytes; replay 0 writes")
    print(f"SCOPE {len(runs)} runs, {changed} bytes changed against the original, {len(outside)} outside "
          f"{len(ranges)} owned ranges")
    print(f"STUDIO {sum(1 for r in eq if r['equal'])}/{len(eq)} coach scenes equal the Studio compile from retail "
          f"({sum(1 for r in eq if r['owned_by_cm1'])} owned by cm1)")
    print(f"OUTPUT {a.image} {output_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
