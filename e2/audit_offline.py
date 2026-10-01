"""PROVED OFFLINE: reproduce E2's bounded native book and resource census.

Reads the user's retail disc. No disc writes, graphics, audio, or emulator launch.
The imported test harness substitutes archive I/O and presentation boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_espn25_rosters as rosters
from mod_editor.core import nfl2k5_espn25_scenarios as sc
from mod_editor.core import nfl2k5_historic_teams_quick_game as h1
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_espn25_more_moments_native import MomentsCPU
from nfl2k5_historic_quick_game_native import TeamSelectCPU, disc_evidence


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def native_book(cpu, home):
    """Run the actual default-book formatter, including the real sprintf."""
    cpu.run(0x628D0, args=(int(home),))
    return cpu.text(0xB307D0 if home else 0xB30810)


def side_view(cpu, team, home):
    label = cpu.r(team + 0x110)
    return dict(name=cpu.text(cpu.r(team + 0x104)),
                asset_code=cpu.text(cpu.r(team + 0x10C)),
                category=cpu.r(team + 0x128),
                identity=struct.unpack("<H", cpu.read(team + 0x118, 2))[0],
                label_abbreviation=cpu.text(cpu.r(label + 4)),
                filename=native_book(cpu, home))


def run(source, xbe):
    raw = xbe.read_bytes()
    resources, context, ids = disc_evidence(source)
    data = mm.Data.load()
    with rr._outer_image()(source) as archive:
        by_id = {entry.name_id: entry for entry in archive.entries}
        templates = {key: archive.read_entry(by_id[mm.name_id(t["template"])].index)
                     for key, t in data.teams.items()}
        books = {}
        for abbr in ("ARZ ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC MIA MIN NE NO NYG NYJ "
                     "OAK PHI PIT SD SEA SF STL TB TEN WAS").split():
            name = abbr + "-pb.iff"
            entry = by_id[mm.name_id(name)]
            payload = archive.read_entry(entry.index)
            books[name] = dict(outer=entry.index, name_id=entry.name_id, bytes=len(payload), sha256=digest(payload))
    collection = mm.compile_situ(resources[22], data, resources[5])
    files = mm.compile_files(resources[5], templates, data)
    # Release repair is required for repeated native imports, just as on production builds.
    base, _ = rosters.apply_xbe(raw)
    payload, _ = mm.apply(base, data)
    cpu = MomentsCPU(payload, resources, context, ids,
                     situ_chunk=collection[:32 + sc.u32(collection, 4)], extra_files=files)
    moments = []
    for i in range(50):
        cpu.events.clear()
        cpu.select(i)
        cpu.run(0x617E0)
        cpu.run(0x615A0)
        row = dict(row=i + 1, loaded_files=[e["filename"] for e in cpu.events], sides={})
        for side, home, getter, kit in (("away", False, 0x61C60, 0xB30730),
                                        ("home", True, 0x61C50, 0xB30710)):
            row["sides"][side] = side_view(cpu, cpu.run(getter), home)
            row["sides"][side]["kit"] = cpu.text(kit)
        moments.append(row)
        cpu.run(0x20C3C0)
    # H1's real Team Select next handler imports all 75 historic teams, then uses the same formatter.
    payload, _ = h1.apply(base)
    cpu = TeamSelectCPU(payload, resources, context, ids)
    cpu.team_select(cpu.last_resident(), cpu.team(1))
    historic = []
    for i in range(75):
        cpu.events.clear()
        selected = cpu.press("home", 1)
        team = cpu.r(0xACF63C)
        cpu.run(0x617E0)
        row = side_view(cpu, cpu.run(0x61C50), True)
        row.update(index=i, source=context["descriptors"][i]["filename"],
                   selected=selected["home"], loaded_files=selected["loaded"])
        assert row["category"] == 4 and row["filename"] in books
        assert row["source"] in row["loaded_files"]
        historic.append(row)
    return dict(label="PROVED OFFLINE", source=str(source), xbe=str(xbe), xbe_sha256=digest(raw),
                main_sha256=digest(resources[5]), situ_sha256=digest(resources[22]),
                boundaries="Existing MomentsCPU and TeamSelectCPU archive/presentation stubs. Native import, "
                           "label assignment, match copy, kit formatting and 0x628D0 book formatting execute. "
                           "No book decode, play execution, rendered art, or full candidate B game is claimed.",
                books=books, historic_teams=historic, moments=moments,
                counts=dict(historic_teams=len(historic), moments=len(moments),
                            moment_sides=sum(len(m["sides"]) for m in moments), extra_team_files=len(files)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
    p.add_argument("--xbe", type=Path, default=Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe"))
    p.add_argument("--out", type=Path, default=ROOT / "e2/evidence/native_books.json")
    args = p.parse_args()
    result = run(args.source, args.xbe)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["counts"]))
