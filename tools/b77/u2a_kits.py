#!/usr/bin/env python3
"""Beta 77 u2a: scope-limited 2026 kit corrections for any team, on top of the shipped v0.5 art.

The Patriots job (u1) corrected one team with hand-built bands. The all-teams job corrects many small things (a wordmark
too small, a stripe too narrow, a missing sleeve mark ...) and must never churn art that is already right. The method:

  1. the correction is written into the team's Studio recipe (``data/nfl2k5_teams_2026/<TEAM>.json``) so a Studio build
     gets it;
  2. ``author`` runs the art tool's own part authors (torso, sleeve, pants, socks) twice, on the v0.5 recipe (git
     ``local/b77-base``) and on the corrected recipe. Where the two masters differ is the *scope* (grown by the filter
     footprint); every native texel outside the scope keeps its exact v0.5 RGBA, inside it the corrected master is
     box-reduced to native size. The jersey keeps its protected palette and coarse mips (u1's palette lock);
  3. ``compile`` runs the Studio's own importers on the scope-limited PNGs and records exact native spans;
  4. ``tools/b77/u2a_repair.py`` writes those spans into the v0.5 packs.

Geometry is read only. Game-derived inputs and outputs stay in private scratch (never in the repository).
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zlib

import numpy as np
from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools")]
import nfl2k5_team_2026_art as art  # noqa: E402

MASTER = art.MASTER
SCHEMA_MANIFEST = "b77/u2a/texture-repair/v1"
# a master texel counts as changed when the corrected and the v0.5 recipe masters differ by more than this (0..1)
CHANGE_EPS = 1.0 / 255.0


def _u1():
    """u1's helpers (palette lock for the jersey, helmet mips, png writer), loaded by path under one module name."""
    name = "b77_u1_patriots_helpers"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools/b77/u1_patriots.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _u8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kit_resource_name(selector: str) -> str:
    return f"{selector}.IFF"


# --------------------------------------------------------------------------------------------- scope-limited parts
def _changed_scope(new: np.ndarray, old: np.ndarray, grow: int = 1) -> np.ndarray:
    """Native-size boolean scope: native texels whose 4x4 master block differs between the two masters, grown."""
    diff = np.abs(new[..., :4] - old[..., :4]).max(axis=2) > CHANGE_EPS
    from scipy import ndimage
    h, w = diff.shape[0] // MASTER, diff.shape[1] // MASTER
    scope = diff.reshape(h, MASTER, w, MASTER).any(axis=(1, 3))
    return ndimage.binary_dilation(scope, iterations=grow) if grow else scope


def merge_scope(new_master: np.ndarray, base_u8: np.ndarray, scope: np.ndarray) -> np.ndarray:
    """Native RGBA: the corrected master box-reduced inside the scope, the shipped v0.5 texels everywhere else."""
    native = _u8(art.downscale(new_master))
    native[~scope] = base_u8[~scope]
    return native


def author_torso_delta(spec_new: "art.Spec", spec_old: "art.Spec", side: str, retail: Path, marks: Path,
                       base_png: Path, resource: Path):
    """The corrected jersey: scope from the two recipes, protected palette and coarse mips from the stored jersey."""
    u1 = _u1()
    kit_new, kit_old = spec_new.data["kits"][side], spec_old.data["kits"][side]
    new = art.author_torso(spec_new, dict(kit_new), retail, marks)
    old = art.author_torso(spec_old, dict(kit_old), retail, marks)
    base_u8 = np.asarray(Image.open(base_png).convert("RGBA")).copy()
    scope = _changed_scope(new, old)
    native = merge_scope(new, base_u8, scope)
    clean = u1._jersey_levels(resource, base_u8)
    tail = b"".join(level.rgba for level in clean[1:])
    locked = np.unique(base_u8[~scope].reshape(-1, 4), axis=0).tolist()
    preservation = {"scope_bits": base64.b64encode(np.packbits(scope).tobytes()).decode(),
                    "clean_tail_zlib": base64.b64encode(zlib.compress(tail, 9)).decode(),
                    "clean_tail_sha256": hashlib.sha256(tail).hexdigest()}
    meta = PngImagePlugin.PngInfo()
    meta.add_text("nfl2k5_palette_lock", json.dumps({"schema": "nfl2k5_palette_lock/v1", "rgba": locked,
                                                    "preserve_mips": preservation}, separators=(",", ":")))
    return native, new, scope, meta, {"locked_palette_colors": len(locked)}


def author_pants_delta(spec_new, spec_old, side: str, retail: Path, marks: Path, base_png: Path):
    kit_new, kit_old = spec_new.data["kits"][side], spec_old.data["kits"][side]
    new = art.author_pants(spec_new, dict(kit_new), retail, marks)
    old = art.author_pants(spec_old, dict(kit_old), retail, marks)
    base_u8 = np.asarray(Image.open(base_png).convert("RGBA")).copy()
    scope = _changed_scope(new, old)
    return merge_scope(new, base_u8, scope), new, scope


