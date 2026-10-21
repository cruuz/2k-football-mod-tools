"""Super Bowl field marks on the 30s and 25s (sb1): the event logo, the period NFL shield or the two clubs' marks,
placed where the real game painted them, on the dedicated Anniversary fields.

Why a new step. The Anniversary fields are built from the retail period field (``s25``), whose overlay shape has two
square quads on each 30-yard line, ``AFC_shield`` and ``NFC_shield`` (128 x 128 textures). The executable hides
both (material flag bit 0, 0x9C6E1..0x9C7CD) unless FUN_00133a70 reports a conference title week, and hides
``playoff_logo`` (the sideline strips) unless the game mode word 0xE5FF80 is 6. In the Anniversary mode (8) every
mark the field carried away from midfield was therefore invisible, which is why the Super Bowl XLII moment showed
no XLII logo.

What this step does, on the Super Bowl rows only (the 17 rows in ``data/nfl2k5_super_bowl_fields/manifest.json``):

* renames the two materials to names the executable never looks up (``AFC_shield`` -> ``era_flankA``,
  ``NFC_shield`` -> ``era_flankN``, equal UTF-16 length, so every offset stays), which leaves them visible (the file
  flag word 0x80000000 has bit 0 clear);
* paints their 128 x 128 textures with the game's flank marks;
* moves their eight vertices each (positions only; UVs, triangles and descriptors keep their bytes) so each mark sits
  centred across the field on the real yard line at its real size, measured on the reference diagrams. A flank kind
  of ``event`` or ``shield`` shows the same mark on both sides (``era_flankA``; ``era_flankN`` keeps its retail name
  and stays hidden). A ``team`` flank shows each club on the side of its own end zone: ``era_flankA`` on the south
  (+z) 30, ``era_flankN`` on the north (-z) 30, and the other quad of each material collapses to a point.

Sources of the marks. ``event``: the user's ``super_bowl/<NUMERALS>.png`` from the optional Super Bowl logos folder
(never shipped), else the authored mark shipped here (drawn by ``tools/nfl2k5_super_bowl_marks_art.py`` from
geometry, in the event's design system). ``shield``: the season's NFL shield (the period shield read from the
user's retail disc before 2008, the mod's official 2008 shield after). ``team``: ``teams/<CODE>_<SEASON>.png`` or
``teams/<CODE>.png`` from the folder, else the authored club mark shipped here (the mod's own logo where it is the
season's, else a club roundel).

Regular venue resources and every other material, texture and vertex keep their bytes. EXPERIMENTAL and UNWITNESSED in
game unless a report says otherwise.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data/nfl2k5_super_bowl_fields"
SCHEMA = "nfl2k5_super_bowl_fields/v1"
YARD_M = 0.9144
#: equal-length names the executable never looks up (it hides AFC_shield / NFC_shield outside a title week)
RENAMES = {"AFC_shield": "era_flankA", "NFC_shield": "era_flankN"}
FLANK_KINDS = ("event", "shield", "team")
OVERLAY_SHAPE = "D_graphic_overlays"
#: transparent texels kept round a mark so the mip chain never bleeds its edge
MARGIN = 3
TEXTURE = 128
#: a real flank mark is never larger than this (yards along x across); the box keeps a user's odd image sane
MAX_BOX_YD = (18.0, 14.0)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


_MANIFEST = None


def manifest():
    global _MANIFEST
    if _MANIFEST is None:
        raw = (ART / "manifest.json").read_bytes()
        require(len(raw) < 256 * 1024, "Super Bowl field manifest is too large")
        doc = json.loads(raw)
        require(doc.get("schema") == SCHEMA, "foreign Super Bowl field manifest")
        rows = [r["row"] for r in doc["rows"]]
        require(len(rows) == len(set(rows)) and all(1 <= r <= 51 for r in rows), "Super Bowl field rows")
        for r in doc["rows"]:
            f = r["flank"]
            require(f["kind"] in FLANK_KINDS, f"row {r['row']}: flank kind")
            require(0 < f["from_mid_yd"] < 45, f"row {r['row']}: flank yard line")
            along, across = f["box_yd"]
            require(0 < along <= MAX_BOX_YD[0] and 0 < across <= MAX_BOX_YD[1], f"row {r['row']}: flank box")
            if f["kind"] == "team":
                require(set(f["teams"]) == {"N", "S"}, f"row {r['row']}: team flank sides")
            for key in authored_keys(r):
                require(key in doc["marks"], f"row {r['row']}: authored mark {key} missing")
        _MANIFEST = doc
    return _MANIFEST


def entry(row):
    found = [r for r in manifest()["rows"] if r["row"] == row]
    return found[0] if found else None


def authored_keys(r):
    f = r["flank"]
    if f["kind"] == "event":
        return [r["event"]]
    if f["kind"] == "team":
        return [f"{f['teams'][side]}_{r['season']}" for side in ("N", "S")]
    return []


def authored(key):
    """RGBA of an authored mark shipped with the Studio, pinned by its manifest hash."""
    from PIL import Image
    import numpy as np
    item = manifest()["marks"][key]
    path = (ART / item["file"]).resolve()
    require(path.is_relative_to(ART.resolve()), "mark path escapes its folder")
    raw = path.read_bytes()
    require(len(raw) < 2 * 1024 * 1024 and sha(raw) == item["sha256"], f"{item['file']}: mark hash differs")
    with Image.open(path) as im:
        require(list(im.size) == item["size"], f"{item['file']}: mark dimensions differ")
        return np.asarray(im.convert("RGBA")).copy()


def sources(r, marks):
    """{side or 'both': (RGBA, receipt)} of the row's flank marks (``marks`` is a nfl2k5_super_bowl_walls.Marks)."""
    f = r["flank"]
    if f["kind"] == "event":
        rgba, origin, note = marks.user("event", r["event"]) if marks is not None else (None, "authored", None)
        if rgba is None:
            return {"both": (authored(r["event"]), dict(kind="event", key=r["event"], source="authored", note=note))}
        return {"both": (rgba, dict(kind="event", key=r["event"], source=origin, note=note))}
    if f["kind"] == "shield":
        require(marks is not None, "the shield flank needs the build's marks")
        rgba, origin = marks.shield(r["season"])
        return {"both": (rgba, dict(kind="shield", key="NFL", source=origin))}
    out = {}
    for side in ("N", "S"):
        code = f["teams"][side]
        rgba, origin, note = (marks.user("team", code, r["season"]) if marks is not None
                              else (None, "authored", None))
        key = f"{code}_{r['season']}"
        if rgba is None:
            out[side] = (authored(key), dict(kind="team", key=code, side=side, source="authored", note=note))
        else:
            out[side] = (rgba, dict(kind="team", key=code, side=side, source=origin, note=note))
    return out


