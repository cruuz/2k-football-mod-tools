#!/usr/bin/env python3
"""Build data/nfl2k5_history_2026.json: the real NFL history the franchise History screen starts from (job j5-seed, b780).

The franchise History screen (ESPN.com > TEAM HISTORY, research ``b780_r4-records_RESEARCH.md``) shows real seasons 2002
to 2025 before the first franchise season, so a new franchise does not open on an empty page. This builder produces that
read-only seed, and every value in it comes from a pinned source:

* **seasons**: one row per club per season 2002..2025 (W-L-T, points for/against, division and conference records,
  division finish, playoff result, head coach, the club's name that year) computed from the nflverse ``games.csv``
  (CC-BY 4.0), pinned to one commit of ``nflverse/nfldata`` and its SHA-256, plus a digest of exactly the rows used.
  The division finish applies the NFL's written tie-break procedure to the game scores; every row is then checked
  against the final division standings Wikipedia keeps for each season (192 pinned template revisions).
* **awards**: the AP award lists on Wikipedia, each at a fixed revision whose text is pinned by SHA-256.
* **nfl_records / nfl_career_leaders**: the NFL record book and career leader lists on Wikipedia (pinned revisions),
  cross-checked against nflverse player statistics for every record set after 1998.
* **hall_of_fame**: the Pro Football Hall of Fame inductee list on Wikipedia (pinned revision, complete through the
  Class of 2026).
* **pending_candidates**: real players retired since 2015 and not inducted, with pinned honors counts.

Rules the tests and the screen rely on are written into the output under ``rules``. Development tool: the Studio only
reads the generated JSON. Network is needed on a cache miss only; every text is verified against its pinned digest
before anything is parsed.

Usage:
  python3 tools/b780_history_seed.py --games games.csv [--cache DIR] [--out PATH]
  python3 tools/b780_history_seed.py --check            # rebuild in memory and compare with the committed file
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nfl2k5_history_2026.json"
SCHEMA = "nfl2k5_history_seed/v1"
BASE_YEAR = 2026
FIRST_SEASON, LAST_SEASON = 2002, 2025
USER_AGENT = "2k5-mod-studio-history-seed/1.0 (https://github.com/cruuz/2k-football-mod-tools; data builder)"

# ---------------------------------------------------------------------------------------------------------------------
# Pinned sources
# ---------------------------------------------------------------------------------------------------------------------
# nflverse/nfldata, file data/games.csv at one commit. The raw URL below is immutable (a commit, not a branch).
NFLVERSE_GAMES = {
    "title": "nflverse games.csv (every NFL game since 1999, scores, coaches, game types)",
    "publisher": "nflverse",
    "license": "CC-BY-4.0",
    "repository": "https://github.com/nflverse/nfldata",
    "commit": "e28cf00d4fdffa262603191a0b339901d4a7efd0",
    "commit_time": "2026-10-17T17:05:13Z",
    "url": "https://raw.githubusercontent.com/nflverse/nfldata/e28cf00d4fdffa262603191a0b339901d4a7efd0/data/games.csv",
    "sha256": "a5181ec4974309828d1d58e6f881eb1d106ee85c15c038a51b6bdca7b7ee6cf5",
    "bytes": 2185207,
}

JSON_INLINE_LIMIT = 300


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def http_get(url: str, tries: int = 4) -> bytes:
    last = None
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except Exception as error:  # network hiccup or rate limit: wait and retry
            last = error
            time.sleep(1.5 * (attempt + 1))
    raise SystemExit(f"cannot read {url}: {last}")


# ---------------------------------------------------------------------------------------------------------------------
# JSON output: structure expanded, rows inline (readable diffs for ~3,000 short rows)
# ---------------------------------------------------------------------------------------------------------------------
def _flat(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def dumps(value: Any, indent: int = 0) -> str:
    """JSON with the structure expanded and every short row on one line."""

    if isinstance(value, (dict, list)):
        if not value:
            return "{}" if isinstance(value, dict) else "[]"
        flat = _flat(value)
        if len(flat) <= JSON_INLINE_LIMIT:
            return flat
        pad = " " * (indent + 1)
        if isinstance(value, dict):
            items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent + 1)}" for k, v in value.items()]
            return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
        items = [f"{pad}{dumps(v, indent + 1)}" for v in value]
        return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------------------------------
# Wikitext: pinned pages, a small wikitable reader, plain-text cleaning
# ---------------------------------------------------------------------------------------------------------------------
def wiki_url(title: str, revision: int) -> str:
    return f"https://en.wikipedia.org/w/index.php?title={urllib.parse.quote(title.replace(' ', '_'))}&oldid={revision}"


class WikiSources:
    """Pinned Wikipedia revisions: ``pins`` maps key -> (title, revision, sha256); texts come from ``cache`` or the network."""

    def __init__(self, pins: dict[str, tuple[str, int, str]], cache: Path | None):
        self.pins, self.cache = pins, Path(cache) if cache else None
        self.used: set[str] = set()

    def text(self, key: str) -> str:
        title, revision, digest = self.pins[key]
        path = self.cache / f"{key}.wiki" if self.cache else None
        if path is not None and path.is_file():
            raw = path.read_bytes()
        else:
            raw = http_get(wiki_url(title, revision) + "&action=raw")
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        got = sha256_hex(raw)
        if got != digest:
            raise SystemExit(f"{key} ({title}, revision {revision}): the text read has digest {got}, the pin is {digest}")
        self.used.add(key)
        return raw.decode("utf-8")

    def describe(self, publisher: str = "Wikipedia") -> dict[str, dict]:
        return {k: {"title": self.pins[k][0], "url": wiki_url(self.pins[k][0], self.pins[k][1]), "revision": self.pins[k][1],
                    "sha256": self.pins[k][2], "publisher": publisher} for k in sorted(self.used)}


def _skip_balanced(text: str, start: int, open_: str, close: str) -> int:
    """Index just after the group opened at ``start`` (``open_`` is two characters long); the end of text if unbalanced."""

    depth, i = 0, start
    while i < len(text):
        if text.startswith(open_, i):
            depth += 1
            i += len(open_)
        elif text.startswith(close, i):
            depth -= 1
            i += len(close)
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def split_top(text: str, separators: tuple[str, ...]) -> list[str]:
    """Split on the separators outside [[links]], {{templates}} and <tags>."""

    parts, buf, i = [], [], 0
    while i < len(text):
        if text.startswith("[[", i):
            j = _skip_balanced(text, i, "[[", "]]")
            buf.append(text[i:j])
            i = j
        elif text.startswith("{{", i):
            j = _skip_balanced(text, i, "{{", "}}")
            buf.append(text[i:j])
            i = j
        else:
            for sep in separators:
                if text.startswith(sep, i):
                    parts.append("".join(buf))
                    buf = []
                    i += len(sep)
                    break
            else:
                buf.append(text[i])
                i += 1
    parts.append("".join(buf))
    return parts


def strip_templates(text: str, names: tuple[str, ...]) -> str:
    """Remove ``{{name ...}}`` groups (footnotes, citations) for the given lower-case template names."""

    out, i = [], 0
    while i < len(text):
        if text.startswith("{{", i):
            j = _skip_balanced(text, i, "{{", "}}")
            head = re.match(r"\{\{\s*([^|}\s][^|}]*?)\s*(?:[|}]|$)", text[i:j])
            if head and head.group(1).lower() in names:
                i = j
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


REF_TEMPLATES = ("efn", "efn-ua", "efn-lr", "refn", "sfn", "ref label", "note label", "sup", "rp", "cite web", "cite news",
                 "cite book", "cite journal", "citation", "citation needed", "cn", "fact", "clarify", "when", "dead link",
                 "cbignore", "ref", "reflist", "notelist", "failed verification", "nbsp", "snd", "better source needed")
ENTITIES = {"&ndash;": "–", "&mdash;": "—", "&nbsp;": " ", "&amp;": "&", "&quot;": '"', "&#39;": "'", "&apos;": "'",
            "&minus;": "-", "&thinsp;": " ", "&lt;": "<", "&gt;": ">"}
ARG_TEMPLATES = ("nowrap", "center", "centre", "small", "big", "nobr", "nowrap2", "sort", "abbr", "hs", "bold", "strong", "nts")


def strip_markup(text: str) -> str:
    """Wikitext cell -> plain text. Footnotes, citations, comments, tags and link targets are dropped; labels stay."""

    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref\b[^>/]*/>", "", text)
    text = re.sub(r"<ref\b[^>]*>.*?</ref>", "", text, flags=re.S)
    text = strip_templates(text, REF_TEMPLATES)
    text = re.sub(r"\[\[(?:File|Image|Category):[^\]]*\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", text)

    def sortname(m: re.Match) -> str:
        return f"{m.group(1).strip()} {m.group(2).strip()}".strip()
    text = re.sub(r"\{\{\s*sortname\s*\|\s*([^|}]*)\|\s*([^|}]*)(?:\|[^}]*)?\}\}", sortname, text, flags=re.I)
    text = re.sub(r"\{\{\s*(?:NFL year|nfly)\s*\|\s*(\d{4})\s*\|\s*(\d{4})[^}]*\}\}", "\\1\u2013\\2", text, flags=re.I)
    text = re.sub(r"\{\{\s*(?:NFL year|nfly)\s*\|\s*(\d{4})[^}]*\}\}", r"\1", text, flags=re.I)
    text = re.sub(r"\{\{\s*(?:dagger|double-dagger)\s*\}\}", "\u2020", text, flags=re.I)
    text = re.sub(r"\{\{\s*winpct\s*\|[^}]*\}\}", "", text, flags=re.I)
    text = re.sub(r"\{\{\s*(?:unbulleted list|ubl|plainlist|hlist|flatlist)\s*\|([^{}]*)\}\}",
                  lambda m: "/".join(x.strip() for x in m.group(1).split("|") if x.strip()), text, flags=re.I)
    for _ in range(4):                                    # nested argument templates: {{nowrap|{{center|x}}}}
        text = re.sub(r"\{\{\s*(?:%s)\s*\|([^{}]*)\}\}" % "|".join(ARG_TEMPLATES), lambda m: m.group(1).split("|")[-1],
                      text, flags=re.I)
    text = re.sub(r"\{\{\s*(?:%s)\s*\|" % "|".join(ARG_TEMPLATES), "", text, flags=re.I)      # an opener never closed
    text = re.sub(r"<br\s*/?>", " / ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"'{2,}", "", text)
    for entity, char in ENTITIES.items():
        text = text.replace(entity, char)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return re.sub(r"\s+", " ", text).strip(" |\u00a0")


class Cell:
    __slots__ = ("raw", "attrs", "header")

    def __init__(self, raw: str, attrs: dict[str, str], header: bool):
        self.raw, self.attrs, self.header = raw, attrs, header

    @property
    def text(self) -> str:
        return strip_markup(self.raw)

    def __repr__(self) -> str:
        return f"Cell({self.text!r})"


ATTR_PAIR = re.compile(r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|\u201c([^\u201d]*)\u201d|([^\s"'|]+)|())""")
# MediaWiki accepts odd attribute text (``style=`` with no value, a missing quote): anything that opens like name=... counts
ATTR_ONLY = re.compile(r"""^\s*[A-Za-z_:][-A-Za-z0-9_:.]*\s*=[^|]*$""")


