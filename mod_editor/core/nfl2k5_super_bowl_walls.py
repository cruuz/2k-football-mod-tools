"""Super Bowl event walls on the dedicated Anniversary stadium aliases (N06).

The alias compiler copies each venue's non-field scenes from its source, so a Super Bowl moment showed the host
team's slogans, banners and boards (Vikings SKOL walls in Super Bowl LII, Colts walls in XLVI). For the Super Bowl
rows this pass repaints only the listed temporary surfaces of the stadium scene with authored event art. Permanent
venue signs, geometry, material bindings and every other texture keep their bytes. The stadium scene is refit into
its existing compressed span, so the bundle keeps its size and every other chunk, and a native repair can write the
same span in place. Regular venue resources are never touched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data/nfl2k5_super_bowl_walls"
SCHEMA = "nfl2k5_super_bowl_walls/v1"
ALPHA_MODES = ("opaque", "source", "art")


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
        require(len(raw) < 256 * 1024, "Super Bowl wall manifest is too large")
        doc = json.loads(raw)
        require(doc.get("schema") == SCHEMA, "foreign Super Bowl wall manifest")
        rows = [r["row"] for r in doc["rows"]]
        require(len(rows) == len(set(rows)) and all(1 <= r <= 51 for r in rows), "Super Bowl wall rows")
        require(not set(rows) & set(doc.get("held_rows", ())), "a held row carries wall art")
        for r in doc["rows"]:
            names = [t["material"] for t in r["textures"]]
            require(len(names) == len(set(names)) and names, f"row {r['row']}: wall materials")
            for t in r["textures"]:
                require(t["alpha"] in ALPHA_MODES and len(t["size"]) == 2, f"row {r['row']}: {t['material']} entry")
                for box in t.get("areas", ()):
                    require(len(box) == 4 and 0 <= box[0] < box[2] <= t["size"][0]
                            and 0 <= box[1] < box[3] <= t["size"][1], f"row {r['row']}: {t['material']} area {box}")
        _MANIFEST = doc
    return _MANIFEST


def entry(row):
    """The manifest row for an Anniversary physical row, or None for a row without event walls."""
    found = [r for r in manifest()["rows"] if r["row"] == row]
    return found[0] if found else None


def art(texture):
    from PIL import Image
    import numpy as np
    path = (ART / texture["file"]).resolve()
    require(path.is_relative_to(ART.resolve()), "wall art path escapes its folder")
    raw = path.read_bytes()
    require(len(raw) < 1024 * 1024 and sha(raw) == texture["sha256"], f"{texture['material']}: wall art hash differs")
    with Image.open(path) as im:
        require(list(im.size) == texture["size"], f"{texture['material']}: wall art dimensions differ")
        return np.asarray(im.convert("RGBA")).copy()


def _stadium_chunk(bundle):
    from . import nfl2k5_modern_metlife as mm
    tx = mm._tools()[0]
    found = []
    for chunk in tx.parse_chunks(bundle, allow_trailing=True):
        if chunk.kind == "SCNE":
            rec, decoded = mm._scene(bundle, chunk)
            if rec.get("name") == "stadium":
                found.append((chunk, rec, decoded))
    require(len(found) == 1, "venue resource lacks a single stadium scene")
    return found[0]


def area_mask(texture, width, height):
    """Boolean (height, width) mask of the painted texels: the listed areas, or the whole texture."""
    import numpy as np
    mask = np.zeros((height, width), bool)
    boxes = texture.get("areas") or [[0, 0] + list(texture["size"])]
    sx, sy = width / texture["size"][0], height / texture["size"][1]
    for x0, y0, x1, y1 in boxes:
        mask[int(y0 * sy):int(y1 * sy), int(x0 * sx):int(x1 * sx)] = True
    return mask


def target(decoded, rec, r, texture):
    """(RGBA the surface should carry, resized) from its art, its alpha mode and the disc texels it keeps."""
    from . import nfl2k5_modern_venues_2026 as mv
    from PIL import Image
    import numpy as np
    width, height = int(r["width"]), int(r["height"])
    rgba = art(texture)
    resized = rgba.shape[:2] != (height, width)
    if resized:
        rgba = np.asarray(Image.fromarray(rgba).resize((width, height), Image.Resampling.LANCZOS)).copy()
    current = mv.read_texture(decoded, rec, r)
    if texture["alpha"] == "source":
        rgba[..., 3] = np.where(current[..., 3] >= 128, 255, 0).astype(np.uint8)
    elif texture["alpha"] == "art":
        rgba[..., 3] = np.where(rgba[..., 3] >= 128, 255, 0).astype(np.uint8)
    else:
        rgba[..., 3] = 255
    if texture.get("areas"):
        keep = ~area_mask(texture, width, height)
        rgba[keep] = current[keep]
    return rgba, resized


def already_painted(decoded, rec, row_entry):
    """True when every listed surface already shows its art (within quantisation error) with the expected cutout.
    Surfaces that keep disc texels outside their areas cannot be re-quantised to identical bytes, so a replay is
    recognised here instead of by byte equality."""
    from . import nfl2k5_modern_venues_2026 as mv
    import numpy as np
    rows = mv.p8_rows(rec)
    materials = mv.rows_by_material(rec)
    for texture in row_entry["textures"]:
        if texture["material"] not in materials:
            return False
        r = rows[materials[texture["material"]]]
        want, _ = target(decoded, rec, r, texture)
        have = mv.read_texture(decoded, rec, r)
        mask = area_mask(texture, int(r["width"]), int(r["height"])) & (want[..., 3] >= 128)
        if not np.array_equal(have[..., 3] >= 128, want[..., 3] >= 128):
            return False
        if mask.any() and float(np.abs(have[mask][:, :3].astype(int) - want[mask][:, :3].astype(int)).mean()) > 6.0:
            return False
    return True


def painted(decoded, rec, row_entry, cap=256):
    """(edited decoded scene, texture receipts) with every listed surface painted from its authored art.

    ``alpha: source`` keeps the disc texture's own cutout (the crowd banners' cloth outlines), ``art`` uses the
    authored cutout and ``opaque`` fills the texture. Cutouts are snapped to fully opaque or clear. A surface with
    ``areas`` keeps the disc's texels outside them.
    """
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    rows = mv.p8_rows(rec)
    materials = mv.rows_by_material(rec)
    system = int(rec["system_bytes"])
    edited = bytearray(decoded)
    receipts = []
    done = set()
    for texture in row_entry["textures"]:
        require(texture["material"] in materials, f"stadium scene lacks {texture['material']}")
        index = materials[texture["material"]]
        require(index not in done, f"{texture['material']} shares a texture with another listed surface")
        done.add(index)
        r = rows[index]
        width, height = int(r["width"]), int(r["height"])
        rgba, resized = target(decoded, rec, r, texture)
        colours = mm.write_p8(edited, system, r, rgba, cap)
        receipts.append(dict(material=texture["material"], texture=index, size=[width, height],
                             alpha=texture["alpha"], palette_entries=colours, resized=resized,
                             pixel_offset=int(r["pixel_offset"]), palette_offset=int(r["palette_offset"])))
    return edited, receipts


def texture_bytes(decoded, rec, indices):
    """{texture index: sha256 of its pixel chain and palette} for the comparison receipts."""
    from . import nfl2k5_modern_venues_2026 as mv
    rows = mv.p8_rows(rec)
    system = int(rec["system_bytes"])
    out = {}
    for index in indices:
        r = rows[index]
        start, end = system + int(r["pixel_offset"]), system + int(r["palette_offset"]) + 1024
        out[str(index)] = sha(bytes(decoded[start:end]))
    return out


def apply(bundle, row):
    """(bundle, receipt) with the row's event walls; rows without event walls return (bundle, None) unchanged."""
    from . import nfl2k5_modern_metlife as mm
    row_entry = entry(row)
    if row_entry is None:
        return bundle, None
    tx = mm._tools()[0]
    chunk, rec, decoded = _stadium_chunk(bundle)
    span = mm.scene_span(bundle, chunk)
    if already_painted(decoded, rec, row_entry):
        return bundle, dict(row=row, event=row_entry["event"], already_applied=True, written=False,
                            stadium_offset=chunk.offset, stadium_size=len(span))
    attempts = []
    for cap in mm.PALETTE_CAPS:
        edited, textures = painted(decoded, rec, row_entry, cap)
        if bytes(edited) == decoded:
            return bundle, dict(row=row, event=row_entry["event"], already_applied=True, written=False,
                                stadium_offset=chunk.offset, stadium_size=len(span), textures=textures)
        try:
            rebuilt, info = mm.fit_span(span, bytes(edited))
        except (tx.TxtrError, mm.ModernMetLifeError) as exc:
            attempts.append(f"{cap} colours: {exc}")
            continue
        back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
        require(back == bytes(edited) and len(rebuilt) == len(span), f"row {row}: stadium refit read-back differs")
        result = bundle[:chunk.offset] + rebuilt + bundle[chunk.offset + len(span):]
        _check_scope(decoded, bytes(edited), rec, textures)
        return result, dict(row=row, event=row_entry["event"], already_applied=False, written=True,
                            palette_cap=cap, fit_attempts=attempts, stadium_offset=chunk.offset,
                            stadium_size=len(span), stadium_before=sha(span), stadium_after=sha(rebuilt),
                            decoded_before=sha(decoded), decoded_after=sha(bytes(edited)),
                            textures=textures, fit=info, geometry_and_other_textures_identical=True)
    raise ValueError(f"row {row}: event walls do not fit the stadium span: " + " | ".join(attempts))


def _check_scope(decoded, edited, rec, textures):
    """Every changed decoded byte lies in a listed texture's pixel chain or palette."""
    system = int(rec["system_bytes"])
    allowed = [(system + t["pixel_offset"], system + t["palette_offset"] + 1024) for t in textures]
    protected = bytearray(edited)
    for start, end in allowed:
        protected[start:end] = decoded[start:end]
    require(bytes(protected) == decoded, "event walls changed bytes outside their textures")
