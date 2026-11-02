"""The coaching staff as the Rosters > Coaches page sees it: who coaches each club now, and the staff changes to build.

The page edits one small document, the ``staff`` section of a roster-edits file (schema ``nfl2k5_coach_staff/v1``, the
format ``nfl2k5_coach_staff`` writes into a disc at build time; b780 job c2-staff).  This module is everything the page
needs that is not drawing: the 32 clubs, each club's head coach read from the loaded roster, the 32 defensive
coordinators of the Studio's 2026 data, and plain functions that turn the document into a new document for a swap, a
move, a firing, a new coach, a coordinator change or a playbook choice.  Nothing here writes a disc or a save.

The document, one entry per club that changes (clubs not listed keep their coach)::

    {"schema": "nfl2k5_coach_staff/v1",
     "head_coaches": [{"team": "OAK", "coach": "Andy Reid", "playbook": "club"},
                      {"team": "NYG", "created": "pat-shurmur", "playbook": "club"}],
     "defensive_coordinators": [{"team": "DAL", "dc": "PHI"}],
     "created_coaches": [{"id": "pat-shurmur", "first": "Pat", "last": "Shurmur", "bio": ["", "", ""], "body": 50,
                          "photo": 8999, "style": "SF", "ratings": {"overall": 70}}]}

``team`` is the club's book code (SF CHI ... ARZ SD KC ... OAK STL WAS), ``coach`` a head coach's full name as the roster
holds it, ``dc`` the home club's book code of a 2026 coordinator.  Every function here returns a new document and keeps
the invariants the build checks: every club has exactly one head coach and one coordinator, nobody works two seats, and
a coach who leaves a club is replaced there in the same move (a swap), or let go when a new person takes his seat.

When ``mod_editor.core.nfl2k5_coach_staff`` exists (it is the build-time engine), ``engine_plan`` asks it to judge the
document against the roster too and passes its words on; this module never depends on it to work.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import nfl2k5_franchise_save as fs
from . import nfl2k5_roster_records as rr

SCHEMA = "nfl2k5_coach_staff/v1"
ROOT = Path(__file__).resolve().parents[2]
DEFENSE_FILE = ROOT / "data" / "vip" / "defense_identity_2026.json"
HEAD_COACH_FILE = ROOT / "data" / "vip" / "coach_sources_2026.json"
FACES_DIR = ROOT / "data" / "nfl2k5_modern_coaches"

#: The game's coach sideline models a created coach can wear (c2-staff KNOWN_BODIES); 50 is the created-team coach.
COACH_BODIES: tuple[int, ...] = tuple(range(0, 31)) + (33, 36, 37, 50, 51)
DEFAULT_BODY = 50
NO_PHOTO = fs.COACH_NO_PHOTO
NAME_LIMIT = fs.COACH_NAME_MAX
BIO_LIMIT = fs.COACH_BIO_MAX
PLAYBOOKS = ("club", "coach")


class StaffUiError(ValueError):
    """A staff change the page cannot make; the message is plain words for the status line."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StaffUiError(message)


# --------------------------------------------------------------------------------------------- the 32 clubs
@dataclass(frozen=True)
class Club:
    index: int          # team order in the roster: alphabetical by nickname, the game's own
    book: str           # the code the staff document uses (the playbook label table's key)
    code: str           # the 2026 abbreviation people read
    nickname: str


CLUBS: tuple[Club, ...] = tuple(Club(*row) for row in (
    (0, "SF", "SF", "49ers"), (1, "CHI", "CHI", "Bears"), (2, "CIN", "CIN", "Bengals"), (3, "BUF", "BUF", "Bills"),
    (4, "DEN", "DEN", "Broncos"), (5, "CLE", "CLE", "Browns"), (6, "TB", "TB", "Buccaneers"),
    (7, "ARZ", "ARI", "Cardinals"), (8, "SD", "LAC", "Chargers"), (9, "KC", "KC", "Chiefs"), (10, "IND", "IND", "Colts"),
    (11, "DAL", "DAL", "Cowboys"), (12, "MIA", "MIA", "Dolphins"), (13, "PHI", "PHI", "Eagles"),
    (14, "ATL", "ATL", "Falcons"), (15, "NYG", "NYG", "Giants"), (16, "JAX", "JAX", "Jaguars"), (17, "NYJ", "NYJ", "Jets"),
    (18, "DET", "DET", "Lions"), (19, "GB", "GB", "Packers"), (20, "CAR", "CAR", "Panthers"),
    (21, "NE", "NE", "Patriots"), (22, "OAK", "LV", "Raiders"), (23, "STL", "LAR", "Rams"), (24, "BAL", "BAL", "Ravens"),
    (25, "WAS", "WAS", "Commanders"), (26, "NO", "NO", "Saints"), (27, "SEA", "SEA", "Seahawks"),
    (28, "PIT", "PIT", "Steelers"), (29, "HOU", "HOU", "Texans"), (30, "TEN", "TEN", "Titans"),
    (31, "MIN", "MIN", "Vikings")))
