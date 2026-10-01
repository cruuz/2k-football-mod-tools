"""PROVED OFFLINE: use the existing s14 native tint-response measurement, without changing its transfer."""
from pathlib import Path
import sys,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT)]
from reports.b76_s14 import fit_display as fit
from mod_editor.core import nfl2k5_scorebug_teams as teams
OUT=Path(__file__).resolve().parent
measure=json.loads((OUT/'measurements.json').read_text())
# s14's probe predates validation of wash after dropping the display record.
# Keep the scratch probe's wash consistent; never widen production validation.
from contextlib import contextmanager
original_probe=fit.probe_folder
@contextmanager
def probe_folder():
    with original_probe() as folders:
        for tint,folder in folders.items():
            p=folder/'team_accents.json';d=json.loads(p.read_text())
            for name in ('NYG','LAR'):d['teams'][name]['wash']=tint
            p.write_text(json.dumps(d))
        yield folders
fit.probe_folder=probe_folder
resp=fit.response()
colours={'teams':{}}
for name,side in [('PHI','away'),('CHI','home')]:
    row=measure['states'][name]
    colours['teams'][name]={'phi_chi':dict(side=side,wing=dict(frames=row['count']),plate=dict(rgb=row['plate_rgb'],frames=row['count']),wing_rows=dict(first_row=940,rgb=row['wing_row_profiles'][name]))}
measured=fit.measured_shades(colours,resp)
accents=teams.load();display=teams.load_display()
for name,row in measured.items():
    parent='#004851' if name=='PHI' else '#E64100'
    value=fit.hexof(row['wing']);fitted=teams.broadcast_shade(parent,display['transfer'])
    row.update(parent=parent,hex=value,fitted=fitted,distance=teams.oklab_distance(value,fitted),bound=display['transfer']['measured_bound'])
    row['plate_candidates']=sorted([dict(value=v,error=float(fit.de2000(teams.rgb(v),row['plate'])[0])) for v in teams.variants(accents[name]['official']) if teams.contrast_white(v)>=4.5],key=lambda r:r['error'])[:5]
(OUT/'fit.json').write_text(json.dumps(dict(classification='PROVED OFFLINE',teams=measured),indent=2)+'\n');print(measured)
