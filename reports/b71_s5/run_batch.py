from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import sys
from run_logged import run,ROOT,OUT
names=sys.argv[2:];prefix=sys.argv[1]
with ThreadPoolExecutor(max_workers=3) as pool:
 fs={pool.submit(run,prefix+'-'+Path(p).stem,[sys.executable,p,'-v']):p for p in names}
 codes=[f.result() for f in as_completed(fs)]
raise SystemExit(any(codes))
