#!/usr/bin/env python3
"""Build ``data/nfl2k5_franchise_leaders_2026.json`` (job b780 j5b-leaders): each club's all-time career leaders and
single-season / single-game record holders, shipped only where two sources agree.

What is built
  * career: the club's top 3 in ten categories (passing yards and touchdowns, rushing yards and touchdowns, receptions,
    receiving yards and touchdowns, sacks, interceptions, tackles), regular season, through the 2025 season;
  * season and game: the club's record holder in the same ten categories.
Nothing here is invented or recalled from memory; every number is read from a source and checked against another.

Sources (all read-only, retrieval dates and pins in the evidence file)
  S1  the club's own 2026 media guide (Internet Archive, collection nfl-media-guides; image-only PDFs read through the Archive's OCR,
      Tesseract at 300 dpi and the page pictures).  The Steelers' 2026 guide is not online, so the 2025 edition is used (through 2024).
  S2  Wikipedia: the player's NFL career statistics table (regular season rows), summed over the club's rows (CC BY-SA 4.0).
  S3  nflverse weekly player stats 1999-2025 (CC-BY-4.0), regular season, summed per club.  Play-by-play derived, so yards and
      sacks can differ from the official numbers by a few units (Matt Forte, Bears: 8,595 against the official 8,602) and
      tackles are not comparable at all; S3 therefore counts as a second source only on an exact match and otherwise only guards
      against gross conflicts (tolerances below).
Not used on purpose: Pro-Football-Reference and FootballDB (bot-blocked, HTTP 403) and StatMuse (its terms forbid automated and
manual data mining).

The two-source rule (``decide``)
  ship      S1 equals S2, or S1 equals S3 exactly where S3 sees the whole career with the club (1999-2025 only), and nothing
            contradicts it (S2 differing, S3 beyond tolerance, or an S3 total above the guide's);
  review    S1 equals S2 but S3 is beyond tolerance (not shipped, listed);
  conflict  S1 and S2 differ (not shipped, listed);
  single    only S1 exists (not shipped, listed).
A (club, scope, category) ships the longest run of consecutive ranks from rank 1 whose rows all ship (a later rank cannot be
trusted when an earlier one failed).  Touchdown categories that the guide only prints as a column of a yards-ranked list are
marked ``basis: column``: the order is exact only for the printed rows.

Usage
  python3 tools/b780_franchise_leaders_build.py fetch-nflverse --cache DIR
  python3 tools/b780_franchise_leaders_build.py build --guides DIR --nflverse DIR --wiki-cache DIR
  python3 tools/b780_franchise_leaders_build.py verify          # offline: evidence -> decisions -> data, must equal the shipped files
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
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

CATEGORIES = {
    "pass_yds": "Passing yards", "pass_td": "Passing touchdowns", "rush_yds": "Rushing yards", "rush_td": "Rushing touchdowns",
    "rec": "Receptions", "rec_yds": "Receiving yards", "rec_td": "Receiving touchdowns", "sacks": "Sacks",
    "int": "Interceptions", "tackles": "Tackles",
}
SCOPES = ("career", "season", "game")
SLOTS = {"career": 3, "season": 1, "game": 1}

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
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’`]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t not in ("jr", "sr", "ii", "iii", "iv", "v"))


def parse_years(s: str, through: int = THROUGH) -> set[int]:
    """'1975-87' -> 1975..1987; '1940-41; 45-50'; "2008-16; '25"; '2017, 20-present'; '2019'."""
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
        if not b:
            out.add(a)
        elif b.lower().startswith("pres"):
            out.update(range(a, through + 1))
        elif b.isdigit():
            e = int(b) if len(b) == 4 else century + int(b)
            out.update(range(a, (e + 100 if e < a else e) + 1))
        else:
            out.add(a)
    return out


def year_of(s: str):
    m = re.search(r"((?:19|20)\d{2})", s or "")
    if m:
        return int(m.group(1))
    m = re.search(r"\b\d{1,2}/\d{1,2}/(\d{2})\b", s or "")
    if m:
        y = int(m.group(1))
        return 1900 + y if y > 30 else 2000 + y
    return None


# ------------------------------------------------------------------------------------------------ Wikipedia tables (stdlib)
# stat-table team cell -> [(club, first_year, last_year)]; a None club = known ambiguous
def _a(c, a=1900, b=3000):
    return (c, a, b)


ABBR = {
    "ARI": [_a("ARI")], "ARZ": [_a("ARI")], "PHX": [_a("ARI")], "PHO": [_a("ARI")], "CRD": [_a("ARI")], "CHC": [_a("ARI")],
    "STL": [_a("ARI", 1960, 1987), _a("LAR", 1995, 2015)], "ATL": [_a("ATL")],
    "BAL": [_a("IND", 1953, 1983), _a("BAL", 1996)], "BLC": [_a("IND")], "BLT": [_a("BAL")], "RAV": [_a("BAL")],
    "BUF": [_a("BUF")], "CAR": [_a("CAR")], "CHI": [_a("CHI")], "CIN": [_a("CIN")], "CLE": [_a("CLE")], "CLV": [_a("CLE")],
    "DAL": [_a("DAL")], "DEN": [_a("DEN")], "DET": [_a("DET")], "GB": [_a("GB")], "GNB": [_a("GB")],
    "HOU": [_a("TEN", 1960, 1996), _a("HOU", 2002)], "HST": [_a("HOU")], "IND": [_a("IND", 1984)], "TEN": [_a("TEN", 1997)],
    "OTI": [_a("TEN", 1997)], "HOI": [_a("TEN")], "JAX": [_a("JAX")], "JAC": [_a("JAX")],
    "KC": [_a("KC")], "KAN": [_a("KC")], "DLT": [_a("KC")],
    "LV": [_a("LV")], "OAK": [_a("LV")], "RAI": [_a("LV")], "LVR": [_a("LV")],
    "LAC": [_a("LAC")], "SD": [_a("LAC")], "SDG": [_a("LAC")], "LAR": [_a("LAR")], "RAM": [_a("LAR")],
    "LA": [_a("LAR", 1946, 1981), (None, 1982, 1994), _a("LAR", 2016)],
    "MIA": [_a("MIA")], "MIN": [_a("MIN")], "NE": [_a("NE")], "NWE": [_a("NE")], "BOS": [_a("NE")], "NO": [_a("NO")], "NOR": [_a("NO")],
    "NYG": [_a("NYG")], "NYJ": [_a("NYJ")], "NYT": [_a("NYJ")], "PHI": [_a("PHI")], "PIT": [_a("PIT")],
    "SF": [_a("SF")], "SFO": [_a("SF")], "SEA": [_a("SEA")], "TB": [_a("TB")], "TAM": [_a("TB")],
    "WAS": [_a("WAS")], "WSH": [_a("WAS")],
}
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
            self._cell = {"text": [], "cs": int(a.get("colspan", 1) or 1), "rs": int(a.get("rowspan", 1) or 1)}
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


def html_tables(html: str):
    p = _Tables()
    p.feed(html)
    return p.tables


def num(s):
    s = (s or "").replace(",", "").replace("−", "-").replace("–", "-").strip()
    s = re.sub(r"[^\d.\-]", "", s)
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def column_map(heads):
    """canonical stat -> column index for a flattened Wikipedia NFL stat-table header ('Group Column')."""
    m = {}
    for i, h in enumerate(heads):
        c = re.sub(r"\s+", " ", h.lower()).strip()
        if c in ("year", "season", "year year"):
            m.setdefault("year", i)
        elif c == "team" or c.endswith(" team"):
            m.setdefault("team", i)
        elif "passing" in c and c.endswith(" yds"):
            m.setdefault("pass_yds", i)
        elif "passing" in c and c.endswith(" td"):
            m.setdefault("pass_td", i)
        elif "rushing" in c and (c.endswith(" yds") or c.endswith(" yards")):
            m.setdefault("rush_yds", i)
        elif "rushing" in c and c.endswith(" td"):
            m.setdefault("rush_td", i)
        elif "receiving" in c and c.endswith(" rec"):
            m.setdefault("rec", i)
        elif "receiving" in c and (c.endswith(" yds") or c.endswith(" yards")):
            m.setdefault("rec_yds", i)
        elif "receiving" in c and c.endswith(" td"):
            m.setdefault("rec_td", i)
        elif "sacked" not in c and ("sck" in c.split() or "sacks" in c.split() or c.endswith(" sack") or c in ("sacks", "sck")):
            m.setdefault("sacks", i)
        elif "tackles" in c and (c.endswith(" cmb") or c.endswith(" comb") or c.endswith(" total") or c.endswith(" tot")):
            m.setdefault("tackles", i)
        elif c in ("tackles", "tkl", "tot tackles", "total tackles", "tackles tkl", "combined tackles"):
            m.setdefault("tackles", i)
        elif "interceptions" in c and c.endswith(" int"):
            m.setdefault("int", i)
        elif c in ("int", "ints", "interceptions"):
            m.setdefault("int", i)
    return m


def player_tables(html: str):
    """NFL career stat tables of a player article: {'heads', 'cmap', 'rows', 'heading', 'post'} (offense columns are only
    mapped for offense tables and defense columns only for defense tables, so a quarterback's 'Sacks' are not defensive sacks)."""
    out = []
    for t in html_tables(html):
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
        cm = column_map(heads)
        if "team" not in cm or "year" not in cm:
            continue
        low = " ".join(h.lower() for h in heads)
        offense = any(w in low for w in ("passing", "rushing", "receiving"))
        defensive = ("tackles" in low or "interceptions" in low or "defense" in low or "defensive" in low
                     or (not offense and re.search(r"\bint\b", low) is not None))
        if not defensive:
            for k in ("sacks", "tackles", "int"):
                cm.pop(k, None)
        heading = (t["heading"] + " " + t["caption"]).lower()
        post = bool(re.search(r"post ?season|playoff|super bowl", heading)) or "opp" in low.split()
        rows = [r for r in g[len(hdr):] if r and re.match(r"^(19|20)\d{2}", r[0])]
        out.append({"heads": heads, "cmap": cm, "rows": rows, "heading": t["heading"], "post": post})
    return out


def club_sums(html: str, club: str, through: int = THROUGH):
    """Regular-season stat rows of a player article that belong to `club` -> sums, per-season values, seasons seen."""
    rows, years, amb = {}, set(), 0
    for t in player_tables(html):
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
            if who == "AMBIG":
                amb += 1
                continue
            if who != club:
                continue
            years.add(yr)
            for cat in CATEGORIES:
                if cat in cm and cm[cat] < len(r):
                    v = num(r[cm[cat]])
                    if v is not None:
                        rows.setdefault(cat, {}).setdefault(yr, v)      # a season repeated in a second table counts once
    return {"sums": {c: sum(by.values()) for c, by in rows.items()}, "seasons": {c: dict(by) for c, by in rows.items()},
            "years": sorted(years), "ambiguous": amb}


class Wiki:
    """Article HTML through index.php?action=render (edge cached, fast, polite gap); the API only for batched revision ids."""

    def __init__(self, cache_dir, min_gap: float = 0.7):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.gap = min_gap
        self._last = 0.0

    def _get(self, url: str):
        for attempt in range(8):
            wait = self.gap - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=90) as r:   # nosec B310 - fixed https host
                    return r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return 404, ""
                if e.code in (429, 503):
                    time.sleep(8 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(4 * (attempt + 1))
        raise RuntimeError("wikipedia fetch failed: " + url)

    def path(self, title: str) -> Path:
        return self.cache / (hashlib.sha1(title.encode()).hexdigest()[:16] + ".json")

    def page(self, title: str) -> dict:
        p = self.path(title)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        url = "https://en.wikipedia.org/w/index.php?" + urllib.parse.urlencode({"title": title.replace(" ", "_"), "action": "render"})
        status, html = self._get(url)
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if status == 404 or not html:
            out = {"title": title, "missing": True, "retrieved": today}
        elif 'id="disambigbox"' in html or "dmbox-disambig" in html:
            out = {"title": title, "missing": True, "disambiguation": True, "retrieved": today}
        else:
            out = {"title": title, "revid": None, "html": html, "retrieved": today}
        p.write_text(json.dumps(out), encoding="utf-8")
        return out

    def fill_revids(self, titles) -> None:
        """batched revision-id lookup (<=50 titles a call) for cached pages; adds revid, canonical title, timestamp to the cache"""
        todo = [t for t in titles if self.path(t).exists() and json.loads(self.path(t).read_text(encoding="utf-8")).get("revid") is None
                and not json.loads(self.path(t).read_text(encoding="utf-8")).get("missing")]
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


def title_candidates(name: str):
    base = re.sub(r"\s+", " ", name).strip()
    plain = "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c))
    out = []
    for b in dict.fromkeys([base, plain]):
        out.append(b)
        out += [f"{b} ({s})" for s in POS_SUFFIX]
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
    "pass_yds": ("passing_yards",), "pass_td": ("passing_tds",), "rush_yds": ("rushing_yards",), "rush_td": ("rushing_tds",),
    "rec": ("receptions",), "rec_yds": ("receiving_yards",), "rec_td": ("receiving_tds",), "sacks": ("def_sacks",),
    "int": ("def_interceptions",), "tackles": ("def_tackles_solo", "def_tackle_assists"),
}
NV_URL = "https://github.com/nflverse/nflverse-data/releases/download"


