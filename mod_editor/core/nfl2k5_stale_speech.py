"""Stale per-team and per-stadium booth lines fall back to the game's generic line or are skipped (beta 81, sb-booth).
EXPERIMENTAL.

Stale-line audit, part 2 (coordinator's rulings, 2026-11-25): "retarget the stadium lines that have a generic line;
skip the head-coach intros; skip the stale stadiums in Berman's city intros; skip Berman's team-history blurbs only
where they state something no longer true; remove the 'Redskins' lines that have their own context list; keep every
correct 'Washington' call."

How these lines are picked (static RE, retail executable; the mechanism witnessed for key 14039, see
nfl2k5_stadium_welcome): a context key of the ``lines`` speech index (SPCI, outer 3, third table) has one recording
per context, a team speech id (team record +0x154, the same number as the club's asset code) or a stadium number,
picked by scanning the key's context list. When the scan finds nothing the booth resolver 0x67560 retries context 999
(the game's own generic line, e.g. "visiting us for the game.") and the other speaker variant; when those fail the
sequencer FUN_000C32C0 drops the phrase and the broadcast goes on.

What this owner does: for each (key, context) in ``RULES`` whose condition holds on the built disc, the context's
value becomes 0xFFFF in every context list of that key (all speaker variants), so the line falls back to the key's
generic 999 line or, where the key has none, is skipped. Every list edited here belongs to its key alone, except
list 4664, which keys 38506 and 38550 share with identical rules. Conditions read the built disc:

* ``row``: the stadium row with that number shows another display name than retail (renamed by the venue options);
* ``place`` / ``nickname``: the club with that speech id no longer carries its retail city (Raiders, Rams, Chargers)
  or nickname (Washington);
* ``coach``: the club's head coach is no longer its 2004 coach (a 2004 storyline is no longer current);
* ``always``: the recording names a building that was already gone in 2004 (Veterans Stadium, CMGI Field, ...).

A disc whose roster this module cannot read, or on which no condition holds, is left alone. Data only: two bytes per
(list, context) in the one ``lines`` SPCI, stored uncompressed. Unwitnessed for these keys unless a report says
otherwise.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Callable

from .nfl2k5_stadium_welcome import SPCI_OUTER_INDEX, SPCI_STORED, find_spci

OWNER = "nfl2k5_stale_speech"
SCHEMA = "nfl2k5_stale_speech/v1"
LABEL = "EXPERIMENTAL"
SKIP = 0xFFFF
TEAMS_2004 = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
              28, 29, 30, 37)

R, A, P, N, C = "row", "always", "place", "nickname", "coach"
_STADIUM_LINE = {1: R, 3: R, 6: R, 7: R, 8: R, 11: R, 12: R, 14: R, 15: R, 18: R, 19: R, 22: R, 23: R, 24: R, 30: R}
#: key -> {context: condition}; the comment is what the retail recording says (transcribed) and its fallback
RULES: dict[int, dict[int, str]] = {
    # "visiting us at <stadium>" -> 999 "visiting us for the game."
    9453: {**_STADIUM_LINE, 17: R, 2: A, 4: A, 16: A, 21: A, 22: A, 25: A},
    # "over at <stadium> we had" / "<stadium>." (one shared list) -> 999 "over in the stadium we had" / "the stadium"
    38506: {**_STADIUM_LINE, 0: R, 20: P, 25: A},
    38550: {**_STADIUM_LINE, 0: R, 20: P, 25: A},
    # "On the east side of the bay in Oakland" / "on the Mississippi River in St. Louis" / "in San Diego right by
    # Coronado Bay" -> 999 "in the big city we had"
    38502: {20: P, 23: P, 24: P},
    # Berman's pregame city intro (no generic: skipped)
    38800: {**_STADIUM_LINE, 0: R, 17: R, 25: R, 27: R, 28: R, 20: P, 23: P, 24: P, 9: C, 21: C},
    # Berman's team-history blurb, only where it is no longer true (no generic: skipped)
    38803: {0: C, 4: C, 6: C, 8: C, 11: C, 13: C, 16: C, 17: C, 22: C, 26: C, 27: C, 28: C, 37: C,
            23: P, 24: P, 29: N},
    # the head-coach intro names the club's 2004 coach (no generic: skipped)
    13850: {team: C for team in TEAMS_2004},
    # Washington's "Redskins" lines on lists of their own (the PA, crowd and booth calls; generic or skipped)
    512: {29: N}, 1201: {29: N}, 9414: {29: N}, 9427: {29: N}, 9444: {29: N}, 9456: {29: N}, 9467: {29: N},
    9468: {29: N}, 50020: {29: N},
}
#: context list index -> its retail values (u16 little-endian, hex); the pin every edit is checked against
RETAIL_LISTS = {
    2302: ("010002000300040006000700080009000a000b000c000d000e000f001000110012001300150016001700180019001a001e00"
         "1f0020002100250026002700e703"),
    4664: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f0020002500e703"),
    4522: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e00250064007b007d0090009e00a200e703"),
    5121: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00200025003000320033003400350036003700380039003a003b003c003d003e003f004000"
         "410042004300440045004600470049004a004b004c004d004e004f00500051005200530054005500"),
    5224: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f002100220023002500280029002a002b002c002d002e00"),
    2784: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e002500"),
    231: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f002200230024002500280029002a002b002c002d005900e503e603"),
    538: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d0064007d00a200e503e603"),
    1187: ("1f0022002300280029002a002b002c002d002e00a200"),
    1199: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e0025006400e703"),
    1824: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e006400a200e603"),
    1870: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e006400a200e503"),
    2256: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e00a200e503e603"),
    2498: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e00a200e703"),
    2649: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e007b0090009e00a200e503"),
    2697: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e001f00220023002500280029002a002b002c002d002e007b0090009e00a200e603"),
    9905: ("00000100020003000400050006000700080009000a000b000c000d000e000f00100011001200130014001500160017001800"
         "19001a001b001c001d001e0063006400650066006700680069006a006b006c006d006e006f00700071007200730074007500"
         "76007700780079007a007b007c007d007e007f00800081008200c7002b018f01"),
}
#: retail display names of the stadium rows a ``row`` condition reads (data/nfl2k5_modern_venues_2026/names.json)
RETAIL_ROWS = {0: "Arizona Stadium", 1: "The Georgia Dome", 3: "Ralph Wilson Stadium", 6: "Paul Brown Stadium",
               7: "Texas Stadium", 8: "INVESCO Field at Mile High Stadium", 11: "The RCA Dome", 12: "ALLTEL Stadium",
               14: "Pro Player Stadium", 15: "H. H. H. Metrodome", 17: "The Louisiana Super Dome",
               18: "Giants Stadium", 19: "Giants Stadium", 22: "Heinz Field", 23: "Edward Jones Dome ",
               24: "QUALCOMM Stadium", 25: "San Francisco Park", 27: "Tampa Bay Stadium", 28: "Titans Coliseum",
               30: "The Cleveland Browns Stadium"}
RETAIL_PLACES = {20: "Oakland", 23: "St. Louis", 24: "San Diego"}
RETAIL_NICKNAMES = {29: "Redskins"}
#: the 2004 head coach of each club (retail roster), by speech id
RETAIL_COACHES = {0: "Green", 1: "Mora Jr.", 2: "Billick", 3: "Mularkey", 4: "Fox", 5: "Smith", 6: "Lewis",
                  7: "Coach", 8: "Shanahan", 9: "Mariucci", 10: "Sherman", 11: "Dungy", 12: "Del Rio", 13: "Vermeil",
                  14: "Wannstedt", 15: "Tice", 16: "Belichick", 17: "Haslett", 18: "Coughlin", 19: "Edwards",
                  20: "Turner", 21: "Reid", 22: "Cowher", 23: "Martz", 24: "Schottenheimer", 25: "Erickson",
                  26: "Holmgren", 27: "Gruden", 28: "Fisher", 29: "Gibbs", 30: "Davis", 37: "Capers"}


class StaleSpeechError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise StaleSpeechError(message)


def _rel(body: bytes, field: int) -> int:
    return field + struct.unpack_from("<I", body, field)[0] - 1


def context_lists(body: bytes) -> tuple[dict[int, list[int]], dict[int, set[int]], int]:
    """(key -> its context list indexes, list index -> the keys that use it, body offset of the lists table) for the
    third table of a lines SPCI body (rows: keys, list-index array, u16 mask, u16 count, u8 variants)."""
    table, lists = _rel(body, 0x38), _rel(body, 0x3C)
    by_key: dict[int, list[int]] = {}
    users: dict[int, set[int]] = {}
    for row in range(body[0x42]):
        at = table + 16 * row
        _mask, count, variants = struct.unpack_from("<HHB", body, at + 8)
        keys = struct.unpack_from(f"<{count}H", body, _rel(body, at))
        index_at = _rel(body, at + 4)
        for p, key in enumerate(keys):
            for v in range(variants):
                index = struct.unpack_from("<H", body, index_at + 2 * (variants * p + v))[0]
                by_key.setdefault(key, []).append(index)
                users.setdefault(index, set()).add(key)
    return by_key, users, lists


def _list_at(lists: int, index: int) -> int:
    return lists + 2 * index


def list_values(body: bytes, lists: int, index: int) -> tuple[int, ...]:
    at = _list_at(lists, index)
    count = struct.unpack_from("<H", body, at)[0]
    return struct.unpack_from(f"<{count}H", body, at + 2)


def retail_values(index: int) -> tuple[int, ...]:
    raw = bytes.fromhex(RETAIL_LISTS[index])
    return struct.unpack(f"<{len(raw) // 2}H", raw)


def list_state(index: int, values: tuple[int, ...]) -> str:
    """retail / applied (only rule contexts of its keys set to 0xFFFF) / foreign."""
    retail = retail_values(index)
    if values == retail:
        return "retail"
    if len(values) != len(retail):
        return "foreign"
    allowed = {c for key, rule in RULES.items() if index in _LIST_KEYS.get(key, ()) for c in rule}
    changed = [(r, v) for r, v in zip(retail, values) if r != v]
    return "applied" if all(v == SKIP and r in allowed for r, v in changed) else "foreign"


#: key -> the retail context lists it uses (one per speaker variant), checked against the disc in plan_lists
_LIST_KEYS = {9453: (2302,), 38506: (4664,), 38550: (4664,), 38502: (4522,), 38800: (5121,), 38803: (5224,),
              13850: (2784,), 512: (231,), 1201: (538,), 9414: (1187, 1199), 9427: (1824, 1870), 9444: (2256,),
              9456: (2498,), 9467: (2649,), 9468: (2697,), 50020: (9905,)}


def plan_lists(body: bytes) -> dict[int, tuple[int, ...]]:
    """list index -> current values, after checking the table shape: every rule key uses exactly its pinned lists,
    no other key uses them, keys sharing a list share its rules, and every list is retail or edited by this owner."""
    by_key, users, lists = context_lists(body)
    out = {}
    for key, rule in RULES.items():
        require(tuple(by_key.get(key, ())) == _LIST_KEYS[key], f"key {key} does not use its pinned context lists")
        for index in by_key[key]:
            others = users[index] - set(RULES)
            require(not others, f"context list {index} is shared with keys {sorted(others)}")
            for other in users[index]:
                require(RULES[other] == rule, f"keys {key} and {other} share list {index} with different rules")
            values = list_values(body, lists, index)
            require(list_state(index, values) != "foreign", f"context list {index} is not the retail one; refusing")
            out[index] = values
    return out


def decide(facts: dict[str, Any]) -> dict[int, dict[int, str]]:
    """key -> {context: reason} for every rule whose condition holds on this disc."""
    rows, teams = facts["rows"], facts["teams"]
    out: dict[int, dict[int, str]] = {}
    for key, rule in RULES.items():
        for ctx, cond in rule.items():
            team = teams.get(ctx, {})
            if cond == R:
                why = (f"row s{ctx:02d} shows {rows[ctx]!r}" if ctx in rows and ctx in RETAIL_ROWS
                       and rows[ctx] != RETAIL_ROWS[ctx] else None)
            elif cond == A:
                why = "named a building already gone in 2004"
            elif cond == P:
                why = (f"the club's city is {team.get('city')!r}" if team.get("city") not in (None, RETAIL_PLACES[ctx])
                       else None)
            elif cond == N:
                why = (f"the club's nickname is {team.get('nickname')!r}"
                       if team.get("nickname") not in (None, RETAIL_NICKNAMES[ctx]) else None)
            else:
                why = (f"the club's head coach is {team.get('coach')!r}"
                       if team.get("coach") not in (None, RETAIL_COACHES[ctx]) else None)
            if why:
                out.setdefault(key, {})[ctx] = why
    return out


def disc_facts(path: Path | str) -> dict[str, Any]:
    """Stadium row names, and each club's city, nickname and head coach by speech id, read from the built disc."""
    from . import nfl2k5_coach_staff as staff
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_roster_records as rr
    with rr._outer_image()(path) as archive:
        body = archive.read_entry(rr.ROST_OUTER_INDEX)[rr.RESOURCE_HEADER_SIZE:]
    rows: dict[int, str] = {}
    for _offset, fields in mm._stadium_records(body):
        code = fields["asset_code"][1]
        if len(code) == 3 and code[0] == "s" and code[1:].isdigit():
            rows.setdefault(int(code[1:]), fields["display_name"][1])
    document = rr.RosterDocument(body, base=0)
    teams: dict[int, dict[str, Any]] = {}
    for coach in staff.read_roster(body):
        team = document.teams[coach.club.index]
        teams[coach.club.asset] = {"city": team.city, "nickname": team.nickname, "coach": coach.last}
    return {"rows": rows, "teams": teams}


