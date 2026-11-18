#!/usr/bin/env python3
"""b81-art: the finished in-game helmets of a SOFTDRINK build, cleaned (Noah 2026-11-18: "clean up team helmets and
play now visuals when choosing teams bc rn teams like the ravens and others show the old logo peaking through outside
of the new logo placed on top", and "Helmets also have duplicate holes/spots for the modernized design").

What the art carried (measured on the released v0.9 disc, whose kit art and art passes the v0.10 builds share):

* every Revolution-shell texture (``helmet02``, the shell every 2026 player wears, drawn with the modern shell's own
  vents as geometry) still had the 2004 shell's vents painted on it: four crown crescents and two rear slits, each a
  soft twin beside a modern vent;
* the place of the 2004 flag on the back of that shell kept a dotted outline (and on a few shells the wrong colour);
* pieces of the 2004 logo stayed beside the 2026 logo on both shells (outline tips, small separate pieces, smears).

``build`` (authoring, needs the disc and the cleaned level-0 PNGs made by the tools in ``tools/b81_art``) writes
``data/nfl2k5_kit_fixes_2026_b81.json``: one row per texture in the Studio's own kit-fix format, pinned to the
finished span, whose ``runs`` repaint only the cleaned texels with colours the texture's palette already holds at
each texel's alpha. ``check`` reads a disc image and says how many rows are waiting, done or not this art.

  python3 tools/b81_helmet_cleanup.py build --image DISC.iso --cleaned DIR --out data/nfl2k5_kit_fixes_2026_b81.json
  python3 tools/b81_helmet_cleanup.py check --image DISC.iso
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

CHUNKS = {"helmet00": 11, "helmet02": 12}
SOURCE = ("b81-art (beta 81): the finished in-game helmets of the SOFTDRINK 2026 kits, measured on the released v0.9 "
          "disc: the 2004 Revolution vents painted beside the modern shell's vents, the 2004 flag's outline on the "
          "back of the shell, and 2004 logo pieces left beside the 2026 logo")
METHOD = ("each texture's cleaned texels are stored as runs of colours taken from the texture's own palette at each "
          "texel's alpha (shell rebuilt from the shading around the piece; a patterned shell continues its nearest "
          "colours); nothing else changes")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kit_modules():
    from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
    return kf, kf.bump


def read_kits(image: Path, selectors) -> dict:
    """{selector: kit package bytes} from a disc image (read only)."""
    kf, bump = kit_modules()
    out = {}
    with bump._Image.open(Path(image), writable=False) as source:
        index = bump._parsed_index(source)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        for selector in selectors:
            entries = by_name.get(selector + ".IFF", [])
            if len(entries) != 1:
                continue
            out[selector] = source.read_segments(index.sub_extents(entries[0], 0, entries[0].size))
    return out


def level0(span: bytes):
    """(RGBA level 0, palette, alpha per texel, mip count) of a P8 helmet chunk span."""
    kf, _ = kit_modules()
    chunk, decoded, textures = kf.native_textures(span, "txtr")
    planes = kf.read_planes(decoded, chunk, textures[0])
    palette = kf.read_palette(decoded, chunk, textures[0])
    return palette[planes[0]].astype(np.uint8), palette, textures[0]


def snap(colours: np.ndarray, alphas: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Each wanted colour as the palette's nearest entry of the texel's own alpha (the compiler's own rule)."""
    kf, _ = kit_modules()
    index = kf.nearest(colours.astype(np.int64), alphas.astype(np.int64), palette.astype(np.int64))
    return palette[index][:, :3].astype(np.uint8)


def runs_of(before: np.ndarray, after: np.ndarray) -> list:
    """[[y, x0, "RRGGBB..."], ...]: every horizontal run of texels whose colour changed."""
    changed = (before[..., :3] != after[..., :3]).any(axis=2)
    rows = []
    for y in np.flatnonzero(changed.any(axis=1)):
        xs = np.flatnonzero(changed[y])
        starts = np.concatenate(([xs[0]], xs[1:][np.diff(xs) > 1]))
        ends = np.concatenate((xs[:-1][np.diff(xs) > 1], [xs[-1]]))
        for x0, x1 in zip(starts, ends):
            rows.append([int(y), int(x0), after[y, x0:x1 + 1, :3].tobytes().hex().upper()])
    return rows


