#!/usr/bin/env python3
"""Native ht/e2 compatibility against every category in the routed stock books."""
from pathlib import Path
import json
import hashlib
import sys
STACK=Path(sys.argv[1]).resolve()
sys.path[:0]=[str(STACK),str(STACK/'tests'),str(STACK/'tests/mod_editor')]
from test_nfl2k5_stock_books import BooksCPU, NativeStockBooks
from mod_editor.core import nfl2k5_historic_rosters as h
from mod_editor.core import nfl2k5_historic_teams_quick_game as h1

NativeStockBooks.setUpClass()
fixture=NativeStockBooks
payload=h1.enable_season_routing(fixture.payload)
resources=dict(fixture.resources)
context=dict(fixture.context,descriptors=list(fixture.context['descriptors']))
teams=h.require_build_ready()['teams']
for i,t in enumerate(teams):
    index=9000+i
    resources[index]=h.compile_team(resources[t['outer']],t)
    context['descriptors'].append(dict(filename=t['alias'],outer=index))
trace=[]
for flow in h1.LOCAL_FLOWS:
    cpu=BooksCPU(payload,resources,context,fixture.ids,books=fixture.books)
    cpu.team_select(cpu.last_resident(),cpu.team(15),flow=flow)
    for t in teams:
        cpu.press('home',1)
        assert cpu.pool()['used']==len(t['players'])
        cpu.stage();names=cpu.load_books()
        categories=cpu.personnel(1,names[0]);cpu.release_books()
        trace.append(dict(flow=flow,team=t['name'],book=names[0],categories=categories,players=len(t['players'])))
        print('PROVED OFFLINE',trace[-1],flush=True)
out=dict(label='PROVED OFFLINE',one_pool=True,loads=trace,
         manifest_sha256=hashlib.sha256((h.DATA_DIR/'manifest.json').read_bytes()).hexdigest(),
         writer_sha256=hashlib.sha256(Path(h.__file__).read_bytes()).hexdigest(),
         boundaries='Archive delivery and allocator free substituted by the e2 native harness. No rendered gameplay.')
Path('/media/noah/Storage/.b76-research/ht/astra-build/evidence/phase2-stock-native.json').write_text(json.dumps(out,indent=2)+'\n')
