"""Bounded final-eye capture and 53-model stadium survey; no game boot or display."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_camera as camera, nfl2k5_widescreen as wide
from tools.nfl2k5_camera_broadcast_proof import BroadcastProjection
from tools.nfl2k5_camera_far_proof import float_word, RETAIL_SHA256


class FinalProjection(BroadcastProjection):
    def frame(self, ball, *, direction=1, snap=False):
        h, uc = self.h, self.uc
        uc.mem_write(h.AUX, struct.pack('<4f', *ball, 1))
        uc.mem_write(0xA82CC4, struct.pack('<I', int(snap)))
        h.execute(uc, 0x5F760, ecx=0, edx=h.SRC, args=(float_word(1/30), h.AUX,
                  h.AUX+16, h.AUX+32, h.AUX+48, float_word(direction)))
        self.eye, self.target = h.f(uc, 0xA82BF0, 3), h.f(uc, 0xA82C00, 3)
        h.activate(uc, source=h.SRC)
        return dict(ball=list(ball), eye=self.eye, target=self.target,
                    desired_eye=h.f(uc, 0xA82C60, 3), filter_eye=h.f(uc, 0xA82C70, 3))


def historical(retail, revision):
    """Exact v5.4 installation; v5.3 uses its original native setup callback."""
    requests = ((camera.OWNER, 'code', 208, 16), (camera.OWNER, 'read_only', 80, 16))
    allocated = camera.space.apply(retail, requests, scaleout=True)[0]
    code = camera.allocation(allocated, revision=54)
    result = camera.space.install_code(allocated, camera.OWNER, camera.code_for(code['va'], 54))[0]
    result = camera.space.install_read_only(result, camera.OWNER, camera.broadcast_records(code['va'], 54))[0]
    buf = bytearray(result)
    for _, off, _, after in camera._sites(result, camera.DEFAULT_PRESET, 54):
        buf[off:off+len(after)] = after
    if revision == 'v5.3':
        ro = camera.allocation(result, 'read_only', 54)
        struct.pack_into('<I', buf, ro['raw']+0x40, 0xA40C0)
    for section in camera._sections(buf):
        buf[section.header_offset+36:section.header_offset+56] = camera.section_digest(buf, section)
    # Allocator seals include the immutable bytes (descriptor differs in v5.3).
    camera.space._seal_scaleout(buf, camera.space._validate(allocated)[2])
    return bytes(buf)


def capture(retail):
    from tools.nfl2k5_camera_stadium_survey import GRID_X, GRID_Z
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise ValueError('pinned USA retail executable required')
    current = camera.apply(retail)[0]
    cases, samples = {}, []
    for revision in ('v5.3', 'v5.4', 'v6'):
        payload = current if revision == 'v6' else historical(retail, revision)
        p = FinalProjection(wide.apply(payload, '16:9')[0])
        ro = next(a for a in camera.space.layout(payload)['allocations'] if a['owner']==camera.OWNER and a['kind']=='read_only')['va']
        rows = []
        for state in ((9, 17, 15, 7) if revision == 'v6' else (9,)):
            for d in (1, -1):
                p.setup(ro + (80*camera.broadcast_slot(state) if revision=='v6' else 0), direction=d)
                lens = p.metrics['lens_word']
                samples.append(dict(revision=revision,state=state,direction=d,metrics=p.metrics,
                    points={name:p.point(x,y,z*d) for name,x,y,z in
                            [('ball',0,0,0),('near_wideout',2200,175,0),('far_wideout',-2200,175,0),
                             ('backfield',0,0,-700),('deep_receiver',0,175,2500)]}))
                for bz in GRID_Z:
                    for bx in GRID_X:
                        rows.append(dict(state=state,direction=d,bx=bx,bz=bz,lens=lens,kind='settled',
                                         **p.frame((bx,0.,bz),direction=d,snap=True)))
        cases[revision] = rows
    # Run ordinary moving updates and inherited PAT/goal-post eyes, including
    # elevated balls. Every recorded eye is the native output after smoothing.
    transient=[]
    p=FinalProjection(wide.apply(current,'16:9')[0]); table=camera.read_preset_table(current)[7]
    for d in (1,-1):
        for state in (7,8,9,10,11,12,13,14,15,16,17,18,19):
            p.setup(table[state][1],direction=d)
            # Deliberately inherit a bad sideline/corner eye and velocity.
            for va in (0xA82BF0,0xA82C70):
                p.uc.mem_write(va,struct.pack('<4f',7300.,365.,5936.*d,1.))
            p.uc.mem_write(0xA82C80,struct.pack('<4f',2000.,-1500.,3000.*d,0.))
            for n in range(120):
                bx=min(2400,n*40); bz=(5400-n*90)*d
                row=p.frame((bx,2000. if state in (13,14,15) else 0.,bz),direction=d)
                transient.append(dict(state=state,direction=d,bx=bx,bz=bz,lens=p.metrics['lens_word'],kind='transition',**row))
    cases['v6_transitions']=transient
    return dict(schema='nfl2k5_presentation_native/v6',retail_sha256=RETAIL_SHA256,
                runtime_witnessed=False,projection_samples=samples,cases=cases)


def survey_one(args):
    import numpy as np
    from tools import nfl2k5_camera_stadium_survey as s
    path,native_path=args
    tri,labels,hashes=s.load_triangles(Path(path)); tree=s.bvh(tri,labels)
    native=json.loads(Path(native_path).read_text())
    revisions={}
    for revision,rows in native['cases'].items():
        results=[]
        for row in rows:
            field,occluded=s.frame(tree,np.array(row['eye']),np.array(row['target']),row['lens'])
            results.append(dict(bx=row['bx'],field_pixels=field,occluded_pixels=occluded))
        revisions[revision]=s.summarize(results)
        revisions[revision]['max_occluded_percent']=max(100*r['occluded_pixels']/max(1,r['field_pixels']) for r in results)
        revisions[revision]['empty_field_frames']=sum(r['field_pixels']==0 for r in results)
    return dict(scene=Path(path).stem,source_sha256=hashes,triangles=len(tri),revisions=revisions)


def survey(cache, native_path, output, workers=4):
    paths=[]
    for outer in range(3136,3189):
        choices=sorted((Path(cache)/'models').glob(f'{outer}_*_stadium.gltf'))
        if len(choices)!=1:raise ValueError(f'expected one stadium {outer}')
        paths.append(choices[0])
    rows=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(survey_one,((p,native_path) for p in paths)):
            rows.append(row);print(row['scene'],row['revisions'],flush=True)
    totals={}
    for revision in rows[0]['revisions']:
        totals[revision]={}
        for band in ('whole_grid','between_numbers','between_hashes'):
            frames=sum(r['revisions'][revision][band]['frames'] for r in rows)
            dirty=sum(r['revisions'][revision][band]['dirty_frames'] for r in rows)
            totals[revision][band]=dict(frames=frames,dirty_frames=dirty,dirty_percent=100*dirty/frames)
    result=dict(schema='nfl2k5_camera_final_eye_survey/v6',runtime_witnessed=False,
                native_capture_sha256=hashlib.sha256(Path(native_path).read_bytes()).hexdigest(),
                method='Native final smoothed eye and target; 96x72; det<0; >2% wall-rectangle ground occlusion',
                limitations='53 static model variants; opaque triangles, no GPU/alpha/near plane or game witness',
                totals=totals,models=rows)
    Path(output).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--xbe',type=Path);ap.add_argument('--capture',type=Path,required=True)
    ap.add_argument('--cache',type=Path);ap.add_argument('--survey',type=Path);ap.add_argument('--workers',type=int,default=4)
    args=ap.parse_args()
    if args.xbe:args.capture.write_text(json.dumps(capture(args.xbe.read_bytes()),indent=2)+'\n')
    if args.cache:survey(args.cache,args.capture,args.survey,args.workers)
