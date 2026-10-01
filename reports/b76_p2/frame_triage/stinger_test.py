import cv2, numpy as np, json, sys
B = "/home/noah/2k-worktrees/.b76-session/scratchpad/b76"
DENSE = "/home/noah/2k-worktrees/.b76-session/scratchpad/p2/dense/mnf87"
t = cv2.imread(f"{DENSE}/f_0045.png")[260:790, 740:1180]
def redmask(im):
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    return (((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 140) & (hsv[..., 2] > 70))
def score(key):
    src, name = key.split("/")
    im = cv2.imread(f"{B}/{src}/frames/{name}")
    small = cv2.resize(im, (640, 360), interpolation=cv2.INTER_AREA).astype(np.float32)
    rm = redmask(cv2.resize(im, (640, 360), interpolation=cv2.INTER_AREA)).astype(np.float32)
    best = (0.0, None)
    for s in np.linspace(0.18, 1.0, 12):
        tt = cv2.resize(t, (int(t.shape[1] * s / 3), int(t.shape[0] * s / 3)), interpolation=cv2.INTER_AREA).astype(np.float32)
        if tt.shape[0] >= 360 or tt.shape[1] >= 640 or min(tt.shape[:2]) < 12:
            continue
        r = cv2.matchTemplate(small, tt, cv2.TM_CCOEFF_NORMED)
        trm = redmask(tt.astype(np.uint8)).astype(np.float32)
        mass = cv2.matchTemplate(rm, np.ones_like(trm), cv2.TM_CCORR)
        r = np.where(np.isfinite(r) & (mass >= 0.5 * trm.sum()) & (mass <= 1.8 * trm.sum()), r, 0).astype(np.float32)
        _, mx, _, loc = cv2.minMaxLoc(r)
        if mx > best[0]:
            best = (round(float(mx), 3), (loc[0] * 3, loc[1] * 3, round(float(s), 2)))
    return best
if __name__ == "__main__":
    for k in sys.argv[1:]:
        print(k, score(k))
