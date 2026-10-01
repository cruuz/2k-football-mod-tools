"""Fan composition receipt acceptance and safe optional-art behavior."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_model_fan_art as fans
from mod_editor.core import nfl2k5_modern_venues_2026 as mv

class Receipt(unittest.TestCase):
 def setUp(self):
  self.pin=dict(offset=32,length=64,model_sha256='base',model_portrait_sha256='portrait',classic_sha256='classic')
  self.receipt=dict(schema='nfl2k5_model_fan_art/v1',offset=32,length=64,before_sha256='base',after_sha256='u4')
 def test_recognizes_each_pinned_model_variant(self):
  for parent in ['base','portrait','classic']:
   self.assertTrue(fans.applied('u4',self.pin,dict(self.receipt,before_sha256=parent)))
 def test_tampered_bytes_parent_span_and_schema_refuse(self):
  self.assertFalse(fans.applied('other',self.pin,self.receipt))
  self.assertFalse(fans.applied('u4',self.pin,None))
  for k,v in [('schema','unknown'),('before_sha256','foreign'),('offset',0),('length',1)]:
   self.assertFalse(fans.applied('u4',self.pin,dict(self.receipt,**{k:v})),k)
 def test_unselected_art_keeps_exact_model_output(self):
  data=[('s00dd.iff',b'bytes',{'field':'receipt'})]
  with patch.object(mv,'load_art',side_effect=AssertionError('no art reads')):
   self.assertIs(fans.paint_results(data,{},None,{}),data)
 def test_neutral_event_slot_does_not_take_a_club_banner(self):
  # s40 never takes club art: only its own residual cloth from the shared-art catalog (neutral_plan)
  data=[('s40dd.iff',b'neutral model',{})]
  club={'items':[dict(scene='stadium',key='banner_home_player')],'manifest':'m','digest':'d'}
  with patch.object(mv,'load_art',return_value={'venues':{'s23':club}}),patch.object(fans,'neutral_plan',return_value=None) as neutral,patch.object(mv,'plan_venue',side_effect=AssertionError('no club plan')):
   self.assertEqual(fans.paint_results(data,{},'root',{'bundles':[]}),data)
  neutral.assert_called_once_with('s40',{})
 def test_only_neutral_model_slots_take_a_residual_plan(self):
  from mod_editor.core import nfl2k5_stadium_shared_art as shared
  self.assertEqual(shared.MODEL_NEUTRAL,frozenset({'s40'}))
  self.assertIsNone(fans.neutral_plan('s23',{}))
  self.assertNotIn('s40',shared.special_venues());self.assertNotIn('s40',mv.table()['venues'])
  self.assertEqual([(i['scene'],i['key'],i['rects']) for i in shared.items('s40')],[('stadium','banner_home_player',[[128,64,256,128]])])
  data=[('s23dd.iff',b'home model',{})]
  with patch.object(mv,'load_art',return_value={'venues':{}}),patch.object(fans,'neutral_plan',side_effect=AssertionError('home slots take no residual')):
   self.assertEqual(fans.paint_results(data,{},'root',{'bundles':[]}),data)
 def test_unknown_parent_model_is_rejected_before_any_archive_write(self):
  venue=dict(items=[dict(scene='stadium',key='banner_home_player')],manifest='manifest',digest='digest')
  plan=dict(items=[dict(key='banner_home_player')],base={})
  with patch.object(mv,'load_art',return_value={'venues':{'s00':venue}}),patch.object(mv,'plan_venue',return_value=plan),patch.object(fans,'paint_bundle',return_value=(b'changed',{})):
   with self.assertRaisesRegex(mv.ModernVenuesError,'pinned base model'):
    fans.paint_results([('s00dd.iff',b'foreign',{})],{},'root',{'bundles':[dict(self.pin,name='s00dd.iff',offset=0,length=7)]})


EXTRACTED=ROOT/'extracted'/'ESPN NFL 2K5 (USA)'

@unittest.skipUnless(EXTRACTED.is_dir(),'needs the hydrated retail archive')
class NeutralSlot(unittest.TestCase):
 """SoFi's s40 keeps the retail cloth atlas; the neutral plan paints its ESPN VIDEOGAMES cloth with fb2's ESPN
 item through the same painter, inside the scene's span, in the dry-day and night-snow bundles."""
 def test_the_residual_cloth_paints_inside_the_span(self):
  import numpy as np
  retail={}
  from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
  require_nfl_retail_packs(EXTRACTED)
  with mv._outer_image()(str(EXTRACTED),writable=False) as archive:
   for n in ('s40dd.iff','s40ns.iff'):
    e=next(x for x in archive.entries if x.name_id==mv.name_id(n));retail[n]=archive.read(e.virtual_offset,e.size)
  plan=fans.neutral_plan('s40',retail)
  self.assertEqual([(i['key'],i['source']) for i in plan['items']],[('banner_home_player','shared_art')])
  self.assertEqual(plan['manifest'],'data/nfl2k5_stadium_shared_art/venues/s40/manifest.json')
  base=plan['base'][('stadium',plan['items'][0]['dd']['index'])]
  row=next(r for r in json.loads((ROOT/'data/nfl2k5_stadium_shared_art/design.json').read_text())['textures'] if r['venue']=='s40')
  self.assertEqual(mv.sha(base.tobytes()),row['source_rgba_sha256'])
  for n in retail:
   after,detail=fans.paint_bundle(retail[n],n,plan)
   self.assertEqual(len(after),len(retail[n]))
   self.assertEqual([t['key'] for t in detail['textures']],['banner_home_player'])
   rec,dec=mv.decode_scenes(after)['stadium'];rec0,dec0=mv.decode_scenes(retail[n])['stadium']
   k=mv.find_stadium_texture(rec,'banner_home_player')
   now=mv.read_texture(dec,rec,mv.p8_rows(rec)[k]).astype(int);was=mv.read_texture(dec0,rec0,mv.p8_rows(rec0)[k]).astype(int)
   changed=np.abs(now[64:128,128:256,:3]-was[64:128,128:256,:3]).sum(axis=2)>24
   self.assertGreater(float(changed.mean()),0.5,n)

