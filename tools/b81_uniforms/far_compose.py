#!/usr/bin/env python3
"""b81-uniforms R54, small retail-free form: the far-player atlas pants and sleeves follow the 2026 uniform pass.

Bench and far-away players are drawn from each kit package's chunk 51 ``splayer`` atlas. The 2026 uniform pass corrected
the full-size pants and sleeve textures of many kits and left the atlas alone. This tool writes
``data/nfl2k5_sideline_2026_b81u.json``: RULE rows of the shipped sideline mechanism (schema nfl2k5_sideline_2026/v1,
``compose``), one per kit whose pants or sleeve texture the pass changed. At build time the step ``sideline_2026_b81u``
(after the uniform pass) composes each listed piece from the kit's own finished field texture, lit by the island's own
folds (``_sideline_compose``), exactly as the shipped ``sideline_2026`` step does. The document holds no picture and
no atlas texel: per kit the parts, the field colours (the finished texture's fabric colour, the shipped guard), the
pants crop the island shows (integers), and SHA-256 pins: the atlas the build holds there (before), the finished field
textures read (field), and the atlas the step writes (after). A kit whose atlas, field texture or result differs is left
alone.

  python3 tools/b81_uniforms/far_compose.py build --released V09.iso --built BUILT.iso --out data/nfl2k5_sideline_2026_b81u.json
                                                  [--receipt R.json] [--decoded DIR] [--only SEL ...]

``--released`` is the released v0.9 disc (the uniform pass rows are pinned to its textures), ``--built`` a Studio build of
this branch's base (its atlases are what the step finds; its field textures are replaced in memory by the pass's
finished ones). Authoring tool: nothing here ships but the document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

SCHEMA = "nfl2k5_sideline_2026/v1"
NOTE = ("b81-uniforms R54 (beta 81): the far-player atlas pants and sleeves of every kit whose pants or sleeve texture the "
        "2026 uniform pass changed, composed at build time from the kit's own finished field texture by the sideline "
        "step's compose (rules and pins only; no atlas texel is stored)")
PARTS = {"pants": (2, "pants00"), "sleeve": (3, "sleeve00")}
#: the retail far-player pictures show the LEFT leg of the pants texture (measured by registration on every kit:
#: atlas_x = 0.467 x - 10.8, atlas_y = 0.390 y + 0.3, uniforms/work/R2/helper_s1/ATLAS_SURVEY.md and R2-F); islands the
#: sideline step composed keep its own crop (SIDELINE_COMPOSE, the right half)
RETAIL_PANTS_CROP = [23, 0, 297, 230]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def modules():
    import b81_uniform_pass as up
    from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
    return kf, up


def span_of(raw: bytes, index: int) -> bytes:
    kf, _ = modules()
    chunk = kf._chunk_for(raw, index)
    return raw[chunk.offset:chunk.end_offset]


def finished(released: bytes, selector: str) -> bytes:
    """The released package after the 2026 uniform pass (its rows are pinned to the released textures)."""
    kf, _ = modules()
    document = kf.uniforms_b81()
    if not any(r["selector"] == selector for r in document["textures"]):
        return released
    replacements, _ = kf.compile_resource(selector, released, strict=False, document=document)
    out = bytearray(released)
    for offset, data in replacements:
        out[offset:offset + len(data)] = data
    return bytes(out)


def build_state(released: bytes, built: bytes, selector: str) -> bytes:
    """The package as the step finds it in a build of this branch: the built package (its atlas after the earlier
    sideline step and the helmet cleanup) with the uniform pass's finished field textures (chunks 1-4)."""
    kf, _ = modules()
    fin = finished(released, selector)
    kf.require(len(fin) == len(built), selector + ": package size differs")
    out = bytearray(built)
    for index in (1, 2, 3, 4):
        c = kf._chunk_for(fin, index)
        b = kf._chunk_for(built, index)
        kf.require((c.offset, c.end_offset) == (b.offset, b.end_offset), selector + ": allocation moved")
        out[c.offset:c.end_offset] = fin[c.offset:c.end_offset]
    return bytes(out)