def _cell(source: str, header: bool) -> Cell:
    parts = split_top(source, ("|",))
    attrs: dict[str, str] = {}
    if len(parts) >= 2 and ATTR_ONLY.match(parts[0]) and len(parts[0]) < 160:
        for m in ATTR_PAIR.finditer(parts[0]):
            attrs[m.group(1).lower()] = next((g for g in m.groups()[1:] if g), "")
        source = "|".join(parts[1:])
    return Cell(source.strip(), attrs, header)


def _span(cell: Cell, key: str) -> int:
    try:
        return max(1, int(re.sub(r"\D", "", cell.attrs.get(key, "1")) or 1))
    except ValueError:
        return 1


def parse_tables(text: str) -> list[list[list[Cell]]]:
    """Every top-level wikitable as rows of cells with rowspan/colspan expanded (a spanned cell repeats in each slot)."""

    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref\b[^>/]*/>", "", text)
    text = re.sub(r"<ref\b[^>]*>.*?</ref>", "", text, flags=re.S)
    tables: list[list[list[Cell]]] = []
    depth = 0
    raw_rows: list[list[Cell]] = []
    row: list[Cell] = []
    cell_src: list[str] | None = None
    cell_header = False

    def flush_cell() -> None:
        nonlocal cell_src
        if cell_src is not None:
            row.append(_cell("".join(cell_src), cell_header))
        cell_src = None

    def flush_row() -> None:
        nonlocal row
        flush_cell()
        if row:
            raw_rows.append(row)
        row = []

    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("{|"):
            depth += 1
            if depth == 1:
                raw_rows, row, cell_src = [], [], None
                continue
        if depth == 0:
            continue
        if stripped.startswith("|}"):
            depth -= 1
            if depth == 0:
                flush_row()
                tables.append(_expand(raw_rows))
                continue
        if depth > 1:                                      # nested table: part of the current cell
            if cell_src is not None:
                cell_src.append("\n" + line)
            continue
        if stripped.startswith("|-"):
            flush_row()
        elif stripped.startswith("|+"):
            continue
        elif stripped.startswith(("|", "!")):
            flush_cell()
            header = stripped.startswith("!")
            parts = split_top(stripped[1:], ("||", "!!") if header else ("||",))
            for part in parts[:-1]:
                row.append(_cell(part, header))
            cell_src, cell_header = [parts[-1]], header
        elif cell_src is not None:
            cell_src.append("\n" + line)
    return tables


def _expand(raw_rows: list[list[Cell]]) -> list[list[Cell]]:
    grid: list[list[Cell]] = []
    carry: dict[int, tuple[int, Cell]] = {}            # column -> (rows still to fill, cell)
    for raw in raw_rows:
        out: list[Cell] = []
        queue = list(raw)
        col = 0
        while queue or any(c >= col for c in carry):
            if col in carry:
                left, cell = carry[col]
                out.append(cell)
                if left > 1:
                    carry[col] = (left - 1, cell)
                else:
                    del carry[col]
                col += 1
                continue
            if not queue:
                if any(c > col for c in carry):
                    out.append(Cell("", {}, False))
                    col += 1
                    continue
                break
            cell = queue.pop(0)
            cs, rs = _span(cell, "colspan"), _span(cell, "rowspan")
            for k in range(cs):
                out.append(cell)
                if rs > 1:
                    carry[col + k] = (rs - 1, cell)
            col += cs
        grid.append(out)
    return grid


# ---------------------------------------------------------------------------------------------------------------------
# Clubs
# ---------------------------------------------------------------------------------------------------------------------
# Arena order of the 32 clubs (alphabetical by the 2004 nicknames; ``nfl2k5_champions_history.CLUBS``).
ARENA_NICKNAMES = ("49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers", "Cardinals", "Chargers", "Chiefs",
                   "Colts", "Cowboys", "Dolphins", "Eagles", "Falcons", "Giants", "Jaguars", "Jets", "Lions", "Packers",
                   "Panthers", "Patriots", "Raiders", "Rams", "Ravens", "Redskins", "Saints", "Seahawks", "Steelers",
                   "Texans", "Titans", "Vikings")
# club id (the NFL's abbreviation today) -> (arena nickname, division)
CLUB_TABLE = {
    "SF": ("49ers", "NFC West"), "CHI": ("Bears", "NFC North"), "CIN": ("Bengals", "AFC North"), "BUF": ("Bills", "AFC East"),
    "DEN": ("Broncos", "AFC West"), "CLE": ("Browns", "AFC North"), "TB": ("Buccaneers", "NFC South"),
    "ARI": ("Cardinals", "NFC West"), "LAC": ("Chargers", "AFC West"), "KC": ("Chiefs", "AFC West"),
    "IND": ("Colts", "AFC South"), "DAL": ("Cowboys", "NFC East"), "MIA": ("Dolphins", "AFC East"),
    "PHI": ("Eagles", "NFC East"), "ATL": ("Falcons", "NFC South"), "NYG": ("Giants", "NFC East"),
    "JAX": ("Jaguars", "AFC South"), "NYJ": ("Jets", "AFC East"), "DET": ("Lions", "NFC North"),
    "GB": ("Packers", "NFC North"), "CAR": ("Panthers", "NFC South"), "NE": ("Patriots", "AFC East"),
    "LV": ("Raiders", "AFC West"), "LAR": ("Rams", "NFC West"), "BAL": ("Ravens", "AFC North"),
    "WAS": ("Redskins", "NFC East"), "NO": ("Saints", "NFC South"), "SEA": ("Seahawks", "NFC West"),
    "PIT": ("Steelers", "AFC North"), "HOU": ("Texans", "AFC South"), "TEN": ("Titans", "AFC South"),
    "MIN": ("Vikings", "NFC North"),
}
CLUB_IDS = tuple(sorted(CLUB_TABLE, key=lambda c: ARENA_NICKNAMES.index(CLUB_TABLE[c][0])))
DIVISION_OF = {c: v[1] for c, v in CLUB_TABLE.items()}
DIVISIONS = ("AFC East", "AFC North", "AFC South", "AFC West", "NFC East", "NFC North", "NFC South", "NFC West")
CONFERENCE_OF = {c: d[:3] for c, d in DIVISION_OF.items()}
# nflverse team code -> club id
NFLVERSE_CLUB = {c: c for c in CLUB_TABLE}
NFLVERSE_CLUB.update({"LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV"})
# the abbreviation the NFL printed that season for the nflverse code
DISPLAY_LABEL = {"LA": "LAR"}
# club -> ((first season, last season, name), ...): the name the club carried
CLUB_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints",
    "NYG": "New York Giants", "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans",
}
CLUB_NAME_CHANGES = {
    "LAR": ((2002, 2015, "St. Louis Rams"), (2016, 2025, "Los Angeles Rams")),
    "LAC": ((2002, 2016, "San Diego Chargers"), (2017, 2025, "Los Angeles Chargers")),
    "LV": ((2002, 2019, "Oakland Raiders"), (2020, 2025, "Las Vegas Raiders")),
    "WAS": ((2002, 2019, "Washington Redskins"), (2020, 2021, "Washington Football Team"),
            (2022, 2025, "Washington Commanders")),
}
CLUB_NAMES_ALL = {c: ((FIRST_SEASON, LAST_SEASON, n),) for c, n in CLUB_NAMES.items()}
CLUB_NAMES_ALL.update(CLUB_NAME_CHANGES)


def club_name(club: str, season: int) -> str:
    for first, last, name in CLUB_NAMES_ALL[club]:
        if first <= season <= last:
            return name
    raise KeyError((club, season))


assert set(CLUB_NAMES_ALL) == set(CLUB_TABLE) and len(CLUB_IDS) == 32

PLAYOFF_CODES = ("missed", "lost_wild_card", "lost_divisional", "lost_conference", "lost_super_bowl", "champion")
ROUND_CODE = {"WC": 1, "DIV": 2, "CON": 3, "SB": 4}
SUPER_BOWL_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
                       "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII",
                       "XXIX", "XXX", "XXXI", "XXXII", "XXXIII", "XXXIV", "XXXV", "XXXVI", "XXXVII", "XXXVIII", "XXXIX",
                       "XL", "XLI", "XLII", "XLIII", "XLIV", "XLV", "XLVI", "XLVII", "XLVIII", "XLIX", "L", "LI", "LII",
                       "LIII", "LIV", "LV", "LVI", "LVII", "LVIII", "LIX", "LX"]


# ---------------------------------------------------------------------------------------------------------------------
# Seasons from nflverse games
# ---------------------------------------------------------------------------------------------------------------------
class Game:
    __slots__ = ("season", "kind", "week", "home", "away", "hs", "as_", "home_coach", "away_coach", "date", "home_label",
                 "away_label", "game_id", "overtime")

    def __init__(self, row: dict[str, str]):
        self.season = int(row["season"])
        self.kind = row["game_type"]
        self.week = int(row["week"])
        self.game_id = row["game_id"]
        self.home_label, self.away_label = row["home_team"], row["away_team"]
        self.home, self.away = NFLVERSE_CLUB[self.home_label], NFLVERSE_CLUB[self.away_label]
        self.hs, self.as_ = int(row["home_score"]), int(row["away_score"])
        self.home_coach, self.away_coach = row["home_coach"].strip(), row["away_coach"].strip()
        self.date = row["gameday"]
        self.overtime = row.get("overtime", "0") == "1"


def games_subset_digest(rows: list[dict[str, str]], fields: Iterable[str]) -> str:
    """SHA-256 of the 2002..2025 rows exactly as used: the listed fields, tab separated, one game per line, in file order."""

    fields = tuple(fields)
    out = hashlib.sha256()
    for row in rows:
        if FIRST_SEASON <= int(row["season"]) <= LAST_SEASON:
            out.update(("\t".join(row[f] for f in fields) + "\n").encode("utf-8"))
    return out.hexdigest()


USED_FIELDS = ("game_id", "season", "game_type", "week", "gameday", "away_team", "away_score", "home_team", "home_score",
               "overtime", "away_coach", "home_coach")


def load_games(path: Path) -> tuple[list[Game], list[dict[str, str]], str]:
    raw = Path(path).read_bytes()
    digest = sha256_hex(raw)
    if digest != NFLVERSE_GAMES["sha256"]:
        raise SystemExit(f"{path}: SHA-256 {digest} is not the pinned {NFLVERSE_GAMES['sha256']} "
                         f"(nflverse/nfldata commit {NFLVERSE_GAMES['commit'][:12]})")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    games = []
    for row in rows:
        if FIRST_SEASON <= int(row["season"]) <= LAST_SEASON:
            if row["home_score"] in ("", "NA") or row["away_score"] in ("", "NA"):
                raise SystemExit(f"{row['game_id']}: no score")
            games.append(Game(row))
    return games, rows, digest


def pct(w: int, l: int, t: int) -> float | None:
    n = w + l + t
    return None if n == 0 else (w + t / 2) / n


