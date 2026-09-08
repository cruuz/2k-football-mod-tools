#!/usr/bin/env python3
"""Offline Pro Football Reference starter/number enrichment for the nflverse base.

Only derived player facts and source citations enter the dataset. Raw pages and
pfr_pull/v1 remain private inputs. No network or game execution is used.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "tools"):
    sys.path.insert(0, str(path))
import nfl2k5_espn25_rosters_from_nflverse as gen
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr

DEFAULT_PFR = ROOT / ".scratch/pfr/pfr_data.json"
LINEUP_BASIS = "E: exact game starters from the box score; bench from the season roster"
PFR_CODES = dict(zip(
    "BUF CIN CLE IND ARZ DAL DEN GB KC MIA NO NE NYG NYJ TEN PHI PIT OAK STL SD SF TB WAS".split(),
    "buf cin cle clt crd dal den gnb kan mia nor nwe nyg nyj oti phi pit rai ram sdg sfo tam was".split()))
# Cross-source familiar/legal-name joins, scoped by franchise. PFR display names
# remain authoritative. These joins do not supply a missing game-season number.
NAME_ALIASES = {
    ("BUF", "Rob Coons"): "Robert Coons", ("BUF", "Marcus Spriggs"): "T. Marcus Spriggs",
    ("IND", "Bradford Banta"): "Brad Banta", ("ARZ", "Pete Noga"): "Peter Noga",
    ("DEN", "Bill Bryan"): "Billy Bryan", ("GB", "Nick Luchey"): "Nicolas Luchey",
    ("KC", "Dave Szott"): "David Szott", ("KC", "Dave Whitmore"): "David Whitmore",
    ("NYG", "Dave Whitmore"): "David Whitmore", ("NO", "Don Schwartz"): "Donald Schwartz",
    ("NO", "Mike Strachan"): "Michael Strachan", ("NYG", "Will Peterson"): "William James",
    ("TEN", "Mike Jones"): "Mike D. Jones", ("PHI", "N.D. Kalu"): "Ndukwe Kalu",
    ("STL", "Devin Bush Sr."): "Devin Bush", ("STL", "Mike Jones"): "Mike A. Jones",
    ("SF", "Jim Robinson"): "Jimmy Robinson", ("SF", "Tom Seabron"): "Thomas Seabron",
    ("SF", "Mike Walter"): "Michael Walter", ("WAS", "John McDaniel"): "Johnnie McDaniel",
}
POSITION_MAP = {
    **{p: (p,) for p in rr.POSITIONS},
    "FL": ("WR",), "SE": ("WR",), "E": ("WR",), "LE": ("WR",),
    "RB": ("HB", "FB"), "LHB": ("HB",),
    "LT": ("T",), "RT": ("T",), "LG": ("G",), "RG": ("G",),
    "OL": ("C", "G", "T"), "G-C": ("G", "C"),
    "LDE": ("DE",), "RDE": ("DE",), "LDT": ("DT",), "RDT": ("DT",), "NT": ("DT",),
    "LLB": ("OLB",), "RLB": ("OLB",), "LOLB": ("OLB",), "ROLB": ("OLB",),
    "SLB": ("OLB",), "WLB": ("OLB",), "SAM": ("OLB",), "WILL": ("OLB",),
    "MLB": ("ILB",), "LILB": ("ILB",), "RILB": ("ILB",), "LB": ("OLB", "ILB"),
    "LCB": ("CB",), "RCB": ("CB",), "DB": ("CB", "FS", "SS"),
    "S": ("FS", "SS"), "RS": ("FS", "SS"), "LS": ("C",),
    "DL": ("DE", "DT"), "OT": ("T",), "OG": ("G",), "SAF": ("FS", "SS"),
    "KR": ("HB", "WR", "CB"), "": (),
}
LEFT = {"LT", "LG", "LDE", "LDT", "LLB", "LOLB", "LILB", "LCB", "SE"}
RIGHT = {"RT", "RG", "RDE", "RDT", "RLB", "ROLB", "RILB", "RCB", "FL"}
PAIRED = {"T", "G", "DE", "DT", "OLB", "ILB", "CB", "WR"}


def positions(label, *, starter=False):
    # LS in a 1968 starters table is left safety, never the long snapper.
    if starter and label == "LS":
        return ("FS", "SS")
    result = []
    for part in label.split("/"):
        e.require(part in POSITION_MAP, f"unmapped source position: {label!r}")
        result.extend(POSITION_MAP[part])
    return tuple(dict.fromkeys(result))


def match_name(name, rows, field="player", aliases=()):
    """Exact spelling first, then the base generator's normalization; no fuzzy join."""
    names = (name, *aliases)
    for candidate in names:
        for mode, normalize in (("exact", lambda s: s), ("normalized", gen.norm)):
            hits = [r for r in rows if normalize(r[field]) == normalize(candidate)]
            e.require(len(hits) <= 1, f"ambiguous source name: {name}")
            if hits:
                return hits[0], mode if candidate == name else "alias"
    return None, "unmatched"


