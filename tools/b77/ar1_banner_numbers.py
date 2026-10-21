#!/usr/bin/env python3
"""Check every player number on the 2026 stadium banners against the roster, and rebuild the banners that are wrong.

The cloth banners and signs in each home stadium (banner_home_team, banner_home_player, banner_away_team) are drawn from
the text in ``data/nfl2k5_teams_2026/<TEAM>.json`` (``venue.banners``) by ``tools/nfl2k5_team_2026_art.py venue``. A
cloth such as ``#14 CARNELL TATE`` names a player and a number, so the number has to be the one on the roster the disc
carries.

  python3 tools/b77/ar1_banner_numbers.py check --disc DISC.iso
  python3 tools/b77/ar1_banner_numbers.py rebuild --disc DISC.iso --retail RETAIL.iso --art-tree TREE   (or --sheets TEN:banner_away_team)

``check`` reads the disc's roster (read only), reads every banner text that holds ``#<number>`` and prints each cloth whose
number is not worn by a rostered player of that name. Exit status 1 when any cloth is wrong.

``rebuild`` redraws, from the repository's team specs and the user's own retail banner texture (read from RETAIL.iso;
nothing retail is written to the repository), the text-only banner sheets that ``check`` flags (or ``--sheets`` names), compares it
with the PNGs in the venue art tree, and rewrites the native PNG, the 4x master and their hashes in the tree's
``<TEAM>/venue/manifest.json`` where they differ. A sheet that draws a team mark needs the marks pack and is skipped
(and listed). Redrawing an unchanged spec reproduces the tree's bytes exactly, so only a cloth whose text changed moves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / "data" / "nfl2k5_teams_2026"
#: What a cloth says for a player when it is not his surname (all nicknames the banners use).
NICKNAMES = {
    "MHJ": "Harrison", "BUDDA": "Budda", "BIJAN": "Bijan", "LAMAR": "Lamar", "KING": "Henry", "ZAY": "Zay",
    "ROQUAN": "Roquan", "JA'MARR": "Ja'Marr", "DAK": "Dak", "CEEDEE": "CeeDee", "SAUCE": "Sauce", "BTJ": "Brian Thomas",
    "PUKA": "Puka", "KYREN": "Kyren", "KOOL-AID": "Kool-Aid", "JALEN": "Jalen Hurts", "SAQUON": "Saquon",
    "DEVONTA": "DeVonta", "JSN": "Smith-Njigba", "SPOON": "Witherspoon", "CMC": "McCaffrey",
    "BIG JEFF": "Jeffery Simmons", "CARNELL": "Carnell Tate", "WILL": "Will Anderson", "NICO": "Nico Collins",
}


def banner_texts(spec):
    """[(sheet material, slot index, text)] of every banner text of one team spec that holds ``#<number>``."""
    rows = []
    for material, sheet in spec.get("venue", {}).get("banners", {}).items():
        for slot, banner in enumerate(sheet.get("banners", ())):
            for item in banner.get("items", ()):
                text = item.get("text")
                if isinstance(text, str) and re.search(r"#\s*\d+", text):
                    rows.append((material, slot, text))
    return rows


def _norm(text):
    return re.sub(r"[^a-z ]", "", text.lower().replace("-", " "))


def words_of(text):
    words = [w for line in text.split("\n") for w in re.sub(r"#\d+", "", line).split()]
    return words + [part for w in words if "-" in w for part in w.split("-")]  # HINES-ALLEN also names Hines and Allen


def check_text(text, players):
    """[(number, [candidate names])] for every number on one cloth that no matching rostered player wears.

    ``players`` is [(display name, jersey number)]. A cloth matches a player when one of its words is a whole word of the
    player's name (or its nickname maps to part of the name)."""
    wrong = []
    words = words_of(text)
    for number in (int(n) for n in re.findall(r"#(\d+)", text)):
        candidates = []
        for name, jersey in players:
            tokens = _norm(name).split()
            for word in words:
                key = _norm(word)
                nick = _norm(NICKNAMES.get(word.upper(), "zzzz"))
                if (key and key in tokens) or nick in _norm(name):
                    candidates.append((name, jersey))
                    break
        if not any(jersey == number for _, jersey in candidates):
            wrong.append((number, sorted(set(candidates))[:8]))
    return wrong


def roster_players(disc):
    sys.path.insert(0, str(ROOT))
    from mod_editor.core import nfl2k5_roster_records as rr
    document = rr.load_image(disc)
    return [(p.display, int(p.record.values["jersey"])) for p in document.players if p.group in ("team", "pool")]


