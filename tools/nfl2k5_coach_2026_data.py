#!/usr/bin/env python3
"""Sourced 2026 head-coach records for the SOFTDRINK 2K28 roster: ratings, play-calling tendencies, announcer flag.

Job b780 c1-coachdata (design: b77_session/reports/b780_r2-coach_RESEARCH.md, design A0).  The 32 club coach records of
the v0.8 roster carry 2026 names and career numbers, but the 23 ratings, the tendency block and the flags are still the
2004 coach of that franchise (Andy Reid plays with Dick Vermeil's ratings).  This tool derives the 2026 values from
public data and writes ``data/nfl2k5_coaches_2026.json``; ``tools/nfl2k5_team_2026_roster.py`` merges a club's entry into
its roster-edits ``coaches`` entry, and ``nfl2k5_roster_records.apply_coach_records`` writes it.

Nothing here is a scouting opinion.  Every number is computed from named data with the formula in this file, the inputs
are pinned by SHA-256 in the output, and each coach's raw metrics and sample sizes are kept next to his ratings
("basis"), so a rating can be re-derived and argued with.  Where a coach has no evidence for a rating (a first-time head
coach has no head-coach games, a coach who never ran a special-teams unit has no kicking evidence) the rating is the
league baseline, never a guess.

Inputs (all public nflverse data, CC-BY-4.0, plus files already in this repository)
  games.csv                      every game 1999-2025 with scores, head coaches, spread line      (--nflverse)
  roster_YYYY.csv                gsis_id -> position, to split rushing and receiving by RB / WR / TE  (--nflverse)
  pbp_YYYY.parquet 2020-2025     play by play: EPA, success, sacks, hits, penalties, special teams     (--pbp-dir)
  pbp_participation_YYYY.parquet 2022-2025  offense formation and personnel per play                  (--participation-dir)
  data/vip/coach_sources_2026.json  which team and seasons each coach was head coach / coordinator (HC, OC, DC)
  data/vip/coaches/<CLUB>.json   the observed play-calling tendencies (nfl2k5_coach_tendencies)
  data/nfl2k5_teams_2026/<CLUB>.json  the head coach's name (and the spelling games.csv uses)
Reading parquet needs pyarrow; the committed JSON is what builds and tests use, so only a rebuild needs it.

Ratings (60-99 like the retail scale; football ratings centre on 78, character ratings on 83, 9 points per standard
deviation across the 32 coaches; a metric is first shrunk toward the league mean by n / (n + n0) so one short stint
cannot make an extreme rating):
  offense, pass_for, rush_for        team EPA per play / per dropback / per designed rush in the coach's HC and OC seasons
  defense, pass_coverage             team EPA allowed per play / per pass attempt in his HC and DC seasons
  pass_rush                          sack rate and QB-hit rate of that defense
  qb, wr, te, rb                     EPA and CPOE per attempt; EPA per target to WRs and TEs; EPA per carry of RBs
  ol, dl, lb, db                     sacks and hits allowed / run success; sacks, hits, run EPA allowed; run stuffs; coverage
  special_teams                      kicking and return EPA per game in his head-coach games
  professionalism, discipline        pre-snap (false start, delay of game, offside ...) and personal-conduct fouls per game
  preparation                        EPA per play over his offense's first 15 plays of a game
  conditioning                       fourth-quarter EPA margin per game
  motivation                         win rate right after a loss, and against the betting spread
  leadership                         win rate in one-score games, and playoff win rate
  respect                            career win rate, playoff wins per season, years as head coach
  overall                            career win rate, recent point margin, playoff win rate, and his offense and defense
Tendencies (play-calling block of the coach record, nfl2k5_roster_records.COACH_TENDENCY_GROUPS)
  run share and the situational run shares   observed rates (data/vip/coaches), cells shrunk toward his own run share
  run lane                                   observed run-lane shares
  formation shares                           participation data: shotgun / pistol / empty = class 1, under center with two or
                                             more backs = I form (class 3), one back = class 4, no back = class 5
  personnel shares                           participation data: backs, tight ends and receivers on the field mapped to the
                                             playbook's personnel categories (Ace = 1 RB 2 TE 2 WR, Kings = 1 RB 1 TE 3 WR ...)
  no huddle                                  observed rate turned into the game's per-snap roll (nfl2k5_vip.build_coach)
Everything else in the block (pass target zones, receiver roles, motion, defensive flag shares) has no public per-zone
source and is left as the record has it.

Usage
  python3 tools/nfl2k5_coach_2026_data.py build --nflverse DIR --pbp-dir DIR --participation-dir DIR [--out FILE]
  python3 tools/nfl2k5_coach_2026_data.py check                      # the committed file against the repository
  python3 tools/nfl2k5_coach_2026_data.py edits IN.json OUT.json     # add the entries to a roster-edits document
"""
from __future__ import annotations

import argparse
import collections
import csv
import difflib
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_coach_tendencies as ct  # noqa: E402

SCHEMA = "nfl2k5_coaches_2026/v1"
MODEL_VERSION = 1
DATA_PATH = ROOT / "data" / "nfl2k5_coaches_2026.json"
SOURCES_PATH = ROOT / "data" / "vip" / "coach_sources_2026.json"
VIP_DIR = ROOT / "data" / "vip" / "coaches"
SPEC_DIR = ROOT / "data" / "nfl2k5_teams_2026"
FIRST_SEASON, LAST_SEASON = 2020, 2025              # play-by-play evidence window (full seasons only)
GAMES_BEFORE = 2026                                  # career results: seasons before the one being played
BASE_FOOTBALL, BASE_CHARACTER, SPREAD = 78, 83, 9
RATING_MIN, RATING_MAX = 60, 99
N0 = dict(plays=600.0, dropbacks=400.0, rate=300.0, targets=150.0, games=17.0, carries=150.0)
SCRIPT_PLAYS = 15

FOOTBALL = ("overall", "offense", "rush_for", "pass_for", "defense", "pass_rush", "pass_coverage", "qb", "rb", "te", "wr",
            "ol", "dl", "lb", "db", "special_teams")
