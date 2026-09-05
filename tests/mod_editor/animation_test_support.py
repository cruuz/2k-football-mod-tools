"""Synthetic motion fixtures; contains no retail resource bytes."""
import struct
from mod_editor.core import nfl2k5_animation as A


def make_clip(*,channels=3,frames=4,flags=0,auxiliary=True,kind='SMCD',family=None):
    name = {'referee':'ANM_REF_PENALTY_DELAY_OF_GAME_R','player':'ANM_CELEBRATE_USER_34'}.get(family,'Synthetic motion')
    identity = {'referee':'archive:3107/27','player':'archive:3092/163'}.get(family,'archive:7/2')
    if family:
        channels = 21 if family == 'referee' else 23
    body = bytearray(32)
    body[12:16] = kind.encode()
    name_bytes = (name+'\0').encode('utf-16le')
    body.extend(name_bytes)
    body.extend(bytes((-len(body))%4))
    common_root = len(body)
    def pointer(field,target):
        struct.pack_into('<i',body,field,target-field+1)
    pointer(16,32)
    pointer(20,common_root)
    count = 2 if kind == 'MMCD' else 1
    if kind == 'MMCD':
        body.extend(struct.pack('<I',count)+bytes(count*16))
    roots = [len(body)+i*52 for i in range(count)]
    body.extend(bytes(count*52))
    if kind == 'MMCD':
        for i,root in enumerate(roots):
            directory = common_root+4+i*16
            pointer(directory,root)
            struct.pack_into('<3I',body,directory+4,0xdeadbeef,i,0x12345678)
    for root in roots:
        body[root] = channels
        body[root+1] = 0x61
        struct.pack_into('<H',body,root+2,frames)
        body[root+4] = flags
        struct.pack_into('<I',body,root+8,0x80000201)
        body[root+12:root+16] = bytes((12,0xde,0xad,0xbe))
        struct.pack_into('<5f',body,root+16,1.25,0.173,1.1,-2.2,3.3)
        pointer(root+44,len(body))
        body.extend(struct.pack('<3I',2,(65536<<8)|9,0xffffffff))
        if auxiliary:
            pointer(root+48,len(body))
            for frame in range(frames):
                body.extend(struct.pack('<I4h',0x20080200,frame,-2,3,-32768))
        pointer(root+40,len(body))
        for frame in range(frames):
            body.extend(struct.pack('<3h',frame,-frame,3*frame))
            if not flags&8:
                body.extend(struct.pack('<h',frame*7))
        body.extend(b'\x23\x81\x99\x51')  # nonzero trajectory slack
        pointer(root+36,len(body))
        for frame in range(frames):
            for channel in range(channels):
                body.extend(struct.pack('<I',0x20080200+(frame*2+channel)%100))
        body.extend(b'\x31\x41\x59\x26')  # nonzero quaternion slack
    wrapper = struct.pack('<4s7I',kind.encode(),len(body),len(body),0,0,0,0,0)
    source = {'scope':'archive','segments':[{'pack':'3','offset':1000,'length':len(wrapper)+len(body)}]}
    return A.parse_archive_span(wrapper+body,identity,source)


def simple_skeleton(family='referee'):
    return {'family':family,'bones':[{'name':f'joint_{i}','parent':i-1,'local_cm':[0,1,0]} for i in range(25)]}
