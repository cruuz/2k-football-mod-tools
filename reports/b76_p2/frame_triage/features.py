"""p2 triage features over the 2026 frame sets (read only; writes features.jsonl here).

Per frame: scorebug NCC and centre red fraction (p1 scan2), the MNF stinger red-mask NCC over scales,
the top-right ESPN MNF watermark NCC, colour fractions, flat-block fraction, luma, and the p1 OCR words
for the frames without a scorebug. Code computes; Jev (jev_triage.py) judges the text state.
"""
import json, os, sys, glob
from concurrent.futures import ProcessPoolExecutor
import cv2, numpy as np
B = "/home/noah/2k-worktrees/.b76-session/scratchpad/b76"
HERE = os.path.dirname(os.path.abspath(__file__))
DENSE = "/home/noah/2k-worktrees/.b76-session/scratchpad/p2/dense/mnf87"
scan2 = json.load(open(f"{B}/work/scan2.json"))
ocr = {}
for line in open(f"{B}/work/p1/triage_ocr.jsonl"):
    r = json.loads(line); ocr[r["key"]] = r["words"]

def redmask(im):
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    m = (((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 140) & (hsv[..., 2] > 70)).astype(np.float32)
    return m

_t = cv2.imread(f"{DENSE}/f_0045.png")
TPL = cv2.GaussianBlur(redmask(_t)[260:790, 740:1180], (0, 0), 3)
_w = cv2.imread(f"{DENSE}/f_0029.png", cv2.IMREAD_GRAYSCALE)
WM = _w[8:48, 1640:1905].astype(np.float32)

def feats(key):
    src, name = key.split("/")
    im = cv2.imread(f"{B}/{src}/frames/{name}")
    small = cv2.resize(im, (480, 270), interpolation=cv2.INTER_AREA)
    rm = cv2.GaussianBlur(redmask(small), (0, 0), 0.75)
    best, where = 0.0, None
    for s in (0.12, 0.17, 0.25, 0.35, 0.5):
        t = cv2.resize(TPL, (max(8, int(TPL.shape[1] * s)), max(8, int(TPL.shape[0] * s))), interpolation=cv2.INTER_AREA)
        if t.shape[0] >= rm.shape[0] or t.shape[1] >= rm.shape[1] or t.std() == 0:
            continue
        r = cv2.matchTemplate(rm, t, cv2.TM_CCOEFF_NORMED)
        # a window with almost no red pixels is flat: its normalised score is meaningless (0/0 -> 1.0)
        ones = np.ones_like(t)
        mass = cv2.matchTemplate(rm, ones, cv2.TM_CCORR)
        r = np.where(np.isfinite(r) & (mass >= 0.3 * float(t.sum())), r, 0.0).astype(np.float32)
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx > best:
            best, where = float(mx), (int(loc[0] * 4), int(loc[1] * 4), round(s * 4, 2))
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    wm = cv2.matchTemplate(g[0:70, 1600:1920].astype(np.float32), WM, cv2.TM_CCOEFF_NORMED)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h, s_, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    frac = lambda m: round(float(m.mean()), 3)
    green = (h >= 35) & (h <= 85) & (s_ > 60) & (v > 50)
    red = ((h < 8) | (h > 170)) & (s_ > 140) & (v > 70)
    navy = (h >= 100) & (h <= 130) & (s_ > 90) & (v > 30) & (v < 140)
    black = v < 35
    white = (v > 215) & (s_ < 30)
    gs = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blocks = gs[:264, :480].reshape(33, 8, 60, 8).std(axis=(1, 3))
    flat = frac(blocks < 3.0)
    bar, redc = scan2.get(key, (None, None))
    return key, dict(src=src, frame=name, idx=int(name[6:12]),
                     t_s=round((int(name[6:12]) - 1) * (30 / 29.97 if src == "mnf" else 0.5), 2),
                     bar_ncc=bar, red_centre=redc, stinger_ncc=round(best, 3), stinger_at=where,
                     watermark_ncc=round(float(wm.max()), 3), green=frac(green), red=frac(red), navy=frac(navy),
                     black=frac(black), white=frac(white), flat=flat, luma=round(float(gs.mean()), 1),
                     ocr=ocr.get(key))

if __name__ == "__main__":
    keys = [f"{s}/{os.path.basename(f)}" for s in ("mnf", "obs") for f in sorted(glob.glob(f"{B}/{s}/frames/*.png"))]
    with ProcessPoolExecutor(max_workers=20) as pool, open(f"{HERE}/features.jsonl", "w") as out:
        for key, row in pool.map(feats, keys, chunksize=16):
            out.write(json.dumps(dict(key=key, **row)) + "\n")
    print("frames", len(keys))
