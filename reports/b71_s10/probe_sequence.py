from pathlib import Path
import sys,struct,json
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s
import nfl2k5_scorebug_projection as p
# Reconstruct the S9 owner/compiler in this process, never on disk. The base
# object is a bundle prerequisite, so this remains reproducible after delivery.
import subprocess,types,hashlib
from mod_editor.core import nfl2k5_scorebug_runtime as owner,nfl2k5_scorebug_sprite_code as engine
BASE='a3f18036230e386c63b26ee7ec95606753d7eea8'
def old(path):return subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
prior={};exec(old('mod_editor/core/nfl2k5_scorebug_sprite_code.py'),prior)
for key in ('CODE','LABELS','RELOCATIONS'):setattr(engine,key,prior[key])
name='mod_editor.core._s10_baseline_compiler';compiler=types.ModuleType(name);compiler.__file__=str(ROOT/'mod_editor/core/nfl2k5_scorebug_sprite.py');sys.modules[name]=compiler
exec(compile(old('mod_editor/core/nfl2k5_scorebug_sprite.py'),compiler.__file__,'exec'),compiler.__dict__)
s.compile_folder=compiler.compile_folder
assert hashlib.sha256(owner.code_for(0,0)[0]).hexdigest()=='3ac2cc0192032ad2b3b295e97ce0ad7a7c00a89807b2b95eb50ba71c6e8025f4'
preview=s.NativePreview();rows=[]
assert hashlib.sha256(preview.modes[False]['scene']).hexdigest()=='065464a54b94b8e18c359ef3897980a6c722304b9593a9fe96ffb4ed7c9388a6'
print('Pinned S9 owner and 4:3 scene reproduced; no product files modified.',flush=True)
for wide in (False,True):
 mode=preview.modes[wide];c={}
 g=p.native_geometry(preview.payload,mode['scene'],fonts=preview.fonts,texture_span=mode['atlas'],runtime_textures=mode['textures'],capture=c,widescreen=wide,visibility_state='kickoff',identity=dict(home='KC',away='DAL'))
 m=c['machine']
 try:
  for state,latch in [('kickoff',None),('after_play',1),('pre_snap',None),('pre_snap',0),('flag',None),('pre_snap',None)]:
   old=m.get(0xba2f14);p.configure_visibility(m,state)
   m.put(0xba2f14,old)
   if latch is not None:m.run(0xfc330 if latch else 0xfc340)
   m.put(0xe602b4,2 if state=='kickoff' else 4)
   for frame in range(45):
    m.run(0xfce70,(0x3c888889,),limit=500000)
    if frame in (0,1,2,30,44):
     qs=[m.get(0xa95a00+i*112) for i in range(6)];sl=[m.floats(0xa95a04+i*112,1)[0] for i in range(6)]
     colors=[hex(m.get(c['body']+0x2d20+q['vertex']*10)) for q in mode['compiled'].quads if q['name'].startswith('down:')]
     row=dict(wide=wide,state=state,latch=m.get(0xba2f14),frame=frame,requests=qs,slides=sl,colors=colors)
     print(json.dumps(row),flush=True);rows.append(row)
 finally:m.close()
Path(__file__).with_name('baseline_sequence.json').write_text(json.dumps(rows,indent=2)+'\n')
