"""Real-player ratings on NFL 2K5's own scale, from one season's real statistics. DESIGN / PROVED OFFLINE.

Built by job m2 (moments wave, 2026-09-23) for the 25th Anniversary team-seasons, and written as a reusable
module (job u1 feeds it 2025 statistics with 2026 roster rows). 2K never rated these players; this is a model,
not 2K's data, and nobody has played it (UNWITNESSED).

The method (full write-up: docs/nfl2k5_ratings_model.md):

1. Every player has a 2K5 position (the 17 retail codes). A production score for that position is computed
   from the season's real statistics (nflverse ``stats_player_reg_<season>``), plus the weeks he started
   (nflverse weekly depth charts) and his snap share (nflverse snap counts, 2012 on) where those exist.
2. The score becomes a percentile against the whole league at that 2K5 position in that season (the season
   roster is the population, so backups who never played rank at the bottom, as they do in a real depth chart).
3. The percentile is looked up on 2K5's own scale. ``data/nfl2k5_ratings_reference.json`` holds, per retail
   position, two tables built from the retail 2004 rosters of the 32 clubs (1,696 players):
   - ``quantiles``: each rating's own distribution. A position's skill ratings (for a QB: accuracy, arm,
     reading coverage) take the value at the player's percentile, so the league's best passer gets the
     accuracy of 2K5's best passer. Each skill follows its own real aspect where the statistics carry it
     (completion rate for accuracy, air yards per attempt for arm, sacks for pass rush, and so on).
   - ``profile``: the ratings of the retail players ranked at the same percentile (a kernel-weighted mean
     over retail players ordered by the studio's documented OVR estimate). Every other rating comes from it.
4. Measurables override the profile where they exist. Speed, in this order: a player who is also in the retail
   2004 rosters keeps his own retail speed (the caller passes his retail ratings as ``anchors``; they also carry
   his agility, strength and jumping); else the nflverse combine 40-yard time; else a cited 40 from the
   caller's ``forty_sources`` file (a combine time the nflverse file lacks, then a pro-day time, then another
   cited time whose event the source does not name); else the position profile, recorded in the basis as
   ``speed_source: "profile"``. Every 40 maps onto 2K5's scale the same way (2K5's own speed follows the combine
   40: speed = 315.1 - 50.7 x forty, r = -0.949 over 794 retail players, fitted when the reference is built).
5. The three style bytes follow retail's own conventions (kicking style 99/1/49, power-run style by position
   and weight, scramble 5 for everyone but a QB, whose value follows his rushing).

Inputs are plain dicts (CSV rows). Nothing here reads the disc except ``build_reference`` (which is handed a
decoded retail roster document by the caller). Standard library only.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import io
import json
import math
import unicodedata
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from . import nfl2k5_roster_records as rr

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE = ROOT / "data/nfl2k5_ratings_reference.json"
DEFAULT_FORTY_SOURCES = ROOT / "data/nfl2k5_ratings_forty_sources.json"
REFERENCE_SCHEMA = "nfl2k5.ratings_reference.v1"
FORTY_SOURCES_SCHEMA = "nfl2k5.forty_sources.v1"
MODEL_VERSION = "m2-ratings-3"
EVIDENCE = "DESIGN / PROVED OFFLINE: a model from real statistics, not 2K's ratings; unwitnessed in play"
RATINGS = tuple(rr.RATING_BYTE_ORDER)
POSITIONS = tuple(rr.POSITIONS)
GRID_POINTS = 41
GRID = tuple(i / (GRID_POINTS - 1) for i in range(GRID_POINTS))
PROFILE_BANDWIDTH = 0.05

# Starters per team at each 2K5 position. A player listed within these depths (``depth`` 1-based) rates at least like
# the league's weakest regular starter at his position that season: the value percentile of rank 32 x starters. This
# is what lets a player who started the moment's game after a partial regular season (Nick Foles, Super Bowl LII)
# play like a starter.
STARTERS = {"QB": 1, "HB": 1, "FB": 1, "WR": 2, "TE": 1, "T": 2, "G": 2, "C": 1, "DE": 2, "DT": 2, "OLB": 2, "ILB": 1,
            "CB": 2, "FS": 1, "SS": 1, "K": 1, "P": 1}
STYLE = ("kicking_style", "power_run_style", "scramble")
PHYSICAL = ("speed", "agility", "strength", "jumping")
ANCHORED_EXTRA = {"QB": ("pass_arm_strength",), "K": ("kick_power",), "P": ("kick_power",)}
AGE_DECLINE = ("speed", "agility")      # -1 per year of age past 30 on an anchored rating
# Where a player's speed comes from, best first. A cited 40 (``forty_sources``) is used only when the nflverse
# combine file has no time for him; its kinds rank combine (a real combine time the file lacks, for example before
# 2000), then pro day, then "other" (a cited time whose event the source does not name).
FORTY_KINDS = ("combine", "pro_day", "other")
SPEED_SOURCES = ("retail_anchor", "combine", "cited_combine", "pro_day", "other_40", "profile")
FORTY_RANGE = (4.1, 6.2)

# ------------------------------------------------------------------------------------------ positions
# nflverse roster position (and depth-chart position where the roster gives one) -> 2K5 retail code.
DIRECT = {"QB": "QB", "K": "K", "PK": "K", "P": "P", "WR": "WR", "TE": "TE", "FB": "FB", "RB": "HB", "HB": "HB",
          "T": "T", "OT": "T", "LT": "T", "RT": "T", "G": "G", "OG": "G", "LG": "G", "RG": "G", "C": "C",
          "DE": "DE", "LE": "DE", "RE": "DE", "LDE": "DE", "RDE": "DE", "EDGE": "DE", "DT": "DT", "NT": "DT",
          "LDT": "DT", "RDT": "DT", "OLB": "OLB", "LOLB": "OLB", "ROLB": "OLB", "SLB": "OLB", "WLB": "OLB",
          "ILB": "ILB", "MLB": "ILB", "LILB": "ILB", "RILB": "ILB", "MIKE": "ILB", "CB": "CB", "LCB": "CB",
          "RCB": "CB", "NB": "CB", "FS": "FS", "SS": "SS"}
AMBIGUOUS = {"OL", "DL", "LB", "DB", "S", "SAF", "LS", "KR", "PR", ""}


def map_position(position: str, depth_chart_position: str = "", weight: float | None = None) -> str:
    """The 2K5 code for an nflverse roster row. Deterministic; the rules are listed in the docs."""
    for text in (depth_chart_position, position):
        text = (text or "").strip().upper()
        if text in DIRECT:
            return DIRECT[text]
    text = (position or "").strip().upper()
    w = float(weight) if weight not in (None, "") else 0.0
    if text == "OL":
        return "T" if w >= 315 else "G"
    if text == "DL":
        return "DT" if w >= 295 else "DE"
    if text == "LB":
        return "OLB"
    if text in ("S", "SAF"):
        return "SS" if w >= 208 else "FS"
    if text == "DB":
        return "CB" if w < 200 else "FS" if w < 208 else "SS"
    if text == "LS":
        return "C"
    return "WR"


# ------------------------------------------------------------------------------------------ helpers
def _num(value) -> float:
    if value in (None, "", "NA"):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _open_text(path):
    path = Path(path)
    if path.suffix == ".gz":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def read_csv(path) -> list[dict]:
    with _open_text(path) as handle:
        return list(csv.DictReader(handle))


_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name: str) -> str:
    """A loose join key for a person's name: lower case ASCII letters only, no generational suffix (so "Le Kevin
    Smith", "LeKevin Smith" and "T.J." against "TJ" meet)."""
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    for ch in ".,'`\"":
        text = text.replace(ch, "")
    words = [w for w in text.replace("-", " ").split() if w not in _SUFFIXES]
    return "".join(words)


