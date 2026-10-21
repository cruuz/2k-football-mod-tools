#!/usr/bin/env python3
"""Read-only comparison of every named uniform package in two NFL 2K5 images.

Writes private evidence only. Never writes to an input disc image or artwork source.
The sheets are native texture layouts, not a claim of in-game UV validation.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
from functools import lru_cache
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tools/b765')]
import numpy as np
from PIL import Image, ImageDraw
from nfl2k5_playbook_position_recode import OuterImage
from nfl_uniform_inventory import logical_name_candidates
from nfl_txtr import parse_chunks, decode_chunk, parse_texture, texture_to_rgba
from u1_audit import tset_texture, digit_filename

CODES = dict(zip(['%02d' % x for x in range(31)] + ['37'],
    'ARI ATL BAL BUF CAR CHI CIN DAL DEN DET GB IND JAX KC MIA MIN NE NO NYG NYJ LV PHI PIT LAR LAC SF SEA TB TEN WAS CLE HOU'.split()))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_json(path, value):
    # The renderer can watch this directory while extraction is running.
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)

def load_provenance():
    provenance = {}
    for job,file in [('uf1','nfl2k5_kit_fixes_2026.json'),('uf2','nfl2k5_kit_fixes_2026_alts.json')]:
        for row in json.loads((ROOT/'data'/file).read_text())['textures']:
            provenance.setdefault((row['selector'],row['chunk']),[]).append(dict(job=job,file='data/'+file,**row))
    file = 'nfl2k5_nyg_numbers_pins.json'
    for row in json.loads((ROOT/'data'/file).read_text())['digits']:
        provenance.setdefault(('18H0',33+row['digit']),[]).append(dict(
            job='ny1',file='data/'+file,note='Plain-white home arm digit copied from jersey digit',**row))
    file = 'nfl2k5_unc_bowl_uniforms_pins.json'
    for selector,resource in json.loads((ROOT/'data'/file).read_text())['resources'].items():
        for row in resource['spans']:
            chunks = (range(13,44) if row['label']=='jersey_digits_repack_13_43'
                      else [int(row['label'].removeprefix('chunk_'))])
            for chunk in chunks:
                provenance.setdefault((selector.removesuffix('.IFF'),chunk),[]).append(dict(
                    job='unc_bowl_uniforms',file='data/'+file,
                    pin_scope='chunks_13_43' if len(chunks)>1 else 'chunk',
                    note='White italic PIT jersey digits' if selector.startswith('22') else
                         'CIN broad pants stripes' if chunk==2 else
                         'CIN small-player preview synchronized' if chunk==51 else
                         'CIN black rear helmet digits',**row))
    return provenance

@lru_cache(maxsize=256)
def decoded_span(span):
    c=parse_chunks(span)[0]
    dec,_=decode_chunk(span,c)
    textures=[]
    if c.kind in ('TSET','TXTR'):
        ts=([tset_texture(dec,i) for i in range(struct.unpack_from('<I',dec,4)[0])]
            if c.kind=='TSET' else [parse_texture(dec,c)])
        textures=[(t,texture_to_rgba(dec,c,t)) for t in ts]
    return dec,textures

def extract(image, entry, selector, dest):
    raw = image.read(entry.virtual_offset, entry.size)
    dest.mkdir(parents=True, exist_ok=True)
    chunks, assets = [], []
    metrics = []
    for c in parse_chunks(raw):
        span = raw[c.offset:c.end_offset]
        dec, textures = decoded_span(span)
        r = dict(chunk=c.index, kind=c.kind, offset=c.offset, length=len(span),
                 span_sha256=sha(span), decoded_sha256=sha(dec),
                 spans=[dict(pack=p.name if hasattr(p, 'name') else str(p.ordinal),
                     image_offset=p.image_offset+o, length=n)
                     for p,o,n in image._segments(entry.virtual_offset+c.offset,len(span))])
        chunks.append(r)
        if c.kind == 'NAME':
            metrics = [list(struct.unpack_from('<HH', dec, 0x2c+i*4)) for i in range(29)]
        if c.kind == 'Unif':
            r['words'] = list(struct.unpack('<'+'I'*(len(dec)//4),dec))
        if c.kind not in ('TSET','TXTR'):
            continue
        for t,rgba in textures:
            a = dict(chunk=c.index, name=t.name, width=t.width, height=t.height,
                     mip_levels=t.mip_levels, rgba_sha256=sha(rgba))
            if c.kind in ('TSET','TXTR'):
                n = {1:'torso',2:'pants',3:'sleeve'}.get(c.index,t.name)
                if c.index in (11,12): n='helmet_'+t.name
                if 13 <= c.index <= 42: n=digit_filename(c.index,t.name).removesuffix('.png')
                if not t.name.endswith('_mud'):
                    a['png'] = str(dest/(n+'.png'))
                    Image.frombytes('RGBA',(t.width,t.height),rgba).save(a['png'])
            assets.append(a)
    return dict(selector=selector,outer_index=entry.index,resource_size=len(raw),
                resource_sha256=sha(raw),chunks=chunks,assets=assets,metrics=metrics)

def make_sheet(sel, team, old, new, out):
    # One identical scale per element on both sides, nearest sampling shows native edges.
    rows = [('Helmet C: side logos / crown / rear / maker','helmet_helmet02.png',512,256),
            ('Helmet A: alternate shell decal atlas','helmet_helmet00.png',512,256),
            ('Jersey front + back atlas: collar / maker / name area','torso.png',512,256),
            ('Sleeves: both islands, stripes and maker','sleeve.png',256,256),
            ('Pants: both legs','pants.png',512,256),
            ('Nameplate atlas, first half / second half','names.png',512,64),
            ('Jersey numerals 0-9, native glyph shapes','digit_jersey',512,64),
            ('Shoulder numerals 0-9','digit_arm',512,64),
            ('Helmet numerals 0-9','digit_helmet',512,64),
            ('Socks','socks00.png',256,128)]
    canvas=Image.new('RGB',(1080,60+sum(h+28 for _,_,_,h in rows)),(35,37,40))
    d=ImageDraw.Draw(canvas);d.text((10,8),f'{team} {sel} | native texture comparison (not an in-game render)',fill='white')
    d.text((10,30),'PUBLIC v0.6',fill='white');d.text((550,30),'CURRENT v0.6.1',fill='white')
    y=60
    for title,name,w,h in rows:
        d.text((10,y),title,fill='white');y+=24
        for x,root in ((10,old),(550,new)):
            if name.startswith('digit_'):
                im=Image.new('RGBA',(640,64))
                for i in range(10):
                    p=root/f'{name}_{i}.png'
                    if p.exists(): im.paste(Image.open(p).convert('RGBA').resize((64,64),Image.Resampling.NEAREST),(i*64,0))
            elif (root/name).exists():
                im=Image.open(root/name).convert('RGBA')
                if name=='names.png':
                    folded=Image.new('RGBA',(512,64));folded.paste(im.crop((0,0,512,32)),(0,0));folded.paste(im.crop((512,0,1024,32)),(0,32));im=folded
            else: continue
            im.thumbnail((w,h),Image.Resampling.NEAREST)
            if name in ('sleeve.png','socks00.png'): im=im.resize((w,h),Image.Resampling.NEAREST)
            canvas.paste(im,(x,y),im)
        y+=h+4
    canvas.save(out)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public',type=Path,required=True);p.add_argument('--current',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--only',nargs='*')
    a=p.parse_args();a.out=a.out.resolve()
    if a.out==ROOT or ROOT in a.out.parents: p.error('private evidence output must be outside the repository')
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'sheets').mkdir(exist_ok=True)
    identity = {tag:dict(path=str(path.resolve()),size=path.stat().st_size,
                        mtime_ns=path.stat().st_mtime_ns)
                for tag,path in [('public',a.public),('current',a.current)]}
    identity_path = a.out/'source_identity.json'
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            p.error('source identity changed; use a fresh evidence directory')
    elif (a.out/'extracts').exists():
        p.error('existing extracts lack source identity; use a fresh evidence directory')
    else:
        write_json(identity_path,identity)
    provenance=load_provenance()
    candidates=logical_name_candidates();rows=[];summary=Counter()
    with OuterImage(a.public) as before, OuterImage(a.current) as after:
        bmap={e.name_id:e for e in before.entries}
        entries=[e for e in after.entries if e.name_id in candidates]
        for e in entries:
            sel=candidates[e.name_id].name.removesuffix('.IFF')
            if a.only and sel not in a.only:continue
            team=CODES.get(sel[:2],'CODE'+sel[:2]);sides=[]
            for tag,img,entry in [('public',before,bmap[e.name_id]),('current',after,e)]:
                folder=a.out/'extracts'/tag/sel;manifest=folder/'manifest.json'
                if manifest.exists(): doc=json.loads(manifest.read_text())
                else: doc=extract(img,entry,sel,folder);write_json(manifest,doc)
                sides.append(doc)
            old,new=sides;changes=[]
            assert len(old['chunks']) == len(new['chunks']), sel
            assert len(old['assets']) == len(new['assets']), sel
            for x,y in zip(old['chunks'],new['chunks']):
                assert (x['chunk'],x['kind']) == (y['chunk'],y['kind']), sel
                if x['decoded_sha256']==y['decoded_sha256']:continue
                notes=provenance.get((sel,y['chunk']),[])
                changes.append(dict(chunk=y['chunk'],kind=y['kind'],before=x,after=y,
                    provenance=[{k:r.get(k) for k in ('job','file','note','defects','before_sha256','after_sha256')} for r in notes],
                    output_pin_match=any(r.get('after_sha256')==y['span_sha256'] for r in notes)))
            texture_diffs=[]
            for x,y in zip(old['assets'],new['assets']):
                assert (x['chunk'],x['name'])==(y['chunk'],y['name'])
                if x['rgba_sha256']==y['rgba_sha256']:continue
                r=dict(chunk=y['chunk'],name=y['name'],dimensions=[y['width'],y['height']])
                if 'png' in x and 'png' in y:
                    aa=np.array(Image.open(x['png']));bb=np.array(Image.open(y['png']))
                    if aa.shape==bb.shape:
                        mask=np.any(aa!=bb,axis=2);ys,xs=np.where(mask)
                        r.update(changed_texels=int(mask.sum()),bbox=[int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1])
                texture_diffs.append(r)
            sheet=a.out/'sheets'/f'{team}_{sel}.png'
            make_sheet(sel,team,a.out/'extracts/public'/sel,a.out/'extracts/current'/sel,sheet)
            rows.append(dict(team=team,selector=sel,changes=changes,texture_diffs=texture_diffs,
                resource_equal=old['resource_sha256']==new['resource_sha256'],sheet=str(sheet)))
            summary['kits']+=1;summary['changed_kits']+=bool(changes);summary['changed_chunks']+=len(changes)
            summary['changed_textures']+=len(texture_diffs)
            print(f'{sel} {team}: {len(changes)} decoded chunks, {len(texture_diffs)} texture planes differ',flush=True)
            write_json(a.out/'compare.json',dict(summary=dict(summary),kits=rows))
    summary['sheets']=len(rows);summary['teams']=len(set(r['team'] for r in rows))
    write_json(a.out/'summary.json',dict(summary));print(json.dumps(dict(summary)),flush=True)

if __name__=='__main__':main()
