"""Standalone acceptance suites, one interpreter per file, with captured output."""
from pathlib import Path
import json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'logs'
files=[
 'test_beta61_allocator_integration.py','test_nfl2k5_gameplay_levers.py','test_nfl2k5_my_career_m3_budget.py',
 'test_nfl2k5_roster_arena_image.py','test_nfl2k5_roster_storage.py',
 'test_nfl2k5_scorebug_sprite.py','test_nfl2k5_scorebug_sd.py','test_nfl2k5_scorebug_watermark.py',
 'test_scorebug_studio_panel_qt.py','test_scorebug_sprite_preview_qt.py',
 'test_shipped_tools_posix_only.py','test_shipped_tools_are_self_sufficient.py',
 'test_xbe_patch_memory_writes.py','test_xbe_patch_cave_references.py',
 'test_nfl2k5_build_settings.py','test_build_panel_qt.py','test_gameplay_project_ui.py']
files+=sorted(p.name for p in (ROOT/'tests/mod_editor').glob('test_*scorebug*.py') if p.name not in files)
files += [p.name for p in (ROOT/'tests/mod_editor').glob('test_*cave*pair*.py') if p.name not in files]
receipt=OUT/'suites.json'
records=json.loads(receipt.read_text()) if '--resume' in sys.argv and receipt.exists() else []
env=dict(os.environ,PYTHONPATH=str(ROOT),QT_QPA_PLATFORM='offscreen')
for name in files:
 path=ROOT/'tests/mod_editor'/name
 if not path.is_file():continue
 previous=next((r for r in records if r['file']==str(path.relative_to(ROOT))),None)
 if previous and previous['exit_code']==0:continue
 command=[sys.executable,str(path)]
 if name=='test_nfl2k5_scorebug_template_release.py':
  command=[sys.executable,str(ROOT/'reports/b72_s1/prove_release_pin.py')]
 start=time.monotonic()
 with (OUT/(path.stem+'.log')).open('w') as log:
  result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 row=dict(file=str(path.relative_to(ROOT)),exit_code=result.returncode,seconds=round(time.monotonic()-start,2))
 if name=='test_nfl2k5_scorebug_template_release.py':
  row['command']=['python3','reports/b72_s1/prove_release_pin.py']
  row['scope']='Complete release-art suite with pending protected catalog pin substituted in memory.'
 if previous is None:records.append(row)
 else:records[records.index(previous)]=row
 (OUT/'suites.json').write_text(json.dumps(records,indent=2)+'\n',newline='\n')
 print(row,flush=True)
raise SystemExit(int(any(r['exit_code'] for r in records)))
