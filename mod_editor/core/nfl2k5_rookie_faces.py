"""Rookie faces (job b778-rh1, Noah 2026-10-22): a bank of new fictional draft headshots for generated prospects,
picked by the prospect's own skin tone, build (weight) and the odds his name and position carry, with his in-game
skin tone, generic head and hair set from the face he gets. EXPERIMENTAL.

Noah: "make sure that the skin tones of rookie prospects perfectly matches their headshot ... I would like to
increase the variety in rookie headshots by at least 50 more new ones ... when you draft a rookie, the face almost
always looks different."

What retail does (FUN_000E6780, the class generator's body/face pass, called once per prospect by FUN_002BE6F0)
-------------------------------------------------------------------------------------------------------------
* Skin (player +0x18 bits 7-9) and face shape (+0x20 bits 17-19) are drawn "between" two template records per
  position, but every one of the 17 template pairs stores low > high, so the unsigned divisor wraps and both come out
  uniform over 0..7.  The generic heads exist only for skin 0..5 and face 0..6 (``f9001 + 100*skin + face``), so a
  quarter of all prospects get a skin with no head of its own.
* The portrait (+0x06) comes from the 41-row range table at 0x4F4F40 (generic id -> portrait range in 8000..8905,
  895 retail portraits) at ``lo + (hi - lo) * f(weight)``: no randomness, so the same weight gives the same face, and
  skin 6/7 falls through to the last range, 8895..8905 (11 of the darkest faces).

What this option does
---------------------
1. A new portrait bank: ``data/nfl2k5_rookie_faces`` holds fictional draft-style headshots (generated, reviewed one by
   one; no real person, no reference photo ships), each labelled with its skin tone (0..5, the generic head tones),
   build (lean < LEAN_MAX_LB, heavy >= HEAVY_MIN_LB, else medium) and whether its hair hangs (locs, long braids).
   The bank is grouped into 18 buckets (tone x build), each a contiguous run of portrait ids that no roster on the
   image uses and no portrait occupies (b778-rh2: 24 rows in the five-digit run from 10000, see ID_MIN / ID_END).
2. The portraits are added, not replaced: the game's PORTRAIT context reads the record named by the UTF-16 string at
   0xE6A3B4 ("Portrait.iff", outer 10, CACR) and streams slot ``sorted-hash index x 0x4500`` from the aggregate the
   record names ("portrait.cdf", outer 3105).  This option appends a new record ("Portrai2.iff") and aggregate
   ("portrai2.cdf") holding every existing slot (copied from the finished image) plus the bank, sorted by hash, and
   points the string at the new record.  Outer 10 and 3105 are left byte-identical, so every tool that reads or checks
   a portrait or Team Select card at its catalogued offset keeps working.  Cost: one more outer pair (the copy of
   3105 plus 17,664 bytes per new face) on disc, 4 heap bytes per new face in the loaded record.
3. The generator's skin/face draw (0xE67EA, now a jump over 132 bytes that hold helpers) and its portrait pick
   (0xE7019..0xE7117) are replaced in place, with the tables in the retail range table's 504 bytes (0x4F4F40, .rdata,
   RWX like retail .data).  Per prospect, after his name, position and weight exist:
   * logit(Black) = POS[position] + FIRST[band of his first name] + LAST[code of his surname]  (1/16 nat units);
     P = SIG[(logit + 128) >> 3]; one random byte decides.  POS is the TIDES position share, FIRST/LAST are the
     log likelihood ratios P(name | Black) / P(name | not Black) from voter-file name data, so a "Jamal" is Black most
     of the time and a white "Jamal" is rare but possible.  Ratings never read any of this.
   * tone: Black -> 2..5 by TCB (head 1 is a tan that reads as Hispanic or Pacific Islander), otherwise 0..1 by TCO
     (one random byte); build from his own weight.
   * the face: ``start + rand % count`` of the (tone, build) bucket, redrawn up to 8 times while any player in the
     live roster already wears it (so a class rarely repeats a face and never one an active player has).
   * skin bits = tone, Dreads bit = the face's hanging hair, face shape = rand % 7 (a generic head for every pair).
   * an older franchise save carries its own name pool in another order: when the first letter of pool name 0 is
     not the one the tables were built for, the first-name term is left out (position and surname still count).
   * nickname first names (Scooby, Riff Raff, ...) sit at the end of the shipped name pool from index NICK0; a drawn
     nickname is kept one time in (NICKMASK + 1), else redrawn from the ordinary names, about 1 % of prospects.
   The surname, its commentary cue and every rating are left exactly as the generator made them.

b778-rh2 (Noah 10/22: "max out the number", "more types", rare East / South Asian prospects with fitting names, "some
genuinely ugly people", "it's very rare you stumble onto the same face twice"):
   * rows hold up to 511 faces (count | hanging << 9), so the big cells reach 1.5x the faces alive at once in a fully
     generated league; a face in use is redrawn up to 24 times (was 8).
   * three rare surnames (Nguyen, Chen, Patel: rows RS0..RS0+2 of the shipped pool, US Census 2010 Asian shares above
     94 %) take their own rows 18..23 (East Asian, tone 1 / South Asian, tone 2, by build) and one of four fitting
     first names from the pool tail (RFIRST0..), which an ordinary draw never keeps.  Drawn like any surname (1 in 485
     per prospect): about 0.9 East Asian and 0.5 South Asian prospects per class of 224.  Ratings never read any of it.
   * an older save's pool (canary mismatch) gets neither the first-name term nor the rare rows.
   * code: region B grows by the 9 nop bytes of padding after its ret 4 (0xE7117..0xE7120, no reference lands there);
     the lean / heavy cut-offs are code immediates; still zero allocator bytes.

Saves: the code reads the pool, the roster and the position from the live roster, so an old franchise save gets the
new faces for every class it generates after the update (its own name pool may lack the nicknames; nothing else
differs).  Players already in a save keep their portrait ids.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import struct
import zlib
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
OWNER = "nfl2k5_rookie_faces"
UI_LABEL = "Rookie faces: new draft headshots that match skin tone, build and name"
BUILD_CAPTION = "Rookie faces (draft prospects)"
HELP_TEXT = ("EXPERIMENTAL. Generated draft prospects get new fictional draft headshots instead of the 2004 stock "
             "photos: the face matches his in-game skin tone and build (his weight), his name and position make his "
             "skin tone as likely as in the real NFL, and a face an active player already wears is avoided. A few "
             "prospects get a nickname first name, and now and then an East Asian or South Asian prospect appears "
             "with a fitting name. Disc images only. Not yet tested in a long franchise.")
EVIDENCE = "EXPERIMENTAL"
DATA_DIR = ROOT / "data" / "nfl2k5_rookie_faces"
BANK_JSON = DATA_DIR / "bank.json"
NAMES_JSON = DATA_DIR / "name_odds.json"
SCHEMA_BANK = "nfl2k5_rookie_faces_bank/v2"
SCHEMA_NAMES = "nfl2k5_rookie_faces_names/v1"

# ------------------------------------------------------------------------------------------------ the executable
IMAGE_BASE = 0x10000
REGION_A = 0xE67EA            # retail skin/face draw, 132 bytes up to the weight code at 0xE686E
REGION_A_END = 0xE686E
REGION_B = 0xE7019            # retail portrait pick and epilogue, plus the 9 nop bytes of padding after its ret 4
REGION_B_END = 0xE7120        # (0xE7117..0xE7120 is inter-routine padding, no reference lands there; next routine 0xE7120)
TABLE_VA = 0x4F4F40           # retail generic-portrait range table (41 rows + sentinel), only read by REGION_B
TABLE_END = 0x4F5138          # the next table (read by FUN_000E6680) starts here
TABLE_DATA = 0x142            # tables, then code
ROSTER_VA = 0xB72918          # -> the live roster object
RAND_VA = 0x48B50             # u32 rand(ecx = generator at 0xE5FCA0)
STRING_VA = 0xE6A3B4          # UTF-16 "Portrait.iff", the PORTRAIT context's record file (only reference 0xE714F)
RECORD_NAME = "Portrai2.iff"
CDF_NAME = "portrai2.cdf"
RETAIL_RECORD_NAME = "Portrait.iff"
RETAIL_CDF_NAME = "portrait.cdf"
# Assembled from tools/b77/rh1_rookie_faces.S (GNU as, linked at 0xE67EA; b778-rh2 version); the listing is in that file.
CODE_A = bytes.fromhex(
    "e97f00000051e8060000005931d2f7f1c3b9a0fce500e94b23f6ff31ff39cf73083904fb740347ebf4c38b4d008b5504"
    "85c9740c66394206740983c25449ebf083c901c30fb705a04f4f0039c7722e39cf732a663b3d9d4f4f00730de8b0ffff"
    "ff8405a24f4f0074140fb70da04f4f00e890ffffff89d78b04fb894610c3")
CODE_B = bytes.fromhex(
    "89068b2d1829b7008b5d548b4d5083c3048b4614e8d3f7ffff897c241431d239cf732289f8c1e8020fb68008504f0089"
    "f983e10301c9d3e883e0030fbe90744f4f008b4d508954241083eb048b4610e898f7ffffe8bcf7ffff8b03668b00663b"
    "05a54f4f00752289f8c1e0050fb70da04f4f0031d2f7f183f81f77120fbe90544f4f0001542410eb05834c2414ff0fb6"
    "463583f810770b0fbe80404f4f00014424108b4424100580000000c1f803790231c083f81f7602b01f0fb6b8784f4f00"
    "e81df7ffff0fb6c039f819ffe811f7ffffba9c4f4f0031c94131db85ff7408ba984f4f00b104433a02720543424975f7"
    "0fb6462a31d23c4a7606423c7d720142e964df4000")
CODE_D = bytes.fromhex(
    "895c24108b442414662b05a34f4f0083f803732c31c93c020f93c18a99514f4f00895c24108d59068b0e83e1038d0481"
    "6603059d4f4f008b4d548b0cc1894e108d3c5b01d78d3cbda84f4f006a185b0fb74f0280e501e81217bfff895424140f"
    "b70701d0e82917bfff75034b75e1668946068b4e1881e17efcffff8b442410c1e00709c10fb64703d1e8394424147301"
    "41894e186a0759e8d116bfff01d2806622f10856225f5e5d5b83c408c20400")

# table layout (offsets from TABLE_VA)
T_POS, T_TONES, T_FIRST, T_LASTCODE, T_SIG = 0x00, 0x11, 0x14, 0x34, 0x38
T_TCB, T_TCO, T_RFIRST0 = 0x58, 0x5C, 0x5D
T_NICK0, T_NICKMASK, T_RS0 = 0x60, 0x62, 0x63
T_CANARY = 0x65                # UTF-16 first letter of pool first name 0: an older save's own pool keeps its name term neutral
T_BUCKETS, T_LASTBITS = 0x68, 0xC8
BUCKETS = 18                  # tone 0..5 x build 0..2, bucket = tone * 3 + build
ROWS = 24                     # + the rare rows: 18 + 3 * group + build (group 0 East Asian, 1 South Asian)
ROW_COUNT_MAX = 511           # row word = count | hanging << 9
ROW_HANGING_MAX = 127
POOL_COUNT = 485
# b778-rh2 rare groups (Noah 10/22: "super Asian every now and then", South Asian "maybe one or two appear every few
# years"): three surnames at adjacent pool rows, drawn like any other surname (1/485 each per prospect), carry their
# own face rows and a fitting first name (four per surname at the pool tail, never drawn otherwise).
RARE_SURNAMES = ("Nguyen", "Chen", "Patel")         # East, East, South (US Census 2010: 96.5 / 96.1 / 94.8 % Asian)
RARE_FIRSTS = ("Minh", "Tuan", "Huy", "Vinh",       # Nguyen
               "Wei", "Jun", "Ming", "Hao",          # Chen
               "Raj", "Nikhil", "Ravi", "Neil")      # Patel
RARE_GROUPS = ("east", "south")
RARE_TONES = (1, 2)            # generic-head tone of the East / South rows
RS0_OFF = 0x8000              # T_RS0 when the pool has no rare surnames: no surname index matches
# Portrait ids: u16 at player +0x06, formatted "%04d" (so 10000..65535 print five digits) into 16-byte stack buffers by
# the only three portrait loaders (0xE7170 player, 0xE71E0, 0xE7240; 25 + 7 + 2 call sites, no other consumer), then
# looked up by name hash; a missing name falls back to "nophoto".  No code compares a portrait id with 9999/10000, and
# shipped rosters already carry ids from 21696 up (shown as "nophoto").  b778-rh2 puts the bank in 10000..21695: one
# free contiguous run, clear of every 4-digit id other options and players use.
ID_MIN, ID_END = 1000, 21696

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
# P(Black | position): TIDES, "The 2013 Racial and Gender Report Card: National Football League" (2012 season),
# Tables 14 (offense) and 15 (defense) and the special-teams table; QB blended toward 2023, when 14 Black
# quarterbacks started in Week 1 (CBS Sports, 2023-09-10); FB is not tabled: the RB/TE midpoint.
P_BLACK = dict(QB=0.35, K=0.02, P=0.02, WR=0.87, CB=0.97, FS=0.83, SS=0.83, HB=0.92, FB=0.45, TE=0.38,
               OLB=0.70, ILB=0.70, C=0.18, G=0.46, T=0.57, DT=0.79, DE=0.80)
# Tone (the generic heads' six skins) given the coin: Black players span the light-brown (mixed, light-skinned) head 1
# to the darkest head 5; the others are white (head 0) or Hispanic / Pacific Islander / other (head 1).
TONE_BLACK = (0.0, 0.27, 0.31, 0.26, 0.16)        # tones 1..5 (none on head 1: its tan reads as Hispanic or Pacific Islander)
TONE_OTHER = (0.82, 0.18)                         # tones 0..1
LEAN_MAX_LB = 224             # nflverse combine weights 2015-2025: lean < 225 (WR, CB, S, most RB/QB, K)
HEAVY_MIN_LB = 275            # heavy >= 275 (OL, DT, a third of DE); medium in between (LB, TE, FB, edge)
WEIGHT_BASE = 150             # player +0x2A = weight - 150
NICKMASK = 7                  # keep a drawn nickname one time in eight
UNITS = 16                    # table logits are 1/16 nat


class RookieFacesError(ValueError):
    """A foreign layout, an unexpected disc or a failed read-back."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RookieFacesError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------------ data files