def load_forty_sources(source) -> dict[str, dict]:
    """Cited 40-yard times keyed by gsis id, from a ``nfl2k5.forty_sources.v1`` JSON file (path) or a mapping.

    Each entry: ``forty`` (seconds), ``kind`` (one of FORTY_KINDS), ``source_url`` and ``quote`` (the words on the
    page that give the time); ``event``, ``name`` and ``note`` are optional. Entries without a time are allowed
    (they record that a search found none) and are skipped. Raises ValueError on a malformed entry.
    """
    if source is None:
        return {}
    data = source if isinstance(source, Mapping) else json.loads(Path(source).read_text(encoding="utf-8"))
    if "players" in data:
        if data.get("schema") != FORTY_SOURCES_SCHEMA:
            raise ValueError("unsupported forty sources schema")
        data = data["players"]
    out = {}
    for pid, entry in data.items():
        forty = entry.get("forty")
        if forty in (None, ""):
            continue
        forty = float(forty)
        if not FORTY_RANGE[0] <= forty <= FORTY_RANGE[1]:
            raise ValueError(f"{pid}: 40 time {forty} out of range")
        if entry.get("kind") not in FORTY_KINDS:
            raise ValueError(f"{pid}: kind must be one of {FORTY_KINDS}")
        if not entry.get("source_url") or not entry.get("quote"):
            raise ValueError(f"{pid}: a cited 40 needs source_url and quote")
        out[pid] = {**entry, "forty": forty}
    return out


def clamp(value: float, low: float = 0, high: float = 99) -> int:
    return int(max(low, min(high, round(value))))


def _shrink(successes: float, trials: float, prior: float, weight: float) -> float:
    return (successes + prior * weight) / (trials + weight) if trials + weight > 0 else prior


# ------------------------------------------------------------------------------------------ production
# One ``value`` score per position plus named aspects. Every formula is a plain weighted sum of season
# totals; the weights are the documented design (docs/nfl2k5_ratings_model.md), not fitted to 2K.
ASPECT_VOLUME = {  # shrinkage weight: the pseudo-volume of league-average performance added to each player
    "QB": 150.0, "HB": 60.0, "FB": 20.0, "WR": 40.0, "TE": 30.0, "K": 12.0, "P": 30.0,
}
QUALIFY = {  # the volume that puts a player in the comparison table for a rate or per-attempt aspect
    "QB": 150.0, "HB": 60.0, "FB": 20.0, "WR": 30.0, "TE": 20.0, "K": 10.0, "P": 30.0,
}
# A rate aspect moves the value percentile in logit space: logit(q) + strength x volume trust x (aspect rank - 0.5).
# In the middle of the league that is about +/-0.23 at strength 2; near the top it compresses, so the league's best
# passers are told apart instead of all reaching 2K5's ceiling. Arm strength is mostly physical and leans on air
# yards per attempt (largely a scheme number), so it moves half as far.
ASPECT_STRENGTH = {"accuracy": 2.0, "read": 2.0, "arm": 1.0, "hands": 2.0, "security": 1.5, "power": 1.5,
                   "placement": 1.5}


