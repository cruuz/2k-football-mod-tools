#!/usr/bin/env python3
"""Build data/nfl2k5_owners_2026.json and data/nfl2k5_coach_pool_2026.json (job c5-owners, beta 80); development use only.

EXPERIMENTAL / UNWITNESSED. The coaching carousel needs owners whose patience is a measured fact, not a guess. This tool
derives it, and only from pinned inputs (each is verified by SHA-256 before anything is parsed):

* nflverse ``games.csv`` (nfldata commit e28cf00d..., 2,185,207 bytes): the head coach of every club's games, 1999-2025.
  The file has no interim coaches for 2024 and 2025 and its 2026 coach columns are stale for some clubs, so only the
  OPENING-DAY coach of each season 1999-2025 and the season record are used from it.
* the repo's sourced 2026 head coaches (``data/nfl2k5_teams_2026/*.json`` and ``data/vip/coach_sources_2026.json``) and its
  sourced 2026 defensive coordinators (``data/vip/defense_identity_2026.json``).
* Wikipedia "List of current NFL franchise owners" at a fixed revision: principal owner, since when, and the note that
  tells a family succession from an outside purchase (a purchase starts a new owner era; a family succession does not).
* Wikipedia "2026 NFL season" at a fixed revision: the table of the 2026 offseason's head coach changes (reason, date); the
  tool checks that the page says what ``offseason_2026.json`` says.
* ``tools/nfl2k5_coach_owners/url_checks.json``: every other URL the data cites, fetched on a stated day (``--check-urls``).

Method (all in the output's ``model.fit``): the unit is one offseason decision, "was the coach who opened season s
replaced by the start of s+1", 861 decisions (27 offseasons x 32 clubs, Houston from 2002), 191 changes. A logistic
regression on the season's win percentage and the coach's seasons with the club (first, second, third or later) gives
the league hazard; each club's owner multiplier is the observed/expected count of changes in the owner's era shrunk
toward 1 with a gamma prior whose shape is the data's own (maximum likelihood; where the data show no spread between
clubs, the smallest shape the 95% profile-likelihood test cannot reject, i.e. the most owner spread the data allow).

usage: nfl2k5_coach_owners_build.py [--games PATH] [--owners-wikitext PATH] [--season-wikitext PATH] [--cache DIR]
                                    [--fetch] [--check-urls] [--check] [--no-pool]
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_coach_owners as co  # noqa: E402
from mod_editor.core import nfl2k5_team_history as th  # noqa: E402

OUT_OWNERS = ROOT / "data" / "nfl2k5_owners_2026.json"
OUT_POOL = ROOT / "data" / "nfl2k5_coach_pool_2026.json"
INPUTS = Path(__file__).resolve().parent / "nfl2k5_coach_owners"
DEFAULT_CACHE = Path(os.environ.get("NFL2K5_COACH_OWNERS_CACHE", Path.home() / ".cache" / "nfl2k5-coach-owners"))

NFLDATA_COMMIT = "e28cf00d4fdffa262603191a0b339901d4a7efd0"
GAMES_SHA256 = "a5181ec4974309828d1d58e6f881eb1d106ee85c15c038a51b6bdca7b7ee6cf5"
GAMES_BYTES = 2185207
GAMES_URL = f"https://raw.githubusercontent.com/nflverse/nfldata/{NFLDATA_COMMIT}/data/games.csv"
WIKI = "https://en.wikipedia.org/w/index.php?title={title}&oldid={revision}"
OWNERS_TITLE, OWNERS_REVISION = "List of current NFL franchise owners", 1381227405
OWNERS_SHA256 = "2c10af89b73ec3c02b33ea445baa45b11b6bcae22af925078d616486a31829da"
SEASON_TITLE, SEASON_REVISION = "2026 NFL season", 1383458077
SEASON_SHA256 = "80d2b63331403fa520d1e56cf7e932c8febc5e305a7a2423b1b331f0872d453d"
ALIAS = {"OAK": "LV", "SD": "LAC", "STL": "LAR", "LA": "LAR"}      # nflverse era codes -> the 2026 club code
DC_KEY_TO_CLUB = {"ARZ": "ARI", "OAK": "LV", "SD": "LAC", "STL": "LAR"}     # data/vip/defense_identity_2026.json keys
FIRST, LAST = co.SEASON_FIRST, co.SEASON_LAST
NEW_COACH_YEAR = LAST + 1                                           # 2026: from the repo's sourced head coach data
FAMILY = re.compile(r"\b(son|daughter|grandson|granddaughter|wife) of\b|\bpart of the [A-Za-z]+ family\b|\bgrandfather\b"
                    r"|\bfamily has owned\b", re.I)
SEED = 20261102
REPLICATIONS, BURN_IN, SEASONS = 100, 20, 20
HEADLINE_PER_OFFSEASON = 8.0           # the r2 research headline (coach at the end of the season, interim hand-offs counted)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

CITED: dict[str, set[str]] = {}        # url -> words the fetched page must contain (filled while the documents are built)


def cite(url: str, *expect: str) -> str:
    CITED.setdefault(url, set()).update(expect)
    return url


# ---------------------------------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------------------------------
def read_pinned(path: Path, sha256: str, label: str) -> bytes:
    raw = Path(path).read_bytes()
    got = hashlib.sha256(raw).hexdigest()
    if got != sha256:
        raise SystemExit(f"{label}: {path} has SHA-256 {got}, the pin is {sha256}")
    return raw


def fetch_to(cache: Path, name: str, url: str, sha256: str) -> Path:
    path = cache / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        cache.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "2k5-mod-studio-coach-owners/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:   # nosec B310 - fixed https hosts
            path.write_bytes(response.read())
    return path


class Games:
    """Per (club, season) regular-season and postseason games of nflverse games.csv, 1999-2025, scored games only."""

    def __init__(self, raw: bytes):
        text = raw.decode("utf-8")
        rows = list(csv.DictReader(text.splitlines(), delimiter=","))
        rows.sort(key=lambda r: (int(r["season"]), r["gameday"], r["game_id"]))
        self.reg: dict[tuple[str, int], list[tuple]] = collections.defaultdict(list)
        self.post: dict[tuple[str, int], list[tuple]] = collections.defaultdict(list)
        for r in rows:
            season = int(r["season"])
            if season < FIRST or season > LAST or r["home_score"] in ("", "NA") or r["away_score"] in ("", "NA"):
                continue
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            for side, mine, theirs in (("home", hs, as_), ("away", as_, hs)):
                club = ALIAS.get(r[side + "_team"], r[side + "_team"])
                game = (r["gameday"], int(r["week"]), r[side + "_coach"], mine, theirs, r["game_type"])
                (self.reg if r["game_type"] == "REG" else self.post)[(club, season)].append(game)
        self.clubs = sorted({club for club, _ in self.reg})

    def seasons(self, club: str) -> list[int]:
        return sorted(s for c, s in self.reg if c == club)

    def opener(self, club: str, season: int) -> str:
        return self.reg[(club, season)][0][2]

    def closer(self, club: str, season: int) -> str:
        return self.reg[(club, season)][-1][2]

    def record(self, club: str, season: int) -> tuple[int, int, int]:
        games = self.reg[(club, season)]
        w = sum(1 for g in games if g[3] > g[4])
        l = sum(1 for g in games if g[3] < g[4])
        return w, l, len(games) - w - l

    def playoffs(self, club: str, season: int) -> tuple[bool, int]:
        games = self.post.get((club, season), [])
        return bool(games), sum(1 for g in games if g[3] > g[4])


def teams_2026(teams_dir: Path, sources_file: Path) -> dict[str, dict]:
    """club -> {name, head_coach, sources} from the repo's own sourced 2026 data (two files that must agree)."""
    sourced = {e["team"]: e for e in json.loads(Path(sources_file).read_text(encoding="utf-8"))}
    out = {}
    for path in sorted(Path(teams_dir).glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        club = path.stem                      # the Rams' file says team "LA" inside; the file name is the club code
        coach = d["roster"]["head_coach"]
        entry = sourced[club]
        if entry["coach"] != coach:
            raise SystemExit(f"{club}: {path.name} says {coach!r}, data/vip/coach_sources_2026.json says {entry['coach']!r}")
        out[club] = {"name": d["name"], "head_coach": coach, "sources": list(entry["sources"])}
    if sorted(out) != sorted(co.CLUBS):
        raise SystemExit("the 2026 team files do not name the 32 clubs")
    return out


# ---------------------------------------------------------------------------------------------------------------------
# History and decisions
# ---------------------------------------------------------------------------------------------------------------------
def stints(games: Games, club: str, coach_2026: str) -> list[dict]:
    """Opening-day head coaches of a club, one entry per uninterrupted run of seasons (1999-2025, then 2026)."""
    seasons = games.seasons(club)
    runs: list[dict] = []
    for season in seasons + [NEW_COACH_YEAR]:
        name = coach_2026 if season == NEW_COACH_YEAR else games.opener(club, season)
        if runs and runs[-1]["name"] == name and runs[-1]["last"] == season - 1:
            runs[-1]["last"] = season
        else:
            runs.append({"name": name, "first": season, "last": season})
    for run in runs:
        run["seasons"] = run["last"] - run["first"] + 1
        run["opened_window"] = run["first"] == seasons[0] == FIRST      # may have started before 1999: tenure is a lower bound
    return runs


def decisions(games: Games, teams: dict[str, dict]) -> list[dict]:
    rows = []
    for club in games.clubs:
        runs = stints(games, club, teams[club]["head_coach"])
        by_season = {}
        for run in runs:
            for season in range(run["first"], run["last"] + 1):
                by_season[season] = run
        for season in games.seasons(club):
            run = by_season[season]
            w, l, t = games.record(club, season)
            made, pwins = games.playoffs(club, season)
            nxt = by_season[season + 1]
            rows.append({"club": club, "season": season, "coach": run["name"], "w": w, "l": l, "t": t, "g": w + l + t,
                         "pct": (w + t / 2) / (w + l + t), "tenure": season - run["first"] + 1, "censored": run["opened_window"],
                         "changed": nxt is not run, "next": nxt["name"], "made": made, "pwins": pwins})
    return rows


def group(d: dict) -> int:
    """Design column: 0 unknown tenure (the coach opened the 1999 window), 1 first season, 2 second, 3 third or later."""
    return 0 if d["censored"] else 1 + co.tenure_bucket(d["tenure"])


# ---------------------------------------------------------------------------------------------------------------------
# Statistics (stdlib only)
# ---------------------------------------------------------------------------------------------------------------------
def solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        pv = m[c][c]
        for j in range(c, n + 1):
            m[c][j] /= pv
        for r in range(n):
            if r != c and m[r][c] != 0:
                f = m[r][c]
                for j in range(c, n + 1):
                    m[r][j] -= f * m[c][j]
    return [m[i][n] for i in range(n)]


def logistic(x: list[list[float]], y: list[int], iters: int = 100) -> tuple[list[float], list[float], float]:
    k = len(x[0])
    beta = [0.0] * k
    ll = 0.0
    h = [[0.0] * k for _ in range(k)]
    for _ in range(iters):
        grad = [0.0] * k
        h = [[0.0] * k for _ in range(k)]
        ll = 0.0
        for xi, yi in zip(x, y):
            p = 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, xi))))
            p = min(max(p, 1e-12), 1 - 1e-12)
            ll += yi * math.log(p) + (1 - yi) * math.log(1 - p)
            w = p * (1 - p)
            for a in range(k):
                grad[a] += (yi - p) * xi[a]
                for c in range(k):
                    h[a][c] += w * xi[a] * xi[c]
        step = solve(h, grad)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-10:
            break
    se = []
    for a in range(k):
        e = [1.0 if i == a else 0.0 for i in range(k)]
        se.append(math.sqrt(max(solve(h, e)[a], 0.0)))
    return beta, se, ll


