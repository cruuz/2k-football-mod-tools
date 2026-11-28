#!/usr/bin/env python3
"""The classic Seamen kits' relief: data/nfl2k5_relief_2026_classic.json (job b81-seamen).

The owner (2026-11-25, playing the 11/20 private disc): "also seamen have a dolphins bump texture in their jersey, have them use
a cleaner one". The Seamen kit packages (14h14.iff, 14a14.iff) are composed from the 2026 Dolphins kits before the 2026
relief runs, so their jersey, sleeve and pants bump maps (chunks 45, 46, 47) are byte for byte the Dolphins' pre-relief
maps (the b81u document's 14H0/14A0 ``before`` pins: 8267881b..., a73304fb..., f118e3d8...), with the Dolphins'
construction and marks raised in them. This document gives them the 2026 relief with no marks at all: plain fabric with
this season's seams.

* jersey and sleeve: the b81u base (the retail 18H0 maps, the 2004 folds softened and the 2004 construction lifted out,
  derived on the user's disc) plus the b81u difference master (hairline seams, the flat collar band, the vents, the pin
  holes; the sleeve's hem hairline) and no patch (a b81u patch raises the kit's own painted shield and maker's marks;
  the Seamen paint none);
* pants: the kit's own pants map with every construction box the Dolphins' rows lift out lifted out, and nothing raised.

The package layout of a composed classic kit follows its own art, so these rows pin no package offset (``offset`` null):
the step finds each chunk by index and pins its span (``before_sha256``, ``length``), the composed map and the written
span. The jersey rows pin the Seamen torso's collar opening.

  python3 tools/b81_uniforms/relief_classic.py --disc BUILT.iso --retail RETAIL.iso [--write]

``--disc`` is a built disc that holds 14h14.iff and 14a14.iff as the step reads them (any v0.10 build: the relief steps
never write them); it and the retail disc are read only. Without ``--write`` it only says whether the document matches.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

OUT = ROOT / "data/nfl2k5_relief_2026_classic.json"
SELECTORS = {"14H14": "14H0", "14A14": "14A0"}      # each Seamen side and the Dolphins kit whose maps it carries
JOB = ("b81-seamen (the owner 2026-11-25: \"seamen have a dolphins bump texture in their jersey, have them use a cleaner "
       "one\"): the classic Seamen kits' jersey, sleeve and pants relief, level B with this season's seams and no marks; "
       "authored by tools/b81_uniforms/relief_classic.py on the b81u bases and masters")


def build(disc, retail):
    import numpy as np
    from nfl_txtr import parse_chunks
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    from mod_editor.core import nfl2k5_relief_2026 as relief
    b81u = relief.relief_b81u()
    doc = {"schema": relief.SCHEMA, "job": JOB, "level": b81u["level"], "art": b81u["art"],
           "gauss_kernels": b81u["gauss_kernels"], "bases": b81u["bases"], "masters": b81u["masters"],
           "patches": {}, "slots": []}
    problems = []
    maps = relief.retail_maps(doc, retail, problems)
    relief.require(maps is not None, "retail maps: " + "; ".join(problems))
    gauss = relief.Kernels(doc["gauss_kernels"])
    folder = relief.art_folder(doc)
    masters = {name: relief.read_art(folder, entry) for name, entry in doc["masters"].items()}
    donor_rows = {(r["selector"], r["slot"]): r for r in b81u["slots"]}
    with bump._Image.open(Path(disc), writable=False) as image:
        index = bump._parsed_index(image)
        packages = {}
        for selector in SELECTORS:
            found = [e for e in index.entries if bump.logical_name_for(e.name_id) == selector + ".IFF"]
            relief.require(len(found) == 1, f"{selector}.IFF absent or duplicated on {disc}")
            packages[selector] = image.read_segments(index.sub_extents(found[0], 0, found[0].size))
    for selector, donor in SELECTORS.items():
        raw = packages[selector]
        chunks = {c.index: c for c in parse_chunks(raw, allow_trailing=True)}
        for slot, chunk_index in (("bump_jersey", 45), ("bump_sleeve", 46), ("bump_pants", 47)):
            c = chunks[chunk_index]
            span = raw[c.offset:c.end_offset]
            # the span the Seamen kit carries is the Dolphins kit's own pre-relief map (chunk 47 crosses sides)
            befores = {r["before_sha256"] for (s, sl), r in donor_rows.items() if sl == slot and s in SELECTORS.values()}
            relief.require(relief.sha(span) in befores, f"{selector} {slot}: not a Dolphins pre-relief map")
            row = {"selector": selector, "slot": slot, "chunk": chunk_index, "resource_size": None, "offset": None,
                   "length": len(span), "base": "before" if slot == "bump_pants" else "retail", "patch": None}
            if slot == "bump_jersey":
                opening = relief.collar_opening(relief.torso_rgba(raw))
                row["opening_sha256"] = relief.opening_sha256(opening)
                base = relief.jersey_base(gauss, maps["bump_jersey"], opening, relief.jersey_islands_for(doc, maps, folder))
            elif slot == "bump_sleeve":
                base = relief.sleeve_base(gauss, maps["bump_sleeve"])
            else:
                worked = sorted({tuple(b) for s in SELECTORS.values() for b in donor_rows[(s, slot)]["worked"]})
                row["worked"] = [list(b) for b in worked]
                base = relief.pants_base(gauss, relief._texture(span), worked)
            difference = masters.get(slot, np.zeros(base.shape, np.uint8))
            composed = relief.add_difference(base, difference)
            row["composed_sha256"] = relief.sha(composed.tobytes())
            row["before_sha256"] = relief.sha(span)
            ((_key, after, _detail),) = relief._job((row["composed_sha256"], (composed.tobytes(), composed.shape),
                                                     [((selector, slot), span)]))
            row["after_sha256"] = relief.sha(after)
            doc["slots"].append({k: row[k] for k in ("selector", "slot", "chunk", "resource_size", "offset", "length",
                                                    "base", "patch", "composed_sha256", "before_sha256", "after_sha256",
                                                    *(("opening_sha256",) if slot == "bump_jersey" else ()),
                                                    *(("worked",) if slot == "bump_pants" else ()))})
    return doc


def dumps(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--disc", type=Path, required=True)
    parser.add_argument("--retail", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    text = dumps(build(args.disc, args.retail))
    same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
    if args.write and not same:
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", OUT)
    else:
        print("the document " + ("matches" if same else "differs"))
    return 0 if same or args.write else 1


if __name__ == "__main__":
    raise SystemExit(main())
