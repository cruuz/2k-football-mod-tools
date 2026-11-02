"""Coaching staff (b780 c2-staff): move, swap and create head coaches, a defensive coordinator for every club, and the
per-club binding of the automatic 2026 CPU coach profiles.

Where the staff lives
---------------------
A roster-edits document's ``staff`` section (schema ``nfl2k5_coach_staff/v1``) says, for the clubs that change, who
their head coach is (a coach already on the roster, by full name, or a created coach), whether he brings his playbook,
and which of the 32 real 2026 defensive coordinators runs each club's defense. Clubs it does not name keep their coach,
their playbook and their own coordinator.

How a move is written
---------------------
The 35 coach records are records the teams point at (team ``+0x14C``). A build-time move is a **content move**: every
club keeps its own record and that record receives the content of the coach it now employs: his name and biography
(rewritten in the roster's one coach string region), his body model (``+0x18``), his picture (``+0x40``), his ratings,
his native play-calling tendencies and his career numbers. With his new club his seasons with the team and this
season's wins, losses and ties start at zero, and the announcer flag (``+0x1A`` bit 0x02, "no recorded name") is set so
the commentary uses its generic head-coach line: the recorded coach-name lines are picked by the CLUB (cue 9200 + the
team's speech id), so they can never name a moved coach. Records stay with their clubs because the historic, all-time and
Pro Bowl teams share the club records (the New England record is also the coach of BWG, LAL, BFM, ANE, AFC and NFL), and
because no game code that pairs a club with its record can then be surprised. Team pointers never change.

Moves are written by name, so applying the same staff twice changes nothing, and so does a rebuild from a disc that was
built with it.

The 2026 CPU coach profiles
---------------------------
``nfl2k5_coach_ai`` compiles one profile per club against the club's own final playbook. With a staff change each club
gets the profile of the coach it now employs (his offense, fitted to the host club's book), with the defensive rings of
the club's coordinator, and the kernel's 32-row table is written to say so (``nfl2k5_coach_ai.install_table``). A club
whose coach has no 2026 profile (a 2004 coach, a created coach without a play-calling style) plays with its coach
record's native tendencies, and only that club. ``profile_bindings`` is the per-club answer.

"Bring his playbook" makes the host club's PLAY resource a byte copy of the final book of the club the coach heads on the
SOURCE roster (all 32 PLAY resources have one size, so this is a fixed-span write). The host keeps its label, franchise
key and play-call screen name. The copies are made from one snapshot, so a swap where both coaches bring their books is
exact; rebuilding from a disc that already carries the move copies nothing (the coach already heads that club).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "nfl2k5_coach_staff/v1"
OWNER = "nfl2k5_coach_staff"
CLUB_COUNT = 32

# ---------------------------------------------------------------------------------------------- the coach record
RECORD_SIZE = 0xA8
STRING_FIELDS = (0x00, 0x04, 0x08, 0x0C, 0x10)       # first name, last name, three biography lines (relative pointers)
CONTENT_START = 0x14                                 # every byte from here to the end of the record is plain data
HEIGHT, WEIGHT = 0x14, 0x16                          # u16 (inches, pounds; INFERRED, no reader found)
BODY, FLAGS = 0x18, 0x1A                             # u16 model number (c%02d.iff), u8 flags
FLAG_FREE, FLAG_GENERIC_NAME = 0x01, 0x02            # free record (Create Team hands it out), "no recorded name"
PHOTO = 0x40                                         # u16 picture id (7000 + asset on the 32 clubs)
WITH_TEAM_FIELDS = (0x1C, 0x26, 0x28, 0x2A)          # seasons with the team; this season's wins, losses, ties
RATINGS = 0x42                                       # 23 bytes, nfl2k5_franchise_save.COACH_RATINGS order
PLAYCALLING_RUN = 0x59                               # u8 run share; the native tendency block runs to the record's end
TENDENCY_BLOCK = (0x59, RECORD_SIZE)
NAMED_TENDENCIES = 0x83                              # 10 bytes, nfl2k5_franchise_save.COACH_TENDENCIES order
NO_PHOTO = 8999                                      # the picture id of the game's own created-team coaches
CREATED_BODY = 50                                    # c50.iff, the created-team coach model
#: The coach models (c%02d.iff) a retail USA disc carries; a record's body must name one of them.
KNOWN_BODIES = tuple(range(31)) + (33, 36, 37, 50, 51)
NAME_MAX, BIO_MAX, BIO_LINES = 24, 52, 3             # the longest the game's own records hold
PROFILE_NAME_UNITS = 12                              # a 2026 profile name: twelve UTF-16 units + NUL
CREATED_IDENTITY_TEAM = "STAFF"                      # identity namespace of a created coach's profile

# ---------------------------------------------------------------------------------------------- the 32 clubs
#: Book (label table) codes in book order: the second string of the roster's 36-entry label table, the keys of
#: nfl2k5_playbook_pack's BOOK_ENTRIES and of data/vip/defense_identity_2026.json.
BOOK_CODES = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARZ", "SD", "KC", "IND", "DAL", "MIA", "PHI", "ATL",
              "NYG", "JAX", "NYJ", "DET", "GB", "CAR", "NE", "OAK", "STL", "BAL", "WAS", "NO", "SEA", "PIT", "HOU",
              "TEN", "MIN")
TEAM_CODES = {"ARZ": "ARI", "SD": "LAC", "OAK": "LV", "STL": "LAR"}     # book code -> 2026 code where they differ
NICKNAMES = ("49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers", "Cardinals", "Chargers", "Chiefs",
             "Colts", "Cowboys", "Dolphins", "Eagles", "Falcons", "Giants", "Jaguars", "Jets", "Lions", "Packers",
             "Panthers", "Patriots", "Raiders", "Rams", "Ravens", "Commanders", "Saints", "Seahawks", "Steelers",
             "Texans", "Titans", "Vikings")
PLACES = ("San Francisco", "Chicago", "Cincinnati", "Buffalo", "Denver", "Cleveland", "Tampa Bay", "Arizona",
          "Los Angeles Chargers", "Kansas City", "Indianapolis", "Dallas", "Miami", "Philadelphia", "Atlanta",
          "New York Giants", "Jacksonville", "New York Jets", "Detroit", "Green Bay", "Carolina", "New England",
          "Las Vegas", "Los Angeles Rams", "Baltimore", "Washington", "New Orleans", "Seattle", "Pittsburgh", "Houston",
          "Tennessee", "Minnesota")
_EXTRA_ALIASES = {"WSH": "WAS", "REDSKINS": "WAS", "WASHINGTON COMMANDERS": "WAS", "LA RAMS": "STL",
                  "LA CHARGERS": "SD", "ST. LOUIS": "STL", "SAN DIEGO": "SD", "OAKLAND": "OAK"}


class StaffError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise StaffError(message)


@dataclass(frozen=True)
class Club:
    index: int          # team record ordinal = book index = label index (0..31)
    book: str           # book / label code (ARZ ... WAS)
    team: str           # 2026 code (ARI, LAC, LV, LAR; otherwise the book code)
    asset: int          # team asset id (the 2004 team code the art and models use)
    nickname: str
    place: str

    @property
    def title(self) -> str:
        return self.place


@lru_cache(maxsize=1)
def _portrait_rows() -> tuple[dict, ...]:
    rows = json.loads((ROOT / "data/vip/coach_portraits_2026.json").read_text(encoding="utf-8"))
    return tuple(sorted(rows, key=lambda r: r["book_index"]))


@lru_cache(maxsize=1)
def _clubs() -> tuple[Club, ...]:
    rows = _portrait_rows()
    require([r["book_index"] for r in rows] == list(range(CLUB_COUNT)), "the 2026 coach directory is not 32 clubs")
    out = []
    for index, row in enumerate(rows):
        book = BOOK_CODES[index]
        require(TEAM_CODES.get(book, book) == row["team"], f"club {index}: the coach directory names {row['team']}")
        out.append(Club(index, book, row["team"], row["asset"], NICKNAMES[index], PLACES[index]))
    return tuple(out)


CLUBS: tuple[Club, ...] = ()        # filled lazily by clubs(); module constant for readers that import it


def clubs() -> tuple[Club, ...]:
    global CLUBS
    if not CLUBS:
        CLUBS = _clubs()
    return CLUBS


@lru_cache(maxsize=1)
def _aliases() -> dict[str, int]:
    out: dict[str, int] = {}
    for c in clubs():
        for key in (c.book, c.team, c.nickname, c.place, f"{c.place} {c.nickname}"):
            out[key.upper()] = c.index
    for key, book in _EXTRA_ALIASES.items():
        out[key] = BOOK_CODES.index(book)
    return out


def club(value) -> Club:
    """A club by index (0..31), book code, 2026 code, roster abbreviation, nickname or place; StaffError otherwise."""
    if isinstance(value, Club):
        return value
    if type(value) is int:
        require(0 <= value < CLUB_COUNT, f"there is no club {value}: clubs are 0..31")
        return clubs()[value]
    require(isinstance(value, str) and value.strip(), f"{value!r} is not a club")
    index = _aliases().get(value.strip().upper())
    require(index is not None, f"{value!r} is not one of the 32 clubs")
    return clubs()[index]


# ---------------------------------------------------------------------------------------------- the people
@lru_cache(maxsize=1)
def _coach_sources() -> dict[str, dict]:
    rows = json.loads((ROOT / "data/vip/coach_sources_2026.json").read_text(encoding="utf-8"))
    return {r["team"]: r for r in rows}


@lru_cache(maxsize=1)
def _directory() -> tuple[dict, ...]:
    sources = _coach_sources()
    out = []
    for row in _portrait_rows():
        home = clubs()[row["book_index"]]
        source = sources.get(row["team"])
        require(source is not None and source["profile_name"] == row["name"]
                and source["native_book_index"] == row["book_index"],
                f"{row['team']}: the coach sources and the portrait directory disagree")
        out.append(dict(id=row["team"], name=source["coach"], home=home.book, home_index=home.index,
                        portrait=row["portrait"], alternate=row.get("alternate_portrait"),
                        profile_name=row["name"], identity=row["identity"], legacy_identity=row["legacy_identity"],
                        sources=list(source.get("sources") or [])))
    return tuple(out)


def head_coach_directory() -> list[dict]:
    """The 32 2026 head coaches: id (2026 club code), name, home (book code), home_index, portrait, alternate (or None),
    profile_name, identity, legacy_identity, sources."""
    return copy.deepcopy(list(_directory()))


def directory_coach(value) -> dict:
    """A 2026 head coach by id (2026 club code), any club spelling of his 2026 club, or his full name."""
    text = str(value or "").strip()
    for row in _directory():
        if text.casefold() == row["name"].casefold():
            return dict(row)
    try:
        home = club(text)
    except StaffError:
        raise StaffError(f"{value!r} is not one of the 32 2026 head coaches") from None
    return dict(_directory()[home.index])


@lru_cache(maxsize=1)
def _identity_rows() -> dict[str, dict]:
    from . import nfl2k5_defense_rings as rings
    return rings.load_identity()["teams"]


def coordinator_directory() -> list[dict]:
    """The 32 2026 defensive coordinators: id (book code of his 2026 club), name, home (book code), front, family,
    baseline_2025 (the 2025 team whose calls the rings are fitted to), role, source."""
    out = []
    for c in clubs():
        row = _identity_rows()[c.book]
        out.append(dict(id=c.book, name=row["dc"], home=c.book, home_index=c.index, front=row.get("front"),
                        family=row.get("family"), baseline_2025=row.get("baseline_2025"),
                        role=row.get("baseline_role"), source=row.get("source")))
    return out


def coordinator(value) -> dict:
    text = str(value or "").strip()
    for row in coordinator_directory():
        if text.casefold() == row["name"].casefold():
            return row
    try:
        home = club(text)
    except StaffError:
        raise StaffError(f"{value!r} is not one of the 32 2026 defensive coordinators") from None
    return coordinator_directory()[home.index]


# ---------------------------------------------------------------------------------------------- the document
_RATING_NAMES = ("overall", "offense", "rush_for", "pass_for", "defense", "pass_rush", "pass_coverage",
                 "qb", "rb", "te", "wr", "ol", "dl", "lb", "db", "special_teams", "professionalism",
                 "preparation", "conditioning", "motivation", "leadership", "discipline", "respect")
_TENDENCY_NAMES = ("shotgun_run", "shotgun_pass", "split_back_run", "split_back_pass", "i_form_run",
                   "i_form_pass", "lone_back_run", "lone_back_pass", "empty_run", "empty_pass")
_CAREER_FIELDS = {"seasons_with_team": 0x1C, "total_seasons": 0x1E, "wins": 0x20, "losses": 0x22, "ties": 0x24,
                  "winning_seasons": 0x30, "super_bowls": 0x32, "playoff_wins": 0x34, "playoff_losses": 0x36,
                  "super_bowl_wins": 0x38, "super_bowl_losses": 0x3A}
_SPEC_KEYS = {"id", "first", "last", "bio", "body", "photo", "style", "ratings", "tendencies", "playcalling_run",
              "fields", "height_in", "weight_lb", "source", "note"}


def empty() -> dict:
    return {"schema": SCHEMA, "head_coaches": [], "defensive_coordinators": [], "created_coaches": []}


def _text(value, label, *, low=1, high=NAME_MAX):
    require(isinstance(value, str), f"{label} must be text")
    require("\0" not in value and "\r" not in value and "\n" not in value, f"{label} cannot hold a line break or NUL")
    require(low <= len(value) <= high, f"{label} must be {low} to {high} characters")
    require(all(ch.isprintable() for ch in value), f"{label} has a character the game cannot print")
    return value


def _number(value, label, low, high):
    require(type(value) is int and low <= value <= high, f"{label} must be a whole number from {low} to {high}")
    return value


def _normalize_created(spec) -> dict:
    require(isinstance(spec, Mapping), "a created coach must be an object")
    unknown = sorted(set(spec) - _SPEC_KEYS)
    require(not unknown, f"created coach {spec.get('id')!r}: unknown fields {', '.join(unknown)}")
    out = {"id": _text(spec.get("id"), "a created coach's id", high=40)}
    who = f"created coach {out['id']!r}"
    out["first"] = _text(spec.get("first"), f"{who}: first name")
    out["last"] = _text(spec.get("last"), f"{who}: last name")
    bio = list(spec.get("bio") or [])
    require(len(bio) <= BIO_LINES, f"{who}: at most {BIO_LINES} biography lines")
    out["bio"] = [_text(line, f"{who}: biography line", low=0, high=BIO_MAX) for line in bio]
    body = spec.get("body", CREATED_BODY)
    require(body in KNOWN_BODIES and type(body) is int,
            f"{who}: body {body!r} is not one of the game's coach models ({', '.join(map(str, KNOWN_BODIES))})")
    out["body"] = body
    out["photo"] = _number(spec.get("photo", NO_PHOTO), f"{who}: photo", 0, 0xFFFF)
    if spec.get("style") not in (None, ""):
        out["style"] = directory_coach(spec["style"])["id"]
    for key, names, high in (("ratings", _RATING_NAMES, 99), ("tendencies", _TENDENCY_NAMES, 100),
                             ("fields", tuple(_CAREER_FIELDS), 0xFFFF)):
        values = spec.get(key) or {}
        require(isinstance(values, Mapping), f"{who}: {key} must be an object")
        bad = sorted(set(values) - set(names))
        require(not bad, f"{who}: unknown {key} {', '.join(bad)}")
        out[key] = {name: _number(values[name], f"{who}: {key} {name}", 0, high) for name in names if name in values}
    if "playcalling_run" in spec:
        out["playcalling_run"] = _number(spec["playcalling_run"], f"{who}: run share", 0, 100)
    if "height_in" in spec:
        out["height_in"] = _number(spec["height_in"], f"{who}: height", 48, 96)
    if "weight_lb" in spec:
        out["weight_lb"] = _number(spec["weight_lb"], f"{who}: weight", 100, 450)
    for key in ("source", "note"):
        if spec.get(key):
            out[key] = _text(spec[key], f"{who}: {key}", high=400)
    return out


def normalize(staff) -> dict:
    """A checked copy of a ``staff`` section with canonical club codes; StaffError in plain words otherwise.
    The roster is not needed: this checks only what the document says on its own."""
    if staff in (None, {}):
        return empty()
    require(isinstance(staff, Mapping), "the coaching staff must be an object")
    require(staff.get("schema", SCHEMA) == SCHEMA, f"unknown coaching staff schema {staff.get('schema')!r}")
    unknown = sorted(set(staff) - {"schema", "head_coaches", "defensive_coordinators", "created_coaches", "note"})
    require(not unknown, f"the coaching staff has unknown sections: {', '.join(unknown)}")
    out = empty()
    created = []
    for spec in staff.get("created_coaches") or []:
        created.append(_normalize_created(spec))
    ids = [c["id"] for c in created]
    require(len(ids) == len(set(ids)), "two created coaches share one id")
    out["created_coaches"] = created
    seen_teams, seen_coaches = {}, {}
    for entry in staff.get("head_coaches") or []:
        require(isinstance(entry, Mapping), "a head coach entry must be an object")
        bad = sorted(set(entry) - {"team", "coach", "created", "playbook"})
        require(not bad, f"a head coach entry has unknown fields {', '.join(bad)}")
        host = club(entry.get("team"))
        require(host.index not in seen_teams, f"{host.place} is named twice in the head coaches")
        seen_teams[host.index] = True
        require(("coach" in entry) != ("created" in entry),
                f"{host.place}: name either a coach on the roster or a created coach, not both or neither")
        row = {"team": host.book}
        if "coach" in entry:
            name = _text(entry["coach"], f"{host.place}: head coach", high=2 * NAME_MAX + 1).strip()
            key = name.casefold()
            require(key not in seen_coaches, f"{name} is named head coach of both {seen_coaches.get(key)} "
                                            f"and {host.place}")
            seen_coaches[key] = host.place
            row["coach"] = name
        else:
            require(entry["created"] in ids, f"{host.place}: there is no created coach {entry['created']!r}")
            require(entry["created"] not in seen_coaches,
                    f"created coach {entry['created']!r} is named head coach of two clubs")
            seen_coaches[entry["created"]] = host.place
            row["created"] = entry["created"]
        playbook = entry.get("playbook", "club")
        require(playbook in ("club", "coach"), f"{host.place}: playbook must be 'club' or 'coach'")
        if playbook == "coach":
            if "created" in row:
                spec = next(c for c in created if c["id"] == row["created"])
                require("style" in spec, f"{host.place}: a created coach brings a playbook only with a play-calling "
                                         "style (the style coach's club's book)")
            row["playbook"] = "coach"
        out["head_coaches"].append(row)
    out["head_coaches"].sort(key=lambda r: club(r["team"]).index)
    seen = {}
    for entry in staff.get("defensive_coordinators") or []:
        require(isinstance(entry, Mapping) and set(entry) <= {"team", "dc"} and "team" in entry and "dc" in entry,
                "a defensive coordinator entry is {\"team\": club, \"dc\": coordinator}")
        host = club(entry["team"])
        require(host.index not in seen, f"{host.place} is named twice in the defensive coordinators")
        seen[host.index] = True
        out["defensive_coordinators"].append({"team": host.book, "dc": coordinator(entry["dc"])["id"]})
    out["defensive_coordinators"].sort(key=lambda r: club(r["team"]).index)
    if staff.get("note"):
        out["note"] = _text(staff["note"], "the staff note", high=400)
    return out


def is_empty(staff) -> bool:
    value = normalize(staff)
    return not value["head_coaches"] and not value["defensive_coordinators"]


# ---------------------------------------------------------------------------------------------- reading a roster
@dataclass
class HeadCoach:
    club: Club
    record_index: int
    record_offset: int
    first: str
    last: str
    bio: tuple[str, str, str]
    photo: int
    body: int
    flags: int
    fields: dict[str, int]
    ratings: dict[str, int]
    tendencies: dict[str, int]
    playcalling_run: int
    directory_id: str | None          # the 2026 head coach this record is (name and picture), or None

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()

    def as_dict(self) -> dict:
        out = {k: v for k, v in self.__dict__.items() if k != "club"}
        out.update(club=self.club.book, team=self.club.team, place=self.club.place, name=self.name, bio=list(self.bio))
        return out


def _coach_tool():
    from . import nfl2k5_roster_records as rr
    return rr._coach_tool()


def _strings(body, record) -> list[str]:
    cw = _coach_tool()
    out = []
    for at in STRING_FIELDS:
        target = cw.relative_target(bytes(body), record + at, f"coach +0x{at:x}")
        out.append(cw.utf16z(bytes(body), target, f"coach +0x{at:x}") if target is not None else "")
    return out


def _directory_match(name: str, photo: int) -> str | None:
    for row in _directory():
        if row["name"] == name and photo in (row["portrait"], row["alternate"] or row["portrait"]):
            return row["id"]
    return None


def _coach_table(body) -> dict[str, int]:
    """The coach table of a main ROST body: retail, or grown by the roster capacity arena (its tables move; the coach
    table and its strings do not). {"offset", "count", "end"}."""
    def rel(field):
        value = struct.unpack_from("<i", body, field)[0]
        return None if value == 0 else field + value - 1
    require(len(body) >= 0x100 and bytes(body[0x0C:0x10]) == b"ROST", "this is not a main roster")
    root = rel(0x14)
    require(root is not None and 0 < root < len(body) - 0x70, "the roster's object is missing")
    count = struct.unpack_from("<I", body, root + 0x30)[0]
    table = rel(root + 0x34)
    require(table is not None and CLUB_COUNT < count <= 64 and table + count * RECORD_SIZE <= len(body),
            "the roster's coach table is not the game's")
    return {"offset": table, "count": count, "end": table + count * RECORD_SIZE, "stride": RECORD_SIZE}


def _club_records(body, teams) -> dict[int, tuple[int, int]]:
    """club index -> (coach record index, record offset) for the 32 clubs; StaffError when the roster is not that."""
    table = _coach_table(body)
    out = {}
    for team in teams:
        if team.index >= CLUB_COUNT:
            continue
        require(team.coach_offset is not None, f"club {team.index} has no head coach record")
        offset = team.coach_offset
        require(table["offset"] <= offset < table["end"] and (offset - table["offset"]) % RECORD_SIZE == 0,
                f"club {team.index}'s coach pointer is not a coach record")
        out[team.index] = ((offset - table["offset"]) // RECORD_SIZE, offset)
    require(sorted(out) == list(range(CLUB_COUNT)), "this roster does not have the 32 clubs")
    require(len({v[0] for v in out.values()}) == CLUB_COUNT, "two clubs share one head coach record")
    return out


def _read(body, team_index, record_index, offset) -> HeadCoach:
    raw = bytes(body[offset:offset + RECORD_SIZE])
    first, last, *bio = _strings(body, offset)
    photo = struct.unpack_from("<H", raw, PHOTO)[0]
    name = f"{first} {last}".strip()
    return HeadCoach(club=clubs()[team_index], record_index=record_index, record_offset=offset, first=first, last=last,
                     bio=tuple(bio), photo=photo, body=struct.unpack_from("<H", raw, BODY)[0], flags=raw[FLAGS],
                     fields={k: struct.unpack_from("<H", raw, at)[0] for k, at in _CAREER_FIELDS.items()},
                     ratings={k: raw[RATINGS + i] for i, k in enumerate(_RATING_NAMES)},
                     tendencies={k: raw[NAMED_TENDENCIES + i] for i, k in enumerate(_TENDENCY_NAMES)},
                     playcalling_run=raw[PLAYCALLING_RUN], directory_id=_directory_match(name, photo))


def _teams_of(body, teams=None):
    if teams is not None:
        return teams
    from . import nfl2k5_roster_records as rr
    return rr.RosterDocument(bytes(body)).teams


def coach_records(body, teams=None) -> dict[int, HeadCoach]:
    """club index -> the head coach record it points at (read only)."""
    teams = _teams_of(body, teams)
    return {i: _read(body, i, rec, off) for i, (rec, off) in sorted(_club_records(body, teams).items())}


def read_roster(body, teams=None) -> list[HeadCoach]:
    """The 32 clubs' head coaches in club order."""
    return list(coach_records(body, teams).values())


