"""PROVED OFFLINE: resolve B's actual builder inputs and intersect modern book targets.

DESIGN: emit source-free alias metadata; this never installs a hook or copies a book.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import zlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_historic_styles as hs

RECIPE=Path('/home/noah/Desktop/2K5-8 Editors/ultimate/ULTIMATE_BUILD_RECIPE_2026-09-25_candidate_B.json')
SOURCE=Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')

def save(name,value):
    (ROOT/name).write_text(json.dumps(value,indent=2)+'\n')

def main():
    recipe=json.loads(RECIPE.read_text())
    plan=mod_build.apply_preset(mod_build.BuildPlan('',''),recipe['preset'])
    for key,value in recipe['overrides'].items():
        assert hasattr(plan,key),key
        setattr(plan,key,value)
    keys=[k for k in vars(plan) if any(w in k for w in ('kick','overtime','espn25','historic','penalt','defer','decided','defensive_try','playbook','venues','sofi','super_bowl','uniform_choice','two_point','highmark','metlife','position_pools'))]
    scope=dict(classification='PROVED OFFLINE',scope='Preset plus overrides, exactly as build_ultimate_teams2026.py. That builder ignores pending. No candidate B ISO read.',
        recipe_path=str(RECIPE),recipe_sha256=hashlib.sha256(RECIPE.read_bytes()).hexdigest(),
        options={k:getattr(plan,k) for k in keys},pending={k:v for k,v in recipe['pending'].items() if 'espn' in k},
        playbook_pack_count=len(recipe['freeze']['playbooks']),playbook_pack_hashes=recipe['freeze']['playbooks'])
    save('e2/evidence/build_scope.json',scope)
    by=defaultdict(list);rows=[]
    for filename in plan.playbook_packs:
        p=Path(filename);raw=p.read_bytes();doc=json.loads(raw);sha=hashlib.sha256(raw).hexdigest()
        assert sha==scope['playbook_pack_hashes'][p.name]
        targets=doc['book'].get('targets') or [doc['book']['team']]
        for target in targets:by[target+'-pb.iff'].append(p.name)
        rows.append(dict(file=p.name,sha256=sha,targets=targets,book=doc['book']['name'],schema=doc['schema']))
    assert len(rows)==64 and len(by)==32 and all(len(p)==2 for p in by.values())
    native=json.loads((ROOT/'e2/evidence/native_books.json').read_text())
    requested={x['filename'] for x in native['historic_teams']}|{v['filename'] for m in native['moments'] for v in m['sides'].values()}
    assert requested<=set(by)
    report=dict(classification='PROVED OFFLINE',packs=rows,overwritten_filenames=dict(by),native_requested_union=sorted(requested),
        native_requested_union_count=len(requested),all_native_requests_hit_modern_targets=True,
        retail_alias_bytes_31=sum(native['books'][k]['bytes'] for k in requested),retail_alias_bytes_32=sum(b['bytes'] for b in native['books'].values()))
    save('e2/evidence/modern_book_targets.json',report)
    aliases=[]
    with hs.Source(SOURCE) as source:
        ids=set(source.by_id)
        for filename,book in sorted(native['books'].items()):
            alias='E2R-'+filename
            identity=zlib.crc32(alias.upper().encode('utf-16le'))&0xffffffff
            assert identity not in ids and len(alias.encode('utf-16le'))+2<=64
            ids.add(identity)
            aliases.append(dict(source=filename,source_sha256=book['sha256'],bytes=book['bytes'],source_outer=book['outer'],
                alias=alias,alias_name_id=identity,needed_by_existing_75_or_50=filename in requested))
    save('e2/playbook_fix_plan.json',dict(schema='e2.stock_book_design.v1',classification='DESIGN',implemented=False,
        rule='For each match side independently: mode 8 OR category 4 selects its stock alias; current side keeps modern franchise file.',
        evidence='PROVED OFFLINE: alias CRCs do not collide with any retail outer entry or each other; each fits 32 UTF-16 code units including NUL. Loader/decode integration unproved.',
        archive_requirement='32 new entries; full m1 directory has 6 remaining, so at least 26 additional entries require relocation/growth.',aliases=aliases))
    print('64 pack hashes; 32 replacement targets; all 31 requested franchise books conflict; 32 alias IDs distinct and bounded.')

if __name__=='__main__':main()
