from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mod_editor.core.nfl2k5_crib import load_nfl2k5_crib_catalog
from mod_editor.core.nfl2k5_crib_scene_texture_writer import (
    TARGETS,
    build_unified_crib_scene_texture_imports,
)
from mod_editor.core.nfl2k5_stadium_texture_writer import encode_rgba_png


PRIVATE_ROOT = Path(
    "/home/noah/.cache/2k5-mod-studio/"
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)


class Nfl2k5CribSceneTextureWriterTests(unittest.TestCase):
    def test_all_188_owned_surfaces_are_logical_and_editable(self) -> None:
        self.assertEqual(len(TARGETS), 188)
        self.assertEqual(len({value[1] for value in TARGETS.values()}), 36)
        catalog = load_nfl2k5_crib_catalog()
        promoted = tuple(catalog.by_selector(selector) for selector in TARGETS)
        self.assertTrue(all(asset.editable for asset in promoted))
        self.assertTrue(all(asset.format_name == "P8" for asset in promoted))
        self.assertEqual(sum(asset.editable for asset in catalog.assets), 498)
        self.assertEqual(
            promoted[-1].provider_edit("mine.png"),
            {
                "kind": "crib_scene_texture",
                "png": "mine.png",
                "selector": promoted[-1].selector,
            },
        )

    def test_private_ticker_surface_rebuild_is_fixed_and_reparsed(self) -> None:
        indexes = PRIVATE_ROOT / "indexes/nfl2k5_resource_chunks_v2.json"
        packs = tuple(PRIVATE_ROOT.glob("extracted/*/vc_53450030/0"))
        if not indexes.is_file() or len(packs) != 1:
            self.skipTest("private indexed NFL 2K5 source is unavailable")
        with tempfile.TemporaryDirectory(prefix="crib-scene-writer-") as raw:
            png = Path(raw) / "ticker.png"
            width = height = 64
            png.write_bytes(encode_rgba_png(
                width, height, bytes((24, 48, 96, 255)) * (width * height)
            ))
            built = build_unified_crib_scene_texture_imports(
                packs[0], indexes,
                (("crib_scene_texture:ticker:0", png),),
            )
        self.assertEqual(len(built), 1)
        replacement, previews, report, selector, target = built[0]
        self.assertEqual(selector, "crib_scene_texture:ticker:0")
        self.assertEqual(len(replacement), target["span_size"])
        self.assertEqual(len(previews), 1)
        self.assertTrue(previews[0][1].startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(report["claims"]["complete_mip_chains_regenerated"])
        self.assertTrue(report["claims"]["opaque_tail_preserved"])

    def test_private_same_scene_edits_compile_to_one_span(self) -> None:
        indexes = PRIVATE_ROOT / "indexes/nfl2k5_resource_chunks_v2.json"
        packs = tuple(PRIVATE_ROOT.glob("extracted/*/vc_53450030/0"))
        if not indexes.is_file() or len(packs) != 1:
            self.skipTest("private indexed NFL 2K5 source is unavailable")
        with tempfile.TemporaryDirectory(prefix="crib-scene-group-") as raw:
            edits = []
            for number, (selector, width, height, color) in enumerate((
                ("crib_scene_texture:phone:0", 64, 64, (20, 60, 100, 255)),
                ("crib_scene_texture:phone:4", 32, 32, (100, 60, 20, 255)),
            )):
                png = Path(raw) / f"phone-{number}.png"
                png.write_bytes(encode_rgba_png(
                    width, height, bytes(color) * (width * height)
                ))
                edits.append((selector, png))
            built = build_unified_crib_scene_texture_imports(
                packs[0], indexes, edits
            )
        self.assertEqual(len(built), 1)
        self.assertEqual(built[0][4]["texture_count"], 2)
        self.assertEqual(built[0][4]["chunk_index"], 105)
        self.assertTrue(
            built[0][2]["claims"]["same_scene_edits_composed_before_compression"]
        )

    def test_private_non_electronics_scene_surface_uses_general_writer(self) -> None:
        indexes = PRIVATE_ROOT / "indexes/nfl2k5_resource_chunks_v2.json"
        packs = tuple(PRIVATE_ROOT.glob("extracted/*/vc_53450030/0"))
        if not indexes.is_file() or len(packs) != 1:
            self.skipTest("private indexed NFL 2K5 source is unavailable")
        selector = "crib_scene_texture:glass_00:0"
        with tempfile.TemporaryDirectory(prefix="crib-scene-general-") as raw:
            png = Path(raw) / "glass.png"
            png.write_bytes(encode_rgba_png(
                32, 32, bytes((28, 88, 148, 220)) * (32 * 32)
            ))
            built = build_unified_crib_scene_texture_imports(
                packs[0], indexes, ((selector, png),)
            )
        self.assertEqual(len(built), 1)
        self.assertEqual(built[0][3], selector)
        self.assertEqual(built[0][4]["chunk_index"], 96)
        self.assertTrue(
            built[0][2]["claims"]["all_catalogued_crib_scene_p8_surfaces"]
        )


if __name__ == "__main__":
    unittest.main()
