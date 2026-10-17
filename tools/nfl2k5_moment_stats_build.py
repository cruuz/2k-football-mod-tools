#!/usr/bin/env python3
"""Historical stats at the start of every ESPN 25th Anniversary moment (b775 job mo2).

Builds ``data/nfl2k5_moment_stats.json`` from cached public play-by-play:

* nflverse play-by-play (CC-BY-4.0, https://github.com/nflverse/nflverse-data/releases), seasons 1999 and later;
* Pro-Football-Reference box score pages (their play-by-play table), read from Internet Archive snapshots
  (pro-football-reference.com refuses scripted clients). The pages are reference inputs only: they stay in the
  local source folder and never ship. The JSON keeps the URL, the snapshot URL and the sha256 of the page.

Every number is a sum over play rows of one cited source that come before the moment's first play. The JSON lists the
included play rows (nflverse ``play_id``; PFR play-by-play row ordinal) so each value can be recomputed. A PFR stat
family is kept only when the same parser, run over the WHOLE game, reproduces PFR's own box score table for every
player exactly; otherwise the family is left out and named in ``omitted``. Games with no play-by-play anywhere
(PFR has none for these older games) get no stats and say so.

usage: nfl2k5_moment_stats_build.py --sources DIR [--check]
  DIR holds nflverse/play_by_play_<season>.csv.gz, nflverse/players.csv and pfr/<boxscore id>.html.
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import html
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/nfl2k5_moment_stats.json"
SCHEMA = "nfl2k5_moment_stats/v1"
NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz"
PFR = "https://www.pro-football-reference.com/boxscores/{id}.htm"

# The game's own stat ids (default.xbe descriptor table 0xA8A510, player card columns, box score rows 0xAED668).
STATS = {
    "pass_cmp": 0x04, "pass_att": 0x23, "pass_yds": 0x4C, "pass_td": 0x40, "pass_int": 0x16,
    "rush_att": 0x03, "rush_yds": 0x50, "rush_td": 0x3F,
    "rec": 0x2E, "rec_yds": 0x4F, "rec_td": 0x3E,
    "tackles": 0x32, "half_sacks": 0x2F, "def_int": 0x17, "def_int_yds": 0x48, "forced_fumbles": 0x11,
    "xpm": 0x58, "xpa": 0x59,
    "fga_1_29": 0xA9, "fga_30_39": 0xAA, "fga_40_49": 0xAB, "fga_50": 0xAC,
    "fgm_1_29": 0xAD, "fgm_30_39": 0xAE, "fgm_40_49": 0xAF, "fgm_50": 0xB0,
    "punts": 0x2B, "punt_yds": 0x4E, "kr": 0x18, "kr_yds": 0x4B, "pr": 0x2A, "pr_yds": 0x4D,
    # team-only rows of the box score
    "first_downs": 0x0E, "third_att": 0x27, "third_conv": 0x53, "fourth_att": 0x28, "fourth_conv": 0x54,
    "pass_plays": 0x25, "rush_plays": 0x26, "penalties": 0x24, "penalty_yds": 0x62, "turnovers": 0x42,
    "time_of_possession": 0x5F,
}
TEAM_ONLY = ("first_downs", "third_att", "third_conv", "fourth_att", "fourth_conv", "pass_plays", "rush_plays",
             "penalties", "penalty_yds", "turnovers", "time_of_possession")
FAMILIES = {
    "passing": ("pass_cmp", "pass_att", "pass_yds", "pass_td", "pass_int"),
    "rushing": ("rush_att", "rush_yds", "rush_td"),
    "receiving": ("rec", "rec_yds", "rec_td"),
    "defense": ("tackles", "half_sacks", "def_int", "def_int_yds", "forced_fumbles"),
    "kicking": ("xpm", "xpa", "fga_1_29", "fga_30_39", "fga_40_49", "fga_50", "fgm_1_29", "fgm_30_39", "fgm_40_49",
                "fgm_50"),
    "punting": ("punts", "punt_yds"),
    "returns": ("kr", "kr_yds", "pr", "pr_yds"),
}
DEFINITIONS = {
    "pass_yds": "players: gross passing yards; team: net (gross minus yards lost to sacks), the official team figure",
    "rush_att": "includes kneel-downs, as official rushing totals do",
    "half_sacks": "the game counts sacks in halves (total sacks = 0.5 x this): a full sack is 2, a shared sack 1",
    "tackles": "solo + assisted tackles credited on the play rows (nflverse); not available for PFR games",
    "pass_plays": "pass attempts plus sacks", "rush_plays": "rushing attempts",
    "turnovers": "interceptions thrown plus fumbles lost",
    "time_of_possession": "seconds; game-clock time between consecutive nflverse plays credited to the team with the "
                          "ball on the earlier play (not available for PFR games, whose old play clocks are spaced "
                          "evenly rather than recorded)",
    "first_downs": "nflverse first_down (rushing, passing and penalty first downs)",
    "penalties": "accepted penalties (declined and offsetting fouls excluded)",
}

# One entry per physical Anniversary row (1..51). side names are the SITU franchise names; "real" maps them to the
# source's team codes (a SITU side need not be the real home team). start: first play of the moment (excluded).
CATALOG = [
    *({"row": r, "status": "no_play_by_play", "pfr": i} for r, i in (
        (1, "196712310gnb"), (2, "196811170rai"), (3, "197112250kan"), (4, "197212230pit"), (5, "197412210rai"),
        (6, "197912160dal"), (7, "198012070sfo"), (8, "198201020mia"), (9, "198201100sfo"), (10, "198310020was"),
        (11, "198701110cle"), (12, "198709200cin"), (13, "198711080crd"), (16, "199201040den"),
        (17, "199210040den"), (18, "199301030buf"))),
    {"row": 14, "pfr": "198901220cin", "real": {"bengals": "CIN", "49ers": "SFO"},
     "start": "first play of the 49ers' drive from their 8 with 3:10 left (score 16-13)"},
    {"row": 15, "pfr": "199101270buf", "real": {"bills": "BUF", "giants": "NYG"},
     "start": "first play of the Bills' last drive from their 10 with 2:16 left (score 19-20)"},
    {"row": 19, "pfr": "199410170den", "real": {"broncos": "DEN", "chiefs": "KAN"},
     "start": "the Broncos' kickoff after taking a 28-24 lead with 1:29 left"},
    {"row": 20, "pfr": "199709210buf", "real": {"colts": "IND", "bills": "BUF"},
     "start": "the Colts' kickoff after taking a 26-0 lead in the second quarter"},
    {"row": 21, "pfr": "199801250den", "real": {"packers": "GNB", "broncos": "DEN"},
     "start": "first play of the Broncos' drive from the Green Bay 49 with 3:27 left (score 24-24)"},
    {"row": 26, "pfr": "199901170min", "real": {"falcons": "ATL", "vikings": "MIN"},
     "start": "first play of the Falcons' drive from their 29 with 2:07 left (score 20-27)"},
    {"row": 22, "season": 1999, "game": "1999_21_STL_TEN", "start_play": 4097, "real": {"rams": "LA", "titans": "TEN"}},
    {"row": 23, "season": 2001, "game": "2001_21_STL_NE", "start_play": 3705, "real": {"rams": "LA", "patriots": "NE"}},
    {"row": 24, "season": 2002, "game": "2002_18_NYG_SF", "start_play": 2662, "real": {"giants": "NYG", "49ers": "SF"},
     "note": "SITU starts the Giants' kickoff at 3:05 of the third quarter; the real kickoff after the 38-14 field "
             "goal was at 4:27 (play 2662)"},
    {"row": 25, "season": 2003, "game": "2003_19_GB_PHI", "start_play": 3635, "real": {"packers": "GB", "eagles": "PHI"},
     "note": "SITU clock 1:26; the real fourth-and-26 snap was at 1:12 (play 3635)"},
    {"row": 51, "season": 2025, "game": "2025_07_PIT_CIN", "start_play": 4262, "real": {"steelers": "PIT", "bengals": "CIN"}},
]
SPEC = ROOT / "tools/nfl2k5_espn25_more_moments_spec.json"
NEW_ROWS = {  # more_moments order -> physical row (26..51); the spec carries nflverse game and start play
    "helmet_catch": 27, "toe_tap": 28, "manningham": 29, "comeback_28_3": 30, "fourth_and_18": 31,
    "music_city_miracle": 32, "tuck_rule": 33, "super_bowl_shootout": 34, "ambush": 35, "new_meadowlands_miracle": 36,
    "beast_quake": 37, "catch_three": 38, "mile_high_miracle": 39, "goal_line_stand": 40, "dez_caught_it": 41,
    "butler_goal_line": 42, "miracle_in_motown": 43, "minneapolis_miracle": 44, "philly_special": 45,
    "jet_chip_wasp": 46, "thirteen_seconds": 47, "donald_fourth_down": 48, "comeback_33": 49, "overtime_in_vegas": 50,
}
NFL_TEAM = {"rams": "LA", "titans": "TEN", "patriots": "NE", "giants": "NYG", "49ers": "SF", "packers": "GB",
            "eagles": "PHI", "steelers": "PIT", "bengals": "CIN", "cardinals": "ARI", "falcons": "ATL",
            "vikings": "MIN", "bills": "BUF", "raiders": "OAK", "panthers": "CAR", "saints": "NO", "colts": "IND",
            "seahawks": "SEA", "ravens": "BAL", "broncos": "DEN", "cowboys": "DAL", "lions": "DET", "chiefs": "KC"}
SUPER_BOWL_ROWS = (14, 15, 21, 22, 23, 27, 28, 29, 30, 34, 35, 40, 42, 45, 46, 48, 50)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def catalog():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    rows = {c["row"]: dict(c) for c in CATALOG}
    for m in spec["moments"]:
        row = NEW_ROWS.get(m["id"])
        if row is None:
            continue
        season = int(m["game_id"][:4])
        rows[row] = {"row": row, "season": season, "game": m["game_id"], "start_play": int(m["start_play_id"])}
    assert sorted(rows) == list(range(1, 52)), sorted(set(range(1, 52)) - set(rows))
    return [rows[r] for r in range(1, 52)]


# ---------------------------------------------------------------------------------------------------- nflverse
def nflverse_game(src, season, game):
    path = src / f"nflverse/play_by_play_{season}.csv.gz"
    with gzip.open(path, "rt", newline="") as f:
        plays = [r for r in csv.DictReader(f) if r["game_id"] == game]
    if not plays:
        raise SystemExit(f"{game}: no plays in {path}")
    plays.sort(key=lambda r: float(r["order_sequence"]) if r["order_sequence"] not in ("", "NA")
               else float(r["play_id"]))
    return plays, path


def num(v):
    return float(v) if v not in ("", "NA", None) else 0.0


def flag(r, k):
    return r.get(k) in ("1", "1.0")


def nflverse_stats(plays, start_play, names):
    order = [int(float(r["play_id"])) for r in plays]
    cut = order.index(start_play)
    before = plays[:cut]
    team = collections.defaultdict(collections.Counter)
    player = collections.defaultdict(collections.Counter)
    who = {}

    def credit(pid, pname, tm, stat, v):
        if not pid or pid == "NA":
            return
        player[pid][stat] += v
        who.setdefault(pid, (pname, tm))

    for i, r in enumerate(before):
        pt = r["play_type"]
        if pt in ("no_play", "") and not flag(r, "penalty"):
            continue
        desc = r["desc"]
        pos, de = r["posteam"], r["defteam"]
        two = flag(r, "two_point_attempt")
        nullified = pt == "no_play"
        if flag(r, "penalty") and r["penalty_team"] and "declined" not in desc.lower() \
                and "offsetting" not in desc.lower():
            team[r["penalty_team"]]["penalties"] += 1
            team[r["penalty_team"]]["penalty_yds"] += int(num(r["penalty_yards"]))
        if nullified or two:
            continue
        if flag(r, "first_down") and pos:
            team[pos]["first_downs"] += 1
        for k, s in (("third_down_converted", ("third_att", "third_conv")), ("third_down_failed", ("third_att",)),
                     ("fourth_down_converted", ("fourth_att", "fourth_conv")), ("fourth_down_failed", ("fourth_att",))):
            if flag(r, k) and pos:
                for stat in s:
                    team[pos][stat] += 1
        if flag(r, "sack"):
            team[pos]["pass_plays"] += 1
            team[pos]["sack_yds"] += -int(num(r["yards_gained"]))
            if r["sack_player_id"] not in ("", "NA"):
                credit(r["sack_player_id"], r["sack_player_name"], de, "half_sacks", 2)
                team[de]["half_sacks"] += 2
            for k in ("half_sack_1", "half_sack_2"):
                if r[k + "_player_id"] not in ("", "NA"):
                    credit(r[k + "_player_id"], r[k + "_player_name"], de, "half_sacks", 1)
                    team[de]["half_sacks"] += 1
        elif flag(r, "pass_attempt") and r["passer_player_id"] not in ("", "NA"):
            team[pos]["pass_plays"] += 1
            for stat, v in (("pass_att", 1), ("pass_cmp", int(flag(r, "complete_pass"))),
                            ("pass_yds", int(num(r["passing_yards"]))), ("pass_td", int(flag(r, "pass_touchdown"))),
                            ("pass_int", int(flag(r, "interception")))):
                credit(r["passer_player_id"], r["passer_player_name"], pos, stat, v)
                team[pos][stat] += v
            if flag(r, "complete_pass") and r["receiver_player_id"] not in ("", "NA"):
                for stat, v in (("rec", 1), ("rec_yds", int(num(r["receiving_yards"]))),
                                ("rec_td", int(flag(r, "pass_touchdown")))):
                    credit(r["receiver_player_id"], r["receiver_player_name"], pos, stat, v)
                    team[pos][stat] += v
            if flag(r, "interception"):
                credit(r["interception_player_id"], r["interception_player_name"], de, "def_int", 1)
                credit(r["interception_player_id"], r["interception_player_name"], de, "def_int_yds",
                       int(num(r["return_yards"])))
                team[de]["def_int"] += 1
                team[de]["def_int_yds"] += int(num(r["return_yards"]))
        if flag(r, "rush_attempt") and r["rusher_player_id"] not in ("", "NA"):
            team[pos]["rush_plays"] += 1
            for stat, v in (("rush_att", 1), ("rush_yds", int(num(r["rushing_yards"]))),
                            ("rush_td", int(flag(r, "rush_touchdown")))):
                credit(r["rusher_player_id"], r["rusher_player_name"], pos, stat, v)
                team[pos][stat] += v
        for k in ("solo_tackle_1", "solo_tackle_2", "assist_tackle_1", "assist_tackle_2", "assist_tackle_3",
                  "assist_tackle_4", "tackle_with_assist_1", "tackle_with_assist_2"):
            pid = r.get(k + "_player_id")
            if pid not in ("", "NA", None):
                tm = r.get(k + "_team") or de
                credit(pid, r[k + "_player_name"], tm, "tackles", 1)
                team[tm]["tackles"] += 1
        for k in ("forced_fumble_player_1", "forced_fumble_player_2"):
            pid = r.get(k + "_player_id")
            if pid not in ("", "NA", None):
                credit(pid, r[k + "_player_name"], r[k + "_team"], "forced_fumbles", 1)
                team[r[k + "_team"]]["forced_fumbles"] += 1
        if flag(r, "fumble_lost") and r["fumbled_1_team"]:
            team[r["fumbled_1_team"]]["fumbles_lost"] += 1
        if flag(r, "extra_point_attempt") and r["kicker_player_id"] not in ("", "NA"):
            good = int(r["extra_point_result"] == "good")
            for stat, v in (("xpa", 1), ("xpm", good)):
                credit(r["kicker_player_id"], r["kicker_player_name"], pos, stat, v)
                team[pos][stat] += v
        if flag(r, "field_goal_attempt") and r["kicker_player_id"] not in ("", "NA"):
            d = int(num(r["kick_distance"]))
            band = "1_29" if d < 30 else "30_39" if d < 40 else "40_49" if d < 50 else "50"
            for stat, v in (("fga_" + band, 1), ("fgm_" + band, int(r["field_goal_result"] == "made"))):
                credit(r["kicker_player_id"], r["kicker_player_name"], pos, stat, v)
                team[pos][stat] += v
        if pt == "punt" and r["punter_player_id"] not in ("", "NA") and not flag(r, "punt_blocked"):
            for stat, v in (("punts", 1), ("punt_yds", int(num(r["kick_distance"])))):
                credit(r["punter_player_id"], r["punter_player_name"], pos, stat, v)
                team[pos][stat] += v
            if r["punt_returner_player_id"] not in ("", "NA") and not flag(r, "punt_fair_catch"):
                for stat, v in (("pr", 1), ("pr_yds", int(num(r["return_yards"])))):
                    credit(r["punt_returner_player_id"], r["punt_returner_player_name"], de, stat, v)
                    team[de][stat] += v
        if pt == "kickoff" and r["kickoff_returner_player_id"] not in ("", "NA") and not flag(r, "touchback"):
            for stat, v in (("kr", 1), ("kr_yds", int(num(r["return_yards"])))):
                credit(r["kickoff_returner_player_id"], r["kickoff_returner_player_name"], r["return_team"] or de,
                       stat, v)
                team[r["return_team"] or de][stat] += v
    # time of possession from consecutive game clocks up to the moment's first play
    top = collections.Counter()
    seq = [r for r in plays[:cut + 1] if r["game_seconds_remaining"] not in ("", "NA")]
    for a, b in zip(seq, seq[1:]):
        if a["posteam"]:
            top[a["posteam"]] += max(0, int(num(a["game_seconds_remaining"]) - num(b["game_seconds_remaining"])))
    for tm, v in top.items():
        team[tm]["time_of_possession"] = v
    for tm in team:
        team[tm]["turnovers"] = team[tm]["pass_int"] + team[tm]["fumbles_lost"]
        team[tm]["pass_yds_net"] = team[tm]["pass_yds"] - team[tm]["sack_yds"]
    players = []
    for pid, stats in player.items():
        pname, tm = who[pid]
        full = names.get(pid, {})
        players.append({"source_id": pid, "source_name": pname, "name": full.get("name") or pname,
                        "first": full.get("first"), "last": full.get("last"), "team": tm,
                        "stats": {k: v for k, v in sorted(stats.items()) if v}})
    included = [int(float(r["play_id"])) for r in before]
    return team, players, included, plays[cut]


def nflverse_names(src):
    out = {}
    with open(src / "nflverse/players.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["gsis_id"]] = {"name": r["display_name"], "first": r["first_name"], "last": r["last_name"]}
    return out


# ---------------------------------------------------------------------------------------------------- PFR
LINK = re.compile(r'<a href="/players/[A-Za-z]/([A-Za-z0-9.]+)\.htm">([^<]+)</a>')


def pfr_page(src, pid):
    path = src / f"pfr/{pid}.html"
    return path.read_text(encoding="utf-8", errors="replace"), path


def pfr_table(text, tid):
    i = text.find(f'id="{tid}"')
    if i < 0:
        return []
    j = text.find("</table>", i)
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", text[i:j], re.S):
        cells = dict(re.findall(r'<t[hd][^>]*data-stat="([^"]+)"[^>]*>(.*?)</t[hd]>', r, re.S))
        if cells:
            out.append(cells)
    return out


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def pfr_rows(text):
    rows = []
    for c in pfr_table(text, "pbp"):
        if "detail" not in c or clean(c.get("quarter", "")) == "Quarter":
            continue
        rows.append({k: (v if k == "detail" else clean(v)) for k, v in c.items()})
    return rows


def pfr_box(text):
    """{pfr id: (name, team, {stat: value})} from PFR's own player tables (the reconciliation target)."""
    box = {}
    keys = {"pass_cmp": "pass_cmp", "pass_att": "pass_att", "pass_yds": "pass_yds", "pass_td": "pass_td",
            "pass_int": "pass_int", "rush_att": "rush_att", "rush_yds": "rush_yds", "rush_td": "rush_td",
            "rec": "rec", "rec_yds": "rec_yds", "rec_td": "rec_td", "def_int": "def_int",
            "def_int_yds": "def_int_yds", "sacks": "sacks", "kick_ret": "kr", "kick_ret_yds": "kr_yds",
            "punt_ret": "pr", "punt_ret_yds": "pr_yds", "xpm": "xpm", "xpa": "xpa", "fgm": "fgm", "fga": "fga",
            "punt": "punts", "punt_yds": "punt_yds"}
    for tid in ("player_offense", "player_defense", "returns", "kicking"):
        for c in pfr_table(text, tid):
            m = LINK.search(c.get("player", ""))
            if not m:
                continue
            pid, name = m.group(1), html.unescape(m.group(2))
            e = box.setdefault(pid, [name, clean(c.get("team", "")), {}])
            for k, v in c.items():
                if k in keys and clean(v) not in ("",):
                    try:
                        e[2][keys[k]] = float(clean(v))
                    except ValueError:
                        pass
    return box


