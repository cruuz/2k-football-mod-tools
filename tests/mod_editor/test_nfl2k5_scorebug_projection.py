"""Native installed geometry, safe area, both direction modes and widescreen."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(Path(__file__).resolve().parent)]
from test_nfl2k5_scorebug_runtime import XBE,PACK,HAVE_UC
from mod_editor.core import nfl2k5_scorebug_ingame as r,nfl2k5_scorebug_resources as a
from nfl2k5_scorebug_projection import native_geometry,v7_baseline


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and importlib.util.find_spec('PIL'),
                     'pinned USA XBE, pack 0, Pillow and Unicorn required')
class ProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe=XBE.read_bytes()
        with PACK.open('rb') as f:
            view=a.PackView.from_fd(f.fileno(),0,PACK.stat().st_size)
            cls.spans={n:view[v['pack_offset']:v['pack_offset']+v['span_size']] for n,v in a.RESOURCES.items()}
        cls.after=r.decode(r.apply(cls.spans['score_bug'],'score_bug')[0])[1]
        cls.normal=native_geometry(cls.xbe,cls.after)

    def test_reference_measurement_and_installed_frame_agree(self):
        from PIL import Image
        path=ROOT/'docs/scorebug_ingame/target_NO_MIA.png'
        if not path.is_file():self.skipTest('target_NO_MIA.png reference absent')
        with Image.open(path) as source:
            im=source.convert('RGB')
        self.assertEqual(im.size,(1280,960))
        # Long neutral frame rails distinguish the scorebug from green field
        # lines. ROI excludes the synthetic footer and watermark.
        rails=[]
        for y in range(700,880):
            start=None
            for x in range(im.width):
                color=im.getpixel((x,y));hit=max(color)-min(color)<20
                if hit and start is None:start=x
                if start is not None and (not hit or x==im.width-1):
                    if x-start>900:rails.append((start,y,x,y))
                    start=None
        measured=[min(v[0] for v in rails)/2,min(v[1] for v in rails)/2,
                  max(v[2] for v in rails)/2,max(v[3] for v in rails)/2]
        self.assertEqual(measured,[84,381,560,429])
        for want,have in zip(measured,self.normal['frame']):self.assertAlmostEqual(want,have,delta=.1)
        self.assertEqual(self.normal['native_root_matrix'][12:14],[320,408])

    def test_both_modes_and_native_slide_keep_whole_clock_inside_safe_area(self):
        for mode in (0,1):
            for slide in (0,1):
                geometry=native_geometry(self.xbe,self.after,mode=mode,slide=slide)
                for name in ('frame','clock','down'):
                    x0,y0,x1,y1=geometry[name]
                    self.assertTrue(0<=x0<x1<=640,(name,geometry[name]))
                    self.assertTrue(16<=y0<y1<=464,(name,geometry[name]))
                self.assertLess(geometry['frame_instructions'],12000)

    def test_widescreen_activates_real_hook_without_vertical_scale_or_shift(self):
        normal=self.normal
        wide=native_geometry(self.xbe,self.after,widescreen=True)
        for name in ('frame','clock','down'):
            for i in (1,3):self.assertAlmostEqual(normal[name][i],wide[name][i],places=4)
            self.assertAlmostEqual(wide[name][2]-wide[name][0],(normal[name][2]-normal[name][0])*27/32,places=3)
        # Display stretch cancels this contraction and retains 4:3 HUD proportions.
        self.assertAlmostEqual((wide['frame'][2]-wide['frame'][0])*32/27,
                               normal['frame'][2]-normal['frame'][0],places=3)

    def test_shipped_v7_baseline_does_not_prove_a_twofold_mesh_scale(self):
        decoded,_=v7_baseline(self.spans)
        before=native_geometry(self.xbe,decoded,root=(320,424))
        self.assertAlmostEqual(before['frame'][1]-self.normal['frame'][1],16,places=3)
        self.assertAlmostEqual(before['frame'][2]-before['frame'][0],
                               self.normal['frame'][2]-self.normal['frame'][0],places=3)
        self.assertAlmostEqual(self.normal['clock'][2]-self.normal['clock'][0],158,delta=.02)


if __name__=='__main__':unittest.main()
