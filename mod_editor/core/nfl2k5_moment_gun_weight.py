"""Era-correct shotgun weight for the ESPN 25th Anniversary moments (job a4, beta 77). EXPERIMENTAL / UNWITNESSED.

Noah, 2026-10-08, playing the Mile High Miracle: "broncos are not in shotgun, playbooks are awful". The book each side
loads is decided by ``nfl2k5_stock_books`` (a side whose season word is 2005 or later gets its franchise's current book,
an older side gets the preserved retail bank). What that does not decide is how often the CPU *calls* a shotgun set from
the book it has, and that is a retail engine rule, not book data:

    0x207EF0 (the formation weight the CPU's formation lottery and personnel lottery both use) returns the constant
    0.05 (``fld [0x4E6D10]`` at 0x207F99) for every offensive shotgun or pistol set whenever the ball is more than
    10 yards from the goal line, whatever the set's own ratings say.

So in every book a shotgun set is nearly invisible between the 20s, however many it holds (u-ai map section 2.3; the
v0.5 Broncos book called shotgun on 3 percent of first downs by the analytic selector, the p48o v2 book 26 percent,
while Peyton Manning's 2012 Broncos snapped from the gun on 47 percent of first downs, nflverse). The rule is retail
behaviour that suits retail books and the 2004 season (league shotgun share 13 percent); it is wrong for 2012 and later.

This module owns the *bytes* of the fix; ``nfl2k5_stock_books`` places them (it owns the 1,536 byte allocation they live in,
so no new allocation is needed: the executable's code pages have no room for a new owner once F4 and F4b are in). The
single ``fld`` becomes a call to a 34 byte stub::

    cmp  dword [0xE5FF80], 8      ; game mode 8 = ESPN 25th Anniversary
    jne  ordinary
    mov  eax, [0xBF1858]          ; the selected moment's physical row (0..50), the same word 62902 and 62C96 read
    cmp  eax, 51
    jae  ordinary
    fld  dword [table + eax*4]    ; this moment's weight
    ret
  ordinary:
    fld  dword [0x4E6D10]         ; exactly the retail 0.05
    ret

Outside Anniversary mode (b77-a4 follow-up) the stub looks the offense team up by its franchise key (the string the book resolver
reads) in a 32-entry table of per-franchise weights fitted to the real 2025 and 2026 nflverse shotgun rates by down and distance;
a historic or Anniversary side (category word 4), a franchise the data marks classic and a key the 32 rows do not know get the
retail constant, as do the inside-the-10 and goal-line cases, which the rule never touched. The stub's team test::

    mov  eax, [esp+0x20]          ; argument 1 of 0x207EF0 = the live team (its +0x20 is its book)
    mov  eax, [eax+0x1c]          ; the live team's roster record, NOT the live object itself
    cmp  dword [eax+0x128], 4     ; category 4: historic or Anniversary side -> ordinary
    mov  edx, [[eax+0x110]+4]     ; roster franchise key string; scan the owner's 32 key rows

The weights then follow the team; a QB or coach archetype is not modelled. (That was the first franchise generation: one weight per team.)

b77-a4pd (third generation): the franchise weight is looked up per team AND per down and distance bin. After the key scan the stub
reads the live down (``[[0xE602EC]+4]``) and, for 2nd to 4th down, the yards to go from the game's own function 0x207950 (the one the
personnel curve 0x207E30 uses; it reads the line of scrimmage and the first-down marker), and picks one of seven bins: 1st down at any
distance; 2nd down 1-3 / 4-7 / 8+ yards; 3rd and 4th down 1-3 / 4-6 / 7+ yards (distance in whole yards: the float is cut at half yards,
3.5 / 7.5 / 6.5 yd). The weight is ``uint16 * 0.05`` from a 32 x 7 table (14 bytes per franchise, rows in the order of the key rows).
Inside the 10 and at the goal line nothing changes (the stub is only reached beyond 10 yards), and a down outside 1..4 gets the retail
constant. Anniversary mode, category 4 sides and unknown keys are exactly as in the earlier generation. The 51 weights are data (``data/nfl2k5_moment_playbook_eras.json``, key ``gun_weight`` per row): 0.05 for
every moment whose side keeps a classic book, and for the modern ones a number chosen so the CPU side's shotgun share
in the analytic selector approaches the sourced real rate of that team-season. The weight applies to both sides of the
match; it is fitted to the side the CPU plays (the user's own team never uses the lottery).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from typing import Mapping

from .nfl2k5_cave_oracle import XbeImage

EVIDENCE = "EXPERIMENTAL"
DATA = Path(__file__).resolve().parents[2] / "data/nfl2k5_moment_playbook_eras.json"
SCHEMA = "b77/a4_moment_playbook_eras/v2"
MOMENT_COUNT = 51
TABLE_SIZE = 4 * MOMENT_COUNT
ROW_WORD = 0x00BF1858              # the selected moment's physical row, written by the select handler 20CB30
MODE_WORD = 0x00E5FF80             # 8 = ESPN 25th Anniversary
RETAIL_WEIGHT_VA = 0x004E6D10      # the retail 0.05 constant (about 230 other readers: never edited)
RETAIL_WEIGHT_BYTES = bytes.fromhex("cdcc4c3d")
RETAIL_WEIGHT = struct.unpack("<f", RETAIL_WEIGHT_BYTES)[0]
SITE_VA = 0x00207F99
RETAIL_SITE = bytes.fromhex("d905106d4e00")          # fld dword ptr [0x4E6D10]
MIN_WEIGHT, MAX_WEIGHT = 0.05, 4.0
# SHA-256 of the retail bytes 0x207F72..0x207F98: cmp cl,3 / jg / the 0xC0000 flag test / jne 0x207FA7 (75 20) / the
# 10 yard test up to the site. If another job lifts or edits that rule, the install refuses instead of guessing.
RULE_SHA256 = "02173a4518fdce1296632cd98f9ac426cca0308bd948b8427d29035281fc79fe"


class MomentGunWeightError(ValueError):
    """Unsupported executable, foreign or mixed installation, or invalid weight data."""


def _require(condition, message):
    if not condition:
        raise MomentGunWeightError(message)


# ------------------------------------------------------------------------------------------------ data

def load(path: Path = DATA) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    _require(data.get("schema") == SCHEMA, "foreign moment playbook era data")
    return data


def weights(data: Mapping | None = None) -> list[float]:
    """The 51 per-row weights in physical row order (row 1 first), validated."""
    data = load() if data is None else data
    rows = sorted(data["moments"], key=lambda r: r["row"])
    _require([r["row"] for r in rows] == list(range(1, MOMENT_COUNT + 1)), "the era data must hold physical rows 1 to 51")
    out = []
    for r in rows:
        w = r["gun_weight"]
        _require(type(w) in (int, float) and MIN_WEIGHT <= w <= MAX_WEIGHT, f"row {r['row']}: gun_weight outside {MIN_WEIGHT}..{MAX_WEIGHT}")
        out.append(float(w))
    return out


def table_bytes(values) -> bytes:
    _require(len(values) == MOMENT_COUNT, "need 51 weights")
    for v in values:
        _require(MIN_WEIGHT <= v <= MAX_WEIGHT, "gun weight out of bounds")
    return b"".join(struct.pack("<f", v) for v in values)


def decode_table(raw: bytes) -> list[float]:
    _require(len(raw) == TABLE_SIZE, "weight table size")
    values = list(struct.unpack("<51f", raw))
    _require(all(MIN_WEIGHT <= v <= MAX_WEIGHT for v in values), "moment gun weight outside its bounds")
    return values


# ------------------------------------------------------------------------------------------------ bytes

TEAM_COUNT = 32
TEAM_TABLE_SIZE = 4 * TEAM_COUNT             # generation 2: one float32 per franchise
STUB_SPACE_SINGLE = 128            # generation 2 (single weight per franchise): bytes reserved for its stub
STUB_SPACE = 256                   # generation 3 (per bin): bytes reserved for the stub in the owner's allocation
CATEGORY_OFFSET, KEY_OFFSET = 0x128, 0x110       # ROSTER record, not the 0x3c-byte live team
ROSTER_OFFSET = 0x1C               # live team -> roster record; native initializer 0x87197 / 0x8719C
TEAM_ARG = 0x20                    # [esp+0x20] inside the stub = argument 1 of 0x207EF0, the offense team (its +0x20 is its book)
STATE_POINTER = 0x00E602EC         # the game's situation object: [+4] = down (1..4); the yards-to-go function reads its marker rows
TOGO_FUNCTION = 0x00207950         # returns the yards to go (game units, 91.44 per yard) in st0; the personnel curve 0x207E30 calls it
YARD = 91.44

BIN_NAMES = ("d1", "d2_short", "d2_mid", "d2_long", "d3_short", "d3_mid", "d3_long")
BIN_COUNT = len(BIN_NAMES)
BIN_UNIT = 0.05                    # table entries are uint16 multiples of 0.05
BIN_MAX_WEIGHT = 16.0
BIN_ROW_SIZE = 2 * BIN_COUNT
BIN_TABLE_SIZE = BIN_ROW_SIZE * TEAM_COUNT
# 2nd down cuts at 3.5 and 7.5 yd, 3rd and 4th down at 3.5 and 6.5 yd (float32 bits compare like integers for non-negative floats)
CUT_SHORT, CUT_SECOND_MID, CUT_THIRD_MID = (struct.unpack("<I", struct.pack("<f", y * YARD))[0] for y in (3.5, 7.5, 6.5))


def _stub_head(a, moment_table_va: int, *, live_team: bool = False) -> None:
    """The Anniversary part and the start of the franchise part, shared by both generations of the stub."""
    a.b("833d" + struct.pack("<I", MODE_WORD).hex() + "08")                 # cmp dword [mode], 8
    a.j8("75", "team")
    a.b("a1" + struct.pack("<I", ROW_WORD).hex())                           # mov eax, [row]
    a.b("83f8" + bytes([MOMENT_COUNT]).hex())                               # cmp eax, 51
    a.j8("73", "ordinary")
    a.b("d90485" + struct.pack("<I", moment_table_va).hex())               # fld dword [table + eax*4]
    a.b("c3")
    a.label("team")
    a.b("8b44" + "24" + bytes([TEAM_ARG]).hex())                           # mov eax, [esp+0x20]  (the offense team)
    a.b("85c0")
    a.j8("74", "ordinary")
    if live_team:
        # 0x207EF0 receives E5FC20/E5FC60. Their +0x110/+0x128 lie in
        # the PRNG state, so the old stub dereferenced a random integer.
        a.b("8b40" + bytes([ROSTER_OFFSET]).hex() + "85c0")
        a.j8("74", "ordinary")
    a.b("83b8" + struct.pack("<I", CATEGORY_OFFSET).hex() + "04")           # cmp dword [eax+0x128], 4
    a.j8("74", "ordinary")
    a.b("8b90" + struct.pack("<I", KEY_OFFSET).hex() + "85d2")             # mov edx, [eax+0x110] / test edx, edx
    a.j8("74", "ordinary")
    a.b("8b520485d2")                                                       # mov edx, [edx+4] / test edx, edx
    a.j8("74", "ordinary")


def _stub_scan(a, key_table_va: int) -> None:
    a.b("b9" + struct.pack("<I", key_table_va).hex())                       # mov ecx, key rows
    a.label("scan")
    a.b("8b023b01")                                                         # first two UTF-16 letters
    a.j8("75", "next")
    a.b("668b4204663b4104")                                                 # third letter or NUL
    a.j8("75", "next")
    a.b("6685c0")
    a.j8("74", "found")
    a.b("66837a0600")                                                       # a three-letter key must terminate
    a.j8("74", "found")
    a.label("next")
    a.b("83c108" + "81f9" + struct.pack("<I", key_table_va + 8 * TEAM_COUNT).hex())
    a.j8("72", "scan")
    a.label("ordinary")
    a.b(RETAIL_SITE.hex() + "c3")                                           # fld [0x4E6D10]; ret
    a.label("found")


def stub_bytes_single(stub_va: int, moment_table_va: int, key_table_va: int, team_table_va: int) -> bytes:
    """GENERATION 2 (job a4, one weight per franchise), kept so the earlier body can be recognised and completed in place."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(stub_va)
    _stub_head(a, moment_table_va)
    _stub_scan(a, key_table_va)
    a.b("81e9" + struct.pack("<I", key_table_va).hex() + "d1e9")            # sub ecx, key rows / shr ecx, 1  (= index * 4)
    a.b("d981" + struct.pack("<I", team_table_va).hex() + "c3")            # fld dword [ecx + team table]; ret
    out = a.assemble()
    _require(len(out) <= STUB_SPACE_SINGLE, "stub exceeds its space")
    return out.ljust(STUB_SPACE_SINGLE, b"\xcc")


