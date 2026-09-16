import json
from pathlib import Path
from nfl2k5_scorebug_exact import Build
pack=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0')
out=Path('.scratch/combined-render');out.mkdir(parents=True,exist_ok=True)
build=Build(pack,pack.parents[1]/'default.xbe')
try:
    for wide in (False,True):
        name='wide' if wide else '43'
        geometry=build.render(out/(name+'.png'),runtime=True,widescreen=wide)
        (out/(name+'.json')).write_text(json.dumps(geometry,indent=2,default=str)+'\n')
        print(name,'rendered; private fonts:',[x['name'] for x in geometry.get('private_fonts',[])],flush=True)
finally:build.close()
