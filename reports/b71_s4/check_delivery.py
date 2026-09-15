"""Check final source seals and prepared artifacts without executing the builder."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_resources as resources,nfl2k5_scorebug_runtime as owner
from mod_editor.core.nfl2k5_cave_manifest import source_fingerprints

out=ROOT/'reports/b71_s4'
manifest=json.loads((ROOT/'data/nfl2k5_cave_reservations.json').read_bytes())
assert manifest['source_sha256']==source_fingerprints()
count,append,growth=resources.probe_sizes('mnf')
assert (count,append,growth)==(33,410624,411648)
code=owner.code_for(0,0)[0].rstrip(b'\xcc')
assert (len(code),owner.CODE_SIZE,owner.DATA_SIZE)==(1380,1408,128)
builder=out/'build_testdisc71.py'
tree=ast.parse(builder.read_bytes());compile(tree,str(builder),'exec')
constants={node.targets[0].id:ast.literal_eval(node.value) for node in tree.body
           if isinstance(node,ast.Assign) and len(node.targets)==1
           and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('NAME','OPTIONS')}
assert constants['NAME']=='NFL 2K5 MOD TEST 2026-09-15j (painted bar + colour + widescreen)'
assert constants['OPTIONS']==('scorebug','scorebug_runtime','modern_color','widescreen')
prepared=json.loads((out/'builder_prepared.json').read_bytes())
assert prepared['builder_sha256']==hashlib.sha256(builder.read_bytes()).hexdigest()
assert prepared['executed'] is False
m=json.loads((out/'measurements.json').read_bytes())
for aspect in m['comparisons'].values():
 assert all(r['native_boundary_error_px']<=1 for r in aspect['regions'].values())
 assert all(r['max_error_px']<=1 and r['rendered_ink_max_error_px']<=1 for r in aspect['text'].values())
 assert all(r['max_hud_pixel_error']<=1 for r in aspect['rendered_text_source_boxes'].values())
 assert aspect['exact_match'] is False
assert all(r['no_plate_overlap'] for r in json.loads((out/'multi_digit_scores.json').read_bytes()).values())
for stem in ('render','no_den','flag','score','hang_time','ball_on','live_clock_hidden','all_events'):
 for aspect in ('43','wide'):assert (out/(stem+'_'+aspect+'.png')).is_file()
summary=json.loads((out/'final-delivery-suite-summary.json').read_bytes())
assert summary['sources_frozen'] and not summary['failed']
for path,expected in summary['source_sha256'].items():
 assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected,path
for name in ('xbe-memory-final','xbe-cave-references-final'):
 assert json.loads((out/(name+'.result.json')).read_bytes())['exit']==0
result=dict(volume_bytes=append,sector_growth=growth,native_heap_bytes=414080,
            code_bytes=len(code),code_budget=owner.CODE_SIZE,data_budget=owner.DATA_SIZE,
            manifest_sources_fresh=True,final_suite_sources_fresh=True,
            builder_name=constants['NAME'],builder_options=constants['OPTIONS'],builder_executed=False,
            boundary_acceptance=True,exact_pixel_match=False)
(out/'delivery_checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
