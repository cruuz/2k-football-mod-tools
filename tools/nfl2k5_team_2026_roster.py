#!/usr/bin/env python3
"""Build a team's 2026 roster as ordinary Rosters edits (``2k5_mod_studio_roster_edits/v1``).

Job u1 (2026 modernization pilot, the New York Giants). The team's own 53 retail records are rewritten in place:
name, jersey number, position, height, weight, birth date, college (when the roster's college table has it),
years pro, the 28 ratings, the depth order, the announcer cue and the appearance keys (skin tone, face and
portrait slot). Team membership, pointers, contracts, history and every unrelated bit stay with the record, so the
document replays onto the ultimate build's roster (which applies ``roster_edits`` last, after the one-pool
reclassification) exactly like an edit made on the Rosters page.

Sources: nflverse-data ``rosters/roster_<season>.csv`` (the roster and physicals), ``depth_charts`` (the order),
and job m2's ratings model (``mod_editor/core/nfl2k5_ratings_model.py``: the season's real statistics mapped onto
2K5's own rating scale). nflverse data is CC-BY-4.0. Nothing retail is written to the repository.

  python3 tools/nfl2k5_team_2026_roster.py build --spec data/nfl2k5_teams_2026/NYG.json \
      --disc RETAIL.iso --nflverse DIR --out DIR [--ratings-model PATH] [--faces faces.json]

Outputs in ``--out``: ``roster_edits.json`` (the team alone), ``roster_rows.csv`` (one row per player, source values
beside the written values, for the Jev row check) and ``receipt.json``.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

SCHEMA = "nfl2k5_team_2026_roster/v1"
# One-pool codes (the ultimate build's scheme): 16 EDGE, 15 interior DL, 11 LB. On a retail-scheme disc the same
# codes read DE, DT and ILB, so the document is valid on both.
FAMILY = {"QB": "QB", "HB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL",
          "DE": "DL", "DT": "DL", "OLB": "LB", "ILB": "LB", "CB": "DB", "FS": "DB", "SS": "DB", "K": "K", "P": "P"}
NFLVERSE_DEPTH_ORDER = {"QB": 0, "RB": 1, "FB": 2, "WR": 3, "TE": 4, "T": 5, "LT": 5, "RT": 5, "G": 6, "LG": 6,
                        "RG": 6, "C": 7, "DE": 8, "DT": 9, "NT": 9, "OLB": 10, "EDGE": 10, "ILB": 11, "MLB": 11,
                        "LB": 11, "CB": 12, "FS": 13, "SS": 14, "S": 13, "K": 15, "P": 16, "LS": 17}


def norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold() if c.isalnum())


def load_ratings_model(path: str | None):
    if path is None:
        from mod_editor.core import nfl2k5_ratings_model as rm  # the stack's copy once integrated
        return rm
    spec = importlib.util.spec_from_file_location("mod_editor.core.nfl2k5_ratings_model", path)
    rm = importlib.util.module_from_spec(spec)
    sys.modules["mod_editor.core.nfl2k5_ratings_model"] = rm
    spec.loader.exec_module(rm)
    return rm


def game_position(row: dict, defense: str) -> str:
    """The 2K5 position (retail name of the one-pool code) for an nflverse roster row; the weekly lineup slot
    (``slot``, from the depth charts) wins over the roster's own depth-chart position."""
    pos = row["position"].upper()
    slot = (row.get("slot") or "").upper()
    # the 2026 nflverse depth-chart slots (every one: WR TE RB FB QB LT LG C RG RT; LDE RDE LDT RDT NT; WLB SLB MLB
    # LILB RILB; LCB RCB NB FS SS; KR PR PK K P LS H)
    depth = {"LCB": "CB", "RCB": "CB", "NB": "CB", "LDE": "DE", "RDE": "DE", "LDT": "DT", "RDT": "DT",
             "LILB": "ILB", "RILB": "ILB", "MLB": "ILB", "WLB": "OLB", "SLB": "OLB", "LOLB": "OLB",
             "ROLB": "OLB"}.get(slot, slot)
    if not depth or depth in SPECIAL_SLOTS or depth in ("WR", "RB", "TE", "QB"):
        depth = (row.get("depth_chart_position") or "").upper()
    weight = float(row.get("weight") or 0)
    if pos == "QB":
        return "QB"
    if pos in ("RB", "HB"):
        return "FB" if depth == "FB" else "HB"
    if pos == "FB":
        return "FB"
    if pos == "WR":
        return "WR"
    if pos == "TE":
        return "TE"
    if pos in ("OL", "T", "G", "C", "OT", "OG") or depth in ("LT", "RT", "LG", "RG", "T", "G", "C"):
        if depth in ("C",):
            return "C"
        if depth in ("LG", "RG", "G"):
            return "G"
        if depth in ("LT", "RT", "T"):
            return "T"
        return "T" if weight >= 315 else "G"
    if pos == "LS" or depth == "LS":
        return "C"
    if pos in ("DL", "DE", "DT", "NT"):
        if depth in ("NT", "DT"):
            return "DT"          # a nose or a 4-3 tackle (LDT/RDT): the one-pool interior
        if depth == "DE":
            return "DT" if defense == "3-4" else "DE"   # a 3-4 end plays inside; a 4-3 end is the edge
        if depth in ("OLB", "EDGE"):
            return "DE"
        return "DE" if weight < 295 else "DT"   # no lineup slot: by size
    if pos in ("LB", "OLB", "ILB", "MLB"):
        if depth in ("OLB", "EDGE") and defense == "3-4":
            return "DE"          # the 3-4 outside backer is the edge rusher: one-pool EDGE (16)
        if depth == "DE":
            return "DE"          # a linebacker lined up at end rushes the edge
        if depth in ("NT", "DT"):
            return "DT"
        return "ILB"             # one-pool LB (11); OLB (10) is retired on the ultimate build
    if pos in ("DB", "CB", "S", "SAF", "FS", "SS"):
        if depth == "CB" or pos == "CB":
            return "CB"
        if depth == "SS":
            return "SS"
        if depth == "FS":
            return "FS"
        return "SS" if weight >= 208 else "FS"
    if pos == "K":
        return "K"
    if pos == "P":
        return "P"
    raise ValueError(f"no 2K5 position for {row['full_name']}: {pos}/{depth}")


