"""Read-only C4 rig/bundle read-back and bounded native shadow descriptor proof."""
from pathlib import Path
import colorsys
import json
import math
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_color as mc

OLD = {
 'day': dict(ambient=(.94,.96,1), ambient_intensity=.58,
             lights=(((1,.98,.94),1.2),((.9,.94,1),.48)), shadow=.275),
 'afternoon': dict(ambient=(1,.95,.86), ambient_intensity=.45,
                   lights=(((1,.94,.84),1.2),((.7,.78,1),.26),((.7,.78,1),.26)), shadow=.27),
}
OLD_HASHES = {
 'day':'a78a892d15fe6477dcc3615a4f3ee8bd5919f0971f186c33e445ccf124c67586',
 'night_indoor':'18c6d914b12edc22d092cea97b7839d4f4611e23b5a898cbceeb4d74222b9fb9',
 'alt_day':'f6f80216e8cf2010b84fcaa46a9a6b50728c27bca47b1ed7c13810fdc220751c',
 'alt_dynamic':'00ce7e0fafa7b22c47925dd57ca01e8f362930627478f127023f797de8818887',
 'rain':'ccfb026911c23bd9f5505f98599b70e19cb8b2e17b9412a6f3cdc64c65bec890',
 'snow':'8c95f170e019d0eb8654b3b3e23fc1c6d78d4d593f5ad1df6c32c00c493d5ee4',
 'afternoon':'3b9fb968fbde08feefa57b2e146089d021ea69fd39da52907459bb970eb58dc0',
}


def hsv(rgb):
    h,s,v = colorsys.rgb_to_hsv(*(c/255 for c in rgb))
    return dict(hue_degrees=round(h*360,3), saturation=round(s,6), value=round(v,6))


def old_table(name, retail):
    if name not in OLD:
        return mc.modern_table(retail)
    rig = OLD[name]
    out = bytearray(retail)
    struct.pack_into('<3f',out,0,*rig['ambient'])
    struct.pack_into('<f',out,0x10,rig['ambient_intensity'])
    for i,(rgb,intensity) in enumerate(rig['lights']):
        struct.pack_into('<3f',out,0x20+i*0x40,*rgb)
        struct.pack_into('<f',out,0x40+i*0x40,intensity)
    return bytes(out)


def shadow_descriptor(image, va):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import UC_X86_REG_ESP
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    # Map only the three native routines and bounded synthetic data/stack.
    for at,size in ((0x64000,12),(0x12fb8d,26),(0x2af50,30)):
        u.mem_map(at & ~0xfff,0x1000)
        u.mem_write(at,image.read(at,size))
    u.mem_map(0xb34000,0x1000)
    u.mem_map(va & ~0xfff,0x2000)
    u.mem_write(va,image.read(va,mc.TABLE_SIZE))
    u.mem_write(0xb34774,struct.pack('<I',va))
    u.mem_map(0x2000000,0x2000)
    sp = 0x2000800
    direction = image.read(va+0x30,16)
    u.mem_write(sp+0x10,direction)
    u.reg_write(UC_X86_REG_ESP,sp)
    u.emu_start(0x12fb8d,0x12fba7,count=100)
    descriptor = bytes(u.mem_read(sp+0x50,0x28))
    expected = struct.unpack('<f',image.read(va+0x100,4))[0]
    assert struct.unpack_from('<I',descriptor)[0] == 1
    assert descriptor[0x10:0x20] == direction
    assert struct.unpack_from('<f',descriptor,0x20)[0] == -expected
    assert struct.unpack_from('<i',descriptor,0x24)[0] == -1
    return dict(native_getter='0x64000', consumer='0x12fb8d', descriptor_writer='0x2af50',
                intensity=struct.unpack_from('<f',descriptor,0x20)[0], direction_unchanged=True,
                code_sha256={hex(at):mc.sha(image.read(at,size)) for at,size in ((0x64000,12),(0x12fb8d,26),(0x2af50,30))})