CHARACTER = ("professionalism", "preparation", "conditioning", "motivation", "leadership", "discipline", "respect")
RATING_ORDER = FOOTBALL + CHARACTER
PROCEDURAL = frozenset(x.casefold() for x in (
    "False Start", "Delay of Game", "Neutral Zone Infraction", "Encroachment", "Illegal Formation", "Illegal Shift",
    "Illegal Substitution", "Too Many Men on Field", "Illegal Motion", "Defensive Offside", "Offensive Offside",
    "Delay of Kickoff"))
PERSONAL = frozenset(x.casefold() for x in (
    "Unnecessary Roughness", "Roughing the Passer", "Roughing the Kicker", "Unsportsmanlike Conduct", "Taunting",
    "Face Mask", "Horse Collar Tackle", "Lowering the Head to Initiate Contact", "Personal Foul"))
SPECIAL_PLAYS = frozenset(("kickoff", "punt", "field_goal", "extra_point"))
GUN_FORMATIONS = frozenset(("SHOTGUN", "PISTOL", "EMPTY", "WILDCAT"))


class CoachDataError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CoachDataError(message)


# ------------------------------------------------------------------------------------------- small numeric helpers
def num(value: Any) -> float | None:
    return ct.number(value)


def flag(row: Mapping[str, Any], key: str) -> bool:
    return num(row.get(key)) == 1


def shrink(value: float | None, count: float, prior: float, league: float | None) -> float | None:
    """Move a coach's pooled mean toward the league mean by count / (count + prior)."""
    if value is None or league is None or count <= 0:
        return None
    return league + (value - league) * count / (count + prior)


def mean_of(total: float, count: float) -> float | None:
    return total / count if count else None


def standardize(values: Mapping[str, float | None], sign: float = 1.0) -> dict[str, float]:
    """z-score across the coaches that have a value (population sd); a coach without evidence is neutral (0)."""
    present = [v for v in values.values() if v is not None]
    if len(present) < 3:
        return {k: 0.0 for k in values}
    mean, sd = statistics.fmean(present), statistics.pstdev(present)
    return {k: (sign * (v - mean) / sd if v is not None and sd > 0 else 0.0) for k, v in values.items()}


def combine(parts: Iterable[tuple[float, Mapping[str, float]]]) -> dict[str, float]:
    """A weighted sum of z-scores, re-standardized so the composite keeps unit spread across the coaches."""
    parts = list(parts)
    keys = list(parts[0][1])
    raw = {k: sum(w * z[k] for w, z in parts) for k in keys}
    return standardize(raw)


def to_rating(z: float, centre: int) -> int:
    return max(RATING_MIN, min(RATING_MAX, int(round(centre + SPREAD * z))))


def largest_remainder(weights: list[float], total: int = 100) -> list[int]:
    """Whole numbers that add up to ``total`` in proportion to ``weights`` (largest remainder; ties go to the lower index)."""
    require(weights and all(w >= 0 for w in weights) and sum(weights) > 0, "no weights to share out")
    scale = total / sum(weights)
    exact = [w * scale for w in weights]
    floors = [int(math.floor(x)) for x in exact]
    for index in sorted(range(len(weights)), key=lambda i: (-(exact[i] - floors[i]), i))[: total - sum(floors)]:
        floors[index] += 1
    return floors


# ------------------------------------------------------------------------------------------- inputs
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_coaches() -> list[dict[str, Any]]:
    """The 32 coaches: provenance (roles, seasons) from the VIP sources, name from the team spec."""
    rows = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    out = []
    for row in rows:
        spec = json.loads((SPEC_DIR / f"{row['team']}.json").read_text(encoding="utf-8"))["roster"]
        require(spec["head_coach"] == row["coach"], f"{row['team']}: team spec says {spec['head_coach']!r}, VIP sources "
                                                     f"say {row['coach']!r}")
        out.append(dict(row, games_name=spec.get("head_coach_games_name") or spec["head_coach"]))
    require(len(out) == 32 and len({r["team"] for r in out}) == 32, "expected the 32 clubs once each")
    return out


def intervals(coach: Mapping[str, Any], key: str, roles: set[str] | None = None) -> list[dict[str, Any]]:
    out = []
    for iv in coach[key]:
        if roles is not None and iv["role"] not in roles:
            continue
        if iv["first_season"] > LAST_SEASON:
            continue
        out.append(dict(iv, last_season=min(iv["last_season"], LAST_SEASON), team=ct.team(iv["team"])))
    return out


class Index:
    """(team, season) -> [(coach, interval)] with the date cut-offs of mid-season changes."""

    def __init__(self, coaches: list[dict[str, Any]], key: str, roles: set[str] | None = None) -> None:
        self.by_key: dict[tuple[str, int], list[tuple[str, dict[str, Any]]]] = collections.defaultdict(list)
        for coach in coaches:
            for iv in intervals(coach, key, roles):
                for season in range(max(iv["first_season"], FIRST_SEASON), iv["last_season"] + 1):
                    self.by_key[iv["team"], season].append((coach["team"], iv))

    def who(self, team: str | None, season: int, date: str) -> list[str]:
        if not team:
            return []
        out = []
        for coach, iv in self.by_key.get((team, season), ()):
            if date and (date < iv.get("first_date", "0000") or date > iv.get("last_date", "9999")):
                continue
            out.append(coach)
        return out


# ------------------------------------------------------------------------------------------- results (games.csv)
def resolve_games_name(rows: list[dict[str, str]], name: str, team: str) -> str:
    """The spelling games.csv uses for this head coach: the given name when it appears, else the closest spelling among
    the head coaches of the club's latest games (difflib ratio 0.85, the rule nfl2k5_team_2026_roster.games_coach_name
    uses), else the given name (a coach with no head-coach games before 2026 finds nothing)."""
    names = {r[f"{side}_coach"] for r in rows for side in ("home", "away") if r.get(f"{side}_coach")}
    if name in names:
        return name
    near = difflib.get_close_matches(name, sorted(names), n=1, cutoff=0.85)
    return near[0] if near else name