def read_image(image) -> list[HeadCoach]:
    from . import nfl2k5_playbook_pack as packs
    with packs._outer_image().OuterImage(image) as archive:
        body = archive.read_entry(5)[32:]
    return read_roster(body)


def locate_directory_coach(body, teams, team_code) -> int | None:
    """Record offset of the 2026 head coach of ``team_code`` (his 2026 club) wherever he heads a club now, matched by
    his full name; None when no club employs him (fired, or a roster without the 2026 names)."""
    want = directory_coach(team_code)["id"]
    # by name AND picture: a 2004 roster has its own Andy Reid (Philadelphia's coach then, with that club's picture)
    hits = [c.record_offset for c in coach_records(body, teams).values() if c.directory_id == want]
    return hits[0] if len(hits) == 1 else None


# ---------------------------------------------------------------------------------------------- planning
@dataclass
class ClubPlan:
    club: Club
    coach: str                        # the head coach's full name after the staff
    source_club: Club | None          # the club whose record content he brings (None: created)
    created: dict | None              # the created coach spec
    moved: bool                       # the record content changes
    dc: str                           # book code of the defensive coordinator's identity row
    dc_name: str
    playbook_from: Club               # the club whose final book this club plays
    directory_id: str | None          # the 2026 head coach he is, or None
    profile: str | None               # whose 2026 play-calling the profile uses (directory id), or None
    native_reason: str | None         # why the club plays native tendencies (no 2026 profile)

    def as_dict(self) -> dict:
        return dict(team=self.club.book, place=self.club.place, coach=self.coach,
                    from_team=self.source_club.book if self.source_club else None,
                    created=self.created["id"] if self.created else None, moved=self.moved,
                    dc=self.dc, dc_name=self.dc_name, playbook_from=self.playbook_from.book,
                    directory_id=self.directory_id, profile=self.profile, native_reason=self.native_reason)


