"""Build and run a u1_blender.py job for helmet card layers (helm_card and the unif card's helmet layer)."""
import sys, json, subprocess, os, time
from pathlib import Path
WORK = Path(__import__('os').environ.get('B81_ART_WORK', '/home/noah/2k-worktrees/.b77-scratch/b81/art/work'))
WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WT / 'tools' / 'b77'))
import u1_cards as U
OFF = [0.0, 0.0455, 0.339]     # the card job's head offset (applied there because the body is loaded too)
def view(name, side, out, size=1024):
    v = U.view(name, side, Path(out))
    v['target'] = [v['target'][i] - OFF[i] for i in range(3)]   # head only: no offset, so move the target instead
    v['size'] = [size, size]
    return v
def item(tex_png, side, outs, facemask=(128, 128, 128), size=1024):
    tex = {k: str(tex_png) for k in ("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C")}
    return {"tex": tex, "hide": list(U.HEAD_HIDE), "facemask_rgb": list(facemask), "facemask": "FACEMASK12", "shell": "C",
            "views": [view(n, side, p, size) for n, p in outs.items()]}
def run(items, tag, mode='modern', threads=8):
    job = {"head": str(WORK / f'head_{mode}' / 'hi_head_o3c115.gltf'), "body": None, "items": items}
    jp = WORK / 'bl' / f'job_{tag}.json'
    jp.write_text(json.dumps(job))
    cmd = ["flock", "/tmp/b77-blender.lock", "nice", "-n", "19", "ionice", "-c2", "-n7", "taskset", "-c", "16-31",
           "xvfb-run", "-a", "-s", "-screen 0 1280x1024x24", "blender", "-b", "--factory-startup", "-t", str(threads),
           "--python-exit-code", "1", "-P", str(WT / 'tools/b765/u1_blender.py'), "--", str(jp)]
    env = dict(os.environ); env.pop('DISPLAY', None); env['LP_NUM_THREADS'] = str(threads); env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    t = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (WORK / 'bl' / f'log_{tag}.txt').write_text(r.stdout[-20000:] + '\n---\n' + r.stderr[-5000:])
    if r.returncode:
        raise SystemExit(f"blender failed ({tag}): {r.stdout[-1500:]}{r.stderr[-800:]}")
    return time.time() - t
if __name__ == '__main__':
    import cardlib as C
    out = WORK / 'bl' / 'test'; out.mkdir(exist_ok=True)
    its = [item(C.hindex()['helmet02_00H0'], 'H', {'helm_card': out / 'ari_H_helm.png', 'helmet': out / 'ari_H_unifhelm.png'}, (120, 125, 130))]
    print('seconds', run(its, 'test'))