def author_sleeve_delta(spec_new, spec_old, side: str, retail: Path, marks: Path, base_png: Path):
    kit_new, kit_old = spec_new.data["kits"][side], spec_old.data["kits"][side]
    new = art.author_sleeve(spec_new, dict(kit_new), retail, marks)
    old = art.author_sleeve(spec_old, dict(kit_old), retail, marks)
    base_u8 = np.asarray(Image.open(base_png).convert("RGBA")).copy()
    scope = _changed_scope(new, old)
    return merge_scope(new, base_u8, scope), new, scope


def author_socks_delta(spec_new, spec_old, side: str, retail: Path, equipment: Path, base_png: Path):
    kit_new, kit_old = spec_new.data["kits"][side], spec_old.data["kits"][side]
    new = art.author_socks(spec_new, dict(kit_new), retail, equipment)
    old = art.author_socks(spec_old, dict(kit_old), retail, equipment)
    base_u8 = np.asarray(Image.open(base_png).convert("RGBA")).copy()
    scope = _changed_scope(new, old)
    native = merge_scope(new, base_u8, scope)
    mud = native.copy()
    mud[..., :3] = ((native[..., :3].astype(np.int32) * 60 + 50) // 100).astype(np.uint8)
    return native, new, scope, mud


def save_png(arr: np.ndarray, path: Path, meta: PngImagePlugin.PngInfo | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path, pnginfo=meta, optimize=False, compress_level=9)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipes_differ(spec_new: dict, spec_old: dict, side: str, part: str) -> bool:
    """True when the kit's recipe for ``part`` ('torso', 'sleeve', 'pants', 'socks') changed (the torso also reads
    nothing else from the kit; the sleeve swoosh colour lives under torso.sleeve_swooshes)."""
    keys = {"torso": ("torso",), "sleeve": ("sleeve", "torso"), "pants": ("pants",), "socks": ("socks",)}[part]
    a, b = spec_new["kits"][side], spec_old["kits"][side]
    if part == "sleeve":
        sw_a = a.get("torso", {}).get("sleeve_swooshes"); sw_b = b.get("torso", {}).get("sleeve_swooshes")
        return a.get("sleeve") != b.get("sleeve") or sw_a != sw_b
    return any(a.get(k) != b.get(k) for k in keys)


# --------------------------------------------------------------------------------------------- author command
def author_team(spec_new_path: Path, spec_old_path: Path, v05: Path, retail: Path, equipment: Path, marks: Path,
                uniform_marks: Path, out: Path, parts: tuple[str, ...] = ("torso", "sleeve", "pants", "socks", "helmet", "helmet_digits")) -> dict:
    """Author every changed part of a team's two kits on top of the shipped v0.5 export.

    ``v05``: the v0.5 kit export (``uniforms/<selector>/*.png``, ``resources/<selector>.IFF``, ``export.json``);
    ``retail``/``equipment``/``marks``: the art tool's donor inputs (retail kit export, equipment export, marks).
    Writes ``out/uniforms/<selector>/`` (the v0.5 folder with the changed textures replaced, for rendering),
    ``out/changed/<selector>/<part>_scope.png``, ``out/project.json`` (the Studio edits) and ``out/author_receipt.json``."""
    import shutil
    art.use_uniform_marks(uniform_marks)
    spec_new, spec_old = art.Spec(spec_new_path), art.Spec(spec_old_path)
    if spec_new.data["team"] != spec_old.data["team"]:
        raise ValueError("recipes are for different teams")
    code = spec_new.data["asset_code"]
    export = json.loads((v05 / "export.json").read_text())
    outer_of = {row["selector"]: row["outer_index"] for row in export["sets"]}
    edits, receipts = [], []
    for side, kit in spec_new.data["kits"].items():
        sel, side_code = kit["selector"], kit["selector"][len(code)]
        variant = int(sel[len(code) + 1:])
        folder = out / "uniforms" / sel
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(v05 / "uniforms" / sel, folder)
        base = v05 / "uniforms" / sel
        resource = v05 / "resources" / kit_resource_name(sel)
        for part in parts:
            if part == "helmet":
                if kit["helmet"].get("shell") != spec_old.data["kits"][side]["helmet"].get("shell"):
                    sf = spec_old.colour(spec_old.data["kits"][side]["helmet"]["shell"])
                    st = spec_new.colour(kit["helmet"]["shell"])
                    for family in ("helmet00", "helmet02"):
                        base_u8 = np.asarray(Image.open(base / f"helmet_{family}.png").convert("RGBA")).copy()
                        native, keep = recolour_helmet_shell(base_u8, sf, st)
                        sha_ = save_png(native, folder / f"helmet_{family}.png")
                        edits.append({"kind": "live_helmet", "asset_code": code, "side": side_code, "variant": variant,
                                      "family": family, "png": str(folder / f"helmet_{family}.png")})
                        receipts.append(dict(selector=sel, name=f"helmet_{family}", sha256=sha_,
                                             scope_texels=int(keep.sum())))
                continue
            if part == "helmet_digits":
                if kit.get("helmet_digits") != spec_old.data["kits"][side].get("helmet_digits"):
                    u1 = _u1()
                    for n, native, master in u1.author_digits(spec_new, kit, retail, "helmet", "helmet_digits"):
                        path = folder / f"digit_helmet_{n}.png"
                        sha_ = u1._save_png(native, path, registration=kit["helmet_digits"].get("registration"))
                        edits.append({"kind": "live_number_nameplate", "family": "helmet_digit", "asset_code": code,
                                      "side": side_code, "variant": variant, "digit": n, "png": str(path)})
                        receipts.append(dict(selector=sel, name=f"digit_helmet_{n}", sha256=sha_))
                continue
            if not recipes_differ(spec_new.data, spec_old.data, side, part):
                continue
            if part == "torso":
                native, master, scope, meta, info = author_torso_delta(spec_new, spec_old, side, retail, marks,
                                                                       base / "torso.png", resource)
                sha_ = save_png(native, folder / "torso.png", meta)
                edits.append({"kind": "torso", "asset_code": code, "side": side_code, "variant": variant,
                              "clean_png": str(folder / "torso.png"), "mud_png": None, "mud_mode": "darken_60"})
                receipts.append(dict(selector=sel, name="torso", sha256=sha_, scope_texels=int(scope.sum()), **info))
            elif part == "pants":
                native, master, scope = author_pants_delta(spec_new, spec_old, side, retail, marks, base / "pants.png")
                sha_ = save_png(native, folder / "pants.png")
                edits.append({"kind": "pants", "asset_code": code, "side": side_code, "variant": variant,
                              "clean_png": str(folder / "pants.png"), "mud_png": None, "mud_mode": "darken_60"})
                receipts.append(dict(selector=sel, name="pants", sha256=sha_, scope_texels=int(scope.sum())))
            elif part == "sleeve":
                native, master, scope = author_sleeve_delta(spec_new, spec_old, side, retail, marks, base / "sleeve.png")
                sha_ = save_png(native, folder / "sleeve.png")
                edits.append({"kind": "sleeve", "asset_code": code, "side": side_code, "variant": variant,
                              "clean_png": str(folder / "sleeve.png"), "mud_png": None, "mud_mode": "darken_60"})
                receipts.append(dict(selector=sel, name="sleeve", sha256=sha_, scope_texels=int(scope.sum())))
            elif part == "socks":
                outer = kit.get("outer_index") or outer_of[sel]
                kit_n = dict(kit, outer_index=outer)
                spec_new.data["kits"][side] = kit_n
                native, master, scope, mud = author_socks_delta(spec_new, spec_old, side, retail, equipment,
                                                                base / "socks00.png")
                sha_ = save_png(native, folder / "socks00.png")
                save_png(mud, folder / "socks00_mud.png")
                edits.append({"kind": "uniform_equipment_texture", "asset_id": f"tset:{outer}:4:0:socks00",
                              "png": str(folder / "socks00.png")})
                edits.append({"kind": "uniform_equipment_texture", "asset_id": f"tset:{outer}:4:1:socks00_mud",
                              "png": str(folder / "socks00_mud.png")})
                receipts.append(dict(selector=sel, name="socks00", sha256=sha_, scope_texels=int(scope.sum())))
            (out / "changed" / sel).mkdir(parents=True, exist_ok=True)
            Image.fromarray((scope * 255).astype(np.uint8)).save(out / "changed" / sel / f"{part}_scope.png")
    project = {"schema": "nfl2k5_visual_mod_project/v1", "purpose": f"b77 u2a {spec_new.data['team']} 2026 kit corrections",
               "edits": edits}
    (out / "project.json").write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (out / "author_receipt.json").write_text(json.dumps({"schema": "b77/u2a/author-receipt/v1",
        "spec_sha256": sha(Path(spec_new_path).read_bytes()), "old_spec_sha256": sha(Path(spec_old_path).read_bytes()),
        "items": receipts}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return project


# --------------------------------------------------------------------------------------------- helmet shell recolour
def recolour_helmet_shell(png: np.ndarray, shell_from: np.ndarray, shell_to: np.ndarray, min_region: int = 150,
                          exclude_x_from: int = 185) -> tuple[np.ndarray, np.ndarray]:
    """Recolour the large grey shell regions of a decoded helmet texture (RGBA u8) to another shell colour, keeping the
    shading. Small grey details (panther teeth and eyes, screws), the coloured stripes and logo, the black body of a
    logo, and the label strip on the right of the atlas keep their texels. Edge texels next to the recoloured shell are
    darkened in proportion so no light fringe is left around stripes. Returns (new RGBA u8, shell mask)."""
    from scipy import ndimage
    a = png.astype(np.float32) / 255.0
    rgb = a[..., :3]
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    ref = float(shell_from @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    cand = (chroma < 0.07) & (luma > 0.45 * ref) & (luma < 1.30 * ref) & (a[..., 3] > 0.5)
    cand[:, exclude_x_from:] = False
    lab, n = ndimage.label(cand)
    sizes = ndimage.sum(cand, lab, index=np.arange(1, n + 1))
    keep = np.isin(lab, 1 + np.where(sizes >= min_region)[0])
    k = np.clip(luma / max(ref, 1e-3), 0.0, 1.6)[..., None]
    out = rgb.copy()
    out[keep] = np.clip(shell_to[None, None, :] * k, 0, 1)[keep]
    ring = ndimage.binary_dilation(keep, iterations=1) & ~keep & (a[..., 3] > 0.5)
    ring &= (luma > 0.15)
    ring[:, exclude_x_from:] = False
    out[ring] = out[ring] * 0.45
    res = png.copy()
    res[..., :3] = (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
    return res, keep


# --------------------------------------------------------------------------------------------- project and compile
def merge_projects(final_root: Path, teams: list[str], out: Path, export: Path, job: str = "u2a") -> dict:
    """One Studio project for every team: each team's authored edits plus the Team Select cards of the kits whose art
    changed (rendered by tools/b77/u2a_cards.py into ``final_root/<TEAM>/cards/<selector>/``)."""
    sets = {row["selector"]: row for row in json.loads(export.read_text())["sets"]}
    edits, changed = [], []
    for team in teams:
        project = json.loads((final_root / team / "project.json").read_text())
        edits += project["edits"]
        receipt = json.loads((final_root / team / "author_receipt.json").read_text())
        for sel in sorted({item["selector"] for item in receipt["items"]}):
            if sel not in sets:
                raise ValueError(f"{sel} is not a shipped kit selector")
            changed.append(sel)
            # the uniform card shows the jersey, pants and helmet; the helmet cards only when the helmet itself changed
            helmet = any(item["selector"] == sel and item["name"].startswith("helmet_helmet") for item in receipt["items"])
            for family, res in ((("unif", 256), ("helm", 256), ("helm", 128)) if helmet else (("unif", 256),)):
                card = final_root / team / "cards" / sel / f"team-select_{family}_{res}.png"
                if not card.exists():
                    raise ValueError(f"missing card {card}")
                edits.append({"kind": "team_select", "asset_code": sel[:2], "side": "home" if sel[2] == "H" else "away",
                              "style": 0, "family": family, "resolution": res, "png": str(card)})
    doc = {"schema": "nfl2k5_visual_mod_project/v1", "purpose": f"b77 {job}: 2026 kits of {' '.join(teams)}",
           "edits": edits}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"kits_changed": changed, "edits": len(edits)}


def compile_all(project: Path, v05: Path, index: Path, out: Path, schema: str = SCHEMA_MANIFEST) -> dict:
    """The Studio's own importers on the merged project (u1's compiler), with the kit packages named per selector."""
    u1 = _u1()
    export = json.loads((v05 / "export.json").read_text())
    u1.NE_OUTER.clear()
    u1.NE_OUTER.update({str(row["outer_index"]): f"{row['selector']}.IFF" for row in export["sets"]})
    manifest = u1.compile_project(project, v05 / "resources", v05 / "cards", out, index)
    manifest["schema"] = schema
    (out / "native_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                              encoding="utf-8", newline="\n")
    return manifest


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("project")
    s.add_argument("--final", type=Path, required=True); s.add_argument("--teams", nargs="+", required=True)
    s.add_argument("--export", type=Path, required=True); s.add_argument("--out", type=Path, required=True)
    s.add_argument("--job", default="u2a")
    s = sub.add_parser("compile")
    s.add_argument("--project", type=Path, required=True); s.add_argument("--v05", type=Path, required=True)
    s.add_argument("--index", type=Path, required=True); s.add_argument("--out", type=Path, required=True)
    s.add_argument("--schema", default=SCHEMA_MANIFEST)
    a = p.parse_args(argv)
    if a.command == "project":
        print(json.dumps(merge_projects(a.final, a.teams, a.out, a.export, a.job)))
    else:
        manifest = compile_all(a.project, a.v05, a.index, a.out, a.schema)
        print(json.dumps({"resources": {k: len(v) for k, v in manifest["resources"].items()}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
