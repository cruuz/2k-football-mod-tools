"""Read-only retail shoe export/stage/build comparison; no disc or emulator.

The source archive is opened in place. Exported PNGs and session artifacts live
only in a TemporaryDirectory. Output contains derived measurements only.
"""
from pathlib import Path
import argparse
from io import BytesIO
import json
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.equipment_palette import quality
from mod_editor.core.nfl2k5_equipment_import import stage_equipment_import
from mod_editor.core.nfl2k5_extended_visual_catalog import ExtendedVisualAsset, VisualWriterRoute
from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ExtendedVisualIO
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.session import StudioSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    parser.add_argument("--scale", type=int, choices=(1, 2, 4), default=4)
    args = parser.parse_args()
    targets, _groups = writer.load_targets()
    assets = {
        target.asset_id: ExtendedVisualAsset(
            target.asset_id, target.name, "Equipment", "uniform_equipment_texture",
            target.asset_id, target.width, target.height, VisualWriterRoute.UNIFIED_VISUAL,
            "nfl2k5.uniforms.all_visual", texture=target.name, equipment_descriptor=target)
        for target in targets.values()
    }
    source = next(t for t in targets.values() if t.set_selector == "28H0" and t.name == "shoes01")
    destination = next(t for t in targets.values() if t.set_selector == "28H0" and t.name == "shoes02")
    build = writer.build_unified_uniform_equipment_imports
    compile_cache = writer.EquipmentCompileCache()

    def cached_build(*positional, **keywords):
        keywords["compile_cache"] = compile_cache
        return build(*positional, **keywords)

    with tempfile.TemporaryDirectory(prefix="d1-retail-shoe-") as temporary:
        root = Path(temporary)
        originals = root / "originals"
        originals.mkdir()
        cache = SimpleNamespace(root=root / "cache", originals=originals, pack0=args.index,
                                source=SimpleNamespace(sha256="retail-read-only"))
        io = Nfl2k5ExtendedVisualIO(cache)
        catalog = SimpleNamespace(get_asset=lambda identifier: assets[identifier])
        # Use real equipment IO while avoiding unrelated private catalog
        # requirements. The facade/session exporter and importer remain real.
        with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", return_value=io):
            session = StudioSession(cache, catalog, root=root / "sessions", session_id="test")
        session.attach_visual_catalog(catalog)
        facade = Nfl2k5StudioFacade(uniform_catalog=catalog, xemu_command=())
        facade._session = session
        png = facade.export_asset(assets[source.asset_id], root / "shoes01.png", lambda *args: None)
        with Image.open(png) as exported:
            source_rgba = exported.convert("RGBA").tobytes()
        print(json.dumps({
            "export": "facade.export_asset", "source": source.asset_id,
            "target": destination.asset_id,
            "source_colours": len(set(zip(source_rgba[::4], source_rgba[1::4],
                                          source_rgba[2::4], source_rgba[3::4]))),
            "export_exact": source_rgba == io._decode_uniform_equipment(assets[source.asset_id])[1],
        }), flush=True)
        with patch.object(writer, "build_unified_uniform_equipment_imports", cached_build):
            result = stage_equipment_import(session, assets[destination.asset_id], png,
                                            independent=True, scale=args.scale)
            print("staged", len(result.changed_asset_ids), "consumer packages", flush=True)
            span, previews, receipt, *_rest = cached_build(
                cache.pack0, [(destination.asset_id, session.current_path(assets[destination.asset_id]))])
        with Image.open(BytesIO(previews[0][1])) as final_image:
            upsampled = final_image.convert("RGBA").resize(
                (source.width, source.height), Image.Resampling.NEAREST).tobytes()
        comparison = quality(source_rgba, upsampled)
        print(json.dumps({
            "comparison": "decoded result enlarged with nearest-neighbour to the exported PNG size",
            **{key: comparison[key] for key in
               ("maximum_channel_error", "mean_delta_e76", "maximum_delta_e76")},
        }), flush=True)
        row = receipt["edits"][0]
        palette_quality = dict(row["palette_quality"])
        palette_quality["merged_colour_count"] = len(palette_quality.pop("merged_colours"))
        package = writer.read_entry_bytes(io.archive, io.archive.entries[destination.outer_index])
        chunk = writer.parse_chunks(package, allow_trailing=True)[destination.chunk_index]
        print(json.dumps({
            "palette_quality": palette_quality,
            "projection_quality": row["projection_quality"],
            "encoded_dimensions": row["encoded_dimensions"],
            "palette_entries": row["palette_entries"],
            "wrapper_scratch_preserved": span[20:24] == package[chunk.offset + 20:chunk.offset + 24],
        }, indent=2), flush=True)


if __name__ == "__main__":
    main()
