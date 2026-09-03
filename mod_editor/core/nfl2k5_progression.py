"""NFL-shaped player development for franchise (data patch to the retail aging tables, xemu-only).

How retail NFL 2K5 develops a player (all found in ``default.xbe``; nothing here is random once a player
exists):

* Every offseason the Postseason step ``FUN_00247b40`` adds one to each active player's **years pro**
  (player+0x24 bits 8-12) and the Preseason step (``FUN_002480b0`` stage 7) runs the aging routine
  ``FUN_000e63f0(player, old_years, new_years)`` on every player.  For each of the 29 rating bytes it
  looks up the player's hidden **development archetype** — player+0x24 bit 7 (profile) and bits 4-6
  (sub-type), drawn once at generation — in the 162-row table at 0x4F27B0 (position, profile, sub ->
  ten curve indices) and applies ``rating += curve[new_years] - curve[old_years]`` (``FUN_000e5890``),
  clamped 0..100.  A curve is 21 signed bytes (years pro 0..20).  The ten curve tables sit at
  0x4F31D0..0x4F4CB0 (.rdata), one per rating family: speed/agility; strength/jumping/arm/kick power;
  stamina/durability; a hidden byte; consistency; read coverage + aggression; leadership/composure;
  pass accuracy/catch/kick accuracy; secure ball/break tackle/blocking/tackle; routes/pass rush/coverage.
* Rookies are rolled uniformly between a low and a high template per position (68 templates in the
  roster pack, ``FUN_000e6780``), then ``curve[0]`` is applied.  The archetype is drawn with the
  per-position weights at 0x521680 (162 rows of ``{position, profile, sub, weight}``; ``FUN_002be5b0``).

So the game already makes busts and gems: the same draft-day rating leads to different careers only
through the hidden archetype.  Retail curves are flat, though (about +2..+3 from rookie year to the
prime, then a slow slide), so nobody really develops and the draft-day rating is the career.

This patch keeps the mechanism and re-shapes the data:

* **growth**: every curve gains a ramp over years 1..5 (per family: physical +1..+3, technique and
  mental +5..+6), so a prime-age player sits well above his rookie self;
* **decline**: after a per-family age (years 9..12) each extra year subtracts more (speed fastest);
* **spread**: per position the archetypes with the most and the least growth get more weight and the
  middle ones less (``SPREAD`` = 35 %), so more prospects turn into stars or busts.  Per-position weight
  totals are preserved exactly (the draw is ``rand % total``).

Year 0 is never changed: draft-day ratings, the draft and the scouting screens are identical.
Everything is pattern-checked against the retail tables; the ``.rdata`` digest is recomputed.
Unverified at runtime.
"""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
CURVES_VA = 0x004F31D0
CURVES_SIZE = 0x004F4CB0 - CURVES_VA        # 6880
WEIGHTS_VA = 0x00521680
WEIGHT_ROWS = 162
WEIGHTS_SIZE = WEIGHT_ROWS * 8               # 1296
PROFILES_VA = 0x004F27B0                     # 162 rows x 16: position, profile, sub, 10 curve indices (read only)
CURVE_LEN = 21                               # years pro 0..20
YEARS_CAP = 20

# (family, table VA, curve count) -- the tables abut with a little padding each; the aging routine
# indexes them with row.byte[6 + family]*21.  The families below name the ratings each table drives.
TABLES = (
    ("speed_agility", 0x004F31D0, 42),
    ("strength_jumping_arm_kickpower", 0x004F3548, 41),
    ("stamina_durability", 0x004F38A8, 20),
    ("hidden_4f", 0x004F3A50, 14),
    ("consistency", 0x004F3B78, 16),
    ("read_coverage_aggression", 0x004F3CC8, 39),
    ("leadership_composure", 0x004F4000, 35),
    ("pass_accuracy_catch_kick_accuracy", 0x004F42E0, 42),
    ("secure_breaktackle_blocking_tackle", 0x004F4658, 42),
    ("routes_passrush_coverage", 0x004F49D0, 35),
)
# family -> (growth by year 5, extra decline per year after DECLINE_AFTER, decline starts after this year)
SHAPE = {
    "speed_agility": (1.0, 2.0, 9),
    "strength_jumping_arm_kickpower": (3.0, 1.0, 10),
    "stamina_durability": (1.0, 1.5, 9),
    "hidden_4f": (0.0, 0.0, 20),
    "consistency": (6.0, 0.5, 12),
    "read_coverage_aggression": (6.0, 0.5, 12),
    "leadership_composure": (5.0, 0.0, 20),
    "pass_accuracy_catch_kick_accuracy": (6.0, 0.5, 11),
    "secure_breaktackle_blocking_tackle": (5.0, 1.0, 10),
    "routes_passrush_coverage": (6.0, 1.0, 10),
}
GROWTH_YEARS = 5
SPREAD = 0.35
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")

