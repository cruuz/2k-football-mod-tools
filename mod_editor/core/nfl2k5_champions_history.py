"""Super Bowls before the franchise starts, for the champions history (job hn1, beta 79).

The native owner ``nfl2k5_champions`` keeps the last 22 Super Bowls in one checked 270-byte block right after the
practice-squad reserve block ("2K5RSV2", 352 bytes) at the end of the roster arena. A franchise save's auxiliary tail (up
to 366 bytes) occupies the last bytes of the arena, so the block is kept inside the 306 free bytes between the two (it
ends 0x192 bytes before the arena's end; the tail starts 0x16E before it). The arena is saved whole with every franchise,
so the history costs no save size, an old save has no block (an empty history) and the history-pool fold never sees it.
The layout is documented in ``tools/nfl2k5_champions/runtime.c``:

* +0 magic ``2K5CHMP\\0``, +8 version 2, +9 ring size 22, +12 Adler-32 of bytes 0..11 and 16..269 (little endian);
* +16 the newest season's MVP: ``[0]`` Super Bowl number, ``[1..7]`` the player (55 bits: initial, nine letters, position;
  5-bit characters A-Z - . ' space ?), ``[8]`` the player's club + 1;
* +28 twenty-two 11-byte entries, entry ``n % 22`` holding Super Bowl number n:
  ``[0]`` n, ``[1..3]`` champion + 1, runner-up + 1, champion points, runner-up points (6 bits each, little endian),
  ``[4..10]`` Super Bowl MVP (55 bits as above).

This module writes the real Super Bowls XXXIX (February 2005) to LX (February 2026) into a 2026 roster so that a new
franchise shows who won the Super Bowl before it began. The data is ``data/nfl2k5_champions_2026.json``
(``tools/nfl2k5_champions_seed.py`` builds it from three Wikipedia pages read at pinned revisions; every row lists its
sources). Only the block's 270 bytes are written; they must be zero or already hold exactly this data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping
import zlib

SCHEMA = "nfl2k5_champions_history/v1"
DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_champions_2026.json"
MAGIC = b"2K5CHMP\0"
RING, ENTRY, MVP_AT, ENTRIES_AT = 22, 11, 16, 28
USED = ENTRIES_AT + RING * ENTRY                      # 270
RESERVE_MAGIC = b"2K5RSV2\0"
RESERVE_BLOCK = 352
FROM_END = 0x400                                      # the reserve region starts 0x400 bytes before the arena's end
AUX_TAIL = 366                                        # the most a franchise save's auxiliary tail holds (its last bytes)
FREE = FROM_END - RESERVE_BLOCK - AUX_TAIL            # 306 bytes between the reserve block and the auxiliary tail
assert USED <= FREE
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
# The arena order of the 32 clubs (alphabetical by the 2004 nicknames; a relocated or renamed franchise keeps its place)
CLUBS = ("49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers", "Cardinals", "Chargers", "Chiefs",
         "Colts", "Cowboys", "Dolphins", "Eagles", "Falcons", "Giants", "Jaguars", "Jets", "Lions", "Packers", "Panthers",
         "Patriots", "Raiders", "Rams", "Ravens", "Redskins", "Saints", "Seahawks", "Steelers", "Texans", "Titans",
         "Vikings")
FRANCHISE = {"Commanders": "Redskins", "Washington Football Team": "Redskins"}


class ChampionsHistoryError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ChampionsHistoryError(message)


def _sym5(c: str) -> int:
    c = c.upper()
    if "A" <= c <= "Z":
        return ord(c) - 64
    return {"-": 27, ".": 28, "'": 29, " ": 30}.get(c, 31)


def _put_bits(out: bytearray, at: int, value: int, count: int) -> None:
    for b in range(count):
        if value >> b & 1:
            out[(at + b) >> 3] |= 1 << ((at + b) & 7)


def _get_bits(blob: bytes, at: int, count: int) -> int:
    return sum(((blob[(at + b) >> 3] >> ((at + b) & 7)) & 1) << b for b in range(count))


SUFFIXES = ("Jr", "Jr.", "Sr", "Sr.", "II", "III", "IV", "V")


def split_name(name: str) -> tuple[str, str]:
    """(first name, last name without a generational suffix): "Kenneth Walker III" -> ("Kenneth", "Walker")."""

    first, _, last = name.strip().partition(" ")
    head, _, tail = last.rpartition(" ")
    return first, head if head and tail in SUFFIXES else last


def pack_person(name: str, position: str) -> bytes:
    """The 7-byte person field: first initial, up to nine letters of the last name, position code."""

    first, last = split_name(name)
    out = bytearray(7)
    _put_bits(out, 0, _sym5(first[0]) if first else 0, 5)
    for i, c in enumerate(last[:9]):
        _put_bits(out, 5 + 5 * i, _sym5(c), 5)
    _put_bits(out, 50, POSITIONS.index(position), 5)
    return bytes(out)


def unpack_person(blob: bytes) -> dict | None:
    alphabet = " ABCDEFGHIJKLMNOPQRSTUVWXYZ-.' ?"
    first, pos = _get_bits(blob, 0, 5), _get_bits(blob, 50, 5)
    last = ""
    for i in range(9):
        s = _get_bits(blob, 5 + 5 * i, 5)
        if not s:
            break
        last += alphabet[s]
    if not last and not first:
        return None
    return {"initial": alphabet[first] if first else "", "last": last, "position": POSITIONS[pos] if pos < 17 else "?"}


def club_index(name: str) -> int:
    """The arena index of a team name such as "St. Louis Rams" or "Washington Commanders"."""

    matches = [i for i, nick in enumerate(CLUBS) if name.endswith(nick)]
    if not matches:
        matches = [CLUBS.index(v) for k, v in FRANCHISE.items() if name.endswith(k)]
    _require(len(matches) == 1, f"no single club for {name!r}")
    return matches[0]


def entry_bytes(n: int, champion: int, runner_up: int, champion_points: int, runner_points: int,
                sb_mvp: tuple[str, str] | None) -> bytes:
    _require(1 <= n <= 255 and 0 <= champion < 32 and 0 <= runner_up < 32 and champion != runner_up, "bad season")
    t = (champion + 1) | (runner_up + 1) << 6 | min(champion_points, 63) << 12 | min(runner_points, 63) << 18
    out = bytearray(ENTRY)
    out[0] = n
    out[1:4] = t.to_bytes(3, "little")
    if sb_mvp:
        out[4:11] = pack_person(*sb_mvp)
    return bytes(out)


def mvp_slot(n: int, mvp: tuple[str, str] | None, club: int | None) -> bytes:
    """The 9-byte newest-season MVP field: Super Bowl number, person, club + 1."""

    out = bytearray(9)
    if mvp:
        out[0] = n
        out[1:8] = pack_person(*mvp)
        out[8] = 0 if club is None else club + 1
    return bytes(out)


def checksum(block: bytes) -> int:
    return zlib.adler32(block[MVP_AT:USED], zlib.adler32(block[:12]))


def block_bytes(entries: Mapping[int, bytes], mvp: bytes | None = None) -> bytes:
    """The 270-byte history block holding these entries (Super Bowl number -> 11 bytes) and the newest MVP field."""

    out = bytearray(USED)
    out[:8], out[8], out[9] = MAGIC, 2, RING
    if mvp:
        out[MVP_AT:MVP_AT + 9] = mvp
    for n in sorted(entries):
        out[ENTRIES_AT + (n % RING) * ENTRY:ENTRIES_AT + (n % RING + 1) * ENTRY] = entries[n]
    out[12:16] = checksum(bytes(out)).to_bytes(4, "little")
    return bytes(out)


def read_block(raw: bytes) -> list[dict]:
    """The valid seasons of a block, newest first; [] for an absent, foreign or damaged block."""

    if len(raw) < USED or raw[:8] != MAGIC or raw[8] != 2 or raw[9] != RING:
        return []
    if int.from_bytes(raw[12:16], "little") != checksum(raw):
        return []
    rows = []
    slot = raw[MVP_AT:MVP_AT + 9]
    for i in range(RING):
        e = raw[ENTRIES_AT + i * ENTRY:ENTRIES_AT + (i + 1) * ENTRY]
        t = int.from_bytes(e[1:4], "little")
        champion, runner = (t & 63) - 1, (t >> 6 & 63) - 1
        if not e[0] or e[0] % RING != i or not (0 <= champion < 32 and 0 <= runner < 32):
            continue
        rows.append({"super_bowl": e[0], "champion": champion, "runner_up": runner, "champion_points": t >> 12 & 63,
                     "runner_up_points": t >> 18 & 63, "super_bowl_mvp": unpack_person(e[4:11]),
                     "season_mvp": unpack_person(slot[1:8]) if slot[0] == e[0] else None,
                     "season_mvp_club": slot[8] - 1 if slot[0] == e[0] and slot[8] else None})
    return sorted(rows, key=lambda r: -r["super_bowl"])


def load(path: Path | str = DEFAULT_DATA) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: Mapping) -> None:
    _require(data.get("schema") == SCHEMA, "unknown champions history schema")
    _require(type(data.get("base_year")) is int, "invalid base year")
    sources = data.get("sources", {})
    for key, pin in sources.items():
        _require(pin.get("url") and len(pin.get("sha256", "")) == 64, f"source {key} needs a URL and a SHA-256")
    seen = set()
    for row in data.get("seasons", []):
        n = row.get("super_bowl")
        _require(type(n) is int and 1 <= n <= 255 and n not in seen, "each season needs its own Super Bowl number")
        seen.add(n)
        _require(row.get("champion") and row.get("runner_up") and row["champion"] != row["runner_up"], f"Super Bowl {n}: clubs")
        _require(row.get("sources") and all(s in sources for s in row["sources"]), f"Super Bowl {n}: unlisted source")
        for key in ("champion_points", "runner_up_points"):
            _require(type(row.get(key)) is int and 0 <= row[key] <= 63, f"Super Bowl {n}: {key}")
        for key in ("super_bowl_mvp", "season_mvp"):
            person = row.get(key)
            _require(person is None or (person.get("name") and person.get("position") in POSITIONS), f"Super Bowl {n}: {key}")
    _require(bool(seen), "no seasons")


def entries_for(data: Mapping) -> dict[int, bytes]:
    """The newest ``RING`` seasons of the data as entries."""

    validate(data)
    rows = sorted(data["seasons"], key=lambda r: -r["super_bowl"])[:RING]
    out = {}
    for row in rows:
        sb = row.get("super_bowl_mvp")
        out[row["super_bowl"]] = entry_bytes(
            row["super_bowl"], club_index(row["champion"]), club_index(row["runner_up"]), row["champion_points"],
            row["runner_up_points"], (sb["name"], sb["position"]) if sb else None)
    return out


def newest_mvp(data: Mapping) -> bytes:
    """The newest season's MVP field of the data."""

    validate(data)
    row = max(data["seasons"], key=lambda r: r["super_bowl"])
    mvp = row.get("season_mvp")
    return mvp_slot(row["super_bowl"], (mvp["name"], mvp["position"]) if mvp else None,
                    club_index(mvp["team"]) if mvp and mvp.get("team") else None)


