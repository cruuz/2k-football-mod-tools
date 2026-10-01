"""PROVED OFFLINE: PHI/CHI evidence corrections survive compilation and native owner read-back."""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_teams as teams
DATA=ROOT/'data/nfl2k5_scorebug_sprite'
EXPECTED={'PHI':('#1FB0C4','#26636B','21'), 'CHI':('#FB6930','#AC3100','05')}
PINS={
 'data/nfl2k5_scorebug_mnf/logos/phi.png':'02afc83aea87b4cf2b8e4de119e0000005adf0f4d86f1004e4603e1a734fa948',
 'data/nfl2k5_scorebug_mnf/logos/chi.png':'de13ce77f15a3aa2886065817db8281bf94f09cd2fb422f65fae4470f6905aca',
 'data/nfl2k5_scorebug_sprite/team_colors_official_2026.json':'e10e27efc9168506cad0c5b0a2558fa3959e8a0e353ca06894e2baa11dbbcee4'}

class DataTests(unittest.TestCase):
 def test_official_identity_and_mark_pixels_are_unchanged(self):
  for p,digest in PINS.items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),digest,p)
 def test_measured_shades_keep_the_existing_bound_and_white_plate_contrast(self):
  palette=teams.load();display=teams.load_display()
  self.assertEqual(display['transfer']['measured_bound'],.0485)
  for name,(wing,plate,code) in EXPECTED.items():
   t=palette[name];self.assertEqual((t['wing'],t['wash'],t['plate'],t['asset_code']),(wing,wing,plate,code))
   self.assertEqual(t['display']['source'],'measured')
   self.assertGreaterEqual(teams.contrast_white(plate),4.5)
   self.assertEqual(teams.display_shade(name,t,display),wing)
  self.assertEqual(palette['CHI']['display']['parent'],'#E64100')
 def test_compiled_native_table_contains_both_correct_identities(self):
  c=sprite.compile_folder();magic,count,offset=teams.FOOTER.unpack_from(c.table,len(c.table)-teams.FOOTER.size)
  self.assertEqual((magic,count),(teams.MAGIC,52))
  rows=[teams.ENTRY.unpack_from(c.table,offset-sprite.TABLE_OFFSET+i*teams.ENTRY.size) for i in range(count)]
  for name,(wing,plate,code) in EXPECTED.items():
   identity=struct.unpack('<I',code.encode('utf-16le'))[0]
   self.assertIn((identity,0,int('FF'+wing[1:],16),int('FF'+plate[1:],16),int('FF'+plate[1:],16)),rows)
 def test_label_scaling_keeps_wordmark_size_and_position(self):
  s=json.loads((DATA/'layout.json').read_text());f=next(f for f in s['fields'] if f['name']=='down')
  g=s['glyph_sets']['label'];factor=f['size']/g['cap_height'];e=g['glyphs']['ESPN']
  self.assertEqual((f['size'],f['anchor']), (24,[959,955]))
  self.assertEqual([v*factor for v in e['size']],[100,24])
  self.assertEqual(f['anchor'][1]-e['raise']*factor,956)
  self.assertEqual(sprite.probe_sizes(),(34,327904,327680))

NATIVE=(ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe').is_file() and importlib.util.find_spec('unicorn') is not None
@unittest.skipUnless(NATIVE,'pinned retail game and Unicorn needed')
class NativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.preview=sprite.NativePreview()
 def colour(self,c,q):return struct.unpack_from('<I',c['live_decoded'],0x2d20+q['vertex']*10)[0]
 def inspect(self,wide,**state):
  g,c=self.preview.capture(dict(away='PHI',home='CHI',broadcast='monday_night',**state),wide)
  quads=self.preview.modes[wide]['compiled'].quads
  colours={q['name']:self.colour(c,q) for q in quads if not q['dynamic']}
  uv_to_token={sprite.quantized_uv(self.preview.modes[wide]['compiled'].cells[v['cell']],self.preview.modes[wide]['compiled'].spec['atlas']):k for k,v in self.preview.modes[wide]['compiled'].spec['glyph_sets']['label']['glyphs'].items()}
  # Aliases GOAL/Goal and uppercase/lowercase ordinals deliberately share cells.
  tokens=[]
  for q in quads:
   if q['name'].startswith('down:') and self.colour(c,q):
    uv=tuple(struct.unpack_from('<h',c['live_decoded'],0x2d20+(q['vertex']+j)*10+4+k*2)[0] for j in range(4) for k in range(2))
    tokens.append(uv_to_token[uv])
  return g,c,colours,tokens
 def test_both_possession_plates_and_wings_after_native_update(self):
  for wide in (False,True):
   for side,name in [('away','PHI'),('home','CHI')]:
    g,c,colours,tokens=self.inspect(wide,possession=side,down=1,distance=10,play_clock=6)
    try:
     self.assertEqual(colours['away_wing'],0xFF1FB0C4);self.assertEqual(colours['home_wing'],0xFFFB6930)
     self.assertEqual(colours['plate'],int('FF'+EXPECTED[name][1][1:],16))
     from mod_editor.core import nfl2k5_scorebug_ingame as scene
     materials={m['name']:m for m in g['materials']}
     for material,expected in [('hscore_buga','sb05h0'),('zscore_buga','sb21h0')]:
      raw=c['texture_spans'][materials[material]['texture']]
      body,_=scene.tx.decode_chunk(raw,scene.tx.parse_chunks(raw)[0])
      self.assertEqual(body[32:46].decode('utf-16le').rstrip('\0'),expected)
     self.assertEqual(''.join(tokens).lower(),'1st&10')
    finally:c['machine'].close()
 def test_new_matchup_states_use_complete_tokens_in_both_aspects(self):
  cases=[(dict(down=2,previous_down=1),'2nddown'),(dict(down=4,distance=1),'4th&1'),
         (dict(down=3,distance=16),'3rd&16'),(dict(down=2,goal_to_go=True),'2nd&goal'),
         (dict(phase=2),'espn'),(dict(event='hang time'),'espn'),(dict(event='ball on'),'espn'),
         (dict(event='FLAG'),'')]
  for wide in (False,True):
   for state,text in cases:
    g,c,colours,tokens=self.inspect(wide,**state)
    try:self.assertEqual(''.join(tokens).lower(),text,(wide,state))
    finally:c['machine'].close()
 def test_red_cell_boundary_is_shared_by_both_teams(self):
  for side in ('away','home'):
   for pc in (6,5,2,0):
    g,c,colours,tokens=self.inspect(True,possession=side,play_clock=pc)
    try:self.assertEqual(colours['red'],0xFFDD0038 if pc<=5 else 0xFFFFFFFF,(side,pc))
    finally:c['machine'].close()
 def test_logo_texture_descriptor_tints_read_back_from_native_chunks(self):
  # Name-padding tints and the scene table must agree even for consumers that use the fallback descriptor.
  from mod_editor.core import nfl2k5_scorebug_ingame as scene
  for wide in (False,True):
   chunks=self.preview.modes[wide]['textures']
   for name,(wing,plate,code) in EXPECTED.items():
    matches=[]
    for raw in chunks:
     ch=scene.tx.parse_chunks(raw)[0]
     if ch.kind!='TXTR':continue
     body,_=scene.tx.decode_chunk(raw,ch)
     if body[32:46].decode('utf-16le').rstrip('\0')=='sb'+code+'h0':matches.append(struct.unpack_from('<II',body,48))
    self.assertEqual(matches,[(int('FF'+plate[1:],16),int('FF'+wing[1:],16))])

if __name__=='__main__':unittest.main()