def check(disc, specs=SPECS):
    players = roster_players(disc)
    problems = []
    for path in sorted(Path(specs).glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        for material, slot, text in banner_texts(spec):
            for number, candidates in check_text(text, players):
                problems.append(dict(team=spec.get("team", path.stem), sheet=material, slot=slot, text=text,
                                     number=number, rostered=candidates))
    return problems


def retail_reference(retail, prefix, material, folder):
    """The retail dry-day banner texture the venue tool uses as the cloth template, written to ``folder``."""
    sys.path.insert(0, str(ROOT))
    from PIL import Image
    from mod_editor.core import nfl2k5_modern_venues_2026 as mv
    with mv._outer_image()(retail) as archive:
        entry = {e.name_id: e for e in archive.entries}[mv.name_id(f"{prefix}dd.iff")]
        data = archive.read(entry.virtual_offset, entry.size)
    rec, decoded = mv.decode_scenes(data)["stadium"]
    for index, row in mv.p8_rows(rec).items():
        if material in (row.get("mapped_material_names") or ()):
            path = Path(folder) / f"{prefix}dd_stadium_t{index:03d}_{material}.png"
            Image.fromarray(mv.read_texture(decoded, rec, row)).save(path)
            return path
    raise ValueError(f"{prefix}dd has no {material} texture")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild(retail, tree, only, work=None):
    """``only``: {(team, sheet material)} to redraw (the sheets ``check`` flags). Other sheets may come from other art
    (Kansas City's is Modern Arrowhead's), so they are never touched."""
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(ROOT))
    import tempfile
    import nfl2k5_team_2026_art as art
    work = Path(work or tempfile.mkdtemp(prefix="ar1_banners_"))
    work.mkdir(parents=True, exist_ok=True)
    report = []
    for spec_path in sorted(SPECS.glob("*.json")):
        spec = art.Spec(spec_path)
        team = spec.data["team"]
        if not any(t == team for t, _ in only):
            continue
        manifest_path = Path(tree) / team / "venue" / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prefix = spec.data["venue"]["prefix"]
        for material, _slot, _text in banner_texts(spec.data):
            if (team, material) not in only:
                continue
            if any(r["material"] == material for r in report if r["team"] == team):
                continue
            sheet = spec.data["venue"]["banners"][material]
            if any("mark" in item for b in sheet["banners"] for item in b["items"]) or sheet.get("alpha") == "items":
                report.append(dict(team=team, material=material, state="skipped: draws a mark (needs the marks pack)"))
                continue
            item = next((i for i in manifest["items"] if i["scene"] == "stadium" and i["material"] == material), None)
            if item is None:
                report.append(dict(team=team, material=material, state="skipped: not in the art tree manifest"))
                continue
            ref = retail_reference(retail, prefix, material, work)
            master = art.author_banner_sheet(spec, sheet, ref, Path("/nonexistent-marks"))
            native = art.downscale(master)
            out_native = Path(tree) / team / "venue" / item["file"]
            out_master = Path(tree) / team / "venue" / item["master"]
            fresh = {}
            for key, array, path in (("sha256", native, work / f"{team}_{material}_native.png"),
                                     ("master_sha256", master, work / f"{team}_{material}_master.png")):
                fresh[key] = art.save(array, path)
            if fresh["sha256"] == item["sha256"] and fresh["master_sha256"] == item["master_sha256"]:
                report.append(dict(team=team, material=material, state="unchanged"))
                continue
            out_native.write_bytes((work / f"{team}_{material}_native.png").read_bytes())
            out_master.write_bytes((work / f"{team}_{material}_master.png").read_bytes())
            before = dict(sha256=item["sha256"], master_sha256=item["master_sha256"])
            item.update(fresh)
            report.append(dict(team=team, material=material, state="rewritten", before=before, after=fresh))
        manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    c.add_argument("--disc", type=Path, required=True)
    r = sub.add_parser("rebuild")
    r.add_argument("--disc", type=Path, help="redraw the sheets that `check` flags on this disc's roster")
    r.add_argument("--sheets", default="", help="or name them: TEN:banner_away_team,HOU:banner_home_player")
    r.add_argument("--retail", type=Path, required=True)
    r.add_argument("--art-tree", type=Path, required=True)
    r.add_argument("--work", type=Path)
    args = parser.parse_args(argv)
    if args.command == "check":
        problems = check(args.disc)
        print(json.dumps(problems, indent=1))
        print(f"{len(problems)} banner number(s) differ from the roster")
        return 1 if problems else 0
    only = {tuple(x.strip().split(":", 1)) for x in args.sheets.split(",") if x.strip()}
    if args.disc:
        only |= {(p["team"], p["sheet"]) for p in check(args.disc)}
    if not only:
        print("nothing to redraw: every banner number matches the roster")
        return 0
    print(json.dumps(rebuild(args.retail, args.art_tree, only, args.work), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
