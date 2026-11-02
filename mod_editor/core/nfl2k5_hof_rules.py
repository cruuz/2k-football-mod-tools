"""Hall of Fame rules for the franchise history (job j6-hof, b780): who is inducted, when, and what the pop-up says.

Noah's asks (Discord #2k5-ideas, SWeaR 10/10): "Yearly HOF inductions would be fire". The research (b780 r4, J6) chose a
real five-season wait, up to five inductees a class, real retirees seeded so there are classes from year one, and a pop-up
after the Super Bowl pop-up. This module is the rule book. It is plain Python on integers with no game, save or roster
dependency, so the native history owner (job j23, "J3") can mirror it line for line and prove the C code against it
(``golden_vectors`` and ``history_words`` below feed an offline Unicorn replay).

The rule in plain words (``RULE_HELP`` repeats it for the Studio option text)
------------------------------------------------------------------------------
* A player is judged when he retires (the retirement pass marks him; his record and history are dropped a few stages
  later, so the score is computed once, then and kept). Score = honors + games + production, all whole points:

  - honors: 25 per first-team All-Pro season, 25 per MVP, 15 per Offensive or Defensive Player of the Year, 15 per Super
    Bowl MVP, 10 for Rookie of the Year (once), 15 per rushing title (at most 4), 3 per Super Bowl ring (at most 4);
  - games: 1 point per 4 games above 80, at most 20 (35 for linemen, whose record is seasons as a starter);
  - production: up to 25 points, how close his career comes to a typical Hall of Famer at his position (touchdowns for
    quarterbacks, yards and touchdowns for backs and receivers, sacks and interceptions on defense, field goals for
    kickers; linemen and punters have no production line). Tackles are not counted (the sim piles them up).
* Pro Bowls are not counted. The game records them only for seeded real players, never for new ones, so counting them
  would favour real careers over franchise careers; the calibration does as well without them (see below).
* A retiree with 80 points or more becomes a candidate (the table holds 64; when it is full a better score replaces the
  weakest). He is eligible five seasons after his last season and stays eligible for 15 more seasons (20 after he
  retires), then drops off.
* At each season close the eligible candidates are ranked (score, then honors, seasons, earliest retirement, table slot):
  up to 5 with 100 points or more are inducted. If fewer than 2 reach 100, the best candidates with 80 or more fill the
  class up to 2. No eligible candidate with 80 points means no class that year (no pop-up).
* The class is named for the next year ("Class of 2027" after the 2026 season), like the real one.

Calibration (``tools/b780_hof_calibrate.py``; every number is re-checked by ``tests/mod_editor/test_b780_j6_hof_rules.py``)
-----------------------------------------------------------------------------------------------------------------------
Real careers of the 5,399 players in the sources who retired 2005-2019 (``data/nfl2k5_hof_calibration_2026.json``): 55 are real
Hall of Famers (the Wikipedia list at a pinned revision, through the Class of 2026; j5's list agrees on all 55 classes). Bar
100: 47 of the 55 inductees pass (85.5 %: retired 2005-2012 30 of 36, 2013-2019 17 of 19) and 12 of the 239 notable
non-inductees pass (5.0 %); none of the other 5,105 retirees does (the 5,057 left out of the dataset score 39 or less). The
yearly replay (one close per season from 2004, table filled year by year) makes classes of 2 to 5 for every class 2010-2026:
68 inductees, 52 of them real Hall of Famers. The All-Pro weight and the production cap are the two knobs that matter (+/-20 %
of either moves 5 to 10 players); the other weights and caps move at most one inductee and two non-inductees. The production
term saturates, so scaling the game's sim production by 0.8 to 1.3 leaves the ten-season sim count at 15.

What this module does not do: it does not read the save, the roster or the executable; the hall block layout belongs to
``nfl2k5_franchise_extension`` (job j23) and the records here are byte-compatible with it (``candidate_to_bytes`` /
``inductee_to_bytes``; the cross-check test runs when that module is present).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Iterable, Sequence

SCHEMA = "nfl2k5_hof_rules/v1"
OWNER = "nfl2k5_history"                    # the native owner that runs these rules (job j23, J3)
EVIDENCE = "UNIT + OFFLINE REAL-CAREER REPLAY"

# --------------------------------------------------------------------------------------------------------------------
# calendar and table (the hall block of the franchise extension footer: 192 inductees, 64 candidates)
WAIT_SEASONS = 5            # eligible when the season being closed is at least this many seasons after his last one
WINDOW_SEASONS = 15         # and for this many more closes (retired + 5 .. retired + 20 inclusive)
MAX_CLASS = 5
MIN_CLASS = 2
BAR = 100                   # points that induct, whatever the class size so far (up to MAX_CLASS)
FLOOR = 80                  # points to become a candidate, and the lowest that may fill a class up to MIN_CLASS
INDUCTEE_SLOTS = 192
CANDIDATE_SLOTS = 64

# --------------------------------------------------------------------------------------------------------------------
# positions: the game's 17 codes and the ten groups the rule uses
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
GROUPS = ("QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB", "K", "P")
GROUP_OF_POSITION = (0, 8, 9, 2, 7, 7, 7, 1, 1, 3, 6, 6, 4, 4, 4, 5, 5)
G_QB, G_RB, G_WR, G_TE, G_OL, G_DL, G_LB, G_DB, G_K, G_P = range(10)
NO_PRODUCTION = (G_OL, G_P)                 # no production term: linemen have no stat line, punters' lines are not used
BIG_GAMES_CAP = (G_OL,)                     # linemen only: seasons as a starter are their record

# the history fields the native code sums over a player's whole stream (folded "pre" row included); values are 16-bit
# words, fields 2 and 13 are signed. Nothing else is read.
FIELD_GAMES = 0
FIELD_RUSHING_YARDS = 2
FIELD_RUSHING_TOUCHDOWNS = 3
FIELD_PASSING_TOUCHDOWNS = 9
FIELD_RECEIVING_YARDS = 13
FIELD_RECEIVING_TOUCHDOWNS = 14
FIELD_SACKS_HALF = 19
FIELD_INTERCEPTIONS = 20
FIELDS_FIELD_GOALS = (61, 63, 65, 67)       # made, by distance bucket
HONOR_FIELD0 = 96                           # mvp opoy dpoy oroy droy super_bowl super_bowl_mvp pro_bowl all_pro rushing_title
HONORS = ("mvp", "opoy", "dpoy", "oroy", "droy", "super_bowl", "super_bowl_mvp", "pro_bowl", "all_pro", "rushing_title")
SIGNED_FIELDS = (FIELD_RUSHING_YARDS, FIELD_RECEIVING_YARDS)

# --------------------------------------------------------------------------------------------------------------------
# the score (whole points; every term is an integer product, a floor division by a constant, or a min)
POINTS = {"all_pro": 25, "mvp": 25, "player_of_year": 15, "super_bowl_mvp": 15, "rookie_of_year": 10,
          "rushing_title": 15, "super_bowl": 3}
RUSHING_TITLE_CAP = 4
SUPER_BOWL_CAP = 4
ROOKIE_OF_YEAR_CAP = 1      # a man is a rookie once (offense or defense)
GAMES_FREE = 80
GAMES_PER_POINT = 4
GAMES_CAP = 20
GAMES_CAP_LINEMEN = 35
PRODUCTION_CAP = 25
SCORE_MAX = 0xFFFF          # the footer stores the score in a u16; the sum saturates here (a real career scores under 400)
# production par: a career worth one par is a typical Hall of Famer at the position (35th percentile of the real inductees
# who retired 2005-2019; kickers use a real threshold, 400 field goals, because the dataset's two kickers are partial).
# The composite is in tenths: see ``composite``.
PAR = {"QB": 2100, "RB": 21000, "WR": 18500, "TE": 18500, "DL": 3000, "LB": 1500, "DB": 2000, "K": 4000}

UI_LABEL = "Hall of Fame classes with real retirees seeded"     # 60-character caption rule

RULE_HELP = (
    "Hall of Fame: when a player retires he is scored from his honors, games and production. First-team All-Pro 25, MVP 25, "
    "Player of the Year 15, Super Bowl MVP 15, Rookie of the Year 10 (once), rushing title 15, Super Bowl ring 3, one point per "
    "4 games over 80 (most 20; 35 for linemen), and up to 25 for production at his position (none for linemen and punters). Pro Bowls and "
    "tackles do not count. With 80 points he becomes a candidate. Five seasons after he retires he can be inducted: each "
    "year up to 5 candidates with 100 points go in, and if fewer than 2 reach 100 the best candidates with 80 or more "
    "fill the class to 2. A candidate is dropped 20 seasons after he retired.")


@dataclass(frozen=True)
class Career:
    """A player's career sums as the native code reads them from the history stream (see the FIELD_ constants)."""

    group: int
    games: int = 0
    mvp: int = 0
    opoy: int = 0
    dpoy: int = 0
    oroy: int = 0
    droy: int = 0
    super_bowl: int = 0
    super_bowl_mvp: int = 0
    pro_bowl: int = 0
    all_pro: int = 0
    rushing_title: int = 0
    passing_touchdowns: int = 0
    rushing_touchdowns: int = 0
    rushing_yards: int = 0
    receiving_yards: int = 0
    receiving_touchdowns: int = 0
    sacks_half: int = 0
    interceptions: int = 0
    field_goals_made: int = 0

    @classmethod
    def from_position(cls, position: int | str, **fields) -> "Career":
        code = POSITIONS.index(position) if isinstance(position, str) else int(position)
        if not 0 <= code < len(POSITIONS):
            raise ValueError("position code out of range")
        return cls(GROUP_OF_POSITION[code], **fields)


