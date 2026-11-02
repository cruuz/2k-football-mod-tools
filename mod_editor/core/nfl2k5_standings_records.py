"""Team Standings records view: division and conference records, plus home, road and streak (b780 j1-standings).

EXPERIMENTAL / UNWITNESSED in game. Players asked for it twice: CER, 2026-10-07: "A way to get division and confrence
records into the team standings page"; SWeaR wanted NBA 2K-style franchise records (2026-10-03, 10-10).

What the retail game has (static RE of the USA ``default.xbe``, job b780 r4-records report, section 2.2)
---------------------------------------------------------------------------------------------------------
* ESPN.com > Team Standings (descriptor 0x54CEA0) is drawn by its own code: draw 0x3554B0, input 0x3551A0, enter
  0x3550F0, legend 0x355CD0. Per conference it draws four division blocks; each club row has its name and the W, L and
  T counts (0xC7720 / 0xC7750 / 0xC7780 formatted by 0x4A400). L and R switch AFC and NFC; no other button is used.
* The same code also draws the realignment screen (enter 0x3550D0): the standings case is ``[0xAE9EE8] == 1``.
* The game keeps home and road records and the current streak for its inbox tables (0xC6B70, 0xC6C30, 0xC8200) but
  computes no division or conference record for display. Every score of the season is in the schedule grid (0xE57C40,
  22 rows of 17 cells, 8 bytes each; quarter scores 0xE587F0, 10 bytes a cell), so no save field is needed.
* Retail W, L and T add up every row of the grid, so after the playoffs they include playoff games (a retail quirk,
  left alone). DIV and CONF count only the rows before the playoffs: the byte at 0x5151C4 (17 retail, 18 with the
  season-length patch), as the NFL does.

What this owner adds
--------------------
* White and Black turn the columns of ESPN.com's Team Standings through three views, with the cursor sound:
  W L T (the retail screen, unchanged) -> DIV CONF -> HOME ROAD STRK -> W L T. Black goes forward, White back.
* DIV and CONF: the club's record against its own division and against its conference, regular season only ("4-2",
  "5-1-1"); a division game is also a conference game. Counted from the grid every frame, nothing is stored.
* HOME, ROAD and STRK are the game's own values (its inbox standings tables use them): home and road records over the
  same rows the retail W L T use, and the streak as "W3" or "L2" ("--" after a tie or with none).
* Header labels, the legend lines below the tables and the cell positions follow the view. Every visit to the screen
  opens on W L T. The realignment screen and every other screen are untouched.

Allocation: a late owner (``nfl2k5_xbe_space.LATE_OWNERS``, last): 2,048 code bytes and 16 RW bytes (the view).
Edits: input 0x35543F, three header labels, three cell formatters, four legend lines (all in 0x3551A0 / 0x3554B0 /
0x355CD0) and the enter pointer at 0x54CDB4. With the view at 0 every stub falls through to the retail routine.

Evidence: static RE, then the real draw and input code under Unicorn on the retail executable with the owner
installed (python3 -m unittest tests.mod_editor.test_nfl2k5_standings_records); an emulator still of each view is in
the job report. Not witnessed by a player.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping, Sequence

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_standings_records_code as runtime
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_standings_records"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 2048
DATA_SIZE = 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))

BUILD_CAPTION = "Team Standings: division, conference, home, road records"
HELP_TEXT = (
    "EXPERIMENTAL. Adds the records the retail Team Standings page never showed. On ESPN.com > Team Standings, "
    "White and Black turn the columns: W L T (as before), then DIV and CONF (your record against your own division "
    "and against your conference, regular season only), then HOME, ROAD and STRK (home record, road record and the "
    "current streak). The headers and the legend under the tables say which one you are looking at, and the page "
    "always opens on W L T. L and R still switch AFC and NFC. Nothing is saved: the numbers are worked out from the "
    "season's schedule every time the page draws. Off, the page is the retail page byte for byte.")

# the views, and the retail pad bits (the Player Card pages use the same ones: Black 0x1000, White 0x2000)
VIEWS = ("W L T", "DIV CONF", "HOME ROAD STRK")
BLACK, WHITE = 0x1000, 0x2000
STATE_VIEW_OFFSET = 0

# (label, VA, retail bytes, entry label, kind): "call" = call rel32, "callnop" = call rel32 plus NOP padding
SITE_TABLE = (
    ("input", 0x0035543F, bytes.fromhex("8b442414f6c4c0"), "sr_input", "call"),
    ("header_w", 0x00355903, bytes.fromhex("ba883ceb00"), "sr_hdr0", "call"),
    ("header_l", 0x0035592A, bytes.fromhex("ba8c3ceb00"), "sr_hdr1", "call"),
    ("header_t", 0x00355951, bytes.fromhex("ba903ceb00"), "sr_hdr2", "call"),
    ("cell_w", 0x00355B1E, bytes.fromhex("e8dd48cfff"), "sr_cell0", "call"),
    ("cell_l", 0x00355B68, bytes.fromhex("e89348cfff"), "sr_cell1", "call"),
    ("cell_t", 0x00355BB2, bytes.fromhex("e84948cfff"), "sr_cell2", "call"),
    ("legend_1", 0x00355D39, bytes.fromhex("ba9c3ceb00"), "sr_leg0", "call"),
    ("legend_2", 0x00355D5F, bytes.fromhex("bad43ceb00"), "sr_leg1", "call"),
    ("legend_3", 0x00355D85, bytes.fromhex("ba0c3deb00"), "sr_leg2", "call"),
    ("legend_4", 0x00355DAB, bytes.fromhex("ba483deb00"), "sr_leg3", "call"),
)
# the Team Standings enter callback in its event descriptor (retail FUN_003550F0)
ENTER_POINTER = (0x0054CDB4, 0x003550F0, "sr_enter")

# Retail spans the stubs and the runtime depend on, pinned by SHA-256 of their retail bytes: the screen's three
# functions and helpers (the stubs rely on its frame offsets), its event descriptors, the game's text calls, the cursor
# sound, the league and schedule-cell readers the runtime's raw reads rest on, the home / road / streak routines it calls
# and the division -> conference table. Spans that hold this owner's own edits are masked back to retail first.
GUARDS = (
    ("standings screen", 0x00355000, 0xDC0),
    ("standings descriptors", 0x0054CC60, 0x240),
    ("text font", 0x000469B0, 0x24),
    ("text position", 0x00046A70, 0x40),
    ("text width", 0x00046C50, 0x52),
    ("font table", 0x000EF850, 8),
    ("menu cursor sound", 0x0014D390, 0x2E),
    ("sound lookup", 0x00038650, 0x10),
    ("sound play", 0x00089DA0, 0x10),
    ("league mode", 0x000C4B80, 6),
    ("club count", 0x000C4BE0, 0x30),
    ("club by index", 0x000C4C50, 0x50),
    ("club index", 0x000C4CA0, 0x40),
    ("cell home club", 0x000C4E00, 0x12),
    ("cell away club", 0x000C4E20, 0x12),
    ("cell address", 0x000C4F10, 0xD),
    ("cell status", 0x000C4FD0, 0x80),
    ("status byte", 0x001C1C70, 3),
    ("cell home points", 0x000C5110, 0x36),
    ("cell away points", 0x000C5150, 0x36),
    ("club division", 0x000C6480, 0x17),
    ("home record", 0x000C6B70, 0xB5),
    ("road record", 0x000C6C30, 0xB5),
    ("win streak", 0x000C78D0, 0x8D),
    ("loss streak", 0x000C7960, 0x8D),
    ("conference table", 0x004F0FE0, 0x20),
)
GUARD_SHA256_PINNED = {
    "standings screen": "b8ba149d6c668bbba1042822e7ebdfe30c54cf650d385d0f87169e970acf4457",
    "standings descriptors": "382b6ef0b4b5398a92d5f397bb051b9f4fc97f71015c1a563cd2bf67cca9b55c",
    "text font": "5af8ad0a8008d7338a8516c6367054fd3b3217952b3755c61d4a3532277f2b06",
    "text position": "609c0623574545c3cd4d670b7fa88fc8d2645e4708fd5c09afed1c2c97f92633",
    "text width": "d473ba402936abbdf3c8dc72f0e5f705054042858be60046541103bd838d9eb3",
    "font table": "2b749cc28858f48edd6c85faf49916486d941f55a861696947a0ab14cb1946e4",
    "menu cursor sound": "d11593dfc0c387e618406b33f9b79fac52d1dc3b44bb28b96dc778c5e0f3d112",
    "sound lookup": "e3748cb7822a5af10d575696311650ef9305a14bd68438172ff70d41551fe455",
    "sound play": "7d7a843ebe16c862c0a1b68a60fb3dac9b899497961b0f7481b51f5eceb65b1b",
    "league mode": "ea571d62a509b72a0a8afeb1ce87e10afb9b23fe864a4f34521e3a467052a60a",
    "club count": "7c45cec0d593b35c7999f211d6ebc1f2aa91c7c90fc5d8d17993c165419e4f32",
    "club by index": "bf4afd3d901ae05431add7119322ba12f7d246f0322e194cdd9c47ace0faca0c",
    "club index": "b9492612c41c8ebe2f6a64de893f9b72e03124f3738564c3c4de9678a5c48a53",
    "cell home club": "85b4401e850c9a15ab8d953502a50a19a5c5cf14e909987422b9a78157dea3b0",
    "cell away club": "9a29fc4c3b49d2b68d0f2b3af8b4c25ae6a766d69331ee91f204e2d07dc424d9",
    "cell address": "d5ad895b67c726ab60b8eb71af00988b5ed29297e8a4e8e93e69143a1f98cc62",
    "cell status": "4cdd040f4cff4da8422c1b68b4c098eaa496c795cb151b35547affee6df93ef5",
    "status byte": "89573367e4d6d90bd23cb821d47376e7295f82c3e3094792990e764c13d75588",
    "cell home points": "7602534cb462964558267d05bb6b12bb885f271c9a5a5510525f958f9383773d",
    "cell away points": "062a264af2bf7428751275cdebc248618869ad7153369f80ea69f2f19d0249c7",
    "club division": "d5a2b03ec60fb6f7e72095f4e4a6193e22cd48a3f99c74c0dafe5f1e70904561",
    "home record": "dfd038a35eb10e6d5a71803bc919a191eab4f4484598fbd76e8df6c088199d36",
    "road record": "1eac0aaafcd2082f520f18cbb8c0c2c6259f12cf27fe0630d7ecca5996a62834",
    "win streak": "2f218df9316b65e5bfe39918f1b74816fbfca299fb17ed5c63c8da5ff933d6fc",
    "loss streak": "3ff34eecfbe17c99d10cc571439ae148e5b2e33fee629ab88b59877af71cc6e3",
    "conference table": "b0da5b1bd2e6f3d76a2e9cc5e7ac9abba91737dd877305d6e06e252d024e40ef",
}
# the regular-season row count the runtime reads (17 retail, 18 with the season-length patch): not pinned by hash,
# bounded here (nfl2k5_season_length and nfl2k5_playoffs14 own the byte)
WEEKS_VA = 0x005151C4
WEEKS_ALLOWED = (17, 18)

# ---- the model: what the screen must show, from the season's schedule grid ----------------------------------------------

CLUBS = 32
DIVISIONS = 8
GRID_ROWS = 22
GRID_SLOTS = 17
GRID_VA, SCORES_VA, DIVISIONS_VA = 0x00E57C40, 0x00E587F0, 0x00E576D4
CONFERENCE_TABLE_VA = 0x004F0FE0
# division -> conference (the table at 0x4F0FE0): NFC divisions 0-3 are conference 1, AFC divisions 4-7 conference 0
CONFERENCE_OF_DIVISION = (1, 1, 1, 1, 0, 0, 0, 0)
PLAYED = 3          # the status byte of a played cell (byte 0); byte 1 is the home club, byte 2 the away club


def _cell_games(grid: bytes, scores: bytes, rows: int):
    """Every played game of the first ``rows`` rows as (row, slot, home, away, home_points, away_points)."""
    if len(grid) < GRID_ROWS * GRID_SLOTS * 8 or len(scores) < GRID_ROWS * GRID_SLOTS * 10:
        raise ValueError("schedule grid or score table is too short")
    for row in range(min(rows, GRID_ROWS)):
        for slot in range(GRID_SLOTS):
            cell = row * GRID_SLOTS + slot
            if grid[8 * cell] != PLAYED:
                continue
            home, away = grid[8 * cell + 1], grid[8 * cell + 2]
            home_points = sum(scores[10 * cell:10 * cell + 5])
            away_points = sum(scores[10 * cell + 5:10 * cell + 10])
            yield row, slot, home, away, home_points, away_points


def _tally(record: list, mine: int, theirs: int) -> None:
    record[0 if mine > theirs else 1 if mine < theirs else 2] += 1


def division_conference_records(grid: bytes, scores: bytes, divisions: Sequence[int], *, weeks: int = 17) -> list[dict]:
    """The DIV and CONF records of the 32 clubs over the first ``weeks`` (regular-season) rows.

    ``grid`` and ``scores`` are the game's schedule grid (0xE57C40) and quarter scores (0xE587F0); ``divisions`` the
    division of each league club index (0xE576D4). Returns, per club, ``{"div": [w, l, t], "conf": [w, l, t]}``.
    A division game is also a conference game."""

    out = [{"div": [0, 0, 0], "conf": [0, 0, 0]} for _ in range(CLUBS)]
    for _row, _slot, home, away, home_points, away_points in _cell_games(grid, scores, weeks):
        if home >= CLUBS or away >= CLUBS or home == away:
            continue
        for me, other, mine, theirs in ((home, away, home_points, away_points), (away, home, away_points, home_points)):
            my_div, other_div = divisions[me], divisions[other]
            if my_div >= DIVISIONS:
                continue
            if other_div == my_div:
                _tally(out[me]["div"], mine, theirs)
            if other_div < DIVISIONS and CONFERENCE_OF_DIVISION[other_div] == CONFERENCE_OF_DIVISION[my_div]:
                _tally(out[me]["conf"], mine, theirs)
    return out


def home_road_records(grid: bytes, scores: bytes, *, rows: int = GRID_ROWS) -> list[dict]:
    """The game's own HOME and ROAD records (0xC6B70 / 0xC6C30) over ``rows`` grid rows (retail: all 22)."""

    out = [{"home": [0, 0, 0], "road": [0, 0, 0]} for _ in range(CLUBS)]
    for _row, _slot, home, away, home_points, away_points in _cell_games(grid, scores, rows):
        if home < CLUBS:
            _tally(out[home]["home"], home_points, away_points)
        if away < CLUBS:
            _tally(out[away]["road"], away_points, home_points)
    return out