def load_names(path: Path | None = None) -> dict[str, Any]:
    doc = json.loads(Path(path or NAMES_JSON).read_text(encoding="utf-8"))
    require(doc.get("schema") == SCHEMA_NAMES, "unknown rookie-face name odds document")
    return doc


def load_bank(path: Path | None = None) -> dict[str, Any]:
    doc = json.loads(Path(path or BANK_JSON).read_text(encoding="utf-8"))
    require(doc.get("schema") == SCHEMA_BANK, "unknown rookie-face bank document")
    require(len(doc["buckets"]) == ROWS, f"the bank needs {ROWS} rows")
    for b, row in enumerate(doc["buckets"]):
        if b < BUCKETS:
            require(row["tone"] * 3 + row["build"] == b and not row.get("group"), f"bucket {b} is out of order")
        else:
            g, build = divmod(b - BUCKETS, 3)
            require(row.get("group") == RARE_GROUPS[g] and row["build"] == build and row["tone"] == RARE_TONES[g],
                    f"rare row {b} is out of order")
        require(1 <= row["count"] <= ROW_COUNT_MAX and 0 <= row["hanging"] <= min(row["count"], ROW_HANGING_MAX),
                f"row {b} has a bad count")
        require(ID_MIN <= row["start"] and row["start"] + row["count"] <= ID_END, f"row {b} ids must stay in {ID_MIN}..{ID_END - 1}")
    return doc