def _f(x):
    try:
        return float(x) if x not in ("", None) else 0.0
    except ValueError:
        return 0.0


class NFLverse:
    """Regular-season weekly player stats 1999..2025 summed per club (franchise), per season and per game."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.career, self.season, self.game, self.names = {}, {}, {}, {}
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
                    for cat, cols in NV_COLS.items():
                        v = sum(_f(r[c]) for c in cols)
                        if v:
                            c1 = self.career.setdefault((club, pid), {})
                            c1[cat] = c1.get(cat, 0.0) + v
                            c2 = self.season.setdefault((club, pid, yr), {})
                            c2[cat] = c2.get(cat, 0.0) + v
                            self.game.setdefault((club, cat), []).append((v, pid, yr, int(r["week"] or 0)))
        return self

    def find(self, club, name, years):
        """player id of a guide row (same club, same name, seasons overlapping the guide's years), or None"""
        want = norm(name).split()
        if not want:
            return None
        best = None
        for (c, pid) in self.career:
            if c != club:
                continue
            have = norm(self.names.get(pid, "")).split()
            if have == want:
                sc = 3
            elif have and have[-1] == want[-1] and have[0][:1] == want[0][:1] and (have[0].startswith(want[0][:3]) or want[0].startswith(have[0][:3])):
                sc = 2
            else:
                continue
            ys = {k[2] for k in self.season if k[0] == club and k[1] == pid}
            ov = len(ys & set(years)) if years else 1
            if ov and (best is None or (sc, ov) > best[0]):
                best = ((sc, ov), pid)
        return best[1] if best else None


# ------------------------------------------------------------------------------------------------ the decision
def tolerance(cat: str, v: float) -> float:
    """how far play-by-play derived nflverse totals may sit from the official number before they count as contradicting it"""
    if cat in ("pass_yds", "rush_yds", "rec_yds"):
        return max(25.0, 0.006 * v)
    if cat == "sacks":
        return max(2.5, 0.03 * v)
    return max(2.0, 0.01 * v)


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
def clean_number(v):
    return int(v) if float(v).is_integer() else round(float(v), 1)


def assemble(evidence: dict) -> dict:
    """The shipped data, derived only from the evidence file (so ``verify`` can re-derive it offline)."""
    cands = evidence["candidates"]
    groups: dict = {}
    for c in cands:
        groups.setdefault((c["club"], c["scope"], c["category"]), []).append(c)
    clubs = {code: {"name": name, "career": {}, "season": {}, "game": {}} for code, (name, _) in CLUBS.items()}
    excluded = []
    counts = {"shipped": {s: 0 for s in SCOPES}, "excluded": {}, "by_decision": {}}
    for (club, scope, cat), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], SCOPES.index(kv[0][1]), list(CATEGORIES).index(kv[0][2]))):
        rows = sorted(rows, key=lambda c: (c["rank"], c["order"]))
        slots = SLOTS[scope]
        taken, stopped = [], None
        for c in rows:
            d = decide(cat, c["value"], (c.get("wikipedia") or {}).get("value"), (c.get("nflverse") or {}).get("value"),
                       bool((c.get("nflverse") or {}).get("covered")))
            counts["by_decision"][d["decision"]] = counts["by_decision"].get(d["decision"], 0) + 1
            if stopped is None and d["decision"] == "ship" and len(taken) < slots:
                taken.append((c, d))
                continue
            if stopped is None and d["decision"] != "ship":
                stopped = d["decision"]
            reason = d["decision"] if d["decision"] != "ship" else ("beyond the slots" if len(taken) >= slots else "after a failed rank")
            if d["decision"] == "ship" and stopped:
                reason = f"after a rank that is {stopped}"
            if reason == "beyond the slots":
                continue
            excluded.append({"club": club, "scope": scope, "category": cat, "rank": c["rank"], "name": c["name"], "years": c["years"],
                             "reason": reason, "guide": c["value"], "wikipedia": (c.get("wikipedia") or {}).get("value"),
                             "nflverse": (c.get("nflverse") or {}).get("value"), "detail": d["wikipedia"] + "/" + d["nflverse"]})
        if taken:
            out = []
            for c, d in taken:
                row = {"rank": c["rank"], "name": c["name"], "years": c["years"], "value": clean_number(c["value"]),
                       "confirmed_by": d["confirmed_by"]}
                if scope == "career" and c.get("link") is not None:
                    row["link"] = c["link"]
                if c["kind"] == "column":
                    row["basis"] = "column"
                out.append(row)
            clubs[club][scope][cat] = out
            counts["shipped"][scope] += len(out)
    for e in excluded:
        counts["excluded"][e["reason"]] = counts["excluded"].get(e["reason"], 0) + 1
    # lists the guide does not print at all
    for m in evidence.get("missing", []):
        excluded.append({"club": m["club"], "scope": m["scope"], "category": m["category"], "rank": None, "name": None, "years": None,
                         "reason": "not printed in the guide", "guide": None, "wikipedia": None, "nflverse": None, "detail": m.get("why", "")})
        counts["excluded"]["not printed in the guide"] = counts["excluded"].get("not printed in the guide", 0) + 1
    data = {
        "schema": SCHEMA, "base_year": 2026, "through_season": evidence["through_season"],
        "categories": CATEGORIES,
        "rules": evidence["rules"],
        "sources": evidence["public_sources"],
        "counts": counts,
        "clubs": clubs,
    }
    return data, excluded


