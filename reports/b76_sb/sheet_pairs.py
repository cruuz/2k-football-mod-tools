"""Beta 76 sb: the TV-versus-preview state sheets. Broadcast frames are read-only local evidence (the Giants at Rams
off-air frames and the Broncos at Chiefs 1 fps frames); nothing from them is written into the repository but the
small bar crops of the sheets."""
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw
GR='/home/noah/2k-worktrees/.b76-session/scratchpad/b76/obs/frames/'
BC='/media/noah/Storage/Broadcast refs/espn-2026-broncos-chiefs-full/frames_1s/'
R=sys.argv[1]; out=sys.argv[2]; suffix=sys.argv[3] if len(sys.argv)>3 else ''
states=json.load(open(Path(__file__).with_name('sheet_states.json')))
def ref(r): return GR+r[3:] if r.startswith('GR:') else BC+'s_%05d.jpg'%(int(r[3:])+1)
BOX=(430,892,1490,1058); W=BOX[2]-BOX[0]; H=BOX[3]-BOX[1]; S=0.62
w,h=int(W*S),int(H*S)
sheet=Image.new('RGB',(w*2+6,(h+16)*len(states)),(24,24,24)); d=ImageDraw.Draw(sheet)
for i,(name,r,st) in enumerate(states):
    tv=Image.open(ref(r)).convert('RGB').crop(BOX).resize((w,h),Image.LANCZOS)
    ours=Image.open(R+'/'+name+suffix+'_display.png').convert('RGB')
    if ours.size!=(1920,1080): ours=ours.resize((round(ours.width*1080/ours.height),1080),Image.LANCZOS)
    ox=(ours.width-1920)//2
    ours=ours.crop((BOX[0]+ox,BOX[1],BOX[2]+ox,BOX[3])).resize((w,h),Image.LANCZOS)
    y=i*(h+16); d.text((4,y+2),'%s   TV (left, %s)   |   ours, native preview model (right)'%(name,r),fill=(255,255,0))
    sheet.paste(tv,(0,y+16)); sheet.paste(ours,(w+6,y+16))
sheet.save(out,quality=88); print(out,sheet.size)
