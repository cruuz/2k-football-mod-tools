#!/usr/bin/env python3
"""Beta 77 ALG: what the Allegiant (s20) turf draws on screen, by the game's own colour model. Read only.

Input is a directory of the nine extracted s20{d,a,n}{d,r,s}.iff bundles. For each bundle it reads the field scene's
colour map (``color_premipped``) and outside grass (``grass_outside_premipped``), the Fldd tint and the grass and
outside vertex tints, then applies Modern surfaces' calibrated model: on screen = map x rig gain x screen factor x Fldd
tint x vertex tint x the measured response (FIELD_RESPONSE for the field, APRON_RESPONSE for the outside grass). The
rig is the one Modern surfaces solved the bundle under; its gain is Modern colour's configured rig when the disc's
colour-lighting receipt is given (``--colour-lighting``), else the retail rig. Nothing here writes a bundle.

    python3 tools/b77/alg_grass_check.py --bundles DIR [--colour-lighting IMAGE.colour-lighting.json] [--out OUT.json]
    python3 tools/b77/alg_grass_check.py --photos REFS_DIR [--out OUT.json]     (turf colour in the dated photos)

Pass 4 finding: the stadium previews drew the turf at its raw colour-map value; the game draws map x rig gain x screen
factor x tints x the measured response, about half of it (the dome rig's gain is 2.6 and Modern colour's screen factor
0.18), so the previews showed the grass about 1.9 times too bright (luma 189 against 99 on screen).
"""
from __future__ import annotations

import argparse
import colorsys
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from mod_editor.core import nfl2k5_allegiant_model as lv  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: E402
from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402

SCHEMA = "b77_alg_grass_check/v2"
PREFIX = "s20"
LUMA = np.array([0.299, 0.587, 0.114])


def read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        chunks = []
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                return b"".join(chunks)
            chunks.append(block)
    finally:
        os.close(fd)


def on_screen(rgb, gain, factor, tint, vertex, response):
    """Modern surfaces' calibrated model of one surface's drawn colour (response is a number or one per channel)."""
    resp = response if isinstance(response, (tuple, list)) else (response,) * 3
    return tuple(float(v) * g * f * (t / 255.0) * (x / 255.0) * r
                 for v, g, f, t, x, r in zip(rgb, gain, factor if isinstance(factor, (tuple, list)) else (factor,) * 3,
                                             tint, vertex, resp))


def luma(rgb):
    return float(np.dot(rgb, LUMA))


def _r(values, nd=1):
    return [round(float(v), nd) for v in values]


def bundle_check(data, name, colour_settings=None):
    """One bundle's turf: the stored maps, the tints and what the game model draws."""
    _venue, time_code, _weather = ms.bundle_parts(name)
    cls = ms.light_class(name, True)  # the Allegiant row is indoor (ROST +0x18 = 1), so every s20 bundle takes the dome rig
    rig = ms.rig_name(cls, time_code)
    look = ms.venue_look(PREFIX)
    chunk = ml.bundle_scenes(data)["field"]
    rec, dec = ml._scene(data, chunk)
    rows = ml.texture_rows(rec)
    grass, _ = ml.read_p8(dec, chunk.system_bytes, rows[ms.COLOUR_MATERIAL])
    outside, _ = ml.read_p8(dec, chunk.system_bytes, rows[ms.OUTSIDE_MATERIAL])
    tint = ms.field_tint(data) or (255, 255, 255)
    vertex = ms._grass_vertex_tint(dec, rec) or (255, 255, 255)
    vertex_out = ms._outside_vertex_tint(dec, rec) or (255, 255, 255)
    layout = ms.field_layout(dec, rec)
    gain = ms.rig_gain(rig, colour_settings)
    factor = ms.screen_factor(rig)
    response = ms.field_response(look, cls, layout)
    pix = grass[..., :3].reshape(-1, 3).astype(np.float64)
    mean = pix.mean(0)
    drawn = on_screen(mean, gain, factor, tint, vertex, response)
    scale = np.array(drawn) / np.maximum(mean, 1e-6)
    drawn_luma = (pix * scale) @ LUMA
    out_mean = outside[..., :3].reshape(-1, 3).astype(np.float64).mean(0)
    apron = on_screen(out_mean, gain, factor, tint, vertex_out, ms.apron_response(cls))
    target = ms.venue_target(PREFIX, look, cls)
    return dict(
        light=cls, rig=rig, look=look, layout=layout, surfaced=bool(ms.surfaced(dec, rec)),
        map_mean=_r(mean), map_luma_std=round(float((pix @ LUMA).std()), 2),
        outside_map_mean=_r(out_mean), fldd_tint=list(tint), vertex_tint=list(vertex),
        outside_vertex_tint=list(vertex_out), rig_gain=_r(gain, 3), screen_factor=factor, response=response,
        field_on_screen=_r(drawn), field_on_screen_luma=round(luma(drawn), 1),
        field_on_screen_luma_std=round(float(drawn_luma.std()), 2),
        apron_on_screen=_r(apron), target=_r(target), target_luma=round(luma(target), 1),
        field_over_target=_r([d / max(1e-6, t) for d, t in zip(drawn, target)], 3),
        field_scale=_r(scale, 4), apron_scale=_r(np.array(apron) / np.maximum(out_mean, 1e-6), 4))


def colour_settings_from(path):
    """Modern colour's settings from an image's colour-lighting receipt (None when the receipt has none)."""
    if not path:
        return None
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return doc.get("settings")


