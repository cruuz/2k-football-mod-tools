#!/usr/bin/env python3
"""contact.py RUN FIRST STEP COUNT OUT.jpg : labelled contact sheet of emulator frames g<FIRST>, g<FIRST+STEP>, ... (game area only)."""
import sys, glob
from PIL import Image, ImageDraw
run, first, step, count, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
E = '/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/emu/emu/'
cols = 5; rows = (count + cols - 1) // cols
sheet = Image.new('RGB', (cols * 320, rows * 240)); d = ImageDraw.Draw(sheet)
for i in range(count):
    n = first + i * step
    fs = glob.glob(f'{E}{run}/shots/*_{run}_g{n:03d}.png')
    if not fs: continue
    im = Image.open(fs[0]).convert('RGB').crop((200, 56, 1080, 716)).resize((320, 240), Image.LANCZOS)
    x, y = (i % cols) * 320, (i // cols) * 240
    sheet.paste(im, (x, y)); d.rectangle((x, y, x + 46, y + 13), fill=(0, 0, 0)); d.text((x + 3, y + 1), f'g{n:03d}', fill=(255, 255, 0))
sheet.save(out, quality=85)