def nfl_match(name, rows, team):
    alias = NAME_ALIASES.get((team, name))
    for field in ("full_name", "legal_name"):
        found, basis = match_name(name, rows, field, (alias,) if alias else ())
        if found:
            return found, basis
    return None, "pfr_only"


def display(name, nfl=None):
    if nfl and gen.norm(name) == gen.norm(nfl["full_name"]):
        return gen.display_parts(nfl)
    parts = name.split()
    if parts[-1] in ("Sr.", "Jr.", "II", "III"):
        first, last = " ".join(parts[:-2]), " ".join(parts[-2:])
    else:
        first, last = " ".join(parts[:-1]), parts[-1]
    e.require(first and last, f"incomplete player name: {name}")
    rr.validate_name(first)
    rr.validate_name(last)
    return first, last


class Evidence:
    def __init__(self, path=DEFAULT_PFR):
        raw = e.read_bounded(path, 4 * 1024 * 1024)
        data = json.loads(raw)
        e.require(data["schema"] == "pfr_pull/v1", "foreign PFR evidence schema")
        self.digest, self.pulled = e.sha(raw), data["pulled"]
        self.boxes = {b["index"]: b for b in data["boxscores"]}
        self.rosters = {(r["team"], r["season"]): r for r in data["rosters"]}
        e.require(len(data["boxscores"]) == len(self.boxes) == 25 and set(self.boxes) == set(range(25)),
                  "expected 25 unique box scores")
        e.require(len(data["rosters"]) == len(self.rosters) == 50, "expected 50 unique season rosters")
        self.omitted_totals = 0
        for page in self.rosters.values():
            people = []
            for line, row in enumerate(page["players"], 1):
                if row["player"] == "Team Total":
                    self.omitted_totals += 1
                    continue
                positions(row["pos"])
                e.require(not row["no"] or row["no"].isdigit() and 0 <= int(row["no"]) <= 99,
                          f"invalid PFR jersey: {row['player']}")
                people.append({**row, "line": line})
            e.require(len({gen.norm(r['player']) for r in people}) == len(people), "duplicate PFR roster name")
            page["players"] = people
        for box in self.boxes.values():
            e.require(len(box["teams"]) == 2, "missing box-score teams")
            for side in ("away", "home"):
                e.require(len(box[side]) == 22 and len({gen.norm(s['player']) for s in box[side]}) == 22,
                          "expected 22 distinct box-score starters per side")
                for s in box[side]:
                    positions(s["pos"], starter=True)

    def side(self, moment, descriptor):
        box = self.boxes[moment["moment"]]
        e.require(box["date"] == moment["game_date"], "box-score date differs from moment")
        selector = descriptor["selector"]
        hits = [i for i, name in enumerate(box["teams"]) if gen.norm(name).endswith(gen.norm(selector))]
        e.require(len(hits) == 1, f"cannot bind box-score team: {selector}")
        side = ("away", "home")[hits[0]]
        page = self.rosters[PFR_CODES[gen.SELECTORS[selector]], moment["season"]]
        return box, side, page

    def starters(self, moment, descriptor):
        box, side, page = self.side(moment, descriptor)
        out = []
        for starter in box[side]:
            row, basis = match_name(starter["player"], page["players"])
            e.require(row is not None, f"starter absent from season roster: {starter['player']}")
            pos, note = starter["pos"], None
            # The raw box page itself says SS; its season roster says RG. This
            # restores the missing fifth offensive lineman without changing bytes.
            if (moment["moment"], descriptor["selector"], starter["player"]) == (12, "cardinals", "Lance Smith"):
                e.require(pos == "SS" and row["pos"] == "RG", "Lance Smith conflict evidence changed")
                pos, note = "RG", "Box score says SS; season roster says RG. Use RG; position correction is HYPOTHESIS."
            out.append({"name": starter["player"], "box_position": starter["pos"], "position": pos,
                        "season_position": row["pos"], "jersey": int(row["no"]) if row["no"] else None,
                        "jersey_text": row["no"],
                        "roster_match": basis, "position_note": note})
        return out