def _n(value: int) -> int:
    """Negative sums (a wrapped signed word) count as zero."""

    return value if value > 0 else 0


def composite(c: Career) -> int:
    """Career production in tenths of a point, by group (no stat line: 0)."""

    g = c.group
    if g == G_QB:
        return 10 * _n(c.passing_touchdowns) + 20 * _n(c.rushing_touchdowns)
    if g == G_RB:
        return _n(c.rushing_yards) + 60 * _n(c.rushing_touchdowns) + _n(c.receiving_yards) + 60 * _n(c.receiving_touchdowns)
    if g in (G_WR, G_TE):
        return _n(c.receiving_yards) + 60 * _n(c.receiving_touchdowns)
    if g == G_DL:
        return 15 * _n(c.sacks_half) + 40 * _n(c.interceptions)
    if g == G_LB:
        return 15 * _n(c.sacks_half) + 50 * _n(c.interceptions)
    if g == G_DB:
        return 50 * _n(c.interceptions) + 15 * _n(c.sacks_half)
    if g == G_K:
        return 10 * _n(c.field_goals_made)
    return 0


def honors_points(c: Career) -> int:
    return (POINTS["all_pro"] * _n(c.all_pro) + POINTS["mvp"] * _n(c.mvp)
            + POINTS["player_of_year"] * (_n(c.opoy) + _n(c.dpoy)) + POINTS["super_bowl_mvp"] * _n(c.super_bowl_mvp)
            + POINTS["rookie_of_year"] * min(_n(c.oroy) + _n(c.droy), ROOKIE_OF_YEAR_CAP)
            + POINTS["rushing_title"] * min(_n(c.rushing_title), RUSHING_TITLE_CAP)
            + POINTS["super_bowl"] * min(_n(c.super_bowl), SUPER_BOWL_CAP))