def parse_play(detail):
    """One PFR play-by-play detail cell -> list of (actor pfr id, actor name, stat, value) and flags."""
    links = [(m.start(), m.group(1), html.unescape(m.group(2))) for m in LINK.finditer(detail)]
    text = html.unescape(re.sub(r"<[^>]+>", "", detail)).strip()
    p = re.sub(r'<a href="/players/[^"]+">[^<]+</a>', "\x01", detail)
    p = html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
    ids = [(i, n) for _s, i, n in links]
    out, flags = [], set()

    def yards(s):
        if s is None:
            return 0
        if "no gain" in s:
            return 0
        m = re.search(r"(-?\d+) yards?", s)
        return int(m.group(1)) if m else 0

    if not p or "Timeout" in p or "coin toss" in p or "(no play)" in p or "Play nullified" in p \
            or re.match(r"^\w[\w ]* penalized", p) or p.startswith("Penalty on"):
        if p.startswith("Penalty on") or "(no play)" in p:
            flags.add("penalty_row")
        flags.add("no_stats")
        return out, flags, text
    main = p.split(". Penalty on")[0]
    k = 0  # actor index in ids, in order of appearance

    def nxt():
        nonlocal k
        k += 1
        return ids[k - 1] if k - 1 < len(ids) else (None, None)

    m = re.match(r"^\x01 pass (complete|incomplete)( (?:short |deep )?(?:left|right|middle))?( to \x01| intended for \x01)?(.*)$", main)
    if m:
        qb = nxt()
        flags.add("pass")
        cmp_ = m.group(1) == "complete"
        rest = m.group(4)
        rec = nxt() if m.group(3) else (None, None)
        out.append((*qb, "pass_att", 1))
        if "is intercepted by \x01" in rest or "intercepted by \x01" in rest:
            d = nxt()
            out.append((*qb, "pass_int", 1))
            out.append((*d, "def_int", 1))
            ry = re.search(r"returns? for (-?\d+|no gain)", rest)
            out.append((*d, "def_int_yds", yards(ry.group(0)) if ry else 0))
            flags.add("interception")
        elif cmp_:
            y = yards(rest.split(".")[0])
            td = int(", touchdown" in rest.split(".")[0])
            out += [(*qb, "pass_cmp", 1), (*qb, "pass_yds", y), (*qb, "pass_td", td)]
            if rec[0]:
                out += [(*rec, "rec", 1), (*rec, "rec_yds", y), (*rec, "rec_td", td)]
            else:
                flags.add("unknown_receiver")
    elif re.match(r"^\x01 sacked", main):
        qb = nxt()
        flags.add("sack")
        y = yards(main)
        sackers = []
        if re.match(r"^\x01 sacked by \x01 and \x01", main):
            sackers = [nxt(), nxt()]
            for s in sackers:
                out.append((*s, "half_sacks", 1))
        elif re.match(r"^\x01 sacked by \x01", main):
            s = nxt()
            out.append((*s, "half_sacks", 2))
        out.append((*qb, "sack_yds", -y))
    elif re.match(r"^\x01 kicks off", main):
        k_ = nxt()
        m = re.search(r"returned by \x01 for (-?\d+ yards?|no gain)", main)
        if m:
            r_ = nxt()
            out += [(*r_, "kr", 1), (*r_, "kr_yds", yards(m.group(1)))]
        flags.add("kickoff")
    elif re.match(r"^\x01 punts", main):
        pu = nxt()
        out += [(*pu, "punts", 1), (*pu, "punt_yds", yards(main.split(",")[0]))]
        m = re.search(r"returned by \x01 for (-?\d+ yards?|no gain)", main)
        if m:
            r_ = nxt()
            out += [(*r_, "pr", 1), (*r_, "pr_yds", yards(m.group(1)))]
        flags.add("punt")
    elif re.match(r"^\x01 (-?\d+) yard field goal (good|no good)", main):
        ki = nxt()
        m = re.match(r"^\x01 (-?\d+) yard field goal (good|no good)", main)
        d = int(m.group(1))
        band = "1_29" if d < 30 else "30_39" if d < 40 else "40_49" if d < 50 else "50"
        out += [(*ki, "fga_" + band, 1), (*ki, "fgm_" + band, int(m.group(2) == "good"))]
        flags.add("field_goal")
    elif re.match(r"^\x01 kicks extra point (good|no good)", main):
        ki = nxt()
        out += [(*ki, "xpa", 1), (*ki, "xpm", int("no good" not in main))]
        flags.add("extra_point")
    elif re.match(r"^\x01 (?:(?:left|right|up the|middle)[\w ]*?)?for (-?\d+ yards?|no gain)", main) \
            or re.match(r"^\x01 (left|right|middle)[\w ]* for", main):
        ru = nxt()
        seg = main.split(".")[0]
        out += [(*ru, "rush_att", 1), (*ru, "rush_yds", yards(seg)), (*ru, "rush_td", int(", touchdown" in seg))]
        flags.add("rush")
    else:
        flags.add("unparsed")
    # tackles and fumbles anywhere in the play
    for mm in re.finditer(r"\(tackle by \x01( and \x01)?\)", p):
        pass
    if "fumbles" in main:
        flags.add("fumble")
    return out, flags, text


