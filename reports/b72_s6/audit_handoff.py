"""Prepare/replay the installed handoff recipe with actual MCP responses."""
from pathlib import Path
import json
import runpy
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
RECIPES=Path('/home/noah/ai-stack/jev/recipes')
sys.path.insert(0,str(RECIPES))
import jevlib

class Ready(Exception):pass

def request(states,questions,**kwargs):
    (OUT/'handoff_request.json').write_text(json.dumps(dict(states=states,questions=questions),indent=2)+'\n')
    raise Ready

def replay(states,questions,**kwargs):
    expected=json.loads((OUT/'handoff_request.json').read_text())
    assert states==expected['states'] and questions==expected['questions']
    response=json.loads((OUT/'handoff_response.json').read_text())
    assert not response['errors']
    return response['answers']

jevlib.batch=replay if '--replay' in sys.argv else request
sys.argv=[str(RECIPES/'factcheck.py'),'--claims',str(OUT/'handoff_audited.md'),
          '--evidence',str(OUT/'GPU_FINDINGS.md'),str(OUT/'VALIDATION.md'),str(OUT/'NEXT_CAPTURE.md'),
          '--out',str(OUT/'handoff_factcheck.md')]
try:runpy.run_path(str(RECIPES/'factcheck.py'),run_name='__main__')
except Ready:print('Prepared handoff recipe request.')
