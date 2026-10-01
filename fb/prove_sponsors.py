"""Compare E's selected u4 stadium painter with residual sponsors, decoded in RAM."""
import sys,json,resource
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_stadium_shared_art as shared
B=ROOT.parent;ART=B.parent/'main/freeze/candC/root_final_v2';art=mv.load_art(ART);checks=[];pics=[]
with mv._outer_image()(ROOT/'extracted/ESPN NFL 2K5 (USA)',writable=False) as archive:
 for prefix in sorted({r['venue'] for r in json.loads((shared.DATA/'design.json').read_text())['textures']}):
  retail={}
  for pin in mv.venues()[prefix]['bundles']:
   e=mv._entry(archive,pin);b=archive.read(e.virtual_offset,e.size);assert mv.sha(b)==pin['retail_sha256'];retail[pin['name']]=b
  name=prefix+'dd.iff';raw=retail[name];rec,decoded=mv.decode_scenes(raw)['stadium'];venue=art['venues'].get(prefix)
  with patch.object(shared,'items',return_value=()):
   baseline_plan=mv.plan_venue(prefix,venue,retail,art['league'])
  before,_=mv.paint_scene(decoded,rec,prefix,'dd',baseline_plan,baseline_plan['base'])
  plan=mv.plan_venue(prefix,venue,retail,art['league']);after,detail=mv.paint_scene(decoded,rec,prefix,'dd',plan,plan['base'])
  targets={i['key'] for i in shared.items(prefix)};mask=np.zeros(len(before),bool);changes=[]
  for key in targets:
   index=mv.find_stadium_texture(rec,key);row=mv.p8_rows(rec)[index]
   lo=int(rec['system_bytes'])+row['pixel_offset'];hi=int(rec['system_bytes'])+row['palette_offset']+1024
   mask[lo:hi]=True
   assert before[lo:hi]!=after[lo:hi],(prefix,key,'already replaced; no new bytes')
   a=mv.read_texture(before,rec,row);b=mv.read_texture(after,rec,row)
   changes.append(dict(key=key,size=[row['width'],row['height']],format=row['format_name'],before=mv.sha(before[lo:hi]),after=mv.sha(after[lo:hi])))
   if prefix in ['s05','s06']:
    pics.append((prefix,key,Image.fromarray(a),Image.fromarray(b)))
  assert np.array_equal(np.frombuffer(before,dtype=np.uint8)[~mask],np.frombuffer(after,dtype=np.uint8)[~mask]),prefix
  check=dict(venue=prefix,changed=changes,all_other_decoded_bytes_unchanged=int((~mask).sum()),source_bundles_verified=9)
  # Two complete refits cover a home atlas layered over u4 and an event venue.
  if prefix in ['s05','s31']:
   baseline_bundle,_=mv.modern_bundle(raw,name,baseline_plan,baseline_plan['base'])
   final_bundle,_=mv.modern_bundle(raw,name,plan,plan['base'])
   ch=mv.bundle_scenes(raw)['stadium'];end=ch.offset+32+ch.stored_size
   assert baseline_bundle[:ch.offset]==final_bundle[:ch.offset] and baseline_bundle[end:]==final_bundle[end:]
   _,back=mv.decode_scenes(final_bundle)['stadium'];assert back==after
   check['compressed_refit_readback']=True;check['other_scene_bytes_unchanged']=True
  checks.append(check);print('PROVED SPONSORS',prefix,len(changes),flush=True)
  (B/'evidence/sponsor_proof.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',checks=checks),indent=2)+'\n')
page=Image.new('RGB',(2150,sum(max(a.height,b.height)*4+50 for _,_,a,b in pics)),'#bbb');draw=ImageDraw.Draw(page);y=0
for prefix,key,a,b in pics:
 draw.text((5,y+3),f'PROVED OFFLINE {prefix} {key} E/u4 before (left), residual-only after (right)',fill='black')
 for x,im in [(5,a),(1080,b)]:
  im=im.resize((im.width*4,im.height*4),Image.Resampling.NEAREST);page.paste(im,(x,y+28),im)
 y+=max(a.height,b.height)*4+50
page.save(B/'review/home_sponsors_E_before_after.png')
(B/'evidence/sponsor_proof.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',checks=checks,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),indent=2)+'\n')
