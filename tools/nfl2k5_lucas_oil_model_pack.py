#!/usr/bin/env python3
"""2K5 Edition 4x pack manifest for a disc that carries Lucas Oil Stadium (job st3).

Every texture Lucas Oil Stadium draws in the stadium scene gets its 4x master from
``tools/nfl2k5_lucas_oil_model_art.py --masters``; the Colts' end zones and the midfield horseshoe take the 2026 venue art
folder's own masters (``<art root>/IND/venue/master4x/field``; s11 gives each end its own three textures, the north set
standing in for a missing south one). The turf and the apron are painted by Modern playing surfaces' own painter at
build time, so they have no master here. The roof is drawn closed, so every bundle's field textures take the same
masters. The targets are named on the model's own scene layout (outer, chunk, texture descriptor), recompiled here from
the retail source, so x2's ``nfl2k5_texture_pack.py build`` keys them from the catalog of the disc that will be played.
Retail textures the model keeps (sideline props, pylons, yard markers, banners, digits) and the runtime crowd atlas are
left out.

    python3 tools/nfl2k5_lucas_oil_model_pack.py SOURCE MASTERS_DIR OUT_DIR [--art-root DIR]
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
from mod_editor.core import nfl2k5_stadium_environment as env  # noqa: E402
from mod_editor.core import nfl2k5_lucas_oil_model as um  # noqa: E402


def master_for(material, team_masters, tod="d", weather="d"):
    """The 4x master (a Path) of one Lucas Oil Stadium material in a bundle of time of day ``tod``, or None (the sky
    has a drawing per time of day, and the towers, the clerestory and the glass wall their own night drawings)."""
    if material.startswith("env_"):
        # the environment kit's own masters (its art tool's --masters, into the same folder), dry bundles only
        name = env.master_name(material, um.VENUE, tod, weather)
        return Path(name) if name else None
    if material in um.MATERIALS:
        key = um.MATERIALS[material][0]
        if key == "los_sky":
            key = f"los_sky_{tod}"
        elif key in um.NIGHT_TEXTURES and tod == "n":
            key = f"{key}_n"
        return Path(key + ".png")
    if team_masters is not None and material in um.TEAM_FIELD:
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
    parser.add_argument("masters", help="tools/nfl2k5_lucas_oil_model_art.py --masters output")
    parser.add_argument("out")
    parser.add_argument("--art-root", default=None, help="the 2026 venue art folder the build used")
    args = parser.parse_args(argv)
    masters, out = Path(args.masters), Path(args.out)
    team_masters = Path(args.art_root) / "IND" / "venue" / "master4x" / "field" if args.art_root else None
    team = um.team_field_art(args.art_root) if args.art_root else None
    (out / "images").mkdir(parents=True, exist_ok=True)
    retail = um.read_retail(args.source)
    pins = um._venue_pins()
    entries, missing = [], []
    for name in um.VARIANTS:
        model, _info = um.model_bundle(retail[name], name, um.build(), cameras=um.lucas_oil_shots(),
                                       dry_bundle=retail[um.dry_of(name)])
        field, _finfo = um.field_span(retail[name], name, team=team)
        chunk = ml.bundle_scenes(retail[name])["field"]
        model = model[:chunk.offset] + field + model[chunk.offset + len(field):]
        for scene in ("stadium", "field"):
            chunk_index, materials = layout(model, scene)
            for material, descriptor in sorted(materials.items()):
                rel = master_for(material, team_masters if scene == "field" else None, name[3], name[4])
                if rel is None:
                    continue
                source = rel if rel.is_absolute() else masters / rel
                if not source.is_file():
                    missing.append(f"{name} {material}: {rel}")
                    continue
                dest_name = ("colts_" + rel.name) if rel.is_absolute() else rel.as_posix().replace("/", "_")
                dest = out / "images" / dest_name
                if not dest.exists():
                    shutil.copyfile(source, dest)
                entries.append(dict(image=dest.relative_to(out).as_posix(), group="lucas_oil_model",
                                    target=dict(outer=int(pins[name]["outer"]), chunk=chunk_index, descriptor=descriptor),
                                    note=f"{name} scene {scene} ({material}) Lucas Oil Stadium"))
    doc = dict(name="Lucas Oil Stadium 4x (st3)", priority=0,
               description="Lucas Oil Stadium's own textures at 4x (the bowl, the roof and its trusses, the north window, "
                           "the boards and banners, the brick fieldhouse and site; the Colts' end zones and midfield "
                           "horseshoe). Build it against the catalog of a disc that has Lucas Oil Stadium.",
               entries=entries)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"PACK_MANIFEST_OK {len(entries)} targets, {len(missing)} missing -> {out}")
    for line in missing[:20]:
        print("  missing", line)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