class SeasonTable:
    """One regular season: every club's results and the NFL's division tie-break."""

    def __init__(self, season: int, games: list[Game]):
        self.season = season
        self.games = [g for g in games if g.season == season and g.kind == "REG"]
        self.clubs = sorted({g.home for g in self.games} | {g.away for g in self.games})
        # per club: list of (opponent, points for, points against)
        self.log: dict[str, list[tuple[str, int, int]]] = {c: [] for c in self.clubs}
        for g in self.games:
            self.log[g.home].append((g.away, g.hs, g.as_))
            self.log[g.away].append((g.home, g.as_, g.hs))
        self.record = {c: self.tally(self.log[c]) for c in self.clubs}
        self.pf = {c: sum(x[1] for x in self.log[c]) for c in self.clubs}
        self.pa = {c: sum(x[2] for x in self.log[c]) for c in self.clubs}
        self.notes: dict[str, str] = {}

    @staticmethod
    def tally(entries: Iterable[tuple[str, int, int]]) -> tuple[int, int, int]:
        w = l = t = 0
        for _opp, pf, pa in entries:
            if pf > pa:
                w += 1
            elif pf < pa:
                l += 1
            else:
                t += 1
        return w, l, t

    def pct_of(self, club: str) -> float:
        return pct(*self.record[club]) or 0.0

    def vs(self, club: str, opponents: Iterable[str]) -> list[tuple[str, int, int]]:
        keep = set(opponents)
        return [x for x in self.log[club] if x[0] in keep]

    def division_games(self, club: str) -> list[tuple[str, int, int]]:
        return self.vs(club, [c for c in self.clubs if DIVISION_OF[c] == DIVISION_OF[club] and c != club])

    def conference_games(self, club: str) -> list[tuple[str, int, int]]:
        return self.vs(club, [c for c in self.clubs if CONFERENCE_OF[c] == CONFERENCE_OF[club] and c != club])

    # --- tie-break steps; each returns (value, higher_is_better) or None when the step does not apply -------------------
    def _head_to_head(self, club: str, tied: list[str]) -> float | None:
        games = self.vs(club, [c for c in tied if c != club])
        return pct(*self.tally(games))

    def _common(self, tied: list[str]) -> tuple[set[str], bool]:
        opponents = [set(o for o, _pf, _pa in self.log[c]) - set(tied) for c in tied]
        common = set.intersection(*opponents)
        games = min(len(self.vs(c, common)) for c in tied) if common else 0
        return common, games >= 4

    def _strength(self, club: str, beaten_only: bool) -> float | None:
        w = l = t = 0
        for opp, pf, pa in self.log[club]:
            if beaten_only and not pf > pa:
                continue
            ow, ol, ot = self.record[opp]
            w, l, t = w + ow, l + ol, t + ot
        return pct(w, l, t)

    def _rank_sum(self, club: str, within: list[str]) -> int:
        scored = sorted((self.pf[c] for c in within), reverse=True)
        allowed = sorted(self.pa[c] for c in within)
        return (1 + scored.index(self.pf[club])) + (1 + allowed.index(self.pa[club]))

    def _steps(self, tied: list[str]):
        """(name, function(club) -> comparable or None, higher_is_better) for the tied group, in the NFL's order.

        The division procedure is the same list for two clubs and for three or more: head-to-head (the percentage in the
        games among the tied clubs), division record, common games (at least four), conference record, strength of
        victory, strength of schedule, the two points rankings, net points in common games, net points in all games.
        Net touchdowns and the coin toss cannot be reproduced from scores; an unbroken tie is reported as unresolved."""

        steps: list[tuple[str, Any, bool]] = [("head_to_head", lambda c: self._head_to_head(c, tied), True),
                                              ("division_record", lambda c: pct(*self.tally(self.division_games(c))), True)]
        common, enough = self._common(tied)
        if enough:
            steps.append(("common_games", lambda c: pct(*self.tally(self.vs(c, common))), True))
        steps.append(("conference_record", lambda c: pct(*self.tally(self.conference_games(c))), True))
        steps.append(("strength_of_victory", lambda c: self._strength(c, True), True))
        steps.append(("strength_of_schedule", lambda c: self._strength(c, False), True))
        conf = [c for c in self.clubs if CONFERENCE_OF[c] == CONFERENCE_OF[tied[0]]]
        steps.append(("conference_points_rank", lambda c: self._rank_sum(c, conf), False))
        steps.append(("league_points_rank", lambda c: self._rank_sum(c, self.clubs), False))
        if enough:
            steps.append(("net_points_common", lambda c: sum(pf - pa for _o, pf, pa in self.vs(c, common)), True))
        steps.append(("net_points_all", lambda c: self.pf[c] - self.pa[c], True))
        return steps

    def best_of(self, tied: list[str]) -> tuple[list[str], str]:
        """The club(s) left on top when the NFL's procedure is applied to ``tied``; the step that decided it.

        If a step leaves exactly two of three or more clubs, the procedure restarts from its first step for those two."""

        remaining = list(tied)
        if len(remaining) == 1:
            return remaining, "none"
        for name, fn, higher in self._steps(remaining):
            values = {c: fn(c) for c in remaining}
            if all(v is None for v in values.values()):
                continue
            values = {c: (-1.0 if v is None else v) for c, v in values.items()}
            best = max(values.values()) if higher else min(values.values())
            keep = [c for c in remaining if values[c] == best]
            if len(keep) < len(remaining):
                remaining = keep
                if len(remaining) == 1:
                    return remaining, name
                if len(remaining) == 2 and len(tied) > 2:
                    return self.best_of(remaining)
        return remaining, "unresolved"

    def order(self, tied: list[str]) -> list[tuple[str, str]]:
        """``tied`` ranked best first as (club, step that placed it)."""

        left = sorted(tied)
        out: list[tuple[str, str]] = []
        while left:
            if len(left) == 1:
                out.append((left[0], "none"))
                break
            top, step = self.best_of(left)
            if len(top) > 1:                              # an unbroken tie: net touchdowns / coin toss in the real rules
                top = [sorted(top)[0]]
                step = "unresolved"
            out.append((top[0], step))
            left.remove(top[0])
        return out

    def standings(self) -> dict[str, dict[str, Any]]:
        """{club: {place, tiebreak}} for all 32 clubs."""

        out: dict[str, dict[str, Any]] = {}
        for division in DIVISIONS:
            members = [c for c in self.clubs if DIVISION_OF[c] == division]
            groups: dict[float, list[str]] = collections.defaultdict(list)
            for c in members:
                groups[self.pct_of(c)].append(c)
            place = 1
            for key in sorted(groups, reverse=True):
                for club, step in self.order(groups[key]):
                    out[club] = {"place": place, "tiebreak": step if len(groups[key]) > 1 else "none"}
                    place += 1
        return out


def build_seasons(games: list[Game]) -> tuple[list[dict], dict[str, dict]]:
    """The 24 season blocks and the per-club totals over them."""

    seasons = []
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        table = SeasonTable(season, games)
        stands = table.standings()
        post = collections.defaultdict(list)
        sb_game = None
        for g in games:
            if g.season == season and g.kind != "REG":
                post[g.home].append((g.kind, g.week, g.hs > g.as_))
                post[g.away].append((g.kind, g.week, g.as_ > g.hs))
                if g.kind == "SB":
                    sb_game = g
        assert sb_game is not None, season
        coaches: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        labels: dict[str, str] = {}
        for g in table.games:
            coaches[g.home][g.home_coach] += 1
            coaches[g.away][g.away_coach] += 1
            labels[g.home], labels[g.away] = g.home_label, g.away_label
        rows = []
        for club in CLUB_IDS:
            w, l, t = table.record[club]
            dw, dl, dt = table.tally(table.division_games(club))
            cw, cl, ct = table.tally(table.conference_games(club))
            rounds = sorted(post.get(club, []), key=lambda x: x[1])
            if not rounds:
                code, bye = 0, False
            else:
                last_kind, _week, won = rounds[-1]
                code = ROUND_CODE[last_kind] + (1 if (last_kind == "SB" and won) else 0)
                if won and last_kind != "SB":
                    raise SystemExit(f"{season} {club}: won a {last_kind} game and has no later game")
                bye = rounds[0][0] == "DIV"
            ordered = sorted(coaches[club].items(), key=lambda kv: (-kv[1], kv[0]))
            row = {"club": club, "label": DISPLAY_LABEL.get(labels[club], labels[club]), "name": club_name(club, season),
                   "w": w, "l": l, "t": t, "pf": table.pf[club], "pa": table.pa[club],
                   "div": [dw, dl, dt], "conf": [cw, cl, ct], "place": stands[club]["place"],
                   "playoffs": PLAYOFF_CODES[code]}
            if bye:
                row["bye"] = True
            if stands[club]["tiebreak"] != "none":
                row["tiebreak"] = stands[club]["tiebreak"]
            row["coach"] = ordered[0][0]
            if len(ordered) > 1:
                row["coach_games"] = ordered[0][1]
                row["other_coaches"] = [[n, c] for n, c in ordered[1:]]
            rows.append(row)
        champion = sb_game.home if sb_game.hs > sb_game.as_ else sb_game.away
        runner_up = sb_game.away if sb_game.hs > sb_game.as_ else sb_game.home
        winner_points, loser_points = max(sb_game.hs, sb_game.as_), min(sb_game.hs, sb_game.as_)
        header = {
            "season": season, "super_bowl": SUPER_BOWL_NUMERALS[season - 1966], "super_bowl_number": season - 1965,
            "regular_season_games": 17 if season >= 2021 else 16,
            "playoff_teams": 14 if season >= 2020 else 12, "champion": champion, "runner_up": runner_up,
            "champion_points": winner_points, "runner_up_points": loser_points, "super_bowl_date": sb_game.date,
        }
        seasons.append({**header, "teams": rows})
    return seasons, club_totals(seasons)


def club_totals(seasons: list[dict]) -> dict[str, dict]:
    """Per club over 2002..2025: record, points, playoff trips, titles (derived from the season rows, nothing else)."""

    totals = {c: dict(w=0, l=0, t=0, pf=0, pa=0, playoff_trips=0, division_titles=0, conference_titles=0, super_bowl_wins=0,
                      super_bowl_losses=0) for c in CLUB_IDS}
    for season in seasons:
        for row in season["teams"]:
            x = totals[row["club"]]
            for key in ("w", "l", "t", "pf", "pa"):
                x[key] += row[key]
            x["playoff_trips"] += row["playoffs"] != "missed"
            x["division_titles"] += row["place"] == 1
            x["conference_titles"] += row["playoffs"] in ("lost_super_bowl", "champion")
            x["super_bowl_wins"] += row["playoffs"] == "champion"
            x["super_bowl_losses"] += row["playoffs"] == "lost_super_bowl"
    return totals


# ---------------------------------------------------------------------------------------------------------------------
# Second source for the seasons: the final division standings Wikipedia keeps per season (pinned template revisions)
# ---------------------------------------------------------------------------------------------------------------------
def template_key(season: int, division: str) -> str:
    return f"standings_{season}_{division.replace(' ', '_')}"


