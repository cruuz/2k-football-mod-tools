#!/usr/bin/env python3
"""Reproduce the u1 Patriots texture correction; geometry is read only.

The stripe authoring clips read-only jersey triangles against common shoulder planes. It writes only texture
polygons into the team spec, never positions, indices or UVs. ``author`` applies the corrected stripe coverage to
the exported v0.4 torso while preserving every pixel outside the old/new bands, and writes ten uniformly
registered traced block numerals. The normal-map candidate smooths the coarse mesh relief only in the two
fabric panels; collars, shields, seams, sleeves and alpha are preserved. Compile through the existing writers.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import zlib

import numpy as np
from PIL import Image, ImageFilter, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import nfl2k5_team_2026_art as art


def block_shapes():
    """Normalized outlines traced against the club's 2026 photo-day gallery.

    The distinguishing modern features are the flat-ended 1, broad chamfered bowls and diagonal 7. These are
    explicit authored traces, not an official font file. Photographic folds and perspective are not copied.
    """
    def glyph(width, outer, holes=()):
        return dict(width=width, height=100, contours=[outer], holes=list(holes))
    octagon = [[10,0],[50,0],[60,10],[60,90],[50,100],[10,100],[0,90],[0,10]]
    return {
        "0": glyph(60, octagon, [[[20,20],[40,20],[40,80],[20,80]]]),
        "1": glyph(32, [[13,0],[32,0],[32,100],[12,100],[12,24],[0,24],[0,14]]),
        "2": glyph(60, [[10,0],[50,0],[60,10],[60,43],[20,66],[20,80],[60,80],[60,100],
                         [0,100],[0,54],[40,32],[40,20],[20,20],[20,28],[0,28],[0,10]]),
        "3": glyph(60, [[10,0],[50,0],[60,10],[60,43],[53,50],[60,57],[60,90],[50,100],
                         [10,100],[0,90],[0,72],[20,72],[20,80],[40,80],[40,60],[23,60],
                         [23,40],[40,40],[40,20],[20,20],[20,28],[0,28],[0,10]]),
        "4": glyph(64, [[36,0],[60,0],[60,59],[64,59],[64,79],[60,79],[60,100],[40,100],
                         [40,79],[0,79],[0,58]], [[[19,59],[40,22],[40,59]]]),
        "5": glyph(60, [[0,0],[60,0],[60,28],[40,28],[40,20],[20,20],[20,40],[50,40],
                         [60,50],[60,90],[50,100],[10,100],[0,90],[0,72],[20,72],[20,80],
                         [40,80],[40,60],[10,60],[0,50]]),
        "6": glyph(60, [[10,0],[50,0],[60,10],[60,28],[40,28],[40,20],[20,20],[20,40],
                         [50,40],[60,50],[60,90],[50,100],[10,100],[0,90],[0,10]],
                   [[[20,60],[40,60],[40,80],[20,80]]]),
        "7": glyph(60, [[0,0],[60,0],[60,20],[30,100],[8,100],[38,20],[20,20],[20,29],[0,29]]),
        "8": glyph(60, [[10,0],[50,0],[60,10],[60,43],[53,50],[60,57],[60,90],[50,100],
                         [10,100],[0,90],[0,57],[7,50],[0,43],[0,10]],
                   [[[20,20],[40,20],[40,40],[20,40]], [[20,60],[40,60],[40,80],[20,80]]]),
        "9": glyph(60, [[10,0],[50,0],[60,10],[60,90],[50,100],[10,100],[0,90],[0,72],
                         [20,72],[20,80],[40,80],[40,60],[10,60],[0,50],[0,10]],
                   [[[20,20],[40,20],[40,40],[20,40]]]),
    }


def load_jersey(path):
    """Read a glTF's jersey primitives without changing any vertex or UV."""
    g = json.loads(path.read_text())
    buffers = [(path.parent / b["uri"]).read_bytes() for b in g["buffers"]]
    count = {"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4}
    dtype = {5121:np.uint8,5123:np.uint16,5125:np.uint32,5126:np.float32}
    def read(i):
        a=g["accessors"][i];v=g["bufferViews"][a["bufferView"]];dt=np.dtype(dtype[a["componentType"]])
        k=count[a["type"]];s=v.get("byteStride",dt.itemsize*k)
        return np.ndarray((a["count"],k),dt,buffers[v["buffer"]],
                          offset=v.get("byteOffset",0)+a.get("byteOffset",0),strides=(s,dt.itemsize)).copy()
    names=[m["name"] for m in g["materials"]]
    result=[]
    for mesh in g["meshes"]:
        for p in mesh["primitives"]:
            if names[p["material"]] != "UNIF_jersey": continue
            pos=read(p["attributes"]["POSITION"]);uv=read(p["attributes"]["TEXCOORD_0"])*[512,256]
            indices=read(p["indices"]).ravel()
            if p.get("mode",4)==5:
                triangles=[indices[i:i+3] if i%2==0 else indices[[i+1,i,i+2]] for i in range(len(indices)-2)]
            elif p.get("mode",4)==4:triangles=indices.reshape(-1,3)
            else:raise ValueError("unhandled jersey primitive")
            result += [np.concatenate([pos[t],uv[t]],axis=1) for t in triangles if len(set(t))==3]
    if not result:raise ValueError("body model has no jersey triangles")
    return result


def clip(poly, values):
    """Clip a polygon with per-vertex signed distances (inside <= 0)."""
    output=[]
    for a,b,da,db in zip(poly,np.roll(poly,-1,axis=0),values,np.roll(values,-1)):
        if da<=0:output.append(a)
        if (da<=0)!=(db<=0):output.append(a+(b-a)*(da/(da-db)))
    return np.asarray(output)


def bleed_triangle_edges(polygon, triangle, pixels=1.5):
    """Extend only mesh edges into the UV gutter; keep stripe boundaries fixed.

    Bilinear filtering needs colour beyond an island's last covered texel. Expanding every edge would also
    change the stripe width, so an edge receives padding only when both endpoints lie on an original UV
    triangle edge. Internal triangle padding removes antialias gaps without changing the shared band planes.
    """
    p=np.asarray(polygon,np.float64)
    area=np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1))
    if abs(area)<1e-8:return p
    lines=[]
    for a,b in zip(p,np.roll(p,-1,axis=0)):
        edge=b-a;length=np.linalg.norm(edge)
        if length<1e-8:return p
        pad=0.0
        for c,d in zip(triangle,np.roll(triangle,-1,axis=0)):
            v=d-c;size=np.linalg.norm(v)
            if size and max(abs(np.cross(v,a-c)),abs(np.cross(v,b-c)))/size<1e-5:
                pad=pixels;break
        normal=np.array([edge[1],-edge[0]])/length*np.sign(area)
        lines.append((a+normal*pad,edge))
    result=[]
    for (a,u),(b,v) in zip(lines[-1:]+lines[:-1],lines):
        matrix=np.stack([u,-v],axis=1)
        if abs(np.linalg.det(matrix))<1e-9:return p
        result.append(a+u*np.linalg.solve(matrix,b-a)[0])
    return np.asarray(result)


