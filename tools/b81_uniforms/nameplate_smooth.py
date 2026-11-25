#!/usr/bin/env python3
"""b81-nameplates: give every beta 81 nameplate strip smooth (coverage) edges.

Owner, 2026-11-25, on the Colts road kit of the 11/20 private disc: "suprised to see that the last name font is
pixelated and not good (the shoulder stripes and everything else looks good tho) not accurate nameplate font".

Cause: the beta 81 nameplate strips (``names_png`` pictures and the Jaguars ``names_derived`` strips) were drawn with
every texel fully on or off (alpha 0 or 255). The game copies the letters 1:1 into the plate and magnifies it on the
jersey, so every texel step shows. The released v0.9 strips carry 117 to 227 alpha levels on their edges.

This tool keeps each approved letter (its silhouette, its glyph cell, its colour) and runs the Studio's own
``smooth_letters`` operation on it (``nfl2k5_glyph_fixes_2026.smooth_letters``: 8 x 8 subtexels, integer box filters,
a threshold that keeps or sets the stroke weight, exact coverage as alpha):

* a ``names_png`` row gets the smoothed picture (same file name) and new pins; its ``name_widths`` row gets the widths
  of the smoothed letters (ink plus one clear column, as before) and new pins;
* a ``names_derived`` row (the Jaguars road strips, built from the user's own disc) gets ``smooth_letters`` appended to
  its operations, so still no picture ships; its widths follow the same rule;
* a strip that already has soft edges (the Browns road strips: v0.9's letters recoloured) is left alone.

``--level SEL=N`` sets the threshold (N/64 of full weight) for the strips of that kit; 32 keeps the drawn weight.
Every pin is computed on the released v0.9 disc's kits as a build holds them at this step (after the nameplate pass,
whose Jaguars letters come from the retail disc), through the Studio's compile route.

  python3 tools/b81_uniforms/nameplate_smooth.py --image V09.iso --retail RETAIL.iso [--level 11A0=25 ...] [--apply]
          [--preview DIR]

Authoring tool: it needs the user's own released and retail discs. Nothing here ships except the document and art.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from mod_editor.core import nfl2k5_glyph_fixes_2026 as gf  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402
import b81_uniform_pass as up  # noqa: E402

SMOOTH = dict(op="smooth_letters", box=11, passes=3, den=64)
DEFAULT_LEVEL = 32
DEFECT = "b81n-nameplate-hard-edges"
NOTE = ("b81-nameplates (owner 11/25: the Colts last name font \"pixelated and not good ... not accurate\"): the letters "
        "keep this design and get smooth coverage edges (smooth_letters: 8x8 subtexels, three {box}-subtexel box passes, "
        "cut at {level}/64){weight}; widths = ink plus one clear column")
WEIGHT = {32: ""}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def letter_colours(rgba):
    """(fill, outline or None) of a hard-edged strip: one colour, or a fill with an edge colour that the clear texels
    also carry (the strip convention: a filtered edge never fades through black)."""
    opaque = rgba[rgba[..., 3] == 255][:, :3]
    colours, counts = np.unique(opaque, axis=0, return_counts=True)
    hexes = ["#%02X%02X%02X" % tuple(int(v) for v in c) for c in colours]
    if len(hexes) == 1:
        return hexes[0], None
    if len(hexes) != 2:
        raise ValueError("a nameplate strip with %d letter colours" % len(hexes))
    clear = np.unique(rgba[rgba[..., 3] == 0][:, :3], axis=0)
    if len(clear) != 1:
        raise ValueError("a two-colour strip whose clear texels carry several colours")
    edge = "#%02X%02X%02X" % tuple(int(v) for v in clear[0])
    if edge not in hexes:
        raise ValueError("a two-colour strip whose clear texels carry neither letter colour")
    return [h for h in hexes if h != edge][0], edge


def smooth_widths(rgba, offsets):
    """Each glyph's advance: its last column with any coverage, plus one clear column (the compositor adds one more)."""
    ink = rgba[..., 3] > 0
    out = []
    for x0 in offsets:
        cols = np.flatnonzero(ink[:, x0:x0 + 32].any(0))
        out.append(min(32, int(cols[-1]) + 2) if len(cols) else 1)
    return out


