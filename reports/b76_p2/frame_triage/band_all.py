import json, glob, os
from concurrent.futures import ProcessPoolExecutor
import cv2, numpy as np
B = "/home/noah/2k-worktrees/.b76-session/scratchpad/b76"
T = cv2.cvtColor(cv2.imread("tpl_mnf_band.png"), cv2.COLOR_BGR2GRAY).astype(np.float32)
def score(key):
    src, name = key.split("/")
    g = cv2.cvtColor(cv2.imread(f"{B}/{src}/frames/{name}"), cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (960, 540), interpolation=cv2.INTER_AREA).astype(np.float32)
    best = (0.0, None)
    for s in (0.12, 0.16, 0.2, 0.26, 0.33, 0.42, 0.5, 0.6, 0.75, 0.9, 1.1):
        t = cv2.resize(T, (max(10, int(T.shape[1] * s)), max(6, int(T.shape[0] * s))), interpolation=cv2.INTER_AREA)
        if t.shape[0] >= g.shape[0] or t.shape[1] >= g.shape[1]:
            continue
        r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
        r = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx > best[0]:
            best = (round(float(mx), 3), (loc[0] * 2, loc[1] * 2, s * 2))
    return key, best
if __name__ == "__main__":
    keys = [f"{s}/{os.path.basename(f)}" for s in ("mnf", "obs") for f in sorted(glob.glob(f"{B}/{s}/frames/*.png"))]
    out = {}
    with ProcessPoolExecutor(max_workers=20) as pool:
        for k, (s, at) in pool.map(score, keys, chunksize=16):
            out[k] = dict(band=s, band_at=at)
    json.dump(out, open("band.json", "w"))
    v = np.array([x["band"] for x in out.values()])
    for th in (0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8):
        print(th, int((v >= th).sum()))
