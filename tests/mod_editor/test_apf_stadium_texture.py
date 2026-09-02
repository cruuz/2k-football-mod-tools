from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from mod_editor.apf_studio import stadium_texture as target


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_GAME = ROOT / "extracted" / "All-Pro Football 2K8 (USA)"


@unittest.skipUnless((PRIVATE_GAME / "0A").is_file(), "private APF retail source absent")
class StadiumEmbeddedTextureRetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        (
            _entry,
            _record,
            cls.outer,
            _blocks,
            _stored,
            cls.system,
            cls.vram,
        ) = target._source(PRIVATE_GAME)  # type: ignore[attr-defined]
        cls.catalog = target._catalog_from_parts(  # type: ignore[attr-defined]
            cls.system, cls.vram
        )

    def test_draw_material_embedded_texture_join_is_total(self) -> None:
        catalog = self.catalog
        self.assertEqual(
            (len(catalog.surfaces), len(catalog.materials), len(catalog.textures)),
            (89, 84, 78),
        )
        self.assertEqual(catalog.shader_family_count, 20)
        self.assertTrue(all(texture.material_slots for texture in catalog.textures))
        self.assertEqual(
            {
                slot
                for surface in catalog.surfaces
                for slot in surface.material_slots
            },
            set(range(84)),
        )

    def test_every_reusable_codec_has_bit_exact_full_mip_transport(self) -> None:
        editable = [texture for texture in self.catalog.textures if texture.editable]
        self.assertEqual(len(editable), 78)
        self.assertEqual(
            Counter(texture.format_name for texture in editable),
            Counter(
                {
                    "DXT1": 31,
                    "DXT4_5": 17,
                    "DXN": 14,
                    "8": 7,
                    "5_6_5": 5,
                    "8_8": 2,
                    "8_8_8_8": 1,
                    "DXT5A": 1,
                }
            ),
        )
        self.assertTrue(all(texture.editable for texture in self.catalog.textures))
        for texture in editable:
            payload = target._texture_bytes(self.vram, texture)  # type: ignore[attr-defined]
            if texture.format_name == "DXT1":
                layout = target.bc1_mips.derive_layout(texture.metadata)
                rebuilt = target.bc1_mips.transport_roundtrip(payload, layout)
            elif texture.format_name == "DXT4_5":
                layout = target.bc3_mips.derive_layout(texture.metadata)
                rebuilt = target.bc3_mips.transport_roundtrip(payload, layout)
            elif texture.format_name == "DXN":
                if texture.metadata["tiled"]:
                    layout = target.dxn_mips.derive_layout(texture.metadata)
                    rebuilt = target.dxn_mips.transport_roundtrip(payload, layout)
                else:
                    layout = target._derive_linear_dxn_layout(texture.metadata)  # type: ignore[attr-defined]
                    rebuilt = target._linear_dxn_roundtrip(payload, layout)  # type: ignore[attr-defined]
            else:
                layout = target._derive_generic_layout(  # type: ignore[attr-defined]
                    texture.metadata, texture.format_name
                )
                rebuilt = target._generic_roundtrip(  # type: ignore[attr-defined]
                    payload,
                    layout,
                    target._GENERIC_FORMATS[texture.format_name][4],  # type: ignore[attr-defined]
                )
            self.assertEqual(rebuilt, payload, texture.selector)

    def test_exported_png_is_an_exact_outer_no_op(self) -> None:
        texture = self.catalog.textures[0]
        with tempfile.TemporaryDirectory(prefix="apf-stadium-no-op-") as directory:
            png = Path(directory) / "source.png"
            target.export_png(PRIVATE_GAME, texture.index, png)
            rebuilt, manifest, selected = target.build_patch(
                PRIVATE_GAME, png, texture.index
            )
        self.assertEqual(selected, texture)
        self.assertEqual(manifest["mode"], "no_op")
        self.assertEqual(rebuilt, self.outer)
        self.assertEqual(hashlib.sha256(rebuilt).hexdigest(), target.OUTER_SHA256)
        self.assertEqual(manifest["verification"]["changed_inner_parts"], [])
        self.assertEqual(manifest["verification"]["changed_vram_byte_count"], 0)

    def test_stage_replacement_snapshots_a_native_size_private_png(self) -> None:
        texture = self.catalog.textures[42]
        with tempfile.TemporaryDirectory(prefix="apf-stadium-stage-") as directory:
            source = Path(directory) / "source.png"
            staged = Path(directory) / "staged.png"
            Image.new("RGBA", (17, 13), (12, 34, 56, 255)).save(source)
            result, source_size = target.stage_replacement_png(
                PRIVATE_GAME, texture.index, source, staged
            )
            self.assertEqual(result, staged)
            self.assertEqual(source_size, (17, 13))
            with Image.open(staged) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (texture.width, texture.height))
                self.assertEqual(image.mode, "RGBA")
            with self.assertRaises(target.StadiumTextureError):
                target.stage_replacement_png(
                    PRIVATE_GAME, texture.index, source, staged
                )

    def test_changed_bc1_fits_and_reopens_with_only_selected_vram_part_changed(self) -> None:
        texture = self.catalog.textures[42]
        rgba = bytearray(
            target._decode_texture_base(  # type: ignore[attr-defined]
                texture,
                target._texture_bytes(self.vram, texture),  # type: ignore[attr-defined]
            )
        )
        rgba[:4] = bytes(((rgba[0] + 17) % 256, rgba[1], rgba[2], 255))
        with tempfile.TemporaryDirectory(prefix="apf-stadium-changed-") as directory:
            png = Path(directory) / "changed.png"
            Image.frombytes("RGBA", (texture.width, texture.height), bytes(rgba)).save(png)
            rebuilt, manifest, _selected = target.build_patch(
                PRIVATE_GAME, png, texture.index
            )
        self.assertNotEqual(rebuilt, self.outer)
        self.assertEqual(manifest["mode"], "changed")
        self.assertEqual(
            manifest["verification"]["changed_inner_parts"],
            [{"file_index": 8, "part_index": 1}],
        )
        self.assertGreater(manifest["verification"]["changed_vram_byte_count"], 0)
        self.assertGreater(manifest["iff"]["allocation_slack_after"], 0)
        self.assertLessEqual(
            manifest["iff"]["block1_h7a_preservation"]["payload_growth_bytes"],
            2026,
        )


if __name__ == "__main__":
    unittest.main()
