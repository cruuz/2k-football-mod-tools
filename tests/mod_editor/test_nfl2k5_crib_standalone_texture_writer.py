"""Coverage for every standalone Crib P8 storage/layout class."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from mod_editor.core.nfl2k5_crib import (
    CribStorage,
    load_nfl2k5_crib_catalog,
)
from mod_editor.core.nfl2k5_crib_standalone_texture_writer import (
    REFLECTION_GAP_BYTES,
    build_unified_crib_standalone_texture_imports,
)
from nfl_txtr import HEADER, encode_rgba_png

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import nfl2k5_visual_mod_project as unified  # noqa: E402


PRIVATE_ROOT = Path(
    "/home/noah/.cache/2k5-mod-studio/"
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)


class CribStandaloneTextureWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_crib_catalog()

    def test_catalog_matrix_covers_every_standalone_layout(self) -> None:
        aggregate = [
            asset for asset in self.catalog.assets
            if asset.storage is CribStorage.TEAM_ITEM_AGGREGATE
            and not asset.selector.startswith("crib_team_photo:")
        ]
        external = [
            asset for asset in self.catalog.assets
            if asset.storage is CribStorage.EXTERNAL_TEXTURE
        ]
        self.assertEqual(len(aggregate), 114)
        self.assertEqual(len(external), 68)
        self.assertTrue(all(asset.editable for asset in aggregate + external))
        self.assertEqual(Counter(asset.format_name for asset in aggregate), {
            "P8": 114,
        })
        self.assertEqual(Counter(asset.format_name for asset in external), {
            "P8": 67,
            "VC_P8_LINEAR": 1,
        })
        reflection = self.catalog.by_selector(
            "crib_external_texture:8:reflection"
        )
        chain = sum(
            max(1, reflection.width >> level)
            * max(1, reflection.height >> level)
            for level in range(reflection.mip_levels)
        )
        self.assertEqual(reflection.palette_offset - chain, REFLECTION_GAP_BYTES)
        ticker = self.catalog.by_selector(
            "crib_external_texture:77:ticker_src"
        )
        self.assertEqual(ticker.dimensions, (1024, 32))
        self.assertEqual(ticker.mip_levels, 1)
        self.assertEqual(ticker.palette_offset, 1024 * 32)

    def test_private_representatives_rebuild_in_their_exact_spans(self) -> None:
        indexes = PRIVATE_ROOT / "indexes/nfl2k5_resource_chunks_v2.json"
        packs = tuple(PRIVATE_ROOT.glob("extracted/*/vc_53450030/0"))
        if not indexes.is_file() or len(packs) != 1:
            self.skipTest("private indexed NFL 2K5 source is unavailable")
        selectors = (
            "crib_item_texture:00_helmet",
            "crib_external_texture:7:logo",
            "crib_external_texture:8:reflection",
            "crib_external_texture:77:ticker_src",
        )
        with tempfile.TemporaryDirectory(prefix="crib-standalone-") as raw:
            for number, selector in enumerate(selectors):
                asset = self.catalog.by_selector(selector)
                png = Path(raw) / f"{number}.png"
                png.write_bytes(encode_rgba_png(
                    asset.width,
                    asset.height,
                    bytes((24 + number * 20, 64, 112, 255))
                    * (asset.width * asset.height),
                ))
                built = build_unified_crib_standalone_texture_imports(
                    packs[0], selector, png
                )
                self.assertGreaterEqual(len(built), 1)
                self.assertLessEqual(len(built), 2)
                self.assertEqual(
                    sum(len(row[0]) for row in built),
                    HEADER.size + asset.stored_size,
                )
                self.assertTrue(built[0][1][0][1].startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertTrue(
                    built[0][2]["claims"]["physical_extent_derived_from_private_archive"]
                )

    def test_unified_project_kind_stages_and_dispatches_logical_selector(self) -> None:
        with tempfile.TemporaryDirectory(prefix="crib-unified-") as raw:
            root = Path(raw)
            png = root / "item.png"
            png.write_bytes(b"user-authored png input")
            project_path = root / "project.json"
            project_path.write_bytes(unified.canonical_json({
                "edits": [{
                    "kind": unified.CRIB_STANDALONE_TEXTURE_KIND,
                    "selector": "crib_item_texture:00_helmet",
                    "png": str(png),
                }],
                "purpose": "Standalone Crib unified-provider contract test.",
                "schema": unified.SCHEMA,
            }))
            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            work = root / "work"
            work.mkdir()
            owned_root = unified.ownership.track_existing(work, True)
            files = []
            target = {
                "selector": "crib_item_texture:00_helmet",
                "logical_selector": "crib_item_texture:00_helmet",
            }
            expected = [(b"fixed span", [], {"target": target},
                         target["selector"], target)]
            try:
                with mock.patch.object(
                    unified.crib_standalone_adapter,
                    "build_unified_crib_standalone_texture_imports",
                    return_value=expected,
                ) as compiler:
                    built = unified.build_crib_standalone_texture_imports(
                        0,
                        project.value["edits"][0],
                        project,
                        pins,
                        root / "0",
                        owned_root,
                        files,
                    )
                self.assertEqual(built, expected)
                self.assertEqual(compiler.call_count, 1)
                self.assertEqual(
                    compiler.call_args.args[1], "crib_item_texture:00_helmet"
                )
                staged = compiler.call_args.args[2]
                self.assertTrue(staged.is_relative_to(work))
                self.assertEqual(staged.read_bytes(), png.read_bytes())
            finally:
                unified.ownership.cleanup_owned(files, [owned_root])
if __name__ == "__main__":
    unittest.main()
