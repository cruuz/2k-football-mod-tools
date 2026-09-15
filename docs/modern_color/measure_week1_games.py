# Measurement script used for docs/modern_color/README.md (2026-09-15). Reads the Week 1 frames folder; paths are the machine they were measured on.
import numpy as np, json
from PIL import Image
D="/media/noah/Storage/NFL-Lighting-References/Week1-All-Teams-Highlights/frames"
GAMES=[("NE@SEA","Lumen Field, Seattle","open","late afternoon (8:20 ET = 5:20 PT, sun up)",1,33),
("SF@LAR","MCG, Melbourne","open","day (10:35 local)",34,60),("NYJ@TEN","Nissan Stadium, Nashville","open","day (1 ET)",61,96),
("ATL@PIT","Acrisure Stadium, Pittsburgh","open","day (1 ET)",97,136),("CLE@JAX","EverBank Stadium, Jacksonville","open","day (1 ET)",137,176),
("BAL@IND","Lucas Oil Stadium, Indianapolis","dome","dome (1 ET)",177,218),("BUF@HOU","NRG Stadium, Houston","dome","dome (1 ET)",219,253),
("NO@DET","Ford Field, Detroit","dome","dome (1 ET)",254,282),("TB@CIN","Paycor Stadium, Cincinnati","open","day (1 ET)",283,317),
("CHI@CAR","Bank of America Stadium, Charlotte","open","day (1 ET)",318,352),("WAS@PHI","Lincoln Financial Field, Philadelphia","open","late afternoon (4:25 ET)",353,386),
("GB@MIN","U.S. Bank Stadium, Minneapolis","dome","dome (4:25 ET)",387,433),("MIA@LV","Allegiant Stadium, Las Vegas","dome","dome (4:25 ET)",434,464),
("ARI@LAC","SoFi Stadium, Inglewood","dome (canopy)","dome-canopy (4:25 ET = 1:25 PT)",465,495),("DAL@NYG","MetLife Stadium, East Rutherford","open","night (8:20 ET)",496,517),
("DEN@KC","Arrowhead Stadium, Kansas City","open","night (8:15 ET)",518,554)]
def hsv(a):
    r,g,b=a[...,0]/255.,a[...,1]/255.,a[...,2]/255.
    mx=a.max(-1)/255.; mn=a.min(-1)/255.; d=mx-mn; s=np.where(mx>0,d/np.maximum(mx,1e-6),0)
    m=d>1e-6; rc=np.where(m,(mx-r)/np.maximum(d,1e-6),0); gc=np.where(m,(mx-g)/np.maximum(d,1e-6),0); bc=np.where(m,(mx-b)/np.maximum(d,1e-6),0)
    h=np.where(mx==r,bc-gc,np.where(mx==g,2+rc-bc,4+gc-rc)); h=(h/6.)%1.0*360
    return h,s,mx