def stripe_polygons(triangles, colours):
    # cm in the shared rest-pose model. The same scalar on front and back guarantees the shoulder seam joins.
    # Inboard red 2.5 cm, outboard red 2.5 cm, middle 2.25 cm; stop at the upper chest/back panel edge.
    edges=[21.5,24.0,26.25,28.75]
    items=[]
    for colour,low,high in zip(colours,edges[:-1],edges[1:]):
        for triangle in triangles:
            poly=triangle.copy()
            for axis,side in ((1,1),(0,0),(0,1),(0,-1)):
                if not len(poly):break
                if axis==1:dist=63.5-poly[:,1]
                elif side==0:dist=14.0-np.abs(poly[:,0])
                elif side==1:dist=low-(np.abs(poly[:,0])+1.6*np.abs(poly[:,2]))
                else:dist=np.abs(poly[:,0])+1.6*np.abs(poly[:,2])-high
                poly=clip(poly,dist)
            if len(poly)>=3:
                uv=bleed_triangle_edges(poly[:,3:5],triangle[:,3:5])
                items.append(dict(polygon=np.round(uv,6).tolist(),colour=colour))
    return items


def update_spec(source,model,out):
    p=json.loads(source.read_text())
    if p["team"]!="NE":raise ValueError("this authoring recipe owns only NE")
    tris=load_jersey(model)
    for side,k in p["kits"].items():
        k["torso"]["decorations"]=stripe_polygons(tris,["red","white" if side=="home" else "jersey_navy","red"])
        k["arm_digits"]="none"
        k["unif_color"]={"facemask":"#C8102E","turtleneck":k.get("unif_color",{}).get("turtleneck")}
        k["digits"].update(glyph_shapes=block_shapes(),glyph_height=60,glyph_center=[32,32],registration="as_authored",
                            outline="number_silver",outline_frac=.014,outline2="red",outline2_frac=.024)
    p["albedo"]["number_silver"]="#B0B7BC"
    p["sources_u1_b765"]={"font":"https://www.patriots.com/photos/photos-best-of-new-england-patriots-2026-full-uniform-shoot",
                           "trim":"https://www.patriots.com/news/patriots-unveil-new-uniforms-ahead-of-2020-season",
                           "glyphs":"Authored block contours traced from the 2026 photo-day gallery; not an official font file",
                           "body_sha256":hashlib.sha256(model.read_bytes()).hexdigest(),
                           "stripes_cm":{"axis":"abs(rest_position.x)+1.6*abs(rest_position.z)",
                                         "edges":[21.5,24.0,26.25,28.75],"min_y":63.5,
                                         "min_abs_x":14.0,
                                         "uv_triangle_edge_bleed_px":1.5}}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(p,indent=1)+"\n")


