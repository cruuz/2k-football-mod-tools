#!/usr/bin/env python3
"""Beta 77 u3b: author 2026 alternates (CLE DAL DEN DET GB HOU IND) into their uniform style slots.

Builds on ``tools/b77/u3s_alternates.py`` (export, cards and compile are its functions, unchanged). What this module
adds is the authoring step for sets that are not a plain transplant of the team's shipped 2026 kit: an ordered list of
``ops`` per kit that turns the donor textures into the alternate, every one measured against the donor art and the
club's own photos (the recipes in ``data/nfl2k5_uniform_alternates_2026_u3b.json`` carry the sources).

Ops (each names ``components``: fnmatch patterns on the texture stem such as ``torso``, ``sleeve``, ``pants``,
``helmet_helmet02``, ``splayer``, ``digit_jersey_*``, ``digit_arm_*``, ``socks00``). Boxes are native texture pixels
``[x0, y0, x1, y1]``. An op applies inside its ``boxes`` (default: the whole texture) minus its ``exclude`` boxes and the ``protect_small`` shapes (small enclosed components of one colour, grown);
``region`` names a box of the sideline-player atlas.

  remix     ``from``/``to`` colour lists: every texel that is a blend of the ``from`` colours is rebuilt from the same
            weights over the ``to`` colours (anti-aliasing and baked shading kept; only texels that hold one of the
            ``moved`` source indexes, default [0], change); one colour each uses the art
            tool's family recolour.
  tint      a one-colour glyph (digits) becomes ``colour`` (alpha kept, luminance kept relative to its median).
  halo      a ring of ``colour`` around the shapes of colour ``target`` (a collar trim).
  outline   a one-colour glyph (digits) gets ``fill`` inside and a ring of ``line`` ``width`` texels wide.
  star      ``stars``: [{c, R, r, rot, outline, fill, line}] antialiased five-point stars (fill ringed by line).
  paint     ``rects``: [{"box", "colour", "alpha"}] flat rectangles (stripes), shading kept when ``shade`` is true.

  export / cards / compile: as u3s_alternates.py.   author --recipes FILE --key CLE:3 --export EXPORT --out ART
"""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77"), str(ROOT / "tools/b765")]
import u3s_alternates as base  # noqa: E402
import nfl2k5_team_2026_art as art  # noqa: E402

DEFAULT_RECIPES = ROOT / "data/nfl2k5_uniform_alternates_2026_u3b.json"
hex_rgb = base.hex_rgb
require = base.require


def remix_many(rgb: np.ndarray, sources: list[np.ndarray], targets: list[np.ndarray], tolerance: float,
               moved: list[int]) -> np.ndarray:
    """u3s_alternates.remix with several moved colours: a texel changes where it holds any of the ``moved``
    source colours (the base function only moves the first one)."""
    a = np.stack(sources, axis=1).astype(np.float64)
    b = np.stack(targets, axis=1).astype(np.float64)
    x = rgb.reshape(-1, 3).T.astype(np.float64)
    weights, *_ = np.linalg.lstsq(np.vstack([a, np.full((1, a.shape[1]), 3.0)]),
                                  np.vstack([x, np.full((1, x.shape[1]), 3.0)]), rcond=None)
    weights = np.clip(weights, 0.0, None)
    weights /= np.maximum(weights.sum(axis=0, keepdims=True), 1e-6)
    residual = np.linalg.norm(x - a @ weights, axis=0)
    m = art.smooth_threshold(np.clip(1.0 - residual / tolerance, 0.0, 1.0), 0.3, 0.7)
    held = np.clip(weights[moved].sum(axis=0) / 0.02, 0.0, 1.0)
    m *= held
    new = (b @ weights).T
    out = x.T * (1 - m[:, None]) + new * m[:, None]
    return np.clip(out, 0.0, 1.0).reshape(rgb.shape).astype(np.float32)


def op_mask(shape: tuple[int, int], op: dict, regions: dict | None) -> np.ndarray:
    h, w = shape
    mask = np.ones((h, w), np.float32)
    boxes = list(op.get("boxes", []))
    if op.get("region") and regions:
        boxes.append(list(regions[op["region"]]))
    if boxes:
        mask = np.zeros((h, w), np.float32)
        for x0, y0, x1, y1 in boxes:
            mask[y0:y1, x0:x1] = 1.0
    for x0, y0, x1, y1 in op.get("exclude", []):
        mask[y0:y1, x0:x1] = 0.0
    return mask