_BY_KEY: dict[str, Club] = {}
for _club in CLUBS:
    for _key in (_club.book, _club.code, _club.nickname):
        _BY_KEY[_key.casefold()] = _club
_BY_KEY["redskins"] = CLUBS[25]


def club(value: Any) -> Club:
    """A club by index, book code, 2026 code or nickname."""

    if isinstance(value, Club):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < len(CLUBS):
        return CLUBS[value]
    found = _BY_KEY.get(str(value).strip().casefold())
    _require(found is not None, f"{value!r} is not one of the 32 clubs")
    assert found is not None
    return found


# --------------------------------------------------------------------------------------------- the roster, read
@dataclass(frozen=True)
class HeadCoachRow:
    """One club's head coach as the loaded roster holds him."""

    club: Club
    display: str                      # the roster's name for the club ("Kansas City Chiefs")
    record: int | None                # index in the coach table
    first: str = ""
    last: str = ""
    bio: tuple[str, str, str] = ("", "", "")
    photo: int = 0
    body: int = 0                     # the sideline model number (the low half of the record's +0x18)
    flags: int = 0
    career: Mapping[str, int] = field(default_factory=dict)
    ratings: Mapping[str, int] = field(default_factory=dict)
    tendencies: Mapping[str, int] = field(default_factory=dict)
    run_share: int = 0                # the share of plays he calls as runs (record +0x59)

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()


def read_head_coaches(document: Any) -> list[HeadCoachRow]:
    """The 32 clubs' head coaches out of a loaded ``RosterDocument`` (a disc roster or a save's arena)."""

    body = document.body
    ob = document.obj_base
    count = document.u32(ob + rr.OBJ_OFF + 0x30)
    table = document.rel(ob + rr.OBJ_OFF + 0x34)
    rows: list[HeadCoachRow] = []
    for entry in CLUBS:
        if entry.index >= len(document.teams):
            break
        team = document.teams[entry.index]
        offset = team.coach_offset
        if offset is None or table is None:
            rows.append(HeadCoachRow(entry, team.display, None))
            continue
        record, remainder = divmod(offset - table, fs.COACH_SIZE)
        if remainder or not 0 <= record < count:
            rows.append(HeadCoachRow(entry, team.display, None))
            continue

        def text(field_offset: int, _offset: int = offset) -> str:
            target = document.rel(_offset + field_offset)
            return rr.read_utf16z(body, target)[0] if target is not None else ""

        career = {name: struct.unpack_from(fmt, body, offset + rel)[0]
                  for name, (rel, fmt) in fs.COACH_FIELDS.items() if name not in ("body", "photo", "playcalling_run")}
        ratings = {name: body[offset + fs.COACH_RATINGS_OFFSET + k] for k, name in enumerate(fs.COACH_RATINGS)}
        tendencies = {name: body[offset + fs.COACH_TENDENCIES_OFFSET + k] for k, name in enumerate(fs.COACH_TENDENCIES)}
        rows.append(HeadCoachRow(
            entry, team.display, record, text(0x00), text(0x04), (text(0x08), text(0x0C), text(0x10)),
            struct.unpack_from("<H", body, offset + fs.COACH_FIELDS["photo"][0])[0],
            struct.unpack_from("<H", body, offset + fs.COACH_FIELDS["body"][0])[0],
            body[offset + fs.COACH_FLAGS], career, ratings, tendencies,
            body[offset + fs.COACH_FIELDS["playcalling_run"][0]]))
    return rows


