#!/usr/bin/env python3
"""b77 / a4: build ``data/nfl2k5_moment_playbook_eras.json``, the era-correct playbook decisions for the 51 Anniversary moments.

What it records for each moment (physical row 1..51), per side:

* the book the v0.5 executable picks today, as proved under Unicorn by ``--proof`` (the resolver ``62902`` run with the real
  team object of each side: franchise key, SITU season word, exit taken);
* the book choice and why: a side whose season word is 2005 or later gets the franchise's current (v2) book, an older side
  keeps the preserved retail 2004 bank. The cut is the league's own shotgun adoption (nflverse, regular season, share of
  all run and pass snaps): 12 to 14 percent through 2004, 27 percent in 2007, 47 percent in 2012, 65 percent from 2016;
* the real shotgun rate of that team-season (nflverse ``shotgun`` flag, regular season, by down) and, for the side the CPU
  plays, the ``gun_weight`` that makes the analytic selector (``pb/v2/selection_model.py``, checked by p48o against the
  native lottery) call shotgun about as often as the real team did on first and second down.

``gun_weight`` is the value the owner ``nfl2k5_moment_gun_weight`` returns instead of the retail 0.05 for shotgun sets
beyond 10 yards of the goal line (see that module). It is fitted to the CPU side because the user's own team never uses
the CPU's formation lottery.

a4pd (franchise weights per down and distance bin): the ``teams`` block holds, for each of the 32 book keys, the real 2025 and 2026-to-date
shotgun rates in seven bins (``TEAM_BINS``) and the seven fitted weights (``gun_weights``, multiples of 0.05 up to 16.0). Commands::

    python3 tools/b77/a4_eras.py team-rates --csv 2025=play_by_play_2025.csv.gz --csv 2026=play_by_play_2026.csv.gz --out team_rates.json
    python3 tools/b77/a4_eras.py teams --data data/nfl2k5_moment_playbook_eras.json --team-rates team_rates.json --books DIR \\
        --selection-model-dir TREE --out data/nfl2k5_moment_playbook_eras.json        # replaces the teams block, keeps the moments

``a4_repair.py --refit-books`` refits the moments and the seven bin weights of every team from the given books (no network).

Re-run when the books change (p48o / p48d final)::

    python3 tools/b77/a4_eras.py build --proof reports/a4_current_books.json --rates nflverse_rates.json \\
        --books DIR_WITH_TEAM_BOOKS --selection-model-dir /path/to/tree/with/pb/v2 --out data/nfl2k5_moment_playbook_eras.json

``DIR_WITH_TEAM_BOOKS`` holds one composed PLAY entry per franchise named ``<KEY>.play`` (the 32 entries 307..342 of the
final disc, extracted). ``rates`` is the output of ``rates`` (below) or a hand-checked copy. Nothing here is a gameplay
result: shares are the analytic selector's numbers on the real book bytes.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SCHEMA = "b77/a4_moment_playbook_eras/v2"
NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.csv.gz"
MODERN_FIRST_SEASON = 2005
# nflverse team codes for the franchise keys the books use
NFLVERSE_CODES = {"ARZ": ("ARI",), "STL": ("STL", "LA"), "SD": ("SD", "LAC"), "OAK": ("OAK", "LV")}
SIT_D1 = ("1st&10 own20", "1st&10 own25", "1st&10 opp40")
SIT_D2 = ("2nd&7 own35", "2nd&8 mid")
SIT_D3 = ("3rd&3 own25", "3rd&8 mid")
SITUATIONS = {"1st&10 own20": dict(down=1, distance=10, yard=20), "1st&10 own25": dict(down=1, distance=10, yard=25),
              "1st&10 opp40": dict(down=1, distance=10, yard=60), "2nd&7 own35": dict(down=2, distance=7, yard=35),
              "2nd&8 mid": dict(down=2, distance=8, yard=50), "3rd&3 own25": dict(down=3, distance=3, yard=25),
              "3rd&8 mid": dict(down=3, distance=8, yard=50)}
WEIGHT_GRID = [round(0.05 + 0.05 * i, 2) for i in range(40)]             # 0.05 .. 2.00
RETAIL_WEIGHT = 0.05
BIN_MAX_WEIGHT = 16.0                                                  # per-bin weights: 0.05 .. 16.0 in steps of 0.05 (uint16 units of 0.05 in the executable)
FIT_TOLERANCE = 0.5                                                    # percentage points
BIN_GRID = [round(0.05 * k, 2) for k in range(1, int(round(BIN_MAX_WEIGHT / 0.05)) + 1)]


# ------------------------------------------------------------------------------------------------ real rates (nflverse)

def rates_from_csv(path: Path, year: int) -> dict:
    """{team: {plays, gun, d1, d2, d3, pass_pct, no_huddle}} for one season's regular-season run and pass snaps."""
    counts: dict[str, dict[str, int]] = {}
    with gzip.open(path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["season_type"] != "REG" or not row["posteam"]:
                continue
            is_pass = row["pass"] == "1" and row.get("qb_spike", "0") != "1"
            is_rush = row["rush"] == "1" and row.get("qb_kneel", "0") != "1"
            if not (is_pass or is_rush):
                continue
            try:
                down = int(float(row["down"]))
            except ValueError:
                continue
            team = counts.setdefault(row["posteam"], {})
            for tag in ("all", f"d{down}"):
                team[tag + "_n"] = team.get(tag + "_n", 0) + 1
                if row["shotgun"] == "1":
                    team[tag + "_gun"] = team.get(tag + "_gun", 0) + 1
            if is_pass:
                team["all_pass"] = team.get("all_pass", 0) + 1
            if row["no_huddle"] == "1":
                team["all_nohuddle"] = team.get("all_nohuddle", 0) + 1
    return {"season": year, "source": NFLVERSE.format(year=year), "teams": counts}


def percent(counts: dict, tag: str) -> float | None:
    n = counts.get(tag + "_n", 0)
    return round(100.0 * counts.get(tag + "_gun", 0) / n, 1) if n else None


def team_rate(rates: dict, key: str, season: int) -> dict | None:
    """The real rates of franchise ``key`` in ``season`` from a ``rates`` file, or None (before 1999 there is no data)."""
    year = rates.get(str(season))
    if not year:
        return None
    for code in NFLVERSE_CODES.get(key, (key,)):
        c = year["teams"].get(code)
        if c:
            n = c["all_n"]
            return dict(source=year["source"], nflverse_team=code, plays=n, gun_pct=percent(c, "all"), first_down_pct=percent(c, "d1"),
                        second_down_pct=percent(c, "d2"), third_down_pct=percent(c, "d3"),
                        pass_pct=round(100.0 * c.get("all_pass", 0) / n, 1), no_huddle_pct=round(100.0 * c.get("all_nohuddle", 0) / n, 1))
    return None


def league_rate(rates: dict, season: int) -> dict | None:
    year = rates.get(str(season))
    if not year:
        return None
    n = sum(c["all_n"] for c in year["teams"].values())
    g = sum(c.get("all_gun", 0) for c in year["teams"].values())
    n1 = sum(c.get("d1_n", 0) for c in year["teams"].values())
    g1 = sum(c.get("d1_gun", 0) for c in year["teams"].values())
    return dict(plays=n, gun_pct=round(100.0 * g / n, 1), first_down_pct=round(100.0 * g1 / n1, 1), source=year["source"])


# ------------------------------------------------------------------------------------------------ the analytic fit

@contextlib.contextmanager
def gun_weight(selection_model, value: float):
    """Run the analytic selector with the shotgun constant replaced (the owner's whole effect on the lottery)."""
    original = selection_model.form_weight

    def patched(flags, sit, which):
        ftype = (flags >> 8) & 0x3F
        to_goal = (100 - sit["yard"]) * selection_model.YD
        if ftype < 4 and flags & 0xC0000 == 0x80000 and to_goal > 914.4:
            return value
        # same curve, with the gun test passed
        ytg = sit["distance"] * selection_model.YD
        t = selection_model.blend_t(sit["down"], ytg)
        points = selection_model.CURVE_A if which == "A" else selection_model.CURVE_B
        r = [(flags >> s) & 7 for s in (21, 24, 27)]
        tt, a, b = (t - 0.5, r[1], r[2]) if t >= 0.5 else (t, r[0], r[1])
        return selection_model.curve(points, b - 2) * 2 * tt + (1 - 2 * tt) * selection_model.curve(points, a - 2)

    selection_model.form_weight = patched
    try:
        yield
    finally:
        selection_model.form_weight = original


def gun_share(selection_model, book, name: str) -> float:
    """Percent of CPU formation calls that are shotgun or pistol sets in one situation (analytic selector)."""
    _pcat, pform, _means = book.distribution(SITUATIONS[name])
    total = sum(pform.values())
    gun = sum(p for fi, p in pform.items() if book.forms[fi]["flags"] & 0xC0000 == 0x80000 and book.forms[fi]["type"] < 4)
    return 100.0 * gun / total if total else 0.0


def shares_at(selection_model, book, value: float) -> dict:
    with gun_weight(selection_model, value):
        mean = lambda names: sum(gun_share(selection_model, book, n) for n in names) / len(names)   # noqa: E731
        return dict(first_down=round(mean(SIT_D1), 1), second_down=round(mean(SIT_D2), 1),
                    third_and_short_to_long=round(mean(SIT_D3), 1))


def fit_weight(selection_model, book, real_first: float, real_second: float) -> tuple[float, dict]:
    """The weight on the grid whose mean of the first and second down shares is closest to the real mean of the two.

    The analytic selector is steeper on first down than second (the books' ratings favour the gun sets on first down), the
    real teams the other way round, so a fit to each down separately would overshoot one of them; the mean is the honest
    target and both downs are reported next to the real numbers."""
    best = None
    for w in WEIGHT_GRID:
        s = shares_at(selection_model, book, w)
        err = ((s["first_down"] + s["second_down"]) / 2 - (real_first + real_second) / 2) ** 2
        if best is None or err < best[0] - 1e-9:
            best = (err, w, s)
    return best[1], best[2]



# ------------------------------------------------------------------------------------------------ franchise teams (exhibition, season, franchise)

TEAM_BINS = {                      # name: (downs, yards to go range, representative distance for the selector)
    # The stub of nfl2k5_moment_gun_weight picks the same seven bins from the live down and yards to go: 1st down at any distance;
    # 2nd down 1-3 / 4-7 / 8+; 3rd and 4th down 1-3 / 4-6 / 7+. The selector's rating curve (0x207E30) is flat inside each bin except
    # 2nd & 4-7 (t = 0 to 0.2 over 5..7 yd) and 3rd & 4-6 (t = 0.25 to 0.75), so one representative distance per bin is exact for the
    # flat bins and the centre of the two sloped ones.
    "d1": ((1,), (1, 99), 10), "d2_short": ((2,), (1, 3), 2), "d2_mid": ((2,), (4, 7), 6), "d2_long": ((2,), (8, 99), 11),
    "d3_short": ((3, 4), (1, 3), 2), "d3_mid": ((3, 4), (4, 6), 5), "d3_long": ((3, 4), (7, 99), 10)}
BIN_ORDER = tuple(TEAM_BINS)       # the order of the seven weights in the executable's table (one row of 7 uint16 per franchise)
TEAM_YARD = 50                     # the selector's yard line for the bins: the rule only acts beyond 10 yards of the goal
# franchise keys of the shipped books -> nflverse team codes (latest first)
TEAM_CODES = {"ARZ": ("ARI",), "STL": ("LA", "STL"), "SD": ("LAC", "SD"), "OAK": ("LV", "OAK")}


def team_bins_from_csv(path: Path) -> dict:
    """{nflverse team: {bin: [snaps, shotgun snaps, sum of yards to go]}} for regular season run and pass snaps (no spikes, no kneels)
    beyond 10 yards of the goal line, 4th downs counted with the 3rd-down bins."""
    out: dict[str, dict[str, list[int]]] = {}
    with gzip.open(path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["season_type"] != "REG" or not row["posteam"]:
                continue
            is_pass = row["pass"] == "1" and row.get("qb_spike", "0") != "1"
            is_rush = row["rush"] == "1" and row.get("qb_kneel", "0") != "1"
            if not (is_pass or is_rush):
                continue
            try:
                down, togo, line = int(float(row["down"])), int(float(row["ydstogo"])), float(row["yardline_100"])
            except ValueError:
                continue
            if line <= 10:
                continue
            for name, (downs, (lo, hi), _rep) in TEAM_BINS.items():
                if down in downs and lo <= togo <= hi:
                    cell = out.setdefault(row["posteam"], {}).setdefault(name, [0, 0, 0])
                    cell[0] += 1
                    cell[1] += row["shotgun"] == "1"
                    cell[2] += togo
    return out


def csv_facts(path: Path) -> dict:
    """What the report cites about one nflverse file: name, size, sha256, regular season games, last week and the file's date."""
    import datetime
    games, last_week = set(), 0
    with gzip.open(path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["season_type"] == "REG":
                games.add(row["game_id"])
                last_week = max(last_week, int(row["week"]))
    stat = path.stat()
    return dict(file=path.name, bytes=stat.st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), regular_season_games=len(games),
                last_week=last_week, downloaded=datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"))


def merge_team_bins(parts: list[dict]) -> dict:
    out: dict = {}
    for part in parts:
        for team, bins in part.items():
            for name, cell in bins.items():
                dest = out.setdefault(team, {}).setdefault(name, [0, 0, 0])
                for i, v in enumerate(cell):
                    dest[i] += v
    return out


def team_share(selection_model, book, bin_name: str) -> float:
    _downs, _range, distance = TEAM_BINS[bin_name]
    down = TEAM_BINS[bin_name][0][0]
    _pcat, pform, _means = book.distribution(dict(down=down, distance=distance, yard=TEAM_YARD))
    total = sum(pform.values())
    gun = sum(p for fi, p in pform.items() if book.forms[fi]["flags"] & 0xC0000 == 0x80000 and book.forms[fi]["type"] < 4)
    return 100.0 * gun / total if total else 0.0


def team_shares_at(selection_model, book, value: float) -> dict:
    with gun_weight(selection_model, value):
        return {name: round(team_share(selection_model, book, name), 1) for name in TEAM_BINS}


def fit_bin_weights(selection_model, book, bins: dict) -> tuple[dict, dict]:
    """One weight per down and distance bin: the grid weight (0.05 to 16.0) whose analytic selector share is nearest to the team's
    real shotgun share in that bin; where the selector's curve is nearly flat (a share that saturates, such as a book that is all
    shotgun on 3rd and long) the lowest weight within FIT_TOLERANCE points of the nearest share is taken instead of a needlessly
    large one. The seven bins are independent because the stub looks the weight up by bin; a bin the team never played keeps the
    retail 0.05. Returns (weights, selector shares at those weights)."""
    shares = {}                                                   # weight -> {bin: share}, one scan of the grid
    for w in BIN_GRID:
        with gun_weight(selection_model, w):
            shares[w] = {name: team_share(selection_model, book, name) for name in TEAM_BINS}
    weights, fitted = {}, {}
    for name in TEAM_BINS:
        real = bins.get(name, {}).get("gun_pct")
        if real is None:
            weights[name], fitted[name] = RETAIL_WEIGHT, round(shares[RETAIL_WEIGHT][name], 1)
            continue
        errors = {w: abs(shares[w][name] - real) for w in BIN_GRID}
        best = min(errors.values())
        w = next(w for w in BIN_GRID if errors[w] <= best + FIT_TOLERANCE)       # lowest weight within the tolerance of the best fit
        weights[name], fitted[name] = w, round(shares[w][name], 1)
    return weights, fitted


def _fit_record(selection_model, books_dir: Path, key: str, bins: dict) -> dict:
    raw = (books_dir / f"{key}.play").read_bytes()
    book = selection_model.book_from(raw)
    weights, fitted = fit_bin_weights(selection_model, book, bins)
    return dict(gun_weights=weights, fit=dict(book=f"{key}.play", book_sha256=hashlib.sha256(raw).hexdigest(),
                                              retail_rule=team_shares_at(selection_model, book, RETAIL_WEIGHT), fitted=fitted))


def team_records(team_rates: dict, books_dir: Path | None, selection_model, sources: dict) -> dict:
    """The ``teams`` block: for each of the 32 book keys the pooled real bins and (with books) the seven fitted bin weights."""
    keys = [row["source"].removesuffix("-pb.iff") for row in json.loads((ROOT / "data/nfl2k5_stock_books.json").read_text())["aliases"]]
    out = {}
    for key in keys:
        code = next(c for c in TEAM_CODES.get(key, (key,)) if c in team_rates)
        cells = team_rates[code]
        bins = {name: dict(snaps=cells[name][0], gun=cells[name][1], gun_pct=round(100.0 * cells[name][1] / cells[name][0], 1),
                           mean_togo=round(cells[name][2] / cells[name][0], 2)) if cells.get(name, [0])[0] else dict(snaps=0, gun=0, gun_pct=None, mean_togo=None)
                for name in TEAM_BINS}
        snaps = sum(b["snaps"] for b in bins.values())
        gun = sum(b["gun"] for b in bins.values())
        record = dict(nflverse_team=code, sources=sources, snaps=snaps, gun_pct=round(100.0 * gun / snaps, 1), bins=bins,
                      gun_weights={name: RETAIL_WEIGHT for name in TEAM_BINS})
        if selection_model and books_dir:
            record.update(_fit_record(selection_model, books_dir, key, bins))
        out[key] = record
    return out


# ------------------------------------------------------------------------------------------------ build

def load_selection_model(directory: Path):
    sys.path.insert(0, str(directory))
    sys.path.insert(0, str(directory / "tools"))
    from pb.v2 import selection_model            # noqa: E402
    return selection_model


def side_record(proof_side: dict, season: int, key: str, rates: dict | None) -> dict:
    classic = proof_side["exit"] != "default"
    out = dict(franchise_key=key, season=season, book_now=("classic: " + proof_side["alias"]) if classic else f"franchise book {key}-pb.iff",
               book_now_exit=proof_side["exit"], category=proof_side["category"])
    if rates is not None:
        real = team_rate(rates, key, season)
        if real:
            out["real"] = real
    return out


def league_rate_for(rates: dict, season: int) -> dict | None:
    return league_rate(rates, season)


def side_notes(side: dict, league: dict | None) -> tuple[str, str]:
    """Plain-language offense and defense reasoning for one side, from its facts only."""
    key, season, real = side["franchise_key"], side["season"], side.get("real")
    league_text = (f"league shotgun share {league['gun_pct']}% (first down {league['first_down_pct']}%) in {season}" if league
                   else "no nflverse play-by-play before 1999")
    real_text = (f"{key} {season}: {real['gun_pct']}% of snaps in shotgun (first down {real['first_down_pct']}%, second {real['second_down_pct']}%, "
                 f"third {real['third_down_pct']}%), {real['no_huddle_pct']}% no-huddle") if real else ""
    if side["era"] == "classic":
        offense = (f"Season {season} is before 2005: the preserved retail 2004 {key} book (E2R-{key}-pb.iff, a byte copy of the retail entry) is the period "
                   f"book; {league_text}. " + real_text).strip()
        defense = f"Same retail 2004 book: its own retail defense (base fronts and coverages of the 2004 game), kept as shipped."
    else:
        offense = (f"Season {season} is 2005 or later: the franchise's current {key} book (p48o v2 offense, shotgun, trips, bunch and "
                   f"flea flicker included); {league_text}. " + real_text).strip()
        defense = (f"The same {key} book's p48d v2 defense. It follows the franchise's 2025 coordinator tendencies; the {season} coordinator's "
                   "base front and blitz rate are not modelled (listed as a limit in the report).")
    return offense, defense


def build(proof: dict, rates: dict, books_dir: Path | None, selection_dir: Path | None, moments_data, team_rates: dict | None = None) -> dict:
    selection_model = load_selection_model(selection_dir) if selection_dir else None
    rows = []
    for entry in sorted(proof["rows"], key=lambda r: r["physical_row"]):
        row = entry["physical_row"]
        user = entry["user_side"]                                    # 0 away, 1 home (SITU +0x24)
        cpu = "away" if user == 1 else "home"
        sides = {}
        for side in ("away", "home"):
            sides[side] = side_record(entry[side], entry["situ_season_words"][side], entry[side]["franchise_key"], rates)
            modern = entry["situ_season_words"][side] >= MODERN_FIRST_SEASON
            sides[side]["book_choice"] = f"franchise book {entry[side]['franchise_key']}-pb.iff (v2 offense, v2 defense)" if modern else \
                "preserved retail 2004 book E2R-" + entry[side]["franchise_key"] + "-pb.iff"
            sides[side]["era"] = "modern" if modern else "classic"
            sides[side]["offense"], sides[side]["defense"] = side_notes(sides[side], league_rate_for(rates, sides[side]["season"]))
        record = dict(row=row, title=entry["title"], date=entry["date"], user_side="home" if user == 1 else "away", cpu_side=cpu,
                      sides=sides, gun_weight=RETAIL_WEIGHT)
        cpu_side = sides[cpu]
        if cpu_side["era"] == "modern" and "real" in cpu_side and selection_model and books_dir:
            book_path = books_dir / f"{cpu_side['franchise_key']}.play"
            raw = book_path.read_bytes()
            book = selection_model.book_from(raw)
            real = cpu_side["real"]
            weight, fitted = fit_weight(selection_model, book, real["first_down_pct"], real["second_down_pct"])
            record["gun_weight"] = weight
            record["fit"] = dict(book=f"{cpu_side['franchise_key']}.play", book_sha256=hashlib.sha256(raw).hexdigest(),
                                 target=dict(first_down=real["first_down_pct"], second_down=real["second_down_pct"], third_down_real=real["third_down_pct"]),
                                 retail_rule=shares_at(selection_model, book, RETAIL_WEIGHT), fitted=fitted)
        rows.append(record)
    league = {str(y): league_rate(rates, y) for y in sorted(int(k) for k in rates) if league_rate(rates, y)}
    teams = team_records(team_rates["bins"], books_dir, selection_model, team_rates["sources"]) if team_rates else {}
    return dict(schema=SCHEMA, modern_first_season=MODERN_FIRST_SEASON,
                rule=("A side whose SITU season word is 2005 or later gets its franchise's current book; an older side keeps the preserved "
                      "retail 2004 bank. The selector stays the one in nfl2k5_stock_books (62902). gun_weight replaces the retail 0.05 "
                      "that 0x207EF0 gives every shotgun set beyond 10 yards of the goal line (nfl2k5_moment_gun_weight)."),
                league_shotgun_pct=league, source="nflverse play_by_play (https://github.com/nflverse/nflverse-data/releases/tag/pbp), "
                "regular season, run and pass snaps excluding spikes and kneels, share with shotgun == 1", moments=rows, teams=teams)


def refit(data: dict, books_dir: Path, selection_dir: Path) -> dict:
    """The same data with every modern row's ``gun_weight`` and ``fit`` recomputed from the books in ``books_dir``
    (``<KEY>.play``: the final composed PLAY entries). Real rates, rows and notes are read from ``data`` itself, so the
    integrator needs no network and no emulator: the repair calls this when it is given the final offense and defense books."""
    selection_model = load_selection_model(selection_dir)
    out = json.loads(json.dumps(data))
    for record in out["moments"]:
        if "fit" not in record:
            continue
        cpu = record["sides"][record["cpu_side"]]
        real = cpu["real"]
        raw = (books_dir / f"{cpu['franchise_key']}.play").read_bytes()
        book = selection_model.book_from(raw)
        weight, fitted = fit_weight(selection_model, book, real["first_down_pct"], real["second_down_pct"])
        record["gun_weight"] = weight
        record["fit"] = dict(book=f"{cpu['franchise_key']}.play", book_sha256=hashlib.sha256(raw).hexdigest(),
                             target=record["fit"]["target"], retail_rule=shares_at(selection_model, book, RETAIL_WEIGHT), fitted=fitted)
    for key, team in out.get("teams", {}).items():
        if team.get("classic") or "fit" not in team:
            continue
        team.update(_fit_record(selection_model, books_dir, key, team["bins"]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rates", help="aggregate nflverse play_by_play_<year>.csv.gz files into one rates file")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    t = sub.add_parser("team-rates", help="pool franchise down and distance shotgun bins from several nflverse seasons")
    t.add_argument("--csv", action="append", required=True, help="YEAR=path/to/play_by_play_YEAR.csv.gz (repeatable)")
    t.add_argument("--out", type=Path, required=True)
    u = sub.add_parser("teams", help="replace the teams block (and the schema tag) of an existing era data file; the moments block is kept as is")
    u.add_argument("--data", type=Path, required=True)
    u.add_argument("--team-rates", type=Path, required=True)
    u.add_argument("--books", type=Path, required=True)
    u.add_argument("--selection-model-dir", type=Path, required=True)
    u.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("build", help="write the era data file")
    b.add_argument("--team-rates", type=Path)
    b.add_argument("--proof", type=Path, required=True)
    b.add_argument("--rates", type=Path, required=True)
    b.add_argument("--books", type=Path)
    b.add_argument("--selection-model-dir", type=Path)
    b.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "rates":
        out = {}
        for path in sorted(args.dir.glob("play_by_play_*.csv.gz")):
            year = int(path.name.split("_")[-1].split(".")[0])
            out[str(year)] = rates_from_csv(path, year)
            print(year, len(out[str(year)]["teams"]), "teams", flush=True)
        args.out.write_text(json.dumps(out, sort_keys=True), encoding="utf-8", newline="\n")
        return 0
    if args.cmd == "team-rates":
        parts, sources, files = [], {}, {}
        for spec in args.csv:
            year, path = spec.split("=", 1)
            parts.append(team_bins_from_csv(Path(path)))
            sources[year] = NFLVERSE.format(year=year)
            files[year] = csv_facts(Path(path))
        args.out.write_text(json.dumps(dict(sources=sources, files=files, bins=merge_team_bins(parts)), sort_keys=True), encoding="utf-8", newline="\n")
        return 0
    if args.cmd == "teams":
        data = json.loads(args.data.read_text())
        rates = json.loads(args.team_rates.read_text())
        data["schema"] = SCHEMA
        data["team_bins"] = {name: dict(downs=list(downs), togo=list(rng), selector_distance=rep) for name, (downs, rng, rep) in TEAM_BINS.items()}
        data["team_bin_files"] = rates.get("files", {})
        data["teams"] = team_records(rates["bins"], args.books, load_selection_model(args.selection_model_dir), rates["sources"])
        args.out.write_text(json.dumps(data, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
        print("wrote", args.out, "teams", len(data["teams"]))
        return 0
    team_rates = json.loads(args.team_rates.read_text()) if args.team_rates else None
    data = build(json.loads(args.proof.read_text()), json.loads(args.rates.read_text()), args.books, args.selection_model_dir, None, team_rates)
    args.out.write_text(json.dumps(data, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    print("wrote", args.out, "rows", len(data["moments"]), "weights", sorted({m["gun_weight"] for m in data["moments"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