# ------------------------------------------------------------------------------------------------ build
def load_guides(folder: Path, clubs=None) -> dict:
    out = {}
    for p in sorted(Path(folder).glob("*.json")):
        if p.name.startswith("_") or (clubs and p.stem not in clubs):
            continue
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def select_rows(lst: dict, scope: str):
    limit = SLOTS[scope] if scope != "career" else 3
    return [(rk, r) for rk, r in rank_rows(lst) if rk <= limit]


RULES = {
    "career": "Regular-season totals with the club since the franchise began, through the 2025 season. Sacks follow what each club's own list says (official sacks only where the list says since 1982 or later).",
    "season": "The club's best regular season in the category, through 2025.",
    "game": "The club's best regular-season game in the category, through 2025.",
    "shipping": "A value ships only when the club's own 2026 media guide and a second, independent source agree: the player's Wikipedia season table summed over the club, or nflverse play-by-play totals where they cover the whole career. A disagreement, a single source or a failed earlier rank keeps the row out (see the evidence file).",
    "ranks": "A club's list ships its longest run of verified ranks from rank 1. basis column: the guide prints the stat only as a column of a list ranked by another stat, so the order holds for the printed rows only.",
}
PUBLIC_SOURCES = {
    "club_guides": "Each club's own 2026 media guide (Internet Archive collection nfl-media-guides); the Steelers' 2026 guide is not online, so their 2025 edition is used with the 2025 season added from nflverse where checked.",
    "wikipedia": "Wikipedia player articles, NFL career statistics tables (CC BY-SA 4.0), regular-season rows summed per club.",
    "nflverse": "nflverse weekly player stats 1999-2025 (CC-BY-4.0), regular season, summed per club.",
}