_RETAIL_CURVES_Z = (
    "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"
)
_RETAIL_WEIGHTS_Z = (
    "eNpNk0ly5DAMBAkukkhxG8f8/62mUHlwH5yhVkYZLKJD+D7J/wZrYuQ5wbzEovcWLtGmGE3Et/wjlhn0poon3xmjmHjOXSx3iO6/"
    "onXx+JF5IvNEfP3HJloVj5/wnfm/iG+hi7ZEfMO3rDw7fvb8RzQTTz/OVMUzj7O8TgtTNH1v+F++E99KCoXzFhUpRr5PXTx+Yf4L"
    "/6Kfi/NenPfCv/Bv7vcm/yb/pn9n/ieW5fxO6bQhnvt1Jpi3ePzH82/ReD7zPMzjzFMsP07Dt7MPD/0/9OM8+/DQfyW/cr+V+Sv5"
    "lfutnLd6/hINnvkr+ZX7reQ3+mz008hv9N/os5HfPF++md5/8zfyG/fbyH/Zn5f5ndHEFMVzXmcpzm9/XuZ/2R9nyuL5fTlLPZus"
    "+Tv70Om/009n/s78A3/gD/yBP/AH/sSf+BN/4k/8ib/xN31u+tz0ufH3H9/wvz43fW763PS56XORv5hnMc9inkX+Yp8X+Yv8Rf4i"
    "f5G/2OdfahkMSg=="
)


class ProgressionError(ValueError):
    """The progression patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProgressionError(message)


def retail_curves() -> bytes:
    data = zlib.decompress(base64.b64decode(_RETAIL_CURVES_Z))
    _require(len(data) == CURVES_SIZE, "embedded retail curve tables have the wrong size")
    return data


def retail_weights() -> bytes:
    data = zlib.decompress(base64.b64decode(_RETAIL_WEIGHTS_Z))
    _require(len(data) == WEIGHTS_SIZE, "embedded retail weight table has the wrong size")
    return data


# ---------------------------------------------------------------- decoding
def decode_curves(blob: bytes) -> dict[str, list[list[int]]]:
    """family -> list of 21-entry signed curves."""

    out: dict[str, list[list[int]]] = {}
    for family, va, count in TABLES:
        base = va - CURVES_VA
        out[family] = [list(struct.unpack("<21b", blob[base + i * CURVE_LEN: base + (i + 1) * CURVE_LEN]))
                       for i in range(count)]
    return out


def decode_weights(blob: bytes) -> list[dict[str, int]]:
    rows = []
    for i in range(WEIGHT_ROWS):
        pos, profile, sub, weight, pad = struct.unpack_from("<IBBBB", blob, i * 8)
        rows.append({"position": pos, "profile": profile, "sub": sub, "weight": weight})
    return rows


def _encode_curves(tables: Mapping[str, list[list[int]]], retail: bytes) -> bytes:
    buf = bytearray(retail)                  # keeps the padding bytes between tables
    for family, va, count in TABLES:
        base = va - CURVES_VA
        for i, curve in enumerate(tables[family]):
            _require(len(curve) == CURVE_LEN, "curve length")
            buf[base + i * CURVE_LEN: base + (i + 1) * CURVE_LEN] = struct.pack("<21b", *curve)
    return bytes(buf)


def _encode_weights(rows: list[dict[str, int]], retail: bytes) -> bytes:
    buf = bytearray(retail)
    for i, row in enumerate(rows):
        buf[i * 8 + 6] = row["weight"]
    return bytes(buf)


# ---------------------------------------------------------------- the transform
def _clamp8(value: float) -> int:
    return max(-127, min(127, int(round(value))))


def reshape_curve(curve: list[int], family: str, growth_scale: float = 1.0, decline_scale: float = 1.0) -> list[int]:
    """Year 0 untouched; a growth ramp over years 1..GROWTH_YEARS; steeper decline after the family's age."""

    growth, decline, after = SHAPE[family]
    out = []
    for year, value in enumerate(curve):
        ramp = growth * growth_scale * min(year, GROWTH_YEARS) / GROWTH_YEARS
        slide = decline * decline_scale * max(0, year - after)
        out.append(_clamp8(value + ramp - slide) if year else value)
    return out


def reshape_curves(tables: Mapping[str, list[list[int]]], growth_scale: float = 1.0,
                   decline_scale: float = 1.0) -> dict[str, list[list[int]]]:
    return {family: [reshape_curve(c, family, growth_scale, decline_scale) for c in curves]
            for family, curves in tables.items()}