SPECIAL_SLOTS = {"KR", "PR", "H", "PK", "P", "LS"}
# lineup slot priority inside one depth rank: outside corners before the nickel, the nose before the ends
SLOT_PRIORITY = {"LCB": 0, "RCB": 1, "NB": 2, "NT": 0, "LDE": 1, "RDE": 2, "DT": 1, "LT": 0, "RT": 1, "LG": 0,
                 "RG": 1, "WLB": 0, "SLB": 1, "LILB": 0, "RILB": 1, "MLB": 0, "FS": 0, "SS": 0}


def depth_ranks(depth_csv: Path, team: str, since: str | None = None) -> dict[str, tuple[str, float]]:
    """gsis_id -> (lineup slot, mean rank from 0) over the team's nflverse depth charts since ``since``.

    Averaging the regular-season snapshots keeps a one-day injury flip (a backup listed first on the latest
    snapshot) from becoming the game's default lineup. Special-teams slots count only for players who have no
    offensive or defensive slot (kickers, punters, long snappers, pure returners)."""
    rows = [r for r in csv.DictReader(depth_csv.open(encoding="utf-8")) if r.get("team") == team]
    if not rows:
        return {}
    key = "dt" if "dt" in rows[0] else "week"
    if since and key == "dt":
        rows = [r for r in rows if r[key] >= since] or rows
    seen: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        gid = r.get("gsis_id") or ""
        rank = r.get("pos_rank") or r.get("depth_team") or "1"
        try:
            rank_f = float(rank) - 1
        except ValueError:
            continue
        slot = (r.get("pos_abb") or r.get("depth_position") or r.get("position") or "").upper()
        if gid and slot:
            seen[(gid, slot)].append(rank_f)
    best: dict[str, tuple[str, float]] = {}
    for (gid, slot), ranks in seen.items():
        mean = sum(ranks) / len(ranks)
        special = slot in SPECIAL_SLOTS
        current = best.get(gid)
        score = (special, mean, SLOT_PRIORITY.get(slot, 5))
        if current is None or score < (current[0] in SPECIAL_SLOTS, current[1], SLOT_PRIORITY.get(current[0], 5)):
            best[gid] = (slot, mean)
    return best


def pbp_for(last: str, jersey: int, bank: dict[str, int]) -> tuple[int, str]:
    # Retail-player ordinals can insert that player's given name. The verified generic bank
    # supplies surname-only clips and already excludes ambiguous or unrecorded entries.
    key = rr.commentary_surname(last)
    if key in bank:
        return bank[key], "recorded surname bank"
    return rr.number_commentary_id(jersey), "announces the jersey number"


def ordered_document(document: dict, placeholder: str, name_order: list[int]) -> dict:
    """Two passes in list order: every team record's names -> the shared placeholder (frees the old strings),
    then the final entries, longest new name first (the same order the dry run allocated in)."""
    entries = {(e["pool"], e["index"]): e for e in document["edits"]}
    release = []
    final = []
    for idx in name_order:
        e = entries.pop(("primary", idx), None)
        if e is None:
            continue
        release.append({"pool": e["pool"], "index": e["index"], "last": e["last"], "first": e["first"],
                        "fields": {}, "names": {"first": placeholder, "last": placeholder}})
        e = dict(e, first=placeholder, last=placeholder)
        final.append(e)
    out = dict(document)
    out["edits"] = release + final + list(entries.values())
    out["name_passes"] = {"placeholder": placeholder, "release_entries": len(release),
                          "note": "entries 0..n-1 free the team's old name strings; the rest are the edits"}
    return out


