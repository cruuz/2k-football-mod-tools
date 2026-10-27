#!/usr/bin/env python3
"""b778 / rt1: 2026 QBs' Throw Power from multi-season arm evidence; Read and Consistency from a career anchor.

Noah (2026-10-22): "I also wonder if Mahomes' rating is too low. I feel like a lot of quarterbacks need higher throw
power ratings. I updated Cam Ward's in my franchise, but I feel like it should be scaled across the league."

Two layers, both QB-only:

1. The order and the overall (this tool, on the 2026 league's roster-edits document). The r1 ratings
   (``tools/ratings_v2``, r1-ratings-v2.4) read Throw Power from 2024-25 only, 30% of it from deep EPA (what the
   offense made of deep balls, not the arm) and with the honours floor (a Pro Bowl lifts every measured rating, the
   arm too). So Darnold, Maye, Love and Prescott share Allen's arm and Mahomes sits below Bo Nix. Here each QB with
   NFL tracking data gets an arm EVIDENCE score from 2021-2025 (five seasons; play-by-play weighted toward 2025),
   physical measures only:

     long   0.60  his three longest weekly NGS max air distances (how far the ball actually travelled in the air;
                  nflverse ngs_passing, weeks 2021-2025, regular season and playoffs), shrunk toward the league by
                  his number of NGS weeks (k = 6 weeks)
     depth  0.25  mean air yards of his completions thrown 20+ air yards (nflverse play-by-play 2022-2025), shrunk
                  toward the league (k = 15 completions)
     rate   0.15  share of his attempts thrown 20+ air yards (same seasons, k = 150 attempts)

   Only QBs with a full season of tracking (17+ NGS weeks) are moved; with less, the arm keeps r1's value (a rookie's
   handful of long throws says more about his offense than his arm). Each measure is a z-score over those QBs; the
   score's rank reads a value off the same QBs' current Throw Power, sorted, so the scale is the one the league already
   has. The new value blends it with the current one by how much tracking he has, ``w = 0.6 * weeks / (weeks + 16)``
   (a veteran with 90 NGS weeks moves about half way), and moves at most 8 points:
   ``new = round(clamp(w * evidence + (1 - w) * current, current - 8, current + 8))``.

   The QB overall (the game's own formula, FUN_00246D90: 40% accuracy, 40% arm, 10% read, 10% composure, minus a
   consistency penalty) also gets a career anchor where a QB has one: passing EPA per dropback over 2018-2025 (nflverse
   stats_player_reg; seasons weighted 0.1 .. 1.0 toward 2025, shrunk by k = 300 dropbacks). Only QBs with 200+
   dropbacks before 2024 (a career beyond r1's two seasons) are anchored. Their career rank reads a value off the
   anchored QBs' current Read Coverage and Consistency, averaged 50/50 with the current value, and is a FLOOR: it
   lifts an established passer after a down year and never lowers anyone. Pass accuracy is not touched (job qa1
   owns it).

2. The level (the ``qb_throw_power`` directive the build applies last, ``nfl2k5_qb_throw_power.B778_CURVE``): every
   QB record of every roster, the rookie templates included, through one monotone, capped curve.

The values this tool writes are on the source scale (what the roster-edits document holds); the curve maps them to the
game's scale at build time. Inputs are public nflverse files (CC-BY 4.0) and the user's own disc; nothing else.

  python3 tools/b778/rt1_qb_ratings.py run --disc RELEASED.iso --retail RETAIL.iso --edits LEAGUE.json \
      --nflverse DIR [--nflverse DIR ...] --out-edits NEW.json --receipt RECEIPT.json
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_qb_throw_power as qp  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core.nfl2k5_ratings_model import name_key  # noqa: E402

SCHEMA = "b778/rt1_qb_ratings/v1"
QB = 0
ARM, READ, ACC, CONS = "pass_arm_strength", "pass_read_coverage", "pass_accuracy", "consistency"
CAREER_FIELDS = (READ, CONS)
FIELDS = (ARM, READ, ACC, CONS)
WRITTEN = (ARM, READ, CONS)
# arm evidence
NGS_SEASONS = (2021, 2022, 2023, 2024, 2025)
PBP_SEASONS = (2022, 2023, 2024, 2025)
PBP_WEIGHT = {2025: 1.0, 2024: 0.8, 2023: 0.6, 2022: 0.4}
DEEP_AIR_YARDS = 20.0
ARM_WEIGHTS = {"long": 0.60, "depth": 0.25, "rate": 0.15}
SHRINK = {"long": 6.0, "depth": 15.0, "rate": 150.0}
TOP_WEEKS = 3
REGULAR_WEEKS = 17          # a full season of tracked games: less than that, the arm keeps r1's value
TRUST_MAX, TRUST_K = 0.6, 16.0
MAX_MOVE = 8                # the evidence moves a source value at most this far
# read career anchor
CAREER_WEIGHT = {2025: 1.0, 2024: 0.8, 2023: 0.6, 2022: 0.45, 2021: 0.3, 2020: 0.2, 2019: 0.15, 2018: 0.1}
CAREER_K = 300.0
CAREER_MIN_EARLY_DROPBACKS = 200.0
READ_BLEND = 0.5


class Rt1Error(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise Rt1Error(message)


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path) -> list[dict]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_csv(path, columns: Sequence[str]) -> Iterable[dict]:
    """Large files (play-by-play): only the named columns, row by row."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        at = {name: header.index(name) for name in columns}
        for row in reader:
            yield {name: row[i] if i < len(row) else "" for name, i in at.items()}


