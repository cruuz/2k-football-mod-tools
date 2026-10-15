"""Grass ownership, exact paint protection and lossless native scene writes."""
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_broadcast_greens as g


def fixture(owners=("color_premipped",)):
    palette = bytes((61, 110, 86, 255, 255, 255, 255, 255, 61, 110, 86, 0, 220, 212, 205, 255)) + bytes(1008)
    data = bytes(256) + palette + b"unrelated paint and geometry"
    rec = dict(name="field", system_bytes=256,
               materials=[dict(name=n, record_offset=i * 128, texture_index=0) for i, n in enumerate(owners)],
               embedded_textures=[dict(index=0, palette_offset=0, format_name="P8")])
    return data, rec


class OwnershipTests(unittest.TestCase):
    def test_white_snow_transparent_and_all_other_decoded_bytes_stay_exact(self):
        before, rec = fixture()
        after, receipt = g.paint_scene(before, rec, "synthetic")
        self.assertNotEqual(before[256:259], after[256:259])
        self.assertEqual(before[:256], after[:256])
        self.assertEqual(before[259:], after[259:])
        self.assertEqual(receipt["non_grass_bytes_changed"], 0)
        self.assertEqual(receipt["palettes"][0]["entries"], [0])

    def test_green_team_paint_on_a_shared_texture_is_refused(self):
        before, rec = fixture(("color_premipped", "center_logo"))
        with self.assertRaisesRegex(ValueError, "shared with paint"):
            g.paint_scene(before, rec, "synthetic")

    def test_a_separate_logo_descriptor_aliasing_the_palette_is_refused(self):
        before, rec = fixture()
        rec["materials"].append(dict(name="center_logo", texture_index=1))
        rec["embedded_textures"].append(dict(index=1, palette_offset=0, format_name="P8"))
        with self.assertRaisesRegex(ValueError, "palette shared with paint"):
            g.paint_scene(before, rec, "synthetic")

    def test_paint_texture_of_same_green_colour_is_unchanged(self):
        before, rec = fixture(("endzone_N_L",))
        after, receipt = g.paint_scene(before, rec, "synthetic")
        self.assertEqual(before, after)
        self.assertEqual(receipt["decoded_ranges"], [])

    def test_material_only_rgb_preserves_alpha_and_all_neighbours(self):
        before = bytearray(128)
        struct.pack_into("<I", before, 0x18, 0xFF566E3D)
        rec = dict(name="field", system_bytes=128, embedded_textures=[],
                   materials=[dict(name="color_premipped", record_offset=0, texture_index=None)])
        after, _ = g.paint_scene(bytes(before), rec, "grass")
        self.assertEqual(after[:0x18], before[:0x18])
        self.assertEqual(after[0x1B:], before[0x1B:])

    def test_measured_turf_transform_hits_the_photo_median(self):
        self.assertEqual(g.rgb_transform((87, 111, 62), "synthetic"), (58, 102, 56))
        # Linear scaling retains the bands; only one-byte rounding intervenes.
        for family in ("synthetic", "grass"):
            a = g.rgb_transform((80, 100, 60), family)
            b = g.rgb_transform((88, 110, 66), family)
            for x, y in zip(a, b):
                self.assertAlmostEqual(y / x, 1.1, delta=.03)

    def test_zero_scratch_final_flag_alignment_changes_without_decoded_changes(self):
        import nfl_vc_lz_fill as fill
        decoded = b"a" * 48
        encoded = fill.serialize(48, 0, 12, [("L", 97)] * 12 + [("M", 12, 12)] * 3)
        unsafe, _ = fill.fill_stream(encoded, decoded, 39, slack=0)
        self.assertEqual(len(fill.parse_tokens(unsafe)[3]) % 8, 0)
        body, receipt = next(g.safe_fills(encoded, decoded, 39, 0))
        self.assertEqual(len(body), 39)
        self.assertNotEqual(len(fill.parse_tokens(body)[3]) % 8, 0)
        self.assertEqual(receipt["scratch"], 0)
        self.assertTrue(receipt["split_matches"])
        self.assertEqual(g.ml._tools()[0].decompress_vc_lz(body, 48)[0], decoded)

    def test_build_pass_follows_anniversary_fields_and_precedes_compaction(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text()
        fields = text.index('receipt["steps"].append({"step": "espn25_fields"')
        greens = text.index('receipt["steps"].append({"step": "broadcast_greens"')
        compact = text.index('compacted = finish_private', fields)
        self.assertLess(fields, greens)
        self.assertLess(greens, compact)

    def test_image_receipt_replay_writes_nothing_and_refuses_later_mutation(self):
        class Archive:
            data = b"completed field"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, offset, size):
                return self.data
        archive = Archive()
        entry = SimpleNamespace(virtual_offset=0, size=len(archive.data))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "build.iso"
            g.save(g.receipt_path(path), dict(schema=g.SCHEMA, revision=g.REVISION,
                   bundles={"s18nd.iff": dict(after=g.sha(archive.data))}))
            with patch.object(g.ms, "_outer_image", return_value=lambda *args, **kwargs: archive), \
                 patch.object(g, "entries", return_value={"s18nd.iff": entry}), \
                 patch.object(g, "families", return_value={"s18": "synthetic"}):
                result = g.apply_to_image(path)
                self.assertEqual(result["bytes_written"], 0)
                archive.data = b"foreign field"
                with self.assertRaisesRegex(ValueError, "changed after greens"):
                    g.apply_to_image(path)


if __name__ == "__main__":
    unittest.main()