def source_names(r: dict) -> tuple[str, str]:
    """First and last name from an nflverse roster row. When last_name is only the start of the surname that
    full_name carries after the first name (last_name "Joseph", full_name "Sebastian Joseph-Day"), the whole
    surname is used; a generational suffix (Jr., Sr., II..V) is not added."""
    import re
    first, last, full = r["first_name"].strip(), r["last_name"].strip(), r["full_name"].strip()
    if full.casefold().startswith(first.casefold() + " "):
        # generational suffixes stay off (the name atlas has no period glyph): "Beckham Jr." stays "Beckham"
        rest = re.sub(r",?\s+(jr|sr|ii|iii|iv|v)\.?$", "", full[len(first):].strip(), flags=re.IGNORECASE).strip()
        if rest.casefold() != last.casefold() and rest.casefold().startswith(last.casefold()):
            last = rest
    return first, last


def display_names(r: dict) -> tuple[str, str]:
    """The names a player goes by: the surname from source_names, and the first name as full_name has it (the name
    he is listed by, "Josh" for last_name Conerly, full_name "Josh Conerly Jr.", first_name "Joshua"), with a
    generational suffix dropped before the match."""
    import re
    first, last = source_names(r)
    full = re.sub(r",?\s+(jr|sr|ii|iii|iv|v)\.?$", "", r["full_name"].strip(), flags=re.IGNORECASE).strip()
    if full.casefold().endswith(" " + last.casefold()) and len(full) > len(last) + 1:
        first = full[: -len(last)].strip()
    return first, last


def written_names(assigned: dict) -> tuple[dict, list[str]]:
    """The names written for each record (display_names fitted by fit_name), keyed like ``assigned``, and one note
    per shortened name ("Easton Mascarenas-Arnold -> Easton Mascarenas") for the receipt."""
    new_names: dict = {}
    shortened: list[str] = []
    for idx, r in assigned.items():
        full = r["full_name"].strip()
        first, last = display_names(r)
        (first_fit, cut_first), (last_fit, cut_last) = fit_name(first), fit_name(last)
        if cut_first or cut_last:
            shortened.append(f"{full} -> {first_fit} {last_fit}")
        new_names[idx] = (first_fit, last_fit)
    return new_names, shortened