def cmd_build(args) -> int:
    guides = load_guides(Path(args.guides), set(args.clubs.split(",")) if args.clubs else None)
    wiki = Wiki(args.wiki_cache)
    nv = NFLverse(args.nflverse).load()
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    cohort_full = {(norm(r[1]), norm(r[2]), r[3]): r[0] for r in cohort["records"]}
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
        return {"pool": "primary", "index": idx, "first": r["first_name"], "last": r["last_name"], "birth_date": r["birth_date"]} if idx is not None else None

    # --- which (club, player) pairs need a Wikipedia page
    need: dict = {}
    for club, g in guides.items():
        for lst in g["lists"]:
            for rk, r in select_rows(lst, lst["scope"]):
                ys = parse_years(r["years"]) if lst["scope"] == "career" else set()
                need.setdefault((club, r["name"]), set()).update(ys)
    resolved = {}
    cache_file = Path(args.wiki_cache) / "resolved.json"
    if cache_file.exists():
        resolved = json.loads(cache_file.read_text(encoding="utf-8"))
    for (club, name), ys in sorted(need.items()):
        key = f"{club}|{name}"
        if key in resolved:
            continue
        found = None
        for cand in title_candidates(name):
            pg = wiki.page(cand)
            if pg.get("missing"):
                continue
            r = club_sums(pg["html"], club)
            if years_overlap_ok(r["years"], ys):
                found = {"title": cand, "retrieved": pg["retrieved"], "sums": r["sums"], "seasons": r["seasons"], "years": r["years"],
                         "ambiguous": r["ambiguous"]}
                break
        resolved[key] = found
        cache_file.write_text(json.dumps(resolved), encoding="utf-8")
    wiki.fill_revids(sorted({v["title"] for v in resolved.values() if v}))
    for v in resolved.values():
        if v:
            pg = json.loads(wiki.path(v["title"]).read_text(encoding="utf-8"))
            v["revid"], v["canonical_title"] = pg.get("revid"), pg.get("canonical_title", v["title"])
    # --- candidates
    cands, lists, missing = [], [], []
    for club, g in sorted(guides.items()):
        for m in g.get("missing", []):
            missing.append({"club": club, "scope": m["scope"], "category": m["category"], "why": m.get("why", "")})
        for lst in g["lists"]:
            scope, cat = lst["scope"], lst["category"]
            lists.append({"club": club, "scope": scope, "category": cat, "title": lst["title"], "page": lst["pdf_page"], "kind": lst["kind"],
                          "ranked_by": lst["ranked_by"], "scope_note": lst["scope_note"], "complete_to": lst.get("complete_to"),
                          "rows": [[r.get("rank"), r["name"], r["years"], r["value"]] for r in lst["rows"]]})
            for order, (rk, r) in enumerate(select_rows(lst, scope)):
                v1 = clean_number(r["value"])
                ys = parse_years(r["years"]) if scope == "career" else ({year_of(r["years"])} - {None})
                res = resolved.get(f"{club}|{r['name']}")
                c = {"club": club, "scope": scope, "category": cat, "rank": rk, "order": order, "name": r["name"], "years": r["years"],
                     "value": v1, "kind": lst["kind"], "guide": {"page": lst["pdf_page"], "title": lst["title"], "raw": r["raw"]}}
                if res:
                    if scope == "career":
                        wv = res["sums"].get(cat)
                    else:
                        yr = next(iter(ys)) if ys else None
                        wv = res["seasons"].get(cat, {}).get(str(yr)) if scope == "season" and yr else None
                    c["wikipedia"] = {"title": res["canonical_title"] if res.get("canonical_title") else res["title"], "revid": res.get("revid"),
                                      "retrieved": res["retrieved"], "value": None if wv is None else clean_number(wv), "years": [res["years"][0], res["years"][-1]] if res["years"] else []}
                pid = nv.find(club, r["name"], ys) if cat != "tackles" else None
                if pid is not None:
                    if scope == "career":
                        have = nv.career.get((club, pid), {}).get(cat, 0.0)
                        covered = bool(ys) and all(NV_WINDOW[0] <= y <= NV_WINDOW[1] for y in ys)
                        c["nflverse"] = {"value": clean_number(have), "covered": covered, "player": nv.names[pid]}
                    else:
                        yr = next(iter(ys)) if ys else None
                        if yr and NV_WINDOW[0] <= yr <= NV_WINDOW[1]:
                            if scope == "season":
                                have = nv.season.get((club, pid, yr), {}).get(cat, 0.0)
                            else:
                                have = max((x[0] for x in nv.game.get((club, cat), []) if x[1] == pid and x[2] == yr), default=0.0)
                            c["nflverse"] = {"value": clean_number(have), "covered": True, "player": nv.names[pid]}
                if scope == "career":
                    c["link"] = link_of(club, r["name"])
                cands.append(c)
    evidence = {
        "schema": EVIDENCE_SCHEMA, "through_season": THROUGH, "retrieved": time.strftime("%Y-%m-%d", time.gmtime()),
        "rules": RULES, "public_sources": PUBLIC_SOURCES,
        "sources": {"nflverse_files": nv.hashes, "guides": {club: {"item": g["guide_ident"], "through_season": g["through_season"], "notes": g.get("notes", [])}
                                                              for club, g in sorted(guides.items())}},
        "lists": lists, "missing": missing, "candidates": cands,
    }
    data, excluded = assemble(evidence)
    evidence["excluded"] = excluded
    Path(args.evidence).write_text(json.dumps(evidence, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    Path(args.out).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
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


def cmd_fetch_nflverse(args) -> int:
    dest = Path(args.cache)
    dest.mkdir(parents=True, exist_ok=True)
    names = [f"stats_player/stats_player_week_{y}.csv.gz" for y in range(NV_WINDOW[0], NV_WINDOW[1] + 1)]
    names += ["rosters/roster_2026.csv", "players/players.csv"]
    for n in names:
        target = dest / Path(n).name
        if target.exists() and target.stat().st_size:
            continue
        with urllib.request.urlopen(urllib.request.Request(f"{NV_URL}/{n}", headers={"User-Agent": UA}), timeout=180) as r:     # nosec B310 - fixed https host
            target.write_bytes(r.read())
        print("fetched", target.name)
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
    b.add_argument("--out", default=str(DATA))
    b.add_argument("--evidence", default=str(EVIDENCE))
    b.set_defaults(fn=cmd_build)
    v = sub.add_parser("verify")
    v.add_argument("--out", default=str(DATA))
    v.add_argument("--evidence", default=str(EVIDENCE))
    v.set_defaults(fn=cmd_verify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