@dataclass
class StaffPlan:
    staff: dict
    clubs: list[ClubPlan] = field(default_factory=list)
    fired: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def changes(self) -> list[ClubPlan]:
        return [c for c in self.clubs if c.moved]

    def as_dict(self) -> dict:
        return dict(schema=SCHEMA, ok=self.ok, errors=list(self.errors), notes=list(self.notes),
                    fired=list(self.fired), clubs=[c.as_dict() for c in self.clubs])


def plan(staff, body, teams=None) -> StaffPlan:
    """The staff this document gives on this roster (the roster after the ``coaches`` list), without writing.
    ``errors`` lists every problem in plain words; no errors means ``apply_to_body`` writes exactly this plan."""
    try:
        value = normalize(staff)
    except StaffError as exc:
        return StaffPlan(staff={}, errors=[str(exc)])
    result = StaffPlan(staff=value)
    try:
        current = coach_records(body, teams)
    except (StaffError, ValueError) as exc:
        result.errors.append(f"the roster's coaches cannot be read: {exc}")
        return result
    place = [c.place for c in clubs()]
    created = {c["id"]: c for c in value["created_coaches"]}
    entries = {club(e["team"]).index: e for e in value["head_coaches"]}
    where: dict[str, list[int]] = {}
    for i, coach in current.items():
        where.setdefault(coach.name.casefold(), []).append(i)
    # 1. every club's head coach: a roster record's coach (by the club he heads now), a created coach, or an error
    final: dict[int, tuple[str, Any]] = {}
    for i in range(CLUB_COUNT):
        entry = entries.get(i)
        if entry is None:
            final[i] = ("record", i)
        elif "created" in entry:
            final[i] = ("created", created[entry["created"]])
        else:
            hits = where.get(entry["coach"].casefold(), [])
            if len(hits) == 1:
                final[i] = ("record", hits[0])
            else:
                final[i] = ("error", None)
                result.errors.append(f"{place[i]}: there is no head coach named {entry['coach']} on this roster"
                                     if not hits else
                                     f"{entry['coach']} heads more than one club on this roster "
                                     f"({', '.join(place[h] for h in hits)}); rename one first")
    # 2. one coach, one club: a club whose coach leaves and that names nobody has no coach
    takers: dict[int, list[int]] = {}
    for i, (kind, source) in final.items():
        if kind == "record":
            takers.setdefault(source, []).append(i)
    for source, who in sorted(takers.items()):
        if len(who) < 2:
            continue
        name = current[source].name
        if source in who and source not in entries:
            other = next(j for j in who if j != source)
            result.errors.append(f"{place[source]} has no head coach: {name} moves to {place[other]}. "
                                 f"Choose {place[source]}'s new coach (or swap them).")
            final[source] = ("error", None)
        else:
            result.errors.append(f"{name} cannot head both {place[who[0]]} and {place[who[1]]}")
            for j in who[1:]:
                final[j] = ("error", None)

    def name_of(i):
        kind, value_ = final[i]
        return (current[value_].name if kind == "record" else
                f"{value_['first']} {value_['last']}" if kind == "created" else current[i].name)

    seen: dict[str, int] = {}
    for i in range(CLUB_COUNT):
        if final[i][0] == "error":
            continue
        key = name_of(i).casefold()
        if key in seen:
            result.errors.append(f"two clubs would have a head coach named {name_of(i)} ({place[seen[key]]} and "
                                 f"{place[i]}); the Studio tells coaches apart by name")
        seen.setdefault(key, i)
    # 3. defensive coordinators: every club keeps its own unless named; one person, one club
    named = {club(e["team"]).index: e["dc"] for e in value["defensive_coordinators"]}
    dcs = {i: named.get(i, clubs()[i].book) for i in range(CLUB_COUNT)}
    dc_names = {row["id"]: row["name"] for row in coordinator_directory()}
    holder: dict[str, int] = {}
    for i in range(CLUB_COUNT):
        first = holder.setdefault(dcs[i], i)
        if first != i:
            fix = [place[j] for j in (first, i) if j not in named] or [place[first], place[i]]
            result.errors.append(f"{dc_names[dcs[i]]} would run the defense of both {place[first]} and {place[i]}. "
                                 f"Give {' or '.join(fix)} another defensive coordinator (or swap them).")
    # 4. the per-club plan
    for i in range(CLUB_COUNT):
        c = clubs()[i]
        kind, source = final[i]
        entry = entries.get(i) or {}
        if kind == "error":
            result.clubs.append(ClubPlan(c, current[i].name, c, None, False, dcs[i], dc_names[dcs[i]], c,
                                         current[i].directory_id, None, "the staff for this club has an error"))
            continue
        if kind == "created":
            spec = source
            coach_name, directory_id, profile, origin = f"{spec['first']} {spec['last']}", None, spec.get("style"), None
            book_from = c
            if entry.get("playbook") == "coach":
                style = directory_coach(spec["style"])
                hits = where.get(style["name"].casefold(), [])
                book_from = clubs()[hits[0]] if len(hits) == 1 else club(style["home"])
            reason = None if profile else (f"{coach_name} is a created coach without a play-calling style, so "
                                           f"{c.place} plays with his record's own tendencies")
            moved = True
        else:
            spec, origin = None, clubs()[source]
            coach_name, directory_id = current[source].name, current[source].directory_id
            profile = directory_id
            book_from = origin if entry.get("playbook") == "coach" else c
            reason = None if profile else (f"{coach_name} has no 2026 CPU coach profile (he is not one of the 32 2026 "
                                           f"head coaches with his own name and picture), so {c.place} plays with "
                                           "his record's own tendencies")
            moved = source != i
        result.clubs.append(ClubPlan(c, coach_name, origin, spec, moved, dcs[i], dc_names[dcs[i]], book_from,
                                     directory_id, profile, reason))
        if moved:
            result.notes.append(f"{c.place}: head coach {coach_name} "
                                f"{'from ' + origin.place if origin else '(created coach)'}; seasons with the team "
                                "start at 0")
        if book_from.index != i:
            result.notes.append(f"{c.place} plays {book_from.place}'s playbook (a copy of its final book)")
        if dcs[i] != c.book:
            result.notes.append(f"{c.place}: defensive coordinator {dc_names[dcs[i]]} (from {club(dcs[i]).place})")
    # 5. who no club employs any more, and a head coach who called his club's defense
    if not result.errors:
        employed = {source for kind, source in final.values() if kind == "record"}
        result.fired = [current[j].name for j in range(CLUB_COUNT) if j not in employed]
        for name in result.fired:
            result.notes.append(f"{name} no longer heads a club (no club employs him in this staff)")
        for i in range(CLUB_COUNT):
            row = _identity_rows()[clubs()[i].book]
            if row["dc"] == current[i].name and final[i] != ("record", i) and dcs[i] == clubs()[i].book:
                result.notes.append(f"{place[i]}'s defense still follows {row['dc']}'s 2025 calls (he called them as "
                                    f"head coach); give {place[i]} another defensive coordinator if you like")
    return result


