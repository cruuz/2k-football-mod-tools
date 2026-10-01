"""MetLife crowd (u5): the Giants and Jets superfans wear 2026 marks (EXPERIMENTAL / UNWITNESSED).

The stadium's ``crowd`` material draws people from the per-venue crowd scenes: ``crowds18`` (Giants home) and
``crowds19`` (Jets home), a warm and a cold set each (outers 2550, 2845 and 2551, 2846, PROVED OFFLINE). Their
superfan atlases carry 2004 marks: the Giants helmet shell has the 1976 GIANTS wordmark on both sides and the Jets
hard hat a 'jetfan GO JETS' crest. This module composites authored overlays over the user's own retail atlas
(``hats18``: Giants blue over each wordmark and the 2026 ny helmet logo; ``hats19``: the 2024 Jets logo on a white
panel), writes them into the retail P8 allocation and refits each scene inside its fixed span with the retail wrapper.
The overlays are drawn by ``tools/nfl2k5_metlife_model_art.py``; no retail pixels are committed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from . import nfl2k5_modern_metlife as ml
from . import nfl2k5_scne_builder as sb

LABEL = "EXPERIMENTAL / UNWITNESSED"
ART_DIR = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_metlife_model" / "art"
#: outer -> (scene name, texture material, overlay art)
TARGETS = {
    2550: ("crowds18", "hats18", "crowd_hats18.png"),
    2845: ("crowds18", "hats18", "crowd_hats18.png"),
    2551: ("crowds19", "hats19", "crowd_hats19.png"),
    2846: ("crowds19", "hats19", "crowd_hats19.png"),
}


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _overlay(name):
    from PIL import Image
    with Image.open(ART_DIR / name) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()


def crowd_resource(data, outer):
    """(new resource bytes, receipt) for one retail crowd outer; same size, one scene refit in its span."""
    scene_name, material, art = TARGETS[outer]
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
        ml.require(material in rows, f"outer {outer}: {scene_name} has no {material} texture")
        row = rows[material]
        edited = bytearray(dec)
        system = int(rec["system_bytes"])
        current, _raw = ml.read_p8(edited, system, row)
        painted = ml.composite_over(current, _overlay(art))
        colours = ml.write_p8(edited, system, row, painted)
        span = bytes(data[chunk.offset:chunk.offset + 32 + chunk.stored_size])
        try:
            rebuilt, info = ml.fit_span(span, bytes(edited))          # keeps the retail wrapper when it can
        except Exception:  # noqa: BLE001 - fall back to the builder's refit (scratch word at the in-place minimum)
            rebuilt, info = sb.fixed_span_chunk("SCNE", bytes(edited), chunk.system_bytes, chunk.video_bytes, span)
        ml.require(len(rebuilt) == len(span), f"outer {outer}: refit escaped its span")
        back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
        ml.require(back == bytes(edited), f"outer {outer}: refit read-back differs")
        out[chunk.offset:chunk.offset + len(span)] = rebuilt
        receipt = dict(outer=outer, scene=scene_name, material=material, art=art, palette_entries=colours,
                       scratch=ml._tools()[3].unpack_from(rebuilt, 0)[5],
                       offset=chunk.offset, size=len(span), before_sha256=sha(span), after_sha256=sha(rebuilt))
    ml.require(receipt is not None, f"outer {outer}: no {scene_name} scene")
    return bytes(out), receipt


def apply_lab_disc(disc):
    """Lab: rewrite the four crowd outers of a disc image in place (each must still be retail: the scene refits
    from the disc's own bytes, so a second run refuses on the changed atlas)."""
    receipts = []
    with ml._outer_image()(str(disc), writable=True) as archive:
        for outer in TARGETS:
            e = archive.entries[outer]
            data = archive.read(e.virtual_offset, e.size)
            new, rec = crowd_resource(data, outer)
            ml.require(len(new) == len(data), f"outer {outer}: size changed")
            archive.write(e.virtual_offset, new)
            ml.require(archive.read(e.virtual_offset, e.size) == new, f"outer {outer}: read-back differs")
            receipts.append(rec)
    return receipts