def pfr_stats(src, entry, situ):
    text, path = pfr_page(src, entry["pfr"])
    rows = pfr_rows(text)
    box = pfr_box(text)
    team_of = {pid: tm for pid, (n, tm, s) in box.items()}
    parsed = []
    for i, r in enumerate(rows):
        out, flags, t = parse_play(r["detail"])
        parsed.append((i, r, out, flags, t))
    return rows, parsed, box, team_of, path


def aggregate(parsed, upto, team_of):
    player = collections.defaultdict(collections.Counter)
    names = {}
    for i, r, out, flags, t in parsed[:upto]:
        for pid, name, stat, v in out:
            if pid is None:
                continue
            player[pid][stat] += v
            names[pid] = name
    return player, names


def reconcile(parsed, box, team_of):
    """Which stat families the parser reproduces exactly over the whole game, compared with PFR's box score."""
    player, names = aggregate(parsed, len(parsed), team_of)
    ok = {}
    checks = {"passing": ("pass_cmp", "pass_att", "pass_yds", "pass_td", "pass_int"),
              "rushing": ("rush_att", "rush_yds", "rush_td"), "receiving": ("rec", "rec_yds", "rec_td"),
              "returns": ("kr", "kr_yds", "pr", "pr_yds"), "kicking": ("xpm", "xpa"), "punting": ("punts", "punt_yds"),
              "interceptions": ("def_int",)}
    detail = {}
    for fam, stats in checks.items():
        bad = []
        for pid in set(box) | set(player):
            bstats = box.get(pid, [None, None, {}])[2]
            for s in stats:
                if s in ("xpm", "xpa"):
                    mine = player[pid][s]
                else:
                    mine = player[pid][s]
                theirs = bstats.get(s, 0.0)
                if fam == "kicking":
                    mine = player[pid][s]
                if abs(mine - theirs) > 0.001:
                    bad.append((pid, s, mine, theirs))
        ok[fam] = not bad
        detail[fam] = bad[:8]
    # field goals: compare made/attempted totals per kicker
    bad = []
    for pid in set(box) | set(player):
        b = box.get(pid, [None, None, {}])[2]
        fga = sum(player[pid][k] for k in player[pid] if k.startswith("fga_"))
        fgm = sum(player[pid][k] for k in player[pid] if k.startswith("fgm_"))
        if abs(fga - b.get("fga", 0)) > .001 or abs(fgm - b.get("fgm", 0)) > .001:
            bad.append((pid, "fg", fgm, fga, b.get("fgm", 0), b.get("fga", 0)))
    ok["kicking"] = ok["kicking"] and not bad
    detail["field_goals"] = bad[:8]
    bad = []
    for pid in set(box) | set(player):
        b = box.get(pid, [None, None, {}])[2]
        if abs(player[pid]["half_sacks"] / 2 - b.get("sacks", 0)) > .001:
            bad.append((pid, "sacks", player[pid]["half_sacks"] / 2, b.get("sacks", 0)))
    ok["sacks"] = not bad
    detail["sacks"] = bad[:8]
    return ok, detail


