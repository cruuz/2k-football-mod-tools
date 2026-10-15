"""Dynamic display ratings with a retail-like spread and native sim isolation.

Only four confirmed UI CALL instructions are redirected. C4830/C4860/C48A0
and every simulation/AI caller keep their original bytes. Raw modern scores
are computed on demand and mapped through fixed, strictly increasing quartile
curves calibrated against the USA retail roster. See team_ratings.md.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = 'nfl2k5_team_ratings_display'
CODE_SIZE = 512
RO_SIZE = 512
REQUESTS = ((OWNER, 'code', CODE_SIZE, 16), (OWNER, 'read_only', RO_SIZE, 16))
OFFENSE = ((0,1,60),(7,1,20),(3,2,40),(9,1,20),(12,1,12),(13,1,24),(14,1,24),(8,1,4))
DEFENSE = ((16,1,60),(15,1,40),(11,1,20),(4,2,50),(5,1,15),(6,1,15))
# Fixed raw-score -> retail-score curves. Interior anchors are min/Q1/Q2/Q3/max
# of the accepted refreshed roster and the pinned retail roster, respectively.
# 0/1 endpoints keep later franchise changes dynamic across the complete range.
KNOTS = (
    ((0.,0.),(.746671617,.720623255),(.789927855,.759062171),(.817135781,.821235657),
     (.838349864,.876917675),(.885806680,.955051303),(1.,1.)),
    ((0.,0.),(.705035031,.716373444),(.746923089,.772519752),(.754848450,.800752133),
     (.781544879,.889050111),(.820900202,.967114985),(1.,1.)),
    ((0.,0.),(.743069828,.767066181),(.773852915,.832994401),(.790151209,.854142606),
     (.807515517,.882709712),(.839247048,.938666284),(1.,1.)),
)
RAW_OFFSETS = (0, 64, 128)
DISPLAY_OFFSETS = (192, 224, 256)
MAP_OFFSET = 320
SPREAD_OFFSET = 288
CURVE_SIZE = 56
NATIVE_ROUTINES = (
    (0xC4830,48,'797813dbbf9c1be6b50f43d8c939d0c20293ea22df3fcd5a0818aa9fec3ccdff'),
    (0xC4860,64,'861789af6c92d77f49c2b5b81fcffd96993c9e739c328e26646880830883560d'),
    (0xC48A0,144,'2ccf4df3d8530611dc16202bb80d45f5ff908ec2b9d0b8c27e7a235cec6fe263'),
)
GUARDS = NATIVE_ROUTINES + (
    (0xC45A0,164,'869e8796c1149d642fa45905469bd0484a767a55c3d84197e4b8c6a336794148'),
    (0xC4400,413,'300512909be3f527884f0611627b73c60d06577fc2dd059d684c5831b7589db5'),
    (0x246D80,16,'14151a04d17c38132fedfdc5f87173ccf04fb8d55f435cdc7ca1ef0c7bb6b03f'),
)
# Complete direct CALL/JMP census: (instruction VA, native target, classification).
# Internal OVR calls are retained with the native simulation getter.
CALLERS = (
    (0x5837B,0xC4830,'AI: shared team-strength comparator'),
    (0xC48A6,0xC4830,'AI: native overall dependency'),
    (0x1CF37A,0xC4830,'simulation: live-game initialization'),
    (0x1CF38B,0xC4830,'simulation: live-game initialization'),
    (0x218CE0,0xC4830,'AI: trade unit-strength evaluation'),
    (0x31F22C,0xC4830,'UI: team-select/controller panel'),
    (0x583B7,0xC4860,'AI: shared team-strength comparator'),
    (0xC48B1,0xC4860,'AI: native overall dependency'),
    (0x218D10,0xC4860,'AI: trade unit-strength evaluation'),
    (0x31F23D,0xC4860,'UI: team-select/controller panel'),
    (0x34BB60,0xC4860,'UI: overall-defense spreadsheet column'),
    (0x584E6,0xC48A0,'AI: shared team-strength comparator'),
    (0xD23E0,0xC48A0,'simulation: matchup-strength predicate'),
    (0xD23EB,0xC48A0,'simulation: matchup-strength predicate'),
    (0x1062BF,0xC48A0,'simulation: match initialization'),
    (0x1062D3,0xC48A0,'simulation: match initialization'),
    (0x115C03,0xC48A0,'AI: league record/strength selection'),
    (0x31F24E,0xC48A0,'UI: team-select/controller panel'),
)
# Only these four instructions may be rewritten, all five-byte direct CALLs.
SITES = ((0x31F22C,5,0), (0x31F23D,5,1), (0x31F24E,5,2), (0x34BB60,5,1))


def map_score(value, unit):
    """Reference mapping; native code uses the same float32 knot table."""
    value = max(0., min(1., value))
    points = [struct.unpack('<ff', struct.pack('<ff', *p)) for p in KNOTS[unit]]
    for (x0,y0),(x1,y1) in zip(points, points[1:]):
        if value <= x1:
            return y0 + (value-x0)*(y1-y0)/(x1-x0)
    return 1.


def table_bytes():
    weights = b''.join(struct.pack('<HBBIfff',w,n,p,0x246D80,.10,0.,1.)
                       for p,n,w in OFFENSE+DEFENSE).ljust(SPREAD_OFFSET,b'\0')
    curves = b''.join(struct.pack('<ff',*p) for curve in KNOTS for p in curve)
    return (weights+curves).ljust(RO_SIZE,b'\0')


def code_for(code_va, table_va):
    buf = bytearray(b'\xcc'*CODE_SIZE)

    def put(offset, a, limit):
        code = a.assemble()
        if len(code)>limit: raise ValueError('Display rating code exceeds allocation')
        buf[offset:offset+len(code)] = code

    a = _Asm(code_va)
    a.b('53 8b d9 ba 08000000')
    a.call(0xC3CB0)
    a.b('85 c0 b8 07000000')
    a.j8('74','counted')
    a.b('40')
    a.label('counted')
    a.b('b9'+struct.pack('<I',table_va).hex())
    a.call(0xC45A0)
    a.b('5b c3')
    put(0,a,64)

    a = _Asm(code_va+64)
    a.b('53 8b d9 b8 06000000 b9'+struct.pack('<I',table_va+160).hex())
    a.call(0xC45A0)
    a.b('5b c3')
    put(64,a,64)

    a = _Asm(code_va+128)
    a.b('51 56 8b f1')
    a.call(code_va)
    a.b('d9 5c 24 04 8b ce')
    a.call(code_va+64)
    a.b('d8 44 24 04 d8 0d 84414e00 5e 59 c3')
    put(128,a,64)

    for unit,offset in enumerate(DISPLAY_OFFSETS):
        a = _Asm(code_va+offset)
        a.call(code_va+RAW_OFFSETS[unit])
        a.b('ba'+struct.pack('<I',table_va+SPREAD_OFFSET+unit*CURVE_SIZE).hex())
        a.jmp_abs(code_va+MAP_OFFSET)
        put(offset,a,32)

    # ST0 raw score, EDX curve. Clamp to [0,1], find its interval, interpolate.
    # Locals contain input and temporary product; no shared writable scratch.
    a = _Asm(code_va+MAP_OFFSET)
    a.b('83 ec 04 d9 1c 24 d9 02 d8 1c 24 df e0 f6 c4 01')
    a.j8('75','positive')             # 0 < input
    a.b('d9 ee')                      # FLDZ
    a.j8('eb','done')
    a.label('positive')
    a.b('d9 e8 d8 1c 24 df e0 f6 c4 01')
    a.j8('75','one')                  # 1 < input
    a.label('loop')
    a.b('d9 42 08 d8 1c 24 df e0 f6 c4 01')
    a.j8('74','found')                # next x >= input
    a.b('83 c2 08')
    a.j8('eb','loop')
    a.label('found')
    a.b('d9 04 24 d8 22 d9 42 0c d8 62 04 de c9 d9 42 08 d8 22 de f9 d8 42 04')
    a.j8('eb','done')
    a.label('one')
    a.b('d9 e8')
    a.label('done')
    a.b('83 c4 04 c3')
    put(MAP_OFFSET,a,CODE_SIZE-MAP_OFFSET)
    return bytes(buf)


def allocations(payload):
    found = [r for r in space.layout(payload)['allocations'] if r['owner']==OWNER] if space.status(payload)=='applied' else []
    if not found: return {}
    rows = {r['kind']:r for r in found}
    if len(found)!=2 or set(rows)!= {'code','read_only'} or any(
            (rows[k]['size'],rows[k]['align'])!=(size,16)
            for k,size in (('code',CODE_SIZE),('read_only',RO_SIZE))):
        raise ValueError('Foreign display-rating allocation')
    return rows


def allocation(payload):
    return allocations(payload).get('read_only')


def entrypoints(payload, *, raw=False):
    rows = allocations(payload)
    if not rows: raise ValueError('Display ratings are not allocated')
    return tuple(rows['code']['va']+i for i in (RAW_OFFSETS if raw else DISPLAY_OFFSETS))


def site_bytes(site, target):
    return b'\xe8'+struct.pack('<i',target-site-5)


def _state(payload, *, require_pools=True):
    image = XbeImage(payload)
    if space.status(payload)=='foreign': raise ValueError('Foreign executable geometry or seals')
    rows = allocations(payload)
    for va,n,digest in GUARDS:
        if hashlib.sha256(image.read(va,n)).hexdigest()!=digest:
            raise ValueError(f'Native rating dependency changed at {va:#x}; rebuild from the unmodified base, not d1eb870e')
    from .nfl2k5_position_pools import CHAIN_INDEX_VA, chain_index_bytes
    if require_pools and image.read(CHAIN_INDEX_VA,16)!=chain_index_bytes():
        raise ValueError('Team ratings require modern position pools')
    for site,target,kind in CALLERS:
        if kind.startswith('UI:'): continue
        opcode=b'\xe9' if site in (0x5837B,0x584E6,0x218CE0,0x218D10) else b'\xe8'
        if image.read(site,5)!=opcode+struct.pack('<i',target-site-5):
            raise ValueError(f'Non-UI rating caller changed at {site:#x}')
    states=set()
    for site,n,unit in SITES:
        got=image.read(site,n)
        native=site_bytes(site,NATIVE_ROUTINES[unit][0])
        after=site_bytes(site,rows['code']['va']+DISPLAY_OFFSETS[unit]) if rows else None
        states.add('retail' if got==native else 'applied' if got==after else 'foreign')
    if len(states)!=1 or 'foreign' in states: raise ValueError('Mixed or foreign display-rating callers')
    state=states.pop()
    if rows:
        ro=image.read(rows['read_only']['va'],RO_SIZE)
        code=image.read(rows['code']['va'],CODE_SIZE)
        if ro!=(table_bytes() if state=='applied' else bytes(RO_SIZE)) or code!=(
                code_for(rows['code']['va'],rows['read_only']['va']) if state=='applied' else b'\xcc'*CODE_SIZE):
            raise ValueError('Foreign display-rating owner contents')
    return state,rows


def status(payload):
    try: return _state(payload,require_pools=False)[0]
    except (ValueError,KeyError,IndexError,struct.error): return 'foreign'


def apply(payload):
    state,rows=_state(payload)
    original=payload
    if state=='applied':
        return payload,dict(owner=OWNER,changed_bytes=0,already_applied=True,simulation_native=True)
    if not rows:
        payload,_=space.extend_scaleout(payload,REQUESTS) if space.status(payload)=='applied' else space.apply(payload,REQUESTS,scaleout=True)
        rows=allocations(payload)
    code_va,table_va=rows['code']['va'],rows['read_only']['va']
    sites=[(f'UI_rating_{site:x}',site,site_bytes(site,NATIVE_ROUTINES[unit][0]),
            site_bytes(site,code_va+DISPLAY_OFFSETS[unit])) for site,_n,unit in SITES]
    payload,_=space.install_read_only(payload,OWNER,table_bytes())
    payload,_=space.install_code(payload,OWNER,code_for(code_va,table_va))
    payload,_=rdata.apply(payload,sites,OWNER)
    if status(payload)!='applied': raise ValueError('Display-rating readback failed')
    return payload,dict(owner=OWNER,changed_bytes=sum(a!=b for a,b in zip(original,payload)),
                        already_applied=False,table_va=hex(table_va),code_va=hex(code_va),
                        dynamic=True,simulation_native=True,ui_callers=len(SITES))
