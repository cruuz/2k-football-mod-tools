"""Differential checks against the job's ec5d68d4 base implementation."""
from collections import Counter
from pathlib import Path
import ast
import random
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import nfl_tset_png_import as palettes
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_resources as resources
from mod_editor.core import nfl2k5_scorebug_ingame as scene


def original(path, name, module):
    source=subprocess.check_output(['git','show','ec5d68d4:'+path],cwd=ROOT,text=True)
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    namespace=dict(vars(module))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<ec5d68d4 '+name+'>','exec'),namespace)
    return namespace[name]


old_palette=original('tools/nfl_tset_png_import.py','median_cut_palette',palettes)
histograms=[Counter({(i,i,i,255):1 for i in range(256)}),
            Counter({(i,j,0,255):1 for i in range(0,256,16) for j in range(0,256,16)})]
for seed in range(4):
    rng=random.Random(seed)
    histograms.append(Counter({tuple(rng.randrange(256) for _ in range(4)):rng.randrange(1,101) for _ in range(512)}))
for histogram in histograms:
    for maximum in (16,64,128,256):
        assert palettes.median_cut_palette(histogram,maximum)==old_palette(histogram,maximum)
print('24 palette comparisons against ec5d68d4 passed (ties and seeded RGBA).',flush=True)

old_panel=original('mod_editor/core/nfl2k5_scorebug_exact.py','panel',exact)
pack=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
count=0
with pack.open('rb') as stream:
    for team in [None]+sorted(scene.TEAM_LOGOS):
        if team is None:span=b''
        else:
            record=scene.TEAM_LOGOS[team]
            stream.seek(record['pack_offset']);span=stream.read(record['span_size'])
        for side in ('home','away'):
            images=list(resources.panel_states(span,team,side))
            assert len(images)==4
            for timeout,image in enumerate(images):
                assert image.tobytes()==old_panel(span,team,side,timeouts=timeout).tobytes(),(team,side,timeout)
                count+=1
print(str(count)+' panel variants exactly match ec5d68d4 RGBA bytes.',flush=True)
