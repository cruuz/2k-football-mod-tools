#!/usr/bin/env python3
"""Build ``data/nfl2k5_franchise_leaders_2026.json`` (job b780 j5b-leaders): each club's all-time career leaders and
single-season / single-game record holders, shipped only where two sources agree.

What is built
  * career: the club's top 3 in ten categories (passing yards and touchdowns, rushing yards and touchdowns, receptions,
    receiving yards and touchdowns, sacks, interceptions, tackles), regular season, through the 2025 season;
  * season and game: the club's record holder in the same ten categories.
Category ids and the half-sack unit are the ones of the franchise extension footer (``nfl2k5_franchise_extension``
LEADER_CATEGORIES / RECORD_CATEGORIES); club ids are the history seed's (``data/nfl2k5_history_2026.json``).
Nothing here is invented or recalled from memory; every number is read from a source and checked against another.

Sources (read-only; retrieval dates and pins are in the evidence file)
  S1  the club's own 2026 media guide (Internet Archive, collection nfl-media-guides; image-only PDFs read through the Archive's
      OCR, Tesseract at 300 dpi and the page pictures, transcribed by helper agents into one JSON file per club).  The
      Steelers' 2026 guide is not online, so their 2025 edition (through 2024) is used and the 2025 season is added from nflverse.
  S2  Wikipedia: the player's NFL career statistics table, regular-season rows summed over the club (CC BY-SA 4.0).
  S3  nflverse weekly player stats 1999-2025 (CC-BY-4.0), regular season, summed per club.  Play-by-play derived, so yards and
      sacks can differ from the official numbers by a few units (Matt Forte, Bears: 8,595 against the official 8,602) and
      tackles are not comparable at all.  S3 therefore counts as a second source only on an exact match where it sees the
      whole career, and otherwise only guards against gross conflicts (``tolerance``).
Not used on purpose: Pro-Football-Reference and FootballDB (bot-blocked, HTTP 403) and StatMuse (its terms forbid automated and
manual data mining).

The two-source rule (``decide``)
  ship      S1 equals S2, or S1 equals S3 exactly where S3 sees the whole career with the club (1999-2025 only), and nothing
            contradicts it (S2 differing, S3 beyond tolerance, or an S3 total above the guide's);
  review    S1 equals S2 but S3 is beyond tolerance (not shipped, listed);
  conflict  S1 and S2 differ (not shipped, listed);
  single    only S1 exists (not shipped, listed).
A (club, scope, category) ships the longest run of consecutive ranks from rank 1 whose rows all ship (a later rank cannot be
trusted when an earlier one failed), and only when the completeness guard holds: no nflverse player who is not on the
guide's printed list has a total above the list's last printed value (for a stat the guide prints only as a column of
another list, above the third-ranked value), and no nflverse single season or game beats the guide's record.

The club files (S1) are ``data/nfl2k5_franchise_leaders_guides/<CLUB>.json``: one per club, {team, guide_ident, through_season, lists,
missing, notes}.  A list is {scope career|season|game, category (pass_yds ... tackles), title, pdf_page, kind list|column, ranked_by,
scope_note, complete_to, rows[{rank, tie, name, years, value, raw}]}: ``raw`` is the printed line, ``kind column`` means the guide prints
the stat only as a column of a list ranked by another stat.  Every one of the 30 scope/category pairs is a list or a reason in ``missing``
(``check_guide`` enforces it).  They were read from the page pictures of each guide (the Archive's OCR and Tesseract only as cross-checks).

Usage
  python3 tools/b780_franchise_leaders_build.py import-guides --src DIR      # validate transcribed files, write them to data/
  python3 tools/b780_franchise_leaders_build.py fetch-nflverse --cache DIR
  python3 tools/b780_franchise_leaders_build.py build --guides data/nfl2k5_franchise_leaders_guides --nflverse DIR --wiki-cache DIR
  python3 tools/b780_franchise_leaders_build.py verify          # offline: evidence -> decisions -> data, must equal the shipped files
  python3 tools/b780_franchise_leaders_build.py summary         # coverage tables from the shipped files
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nfl2k5_franchise_leaders_2026.json"
EVIDENCE = ROOT / "data" / "nfl2k5_franchise_leaders_evidence_2026.json"
COHORT = ROOT / "tools" / "b77" / "f12_cohort.json"
SCHEMA = "nfl2k5_franchise_leaders/v1"
EVIDENCE_SCHEMA = "nfl2k5_franchise_leaders_evidence/v1"
UA = "2k5-mod-studio-research/1.0 (hobby open-source NFL mod; repo cruuz/2k-football-mod-tools)"
THROUGH = 2025
NV_WINDOW = (1999, THROUGH)

# category ids are the footer's; sacks are kept in half sacks, the game's own unit
CATEGORIES = {
    "passing_yards": "Passing yards", "passing_td": "Passing touchdowns", "rushing_yards": "Rushing yards",
    "rushing_td": "Rushing touchdowns", "receptions": "Receptions", "receiving_yards": "Receiving yards",
    "receiving_td": "Receiving touchdowns", "sacks_half": "Sacks (half sacks)", "interceptions": "Interceptions", "tackles": "Tackles",
}
GUIDE_CATEGORY = {   # the short names the transcribed guide files use -> footer ids
    "pass_yds": "passing_yards", "pass_td": "passing_td", "rush_yds": "rushing_yards", "rush_td": "rushing_td", "rec": "receptions",
    "rec_yds": "receiving_yards", "rec_td": "receiving_td", "sacks": "sacks_half", "int": "interceptions", "tackles": "tackles",
}
SCALE = {"sacks_half": 2}          # stored units per source unit
SCOPES = ("career", "season", "game")
SLOTS = {"career": 3, "season": 1, "game": 1}
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")   # footer person codes
POSITION_OVERRIDE = {"Dexter Jackson": "FS", "Ed Reed": "FS", "Bob Sanders": "SS", "Troy Polamalu": "SS", "Ray Lewis": "ILB",
                     "Brian Urlacher": "ILB", "Patrick Willis": "ILB", "DeMeco Ryans": "ILB", "Luke Kuechly": "ILB",
                     "Darius Leonard": "ILB", "Jerod Mayo": "ILB", "Brian Cushing": "ILB"}   # the table the champions and history seeds use
DEFAULT_POSITION = {"passing_yards": "QB", "passing_td": "QB", "rushing_yards": "HB", "rushing_td": "HB", "receptions": "WR", "receiving_yards": "WR",
                    "receiving_td": "WR", "sacks_half": "DE", "interceptions": "CB", "tackles": "OLB"}   # only when no source names the position
ARENA_ORDER = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARI", "LAC", "KC", "IND", "DAL", "MIA", "PHI", "ATL", "NYG", "JAX", "NYJ",
               "DET", "GB", "CAR", "NE", "LV", "LAR", "BAL", "WAS", "NO", "SEA", "PIT", "HOU", "TEN", "MIN")

# code -> (name, nflverse team code)
CLUBS = {
    "ARI": ("Arizona Cardinals", "ARI"), "ATL": ("Atlanta Falcons", "ATL"), "BAL": ("Baltimore Ravens", "BAL"),
    "BUF": ("Buffalo Bills", "BUF"), "CAR": ("Carolina Panthers", "CAR"), "CHI": ("Chicago Bears", "CHI"),
    "CIN": ("Cincinnati Bengals", "CIN"), "CLE": ("Cleveland Browns", "CLE"), "DAL": ("Dallas Cowboys", "DAL"),
    "DEN": ("Denver Broncos", "DEN"), "DET": ("Detroit Lions", "DET"), "GB": ("Green Bay Packers", "GB"),
    "HOU": ("Houston Texans", "HOU"), "IND": ("Indianapolis Colts", "IND"), "JAX": ("Jacksonville Jaguars", "JAX"),
    "KC": ("Kansas City Chiefs", "KC"), "LV": ("Las Vegas Raiders", "LV"), "LAC": ("Los Angeles Chargers", "LAC"),
    "LAR": ("Los Angeles Rams", "LA"), "MIA": ("Miami Dolphins", "MIA"), "MIN": ("Minnesota Vikings", "MIN"),
    "NE": ("New England Patriots", "NE"), "NO": ("New Orleans Saints", "NO"), "NYG": ("New York Giants", "NYG"),
    "NYJ": ("New York Jets", "NYJ"), "PHI": ("Philadelphia Eagles", "PHI"), "PIT": ("Pittsburgh Steelers", "PIT"),
    "SF": ("San Francisco 49ers", "SF"), "SEA": ("Seattle Seahawks", "SEA"), "TB": ("Tampa Bay Buccaneers", "TB"),
    "TEN": ("Tennessee Titans", "TEN"), "WAS": ("Washington Commanders", "WAS"),
}
NV2CLUB = {nv: code for code, (_, nv) in CLUBS.items()}


# ------------------------------------------------------------------------------------------------ names and years
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’`]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t not in SUFFIXES)


def split_name(name: str):
    """'Odell Beckham Jr.' -> ('Odell', 'Beckham', 'Jr.');  'Portis' -> ('', 'Portis', '')"""
    toks = re.sub(r"\s+", " ", (name or "").replace(",", " ")).strip().split()
    suffix = ""
    if len(toks) > 1 and toks[-1].lower().strip(".") in SUFFIXES:
        suffix = toks.pop()
    if len(toks) == 1:
        return "", toks[0], suffix
    return toks[0], " ".join(toks[1:]), suffix


def parse_years(s: str, through: int = THROUGH) -> set[int]:
    """'1975-87' -> 1975..1987; '1940-41; 45-50'; "2008-16; '25"; '2017, 20-present'; '2019'; an open end ('2020-') runs to the last season."""
    out: set[int] = set()
    century = None
    for part in re.split(r"[;,]", (s or "").replace("–", "-").replace("—", "-")):
        part = part.strip().strip("()")
        m = re.fullmatch(r"'?(\d{2}|\d{4})(?:\s*-\s*(\d{4}|\d{2}|present|Pres\.?|\w*))?", part, re.I)
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        a = int(a) if len(a) == 4 else (century + int(a) if century is not None else None)
        if a is None:
            continue
        century = (a // 100) * 100
        if b is None:
            out.add(a)
        elif b == "" or b.lower().startswith("pres"):             # "2020-" and "2017-present": still on the club's list at the end of 2025
            out.update(range(a, through + 1))
        elif b.isdigit():
            e = int(b) if len(b) == 4 else century + int(b)
            out.update(range(a, (e + 100 if e < a else e) + 1))
        else:
            out.add(a)
    return {y for y in out if y <= through}               # the guides' totals end with the 2025 season ("2014-18, 26" is a 2026 roster note)


def game_date(s: str):
    """(iso date or None, season) for a game record's date text; January and February games belong to the previous season."""
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b", s or "")
    if m:
        mo, da, y = int(m.group(1)), int(m.group(2)), m.group(3)
        y = int(y) if len(y) == 4 else (1900 + int(y) if int(y) > 30 else 2000 + int(y))
        return f"{y:04d}-{mo:02d}-{da:02d}", (y - 1 if mo <= 2 else y)
    m = re.search(r"((?:19|20)\d{2})", s or "")
    return None, (int(m.group(1)) if m else None)


