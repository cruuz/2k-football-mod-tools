"""Prove both decoded intents on a retail bundle; retain hashes, never retail bytes."""
from pathlib import Path
import json,sys,time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_modern_arrowhead as art,nfl2k5_modern_color as colour
name=sys.argv[1]; started=time.monotonic()
pin=next(p for p in art._pins()['bundles'] if p['name']==name)
cpin=next(p for p in colour._pins()['bundles'] if p['name']==name)
with art._outer_image()(ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030') as archive:
 e=archive.entries[pin['outer']];retail=archive.read(e.virtual_offset,e.size)
assert art.sha(retail)==pin['retail_sha256']==cpin['retail_sha256']
graded,_=colour.modern_bundle(retail,outer_index=pin['outer'])
assert art.sha(graded)==cpin['applied_sha256']
after,edits=art.combined_bundle(retail,graded,outer_index=pin['outer'])
tx,inv,R,H,stw=art._tools()
field=next(c for kind,c in art.bundle_plan(retail) if kind=='field')
size=H.size+field.stored_size
assert after[:H.size]==retail[:H.size]
rec,decoded=art._scene(after,field)
_,graded_decoded=art._scene(graded,field)
painted,_=art.paint_scene(retail,field)
mask=bytearray(len(decoded));textures=[]
for index,(png,row) in sorted(art.scene_targets(rec).items()):
 start=rec['system_bytes']+row['pixel_offset']; palette=rec['system_bytes']+row['palette_offset']
 assert decoded[start:palette]==painted[start:palette],png
 mask[start:palette+1024]=b'\1'*(palette+1024-start)
 textures.append(png)
assert all(a==b or mask[i] for i,(a,b) in enumerate(zip(decoded,graded_decoded)))
assert len(decoded)==len(graded_decoded)
covered=bytearray(len(retail))
for edit in edits:
 a,b=edit['offset'],edit['offset']+edit['size'];covered[a:b]=b'\1'*(b-a)
 if edit['kind']=='stadium':assert edit['applied']==next(s['applied'] for s in pin['sites'] if s['kind']=='stadium')
assert all(a==b or covered[i] for i,(a,b) in enumerate(zip(after,graded)))
# Exercise the actual apply/receipt/read-back path with the proved bundle bytes
# and an in-memory archive. No image or retail bundle is saved to disk.
class Entry: name_id,size,virtual_offset=pin['name_id'],len(retail),0
class Archive:
 entries={pin['outer']:Entry()}
 def __init__(self,source,writable=False):self.source=source;self.writable=writable
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,at,size):return buffers[self.source][at:at+size]
 def write(self,at,data):
  assert self.writable
  blob=buffers[self.source];buffers[self.source]=blob[:at]+data+blob[at+len(data):];return len(data)
buffers={'retail':retail,'target':graded}
receipts={'target':dict(schema=colour.RECEIPT_SCHEMA,settings=colour.default_settings(),settings_sha256=colour.settings_id(),state='applied',bundle_pins={name:cpin})}
with patch.object(art,'_pins',return_value={'bundles':[pin]}),patch.object(colour,'_pins',return_value={'bundles':[cpin]}),patch.object(art,'_outer_image',return_value=Archive),patch.object(colour,'_outer_image',return_value=Archive),patch.object(colour,'read_image_receipt',side_effect=lambda p:receipts.get(p)),patch.object(colour,'_save_image_receipt',side_effect=lambda p,r:receipts.__setitem__(p,r)),patch.object(art,'combined_bundle',return_value=(after,edits)):
 result=art.apply_to_image('target',retail_source='retail')
 assert result['state']=='applied' and buffers['target']==after
 assert colour.image_status('target')=='applied' and art.image_status('target')=='applied'
 snapshot=buffers['target'];art.apply_to_image('target',retail_source='retail');assert buffers['target']==snapshot
 buffers['target']=snapshot[:-1]+bytes([snapshot[-1]^1])
 assert colour.image_status('target')=='foreign' and art.image_status('target')=='foreign'
 try:art.apply_to_image('target',retail_source='retail')
 except ValueError:pass
 else:raise AssertionError('tampered bundle accepted')
result=dict(name=name,sha256=art.sha(after),seconds=time.monotonic()-started,art_textures=textures,decoded_colour_outside_art_exact=True,retail_field_wrapper_exact=True,stadium_applied_pin_exact=True,other_bundle_bytes_exact=True,write_reparse_replay_tamper=True,disc_built=False,edits=edits)
(ROOT/'reports/b71_a6'/('composition-'+name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='edits'}),flush=True)
