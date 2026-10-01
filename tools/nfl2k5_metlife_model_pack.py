"""2K5 Edition 4x pack manifest for a disc that carries the Modern MetLife model (u5).

The Modern MetLife 4x pack (tools/nfl2k5_modern_metlife_masters.py) names its targets on the skin's scene layout:
(outer, chunk, texture descriptor offset). The model writes a new stadium scene, so a stadium-chunk target of that
manifest points at another texture (or none) in the model's scene. x2's `nfl2k5_texture_pack.py build` keys each
target from the catalog of the disc that will be played, so on a model disc those rows would key the wrong
textures. This tool rebuilds the model scene of every bundle from the retail source and writes a manifest in which:

* the field-chunk rows stay as they are (the model does not touch the field scene);
* every stadium-chunk row moves to the model's descriptor of the same material, and the rows for textures the
  model does not use are dropped (listed in the receipt);
* the model's own type-drawn textures get their 4x masters (METLIFE STADIUM letters, the MetLife sign, and per
  venue the board panel, the signage atlas with the Ring of Honor plates, and the field-wall atlas) from
  `tools/nfl2k5_metlife_model_art.py --masters`.

The reused textures keep the skin's pixels exactly (PROVED OFFLINE), so their x2 keys, and the images, are the same.

    python3 tools/nfl2k5_metlife_model_pack.py SOURCE SKIN_PACK_DIR MASTERS_DIR OUT_DIR
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
from mod_editor.core import nfl2k5_metlife_model as mm  # noqa: E402
from mod_editor.core import nfl2k5_stadium_environment as env  # noqa: E402

#: model material -> 4x master file (``--masters`` output); the board panel, the signage atlas (Ring of Honor
#: plates and signs) and the field-wall atlas are per venue (b76-u5b)
MASTER_FILES = {"ml_letters": "ml_letters_4x.png", "ml_logo": "ml_logo_4x.png"}
VENUE_MASTERS = ("LIGHT_ml_board_panel", "ml_signs", "ml_wall")


def venue_master_files(venue):
    return dict(MASTER_FILES, **{m: f"{m.replace('LIGHT_', '')}_{venue}_4x.png" for m in VENUE_MASTERS})


def stadium_layout(bundle):
    """(stadium chunk index, {material: descriptor offset}) of a bundle's stadium scene."""
    chunk = ml.bundle_scenes(bundle)["stadium"]
    rec, _decoded = ml._scene(bundle, chunk)
    descriptors = {int(t["index"]): int(t["descriptor_offset"]) for t in rec["embedded_textures"]}
    return int(chunk.index), {m: descriptors[int(r["index"])] for m, r in ml.texture_rows(rec).items()}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="retail packs folder or disc image")
    parser.add_argument("skin_pack", help="the Modern MetLife 4x pack folder (manifest.json + images/)")
    parser.add_argument("masters", help="tools/nfl2k5_metlife_model_art.py --masters output")
    parser.add_argument("out")
    args = parser.parse_args(argv)
    skin_pack, out = Path(args.skin_pack), Path(args.out)
    manifest = json.loads((skin_pack / "manifest.json").read_text(encoding="utf-8"))
    retail = mm._read_retail(args.source)
    with ml._outer_image()(str(args.source)) as archive:
        outers = {name: int(e.index) for name, e in ml.metlife_entries(archive).items()}
    layouts = {}
    for name in ml.VARIANTS:
        skin = mm.skin_bundle(retail[name], name, retail[ml.dry_name(name)])
        model, _info = mm.model_bundle(skin, name)
        (sc, skin_map), (mc, model_map) = stadium_layout(skin), stadium_layout(model)
        ml.require(sc == mc, f"{name}: the stadium chunk moved")
        layouts[outers[name]] = (name, sc, {d: m for m, d in skin_map.items()}, model_map)
    (out / "images").mkdir(parents=True, exist_ok=True)
    entries, dropped, moved = [], [], 0
    for entry in manifest["entries"]:
        target = entry["target"]
        name, stadium_chunk, skin_names, model_map = layouts[int(target["outer"])]
        if int(target["chunk"]) == stadium_chunk:
            material = skin_names.get(int(target["descriptor"]))
            if material is None or material not in model_map:
                dropped.append(f"{name} {material or target['descriptor']}")
                continue
            entry = dict(entry, target=dict(target, descriptor=model_map[material]),
                         note=entry.get("note", "") + " -> MetLife model")
            moved += 1
        source = skin_pack / entry["image"]
        dest = out / entry["image"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(source, dest)
        entries.append(entry)
    masters = Path(args.masters)
    for outer, (name, stadium_chunk, _skin_names, model_map) in sorted(layouts.items()):
        venue = name[:3]
        files = venue_master_files(venue)
        for material, file_name in files.items():
            if material not in model_map:
                continue
            dest = out / "images" / f"model_{file_name}"
            if not dest.exists():
                shutil.copyfile(masters / file_name, dest)
            entries.append(dict(image=dest.relative_to(out).as_posix(), group="metlife_model",
                                target=dict(outer=outer, chunk=stadium_chunk, descriptor=model_map[material]),
                                note=f"{name} scene stadium ({material}) MetLife model"))
        # the environment kit's own masters (its art tool's --masters, into the same folder), dry bundles only
        for material in sorted(m for m in model_map if m.startswith("env_")):
            file_name = env.master_name(material, venue, name[3], name[4])
            if file_name is None:
                continue
            dest = out / "images" / f"env_{file_name}"
            if not dest.exists():
                shutil.copyfile(masters / file_name, dest)
            entries.append(dict(image=dest.relative_to(out).as_posix(), group="metlife_model",
                                target=dict(outer=outer, chunk=stadium_chunk, descriptor=model_map[material]),
                                note=f"{name} scene stadium ({material}) environment kit"))
    doc = dict(name="MetLife Stadium 4x, model layout (u5)", priority=0,
               description="The Modern MetLife 4x art retargeted to the Modern MetLife model's stadium scene, plus "
                           "the model's lettering, sign, board panels, signs and Ring of Honor, and field walls at 4x. "
                           "Build it against the catalog of a disc that has the MetLife model.",
               entries=entries)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    (out / "retarget.json").write_text(json.dumps(dict(moved=moved, dropped=dropped), indent=1) + "\n",
                                       encoding="utf-8")
    print(f"PACK_MANIFEST_OK {len(entries)} targets ({moved} moved, {len(dropped)} dropped) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