def author(spec_path,before,old_spec_path,retail,out):
    spec=art.Spec(spec_path);old=json.loads(old_spec_path.read_text());out.mkdir(parents=True,exist_ok=True)
    edits=[];receipts=[]
    for side,k in spec.data["kits"].items():
        sel=k["selector"];dest=out/sel;dest.mkdir(exist_ok=True)
        baseline=np.asarray(Image.open(before/sel/'torso.png').convert('RGBA')).copy()
        master=art.upscale(baseline.astype(np.float32)/255)
        olditems=old["kits"][side]["torso"]["decorations"]
        mask=np.zeros(master.shape[:2],np.float32)
        for d in olditems+k["torso"]["decorations"]:
            mask=np.maximum(mask,art.polygon_coverage(mask.shape,[(x*4,y*4) for x,y in d["polygon"]]))
        master[mask>0]=np.r_[spec.colour(k["torso"]["base_colour"]),1]
        master=art.decorate(master,spec,k["torso"]["decorations"],None,'torso')
        native=(art.downscale(master)*255+.5).astype(np.uint8)
        scope=mask.reshape(256,4,512,4).max(axis=(1,3))>0
        native[~scope]=baseline[~scope]
        # A global median-cut palette otherwise perturbs rare collar/shield pixels by a few channels.
        # Reserve their exact RGBA entries in the existing importer's explicit metadata option.
        locked=np.unique(baseline[~scope],axis=0).tolist()
        # The pack's original coarse mips were quantized from pre-P8 artwork. Filtering its decoded mip0
        # again changes protected letters and collar details, so carry their original RGBA into the recipe.
        import nfl_tset_png_import as tset
        from nfl_txtr import HEADER,Chunk,decode_chunk
        original=(before.parent/'resources'/f'{sel}.IFF').read_bytes();start=0x70
        header=HEADER.unpack_from(original,start)
        if header[0]!=b'TSET':raise ValueError('unexpected jersey TSET location')
        span=original[start:start+HEADER.size+header[1]]
        clean,mud=tset.decode_tset_levels(decode_chunk(span,Chunk(1,0,header[0].decode(),*header[1:]))[0])
        if clean[0].rgba!=baseline.tobytes():raise ValueError('baseline PNG does not match native jersey pixels')
        for c,m in zip(clean,mud):
            derived=bytes((v*60+50)//100 if i%4!=3 else v for i,v in enumerate(c.rgba))
            if derived!=m.rgba:raise ValueError('native mud palette differs from the approved darken_60 recipe')
        tail=b''.join(x.rgba for x in clean[1:])
        preservation={'scope_bits':base64.b64encode(np.packbits(scope).tobytes()).decode(),
                      'clean_tail_zlib':base64.b64encode(zlib.compress(tail,9)).decode(),
                      'clean_tail_sha256':hashlib.sha256(tail).hexdigest()}
        metadata=PngImagePlugin.PngInfo()
        metadata.add_text('nfl2k5_palette_lock',json.dumps({'schema':'nfl2k5_palette_lock/v1','rgba':locked,
                                                         'preserve_mips':preservation},separators=(',',':')))
        path=dest/'torso.png';Image.fromarray(native).save(path,pnginfo=metadata)
        Image.fromarray((scope*255).astype(np.uint8)).save(dest/'permitted_scope.png')
        receipts.append(dict(selector=sel,kind='torso',changed_pixels=int(np.any(native!=baseline,axis=2).sum()),
                             permitted_pixels=int(scope.sum()),locked_palette_colors=len(locked),
                             outside_identical=bool(np.array_equal(native[~scope],baseline[~scope]))))
        edits.append(dict(kind='torso',asset_code='16',side=sel[2],variant=0,clean_png=str(path),mud_png=None,mud_mode='darken_60'))
        for n in range(10):
            arr=art.author_glyphs(spec,{'_glyphs':k['digits']},retail,f'digit_jersey_{n}','_glyphs')
            path=dest/f'digit_jersey_{n}.png'
            art.save(art.downscale(arr),path,digit_registration='as_authored')
            edits.append(dict(kind='live_number_nameplate',family='jersey_digit',asset_code='16',side=sel[2],variant=0,digit=n,png=str(path)))
            with Image.open(before/sel/f'digit_arm_{n}.png') as current:
                if current.convert('RGBA').getchannel('A').getbbox():
                    raise ValueError(f'{sel}: exported arm digit is visible; verify family mapping before authoring')
        if k.get('unif_color'):
            edits.append(dict(kind='unif_color',selector=sel,facemask=k['unif_color']['facemask'],turtleneck=None))
    (out/'project.json').write_text(json.dumps(dict(schema='nfl2k5_visual_mod_project/v1',purpose='u1 Patriots 2026 texture correction',edits=edits),indent=2,sort_keys=True)+'\n')
    (out/'pixel_scope.json').write_text(json.dumps(receipts,indent=2)+'\n')


def modern_bump(rgba):
    """Opt-in coarse-relief smoothing candidate; this does not author a new knit pattern."""
    if rgba.shape!=(256,512,4):raise ValueError('expected the 512x256 jersey normal map')
    output=rgba.copy()
    # Box boundaries intentionally avoid the shield, collar, shoulder, seam and hem folds.
    for x0,y0,x1,y1 in ((77,98,247,228),(320,100,469,226)):
        patch=rgba[y0:y1,x0:x1,:3]
        smooth=np.asarray(Image.fromarray(patch).filter(ImageFilter.GaussianBlur(.9))).astype(np.float64)
        n=(smooth-127.5)/127.5;n/=np.maximum(np.linalg.norm(n,axis=-1,keepdims=True),1e-6)
        output[y0:y1,x0:x1,:3]=np.clip(n*127.5+127.5,0,255).round().astype(np.uint8)
    return output


def compile_project(project_path,before,out):
    """Compile through the Studio's existing importers; emit exact native spans and decoded previews."""
    from dataclasses import asdict
    import nfl2k5_jersey_png_workflow as defaults
    import nfl_jersey_tset_targets as jersey_targets
    import nfl_jersey_tset_png_import as jersey_import
    import nfl_live_numbers_nameplate_png_import as digit_import
    import nfl_live_numbers_nameplate_targets as digit_targets
    doc=json.loads(project_path.read_text());out.mkdir(parents=True,exist_ok=True)
    spans={};reports=[]
    for edit in doc['edits']:
        if edit['kind']=='unif_color':
            import struct
            sel=edit['selector'];resource=sel+'.IFF';original=(before/resource).read_bytes()
            if original[0:4]!=b'Unif':raise ValueError('unexpected first package chunk')
            start=0x50;before_word=struct.unpack_from('<I',original,start)[0]
            if before_word not in {0xFFA20001,0xFFC8102E}:raise ValueError('unexpected Patriots facemask colour')
            span=struct.pack('<I',0xFFC8102E);path=out/(sel+'_facemask.span');path.write_bytes(span)
            spans.setdefault(resource,[]).append(dict(offset=start,length=4,
                before_sha256=hashlib.sha256(original[start:start+4]).hexdigest(),
                after_sha256=hashlib.sha256(span).hexdigest(),replacement=path.name))
            reports.append(dict(selector=sel,name='facemask',before_argb=f'{before_word:08X}',after_argb='FFC8102E'))
            print(sel,'facemask',4,flush=True)
            continue
        sel=edit['asset_code']+edit['side']+str(edit['variant']);resource=sel+'.IFF'
        name='torso' if edit['kind']=='torso' else 'digit_'+('arm' if edit['family']=='arm_digit' else 'jersey')+'_'+str(edit['digit'])
        if edit['kind']=='torso':
            _,_,_,target=jersey_targets.select_target('16',edit['side'],0,jersey_targets.DEFAULT_REPORT)
            span,previews,receipt=jersey_import.import_png(defaults.DEFAULT_INDEX,defaults.DEFAULT_INVENTORY,
                                                         jersey_targets.DEFAULT_REPORT,target,Path(edit['clean_png']),None,edit['mud_mode'])
        else:
            _,_,target=digit_targets.select_target(edit['family'],'16',edit['side'],0,edit['digit'],digit_targets.DEFAULT_REPORT)
            span,png,receipt=digit_import.build_import(defaults.DEFAULT_INDEX,digit_targets.DEFAULT_REPORT,
                                                      edit['family'],'16',edit['side'],0,edit['digit'],Path(edit['png']))
            previews=[(name+'.png',png)]
        original=(before/resource).read_bytes();start=target.chunk_offset;end=start+target.span_size
        if len(span)!=target.span_size or end>len(original):raise ValueError('stored span geometry changed')
        path=out/(sel+'_'+name+'.span');path.write_bytes(span)
        row=dict(offset=start,length=len(span),before_sha256=hashlib.sha256(original[start:end]).hexdigest(),
                 after_sha256=hashlib.sha256(span).hexdigest(),replacement=path.name)
        spans.setdefault(resource,[]).append(row)
        (out/(sel+'_'+name+'.json')).write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        for i,(_,png) in enumerate(previews):
            dest=out/'decoded'/sel;dest.mkdir(parents=True,exist_ok=True)
            (dest/(name+'.png' if i==0 else name+'_mud.png')).write_bytes(png)
        reports.append(dict(selector=sel,name=name,target=asdict(target),report=receipt))
        print(sel,name,len(span),flush=True)
    (out/'native_manifest.json').write_text(json.dumps(dict(schema='b765/u1/texture-repair/v1',resources=spans),indent=2,sort_keys=True)+'\n')
    (out/'compile_receipts.json').write_text(json.dumps(reports,indent=2,sort_keys=True)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    s=subs.add_parser('update-spec');s.add_argument('--spec',type=Path,required=True);s.add_argument('--body-gltf',type=Path,required=True);s.add_argument('--out',type=Path,required=True)
    s=subs.add_parser('author');s.add_argument('--spec',type=Path,required=True);s.add_argument('--old-spec',type=Path,required=True);s.add_argument('--before',type=Path,required=True);s.add_argument('--retail',type=Path,required=True);s.add_argument('--out',type=Path,required=True)
    s=subs.add_parser('bump-candidate');s.add_argument('--input',type=Path,required=True);s.add_argument('--out',type=Path,required=True)
    s=subs.add_parser('compile');s.add_argument('--project',type=Path,required=True);s.add_argument('--before-resources',type=Path,required=True);s.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.command=='update-spec':update_spec(a.spec,a.body_gltf,a.out)
    elif a.command=='author':author(a.spec,a.before,a.old_spec,a.retail,a.out)
    elif a.command=='compile':compile_project(a.project,a.before_resources,a.out)
    else:
        source=np.asarray(Image.open(a.input).convert('RGBA'));result=modern_bump(source)
        a.out.parent.mkdir(parents=True,exist_ok=True);Image.fromarray(result).save(a.out)
    return 0


if __name__=='__main__':raise SystemExit(main())