def starter_cost(starter, slot):
    pos, label = slot.record.position_name, starter["position"]
    if pos not in positions(label, starter=True):
        return gen.INF
    values = slot.record.values
    if label in LEFT:
        depth = values["depth_rank"]
    elif label in RIGHT:
        depth = values["depth_side"]
    else:
        depth = min(values["depth_rank"], values["depth_side"]) if pos in PAIRED else values["depth_rank"]
    season_fit = pos in positions(starter["season_position"])
    # Explicit side and source-role constraints come before deterministic ties.
    return depth * 10000 + (0 if season_fit else 100) + slot.index


def make_roster(raw, descriptor, moment, source, colleges, evidence):
    document = rr.RosterDocument(raw[32:])
    team, season = gen.SELECTORS[descriptor["selector"]], moment["season"]
    _, _, page = evidence.side(moment, descriptor)
    starters = evidence.starters(moment, descriptor)
    nfl_rows = [{**r, "legal_name": r["first_name"] + " " + r["last_name"]}
                for r in source.candidates(team, season) if r["season"] == season]
    candidates, used_identities, exclusions = [], set(), []
    for rank, row in enumerate(sorted(page["players"], key=lambda r: (
            -gen.number(r["gs"]), -gen.number(r["g"]), -gen.number(r["av"]), gen.norm(r["player"])))):
        nfl, match = nfl_match(row["player"], nfl_rows, team)
        # Link same-player fillers across seasons too, excluding duplicate aliases.
        if nfl is None:
            all_rows = [{**r, "legal_name": r["first_name"] + " " + r["last_name"]}
                        for r in source.candidates(team, season)]
            nfl_identity, _ = nfl_match(row["player"], all_rows, team)
        else:
            nfl_identity = nfl
        identity = nfl_identity["identity"] if nfl_identity else "pfr|" + gen.norm(row["player"])
        used_identities.add(identity)
        try:
            first, last = display(row["player"], nfl)
        except rr.RosterRecordError:
            exclusions.append({"name": row["player"], "file": page["url"], "line": row["line"],
                               "reason": "Name does not fit the existing 15-character codec; not shortened."})
            continue
        candidates.append(dict(name=row["player"], first=first, last=last, identity=identity,
                               nfl=nfl, pfr=row, rank=rank, season=season, position=row["pos"], match=match))
    for r in source.candidates(team, season):
        if r["identity"] in used_identities:
            continue
        used_identities.add(r["identity"])
        first, last = gen.display_parts(r)
        candidates.append(dict(name=r["full_name"], first=first, last=last, identity=r["identity"],
                               nfl=r, pfr=None, rank=0, season=r["season"],
                               position=r["depth_chart_position"] or r["position"], match="nflverse_fallback"))
    starters_by_name = {s["name"]: s for s in starters}
    starter_rows = []
    for s in starters:
        hits = [c for c in candidates if c["name"] == s["name"] and c["pfr"]]
        e.require(len(hits) == 1, f"starter cannot be encoded: {s['name']}")
        starter_rows.append(hits[0])
    starter_slots = gen.assignment([[starter_cost(s, p) for p in document.players] for s in starters])
    selected = dict(zip(starter_slots, starter_rows))
    starter_ids = {c["identity"] for c in starter_rows}
    bench = [c for c in candidates if c["identity"] not in starter_ids]
    slots = [p for p in document.players if p.index not in selected]
    costs = []
    for p in slots:
        row = []
        for c in bench:
            pos = p.record.position_name
            fits = positions(c["position"])
            fit = 0 if pos in fits else 1 if any(gen.FAMILY.get(x) == gen.FAMILY[pos] for x in fits) else gen.INF
            if fit == gen.INF:
                row.append(gen.INF)
                continue
            # Prefer page members, then same-season nflverse, then closest-year
            # same-franchise reserves. Within compatible roles, GS/G/AV rank wins.
            tier = 0 if c["pfr"] else 1 if c["season"] == season else 2
            depth = min(p.record.values['depth_rank'], p.record.values['depth_side']) if pos in PAIRED else p.record.values['depth_rank']
            row.append(tier * 10**11 + abs(c["season"] - season) * 10**8 +
                       c["rank"] * (8 - depth) * 1000 + fit * 100 + p.index)
        costs.append(row)
    selected.update((p.index, bench[j]) for p, j in zip(slots, gen.assignment(costs)))
    rows, provenance = [], []
    for p in document.players:
        c = selected[p.index]
        nfl, pr = c["nfl"], c["pfr"]
        jersey = int(pr["no"]) if pr and pr["no"] else None
        nfl_college = nfl["college"] if nfl else ""
        use_pfr_college = bool(pr and pr["college"] and colleges.count(nfl_college) != 1)
        college_source = pr["college"] if use_pfr_college else nfl_college
        college = college_source if colleges.count(college_source) == 1 else ""
        row = {"pool": "primary", "index": p.index, "first": c["first"], "last": c["last"],
               "position": p.record.position_name, "jersey": p.record.values["jersey"] if jersey is None else jersey,
               "college": college, **p.record.ratings()}
        rows.append(row)
        st = starters_by_name.get(c["name"]) if pr else None
        basis = {"basis": "pfr_game_season", "file": page["url"], "line": pr["line"], "season": season, "source_text": pr["no"]} if jersey is not None else {
            "basis": "retail_slot_unknown_historical_number", "file": None, "line": None,
            "reason": "season_roster_number_blank" if pr else "player_absent_from_game_season_roster"}
        provenance.append({"slot": p.index, "first": c["first"], "last": c["last"],
            "source_file": nfl["source_file"] if nfl else page["url"],
            "source_line": nfl["source_line"] if nfl else pr["line"],
            "source_full_name": c["name"], "source_identity": c["identity"],
            "source_team": nfl["team"] if nfl else team, "source_season": c["season"],
            "source_position": st["position"] if st else c["position"],
            "source_status": nfl["status"] if nfl else "", "source_name_match": c["match"],
            "role_fit": "exact",
            "adjacent_season_filler": c["season"] != season, "jersey": row["jersey"], "jersey_source": basis,
            "college_basis": "exact_main_table_index" if college else "retail_slot",
            "college_source": "Pro Football Reference" if use_pfr_college else "nflverse" if nfl_college else "unknown",
            "source_college": college_source, "retail_depth_rank": p.record.values["depth_rank"],
            "retail_depth_side": p.record.values["depth_side"],
            "named_in_chosen_moment": gen.norm(c["name"]) in gen.norm(moment["history"] + moment["objective"]),
            "retained_retail_identity": gen.norm(p.display) == gen.norm(c["name"]),
            "editorial_qb_preference": c["name"] == gen.QB_PREFERENCES.get((team, season)),
            "lineup_basis": LINEUP_BASIS if st else "season_roster_bench" if pr else "nflverse_role_filler",
            "game_starter": bool(st), "pfr_name": pr["player"] if pr else None,
            "pfr_roster_url": page["url"] if pr else None, "pfr_roster_line": pr["line"] if pr else None,
            "bench_selection_rank": c["rank"] if pr and not st else None})
        fits = positions(st["position"], starter=True) if st else positions(c["position"])
        provenance[-1]["role_fit"] = "exact" if fits == (p.record.position_name,) else "broad_source_role" if p.record.position_name in fits else "same_role_family"
    stream = io.StringIO()
    writer = csv.DictWriter(stream, e.CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    text = stream.getvalue()
    return text, provenance, e.compile_resource(raw, e.parse_csv(text), colleges), exclusions


def enrich_manifest(manifest, moments, evidence, output_folder):
    by_outer = {t["outer"]: t for t in manifest["resources"]}
    for target in manifest["resources"]:
        page = evidence.rosters[PFR_CODES[gen.SELECTORS[target['selector']]], target['selected_season']]
        target.update(pfr_season_source_players=len(page['players']),
                      numbers_from_game_season=sum(p['jersey_source']['basis'] == 'pfr_game_season' for p in target['players']),
                      pfr_season_players=sum(p['pfr_name'] is not None for p in target['players']),
                      losing_moment_starters=[])
    for m, output in zip(moments, manifest["moments"]):
        for side in ("away", "home"):
            target = by_outer[m[side]["outer"]]
            box, source_side, page = evidence.side(m, m[side])
            starters = evidence.starters(m, m[side])
            people = {gen.norm(p["source_full_name"]): p for p in target["players"]}
            document_slots = [{"name": p["source_full_name"], "position": r["position"], **p}
                              for p, r in zip(target["players"], e.parse_csv((output_folder / target["csv"]).read_text()))]
            for s in starters:
                person = people.get(gen.norm(s["name"]))
                role_matches = person and next(p for p in document_slots if p['slot'] == person['slot'])["position"] in positions(s['position'], starter=True)
                s.update(slot=person['slot'] if person else None, present=person is not None,
                         at_starting_depth=False, number_matches=bool(person and s['jersey'] is not None and person['jersey'] == s['jersey']))
                if role_matches:
                    slot = next(p for p in document_slots if p['slot'] == person['slot'])
                    pos, label = slot['position'], s['position']
                    field = 'retail_depth_rank' if label in LEFT or pos not in PAIRED else 'retail_depth_side' if label in RIGHT else None
                    group = [p for p in document_slots if p['position'] == pos]
                    def ordinal(key):
                        order = sorted(group, key=lambda p: (p[key], p['slot']))
                        return next(i for i, p in enumerate(order) if p['slot'] == slot['slot'])
                    depth = ordinal(field) if field else min(ordinal('retail_depth_rank'), ordinal('retail_depth_side'))
                    same_role = sum(pos in positions(x['position'], starter=True) for x in starters)
                    limit = (same_role + 1) // 2 if pos in PAIRED else same_role
                    s['at_starting_depth'] = depth < limit
            resolved = sum(s['present'] and s['at_starting_depth'] for s in starters)
            # A coincidental same-name match cannot establish another season's lineup.
            exact = resolved == 22 and all(s['number_matches'] or s['jersey'] is None for s in starters)
            missing = [s['name'] for s in starters if not s['present']]
            verified_numbers = 0
            for person in target['players']:
                donor, _ = match_name(person['source_full_name'], page['players'])
                verified_numbers += bool(donor and donor['no'] and int(donor['no']) == person['jersey'])
            s_out = output['sides'][side]
            s_out.update(lineup_basis=LINEUP_BASIS, exact_game_lineup_established=exact,
                         starters_resolved=resolved, starters_present=sum(s['present'] for s in starters),
                         starters=starters, missing_starters=missing,
                         starters_not_at_starting_depth=[s['name'] for s in starters if s['present'] and not s['at_starting_depth']],
                         starter_number_mismatches=[s['name'] for s in starters if s['present'] and s['jersey'] is not None and not s['number_matches']],
                         numbers_from_game_season=verified_numbers,
                         numbers_still_unknown=53 - verified_numbers,
                         boxscore_url=box['url'], pfr_roster_url=page['url'], boxscore_source_side=source_side,
                         boxscore_side_remapped=source_side != side)
            if m['moment'] != target['chosen_moment']:
                target['losing_moment_starters'].append({'moment': m['moment'], 'side': side,
                    'missing_starters': missing, 'starters_resolved': resolved,
                    'starters_not_at_starting_depth': s_out['starters_not_at_starting_depth'],
                    'starter_number_mismatches': s_out['starter_number_mismatches']})
        output['lineup_basis'] = LINEUP_BASIS
        output['exact_game_lineup_established'] = all(s['exact_game_lineup_established'] for s in output['sides'].values())
    manifest['source']['lineup_source'] = {'name': 'Pro Football Reference',
        'attribution': 'Pro Football Reference box-score starters and season rosters; derived player facts only. Raw pages are not distributed. The nflverse CC-BY base attribution remains separate.',
        'generator': 'tools/nfl2k5_espn25_exact_lineups.py', 'input_sha256': evidence.digest,
        'pulled': evidence.pulled, 'boxscores': 25, 'season_rosters': 50,
        'aggregate_rows_excluded': evidence.omitted_totals,
        'player_rows': sum(len(p['players']) for p in evidence.rosters.values())}
    manifest['rules'].update(starters='Reserve all 22 box-score starters first, using retail rank and side chains; extra TE/WR/DB starters take the next available depth in their role. Team names bind the box-score sides to SITU.',
        editorial_qbs='Superseded by box-score starters. Original editorial_qb_preference fields retained for compatibility.',
        fillers='Bench: prefer season-roster members ordered by games started, games, AV, name within the fixed retail position mix; then same-season nflverse, then closest-season same-franchise role fillers. All exceptions recorded.',
        numbers='Only the selected game-season PFR roster supplies numbers, exact name then normalized name. Blank or absent rows retain the retail number and are marked unknown. No other-season jersey inference.',
        names='PFR display names for season-page members; exact/normalized or documented franchise-scoped familiar/legal-name aliases link the nflverse base. Existing 15-character codec, no truncation.',
        college='Keep an encodable nflverse college; when that CSV cell would be blank, use PFR college. Encode only an exact unique main-table string; retain the source college fact even when it cannot be encoded.',
        activation='All presets off. EXPERIMENTAL / UNWITNESSED. Exact box-score starter identities do not establish snap-specific personnel, and shared files retain the chosen moment.')