# ------------------------------------------------------------------------------------------------ evidence
def long_throws(ngs_rows: Iterable[Mapping], seasons: Sequence[int] = NGS_SEASONS) -> dict[str, dict]:
    """{gsis: {"top": mean of the TOP_WEEKS longest weekly max air distances, "weeks": n, "longest": max}} from NGS
    weekly passing rows (week 0, the season row, is skipped)."""
    weeks = collections.defaultdict(list)
    for row in ngs_rows:
        season = int(_num(row.get("season")) or 0)
        distance = _num(row.get("max_air_distance"))
        if season not in seasons or str(row.get("week")) in ("0", "") or distance is None or not row.get("player_gsis_id"):
            continue
        weeks[row["player_gsis_id"]].append(distance)
    out = {}
    for gsis, values in weeks.items():
        values.sort(reverse=True)
        top = values[:TOP_WEEKS]
        out[gsis] = {"top": round(sum(top) / len(top), 4), "weeks": len(values), "longest": round(values[0], 3)}
    return out


def deep_passing(pbp_rows: Iterable[Mapping], season: int, into: dict | None = None) -> dict[str, dict]:
    """Season-weighted deep counts per passer from play-by-play rows (pass attempts with air yards, sacks excluded)."""
    out = into if into is not None else {}
    weight = PBP_WEIGHT[season]
    for row in pbp_rows:
        if row.get("pass_attempt") != "1" or row.get("sack") == "1" or row.get("season_type") not in ("REG", "POST"):
            continue
        air = _num(row.get("air_yards"))
        gsis = row.get("passer_player_id") or ""
        if air is None or not gsis:
            continue
        d = out.setdefault(gsis, {"att": 0.0, "deep": 0.0, "deep_cmp": 0.0, "deep_cmp_air": 0.0})
        d["att"] += weight
        if air >= DEEP_AIR_YARDS:
            d["deep"] += weight
            if row.get("complete_pass") == "1":
                d["deep_cmp"] += weight
                d["deep_cmp_air"] += weight * air
    return out


def career_epa(stats_by_season: Mapping[int, Iterable[Mapping]]) -> dict[str, dict]:
    """{gsis: {"epa": weighted passing EPA, "db": weighted dropbacks, "early_db": raw dropbacks before 2024}}."""
    out: dict[str, dict] = {}
    for season, rows in stats_by_season.items():
        weight = CAREER_WEIGHT.get(int(season))
        if weight is None:
            continue
        for row in rows:
            if row.get("season_type", "REG") not in ("REG", ""):
                continue
            gsis = row.get("player_id") or ""
            dropbacks = (_num(row.get("attempts")) or 0.0) + (_num(row.get("sacks_suffered")) or 0.0)
            epa = _num(row.get("passing_epa"))
            if not gsis or dropbacks <= 0 or epa is None:
                continue
            d = out.setdefault(gsis, {"epa": 0.0, "db": 0.0, "early_db": 0.0, "seasons": []})
            d["epa"] += weight * epa
            d["db"] += weight * dropbacks
            d["seasons"].append(int(season))
            if int(season) < 2024:
                d["early_db"] += dropbacks
    return out