# --------------------------------------------------------------------------------------------- the Studio's 2026 data
@dataclass(frozen=True)
class Coordinator:
    """A 2026 defensive coordinator, keyed by the book code of the club he works for in the Studio's data."""

    book: str
    name: str
    family: str = ""
    front: str = ""
    package: tuple[str, ...] = ()
    source: str = ""


_DATA_CACHE: dict[str, Any] = {}


def _json(path: Path) -> Any:
    key = str(path)
    if key not in _DATA_CACHE:
        _DATA_CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
    return _DATA_CACHE[key]


def coordinators() -> dict[str, Coordinator]:
    """The 32 defensive coordinators by home club book code (``data/vip/defense_identity_2026.json``)."""

    try:
        teams = _json(DEFENSE_FILE)["teams"]
    except (OSError, ValueError, KeyError):
        return {}
    out: dict[str, Coordinator] = {}
    for entry in CLUBS:
        row = teams.get(entry.book)
        if isinstance(row, Mapping) and row.get("dc"):
            out[entry.book] = Coordinator(entry.book, str(row["dc"]), str(row.get("family", "")), str(row.get("front", "")),
                                          tuple(str(p) for p in row.get("package", ())), str(row.get("source", "")))
    return out


def head_coach_homes() -> dict[str, str]:
    """2026 head coach name -> his 2026 club code, for pictures and "from" notes (``coach_sources_2026.json``)."""

    try:
        rows = _json(HEAD_COACH_FILE)
    except (OSError, ValueError):
        return {}
    return {str(row["coach"]): str(row["team"]) for row in rows if isinstance(row, Mapping) and row.get("coach")}


def face_path(code: str) -> Path | None:
    """The painted face texture of a 2026 head coach (the Studio ships one per club), or None."""

    path = FACES_DIR / code / "head.png"
    return path if path.is_file() else None


# --------------------------------------------------------------------------------------------- the document
def empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "head_coaches": [], "defensive_coordinators": [], "created_coaches": []}


def is_empty(staff: Mapping[str, Any] | None) -> bool:
    return not staff or not any(staff.get(key) for key in ("head_coaches", "defensive_coordinators", "created_coaches"))


Occupant = tuple[str, str]          # ("coach", full name) or ("created", id)


def _entries(staff: Mapping[str, Any], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in staff.get(key) or []:
        if isinstance(entry, Mapping) and entry.get("team") is not None:
            out[club(entry["team"]).book] = dict(entry)
    return out


def created_coaches(staff: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(spec["id"]): dict(spec) for spec in staff.get("created_coaches") or [] if isinstance(spec, Mapping) and spec.get("id")}


def head_seats(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any]) -> dict[str, Occupant]:
    """Who holds each club's head coach seat once the document is applied (book code -> occupant)."""

    seats: dict[str, Occupant] = {row.club.book: ("coach", row.name) for row in rows}
    for book, entry in _entries(staff, "head_coaches").items():
        if entry.get("created"):
            seats[book] = ("created", str(entry["created"]))
        elif entry.get("coach"):
            seats[book] = ("coach", str(entry["coach"]))
    return seats


def dc_seats(staff: Mapping[str, Any]) -> dict[str, str]:
    """Who coordinates each club's defense once the document is applied (club book code -> home club book code)."""

    seats = {book: book for book in coordinators()}
    for book, entry in _entries(staff, "defensive_coordinators").items():
        if entry.get("dc") and book in seats:
            home = str(entry["dc"])
            seats[book] = club(home).book if home.casefold() in _BY_KEY else home
    return seats


def occupant_name(occupant: Occupant, staff: Mapping[str, Any]) -> str:
    kind, value = occupant
    if kind == "created":
        spec = created_coaches(staff).get(value, {})
        return f"{spec.get('first', '')} {spec.get('last', '')}".strip() or value
    return value