def main():
    source = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
    payload = (source/'default.xbe').read_bytes()
    patched, receipt = mc.apply(payload)
    retail_image, image = mc.XbeImage(payload), mc.XbeImage(patched)
    assert mc.xbe_status(patched)=='applied'
    assert mc.apply(patched)[0]==patched
    assert mc.apply(patched,enabled=False)[0]==payload
    rows = []
    targets = {'day':(88,105,61),'afternoon':(98,119,72),'night_indoor':(107,121,53)}
    for name,va,retail_hash in mc.LIGHT_TABLES:
        retail = retail_image.read(va,mc.TABLE_SIZE)
        before = old_table(name,retail)
        after = image.read(va,mc.TABLE_SIZE)
        assert mc.sha(retail)==retail_hash
        assert mc.sha(before)==OLD_HASHES[name]
        assert mc.sha(after)==next(r['applied_sha256'] for r in mc._pins()['light_tables'] if r['name']==name)
        assert (before!=after)==(name in OLD)
        count=struct.unpack_from('<I',retail,0x14)[0]
        allowed=set(range(12))|set(range(16,20))
        for i in range(count):
            allowed.update(range(0x20+i*64,0x2c+i*64));allowed.update(range(0x40+i*64,0x44+i*64))
        if name in OLD:allowed.update(range(0x100,0x104))
        assert all(i in allowed for i,(a,b) in enumerate(zip(retail,after)) if a!=b)
        directions=[struct.unpack_from('<3f',retail,0x30+i*64) for i in range(count)]
        rig = mc.read_rig(after)
        prediction=mc.predicted_on_screen((181,216,102),name,table=rig)
        old_prediction=mc.predicted_on_screen((181,216,102),name,table=mc.read_rig(before))
        key=directions[0]
        elevation=math.degrees(math.atan2(key[1],math.hypot(key[0],key[2])))
        rows.append(dict(name=name,va=hex(va),retail_sha256=mc.sha(retail),before_sha256=mc.sha(before),
                         after_sha256=mc.sha(after),before=mc.read_rig(before),after=rig,
                         changed_offsets=[hex(i) for i,(a,b) in enumerate(zip(before,after)) if a!=b],
                         count=count,directions=directions,stored_key_elevation_degrees=elevation,
                         stored_shadow_length_per_unit_height=math.hypot(key[0],key[2])/key[1],
                         key_to_ambient=rig['lights'][0][1]/rig['ambient_intensity'],
                         directional_to_ambient=sum(i for c,i in rig['lights'])/rig['ambient_intensity'],
                         prediction_before=old_prediction,prediction_after=prediction,hsv=hsv(prediction),
                         reference=targets.get(name),native_shadow=shadow_descriptor(image,va)))
    bundle_hash=mc.sha(json.dumps(mc._pins()['bundles'],sort_keys=True,separators=(',',':')).encode())
    assert bundle_hash=='f4ef2c5a179ad39a07f4670ed924e3c4a605a6a2775518a78aa790306c706295'
    bundles=[]
    with mc._outer_image()(source/'vc_53450030') as archive:
        for name in ('s08dd.iff','s13dd.iff','s13ad.iff','s13nd.iff','s11dd.iff','s09dd.iff'):
            pin=next(p for p in mc._pins()['bundles'] if p['name']==name)
            e=archive.entries[pin['outer']];before=archive.read(e.virtual_offset,e.size)
            after,edits=mc.modern_bundle(before,outer_index=pin['outer'])
            assert mc.sha(before)==pin['retail_sha256'] and mc.sha(after)==pin['applied_sha256']
            tx,inv,R,H=mc._tools()
            decoded=[]
            for blob in (before,after):
                ch=tx.parse_chunks(blob,allow_trailing=True)[0]
                rec,out,record=mc._scene(blob,ch,pin['outer'])
                texture=next((t for t in rec['embedded_textures'] if t.get('mapped_material_names')==['color_premipped']),None)
                if texture:
                    info=inv.texture_info(out,texture['descriptor_offset'],rec['name'],texture['index'])
                    rgba=tx.texture_to_rgba(out,record.as_chunk(),info)
                    mean=tuple(sum(rgba[i] for i in range(c,len(rgba),4))/(len(rgba)/4) for c in range(3))
                    rgb=tuple(round(v) for v in mean)
                    kind='decoded colour-map mean'
                else:
                    mat=next(m for m in rec['materials'] if m['name']==mc.COLOR_MAP_MATERIAL)
                    word=struct.unpack_from('<I',out,mat['record_offset']+0x18)[0]
                    rgb=((word>>16)&255,(word>>8)&255,word&255);kind='material +0x18'
                decoded.append(dict(kind=kind,rgb=rgb))
            rig='night_indoor' if name in ('s13nd.iff','s11dd.iff','s09dd.iff') else 'afternoon' if name=='s13ad.iff' else 'day'
            for edit in edits:
                at,size=edit['offset'],edit['size']
                if edit['kind']!='tint':
                    assert before[at:at+32]==after[at:at+32]
                    a,_=tx.decode_chunk(before[at:at+size],tx.parse_chunks(before[at:at+size],allow_trailing=True)[0])
                    b,_=tx.decode_chunk(after[at:at+size],tx.parse_chunks(after[at:at+size],allow_trailing=True)[0])
                    assert len(a)==len(b)
            bundles.append(dict(name=name,retail_sha256=mc.sha(before),applied_sha256=mc.sha(after),
                                decoded=decoded,rig=rig,prediction=mc.predicted_on_screen(decoded[1]['rgb'],rig),
                                edits=edits))
    result=dict(scope='PROVED offline. Native shadow light term, not rendered length/softness. Afternoon uses existing extrapolated screen factor.',
                owner_sha256=mc.sha(Path(mc.__file__).read_bytes()),all_bundle_pins_sha256=bundle_hash,
                bundle_count=477,rigs=rows,decoded_bundles=bundles,xbe_receipt=receipt)
    (ROOT/'reports/b71_c4/daylight-proof.json').write_text(json.dumps(result,indent=2)+'\n')
    for row in rows:
        print(row['name'],row['prediction_before'],'->',row['prediction_after'],'shadow',row['native_shadow']['intensity'])
    print('PASS: seven rig read-backs, bounded native shadow descriptor, six decoded bundles, all bundle pins unchanged')

if __name__=='__main__':
    main()
