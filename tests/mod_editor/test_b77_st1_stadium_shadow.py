"""b77 st1: afternoon field shadows cast by the stadium the bundle carries, and MetLife's measured afternoon response."""
from __future__ import annotations

import json
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402

from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402
from mod_editor.core import nfl2k5_stadium_shadow as sh  # noqa: E402

#: the retail game (a hydrated tree's extracted folder; NFL2K5_RETAIL_SOURCE names another extracted folder or disc image)
EXTRACTED = Path(os.environ.get("NFL2K5_RETAIL_SOURCE", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))


def wall(x, z0, z1, height):
    """Two triangles of a vertical wall along z at x (metres)."""
    a, b, c, d = (x, 0.0, z0), (x, height, z0), (x, height, z1), (x, 0.0, z1)
    return np.array([[a, b, c], [a, c, d]], dtype=np.float64)


class Mapping(unittest.TestCase):
    def test_one_texture_spans_188_metres_from_the_executable_constants(self):
        self.assertEqual(struct.pack("<f", sh.DETAIL_SCALE), struct.pack("<I", 0x38DE9A9E))
        self.assertAlmostEqual(sh.TEXTURE_M, 188.0439, places=3)
        self.assertAlmostEqual(sh.TEXEL_M, 0.73455, places=4)

    def test_the_window_covers_the_detail_layer_with_a_margin(self):
        # E_detail spans x +-26.21 m and z +-56.69 m
        self.assertGreaterEqual(sh.WINDOW_U * sh.TEXEL_M, 26.21 + 2 * sh.TEXEL_M)
        self.assertGreaterEqual(sh.WINDOW_V * sh.TEXEL_M, 56.69 + 2 * sh.TEXEL_M)

    def test_the_sun_vector_is_the_exact_unit_vector(self):
        x, y, z = sh.sun_vector(315, 35)
        self.assertAlmostEqual(x * x + y * y + z * z, 1.0, places=15)
        self.assertLess(x, 0)
        self.assertGreater(z, 0)
        self.assertEqual(sh.sun_vector(315, 35), sh.sun_vector(315, 35))


class Cast(unittest.TestCase):
    def test_a_wall_casts_its_height_over_the_tangent_of_the_sun(self):
        # a 20 m wall at x = -30 m, the sun low in the -x sky at 45 degrees: the shadow reaches x = -10 m
        tris = wall(-30.0, -70.0, 70.0, 20.0)
        counts = sh.coverage(tris, sh.sun_vector(270, 45))
        full = sh.SUPERSAMPLE ** 2
        row = counts[sh.CENTRE]
        u = lambda x: int(sh.CENTRE + x / sh.TEXEL_M)       # noqa: E731
        self.assertEqual(row[u(-20.0)], full)               # in the shadow
        self.assertEqual(row[u(-12.0)], full)
        self.assertEqual(row[u(-8.0)], 0)                   # sunlit
        self.assertEqual(row[u(20.0)], 0)
        self.assertEqual(int(counts[0, 0]), full)           # outside the window: shadow, as retail authors it

    def test_a_sun_from_plus_z_throws_shadows_toward_minus_z(self):
        # a 10 m wall across the field at z = +50 m, sun from +z at 45 degrees: shadow from z = +50 to z = +40
        a, b, c, d = (-40.0, 0.0, 50.0), (-40.0, 10.0, 50.0), (40.0, 10.0, 50.0), (40.0, 0.0, 50.0)
        tris = np.array([[a, b, c], [a, c, d]], dtype=np.float64)
        counts = sh.coverage(tris, sh.sun_vector(0, 45))
        v = lambda z: int(sh.CENTRE + z / sh.TEXEL_M)       # noqa: E731
        self.assertEqual(counts[v(45.0), sh.CENTRE], sh.SUPERSAMPLE ** 2)
        self.assertEqual(counts[v(35.0), sh.CENTRE], 0)
        self.assertEqual(counts[v(0.0), sh.CENTRE], 0)

    def test_the_levels_are_the_retail_ramp_and_soft_by_about_a_texel(self):
        tris = wall(-30.0, -70.0, 70.0, 20.0)
        alpha = sh.alpha_levels(sh.coverage(tris, sh.sun_vector(270, 45)))
        self.assertEqual(alpha.dtype, np.uint8)
        self.assertLessEqual(set(np.unique(alpha).tolist()), set(sh.LEVELS))
        row = alpha[sh.CENTRE, sh.CENTRE - sh.WINDOW_U:sh.CENTRE + sh.WINDOW_U]
        soft = [v for v in row.tolist() if 0 < v < 254]
        self.assertLessEqual(len(soft), 4)                  # one edge: the coverage texel and about a texel each side
        self.assertEqual(int(alpha[0, 0]), 254)

    def test_ground_level_props_cast_nothing(self):
        self.assertIn("sideline", sh.PROP_PREFIXES)
        self.assertIn("env_", sh.PROP_PREFIXES)         # the environment backdrop band would shade everything
        self.assertGreater(sh.GROUND_M, 0)