def _tidy(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], seats: Mapping[str, Occupant],
          dcs: Mapping[str, str], playbooks: Mapping[str, str], created: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """A new document from the final seats: only clubs that differ from the roster appear, in club order."""

    base = {row.club.book: ("coach", row.name) for row in rows}
    heads, used = [], set()
    for entry in CLUBS:
        occupant = seats.get(entry.book, base.get(entry.book))
        if occupant is None or occupant == base.get(entry.book):
            continue
        kind, value = occupant
        item: dict[str, Any] = {"team": entry.book}
        item["created" if kind == "created" else "coach"] = value
        if playbooks.get(entry.book) == "coach":
            item["playbook"] = "coach"
        heads.append(item)
        if kind == "created":
            used.add(value)
    dc_rows = [{"team": entry.book, "dc": dcs[entry.book]} for entry in CLUBS
               if entry.book in dcs and dcs[entry.book] != entry.book]
    out = {"schema": SCHEMA, "head_coaches": heads, "defensive_coordinators": dc_rows,
           "created_coaches": [dict(created[key]) for key in created if key in used]}
    return out


def _state(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any]):
    playbooks = {book: str(entry.get("playbook", "club")) for book, entry in _entries(staff, "head_coaches").items()}
    return head_seats(rows, staff), dc_seats(staff), playbooks, created_coaches(staff)


def _name_once(rows: Sequence[HeadCoachRow], name: str) -> None:
    """The plan names coaches by name, so two head coaches with one name cannot be told apart (retail's two Schottenheimers)."""

    clubs_with = [row.club.code for row in rows if row.name.casefold() == name.casefold()]
    _require(len(clubs_with) <= 1, f"{name} is the head coach of more than one club on this roster ({', '.join(clubs_with)}), "
                                   "and a staff plan tells coaches apart by name")


def swap_head_coaches(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], club_a: Any, club_b: Any) -> dict[str, Any]:
    """Two clubs exchange head coaches; each arriving coach plays from his new club's playbook until told otherwise."""

    a, b = club(club_a).book, club(club_b).book
    _require(a != b, "pick two different clubs to swap")
    seats, dcs, playbooks, created = _state(rows, staff)
    for occupant in (seats[a], seats[b]):
        if occupant[0] == "coach":
            _name_once(rows, occupant[1])
    seats[a], seats[b] = seats[b], seats[a]
    playbooks.pop(a, None)
    playbooks.pop(b, None)
    return _tidy(rows, staff, seats, dcs, playbooks, created)


def move_head_coach(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], coach_name: str, to_club: Any) -> dict[str, Any]:
    """A coach takes a club's seat: when he has a club the two clubs swap, when he was let go he is hired and the
    coach he replaces is let go."""

    target = club(to_club).book
    seats, _dcs, _playbooks, _created = _state(rows, staff)
    _name_once(rows, coach_name)
    holder = next((book for book, (kind, value) in seats.items() if kind == "coach" and value == coach_name), None)
    if holder is None:
        return hire_head_coach(rows, staff, target, ("coach", coach_name))
    _require(holder != target, f"{coach_name} already coaches {club(target).code}")
    return swap_head_coaches(rows, staff, holder, target)


def hire_head_coach(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], club_: Any, occupant: Occupant) -> dict[str, Any]:
    """A coach nobody employs (let go earlier in this plan) takes a club's seat; the coach he replaces is let go."""

    book = club(club_).book
    seats, dcs, playbooks, created = _state(rows, staff)
    kind, value = occupant
    if kind == "coach":
        _require(any(row.name == value for row in rows), f"{value} is not a head coach on this roster")
        _name_once(rows, value)
    else:
        _require(value in created, f"there is no new coach {value!r} in this plan")
    _require(occupant not in seats.values(), f"{occupant_name(occupant, staff)} already coaches a club; swap the two clubs instead")
    seats[book] = occupant
    playbooks.pop(book, None)
    return _tidy(rows, staff, seats, dcs, playbooks, created)


def let_go(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any]) -> list[str]:
    """Head coaches on the roster whom nobody employs once the document is applied."""

    seated = {value for kind, value in head_seats(rows, staff).values() if kind == "coach"}
    return [row.name for row in rows if row.name and row.name not in seated]


# ---- new coaches
def _text(value: Any, limit: int, label: str, *, required: bool) -> str:
    text = " ".join(str(value or "").split())
    _require(bool(text) or not required, f"type the coach's {label}")
    _require(len(text) <= limit, f"the coach's {label} is longer than {limit} characters")
    _require(text.isprintable(), f"the coach's {label} has a character the game cannot show")
    return text