def _logit(q: float) -> float:
    q = min(0.995, max(0.005, q))
    return math.log(q / (1 - q))


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def production(position: str, s: Mapping[str, float], extra: Mapping[str, float]) -> dict:
    """Season production for one player at one 2K5 position.

    ``s`` is the nflverse season stats row (numbers), ``extra`` holds ``starts`` (weeks as a depth-chart
    starter) and ``snaps`` (sum of the per-game snap share, 0..1 per game). Returns the value score, the
    aspect scores and the volume behind the aspects.
    """
    starts, snaps = extra.get("starts", 0.0), extra.get("snaps", 0.0)
    tackles = s["def_tackles_solo"] + 0.5 * s["def_tackle_assists"] + 0.5 * s["def_tackles_with_assist"]
    fumbles_lost = s["rushing_fumbles_lost"] + s["receiving_fumbles_lost"] + s["sack_fumbles_lost"]
    touches = s["carries"] + s["receptions"]
    if position == "QB":
        dropbacks = s["attempts"] + s["sacks_suffered"]
        value = s["passing_epa"] + s["rushing_epa"] + 0.15 * (s["attempts"] + s["carries"])
        air = s["passing_air_yards"]
        arm = (air / s["attempts"]) if s["attempts"] and air else (s["passing_yards"] / s["attempts"] if s["attempts"] else 0.0)
        return {"value": value, "volume": s["attempts"],
                "accuracy": ("rate", s["completions"], s["attempts"]),
                "arm": ("mean", arm, s["attempts"]),
                "read": ("mean", (s["passing_epa"] / dropbacks) if dropbacks else 0.0, dropbacks),
                "mobility": ("mobility", s["rushing_yards"] / s["games"] if s["games"] else 0.0,
                             s["attempts"] if s["games"] >= 4 else 0.0)}
    if position in ("HB", "FB"):
        value = (s["rushing_yards"] + s["receiving_yards"] + 20 * (s["rushing_tds"] + s["receiving_tds"])
                 + 5 * s["receptions"] - 40 * fumbles_lost + 25 * snaps + 3 * starts)
        return {"value": value, "volume": touches,
                "receiving": ("plain", s["receiving_yards"] + 5 * s["receptions"] + 20 * s["receiving_tds"]),
                "security": ("rate_low", fumbles_lost, touches)}
    if position in ("WR", "TE"):
        value = (s["receiving_yards"] + 20 * s["receiving_tds"] + 5 * s["receptions"] + s["rushing_yards"]
                 - 40 * fumbles_lost + 25 * snaps + 3 * starts)
        return {"value": value, "volume": s["targets"],
                "hands": ("rate", s["receptions"], s["targets"])}
    if position in ("T", "G", "C"):
        return {"value": 10 * starts + 17 * snaps, "volume": 0.0}
    if position in ("DE", "DT"):
        rush = 4 * s["def_sacks"] + 1.5 * s["def_qb_hits"]
        stop = tackles + 1.5 * s["def_tackles_for_loss"]
        value = rush + 0.5 * stop + 3 * s["def_fumbles_forced"] + 2 * s["def_pass_defended"] + 6 * s["def_tds"] + 2 * starts + 20 * snaps
        return {"value": value, "volume": 0.0, "rush": ("plain", rush), "stop": ("plain", stop)}
    if position in ("OLB", "ILB"):
        rush = 4 * s["def_sacks"] + 1.5 * s["def_qb_hits"]
        stop = tackles + 2 * s["def_tackles_for_loss"]
        cover = 4 * s["def_interceptions"] + 2 * s["def_pass_defended"]
        value = stop + 0.75 * rush + cover + 3 * s["def_fumbles_forced"] + 6 * s["def_tds"] + 2 * starts + 20 * snaps
        return {"value": value, "volume": 0.0, "rush": ("plain", rush), "stop": ("plain", stop), "cover": ("plain", cover)}
    if position in ("CB", "FS", "SS"):
        cover = 5 * s["def_interceptions"] + 3 * s["def_pass_defended"]
        stop = tackles + 1.5 * s["def_tackles_for_loss"]
        weight = 0.5 if position == "CB" else 0.8
        value = cover + weight * stop + 3 * s["def_fumbles_forced"] + 2 * s["def_sacks"] + 6 * s["def_tds"] + 2 * starts + 20 * snaps
        return {"value": value, "volume": 0.0, "cover": ("plain", cover), "stop": ("plain", stop),
                "ball": ("plain", s["def_interceptions"])}
    if position == "K":
        made_long = s["fg_made_50_59"] + s["fg_made_60_"]
        value = (3 * s["fg_made"] + s["fg_made_40_49"] + 2 * made_long - 2 * s["fg_missed"]
                 + 0.5 * s["pat_made"] - 2 * s["pat_missed"])
        return {"value": value, "volume": s["fg_att"],
                "accuracy": ("rate", s["fg_made"], s["fg_att"]),
                "power": ("plain", s["fg_long"] + 4 * made_long if s["fg_made"] else 0.0)}
    if position == "P":
        gross = s["pt_yards"] / s["pt_att"] if s["pt_att"] else 0.0
        net = s["pt_net_yards"] / s["pt_att"] if s["pt_att"] and s["pt_net_yards"] else gross
        value = s["pt_att"] * 0.5 + (gross - 40) * 4 * min(1.0, s["pt_att"] / 40)
        return {"value": value, "volume": s["pt_att"],
                "power": ("mean", gross, s["pt_att"]),
                "placement": ("rate", s["pt_inside_20"], s["pt_att"])}
    raise ValueError(f"unknown 2K5 position {position!r}")