class Venues(unittest.TestCase):
    def test_metlife_carries_the_retail_giants_stadium_sun(self):
        rows = sh.venues()
        for prefix in ("s18", "s19"):
            self.assertEqual(rows[prefix]["sun"], {"azimuth_deg": 315, "elevation_deg": 35})
            self.assertTrue(rows[prefix]["fit"])


class Stage2(unittest.TestCase):
    def test_every_modern_venue_with_a_shadow_texture_has_a_row(self):
        rows = sh.venues()
        for option, prefixes in sh.OPTION_VENUES.items():
            for prefix in prefixes:
                if prefix in ("s01", "s11", "s15", "s23"):      # retail domes: no shadow texture in any bundle
                    continue
                self.assertIn(prefix, rows, f"{option} {prefix}")
                row = rows[prefix]
                self.assertTrue(row.get("roof") == "closed" or "sun" in row, prefix)

    def test_closed_roofs_are_the_indoor_modern_venues(self):
        closed = sorted(p for p, row in sh.venues().items() if row.get("roof") == "closed")
        self.assertEqual(closed, ["s07", "s20", "s24", "s40"])

    def test_a_closed_roof_lights_the_whole_window(self):
        from unittest import mock
        found = (None, None, None)
        captured = {}

        def fake_write(bundle, alpha):
            captured["alpha"] = alpha
            return bytes(bundle), dict(offset=0, length=0, before_sha256="", after_sha256="", decoded_sha256="")
        tx, ml = mock.Mock(), mock.Mock()
        ml.bundle_scenes.return_value = {"stadium": mock.Mock(system_bytes=0)}
        tx.decode_chunk.return_value = (b"", None)
        with mock.patch.object(sh, "shadow_chunk", return_value=found), \
                mock.patch.object(sh, "_tools", return_value=(tx, ml)), \
                mock.patch.object(sh, "write_shadow", side_effect=fake_write):
            sh.bundle_shadow(b"x", "s20")
        a = captured["alpha"]
        w = (slice(sh.CENTRE - sh.WINDOW_V, sh.CENTRE + sh.WINDOW_V), slice(sh.CENTRE - sh.WINDOW_U, sh.CENTRE + sh.WINDOW_U))
        self.assertTrue((a[w] == 0).all())
        self.assertEqual(int(a[0, 0]), 254)

    def test_the_fit_ladder_ends_on_two_levels(self):
        self.assertEqual(sh.FIT_LADDER[0], (True, sh.LEVELS))
        self.assertEqual(sh.FIT_LADDER[-1], (False, (0, 254)))
        tris = wall(-30.0, -70.0, 70.0, 20.0)
        hard = sh.alpha_levels(sh.coverage(tris, sh.sun_vector(270, 45)), False, (0, 254))
        self.assertEqual(set(np.unique(hard).tolist()), {0, 254})

    def test_the_build_runs_the_step_after_the_stadium_writers_and_before_surfaces(self):
        text = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        step = text.index('stadium_shadow.apply_to_image(target')
        self.assertLess(text.index('everbank.apply_to_image(target'), step)
        self.assertLess(text.index('practice.apply_to_image(target'), step)
        self.assertLess(step, text.index('surfaces.apply_to_image(target'))


