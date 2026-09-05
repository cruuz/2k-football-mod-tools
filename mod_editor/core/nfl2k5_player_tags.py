"""Star tags: one bit of the roster record, written into the ROST resource of a disc-image COPY.

``nfl2k5_player_star`` draws a separate white outline under each active player whose
**0x54 roster record has byte +0x53 bit 0 set**. This module writes that bit.

Where: pack ``vc_53450030/0``, outer entry 5 (``ROST``, 0x20-byte wrapper + 0x90F60 body), the same
resource ``nfl2k5_team_history`` edits.  The roster object sits at body +0x40; its two player tables
are ``obj+0x00``/``obj+0x04`` (2,479 primary records, stride 0x54) and ``obj+0x08``/``obj+0x0C``
(68 secondary records), both reached through the file's relative pointers
(``target = field + i32 - 1``, the form ``FUN_000c0500`` relocates in place at load).

Why +0x53: it is the second of the two bytes Bad_AL's NFL2K5Tool calls "padded by 2 zero bytes" at
the end of the record; it is **zero in every one of the 2,547 retail records**; and the game's own
field-by-field player clone (0xC16CD..0xC1DDB) names every field of the record from +0x00 to +0x51
and never names +0x52 or +0x53.  Every other candidate is live: +0x27 bit 0 is contract length (set
in 981 primary records), +0x26 bit 0 and +0x08 bit 0 belong to the contract block and the Player
Type flags, +0x23 is bits 24..31 of the live dword at +0x20 (an 8-bit field at bits 22..29 plus two
flag bits, read by FUN_000be290 and written by FUN_000be2a0), and +0x24 bit 7 is its own copied
one-bit field and is set in retail data.  See ``nfl2k5_player_star`` for the full derivation.

No other studio pass writes +0x53: the team history rebuilds the entry pool, the players' +0x2C
pointers and the used count; the position-pool reclassifier writes +0x35; modern prospect names
rewrite the generated-name pool.  Running this pass last therefore leaves every other pass's digest
gate intact, and its own gate is simply "which records carry the bit".

Because the tag lives in the roster body, it rides into every franchise or roster save made from the
patched disc for free (a save carries the whole ROST body), but a franchise that already exists
carries its own older copy and will not have it.

Tags do not consume the retail nine-entry controller list. The renderer walks all
22 physical on-field entities, so there is no roster-wide tagging quota.
"""

from __future__ import annotations

import datetime as dt
import importlib
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .nfl2k5_player_star import STAR_LIST_LIMIT, TAG_BIT, TAG_RECORD_OFFSET
from .nfl2k5_team_history import decode_birth, normalise_name, parse_birth_date

ROOT = Path(__file__).resolve().parents[2]

ROST_OUTER_INDEX = 5
RESOURCE_HEADER_SIZE = 0x20
BODY_SIZE = 0x90F60
RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE
OBJ_OFF = 0x40
PLAYER_SIZE = 0x54
POOLS = ("primary", "secondary")
POOL_FIELDS = {"primary": (OBJ_OFF + 0x00, OBJ_OFF + 0x04), "secondary": (OBJ_OFF + 0x08, OBJ_OFF + 0x0C)}
RETAIL_PRIMARY_COUNT = 2479
RETAIL_SECONDARY_COUNT = 68


class PlayerTagError(ValueError):
    """The star-tag writer cannot proceed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlayerTagError(message)


def _u32(body: bytes, off: int) -> int:
    return struct.unpack_from("<I", body, off)[0]


def _rel(body: bytes, off: int) -> int | None:
    value = struct.unpack_from("<i", body, off)[0]
    return None if value == 0 else off + value - 1


def _utf16(body: bytes, off: int | None) -> str:
    if off is None:
        return ""
    end = body.find(b"\0\0", off)
    while end != -1 and (end - off) % 2:
        end = body.find(b"\0\0", end + 1)
    raw = body[off: end if end != -1 else off + 64]
    return raw.decode("utf-16-le", "replace")


@dataclass(frozen=True)
class TaggedPlayer:
    pool: str
    index: int
    offset: int                  # body offset of the 0x54 record
    first: str
    last: str
    birth: dt.date | None
    position: int
    tagged: bool

    @property
    def key(self) -> str:
        """``last,first,birth_date`` -- the identity a build plan can name."""

        return f"{self.last},{self.first},{self.birth.isoformat() if self.birth else ''}"

    @property
    def display(self) -> str:
        return f"{self.first} {self.last}".strip() or f"#{self.index}"


@dataclass
class TagRoster:
    body: bytes
    players: list[TaggedPlayer]

    def by_pool(self, pool: str) -> list[TaggedPlayer]:
        return [p for p in self.players if p.pool == pool]

    @property
    def tagged(self) -> list[TaggedPlayer]:
        return [p for p in self.players if p.tagged]


def parse_body(body: bytes) -> TagRoster:
    """Decode both player tables and read each record's star bit."""

    _require(len(body) == BODY_SIZE, f"ROST body is {len(body)} bytes, not 0x{BODY_SIZE:x}")
    _require(body[0x0C:0x10] == b"ROST" and _u32(body, 0x10) == 17, "ROST preamble")
    players: list[TaggedPlayer] = []
    for pool in POOLS:
        count_off, ptr_off = POOL_FIELDS[pool]
        count = _u32(body, count_off)
        table = _rel(body, ptr_off)
        _require(table is not None, f"{pool} player table pointer is null")
        _require(0 <= count <= 4000, f"implausible {pool} player count {count}")
        _require(table + count * PLAYER_SIZE <= BODY_SIZE, f"{pool} player table outside the body")
        for index in range(count):
            off = table + index * PLAYER_SIZE
            players.append(TaggedPlayer(
                pool=pool, index=index, offset=off,
                first=_utf16(body, _rel(body, off + 0x10)), last=_utf16(body, _rel(body, off + 0x14)),
                birth=decode_birth(_u32(body, off + 0x18)), position=body[off + 0x35],
                tagged=bool(body[off + TAG_RECORD_OFFSET] & TAG_BIT)))
    return TagRoster(body=body, players=players)


