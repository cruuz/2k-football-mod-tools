"""Real team history for the Player Card TEAM column: field-87 entries written into the ROST template.

The franchise Player Card's TEAM column (``nfl2k5_team_column``) reads field 87 of the player's
season-history stream: ``(slot << 23) | (87 << 16) | (teamIndex + 1)``.  The rollover cave writes
those entries from the first season a patched disc plays; seasons the retail roster already
carries (1,325 players, 5,867 player-seasons with a games entry, 1982-2003) have none and read
``--``.  This module writes them into the roster resource itself, so every franchise CREATED from
the patched disc shows the real club for those seasons.

Where (retail pack ``vc_53450030/0``, outer entry 5, uncompressed, 0x20-byte wrapper + 0x90F60 body):

* the roster object is the body at +0x40 (``FUN_000c2040`` copies the resource whole into a static
  buffer and relocates it in place, ``FUN_000c0500``); ``obj[0x10]`` = pool used count (36,866),
  ``obj[0x11]`` -> the pool (body 0x41A74), followed by 52,536 zero bytes = 13,134 free dwords, so
  36,866 + 13,134 = 50,000 = the game's own capacity (``FUN_0014e7e0``).  The runtime layout is the
  disc layout: what this module writes into the slack is exactly where the game's own inserts go;
* every player record (0x54, from ``obj[0]``/``obj[1]``) points at its stream with the field-local
  relative pointer at +0x2C (``target = field + i32 - 1``); the streams are contiguous and cover
  the pool exactly, in player order;
* an entry dword: bits 0..15 value, 16..22 field, 23..27 season slot, 28 = deleted, 29 = postseason
  class, 30 = folded, 31 = end of the player's stream.  A player's k-th pro season is slot k; the
  current season slot is ``(player+0x24 >> 8) & 0x1F``; year = base year - (count - slot).

The writer rebuilds only the pool region: for each player the new team entries go in front of the
retail entries (the game inserts at the head, ``FUN_0014f220``), bit 31 stays on the last dword,
``obj[0x10]`` and every +0x2C pointer are recomputed, the used count must stay <= 50,000, and no
byte outside the pool region, the player records' +0x2C words and the used count may change.
Identity for matching a CSV row to a record: first/last name (+0x10/+0x14), birth date packed in
+0x18 (bits 21-27 year - 1900, 16-20 day, 12-15 month; ``FUN_00145d20``), position byte +0x35.

Only seasons whose slot already has a games entry (field 0, regular class) get a team entry: that
is exactly when the card shows a row.  Cost: 1 dword per player-season out of the pool's free
13,134, so the game's automatic folding of the oldest seasons starts earlier.  This never reaches a
franchise created before the patched disc was in use (the save carries its own roster copy).
Unwitnessed in game.

Consistency (2026-09-04, Noah: "make it more consistent"): the shipped CSV covers 5,042 of the
5,838 rows the card can show, and beta 58 left the rest reading ``--`` -- about one row in seven,
scattered.  A season with no CSV row is now filled with the player's **own 2004 club**, read from
the roster's team records (each of the 32 club records begins with a NULL-terminated array of
player pointers before its abbreviation at +0x108), and counted as ``seasons_inferred`` in the
receipt and the match log so the CSV's own coverage stays visible and honest.  A CSV row always
wins over the inference, so a single line in a user CSV corrects any inferred season.  That leaves
exactly three ways a row can still read ``--``: the folded "pre" row (the getter checks bit 30), a
season with no games entry (the card draws no row at all), and a player who is on no 2004 club --
the 170 retail free agents, 92 of whose displayable seasons the CSV does not cover either.  On the
retail roster: 5,746 of 5,838 shown seasons carry a team (was 5,042), the pool goes 36,866 ->
42,612 of 50,000, and the 29 seasons older than the card's 15-row window are still skipped because
no row exists for them.  ``infer_current_team=False`` restores the CSV-only behaviour.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import importlib
import io
import re
import struct
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .nfl2k5_team_column import TEAM_FIELD

ROOT = Path(__file__).resolve().parents[2]

ROST_OUTER_INDEX = 5
RESOURCE_HEADER_SIZE = 0x20
BODY_SIZE = 0x90F60
RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE
OBJ_OFF = 0x40                  # the roster object inside the body
PLAYER_SIZE = 0x54
TEAM_SIZE = 0x1F4
TEAM_ROSTER_BYTES = 0x108       # a team record starts with its player pointers and ends them before +0x108 (the abbreviation)
POOL_CAPACITY = 50_000          # FUN_0014e7e0 for a roster with >= 35 team records
RETAIL_POOL_USED = 36_866
BASE_YEAR = 2004                # the retail roster's current season
MAX_DISPLAY_AGE = 15            # banks 12..26: the card shows the last 15 completed seasons
NFL_TEAM_COUNT = 32

# sha256 of (used count LE, the used pool dwords, every player's +0x2C word), see pool_digest()
RETAIL_POOL_SHA256 = "e181a8f7a3d0cc590d60cdae6ce1d45d4255c5503c4d18ba216bf648fe708f18"
SHIPPED_CSV = ROOT / "data" / "nfl2k5_retail_team_history.csv"
SHIPPED_CSV_SHA256 = "5e8ae2e8f09ac2dd6a397e9735e60641edcf8c2707c40bf42551b66d45577374"   # tools/nfl2k5_team_history_from_nflverse.py, 2026-09-03
SHIPPED_POOL_SHA256 = "f6bb10ada2a46f143c2f766dd029289690a25aa53af4423fa2790e846c8008f9"   # the pool digest after the shipped CSV + the 2004-club fill is applied to the retail roster
ATTRIBUTION = "nflverse-data (https://github.com/nflverse/nflverse-data), CC-BY-4.0"

CSV_COLUMNS = ("last_name", "first_name", "birth_date", "season", "team")
CSV_OPTIONAL = ("position", "roster_index", "source", "note")

# 2004 roster abbreviation -> retail team index (the roster's own team table is preferred at run time)
RETAIL_TEAM_INDEX = {"SF": 0, "CHI": 1, "CIN": 2, "BUF": 3, "DEN": 4, "CLE": 5, "TB": 6, "ARZ": 7, "SD": 8, "KC": 9,
                     "IND": 10, "DAL": 11, "MIA": 12, "PHI": 13, "ATL": 14, "NYG": 15, "JAX": 16, "NYJ": 17, "DET": 18,
                     "GB": 19, "CAR": 20, "NE": 21, "OAK": 22, "STL": 23, "BAL": 24, "WAS": 25, "NO": 26, "SEA": 27,
                     "PIT": 28, "HOU": 29, "TEN": 30, "MIN": 31}
# plain aliases (nflverse / gsis / common spellings) -> 2004 abbreviation
TEAM_ALIASES = {"ARI": "ARZ", "PHX": "ARZ", "PHO": "ARZ", "RAI": "OAK", "LV": "OAK", "LVR": "OAK", "RAM": "STL", "SL": "STL",
                "LAR": "STL", "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "JAC": "JAX", "WSH": "WAS", "GNB": "GB",
                "KAN": "KC", "NWE": "NE", "NOR": "NO", "SFO": "SF", "TAM": "TB", "SDG": "SD", "LAC": "SD", "OTI": "TEN",
                "TB2": "TB", "RAV": "BAL", "CRD": "ARZ", "NYA": "NYJ", "NYN": "NYG"}
# era-dependent codes: code -> [(first_season, last_season, 2004 abbreviation, note)].  A 2004 abbreviation
# always names its franchise, so a code that is ALSO a 2004 abbreviation (HOU, STL, BAL) is read as the
# earlier club only for the seasons when that club existed and the 2004 club did not; the generator
# writes 2004 abbreviations, so its CSV re-reads unchanged.
ERA_CODES = {
    "HOU": [(1900, 1996, "TEN", "Houston Oilers"), (1997, 2100, "HOU", None)],
    "STL": [(1900, 1987, "ARZ", "St. Louis Cardinals"), (1988, 2100, "STL", None)],
    "BAL": [(1900, 1983, "IND", "Baltimore Colts"), (1984, 2100, "BAL", None)],
    "LA": [(1900, 2100, None, "ambiguous: use RAM (Rams) or RAI (Raiders)")],
}


class TeamHistoryError(ValueError):
    """The team-history writer cannot proceed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TeamHistoryError(message)


