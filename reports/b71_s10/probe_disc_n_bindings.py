"""Bounded native execution of disc n's actual XBE, scene and textures, read-only."""
from pathlib import Path
import sys,json,hashlib,struct,subprocess
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite,nfl2k5_scorebug_ingame as scene,nfl2k5_scorebug_resources as art,platform_compat as io
import nfl2k5_scorebug_projection as p
iso=Path('/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-16n (sprite scorebug pass 2 + everything).xiso.iso')
with iso.open('rb') as f:
 entries,_=scene.layout.xc.parse_xdvdfs(f.fileno(),iso.stat().st_size)
 x=entries['default.xbe'];payload=io.pread(f.fileno(),x.size,x.byte_offset)
 pack=entries['vc_53450030/0'];append=io.pread(f.fileno(),323808,pack.byte_offset+art.HUD_START+art.HUD_SIZE)
 chunks=[append[c.offset:c.end_offset] for c in scene.tx.parse_chunks(append)]
 decoded=scene.decode(chunks[-1])[1]
preview=sprite.NativePreview()
# The supplied XBE already has its own owner installed. Do not reapply S10.
p._runtime_payload=lambda supplied,_identity:supplied
from mod_editor.core import nfl2k5_scorebug_runtime as owner,nfl2k5_scorebug_sprite_code as engine
prior={};exec(subprocess.check_output(['git','show','a3f18036:mod_editor/core/nfl2k5_scorebug_sprite_code.py'],cwd=ROOT),prior)
for key in ('CODE','LABELS','RELOCATIONS'):setattr(engine,key,prior[key])
code,data=owner.sites(payload);expected,labels=owner.code_for(code['va'],data['va'])
actual=payload[code['raw']:code['raw']+owner.CODE_SIZE]
assert actual==expected,('disc owner differs from the pinned S9 engine',hashlib.sha256(actual).hexdigest())
# Audit a copy with only the two already-verified owner calls normalized. The
# executed payload keeps the disc's owner and hooks byte-for-byte.
validate_static=p.validate_native_code
def validate_installed(supplied):
 audit=bytearray(supplied)
 for name,(va,original) in owner.HOOKS.items():
  off=scene.layout.sbpos.va_to_off(supplied,va)
  assert supplied[off:off+5]==owner.hook_bytes(name,labels)
  audit[off:off+5]=original
 return validate_static(bytes(audit))
p.validate_native_code=validate_installed
assert p.wide.apply(payload)[0]==payload,'disc widescreen must already be applied'
assert scene.apply_xbe(payload)[0]==payload,'disc static HUD bytes must already be applied'
c={};g=p.native_geometry(payload,decoded,fonts=preview.fonts,texture_span=chunks[-2],runtime_textures=chunks[:-1],capture=c,widescreen=True,visibility_state='kickoff',visible_elements=(),game_seconds=300)
m=c['machine'];rows=[]
try:
 for state,latch in [('kickoff',None),('after_play',1),('pre_snap',0),('flag',None),('pre_snap',None)]:
  saved=m.get(0xba2f14);p.configure_visibility(m,state);m.put(0xba2f14,saved)
  m.put(0xe602b4,2 if state=='kickoff' else 4)
  if latch is not None:m.run(0xfc330 if latch else 0xfc340)
  for _ in range(45):m.run(0xfce70,(0x3c888889,),limit=500000)
  row=dict(state=state,requests=[m.get(0xa95a00+i*112) for i in range(6)],bindings=[m.get(0xa95a20+i*112) for i in range(6)],slides=[m.floats(0xa95a04+i*112,1)[0] for i in range(6)])
  row['down_colors']=[hex(m.get(c['body']+0x2d20+(136+i*4)*10)) for i in range(8)]
  assert row['bindings']==[1]*6
  if state=='pre_snap':assert row['requests']==[1,1,0,0,0,0] and row['down_colors'].count('0xffffffff')==5
  rows.append(row)
finally:m.close()
result=dict(actual_disc_read_only=True,disc_owner_matches_s9=True,static_and_wide_apply_are_byte_identical=True,xbe_sha256=hashlib.sha256(payload).hexdigest(),scene_sha256=hashlib.sha256(decoded).hexdigest(),states=rows,limitations=['Synthetic world queries and native latch calls; not captured gameplay memory','GPU not executed; no emulator opened'])
Path(__file__).with_name('disc_n_native_bindings.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