def fit_hazard(rows: list[dict]) -> dict:
    x = [[1.0 if group(d) == g else 0.0 for g in range(4)] + [d["pct"] - 0.5] for d in rows]
    y = [1 if d["changed"] else 0 for d in rows]
    beta, se, ll = logistic(x, y)
    null = sum(y) / len(y)
    ll_null = sum(y) * math.log(null) + (len(y) - sum(y)) * math.log(1 - null)
    for d, xi in zip(rows, x):
        d["p"] = 1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, xi))))
    # do the playoffs add anything once the record is known? (two more columns: made them, won a playoff game)
    x_playoffs = [xi + [1.0 if d["made"] else 0.0, 1.0 if d["pwins"] > 0 else 0.0] for xi, d in zip(x, rows)]
    _beta2, _se2, ll_playoffs = logistic(x_playoffs, y)
    lr = 2 * (ll_playoffs - ll)
    return {"alpha_unknown_tenure": beta[0], "alpha": beta[1:4], "slope_per_win_pct": beta[4], "se": se,
            "log_likelihood": ll, "log_likelihood_null": ll_null, "decisions": len(y), "changes": sum(y),
            "playoff_terms": {"extra_columns": ["made the playoffs", "won a playoff game"], "likelihood_ratio": round(lr, 2),
                              "df": 2, "p_value": round(math.exp(-lr / 2), 3)}}


