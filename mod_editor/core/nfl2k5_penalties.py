"""Penalties at NFL rates and a working Chop Block toggle (executable patch, xemu-only).

How retail NFL 2K5 decides a flag (everything in ``default.xbe``, studied 2026-09-04):

* The Penalty Settings screen writes 12 sliders (0.0-1.0, menu step 0.025) and 11 toggles into the
  settings block at ``.data`` 0xE60058..0xE600BC. Saved profiles carry those values, so the defaults
  written by ``FUN_000e2c70`` are not a lever a patch can rely on.
* Every slider feeds a detector through the shared interpolator ``FUN_001b0ae0`` (``ecx`` = table of
  ``(x, y)`` float pairs, ``edx`` = the count stored at table-4, ``push x``; binary search, linear
  interpolation, clamped to the end knots). Nine such tables sit in ``.rdata``: a probability per
  blocking engagement (offensive and defensive holding, clipping), a hazard rate and a contact radius
  (defensive pass interference), a grace window in seconds (roughing the passer/kicker, late hit), a
  distance threshold in cm (ineligible receiver downfield), a per-tackle probability that the tackle
  code then multiplies by the slider again (face mask), and the neutral-zone width (NZI).
* ``FUN_000b1440`` (game start and every settings change) sets the runtime enable word (+0x50) of each
  of the 26 penalty records at ``.data`` 0xA89950 + idx*0x70 through a 25-entry jump table at
  0xB1574: toggles copy the toggle, sliders test ``> 0``. Both the Clipping (idx 9) and the Chop Block
  (idx 10) entries point at the Clipping-slider case (0xB14EE), so the **Chop Block On/Off toggle
  (0xE60064) is dead in retail**: chop blocks are called whenever the Clipping slider is above 0.

This patch keeps every mechanism and changes data in place, plus one 10-byte stub:

1. **Curve re-knotting (the rate lever).** Seven of the nine tables get new y-values so slider 0.5
   (the default, and what saved profiles carry) produces an NFL-shaped rate, 0 stays 0 / the widest
   window, and 1.0 keeps the retail extreme so the user slider still spans a range. Knot counts and
   x-values are untouched (the interpolator needs ascending x). The DPI hazard, its contact radius and
   the NZI width keep their retail knots. All rates are **ESTIMATED**: the engine has no calls-per-game
   number (each slider drives a probability per event, a hazard per second or a grace window) and the
   event frequencies are unmeasured, so the knots are a first cut pending a calibration playtest.
   One deliberate deviation from the study's list: the ineligible-downfield threshold keeps a
   non-increasing shape (the 0.7 knot follows the 0.5 knot down to 274.32 cm), so a higher slider is
   never more lenient than a lower one.
2. **Modern-rules record.** The incidental face mask (idx 25) yardage at 0xA8A480 goes from 457.2 cm
   (5 yd, the 2004 rule) to 1371.6 cm (15 yd); its enforcement-class flags are untouched.
3. **Chop Block toggle.** The case-10 jump-table entry at 0xB1598 is repointed to a 10-byte stub
   ``mov eax,[0xE60064]; jmp 0xB1558`` (the same shape as the False Start case) hosted in the dead
   ``FUN_000b4a60`` (0xB4A60; zero Ghidra callers, no rel32 / immediate / pointer reference anywhere
   in the retail image; the 6 bytes after the stub are int3-filled). Chop Block now follows its own
   On/Off toggle instead of the Clipping slider. Note that retail's default for that toggle is Off, so
   an existing profile silences chop blocks until Penalty Settings -> Chop Block is switched On.

Follow-ups deliberately left out of this cut:

* the defaults in ``FUN_000e2c70`` (0xE2C70..0xE2CFC): flipping Chop Block's default to On at 0xE2CBE
  once the toggle is witnessed working, and the 0.5 slider defaults stay so profiles and curves agree;
* an OPI probability (``FUN_000b3510`` is a deterministic contact gate; the OPI slider only enables it):
  a ~40-byte cave rolling ``FUN_000b02a0(p)`` against a new table would give the slider a meaning
  (NFL OPI ~ 0.14 per team-game vs DPI 0.58) -- only if calibration shows OPI is over- or under-called;
* the hidden Late Hit slider row (the detector already reads 0xE600A8; exposing it needs the 0x34-byte
  menu table relocated).

Not in the engine at all (no detector, no record): illegal formation, illegal shift, 12 men on the
field, illegal contact, illegal use of hands, horse collar, taunting. Excessive crowd noise (idx 22)
and the second fair-catch record (idx 17) have no call site and never fire.

Calibration (Noah, in game, retail defaults): six CPU-vs-CPU games (coach or demo mode; Practice ->
Scrimmage does not count, penalties are disabled when the mode word 0xE5FF80 < 4), tally flags by
type from the play log / referee announcements, then scale each table's 0.5 knot by
``nfl_rate / measured_rate`` (clamped to the 1.0 knot). NFL 2024 per team-game (nflpenalties.com):
offensive holding 1.30, false start 1.30, DPI 0.58, defensive holding 0.34, unnecessary roughness
0.34, delay 0.32, roughing the passer 0.18, face mask 0.17, NZI 0.17, OPI 0.14, ineligible
downfield 0.14. Unwitnessed in game.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from . import nfl2k5_rdata_sites as rdata

IMAGE_BASE = 0x10000

# --- code the patch relies on (documentation + the emulation tests) --------------------------------
INTERPOLATOR_VA = 0x001B0AE0        # FUN_001b0ae0(ecx = pairs, edx = count, push x) -> st(0)
ENABLE_PASS_VA = 0x000B1440         # FUN_000b1440: record[idx].enable = toggle | slider > 0, idx 1..25
ENABLE_JUMP_TABLE_VA = 0x000B1574   # 25 dword entries, index = penalty idx - 1
CASE10_ENTRY_VA = 0x000B1598        # entry for idx 10 (Chop Block)
RETAIL_CASE10_TARGET = 0x000B14EE   # `fld [0xE600AC]` = the Clipping-slider case (idx 9 shares it at 0xB1594)
STORE_VA = 0x000B1558               # `mov [ecx],eax` then the loop advances to the next record
MODE_VA = 0x00E5FF80                # game-mode word; < 4 disables every penalty (practice)

# --- the settings block (.data, BSS: defaults written by FUN_000e2c70, overridden by saved profiles)
SETTINGS: Mapping[str, int] = MappingProxyType({
    "offsides": 0xE60058, "encroachment": 0xE6005C, "false_start": 0xE60060, "chop_block": 0xE60064,
    "intentional_grounding": 0xE60068, "illegal_forward_pass": 0xE6006C, "fair_catch_interference": 0xE60070,
    "ineligible_receiver": 0xE60074, "illegal_kick": 0xE60078, "illegal_onside_kick": 0xE6007C,
    "delay_of_game": 0xE60080, "all_penalties": 0xE6008C,
    "face_mask": 0xE60090, "neutral_zone_infraction": 0xE60094, "defensive_pass_interference": 0xE60098,
    "offensive_pass_interference": 0xE6009C, "offensive_holding": 0xE600A0, "defensive_holding": 0xE600A4,
    "late_hit": 0xE600A8, "clipping": 0xE600AC, "roughing_the_passer": 0xE600B0, "roughing_the_kicker": 0xE600B4,
    "ineligible_receiver_downfield": 0xE600B8, "crowd_noise": 0xE600BC,
})
CHOP_BLOCK_TOGGLE_VA = SETTINGS["chop_block"]
CLIPPING_SLIDER_VA = SETTINGS["clipping"]

# --- the penalty record table (.data) --------------------------------------------------------------
RECORD_TABLE_VA = 0x00A89950
RECORD_SIZE = 0x70
RECORD_COUNT = 26
RECORD_INDEX_OFFSET = 0x08
RECORD_YARDS_OFFSET = 0x40          # float, cm (457.2 = 5 yd); 0 = spot foul
RECORD_ENABLE_OFFSET = 0x50         # dword written by FUN_000b1440
RECORD_NAMES = ("none", "Offsides", "Encroachment", "Neutral zone infraction", "Delay of game", "Roughing the passer",
                "Roughing the kicker", "Offensive holding", "Defensive holding", "Clipping", "Chop block", "Late hit",
                "Intentional grounding", "Offensive pass interference", "Defensive pass interference", "False start",
                "Fair catch interference", "Fair catch interference (unused)", "Ineligible receiver downfield",
                "Illegal touching", "Illegal kick", "Illegal onside kick", "Excessive crowd noise", "Illegal forward pass",
                "Personal foul face mask", "Incidental face mask")
IDX_CLIPPING, IDX_CHOP_BLOCK, IDX_INCIDENTAL_FACEMASK = 9, 10, 25


def record_va(idx: int, field_offset: int = 0) -> int:
    return RECORD_TABLE_VA + idx * RECORD_SIZE + field_offset


FACEMASK_YARDS_VA = record_va(IDX_INCIDENTAL_FACEMASK, RECORD_YARDS_OFFSET)
assert FACEMASK_YARDS_VA == 0x00A8A480
RETAIL_FACEMASK_YARDS = struct.pack("<f", 457.2)        # 5 yd (2004 rule)
PATCHED_FACEMASK_YARDS = struct.pack("<f", 1371.6)      # 15 yd (every face mask is a personal foul since 2008)
YARD_CM = 91.44

# --- the nine slider -> factor curve tables (.rdata): key, label, VA of the first pair, unit, retail pairs
# (hex, little-endian float32 (x, y) pairs; the count dword sits at VA - 4 and is pinned separately)
Pairs = tuple[tuple[float, float], ...]
TABLES: tuple[tuple[str, str, int, str, str], ...] = (
    ("off_holding", "Offensive holding: probability per blocking engagement", 0x0050CDF8, "p",
     "00000000000000000000803ecdcc4c3d0000003fcdcccc3d0000403f0000803e0000803f0000003f"),
    ("def_holding", "Defensive holding: probability per event", 0x0050CE24, "p",
     "00000000000000000000803ecdcc4c3e0000003f0000003f0000403fcdcc4c3f0000803f3333733f"),
    ("clipping", "Clipping: probability per block from behind (also gates chop block in retail)", 0x0050CE50, "p",
     "00000000000000000000803e9a99993e0000003f0000003f0000403f3333333f0000803f3333733f"),
    ("dpi", "Defensive pass interference: hazard multiplier while the ball is in flight", 0x0050C6D0, "x",
     "00000000000000000000803e3333b33e0000003f6666863f0000803f00000040"),
    ("dpi_radius", "Defensive pass interference: contact radius around the landing point (cm)", 0x0050C734, "cm",
     "00000000666618440000803e666698430000003fd34d12420000803f0ad7f340"),
    ("roughing", "Roughing the passer / kicker: grace window after the release (s)", 0x0050C6AC, "s",
     "00000000000040400000803e0000c03f0000003f9a99193f0000803fcdcc4c3e"),
    ("late_hit", "Late hit: window after the whistle (s)", 0x0050C6F4, "s",
     "00000000000000400000003f0000803f0000803fcdcccc3d"),
    ("face_mask", "Face mask: probability per grabbing tackle (times the slider again in the tackle code)", 0x0050CD48, "p",
     "00000000cdcc4c3d0000003f8fc2753c3333333f0ad7233c6666663f0ad7a33b0000803f6f12033b"),
    ("inel_downfield", "Ineligible receiver downfield: how far past the line a lineman may be at the throw (cm)", 0x0050C678, "cm",
     "000000009a99e444cdcc4c3e3373ab44cdcccc3e48e136440000003ff62809443333333f48e1b6430000803ff6288943"),
    ("nzi", "Neutral zone infraction: zone width factor (x 13.97 cm)", 0x0050C758, "x",
     "00000000000000000000003f1f856b3f0000803f0000803f"),
)
TABLE_VAS: Mapping[str, int] = MappingProxyType({key: va for key, _label, va, _unit, _hex in TABLES})


def _decode_pairs(blob: bytes) -> Pairs:
    if len(blob) % 8:
        raise ValueError("a curve table is (x, y) float pairs")
    return tuple(struct.unpack_from("<ff", blob, i * 8) for i in range(len(blob) // 8))


def _encode_pairs(pairs: Sequence[tuple[float, float]]) -> bytes:
    return b"".join(struct.pack("<ff", float(x), float(y)) for x, y in pairs)


RETAIL_PAIRS: Mapping[str, Pairs] = MappingProxyType({key: _decode_pairs(bytes.fromhex(h)) for key, _l, _va, _u, h in TABLES})
TABLE_COUNTS: Mapping[str, int] = MappingProxyType({key: len(pairs) for key, pairs in RETAIL_PAIRS.items()})

# --- profiles: table key -> new (x, y) knots; tables not named keep their retail knots -------------
# "nfl": the ESTIMATED first cut from the 2026-09-04 study (see the module docstring); x untouched.
PROFILES: Mapping[str, Mapping[str, Pairs]] = MappingProxyType({
    "nfl": MappingProxyType({
        "off_holding": ((0.0, 0.0), (0.25, 0.10), (0.5, 0.20), (0.75, 0.35), (1.0, 0.50)),
        "def_holding": ((0.0, 0.0), (0.25, 0.15), (0.5, 0.30), (0.75, 0.60), (1.0, 0.95)),
        "clipping": ((0.0, 0.0), (0.25, 0.05), (0.5, 0.10), (0.75, 0.40), (1.0, 0.95)),
        "roughing": ((0.0, 3.0), (0.25, 1.2), (0.5, 0.45), (1.0, 0.2)),
        "late_hit": ((0.0, 2.0), (0.5, 0.8), (1.0, 0.1)),
        "face_mask": ((0.0, 0.02), (0.5, 0.006), (0.7, 0.004), (0.9, 0.002), (1.0, 0.001)),
        # 0.5 knot 548.64 -> 274.32 cm (3 yd; the modern rule is 1 yd but 2K5 linemen drift); the 0.7
        # knot follows it down so the threshold never loosens as the slider rises
        "inel_downfield": ((0.0, 1828.8), (0.2, 1371.6), (0.4, 731.52), (0.5, 274.32), (0.7, 274.32), (1.0, 274.32)),
    }),
})
DEFAULT_PROFILE = "nfl"

# --- the Chop Block stub ---------------------------------------------------------------------------
# Host: dead FUN_000b4a60 (0xB4A60..0xB4A8D, an 8-byte-pattern fill helper; zero Ghidra callers, and the
# retail image holds no rel32 target, push/mov immediate or aligned pointer landing on any of its bytes).
HOST_VA = 0x000B4A60
HOST_SIZE = 16
RETAIL_HOST = bytes.fromhex("568bf18d0c063bf173208b5424088b44")
assert len(RETAIL_HOST) == HOST_SIZE
STUB = (b"\xa1" + struct.pack("<I", CHOP_BLOCK_TOGGLE_VA)                      # mov eax,[0xE60064]
        + b"\xe9" + struct.pack("<i", STORE_VA - (HOST_VA + 5 + 5)))            # jmp 0xB1558
STUB_SIZE = len(STUB)
assert STUB_SIZE == 10
PATCHED_HOST = STUB + b"\xcc" * (HOST_SIZE - STUB_SIZE)
RETAIL_CASE10_ENTRY = struct.pack("<I", RETAIL_CASE10_TARGET)
PATCHED_CASE10_ENTRY = struct.pack("<I", HOST_VA)


class PenaltiesError(ValueError):
    """The penalties patch cannot be applied to this executable or profile."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PenaltiesError(message)