def plan_document(document, source_body, teams=None) -> StaffPlan:
    """``plan`` for a whole roster-edits document on a roster BEFORE the edits: its ``coaches`` list is applied to a
    copy first (the names the staff refers to)."""
    from . import nfl2k5_roster_records as rr
    teams = _teams_of(source_body, teams)
    body = bytearray(source_body)
    if (document or {}).get("coaches"):
        rr.apply_coach_names(body, teams, document["coaches"], [])
    return plan((document or {}).get("staff"), body, teams)


# ---------------------------------------------------------------------------------------------- writing
def _template_record(body, table) -> bytes:
    """The game's own created-team coach record (the first free record), the starting point of a created coach."""
    for index in range(CLUB_COUNT, table["count"]):
        at = table["offset"] + index * RECORD_SIZE
        raw = bytes(body[at:at + RECORD_SIZE])
        if raw[FLAGS] & FLAG_FREE and struct.unpack_from("<H", raw, PHOTO)[0] == NO_PHOTO \
                and struct.unpack_from("<H", raw, BODY)[0] in KNOWN_BODIES:
            return raw
    raise StaffError("this roster has no created-team coach record to start a created coach from")


def created_record(spec: Mapping, template: bytes, style_record: bytes | None) -> bytes:
    """The non-string bytes (``CONTENT_START``..end) of a created coach's record: the game's created-team coach as the
    base, the style coach's native tendency block when a style is given, then the spec's own values."""
    raw = bytearray(template)
    raw[FLAGS] = (raw[FLAGS] & ~FLAG_FREE & 0xFF) | FLAG_GENERIC_NAME
    struct.pack_into("<H", raw, BODY, spec.get("body", CREATED_BODY))
    struct.pack_into("<H", raw, PHOTO, spec.get("photo", NO_PHOTO))
    for at in _CAREER_FIELDS.values():
        struct.pack_into("<H", raw, at, 0)
    for at in WITH_TEAM_FIELDS:
        struct.pack_into("<H", raw, at, 0)
    if style_record is not None:
        raw[TENDENCY_BLOCK[0]:TENDENCY_BLOCK[1]] = style_record[TENDENCY_BLOCK[0]:TENDENCY_BLOCK[1]]
    for name, value in (spec.get("fields") or {}).items():
        struct.pack_into("<H", raw, _CAREER_FIELDS[name], value)
    for name, value in (spec.get("ratings") or {}).items():
        raw[RATINGS + _RATING_NAMES.index(name)] = value
    for name, value in (spec.get("tendencies") or {}).items():
        raw[NAMED_TENDENCIES + _TENDENCY_NAMES.index(name)] = value
    if "playcalling_run" in spec:
        raw[PLAYCALLING_RUN] = spec["playcalling_run"]
    if "height_in" in spec:
        struct.pack_into("<H", raw, HEIGHT, spec["height_in"])
    if "weight_lb" in spec:
        struct.pack_into("<H", raw, WEIGHT, spec["weight_lb"])
    return bytes(raw[CONTENT_START:])