# ---------------------------------------------------------------------------------------------------- build
def build(src):
    situ = {r["row"]: r for r in json.loads((src / "i4_situ.json").read_text())}
    names = nflverse_names(src)
    sources, moments = {}, []
    for entry in catalog():
        row = entry["row"]
        s = situ[row]
        m = {"row": row, "title": s["title"], "date": s["date"], "super_bowl": row in SUPER_BOWL_ROWS,
             "situ": {"away": s["away"], "home": s["home"], "quarter": s["quarter_index"] + 1,
                      "clock_seconds": s["clock_seconds"], "away_score": s["away_score"],
                      "home_score": s["home_score"]}}
        if entry.get("status") == "no_play_by_play":
            text, path = pfr_page(src, entry["pfr"])
            assert 'id="pbp"' not in text, row
            key = "pfr:" + entry["pfr"]
            sources[key] = {"url": PFR.format(id=entry["pfr"]), "sha256": sha_file(path),
                            "note": "box score page has no play-by-play table"}
            m.update(status="no_play_by_play", source=key, team={}, players=[],
                     omitted=["every stat: no play-by-play exists for this game in the cited source, so the "
                              "totals cannot be cut at the moment's clock"])
            moments.append(m)
            continue
        if "pfr" in entry:
            rows, parsed, box, team_of, path = pfr_stats(src, entry, s)
            start = pfr_start(row, rows)
            key = "pfr:" + entry["pfr"]
            sources[key] = {"url": PFR.format(id=entry["pfr"]), "sha256": sha_file(path),
                            "via": "Internet Archive snapshot (pro-football-reference.com blocks scripted access)"}
            ok, detail = reconcile(parsed, box, team_of)
            player, pnames = aggregate(parsed, start, team_of)
            keep = {"passing": ok["passing"], "rushing": ok["rushing"], "receiving": ok["receiving"],
                    "returns": ok["returns"], "kicking": ok["kicking"], "punting": ok["punting"]}
            keep_int = ok["interceptions"]
            keep_sacks = ok["sacks"]
            fam_of = {st: fam for fam, sts in FAMILIES.items() for st in sts}
            players, team = [], collections.defaultdict(collections.Counter)
            for pid, st in player.items():
                tm = team_of.get(pid)
                stats = {}
                for k, v in st.items():
                    fam = fam_of.get(k)
                    if k == "sack_yds":
                        if keep_sacks and tm:
                            team[tm]["sack_yds"] += v
                        continue
                    if k == "half_sacks":
                        if not keep_sacks:
                            continue
                    elif k in ("def_int", "def_int_yds"):
                        if not keep_int:
                            continue
                    elif fam is None or not keep.get(fam):
                        continue
                    if v:
                        stats[k] = v
                if not tm:
                    continue
                for k, v in stats.items():
                    team[tm][k] += v
                if stats:
                    players.append({"source_id": pid, "name": pnames[pid], "team": tm, "stats": dict(sorted(stats.items()))})
            for tm in team:
                if keep["passing"]:
                    team[tm]["pass_plays"] = team[tm]["pass_att"] + (0 if not keep_sacks else 0)
                if keep["rushing"]:
                    team[tm]["rush_plays"] = team[tm]["rush_att"]
                if keep["passing"] and keep_sacks:
                    team[tm]["pass_yds_net"] = team[tm]["pass_yds"] - team[tm]["sack_yds"]
            omitted = [f"{fam}: the parser does not reproduce PFR's whole-game box score ({detail.get(fam)})"
                       for fam, v in ok.items() if not v]
            omitted += ["first downs, third/fourth downs, penalties, time of possession: not recorded per play "
                        "in this source in a form that can be cut", "tackles and forced fumbles: not in the "
                        "source's box score for this game, so they cannot be checked"]
            m.update(status="seeded", source=key, cut={"rule": entry["start"], "first_play_row": start,
                     "first_play": pfr_text(rows[start])},
                     included_rows=list(range(start)), real=entry["real"],
                     team=finish_team(team, entry["real"], s), players=side_players(players, entry["real"], s),
                     reconciliation={k: v for k, v in ok.items()}, omitted=omitted)
            moments.append(m)
            continue
        plays, path = nflverse_game(src, entry["season"], entry["game"])
        key = f"nflverse:{entry['season']}"
        sources[key] = {"url": NFLVERSE.format(season=entry["season"]), "sha256": sha_file(path),
                        "licence": "CC-BY-4.0", "attribution": "nflverse contributors"}
        team, players, included, first = nflverse_stats(plays, entry["start_play"], names)
        real = entry.get("real") or {s["away"]: first["away_team"], s["home"]: first["home_team"]}
        check_score(row, s, first, real)
        m.update(status="seeded", source=key, game=entry["game"],
                 cut={"rule": "every play before nflverse play_id %d" % entry["start_play"],
                      "first_play": first["desc"]}, note=entry.get("note"), included_play_ids=included, real=real,
                 team=finish_team(team, real, s), players=side_players(players, real, s),
                 omitted=["redzone, return touchdowns, two-point tries: not seeded"])
        moments.append(m)
    sources["nflverse:players"] = {"url": "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv",
                                   "sha256": sha_file(src / "nflverse/players.csv"), "licence": "CC-BY-4.0"}
    return {"schema": SCHEMA, "evidence": "Sourced play-by-play sums cut at each moment's first play; EXPERIMENTAL "
            "/ UNWITNESSED in game", "generator": "tools/nfl2k5_moment_stats_build.py", "stat_ids": STATS,
            "definitions": DEFINITIONS, "sources": sources, "moments": moments}