def head_coach_games(rows: list[dict[str, str]], name: str) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if int(r["season"]) >= GAMES_BEFORE:
            continue
        for side, other in (("home", "away"), ("away", "home")):
            if r.get(f"{side}_coach") != name or r.get(f"{side}_score") in ("", None):
                continue
            mine, theirs = int(r[f"{side}_score"]), int(r[f"{other}_score"])
            spread = num(r.get("spread_line"))
            covered = None
            if spread is not None:
                edge = (mine - theirs) - (spread if side == "home" else -spread)     # spread_line > 0: home favoured by that many
                covered = None if edge == 0 else edge > 0
            out.append(dict(season=int(r["season"]), week=int(r["week"]), type=r["game_type"], mine=mine, theirs=theirs,
                            covered=covered, date=r["gameday"]))
    out.sort(key=lambda g: (g["season"], g["date"], g["week"]))
    return out


def results_block(games: list[dict[str, Any]]) -> dict[str, Any]:
    regular = [g for g in games if g["type"] == "REG"]
    post = [g for g in games if g["type"] != "REG"]
    wins = sum(g["mine"] > g["theirs"] for g in regular)
    ties = sum(g["mine"] == g["theirs"] for g in regular)
    seasons = sorted({g["season"] for g in regular})
    recent = [g for g in regular if g["season"] in seasons[-3:]]
    close = [g for g in regular if abs(g["mine"] - g["theirs"]) <= 8]
    bounce = []
    previous = None
    for g in regular:
        if previous is not None and previous["season"] == g["season"] and previous["mine"] < previous["theirs"]:
            bounce.append(g)
        previous = g
    ats = [g["covered"] for g in regular if g["covered"] is not None]
    post_wins = sum(g["mine"] > g["theirs"] for g in post)
    return dict(
        games=len(regular), seasons=len(seasons), win_rate=mean_of(wins + 0.5 * ties, len(regular)),
        recent_games=len(recent), recent_margin=mean_of(sum(g["mine"] - g["theirs"] for g in recent), len(recent)),
        close_games=len(close), close_win_rate=mean_of(sum(g["mine"] > g["theirs"] for g in close) + 0.5 * sum(g["mine"] == g["theirs"] for g in close), len(close)),
        bounce_games=len(bounce), bounce_win_rate=mean_of(sum(g["mine"] > g["theirs"] for g in bounce), len(bounce)),
        ats_games=len(ats), ats_rate=mean_of(sum(ats), len(ats)),
        playoff_games=len(post), playoff_wins=post_wins, playoff_win_rate=mean_of(post_wins, len(post)),
        super_bowls=sum(g["type"] == "SB" for g in post))


def league_results() -> dict[str, float]:
    """League-wide anchors for shrinkage: the average coach wins half, covers half and wins half after a loss."""
    return dict(win_rate=0.5, close_win_rate=0.5, bounce_win_rate=0.5, ats_rate=0.5, playoff_win_rate=0.5, recent_margin=0.0)


# ------------------------------------------------------------------------------------------- play by play
class Totals(collections.defaultdict):
    def __init__(self) -> None:
        super().__init__(float)


PBP_COLUMNS = ("game_id", "play_id", "season", "season_type", "game_date", "posteam", "defteam", "qtr", "down", "ydstogo",
               "play_type", "epa",
               "success", "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike", "pass_attempt", "rush_attempt", "sack",
               "qb_hit", "interception", "tackled_for_loss", "cpoe", "penalty", "penalty_team", "penalty_type",
               "rusher_player_id", "receiver_player_id", "special_teams_play")


def read_positions(nflverse: Path) -> dict[tuple[int, str], str]:
    out: dict[tuple[int, str], str] = {}
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        path = nflverse / f"roster_{season}.csv"
        require(path.is_file(), f"missing {path}")
        for row in csv.DictReader(path.open(encoding="utf-8", newline="")):
            if row.get("gsis_id") and row.get("position"):
                out[season, row["gsis_id"]] = row["position"]
    return out


def long_yardage(row: Mapping[str, Any]) -> bool:
    """A long-yardage down: third or fourth and 6 or more, second and 9 or more (where the game's personnel window moves to
    the light groups, codes 8 to 10)."""
    down, to_go = num(row.get("down")), num(row.get("ydstogo"))
    return down is not None and to_go is not None and ((down >= 3 and to_go >= 6) or (down == 2 and to_go >= 9))