def clean_number(v):
    return int(v) if float(v).is_integer() else round(float(v), 1)


# ------------------------------------------------------------------------------------------------ Wikipedia tables (stdlib)
# stat-table team cell -> [(club, first_year, last_year)]; a None club = known ambiguous
def _a(c, a=1900, b=3000):
    return (c, a, b)


ABBR = {
    "ARI": [_a("ARI")], "ARZ": [_a("ARI")], "PHX": [_a("ARI")], "PHO": [_a("ARI")], "CRD": [_a("ARI")], "CHC": [_a("ARI")],
    "STL": [_a("ARI", 1960, 1987), _a("LAR", 1995, 2015)], "ATL": [_a("ATL")],
    "BAL": [_a("IND", 1953, 1983), _a("BAL", 1996)], "BLC": [_a("IND")], "BLT": [_a("BAL")], "RAV": [_a("BAL")],
    "BUF": [_a("BUF")], "CAR": [_a("CAR")], "CHI": [_a("CHI")], "CIN": [_a("CIN")], "CLE": [_a("LAR", 1936, 1945), _a("CLE", 1946)], "CLV": [_a("CLE")],
    "DAL": [(None, 1960, 1962), _a("DAL", 1963)], "DTX": [_a("KC")], "DAT": [_a("KC")], "DEN": [_a("DEN")], "DET": [_a("DET")], "GB": [_a("GB")], "GNB": [_a("GB")],
    "HOU": [_a("TEN", 1960, 1996), _a("HOU", 2002)], "HST": [_a("HOU")], "IND": [_a("IND", 1984)], "TEN": [_a("TEN", 1997)],
    "OTI": [_a("TEN", 1997)], "HOI": [_a("TEN")], "JAX": [_a("JAX")], "JAC": [_a("JAX")],
    "KC": [_a("KC")], "KAN": [_a("KC")], "DLT": [_a("KC")],
    "LV": [_a("LV")], "OAK": [_a("LV")], "RAI": [_a("LV")], "LVR": [_a("LV")],
    "LAC": [_a("LAC")], "SD": [_a("LAC")], "SDG": [_a("LAC")], "RAM": [_a("LAR")],
    "LAR": [_a("LAR", 1946, 1981), (None, 1982, 1994), _a("LAR", 1995)],       # some articles write LAR for the Los Angeles Raiders too
    "LA": [_a("LAR", 1946, 1981), (None, 1982, 1994), _a("LAR", 2016)],
    "MIA": [_a("MIA")], "MIN": [_a("MIN")], "NE": [_a("NE")], "NWE": [_a("NE")], "BOS": [_a("NE", 1960, 1970)], "NO": [_a("NO")], "NOR": [_a("NO")],
    "NYG": [_a("NYG")], "NYJ": [_a("NYJ")], "NYT": [_a("NYJ")], "PHI": [_a("PHI")], "PIT": [_a("PIT")],
    "SF": [_a("SF")], "SFO": [_a("SF")], "SEA": [_a("SEA")], "TB": [_a("TB")], "TAM": [_a("TB")],
    "WAS": [_a("WAS")], "WSH": [_a("WAS")],
}
# CLE before 1946 is the Cleveland Rams (the Browns began in 1946); BOS is the Boston Patriots 1960-70; DAT is the Dallas Texans (the Chiefs franchise)
AMBIGUOUS_SETS = {"LA": {"LAR", "LV"}, "LAR": {"LAR", "LV"}, "DAL": {"DAL", "KC"}}      # who an ambiguous cell may be (the Rams or the Raiders, 1982-94; the Cowboys or the Texans, 1960-62)
NICK = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF", "panthers": "CAR", "bears": "CHI", "bengals": "CIN",
    "browns": "CLE", "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB", "texans": "HOU", "colts": "IND",
    "jaguars": "JAX", "chiefs": "KC", "raiders": "LV", "chargers": "LAC", "rams": "LAR", "dolphins": "MIA", "vikings": "MIN",
    "patriots": "NE", "saints": "NO", "giants": "NYG", "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "49ers": "SF",
    "seahawks": "SEA", "buccaneers": "TB", "titans": "TEN", "oilers": "TEN", "redskins": "WAS", "commanders": "WAS",
}


def club_of_cell(cell: str, year):
    """Franchise code for a stat-table team cell, 'AMBIG' when the abbreviation is ambiguous that year, None otherwise."""
    c = re.sub(r"[^A-Za-z0-9 .]", "", cell or "").strip()
    if not c:
        return None
    key = c.upper().replace(".", "").replace(" ", "")
    if key in ABBR:
        for club, a, b in ABBR[key]:
            if year is None or a <= year <= b:
                return club if club else "AMBIG"
        return None
    low = c.lower()
    for nick, club in NICK.items():
        if re.search(r"\b" + re.escape(nick) + r"\b", low):
            return club
    return None


def _span(value) -> int:
    """colspan / rowspan attribute -> a small positive integer (a malformed value such as '2"' reads as 2, nothing as 1)"""
    m = re.search(r"\d+", value or "")
    return max(1, min(int(m.group(0)), 60)) if m else 1


class _Tables(HTMLParser):
    """Top-level tables of an article with the nearest heading, colspan/rowspan expanded."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.depth = 0
        self.heading = ""
        self._in_heading = None
        self._hbuf = []
        self._cur = None
        self._row = None
        self._cell = None
        self._cap = None
        self._skip_stack = []
        self._pending = {}
        self._col = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._cell is not None or self._cap is not None or self._in_heading:
            style = (a.get("style") or "").replace(" ", "").lower()
            if tag in ("sup", "style", "script") or "display:none" in style or "mw-editsection" in (a.get("class") or ""):
                self._skip_stack.append(tag)
                return
        if self._skip_stack:
            self._skip_stack.append(tag)
            return
        if tag in ("h2", "h3", "h4"):
            self._in_heading = tag
            self._hbuf = []
        elif tag == "table":
            self.depth += 1
            if self.depth == 1:
                self._cur = {"heading": self.heading, "caption": "", "grid": []}
                self._pending = {}
        elif self.depth == 1 and tag == "caption":
            self._cap = []
        elif self.depth == 1 and tag == "tr":
            self._row = []
            self._col = 0
            self._fill()
        elif self.depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = {"text": [], "cs": _span(a.get("colspan")), "rs": _span(a.get("rowspan"))}
        elif tag == "br" and self._cell is not None:
            self._cell["text"].append(" ")

    def _fill(self):
        while self._col in self._pending:
            text, left = self._pending[self._col]
            self._row.append(text)
            if left > 1:
                self._pending[self._col] = (text, left - 1)
            else:
                del self._pending[self._col]
            self._col += 1

    def handle_endtag(self, tag):
        if self._skip_stack:
            self._skip_stack.pop()
            return
        if tag in ("h2", "h3", "h4") and self._in_heading == tag:
            self.heading = re.sub(r"\s+", " ", "".join(self._hbuf)).strip()
            self._in_heading = None
        elif tag == "table":
            if self.depth == 1 and self._cur is not None:
                self.tables.append(self._cur)
                self._cur = None
            self.depth = max(0, self.depth - 1)
        elif self.depth == 1 and tag == "caption" and self._cap is not None:
            if self._cur is not None:
                self._cur["caption"] = re.sub(r"\s+", " ", "".join(self._cap)).strip()
            self._cap = None
        elif self.depth == 1 and tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell["text"])).strip()
            for _ in range(self._cell["cs"]):
                self._row.append(text)
                if self._cell["rs"] > 1:
                    self._pending[self._col] = (text, self._cell["rs"] - 1)
                self._col += 1
                self._fill()
            self._cell = None
        elif self.depth == 1 and tag == "tr" and self._row is not None:
            self._fill()
            if self._cur is not None:
                self._cur["grid"].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._skip_stack:
            return
        if self._in_heading:
            self._hbuf.append(data)
        if self._cap is not None:
            self._cap.append(data)
        if self._cell is not None:
            self._cell["text"].append(data)


_TABLE_TAG = re.compile(r"<(/?)table\b[^>]*>", re.I)
_TABLE_OPEN_CLASS = re.compile(r"<table\b[^>]*\bclass=\"[^\"]*\b(?:wikitable|infobox)\b[^\"]*\"[^>]*>", re.I)
_HEADING = re.compile(r"<h([234])\b[^>]*>(.*?)</h\1>", re.I | re.S)


def html_tables(html: str):
    """Top-level wikitables and infoboxes of an article (with the nearest heading), or every table of a bare snippet.
    Only those tables are parsed: an article's references and navigation boxes are most of its HTML."""
    spans = []
    for m in _TABLE_OPEN_CLASS.finditer(html):
        if spans and m.start() < spans[-1][1]:
            continue                                            # nested inside the previous table
        depth, end = 0, None
        for t in _TABLE_TAG.finditer(html, m.start()):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                end = t.end()
                break
        if end:
            spans.append((m.start(), end))
    if not spans:
        p = _Tables()
        p.feed(html)
        return p.tables
    headings = [(h.start(), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h.group(2))).strip()) for h in _HEADING.finditer(html)]
    out = []
    for a, b in spans:
        heading = ""
        for pos, text in headings:
            if pos < a:
                heading = text
            else:
                break
        p = _Tables()
        p.heading = heading
        p.feed(html[a:b])
        out.extend(p.tables)
    return out


