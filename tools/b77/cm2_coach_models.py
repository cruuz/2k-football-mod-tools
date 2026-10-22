#!/usr/bin/env python3
"""cm2 (b778): coach models that match each coach's skin, and a cap for Mike McCarthy, for
``mod_editor/core/nfl2k5_modern_coaches.py``.

Noah's 10/21 stream: Tampa Bay's Todd Bowles stood on the 2004 Jon Gruden model (c27, a white man's head, arms and
hands) with a darkened face. Noah: "we should use an actual black model". The audit of all 32 clubs (``MODEL_SKIN``
in the module: the skin of each retail coach model, from its arms, hands and face) found the same mistake the other
way round on three clubs: Todd Monken (CLE, on Dennis Green's c00), Zac Taylor (CIN, on Marvin Lewis's c06) and Shane
Steichen (IND, on Tony Dungy's c11) are white coaches with a lightened face on a Black coach's head, arms and hands.
Mike McCarthy (PIT) wore no cap (c26 has no cap geometry); Noah asked for one.

The moves (every one onto an existing 2004 model of the right skin; nothing is darkened or lightened any more):

* TB  Todd Bowles      c27 -> c00  Dennis Green's model: a Black coach's head, arms and hands, his broad build
* PIT Mike McCarthy    c26 -> c27  the capped Gruden model (black cap in the Steelers' colours), with the heavy
                                   build he had on c26 carried over by position (c13 -> c26, same family as c26)
* CLE Todd Monken      c00 -> c26  a white coach's model (glasses hidden), the average body of c13 (same family)
* CIN Zac Taylor       c06 -> c36  a white coach's model no club uses, the lean body of c20 (same family)
* IND Shane Steichen   c11 -> c33  a white coach's model no club uses, the lean body of c20 (same family)
* JAX Liam Coen        c30 (kept)  the same model; his hair painted a darker brown so it reads as short hair, not a
                                   bald crown (the stream: "does that look like liam coen")

c06 and c11 are no club's model afterwards (they go back to retail on a disc that carried them). c33 and c36 are named
by no coach record on the retail or v0.6.1 disc (the created-team coaches USER1 and USER2 use c50 and c51).

Heads are painted with cm1's painter (``cm1_coach_models.paint_head``: one skin tone on the head mesh in 3D, painted
hair and facial hair). The fine facial detail is co2's authored face of the same coach, moved from the model it was
authored on to the new model through 3D (each texel of the new head takes the detail of the nearest point of the old
head; every coach head shares one face rig and bind space), so the features land on the new mesh's features.

  python3 tools/b77/cm2_coach_models.py apparel --retail RETAIL.iso [--teams TB,PIT]
  python3 tools/b77/cm2_coach_models.py geometry --retail RETAIL.iso [--teams PIT]
  python3 tools/b77/cm2_coach_models.py head --retail RETAIL.iso [--detail-ref 0a2bcf5c] [--teams TB]

Reference photos are only looked at; no photo or retail pixel is written by this tool except through the existing
recolour of the retail garment shading (co1's ``garment``) that every club's apparel uses.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402
import cm1_coach_models as cm1  # noqa: E402

# club -> (the model he wore before cm2, the model he wears now)
MOVES = {"TB": ("27", "00"), "PIT": ("26", "27"), "CLE": ("00", "26"), "CIN": ("06", "36"), "IND": ("11", "33")}
REPAINT = ("JAX",)          # same model, head repainted

RECIPES: dict[str, dict] = {
    # Todd Bowles: dark brown skin, a touch lighter and warmer than cm1's so it meets c00's own brown arms and hands;
    # shaved head; a light grey-black stubble on the lip and chin (his headshot is near clean-shaven); brown eyes; half
    # of co2's photo detail (his broad smile's creases read as deep wrinkles on a dark face at full strength). Big: c00's
    # broad body as it is.
    "TB": {
        "who": "Todd Bowles",
        "head": dict(
            skin=(126, 78, 54), warm=(128, 72, 50), neck=0.06, mottling=0.03, lips=(114, 66, 58), brows=(46, 32, 26),
            brow_strength=0.5, eyes=(80, 52, 36), detail=0.5,
            hair=dict(colour=(40, 32, 28), opacity=0.3, front=46.0, recede=1.4, side=43.0, back=34.5, sideburn=38.6),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin"), colour=(60, 54, 52),
                         density=0.3, light=0.3, light_colour=(140, 136, 132))]),
    },
    # Mike McCarthy: fair, ruddy skin; white hair (under the cap it shows at the sides and the back); light brows;
    # clean-shaven; heavy (the c13 -> c26 build change carried onto c27 by position)
    "PIT": {
        "who": "Mike McCarthy",
        "body": dict(donor="26", via="13"),
        "head": dict(
            skin=(214, 156, 140), warm=(212, 134, 120), neck=0.08, lips=(192, 118, 106), brows=(186, 180, 172),
            brow_strength=0.35, detail=0.7,
            hair=dict(colour=(224, 222, 216), grey=0.25, grey_colour=(188, 184, 178), front=46.4, recede=1.2, side=43.4,
                      back=34.5, sideburn=38.8)),
    },
    # Todd Monken: cm1's recipe (fair, ruddy; full white-grey hair; clean-shaven), now on a white coach's head; solid
    # but not heavy: c13's average body in place of c26's belly (same family)
    "CLE": {
        "who": "Todd Monken",
        "body": dict(donor="13"),
        "head": cm1.RECIPES["CLE"]["head"],
    },
    # Zac Taylor: cm1's recipe (very fair, rosy; short brown hair; clean-shaven), lean: c20's body (same family)
    "CIN": {
        "who": "Zac Taylor",
        "body": dict(donor="20"),
        "head": cm1.RECIPES["CIN"]["head"],
    },
    # Shane Steichen: fair skin; short dark-brown hair; clean-shaven; lean: c20's body (same family); half of co2's
    # photo detail (its furrowed brow and grin creases read as a grimace at full strength)
    "IND": {
        "who": "Shane Steichen",
        "body": dict(donor="20"),
        "head": dict(
            skin=(218, 166, 148), warm=(214, 146, 130), neck=0.08, lips=(198, 124, 112), brows=(66, 50, 42),
            brow_strength=0.4, detail=0.5,
            hair=dict(colour=(60, 44, 36), front=46.8, recede=0.9, side=43.5, back=34.5, sideburn=38.8),
            facial=[dict(kind="stubble", parts=("moustache", "corners", "chin", "cheeks"), colour=(96, 84, 78),
                         density=0.08)]),
    },
    # Liam Coen: cm1's recipe with the hair a darker brown (cm1's light brown met his pink skin at sideline distance
    # and read as a bald crown in the stream); the c30 geometry (lean body) is unchanged
    "JAX": {
        "who": "Liam Coen",
        "head": dict(cm1.RECIPES["JAX"]["head"],
                     hair=dict(cm1.RECIPES["JAX"]["head"]["hair"], colour=(88, 66, 48), grey=0.0)),
    },
}


def scene(retail, code: str) -> "cm1.Scene":
    name = f"c{code}.iff"
    return cm1.Scene(cm1.read_archive(retail, name), name)


def _skin_raster(head: dict, W: int, H: int):
    T = cm1.tris_of(head, "headShader1")
    pos, tri, _alt = cm1.raster(head["U"], head["P"], T, W, H)
    main = cm1.skin_component(head)
    tri_main = np.array([t[0] in main for t in T])
    cov = tri >= 0
    return pos, cov, cov & tri_main[np.maximum(tri, 0)]


def reproject_detail(old_head: dict, old_rgba: np.ndarray, new_head: dict, scale: int = 4) -> np.ndarray:
    """``old_rgba`` (the head texture authored on ``old_head``) laid out for ``new_head``: every skin texel of the new
    layout takes the colour at the nearest skin point of the old head (both heads share the coach face rig and its
    bind space); texels outside the skin (the eye, teeth and mouth atlas, the same template place on every 2004 head)
    keep the old pixels."""
    from scipy.spatial import cKDTree
    H0, W0 = old_rgba.shape[:2]
    W, H = W0 * scale, H0 * scale
    src = np.asarray(Image.fromarray(old_rgba).convert("RGB").resize((W, H), Image.BICUBIC), float)
    pos_o, _cov_o, skin_o = _skin_raster(old_head, W, H)
    pos_n, _cov_n, skin_n = _skin_raster(new_head, W, H)
    tree = cKDTree(pos_o[skin_o])
    _d, idx = tree.query(pos_n[skin_n])
    out = src.copy()
    out[skin_n] = src[skin_o][idx]
    small = out.reshape(H0, scale, W0, scale, 3).mean(axis=(1, 3))
    return np.concatenate([np.clip(np.rint(small), 0, 255), np.full((H0, W0, 1), 255.0)], -1).astype(np.uint8)


def cmd_apparel(args) -> int:
    """Shirt (with the cap patch), jacket, chest logo and headset of each moved club, from the retail textures of the
    model it now wears (co1's recolour, same colours as before)."""
    import co1_coach_art as art
    for team in args.teams:
        _old, new = MOVES[team]
        raw = cm1.read_archive(args.retail, f"c{new}.iff")
        tx, _fill = mc._tools()
        rec, decoded = mc._mm()._scene(raw, tx.parse_chunks(raw)[0])
        t = art.textures(rec, decoded)
        top, trim, cap, _why = art.APPAREL[team]
        items = {"shirt": art.garment(t["shirtShader1"][1], top, trim, cap),
                 "jacket": art.garment(t["jacketShader1"][1], top, trim),
                 "headset": art.headset(t["accessoriesShader1"][1]), "logo": art.logo_texture(team)[0]}
        for name, master in items.items():
            Image.fromarray(art.area_down(master), "RGBA").save(mc.art_path(team, name), optimize=True)
        print(team, f"c{new}", "cap" if "hatShader1" in t else "no cap", top, trim, cap)
    return 0


def cmd_geometry(args) -> int:
    for team in args.teams:
        recipe = RECIPES[team]
        path = mc.geometry_path(team)
        if "body" not in recipe:
            if team in MOVES and path.exists():
                path.unlink()                    # the old model's edit does not fit the new model
                print(team, "geometry removed (no body change on the new model)")
            continue
        code = MOVES[team][1] if team in MOVES else None
        sc = scene(args.retail, code)
        donor = scene(args.retail, recipe["body"]["donor"])
        if recipe["body"].get("via"):
            donor = (scene(args.retail, recipe["body"]["via"]), donor)
        doc, _new = cm1.make_geometry(sc, recipe, donor)
        text = json.dumps(doc, separators=(", ", ": ")) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        print(team, sc.name, {s["name"]: (len(s["positions"]), len(s["normals"])) for s in doc["shapes"]},
              f"{len(text)} bytes")
    return 0


def cmd_head(args) -> int:
    for team in args.teams:
        recipe = RECIPES[team]["head"]
        old, new = MOVES.get(team, (None, None))
        if old is None:
            row = next(r for r in mc.pins()["teams"] if r["team"] == team)
            old = new = row["body_code"]
        blob = subprocess.run(["git", "-C", str(ROOT), "show",
                               f"{args.detail_ref}:data/nfl2k5_modern_coaches/{team}/head.png"],
                              check=True, capture_output=True).stdout
        detail = np.asarray(Image.open(io.BytesIO(blob)).convert("RGBA"))
        new_scene = scene(args.retail, new)
        if old != new:
            detail = reproject_detail(scene(args.retail, old).shapes["coachHeadGrp1"], detail,
                                      new_scene.shapes["coachHeadGrp1"])
        rgba = cm1.paint_head(new_scene.shapes["coachHeadGrp1"], detail, recipe)
        Image.fromarray(rgba).save(mc.art_path(team, "head"), optimize=True)
        print(team, f"c{old} -> c{new}", "head.png", rgba.shape)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("apparel", "geometry", "head"):
        s = sub.add_parser(name)
        s.add_argument("--retail", required=True)
        s.add_argument("--teams", default="")
        if name == "head":
            s.add_argument("--detail-ref", default="0a2bcf5c")
    a = p.parse_args(argv)
    default = list(MOVES) if a.command == "apparel" else list(MOVES) + list(REPAINT)
    a.teams = [t for t in a.teams.split(",") if t] or default
    return {"apparel": cmd_apparel, "geometry": cmd_geometry, "head": cmd_head}[a.command](a)


if __name__ == "__main__":
    raise SystemExit(main())
