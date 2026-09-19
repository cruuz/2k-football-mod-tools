"""Native visibility, watermark, sampling, and final ESPN residual receipts."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tests/mod_editor')]
from mod_editor.core import nfl2k5_scorebug_sprite as s
from test_nfl2k5_scorebug_watermark import exercise
from test_nfl2k5_scorebug_sd import sampling_receipt
p=s.NativePreview();records=[]
inputs=('data/nfl2k5_scorebug_sprite/template.png','data/nfl2k5_scorebug_sprite/layout.json',
 'tools/scorebug_sprite/runtime.c','mod_editor/core/nfl2k5_scorebug_sprite_code.py',
 'mod_editor/core/nfl2k5_scorebug_sprite.py','tools/nfl2k5_scorebug_projection.py')
(OUT/'proof_inputs.json').write_text(json.dumps({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in inputs},indent=2)+'\n',newline='\n')
for extended in (False,True):
 for wide in (False,True):records+=exercise(p,wide,extended)
(OUT/'watermark_native.json').write_text(json.dumps(dict(cases=records,count=len(records),runtime_witnessed=False,
 boundaries=['Synthetic schedule records in the current grid; native weekday site and installed calendar detour execute.',
 'Only the existing brand quad UVs and colours change; no new material or quad.']),indent=2)+'\n',newline='\n')
(OUT/'sampling.json').write_text(json.dumps(sampling_receipt(),indent=2)+'\n',newline='\n')
for name in ('prove_states.py','prove_sequence.py'):
 with (OUT/(name[:-3]+'.log')).open('w') as log:subprocess.run([sys.executable,str(OUT/name)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
with (OUT/'match_final.log').open('w') as log:
 subprocess.run([sys.executable,str(ROOT/'tools/scorebug_sprite/match_espn.py'),'--frames',str(Path.home()/'Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
print('Visibility, watermark, sampling and match proofs complete.',flush=True)