def streaks(grid: bytes, scores: bytes, *, rows: int = GRID_ROWS) -> list[tuple[int, int]]:
    """The game's own (win streak, loss streak) of every club (0xC78D0 / 0xC7960): rows then cells in order; a win
    adds to the win streak and anything else clears it, likewise for losses (a tie clears both)."""

    wins, losses = [0] * CLUBS, [0] * CLUBS
    for _row, _slot, home, away, home_points, away_points in _cell_games(grid, scores, rows):
        for me, mine, theirs in ((home, home_points, away_points), (away, away_points, home_points)):
            if me >= CLUBS:
                continue
            wins[me] = wins[me] + 1 if mine > theirs else 0
            losses[me] = losses[me] + 1 if mine < theirs else 0
    return list(zip(wins, losses))


def format_record(record: Sequence[int]) -> str:
    """"W-L", or "W-L-T" when a game was tied: the game's own record format (formats 0xE68C28 / 0xE68C34)."""

    w, l, t = record
    return f"{w}-{l}-{t}" if t else f"{w}-{l}"


def format_streak(wins: int, losses: int) -> str:
    return f"W{wins}" if wins > 0 else f"L{losses}" if losses > 0 else "--"


# ---- the owner: install, status, sites ---------------------------------------------------------------------------------


