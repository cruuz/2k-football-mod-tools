#!/usr/bin/env python3
"""Beta 77 u3d: author the 2026 alternates of MIN NE NO NYG NYJ PHI into their slot-plan style slots.

Builds on ``tools/b77/u3s_alternates.py`` (export, Team Select cards, the compile step through the Studio's fixed-span
importers) and on the 2026 team art tool ``tools/nfl2k5_team_2026_art.py`` (the same ``author`` the primary kits were
made with). The recipes live in ``data/nfl2k5_uniform_alternates_2026_u3d.json`` (same schema as u3s's file, so
``u3s_repair.py`` and ``u3d_repair.py`` read them).

A recipe names the slot (code, style), the kits' build and any of:

* ``spec``: per side (H, A), a patch on one of the team's shipped 2026 kits (``base``: "home" or "away" in
  ``data/nfl2k5_teams_2026/<TEAM>.json``); the patched kit goes through the art tool's author functions on the slot's
  own textures (torso, sleeve, pants, both helmets, the three digit families, the nameplate, socks, the player atlas,
  equipment). ``albedo`` adds colours; ``marks_dir`` names the team's mark masks.
* ``copy``: texture files taken as they are from another kit of the export (``{"H": {"pants": "21H0"}}``).
* ``recolour`` / ``blank`` / ``socks`` / ``splayer_socks`` / ``unif``: the u3s derive rules, applied last.
* ``marks_from``: the kit whose logo, chiclet and flip chip texture replace the slot's.
* ``marks_extra``: ``{"giants_wordmark_white.png": "/path/to/file.png"}``, mask files from other folders of the research
  tree added to the mark folder.
* ``derived_marks``: full-colour marks made from the team's mark masks, ``{"logo_cr": {"fill": "logo_silhouette.png",
  "fill_colour": "#C9A646", "ring": "logo_silhouette.png", "ring_colour": "#000000", "ring_frac": 0.012, "detail":
  "logo_black.png"}}`` (an outline ring under the fill, line detail over it); ``marks`` in the spec may then name them.
* ``helmet_fleur_stripe``: the centre stripe of both helmet atlases cleared to the shell colour and redrawn as a tapering
  field of small marks (the Saints' black helmet), ``{"mark": "logo_gold.png", "colour", "base", "x", "y0", "y1", "w0",
  "w1", "size", "pitch"}`` (atlas px; the field is ``w0`` wide at ``y0`` and ``w1`` at ``y1``).
* ``retail_override``: ``{"H": {"helmet_helmet02": "19H0"}}``, textures of the slot that the art tool should start from
  in another kit's version (a slot whose own helmet is white and must become a black one starts from the green 2026
  helmet).
* ``yoke_bands``: ``{"colours": [outer, middle, inner], "params": {...}}``, three bands along the armhole seam, over the
  shoulder and down the front and back (the Patriots job's 3D bands, ``u1_patriots.yoke_stripe_bands``), added to the
  torso decorations of every side; ``params`` override ``u1_patriots.YOKE`` (cm on the rest-pose body).
* ``keep_slot``: ``["socks00", "socks00_mud"]``, textures reset to the slot's own after every other step (no edit is
  written for them).
* ``donor_all``: ``{"A": "21H4"}``, every texture (and the Unif colour words) of another kit of the export goes into
  the side first (one design in both kits of a style).
* ``modernize``: the slot's own retail art kept and given the 2026 marks of the art tool, per side or ``"all"``:
  ``torso`` {"shield": true}, ``sleeve`` {"swoosh": "#FFFFFF", "shift_rows": n, "offset": [dx, dy]}, ``pants``
  {"swoosh": "#FFFFFF", "shield": true} (the 2004 hip marks are filled from the fabric first).

  export   --disc DISC --selectors 21A0,21H0,21H13,21A13 --cards 21:13 --out EXPORT
  author   --key PHI:13 --export EXPORT --out ART
  cards    --key PHI:13 --art ART --export EXPORT --out CARDS
  compile  --art ART --export EXPORT --index RETAIL_INDEX --out COMPILED

Game-derived inputs and outputs stay in private scratch; the repository holds only recipes and tools.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77"), str(ROOT / "tools/b765")]
import nfl2k5_team_2026_art as art  # noqa: E402
import u3s_alternates as ua  # noqa: E402

RECIPES = ROOT / "data/nfl2k5_uniform_alternates_2026_u3d.json"
TEAM_SPECS = ROOT / "data/nfl2k5_teams_2026"
RESEARCH = Path(os.environ.get("B76_RESEARCH", "/media/noah/Storage/.b76-research"))
UNIFORM_MARKS = RESEARCH / "uw/marks/manifest.json"
MODELS = RESEARCH / "u3/minis/models"
SIDE_NAME = {"H": "home", "A": "away"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_recipe(key: str, recipes: Path = RECIPES) -> dict:
    doc = json.loads(recipes.read_text())
    require(doc.get("schema") == ua.RECIPES_SCHEMA, "unexpected recipes schema")
    recipe = doc["alternates"].get(key)
    require(recipe is not None, f"no recipe {key}")
    return recipe


def merge(base, patch):
    """Deep merge: dicts merge key by key, every other value (lists too) is replaced; ``None`` deletes a key."""
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return copy.deepcopy(patch)
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def helmet_fleur_stripe(cfg: dict, marks: Path, png: Path) -> None:
    """Both helmet atlases carry the stripe at the same columns (155..169); the retail stripe is filled with the shell
    colour (``base``) and the small marks laid in rows, tapering from ``w0`` at ``y0`` to ``w1`` at ``y1``."""
    M = art.MASTER
    ref = art.load(png)
    out = art.upscale(ref)
    shape = out.shape[:2]
    x0, x1 = (float(v) for v in cfg.get("clear", (152, 172)))
    art.over(out, ua.hex_rgb(cfg["base"]), art.rect_coverage(shape, x0 * M, 0, x1 * M, float(cfg["y1"] + 6) * M))
    path = marks / cfg["mark"]
    colour = ua.hex_rgb(cfg["colour"])
    rows = np.arange(float(cfg["y0"]), float(cfg["y1"]) + 1e-6, float(cfg["pitch"]))
    for i, y in enumerate(rows):
        t = i / max(len(rows) - 1, 1)
        width = float(cfg["w0"]) + (float(cfg["w1"]) - float(cfg["w0"])) * t
        count = max(1, int(round(width / float(cfg["pitch"]))))
        size = float(cfg["size"]) * (1.0 - 0.35 * t)
        offset = (0.5 if i % 2 else 0.0) * float(cfg["pitch"]) * (count > 1)
        for k in range(count):
            x = float(cfg["x"]) + (k - (count - 1) / 2.0) * float(cfg["pitch"]) + offset * (0.5 if count > 1 else 0)
            cov = art.mark_coverage(path, shape, (x * M, y * M), size * M, 0.0)
            art.over(out, colour, cov)
    out[..., 3] = np.asarray(Image.fromarray(ref[..., 3]).resize(out.shape[1::-1], Image.NEAREST), np.float32)
    art.save(art.downscale(out), png)


# ----------------------------------------------------------------------------------------------- inputs

def equipment_dir(export_dir: Path) -> Path:
    """The art tool's ``--equipment`` folder (tset_<outer>_<chunk>_<index>_<name>.png, p8_<outer>_<name>.png) as
    links to the export's textures."""
    exp = json.loads((export_dir / "export.json").read_text())
    out = export_dir / "equipment"
    out.mkdir(exist_ok=True)
    for selector, kit in exp["kits"].items():
        outer = kit["outer_index"]
        link = export_dir / "uniforms" / selector / "nameplate.png"      # the art tool's name for names.png
        if not link.exists() and (link.parent / "names.png").exists():
            link.symlink_to("names.png")
        for a in kit["assets"]:
            src = (export_dir / "uniforms" / selector / a["file"]).resolve()
            if a["kind"] == "TSET" and a["chunk"] in ua.EQUIPMENT_CHUNKS:
                name = f"tset_{outer}_{a['chunk']}_{a['tset_index']}_{a['name']}.png"
            elif a["file"][:-4] in ua.P8_CHUNKS:
                name = f"p8_{outer}_{a['file']}"
            else:
                continue
            dst = out / name
            if not dst.exists():
                dst.symlink_to(src)
    return out


