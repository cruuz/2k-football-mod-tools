"""Run the installed diff-gate recipe unchanged via logged Jev MCP answers."""
from pathlib import Path
import argparse
import json
import os
import runpy
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
RECIPES=Path('/home/noah/ai-stack/jev/recipes')
p=argparse.ArgumentParser()
p.add_argument('--base',default='origin/main')
p.add_argument('--replay',action='store_true')
a=p.parse_args()
tag='origin' if a.base=='origin/main' else 'own'
sys.path.insert(0,str(RECIPES))
import jevlib

class Ready(Exception):pass

def request(states,questions,**kwargs):
    (OUT/(tag+'_gate_request.json')).write_text(json.dumps(dict(states=states,questions=questions),indent=2)+'\n')
    raise Ready

def replay(states,questions,**kwargs):
    expected=json.loads((OUT/(tag+'_gate_request.json')).read_text())
    assert states==expected['states'] and questions==expected['questions']
    response=json.loads((OUT/(tag+'_gate_response.json')).read_text())
    assert not response['errors']
    return response['answers']

jevlib.batch=replay if a.replay else request
os.environ['GIT_DIR']=str(ROOT/'.scratch/b72-s9.git')
os.environ['GIT_WORK_TREE']=str(ROOT)
sys.argv=[str(RECIPES/'jev_diff_gate.py'),a.base,'HEAD','--repo',str(ROOT),
          '--out',str(OUT/(tag+'_diff_gate.md')),'--json',str(OUT/(tag+'_diff_gate.json'))]
try:runpy.run_path(str(RECIPES/'jev_diff_gate.py'),run_name='__main__')
except Ready:print('Prepared actual recipe request:',tag)
