#!/usr/bin/env python3
"""Bounded native camera projection fixtures, JSON receipt and schematic PNG.

No disc/archive, game emulator or display. The native constructor, descriptor
copy/setup, full type-2 position update, live callback, lens setter, activation
and projector execute in Unicorn. Settled focus and synthetic actor chains are
explicit fixture inputs, not a GPU render or proof of every moving play.
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
GAME_CAMERA = 0xA82940
# Historical geometry from ASTRA_CAMERA_FAR_REPORT, not current production data.
PRIOR_FAR_VALUES = {
    9: ((0.,0.,-250.),28.,(0.,700.,-1800.)),
    13: ((0.,0.,-250.),28.,(0.,650.,-1600.)),
    15: ((0.,50.,-150.),24.,(0.,800.,-2000.)),
    16: ((0.,0.,-350.),28.,(0.,650.,-1600.)),
    17: ((0.,0.,-250.),28.,(0.,650.,-1600.)),
    18: ((0.,0.,-250.),28.,(0.,650.,-1600.)),
    19: ((0.,0.,-250.),28.,(0.,650.,-1600.)),
}


def prior_far_payload(retail):
    """Only the prior geometry, with native retail pass callbacks, for comparison."""
    buf = bytearray(retail)
    for state, values in PRIOR_FAR_VALUES.items():
        off = camera._offset(buf, camera.FAR_DESCRIPTORS[state])
        buf[off:off+80] = camera.descriptor_bytes(camera.FAR_RETAIL_DESCRIPTORS[state], values)
    for s in camera._sections(buf):
        buf[s.header_offset+36:s.header_offset+56] = camera.section_digest(buf, s)
    return bytes(buf)


def float_word(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def descriptor_inventory(retail, patched):
    """All 58 row/state recipients, including unchanged shared presentation views."""
    table = camera.read_preset_table(retail)
    rows = []
    for preset_row in (0, 1):
        for state, (flags, va) in enumerate(table[preset_row]):
            before = camera._read(retail, va, 80)
            after = camera._read(patched, va, 80)
            rows.append(dict(preset_row=preset_row, state=state, flags=flags, va=hex(va),
                aliases=[i for i, entry in enumerate(table[preset_row]) if entry[1] == va],
                changed=before != after, before=camera.decode_descriptor(before),
                after=camera.decode_descriptor(after),
                field_deltas=[dict(offset=hex(off), before=struct.unpack_from('<f',before,off)[0],
                    after=struct.unpack_from('<f',after,off)[0],
                    delta=struct.unpack_from('<f',after,off)[0]-struct.unpack_from('<f',before,off)[0])
                    for off in range(0,80,4) if before[off:off+4] != after[off:off+4]],
                before_sha256=hashlib.sha256(before).hexdigest(),
                after_sha256=hashlib.sha256(after).hexdigest()))
    return rows


def selection_evidence(retail):
    """Small executable receipts; corpus interpretations are in the report."""
    spans = (
        (0x9FFB6, 42, 'release kind 3/6/other selects states 13/14/15 through 89260'),
        (0x89260, 212, 'native state setter writes B616C0 and resets transition timers'),
        (0xA4A50, 308, 'Standard live growth, lag and authored-record reset'),
        (0xA4C30, 340, 'Far live growth, lag and authored-record reset'),
        (0xA49D0, 128, 'Standard QB pivot and human-gated optional pass zoom'),
        (0xA4BF0, 63, 'Far QB pivot and optional pass zoom'),
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
        self.payload = payload
        self.predicates = {0x12DF0: 0, 0x64BE0: 0, 0x887D0: 0}
        predicates = self.predicates
        # Only peripheral predicates are substituted. Camera math/callbacks
        # execute unmodified or exactly as installed by the production owner.
        def predicate(uc, address, _size, _):
            if address not in predicates:
                return
            r = fixtures.r
            sp = uc.reg_read(r.UC_X86_REG_ESP)
            uc.reg_write(r.UC_X86_REG_EAX, predicates[address])
            uc.reg_write(r.UC_X86_REG_EIP, struct.unpack('<I', uc.mem_read(sp, 4))[0])
            uc.reg_write(r.UC_X86_REG_ESP, sp + 4)
        self.uc.hook_add(fixtures.u.UC_HOOK_CODE, predicate)

    def actors(self, *, direction=1, controlled=True, actor_z=None):
        """Synthetic focus actor, team direction and human-control pointers."""
        uc = self.uc
        base = self.h.AREA + 0x5000
        for va, value in ((0xE5FC00, base), (base, base+0x100),
                (base+0x118, base+0x200), (0xE60280, base+0x300),
                (0xE60284, base+0x400), (base+0x308, base+0x500),
                (base+0x50C, base+0x600), (base+0x330, int(controlled)),
                (base+0x430, int(controlled)), (base+0x30C, base+0x700),
                (base+0x70C, base+0x800), (base+0x804, 0)):
            uc.mem_write(va, struct.pack('<I', value))
        uc.mem_write(base+0x604, struct.pack('<f', direction))
        # Use the same side of both native end-zone reset predicates.
        uc.mem_write(base+0x238, struct.pack('<f', -5000*direction if actor_z is None else actor_z))

    def setup(self, descriptor, *, direction=1, zoom=0, live_updates=0, controlled=True):
        h, uc = self.h, self.uc
        self.actors(direction=direction, controlled=controlled)
        uc.mem_write(0xE5FFF4, struct.pack('<3I',1,0,zoom))
        uc.mem_write(0xB6176C, struct.pack('<I', 0))
        h.execute(uc,0x60090,ecx=0,edx=descriptor,args=(0x3F800000,))
        for _ in range(live_updates):
            callback = struct.unpack('<I', uc.mem_read(GAME_CAMERA+0x434, 4))[0]
            if not callback:
                raise ValueError('live_updates requires a native frame callback')
            h.execute(uc, callback, ecx=GAME_CAMERA)
        return self.project_current(direction=direction)

    def project_current(self, *, direction=1):
        h, uc = self.h, self.uc
        decoded = camera.decode_descriptor(bytes(uc.mem_read(0xA82D30,80)))
        if decoded['type'] != 2:
            raise ValueError('settled fixture requires the native type-2 camera')
        target, lens, offset = decoded['target'],decoded['fov'],decoded['offset']
        target = (target[0],target[1],target[2]*direction)
        offset = (offset[0],offset[1],offset[2]*direction)
        eye = tuple(t+e for t,e in zip(target,offset))
        # Seed settled position and lens, then execute ALL of the native
        # update. This tests target+offset rather than assuming its geometry.
        # Dynamic lag convergence and moving focus remain separate witnesses.
        h.execute(uc,0x66B20,ecx=h.SRC)
        h.execute(uc,0x5E100,ecx=h.SRC,args=(float_word(lens),float_word(1.0)))
        for va, values in ((0xA82BF0, (*eye, 1)), (0xA82C00, (*target, 1)),
                (0xA82C20, (*target,1)), (0xA82C30, (*target,1)), (0xA82C40, (0,0,0,0)),
                (0xA82C60, (*eye,1)), (0xA82C70, (*eye,1)), (0xA82C80, (0,0,0,0)),
                (h.AUX, (0,0,0,1)), (h.AUX+16, (0,0,0,0)),
                (h.AUX+32, (0,0,0,1)), (h.AUX+48, (0,1,0,0))):
            uc.mem_write(va,struct.pack('<4f',*values))
        uc.mem_write(0xA82D94, struct.pack('<f', 1.0))
        h.execute(uc,0x5F760,ecx=0,edx=h.SRC,args=(float_word(1/30), h.AUX,
            h.AUX+16,h.AUX+32,h.AUX+48,float_word(direction)))
        self.eye = h.f(uc,0xA82BF0,3)
        self.target = h.f(uc,0xA82C00,3)
        for actual, expected in zip((*self.eye,*self.target), (*eye,*target)):
            if abs(actual-expected)>0.002:
                raise AssertionError(('native position differs from settled fixture', actual, expected))
        h.activate(uc,source=h.SRC)
        matrix = h.f(uc,wide.ACTIVE_CAMERA_VA,16)
        self.metrics = dict(eye_focus_relative_cm=self.eye, target_focus_relative_cm=self.target,
            focus_distance_cm=math.dist(self.eye,(0,0,0)),
            eye_target_distance_cm=math.dist(self.eye,self.target), lens_word=lens,
            native_lens_scale=h.f(uc,h.SRC+0x270)[0],
            vertical_fov_degrees=math.degrees(2*math.atan(240/abs(matrix[5]))),
            horizontal_fov_degrees=math.degrees(2*math.atan(360/abs(matrix[0]))),
            downward_pitch_degrees=math.degrees(math.atan2(self.eye[1]-self.target[1],
                math.hypot(self.eye[0]-self.target[0], self.eye[2]-self.target[2]))))
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
    table = camera.read_preset_table(retail)
    for build, source in (('retail',retail), ('prior_far',prior_far_payload(retail)), ('new',patched)):
        for aspect in ('4:3',*wide.ASPECTS):
            p = source if aspect=='4:3' else wide.apply(source,aspect)[0]
            projection = Projection(p)
            for preset_row in ((1,) if build=='prior_far' else (0,1)):
                for direction in (1,-1):
                    # All scrimmage, kick, return and preview states. Other
                    # presentation states are covered by the complete inventory
                    # and native table-index tests, not invented scene objects.
                    for state in (1,*range(8,20)):
                        va = table[preset_row][state][1]
                        for zoom in ((0,1) if state==15 else (0,)):
                            for updates in ((0,96) if state in (1,16) else (0,)):
                                decoded = projection.setup(va,direction=direction,zoom=zoom,live_updates=updates)
                                points = {name:projection.point(0,0,z*direction)
                                          for name,z in (('focus_ground',0),('backfield_500cm',-500),('backfield_700cm',-700))}
                                receivers = [dict(position_cm=(x,y,z*direction),
                                    screen_640x480=projection.point(x,y,z*direction))
                                    for x,z in ((-800,500),(800,500),(-1600,2500),(1600,2500),(0,4000))
                                    for y in (0,175)] if state==15 else []
                                rows.append(dict(build=build,preset_row=preset_row,aspect=aspect,state=state,
                                    direction=direction,pass_zoom=zoom,live_updates=updates,
                                    descriptor_after_setup=decoded,metrics=projection.metrics,
                                    receiver_samples=receivers,points_640x480=points,
                                    focus_clearance_px=381-points['focus_ground'][1],
                                    backfield_clearance_px=381-points['backfield_700cm'][1]))
    return dict(schema='nfl2k5_camera_far_proof/v3',experimental=True,runtime_witnessed=False,
        proof='Native CPU projection of synthetic settled focus; no GPU or gameplay witness',
        correction='Type 2 eye = focus + descriptor target + offset; prior v2 fixture omitted target in eye',
        substituted_predicates={'0x12df0':0,'0x64be0':0,'0x887d0':0},
        distance_definition='Euclidean native settled eye relative to the ground focus; offset norm also reported',
        safe_bar_640x480=list(SAFE_BAR),retail_sha256=RETAIL_SHA256,patch_receipt=receipt,
        selection_evidence=selection_evidence(retail),
        descriptor_inventory=descriptor_inventory(retail,patched),
        native_functions=['0x60090','0x66b20','0x66720','0x5f760','0xa4a50','0xa4c30',
                          '0xa49d0','0xa4bf0','0x2ba10','0x5e100','0x66a90','0x2ac80','0x2ab40'],
        rows=rows)


def render(retail, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    patched = camera.apply(retail)[0]
    fig,axes=plt.subplots(4,4,figsize=(18,14),layout='constrained')
    for col,(title,payload,descriptors) in enumerate((
        ('Retail Standard',retail,camera.STANDARD_DESCRIPTORS),
        ('Retail Far',retail,camera.FAR_DESCRIPTORS),
        ('New Standard',patched,camera.STANDARD_DESCRIPTORS),
        ('New Far',patched,camera.FAR_DESCRIPTORS))):
        for row,(state,aspect,zoom) in enumerate(((9,'4:3',0),(9,'16:9',0),(15,'4:3',1),(15,'16:9',1))):
            p = Projection(payload if aspect=='4:3' else wide.apply(payload,aspect)[0])
            ax=axes[row,col];p.setup(descriptors[state],zoom=zoom)
            for z in range(-700,4200,200):
                pts=[p.point(x,0,z) for x in range(-2200,2300,200)]
                ax.plot(*zip(*pts),color='#a9bdb0',lw=.45)
            for x in range(-2200,2400,400):
                pts=[p.point(x,0,z) for z in range(-700,4200,200)]
                ax.plot(*zip(*pts),color='#a9bdb0',lw=.45)
            pts=[p.point(x,0,0) for x in range(-2200,2300,200)]
            ax.plot(*zip(*pts),color='#2471a3',lw=2)
            actors = ((-180,0),(-90,0),(0,0),(90,0),(180,0),(0,-500),(0,-700)) if state==9 else (
                (-800,500),(800,500),(-1600,2500),(1600,2500),(0,4000))
            for x,z in actors:
                foot,head=p.point(x,0,z),p.point(x,175,z)
                ax.plot((foot[0],head[0]),(foot[1],head[1]),color='#aa3434',lw=3)
                ax.scatter(*head,c='#aa3434',s=12)
            ax.add_patch(Rectangle((84,381),476,48,color='#25282a'))
            ax.text(322,407,'Scorebar [84, 381, 560, 429]',ha='center',va='center',color='white',fontsize=8)
            ax.set(xlim=(0,640),ylim=(480,0),aspect='equal',
                   title=f'{title}, {aspect}\n{camera.STATE_LABELS[state]}'+(' / zoom on' if zoom else ''))
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