BOXES = (11, 9, 7, 5)


def counters(mask):
    """The clear regions of a glyph cell that touch no border (its counters), as lists of (row, column)."""
    h, w = mask.shape
    seen = mask.copy()
    out = []
    for y0 in range(h):
        for x0 in range(w):
            if seen[y0, x0]:
                continue
            stack, points, edge = [(y0, x0)], [], False
            seen[y0, x0] = True
            while stack:
                y, x = stack.pop()
                points.append((y, x))
                edge |= y in (0, h - 1) or x in (0, w - 1)
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if not edge:
                out.append(points)
    return out


OPEN = 0.5          # a counter stays open: its texels keep at least half their clear area on average


def keeps_counters(before, after, offsets):
    """Every counter of the drawn letters keeps at least OPEN of its clear area after smoothing (a 2-texel serif A
    counter takes some coverage from any smoothing; a closed one reads as a blob)."""
    for x0 in offsets:
        for points in counters(before[:, x0:x0 + 32, 3] > 0):
            clear = sum(255 - int(after[y, x0 + x, 3]) for y, x in points) / (255.0 * len(points))
            if clear < OPEN:
                return False
    return True


def smooth_op(offsets, fill, outline, level, box=SMOOTH["box"]):
    op = dict(SMOOTH, offsets=[int(x) for x in offsets], fill=fill, level=int(level), box=int(box))
    if outline:
        op["outline"] = outline
        op["blend_steps"] = 8
    return op


def plan(document, kits, levels):
    """{selector: (strip row, widths row or None, new strip RGBA, op, widths)} for every hard-edged strip."""
    rows = {}
    for row in document["textures"]:
        rows.setdefault(row["selector"], {})[row["kind"]] = row
    out = {}
    for selector, kinds in sorted(rows.items()):
        strip_row = kinds.get("names_png") or kinds.get("names_derived")
        if strip_row is None:
            continue
        raw = kits[selector]
        span = raw[gf._chunk_for(raw, gf.NAMES_CHUNK).offset:gf._chunk_for(raw, gf.NAMES_CHUNK).end_offset]
        name = gf._chunk_for(raw, gf.NAME_CHUNK)
        offsets = [x for x, _w in gf.name_widths(raw[name.offset:name.end_offset])]
        if strip_row["kind"] == "names_png":
            current = gf.names_png_rgba((gf.art_folder(document) / strip_row["png"]).read_bytes())
            ops = None
        else:
            ops = [op for op in strip_row["derive"] if op["op"] != "smooth_letters"]
            current = gf.derive_digit(gf.names_level0(span), ops)
        if len(np.unique(current[..., 3])) > 2:
            continue                                        # already soft-edged (the Browns road recolour)
        fill, outline = letter_colours(current)
        for box in BOXES:                   # the widest smoothing that keeps every counter open (a serif A's is tiny)
            op = smooth_op(offsets, fill, outline, levels.get(selector, DEFAULT_LEVEL), box)
            new = gf.smooth_letters(current, op)
            if keeps_counters(current, new, offsets):
                break
        else:
            raise ValueError(selector + ": no smoothing keeps every counter open")
        out[selector] = (strip_row, kinds.get("name_widths"), new, op, smooth_widths(new, offsets), ops, span,
                         raw[name.offset:name.end_offset])
    return out


