#!/usr/bin/env python3
"""Read-only number material and UV measurements; no retail vertex export."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from nfl_outer import parse_archive,read_entry_range
from nfl_txtr import parse_chunks,decode_chunk
from nfl_scene_probe import ResourceRecord
from nfl_scne_inventory import parse_scene
from nfl_scne_gltf import decode_batches
from mod_editor.core.nfl2k5_models import uv_to_gltf
from xbe_info import Xbe


def run(index,xbe,output):
    executable=Xbe(xbe)
    assert hashlib.sha256(executable.data).hexdigest()=='73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
    # These bytes pin the actual material binder and GPU address emitter.
    pins={0x8e8f0:'894830',0x8e8f3:'c7402000008040',0x8e8fa:'c7402400000040',
          0x32043:'8b44bd20',0x32052:'8b44bd20',0x320c7:'8d82081b0800',
          0x30816:'d84f20',0x30826:'d84f24',0x30833:'d84f20'}
    for address,encoded in pins.items():
        expected=bytes.fromhex(encoded); offset=executable.va_to_offset(address,len(expected))
        assert executable.data[offset:offset+len(expected)]==expected,hex(address)
    archive=parse_archive(index);entry=archive.entries[3]
    data=read_entry_range(archive,entry,0,entry.size);chunks=parse_chunks(data)
    scenes=[]
    for number in (113,114):
        chunk=chunks[number];decoded,_=decode_chunk(data,chunk)
        resource=ResourceRecord(3,hex(entry.name_id),entry.size,number,chunk.offset,chunk.kind,
                                chunk.stored_size,chunk.system_bytes,chunk.video_bytes,0xffffffff,chunk.overlap_scratch_bytes)
        scene,*_=parse_scene(0,resource,decoded,{})
        rows=[]
        for sub in scene['submeshes']:
            if not sub['material_name'].startswith('NUMBER'):continue
            shape=scene['shapes'][sub['shape_index']]
            uv=next(d for d in shape['attribute_descriptors'] if d['register']==6)
            assert uv['format_name']=='NORMSHORT2'
            stream=next(s for s in shape['vertex_streams'] if s['stream_index']==uv['stream_index'])
            vertices=set(i for _,items in decode_batches(decoded,sub['command_offset'],sub['word_count']) for i in items)
            constant=struct.unpack_from('<4f',decoded,shape['record_offset']+0x30)
            pairs=[uv_to_gltf(*struct.unpack_from('<hh',decoded,stream['offset']+i*stream['stride']+uv['byte_offset']),constant[:2],constant[2:]) for i in vertices]
            material=scene['materials'][sub['material_index']];base=material['record_offset']
            address=struct.unpack_from('<I',decoded,base+0x50)[0]
            blend=struct.unpack_from('<I',decoded,base+0x74)[0]
            assert address==0x133
            # Binder sets material scale U=4,V=2. The draw path at 0x307fc
            # folds it into c[-89], including the shape's offset.
            bounds=[[round(min(p[k] for p in pairs)*scale,6),round(max(p[k] for p in pairs)*scale,6)] for k,scale in enumerate((4,2))]
            rows.append({'material':material['name'],'record_offset':base,'vertices':len(vertices),
                         'uv_bounds_after_material_scale':bounds,'address_word':hex(address),
                         'u_address':address&15,'v_address':(address>>4)&15,
                         'blend_word':hex(blend),'source_blend_factor':hex(blend&65535),
                         'destination_blend_factor':hex(blend>>16)})
        scenes.append({'scene':scene['name'],'outer':3,'chunk':number,'chunk_offset':chunk.offset,
                       'decoded_sha256':hashlib.sha256(decoded).hexdigest(),'number_submeshes':rows})
    result={'xbe_sha256':hashlib.sha256(executable.data).hexdigest(),
            'pinned_instruction_addresses':[hex(a) for a in pins],
            'interpretation':{'address_3':'NV2A CLAMP_TO_EDGE','source_0x302':'SRC_ALPHA',
                              'destination_0x303':'ONE_MINUS_SRC_ALPHA',
                              'caution':'Static material and emitted-state path. Camera pixel size, lighting and in-game appearance remain unwitnessed.'},
            'scenes':scenes}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(f"Pinned retail XBE. Measured {sum(len(s['number_submeshes']) for s in scenes)} number submeshes in lo_body and hi_body; all U/V address nibbles are 3.")


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index',type=Path,default=ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0')
    p.add_argument('--xbe',type=Path,default=ROOT/'extracted/ESPN NFL 2K5 (USA)/default.xbe')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.index,a.xbe,a.output)
