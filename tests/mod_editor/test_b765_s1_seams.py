"""Native crowd seams exclude connector triangles and keep exact vertex IDs."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402
from tools.b765 import s1_seams as seams  # noqa: E402


def native_bundle(*, right_v=.4, material=0, degenerate=False, separated=False):
    record = bytearray(0x100)
    struct.pack_into("<I", record, 0x44, 2)
    struct.pack_into("<4f", record, 0x10, 0, 0, 0, 1)
    struct.pack_into("<I", record, 0x84, 0x32)
    struct.pack_into("<I", record, 0x88, 0x00080115)
    struct.pack_into("<I", record, 0x90, 0x140)
    struct.pack_into("<I", record, 0x9C, 0x00040121)
    struct.pack_into("<2H", record, 0xC4, 12, 10)
    template = sb.Shape(record, "template", [], [sb.Submesh(bytearray(0x80), b"")], [None] * 8)
    shapes = []
    for i, (positions, vs) in enumerate([
        ([(-100, 0, 0), (-100, 100, 0), (0, 0, 0), (0, 100, 0)], [.1, .1, .2, .2]),
        ([(0, 0, 0), (0, 100, 0), (100, 0, 0), (100, 100, 0)],
         [right_v, right_v, right_v + .1, right_v + .1]),
    ]):
        if i == 1 and separated:
            positions = [(x, y, z + .001) for x, y, z in positions]
        if i == 1 and degenerate:
            positions = [(0, 0, 0), (0, 100, 0), (0, 0, 0), (0, 100, 0)]
        uv = [(.2425 if k % 2 == 0 else .0075, v) for k, v in enumerate(vs)]
        shapes.append(sb.static_shape(template, "band" + str(i), positions,
                                      [(101, 102, 103, 255)] * 4, uv,
                                      [(material if i else 0,
                                        sb.encode_words(sb.TRIANGLE_STRIP, [0, 1, 2, 3]))],
                                      uv_constant=(2, 2, 0, 0)))
    identity = struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    nodes = [sb.Node(bytearray(0x60), s.name, s.name, identity, identity) for s in shapes]
    scene = sb.Scene("stadium", [], [sb.Material(bytearray(0x80), "crowd", None),
                                    sb.Material(bytearray(0x80), "seat", None)], nodes, shapes, [])
    decoded, system, video = sb.serialize(scene)
    chunk, _ = sb.compressed_chunk("SCNE", decoded, system, video,
                                   stream_tag=3, offset_bits=12, optimal=False)
    return chunk


class CrowdSeamTests(unittest.TestCase):
    def test_active_matching_column_keeps_ids_and_wrapped_uv(self):
        report = seams.analyze_bundle(native_bundle(), "synthetic.iff")
        self.assertEqual(report["matched_active_column_pairs"], 1)
        pair = report["pairs"][0]
        self.assertEqual(pair["a"]["vertices_bottom_top"], [2, 3])
        self.assertEqual(pair["b"]["vertices_bottom_top"], [0, 1])
        self.assertEqual(pair["a"]["bottom_m"], pair["b"]["bottom_m"])
        self.assertEqual(pair["a"]["top_m"], pair["b"]["top_m"])
        self.assertAlmostEqual(pair["wrapped_v_phase_jump_bottom"], -.2, places=4)
        self.assertTrue(pair["matching_u_range"])
        self.assertTrue(all(f["area_m2"] > 0 for s in ("a", "b")
                            for f in pair[s]["active_adjacent_faces"]))

    def test_repeat_equivalent_uv_phase_does_not_create_seam(self):
        self.assertEqual(seams.analyze_bundle(native_bundle(right_v=1.2), "same.iff")
                         ["matched_active_column_pairs"], 0)

    def test_collapsed_connector_faces_do_not_create_seam(self):
        report = seams.analyze_bundle(native_bundle(degenerate=True), "connector.iff")
        self.assertEqual(report["matched_active_column_pairs"], 0)
        self.assertEqual(report["used_crowd_vertices"], 4)

    def test_non_crowd_face_does_not_create_seam(self):
        self.assertEqual(seams.analyze_bundle(native_bundle(material=1), "seat.iff")
                         ["matched_active_column_pairs"], 0)

    def test_nearby_column_is_not_an_exact_coincident_column(self):
        self.assertEqual(seams.analyze_bundle(native_bundle(separated=True), "nearby.iff")
                         ["matched_active_column_pairs"], 0)

    def test_native_uv_axes_in_optional_atlas_comparison(self):
        atlas = np.zeros((256, 256, 4), dtype=np.uint8)
        atlas[38:66, :, :] = 255  # V=.2 opaque; V=.4 transparent, regardless of U.
        report = seams.analyze_bundle(native_bundle(), "atlas.iff", atlas=atlas)
        sample = report["pairs"][0]["atlas_at_seam"]
        self.assertEqual(sample["side_a_opaque_fraction"], 1)
        self.assertEqual(sample["side_b_opaque_fraction"], 0)
        self.assertEqual(sample["opacity_disagreement_fraction"], 1)

    def test_bilinear_sampling_wraps_at_pixel_centres(self):
        atlas = np.array([[[10, 20, 30, 255], [110, 120, 130, 0]]], dtype=np.uint8)
        np.testing.assert_array_equal(seams.sample_atlas(atlas, .25, .5), atlas[0, 0])
        np.testing.assert_allclose(seams.sample_atlas(atlas, 0, .5), [60, 70, 80, 127.5])
        np.testing.assert_allclose(seams.sample_atlas(atlas, 1, .5), [60, 70, 80, 127.5])

    def test_deterministic_report_and_read_only_output_guard(self):
        data = native_bundle()
        a = seams.analyze_bundle(data, "same.iff")
        self.assertEqual(seams.geometry.json_bytes(a),
                         seams.geometry.json_bytes(seams.analyze_bundle(data, "same.iff")))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "s07dd.iff"
            path.write_bytes(data)
            self.assertEqual(seams.main(["--input", str(path), "--output", str(path)]), 2)
            self.assertEqual(path.read_bytes(), data)

    def test_invalid_threshold_refused(self):
        for value in (-.1, .5, float("nan")):
            with self.assertRaises(ValueError):
                seams.analyze_bundle(native_bundle(), "bad.iff", phase_threshold=value)


if __name__ == "__main__":
    unittest.main()
