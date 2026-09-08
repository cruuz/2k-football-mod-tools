#!/usr/bin/env python3
"""Offline, deterministic ESPN 25th roster generation and full 75-file inventory.

Source: user-supplied nflverse-data season CSVs, CC-BY-4.0, same attribution
as nfl2k5_team_history_from_nflverse.py. No downloads or game execution.
The supplied PFR box scores and season rosters establish starter identities.
Missing fixed-role reserves and shared-file conflicts remain explicit.
Use --check to regenerate in temporary storage and compare every output byte.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "tools"):
    sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_team_history as th

DEFAULT_RETAIL = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
DEFAULT_INPUT = ROOT / "inputs/nflverse_rosters"
SELECTORS = {
    "49ers": "SF", "bears": "CHI", "bengals": "CIN", "bills": "BUF", "broncos": "DEN",
    "browns": "CLE", "buccaneers": "TB", "cardinals": "ARZ", "chargers": "SD", "chiefs": "KC",
    "colts": "IND", "cowboys": "DAL", "dolphins": "MIA", "eagles": "PHI", "falcons": "ATL",
    "giants": "NYG", "jaguars": "JAX", "jets": "NYJ", "lions": "DET", "packers": "GB",
    "panthers": "CAR", "patriots": "NE", "raiders": "OAK", "rams": "STL", "ravens": "BAL",
    "redskins": "WAS", "saints": "NO", "seahawks": "SEA", "steelers": "PIT", "oilers": "TEN",
    "titans": "TEN", "vikings": "MIN",
}
SOURCE_COLUMNS = ("season", "team", "position", "depth_chart_position", "jersey_number", "status",
                  "full_name", "first_name", "last_name", "birth_date", "college", "years_exp",
                  "entry_year", "rookie_year", "draft_club", "draft_round", "draft_number", "games_started")
FAMILY = {p: group for group, positions in rr.POSITION_GROUPS.items() for p in positions}
ALIASES = {"RB": ("HB", "FB"), "HB": ("HB",), "FB": ("FB",), "OT": ("T",),
           "OG": ("G",), "OL": ("C", "G", "T"), "LS": ("C",), "NT": ("DT",),
           "DL": ("DT", "DE"), "LB": ("OLB", "ILB"), "MLB": ("ILB",),
           "DB": ("CB", "FS", "SS"), "SAF": ("FS", "SS"), "S": ("FS", "SS"),
           "E": ("WR", "TE")}
STATUS_ORDER = {"ACT": 0, "RES": 1, "PUP": 2, "SUS": 3, "TRD": 4, "TRT": 4,
                "TRC": 4, "TRL": 4, "CUT": 5, "RET": 6, "NWT": 6, "": 7}
INF = 10**15
# Editorial corrections after reviewing the weak tenure heuristic. These are
# explicitly HYPOTHESIS, not game-start evidence from nflverse. The generator
# requires each exact name to exist in this team's chosen season and QB role.
# A long-serving backup must not silently become an asserted historical starter.
QB_PREFERENCES = {
    ("OAK", 1968): "Daryle Lamonica",
    ("SD", 1981): "Dan Fouts",
    ("KC", 1992): "Dave Krieg",
}


def norm(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if c.isalnum())


def number(value):
    try:
        v = float(value)
        return int(v) if v.is_integer() else 0
    except (ValueError, TypeError):
        return 0


def franchise(code, year):
    # LA is the Rams throughout the supplied LA rows (1961..1981). Raiders
    # move years use RAI; keep this source-specific resolution out of the shared
    # generic resolver, which correctly refuses ambiguous caller-supplied LA.
    if code == "LA":
        e.require(1961 <= year <= 1981, "unexpected ambiguous LA source code")
        return "STL"
    if code in ("BOS", "COW", "CHR", "NYT", "TEX"):
        return {"BOS": "NE", "COW": "DAL", "CHR": "SD", "NYT": "NYJ", "TEX": "KC"}[code]
    return th.resolve_team(code, year)[0]


def display_parts(row):
    full, last = row["full_name"].strip(), row["last_name"].strip()
    if full.casefold().endswith(" " + last.casefold()):
        first = full[:-len(last)].strip()
    else:
        first, _, last = full.partition(" ")
    e.require(first and last, "source has no complete display name")
    # Do not shorten/invent a name to make it fit. This source's selected
    # identities must pass the existing 15-character roster name validator.
    rr.validate_name(first)
    rr.validate_name(last)
    return first, last


def name_fits(row):
    try:
        display_parts(row)
        return True
    except rr.RosterRecordError:
        return False


class Source:
    def __init__(self, folder):
        self.by_team = defaultdict(list)
        self.by_identity = defaultdict(list)
        self.files, self.rows, self.nonempty, self.columns = [], [], Counter(), set()
        for year in range(1960, 2005):
            path = Path(folder) / f"roster_{year}.csv"
            raw = e.read_bounded(path, 2 * 1024 * 1024)
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            self.columns.update(reader.fieldnames)
            count = 0
            for line, row in enumerate(reader, 2):
                e.require(number(row["season"]) == year, "source season does not match filename")
                r = {k: row.get(k, "") for k in SOURCE_COLUMNS}
                r.update(source_file=path.name, source_line=line, season=year,
                         franchise=franchise(row["team"], year))
                r["identity"] = "|".join(norm(r[k]) for k in ("first_name", "last_name", "birth_date"))
                self.by_team[r["franchise"]].append(r)
                self.by_identity[r["identity"]].append(r)
                self.rows.append(r)
                self.nonempty.update(k for k, v in row.items() if v and v != "0")
                count += 1
            self.files.append({"file": path.name, "sha256": e.sha(raw), "rows": count})

    def jersey(self, row, selected_season):
        v = number(row["jersey_number"])
        if 1 <= v <= 99:
            return v, {"basis": "source_row", "file": row["source_file"], "line": row["source_line"]}
        # A jersey from a different season is evidence of that other season only.
        candidates = [r for r in self.by_identity[row["identity"]]
                      if r["franchise"] == row["franchise"] and 1 <= number(r["jersey_number"]) <= 99]
        if candidates:
            r = min(candidates, key=lambda r: (abs(r["season"] - selected_season), r["season"], r["source_line"]))
            return number(r["jersey_number"]), {"basis": "other_season_same_player_same_franchise",
                    "file": r["source_file"], "line": r["source_line"]}
        return None, {"basis": "retail_slot_unknown_historical_number"}

    def candidates(self, team, season):
        # All same-franchise years are eligible only as explicitly marked role
        # fillers. Assignment lexicographically prefers the selected season,
        # then the nearest source year. No player is borrowed from another club.
        chosen = {}
        for r in self.by_team[team]:
            if not name_fits(r):
                continue
            key = r["identity"]
            old = chosen.get(key)
            if old is None or (abs(r["season"] - season), STATUS_ORDER.get(r["status"], 7), r["season"], r["source_line"]) < (
                    abs(old["season"] - season), STATUS_ORDER.get(old["status"], 7), old["season"], old["source_line"]):
                chosen[key] = r
        return sorted(chosen.values(), key=lambda r: (r["full_name"], r["birth_date"], r["source_line"]))


def position_fit(row, position):
    source = row["depth_chart_position"] or row["position"]
    positions = ALIASES.get(source, (source,))
    if position in positions:
        return (0 if positions == (position,) else 1), source
    if any(FAMILY.get(p) == FAMILY[position] for p in positions):
        return 4, source
    # Historic E was a receiving end. Both listed roles are compatible even
    # though WR/TE are separate retail families. Never assign an unrelated role.
    return INF, source


def assignment(cost):
    """Rectangular minimum-cost one-to-one assignment, deterministic tie order.

    Potentials and augmenting paths; bounded by 53 rows and <=3000 candidates.
    This keeps flexible DB/LB/OL candidates available for scarce exact roles.
    """
    n, m = len(cost), len(cost[0])
    e.require(n <= m <= 3000, "candidate count outside bounded assignment")
    u, v, p, way = [0] * (n + 1), [0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (m + 1), [False] * (m + 1)
        while True:
            used[j0], i0, delta, j1 = True, p[j0], INF, 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            e.require(delta < INF, "no compatible 53-player assignment")
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    result = [0] * n
    for j in range(1, m + 1):
        if p[j]:
            result[p[j] - 1] = j - 1
    e.require(all(cost[i][j] < INF // 2 for i, j in enumerate(result)), "no compatible role assignment")
    return result


def choose_season(descriptor, uses):
    def key(m):
        date_year, year = int(m["game_date"][:4]), descriptor["year"]
        return (0 if m["season"] == year else 1 if date_year == year else 2,
                abs(m["season"] - year), m["moment"])
    return min(uses, key=key)


def make_roster(raw, descriptor, moment, source, colleges):
    document = rr.RosterDocument(raw[32:])
    team, season = SELECTORS[descriptor["selector"]], moment["season"]
    candidates = source.candidates(team, season)
    qb_preference = QB_PREFERENCES.get((team, season))
    if qb_preference:
        e.require(sum(r["full_name"] == qb_preference and r["season"] == season and
                      position_fit(r, "QB")[0] == 0 for r in candidates) == 1,
                  "editorial QB preference lacks exact supplied season membership")
    story = norm(moment["history"] + " " + moment["objective"] + " " + moment["title"])
    priorities, jerseys = [], []
    for r in candidates:
        identity_rows = source.by_identity[r["identity"]]
        tenure = len({x["season"] for x in identity_rows if x["franchise"] == team and 0 <= season - x["season"] <= 3})
        experience = max(0, season - min(x["season"] for x in identity_rows))
        priorities.append((0 if norm(r["full_name"]) in story else 1,
                           STATUS_ORDER.get(r["status"], 7), -number(r["games_started"]),
                           -tenure, -max(number(r["years_exp"]), experience),
                           number(r["draft_round"]) or 99, number(r["draft_number"]) or 999,
                           r["full_name"], r["birth_date"]))
        jerseys.append(source.jersey(r, season))
    priority_order = {i: rank for rank, i in enumerate(sorted(range(len(candidates)), key=priorities.__getitem__))}
    cost = []
    for p in document.players:
        values = p.record.values
        row = []
        for j, r in enumerate(candidates):
            fit, _ = position_fit(r, p.record.position_name)
            distance = abs(r["season"] - season)
            # Same-season membership wins globally before any ranking preference.
            # Role fillers use nearest years. Rank-weight assigns the strongest
            # available weak starter proxy to the slot with the best depth rank.
            penalty = ((10**11 + (8 - values["depth_rank"]) * 10**6) if distance else 0) + distance * 10**8
            # A real name already in this slot is stronger evidence than our
            # ranking heuristic, if that player is in the chosen season list.
            retained_name = distance == 0 and norm(p.display) in (
                norm(r["full_name"]), norm(r["first_name"] + " " + r["last_name"]))
            row.append(INF if fit == INF else penalty + fit * 100000 +
                       priority_order[j] * (8 - values["depth_rank"]) * 10 +
                       (0 if jerseys[j][0] == values["jersey"] else 1000) - (10**7 if retained_name else 0) -
                       (10**9 if qb_preference == r["full_name"] and not distance and
                        p.record.position_name == "QB" and values["depth_rank"] == 0 else 0))
        cost.append(row)
    selected = assignment(cost)
    rows, provenance = [], []
    for p, j in zip(document.players, selected):
        r = candidates[j]
        first, last = display_parts(r)
        jersey, basis = jerseys[j]
        fit, source_position = position_fit(r, p.record.position_name)
        college = r["college"] if colleges.count(r["college"]) == 1 else ""
        row = {"pool": "primary", "index": p.index, "first": first, "last": last,
               "position": p.record.position_name, "jersey": p.record.values["jersey"] if jersey is None else jersey,
               "college": college, **p.record.ratings()}
        rows.append(row)
        provenance.append({"slot": p.index, "first": first, "last": last, "source_file": r["source_file"],
                           "source_line": r["source_line"], "source_full_name": r["full_name"],
                           "source_identity": r["identity"], "source_team": r["team"], "source_season": r["season"],
                           "source_position": source_position, "source_status": r["status"],
                           "role_fit": "exact" if fit == 0 else "broad_source_role" if fit == 1 else "same_role_family",
                           "adjacent_season_filler": r["season"] != season, "jersey": row["jersey"],
                           "jersey_source": basis, "college_basis": "exact_main_table_index" if college else "retail_slot",
                           "retail_depth_rank": p.record.values["depth_rank"],
                           "named_in_chosen_moment": priorities[j][0] == 0,
                           "retained_retail_identity": norm(p.display) in (norm(r["full_name"]), norm(r["first_name"] + " " + r["last_name"])),
                           "editorial_qb_preference": r["full_name"] == qb_preference,
                           "lineup_basis": "inferred_season_depth_not_game_starter"})
    stream = io.StringIO()
    writer = csv.DictWriter(stream, e.CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    text = stream.getvalue()
    parsed = e.parse_csv(text)
    after = e.compile_resource(raw, parsed, colleges)
    return text, provenance, after


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def generate(retail, inputs, output, docs, pfr=None):
    import nfl2k5_espn25_exact_lineups as exact
    evidence = exact.Evidence(pfr or exact.DEFAULT_PFR)
    source = Source(inputs)
    output.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    with rr._outer_image()(retail) as archive:
        def bounded(index, maximum):
            entry = archive.entries[index]
            e.require(32 < entry.size <= maximum, "resource exceeds bounded inventory read")
            return archive.read(entry.virtual_offset, entry.size)
        context = e.describe_context(bounded(5, e.MAX_RESOURCE), bounded(22, e.MAX_RESOURCE), archive.entries)
        resources = {d["outer"]: bounded(d["outer"], 16384) for d in context["descriptors"]}
    moments = context["moments"]
    for m in moments:
        date = dt.datetime.strptime(m["date"], "%B %d, %Y").date()
        m["game_date"] = date.isoformat()
        m["season"] = date.year - (date.month <= 2)
        m["game"] = f"{m['away']['selector']} vs {m['home']['selector']}"
    # The context pin excludes generator annotations.
    clean_context = {**context, "moments": [{k: v for k, v in m.items() if k not in ("game_date", "season", "game")}
                                           for m in moments]}
    used = {m[side]["outer"] for m in moments for side in ("away", "home")}
    source_names = {norm(name) for r in source.rows for name in (r["full_name"], r["first_name"] + " " + r["last_name"])}
    inventory_rows, inventory_files, targets = [], [], []
    for d in sorted(context["descriptors"], key=lambda d: d["outer"]):
        raw = resources[d["outer"]]
        document = rr.RosterDocument(raw[32:])
        e.require(document.to_body() == raw[32:], "inventory codec round trip differs")
        classifications = Counter()
        for p in document.players:
            placeholder = p.first.casefold() == d["selector"].casefold() or p.first.casefold() == "buccanneers" or p.last in (
                "Center", "Cornerback", "Def End", "Def Tackle", "Free Safety", "Fullback", "Guard",
                "Halfback", "In Linebacker", "Kicker", "Out Linebacker", "Punter", "Quarterback",
                "Strong Safety", "Tackle", "Tight End", "Wide Receiver")
            classification = "placeholder" if placeholder else "real_name_in_supplied_data" if norm(p.display) in source_names else "unresolved_name"
            classifications[classification] += 1
            inventory_rows.append({"filename": d["filename"], "outer": d["outer"], "team": d["selector"],
                                   "file_year": d["year"], "used_by_moments": int(d["outer"] in used),
                                   "slot": p.index, "first": p.first, "last": p.last,
                                   "position": p.record.position_name, "jersey": p.record.values["jersey"],
                                   "classification": classification, **p.record.ratings()})
        file_info = {**d, "size": len(raw), "retail_sha256": e.sha(raw), "wrapper_hex": raw[:32].hex(),
                     "team_label": document.teams[0].city + " " + document.teams[0].nickname,
                     "players": len(document.players), "primary": sum(p.pool == "primary" for p in document.players),
                     "secondary": sum(p.pool == "secondary" for p in document.players), "classification": dict(classifications),
                     "position_mix": dict(Counter(p.record.position_name for p in document.players)),
                     "name_pool": document.names.summary(), "used_by_moments": d["outer"] in used}
        inventory_files.append(file_info)
        if d["outer"] not in used:
            continue
        uses = [m for m in moments if any(m[s]["outer"] == d["outer"] for s in ("away", "home"))]
        chosen = choose_season(d, uses)
        text, provenance, after, exclusions = exact.make_roster(raw, d, chosen, source, context["colleges"], evidence)
        name = d["filename"][:-4] + ".csv"
        (output / name).write_text(text, encoding="utf-8", newline="\n")
        target = {**d, "size": len(raw), "retail_sha256": e.sha(raw), "applied_sha256": e.sha(after),
                  "csv": name, "csv_sha256": e.sha(text.encode()), "selected_season": chosen["season"],
                  "chosen_moment": chosen["moment"], "uses": [m["moment"] for m in uses],
                  "editorial_qb_preference": QB_PREFERENCES.get((SELECTORS[d["selector"]], chosen["season"])),
                  "losing_moments": [m["moment"] for m in uses if m["season"] != chosen["season"]],
                  "placeholders_replaced": classifications["placeholder"], "position_mix": file_info["position_mix"],
                  "season_source_players": len({r["identity"] for r in source.by_team[SELECTORS[d["selector"]]] if r["season"] == chosen["season"]}),
                  "excluded_source_names": exclusions,
                  "fillers": sum(p["adjacent_season_filler"] for p in provenance),
                  "unknown_numbers": sum(p["jersey_source"]["basis"] == "retail_slot_unknown_historical_number" for p in provenance),
                  "other_season_numbers": sum(p["jersey_source"]["basis"] == "other_season_same_player_same_franchise" for p in provenance),
                  "players": provenance}
        targets.append(target)
        print(f"{name}: season {chosen['season']}, {target['fillers']} role fillers, {target['unknown_numbers']} unknown numbers", flush=True)
    by_outer = {t["outer"]: t for t in targets}
    moment_rows = []
    for m in moments:
        row = {k: m[k] for k in ("moment", "title", "date", "game_date", "season", "game")}
        row["lineup_basis"] = "Inferred season regulars: source-matched existing names, status, role, prior team tenure, available experience/draft fields, retail depth slots; no game lineup evidence."
        row["exact_game_lineup_established"] = False
        row["sides"] = {}
        for side in ("away", "home"):
            t = by_outer[m[side]["outer"]]
            row["sides"][side] = {k: t[k] for k in ("outer", "filename", "selected_season", "chosen_moment",
                "placeholders_replaced", "fillers", "unknown_numbers", "other_season_numbers")}
            row["sides"][side]["shared_season_conflict"] = t["selected_season"] != m["season"]
        moment_rows.append(row)
    manifest = {"schema": e.SCHEMA, "evidence": e.EVIDENCE, "default_enabled": False,
        "source": {"name": "nflverse-data season rosters, user-supplied offline CSVs 1960..2004",
                   "url": "https://github.com/nflverse/nflverse-data/releases/tag/rosters",
                   "licence": "CC-BY-4.0", "licence_url": "https://creativecommons.org/licenses/by/4.0/",
                   "attribution": "nflverse contributors; source season rosters transformed into fixed 53-slot NFL 2K5 historic rosters.",
                   "generator": "tools/nfl2k5_espn25_rosters_from_nflverse.py", "files": source.files,
                   "nonempty_columns": dict(source.nonempty), "available_columns": sorted(source.columns)},
        "context_sha256": e.context_sha(clean_context), "colleges": context["colleges"],
        "retail_input": {"source": "User-owned ESPN NFL 2K5 USA historic ROST resources",
                         "licence": "Not covered by the nflverse licence; user-owned game input",
                         "contribution": "Preserved position/rating profiles, unknown-number fallbacks and resource layout. No binary game resource is distributed by this dataset."},
        "rules": {
            "shared_seasons": "Prefer a used moment matching file season; then calendar date year; then nearest season, lower moment index breaks ties. Unique files take their moment season. January/February belong to preceding season.",
            "starters": "No game starts or depth ordinal supplied. Retain source-matched real retail identities in compatible slots of the chosen season. Otherwise use status/position, team tenure in the current and preceding three seasons, available experience/draft and named narrative participants as weak deterministic ranking inputs, not established starters.",
            "editorial_qbs": "HYPOTHESIS: season-regular preferences Daryle Lamonica (1968 OAK), Dan Fouts (1981 SD), Dave Krieg (1992 KC) correct tenure's preference for long-serving backups. These editorial historical judgments have supplied name/season/role membership validation only; no supplied game-start evidence or external verification. All other depth choices use the stated heuristic.",
            "fillers": "Maximize compatible selected-season identities first. Fill scarce role slots with nearest-season same-franchise identities, explicitly labeled; no duplicate or invented names. These fillers are not members of the claimed game roster.",
            "positions": "Keep each retail slot code, rank, side and team pointer. Broader DB/LB/OL/RB/DL roles may fill compatible slots; all concessions listed per player.",
            "numbers": "Use selected source row number when 1..99. Else nearest season of the same player and franchise if available, explicitly marked uncertain. Else retain retail slot number and mark unknown. Source zero is missing, not a real jersey.",
            "ratings": "Keep all 28 retail rating/style bytes exactly. No Hall of Fame, All-Pro or Pro Bowl signal supplied; no adjustment. Native C1030 clamps ratings to 0..100.",
            "appearance": "Keep every appearance, height/weight, age, commentary/photo, contract and unknown bit. Name, jersey and exact main-table college index only may change.",
            "college": "Source college must match exactly one main table string; encode its zero-based index, never a field-relative pointer. Otherwise retain retail word.",
            "names": "Use supplied full_name split by supplied last_name; preserve familiar names from full_name when first_name is legal name. Existing codec allocator only; no truncation.",
            "activation": "All presets off: opt-in because data cannot meet exact-game identities/numbers, even if bounded native loading passes. Protected wiring in WIRING.md."},
        "resources": targets, "moments": moment_rows}
    exact.enrich_manifest(manifest, moments, evidence, output)
    write_json(output / "manifest.json", manifest)
    fields = list(inventory_rows[0])
    with (docs / "nfl2k5_espn25_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory_rows)
    write_json(docs / "nfl2k5_espn25_inventory.json", {"evidence": e.EVIDENCE, "files": inventory_files,
               "resources": len(inventory_files), "players": len(inventory_rows), "used_resources": len(targets),
               "source": "User-owned retail archive, independently decoded with RosterDocument", "codec_roundtrip_all": True})
    print("manifest sha256", e.sha((output / "manifest.json").read_bytes()), flush=True)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail", type=Path, default=DEFAULT_RETAIL)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=e.DATA_DIR)
    parser.add_argument("--docs", type=Path, default=ROOT / "docs/mod_editor")
    parser.add_argument("--pfr", type=Path, help="Private pfr_pull/v1 evidence (default .scratch/pfr/pfr_data.json)")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="espn25-data-check-") as directory:
            scratch = Path(directory).resolve()
            generate(args.retail, args.inputs, scratch / "data", scratch / "docs", args.pfr)
            for folder, target in ((scratch / "data", args.out), (scratch / "docs", args.docs)):
                for path in folder.iterdir():
                    e.require(path.read_bytes() == (target / path.name).read_bytes(), f"regeneration differs: {path.name}")
            e.require({p.name for p in (scratch / "data").iterdir()} == {p.name for p in args.out.iterdir()}, "unexpected dataset files")
        print("all generated files reproduce exactly")
    else:
        generate(args.retail, args.inputs, args.out, args.docs, args.pfr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