# Which percentile drives each skill rating. Anything not named here comes from the profile at the value
# percentile; the three style bytes and the physical ratings have their own rules.
SKILL_DRIVERS = {
    "QB": {"pass_accuracy": "accuracy", "pass_arm_strength": "arm", "pass_read_coverage": "read",
           "composure": "value", "consistency": "value", "leadership": "value"},
    "HB": {"break_tackle": "value", "catch": "receiving", "run_route": "receiving", "hold_onto_ball": "security"},
    "FB": {"run_blocking": "value", "break_tackle": "value", "catch": "receiving", "hold_onto_ball": "security"},
    "WR": {"catch": "hands", "run_route": "value", "hold_onto_ball": "value"},
    "TE": {"catch": "hands", "run_route": "value", "run_blocking": "value", "pass_blocking": "value"},
    "T": {"run_blocking": "value", "pass_blocking": "value"},
    "G": {"run_blocking": "value", "pass_blocking": "value"},
    "C": {"run_blocking": "value", "pass_blocking": "value"},
    "DE": {"pass_rush": "rush", "tackle": "stop", "run_coverage": "stop"},
    "DT": {"pass_rush": "rush", "tackle": "stop", "run_coverage": "stop"},
    "OLB": {"tackle": "stop", "run_coverage": "stop", "coverage": "cover", "pass_rush": "rush"},
    "ILB": {"tackle": "stop", "run_coverage": "stop", "coverage": "cover", "pass_rush": "rush"},
    "CB": {"coverage": "cover", "tackle": "stop", "catch": "ball"},
    "FS": {"coverage": "cover", "tackle": "stop", "catch": "ball", "run_coverage": "stop"},
    "SS": {"coverage": "cover", "tackle": "stop", "catch": "ball", "run_coverage": "stop"},
    "K": {"kick_power": "power", "kick_accuracy": "accuracy"},
    "P": {"kick_power": "power", "kick_accuracy": "placement"},
}
STAT_COLUMNS = (
    "games", "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered",
    "sack_fumbles_lost", "passing_air_yards", "passing_epa", "carries", "rushing_yards", "rushing_tds",
    "rushing_fumbles_lost", "rushing_epa", "receptions", "targets", "receiving_yards", "receiving_tds",
    "receiving_fumbles_lost", "def_tackles_solo", "def_tackles_with_assist", "def_tackle_assists",
    "def_tackles_for_loss", "def_fumbles_forced", "def_sacks", "def_qb_hits", "def_interceptions",
    "def_pass_defended", "def_tds", "fg_made", "fg_att", "fg_missed", "fg_long", "fg_made_40_49", "fg_made_50_59",
    "fg_made_60_", "pat_made", "pat_missed", "pt_att", "pt_yards", "pt_inside_20", "pt_net_yards",
)
EMPTY_STATS = {name: 0.0 for name in STAT_COLUMNS}