def body_status(body: bytes) -> str:
    """retail (no record tagged) | applied (some are) | foreign (a pad byte carries other bits)."""

    try:
        roster = parse_body(body)
    except (PlayerTagError, struct.error):
        return "foreign"
    for player in roster.players:
        if body[player.offset + TAG_RECORD_OFFSET] & ~TAG_BIT:
            return "foreign"
    return "applied" if roster.tagged else "retail"


def summary(body: bytes) -> dict[str, Any]:
    roster = parse_body(body)
    return {"players": len(roster.players),
            "primary": len(roster.by_pool("primary")), "secondary": len(roster.by_pool("secondary")),
            "tagged": len(roster.tagged),
            "tagged_players": [{"pool": p.pool, "index": p.index, "name": p.display, "key": p.key}
                               for p in roster.tagged]}


# --------------------------------------------------------------------------------------------- matching
def _index_of(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def resolve(roster: TagRoster, tags: Sequence[object]) -> tuple[list[TaggedPlayer], list[str]]:
    """``player_tags`` entries -> records, matched the way ``nfl2k5_team_history`` matches a CSV row.

    An entry is either a primary-pool roster index (``17`` or ``"17"``) or a
    ``last,first,birth_date`` key; the date may be omitted (``"Vick,Michael"``) when the name is
    unique, and so may the first name (``"Manning"``) when the surname is.  Match order:
    last+first+DOB, then last+DOB, then last+first, then last alone.  Returns the resolved records
    plus a log line for every entry that matched nothing or matched ambiguously."""

    by_exact: dict[tuple[str, str, dt.date | None], list[TaggedPlayer]] = {}
    by_last_dob: dict[tuple[str, dt.date | None], list[TaggedPlayer]] = {}
    by_names: dict[tuple[str, str], list[TaggedPlayer]] = {}
    by_last: dict[str, list[TaggedPlayer]] = {}
    for p in roster.players:
        by_exact.setdefault((normalise_name(p.last), normalise_name(p.first), p.birth), []).append(p)
        by_last_dob.setdefault((normalise_name(p.last), p.birth), []).append(p)
        by_names.setdefault((normalise_name(p.last), normalise_name(p.first)), []).append(p)
        by_last.setdefault(normalise_name(p.last), []).append(p)
    primary = roster.by_pool("primary")
    out: list[TaggedPlayer] = []
    log: list[str] = []
    seen: set[tuple[str, int]] = set()
    for entry in tags:
        index = _index_of(entry)
        found: TaggedPlayer | None = None
        if index is not None:
            if 0 <= index < len(primary):
                found = primary[index]
            else:
                log.append(f"{entry!r}: no primary roster record with index {index}")
        else:
            parts = [part.strip() for part in str(entry).split(",")]
            _require(bool(parts and parts[0]), f"{entry!r}: a star tag needs at least a last name")
            last = parts[0]
            first = parts[1] if len(parts) > 1 else ""
            birth = parse_birth_date(parts[2]) if len(parts) > 2 and parts[2] else None
            ambiguous = 0
            for table, key in ((by_exact, (normalise_name(last), normalise_name(first), birth)),
                               (by_last_dob, (normalise_name(last), birth)),
                               (by_names, (normalise_name(last), normalise_name(first))),
                               (by_last, normalise_name(last))):
                if birth is None and table is by_last_dob:
                    continue
                if first and table is by_last:
                    continue
                hits = table.get(key, [])
                if len(hits) == 1:
                    found = hits[0]
                    break
                if len(hits) > 1:
                    ambiguous = len(hits)
                    break
            if found is None:
                log.append(f"{entry!r}: ambiguous, {ambiguous} records share that identity" if ambiguous
                           else f"{entry!r}: no roster record matches")
        if found is None:
            continue
        if (found.pool, found.index) in seen:
            log.append(f"{entry!r}: duplicate of an earlier tag ({found.display})")
            continue
        seen.add((found.pool, found.index))
        out.append(found)
    return out, log


def apply_body(body: bytes, tags: Sequence[object]) -> tuple[bytes, dict[str, Any]]:
    """A new body with byte +0x53 bit 0 set on the named records and clear on every other one."""

    roster = parse_body(body)
    wanted, log = resolve(roster, tags)
    buf = bytearray(body)
    for player in roster.players:
        buf[player.offset + TAG_RECORD_OFFSET] = 0
    for player in wanted:
        buf[player.offset + TAG_RECORD_OFFSET] = TAG_BIT
    out = bytes(buf)
    # invariant: only the pad byte of a 0x54 record ever changes
    allowed = {p.offset + TAG_RECORD_OFFSET for p in roster.players}
    stray = [i for i in range(len(out)) if out[i] != body[i] and i not in allowed]
    _require(not stray, f"the tag writer touched bytes outside the record pad: {[hex(i) for i in stray[:5]]}")
    check = parse_body(out)
    _require({(p.pool, p.index) for p in check.tagged} == {(p.pool, p.index) for p in wanted},
             "tag round trip")
    return out, {"tagged": len(wanted), "requested": len(tags),
                 "players": [{"pool": p.pool, "index": p.index, "name": p.display, "key": p.key} for p in wanted],
                 "star_list_limit": STAR_LIST_LIMIT, "log": log}


# --------------------------------------------------------------------------------------------- image
def _outer_image():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module("nfl2k5_playbook_position_recode").OuterImage


def _entry(archive) -> Any:
    entries = archive.entries
    _require(len(entries) > ROST_OUTER_INDEX, f"the archive has no outer entry {ROST_OUTER_INDEX}")
    entry = entries[ROST_OUTER_INDEX]
    _require(entry.size == RESOURCE_SIZE, f"outer entry {ROST_OUTER_INDEX} is 0x{entry.size:x} bytes, not the main roster")
    return entry


def resource_status(resource: bytes) -> str:
    if len(resource) != RESOURCE_SIZE or resource[:4] != b"ROST" or _u32(resource, 4) != BODY_SIZE or _u32(resource, 8) != BODY_SIZE:
        return "foreign"
    return body_status(resource[RESOURCE_HEADER_SIZE:])


def status(path: Path | str) -> str:
    """retail | applied | foreign for a disc image or a loose pack folder."""

    with _outer_image()(path) as archive:
        entry = _entry(archive)
        return resource_status(archive.read(entry.virtual_offset, entry.size))


def read_players(path: Path | str) -> list[TaggedPlayer]:
    """Every current-roster record with its identity and its current star bit."""

    with _outer_image()(path) as archive:
        entry = _entry(archive)
        resource = archive.read(entry.virtual_offset, entry.size)
    _require(resource_status(resource) != "foreign", "the roster resource is foreign")
    return parse_body(resource[RESOURCE_HEADER_SIZE:]).players


def normalise_tags(tags: Iterable[object] | None) -> list[object]:
    """A ``BuildPlan.player_tags`` value cleaned up: blanks dropped, order and duplicates kept."""

    out: list[object] = []
    for tag in tags or ():
        if tag is None or isinstance(tag, bool):
            continue
        if isinstance(tag, int):
            out.append(int(tag))
            continue
        text = str(tag).strip()
        if text:
            out.append(text)
    return out


def apply(path: Path | str, tags: Sequence[object], *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write the star tags into the main roster of the disc image at ``path`` (a COPY)."""

    say = progress or (lambda _m: None)
    wanted = normalise_tags(tags)
    _require(bool(wanted), "no players to tag")
    with _outer_image()(path, writable=True) as archive:
        entry = _entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        state = resource_status(before)
        _require(state in ("retail", "applied"), f"the roster's star tags are {state}; refusing")
        say("Matching the star tags to the roster")
        body, receipt = apply_body(before[RESOURCE_HEADER_SIZE:], wanted)
        replacement = before[:RESOURCE_HEADER_SIZE] + body
        if replacement == before:
            return {"status": state, "already_applied": True, "outer_index": ROST_OUTER_INDEX, **receipt}
        say("Writing the star tags into the roster")
        count = archive.write(entry.virtual_offset, replacement)
        _require(count == len(replacement), "short write of the roster resource")
        check = archive.read(entry.virtual_offset, entry.size)
        _require(check == replacement, "read-back of the roster resource differs")
    return {"status": resource_status(replacement), "outer_index": ROST_OUTER_INDEX,
            "virtual_offset": f"0x{entry.virtual_offset:x}",
            "record_offset": f"0x{TAG_RECORD_OFFSET:02x}", "bit": TAG_BIT, **receipt}


__all__ = ["BODY_SIZE", "OBJ_OFF", "PLAYER_SIZE", "POOLS", "RESOURCE_HEADER_SIZE", "RESOURCE_SIZE",
           "RETAIL_PRIMARY_COUNT", "RETAIL_SECONDARY_COUNT", "ROST_OUTER_INDEX", "TagRoster", "TaggedPlayer",
           "PlayerTagError", "apply", "apply_body", "body_status", "normalise_tags", "parse_body",
           "read_players", "resolve", "resource_status", "status", "summary"]
