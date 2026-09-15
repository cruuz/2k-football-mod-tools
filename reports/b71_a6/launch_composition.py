from concurrent.futures import ThreadPoolExecutor
from run import run
names=['s13'+t+w+'.iff' for t in 'dan' for w in 'drs']
with ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(lambda n:run('composition-'+n,['python3','reports/b71_a6/prove_composition.py',n]),names))
raise SystemExit(any(results))
