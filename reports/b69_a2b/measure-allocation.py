from pathlib import Path
import json
from mod_editor.core import nfl2k5_xbe_space as space,nfl2k5_my_career_mode as career,nfl2k5_weather_haze as haze
from mod_editor.core import nfl2k5_coin_defer as coin,nfl2k5_decided_clock as clock,nfl2k5_cpu_scrambles as scrambles
from tests.nfl2k5_allocator_stack import REQUESTS
new_requests=coin.REQUESTS+clock.REQUESTS+scrambles.REQUESTS
old=space.plan([r for r in REQUESTS if r not in new_requests],scaleout=True)
new=space.plan(REQUESTS,scaleout=True)
a={(r['owner'],r['kind']):r for r in old['allocations']};b={(r['owner'],r['kind']):r for r in new['allocations']}
report={'requests':{m.OWNER:m.REQUESTS for m in (career,haze,coin,clock,scrambles)},'allocation_changed':True,'added':[v for k,v in b.items() if k not in a],'moved':[{'owner':k[0],'kind':k[1],'before':a[k],'after':b[k]} for k in sorted(a.keys()&b.keys()) if a[k]!=b[k]],'old_layout':old,'new_layout':new,'scope':'Deterministic complete gate union before/after J5 requests; other build selections can assign different addresses.'}
Path('reports/b69_a2b/allocation-delta.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print('added',len(report['added']),'moved',len(report['moved']))