def apply(document, planned, *, write_art):
    folder = gf.art_folder(document)
    payloads = {}
    for selector, (strip_row, widths_row, new, op, widths, ops, span, name_span) in planned.items():
        level = op["level"]
        note = NOTE.format(level=level, box=op["box"], weight="" if level == DEFAULT_LEVEL else
                           ", strokes set to the measured real weight (stem/cap 0.14, about 3.4 of the 24 cap rows)")
        if strip_row["kind"] == "names_png":
            payload = up.names_png_bytes(new)
            payloads[strip_row["png"]] = payloads.get(strip_row["png"], payload)
            if payloads[strip_row["png"]] != payload:
                raise ValueError(selector + ": kits that share a strip picture must share its smoothing")
            fixed, _detail = gf.compile_names_png(span, payload)
            strip_row["png_sha256"] = sha(payload)
        else:
            strip_row["derive"] = ops + [op]
            strip_row["rgba_sha256"] = sha(np.ascontiguousarray(new).tobytes())
            fixed, _detail = gf.compile_derived_names(span, strip_row)
        if not (gf.names_level0(fixed) == new).all():
            raise ValueError(selector + ": the compiled strip differs from the smoothed one")
        strip_row["after_sha256"] = sha(fixed)
        new_name = name_span
        if widths_row is not None:
            new_name, _ = gf.compile_name_widths(name_span, widths)
            widths_row["widths"] = widths
            widths_row["after_sha256"] = sha(new_name)
        if not kf.layout_fits(kf.atlas_glyph_starts(fixed), kf.name_metrics(new_name)):
            raise ValueError(selector + ": the smoothed glyphs do not start at the NAME offsets")
        for row in (strip_row, widths_row):
            if row is None:
                continue
            if DEFECT not in row["defects"]:
                row["defects"] = list(row["defects"]) + [DEFECT]
            if "b81-nameplates" not in row["note"]:
                # shipped text names no one (b81 rule): a note that opens with a person's name and a date opens with
                # "Owner" and the date
                row["note"] = re.sub(r"^[A-Z][a-z]+ (\d{1,2}/\d{1,2}) ", r"Owner \1 ", row["note"]) + "; " + note
    if write_art:
        for png, payload in payloads.items():
            (folder / png).write_bytes(payload)
    return payloads


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--image", required=True, help="the released v0.9 disc (the rows' before pins)")
    parser.add_argument("--retail", required=True, help="the retail disc (the nameplate pass's Jaguars letters)")
    parser.add_argument("--level", action="append", default=[], help="SEL=N: threshold N/64 for that kit's strip")
    parser.add_argument("--apply", action="store_true", help="write the document and the art (default: dry run)")
    parser.add_argument("--preview", help="write each smoothed strip and its widths here")
    args = parser.parse_args(argv)
    levels = {k: int(v) for k, v in (item.split("=", 1) for item in args.level)}
    path = gf.DATA_B81U
    document = json.loads(path.read_text(encoding="utf-8"))
    selectors = sorted({r["selector"] for r in document["textures"] if r["kind"] in ("names_png", "names_derived")})
    retail = up.retail_kits_for_nameplates(args.retail)
    kits = {s: up.after_nameplate_pass(s, raw, retail) for s, raw in up.read_kits(Path(args.image), selectors).items()}
    planned = plan(document, kits, levels)
    if args.preview:
        from PIL import Image
        out = Path(args.preview)
        out.mkdir(parents=True, exist_ok=True)
        for selector, item in planned.items():
            Image.fromarray(item[2], "RGBA").save(out / f"{selector}_names.png")
            (out / f"{selector}_widths.json").write_text(json.dumps(item[4]))
    payloads = apply(document, planned, write_art=args.apply)
    for selector, item in planned.items():
        print(selector, item[0]["kind"], "level", item[3]["level"], "box", item[3]["box"], "alpha levels", len(np.unique(item[2][..., 3])),
              "widths", item[4])
    if args.apply:
        path.write_text(up.shipped_json(document, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
        gf.spec(path)
    print(json.dumps(dict(strips=len(planned), pictures=len(payloads), applied=bool(args.apply))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