# --------------------------------------------------------------------------------------------- codes
def resolve_team(code: str, season: int) -> tuple[str, str | None]:
    """A team code as written in a CSV or by nflverse -> (2004 abbreviation, note).  Era codes are
    resolved by season (HOU <= 1996 is the Oilers = TEN, STL <= 1987 the Cardinals = ARZ, ...)."""

    raw = (code or "").strip().upper()
    _require(bool(raw), "empty team code")
    if raw in ERA_CODES:
        for first, last, abbr, note in ERA_CODES[raw]:
            if first <= season <= last:
                _require(abbr is not None, f"team code {raw} in {season}: {note}")
                return abbr, note
        raise TeamHistoryError(f"team code {raw} did not exist in {season}")
    abbr = TEAM_ALIASES.get(raw, raw)
    _require(abbr in RETAIL_TEAM_INDEX, f"unknown team code {code!r}")
    return abbr, None


# --------------------------------------------------------------------------------------------- names
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalise_name(value: str | None) -> str:
    """Lower-case ASCII letters only, generational suffixes dropped (``O'Neal Jr.`` -> ``oneal``)."""

    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    words = [w for w in re.split(r"[\s,.]+", text.lower()) if w]
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return re.sub(r"[^a-z]", "", "".join(words))


def parse_birth_date(value: str | None) -> dt.date | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise TeamHistoryError(f"bad birth date {value!r} (use YYYY-MM-DD)")