# ------------------------------------------------------------------------------------------ season
class SeasonStats:
    """One season of league-wide real data: statistics, starts, snaps and the population per 2K5 position."""

    def __init__(self, season: int):
        self.season = int(season)
        self.stats: dict[str, dict] = {}
        self.starts: dict[str, float] = {}
        self.snaps: dict[str, float] = {}
        self.population_rows: dict[str, str] = {}   # player id -> 2K5 position
        self.forty: dict[str, float] = {}                # nflverse combine 40 by gsis id
        self.forty_cited: dict[str, dict] = {}           # cited 40s for players the combine file lacks
        self.aspect_tables: dict[tuple[str, str], list[float]] = {}
        self.aspect_priors: dict[tuple[str, str], float] = {}
        self.sources: list[str] = []

    # -- construction
    @classmethod
    def from_files(cls, season: int, stats, roster=None, *, depth_charts=None, snap_counts=None,
                   combine=None, players=None, forty_sources=None) -> "SeasonStats":
        """Load nflverse files for one season (CSV or CSV.GZ paths). Only ``stats`` is required.

        stats: stats_player_reg_<season>; roster: roster_<season> (the population, recommended);
        depth_charts: depth_charts_<season> (starts); snap_counts: snap_counts_<season> (2012 on);
        combine: combine (40-yard times); players: players (gsis id <-> pfr id, names and draft years; a combine
        row without a pfr id joins on name and draft year when exactly one player matches);
        forty_sources: cited 40s for players the combine file lacks (``load_forty_sources``: a path or mapping).
        """
        self = cls(season)
        self.sources.append(Path(stats).name)
        for row in read_csv(stats):
            if row.get("season_type", "REG") not in ("REG", ""):
                continue
            pid = row.get("player_id", "")
            if pid:
                self.stats[pid] = {name: _num(row.get(name)) for name in STAT_COLUMNS}
                self.population_rows.setdefault(pid, map_position(row.get("position", ""), "", None))
        if roster is not None:
            self.sources.append(Path(roster).name)
            for row in read_csv(roster):
                if row.get("status", "ACT") in ("DEV", "CUT", "RET", "NWT", "EXE", "TRC", "TRT", "TRD"):
                    continue
                pid = row.get("gsis_id", "")
                if pid:
                    self.population_rows[pid] = map_position(row.get("position", ""), row.get("depth_chart_position", ""),
                                                             row.get("weight"))
        if depth_charts is not None:
            self.sources.append(Path(depth_charts).name)
            self.starts = starts_from_depth_charts(read_csv(depth_charts))
        if snap_counts is not None:
            self.sources.append(Path(snap_counts).name)
            ids = {}
            if players is not None:
                for row in read_csv(players):
                    if row.get("pfr_id") and row.get("gsis_id"):
                        ids[row["pfr_id"]] = row["gsis_id"]
            for row in read_csv(snap_counts):
                if row.get("game_type", "REG") != "REG":
                    continue
                pid = ids.get(row.get("pfr_player_id", ""), "")
                if pid:
                    share = max(_num(row.get("offense_pct")), _num(row.get("defense_pct")))
                    self.snaps[pid] = self.snaps.get(pid, 0.0) + share
        if combine is not None:
            ids, by_name = {}, {}
            if players is not None:
                for row in read_csv(players):
                    gsis = row.get("gsis_id")
                    if not gsis:
                        continue
                    if row.get("pfr_id"):
                        ids[row["pfr_id"]] = gsis
                    year = (row.get("draft_year") or row.get("rookie_season") or "").strip()
                    if year and row.get("display_name"):
                        by_name.setdefault((name_key(row["display_name"]), year), set()).add(gsis)
            for row in read_csv(combine):
                forty = _num(row.get("forty"))
                if not FORTY_RANGE[0] <= forty <= FORTY_RANGE[1]:
                    continue
                pid = ids.get(row.get("pfr_id") or "", "")
                if not pid:
                    year = (row.get("draft_year") or row.get("season") or "").strip()
                    hits = by_name.get((name_key(row.get("player_name", "")), year), set())
                    pid = next(iter(hits)) if len(hits) == 1 else ""
                if pid:
                    self.forty.setdefault(pid, forty)
        for pid, entry in load_forty_sources(forty_sources).items():
            if pid not in self.forty:
                self.forty_cited[pid] = entry
        self._build_tables()
        return self

    def production_for(self, pid: str, position: str) -> dict:
        stats = self.stats.get(pid, EMPTY_STATS)
        return production(position, stats, {"starts": self.starts.get(pid, 0.0), "snaps": self.snaps.get(pid, 0.0)})

    def _build_tables(self) -> None:
        """Percentile tables per (position, aspect) over the season population.

        Rate and per-attempt aspects are shrunk toward the league's volume-weighted mean (the prior), so a
        player with 3 attempts is not the league's most accurate passer.
        """
        productions = {pid: self.production_for(pid, position) for pid, position in self.population_rows.items()}
        sums: dict[tuple[str, str], list[float]] = {}
        for pid, position in self.population_rows.items():
            for aspect, spec in productions[pid].items():
                if aspect in ("value", "volume") or spec[0] in ("plain", "mobility"):
                    continue
                kind, a, b = spec
                acc = sums.setdefault((position, aspect), [0.0, 0.0])
                if b > 0:
                    acc[0] += a if kind in ("rate", "rate_low") else a * b
                    acc[1] += b
        self.aspect_priors = {key: (a / b if b else 0.0) for key, (a, b) in sums.items()}
        values: dict[tuple[str, str], list[float]] = {}
        for pid, position in self.population_rows.items():
            prod = productions[pid]
            values.setdefault((position, "value"), []).append(prod["value"])
            for aspect, spec in prod.items():
                if aspect in ("value", "volume"):
                    continue
                if not self.qualified(position, spec):
                    continue
                values.setdefault((position, aspect), []).append(self.aspect_value(position, aspect, spec))
        self.aspect_tables = {key: sorted(v) for key, v in values.items()}

    @staticmethod
    def qualified(position: str, spec) -> bool:
        kind = spec[0]
        if kind == "plain":
            return True
        if kind == "mobility":
            return spec[2] >= 50
        return spec[2] >= QUALIFY.get(position, 20.0)

    def aspect_value(self, position: str, aspect: str, spec) -> float:
        """The comparable number for an aspect (higher is always better)."""
        kind = spec[0]
        if kind in ("plain", "mobility"):
            return float(spec[1])
        weight = ASPECT_VOLUME.get(position, 20.0)
        prior = self.aspect_priors.get((position, aspect), 0.0)
        if kind == "rate":
            return _shrink(spec[1], spec[2], prior, weight)
        if kind == "rate_low":
            return -_shrink(spec[1], spec[2], prior, weight)
        if kind == "mean":
            mean, volume = spec[1], spec[2]
            return (mean * volume + prior * weight) / (volume + weight) if volume + weight else prior
        raise ValueError(kind)

    def starter_floor(self, position: str) -> float:
        """Value percentile of the league's weakest regular starter at this position (rank 32 x starters)."""
        table = self.aspect_tables.get((position, "value")) or [0.0]
        rank = 32 * STARTERS.get(position, 1)
        if len(table) <= rank:
            return 0.5
        return self.percentile(position, "value", table[len(table) - rank])

    def percentile(self, position: str, aspect: str, value: float) -> float:
        table = self.aspect_tables.get((position, aspect)) or self.aspect_tables.get((position, "value")) or [0.0]
        below = bisect.bisect_left(table, value)
        above = bisect.bisect_right(table, value)
        return (below + 0.5 * (above - below)) / len(table)


