#!/usr/bin/env python3
"""Offline native SCNE diagnostic render, with original P8 pixels and UV constants.

Approximate nearest sampling, double-sided faces, alpha cutout at 0.5, no game
lighting/LOD/sorting. Missing runtime crowd atlas is shown as red wire edges.
Camera spots are offline inspection coordinates in metres, not runtime claims.
Numba is an optional accelerator (packaging/requirements-stadium-audit.txt).
Without it the same rasterizer runs in Python, which is slower for full scenes.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import struct
import json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
try:
    from numba import njit
except ImportError:
    def njit(*, cache=False):
        return lambda function: function
from PIL import Image,ImageDraw
from tools.b765.s1_audit import scene_data,triangles
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_sofi_model as model

SPOTS={
 'broadcast_midfield':((49.,14.,4.5),(4.,0.,2.5),35.),
 'kickoff_south':((0.,6.,-52.),(0.,4.,34.),60.),
 'endzone_north':((0.,8.,62.),(0.,7.,-25.),60.),
 'replay_lower_bowl':((16.,4.,0.),(74.,16.,0.),48.),
 'replay_party_pass':((0.,8.,42.),(0.,28.,109.),48.),
 'upper_corner':((0.,14.,0.),(95.,47.,105.),50.),
}

def clip_near(cam,uv,colour,near=.5):
    """Clip camera-space polygons with interpolated UV/color instead of dropping faces."""
    polygon=[]
    for i in range(len(cam)):
        j=(i+1)%len(cam);a,b=cam[i],cam[j]
        if a[2]>=near:polygon.append((a,uv[i],colour[i]))
        if (a[2]>=near)!=(b[2]>=near):
            t=(near-a[2])/(b[2]-a[2])
            polygon.append((a+(b-a)*t,uv[i]+(uv[j]-uv[i])*t,colour[i]+(colour[j]-colour[i])*t))
    return polygon

@njit(cache=True)
def draw_triangle(screen,uv,colour,texture,zbuf,pixels):
    h,w=pixels.shape[:2]
    x0=max(0,int(np.floor(np.min(screen[:,0]))));x1=min(w-1,int(np.ceil(np.max(screen[:,0]))))
    y0=max(0,int(np.floor(np.min(screen[:,1]))));y1=min(h-1,int(np.ceil(np.max(screen[:,1]))))
    denom=(screen[1,1]-screen[2,1])*(screen[0,0]-screen[2,0])+(screen[2,0]-screen[1,0])*(screen[0,1]-screen[2,1])
    if abs(denom)<1e-7:return
    for y in range(y0,y1+1):
      for x in range(x0,x1+1):
        a=((screen[1,1]-screen[2,1])*(x+.5-screen[2,0])+(screen[2,0]-screen[1,0])*(y+.5-screen[2,1]))/denom
        b=((screen[2,1]-screen[0,1])*(x+.5-screen[2,0])+(screen[0,0]-screen[2,0])*(y+.5-screen[2,1]))/denom
        c=1-a-b
        if a<0 or b<0 or c<0:continue
        q=a/screen[0,2]+b/screen[1,2]+c/screen[2,2]
        depth=1/q
        if depth>=zbuf[y,x]:continue
        a=a/screen[0,2]/q;b=b/screen[1,2]/q;c=c/screen[2,2]/q
        u=a*uv[0,0]+b*uv[1,0]+c*uv[2,0];v=a*uv[0,1]+b*uv[1,1]+c*uv[2,1]
        tx=int((u%1)*texture.shape[1])%texture.shape[1];ty=int((v%1)*texture.shape[0])%texture.shape[0]
        t=texture[ty,tx]
        if t[3]<128:continue
        zbuf[y,x]=depth
        for ch in range(3):
          light=(a*colour[0,ch]+b*colour[1,ch]+c*colour[2,ch])*2/255.
          pixels[y,x,ch]=min(255,int(t[ch]*light))

@njit(cache=True)
def draw_wires(wires,zbuf,pixels):
    h,w=pixels.shape[:2]
    for tri in wires:
      for i,j in ((0,1),(1,2),(2,0)):
        a,b=tri[i],tri[j]
        n=int(min(2000,max(abs(a[0]-b[0]),abs(a[1]-b[1]))))+1
        for k in range(n):
            t=k/max(n-1,1)
            x=int(np.rint(a[0]*(1-t)+b[0]*t));y=int(np.rint(a[1]*(1-t)+b[1]*t))
            if 0<=x<w and 0<=y<h:
                depth=1/((1-t)/a[2]+t/b[2])
                if depth<=zbuf[y,x]+.03:
                    pixels[y,x,0]=255;pixels[y,x,1]=80;pixels[y,x,2]=65

def render(data,spot,width=960,height=540,crowd_atlas=None):
    chunk,rec,decoded,sc=scene_data(data)
    eye,target,fov=SPOTS[spot];eye=np.array(eye);forward=np.array(target)-eye;forward/=np.linalg.norm(forward)
    right=np.cross(forward,(0.,1.,0.));right/=np.linalg.norm(right);up=np.cross(right,forward)
    focal=height/(2*np.tan(np.radians(fov)/2))
    textures={}
    for mat,row in ml.texture_rows(rec).items():textures[mat]=ml.read_p8(decoded,chunk.system_bytes,row)[0]
    if crowd_atlas is not None:textures['crowd']=np.asarray(Image.open(crowd_atlas).convert('RGBA'))
    pixels=np.zeros((height,width,3),dtype=np.uint8);pixels[:]=[26,33,43]
    zbuf=np.full((height,width),1e20);wires=[]
    fallback=np.full((1,1,4),255,dtype=np.uint8)
    for s in sc.shapes:
        if s.stride(0)!=12 or s.stride(1)!=10:continue
        P,C,_=model._vertices(s);C=np.asarray(C,dtype=np.float64)
        raw=np.frombuffer(s.streams[1],dtype=np.dtype([('c','u1',4),('uv','<i2',2),('s','<i2')]))['uv'].astype(float)
        UV=raw/np.where(raw<0,32768.,32767.)*np.array(struct.unpack_from('<2f',s.record,0x30))+np.array(struct.unpack_from('<2f',s.record,0x38))
        p=P-eye;z=p@forward;cam=np.column_stack((p@right,p@up,z))
        screen=np.column_stack((width/2+(p@right)*focal/np.maximum(z,1e-6),height/2-(p@up)*focal/np.maximum(z,1e-6),z))
        for sub in s.submeshes:
            mat=sc.materials[sub.material].name
            if mat.startswith('env_'):continue
            for mode,ids in __import__('mod_editor.core.nfl2k5_scne_builder',fromlist=['']).decode_words(sub.words):
              for tri in triangles(mode,ids):
                ix=list(tri);sp=screen[ix]
                if np.linalg.norm(np.cross(P[ix[1]]-P[ix[0]],P[ix[2]]-P[ix[0]]))<1e-7:continue
                if max(sp[:,2])<.5:continue
                if min(sp[:,2])<.5:
                    poly=clip_near(cam[ix],UV[ix],C[ix])
                    for k in range(1,len(poly)-1):
                        projected,uv,colour=map(np.asarray,zip(poly[0],poly[k],poly[k+1]))
                        sp2=np.column_stack((width/2+projected[:,0]*focal/projected[:,2],height/2-projected[:,1]*focal/projected[:,2],projected[:,2]))
                        if mat=='crowd' and crowd_atlas is None:wires.append(sp2)
                        else:draw_triangle(sp2,uv,colour,textures.get(mat,fallback),zbuf,pixels)
                    continue
                if max(sp[:,0])<0 or min(sp[:,0])>=width or max(sp[:,1])<0 or min(sp[:,1])>=height:continue
                if mat=='crowd' and crowd_atlas is None:
                    if np.linalg.norm(np.cross(P[ix[1]]-P[ix[0]],P[ix[2]]-P[ix[0]]))>1e-7:wires.append(sp)
                else:draw_triangle(sp,UV[ix],C[ix],textures.get(mat,fallback),zbuf,pixels)
    # Occlude wire edges by the real scene depth. Never draw an invented fan atlas.
    if wires:draw_wires(np.asarray(wires),zbuf,pixels)
    return Image.fromarray(pixels)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--spots',nargs='+',choices=SPOTS,default=list(SPOTS));p.add_argument('--crowd-atlas',type=Path)
    a=p.parse_args(argv);a.out.mkdir(parents=True,exist_ok=True);data=a.input.read_bytes();frames=[]
    for spot in a.spots:
        im=render(data,spot,crowd_atlas=a.crowd_atlas);d=ImageDraw.Draw(im);d.rectangle((0,0,960,44),fill=(15,18,22));d.text((8,5),f'{a.input.name} {spot} OFFLINE STADIUM ONLY (field omitted)',fill='white');d.text((8,22),'Runtime crowd atlas missing: red wire edges; approximate alpha/lighting' if not a.crowd_atlas else 'Supplied crowd atlas; approximate alpha/lighting; no LOD or sorting simulation',fill='white')
        path=a.out/f'{spot}.png';im.save(path);frames.append((spot,im))
    sheet=Image.new('RGB',(960*2,540*((len(frames)+1)//2)),(15,18,22))
    for i,(_,im) in enumerate(frames):sheet.paste(im,((i%2)*960,(i//2)*540))
    sheet.save(a.out/'contact_sheet.png')
    (a.out/'camera_spots.json').write_text(json.dumps({spot:dict(eye_m=SPOTS[spot][0],target_m=SPOTS[spot][1],vertical_fov_degrees=SPOTS[spot][2]) for spot in a.spots},indent=2)+'\n', newline="\n")
    return 0

if __name__=='__main__':raise SystemExit(main())