# ---------------------------------------------------------------- profiles
def validate_profile(tables: Mapping[str, Sequence[tuple[float, float]]]) -> dict[str, Pairs]:
    """A profile may only re-knot known tables, keeps every count, and keeps x exactly as retail."""

    out: dict[str, Pairs] = {}
    for key, pairs in tables.items():
        _require(key in RETAIL_PAIRS, f"unknown curve table {key!r}; choose from {sorted(RETAIL_PAIRS)}")
        retail = RETAIL_PAIRS[key]
        knots = tuple((float(x), float(y)) for x, y in pairs)
        _require(len(knots) == len(retail), f"{key}: {len(knots)} knots, the table holds {len(retail)}")
        for (x, y), (rx, _ry) in zip(knots, retail):
            _require(struct.pack("<f", x) == struct.pack("<f", rx), f"{key}: knot x {x!r} must stay {rx!r}")
            _require(y == y and abs(y) != float("inf"), f"{key}: knot y {y!r} is not finite")
            _require(y >= 0.0, f"{key}: knot y {y!r} is negative")
        out[key] = knots
    return out


def load_profile(profile: str | Path) -> tuple[str, dict[str, Pairs]]:
    """A built-in profile name, or a JSON file ``{"tables": {key: [[x, y], ...]}}`` (``"name"`` optional)."""

    text = str(profile)
    if text in PROFILES:
        return text, validate_profile(PROFILES[text])
    path = Path(text).expanduser()
    _require(path.suffix.lower() == ".json" and path.is_file(),
             f"unknown penalty profile {text!r}; choose from {sorted(PROFILES)} or give a .json file")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PenaltiesError(f"{path}: {exc}") from exc
    _require(isinstance(doc, dict) and isinstance(doc.get("tables"), dict), f"{path}: expected {{\"tables\": {{...}}}}")
    tables = validate_profile(doc["tables"])
    _require(bool(tables), f"{path}: the profile re-knots no table")
    return str(doc.get("name") or path.stem), tables