def trim(rgba):
    import numpy as np
    ys, xs = np.nonzero(rgba[..., 3] > 8)
    require(len(ys) > 0, "the flank mark is empty")
    return np.ascontiguousarray(rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1])


def fitted_box(mark, box_yd):
    """(along, across) in yards: the mark's aspect fitted inside the row's measured box."""
    h, w = mark.shape[:2]
    along, across = box_yd
    if w * across >= h * along:
        return along, along * h / w
    return across * w / h, across


def texture(mark):
    """The 128 x 128 texture of a trimmed mark: stretched to fill the texture inside a clear margin, so the quad
    (sized to the mark's own aspect) shows it undistorted. Exact integer resampling (the walls' own)."""
    import numpy as np
    from . import nfl2k5_super_bowl_walls as walls
    inner = TEXTURE - 2 * MARGIN
    placed = walls.resample(walls.defringe(mark), inner, inner)
    out = np.zeros((TEXTURE, TEXTURE, 4), np.uint8)
    out[MARGIN:MARGIN + inner, MARGIN:MARGIN + inner] = placed
    out[out[..., 3] == 0, :3] = 0
    return out


def _quads(rec, decoded, shape, material):
    """[[vertex index x4]] of a material's quads on the overlay shape, in vertex order."""
    from . import nfl2k5_scne_builder as sb
    idx = set()
    for sm in rec["submeshes"]:
        if sm["shape_index"] != shape["index"] or sm["material_name"] != material:
            continue
        words = bytes(decoded[sm["command_offset"]:sm["command_offset"] + 4 * sm["primary_command_word_count"]])
        for _mode, ix in sb.decode_words(words):
            idx.update(ix)
    idx = sorted(idx)
    require(len(idx) == 8, f"{material}: expected two quads on the overlay shape, found {len(idx)} vertices")
    return [idx[:4], idx[4:]]


