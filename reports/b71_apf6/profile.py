"""Same real export, 21 rounds of play, formation and audible edits; no retail output."""
import collections, functools, hashlib, json, os, statistics, sys, tempfile, time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from mod_editor.apf_studio import playcalling_service as service, book_content
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.session import ApfSession
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor, SITUATIONS
from PyQt5.QtWidgets import QApplication
from tests.mod_editor.test_apf_playcall_research_native import INDEX

label=sys.argv[1]
if label == 'before':
 import subprocess
 from mod_editor.apf_studio import playcalling_editor_qt as editor
 base=Path(__file__).with_name('base.txt').read_text().strip()
 for module in (book_content, service, editor):
  relative=Path(module.__file__).relative_to(Path.cwd()).as_posix()
  source_code=subprocess.check_output(['git','show',base+':'+relative])
  exec(compile(source_code,relative,'exec'),module.__dict__)
 ApfPlayCallingEditor=editor.ApfPlayCallingEditor
phases=collections.defaultdict(lambda: [0,0.])
def timer(owner,name,key):
 original=getattr(owner,name)
 @functools.wraps(original)
 def measured(*args,**kwargs):
  start=time.perf_counter()
  try:return original(*args,**kwargs)
  finally:
   phases[key][0]+=1; phases[key][1]+=time.perf_counter()-start
 setattr(owner,name,measured)
for owner,name,key in [(book_content,'book_catalog','source books'),(book_content,'master_inventory','MASTER inventory'),
 (service.Backend,'load','base state'),(service.PlayCallingService,'events','ledger read'),
 (service.PlayCallingService,'apply','apply and validate'),(service.PlayCallingService,'state','state including replay'),
 (service.PlayCallingService,'context','context and rows'),(service.PlayCallingService,'predict','predictions'),
 (service.PlayCallingService,'situations','situation candidates')]: timer(owner,name,key)
app=QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(prefix='apf6-profile-') as tmp:
 f=ApfStudioFacade(cache_root=Path(tmp)); source=ApfSource(INDEX.parent,INDEX.parent,INDEX,hashlib.sha256(INDEX.read_bytes()).hexdigest(),INDEX.stat().st_size,'e'*64,'Owned APF export')
 f.source=source;f.catalog=NS(assets=(),capabilities=(),by_id={}); f.session=ApfSession(source,f.catalog,cache_root=Path(tmp))
 start=time.perf_counter()
 panel=ApfPlayCallingEditor(f,lambda label,work,done,blocking: done(work(lambda *_:None)))
 panel.donor_picker.setCurrentText('O-ManBlock')
 if 'shell' in label: panel.modifiedChanged.connect(panel.set_context)
 if 'bulk' in label: panel.queue_edits.setChecked(True)
 first=time.perf_counter()-start
 assert panel._context, panel.notice.text()
 forms=[r for r in panel._context['formations'] if r['id']<151 and r['plays']]
 form=forms[0]
 durations=[]; checkpoints=[]
 for i in range(63):
  if 'varied' in label: form=forms[(i//3)%len(forms)]
  common={'book':'O-ManBlock'}
  request=({'kind':'play_rating',**common,'formation':form['id'],'play':form['plays'][0][0],'value':(i//3)%8},
           {'kind':'ratings',**common,'formation':form['id'],'ratings':[(i//3)%8]*3},
           {'kind':'audibles',**common})[i%3]
  start=time.perf_counter()
  if 'shell' in label or 'bulk' in label:
   panel.review_request(request)
  elif label.startswith('confirm'):
   result=f.confirm_playcalling([request]); assert result['staged']==[0],result
  else:
   review=f.playcalling_review(request); assert not review['refused'],review
   f.stage_playcalling(review)
  if 'shell' not in label and 'bulk' not in label: panel.refresh()
  assert len(panel._pending if 'bulk' in label else panel._context['events'])==i+1,panel.notice.text()
  elapsed=time.perf_counter()-start;durations.append(elapsed)
  checkpoints.append({'edit':i+1,'kind':request['kind'],'seconds':elapsed})
  print(i+1,request['kind'],round(elapsed,4),flush=True)
 bulk_seconds = None
 if 'bulk' in label:
  start=time.perf_counter();panel.confirm_review();bulk_seconds=time.perf_counter()-start
  assert not panel._pending,panel.notice.text()
  assert len(panel._context['events'])==63
  assert len(f.session._undo)==1
 panel.close();f.close()
result={'confirm_all_seconds':bulk_seconds,'label':label,'source_index':str(INDEX),'source_index_sha256':source.index_sha256 if hasattr(source,'index_sha256') else hashlib.sha256(INDEX.read_bytes()).hexdigest(),
 'first_load_seconds':first,'edits':checkpoints,'total_seconds':sum(durations),'mean_seconds':statistics.mean(durations),'median_seconds':statistics.median(durations),'max_seconds':max(durations),
 'phases_inclusive':dict(phases),'platform':sys.version,'method':('63 mixed edits: 21 play ratings, 21 formation ratings, 21 balanced audibles; same O-ManBlock export; ' + ('queue all edits then one Confirm all' if 'bulk' in label else 'UI Confirm plus synchronous shell CPU-page reset and panel refresh' if 'shell' in label else 'Confirm plus complete offscreen page refresh' if label.startswith('confirm') else 'review + stage + complete offscreen page refresh') + '; ' + ('cycling formations' if 'varied' in label else 'one formation') + '; phase times overlap.')}
Path(__file__).with_name(label+'.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