def collect_pbp(rows: Iterable[Mapping[str, Any]], coaches: list[dict[str, Any]], positions: Mapping[tuple[int, str], str],
                state: dict[str, Any] | None = None) -> dict[str, Any]:
    """One pass over play-by-play rows (any order).  Returns the running totals; call again with ``state`` to add files."""
    if state is None:
        state = dict(offense=Index(coaches, "offense_history"), defense=Index(coaches, "defense_history"),
                     head=Index(coaches, "offense_history", {"HC"}),
                     off=collections.defaultdict(Totals), dfn=collections.defaultdict(Totals),
                     hc=collections.defaultdict(Totals), league=Totals(), script=collections.defaultdict(list),
                     hc_games=collections.defaultdict(set), plays={}, league_plays={})
    off, dfn, hc, league = state["off"], state["dfn"], state["hc"], state["league"]
    for row in rows:
        season = num(row.get("season"))
        if season is None or not FIRST_SEASON <= season <= LAST_SEASON or row.get("season_type") != "REG":
            continue
        season = int(season)
        date = str(row.get("game_date", ""))[:10]
        pos = ct.team(row["posteam"]) if row.get("posteam") else None
        opp = ct.team(row["defteam"]) if row.get("defteam") else None
        ptype = row.get("play_type")
        epa = num(row.get("epa"))
        scrimmage = (ptype in ("pass", "run") and epa is not None and not flag(row, "qb_kneel") and not flag(row, "qb_spike"))
        dropback = scrimmage and flag(row, "qb_dropback")
        attempt = scrimmage and flag(row, "pass_attempt") and not flag(row, "sack")
        designed = scrimmage and flag(row, "rush_attempt") and not flag(row, "qb_dropback")
        success = num(row.get("success"))
        special = ptype in SPECIAL_PLAYS and epa is not None
        if scrimmage:
            league["plays"] += 1
            league["epa"] += epa
            state["league_plays"][row["game_id"], int(num(row.get("play_id")) or 0)] = (
                "pass" if dropback or attempt else "run", long_yardage(row))
            if dropback:
                league["dropbacks"] += 1
                league["dropback_epa"] += epa
                league["sacks"] += flag(row, "sack")
                league["hits"] += flag(row, "qb_hit")
            if attempt:
                league["attempts"] += 1
                league["attempt_epa"] += epa
                league["ints"] += flag(row, "interception")
                cpoe = num(row.get("cpoe"))
                if cpoe is not None:
                    league["cpoe_n"] += 1
                    league["cpoe"] += cpoe
            if designed:
                league["rushes"] += 1
                league["rush_epa"] += epa
                league["rush_success"] += success or 0
                league["stuffs"] += flag(row, "tackled_for_loss")
        for coach in state["offense"].who(pos, season, date):
            t = off[coach]
            if scrimmage:
                t["plays"] += 1
                t["epa"] += epa
                if dropback:
                    t["dropbacks"] += 1
                    t["dropback_epa"] += epa
                    t["sacks"] += flag(row, "sack")
                    t["hits"] += flag(row, "qb_hit")
                if attempt:
                    t["attempts"] += 1
                    t["attempt_epa"] += epa
                    cpoe = num(row.get("cpoe"))
                    if cpoe is not None:
                        t["cpoe_n"] += 1
                        t["cpoe"] += cpoe
                    target = positions.get((season, str(row.get("receiver_player_id"))))
                    if target in ("WR", "TE"):
                        kind = target.lower()
                        t[kind + "_targets"] += 1
                        t[kind + "_epa"] += epa
                if designed:
                    t["rushes"] += 1
                    t["rush_epa"] += epa
                    t["rush_success"] += success or 0
                    if positions.get((season, str(row.get("rusher_player_id")))) in ("RB", "FB"):
                        t["rb_carries"] += 1
                        t["rb_epa"] += epa
                key = (row["game_id"], int(num(row.get("play_id")) or 0))
                state["plays"][key] = state["plays"].get(key, ()) + (
                    (coach, "pass" if dropback or attempt else "run", long_yardage(row)),)
        for coach in state["defense"].who(opp, season, date):
            t = dfn[coach]
            if scrimmage:
                t["plays"] += 1
                t["epa"] += epa
                if dropback:
                    t["dropbacks"] += 1
                    t["dropback_epa"] += epa
                    t["sacks"] += flag(row, "sack")
                    t["hits"] += flag(row, "qb_hit")
                if attempt:
                    t["attempts"] += 1
                    t["attempt_epa"] += epa
                    t["ints"] += flag(row, "interception")
                if designed:
                    t["rushes"] += 1
                    t["rush_epa"] += epa
                    t["stuffs"] += flag(row, "tackled_for_loss")
        # head-coach games: both sides of the ball, special teams, penalties, the opening script, the fourth quarter
        for side_team, other, attacking in ((pos, opp, True), (opp, pos, False)):
            for coach in state["head"].who(side_team, season, date):
                state["hc_games"][coach].add(row["game_id"])
                t = hc[coach]
                if special:
                    t["st_epa"] += epa if attacking else -epa
                if scrimmage and num(row.get("qtr")) == 4:
                    t["q4_epa"] += epa if attacking else -epa
                if scrimmage and attacking:
                    state["script"][coach, row["game_id"]].append((num(row.get("play_id")) or 0, epa))
                if num(row.get("penalty")) == 1 and row.get("penalty_type") and ct.team(row.get("penalty_team") or "") == side_team:
                    kind = str(row["penalty_type"]).casefold()
                    t["pen_procedural"] += kind in PROCEDURAL
                    t["pen_personal"] += kind in PERSONAL
    return state


#: personnel (RB, TE, WR on the field) -> the playbook category code the game's personnel weights are indexed by (every book
#: keeps one category per code with exactly this mix: 0 Jacks, 1 Jumbo, 2 Jokers, 3 Ace, 4 Pro, 5 Pistol, 6 Kings, 7 Queens,
#: 9 Flush, 10 5 Wide; read from the categories of the released books with nfl2k5_play_library.category_positions)
PERSONNEL_CODES = {(2, 3, 0): 0, (1, 3, 1): 1, (2, 2, 1): 2, (1, 2, 2): 3, (2, 1, 2): 4, (1, 1, 3): 6, (2, 0, 3): 7,
                   (1, 0, 4): 9, (0, 0, 5): 10, (0, 1, 4): 10, (0, 2, 3): 10}


def personnel_code(personnel: str | None, formation: str | None = None, long: bool = False) -> int | None:
    """The game's personnel category code (0..10) of an ``offense_personnel`` string such as "1 RB, 1 TE, 3 WR".

    The game picks a personnel group by weights inside a window of +-2 codes around a situation centre that runs from
    heavy (short yardage, 0 to 2) to light (long yardage, 8 to 10), and the SOFTDRINK books keep their modern 11 personnel
    long-yardage formations in the code 9 group ("Kings Long").  So 11 personnel on a long-yardage down counts for code 9,
    on any other down for code 6 (Kings), or 5 for a pistol formation."""
    if not personnel:
        return None
    have = {"RB": 0, "TE": 0, "WR": 0}
    for part in str(personnel).split(","):
        words = part.split()
        if len(words) == 2 and words[1] in have:
            have[words[1]] += int(words[0])
    rb, te, wr = have["RB"], have["TE"], have["WR"]
    if rb + te + wr < 4:
        return None
    if (rb, te, wr) == (1, 1, 3):
        return 9 if long else 5 if str(formation or "").upper() == "PISTOL" else 6
    code = PERSONNEL_CODES.get((rb, te, wr))
    if code is not None:
        return code
    if wr >= 4:
        return 9 if rb >= 1 else 10
    if wr == 3:
        return 7 if rb >= 2 else 6
    if wr == 2:
        return 3 if te >= 2 else 4
    return 2 if rb >= 2 else 1