def _stream(shape, index):
    found = [v for v in shape["vertex_streams"] if v["stream_index"] == index]
    require(len(found) == 1, f"overlay shape lacks vertex stream {index}")
    return found[0]


def place_single(out, rec, decoded, material, along, across, centre=None):
    """Resize a material's one quad round its own centre, or round ``centre`` (x, z metres); returns the changed
    byte ranges."""
    shape = [s for s in rec["shapes"] if s["name"] == OVERLAY_SHAPE][0]
    st0, st1 = _stream(shape, 0), _stream(shape, 1)
    su, sv, ou, ov = struct.unpack_from("<4f", decoded, shape["record_offset"] + 0x30)
    from . import nfl2k5_scne_builder as sb
    idx = set()
    for sm in rec["submeshes"]:
        if sm["shape_index"] == shape["index"] and sm["material_name"] == material:
            words = bytes(decoded[sm["command_offset"]:sm["command_offset"] + 4 * sm["primary_command_word_count"]])
            for _mode, ix in sb.decode_words(words):
                idx.update(ix)
    idx = sorted(idx)
    require(len(idx) == 4, f"{material}: expected one quad, found {len(idx)} vertices")
    pts = [struct.unpack_from("<3f", decoded, st0["offset"] + st0["stride"] * i) for i in idx]
    cx, cz = sum(p[0] for p in pts) / 4, sum(p[2] for p in pts) / 4
    if centre is not None:
        cx, cz = centre[0] * 100.0, centre[1] * 100.0
    ranges = []
    for i, (x, y, z) in zip(idx, pts):
        qu, qv = struct.unpack_from("<2h", decoded, st1["offset"] + st1["stride"] * i + 4)
        u, v = round(qu / 32767.0 * su + ou), round(qv / 32767.0 * sv + ov)
        require(u in (0, 1) and v in (0, 1), f"{material}: quad UVs are not a unit square")
        at = st0["offset"] + st0["stride"] * i
        struct.pack_into("<3f", out, at, cx + (v - 0.5) * across * 100.0, y, cz - (u - 0.5) * along * 100.0)
        ranges.append((at, 12))
    return ranges


def place(out, rec, decoded, material, placements):
    """Move a material's two quads: ``placements`` is [(centre z metres or None to collapse, along m, across m)]
    in the quads' order; the side of each quad is read from its own z. Returns the changed byte ranges."""
    shape = [s for s in rec["shapes"] if s["name"] == OVERLAY_SHAPE]
    require(len(shape) == 1, "the field has no single overlay shape")
    shape = shape[0]
    st0, st1 = _stream(shape, 0), _stream(shape, 1)
    require(st0["stride"] >= 12 and st1["stride"] >= 8, "overlay vertex strides")
    su, sv, ou, ov = struct.unpack_from("<4f", decoded, shape["record_offset"] + 0x30)
    ranges = []
    quads = _quads(rec, decoded, shape, material)
    by_side = {}
    for quad in quads:
        z = sum(struct.unpack_from("<3f", decoded, st0["offset"] + st0["stride"] * i)[2] for i in quad) / 4
        require(abs(z) > 100, f"{material}: a quad sits on midfield")
        by_side["S" if z > 0 else "N"] = quad
    require(set(by_side) == {"N", "S"}, f"{material}: quads are not one per side")
    for side, (centre_yd, along, across) in placements.items():
        for i in by_side[side]:
            at = st0["offset"] + st0["stride"] * i
            x, y, z = struct.unpack_from("<3f", decoded, at)
            if centre_yd is None:
                cz = struct.unpack_from("<3f", decoded, st0["offset"] + st0["stride"] * by_side[side][0])[2]
                nx, nz = 0.0, cz
            else:
                qu, qv = struct.unpack_from("<2h", decoded, st1["offset"] + st1["stride"] * i + 4)
                u = round(qu / 32767.0 * su + ou)
                v = round(qv / 32767.0 * sv + ov)
                require(u in (0, 1) and v in (0, 1), f"{material}: overlay quad UVs are not a unit square")
                cz = (1 if side == "S" else -1) * centre_yd * YARD_M * 100.0
                nx = (v - 0.5) * across * 100.0
                nz = cz - (u - 0.5) * along * 100.0
            struct.pack_into("<3f", out, at, nx, y, nz)
            ranges.append((at, 12))
    return ranges