def patch_body(body: bytes, decisions: dict[int, dict[int, str]]) -> tuple[bytes, dict[str, Any]]:
    current = plan_lists(body)
    by_key, _users, lists = context_lists(body)
    out = bytearray(body)
    edits = []
    for key, contexts in sorted(decisions.items()):
        for index in by_key[key]:
            retail = retail_values(index)
            for ctx in sorted(contexts):
                if ctx not in retail:
                    continue                                    # this variant's list has no such context
                at = _list_at(lists, index) + 2 + 2 * retail.index(ctx)
                struct.pack_into("<H", out, at, SKIP)
                edits.append({"key": key, "list": index, "context": ctx, "body_offset": f"0x{at:X}"})
    result = bytes(out)
    changed = sum(1 for a, b in zip(body, result) if a != b)
    return result, {"edits": edits, "changed_bytes": changed}


def apply_to_image(path: Path | str, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Apply the rules that hold on this built COPY (in place, read back). Idempotent; a context already skipped
    stays skipped; a disc whose roster cannot be read is left alone."""
    from . import nfl2k5_roster_records as rr
    say = progress or (lambda _m: None)
    head = {"owner": OWNER, "schema": SCHEMA, "label": LABEL, "runtime_witnessed": False}
    try:
        facts = disc_facts(path)
    except (OSError, ValueError, KeyError, IndexError, AttributeError, struct.error) as exc:
        return {**head, "state": "skipped", "reason": f"no readable roster: {exc}", "changed_bytes": 0}
    decisions = decide(facts)
    if not decisions:
        return {**head, "state": "not_needed", "reason": "no rule holds on this disc", "changed_bytes": 0}
    with rr._outer_image()(path, writable=True) as archive:
        entry = archive.entries[SPCI_OUTER_INDEX]
        raw = archive.read(entry.virtual_offset, entry.size)
        at = find_spci(raw)
        body = raw[at + 0x20:at + 0x20 + SPCI_STORED]
        result, receipt = patch_body(body, decisions)
        if receipt["changed_bytes"]:
            say(f"Stale booth lines: {receipt['changed_bytes'] // 2} team and stadium lines fall back or are skipped")
            start = entry.virtual_offset + at + 0x20
            for i in range(0, SPCI_STORED, 2):
                if body[i:i + 2] != result[i:i + 2]:
                    require(archive.write(start + i, result[i:i + 2]) == 2, "short write in the speech index")
            back = archive.read(start, SPCI_STORED)
            require(back == result, "the speech index did not read back")
    return {**head, "state": "applied", "decisions": {str(k): v for k, v in decisions.items()}, **receipt}