def fit_name(text: str) -> tuple[str, bool]:
    """A name the game can hold: its buffers take 15 characters and its jersey name atlas draws A-Z, a-z,
    apostrophe, hyphen and space. Accents fold to ASCII; an over-long hyphenated surname keeps its first part (the
    broadcast short form: Van Pran-Granger -> Van Pran); any other over-long name is cut at 15. Returns the name and
    whether it was shortened."""
    value = " ".join(unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").split())
    value = "".join(c for c in value if c.isalnum() or c in " '-.")
    short = value
    if len(short) > 15 and "-" in short:
        short = short.split("-", 1)[0].strip()
    if len(short) > 15:
        short = short[:15].rstrip()
    return rr.validate_name(short), short != value


def speed_source_counts(rows: list[dict]) -> dict:
    """How many players' speed came from each source (m2's basis["speed_source"])."""
    counts: dict = {}
    for r in rows:
        basis = r.get("rating_basis") or {}
        try:
            basis = basis if isinstance(basis, dict) else json.loads(basis)
            source = basis.get("speed_source", "unknown")
        except (TypeError, ValueError, AttributeError):
            source = "unknown"
        counts[source] = counts.get(source, 0) + 1
    return dict(sorted(counts.items()))


def merged_forty_sources(rm, paths: list[str]) -> dict:
    """Cited 40 times (job m2's ``nfl2k5.forty_sources.v1`` files, validated by the model's own loader) merged in
    the order given. A player listed twice with different times is refused: say which file is right."""
    merged: dict = {}
    for path in paths:
        for pid, entry in rm.load_forty_sources(path).items():
            if pid in merged and float(merged[pid]["forty"]) != float(entry["forty"]):
                raise SystemExit(f"{pid}: 40 time {merged[pid]['forty']} in one file and {entry['forty']} in {path}")
            merged[pid] = entry
    if paths:
        print(f"  cited 40 times: {len(merged)} players from {len(paths)} file(s)")
    return merged


FRANCHISE_ALIASES = {"LV": ("LV", "OAK"), "LAC": ("LAC", "SD"), "LA": ("LA", "STL"), "ARI": ("ARI",)}


def coach_career(games_csv: Path, coach: str, team: str, season: int) -> dict:
    """A head coach's career numbers before ``season`` from nflverse games.csv (1999 onwards; every 2026 head
    coach started after that): regular-season wins, losses and ties, seasons, seasons with this franchise,
    winning seasons, playoff wins and losses, Super Bowl appearances, wins and losses."""
    franchise = set(FRANCHISE_ALIASES.get(team, (team,)))
    w = l = t = pw = pl = sbw = sbl = 0
    per_season: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    with_team = set()
    for g in csv.DictReader(games_csv.open(encoding="utf-8")):
        if int(g["season"]) >= season:
            continue
        for side, other in (("home", "away"), ("away", "home")):
            if g[f"{side}_coach"] != coach or g[f"{side}_score"] in ("", None):
                continue
            mine, theirs = int(g[f"{side}_score"]), int(g[f"{other}_score"])
            if g["game_type"] == "REG":
                won, lost = mine > theirs, mine < theirs
                w, l, t = w + won, l + lost, t + (not won and not lost)
                per_season[g["season"]][0] += won
                per_season[g["season"]][1] += lost
                if g[f"{side}_team"] in franchise:
                    with_team.add(g["season"])
            else:
                pw, pl = pw + (mine > theirs), pl + (mine < theirs)
                if g["game_type"] == "SB":
                    sbw, sbl = sbw + (mine > theirs), sbl + (mine < theirs)
    return {"wins": w, "losses": l, "ties": t, "total_seasons": len(per_season),
            "seasons_with_team": len(with_team),
            "winning_seasons": sum(1 for won, lost in per_season.values() if won > lost),
            "playoff_wins": pw, "playoff_losses": pl, "super_bowls": sbw + sbl, "super_bowl_wins": sbw,
            "super_bowl_losses": sbl}


def games_coach_name(games_csv: Path, full: str, team: str, season: int, given: str | None) -> str:
    """The spelling games.csv uses for this head coach. ``roster.head_coach_games_name`` in the spec wins; else,
    when the team's coach in ``season`` differs from the spec's name only by a typo (difflib ratio 0.85 or more,
    e.g. games.csv's "Klint Kubliak" for Klint Kubiak), that spelling is used for the career lookup and the spec's
    spelling is what the game shows. A clearly different name is reported and the spec's name is kept."""
    import difflib
    if given:
        return str(given)
    franchise = set(FRANCHISE_ALIASES.get(team, (team,)))
    seen: dict[str, int] = defaultdict(int)
    for g in csv.DictReader(games_csv.open(encoding="utf-8")):
        if int(g["season"]) != season:
            continue
        for side in ("home", "away"):
            if g[f"{side}_team"] in franchise and g[f"{side}_coach"]:
                seen[g[f"{side}_coach"]] += 1
    if not seen or full in seen:
        return full
    listed = max(seen, key=seen.get)
    if difflib.SequenceMatcher(None, full.casefold(), listed.casefold()).ratio() >= 0.85:
        print(f"  games.csv spells the {team} {season} head coach {listed!r}: career numbers looked up under that "
              f"spelling, the game shows {full!r}")
        return listed
    print(f"  WARNING: games.csv lists {listed!r} as the {team} {season} head coach, the spec says {full!r}; "
          "set roster.head_coach_games_name if they are the same person")
    return full


def coach_entry(roster_cfg: dict, abbreviation: str, disc: str, nfl: Path | None = None,
                team: str = "", season: int = 2026) -> dict | None:
    """The head coach's name for the roster edits' ``coaches`` list. Coach names are written in place into their
    retail allocations (rr.apply_coach_names), so a first name longer than the retail one becomes its initial
    ("John" in "Tom"'s span -> "J."; the Coach Matchup screen shows the initial anyway). A last name longer than
    the retail one does not fit and is reported (the coach keeps the retail name until a coach-string writer that
    can move allocations exists). Checked here with a dry run on the retail roster."""
    full = str(roster_cfg.get("head_coach", "") or "").strip()
    if not full:
        return None
    first, _, last = full.partition(" ")
    base = bytearray(rr.load_image(disc).to_body())
    doc = rr.RosterDocument(bytes(base))
    for candidate in ({"first": first, "last": last}, {"first": first[:1] + ".", "last": last}):
        log: list[str] = []
        trial = bytearray(base)
        rr.apply_coach_names(trial, doc.teams, [dict(candidate, team=abbreviation)], log)
        if not log:
            print(f"  head coach: {candidate['first']} {candidate['last']}" +
                  ("" if candidate["first"] == first else f" (the retail span holds no '{first}')"))
            entry = dict(candidate, team=abbreviation, full_name=full)
            games = (nfl / "games.csv") if nfl else None
            if games is not None and games.is_file():
                lookup = games_coach_name(games, full, team, season, roster_cfg.get("head_coach_games_name"))
                entry["fields"] = coach_career(games, lookup, team, season)
                if lookup != full:
                    entry["games_name"] = lookup
                entry["career_source"] = f"nflverse games.csv, seasons before {season}"
                f = entry["fields"]
                print(f"  head coach career: {f['wins']}-{f['losses']}-{f['ties']} in {f['total_seasons']} seasons, "
                      f"playoffs {f['playoff_wins']}-{f['playoff_losses']}, Super Bowls won {f['super_bowl_wins']}")
            return entry
    print(f"  head coach {full!r} does not fit the retail spans: {log}")
    return None


def written_years_pro(row: dict) -> int:
    """The record's years pro for an nflverse roster row.

    nflverse ``years_exp`` counts completed seasons (a 2026 rookie is 0); the game's years pro counts the season in
    progress too (a rookie stores 1 and the card prints R, a 2025 draftee stores 2). Writing ``years_exp`` as it came
    made every 2026 draftee read 0, every 2025 draftee read R and every veteran one year low (Noah 2026-10-07, job f12).
    """
    return rr.years_pro_from_years_exp(row["years_exp"])


def body_for(weight: int) -> int:
    return 0 if weight < 205 else 1 if weight < 280 else 2


# roster.overrides fields that correct the player's nflverse row before the build reads it (spec name -> column)
OVERRIDE_SOURCE_FIELDS = {
    "jersey": "jersey_number", "jersey_number": "jersey_number", "height": "height", "weight": "weight",
    "birth_date": "birth_date", "college": "college", "years_exp": "years_exp", "years_pro": "years_exp",
    "position": "position", "depth_chart_position": "depth_chart_position", "first_name": "first_name",
    "last_name": "last_name", "full_name": "full_name", "status": "status"}


def apply_source_overrides(rows: list[dict], overrides: dict) -> list[str]:
    """``roster.overrides`` {gsis_id: {field: value}}: corrections to a player's nflverse row made before the build
    reads it (LAC Hayden Rucci wears 40 while roster_2026 repeats David Njoku's 83; job d4). Fields are the
    OVERRIDE_SOURCE_FIELDS or a rating (rr.RATING_BYTE_ORDER), which apply_rating_overrides sets after the ratings
    model. Returns one note per change for the receipt; an id not on the team's rows is a warning."""
    by_id = {r["gsis_id"]: r for r in rows}
    notes = []
    for pid, fields in (overrides or {}).items():
        unknown = [f for f in fields if f not in OVERRIDE_SOURCE_FIELDS and f not in rr.RATING_BYTE_ORDER]
        if unknown:
            raise SystemExit(f"roster.overrides {pid}: unknown field(s) {unknown}; use "
                             f"{sorted(OVERRIDE_SOURCE_FIELDS)} or a rating {list(rr.RATING_BYTE_ORDER)}")
        row = by_id.get(pid)
        if row is None:
            print(f"  WARNING: roster.overrides {pid} is not on the team's nflverse rows; override ignored")
            notes.append(f"{pid}: not on the team's rows (ignored)")
            continue
        for field, value in fields.items():
            if field in OVERRIDE_SOURCE_FIELDS:
                column = OVERRIDE_SOURCE_FIELDS[field]
                notes.append(f"{pid} {row['full_name']}: {column} {row.get(column, '')!r} -> {str(value)!r}")
                row[column] = str(value)
    return notes


def apply_rating_overrides(rows: list[dict], overrides: dict) -> list[str]:
    """The rating fields of ``roster.overrides`` (0..127), set after the ratings model."""
    notes = []
    by_id = {r["gsis_id"]: r for r in rows}
    for pid, fields in (overrides or {}).items():
        row = by_id.get(pid)
        for field, value in fields.items():
            if row is not None and field in rr.RATING_BYTE_ORDER:
                notes.append(f"{pid} {row['full_name']}: {field} {row['ratings'][field]} -> {int(value)}")
                row["ratings"][field] = max(0, min(127, int(value)))
    return notes


def build(args) -> int:
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    team_abbr = spec["team"]
    roster_cfg = spec.get("roster", {})
    season = int(roster_cfg.get("season", 2026))
    defense = roster_cfg.get("defense", "4-3")
    nfl = Path(args.nflverse)
    team_rows = [r for r in csv.DictReader((nfl / f"roster_{season}.csv").open(encoding="utf-8"))
                 if r["team"] == team_abbr]
    override_notes = apply_source_overrides(team_rows, roster_cfg.get("overrides", {}))
    rows = [r for r in team_rows if r["status"] in tuple(roster_cfg.get("statuses", ["ACT"]))]
    depth = depth_ranks(nfl / f"depth_charts_{season}.csv", team_abbr, roster_cfg.get("depth_since"))
    doc = rr.load_image(args.disc)
    team = next(t for t in doc.teams if t.abbreviation == roster_cfg.get("roster_abbreviation", team_abbr))
    records = sorted(doc.team_players(team.index), key=lambda p: p.index)
    if len(rows) > len(records):
        raise SystemExit(f"{len(rows)} players for {len(records)} records; trim the status list")
    filled = []
    if len(rows) < len(records):
        # every retail team has 53 records and a record left alone keeps its 2004 player, so an active list short of
        # 53 (a week's transactions) is filled from the practice squad: players on the season's depth charts first,
        # then the most experienced
        have = {r["gsis_id"] for r in rows}
        pool = [r for r in team_rows if r["status"] in tuple(roster_cfg.get("fill_statuses", ["DEV"]))
                and r["gsis_id"] not in have]
        pool.sort(key=lambda r: (depth.get(r["gsis_id"], ("", 99.0))[1], -int(float(r["years_exp"] or 0)),
                                 r["full_name"]))
        filled = pool[: len(records) - len(rows)]
        rows += filled
        if len(rows) < len(records):
            raise SystemExit(f"{len(rows)} players for {len(records)} records even after the practice squad")
        print(f"  filled {len(filled)} record(s) from the practice squad: {', '.join(r['full_name'] for r in filled)}")
    # position and depth for every source row
    for r in rows:
        slot, rank = depth.get(r["gsis_id"], ("", 99.0))
        r["slot"] = slot
        r["game_position"] = game_position(r, defense)
        r["depth_source"] = f"{slot}{rank + 1:.1f}" if rank < 99 else ""
        # a player listed only in a special-teams slot (a long snapper, a pure returner) sorts after every player
        # listed in a regular slot of the same 2K5 position (the long snapper is C3, never the starting centre)
        r["depth_rank_src"] = rank + (10.0 if slot in SPECIAL_SLOTS and r["game_position"] not in ("K", "P") else 0.0)
        r["slot_priority"] = SLOT_PRIORITY.get(slot, 5)
    # ratings (job m2's model on the previous season's statistics)
    rm = load_ratings_model(args.ratings_model)
    stats_season = int(roster_cfg.get("stats_season", season - 1))
    forties = merged_forty_sources(rm, args.forty_sources or [])
    stats = rm.SeasonStats.from_files(
        stats_season, str(nfl / f"stats_player_reg_{stats_season}.csv.gz"), str(nfl / f"roster_{stats_season}.csv"),
        depth_charts=str(nfl / f"depth_charts_{stats_season}.csv"), snap_counts=str(nfl / f"snap_counts_{stats_season}.csv"),
        combine=str(nfl / "combine.csv"), players=str(nfl / "players.csv"), forty_sources=forties)
    reference = rm.Reference.load()
    model_rows = []
    for r in rows:
        # the ratings model's "years_pro" key means completed seasons (0 = rookie: draft-position prior), i.e. nflverse
        # years_exp as it came; only the record write below converts to the game's convention (rookie = 1)
        model_rows.append({"position": r["game_position"], "gsis_id": r["gsis_id"], "weight": r["weight"],
                           "birth_date": r["birth_date"], "years_pro": r["years_exp"],
                           "draft_number": r.get("draft_number", ""), "depth": int(round(r["depth_rank_src"])) + 1,
                           "full_name": r["full_name"]})
    rated = rm.rate_players(model_rows, stats, reference)
    for r, m in zip(rows, rated):
        r["ratings"] = {k: int(m[k]) for k in rr.RATING_BYTE_ORDER}
        r["rating_basis"] = m.get("rating_basis", "")
    override_notes += apply_rating_overrides(rows, roster_cfg.get("overrides", {}))
    # records: keep a retail player's slot for the 2026 player of the same position family where possible
    by_family = defaultdict(list)
    for p in records:
        by_family[FAMILY[p.record.position_name if p.record.position_name in FAMILY else "ILB"]].append(p)
    for fam in by_family:
        by_family[fam].sort(key=lambda p: (p.record.values["depth_rank"], p.index))
    order = sorted(rows, key=lambda r: (NFLVERSE_DEPTH_ORDER.get(r["game_position"], 20), r["depth_rank_src"], r["slot_priority"]))
    assigned: dict[int, dict] = {}
    leftovers = []
    for r in order:
        pool = by_family.get(FAMILY[r["game_position"]], [])
        if pool:
            assigned[pool.pop(0).index] = r
        else:
            leftovers.append(r)
    spare = [p for fam in by_family.values() for p in fam]
    spare.sort(key=lambda p: p.index)
    for r, p in zip(leftovers, spare):
        assigned[p.index] = r
    record_by_index = {p.index: p for p in records}
    # announcer cues
    bank = rr.recorded_surname_ids()
    faces = json.loads(Path(args.faces).read_text(encoding="utf-8")) if args.faces else {}
    colleges_norm = {norm(c): i for i, c in enumerate(doc.colleges) if c}
    # per-position depth order inside the written document (by code)
    written_depth: dict[str, list] = defaultdict(list)
    for idx, r in assigned.items():
        written_depth[r["game_position"]].append((round(r["depth_rank_src"], 2), r["slot_priority"], r["full_name"], idx))
    rank_of = {}
    for pos, items in written_depth.items():
        for rank, (_, _, _, idx) in enumerate(sorted(items)):
            rank_of[idx] = rank
    # Names: the player-name pool is packed solid (no free bytes), so first point every team record at one short
    # name that other players keep using (which frees the team's old strings into merged blocks), then place the
    # new names longest first. apply_body replays the document in list order, so the written document carries the
    # same two passes (see ordered_document) and the replay allocates exactly as this dry run did.
    team_offsets = {p.offset for p in records}
    placeholder = min((p.last for p in doc.players if p.pool == "primary" and p.offset not in team_offsets
                       and p.last and len(p.last) >= 2), key=lambda t: (rr.encoded_size(t), t))
    was_names = {idx: (record_by_index[idx].first, record_by_index[idx].last) for idx in assigned}
    for idx in sorted(assigned):
        doc.set_name(record_by_index[idx], "first", placeholder)
        doc.set_name(record_by_index[idx], "last", placeholder)
    new_names, shortened = written_names(assigned)
    name_order = sorted(assigned, key=lambda i: (-max(rr.encoded_size(t) for t in new_names[i]), i))
    for idx in name_order:
        doc.set_name(record_by_index[idx], "first", new_names[idx][0])
        doc.set_name(record_by_index[idx], "last", new_names[idx][1])
    csv_rows = []
    for idx, r in sorted(assigned.items()):
        p = record_by_index[idx]
        rec = p.record
        was = " ".join(was_names[idx]).strip()
        first, last = new_names[idx]
        full = r["full_name"].strip()
        jersey = int(r["jersey_number"] or 0)
        weight = int(float(r["weight"] or 0))
        height = int(float(r["height"] or 0))
        birth = dt.date.fromisoformat(r["birth_date"]) if r.get("birth_date") else None
        doc.set_position(p, r["game_position"])
        rec.set("jersey", jersey)
        rec.set("height", height)
        rec.set("weight", weight)
        if birth:
            rec.set("birth_month", birth.month)
            rec.set("birth_day", birth.day)
            rec.set("birth_year", birth.year)
        rec.set("years_pro", written_years_pro(r))
        for k, v in r["ratings"].items():
            rec.set(k, max(0, min(127, v)))
        rank = min(rank_of[idx], rr.DEPTH_ROW_CAP)
        rec.set("depth_rank", rank)
        rec.set("depth_side", min(rr.DEPTH_SIDE_FOR_RANK.get(rank, rank), rr.DEPTH_ROW_CAP))
        rec.set("body", body_for(weight))
        # Match the full source surname before the game's display buffer shortens it.
        pbp, cue = pbp_for(source_names(r)[1], jersey, bank)
        rec.set("pbp_id", pbp)
        face = faces.get(r["gsis_id"], {})
        if "photo_id" in face:
            rec.set("photo_id", int(face["photo_id"]))
        if "skin_tone" in face:
            # keep the record's skin group (bits 3-4), set the tone (bits 0-2)
            group = rec.get("skin") & ~7
            rec.set("skin", group | int(face["skin_tone"]))
        if "dreads" in face:
            rec.set("dreads", int(face["dreads"]))
        college = ""
        for c in reversed([c.strip() for c in (r.get("college") or "").split(";") if c.strip()]):
            if norm(c) in colleges_norm:
                doc.set_college(p, colleges_norm[norm(c)])
                college = doc.colleges[colleges_norm[norm(c)]]
                break
        csv_rows.append({
            "pool": p.pool, "index": p.index, "was": was, "gsis_id": r["gsis_id"], "source_name": full,
            "written_first": p.first, "written_last": p.last, "source_position": f"{r['position']}/{r.get('depth_chart_position','')}",
            "written_position": rr.position_name(rec.values["position"], "one_pool"), "source_jersey": r["jersey_number"],
            "written_jersey": rec.values["jersey"], "source_height": r["height"], "written_height": rec.values["height"],
            "source_weight": r["weight"], "written_weight": rec.get("weight"), "source_birth_date": r["birth_date"],
            "written_birth": f"{rec.get('birth_year') if hasattr(rec, 'get') else ''}-{rec.values['birth_month']:02d}-{rec.values['birth_day']:02d}",
            "source_college": r.get("college", ""), "written_college": college, "source_years_exp": r["years_exp"],
            "written_years_pro": rec.values["years_pro"], "depth_source": r["depth_source"], "written_depth_rank": rec.values["depth_rank"],
            "pbp_id": pbp, "pbp_cue": cue, "photo_id": rec.values["photo_id"], "skin": rec.get("skin"),
            "overall_estimate": "", **{f"r_{k}": rec.values[k] for k in rr.RATING_BYTE_ORDER},
            "rating_basis": r["rating_basis"] if isinstance(r["rating_basis"], str) else json.dumps(r["rating_basis"])})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    edits = ordered_document(rr.edits_document(doc, name=f"{spec['name']} {season} roster (job u1)", author="SOFTDRINK"),
                             placeholder, name_order)
    coach = coach_entry(roster_cfg, team.abbreviation, args.disc, nfl, team_abbr, season)
    if coach:
        edits["coaches"] = [coach]
    (out / "roster_edits.json").write_text(json.dumps(edits, indent=1) + "\n", encoding="utf-8", newline="\n")
    with (out / "roster_rows.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(csv_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    receipt = {"schema": SCHEMA, "team": team_abbr, "season": season, "stats_season": stats_season,
               "defense": defense, "players": len(csv_rows), "records": len(records),
               "source_roster_sha256": hashlib.sha256((nfl / f"roster_{season}.csv").read_bytes()).hexdigest(),
               "ratings_model": getattr(rm, "MODEL_VERSION", "?"), "ratings_model_path": str(Path(rm.__file__).resolve()),
               "ratings_reference_sha256": hashlib.sha256(Path(rm.DEFAULT_REFERENCE).read_bytes()).hexdigest(),
               "edits_players": len(edits["edits"]), "moves": len(edits.get("moves", [])),
               "filled_from_practice_squad": [r["full_name"] for r in filled], "shortened_names": shortened,
               "forty_sources": [str(Path(p).resolve()) for p in (args.forty_sources or [])],
               "speed_sources": speed_source_counts(rows), "overrides": override_notes}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=1))
    return 0