def bank_ids(bank: Mapping[str, Any]) -> list[int]:
    return [row["start"] + k for row in bank["buckets"] for k in range(row["count"])]


def _key(name: str) -> str:
    return "".join(c for c in name.upper() if c.isalpha())


# ------------------------------------------------------------------------------------------------ tables
def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _s8(value: float) -> int:
    return max(-127, min(127, int(round(value))))


def _cdf(weights: Sequence[float]) -> list[int]:
    out, acc = [], 0.0
    total = sum(weights)
    for w in weights[:-1]:
        acc += w / total
        out.append(max(0, min(255, int(round(acc * 256)))))
    return out


def rare_layout(firsts: Sequence[str], lasts: Sequence[str]) -> tuple[int, int]:
    """(RS0, RFIRST0): the pool row of the three rare surnames and of the twelve rare first names at the tail, or
    (RS0_OFF, POOL_COUNT) when this pool does not carry them (a user CSV): the rare groups are then off."""
    tail = len(firsts) - len(RARE_FIRSTS)
    keys = [_key(n) for n in lasts]
    want = [_key(n) for n in RARE_SURNAMES]
    for i in range(len(lasts) - len(want) + 1):
        if keys[i:i + len(want)] == want and [_key(n) for n in firsts[tail:]] == [_key(n) for n in RARE_FIRSTS]:
            if not any(_key(n) in want for n in lasts[:i] + lasts[i + len(want):]):
                return i, tail
    return RS0_OFF, len(firsts)


