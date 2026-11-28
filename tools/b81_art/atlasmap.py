"""Where the modern shell details sit on the helmet02 atlas: each detail vertex -> nearest shell surface point -> UV."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import geom, cardlib as C, numpy as np
from PIL import Image, ImageDraw
def closest_on_tri(p, a, b, c):
    # Ericson, Real-Time Collision Detection
    ab, ac, ap = b-a, c-a, p-a
    d1, d2 = ab@ap, ac@ap
    if d1 <= 0 and d2 <= 0: return a, (1,0,0)
    bp = p-b; d3, d4 = ab@bp, ac@bp
    if d3 >= 0 and d4 <= d3: return b, (0,1,0)
    vc = d1*d4 - d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1/(d1-d3); return a+v*ab, (1-v,v,0)
    cp = p-c; d5, d6 = ab@cp, ac@cp
    if d6 >= 0 and d5 <= d6: return c, (0,0,1)
    vb = d5*d2 - d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2/(d2-d6); return a+w*ac, (1-w,0,w)
    va = d3*d6 - d5*d4
    if va <= 0 and (d4-d3) >= 0 and (d5-d6) >= 0:
        w = (d4-d3)/((d4-d3)+(d5-d6)); return b+w*(c-b), (0,1-w,w)
    den = 1.0/(va+vb+vc); v = vb*den; w = vc*den
    return a+ab*v+ac*w, (1-v-w,v,w)
def main():
    g, parts = geom.load_gltf('modern'); gr, partsr = geom.load_gltf('retail')
    shell = parts['HI_HELMET_C']; det = parts['LOGO_helmet_C']
    retail_tris = {tuple(sorted(t)) for t in partsr['LOGO_helmet_C']['tris'].tolist()}
    P = shell['pos']; UV = shell['uv']; T = shell['tris']
    T = T[(T[:,0]!=T[:,1])&(T[:,1]!=T[:,2])&(T[:,0]!=T[:,2])]
    cent = P[T].mean(axis=1)
    used = sorted({int(i) for t in det['tris'] for i in t})
    vuv = {}; vdist = {}
    for vi in used:
        p = det['pos'][vi]
        order = np.argsort(((cent - p)**2).sum(axis=1))[:40]
        best = None
        for ti in order:
            a,b,c = P[T[ti]]
            q, w = closest_on_tri(p, a, b, c)
            d = np.linalg.norm(q-p)
            if best is None or d < best[0]:
                best = (d, ti, w)
        d, ti, w = best
        uv = sum(wi*UV[T[ti][k]] for k, wi in enumerate(w))
        vuv[vi] = uv; vdist[vi] = d
    print('detail verts', len(used), 'max dist to shell (cm)', max(vdist.values()), 'median', np.median(list(vdist.values())))
    # texel the detail parts sample
    duv = det['uv'][used]; print('detail UVs sampled (unique):', np.unique(np.round(duv*256,2),axis=0)[:10])
    S = 8; N = 256*S
    im = Image.new('L', (N, N), 0); dr = ImageDraw.Draw(im)
    n=0
    for t in det['tris'].tolist():
        if len(set(t)) < 3: continue
        pts = [vuv[i] for i in t]
        us = [p[0] for p in pts]; vs = [p[1] for p in pts]
        if max(us)-min(us) > 0.2 or max(vs)-min(vs) > 0.2: continue   # spans two islands
        # the retail decal quads: their own UVs are real texture coords (not one black texel)
        uvs_own = det['uv'][t]
        if np.ptp(uvs_own[:,0]) > 1e-4 or np.ptp(uvs_own[:,1]) > 1e-4: continue
        dr.polygon([(p[0]*N, p[1]*N) for p in pts], fill=255); n+=1
    print('detail tris drawn', n)
    m = np.asarray(im, dtype=np.float64).reshape(256,S,256,S).mean(axis=(1,3))/255.0
    np.save(C.WORK/'modern_detail_atlas.npy', m)
    tex = C.hcur('helmet02_00H0')[...,:3].astype(float)
    ov = tex.copy(); ov = ov*(1-0.6*m[...,None]) + np.array([255,0,0])*0.6*m[...,None]
    Image.fromarray(C.up(np.clip(ov,0,255).astype(np.uint8),4)).save(C.WORK/'view_atlas_details.png')
main()
