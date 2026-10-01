#!/usr/bin/env python3
"""2K5 Edition 4x pack manifest for a disc that carries SoFi Stadium (u6).

Every texture SoFi Stadium draws (the stadium scene's new textures and the field's end-zone panels and midfield
mark) gets its 4x master from ``tools/nfl2k5_sofi_model_art.py --masters``. The targets are named on the model's
own scene layout (outer, chunk, texture descriptor), recompiled here from the retail source, so x2's
``nfl2k5_texture_pack.py build`` keys them from the catalog of the disc that will be played. Retail textures the
model keeps (sideline props, pylons, yard markers, banners, digits) and the runtime crowd atlas are left out.

    python3 tools/nfl2k5_sofi_model_pack.py SOURCE MASTERS_DIR OUT_DIR
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
from mod_editor.core import nfl2k5_sofi_model as sm  # noqa: E402
from mod_editor.core import nfl2k5_stadium_environment as env  # noqa: E402


#: main (2026-09-24): the Super Bowl LXI mark is the NFL's own raster, sharp only at native size, so every texture
#: that carries it stays out of the pack and the Edition shows the native
SUPER_BOWL_NATIVE_ONLY = {"LIGHT_sf_ribbon", "LIGHT_sf_screen", "center_logo"}


def master_for(material, venue, tod, weather):
    """The 4x master file (relative to MASTERS_DIR) of one SoFi material in one bundle, or None."""
    if material.startswith("env_"):
        # the environment kit's own masters (its art tool's --masters, into the same folder), dry bundles only
        return env.master_name(material, venue, tod, weather)
    if venue == "s40" and material in SUPER_BOWL_NATIVE_ONLY:
        return None
    if venue == "s40" and material == "logo":
        return "field/s40_shield.png"
    if material == "LIGHT_sf_screen" and sm.portrait_panel(venue) is not None:
        # the private portrait panel's master (the private folder, never the repo): absolute, so the join ignores MASTERS
        return str(sm.PRIVATE_ART / "master4x" / f"LIGHT_sf_screen_{venue}.png")
    sky = "o" if weather in "rs" and tod != "n" else tod
    night = "n" if tod == "n" else "d"
    table = {
        "sf_seat": "sf_seat.png", "sf_concrete": "sf_concrete.png", "LIGHT_sf_ribbon": f"LIGHT_sf_ribbon_{venue}.png",
        "LIGHT_sf_glass": "LIGHT_sf_glass.png", "LIGHT_sf_facade": "LIGHT_sf_facade.png", "sf_portal": "sf_portal.png",
        "LIGHT_sf_concourse": "LIGHT_sf_concourse.png",
        "sf_etfe_under": f"sf_etfe_under_{night}.png", "sf_etfe_top": f"sf_etfe_top_{night}.png",
        "sf_alu": "sf_alu.png", "sf_white": "sf_white.png", "LIGHT_sf_lights": "LIGHT_sf_lights.png",
        "LIGHT_sf_screen": f"LIGHT_sf_screen_{venue}.png", "sf_dark": "sf_dark.png", "sf_letters": "sf_letters.png",
        "sf_letters_screen": "sf_letters_screen.png", "sf_plaza": "sf_plaza.png", "sf_ground": "sf_ground.png",
        "sf_water": "sf_water.png", "sf_sky": f"sf_sky_{sky}.png",
        "endzone_N_L": f"field/{venue}_endzone_L.png", "endzone_N_M": f"field/{venue}_endzone_M.png",
        "endzone_N_R": f"field/{venue}_endzone_R.png", "center_logo": f"field/{venue}_midfield.png",
    }
    return table.get(material)


def layout(bundle, scene):
    """(chunk index, {material: descriptor offset}) of one scene of a bundle."""
    chunk = ml.bundle_scenes(bundle)[scene]
    rec, _decoded = ml._scene(bundle, chunk)
    descriptors = {int(t["index"]): int(t["descriptor_offset"]) for t in rec["embedded_textures"]}
    return int(chunk.index), {m: descriptors[int(r["index"])] for m, r in ml.texture_rows(rec).items()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="retail disc image or packs folder")
    parser.add_argument("masters", help="tools/nfl2k5_sofi_model_art.py --masters output")
    parser.add_argument("out")
    args = parser.parse_args(argv)
    masters, out = Path(args.masters), Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    retail = sm.read_retail(args.source)
    pins = sm._venue_pins()
    entries, missing = [], []
    for name in sm.VARIANTS:
        venue, tod, weather = name[:3], name[3], name[4]
        model, _info = sm.model_bundle(retail[name], name, sm.build(venue=venue), cameras=sm.sofi_shots(venue),
                                       dry_bundle=retail[sm.dry_of(name)])
        for scene in ("stadium", "field"):
            chunk_index, materials = layout(model, scene)
            for material, descriptor in sorted(materials.items()):
                file_name = master_for(material, venue, tod, weather)
                if file_name is None:
                    continue
                source = masters / file_name
                if not source.is_file():
                    missing.append(f"{name} {material}: {file_name}")
                    continue
                dest = out / "images" / (Path(file_name).name if Path(file_name).is_absolute()
                                         else file_name.replace("/", "_"))
                if not dest.exists():
                    shutil.copyfile(source, dest)
                entries.append(dict(image=dest.relative_to(out).as_posix(), group="sofi_model",
                                    target=dict(outer=int(pins[name]["outer"]), chunk=chunk_index, descriptor=descriptor),
                                    note=f"{name} scene {scene} ({material}) SoFi Stadium"))
    doc = dict(name="SoFi Stadium 4x (u6)", priority=0,
               description="SoFi Stadium's own textures at 4x (the bowl, canopy, Infinity Screen panels, signs, "
                           "plaza and both teams' end zones and midfield). Build it against the catalog of a disc "
                           "that has SoFi Stadium.",
               entries=entries)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"PACK_MANIFEST_OK {len(entries)} targets, {len(missing)} missing -> {out}")
    for line in missing[:20]:
        print("  missing", line)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