def base_table(fit: dict) -> list[list[int]]:
    table = []
    for b in range(co.TENURE_BUCKETS):
        row = []
        for idx in range(co.GAMES_SCALE + 1):
            z = fit["alpha"][b] + fit["slope_per_win_pct"] * (idx / co.GAMES_SCALE - 0.5)
            row.append(int(round(1000 / (1 + math.exp(-z)))))
        table.append(row)
    return table


def nb_loglik(observed: dict, expected: dict, k: float) -> float:
    total = 0.0
    for club, o in observed.items():
        e = expected[club]
        if e <= 0:
            continue
        total += math.lgamma(o + k) - math.lgamma(k) - math.lgamma(o + 1) + k * math.log(k / (k + e)) + o * math.log(e / (k + e))
    return total


def poisson_loglik(observed: dict, expected: dict) -> float:
    return sum(o * math.log(expected[c]) - expected[c] - math.lgamma(o + 1) for c, o in observed.items() if expected[c] > 0)


def frailty_shape(observed: dict, expected: dict) -> dict:
    """Gamma shape for the owner multipliers. NB marginal likelihood over a grid; when the likelihood keeps rising to the
    end of the grid (no spread between clubs beyond records and tenure) use the smallest shape whose likelihood-ratio
    test against the best one is not rejected at 95% (chi-square, 1 df, 3.841): the largest owner spread the data allow."""
    grid = [float(k) for k in range(1, 401)]
    lls = [nb_loglik(observed, expected, k) for k in grid]
    best = max(range(len(grid)), key=lambda i: lls[i])
    ll_poisson = poisson_loglik(observed, expected)
    at_edge = best >= len(grid) - 5 or lls[best] <= ll_poisson + 1e-9
    if at_edge:
        top = max(lls[-1], ll_poisson)
        k = next(g for g, ll in zip(grid, lls) if 2 * (top - ll) <= 3.841)
        rule = "no spread between clubs beyond records and tenure: smallest shape not rejected at 95%"
    else:
        k = grid[best]
        rule = "maximum likelihood"
    return {"shape": k, "rule": rule, "log_likelihood_poisson": round(ll_poisson, 3),
            "log_likelihood_at_shape": round(nb_loglik(observed, expected, k), 3),
            "likelihood_ratio_vs_no_spread": round(2 * (nb_loglik(observed, expected, k) - ll_poisson), 3),
            "sum_squared_dispersion": round(sum((observed[c] - expected[c]) ** 2 / expected[c] for c in observed if expected[c] > 0), 2),
            "clubs": len(observed)}