def check_score(row, s, first, real):
    """nflverse total_*_score includes the play's own points; posteam/defteam_score are before the snap."""
    pos, de = first["posteam"], first["defteam"]
    sides = {pos: int(num(first["posteam_score"])), de: int(num(first["defteam_score"]))} if pos else {}
    want = {real[s["away"]]: s["away_score"], real[s["home"]]: s["home_score"]}
    if sides and sides != want:
        print(f"row {row}: score before the first play {sides} differs from SITU {want}", file=sys.stderr)
    return sides == want


def pfr_text(r):
    return clean(r["detail"])


def pfr_start(row, rows):
    """The moment's first play row in PFR's play-by-play, located by quarter, score and the play itself."""
    want = {14: ("4", "Montana", "8"), 15: ("4", "Kelly", None), 19: ("4", "kicks off", None),
            20: ("2", "kicks off", None), 21: ("4", None, None), 26: ("4", "Chandler", None)}[row]
    rules = {
        14: lambda r: r["quarter"] == "4" and r.get("pbp_score_aw") == "16" and r.get("pbp_score_hm") == "13"
        and r.get("location", "").endswith(" 8"),
        15: lambda r: r["quarter"] == "4" and r.get("location") == "BUF 10" and r.get("down") == "1",
        19: lambda r: r["quarter"] == "4" and "kicks off" in clean(r["detail"]) and r.get("pbp_score_hm") == "28",
        20: lambda r: r["quarter"] == "2" and "kicks off" in clean(r["detail"]) and r.get("pbp_score_aw") == "26",
        21: lambda r: r["quarter"] == "4" and r.get("location") == "GNB 49" and r.get("down") == "1"
        and r.get("pbp_score_aw") == "24" and r.get("pbp_score_hm") == "24",
        26: lambda r: r["quarter"] == "4" and r.get("location") == "ATL 29" and r.get("down") == "1",
    }
    hits = [i for i, r in enumerate(rows) if rules[row](r)]
    if not hits:
        raise SystemExit(f"row {row}: no PFR play matches the moment")
    return hits[0]


