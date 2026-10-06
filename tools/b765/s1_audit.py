#!/usr/bin/env python3
"""Read-only v0.4 stadium measurements. Geometry candidates are not gameplay proof.

python3 tools/b765/s1_audit.py --files DIR --out DIR [--extract DISC]
Exports all venue variants, native texture sheets, and measured crowd/deck crossings.
No source file is modified. Runtime crowd atlases, sorting and LOD need xemu.
SciPy accelerates radius queries when installed; the NumPy fallback has the
same finite-radius selection. Optional accelerators are listed in
packaging/requirements-stadium-audit.txt and are not Studio dependencies.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
try:
    from scipy.spatial import cKDTree
except ImportError:
    cKDTree = None
from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_scne_builder as sb
from mod_editor.core import nfl2k5_sofi_model as model

VENUES = dict(zip([f's{i:02}' for i in range(32)], [
    'State Farm', 'Mercedes-Benz', 'M&T Bank', 'Highmark', 'Bank of America',
    'Soldier Field', 'Paycor', 'AT&T', 'Cleveland', 'Empower Field', 'Lambeau',
    'Lucas Oil', 'EverBank', 'Arrowhead', 'Hard Rock', 'U.S. Bank', 'Gillette',
    'Caesars Superdome', 'MetLife Giants', 'MetLife Jets', 'Allegiant',
    'Lincoln Financial', 'Acrisure', 'SoFi Rams', 'SoFi Chargers', "Levi's",
    'Lumen', 'Raymond James', 'Nissan', 'Northwest', 'Houston', 'Tennessee alternate'
]))
# Native s28/s29/s30/s31 identities are resolved from local venue table below.
VENUES.pop('s31')
VENUES.update(s08='Empower Field at Mile High',s09='Ford Field',s28='Nissan Stadium',s29='Northwest Stadium',s30='Huntington Bank Field',s37='Reliant Stadium',s40='Super Bowl SoFi')
# Extra extracted neutral slots stay auditable but never count as home venues.
EXTRA_VENUES={'s31':'Aloha Stadium (neutral auxiliary; not a team home venue)'}
sha = lambda b: hashlib.sha256(b).hexdigest()
AUDIT_VERSION=3
GEOMETRY_CACHE={}


class _NumpyRadiusIndex:
    """Portable candidate selection for the optional offline audit."""
    def __init__(self, centres):
        self.centres = np.asarray(centres)

    def query_ball_point(self, point, radius):
        return np.flatnonzero(np.linalg.norm(self.centres-point, axis=1) <= radius).tolist()


def _spatial_index(centres):
    return cKDTree(centres) if cKDTree is not None else _NumpyRadiusIndex(centres)


def geometry_sha(sc):
    h=hashlib.sha256()
    for s in sc.shapes:
        h.update(s.name.encode());h.update(s.record[0x30:0x40])
        h.update(s.streams[0] or b'')
        if s.stride(1)==10 and s.streams[1]:
            h.update(np.frombuffer(s.streams[1],dtype='u1').reshape(-1,10)[:,4:].tobytes())
        for sub in s.submeshes:
            h.update(sc.materials[sub.material].name.encode());h.update(sub.words)
    for n in sc.nodes:h.update(n.matrix14);h.update(n.matrix1c)
    return h.hexdigest()


def triangles(mode, ids):
    if mode == sb.TRIANGLE_STRIP:
        for k in range(len(ids)-2):
            a,b,c = ids[k:k+3]
            yield (b,a,c) if k % 2 else (a,b,c)
    elif mode == 5:  # NV2A TRIANGLES
        for k in range(0, len(ids)-2, 3):
            yield tuple(ids[k:k+3])
    elif mode == 7:  # NV2A TRIANGLE_FAN
        for k in range(1, len(ids)-1):
            yield (ids[0], ids[k], ids[k+1])


def segment_hits(a, b, tris, eps=1e-7):
    """Exact finite-segment/triangle intersections, excluding endpoints/coplanarity."""
    d = b-a
    e1, e2 = tris[:,1]-tris[:,0], tris[:,2]-tris[:,0]
    h = np.cross(np.broadcast_to(d,e2.shape), e2)
    det = np.einsum('ij,ij->i',e1,h)
    safe = np.abs(det)>eps
    inv = np.divide(1.,det,out=np.zeros_like(det),where=safe)
    s = a-tris[:,0]
    u = inv*np.einsum('ij,ij->i',s,h)
    q = np.cross(s,e1)
    v = inv*np.einsum('j,ij->i',d,q)
    t = inv*np.einsum('ij,ij->i',e2,q)
    return np.flatnonzero(safe & (u>=-eps) & (v>=-eps) & (u+v<=1+eps) & (t>1e-4) & (t<1-1e-4))


def scene_data(data):
    chunk = ml.bundle_scenes(data)['stadium']
    rec, decoded = ml._scene(data,chunk)
    return chunk,rec,decoded,sb.parse(decoded,chunk.system_bytes)


def crowd_pair_crossings(data):
    """Non-coplanar billboard piercings; transparency/visibility are unproved.

    Adjacent strip faces and zero-area connectors are not separate intersecting
    billboards. Coincident/coplanar faces are covered by the duplicate audit.
    """
    _,_,_,sc=scene_data(data)
    points=[];identities=[];edge_map={}
    for si,s in enumerate(sc.shapes):
        if s.stride(0)!=12 or s.stride(1)!=10:continue
        P,_,_=model._vertices(s)
        for sj,sub in enumerate(s.submeshes):
            if sc.materials[sub.material].name!='crowd':continue
            for mode,ids in sb.decode_words(sub.words):
                for tri in triangles(mode,ids):
                    if np.linalg.norm(np.cross(P[tri[1]]-P[tri[0]],P[tri[2]]-P[tri[0]]))<1e-7:continue
                    points.append(P[list(tri)])
                    identities.append(dict(shape=si,name=s.name,submesh=sj,vertices=list(tri)))
                    for a,b in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0])):
                        a,b=sorted((a,b));edge_map[(si,sj,a,b)]=(P[a],P[b])
    if not points:return []
    tris=np.asarray(points);centres=tris.mean(1)
    radii=np.linalg.norm(tris-centres[:,None,:],axis=2).max(1)
    tree=_spatial_index(centres);maxradius=float(radii.max());result=[]
    for (si,sj,a,b),(start,end) in edge_map.items():
        midpoint=(start+end)/2;half=np.linalg.norm(end-start)/2
        candidates=np.asarray(tree.query_ball_point(midpoint,half+maxradius+1e-3),dtype=int)
        if not len(candidates):continue
        candidates=candidates[np.linalg.norm(centres[candidates]-midpoint,axis=1)<=radii[candidates]+half+1e-3]
        for hit in candidates[segment_hits(start,end,tris[candidates])]:
            other=identities[hit]
            if si==other['shape'] and {a,b}&set(other['vertices']):continue
            result.append(dict(crowd_edge=dict(shape=si,name=sc.shapes[si].name,submesh=sj,vertices=[a,b]),
                crowd_triangle=other,edge_start_m=start.tolist(),edge_end_m=end.tolist()))
    return result


def atlas_crossing_samples(data,crossings,atlas_path):
    """Sample one supplied atlas frame at measured crowd/surface intersections.

    This does not simulate NV2A filtering, animated frames or visibility.
    """
    _,_,_,sc=scene_data(data)
    atlas=np.asarray(Image.open(atlas_path).convert('RGBA'));samples=[]
    for cross in crossings:
        s=sc.shapes[cross['crowd']['shape']];P,_,_=model._vertices(s)
        a,b=cross['crowd']['vertices'];start,end=P[[a,b]]
        surf=sc.shapes[cross['surface']['shape']];Q,_,_=model._vertices(surf)
        tri=Q[cross['surface']['vertices']]
        d=end-start;e1,e2=tri[1]-tri[0],tri[2]-tri[0]
        h=np.cross(d,e2);det=e1@h;q=np.cross(start-tri[0],e1);t=e2@q/det
        raw=np.frombuffer(s.streams[1],dtype=np.dtype([('c','u1',4),('uv','<i2',2),('s','<i2')]))['uv'].astype(float)
        uv=raw/np.where(raw<0,32768.,32767.)*np.array(struct.unpack_from('<2f',s.record,0x30))+np.array(struct.unpack_from('<2f',s.record,0x38))
        hituv=uv[a]*(1-t)+uv[b]*t
        x,y=int(hituv[0]%1*atlas.shape[1]),int(hituv[1]%1*atlas.shape[0])
        samples.append(dict(**cross,intersection_m=(start+t*d).tolist(),uv=hituv.tolist(),
            atlas_texel=[x,y],atlas_alpha=int(atlas[y,x,3])))
    return dict(schema='b765_s1_atlas_crossing_samples/v1',bundle_sha256=sha(data),
        atlas=str(atlas_path),atlas_sha256=sha(atlas_path.read_bytes()),
        proof='offline intersection and nearest texel in one supplied frame; game filtering/depth/occlusion unproved',
        pairs=len(samples),opaque_pairs=sum(s['atlas_alpha']>0 for s in samples),
        transparent_pairs=sum(s['atlas_alpha']==0 for s in samples),samples=samples)


def measure(data, filename):
    c,rec,decoded,sc = scene_data(data)
    geometry_digest=geometry_sha(sc)
    if geometry_digest in GEOMETRY_CACHE:
        row=deepcopy(GEOMETRY_CACHE[geometry_digest])
        row.pop('texture_alpha',None)
        row.update(name=filename,venue=VENUES.get(filename[:3],EXTRA_VENUES.get(filename[:3],filename[:3])),
            time_of_day={'d':'day','a':'afternoon','n':'night'}[filename[3]],weather={'d':'dry','r':'rain','s':'snow'}[filename[4]],
            before_sha256=sha(data),after_sha256=sha(data),screenshots_before=[],screenshots_after=[],contact_sheet=None,
            scene=dict(offset=c.offset,stored_length=32+c.stored_size,sha256=sha(data[c.offset:c.end_offset]),decoded_sha256=sha(decoded),system=c.system_bytes,video=c.video_bytes))
        row['material_classes']={m.name:[*model._class_of(m)] for m in sc.materials if m.name=='crowd' or m.name.endswith(('rail','truss'))}
        return row,rec,decoded
    crowd_edges, deck, deck_ids, density, heights, degenerate = [],[],[],[],[],0
    counts, duplicate_keys, duplicate_pairs = {},{},[]
    shapes = []
    for si,s in enumerate(sc.shapes):
        if s.stride(0)!=12 or s.stride(1)!=10:
            continue
        P, colours, _ = model._vertices(s)
        lane=np.frombuffer(s.streams[1],dtype=np.dtype([('colour','u1',4),('uv','<i2',2),('selector','<i2')]))['uv'].astype(float)
        scale=np.asarray(struct.unpack_from('<2f',s.record,0x30))
        offset=np.asarray(struct.unpack_from('<2f',s.record,0x38))
        UV=lane/np.where(lane<0,32768.,32767.)*scale+offset
        used_crowd = set()
        for sj,sub in enumerate(s.submeshes):
            mat = sc.materials[sub.material].name
            for mode,ids in sb.decode_words(sub.words):
                counts[mat] = counts.get(mat,0) + len(ids)
                if mat=='crowd':
                    visible_tris=[tri for tri in triangles(mode,ids)
                        if np.linalg.norm(np.cross(P[tri[1]]-P[tri[0]],P[tri[2]]-P[tri[0]]))>=1e-7]
                    edges = sorted({tuple(sorted(e)) for tri in visible_tris
                                    for e in ((tri[0],tri[1]),(tri[1],tri[2]),(tri[2],tri[0]))})
                    used_crowd.update(ids)
                    for a,b in edges:
                        du,dv = np.abs(UV[a]-UV[b])
                        dist = float(np.linalg.norm(P[a]-P[b]))
                        if du < 2e-4 and dv>1e-5 and dist>1e-4:
                            density.append(dist/float(dv))
                        if du>0.15 and dv<2e-3:
                            heights.append(float(abs(P[a,1]-P[b,1])))
                        if dist>1e-4:
                            crowd_edges.append((P[a],P[b],dict(shape=si,name=s.name,submesh=sj,vertices=[a,b])))
                for tri in triangles(mode,ids):
                    points = P[list(tri)]
                    if np.linalg.norm(np.cross(points[1]-points[0],points[2]-points[0]))<1e-7:
                        if mat=='crowd': degenerate+=1
                        continue
                    if mat=='crowd':
                        key=tuple(sorted(tuple(p) for p in points))
                        ident=dict(shape=si,name=s.name,submesh=sj,vertices=list(tri))
                        if key in duplicate_keys: duplicate_pairs.append([duplicate_keys[key],ident])
                        else: duplicate_keys[key]=ident
                    elif any(x in mat.lower() for x in ('seat','deck','concrete','rail','portal','stairs','soffit')) and not mat.startswith('env_'):
                        deck.append(points)
                        deck_ids.append(dict(shape=si,name=s.name,submesh=sj,material=mat,vertices=list(tri)))
        if used_crowd:
            shapes.append(dict(shape=si,name=s.name,vertices=len(used_crowd),
                minimum=np.round(P[list(used_crowd)].min(0),3).tolist(),maximum=np.round(P[list(used_crowd)].max(0),3).tolist()))
    crossings=[]
    if deck:
        deck=np.asarray(deck)
        centres=deck.mean(1)
        radii=np.linalg.norm(deck-centres[:,None,:],axis=2).max(1)
        tree=_spatial_index(centres)
        maxradius=float(radii.max())
        seen=set()
        for a,b,ident in crowd_edges:
            centre=(a+b)/2
            half=np.linalg.norm(b-a)/2
            ids=np.asarray(tree.query_ball_point(centre,half+maxradius+1e-3),dtype=int)
            if not len(ids):continue
            ids=ids[np.linalg.norm(centres[ids]-centre,axis=1)<=radii[ids]+half+1e-3]
            if not len(ids):continue
            for hit in ids[segment_hits(a,b,deck[ids])]:
                key=(ident['shape'],tuple(ident['vertices']),int(hit))
                if key in seen:continue
                seen.add(key)
                crossings.append(dict(crowd=ident,surface=deck_ids[hit],edge_start_m=np.round(a,5).tolist(),edge_end_m=np.round(b,5).tolist()))
    density=np.asarray(density)
    heights=np.asarray(heights)
    row=dict(audit_version=AUDIT_VERSION,geometry_sha256=geometry_digest,name=filename,venue=VENUES.get(filename[:3],EXTRA_VENUES.get(filename[:3],filename[:3])),time_of_day={'d':'day','a':'afternoon','n':'night'}[filename[3]],
        weather={'d':'dry','r':'rain','s':'snow'}[filename[4]],before_sha256=sha(data),after_sha256=sha(data),
        action='unchanged_pending_geometry_review',source='v0.4 exact stored bytes',proof='offline_native_measurements',
        screenshots_before=[],screenshots_after=[],contact_sheet=None,
        runtime_checks=dict(alpha_sorting='not_observed',lod_pop='not_observed',crowd_atlas='runtime_generated_not_in_stadium_scene'),
        scene=dict(offset=c.offset,stored_length=32+c.stored_size,sha256=sha(data[c.offset:c.end_offset]),decoded_sha256=sha(decoded),system=c.system_bytes,video=c.video_bytes),
        crowd_shapes=shapes,crowd_vertex_references=counts.get('crowd',0),
        crowd_band_height_m=dict(min=float(heights.min()),median=float(np.median(heights)),max=float(heights.max())) if len(heights) else {},
        crowd_repeat_metres=dict(samples=len(density),min=float(density.min()),median=float(np.median(density)),max=float(density.max()),
            median_ratio_to_9_14=float(np.median(density)/9.14)) if len(density) else {},
        crowd_degenerate_triangles=degenerate,exact_duplicate_crowd_triangles=duplicate_pairs,
        crowd_surface_crossings=crossings,issue_list=[])
    if crossings: row['issue_list'].append(dict(kind='geometry_edge_surface_crossing',count=len(crossings),
        fix='coordinator geometry handoff',evidence='finite crowd triangle edges pierce seating/deck triangles; visibility requires xemu'))
    if duplicate_pairs: row['issue_list'].append(dict(kind='exact_duplicate_crowd_triangles',count=len(duplicate_pairs),fix='coordinator geometry handoff'))
    if len(density) and np.median(density)>9.14*1.1:
        row['issue_list'].append(dict(kind='crowd_uv_density_wide',fix='coordinator UV handoff',median_ratio=float(np.median(density)/9.14)))
    row['material_classes']={m.name:[*model._class_of(m)] for m in sc.materials if m.name=='crowd' or m.name.endswith(('rail','truss'))}
    GEOMETRY_CACHE[geometry_digest]=deepcopy(row)
    return row,rec,decoded


def texture_sheet(filename,rec,decoded,out):
    """Native source pixels only; the runtime crowd atlas has no static substitute."""
    rows=ml.texture_rows(rec)
    picks=[(m,r) for m,r in rows.items() if any(k in m.lower() for k in ('seat','deck','rail','roof','concrete','truss','glass','ribbon','score'))]
    if not picks: picks=list(rows.items())[:24]
    picks=picks[:32]
    w,h=960,50+((len(picks)+3)//4)*175
    im=Image.new('RGB',(w,h),(25,28,33)); d=ImageDraw.Draw(im)
    d.text((10,10),f'{filename} — native v0.4 stadium textures (offline; unchanged)',fill='white')
    alpha=[]
    for i,(mat,r) in enumerate(picks):
        a,_=ml.read_p8(decoded,int(rec['system_bytes']),r)
        alpha.append(dict(material=mat,width=int(r['width']),height=int(r['height']),transparent_pixels=int((a[:,:,3]==0).sum()),partial_alpha_pixels=int(((a[:,:,3]>0)&(a[:,:,3]<255)).sum())))
        thumb=Image.fromarray(a,'RGBA');thumb.thumbnail((224,135))
        tile=Image.new('RGBA',(224,135),(100,100,100,255));tile.alpha_composite(thumb,((224-thumb.width)//2,(135-thumb.height)//2))
        x,y=(i%4)*240+8,48+(i//4)*175
        im.paste(tile.convert('RGB'),(x,y));d.text((x,y+138),mat[:34],fill='white')
        d.text((x,y+153),f"{r['width']}x{r['height']} P8",fill=(180,190,200))
    dest=out/f'{filename}.textures.png';im.save(dest)
    return str(dest),alpha


def extract(disc,files,out):
    manifest_path=out/'stadium_extraction_manifest.json'
    doc=json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(schema='b765_s1_extraction/v1',source=str(disc),entries=[])
    known={r['name']:r for r in doc['entries']}
    with ml._outer_image()(str(disc)) as archive:
        byid={e.name_id:e for e in archive.entries}
        for prefix in ['s07']+[v for v in VENUES if v!='s07']:
            for tod in 'dan':
                for weather in 'drs':
                    name=f'{prefix}{tod}{weather}.iff';target=files/name
                    if name in known and target.exists() and sha(target.read_bytes())==known[name]['sha256']:continue
                    e=byid[ml.name_id(name)];raw=archive.read(e.virtual_offset,e.size)
                    target.write_bytes(raw)
                    known[name]=dict(name=name,outer_index=e.index,name_id=e.name_id,virtual_offset=e.virtual_offset,size=e.size,sha256=sha(raw),path=str(target))
    doc['entries']=list(known.values());manifest_path.write_text(json.dumps(doc,indent=2)+'\n', newline="\n")


def audit_group(files,out,names):
    result=[]
    for name in names:
        row,rec,decoded=measure((files/name).read_bytes(),name)
        if name[4]=='d':row['contact_sheet'],row['texture_alpha']=texture_sheet(name,rec,decoded,out)
        result.append(row)
    return result


def migrate_exact_duplicates(row,data):
    """A rounded match is only a candidate; confirm exact native coordinate equality."""
    pairs=row.get('exact_duplicate_crowd_triangles',[])
    if pairs:
        _,_,_,sc=scene_data(data);confirmed=[]
        for pair in pairs:
            points=[]
            for tri in pair:
                s=sc.shapes[tri['shape']]
                P=np.frombuffer(s.streams[0],dtype='<f4').reshape(-1,3)
                points.append(sorted(tuple(p) for p in P[tri['vertices']]))
            if points[0]==points[1]:confirmed.append(pair)
        row['exact_duplicate_crowd_triangles']=confirmed
        row['issue_list']=[issue for issue in row['issue_list'] if issue['kind']!='exact_duplicate_crowd_triangles']
        if confirmed:row['issue_list'].append(dict(kind='exact_duplicate_crowd_triangles',count=len(confirmed),fix='coordinator geometry handoff'))
    row['duplicate_coordinate_comparison']='exact native local FLOAT3 values; runtime z-fighting unproved'
    row['audit_version']=AUDIT_VERSION


def load_report(path):
    report=json.loads(path.read_text());cache={}
    for row in report['venues'].values():
        if row.get('geometry_diagnostics_file'):
            p=Path(row['geometry_diagnostics_file'])
            if p not in cache:cache[p]=json.loads(p.read_text())
            row.update(cache[p])
    return report


def save_report(path,report):
    """Keep the per-variant audit reviewable; share full native-ID geometry lists."""
    document={**report,'venues':{}};written=set();folder=path.parent/'geometry_diagnostics';folder.mkdir(exist_ok=True)
    fields=('crowd_shapes','exact_duplicate_crowd_triangles','crowd_surface_crossings','crowd_crowd_crossings')
    for name,row in report['venues'].items():
        diagnostic=folder/f"{row['geometry_sha256']}.v{row['audit_version']}.json"
        if diagnostic not in written:
            diagnostic.write_text(json.dumps({k:row[k] for k in fields if k in row},indent=2)+'\n', newline="\n");written.add(diagnostic)
        document['venues'][name]={**{k:v for k,v in row.items() if k not in fields},
            'geometry_diagnostics_file':str(diagnostic),
            'crowd_surface_crossing_count':len(row['crowd_surface_crossings']),
            'exact_duplicate_crowd_triangle_count':len(row['exact_duplicate_crowd_triangles'])}
        if 'crowd_crowd_crossings' in row:
            document['venues'][name]['crowd_crowd_crossing_count']=len(row['crowd_crowd_crossings'])
    path.write_text(json.dumps(document,indent=2)+'\n', newline="\n")


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--files',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--extract',type=Path);p.add_argument('--names',nargs='*');p.add_argument('--workers',type=int,default=1);p.add_argument('--crowd-pairs-only',action='store_true',help='Add non-coplanar crowd/crowd piercings to existing native audit rows');p.add_argument('--atlas-crossing-samples',type=Path,help='Sample a supplied atlas at cached native crowd/deck intersections; no resource writes');p.add_argument('--near-coplanar-only',action='store_true',help='Write separate geometry overlap candidates and compact summary; preserve stadium_audit.json')
    a=p.parse_args(argv)
    if a.near_coplanar_only:
        if a.extract or a.crowd_pairs_only or a.atlas_crossing_samples:
            p.error('--near-coplanar-only cannot be combined with extraction or other measurement modes')
        from tools.b765 import s1_coplanar
        names=a.names or [x.name for x in sorted(a.files.glob('s*.iff'),key=lambda p:(not p.name.startswith('s07'),p.name))]
        s1_coplanar.run(a.files,names,a.out/'near_coplanar_crowd_pairs.json',summary=a.out/'near_coplanar_summary.json')
        return 0
    a.files.mkdir(parents=True,exist_ok=True);a.out.mkdir(parents=True,exist_ok=True)
    if a.extract:extract(a.extract,a.files,a.out)
    report_path=a.out/'stadium_audit.json'
    report=load_report(report_path) if report_path.exists() else dict(schema='b765_s1_stadium_audit/v1',proof='offline only; screenshots populated by s1_capture.py',venues={})
    report['target_venue_codes']=list(VENUES)
    report['extra_venue_codes']=list(EXTRA_VENUES)
    for name,row in report['venues'].items():row['venue']=VENUES.get(name[:3],EXTRA_VENUES.get(name[:3],name[:3]))
    for name,row in report['venues'].items():
        if row.get('audit_version')==2 and sha((a.files/name).read_bytes())==row['before_sha256']:
            migrate_exact_duplicates(row,(a.files/name).read_bytes())
    names=a.names or [x.name for x in sorted(a.files.glob('s*.iff'),key=lambda p:(not p.name.startswith('s07'),p.name))]
    if a.atlas_crossing_samples:
        for name in names:
            row=report['venues'][name];data=(a.files/name).read_bytes()
            if sha(data)!=row['before_sha256']:raise ValueError(f'{name}: audit source hash differs')
            doc=atlas_crossing_samples(data,row['crowd_surface_crossings'],a.atlas_crossing_samples)
            doc['disc_file']=name;dest=a.out/f'{name}.atlas_crossing_samples.json'
            dest.write_text(json.dumps(doc,indent=2)+'\n', newline="\n")
            print(name,'opaque sampled crossings',doc['opaque_pairs'],'of',doc['pairs'],flush=True)
        return 0
    if a.crowd_pairs_only:
        cache={}
        for name in names:
            row=report['venues'][name];data=(a.files/name).read_bytes()
            if sha(data)!=row['before_sha256']:raise ValueError(f'{name}: audit source hash differs')
            key=row['geometry_sha256']
            if key not in cache:cache[key]=crowd_pair_crossings(data)
            row['crowd_crowd_crossings']=cache[key]
            row['crowd_crowd_crossing_interpretation']='non-coplanar finite-edge piercings; opaque overlap and visibility unproved'
            print(name,'crowd/crowd pairs',len(cache[key]),flush=True)
        # Propagate the same measurements to variants with identical geometry.
        for row in report['venues'].values():
            if row['geometry_sha256'] in cache:row['crowd_crowd_crossings']=cache[row['geometry_sha256']]
        save_report(report_path,report)
        return 0
    if a.workers>1:
        groups={}
        for name in names:
            old=report['venues'].get(name)
            if old and old.get('audit_version')==AUDIT_VERSION and old['before_sha256']==sha((a.files/name).read_bytes()):continue
            groups.setdefault(name[:3],[]).append(name)
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            jobs=[pool.submit(audit_group,a.files,a.out,names) for names in groups.values()]
            for job in as_completed(jobs):
                for row in job.result():
                    report['venues'][row['name']]=row
                    print(row['name'],'crossings',len(row['crowd_surface_crossings']),'UV',row['crowd_repeat_metres'].get('median'),flush=True)
                save_report(report_path,report)
        save_report(report_path,report)
        return 0
    for name in names:
        data=(a.files/name).read_bytes();old=report['venues'].get(name)
        if old and old.get('audit_version')==AUDIT_VERSION and old['before_sha256']==sha(data):
            GEOMETRY_CACHE[old['geometry_sha256']]=deepcopy(old)
            continue
        row,rec,decoded=measure(data,name)
        if name[4]=='d': row['contact_sheet'],row['texture_alpha']=texture_sheet(name,rec,decoded,a.out)
        report['venues'][name]=row
        save_report(report_path,report)
        print(name,'crossings',len(row['crowd_surface_crossings']),'UV',row['crowd_repeat_metres'].get('median'),'duplicates',len(row['exact_duplicate_crowd_triangles']),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
