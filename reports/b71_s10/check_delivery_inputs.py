"""Refuse a delivery that silently drops a required check or its causal limit."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
expected=sorted(p for p in (ROOT/'tests/mod_editor').glob('test_*.py') if 'scorebug' in p.name or 'scorebar' in p.name)
expected += [ROOT/'tests/nfl2k5_scorebug_layout_test.py',ROOT/'tests/nfl2k5_scorebug_mod_project_test.py']
expected += [ROOT/'tests/mod_editor'/('test_'+n+'.py') for n in ('provider_integrity','product_catalog','phase1_packaging','mod_build','build_panel_qt','nfl2k5_allocator_scaleout','nfl2k5_xbe_space')]
rows=sorted((json.loads(p.read_text()) for p in OUT.glob('*.result.json')),key=lambda r:r['start_utc'])
latest={tuple(r['argv']):r for r in rows}
cutoff=json.loads((OUT/'build-owner-final.result.json').read_text())['end_utc']
for p in expected:
 argv=('python3',str(p.relative_to(ROOT)),'-v');r=latest[argv]
 assert r['exit_code']==0,(argv,r)
 assert r['start_utc']>cutoff,(argv,'pre-final owner')
for name in ('native-sequence-clock-fixture-final','prove-states-final','byte-audit-final','timers-literals','history-probe','compiler-pins','owner-reproducible-final','prepared-disc-final','registry-strict','disc-n-native-bindings-verified'):
 r=json.loads((OUT/(name+'.result.json')).read_text());assert r['exit_code']==0,(name,r)
sweep=json.loads((OUT/'label_sweep.json').read_text());assert sweep['count']==808
assert len(json.loads((OUT/'states.json').read_text()))==50
seq=json.loads((OUT/'native_sequence.json').read_text());assert len(seq['stages'])==28
assert sum(len(s['frames']) for s in seq['stages'])==1820
for mode in ('False','True'):
 row=json.loads((OUT/'scene_byte_audit.json').read_text())[mode]
 assert row['scene_changed_byte_count']==1 and row['unchanged_texture_chunks']==34
 assert row['appended_bytes']==323808
assert not (OUT/'build-receipt').exists(),'Prepared disc must not have been run'
print('PASS: all required latest checks ran against final owner; 808 labels, 50 sheet states, 1820 retained frames; disc not built.')
