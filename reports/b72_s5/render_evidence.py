"""Generate model sheets and baseline calibration evidence, never game captures."""
from pathlib import Path
import sys,json,tempfile,subprocess
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from tools.scorebug_sprite import render,gpu
from tools.scorebug_sprite.jev import descriptors
from PIL import Image
OUT=ROOT/'reports/b72_s5'
p=sprite.NativePreview()
for aspect in ('4:3','16:9'):
 render.contact_sheet(p,OUT/('all_teams_'+aspect.replace(':','')+'.png'),aspect)
 print('sheet',aspect,flush=True)
# Compare the pre-change template with the supplied failing captures. The native
# owner still handles revision 1, so the baseline can run under the same model.
with tempfile.TemporaryDirectory() as folder:
 folder=Path(folder)
 for name in ('layout.json','template.png'):
  (folder/name).write_bytes(subprocess.check_output(['git','show','ec5d68d4:data/nfl2k5_scorebug_sprite/'+name],cwd=ROOT))
 p=sprite.NativePreview(folder=folder)
 rows=[]
 captures=Path('/home/noah/Desktop/2K5-8 Editors/beta72_evidence/scorebug_ingame_0919')
 for state,filename,target in [('raiders_ball','ksnip_20260919-112349.png',[19,27,67]),('field_goal_setup','ksnip_20260919-112501.png',[19,25,90]),('lions_ball','ksnip_20260919-112603.png',[19,22,74])]:
  s=render.state_for(state,'DET','LV')
  image,r=render.render(p,s,'16:9',OUT/(state+'_baseline_model.png'))
  measured=descriptors.describe(captures/filename)['fields']['down']['luma']
  predicted=r['descriptor']['fields']['down']['luma']
  rows.append(dict(state=state,screenshot=filename,supplied_luma=target,screenshot_luma=measured,model_luma=predicted,
   absolute_error=[round(abs(a-b),2) for a,b in zip(target,predicted)],passed=all(abs(a-b)<=15 for a,b in zip(target,predicted)),
   score_core_luma={k:r['descriptor']['fields'][k]['core_luma'] for k in ('away_score','home_score')},runtime_witnessed=False))
  print(rows[-1],flush=True)
 for wide in (False,True):
  g,c=p.capture(render.state_for('raiders_ball'),wide)
  try:(OUT/f'baseline_gpu_{wide}.json').write_text(json.dumps(gpu.capture_state(c),indent=2)+'\n')
  finally:c['machine'].close()
 (OUT/'calibration.json').write_text(json.dumps(rows,indent=2)+'\n')
