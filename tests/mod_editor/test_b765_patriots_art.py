"""Texture-only regressions for the Patriots shoulder/number authoring path."""
from __future__ import annotations

import importlib.util
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zlib

import numpy as np
from PIL import Image, ImageDraw, PngImagePlugin

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import nfl2k5_team_2026_art as art
import nfl_tset_png_import as tset
spec=importlib.util.spec_from_file_location('b765_patriots',ROOT/'tools/b765/u1_patriots.py')
recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)


class PatriotsArtTests(unittest.TestCase):
    def test_polygon_crop_preserves_existing_coverage(self):
        for points in ([[[2.2,3.8],[40.1,9.2],[17.8,35.5]],
                       [[-12.4,-3.9],[22.1,0.2],[4.2,55.7]],
                       [[18.15,10.875],[66,14],[29.25,64]],
                       [[-8,-9],[-3,-4],[-8,-4]]]):
            im=Image.new('L',(64*8,48*8))
            ImageDraw.Draw(im).polygon([(x*8,y*8) for x,y in points],fill=255)
            expected=np.asarray(im.resize((64,48),Image.BOX),np.float32)/255
            np.testing.assert_array_equal(art.polygon_coverage((48,64),points),expected)

    def test_all_ten_traces_share_height_and_baseline(self):
        boxes=[]
        for digit,shape in recipe.block_shapes().items():
            cov=art.render_polygon_glyph(shape,(256,256),height=220,center=[128,128])
            boxes.append(Image.fromarray((cov*255).astype(np.uint8)).getbbox())
            self.assertGreater(float(cov.sum()),1000,digit)
        self.assertEqual(len(boxes),10)
        self.assertEqual(len({(b[1],b[3]) for b in boxes}),1)

    def test_uv_gutter_padding_keeps_stripe_boundaries_fixed(self):
        triangle=np.array([[0,0],[20,0],[0,20]],float)
        band=np.array([[0,5],[15,5],[10,10],[0,10]],float)
        padded=recipe.bleed_triangle_edges(band,triangle)
        np.testing.assert_allclose(padded[[0,1],1],5)
        np.testing.assert_allclose(padded[[2,3],1],10)
        np.testing.assert_allclose(padded[[0,3],0],-1.5)
        self.assertGreater(padded[1,0],band[1,0])

    def test_stripes_do_not_enter_the_neck_region(self):
        triangle=np.array([[8,65,-8,20,20],[10,65,-8,30,20],[12,65,-8,20,30]],float)
        self.assertEqual(recipe.stripe_polygons([triangle],['red','white','red']),[])

    def test_palette_reservation_keeps_rare_protected_colors_exact(self):
        rare=(1,3,7,255)
        pixels=[(i%256,i//256,150,255) for i in range(300) for _ in range(10)]+[rare]
        level=tset.MipLevel(0,len(pixels),1,bytes(v for c in pixels for v in c))
        palette,indices,info=tset.quantize_levels([level],16,locked_colors=[rare])
        self.assertEqual(palette[indices[0][-1]],rare)
        self.assertEqual(info['locked_palette_entries'],1)
        self.assertEqual(tset.quantize_levels([level],16),tset.quantize_levels([level],16,locked_colors=[]))
        with self.assertRaises(tset.ImportError):tset.quantize_levels([level],1,locked_colors=[rare,(2,3,7,255)])

    def test_palette_reservation_metadata_is_explicit_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'palette.png';im=Image.new('RGBA',(2,2),(1,3,7,255))
            im.save(p);self.assertEqual(tset.png_locked_colors(p.read_bytes()),[])
            meta=PngImagePlugin.PngInfo();meta.add_text('nfl2k5_palette_lock',json.dumps({'schema':'nfl2k5_palette_lock/v1','rgba':[[1,3,7,255]]}))
            im.save(p,pnginfo=meta);self.assertEqual(tset.png_locked_colors(p.read_bytes()),[(1,3,7,255)])
            meta=PngImagePlugin.PngInfo();meta.add_text('nfl2k5_palette_lock','{}');im.save(p,pnginfo=meta)
            with self.assertRaises(tset.ImportError):tset.png_locked_colors(p.read_bytes())

    def test_original_mip_texels_are_kept_outside_the_filter_scope(self):
        import hashlib
        blue=bytes([20,30,200,255]);green=bytes([30,150,40,255])
        levels=[tset.MipLevel(n,w,h,blue*(w*h)) for n,(w,h) in enumerate(tset.MIP_DIMENSIONS)]
        mask=np.zeros((256,512),np.uint8);mask[:2,:2]=1
        tail=green*(tset.INDEX_CHAIN_BYTES-512*256)
        doc={'rgba':[tuple(green)],'preserve_mips':{'scope_bits':base64.b64encode(np.packbits(mask).tobytes()).decode(),
             'clean_tail_zlib':base64.b64encode(zlib.compress(tail)).decode(),'clean_tail_sha256':hashlib.sha256(tail).hexdigest()}}
        kept,locked=tset.preserve_reserved_mips(levels,doc)
        self.assertEqual(kept[1].rgba[:4],blue)
        self.assertEqual(kept[1].rgba[4:],green*(kept[1].width*kept[1].height-1))
        palette,indices,_=tset.quantize_levels(kept,16,locked_colors=locked)
        self.assertEqual(palette[indices[1][1]],tuple(green))
        doc['preserve_mips']['clean_tail_sha256']='0'*64
        with self.assertRaises(tset.ImportError):tset.preserve_reserved_mips(levels,doc)

    def test_oversized_reserved_mip_inflate_is_refused(self):
        levels=[tset.MipLevel(n,w,h,b'\0'*(w*h*4)) for n,(w,h) in enumerate(tset.MIP_DIMENSIONS)]
        tail=b'\0'*((tset.INDEX_CHAIN_BYTES-512*256)*4+1)
        doc={'rgba':[(0,0,0,0)],'preserve_mips':{'scope_bits':base64.b64encode(b'\0'*(512*256//8)).decode(),
             'clean_tail_zlib':base64.b64encode(zlib.compress(tail)).decode()}}
        with self.assertRaises(tset.ImportError):tset.preserve_reserved_mips(levels,doc)

    def test_modern_one_has_no_bottom_foot(self):
        cov=art.render_polygon_glyph(recipe.block_shapes()['1'],(128,128),height=100,center=[64,64])
        lower=np.flatnonzero(cov[112]>.5);stem=np.flatnonzero(cov[85]>.5)
        np.testing.assert_array_equal(lower,stem)

    def test_spec_has_no_tv_numbers_and_silver_inner_trim(self):
        p=json.loads((ROOT/'data/nfl2k5_teams_2026/NE.json').read_text())
        for kit in p['kits'].values():
            self.assertEqual(kit['arm_digits'],'none')
            self.assertEqual(kit['digits']['outline'],'number_silver')
            self.assertEqual(kit['digits']['registration'],'as_authored')
            self.assertEqual(set(kit['digits']['glyph_shapes']),set('0123456789'))
            self.assertEqual(kit['unif_color']['facemask'],'#C8102E')

    def test_registration_is_explicit_without_changing_default_png(self):
        with tempfile.TemporaryDirectory() as td:
            a=np.zeros((16,16,4),np.float32)
            old=Path(td)/'old.png';new=Path(td)/'new.png'
            art.save(a,old);art.save(a,new,digit_registration='as_authored')
            with Image.open(old) as im:self.assertNotIn('nfl2k5_digit_registration',im.info)
            with Image.open(new) as im:self.assertEqual(im.info['nfl2k5_digit_registration'],'as_authored')

    def test_optin_bump_preserves_protected_pixels_and_alpha(self):
        a=np.zeros((256,512,4),np.uint8);a[:]=[128,128,250,83]
        yy,xx=np.indices((256,512));a[...,0]=np.where((xx//3+yy//3)%2,180,76)
        b=recipe.modern_bump(a);mask=np.zeros(a.shape[:2],bool)
        mask[98:228,77:247]=True;mask[100:226,320:469]=True
        np.testing.assert_array_equal(a[~mask],b[~mask])
        np.testing.assert_array_equal(a[...,3],b[...,3])
        self.assertLess(float(b[mask,0].std()),float(a[mask,0].std())*.8)
        normals=(b[mask,:3].astype(float)-127.5)/127.5
        self.assertLess(float(np.abs(np.linalg.norm(normals,axis=1)-1).max()),.01)


if __name__=='__main__':unittest.main()