def seeded_block(data: Mapping | None = None) -> bytes:
    data = load() if data is None else data
    return block_bytes(entries_for(data), newest_mvp(data))


def gap_offset(body: bytes) -> int:
    """Where the history block begins in a roster body (the arena ends the body), or raise."""

    at = len(body) - FROM_END
    _require(at > 0 and body[at:at + 8] == RESERVE_MAGIC, "this roster has no reserve block (no Studio arena growth)")
    return at + RESERVE_BLOCK


def apply_body(body: bytes, data: Mapping | None = None) -> tuple[bytes, dict]:
    """The roster body with the seasons written into the spare bytes; refuses spare bytes already in use."""

    data = load() if data is None else data
    entries = entries_for(data)
    block = block_bytes(entries, newest_mvp(data))
    at = gap_offset(body)
    current = body[at:at + FREE]
    _require(not any(current) or current[:USED] == block, f"the free bytes at 0x{at:x} are in use")
    out = bytearray(body)
    out[at:at + USED] = block
    return bytes(out), {"seasons": len(entries), "newest_super_bowl": max(entries), "oldest_super_bowl": min(entries),
                        "offset": hex(at), "unchanged": bytes(out) == body, "sources": sorted(data["sources"])}


def read_body(body: bytes) -> list[dict]:
    at = gap_offset(body)
    return read_block(body[at:at + USED])


__all__ = ["SCHEMA", "DEFAULT_DATA", "RING", "ENTRY", "ChampionsHistoryError", "CLUBS", "pack_person", "unpack_person",
           "club_index", "entry_bytes", "mvp_slot", "newest_mvp", "seeded_block", "block_bytes", "read_block", "checksum", "load", "validate", "entries_for",
           "gap_offset", "apply_body", "read_body"]
