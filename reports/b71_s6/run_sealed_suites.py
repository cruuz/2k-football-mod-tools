"""Recheck the final texture pipeline, shared compiler pins and release closure."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from run_logged import run
names=('nfl2k5_scorebug_sprite','nfl2k5_scorebug_exact','nfl2k5_scorebug_freeze_v2','nfl2k5_scorebug_resources','nfl2k5_scorebug_template_release','provider_integrity','product_catalog','phase1_packaging','scorebug_sprite_preview_qt')
with ThreadPoolExecutor(max_workers=3) as pool:
 futures=[pool.submit(run,'sealed-test_'+n,['python3','tests/mod_editor/test_'+n+'.py','-v']) for n in names]
 codes=[f.result() for f in as_completed(futures)]
raise SystemExit(any(codes))
