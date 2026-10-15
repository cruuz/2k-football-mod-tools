#!/usr/bin/env python3
"""Render ur1's private readback textures using the existing offline Blender rig.

The same supplied model, camera, sample number and name are used for both discs.
This is rest-pose evidence, not a runtime or per-player equipment simulation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageDraw
from u1_render_kit import item_for
from ur1_compare import ROOT, CODES, write_json

def name_sample(folder, metrics):
    atlas=Image.open(folder/'names.png').convert('RGBA')
    name='GAINWELL';glyphs=[]
    for ch in name:
        x,w=metrics[ord(ch)-65+2];glyphs.append(atlas.crop((x,0,x+w,32)))
    im=Image.new('RGBA',(256,32));x=(256-sum(g.width+1 for g in glyphs))//2
    for g in glyphs:im.paste(g,(x,0));x+=g.width+1
    path=folder/'sample_name.png';im.save(path);return path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--models',type=Path,required=True)
    p.add_argument('--watch',type=int,default=0,help='wait for this many completed kit pairs')
    a=p.parse_args();out=a.out.resolve();models=a.models.resolve()
    if out==ROOT or ROOT in out.parents:
        p.error('private evidence output must be outside the repository')
    dest=out/'model_renders';dest.mkdir(exist_ok=True);records={};cache={};batch=0
    receipt=out/'render_receipt.json'
    if receipt.exists():
        records={k:v for k,v in json.loads(receipt.read_text()).items() if v.get('renderer_version')==2}
    while True:
        ready=sorted(p.parent.name for p in (out/'extracts/current').glob('*/manifest.json')
                     if (out/'extracts/public'/p.parent.name/'manifest.json').exists())
        todo=[s for s in ready if s not in records][:16]
        if not todo:
            if not a.watch or len(records)>=a.watch:break
            time.sleep(5);continue
        items=[];plans=[]
        for sel in todo:
            paths=[]
            for tag in ('public','current'):
                folder=out/'extracts'/tag/sel;doc=json.loads((folder/'manifest.json').read_text())
                wanted=[x['rgba_sha256'] for x in doc['assets'] if x['chunk'] in (1,2,3,4,12,14,17,24,27,34,37,43)]
                fm=doc['chunks'][0]['words'][12]&0xffffff
                route=doc['chunks'][0]['words'][14]
                if route not in (0,1,2,3,4):
                    raise ValueError(f'{sel}: unknown native arm-number selector {route}')
                key=hashlib.sha256(json.dumps([wanted,fm,route,doc['metrics']]).encode()).hexdigest()
                if key in cache:paths.append(cache[key]);continue
                label=f'{tag}_{sel}';name=name_sample(folder,doc['metrics'])
                it=item_for(label,folder,f'{fm:06x}',14,dest,'all')
                # 0x8F580 reads Unif payload +8; 0x4EF810[selector*5+neckroll]
                # selects one arm-number material family. Here neckroll is 0.
                family={1:'shoulder_B',2:'shoulder_A',3:'sleeve_B',4:'sleeve_A'}.get(route)
                it['hide']=[h for h in it['hide'] if h!='NUMBER_sleeve*']
                it['tex']={k:v for k,v in it['tex'].items() if not k.startswith('NUMBER_shoulder')}
                for f in ('shoulder_A','shoulder_B','sleeve_A','sleeve_B'):
                    if f!=family:it['hide'].append('NUMBER_'+f+'*')
                    else:
                        it['hide'].append('NUMBER_'+f+'_M')
                        for pos,num in [('L',1),('R',4)]:
                            it['tex'][f'NUMBER_{f}_{pos}']=str(folder/f'digit_arm_{num}.png')
                it['uv_scale']['NUMBER_sleeve*']=[4,2]
                it['tex']['PLAYERNAME']=str(name)
                it['hide'].remove('PLAYERNAME*');it['hide'].append('PLAYERNAME_long')
                chosen=['front','back','left','t_front','t_back','h_left','h_back']
                it['views']=[v for v in it['views'] if any(Path(v['out']).stem==label+'_'+n for n in chosen)]
                for v in it['views']:
                    v['samples']=4
                    v['size']=[320,480] if Path(v['out']).stem in [label+'_'+n for n in ('front','back','left')] else [480,480]
                viewpaths={n:str(dest/f'{label}_{n}.png') for n in chosen};cache[key]=viewpaths
                paths.append(viewpaths);items.append(it)
            plans.append((sel,paths))
        job=dict(head=str(models/'hi_head.gltf'),body=str(models/'hi_body.gltf'),arms_down=60,items=items)
        jp=dest/f'batch_{batch:03d}.json';write_json(jp,job)
        with (dest/f'batch_{batch:03d}.log').open('w',newline='\n') as log:
            if items:
                subprocess.run(['blender','--factory-startup','-b','-t','2','--python-exit-code','1','-P',
                    str(ROOT/'tools/b765/u1_blender.py'),'--',str(jp)],stdout=log,stderr=subprocess.STDOUT,check=True)
        for sel,paths in plans:
            canvas=Image.new('RGB',(1080,1540),(35,37,40));d=ImageDraw.Draw(canvas)
            d.text((10,5),sel+' | same rest-pose model, number 14, diagnostic GAINWELL (not roster evidence)',fill='white')
            d.text((10,25),'v0.6',fill='white');d.text((550,25),'current',fill='white')
            for x,pp in zip((10,550),paths):
                for i,n in enumerate(('front','back','left')):
                    im=Image.open(pp[n]).convert('RGBA');im.thumbnail((173,270));canvas.paste(im,(x+175*i,50),im)
                for y,n1,n2 in ((330,'t_front','t_back'),(850,'h_left','h_back')):
                    for dx,n in ((0,n1),(265,n2)):
                        im=Image.open(pp[n]).convert('RGBA');im.thumbnail((260,480));canvas.paste(im,(x+dx,y),im)
                        d.text((x+dx,y+270),n,fill='white')
            d.text((10,1450),'Offline rig: native arm-number route; constant shell C and no neckroll; animation/LOD can differ.',fill='white')
            d.text((10,1470),'Name strip uses native atlas offsets and widths with 1 px spacing on a diagnostic 256x32 target.',fill='white')
            d.text((10,1490),'Historical slots retain their era. Photo matching is separate from this geometric comparison.',fill='white')
            team=CODES.get(sel[:2],'CODE'+sel[:2]);path=out/'sheets'/f'{team}_{sel}_model.png';canvas.save(path)
            records[sel]=dict(paths=paths,sheet=str(path),renderer_version=2);print('rendered',sel,flush=True)
        write_json(receipt,records);batch+=1
    print(json.dumps(dict(kits=len(records),model_sheets=len(records))),flush=True)

if __name__=='__main__':main()