def coach_id(first: str, last: str, taken: Iterable[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{first} {last}".lower()).strip("-") or "coach"
    taken = set(taken)
    candidate, number = slug, 1
    while candidate in taken:
        number += 1
        candidate = f"{slug}-{number}"
    return candidate


def new_coach_spec(first: str, last: str, *, bio: Sequence[str] = (), body: int = DEFAULT_BODY, style: str | None = None,
                   overall: int | None = None, playcalling_run: int | None = None) -> dict[str, Any]:
    """A created coach in the document's own shape, checked in plain words (the id is set when he is hired)."""

    first = _text(first, NAME_LIMIT, "first name", required=True)
    last = _text(last, NAME_LIMIT, "last name", required=True)
    lines = [_text(line, BIO_LIMIT, "biography line", required=False) for line in list(bio)[:3]]
    lines += [""] * (3 - len(lines))
    _require(body in COACH_BODIES, f"coach model {body!r} is not one the game has")
    spec: dict[str, Any] = {"first": first, "last": last, "bio": lines, "body": int(body), "photo": NO_PHOTO}
    if style:
        spec["style"] = club(style).code
    if overall is not None:
        _require(type(overall) is int and 0 <= overall <= 99, "the overall rating is a number from 0 to 99")
        spec["ratings"] = {"overall": overall}
    if playcalling_run is not None:
        _require(type(playcalling_run) is int and 0 <= playcalling_run <= 100, "the run share is a number from 0 to 100")
        spec["playcalling_run"] = playcalling_run
    return spec


def hire_created_coach(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], club_: Any,
                       spec: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """A new person takes a club's seat; the coach he replaces is let go.  Returns the document and the new id."""

    book = club(club_).book
    seats, dcs, playbooks, created = _state(rows, staff)
    checked = new_coach_spec(spec.get("first", ""), spec.get("last", ""), bio=spec.get("bio", ()),
                             body=int(spec.get("body", DEFAULT_BODY)), style=spec.get("style"),
                             overall=(spec.get("ratings") or {}).get("overall"), playcalling_run=spec.get("playcalling_run"))
    full = f"{checked['first']} {checked['last']}".casefold()
    taken = {row.name.casefold() for row in rows} | {f"{c.get('first', '')} {c.get('last', '')}".casefold() for c in created.values()}
    _require(full not in taken, f"{checked['first']} {checked['last']} is already a head coach's name in this plan; "
                                "give the new coach another name (a staff plan tells coaches apart by name)")
    new_id = coach_id(checked["first"], checked["last"], created)
    created = dict(created)
    created[new_id] = {"id": new_id, **checked}
    seats[book] = ("created", new_id)
    playbooks.pop(book, None)
    return _tidy(rows, staff, seats, dcs, playbooks, created), new_id


# ---- coordinators and playbooks
def swap_coordinators(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], club_a: Any, club_b: Any) -> dict[str, Any]:
    a, b = club(club_a).book, club(club_b).book
    _require(a != b, "pick two different clubs to swap")
    seats, dcs, playbooks, created = _state(rows, staff)
    dcs[a], dcs[b] = dcs[b], dcs[a]
    return _tidy(rows, staff, seats, dcs, playbooks, created)


def set_coordinator(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], club_: Any, dc_home: Any) -> dict[str, Any]:
    """A club gets another club's coordinator; that club gets this club's coordinator (a coordinator works for one club)."""

    book, home = club(club_).book, club(dc_home).book
    dcs = dc_seats(staff)
    _require(home in dcs, f"{club(dc_home).code} has no coordinator in the Studio's 2026 data")
    holder = next(b for b, h in dcs.items() if h == home)
    _require(holder != book, "that coordinator already runs this defense")
    return swap_coordinators(rows, staff, book, holder)