def nick0(firsts: Sequence[str], names: Mapping[str, Any]) -> int:
    """First index of the trailing run of nickname first names (POOL_COUNT when there is none); the rare first names
    at the very end (rare_layout) belong to that run: neither is ever kept from an ordinary draw's band."""
    nick = {_key(n) for n in names["nicknames"]}
    index = len(firsts)
    rare = [_key(n) for n in RARE_FIRSTS]
    if [_key(n) for n in firsts[index - len(rare):]] == rare:
        index -= len(rare)
    while index > 0 and _key(firsts[index - 1]) in nick:
        index -= 1
    return max(1, index)


def last_code_levels(names: Mapping[str, Any]) -> tuple[tuple[float, float, float], tuple[int, int, int, int]]:
    cuts = tuple(names["surname_code_cuts"])
    values = tuple(names["surname_code_logits"])
    require(len(cuts) == 3 and len(values) == 4, "surname code levels")
    return cuts, values


def tables(firsts: Sequence[str], lasts: Sequence[str], bank: Mapping[str, Any],
           names: Mapping[str, Any] | None = None) -> bytes:
    """The TABLE_DATA bytes at TABLE_VA for this pool and bank."""
    names = names or load_names()
    require(len(firsts) == POOL_COUNT and len(lasts) == POOL_COUNT, "the name pool must hold 485 entries")
    out = bytearray(TABLE_DATA)
    first_lr = {_key(k): v for k, v in names["first"].items()}
    last_lr = {_key(k): v for k, v in names["last"].items()}
    n0 = nick0(firsts, names)
    rs0, rfirst0 = rare_layout(firsts, lasts)
    for band in range(32):
        lo, hi = (band * n0 + 31) // 32, ((band + 1) * n0 + 31) // 32
        vals = [first_lr.get(_key(firsts[i]), 0) for i in range(lo, hi)] or [0]
        struct.pack_into("<b", out, T_FIRST + band, _s8(sum(vals) / len(vals)))
    cuts, values = last_code_levels(names)
    for code, v in enumerate(values):
        struct.pack_into("<b", out, T_LASTCODE + code, _s8(v))
    for i, last in enumerate(lasts):
        v = last_lr.get(_key(last), 0)
        code = sum(v >= c for c in cuts)
        out[T_LASTBITS + (i >> 2)] |= code << ((i & 3) * 2)
    for k in range(32):
        x = (k * 8 + 4 - 128) / UNITS
        out[T_SIG + k] = max(0, min(255, int(round(256 / (1 + math.exp(-x))))))
    # Position terms, calibrated so that the class-wide share of Black players at each position equals P_BLACK under
    # the pool's own (uniform, independent) first-name and surname draws: the pool is NFL names, so the names alone
    # would push every position above its share.
    first_w = collections.Counter()
    nick_kept = (rfirst0 - n0) / POOL_COUNT / (NICKMASK + 1)
    for i in range(n0):
        first_w[struct.unpack_from("<b", out, T_FIRST + (i * 32) // n0)[0]] += (1 - nick_kept) / n0
    first_w[0] += nick_kept
    last_w = collections.Counter()
    for i in range(POOL_COUNT):
        code = (out[T_LASTBITS + (i >> 2)] >> ((i & 3) * 2)) & 3
        last_w[struct.unpack_from("<b", out, T_LASTCODE + code)[0]] += 1 / POOL_COUNT
    pairs = [(f + l, wf * wl) for f, wf in first_w.items() for l, wl in last_w.items()]

    def share(term: int) -> float:
        total = 0.0
        for value, weight in pairs:
            k = max(0, min(31, (term + value + 128) >> 3))
            total += weight * out[T_SIG + k] / 256
        return total
    for i, pos in enumerate(POSITIONS):
        best = min(range(-127, 128), key=lambda t: (abs(share(t) - P_BLACK[pos]), abs(t)))
        struct.pack_into("<b", out, T_POS + i, best)
    out[T_TCB:T_TCB + 4] = bytes(_cdf(TONE_BLACK))
    out[T_TCO] = _cdf(TONE_OTHER)[0]
    struct.pack_into("<H", out, T_NICK0, n0)
    out[T_NICKMASK] = NICKMASK
    struct.pack_into("<H", out, T_RS0, rs0)
    struct.pack_into("<H", out, T_RFIRST0, rfirst0)
    out[T_TONES:T_TONES + 2] = bytes(RARE_TONES)
    require(len(bank["buckets"]) == ROWS, f"the bank needs {ROWS} rows")
    for b, row in enumerate(bank["buckets"]):
        require(row["count"] <= ROW_COUNT_MAX and row["hanging"] <= ROW_HANGING_MAX, f"row {b} is too large")
        struct.pack_into("<HH", out, T_BUCKETS + 4 * b, row["start"], row["count"] | row["hanging"] << 9)
    struct.pack_into("<H", out, T_CANARY, ord(firsts[0][0]))
    return bytes(out)


# ------------------------------------------------------------------------------------------------ XBE
def _section_map(payload: bytes) -> list[tuple[int, int, int, int]]:
    """[(virtual address, raw offset, raw size, header offset)] of every section."""
    require(payload[:4] == b"XBEH", "not an XBE")
    base = struct.unpack_from("<I", payload, 0x104)[0]
    count, table_va = struct.unpack_from("<II", payload, 0x11C)
    out = []
    for i in range(count):
        h = table_va - base + i * 56
        _flags, va, _vsize, raw, rsize = struct.unpack_from("<IIIII", payload, h)
        out.append((va, raw, rsize, h))
    return out


def _offset(payload: bytes, va: int, size: int = 1) -> int:
    for sva, raw, rsize, _h in _section_map(payload):
        if sva <= va and va + size <= sva + rsize:
            return raw + va - sva
    raise RookieFacesError(f"0x{va:x} is not file-backed")


def _spans(table: bytes) -> list[tuple[int, bytes]]:
    pad = lambda code, size: code + b"\xcc" * (size - len(code))  # noqa: E731
    return [(REGION_A, pad(CODE_A, REGION_A_END - REGION_A)),
            (REGION_B, pad(CODE_B, REGION_B_END - REGION_B)),
            (TABLE_VA, table + pad(CODE_D, TABLE_END - TABLE_VA - TABLE_DATA)),
            (STRING_VA, RECORD_NAME.encode("utf-16-le"))]


RETAIL_SPAN_SHA256 = {       # retail and every released SOFTDRINK image (v0.6.1 checked) carry these bytes
    REGION_A: "6e6acd5a0be9dbac8fa24161f92fe29b314117851773a9577534a498e73165c6",
    REGION_B: "8c8c09860c0f31519aa72f0293c805c646f84ca632611890705977d32f317692",
    TABLE_VA: "e6ec955562c16009edf4ca8790a0b310d685f3c04443ff1106323fc5514567fd",
    STRING_VA: "8d322c825fff63a505e786350f7fe8da17d68dd292769f9f5146c2605ea14ae2",
}


def _retail_spans(payload: bytes) -> dict[int, bytes]:
    return {va: payload[_offset(payload, va, len(data)):_offset(payload, va, len(data)) + len(data)]
            for va, data in _spans(bytes(TABLE_DATA))}


def xbe_status(payload: bytes) -> str:
    """retail | applied | foreign (an applied image may carry any table bytes; code and string must match)."""
    try:
        current = _retail_spans(payload)
    except (RookieFacesError, struct.error):
        return "foreign"
    if all(sha(current[va]) == RETAIL_SPAN_SHA256[va] for va in current):
        return "retail"
    spans = dict(_spans(bytes(TABLE_DATA)))
    a, b, d, s = (current[REGION_A], current[REGION_B], current[TABLE_VA], current[STRING_VA])
    if (a == spans[REGION_A] and b == spans[REGION_B] and s == spans[STRING_VA]
            and d[TABLE_DATA:] == spans[TABLE_VA][TABLE_DATA:]):
        return "applied"
    return "foreign"


def xbe_tables(payload: bytes) -> bytes:
    off = _offset(payload, TABLE_VA, TABLE_DATA)
    return payload[off:off + TABLE_DATA]


def xbe_apply(payload: bytes, table: bytes) -> tuple[bytes, dict[str, Any]]:
    require(len(table) == TABLE_DATA, "the table block has the wrong size")
    state = xbe_status(payload)
    require(state in ("retail", "applied"), f"the executable's generator bytes are {state}, not retail")
    buf = bytearray(payload)
    touched = set()
    changed = 0
    for va, data in _spans(table):
        off = _offset(payload, va, len(data))
        changed += sum(1 for x, y in zip(buf[off:off + len(data)], data) if x != y)
        buf[off:off + len(data)] = data
        for sva, raw, rsize, h in _section_map(payload):
            if raw <= off < raw + rsize:
                touched.add((raw, rsize, h))
    for raw, rsize, h in touched:
        digest = hashlib.sha1(struct.pack("<I", rsize) + bytes(buf[raw:raw + rsize])).digest()  # nosec B324
        buf[h + 36:h + 56] = digest
    out = bytes(buf)
    require(xbe_status(out) == "applied" and xbe_tables(out) == table, "rookie faces executable read-back failed")
    return out, {"state": "applied", "changed_bytes": changed, "sections_repinned": len(touched),
                 "edits": [{"va": hex(va), "bytes": len(d), "label": label}
                           for (va, d), label in zip(_spans(table), SPAN_LABELS)]}


SPAN_LABELS = ("class generator skin/face draw -> jump + helpers", "class generator portrait pick",
               "rookie-face tables + code (retail generic range table)", "PORTRAIT record file name")


def reservations(payload: bytes) -> list[dict[str, Any]]:
    """The four owned spans of an applied executable, for the cave manifest."""
    require(xbe_status(payload) == "applied", "rookie faces are not applied")
    return [{"start": hex(va), "size": len(d), "owner": OWNER, "basis": "declared edit: " + label}
            for (va, d), label in zip(_spans(bytes(TABLE_DATA)), SPAN_LABELS)]


# ------------------------------------------------------------------------------------------------ portraits
RECORD_COUNT, RECORD_SLOT, RECORD_HASHES, RECORD_NAME_AT = 0x60, 0x64, 0x68, 0x20
SLOT = 0x4500
SPAN = 0x44A0                 # the TXTR wrapper inside a slot (17,568 bytes, then 96 zero bytes)
NAME_AT = 0x40                # resource name inside a slot (UTF-16LE, 12 bytes up to the descriptor at +0x4C)
NAME_BYTES = 12


def member_hash(name: str) -> int:
    return zlib.crc32(name.encode("utf-16le")) & 0xFFFFFFFF


def name_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


def parse_record(record: bytes) -> tuple[int, int, list[int]]:
    require(record[:4] == b"CACR", "the portrait record is not a CACR")
    count, slot = struct.unpack_from("<II", record, RECORD_COUNT)
    hashes = list(struct.unpack_from(f"<{count}I", record, RECORD_HASHES))
    require(hashes == sorted(hashes) and len(set(hashes)) == count, "the portrait record hashes are not sorted")
    return count, slot, hashes


def slot_name(slot: bytes) -> str:
    return slot[NAME_AT:NAME_AT + NAME_BYTES].decode("utf-16-le").split("\0")[0]


def make_slot(template: bytes, name: str, indices_linear: bytes, palette_rgba: bytes) -> bytes:
    """A portrait slot: the template's wrapper and system bytes, the new name, P8 swizzled indices and BGRA palette."""
    from tools import nfl_txtr as tx  # noqa: PLC0415 - tools is a namespace package next to mod_editor
    require(len(template) == SLOT and template[:4] == b"TXTR", "foreign portrait template")
    require(len(indices_linear) == 128 * 128 and len(palette_rgba) == 1024, "a face must be 128x128 P8")
    require(len(name) <= 5 and name.isdigit(), "portrait names are numbers of at most five digits")
    out = bytearray(template)
    out[NAME_AT:NAME_AT + NAME_BYTES] = name.encode("utf-16-le").ljust(NAME_BYTES, b"\0")
    chunk = tx.parse_chunks(bytes(out[:SPAN]), allow_trailing=True)[0]
    decoded, _ = tx.decode_chunk(bytes(out[:SPAN]), chunk)
    texture = tx.parse_texture(decoded, chunk)
    require(texture.width == texture.height == 128 and texture.format_name == "P8" and texture.mip_levels == 1,
            "the template is not a 128x128 P8 portrait")
    base = 32 + chunk.system_bytes
    out[base + texture.pixel_offset:base + texture.pixel_offset + 16384] = tx.swizzle_2d(indices_linear, 128, 128, 1)
    pal = bytearray(palette_rgba)
    for k in range(256):
        r, g, b, a = pal[4 * k:4 * k + 4]
        pal[4 * k:4 * k + 4] = bytes((b, g, r, a))
    out[base + texture.palette_offset:base + texture.palette_offset + 1024] = pal
    return bytes(out)


def face_pixels(rgb: bytes) -> tuple[bytes, bytes]:
    """(linear indices, RGBA palette) of a 128x128 RGB face with at most 256 colours (the shipped faces are)."""
    require(len(rgb) == 128 * 128 * 3, "a face is 128x128 RGB")
    colours = sorted({rgb[i:i + 3] for i in range(0, len(rgb), 3)})
    require(len(colours) <= 256, "a face has more than 256 colours")
    lookup = {c: k for k, c in enumerate(colours)}
    indices = bytes(lookup[rgb[i:i + 3]] for i in range(0, len(rgb), 3))
    palette = b"".join(c + b"\xff" for c in colours).ljust(1024, b"\0")
    return indices, palette


def bank_faces(bank: Mapping[str, Any]) -> Iterable[tuple[int, bytes]]:
    """(portrait id, 128x128 RGB) for every bank face. Each atlas ``faces_NN.png`` holds 16 x 16 cells of 8-bit palette
    indices and ``faces_NN_pal.png`` one 256-colour RGB palette row per cell (both sha256-pinned in bank.json)."""
    import io  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    files = {}
    for sheet in bank["atlases"]:
        data = (DATA_DIR / sheet["file"]).read_bytes()
        require(sha(data) == sheet["sha256"], f"{sheet['file']} does not match its pin")
        files[sheet["file"]] = Image.open(io.BytesIO(data))
    for face in bank["faces"]:
        index = files[face["atlas"]]
        palette = files[face["atlas"][:-4] + "_pal.png"].convert("RGB")
        col, row = face["cell"]
        require(index.mode == "L", "a face atlas must be 8-bit indices")
        cell = index.crop((col * 128, row * 128, col * 128 + 128, row * 128 + 128)).tobytes()
        pal = palette.crop((0, row * 16 + col, 256, row * 16 + col + 1)).tobytes()
        yield face["id"], b"".join(pal[3 * i:3 * i + 3] for i in cell)


def build_portraits(record: bytes, cdf: bytes, faces: Iterable[tuple[int, bytes]]) -> tuple[bytes, bytes, int]:
    """(new record named CDF_NAME, new aggregate, faces added): every existing slot plus one per face, hash-sorted."""
    count, slot, hashes = parse_record(record)
    require(slot == SLOT and len(cdf) == count * SLOT, "the portrait aggregate does not match its record")
    slots = {h: cdf[i * SLOT:(i + 1) * SLOT] for i, h in enumerate(hashes)}
    template = None
    for h in hashes:
        if slot_name(slots[h]).isdigit():
            template = slots[h]
            break
    require(template is not None, "no numeric portrait to copy the slot layout from")
    added = 0
    for pid, rgb in faces:
        name = f"{pid:04d}"
        h = member_hash(name)
        require(h not in slots, f"portrait {name} already exists on this image")
        indices, palette = face_pixels(rgb)
        slots[h] = make_slot(template, name, indices, palette)
        added += 1
    order = sorted(slots)
    new_record = bytearray(record[:RECORD_HASHES])
    struct.pack_into("<I", new_record, RECORD_COUNT, len(order))
    new_record[RECORD_NAME_AT:RECORD_NAME_AT + 0x40] = CDF_NAME.encode("utf-16-le").ljust(0x40, b"\0")
    new_record += struct.pack(f"<{len(order)}I", *order) + bytes(20)
    struct.pack_into("<I", new_record, 4, len(new_record) - 32)
    return bytes(new_record), b"".join(slots[h] for h in order), added


# ------------------------------------------------------------------------------------------------ the image
FILLER = "rh1_faces_end.bin"


def _archive_entries(path: Path | str):
    from tools.nfl2k5_playbook_position_recode import OuterImage  # noqa: PLC0415
    return OuterImage(Path(path))


def roster_photo_ids(path: Path | str) -> set[int]:
    """Every portrait id any ROST resource on the image names (main, historic, moment and classic rosters)."""
    from . import nfl2k5_roster_records as rr  # noqa: PLC0415
    out: set[int] = set()
    with _archive_entries(path) as archive:
        for entry in archive.entries:
            if entry.size < 0x100 or archive.read(entry.virtual_offset, 4) != b"ROST":
                continue
            data = archive.read(entry.virtual_offset, entry.size)
            try:
                doc = rr.RosterDocument(data[0x20:], base=0)
            except Exception as exc:  # noqa: BLE001 - a ROST this reader does not know is reported, not guessed
                raise RookieFacesError(f"a roster resource ({entry.name_id:#x}) cannot be read: {exc}") from exc
            out.update(p.record.values["photo_id"] for p in doc.players)
    return out


def pool_names(body: bytes) -> tuple[list[str], list[str]]:
    """The generated-player name pool of a ROST body, read the way the game reads it: count at +0x90, the entry array
    through the field-relative pointer at +0x94 (later build steps relocate it when the player table grows), each
    entry two field-relative pointers to NUL-terminated UTF-16 strings."""
    count = struct.unpack_from("<I", body, 0x90)[0]
    require(count == POOL_COUNT, f"the name pool holds {count} entries, not {POOL_COUNT}")
    array = 0x94 + struct.unpack_from("<i", body, 0x94)[0] - 1
    require(0 < array and array + 8 * count <= len(body), "the name pool array is outside the roster")

    def text(field: int) -> str:
        at = field + struct.unpack_from("<i", body, field)[0] - 1
        end = at
        require(0 < at < len(body) and not at & 1, "a pool name points outside the roster")
        while body[end:end + 2] != b"\0\0":
            end += 2
            require(end + 2 <= len(body) and end - at <= 64, "a pool name is not terminated")
        return body[at:end].decode("utf-16-le")
    firsts = [text(array + 8 * i) for i in range(count)]
    lasts = [text(array + 8 * i + 4) for i in range(count)]
    return firsts, lasts


def _pool(path: Path | str) -> tuple[list[str], list[str]]:
    from . import nfl2k5_roster_records as rr  # noqa: PLC0415
    from . import nfl2k5_roster_arena as arena  # noqa: PLC0415
    with rr._outer_image()(path) as archive:
        if arena.grown_outer(archive, rr.ROST_OUTER_INDEX):
            resource = arena.inspection_resource(archive, rr.ROST_OUTER_INDEX)
        else:
            entry = rr._entry(archive)
            resource = archive.read(entry.virtual_offset, entry.size)
    return pool_names(resource[0x20:])


def _outer(archive, name: str):
    wanted = name_id(name)
    for entry in archive.entries:
        if entry.name_id == wanted:
            return entry
    return None


def plan(path: Path | str, bank: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Everything apply_to_image writes, read from the image (nothing written)."""
    bank = bank or load_bank()
    firsts, lasts = _pool(path)
    table = tables(firsts, lasts, bank)
    ids = bank_ids(bank)
    require(len(ids) == len(set(ids)) == len(bank["faces"]), "bank ids and faces disagree")
    used = roster_photo_ids(path)
    clash = sorted(set(ids) & used)
    require(not clash, f"rosters on this image already use portrait ids {clash[:8]}: the rookie bank cannot take them")
    with _archive_entries(path) as archive:
        record_entry, cdf_entry = _outer(archive, RETAIL_RECORD_NAME), _outer(archive, RETAIL_CDF_NAME)
        require(record_entry is not None and cdf_entry is not None, "the image has no Portrait.iff / portrait.cdf")
        record = archive.read(record_entry.virtual_offset, record_entry.size)
        cdf = archive.read(cdf_entry.virtual_offset, cdf_entry.size)
        present = {e.name_id for e in archive.entries}
    taken = set(parse_record(record)[2])
    require(not ({member_hash(f"{i:04d}") for i in ids} & taken), "a bank id already has a portrait on this image")
    new_record, new_cdf, added = build_portraits(record, cdf, bank_faces(bank))
    return dict(table=table, record=new_record, cdf=new_cdf, added=added,
                exists=(name_id(RECORD_NAME) in present, name_id(CDF_NAME) in present),
                pool_nick0=nick0(firsts, load_names()))


def apply_to_image(path: Path | str, read_xbe: Callable[[Path], bytes], write_xbe: Callable[[Path, bytes], None], *,
                   bank: Mapping[str, Any] | None = None,
                   progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Add the bank to a disc image COPY: new portrait record + aggregate, then the executable."""
    from . import nfl2k5_historic_styles as hs  # noqa: PLC0415
    say = progress or (lambda _m: None)
    path = Path(path)
    payload = read_xbe(path)
    require(xbe_status(payload) == "retail", f"the generator bytes are {xbe_status(payload)}; rebuild from a clean image")
    say("Rookie faces: reading rosters and portraits")
    p = plan(path, bank)
    require(not any(p["exists"]), "the image already carries a rookie-face record or aggregate")
    appended = [(RECORD_NAME, p["record"]), (CDF_NAME, p["cdf"]), (FILLER, bytes(2048))]
    say(f"Rookie faces: writing {p['added']} new portraits")
    disc = hs.rewrite_archive(path, {}, appended)
    patched, xbe_receipt = xbe_apply(payload, p["table"])
    write_xbe(path, patched)
    state = image_status(path, read_xbe, bank=bank)
    require(state == "applied", f"rookie faces read-back: {state}")
    return {"state": state, "faces_added": p["added"], "record": RECORD_NAME, "aggregate": CDF_NAME,
            "record_bytes": len(p["record"]), "aggregate_bytes": len(p["cdf"]),
            "record_sha256": sha(p["record"]), "aggregate_sha256": sha(p["cdf"]), "nick0": p["pool_nick0"],
            "table_sha256": sha(p["table"]), "xbe": xbe_receipt,
            "archive": {k: v for k, v in disc.items() if k != "packs"}}


def image_status(path: Path | str, read_xbe: Callable[[Path], bytes], *,
                 bank: Mapping[str, Any] | None = None) -> str:
    """retail | applied | foreign: the executable half, the new record and aggregate, and every bank face."""
    state = xbe_status(read_xbe(Path(path)))
    with _archive_entries(path) as archive:
        record_entry, cdf_entry = _outer(archive, RECORD_NAME), _outer(archive, CDF_NAME)
        if state == "retail":
            return "retail" if record_entry is None and cdf_entry is None else "foreign"
        if state != "applied" or record_entry is None or cdf_entry is None:
            return "foreign"
        record = archive.read(record_entry.virtual_offset, record_entry.size)
        count, slot, hashes = parse_record(record)
        if slot != SLOT or cdf_entry.size != count * SLOT:
            return "foreign"
        if record[RECORD_NAME_AT:RECORD_NAME_AT + 2 * len(CDF_NAME)] != CDF_NAME.encode("utf-16-le"):
            return "foreign"
        bank = bank or load_bank()
        index = {h: i for i, h in enumerate(hashes)}
        for pid in bank_ids(bank):
            name = f"{pid:04d}"
            i = index.get(member_hash(name))
            if i is None:
                return "foreign"
            head = archive.read(cdf_entry.virtual_offset + i * SLOT + NAME_AT, NAME_BYTES)
            if head.decode("utf-16-le").split("\0")[0] != name:
                return "foreign"
    return "applied"