def build_row(selector: str, family: str, raw: bytes, cleaned_rgba: np.ndarray, note: str, defects: list):
    """One document row and the texture it produces, or None when the cleaned texture changes nothing."""
    kf, _ = kit_modules()
    chunk = kf._chunk_for(raw, CHUNKS[family])
    span = raw[chunk.offset:chunk.end_offset]
    before, palette, texture = level0(span)
    if cleaned_rgba.shape != before.shape:
        raise ValueError(f"{selector} {family}: the cleaned texture is not {before.shape[1]}x{before.shape[0]}")
    wanted = before.copy()
    changed = (cleaned_rgba[..., :3] != before[..., :3]).any(axis=2)
    if not changed.any():
        return None, before
    wanted[changed, :3] = snap(cleaned_rgba[changed][:, :3], before[changed][:, 3], palette)
    rows = runs_of(before, wanted)
    if not rows:
        return None, before
    row = dict(selector=selector, chunk=CHUNKS[family], texture=family, kind="txtr",
               size=[int(texture["width"]), int(texture["height"]), int(texture["mips"])],
               resource_size=len(raw), offset=int(chunk.offset), length=len(span), before_sha256=sha(span),
               defects=defects, note=note, ops=[dict(op="runs", rows=rows)])
    try:
        new, detail = kf.compile_texture(span, row)
    except Exception as exc:  # noqa: BLE001 - the fixed allocation is tight: keep the mip parents' indices crisp
        if "scratch word" not in str(exc) and "does not fit" not in str(exc) and "fit" not in str(exc).lower():
            raise
        row["mip"] = "mode"
        new, detail = kf.compile_texture(span, row)
    after, _palette, _texture = level0(new)
    if not np.array_equal(after, wanted):
        raise ValueError(f"{selector} {family}: the compiled texture differs from the cleaned one")
    if detail["palette_slots_added"] or detail["merged_twin_slots"]:
        raise ValueError(f"{selector} {family}: the palette changed")
    row["after_sha256"] = sha(new)
    row["texels"] = int((after[..., :3] != before[..., :3]).any(axis=2).sum())
    return row, after


def imported(raw: bytes, selector: str, family: str, png: Path, retail_index: Path) -> bytes:
    """The kit package as a build holds it after the league project gives this slot new helmet art: the Studio's own
    importer (same PNG, same slot) writes the span, everything else in the package stays."""
    import nfl_live_helmet_txtr_png_import as importer
    import nfl_live_helmet_txtr_targets as targets
    kf, _ = kit_modules()
    span, _extra, _report = importer.build_import(Path(retail_index), targets.DEFAULT_REPORT, selector[:2], selector[2],
                                                  int(selector[3:]), family, Path(png))
    chunk = kf._chunk_for(raw, CHUNKS[family])
    if len(span) != chunk.end_offset - chunk.offset:
        raise ValueError(f"{selector} {family}: the imported span is not the slot's size")
    return raw[:chunk.offset] + span + raw[chunk.end_offset:]