def set_playbook(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any], club_: Any, which: str) -> dict[str, Any]:
    """Whether the coach who arrives at a club brings his old club's playbook (``"coach"``) or the club keeps its own."""

    _require(which in PLAYBOOKS, f"playbook must be one of {PLAYBOOKS}")
    book = club(club_).book
    seats, dcs, playbooks, created = _state(rows, staff)
    base = {row.club.book: ("coach", row.name) for row in rows}
    _require(seats.get(book) != base.get(book), "only a coach who arrives at a club can bring his playbook")
    seat = seats[book]
    _require(which == "club" or seat[0] != "created" or created.get(seat[1], {}).get("style"),
             "a new coach brings a playbook only when he calls plays like another coach (the playbook of that coach's club)")
    playbooks[book] = which
    return _tidy(rows, staff, seats, dcs, playbooks, created)


def reset(staff: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return empty()


# --------------------------------------------------------------------------------------------- words
def describe(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any]) -> list[str]:
    """The changes in plain words, one line each (head coaches, then coordinators, then who is let go)."""

    lines: list[str] = []
    base = {row.club.book: row for row in rows}
    homes = {row.name: row.club for row in rows}
    seats = head_seats(rows, staff)
    entries = _entries(staff, "head_coaches")
    for entry in CLUBS:
        occupant = seats.get(entry.book)
        was = base.get(entry.book)
        if occupant is None or was is None or occupant == ("coach", was.name):
            continue
        kind, value = occupant
        if kind == "created":
            origin = " (new coach)"
        else:
            home = homes.get(value)
            origin = f" (from {home.code})" if home is not None else ""
        brings = ", brings his playbook" if entries.get(entry.book, {}).get("playbook") == "coach" else ""
        lines.append(f"{entry.code} head coach: {was.name or 'nobody'} → {occupant_name(occupant, staff)}{origin}{brings}")
    people = coordinators()
    for entry in CLUBS:
        mine = dc_seats(staff).get(entry.book)
        if mine is None or mine == entry.book or entry.book not in people:
            continue
        lines.append(f"{entry.code} defensive coordinator: {people[entry.book].name} → {people[mine].name} (from {club(mine).code})")
    for name in let_go(rows, staff):
        lines.append(f"{name} is let go and leaves the roster")
    return lines


def problems(rows: Sequence[HeadCoachRow], staff: Mapping[str, Any]) -> list[str]:
    """What is wrong with a staff document against this roster, in plain words (an empty list is a plan that builds)."""

    if not isinstance(staff, Mapping):
        return ["the staff file is not a staff document"]
    out: list[str] = []
    if staff.get("schema") != SCHEMA:
        out.append(f"the staff file says {staff.get('schema')!r}; this Studio writes {SCHEMA!r}")
    names = {row.name for row in rows}
    created = created_coaches(staff)
    clubs_seen: dict[str, int] = {}
    people_seen: dict[Occupant, str] = {}
    entries: dict[str, dict[str, Any]] = {}
    for item in staff.get("head_coaches") or []:
        try:
            book = club(item.get("team")).book
        except (StaffUiError, AttributeError):
            out.append(f"a head coach entry names a club that does not exist: {item!r}")
            continue
        label = club(book).code
        clubs_seen[book] = clubs_seen.get(book, 0) + 1
        if clubs_seen[book] == 2:
            out.append(f"{label} has two head coach entries")
        entries[book] = item
        if item.get("created"):
            occupant: Occupant = ("created", str(item["created"]))
            if occupant[1] not in created:
                out.append(f"{label} hires a new coach {occupant[1]!r} that the plan does not define")
        elif item.get("coach"):
            occupant = ("coach", str(item["coach"]))
            if occupant[1] not in names:
                out.append(f"{label} hires {occupant[1]}, who is not a head coach on this roster")
        else:
            out.append(f"{label} has a head coach entry with nobody in it")
            continue
        if occupant in people_seen:
            out.append(f"{occupant_name(occupant, staff)} would coach both {club(people_seen[occupant]).code} and {label}")
        people_seen[occupant] = book
        if item.get("playbook", "club") not in PLAYBOOKS:
            out.append(f"{label}: the playbook choice must be club or coach")
        elif item.get("playbook") == "coach" and occupant[0] == "created" and not created.get(occupant[1], {}).get("style"):
            out.append(f"{label}: a new coach brings a playbook only when he calls plays like another coach")
    arrived = {value: book for (kind, value), book in people_seen.items() if kind == "coach"}
    for row in rows:
        if row.club.book not in entries and arrived.get(row.name, row.club.book) != row.club.book:
            out.append(f"{row.club.code} lost {row.name} and nobody replaces him")
    people = coordinators()
    held: dict[str, int] = {}
    for item in staff.get("defensive_coordinators") or []:
        try:
            club(item.get("team"))
            club(item.get("dc"))
        except (StaffUiError, AttributeError):
            out.append(f"a coordinator entry names a club that does not exist: {item!r}")
    for home in dc_seats(staff).values():
        held[home] = held.get(home, 0) + 1
    for home, count in held.items():
        if count > 1:
            out.append(f"{people[home].name if home in people else home} would run {count} defenses")
    return out


