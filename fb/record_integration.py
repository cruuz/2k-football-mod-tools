"""List exact source/pin changes against candidate E; never rewrite model pins."""
import ast,subprocess,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];B=ROOT.parent
base=json.loads((B/'setup.json').read_text())['base']
def original(p):return subprocess.check_output(['git','--git-dir='+str(B/'private.git'),'show',base+':'+str(p)])
def sha(b):return hashlib.sha256(b).hexdigest()
models=['state_farm','mercedes_benz','highmark','att','lucas_oil','everbank','hard_rock','usbank','sofi','levis','allegiant','lambeau']
checks=[]
for model in models:
 path=Path('mod_editor/core/nfl2k5_'+model+'_model.py');before=original(path).decode();after=(ROOT/path).read_text()
 def nodes(s):return {n.name:ast.get_source_segment(s,n) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 a,b=nodes(before),nodes(after);changed=[k for k in a if a[k]!=b[k]]
 assert set(changed)=={'bundle_state','image_status','apply_to_image'},(model,changed)
 pin=Path('data/nfl2k5_'+model+'_model/pins.json');assert original(pin)==(ROOT/pin).read_bytes()
 checks.append(dict(model=model,changed_functions=changed,all_geometry_texture_generators_camera_builders_unchanged=True,pin_file=str(pin),sha256=sha((ROOT/pin).read_bytes()),pin_change=False))
reg=Path('mod_editor/capabilities/registry.v1.json');old=json.loads(original(reg));new=json.loads((ROOT/reg).read_text());pins=[]
for a,b in zip(old['capabilities'],new['capabilities']):
 assert a['id']==b['id']
 aa=a.get('source_container',{}).get('hash_pins',[]);bb=b.get('source_container',{}).get('hash_pins',[])
 if aa!=bb:pins.append(dict(capability=a['id'],before=aa,after=bb))
(B/'evidence/integration_pins.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',base=base,model_checks=checks,registry_changes=pins),indent=2)+'\n')
# Byte-preservation claims concern geometry and decoded allocations; compressed
# bytes within a changed stadium span necessarily differ.
print('UNCHANGED MODEL PIN FILES',len(checks),'CHANGED REGISTRY PIN SETS',len(pins))
