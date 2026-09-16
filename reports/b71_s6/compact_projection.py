"""Remove duplicate historical observation payloads, preserving every reservation."""
from pathlib import Path
import copy,hashlib,json
ROOT=Path(__file__).resolve().parents[2]

def compact(document):
    doc=copy.deepcopy(document);removed={}
    for key,value in doc.items():
        if key.endswith('_projection') and key!='b71_s6_projection' and isinstance(value,dict) and 'observed_steps' in value:
            steps=value.pop('observed_steps')
            seal=hashlib.sha256(json.dumps(steps,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            value['historical_observed_step_count']=len(steps)
            value['historical_observed_steps_sha256']=seal
            value['historical_observed_steps_location']='Retained in the top-level steps ledger and the S5 parent manifest; duplicate projection payload omitted.'
            removed[key]=dict(count=len(steps),sha256=seal)
    for key in ('steps','spans','allocator_layout','source_sha256','stack_xbe_sha256'):
        assert doc[key]==document[key],key
    return doc,removed

def main():
    path=ROOT/'data/nfl2k5_cave_reservations.json';before=path.read_bytes();doc,removed=compact(json.loads(before));after=(json.dumps(doc,indent=2)+'\n').encode()
    assert len(after)<8*1024**2
    path.write_bytes(after)
    (ROOT/'.scratch/b71-s6-manifest.json').write_bytes(after)
    result=dict(before_bytes=len(before),after_bytes=len(after),before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(after).hexdigest(),compacted_historical_projections=removed,reservations_steps_sources_and_xbe_unchanged=True)
    (ROOT/'reports/b71_s6/projection-compaction.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