def protect_mask(rgba: np.ndarray, rule: dict) -> np.ndarray:
    """1 where the op may act, 0 around small enclosed shapes of one colour (a star, a logo): the connected
    components of texels within ``tolerance`` (RGB distance, 0..1) of ``colour`` that cover at most ``max_area``
    texels, grown by ``grow`` texels, so their outline stays as shipped."""
    from scipy import ndimage
    near = (np.linalg.norm(rgba[..., :3] - hex_rgb(rule["colour"])[None, None, :], axis=2) < float(rule.get("tolerance", 0.12))) \
        & (rgba[..., 3] > 0.5)
    labels, count = ndimage.label(near)
    keep = np.zeros(near.shape, bool)
    if count:
        areas = ndimage.sum(near, labels, index=np.arange(1, count + 1))
        for i, area in enumerate(areas, 1):
            if area <= rule.get("max_area", 900) and area >= rule.get("min_area", 8):
                keep |= labels == i
    keep = ndimage.binary_dilation(keep, iterations=int(rule.get("grow", 3)))
    return 1.0 - keep.astype(np.float32)


def apply_op(rgba: np.ndarray, op: dict, regions: dict | None = None) -> tuple[np.ndarray, int]:
    """One op on a float RGBA texture; returns the new texture and how many texels changed."""
    out = rgba.copy()
    rgb = out[..., :3]
    mask = op_mask(rgba.shape[:2], op, regions)
    if op.get("protect_small"):
        mask = mask * protect_mask(rgba, op["protect_small"])
    kind = op["op"]
    if kind == "remix":
        if isinstance(op["from"], list):
            new = remix_many(rgb, [hex_rgb(c) for c in op["from"]], [hex_rgb(c) for c in op["to"]],
                             float(op.get("tolerance", 0.08)), list(op.get("moved", [0])))
        else:
            new = art._recolour_family(rgb, hex_rgb(op["from"]), hex_rgb(op["to"]), float(op.get("tolerance", 0.2)))
    elif kind == "tint":
        luma = rgb.mean(axis=2, keepdims=True)
        solid = rgba[..., 3] > 0.5
        reference = float(op["reference"]) if "reference" in op else float(np.median(luma[solid])) if solid.any() else 1.0
        new = np.clip(hex_rgb(op["colour"])[None, None, :] * luma / max(reference, 1e-3), 0.0, 1.0)
    elif kind == "paint":
        new = rgb.copy()
        covered = np.zeros(rgba.shape[:2], np.float32)
        luma = rgb.mean(axis=2, keepdims=True)
        for rect in op["rects"]:
            x0, y0, x1, y1 = rect["box"]
            sub = np.zeros_like(covered)
            sub[y0:y1, x0:x1] = float(rect.get("alpha", 1.0))
            colour = hex_rgb(rect["colour"])[None, None, :]
            if op.get("shade"):
                colour = np.clip(colour * (0.85 + 0.3 * luma), 0, 1)
            new = new * (1 - sub[..., None]) + colour * sub[..., None]
            covered = np.maximum(covered, sub)
        mask = mask * covered
    elif kind == "halo":
        # a ring of ``colour`` ``width`` texels wide around the shapes that are ``target`` (within ``tolerance``)
        from scipy import ndimage
        near = np.linalg.norm(rgb - hex_rgb(op["target"])[None, None, :], axis=2) < float(op.get("tolerance", 0.08))
        near &= rgba[..., 3] > 0.5
        ring = ndimage.binary_dilation(near, iterations=int(op.get("width", 2))) & ~near
        covered = ring.astype(np.float32)
        new = np.broadcast_to(hex_rgb(op["colour"])[None, None, :], rgb.shape)
        mask = mask * covered
    elif kind == "outline":
        # a one-colour glyph gets a ring: alpha grows by ``width`` texels, the glyph keeps ``fill`` and the ring is ``line``
        from scipy import ndimage
        width = int(op.get("width", 1))
        alpha = rgba[..., 3]
        size = 2 * width + 1
        yy, xx = np.mgrid[-width:width + 1, -width:width + 1]
        grown = ndimage.maximum_filter(alpha, footprint=(xx * xx + yy * yy) <= width * width + 1)
        fill, line = hex_rgb(op["fill"]), hex_rgb(op["line"])
        inside = np.clip(alpha, 0.0, 1.0)[..., None]
        out[..., :3] = line[None, None, :] * (1 - inside) + fill[None, None, :] * inside
        out[..., 3] = grown
        changed = int((out[..., 3] > 0.01).sum() - (alpha > 0.01).sum())
        return out, abs(changed) + int((alpha > 0.01).sum())
    elif kind == "star":
        # five-point stars (a line colour ring around a fill colour), drawn antialiased at 8x
        new = rgb.copy()
        covered = np.zeros(rgba.shape[:2], np.float32)
        for st in op["stars"]:
            for layer, colour, shrink in (("line", st["line"], 0.0), ("fill", st["fill"], st["outline"])):
                sub = star_coverage(rgba.shape[:2], st["c"], st["R"] - shrink * 1.6, st.get("r", 0.42),
                                    st.get("rot", 0.0))
                new = new * (1 - sub[..., None]) + hex_rgb(colour)[None, None, :] * sub[..., None]
                covered = np.maximum(covered, sub)
        mask = mask * covered
    else:
        raise SystemExit(f"unknown op {kind}")
    out[..., :3] = rgb * (1 - mask[..., None]) + new * mask[..., None]
    changed = int((np.abs(out[..., :3] - rgba[..., :3]).max(axis=2) > 1.5 / 255).sum())
    return out, changed