def parse_standings_template(text: str) -> list[dict[str, Any]]:
    """The four rows of a ``Template:<year> <division> standings`` page in final order."""

    tables = parse_tables(text.split("<noinclude>")[0])
    rows = []
    for raw in tables[0][2:]:
        cells = [c.text for c in raw]
        if len(cells) < 9:
            continue
        seed = re.match(r"\((\d)\)\s*(.*)", cells[0])

        def record(value: str) -> tuple[int, int, int]:
            nums = [int(x) for x in re.split(r"[–—-]", value)]
            return (nums[0], nums[1], nums[2] if len(nums) > 2 else 0)
        rows.append({"name": (seed.group(2) if seed else cells[0]).strip(), "seed": int(seed.group(1)) if seed else None,
                     "w": int(cells[1]), "l": int(cells[2]), "t": int(cells[3]), "div": record(cells[5]),
                     "conf": record(cells[6]), "pf": int(cells[7]), "pa": int(cells[8])})
    return rows


def verify_standings(seasons: list[dict], wiki: "WikiSources") -> dict[str, Any]:
    """Compare every computed club-season with Wikipedia's final standings: name, W-L-T, PF, PA, division and conference
    records, the order of the four clubs in each division, the playoff seeds (who made the playoffs, who had the bye, who
    won the division). Returns {compared, problems}; a problem is {season, club, field, ours, wikipedia}."""

    problems, compared = [], 0

    def problem(season, club, field, ours, theirs):
        problems.append({"season": season, "club": club, "field": field, "ours": ours, "wikipedia": theirs})

    for season in seasons:
        year = season["season"]
        for division in DIVISIONS:
            rows = parse_standings_template(wiki.text(template_key(year, division)))
            if len(rows) != 4:
                problem(year, division, "rows", len(rows), 4)
                continue
            for place, ref in enumerate(rows, 1):
                compared += 1
                mine = next((t for t in season["teams"] if t["name"] == ref["name"]), None)
                if mine is None:
                    problem(year, ref["name"], "name", None, ref["name"])
                    continue
                for key in ("w", "l", "t", "pf", "pa"):
                    if mine[key] != ref[key]:
                        problem(year, ref["name"], key, mine[key], ref[key])
                for key in ("div", "conf"):
                    if tuple(mine[key]) != ref[key]:
                        problem(year, ref["name"], key, list(mine[key]), list(ref[key]))
                if mine["place"] != place:
                    problem(year, ref["name"], "place", mine["place"], place)
                made = mine["playoffs"] != "missed"
                if (ref["seed"] is not None) != made:
                    problem(year, ref["name"], "playoffs", mine["playoffs"], f"seed {ref['seed']}")
                elif ref["seed"] is not None:
                    byes = 1 if year >= 2020 else 2                     # the top seeds rest in the first round
                    if (ref["seed"] <= byes) != bool(mine.get("bye")):
                        problem(year, ref["name"], "bye", bool(mine.get("bye")), ref["seed"] <= byes)
                    if (ref["seed"] <= 4) != (mine["place"] == 1):
                        problem(year, ref["name"], "division_winner", mine["place"] == 1, ref["seed"] <= 4)
    return {"compared": compared, "problems": problems}


# ---------------------------------------------------------------------------------------------------------------------
# Awards 2002..2025
# ---------------------------------------------------------------------------------------------------------------------
# award id -> (label, source key, which table of the page: 0-based among the winner tables, or a heading to cut at)
AWARDS = (
    ("mvp", "AP NFL Most Valuable Player", "wiki_mvp", None),
    ("opoy", "AP NFL Offensive Player of the Year", "wiki_opoy", None),
    ("dpoy", "AP NFL Defensive Player of the Year", "wiki_dpoy", None),
    ("oroy", "AP NFL Offensive Rookie of the Year", "wiki_roy", "Offensive"),
    ("droy", "AP NFL Defensive Rookie of the Year", "wiki_roy", "Defensive"),
    ("cpoy", "AP NFL Comeback Player of the Year", "wiki_cpoy", None),
    ("coy", "AP NFL Coach of the Year", "wiki_coy", None),
    ("super_bowl_mvp", "Super Bowl Most Valuable Player (the game that ends the season)", "wiki_sbmvp", None),
)
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
POSITION_WORDS = {
    "quarterback": "QB", "qb": "QB", "running back": "HB", "rb": "HB", "halfback": "HB", "hb": "HB", "fullback": "FB",
    "fb": "FB", "wide receiver": "WR", "wr": "WR", "kick returner": "WR", "return specialist": "WR", "tight end": "TE",
    "te": "TE", "offensive tackle": "T", "ot": "T", "tackle": "T", "guard": "G", "offensive guard": "G", "og": "G",
    "center": "C", "c": "C", "defensive end": "DE", "de": "DE", "edge rusher": "DE", "defensive tackle": "DT", "dt": "DT",
    "linebacker": "OLB", "lb": "OLB", "olb": "OLB", "outside linebacker": "OLB", "inside linebacker": "ILB",
    "middle linebacker": "ILB", "ilb": "ILB", "mlb": "ILB", "cornerback": "CB", "cb": "CB", "safety": "SS", "s": "SS",
    "free safety": "FS", "fs": "FS", "strong safety": "SS", "ss": "SS", "punter": "P", "p": "P", "placekicker": "K",
    "kicker": "K", "k": "K", "defensive back": "CB", "db": "CB",
}
# The page names no side for these players; the code follows the positions they are known for (cited per player in rules).
POSITION_OVERRIDE = {
    "Dexter Jackson": "FS",      # Super Bowl XXXVII MVP, free safety
    "Ed Reed": "FS",             # 2004 DPOY
    "Bob Sanders": "SS",         # 2007 DPOY
    "Troy Polamalu": "SS",       # 2010 DPOY
    "Ray Lewis": "ILB",          # 2003 DPOY
    "Brian Urlacher": "ILB",     # 2005 DPOY, middle linebacker
    "Patrick Willis": "ILB",     # 2007 DROY, middle/inside linebacker
    "DeMeco Ryans": "ILB",       # 2006 DROY
    "Luke Kuechly": "ILB",       # 2012 DROY, 2013 DPOY, middle linebacker
    "Darius Leonard": "ILB",     # 2018 DROY
    "Jerod Mayo": "ILB",         # 2008 DROY
    "Brian Cushing": "ILB",      # 2009 DROY
}
NOISE_SUFFIX = re.compile(r"\s*(?:\(\d+\)|[†‡*~^§#])+\s*$")


def clean_name(text: str) -> str:
    text = text.strip()
    for _ in range(3):
        text = NOISE_SUFFIX.sub("", text).strip()
    return re.sub(r"\s+", " ", text)


def position_code(text: str, name: str) -> str | None:
    if name in POSITION_OVERRIDE:
        return POSITION_OVERRIDE[name]
    key = re.sub(r"\s*\(\d+\)\s*$", "", text.strip().lower())
    key = re.sub(r"\s*\((?:american|gridiron) football(?: position)?\)$", "", key)
    return POSITION_WORDS.get(key)


def _name_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for club, spans in CLUB_NAMES_ALL.items():
        for _first, _last, name in spans:
            index[name.lower()] = club
        nickname = spans[-1][2].split(" ")[-1]
        index.setdefault(nickname.lower(), club)
    index.update({"redskins": "WAS", "commanders": "WAS", "washington football team": "WAS", "la rams": "LAR", "la chargers": "LAC",
                  "ny giants": "NYG", "ny jets": "NYJ", "san francisco": "SF", "tampa bay": "TB", "kansas city": "KC",
                  "green bay": "GB", "new england": "NE", "new orleans": "NO", "oakland": "LV", "st. louis": "LAR",
                  "san diego": "LAC", "las vegas": "LV", "arizona": "ARI", "atlanta": "ATL", "baltimore": "BAL", "buffalo": "BUF",
                  "carolina": "CAR", "chicago": "CHI", "cincinnati": "CIN", "cleveland": "CLE", "dallas": "DAL", "denver": "DEN",
                  "detroit": "DET", "houston": "HOU", "indianapolis": "IND", "jacksonville": "JAX", "miami": "MIA",
                  "minnesota": "MIN", "philadelphia": "PHI", "pittsburgh": "PIT", "seattle": "SEA", "tennessee": "TEN",
                  "washington": "WAS"})
    return index


NAME_INDEX = _name_index()


def club_of(raw: str, season: int | None = None) -> str | None:
    """The club id a team cell names: from its link targets ("2016 Oakland Raiders season", "Seattle Seahawks"), else its text."""

    for target in re.findall(r"\[\[([^\]|]+)", raw):
        t = re.sub(r"^\d{4}(?:[–-]\d{2,4})?\s+", "", target.strip())
        t = re.sub(r"\s+season$", "", t, flags=re.I)
        if t.lower() in NAME_INDEX:
            return NAME_INDEX[t.lower()]
    text = clean_name(strip_markup(raw)).lower()
    return NAME_INDEX.get(text)


def season_of(cell: Cell) -> int | None:
    m = (re.search(r"\[\[(\d{4}) NFL season", cell.raw) or re.search(r"NFL year\|(\d{4})", cell.raw)
         or re.match(r"\s*(\d{4})\b", cell.text))
    return int(m.group(1)) if m else None


def cut_section(text: str, heading: str | None) -> str:
    """The text of one ``=== heading ===`` section (to the next heading of the same or higher level)."""

    if heading is None:
        return text
    m = re.search(r"^(=+)\s*%s\s*\1\s*$" % re.escape(heading), text, flags=re.M)
    if not m:
        raise SystemExit(f"section {heading!r} not found")
    rest = text[m.end():]
    end = re.search(r"^={1,%d}[^=\n].*$" % len(m.group(1)), rest, flags=re.M)
    return rest[:end.start()] if end else rest


def winner_table(text: str) -> list[list[Cell]]:
    for table in parse_tables(text):
        if len(table) > 20 and table[0] and table[0][0].text in ("Season", "Year"):
            return table
    raise SystemExit("no winners table")


def _entries(cell: Cell) -> list[str]:
    return [e for e in re.split(r"<br\s*/?>", cell.raw, flags=re.I) if strip_markup(e)]