def hire_record(raw: bytes) -> bytes:
    """A coach record's content as it starts with a new club (``CONTENT_START``..end): seasons with the team and this
    season's wins, losses and ties at zero, the free-record flag clear and the announcer flag set (generic line).
    Everything else (body, picture, ratings, tendencies, career) is his."""
    out = bytearray(raw)
    for at in WITH_TEAM_FIELDS:
        struct.pack_into("<H", out, at, 0)
    out[FLAGS] = (out[FLAGS] & ~FLAG_FREE & 0xFF) | FLAG_GENERIC_NAME
    return bytes(out[CONTENT_START:])


def coach_text_region(body) -> dict[str, int]:
    """The roster's coach text region (retail-size main ROST): {"start", "used_end", "end"}: the 175 coach strings
    sit back to back from ``start`` to ``used_end``; ``used_end``..``end`` is zeroed and referenced by nothing (free:
    on SOFTDRINK rosters the cleared 2004 biographies, about 4,278 bytes). StaffError when the region is not the game's
    one back-to-back region of singly referenced strings (a grown or foreign roster)."""
    cw = _coach_tool()
    snapshot = bytes(body)
    tables = cw.parse_roster_body(snapshot)
    references = cw.known_string_pointer_references(snapshot, tables)
    table = tables["coaches"]
    targets = []
    for index in range(table["count"]):
        record = table["offset"] + index * RECORD_SIZE
        for at in STRING_FIELDS:
            target = cw.relative_target(snapshot, record + at, f"coach {index} +0x{at:x}")
            require(target is not None, f"coach record {index} +0x{at:x} has no text")
            targets.append((target, cw.utf16z(snapshot, target, f"coach {index} +0x{at:x}")))
    targets.sort()
    start = cursor = targets[0][0]
    for target, text in targets:
        require(target == cursor and references.get(target, 0) == 1,
                "the coach names are not the game's single back-to-back text region (a grown or foreign roster)")
        cursor += (len(text) + 1) * 2
    # The region runs to the next string anything else in the roster points at (the label strings on retail): a
    # rewrite (``apply_coach_names`` clears the 2004 biographies) leaves zeroed, unreferenced bytes there, which are
    # free. Anything that is not zero stays outside.
    following = min((t for t in references if t >= cursor), default=cursor)
    end = following if following > cursor and not any(snapshot[cursor:following]) else cursor
    return {"start": start, "used_end": cursor, "end": end}


