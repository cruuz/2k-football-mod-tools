"""Serial special-slot table from sn's descriptor-verified ledger, bound to current source hashes."""
import sys,json,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_stadium_shared_art as shared
SN=ROOT.parent.parent/'sn';source=ROOT/'extracted/ESPN NFL 2K5 (USA)'
design=json.loads((shared.DATA/'design.json').read_text());ledger={r['bundle']:r for r in map(json.loads,(SN/'retail.bundles.jsonl').read_text().splitlines())}
out={};receipts=[]
with mv._outer_image()(source,writable=False) as archive:
 by_id={e.name_id:e for e in archive.entries}
 for prefix in sorted({r['venue'] for r in design['textures']} - set(mv.table()['venues'])):
  bundles=[];variants={}
  for name in mv.bundle_names(prefix):
   pin=ledger[name];entry=by_id[mv.name_id(name)];data=archive.read(entry.virtual_offset,entry.size)
   assert mv.sha(data)==pin['sha256'] and entry.index==pin['outer'] and len(data)==pin['size'],name
   occurrences=[json.loads(s) for s in gzip.decompress(next((SN/'retail.occurrences').glob(name+'*')).read_bytes()).splitlines()]
   variants[name[3:5]]=[r for r in occurrences if r['scene']=='stadium']
   chunks=mv._tools()[0].parse_chunks(data)
   scenes={r['scene']:chunks[r['index']] for r in pin['chunks'] if r.get('scene') in mv.SCENES}
   sites=[dict(kind=kind,offset=scenes[kind].offset,size=scenes[kind].end_offset-scenes[kind].offset,retail=mv.sha(data[scenes[kind].offset:scenes[kind].end_offset])) for kind in mv.SCENES]
   if name[3:5]=='dd':
    materials={n:r['texture'] for r in occurrences if r['scene']=='field' for n in r['names']}
    field=dict(endzones='split' if any(materials.get('endzone_S_'+p)!=materials.get('endzone_N_'+p) for p in mv.END_ZONE_PARTS) else 'shared',center_logo='center_logo' in materials)
   bundles.append(dict(name=name,outer=entry.index,name_id=entry.name_id,size=entry.size,retail_sha256=pin['sha256'],sites=sites))
  targets=[]
  for row in [r for r in design['textures'] if r['venue']==prefix]:
   dd=next(r for r in variants['dd'] if mv.export_key(r['names'])==row['material'])
   assert dd['rgba_sha256']==row['source_rgba_sha256'] and dd['studio_verified']
   matched={}
   for code,entries in variants.items():
    matches=[r for r in entries if mv._norm(r['names'])==mv._norm(dd['names'])]
    if not matches:
     matches=[r for r in entries if r['rgba_sha256']==dd['rgba_sha256']]
    assert len(matches)==1,(prefix,code,row['material'],len(matches))
    r=matches[0];assert r['studio_verified'] and r['format']=='P8'
    matched[code]=[r['texture'],r['width'],r['height']]
   targets.append(dict(key=row['material'],texture=dd['texture'],size=row['size'],names=dd['names'],variants=matched,
                       match={c:1.0 for c in mv.CODES},cutout=False,note='Exact normalized names or unique identical RGBA in sn descriptor-verified occurrences, every source bundle SHA-256 checked; not an image-correlation score',**{'class':'league'}))
  out[prefix]=dict(team=prefix,stadium='Retail special slot '+prefix,field=field,bundles=bundles,targets=targets,league=[],league_art=[],extras=[],stadium_only=True)
  receipts.append(dict(venue=prefix,source_bundles_sha256_verified=9,targets=len(targets),selector_method='exact normalized material names or unique identical RGBA, all nine variants'))
  print(prefix,len(targets),flush=True)
shared.TABLE_PATH.write_text(json.dumps(dict(schema='nfl2k5_stadium_shared_art_special_venues/v1',venues=out),indent=2,sort_keys=True)+'\n')
(ROOT.parent/'evidence/special_selector_proof.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',venues=receipts),indent=2)+'\n')
print('PINNED',len(out),flush=True)
