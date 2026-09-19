"""Bounded retail CPU submission audit. No emulator or GPU execution."""
from pathlib import Path
import hashlib
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]

CODE_PINS = (
    (0x243d0, 0x24a00, '5884747e2f9e61925c4804a546eabb5075b7e5c19dcc802d6de159a0e18218db'),
    (0x2fc80, 0x2fea3, 'dfa8fa09a91ba89dc0440ba9506ab1149207b43fdf81cbf7b284b3ef399c660e'),
)


def submission_trace(capture):
    """Execute 243D0's descriptor walk and push-buffer copy with an owned sink.

    Shader setup and matrix uploads are explicit boundaries. Material-state
    emission executes separately through retail 2FC80. No scene is reordered.
    """
    import unicorn
    from mod_editor.core import nfl2k5_scorebug_ingame as scene
    m, body = capture['machine'], capture['body']
    for start, end, expected in CODE_PINS:
        if hashlib.sha256(bytes(m.uc.mem_read(start, end-start))).hexdigest() != expected:
            raise ValueError('Foreign native submission code at ' + hex(start))
    bucket, head, sink = m.alloc(0x400), m.alloc(128), m.alloc(0x10000)
    m.put(head,bucket); m.put(0xa6aa6c,head)
    mats = m.get(body+256+0x20)
    m.put(bucket+4,m.get(mats+4)); m.put(bucket+12,sink)
    # Shader helper, material binder, matrix upload. Restore all afterwards.
    replacements = {0x315c0:bytes.fromhex('c3'), 0x24160:bytes.fromhex('c20800'),
                    0x22950:bytes.fromhex('8b44240cc20c00'),
                    0x28110:bytes.fromhex('a16caaa600c3')}
    saved = {va:bytes(m.uc.mem_read(va,len(code))) for va,code in replacements.items()}
    rows=[]
    def trace(_u,va,_size,_data):
        if va==0x24555:
            mat=m.uc.reg_read(m.x.UC_X86_REG_ECX)
            descriptor=m.uc.reg_read(m.x.UC_X86_REG_EDI)
            rows.append(dict(material=(mat-mats)//128,name=m.read_string(m.get(mat)),
                visible=not bool(m.get(mat+8)&1),descriptor=descriptor-body,
                tint=hex(m.get(mat+24)),diffuse=hex(m.get(mat+20)),
                vertex_shader=hex(m.get(mat+4)),states=[hex(m.get(mat+0x60+j*4)) for j in range(8)]))
    hook=m.uc.hook_add(unicorn.UC_HOOK_CODE,trace)
    try:
        for va,code in replacements.items():
            m.uc.mem_write(va,code);m.uc.ctl_remove_cache(va,va+len(code))
        m.run(0x243d0,(mats,0,0),ecx=body+scene.layout.SHAPE,edx=capture['matrices'],limit=100000)
        size=m.get(bucket+12)-sink
        words=struct.unpack('<'+'I'*(size//4),m.uc.mem_read(sink,size))
    finally:
        m.uc.hook_del(hook)
        for va,code in saved.items():
            m.uc.mem_write(va,code);m.uc.ctl_remove_cache(va,va+len(code))
    # Native state encoder, starting with distinct cached values.
    m.uc.mem_write(bucket+0x20,bytes([0xff])*16);m.put(bucket+12,sink)
    m.run(0x2fc80,(0,),ecx=bucket,edx=mats+0x60,limit=10000)
    state_words=struct.unpack('<'+'I'*((m.get(bucket+12)-sink)//4),m.uc.mem_read(sink,m.get(bucket+12)-sink))
    return dict(rows=rows,push_words=list(words),state_words=list(state_words),
        code_pins=[dict(start=hex(a),end=hex(b),sha256=h) for a,b,h in CODE_PINS],
        boundaries=['315C0 shader setup','24160 material binder','22950 matrix upload'],
        native_functions=['243D0 descriptor traversal and command copy','2FC80 render-state encoding'],
        runtime_witnessed=False)


def main():
    import argparse
    import json
    from mod_editor.core.nfl2k5_scorebug_sprite import NativePreview
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('native_submission.json'))
    args=parser.parse_args();preview=NativePreview();result={}
    for wide in (False,True):
        _,capture=preview.capture(dict(away='DET',home='LV'),wide)
        try:result['16:9' if wide else '4:3']=submission_trace(capture)
        finally:capture['machine'].close()
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(args.output)


if __name__=='__main__':main()