def plan(row: dict, raw: bytes):
    """(new splayer span or None, receipt): the shipped measured sideline path on one package, in memory."""
    kf, _ = modules()
    from mod_editor.core.nfl2k5_kit_fixes_2026 import parse_chunks
    chunks = {c.index: c for c in parse_chunks(raw)}
    splayer = raw[chunks[51].offset:chunks[51].end_offset]
    alt = kf._sideline_rgba(splayer, "txtr", "splayer")
    entry, replacements, receipt = kf._sideline_measured_plan(row, None, raw, chunks, splayer, alt, None)
    return (replacements[0][1] if replacements else None), receipt, splayer


def cmd_build(args) -> int:
    kf, up = modules()
    rows_b81u = kf.uniforms_b81()["textures"]
    changed = {}
    for r in rows_b81u:
        for part, (index, name) in PARTS.items():
            if r["chunk"] == index:
                changed.setdefault(r["selector"], set()).add(part)
    selectors = sorted(changed)
    if args.only:
        selectors = [s for s in selectors if s in set(args.only)]
    released = up.read_kits(Path(args.released), selectors)
    built = up.read_kits(Path(args.built), selectors)
    composed = {row["selector"]: set((row.get("compose") or {})) for row in kf.sideline()["kits"]}
    rows, receipt = [], {}
    decoded = Path(args.decoded) if args.decoded else None
    if decoded:
        decoded.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    for selector in selectors:
        raw = build_state(released[selector], built[selector], selector)
        parts = [p for p in ("pants", "sleeve") if p in changed[selector]]
        textures = kf._sideline_field_textures(raw, {c.index: c for c in kf.parse_chunks(raw)}, selector, parts)
        field = {p: [int(v) for v in kf._sideline_field_mode(textures[p], p)] for p in parts}
        compose = {}
        for p in parts:
            op = {}
            if p == "pants" and "pants" not in composed.get(selector, set()):
                op["crop"] = list(RETAIL_PANTS_CROP)
            compose[p] = op
        row = dict(selector=selector, parts=parts, field=field, compose=compose,
                   field_sha256={p: sha(span_of(raw, PARTS[p][0])) for p in parts})
        try:
            new, rec, splayer = plan(row, raw)
        except Exception as exc:  # noqa: BLE001 - named in the receipt; the other kits are still written
            receipt[selector] = dict(state="failed", error=str(exc)[:300])
            print("FAILED", selector, str(exc)[:200], flush=True)
            continue
        if new is None:
            receipt[selector] = dict(state=rec.get("state"), receipt=rec)
            print("NO CHANGE", selector, rec.get("state"), flush=True)
            continue
        row["before_sha256"] = sha(splayer)
        row["after_sha256"] = sha(new)
        rows.append(row)
        receipt[selector] = dict(state="row", parts=parts, crop=compose.get("pants", {}).get("crop"),
                                 changed_texels=rec.get("changed_texels"), fit=rec.get("fit"))
        if decoded:
            Image.fromarray(kf._sideline_rgba(splayer, "txtr", "splayer"), "RGBA").save(decoded / f"{selector}_splayer_before.png")
            Image.fromarray(kf._sideline_rgba(new, "txtr", "splayer"), "RGBA").save(decoded / f"{selector}_splayer.png")
        print(selector, parts, rec.get("changed_texels"), flush=True)
    rows.sort(key=lambda r: r["selector"])
    document = dict(schema=SCHEMA, note=NOTE, kits=rows)
    Path(args.out).write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=1, sort_keys=True, default=str) + "\n",
                                      encoding="utf-8", newline="\n")
    failed = sum(1 for e in receipt.values() if e["state"] == "failed")
    print(json.dumps(dict(rows=len(rows), failed=failed, kits=len(selectors))))
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build")
    build.add_argument("--released", required=True)
    build.add_argument("--built", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--receipt")
    build.add_argument("--decoded")
    build.add_argument("--only", nargs="+")
    return cmd_build(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
