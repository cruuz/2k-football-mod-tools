"""Check C4 scope, merge ancestry, immutable sources and reviewable artifacts."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
G=['git','--git-dir='+str(ROOT/'.scratch/astra-c4.git')]
def git(*args):
    return subprocess.check_output(G+list(args),cwd=ROOT)

for parent in ('a7440f05','45a5ade9'):
    subprocess.run(G+['merge-base','--is-ancestor',parent,'HEAD'],check=True,cwd=ROOT)
base_pins=json.loads(git('show','45a5ade9:data/nfl2k5_modern_color_pins.json'))
current=json.loads((ROOT/'data/nfl2k5_modern_color_pins.json').read_text())
assert base_pins['bundles']==current['bundles']
changed=[a['name'] for a,b in zip(base_pins['light_tables'],current['light_tables']) if a!=b]
assert changed==['day','afternoon']
for a,b in zip(base_pins['light_tables'],current['light_tables']):
    assert {k:v for k,v in a.items() if k!='applied_sha256'}=={k:v for k,v in b.items() if k!='applied_sha256'}
# All scorebug owner/helper sources and widescreen retain the combined A5 implementation.
paths=git('ls-tree','-r','--name-only','a7440f05','mod_editor/core','tools').decode().splitlines()
paths=[p for p in paths if Path(p).suffix=='.py' and ('scorebug' in Path(p).name or Path(p).name=='nfl2k5_widescreen.py')]
for p in paths:
    assert (ROOT/p).read_bytes()==git('show','a7440f05:'+p),p
# Every source branch RC96 feature bullet is represented after merging.
headings=[]
for rev in ('a7440f05','45a5ade9'):
    text=git('show',rev+':docs/mod_editor/2k5_mod_studio_changelog.md').decode().split('## v1.0 RC95')[0]
    headings.extend(line.split('**')[1] for line in text.splitlines() if line.startswith('- **'))
changelog=(ROOT/'docs/mod_editor/2k5_mod_studio_changelog.md').read_text().split('## v1.0 RC95')[0]
for title in headings:assert '**'+title+'**' in changelog,title
for rev,folder in [('a7440f05','b71_a5'),('45a5ade9','b71_c3')]:
    for name in ['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md']:
        assert (ROOT/'reports'/folder/('INHERITED_'+name)).read_bytes()==git('show',rev+':'+name)
proof=json.loads((ROOT/'reports/b71_c4/daylight-proof.json').read_text())
assert proof['owner_sha256']==hashlib.sha256((ROOT/'mod_editor/core/nfl2k5_modern_color.py').read_bytes()).hexdigest()
assert (ROOT/'data/nfl2k5_cave_reservations.json').read_bytes()==git('show','a7440f05:data/nfl2k5_cave_reservations.json')
result=dict(merge_parents_preserved=True,c3_commit='45a5ade9',base_commit='a7440f05',
            changed_rigs=changed,unchanged_bundle_count=len(current['bundles']),
            pinned_unchanged_a5_sources=paths,rc96_feature_bullets_preserved=sorted(set(headings)),
            inherited_reports_exact=True,proof_matches_current_owner=True,protected_manifest_unchanged=True)
(ROOT/'reports/b71_c4/delivery-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS: both merge parents, all inherited feature bullets/reports, exact bundle and unaffected rig pins,',len(paths),'unchanged A5 scorebug/widescreen sources')
