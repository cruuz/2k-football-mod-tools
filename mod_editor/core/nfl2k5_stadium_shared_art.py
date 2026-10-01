"""Reviewed residual sponsors and plain-type event field logos for the u4 venue-art pass (and for SoFi's neutral s40,
through the model fan step)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_stadium_shared_art"
ART_ROOT = DATA / "venues"
TABLE_PATH = DATA / "special_venues.json"
EVENT_PATH = DATA / "event_fields.json"
# The board kit's venues (tiers 1 and 2; tier 3 added s02, s06, s09 and s21, st3): their venue art lives in u4's table.
EXCLUDED = frozenset(("s02", "s04", "s06", "s08", "s09", "s13", "s17", "s21", "s22", "s26", "s27", "s29", "s30", "s37"))
# Neutral slots that a model writer builds. SoFi's Super Bowl LXI venue at s40 has no venue-table row, and the
# venue-art pass never writes it. Its retained fan cloth takes its residual item from this catalog through the model
# fan step (nfl2k5_model_fan_art.neutral_plan) when the SoFi writer builds s40 (st3, main's call, 2026-09-29).
MODEL_NEUTRAL = frozenset(("s40",))


@lru_cache(maxsize=1)
def special_venues():
    doc = json.loads(TABLE_PATH.read_text())
    if doc.get("schema") != "nfl2k5_stadium_shared_art_special_venues/v1":
        raise ValueError("unsupported shared stadium-art table")
    return doc["venues"]


@lru_cache(maxsize=64)
def items(prefix):
    from . import nfl2k5_modern_venues_2026 as mv
    path = ART_ROOT / prefix / "manifest.json"
    if not path.is_file():
        expected = {r["venue"] for r in json.loads((DATA / "design.json").read_text())["textures"]}
        mv.require(prefix not in expected, f"{prefix}: shared-art manifest is missing")
        return ()
    mv.require(prefix not in EXCLUDED, f"shared art must not own board-kit venue {prefix}")
    doc = json.loads(path.read_text())
    mv.require(doc.get("schema") == mv.ART_SCHEMA and doc.get("venue_prefix") == prefix,
               f"{path}: unsupported manifest")
    out, seen = [], set()
    for raw in doc["items"]:
        key = raw["material"]
        sponsor = raw["scene"] == "stadium" and raw["kind"] == "sponsor"
        event = (raw["scene"] == "field" and raw["kind"] == "field-logo"
                 and key in special_venues().get(prefix, {}).get("field_logos", {}))
        mv.require((sponsor or event) and raw["format"] == "P8" and raw["layer"] == "full",
                   f"{path}: shared art must be reviewed full-layer P8 sponsors or event field logos")
        identity = (raw["scene"], key)
        mv.require(identity not in seen, f"{path}: duplicate {identity}")
        seen.add(identity)
        file = (path.parent / raw["file"]).resolve()
        mv.require(file.is_relative_to(path.parent.resolve()), f"{path}: art escapes its folder")
        data = file.read_bytes()
        mv.require(mv.sha(data) == raw["sha256"], f"{file}: manifest hash differs")
        rgba = mv._rgba(data)
        w, h = raw["size"]
        mv.require(rgba.shape == (h, w, 4) and mv._rects_ok(raw["rects"], w, h),
                   f"{file}: bad dimensions or rectangles")
        master = (path.parent / raw["master"]).resolve()
        mv.require(master.is_relative_to(path.parent.resolve()), f"{path}: master escapes its folder")
        mv.require(mv.sha(master.read_bytes()) == raw["master_sha256"], f"{master}: master hash differs")
        if event:
            target = special_venues()[prefix]["field_logos"][key]
            mv.require(raw["size"] == target["size"] and raw["rects"] == [[0, 0, w, h]],
                       f"{path}: event logos must replace their complete native texture")
        out.append(dict(scene=raw["scene"], key=key, layer="full", size=[w,h], rgba=rgba,
                        master=str(master), rects=raw["rects"], sha256=raw["sha256"],
                        source="shared_art", kind=raw["kind"]))
    return tuple(out)
