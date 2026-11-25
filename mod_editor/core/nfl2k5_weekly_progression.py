"""Franchise in-season weekly progression, USA retail (b778 pg1). EXPERIMENTAL.

Noah 10/22: player development should follow the NFL "in terms of their longevity and how they regress or progress
every offseason, or even every week"; job pg2 shows the week-by-week changes on a Player Progression screen.

Where a week's games end (static disassembly of the USA executable, b778 pg1; team_column documents the same path):
every user-played and every simulated game ends in ``0x135310`` (from ``0x1356C0``/``0x1356D0``; the simulator calls
``0x1356D0`` at 0x10B9E0). For the preseason, regular season and playoffs (stage 7..9) it first ends the game's weekly
preparation for both clubs (``0x2AC520`` -> ``0x2AB840`` at 0x13538F/0x135398), so ratings are back to their base
values, and only then merges each club's game stats (``0x134DD0`` at 0x1353E3/0x1353FC), which calls the per-player
merge ``0x1334B0`` at 0x134E05 for every player in the club's array (injured-reserve players are parked outside).

This owner replaces that one call with ``wk_merge``: it reads the player's current-season totals of up to four stat
fields and games played (``0x14EE40``), runs the retail merge, reads them again, and so knows exactly this game's line.
Only in a franchise (league type 2) regular-season game (stage 8) and only for a healthy player it then moves a few
ratings by one point:

* a young player (years pro <= 3, QB <= 4) with a good game: +1 on his position's key ratings, every other good game;
* an older player (years pro >= the position's decline year) who sat out or had a poor game: -1 speed and -1 agility
  or stamina (a QB: speed only), one such week in four;
* nothing else (poor or idle young players, average games, kickers and punters, injured players, other modes).

Quarterbacks are judged on the game's adjusted yards per attempt ((yards + 20 TD - 45 INT) / attempts, 15+ attempts).
The cadence is deterministic (the player's record address and the week), as the rest of franchise development is.
Ratings stay within 0..100. Weekly preparation never sees a change: it was cleaned up before the merge, and the
next game's preparation starts from the new base. Nothing new is saved: the changes live in the player records the
franchise save already carries (pg2 records the weekly snapshots). The season's weekly total is a fraction of the
offseason step (b778 pg1 report: young starters about a fifth, veterans under a tenth).
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_progression import _Asm, POSITIONS, CLASSES, CLASS_OF

OWNER = "nfl2k5_weekly_progression"
CODE_SIZE = 608
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Franchise: weekly player progression"
HELP_TEXT = ("EXPERIMENTAL. After each franchise regular-season game, a young player with a good game gains a point on "
             "his key ratings every other good game, and an older player who sat out or played poorly loses a point of "
             "speed every few weeks. Injured players, playoffs and other modes are unchanged. Small next to the "
             "offseason changes.")
HOOK = ("weekly_merge", 0x00134E05, bytes.fromhex("e8a6e6ffff"))            # call 0x1334B0 (per-player stat merge)
FN_MERGE, FN_STAT_NOW = 0x001334B0, 0x0014EE40
FN_LEAGUE, FN_STAGE, FN_WEEK = 0x000C4B80, 0x000C4BB0, 0x000C4E70
GUARDS = (  # retail code this owner calls or hooks (the hook's own bytes masked back to retail)
    (0x00134DD0, 0x35, "d76cb3b9b599b7053c7f1d26471790dbf282a752ea81e8f9140d3cce8013c900"),   # merge loop up to the call
    (0x001334B0, 0x10, "23260f861feca35fc9af9b81ffede65d28cd43a08a8d4d876b3a2bd46158b7a7"),   # per-player merge head
    (0x0014EE40, 0x1F, "fc126037b6c785bd0575f57a96d322c442e7e6786cab43d75368c4d3a4a4ccd3"),   # current-season stat
    (0x000C4B80, 0x06, "ea571d62a509b72a0a8afeb1ce87e10afb9b23fe864a4f34521e3a467052a60a"),   # league type
    (0x000C4BB0, 0x06, "712452f8e0b8c23621623a511c8e9688c1a61e199a1a75329dd87f51b658661d"),   # stage
    (0x000C4E70, 0x06, "6b33a3cdfc251883b056280f93e667454d3a140817693bca265ae92b96924b09"),   # week
)
LEAGUE_FRANCHISE, STAGE_REGULAR = 2, 8
GOOD_MASK, OLD_MASK = 0, 3            # +1 on every good game of a young player, -1 one week in four (h & 3 == 0)
QB_MIN_ATTEMPTS = 15
SPEED, AGILITY, STAMINA = 0x36, 0x37, 0x39
KIND_QB, KIND_SUM, KIND_PLAYED, KIND_NONE = 0, 1, 2, 3
# class -> (fields, kind, good, poor, young max years pro, old from years pro, key rating offsets)
# Stream field ids: 0 games, 2 rushing yards, 6 attempts, 8 passing yards, 9 TD, 10 INT thrown, 13 receiving yards,
# 18 tackles, 19 sacks (half-sack units), 20 interceptions. QB thresholds are AY/A x10.
RULES = {
    "QB": ((6, 8, 9, 10), KIND_QB, 85, 45, 4, 16, (0x42, 0x43, 0x4E)),
    "KP": ((), KIND_NONE, 0, 0, 0, 31, ()),
    "WR": ((13,), KIND_SUM, 80, 15, 3, 10, (0x44, 0x3F, 0x47)),
    "CB": ((18, 20), KIND_SUM, 6, 1, 3, 9, (0x3E, 0x43, 0x40)),
    "S": ((18, 20), KIND_SUM, 8, 1, 3, 10, (0x3E, 0x49, 0x40)),
    "RB": ((2, 13), KIND_SUM, 100, 30, 3, 7, (0x41, 0x47, 0x37)),
    "FB": ((2, 13), KIND_SUM, 40, 0, 3, 8, (0x45, 0x41)),
    "TE": ((13,), KIND_SUM, 60, 10, 3, 11, (0x44, 0x3F, 0x45)),
    "LB": ((18, 19), KIND_SUM, 8, 2, 3, 10, (0x40, 0x49, 0x3E)),
    "OL": ((), KIND_PLAYED, 1, -1, 3, 12, (0x45, 0x46)),
    "DL": ((19, 18), KIND_SUM, 6, 1, 3, 11, (0x48, 0x40)),
}
ROW = 14
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class WeeklyProgressionError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise WeeklyProgressionError(message)


def rows() -> bytes:
    out = bytearray()
    for cls in CLASSES:
        fields, kind, good, poor, young, old, keys = RULES[cls]
        f = list(fields) + [0xFF] * (4 - len(fields))
        k = list(keys) + [0] * (3 - len(keys))
        out += struct.pack("<4BBhhBB3B", *f, kind, good, poor, young, old, *k)
    require(len(out) == ROW * len(CLASSES), "rule rows")
    return bytes(out)


def code_for(code_va):
    """The cave (CODE_SIZE bytes): wk_merge, called from 0x134E05 with eax = roster player, [esp+4] = match copy,
    [esp+8] = club; it returns like 0x1334B0 (ret 8) with ebx, esi, edi and ebp preserved."""
    a = _Asm(code_va)
    # frame after the prologue: [esp+0..15] four stat fields, [esp+16] games, saved ebp edi esi ebx, return, copy, club
    a.label("wk")
    a("53" "56" "57" "55" "8bf0" "6a00" "6a00" "6a00" "6a00" "6a00")
    a.call(FN_LEAGUE); a("83f8%02x" % LEAGUE_FRANCHISE); a.j8("75", "plain")
    a.call(FN_STAGE); a("83f8%02x" % STAGE_REGULAR); a.j8("75", "plain")
    a("0fb64635" "83f810"); a.j8("77", "plain")           # position <= 16
    a("0fb6b8"); a.abs32("cls")                           # movzx edi, byte [eax + cls]
    a("6bff%02x" % ROW + "81c7"); a.abs32("rows")         # edi = rows + ROW * class
    a("807f04%02x" % KIND_NONE); a.j8("74", "plain")      # kickers and punters: plain merge
    a.call("read")                                        # frame = this season's totals before the game
    a("ff74242c" "ff74242c" "8bc6"); a.call(FN_MERGE)     # push club; push copy; eax = player; merge (ret 8)
    a.call("read")                                        # frame = this game's line (after - before)
    a.j32("e9", "judge")
    a.label("plain")
    a("ff74242c" "ff74242c" "8bc6"); a.call(FN_MERGE)
    a.label("out")
    a("83c414" "5d" "5f" "5e" "5b" "c20800")
    # ---- read: frame = now - frame for the row's four fields and games ([esp+4..] = the caller's frame)
    a.label("read")
    a("33db")
    a.label("rl")
    a("0fb6141f" "80faff"); a.j8("74", "rz")
    a("8bce"); a.call(FN_STAT_NOW); a.j8("eb", "rs")
    a.label("rz")
    a("33c0")
    a.label("rs")
    a("2b449c04" "89449c04" "43" "83fb04"); a.j8("72", "rl")
    a("33d2" "8bce"); a.call(FN_STAT_NOW); a("2b442414" "89442414" "c3")
    # ---- judge this game: ecx = +1 good, -1 poor or sat out, 0 otherwise
    a.label("judge")
    a("f6462380"); a.j8("75", "out")                     # injured (+0x20 bit 31): untouched
    a("33c9" "837c241000"); a.j8("7f", "played")          # games this week > 0 ?
    a("49"); a.j8("eb", "judged")                         # sat out: counts as a poor week
    a.label("played")
    a("0fb64704" "83f8%02x" % KIND_PLAYED); a.j8("75", "notol")
    a("41"); a.j8("eb", "judged")                         # linemen: a game played is a good week
    a.label("notol")
    a("85c0"); a.j8("75", "sum")
    a("8b1c24" "83fb%02x" % QB_MIN_ATTEMPTS); a.j8("7c", "judged")   # QB: 15+ attempts
    a("8b442408" "6bc014" "03442404" "8b54240c" "6bd22d" "2bc2" "6bc00a" "99" "f7fb")
    a.j8("eb", "cmp")
    a.label("sum")
    a("8b0424" "03442404")                                # the first two fields
    a.label("cmp")
    a("0fbf5705" "3bc2"); a.j8("7c", "ng"); a("41"); a.j8("eb", "judged")
    a.label("ng")
    a("0fbf5707" "3bc2"); a.j8("7f", "judged"); a("49")
    a.label("judged")
    a("8b4624" "c1e808" "83e01f" "50")                     # push years pro
    a.call(FN_WEEK); a("8bd6" "c1ea02" "03c2" "8bd8" "58")  # ebx = (player >> 2) + week; eax = years pro
    a("83f901"); a.j8("75", "old")
    a("3a4709"); a.j8("77", "fin")                       # young?
    a("f6c3%02x" % GOOD_MASK); a.j8("75", "fin")
    for k in range(3):
        a("0fb6570%x" % (0xB + k) + "85d2"); a.j8("74", "fin")    # movzx edx, byte [edi+11+k]; none left: done
        a("803c1664"); a.j8("73", f"k{k}")              # cmp byte [esi+edx], 100; jae skip
        a("fe0416")                                       # inc byte [esi+edx]
        a.label(f"k{k}")
    a.j8("eb", "fin")
    a.label("old")
    a("83f9ff"); a.j8("75", "fin")
    a("3a470a"); a.j8("72", "fin")                       # from the position's decline year
    a("f6c3%02x" % OLD_MASK); a.j8("75", "fin")
    a("807e%02x00" % SPEED); a.j8("74", "o1"); a("fe4e%02x" % SPEED)
    a.label("o1")
    a("807e3500"); a.j8("74", "fin")                     # a quarterback: speed only
    a("b2%02x" % AGILITY + "f6c304"); a.j8("74", "o2"); a("b2%02x" % STAMINA)
    a.label("o2")
    a("0fb6d2" "803c1600"); a.j8("74", "fin"); a("fe0c16")
    a.label("fin")
    a("83c414" "5d" "5f" "5e" "5b" "c20800")
    a.label("cls")
    a.raw(bytes(CLASSES.index(CLASS_OF[name]) for name in POSITIONS))
    a.label("rows")
    a.raw(rows())
    body = a.assemble()
    require(len(body) <= CODE_SIZE, f"weekly progression is {len(body)} bytes, CODE_SIZE {CODE_SIZE}")
    return body.ljust(CODE_SIZE, b"\xcc")


def sites(code_va=0):
    name, va, before = HOOK
    return [(name, va, before, b"\xe8" + struct.pack("<i", code_va - (va + 5)))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    found = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(found) == 1 and (found[0]["kind"], found[0]["size"], found[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign weekly progression allocation")
    return found[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"]) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed weekly progression site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign weekly progression prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise WeeklyProgressionError(f"foreign/mixed weekly progression input: {exc}") from exc
    common = dict(owner=OWNER, league="franchise", stage="regular season", roster_fields_only=True, save_growth=0)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Weekly progression needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"weekly progression site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "weekly progression postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "GUARDS", "RULES", "BUILD_CAPTION", "HELP_TEXT", "code_for",
           "sites", "allocation", "status", "apply", "rows"]
