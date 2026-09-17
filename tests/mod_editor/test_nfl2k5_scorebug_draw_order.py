"""Submission-order regressions: exercise capacity pressure and a bad native scene."""
from pathlib import Path
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite, nfl2k5_scorebug_ingame as scene
import nfl2k5_scorebug_projection as projection

class AllocationTests(unittest.TestCase):
 def assert_order(self,c):
  order={k:i for i,k in enumerate(c.material_order)}
  rows=sorted(c.quads,key=lambda q:(order[q['material']],q['layer_rank']))
  for at,a in enumerate(rows):
   for b in rows[at+1:]:
    x,y=a['box'],b['box']
    if max(x[0],y[0])<min(x[2],y[2]) and max(x[1],y[1])<min(x[3],y[3]):
     self.assertLessEqual(a['z'],b['z'],(a['name'],b['name']))
  for material,(_,words) in enumerate(scene.layout.SUBMESH_COMMANDS):
   self.assertLessEqual(3*sum(q['material']==material for q in rows)+4,words)
 def test_default_overlap_order_and_reserved_bindings(self):
  for wide in (False,True):
   c=sprite.compile_folder(widescreen=wide);self.assert_order(c)
   for role,material in [('home_logo',5),('away_logo',8),('FLAG',2),('FUMBLE',0)]:
    self.assertEqual(next(q for q in c.quads if q['name']==role)['material'],material)
 def test_full_label_batch_moves_plate_and_repairs_a_material_cycle(self):
  spec,image=sprite.load_layout()
  # Fourteen glyph slots leave only one free quad in batch 7; request two plates.
  for r in spec['static']:
   if r['name'] in ('plate','pointer'):r['material']=7
  # Wing between body and capsule creates a cycle if both retain batch 3.
  wing=next(r for r in spec['static'] if r['name']=='away_wing')
  wing['box']=[837,990,1083,1045]
  next(r for r in spec['static'] if r['name']=='capsule')['z']=-18
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);image.save(p/'template.png');(p/'layout.json').write_text(json.dumps(spec))
   c=sprite.compile_folder(p);self.assert_order(c)
  self.assertTrue(all(q['material']==7 for q in c.quads if q['name'].startswith('down:')))
  self.assertTrue(any(q['material']!=7 for q in c.quads if q['name'] in ('plate','pointer')))
 def test_legacy_depth_convention_preserves_visual_layering(self):
  spec,image=sprite.load_layout();del spec['layer_order']
  for group in ('static','fields','events','brand'):
   for r in spec[group]:r['z']=-20-r['z']
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);image.save(p/'template.png');(p/'layout.json').write_text(json.dumps(spec))
   c=sprite.compile_folder(p)
  current=sprite.compile_folder()
  self.assertEqual(c.table,current.table)
  self.assertEqual(c.material_order,current.material_order)
 def test_overlaps_follow_native_anchors_in_custom_layouts(self):
  spec,image=sprite.load_layout()
  clock=next(r for r in spec['fields'] if r['name']=='play_clock')
  clock['anchor']=[950,955];clock['z']=-16
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);image.save(p/'template.png');(p/'layout.json').write_text(json.dumps(spec))
   c=sprite.compile_folder(p)
  # Its declared box still lies over the red clock cell, but its native glyphs
  # now overlap the down label. The later label must cover those clock glyphs.
  by_name={q['name']:q for q in c.quads}
  a,b=by_name['play_clock:0'],by_name['down:0']
  self.assertLess((c.material_order.index(a['material']),a['layer_rank']),
                  (c.material_order.index(b['material']),b['layer_rank']))

@unittest.skipUnless((ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe').is_file() and importlib.util.find_spec('unicorn'),'Retail and Unicorn required')
class NativeOrderTests(unittest.TestCase):
 def test_preview_obeys_descriptor_order_and_cannot_rescue_an_overdrawn_label(self):
  from PIL import Image
  p=sprite.NativePreview()
  for wide in (False,True):
   g,c=p.capture(dict(down=1,away='DAL',home='KC'),wide)
   try:
    mode=p.modes[wide];live=c['live_decoded'];base=c['body']
    raw=list(projection.submission_batches(mode['scene']))
    relocated=list(projection.submission_batches(live,base))
    self.assertEqual(raw,relocated)
    rows=mode['compiled'].quads
    active=[q['vertex']+j for q in rows for j in range(4) if struct.unpack_from('<I',live,scene.layout.S1+q['vertex']*10)[0]]
    self.assertEqual(len({round(g['world_positions'][v][2],6) for v in active}),1)
    table=sprite.SUBMESH_TABLE
    records=[live[table+i*128:table+(i+1)*128] for i in range(11)]
    plate=next(q for q in rows if q['name']=='plate')
    physical=mode['compiled'].material_order.index(plate['material'])
    bad=bytearray(live);record=records.pop(physical);records.append(record)
    bad[table:table+11*128]=b''.join(records)
    roi=sprite.contracted(sprite.hud_box(next(r for r in mode['compiled'].spec['fields'] if r['name']=='down')['box'],wide),wide)
    roi=tuple(round(v) for v in roi)
    with tempfile.TemporaryDirectory() as directory:
     counts=[]
     for name,decoded in [('good',live),('bad',bytes(bad))]:
      path=Path(directory)/(name+'.png')
      result=projection.render_native(decoded,mode['atlas'],p.fonts,g,path,texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#303030'))
      self.assertEqual(result['raster_policy']['depth'],'none (sprite submission order)')
      counts.append(sum(min(pixel)>200 for pixel in Image.open(path).convert('RGB').crop(roi).getdata()))
     self.assertGreater(counts[0],25)
     self.assertEqual(counts[1],0)
   finally:c['machine'].close()

if __name__=='__main__':unittest.main()
