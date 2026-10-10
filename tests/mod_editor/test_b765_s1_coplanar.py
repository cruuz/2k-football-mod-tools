"""Geometric area/contact and native scene guards for near-coplanar diagnostics."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import struct
import tempfile
import unittest
from unittest import mock

import numpy as np
from tools.b765 import s1_audit as audit, s1_coplanar as coplanar
from mod_editor.core import nfl2k5_scne_builder as builder


def native_scene(*, offset_m=0.0, second_points=None, transformed=False, connectors=False):
    """A serialized/read-back native FLOAT3 scene, including real NV2A index commands."""
    record = bytearray(0x100)
    struct.pack_into('<I', record, 0x44, 2)
    struct.pack_into('<I', record, 0x84, 0x32)
    struct.pack_into('<I', record, 0x88, 0x00080115)
    struct.pack_into('<I', record, 0x90, 0x140)
    struct.pack_into('<I', record, 0x9C, 0x00040121)
    struct.pack_into('<2H', record, 0xC4, 12, 10)
    template = builder.Shape(record, 'template', [],
                             [builder.Submesh(bytearray(0x80), b'')], [None] * 8)
    base = [(0, 0, 0), (100, 0, 0), (0, 100, 0)]
    rail = second_points or [(x, y, z + offset_m * 100) for x, y, z in base]
    command = builder.encode_words(builder.TRIANGLE_STRIP,
                                   [0, 1, 2] + ([2, 2, 2] if connectors else []))
    shapes = [builder.static_shape(template, name, points, [(255, 255, 255, 255)] * 3,
                                    [(0, 0), (1, 0), (0, 1)], [(material, command)])
              for name, points, material in [('crowd_band', base, 0), ('deck_rail', rail, 1)]]
    identity = struct.pack('<16f', *np.eye(4).reshape(-1))
    translated = np.eye(4).reshape(-1); translated[12] = 100
    nodes = [builder.Node(bytearray(0x60), shape.name, shape.name,
                          struct.pack('<16f', *translated) if transformed and index == 1 else identity,
                          identity) for index, shape in enumerate(shapes)]
    scene = builder.Scene('stadium', [],
                           [builder.Material(bytearray(0x80), 'crowd', None),
                            builder.Material(bytearray(0x80), 'att_rail', None)], nodes, shapes, [])
    data, system, _ = builder.serialize(scene)
    return builder.parse(data, system)


class PolygonAreaTests(unittest.TestCase):
    def setUp(self):
        self.triangle = np.asarray([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
        self.normal = np.asarray([0., 0., 1.])

    def test_full_overlap_has_known_half_square_metre_area(self):
        self.assertAlmostEqual(coplanar.overlap_area(self.triangle, self.triangle, self.normal), .5)
        # Polygon winding must not alter area or invent a backface interpretation.
        self.assertAlmostEqual(coplanar.overlap_area(self.triangle, self.triangle[::-1], self.normal), .5)

    def test_shared_edge_contact_has_no_area(self):
        adjacent = np.asarray([[1., 0., 0.], [1., 1., 0.], [0., 1., 0.]])
        self.assertEqual(coplanar.overlap_area(self.triangle, adjacent, self.normal), 0)

    def test_disjoint_triangles_have_no_area(self):
        self.assertEqual(coplanar.overlap_area(self.triangle, self.triangle + [2., 0., 0.], self.normal), 0)

    def test_dominant_projection_preserves_tilted_world_area(self):
        tilted = np.asarray([[0., 0., 0.], [1., 0., 1.], [0., 1., 0.]])
        normal = np.cross(tilted[1] - tilted[0], tilted[2] - tilted[0])
        self.assertAlmostEqual(coplanar.overlap_area(tilted, tilted, normal), np.sqrt(2) / 2)

    def test_area_measurement_does_not_normalize_the_callers_normal_in_place(self):
        normal = np.asarray([0., 0., 2.])
        self.assertAlmostEqual(coplanar.overlap_area(self.triangle, self.triangle, normal), .5)
        self.assertEqual(normal.tolist(), [0., 0., 2.])


class NativeMeasurementTests(unittest.TestCase):
    def test_portable_radius_index_preserves_complete_native_measurements(self):
        cases = [
            (native_scene(offset_m=.001, connectors=True), 1),
            (native_scene(offset_m=.003), 0),
            (native_scene(second_points=[(100, 0, 0), (100, 100, 0), (0, 100, 0)]), 0),
        ]
        for scene, expected_count in cases:
            with self.subTest(expected_count=expected_count):
                accelerated = coplanar.measure_scene(scene)
                with mock.patch.object(audit, 'cKDTree', None):
                    portable = coplanar.measure_scene(scene)
                # Compare native IDs, scope hash, distances, normals and areas,
                # alongside the independently known geometric count.
                self.assertEqual(portable, accelerated)
                self.assertEqual(portable['candidate_count'], expected_count)
                if expected_count:
                    pair = portable['candidates'][0]
                    self.assertEqual(pair['first']['vertices'], [0, 1, 2])
                    self.assertEqual(pair['second']['shape'], 1)
                    self.assertAlmostEqual(pair['projected_overlap_area_m2'], .5)
                    self.assertAlmostEqual(pair['plane_distance_max_m'], .001, places=8)

    def test_native_readback_preserves_ids_and_skips_strip_connectors(self):
        result = coplanar.measure_scene(native_scene(connectors=True))
        self.assertEqual((result['positive_faces'], result['candidate_count']), (2, 1))
        candidate = result['candidates'][0]
        self.assertEqual(candidate['first']['vertices'], [0, 1, 2])
        self.assertEqual(candidate['second']['shape'], 1)
        self.assertEqual(candidate['second']['submesh'], 0)
        self.assertEqual(candidate['second']['node_indices'], [1])
        self.assertEqual(candidate['normal_relationship'], 'same_facing')
        self.assertAlmostEqual(candidate['projected_overlap_area_m2'], .5)

    def test_parallel_offset_distance_threshold_controls_pair_inclusion(self):
        within = coplanar.measure_scene(native_scene(offset_m=.001))
        outside = coplanar.measure_scene(native_scene(offset_m=.003))
        self.assertEqual(within['candidate_count'], 1)
        self.assertAlmostEqual(within['candidates'][0]['plane_distance_max_m'], .001, places=8)
        self.assertEqual(outside['candidate_count'], 0)
        self.assertEqual(coplanar.measure_scene(native_scene(offset_m=.003),
                                               distance_max_m=.004)['candidate_count'], 1)

    def test_native_shared_edge_and_disjoint_faces_are_not_candidates(self):
        edge = [(100, 0, 0), (100, 100, 0), (0, 100, 0)]
        disjoint = [(200, 0, 0), (300, 0, 0), (200, 100, 0)]
        self.assertEqual(coplanar.measure_scene(native_scene(second_points=edge))['candidate_count'], 0)
        self.assertEqual(coplanar.measure_scene(native_scene(second_points=disjoint))['candidate_count'], 0)

    def test_transformed_native_node_refuses_local_geometry_measurement(self):
        with self.assertRaisesRegex(ValueError, 'non-identity node matrix14'):
            coplanar.measure_scene(native_scene(transformed=True))

    def test_invalid_thresholds_refuse_before_measurement(self):
        for options in ({'distance_max_m': -1}, {'normal_abs_dot_min': 1.1},
                        {'overlap_area_min_m2': float('nan')}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                coplanar.measure_scene(native_scene(), **options)

    def test_output_cannot_overwrite_existing_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'stadium_audit.json'; target.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'preserving native inputs and stadium_audit'):
                coplanar.run(Path(temporary), ['s07dd.iff'], target)
            self.assertEqual(target.read_text(), 'keep')

    def test_audit_cli_routes_separate_outputs_without_loading_existing_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / 'stadium_audit.json'; target.write_text('keep existing content')
            with mock.patch.object(coplanar, 'run') as run:
                self.assertEqual(audit.main(['--files', temporary, '--out', temporary,
                                             '--near-coplanar-only', '--names', 's07dd.iff']), 0)
                self.assertEqual(run.call_args.args,
                                 (directory, ['s07dd.iff'], directory / 'near_coplanar_crowd_pairs.json'))
            self.assertEqual(target.read_text(), 'keep existing content')


if __name__ == '__main__':
    unittest.main()