def build_spec(recipe: dict, export_dir: Path) -> dict:
    """The art tool's spec document for the alternate: the team's 2026 kits patched per side, on the slot's selectors."""
    exp = json.loads((export_dir / "export.json").read_text())
    team = json.loads((TEAM_SPECS / f"{recipe['team']}.json").read_text())
    spec = copy.deepcopy(team)
    spec["status"] = f"u3d alternate {recipe['team']}:{recipe['style']} {recipe['set']}"
    spec["albedo"].update(recipe.get("albedo", {}))
    spec["marks"].update(recipe.get("marks", {}))
    kits = {}
    for side, patch in recipe["spec"]["kits"].items():
        selector = f"{recipe['code']}{side}{recipe['style']}"
        base = team["kits"][patch.get("base", SIDE_NAME[side])]
        kit = merge(base, {k: v for k, v in patch.items() if k != "base"})
        kit["selector"] = selector
        kit["outer_index"] = exp["kits"][selector]["outer_index"]
        kit.setdefault("card", {"recolour": []})
        sp = kit.get("splayer")
        if sp:
            # the slot's own atlas torso (``torso_donor``) or another kit's: the outer index is read from the export
            sp["torso_donor_outer"] = exp["kits"][sp["torso_donor"]]["outer_index"]
        kits[side] = kit
    yoke = recipe.get("yoke_bands")
    if yoke:
        import u1_patriots
        tris = u1_patriots.gltf_triangles(MODELS / "hi_body_o3c114.gltf", "UNIF_jersey")
        item = u1_patriots.yoke_stripe_bands(tris, yoke["colours"], dict(u1_patriots.YOKE, **yoke.get("params", {})))
        for kit in kits.values():
            kit["torso"]["decorations"] = list(kit["torso"].get("decorations") or []) + [item]
    spec["kits"] = kits
    return spec