def check(bundles_dir, colour_settings=None):
    rows = {}
    for name in lv.VARIANTS:
        rows[name] = bundle_check(read(Path(bundles_dir) / name), name, colour_settings)
    return dict(schema=SCHEMA, colour_graded=colour_settings is not None, bundles=rows)


# --- the photos ---------------------------------------------------------------------------------------------------------
#: dated Commons photos (b76 research refs, ``commons/img``): key -> (file, date as the Commons record gives it, note)
COMMONS = {
    "a00": ("a00_2021_Vegas_Kickoff_Classic_at_Allegiant_Stadium_202109061517.jpg", "2021-09-04 game (evening, INFERRED)", "wide, 200 level"),
    "a01": ("a01_2021_Vegas_Kickoff_Classic_at_Allegiant_Stadium_202109061533.jpg", "2021-09-04 game (evening, INFERRED)", "wide, 400 level"),
    "a02": ("a02_2022_Las_Vegas_Bowl_Allegiant_Stadium_jpg.jpg", "2022-12-17 12:15", "wide, day, roof lit"),
    "a16": ("a16_Daniel_Carlson_field_goal_Raiders_WFT_DEC2021_jpg.jpg", "2021-12-05 18:23", "field level, day"),
    "a33": ("a33_WFT_at_Raiders_51736169241_jpg.jpg", "2021-12-05 17:16", "field level, day"),
    "a34": ("a34_WFT_at_Raiders_51736405153_jpg.jpg", "2021-12-05 17:06", "field level, day"),
    "a25": ("a25_Vegas_Kickoff_Classic_Brigham_Young_University_BYU_Cougars_2.jpg", "2021-09-04 20:34", "field level, evening"),
    "a27": ("a27_Vegas_Kickoff_Classic_Brigham_Young_University_BYU_Cougars_2.jpg", "2021-09-04 20:34", "high angle, evening"),
}
FIELD_SHARE = 0.20


def photo_turf(path):
    """Median turf colour of one photo with an automatic mask: green-dominant, saturated, not paint or deep shadow."""
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    m = (g >= r * 1.05) & (g >= b * 1.15) & (sat > 0.18) & (mx > 30) & (mn < 200)
    if m.sum() < 500:
        return None
    px = a[m]
    med = np.median(px, 0)
    y = px @ LUMA
    hue = float(colorsys.rgb_to_hsv(*(med / 255.0))[0] * 360)
    return dict(share=round(float(m.mean()), 3), median=_r(med), luma=round(float(np.median(y)), 1),
                luma_p25_p75=[round(float(np.percentile(y, 25)), 1), round(float(np.percentile(y, 75)), 1)],
                r_over_g=round(float(med[0] / med[1]), 3), b_over_g=round(float(med[2] / med[1]), 3), hue=round(hue, 1))


def photo_summary(rows):
    """Median of the field-dominant photos' turf medians (share at least FIELD_SHARE)."""
    big = [v for v in rows.values() if v and v["share"] >= FIELD_SHARE]
    if not big:
        return None
    med = np.median([v["median"] for v in big], 0)
    return dict(photos=len(big), median=_r(med), luma=round(float(np.median([v["luma"] for v in big])), 1),
                luma_p25_p75=[round(float(np.percentile([v["luma"] for v in big], q)), 1) for q in (25, 75)],
                r_over_g=round(float(np.median([v["r_over_g"] for v in big])), 3),
                b_over_g=round(float(np.median([v["b_over_g"] for v in big])), 3),
                hue=round(float(np.median([v["hue"] for v in big])), 1))


def photos_check(refs):
    refs = Path(refs)
    out = dict(schema=SCHEMA, commons={}, raiders={}, mask="green >= 1.05 red and >= 1.15 blue, saturation > 0.18, "
               "max > 30, min < 200 (no paint, no deep shadow)")
    for key, (name, date, note) in COMMONS.items():
        row = photo_turf(refs / "commons" / "img" / name)
        out["commons"][key] = dict(row or {}, date=date, note=note)
    gallery = {}
    for path in sorted((refs / "raiders").glob("*/*.jpg")):
        gallery[f"{path.parent.name[:14]}/{path.name[:3]}"] = photo_turf(path)
    out["raiders"] = dict(photos=len(gallery), summary=photo_summary(gallery),
                          per_gallery={g: photo_summary({k: v for k, v in gallery.items() if k.startswith(g[:14])})
                                       for g in sorted({k.split("/")[0] for k in gallery})})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bundles")
    ap.add_argument("--photos", help="the b76 research refs folder (commons/img and raiders/*)")
    ap.add_argument("--colour-lighting", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if args.photos:
        doc = photos_check(args.photos)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(doc, indent=1) + "\n")
        for key, row in doc["commons"].items():
            print(key, row.get("date"), row.get("note"), row.get("median"), "luma", row.get("luma"), "R/G", row.get("r_over_g"),
                  "B/G", row.get("b_over_g"), "hue", row.get("hue"))
        print("raiders.com", doc["raiders"]["photos"], "photos; field-dominant:", doc["raiders"]["summary"])
        return 0
    if not args.bundles:
        ap.error("--bundles or --photos is required")
    doc = check(args.bundles, colour_settings_from(args.colour_lighting))
    text = json.dumps(doc, indent=1) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    for name, row in doc["bundles"].items():
        print(name, row["rig"], "map", row["map_mean"], "draws", row["field_on_screen"],
              "luma", row["field_on_screen_luma"], "target", row["target"], "apron", row["apron_on_screen"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
