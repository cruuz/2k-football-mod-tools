"""Measured v3 font cells, native formatting, urgency contrast and geometry."""
from pathlib import Path
import importlib.util,struct,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_exact as exact,nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_ingame as scene
import nfl2k5_scorebug_projection as projection
PACK=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'

class ContractTests(unittest.TestCase):
 def test_measured_boxes_secondary_choices_and_safe_volume(self):
  self.assertEqual(exact.MNF_SOURCE['plate'],(837,947,1083,983))
  self.assertEqual(exact.MNF_SOURCE['strip'],(839,999,1082,1040))
  self.assertEqual(exact.plate_argb('KC'),0xffe31837)
  self.assertEqual(exact.plate_argb('LV'),0xffa5acaf)
  self.assertEqual(art.probe_sizes('mnf')[1],410624)
  self.assertLess(art.probe_sizes('mnf')[1],420000)
  self.assertEqual(owner.PLAY_CLOCK_CELL,0xffd70033)

@unittest.skipUnless(PACK.is_file() and importlib.util.find_spec('unicorn'),'retail pack and Unicorn required')
class NativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from nfl2k5_scorebug_exact import Build
  cls.build=Build(PACK,PACK.parents[1]/'default.xbe');cls.addClassCleanup(cls.build.close)
 def capture(self,private=True,**state):
  b=self.build;span=scene.stage_binding_scene(b.spans['score_bug'],runtime=True)[0]
  tex=scene.encode_atlas(b.spans['score_buga'],exact.atlas_mnf())[0];capture={}
  geometry=projection.native_geometry(b.payload,scene.decode(span)[1],fonts=b.fonts,texture_span=tex,runtime_textures=b.panels,runtime_fonts=b.font_spans if private else (),capture=capture,**state)
  self.addCleanup(capture['machine'].close)
  return geometry,capture
 def test_missing_private_font_keeps_native_clock_formatters(self):
  _,capture=self.capture(private=False);m=capture['machine']
  for record,formatter in ((0xa958fc,0xfc100),(0xa95924,0xfc150),(0xa95a3c,0xfbe30)):
   self.assertEqual(m.get(record),formatter)
 def test_event_slab_samples_charcoal_after_atlas_uv_normalization(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'flag.png'
   g=self.build.render(path,runtime=True,visible_elements=(1,3))
   self.assertTrue(next(r for r in g['materials'] if r['name']=='bscore_buga2')['visible'])
   self.assertEqual(Image.open(path).convert('RGB').getpixel((282,415)),(37,37,37))
 def test_native_score_callback_decimal_range_and_ascii_preservation(self):
  geometry,capture=self.capture();m=capture['machine'];buffer=m.alloc(64)
  for side,pointer in enumerate((m.home,m.away)):
   callback=m.get(owner.SCORE_CALLBACKS[side])
   for score in (0,1,7,10,28,99,100):
    m.put(pointer,score);m.run(callback,ecx=buffer)
    text=m.read_string(buffer)
    base=owner.SCORE_DIGIT_BASE if score<10 else owner.SCORE_COMPACT_BASE
    self.assertEqual(text,''.join(chr(base+int(ch)) for ch in str(score)))
  font=self.build.private_fonts[0];glyphs={g.codepoint:g for g in font.glyphs}
  self.assertTrue(all(cp in glyphs for cp in range(33,127)))
  boxes=[]
  for digit in range(10):
   glyph=glyphs[0x80+digit]
   self.assertAlmostEqual(glyph.right-glyph.left,40/3,places=4)
   self.assertAlmostEqual(glyph.bottom-glyph.top,53*448/1080,places=4)
   x0,y0,x1,y1=[round(v*256) for v in glyph.uv];boxes.append((x0,y0,x1,y1))
   self.assertEqual((x1-x0,y1-y0),(26,48))
  ascii_boxes=[tuple(round(v*256) for v in g.uv) for g in font.glyphs if g.codepoint<128]
  for i,(x,y,u,v) in enumerate(boxes):
   for a,b,c,d in ascii_boxes+boxes[:i]:self.assertFalse(x<c and a<u and y<d and b<v)
  for digit in range(10):
   large,compact=glyphs[0x80+digit],glyphs[0x90+digit]
   self.assertEqual(large.uv,compact.uv)
   self.assertAlmostEqual(compact.bottom-compact.top,53*448/1080,places=4)
 def test_clock_white_digit_red_cell_urgency_and_disabled_boundaries(self):
  _,capture=self.capture();m=capture['machine'];buffer=m.alloc(64)
  # The real material lookup, independently resolved by name.
  g=projection.native_text_draw(capture)
  cell=int(next(row['address'] for row in g['materials'] if row['name']=='score_buga'),16)
  payload=owner.apply(self.build.payload)[0];code,data=owner.sites(payload)
  update=owner.code_for(code['va'],data['va'])[1]['update']
  # The owner calls the displaced native frame update before applying its colours.
  for seconds,expected in ((12,owner.PLAY_CLOCK_CELL),(5,owner.PLAY_CLOCK_CELL),
                           (4,owner.ESPN_RED),(2.5,0xfff00c3e),
                           (0,owner.ESPN_RED),(-1,owner.PLAY_CLOCK_CELL),
                           (float('nan'),owner.PLAY_CLOCK_CELL)):
   m.float(m.clock+16,seconds);m.put(m.clock+24,0);m.put(0xa95a70,1)
   m.run(update,(struct.unpack('<I',struct.pack('<f',1/60))[0],),limit=500000)
   self.assertEqual(m.get(0xa95a48),owner.WHITE)
   self.assertEqual(m.get(cell+0x18),expected,seconds)
  m.float(m.clock+16,4);m.run(m.get(0xa95a3c),ecx=buffer);self.assertEqual(m.read_string(buffer),'Ä')
 def test_painted_mask_tints_come_from_native_logo_lookup(self):
  from tempfile import TemporaryDirectory
  with TemporaryDirectory() as directory:
   for matchup,possession in ((('DEN','KC'),'home'),(('NO','DEN'),'away')):
    g=self.build.render(Path(directory)/'tints.png',runtime=True,matchup=matchup,possession=possession)
    rows={row['name']:int(row['tint'],16) for row in g['materials']}
    self.assertEqual(rows['dscore_buga'],exact.plate_argb(matchup[1 if possession=='home' else 0]))
    for side,material in ((0,'yscore_buga'),(1,'yscore_buga1')):
     self.assertEqual(rows[material],exact.wing_table()[int(art.TEAM_LOGOS[matchup[side]]['asset_code'])])
    self.assertEqual(rows['cscore_buga'],0xffffffff)
 def test_native_geometry_both_aspects_and_all_visible_triangle_winding(self):
  from nfl2k5_scorebug_exact import box_of
  with tempfile.TemporaryDirectory() as directory:
   for wide in (False,True):
    geometry=self.build.render(Path(directory)/f'{wide}.png',runtime=True,widescreen=wide,score_values=(7,7),previous_scores=(7,7))
    self.assertEqual(projection.containment_failures(geometry,geometry['frame'],.02),{})
    self.assertTrue(all(row['positive']==0 for row in geometry['winding'].values()))
    for key,source in (('frame','bar'),('down','plate'),('clock','strip')):
     want=list(exact.hud_box(exact.MNF_SOURCE[source]))
     if wide:
      for i in (0,2):want[i]=320+(want[i]-320)*27/32
     self.assertLess(max(abs(a-b) for a,b in zip(geometry[key],want)),.01)
    for score in (28,100,999):
     geometry=self.build.render(Path(directory)/f'{wide}-{score}.png',runtime=True,widescreen=wide,score_values=(score,score),previous_scores=(score,score))
     plate=geometry['down'];scores=[r for r in geometry['draws'] if r['text'] and 0x80<=ord(r['text'][0])<=0x99]
     self.assertEqual(len(scores),2)
     for row in scores:
      left,top,right,bottom=box_of([v['screen'] for v in row['vertices']])
      self.assertTrue(right<=plate[0] or left>=plate[2],(score,wide,(left,right),plate))

if __name__=='__main__':unittest.main()