def profile_pairs(profile: str | Path = DEFAULT_PROFILE) -> dict[str, Pairs]:
    """Every table's knots under ``profile`` (retail knots for the tables it does not name)."""

    _name, tables = load_profile(profile)
    return {key: tables.get(key, RETAIL_PAIRS[key]) for key in RETAIL_PAIRS}


def describe(profile: str | Path = DEFAULT_PROFILE) -> list[dict[str, object]]:
    """Retail vs new knots per table, for receipts and the terminal."""

    new = profile_pairs(profile)
    rows = []
    for key, label, va, unit, _hex in TABLES:
        retail = RETAIL_PAIRS[key]
        rows.append({"table": key, "label": label, "va": f"0x{va:x}", "unit": unit, "count": len(retail),
                     "retail": [list(p) for p in retail], "new": [list(p) for p in new[key]],
                     "changed": _encode_pairs(new[key]) != _encode_pairs(retail)})
    return rows


# ---------------------------------------------------------------- reading an executable
def decode_tables(payload: bytes) -> dict[str, Pairs]:
    """The nine tables as the game sees them (count word at VA-4, pairs after it)."""

    out: dict[str, Pairs] = {}
    for key, _label, va, _unit, _hex in TABLES:
        off = rdata.offset_of(payload, va)
        count = struct.unpack_from("<I", payload, off - 4)[0]
        _require(count == TABLE_COUNTS[key], f"{key}: count word is {count}, retail is {TABLE_COUNTS[key]}")
        out[key] = _decode_pairs(payload[off: off + count * 8])
    return out