def build_awards(wiki: WikiSources) -> list[dict]:
    winners: dict[tuple[int, str], list[dict]] = collections.defaultdict(list)
    for award, _label, key, heading in AWARDS:
        table = winner_table(cut_section(wiki.text(key), heading))
        header = [c.text for c in table[0]]
        for row in table[1:]:
            season = season_of(row[0])               # the link target, so Super Bowl XXXVII (played 2003) is season 2002
            if award == "super_bowl_mvp":
                number = re.search(r"\{\{\s*sort\s*\|\s*(\d+)\s*\|", row[1].raw)
                if season is not None and (not number or int(number.group(1)) != season - 1965):
                    raise SystemExit(f"Super Bowl MVP row {row[0].raw!r} {row[1].raw!r}: game number does not match the season")
                name_i, team_i, pos_i = 2, 3, 4
            else:
                name_i = 1
                pos_i = header.index("Position") if "Position" in header else None
                team_i = header.index("Team")
            if season is None or not FIRST_SEASON <= season <= LAST_SEASON:
                continue
            names = _entries(row[name_i])
            teams = _entries(row[team_i])
            poses = _entries(row[pos_i]) if pos_i is not None else []
            for i, raw_name in enumerate(names):
                name = clean_name(strip_markup(raw_name))
                club = club_of(teams[min(i, len(teams) - 1)] if teams else "", season)
                if club is None:
                    raise SystemExit(f"{award} {season}: no club for {teams!r}")
                entry = {"name": name, "club": club}
                if award == "coy":
                    entry["position"] = "HC"
                else:
                    pos_text = strip_markup(poses[min(i, len(poses) - 1)]) if poses else ""
                    code = position_code(pos_text, name)
                    if code is None:
                        raise SystemExit(f"{award} {season} {name}: unknown position {pos_text!r}")
                    entry["position"] = code
                winners[(season, award)].append(entry)
    out = []
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        for award, *_ in AWARDS:
            got = winners.get((season, award))
            if not got:
                raise SystemExit(f"{award} {season}: no winner found")
            out.append({"season": season, "award": award, "winners": got})
    return out


# ---------------------------------------------------------------------------------------------------------------------
# NFL record book (single game, single season, career) from the pinned Wikipedia record pages
# ---------------------------------------------------------------------------------------------------------------------
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
DATE_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b")
SEASON_LINK = re.compile(r"^(\d{4}) (.+?)(?: \(NFL\))? season$")
# category -> (unit, [(scope, page key, section heading, bold label), ...])
RECORD_SPECS: dict[str, tuple[str, list[tuple[str, str, str, str]]]] = {
    "passing_yards": ("yards", [("career", "wiki_qb_records", "Passing yards", "Most passing yards, career"),
                                ("season", "wiki_qb_records", "Passing yards", "Most passing yards, season"),
                                ("game", "wiki_qb_records", "Passing yards", "Most passing yards, game")]),
    "passing_tds": ("touchdowns", [("career", "wiki_qb_records", "Passing touchdowns", "Most passing touchdowns, career"),
                                   ("season", "wiki_qb_records", "Passing touchdowns", "Most passing touchdowns, season"),
                                   ("game", "wiki_qb_records", "Passing touchdowns", "Most passing touchdowns, game")]),
    "rushing_yards": ("yards", [("career", "wiki_records", "Rushing yards", "Most yards gained, career"),
                                ("season", "wiki_records", "Rushing yards", "Most yards gained, season"),
                                ("game", "wiki_records", "Rushing yards", "Most yards gained, game")]),
    "rushing_tds": ("touchdowns", [("career", "wiki_records", "Rushing touchdowns", "Most touchdowns, career"),
                                   ("season", "wiki_records", "Rushing touchdowns", "Most rushing touchdowns, season"),
                                   ("game", "wiki_records", "Rushing touchdowns", "Most rushing touchdowns, game")]),
    "receptions": ("catches", [("career", "wiki_records", "Receptions", "Most pass receptions, career"),
                               ("season", "wiki_records", "Receptions", "Most pass receptions, season"),
                               ("game", "wiki_records", "Receptions", "Most pass receptions, game")]),
    "receiving_yards": ("yards", [("career", "wiki_records", "Yards receiving", "Most receiving yards, career"),
                                  ("season", "wiki_records", "Yards receiving", "Most receiving yards, season"),
                                  ("game", "wiki_records", "Yards receiving", "Most receiving yards, game")]),
    "receiving_tds": ("touchdowns", [("career", "wiki_records", "Receiving touchdowns", "Most touchdowns, career"),
                                     ("season", "wiki_records", "Receiving touchdowns", "Most touchdowns, season"),
                                     ("game", "wiki_records", "Receiving touchdowns", "Most touchdowns, game")]),
    "sacks": ("sacks", [("career", "wiki_records", "Sacks", "Most sacks, career"), ("season", "wiki_records", "Sacks", "Most sacks, season"),
                        ("game", "wiki_records", "Sacks", "Most sacks, game")]),
    "interceptions": ("interceptions", [("career", "wiki_records", "Interceptions", "Most interceptions, career"),
                                        ("season", "wiki_records", "Interceptions", "Most interceptions, season"),
                                        ("game", "wiki_records", "Interceptions", "Most interceptions, game")]),
    "tackles": ("tackles", [("career", "wiki_records", "Tackles", "Most combined tackles, career"),
                            ("season", "wiki_records", "Tackles", "Most combined tackles, season"),
                            ("game", "wiki_records", "Tackles", "Most combined tackles, game")]),
    "points": ("points", [("career", "wiki_records", "Scoring", "Most points scored, career"),
                          ("season", "wiki_records", "Scoring", "Most points scored, season"),
                          ("game", "wiki_records", "Scoring", "Most points scored, game")]),
    "field_goals": ("field goals", [("career", "wiki_records", "Field goals", "Most field goals made, career"),
                                    ("season", "wiki_records", "Field goals", "Most field goals made, season"),
                                    ("game", "wiki_records", "Field goals", "Most field goals made, game")]),
}
CATEGORY_LABELS = {
    "passing_yards": "Passing yards", "passing_tds": "Passing touchdowns", "rushing_yards": "Rushing yards",
    "rushing_tds": "Rushing touchdowns", "receptions": "Receptions", "receiving_yards": "Receiving yards",
    "receiving_tds": "Receiving touchdowns", "sacks": "Sacks", "interceptions": "Interceptions", "tackles": "Tackles",
    "points": "Points", "field_goals": "Field goals made",
}
# Team names (including defunct and renamed clubs) -> the club that exists today, or None for clubs that no longer exist.
HISTORIC_TEAMS = {
    "chicago cardinals": "ARI", "st. louis cardinals": "ARI", "phoenix cardinals": "ARI", "arizona cardinals": "ARI",
    "cleveland rams": "LAR", "los angeles rams": "LAR", "st. louis rams": "LAR", "houston oilers": "TEN",
    "tennessee oilers": "TEN", "tennessee titans": "TEN", "baltimore colts": "IND", "indianapolis colts": "IND",
    "boston patriots": "NE", "new england patriots": "NE", "los angeles raiders": "LV", "oakland raiders": "LV",
    "las vegas raiders": "LV", "san diego chargers": "LAC", "los angeles chargers": "LAC", "dallas texans": "KC",
    "kansas city chiefs": "KC", "decatur staleys": "CHI", "chicago staleys": "CHI", "chicago bears": "CHI",
    "portsmouth spartans": "DET", "detroit lions": "DET", "boston redskins": "WAS", "washington redskins": "WAS",
    "washington football team": "WAS", "washington commanders": "WAS", "new york titans": "NYJ", "new york jets": "NYJ",
}
HISTORIC_TEAMS.update({name.lower(): club for club, spans in CLUB_NAMES_ALL.items() for _a, _b, name in spans})


def section_of(text: str, heading: str) -> str:
    """The text under the first ``=`` heading with this title, up to the next heading of the same or higher rank."""

    m = re.search(r"^(=+)\s*%s\s*\1\s*$" % re.escape(heading), text, flags=re.M)
    if not m:
        raise SystemExit(f"heading {heading!r} not found")
    rest = text[m.end():]
    end = re.search(r"^={1,%d}[^=\n].*$" % len(m.group(1)), rest, flags=re.M)
    return rest[:end.start()] if end else rest


