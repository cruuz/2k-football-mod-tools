#!/usr/bin/env python3
"""Export one actual decoded Anniversary field for Blender's offline top view.

Uses the repository's topology decoder and shader-proved native UV helpers.
This is an offline model render, never a game screenshot.
"""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_modern_metlife as mm
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core.nfl2k5_models import _shape_lanes,read_lane_2h,read_positions,uv_to_gltf
from nfl_scne_gltf import decode_batches,gltf_topology
from PIL import Image

def export(source,out):
 raw=Path(source).read_bytes();tx=mm._tools()[0];chunk=tx.parse_chunks(raw,allow_trailing=True)[0];rec,decoded=mm._scene(raw,chunk)
 out=Path(out);out.mkdir(parents=True,exist_ok=True);textures={}
 rows=mv.p8_rows(rec)
 for name,index in mv.rows_by_material(rec).items():
  row=rows.get(index)
  if row:
   p=out/(name+'.png');Image.fromarray(mv.read_texture(decoded,rec,row)).save(p);textures[name]=str(p.resolve())
 meshes=[]
 for shape in rec['shapes']:
  lanes=_shape_lanes(rec,shape,decoded);positions=read_positions(decoded,shape,lanes)
  pairs=read_lane_2h(decoded,shape,lanes.texcoord,lanes.vertex_count);uv=[uv_to_gltf(u,v,lanes.uv_scale,lanes.uv_offset) for u,v in pairs]
  for sub in rec['submeshes']:
   if sub['shape_index']!=shape['index']:continue
   triangles=[]
   for mode,indices in decode_batches(decoded,sub['command_offset'],sub['primary_command_word_count']):
    topology,ix,_=gltf_topology(mode,indices)
    if topology==4:triangles.extend([ix[i:i+3]for i in range(0,len(ix),3)])
    elif topology==5:
     for i in range(len(ix)-2):triangles.append([ix[i+1],ix[i],ix[i+2]]if i%2 else[ix[i],ix[i+1],ix[i+2]])
    elif topology==6:
     triangles.extend([[ix[0],ix[i],ix[i+1]]for i in range(1,len(ix)-1)])
   if triangles:meshes.append(dict(name=shape['name']+'_'+sub['material_name'],material=sub['material_name'],positions=positions,uv=uv,triangles=triangles))
 (out/'scene.json').write_text(json.dumps(dict(textures=textures,meshes=meshes)))
 return out/'scene.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');a=p.parse_args();print(export(a.source,a.output))