def _z(values: Sequence[float]) -> tuple[float, float]:
    mean = statistics.mean(values)
    sd = statistics.pstdev(values) or 1.0
    return mean, sd


def percentile_ranks(values: Sequence[float]) -> list[float]:
    """Mid-rank percentile of each value (ties share), 0..1."""
    order = sorted(values)
    n = len(order)
    out = []
    for v in values:
        lo = sum(1 for x in order if x < v)
        eq = sum(1 for x in order if x == v)
        out.append((lo + 0.5 * eq) / n)
    return out


def quantile(sorted_values: Sequence[float], q: float) -> float:
    q = min(1.0, max(0.0, q))
    at = q * (len(sorted_values) - 1)
    low = int(math.floor(at))
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (at - low)


def arm_plan(qbs: Sequence[Mapping], long: Mapping[str, Mapping], deep: Mapping[str, Mapping]) -> dict[str, dict]:
    """New source-scale Throw Power for every QB with tracking evidence. ``qbs``: dicts with ``key``, ``gsis`` and
    ``arm`` (current source value). Returns {key: {"arm": new, "evidence": ..., "w": ...}}."""
    have = [q for q in qbs if q.get("gsis") and long.get(q["gsis"], {}).get("weeks", 0) >= REGULAR_WEEKS]
    if not have:
        return {}
    regular = have
    league_long = statistics.mean(long[q["gsis"]]["top"] for q in regular)
    tot = {k: sum(deep.get(q["gsis"], {}).get(k, 0.0) for q in regular) for k in ("att", "deep", "deep_cmp", "deep_cmp_air")}
    league_depth = tot["deep_cmp_air"] / tot["deep_cmp"] if tot["deep_cmp"] else 0.0
    league_rate = tot["deep"] / tot["att"] if tot["att"] else 0.0
    shrunk = {}
    for q in have:
        lt, d = long[q["gsis"]], deep.get(q["gsis"], {})
        shrunk[q["key"]] = {
            "long": (lt["top"] * lt["weeks"] + league_long * SHRINK["long"]) / (lt["weeks"] + SHRINK["long"]),
            "depth": (d.get("deep_cmp_air", 0.0) + league_depth * SHRINK["depth"]) / (d.get("deep_cmp", 0.0) + SHRINK["depth"]),
            "rate": (d.get("deep", 0.0) + league_rate * SHRINK["rate"]) / (d.get("att", 0.0) + SHRINK["rate"]),
        }
    scale = {k: _z([shrunk[q["key"]][k] for q in regular]) for k in ARM_WEIGHTS}
    score = {key: sum(ARM_WEIGHTS[k] * (s[k] - scale[k][0]) / scale[k][1] for k in ARM_WEIGHTS) for key, s in shrunk.items()}
    keys = [q["key"] for q in have]
    ranks = dict(zip(keys, percentile_ranks([score[k] for k in keys])))
    current_scale = sorted(float(q["arm"]) for q in have)
    out = {}
    for q in have:
        weeks = long[q["gsis"]]["weeks"]
        evidence = quantile(current_scale, ranks[q["key"]])
        w = TRUST_MAX * weeks / (weeks + TRUST_K)
        blend = w * evidence + (1 - w) * q["arm"]
        new = int(round(max(q["arm"] - MAX_MOVE, min(q["arm"] + MAX_MOVE, blend))))
        out[q["key"]] = {"arm": max(0, min(rr.RATING_MAX, new)), "blend": round(blend, 2), "evidence_value": round(evidence, 2),
                         "w": round(w, 3), "score": round(score[q["key"]], 3), "rank": round(ranks[q["key"]], 3),
                         "long_top3_yd": long[q["gsis"]]["top"], "longest_yd": long[q["gsis"]]["longest"],
                         "ngs_weeks": weeks, "shrunk": {k: round(v, 4) for k, v in shrunk[q["key"]].items()}}
    return out


