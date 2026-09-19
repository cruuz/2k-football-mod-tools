"""One brand quad, real weekday-site dispatch, conservative date fallbacks."""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_ingame as scene,nfl2k5_calendar_engine as calendar,nfl2k5_xbe_space as space
import nfl2k5_scorebug_projection as projection
RETAIL=ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe'
NATIVE=RETAIL.is_file() and (RETAIL.parent/'vc_53450030/0').is_file() and importlib.util.find_spec('unicorn') is not None

class ContractTests(unittest.TestCase):
 def test_two_cells_one_quad_and_three_policies(self):
  tables=[]
  for mode in s.WATERMARK_MODES:
   c=s.compile_folder(watermark=mode);tables.append(c.table)
   self.assertEqual(len(c.quads),47)
   self.assertEqual(sum(q.get('brand',False) for q in c.quads),1)
   brand=next(q for q in c.quads if q.get('brand'));self.assertEqual(brand['initial_cell'],'espn_mnf' if mode=='mnf' else 'espn_nfl')
   self.assertEqual(brand['initial_colour'],0 if mode=='off' else 0xffffffff)
   self.assertTrue({'espn_nfl','espn_mnf'}<=set(c.cells))
  self.assertEqual(len(set(tables)),3)
  with self.assertRaises(ValueError):s.compile_folder(watermark='nfl_on_sunday')
 def test_build_setting_round_trip_and_presets(self):
  from mod_editor.core import mod_build as build,nfl2k5_build_settings as saved
  for mode in s.WATERMARK_MODES:
   plan=build.BuildPlan('','',scorebug_watermark=mode)
   self.assertEqual(saved.to_plan(saved.from_plan(plan),'','').scorebug_watermark,mode)
  for name in ('softdrink_basic','softdrink_advanced','softdrink_experimental'):
   plan=build.apply_preset(build.BuildPlan('',''),name)
   self.assertFalse(plan.scorebug_runtime);self.assertEqual(plan.scorebug_watermark,'auto')
  with self.assertRaises(ValueError):saved.build_settings({'scorebug_watermark':'bad'})


def brand_record(compiled):
 h=s.HEADER.unpack_from(compiled.table);start=h[5]-s.TABLE_OFFSET
 for i in range(h[4]):
  vertex,tint,material,offset=s.STATIC.unpack_from(compiled.table,start+i*s.STATIC.size)
  if offset:return vertex,offset
 raise AssertionError('No brand table')


def exercise(preview,wide,extended):
 mode=preview.modes[wide];compiled=mode['compiled'];capture={}
 payload=calendar.apply(space.apply(preview.payload,calendar.REQUESTS+owner.REQUESTS,scaleout=True)[0])[0] if extended else preview.payload
 geometry=projection.native_geometry(payload,mode['scene'],fonts=preview.fonts,texture_span=mode['atlas'],runtime_textures=mode['textures'],capture=capture,widescreen=wide)
 m=capture['machine'];records=[]
 patched=owner.apply(payload)[0];code,data=owner.sites(patched);update=owner.code_for(code['va'],data['va'])[1]['update']
 vertex,offset=brand_record(compiled)
 try:
  scenarios=[('play_now',0,9,14,26,2,'nfl'),('monday_night',2,9,14,26,2,'mnf'),
   ('sunday_night',2,9,13,26,2,'nfl'),('monday_afternoon',2,9,14,26,1,'nfl'),
   ('invalid_month',2,0,14,26,2,'nfl'),('invalid_day',2,9,0,26,2,'nfl')]
  # 2100-09-13 is Monday. Retail's historical-year convention is intentionally
  # retained without the calendar patch; extended mode must execute its detour.
  if extended:scenarios.append(('extended_2100_monday',2,9,13,100,2,'mnf'))
  for policy in s.WATERMARK_MODES:
   encoded=s.compile_folder(widescreen=wide,watermark=policy)
   _,encoded_at=brand_record(encoded)
   mark=encoded.table[encoded_at-s.TABLE_OFFSET:encoded_at-s.TABLE_OFFSET+s.BRAND.size]
   m.uc.mem_write(capture['body']+offset,mark)
   for name,game,month,day,year,night,want in scenarios:
    m.put(0xe576a0,game);m.put(0xe60184,night);m.put(0xe576b4,21);m.put(0xe576bc,16)
    m.uc.mem_write(0xe57c40+(21*17+16)*8,bytes([1,0,1,month,day,year,8,0]))
    m.run(update,(0x3c888889,),limit=500000)
    uv=tuple(x for j in range(4) for x in struct.unpack('<2h',m.uc.mem_read(capture['body']+scene.layout.S1+(vertex+j)*10+4,4)))
    variant='mnf' if policy=='mnf' else want if policy=='auto' else 'nfl'
    expected=s.quantized_uv(compiled.cells['espn_'+variant],compiled.spec['atlas'])
    colour=m.get(capture['body']+scene.layout.S1+vertex*10)
    assert uv==expected,(wide,extended,policy,name,variant)
    assert colour==(0 if policy=='off' else 0xffffffff)
    called=0xd22ac in m.visits
    assert called==bool(policy=='auto' and game==2 and night==2 and month and day),(policy,name,called)
    if called and extended:assert 0x1c18b0 not in m.visits
    records.append(dict(aspect='16:9' if wide else '4:3',calendar=extended,policy=policy,scenario=name,selected=variant if colour else 'off',site_called=called,raw_retail_called=0x1c18b0 in m.visits))
  # Out-of-range grid indices cannot form a pointer into unrelated state.
  m.put(capture['body']+offset,0);m.put(0xe576a0,2);m.put(0xe60184,2)
  for week,slot in ((22,0),(0,17),(0xffffffff,0)):
   m.put(0xe576b4,week);m.put(0xe576bc,slot);m.run(update,(0x3c888889,),limit=500000)
   assert 0xd22ac not in m.visits
 finally:m.close()
 return records

@unittest.skipUnless(NATIVE,'Pinned USA game and Unicorn required')
class NativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.preview=s.NativePreview()
 def test_retail_and_calendar_site_at_both_aspects(self):
  for extended in (False,True):
   for wide in (False,True):self.assertTrue(exercise(self.preview,wide,extended))

if __name__=='__main__':unittest.main()