class Surfaces(unittest.TestCase):
    def test_only_metlife_afternoon_has_a_measured_response(self):
        measured = {(p, light) for p, row in ms.venues().items() for light in (row.get("response") or {})}
        self.assertEqual(measured, {("s18", "afternoon"), ("s19", "afternoon")})
        self.assertEqual(ms.venue_response("s18", "afternoon"), (1.4744, 1.7017, 1.6134))
        self.assertIsNone(ms.venue_response("s18", "day"))
        self.assertIsNone(ms.venue_response("s13", "afternoon"))

    def test_the_measured_response_is_above_the_inferred_one_on_every_channel(self):
        inferred = ms.field_response(ms.venue_look("s18"), "afternoon", "quad")
        for r in ms.venue_response("s18", "afternoon"):
            self.assertGreater(r, inferred)

    def test_a_per_channel_response_divides_each_channel(self):
        look, rig, target = ms.venue_look("s18"), "afternoon", (20, 30, 15)
        self.assertEqual(ms.solve_map_mean(look, "afternoon", rig, response=2.0, target=target),
                         ms.solve_map_mean(look, "afternoon", rig, response=(2.0, 2.0, 2.0), target=target))
        one = ms.solve_map_mean(look, "afternoon", rig, response=1.0, target=target)
        two = ms.solve_map_mean(look, "afternoon", rig, response=(1.0, 2.0, 1.0), target=target)
        self.assertLess(max(one), ms.MAP_CEILING)
        self.assertAlmostEqual(two[1], one[1] / 2)          # green is never clamped below the ceiling

    def test_a_measured_response_needs_an_rgb_and_a_source(self):
        original = ms.VENUES_PATH
        doc = json.loads(original.read_text(encoding="utf-8"))
        row = next(r for r in doc["venues"] if r["prefix"] == "s18")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for broken in ({"afternoon": {"rgb": [1.5, 1.7]}}, {"afternoon": {"rgb": [1.5, 1.7, 1.6]}},
                           {"dusk": {"rgb": [1.5, 1.7, 1.6], "source": "x"}}):
                row["response"] = broken
                path = Path(tmp) / "venues.json"
                path.write_text(json.dumps(doc), encoding="utf-8")
                try:
                    ms.VENUES_PATH = path
                    with self.assertRaises(ms.ModernSurfacesError):
                        ms.venues()
                finally:
                    ms.VENUES_PATH = original


@unittest.skipUnless(EXTRACTED.exists(), "needs the hydrated retail archive")
class Retail(unittest.TestCase):
    def test_the_retail_giants_stadium_texture_is_that_stadium_under_the_venue_sun(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        if EXTRACTED.is_dir():
            from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
            require_nfl_retail_packs(EXTRACTED)
        tx = ml._tools()[0]
        with ml._outer_image()(str(EXTRACTED)) as archive:
            e = ml.metlife_entries(archive)["s18ad.iff"]
            data = archive.read(e.virtual_offset, e.size)
        chunk = ml.bundle_scenes(data)["stadium"]
        decoded, _ = tx.decode_chunk(data, chunk)
        cast = sh.cast(decoded, chunk.system_bytes, sh.venue_sun("s18"))
        retail = sh.read_alpha(data)
        w = (slice(sh.CENTRE - sh.WINDOW_V, sh.CENTRE + sh.WINDOW_V), slice(sh.CENTRE - sh.WINDOW_U, sh.CENTRE + sh.WINDOW_U))
        self.assertGreater(((cast[w] > 127) == (retail[w] > 127)).mean(), 0.97)

    def test_the_metlife_model_writes_the_pinned_shadow_into_the_afternoon_bundle(self):
        from mod_editor.core import nfl2k5_metlife_model as mm
        from mod_editor.core import nfl2k5_modern_metlife as ml
        pins = {p["name"]: p for p in mm.model_pins()["bundles"]}
        self.assertEqual(sorted(n for n, p in pins.items() if "shadow" in p), ["s18ad.iff", "s19ad.iff"])
        with ml._outer_image()(str(EXTRACTED)) as archive:
            entries = ml.metlife_entries(archive)
            e, d = entries["s18ad.iff"], entries[ml.dry_name("s18ad.iff")]
            retail, dry = archive.read(e.virtual_offset, e.size), archive.read(d.virtual_offset, d.size)
        skin = mm.skin_bundle(retail, "s18ad.iff", dry)
        model, info = mm.model_bundle(skin, "s18ad.iff")
        sp = pins["s18ad.iff"]["shadow"]
        self.assertEqual(mm.sha(model[sp["offset"]:sp["offset"] + sp["length"]]), sp["model_sha256"])
        self.assertEqual(mm.sha(skin[sp["offset"]:sp["offset"] + sp["length"]]), sp["skin_sha256"])
        self.assertEqual(info["shadow"]["sun"], sp["sun"])


if __name__ == "__main__":
    unittest.main()
