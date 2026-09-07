#!/usr/bin/env python3
"""Bounded native camera projection fixtures, JSON receipt and schematic PNG.

No disc/archive, game emulator or display. The native constructor, descriptor
copy/setup, basis installer, lens setter, activation and projector execute in
Unicorn. The normalized look direction and synthetic ground grid are explicit
fixture inputs, not a GPU render or proof of every moving focus/lag state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_camera as camera, nfl2k5_widescreen as wide
from tests.mod_editor import test_nfl2k5_widescreen_polish as fixtures

RETAIL_SHA256 = '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
SAFE_BAR = (84,381,560,429)


def selection_evidence(retail):
    """Small executable receipts; corpus interpretations are in the report."""
    spans = (
        (0x64991, 5, 'unconditional common-game call to camera initializer'),
        (0xA55A0, 80, 'common camera initializer and final selection jump'),
        (0xA5490, 83, 'controller/session option to active row'),
        (0xA572D, 39, 'active row times 29 plus state indexes descriptor table'),
        (0xE2E00, 50, '736-byte settings export/import helpers'),
        (0x2C6960, 48, 'Options writes session index and uses native setter'),
        (0x2C6A35, 79, 'temporary menu snapshot of seven camera words'),
        (0x2C6A90, 97, 'Cancel restores snapshot and tail-calls Options setter'),
    )
    records=[]
    for va,size,meaning in spans:
        raw=camera._read(retail,va,size)
        records.append(dict(va=hex(va),size=size,meaning=meaning,
                            sha256=hashlib.sha256(raw).hexdigest(),bytes=raw.hex()))
    text=next(s for s in camera._sections(retail) if s.virtual_address==0x11000)
    code=retail[text.raw_offset:text.raw_offset+text.raw_size]
    targets={0xE2E20:[],0xA55A0:[],0xA5B20:[]}
    for off in range(len(code)-4):
        if code[off] in (0xE8,0xE9):
            target=text.virtual_address+off+5+struct.unpack_from('<i',code,off+1)[0]
            if target in targets: targets[target].append(hex(text.virtual_address+off))
    return dict(spans=records,
        encoded_direct_call_jump_census={hex(va):sites for va,sites in targets.items()},
        census_limit='Byte scan of retail text E8/E9 rel32, reviewed at these sites; not an indirect-call census',
        settings_blob=dict(base='0xe5ff80',size=736,camera_offset='0x70',
                           qb_pivot_offset='0x74',runner_pivot_offset='0x78',pass_zoom_offset='0x7c',
                           custom_distance_offset='0x80',custom_angle_offset='0x84',custom_height_offset='0x88'),
        descriptor_deltas={str(state):dict(va=hex(camera.FAR_DESCRIPTORS[state]),
            target_delta=[b-a for a,b in zip(camera.FAR_RETAIL_VALUES[state][0],values[0])],
            lens_delta=values[1]-camera.FAR_RETAIL_VALUES[state][1],
            eye_delta=[b-a for a,b in zip(camera.FAR_RETAIL_VALUES[state][2],values[2])])
            for state,values in camera.PRESETS['far_look'].items()})


class Projection:
    def __init__(self, payload):
        self.h = fixtures.RetailExecutionTests()
        self.uc = self.h.load(payload)

    def setup(self, descriptor, *, direction=1, zoom=0, pullback=1):
        h, uc = self.h, self.uc
        uc.mem_write(0xE5FFF4, struct.pack('<3I',1,0,zoom))
        # The actual descriptor copier invokes the Far setup callback, including
        # retail Pass Play Zoom Out's separate override when it is enabled.
        h.execute(uc,0x60090,ecx=0,edx=descriptor,args=(0x3F800000,))
        decoded = camera.decode_descriptor(bytes(uc.mem_read(0xA82D30,80)))
        target, lens, eye = decoded['target'],decoded['fov'],decoded['offset']
        target = (target[0],target[1],target[2]*direction)
        eye = (eye[0],eye[1]*pullback,eye[2]*pullback*direction)
        forward = tuple(t-e for t,e in zip(target,eye))
        length = math.sqrt(sum(x*x for x in forward))
        forward = tuple(x/length for x in forward)
        right = (float(direction),0.,0.)
        up = (0.,forward[2]*direction,-forward[1]*direction)
        h.execute(uc,0x66B20,ecx=h.SRC)
        for va,v in ((h.AUX,eye),(h.AUX+16,forward),(h.AUX+32,up),(h.AUX+48,right)):
            uc.mem_write(va,struct.pack('<4f',*v,1 if va==h.AUX else 0))
        h.execute(uc,0x2BA10,ecx=h.SRC,edx=h.AUX,args=(h.AUX+16,h.AUX+32,h.AUX+48))
        h.execute(uc,0x66A90,ecx=h.SRC,args=(struct.unpack('<I',struct.pack('<f',lens/18))[0],))
        h.activate(uc,source=h.SRC)
        return decoded

    def point(self, x, y, z):
        h,uc = self.h,self.uc
        uc.mem_write(h.POINT,struct.pack('<4f',x,y,z,1))
        h.execute(uc,wide.PROJECT_VA,ecx=wide.ACTIVE_CAMERA_VA,edx=h.POINT,args=(h.OUT,))
        result = h.f(uc,h.OUT,4)
        h.consume_reciprocal(uc)
        # Native framebuffer is 720x480. The requested bar witness is 640x480.
        # Only x changes in this presentation normalization.
        return [result[0]*640/720,result[1]]


def prove(retail):
    if len(retail)!=11948032 or hashlib.sha256(retail).hexdigest()!=RETAIL_SHA256:
        raise ValueError('the pinned USA executable is required')
    patched, receipt = camera.apply(retail)
    rows=[]
    for aspect in ('4:3',*wide.ASPECTS):
        p = patched if aspect=='4:3' else wide.apply(patched,aspect)[0]
        projection = Projection(p)
        for direction in (1,-1):
            for state,va in camera.FAR_DESCRIPTORS.items():
                for zoom in ((0,1) if state==15 else (0,)):
                    for pullback in ((1.,2.) if state==16 else (1.,)):
                        decoded = projection.setup(va,direction=direction,zoom=zoom,pullback=pullback)
                        points = {name:projection.point(0,0,z*direction)
                                  for name,z in (('focus_ground',0),('backfield_500cm',-500),('backfield_700cm',-700))}
                        rows.append(dict(aspect=aspect,state=state,direction=direction,pass_zoom=zoom,
                            pullback=pullback,descriptor_after_setup=decoded,points_640x480=points,
                            focus_clearance_px=381-points['focus_ground'][1],
                            backfield_clearance_px=381-points['backfield_700cm'][1]))
    return dict(schema='nfl2k5_camera_far_proof/v2',experimental=True,runtime_witnessed=False,
        proof='Native CPU projection of synthetic settled focus; no GPU or gameplay witness',
        safe_bar_640x480=list(SAFE_BAR),retail_sha256=RETAIL_SHA256,patch_receipt=receipt,
        selection_evidence=selection_evidence(retail),
        native_functions=['0x60090','0x66b20','0x66720','0x2ba10','0x66a90','0x2ac80','0x2ab40'],
        rows=rows)


def render(retail, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    patched = camera.apply(retail)[0]
    fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    for col,(title,payload,descriptors) in enumerate((
        ('Retail Far, 4:3',retail,camera.FAR_DESCRIPTORS),
        ('Revised Far, 4:3',patched,camera.FAR_DESCRIPTORS),
        ('Revised Far, widescreen v3',wide.apply(patched)[0],camera.FAR_DESCRIPTORS))):
        p = Projection(payload)
        for row,state in enumerate((9,16)):
            ax=axes[row,col];p.setup(descriptors[state])
            for z in range(-700,2200,100):
                pts=[p.point(x,0,z) for x in range(-1400,1500,100)]
                ax.plot(*zip(*pts),color='#a9bdb0',lw=.45)
            for x in range(-1200,1400,200):
                pts=[p.point(x,0,z) for z in range(-700,2200,100)]
                ax.plot(*zip(*pts),color='#a9bdb0',lw=.45)
            pts=[p.point(x,0,0) for x in range(-1400,1500,100)]
            ax.plot(*zip(*pts),color='#2471a3',lw=2,label='Line of scrimmage / focus plane')
            for x,z in ((-180,0),(-90,0),(0,0),(90,0),(180,0),(0,-500),(0,-700)):
                foot,head=p.point(x,0,z),p.point(x,175,z)
                ax.plot((foot[0],head[0]),(foot[1],head[1]),color='#aa3434',lw=3)
                ax.scatter(*head,c='#aa3434',s=12)
            ax.add_patch(Rectangle((84,381),476,48,color='#25282a'))
            ax.text(322,407,'Scorebar [84, 381, 560, 429]',ha='center',va='center',color='white',fontsize=9)
            ax.set(xlim=(0,640),ylim=(480,0),aspect='equal',title=f'{title}\n{camera.STATE_LABELS[state]}')
            ax.set_facecolor('#eef4ef')
            ax.tick_params(labelsize=8)
    fig.suptitle('Native projection fixtures, synthetic field and players. EXPERIMENTAL / UNWITNESSED.',fontsize=14)
    fig.savefig(path,dpi=140)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xbe',type=Path,default=fixtures.XBE)
    parser.add_argument('--json',type=Path,required=True)
    parser.add_argument('--png',type=Path)
    args=parser.parse_args()
    # Stat before read: this tool must never accept a disc/pack by accident.
    if args.xbe.stat().st_size!=11948032: parser.error('expected 11,948,032-byte retail XBE')
    retail=args.xbe.read_bytes()
    result=prove(retail)
    args.json.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if args.png: render(retail,args.png)
    print(f"{len(result['rows'])} bounded projection cases; no gameplay witness")


if __name__=='__main__': main()
