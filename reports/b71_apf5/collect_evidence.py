"""Extract only numeric/derived witnesses from the latest successful native run."""
import hashlib
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
from mod_editor.core import apf2k8_fourth_down as model
folder=Path(__file__).parent
records=[json.loads(line) for line in (folder/'commands.jsonl').read_text().splitlines()]
record=next(row for row in sorted(records,key=lambda r:r['started_utc'],reverse=True) if row['command'][-1]=='tests/mod_editor/test_apf_fourth_down_native.py' and row['exit_code']==0)
log=root/record['log']; text=log.read_text()
assert text.rstrip().endswith('OK') and 'Ran 6 tests' in text
parsed={}
for line in text.splitlines():
    if 'APF5_' not in line:continue
    key,_,value=line[line.index('APF5_'):].partition(' ')
    try:value=json.loads(value)
    except ValueError:pass
    parsed.setdefault(key,[]).append(value)
assert len(parsed['APF5_PREVIEW'])==6
assert sum(row['cases'] for row in parsed['APF5_PREVIEW'])==2016
assert parsed['APF5_RETAIL_EQUIVALENCE']==[360]
assert len(parsed['APF5_COMPLETE_CALL'])==2
assert len(parsed['APF5_DRAW_CHAIN'])==2
receipt={'scope':'Bounded offline; all match behavior UNWITNESSED','source_log':record['log'],
         'source_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'native':parsed,
         'patches':[dict(model.PatchDocument(p).receipt,
                    default_toml_sha256=hashlib.sha256(model.PatchDocument(p).as_toml().encode()).hexdigest(),
                    authored_words=[{'address':f'{a:08X}','value':f'{v:08X}'} for a,v in model.PatchDocument(p).words])
                    for p in model.PROFILES]}
(folder/'native_receipts.json').write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
print(json.dumps({'source_log':record['log'],'preview_comparisons':2016,'retail_equivalence_comparisons':360,
                  'complete_calls':2,'draw_chains':2,'gameplay':'UNWITNESSED'},indent=2))