def career_plan(qbs: Sequence[Mapping], career: Mapping[str, Mapping]) -> dict[str, dict]:
    """New Read Coverage and Consistency floors for QBs with a career before 2024 (see the module doc)."""
    have = [q for q in qbs if q.get("gsis") and career.get(q["gsis"], {}).get("early_db", 0.0) >= CAREER_MIN_EARLY_DROPBACKS]
    if not have:
        return {}
    prior = sum(career[q["gsis"]]["epa"] for q in have) / sum(career[q["gsis"]]["db"] for q in have)
    value = {q["key"]: (career[q["gsis"]]["epa"] + prior * CAREER_K) / (career[q["gsis"]]["db"] + CAREER_K) for q in have}
    keys = [q["key"] for q in have]
    ranks = dict(zip(keys, percentile_ranks([value[k] for k in keys])))
    scales = {name: sorted(float(q["current"][name]) for q in have) for name in CAREER_FIELDS}
    out = {}
    for q in have:
        row = {"career_epa_per_db": round(value[q["key"]], 4), "rank": round(ranks[q["key"]], 3),
               "seasons": sorted(career[q["gsis"]]["seasons"]), "anchor_value": {}}
        for name in CAREER_FIELDS:
            anchor = quantile(scales[name], ranks[q["key"]])
            # a floor: the career keeps an established passer from being judged on two seasons; it never lowers one
            new = max(int(q["current"][name]), int(round(READ_BLEND * anchor + (1 - READ_BLEND) * q["current"][name])))
            row[name] = max(0, min(rr.RATING_MAX, new))
            row["anchor_value"][name] = round(anchor, 2)
        out[q["key"]] = row
    return out


# ------------------------------------------------------------------------------------------------ roster side
def match_gsis(players_rows: Iterable[Mapping], first: str, last: str, birth: str = "") -> tuple[str, str]:
    """(gsis, how) for a QB by name (``name_key``) among nflverse players at QB; a birth date breaks a tie."""
    key = name_key(f"{first} {last}")
    hits = [r for r in players_rows if r.get("position") == "QB" and name_key(r.get("display_name", "")) == key]
    if birth:
        dated = [r for r in hits if (r.get("birth_date") or "")[:10] == birth]
        if dated:
            hits = dated
    if not hits:
        return "", "no nflverse QB of that name"
    hits.sort(key=lambda r: (int(_num(r.get("last_season")) or 0), r.get("gsis_id", "")), reverse=True)
    return hits[0]["gsis_id"], "name" + (" + birth date" if birth else "") + (f" (latest of {len(hits)})" if len(hits) > 1 else "")


def source_values(edits: Mapping, retail_doc, keys: Iterable[tuple[str, int]]) -> dict[tuple[str, int], dict]:
    """The document's own value of each field per record (last edit wins, else retail) and the record's name as the
    document leaves it before the build's later passes (membership moves do not change a record's identity)."""
    want = set(keys)
    state = {}
    for p in retail_doc.players:
        if (p.pool, p.index) in want:
            v = p.record.values
            state[(p.pool, p.index)] = {"first": p.first, "last": p.last, **{n: v[n] for n in FIELDS},
                                        "position": v["position"]}
    for entry in edits.get("edits", []):
        key = (str(entry.get("pool", "primary")), int(entry.get("index", -1)))
        if key not in state:
            continue
        for name in (*FIELDS, "position"):
            if name in (entry.get("fields") or {}):
                state[key][name] = int(entry["fields"][name])
        for which in ("first", "last"):
            if which in (entry.get("names") or {}):
                state[key][which] = entry["names"][which]
    return state