def _rewrite_strings(body: bytearray, table, wanted: dict[int, list[str]]) -> int:
    """Rewrite the coach string region (as ``nfl2k5_roster_records.apply_coach_names`` does) with ``wanted``
    (record index -> five texts); StaffError when the region is not the game's one back-to-back region or the text does
    not fit. Returns the region's byte size."""
    cw = _coach_tool()
    snapshot = bytes(body)
    region = coach_text_region(snapshot)
    start, end = region["start"], region["end"]
    slots = []
    for index in range(table["count"]):
        record = table["offset"] + index * RECORD_SIZE
        for at in STRING_FIELDS:
            target = cw.relative_target(snapshot, record + at, f"coach {index} +0x{at:x}")
            slots.append((record + at, target, cw.utf16z(snapshot, target, f"coach {index} +0x{at:x}")))
    layout = bytearray()
    pointers = []
    for position, (field_offset, _target, text) in enumerate(slots):
        index, slot = divmod(position, len(STRING_FIELDS))
        text = wanted.get(index, [None] * 5)[slot]
        text = slots[position][2] if text is None else text
        pointers.append((field_offset, start + len(layout)))
        layout += text.encode("utf-16-le") + b"\0\0"
    require(len(layout) <= end - start,
            f"the coaches' names and biographies need {len(layout)} bytes and the roster's coach text region holds "
            f"{end - start}; shorten a created coach's biography")
    body[start:end] = bytes(layout) + bytes(end - start - len(layout))
    for field_offset, target in pointers:
        struct.pack_into("<i", body, field_offset, target - field_offset + 1)
    check = bytes(body)
    for position, (field_offset, _target, text) in enumerate(slots):
        index, slot = divmod(position, len(STRING_FIELDS))
        expect = wanted.get(index, [None] * 5)[slot]
        expect = text if expect is None else expect
        got = cw.utf16z(check, cw.relative_target(check, field_offset, "coach"), "coach")
        require(got == expect, f"coach record {index} reads {got!r} after the staff rewrite")
    return end - start


def _relink_strings(body: bytearray, moves: dict[int, int]) -> None:
    """Point each destination record's five text fields at its source coach's strings (``moves``: destination record
    offset -> source record offset). Only for a permutation of the clubs' own coaches (every source is also a
    destination), so every string keeps exactly one pointer; the text region itself is not touched. This is how a
    staff is written on a roster whose arena has grown (a built disc), where the region cannot be rewritten."""
    cw = _coach_tool()
    require(sorted(moves) == sorted(moves.values()), "only a swap or rotation of the clubs' own coaches can be "
                                                     "written on this roster (no created coach, nobody leaves)")
    snapshot = bytes(body)
    targets = {}
    for dst, src in moves.items():
        targets[dst] = [cw.relative_target(snapshot, src + at, f"coach +0x{at:x}") for at in STRING_FIELDS]
        require(all(t is not None for t in targets[dst]), "a coach record has no text; the staff cannot be written")
    for dst, found in targets.items():
        for at, target in zip(STRING_FIELDS, found):
            struct.pack_into("<i", body, dst + at, target - (dst + at) + 1)


def apply_to_body(body: bytearray, teams, staff, log: list[str] | None = None) -> dict:
    """Write the head coach moves and created coaches of ``staff`` into a ROST body in place (after the ``coaches``
    list). Refuses (StaffError, nothing written) on any planning error. Returns the receipt."""
    log = log if log is not None else []
    if staff in (None, {}) or is_empty(staff):
        return dict(schema=SCHEMA, status="none", changed_bytes=0)
    teams = _teams_of(body, teams)
    result = plan(staff, body, teams)
    require(result.ok, "Coaching staff (Rosters > Coaches): " + " ".join(result.errors))
    table = _coach_table(body)
    records = _club_records(body, teams)
    before = bytes(body)
    current = coach_records(body, teams)
    template = _template_record(body, table) if any(c.created for c in result.clubs) else None
    wanted: dict[int, list[str]] = {}
    content: dict[int, bytes] = {}
    relinks: dict[int, int] = {}
    for c in result.clubs:
        if not c.moved:
            continue
        record_index, offset = records[c.club.index]
        if c.created is not None:
            spec = c.created
            style = None
            if spec.get("style"):
                at = locate_directory_coach(before, teams, spec["style"])
                if at is None and current[c.club.index].name == f"{spec['first']} {spec['last']}":
                    at = offset         # written by an earlier pass (his style coach may since have left): keep it
                style = before[at:at + RECORD_SIZE] if at is not None else None
                if style is None:
                    log.append(f"coaching staff: {spec['first']} {spec['last']}'s style coach is not on this roster; "
                               "he keeps the created-team coach's native tendencies")
            content[c.club.index] = created_record(spec, template, style)
            bio = list(spec.get("bio") or []) + [""] * BIO_LINES
            wanted[record_index] = [spec["first"], spec["last"], *bio[:BIO_LINES]]
        else:
            source = current[c.source_club.index]
            raw = before[source.record_offset:source.record_offset + RECORD_SIZE]
            content[c.club.index] = hire_record(raw)
            wanted[record_index] = [source.first, source.last, *source.bio]
            relinks[offset] = source.record_offset
    from . import nfl2k5_roster_records as rr
    if not wanted:
        size, method = 0, "none"
    elif len(body) == rr._coach_tool().ROST_BODY_SIZE:
        size, method = _rewrite_strings(body, table, wanted), "text region rewritten"
    else:
        # a grown roster (the capacity arena of a built disc): the region cannot be laid out again, but a swap or
        # rotation of the clubs' own coaches only needs their text pointers exchanged
        require(not any(c.created for c in result.clubs if c.moved),
                "a created coach can be written only on a roster before its capacity growth (build from your "
                "retail disc); this roster has grown")
        _relink_strings(body, relinks)
        size, method = 0, "text pointers exchanged"
    for index, raw in content.items():
        offset = records[index][1]
        body[offset + CONTENT_START:offset + RECORD_SIZE] = raw
    after = coach_records(body, teams)
    rows = []
    for c in result.clubs:
        got = after[c.club.index]
        require(got.name == c.coach, f"{c.club.place} reads {got.name!r} after the staff was written")
        if c.moved:
            offset = records[c.club.index][1]
            require(bytes(body[offset + CONTENT_START:offset + RECORD_SIZE]) == content[c.club.index],
                    f"{c.club.place}'s coach record did not read back")
            rows.append(dict(team=c.club.book, coach=c.coach,
                             from_team=c.source_club.book if c.source_club else None,
                             created=c.created["id"] if c.created else None, body=got.body, photo=got.photo,
                             playbook_from=c.playbook_from.book))
    for line in result.notes:
        log.append("coaching staff: " + line)
    return dict(schema=SCHEMA, status="applied", head_coaches_changed=len(rows), clubs=rows, fired=result.fired,
                defensive_coordinators={c.club.book: c.dc for c in result.clubs if c.dc != c.club.book},
                playbooks={c.club.book: c.playbook_from.book for c in result.clubs if c.playbook_from != c.club},
                string_region_bytes=size, strings=method,
                changed_bytes=sum(a != b for a, b in zip(before, bytes(body))), notes=result.notes)