def _pins_are_retail(payload: bytes) -> bool:
    """The count words, the tables the profile keeps, and the interpolator/enable-pass shape must be retail."""

    try:
        for key, _label, va, _unit, _hex in TABLES:
            off = rdata.offset_of(payload, va)
            if struct.unpack_from("<I", payload, off - 4)[0] != TABLE_COUNTS[key]:
                return False
        # the interpolator's first instructions (`fld [esp+4]; push esi; fcomp [ecx]`) and the enable pass's
        # `jmp dword [eax*4+0xB1574]`, `mov [ecx],eax` store and the shared Clipping case
        if payload[rdata.offset_of(payload, INTERPOLATOR_VA): rdata.offset_of(payload, INTERPOLATOR_VA) + 6] != bytes.fromhex("d944240456d8"):
            return False
        if payload[rdata.offset_of(payload, ENABLE_PASS_VA + 0x57): rdata.offset_of(payload, ENABLE_PASS_VA + 0x57) + 7] != bytes.fromhex("ff248574150b00"):
            return False
        if payload[rdata.offset_of(payload, STORE_VA): rdata.offset_of(payload, STORE_VA) + 2] != bytes.fromhex("8901"):
            return False
        if payload[rdata.offset_of(payload, RETAIL_CASE10_TARGET): rdata.offset_of(payload, RETAIL_CASE10_TARGET) + 6] != b"\xd9\x05" + struct.pack("<I", CLIPPING_SLIDER_VA):
            return False
        if payload[rdata.offset_of(payload, CASE10_ENTRY_VA - 4): rdata.offset_of(payload, CASE10_ENTRY_VA - 4) + 4] != RETAIL_CASE10_ENTRY:
            return False          # idx 9 (Clipping) keeps the shared case
        idx_off = rdata.offset_of(payload, record_va(IDX_CHOP_BLOCK, RECORD_INDEX_OFFSET))
        if struct.unpack_from("<I", payload, idx_off)[0] != IDX_CHOP_BLOCK:
            return False
    except (rdata.RdataSiteError, ValueError, struct.error):
        return False
    return True


