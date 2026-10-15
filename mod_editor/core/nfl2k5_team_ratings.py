"""Dynamic modern OFF/DEF/OVR, using native player overalls and roster chains.

The three public getters are replaced in place. Native C4400/C45A0 still
walk the current roster on every call. No team identifiers or frozen ratings
are installed. The optional enum-8 fullback/H-back adds 2 weight only when
present. A TE-labelled H-back participates in TE instead. Base offense is
11 personnel; defense is nickel with two EDGE, two DT, two LB and three CB.
Bench players retain native 0.10 weight. OVR is the equal mean of both units.
See docs/mod_editor/team_ratings.md for calibration and evidence boundaries.
"""
from __future__ import annotations
import hashlib
import struct
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = 'nfl2k5_team_ratings'
RO_SIZE = 288
REQUESTS = ((OWNER, 'read_only', RO_SIZE, 16),)
# position, native rank/side threshold, weight (doubled for exact half weights)
OFFENSE = ((0,1,60),(7,1,20),(3,2,40),(9,1,20),(12,1,12),(13,1,24),(14,1,24),(8,1,4))
DEFENSE = ((16,1,60),(15,1,40),(11,1,20),(4,2,50),(5,1,15),(6,1,15))
SITES = ((0xC4830,48,'797813dbbf9c1be6b50f43d8c939d0c20293ea22df3fcd5a0818aa9fec3ccdff'),
         (0xC4860,64,'861789af6c92d77f49c2b5b81fcffd96993c9e739c328e26646880830883560d'),
         (0xC48A0,144,'2ccf4df3d8530611dc16202bb80d45f5ff908ec2b9d0b8c27e7a235cec6fe263'))
GUARDS = ((0xC45A0,164,'869e8796c1149d642fa45905469bd0484a767a55c3d84197e4b8c6a336794148'),
          (0xC4400,413,'300512909be3f527884f0611627b73c60d06577fc2dd059d684c5831b7589db5'),
          (0x246D80,16,'14151a04d17c38132fedfdc5f87173ccf04fb8d55f435cdc7ca1ef0c7bb6b03f'))


def table_bytes():
    return b''.join(struct.pack('<HBBIfff',w,n,p,0x246D80,0.10,0.,1.)
                    for p,n,w in OFFENSE+DEFENSE).ljust(RO_SIZE,b'\0')


def code_for(va, table):
    a = _Asm(va)
    if va == 0xC4830:
        a.b('53 8b d9 ba 08000000')  # save team in EBX, count FB
        a.call(0xC3CB0)
        a.b('85 c0 b8 07000000')
        a.j8('74','counted')
        a.b('40')                   # eighth row only if FB exists
        a.label('counted')
        a.b('b9'+struct.pack('<I',table).hex())
        a.call(0xC45A0)
        a.b('5b c3')
        size = 48
    elif va == 0xC4860:
        a.b('53 8b d9 b8 06000000 b9'+struct.pack('<I',table+160).hex())
        a.call(0xC45A0)
        a.b('5b c3')
        size = 64
    elif va == 0xC48A0:
        a.b('51 56 8b f1')
        a.call(0xC4830)
        a.b('d9 5c 24 04 8b ce')
        a.call(0xC4860)
        a.b('d8 44 24 04 d8 0d 84414e00 5e 59 c3')
        size = 144
    else:
        raise ValueError('Unknown rating entry point')
    code = a.assemble()
    if len(code)>size: raise ValueError('Rating code exceeds original routine')
    return code.ljust(size,b'\x90')


def allocation(payload):
    found = [r for r in space.layout(payload)['allocations'] if r['owner']==OWNER] if space.status(payload)=='applied' else []
    if not found: return None
    if len(found)!=1 or (found[0]['kind'],found[0]['size'],found[0]['align'])!=('read_only',RO_SIZE,16):
        raise ValueError('Foreign team-rating allocation')
    return found[0]


def _state(payload, *, require_pools=True):
    image = XbeImage(payload)
    if space.status(payload)=='foreign': raise ValueError('Foreign executable geometry or seals')
    row = allocation(payload)
    for va,n,digest in GUARDS:
        if hashlib.sha256(image.read(va,n)).hexdigest()!=digest:
            raise ValueError(f'Foreign rating dependency {va:#x}')
    # Modern two-chain LB/DT is required: never silently misread retail schemes.
    from .nfl2k5_position_pools import CHAIN_INDEX_VA, chain_index_bytes
    if require_pools and image.read(CHAIN_INDEX_VA,16)!=chain_index_bytes():
        raise ValueError('Team ratings require modern position pools')
    states=set()
    for va,n,digest in SITES:
        raw=image.read(va,n)
        states.add('retail' if hashlib.sha256(raw).hexdigest()==digest else
                   'applied' if row and raw==code_for(va,row['va']) else 'foreign')
    if len(states)!=1 or 'foreign' in states: raise ValueError('Mixed or foreign team-rating routines')
    state=states.pop()
    if row and image.read(row['va'],RO_SIZE)!=(table_bytes() if state=='applied' else bytes(RO_SIZE)):
        raise ValueError('Foreign team-rating table')
    return state,row


def status(payload):
    try: return _state(payload, require_pools=False)[0]
    except (ValueError,KeyError,IndexError,struct.error): return 'foreign'


def apply(payload):
    state,row=_state(payload)
    original=payload
    if state=='applied': return payload,dict(owner=OWNER,changed_bytes=0,already_applied=True)
    if row is None:
        payload,_=space.extend_scaleout(payload,REQUESTS) if space.status(payload)=='applied' else space.apply(payload,REQUESTS,scaleout=True)
        row=allocation(payload)
    image=XbeImage(payload)
    sites=[(f'rating_{va:x}',va,image.read(va,n),code_for(va,row['va'])) for va,n,_ in SITES]
    payload,_=space.install_read_only(payload,OWNER,table_bytes())
    payload,_=rdata.apply(payload,sites,OWNER)
    if status(payload)!='applied': raise ValueError('Team-rating readback failed')
    return payload,dict(owner=OWNER,changed_bytes=sum(a!=b for a,b in zip(original,payload)),
                        already_applied=False,table_va=hex(row['va']),dynamic=True)