def star_coverage(shape: tuple[int, int], centre, radius: float, inner: float, rotation: float,
                  scale: int = 8) -> np.ndarray:
    """Antialiased coverage of a five-point star: ``radius`` is the tip distance, ``inner`` the inner/outer radius
    ratio, ``rotation`` degrees clockwise from point-up."""
    import math
    from PIL import ImageDraw
    h, w = shape
    img = Image.new("L", (w * scale, h * scale), 0)
    points = []
    for k in range(10):
        r = radius if k % 2 == 0 else radius * inner
        a = math.radians(rotation - 90 + 36 * k)
        points.append(((centre[0] + r * math.cos(a)) * scale, (centre[1] + r * math.sin(a)) * scale))
    ImageDraw.Draw(img).polygon(points, fill=255)
    return np.asarray(img.resize((w, h), Image.BOX), np.float32) / 255.0


def load_recipe(recipes: Path, key: str) -> dict:
    doc = json.loads(recipes.read_text())
    require(doc.get("schema") == base.RECIPES_SCHEMA, "unexpected recipes schema")
    recipe = doc["alternates"].get(key)
    require(recipe is not None, f"no recipe {key}")
    require(recipe.get("build_type") in ("derive", "modernize", "new"), "unknown build_type")
    return recipe


def author(recipe: dict, export_dir: Path, out: Path) -> dict:
    exp = json.loads((export_dir / "export.json").read_text())
    code, style = recipe["code"], int(recipe["style"])
    out.mkdir(parents=True, exist_ok=True)
    edits, receipts = [], {}
    for side, kit in sorted(recipe["kits"].items()):
        selector = f"{code}{side}{style}"
        donor = kit["donor"]
        target = exp["kits"][selector]
        folder = out / selector
        folder.mkdir(parents=True, exist_ok=True)
        notes = []
        ops = list(recipe.get("ops", [])) + list(kit.get("ops", []))
        for asset in target["assets"]:
            file = asset["file"]
            stem = file[:-4]
            if stem.startswith("bump_"):
                continue
            part_donor = (kit.get("part_donors") or {}).get(stem, donor)    # e.g. the sleeve from another kit
            is_blank = any(Path(file).match(pattern + ".png") for pattern in recipe.get("blank", []))
            src = {a["file"]: a for a in exp["kits"][part_donor]["assets"]}.get(file)
            if is_blank:
                rgba = np.zeros((asset["size"][1], asset["size"][0], 4), np.float32)     # the Studio draws a blank glyph as nothing
                notes.append(f"{file}: blank")
            else:
                require(src is not None and src["size"] == asset["size"] or stem.startswith("digit_arm_"),
                        f"{selector}: donor {part_donor} has no {file} of the same size")
                rgba = art.load(export_dir / "uniforms" / part_donor / file)
                if list(rgba.shape[1::-1]) != asset["size"]:
                    rgba = np.asarray(Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").resize(
                        tuple(asset["size"]), Image.LANCZOS), np.float32) / 255.0
                    notes.append(f"{file}: donor {src['size']} resized to the slot's {asset['size']}")
            for op in ops:
                if any(fnmatch.fnmatch(stem, pattern) for pattern in op["components"]):
                    rgba, n = apply_op(rgba, op, art.SPLAYER if stem == "splayer" else None)
                    notes.append(f"{file}: {op['op']} {op.get('why', '')[:60]} ({n} texels)")
            socks = kit["socks"] if "socks" in kit else recipe.get("socks")
            splayer_socks = kit["splayer_socks"] if "splayer_socks" in kit else recipe.get("splayer_socks")
            if stem in ("socks00", "socks00_mud") and socks:
                reference = art.load(export_dir / "uniforms" / selector / "socks00.png")
                rgba = base.white_socks(hex_rgb(socks["colour"]), reference)
                if stem.endswith("_mud"):
                    rgba[..., :3] *= 0.6
                notes.append(f"{file}: socks {socks['colour']} with the slot's retail fabric shading")
            if stem == "splayer" and splayer_socks:
                own = art.load(export_dir / "uniforms" / selector / "splayer.png")
                colour = hex_rgb(splayer_socks)
                for x0, y0, x1, y1 in (art.SPLAYER["sock"], art.SPLAYER["sock_low"]):
                    patch = own[y0:y1, x0:x1, :3].mean(axis=2)
                    shade = np.clip(1.0 + (patch - np.median(patch)) * 0.8, 0.8, 1.1)
                    rgba[y0:y1, x0:x1, :3] = np.clip(colour[None, None, :] * shade[..., None], 0, 1)
                notes.append(f"splayer: socks {splayer_socks} with the slot's own atlas shading")
            png = folder / file
            native = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
            Image.fromarray(native, "RGBA").save(png)
            own = np.asarray(Image.open(export_dir / "uniforms" / selector / file).convert("RGBA"))
            if any(fnmatch.fnmatch(stem, pattern) for pattern in recipe.get("keep_slot", [])):
                # the donor's texture is the slot's retail texture up to a rounding of the shipped bytes: the
                # equipment writer refuses an edit equal to retail, so the slot's own stays
                notes.append(f"{file}: kept as the slot's own (recipe keep_slot)")
                Image.fromarray(own, "RGBA").save(png)
                continue
            if np.array_equal(native, own):
                notes.append(f"{file}: already the slot's own texture, no edit")
                continue
            edits.extend(base.edit_for(selector, asset, target["outer_index"], png))
        want = dict(exp["kits"][donor]["unif"])
        want.update({k: v for k, v in (kit.get("unif") or recipe.get("unif") or {}).items() if k in want})
        if want != target["unif"]:
            edits.append({"kind": "unif_color", "selector": selector, "facemask": want["facemask"],
                          "turtleneck": want["turtleneck"]})
            notes.append(f"Unif colours {target['unif']} -> {want}")
        receipts[selector] = {"donor": donor, "notes": notes}
    doc = {"schema": "b77/u3s/alternate-art/v1", "key": f"{recipe['team']}:{style}", "set": recipe["set"],
           "edits": edits, "receipts": receipts}
    (out / "edits.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return doc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("author")
    s.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES)
    s.add_argument("--key", required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("cards")
    s.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES)
    s.add_argument("--key", required=True)
    s.add_argument("--art", type=Path, required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--models", type=Path, required=True)
    s.add_argument("--shellc", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("compile")
    s.add_argument("--art", type=Path, required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--index", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.command == "author":
        doc = author(load_recipe(a.recipes, a.key), a.export, a.out)
        print(len(doc["edits"]), "edits")
    elif a.command == "cards":
        print(json.dumps(base.cards(load_recipe(a.recipes, a.key), a.art, a.export, a.models, a.shellc, a.out)))
    elif a.command == "compile":
        manifest = base.compile_edits(a.art, a.export, a.index, a.out)
        print(json.dumps({k: len(v) for k, v in manifest["resources"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