def sites(profile: str | Path = DEFAULT_PROFILE) -> list[tuple[str, int, bytes, bytes]]:
    """``(label, va, retail_bytes, patched_bytes)`` for every span the profile changes."""

    new = profile_pairs(profile)
    out: list[tuple[str, int, bytes, bytes]] = []
    for key, _label, va, _unit, _hex in TABLES:
        before, after = _encode_pairs(RETAIL_PAIRS[key]), _encode_pairs(new[key])
        if before != after:
            out.append((f"curve_{key}", va, before, after))
    out.append(("incidental_facemask_yards", FACEMASK_YARDS_VA, RETAIL_FACEMASK_YARDS, PATCHED_FACEMASK_YARDS))
    out.append(("chop_block_case_entry", CASE10_ENTRY_VA, RETAIL_CASE10_ENTRY, PATCHED_CASE10_ENTRY))
    out.append(("chop_block_stub_host", HOST_VA, RETAIL_HOST, PATCHED_HOST))
    return out


def kept_tables(profile: str | Path = DEFAULT_PROFILE) -> list[tuple[str, int, bytes, bytes]]:
    """Tables the profile leaves alone: pinned retail (same bytes before and after)."""

    new = profile_pairs(profile)
    return [(f"curve_{key}", va, _encode_pairs(RETAIL_PAIRS[key]), _encode_pairs(RETAIL_PAIRS[key]))
            for key, _label, va, _unit, _hex in TABLES if _encode_pairs(new[key]) == _encode_pairs(RETAIL_PAIRS[key])]


