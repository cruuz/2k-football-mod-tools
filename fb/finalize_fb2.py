"""Small read-only integration inventory and source-gate evidence."""
import json,subprocess,hashlib,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')];B=ROOT.parent
from mod_editor.core import nfl2k5_cave_oracle as oracle
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
base=json.loads((B/'setup.json').read_text())['base'];git=['git','--git-dir='+str(B/'private.git'),'--work-tree='+str(ROOT),'-c','core.filemode=false']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads(oracle.DEFAULT_MANIFEST.read_text());stale=[]
for path,old in manifest['source_sha256'].items():
 p=ROOT/path
 if sha(p)!=old:stale.append(dict(path=path,before=old,after=sha(p)))
(B/'evidence/cave_source_changes_fb2.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',changes=stale,action='Main regenerates the observed-build reservation manifest after integration. A full build is outside fb2 scope; no cave pin was hand-edited.'),indent=2)+'\n')
paths=subprocess.check_output(git+['diff','--name-only','--diff-filter=M'],text=True).splitlines()
changes=[]
for path in paths:
 p=ROOT/path
 if p.is_file():changes.append(dict(path=path,before=hashlib.sha256(subprocess.check_output(git+['show',base+':'+path])).hexdigest(),after=sha(p)))
(B/'evidence/integration_files_fb2.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',base=base,modified=changes),indent=2)+'\n')
# Only current evidence is distributed. Obsolete fb prep stays in the lab area.
folder=ROOT/'fb/evidence';folder.mkdir(exist_ok=True)
for name in ['fan_proof.json','fan_proof.log','fan_inventory.json','sponsor_proof.json','sponsor_proof.log','corporate_reuse.log','residual_sponsor_ledger.json','u4_sponsor_exclusions.json','special_selector_proof.json','tests_fb2.log','tests_catalog_final.log','tests_fan_final.log','integration_pins.json','integration_files_fb2.json','cave_source_changes_fb2.json','event_proof.json','event_disassembly.txt','event_strings.txt']:
 shutil.copyfile(B/'evidence'/name,folder/name)
review=ROOT/'fb/review';review.mkdir(exist_ok=True)
for p in (B/'review').glob('model_banners*'):shutil.copyfile(p,review/p.name)
shutil.copyfile(B/'review/home_sponsors_E_before_after.png',review/'home_sponsors_E_before_after.png')
sponsors=review/'sponsors';sponsors.mkdir(exist_ok=True)
for p in (B/'review/sponsors').glob('before_after_*.png'):shutil.copyfile(p,sponsors/p.name)
shutil.copyfile(B/'review/sponsors/index.html',sponsors/'index.html')
print('MODIFIED',len(changes),'STALE CAVE SOURCES',len(stale))
print(json.dumps(stale,indent=2))