def stub_bytes(stub_va: int, moment_table_va: int, key_table_va: int, bin_table_va: int,
               *, legacy_team_pointer: bool = False) -> bytes:
    """The stub (padded to STUB_SPACE) for the given tables.

    Mode 8: the moment's weight. Otherwise: the offense team's weight if it is a current franchise (category word not 4) whose
    franchise key (``[[[live_team+0x1c]+0x110]+4]``) is one of the 32 keys of the owner's key rows, in the
    bin of the live down and yards to go; anything else gets the retail constant.
    ``legacy_team_pointer`` reproduces the faulty shipped a4pd bytes ONLY for exact upgrade recognition."""
    from .nfl2k5_draft_ai import _Asm
    a = _Asm(stub_va)
    _stub_head(a, moment_table_va, live_team=not legacy_team_pointer)
    _stub_scan(a, key_table_va)
    a.b("81e9" + struct.pack("<I", key_table_va).hex() + "c1e903" + "6bc9" + bytes([BIN_ROW_SIZE]).hex())   # sub ecx,rows / shr ecx,3 / imul ecx,ecx,14
    a.b("a1" + struct.pack("<I", STATE_POINTER).hex() + "8b4004" + "48")   # mov eax,[state] / mov eax,[eax+4] (down) / dec eax
    a.j8("74", "first")                                                     # 1st down: bin 0 at any distance
    a.b("83f803")                                                           # cmp eax, 3  (down-1 as unsigned: 0 and 5+ fail)
    a.j8("77", "ordinary")
    a.b("5150" + "55" + "8bec" + "83ec20" + "83e4f0")                      # push ecx / push eax / push ebp / mov ebp,esp / sub esp,32 / and esp,-16
    a.b("8bcc" + "8d542410")                                                # mov ecx,esp / lea edx,[esp+16]  (two aligned 16 byte rows)
    a.call(TOGO_FUNCTION)                                                   # st0 = yards to go (game units)
    a.b("8be5" + "5d")                                                      # mov esp,ebp / pop ebp
    a.b("50" + "d91c24" + "5a" + "58" + "59")                              # push eax / fstp dword [esp] / pop edx (distance bits) / pop eax / pop ecx
    a.b("83f801" + "b801000000")                                            # cmp eax,1 / mov eax,1  (2nd down: base bin 1)
    a.j8("75", "third")
    a.b("81fa" + struct.pack("<I", CUT_SHORT).hex())                        # cmp edx, 3.5 yd
    a.j8("76", "pick")
    a.b("40" + "81fa" + struct.pack("<I", CUT_SECOND_MID).hex())            # inc eax / cmp edx, 7.5 yd
    a.j8("76", "pick")
    a.b("40")                                                               # inc eax
    a.j8("eb", "pick")
    a.label("third")
    a.b("b804000000" + "81fa" + struct.pack("<I", CUT_SHORT).hex())         # mov eax,4 / cmp edx, 3.5 yd
    a.j8("76", "pick")
    a.b("40" + "81fa" + struct.pack("<I", CUT_THIRD_MID).hex())             # inc eax / cmp edx, 6.5 yd
    a.j8("76", "pick")
    a.b("40")                                                               # inc eax
    a.j8("eb", "pick")
    a.label("first")
    a.b("31c0")                                                             # xor eax, eax
    a.label("pick")
    a.b("8d0c41" + "df81" + struct.pack("<I", bin_table_va).hex())          # lea ecx,[ecx+eax*2] / fild word [ecx + bin table]
    a.b("d80d" + struct.pack("<I", RETAIL_WEIGHT_VA).hex() + "c3")         # fmul dword [0.05] / ret
    out = a.assemble()
    _require(len(out) <= STUB_SPACE, "stub exceeds its space")
    return out.ljust(STUB_SPACE, b"\xcc")


