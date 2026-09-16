from concurrent.futures import ThreadPoolExecutor,as_completed
from run_logged import run
if run('manifest-sealed',['python3','reports/b71_s6/refresh_manifest_projection.py']):raise SystemExit(1)
names=['test_xbe_patch_memory_writes','test_xbe_patch_cave_references','test_nfl2k5_cave_oracle','test_nfl2k5_owner_pairwise_composition']
with ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(run,'gate-'+name,['python3','tests/mod_editor/'+name+'.py','-v']) for name in names]
 codes=[f.result() for f in as_completed(futures)]
raise SystemExit(any(codes))
