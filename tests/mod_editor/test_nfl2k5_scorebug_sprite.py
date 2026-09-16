"""Sprite resource loader, native owner, layout, ABI and volume proofs."""
from pathlib import Path
import importlib.util
import json
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_exact as exact
PACK=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
RETAIL=PACK.is_file() and (PACK.parents[1]/'default.xbe').is_file()
NATIVE=RETAIL and importlib.util.find_spec('unicorn') is not None

class ContractTests(unittest.TestCase):
 def test_layout_capacity_full_alpha_and_source_boxes(self):
  c=sprite.compile_folder();self.assertEqual(c.atlas.size,(256,512));self.assertEqual(len(c.quads),45)
  self.assertLess(sprite.probe_sizes()[1],400*1024)
  for digit in '0123456789':self.assertEqual(c.spec['glyph_sets']['score']['glyphs'][digit]['size'],[40,53])
  self.assertEqual(len(set(c.atlas.getchannel('A').getdata())),256)
  self.assertFalse(list(sprite.DEFAULT_FOLDER.glob('*.ttf')))
  self.assertEqual(c.spec['reference_boxes']['bar'],[437,942,1478,1052])
  self.assertEqual(sprite.compile_folder().table,c.table)
 def test_future_layout_changes_are_data_and_invalid_layouts_refuse(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory);spec,image=sprite.load_layout();image.save(p/'template.png')
   spec['fields'][0]['anchor'][0]+=12
   (p/'layout.json').write_text(json.dumps(spec));custom=sprite.compile_folder(p)
   self.assertNotEqual(custom.table,sprite.compile_folder().table)
   spec['fields'][0]['source']='made up getter';(p/'layout.json').write_text(json.dumps(spec))
   with self.assertRaisesRegex(sprite.SpriteError,'data source'):sprite.compile_folder(p)
 def test_production_route_is_sprite_and_presets_stay_off(self):
  import inspect
  from mod_editor.core import mod_build as build
  self.assertEqual(inspect.signature(scene.runtime_apply_in_place).parameters['probe'].default,'sprite')
  for preset in ('softdrink_basic','softdrink_advanced','softdrink_experimental'):
   try:plan=build.apply_preset(build.BuildPlan(source="source",target="target"),preset)
   except ValueError:continue
   self.assertFalse(plan.scorebug_runtime)