def num(s):
    s = (s or "").replace(",", "").replace("−", "-").replace("–", "-").strip()
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


TD_ENDINGS = (" td", " tds", " touchdowns")
SACK_WORDS = {"sck", "scks", "sacks", "sk", "sack"}


def column_map(heads):
    """footer category id -> column index for a flattened Wikipedia NFL stat-table header ('Group Column')."""
    m = {}
    for i, h in enumerate(heads):
        c = re.sub(r"\s+", " ", h.lower()).strip()
        if c in ("year", "season", "year year"):
            m.setdefault("year", i)
        elif c == "team" or c.endswith(" team"):
            m.setdefault("team", i)
        elif "passing" in c and (c.endswith(" yds") or c.endswith(" yards")):
            m.setdefault("passing_yards", i)
        elif "passing" in c and c.endswith(TD_ENDINGS):
            m.setdefault("passing_td", i)
        elif "rushing" in c and (c.endswith(" yds") or c.endswith(" yards")):
            m.setdefault("rushing_yards", i)
        elif "rushing" in c and c.endswith(TD_ENDINGS):
            m.setdefault("rushing_td", i)
        elif "receiving" in c and c.endswith(" rec"):
            m.setdefault("receptions", i)
        elif "receiving" in c and (c.endswith(" yds") or c.endswith(" yards")):
            m.setdefault("receiving_yards", i)
        elif "receiving" in c and c.endswith(TD_ENDINGS):
            m.setdefault("receiving_td", i)
        elif "sacked" not in c and (set(c.split()) & SACK_WORDS or c.endswith(" sack")):
            m.setdefault("sacks_half", i)
        elif "tackles" in c and (c.endswith(" cmb") or c.endswith(" comb") or c.endswith(" total") or c.endswith(" tot")):
            m.setdefault("tackles", i)
        elif c in ("tackles", "tkl", "tot tackles", "total tackles", "tackles tkl", "combined tackles", "ttkl", "comb", "cmb"):
            m.setdefault("tackles", i)
        elif "interceptions" in c and c.endswith(" int"):
            m.setdefault("interceptions", i)
        elif c in ("int", "ints", "interceptions"):
            m.setdefault("interceptions", i)
    return m


def flat_groups(heads):
    """A header row without group names ('Att Yds Avg Lng TD Rec Yds Avg Lng TD') gets them by position: a block that starts with
    Cmp is passing, an Att block is rushing, a Rec block is receiving."""
    out, group = [], None
    for h in heads:
        c = h.strip().lower()
        if c in ("cmp", "comp"):
            group = "Passing"
        elif c in ("att", "carries") and group != "Passing":
            group = "Rushing"
        elif c in ("rec", "receptions"):
            group = "Receiving"
        elif c in ("rtg", "rate"):
            out.append("Passing " + h)
            group = "Rushing"
            continue
        out.append(f"{group} {h}" if group and c in ("att", "cmp", "comp", "yds", "yards", "avg", "lng", "td", "tds", "touchdowns", "rec", "int", "pct", "y/a") else h)
    return out


def player_tables(source):
    """NFL career stat tables of a player article (HTML text or the tables ``html_tables`` made of it):
    {'heads', 'cmap', 'rows', 'heading', 'post', 'total'} (total is the table's own Total or Career row; offense columns are only mapped for offense tables and defense columns only for
    defense tables, so a quarterback's 'Sacks' are not defensive sacks)."""
    out = []
    for t in (html_tables(source) if isinstance(source, str) else source):
        g = t["grid"]
        if len(g) < 3:
            continue
        hdr = []
        for r in g[:3]:
            first = (r[0] if r else "").strip().lower()
            if first in ("year", "season") or (hdr and not re.match(r"^(19|20)\d{2}", first or "") and first not in ("career", "total", "totals")):
                hdr.append(r)
            elif hdr:
                break
        if not hdr:
            continue
        n = max(len(r) for r in g)
        heads = []
        for ci in range(n):
            parts = []
            for r in hdr:
                if ci < len(r) and r[ci] and (not parts or parts[-1] != r[ci]):
                    parts.append(r[ci])
            heads.append(" ".join(parts))
        if len(hdr) == 1 and not any(w in " ".join(heads).lower() for w in ("passing", "rushing", "receiving", "tackles", "interceptions")):
            heads = flat_groups(heads)
        cm = column_map(heads)
        if "team" not in cm or "year" not in cm:
            continue
        low = " ".join(h.lower() for h in heads)
        offense = any(w in low for w in ("passing", "rushing", "receiving"))
        defensive = ("tackles" in low or "interceptions" in low or "defense" in low or "defensive" in low
                     or (not offense and re.search(r"\bint\b", low) is not None))
        if not defensive:
            for k in ("sacks_half", "tackles", "interceptions"):
                cm.pop(k, None)
        heading = (t["heading"] + " " + t["caption"]).lower()
        post = bool(re.search(r"post ?season|playoff|super bowl", heading)) or "opp" in low.split()
        rows = [r for r in g[len(hdr):] if r and re.match(r"^(19|20)\d{2}", r[0])]
        total = next((r for r in reversed(g[len(hdr):]) if r and r[0].strip().lower() in ("career", "total", "totals")), None)
        out.append({"heads": heads, "cmap": cm, "rows": rows, "heading": t["heading"], "post": post, "total": total})
    return out


def club_sums(source, club: str, through: int = THROUGH, guide_years=None):
    """Regular-season stat rows of a player article (HTML or its tables) that belong to `club` -> sums, per-season values, seasons seen
    (sacks are returned in half sacks).  A team cell that is ambiguous that year ("LA" 1982-94: Rams or Raiders; "DAL" 1960-62: Cowboys or
    Texans) counts for `club` when the club's printed seasons include that year, or else when the player's clear rows name `club` and not
    the other club of the pair.  Only identity is decided this way; the values are still checked against the sources."""
    parsed, others, amb = [], set(), 0
    for t in player_tables(source):
        if t["post"]:
            continue
        cm = t["cmap"]
        for r in t["rows"]:
            ym = re.match(r"^((?:19|20)\d{2})", r[0])
            if not ym or len(r) <= cm["team"]:
                continue
            yr = int(ym.group(1))
            if yr > through:
                continue
            who = club_of_cell(r[cm["team"]], yr)
            if who is None:
                continue
            if who != "AMBIG":
                others.add(who)
            vals = {}
            for cat in CATEGORIES:
                if cat in cm and cm[cat] < len(r):
                    v = num(r[cm[cat]])
                    if v is not None:
                        vals[cat] = v * SCALE.get(cat, 1)
            key = re.sub(r"[^A-Za-z0-9]", "", r[cm["team"]]).upper()
            parsed.append((who, yr, vals, key))
    rows, years = {}, set()
    for who, yr, vals, key in parsed:
        if who == "AMBIG":
            amb += 1
            pair = AMBIGUOUS_SETS.get(key, set())
            ours = club in pair and ((guide_years and yr in guide_years) or (club in others and not ((pair - {club}) & others)))
            if not ours:
                continue
        elif who != club:
            continue
        years.add(yr)
        for cat, v in vals.items():
            rows.setdefault(cat, {}).setdefault(yr, v)               # a season repeated in a second table counts once
    return {"sums": {c: sum(by.values()) for c, by in rows.items()}, "seasons": {c: {str(y): v for y, v in by.items()} for c, by in rows.items()},
            "years": sorted(years), "ambiguous": amb}


