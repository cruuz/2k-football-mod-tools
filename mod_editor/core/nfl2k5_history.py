"""Franchise history capture (b780 J3, job j23-footer). EXPERIMENTAL.

Noah's players asked for it in #2k5-ideas (SWeaR 10/03, 10/10, 11/01; LePromisedPrince 9/06; adon 10/06; CER 10/07): a
team history, records, the Hall of Fame, past box scores. The game throws a finished game's box score away and keeps no
season results or records, so this owner copies them, at the two moments the game still has them, into the blocks of
the franchise extension footer (``nfl2k5_franchise_extension``; the footer host ``nfl2k5_franchise_footer`` saves and
loads them with the franchise and gives this owner the body).

What the game does (retail USA ``default.xbe``, static reading)
---------------------------------------------------------------
* A user-played game ends in ``FUN_001356C0`` (from the result flow 0xC5D99); a simulated one in ``FUN_001356D0`` (the
  week sim 0x10B9E0, the game cast 0xEC65A). Both call the commit ``FUN_00135310`` (each player's numbers into his
  season line, the quarter scores into the grid) and then jump to the game summary ``0x73770``, which still reads the
  finished game's live club and player numbers (bank 0 of 0xCB2D0 / 0xCB240). r4-records' offline probe read every
  club and player line of 16 simulated games at the commit, identical before and after it.
* Stage 9 of ``FUN_002480B0`` (Advance to offseason): the Super Bowl notice and the retirement pass (0x2485FA), then
  ``call 0x13ED70`` (the contract ring) at 0x248601, then the rollover that clears the season. At 0x248601 the whole
  season grid, the awards, every player's season line and the retirees (record +8 bit 3) are still there.

What this owner adds (three sites; code only, no memory of its own)
-------------------------------------------------------------------
* 0x1356C8 and 0x1356FF (the two ``jmp 0x73770``): for a regular-season or playoff game (not the preseason or the Pro
  Bowl), single-game records of both clubs (12 categories, club and league) and, when the user's club played, its box
  score (both clubs' 16 team stats, four opponent leaders, up to 23 of the user's player lines). Then the summary runs.
* 0x248601 (``call 0x13ED70``): the season record (every club's regular-season W-L-T, points, division place, playoff
  result, head coach; the champion and score; the awards), the franchise totals, single-season records, all-time club
  and league leaders (a linked leader adds the season to his own total; anyone else enters from his unfolded seasons
  with the club), the Hall of Fame candidates (retirees) and this year's class. Then the displaced call runs.
* The Hall of Fame is job j6-hof's rule (``nfl2k5_hof_rules``), compiled in unchanged from its ``c_reference()``: at the
  close of season Y the class of Y + 1 (up to 5 with 100 points, at least 2 from 80), then the candidates past their
  window leave, then this season's retirees with 80 points join (a full table drops its weakest). Two counters the
  game never keeps are added to a retiree's career from block 8 (``playoffs``): Super Bowls lost (every player of the
  losing club, counted at the close) and playoff wins (the player with the most pass attempts on the winning club of
  each postseason game, counted at the game's commit).

It only reads the game's state through getters (no random number draw, no allocation) and writes only inside the body.
Every loop is bounded and every pointer checked; when the body is absent (xemu at 64 MB on a K128 build) nothing runs.

Allocation: code 12,288 B, late owner after ``nfl2k5_franchise_footer`` (it calls that owner's ``xt_body``).
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_franchise_extension as ext
from . import nfl2k5_history_code as runtime
from . import nfl2k5_hof_rules as hof_rules
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_history"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 12288
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
CONFIG_AT = runtime.LABELS["hst_config"]
CONFIG_MAGIC, CONFIG_VERSION = 0x43545348, 1           # "HSTC"
CONFIG_FIELDS = ("magic", "version", "body_fn", "chain_close", "hall_bar", "hall_wait", "hall_window", "hall_class",
                 "flags")
FLAG_RECORDS, FLAG_BOXSCORES, FLAG_LEADERS, FLAG_HALL = 1, 2, 4, 8
ALL_PARTS = FLAG_RECORDS | FLAG_BOXSCORES | FLAG_LEADERS | FLAG_HALL

# Hall of Fame rule: job j6-hof's (nfl2k5_hof_rules); the native code is its c_reference(), compiled in. These values
# fill the config table for status only (the code uses the compiled constants).
HALL_RULE = {"bar": hof_rules.BAR, "floor": hof_rules.FLOOR, "wait": hof_rules.WAIT_SEASONS,
             "window": hof_rules.WINDOW_SEASONS, "class_size": hof_rules.MAX_CLASS, "min_class": hof_rules.MIN_CLASS,
             "class_year": "the season closed + 1", "score": hof_rules.RULE_HELP}

# (label, VA, retail bytes, entry label, opcode, length)
SITE_TABLE = (
    ("played", 0x001356C8, bytes.fromhex("e9a3e0f3ff"), "history_played", 0xE9, 5),
    ("simulated", 0x001356FF, bytes.fromhex("e96ce0f3ff"), "history_simulated", 0xE9, 5),
    ("season_close", 0x00248601, bytes.fromhex("e86a67efff"), "history_close", 0xE8, 5),
)
RETAIL_CLOSE = 0x0013ED70
GUARDS = (
    ("played commit tail", 0x001356C0, 0x0D, "4e2f1e9a11062272a854da62b8f2f8f795ff40fb11751ac4adba81bf985a220d"),
    ("simulated commit tail", 0x001356F3, 0x11, "cd5a66618432bcc39e6d2f35447ce82edcc5654ed409392ed220a825e89706b8"),
    ("season close", 0x002485FF, 0x0D, "942cac420a25dc75b467ec526a1c57f219f13ac3555187ca25270a8b02251232"),
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, AttributeError)


class HistoryError(ValueError):
    """Unsupported executable, foreign or mixed installation, or the footer host is missing."""


def _require(condition, message):
    if not condition:
        raise HistoryError(message)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def labels(code_va: int) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def code_for(code_va: int, config: Mapping[str, int]) -> bytes:
    result = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        _require(symbol == "code", "unexpected history relocation")
        target = code_va + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    values = {"magic": CONFIG_MAGIC, "version": CONFIG_VERSION, "hall_bar": HALL_RULE["bar"],
              "hall_wait": HALL_RULE["wait"], "hall_window": HALL_RULE["window"],
              "hall_class": HALL_RULE["class_size"], "flags": ALL_PARTS, **dict(config)}
    for index, name in enumerate(CONFIG_FIELDS):
        struct.pack_into("<I", result, CONFIG_AT + 4 * index, int(values.get(name, 0)) & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "the history runtime exceeds its fixed budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def read_config(blob: bytes) -> dict[str, int] | None:
    if len(blob) < CONFIG_AT + 64:
        return None
    values = {name: struct.unpack_from("<I", blob, CONFIG_AT + 4 * i)[0] for i, name in enumerate(CONFIG_FIELDS)}
    if values["magic"] != CONFIG_MAGIC or values["version"] != CONFIG_VERSION:
        return None
    return values


def sites(code_va: int, chain_close: int = RETAIL_CLOSE) -> list[tuple[str, int, bytes, bytes]]:
    at = labels(code_va)
    rows = []
    for label, va, before, entry, opcode, length in SITE_TABLE:
        if label == "season_close" and chain_close != RETAIL_CLOSE:
            before = b"\xe8" + _rel32(va + 5, chain_close)
        rows.append((label, va, before, bytes([opcode]) + _rel32(va + 5, at[entry]) + b"\x90" * (length - 5)))
    return rows


def allocations(payload: bytes) -> dict[str, dict]:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and (rows[0]["size"], rows[0]["align"]) == (CODE_SIZE, 16),
             "foreign history allocation")
    return {"code": rows[0]}


def _guard_digest(image: XbeImage, va: int, size: int) -> str:
    content = bytearray(image.read(va, size))
    for _label, address, before, *_rest in SITE_TABLE:
        if va <= address and address + len(before) <= va + size:
            content[address - va:address - va + len(before)] = before
    return hashlib.sha256(content).hexdigest()


def guard_digests(payload: bytes) -> dict[str, str]:
    image = XbeImage(payload)
    return {name: _guard_digest(image, va, size) for name, va, size, _d in GUARDS}


def _check_guards(image: XbeImage) -> None:
    for name, va, size, digest in GUARDS:
        _require(_guard_digest(image, va, size) == digest, f"foreign history dependency: {name} ({va:#x})")


def _recognize(payload: bytes):
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocations(payload)
    if not found:
        for label, va, before, *_rest in SITE_TABLE:
            raw = image.read(va, len(before))
            _require(raw == before or (label == "season_close" and raw[:1] == b"\xe8"),
                     f"history site {label} changed without an allocation")
        _check_guards(image)
        return "retail", None, None
    code_va = found["code"]["va"]
    blob = image.read(code_va, CODE_SIZE)
    if blob == b"\xcc" * CODE_SIZE:
        _check_guards(image)
        return "retail", found, None
    config = read_config(blob)
    _require(config is not None, "foreign history code (no CONFIG)")
    _require(blob == code_for(code_va, config), "foreign history code")
    for label, va, _before, after in sites(code_va, config["chain_close"]):
        _require(image.read(va, len(after)) == after, f"history site {label} is not this owner's")
    from . import nfl2k5_franchise_footer as footer
    _require(footer.status(payload) == "applied" and config["body_fn"] == footer.body_function_va(payload),
             "the franchise footer host this owner reads is missing or foreign")
    _require(config["chain_close"] == RETAIL_CLOSE, "the season-close site chains a foreign target")
    _check_guards(image)
    return "applied", found, config


def owned_state(payload: bytes):
    return _recognize(payload)


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)[0]
    except _ERRORS:
        return "foreign"


def installed_sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, displaced bytes, installed bytes) of an exact install; empty otherwise (companion guards)."""

    try:
        state, found, config = _recognize(payload)
    except _ERRORS:
        return []
    return sites(found["code"]["va"], config["chain_close"]) if state == "applied" else []


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    found = allocations(payload)
    edits = sites(found["code"]["va"] if found else 0x14DA000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes, *, parts: int = ALL_PARTS, hall_rule: Mapping[str, int] | None = None
          ) -> tuple[bytes, Mapping[str, object]]:
    """Install the capture. The franchise footer host must already be installed (it owns the body)."""

    _require(type(parts) is int and 0 <= parts <= ALL_PARTS, "parts is a mask of the four history parts")
    state, found, _config = _recognize(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": len(runtime.CODE), "owner_bytes": CODE_SIZE}
    if state == "applied":
        return payload, {**common, "status": "already_applied", "changed_bytes": 0}
    from . import nfl2k5_franchise_footer as footer
    _require(footer.status(payload) == "applied", "install the franchise footer host first")
    image = XbeImage(payload)
    for label, va, before, *_rest in SITE_TABLE:
        _require(image.read(va, len(before)) == before, f"the history site {label} is already hooked by another owner")
    _check_guards(image)
    before = payload
    if not found:
        _require(space.is_scaleout(payload), "the history capture needs the scale-out allocator")
        payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
        found = allocations(payload)
    else:
        allocation_receipt = {}
    code_va = found["code"]["va"]
    rule = {**HALL_RULE, **dict(hall_rule or {})}
    config = {"body_fn": footer.body_function_va(payload), "chain_close": RETAIL_CLOSE, "flags": parts,
              "hall_bar": rule["bar"], "hall_wait": rule["wait"], "hall_window": rule["window"],
              "hall_class": rule["class_size"]}
    payload, code_receipt = space.install_code(payload, OWNER, code_for(code_va, config))
    buf = bytearray(payload)
    image = XbeImage(payload)
    for _label, va, _b, after in sites(code_va):
        off = image.offset(va, len(after))
        buf[off:off + len(after)] = after
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(status(result) == "applied", "history postcondition failed")
    return result, {**common, "status": "applied", "code_va": hex(code_va), "parts": parts, "hall_rule": rule,
                    "allocation": allocation_receipt, "code_install": code_receipt,
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": space.count_differing_bytes(before, result),
                    "sites": [{"label": label, "va": hex(va), "size": len(b)} for label, va, b, _a in sites(code_va)]}


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HALL_RULE", "HistoryError", "apply", "allocations", "code_for",
           "guard_digests", "installed_sites", "labels", "owned_state", "read_config", "reservations", "sites", "status"]
