"""Diagnostic crossings must not mistake infinite rays or strip connectors for faces."""
import unittest
import json
import builtins
import runpy
from unittest import mock
import numpy as np
from tools.b765.s1_audit import segment_hits,triangles,VENUES,ROOT
from tools.b765.s1_render import clip_near


class Intersections(unittest.TestCase):
    def setUp(self):
        self.tri=np.asarray([[[-1.,0.,-1.],[1.,0.,-1.],[0.,0.,1.]]])

    def test_finite_segment_crossing(self):
        self.assertEqual(segment_hits(np.array([0.,-1.,0.]),np.array([0.,1.,0.]),self.tri).tolist(),[0])

    def test_intersection_past_endpoint_is_not_a_crossing(self):
        self.assertEqual(segment_hits(np.array([0.,1.,0.]),np.array([0.,2.,0.]),self.tri).tolist(),[])

    def test_endpoint_contact_is_not_a_piercing(self):
        self.assertEqual(segment_hits(np.array([0.,0.,0.]),np.array([0.,1.,0.]),self.tri).tolist(),[])

    def test_coplanar_and_outside_triangle_are_not_piercings(self):
        self.assertEqual(segment_hits(np.array([0.,0.,0.]),np.array([.1,0.,.1]),self.tri).tolist(),[])
        self.assertEqual(segment_hits(np.array([2.,-1.,0.]),np.array([2.,1.,0.]),self.tri).tolist(),[])

    def test_nv2a_modes_and_strip_winding(self):
        self.assertEqual(list(triangles(6,[0,1,2,3])),[(0,1,2),(2,1,3)])
        self.assertEqual(list(triangles(5,[0,1,2,3,4,5])),[(0,1,2),(3,4,5)])
        self.assertEqual(list(triangles(7,[0,1,2,3])),[(0,1,2),(0,2,3)])

    def test_home_coverage_comes_from_pack_venue_catalog(self):
        catalog=json.loads((ROOT/'data/nfl2k5_modern_venues_2026/names.json').read_text())['venues']
        self.assertEqual(set(VENUES),set(catalog)|{'s18','s19','s40'})

    def test_render_clips_near_plane_without_creating_a_missing_face(self):
        cam=np.asarray([[0.,0.,0.],[1.,0.,1.],[0.,1.,1.]])
        uv=np.asarray([[0.,0.],[1.,0.],[0.,1.]])
        result=clip_near(cam,uv,np.ones((3,4))*255)
        self.assertEqual(len(result),4)
        self.assertTrue(all(row[0][2]>=.5 for row in result))
        self.assertTrue(any(np.allclose(row[1],[.5,0]) for row in result))

    def test_offline_audit_and_rasterizer_work_without_optional_accelerators(self):
        original_import = builtins.__import__
        def without_accelerators(name, *args, **kwargs):
            if name.split('.')[0] in ('scipy', 'numba'):
                raise ImportError('optional accelerator absent')
            return original_import(name, *args, **kwargs)
        with mock.patch.object(builtins, '__import__', without_accelerators):
            audit = runpy.run_path(str(ROOT / 'tools/b765/s1_audit.py'))
            render = runpy.run_path(str(ROOT / 'tools/b765/s1_render.py'))
        centres = np.asarray([[0.,0.,0.],[1.,0.,0.],[1.01,0.,0.],[0.,2.,0.]])
        self.assertEqual(audit['_spatial_index'](centres).query_ball_point(np.zeros(3), 1.), [0,1])
        screen = np.asarray([[0.,0.,1.],[3.,0.,1.],[0.,3.,1.]])
        pixels = np.zeros((4,4,3), dtype=np.uint8)
        zbuf = np.full((4,4), 1e20)
        texture = np.asarray([[[40,80,120,255]]], dtype=np.uint8)
        render['draw_triangle'](screen, np.zeros((3,2)), np.full((3,4),127.5), texture, zbuf, pixels)
        self.assertEqual(pixels[0,0].tolist(), [40,80,120])
        self.assertEqual(pixels[3,3].tolist(), [0,0,0])
        self.assertEqual(zbuf[0,0], 1.)


if __name__=='__main__':unittest.main()