# --------------------------------------------------------------------------------------------- roster
@dataclass(frozen=True)
class Player:
    index: int
    offset: int                 # body offset of the 0x54 record
    first: str
    last: str
    birth: dt.date | None
    position: int
    count: int                  # season slot count (years pro)
    stream: int | None          # body offset of the history stream, None when the player has none
    entries: tuple[int, ...]    # the stream's dwords (the last one carries bit 31)

    def games_slots(self) -> set[int]:
        return {(w >> 23) & 0x1F for w in self.entries
                if not (w & 0x10000000) and not (w & 0x20000000) and ((w >> 16) & 0x7F) == 0}

    def team_slots(self) -> set[int]:
        return {(w >> 23) & 0x1F for w in self.entries if not (w & 0x10000000) and ((w >> 16) & 0x7F) == TEAM_FIELD}


@dataclass
class Roster:
    body: bytes
    players: list[Player]
    teams: list[str]            # abbreviation by team index
    pool: int                   # body offset of the pool
    used: int                   # dwords in use
    players_off: int
    player_count: int
    current_team: dict[int, int] = field(default_factory=dict)   # player index -> 2004 club (0..31)

    def team_index(self, abbreviation: str) -> int:
        try:
            return self.teams.index(abbreviation)
        except ValueError:
            _require(abbreviation in RETAIL_TEAM_INDEX, f"no team {abbreviation!r} in this roster")
            return RETAIL_TEAM_INDEX[abbreviation]


def _s32(body: bytes, off: int) -> int:
    return struct.unpack_from("<i", body, off)[0]


def _u32(body: bytes, off: int) -> int:
    return struct.unpack_from("<I", body, off)[0]


def _rel(body: bytes, off: int) -> int | None:
    value = _s32(body, off)
    return None if value == 0 else off + value - 1


def _utf16(body: bytes, off: int | None) -> str:
    if off is None:
        return ""
    end = body.find(b"\0\0", off)
    while end != -1 and (end - off) % 2:
        end = body.find(b"\0\0", end + 1)
    raw = body[off: end if end != -1 else off + 64]
    return raw.decode("utf-16-le", "replace")


