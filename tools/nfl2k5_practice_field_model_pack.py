#!/usr/bin/env python3
"""2K5 Edition 4x pack manifest for a disc that carries the modern practice facility (job pf).

Every texture of the practice facility's own art in the stadium scene gets its 4x master from
``tools/nfl2k5_practice_field_model_art.py --masters``, treated the way the build treats the native art: the side
fields' greens regraded to job tf's day targets, the night drawings of the lit textures in the night bundles, and the
rain and snow looks applied per bundle (so a master never undoes a wet or snowy texture). The midfield takes a 4x
master of the current NFL shield drawn from the 2026 venue art folder's league marks when that folder is given (league
marks never ship; the pack is built locally). The targets are named on the model's own scene layout (outer, chunk,
texture descriptor), recompiled here from the retail source, so x2's ``nfl2k5_texture_pack.py build`` keys them from
the catalog of the disc that will be played. Retail textures the model keeps or borrows (sideline props, pylons, yard
markers, digits, the cityscape's grass, parking, road, trees and hills), the runtime crowd atlas, job tf's field
surface and the cleared (transparent) field marks are left out.

    python3 tools/nfl2k5_practice_field_model_pack.py SOURCE MASTERS_DIR OUT_DIR [--art-root DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: E402
from mod_editor.core import nfl2k5_practice_field_model as pf  # noqa: E402


def master_art(key, tod, weather, masters):
    """(RGBA master, image name) of one of the model's own art keys in one bundle, as ``pf._textures`` treats the
    native art, or None when the master is missing."""
    import numpy as np
    from PIL import Image
    name = f"{key}_night" if (tod == "n" and key in pf.NIGHT_ART) else key
    path = masters / f"{name}.png"
    if not path.is_file():
        return None
    rgba = np.asarray(Image.open(path).convert("RGBA"))
    if key in pf.GRASS_ART:
        rgba = pf.regrade_green(rgba, pf.texture_mean_for(pf.SURFACE_LOOK, key))
    elif key in pf.TURF_ART:
        rgba = pf.regrade_green(rgba, pf.texture_mean_for(pf.SYNTHETIC_LOOK, key))
    tinted = key in pf.SNOW_COVER and weather != "d"
    rgba = pf._weather(rgba, key, weather)
    return rgba, f"{name}{'_' + weather if tinted else ''}.png"


def layout(bundle, scene):
    """(chunk index, {material: descriptor offset}) of one scene of a bundle."""
    chunk = ml.bundle_scenes(bundle)[scene]
    rec, _decoded = ml._scene(bundle, chunk)
    descriptors = {int(t["index"]): int(t["descriptor_offset"]) for t in rec["embedded_textures"]}
    return int(chunk.index), {m: descriptors[int(r["index"])] for m, r in ml.texture_rows(rec).items()}


def main(argv=None):
    from PIL import Image
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="retail disc image or packs folder")
    parser.add_argument("masters", help="tools/nfl2k5_practice_field_model_art.py --masters output")
    parser.add_argument("out")
    parser.add_argument("--art-root", default=None, help="the 2026 venue art folder the build used (its NFL shield)")
    args = parser.parse_args(argv)
    masters, out = Path(args.masters), Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    shield = pf.league_shield(args.art_root)
    retail = pf.read_retail(args.source)
    pins = pf._venue_pins()
    entries, missing, written = [], [], set()
    for name in pf.VARIANTS:
        tod, weather = name[3], name[4]
        model, _info = pf.model_bundle(retail[name], name, pf.build(venue=name[:3]), cameras=pf.practice_shots())
        chunk_index, materials = layout(model, "stadium")
        for material, descriptor in sorted(materials.items()):
            spec = pf.MATERIALS.get(material)
            if spec is None or spec[0].startswith("city:"):
                continue
            art = master_art(spec[0], tod, weather, masters)
            if art is None:
                missing.append(f"{name} {material}: {spec[0]}")
                continue
            rgba, image = art
            dest = out / "images" / image
            if image not in written:
                Image.fromarray(rgba, "RGBA").save(dest, optimize=True)
                written.add(image)
            entries.append(dict(image=dest.relative_to(out).as_posix(), group="practice_field_model",
                                target=dict(outer=int(pins[name]["outer"]), chunk=chunk_index, descriptor=descriptor),
                                note=f"{name} scene stadium ({material}) practice facility"))
        if shield is not None:
            f_index, f_materials = layout(retail[name], "field")
            chunk = ml.bundle_scenes(retail[name])["field"]
            rec, _dec = ml._scene(retail[name], chunk)
            row = ml.texture_rows(rec)[pf.MIDFIELD]
            image = "pf_midfield_shield.png"
            if image not in written:
                pf.midfield_master(shield, (int(row["width"]), int(row["height"]))).save(out / "images" / image,
                                                                                           optimize=True)
                written.add(image)
            entries.append(dict(image=f"images/{image}", group="practice_field_model",
                                target=dict(outer=int(pins[name]["outer"]), chunk=f_index,
                                            descriptor=f_materials[pf.MIDFIELD]),
                                note=f"{name} scene field ({pf.MIDFIELD}) the current NFL shield"))
    doc = dict(name="Practice facility 4x (pf)", priority=0,
               description="The practice facility's own textures at 4x (the field house, the headquarters' glass, the "
                           "side fields, fences, poles, bleachers, clocks and gear; the midfield shield when the venue art "
                           "folder is given). Build it against the catalog of a disc that has the practice facility.",
               entries=entries)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"PACK_MANIFEST_OK {len(entries)} targets, {len(missing)} missing -> {out}")
    for line in missing[:20]:
        print("  missing", line)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
