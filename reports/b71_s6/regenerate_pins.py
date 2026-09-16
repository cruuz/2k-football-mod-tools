from pathlib import Path
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/"tools")]
from nfl2k5_scorebug_exact import Build,compiler_pins
from mod_editor.core import nfl2k5_scorebug_resources as resources
PACK=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0')
XBE=PACK.parents[1]/'default.xbe'
Path('.scratch').mkdir(exist_ok=True)
build=Build(PACK,XBE)
try:
    pins=compiler_pins(build)
    pins['CLOCK_FONT_SHA256']=hashlib.sha256(resources.clock_font_span(build.view)).hexdigest()
finally: build.close()
pins['MNF_VERSION']='scorebug-mnf-2026-v4'
p=Path('mod_editor/core/nfl2k5_scorebug_resources.py');s=p.read_text()
for key,value in pins.items():
    s,n=re.subn(r'^'+re.escape(key)+r' = .*$',lambda m:key+' = '+repr(value),s,flags=re.M)
    assert n==1,(key,n)
p.write_text(s,newline='\n')
Path('reports/b71_s6/compiler_pins.json').write_text(json.dumps(pins,indent=2)+'\n')
print(json.dumps(pins,indent=2))