def formation_class(formation: str | None, personnel: str | None) -> int | None:
    """The game's formation class (1 gun ... 5 empty, nfl2k5 table 0xAC9EE0) of a participation row."""
    if not formation:
        return None
    form = formation.upper().replace(" ", "_")
    if form in GUN_FORMATIONS:
        return 1
    backs = None
    for part in str(personnel or "").split(","):
        words = part.split()
        if len(words) == 2 and words[1] == "RB":
            backs = int(words[0])
    if backs is None:
        backs = 0 if form == "EMPTY" else 1 if form == "SINGLEBACK" else 2 if form in ("I_FORM", "JUMBO") else None
    if backs is None:
        return None
    return 3 if backs >= 2 else 4 if backs == 1 else 5


def collect_formations(rows: Iterable[Mapping[str, Any]], state: dict[str, Any],
                       counts: dict[str, dict[str, collections.Counter]] | None = None) -> dict[str, dict[str, collections.Counter]]:
    """Participation rows joined to the offense plays the pbp pass remembered (by game_id, play_id)."""
    if counts is None:
        counts = collections.defaultdict(new_counts)
    for row in rows:
        play = num(row.get("play_id"))
        owners = state["plays"].get((row.get("nflverse_game_id"), int(play))) if play is not None else None
        if not owners:
            continue
        cls = formation_class(row.get("offense_formation"), row.get("offense_personnel"))
        for coach, kind, long in owners:
            key = "pass_" if kind == "pass" else "run"
            if cls is not None:
                counts[coach][key][cls] += 1
            code = personnel_code(row.get("offense_personnel"), row.get("offense_formation"), long)
            if code is not None:
                counts[coach]["personnel_" + key.rstrip("_")][code] += 1
    return counts


def new_counts() -> dict[str, collections.Counter]:
    return dict(run=collections.Counter(), pass_=collections.Counter(),
                personnel_run=collections.Counter(), personnel_pass=collections.Counter())


def collect_league_formations(rows: Iterable[Mapping[str, Any]], state: dict[str, Any],
                              counts: dict[str, collections.Counter] | None = None) -> dict[str, collections.Counter]:
    """The same join for every offense play in the league: the baseline a coach without offense evidence starts from."""
    if counts is None:
        counts = new_counts()
    for row in rows:
        play = num(row.get("play_id"))
        found = state["league_plays"].get((row.get("nflverse_game_id"), int(play))) if play is not None else None
        if not found:
            continue
        kind, long = found
        key = "pass_" if kind == "pass" else "run"
        cls = formation_class(row.get("offense_formation"), row.get("offense_personnel"))
        code = personnel_code(row.get("offense_personnel"), row.get("offense_formation"), long)
        if cls is not None:
            counts[key][cls] += 1
        if code is not None:
            counts["personnel_" + key.rstrip("_")][code] += 1
    return counts


