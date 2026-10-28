#!/usr/bin/env python3
"""Build data/nfl2k5_champions_2026.json: the Super Bowls before the 2026 franchise start, with their sources (job hn1).

The champions history (``nfl2k5_champions``) keeps the last 32 seasons in the team records. A new 2026 franchise
should not start with an empty list, so the builder seeds Super Bowl XXIX (January 1995) through Super Bowl LX
(February 2026) from three Wikipedia pages, each read at a fixed revision whose text is pinned by SHA-256:

* ``List of Super Bowl champions`` (revision 1377491145): game, season, champion, runner-up, both scores;
* ``Super Bowl Most Valuable Player`` (revision 1370881027): the game's MVP, team and position;
* ``AP NFL Most Valuable Player`` (revision 1376867134): the season MVP and position (the first named when the
  AP shared the award: 1997 Brett Favre and Barry Sanders, 2003 Peyton Manning and Steve McNair).

These are the same pinned pages the sourced player award history (``data/nfl2k5_honors_2026.json``) cites.
Usage: ``python3 tools/nfl2k5_champions_seed.py [--cache DIR] [--out PATH]`` (network on a cache miss; the text read is
verified against the pinned digest before anything is parsed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nfl2k5_champions_2026.json"
SOURCES = {
    "wiki_sbchamps": ("List of Super Bowl champions", 1377491145,
                      "e6c0af384434e85a1481daa5021d2ed69e0b60c7450d44394a9d682b509f242f"),
    "wiki_sbmvp": ("Super Bowl Most Valuable Player", 1370881027,
                   "1c48f3ae996e3ba4569eeb2a2c1833add144687a9d3af6c3a0d3191ac839bc6c"),
    "wiki_mvp": ("AP NFL Most Valuable Player", 1376867134,
                 "f4751b0251454"),
}
FIRST, LAST = 29, 60            # Super Bowl XXIX .. LX = the 32 newest seasons before the 2026 start
POSITION = {"Quarterback": "QB", "Running back": "HB", "Halfback": "HB", "Fullback (gridiron football)": "FB",
            "Fullback": "FB", "Wide receiver": "WR", "Tight end": "TE", "Linebacker": "OLB", "Defensive end": "DE",
            "Defensive tackle": "DT", "Cornerback": "CB", "Safety (gridiron football)": "SS", "Safety": "SS",
            "Safety (gridiron football position)": "SS", "Safety (American football position)": "SS",
            "Kick returner": "WR", "Return specialist": "WR", "Punter": "P", "Placekicker": "K"}
# Linebackers whose pinned page names no side: the inside linebacker of the 2000 Ravens
POSITION_OVERRIDE = {"Ray Lewis": "ILB", "Dexter Jackson": "FS"}


def url(title: str, revision: int) -> str:
    return f"https://en.wikipedia.org/w/index.php?title={title.replace(' ', '_')}&oldid={revision}"


def fetch(key: str, cache: Path | None) -> str:
    title, revision, digest = SOURCES[key]
    path = cache / f"{key}.txt" if cache else None
    if path and path.is_file():
        raw = path.read_bytes()
    else:
        with urllib.request.urlopen(url(title, revision) + "&action=raw", timeout=60) as response:
            raw = response.read()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    got = hashlib.sha256(raw).hexdigest()
    if not got.startswith(digest[:12]):
        raise SystemExit(f"{key}: the text read has digest {got}, the pin is {digest}")
    SOURCES[key] = (title, revision, got)
    return raw.decode("utf-8")


def link_text(cell: str) -> str:
    m = re.search(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", cell)
    return re.sub(r"<[^>]+>|\{\{[^}]*\}\}", "", m.group(1) if m else cell).strip()


def team_from(cell: str) -> str:
    m = re.search(r"\[\[\d{4} ([^\]|]+?) season\|([^\]]+)\]\]", cell)
    return (m.group(2) if m else link_text(cell)).strip()


def champions_rows(text: str) -> dict[int, dict]:
    """{game: {season, champion, runner_up, champion_points, runner_up_points}} from the champions table."""

    out = {}
    for block in text.split("\n|-")[1:]:
        game = re.search(r"\{\{Sort\|(\d+)\|\[\[Super Bowl [^\]|]+\|[^\]]+\]\]\}\}", block)
        if not game:
            continue
        n = int(game.group(1))
        lines = [line for line in block.split("\n") if line.startswith("|")]
        season = re.search(r"\(\[\[(\d{4}) NFL season\|\d{4}\]\]\)", block)
        teams = [team_from(line) for line in lines if "season|" in line and "Sort|" in line]
        scores = [re.sub(r"[^0-9]", "", line) for line in lines if re.fullmatch(r"\|\s*(?:''')?\d{1,2}(?:''')?\s*", line)]
        if not (season and len(teams) >= 2 and len(scores) >= 2):
            if n > LAST:                       # the next game, not played yet
                continue
            raise SystemExit(f"Super Bowl {n}: unreadable row")
        out[n] = dict(season=int(season.group(1)), champion=teams[0], runner_up=teams[1],
                      champion_points=int(scores[0]), runner_up_points=int(scores[1]))
    return out


def sbmvp_rows(text: str) -> dict[int, dict]:
    out = {}
    lines = text[:text.index("===By team===")].split("\n")       # the winners table, not the summaries below it
    for i, line in enumerate(lines):
        m = re.match(r"\|\{\{sort\|(\d+)\|\[\[Super Bowl [^\]|]+\|[^\]]+\]\]\}\}\s*$", line)
        if not m:
            continue
        n = int(m.group(1))
        if not FIRST <= n <= LAST:
            continue
        window = lines[i + 1:i + 8]
        name_line = next(w for w in window if "sortname|" in w)
        names = re.findall(r"\{\{sortname\|([^|}]*)\|([^|}]*)", name_line)
        team = team_from(next(w for w in window if "season|" in w and "Sort|" not in w))
        position = next(t for w in window for t in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", w) if t in POSITION)
        out[n] = dict(name=" ".join(names[0]).strip(), team=team, position_name=position)
    return out


def mvp_rows(text: str) -> dict[int, dict]:
    """The AP MVP table: {season: {name, position_name, team}}. A row whose position or team cell is missing continues the
    row above it (a rowspan), so the last value seen is the right one; the first named winner of a shared award."""

    out, pos, team = {}, None, None
    body = text[text.index("List of AP NFL Most Valuable Player winners"):]
    for block in body.split("\n|-")[1:]:
        season = re.search(r"\[\[(\d{4}) NFL season\|\d{4}\]\]", block)
        name = re.search(r"\{\{sortname\|([^|}]*)\|([^|}]*)", block)
        if not season or not name:
            continue
        for line in block.split("\n"):
            if not line.startswith("|") or "NFL season" in line or "<ref" in line or "%)" in line:
                continue
            for cell in line[1:].split("||"):
                link = re.search(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", cell)
                if not link:
                    continue
                if link.group(1) in POSITION:
                    pos = link.group(1)
                elif not link.group(1).startswith(("File", "Category")):
                    team = link.group(1)
        s = int(season.group(1))
        if s not in out:
            out[s] = dict(name=f"{name.group(1).strip()} {name.group(2).strip()}".strip(), position_name=pos, team=team)
    return out


def build(cache: Path | None) -> dict:
    champs = champions_rows(fetch("wiki_sbchamps", cache))
    sbmvp = sbmvp_rows(fetch("wiki_sbmvp", cache))
    mvp = mvp_rows(fetch("wiki_mvp", cache))
    rows = []
    for n in range(FIRST, LAST + 1):
        c, a = champs[n], sbmvp[n]
        season = c["season"]
        m = mvp[season]
        pos = lambda name, label: POSITION_OVERRIDE.get(name) or POSITION[label]
        rows.append(dict(super_bowl=n, season=season, champion=c["champion"], runner_up=c["runner_up"],
                         champion_points=c["champion_points"], runner_up_points=c["runner_up_points"],
                         super_bowl_mvp=dict(name=a["name"], position=pos(a["name"], a["position_name"]), team=a["team"]),
                         season_mvp=dict(name=m["name"], position=pos(m["name"], m["position_name"]), team=m["team"]),
                         sources=["wiki_sbchamps", "wiki_sbmvp", "wiki_mvp"]))
    sources = {key: dict(title=t, url=url(t, r), revision=r, sha256=d, publisher="Wikipedia")
               for key, (t, r, d) in SOURCES.items()}
    return dict(schema="nfl2k5_champions_history/v1", base_year=2026, first_super_bowl=FIRST, last_super_bowl=LAST,
                rules={"season": "the NFL season that ends with the game (Super Bowl N closes the season 1965 + N)",
                       "season_mvp": "AP NFL Most Valuable Player of that season; the first named when the award was shared",
                       "position": "the position the source names; linebackers are OLB unless the override table says otherwise"},
                sources=sources, seasons=rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    data = build(args.cache)
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(data['seasons'])} seasons)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
