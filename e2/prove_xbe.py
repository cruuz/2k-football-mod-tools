"""PROVED OFFLINE: compose the recipe's executable owners before the expensive disc build."""
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), '/home/noah/Desktop/2K5-8 Editors/ultimate']
import build_ultimate as bu
from mod_editor.core import mod_build as mb, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_anniversary_kickoff as gate, nfl2k5_era_rules as era

OUT = Path('/media/noah/Storage/.b76-research/e2/astra-build')
r = json.loads((OUT / 'candidate_B_e2.json').read_text())
p = mb.apply_preset(mb.BuildPlan(bu.DEFAULT_SOURCE, str(OUT/'candidate_B_e2.xiso.iso')), r['preset'])
for key,value in r['overrides'].items():setattr(p,key,bu.resolve(value, ROOT, key))
options={k:getattr(p,k) for k in inspect.signature(tt._apply_all).parameters if hasattr(p,k)}
options.update(wanted=None,anniversary_kickoff=True,anniversary_kickoff_tables=gate.disc_tables(p.source),
               widescreen_menus=True)
# Disc builder installs the position pools before the rows pass.
options['depth_chart_rows'] = False
x, receipt=tt._apply_all(mb._xbe_bytes(Path(p.source)),**options)
from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_depth_chart_rows as rows
if p.position_pools:
    x, _ = pools.apply(x, roster_has_olb=True, depth_chart_third_starter=p.depth_chart_rows)
if p.depth_chart_rows:
    x, _ = rows.apply(x)
states=tt._grown_status_fields(x)
assert states['historic_stock_books']=='applied' and states['espn25_era_rules']=='applied', states
(OUT/'recipe-probe.xbe').write_bytes(x)
(OUT/'recipe-xbe-proof.json').write_text(json.dumps(dict(classification='PROVED OFFLINE',states=states,
    route=era.routing_info(x), receipt=receipt),indent=2,default=str)+'\n')
print('PROVED OFFLINE',states,flush=True)
