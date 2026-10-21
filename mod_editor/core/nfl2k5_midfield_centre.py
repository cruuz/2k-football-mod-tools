"""Centre every field's midfield logo on the 50-yard line and the field's centre line (b777 ar1).

A field scene draws its midfield logo on a private four-vertex quad (material ``center_logo`` in the shape
``D_graphic_overlays``). Retail placed some of those quads off the middle of the field (the Titans' Nissan Stadium field
sits 1.55 m down the field from the 50), and the authored 2026 art is centred in its texture, so the logo drew off centre.
The field's own axes are x = 0 (the centre line between the hash marks) and z = 0 (the 50), in centimetres.

``measure`` finds the quad, maps the logo's ink (the alpha bounding box of the centre-logo texture) through the quad's UVs
to field coordinates, and reports how far the ink centre is from (0, 0), in centimetres and in texels of the logo texture.
``recentre`` moves exactly the four quad vertices (x and z only, eight floats) by that offset when it is more than
``TOLERANCE_TEXELS`` in either axis, so a logo within a texel of centre keeps its bytes. Nothing else in the scene changes:
not the texture, the UVs, the draw, or any other vertex; the shape bounds already cover the whole field.
"""
from __future__ import annotations

import struct

SHAPE, MATERIAL = "D_graphic_overlays", "center_logo"
#: the Anniversary aliases rename the material to ``era_midlogo`` (nfl2k5_espn25_fields.PERIOD_MATERIALS)
MATERIALS = (MATERIAL, "era_midlogo")
TOLERANCE_TEXELS = 1.0
ALPHA_INK = 16


class MidfieldError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise MidfieldError(message)


def _stream(shape, index):
    return next((v for v in shape["vertex_streams"] if v["stream_index"] == index), None)


def quad(rec, decoded):
    """None when the scene has no private flat four-vertex midfield quad, else {shape, ids, positions, uvs, at}: the four vertices of the
    ``center_logo`` draw with their float positions (x, z), signed-short UVs and the byte offset of each position."""
    from . import nfl2k5_scne_builder as builder
    shape = next((s for s in rec["shapes"] if s["name"] == SHAPE), None)
    if shape is None:
        return None
    used, others = set(), set()
    for sub in rec["submeshes"]:
        if sub["shape_index"] != shape["index"]:
            continue
        words = bytes(decoded[sub["command_offset"]:sub["command_offset"] + 4 * sub["primary_command_word_count"]])
        indices = {i for _mode, ix in builder.decode_words(words) for i in ix}
        (used if sub["material_name"] in MATERIALS else others).update(indices)
    if not used:
        return None
    if len(used) != 4 or used & others:
        return None  # a quad this module does not own (shared vertices): left exactly as it is
    s0, s1 = _stream(shape, 0), _stream(shape, 1)
    if s0 is None or s1 is None or s0["stride"] < 12 or s1["stride"] < 8:
        return None
    ids = sorted(used)
    at = [s0["offset"] + s0["stride"] * i for i in ids]
    positions = [struct.unpack_from("<3f", decoded, a) for a in at]
    uvs = [struct.unpack_from("<2h", decoded, s1["offset"] + s1["stride"] * i + 4) for i in ids]
    if not all(abs(p[1]) < 0.01 for p in positions):
        return None  # not flat on the field
    return dict(ids=ids, at=at, positions=[(p[0], p[2]) for p in positions], uvs=uvs)


def logo_row(rows, materials):
    """The P8 row of the centre-logo texture from ``rows`` ({index: row}) and ``materials`` ({name: index}), or None."""
    index = next((materials[m] for m in MATERIALS if m in materials), None)
    return rows.get(index) if index is not None else None


