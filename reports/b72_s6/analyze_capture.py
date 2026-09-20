"""Read-only live capture audit; never writes resource or RAM dumps into reports."""
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from tools.scorebug_sprite import live, xemu_model
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_resources as art
from nfl_outer import HEADER_SIZE
from nfl2k5_scorebug_projection import submission_batches

OUT = Path(__file__).resolve().parent
EVIDENCE = Path('/home/noah/Desktop/2K5-8 Editors/beta72_evidence/xemu_capture_0919')
CAPTURE = Path('/home/noah/.var/app/app.xemu.xemu/data/xemu/capture/20260919-135300')
XEMU = Path('/home/noah/Desktop/2K5-8 Editors/research/xemu_src/xemu/hw/xbox/nv2a')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(name, obj):
    (OUT/name).write_text(json.dumps(obj, indent=2)+'\n', encoding='utf-8', newline='\n')


def floats(words):
    return [struct.unpack('<f', struct.pack('<I', w))[0] for w in words]


def identity(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            digest.update(block)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest())


def texture_from_patch(patch):
    # file_grow v2 can prepend other files before this pack. Its sector offset
    # is authoritative; assuming the ZIP member starts with pack 0 is wrong.
    with zipfile.ZipFile(patch) as z:
        manifest = json.loads(z.read('manifest.json'))
        op = next(o for o in manifest['ops'] if o.get('path') == 'vc_53450030/0')
        origin = op['append']['file_sector_offset']*2048
        with z.open(op['payload']['member']) as f:
            f.seek(origin+HEADER_SIZE+art.HUD_OUTER_INDEX*12)
            ident, size, sector = struct.unpack('<3I', f.read(12))
            assert ident == 11965036 and 0 < size-art.HUD_SIZE < 400000
            f.seek(origin+sector*2048+art.HUD_SIZE)
            appended = f.read(size-art.HUD_SIZE)
        chunks = list(scene.tx.parse_chunks(appended))
        atlas, scne = chunks[-2:]
        assert atlas.kind == 'TXTR' and scne.kind == 'SCNE'
        body,_ = scene.tx.decode_chunk(appended, atlas)
        info = scene.tx.parse_texture(body, atlas)
        assert (info.name,info.width,info.height,info.mip_levels) == ('score_buga',256,512,1)
        video = body[atlas.system_bytes:]
        indices = video[info.pixel_offset:info.pixel_offset+131072]
        palette = video[info.palette_offset:info.palette_offset+1024]
        disk_scene,_ = scene.tx.decode_chunk(appended, scne)
        return indices,palette,disk_scene,dict(
            patch=identity(patch), payload_member=op['payload']['member'],
            pack_origin_in_member=origin, appended_bytes=len(appended),
            atlas_span_sha256=sha(appended[atlas.offset:atlas.end_offset]),
            scene_span_sha256=sha(appended[scne.offset:scne.end_offset]))