def starts_from_depth_charts(rows: Sequence[Mapping]) -> dict[str, float]:
    """Weeks as a starter per player id.

    2001-2024 schema (weekly): one start per REG week with ``depth_team`` 1 in the offense or defense.
    2025+ schema (``dt`` snapshots with ``pos_rank``): 17 x the share of the team's snapshots in which the player
    is listed first at a position.
    """
    starts: dict[str, float] = {}
    if rows and "pos_rank" in rows[0]:
        snapshots: dict[str, set] = {}
        first: dict[str, set] = {}
        for row in rows:
            team, stamp, pid = row.get("team", ""), row.get("dt", ""), row.get("gsis_id", "")
            snapshots.setdefault(team, set()).add(stamp)
            if pid and str(row.get("pos_rank")) == "1":
                first.setdefault(pid, set()).add((team, stamp))
        for pid, marks in first.items():
            total = sum(len(snapshots.get(team, ())) for team in {t for t, _ in marks})
            starts[pid] = round(17.0 * len(marks) / total, 3) if total else 0.0
        return starts
    seen = set()
    for row in rows:
        if row.get("game_type", "REG") != "REG" or str(row.get("depth_team", "")) != "1":
            continue
        if row.get("formation") not in ("Offense", "Defense", None, ""):
            continue
        pid = row.get("gsis_id", "")
        key = (pid, row.get("week"))
        if pid and key not in seen:
            seen.add(key)
            starts[pid] = starts.get(pid, 0.0) + 1.0
    return starts


# ------------------------------------------------------------------------------------------ reference
class Reference:
    """The retail 2004 scale: per position, per rating quantile tables and the ranked profile."""

    def __init__(self, data: Mapping):
        if data.get("schema") != REFERENCE_SCHEMA:
            raise ValueError("unsupported ratings reference schema")
        self.data = data
        self.grid = tuple(data["grid"])
        self.positions = data["positions"]
        self.speed = data["speed_from_forty"]

    @classmethod
    def load(cls, path=DEFAULT_REFERENCE) -> "Reference":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _interp(self, table: Sequence[float], q: float) -> float:
        q = max(0.0, min(1.0, q))
        at = q * (len(table) - 1)
        low = int(math.floor(at))
        high = min(low + 1, len(table) - 1)
        return table[low] + (table[high] - table[low]) * (at - low)

    def quantile(self, position: str, rating: str, q: float) -> float:
        return self._interp(self.positions[position]["quantiles"][rating], q)

    def profile(self, position: str, rating: str, q: float) -> float:
        return self._interp(self.positions[position]["profile"][rating], q)

    def speed_from_forty(self, forty: float) -> float:
        return self.speed["intercept"] + self.speed["slope"] * forty


def build_reference(document, *, forty_by_name: Mapping[str, float] | None = None, source: Mapping | None = None) -> dict:
    """Build the reference from a decoded retail roster (``nfl2k5_roster_records.RosterDocument``).

    Population: the players on the 32 NFL clubs (team records 0..31). Ranks use the studio's documented OVR
    estimate (``PlayerRecord.overall``). ``forty_by_name`` maps "first last" (lower case) to a combine 40 time
    and fits the speed line; it is optional (a missing fit keeps the documented default).
    """
    by_position: dict[str, list] = {p: [] for p in POSITIONS}
    speed_pairs = []
    for team in document.teams[:32]:
        for player in document.team_players(team.index):
            record = player.record
            ratings = record.ratings()
            by_position[record.position_name].append((record.overall(), player.first, player.last, ratings))
            if forty_by_name:
                forty = forty_by_name.get(f"{player.first} {player.last}".lower())
                if forty:
                    speed_pairs.append((forty, ratings["speed"]))
    positions = {}
    for position, players in by_position.items():
        players.sort(key=lambda item: (-item[0], item[2], item[1]))
        n = len(players)
        quantiles, profile = {}, {}
        for rating in RATINGS:
            values = sorted(item[3][rating] for item in players)
            quantiles[rating] = [round(_sorted_quantile(values, q), 1) for q in GRID]
            # percentile of the player ranked i (best = highest percentile)
            points = [(1.0 - (i + 0.5) / n, item[3][rating]) for i, item in enumerate(players)]
            profile[rating] = [round(_kernel(points, q, PROFILE_BANDWIDTH), 1) for q in GRID]
        positions[position] = {"n": n, "quantiles": quantiles, "profile": profile,
                               "starters": sum(1 for _ in players[:32])}
    speed = {"intercept": 314.61, "slope": -50.77, "n": 0, "r": None, "resid_sd": None,
             "note": "default: the fit made when the reference was designed (m2, 2026-09-23)"}
    if len(speed_pairs) >= 50:
        speed = _fit_line(speed_pairs)
    return {"schema": REFERENCE_SCHEMA, "model": MODEL_VERSION, "evidence": EVIDENCE,
            "source": dict(source or {}), "grid": list(GRID), "bandwidth": PROFILE_BANDWIDTH,
            "population": "retail 2004 rosters of the 32 NFL clubs, ranked by the studio OVR estimate",
            "positions": positions, "speed_from_forty": speed}


def _sorted_quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    at = q * (len(values) - 1)
    low = int(math.floor(at))
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (at - low)


def _kernel(points: Sequence[tuple[float, float]], q: float, bandwidth: float) -> float:
    total = weight_sum = 0.0
    for at, value in points:
        weight = math.exp(-0.5 * ((at - q) / bandwidth) ** 2)
        total += weight * value
        weight_sum += weight
    return total / weight_sum if weight_sum else 0.0


