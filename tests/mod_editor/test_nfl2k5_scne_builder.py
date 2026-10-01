"""Static SCNE builder (u5): parse -> serialize from scratch round trip and the MetLife model's fixed span."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"


def _retail_bundle(name):
    from mod_editor.core import nfl2k5_modern_metlife as ml
    from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
    require_nfl_retail_packs(EXTRACTED)
    with ml._outer_image()(str(EXTRACTED)) as archive:
        e = ml.metlife_entries(archive)[name]
        return archive.read(e.virtual_offset, e.size)


class PushWords(unittest.TestCase):
    def test_encode_decode(self):
        for idx in ([0, 1, 2, 3], [5, 6, 7], list(range(9))):
            words = sb.encode_words(sb.TRIANGLE_STRIP, idx)
            self.assertEqual(sb.decode_words(words), [(sb.TRIANGLE_STRIP, idx)])

    def test_strip_join_keeps_parity(self):
        joined = sb.strips_to_indices([[0, 1, 2], [3, 4, 5, 6]])
        start = len(joined) - 4
        self.assertEqual(joined[start:], [3, 4, 5, 6])
        self.assertEqual(start % 2, 0)

    def test_sphere_contains_points(self):
        pts = [(0, 0, 0), (100.5, -3, 7), (-20, 40.25, 9)]
        c, r = sb.bounding_sphere(pts)
        for p in pts:
            d = sum((a - b) ** 2 for a, b in zip(c, p)) ** 0.5
            self.assertLessEqual(d, r)


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class RetailRoundTrip(unittest.TestCase):
    def test_stadium_scenes_round_trip(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        tx, inv, RR, HEADER, stw = ml._tools()
        for name in ("s18dd.iff", "s18ad.iff", "s19ns.iff"):
            data = _retail_bundle(name)
            chunk = ml.bundle_scenes(data)["stadium"]
            rec, dec = ml._scene(data, chunk)
            scene = sb.parse(dec, chunk.system_bytes)
            out, system, video = sb.serialize(scene)
            again = sb.parse(out, system)
            self.assertEqual([s.name for s in scene.shapes], [s.name for s in again.shapes])
            self.assertEqual([s.streams for s in scene.shapes], [s.streams for s in again.shapes])
            self.assertEqual([[m.words for m in s.submeshes] for s in scene.shapes],
                             [[m.words for m in s.submeshes] for s in again.shapes])
            self.assertEqual([(m.name, m.texture) for m in scene.materials], [(m.name, m.texture) for m in again.materials])
            self.assertEqual([(t.pixels, t.palette) for t in scene.textures], [(t.pixels, t.palette) for t in again.textures])
            self.assertEqual([(m.name, bytes(m.record[0x10:0x20])) for m in scene.markers],
                             [(m.name, bytes(m.record[0x10:0x20])) for m in again.markers])
            self.assertEqual([l.name for l in scene.lights], [l.name for l in again.lights])
            record = RR(outer_index=0, outer_id="", outer_size=len(out), chunk_index=0, chunk_offset=0, kind="SCNE",
                        stored_size=len(out), word_08=system, word_0c=video, word_10=0, word_14=0)
            parsed, _n, _m, _s = inv.parse_scene(0, record, out, {})
            self.assertEqual(len(parsed["shapes"]), len(scene.shapes))

    def test_model_bundle_keeps_every_size(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        from mod_editor.core import nfl2k5_metlife_model as mm
        retail = _retail_bundle("s19nd.iff")
        skin = mm.skin_bundle(retail, "s19nd.iff", retail)
        model, info = mm.model_bundle(skin, "s19nd.iff")
        self.assertEqual(len(model), len(skin))
        tx = ml._tools()[0]
        self.assertEqual([(c.kind, c.offset, c.stored_size) for c in tx.parse_chunks(model, allow_trailing=True)],
                         [(c.kind, c.offset, c.stored_size) for c in tx.parse_chunks(skin, allow_trailing=True)])
        chunk = ml.bundle_scenes(model)["stadium"]
        rec, dec = ml._scene(model, chunk)
        scene = sb.parse(dec, chunk.system_bytes)
        names = {s.name for s in scene.shapes}
        self.assertIn("sideline_home_north", names)
        self.assertIn("digits", names)
        self.assertTrue(any(n.startswith("ml_bowl") for n in names))
        self.assertIn("crowd", {m.name for m in scene.materials})
        self.assertIn("jumbo_tron", {m.name for m in scene.materials})
        self.assertLess(len(dec), 1656832)          # smaller than the retail stadium scene
        for s in scene.shapes:
            if not (s.name.startswith("ml_") or s.name in ("digits", "banners_corp01", "banners_fan01")):
                continue    # untouched retail shapes keep their retail spheres (one binary32 ULP of slack)
            pts = [struct.unpack_from("<3f", s.streams[0], 12 * i) for i in range(s.vertex_count)]
            cx, cy, cz = struct.unpack_from("<3f", s.record, 0)
            r = struct.unpack_from("<f", s.record, 0x48)[0]
            self.assertTrue(all(((p[0] - cx) ** 2 + (p[1] - cy) ** 2 + (p[2] - cz) ** 2) ** 0.5 <= r for p in pts),
                            s.name)


if __name__ == "__main__":
    unittest.main()
