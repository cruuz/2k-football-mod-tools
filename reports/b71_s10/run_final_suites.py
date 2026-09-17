from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from run_logged import run,ROOT
files=sorted(p for p in (ROOT/'tests/mod_editor').glob('test_*') if p.suffix=='.py' and ('scorebug' in p.name or 'scorebar' in p.name))
files += [ROOT/'tests/nfl2k5_scorebug_layout_test.py',ROOT/'tests/nfl2k5_scorebug_mod_project_test.py']
files += [ROOT/'tests/mod_editor'/('test_'+name+'.py') for name in ('provider_integrity','product_catalog','phase1_packaging','mod_build','build_panel_qt','nfl2k5_allocator_scaleout','nfl2k5_xbe_space')]
with ThreadPoolExecutor(max_workers=3) as pool:
 futures=[pool.submit(run,'final-'+p.stem,['python3',str(p.relative_to(ROOT)),'-v']) for p in files]
 result=[f.result() for f in as_completed(futures)]
result.append(run('registry-strict',['python3','-m','mod_editor.capabilities.validate_registry']))
raise SystemExit(any(result))
