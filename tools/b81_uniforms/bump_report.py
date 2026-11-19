#!/usr/bin/env python3
"""Compose the Track B prototype images for Noah (uniforms/bump/): the game's own shading before and after (emulator),
the same at gameplay distance, the first draft's strength study, offline renders, and the relief maps as lit surfaces."""
import glob, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
U = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms'); E = U / 'emu/emu'; B = U / 'bump'
def font(n): return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', n)
def frame(run, g, box):
    f = glob.glob(f'{E}/{run}/shots/*_{run}_g{g:03d}.png')[0]; x, y, w, h = box
    return Image.open(f).convert('RGB').crop((x, y, x + w, y + h))
def sheet(title, notes, tiles, out, height=560):
    import textwrap
    ims = []
    for label, im in tiles:
        im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
        c = Image.new('RGB', (im.width, height + 40), (24, 24, 28)); c.paste(im, (0, 40))
        ImageDraw.Draw(c).text((6, 8), label, fill=(255, 214, 90), font=font(20)); ims.append(c)
    W = max(sum(i.width for i in ims) + 8 * (len(ims) - 1) + 32, 1500)
    notes = [l for n in notes for l in textwrap.wrap(n, (W - 32) // 11)]
    H = 70 + 28 * len(notes) + ims[0].height + 20
    s = Image.new('RGB', (W, H), (24, 24, 28)); d = ImageDraw.Draw(s)
    d.text((16, 12), title, fill=(255, 255, 255), font=font(32)); y = 62
    for n in notes: d.text((16, y), n, fill=(210, 214, 222), font=font(18)); y += 28
    x = 16
    for i in ims: s.paste(i, (x, y + 6)); x += i.width + 8
    s.save(B / out); print(out, s.size)
N = ["The game's own shading in the emulator (xemu, 2x render scale), at the STOCK jersey strength 0.10: nothing in the game program changes.",
     "Before: the 2004 map: an open mesh over chest and back, a ribbed collar, loose folds. New: the same sculpted folds, kept at full depth; this season's Nike body on top: smooth chest and back, the chevron seam, long seams, a stitched collar; the sculpted holes moved to perforated side panels."]
sheet("Jersey relief, white jersey (Falcons road): close-ups", N,
      [("BEFORE (released v0.9)", frame('before', 34, (480, 240, 300, 340))), ("NEW: front (chevron, long seams, side panel)", frame('nike010', 38, (530, 195, 250, 283))),
       ("NEW: back and side panel", frame('nike010', 38, (200, 60, 280, 317)))], 'EMULATOR_white_jersey_Falcons_road.png')
sheet("Jersey relief, dark jersey (Giants home): close-ups", N,
      [("BEFORE (released v0.9)", frame('before', 28, (470, 215, 300, 340))), ("NEW", frame('nike010', 24, (450, 190, 440, 290)))], 'EMULATOR_dark_jersey_Giants_home.png')
sheet("Jersey relief at the gameplay camera", ["At gameplay distance the relief is too small to read in either version: no shimmer or moire from the new side-panel holes (they are on the same 4-texel scale as the 2004 mesh, and the stored smaller copies of the map average them away).",
      "The difference is for replays, cut scenes between plays and the pregame."],
      [("BEFORE (released v0.9)", frame('before', 102, (360, 200, 560, 380))), ("NEW", frame('nike010', 90, (360, 200, 560, 380))), ("NEW: after-play close-up", frame('nike010', 96, (360, 120, 560, 380)))],
      'EMULATOR_gameplay_distance.png', height=520)
s1, s2 = B / 'work/atl_strip.png', B / 'work/nyg_strip.png'
if s1.exists():
    a, b = Image.open(s1).convert('RGB'), Image.open(s2).convert('RGB')
    both = Image.new('RGB', (max(a.width, b.width), a.height + b.height + 6), (24, 24, 28)); both.paste(a, (0, 0)); both.paste(b, (0, a.height + 6))
    sheet("Strength study (first draft, smooth body with seams only)", ["Left to right: the 2004 map at 0.10 | first draft at 0.10 (stock) | at 0.20 | at 0.35. The jersey strength is one number in the game program, shared with the sleeves; raising it needs a program patch and deepens every fold.",
          "Finding: the relief reads at the stock 0.10, so the crafted map is built to the 2004 map's own steepness and no program change is asked for."], [("white jersey (top), dark jersey (bottom)", both)], 'EMULATOR_strength_study_first_draft.png', height=1026)
L = np.array([-0.55, 0.55, 0.63]); L /= np.linalg.norm(L)
def lit(p, scale):
    a = np.asarray(Image.open(p).convert('RGB')).astype(float) / 127.5 - 1; n = a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-9)
    s = np.clip((n * L).sum(-1), 0, 1) ** 0.9
    o = Image.fromarray((40 + 215 * s / L[2] * 0.62).clip(0, 255).astype(np.uint8)).convert('RGB')
    return o.resize((round(o.width * scale), round(o.height * scale)), Image.LANCZOS)
V = U / 'work/v09/uniforms/01A0'; W_ = B / 'work'
def stack(a, b):
    o = Image.new('RGB', (a.width, a.height + b.height + 6), (24, 24, 28)); o.paste(a, (0, 0)); o.paste(b, (0, a.height + 6)); return o
sheet("The relief maps, shown as lit surfaces: jersey (512x256)", ["Top: the 2004 map (Falcons road package). Bottom: the crafted map. Same slot, same size, same encoding (tangent-space normals).",
      "Kept: every fold outside the old mesh, and the folds under it. Lifted out: the mesh trapezoid and rectangle, their piping, the ribbed collar, the shield tab and word block. Added: the chevron and long seams with their side breaks, the flat stitched collar with its small mesh grill and shield, perforated side panels."],
      [("2004 (top) / crafted (bottom)", stack(lit(V / 'bump_jersey.png', 3), lit(W_ / '01A0_nike_jersey.png', 3)))], 'MAPS_jersey_old_and_new.png', height=1100)
sl = stack(lit(V / 'bump_sleeve.png', 4), lit(W_ / '01A0_nike_sleeve.png', 4)); pt = stack(lit(V / 'bump_pants.png', 2).crop((0, 0, 1024, 200)), lit(W_ / '01A0_nike_pants.png', 2).crop((0, 0, 1024, 200)))
sheet("The relief maps: sleeve (128x128) and the top of the pants", ["Sleeve: the 2004 Falcons sleeve carries a large embossed 2004 falcon; the crafted sleeve keeps sculpted folds, adds the bound cuff, and embosses the painted 2026 logo and swoosh exactly where the colour texture has them.",
      "Pants: today's packs still emboss a shield where the swoosh is painted (left) and the Reebok vector where the shield is painted (right). Crafted: both lifted out; the swoosh and the shield embossed under the painted ones."],
      [("sleeve: 2004 (top) / crafted (bottom)", sl), ("pants hips: today (top) / crafted (bottom)", pt)], 'MAPS_sleeve_and_pants_old_and_new.png', height=1030)
