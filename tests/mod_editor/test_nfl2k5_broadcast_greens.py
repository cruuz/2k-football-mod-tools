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

    def test_turf_transform_is_the_ten_thirteen_turf_with_more_forest_green(self):
        # gr4 (Noah 2026-10-18): the 10/13 MetLife targets (88, 108, 64) land on (74, 102, 60): hue 100, S 0.41 (the 10/13
        # turf was 89 and 0.44), not gr1's (58, 102, 56) (hue 117, "artificial")
        import colorsys
        self.assertEqual(g.rgb_transform((88, 108, 64), "synthetic"), (74, 102, 60))
        r, gr, b = (v / 255 for v in g.rgb_transform((88, 108, 64), "synthetic"))
        h, s, v = colorsys.rgb_to_hsv(r, gr, b)
        self.assertTrue(96 <= h * 360 <= 104, h * 360)
        r0, g0, b0 = (c / 255 for c in (88, 108, 64))
        h0, s0, v0 = colorsys.rgb_to_hsv(r0, g0, b0)
        self.assertTrue(8 <= h * 360 - h0 * 360 <= 14)                          # toward forest green
        self.assertLessEqual(s, s0 + 0.005)                                     # and not more saturated
        self.assertLess(v, v0)                                                  # a little deeper
        # Linear scaling retains the bands; only one-byte rounding intervenes.
        for family in ("synthetic", "grass"):
            a = g.rgb_transform((80, 100, 60), family)
            b = g.rgb_transform((88, 110, 66), family)
            for x, y in zip(a, b):
                self.assertAlmostEqual(y / x, 1.1, delta=.03)

    def test_grass_gain_is_frozen_so_the_xlii_field_does_not_move(self):
        # the XLII moment field (retail s25 grass x this gain) is the shade Noah approved on 10/18
        self.assertEqual(g.GRASS_GAIN, (102 / 111,) * 3)
        self.assertEqual(g.rgb_transform((109, 136, 75), "grass"), (100, 125, 69))

    def test_end_zone_turf_follows_the_field_and_paint_is_left_alone(self):
        before = bytearray(1024)
        turf = (61 * 109 // 100, 125, 69)                          # a turf entry (B, G, R order below)
        entries = {0: (69, 125, 100), 1: (60, 110, 80), 2: (200, 90, 40), 3: (255, 255, 255), 4: (30, 60, 30)}
        for i, (b, gr, r) in entries.items():
            before[i * 4:i * 4 + 4] = bytes((b, gr, r, 255))
        envelope = g.ms.turf_envelope([(100, 125, 69), (96, 122, 66), (104, 130, 72)])
        after, selected = g.end_zone_palette(bytes(before), envelope, "grass")
        self.assertEqual(selected[:1], [0])
        for i in (2, 3):                                           # gold and white paint never change
            self.assertEqual(after[i * 4:i * 4 + 4], bytes(before[i * 4:i * 4 + 4]))
        b, gr, r, a = after[0:4]
        want = tuple(int(round(c * k * m)) for c, k, m in zip((100, 125, 69), g.GRASS_GAIN, g.END_ZONE_MATCH))
        self.assertEqual((r, gr, b), want)
        self.assertEqual(a, 255)
        # the factor the end zone takes beside the family gain is the measured in-game one (Lambeau, 10/18)
        self.assertEqual(tuple(round(1 / m, 2) for m in g.END_ZONE_MATCH), (1.11, 1.07, 1.15))
        turf_after, turf_sel = g.end_zone_palette(bytes(before), envelope, "synthetic")
        self.assertNotEqual(turf_after[:4], after[:4])             # turf takes its own gain

    def test_a_field_scene_darkens_its_end_zone_turf_with_the_field(self):
        decoded = bytearray(2048)
        field_pal, end_pal, logo_pal = 0, 1024, 1024
        for i, (r, gr, b) in enumerate(((100, 125, 69), (96, 122, 66))):
            decoded[field_pal + i * 4:field_pal + i * 4 + 4] = bytes((b, gr, r, 255))
        ez = bytearray(1024)
        ez[0:4] = bytes((69, 125, 100, 255))
        ez[4:8] = bytes((20, 150, 255, 255))                      # a gold stripe
        decoded[end_pal:end_pal + 1024] = ez
        rec = dict(name="field", system_bytes=0,
                   materials=[dict(name="color_premipped", record_offset=0, texture_index=0),
                              dict(name="endzone_N_L", record_offset=128, texture_index=1)],
                   embedded_textures=[dict(index=0, palette_offset=field_pal, format_name="P8"),
                                      dict(index=1, palette_offset=end_pal, format_name="P8")])
        rows = {"color_premipped": rec["embedded_textures"][0], "endzone_N_L": rec["embedded_textures"][1]}
        samples = [(100, 125, 69), (96, 122, 66)] * 8
        with patch.object(g.ml, "texture_rows", return_value=rows), patch.object(g, "_field_samples", return_value=samples):
            after, receipt = g.paint_scene(bytes(decoded), rec, "grass")
        self.assertEqual(receipt["non_grass_bytes_changed"], 0)
        self.assertEqual(len(receipt["end_zone_palettes"]), 1)
        self.assertEqual(receipt["end_zone_palettes"][0]["entries"], [0])
        self.assertEqual(after[end_pal + 4:end_pal + 8], bytes((20, 150, 255, 255)))   # the paint stays exact
        # the field's palette entry 0 and the end zone's entry 0 land on the same relative colour in game: the field gets
        # the family gain, the end zone the family gain times END_ZONE_MATCH (the end zone has no detail layer)
        fb, fg, fr = after[field_pal:field_pal + 3]
        eb, eg, er = after[end_pal:end_pal + 3]
        for e, f, m in zip((er, eg, eb), (fr, fg, fb), g.END_ZONE_MATCH):
            self.assertAlmostEqual(e / f, m, delta=0.02)
        # a field with no colour reference changes no end zone
        with patch.object(g.ml, "texture_rows", return_value=rows), patch.object(g, "_field_samples", return_value=None):
            again, receipt = g.paint_scene(bytes(decoded), rec, "grass")
        self.assertEqual(receipt["end_zone_palettes"], [])

    def test_an_end_zone_palette_shared_with_paint_is_left_alone(self):
        decoded = bytearray(2048)
        decoded[0:4] = bytes((69, 125, 100, 255))
        decoded[1024:1028] = bytes((69, 125, 100, 255))
        rec = dict(name="field", system_bytes=0,
                   materials=[dict(name="color_premipped", record_offset=0, texture_index=0),
                              dict(name="endzone_N_L", record_offset=128, texture_index=1),
                              dict(name="center_logo", record_offset=256, texture_index=2)],
                   embedded_textures=[dict(index=0, palette_offset=0, format_name="P8"),
                                      dict(index=1, palette_offset=1024, format_name="P8"),
                                      dict(index=2, palette_offset=1024, format_name="P8")])
        rows = {"color_premipped": rec["embedded_textures"][0], "endzone_N_L": rec["embedded_textures"][1]}
        with patch.object(g.ml, "texture_rows", return_value=rows), patch.object(g, "_field_samples", return_value=[(100, 125, 69)]):
            after, receipt = g.paint_scene(bytes(decoded), rec, "grass")
        self.assertEqual(after[1024:1028], bytes(decoded[1024:1028]))
        self.assertEqual(receipt["end_zone_palettes"], [])

    def test_anniversary_aliases_take_the_grass_gain_unless_they_keep_a_venue_field(self):
        from mod_editor.core import nfl2k5_espn25_fields as fields
        words = {"s10": 1, "s15": 0, "s21": 0, "s25": 1}
        body = bytearray(len(words) * 64)
        records = []
        for n, (prefix, word) in enumerate(words.items()):
            struct.pack_into("<I", body, n * 64 + 0x1C, word)
            records.append((n * 64, dict(asset_code=("name", prefix))))
        data = bytes(32) + bytes(body)
        archive = SimpleNamespace(entries=[SimpleNamespace(virtual_offset=0, size=len(data))] * 6,
                                  read=lambda offset, size: data)
        catalog = [dict(row=1, source_prefix="s10"), dict(row=24, source_prefix="s25"), dict(row=25, source_prefix="s21"),
                   dict(row=26, source_prefix="s15"), dict(row=36, source_prefix="s15")]
        venues = {"s10": dict(surface="grass"), "s15": dict(surface="synthetic"), "s21": dict(surface="grass"),
                  "s25": dict(surface="grass")}
        with patch.object(g.ml, "_stadium_records", return_value=records), patch.object(g.ms, "venues", return_value=venues), \
             patch.object(fields, "catalog", return_value=catalog):
            result = g.families(archive)
        self.assertEqual(result["s15"], "synthetic")               # the home surface of a turf venue is unchanged
        self.assertEqual(result["a00"], "grass")
        self.assertEqual(result["a25"], "grass")                   # a turf venue's alias draws the retail GRASS map
        self.assertEqual(result["a35"], "grass")
        # rows 24 and 25 keep their venue's own retail field and follow its retail surface word (s25 grass, s21 turf)
        self.assertEqual(result["a23"], "grass")
        self.assertEqual(result["a24"], "synthetic")

    def test_b778_the_fieldturf_and_helix_home_fields_take_their_own_families(self):
        # Davy (10/21, Gillette): "a little too light green"; Noah: darken Gillette and the venues with the same surface.
        # Noah (10/22, Nissan at night): the Helix turf is "too vibrant ... too green". The real venue table decides:
        # the ten synthetic_fieldturf venues and the six synthetic_helix venues change, natural grass keeps its family.
        from mod_editor.core import nfl2k5_espn25_fields as fields
        archive = SimpleNamespace(entries=[SimpleNamespace(virtual_offset=0, size=32)] * 6,
                                  read=lambda offset, size: bytes(32))
        with patch.object(g.ml, "_stadium_records", return_value=[]), patch.object(fields, "catalog", return_value=[]):
            result = g.families(archive)
        table = g.ms.venues()
        self.assertEqual({p for p, v in result.items() if v == "fieldturf"},
                         {"s01", "s04", "s06", "s09", "s15", "s16", "s17", "s18", "s19", "s26"})   # ATL CAR CIN DET MIN NE NO NYG NYJ SEA
        self.assertEqual({table[p]["team"] for p, v in result.items() if v == "fieldturf"},
                         {"ATL", "CAR", "CIN", "DET", "MIN", "NE", "NO", "NYG", "NYJ", "SEA"})
        helix = {p for p, v in table.items() if v["look"] == "synthetic_helix"}
        self.assertEqual({table[p]["team"] for p in helix}, {"DAL", "IND", "LAR", "LAC", "TEN", "HOU"})
        self.assertEqual({p for p, v in result.items() if v == "helix"}, helix)
        self.assertNotIn("synthetic", set(result.values()))   # no home venue is left on the plain synthetic family
        self.assertTrue(all(result[p] == "grass" for p, v in table.items() if v["surface"] == "grass"))

    def test_b778_grass_and_plain_synthetic_gains_are_the_released_gr4_gains(self):
        # every bundle outside the sixteen turf home venues takes exactly the arithmetic the v0.6.1 disc was built with
        self.assertEqual(g.GAINS["synthetic"], (74 / 88, 102 / 108, 102 / 108))
        self.assertEqual(g.GAINS["grass"], (102 / 111,) * 3)
        self.assertEqual(g.SYNTHETIC_GAIN, (74 / 88, 102 / 108, 102 / 108))
        self.assertEqual(g.rgb_transform((88, 108, 64), "synthetic"), (74, 102, 60))
        before, rec = fixture()
        plain, _ = g.paint_scene(before, rec, "synthetic")
        self.assertEqual(plain[256:259], bytes((round(61 * 102 / 108), round(110 * 102 / 108), round(86 * 74 / 88))))
        self.assertEqual(set(g.SATURATION), {"helix"})
        for rgb in ((100, 125, 69), (88, 108, 64), (7, 250, 3)):          # end zones: c * k * m, as gr4 wrote it
            for family in ("grass", "synthetic"):
                want = tuple(int(min(255, max(0, round(c * k * m)))) for c, k, m in zip(rgb, g.GAINS[family], g.END_ZONE_MATCH))
                self.assertEqual(g._shade(rgb, family, g.END_ZONE_MATCH), want)
                self.assertEqual(g.rgb_transform(rgb, family), tuple(int(round(c * k)) for c, k in zip(rgb, g.GAINS[family])))

    def test_b778_fieldturf_is_a_little_deeper_with_the_same_hue(self):
        import colorsys
        self.assertEqual(g.FIELDTURF_GAIN, tuple(k * g.FIELDTURF_SHADE for k in g.SYNTHETIC_GAIN))
        self.assertTrue(0.90 <= g.FIELDTURF_SHADE <= 0.94)
        def luma(rgb):
            r, gr, b = rgb
            return 0.299 * r + 0.587 * gr + 0.114 * b
        for target in ((88, 108, 64), (86, 106, 68), (74, 94, 62), (100, 122, 72)):     # the FieldTurf look by light
            old, new = g.rgb_transform(target, "synthetic"), g.rgb_transform(target, "fieldturf")
            self.assertTrue(0.90 <= luma(new) / luma(old) <= 0.95, (old, new))
            h0, s0, _ = colorsys.rgb_to_hsv(*(v / 255 for v in old))
            h1, s1, _ = colorsys.rgb_to_hsv(*(v / 255 for v in new))
            self.assertLess(abs(h1 - h0) * 360, 3.0, (old, new))     # not minty, not olive (one-byte rounding only)
            self.assertLess(abs(s1 - s0), 0.02, (old, new))
        # the same entries change, paint and every other decoded byte stay exact
        before, rec = fixture()
        helix, helix_receipt = g.paint_scene(before, rec, "synthetic")
        turf, turf_receipt = g.paint_scene(before, rec, "fieldturf")
        self.assertEqual(turf_receipt["decoded_ranges"], helix_receipt["decoded_ranges"])
        self.assertEqual(turf[:256], before[:256])
        self.assertEqual(turf[259:], before[259:])
        self.assertTrue(all(t < h for t, h in zip(turf[256:259], helix[256:259])))
        # end-zone turf follows its field's deeper turf
        envelope = g.ms.turf_envelope([(86, 110, 61), (82, 106, 58)])        # RGB
        palette = bytes((61, 110, 86, 255)) + bytes(1020)                     # BGRA: the same turf
        ez_helix, sel_helix = g.end_zone_palette(palette, envelope, "synthetic")
        ez_turf, sel_turf = g.end_zone_palette(palette, envelope, "fieldturf")
        self.assertEqual(sel_helix, sel_turf)
        self.assertEqual(sel_turf, [0])
        for t, h in zip(ez_turf[:3], ez_helix[:3]):
            self.assertAlmostEqual(t / h, g.FIELDTURF_SHADE, delta=0.02)
        with self.assertRaisesRegex(ValueError, "unknown surface family"):
            g.rgb_transform((88, 108, 64), "astroturf")

    def test_b778_helix_is_a_little_deeper_and_less_vivid_with_the_same_hue(self):
        import colorsys
        self.assertEqual(g.HELIX_GAIN, tuple(k * g.HELIX_SHADE for k in g.SYNTHETIC_GAIN))
        self.assertTrue(0.85 <= g.HELIX_SATURATION < 1.0)
        def luma(rgb):
            r, gr, b = rgb
            return 0.299 * r + 0.587 * gr + 0.114 * b
        for target in ((86, 107, 58), (84, 105, 62), (72, 93, 58), (98, 124, 66)):      # the Helix look by light
            old, new = g.rgb_transform(target, "synthetic"), g.rgb_transform(target, "helix")
            self.assertTrue(0.90 <= luma(new) / luma(old) <= 0.95, (old, new))
            h0, s0, _ = colorsys.rgb_to_hsv(*(v / 255 for v in old))
            h1, s1, _ = colorsys.rgb_to_hsv(*(v / 255 for v in new))
            self.assertLess(abs(h1 - h0) * 360, 3.0, (old, new))          # same hue (one-byte rounding only)
            self.assertTrue(0.02 <= s0 - s1 <= 0.08, (old, new, s0, s1))   # slightly less saturated
        # the same entries change and paint stays exact; end zones follow the field
        before, rec = fixture()
        plain, plain_receipt = g.paint_scene(before, rec, "synthetic")
        helix, helix_receipt = g.paint_scene(before, rec, "helix")
        self.assertEqual(helix_receipt["decoded_ranges"], plain_receipt["decoded_ranges"])
        self.assertEqual(helix[:256], before[:256])
        self.assertEqual(helix[259:], before[259:])
        envelope = g.ms.turf_envelope([(86, 110, 61), (82, 106, 58)])
        palette = bytes((61, 110, 86, 255)) + bytes(1020)
        _ez, sel = g.end_zone_palette(palette, envelope, "helix")
        self.assertEqual(sel, [0])

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