def team_table_bytes(values) -> bytes:
    """GENERATION 2: one float32 weight per franchise."""
    _require(len(values) == TEAM_COUNT, "need 32 team weights")
    for v in values:
        _require(MIN_WEIGHT <= v <= MAX_WEIGHT, "team gun weight out of bounds")
    return b"".join(struct.pack("<f", v) for v in values)


def decode_team_table(raw: bytes) -> list[float]:
    _require(len(raw) == TEAM_TABLE_SIZE, "team weight table size")
    values = list(struct.unpack("<32f", raw))
    _require(all(MIN_WEIGHT <= v <= MAX_WEIGHT for v in values), "team gun weight outside its bounds")
    return values


def bin_units(weight) -> int:
    """The table entry (a multiple of 0.05) of one bin weight; refuses a weight that is off the grid or out of bounds."""
    _require(type(weight) in (int, float) and MIN_WEIGHT - 1e-9 <= weight <= BIN_MAX_WEIGHT + 1e-9, f"bin gun weight {weight!r} outside {MIN_WEIGHT}..{BIN_MAX_WEIGHT}")
    units = round(weight / BIN_UNIT)
    _require(abs(units * BIN_UNIT - weight) < 1e-6, f"bin gun weight {weight!r} is not a multiple of {BIN_UNIT}")
    return units