def decode_birth(word: int) -> dt.date | None:
    year, month, day = 1900 + ((word >> 21) & 0x7F), (word >> 12) & 0xF, (word >> 16) & 0x1F
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def parse_body(body: bytes) -> Roster:
    """Decode the roster object: players (with their history streams), teams, the pool."""

    _require(len(body) == BODY_SIZE, f"ROST body is {len(body)} bytes, not 0x{BODY_SIZE:x}")
    _require(body[0x0C:0x10] == b"ROST" and _u32(body, 0x10) == 17, "ROST preamble")
    obj = OBJ_OFF
    player_count = _u32(body, obj + 0x00)
    players_off = _rel(body, obj + 0x04)
    team_count = _u32(body, obj + 0x18)
    teams_off = _rel(body, obj + 0x1C)
    used = _u32(body, obj + 0x40)
    pool = _rel(body, obj + 0x44)
    _require(players_off is not None and teams_off is not None and pool is not None, "roster object pointers")
    _require(1 <= player_count <= 4000 and 1 <= team_count <= 64, "implausible roster counts")
    _require(used <= POOL_CAPACITY and pool + POOL_CAPACITY * 4 <= BODY_SIZE, "pool outside the body")
    teams = [_utf16(body, _rel(body, teams_off + k * TEAM_SIZE + 0x108)) for k in range(team_count)]
    players: list[Player] = []
    for index in range(player_count):
        off = players_off + index * PLAYER_SIZE
        stream = _rel(body, off + 0x2C)
        entries: list[int] = []
        if stream is not None:
            _require(pool <= stream < pool + used * 4 and (stream - pool) % 4 == 0, f"player {index}: stream outside the pool")
            at = stream
            while True:
                word = _u32(body, at)
                entries.append(word)
                at += 4
                if word & 0x80000000:
                    break
                _require(at < pool + used * 4, f"player {index}: unterminated stream")
        players.append(Player(index=index, offset=off, first=_utf16(body, _rel(body, off + 0x10)),
                              last=_utf16(body, _rel(body, off + 0x14)), birth=decode_birth(_u32(body, off + 0x18)),
                              position=body[off + 0x35], count=(_u32(body, off + 0x24) >> 8) & 0x1F,
                              stream=stream, entries=tuple(entries)))
    current_team: dict[int, int] = {}
    for k in range(min(team_count, NFL_TEAM_COUNT)):        # 0..31 are the 2004 clubs; 32/33 are USER, 34+ all-star
        base = teams_off + k * TEAM_SIZE
        for slot in range(0, TEAM_ROSTER_BYTES, 4):          # a NULL-terminated array of player pointers at +0x00
            target = _rel(body, base + slot)
            if target is None or not (players_off <= target < players_off + player_count * PLAYER_SIZE) \
                    or (target - players_off) % PLAYER_SIZE:
                break
            current_team.setdefault((target - players_off) // PLAYER_SIZE, k)
    streams = sorted((p.stream, len(p.entries)) for p in players if p.stream is not None)
    covered = 0
    at = pool
    for start, length in streams:
        _require(start == at, "streams are not contiguous in player order")
        at += length * 4
        covered += length
    _require(covered == used, f"streams cover {covered} dwords but the pool says {used}")
    return Roster(body=body, players=players, teams=teams, pool=pool, used=used, players_off=players_off,
                  player_count=player_count, current_team=current_team)


def pool_digest(roster: Roster) -> str:
    h = hashlib.sha256(struct.pack("<I", roster.used))
    h.update(roster.body[roster.pool: roster.pool + roster.used * 4])
    for p in roster.players:
        h.update(roster.body[p.offset + 0x2C: p.offset + 0x30])
    return h.hexdigest()


def body_status(body: bytes) -> str:
    """retail | applied (the shipped CSV) | applied-custom (other field-87 entries) | foreign."""

    try:
        roster = parse_body(body)
    except (TeamHistoryError, struct.error):
        return "foreign"
    digest = pool_digest(roster)
    if digest == RETAIL_POOL_SHA256:
        return "retail"
    if SHIPPED_POOL_SHA256 and digest == SHIPPED_POOL_SHA256:
        return "applied"
    if any(p.team_slots() for p in roster.players):
        return "applied-custom"
    return "foreign"


def summary(body: bytes) -> dict[str, int]:
    roster = parse_body(body)
    return {"players_with_history": sum(1 for p in roster.players if p.stream is not None),
            "seasons_with_games": sum(len(p.games_slots()) for p in roster.players),
            "team_entries": sum(len(p.team_slots()) for p in roster.players),
            "pool_used": roster.used, "pool_free": POOL_CAPACITY - roster.used}


# --------------------------------------------------------------------------------------------- csv
@dataclass(frozen=True)
class Row:
    line: int
    last: str
    first: str
    birth: dt.date | None
    season: int
    team: str                   # the 2004 abbreviation after era resolution
    note: str | None
    position: str | None = None
    roster_index: int | None = None


def read_csv(text: str) -> list[Row]:
    """Parse a team-history CSV (``#`` comment lines allowed; columns last_name, first_name,
    birth_date, season, team; optional position, roster_index).  Bad rows raise."""

    lines = [(n + 1, line) for n, line in enumerate(text.splitlines()) if line.strip() and not line.lstrip().startswith("#")]
    _require(bool(lines), "the CSV has no rows")
    reader = csv.DictReader(io.StringIO("\n".join(line for _n, line in lines)))
    missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
    _require(not missing, f"the CSV lacks the columns {missing}")
    rows: list[Row] = []
    for k, item in enumerate(reader):
        line = lines[k + 1][0] if k + 1 < len(lines) else lines[-1][0]
        try:
            season = int(str(item.get("season") or "").strip())
        except ValueError as exc:
            raise TeamHistoryError(f"line {line}: bad season {item.get('season')!r}") from exc
        _require(1920 <= season <= 2100, f"line {line}: season {season} out of range")
        abbr, note = resolve_team(str(item.get("team") or ""), season)
        raw_index = str(item.get("roster_index") or "").strip()
        rows.append(Row(line=line, last=str(item.get("last_name") or "").strip(), first=str(item.get("first_name") or "").strip(),
                        birth=parse_birth_date(item.get("birth_date")), season=season, team=abbr, note=note,
                        position=(str(item.get("position") or "").strip().upper() or None),
                        roster_index=int(raw_index) if raw_index else None))
        _require(bool(rows[-1].last), f"line {line}: empty last name")
    return rows


# --------------------------------------------------------------------------------------------- matching
POSITION_CODES = ("QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
_POSITION_ALIASES = {"HB": "RB", "S": "FS", "SAF": "FS", "LB": "OLB", "MLB": "ILB", "OL": "T", "OT": "T", "OG": "G", "DL": "DE",
                     "EDGE": "DE", "NT": "DT", "DB": "CB"}


def _position_matches(code: str | None, player: Player) -> bool:
    if not code:
        return False
    code = _POSITION_ALIASES.get(code, code)
    if code not in POSITION_CODES:
        return False
    want = POSITION_CODES.index(code)
    group = {"FS": ("FS", "SS"), "SS": ("FS", "SS"), "OLB": ("OLB", "ILB"), "ILB": ("OLB", "ILB"),
             "DE": ("DE", "DT"), "DT": ("DE", "DT"), "T": ("T", "G", "C"), "G": ("T", "G", "C"), "C": ("T", "G", "C"),
             "RB": ("RB", "FB"), "FB": ("RB", "FB")}.get(code, (code,))
    return POSITION_CODES[player.position] in group if player.position < len(POSITION_CODES) else want == player.position


INFERRED_LOG_SAMPLE = 40        # how many per-player "inferred" lines the log keeps before summarising


@dataclass
class MatchLog:
    exact: int = 0
    fallback_dob: int = 0
    fallback_position: int = 0
    none: int = 0
    ambiguous: int = 0
    seasons_written: int = 0
    would_not_show: int = 0
    never_displayed: int = 0
    already_present: int = 0
    outside_career: int = 0
    duplicate_rows: int = 0
    seasons_inferred: int = 0          # filled with the player's 2004 club because no CSV row covered them
    players_inferred: int = 0
    seasons_no_team: int = 0           # still "--": the player is a 2004 free agent, he has no club to infer
    players_no_team: int = 0
    displayable_seasons: int = 0       # every retail player-season the card can show a row for
    lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "lines"}


def match_rows(roster: Roster, rows: Sequence[Row], *, base_year: int = BASE_YEAR,
               infer_current_team: bool = True) -> tuple[dict[int, dict[int, int]], MatchLog]:
    """CSV rows -> {player index: {slot: team index}} plus a log.  Match order per (name, DOB):
    normalised last+first+DOB, then last+DOB (unique), then last+first+position (unique, warned).

    With ``infer_current_team`` on (the default), every remaining player-season the card can show a
    row for is filled with the player's **2004 club** taken from the roster's own team membership,
    and counted separately as "inferred" so the CSV's own coverage stays visible.  That is what
    makes the TEAM column consistent: a row either names a team or is one of the two cases that
    genuinely have none - a folded "pre" row, or a player with no 2004 club (the retail free
    agents, who appear in no team record at all).  A CSV row always wins over the inference.
    """

    by_exact: dict[tuple[str, str, dt.date | None], list[Player]] = {}
    by_last_dob: dict[tuple[str, dt.date | None], list[Player]] = {}
    by_names: dict[tuple[str, str], list[Player]] = {}
    for p in roster.players:
        by_exact.setdefault((normalise_name(p.last), normalise_name(p.first), p.birth), []).append(p)
        by_last_dob.setdefault((normalise_name(p.last), p.birth), []).append(p)
        by_names.setdefault((normalise_name(p.last), normalise_name(p.first)), []).append(p)
    log = MatchLog()
    additions: dict[int, dict[int, int]] = {}
    seen: set[tuple[int, int]] = set()
    resolved: dict[tuple[str, str, dt.date | None, str | None, int | None], tuple[Player | None, str]] = {}
    for row in rows:
        key = (normalise_name(row.last), normalise_name(row.first), row.birth, row.position, row.roster_index)
        if key not in resolved:
            player: Player | None = None
            how = "none"
            if row.roster_index is not None:
                if 0 <= row.roster_index < len(roster.players):
                    player, how = roster.players[row.roster_index], "roster_index"
            elif row.birth is not None and len(by_exact.get((key[0], key[1], row.birth), [])) == 1:
                player, how = by_exact[(key[0], key[1], row.birth)][0], "exact"
            elif row.birth is not None and len(by_exact.get((key[0], key[1], row.birth), [])) > 1:
                cands = [p for p in by_exact[(key[0], key[1], row.birth)] if _position_matches(row.position, p)]
                if len(cands) == 1:
                    player, how = cands[0], "exact"
                else:
                    how = "ambiguous"
            elif row.birth is not None and len(by_last_dob.get((key[0], row.birth), [])) == 1:
                player, how = by_last_dob[(key[0], row.birth)][0], "fallback_dob"
            else:
                cands = [p for p in by_names.get((key[0], key[1]), []) if _position_matches(row.position, p)]
                if len(cands) == 1:
                    player, how = cands[0], "fallback_position"
                elif len(cands) > 1:
                    how = "ambiguous"
            resolved[key] = (player, how)
            label = f"{row.first} {row.last} {row.birth or '(no DOB)'}"
            if how == "exact":
                log.exact += 1
            elif how == "fallback_dob":
                log.fallback_dob += 1
                log.lines.append(f"line {row.line}: {label}: matched by last name + birth date only -> {player.first} {player.last}")
            elif how == "fallback_position":
                log.fallback_position += 1
                log.lines.append(f"line {row.line}: WARNING {label}: matched by name + position only (no birth date agreement) -> record {player.index}")
            elif how == "roster_index":
                log.exact += 1
            elif how == "ambiguous":
                log.ambiguous += 1
                log.lines.append(f"line {row.line}: {label}: several records match; add roster_index or position")
            else:
                log.none += 1
                log.lines.append(f"line {row.line}: {label}: no record in this roster")
        player, how = resolved[key]
        if player is None:
            continue
        slot = player.count - (base_year - row.season)
        if (player.index, slot) in seen:
            log.duplicate_rows += 1
            log.lines.append(f"line {row.line}: duplicate season {row.season} for record {player.index}")
            continue
        seen.add((player.index, slot))
        if slot < 1 or slot > player.count or row.season >= base_year:
            log.outside_career += 1
            log.lines.append(f"line {row.line}: {player.first} {player.last}: season {row.season} is outside the record's {player.count} seasons ending {base_year}")
            continue
        if player.count - slot > MAX_DISPLAY_AGE:
            log.never_displayed += 1
            continue
        if slot not in player.games_slots():
            log.would_not_show += 1
            log.lines.append(f"line {row.line}: {player.first} {player.last} {row.season}: row would not show (no games entry for that season)")
            continue
        if slot in player.team_slots():
            log.already_present += 1
            continue
        additions.setdefault(player.index, {})[slot] = roster.team_index(row.team)
        log.seasons_written += 1
    for player in roster.players:
        shown = sorted(slot for slot in player.games_slots()
                       if 1 <= slot < player.count and player.count - slot <= MAX_DISPLAY_AGE)
        log.displayable_seasons += len(shown)
        if not infer_current_team:
            continue
        have = set(additions.get(player.index, {})) | player.team_slots()
        wanted = [slot for slot in shown if slot not in have]
        if not wanted:
            continue
        team = roster.current_team.get(player.index)
        if team is None:
            log.seasons_no_team += len(wanted)
            log.players_no_team += 1
            continue
        for slot in wanted:
            additions.setdefault(player.index, {})[slot] = team
        log.seasons_inferred += len(wanted)
        log.players_inferred += 1
        if log.players_inferred <= INFERRED_LOG_SAMPLE:
            years = ", ".join(str(base_year - (player.count - slot)) for slot in wanted)
            log.lines.append(f"record {player.index}: {player.first} {player.last}: inferred "
                             f"{roster.teams[team]} (his 2004 club) for {years}")
    if log.players_inferred > INFERRED_LOG_SAMPLE:
        log.lines.append(f"... and {log.players_inferred - INFERRED_LOG_SAMPLE} more players whose uncovered "
                         "seasons were inferred from their 2004 club")
    if log.players_no_team:
        log.lines.append(f"{log.seasons_no_team} season(s) over {log.players_no_team} player(s) keep \"--\": "
                         "they are on no 2004 club (the retail free agents), so there is nothing to infer")
    return additions, log


# --------------------------------------------------------------------------------------------- writer
def rebuild(roster: Roster, additions: Mapping[int, Mapping[int, int]]) -> bytes:
    """A new body with the team entries inserted at the head of each player's stream; only the
    pool region, the players' +0x2C words and the used count change."""

    body = bytearray(roster.body)
    ordered = sorted((p for p in roster.players if p.stream is not None), key=lambda p: p.stream)
    at = roster.pool
    new_used = 0
    for p in ordered:
        adds = additions.get(p.index, {})
        for slot in adds:
            _require(1 <= slot <= 31, f"player {p.index}: slot {slot} out of range")
            _require(0 <= adds[slot] < NFL_TEAM_COUNT, f"player {p.index}: team index {adds[slot]} out of range")
        words = [(slot << 23) | (TEAM_FIELD << 16) | (adds[slot] + 1) for slot in sorted(adds)] + list(p.entries)
        _require(words[-1] & 0x80000000, f"player {p.index}: stream end bit missing")
        struct.pack_into("<i", body, p.offset + 0x2C, at - (p.offset + 0x2C) + 1)
        for word in words:
            struct.pack_into("<I", body, at, word)
            at += 4
        new_used += len(words)
    for p in roster.players:
        if p.stream is None:
            _require(p.index not in additions, f"player {p.index} has no history stream to extend")
    _require(new_used <= POOL_CAPACITY, f"pool would hold {new_used} dwords, over the game's {POOL_CAPACITY}")
    end = roster.pool + new_used * 4
    body[end: roster.pool + POOL_CAPACITY * 4] = bytes(roster.pool + POOL_CAPACITY * 4 - end)
    struct.pack_into("<I", body, OBJ_OFF + 0x40, new_used)
    out = bytes(body)
    # invariant: nothing outside the pool region, the +0x2C words and the used count changed
    changed = [i for i in range(len(out)) if out[i] != roster.body[i]]
    allowed = set(range(roster.pool, roster.pool + POOL_CAPACITY * 4)) | set(range(OBJ_OFF + 0x40, OBJ_OFF + 0x44))
    for p in roster.players:
        allowed.update(range(p.offset + 0x2C, p.offset + 0x30))
    stray = [i for i in changed if i not in allowed]
    _require(not stray, f"rebuild touched bytes outside the pool: {[hex(i) for i in stray[:5]]}")
    check = parse_body(out)
    _require(check.used == new_used, "used count round trip")
    return out


def apply_body(body: bytes, rows: Sequence[Row], *, base_year: int = BASE_YEAR,
               infer_current_team: bool = True) -> tuple[bytes, dict[str, Any]]:
    roster = parse_body(body)
    additions, log = match_rows(roster, rows, base_year=base_year, infer_current_team=infer_current_team)
    out = rebuild(roster, additions)
    written = sum(len(slots) for slots in additions.values())
    return out, {"pool_used_before": roster.used, "pool_used_after": parse_body(out).used,
                 "players_matched": len(additions), "matches": log.as_dict(), "log": log.lines,
                 "infer_current_team": infer_current_team,
                 "seasons_with_a_team": written,
                 "seasons_displayable": log.displayable_seasons,
                 "seasons_without_a_team": log.displayable_seasons - written}


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
    """retail | applied | applied-custom | foreign for a disc image or a loose pack folder."""

    with _outer_image()(path) as archive:
        entry = _entry(archive)
        return resource_status(archive.read(entry.virtual_offset, entry.size))


def load_rows(source: Path | str | None = "retail") -> tuple[list[Row], dict[str, str]]:
    """The shipped CSV (``"retail"``/None, pinned) or a user file."""

    if source in (None, "", "retail"):
        _require(SHIPPED_CSV.is_file(), f"the built-in team history is missing: {SHIPPED_CSV}")
        data = SHIPPED_CSV.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        _require(not SHIPPED_CSV_SHA256 or digest == SHIPPED_CSV_SHA256, "the built-in team history CSV does not match its pin")
        return read_csv(data.decode("utf-8")), {"source": "retail", "path": str(SHIPPED_CSV), "sha256": digest}
    path = Path(source).expanduser()
    _require(path.is_file(), f"team history CSV not found: {path}")
    data = path.read_bytes()
    return read_csv(data.decode("utf-8-sig")), {"source": "custom", "path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def apply(path: Path | str, source: Path | str | None = "retail", *, base_year: int = BASE_YEAR,
          infer_current_team: bool = True,
          progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write the team history into the main roster of the disc image at ``path`` (a COPY)."""

    say = progress or (lambda _m: None)
    rows, provenance = load_rows(source)
    with _outer_image()(path, writable=True) as archive:
        entry = _entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        state = resource_status(before)
        if state in ("applied", "applied-custom"):
            return {"status": state, "already_applied": True, "outer_index": ROST_OUTER_INDEX, **provenance}
        _require(state == "retail", f"the roster's history pool is {state}, not retail; refusing")
        say("Matching the team history to the roster")
        body, receipt = apply_body(before[RESOURCE_HEADER_SIZE:], rows, base_year=base_year,
                                   infer_current_team=infer_current_team)
        replacement = before[:RESOURCE_HEADER_SIZE] + body
        say("Writing the roster's history pool")
        count = archive.write(entry.virtual_offset, replacement)
        _require(count == len(replacement), "short write of the roster resource")
        check = archive.read(entry.virtual_offset, entry.size)
        _require(check == replacement, "read-back of the roster resource differs")
    return {"status": resource_status(replacement), "outer_index": ROST_OUTER_INDEX, "virtual_offset": f"0x{entry.virtual_offset:x}",
            "rows": len(rows), "base_year": base_year, **provenance, **receipt}


__all__ = ["ATTRIBUTION", "BASE_YEAR", "BODY_SIZE", "CSV_COLUMNS", "ERA_CODES", "MAX_DISPLAY_AGE", "MatchLog", "POOL_CAPACITY",
           "RESOURCE_HEADER_SIZE", "RESOURCE_SIZE", "RETAIL_POOL_SHA256", "RETAIL_POOL_USED", "RETAIL_TEAM_INDEX",
           "ROST_OUTER_INDEX", "Roster", "Row", "TEAM_ROSTER_BYTES", "INFERRED_LOG_SAMPLE", "SHIPPED_CSV", "SHIPPED_CSV_SHA256", "SHIPPED_POOL_SHA256", "TEAM_ALIASES",
           "TeamHistoryError", "apply", "apply_body", "body_status", "load_rows", "match_rows", "normalise_name",
           "parse_birth_date", "parse_body", "pool_digest", "read_csv", "rebuild", "resolve_team", "resource_status",
           "status", "summary"]
