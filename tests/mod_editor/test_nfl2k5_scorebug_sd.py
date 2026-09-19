"""SD atlas footprints, worst field compression, and tiny colour preservation."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_assets as assets


def sampling_receipt():
 spec,image=s.load_layout();records=[]
 # Maximum supported formatted widths, including native ordinal suffixes and
 # Inches. Every digit and ordinal in each set is then tested at that bound.
 longest={'score':list('888'),'clock':list('60:00'),'small':['4','TH'],'quarter':['4TH'],
          'label':['4','th',' ','&',' ','Inch','es'],'ticks':['~','~','~']}
 for wide in (False,True):
  sx=s.x_scale(wide)*(s.WIDE_CONTRACTION if wide else 1);sy=448/1080
  for row in spec['static']+spec['brand']+spec['events']:
   if row['cell']=='logo':continue
   x,y,r,b=spec['cells'][row['cell']]['box'];a,c,d,e=row['box']
   w,h=(d-a)*sx,(e-c)*sy
   records.append(dict(aspect='16:9' if wide else '4:3',cell=row['cell'],field=row['name'],texels=[r-x,b-y],minimum_footprint=[w,h]))
  for field in spec['fields']:
   gs=spec['glyph_sets'][field['glyph_set']];glyphs=gs['glyphs'];f=field['size']/gs['cap_height']
   tokens=longest[field['glyph_set']]
   total=sum(glyphs[t]['advance'] for t in tokens)-glyphs[tokens[-1]]['advance']+glyphs[tokens[-1]]['size'][0]
   compression=min(1,(field['box'][2]-field['box'][0])/(total*f))
   for token,g in glyphs.items():
    if not all(g['size']):continue
    x,y,r,b=spec['cells'][g['cell']]['box'];w,h=g['size']
    records.append(dict(aspect='16:9' if wide else '4:3',cell=g['cell'],field=field['name'],texels=[r-x,b-y],minimum_footprint=[w*sx*f*compression,h*sy*f]))
 return records

class SDTests(unittest.TestCase):
 def test_every_atlas_cell_fits_both_aspects_even_at_worst_field_compression(self):
  for row in sampling_receipt():
   self.assertTrue(all(t<=p+.02 for t,p in zip(row['texels'],row['minimum_footprint'])),row)
 def test_rare_dark_feather_pixels_survive_p8_palette(self):
  from PIL import Image
  import numpy as np
  c=s.compile_folder();reserved=tuple(c.atlas.crop(c.cells['pointer']).getdata())
  palette,indices=assets.quantize_alpha_aware(c.atlas,reserved=reserved)
  decoded=np.asarray(palette,dtype=np.uint8)[np.frombuffer(indices,dtype=np.uint8)].reshape(c.atlas.height,c.atlas.width,4)
  x,y,r,b=c.cells['pointer']
  self.assertTrue(np.array_equal(decoded[y:b,x:r],np.asarray(c.atlas)[y:b,x:r]))
  self.assertLessEqual(len(palette),256)
  self.assertGreater(len(set(c.atlas.getchannel('A').getdata())),64)
 def test_template_cells_and_glyph_metrics_are_distinct_coordinate_spaces(self):
  spec,_=s.load_layout();g=spec['glyph_sets']['label']['glyphs']['0'];x,y,r,b=spec['cells'][g['cell']]['box']
  self.assertEqual([r-x,b-y],[8,12]);self.assertGreaterEqual(g['size'][1]*448/1080,12)
  self.assertGreaterEqual(g['size'][0]/3,8)

if __name__=='__main__':unittest.main()
