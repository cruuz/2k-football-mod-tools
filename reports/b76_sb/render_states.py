"""Beta 76 sb: the TV-versus-preview state sheets. Broadcast frames are read-only local evidence (the Giants at Rams
off-air frames and the Broncos at Chiefs 1 fps frames); nothing from them is written into the repository but the
small bar crops of the sheets."""
import json
import os
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
GR='/home/noah/2k-worktrees/.b76-session/scratchpad/b76/obs/frames/'
BC='/media/noah/Storage/Broadcast refs/espn-2026-broncos-chiefs-full/frames_1s/'
R=sys.argv[1]; aspect=sys.argv[2] if len(sys.argv)>2 else '16:9'
states=json.load(open(Path(__file__).with_name('sheet_states.json')))
def ref(r): return GR+r[3:] if r.startswith('GR:') else BC+'s_%05d.jpg'%(int(r[3:])+1)
def one(row):
    name,r,st=row; st=dict(st,broadcast='monday_night')
    if st['away']=='NYG': st.update(away_record=[1,0,0],home_record=[0,1,0])
    out=os.path.join(R,name+('_43' if aspect=='4:3' else '')+'.png')
    p=subprocess.run([sys.executable,'-m','mod_editor.core.nfl2k5_scorebug_sprite','preview','--screenshot',ref(r),'--aspect',aspect,'--output',out,'--state',json.dumps(st)],capture_output=True,text=True)
    return name,p.returncode,p.stderr[-300:]
with ThreadPoolExecutor(6) as ex:
    for n,rc,err in ex.map(one,states): print(n,rc,err if rc else '')
