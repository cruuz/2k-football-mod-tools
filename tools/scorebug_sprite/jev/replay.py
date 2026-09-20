"""Run every-tenth-frame mining outside the sandbox, with resumable receipts."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite.jev.session import Session,write_json
from tools.scorebug_sprite.jev.miner import prepare,cluster


def request_hash(request):
    return hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def resume(requests,log):
    rows=[json.loads(s) for s in log.read_text(encoding='utf-8').splitlines() if s.strip()] if log.exists() else []
    if len(rows)>len(requests):raise ValueError('Answer journal is longer than the request set')
    for index,(row,request) in enumerate(zip(rows,requests)):
        if row.get('request_sha256')!=request_hash(request):
            raise ValueError('Answer journal does not match request '+str(index))
    return [r['answers'] for r in rows]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frames',type=Path,required=True);p.add_argument('--report',type=Path,default=ROOT/'reports/b72_s3')
    p.add_argument('--output',type=Path,default=ROOT/'data/nfl2k5_scorebug_sprite/broadcast_states.json')
    a=p.parse_args();out=a.report/'full_miner';session=Session(a.report)
    if not (out/'requests.json').exists():prepare(a.frames,out,0)
    requests=json.loads((out/'requests.json').read_text(encoding='utf-8'))
    log=out/'answers.jsonl'
    responses=resume(requests,log)
    for req in requests[len(responses):]:
        result=session.replay(req)
        with log.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(dict(request_sha256=request_hash(req),answers=result))+'\n')
        responses.append(result)
        if len(responses)%100==0:print(f'{len(responses)}/{len(requests)}; job cost ${session.spent():.4f}',flush=True)
    write_json(a.output,cluster(json.loads((out/'descriptors.json').read_text(encoding='utf-8')),responses))

if __name__=='__main__':main()
