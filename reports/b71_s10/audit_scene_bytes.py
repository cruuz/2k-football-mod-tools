"""Recompile release and candidate in memory; no retail resources are exported."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys,tempfile,types
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite,nfl2k5_scorebug_resources as art,nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_cave_manifest as manifest
from PIL import Image
OUT=Path(__file__).resolve().parent
BASE='a3f18036230e386c63b26ee7ec95606753d7eea8'
def old(path):return subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
def sha(data):return hashlib.sha256(data).hexdigest()
name='mod_editor.core._s10_base_sprite';before=types.ModuleType(name);before.__file__=str(ROOT/'mod_editor/core/nfl2k5_scorebug_sprite.py');sys.modules[name]=before
exec(compile(old('mod_editor/core/nfl2k5_scorebug_sprite.py'),before.__file__,'exec'),before.__dict__)
results={}
with tempfile.TemporaryDirectory(prefix='s10-layout-') as directory:
 folder=Path(directory);(folder/'layout.json').write_bytes(old('data/nfl2k5_scorebug_sprite/layout.json'));(folder/'template.png').symlink_to(sprite.DEFAULT_FOLDER/'template.png')
 before.DEFAULT_FOLDER=folder
 pack=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
 with pack.open('rb') as stream:
  view=art.PackView.from_fd(stream.fileno(),0,pack.stat().st_size)
  for wide in (False,True):
   prior,pr=before.appendix(view,widescreen=wide);current,cr=sprite.appendix(view,widescreen=wide)
   assert len(prior)==len(current)==323808<400000
   assert pr['components'][:-1]==cr['components'][:-1]
   sc=scene.tx.parse_chunks(current)[-1];a=scene.decode(prior[sc.offset:sc.end_offset])[1];b=scene.decode(current[sc.offset:sc.end_offset])[1]
   assert a[0x1c0:0x740]==b[0x1c0:0x740]
   changes=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y];ranges=[]
   for i in changes:
    if ranges and ranges[-1][1]==i:ranges[-1][1]=i+1
    else:ranges.append([i,i+1])
   results[str(wide)]=dict(old_append_sha256=sha(prior),new_append_sha256=sha(current),old_scene_sha256=sha(a),new_scene_sha256=sha(b),appended_bytes=len(current),unchanged_texture_chunks=34,raw_material_records_unchanged=True,scene_changed_byte_count=len(changes),scene_changed_ranges=[[hex(x),hex(y)] for x,y in ranges],material_order=list(sprite.compile_folder(widescreen=wide).material_order))
   if not wide:
    spans=scene.tx.parse_chunks(current);tx=spans[-2];chunk,decoded,_=scene.decode(current[tx.offset:tx.end_offset]);tex=scene.tx.parse_texture(decoded,chunk);im=Image.frombytes('RGBA',(tex.width,tex.height),scene.tx.texture_to_rgba(decoded,chunk,tex));compiled=sprite.compile_folder();coverage={}
    for token,row in compiled.spec['glyph_sets']['label']['glyphs'].items():
     if not row['size'][0]:continue
     pixels=list(im.crop(compiled.cells[row['cell']]).getchannel('A').getdata());coverage[token]=dict(max_alpha=max(pixels),opaque_pixels=sum(v==255 for v in pixels),nonzero_pixels=sum(v>0 for v in pixels));assert max(pixels)==255
    results['decoded_label_alpha']=coverage
fingerprints=manifest.source_fingerprints();changed={}
for path,now in fingerprints.items():
 previous=sha(old(path))
 if now!=previous:changed[path]=dict(before=previous,after=now)
results['manifest_source_fingerprints_changed']=changed
from mod_editor.core import nfl2k5_scorebug_runtime as owner,nfl2k5_scorebug_sprite_code as engine
current_owner=owner.code_for(0,0)[0]
prior_engine={};exec(old('mod_editor/core/nfl2k5_scorebug_sprite_code.py'),prior_engine)
for key in ('CODE','LABELS','RELOCATIONS'):setattr(engine,key,prior_engine[key])
prior_owner=owner.code_for(0,0)[0]
results['owner']=dict(before=sha(prior_owner),after=sha(current_owner),changed_bytes=sum(a!=b for a,b in zip(prior_owner,current_owner)),allocation_bytes=len(current_owner),data_allocation_bytes=owner.DATA_SIZE)
assert prior_owner!=current_owner
if (OUT/'scene_byte_audit.json').exists():
 previous=json.loads((OUT/'scene_byte_audit.json').read_text())
 for wide in ('False','True'):
  assert results[wide]['new_append_sha256']==previous[wide]['new_append_sha256']
 results['candidate_append_unchanged_after_anchor_validation']=True
(OUT/'scene_byte_audit.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
