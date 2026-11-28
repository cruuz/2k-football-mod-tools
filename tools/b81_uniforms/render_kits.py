#!/usr/bin/env python3
"""b81-uniforms: render decoded kit folders on the Studio's hi body + modern head (tools/b765/u1_blender.py, EEVEE on a
private Xvfb, CPU). usage: render_kits.py ART_ROOT OUT [--only SEL,SEL] [--views audit|close] [--number 17]
ART_ROOT/<SEL>/torso.png ...; facemask from ART_ROOT/../export.json when present."""
import sys, json, subprocess, os, time, argparse, hashlib
from pathlib import Path
WT = Path('/home/noah/2k-worktrees/b81-uniforms')
sys.path.insert(0, str(WT / 'tools' / 'b77'))
import u1_render_kit as K
SCRIPT = WT / 'tools/b765/u1_blender.py'
MODELS = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/models')
AUDIT = [("front", 0, 4, 5.4, [0, 0, -0.15], [360, 560]), ("back", 180, 4, 5.4, [0, 0, -0.15], [360, 560]),
         ("left", 90, 4, 5.4, [0, 0, -0.15], [360, 560]),
         ("tq", 50, 10, 2.9, [0, 0, 0.42], [520, 480]), ("tb", 180, 8, 2.9, [0, 0, 0.42], [520, 480])]
CLOSE = [("c_front", 0, 6, 2.6, [0, 0, 0.42], [640, 600]), ("c_back", 180, 6, 2.6, [0, 0, 0.42], [640, 600]),
         ("c_ql", 55, 10, 2.6, [0, 0, 0.42], [640, 600]), ("c_side", 90, 6, 2.6, [0, 0, 0.42], [640, 600]),
         ("c_pants", 90, 0, 3.0, [0, 0, -0.45], [480, 640]), ("c_top", 0, 38, 2.6, [0, 0, 0.42], [640, 600])]
def item(label, art, facemask, number, out, views, bump=None, strength=1.0):
    it = K.item_for(label, art, facemask, number, out, "none")
    if bump:
        it["bump"] = bump; it["bump_strength"] = strength
    vs = []
    for tag, yaw, pitch, dist, target, size in views:
        vs.append({"yaw": yaw, "pitch": pitch, "dist": dist, "fov": 23, "target": target, "size": size, "parts": "all",
                   "samples": 16, "out": str(Path(out) / f"{label}_{tag}.png")})
    it["views"] = vs
    return it
def run(items, out, tag, threads=8):
    job = {"head": str(MODELS / 'hi_head_o3c115.gltf'), "body": str(MODELS / 'hi_body_o3c114.gltf'), "arms_down": 60, "items": items}
    jp = Path(out) / f'job_{tag}.json'; jp.write_text(json.dumps(job))
    cmd = ["flock", "/tmp/b77-blender.lock", "nice", "-n", "19", "ionice", "-c2", "-n7", "taskset", "-c", "16-31",
           "xvfb-run", "-a", "-s", "-screen 0 1280x1024x24", "blender", "-b", "--factory-startup", "-t", str(threads),
           "--python-exit-code", "1", "-P", str(SCRIPT), "--", str(jp)]
    env = dict(os.environ); env.pop('DISPLAY', None); env['LP_NUM_THREADS'] = str(threads); env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    t = time.time()
    with open(Path(out) / f'log_{tag}.txt', 'w') as log:
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
    if r.returncode:
        raise SystemExit(f"blender failed ({tag}), see {out}/log_{tag}.txt")
    return time.time() - t
def main():
    p = argparse.ArgumentParser()
    p.add_argument('art', type=Path); p.add_argument('out', type=Path)
    p.add_argument('--only', default=''); p.add_argument('--views', default='audit'); p.add_argument('--number', type=int, default=17)
    p.add_argument('--tag', default='a'); p.add_argument('--chunk', type=int, default=30)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    fm = {}
    ex = a.art.parent / 'export.json'
    if ex.exists():
        for s in json.load(open(ex))['sets']: fm[s['selector']] = s.get('facemask', '#808080')
    sels = [s for s in a.only.split(',') if s] or sorted(d.name for d in a.art.iterdir() if d.is_dir())
    views = AUDIT if a.views == 'audit' else CLOSE
    items = [item(s, a.art / s, fm.get(s, '#808080'), a.number, a.out, views) for s in sels]
    t = 0
    for i in range(0, len(items), a.chunk):
        t += run(items[i:i + a.chunk], a.out, f'{a.tag}{i // a.chunk}')
        print('chunk', i // a.chunk, 'done', round(t), 's', flush=True)
if __name__ == '__main__':
    main()
