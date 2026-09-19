"""Remove duplicate helper ownership only where concrete owners cover it fully."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from mod_editor.core.nfl2k5_cave_manifest import source_fingerprints
from mod_editor.core.nfl2k5_cave_oracle import ReservationManifest,XbeImage

def canonical_spans(spans):
 helpers={'nfl2k5_rules_patch','nfl2k5_rdata_sites','nfl2k5_gameplay_lever'}
 # The public patch transactions are observed around the same helper calls.
 # A whole allocator page is deliberately insufficient evidence of ownership.
 ranges=sorted((int(s['start'],0),int(s['end'],0)) for s in spans
               if s['owner'] not in helpers|{'nfl2k5_xbe_space'})
 merged=[]
 for a,b in ranges:
  if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
  else:merged.append([a,b])
 removed=[];kept=[]
 for span in spans:
  if span['owner'] not in helpers:kept.append(span);continue
  a,b=int(span['start'],0),int(span['end'],0)
  assert any(x<=a and b<=y for x,y in merged),('helper lacks concrete-owner coverage',span)
  removed.append(span)
 return kept,dict(helper_names=sorted(helpers),removed_spans=len(removed),
                 every_removed_span_covered_by_concrete_owners=True,
                 observations_retained=True)

def main():
 path=ROOT/'.scratch/b72-s1-gate-manifest.json';original=path.read_bytes();doc=json.loads(original)
 assert doc['source_sha256']==source_fingerprints()
 if 'helper_normalization' not in doc:
  doc['spans'],note=canonical_spans(doc['spans'])
  doc['helper_normalization']=dict(note,observed_manifest_sha256=hashlib.sha256(original).hexdigest())
  retail=(ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe').read_bytes()
  ReservationManifest(doc,XbeImage(retail),source_root=ROOT)
  path.write_text(json.dumps(doc,indent=2)+'\n',newline='\n')
 summary_path=Path(__file__).parent/'gate_manifest_summary.json';summary=json.loads(summary_path.read_text())
 summary.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),spans=len(doc['spans']),helper_normalization=doc['helper_normalization'])
 summary_path.write_text(json.dumps(summary,indent=2)+'\n',newline='\n')
 print(json.dumps(doc['helper_normalization'],indent=2))

if __name__=='__main__':main()