def bin_table_bytes(rows) -> bytes:
    """GENERATION 3: 32 franchise rows of 7 uint16 multiples of 0.05, bins in ``BIN_NAMES`` order."""
    _require(len(rows) == TEAM_COUNT and all(len(r) == BIN_COUNT for r in rows), "need 32 rows of 7 bin weights")
    return b"".join(struct.pack("<7H", *(bin_units(w) for w in row)) for row in rows)


def decode_bin_table(raw: bytes) -> list[list[float]]:
    _require(len(raw) == BIN_TABLE_SIZE, "bin weight table size")
    rows = []
    for i in range(TEAM_COUNT):
        units = struct.unpack_from("<7H", raw, i * BIN_ROW_SIZE)
        _require(all(1 <= u <= round(BIN_MAX_WEIGHT / BIN_UNIT) for u in units), "bin gun weight outside its bounds")
        rows.append([round(u * BIN_UNIT, 2) for u in units])
    return rows


def team_weights(data: Mapping | None = None, keys=None) -> list[float]:
    """GENERATION 2: one weight per franchise (the data file's v1 ``gun_weight``); kept for the earlier body's tests only."""
    data = load() if data is None else data
    teams = data.get("teams", {})
    out = []
    for key in keys:
        row = teams.get(key)
        w = MIN_WEIGHT if not row or row.get("classic") else row["gun_weight"]
        _require(type(w) in (int, float) and MIN_WEIGHT <= w <= MAX_WEIGHT, f"team {key}: gun_weight outside {MIN_WEIGHT}..{MAX_WEIGHT}")
        out.append(float(w))
    return out


