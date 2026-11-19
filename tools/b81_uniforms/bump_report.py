#!/usr/bin/env python3
"""Compose the Track B prototype images for Noah (uniforms/bump/): emulator close-ups before and after at three strengths,
offline previews, and the relief maps themselves."""
import glob
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
U = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms'); E = U / 'emu/emu'; B = U / 'bump'
def font(n):
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', n)
def frame(run, g, box, scale=1.6):
    f = glob.glob(f'{E}/{run}/shots/*_{run}_g{g:03d}.png')[0]
    x, y, w, h = box
    return Image.open(f).convert('RGB').crop((x, y, x + w, y + h)).resize((round(w * scale), round(h * scale)), Image.LANCZOS)
def sheet(title, notes, tiles, out, height=544):
    ims = []
    for label, im in tiles:
        im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
        c = Image.new('RGB', (im.width, height + 40), (24, 24, 28)); c.paste(im, (0, 40))
        ImageDraw.Draw(c).text((6, 8), label, fill=(255, 214, 90), font=font(20)); ims.append(c)
    W = sum(i.width for i in ims) + 8 * (len(ims) - 1) + 32
    H = 70 + 28 * len(notes) + ims[0].height + 20
    s = Image.new('RGB', (W, H), (24, 24, 28)); d = ImageDraw.Draw(s)
    d.text((16, 12), title, fill=(255, 255, 255), font=font(32)); y = 62
    for n in notes:
        d.text((16, y), n, fill=(210, 214, 222), font=font(18)); y += 28
    x = 16
    for i in ims: s.paste(i, (x, y + 6)); x += i.width + 8
    s.save(B / out); print(out, s.size)
N1 = ["Emulator close-ups (xemu, the game's own shading, 2x render scale). The 2004 jersey relief is an open mesh: it shows as dots on chest and back.",
      "The new relief is this season's Nike body: smooth fabric, a chevron seam across the upper chest, long seams front and back, a stitched name plate.",
      "0.10 is the game's stock jersey strength (no change to the game program). 0.20 and 0.35 need one number changed in the program (sleeves share it)."]
sheet("Jersey fabric relief, white jersey (Falcons road)", N1,
      [("BEFORE (released v0.9, strength 0.10)", frame('before', 34, (480, 240, 300, 340))),
       ("NEW relief, strength 0.10 (stock)", frame('after010w', 26, (440, 120, 300, 340))),
       ("NEW relief, strength 0.20", frame('after020', 30, (430, 200, 300, 340))),
       ("NEW relief, strength 0.35", frame('after035', 24, (430, 200, 440, 340)))], 'EMULATOR_white_jersey_Falcons_road.png')
sheet("Jersey fabric relief, dark jersey (Giants home)", N1,
      [("BEFORE (released v0.9, strength 0.10)", frame('before', 28, (470, 215, 300, 340))),
       ("NEW relief, strength 0.10 (stock)", frame('after010', 26, (410, 190, 300, 340))),
       ("NEW relief, strength 0.20", frame('after020', 24, (400, 200, 300, 340))),
       ("NEW relief, strength 0.35", frame('after035', 38, (200, 150, 300, 340)))], 'EMULATOR_dark_jersey_Giants_home.png')
def flat(p):
    im = Image.open(p).convert('RGBA'); bg = Image.new('RGBA', im.size, (58, 62, 74, 255)); bg.alpha_composite(im); return bg.convert('RGB')
P = B / 'work/prev2'
N2 = ["Offline preview on the game's player model (not the game's lighting; the preview strength is not the game's number). It shows the design only.",
      "Top row: the 2004 relief. Bottom row: the new relief. Left to right: light, medium, full preview strength."]
for sel, name in (('01A0', 'white_jersey_Falcons_road'), ('18H0', 'dark_jersey_Giants_home')):
    tiles = []
    for kind, lab in (('old', '2004 relief'), ('new', 'new relief')):
        row = [flat(P / f'{sel}_{kind}_{st}_bq.png') for st in ('0.2', '0.45', '1.0')]
        W = sum(r.width for r in row); im = Image.new('RGB', (W, row[0].height)); x = 0
        for r in row: im.paste(r, (x, 0)); x += r.width
        tiles.append((lab, im))
    a, b = tiles[0][1], tiles[1][1]
    both = Image.new('RGB', (a.width, a.height * 2 + 6), (24, 24, 28)); both.paste(a, (0, 0)); both.paste(b, (0, a.height + 6))
    sheet(f"Jersey fabric relief, offline preview ({name.replace('_', ' ')})", N2, [("2004 relief (top) / new relief (bottom)", both)], f'RENDER_{name}.png', height=900)
old = Image.open(U / 'work/v09/uniforms/01A0/bump_jersey.png').convert('RGB'); new = Image.open(B / 'work/01A0_modern_v2.png').convert('RGB')
so = Image.open(U / 'work/v09/uniforms/01A0/bump_sleeve.png').convert('RGB').resize((256, 256), Image.LANCZOS); sn = Image.open(B / 'work/sleeve_modern_v1.png').convert('RGB').resize((256, 256), Image.LANCZOS)
def pair(j, s):
    im = Image.new('RGB', (512 + 8 + 256, 256), (24, 24, 28)); im.paste(j, (0, 0)); im.paste(s, (520, 0)); return im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
both = Image.new('RGB', (1552, 1030), (24, 24, 28)); both.paste(pair(old, so), (0, 0)); both.paste(pair(new, sn), (0, 518))
sheet("The relief maps themselves (jersey 512x256, sleeve 128x128; same slots, same size)", ["Top: the 2004 map of the Falcons road kit (open mesh panel, ribbed collar, embossed wordmark, loose folds, sleeve shield).",
      "Bottom: the prototype (smooth body, chevron and long seams, flat stitched collar, name plate, the old map's large folds kept, plain sleeve with a cuff seam)."],
      [("2004 (top) / prototype (bottom)", both)], 'MAPS_old_and_new.png', height=1030)