def merge(args) -> int:
    """One roster-edits document for the build: every team document in order, then the league-wide abilities
    tiers recomputed on the edited roster (the ultimate recipe's abilities document was computed on the retail
    roster and would give a replaced 2004 star's tier to whoever now holds his record), and the new X-Factor list
    for ``player_tags``."""
    from mod_editor.core import nfl2k5_abilities_editor as ab
    doc0 = rr.load_image(args.disc)
    base = doc0.to_body()
    # The name pool has no free bytes, and a team whose 2026 names are longer than its 2004 names can only grow
    # into bytes other teams freed. So the league document releases EVERY team's old names first, then writes all
    # the new names longest first (one best-fit pass over the whole league), then everything else.
    releases: list[dict] = []
    finals: list[dict] = []
    rest: list[dict] = []
    moves: list[dict] = []
    coaches: list[dict] = []
    notes = []
    for path in args.team:
        team_doc = json.loads(Path(path).read_text(encoding="utf-8"))
        n = int(team_doc.get("name_passes", {}).get("release_entries", 0))
        releases += team_doc["edits"][:n]
        finals += team_doc["edits"][n:2 * n]
        rest += team_doc["edits"][2 * n:]
        moves += team_doc.get("moves") or []
        coaches += team_doc.get("coaches") or []
        notes.append({"team_document": str(path), "entries": len(team_doc["edits"]), "release_entries": n})

    def longest(e: dict) -> int:
        names = e.get("names") or {}
        return max((rr.encoded_size(names[k]) for k in ("first", "last") if names.get(k)), default=0)

    finals.sort(key=lambda e: (-longest(e), e["pool"], e["index"]))
    merged_edits: list[dict] = releases + finals + rest
    body, receipt = rr.apply_body(base, {"schema": rr.EDITS_SCHEMA, "name": "2026 teams", "edits": merged_edits,
                                         "moves": moves, "coaches": coaches})
    if receipt["log"]:
        raise SystemExit(f"league replay log is not clean: {receipt['log'][:5]}")
    notes.append({"league_replay": {"players_changed": receipt["players_changed"],
                                    "fields_written": receipt["fields_written"]}})
    team_final: dict[tuple[str, int], dict] = {(e["pool"], e["index"]): e for e in merged_edits if e.get("fields")}
    doc1 = rr.RosterDocument(body)
    plan = ab.plan_auto_assign(doc1, top_n=args.top_n)
    ab.apply_plan(doc1, plan)
    abil = rr.edits_between(body, doc1.to_body(), name="abilities tiers")
    added = moved_in = 0
    for e in abil["edits"]:
        key = (e["pool"], e["index"])
        if key in team_final:
            team_final[key]["fields"].update(e["fields"])
            moved_in += 1
        else:
            merged_edits.append(e)
            added += 1
    tags = sorted({str(r["identity"]["index"]) for r in plan["rows"] if r.get("rank") == 1
                   and r["identity"].get("pool") == "primary"}, key=int)
    out = {"schema": rr.EDITS_SCHEMA, "name": "2026 teams + abilities tiers (job u1)", "author": "SOFTDRINK",
           "source_body_sha256": hashlib.sha256(base).hexdigest(), "players": len(doc0.players),
           "edits": merged_edits, "moves": moves, "coaches": coaches}
    # replay the merged document on the retail body once more: it must land cleanly
    final_body, final_receipt = rr.apply_body(base, out)
    if final_receipt["log"]:
        raise SystemExit(f"merged replay log is not clean: {final_receipt['log'][:5]}")
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    summary = {"schema": SCHEMA + "#merge", "teams": notes, "abilities_rows": len(plan["rows"]),
               "abilities_edits_other_players": added, "abilities_folded_into_team_entries": moved_in,
               "player_tags": tags, "merged_entries": len(merged_edits),
               "final_body_sha256": hashlib.sha256(final_body).hexdigest()}
    Path(args.out).with_suffix(".receipt.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8",
                                                          newline="\n")
    print(json.dumps(summary, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--spec", required=True)
    b.add_argument("--disc", required=True, help="the user's retail disc image (read-only)")
    b.add_argument("--nflverse", required=True, help="folder with roster_<season>.csv, depth charts, stats, snaps")
    b.add_argument("--ratings-model", help="path of nfl2k5_ratings_model.py when the stack does not carry it yet")
    b.add_argument("--forty-sources", action="append",
                   help="cited 40 times, nfl2k5.forty_sources.v1 (job m2's schema; repeatable, merged in order)")
    b.add_argument("--faces", help="face and portrait slot plan (gsis_id -> photo_id, skin_tone, dreads)")
    b.add_argument("--out", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--disc", required=True)
    m.add_argument("--team", action="append", required=True, help="a team's roster_edits.json (repeatable)")
    m.add_argument("--top-n", type=int, default=10)
    m.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    return build(args) if args.command == "build" else merge(args)


if __name__ == "__main__":
    sys.exit(main())
