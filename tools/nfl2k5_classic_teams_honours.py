#!/usr/bin/env python3
"""Sourced season honours of the classic teams' players (job ct1, coordinator 10/17), and the OVR floors they set.

Writes data/nfl2k5_classic_teams/honours.json from fixed-revision Wikipedia pages (the All-Pro team and the Pro Bowl
of the season, the AP MVP / OPOY / DPOY lists; the same revisions the honours history job f5 pinned, read from its
cache) and the season's league leaders from nflverse player statistics (CC-BY-4.0). Every honour carries its source
key and the exact source line, so tests can check it against the page.

The rules (one floor per player, the highest of his honours) are deliberately simple:

    MVP 95 | OPOY or DPOY 93 | AP first-team All-Pro 90 | NFL leader (passing yards or TDs, rushing yards,
    receiving yards, sacks, interceptions) 90 | AP second-team All-Pro 87 | Pro Bowl 84

The floor is on the game's own integer overall (nfl2k5_my_career_prospects.native_overall). The classic team
generator also hands each honoured player to the ratings model as an honour level (AP1 for MVP/OPOY/DPOY/leaders/AP1,
AP2, PB), the model's existing input; the shared model itself is not changed.

  nfl2k5_classic_teams_honours.py --sources F5_CACHE_DIR --inputs NFLVERSE_DIR [--check]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/nfl2k5_classic_teams"
OUT = DATA / "honours.json"
RULES = {"MVP": 95, "OPOY": 93, "DPOY": 93, "AP1": 90, "LEADER": 90, "AP2": 87, "PB": 84}
MODEL_LEVEL = {"MVP": "AP1", "OPOY": "AP1", "DPOY": "AP1", "AP1": "AP1", "LEADER": "AP1", "AP2": "AP2", "PB": "PB"}
LEADER_STATS = {"passing_yards": "passing yards", "passing_tds": "passing touchdowns", "rushing_yards": "rushing yards",
                "receiving_yards": "receiving yards", "def_sacks": "sacks", "def_interceptions": "interceptions"}
AWARDS = {"MVP": "mvp", "OPOY": "opoy", "DPOY": "dpoy"}
FULL_NAMES = {"titans": "Tennessee Titans", "giants": "New York Giants", "browns": "Cleveland Browns",
              "buccaneers": "Tampa Bay Buccaneers", "colts": "Indianapolis Colts", "chargers": "San Diego Chargers",
              "eagles": "Philadelphia Eagles", "lions": "Detroit Lions", "steelers": "Pittsburgh Steelers",
              "bears": "Chicago Bears", "packers": "Green Bay Packers", "seahawks": "Seattle Seahawks",
              "panthers": "Carolina Panthers", "broncos": "Denver Broncos", "patriots": "New England Patriots",
              "ravens": "Baltimore Ravens", "chiefs": "Kansas City Chiefs"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


SUFFIX = r"(\s+(Jr\.?|Sr\.?|II|III|IV))?"     # a page may add or drop a generational suffix


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


def plain(wiki: str) -> str:
    """Wiki markup to plain text: links to their display text, templates and emphasis removed."""
    t = re.sub(r"\{\{sortname\|([^|}]*)\|([^|}]*)(\|[^}]*)?\}\}", r"\1 \2", wiki)
    t = re.sub(r"\{\{NFLplayer\|[^|}]*\|\s*([^|}]+?)\s*(\|[^}]*)?\}\}", r"\1, ", t)
    t = re.sub(r"\{\{[Ss]mall\|[^}]*\}\}", " ", t)
    t = re.sub(r"\{\{[^}]*\}\}", " ", t)
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)
    t = t.replace("'''", "").replace("''", "")
    t = re.sub(r"<[^>]*>", " ", t)
    return fold(t)


def name_variants(row, source_name):
    first, last = row["first"], row["last"]
    out = {fold(f"{first} {last}"), fold(source_name)}
    for n in list(out):
        out.add(re.sub(r"\s+(Jr\.?|Sr\.?|II|III|IV)$", "", n))
    return {n for n in out if n}


def items(text):
    """Every '<br>'-separated item of every table cell line (a line that starts with '|')."""
    for line in text.splitlines():
        if not line.startswith(("|", "*", "!")) or line.startswith(("|-", "|}", "!-")):
            continue
        for item in re.split(r"<br\s*/?>", line, flags=re.I):
            yield line, item


def named(item_plain, names):
    for n in names:
        if re.search(r"(^|[\s|'(])" + re.escape(n) + SUFFIX + r"\s*[,(]", item_plain):
            return n
    return None


def all_pro(text, team_full, names):
    found = []
    for line, item in items(text):
        if team_full.lower() not in item.lower():
            continue
        p = plain(item)
        if not named(p, names):
            continue
        tags = p[p.rfind("(") + 1:] if "(" in p else ""
        if "AP-2" in tags:
            found.append(("AP2", line.strip()))
        elif re.search(r"\bAP\b(?!-)", tags):
            found.append(("AP1", line.strip()))
    return found


def pro_bowl(text, team_full, names):
    for line, item in items(text):
        if team_full.lower() in item.lower() and named(plain(item), names):
            return line.strip()
    return None


def award(text, season, names):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if f"[[{season} NFL season|{season}]]" in line:
            for follow in lines[i:i + 6]:
                if follow.startswith("|-") and follow is not lines[i]:
                    break
                p = plain(follow)
                if any(re.search(r"(^|[\s|])" + re.escape(n) + SUFFIX + r"($|[\s,|(])", p) for n in names):
                    return follow.strip()
    return None


def leaders(nflverse: Path, season: int):
    path = nflverse / f"stats_player_reg_{season}.csv.gz"
    rows = list(csv.DictReader(gzip.open(path, "rt", encoding="utf-8")))
    out = {}
    for stat in LEADER_STATS:
        values = [(float(r[stat] or 0), r["player_id"], r["player_display_name"]) for r in rows]
        top = max(v for v, _i, _n in values)
        out[stat] = (top, {i: n for v, i, n in values if v == top})
    return out, sha(path.read_bytes())


def build(sources: Path, nflverse: Path) -> dict:
    provenance = json.loads((sources / "provenance.json").read_text(encoding="utf-8"))
    teams = json.loads((DATA / "teams.json").read_text(encoding="utf-8"))["teams"]
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))["teams"]
    used, out, stats_files = {}, [], {}
    pages = {}

    def page(key):
        if key not in pages:
            raw = (sources / f"{key}.wiki").read_bytes()
            pin = provenance[key]
            if sha(raw) != pin["sha256"]:
                raise SystemExit(f"{key}: cached text differs from its pinned revision")
            pages[key] = raw.decode("utf-8")
        return pages[key]

    for key in sorted(teams):
        t = teams[key]
        season, full = t["season"], FULL_NAMES[t["selector"]]
        rows = list(csv.DictReader((DATA / f"{key}.csv").read_text(encoding="utf-8").splitlines()))
        board, stats_sha = leaders(nflverse, season)
        stats_files[f"stats_player_reg_{season}.csv.gz"] = stats_sha
        for row, prov in zip(rows, manifest[key]["players"]):
            names = name_variants(row, prov["source_name"])
            honours = []
            for level, line in all_pro(page(f"allpro_{season}"), full, names):
                honours.append(dict(honour=level, source=f"allpro_{season}", line=line))
                used[f"allpro_{season}"] = True
            line = pro_bowl(page(f"probowl_{season}"), full, names)
            if line:
                honours.append(dict(honour="PB", source=f"probowl_{season}", line=line))
                used[f"probowl_{season}"] = True
            for honour, src in AWARDS.items():
                line = award(page(src), season, names)
                if line:
                    honours.append(dict(honour=honour, source=src, line=line))
                    used[src] = True
            for stat, (top, ids) in board.items():
                if prov["gsis_id"] and prov["gsis_id"] in ids and top > 0:
                    honours.append(dict(honour="LEADER", source=f"nflverse_stats_{season}",
                                        line=f"led the NFL in {LEADER_STATS[stat]}: {top:g} ({stat})"))
            if honours:
                best = max(honours, key=lambda h: RULES[h["honour"]])
                out.append(dict(team=key, index=int(row["index"]), name=f"{row['first']} {row['last']}",
                                position=row["position"], gsis_id=prov["gsis_id"], honours=honours,
                                floor=RULES[best["honour"]], model_level=MODEL_LEVEL[best["honour"]]))
    sources_doc = {k: dict(title=provenance[k]["title"], url=provenance[k]["url"], sha256=provenance[k]["sha256"])
                   for k in sorted(used)}
    for name, digest in sorted(stats_files.items()):
        season = int(re.search(r"\d{4}", name).group())
        sources_doc[f"nflverse_stats_{season}"] = dict(
            title=f"nflverse player stats {season} (regular season)",
            url=f"https://github.com/nflverse/nflverse-data/releases/download/stats_player/{name}", sha256=digest)
    return {"schema": "nfl2k5_classic_teams_honours/v1",
            "about": "Sourced season honours of the classic teams' players and the overall floors they set "
                     "(tools/nfl2k5_classic_teams_honours.py). Floors are on the game's native overall.",
            "rules": RULES, "model_level": MODEL_LEVEL, "sources": sources_doc, "players": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sources", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    doc = build(args.sources, args.inputs)
    text = json.dumps(doc, indent=1, ensure_ascii=True) + "\n"
    if args.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("honours reproduce exactly" if same else "honours differ")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(len(doc["players"]), "honoured players")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
