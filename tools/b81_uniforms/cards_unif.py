#!/usr/bin/env python3
"""b81-uniforms: Team Select UNIFORM cards (family unif, 256 px) for kits the pass changes.

The shipped card keeps every pixel the kit change does not touch (so the helmet layer, which the helmet job owns, and
the card's own look stay as they are). The jersey and pants layers are rendered twice with the k2 card cameras and light
(tools/b77/u1_cards.py): once from the kit as the released build holds it, once from the corrected kit; where the two
renders differ, the card takes the shipped pixel plus that difference.
  cards_unif.py OUT SEL=OLD_KITDIR:NEW_KITDIR ...     (kit dirs hold torso.png, sleeve.png, pants.png, digit_*.png)
Writes OUT/<name>.png (name = the league project's card name, e.g. unif_h02_0_256), OUT/card_receipt.json and layer files."""
import sys, json, hashlib, subprocess, os
from pathlib import Path
import numpy as np
from PIL import Image
WT = Path('/home/noah/2k-worktrees/b81-uniforms')
sys.path[:0] = [str(WT / 'tools' / 'b77'), str(WT / 'tools'), str(WT), str(Path(__file__).parent)]
import u1_cards as U
import render_kits as R
PROJ = Path('/media/noah/Storage/2K5-project/b81-art/src128/SOFTDRINK-league-project.json')
M = U.M
TAU = 5.0 / 255.0
def project_cards():
    out = {}
    for e in json.load(open(PROJ))['edits']:
        if e.get('kind') == 'team_select' and e.get('family') == 'unif' and e.get('resolution') == 256:
            out[(e['asset_code'], 'H' if e['side'] == 'home' else 'A', int(e['style']))] = e['png']
    return out
def item(kit, layers, number='30'):
    kit = Path(kit); work = Path(layers['jersey']).parent
    tex = {"UNIF_jersey": U.torso_card(kit / "torso.png", work / (Path(layers['jersey']).stem + "_torso.png")),
           "UNIF_sleeve": str(kit / "sleeve.png"), "UNIF_pants": str(kit / "pants.png")}
    for pos, digit in (("L", number[0]), ("R", number[1])):
        tex[f"NUMBER_{pos}"] = str(kit / f"digit_jersey_{digit}.png")
        for sh in ("shoulder_A", "shoulder_B"):
            tex[f"NUMBER_{sh}_{pos}"] = str(kit / f"digit_arm_{digit}.png")
    hide = ["NUMBER_M", "NUMBER_shoulder_A_M", "NUMBER_shoulder_B_M"] + U.BODY_HIDE + U.HEAD_HIDE + ["HI_HELMET*", "HELMET_*", "LOGO_*", "FACEMASK*"]
    views = []
    for n in ("jersey", "pants"):
        v = U.view(n, 'H', Path(layers[n])); views.append(v)
    return {"tex": tex, "hide": hide, "uv_scale": U.UV_SCALE, "facemask_rgb": [128, 128, 128], "facemask": "FACEMASK12", "shell": "C", "views": views}
def layer256(paths):
    card = Image.new("RGBA", (256 * M, 256 * M), (0, 0, 0, 0))
    for p in paths: card = Image.alpha_composite(card, U.saturate(Image.open(p)))
    a = np.asarray(U.box_reduce(card, 256)).astype(np.float64) / 255.0
    a[..., :3] *= a[..., 3:4]
    return a                                   # premultiplied
def main():
    out = Path(sys.argv[1]); work = out / 'work'; work.mkdir(parents=True, exist_ok=True)
    cards = project_cards(); items, plans = [], []
    for spec in sys.argv[2:]:
        sel, dirs = spec.split('='); old, new = dirs.split(':')
        L = {}
        for tag, kit in (('old', old), ('new', new)):
            L[tag] = {n: str(work / f'{sel}_{tag}_{n}.png') for n in ('jersey', 'pants')}
            items.append(item(kit, L[tag]))
        plans.append((sel, L))
    job = {"head": str(R.MODELS / "hi_head_o3c115.gltf"), "body": str(R.MODELS / "hi_body_o3c114.gltf"),
           "arms_down": U.LAYOUT["arms_down"], "morphs": U.LAYOUT["morphs"], "items": items}
    jp = work / 'job_cards.json'; jp.write_text(json.dumps(job))
    cmd = ["flock", "/tmp/b77-blender.lock", "nice", "-n", "19", "ionice", "-c2", "-n7", "taskset", "-c", "16-31", "xvfb-run", "-a", "-s",
           "-screen 0 1280x1024x24", "blender", "-b", "--factory-startup", "-t", "8", "--python-exit-code", "1", "-P", str(U.BLENDER_SCRIPT), "--", str(jp)]
    env = dict(os.environ); env.pop('DISPLAY', None); env['LP_NUM_THREADS'] = '8'; env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    with open(work / 'log_cards.txt', 'w') as log:
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env)
    if r.returncode: raise SystemExit(f'blender failed, see {work}/log_cards.txt')
    receipt = {}
    for sel, L in plans:
        key = (sel[:2], sel[2], int(sel[3:])); src = cards.get(key)
        if src is None: receipt[sel] = dict(error='no unif card in the league project'); continue
        old = np.asarray(Image.open(src).convert('RGBA')).astype(np.float64) / 255.0
        P = old.copy(); P[..., :3] *= P[..., 3:4]
        Ro = layer256([L['old']['pants'], L['old']['jersey']]); Rn = layer256([L['new']['pants'], L['new']['jersey']])
        D = Rn - Ro
        change = (np.abs(D).max(axis=2) > TAU)
        # the helmet layer covers part of the card: there the shipped pixel is far from the kit render and stays
        shown = np.abs(P[..., :3] - Ro[..., :3]).max(axis=2) < 60.0 / 255.0
        z = change & shown
        N = P.copy(); N[z] = np.clip(P[z] + D[z], 0, 1)
        al = np.clip(N[..., 3:4], 0, 1)
        rgb = np.where(al > 1e-6, N[..., :3] / np.maximum(al, 1e-6), 0.0)
        card = (np.concatenate([np.clip(rgb, 0, 1), al], axis=2) * 255 + 0.5).astype(np.uint8)
        name = f"unif_{'h' if sel[2] == 'H' else 'a'}{sel[:2]}_{int(sel[3:])}_256"
        Image.fromarray(card, 'RGBA').save(out / f'{name}.png')
        receipt[sel] = dict(name=name, source_png=src, source_rgba_sha256=hashlib.sha256((old * 255 + 0.5).astype(np.uint8).tobytes()).hexdigest(),
                            new_rgba_sha256=hashlib.sha256(card.tobytes()).hexdigest(), changed_pixels=int(z.sum()),
                            render_changed_pixels=int(change.sum()), hidden_by_helmet=int((change & ~shown).sum()))
        print(sel, receipt[sel]['changed_pixels'], 'card pixels changed', flush=True)
    (out / 'card_receipt.json').write_text(json.dumps(receipt, indent=1, sort_keys=True) + '\n')
if __name__ == '__main__':
    main()
