#!/usr/bin/env python3
"""b778-sd5: the stadium crowd's sprite strips, kept at their retail bytes.

What the strips are. Every team crowd package (outers 513..852 home, 853..1192 away, one per club, side, day/rain
and dry/snow) holds the 256 x 256 A1R5G5B5 atlas ``crowdbase`` the stadium's ``crowd`` billboards draw, and the
people the CPU copies into it every frame: the A1R5G5B5 strips ``p001``..``p006`` and/or ``p011``..``p016``, 64
texels tall and 880..1344 wide, with their five mip levels. The game reads their texels in its
own frame order, not as one linear 1056 x 64 picture.

What went wrong (PROVED IN EMULATOR and OFFLINE, report b778_sd5_REPORT.md). The SOFTDRINK v0.6 author inputs carry
240 ``p8_texture`` edits of these strips for five clubs (BUF, DAL, LAR, LAC, SF; every package of each). They were
painted on the strips' linear export, so the paint lands texel by texel in the game's frame order: the fans' clothes
come out as a navy, white and grey (BUF red, white and blue) speckle, and the crowd behind the bench at AT&T Stadium
and Highmark Stadium looked pixelated and ragged ("glitchy fans"; the same bytes reach SoFi Stadium and Levi's
Stadium, and these clubs' away fans anywhere). The atlas the game builds from the retail strips is clean.

What this tool does (read only unless ``--out`` is given):

    sd5_crowd_strips.py project PROJECT.json [--out FIXED.json]
        list the project's crowd strip edits; with --out write the same project without them (canonical encoding,
        every other edit kept in its order), so the strips keep their retail bytes
    sd5_crowd_strips.py disc IMAGE --retail RETAIL
        list the crowd packages whose sprite strips differ from retail; exit status 1 when any does

The edit test is by target only (``p8:<outer>:<strip>``), so a project of any vintage is handled the same way.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: the A1R5G5B5 crowd sprite strips (the All Textures lane calls them "player strips")
STRIP_NAMES = frozenset({"p001", "p002", "p003", "p004", "p005", "p006",
                         "p011", "p012", "p013", "p014", "p015", "p016"})
#: the team crowd packages: home 513..852, away 853..1192
CROWD_PACKAGES = range(513, 1193)


def strip_target(edit):
    """(outer, strip) when ``edit`` writes a crowd sprite strip, else None."""
    if not isinstance(edit, dict) or edit.get("kind") != "p8_texture":
        return None
    parts = str(edit.get("asset_id", "")).split(":")
    if len(parts) != 3 or parts[0] != "p8" or not parts[1].isdigit():
        return None
    outer, name = int(parts[1]), parts[2]
    if outer in CROWD_PACKAGES and name in STRIP_NAMES:
        return outer, name
    return None


def strip_edits(document):
    """The crowd strip edits of a project document, in order."""
    return [edit for edit in document.get("edits", []) if strip_target(edit) is not None]


def without_strip_edits(document):
    """A copy of the project document without its crowd strip edits; every other edit kept, in order."""
    return dict(document, edits=[edit for edit in document.get("edits", []) if strip_target(edit) is None])


def changed_strips(image, retail):
    """[(outer, strip)] whose chunk span on ``image`` differs from retail (both read only)."""
    sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
    from mod_editor.core import nfl2k5_modern_fans as fans
    tx, _fill = fans._tools()
    out = []
    with fans._outer_image()(retail) as ra, fans._outer_image()(image) as ia:
        rent, ient = list(ra.entries), list(ia.entries)
        for outer in CROWD_PACKAGES:
            a = ra.read(rent[outer].virtual_offset, rent[outer].size)
            b = ia.read(ient[outer].virtual_offset, ient[outer].size)
            if a == b:
                continue
            for chunk in tx.parse_chunks(a, allow_trailing=True):
                if chunk.kind != "TXTR":
                    continue
                name = tx.parse_texture(tx.decode_chunk(a, chunk)[0], chunk).name
                lo, hi = chunk.offset, chunk.offset + 0x20 + chunk.stored_size
                if name in STRIP_NAMES and a[lo:hi] != b[lo:hi]:
                    out.append((outer, name))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("project")
    p.add_argument("project", type=Path)
    p.add_argument("--out", type=Path)
    d = sub.add_parser("disc")
    d.add_argument("image", type=Path)
    d.add_argument("--retail", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.mode == "project":
        document = json.loads(a.project.read_text(encoding="utf-8"))
        found = strip_edits(document)
        clubs = sorted({strip_target(edit)[0] for edit in found})
        print(f"{len(found)} crowd strip edits in {len(clubs)} crowd packages: {clubs}")
        if a.out:
            sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
            from tools import nfl2k5_visual_mod_project as compiler
            if a.out.exists():
                raise SystemExit(f"refusing to overwrite {a.out}")
            fixed = without_strip_edits(document)
            a.out.write_bytes(compiler.canonical_json(fixed))
            compiler.read_project(a.out)
            print(f"wrote {a.out}: {len(fixed['edits'])} edits (was {len(document['edits'])})")
        return 0
    found = changed_strips(a.image, a.retail)
    for outer, name in found:
        print(f"outer {outer} {name} differs from retail")
    print(f"{len(found)} crowd strips differ from retail")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