# ---------------------------------------------------------------------------------------------------------------------
# Owners
# ---------------------------------------------------------------------------------------------------------------------
def owner_rows(wikitext: str, names: dict[str, str]) -> dict[str, dict]:
    """club -> {name, since, note, acquired} from the pinned table. A family succession or a public owner never starts a
    new era; an outside purchase does."""
    body = wikitext[wikitext.index("==Current owners=="):]
    by_name = {v: k for k, v in names.items()}
    out = {}
    for chunk in body.split("\n|-\n"):
        m = re.search(r"! scope = row \| \[\[([^\]|]+)(?:\|[^\]]+)?\]\]", chunk)
        if not m:
            continue
        club = by_name[m.group(1)]
        cells = re.split(r"\n\| ", chunk)
        owner_cell, since_cell, note_cell = cells[1], cells[2], cells[3] if len(cells) > 3 else ""
        links = [b or a for a, b in re.findall(r"\[\[(?!File:)([^\]|]+)(?:\|([^\]]+))?\]\]", owner_cell)]
        since = re.search(r"(\d{4})", since_cell)
        note = re.sub(r"<ref.*?(</ref>|/>)", "", note_cell, flags=re.S)
        note = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", note).replace("\n", " ").strip(" |")
        name = links[0]
        acquired = "public" if name.endswith("Inc.") else "family" if FAMILY.search(note) else "purchase"
        out[club] = {"name": name, "since": int(since.group(1)), "acquired": acquired, "note": note}
    if sorted(out) != sorted(co.CLUBS):
        raise SystemExit(f"the owners table names {len(out)} clubs, expected 32")
    return out


def departures(season_wikitext: str, raw: dict) -> dict[str, dict]:
    """The 2026 offseason's departures from ``offseason_2026.json``, each checked against the pinned Wikipedia text."""
    out = {}
    for club, entry in sorted(raw.items()):
        if entry["wikipedia_phrase"] not in season_wikitext:
            raise SystemExit(f"{club}: the pinned '{SEASON_TITLE}' page does not say {entry['wikipedia_phrase']!r}")
        last = entry["wikipedia_phrase"].split()[0]
        out[club] = {"reason": entry["reason"], "date": entry["date"], "in_season": entry["in_season"],
                     "source": cite(entry["source"], last, *entry["expect"]), "also": "wikipedia_2026_season"}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------------------------------------------------
def weighted_median(values: list[float], weights: list[float]) -> float:
    pairs = sorted(zip(values, weights))
    half = sum(weights) / 2
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= half:
            return v
    return pairs[-1][0]


def club_records(rows: list[dict]) -> dict[str, str]:
    """club -> "W-L-T W-L-T ..." for 1999-2025, the real sequences the simulation replays."""
    out = collections.defaultdict(list)
    for d in sorted(rows, key=lambda r: (r["club"], r["season"])):
        out[d["club"]].append(f"{d['w']}-{d['l']}-{d['t']}")
    return {club: " ".join(seq) for club, seq in sorted(out.items())}


def real_aggregates(rows: list[dict]) -> dict:
    fired = [d for d in rows if d["changed"]]
    by_off = collections.Counter(d["season"] for d in fired)
    completed = [d["tenure"] for d in fired if not d["censored"]]
    bucket_seen = collections.Counter(co.tenure_bucket(d["tenure"]) for d in rows if not d["censored"])
    bucket_fired = collections.Counter(co.tenure_bucket(d["tenure"]) for d in fired if not d["censored"])
    return {
        "decisions": len(rows), "changes": len(fired), "offseasons": LAST - FIRST + 1,
        "changes_per_offseason": round(len(fired) / (LAST - FIRST + 1), 3),
        "by_offseason": {str(s): by_off.get(s, 0) for s in range(FIRST, LAST + 1)},
        "fewest_in_an_offseason": min(by_off.get(s, 0) for s in range(FIRST, LAST + 1)),
        "most_in_an_offseason": max(by_off.get(s, 0) for s in range(FIRST, LAST + 1)),
        "median_fired_win_pct": round(statistics.median([d["pct"] for d in fired]), 3),
        "share_fired_after_a_winning_season": round(sum(1 for d in fired if d["pct"] > 0.5) / len(fired), 3),
        "median_tenure_when_fired": statistics.median(completed),
        "fired_rate_by_tenure": [round(bucket_fired[b] / bucket_seen[b], 3) for b in range(co.TENURE_BUCKETS)],
        "tenure_note": "tenure columns exclude the coaches who opened 1999 (their start is not in the data)",
    }


def r2_crosscheck(games: Games) -> dict:
    """The r2 research method (coach of the club's LAST game of each season, consecutive seasons 1999-2025), kept so the
    new table can be compared with the research report. Interim coaches missing from the file for 2024-2025 make this
    method wrong for those years, which is why the table does not use it."""
    per_club, records = {}, []
    for club in games.clubs:
        seasons = games.seasons(club)
        count = 0
        for a, b in zip(seasons, seasons[1:]):
            if games.closer(club, a) != games.closer(club, b):
                count += 1
                w, l, t = games.record(club, a)
                records.append((w + t / 2) / (w + l + t))
        per_club[club] = count
    total = sum(per_club.values())
    return {"method": "coach of the club's last game of each season; consecutive seasons 1999-2025 (r2 prototype)",
            "changes_per_club": per_club, "changes": total, "per_offseason": round(total / (LAST - FIRST), 2),
            "median_record_before_a_change": round(statistics.median(records), 3),
            "why_not_used": "an in-season firing is counted against the previous season's record and its interim replacement "
                            "counts again; nflverse has no interim coaches in 2024 and 2025"}