class StandingsRecordsError(ValueError):
    """Unsupported executable, foreign or mixed installation."""


def _require(ok, message):
    if not ok:
        raise StandingsRecordsError(message)


def labels(code_va: int) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def code_for(code_va: int, data_va: int) -> bytes:
    """The owned RX content with the template's relocations applied, padded to CODE_SIZE with int3."""

    symbols = {"code": code_va, "state": data_va}
    out = bytearray(runtime.CODE)
    for off, kind, symbol, value in runtime.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<i", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    _require(len(out) <= CODE_SIZE, "the standings runtime exceeds its fixed budget")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes)."""

    at = labels(code_va)
    out = []
    for label, va, before, entry, _kind in SITE_TABLE:
        after = b"\xe8" + struct.pack("<i", at[entry] - (va + 5))
        after += b"\x90" * (len(before) - len(after))
        out.append((label, va, before, after))
    return out


def data_edits(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """The one table edit: the enter callback in the Team Standings event descriptor (.rdata)."""

    va, retail, entry = ENTER_POINTER
    return [("enter_pointer", va, struct.pack("<I", retail), struct.pack("<I", labels(code_va)[entry]))]


def _guard_digest(image: XbeImage, va: int, size: int) -> str:
    content = bytearray(image.read(va, size))
    # mask this owner's own edits back to retail, so a retail and an installed image give the same digest
    for _label, sva, before, _entry, _kind in SITE_TABLE:
        for i, b in enumerate(before):
            if va <= sva + i < va + size:
                content[sva + i - va] = b
    eva, eretail, _entry = ENTER_POINTER
    for i, b in enumerate(struct.pack("<I", eretail)):
        if va <= eva + i < va + size:
            content[eva + i - va] = b
    return hashlib.sha256(bytes(content)).hexdigest()


def guard_digests(payload: bytes) -> dict[str, str]:
    """The masked digest of every guarded span (used to pin GUARD_SHA256_PINNED from the retail executable)."""

    image = XbeImage(payload)
    return {name: _guard_digest(image, va, size) for name, va, size in GUARDS}


def _check_guards(image: XbeImage) -> None:
    for name, va, size in GUARDS:
        _require(_guard_digest(image, va, size) == GUARD_SHA256_PINNED[name], f"standings dependency changed: {name}")
    _require(image.read(WEEKS_VA, 1)[0] in WEEKS_ALLOWED, "foreign regular-season row count")


def allocations(payload: bytes) -> dict[str, dict]:
    """{"code": row, "data": row} of an installed allocation, {} when the owner is not allocated."""

    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) != "retail" else []
    if not rows:
        return {}
    found = {r["kind"]: r for r in rows}
    _require(len(rows) == len(found) == 2 and set(found) == {"code", "data"}
             and all((found[k]["size"], found[k]["align"]) == (size, align) for _o, k, size, align in REQUESTS),
             "foreign standings records allocation")
    return found


