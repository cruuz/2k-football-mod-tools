"""SoFi crowd (u6): the Rams and Chargers superfans wear their 2026 colours (EXPERIMENTAL / UNWITNESSED).

The stadium's ``crowd`` material draws people from the per-venue crowd scenes: ``crowds23`` (Rams home) and ``crowds24``
(Chargers home), a warm and a cold set each (outers 2555, 2850 and 2556, 2851; PROVED OFFLINE). Their superfan atlases
carry the 2004 colours: the Rams fan's face paint is half St. Louis old gold and half navy under an old-gold horn
hat; the Chargers fan's face paint is navy with a gold and white bolt, under a hat of navy and gold card-suit panels.
This module moves those colours to 2026 on the user's own retail pixels (no retail pixels are committed): navy to Rams
royal #003594 or Chargers powder blue #0080C6, old gold to Rams sol #FFD100 or Chargers gold #FFC20E, keeping each
pixel's shading (skin, teeth and hair are left alone by hue and saturation). Each scene is refit inside its fixed
span with the retail wrapper, as Modern MetLife's superfans are.
"""
from __future__ import annotations

import colorsys
import hashlib

class _LazyNumpy:
    # b76 u6, as main's bb9448867 for the MetLife model: the SoFi model imports this module, and the Build panel imports the model for its
    # caption and help text, and both studios must open every page without numpy (tests/mod_editor/test_numpy_optional.py). numpy loads
    # on first use, when a model is built.
    def __getattr__(self, name):
        import numpy
        globals()["np"] = numpy
        return getattr(numpy, name)


np = _LazyNumpy()

from . import nfl2k5_modern_metlife as ml
from . import nfl2k5_scne_builder as sb

LABEL = "EXPERIMENTAL / UNWITNESSED"
#: outer -> (scene name, texture materials)
TARGETS = {
    2555: ("crowds23", ("heads23", "hats23")),
    2850: ("crowds23", ("heads23", "hats23")),
    2556: ("crowds24", ("heads24", "hats24")),
    2851: ("crowds24", ("heads24", "hats24")),
}
#: 2026 club colours (the NFL Record and Fact Book, as u7 and d4 used them): (blue, gold)
COLOURS = {"crowds23": ((0, 53, 148), (255, 209, 0)), "crowds24": ((0, 128, 198), (255, 194, 14))}


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def recolour(rgba, blue, gold):
    """Navy and old gold moved to the 2026 blue and gold with each pixel's own lightness; other hues untouched."""
    a = rgba.astype(np.float32) / 255.0
    rgb = a[..., :3]
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    d = np.maximum(mx - mn, 1e-6)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.where(mx == r, ((g - b) / d) % 6.0, np.where(mx == g, (b - r) / d + 2.0, (r - g) / d + 4.0)) * 60.0
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    navy = (hue > 195) & (hue < 255) & (sat > 0.25) & (mx > 0.08)
    goldish = (hue > 36) & (hue < 64) & (sat > 0.55) & (mx > 0.40)
    out = rgba.copy()
    for mask, target, ref in ((navy, blue, None), (goldish, gold, None)):
        th, ts, tv = colorsys.rgb_to_hsv(*(c / 255.0 for c in target))
        # keep the pixel's shading: its value relative to the class's brightest pixels maps onto the target value
        vals = mx[mask]
        if not vals.size:
            continue
        top = np.percentile(vals, 95)
        v = np.clip(mx / max(top, 1e-6) * tv, 0, 1)
        s = np.full_like(v, ts)
        h6 = (th * 6.0) % 6.0
        i = np.floor(h6)
        f = h6 - i
        p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
        choices = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
        k = int(i) % 6
        new = np.stack(choices[k], axis=-1)
        out[mask, :3] = np.clip(new[mask] * 255.0, 0, 255).astype(np.uint8)
    return out


def crowd_resource(data, outer):
    """(new resource bytes, receipt) for one retail crowd outer; same size, one scene refit in its span."""
    scene_name, materials = TARGETS[outer]
    blue, gold = COLOURS[scene_name]
    tx = ml._tools()[0]
    out = bytearray(data)
    receipt = None
    for chunk in tx.parse_chunks(data, allow_trailing=True):
        if chunk.kind != "SCNE":
            continue
        rec, dec = ml._scene(data, chunk)
        if rec.get("name") != scene_name:
            continue
        rows = ml.texture_rows(rec)
        edited = bytearray(dec)
        system = int(rec["system_bytes"])
        palettes = {}
        for material in materials:
            ml.require(material in rows, f"outer {outer}: {scene_name} has no {material} texture")
            current, _raw = ml.read_p8(edited, system, rows[material])
            palettes[material] = ml.write_p8(edited, system, rows[material], recolour(current, blue, gold))
        span = bytes(data[chunk.offset:chunk.offset + 32 + chunk.stored_size])
        try:
            rebuilt, _info = ml.fit_span(span, bytes(edited))
        except Exception:  # noqa: BLE001 - fall back to the builder's refit (scratch word at the in-place minimum)
            rebuilt, _info = sb.fixed_span_chunk("SCNE", bytes(edited), chunk.system_bytes, chunk.video_bytes, span)
        ml.require(len(rebuilt) == len(span), f"outer {outer}: refit escaped its span")
        back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
        ml.require(back == bytes(edited), f"outer {outer}: refit read-back differs")
        out[chunk.offset:chunk.offset + len(span)] = rebuilt
        receipt = dict(outer=outer, scene=scene_name, materials=list(materials), palette_entries=palettes,
                       offset=chunk.offset, size=len(span), before_sha256=sha(span), after_sha256=sha(rebuilt))
    ml.require(receipt is not None, f"outer {outer}: no {scene_name} scene")
    return bytes(out), receipt