def calibrate(doc: dict, rows: list[dict]) -> None:
    """Fill ``doc['calibration']``: the model replayed on the real seasons, and the closed-loop simulation twice (the
    league average as fitted, and the league scale that reproduces the r2 headline of 8 changes a year)."""
    scale = {c["team"]: c["fire_scale_q8"] for c in doc["clubs"]}
    model = doc["model"]
    replay_p = [co.fire_permille(model, scale[d["club"]], d["w"], d["l"], d["t"], d["tenure"]) / 1000 for d in rows]
    fired = [d for d in rows if d["changed"]]
    cal = doc["calibration"]
    cal["real"] = doc["league"]
    cal["replay_on_real_seasons"] = {
        "expected_changes": round(sum(replay_p), 1), "real_changes": len(fired),
        "expected_per_offseason": round(sum(replay_p) / (LAST - FIRST + 1), 3),
        "median_win_pct_of_the_fired": round(weighted_median([d["pct"] for d in rows], replay_p), 3),
        "note": "every real club season weighted by its chance of dismissal under the final table (owner scales included, integers)",
    }
    args = dict(seed=SEED, replications=REPLICATIONS, burn_in=BURN_IN, seasons=SEASONS)
    cal["simulation"] = {"seed": SEED, "replications": REPLICATIONS, "burn_in_seasons": BURN_IN, "measured_seasons": SEASONS,
                         "league_q8": 256, "result": co.simulate(doc, **args)}
    lo, hi = 256, 512
    while hi - lo > 1:                                        # smallest league scale whose simulated rate reaches the headline
        mid = (lo + hi) // 2
        rate = co.simulate(doc, league_q8=mid, **dict(args, replications=40))["changes_per_offseason"]
        lo, hi = (mid, hi) if rate < HEADLINE_PER_OFFSEASON else (lo, mid)
    cal["simulation_r2_headline"] = {
        "target_per_offseason": HEADLINE_PER_OFFSEASON, "league_q8": hi, "seed": SEED, "replications": REPLICATIONS,
        "burn_in_seasons": BURN_IN, "measured_seasons": SEASONS,
        "result": co.simulate(doc, league_q8=hi, **args),
        "note": "the r2 research quoted 8 changes a year counting the coach at the end of each season, which counts a mid-season "
                "firing and the hire that replaces the interim as two; set model.league_q8 to this value to get that rate",
    }


def sources_block() -> dict:
    return {
        "nflverse_games": {"title": "nflverse nfldata games.csv", "url": GAMES_URL, "commit": NFLDATA_COMMIT,
                           "bytes": GAMES_BYTES, "sha256": GAMES_SHA256, "publisher": "nflverse / Lee Sharpe",
                           "use": "head coach of every club's games and the season records, 1999-2025 only",
                           "licence": "no licence declared in the repository; only facts (dates, scores, coach names) are used"},
        "wikipedia_owners": {"title": OWNERS_TITLE, "url": WIKI.format(title=OWNERS_TITLE.replace(" ", "_"), revision=OWNERS_REVISION),
                             "revision": OWNERS_REVISION, "sha256": OWNERS_SHA256, "publisher": "Wikipedia", "licence": "CC BY-SA 4.0",
                             "use": "principal owner, since when, and the note that separates a family succession from a purchase"},
        "wikipedia_2026_season": {"title": SEASON_TITLE, "url": WIKI.format(title=SEASON_TITLE.replace(" ", "_"), revision=SEASON_REVISION),
                                  "revision": SEASON_REVISION, "sha256": SEASON_SHA256, "publisher": "Wikipedia", "licence": "CC BY-SA 4.0",
                                  "use": "the table of 2026 offseason head coach changes: who left, why and when"},
        "teams_2026": {"title": "the repo's sourced 2026 head coaches",
                       "url": "https://github.com/cruuz/2k-football-mod-tools/tree/main/data/nfl2k5_teams_2026",
                       "files": ["data/nfl2k5_teams_2026/*.json (roster.head_coach)", "data/vip/coach_sources_2026.json (hire announcements)"],
                       "use": "the 2026 opening-day head coach of each club; the announcement URL of each is in history.current"},
    }


