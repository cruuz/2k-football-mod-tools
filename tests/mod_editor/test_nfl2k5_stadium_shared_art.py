"""Residual sponsors and event fields: scope, exact native size, clear untouched areas."""
import json,unittest,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_stadium_shared_art as shared
from mod_editor.core import nfl2k5_modern_venues_2026 as mv

class Catalog(unittest.TestCase):
 def test_pinned_sponsor_items_only_and_excluded_venues_absent(self):
  count=0;fields=0
  for p in shared.ART_ROOT.glob('*/manifest.json'):
   self.assertNotIn(p.parent.name,shared.EXCLUDED)
   for item in shared.items(p.parent.name):
    if item['kind']=='sponsor':
     count+=1;self.assertEqual(item['scene'],'stadium')
    else:
     fields+=1;self.assertEqual(item['kind'],'field-logo');self.assertEqual(item['scene'],'field')
     self.assertEqual(item['size'],[256,256])
    self.assertEqual(item['rgba'].shape[:2],tuple(reversed(item['size'])))
    mask=np.zeros(item['rgba'].shape[:2],bool)
    for x0,y0,x1,y1 in item['rects']:mask[y0:y1,x0:x1]=True
    self.assertFalse(item['rgba'][~mask].any())
    with Image.open(item['master']) as im:
     self.assertEqual(im.size,tuple(4*x for x in item['size']))
  self.assertEqual(count,83)
  self.assertEqual(fields,7)
 def test_clear_panels_leave_the_wall_decals_see_through(self):
  design=json.loads((shared.DATA/'design.json').read_text())
  clear=[(r,o) for r in design['textures'] for o in r['ops'] if o.get('bg')=='clear']
  self.assertEqual({(r['venue'],r['material']) for r,_ in clear},{('s36','wall02'),('s36','wall03_wall01')})
  for r,o in clear:
   self.assertFalse(r['cloth'])
   rgba={i['key']:i for i in shared.items(r['venue'])}[r['material']]['rgba']
   x0,y0,x1,y1=o['rect'];cell=rgba[y0:y1,x0:x1]
   self.assertGreater(float((cell[...,3]==0).mean()),0.5)
   if o['text']:self.assertTrue((cell[...,3]==255).any())
   else:self.assertFalse(cell[...,3].any())
 def test_special_slots_have_only_approved_event_fields_and_no_league_mark_targets(self):
  self.assertEqual(len(shared.special_venues()),19)
  for prefix,row in shared.special_venues().items():
   self.assertEqual(row['stadium_only'],prefix not in {'s31','s39','s41','s42','s43','s44','s45'})
   self.assertFalse(row['league']);self.assertFalse(row['league_art'])
   self.assertEqual(len(row['bundles']),9)
 def test_only_one_home_residual_atlas_is_authored(self):
  homes={(r['venue'],r['material']) for r in json.loads((shared.DATA/'design.json').read_text())['textures'] if r['venue'] in mv.table()['venues']}
  self.assertEqual(homes,{('s05','texscore02_fence')})   # s06's moved to u4's table with tier 3 (st7b)
  self.assertTrue({'s02','s06','s09','s21'} <= shared.EXCLUDED)
  self.assertEqual(set(json.loads((shared.DATA/'design.json').read_text())['excluded_venues']),set(shared.EXCLUDED))
 def test_event_variants_are_complete_and_independent_of_optional_league_marks(self):
  expected={'s31','s39','s41','s42','s43','s44','s45'}
  todo=dict(mv.venues_to_write(dict(venues={},league={})))
  self.assertTrue(expected <= set(todo))
  self.assertNotIn('s40',todo)
  for prefix in expected:
   row=shared.special_venues()[prefix]
   for target in row['field_logos'].values():
    self.assertEqual(set(target['variants']),set(mv.CODES))
    self.assertEqual(target['format'],'P8')
    self.assertTrue(all(v[1:]==[256,256] for v in target['variants'].values()))
 def test_release_catalog_and_allowlist_cover_dependencies(self):
  import runpy
  allow=set((ROOT/'packaging/release-allowlist.txt').read_text().splitlines())
  release=runpy.run_path(str(ROOT/'packaging/check_2k5_mod_studio_release.py'))
  catalog=release['_scorebug_template_pngs'](ROOT)
  required=[ROOT/'mod_editor/core/nfl2k5_stadium_shared_art.py',ROOT/'mod_editor/core/nfl2k5_model_fan_art.py',ROOT/'tools/nfl2k5_residual_sponsor_art.py']
  required += [p for p in shared.DATA.rglob('*') if p.is_file()]
  self.assertEqual({p for p in allow if p.startswith('data/nfl2k5_stadium_shared_art/')},
                   {p.relative_to(ROOT).as_posix() for p in shared.DATA.rglob('*') if p.is_file()})
  for p in required:
   rel=p.relative_to(ROOT).as_posix();self.assertIn(rel,allow)
   if p.suffix=='.png':self.assertEqual(catalog[rel]['sha256'],mv.sha(p.read_bytes()))

if __name__=='__main__':unittest.main()