# ---------------------------------------------------------------------------------------------- bring his playbook
def source_plan(source_image, roster_edits) -> StaffPlan:
    """The staff plan on the SOURCE image's roster with the document's ``coaches`` list applied in memory (where each
    coach is before this build moves anyone: the playbook a moved coach brings)."""
    from . import nfl2k5_playbook_pack as packs, nfl2k5_roster_records as rr
    document = roster_edits if isinstance(roster_edits, Mapping) else rr.read_edits(Path(roster_edits))
    with packs._outer_image().OuterImage(source_image) as archive:
        roster = rr.RosterDocument(archive.read_entry(5)[32:])
    body = bytearray(roster.body)
    if document.get("coaches"):
        rr.apply_coach_names(body, roster.teams, document["coaches"], [])
    return plan(document.get("staff"), body, roster.teams)


def playbook_copies(staff_plan: StaffPlan) -> list[tuple[Club, Club]]:
    """(host club, club whose final book it receives) for every club that does not play its own book."""
    return [(c.club, c.playbook_from) for c in staff_plan.clubs if c.playbook_from.index != c.club.index]


def apply_playbooks_to_image(target, staff_plan: StaffPlan, progress: Callable[[str], None] | None = None) -> dict:
    """Copy the final books for "bring his playbook" inside the disc image ``target`` (fixed span, one snapshot, read
    back). A profile tail on a copied book is cleared (the 2026 profiles are compiled after this step)."""
    from . import nfl2k5_playbook_pack as packs, nfl2k5_coach_ai as ai
    require(staff_plan.ok, "Coaching staff (Rosters > Coaches): " + " ".join(staff_plan.errors))
    copies = playbook_copies(staff_plan)
    if not copies:
        return dict(step="coach_staff_playbooks", status="none", copies=[])
    module = packs._outer_image()
    rows = []
    with module.OuterImage(target, writable=True) as archive:
        entries = {c.book: module.BOOK_ENTRIES[c.book] for c in clubs()}
        snapshot = {book: archive.read_entry(index) for book, index in entries.items()}
        prepared = []
        for host, donor in copies:
            before, source = snapshot[host.book], snapshot[donor.book]
            require(len(before) == len(source) and before[:32] == source[:32],
                    f"{donor.place}'s playbook cannot be copied over {host.place}'s (the resources differ in shape)")
            after = ai.strip_profile(source)
            prepared.append((host, donor, entries[host.book], before, after))
        for host, donor, index, before, after in prepared:
            if progress:
                progress(f"{host.place} plays {donor.place}'s playbook")
            offset = archive.entries[index].virtual_offset
            if before != after:
                archive.write(offset, after)
            require(archive.read_entry(index) == after, f"{host.place}'s playbook did not read back")
            rows.append(dict(team=host.book, book_from=donor.book, entry=index,
                             before_sha256=hashlib.sha256(before).hexdigest(),
                             after_sha256=hashlib.sha256(after).hexdigest(),
                             changed_bytes=sum(a != b for a, b in zip(before, after))))
    return dict(step="coach_staff_playbooks", status="applied", copies=rows, resource_growth=0, readback_verified=True)


# ---------------------------------------------------------------------------------------------- 2026 profile bindings
@dataclass(frozen=True)
class Binding:
    club: Club
    tendency: str                     # directory id whose data/vip/coaches/<id>.json is compiled
    profile_name: str                 # twelve UTF-16 units at most
    identity: int
    legacy_identity: int
    portrait: int                     # the photo the club's coach record carries (or the directory picture)
    alternate: int                    # 0 or the alias picture the record may carry instead
    defense: str                      # book code of the defensive coordinator's identity row
    coach: str                        # the head coach's full name (receipts)

    def table_row(self) -> dict:
        return dict(identity=self.identity, legacy_identity=self.legacy_identity, book_index=self.club.index,
                    asset=self.club.asset, portrait=self.portrait, alternate_portrait=self.alternate,
                    name=self.profile_name)


def created_profile_name(club_value, spec) -> str:
    host = club(club_value)
    name = f"{host.team} {spec['last']}"
    return name[:PROFILE_NAME_UNITS] if len(name.encode("utf-16le")) <= 2 * PROFILE_NAME_UNITS else \
        name.encode("utf-16le")[:2 * PROFILE_NAME_UNITS].decode("utf-16le", "ignore")


def profile_bindings(body, teams=None, staff=None) -> tuple[list[Binding | None], list[str]]:
    """Per club on the FINAL roster (after the staff was written): the 2026 profile binding, or None; and the plain
    reasons for every None. The staff document supplies created coaches' styles and the defensive coordinators."""
    from . import nfl2k5_vip as vip
    teams = _teams_of(body, teams)
    value = normalize(staff)
    created = {c["id"]: c for c in value["created_coaches"]}
    by_team = {club(e["team"]).index: e for e in value["head_coaches"]}
    dcs = {club(e["team"]).index: e["dc"] for e in value["defensive_coordinators"]}
    team_rows = {t.index: t for t in teams if t.index < CLUB_COUNT}
    out: list[Binding | None] = []
    reasons: list[str] = []
    try:
        coaches = coach_records(body, teams)
    except (StaffError, ValueError) as exc:
        return [None] * CLUB_COUNT, [f"the roster's coaches cannot be read: {exc}"]
    for i in range(CLUB_COUNT):
        c = clubs()[i]
        team = team_rows.get(i)
        coach = coaches[i]
        defense = dcs.get(i, c.book)
        if team is None or (team.kind, team.asset_id) != (0, c.asset):
            out.append(None)
            reasons.append(f"{c.place}: the roster's club {i} is not the 2026 {c.nickname}")
            continue
        entry = by_team.get(i)
        spec = created.get(entry["created"]) if entry and "created" in entry else None
        if spec is not None and coach.name == f"{spec['first']} {spec['last']}":
            if not spec.get("style"):
                out.append(None)
                reasons.append(f"{c.place}: {coach.name} is a created coach without a play-calling style")
                continue
            name = created_profile_name(c, spec)
            out.append(Binding(c, spec["style"], name, vip.coach_identity(CREATED_IDENTITY_TEAM, name),
                               vip.coach_identity(CREATED_IDENTITY_TEAM, name + "\0legacy"), coach.photo, 0, defense,
                               coach.name))
            continue
        if coach.directory_id is None:
            out.append(None)
            reasons.append(f"{c.place}: {coach.name} is not one of the 32 2026 head coaches (name and picture)")
            continue
        row = next(r for r in _directory() if r["id"] == coach.directory_id)
        out.append(Binding(c, row["id"], row["profile_name"], row["identity"], row["legacy_identity"],
                           row["portrait"], row["alternate"] or 0, defense, coach.name))
    return out, reasons


# ---------------------------------------------------------------------------------------------- document helpers (UI)
def final_assignment(staff, roster_body, teams=None) -> dict[int, dict]:
    """club index -> {"coach": name} or {"created": id}: the head coach every club has under ``staff`` (clubs the
    staff does not name keep the roster's coach). ``roster_body``: the roster after the ``coaches`` list."""
    value = normalize(staff)
    current = coach_records(roster_body, teams)
    out = {i: {"coach": current[i].name} for i in range(CLUB_COUNT)}
    for e in value["head_coaches"]:
        out[club(e["team"]).index] = {k: e[k] for k in ("coach", "created") if k in e}
    return out


def from_assignment(staff, assignment: Mapping[int, Mapping], roster_body, teams=None, *,
                    playbooks: Mapping[int, str] | None = None) -> dict:
    """The smallest staff document that gives ``assignment`` (``final_assignment``'s shape); the created coaches and
    defensive coordinators of ``staff`` are kept. ``playbooks``: club index -> "coach" for clubs that bring his book."""
    value = normalize(staff)
    current = coach_records(roster_body, teams)
    entries = []
    for i in range(CLUB_COUNT):
        who = dict(assignment[i])
        if "coach" in who and who["coach"].casefold() == current[i].name.casefold():
            continue
        entry = {"team": clubs()[i].book, **who}
        if (playbooks or {}).get(i) == "coach":
            entry["playbook"] = "coach"
        entries.append(entry)
    value["head_coaches"] = entries
    return normalize(value)


