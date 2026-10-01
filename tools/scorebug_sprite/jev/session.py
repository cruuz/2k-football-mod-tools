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

    def replay(self,request,*,tool='b72-s3-replay'):
        """Integrator only: TypeSafe SDK or the same typed endpoint, env key, no shell."""
        self.guard(request)
        if not os.environ.get('TYPESAFE_API_KEY'):
            raise RuntimeError('TYPESAFE_API_KEY is not set; export it before replay. No answer was fabricated.')
        if request['tool']!='jev_ask':raise ValueError('Replay accepts raw typed jev_ask requests')
        start=time.monotonic()
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError:
            # The Studio does not ship the SDK. The same typed System One
            # endpoint the local jev server uses is called directly instead,
            # so a headless job still journals a real answer rather than
            # fabricating one. No key is stored or logged.
            answers,model,usage=self._http_system_one(request)
        else:
            result=TypeSafeClient().system_one(state=request['state'],questions=request['questions'])
            answers={k:v.model_dump() for k,v in result.answers.items()}
            model=result.model
            usage=dict(input_tokens=result.usage.input_tokens or 0,output_tokens=result.usage.output_tokens or 0)
        meta=dict(tool=tool,model=model,input_tokens=int(usage.get('input_tokens') or 0),
                  output_tokens=int(usage.get('output_tokens') or 0),
                  latency_ms=round((time.monotonic()-start)*1000,2))
        meta['cost_usd']=meta['input_tokens']*PRICE_PER_TOKEN
        response=dict(answers=answers,meta=meta)
        # Global log is only written by an explicitly run outside-sandbox replay.
        USAGE.parent.mkdir(parents=True,exist_ok=True)
        with USAGE.open('a',encoding='utf-8') as f:f.write(json.dumps(meta)+'\n')
        self.record(request,response)
        return response['answers']

    @staticmethod
    def _http_system_one(request,attempts=4):
        import httpx
        base=os.environ.get('TYPESAFE_BASE_URL','https://api.typesafe.ai').rstrip('/')
        model=os.environ.get('TYPESAFE_DEFAULT_MODEL','jev-latest')
        payload=dict(state=request['state'],model=model,questions=request['questions'])
        headers={'Authorization':'Bearer '+os.environ['TYPESAFE_API_KEY'].strip(),
                 'Content-Type':'application/json'}
        last='unknown'
        for attempt in range(1,attempts+1):
            try:
                reply=httpx.post(base+'/v1/systemone',headers=headers,json=payload,timeout=60.)
            except httpx.HTTPError as exc:
                last=type(exc).__name__;time.sleep(.5*attempt);continue
            if reply.status_code==200:
                data=reply.json()
                return data.get('answers',{}),data.get('model',model),data.get('usage',{})
            if reply.status_code in (429,502,503,529) and attempt<attempts:
                last='HTTP %d'%reply.status_code;time.sleep(min(10.,.8*2**(attempt-1)));continue
            # The key never appears in a message; only the status and body do.
            raise RuntimeError('TypeSafe HTTP %d: %s'%(reply.status_code,reply.text[:500]))
        raise RuntimeError('TypeSafe request failed after %d attempts (%s)'%(attempts,last))