POSITION_WORDS = [("middle linebacker", "ILB"), ("inside linebacker", "ILB"), ("outside linebacker", "OLB"), ("linebacker", "OLB"),
                  ("quarterback", "QB"), ("running back", "HB"), ("halfback", "HB"), ("tailback", "HB"), ("fullback", "FB"),
                  ("wide receiver", "WR"), ("wingback", "WR"), ("flanker", "WR"), ("split end", "WR"), ("tight end", "TE"),
                  ("defensive end", "DE"), ("defensive tackle", "DT"), ("nose tackle", "DT"), ("defensive lineman", "DE"),
                  ("cornerback", "CB"), ("free safety", "FS"), ("strong safety", "SS"), ("safety", "SS"), ("defensive back", "CB"),
                  ("placekicker", "K"), ("kicker", "K"), ("punter", "P"), ("offensive tackle", "T"), ("guard", "G"), ("center", "C"),
                  ("kick returner", "WR"), ("return specialist", "WR"), ("end", "WR")]


def position_code(text: str):
    """footer position code for an infobox 'Position' text (the first position named), or None"""
    t = (text or "").lower()
    best = None
    for word, code in POSITION_WORDS:
        for m in re.finditer(r"\b" + re.escape(word) + r"\b", t):
            if best is None or m.start() < best[0] or (m.start() == best[0] and len(word) > best[1]):
                best = (m.start(), len(word), code)
    return best[2] if best else None


def infobox_position(source):
    for t in (html_tables(source) if isinstance(source, str) else source)[:4]:
        for r in t["grid"]:
            if len(r) >= 2 and r[0].strip().lower().rstrip(":") in ("position", "positions", "position(s)"):
                return r[1]
    return None


LINKS_VERSION = 2            # bumped when football_links learned titles with quote marks; cached disambiguation pages of an older version are fetched again


def football_links(html: str):
    """titles the entries of a disambiguation page link to, for the entries that say football"""
    out = []
    for li in re.findall(r"<li\b[^>]*>(.*?)</li>", html, re.S | re.I):
        if "football" not in li.lower():
            continue
        m = re.search(r"""<a\b[^>]*\btitle=(?:"([^"]+)"|'([^']+)')""", li)         # a title with quote marks inside is written with single quotes
        title = (m.group(1) or m.group(2)).replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"') if m else None
        if title and title not in out:
            out.append(title)
    return out[:8]


class Wiki:
    """Article HTML through index.php?action=render (edge cached, fast, polite gap); the API only for batched revision ids."""

    def __init__(self, cache_dir, min_gap: float = 0.25):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.gap = min_gap
        self._last = 0.0
        self._lock = threading.Lock()

    def _pace(self) -> None:
        """one global request rate (1 / gap per second) however many threads ask"""
        with self._lock:
            wait = self.gap - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()

    def _get(self, url: str):
        for attempt in range(8):
            self._pace()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90) as r:   # nosec B310 - fixed https host
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return 404, ""
                if e.code in (429, 503):
                    try:
                        wait = float(e.headers.get("Retry-After") or 0)
                    except ValueError:
                        wait = 0
                    time.sleep(max(wait, 8 * (attempt + 1)) + 1)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(4 * (attempt + 1))
        raise RuntimeError("wikipedia fetch failed: " + url)

    def path(self, title: str) -> Path:
        return self.cache / (hashlib.sha1(title.encode()).hexdigest()[:16] + ".json")

    def page(self, title: str) -> dict:
        """{'title', 'retrieved', 'revid', 'tables'} of an article (only its wikitables and infobox are kept), or {'missing': True}"""
        p = self.path(title)
        if p.exists():
            out = json.loads(p.read_text(encoding="utf-8"))
            if "html" in out:                                   # an older cache entry: keep the tables, drop the page text
                out["tables"] = html_tables(out.pop("html"))
                p.write_text(json.dumps(out), encoding="utf-8")
            if not (out.get("disambiguation") and out.get("links_v") != LINKS_VERSION):      # an older disambiguation entry is fetched again for its links
                return out
        url = "https://en.wikipedia.org/w/index.php?" + urllib.parse.urlencode({"title": title.replace(" ", "_"), "action": "render"})
        status, html = self._get(url)
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if status == 404 or not html:
            out = {"title": title, "missing": True, "retrieved": today}
        elif 'id="disambigbox"' in html or "dmbox-disambig" in html:
            out = {"title": title, "missing": True, "disambiguation": True, "retrieved": today, "football_links": football_links(html), "links_v": LINKS_VERSION}
        else:
            out = {"title": title, "revid": None, "tables": html_tables(html), "retrieved": today}
        p.write_text(json.dumps(out), encoding="utf-8")
        return out

    def fill_revids(self, titles) -> None:
        """batched revision-id lookup (<=50 titles a call) for cached pages; adds revid, canonical title, timestamp to the cache"""
        todo = []
        for t in titles:
            if self.path(t).exists():
                obj = json.loads(self.path(t).read_text(encoding="utf-8"))
                if not obj.get("missing") and obj.get("revid") is None:
                    todo.append(t)
        for i in range(0, len(todo), 50):
            chunk = todo[i:i + 50]
            q = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
                {"action": "query", "titles": "|".join(chunk), "redirects": 1, "prop": "revisions", "rvprop": "ids|timestamp", "format": "json"})
            _, body = self._get(q)
            d = json.loads(body).get("query", {})
            nm = {n["from"]: n["to"] for n in d.get("normalized", [])}
            rd = {r["from"]: r["to"] for r in d.get("redirects", [])}
            pages = {pg["title"]: pg for pg in d.get("pages", {}).values()}
            for t in chunk:
                x = nm.get(t, t)
                x = rd.get(x, x)
                pg = pages.get(x)
                if not pg or "revisions" not in pg:
                    continue
                obj = json.loads(self.path(t).read_text(encoding="utf-8"))
                obj.update({"revid": pg["revisions"][0]["revid"], "canonical_title": x, "revision_timestamp": pg["revisions"][0]["timestamp"]})
                self.path(t).write_text(json.dumps(obj), encoding="utf-8")


POS_SUFFIX = ["American football", "running back", "wide receiver", "quarterback", "linebacker", "defensive end", "cornerback",
              "safety", "tight end", "defensive tackle", "fullback", "halfback"]
SUFFIX_HINT = {"passing_yards": ["quarterback"], "passing_td": ["quarterback"], "rushing_yards": ["running back", "halfback", "fullback"],
               "rushing_td": ["running back", "halfback", "fullback"], "receptions": ["wide receiver", "tight end"],
               "receiving_yards": ["wide receiver", "tight end"], "receiving_td": ["wide receiver", "tight end"],
               "sacks_half": ["defensive end", "linebacker", "defensive tackle"], "interceptions": ["cornerback", "safety", "linebacker"],
               "tackles": ["linebacker", "safety", "defensive end"]}


def title_candidates(name: str, cats=()):
    """article titles to try for a player: the plain name first, then 'Name (American football)' and position variants the
    category suggests (capped, so a missing player costs a handful of requests)"""
    base = re.sub(r"\s+", " ", name).strip()
    plain = "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c))
    suffixes = ["American football"] + [x for c in sorted(cats) for x in SUFFIX_HINT.get(c, [])]
    suffixes += [x for x in POS_SUFFIX if x not in suffixes][:3]
    bases = [base, plain]
    stripped = re.sub(r"\s+(?:Jr|Sr|II|III|IV)\.?$", "", plain).strip()
    if stripped != plain:
        bases.append(stripped)                                           # "Chris Godwin Jr." is the article "Chris Godwin"
    else:
        bases += [plain + " Sr.", plain + " Jr.", plain + " III"]       # "James Wilder" is the article "James Wilder Sr.", "Clay Matthews" is "Clay Matthews III"
    suffixed = (plain + " Sr.", plain + " Jr.", plain + " III")
    out = []
    for b in dict.fromkeys(bases):
        out.append(b)
        if b in suffixed:
            continue
        out += [f"{b} ({x})" for x in dict.fromkeys(suffixes)]
    return list(dict.fromkeys(out))


def years_overlap_ok(seen, guide) -> bool:
    if not seen:
        return False
    g, y = set(guide), set(seen)
    if not g:
        return True
    return len(g & y) >= max(1, int(0.6 * len(g))) and len(y - g) <= max(2, int(0.25 * len(g)))


# ------------------------------------------------------------------------------------------------ nflverse
NV_COLS = {
    "passing_yards": ("passing_yards",), "passing_td": ("passing_tds",), "rushing_yards": ("rushing_yards",), "rushing_td": ("rushing_tds",),
    "receptions": ("receptions",), "receiving_yards": ("receiving_yards",), "receiving_td": ("receiving_tds",), "sacks_half": ("def_sacks",),
    "interceptions": ("def_interceptions",), "tackles": ("def_tackles_solo", "def_tackle_assists"),
}
NV_POSITION = {"QB": "QB", "RB": "HB", "HB": "HB", "FB": "FB", "WR": "WR", "TE": "TE", "DE": "DE", "DT": "DT", "NT": "DT", "DL": "DE", "LB": "OLB",
               "OLB": "OLB", "ILB": "ILB", "MLB": "ILB", "CB": "CB", "DB": "CB", "S": "SS", "SS": "SS", "FS": "FS", "K": "K", "P": "P",
               "T": "T", "OT": "T", "G": "G", "OG": "G", "C": "C"}
