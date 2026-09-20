"""Run the installed diff-gate recipe, routing its Jev request through MCP."""
from pathlib import Path
import json
import os
import runpy
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
RECIPES=Path('/home/noah/ai-stack/jev/recipes')
sys.path.insert(0,str(RECIPES))
import jevlib

class RequestReady(Exception):pass

def request(states,questions,**kwargs):
    (OUT/'jev_gate_request.json').write_text(json.dumps(dict(states=states,questions=questions),indent=2)+'\n')
    raise RequestReady

def replay(states,questions,**kwargs):
    expected=json.loads((OUT/'jev_gate_request.json').read_text())
    assert states==expected['states'] and questions==expected['questions']
    response=json.loads((OUT/'jev_gate_response.json').read_text())
    assert not response['totals']['errors']
    return [r['answers'] for r in response['results']]

jevlib.batch=replay if '--replay' in sys.argv else request
os.environ['GIT_DIR']=str(ROOT/'.scratch/b72-s8.git')
os.environ['GIT_WORK_TREE']=str(ROOT)
sys.argv=[str(RECIPES/'jev_diff_gate.py'),'c5134e232','HEAD','--repo',str(ROOT),
          '--out',str(OUT/'jev_diff_gate.md'),'--json',str(OUT/'jev_diff_gate.json')]
try:runpy.run_path(str(RECIPES/'jev_diff_gate.py'),run_name='__main__')
except RequestReady:print('Prepared the real recipe request; no fabricated model responses.')
