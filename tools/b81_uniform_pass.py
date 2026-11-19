#!/usr/bin/env python3
"""b81-uniforms: the 2026 uniform pass (Noah 2026-11-18: "some uniforms need work to look better and closer to irl ...
goal is to match irl as close as possible").

Each kit texture that the pass corrects (jersey, pants, sleeve, socks, the number digits) is authored as a finished
level-0 picture against this season's game-highlight frames, starting from the texture a SOFTDRINK build already
holds. This tool turns those pictures into ``data/nfl2k5_kit_fixes_2026_b81u.json``: one row per texture in the
Studio's own kit-fix format, pinned to the finished texture of the released build (``before_sha256``) and to what the
Studio's compile makes of it (``after_sha256``). A row lists only the texels that change, as runs of colours. The
compile keeps the native format, size, mip count, wrapper and stored allocation; colours the palette lacks take unused
entries, then entries only the repainted texels used (the ``_mud`` twin follows its own rule). The Studio applies the
document as its last uniform step (``kit_fixes.apply_uniforms_b81``), after the helmet cleanup, so every kit that reads a
2026 kit as a donor (Anniversary, classic) has read it already.

  python3 tools/b81_uniform_pass.py build --image DISC.iso --art DIR --out data/nfl2k5_kit_fixes_2026_b81u.json
                                          [--notes NOTES.json] [--receipt R.json] [--decoded DIR] [--base DOC.json]
  python3 tools/b81_uniform_pass.py check --image DISC.iso

``DIR`` holds ``<SELECTOR>_<texture>.png`` (texture: jersey00, pants00, sleeve00, socks00, 48..57 = the jersey digits,
an48..an57 = the arm digits, hn48..hn57 = the helmet digits). ``--base`` applies an earlier document (the helmet
cleanup) to the kit bytes first, so rows for a texture both passes touch are pinned to the helmet pass's result.
``NOTES`` maps ``<SELECTOR>_<texture>`` to {"note": text, "defects": [..], "reference": [frame files]}.

Authoring tool: it needs the user's own built disc. Nothing here ships except the document it writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

TSET = {"jersey00": 1, "pants00": 2, "sleeve00": 3, "socks00": 4}
SOURCE = ("b81-uniforms (beta 81): 2026 kit textures corrected against this season's game-highlight frames "
          "(refs/uniforms_2026), authored on the finished textures of the released v0.9 disc")
METHOD = ("each corrected texture is stored as runs of the texels that change; the compile adds the colours the "
          "palette lacks to unused entries and keeps format, size, mips, wrapper and allocation")
WORST = 40          # a compiled texel may differ from the authored colour by at most this much (palette room)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def modules():
    from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
    return kf, kf.bump


def chunk_of(texture: str) -> tuple[int, str]:
    """(chunk index, kit-fix kind) of a kit texture name."""
    if texture in TSET:
        return TSET[texture], "tset"
    for prefix, first in (("hn", 23), ("an", 33), ("", 13)):
        digits = texture[len(prefix):]
        if texture.startswith(prefix) and digits.isdigit() and 48 <= int(digits) <= 57:
            return first + int(digits) - 48, "txtr"
    raise ValueError("not a uniform pass texture: " + texture)


def read_kits(image: Path, selectors) -> dict:
    kf, bump = modules()
    out = {}
    with bump._Image.open(Path(image), writable=False) as source:
        index = bump._parsed_index(source)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        for selector in selectors:
            entries = by_name.get(selector + ".IFF", [])
            if len(entries) == 1:
                out[selector] = source.read_segments(index.sub_extents(entries[0], 0, entries[0].size))
    return out


def level0(span: bytes, kind: str):
    kf, _ = modules()
    chunk, decoded, textures = kf.native_textures(span, kind)
    planes = kf.read_planes(decoded, chunk, textures[0])
    palette = kf.read_palette(decoded, chunk, textures[0])
    return palette[planes[0]].astype(np.uint8), textures[0]


def runs_of(before: np.ndarray, after: np.ndarray) -> list:
    changed = (before[..., :3] != after[..., :3]).any(axis=2)
    rows = []
    for y in np.flatnonzero(changed.any(axis=1)):
        xs = np.flatnonzero(changed[y])
        starts = np.concatenate(([xs[0]], xs[1:][np.diff(xs) > 1]))
        ends = np.concatenate((xs[:-1][np.diff(xs) > 1], [xs[-1]]))
        for x0, x1 in zip(starts, ends):
            rows.append([int(y), int(x0), after[y, x0:x1 + 1, :3].tobytes().hex().upper()])
    return rows


def apply_base(raw: bytes, selector: str, base) -> bytes:
    """The kit package after an earlier pinned document (the helmet cleanup) has run on it."""
    if base is None or not any(r["selector"] == selector for r in base["textures"]):
        return raw
    kf, _ = modules()
    replacements, _receipt = kf.compile_resource(selector, raw, strict=False, document=base)
    out = bytearray(raw)
    for offset, data in replacements:
        out[offset:offset + len(data)] = data
    return bytes(out)


def build_row(selector: str, texture: str, raw: bytes, wanted: np.ndarray, info: dict):
    """One document row and the level-0 texture the compile produces, or (None, before) when nothing changes."""
    kf, _ = modules()
    index, kind = chunk_of(texture)
    chunk = kf._chunk_for(raw, index)
    span = raw[chunk.offset:chunk.end_offset]
    before, native = level0(span, kind)
    if native["name"] != texture:
        raise ValueError(f"{selector}: chunk {index} holds {native['name']}, not {texture}")
    if wanted.shape != before.shape:
        raise ValueError(f"{selector} {texture}: the picture is not {before.shape[1]}x{before.shape[0]}")
    target = before.copy()
    target[..., :3] = wanted[..., :3]          # the pass never changes alpha
    # a wanted colour within a few levels of one the palette already holds (at that alpha) takes that entry: palette
    # room goes to the colours the art really adds
    changed = (target[..., :3] != before[..., :3]).any(axis=2)
    if changed.any():
        chunk_, decoded_, textures_ = kf.native_textures(span, kind)
        palette = kf.read_palette(decoded_, chunk_, textures_[0])
        want = target[changed][:, :3].astype(np.int64)
        alphas = before[changed][:, 3].astype(np.int64)
        snapped = palette[kf.nearest(want, alphas, palette)][:, :3]
        close = np.abs(snapped - want).max(axis=1) <= int(info.get("snap", 6))
        want[close] = snapped[close]
        # blends painted over slightly uneven fabric come out a level or two apart: one colour for each such family
        far = np.flatnonzero(~close)
        if len(far):
            colours, inverse, counts = np.unique(want[far], axis=0, return_inverse=True, return_counts=True)
            order = sorted(range(len(colours)), key=lambda i: (-int(counts[i]), tuple(int(v) for v in colours[i])))
            keep, mapped = [], np.arange(len(colours))
            for i in order:
                hit = next((k for k in keep if np.abs(colours[k] - colours[i]).max() <= int(info.get("family", 3))), None)
                if hit is None:
                    keep.append(i)
                else:
                    mapped[i] = hit
            want[far] = colours[mapped[np.asarray(inverse).reshape(-1)]]
        target[changed, :3] = want.astype(np.uint8)
        changed = (target[..., :3] != before[..., :3]).any(axis=2)      # a snapped texel may be back at what it held
    # Settle: a rarely used colour beyond the declared ones compiles to the nearest palette entry (a level or two
    # away). The row must hold exactly what the compile makes, so such texels take the compiled colour and the row is
    # written again until the compile returns the row's own colours.
    for _settle in range(4):
        rows = runs_of(before, target)
        if not rows:
            return None, before, {}
        # every colour of the repainted texels is named once (one texel that wears it), most used first: the compile then
        # keeps or gives each an exact palette entry (an entry only the old art used is not handed to another colour) and,
        # on a full palette, may fold near-identical twin entries to make room
        declared = []
        if changed.any():
            new_colours, counts = np.unique(target[changed][:, :3].astype(np.int64), axis=0, return_counts=True)
            order = sorted(range(len(new_colours)), key=lambda i: (-int(counts[i]), tuple(int(v) for v in new_colours[i])))
            for i in order[:int(info.get("declare", 48))]:
                colour = tuple(int(v) for v in new_colours[i])
                ys, xs = np.nonzero(changed & (target[..., :3] == np.array(colour, np.uint8)).all(axis=2))
                declared.append(dict(op="texels", points=[[int(xs[0]), int(ys[0])]], color="#%02X%02X%02X" % colour))
        row = dict(selector=selector, chunk=index, texture=texture, kind=kind,
                   size=[int(native["width"]), int(native["height"]), int(native["mips"])],
                   resource_size=len(raw), offset=int(chunk.offset), length=len(span), before_sha256=sha(span),
                   defects=list(info.get("defects", [])), note=info.get("note", "corrected against the 2026 frames"),
                   reference=list(info.get("reference", [])), max_blend_slots=int(info.get("max_blend_slots", 96)),
                   ops=declared + [dict(op="runs", rows=rows)])
        try:
            new, detail = kf.compile_texture(span, row)
        except Exception as exc:  # noqa: BLE001 - a tight allocation: crisp mip parents compress better
            if "fit" not in str(exc).lower() and "scratch word" not in str(exc):
                raise
            row["mip"] = "mode"
            new, detail = kf.compile_texture(span, row)
        after, _native = level0(new, kind)
        scope_ = (target[..., :3] != before[..., :3]).any(axis=2)
        drift = (after[..., :3] != target[..., :3]).any(axis=2) & scope_
        if not drift.any() or int(np.abs(after[..., :3].astype(np.int64) - target[..., :3])[drift].max()) > int(info.get("snap", 6)):
            break
        if _settle == 3:
            raise ValueError(f"{selector} {texture}: the row does not settle on the compiled colours")
        target[drift, :3] = after[drift, :3]
        changed = (target[..., :3] != before[..., :3]).any(axis=2)
    scope = (target[..., :3] != before[..., :3]).any(axis=2)
    outside = (after != before).any(axis=2) & ~scope
    error = np.abs(after[..., :3].astype(np.int64) - target[..., :3]).max(axis=2)
    stats = dict(texels=int((after[..., :3] != before[..., :3]).any(axis=2).sum()), scope_texels=int(scope.sum()),
                 worst_colour_error=int(error[scope].max()), mean_colour_error=float(error[scope].mean()),
                 texels_over_8=int((error[scope] > 8).sum()), texels_changed_outside=int(outside.sum()),
                 palette_slots_added=len(detail["palette_slots_added"]), merged_twin_slots=int(detail["merged_twin_slots"]),
                 mud_rule=detail.get("mud_rule"), mip=row.get("mip", "blend"), before_sha256=row["before_sha256"])
    if stats["merged_twin_slots"] and stats["merged_twin_slots"] <= int(info.get("fold_twins", 0)):
        # a full palette (every entry used outside the repaint too): the compile's own last resort, a near-identical
        # twin entry folded into its neighbour, so a texel outside the repaint moves by at most one level. Named per row.
        row["folded_twin_entries"] = stats["merged_twin_slots"]
        row["texels_moved_one_level"] = stats["texels_changed_outside"]
    elif stats["texels_changed_outside"] or stats["merged_twin_slots"]:
        # the pass promises that only its listed texels change: art that needs more palette room than the texture
        # has free (so that twin entries would be folded) must come back with fewer blend colours
        raise ValueError(f"{selector} {texture}: the palette is full ({stats['merged_twin_slots']} twin entries would be "
                         f"folded, {stats['texels_changed_outside']} other texels would move): use fewer colours")
    if stats["worst_colour_error"] > int(info.get("worst", WORST)):
        raise ValueError(f"{selector} {texture}: compiled colour off by {stats['worst_colour_error']} "
                         f"({stats['texels_over_8']} texels over 8, {stats['palette_slots_added']} entries added): "
                         "the palette has no room for this art")
    row["after_sha256"] = sha(new)
    row["texels"] = stats["texels"]
    stats["after_sha256"] = row["after_sha256"]
    stats["after_rgba_sha256"] = sha(np.ascontiguousarray(after).tobytes())
    return row, after, stats


def cmd_build(args) -> int:
    from PIL import Image
    art = Path(args.art)
    notes = json.loads(Path(args.notes).read_text(encoding="utf-8")) if args.notes else {}
    base = json.loads(Path(args.base).read_text(encoding="utf-8")) if args.base else None
    names = sorted(p.stem for p in art.glob("*_*.png"))
    kits = read_kits(Path(args.image), sorted({n.split("_", 1)[0] for n in names}))
    rows, receipt, failed = [], {}, 0
    for name in names:
        selector, texture = name.split("_", 1)
        if selector not in kits:
            receipt[name] = dict(error="kit package absent")
            failed += 1
            continue
        with Image.open(art / f"{name}.png") as image:
            wanted = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        try:
            row, after, stats = build_row(selector, texture, apply_base(kits[selector], selector, base), wanted,
                                          notes.get(name, {}))
        except Exception as exc:  # noqa: BLE001 - named in the receipt; the other rows are still written
            receipt[name] = dict(error=str(exc)[:300])
            print("FAILED", name, str(exc)[:200], flush=True)
            failed += 1
            continue
        if row is None:
            receipt[name] = dict(texels=0)
            continue
        rows.append(row)
        receipt[name] = stats
        if args.decoded:
            Path(args.decoded).mkdir(parents=True, exist_ok=True)
            Image.fromarray(after, "RGBA").save(Path(args.decoded) / f"{name}.png")
        print(name, stats["texels"], "texels, worst", stats["worst_colour_error"], "slots", stats["palette_slots_added"],
              flush=True)
    rows.sort(key=lambda r: (r["selector"], r["chunk"]))
    document = dict(schema="nfl2k5_kit_fixes_2026/v1", source=SOURCE, method=METHOD, textures=rows)
    Path(args.out).write_text(json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8",
                              newline="\n")
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                      newline="\n")
    print(json.dumps(dict(rows=len(rows), texels=sum(r["texels"] for r in rows), failed=failed,
                          selectors=len({r["selector"] for r in rows}))))
    return 1 if failed else 0


DIGIT_SOURCE = ("b81-uniforms (beta 81): 2026 jersey digits redrawn against this season's game-highlight frames "
                "(refs/uniforms_2026), pinned to the finished digits of the released v0.9 disc")
DIGIT_ART = "nfl2k5_glyph_fixes_2026_b81u"


def digit_chunk(name: str) -> tuple[int, str]:
    """``digit_jersey_N`` / ``digit_arm_N`` / ``digit_helmet_N`` -> (chunk index, native texture name)."""
    family, digit = name.rsplit("_", 1)
    first, prefix = {"digit_jersey": (13, ""), "digit_helmet": (23, "hn"), "digit_arm": (33, "an")}[family]
    return first + int(digit), prefix + str(48 + int(digit))


def cmd_digits(args) -> int:
    """Authored digit PNGs (<SELECTOR>_digit_<family>_<N>.png, 64x64 RGBA) -> the digit document and its art folder.
    Identical pictures of several kits are stored once."""
    from io import BytesIO
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    from mod_editor.core import nfl2k5_glyph_fixes_2026 as gf
    from mod_editor.core.nfl2k5_digit_art import REGISTRATION_KEY
    kf, _ = modules()
    art, out_art = Path(args.art), ROOT / "data" / DIGIT_ART
    notes = json.loads(Path(args.notes).read_text(encoding="utf-8")) if args.notes else {}
    names = sorted(p.stem for p in art.glob("*_digit_*_?.png"))
    kits = read_kits(Path(args.image), sorted({n.split("_", 1)[0] for n in names}))
    out_art.mkdir(parents=True, exist_ok=True)
    stored, rows, receipt, failed = {}, [], {}, 0
    for name in names:
        selector, rest = name.split("_", 1)
        index, native = digit_chunk(rest)
        with Image.open(art / f"{name}.png") as image:
            rgba = image.convert("RGBA")
        key = sha(rgba.tobytes())
        if key not in stored:
            # one deterministic PNG per distinct picture, marked As authored (the Studio's own digit route)
            team = notes.get("_team", {}).get(selector[:2], selector[:2])
            file = f"{team}_{selector}_{rest}.png"
            info = PngInfo()
            info.add_text(REGISTRATION_KEY, "as_authored")
            buffer = BytesIO()
            rgba.save(buffer, "PNG", pnginfo=info, optimize=False, compress_level=9)
            (out_art / file).write_bytes(buffer.getvalue())
            stored[key] = file
        file = stored[key]
        payload = (out_art / file).read_bytes()
        raw = kits.get(selector)
        try:
            if raw is None:
                raise ValueError("kit package absent")
            chunk = kf._chunk_for(raw, index)
            span = raw[chunk.offset:chunk.end_offset]
            new, detail = gf.compile_digit(span, payload)
            if detail["texture"] != native:
                raise ValueError(f"chunk {index} holds {detail['texture']}, not {native}")
        except Exception as exc:  # noqa: BLE001 - named in the receipt; the other rows are still written
            receipt[name] = dict(error=str(exc)[:300])
            print("FAILED", name, str(exc)[:200], flush=True)
            failed += 1
            continue
        if new == span:
            receipt[name] = dict(unchanged=True)
            continue
        info_row = notes.get(name, notes.get(selector, {}))
        rows.append(dict(selector=selector, chunk=index, kind="digit_png", texture=native, resource_size=len(raw),
                         offset=int(chunk.offset), length=len(span), png=file, png_sha256=sha(payload),
                         before_sha256=sha(span), after_sha256=sha(new), defects=list(info_row.get("defects", [])),
                         note=info_row.get("note", "redrawn against the 2026 frames")))
        after, _native = level0(new, "txtr")
        receipt[name] = dict(png=file, before_sha256=sha(span), after_sha256=sha(new), palette_entries=detail["palette_entries"],
                             after_rgba_sha256=sha(np.ascontiguousarray(after).tobytes()))
        if args.decoded:
            Path(args.decoded).mkdir(parents=True, exist_ok=True)
            Image.fromarray(after, "RGBA").save(Path(args.decoded) / f"{selector}_{native}.png")
    used = set(stored.values())
    for old in out_art.glob("*.png"):
        if old.name not in used and not args.keep:
            old.unlink()
    rows.sort(key=lambda r: (r["selector"], r["chunk"]))
    document = dict(schema=gf.SCHEMA, purpose=DIGIT_SOURCE, art=DIGIT_ART, references=notes.get("_references", {}),
                    textures=rows)
    Path(args.out).write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                      newline="\n")
    print(json.dumps(dict(rows=len(rows), pictures=len(used), failed=failed, selectors=len({r["selector"] for r in rows}))))
    return 1 if failed else 0


def states(image: Path, document=None) -> dict:
    """How many rows of the document a disc image is waiting for (before), has (after), or does not match."""
    kf, _ = modules()
    document = document or kf.uniforms_b81()
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
    parser = argparse.ArgumentParser(prog="python3 tools/b81_uniform_pass.py")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write the kit-fix document from a disc image and the corrected textures")
    b.add_argument("--image", required=True)
    b.add_argument("--art", required=True, help="folder of corrected level-0 PNGs named <SELECTOR>_<texture>.png")
    b.add_argument("--notes", help="JSON {name: {note, defects, reference}}")
    b.add_argument("--base", help="an earlier kit-fix document applied first (the helmet cleanup)")
    b.add_argument("--out", required=True)
    b.add_argument("--receipt")
    b.add_argument("--decoded", help="folder for the compiled level-0 PNGs (what the game will hold)")
    d = sub.add_parser("digits", help="write the digit document and its art folder from authored digit PNGs")
    d.add_argument("--image", required=True)
    d.add_argument("--art", required=True, help="folder of <SELECTOR>_digit_<jersey|arm|helmet>_<N>.png (64x64 RGBA)")
    d.add_argument("--notes")
    d.add_argument("--out", required=True)
    d.add_argument("--receipt")
    d.add_argument("--decoded")
    d.add_argument("--keep", action="store_true", help="keep art files this run did not write")
    c = sub.add_parser("check", help="row states of the document on a disc image")
    c.add_argument("--image", required=True)
    args = parser.parse_args(argv)
    return {"build": cmd_build, "digits": cmd_digits, "check": cmd_check}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