def _row_growth(profile_row: bytes, tables: Mapping[str, list[list[int]]]) -> float:
    """How much this archetype gains from rookie year to year 6, summed over the ten families."""

    total = 0.0
    for family_index, (family, _va, count) in enumerate(TABLES):
        idx = profile_row[6 + family_index]
        if idx < count:
            curve = tables[family][idx]
            total += curve[6] - curve[0]
    return total


def spread_weights(rows: list[dict[str, int]], profiles: bytes, tables: Mapping[str, list[list[int]]],
                   spread: float = SPREAD) -> list[dict[str, int]]:
    """Move weight from the middle archetypes to the two best- and two worst-developing ones per
    position, keeping every position's total exactly (the game draws ``rand % total``)."""

    out = [dict(r) for r in rows]
    by_pos: dict[int, list[int]] = {}
    for i, row in enumerate(out):
        by_pos.setdefault(row["position"], []).append(i)
    profile_rows = {(struct.unpack_from("<I", profiles, k * 16)[0], profiles[k * 16 + 4], profiles[k * 16 + 5]):
                    profiles[k * 16: k * 16 + 16] for k in range(WEIGHT_ROWS)}
    for pos, idxs in by_pos.items():
        total = sum(out[i]["weight"] for i in idxs)
        growth = {}
        for i in idxs:
            key = (pos, out[i]["profile"], out[i]["sub"])
            growth[i] = _row_growth(profile_rows[key], tables) if key in profile_rows else 0.0
        order = sorted(idxs, key=lambda i: growth[i])
        n = len(order)
        extremes = set(order[:2]) | set(order[-2:]) if n >= 6 else set(order[:1]) | set(order[-1:])
        scaled = {}
        for i in idxs:
            factor = (1.0 + spread) if i in extremes else (1.0 - spread * len(extremes) / max(1, n - len(extremes)))
            scaled[i] = max(1.0, out[i]["weight"] * factor)
        weights = {i: max(1, int(round(scaled[i]))) for i in idxs}
        diff = total - sum(weights.values())
        biggest = max(idxs, key=lambda i: weights[i])
        weights[biggest] = max(1, weights[biggest] + diff)
        _require(sum(weights.values()) == total, "weight total drifted")
        for i in idxs:
            out[i]["weight"] = weights[i]
    return out


def patched_tables(payload_profiles: bytes | None = None, growth_scale: float = 1.0, decline_scale: float = 1.0,
                   spread: float = SPREAD) -> tuple[bytes, bytes]:
    """The two replacement blobs (curves, weights) derived from the embedded retail tables."""

    retail_c = retail_curves()
    retail_w = retail_weights()
    tables = reshape_curves(decode_curves(retail_c), growth_scale, decline_scale)
    curves = _encode_curves(tables, retail_c)
    if payload_profiles is None:
        weights = retail_w
    else:
        weights = _encode_weights(spread_weights(decode_weights(retail_w), payload_profiles, tables, spread), retail_w)
    return curves, weights


# ---------------------------------------------------------------- XBE plumbing
def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise ProgressionError(f"VA 0x{va:x} is in no section")


def _profiles(payload: bytes) -> bytes:
    off = _offset(payload, PROFILES_VA)
    return payload[off: off + WEIGHT_ROWS * 16]


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    curves, weights = patched_tables(_profiles(payload))
    return [
        ("aging_curves", _offset(payload, CURVES_VA), retail_curves(), curves),
        ("archetype_weights", _offset(payload, WEIGHTS_VA), retail_weights(), weights),
    ]


def status(payload: bytes) -> str:
    try:
        sites = _sites(payload)
    except (ProgressionError, ValueError, struct.error):
        return "foreign"
    states = set()
    for _label, off, before, after in sites:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    _require(state == "retail", f"progression sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, off, before, after in _sites(payload):
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "bytes": len(after),
                      "changed": sum(1 for a, b in zip(before, after) if a != b)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "shape": {k: {"growth_by_year_5": v[0], "extra_decline_per_year": v[1], "decline_after_year": v[2]}
                               for k, v in SHAPE.items()},
                     "spread": SPREAD}


__all__ = ["ProgressionError", "CURVES_VA", "CURVES_SIZE", "WEIGHTS_VA", "WEIGHTS_SIZE", "PROFILES_VA", "TABLES",
           "SHAPE", "SPREAD", "apply", "decode_curves", "decode_weights", "patched_tables", "reshape_curve",
           "retail_curves", "retail_weights", "spread_weights", "status"]
