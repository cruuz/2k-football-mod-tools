#!/usr/bin/env python3
"""Beta 77 u3e: the alternate author for new designs and kits made of several donors (an addition to u3s_alternates.py).

``u3s_alternates.py`` authors a "derive" alternate from one donor kit per side. The six teams of job u3e also need

  * ``--overlay`` art: PNGs painted by ``tools/b77/u3e_paint.py`` (the art tool's spec route) that replace the donor's
    texture of the same name (the mud twins of equipment and socks follow with the retail darken_60 rule);
  * ``parts`` donors: a kit takes some textures (a glob of file stems) from another set;
  * recolour rules limited to one kit (``kits``), to ``include`` boxes, with ``protect_enclosed`` boxes that keep the
    body of a logo whose outline closes around it, and ``hard_edges`` for glyphs that must fit a tiny number slot.

``cards`` is ``u3s_alternates.cards`` for any build type; ``u3s_alternates.py compile`` then runs unchanged on the art
folder.

  u3e_author.py author --key WAS:9 --export EXPORT --overlay OVERLAY --out ART
  u3e_author.py cards  --key WAS:9 --art ART --export EXPORT --models DIR --shellc JSON --out CARDS
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
import u3s_alternates as ua  # noqa: E402

BUILD_TYPES = ("derive", "modernize", "new")


def load_recipe(recipes: Path, key: str) -> dict:
    doc = json.loads(recipes.read_text())
    ua.require(doc.get("schema") == ua.RECIPES_SCHEMA, "unexpected recipes schema")
    recipe = doc["alternates"].get(key)
    ua.require(recipe is not None, f"no recipe {key}")
    ua.require(recipe.get("build_type") in BUILD_TYPES, "unknown build_type")
    return recipe


def enclosed_exclusion(rgb: np.ndarray, source: np.ndarray, box, tol: float = 0.22) -> np.ndarray:
    """Texels of the first source colour (shaded versions included) inside ``box`` that are NOT connected to the
    box's border: the body of a logo whose gold outline closes around it, as against the shell around the logo
    (u3e: the Commanders' spear W keeps its burgundy on the black helmet)."""
    from scipy import ndimage
    x0, y0, x1, y1 = box
    sub = rgb[y0:y1, x0:x1]
    luma = sub @ ua.art.LUMA
    k = np.clip(luma / max(float(source @ ua.art.LUMA), 1e-3), 0.0, 2.5)
    near = np.linalg.norm(sub - source[None, None, :] * k[..., None], axis=2) < tol
    lab, n = ndimage.label(near)
    outside = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    mask = np.zeros(rgb.shape[:2], np.float32)
    inner = near & ~np.isin(lab, list(outside))
    mask[y0:y1, x0:x1] = ndimage.binary_dilation(inner, iterations=1).astype(np.float32)
    return mask


def recolour(rgba: np.ndarray, rule: dict, boxes: dict | None = None) -> tuple[np.ndarray, int]:
    """Inside the rule's region and outside its exclusions: ``remix`` (from/to lists of colours, the first moved)
    or the art tool's shading-keeping family recolour (one colour). Region: ``region`` (an atlas place, splayer
    only) or ``include`` boxes; ``exclude`` boxes; ``protect_enclosed`` boxes (see ``enclosed_exclusion``)."""
    out = rgba.copy()
    rgb = out[..., :3]
    if isinstance(rule["from"], list):
        new = ua.remix(rgb, [ua.hex_rgb(c) for c in rule["from"]], [ua.hex_rgb(c) for c in rule["to"]],
                    float(rule.get("tolerance", 0.08)))
    else:
        new = ua.art._recolour_family(rgb, ua.hex_rgb(rule["from"]), ua.hex_rgb(rule["to"]), float(rule.get("tolerance", 0.2)))
    h, w = rgba.shape[:2]
    mask = np.ones((h, w), np.float32)
    if rule.get("region") and boxes:
        mask = np.zeros((h, w), np.float32)
        x0, y0, x1, y1 = boxes[rule["region"]]
        mask[y0:y1, x0:x1] = 1.0
    if rule.get("include"):
        mask = np.zeros((h, w), np.float32)
        for x0, y0, x1, y1 in rule["include"]:
            mask[y0:y1, x0:x1] = 1.0
    for x0, y0, x1, y1 in rule.get("exclude", []):
        mask[y0:y1, x0:x1] = 0.0
    for box in rule.get("protect_enclosed", []):
        first = ua.hex_rgb(rule["from"][0] if isinstance(rule["from"], list) else rule["from"])
        mask *= 1.0 - enclosed_exclusion(rgb, first, box)
    out[..., :3] = rgb * (1 - mask[..., None]) + new * mask[..., None]
    changed = int((np.abs(out[..., :3] - rgba[..., :3]).max(axis=2) > 1.5 / 255).sum())
    return out, changed


def hard_edges(rgba: np.ndarray, colours: int, clear: str | None = None) -> np.ndarray:
    """A glyph with no anti-aliasing: alpha cut at one half, the opaque pixels quantised to ``colours`` flat colours
    (median cut, no dither). The Studio stores numbers in a few hundred bytes; a soft-edged two-tone glyph does not
    fit a small retail slot (PIT 22A5: 816 bytes), the same glyph with hard edges does (u3e probe, 2026-10-08)."""
    if clear:                                   # a fill that is the jersey's own colour is left out (transparent)
        rgba = rgba.copy()
        near = np.linalg.norm(rgba[..., :3] - ua.hex_rgb(clear)[None, None, :], axis=2) < 0.12
        rgba[near, 3] = 0.0
    alpha = rgba[..., 3] >= 0.5
    img8 = (np.clip(rgba[..., :3], 0, 1) * 255 + 0.5).astype(np.uint8)
    out = np.zeros_like(rgba)
    if not alpha.any():
        return out
    # quantise on the opaque pixels only (a canvas of just those pixels, so transparent texels do not count)
    pixels = img8[alpha]
    side = int(np.ceil(np.sqrt(len(pixels))))
    canvas = np.zeros((side * side, 3), np.uint8)
    canvas[:len(pixels)] = pixels
    q = Image.fromarray(canvas.reshape(side, side, 3), "RGB").quantize(colors=colours, method=Image.MEDIANCUT,
                                                                       dither=Image.NONE).convert("RGB")
    flat = np.asarray(q).reshape(-1, 3)[:len(pixels)]
    out[alpha, :3] = flat.astype(np.float32) / 255.0
    out[alpha, 3] = 1.0
    return out


def kit_donor(kit: dict, stem: str) -> str:
    """The donor kit of one texture: the kit's ``parts`` ({glob on the file stem: donor selector}, the first match
    wins) or its ``donor``. A new alternate takes its sleeves from the road kit and its jersey from the home kit
    (u3e)."""
    for pattern, donor in (kit.get("parts") or {}).items():
        if fnmatch.fnmatch(stem, pattern):
            return donor
    return kit["donor"]


def rule_applies(rule: dict, side: str, stem: str) -> bool:
    """A recolour rule applies to the listed component stems (globs allowed), on the kits it names (default both)."""
    if rule.get("kits") and side not in rule["kits"]:
        return False
    return any(fnmatch.fnmatch(stem, pattern) for pattern in rule["components"])


def author(recipe: dict, export_dir: Path, out: Path, overlay: Path | None = None) -> dict:
    """Both kits of the slot: every texture from its donor kit (``kit_donor``), replaced by the overlay's own PNG
    (``overlay/<selector>/<file>``, the art tool's output for the new designs) when there is one, then the recolours,
    blanks, socks and atlas rules."""
    exp = json.loads((export_dir / "export.json").read_text())
    code, style = recipe["code"], int(recipe["style"])
    out.mkdir(parents=True, exist_ok=True)
    edits, receipts = [], {}
    for side, kit in sorted(recipe["kits"].items()):
        selector = f"{code}{side}{style}"
        target = exp["kits"][selector]
        folder = out / selector
        folder.mkdir(parents=True, exist_ok=True)
        notes = []
        for asset in target["assets"]:
            file = asset["file"]
            stem = file[:-4]
            if stem.startswith("bump_"):
                continue                                        # relief maps stay the slot's own
            donor = kit_donor(kit, stem)
            donor_assets = {a["file"]: a for a in exp["kits"][donor]["assets"]}
            src = donor_assets.get(file)
            from_overlay = overlay is not None and (overlay / selector / file).exists()
            mud_of_overlay = (not from_overlay and overlay is not None and stem.endswith("_mud")
                              and (overlay / selector / f"{stem[:-4]}.png").exists())
            if from_overlay:
                source_png, src_size = overlay / selector / file, asset["size"]
                notes.append(f"{file}: overlay art")
            elif mud_of_overlay:
                source_png, src_size = overlay / selector / f"{stem[:-4]}.png", asset["size"]
                notes.append(f"{file}: the overlay's clean texture with the retail darken_60 mud rule")
            else:
                ua.require(src is not None and src["size"] == asset["size"] or stem.startswith("digit_arm_"),
                        f"{selector}: donor {donor} has no {file} of the same size")
                source_png, src_size = export_dir / "uniforms" / donor / file, (src or {}).get("size")
            rgba = ua.art.load(source_png)
            if mud_of_overlay:
                rgba[..., :3] *= 0.6
            if list(rgba.shape[1::-1]) != asset["size"]:
                rgba = np.asarray(Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").resize(
                    tuple(asset["size"]), Image.LANCZOS), np.float32) / 255.0
                notes.append(f"{file}: donor {src_size} resized to the slot's {asset['size']}")
            if any(Path(file).match(pattern + ".png") for pattern in recipe.get("blank", [])):
                rgba = np.zeros_like(rgba)                       # the Studio draws a blank glyph as nothing
                notes.append(f"{file}: blank")
            hard = recipe.get("hard_edges")
            if hard and any(fnmatch.fnmatch(stem, pattern) for pattern in hard["components"]):
                rgba = hard_edges(rgba, int(hard.get("colours", 2)), hard.get("clear"))
                notes.append(f"{file}: hard edges, {hard.get('colours', 2)} flat colours")
            for rule in recipe.get("recolour", []):
                if rule_applies(rule, side, stem):
                    rgba, n = recolour(rgba, rule, ua.art.SPLAYER if stem == "splayer" else None)
                    notes.append(f"{file}: {rule['from']} -> {rule['to']} ({n} texels)")
            if stem in ("socks00", "socks00_mud") and recipe.get("socks") and not (from_overlay or mud_of_overlay):
                reference = ua.art.load(export_dir / "uniforms" / selector / "socks00.png")
                rgba = ua.white_socks(ua.hex_rgb(recipe["socks"]["colour"]), reference)
                if stem.endswith("_mud"):
                    rgba[..., :3] *= 0.6                         # the retail darken_60 mud rule
                notes.append(f"{file}: socks {recipe['socks']['colour']} with the slot's retail fabric shading")
            if stem == "splayer" and recipe.get("splayer_socks"):
                own = ua.art.load(export_dir / "uniforms" / selector / "splayer.png")
                h, w = rgba.shape[:2]
                boxes = [ua.art.SPLAYER["sock"], ua.art.SPLAYER["sock_low"]]
                colour = ua.hex_rgb(recipe["splayer_socks"])
                for x0, y0, x1, y1 in boxes:
                    patch = own[y0:y1, x0:x1, :3].mean(axis=2)
                    shade = np.clip(1.0 + (patch - np.median(patch)) * 0.8, 0.8, 1.1)
                    rgba[y0:y1, x0:x1, :3] = np.clip(colour[None, None, :] * shade[..., None], 0, 1)
                notes.append(f"splayer: socks {recipe['splayer_socks']} with the slot's own atlas shading")
            png = folder / file
            native = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
            Image.fromarray(native, "RGBA").save(png)
            own = np.asarray(Image.open(export_dir / "uniforms" / selector / file).convert("RGBA"))
            if np.array_equal(native, own):
                notes.append(f"{file}: already the slot's own texture, no edit")
                continue
            edits.extend(ua.edit_for(selector, asset, target["outer_index"], png))
        donor = kit["donor"]
        want = dict(exp["kits"][donor]["unif"])
        want.update({k: v for k, v in (recipe.get("unif") or {}).items() if k in want})
        want.update({k: v for k, v in ((recipe.get("unif_by_kit") or {}).get(side) or {}).items() if k in want})
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
    a_ = sub.add_parser("author")
    c_ = sub.add_parser("cards")
    for q in (a_, c_):
        q.add_argument("--recipes", type=Path, default=ROOT / "data/nfl2k5_uniform_alternates_2026.json")
        q.add_argument("--key", required=True)
        q.add_argument("--export", type=Path, required=True)
        q.add_argument("--out", type=Path, required=True)
    a_.add_argument("--overlay", type=Path, default=None)
    c_.add_argument("--art", type=Path, required=True)
    c_.add_argument("--models", type=Path, required=True)
    c_.add_argument("--shellc", type=Path, required=True)
    a = p.parse_args(argv)
    recipe = load_recipe(a.recipes, a.key)
    if a.command == "author":
        doc = author(recipe, a.export, a.out, a.overlay)
        print(len(doc["edits"]), "edits;", json.dumps(doc["receipts"])[:600])
    else:
        print(json.dumps(ua.cards(recipe, a.art, a.export, a.models, a.shellc, a.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