def ink_box(rgba):
    """(x0, y0, x1, y1) half-open pixel box of the visible ink of an RGBA texture, or None."""
    import numpy as np
    seen = rgba[..., 3] > ALPHA_INK
    if not seen.any():
        return None
    ys, xs = np.nonzero(seen)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _axes(q):
    """Least-squares x = a u + b v + c and z = d u + e v + f over the quad (UVs normalised so +-32767 is +-1)."""
    import numpy as np
    uv = np.array([(u / 32767.0, v / 32767.0, 1.0) for u, v in q["uvs"]])
    xs = np.array([p[0] for p in q["positions"]])
    zs = np.array([p[1] for p in q["positions"]])
    return np.linalg.lstsq(uv, xs, rcond=None)[0], np.linalg.lstsq(uv, zs, rcond=None)[0]


def measure(rec, decoded, texture):
    """The logo's offset from the middle of the field, or None when the scene has no midfield logo.

    ``texture`` is the centre-logo texture as RGBA rows (height, width, 4). A texture coordinate s in [-1, 1] covers the
    texture once ((s + 1) / 2), as the quad's +-0.998 UVs show: the logo is drawn once."""
    q = quad(rec, decoded)
    if q is None or texture is None:
        return None
    box = ink_box(texture)
    if box is None:
        return None
    height, width = texture.shape[:2]
    u = (box[0] + box[2]) / 2.0 / width * 2.0 - 1.0
    v = (box[1] + box[3]) / 2.0 / height * 2.0 - 1.0
    ax, az = _axes(q)
    x, z = float(ax @ (u, v, 1.0)), float(az @ (u, v, 1.0))
    extent_x = max(p[0] for p in q["positions"]) - min(p[0] for p in q["positions"])
    extent_z = max(p[1] for p in q["positions"]) - min(p[1] for p in q["positions"])
    texel = (extent_x / width, extent_z / height)
    centre = (sum(p[0] for p in q["positions"]) / 4.0, sum(p[1] for p in q["positions"]) / 4.0)
    return dict(ink_box=list(box), ink_offset_cm=(x, z), quad_centre_cm=centre, texel_cm=texel,
                offset_texels=(x / texel[0] if texel[0] else 0.0, z / texel[1] if texel[1] else 0.0),
                quad_extent_cm=(extent_x, extent_z), vertices=len(q["ids"]))


def needs_move(m, tolerance=TOLERANCE_TEXELS):
    # a quarter-texel margin: the ink box is measured in whole texels, so one texel exactly is "within a pixel"
    return m is not None and (abs(m["offset_texels"][0]) > tolerance + 0.25 or abs(m["offset_texels"][1]) > tolerance + 0.25)


def recentre(out, rec, decoded, texture, tolerance=TOLERANCE_TEXELS):
    """Move the quad so the logo's ink is centred on (0, 0), in place on the bytearray ``out`` (a copy of ``decoded``
    that other writers may already have edited). Returns (ranges, receipt): ``ranges`` is [(byte offset, size)] of the
    floats written (empty when the logo is within the tolerance); the receipt records the measurement either way."""
    m = measure(rec, decoded, texture)
    if m is None:
        return [], dict(state="no midfield logo")
    receipt = dict(state="centred" if not needs_move(m, tolerance) else "moved", tolerance_texels=tolerance,
                   before_ink_offset_cm=[round(v, 3) for v in m["ink_offset_cm"]],
                   before_offset_texels=[round(v, 2) for v in m["offset_texels"]],
                   quad_extent_cm=[round(v, 2) for v in m["quad_extent_cm"]])
    if not needs_move(m, tolerance):
        return [], receipt
    q = quad(rec, decoded)
    dx, dz = m["ink_offset_cm"]
    ranges = []
    for at, (x, z) in zip(q["at"], q["positions"]):
        struct.pack_into("<f", out, at, x - dx)
        struct.pack_into("<f", out, at + 8, z - dz)
        ranges += [(at, 4), (at + 8, 4)]
    after = measure(rec, bytes(out), texture)
    _require(abs(after["ink_offset_cm"][0]) < 0.01 and abs(after["ink_offset_cm"][1]) < 0.01,
             "the midfield logo is not centred after the move")
    receipt["after_ink_offset_cm"] = [round(v, 4) for v in after["ink_offset_cm"]]
    receipt["moved_cm"] = [round(-dx, 3), round(-dz, 3)]
    return ranges, receipt
