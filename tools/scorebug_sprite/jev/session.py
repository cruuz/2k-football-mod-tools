"""Auditable Jev request/replay boundary with a job-wide three-dollar cap."""
from pathlib import Path
import json
import os
import time

CAP_USD=3.0
PRICE_PER_TOKEN=.042/1_000_000
USAGE=Path.home()/'ai-stack/jev/logs/usage.jsonl'


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')


def usage_total(path=USAGE):
    if not Path(path).is_file():return 0.
    return sum(json.loads(s).get('cost_usd',0.) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip())


def unpack(result):
    """Accept the exact MCP envelope or the outside-sandbox SDK receipt."""
    if 'structuredContent' in result:result=json.loads(result['structuredContent']['result'])
    elif 'content' in result:result=json.loads(next(c['text'] for c in result['content'] if c['type']=='text'))
    return result


def answers(result):
    result=unpack(result)
    return result.get('answers',result)


class Session:
    def __init__(self,report):
        self.report=Path(report);self.report.mkdir(parents=True,exist_ok=True)
        self.log=self.report/'jev_calls.jsonl'
        self.start=self.report/'usage_start.json'
        if not self.start.exists():write_json(self.start,dict(cost_usd=usage_total()))
        self.initial=json.loads(self.start.read_text())['cost_usd']

    def spent(self):
        local=0.
        if self.log.exists():
            for line in self.log.read_text(encoding='utf-8').splitlines():
                r=json.loads(line);response=unpack(r.get('response',{}))
                local+=response.get('meta',response.get('totals',{})).get('cost_usd',0.)
        return max(local,usage_total()-self.initial)

    def guard(self,request):
        # At most one UTF-8 byte per input token is a conservative reserve.
        reserve=(len(json.dumps(request).encode('utf-8'))+4096)*PRICE_PER_TOKEN
        if self.spent()+reserve>=CAP_USD:raise RuntimeError('Jev job cap reached; no call was sent')

    def record(self,request,response):
        with self.log.open('a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(dict(tool=request['tool'],request=request,response=response))+'\n')

    def replay(self,request):
        """Integrator only: installed TypeSafe SDK, environment key, no shell."""
        self.guard(request)
        if not os.environ.get('TYPESAFE_API_KEY'):
            raise RuntimeError('TYPESAFE_API_KEY is not set; export it before replay. No answer was fabricated.')
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError as exc:  # integrator-only path; never reached by a normal Studio install
            raise RuntimeError(
                'Replay needs the TypeSafe SDK, which the Studio does not ship. '
                'Install it with: pip install typesafe-sdk. No answer was fabricated.'
            ) from exc
        if request['tool']!='jev_ask':raise ValueError('Replay accepts raw typed jev_ask requests')
        start=time.monotonic()
        result=TypeSafeClient().system_one(state=request['state'],questions=request['questions'])
        meta=dict(tool='b72-s3-replay',model=result.model,input_tokens=result.usage.input_tokens or 0,
                  output_tokens=result.usage.output_tokens or 0,latency_ms=round((time.monotonic()-start)*1000,2))
        meta['cost_usd']=meta['input_tokens']*PRICE_PER_TOKEN
        response=dict(answers={k:v.model_dump() for k,v in result.answers.items()},meta=meta)
        # Global log is only written by an explicitly run outside-sandbox replay.
        USAGE.parent.mkdir(parents=True,exist_ok=True)
        with USAGE.open('a',encoding='utf-8') as f:f.write(json.dumps(meta)+'\n')
        self.record(request,response)
        return response['answers']
