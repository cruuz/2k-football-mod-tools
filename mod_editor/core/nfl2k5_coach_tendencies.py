"""Observed NFL play-by-play tendencies, with explicit missing charting.

Input files remain local. Rates always retain numerators and denominators.
Native pool projection uses a declared 120-second urgency estimate; the game
computes its own estimate. It is not an exact reproduction of all clock policy.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "nfl2k5_coach_tendencies/v1"
ALIASES = {"ARZ": "ARI", "SD": "LAC", "STL": "LAR", "LA": "LAR", "OAK": "LV"}
CATEGORIES = ("run_under", "run_gun", "pass_under", "pass_gun")
CHART_COLUMNS = ("nflverse_game_id", "nflverse_play_id", "is_play_action", "is_screen_pass",
                 "n_blitzers", "n_pass_rushers", "n_defense_box", "qb_location")
PART_COLUMNS = ("nflverse_game_id", "play_id", "defense_man_zone_type", "defense_coverage_type")
COLUMNS = ("season", "season_type", "week", "game_id", "play_id", "game_date", "posteam", "defteam",
           "down", "ydstogo", "yardline_100", "score_differential", "qtr", "half_seconds_remaining",
           "game_seconds_remaining", "play_type", "no_play", "qb_kneel", "qb_spike", "qb_scramble",
           "qb_dropback", "pass_attempt", "rush_attempt", "sack", "qb_hit", "shotgun", "no_huddle",
           "air_yards", "run_location", "run_gap", "punt_attempt", "field_goal_attempt",
           "extra_point_attempt", "two_point_attempt", "home_team", "away_team", "home_coach", "away_coach")


def team(value):
    return ALIASES.get(value, value)


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def yes(row, key):
    return number(row.get(key)) == 1


def called_pass(row):
    return yes(row, "qb_dropback") or yes(row, "pass_attempt") or yes(row, "sack") or yes(row, "qb_scramble")


def scrimmage(row):
    return (not any(yes(row, k) for k in ("no_play", "qb_kneel", "qb_spike", "extra_point_attempt", "two_point_attempt"))
            and row.get("play_type") not in ("no_play", "qb_kneel", "qb_spike")
            and number(row.get("down")) in (1, 2, 3, 4)
            and (called_pass(row) or yes(row, "rush_attempt")))


def projected_pool(row):
    down, distance, zone, score, quarter, remaining = [number(row.get(k)) for k in
        ("down", "ydstogo", "yardline_100", "score_differential", "qtr", "half_seconds_remaining")]
    if None in (down, distance, zone, score, quarter, remaining):
        return None
    urgent = 0 < remaining < 120
    if score >= 0 and not urgent:
        if zone < 5 and (down < 3 or zone < 3):
            return 19
        if zone >= 95:
            return 18
    distance_bin = 0 if down <= 2 and distance < 15 else (1 if distance < 3 else 2)
    score_bin = 0 if score > 0 and quarter >= 3 else (1 if score < 0 else 2)
    return 3 * (2 * distance_bin + int(urgent)) + score_bin


def situation(row):
    d, yards, zone, score, q, clock = [number(row.get(k)) for k in
        ("down", "ydstogo", "yardline_100", "score_differential", "qtr", "half_seconds_remaining")]
    if None in (d, yards, zone, score, q, clock):
        return None
    distance = "1-2" if yards <= 2 else "3-5" if yards <= 5 else "6-10" if yards <= 10 else "11+"
    field = "own1-10" if zone >= 90 else "field" if zone > 20 else "red20-6" if zone > 5 else "goal5"
    margin = "trail9+" if score <= -9 else "trail1-8" if score < 0 else "tie" if score == 0 else "lead1-8" if score <= 8 else "lead9+"
    return f"down{int(d)}|{distance}|{field}|{margin}|half{1 if q <= 2 else 2}|{'late120' if clock <= 120 else 'normal'}"


def rate(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                rate=numerator / denominator if denominator else None)


def optional_two_point(row):
    """Retail 206E70 mandatory-try guard, projected from NFL score/half clock."""
    score, quarter, seconds = [number(row.get(k)) for k in
                                ("score_differential", "qtr", "half_seconds_remaining")]
    if None in (score, quarter, seconds):
        return False
    forced = score == -2 or (quarter in (3, 4) and seconds < 300 and score in (-10, -5, 1, 5))
    return not forced


def neutral_fourth(row):
    """Auditable optional-go projection, not the game's full kicker/clock policy.

    Native replay rejects history overrides past five yards to go or inside
    the offense's own twenty. Learning also excludes go calls in opponent
    territory. Use the own-21..49, <=5-yard, >120s subset as the measured prior.
    """
    distance, zone, clock = [number(row.get(k)) for k in
                              ("ydstogo", "yardline_100", "half_seconds_remaining")]
    return None not in (distance, zone, clock) and 0 < distance <= 5 and 50 < zone < 80 and clock > 120


def observe(counter, row):
    counter["calls"] += 1
    passed = called_pass(row)
    counter["passes"] += passed
    margin, down, distance, zone = [number(row.get(k)) for k in
                                     ("score_differential", "down", "ydstogo", "yardline_100")]
    if margin is not None:
        score = 2 if margin > 14 else 1 if margin > 7 else 0 if margin > 0 else 5 if margin == 0 else 3 if margin >= -7 else 4
        counter[f"stat_score{score}_calls"] += 1
        counter[f"stat_score{score}_runs"] += not passed
    if down in (1, 2, 3, 4) and distance is not None:
        bucket = 0 if distance <= 2 else 1 if distance <= 7 else 2 if distance <= 10 else 3
        key = f"stat_down{int(down) - 1}_distance{bucket}"
        counter[key + "_calls"] += 1
        counter[key + "_runs"] += not passed
    if zone is not None and zone <= 20:
        counter["stat_redzone_calls"] += 1
        counter["stat_redzone_runs"] += not passed
    for name in ("shotgun", "no_huddle"):
        value = number(row.get(name))
        if value in (0, 1):
            counter[name + "_known"] += 1
            counter[name] += int(value)
    gun = number(row.get("shotgun"))
    if gun in (0, 1):
        counter[("pass" if passed else "run") + ("_gun" if gun else "_under")] += 1
    if not passed:
        for name in ("run_location", "run_gap"):
            value = row.get(name)
            if value and value not in ("NA", "nan"):
                counter[name + ":" + value] += 1
                counter[name + "_known"] += 1
        location, gap = row.get("run_location"), row.get("run_gap")
        lane = ("middle" if location == "middle" else
                location + ("_outside" if gap == "end" else "_inside")
                if location in ("left", "right") and gap in ("guard", "tackle", "end") else None)
        if lane:
            counter["run_lane:" + lane] += 1
            counter["run_lane_known"] += 1
    elif yes(row, "pass_attempt") and not yes(row, "sack"):
        air = number(row.get("air_yards"))
        if air is not None:
            counter["air_known"] += 1
            counter["deep20"] += air >= 20
    if passed:
        counter["sacks"] += yes(row, "sack")
        counter["qb_hits"] += yes(row, "qb_hit")
        for key in ("is_play_action", "is_screen_pass"):
            value = number(row.get("chart_" + key))
            if value in (0, 1):
                counter[key + "_known"] += 1
                counter[key] += int(value)
        for key in ("n_blitzers", "n_pass_rushers"):
            value = number(row.get("chart_" + key))
            if value is not None and value >= 0:
                counter[key + "_known"] += 1
                counter[key + ":" + str(int(value))] += 1
                counter[key + "_positive"] += value > (0 if key == "n_blitzers" else 4)
        for key in PART_COLUMNS[2:]:
            value = row.get("part_" + key)
            if value and value not in ("NA", "nan"):
                counter[key + "_known"] += 1
                counter[key + ":" + value] += 1
        man = row.get("part_defense_man_zone_type")
        for label, field, cutoff in (("blitz", "n_blitzers", 0), ("rush5", "n_pass_rushers", 4)):
            pressure = number(row.get("chart_" + field))
            if man in ("MAN_COVERAGE", "ZONE_COVERAGE") and pressure is not None and pressure >= 0:
                counter[label + "_joint_known"] += 1
                counter[label + "_joint:" + ("man" if man == "MAN_COVERAGE" else "zone") +
                        ("_pressure" if pressure > cutoff else "_normal")] += 1
    box = number(row.get("chart_n_defense_box"))
    if box is not None and box >= 0:
        counter["box_known"] += 1
        counter["box:" + str(int(box))] += 1


def summarize(counter):
    result = dict(calls=counter["calls"], pass_rate=rate(counter["passes"], counter["calls"]),
                  shotgun=rate(counter["shotgun"], counter["shotgun_known"]),
                  no_huddle=rate(counter["no_huddle"], counter["no_huddle_known"]),
                  deep_air20=rate(counter["deep20"], counter["air_known"]),
                  play_action=rate(counter["is_play_action"], counter["is_play_action_known"]),
                  screen=rate(counter["is_screen_pass"], counter["is_screen_pass_known"]),
                  joint={k: rate(counter[k], sum(counter[x] for x in CATEGORIES)) for k in CATEGORIES})
    for key in ("run_location", "run_gap", "run_lane"):
        result[key] = {k.split(":", 1)[1]: rate(v, counter[key + "_known"])
                       for k, v in sorted(counter.items()) if k.startswith(key + ":")}
        result[key + "_unknown"] = counter["calls"] - counter["passes"] - counter[key + "_known"]
    for lane in ("left_outside", "left_inside", "middle", "right_inside", "right_outside"):
        result["run_lane"][lane] = rate(counter["run_lane:" + lane], counter["run_lane_known"])
    return result


def matches(row, intervals, side):
    season = number(row.get("season"))
    date = str(row.get("game_date", ""))[:10]
    for interval in intervals:
        if (team(row.get(side)) == interval["team"] and season is not None
                and interval["first_season"] <= season <= interval["last_season"]
                and date >= interval.get("first_date", "0000")
                and date <= interval.get("last_date", "9999")):
            return True
    return False


def read_rows(path, columns=COLUMNS):
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("Reading parquet requires pyarrow; CSV gzip needs only Python") from exc
        file = pq.ParquetFile(path)
        available = set(file.schema.names)
        for batch in file.iter_batches(batch_size=4096, columns=[k for k in columns if k in available]):
            yield from batch.to_pylist()
    else:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)


def source_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def charting_index(files, columns=CHART_COLUMNS, prefix="chart_", provider="FTN via nflverse"):
    """Join by the provider's NFL game/play keys, never by row order or names."""
    index, sources = {}, []
    for path in map(Path, files):
        rows = duplicates = 0
        for row in read_rows(path, columns):
            identity = (str(row.get(columns[0])), number(row.get(columns[1])))
            if identity[1] is None:
                raise ValueError(f"Charting lacks a play identity: {path}")
            value = {prefix + k: row.get(k) for k in columns[2:]}
            if identity in index:
                if index[identity] != value:
                    raise ValueError(f"Conflicting charting for {identity}")
                duplicates += 1
            else:
                index[identity] = value
            rows += 1
        sources.append(dict(file=path.name, sha256=source_hash(path), rows=rows,
                            duplicate_rows_ignored=duplicates,
                            provider=provider, join=f"game_id/play_id = {columns[0]}/{columns[1]}"))
    return index, sources