def draw_index(name, result):
    columns = ['id','begin_line','end_line','primitive','texture','format','palette','geometry_events','vp_complete']
    with (OUT/name).open('w', encoding='utf-8', newline='') as f:
        out = csv.DictWriter(f, fieldnames=columns, lineterminator="\n");out.writeheader()
        for row in result['draws']:
            s=row['state']
            out.writerow(dict(id=row['id'], begin_line=row['begin_line'], end_line=row['end_line'],
                primitive=row['primitive'],texture=hex(s.get('0x1b00',0)),format=hex(s.get('0x1b04',0)),
                palette=hex(s.get('0x1b20',0)),geometry_events=len(row['geometry_events']),
                vp_complete=row['vertex_program_complete']))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--patch',type=Path,required=True)
    a=p.parse_args()
    sample=EVIDENCE/'trace_sample6.log';ram_path=CAPTURE/'ram_6.bin';full_path=CAPTURE/'trace.log'
    ram=ram_path.read_bytes();full=full_path.read_bytes();raw=sample.read_bytes()
    assert full[13976229:18742095] == raw
    result=live.parse(raw.decode().splitlines())
    draw_index('sample_draws.csv',result)
    # Complete observed state and upload memory for every draw, losslessly
    # compressed. These are decoded method values, not copied RAM resources.
    with (OUT/'sample_draw_states.json.gz').open('wb') as f:
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0,filename='') as gz:
            gz.write(json.dumps(result,separators=(',',':')).encode())
    summary=dict(counts=result['counts'],boundary_events=result['boundary_events'],
        sprite_format_draws=sum(d['state'].get('0x1b04')==0x9810b29 for d in result['draws']),
        sprite_offset_draws=sum(d['state'].get('0x1b00')==0x1e55480 for d in result['draws']),
        warnings=result['warnings'],ram_bytes=len(ram),missing_top_bytes=0x4000000-len(ram),
        exact_sample_slice=[13976229,18742095],
        conclusion='The supplied sample does not contain an appended sprite atlas draw.')
    write('sample_summary.json',summary)

    samples=json.loads((CAPTURE/'samples.json').read_text())
    earlier=next(s for s in samples if s['t']=='13:55:28')
    start,end=earlier['trace_bytes'];first=full[:start].count(b'\n')+1
    previous=live.parse(full[start:end].decode().splitlines(),first_line=first)
    draw_index('earlier_draws.csv',previous)
    atlas_rows=[r for r in previous['draws'] if r['state'].get('0x1b04')==0x9810b29]
    assert len(atlas_rows)==6
    # Decode the later RAM snapshot's relocated scene. This is corroboration,
    # not a substitute for the indices omitted from the earlier trace.
    base=0x1e75900;body=live.read_ram(ram,base,20416)
    assert struct.unpack_from('<II',body,0x60)==(0x35525053,16512)
    batches=[]
    for material,indices in submission_batches(body,base|0x80000000):
        at=0x1c0+material*128;words=struct.unpack_from('<32I',body,at)
        name_at=words[0]&0x7fffffff
        name=live.read_ram(ram,name_at,64).decode('utf-16le').split('\0')[0]
        batches.append(dict(material=material,name=name,visible=not bool(words[2]&1),
            indices=indices,material_words=words))
    visible=[r for r in batches if r['visible']]
    first_id=atlas_rows[0]['id']
    submitted=previous['draws'][first_id:first_id+len(visible)]
    assert len(submitted)==8
    for row,batch in zip(submitted,visible):
        row.update(name=batch['name'],inferred_indices=batch['indices'],
            identification='Ordered correspondence with later RAM descriptors and matching texture sequence; index values absent from trace')
    first_setup=min(r['state_writes'].get('0x1720',r['begin_line']) for r in submitted)
    for row in submitted:
        row['inherited_before_sprite_setup']={k:v for k,v in row['state_writes'].items() if v<first_setup}
        row['inherited_from_earlier_sprite_or_game_write']={k:v for k,v in row['state_writes'].items() if v<row['begin_line']}
        row['constants_inherited_before_sprite_setup']={k:v for k,v in row['constant_writes'].items() if v<first_setup}
    write('earlier_hud_draws.json',dict(window=earlier,first_line=first,
        first_sprite_array_setup_line=first_setup,counts=previous['counts'],rows=submitted,
        unknown_registers=[hex(x) for x in [0x184,0x188,0x190,0x194,0x198,0x19c,0x1a0,0x200,0x204,0x208,0x20c,0x210,0x214,0x30c,0x37c,0x17bc,0x17c0,0x1d7c] if f'0x{x:04x}' not in submitted[0]['state']],
        correspondence_proved=False,ram_is_same_draw_snapshot=False))
    write('ram_scene_batches.json',dict(physical_base=hex(base),cpu_base=hex(base|0x80000000),rows=batches))

    disk_indices,disk_palette,disk_scene,disk=texture_from_patch(a.patch)
    indices=live.read_ram(ram,0x1e55480,131072);palette=live.read_ram(ram,0x1e75480,1024)
    compare=dict(build=disk,regions=[])
    for name,offset,actual,expected in [('indices',0x1e55480,indices,disk_indices),('palette',0x1e75480,palette,disk_palette)]:
        compare['regions'].append(dict(name=name,physical_offset=hex(offset),bytes=len(actual),
            ram_sha256=sha(actual),build_sha256=sha(expected),equal=actual==expected,
            changed_bytes=sum(x!=y for x,y in zip(actual,expected))))
    disk_batches=list(submission_batches(disk_scene))
    compare['scene_index_batches_equal_disc_p']=[(b['material'],b['indices']) for b in batches]==disk_batches
    write('ram_build_comparison.json',compare)

    texture=xemu_model.p8_texture(indices,palette,256,512)
    # Only our own generated atlas is saved, and only after exact patch match.
    assert indices==disk_indices and palette==disk_palette
    texture.save(OUT/'ram_atlas.png')
    rows={r['name']:r for r in submitted}
    pipeline=xemu_model.Pipeline(dict(rows=submitted,fixture_assumptions=[
        'Earlier 13:55:28 trace paired with later 13:55:49 RAM',
        'Descriptor-to-draw correspondence inferred because stock logger omits indices']))
    glyph_rows=[]
    for name,verts in [('yscore_buga1',range(140,168)),('yscore_buga',list(range(52,56))+list(range(64,68)))]:
        pipeline.select(name)
        for v in list(verts)[::4]:
            pos=struct.unpack_from('<3h',ram,0x1e77f60+v*6)
            words=[struct.unpack_from('<I',ram,0x1e78620+(v+j)*10)[0] for j in range(4)]
            uvs=[pipeline.vertex_uv(struct.unpack_from('<2h',ram,0x1e78624+(v+j)*10)) for j in range(4)]
            color=tuple(round(c*255) for c in xemu_model.rgba(words[0]))
            if not color[3]:continue
            x0,y0=[int(min(p[k] for p in uvs)*sz+.5) for k,sz in enumerate((256,512))]
            x1,y1=[int(max(p[k] for p in uvs)*sz+.5) for k,sz in enumerate((256,512))]
            cell=texture.crop((x0,y0,x1,y1))
            samples=list(cell.getdata());opaque=[s for s in samples if s[3]==255 and min(s[:3])>=200]
            if not opaque:raise ValueError('No opaque bright core in live UV bounds')
            predictions=[pipeline.fragment(s,color,(19,19,19,255)) for s in opaque]
            glyph_rows.append(dict(material=name,vertex=v,position_s1=pos,vertex_bgra=[hex(w) for w in words],
                uv_bounds=[x0,y0,x1,y1],opaque_core_texels=len(opaque),
                predicted_core_luma_min=min(sum(c*w for c,w in zip(p[:3],(.2126,.7152,.0722))) for p in predictions),
                predicted_core_luma_max=max(sum(c*w for c,w in zip(p[:3],(.2126,.7152,.0722))) for p in predictions),
                limitation='Texel-centre fragment probes, not framebuffer reproduction or raster-coverage prediction'))
    from PIL import Image
    import numpy as np
    shots=[]
    # Explicit display-space interior regions, no fitted shader parameters.
    for filename,boxes in [
        ('shot_6_xemu_window.png',dict(label=(555,631,646,645),away=(474,638,499,670),home=(715,638,741,670))),
        ('noah_screenshot_135542_49ers_at_bills.png',dict(label=(587,648,678,662),away=(506,655,531,687),home=(747,655,773,687)))]:
        im=Image.open(EVIDENCE/filename).convert('RGB');stats={}
        for name,box in boxes.items():
            pixels=np.asarray(im.crop(box)).astype(float);luma=pixels@np.array([.2126,.7152,.0722])
            stats[name]=dict(box=box,luma_min=float(luma.min()),luma_mean=float(luma.mean()),luma_max=float(luma.max()))
        shots.append(dict(filename=filename,size=im.size,regions=stats))
    write('model_probe.json',dict(glyphs=glyph_rows,screenshots=shots,calibration_passed=False,
        cause_proved=False,fix_applied=False,reason='Sample has no HUD draws; earlier known fragment path still predicts bright cores. No exact raster reproduction is possible from these inputs.',
        pipeline=pipeline.receipt()))
    paths=[sample,full_path,ram_path,CAPTURE/'samples.json',EVIDENCE/'xemu_stdout.log']+list(EVIDENCE.glob('*.png'))
    write('input_identities.json',[identity(p) for p in paths])
    write('xemu_source.json',dict(installed_commit='fc24584ce88f0915ad7f04775bb7712c2e3f49ee',
        installed_version='0.8.136',local_source_commit='f9b14039e5bb56ae2d8f028e31e7cc19f13f7e12',
        files={n:sha((XEMU/n).read_bytes()) for n in ['pgraph/pgraph.c','pgraph/gl/texture.c','pgraph/gl/draw.c','pgraph/glsl/vsh-prog.c','pgraph/glsl/psh.c','trace-events']},
        exact_version_logger_verified='https://raw.githubusercontent.com/xemu-project/xemu/fc24584ce88f0915ad7f04775bb7712c2e3f49ee/hw/xbox/nv2a/pgraph/pgraph.c',
        limitation='Exact installed logger and upload semantics checked online; full installed GL shader/cache implementation not verified byte-for-byte'))
    print(json.dumps(dict(sample=summary,ram_comparison=compare,probe=glyph_rows,screenshots=shots),indent=2))


if __name__=='__main__':main()