def build_owners(games: Games, teams: dict[str, dict], owners_wikitext: str, season_wikitext: str) -> dict:
    rows = decisions(games, teams)
    fit = fit_hazard(rows)
    table = base_table(fit)
    owners = owner_rows(owners_wikitext, {c: teams[c]["name"] for c in teams})
    left = departures(season_wikitext, json.loads((INPUTS / "offseason_2026.json").read_text(encoding="utf-8")))
    first_season = {c: games.seasons(c)[0] for c in games.clubs}
    era_first = {c: (owners[c]["since"] if owners[c]["acquired"] == "purchase" and owners[c]["since"] > first_season[c] else first_season[c])
                 for c in games.clubs}
    observed, expected, decided = {}, {}, {}
    for c in games.clubs:
        era = [d for d in rows if d["club"] == c and d["season"] >= era_first[c]]
        observed[c] = sum(1 for d in era if d["changed"])
        expected[c] = sum(d["p"] for d in era)
        decided[c] = len(era)
    contributing = {c: observed[c] for c in games.clubs if expected[c] > 0}
    shape = frailty_shape(contributing, {c: expected[c] for c in contributing})
    k = shape["shape"]
    scale = {c: int(round(256 * (observed[c] + k) / (expected[c] + k))) for c in games.clubs}

    clubs = []
    for c in sorted(games.clubs):
        runs = stints(games, c, teams[c]["head_coach"])
        club_rows = [d for d in rows if d["club"] == c]
        last_name = teams[c]["head_coach"].split()[-1]
        log = []
        for d in club_rows:
            if d["changed"]:
                run = next(r for r in runs if r["first"] <= d["season"] <= r["last"])
                entry = {"after_season": d["season"], "left": d["coach"], "arrived": d["next"],
                         "record": f"{d['w']}-{d['l']}-{d['t']}", "made_playoffs": d["made"], "playoff_wins": d["pwins"],
                         "tenure": run["seasons"], "tenure_is_minimum": run["opened_window"]}
                if d["season"] == LAST and c in left:
                    entry["departure"] = left[c]
                log.append(entry)
        if (c in left) != any(e["after_season"] == LAST for e in log):
            raise SystemExit(f"{c}: offseason_2026.json and the games.csv/2026 coach data disagree about a 2026 change")
        done = [r for r in runs if r["last"] < NEW_COACH_YEAR]
        exact = [r["seasons"] for r in done if not r["opened_window"]]
        hist = {
            "first_season": first_season[c], "decisions": len(club_rows), "changes": len(log),
            "head_coaches": [{k2: r[k2] for k2 in ("name", "first", "last", "seasons", "opened_window")} for r in runs],
            "completed_tenures": [r["seasons"] for r in done],
            "average_tenure_started_in_window": round(sum(exact) / len(exact), 2) if exact else None,
            "short_tenures_le2": sum(1 for r in done if r["seasons"] <= 2 and not r["opened_window"]),
            "current": {"name": teams[c]["head_coach"], "since": runs[-1]["first"],
                        "source": cite(teams[c]["sources"][0], last_name, "head coach"),
                        "also": [cite(u, last_name, "head coach") for u in teams[c]["sources"][1:]]},
            "changes_log": log,
        }
        o = owners[c]
        clubs.append({
            "team": c, "name": teams[c]["name"], "team_index": th.RETAIL_TEAM_INDEX[th.TEAM_ALIASES.get(c, c)],
            "fire_scale_q8": scale[c],
            "owner": {"name": o["name"], "since": o["since"], "acquired": o["acquired"], "note": o["note"],
                      "source": "wikipedia_owners"},
            "era": {"first_season": era_first[c], "decisions": decided[c], "changes": observed[c],
                    "expected_changes": round(expected[c], 4),
                    "multiplier": round((observed[c] + k) / (expected[c] + k), 3)},
            "history": hist,
            "sources": ["nflverse_games", "wikipedia_owners", "teams_2026"] + (["wikipedia_2026_season"] if c in left else []),
        })

    doc = {
        "schema": co.OWNERS_SCHEMA,
        "base_year": 2026,
        "status": "SOURCED history and owners; FITTED hazard; calibration SIMULATED. Nothing here has run in the game.",
        "window": {"first_season": FIRST, "last_season": LAST, "offseasons": LAST - FIRST + 1,
                   "decision": "after each season 1999-2025 the club either keeps the coach who opened that season or opens "
                               "the next one with another (the last decision picked the 2026 coach); Houston starts in 2002",
                   "basis": "opening-day head coach, full-season record"},
        "sources": sources_block(),
        "rules": {
            "owner_era": "an outside purchase after 1999 starts a new owner era (the club's earlier coaching decisions say nothing "
                         "about him); a family succession, a founding family or a public owner does not",
            "owner_scale": "fire_scale_q8 = 256 * (changes + k) / (expected_changes + k) over the owner's era, k = model.fit.frailty.shape; "
                           "a club with no decisions under its owner yet (Seattle) is exactly 256. A smaller k widens the spread of "
                           "owners (the data do not support one smaller than the stored k), a larger k narrows it",
            "reading": "1.00 (256) is the league's average temper; above it the owner fires sooner than the league does for the "
                       "same record and tenure, below it later",
            "departure": "the 2026 offseason's ten head coach departures carry reason, date and a news source; every other change "
                         "is derived from game data only",
        },
        "model": {
            "name": "owner_fire_hazard/v1",
            "unit": "permille",
            "formula": "idx = ((2*W+T)*17 + G)//(2*G); b = 0 if n<=1, 1 if n==2, else 2; p = base_permille[b][idx]; "
                       "p = (p*owner_q8*league_q8 + 32768) >> 16; p = min(p, 1000); fire when (draw % 1000) < p",
            "tenure_bucket": "n = seasons with the club including the season just played; 0 first season, 1 second, 2 third or later",
            "base_permille": table,
            "league_q8": 256,
            "fit": {
                "kind": "logistic regression on the season win percentage (centred at .500) with one intercept per tenure group",
                "decisions": fit["decisions"], "changes": fit["changes"],
                "intercept_unknown_tenure": round(fit["alpha_unknown_tenure"], 4),
                "intercepts": [round(a, 4) for a in fit["alpha"]],
                "slope_per_win_pct": round(fit["slope_per_win_pct"], 4),
                "standard_errors": [round(s, 4) for s in fit["se"]],
                "log_likelihood": round(fit["log_likelihood"], 2), "log_likelihood_null": round(fit["log_likelihood_null"], 2),
                "playoff_terms": dict(fit["playoff_terms"], used=False,
                                      verdict="made-the-playoffs and won-a-playoff-game add nothing significant once the win "
                                              "percentage is known, so the model does not use them"),
                "frailty": shape,
            },
        },
        "league": real_aggregates(rows),
        "crosscheck_r2": r2_crosscheck(games),
        "calibration": {"records": club_records(rows),
                        "records_basis": "the real regular-season record of every club and season 1999-2025 (nflverse games.csv); "
                                         "the simulation gives each of its 32 clubs the sequence of a random real club from a "
                                         "random start, wrapping around, so the spread, tails and persistence of records are real"},
        "clubs": clubs,
    }
    calibrate(doc, rows)
    return doc