def cmd_build(args) -> int:
    from PIL import Image
    cleaned = Path(args.cleaned)
    stats = json.loads(Path(args.stats).read_text(encoding="utf-8")) if args.stats else {}
    names = sorted(p.stem for p in cleaned.glob("helmet0?_*.png"))
    skip = set(args.skip or [])
    selectors = sorted({n.split("_")[1] for n in names} - skip)
    kits = read_kits(Path(args.image), selectors)
    new_art = json.loads(Path(args.new_art).read_text(encoding="utf-8")) if args.new_art else {}
    for selector, families in sorted(new_art.items()):
        for family, png in sorted(families.items()):
            kits[selector] = imported(kits[selector], selector, family, Path(png), Path(args.retail_index))
    rows, receipt = [], {}
    for name in names:
        family, selector = name.split("_")
        if selector in skip or selector not in kits:
            continue
        with Image.open(cleaned / f"{name}.png") as image:
            rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        st = stats.get(name, {})
        defects = [k for k, label in (("vents", "painted 2004 vents"), ("diamond", "2004 flag outline"),
                                      ("old", "2004 logo pieces")) if st.get(k)]
        note = "; ".join(f"{st[k]} texels of {label}" for k, label in
                         (("vents", "the painted 2004 Revolution vents"), ("diamond", "the 2004 flag's outline"),
                          ("old", "2004 logo ink beside the 2026 logo")) if st.get(k)) or "cleaned texels"
        try:
            row, after = build_row(selector, family, kits[selector], rgba, note, defects)
        except Exception as exc:  # noqa: BLE001 - named in the receipt, the other rows are still written
            receipt[name] = dict(error=str(exc)[:300])
            print("FAILED", name, str(exc)[:160], flush=True)
            continue
        if row is None:
            continue
        rows.append(row)
        receipt[name] = dict(texels=row["texels"], before_sha256=row["before_sha256"], after_sha256=row["after_sha256"],
                             after_rgba_sha256=sha(np.ascontiguousarray(after).tobytes()))
        if args.decoded:
            Path(args.decoded).mkdir(parents=True, exist_ok=True)
            Image.fromarray(after, "RGBA").save(Path(args.decoded) / f"{name}.png")
    rows.sort(key=lambda r: (r["selector"], r["chunk"]))
    document = dict(schema="nfl2k5_kit_fixes_2026/v1", source=SOURCE, method=METHOD, textures=rows)
    Path(args.out).write_text(json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8",
                              newline="\n")
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(rows=len(rows), texels=sum(r["texels"] for r in rows),
                          selectors=len({r["selector"] for r in rows}))))
    return 0


def states(image: Path, document=None) -> dict:
    """{"before": n, "after": n, "other": n, "absent": n, "rows": [...]} of the document's rows on a disc image."""
    kf, _ = kit_modules()
    document = document or kf.helmets_b81()
    kits = read_kits(Path(image), sorted({r["selector"] for r in document["textures"]}))
    out = dict(before=0, after=0, other=0, absent=0, rows=[])
    for row in document["textures"]:
        raw = kits.get(row["selector"])
        if raw is None:
            state = "absent"
        else:
            chunk = kf._chunk_for(raw, row["chunk"])
            span = raw[chunk.offset:chunk.end_offset]
            ok = (len(raw), chunk.offset, len(span)) == (row["resource_size"], row["offset"], row["length"])
            digest = sha(span) if ok else None
            state = "before" if digest == row["before_sha256"] else "after" if digest == row["after_sha256"] else "other"
        out[state] += 1
        if state not in ("before", "after"):
            out["rows"].append(dict(selector=row["selector"], texture=row["texture"], state=state))
    return out


def cmd_check(args) -> int:
    result = states(Path(args.image))
    print(json.dumps(result, indent=1))
    return 0 if not result["other"] and not result["absent"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 tools/b81_helmet_cleanup.py")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write the kit-fix document from a disc image and the cleaned textures")
    b.add_argument("--image", required=True)
    b.add_argument("--cleaned", required=True, help="folder of cleaned level-0 PNGs named helmet0N_<selector>.png")
    b.add_argument("--stats", help="helmet_stats.json of the cleanup (texel counts per class, for the notes)")
    b.add_argument("--skip", nargs="*", help="selectors left to the league project's own art")
    b.add_argument("--new-art", help="JSON {selector: {family: png}}: slots whose league project art changes with "
                   "this job; their rows are pinned to what the Studio's importer makes of that PNG")
    b.add_argument("--retail-index", help="the retail vc_53450030/0 (needed with --new-art)")
    b.add_argument("--out", required=True)
    b.add_argument("--receipt")
    b.add_argument("--decoded", help="folder for the compiled level-0 PNGs (what the game will hold)")
    c = sub.add_parser("check", help="how many rows of the document a disc image is waiting for, has, or does not match")
    c.add_argument("--image", required=True)
    args = parser.parse_args(argv)
    return cmd_build(args) if args.command == "build" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
