"""PROVED OFFLINE: native owner execution and software display crops, never game captures."""
from pathlib import Path
import json
import sys
import tempfile
import struct
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from tools.scorebug_sprite import gpu,xemu_model
import nfl2k5_scorebug_projection as projection
SCRATCH=Path('/media/noah/Storage/.b76-research/sb/sb2')
OUT=Path(__file__).resolve().parent

def render(preview,state,wide=True):
    g,c=preview.capture(state,wide); mode=preview.modes[wide]
    try:
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'hud.png'
            projection.render_native(c['live_decoded'],mode['atlas'],preview.fonts,g,p,texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#3a6c34'),gpu_pipeline=xemu_model.Pipeline(gpu.capture_state(c)))
            size=(1920,1080) if wide else (1440,1080)
            im=Image.open(p).convert('RGB').crop((0,16,640,464)).resize(size,Image.Resampling.LANCZOS)
        comp=mode['compiled']; colours={}
        for q in comp.quads:
            if q['name'] in ('away_wing','home_wing','plate','red','away_logo','home_logo'):
                colours[q['name']]=hex(struct.unpack_from('<I',c['live_decoded'],0x2d20+q['vertex']*10)[0])
        return im,dict(state=sprite.normalize_state(state),colours=colours,appended_bytes=mode['volume']['appended_bytes'],runtime_witnessed=False,calibration_passed=False)
    finally:c['machine'].close()

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'before'; preview=sprite.NativePreview()
    for side in ('away','home'):
        st=dict(away='PHI',home='CHI',possession=side,away_score=0,home_score=7,quarter=1,clock=476,play_clock=40,down=1,distance=10,broadcast='monday_night',away_record=[1,1,0],home_record=[2,0,0])
        im,r=render(preview,st);im.save(SCRATCH/(mode+'_'+side+'.png'))
        (OUT/(mode+'_'+side+'.json')).write_text(json.dumps(r,indent=2)+'\n')
    print(mode,'done',flush=True)