def _fit_line(pairs: Sequence[tuple[float, float]]) -> dict:
    n = len(pairs)
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    slope = sxy / sxx
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in pairs]
    return {"intercept": round(intercept, 3), "slope": round(slope, 3), "n": n,
            "r": round(sxy / math.sqrt(sxx * syy), 4),
            "resid_sd": round(math.sqrt(sum(r * r for r in resid) / n), 3),
            "note": "retail speed against the nflverse combine 40-yard time, players matched by exact name"}


# ------------------------------------------------------------------------------------------ rating
def style_bytes(position: str, weight: float, scramble_q: float, anchor: Mapping | None) -> dict:
    """Retail conventions (read off the 2004 rosters, see docs)."""
    kicking = 99 if position == "K" else 1 if position == "P" else 49
    if position in ("HB",):
        power = 99 if weight >= 228 else 1 if weight <= 208 else 50
    elif position == "WR":
        power = 99 if weight >= 212 else 1 if weight <= 186 else 50
    elif position in ("CB", "FS", "SS"):
        power = 1
    elif position in ("QB", "K", "P"):
        power = 50
    else:
        power = 99
    if position == "QB":
        if anchor and anchor.get("scramble") is not None:
            scramble = int(anchor["scramble"])             # 2K's own value for this QB (magnitude and parity)
        else:
            scramble = int(20 + 2 * round(38 * scramble_q))   # even values 20..96, the retail QB range
    else:
        scramble = 5
    return {"kicking_style": kicking, "power_run_style": power, "scramble": scramble}


def rate_player(row: Mapping, stats: SeasonStats, reference: Reference, *, honors: Mapping | None = None,
                anchor: Mapping | None = None) -> tuple[dict, dict]:
    """Ratings for one player row. Returns (28 ratings, basis).

    Row keys used: ``position`` (2K5 code), ``gsis_id`` (joins the statistics; empty = no statistics),
    ``weight``, ``birth_date`` (YYYY-MM-DD), ``years_pro`` (COMPLETED seasons, nflverse ``years_exp``, rookie = 0 --
    not the roster record's field, whose rookie is 1: convert with ``nfl2k5_roster_records.accrued_seasons``),
    ``draft_number`` (optional, rookie prior),
    ``depth`` (1-based, the fallback for linemen when no starts or snaps data exist).
    ``honors``: optional level for this player: "AP1", "AP2" or "PB" (floors the value percentile).
    ``anchor``: optional retail 2004 ratings of the same player (a dict of the 28), for physicals and style.
    """
    position = row["position"]
    if position not in POSITIONS:
        raise ValueError(f"not a retail position: {position!r}")
    pid = row.get("gsis_id") or ""
    prod = stats.production_for(pid, position)
    has_stats = pid in stats.stats or pid in stats.starts or pid in stats.snaps
    basis = {"model": MODEL_VERSION, "season": stats.season, "position": position, "has_stats": has_stats}
    q_value = stats.percentile(position, "value", prod["value"])
    # linemen with no starts or snaps data for the season (before 2001): the team depth chart decides
    if position in ("T", "G", "C") and not stats.starts and not stats.snaps:
        depth = int(row.get("depth") or 9)
        starters = 1 if position == "C" else 2
        q_value = 0.72 if depth <= starters else 0.35 if depth <= starters + 2 else 0.2
        basis["lineman_fallback"] = "no starts/snaps data for the season; percentile from the team depth chart"
    # rookies with no statistics: a draft-position prior instead of the bottom of the league
    years = int(_num(row.get("years_pro")))
    if not has_stats and years == 0:
        pick = _num(row.get("draft_number"))
        prior = 0.55 if 0 < pick <= 32 else 0.42 if 0 < pick <= 64 else 0.32 if 0 < pick <= 128 else 0.2
        q_value = max(q_value, prior)
        basis["rookie_prior"] = prior
    depth = int(_num(row.get("depth"))) if row.get("depth") not in (None, "") else 0
    if 1 <= depth <= STARTERS[position]:
        floor = stats.starter_floor(position)
        if q_value < floor:
            basis["starter_floor"] = round(floor, 4)
            q_value = floor
    level = (honors or {}).get(pid) if isinstance(honors, Mapping) else None
    floors = {"AP1": 0.97, "AP2": 0.94, "PB": 0.9}
    if level in floors:
        q_value = max(q_value, floors[level])
        basis["honor"] = level
    basis["q_value"] = round(q_value, 4)
    aspects = {"value": q_value}
    for aspect, spec in prod.items():
        if aspect in ("value", "volume"):
            continue
        kind = spec[0]
        if kind == "mobility":
            # the QB's rushing per game against QBs with real playing time; a QB without it is a pocket passer
            q_aspect = stats.percentile(position, aspect, spec[1]) if stats.qualified(position, spec) else 0.3
        elif kind == "plain":
            q_aspect = 0.5 * stats.percentile(position, aspect, spec[1]) + 0.5 * q_value
        else:
            # a rate or per-attempt aspect ranks the player among qualified players and shifts his value
            # percentile by up to +/- ASPECT_SHIFT / 2, scaled by how much volume he had
            q_raw = stats.percentile(position, aspect, stats.aspect_value(position, aspect, spec))
            trust = min(1.0, spec[2] / QUALIFY.get(position, 20.0)) if spec[2] > 0 else 0.0
            q_aspect = _logistic(_logit(q_value) + ASPECT_STRENGTH.get(aspect, 2.0) * trust * (q_raw - 0.5))
        if level in floors:
            q_aspect = max(q_aspect, floors[level] - 0.1)
        aspects[aspect] = q_aspect
    basis["q_aspects"] = {k: round(v, 4) for k, v in aspects.items() if k != "value"}
    drivers = SKILL_DRIVERS[position]
    ratings = {}
    for rating in RATINGS:
        if rating in STYLE:
            continue
        driver = drivers.get(rating)
        if driver:
            ratings[rating] = clamp(reference.quantile(position, rating, aspects.get(driver, q_value)))
        else:
            ratings[rating] = clamp(reference.profile(position, rating, q_value))
    # physicals: the retail 2004 ratings of the same player when the caller has them, else measurables
    weight = _num(row.get("weight")) or 0.0
    if anchor:
        age_now = _age(row.get("birth_date"), stats.season)
        decline = max(0, age_now - 30) if age_now else 0
        for rating in PHYSICAL:
            if rating in anchor:
                ratings[rating] = clamp(anchor[rating] - (decline if rating in AGE_DECLINE else 0))
        for rating in ANCHORED_EXTRA.get(position, ()):
            if rating in anchor:   # arm or leg: half 2K's own 2004 rating, half this season's model value
                ratings[rating] = clamp(0.5 * anchor[rating] + 0.5 * ratings[rating])
        basis["anchor"] = "retail 2004 physical ratings of the same player" + (f", minus {decline} for age" if decline else "")
    # speed: retail anchor, else the combine 40, else a cited 40 (combine, pro day, other), else the profile
    if anchor and "speed" in anchor:
        basis["speed_source"] = "retail_anchor"
    elif stats.forty.get(pid):
        ratings["speed"] = clamp(reference.speed_from_forty(stats.forty[pid]), 30, 99)
        basis["forty"], basis["speed_source"] = stats.forty[pid], "combine"
    elif pid in stats.forty_cited:
        cited = stats.forty_cited[pid]
        ratings["speed"] = clamp(reference.speed_from_forty(cited["forty"]), 30, 99)
        basis["forty"] = cited["forty"]
        basis["speed_source"] = {"combine": "cited_combine", "pro_day": "pro_day"}.get(cited["kind"], "other_40")
        basis["forty_source"] = cited["source_url"]
    else:
        basis["speed_source"] = "profile"
        basis["speed_flag"] = "no 40-yard time found: speed from the position profile"
    ratings.update(style_bytes(position, weight, aspects.get("mobility", q_value), anchor))
    return {rating: ratings[rating] for rating in RATINGS}, basis