# --------------------------------------------------------------------------------------------- the build-time engine
def engine() -> Any | None:
    """c2-staff's build-time module, when this Studio has it."""

    try:
        from . import nfl2k5_coach_staff as module          # noqa: PLC0415 - optional by design
    except ImportError:
        return None
    return module


@dataclass(frozen=True)
class EnginePlan:
    """What the build-time engine says about a staff document on a roster: plain-words problems and notes, and per club
    (book code) its own answer: who coaches, where his playbook comes from, and whether the automatic 2026 play calling
    binds to him and why not."""

    errors: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    clubs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def engine_plan(staff: Mapping[str, Any], roster_body: bytes) -> EnginePlan:
    """Ask the build-time engine to plan ``staff`` on ``roster_body``; an empty answer when there is no engine."""

    module = engine()
    if module is None or is_empty(staff):
        return EnginePlan()
    try:
        plan = module.plan(staff, roster_body)
    except Exception as exc:                               # noqa: BLE001 - the engine's own words are the answer
        return EnginePlan(errors=(str(exc),))
    clubs: dict[str, Mapping[str, Any]] = {}
    for row in getattr(plan, "clubs", ()):
        try:
            data = row.as_dict() if hasattr(row, "as_dict") else dict(row)
        except (TypeError, ValueError):
            continue
        if data.get("team"):
            clubs[str(data["team"])] = data
    return EnginePlan(tuple(str(line) for line in getattr(plan, "errors", ())),
                      tuple(str(line) for line in getattr(plan, "notes", ())), clubs)


def engine_normalized(staff: Mapping[str, Any]) -> dict[str, Any]:
    """The document in the build-time engine's own canonical form (the page's own when the engine is absent)."""

    module = engine()
    if module is None or is_empty(staff):
        return dict(staff)
    normalized = module.normalize(staff)
    return dict(normalized)


def read_file(path: Path | str) -> dict[str, Any]:
    """A saved staff file (the document alone, or a roster-edits file that carries one)."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    _require(isinstance(data, Mapping), "a staff file is a JSON object")
    staff = data.get("staff", data) if "head_coaches" not in data else data
    _require(isinstance(staff, Mapping) and staff.get("schema") == SCHEMA,
             f"this is not a staff file (it should say {SCHEMA!r})")
    return dict(staff)


def write_file(path: Path | str, staff: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(dict(staff), indent=1) + "\n", encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    """``python3 -m mod_editor.core.nfl2k5_staff_ui [--disc DISC] [STAFF.json]``: print the clubs, or check a staff file."""

    import argparse

    parser = argparse.ArgumentParser(description="Show the 32 clubs' head coaches and coordinators, or check a staff file.")
    parser.add_argument("staff", nargs="?", help="a staff file (the staff section of a roster-edits file also works)")
    parser.add_argument("--disc", help="the game disc whose roster holds the head coaches")
    args = parser.parse_args(argv)
    people = coordinators()
    if not args.disc:
        for entry in CLUBS:
            dc = people.get(entry.book)
            print(f"{entry.code:4} {entry.nickname:11} defensive coordinator {dc.name if dc else '?'}")
        return 0
    document = rr.load_image(args.disc)
    rows = read_head_coaches(document)
    staff = read_file(args.staff) if args.staff else empty()
    for row in rows:
        print(f"{row.club.code:4} head coach {row.name}")
    issues = problems(rows, staff)
    for line in describe(rows, staff):
        print(" *", line)
    for line in issues:
        print(" !", line)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