def plan_league(disc_doc, retail_doc, edits: Mapping, players_rows: Sequence[Mapping], long, deep, career,
                guards: Mapping[int, str] | None = None) -> list[dict]:
    """One row per rated QB record of the released main roster: identity, the document's source values, the new
    source values (or unchanged) and why."""
    # record moves (``moves``) change team membership only, never which record holds a player, so they do not matter here
    rows = []
    for p in disc_doc.players:
        v = p.record.values
        if v["position"] != QB or p.pool != "primary" or not any(v[n] for n in rr.RATING_BYTE_ORDER):
            continue
        rows.append({"key": f"{p.pool}:{p.index}", "pool": p.pool, "index": p.index, "first": p.first, "last": p.last,
                     "team": (disc_doc.teams[p.teams[0]].abbreviation if p.teams and p.teams[0] < 32 else "FA/other"),
                     "disc": {n: v[n] for n in FIELDS}})
    state = source_values(edits, retail_doc, [(r["pool"], r["index"]) for r in rows])
    directive = qp.directive_of(edits) or {"add": 0, "cap": rr.RATING_MAX, "scope": "all"}
    for row in rows:
        s = state.get((row["pool"], row["index"]))
        if s is None:
            # a record the retail roster does not have (spare capacity a later pass adds): the document cannot set it;
            # its source arm is what the old directive turned into the disc's value
            s = {"first": "", "last": "", "position": -1, **row["disc"]}
            s[ARM] = qp.source_for(row["disc"][ARM], directive)
        if (s["first"], s["last"]) != (row["first"], row["last"]):
            # the document's record holds someone else before the build's later passes (a modern free agent written
            # into a retail spare): left alone, its source arm estimated the same way
            s = {**s, **row["disc"], ARM: qp.source_for(row["disc"][ARM], directive)}
        row["source"] = {n: s[n] for n in FIELDS}
        row["doc_name"] = f"{s['first']} {s['last']}"
        # the edits document must explain the released disc: same name, accuracy and read, arm through the directive
        row["explained"] = (s["first"], s["last"]) == (row["first"], row["last"]) and s["position"] == QB and \
            all(row["disc"][n] == s[n] for n in (READ, ACC, CONS)) and \
            row["disc"][ARM] == qp.map_value(s[ARM], directive)
        birth = (guards or {}).get(row["index"], "")
        row["gsis"], row["match"] = match_gsis(players_rows, row["first"], row["last"], birth) if row["explained"] else ("", "not explained by the document: left alone")
        row["arm"], row["current"] = s[ARM], dict(row["source"])
    eligible = [r for r in rows if r["explained"] and r["gsis"]]
    arms = arm_plan(eligible, long, deep)
    careers = career_plan(eligible, career)
    for row in rows:
        a, c = arms.get(row["key"]), careers.get(row["key"])
        row["new"] = {**row["source"], ARM: a["arm"] if a else row["arm"]}
        for name in CAREER_FIELDS:
            row["new"][name] = c[name] if c else row["source"][name]
        row["arm_basis"] = a
        row["career_basis"] = c
    return rows


def edit_entries(rows: Sequence[Mapping]) -> list[dict]:
    """The roster-edits layer: one entry per QB whose arm or read changes, named as the document leaves the record."""
    out = []
    for row in rows:
        fields = {name: row["new"][name] for name in WRITTEN if row["new"][name] != row["source"][name]}
        if fields:
            out.append({"pool": row["pool"], "index": row["index"], "first": row["first"], "last": row["last"],
                        "fields": dict(sorted(fields.items()))})
    return out


def merged_document(edits: Mapping, entries: Sequence[Mapping], curve) -> dict:
    out = {key: (list(value) if isinstance(value, list) else value) for key, value in edits.items()}
    out["edits"] = list(edits["edits"]) + list(entries)
    out[qp.DIRECTIVE_KEY] = qp.normalise_directive({"curve": [list(p) for p in curve], "cap": rr.RATING_MAX, "scope": "all"})
    out["name"] = str(edits.get("name", "")) + " + b778 rt1 QB arm evidence and career read, Throw Power curve"
    return out


class _Raw:
    def __init__(self, raw: bytes):
        self.raw = raw

    def encode(self) -> bytes:
        return self.raw


def game_overall(raw: bytes) -> int:
    """The game's own displayed overall (FUN_00246D90, ``nfl2k5_my_career_prospects.native_overall``)."""
    from mod_editor.core.nfl2k5_my_career_prospects import native_overall
    return native_overall(_Raw(raw))


# ------------------------------------------------------------------------------------------------ CLI
def find(dirs: Sequence[Path], name: str) -> Path:
    for d in dirs:
        if (Path(d) / name).exists():
            return Path(d) / name
    raise Rt1Error(f"{name} is in none of {', '.join(map(str, dirs))}")


