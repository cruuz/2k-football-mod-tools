#!/usr/bin/env python3
"""Read-only retail measurements; writes metadata only, never source spans/art.

Run from the repository root. The growth probe executes pinned retail loader
instructions using the bounded native test harness. It does not certify an
archive relocation or an in-game result. This research tool is not release code.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tests/mod_editor')]

def measure(index, art, output, set_selector="15H0"):
    import sys,json,struct,hashlib,tempfile
    from pathlib import Path
    from dataclasses import replace
    from unittest.mock import patch
    sys.path[:0]=['.', 'tools','tests/mod_editor']
    from mod_editor.core import nfl2k5_uniform_equipment_writer as w
    from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal
    from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
    from nfl_outer import parse_archive,read_entry_bytes
    from nfl_txtr import parse_chunks,decode_chunk,encode_rgba_png
    from PIL import Image
    index=index.resolve()

    byid,groups=w.load_targets(); archive=parse_archive(index)
    # Bears is asset code 05 in the uniform catalog.
    choices=[r for r in byid.values() if r.name=='shoes10' and r.set_selector.endswith('H0')]
    print([(r.set_selector,r.outer_index) for r in choices[:35]],flush=True)
    target=next(r for r in choices if r.set_selector==set_selector)
    package=read_entry_bytes(archive,archive.entries[target.outer_index]); chunks=parse_chunks(package,allow_trailing=True)
    chunk=chunks[target.chunk_index]; span=package[chunk.offset:chunk.end_offset]
    decoded,info=decode_chunk(package,chunk)
    print('TARGET',target.asset_id,'budget',chunk.stored_size,'scratch',chunk.overlap_scratch_bytes,flush=True)
    rows=[]
    class Captured(Exception):pass
    captured=[]
    def capture(span,candidate,**kw):
     captured.append(candidate);raise Captured()
    with tempfile.TemporaryDirectory() as d:
     p=Path(d)/'art.png';rgba=Image.open(art).convert('RGBA').tobytes()
     for scale in (1,2,4):
      p.write_bytes(with_import_mode(encode_rgba_png(256,256,rgba),target.asset_id,rgba,independent=True,scale=scale))
      for colors in (256,64,16):
       captured.clear()
       with patch.object(w,'PALETTE_LIMITS',(colors,)),patch.object(w,'_rebuild_fixed_span',side_effect=capture):
        try:w.build_unified_uniform_equipment_imports(index,[(target.asset_id,p)])
        except Captured:pass
       candidate=captured[0]; sizes={}
       for bits in dict.fromkeys((info.offset_bits,10,11,12)):
        stream=compress_equipment_optimal(candidate,stream_tag=info.stream_tag,offset_bits=bits,max_encoded_size=4*1024*1024)
        sizes[bits]=len(stream)
       result=dict(size=256//scale,colors=colors,compressed_bytes=min(sizes.values()),by_offset_bits=sizes,budget=chunk.stored_size,miss_bytes=max(0,min(sizes.values())-chunk.stored_size))
       rows.append(result);print(result,flush=True)
     p.write_bytes(with_import_mode(encode_rgba_png(256,256,rgba),target.asset_id,rgba,independent=True,scale=1))
     try:
      compiled=w.build_unified_uniform_equipment_imports(index,[(target.asset_id,p)],preflight_only=True)
      requested=dict(result="fit",attempts=compiled.attempts)
     except w.EquipmentFitError as exc:
      requested=dict(result="refused",message=str(exc),suggestion=exc.suggestion,attempts=exc.attempts)
    ends=sorted(archive.entries,key=lambda e:e.virtual_offset)
    gaps=[dict(after=a.table_index,before=b.table_index,start=a.virtual_end,size=b.virtual_offset-a.virtual_end) for a,b in zip(ends,ends[1:]) if b.virtual_offset>a.virtual_end]
    result=dict(art_sha256=hashlib.sha256(art.read_bytes()).hexdigest(),target=target.asset_id,set_selector=target.set_selector,fit=rows,package_bytes=len(package),package_tail_bytes=len(package)-chunks[-1].end_offset,alignment_gap_after_package=next((g["size"] for g in gaps if g["after"]==target.outer_index),0),chunks=[dict(index=c.index,kind=c.kind,offset=c.offset,stored=c.stored_size,system=c.system_bytes,video=c.video_bytes,scratch=c.overlap_scratch_bytes) for c in chunks],largest_archive_gaps=sorted(gaps,key=lambda r:r['size'],reverse=True)[:10])
    result['requested_full_size']=requested
    output.write_text(json.dumps(result,indent=2)+'\n')


def growth(index, art, output, set_selector="15H0"):
    import sys,struct,hashlib,json,tempfile
    from pathlib import Path
    from unittest.mock import patch
    sys.path[:0]=['.','tools','tests/mod_editor']
    from mod_editor.core import nfl2k5_uniform_equipment_writer as w
    from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
    from mod_editor.core.nfl2k5_equipment_lz import compress_equipment_optimal
    from nfl_outer import parse_archive,read_entry_bytes
    from nfl_txtr import parse_chunks,decode_chunk,encode_rgba_png,HEADER,minimum_vc_lz_overlap_scratch
    from nfl_vc_lz_fill import fill_stream
    from PIL import Image
    import test_nfl2k5_equipment_texture_native as native
    index=index.resolve()

    byid,groups=w.load_targets();archive=parse_archive(index);target=byid['tset:3734:9:4:shoes10']
    package=read_entry_bytes(archive,archive.entries[target.outer_index]);chunk=parse_chunks(package,allow_trailing=True)[9]
    span=package[chunk.offset:chunk.end_offset];decoded,info=decode_chunk(package,chunk)
    class Captured(Exception):pass
    captures=[]
    def capture(_span,candidate,**kw):captures.append(candidate);raise Captured()
    with tempfile.TemporaryDirectory() as d:
     path=Path(d)/'art.png';rgba=Image.open(art).convert('RGBA').tobytes()
     path.write_bytes(with_import_mode(encode_rgba_png(256,256,rgba),target.asset_id,rgba,independent=True))
     with patch.object(w,'PALETTE_LIMITS',(256,)),patch.object(w,'_rebuild_fixed_span',side_effect=capture):
      try:w.build_unified_uniform_equipment_imports(index,[(target.asset_id,path)],preflight_only=True)
      except Captured:pass
    candidate=captures[0]
    stream=min((compress_equipment_optimal(candidate,stream_tag=info.stream_tag,offset_bits=b,max_encoded_size=4*1024*1024) for b in (info.offset_bits,10,11,12)),key=len)
    stored=(len(stream)+15)&~15;scratch=chunk.overlap_scratch_bytes
    stream,fill=fill_stream(stream,candidate,stored,slack=min(scratch,16))
    body=stream+bytes(stored-len(stream));video=len(candidate)-chunk.system_bytes
    header=HEADER.pack(b'TSET',stored,chunk.system_bytes,video,chunk.compression_magic,scratch,0,0)
    grown=header+body
    assert decode_chunk(grown,parse_chunks(grown)[0])[0]==candidate
    native.NativeEquipmentTests.setUpClass();t=native.NativeEquipmentTests();t.setUp()
    EAX,ECX,EDX,ESP,EIP=(native.UC_X86_REG_EAX,native.UC_X86_REG_ECX,native.UC_X86_REG_EDX,native.UC_X86_REG_ESP,native.UC_X86_REG_EIP)
    base=0x2100100;end=base+len(candidate)+scratch;sizes=[];reads=[];registered=[]
    t.uc.mem_write(base-32,b'P'*32);t.uc.mem_write(end,b'S'*32)
    def external(uc,address,_size,_data):
     esp=uc.reg_read(ESP);pop=4;value=1
     if address==0x437d0:value=0x2300000
     elif address==0x48700:
      sizes.append(uc.reg_read(EDX));value=base
     elif address==0x48ff0:
      read_size=t.words(esp+12)[0];destination=t.words(0xb12130)[0]
      assert read_size==stored
      uc.mem_write(destination,body);reads.append((destination,read_size));pop=24
     elif address==0x430e0:value=0
     elif address==0x48760:pass
     elif address in (0x43e30,0x43e10):
      record=uc.reg_read(ECX);field=record+0x14
      descriptor=field+t.words(field)[0]-1
      t.put(field,descriptor);registered.append((record,descriptor))
      # Native descriptor callback, retaining the caller's normal return/cleanup.
      t.put(esp+4,t.words(esp)[0]);uc.reg_write(ESP,esp+4);uc.reg_write(EIP,0x450b0);return
     else:raise AssertionError(hex(address))
     uc.reg_write(EAX,value);uc.reg_write(EIP,t.words(esp)[0]);uc.reg_write(ESP,esp+pop)
    for address in (0x437d0,0x48700,0x48ff0,0x430e0,0x48760,0x43e30,0x43e10):
     t.uc.hook_add(native.UC_HOOK_CODE,external,begin=address,end=address)
    t.uc.mem_write(0x2001000,header);t.put(0x2002000,0,0)
    t.run_native(0x45280,ecx=0x2002000,edx=0x2001000)
    assert sizes==[len(candidate)+scratch]
    t.run_native(0x45100,args=(0,),count=8000000)
    assert bytes(t.uc.mem_read(base+chunk.system_bytes,video))==candidate[chunk.system_bytes:]
    assert bytes(t.uc.mem_read(base-32,32))==b'P'*32 and bytes(t.uc.mem_read(end,32))==b'S'*32
    assert len(registered)==len(groups[target.outer_index,9])
    textures,_=w._validate_layout(decoded,chunk,groups[target.outer_index,9])
    for ref,texture in textures.items():
     desc=base+texture.descriptor_offset
     pixel,palette=struct.unpack_from('<II',candidate,texture.descriptor_offset+4)
     assert t.words(desc+4,2)==(base+chunk.system_bytes+pixel,base+chunk.system_bytes+palette)
    result=dict(target=target.asset_id,old_stored_bytes=chunk.stored_size,grown_stored_bytes=stored,
     system_bytes=chunk.system_bytes,video_bytes=video,scratch_bytes=scratch,wrapper_14_unchanged=header[20:24]==span[20:24],
     native_allocator_bytes=sizes[0],native_read_bytes=reads[0][1],native_descriptors=len(registered),
     native_decode_and_video_exact=True,native_guards_exact=True,instruction_cap=8000000,timeout_microseconds=1000000,
     note='Only allocator, I/O, resource-registration shell and context-state query are stubbed; native 451D0/45280/45100/4DC00/450B0 execute. No package relocation or disc growth is proved.')
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


def appearance(index, art, output, set_selector="05H0"):
    import json
    import tempfile
    from unittest.mock import patch
    from PIL import Image
    from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
    from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
    from nfl_txtr import encode_rgba_png
    target = next(row for row in writer.load_targets()[0].values()
                  if row.set_selector == set_selector and row.name == 'shoes10')
    rgba = Image.open(art).convert('RGBA').tobytes()
    results = []
    with tempfile.TemporaryDirectory() as directory:
        png = Path(directory)/'user-art.png'
        for independent, scale in ((False,1),(True,4)):
            png.write_bytes(with_import_mode(encode_rgba_png(256,256,rgba),target.asset_id,rgba,
                                           independent=independent,scale=scale))
            compiled = writer.build_unified_uniform_equipment_imports(index,[(target.asset_id,png)],preflight_only=True)
            row = compiled.edit_templates[target.reference_index]
            quality = row['palette_quality']
            results.append(dict(mode=row['import_mode'],dimensions=row['encoded_dimensions'],
                palette_entries=row['palette_entries'],mip_levels=row['mip_levels'],
                max_channel_error=quality['maximum_channel_error'],mean_delta_e76=quality['mean_delta_e76'],
                distinct_colour_merges=len(quality['merged_colours']),reason=quality['merge_reason'],
                pixel_offset=row['pixel_offset'],shared_retail_shape=not independent,
                outcome='Decoded pixels only; GPU and game appearance UNWITNESSED'))
    output.write_text(json.dumps(dict(target=target.asset_id,results=results),indent=2)+'\n')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('fit','growth','appearance'))
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--art',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--set-selector',default='15H0')
    args = parser.parse_args()
    {'fit':measure,'growth':growth,'appearance':appearance}[args.mode](
        args.index,args.art,args.output,args.set_selector)


if __name__ == '__main__': main()
