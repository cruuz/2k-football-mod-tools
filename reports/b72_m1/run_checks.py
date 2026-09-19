"""Standalone offline suites, two detached runners at most; logs contain no retail bytes."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'reports/b72_m1'
GROUP = sys.argv[1]
if GROUP == 'all':
    running = []
    for group in ('suites', 'gates'):
        stream = (OUT/(group+'-runner.log')).open('wb')
        process = subprocess.Popen([sys.executable, __file__, group], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        stream.close()
        running.append(process)
    # Keep the supervisor alive: this tool sandbox reaps orphaned processes.
    raise SystemExit(int(any([process.wait() for process in running])))
if GROUP == 'gates':
    names = ['test_xbe_patch_memory_writes', 'test_xbe_patch_cave_references',
             'test_nfl2k5_cave_oracle', 'test_nfl2k5_owner_pairwise_composition']
else:
    names = ['test_nfl2k5_my_career_host']
    names += [p.stem for p in sorted((ROOT/'tests/mod_editor').glob('test_nfl2k5_my_career*.py')) if p.stem not in names]
    names += ['test_mycareer_art', 'test_b69_j1_fit', 'test_b69_j1_wiring', 'test_b69_j1_native', 'test_b69_j1_build',
              'test_studio_session', 'test_music_playlist_project', 'test_audio_annotation_project_archive',
              'test_project_document_workflow', 'test_models_project_wiring', 'test_b71_t5_project_open']
env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen',
           NFL2K5_CAVE_MANIFEST=str(ROOT/'.scratch/b72-m1-gate-manifest.json'))
results = []
for name in names:
    path = OUT/(name + '.log')
    start = time.monotonic()
    with path.open('wb') as stream:
        process = subprocess.run([sys.executable, str(ROOT/'tests/mod_editor'/(name+'.py'))],
                                 cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    result = dict(test=name, returncode=process.returncode, seconds=round(time.monotonic()-start, 3))
    results.append(result)
    (OUT/(GROUP+'-results.json')).write_bytes((json.dumps(results, indent=2)+'\n').encode('utf-8'))
    print(json.dumps(result), flush=True)
raise SystemExit(int(any(r['returncode'] for r in results)))
