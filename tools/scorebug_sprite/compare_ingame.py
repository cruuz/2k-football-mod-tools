"""Compare a player capture to a native CPU preview; write a typed Jev request."""
from pathlib import Path
import argparse
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tools.scorebug_sprite.render import state_for,render
from tools.scorebug_sprite.jev.descriptors import describe
from tools.scorebug_sprite.jev.judge import differences,request,suggestions
from tools.scorebug_sprite.jev.session import Session,write_json,answers
from mod_editor.core.nfl2k5_scorebug_sprite import NativePreview


def compare(screenshot,preview,state,aspect='16:9',output=None):
    actual=describe(screenshot,aspect=aspect)
    with tempfile.TemporaryDirectory(prefix='sprite-compare-') as folder:
        _,receipt=render(preview,state,aspect,Path(folder)/'preview.png')
    rows=differences(actual,receipt['descriptor'])
    result=dict(screenshot=str(screenshot),state=state,fields=rows,calibration=receipt['calibration'],
        jev_request=request(rows,'Retail 243D0 descriptor walk submits plate before down label; owner writes white label vertices. GPU execution is not captured.'),
        cause_proven=False,runtime_witnessed=False)
    if output:write_json(output,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('screenshot',type=Path);p.add_argument('--away',required=True);p.add_argument('--home',required=True)
    p.add_argument('--state',required=True);p.add_argument('--aspect',choices=['16:9','4:3'],default='16:9');p.add_argument('--possession',choices=['away','home'])
    p.add_argument('--output',type=Path,default=Path('scorebug_comparison.json'));p.add_argument('--jev-response',type=Path);p.add_argument('--jev-live',action='store_true')
    p.add_argument('--report',type=Path,default=ROOT/'reports/b72_s3');a=p.parse_args()
    r=compare(a.screenshot,NativePreview(),state_for(a.state,a.away,a.home,a.possession),a.aspect,a.output)
    answer=Session(a.report).replay(r['jev_request']) if a.jev_live else answers(json.loads(a.jev_response.read_text())) if a.jev_response else None
    print('field                 core luminance delta   residual')
    for row in r['fields']:print(f"{row['field']:22} {row['core_delta']:8.2f}             {row['residual']}")
    if answer:
        r['jev']=suggestions(answer);write_json(a.output,r)
        for field,row in r['jev'].items():
            if row['classification']!='none':print(field,row['classification'],'inspect',', '.join(row['inspect_keys']))
    else:print('Jev request saved in',a.output,'(use MCP or --jev-live outside the sandbox).')
    print('Calibration FAIL; cause remains unproved. No automatic edit.')

if __name__=='__main__':main()