def games_points(c: Career) -> int:
    cap = GAMES_CAP_LINEMEN if c.group in BIG_GAMES_CAP else GAMES_CAP
    return min(cap, _n(c.games - GAMES_FREE) // GAMES_PER_POINT)


def production_points(c: Career) -> int:
    if c.group in NO_PRODUCTION:
        return 0
    return min(PRODUCTION_CAP, PRODUCTION_CAP * composite(c) // PAR[GROUPS[c.group]])


def score(c: Career) -> int:
    """The Hall of Fame score (saturating at ``SCORE_MAX``); Pro Bowls are read nowhere. In 32-bit arithmetic the unclamped sum of
    even absurd inputs (every field 32,767) stays under 4 million, so the native code needs no wider type."""

    return min(SCORE_MAX, honors_points(c) + games_points(c) + production_points(c))


def score_parts(c: Career) -> dict:
    return {"honors": honors_points(c), "games": games_points(c), "production": production_points(c), "score": score(c)}


def honors_count(c: Career) -> int:
    """The footer's honors byte: MVP + player of the year + All-Pro + Pro Bowl seasons (display and tie-break only)."""

    return min(255, _n(c.mvp) + _n(c.opoy) + _n(c.dpoy) + _n(c.all_pro) + _n(c.pro_bowl))


def seasons_from_games(games: int) -> int:
    """Fallback for the footer's seasons byte when the caller has no season count (sixteen games make a season)."""

    return min(255, (_n(games) + 15) // 16)


# --------------------------------------------------------------------------------------------------------------------
# records: byte-compatible with the hall block of nfl2k5_franchise_extension (job j23)
FLAG_VALID, FLAG_REAL, FLAG_FRANCHISE = 1, 2, 4
CANDIDATE_ENTRY = struct.Struct("<7sBHHBBHHHBBH")     # person, club+1, retired, score, seasons, flags, 3 keys, honors, rings, 0
INDUCTEE_ENTRY = struct.Struct("<7sBHHBBH")           # person, club+1, class year, retired, flags, seasons, score
assert CANDIDATE_ENTRY.size == 24 and INDUCTEE_ENTRY.size == 16


class HofError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise HofError(message)


@dataclass(frozen=True)
class Candidate:
    person: bytes                    # 7 bytes: first initial, nine letters of the last name, position code (champions packing)
    club: int | None                 # club index 0..31 (arena order, nfl2k5_champions_history.CLUBS) or None
    retired: int                     # the season he last played
    score: int
    seasons: int = 0
    flags: int = FLAG_VALID
    keys: tuple[int, int, int] = (0, 0, 0)
    honors: int = 0
    sb_wins: int = 0

    def __post_init__(self):
        _require(len(self.person) == 7, "person must be 7 bytes")
        _require(0 <= self.score <= 0xFFFF and 0 <= self.retired <= 0xFFFF, "score or season out of range")
        _require(self.club is None or 0 <= self.club < 32, "club out of range")
        _require(len(self.keys) == 3 and all(0 <= k <= 0xFFFF for k in self.keys), "keys out of range")
        _require(0 <= self.seasons <= 255 and 0 <= self.honors <= 255 and 0 <= self.sb_wins <= 255, "byte out of range")


@dataclass(frozen=True)
class Inductee:
    person: bytes
    club: int | None
    class_year: int
    retired: int
    flags: int
    seasons: int
    score: int


def candidate_to_bytes(c: Candidate) -> bytes:
    return CANDIDATE_ENTRY.pack(c.person, 0 if c.club is None else c.club + 1, c.retired, c.score, c.seasons,
                                c.flags | FLAG_VALID, *c.keys, c.honors, c.sb_wins, 0)


def candidate_from_bytes(raw: bytes) -> Candidate | None:
    _require(len(raw) == CANDIDATE_ENTRY.size, "bad candidate size")
    person, club, retired, score_, seasons, flags, k1, k2, k3, honors, rings, _ = CANDIDATE_ENTRY.unpack(raw)
    if not flags & FLAG_VALID:
        return None
    return Candidate(person, club - 1 if club else None, retired, score_, seasons, flags, (k1, k2, k3), honors, rings)


def inductee_to_bytes(i: Inductee) -> bytes:
    return INDUCTEE_ENTRY.pack(i.person, 0 if i.club is None else i.club + 1, i.class_year, i.retired,
                               i.flags | FLAG_VALID, i.seasons, i.score)


def inductee_from_bytes(raw: bytes) -> Inductee | None:
    _require(len(raw) == INDUCTEE_ENTRY.size, "bad inductee size")
    person, club, klass, retired, flags, seasons, score_ = INDUCTEE_ENTRY.unpack(raw)
    if not flags & FLAG_VALID:
        return None
    return Inductee(person, club - 1 if club else None, klass, retired, flags, seasons, score_)


# --------------------------------------------------------------------------------------------------------------------
# the yearly process
def class_year(season: int) -> int:
    """The class is named for the year after the season being closed (the 2026 season closes into the Class of 2027)."""

    return season + 1


def first_eligible_season(retired: int) -> int:
    return retired + WAIT_SEASONS


def last_eligible_season(retired: int) -> int:
    return retired + WAIT_SEASONS + WINDOW_SEASONS


def is_eligible(c: Candidate, season: int) -> bool:
    return first_eligible_season(c.retired) <= season <= last_eligible_season(c.retired)


def rank_key(slot: int, c: Candidate) -> tuple:
    """Smaller sorts first: score, honors count, seasons, earlier retirement, lower slot."""

    return (-c.score, -c.honors, -c.seasons, c.retired, slot)


def empty_table() -> list:
    return [None] * CANDIDATE_SLOTS


def select_class(table: Sequence[Candidate | None], season: int) -> list[int]:
    """Slots inducted at the close of ``season``, best first."""

    ranked = sorted((rank_key(i, c), i) for i, c in enumerate(table) if c is not None and is_eligible(c, season))
    chosen = [i for _, i in ranked if table[i].score >= BAR][:MAX_CLASS]
    if len(chosen) < MIN_CLASS:
        fill = [i for _, i in ranked if i not in chosen and table[i].score >= FLOOR]
        chosen += fill[:MIN_CLASS - len(chosen)]
    return chosen


def admit_detail(table: list, candidate: Candidate) -> tuple[str, Candidate | None]:
    """Put a retiree on the table. -> (outcome, dropped): "added" (a free slot, nothing dropped), "replaced" (the weakest candidate was
    dropped and is returned) or "refused" (below the floor, already on the table, or weaker than everyone in a full table)."""

    if candidate.score < FLOOR:
        return "refused", None
    if any(c == candidate for c in table):                # the retirement pass ran twice for the same man
        return "refused", None
    for i, c in enumerate(table):
        if c is None:
            table[i] = candidate
            return "added", None
    worst = max(range(len(table)), key=lambda i: rank_key(i, table[i]))
    if rank_key(worst, candidate) < rank_key(worst, table[worst]):
        dropped, table[worst] = table[worst], candidate
        return "replaced", dropped
    return "refused", None


def admit(table: list, candidate: Candidate) -> str:
    return admit_detail(table, candidate)[0]


@dataclass
class Close:
    season: int
    class_year: int
    inductees: list = field(default_factory=list)       # Inductee, best first
    sources: list = field(default_factory=list)         # the Candidate each inductee came from (same order)
    expired: list = field(default_factory=list)         # Candidate dropped for age
    admitted: list = field(default_factory=list)        # (Candidate, "added" | "replaced" | "refused")
    evicted: list = field(default_factory=list)         # Candidate dropped to make room (a full table)


def close_season(table: list, season: int, retirees: Iterable[Candidate] = ()) -> Close:
    """The whole yearly step on ``table`` (changed in place): induct, drop the over-age, then admit this season's retirees."""

    result = Close(season, class_year(season))
    for slot in select_class(table, season):
        c = table[slot]
        result.inductees.append(Inductee(c.person, c.club, result.class_year, c.retired, FLAG_FRANCHISE | (c.flags & FLAG_REAL),
                                         c.seasons, c.score))
        result.sources.append(c)
        table[slot] = None
    for i, c in enumerate(table):
        if c is not None and season >= last_eligible_season(c.retired):
            result.expired.append(c)
            table[i] = None
    for retiree in retirees:
        outcome, dropped = admit_detail(table, retiree)
        result.admitted.append((retiree, outcome))
        if dropped is not None:
            result.evicted.append(dropped)
    return result


# --------------------------------------------------------------------------------------------------------------------
# the pop-up (one-button native notice, 0x14E520; the Super Bowl notice shows four lines of about 36 characters)
POPUP_LINE_MAX = 36
POPUP_NAMES_PER_NOTICE = 3          # title + 3 names = 4 lines, the size the Super Bowl notice showed in xemu
POPUP_TITLE = "Hall of Fame Class of {year}"


def person_line(person: bytes, club: int | None, *, clubs: Sequence[str] | None = None,
                position_labels: Sequence[str] = POSITIONS) -> str:
    """"T. BRADY, QB, Buccaneers": the packed name is initial + up to nine letters in capitals, as on the champions page."""

    from . import nfl2k5_champions_history as champions
    clubs = champions.CLUBS if clubs is None else clubs
    info = champions.unpack_person(person)
    _require(info is not None, "empty person")
    code = champions.POSITIONS.index(info["position"]) if info["position"] in champions.POSITIONS else None
    parts = [(info["initial"] + ". " if info["initial"] else "") + info["last"]]
    if code is not None:
        parts.append(position_labels[code])
    if club is not None and 0 <= club < len(clubs):
        parts.append(clubs[club])
    return ", ".join(parts)


def popup_texts(klass: int, inductees: Sequence[Inductee], *, per_notice: int = POPUP_NAMES_PER_NOTICE,
                clubs: Sequence[str] | None = None, position_labels: Sequence[str] = POSITIONS) -> list[str]:
    """The notices for one class: [] for an empty class, else one text per ``per_notice`` names, lines joined by newline."""

    _require(per_notice >= 1, "per_notice")
    names = list(inductees)
    if not names:
        return []
    pages = [names[i:i + per_notice] for i in range(0, len(names), per_notice)]
    texts = []
    for n, page in enumerate(pages, 1):
        title = POPUP_TITLE.format(year=klass) + (f" ({n} of {len(pages)})" if len(pages) > 1 else "")
        lines = [title] + [person_line(i.person, i.club, clubs=clubs, position_labels=position_labels) for i in page]
        texts.append("\n".join(lines))
    return texts


# --------------------------------------------------------------------------------------------------------------------
# native parity: the history words, the golden vectors and the C table
def history_words(c: Career) -> list[int]:
    """A history stream that sums to ``c`` (one folded word per non-zero field, slot 1, end bit on the last word).

    Word: bits 0..15 value, 16..22 field, 23..27 slot, 28 deleted, 29 postseason, 30 folded, 31 end. Every field value
    must fit a signed 16-bit word (the game itself wraps a longer sum), so a vector never exceeds 32,767."""

    values = {FIELD_GAMES: c.games, FIELD_RUSHING_YARDS: c.rushing_yards, FIELD_RUSHING_TOUCHDOWNS: c.rushing_touchdowns,
              FIELD_PASSING_TOUCHDOWNS: c.passing_touchdowns, FIELD_RECEIVING_YARDS: c.receiving_yards,
              FIELD_RECEIVING_TOUCHDOWNS: c.receiving_touchdowns, FIELD_SACKS_HALF: c.sacks_half,
              FIELD_INTERCEPTIONS: c.interceptions, FIELDS_FIELD_GOALS[0]: c.field_goals_made}
    for i, name in enumerate(HONORS):
        values[HONOR_FIELD0 + i] = getattr(c, name)
    words = []
    for fld in sorted(values):
        v = values[fld]
        if v == 0:
            continue
        _require(-32768 <= v <= 32767 and (v >= 0 or fld in SIGNED_FIELDS), f"field {fld} value {v} does not fit one word")
        words.append(0x40000000 | (1 << 23) | (fld << 16) | (v & 0xFFFF))
    if not words:
        words.append(0x40000000 | (1 << 23) | (FIELD_GAMES << 16))
    words[-1] |= 0x80000000
    return words


def career_from_words(group: int, words: Iterable[int]) -> Career:
    """What the native pass computes: sum the live regular-class words of the fields above (negative sums count as zero)."""

    sums: dict[int, int] = {}
    for w in words:
        if w & 0x10000000 or w & 0x20000000:             # deleted, postseason
            continue
        fld, v = (w >> 16) & 127, w & 0xFFFF
        if fld in SIGNED_FIELDS and v >= 0x8000:
            v -= 0x10000
        sums[fld] = sums.get(fld, 0) + v
    return Career(group=group, games=sums.get(FIELD_GAMES, 0), rushing_yards=sums.get(FIELD_RUSHING_YARDS, 0),
                  rushing_touchdowns=sums.get(FIELD_RUSHING_TOUCHDOWNS, 0),
                  passing_touchdowns=sums.get(FIELD_PASSING_TOUCHDOWNS, 0), receiving_yards=sums.get(FIELD_RECEIVING_YARDS, 0),
                  receiving_touchdowns=sums.get(FIELD_RECEIVING_TOUCHDOWNS, 0), sacks_half=sums.get(FIELD_SACKS_HALF, 0),
                  interceptions=sums.get(FIELD_INTERCEPTIONS, 0),
                  field_goals_made=sum(sums.get(f, 0) for f in FIELDS_FIELD_GOALS),
                  **{name: sums.get(HONOR_FIELD0 + i, 0) for i, name in enumerate(HONORS)})


def native_table() -> dict:
    """Every constant the C code needs, in one place (``c_header`` prints it)."""

    return {
        "group_of_position": GROUP_OF_POSITION,
        "points": dict(POINTS), "rushing_title_cap": RUSHING_TITLE_CAP, "super_bowl_cap": SUPER_BOWL_CAP, "rookie_of_year_cap": ROOKIE_OF_YEAR_CAP,
        "games_free": GAMES_FREE, "games_per_point": GAMES_PER_POINT, "games_cap": GAMES_CAP,
        "games_cap_linemen": GAMES_CAP_LINEMEN, "production_cap": PRODUCTION_CAP, "score_max": SCORE_MAX,
        "par": tuple(PAR.get(g, 0) for g in GROUPS), "bar": BAR, "floor": FLOOR, "wait": WAIT_SEASONS,
        "window": WINDOW_SEASONS, "max_class": MAX_CLASS, "min_class": MIN_CLASS, "candidate_slots": CANDIDATE_SLOTS,
        "inductee_slots": INDUCTEE_SLOTS,
    }


def c_header() -> str:
    t = native_table()
    lines = ["/* generated by nfl2k5_hof_rules.c_header(); do not edit */"]
    lines.append("static const unsigned char HOF_GROUP[17] = {%s};" % ", ".join(map(str, t["group_of_position"])))
    lines.append("static const unsigned int HOF_PAR[10] = {%s}; /* QB RB WR TE OL DL LB DB K P; 0 = no stat line */"
                 % ", ".join(map(str, t["par"])))
    for key in ("all_pro", "mvp", "player_of_year", "super_bowl_mvp", "rookie_of_year", "rushing_title", "super_bowl"):
        lines.append(f"#define HOF_PTS_{key.upper()} {t['points'][key]}")
    for key in ("rushing_title_cap", "super_bowl_cap", "rookie_of_year_cap", "games_free", "games_per_point", "games_cap",
                "games_cap_linemen", "production_cap", "score_max", "bar", "floor", "wait", "window", "max_class", "min_class",
                "candidate_slots", "inductee_slots"):
        lines.append(f"#define HOF_{key.upper()} {t[key]}")
    return "\n".join(lines) + "\n"


C_REFERENCE_BODY = r"""
typedef struct {
    unsigned group;                                   /* 0 QB, 1 RB, 2 WR, 3 TE, 4 OL, 5 DL, 6 LB, 7 DB, 8 K, 9 P */
    int games, mvp, opoy, dpoy, oroy, droy, super_bowl, super_bowl_mvp, all_pro, rushing_title;
    int passing_touchdowns, rushing_touchdowns, rushing_yards, receiving_yards, receiving_touchdowns;
    int sacks_half, interceptions, field_goals_made;
} HofCareer;
typedef struct { int valid; unsigned score, honors, seasons, retired; } HofSlot;

/* position code 0..16 (the game's order) to the rule's group; 0xFF for anything else */
unsigned hof_group_of(unsigned position) { return position < 17u ? HOF_GROUP[position] : 0xFFu; }

static unsigned hof_n(int v) { return v > 0 ? (unsigned)v : 0u; }
static unsigned hof_min(unsigned a, unsigned b) { return a < b ? a : b; }

unsigned hof_composite(const HofCareer *c) {
    switch (c->group) {
    case 0: return 10u * hof_n(c->passing_touchdowns) + 20u * hof_n(c->rushing_touchdowns);
    case 1: return hof_n(c->rushing_yards) + 60u * hof_n(c->rushing_touchdowns) + hof_n(c->receiving_yards) + 60u * hof_n(c->receiving_touchdowns);
    case 2: case 3: return hof_n(c->receiving_yards) + 60u * hof_n(c->receiving_touchdowns);
    case 5: return 15u * hof_n(c->sacks_half) + 40u * hof_n(c->interceptions);
    case 6: return 15u * hof_n(c->sacks_half) + 50u * hof_n(c->interceptions);
    case 7: return 50u * hof_n(c->interceptions) + 15u * hof_n(c->sacks_half);
    case 8: return 10u * hof_n(c->field_goals_made);
    default: return 0u;
    }
}

unsigned hof_score(const HofCareer *c) {
    unsigned honors = HOF_PTS_ALL_PRO * hof_n(c->all_pro) + HOF_PTS_MVP * hof_n(c->mvp)
        + HOF_PTS_PLAYER_OF_YEAR * (hof_n(c->opoy) + hof_n(c->dpoy)) + HOF_PTS_SUPER_BOWL_MVP * hof_n(c->super_bowl_mvp)
        + HOF_PTS_ROOKIE_OF_YEAR * hof_min(hof_n(c->oroy) + hof_n(c->droy), HOF_ROOKIE_OF_YEAR_CAP)
        + HOF_PTS_RUSHING_TITLE * hof_min(hof_n(c->rushing_title), HOF_RUSHING_TITLE_CAP)
        + HOF_PTS_SUPER_BOWL * hof_min(hof_n(c->super_bowl), HOF_SUPER_BOWL_CAP);
    unsigned cap = c->group == 4 ? HOF_GAMES_CAP_LINEMEN : HOF_GAMES_CAP;
    unsigned games = hof_min(cap, hof_n(c->games - HOF_GAMES_FREE) / HOF_GAMES_PER_POINT);
    unsigned prod = 0;
    if (HOF_PAR[c->group]) prod = hof_min(HOF_PRODUCTION_CAP, HOF_PRODUCTION_CAP * hof_composite(c) / HOF_PAR[c->group]);
    unsigned total = honors + games + prod;
    return total > HOF_SCORE_MAX ? HOF_SCORE_MAX : total;
}

/* 1 when a ranks strictly before b, ignoring the slot: score, honors, seasons (larger first), earlier retirement */
static int hof_better(const HofSlot *a, const HofSlot *b) {
    if (a->score != b->score) return a->score > b->score;
    if (a->honors != b->honors) return a->honors > b->honors;
    if (a->seasons != b->seasons) return a->seasons > b->seasons;
    return a->retired < b->retired;
}

/* 1 when slot a ranks before slot b: the order above, then the lower slot */
int hof_before(const HofSlot *t, int a, int b) {
    if (t[a].score != t[b].score || t[a].honors != t[b].honors || t[a].seasons != t[b].seasons || t[a].retired != t[b].retired)
        return hof_better(&t[a], &t[b]);
    return a < b;
}

static int hof_eligible(const HofSlot *s, unsigned season) {
    return s->valid && s->retired + HOF_WAIT <= season && season <= s->retired + HOF_WAIT + HOF_WINDOW;
}

/* slots inducted at the close of `season`, best first; returns how many (at most HOF_MAX_CLASS) */
int hof_select(const HofSlot *t, unsigned season, int *out) {
    int n = 0, i, best, chosen[HOF_CANDIDATE_SLOTS] = {0};
    for (;;) {                                         /* up to the class size with the bar or more */
        best = -1;
        for (i = 0; i < HOF_CANDIDATE_SLOTS; i++)
            if (!chosen[i] && hof_eligible(&t[i], season) && t[i].score >= HOF_BAR && (best < 0 || hof_before(t, i, best))) best = i;
        if (best < 0 || n >= HOF_MAX_CLASS) break;
        chosen[best] = 1; out[n++] = best;
    }
    while (n < HOF_MIN_CLASS) {                        /* then the best with the floor or more, up to the minimum */
        best = -1;
        for (i = 0; i < HOF_CANDIDATE_SLOTS; i++)
            if (!chosen[i] && hof_eligible(&t[i], season) && t[i].score >= HOF_FLOOR && (best < 0 || hof_before(t, i, best))) best = i;
        if (best < 0) break;
        chosen[best] = 1; out[n++] = best;
    }
    return n;
}

/* 0 refused, 1 added, 2 replaced the weakest; the same four numbers on the table mean the same man */
int hof_admit(HofSlot *t, const HofSlot *c) {
    int i, worst = 0;
    if (c->score < HOF_FLOOR) return 0;
    for (i = 0; i < HOF_CANDIDATE_SLOTS; i++)
        if (t[i].valid && t[i].score == c->score && t[i].honors == c->honors && t[i].seasons == c->seasons && t[i].retired == c->retired) return 0;
    for (i = 0; i < HOF_CANDIDATE_SLOTS; i++)
        if (!t[i].valid) { t[i] = *c; t[i].valid = 1; return 1; }
    for (i = 1; i < HOF_CANDIDATE_SLOTS; i++)
        if (hof_before(t, worst, i)) worst = i;          /* the lowest ranked slot */
    if (!hof_better(c, &t[worst])) return 0;             /* in his slot he would not rank before the one he replaces */
    t[worst] = *c; t[worst].valid = 1;
    return 2;
}
"""


def c_reference() -> str:
    """The rule as C on 32-bit integers (host-compilable; no library calls): ``hof_score``, ``hof_before``, ``hof_select`` and
    ``hof_admit`` over a 64-slot table, with the constants from ``c_header``. The unit test compiles it, if a C compiler is
    installed, and fuzzes it against this module. The native owner starts from it, so it is the proven starting point and
    not a replacement for the owner's own Unicorn replay."""

    return c_header() + C_REFERENCE_BODY


def golden_vectors() -> list[dict]:
    """Deterministic cases covering every term, cap, group and clamp: ``{"group", "position", "fields", "score", "parts"}``.
    The native owner's Unicorn test builds each stream with ``history_words`` and compares its score with ``score``."""

    cases: list[tuple[int, dict]] = []
    for position, group in enumerate(GROUP_OF_POSITION):
        cases.append((position, {}))
        cases.append((position, dict(games=300, all_pro=5, mvp=1, opoy=1, super_bowl=2, super_bowl_mvp=1)))
    base = {0: dict(passing_touchdowns=500, rushing_touchdowns=15, all_pro=4, mvp=2, super_bowl=3),
            7: dict(rushing_yards=13500, rushing_touchdowns=100, receiving_yards=4000, receiving_touchdowns=15, all_pro=3,
                    rushing_title=2, games=170),
            3: dict(receiving_yards=14500, receiving_touchdowns=120, all_pro=3, games=190),
            9: dict(receiving_yards=11800, receiving_touchdowns=116, all_pro=3, games=233),
            16: dict(sacks_half=270, interceptions=8, all_pro=4, dpoy=1, games=200),
            11: dict(sacks_half=80, interceptions=30, all_pro=5, dpoy=2, super_bowl=2, games=228),
            4: dict(interceptions=60, sacks_half=10, all_pro=4, games=215),
            13: dict(all_pro=6, super_bowl=1, games=206),
            1: dict(field_goals_made=520, all_pro=3, super_bowl=4, games=316)}
    for position, fields in base.items():
        cases.append((position, fields))
    cases += [(7, dict(rushing_yards=-500, receiving_yards=-1)),                                 # wrapped signed sums clamp to 0
              (3, dict(rushing_title=9, super_bowl=9, all_pro=1)),                              # caps
              (12, dict(games=400, all_pro=3)),                                                   # the larger games cap for linemen
              (2, dict(games=400, all_pro=5)),
              (0, dict(games=80)), (0, dict(games=84)), (0, dict(games=159)), (0, dict(games=160)),   # games steps and cap
              (7, dict(rushing_yards=21000, rushing_touchdowns=0)),                              # production exactly at par
              (7, dict(rushing_yards=20999))]                                                    # one tenth below par
    out = []
    for position, fields in cases:
        c = Career.from_position(position, **fields)
        out.append({"position": position, "group": c.group, "fields": {k: v for k, v in fields.items()},
                    "score": score(c), "parts": score_parts(c)})
    return out


__all__ = ["SCHEMA", "OWNER", "WAIT_SEASONS", "WINDOW_SEASONS", "MAX_CLASS", "MIN_CLASS", "BAR", "FLOOR", "INDUCTEE_SLOTS",
           "CANDIDATE_SLOTS", "UI_LABEL", "POSITIONS", "GROUPS", "GROUP_OF_POSITION", "POINTS", "PAR", "RULE_HELP", "Career", "Candidate",
           "Inductee", "Close", "HofError", "composite", "honors_points", "games_points", "production_points", "score",
           "score_parts", "honors_count", "seasons_from_games", "candidate_to_bytes", "candidate_from_bytes",
           "inductee_to_bytes", "inductee_from_bytes", "class_year", "is_eligible", "rank_key", "empty_table",
           "select_class", "admit", "admit_detail", "close_season", "person_line", "popup_texts", "history_words", "career_from_words",
           "native_table", "c_header", "c_reference", "golden_vectors"]