def measure(frames_dir, f0, f1, pat="frame_%06d.jpg"):
    acc={"turf":[],"white":[],"skin":[],"top":[]}; clusters=[]; used=[]
    for fi in range(f0,f1+1):
        try: im=Image.open(f"{frames_dir}/{pat%fi}").convert("RGB")
        except Exception: continue
        used.append(fi)
        a=np.asarray(im)[:900:2,::2].astype(np.float32); h,s,v=hsv(a)
        turf=(h>60)&(h<160)&(s>0.3)&(v>0.2)&(v<0.95)
        if turf.sum()>4000: acc["turf"].append(np.median(a[turf],axis=0))
        white=(s<0.12)&(v>0.85)
        if white.sum()>300: acc["white"].append(np.median(a[white],axis=0))
        skin=(h>8)&(h<35)&(s>0.25)&(s<0.65)&(v>0.35)&(v<0.9)
        if skin.sum()>300: acc["skin"].append(np.median(a[skin],axis=0))
        acc["top"].append(np.median(a[:50].reshape(-1,3),axis=0))
        sat=(s>0.45)&(v>0.25)&~((h>60)&(h<160))
        if sat.sum()>500:
            hb=(h[sat]//30).astype(int); cnt=np.bincount(hb,minlength=12)
            for bi in np.argsort(cnt)[::-1][:2]:
                if cnt[bi]<300: continue
                m=sat.copy(); m[sat]=(hb==bi); clusters.append((int(bi*30),int(cnt[bi]),np.median(a[m],axis=0)))
    def med(k): return [int(x) for x in np.median(np.array(acc[k]),axis=0)] if acc[k] else None
    byhue={}
    for hb,n,c in clusters: byhue.setdefault(hb,[]).append((n,c))
    tops=sorted(((sum(n for n,_ in v), hb, np.median(np.array([c for _,c in v]),axis=0)) for hb,v in byhue.items()), reverse=True)[:3]
    return dict(turf=med("turf"),white=med("white"),skin=med("skin"),top=med("top"),clusters=[(hb,[int(x) for x in c]) for n,hb,c in tops],frames=[used[0],used[-1],len(used)] if used else None)
rows=[]
for g,stad,roof,bucket,f0,f1 in GAMES:
    m=measure(D,f0,f1); m.update(game=g,stadium=stad,roof=roof,bucket=bucket); rows.append(m)
    print(f"{g:8s} {bucket:38s} f{f0}-{f1} turf={m['turf']} white={m['white']} skin={m['skin']} top={m['top']} clusters={m['clusters']}")
m=measure("/media/noah/Storage/NFL-Lighting-References/SNF-Giants-Cowboys-MetLife/frames",1,55); m.update(game="DAL@NYG (Skattebo clip, 2 fps)",stadium="MetLife Stadium",roof="open",bucket="night (8:20 ET)"); rows.append(m)
print("SNF clip", m["turf"], m["white"], m["skin"], m["top"], m["clusters"])
# Arrowhead anchor: every 40th frame of the full MNF highlight
acc=measure.__globals__
import types
def measure_step(frames_dir,f0,f1,step):
    sub=range(f0,f1+1,step); D2=frames_dir
    class P: pass
    # reuse measure by temporarily mapping frames via a generator: simplest, copy the body with a step
    a_turf=[];a_white=[];a_skin=[];a_top=[];clusters=[]
    for fi in sub:
        try: im=Image.open(f"{D2}/frame_{fi:06d}.jpg").convert("RGB")
        except Exception: continue
        a=np.asarray(im)[:900:2,::2].astype(np.float32); h,s,v=hsv(a)
        turf=(h>60)&(h<160)&(s>0.3)&(v>0.2)&(v<0.95)
        if turf.sum()>4000: a_turf.append(np.median(a[turf],axis=0))
        white=(s<0.12)&(v>0.85)
        if white.sum()>300: a_white.append(np.median(a[white],axis=0))
        skin=(h>8)&(h<35)&(s>0.25)&(s<0.65)&(v>0.35)&(v<0.9)
        if skin.sum()>300: a_skin.append(np.median(a[skin],axis=0))
        a_top.append(np.median(a[:50].reshape(-1,3),axis=0))
    md=lambda L:[int(x) for x in np.median(np.array(L),axis=0)] if L else None
    return dict(turf=md(a_turf),white=md(a_white),skin=md(a_skin),top=md(a_top),frames=[f0,f1,len(range(f0,f1+1,step))],step=step)
m=measure_step("/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames",1,30044,40); m.update(game="DEN@KC (full MNF highlight, every 40th frame)",stadium="Arrowhead Stadium",roof="open",bucket="night (8:15 ET)",clusters=[]); rows.append(m)
print("Arrowhead full", m["turf"], m["white"], m["skin"], m["top"])
json.dump(rows,open("games.json","w"),indent=1)
# bucket aggregates
import collections
b=collections.defaultdict(list)
for r in rows:
    key="night" if r["bucket"].startswith("night") else "late afternoon" if r["bucket"].startswith("late") else "dome" if r["bucket"].startswith("dome") else "day"
    if r["turf"]: b[key].append(r["turf"])
for k,v in b.items(): print("BUCKET",k,len(v),"turf median",[int(x) for x in np.median(np.array(v),axis=0)],"min",[int(x) for x in np.min(np.array(v),axis=0)],"max",[int(x) for x in np.max(np.array(v),axis=0)])