# ----------------------------------------------------------------------------------------------- author

def _skip_cards(monkey: bool = True):
    """The art tool also redraws Team Select cards from the retail card art; the cards here are rendered from the
    authored textures (u3s ``cards``), so the art tool's own card step is stubbed out."""
    stub = lambda *a, **k: np.zeros((4, 4, 4), np.float32)  # noqa: E731
    art.author_card_general = stub
    art.author_card_unif = stub
    art.author_card_helm = stub


def derive_marks(recipe: dict, marks: Path, out: Path) -> Path:
    """A folder with the team's marks (linked) and the recipe's derived ones."""
    from scipy import ndimage
    folder = out / "_marks"
    folder.mkdir(parents=True, exist_ok=True)
    for f in marks.glob("*.png"):
        link = folder / f.name
        if not link.exists():
            link.symlink_to(f)
    for name, path in (recipe.get("marks_extra") or {}).items():
        link = folder / name
        if not link.exists():
            link.symlink_to(Path(path))
    for name, rule in (recipe.get("derived_marks") or {}).items():
        def mask(file):
            files = file if isinstance(file, list) else [file]       # a list is the union of its masks
            return np.max([np.asarray(Image.open(marks / f).convert("RGBA"), np.float32)[..., 3] / 255.0
                           for f in files], axis=0)
        fill_a = mask(rule["fill"])
        h, w = fill_a.shape
        r = max(1, int(round(float(rule.get("ring_frac", 0.012)) * h)))
        y, x = np.ogrid[-r:r + 1, -r:r + 1]
        ring_a = ndimage.binary_dilation(mask(rule["ring"]) > 0.5, structure=(x * x + y * y <= r * r)).astype(np.float32)
        ring_rgb = ua.hex_rgb(rule.get("ring_colour", "#000000"))
        fill_rgb = ua.hex_rgb(rule["fill_colour"])
        detail_a = mask(rule["detail"]) if rule.get("detail") else np.zeros_like(fill_a)
        # premultiplied "over": ring, then the fill, then the line detail in the ring colour
        out_p = ring_a[..., None] * ring_rgb[None, None, :]
        out_a = ring_a.copy()
        for a_, rgb_ in ((fill_a, fill_rgb), (detail_a, ring_rgb)):
            out_p = a_[..., None] * rgb_[None, None, :] + (1 - a_[..., None]) * out_p
            out_a = a_ + (1 - a_) * out_a
        rgba = np.zeros((h, w, 4), np.float32)
        rgba[..., :3] = np.where(out_a[..., None] > 1e-4, out_p / np.maximum(out_a[..., None], 1e-4), 0)
        rgba[..., 3] = out_a
        Image.fromarray((np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(folder / f"{name}.png")
    return folder


def retail_dir(recipe: dict, export_dir: Path, out: Path) -> Path:
    """The art tool's ``--retail`` folder: the export's uniform folders, with the recipe's per-slot overrides."""
    base = export_dir / "uniforms"
    over = recipe.get("retail_override") or {}
    folder = out / "_retail"
    if folder.exists():
        import shutil
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for sel in sorted(p.name for p in base.iterdir() if p.is_dir()):
        mine = {f"{recipe['code']}{side}{recipe['style']}": ov for side, ov in over.items()}.get(sel)
        if not mine:
            (folder / sel).symlink_to((base / sel).resolve())
            continue
        (folder / sel).mkdir()
        for f in (base / sel).iterdir():
            donor = mine.get(f.stem)
            src = (base / donor / f.name) if donor else f
            (folder / sel / f.name).symlink_to(src.resolve())
    return folder


def run_art_tool(spec: dict, export_dir: Path, marks: Path, out: Path, retail: Path | None = None) -> dict:
    _skip_cards()
    spec_path = out / "spec.json"
    out.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8", newline="\n")
    equipment = equipment_dir(export_dir)
    args = argparse.Namespace(spec=str(spec_path), retail=str(retail or export_dir / "uniforms"), marks=str(marks),
                              uniform_marks=str(UNIFORM_MARKS), equipment=str(equipment), outer_home=0,
                              outer_away=0, out=str(out / "authored"))
    (out / "authored").mkdir(exist_ok=True)
    require(art.cmd_author(args) == 0, "art tool author failed")
    return json.loads((out / "authored/manifest.json").read_text())


FILE_FOR = {"nameplate": "names"}


def modernize_part(part: str, ops: dict, png: Path) -> None:
    """Retail art plus the official marks, painted on a 4x master as the art tool does for a whole kit."""
    M = art.MASTER
    out = art.upscale(art.load(png))
    if part == "torso":
        if ops.get("shield"):
            c = art.COLLAR_SHIELD
            top = art.TORSO_V_TIP[1] + float(ops.get("trim", 0.0)) + c["gap_px"]
            art.place_mark(out, "nfl_shield", (art.TORSO_V_TIP[0] * M, (top + c["height_px"] / 2.0) * M),
                           c["width_px"] * M, c["height_px"] * M)
    elif part == "sleeve":
        if ops.get("shift_rows"):
            base = np.median(out[:, :, :3].reshape(-1, 3), axis=0)
            out = art.shift_sleeve_islands(out, int(ops["shift_rows"]), base, str(png))
        if ops.get("swoosh"):
            colour = ua.hex_rgb(ops["swoosh"])
            for arm in ("R", "L"):
                art.sleeve_swoosh(out, colour, arm, offset=tuple(ops.get("offset", (0.0, 0.0))))
    elif part == "pants":
        for box in (art.PANTS_SHIELD_BOX, art.PANTS_MAKER_BOX):
            out = art._clear_old_mark(out, box)
        if ops.get("swoosh"):
            ps = art.PANTS_SWOOSH
            art.place_mark(out, "nike_swoosh", (ps["centre"][0] * M, ps["centre"][1] * M), ps["width_px"] * M,
                           ps["height_px"] * M, colour=ua.hex_rgb(ops["swoosh"]))
        if ops.get("shield"):
            sh = art.PANTS_SHIELD
            art.place_mark(out, "nfl_shield", (sh["centre"][0] * M, sh["centre"][1] * M), sh["width_px"] * M,
                           sh["height_px"] * M)
    else:
        raise SystemExit(f"modernize: unknown part {part}")
    out[..., 3] = 1.0 if part != "sleeve" else out[..., 3]
    art.save(art.downscale(out), png)


def author(recipe: dict, export_dir: Path, out: Path, marks: Path | None = None) -> dict:
    exp = json.loads((export_dir / "export.json").read_text())
    code, style = recipe["code"], int(recipe["style"])
    out.mkdir(parents=True, exist_ok=True)
    notes: dict[str, list[str]] = {}
    sides = sorted(recipe["kits"])
    # 1. every texture starts as the slot's own
    for side in sides:
        sel = f"{code}{side}{style}"
        (out / sel).mkdir(exist_ok=True)
        notes[sel] = []
        for a in exp["kits"][sel]["assets"]:
            Image.open(export_dir / "uniforms" / sel / a["file"]).convert("RGBA").save(out / sel / a["file"])
    # 2. the art tool's kits
    if recipe.get("spec"):
        spec = build_spec(recipe, export_dir)
        equipment_dir(export_dir)
        marks_dir = derive_marks(recipe, marks or Path(recipe["marks_dir"]), out / "_art")
        manifest = run_art_tool(spec, export_dir, marks_dir, out / "_art", retail_dir(recipe, export_dir, out / "_art"))
        for item in manifest["items"]:
            if item["kind"] == "team_select":
                continue
            sel = item["set"]
            file = FILE_FOR.get(item["name"], item["name"]) + ".png"
            src = out / "_art" / "authored" / item["retail"]
            have = {a["file"] for a in exp["kits"][sel]["assets"]}
            require(file in have, f"{sel}: the art tool wrote {file}, which the slot has no texture for")
            Image.open(src).convert("RGBA").save(out / sel / file)
            notes[sel].append(f"{file}: art tool")
            if item["name"].startswith(("socks00",)) and f"{item['name']}_mud.png" in have:
                mud = art.load(src)
                mud[..., :3] *= 0.6
                art.save(mud, out / sel / f"{item['name']}_mud.png")
    # 2b. whole kits from another kit of the export (one design in both kits of the style)
    for side in sides:
        sel = f"{code}{side}{style}"
        donor = (recipe.get("donor_all") or {}).get(side)
        if donor:
            for a in exp["kits"][sel]["assets"]:
                if a["file"].startswith("bump_"):
                    continue
                im = Image.open(export_dir / "uniforms" / donor / a["file"]).convert("RGBA")
                if list(im.size) != a["size"]:
                    im = im.resize(tuple(a["size"]), Image.LANCZOS)
                im.save(out / sel / a["file"])
            notes[sel].append(f"every texture copied from {donor}")
    # 3. whole files from other kits
    for side in sides:
        sel = f"{code}{side}{style}"
        for stem, donor in (recipe.get("copy", {}).get(side, {}) or {}).items():
            src = export_dir / "uniforms" / donor / f"{stem}.png"
            Image.open(src).convert("RGBA").save(out / sel / f"{stem}.png")
            notes[sel].append(f"{stem}.png: copied from {donor}")
        mf = recipe.get("marks_from")
        if mf:
            for stem in ("logo", "chiclet", "flipchip"):
                Image.open(export_dir / "uniforms" / mf / f"{stem}.png").convert("RGBA").save(out / sel / f"{stem}.png")
                notes[sel].append(f"{stem}.png: from {mf}")
    # 3a. the stripe of small marks on the helmets
    hs = recipe.get("helmet_fleur_stripe")
    if hs:
        for side in sides:
            sel = f"{code}{side}{style}"
            for fam in ua.HELMETS:
                helmet_fleur_stripe(hs, Path(recipe["marks_dir"]), out / sel / f"helmet_{fam}.png")
            notes[sel].append("helmet atlases: stripe of small marks")
    # 3b. the slot's retail art with the 2026 marks
    mod = recipe.get("modernize")
    if mod:
        art.use_uniform_marks(UNIFORM_MARKS)
        for side in sides:
            sel = f"{code}{side}{style}"
            cfg = merge(mod.get("all", {}), mod.get(side, {}))
            for part, ops in cfg.items():
                notes[sel].append(f"{part}.png: 2026 marks {sorted(ops)}")
                modernize_part(part, ops, out / sel / f"{part}.png")
    # 4. the u3s derive rules
    for side in sides:
        sel = f"{code}{side}{style}"
        for asset in exp["kits"][sel]["assets"]:
            stem = asset["file"][:-4]
            png = out / sel / asset["file"]
            rgba = art.load(png)
            changed = False
            if any(Path(asset["file"]).match(p + ".png") for p in recipe.get("blank", [])):
                rgba = np.zeros_like(rgba)
                notes[sel].append(f"{asset['file']}: blank")
                changed = True
            for rule in recipe.get("recolour", []):
                if stem in rule["components"] and side in rule.get("sides", sides):
                    rgba, n = ua.recolour(rgba, rule, art.SPLAYER if stem == "splayer" else None)
                    notes[sel].append(f"{asset['file']}: {rule['from']} -> {rule['to']} ({n} texels)")
                    changed = True
            if changed:
                Image.fromarray((np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(png)
    # 4b. textures kept as the slot's own (``keep_slot``: stems): the Studio's equipment writer scrambles banded
    # equipment textures (striped socks), so such a texture is left retail rather than rewritten
    for side in sides:
        sel = f"{code}{side}{style}"
        for stem in recipe.get("keep_slot", []):
            src = export_dir / "uniforms" / sel / f"{stem}.png"
            if src.exists():
                Image.open(src).convert("RGBA").save(out / sel / f"{stem}.png")
                notes[sel].append(f"{stem}.png: kept as the slot's own (banded equipment texture)")
    # 5. edits: every texture that differs from the slot's own
    edits = []
    for side in sides:
        sel = f"{code}{side}{style}"
        target = exp["kits"][sel]
        for asset in target["assets"]:
            if asset["file"].startswith("bump_"):
                continue
            png = out / sel / asset["file"]
            own = np.asarray(Image.open(export_dir / "uniforms" / sel / asset["file"]).convert("RGBA"))
            if np.array_equal(np.asarray(Image.open(png).convert("RGBA")), own):
                continue
            edits.extend(ua.edit_for(sel, asset, target["outer_index"], png))
        want = dict(target["unif"])
        want.update({k: v for k, v in (recipe.get("unif") or {}).items() if k in want})
        if want != target["unif"]:
            edits.append({"kind": "unif_color", "selector": sel, "facemask": want["facemask"],
                          "turtleneck": want["turtleneck"]})
            notes[sel].append(f"Unif colours {target['unif']} -> {want}")
    doc = {"schema": "b77/u3s/alternate-art/v1", "key": f"{recipe['team']}:{style}", "set": recipe["set"],
           "edits": edits, "receipts": notes}
    (out / "edits.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return doc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("export")
    s.add_argument("--disc", type=Path, required=True)
    s.add_argument("--selectors", required=True)
    s.add_argument("--cards", default="")
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("author")
    s.add_argument("--recipes", type=Path, default=RECIPES)
    s.add_argument("--key", required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--marks", type=Path)
    s = sub.add_parser("cards")
    s.add_argument("--recipes", type=Path, default=RECIPES)
    s.add_argument("--key", required=True)
    s.add_argument("--art", type=Path, required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--models", type=Path, default=MODELS)
    s.add_argument("--shellc", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("compile")
    s.add_argument("--art", type=Path, required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--index", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.command == "export":
        doc = ua.export(a.disc, a.selectors.split(","), [c for c in a.cards.split(",") if c], a.out)
        print(json.dumps({k: len(v["assets"]) for k, v in doc["kits"].items()}), len(doc["cards"]), "cards")
    elif a.command == "author":
        doc = author(load_recipe(a.key, a.recipes), a.export, a.out, a.marks)
        print(len(doc["edits"]), "edits")
    elif a.command == "cards":
        print(json.dumps(ua.cards(load_recipe(a.key, a.recipes), a.art, a.export, a.models, a.shellc, a.out)))
    elif a.command == "compile":
        manifest = ua.compile_edits(a.art, a.export, a.index, a.out)
        print(json.dumps({k: len(v) for k, v in manifest["resources"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
