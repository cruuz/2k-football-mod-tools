"""Re-run checks that imported an earlier owner during the investigation."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from run_logged import run,ROOT,OUT
cutoff=json.loads((OUT/'build-owner-final.result.json').read_text())['end_utc']
rows=[json.loads(p.read_text()) for p in OUT.glob('final-*.result.json')]
paths={r['argv'][1] for r in rows if r['start_utc']<cutoff}
# This long suite began before the final owner and may not yet have a receipt.
paths.add('tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py')
with ThreadPoolExecutor(max_workers=3) as pool:
 futures=[pool.submit(run,'verified-'+Path(p).stem,['python3',p,'-v']) for p in sorted(paths)]
 results=[f.result() for f in as_completed(futures)]
raise SystemExit(any(results))
