#!/usr/bin/env python3
"""2K5 Edition 4x pack manifest for a disc that carries AT&T Stadium (job st2).

Every texture AT&T Stadium draws in the stadium scene gets its 4x master from
``tools/nfl2k5_att_model_art.py --masters``; the field's turf bands take theirs too, and the Cowboys' end zones
and midfield take the 2026 venue art folder's own masters (``<art root>/DAL/venue/master4x/field``); with a south set
there, each end-zone panel's master is the south and north masters stacked the way the field lays the texture. The field's rain
and snow looks are tinted from the dry art, so only the dry bundles' field textures get masters (a dry master in a snow
game would undo the snow). The targets are named on the model's own scene layout (outer, chunk, texture descriptor),
recompiled here from the retail source, so x2's ``nfl2k5_texture_pack.py build`` keys them from the catalog of the disc
that will be played. Retail textures the model keeps (sideline props, pylons, yard markers, banners, digits) and the
runtime crowd atlas are left out.

    python3 tools/nfl2k5_att_model_pack.py SOURCE MASTERS_DIR OUT_DIR [--art-root DIR]
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
from mod_editor.core import nfl2k5_att_model as hm  # noqa: E402
from mod_editor.core import nfl2k5_stadium_environment as env  # noqa: E402


def split_master(material, team_masters, out_dir):
    """The 4x master of an end-zone panel texture when the art root has a south set: the south end's master in the top
    half (the retail endzone_N_* panels lie at -z), the north end's in the bottom half, as ``hm.split_endzones`` lays
    the texture. None when there is no south set."""
    from PIL import Image
    part = material[-1]
    north, south = team_masters / f"endzone_N_{part}.png", team_masters / f"endzone_S_{part}.png"
    if not any((team_masters / f"{k}.png").is_file() for k in hm.SOUTH_ENDZONE):
        return None
    south = south if south.is_file() else north
    if not north.is_file():
        north = south
    if not north.is_file():
        return None
    n_im, s_im = Image.open(north).convert("RGBA"), Image.open(south).convert("RGBA")
    width, height = n_im.size
    half = height // 2
    image = Image.new("RGBA", (width, 2 * half))
    image.paste(s_im.resize((width, half), Image.LANCZOS), (0, 0))
    image.paste(n_im.resize((width, half), Image.LANCZOS), (0, half))
    dest = out_dir / f"cowboys_split_{material}.png"
    image.save(dest)
    return dest


def master_for(material, weather, team_masters, out_dir=None, tod="d"):
    """The 4x master (a Path) of one AT&T Stadium material in one bundle, or None."""
    if material.startswith("env_"):
        # the environment kit's own masters (its art tool's --masters, into the same folder), dry bundles only
        name = env.master_name(material, hm.VENUE, tod, weather)
        return Path(name) if name else None
    if material in hm.MATERIALS:
        return Path(hm.MATERIALS[material][0] + ".png")
    if weather != "d":
        return None
    if material == hm.GRASS_MATERIAL:
        return Path("field/att_grass.png")
    if material == hm.OUTSIDE_MATERIAL:
        return Path("field/att_grass_outside.png")
    if team_masters is not None and material in hm.ENDZONE_TEXTURES and out_dir is not None:
        split = split_master(material, team_masters, out_dir)
        if split is not None:
            return split
    if team_masters is not None and material in hm.TEAM_FIELD and material not in hm.SOUTH_ENDZONE:
        p = team_masters / f"{material}.png"
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
    parser.add_argument("masters", help="tools/nfl2k5_att_model_art.py --masters output")
    parser.add_argument("out")
    parser.add_argument("--art-root", default=None, help="the 2026 venue art folder the build used")
    args = parser.parse_args(argv)
    masters, out = Path(args.masters), Path(args.out)
    team_masters = Path(args.art_root) / "DAL" / "venue" / "master4x" / "field" if args.art_root else None
    (out / "images").mkdir(parents=True, exist_ok=True)
    retail = hm.read_retail(args.source)
    pins = hm._venue_pins()
    entries, missing = [], []
    for name in hm.VARIANTS:
        weather = name[4]
        model, _info = hm.model_bundle(retail[name], name, hm.build(), cameras=hm.att_shots(),
                                       dry_bundle=retail[hm.dry_of(name)])
        for scene in ("stadium", "field"):
            chunk_index, materials = layout(model, scene)
            for material, descriptor in sorted(materials.items()):
                rel = master_for(material, weather, team_masters, out / "images", name[3])
                if rel is None:
                    continue
                source = rel if rel.is_absolute() else masters / rel
                if not source.is_file():
                    missing.append(f"{name} {material}: {rel}")
                    continue
                if rel.parent == out / "images":
                    dest = rel                                   # a split end-zone master written just now
                else:
                    dest_name = ("cowboys_" + rel.name) if rel.is_absolute() else rel.as_posix().replace("/", "_")
                    dest = out / "images" / dest_name
                    if not dest.exists():
                        shutil.copyfile(source, dest)
                entries.append(dict(image=dest.relative_to(out).as_posix(), group="att_model",
                                    target=dict(outer=int(pins[name]["outer"]), chunk=chunk_index, descriptor=descriptor),
                                    note=f"{name} scene {scene} ({material}) AT&T Stadium"))
    doc = dict(name="AT&T Stadium 4x (st2)", priority=0,
               description="AT&T Stadium's own textures at 4x (the bowl, the roof and arches, the board, the facade and site; "
                           "the dry field's turf bands and the Cowboys' end zones and midfield). Build it against "
                           "the catalog of a disc that has AT&T Stadium.",
               entries=entries)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"PACK_MANIFEST_OK {len(entries)} targets, {len(missing)} missing -> {out}")
    for line in missing[:20]:
        print("  missing", line)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