NV_URL = "https://github.com/nflverse/nflverse-data/releases/download"


def _f(x):
    try:
        return float(x) if x not in ("", None) else 0.0
    except ValueError:
        return 0.0


NFLVERSE_NAME = {"Beanie Wells": "Chris Wells"}            # the guide prints the nickname, nflverse the legal first name (Cardinals running back 2009-12)


class NFLverse:
    """Regular-season weekly player stats 1999..2025 summed per club (franchise), per season and per game (sacks in half sacks)."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.career, self.season, self.game, self.names, self.pos = {}, {}, {}, {}, {}
        self.hashes = {}

    def load(self):
        for yr in range(NV_WINDOW[0], NV_WINDOW[1] + 1):
            p = self.folder / f"stats_player_week_{yr}.csv.gz"
            self.hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
            with gzip.open(p, "rt", encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    if r["season_type"] != "REG":
                        continue
                    club, pid = NV2CLUB.get(r["team"]), r["player_id"]
                    if not club or not pid:
                        continue
                    self.names[pid] = r["player_display_name"]
                    self.pos[pid] = r["position"]
                    for cat, cols in NV_COLS.items():
                        v = sum(_f(r[c]) for c in cols) * SCALE.get(cat, 1)
                        if v:
                            c1 = self.career.setdefault((club, pid), {})
                            c1[cat] = c1.get(cat, 0.0) + v
                            c2 = self.season.setdefault((club, pid, yr), {})
                            c2[cat] = c2.get(cat, 0.0) + v
                            self.game.setdefault((club, cat), []).append((v, pid, yr, int(r["week"] or 0)))
        return self

    def save(self, path) -> None:
        """dev cache of the aggregates (JSON) so a rerun does not re-read 27 weekly files"""
        obj = {"career": {f"{c}|{p}": v for (c, p), v in self.career.items()},
               "season": {f"{c}|{p}|{y}": v for (c, p, y), v in self.season.items()},
               "game": {f"{c}|{cat}": v for (c, cat), v in self.game.items()},
               "names": self.names, "pos": self.pos, "hashes": self.hashes}
        Path(path).write_text(json.dumps(obj), encoding="utf-8")

    @classmethod
    def from_cache(cls, folder, path):
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
        nv = cls(folder)
        nv.career = {tuple(k.split("|", 1)): v for k, v in obj["career"].items()}
        nv.season = {(k.split("|")[0], k.split("|")[1], int(k.split("|")[2])): v for k, v in obj["season"].items()}
        nv.game = {tuple(k.split("|", 1)): [tuple(x) for x in v] for k, v in obj["game"].items()}
        nv.names, nv.pos, nv.hashes = obj["names"], obj["pos"], obj["hashes"]
        return nv

    def find(self, club, name, years):
        """player id of a guide row (same club, same name, seasons overlapping the guide's years), or None"""
        want = norm(NFLVERSE_NAME.get(name, name)).split()
        if not want:
            return None
        if not hasattr(self, "_index"):
            self._index, self._years, self._norm = {}, {}, {}
            for (c, pid) in self.career:
                self._index.setdefault(c, []).append(pid)
            for (c, pid, yr) in self.season:
                self._years.setdefault((c, pid), set()).add(yr)
            self._norm = {pid: norm(n).split() for pid, n in self.names.items()}
        best = None
        for pid in self._index.get(club, []):
            have = self._norm.get(pid, [])
            if have == want:
                sc = 3
            elif len(want) == 1 and have and have[-1] == want[0]:                       # a guide that prints only the last name
                sc = 1
            elif have and len(want) > 1 and have[-1] == want[-1] and have[0][:1] == want[0][:1] and (have[0].startswith(want[0][:3]) or want[0].startswith(have[0][:3])):
                sc = 2
            else:
                continue
            ys = self._years.get((club, pid), set())
            ov = len(ys & set(years)) if years else 1
            if ov and (best is None or (sc, ov) > best[0]):
                best = ((sc, ov), pid)
        return best[1] if best else None

    def club_players(self, club):
        """[(player id, career totals)] of one club"""
        if not hasattr(self, "_by_club"):
            self._by_club, self._seasons_by_club = {}, {}
            for (c, pid), tot in self.career.items():
                self._by_club.setdefault(c, []).append((pid, tot))
            for (c, pid, yr), v in self.season.items():
                self._seasons_by_club.setdefault(c, []).append((pid, yr, v))
        return self._by_club.get(club, [])

    def club_seasons(self, club):
        """[(player id, season, season totals)] of one club"""
        self.club_players(club)
        return self._seasons_by_club.get(club, [])

    def same_person(self, pid, printed_names):
        """does an nflverse player match any name printed on the guide's list (same last name and first initial)?"""
        have = getattr(self, "_norm", {}).get(pid) or norm(self.names.get(pid, "")).split()
        for nm in printed_names:
            w = nm.split()
            if have and w and have[-1] == w[-1] and have[0][:1] == w[0][:1]:
                return True
        return False


# ------------------------------------------------------------------------------------------------ the decision
def tolerance(cat: str, v: float) -> float:
    """how far play-by-play derived nflverse totals may sit from the official number before they count as contradicting it.
    Measured on the rows where the guide equals Wikipedia exactly (section 4 of the report): counts are exact or 1 to 3 off, yards up to
    0.8 percent (career) and 1.2 percent (a season: Drew Brees 2011, nflverse 5,535, official 5,476), sacks up to 4 sacks."""
    if cat in ("passing_yards", "rushing_yards", "receiving_yards"):
        return max(30.0, 0.015 * v)
    if cat == "sacks_half":
        return max(8.0, 0.04 * v)
    return max(3.0, 0.015 * v)


def nv_status(cat: str, v1: float, nv_value, covered: bool) -> str:
    """exact | close | off | partial-ok | conflict | none (tackles are not comparable between sources)"""
    if cat == "tackles" or nv_value is None:
        return "none"
    if covered:
        d = abs(nv_value - v1)
        return "exact" if d < 1e-9 else ("close" if d <= tolerance(cat, v1) else "off")
    return "conflict" if nv_value > v1 + tolerance(cat, v1) else "partial-ok"


def decide(cat: str, v1: float, wiki_value, nv_value, nv_covered: bool) -> dict:
    """-> {'decision', 'confirmed_by', 'against', 'wikipedia', 'nflverse'} ; the whole two-source rule in one place"""
    w = "none" if wiki_value is None else ("agree" if abs(wiki_value - v1) < 1e-9 else "differ")
    n = nv_status(cat, v1, nv_value, nv_covered)
    confirmed = (["wikipedia"] if w == "agree" else []) + (["nflverse"] if n == "exact" else [])
    against = (["wikipedia"] if w == "differ" else []) + (["nflverse"] if n in ("off", "conflict") else [])
    if w == "differ":
        decision = "conflict"
    elif against:
        decision = "review"
    elif confirmed:
        decision = "ship"
    else:
        decision = "single"
    return {"decision": decision, "confirmed_by": confirmed, "against": against, "wikipedia": w, "nflverse": n}


def guard_violated(cat: str, guard) -> bool:
    """completeness guard of a group: an nflverse total above the bar means the guide's list misses someone or is stale"""
    if not guard or cat == "tackles" or guard.get("other_value") is None:
        return False
    return guard["other_value"] > guard["bar"] + tolerance(cat, guard["bar"])


def rank_rows(lst: dict):
    """[(rank, row)] ; a list ranked by this stat keeps its printed order, a column of another list is re-ranked by value"""
    rows = lst["rows"]
    if lst["kind"] == "column":
        out, prev, rk = [], None, 0
        for i, r in enumerate(sorted(rows, key=lambda r: -r["value"]), 1):
            if prev is None or r["value"] != prev:
                rk = i
            prev = r["value"]
            out.append((rk, r))
        return out
    out, last = [], 0
    for i, r in enumerate(rows, 1):
        rk = r.get("rank") or last or i
        out.append((rk, r))
        last = rk
    return out


# ------------------------------------------------------------------------------------------------ evidence -> data (pure)
def person_fields(c: dict) -> dict:
    first, last, suffix = split_name(c["name"])
    out = {"first": first, "last": last}
    if suffix:
        out["suffix"] = suffix
    out["position"] = c.get("position")
    return out


def evaluate_group(cat: str, rows: list, slots: int, guard) -> tuple:
    """-> (taken [(candidate, decision)], excluded rows, decision counts) for one list of the guide"""
    rows = sorted(rows, key=lambda c: (c["rank"], c["order"]))
    incomplete = guard_violated(cat, guard)
    taken, excluded, counts, stopped = [], [], {}, None
    for c in rows:
        d = decide(cat, c["value"], (c.get("wikipedia") or {}).get("value"), (c.get("nflverse") or {}).get("value"),
                   bool((c.get("nflverse") or {}).get("covered")))
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
        reason = None
        if incomplete:
            reason = "incomplete list"
        elif stopped is None and d["decision"] == "ship" and taken and c["value"] > taken[-1][0]["value"] + 1e-9:
            stopped = reason = "out of order"                   # a printed list that rises is misprinted or misread somewhere: stop there
        elif stopped is None and d["decision"] == "ship" and len(taken) < slots:
            taken.append((c, d))
            continue
        elif stopped is None and d["decision"] != "ship":
            stopped = d["decision"]
            reason = d["decision"]
        elif d["decision"] == "ship" and stopped:
            reason = f"after a rank that is {stopped}"
        elif d["decision"] == "ship":
            continue                                    # a further row that is simply beyond the slots
        else:
            reason = d["decision"]
        excluded.append({"club": c["club"], "scope": c["scope"], "category": cat, "rank": c["rank"], "name": c["name"], "years": c["years"],
                         "reason": reason, "guide": c["value"], "wikipedia": (c.get("wikipedia") or {}).get("value"),
                         "nflverse": (c.get("nflverse") or {}).get("value"), "detail": d["wikipedia"] + "/" + d["nflverse"]})
    return taken, excluded, counts


def assemble(evidence: dict):
    """The shipped data and the excluded list, derived only from the evidence file (so ``verify`` can re-derive them offline).
    A guide can print several lists for one stat (all-time and since 1982, top 10 table and record box): each is judged on its own
    and the one with the longest verified run ships."""
    groups: dict = {}
    for c in evidence["candidates"]:
        groups.setdefault((c["club"], c["scope"], c["category"]), {}).setdefault(c.get("variant", 0), []).append(c)
    guards = {(g["club"], g["scope"], g["category"], g.get("variant", 0)): g for g in evidence.get("guards", [])}
    clubs = {code: {"name": name, "arena_index": ARENA_ORDER.index(code), "career": {}, "season": {}, "game": {}, "notes": {}}
             for code, (name, _) in CLUBS.items()}
    excluded = []
    counts = {"shipped": {s: 0 for s in SCOPES}, "excluded": {}, "by_decision": {}}
    for (club, scope, cat), variants in sorted(groups.items(), key=lambda kv: (kv[0][0], SCOPES.index(kv[0][1]), list(CATEGORIES).index(kv[0][2]))):
        best = None
        for v, rows in sorted(variants.items()):
            taken, exc, cnt = evaluate_group(cat, rows, SLOTS[scope], guards.get((club, scope, cat, v)))
            pref = (len(taken), rows[0]["kind"] == "list", rows[0].get("complete_to") or len(rows), -v)
            if best is None or pref > best[0]:
                best = (pref, v, taken, exc, cnt)
        _, v, taken, exc, cnt = best
        for k, n in cnt.items():
            counts["by_decision"][k] = counts["by_decision"].get(k, 0) + n
        excluded.extend(exc)
        if taken:
            out = []
            for c, d in taken:
                row = {"rank": c["rank"], "name": c["name"], **person_fields(c)}
                if scope == "career":
                    row["years"] = c["years"]
                    row["span"] = c["span"]
                else:
                    row["season"] = c["season"]
                    if scope == "game":
                        row["date"] = c.get("date")
                        row["week"] = c.get("week")
                row["value"] = c["value"]
                row["confirmed_by"] = d["confirmed_by"]
                row["guide_page"] = c["guide"]["page"]                  # PDF page of the club guide that prints the row
                if scope == "career" and c.get("link") is not None:
                    row["link"] = c["link"]
                if c["kind"] == "column":
                    row["basis"] = "column"
                if c.get("tie"):
                    row["tie"] = True
                if c.get("adjusted"):
                    row["adjusted"] = c["adjusted"]
                out.append(row)
            clubs[club][scope][cat] = out
            counts["shipped"][scope] += len(out)
            if cat in ("sacks_half", "tackles") and taken[0][0].get("list_note"):
                clubs[club]["notes"][f"{scope}.{cat}"] = taken[0][0]["list_note"]
    for e in excluded:
        counts["excluded"][e["reason"]] = counts["excluded"].get(e["reason"], 0) + 1
    for m in evidence.get("missing", []):
        excluded.append({"club": m["club"], "scope": m["scope"], "category": m["category"], "rank": None, "name": None, "years": None,
                         "reason": "not printed in the guide", "guide": None, "wikipedia": None, "nflverse": None, "detail": m.get("why", "")})
        counts["excluded"]["not printed in the guide"] = counts["excluded"].get("not printed in the guide", 0) + 1
    data = {
        "schema": SCHEMA, "base_year": 2026, "through_season": evidence["through_season"],
        "categories": CATEGORIES, "positions": list(POSITIONS),
        "rules": evidence["rules"], "sources": evidence["public_sources"], "credits": CREDITS,
        "counts": counts, "clubs": clubs,
    }
    return data, excluded


# ------------------------------------------------------------------------------------------------ build
RULES = {
    "career": "Regular-season totals with the club since the franchise began, through the 2025 season. Sacks are in half sacks (124.5 sacks = 249) and follow what each club's own list says (official sacks only where the list says since 1982 or later). Tackles follow the club's own list; nflverse tackle counts are not comparable and are never used.",
    "season": "The club's best regular season in the category, through 2025. season is the NFL season.",
    "game": "The club's best regular-season game in the category, through 2025. season is the NFL season (January games belong to the season before); date is the game date when the guide prints it; week is the regular-season week when nflverse identifies the game.",
    "shipping": "A value ships only when the club's own 2026 media guide and a second, independent source agree: the player's Wikipedia season table summed over the club, or nflverse play-by-play totals where they cover the whole career. A disagreement, a single source, a failed earlier rank or a failed completeness check keeps the row out; every candidate with its sources is in the evidence file.",
    "ranks": "A club's list ships its longest run of verified ranks from rank 1. basis column: the guide prints the stat only as a column of a list ranked by another stat, so the order holds for the printed rows only (and for 1999-2025 careers nflverse confirms nobody is missing).",
    "links": "link is the roster identity (primary pool index, name, birth date) of a player who is on the club's 2026 roster, so his total keeps counting; null otherwise.",
    "footer_mapping": {
        "note": "the ids are the footer's (nfl2k5_franchise_extension, j23-footer) and the history seed's; the club index is clubs[CODE].arena_index",
        "leaders": "career.<category>[rank 1..3] -> leader_entry(person=pack_person(first, last, position), value, flags=LEADER_REAL, plus LEADER_LINKED and player=link.index when link is set); sacks_half is already in half sacks",
        "records": "season.<category>[0] and game.<category>[0] -> record_entry(person, club arena index, value, year=season, week_row=week - 1 when week is set, else none); a record with tie is shared and the named holder is one of them",
        "not_covered": "the records block's completions and forced_fumbles slots, and the league-wide leaders and records (the history seed has those)",
    },
}
CREDITS = {
    "club_guides": "Record lists: each club's own 2026 media guide (the Steelers' 2025 guide), read from the copies in the Internet Archive collection nfl-media-guides. Facts only (names, years, numbers).",
    "wikipedia": "Wikipedia player articles, text under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/); facts only (regular-season statistics read from the articles' career tables).",
    "nflverse": "nflverse (https://github.com/nflverse/nflverse-data), CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).",
}
PUBLIC_SOURCES = {
    "club_guides": "Each club's own 2026 media guide (Internet Archive collection nfl-media-guides); the Steelers' 2026 guide is not online, so their 2025 edition is used and the 2025 season is added from nflverse.",
    "wikipedia": "Wikipedia player articles, NFL career statistics tables (CC BY-SA 4.0), regular-season rows summed per club.",
    "nflverse": "nflverse weekly player stats 1999-2025 (CC-BY-4.0), regular season, summed per club.",
}


def load_guides(folder: Path, clubs=None) -> dict:
    out = {}
    for p in sorted(Path(folder).glob("*.json")):
        if p.name.startswith("_") or (clubs and p.stem not in clubs):
            continue
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def select_rows(lst: dict, scope: str):
    return [(rk, r) for rk, r in rank_rows(lst) if rk <= SLOTS[scope]]


def resolve_wikipedia(wiki: Wiki, need: dict, cache_file: Path) -> dict:
    """{'CLUB|Name': Wikipedia result or None}.  Every name is resolved afresh from the page cache (a cached article costs
    milliseconds), so a change in the table reader is never hidden by an old answer; only articles not yet cached touch the network."""
    resolved: dict = {}
    todo = [(club, name, info) for (club, name), info in sorted(need.items())]

    def one(item):
        club, name, info = item
        try:
            queue = list(title_candidates(name, info["cats"]))
            seen = set()
            while queue:
                cand = queue.pop(0)
                if cand in seen:
                    continue
                seen.add(cand)
                pg = wiki.page(cand)
                if pg.get("missing"):
                    if pg.get("disambiguation"):
                        queue += [t for t in pg.get("football_links", []) if t not in seen][:6]       # the football entries of a disambiguation page
                    continue
                r = club_sums(pg["tables"], club, guide_years=info["years"])
                if years_overlap_ok(r["years"], info["years"]):
                    return f"{club}|{name}", {"title": cand, "retrieved": pg["retrieved"], "sums": r["sums"], "seasons": r["seasons"],
                                              "years": r["years"], "ambiguous": r["ambiguous"], "position_text": infobox_position(pg["tables"])}
        except Exception as exc:                                  # one bad page or a network hiccup must not stop the build
            print(f"  wikipedia: {club} {name}: {exc!r} (left unresolved, rerun to retry)", flush=True)
            return f"{club}|{name}", "ERROR"
        return f"{club}|{name}", None

    with ThreadPoolExecutor(max_workers=4) as pool:
        for n, (key, found) in enumerate(pool.map(one, todo), 1):
            if found != "ERROR":
                resolved[key] = found
            if n % 20 == 0 or n == len(todo):
                cache_file.write_text(json.dumps(resolved), encoding="utf-8")
                print(f"  wikipedia: {n}/{len(todo)} names", flush=True)
    cache_file.write_text(json.dumps(resolved), encoding="utf-8")
    try:
        wiki.fill_revids(sorted({v["title"] for v in resolved.values() if v}))
    except RuntimeError as exc:                                   # the API is rate limited now and then; rerun to fill the rest
        print("  wikipedia: revision ids incomplete:", exc, flush=True)
    for v in resolved.values():
        if v:
            pg = json.loads(wiki.path(v["title"]).read_text(encoding="utf-8"))
            v["revid"], v["canonical_title"] = pg.get("revid"), pg.get("canonical_title", v["title"])
    return resolved


def check_guide(d: dict):
    """Validate one transcribed club guide file -> (errors, warnings).  Every (scope, category) pair must be a list, a column or a
    justified 'missing'; each row needs a number whose digits appear in its printed line; a ranked list must not rise."""
    errs, warns = [], []
    for k in ("team", "guide_ident", "through_season", "lists", "missing", "notes"):
        if k not in d:
            errs.append(f"missing top-level key {k}")
    if errs:
        return errs, warns
    if d["team"] not in CLUBS:
        errs.append(f"unknown club {d['team']}")
    seen = {}
    for li, lst in enumerate(d["lists"]):
        tag = f"list[{li}] {lst.get('scope')}/{lst.get('category')}"
        if lst.get("scope") not in SCOPES:
            errs.append(f"{tag}: bad scope")
        if lst.get("category") not in GUIDE_CATEGORY:
            errs.append(f"{tag}: bad category")
        if lst.get("kind") not in ("list", "column"):
            errs.append(f"{tag}: kind must be list or column")
        if not isinstance(lst.get("pdf_page"), int) or lst["pdf_page"] < 1:
            errs.append(f"{tag}: bad pdf_page")
        for k in ("title", "ranked_by", "scope_note"):
            if not isinstance(lst.get(k), str) or not lst[k]:
                errs.append(f"{tag}: missing {k}")
        rows = lst.get("rows")
        if not isinstance(rows, list) or not rows:
            errs.append(f"{tag}: no rows")
            continue
        prev = None
        for ri, r in enumerate(rows):
            rt = f"{tag} row {ri + 1}"
            for k in ("name", "years", "raw"):
                if not isinstance(r.get(k), str) or not r[k]:
                    errs.append(f"{rt}: missing {k}")
            v = r.get("value")
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errs.append(f"{rt}: value must be a number")
                continue
            shown = str(int(v)) if float(v).is_integer() else f"{v:.1f}"
            if isinstance(r.get("raw"), str) and shown not in r["raw"].replace(",", "") and shown.replace(".0", "") not in r["raw"].replace(",", ""):
                errs.append(f"{rt}: value {v} is not in the printed line {r['raw']!r}")
            if lst.get("kind") == "list" and prev is not None and v > prev + 1e-9:
                warns.append(f"{rt}: value {v} above the previous row {prev}")
            prev = v
        seen.setdefault((lst.get("scope"), lst.get("category")), []).append(lst.get("kind"))
    missing = {(m.get("scope"), m.get("category")) for m in d["missing"]}
    for scope in SCOPES:
        for cat in GUIDE_CATEGORY:
            if (scope, cat) not in seen and (scope, cat) not in missing:
                errs.append(f"{scope}/{cat}: neither a list nor a 'missing' entry")
    return errs, warns


def cmd_import_guides(args) -> int:
    """validate the helper files of a folder and write them (one list per line) to the folder the build reads"""
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    bad = 0
    for p in sorted(Path(args.src).glob("*.json")):
        if p.name.startswith("_"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        errs, warns = check_guide(d)
        for e in errs:
            print(f"{p.name}: ERROR {e}")
        for w in warns[:5]:
            print(f"{p.name}: warning {w}")
        bad += bool(errs)
        if not errs:
            d["notes"] = [n.replace("\u2014", "-").replace("\u2013", "-") for n in d["notes"]]
            with open(dest / p.name, "w", encoding="utf-8", newline="\n") as f:
                f.write(dumps_by_line(d))
    return 1 if bad else 0


def short_note(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip().replace("\u2014", "-").replace("\u2013", "-")
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


def dumps_by_line(obj: dict) -> str:
    """compact JSON with every element of a top-level list of objects on its own line (diffable, still plain JSON)"""
    out = ["{"]
    keys = list(obj)
    for i, k in enumerate(keys):
        v, comma = obj[k], ("," if i < len(keys) - 1 else "")
        if isinstance(v, list) and v and isinstance(v[0], dict):
            out.append(json.dumps(k) + ": [")
            out += [json.dumps(x, ensure_ascii=False, separators=(",", ":")) + ("," if j < len(v) - 1 else "") for j, x in enumerate(v)]
            out.append("]" + comma)
        else:
            out.append(json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False, separators=(",", ":")) + comma)
    out.append("}")
    return "\n".join(out) + "\n"


def cmd_build(args) -> int:
    guides = load_guides(Path(args.guides), set(args.clubs.split(",")) if args.clubs else None)
    wiki = Wiki(args.wiki_cache)
    if args.nv_cache and Path(args.nv_cache).exists():
        nv = NFLverse.from_cache(args.nflverse, args.nv_cache)
    else:
        nv = NFLverse(args.nflverse).load()
        if args.nv_cache:
            nv.save(args.nv_cache)
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    cohort_full = {(norm(r[1]), norm(r[2]), r[3]): r[0] for r in cohort["records"]}
    cohort_by_index = {r[0]: r for r in cohort["records"]}
    cohort_lb: dict = {}
    for r in cohort["records"]:
        cohort_lb.setdefault((norm(r[2]), r[3]), []).append(r[0])
    roster = {}
    with open(Path(args.nflverse) / "roster_2026.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] in ("CUT", "RET", "EXE", "TRD"):
                continue
            roster.setdefault((NV2CLUB.get(r["team"]), norm(r["full_name"])), r)

    def link_of(club, name):
        r = roster.get((club, norm(name)))
        if not r:
            return None
        idx = cohort_full.get((norm(r["first_name"]), norm(r["last_name"]), r["birth_date"]))
        if idx is None:
            c = cohort_lb.get((norm(r["last_name"]), r["birth_date"]), [])
            idx = c[0] if len(c) == 1 else None
        if idx is None:
            return None
        rec = cohort_by_index[idx]
        return {"pool": "primary", "index": idx, "first": rec[1], "last": rec[2], "birth_date": rec[3], "gsis_id": r["gsis_id"]}

    need: dict = {}
    for club, g in guides.items():
        for lst in g["lists"]:
            for rk, r in select_rows(lst, lst["scope"]):
                info = need.setdefault((club, r["name"]), {"years": set(), "cats": set()})
                info["cats"].add(GUIDE_CATEGORY[lst["category"]])
                if lst["scope"] == "career":
                    info["years"].update(parse_years(r["years"]))
    resolved = resolve_wikipedia(wiki, need, Path(args.wiki_cache) / "resolved.json")

    cands, missing, guards = [], [], []
    for club, g in sorted(guides.items()):
        through = int(g["through_season"])
        for m in g.get("missing", []):
            missing.append({"club": club, "scope": m["scope"], "category": GUIDE_CATEGORY[m["category"]], "why": m.get("why", "")})
        seen_variant: dict = {}
        for lst in g["lists"]:
            scope, cat = lst["scope"], GUIDE_CATEGORY[lst["category"]]
            k = SCALE.get(cat, 1)
            variant = seen_variant[(scope, cat)] = seen_variant.get((scope, cat), -1) + 1
            chosen = select_rows(lst, scope)
            for order, (rk, r) in enumerate(chosen):
                v1 = clean_number(r["value"] * k)
                if scope == "career":
                    ys = parse_years(r["years"], through)
                    season, date = None, None
                else:
                    date, season = game_date(r["years"])
                    ys = {season} if season else set()
                res = resolved.get(f"{club}|{r['name']}")
                pid = nv.find(club, r["name"], ys) if cat != "tackles" else None
                c = {"club": club, "scope": scope, "category": cat, "variant": variant, "rank": rk, "order": order, "name": r["name"], "years": r["years"],
                     "value": v1, "kind": lst["kind"], "complete_to": lst.get("complete_to") or len(lst["rows"]),
                     "guide": {"page": lst["pdf_page"], "title": lst["title"], "raw": r["raw"]}}
                if cat in ("sacks_half", "tackles"):
                    c["list_note"] = short_note(lst["scope_note"])        # official or unofficial counting matters for these two
                if r.get("tie"):
                    c["tie"] = True
                if r.get("uncertain"):
                    c["uncertain"] = True
                if scope == "career":
                    c["span"] = [min(ys), max(ys)] if ys else []
                else:
                    c["season"] = season
                    if scope == "game":
                        c["date"] = date
                # ---- positions
                pos = POSITION_OVERRIDE.get(r["name"])
                src = "override" if pos else None
                if not pos and res and res.get("position_text"):
                    pos, src = position_code(res["position_text"]), "wikipedia infobox"
                if not pos and pid is not None:
                    pos, src = NV_POSITION.get(nv.pos.get(pid, "")), "nflverse"
                if not pos:
                    pos, src = DEFAULT_POSITION[cat], "category default"
                c["position"], c["position_source"] = pos, src
                # ---- Steelers 2025 guide etc.: add the seasons after the guide's last one from nflverse
                if scope == "career" and through < THROUGH and ys and max(ys) >= through and pid is not None and cat != "tackles":
                    extra = sum(nv.season.get((club, pid, y), {}).get(cat, 0.0) for y in range(through + 1, THROUGH + 1))
                    if extra:
                        c["adjusted"] = {"guide_value": v1, "added": clean_number(extra), "seasons": list(range(through + 1, THROUGH + 1)), "from": "nflverse"}
                        c["value"] = v1 = clean_number(v1 + extra)
                # ---- source 2
                if res:
                    if scope == "career":
                        wv = res["sums"].get(cat)
                    elif scope == "season":
                        wv = res["seasons"].get(cat, {}).get(str(season)) if season else None
                    else:
                        wv = None
                    c["wikipedia"] = {"title": res.get("canonical_title") or res["title"], "revid": res.get("revid"), "retrieved": res["retrieved"],
                                      "value": None if wv is None else clean_number(wv), "years": [res["years"][0], res["years"][-1]] if res["years"] else []}
                # ---- source 3
                if pid is not None:
                    if scope == "career":
                        have = nv.career.get((club, pid), {}).get(cat, 0.0)
                        covered = bool(ys) and all(NV_WINDOW[0] <= y <= NV_WINDOW[1] for y in ys)
                        c["nflverse"] = {"value": clean_number(have), "covered": covered, "player": nv.names[pid]}
                    elif season and NV_WINDOW[0] <= season <= NV_WINDOW[1]:
                        if scope == "season":
                            have = nv.season.get((club, pid, season), {}).get(cat, 0.0)
                        else:
                            games = [x for x in nv.game.get((club, cat), []) if x[1] == pid and x[2] == season]
                            have = max((x[0] for x in games), default=0.0)
                            top = [x for x in games if x[0] == have]
                            if len(top) == 1 and have:
                                c["week"] = top[0][3]
                        c["nflverse"] = {"value": clean_number(have), "covered": True, "player": nv.names[pid]}
                toks = norm(r["name"]).split()
                if pid is not None and toks and (len(toks) < 2 or len(toks[0]) <= 1):
                    # the guide printed an initial or only a last name: use the full name nflverse knows (the value check below decides)
                    c["printed_name"], c["name"] = r["name"], nv.names[pid]
                if scope == "career":
                    c["link"] = link_of(club, c["name"])
                cands.append(c)
            # ---- completeness guard
            if cat == "tackles" or not chosen:
                continue
            printed = {norm(r["name"]) for r in lst["rows"]}
            if scope == "career":
                if lst["kind"] == "column":
                    ranked = [r for _, r in rank_rows(lst)]
                    bar = ranked[min(2, len(ranked) - 1)]["value"] * k
                else:
                    bar = min(r["value"] for r in lst["rows"]) * k
                best = None
                for pid_, tot in nv.club_players(club):
                    if tot.get(cat) and (best is None or tot[cat] > best[0]) and not nv.same_person(pid_, printed):
                        best = (tot[cat], nv.names[pid_])
                guards.append({"club": club, "scope": scope, "category": cat, "variant": variant, "bar": clean_number(bar),
                               "other_value": clean_number(best[0]) if best else None, "other_player": best[1] if best else None})
            else:
                bar = chosen[0][1]["value"] * k
                if scope == "season":
                    best = max(((v.get(cat, 0.0), pid_, y) for pid_, y, v in nv.club_seasons(club)), default=None)
                else:
                    best = max(((x[0], x[1], x[2]) for x in nv.game.get((club, cat), [])), default=None)
                guards.append({"club": club, "scope": scope, "category": cat, "variant": variant, "bar": clean_number(bar),
                               "other_value": clean_number(best[0]) if best else None, "other_player": nv.names[best[1]] if best else None,
                               "other_season": best[2] if best else None})
    ia = json.loads(Path(args.ia_manifest).read_text(encoding="utf-8")) if args.ia_manifest else {}
    fetched = Path(args.nflverse) / "FETCHED_AT.txt"
    guide_sources = {}
    for club, g in sorted(guides.items()):
        m = ia.get(g["guide_ident"], {})
        guide_sources[club] = {"item": g["guide_ident"], "url": f"https://archive.org/details/{g['guide_ident']}", "title": m.get("title"),
                               "date": m.get("date"), "retrieved": m.get("retrieved"), "text_sha256": m.get("sha256"), "pdf_sha256": m.get("pdf_sha256"),
                               "through_season": g["through_season"], "file_sha256": hashlib.sha256((Path(args.guides) / f"{club}.json").read_bytes()).hexdigest()}
    evidence = {
        "schema": EVIDENCE_SCHEMA, "through_season": THROUGH, "retrieved": time.strftime("%Y-%m-%d", time.gmtime()),
        "rules": RULES, "public_sources": PUBLIC_SOURCES,
        "sources": {"nflverse_files": nv.hashes, "nflverse_url": NV_URL + "/stats_player/stats_player_week_<season>.csv.gz",
                    "nflverse_retrieved": fetched.read_text().strip() if fetched.exists() else None, "guides": guide_sources},
        "guides_folder": "data/nfl2k5_franchise_leaders_guides", "missing": missing, "guards": guards, "candidates": cands,
    }
    data, excluded = assemble(evidence)
    evidence["excluded"] = excluded
    with open(args.evidence, "w", encoding="utf-8", newline="\n") as f:                 # LF on every platform (the repo guards generated files)
        f.write(dumps_by_line(evidence))
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(data["counts"]))
    return 0


def cmd_verify(args) -> int:
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    data, excluded = assemble(evidence)
    shipped = json.loads(Path(args.out).read_text(encoding="utf-8"))
    problems = []
    if data != shipped:
        problems.append("shipped data differs from the data derived from the evidence")
    if excluded != evidence.get("excluded"):
        problems.append("the excluded list differs from the one derived from the evidence")
    for p in problems:
        print("PROBLEM:", p)
    print("ok" if not problems else "FAILED", json.dumps(data["counts"]["shipped"]))
    return 1 if problems else 0


def cmd_summary(args) -> int:
    data = json.loads(Path(args.out).read_text(encoding="utf-8"))
    print("club  career(3 x 10)  season(10)  game(10)")
    for code in ARENA_ORDER:
        c = data["clubs"][code]
        print(f"{code:<5} {sum(len(v) for v in c['career'].values()):>8}      {len(c['season']):>6}     {len(c['game']):>6}")
    print(json.dumps(data["counts"]))
    return 0


def cmd_fetch_nflverse(args) -> int:
    dest = Path(args.cache)
    dest.mkdir(parents=True, exist_ok=True)
    names = [f"stats_player/stats_player_week_{y}.csv.gz" for y in range(NV_WINDOW[0], NV_WINDOW[1] + 1)]
    names += ["rosters/roster_2026.csv"]
    for n in names:
        target = dest / Path(n).name
        if target.exists() and target.stat().st_size:
            continue
        with urllib.request.urlopen(urllib.request.Request(f"{NV_URL}/{n}", headers={"User-Agent": UA}), timeout=180) as r:     # nosec B310 - fixed https host
            target.write_bytes(r.read())
        print("fetched", target.name)
    with open(dest / "FETCHED_AT.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()) + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch-nflverse")
    f.add_argument("--cache", required=True)
    f.set_defaults(fn=cmd_fetch_nflverse)
    b = sub.add_parser("build")
    b.add_argument("--guides", required=True, help="folder with one transcribed <CLUB>.json per club")
    b.add_argument("--nflverse", required=True)
    b.add_argument("--wiki-cache", required=True)
    b.add_argument("--clubs", default="", help="comma separated club codes (default: every guide file)")
    b.add_argument("--ia-manifest", default="", help="the Internet Archive manifest written by the guide fetch (item titles, dates, digests)")
    b.add_argument("--nv-cache", default="", help="optional JSON cache of the nflverse aggregates (dev convenience)")
    b.add_argument("--out", default=str(DATA))
    b.add_argument("--evidence", default=str(EVIDENCE))
    b.set_defaults(fn=cmd_build)
    g = sub.add_parser("import-guides")
    g.add_argument("--src", required=True, help="folder with the transcribed <CLUB>.json files")
    g.add_argument("--dest", default=str(DATA.parent / "nfl2k5_franchise_leaders_guides"))
    g.set_defaults(fn=cmd_import_guides)
    v = sub.add_parser("verify")
    v.add_argument("--out", default=str(DATA))
    v.add_argument("--evidence", default=str(EVIDENCE))
    v.set_defaults(fn=cmd_verify)
    s = sub.add_parser("summary")
    s.add_argument("--out", default=str(DATA))
    s.set_defaults(fn=cmd_summary)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
