#!/usr/bin/env python3
"""Job F5 (beta 77): build data/nfl2k5_honors_2026.json, the sourced award history of the players on the 2026 roster.

Development tool; the Studio only reads the generated JSON. Inputs (none are committed):
  --sources DIR   Wikipedia wikitext saved as <key>.wiki plus provenance.json (title, fixed revision URL, SHA-256 of
                  the exact text read): AP MVP, OPOY, DPOY, Rookie of the Year (offense + defense), Super Bowl MVP,
                  the Super Bowl champions list, the annual rushing leaders, and per season 2005..2025 the
                  "<year> All-Pro Team" and Pro Bowl / Pro Bowl Games pages.
  --nflverse DIR  nflverse annual rosters roster_<season>.csv (2005..2026), github.com/nflverse/nflverse-data
                  release "rosters"; identities (gsis ids, birth dates, teams) and the Super Bowl-week rosters.
  --cohort FILE   the b77 F12 cohort (tools/b77/f12_cohort.json on job/b77-f12): the 2,072 modern primary records of
                  the v0.5 roster, each pinned by index, name and birth date and matched to nflverse 2026/2025.

Counting rules (stated in the output):
  * MVP, OPOY, DPOY, OROY, DROY: the Associated Press award for that season.
  * Super Bowl MVP: the game's MVP; the season is the one the game ends.
  * Rushing title: the season's NFL rushing yards leader.
  * All-Pro: AP first team only (an "AP" selector on the season's All-Pro Team page; AP-2 is second team).
  * Pro Bowl: every player named on the AFC or NFC roster of that season's Pro Bowl (starters, reserves, injury and
    Super Bowl replacements, and those selected who did not take part), as the game page lists them.
  * Super Bowl: the champion (Super Bowl champions list) and its Super Bowl-week roster in nflverse with status ACT
    (active) or INA (inactive): the 53-man roster; injured reserve and practice squad are not counted.
Identity: award name (+ team) -> the season's nflverse row -> gsis id -> the 2026 roster record (birth date and
surname, or a unique name when the two sources disagree on the birth date).

  python3 tools/b77/f5_honors_sources.py --sources S --nflverse N --cohort C --out data/nfl2k5_honors_2026.json
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata

SEASONS = range(2005, 2026)
BASE_YEAR = 2026
NFLVERSE_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_%d.csv"


# --- wikitext parsing ---------------------------------------------------------------------------
TEAMS = ("Chiefs Ravens Packers Bills Rams Eagles Seahawks Patriots Cowboys Steelers Broncos Saints Colts Vikings Bears "
         "Lions Giants Jets Dolphins Titans Texans Jaguars Browns Bengals Raiders Chargers 49ers Cardinals Falcons "
         "Panthers Buccaneers Commanders Redskins").split()
POSITION_WORDS = re.compile(r"^(Quarterback|Running back|Wide receiver|Tight end|Defensive (end|tackle|back|lineman)|Linebacker|"
                            r"Outside linebacker|Inside linebacker|Middle linebacker|Cornerback|Safety|Free safety|Strong safety|"
                            r"Offensive (tackle|guard|lineman|line)|Center|Guard|Tackle|Placekicker|Kicker|Punter|Fullback|Return specialist|"
                            r"Kick returner|Punt returner|Long snapper|Halfback|Edge rusher|Special teams|Special teamer|"
                            r"Kickoff returner|Nose tackle|Pass rusher)$", re.I)

def is_player_link(target):
    if target.startswith(("File:", "Image:", "Category:")) or re.search(r"\bseason\b|Super Bowl|Pro Bowl|All-Pro|NFL|"
                                                                     r"National Football|American Football|AFC|NFC", target):
        return False
    base = re.sub(r"\s*\(.*\)$", "", target).strip()
    if POSITION_WORDS.match(base) or any(base.endswith(" " + t) or base == t for t in TEAMS):
        return False
    if re.search(r"\((gridiron|American) football\)$", target) and POSITION_WORDS.match(base):
        return False
    return True

def players_in(text):
    out = []
    for m in re.finditer(r"\{\{\s*sortname\s*\|([^|}]+)\|([^|}]+)(?:\|([^|}]+))?(?:\|[^}]*)?\}\}|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", text):
        if m.group(1):
            first, last, target = m.group(1).strip(), m.group(2).strip(), (m.group(3) or "").strip()
            out.append({"name": first + " " + last, "target": target or first + " " + last})
        else:
            target, label = m.group(4).strip(), (m.group(5) or m.group(4)).strip()
            if not is_player_link(target):
                continue
            out.append({"name": re.sub(r"\s*\(.*\)$", "", label), "target": target})
    return out
def rows(text):
    for chunk in re.split(r"\n\|-[^\n]*", text):
        yield chunk
def season_rows(text, lo=2005, hi=2025):
    out = []
    for chunk in rows(text):
        body = chunk.strip()
        m = re.search(r"\[\[(\d{4}) NFL season\|", body)
        if not m: continue
        # the season must be the row's first cell
        first_cell = re.split(r"\n[|!]|\|\|", body.lstrip("|! \n"), maxsplit=1)[0]
        if m.group(1) not in first_cell: continue
        season = int(m.group(1))
        if not lo <= season <= hi: continue
        rest = body[m.end():]
        ps = players_in(rest)
        if ps:
            out.append((season, ps[0], body))
    return out
def row_team(body):
    m = re.search(r"\[\[\d{4} ([^\]|]+?) season\|", body.split("NFL season", 1)[-1])
    if m:
        return m.group(1)
    for t in re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", body):
        if any(t.endswith(" " + x) for x in TEAMS):
            return t
    return None

def parse_simple(text):
    return [{"season": s, "name": p["name"], "target": p["target"], "team": row_team(b)} for s, p, b in season_rows(text)]

LINK = re.compile(r"\{\{\s*sortname\s*\|([^|}]+)\|([^|}]+)(?:\|([^|}]+))?(?:\|[^}]*)?\}\}|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
TEAMLINK = re.compile(r"\[\[(\d{4}) ([^\]|]+?) season\|([^\]]+)\]\]|\[\[([^\]|]+?)\]\]")

def entry_player(text):
    for m in LINK.finditer(text):
        if m.group(1):
            return (m.group(1).strip() + " " + m.group(2).strip()), (m.group(3) or "").strip()
        target, label = m.group(4).strip(), (m.group(5) or m.group(4)).strip()
        if not is_player_link(target):
            continue
        return re.sub(r"\s*\(.*\)$", "", label), target
    plain = re.sub(r"<[^>]+>|\{\{[^}]*\}\}|'''?", "", text).strip()
    name = plain.split(",")[0].strip()
    return (name, "") if name else (None, None)

def team_of(text):
    m = re.search(r"\[\[(\d{4}) ([^\]|]+?) season\|", text)
    if m:
        return m.group(2)
    names = [t for t in re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", text)
             if any(t.endswith(" " + x) for x in TEAMS)]
    return names[0] if names else None

NOISE = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>|\{\{\s*(?:efn|efn-ua|refn|sfn|ref label|Ref label|note label|sup)\b(?:[^{}]|\{\{[^{}]*\}\})*\}\}", re.I | re.S)

def clean(text):
    return NOISE.sub("", text)

def allpro(text, season):
    text = clean(text)
    for stop in ("==Key==", "== Key ==", "==Position differences==", "==By NFL Team==", "== By NFL team ==", "==By team==", "==References=="):
        if stop in text:
            text = text[:text.index(stop)]
    out = []
    for cell in re.split(r"\n\|-|\n\||\|\|", text):
        for entry in re.split(r"<br\s*/?>", cell, flags=re.I):
            m = re.search(r"\(([^()]*)\)\s*$", entry.strip())
            if not m:
                continue
            selectors = [s.strip() for s in m.group(1).split(",")]
            if "AP" not in selectors:
                continue
            name, target = entry_player(entry[:m.start()])
            if name and not any(o["name"] == name for o in out):
                out.append({"season": season, "name": name, "target": target, "team": team_of(entry)})
    return out

ROSTER_HEADING = re.compile(r"AFC|NFC|Roster|Offense|Defense|Special teams|Specialists|^Team |^Selected", re.I)
ENTRY = re.compile(r"\[\[[^\]]+\]\]'*\s*,\s*\[\[")

def probowl(text, season):
    out, inside = [], False
    for line in clean(text).split("\n"):
        h = re.match(r"^(=+)\s*(.*?)\s*\1\s*$", line)
        if h:
            inside = bool(ROSTER_HEADING.search(h.group(2))) and "selections" not in h.group(2).lower()
            continue
        if not inside or "coach" in line.lower():
            continue
        nfl = re.search(r"\{\{\s*NFLplayer\s*\|[^|]*\|\s*([^|}]+?)\s*\|", line)
        if nfl:
            out.append({"season": season, "name": re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", nfl.group(1)).strip(),
                        "target": "", "team": team_of(line), "note": "replacement" if "replacement" in line.lower() else ""})
            continue
        for entry in re.split(r"<br\s*/?>", line, flags=re.I):
            if not ENTRY.search(entry):
                continue
            name, target = entry_player(entry)
            if name:
                out.append({"season": season, "name": name, "target": target, "team": team_of(entry),
                            "note": "replacement" if "replacement" in entry.lower() else ""})
    return out

def rushing(text):
    text = text[text.index("==List of NFL rushing title winners=="):]
    return [{"season": s, "name": p["name"], "target": p["target"]} for s, p, _b in season_rows(text)]
def sbmvp(text):
    out = []
    for s, p, body in season_rows(text):
        team = re.search(r"\[\[\d{4} ([^\]|]+?) season\|", body)
        out.append({"season": s, "name": p["name"], "target": p["target"], "team": team.group(1) if team else None})
    return out
def champions(text):
    out = {}
    for m in re.finditer(r"\(\[\[(\d{4}) NFL season\|\d{4}\]\]\)\s*\n\|[^\n]*?\[\[\1 ([^\]|]+?) season\|", text):
        s = int(m.group(1))
        if 2005 <= s <= 2025 and s not in out:
            out[s] = m.group(2)
    return out

# --- identities -------------------------------------------------------------------------------------
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}
TEAM_CODES = {
 "Arizona Cardinals": {"ARZ", "ARI"}, "Atlanta Falcons": {"ATL"}, "Baltimore Ravens": {"BLT", "BAL"}, "Buffalo Bills": {"BUF"},
 "Carolina Panthers": {"CAR"}, "Chicago Bears": {"CHI"}, "Cincinnati Bengals": {"CIN"}, "Cleveland Browns": {"CLV", "CLE"},
 "Dallas Cowboys": {"DAL"}, "Denver Broncos": {"DEN"}, "Detroit Lions": {"DET"}, "Green Bay Packers": {"GB"},
 "Houston Texans": {"HST", "HOU"}, "Indianapolis Colts": {"IND"}, "Jacksonville Jaguars": {"JAX"}, "Kansas City Chiefs": {"KC"},
 "Oakland Raiders": {"OAK", "LV"}, "Las Vegas Raiders": {"OAK", "LV"}, "San Diego Chargers": {"SD", "LAC"}, "Los Angeles Chargers": {"SD", "LAC"},
 "St. Louis Rams": {"SL", "LA"}, "Los Angeles Rams": {"SL", "LA"}, "Miami Dolphins": {"MIA"}, "Minnesota Vikings": {"MIN"},
 "New England Patriots": {"NE"}, "New Orleans Saints": {"NO"}, "New York Giants": {"NYG"}, "New York Jets": {"NYJ"},
 "Philadelphia Eagles": {"PHI"}, "Pittsburgh Steelers": {"PIT"}, "San Francisco 49ers": {"SF"}, "Seattle Seahawks": {"SEA"},
 "Tampa Bay Buccaneers": {"TB"}, "Tennessee Titans": {"TEN"}, "Washington Redskins": {"WAS"}, "Washington Football Team": {"WAS"},
 "Washington Commanders": {"WAS"}, "Washington": {"WAS"},
}
def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'’`]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in SUFFIX]
    # join runs of single letters (initials): "t j watt" -> "tj watt"
    out, buf = [], ""
    for t in toks:
        if len(t) == 1:
            buf += t
        else:
            if buf: out.append(buf); buf = ""
            out.append(t)
    if buf: out.append(buf)
    return " ".join(out)
def last_key(last):
    return norm(last)
cohort_by_birth = collections.defaultdict(list)
cohort_by_name = collections.defaultdict(list)
NFLVERSE = None

def load_cohort(records):
    for index, first, last, birth, years_pro, basis in records:
        rec = {"index": index, "first": first, "last": last, "birth_date": birth, "years_pro_v05": years_pro, "basis": basis}
        cohort_by_birth[birth].append(rec)
        cohort_by_name[norm(first + " " + last)].append(rec)
_rosters = {}
def roster(season):
    if season not in _rosters:
        rows = list(csv.DictReader(open(Path(NFLVERSE) / ("roster_%d.csv" % season), encoding="utf-8")))
        for r in rows:
            r["_keys"] = {norm(r["full_name"]), norm((r.get("football_name") or r["first_name"]) + " " + r["last_name"]),
                          norm(r["first_name"] + " " + r["last_name"])}
        _rosters[season] = rows
    return _rosters[season]
def cohort_for(row):
    cands = [c for c in cohort_by_birth.get(row["birth_date"], []) if last_key(c["last"]) == last_key(row["last_name"])
             or norm(c["first"] + " " + c["last"]) in row["_keys"]]
    return cands[0] if len(cands) == 1 else None
# --- gsis identity (b): cohort -> nflverse gsis via the 2026 / 2025 rosters (the files F12 matched against) ---
_gsis = None
def cohort_gsis():
    global _gsis
    if _gsis is None:
        _gsis = {}
        for season in (2026, 2025):
            rows = roster(season)
            by_birth = collections.defaultdict(list)
            for r in rows:
                by_birth[r["birth_date"]].append(r)
            for recs in cohort_by_birth.values():
                for c in recs:
                    if c["index"] in {v["index"] for v in _gsis.values()}:
                        continue
                    cands = {r["gsis_id"] for r in by_birth.get(c["birth_date"], [])
                             if r["gsis_id"] and (last_key(r["last_name"]) == last_key(c["last"])
                                                  or norm(c["first"] + " " + c["last"]) in r["_keys"])}
                    if len(cands) == 1:
                        _gsis.setdefault(cands.pop(), c)
            # name-only, unique in both, when the birth dates disagree between sources
            names = collections.defaultdict(set)
            for r in rows:
                if r["gsis_id"]:
                    for k in r["_keys"]:
                        names[k].add(r["gsis_id"])
            taken = {v["index"] for v in _gsis.values()}
            for key, recs in cohort_by_name.items():
                if len(recs) == 1 and recs[0]["index"] not in taken and len(names.get(key, ())) == 1:
                    g = next(iter(names[key]))
                    if g not in _gsis:
                        _gsis[g] = dict(recs[0], gsis_note="name only (birth dates differ)")
    return _gsis

def resolve2(season, name, team=None):
    key = norm(name)
    codes = TEAM_CODES.get(team or "", set())
    rows = [r for r in roster(season) if key in r["_keys"]]
    if len(rows) > 1 and codes:
        rows = [r for r in rows if r["team"] in codes] or rows
    how = "name"
    if not rows and codes:
        surname = key.split()[-1] if key else ""
        rows = [r for r in roster(season) if r["team"] in codes and last_key(r["last_name"]) == surname]
        how = "team+surname"
    ids = {r["gsis_id"] for r in rows if r["gsis_id"]}
    if len(ids) != 1:
        return None, None, ("ambiguous" if len(ids) > 1 else "no nflverse %d row" % season) + " (%s)" % how
    gsis = ids.pop()
    row = next(r for r in rows if r["gsis_id"] == gsis)
    c = cohort_gsis().get(gsis)
    if not c:
        return None, row, "not on the 2026 roster"
    return c, row, "nflverse %d %s, gsis %s%s" % (season, how, gsis, (" (" + c["gsis_note"] + ")") if c.get("gsis_note") else "")


def build(sources: Path, nflverse: Path, cohort_path: Path) -> dict:
    global NFLVERSE
    NFLVERSE = nflverse
    cohort = json.loads(Path(cohort_path).read_text(encoding="utf-8"))
    load_cohort(cohort["records"])
    prov = json.loads((sources / "provenance.json").read_text(encoding="utf-8"))

    def text(key):
        raw = (sources / (key + ".wiki")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != prov[key]["sha256"]:
            raise SystemExit(f"{key}: the saved text differs from its pinned revision")
        return raw.decode("utf-8")

    roy = re.split(r"\n==+\s*Defensive", text("roy"), maxsplit=1)
    individual = {"mvp": parse_simple(text("mvp")), "opoy": parse_simple(text("opoy")), "dpoy": parse_simple(text("dpoy")),
                  "oroy": parse_simple(roy[0]), "droy": parse_simple(roy[1])}
    lists = {"all_pro": [], "pro_bowl": []}
    for season in SEASONS:
        lists["all_pro"] += allpro(text("allpro_%d" % season), season)
        lists["pro_bowl"] += probowl(text("probowl_%d" % season), season)
    sources_out = {}

    def wiki(key):
        p = prov[key]
        sources_out["wiki_" + key] = {"title": p["title"], "url": p["url"], "revision": p["revid"],
                                      "revision_time": p["timestamp"], "sha256": p["sha256"], "publisher": "Wikipedia"}
        return "wiki_" + key

    events, skipped = [], []

    def add(honor, season, name, team, source):
        c, row, why = resolve2(season, name, team)
        if c is None:
            skipped.append({"honor": honor, "season": season, "name": name, "team": team, "reason": why})
            return
        events.append({"index": c["index"], "first": c["first"], "last": c["last"], "birth_date": c["birth_date"],
                       "season": season, "honor": honor, "source": source, "match": why})

    for honor, key in (("mvp", "mvp"), ("opoy", "opoy"), ("dpoy", "dpoy"), ("oroy", "roy"), ("droy", "roy")):
        for r in individual[honor]:
            add(honor, r["season"], r["name"], r.get("team"), wiki(key))
    for r in sbmvp(text("sbmvp")):
        add("super_bowl_mvp", r["season"], r["name"], r.get("team"), wiki("sbmvp"))
    for r in rushing(text("rushing")):
        add("rushing_title", r["season"], r["name"], r.get("team"), wiki("rushing"))
    for honor, prefix in (("all_pro", "allpro"), ("pro_bowl", "probowl")):
        for r in lists[honor]:
            add(honor, r["season"], r["name"], r.get("team"), wiki("%s_%d" % (prefix, r["season"])))
    champs_key = wiki("sbchamps")
    for season, team in sorted(champions(text("sbchamps")).items()):
        path = Path(nflverse) / ("roster_%d.csv" % season)
        key = "nflverse_roster_%d" % season
        sources_out[key] = {"title": "nflverse annual roster %d (Super Bowl-week rows)" % season,
                            "url": NFLVERSE_RELEASE % season, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "publisher": "nflverse", "champion": team, "champion_source": champs_key}
        for row in roster(season):
            if row["team"] in TEAM_CODES[team] and row["game_type"] == "SB" and row["status"] in ("ACT", "INA"):
                c = cohort_gsis().get(row["gsis_id"])
                if c:
                    events.append({"index": c["index"], "first": c["first"], "last": c["last"],
                                   "birth_date": c["birth_date"], "season": season, "honor": "super_bowl", "source": key,
                                   "match": "nflverse %d Super Bowl week %s %s, gsis %s" % (season, row["team"], row["status"], row["gsis_id"])})
    for season in (2025, 2026):
        path = Path(nflverse) / ("roster_%d.csv" % season)
        sources_out.setdefault("nflverse_roster_%d" % season, {"title": "nflverse annual roster %d (identities)" % season,
                               "url": NFLVERSE_RELEASE % season, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                               "publisher": "nflverse"})
    players, seen = {}, set()
    for e in events:
        k = (e["index"], e["honor"], e["season"])
        if k in seen:
            continue
        seen.add(k)
        p = players.setdefault(e["index"], {"pool": "primary", "index": e["index"], "first": e["first"], "last": e["last"],
                                            "birth_date": e["birth_date"], "honors": []})
        p["honors"].append({"season": e["season"], "honor": e["honor"], "source": e["source"], "match": e["match"]})
    for p in players.values():
        p["honors"].sort(key=lambda h: (h["season"], h["honor"]))
    counts = collections.Counter(h["honor"] for p in players.values() for h in p["honors"])
    return {"schema": "nfl2k5_honors_history/v1", "base_year": BASE_YEAR,
            "built_from": {"cohort": {"file": "tools/b77/f12_cohort.json (job/b77-f12)",
                                      "sha256": hashlib.sha256(Path(cohort_path).read_bytes()).hexdigest(),
                                      "rost_body_sha256": cohort["rost_body_sha256"]}},
            "rules": {"mvp": "AP NFL Most Valuable Player", "opoy": "AP NFL Offensive Player of the Year",
                      "dpoy": "AP NFL Defensive Player of the Year", "oroy": "AP NFL Offensive Rookie of the Year",
                      "droy": "AP NFL Defensive Rookie of the Year", "super_bowl_mvp": "Super Bowl MVP (season the game ends)",
                      "rushing_title": "NFL rushing yards leader of the season",
                      "all_pro": "AP first-team All-Pro (selector AP on the season's All-Pro Team page; AP-2 excluded)",
                      "pro_bowl": "named on the AFC or NFC Pro Bowl roster of the season (starters, reserves, replacements, selected but not playing)",
                      "super_bowl": "champion's Super Bowl-week nflverse roster, status ACT or INA (53-man roster; IR and practice squad excluded)"},
            "counts": dict(sorted(counts.items())), "players": sorted(players.values(), key=lambda p: p["index"]),
            "sources": dict(sorted(sources_out.items())),
            "not_on_the_roster": len([s for s in skipped if s["reason"] == "not on the 2026 roster"]),
            "unresolved": [s for s in skipped if s["reason"] != "not on the 2026 roster"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--nflverse", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    data = build(args.sources, args.nflverse, args.cohort)
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(data["counts"]), len(data["players"]), "players")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
