"""Franchise History screen, box scores from the Schedule and the Player Card game log (job b780 j4-history). EXPERIMENTAL.

Players asked (Discord #2k5-ideas): SWeaR 10/10 "a dedicated Team History tab in Franchise mode, displaying the all-time
stat leaders for each team and stuff like single game and single season records", SWeaR 10/03 "keeping track of past
MVPS, Super Bowl champs, DPOY ... player and team single season and single game records", SWeaR 10/10 "Yearly HOF
inductions", SWeaR 11/01 "I can go back to a game I played earlier in the season and view the full game stats when
selecting it in Schedule", adon 10/06 "Game logs too", LePromisedPrince 9/06 "History tracking tabs for previous season
results and awards". Research and design: ``b77_session/reports/b780_r4-records_RESEARCH.md`` (Design A, job J4).

What the player sees
--------------------
* **ESPN.com > TEAM HISTORY**, a new row after the retail ones. The screen uses the Team Standings layout
  (``league_news_common``: club banner, title bar, the sub-bar with the L and R arrows) and its geometry (ten row bars,
  the standings font and colours). Black/White change the page, L/R the club, Up/Down scroll, B goes back:

  1. SEASONS: the franchise-era record and titles, then one line per season, newest first (year, W-L-T, division
     finish, playoff result, head coach): the seasons played in this franchise first (yellow), then the real seasons
     2002 to 2025 of the seed.
  2. RECORDS: the club's single-season and single-game records (seeded; a record set in this franchise replaces the
     seeded one and is marked NEW).
  3. LEADERS: the club's all-time top three in ten categories (when the build carries the checked leader data, or the
     franchise footer keeps them).
  4. RECORD BOOK: NFL single-game, single-season and career records; a club record set in this franchise that beats
     the real one takes its place, marked NEW.
  5. AWARDS: L/R choose the award (MVP, OPOY, DPOY, OROY, DROY, Comeback, Coach of the Year, Super Bowl MVP); one line
     per season, franchise seasons first, then the real winners.
  6. HALL OF FAME: classes newest first, franchise inductees then the real members; L/R filter by club (all clubs first).

* **Box score from the Schedule**: X on a played game (the menu legend says "for Box Score") opens it: the line score by
  quarter from the league grid for every game, and for a game the franchise footer kept (your team's games), the team
  stats of both clubs and every player line; Up/Down scroll, B goes back to the Schedule.
* **Player Card game log** (page 4 of the card, after honors and champions): one line per stored game of the player
  this season ("WK 3 @PHI W 24-17  22/31 250 YDS 2 TD 1 INT").

Where the data comes from
-------------------------
* Real history (seasons, awards, the NFL record book, the Hall of Fame, the club records and leaders where they are
  checked) is a read-only block this owner carries, built at install time from the Studio's pinned seed documents
  (``data/nfl2k5_history_2026.json``, job j5-seed, and ``data/nfl2k5_franchise_leaders_2026.json``, job j5b-leaders,
  when the tree carries it; ``load_seed``, ``with_leaders``, ``build_ro``). Clubs are matched by their abbreviation, so
  the game's club order and the relocated clubs (STL, SD, OAK, JAC) need nothing.
* LEADERS: a footer table seeded with real leaders (flag "real") is the live one; a footer table without them (never
  seeded: franchise-era entries only) is merged with the read-only leaders by value, a player in both counted once.
* Franchise history (seasons with their awards and head coaches, totals, records, leaders, Hall of Fame classes, box
  scores) is kept by the franchise extension footer (job j23-footer: ``nfl2k5_franchise_extension``, capture at the
  game commit and the season close). This screen only reads it, through one word of the footer host
  (``hist_xtnd_ptr``: the address of the body in RAM; ``footer_pointer_va``). Without that owner the franchise parts
  read as empty and the real history still shows. ``FOOTER_BLOCKS`` pins the blocks the runtime reads.
* The Player Card's fourth page: the champions owner (part of the honors option) finds this owner's game log through a
  16-byte record {"HSX1", flip, rows, bio} kept right before the cloned ESPN.com rows (it follows the row pointer this
  owner sets at 0x525674), so neither owner links to the other and either can be installed first.

Allocation: one late owner (``nfl2k5_xbe_space.LATE_OWNERS``), code (``CODE_SIZE``), 64 RW bytes (page, club, scroll,
the selected box score) and a read-only block (``RO_SIZE``, 36 KiB: descriptors, the cloned ESPN.com rows, the seed tables).
Two retail sites: the ESPN.com descriptor's row-table pointer (0x525674, .rdata, a 4-byte pointer edit: the cloned table
has the retail rows plus TEAM HISTORY) and the Schedule input (0x24D2E5, a 6-byte call). Nobody else patches either.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Mapping

from . import nfl2k5_history_screen_code as runtime
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_history_screen"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 16384
DATA_SIZE = 64
RO_SIZE = 0x9000          # 36 KiB, resident: j5's seed takes 20,426 bytes, with j5b's club leaders and records 35,4xx
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16), (OWNER, "read_only", RO_SIZE, 16))

UI_LABEL = "Franchise History screen, box scores and game logs"
BUILD_CAPTION = UI_LABEL
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the game keeps no season history, records or award history, and a played "
    "game's box score is gone once the game ends. Patch: ESPN.com gets a TEAM HISTORY row: every club's seasons, "
    "club records, all-time leaders, the NFL record book, the season awards and the Hall of Fame, starting from real "
    "NFL history (2002 to 2025) with everything made in your franchise added and marked NEW. Black/White change the "
    "page, L/R the team. On the Schedule, X opens the box score of a played game (the score by quarter for every game, "
    "full team and player stats for your team's games), and with the Player Card honors option the card gets a game log "
    "page. Your franchise's own history needs the option Franchise history and records (it keeps that data in your "
    "saves); without it the real history and the scores by quarter still show.")

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_history_2026.json"
LEADERS_PATH = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_franchise_leaders_2026.json"
LEADERS_SCHEMA = "nfl2k5_franchise_leaders/v1"

# ---- retail anchors ------------------------------------------------------------------------------------------------
ESPN_DESCRIPTOR = 0x00525664
ESPN_ROWS_FIELD = ESPN_DESCRIPTOR + 0x10
ESPN_ROWS = 0x005253C0
ESPN_ROW_SIZE = 0x34
ESPN_RETAIL_ROWS = 12
STANDINGS_DESCRIPTOR = 0x0054CEA0
LAYOUT_LEAGUE_NEWS_COMMON = 0x00EAA50C       # "league_news_common" (Team Standings' layout)
HANDLER_NO_LIST = 0x000F3DA0                 # Team Standings' handler: B goes back (descriptor flag 0x10)
BACKGROUND_EVENT = 0x0006C080                # Team Standings' event-9 action
FRAME = (0x02400044, 0x018D0052)
FLAGS = 0x15                                 # Team Standings' flags
EVENT_ENTER, EVENT_INPUT, EVENT_DRAW, EVENT_BACKGROUND = 1, 6, 8, 9
SCHEDULE_SITE = 0x0024D2E5

SITE_TABLE = (
    # (label, VA, retail bytes, kind): "rows" = the descriptor's row-table pointer; "call" = call rel32 + nop
    ("espn_rows", ESPN_ROWS_FIELD, struct.pack("<I", ESPN_ROWS), "rows"),
    ("schedule_input", SCHEDULE_SITE, bytes.fromhex("f7c320020000"), "call"),
)

# Dependencies the runtime calls or reads, pinned by SHA-256 of their retail bytes (sites masked).
GUARDS = (
    ("espn descriptor", ESPN_DESCRIPTOR, 0x2C),
    ("espn rows", ESPN_ROWS, ESPN_ROW_SIZE * (ESPN_RETAIL_ROWS + 1)),
    ("standings descriptor", STANDINGS_DESCRIPTOR, 0x2C),
    ("layout name", LAYOUT_LEAGUE_NEWS_COMMON, 0x26),
    ("menu dispatcher", 0x0006E4E0, 0x118),
    ("screen push", 0x0006E390, 0x63),
    ("no-list handler", HANDLER_NO_LIST, 0xA6),
    ("background event", BACKGROUND_EVENT, 0x1C),
    ("schedule input", 0x0024D1B0, 0x280),
    ("schedule selected game", 0x0024B680, 0x83),
    ("menu legend", 0x000F35A0, 0x2A),
    ("pads", 0x000709B0, 0xC0),
    ("cursor sound", 0x0014D390, 0x24),
    ("text init", 0x00046920, 0x16),
    ("text font", 0x000469B0, 0xD),
    ("text align", 0x00046A00, 0x4),
    ("text position", 0x00046A70, 0x40),
    ("text colour", 0x00046B50, 0x4),
    ("text style", 0x00046B60, 0x4),
    ("text width", 0x00046C50, 0x10),
    ("text draw", 0x000F1C70, 0x10),
    ("font table", 0x000EF850, 0x8),
    ("rectangle", 0x0006BBE0, 0x25),
    ("club by index", 0x000C4C50, 0x2E),
    ("club index", 0x000C4CA0, 0x40),
    ("club count", 0x000C6430, 0x30),
    ("cell scores", 0x000C5110, 0x76),
)
# bytes inside guarded spans that other patches legitimately change: (VA, size): the regular-season length byte read by
# the schedule accessors is outside every span; none so far.
VARIABLE_BYTES = ()

# ---- the read-only block --------------------------------------------------------------------------------------------
RO_MAGIC = b"HSR1"
LOG_MAGIC = b"HSX1"
RO_FIELDS = ("magic", "size", "clubs", "seasons", "season_count", "awards", "hof", "hof_count", "book", "book_count",
             "club_records", "leaders", "names", "names_size", "seed_last", "box_descriptor", "box_legend")
RO_HEADER = 0x80
AWARDS = ("mvp", "opoy", "dpoy", "oroy", "droy", "cpoy", "coy", "sbmvp")
CATEGORIES = ("passing_yards", "passing_td", "completions", "rushing_yards", "rushing_td", "receptions",
              "receiving_yards", "receiving_td", "sacks_half", "interceptions", "tackles", "forced_fumbles")
LEADER_CATEGORIES = ("passing_yards", "passing_td", "rushing_yards", "rushing_td", "receptions", "receiving_yards",
                     "receiving_td", "sacks_half", "interceptions", "tackles")
CATEGORY_ALIASES = {"pass_yds": "passing_yards", "pass_td": "passing_td", "rush_yds": "rushing_yards",
                    "rush_td": "rushing_td", "rec": "receptions", "rec_yds": "receiving_yards",
                    "rec_td": "receiving_td", "sacks": "sacks_half", "int": "interceptions", "ints": "interceptions",
                    "def_int": "interceptions", "ff": "forced_fumbles", "comp": "completions",
                    "passing_yds": "passing_yards", "rushing_yds": "rushing_yards", "receiving_yds": "receiving_yards"}
KINDS = ("game", "season", "career")
PLAYOFFS = {"": 0, "missed": 0, "none": 0, "lost_wild_card": 1, "lost_divisional": 2, "lost_conference": 3,
            "lost_super_bowl": 4, "won_super_bowl": 5, "champion": 5}
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
POSITION_ALIASES = {"RB": "HB", "LB": "OLB", "MLB": "ILB", "S": "SS", "SAF": "SS", "DB": "CB", "OT": "T", "OG": "G",
                    "OL": "G", "NT": "DT", "DL": "DT", "EDGE": "DE", "PK": "K", "KR": "WR", "PR": "WR", "WB": "HB",
                    "E": "TE", "B": "HB", "BB": "FB", "TB": "HB", "WR/KR": "WR"}
# franchise key (the seed's club) -> the abbreviations the game may use for it (newest first)
CLUB_ALIASES = {"LA": ("LAR", "LA", "STL"), "LAR": ("LAR", "LA", "STL"), "LAC": ("LAC", "SD"), "LV": ("LV", "OAK"),
                "JAX": ("JAX", "JAC"), "WAS": ("WAS", "WSH"), "ARI": ("ARI", "ARZ"), "HOU": ("HOU",),
                "NE": ("NE",), "NO": ("NO",), "GB": ("GB",), "KC": ("KC",), "SF": ("SF",), "TB": ("TB",)}
CLUBS_2026 = ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX",
              "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN",
              "WAS")


class HistoryScreenError(ValueError):
    """Unsupported executable, foreign or mixed installation, or a seed that does not fit."""


def _require(condition, message):
    if not condition:
        raise HistoryScreenError(message)


def short_name(name: str) -> str:
    """'Patrick Mahomes' -> 'P. MAHOMES' (the screen's style, like the champions page; 20 characters at most)."""

    parts = [p for p in str(name or "").replace(",", " ").split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0].upper()[:20]
    first, last = parts[0], " ".join(parts[1:])
    text = f"{first[0].upper()}. {last.upper()}"
    return "".join(c if 32 <= ord(c) < 127 else "?" for c in text)[:20]


def position_code(text) -> int:
    if text is None:
        return 0xFF
    key = str(text).strip().upper()
    key = POSITION_ALIASES.get(key, key)
    return POSITIONS.index(key) if key in POSITIONS else 0xFF


def category_key(text) -> str:
    key = str(text or "").strip().lower()
    return CATEGORY_ALIASES.get(key, key)


def category_value(category: str, value) -> int:
    """Sacks are kept in half sacks (the game's own unit); everything else as given."""

    number = float(value or 0)
    return int(round(number * 2)) if category == "sacks_half" else int(round(number))


def club_key(text: str) -> str:
    key = str(text or "").strip().upper()
    for franchise, aliases in CLUB_ALIASES.items():
        if key in aliases:
            return "LA" if franchise == "LAR" else franchise
    return key


class _Names:
    """ASCII name pool: offset 0 is reserved (an empty name)."""

    def __init__(self):
        self.data = bytearray(b"\0")
        self.at = {}

    def add(self, text: str) -> int:
        text = short_name(text) if text and not text.isupper() else (text or "")
        if not text:
            return 0xFFFF
        if text not in self.at:
            _require(len(self.data) + len(text) + 1 < 0xFFFF, "name pool full")
            self.at[text] = len(self.data)
            self.data += text.encode("ascii", "replace") + b"\0"
        return self.at[text]


def _holder(row: Mapping) -> Mapping:
    """The first listed holder of a seed record (ties list every holder; the screen names the first)."""
    holders = row.get("holders") or ()
    return holders[0] if holders and isinstance(holders[0], Mapping) else row


def _year(value) -> int:
    try:
        return int(str(value)[:4]) if value not in (None, "") else 0
    except ValueError:
        return 0


def _row_value(row: Mapping, category: str) -> int:
    """A row's value in the footer's units: rows from j5b-leaders carry them already (``units: footer``, half sacks)."""

    if row.get("units") == "footer":
        return int(row.get("value") or 0)
    return category_value(category, row.get("value", 0))


def with_leaders(seed: Mapping | None, leaders: Mapping | None) -> dict | None:
    """The seed document with j5b-leaders' document (``nfl2k5_franchise_leaders/v1``) as its ``club_records`` (the
    club's season and game record holders) and ``club_leaders`` (career top three); j5b's checked lists replace any the
    seed carries. j5b's values are already in the footer's units (sacks in half sacks), so its rows are marked
    ``units: footer``. Either document may be None."""

    if not leaders:
        return dict(seed) if seed is not None else None
    _require(isinstance(leaders, Mapping) and leaders.get("schema") == LEADERS_SCHEMA and
             isinstance(leaders.get("clubs"), Mapping), f"not a {LEADERS_SCHEMA} document")
    out = dict(seed or {})
    records, career = [], []
    for code, club in sorted(leaders["clubs"].items()):
        if not isinstance(club, Mapping):
            continue
        for kind in ("season", "game"):
            for category, rows in sorted((club.get(kind) or {}).items()):
                for row in (rows or ())[:1]:
                    records.append({"club": code, "category": category, "kind": kind, "name": row.get("name", ""),
                                    "value": row.get("value", 0), "year": row.get("season"),
                                    "position": row.get("position"), "units": "footer"})
        for category, rows in sorted((club.get("career") or {}).items()):
            for row in rows or ():
                if 1 <= int(row.get("rank") or 0) <= 3:
                    career.append({"club": code, "category": category, "rank": int(row["rank"]),
                                   "name": row.get("name", ""), "value": row.get("value", 0),
                                   "position": row.get("position"), "units": "footer"})
    out["club_records"], out["club_leaders"] = records, career
    return out


def _seed_tables(seed: Mapping | None):
    """The seed document (j5-seed ``nfl2k5_history_seed/v1``) as plain lists for the block.

    Seasons: ``seasons[].teams[]`` (club = today's abbreviation, playoffs one of ``playoff_codes``); awards:
    ``awards.winners[]`` (or a plain list); NFL records: ``nfl_records[]`` (category, scope game/season/career, holders);
    Hall of Fame: ``hall_of_fame.members[]`` (or a plain list); club records and leaders (j5b-leaders): ``club_records[]``
    and ``club_leaders[]`` when the document carries them. Categories outside the footer's (points, field goals) are
    skipped: the screen shows what the franchise also keeps."""

    seed = seed or {}
    seasons_by_club = {key: [] for key in CLUBS_2026}
    for season in seed.get("seasons", ()) or ():
        year = int(season.get("season", 0))
        for team in season.get("teams", ()) or ():
            key = club_key(team.get("club"))
            if key not in seasons_by_club:
                continue
            playoff = str(team.get("playoffs") or "").lower().replace(" ", "_")
            seasons_by_club[key].append(dict(
                year=year, w=int(team.get("w", 0)), l=int(team.get("l", 0)), t=int(team.get("t", 0)),
                place=int(team.get("place", 0) or 0), playoff=PLAYOFFS.get(playoff, 0),
                coach=str(team.get("coach") or ""), label=str(team.get("label") or key)))
    for rows in seasons_by_club.values():
        rows.sort(key=lambda r: -r["year"])
    awards = {a: [] for a in AWARDS}
    award_rows = seed.get("awards", ())
    if isinstance(award_rows, Mapping):
        award_rows = award_rows.get("winners", ())
    for row in award_rows or ():
        award = str(row.get("award", "")).lower().replace("sb_mvp", "sbmvp")
        if award not in awards:
            continue
        for winner in (row.get("winners") or ())[:1]:      # shared awards: the first listed winner
            awards[award].append(dict(year=int(row.get("season", 0)), name=winner.get("name", ""),
                                      pos=position_code(winner.get("position")), club=club_key(winner.get("club"))))
    for rows in awards.values():
        rows.sort(key=lambda r: -r["year"])
    book = []
    for row in seed.get("nfl_records", ()) or ():
        category, kind = category_key(row.get("category")), row.get("kind") or row.get("scope")
        if category not in CATEGORIES or kind not in KINDS:
            continue
        holder = _holder(row)
        year = 0 if kind == "career" else _year(holder.get("season") or holder.get("year") or row.get("year"))
        book.append(dict(category=CATEGORIES.index(category), kind=KINDS.index(kind), name=holder.get("name", ""),
                         value=category_value(category, row.get("value", 0)), year=year,
                         club=club_key(holder.get("club") or row.get("club")),
                         pos=position_code(holder.get("position") or row.get("position"))))
    book.sort(key=lambda r: (r["category"], r["kind"]))
    hof = []
    members = seed.get("hall_of_fame", ())
    if isinstance(members, Mapping):
        members = members.get("members", ())
    for row in members or ():
        hof.append(dict(year=int(row.get("year", row.get("class", 0)) or 0), name=row.get("name", ""),
                        pos=position_code(row.get("position")), club=club_key(row.get("club") or row.get("team"))))
    hof.sort(key=lambda r: -r["year"])
    club_records = {key: [] for key in CLUBS_2026}
    for row in seed.get("club_records", ()) or ():
        key = club_key(row.get("club"))
        category, kind = category_key(row.get("category")), row.get("kind") or row.get("scope")
        if key in club_records and category in CATEGORIES and kind in ("game", "season"):
            holder = _holder(row)
            club_records[key].append(dict(category=CATEGORIES.index(category), kind=KINDS.index(kind),
                                          name=holder.get("name", ""), value=_row_value(row, category),
                                          year=_year(holder.get("season") or holder.get("year") or row.get("year")),
                                          pos=position_code(holder.get("position") or row.get("position"))))
    leaders = {key: [] for key in CLUBS_2026}
    for row in seed.get("club_leaders", ()) or ():
        key = club_key(row.get("club"))
        category = category_key(row.get("category"))
        if key in leaders and category in LEADER_CATEGORIES and 1 <= int(row.get("rank", 0)) <= 3:
            leaders[key].append(dict(category=LEADER_CATEGORIES.index(category), rank=int(row["rank"]) - 1,
                                     name=row.get("name", ""), value=_row_value(row, category),
                                     pos=position_code(row.get("position"))))
    return seasons_by_club, awards, book, hof, club_records, leaders


def load_seed(path: Path | str | None = None, leaders_path: Path | str | None = None):
    """The pinned seed documents as one (j5-seed's history, plus j5b-leaders' club leaders and records when the tree
    carries them: ``with_leaders``), or None when this build carries neither."""

    path, leaders_path = Path(path) if path else SEED_PATH, Path(leaders_path) if leaders_path else LEADERS_PATH
    seed = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    leaders = json.loads(leaders_path.read_text(encoding="utf-8")) if leaders_path.is_file() else None
    return with_leaders(seed, leaders) if seed is not None or leaders is not None else None


def _utf16(text: str) -> bytes:
    return (text + "\0").encode("utf-16le")


def build_ro(ro_va: int, code_va: int, item_rows: bytes, seed: Mapping | None = None) -> bytes:
    """The read-only block at ``ro_va``: header, the ESPN.com rows (``item_rows``: the image's own twelve rows, read at
    install) plus TEAM HISTORY, the two descriptors with their event and action lists, the UTF-16 texts the game reads,
    and the seed tables the runtime reads (layouts in ``tools/nfl2k5_history_screen/runtime.c``)."""

    _require(len(item_rows) == ESPN_ROW_SIZE * ESPN_RETAIL_ROWS, "the ESPN.com rows are twelve 52-byte rows")
    at = {name: code_va + offset for name, offset in runtime.LABELS.items()}
    out = bytearray(RO_HEADER)
    fields = dict.fromkeys(RO_FIELDS, 0)

    def align(n=4):
        out.extend(bytes((-len(out)) % n))

    def put(data: bytes, n=4) -> int:
        align(n)
        offset = len(out)
        out.extend(data)
        return offset

    title = put(_utf16("Team History"))
    label = put(_utf16("Team History"))
    box_title = put(_utf16("Box Score"))
    fields["box_legend"] = put(_utf16("for Box Score"))
    # action lists: 36-byte entries {type, fn, ...}, type 1 = call fn(ecx = manager), type 0 ends the list
    def actions(*functions) -> int:
        data = b"".join(struct.pack("<I I 28x", 1, fn) for fn in functions) + bytes(36)
        return put(data)

    def events(pairs) -> int:
        data = b"".join(struct.pack("<II", event, ro_va + offset) for event, offset in pairs) + bytes(8)
        return put(data)

    hist_events = events(((EVENT_BACKGROUND, actions(BACKGROUND_EVENT)), (EVENT_ENTER, actions(at["hist_enter"])),
                          (EVENT_INPUT, actions(at["hist_input"])), (EVENT_DRAW, actions(at["hist_draw"]))))
    box_events = events(((EVENT_BACKGROUND, actions(BACKGROUND_EVENT)), (EVENT_ENTER, actions(at["box_enter"])),
                         (EVENT_INPUT, actions(at["box_input"])), (EVENT_DRAW, actions(at["box_draw"]))))

    def descriptor(title_offset, events_offset) -> int:
        return put(struct.pack("<11I", ro_va + title_offset, ro_va + events_offset, HANDLER_NO_LIST, 0, 0, 0,
                               LAYOUT_LEAGUE_NEWS_COMMON, 0, *FRAME, FLAGS))

    hist_descriptor = descriptor(title, hist_events)
    fields["box_descriptor"] = descriptor(box_title, box_events)
    # the ESPN.com rows: the retail twelve, TEAM HISTORY (type 0 = push the descriptor at +8), the end marker (type 3),
    # right after the card's game-log record {"HSX1", flip, rows, bio} that the champions owner finds through the rows
    # pointer (the rows must not start in the first 16 bytes of a page: it reads the record from the rows' own page)
    align(16)
    if (ro_va + len(out) + 16) & 0xFFF < 16:
        out.extend(bytes(16))
    put(LOG_MAGIC + struct.pack("<3I", at["hist_card_flip"], at["hist_card_rows"], at["hist_card_bio"]))
    row = struct.pack("<13I", 0, ro_va + label, ro_va + hist_descriptor, *([0] * 10))
    rows = put(item_rows + row + struct.pack("<I", 3) + bytes(ESPN_ROW_SIZE - 4))
    _require(rows >= 16 and (ro_va + rows) & 0xFFF >= 16 and out[rows - 16:rows - 12] == LOG_MAGIC, "game-log record")
    names = _Names()
    seasons_by_club, awards, book, hof, club_records, leaders = _seed_tables(seed)
    # clubs: 32 x {3 aliases x 4 ASCII, u16 first season line, u16 count}
    club_table, season_lines = bytearray(), bytearray()
    for key in CLUBS_2026:
        aliases = CLUB_ALIASES.get(key, (key,))[:3]
        packed = b"".join(a.encode("ascii")[:3].ljust(4, b"\0") for a in aliases).ljust(12, b"\0")
        rows_of = seasons_by_club[key]
        club_table += packed + struct.pack("<HH", len(season_lines) // 10, len(rows_of))
        for s in rows_of:
            season_lines += struct.pack("<HBBBBHBB", s["year"], min(s["w"], 255), min(s["l"], 255), min(s["t"], 255),
                                        (min(s["place"], 15)) | (s["playoff"] & 15) << 4, names.add(s["coach"]), 0, 0)
    fields["clubs"] = put(bytes(club_table))
    fields["seasons"] = put(bytes(season_lines))
    fields["season_count"] = len(season_lines) // 10
    key_index = {k: i for i, k in enumerate(CLUBS_2026)}

    def club_byte(key):
        return key_index.get(key, 0xFF)

    # awards: 8 x {u16 first, u16 count} (32 bytes), then 6-byte entries {u16 year, u16 name, u8 pos, u8 club}
    award_head, award_rows = bytearray(), bytearray()
    for award in AWARDS:
        award_head += struct.pack("<HH", len(award_rows) // 6, len(awards[award]))
        for r in awards[award]:
            award_rows += struct.pack("<HHBB", r["year"], names.add(r["name"]), r["pos"] if award != "coy" else 0xFF,
                                      club_byte(r["club"]))
    fields["awards"] = put(bytes(award_head) + bytes(award_rows))
    hof_rows = b"".join(struct.pack("<HHBB", r["year"], names.add(r["name"]), r["pos"], club_byte(r["club"]))
                        for r in hof)
    fields["hof"], fields["hof_count"] = put(hof_rows), len(hof)
    book_rows = b"".join(struct.pack("<BBHIHBB", r["category"], r["kind"], names.add(r["name"]), r["value"], r["year"],
                                     club_byte(r["club"]), r["pos"]) for r in book)
    fields["book"], fields["book_count"] = put(book_rows), len(book)
    # club records: 32 x {u16 first, u16 count} (128 bytes), then 12-byte entries (the book's shape, club = the club)
    head, body = bytearray(), bytearray()
    for i, key in enumerate(CLUBS_2026):
        rows_of = club_records[key]
        head += struct.pack("<HH", len(body) // 12, len(rows_of))
        for r in rows_of:
            body += struct.pack("<BBHIHBB", r["category"], r["kind"], names.add(r["name"]), r["value"], r["year"], i,
                                r["pos"])
    fields["club_records"] = put(bytes(head) + bytes(body)) if any(club_records.values()) else 0
    head, body = bytearray(), bytearray()
    for key in CLUBS_2026:
        rows_of = leaders[key]
        head += struct.pack("<HH", len(body) // 10, len(rows_of))
        for r in rows_of:
            body += struct.pack("<BBHIBB", r["category"], r["rank"], names.add(r["name"]), r["value"], r["pos"], 0)
    fields["leaders"] = put(bytes(head) + bytes(body)) if any(leaders.values()) else 0
    fields["names"] = put(bytes(names.data))
    fields["names_size"] = len(names.data)
    fields["seed_last"] = max((s["year"] for rows_of in seasons_by_club.values() for s in rows_of), default=0)
    fields["magic"] = struct.unpack("<I", RO_MAGIC)[0]
    fields["size"] = len(out)
    _require(len(out) <= RO_SIZE, f"the history block needs {len(out)} bytes; its allocation has {RO_SIZE}")
    struct.pack_into("<%dI" % len(RO_FIELDS), out, 0, *(fields[f] for f in RO_FIELDS))
    struct.pack_into("<II", out, RO_HEADER - 8, rows, hist_descriptor)   # for the installer and the tests
    return bytes(out).ljust(RO_SIZE, b"\0")


def build_ro_fitting(ro_va: int, code_va: int, item_rows: bytes, seed: Mapping | None = None):
    """``build_ro``; when the seed does not fit the block, the club leaders and then the club records are left out (the
    footer's seed image can still carry them). Returns (content, the parts left out)."""

    seed = dict(seed or {})
    dropped = []
    for part in (None, "club_leaders", "club_records"):
        if part:
            if not seed.get(part):
                continue
            seed[part] = []
            dropped.append(part)
        try:
            return build_ro(ro_va, code_va, item_rows, seed), dropped
        except HistoryScreenError as exc:
            if "the history block needs" not in str(exc):
                raise
    return build_ro(ro_va, code_va, item_rows, seed), dropped


def ro_rows_offset(content: bytes) -> int:
    return struct.unpack_from("<I", content, RO_HEADER - 8)[0]


def ro_history_descriptor(content: bytes) -> int:
    return struct.unpack_from("<I", content, RO_HEADER - 4)[0]


def ro_field(content: bytes, name: str) -> int:
    return struct.unpack_from("<I", content, 4 * RO_FIELDS.index(name))[0]


# ---- the franchise footer (job j23-footer, nfl2k5_franchise_extension, envelope 1) ----------------------------------
# The runtime reads blocks 1 seasons (awards and head coaches inside the season records), 2 totals, 3 records, 4 leaders,
# 5 hall and 6 box scores, version 1, at the offsets and sizes the body's directory gives (layouts: the *_LAYOUT texts
# of nfl2k5_franchise_extension). FOOTER_BLOCKS pins the ids, versions and minimum sizes the runtime checks.
FOOTER_MAGIC = b"2K5XTND1"
FOOTER_BLOCKS = {1: ("seasons", 18960), 2: ("totals", 528), 3: ("records", 9520), 4: ("leaders", 16176),
                 5: ("hall", 4624), 6: ("boxscores", 12304)}
FOOTER_OWNER_MODULE = "nfl2k5_franchise_footer"     # the native host (j23); its body-pointer word is linked here


def footer_pointer_va(payload: bytes) -> int:
    """The footer host's RW word holding the body address, when that owner is installed in ``payload``; else 0."""

    import importlib
    try:
        host = importlib.import_module(f"{__package__}.{FOOTER_OWNER_MODULE}")
    except ImportError:
        return 0
    try:
        return int(host.body_pointer_va(payload)) if host.status(payload) == "applied" else 0
    except (AttributeError, ValueError, KeyError, TypeError, struct.error):
        return 0


# ---- installation ---------------------------------------------------------------------------------------------------
def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def code_for(code_va: int, data_va: int, ro_va: int, xtnd_ptr_va: int = 0) -> bytes:
    """The owned RX content with the template's relocations applied, padded to CODE_SIZE with int3. ``xtnd_ptr_va`` is
    the footer owner's body-pointer word (0: no footer owner, the franchise parts read empty)."""

    symbols = {"code": code_va, "state": data_va, "ro": ro_va, "xtnd_ptr": xtnd_ptr_va}
    result = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "the history screen runtime exceeds its fixed budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def labels(code_va: int) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def sites(code_va: int, ro_va: int, rows_offset: int) -> list[tuple[str, int, bytes, bytes]]:
    at = labels(code_va)
    out = []
    for label, va, before, kind in SITE_TABLE:
        if kind == "rows":
            after = struct.pack("<I", ro_va + rows_offset)
        else:
            after = b"\xe8" + _rel32(va + 5, at["hist_schedule_hook"]) + b"\x90"
        out.append((label, va, before, after))
    return out


def _guard_digest(image: XbeImage, va: int, size: int, checked_sites) -> str:
    content = bytearray(image.read(va, size))
    for _label, address, before, _after in checked_sites:
        if va <= address and address + len(before) <= va + size:
            content[address - va:address - va + len(before)] = before
    for address, length in VARIABLE_BYTES:
        if va <= address and address + length <= va + size:
            content[address - va:address - va + length] = bytes(length)
    return hashlib.sha256(content).hexdigest()


_RETAIL_SITES = None


def _retail_sites():
    global _RETAIL_SITES
    if _RETAIL_SITES is None:
        _RETAIL_SITES = [(label, va, before, before) for label, va, before, _kind in SITE_TABLE]
    return _RETAIL_SITES


def guard_digests(payload: bytes) -> dict[str, str]:
    """The masked digests of every guarded span (used to pin GUARDS from the retail executable)."""

    image = XbeImage(payload)
    return {name: _guard_digest(image, va, size, _retail_sites()) for name, va, size in GUARDS}


def _check_guards(image: XbeImage) -> None:
    for name, va, size in GUARDS:
        _require(_guard_digest(image, va, size, _retail_sites()) == GUARD_PINS[name],
                 f"foreign history screen dependency: {name} ({va:#x})")


def allocations(payload: bytes) -> dict[str, dict]:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    found = {r["kind"]: r for r in rows}
    _require(len(rows) == 3 and set(found) == {"code", "data", "read_only"}
             and all((found[k]["size"], found[k]["align"]) == (size, align) for _o, k, size, align in REQUESTS),
             "foreign history screen allocation")
    return found


def _item_rows(image: XbeImage) -> bytes:
    return image.read(ESPN_ROWS, ESPN_ROW_SIZE * ESPN_RETAIL_ROWS)


def owned_state(payload: bytes):
    """-> ("retail" | "applied", allocations | None); anything else raises."""

    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocations(payload)
    _check_guards(image)
    if not found:
        _require(rdata.status(payload, _retail_sites()) == "retail", "history screen sites changed without an allocation")
        return "retail", None
    code_va, ro_va = found["code"]["va"], found["read_only"]["va"]
    code = image.read(code_va, CODE_SIZE)
    ro = image.read(ro_va, RO_SIZE)
    if code == b"\xcc" * CODE_SIZE:
        _require(rdata.status(payload, _retail_sites()) == "retail", "history screen sites changed with an empty allocation")
        return "retail", found
    _require(ro[:4] == RO_MAGIC, "foreign history screen block")
    rows = ro_rows_offset(ro)
    _require(0 < rows < RO_SIZE and ro[rows:rows + ESPN_ROW_SIZE * ESPN_RETAIL_ROWS] == _item_rows(image),
             "the history screen's ESPN.com rows differ from the executable's")
    xtnd = struct.unpack_from("<I", ro, RO_HEADER - 12)[0]
    _require(code == code_for(code_va, found["data"]["va"], ro_va, xtnd), "foreign history screen code")
    _require(rdata.status(payload, sites(code_va, ro_va, rows)) == "applied", "mixed history screen sites")
    return "applied", found


def status(payload: bytes) -> str:
    try:
        return owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    edits = [(label, va, before, before) for label, va, before, _kind in SITE_TABLE]
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def install(payload: bytes, seed: Mapping | None = None, xtnd_ptr_va: int = 0) -> tuple[bytes, Mapping[str, object]]:
    """Allocate (a late owner), fill the code and the read-only block, patch the two sites. Idempotent."""

    state, found = owned_state(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": len(runtime.CODE),
              "owner_bytes": CODE_SIZE + DATA_SIZE + RO_SIZE}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if not found:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocations(payload)
    _require(bool(found), "reserve the history screen allocation first")
    image = XbeImage(payload)
    code_va, data_va, ro_va = found["code"]["va"], found["data"]["va"], found["read_only"]["va"]
    content, dropped = build_ro_fitting(ro_va, code_va, _item_rows(image), seed)
    ro = bytearray(content)
    struct.pack_into("<I", ro, RO_HEADER - 12, xtnd_ptr_va)
    installed, ro_receipt = space.install_read_only(payload, OWNER, bytes(ro))
    installed, code_receipt = space.install_code(installed, OWNER, code_for(code_va, data_va, ro_va, xtnd_ptr_va))
    result, site_receipt = rdata.apply(installed, sites(code_va, ro_va, ro_rows_offset(ro)), OWNER)
    _require(status(result) == "applied", "history screen postcondition failed")
    changed = sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before))
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "read_only_install": ro_receipt, "code_va": hex(code_va), "data_va": hex(data_va),
                    "ro_va": hex(ro_va), "footer_pointer": hex(xtnd_ptr_va), "changed_bytes": changed,
                    "seeded": bool(seed), "ro_bytes": ro_field(bytes(ro), "size"), "seed_parts_left_out": dropped,
                    "sites": [{"label": label, "va": hex(va), "size": len(b)}
                              for label, va, b, _after in sites(code_va, ro_va, ro_rows_offset(ro))]}


def main(argv=None) -> int:
    """python3 -m mod_editor.core.nfl2k5_history_screen {status,apply} source.xbe [output.xbe] [--seed seed.json]"""

    import argparse

    parser = argparse.ArgumentParser(description=UI_LABEL)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
            p.add_argument("--seed", type=Path, default=None, help="real-history seed JSON (default: the built-in one)")
    args = parser.parse_args(argv)
    _require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "apply":
        result, receipt = install(payload, seed=load_seed(args.seed), xtnd_ptr_va=footer_pointer_va(payload))
        with args.output.open("xb") as stream:
            stream.write(result)
    else:
        receipt = {"status": status(payload), "owner": OWNER, "experimental": True}
    print(json.dumps(receipt, indent=2, default=str))
    return 0


# pinned from the retail executable (sha 73105b17) by guard_digests(); see tests/mod_editor/test_b780_j4_history_screen.py
GUARD_PINS: dict[str, str] = {
    "espn descriptor": "ff6dc94b81971151535e1e8835786604906c8477b696d8e175f3a54536fb1b27",
    "espn rows": "e0cf9a80df2c72143bbbe62f81b1e6c3c76bcb14f5c9488e107c2da4c2cc114e",
    "standings descriptor": "7a5a5df9ffc7b5b16f9eb3edef6db182f99575f7a452be3c720ec9a870b5c160",
    "layout name": "454ed29c8fcc520e1893024aa4a65700b0ec108a72e3f863eec1fcbe5a20b638",
    "menu dispatcher": "7c2dc845c2228a249def67e8b3fe0b9c05f0badf2c233e34fd392a4833975bef",
    "screen push": "a7d71ca2d920861e3d0eb3da9eb1f9ff8a78c25ca6251b250d987c96a257a3e5",
    "no-list handler": "a8af712896a94ba391ef26504ff7007719bf830ddf9b6d00b3232fa672e02fdc",
    "background event": "c1263c61f0e367774725cb4b0296d9dfc6b4235c7d277339bf08f7f45d78b9ac",
    "schedule input": "f06029efbc8b8adc97a4b73d16c1d36734a8e08c25051f78eaf6fe58afd434c6",
    "schedule selected game": "ec90c74a01a4d2beeb038b6521467c7622f63ad6e2320d7e51c72018a738edef",
    "menu legend": "49dc6d6961ea1982d8556df39afee5f00a2b1cbf3bf222d8d677920e058c0a80",
    "pads": "b7f411a8a6c4f00286a7df5e5238987e34a5c283632a89a27a238b75519a0ef6",
    "cursor sound": "f3e7a1b8abb6220d082e866b736c133189f3bf8a20a8b213ba694bf4c3355168",
    "text init": "715bb82c65136312646957ed6be69fef751004cc7d44f88d321e3c4fd01129e2",
    "text font": "df8e500f21e4fa0b671d89bca38e9934bda6334fe78b372e232d4be9c78d290a",
    "text align": "ed9f6a32e4498f2cf61fbd7a2e9e3cbf505eff408f8aaa0a4a1e0c7ad34271f4",
    "text position": "609c0623574545c3cd4d670b7fa88fc8d2645e4708fd5c09afed1c2c97f92633",
    "text colour": "d3487a2010908a5c9425b41cd1561e0ab67114b078cf02d794fa438402749070",
    "text style": "1cb932b932d3f105267412a55db472ff87ca8d7bca2b5c5e44414a7d435b3b3d",
    "text width": "a4811f90dee5e4196749b5faf93acb5b0a597f9cd633294ca07276d451ee897a",
    "text draw": "65f6ef40cd75472c38615e4ecf846fc3b3f8bbf6744062b29f2befcd66ade68f",
    "font table": "2b749cc28858f48edd6c85faf49916486d941f55a861696947a0ab14cb1946e4",
    "rectangle": "aa8f1c6b0ebe6c948d4f5f312bf1dc05a83bc7104c1dfa946a70168f5e072a81",
    "club by index": "f421059ce4ea9ac33e94e9e1541b8fcbbd4c7b28da07038136d5586a526b1dcf",
    "club index": "b9492612c41c8ebe2f6a64de893f9b72e03124f3738564c3c4de9678a5c48a53",
    "club count": "b954682454bbc2d4da9b59fa5a1212d82a45f0507204723663cf6a5bb4bc8c34",
    "cell scores": "02f2a4cd1ddb47cf01d772c45a8deb4c9220724049e09fe3033ff521f1ca1914",
}

__all__ = ["OWNER", "REQUESTS", "UI_LABEL", "HELP_TEXT", "BUILD_CAPTION", "HistoryScreenError", "build_ro", "code_for",
           "sites", "labels", "allocations", "install", "status", "reservations", "guard_digests", "owned_state",
           "FOOTER_BLOCKS", "footer_pointer_va", "load_seed", "with_leaders", "short_name"]


if __name__ == "__main__":
    raise SystemExit(main())
