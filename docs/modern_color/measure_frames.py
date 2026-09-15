"""Measure broadcast colour clusters over many frames: turf green, Chiefs red, white lines, skin, crowd/sky."""
import sys, numpy as np, colorsys
from PIL import Image
F=sys.argv[1]; start,stop,step=int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]); pat=sys.argv[5] if len(sys.argv)>5 else "frame_%06d.jpg"
def hsv(a):
    r,g,b=a[...,0]/255.,a[...,1]/255.,a[...,2]/255.
    mx=np.max(a,axis=-1)/255.; mn=np.min(a,axis=-1)/255.; d=mx-mn
    h=np.zeros_like(mx); s=np.where(mx>0,d/np.maximum(mx,1e-6),0); v=mx
    m=d>1e-6
    rc=np.where(m,(mx-r)/np.maximum(d,1e-6),0); gc=np.where(m,(mx-g)/np.maximum(d,1e-6),0); bc=np.where(m,(mx-b)/np.maximum(d,1e-6),0)
    h=np.where(mx==r,bc-gc,np.where(mx==g,2+rc-bc,4+gc-rc)); h=(h/6.)%1.0
    return h*360,s,v
acc={k:[] for k in ("turf","red","white","navy","skin","crowd")}
n=0
for i in range(start,stop+1,step):
    try: im=Image.open(f"{F}/{pat%i}").convert("RGB")
    except Exception: continue
    a=np.asarray(im)[:900:3,::3].astype(np.float32)   # skip bottom band (bug), subsample
    h,s,v=hsv(a)
    turf=(h>70)&(h<150)&(s>0.35)&(v>0.25)&(v<0.95)
    red=((h>345)|(h<12))&(s>0.55)&(v>0.35)
    white=(s<0.12)&(v>0.85)
    navy=(h>200)&(h<250)&(s>0.45)&(v>0.12)&(v<0.6)
    skin=(h>8)&(h<35)&(s>0.25)&(s<0.65)&(v>0.35)&(v<0.9)
    for k,m in (("turf",turf),("red",red),("white",white),("navy",navy),("skin",skin)):
        if m.sum()>200: acc[k].append((m.sum()/m.size, np.median(a[m],axis=0), a[m].mean(axis=0)))
    n+=1
print("frames",n)
for k,rows in acc.items():
    if not rows: print(k,"none"); continue
    frac=np.array([r[0] for r in rows]); med=np.array([r[1] for r in rows]); mean=np.array([r[2] for r in rows])
    # weight by pixel fraction; report median of medians for frames where the class covers >= 8% (turf) or >=1% (others)
    thr=0.08 if k=="turf" else 0.01
    sel=frac>=thr
    if sel.sum()==0: sel=frac>=frac.max()*0.5
    M=np.median(med[sel],axis=0); P10=np.percentile(med[sel],10,axis=0); P90=np.percentile(med[sel],90,axis=0)
    r,g,b=M/255.; hh,ss,vv=colorsys.rgb_to_hsv(r,g,b)
    print(f"{k:6s} frames={sel.sum():4d} medianRGB=({M[0]:.0f},{M[1]:.0f},{M[2]:.0f}) p10=({P10[0]:.0f},{P10[1]:.0f},{P10[2]:.0f}) p90=({P90[0]:.0f},{P90[1]:.0f},{P90[2]:.0f}) HSV=({hh*360:.0f},{ss:.2f},{vv:.2f})")