class ModelStatus(unittest.TestCase):
 def test_each_writer_requires_a_matching_composed_span_receipt(self):
  import importlib
  from types import SimpleNamespace
  for name in ['state_farm','mercedes_benz','highmark','att','lucas_oil','everbank','hard_rock','usbank','sofi','levis','allegiant','lambeau']:
   with self.subTest(model=name):
    mod=importlib.import_module('mod_editor.core.nfl2k5_'+name+'_model')
    payload=b'composed u4 model';pin=dict(size=100,offset=32,length=len(payload),retail_sha256='retail',model_sha256='base',classic_sha256='classic')
    receipt=dict(schema='nfl2k5_model_fan_art/v1',offset=32,length=len(payload),before_sha256='base',after_sha256=mv.sha(payload))
    archive=SimpleNamespace(read=lambda offset,size:payload)
    with patch.object(mod,'_pin',return_value=pin),patch.object(mod,'_venue_pins',return_value={'s00dd.iff':{}}),patch.object(mod,'_entry',return_value=SimpleNamespace(size=100,virtual_offset=0)):
     self.assertEqual(mod.bundle_state(archive,'s00dd.iff'),'foreign')
     self.assertEqual(mod.bundle_state(archive,'s00dd.iff',fan_receipt=receipt),'applied')
     self.assertEqual(mod.bundle_state(archive,'s00dd.iff',fan_receipt=dict(receipt,before_sha256='foreign')),'foreign')

class ExportReceipt(unittest.TestCase):
 def test_compacted_image_uses_retained_venue_sidecar(self):
  import tempfile,shutil
  from mod_editor.core import xdvdfs_compact as compact
  self.assertIn('.venues-2026.json',compact.STUDIO_RECEIPTS)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.iso';output=Path(tmp)/'compact.iso'
   original=dict(schema=mv.RECEIPT_SCHEMA,bundles={'s05dd.iff':{'unchanged':'u4'}},venues={'s05':'owned by u4'})
   mv._save_receipt(source,original)
   pin=dict(schema='nfl2k5_model_fan_art/v1',before_sha256='base',after_sha256='u4',offset=32,length=64)
   fans.preserve_receipts(source,dict(bundles={'s00dd.iff':dict(fan_art=pin)}))
   for suffix in compact.STUDIO_RECEIPTS:
    path=Path(str(source)+suffix)
    if path.exists():shutil.copyfile(path,Path(str(output)+suffix))
   carried=mv.read_receipt(output)
   self.assertEqual(carried['bundles'],original['bundles']);self.assertEqual(carried['venues'],original['venues'])
   self.assertEqual(fans.receipt_rows(output,None)['s00dd.iff']['fan_art'],pin)
   parent=dict(model_sha256='base',offset=32,length=64)
   self.assertTrue(fans.applied('u4',parent,fans.receipt_rows(output,None)['s00dd.iff']['fan_art']))
 def test_standalone_model_does_not_fabricate_venue_ownership(self):
  import tempfile
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'source.iso'
   fans.preserve_receipts(path,dict(bundles={'s00dd.iff':dict(fan_art={'pin':'model'})}))
   self.assertFalse(mv.receipt_path(path).exists())
   self.assertEqual(fans.receipt_rows(path,dict(bundles={'s00dd.iff':dict(fan_art={'pin':'model'})}))['s00dd.iff']['fan_art'],{'pin':'model'})

if __name__=='__main__':unittest.main()