def _recognize(payload: bytes) -> str:
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    _check_guards(image)
    found = allocations(payload)
    code_va = found["code"]["va"] if found else 0
    states = set()
    for _label, va, before, after in sites(code_va) + data_edits(code_va):
        got = image.read(va, len(before))
        states.add("retail" if got == before else "applied" if found and got == after else "foreign")
    if found:
        code = image.read(code_va, CODE_SIZE)
        states.add("retail" if code == b"\xcc" * CODE_SIZE else
                   "applied" if code == code_for(code_va, found["data"]["va"]) else "foreign")
        _require(image.read(found["data"]["va"], DATA_SIZE) == bytes(DATA_SIZE), "foreign initial standings state")
    _require(states in ({"retail"}, {"applied"}), "foreign or mixed standings records bytes")
    return next(iter(states))


def status(payload: bytes) -> str:
    """"retail" (no edit), "applied" (installed whole) or "foreign" (anything else, including a half install)."""

    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, OSError):
        return "foreign"


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "standings_records": state == "applied", "views": VIEWS if state == "applied" else None}


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    base = allocations(payload)
    code_va = base["code"]["va"] if base else 0x14DA000
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave")
                   for label, va, before, _after in sites(code_va) + data_edits(code_va)]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner and its twelve edits. Idempotent; needs a retail or sealed scale-out image."""

    state = status(payload)
    _require(state != "foreign", "the source executable is not retail or Team Standings records")
    common = {"owner": OWNER, "experimental": True, "views": list(VIEWS), "code_bytes": len(runtime.CODE),
              "owner_bytes": CODE_SIZE + DATA_SIZE}
    if state == "applied":
        return payload, {**common, "status": "already_applied", "already_applied": True, "changed_bytes": 0, "edits": []}
    before = payload
    allocation_receipt = {}
    if not allocations(payload):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            _require(space.is_scaleout(payload), "standings records needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    found = allocations(payload)
    _require(bool(found), "reserve the standings records allocation first")
    code_va, data_va = found["code"]["va"], found["data"]["va"]
    payload, code_receipt = space.install_code(payload, OWNER, code_for(code_va, data_va))
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = []
    for label, va, old, new in sites(code_va) + data_edits(code_va):
        off = image.offset(va, len(old))
        _require(bytes(buf[off:off + len(old)]) == old, f"standings site {va:#x} is not retail")
        buf[off:off + len(new)] = new
        edits.append(dict(label=label, va=hex(va), before=old.hex(), after=new.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(status(result) == "applied" and space.status(result) == "applied", "standings records postcondition failed")
    return result, {**common, "status": "applied", "already_applied": False, "code_va": hex(code_va), "data_va": hex(data_va),
                    "changed_bytes": space.count_differing_bytes(before, result),
                    "file_growth": len(result) - len(before), "allocation": allocation_receipt,
                    "code_install": code_receipt, "edits": edits,
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "requests": dict(code=CODE_SIZE, data=DATA_SIZE, read_only=0),
                    "reservations": [r for r in space.reservations(result) if r["owner"] == OWNER]}


def main(argv=None) -> int:
    """python3 -m mod_editor.core.nfl2k5_standings_records {status,apply} source.xbe [output.xbe]"""

    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=BUILD_CAPTION)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    _require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "apply":
        result, receipt = apply(payload)
        with args.output.open("xb") as stream:
            stream.write(result)
    else:
        receipt = {**read_settings(payload), "owner": OWNER, "experimental": True}
    print(json.dumps(receipt, indent=2, default=str))
    return 0


__all__ = ["OWNER", "REQUESTS", "BUILD_CAPTION", "HELP_TEXT", "VIEWS", "SITE_TABLE", "GUARDS", "StandingsRecordsError",
           "code_for", "labels", "sites", "data_edits", "allocations", "apply", "status", "read_settings", "reservations",
           "guard_digests", "division_conference_records", "home_road_records", "streaks", "format_record",
           "format_streak"]


if __name__ == "__main__":
    raise SystemExit(main())
