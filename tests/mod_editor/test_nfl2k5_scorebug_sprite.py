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
  c=sprite.compile_folder();self.assertEqual(c.atlas.size,(256,512));self.assertEqual(len(c.quads),47)
  self.assertLess(sprite.probe_sizes()[1],400*1024)
  scores=c.spec['glyph_sets']['score']['glyphs']
  for digit in '0123456789':self.assertEqual(scores[digit]['size'][1],53)
  # The live face is proportional: a narrow 1 and broad rounded 0. The old
  # generic 40-column fit erased exactly this distinction.
  self.assertAlmostEqual(scores['0']['size'][0]/53,49/54,delta=.01)
  self.assertAlmostEqual(scores['1']['size'][0]/53,25/54,delta=.01)
  self.assertLess(scores['7']['size'][0],scores['0']['size'][0])
  self.assertGreater(len(set(c.atlas.getchannel('A').getdata())),64)
  self.assertFalse(list(sprite.DEFAULT_FOLDER.glob('*.ttf')))
  self.assertEqual(c.spec['reference_boxes']['bar'],[437,942,1478,1052])
  self.assertEqual(sprite.compile_folder().table,c.table)
 def test_alpha_aware_palette_preserves_coverage_and_bleeds_straight_rgb(self):
  import numpy as np
  from PIL import Image
  from mod_editor.core import nfl2k5_scorebug_assets as assets
  im=Image.new('RGBA',(64,64));im.paste((225,100,30,255),(16,16,48,48))
  resized=assets.resample_logo(im,(32,32));a=np.asarray(resized)
  palette,indices=assets.quantize_alpha_aware(resized,128)
  decoded=np.asarray(palette,dtype=np.uint8)[np.frombuffer(indices,dtype=np.uint8)].reshape(a.shape)
  self.assertTrue((decoded[:,:,3][a[:,:,3]==0]==0).all())
  self.assertTrue((decoded[:,:,3][a[:,:,3]==255]==255).all())
  self.assertLessEqual(abs(a[16,6,:3].astype(int)-[225,100,30]).max(),1)
  self.assertEqual(a[16,6,3],0)
  # Analytic source-over at a half-covered straight-RGBA edge must retain hue.
  self.assertGreater(decoded[16,7,0],200)
  self.assertGreater(len(np.unique(a[:,:,3])),2)
  solid=a[:,:,3]>=128;pad=np.pad(solid,1,mode='edge')
  adjacent=[pad[y:y+32,x:x+32] for y in range(3) for x in range(3)]
  boundary=np.logical_or.reduce(adjacent)&~np.logical_and.reduce(adjacent)
  self.assertFalse((((a[:,:,3]>0)&(a[:,:,3]<255))&~boundary).any())
 def test_wing_palette_is_monotonic_and_round_ends_have_coverage(self):
  import numpy as np
  from mod_editor.core import nfl2k5_scorebug_assets as assets
  c=sprite.compile_folder();palette,indices=assets.quantize_alpha_aware(c.atlas)
  a=np.asarray(palette,dtype=np.uint8)[np.frombuffer(indices,dtype=np.uint8)].reshape(c.atlas.height,c.atlas.width,4)
  x,y,r,b=c.cells['wing'];profile=a[(y+b)//2,x:r,3].astype(int)
  self.assertTrue((np.diff(profile)<=0).all())
  self.assertGreater(profile[0],128);self.assertEqual(profile[-1],0)
  for name in ('capsule','red'):
   x,y,r,b=c.cells[name];alpha=a[y:b,x:r,3]
   edge=alpha[:,0 if name=='capsule' else -1]
   self.assertLess(edge[0],16)
   self.assertGreater(edge[len(edge)//2],200)
   self.assertGreater(len(set(edge)),3)
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

class LogoFitTests(unittest.TestCase):
 def test_marks_are_drawn_as_the_broadcast_draws_them(self):
  from mod_editor.core import nfl2k5_scorebug_exact as exact, nfl2k5_scorebug_resources as art
  spec=sprite.load_layout()[0];fit=spec['logo_fit']
  self.assertEqual(set(fit['by_team']),set(art.TEAM_LOGOS))
  for team,expect in (('KC',1.89),('DEN',2.09),('BUF',None)):
   im=exact.mnf_panel(team,'home',fit=art.logo_fit_for(team,fit));x0,y0,x1,y1=im.getchannel('A').getbbox()
   aspect=(x1-x0)/(y1-y0)*(200/107)/(64/64)   # cell aspect back to source pixels: 64 cell px = 200 source columns, 64 rows = 107
   plain=exact.mnf_panel(team,'home');px0,py0,px1,py1=plain.getchannel('A').getbbox()
   self.assertGreater(aspect,(px1-px0)/(py1-py0)*(200/107),team)   # wider-to-tall than the unfitted mark
   if expect is not None:self.assertAlmostEqual(aspect,expect,delta=0.12,msg=team)
   self.assertEqual(im.size,(64,64))
  with self.assertRaises(ValueError):exact.mnf_panel('KC','home',fit={'fill_x':3.0})
 def test_edge_bleed_clips_without_changing_native_texture_contract(self):
  plain=exact.mnf_panel('LV','home',fit={'height':1.0})
  zoomed=exact.mnf_panel('LV','home',fit={'height':1.0,'zoom':1.25,'shift_y':-.1})
  self.assertEqual(plain.size,zoomed.size)
  self.assertNotEqual(plain.tobytes(),zoomed.tobytes())
  self.assertEqual(zoomed.getchannel('A').getbbox()[1],0)
  self.assertEqual(exact.mnf_panel('LV','home').tobytes(),
                   exact.mnf_panel('LV','home',fit={'zoom':1,'shift_x':0,'shift_y':0}).tobytes())
  for fit in ({'zoom':float('nan')},{'zoom':2.01},{'shift_x':.51},{'shift_y':float('inf')}):
   with self.assertRaises(ValueError):exact.mnf_panel('LV','home',fit=fit)
 def test_layout_rejects_a_bad_fit(self):
  import copy,json,tempfile
  spec,image=sprite.load_layout()
  for bad in ({'default':{'fill_x':0.1}},{'by_team':{'XXX':{'fill_x':1.2}}},{'default':{'width':1.2}},
              {'default':{'zoom':float('nan')}},{'default':{'shift_x':.51}}):
   with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);rewritten=copy.deepcopy(spec);rewritten['logo_fit']=bad
    (p/'layout.json').write_text(json.dumps(rewritten));image.save(p/'template.png')
    with self.assertRaises(ValueError):sprite.load_layout(p)


class DisplayModelTests(unittest.TestCase):
 def test_display_scale_gives_broadcast_proportions_on_both_displays(self):
  spec=sprite.load_layout()[0]
  boxes={r['name']:r['box'] for r in spec['static']}
  boxes['bar']=spec['reference_boxes']['bar']
  for wide in (False,True):
   for name in ('bar','capsule','plate','away_logo','home_logo','housing'):
    src=boxes[name];shown=sprite.display_box(sprite.contracted(sprite.hud_box(src,wide),wide),wide)
    want=(src[2]-src[0])/(src[3]-src[1]);have=(shown[2]-shown[0])/(shown[3]-shown[1])
    self.assertAlmostEqual(have/want,1,delta=.005,msg=(name,wide))
    if wide:
     for a,b in zip(shown,src):self.assertAlmostEqual(a,b,delta=.5,msg=name)  # 16:9: one source pixel is one display pixel
   self.assertAlmostEqual(sprite.x_scale(wide),640/sprite.DISPLAY[wide]['size'][0]/sprite.DISPLAY[wide]['contraction'])
 def test_pinned_brand_watermark_stays_drawable_and_compiled_tables_differ_only_by_display(self):
  spec=sprite.load_layout()[0];brand=spec['brand'][0]
  self.assertEqual((brand['name'],brand['cell'],brand['material'],brand['pin']),('watermark','espn_mnf',9,'top-right'))
  self.assertEqual(brand['box'],[1655,35,1869,64]);self.assertAlmostEqual(brand['opacity'],0.714,delta=.02)
  self.assertTrue({'frames','method','estimated_opacity','colour'}<=set(brand['source']))
  for wide in (False,True):
   c=sprite.compile_folder(widescreen=wide);row=next(q for q in c.quads if q['name']=='watermark')
   self.assertTrue(row['brand']);self.assertEqual(row['tint'],'none')
   self.assertEqual(row['box'][2],sprite.drawable_right(wide)-sprite.PIN_MARGIN);self.assertEqual(row['layout_box'],brand['box'])
   hud=sprite.hud_box(row['box'],wide);self.assertLessEqual(hud[2],640);self.assertGreater(hud[0],520)
   self.assertEqual(c.widescreen,wide)
   x0,y0,x1,y1=c.cells['espn_mnf'];packed=c.atlas.crop((x0,y0,x1,y1))
   self.assertLessEqual(packed.getchannel('A').getextrema()[1],round(255*brand['opacity'])+1)  # opacity applied when packed
  narrow,wide=sprite.compile_folder(widescreen=False),sprite.compile_folder(widescreen=True)
  self.assertNotEqual(narrow.table,wide.table);self.assertEqual(len(narrow.table),len(wide.table))
  self.assertEqual(narrow.atlas.tobytes(),wide.atlas.tobytes())
 def test_flag_cell_is_yellow_with_a_dark_label_and_brand_cell_is_full_coverage(self):
  spec,image=sprite.load_layout()
  flag=image.crop(spec['cells']['flag']['box']);r,g,b,a=flag.resize((1,1)).getpixel((0,0))
  self.assertGreater(r,200);self.assertGreater(g,150);self.assertLess(b,40)
  self.assertLess(flag.convert('L').crop((round(flag.width*95/246),round(flag.height*6/36),round(flag.width*150/246),round(flag.height*30/36))).getextrema()[0],60)  # dark label ink inside the plate
  self.assertEqual(next(e for e in spec['events'] if e['name']=='FLAG')['cell'],'flag')
  mark=image.crop(spec['cells']['espn_mnf']['box']);self.assertEqual(mark.size,(71,12))
  self.assertGreater(mark.getchannel('A').getextrema()[1],240)  # the template keeps full coverage; the row carries the opacity
  self.assertEqual(mark.convert('RGB').getextrema(),((255,255),)*3)
 def test_live_clock_is_white_with_dark_ink_and_team_plate_is_separate(self):
  spec,image=sprite.load_layout();rows={r['name']:r for r in spec['static']}
  for name in ('capsule','red'):
   self.assertEqual(rows[name]['tint'],'none')
   cell=image.crop(spec['cells'][rows[name]['cell']]['box'])
   self.assertGreater(min(cell.getpixel((cell.width//2,cell.height//2))[:3]),235)
  self.assertEqual(rows['plate']['tint'],'possessing team')
  for f in spec['fields']:
   if f['name'] in ('quarter','clock','play_clock'):self.assertEqual(f['colour'],'#171717')
   if f['name']=='down':self.assertGreaterEqual(f['size']*448/1080,12)
 def test_flag_literal_is_blanked_at_equal_length(self):
  rows={va:(old,new) for va,old,new,_ in owner.override_edits()}
  old,new=rows[0xE6C464];self.assertEqual(old,'FLAG\0'.encode('utf-16le'));self.assertEqual(new,bytes(10))

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
   for q in self.preview.modes[wide]['compiled'].quads:
    if q['dynamic']:continue
    points=g['positions'][q['vertex']:q['vertex']+4]
    box=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
    want=list(sprite.contracted(sprite.hud_box(q['box'],wide),wide))
    self.assertLess(max(abs(a-b) for a,b in zip(box,want)),.02,q['name'])
   expected={'away_score':1,'home_score':1,'clock':4,'play_clock':1,'quarter':1,'down':5,'home_timeouts':3,'away_timeouts':3}
   for role,count in expected.items():
    rows=[q for q in self.preview.modes[wide]['compiled'].quads if q['name'].startswith(role+':')]
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
   # The FLAG plate carries its own dark label; its retail white text is blanked.
   self.assertEqual(any(row['vertices'] for row in g['draws']),event!='FLAG',event)
 def test_clock_crosses_the_retail_ten_minute_formatter_boundary(self):
  g,c=self.capture();m=c['machine'];code,data=owner.sites(self.patched)
  update=owner.code_for(code['va'],data['va'])[1]['update']
  rows=[q for q in self.preview.compiled.quads if q['name'].startswith('clock:')]
  try:
   for seconds,expected in ((599,4),(599.01,5),(599.5,5),(599.99,5),(600,5),(894,5),(900,5),(3600,5),(599,4)):
    m.float(m.game_clock+16,seconds);m.run(update,(0x3c888889,),limit=500000)
    actual=bytes(m.uc.mem_read(c['body'],len(self.preview.scene)))
    self.assertEqual(sum(bool(struct.unpack_from('<I',actual,scene.layout.S1+q['vertex']*10)[0]) for q in rows),expected,seconds)
    self.assertIn(0xfc100 if seconds<=599 else 0xfc150,m.visits)
  finally:m.close()
 def test_plate_secondary_and_team_material_bindings(self):
  for away,home,possessing in (('DEN','KC','home'),('NO','DEN','away')):
   g,c=self.capture(away=away,home=home,possession=possessing)
   row=next(q for q in self.preview.compiled.quads if q['name']=='plate')
   word=struct.unpack_from('<I',c['live_decoded'],scene.layout.S1+row['vertex']*10)[0]
   team=home if possessing=='home' else away
   tint=self.preview.compiled.spec.get('plate_tints',{}).get(team)
   self.assertEqual(word,0xff000000|int(tint[1:],16) if tint else exact.plate_argb(team))
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
  self.assertEqual(m.get(obj-256+sprite.TABLE_OFFSET+28),47)
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