def build(source_files, coach_specs, charting_files=(), participation_files=()):
    """No guessed charting: unavailable features are null with a reason."""
    charting, chart_sources = charting_index(charting_files)
    participation, part_sources = charting_index(participation_files, PART_COLUMNS, "part_", "nflverse participation")
    chart_matches = set()
    part_matches = set()
    counters = {c["team"]: dict(overall=Counter(), pools=defaultdict(Counter), situations=defaultdict(Counter),
                              decisions=Counter(), fourth=defaultdict(Counter), defense=Counter(),
                              games=set(), seasons=Counter()) for c in coach_specs}
    league = Counter()
    sources, seen = [], set()
    for path in source_files:
        path = Path(path)
        dates, rows, duplicates = [], 0, 0
        for row in read_rows(path):
            if row.get("season_type") not in ("REG", "POST"):
                continue
            identity = (str(row.get("game_id")), number(row.get("play_id")))
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            if identity in charting:
                row.update(charting[identity])
                chart_matches.add(identity)
            if identity in participation:
                row.update(participation[identity])
                part_matches.add(identity)
            rows += 1
            dates.append(str(row.get("game_date", ""))[:10])
            eligible = scrimmage(row)
            if eligible:
                observe(league, row)
            for spec in coach_specs:
                c = counters[spec["team"]]
                if matches(row, spec["offense_history"], "posteam"):
                    if eligible:
                        observe(c["overall"], row)
                        index = projected_pool(row)
                        if index is not None:
                            observe(c["pools"][index], row)
                        cell = situation(row)
                        if cell is not None:
                            observe(c["situations"][cell], row)
                        c["games"].add(str(row["game_id"]))
                        c["seasons"][int(number(row["season"]))] += 1
                        q, clock, d = [number(row.get(k)) for k in ("qtr", "half_seconds_remaining", "down")]
                        tempo = number(row.get("no_huddle"))
                        if q in (1, 2) and clock is not None and clock >= 120 and d in (1, 2, 3) and tempo in (0, 1):
                            c["decisions"]["tempo_known"] += 1
                            c["decisions"]["tempo_no_huddle"] += tempo == 1
                    if not yes(row, "no_play") and row.get("play_type") != "no_play":
                        if number(row.get("down")) == 4 and (eligible or yes(row, "punt_attempt") or yes(row, "field_goal_attempt")):
                            c["decisions"]["fourth"] += 1
                            c["decisions"]["go"] += eligible
                            if neutral_fourth(row):
                                c["decisions"]["optional_fourth"] += 1
                                c["decisions"]["optional_go"] += eligible
                            cell = situation(row)
                            if cell:
                                c["fourth"][cell]["fourth"] += 1
                                c["fourth"][cell]["go"] += eligible
                        if yes(row, "extra_point_attempt") or yes(row, "two_point_attempt"):
                            c["decisions"]["tries"] += 1
                            c["decisions"]["two"] += yes(row, "two_point_attempt")
                            if optional_two_point(row):
                                c["decisions"]["optional_tries"] += 1
                                c["decisions"]["optional_two"] += yes(row, "two_point_attempt")
                if eligible and matches(row, spec["defense_history"], "defteam"):
                    observe(c["defense"], row)
        sources.append(dict(file=path.name, sha256=source_hash(path), rows=rows, duplicate_rows_ignored=duplicates,
                            first_game=min(dates) if dates else None, last_game=max(dates) if dates else None))
    results = []
    for spec in coach_specs:
        c = counters[spec["team"]]
        pools = []
        for index in range(20):
            raw = c["pools"][index]
            chosen, fallback = raw, None
            if sum(raw[k] for k in CATEGORIES) < 32:
                chosen, fallback = c["overall"], "coach_overall_fewer_than_32_joint_observations"
            if not sum(chosen[k] for k in CATEGORIES):
                chosen, fallback = league, "league_no_coach_offense_observations"
            denominator = sum(chosen[k] for k in CATEGORIES)
            if not denominator:
                raise ValueError("No usable pass/shotgun observations")
            pools.append(dict(index=index, observations=summarize(raw), fallback=fallback,
                              target_denominator=denominator,
                              joint={k: chosen[k] / denominator for k in CATEGORIES}))
        defense = c["defense"]
        overall = c["overall"]
        native_stats = dict(pass_calls=overall["passes"], run_calls=overall["calls"] - overall["passes"],
                            score=[rate(overall[f"stat_score{i}_runs"], overall[f"stat_score{i}_calls"]) for i in range(6)],
                            redzone=rate(overall["stat_redzone_runs"], overall["stat_redzone_calls"]),
                            down_distance=[rate(overall[f"stat_down{d}_distance{b}_runs"],
                                                overall[f"stat_down{d}_distance{b}_calls"])
                                           for d in range(4) for b in range(4)],
                            distance_bins="<=2,3..7,8..10,11+ yards; four rows for downs1..4",
                            score_bins="lead1..7,lead8..14,lead15+,trail1..7,trail8+,tie")
        results.append(dict(schema=SCHEMA, team=spec["team"], coach=spec["coach"], provenance=spec,
                            sources=sources, charting_sources=chart_sources, participation_sources=part_sources,
                            charting_join=dict(available_unique_rows=len(charting), matched_pbp_rows=len(chart_matches),
                                               unmatched_chart_rows=len(charting) - len(chart_matches)),
                            participation_join=dict(available_unique_rows=len(participation), matched_pbp_rows=len(part_matches),
                                                    unmatched_rows=len(participation) - len(part_matches)),
                            games=len(c["games"]), season_calls=dict(sorted(c["seasons"].items())),
                            overall=summarize(c["overall"]),
                            native_statistics=native_stats,
                            situations={k: summarize(v) for k, v in sorted(c["situations"].items())},
                            fourth_down=rate(c["decisions"]["go"], c["decisions"]["fourth"]),
                            fourth_down_situations={k: rate(v["go"], v["fourth"]) for k, v in sorted(c["fourth"].items())},
                            two_point=rate(c["decisions"]["two"], c["decisions"]["tries"]),
                            native_decision_projections=dict(
                                fourth_down=rate(c["decisions"]["optional_go"], c["decisions"]["optional_fourth"]),
                                fourth_down_scope="Fourth-and-1..5, own21..49, more than 120 half seconds; excludes opponent territory; native kicker/clock policy remains active",
                                two_point=rate(c["decisions"]["optional_two"], c["decisions"]["optional_tries"]),
                                two_point_scope="Exclude attempts where native 206E70 mandates two; native mandates can differ from NFL choices",
                                no_huddle=rate(c["decisions"]["tempo_no_huddle"], c["decisions"]["tempo_known"]),
                                no_huddle_scope="Q1/Q2, down1..3, >=120 half seconds; native personnel/stoppage gates are additional restrictions"),
                            play_action=rate(c["overall"]["is_play_action"], c["overall"]["is_play_action_known"]),
                            screen=rate(c["overall"]["is_screen_pass"], c["overall"]["is_screen_pass_known"]),
                            defense=dict(calls=defense["calls"], opponent_pass_rate=rate(defense["passes"], defense["calls"]),
                                         sack_rate=rate(defense["sacks"], defense["passes"]),
                                         qb_hit_rate=rate(defense["qb_hits"], defense["passes"]),
                                         blitz=rate(defense["n_blitzers_positive"], defense["n_blitzers_known"]),
                                         rush_five_plus=rate(defense["n_pass_rushers_positive"], defense["n_pass_rushers_known"]),
                                         box_count={k.split(":")[1]: rate(v, defense["box_known"])
                                                    for k, v in sorted(defense.items()) if k.startswith("box:")},
                                         man=rate(defense["defense_man_zone_type:MAN_COVERAGE"],
                                                  defense["defense_man_zone_type_known"]),
                                         coverage={k.split(":")[1]: rate(v, defense["defense_coverage_type_known"])
                                                   for k, v in sorted(defense.items()) if k.startswith("defense_coverage_type:")},
                                         man_blitz_joint={k: rate(defense["blitz_joint:" + k], defense["blitz_joint_known"])
                                                          for k in ("man_normal", "man_pressure", "zone_normal", "zone_pressure")},
                                         man_rush5_joint={k: rate(defense["rush5_joint:" + k], defense["rush5_joint_known"])
                                                          for k in ("man_normal", "man_pressure", "zone_normal", "zone_pressure")}),
                            native_offense_pools=pools,
                            limitations=["120-second urgency projection; native estimated needed time varies",
                                         "Observed thrown depth is not called route depth",
                                         "FTN charting covers only matched plays from 2022 onward; unknowns are excluded from each feature denominator",
                                         "Coverage charting covers matched 2022–2025 plays; coaches with no defense history in those seasons have no coverage estimate",
                                         "HC team offense is not necessarily personally called by the HC",
                                         "NFL guard/tackle gaps merge into native inside lanes; exact observed run gaps and thrown air depth cannot be reproduced by called-play proxies",
                                         "2026 input ends 2026-10-05; team/role intervals override stale coach labels"]))
    return results
