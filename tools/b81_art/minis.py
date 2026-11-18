"""Schedule/menu mini helmets (64 px) re-rendered from the cleaned Standard-shell helmets with the repo's own mini
renderer (tools/nfl2k5_team_logos_2026.py minis: same camera, light, shell A, facemask 07), composed like the cards."""
import sys, json, subprocess, os, hashlib; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, compose, assign
from scipy import ndimage
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(C.WT / 'tools'))
import nfl2k5_team_logos_2026 as TL
R = C.WORK / 'bl' / 'mini'
P8 = json.load(open(C.WORK / 'p8_index.json'))
def mini_path(name):
    k = [k for k in P8 if k.endswith(':' + name)]
    return P8[k[0]][0] if len(k) == 1 else None
def final_mini(name): return C.load(C.WORK / 'final' / 'minis' / (name + '.png'))
def render():
    (R / 'old').mkdir(parents=True, exist_ok=True); (R / 'new').mkdir(parents=True, exist_ok=True)
    jobs = []
    for code in sorted(MINI_TEAMS):
        for side, S in (('h', 'H'), ('a', 'A')):
            sel = f'{code}{S}0'
            for kind, tex in (('old', C.hindex()[f'helmet00_{sel}']), ('new', str(C.WORK.parent / 'out' / 'helmets_compiled' / f'helmet00_{sel}.png'))):
                if not Path(tex).exists(): tex = str(assign.new_tex_path('helmet00', sel))
                jobs.append(dict(TL.MINI_LIGHT, texture00=tex, facemask_rgb=[12, 12, 12] if code == '02' else [128, 128, 128], shell=TL.MINI_SHELL, facemask=TL.MINI_FACEMASK,
                                 accessories=False, views=[TL.mini_view(side, R / kind / f'mini_{side}{code}.png')]))
    jp = R / 'job.json'
    jp.write_text(json.dumps({"gltf": str(C.WORK / 'head_retail' / 'hi_head_o3c115.gltf'), "size": 256, "items": jobs}))
    cmd = ["flock", "/tmp/b77-blender.lock", "nice", "-n", "19", "ionice", "-c2", "-n7", "taskset", "-c", "16-31", "xvfb-run", "-a", "-s", "-screen 0 1280x1024x24",
           "blender", "-b", "--factory-startup", "-t", "8", "--python-exit-code", "1", "-P", str(TL.BLENDER_SCRIPT), "--", str(jp)]
    env = dict(os.environ); env.pop('DISPLAY', None); env['LP_NUM_THREADS'] = '8'; env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    (R / 'log.txt').write_text(r.stdout[-8000:] + '\n---\n' + r.stderr[-3000:])
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-400:]
def layer(path):
    m = TL.saturate(Image.open(path))
    a = np.asarray(m, dtype=np.float64) / 255.0
    pm = a.copy(); pm[..., :3] *= pm[..., 3:4]
    return pm.reshape(64, 4, 64, 4, 4).mean(axis=(1, 3))
PASS_MINIS = {'29', '13'}
#: teams whose Standard-shell helmet lost old-logo pieces (beta 80's kit fix or this job): only their minis follow
MINI_TEAMS = {'00', '02', '09'}
def compose_mini(name):
    side, code = name[5], name[6:8]
    old = final_mini(name) if code in PASS_MINIS else C.load(mini_path(name))
    Ro = layer(R / 'old' / f'mini_{side}{code}.png'); Rn = layer(R / 'new' / f'mini_{side}{code}.png')
    P = compose.premul(old)
    D = Rn[..., :3] - Ro[..., :3]; E = P[..., :3] - Ro[..., :3]
    cov = Ro[..., 3] > 0.02
    z = (np.abs(D).max(axis=2) > 10.0 / 255.0) & cov
    z = ndimage.binary_dilation(z, iterations=1) & cov
    if code == '02':
        # Ravens: the mini was rendered from art with still more of the 2004 outline than the league project's
        # texture has, so the whole logo side of the shell takes the new render
        z = cov & (Ro[..., 3] > 0.98); z[40:] = False
        z &= ndimage.binary_dilation(np.abs(E).max(axis=2) > 20.0 / 255.0, iterations=3) | (np.abs(D).max(axis=2) > 10.0 / 255.0)
    hand = ndimage.binary_dilation(z & (np.abs(E).max(axis=2) > 24.0 / 255.0), iterations=1) & z
    keep = (~hand) & cov & (Ro[..., 3] > 0.98)
    w = ndimage.gaussian_filter(keep.astype(np.float64), 2.0)
    c = np.stack([ndimage.gaussian_filter(np.where(keep, E[..., k], 0.0), 2.0) for k in range(3)], axis=-1) / np.maximum(w, 1e-6)[..., None]
    c[w < 1e-3] = 0.0
    Ep = np.where(hand[..., None], c, E)
    newP = P[..., :3].copy(); newP[z] = (Rn[..., :3] + Ep)[z]
    out = old.copy(); rgb = compose.unpremul_u8(np.clip(newP, 0, 1), old[..., 3]); out[z, :3] = rgb[z]
    return old, out, dict(zone=int(z.sum()), hand=int(hand.sum()), changed=int((out != old).any(axis=2).sum()))
if __name__ == '__main__':
    if 'render' in sys.argv: render()
    OUTF = C.WORK.parent / 'out' / 'assets' / 'files'; OUTF.mkdir(parents=True, exist_ok=True)
    mrec = {}
    rows = []
    tiles = []
    for code in sorted(C.TEAMS):
        for side in 'ha':
            name = f'mini_{side}{code}_0'
            if code not in MINI_TEAMS: continue
            old, out, st = compose_mini(name)
            rows.append((name, st['changed'], st['hand']))
            if st['changed']:
                fn = f'b81art_{name}.png'
                Image.fromarray(out, 'RGBA').save(OUTF / fn, optimize=False, compress_level=9)
                mrec[name] = dict(st, file=fn, source_png=os.path.basename(mini_path(name)), source_rgba_sha256=compose.sha(C.load(mini_path(name))),
                                  new_rgba_sha256=compose.sha(out), new_file_sha256=hashlib.sha256((OUTF / fn).read_bytes()).hexdigest(),
                                  stored_rgba_sha256=compose.sha(C.quantize(out)))
            if st['changed'] > 0:
                tiles.append(C.hstack([C.up(C.over(final_mini(name)), 10), C.up(C.over(C.quantize(out)), 10)], gap=2))
    print(sorted([r for r in rows if r[1] > 0], key=lambda r: -r[1]))
    json.dump(mrec, open(C.WORK.parent / 'out' / 'mini_receipt.json', 'w'), indent=1, sort_keys=True)
    if tiles:
        rws = [C.hstack(tiles[i:i+2], gap=10) for i in range(0, len(tiles), 2)]
        W = max(r.shape[1] for r in rws)
        Image.fromarray(np.concatenate([np.pad(r, ((0, 8), (0, W - r.shape[1]), (0, 0))) for r in rws], axis=0)).save(C.WORK / 'view_minis_fix.png')
