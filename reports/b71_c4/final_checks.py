"""Require complete C4 evidence before packaging the handoff."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
folder=ROOT/'reports/b71_c4'
required=('colour_legacy','colour_controls_final','colour_gui','all_default_pins','daylight_readback',
          'daylight_composition','build_panel','mod_build','project_settings','providers',
          'provider_integrity_updated','phase1_packaging','product_catalog','registry_final',
          'builder_source','xbe_memory_writes','xbe_cave_references','manifest_projection_final',
          'cave_oracle_projected','scope_audit','repin_final')
for name in required:
    doc=json.loads((folder/(name+'.json')).read_text())
    assert doc['exit_code']==0,(name,doc)
report=(ROOT/'ASTRA_REPORT.md').read_text()
assert 'RUNNING / not yet recorded' not in report
assert (ROOT/'ASTRA_LAST_MESSAGE.md').read_text().rstrip().endswith('ASTRA_DONE')
assert not (ROOT/'.scratch/testdisc71g').exists(), 'builder unexpectedly left execution evidence'
builder=json.loads((folder/'builder-source-proof.json').read_text())
assert builder['sha256']==hashlib.sha256((folder/'build_testdisc71.py').read_bytes()).hexdigest()
proof=json.loads((folder/'daylight-proof.json').read_text())
assert proof['owner_sha256']==hashlib.sha256((ROOT/'mod_editor/core/nfl2k5_modern_color.py').read_bytes()).hexdigest()
subprocess.run(['git','--git-dir='+str(ROOT/'.scratch/astra-c4.git'),'diff','--check'],cwd=ROOT,check=True)
scratch=sum(p.stat().st_size for p in (ROOT/'.scratch').rglob('*') if p.is_file())
assert scratch<200*1024*1024,scratch
print('PASS:',len(required),'required checks exit 0; final report, message, source identity, builder preparation, whitespace and scratch size verified')