def team_bin_weights(data: Mapping | None = None, keys=None) -> list[list[float]]:
    """The 32 x 7 weights in the order of ``keys`` (the book resolver's key rows) and ``BIN_NAMES``. A franchise the data does not
    name, or names as ``classic``, keeps the retail 0.05 in every bin (classic books and pre-2005 seasons keep retail behaviour)."""
    data = load() if data is None else data
    teams = data.get("teams", {})
    out = []
    for key in keys:
        row = teams.get(key)
        if not row or row.get("classic"):
            out.append([MIN_WEIGHT] * BIN_COUNT)
            continue
        weights = row["gun_weights"]
        _require(sorted(weights) == sorted(BIN_NAMES), f"team {key}: gun_weights must name exactly the seven bins")
        out.append([float(weights[name]) for name in BIN_NAMES])
        bin_units(out[-1][0])
        for w in out[-1]:
            bin_units(w)
    return out


def sites(stub_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes)."""
    return [("shotgun_weight_fld", SITE_VA, RETAIL_SITE, b"\xe8" + struct.pack("<i", stub_va - (SITE_VA + 5)) + b"\x90")]


def check_rule(image: XbeImage) -> None:
    """The shotgun rule around the site, and the retail constant, are exactly the retail bytes."""
    body = image.read(0x00207F72, SITE_VA - 0x00207F72)
    _require(hashlib.sha256(body).hexdigest() == RULE_SHA256, "foreign shotgun rule bytes in 0x207EF0")
    _require(image.read(RETAIL_WEIGHT_VA, 4) == RETAIL_WEIGHT_BYTES, "foreign retail weight constant")


def site_state(image: XbeImage, stub_va: int | None) -> str:
    """"retail" | "applied" for the one call site (anything else raises)."""
    actual = image.read(SITE_VA, len(RETAIL_SITE))
    if actual == RETAIL_SITE:
        return "retail"
    _require(stub_va is not None and actual == sites(stub_va)[0][3], "foreign shotgun weight site")
    return "applied"


__all__ = ["DATA", "MomentGunWeightError", "MOMENT_COUNT", "STUB_SPACE", "STUB_SPACE_SINGLE", "TEAM_COUNT", "TEAM_TABLE_SIZE", "team_table_bytes", "decode_team_table",
           "team_weights", "team_bin_weights", "BIN_NAMES", "BIN_COUNT", "BIN_UNIT", "BIN_MAX_WEIGHT", "BIN_ROW_SIZE", "BIN_TABLE_SIZE", "bin_units", "bin_table_bytes",
           "decode_bin_table", "CUT_SHORT", "CUT_SECOND_MID", "CUT_THIRD_MID", "TABLE_SIZE", "SITE_VA", "RETAIL_SITE", "RETAIL_WEIGHT", "MIN_WEIGHT", "MAX_WEIGHT", "load",
           "weights", "table_bytes", "decode_table", "stub_bytes", "stub_bytes_single", "sites", "check_rule", "site_state"]
