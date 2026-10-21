#!/usr/bin/env python3
"""Read-only native field texture and UV inventory. No disc or art writes.

Images and the JSON index are evidence, not game assets. Every s00..s99 and
Anniversary a00..a99 day/afternoon/night, dry/rain/snow name is checked against
archive IDs. Texture sheets are decoded pixels, not emulator screenshots.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_modern_metlife as mm
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core.nfl2k5_models import _shape_lanes, read_lane_2h, uv_to_gltf
from nfl_scne_gltf import decode_batches


def sha(data):
    return hashlib.sha256(data).hexdigest()


def names():
    return {mv.name_id(n): n for p in 'sa' for i in range(100)
            for t in 'dan' for w in 'drs' for n in [f'{p}{i:02d}{t}{w}.iff']}


def selected(key):
    return key.startswith('endzone') or key in ('center_logo', 'numbers', 'pf_numbers')


def scan(source, output):
    from PIL import Image, ImageDraw
    output.mkdir(parents=True, exist_ok=True)
    ids = names()
    result = []
    with mm._outer_image()(source) as archive:
        entries = sorted((ids[e.name_id], e) for e in archive.entries if e.name_id in ids)
        for name, entry in entries:
            raw = archive.read(entry.virtual_offset, entry.size)
            item = dict(name=name, outer=entry.index, bundle_sha256=sha(raw), size=len(raw))
            try:
                chunk, rec, decoded = fields._field_chunk(raw)
            except ValueError as exc:
                item['error'] = str(exc)
                result.append(item)
                continue
            item.update(field_offset=chunk.offset, field_size=chunk.end_offset-chunk.offset,
                        field_sha256=sha(raw[chunk.offset:chunk.end_offset]), textures=[], uv=[])
            rows = mv.p8_rows(rec)
            images = []
            folder = output / name
            folder.mkdir(exist_ok=True)
            for key, index in mv.rows_by_material(rec).items():
                if not selected(key) or index not in rows:
                    continue
                row = rows[index]
                rgba = mv.read_texture(decoded, rec, row)
                im = Image.fromarray(rgba)
                im.save(folder / (key+'.png'))
                item['textures'].append(dict(material=key, texture_index=index,
                    size=list(im.size), mips=row['mip_levels'], rgba_sha256=sha(rgba.tobytes()),
                    pixel_offset=row['pixel_offset'], palette_offset=row['palette_offset'],
                    system_bytes=rec['system_bytes']))
                images.append((key, im))
            for shape in rec['shapes']:
                subs = [s for s in rec['submeshes'] if s['shape_index']==shape['index'] and selected(s['material_name'])]
                if not subs:
                    continue
                lanes = _shape_lanes(rec, shape, decoded)
                uv = [uv_to_gltf(u,v,lanes.uv_scale,lanes.uv_offset)
                      for u,v in read_lane_2h(decoded,shape,lanes.texcoord,lanes.vertex_count)]
                for sub in subs:
                    used = sorted({i for _, ix in decode_batches(decoded, sub['command_offset'],
                                     sub['primary_command_word_count']) for i in ix})
                    if used:
                        item['uv'].append(dict(material=sub['material_name'], shape=shape['name'],
                            used_vertices=len(used), minimum=[min(uv[i][k] for i in used) for k in (0,1)],
                            maximum=[max(uv[i][k] for i in used) for k in (0,1)]))
            sheet = Image.new('RGB', (1056, 42+300*((len(images)+2)//3)), '#23452f')
            draw = ImageDraw.Draw(sheet)
            draw.text((12,10), name+' | native decoded textures | offline evidence', fill='white')
            for i,(key,im) in enumerate(images):
                x,y=12+(i%3)*348,42+(i//3)*300
                draw.text((x,y),f'{key} {im.width}x{im.height}',fill='white')
                im.thumbnail((328,270))
                sheet.paste(im,(x,y+22),im)
            sheet.save(folder/'sheet.jpg',quality=90)
            item['sheet']=str((folder/'sheet.jpg').relative_to(output))
            result.append(item)
            if len(result)%25==0:
                print(f'{len(result)}/{len(entries)} fields decoded',flush=True)
    (output/'inventory.json').write_text(json.dumps(dict(source=str(source), fields=result),indent=2)+'\n',newline='\n')
    print(json.dumps(dict(resources=len(result), fields=sum('error' not in r for r in result),
                         errors=[r for r in result if 'error' in r], output=str(output))),flush=True)


def practice_extra(source, output, *, events=False):
    """Main practice teamlogo is swapped at runtime; side fields live in stadium."""
    from PIL import Image
    output.mkdir(parents=True,exist_ok=True)
    result=[]
    with mm._outer_image()(source) as archive:
        ids=names()
        for entry in archive.entries:
            name=ids.get(entry.name_id,'')
            if name[:3] not in (('s40','s41','s42','s43','s44','s45') if events else ('s32',)):continue
            raw=archive.read(entry.virtual_offset,entry.size)
            for chunk in mm._tools()[0].parse_chunks(raw,allow_trailing=True):
                if chunk.kind!='SCNE':continue
                rec,decoded=mm._scene(raw,chunk)
                rows=mv.p8_rows(rec)
                for key,index in mv.rows_by_material(rec).items():
                    if key not in ('logo','teamlogo','pf_numbers','pf_endzone_grass','pf_endzone_turf'):continue
                    row=rows[index];rgba=mv.read_texture(decoded,rec,row)
                    filename=name+'_'+rec['name']+'_'+key+'.png'
                    Image.fromarray(rgba).save(output/filename)
                    result.append(dict(name=name,scene=rec['name'],material=key,texture_index=index,
                        size=[row['width'],row['height']],mips=row['mip_levels'],rgba_sha256=sha(rgba.tobytes()),
                        pixel_offset=row['pixel_offset'],palette_offset=row['palette_offset'],system_bytes=rec['system_bytes'],file=filename))
    (output/('event_extra.json' if events else 'practice_extra.json')).write_text(json.dumps(result,indent=2)+'\n',newline='\n')
    print(json.dumps(dict(resources=len({r['name'] for r in result}),extra_textures=len(result),events=events)))


def create_team(source,output):
    """Decode the 42 stock create-team paint sets in all three weathers."""
    from PIL import Image,ImageDraw
    from nfl_create_team_field_art_inventory import LOGO_CODES
    output.mkdir(parents=True,exist_ok=True);result=[];tx=mm._tools()[0]
    with mm._outer_image()(source) as archive:
        byid={e.name_id:e for e in archive.entries}
        for code in LOGO_CODES:
            for weather in 'drs':
                name=f'ct{code}{weather}.iff';entry=byid[mv.name_id(name)]
                raw=archive.read(entry.virtual_offset,entry.size);textures=[];images={}
                folder=output/name;folder.mkdir(exist_ok=True)
                for c in tx.parse_chunks(raw,allow_trailing=True):
                    if c.kind!='TXTR':continue
                    decoded,_=tx.decode_chunk(raw,c);t=tx.parse_texture(decoded,c)
                    if t.name!='center_logo' and not t.name.startswith('endzone_'):continue
                    rgba=tx.texture_to_rgba(decoded,c,t);im=Image.frombytes('RGBA',(t.width,t.height),rgba)
                    im.save(folder/(t.name+'.png'));images[t.name]=im
                    textures.append(dict(material=t.name,size=[t.width,t.height],mips=t.mip_levels,rgba_sha256=sha(rgba)))
                canvas=Image.new('RGB',(1056,300),'#23452f');draw=ImageDraw.Draw(canvas);draw.text((8,8),name+' | native create-team field paint | numbers from venue',fill='white')
                for j,end in enumerate(('north','south')):
                    for k,part in enumerate(('left','middle','right')):
                        im=images[f'endzone_{end}_{part}'];canvas.paste(im,(k*256,30+j*132),im)
                im=images['center_logo'];canvas.paste(im,(790,30),im);canvas.save(folder/'sheet.jpg',quality=90)
                result.append(dict(name=name,outer=entry.index,bundle_sha256=sha(raw),textures=textures,sheet=name+'/sheet.jpg'))
    (output/'create_team_inventory.json').write_text(json.dumps(result,indent=2)+'\n',newline='\n')
    print(json.dumps(dict(resources=len(result),paint_sets=len(LOGO_CODES),textures=sum(len(r['textures']) for r in result))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--practice-extra',action='store_true')
    p.add_argument('--create-team',action='store_true')
    p.add_argument('--event-extra',action='store_true')
    a=p.parse_args()
    if a.event_extra:
        practice_extra(a.source,a.output,events=True)
        raise SystemExit(0)
    (create_team if a.create_team else practice_extra if a.practice_extra else scan)(a.source,a.output)