def drop_refs(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref\b[^>/]*/>", "", text)
    text = re.sub(r"<ref\b[^>]*>.*?</ref>", "", text, flags=re.S)
    return re.sub(r"\{\{\s*rp\s*\|[^}]*\}\}", "", text)


def bullet_for(section: str, label: str) -> str:
    """The remainder of the bullet whose bold label is ``label`` (first match in the section)."""

    for line in section.split("\n"):
        m = re.match(r"^\*\s*'''(.*?)'''\s*:?\s*(.*)$", line)
        if m and strip_markup(m.group(1)).strip() == label:
            return m.group(2).rstrip()
    raise SystemExit(f"bullet {label!r} not found")


NUMBER_AT_START = re.compile(r"\s*;?\s*(\d[\d,]*(?:\.\d+)?)")


def person_links(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, target, label) of the links that name people (not seasons, teams or events)."""

    out = []
    for m in re.finditer(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]", text):
        target, label = m.group(1).strip(), (m.group(2) or m.group(1)).strip()
        if SEASON_LINK.match(target) or re.search(r"\bNFL\b|Super Bowl|\bseason\b|playoffs", target) or \
                target.lower() in HISTORIC_TEAMS:
            continue
        out.append((m.start(), m.end(), target, label))
    return out


def iso_date(text: str) -> str | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    return f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"


def number_of(raw: str) -> int | float:
    raw = raw.replace(",", "")
    return float(raw) if "." in raw else int(raw)


def parse_record_holders(rest: str) -> tuple[int | float, list[dict[str, Any]], int | None]:
    """(value, holders, number of players when the page only names the latest of a long tie)."""

    start = NUMBER_AT_START.match(rest)
    if not start:
        raise SystemExit(f"no number in {rest[:60]!r}")
    value = number_of(start.group(1))
    tail = rest[start.end():]
    many = re.search(r"by (\d+) (?:players|times)", tail)
    links = person_links(tail)
    holders = []
    for i, (_start, end, _target, label) in enumerate(links):
        stop = links[i + 1][0] if i + 1 < len(links) else len(tail)
        after = tail[end:stop]
        season_link = re.search(r"\[\[(\d{4}) ([^\]|]+?)(?: \(NFL\))? season\|([^\]]*)\]\]", after)
        flat = re.sub(r"\[\[(\d{4}) [^\]|]+? season\|([^\]]*)\]\]", r"\2", after)
        when = strip_markup(flat)
        date = iso_date(when)
        years = re.findall(r"\b(1[89]\d{2}|20\d{2})\b", when)
        holder: dict[str, Any] = {"name": clean_name(strip_markup(label)).replace("’", "'")}
        if season_link:
            holder["team"] = season_link.group(2)
            holder["season"] = int(season_link.group(1))
        elif years:
            holder["season"] = int(years[0])
        if date:
            holder["date"] = date
        if len(years) >= 2 and "date" not in holder and not season_link:
            holder["seasons"] = f"{years[0]}-{years[-1]}"
        holders.append(holder)
    return value, holders, int(many.group(1)) if many else None


def build_records(wiki: WikiSources) -> list[dict]:
    pages = {"wiki_records": drop_refs(wiki.text("wiki_records")), "wiki_qb_records": drop_refs(wiki.text("wiki_qb_records"))}
    out = []
    for category, (unit, specs) in RECORD_SPECS.items():
        for scope, page, heading, label in specs:
            rest = bullet_for(section_of(pages[page], heading), label)
            value, holders, many = parse_record_holders(rest)
            if not holders:
                raise SystemExit(f"{category} {scope}: no holder in {rest[:80]!r}")
            if scope == "career":                            # a career is a span of seasons, not one season
                for holder in holders:
                    holder.pop("season", None)
            record: dict[str, Any] = {"id": f"{category}.{scope}", "category": category, "scope": scope, "label": label,
                                      "value": value, "unit": unit, "holders": holders, "source": page}
            if many:
                record["tied_players"] = many
            out.append(record)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# NFL career leaders (top five per category) from the pinned Wikipedia leader lists
# ---------------------------------------------------------------------------------------------------------------------
# category -> (page key, player column, value column, team columns, position column)
LEADER_SPECS = {
    "passing_yards": ("wiki_career_passing_yards", 1, 2, (5, 6), None),
    "passing_tds": ("wiki_career_passing_tds", 1, 2, (4, 5), None),
    "rushing_yards": ("wiki_career_rushing_yards", 1, 4, (2,), None),
    "rushing_tds": ("wiki_career_rushing_tds", 1, 3, (2,), None),
    "receptions": ("wiki_career_receptions", 1, 3, (2,), None),
    "receiving_yards": ("wiki_career_receiving_yards", 1, 5, (3,), 2),
    "receiving_tds": ("wiki_career_receiving_tds", 1, 3, (2,), None),
    "sacks": ("wiki_career_sacks", 2, 4, (3,), 1),
    "interceptions": ("wiki_career_interceptions", 1, 4, (3,), 2),
    "tackles": ("wiki_career_tackles", 2, 3, (4,), 1),
    "points": ("wiki_career_points", 1, 3, (), 2),
    "field_goals": ("wiki_career_field_goals", 1, 2, (3,), None),
}
TOP_N = 5


def clubs_in(raw: str) -> tuple[list[str], list[str]]:
    """(club ids, names of teams that no longer exist) in the order a cell lists them: from its links, else from its text."""

    clubs: list[str] = []
    gone: list[str] = []
    names = [re.sub(r"\s+season$", "", re.sub(r"^\d{4}\s+", "", t.strip()), flags=re.I) for t in re.findall(r"\[\[([^\]|]+)", raw)]
    if not any(n.lower() in HISTORIC_TEAMS for n in names):
        text = re.sub(r"<br\s*/?>", "/", drop_refs(raw), flags=re.I)
        names = [re.sub(r"\s*\([^)]*\)\s*$", "", n).strip() for n in strip_markup(text).split("/")]
    for name in names:
        club = HISTORIC_TEAMS.get(name.lower())
        if club and club not in clubs:
            clubs.append(club)
        elif not club and name and re.search(r"\b(?:Colts|Cardinals|Rams|Oilers|Titans|Eagles|Yellow Jackets|Staleys|Bulldogs|Texans)\b", name):
            gone.append(name)
    return clubs, gone


def career_years(text: str) -> str | None:
    years = [int(y) for y in re.findall(r"\b(19[2-9]\d|20[0-2]\d)\b", text)]
    if not years:
        return None
    return f"{min(years)}-{'present' if re.search(r'present', text, re.I) else max(years)}"


def build_leaders(wiki: WikiSources) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for category, (key, player_col, value_col, team_cols, pos_col) in LEADER_SPECS.items():
        table = next(t for t in parse_tables(drop_refs(wiki.text(key))) if len(t) > 8)
        rows = collections.OrderedDict()
        for row in table[1:]:
            rank_text = row[0].text.strip()
            if not rank_text.isdigit():
                continue
            name = strip_markup(row[player_col].raw)
            if "style=" in name:                                  # a stray attribute prefix in one table
                name = name.split("|")[-1]
            name = clean_name(name)
            entry = rows.setdefault(int(rank_text), {"name": name, "value": None, "raw_teams": [], "texts": [], "position": None})
            entry["value"] = number_of(re.sub(r"[^\d.,]", "", row[value_col].text) or "0")
            for col in team_cols:
                entry["raw_teams"].append(row[col].raw)
                entry["texts"].append(row[col].text)
            if pos_col is not None:
                entry["position"] = row[pos_col].text
        ranked = []
        for rank, entry in rows.items():
            clubs, gone = clubs_in(" ".join(entry["raw_teams"]))
            item = {"rank": rank, "name": entry["name"], "value": entry["value"]}
            if entry["position"]:
                item["position"] = entry["position"]
            years = career_years(" ".join(entry["texts"]))
            if years:
                item["years"] = years
            item["clubs"] = clubs
            if gone:
                item["defunct_or_moved_teams"] = gone
            ranked.append(item)
            if len(ranked) == TOP_N:
                break
        out[category] = ranked
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Pro Football Hall of Fame inductees (through the Class of 2026)
# ---------------------------------------------------------------------------------------------------------------------
HOF_THROUGH_CLASS = 2026
HOF_POSITION_EXTRA = {"end": "WR", "offensive end": "WR", "split end": "WR", "flanker": "WR", "halfback": "HB", "tackle": "T",
                      "defensive back": "CB", "placekicker": "K", "kicker": "K", "punter": "P", "middle linebacker": "ILB",
                      "outside linebacker": "OLB", "nose tackle": "DT", "wide receiver": "WR", "tight end": "TE",
                      "offensive tackle": "T", "guard": "G", "center": "C", "fullback": "FB", "quarterback": "QB",
                      "running back": "HB", "linebacker": "OLB", "cornerback": "CB", "safety": "SS", "free safety": "FS",
                      "defensive end": "DE", "defensive tackle": "DT", "return specialist": "WR", "kick returner": "WR",
                      "defensive middle guard": "DT", "middle guard": "DT"}
NON_PLAYER = re.compile(r"coach|owner|founder|co-founder|commissioner|executive|general manager|administrator|president|"
                        r"organizer|supervisor|official|director|personnel|contributor|publicist|scout", re.I)
HOF_MARKS = (("**", "first_year_of_eligibility"), ("^", "first_year_as_finalist"), ("§", "charter_member"),
             ("†", "centennial_slate"))


def hof_position_code(text: str) -> str | None:
    first = re.split(r"[/,]", text.lower())[0].strip()
    first = re.sub(r"\s+", " ", first)
    return HOF_POSITION_EXTRA.get(first) or POSITION_WORDS.get(first)


def span_years(text: str) -> tuple[int, int] | None:
    years = [int(y) for y in re.findall(r"\b(19[0-9]{2}|20[0-2][0-9])\b", text)]
    return (min(years), max(years)) if years else None


def build_hall_of_fame(wiki: WikiSources) -> dict[str, Any]:
    table = max(parse_tables(wiki.text("wiki_hof")), key=len)
    groups: list[list[list[Cell]]] = []
    last = None
    for row in table[1:]:
        if row[0] is not last:
            groups.append([])
            last = row[0]
        groups[-1].append(row)
    members = []
    for group in groups:
        head = group[0]
        raw_name = head[0].raw
        marks = [flag for mark, flag in HOF_MARKS if mark in strip_markup(raw_name) or (mark == "**" and "D4EDFF" in head[0].attrs.get("style", ""))]
        name = clean_name(re.sub(r"[\*\^§†‡#]+", "", strip_markup(raw_name)))
        cls = int(head[1].text)
        positions = []
        for row in group:
            text = row[2].text
            if text and text not in positions:
                positions.append(text)
        stints = []
        for row in group:
            club = clubs_in(row[3].raw)[0]
            team = re.sub(r"\s*/\s*", " / ", row[3].text.replace("/ /", "/")).strip()
            years = re.sub(r"\s+", "", row[4].text).replace("–", "-").replace("—", "-")
            stints.append({"team": team, "club": club[0] if club else None, "years": years})
        weights: dict[str, int] = collections.Counter()
        for stint in stints:
            span = span_years(stint["years"])
            if stint["club"] and span:
                weights[stint["club"]] += span[1] - span[0] + 1
        primary = max(weights.items(), key=lambda kv: (kv[1], kv[0]))[0] if weights else None
        first_position = positions[0] if positions else ""
        player = bool(first_position) and not NON_PLAYER.search(first_position)
        member: dict[str, Any] = {"name": name, "class": cls, "category": "player" if player else
                                  ("coach" if re.search(r"coach", first_position, re.I) else "contributor"),
                                  "positions": positions, "position": hof_position_code(first_position) if player else None,
                                  "club": primary, "stints": stints}
        if marks:
            member["flags"] = marks
        members.append(member)
    members.sort(key=lambda m: (m["class"], m["name"]))
    return {"through_class": HOF_THROUGH_CLASS, "members": members}


# ---------------------------------------------------------------------------------------------------------------------
# nflverse player statistics (1999..2025): the second source for the records and leaders
# ---------------------------------------------------------------------------------------------------------------------
STATS_FIRST, STATS_LAST = 1999, 2025
NFLVERSE_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_%d.csv.gz"
NFLVERSE_PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
METRICS = ("passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "receptions", "receiving_yards", "receiving_tds",
           "def_sacks", "def_interceptions", "def_tackles_solo", "def_tackle_assists", "fg_made", "pat_made",
           "special_teams_tds", "def_tds", "passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions",
           "def_safeties")
NFLVERSE_TEAM = {"LA": "LAR", "STL": "LAR", "SD": "LAC", "OAK": "LV", "LAC": "LAC", "LV": "LV", "LAR": "LAR", "ARZ": "ARI",
                 "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "SL": "LAR"}


def nflverse_file(directory: Path, name: str, url: str, digest: str | None) -> bytes:
    path = Path(directory) / name
    if path.is_file():
        raw = path.read_bytes()
    else:
        raw = http_get(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    if digest is not None and sha256_hex(raw) != digest:
        raise SystemExit(f"{name}: SHA-256 {sha256_hex(raw)} is not the pinned {digest}")
    return raw


def same_person(a: str, b: str) -> bool:
    """True when two spellings name one person: equal after normalising, or one is the other plus a nickname/middle name."""

    x, y = norm_name(a).split(), norm_name(b).split()
    if not x or not y:
        return False
    return x == y or (x[-1] == y[-1] and (set(x) <= set(y) or set(y) <= set(x)))


def norm_name(text: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'’`\"]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in ("jr", "sr", "ii", "iii", "iv", "v")]
    out, buf = [], ""
    for t in toks:                                       # "t j watt" -> "tj watt"
        if len(t) == 1:
            buf += t
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(t)
    if buf:
        out.append(buf)
    return " ".join(out)


class Stats:
    """Regular-season player lines from nflverse ``stats_player_week_<season>.csv.gz`` plus ``players.csv``."""

    def __init__(self, directory: Path, pins: dict[str, dict]):
        import gzip
        self.lines: list[tuple] = []         # (pid, season, week, game_id, team, name, position, metrics tuple)
        self.names: dict[str, str] = {}
        for season in range(STATS_FIRST, STATS_LAST + 1):
            name = f"stats_player_week_{season}.csv.gz"
            raw = nflverse_file(directory, name, NFLVERSE_STATS_URL % season, pins[name]["sha256"])
            text = gzip.decompress(raw).decode("utf-8")
            for row in csv.DictReader(io.StringIO(text, newline="")):
                if row["season_type"] != "REG":
                    continue
                pid = row["player_id"]
                self.names[pid] = row["player_display_name"]
                self.lines.append((pid, season, int(row["week"]), row["game_id"], NFLVERSE_TEAM.get(row["team"], row["team"]),
                                   row["player_display_name"], row["position"],
                                   tuple(float(row[m] or 0) for m in METRICS)))
        raw = nflverse_file(directory, "players.csv", NFLVERSE_PLAYERS_URL, pins["players.csv"]["sha256"])
        self.players = {r["gsis_id"]: r for r in csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))}
        self._season: dict[tuple[str, int], list[float]] | None = None
        self._ix = {m: i for i, m in enumerate(METRICS)}

    # --- derived metrics -----------------------------------------------------------------------------------------
    def value(self, metrics: tuple, metric: str) -> float:
        g = lambda m: metrics[self._ix[m]]
        if metric == "tackles":
            return g("def_tackles_solo") + g("def_tackle_assists")
        if metric == "points":
            return (6 * (g("rushing_tds") + g("receiving_tds") + g("special_teams_tds") + g("def_tds")) + g("pat_made")
                    + 3 * g("fg_made") + 2 * (g("passing_2pt_conversions") * 0 + g("rushing_2pt_conversions")
                                              + g("receiving_2pt_conversions")) + 2 * g("def_safeties"))
        key = {"sacks": "def_sacks", "interceptions": "def_interceptions", "field_goals": "fg_made"}.get(metric, metric)
        return g(key)

    def season_totals(self, metric: str) -> dict[tuple[str, int], float]:
        out: dict[tuple[str, int], float] = collections.defaultdict(float)
        for pid, season, _w, _g, _t, _n, _p, m in self.lines:
            out[(pid, season)] += self.value(m, metric)
        return out

    def career_totals(self, metric: str) -> dict[str, float]:
        out: dict[str, float] = collections.defaultdict(float)
        for pid, _s, _w, _g, _t, _n, _p, m in self.lines:
            out[pid] += self.value(m, metric)
        return out

    def team_of(self, pid: str, season: int) -> str | None:
        counts = collections.Counter(t for p, s, _w, _g, t, _n, _pos, _m in self.lines if p == pid and s == season)
        return counts.most_common(1)[0][0] if counts else None


YARD_METRICS = {"passing_yards", "rushing_yards", "receiving_yards"}
# category -> (annual leaders page key, regular expression for the value column's header)
ANNUAL_SPECS = {
    "passing_yards": ("wiki_annual_passing_yards", r"yards"), "passing_tds": ("wiki_annual_passing_tds", r"touchdown"),
    "rushing_yards": ("wiki_annual_rushing_yards", r"yards"), "rushing_tds": ("wiki_annual_rushing_tds", r"touchdown"),
    "receptions": ("wiki_annual_receptions", r"receptions"), "receiving_yards": ("wiki_annual_receiving_yards", r"yards"),
    "receiving_tds": ("wiki_annual_receiving_tds", r"touchdown"), "sacks": ("wiki_annual_sacks", r"sacks"),
    "interceptions": ("wiki_annual_interceptions", r"^interceptions$"), "points": ("wiki_annual_points", r"points"),
}


def close_enough(category: str, mine: float, theirs: float) -> bool:
    """Counts must agree exactly; nflverse yardage sums play-by-play and may differ a little from the official figure."""

    if category in YARD_METRICS:
        return abs(mine - theirs) <= max(2.0, 0.0015 * theirs)
    if category == "sacks":                                    # nflverse counts some half sacks differently
        return abs(mine - theirs) <= 1.0
    return abs(mine - theirs) < 1e-9


def annual_leaders(wiki: WikiSources, category: str) -> list[dict[str, Any]]:
    """Season leaders from the pinned annual list: [{season, name, team, club, value}] for every season of the table."""

    key, header_re = ANNUAL_SPECS[category]
    out = []
    for table in parse_tables(drop_refs(wiki.text(key))):
        if len(table) < 20:
            continue
        header = [c.text.lower() for c in table[0]]
        value_col = next((i for i, h in enumerate(header) if re.search(header_re, h) and not re.search(r"games|returned|average", h)), None)
        team_col = next((i for i, h in enumerate(header) if h == "team"), None)
        if value_col is None or team_col is None:
            continue
        for row in table[1:]:
            m = re.match(r"(\d{4})$", row[0].text.strip())
            num = re.search(r"\d[\d,]*(?:\.\d+)?", row[value_col].raw.replace("{{nts|", "").replace("}}", "")) if row[value_col].raw else None
            if not m or not num:
                continue
            clubs = clubs_in(row[team_col].raw)[0]
            out.append({"season": int(m.group(1)), "name": clean_name(strip_markup(row[1].raw)), "team": row[team_col].text,
                        "club": clubs[0] if clubs else None, "value": number_of(num.group(0))})
        if out:
            break
    return out


def verify_records(records: list[dict], stats: "Stats", games_date: dict[str, str],
                   annual: dict[str, list[dict]]) -> list[dict]:
    """What the second sources say about every record. Statuses:

    ``exact``: same value and holder in nflverse (or in the annual list for older seasons); ``within_stat_correction``: yardage
    within 0.15 percent; ``official_differs``: nflverse sums more yards for another player (it sums play-by-play, not the
    official figures) but the pinned annual leaders list agrees with the record; ``not_exceeded``: the record is older than the
    data and nothing since 1998 beats it; ``partial``: a career that began before 1999 (nflverse is no more than the record);
    ``single_source``: only the record page speaks; ``mismatch``: a disagreement (the build refuses to finish)."""

    results = []
    season_cache: dict[str, dict] = {}
    for rec in records:
        category, scope, value = rec["category"], rec["scope"], rec["value"]
        status, detail = "single_source", "record page only"
        extra: dict[str, Any] = {}
        if scope == "season" and category in annual:
            best = max(r["value"] for r in annual[category])
            tops = [r for r in annual[category] if r["value"] == best]
            want = {(norm_name(h["name"]), h["season"]) for h in rec["holders"]}
            got = {(norm_name(r["name"]), r["season"]) for r in tops}
            matched = all(any(same_person(h["name"], r["name"]) and r["season"] == h["season"] for r in tops) for h in rec["holders"])
            if best == value and matched:
                status, detail = "exact", f"annual leaders list: {sorted(got)}"
                for holder in rec["holders"]:
                    row = next((r for r in tops if same_person(r["name"], holder["name"]) and r["season"] == holder["season"]), None)
                    if row:
                        holder.setdefault("team", row["team"])
                        if row["club"]:
                            holder.setdefault("club", row["club"])
            else:
                status, detail = "mismatch", f"annual list best {best} {sorted(got)} vs record {value} {sorted(want)}"
        if rec["category"] != "tackles":
            if scope == "season":
                totals = season_cache.setdefault(category, stats.season_totals(category))
                best = max(totals.values())
                top = [(pid, s) for (pid, s), v in totals.items() if v == best]
                names_top = {(norm_name(stats.names[p]), s) for p, s in top}
                in_range = [h for h in rec["holders"] if h["season"] >= STATS_FIRST]
                if in_range:
                    ok = all((norm_name(h["name"]), h["season"]) in names_top for h in in_range) and close_enough(category, best, value)
                    if ok:
                        status = "exact" if best == value else "within_stat_correction"
                        detail = (detail + "; " if detail != "record page only" else "") + f"nflverse: {sorted(names_top)} {best:g}"
                        for p, season in top:
                            for holder in in_range:
                                if norm_name(holder["name"]) == norm_name(stats.names[p]) and holder["season"] == season:
                                    holder.setdefault("club", stats.team_of(p, season))
                    elif status == "exact":                    # the annual list agrees; nflverse sums other yards
                        status = "official_differs"
                        detail += f"; nflverse best {best:g} by {sorted(names_top)}"
                    else:
                        status, detail = "mismatch", f"nflverse best {best:g} by {sorted(names_top)}, record {value}"
                elif status == "single_source" or status == "exact":
                    if best <= value:
                        status = "exact" if status == "exact" else "not_exceeded"
                        detail += f"; nflverse best since {STATS_FIRST}: {best:g}"
                    else:
                        status, detail = "mismatch", f"nflverse best {best:g} exceeds the record {value}"
            elif scope == "game":
                best, top = -1.0, []
                for pid, season, week, game_id, team, name, pos, m in stats.lines:
                    v = stats.value(m, category)
                    if v > best:
                        best, top = v, []
                    if v == best:
                        top.append((name, season, game_id, team))
                in_range = [h for h in rec["holders"] if h["season"] >= STATS_FIRST]
                if in_range:
                    want = {(norm_name(h["name"]), h.get("date")) for h in in_range}
                    got = {(norm_name(n), games_date.get(g)) for n, _s, g, _t in top}
                    if best >= value and want <= got:
                        status = "exact" if got == want else "exact_with_more"
                        detail = f"nflverse: {sorted(got)}"
                        for n, _s, g, team in top:
                            for holder in in_range:
                                if norm_name(holder["name"]) == norm_name(n) and holder.get("date") == games_date.get(g):
                                    holder.setdefault("club", team)
                    else:
                        status, detail = "mismatch", f"nflverse best {best:g} by {sorted(got)}, record {value} {sorted(want)}"
                else:
                    if best <= value:
                        status, detail = "not_exceeded", f"nflverse best since {STATS_FIRST}: {best:g}"
                    else:
                        status, detail = "mismatch", f"nflverse best {best:g} exceeds the record {value}"
            else:
                totals = stats.career_totals(category)
                name = norm_name(rec["holders"][0]["name"])
                first_year = int(str(rec["holders"][0].get("seasons", "0-0")).split("-")[0])
                mine = [(v, pid) for pid, v in totals.items() if norm_name(stats.names[pid]) == name]
                rookies = [(v, pid) for v, pid in mine if int(stats.players.get(pid, {}).get("rookie_season") or 0) in range(first_year - 1, first_year + 2)]
                if not rookies:
                    status, detail = ("single_source", "holder's career has no nflverse lines") if first_year < STATS_FIRST - 1 else ("mismatch", "no nflverse holder")
                else:
                    v, pid = max(rookies)
                    if first_year >= STATS_FIRST:
                        status = "exact" if close_enough(category, v, value) and v == value else (
                            "within_stat_correction" if close_enough(category, v, value) else "mismatch")
                    else:
                        status = "partial" if v <= value else "mismatch"
                    detail = f"nflverse {STATS_FIRST}+ total {v:g} (career began {first_year})"
        elif scope != "season":
            status, detail = "single_source", "tackles are not complete in nflverse; record page only"
        results.append({"id": rec["id"], "status": status, "detail": detail, **extra})
    return results


def verify_leaders(leaders: dict[str, list[dict]], records: list[dict], stats: "Stats") -> list[dict]:
    """Each leader list against its record row and nflverse career totals (same status words as ``verify_records``)."""

    results = []
    record_value = {r["category"]: r["value"] for r in records if r["scope"] == "career"}
    for category, rows in leaders.items():
        if rows and category in record_value and rows[0]["value"] != record_value[category]:
            results.append({"id": f"{category}.rank1", "status": "mismatch",
                            "detail": f"leader list {rows[0]['value']} vs record page {record_value[category]}"})
        totals = stats.career_totals(category) if category != "tackles" else {}
        for row in rows:
            ident = f"{category}.rank{row['rank']}"
            if category == "tackles":
                results.append({"id": ident, "status": "single_source", "detail": "tackles are not complete in nflverse"})
                continue
            name = norm_name(row["name"])
            first_year = int((row.get("years") or "0-0").split("-")[0])
            candidates = [(v, pid) for pid, v in totals.items() if norm_name(stats.names[pid]) == name and
                          int(stats.players.get(pid, {}).get("rookie_season") or 0) in range(first_year - 1, first_year + 2)]
            if not candidates:
                results.append({"id": ident, "status": "single_source" if first_year < STATS_FIRST - 1 else "mismatch",
                                "detail": f"{row['name']}: no nflverse career starting about {first_year}"})
                continue
            v, pid = max(candidates)
            if first_year >= STATS_FIRST:
                status = "exact" if v == row["value"] else ("within_stat_correction" if close_enough(category, v, row["value"]) else "mismatch")
            else:
                status = "partial" if v <= row["value"] else "mismatch"
            results.append({"id": ident, "status": status,
                            "detail": f"{row['name']}: nflverse {STATS_FIRST}+ total {v:g}, list {row['value']}"})
    return results


# ---------------------------------------------------------------------------------------------------------------------
# Pins and assembly
# ---------------------------------------------------------------------------------------------------------------------
PINS_PATH = Path(__file__).resolve().with_name("b780_history_seed_pins.json")


def load_pins(path: Path = PINS_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def wiki_pins(pins: dict) -> dict[str, tuple[str, int, str]]:
    return {k: (v["title"], v["revision"], v["sha256"]) for k, v in pins["wikipedia"].items()}


def standings_manifest(pins: dict) -> dict[str, Any]:
    keys = sorted(k for k in pins["wikipedia"] if k.startswith("standings_"))
    lines = [f"{k}\t{pins['wikipedia'][k]['title']}\t{pins['wikipedia'][k]['revision']}\t{pins['wikipedia'][k]['sha256']}"
             for k in keys]
    return {"pages": len(keys), "seasons": f"{FIRST_SEASON}-{LAST_SEASON}",
            "manifest_sha256": sha256_hex("\n".join(lines).encode("utf-8")),
            "manifest": "tools/b780_history_seed_pins.json, keys standings_<season>_<division>",
            "title_pattern": "Template:<season> <division> standings"}


SOURCE_NOTES = {
    "wiki_mvp": "AP NFL Most Valuable Player (a shared award lists both players)",
    "wiki_opoy": "AP NFL Offensive Player of the Year", "wiki_dpoy": "AP NFL Defensive Player of the Year",
    "wiki_roy": "AP NFL Rookie of the Year, offensive and defensive tables",
    "wiki_cpoy": "AP NFL Comeback Player of the Year (2005 was shared)", "wiki_coy": "AP NFL Coach of the Year",
    "wiki_sbmvp": "Super Bowl Most Valuable Player (each game keeps its season: Super Bowl XXXVII closes season 2002)",
    "wiki_records": "NFL individual records (rushing, receiving, defense, scoring), regular season",
    "wiki_qb_records": "NFL quarterback records (passing), regular season",
    "wiki_hof": "Pro Football Hall of Fame inductees, complete through the Class of 2026",
}
# Wikipedia's final standings tables are not always right. Each difference found is explained here and listed in the output.
KNOWN_WIKIPEDIA_ERRORS = [
    {"season": 2010, "club": "Houston Texans", "field": "conf", "ours": [5, 7, 0], "wikipedia": [4, 8, 0],
     "why": "the 12 AFC games (IND, JAX and TEN twice, OAK, KC, SD, NYJ, BAL, DEN) were 5-7: five wins in 12 games, and the "
            "Texans' only NFC win was Washington; the table's 4-8 cannot hold with their 6-10 record and 3-3 division record"},
]
RULES = {
    "regular_season": "W-L-T and points from regular-season rows of the nflverse games file only; playoff games never count",
    "division_place": "1 to 4 inside the club's division by win percentage, then the NFL's written tie-break procedure applied "
                      "to the game scores: head-to-head, division record, common games (at least four), conference record, "
                      "strength of victory, strength of schedule, the two points rankings, net points in common games, net "
                      "points in all games; one list for two clubs and for three or more, and when a step leaves two of "
                      "three or more clubs the procedure restarts for those two; a club's `tiebreak` field names the step "
                      "that placed it",
    "playoffs": "the last playoff round a club played: lost_wild_card, lost_divisional, lost_conference, lost_super_bowl or "
                "champion; `bye` is set when its first game was the divisional round",
    "head_coach": "the coach with the most regular-season games; a tie goes to the coach whose game came first",
    "club_ids": "the NFL's abbreviations today (LAR, LAC, LV, WAS); `label` is what the NFL printed that season (STL, SD, OAK)",
    "awards": "every winner of the AP award that season, in the page's order (`winners[0]` when one name is needed); position "
              "codes are the 17 codes of the champions block, HC for a coach; `position_overrides` lists the linebackers and "
              "safeties whose side the pages do not name",
    "position_overrides": POSITION_OVERRIDE,
    "nfl_records": "regular-season records as the pinned Wikipedia record pages list them; ties list every holder; "
                   "`tied_players` is set where the page names only the latest of a long tie; `checks.records` says what a "
                   "second source (nflverse, the annual leaders lists) says about each",
    "check_status": {
        "exact": "the second source gives the same value and holder",
        "within_stat_correction": "nflverse yardage within 0.15 percent (it sums play-by-play, not official figures)",
        "official_differs": "nflverse sums more yards for another player; the annual leaders list agrees with the record",
        "not_exceeded": "the record is older than the data and nothing since 1998 beats it",
        "partial": "a career that began before 1999: nflverse is no more than the record",
        "exact_with_more": "nflverse also lists other players with the tied value",
        "single_source": "only the pinned Wikipedia page speaks (a career before 1999, or tackles, which were never official)"},
    "career_leaders": "regular-season career top five per category from the pinned Wikipedia leader lists; the tackle list is "
                      "unofficial (the NFL did not count tackles); `years` is first-last season, `present` while active",
    "hall_of_fame": "all inductees through the Class of 2026 as the pinned page lists them; `club` is the club (today's "
                    "franchise) with the most seasons among the member's stints, null for defunct clubs; `position` is the "
                    "first listed position as one of the 17 codes, null for coaches and contributors",
    "data_through": "the end of the 2025 season (Super Bowl LX, February 8, 2026)",
}


def split_known(problems: list[dict]) -> tuple[list[dict], list[dict]]:
    """(explained, unexplained) standings differences."""

    explained, unexplained = [], []
    for p in problems:
        hit = next((k for k in KNOWN_WIKIPEDIA_ERRORS if k["season"] == p["season"] and k["club"] == p["club"]
                    and k["field"] == p["field"] and k["ours"] == p["ours"] and k["wikipedia"] == p["wikipedia"]), None)
        (explained if hit else unexplained).append({**p, "why": hit["why"]} if hit else p)
    return explained, unexplained


def build(games_path: Path, nflverse_dir: Path, cache: Path | None, pins: dict) -> dict:
    wiki = WikiSources(wiki_pins(pins), cache)
    games, rows, _digest = load_games(games_path)
    seasons, totals = build_seasons(games)
    standings = verify_standings(seasons, wiki)
    explained, unexplained = split_known(standings["problems"])
    if unexplained:
        raise SystemExit("standings differ from Wikipedia:\n  " + "\n  ".join(json.dumps(p) for p in unexplained))
    awards = build_awards(wiki)
    records = build_records(wiki)
    leaders = build_leaders(wiki)
    hof = build_hall_of_fame(wiki)
    stats = Stats(nflverse_dir, pins["nflverse"]["files"])
    game_dates = {r["game_id"]: r["gameday"] for r in rows}
    annual = {c: annual_leaders(wiki, c) for c in ANNUAL_SPECS}
    record_checks = verify_records(records, stats, game_dates, annual)
    leader_checks = verify_leaders(leaders, records, stats)
    bad = [c for c in record_checks + leader_checks if c["status"] == "mismatch"]
    if bad:
        raise SystemExit("second-source mismatches:\n  " + "\n  ".join(f"{c['id']}: {c['detail']}" for c in bad))
    sources: dict[str, Any] = {"nflverse_games": {
        **NFLVERSE_GAMES, "used_rows": f"seasons {FIRST_SEASON}..{LAST_SEASON}",
        "used_rows_sha256": games_subset_digest(rows, USED_FIELDS), "used_fields": list(USED_FIELDS)}}
    described = wiki.describe()
    for key in sorted(k for k in wiki.used if not k.startswith("standings_")):
        sources[key] = {**described[key], **({"note": SOURCE_NOTES[key]} if key in SOURCE_NOTES else {})}
    sources["nflverse_stats"] = {
        "title": "nflverse weekly player statistics 1999..2025 and the players table", "publisher": "nflverse",
        "license": "CC-BY-4.0", "repository": "https://github.com/nflverse/nflverse-data",
        "downloaded": pins["nflverse"]["downloaded"], "files": pins["nflverse"]["files"]}
    clubs = []
    for club in CLUB_IDS:
        nickname, division = CLUB_TABLE[club]
        clubs.append({"id": club, "arena_index": ARENA_NICKNAMES.index(nickname), "nickname_2004": nickname,
                      "division": division,
                      "names": [{"first": a, "last": b, "name": n} for a, b, n in CLUB_NAMES_ALL[club]],
                      "totals_2002_2025": totals[club]})
    return {
        "schema": SCHEMA, "base_year": BASE_YEAR, "first_season": FIRST_SEASON, "last_season": LAST_SEASON,
        "rules": RULES, "sources": sources, "clubs": clubs, "playoff_codes": list(PLAYOFF_CODES), "seasons": seasons,
        "awards": {"kinds": [{"id": a, "label": label, "source": key} for a, label, key, _h in AWARDS], "winners": awards},
        "nfl_records": records, "nfl_career_leaders": leaders, "hall_of_fame": hof,
        "checks": {"standings": {**standings_manifest(pins), "compared_club_seasons": standings["compared"],
                                 "differences": explained},
                   "records": record_checks, "career_leaders": leader_checks}}


def ensure_games(cache: Path, given: Path | None) -> Path:
    if given:
        return Path(given)
    path = Path(cache) / "games.csv"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(http_get(NFLVERSE_GAMES["url"]))
    return path


def main(argv: list[str] | None = None) -> int:
    import tempfile
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--games", type=Path, help="nflverse games.csv at the pinned commit (downloaded when absent)")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "b780_history_seed",
                        help="folder for the pinned Wikipedia texts and nflverse files (network on a miss)")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--pins", type=Path, default=PINS_PATH)
    parser.add_argument("--check", action="store_true", help="rebuild and compare with the committed file; write nothing")
    args = parser.parse_args(argv)
    pins = load_pins(args.pins)
    cache = Path(args.cache)
    games = ensure_games(cache, args.games)
    document = build(games, cache / "nflverse", cache / "wikipedia", pins)
    text = dumps(document) + "\n"
    if args.check:
        have = json.loads(Path(args.out).read_text(encoding="utf-8"))
        if have != json.loads(text):
            print("the committed file differs from a fresh build", file=sys.stderr)
            return 1
        print("committed file equals a fresh build")
        return 0
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