@unittest.skipUnless(NATIVE,'Pinned USA game and Unicorn required')
class NativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.preview=sprite.NativePreview();cls.patched=owner.apply(cls.preview.payload)[0]
 def capture(self,**state):
  wide=state.pop('widescreen',False);g,c=self.preview.capture(state,wide);self.addCleanup(c['machine'].close);return g,c
 def test_native_values_both_aspects_and_no_font_quads(self):
  for wide in (False,True):
   g,c=self.capture(widescreen=wide)
   self.assertTrue(all(not row['vertices'] for row in g['draws']))
   for q in self.preview.compiled.quads:
    if q['dynamic']:continue
    points=g['positions'][q['vertex']:q['vertex']+4]
    box=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    want=list(exact.hud_box(q['box']))
    if wide:
     for k in (0,2):want[k]=320+(want[k]-320)*27/32
    self.assertLess(max(abs(a-b) for a,b in zip(box,want)),.02,q['name'])
   expected={'away_score':1,'home_score':1,'clock':4,'play_clock':1,'quarter':2,'down':5,'home_timeouts':3,'away_timeouts':3}
   for role,count in expected.items():
    rows=[q for q in self.preview.compiled.quads if q['name'].startswith(role+':')]
    visible=sum(bool(struct.unpack_from('<I',c['live_decoded'],scene.layout.S1+q['vertex']*10)[0]) for q in rows)
    self.assertEqual(visible,count,role)
 def test_opaque_body_blocks_the_screenshot_under_translucent_wings(self):
  from PIL import Image,ImageChops
  import nfl2k5_scorebug_projection as projection
  for wide in (False,True):
   g,c=self.capture(away='NO',home='DEN',possession='away',widescreen=wide)
   with tempfile.TemporaryDirectory() as directory:
    pictures=[]
    for background in ('black','white'):
     path=Path(directory)/(background+'.png')
     projection.render_native(c['live_decoded'],self.preview.atlas,self.preview.fonts,g,path,
       texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),background))
     pictures.append(Image.open(path).convert('RGB'))
    # Interior pixels must not change with the background, including beneath
    # the translucent wing ramps and around their transparent logo cutouts.
    left,right=(177,463) if wide else (150,490)
    delta=ImageChops.difference(*pictures).crop((left,414,right,446))
    self.assertLessEqual(max(v[1] for v in delta.getextrema()),1)
 def test_updates_values_hide_unused_slots_and_keep_retail_events(self):
  g,c=self.capture();m=c['machine'];code,data=owner.sites(self.patched);update=owner.code_for(code['va'],data['va'])[1]['update']
  rows=self.preview.compiled.quads
  for score,timeouts,clock,play,down,period in ((0,0,7,12,1,1),(28,1,7,3,2,2),(100,2,273,4,3,3),(7,3,273,12,4,5)):
   away_score=100 if score==7 else 7
   m.put(m.home,score);m.put(m.away,away_score);m.put(m.home+4,timeouts);m.put(m.away+4,3-timeouts)
   m.float(m.game_clock+16,clock);m.float(m.clock+16,play);m.put(m.play+4,down);m.put(0xe602c4,period)
   m.run(update,(0x3c888889,),limit=500000)
   actual=bytes(m.uc.mem_read(c['body'],len(self.preview.scene)))
   for role,count in (('home_score',len(str(score))),('away_score',len(str(away_score))),('home_timeouts',timeouts),('away_timeouts',3-timeouts),('play_clock',len(str(play)))):
    self.assertEqual(sum(bool(struct.unpack_from('<I',actual,scene.layout.S1+q['vertex']*10)[0]) for q in rows if q['name'].startswith(role+':')),count,(role,score,timeouts,play))
  for event in ('FLAG','FUMBLE','hang time','ball on'):
   g,c=self.capture(event=event)
   self.assertTrue(any(row['vertices'] for row in g['draws']),event)
 def test_plate_secondary_and_team_material_bindings(self):
  for away,home,possessing in (('DEN','KC','home'),('NO','DEN','away')):
   g,c=self.capture(away=away,home=home,possession=possessing)
   row=next(q for q in self.preview.compiled.quads if q['name']=='plate')
   word=struct.unpack_from('<I',c['live_decoded'],scene.layout.S1+row['vertex']*10)[0]
   self.assertEqual(word,exact.plate_argb(home if possessing=='home' else away))
   names={r['name']:r for r in g['materials']}
   for name,team in (('hscore_buga',home),('zscore_buga',away)):
    span=c['texture_spans'][names[name]['texture']];chunk,body,_=scene.decode(span)
    self.assertEqual(scene.tx.parse_texture(body,chunk).name,'sb'+art.TEAM_LOGOS[team]['asset_code']+'h0')
 def test_native_owner_registers_fpu_and_write_ownership(self):
  g,c=self.capture();m=c['machine'];x=m.x;code,data=owner.sites(self.patched)
  labels=owner.code_for(code['va'],data['va'])[1]
  m.uc.mem_write(0xfc1a0,b'\xc3');m.uc.ctl_remove_cache(0xfc1a0,0xfc1f9)
  names=('EAX','EBX','ECX','EDX','ESI','EDI','EBP')
  for hook,args in (('setup',()),('update',(0x3c888889,))):
   for i,n in enumerate(names):m.uc.reg_write(getattr(x,'UC_X86_REG_'+n),0x13570000+i)
   m.uc.reg_write(x.UC_X86_REG_EFLAGS,0x646);m.uc.reg_write(x.UC_X86_REG_FPCW,0x37f);m.uc.reg_write(x.UC_X86_REG_FPSW,0)
   for i in range(8):m.uc.reg_write(getattr(x,f'UC_X86_REG_FP{i}'),(0x8000000000000000+i,0x3fff));m.uc.reg_write(getattr(x,f'UC_X86_REG_XMM{i}'),(i+1)*0x123456789abcdef0123456789abcdef)
   m.uc.reg_write(x.UC_X86_REG_FPTAG,0)
   regs=[getattr(x,'UC_X86_REG_'+n) for n in names]+[x.UC_X86_REG_EFLAGS,x.UC_X86_REG_FPCW,x.UC_X86_REG_FPSW,x.UC_X86_REG_FPTAG,x.UC_X86_REG_MXCSR]+[getattr(x,f'UC_X86_REG_XMM{i}') for i in range(8)]+[getattr(x,f'UC_X86_REG_FP{i}') for i in range(8)]
   before=[m.uc.reg_read(r) for r in regs];m.run(labels[hook],args,limit=500000)
   self.assertEqual([m.uc.reg_read(r) for r in regs],before)
   self.assertEqual(m.visits.count(0xfc1a0 if hook=='setup' else 0xfc9c0),1)
   self.assertNotIn(0x44b60,m.visits)
   for va,size,_ in m.writes:
    self.assertFalse(code['va']<=va<code['va']+code['size'])
    if c['body']<=va<c['body']+len(self.preview.scene):
     ranges=((0x1c0,0x740),(scene.layout.S0,scene.layout.S0+286*6),(scene.layout.S1,scene.layout.S1+286*10))
     self.assertTrue(any(c['body']+a<=va and va+size<=c['body']+b for a,b in ranges),(hex(va),size))
 def test_foreign_code_and_idempotence(self):
  self.assertEqual(owner.apply(self.patched)[0],self.patched)
  code,data=owner.sites(self.patched)
  for offset in (code['raw'],code['raw']+2000,data['raw']):
   bad=bytearray(self.patched);bad[offset]^=1
   self.assertEqual(owner.status(bytes(bad)),'foreign')
   with self.assertRaises(ValueError):owner.apply(bytes(bad))
 def test_native_appended_scene_replaces_retail_with_no_fonts(self):
  from test_nfl2k5_scorebug_assets import NativeOuterLoad
  with PACK.open('rb') as stream:
   view=art.PackView.from_fd(stream.fileno(),0,PACK.stat().st_size);append,receipt=sprite.appendix(view)
   r=art.RESOURCES['score_bug'];retail=bytes(view[r['pack_offset']:r['pack_offset']+r['span_size']])
  blob=retail+append;c=NativeOuterLoad(self.patched,blob,0,len(blob));m=c.m
  handler=m.alloc(16);m.put(handler,m.get(0xb0957c));m.put(handler+8,int.from_bytes(b'SCNE','little'));m.put(handler+12,0x45a90);m.put(0xb0957c,handler)
  m.uc.mem_write(0x2f010,bytes.fromhex('c20400'))
  result=c.run();obj=c.lookup('SCNE','score_bug')
  self.assertEqual(m.get(obj-256+sprite.MARKER_OFFSET),sprite.MAGIC)
  self.assertEqual(result['fonts'],0);self.assertEqual(result['textures'],34)
  self.assertLess(receipt['appended_bytes'],400*1024)
  self.assertEqual(m.get(obj+0x1c),11)
  self.assertEqual(m.get(obj-256+sprite.TABLE_OFFSET+28),45)
 def test_collection_round_trip_and_foreign_byte_refusal(self):
  with PACK.open('rb') as stream:
   original=art.PackView.from_fd(stream.fileno(),0,PACK.stat().st_size)
   new,receipt=art.compile_runtime_collection(original,probe='sprite')
   self.assertEqual(art.runtime_pack_status(new,probe='sprite'),'applied')
   self.assertIs(art.compile_runtime_collection(new,probe='sprite')[0],new)
   self.assertEqual(new[art.HUD_START:art.HUD_START+art.HUD_SIZE],original[art.HUD_START:art.HUD_START+art.HUD_SIZE])
   end=art.HUD_START+art.HUD_SIZE
   mutated=art.join_views(((new,0,end),(bytes([new[end:end+1][0]^1]),0,1),(new,end+1,len(new)-end-1)))
   self.assertEqual(art.runtime_pack_status(mutated,probe='sprite'),'foreign')

if __name__=='__main__':unittest.main()