# ------------------------------------------------------------------------------------------- the ratings model
def unit_metrics(state: Mapping[str, Any], coaches: list[dict[str, Any]], results: Mapping[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Shrunk raw metrics per coach (None = no evidence), the inputs of the z-scores."""
    lg = state["league"]
    L = dict(
        epa=mean_of(lg["epa"], lg["plays"]), dropback_epa=mean_of(lg["dropback_epa"], lg["dropbacks"]),
        attempt_epa=mean_of(lg["attempt_epa"], lg["attempts"]), cpoe=mean_of(lg["cpoe"], lg["cpoe_n"]),
        rush_epa=mean_of(lg["rush_epa"], lg["rushes"]), rush_success=mean_of(lg["rush_success"], lg["rushes"]),
        sack_rate=mean_of(lg["sacks"], lg["dropbacks"]), hit_rate=mean_of(lg["hits"], lg["dropbacks"]),
        stuff_rate=mean_of(lg["stuffs"], lg["rushes"]), int_rate=mean_of(lg["ints"], lg["attempts"]))
    out: dict[str, dict[str, Any]] = {}
    for coach in coaches:
        key = coach["team"]
        o, d, h = state["off"].get(key, Totals()), state["dfn"].get(key, Totals()), state["hc"].get(key, Totals())
        games = len(state["hc_games"].get(key, ()))
        m: dict[str, Any] = {}

        def add(name, total, count, prior, league, sample=None):
            m[name] = shrink(mean_of(total, count), count, prior, league)
            m[name + "_n"] = int(count if sample is None else sample)

        add("off_epa", o["epa"], o["plays"], N0["plays"], L["epa"])
        add("pass_epa", o["dropback_epa"], o["dropbacks"], N0["dropbacks"], L["dropback_epa"])
        add("rush_epa", o["rush_epa"], o["rushes"], N0["plays"] / 2, L["rush_epa"])
        add("rush_success", o["rush_success"], o["rushes"], N0["plays"] / 2, L["rush_success"])
        add("qb_epa", o["attempt_epa"], o["attempts"], N0["dropbacks"], L["attempt_epa"])
        add("qb_cpoe", o["cpoe"], o["cpoe_n"], N0["dropbacks"], L["cpoe"])
        add("off_sack_rate", o["sacks"], o["dropbacks"], N0["rate"], L["sack_rate"])
        add("off_hit_rate", o["hits"], o["dropbacks"], N0["rate"], L["hit_rate"])
        add("def_epa", d["epa"], d["plays"], N0["plays"], L["epa"])
        add("def_attempt_epa", d["attempt_epa"], d["attempts"], N0["dropbacks"], L["attempt_epa"])
        add("def_rush_epa", d["rush_epa"], d["rushes"], N0["plays"] / 2, L["rush_epa"])
        add("def_sack_rate", d["sacks"], d["dropbacks"], N0["rate"], L["sack_rate"])
        add("def_hit_rate", d["hits"], d["dropbacks"], N0["rate"], L["hit_rate"])
        add("def_stuff_rate", d["stuffs"], d["rushes"], N0["rate"], L["stuff_rate"])
        add("def_int_rate", d["ints"], d["attempts"], N0["rate"], L["int_rate"])
        for kind, count in (("wr", o["wr_targets"]), ("te", o["te_targets"]), ("rb", o["rb_carries"])):
            m[kind + "_raw"] = mean_of(o[kind + "_epa"], count)
            m[kind + "_n"] = int(count)
        m["games"] = games
        for name, total in (("st", h["st_epa"]), ("q4", h["q4_epa"])):      # zero-sum across the league: anchor 0
            m[name + "_per_game"] = shrink(mean_of(total, games), games, N0["games"], 0.0)
        m["proc_raw"], m["personal_raw"] = mean_of(h["pen_procedural"], games), mean_of(h["pen_personal"], games)
        script = [sorted(p)[:SCRIPT_PLAYS] for (c, _g), p in state["script"].items() if c == key]
        plays = sum(len(p) for p in script)
        m["script_epa"] = shrink(mean_of(sum(e for p in script for _i, e in p), plays), plays, N0["plays"], L["epa"])
        m["script_n"] = plays
        out[key] = m
    # fouls per game and receiver EPA have no league-wide stream anchor: anchor on the 32 coaches' own pooled mean
    for raw, name in (("proc_raw", "proc_per_game"), ("personal_raw", "personal_per_game")):
        weight = sum(m["games"] for m in out.values() if m[raw] is not None)
        anchor = sum(m[raw] * m["games"] for m in out.values() if m[raw] is not None) / weight if weight else None
        for m in out.values():
            m[name] = shrink(m[raw], m["games"], N0["games"], anchor)
    for kind, prior in (("wr", N0["targets"]), ("te", N0["targets"]), ("rb", N0["carries"])):
        pooled_n = sum(m[kind + "_n"] for m in out.values())
        pooled = sum((m[kind + "_raw"] or 0.0) * m[kind + "_n"] for m in out.values()) / pooled_n if pooled_n else None
        for m in out.values():
            m[kind + "_epa"] = shrink(m[kind + "_raw"], m[kind + "_n"], prior, pooled)
    for key, m in out.items():
        r = results[key]
        anchors = league_results()
        m["win_rate"] = shrink(r["win_rate"], r["games"], N0["games"], anchors["win_rate"])
        m["recent_margin"] = shrink(r["recent_margin"], r["recent_games"], N0["games"], anchors["recent_margin"])
        m["close_win_rate"] = shrink(r["close_win_rate"], r["close_games"], N0["games"], anchors["close_win_rate"])
        m["bounce_win_rate"] = shrink(r["bounce_win_rate"], r["bounce_games"], N0["games"], anchors["bounce_win_rate"])
        m["ats_rate"] = shrink(r["ats_rate"], r["ats_games"], N0["games"] * 2, anchors["ats_rate"])
        m["playoff_win_rate"] = shrink(r["playoff_win_rate"], r["playoff_games"], 6.0, anchors["playoff_win_rate"])
        m["playoff_wins_per_season"] = mean_of(r["playoff_wins"], r["seasons"]) if r["seasons"] else None
        m["tenure"] = float(r["seasons"]) if r["seasons"] else None
    return out


def ratings_from_metrics(metrics: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, float]]]:
    keys = list(metrics)

    def z(name: str, sign: float = 1.0) -> dict[str, float]:
        return standardize({k: metrics[k].get(name) for k in keys}, sign)

    offense, defense = z("off_epa"), z("def_epa", -1)
    composite: dict[str, dict[str, float]] = {
        "offense": offense, "pass_for": z("pass_epa"), "rush_for": z("rush_epa"),
        "defense": defense, "pass_coverage": z("def_attempt_epa", -1),
        "pass_rush": combine([(0.6, z("def_sack_rate")), (0.4, z("def_hit_rate"))]),
        "qb": combine([(0.5, z("qb_epa")), (0.5, z("qb_cpoe"))]),
        "rb": z("rb_epa"), "te": z("te_epa"), "wr": z("wr_epa"),
        "ol": combine([(0.4, z("off_sack_rate", -1)), (0.3, z("off_hit_rate", -1)), (0.3, z("rush_success"))]),
        "dl": combine([(0.4, z("def_sack_rate")), (0.3, z("def_hit_rate")), (0.3, z("def_rush_epa", -1))]),
        "lb": combine([(0.5, z("def_rush_epa", -1)), (0.5, z("def_stuff_rate"))]),
        "db": combine([(0.7, z("def_attempt_epa", -1)), (0.3, z("def_int_rate"))]),
        "special_teams": z("st_per_game"),
        "professionalism": z("proc_per_game", -1), "discipline": z("personal_per_game", -1),
        "preparation": z("script_epa"), "conditioning": z("q4_per_game"),
        "motivation": combine([(0.5, z("bounce_win_rate")), (0.5, z("ats_rate"))]),
        "leadership": combine([(0.5, z("close_win_rate")), (0.5, z("playoff_win_rate"))]),
        "respect": combine([(0.4, z("win_rate")), (0.3, z("playoff_wins_per_season")), (0.3, z("tenure"))]),
    }
    composite["overall"] = combine([(0.35, z("win_rate")), (0.25, z("recent_margin")), (0.20, z("playoff_win_rate")),
                                    (0.10, offense), (0.10, defense)])
    ratings = {k: {name: to_rating(composite[name][k], BASE_FOOTBALL if name in FOOTBALL else BASE_CHARACTER)
                   for name in RATING_ORDER} for k in keys}
    zs = {k: {name: round(composite[name][k], 3) for name in RATING_ORDER} for k in keys}
    return ratings, zs


# ------------------------------------------------------------------------------------------- tendencies
PERSONNEL_FLOOR = 1                          # every reachable personnel code keeps this much weight, so no window of +-2 is empty
PERSONNEL_NEVER = (8,)                       # code 8 has no category in the released books: weight 0 (a pick of it finds nothing)


def floor_personnel(shares: list[int]) -> list[int]:
    """Personnel shares with a floor on every code a book has a group for (taken from the largest codes), code 8 at 0."""
    out = list(shares)
    for code in PERSONNEL_NEVER:
        out[code] = 0
    for code in range(len(out)):
        while code not in PERSONNEL_NEVER and out[code] < PERSONNEL_FLOOR:
            donor = max(range(len(out)), key=lambda i: out[i])
            out[donor] -= 1
            out[code] += 1
    if sum(out) != 100:                                   # code 8 held weight in the data: give it to the largest
        out[max(range(len(out)), key=lambda i: out[i])] += 100 - sum(out)
    return out


FORMATION_MIN_CALLS = 200                    # classified calls needed before a coach's own formation shares are used
CELL_PRIOR_CALLS = 20.0                      # a situational run cell counts this many calls of the coach's own overall share
LANE_PRIOR_RUNS = 40.0                       # a coach's lane shares count this many runs of the league lane shares


def run_percent(rate: Mapping[str, Any], fallback: float, prior: float = CELL_PRIOR_CALLS) -> int:
    """A cell's run percent, shrunk toward the coach's own overall run share by ``prior`` calls."""
    den, run = rate["denominator"], rate["numerator"]
    return int(round(100 * (run + prior * fallback) / (den + prior)))


LANES = ("left_outside", "left_inside", "middle", "right_inside", "right_outside")


def league_lane_shares(vips: Iterable[Mapping[str, Any]]) -> list[float]:
    """Run-lane shares of the 32 coaches pooled by their known runs (the baseline a short sample is pulled toward)."""
    totals = [0.0] * 5
    for vip in vips:
        overall = vip["overall"]
        known = overall["run_lane"]["left_inside"]["denominator"]
        for i, name in enumerate(LANES):
            totals[i] += overall["run_lane"][name]["rate"] * known if overall["run_lane"][name]["rate"] is not None else 0.0
    return [t / sum(totals) for t in totals]


def tendencies_for(vip: Mapping[str, Any], formations: Mapping[str, collections.Counter] | None,
                   league_formations: Mapping[str, collections.Counter] | None = None,
                   league_lanes: list[float] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The tendency groups for one coach and the basis that explains them."""
    overall, stats = vip["overall"], vip["native_statistics"]
    run_share = 1.0 - overall["pass_rate"]["rate"]
    basis: dict[str, Any] = dict(calls=overall["calls"], cell_prior_calls=CELL_PRIOR_CALLS)
    out: dict[str, Any] = {"run_share": int(round(100 * run_share))}
    out["run_by_score"] = [run_percent(r, run_share) for r in stats["score"]]
    out["run_redzone"] = run_percent(stats["redzone"], run_share)
    out["run_by_down_distance"] = [run_percent(r, run_share) for r in stats["down_distance"]]
    lanes = [overall["run_lane"][name]["rate"] for name in LANES]
    known = overall["run_lane"]["left_inside"]["denominator"]
    if all(x is not None for x in lanes) and known:
        prior = league_lanes or [0.2] * 5
        out["run_lane"] = largest_remainder([(x * known + LANE_PRIOR_RUNS * p) for x, p in zip(lanes, prior)])
        basis["run_lane_known_runs"] = known
    projection = vip.get("native_decision_projections", {}).get("no_huddle", {}).get("rate")
    if projection is not None:
        out["no_huddle"] = int(round(100 * projection / (4 - 3 * projection)))        # nfl2k5_vip.build_coach: roll r = p / (4 - 3p)
    for name, key, codes in (("formation_run", "run", (1, 2, 3, 4, 5)), ("formation_pass", "pass_", (1, 2, 3, 4, 5)),
                             ("personnel_run", "personnel_run", tuple(range(11))),
                             ("personnel_pass", "personnel_pass", tuple(range(11)))):
        own = formations.get(key, collections.Counter()) if formations else collections.Counter()
        base = league_formations.get(key, collections.Counter()) if league_formations else collections.Counter()
        source, counts = ("coach", own) if sum(own.values()) >= FORMATION_MIN_CALLS else ("league", base)
        if sum(counts.values()) >= FORMATION_MIN_CALLS:
            shares = largest_remainder([counts[c] for c in codes])
            out[name] = floor_personnel(shares) if key.startswith("personnel") else shares
            basis[name] = dict(source=source, calls=sum(counts.values()), classes={str(c): counts[c] for c in codes})
    return out, basis


# ------------------------------------------------------------------------------------------- build / check / edits
def build(args: argparse.Namespace) -> int:
    coaches = load_coaches()
    nflverse = Path(args.nflverse)
    games_csv = nflverse / "games.csv"
    rows = list(csv.DictReader(games_csv.open(encoding="utf-8", newline="")))
    positions = read_positions(nflverse)
    results, games_names = {}, {}
    for coach in coaches:
        name = resolve_games_name(rows, coach["games_name"], coach["team"])
        games_names[coach["team"]] = name
        results[coach["team"]] = results_block(head_coach_games(rows, name))
    state = None
    pbp_sources = []
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        path = Path(args.pbp_dir) / f"pbp_{season}.parquet"
        state = collect_pbp(ct.read_rows(path, PBP_COLUMNS), coaches, positions, state)
        pbp_sources.append(dict(file=path.name, sha256=sha256_file(path)))
    counts, league_counts = None, None
    part_sources = []
    for season in range(2022, LAST_SEASON + 1):
        path = Path(args.participation_dir) / f"pbp_participation_{season}.parquet"
        columns = ("nflverse_game_id", "play_id", "offense_formation", "offense_personnel")
        counts = collect_formations(ct.read_rows(path, columns), state, counts)
        league_counts = collect_league_formations(ct.read_rows(path, columns), state, league_counts)
        part_sources.append(dict(file=path.name, sha256=sha256_file(path)))
    metrics = unit_metrics(state, coaches, results)
    ratings, zs = ratings_from_metrics(metrics)
    vips = {c["team"]: json.loads((VIP_DIR / f"{c['team']}.json").read_text(encoding="utf-8")) for c in coaches}
    lanes = league_lane_shares(vips.values())
    entries = {}
    for coach in coaches:
        key = coach["team"]
        vip = vips[key]
        require(vip["coach"] == coach["coach"], f"{key}: VIP tendencies are for {vip['coach']!r}")
        tendencies, tendency_basis = tendencies_for(vip, counts.get(key) if counts else None, league_counts, lanes)
        entries[key] = dict(
            coach=coach["coach"], ratings=ratings[key], tendencies=tendencies, announcer="generic",
            basis=dict(games_csv_name=games_names[key], results=results[key],
                       metrics={k: (round(v, 5) if isinstance(v, float) else v) for k, v in metrics[key].items()},
                       z=zs[key], tendencies=tendency_basis))
    document = dict(
        schema=SCHEMA, model_version=MODEL_VERSION, builder="tools/nfl2k5_coach_2026_data.py",
        license="Derived from nflverse data (CC-BY-4.0); formulas and thresholds in the builder",
        description=__doc__.split("Usage")[0].strip(),
        window=dict(play_by_play=[FIRST_SEASON, LAST_SEASON], results_before=GAMES_BEFORE),
        scale=dict(football_centre=BASE_FOOTBALL, character_centre=BASE_CHARACTER, points_per_sd=SPREAD,
                   range=[RATING_MIN, RATING_MAX], shrinkage_prior=N0),
        inputs=dict(games_csv=dict(file="games.csv", sha256=sha256_file(games_csv)),
                    rosters=[dict(file=f"roster_{s}.csv", sha256=sha256_file(nflverse / f"roster_{s}.csv"))
                             for s in range(FIRST_SEASON, LAST_SEASON + 1)],
                    play_by_play=pbp_sources, participation=part_sources,
                    coach_sources=dict(file="data/vip/coach_sources_2026.json", sha256=sha256_file(SOURCES_PATH)),
                    vip_tendencies={p.name: sha256_file(p) for p in sorted(VIP_DIR.glob("*.json"))}),
        coaches=entries)
    out = Path(args.out)
    out.write_text(json.dumps(document, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out} ({out.stat().st_size:,} bytes), {len(entries)} coaches")
    return 0


def load_data(path: Path = DATA_PATH) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, f"{path}: schema {document.get('schema')!r}, expected {SCHEMA}")
    return document


def record_entry(document: Mapping[str, Any], club: str, full_name: str | None = None) -> dict[str, Any] | None:
    """The roster-edits ``coaches`` fields for one club: ratings, tendencies, announcer.  None when the file has no entry
    for the club or the head coach's name differs (a different coach must never inherit another man's ratings)."""
    entry = document["coaches"].get(club)
    if entry is None or (full_name is not None and entry["coach"] != full_name):
        return None
    return dict(ratings=dict(entry["ratings"]), tendencies=json.loads(json.dumps(entry["tendencies"])),
                announcer=entry["announcer"])


def validate(document: Mapping[str, Any]) -> list[str]:
    """Problems with a data file, as plain lines (empty when sound).  Checks the writer's own rules on every entry."""
    from mod_editor.core import nfl2k5_roster_records as rr
    problems = []
    sources = {r["team"]: r for r in json.loads(SOURCES_PATH.read_text(encoding="utf-8"))}
    entries = document["coaches"]
    if set(entries) != set(sources):
        problems.append(f"clubs differ from the VIP sources: {sorted(set(entries) ^ set(sources))}")
    for club, entry in entries.items():
        if club in sources and entry["coach"] != sources[club]["coach"]:
            problems.append(f"{club}: coach {entry['coach']!r} is not {sources[club]['coach']!r}")
        try:
            rr.plan_coach_record(dict(entry, team=club))
        except rr.RosterRecordError as exc:
            problems.append(f"{club}: {exc}")
        if set(entry["ratings"]) != set(rr.COACH_RATING_NAMES):
            problems.append(f"{club}: ratings are not exactly the 23 names")
        for name in ("ratings",):
            if not entry["basis"].get("metrics"):
                problems.append(f"{club}: no basis recorded for {name}")
    return problems


def check(args: argparse.Namespace) -> int:
    document = load_data(Path(args.data))
    problems = validate(document)
    for line in problems:
        print("PROBLEM:", line)
    print(f"{len(document['coaches'])} coaches, {len(problems)} problem(s)")
    return 1 if problems else 0


def add_to_edits(source: Path, target: Path, data: Path = DATA_PATH) -> dict[str, Any]:
    """Copy a roster-edits document and add every club's record fields (ratings, tendencies, announcer) to its existing
    ``coaches`` entry.  Entries are matched by club (the retail codes ARZ, SD, OAK and STL count as ARI, LAC, LV and
    LAR) and then by the coach's name, so a club whose entry names another head coach is left alone and reported; a club
    with no entry is reported as missing (an entry is never invented here: the document's own abbreviation for the club
    is what the writer resolves).  Names, biographies and career numbers in the entries are not touched."""
    document = json.loads(Path(source).read_text(encoding="utf-8"))
    data_doc = load_data(data)
    entries = {ct.team(str(e.get("team", ""))): e for e in document.get("coaches") or [] if e.get("team")}
    written, missing, mismatched = [], [], []
    for club, row in data_doc["coaches"].items():
        entry = entries.get(club)
        if entry is None:
            missing.append(club)
            continue
        named = str(entry.get("full_name") or " ".join(str(entry.get(k, "")) for k in ("first", "last"))).strip()
        last = str(entry.get("last", "")).strip()
        if named and named != row["coach"] and not (last and row["coach"].endswith(last)):
            mismatched.append(f"{club}: the document's coach {named!r} is not {row['coach']!r}")
            continue
        entry.update(record_entry(data_doc, club))
        written.append(club)
    Path(target).write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    return dict(written=len(written), missing=missing, mismatched=mismatched)


def edits(args: argparse.Namespace) -> int:
    result = add_to_edits(Path(args.source), Path(args.target), Path(args.data))
    print(json.dumps(result, indent=1))
    return 1 if result["missing"] or result["mismatched"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="derive the data file from the public data")
    b.add_argument("--nflverse", required=True, help="folder with games.csv and roster_2020..2025.csv")
    b.add_argument("--pbp-dir", required=True, help="folder with pbp_2020..2025.parquet")
    b.add_argument("--participation-dir", required=True, help="folder with pbp_participation_2022..2025.parquet")
    b.add_argument("--out", default=str(DATA_PATH))
    b.set_defaults(func=build)
    c = sub.add_parser("check", help="validate the committed data file")
    c.add_argument("--data", default=str(DATA_PATH))
    c.set_defaults(func=check)
    e = sub.add_parser("edits", help="add the entries to a roster-edits document")
    e.add_argument("source")
    e.add_argument("target")
    e.add_argument("--data", default=str(DATA_PATH))
    e.set_defaults(func=edits)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CoachDataError, RuntimeError, OSError) as exc:      # RuntimeError: parquet without pyarrow; OSError: a missing input
        print(f"coach data refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