def status(payload: bytes, profile: str | Path = DEFAULT_PROFILE) -> str:
    try:
        edit_sites, kept = sites(profile), kept_tables(profile)
    except PenaltiesError:
        return "foreign"
    if not _pins_are_retail(payload):
        return "foreign"
    for _label, va, before, _after in kept:
        try:
            off = rdata.offset_of(payload, va)
        except rdata.RdataSiteError:
            return "foreign"
        if payload[off: off + len(before)] != before:
            return "foreign"
    return rdata.status(payload, edit_sites)


def apply(payload: bytes, profile: str | Path = DEFAULT_PROFILE) -> tuple[bytes, Mapping[str, object]]:
    name, _tables = load_profile(profile)
    state = status(payload, profile)
    if state == "applied":
        return payload, {"already_applied": True, "edits": [], "changed_bytes": 0, "profile": name}
    _require(state == "retail", f"penalty sites are {state}, not retail; refusing")
    try:
        patched, receipt = rdata.apply(payload, sites(profile), f"Penalties ({name})")
    except rdata.RdataSiteError as exc:
        raise PenaltiesError(str(exc)) from exc
    return patched, {**receipt, "profile": name, "estimated": True,
                     "tables": describe(profile),
                     "incidental_facemask_yards": {"va": f"0x{FACEMASK_YARDS_VA:x}", "retail_cm": 457.2, "new_cm": 1371.6},
                     "chop_block": {"case_entry_va": f"0x{CASE10_ENTRY_VA:x}", "retail_target": f"0x{RETAIL_CASE10_TARGET:x}",
                                    "stub_va": f"0x{HOST_VA:x}", "stub_bytes": STUB.hex(), "host_size": HOST_SIZE,
                                    "reads": f"0x{CHOP_BLOCK_TOGGLE_VA:x}", "resumes_at": f"0x{STORE_VA:x}"}}


__all__ = ["CASE10_ENTRY_VA", "CHOP_BLOCK_TOGGLE_VA", "CLIPPING_SLIDER_VA", "DEFAULT_PROFILE", "ENABLE_JUMP_TABLE_VA",
           "ENABLE_PASS_VA", "FACEMASK_YARDS_VA", "HOST_SIZE", "HOST_VA", "IDX_CHOP_BLOCK", "IDX_CLIPPING",
           "IDX_INCIDENTAL_FACEMASK", "INTERPOLATOR_VA", "MODE_VA", "PATCHED_CASE10_ENTRY", "PATCHED_FACEMASK_YARDS",
           "PATCHED_HOST", "PROFILES", "PenaltiesError", "RECORD_COUNT", "RECORD_ENABLE_OFFSET", "RECORD_INDEX_OFFSET",
           "RECORD_NAMES", "RECORD_SIZE", "RECORD_TABLE_VA", "RECORD_YARDS_OFFSET", "RETAIL_CASE10_ENTRY",
           "RETAIL_CASE10_TARGET", "RETAIL_FACEMASK_YARDS", "RETAIL_HOST", "RETAIL_PAIRS", "SETTINGS", "STORE_VA", "STUB",
           "STUB_SIZE", "TABLES", "TABLE_COUNTS", "TABLE_VAS", "apply", "decode_tables", "describe", "kept_tables",
           "load_profile", "profile_pairs", "record_va", "sites", "status", "validate_profile"]