# ---------------------------------------------------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------------------------------------------------
def head_coach_record(games: Games, coach: str, exits: list[dict]) -> dict | None:
    """Regular-season and playoff record of a coach as head coach 1999-2025 (nflverse names). The file credits the opening-day
    coach with every game of 2024 and 2025 (it lists no interim coaches), so a coach fired in the middle of one of those
    seasons loses the games played on or after the day he was fired (``exits``: the firing dates, each with its source)."""
    cut = {(e["club"], e["season"]): e["fired"] for e in exits if e["coach"] == coach}
    w = l = t = pw = pl = 0
    seasons, last, with_club = set(), None, collections.Counter()
    for (club, season), games_ in sorted(games.reg.items(), key=lambda kv: kv[0][1]):
        mine = [g for g in games_ if g[2] == coach and g[0] < cut.get((club, season), "9999-12-31")]
        if not mine:
            continue
        seasons.add(season)
        last = (season, club)
        with_club[club] += 1
        w += sum(1 for g in mine if g[3] > g[4])
        l += sum(1 for g in mine if g[3] < g[4])
        t += sum(1 for g in mine if g[3] == g[4])
        if (club, season) not in cut:
            for g in games.post.get((club, season), []):
                if g[2] == coach:
                    pw += g[3] > g[4]
                    pl += g[3] < g[4]
    if not seasons:
        return None
    out = {"seasons": len(seasons), "wins": w, "losses": l, "ties": t, "playoff_wins": pw, "playoff_losses": pl,
           "last_season": last[0], "last_club": last[1], "clubs": sorted(with_club)}
    if cut:
        out["cut_at_firing"] = [{"club": c, "season": s, "fired": d} for (c, s), d in sorted(cut.items())]
    return out


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def pool_entry(games: Games, exits: list[dict], first: str, last: str, **fields) -> dict:
    sources = [{"url": cite(s["url"], last, *s.get("expect", [])), "what": s["what"]} for s in fields.pop("sources")]
    entry = {"id": slug(f"{first} {last}"), "first": first, "last": last}
    entry.update(fields)
    entry["head_coach_record"] = head_coach_record(games, f"{first} {last}", exits)
    entry["sources"] = sources
    return entry


def build_pool(games: Games, teams: dict[str, dict], pool_input: dict, defense: dict) -> dict:
    heads = {t["head_coach"] for t in teams.values()}
    exits = json.loads((INPUTS / "in_season_exits.json").read_text(encoding="utf-8"))
    for e in exits:
        cite(e["source"], e["coach"].split()[-1])
    candidates = []
    for key, row in sorted(defense["teams"].items()):
        club = DC_KEY_TO_CLUB.get(key, key)
        first, _, last = row["dc"].partition(" ")
        if row["dc"] in heads:
            continue                                            # Tampa Bay: the head coach is also the defensive coordinator
        change = pool_input["dc_changes"].get(club, {})
        sources = change.get("sources") or [{"url": row["source"], "expect": ["defensive coordinator"],
                                             "what": "club coaches page names him as the 2026 defensive coordinator"}]
        fields = dict(side="defense", kind="coordinator", status=change.get("status", "employed"),
                      role_2026=change.get("role_2026", "Defensive coordinator"),
                      team_2026=change["team_2026"] if "team_2026" in change else club,
                      defense_identity_team=key, defense_identity_note=row["baseline_role"], sources=sources)
        if "note" in change:
            fields["note"] = change["note"]
        candidates.append(pool_entry(games, exits, first, last, **fields))
    for extra in pool_input["extra_candidates"]:
        extra = dict(extra)
        first, last = extra.pop("first"), extra.pop("last")
        if f"{first} {last}" in heads:
            raise SystemExit(f"{first} {last} is a 2026 head coach and cannot be in the hiring pool")
        extra.setdefault("defense_identity_team", None)
        candidates.append(pool_entry(games, exits, first, last, **extra))
    ids = [c["id"] for c in candidates]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate pool ids")
    candidates.sort(key=lambda c: (c["last"], c["first"]))
    left_out = []
    for item in pool_input["left_out"]:
        item = dict(item)
        if item.get("source"):
            item["source"] = cite(item["source"], item["name"].split()[-1], *item.pop("expect", []))
        left_out.append(item)
    sources = {k: v for k, v in sources_block().items() if k in ("nflverse_games", "teams_2026")}
    sources["defense_identity_2026"] = {
        "title": "the repo's sourced 2026 defensive coordinators",
        "url": "https://github.com/cruuz/2k-football-mod-tools/blob/main/data/vip/defense_identity_2026.json",
        "files": ["data/vip/defense_identity_2026.json"],
        "use": "the 31 defensive coordinators (Tampa Bay's head coach is its own coordinator) and each one's club page"}
    return {
        "schema": co.POOL_SCHEMA, "base_year": 2026, "as_of": pool_input["as_of"],
        "status": "SOURCED people and roles; derived head coach records; nobody here has been hired by anything yet",
        "rules": pool_input["rules"], "sources": sources, "candidates": candidates, "left_out": left_out,
        "in_season_exits": exits,
    }


# ---------------------------------------------------------------------------------------------------------------------
# URL checks
# ---------------------------------------------------------------------------------------------------------------------
def fetch_page(url: str) -> tuple[int | None, str]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                                                   "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:    # nosec B310 - https URLs cited by the data
            raw = response.read(3_000_000)
            status = response.status
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception:
        return None, ""
    text = html.unescape(raw.decode("utf-8", "replace")).replace("\xa0", " ")
    return status, re.sub(r"\s+", " ", text).lower()


