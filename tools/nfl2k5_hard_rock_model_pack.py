#!/usr/bin/env python3
"""2K5 Edition 4x pack manifest for a disc that carries Hard Rock Stadium (job st2, st4).

Every texture Hard Rock Stadium draws in the stadium scene gets its 4x master from
``tools/nfl2k5_hard_rock_model_art.py --masters``; the field's grass bands take theirs too, and the Dolphins' end zones and
midfield take the 2026 venue art folder's own masters (``<art root>/MIA/venue/master4x/field``; s14 gives each end its own three textures, so each end's panels take their own master, the north set standing in
for a missing south one). The
field's rain and snow looks are tinted from the dry art, so only the dry bundles' field textures get masters (a dry
master in a snow game would undo the snow). The targets are named on the model's own scene layout (outer, chunk, texture
descriptor), recompiled here from the retail source, so x2's ``nfl2k5_texture_pack.py build`` keys them from the catalog
of the disc that will be played. Retail textures the model keeps (sideline props, pylons, yard markers, banners, digits)
and the runtime crowd atlas are left out.

    python3 tools/nfl2k5_hard_rock_model_pack.py SOURCE MASTERS_DIR OUT_DIR [--art-root DIR]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: E402
from mod_editor.core import nfl2k5_hard_rock_model as lv  # noqa: E402
from mod_editor.core import nfl2k5_stadium_environment as env  # noqa: E402


def master_for(material, weather, team_masters, tod="d"):
    """The 4x master (a Path) of one Hard Rock Stadium material in one bundle, or None."""
    if material.startswith("env_"):
        # the environment kit's own masters (its art tool's --masters, into the same folder); its ground tiles
        # are weathered in the rain and snow bundles, so those keep their native drawings
        name = env.master_name(material, lv.VENUE, tod, weather)
        return Path(name) if name else None
    if material in lv.MATERIALS:
        return Path(lv.MATERIALS[material][0] + ".png")
    if weather != "d":
        return None
    if material == lv.GRASS_MATERIAL:
        return Path("field/hr_grass.png")
    if material == lv.OUTSIDE_MATERIAL:
        return Path("field/hr_grass_outside.png")
    if team_masters is not None and material in lv.TEAM_FIELD:
        p = team_masters / f"{material}.png"
        if not p.is_file() and material.startswith("endzone_S_"):
            p = team_masters / f"{material.replace('_S_', '_N_')}.png"
        return p if p.is_file() else None
    return None


def layout(bundle, scene):
    """(chunk index, {material: descriptor offset}) of one scene of a bundle."""
    chunk = ml.bundle_scenes(bundle)[scene]
    rec, _decoded = ml._scene(bundle, chunk)
    descriptors = {int(t["index"]): int(t["descriptor_offset"]) for t in rec["embedded_textures"]}
    return int(chunk.index), {m: descriptors[int(r["index"])] for m, r in ml.texture_rows(rec).items()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="retail disc image or packs folder")
    parser.add_argument("masters", help="tools/nfl2k5_hard_rock_model_art.py --masters output")
    parser.add_argument("out")
    parser.add_argument("--art-root", default=None, help="the 2026 venue art folder the build used")
    args = parser.parse_args(argv)
    masters, out = Path(args.masters), Path(args.out)
    team_masters = Path(args.art_root) / "MIA" / "venue" / "master4x" / "field" if args.art_root else None
    (out / "images").mkdir(parents=True, exist_ok=True)
    retail = lv.read_retail(args.source)
    pins = lv._venue_pins()
    entries, missing = [], []
    for name in lv.VARIANTS:
        weather = name[4]
        model, _info = lv.model_bundle(retail[name], name, lv.build(), cameras=lv.hard_rock_shots(),
                                       dry_bundle=retail[lv.dry_of(name)])
        for scene in ("stadium", "field"):
            chunk_index, materials = layout(model, scene)
            for material, descriptor in sorted(materials.items()):
                rel = master_for(material, weather, team_masters, name[3])
                if rel is None:
                    continue
                source = rel if rel.is_absolute() else masters / rel
                if not source.is_file():
                    missing.append(f"{name} {material}: {rel}")
                    continue
                dest_name = ("mia_" + rel.name) if rel.is_absolute() else rel.as_posix().replace("/", "_")
                dest = out / "images" / dest_name
                if not dest.exists():
                    shutil.copyfile(source, dest)
                entries.append(dict(image=dest.relative_to(out).as_posix(), group="hard_rock_model",
                                    target=dict(outer=int(pins[name]["outer"]), chunk=chunk_index, descriptor=descriptor),
                                    note=f"{name} scene {scene} ({material}) Hard Rock Stadium"))
    doc = dict(name="Hard Rock Stadium 4x (st2)", priority=0,
               description="Hard Rock Stadium's own textures at 4x (the bowl, the shade canopy and its spires, the corner boards, the building and its ramps, the site; the dry field's grass bands and the Dolphins' end zones and midfield). Build it against the catalog of a disc that has Hard Rock Stadium.",
               entries=entries)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"PACK_MANIFEST_OK {len(entries)} targets, {len(missing)} missing -> {out}")
    for line in missing[:20]:
        print("  missing", line)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