def _age(birth_date, season: int) -> int:
    try:
        year, month, _ = (int(x) for x in str(birth_date)[:10].split("-"))
    except (TypeError, ValueError):
        return 0
    return season - year - (1 if month > 9 else 0)


def rate_players(rows: Iterable[Mapping], stats: SeasonStats, reference: Reference, *,
                 honors: Mapping | None = None, anchors: Mapping | None = None) -> list[dict]:
    """Rate a list of rows. Each output row is the input row plus the 28 ratings and ``rating_basis`` (JSON).

    ``anchors``: optional {gsis_id or "first last|birth_date": retail ratings} for players 2K5 already had.
    """
    out = []
    for row in rows:
        anchor = None
        if anchors:
            anchor = anchors.get(row.get("gsis_id") or "") or anchors.get(
                f"{row.get('first', '')} {row.get('last', '')}|{row.get('birth_date', '')}".lower())
        ratings, basis = rate_player(row, stats, reference, honors=honors, anchor=anchor)
        out.append({**row, **{k: str(v) for k, v in ratings.items()},
                    "rating_basis": json.dumps(basis, sort_keys=True, separators=(",", ":"))})
    return out


# ------------------------------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    rate = sub.add_parser("rate", help="rate a roster CSV (columns: position, gsis_id, weight, birth_date, ...)")
    rate.add_argument("--roster", required=True, type=Path)
    rate.add_argument("--season", required=True, type=int, help="the season whose statistics drive the ratings")
    rate.add_argument("--stats", required=True, type=Path, help="nflverse stats_player_reg_<season>.csv(.gz)")
    rate.add_argument("--population", type=Path, help="nflverse roster_<season>.csv (recommended)")
    rate.add_argument("--depth-charts", type=Path)
    rate.add_argument("--snap-counts", type=Path)
    rate.add_argument("--combine", type=Path)
    rate.add_argument("--players", type=Path, help="nflverse players.csv (joins snaps and combine by pfr id)")
    rate.add_argument("--forty-sources", type=Path, help="cited 40 times (nfl2k5.forty_sources.v1 JSON)")
    rate.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    rate.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    stats = SeasonStats.from_files(args.season, args.stats, args.population, depth_charts=args.depth_charts,
                                   snap_counts=args.snap_counts, combine=args.combine, players=args.players,
                                   forty_sources=args.forty_sources)
    rows = read_csv(args.roster)
    rated = rate_players(rows, stats, Reference.load(args.reference))
    fields = list(rows[0].keys()) if rows else []
    for name in (*RATINGS, "rating_basis"):
        if name not in fields:
            fields.append(name)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rated)
    print(json.dumps({"rated": len(rated), "out": str(args.out), "evidence": EVIDENCE}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
