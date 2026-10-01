import json, glob, os
from concurrent.futures import ProcessPoolExecutor
from stinger_test import score, B
keys = [f"{s}/{os.path.basename(f)}" for s in ("mnf", "obs") for f in sorted(glob.glob(f"{B}/{s}/frames/*.png"))]
def one(k):
    return k, score(k)
if __name__ == "__main__":
    out = {}
    with ProcessPoolExecutor(max_workers=20) as pool:
        for k, (s, at) in pool.map(one, keys, chunksize=16):
            out[k] = dict(stinger_color=s, stinger_color_at=at)
    json.dump(out, open("stinger_color.json", "w"))
    print(len(out), sum(v["stinger_color"] >= 0.35 for v in out.values()))