def run_url_checks(path: Path) -> None:
    results = {}
    for url, words in sorted(CITED.items()):
        for attempt in range(3):                                         # a site that is briefly down gets two more tries
            status, text = fetch_page(url)
            if status == 200:
                break
            time.sleep(4)
        found = sorted(w for w in words if w.lower() in text)
        results[url] = {"http": status, "expect": sorted(words), "found": found}
        print(("ok   " if status == 200 and len(found) == len(words) else "FAIL ") + f"{status} {url}")
    doc = {"checked": dt.date.today().isoformat(), "urls": results}
    Path(path).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    bad = [u for u, r in results.items() if r["http"] != 200 or len(r["found"]) != len(r["expect"])]
    if bad:
        raise SystemExit(f"{len(bad)} cited URL(s) failed their check")


def stamp_checks(doc: dict, checks: dict, own_urls: set[str]) -> None:
    """Embed the check result of every URL the document cites as ``url_checks`` (and refuse a URL that was not checked)."""
    table = {}
    for url in sorted(own_urls):
        result = checks["urls"].get(url)
        if result is None or result["http"] != 200 or len(result["found"]) != len(result["expect"]):
            raise SystemExit(f"{url} has no passing check in url_checks.json: run tools/nfl2k5_coach_owners_build.py --check-urls")
        table[url] = {"http": 200, "checked": checks["checked"], "page_contains": result["found"]}
    doc["url_checks"] = table


urls_in = co.cited_urls


# ---------------------------------------------------------------------------------------------------------------------
def render(doc: dict) -> str:
    text = json.dumps(doc, indent=1, ensure_ascii=True)
    # lists of plain numbers on one line (the tables stay readable and the file much shorter)
    return re.sub(r"\[\s*(-?\d+(?:\.\d+)?(?:,\s*-?\d+(?:\.\d+)?)*)\s*\]",
                  lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", text) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=Path, help="nflverse games.csv at the pinned commit (default: the cache)")
    parser.add_argument("--owners-wikitext", type=Path, help="raw wikitext of the pinned owners revision (default: the cache)")
    parser.add_argument("--season-wikitext", type=Path, help="raw wikitext of the pinned 2026 NFL season revision (default: the cache)")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--fetch", action="store_true", help="download missing pinned inputs into --cache")
    parser.add_argument("--check-urls", action="store_true", help="fetch every cited URL and rewrite url_checks.json (network)")
    parser.add_argument("--check", action="store_true", help="build in memory and fail if the checked-in files differ")
    parser.add_argument("--no-pool", action="store_true")
    parser.add_argument("--out-owners", type=Path, default=OUT_OWNERS)
    parser.add_argument("--out-pool", type=Path, default=OUT_POOL)
    args = parser.parse_args(argv)

    def pinned(arg, name, url, sha):
        return arg or (fetch_to(args.cache, name, url, sha) if args.fetch else args.cache / name)

    games_path = pinned(args.games, "games.csv", GAMES_URL, GAMES_SHA256)
    owners_path = pinned(args.owners_wikitext, f"owners_{OWNERS_REVISION}.wikitext",
                         WIKI.format(title=OWNERS_TITLE.replace(" ", "_"), revision=OWNERS_REVISION) + "&action=raw", OWNERS_SHA256)
    season_path = pinned(args.season_wikitext, f"season2026_{SEASON_REVISION}.wikitext",
                         WIKI.format(title=SEASON_TITLE.replace(" ", "_"), revision=SEASON_REVISION) + "&action=raw", SEASON_SHA256)
    games = Games(read_pinned(games_path, GAMES_SHA256, "games.csv"))
    owners_text = read_pinned(owners_path, OWNERS_SHA256, "owners wikitext").decode("utf-8")
    season_text = read_pinned(season_path, SEASON_SHA256, "2026 season wikitext").decode("utf-8")
    teams = teams_2026(ROOT / "data" / "nfl2k5_teams_2026", ROOT / "data" / "vip" / "coach_sources_2026.json")

    owners_doc = build_owners(games, teams, owners_text, season_text)
    docs = [(args.out_owners, owners_doc)]
    pool_doc = None
    if not args.no_pool:
        defense = json.loads((ROOT / "data" / "vip" / "defense_identity_2026.json").read_text(encoding="utf-8"))
        pool_doc = build_pool(games, teams, json.loads((INPUTS / "pool_input.json").read_text(encoding="utf-8")), defense)
        docs.append((args.out_pool, pool_doc))
    checks_path = INPUTS / "url_checks.json"
    if args.check_urls:
        run_url_checks(checks_path)
    if not checks_path.is_file():
        raise SystemExit("no url_checks.json yet: run with --check-urls first")
    checks = json.loads(checks_path.read_text(encoding="utf-8"))
    for _path, doc in docs:
        urls = urls_in(doc)
        unexpected = urls - set(CITED)
        if unexpected:
            raise SystemExit(f"cited without an expectation: {sorted(unexpected)[:3]}")
        stamp_checks(doc, checks, urls)
    co.validate_owners(owners_doc)
    if pool_doc is not None:
        co.validate_pool(pool_doc)
    for path, doc in docs:
        text = render(doc)
        if args.check:
            if Path(path).read_text(encoding="utf-8") != text:
                raise SystemExit(f"{path} is stale: rebuild with tools/nfl2k5_coach_owners_build.py")
            print(f"{Path(path).name} verified")
        else:
            Path(path).write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