def rename(out, rec, names, table=None):
    """Rename materials in place (equal UTF-16 length); returns the changed byte ranges."""
    by_name = {m["name"]: m for m in rec["materials"]}
    ranges = []
    for before in names:
        after = (table or RENAMES)[before]
        require(before in by_name, f"the field lacks {before}")
        start = by_name[before]["name_target"]
        source, target = (before + "\0").encode("utf-16le"), (after + "\0").encode("utf-16le")
        require(len(source) == len(target) and bytes(out[start:start + len(source)]) == source,
                f"unexpected {before} material string")
        out[start:start + len(target)] = target
        ranges.append((start, len(target)))
    return ranges


def apply_field(out, rec, decoded, row, marks, *, spec=None):
    """Paint and place the row's flank marks into the decoded field ``out`` (a bytearray copy of ``decoded``).

    ``spec`` replaces the manifest row (a franchise Super Bowl host passes its own). Returns (texture indices
    written, extra changed byte ranges, receipt) or (None, (), None) for a row without flank marks."""
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    r = spec if spec is not None else entry(row)
    if r is None:
        return None, (), None
    names = {m["name"] for m in rec["materials"]}
    require(set(RENAMES) <= names and not set(RENAMES.values()) & names, "the field's flank materials differ")
    rows, materials = mv.p8_rows(rec), mv.rows_by_material(rec)
    f = r["flank"]
    marks_by_side = sources(r, marks)
    textures, ranges, slots = [], [], []

    def paint(material, rgba):
        t = rows[materials[material]]
        require((int(t["width"]), int(t["height"])) == (TEXTURE, TEXTURE), f"{material}: texture is not 128 x 128")
        mm.write_p8(out, rec["system_bytes"], t, rgba, 256)
        textures.append(materials[material])

    def size_of(mark):
        along_yd, across_yd = fitted_box(mark, f["box_yd"])
        scale = TEXTURE / (TEXTURE - 2 * MARGIN)
        return along_yd * YARD_M * scale, across_yd * YARD_M * scale, along_yd, across_yd

    if f["kind"] in ("event", "shield"):
        mark, receipt = marks_by_side["both"]
        mark = trim(mark)
        along, across, a_yd, c_yd = size_of(mark)
        paint("AFC_shield", texture(mark))
        ranges += place(out, rec, decoded, "AFC_shield", {s: (f["from_mid_yd"], along, across) for s in "NS"})
        ranges += rename(out, rec, ["AFC_shield"])
        slots.append(dict(receipt, material=RENAMES["AFC_shield"], sides="NS", along_yd=round(a_yd, 2),
                          across_yd=round(c_yd, 2)))
    else:
        for material, side, other in (("AFC_shield", "S", "N"), ("NFC_shield", "N", "S")):
            mark, receipt = marks_by_side[side]
            mark = trim(mark)
            along, across, a_yd, c_yd = size_of(mark)
            paint(material, texture(mark))
            ranges += place(out, rec, decoded, material, {side: (f["from_mid_yd"], along, across),
                                                          other: (None, 0.0, 0.0)})
            slots.append(dict(receipt, material=RENAMES[material], sides=side, along_yd=round(a_yd, 2),
                              across_yd=round(c_yd, 2)))
        ranges += rename(out, rec, ["AFC_shield", "NFC_shield"])
    return textures, ranges, dict(row=row, event=r["event"], flank=f["kind"], from_mid_yd=f["from_mid_yd"],
                                  slots=slots)


def user_art_lines(receipts):
    """Build-log lines: the field flank marks filled from the user's folder."""
    filled = {}
    for rec in receipts:
        for s in rec.get("slots", ()):
            if s["source"] == "user_art":
                filled.setdefault(s.get("note") or s["key"], set()).add(rec["event"])
    if not filled:
        return ["Super Bowl fields: the flank marks use the authored art"]
    return ["Super Bowl fields: flank marks filled from your folder: " + "; ".join(
        f"{name} ({', '.join(sorted(events))})" for name, events in sorted(filled.items()))]