def _playbooks(staff) -> dict[int, str]:
    return {club(e["team"]).index: "coach" for e in normalize(staff)["head_coaches"] if e.get("playbook") == "coach"}


def move_head_coach(staff, coach_name: str, to, roster_body, teams=None, *, vacancy: str = "swap") -> dict:
    """Make ``coach_name`` (a coach on the roster) the head coach of ``to``. ``vacancy="swap"``: the club he leaves
    gets ``to``'s present coach; ``"error"``: the club he leaves is left for ``plan`` to report (choose its coach)."""
    require(vacancy in ("swap", "error"), "vacancy must be 'swap' or 'error'")
    host = club(to)
    assignment = final_assignment(staff, roster_body, teams)
    previous = assignment[host.index]
    created = {f"{c['first']} {c['last']}".casefold(): c["id"] for c in normalize(staff)["created_coaches"]}
    occupant = ({"created": created[coach_name.strip().casefold()]} if coach_name.strip().casefold() in created
                else {"coach": coach_name.strip()})
    leaving = [i for i, who in assignment.items() if who == occupant and i != host.index]
    assignment[host.index] = occupant
    playbooks = {i: p for i, p in _playbooks(staff).items() if i != host.index}
    if leaving and vacancy == "swap":
        assignment[leaving[0]] = previous
        playbooks.pop(leaving[0], None)
    return from_assignment(staff, assignment, roster_body, teams, playbooks=playbooks)


def swap_head_coaches(staff, a, b, roster_body, teams=None) -> dict:
    first, second = club(a), club(b)
    assignment = final_assignment(staff, roster_body, teams)
    assignment[first.index], assignment[second.index] = assignment[second.index], assignment[first.index]
    playbooks = {i: p for i, p in _playbooks(staff).items() if i not in (first.index, second.index)}
    return from_assignment(staff, assignment, roster_body, teams, playbooks=playbooks)


def hire_created_coach(staff, to, spec: Mapping, roster_body=None, teams=None) -> dict:
    """Make the created coach ``spec`` the head coach of ``to`` (the present coach leaves the league unless another
    club takes him)."""
    host = club(to)
    spec = _normalize_created(spec)
    value = normalize(staff)
    value["created_coaches"] = [c for c in value["created_coaches"] if c["id"] != spec["id"]] + [spec]
    value["head_coaches"] = [e for e in value["head_coaches"] if club(e["team"]).index != host.index
                             and e.get("created") != spec["id"]] + [{"team": host.book, "created": spec["id"]}]
    return normalize(value)


def fire_head_coach(staff, at, replacement, roster_body, teams=None) -> dict:
    """Replace ``at``'s head coach with ``replacement``: a created coach spec, or the name of a coach on the roster
    (if another club employs him, that club needs a new coach: ``plan`` says so)."""
    if isinstance(replacement, Mapping):
        return hire_created_coach(staff, at, replacement)
    return move_head_coach(staff, str(replacement), at, roster_body, teams, vacancy="error")


def set_defensive_coordinator(staff, at, dc, *, swap: bool = True) -> dict:
    """Give ``at`` the defensive coordinator ``dc`` (book code of his 2026 club, or his name). ``swap``: the club he
    leaves gets ``at``'s present coordinator."""
    value = normalize(staff)
    host, person = club(at), coordinator(dc)["id"]
    current = {i: clubs()[i].book for i in range(CLUB_COUNT)}
    for e in value["defensive_coordinators"]:
        current[club(e["team"]).index] = e["dc"]
    previous = current[host.index]
    leaving = [i for i, d in current.items() if d == person and i != host.index]
    current[host.index] = person
    if swap and leaving:
        current[leaving[0]] = previous
    value["defensive_coordinators"] = [{"team": clubs()[i].book, "dc": d} for i, d in sorted(current.items())
                                       if d != clubs()[i].book]
    return normalize(value)


def set_playbook(staff, at, playbook: str) -> dict:
    """``"coach"``: ``at`` plays the final book of the club its (moved or created-with-style) coach comes from;
    ``"club"``: its own book."""
    value = normalize(staff)
    host = club(at)
    require(playbook in ("club", "coach"), "playbook must be 'club' or 'coach'")
    entry = next((e for e in value["head_coaches"] if club(e["team"]).index == host.index), None)
    require(entry is not None, f"{host.place} keeps its own head coach, so it keeps its own playbook")
    entry.pop("playbook", None)
    if playbook == "coach":
        entry["playbook"] = "coach"
    return normalize(value)


def reset(_staff=None) -> dict:
    """Every club keeps the disc's own head coach, playbook and defensive coordinator."""
    return empty()


def summary(staff_plan: StaffPlan) -> str:
    """One plain paragraph for logs and the Build summary."""
    if not staff_plan.ok:
        return "Coaching staff not written: " + " ".join(staff_plan.errors)
    moved = staff_plan.changes
    parts = [f"{len(moved)} head coach change{'s' if len(moved) != 1 else ''}"]
    dcs = [c for c in staff_plan.clubs if c.dc != c.club.book]
    if dcs:
        parts.append(f"{len(dcs)} defensive coordinator change{'s' if len(dcs) != 1 else ''}")
    books = [c for c in staff_plan.clubs if c.playbook_from != c.club]
    if books:
        parts.append(f"{len(books)} club{'s' if len(books) != 1 else ''} with the new coach's playbook")
    return "Coaching staff: " + ", ".join(parts) + "."


def main(argv=None) -> int:
    """Read-only CLI: the 32 head coaches of a disc, or the staff a roster-edits document gives on it."""
    import argparse
    parser = argparse.ArgumentParser(description="Coaching staff (read only): the head coaches of a disc image, or "
                                                 "the plan of a roster-edits document's staff on it")
    parser.add_argument("operation", choices=("roster", "plan"))
    parser.add_argument("image", type=Path)
    parser.add_argument("roster_edits", type=Path, nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.operation == "roster":
            print(json.dumps([c.as_dict() for c in read_image(args.image)], indent=1))
            return 0
        require(args.roster_edits is not None, "plan needs a roster-edits document")
        result = source_plan(args.image, args.roster_edits)
        print(json.dumps(result.as_dict(), indent=1))
        print(summary(result))
        return 0 if result.ok else 2
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Coaching staff refused: {exc}\n")


__all__ = ["SCHEMA", "StaffError", "Club", "CLUB_COUNT", "BOOK_CODES", "KNOWN_BODIES", "NO_PHOTO", "CREATED_BODY",
           "RECORD_SIZE", "STRING_FIELDS", "CONTENT_START", "WITH_TEAM_FIELDS", "FLAG_FREE", "FLAG_GENERIC_NAME",
           "clubs", "club", "head_coach_directory", "directory_coach", "coordinator_directory", "coordinator",
           "empty", "normalize", "is_empty", "HeadCoach", "coach_records", "read_roster", "read_image",
           "locate_directory_coach", "coach_text_region", "ClubPlan", "StaffPlan", "plan", "plan_document", "created_record", "hire_record",
           "apply_to_body", "source_plan", "playbook_copies", "apply_playbooks_to_image", "Binding",
           "created_profile_name", "profile_bindings", "final_assignment", "from_assignment", "move_head_coach", "swap_head_coaches",
           "hire_created_coach", "fire_head_coach", "set_defensive_coordinator", "set_playbook", "reset", "summary"]


if __name__ == "__main__":
    raise SystemExit(main())