def cmd_run(args) -> int:
    dirs = [Path(d) for d in args.nflverse]
    inputs = {}
    def use(name):
        path = find(dirs, name)
        inputs[name] = {"path": str(path), "sha256": sha256(path)}
        return path
    players = [r for r in read_csv(use("players.csv.gz")) if r.get("position") == "QB"]
    long = long_throws(read_csv(use("ngs_passing.csv.gz")))
    deep: dict = {}
    for season in PBP_SEASONS:
        deep_passing(iter_csv(use(f"play_by_play_{season}.csv.gz"),
                              ("pass_attempt", "sack", "season_type", "air_yards", "passer_player_id", "complete_pass")),
                     season, deep)
    career = career_epa({season: read_csv(use(f"stats_player_reg_{season}.csv.gz")) for season in CAREER_WEIGHT})
    edits = json.loads(Path(args.edits).read_text(encoding="utf-8"))
    inputs["edits"] = {"path": str(args.edits), "sha256": sha256(args.edits)}
    disc_doc = rr.load_image(args.disc)
    retail_doc = rr.load_image(args.retail)
    guards = {int(g[0]): str(g[3])[:10] for g in (edits.get("roster_refresh") or {}).get("identity_guards", [])
              if isinstance(g, list) and len(g) >= 4}
    rows = plan_league(disc_doc, retail_doc, edits, players, long, deep, career, guards)
    entries = edit_entries(rows)
    merged = merged_document(edits, entries, qp.B778_CURVE)
    # the layer replays cleanly on the released roster (names guard every entry) and touches only arm and read
    # refresh_follows: the released roster is judged by its own refresh pass, not by this field-only layer
    body, receipt = rr.apply_body(disc_doc.to_body(), {"schema": rr.EDITS_SCHEMA, "edits": entries}, refresh_follows=True)
    _require(not receipt["log"], f"the QB layer does not replay on the released roster: {receipt['log'][:3]}")
    after = {(p.pool, p.index): p.record.values for p in rr.RosterDocument(body).players}
    before = {(p.pool, p.index): p.record.values for p in disc_doc.players}
    for key, values in after.items():
        diff = {n for n in rr.RATING_BYTE_ORDER if values[n] != before[key][n]}
        _require(diff <= set(WRITTEN), f"{key}: unexpected fields {sorted(diff)}")
    directive = qp.normalise_directive(merged[qp.DIRECTIVE_KEY])
    records = {(p.pool, p.index): p.record for p in disc_doc.players}
    for row in rows:
        row["game"] = {**row["new"], ARM: qp.map_value(row["new"][ARM], directive)}
        raw = bytearray(records[(row["pool"], row["index"])].encode())
        row["overall_disc"] = game_overall(bytes(raw))
        raw[rr.RATING_OFFSETS[ARM]] = row["game"][ARM]
        for name in (READ, CONS):
            raw[rr.RATING_OFFSETS[name]] = row["game"][name]
        row["overall_new"] = game_overall(bytes(raw))
    Path(args.out_edits).write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    out = {"schema": SCHEMA, "inputs": inputs, "disc": {"path": str(args.disc)}, "retail": {"path": str(args.retail)},
           "out_edits": {"path": str(args.out_edits), "sha256": sha256(args.out_edits), "entries_added": len(entries)},
           "directive": directive, "rows": rows,
           "method": {"arm_weights": ARM_WEIGHTS, "shrink": SHRINK, "trust": [TRUST_MAX, TRUST_K], "ngs_seasons": NGS_SEASONS,
                      "pbp_weights": PBP_WEIGHT, "career_weights": CAREER_WEIGHT, "career_k": CAREER_K,
                      "career_min_early_dropbacks": CAREER_MIN_EARLY_DROPBACKS, "read_blend": READ_BLEND}}
    Path(args.receipt).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"qbs": len(rows), "arm_changed": sum(1 for r in rows if r["new"][ARM] != r["source"][ARM]),
                      "read_changed": sum(1 for r in rows if r["new"][READ] != r["source"][READ]),
                      "consistency_changed": sum(1 for r in rows if r["new"][CONS] != r["source"][CONS]),
                      "entries": len(entries), "out_edits": out["out_edits"]}, indent=1))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--disc", required=True)
    run.add_argument("--retail", required=True)
    run.add_argument("--edits", required=True)
    run.add_argument("--nflverse", action="append", required=True)
    run.add_argument("--out-edits", required=True)
    run.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
