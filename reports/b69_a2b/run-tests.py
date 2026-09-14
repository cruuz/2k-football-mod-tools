import concurrent.futures,hashlib,json,os,pathlib,re,subprocess,sys,time
root=pathlib.Path.cwd(); group=sys.argv[1]; workers=int(sys.argv[2])
env={**os.environ,'PYTHONPATH':'.','QT_QPA_PLATFORM':'offscreen','MOD_STUDIO_NO_UPDATE_CHECK':'1','PYTHONHASHSEED':'0','NFL2K5_CAVE_MANIFEST':str(root/'.scratch/a2b/gate-manifest.json')}
logs=root/'reports/b69_a2b'/group;logs.mkdir(parents=True,exist_ok=True)
if len(sys.argv)>3: paths=[pathlib.Path(n) for n in sys.argv[3:]]
elif group=='native':
 paths=sorted(set([*root.glob('tests/mod_editor/test_nfl2k5_my_career*.py'),*root.glob('tests/mod_editor/test_nfl2k5_supersim*.py'),*root.glob('tests/mod_editor/test_nfl2k5_weather*.py'),*root.glob('tests/mod_editor/test_nfl2k5_b69_rules*.py')]+[root/'tests/mod_editor'/n for n in ['test_beta66_supersim_wiring.py','test_nfl2k5_accelerated_clock.py','test_nfl2k5_b661_transition.py','test_nfl2k5_b68_game_composition.py','test_nfl2k5_practice_reserves.py','test_nfl2k5_roster_arena_growth.py']]))
 paths=[p for p in paths if not p.name.endswith('_manifest.py')]
else: raise ValueError(group)
paths=[str(p.relative_to(root)) if p.is_absolute() else str(p) for p in paths]
ledger=[]
def fingerprint():
 from mod_editor.core.nfl2k5_cave_manifest import source_fingerprints
 return hashlib.sha256(json.dumps(source_fingerprints(),sort_keys=True).encode()).hexdigest()
initial=fingerprint()
def run(path):
 start=time.time();log=logs/(pathlib.Path(path).stem+'.log')
 with log.open('w') as out:
  result=subprocess.run(['python3',path],env=env,stdout=out,stderr=subprocess.STDOUT)
 content=log.read_text(errors='replace');lines=content.strip().splitlines()
 status=next((l for l in reversed(lines) if re.match(r'^(OK|FAILED|ERROR|FAIL)(?:\b|$)',l)),lines[-1] if lines else '(no output)')
 ran=next((l for l in reversed(lines) if l.startswith('Ran ')),'')
 return dict(path=path,command='python3 '+path,exit=result.returncode,status=status,ran=ran,final_line=lines[-1] if lines else '',seconds=round(time.time()-start,3),log=str(log.relative_to(root)),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),source_fingerprint=initial)
with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
 for f in concurrent.futures.as_completed([pool.submit(run,p) for p in paths]):
  row=f.result();ledger.append(row);(logs/'tests.json').write_text(json.dumps(sorted(ledger,key=lambda r:r['path']),indent=2)+'\n');print(row['path'],row['exit'],row['ran'],row['status'],flush=True)
print('SOURCE_FINGERPRINT_STABLE',initial==fingerprint(),flush=True)
print('COMPLETED',len(ledger),'FAILED',sum(r['exit']!=0 for r in ledger),flush=True)
