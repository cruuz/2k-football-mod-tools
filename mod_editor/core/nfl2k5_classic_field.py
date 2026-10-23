"""The Seamen's field: authored end zones and midfield anchor on the unused ESPN Stadium (s48) bundles.

ESPN Stadium is a neutral venue no NFL team calls home; the classic Seamen bind to it (stadium asset 48) and this
stage replaces only its field scene's six end-zone textures and its centre logo. The stadium, crowd, walls and
weather looks stay retail. The art is authored from the video's teal end zones and midfield anchor (episode 1
7:25); the N strip is mirrored for S exactly as the retail venue lays its two ends out.
"""
from __future__ import annotations

from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_classic_teams/field"
VENUE = "s48"
BUNDLES = tuple(f"{VENUE}{tod}{weather}.iff" for tod in "dan" for weather in "drs")
CAPS = (256, 128, 96, 64, 48, 32)


class ClassicFieldError(ValueError):
    """A bundle is not the retail s48 layout or the field does not fit its span."""


def require(ok, message):
    if not ok:
        raise ClassicFieldError(message)


def _art():
    from PIL import Image
    out = {}
    for name in ("endzone_N", "endzone_S", "center_logo"):
        path = DATA / f"{name}.png"
        require(path.is_file(), f"missing field art {path}")
        out[name] = Image.open(path).convert("RGBA")
    require(out["endzone_N"].size == (768, 128) and out["endzone_S"].size == (768, 128), "end-zone art size")
    require(out["center_logo"].size == (256, 256), "centre-logo art size")
    return out


def _paint(bundle, art, cap):
    import numpy as np
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    scenes = mm.bundle_scenes(bundle)
    require("field" in scenes, "venue bundle lacks its field scene")
    chunk = scenes["field"]
    rec, decoded = mm._scene(bundle, chunk)
    rows, materials = mv.p8_rows(rec), mv.rows_by_material(rec)
    require({f"endzone_{end}_{part}" for end in "NS" for part in "LMR"}.issubset(materials), "field end zones missing")
    require("center_logo" in materials, "field centre logo missing")
    edited = bytearray(decoded)
    system = int(rec["system_bytes"])
    for end in "NS":
        strip = np.asarray(art[f"endzone_{end}"])
        for part_index, part in enumerate("LMR"):
            row = rows[materials[f"endzone_{end}_{part}"]]
            width, height = int(row["width"]), int(row["height"])
            piece = strip[:, part_index * 256:(part_index + 1) * 256]
            from PIL import Image
            piece = np.asarray(Image.fromarray(piece).resize((width, height), Image.BILINEAR))
            mm.write_p8(edited, system, row, piece, maximum=cap)
    row = rows[materials["center_logo"]]
    from PIL import Image
    logo = np.asarray(art["center_logo"].resize((int(row["width"]), int(row["height"])), Image.BILINEAR))
    mm.write_p8(edited, system, row, logo, maximum=cap)
    span = mm.scene_span(bundle, chunk)
    try:
        rebuilt, info = mm.fit_span(span, bytes(edited))
    except Exception as exc:  # noqa: BLE001 - the fitter raises TxtrError/ModernMetLifeError
        raise ClassicFieldError(f"{cap} colours: {exc}") from exc
    tx = mm._tools()[0]
    check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    require(check == bytes(edited), "field refit read-back differs")
    out = bytearray(bundle)
    out[chunk.offset:chunk.offset + len(span)] = rebuilt
    require(len(out) == len(bundle), "field bundle size changed")
    return bytes(out), dict(cap=cap, refit=info, field_chunk=[chunk.offset, len(span)])


_CACHE = {}


def authored(bundle, art=None):
    """(bundle bytes, receipt) with the Seamen field painted at the first palette cap that fits."""
    key = hashlib.sha256(bundle).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    art = art or _art()
    best = None
    for cap in CAPS:
        try:
            out, receipt = _paint(bundle, art, cap)
            receipt["sha256"] = hashlib.sha256(out).hexdigest()
            _CACHE[key] = (out, receipt)
            return out, receipt
        except ClassicFieldError as exc:
            best = str(exc)
    raise ClassicFieldError(best or "field art does not fit")


def _read(path, source):
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_music_archive as archive
    with archive.Disc(Path(path), descriptors=()) as disc, hs.Source(source) as src:
        target = hs.Target(disc)
        rows = {}
        for name in BUNDLES:
            require(target.has(name) and src.has(name), f"{name} missing from the build or the source")
            rows[name] = (target.get(name), src.get(name), target.outer(name))
    return rows


def status(path, source):
    """'applied' (all nine bundles equal the authored field), 'retail' (all nine are retail), else 'foreign'."""
    try:
        art = _art()
        rows = _read(path, source)
    except (ValueError, KeyError, IndexError, OSError):
        return "foreign"
    states = set()
    for name, (current, _retail, _outer) in rows.items():
        expected, _ = authored(current, art)
        states.add("applied" if current == expected else "retail")
    return states.pop() if len(states) == 1 else "foreign"


def edits(target, source, art=None):
    """({outer index: authored bundle}, receipt) for a disc whose bundles are retail or already authored."""
    art = art or _art()
    out, receipts = {}, {}
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_music_archive as archive
    with archive.Disc(Path(target), descriptors=()) as disc, hs.Source(source) as src:
        copy = hs.Target(disc)
        for name in BUNDLES:
            require(copy.has(name) and src.has(name), f"{name} missing from the build or the source")
            current = copy.get(name)
            expected, receipt = authored(current, art)
            if current != expected:
                out[copy.outer(name)] = expected
                receipts[name] = receipt
    return out, receipts