def finish_team(team, real, s):
    out = {}
    for side in ("away", "home"):
        code = real[s[side]]
        t = team.get(code, {})
        stats = {k: int(v) for k, v in t.items() if k in STATS and v}
        if "pass_yds" in stats or "pass_yds_net" in t:
            if "pass_yds_net" in t:
                stats["pass_yds"] = int(t["pass_yds_net"])
        out[side] = {"source_team": code, "stats": dict(sorted(stats.items()))}
    return out


def side_players(players, real, s):
    side_of = {real[s["away"]]: "away", real[s["home"]]: "home"}
    out = []
    for p in sorted(players, key=lambda p: (p["team"], p["name"])):
        side = side_of.get(p["team"])
        if side is None:
            continue
        q = dict(p, side=side)
        q["stats"] = {k: int(v) for k, v in q["stats"].items() if k in STATS and k not in TEAM_ONLY}
        if q["stats"]:
            out.append(q)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sources", required=True, type=Path)
    ap.add_argument("--check", action="store_true", help="rebuild and compare with the committed JSON")
    a = ap.parse_args(argv)
    doc = build(a.sources)
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    if a.check:
        same = OUT.read_text(encoding="utf-8") == text
        print("moment stats:", "unchanged" if same else "DIFFERS")
        return 0 if same else 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    seeded = [m for m in doc["moments"] if m["status"] == "seeded"]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(seeded)} seeded, {51 - len(seeded)} without play-by-play")
    return 0


if __name__ == "__main__":
    sys.exit(main())
