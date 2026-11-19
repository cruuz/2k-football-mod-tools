#!/usr/bin/env python3
"""bump_report2.py CONFIG.json : the second-round relief images for Noah (uniforms/bump/), one image per level.
Each image: the coin toss (the same camera in every run) with both prototype kits and enlarged chests; that run's
closest looks at each jersey beside a real 2026 broadcast close-up at about the same framing; a gameplay-distance frame.
CONFIG = {"out_dir": ..., "real": {"dark": [file, x0, y0, x1, y1], "white": [...]},
          "levels": [{"key": "A", "run": "uA2", "title": ..., "text": [...], "toss": g, "giants": [g, x0, y0, x1, y1],
                      "falcons": [g, x0, y0, x1, y1], "play": [g, x0, y0, x1, y1], "out": "RELIEF_A_quiet.png"}, ...]}
Game frames are the private emulator display (1280x720, game picture at 200,56 to 1080,716), render scale 2."""
import sys, json, glob
from PIL import Image, ImageDraw, ImageFont
E = '/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/emu/emu/'
BG, FG, DIM, HI = (24, 24, 28), (235, 235, 235), (170, 170, 175), (255, 208, 80)


def font(size, bold=False):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf' % ('-Bold' if bold else ''),):
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()


def frame(run, g):
    return Image.open(glob.glob(f'{E}{run}/shots/*_{run}_g{g:03d}.png')[0]).convert('RGB')


def fit(im, w=None, h=None, resample=Image.LANCZOS):
    s = (w / im.width) if w else (h / im.height)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), resample)


def tile(im, label):
    out = Image.new('RGB', (im.width, im.height + 26), BG); out.paste(im, (0, 26))
    ImageDraw.Draw(out).text((2, 4), label, fill=HI, font=font(15, True)); return out


def row(tiles, gap=10):
    h = max(t.height for t in tiles); w = sum(t.width for t in tiles) + gap * (len(tiles) - 1)
    out = Image.new('RGB', (w, h), BG); x = 0
    for t in tiles: out.paste(t, (x, 0)); x += t.width + gap
    return out


def level_image(cfg, lv):
    real = cfg['real']
    toss = frame(lv['run'], lv['toss'])
    tg, tf = lv.get('toss_giants', [205, 140, 415, 350]), lv.get('toss_falcons', [880, 140, 1080, 350])
    r1 = row([tile(toss.crop((200, 56, 1080, 716)), 'GAME: coin toss, the same camera in every image (emulator frame, unscaled)'),
              tile(fit(toss.crop(tuple(tg)), h=520), 'Giants home, enlarged'),
              tile(fit(toss.crop(tuple(tf)), h=520), 'Falcons road, enlarged')])
    g = lv['giants']; f = lv['falcons']
    H = 470
    rd = Image.open(real['dark'][0]).convert('RGB').crop(tuple(real['dark'][1:]))
    rw = Image.open(real['white'][0]).convert('RGB').crop(tuple(real['white'][1:]))
    r2 = row([tile(fit(frame(lv['run'], g[0]).crop(tuple(g[1:])), h=H), 'GAME: closest dark jersey'),
              tile(fit(rd, h=H), 'REAL 2026 close-up (reference)'),
              tile(fit(frame(lv['run'], f[0]).crop(tuple(f[1:])), h=H), 'GAME: closest white jersey'),
              tile(fit(rw, h=H), 'REAL 2026 close-up (reference)')])
    p = lv['play']
    r3 = row([tile(frame(lv['run'], p[0]).crop(tuple(p[1:])), 'GAME: gameplay distance (unscaled)')])
    W = max(r1.width, r2.width, r3.width) + 32
    head = 44 + 22 * len(lv['text'])
    out = Image.new('RGB', (W, head + r1.height + r2.height + r3.height + 60), BG)
    d = ImageDraw.Draw(out); d.text((16, 10), lv['title'], fill=FG, font=font(24, True))
    for i, t in enumerate(lv['text']): d.text((16, 44 + 22 * i), t, fill=DIM, font=font(15))
    y = head + 10
    for r in (r1, r2, r3):
        out.paste(r, (16, y)); y += r.height + 14
    out.save(cfg['out_dir'] + '/' + lv['out']); print(lv['out'], out.size)


if __name__ == '__main__':
    cfg = json.load(open(sys.argv[1]))
    only = sys.argv[2:]
    for lv in cfg['levels']:
        if not only or lv['key'] in only: level_image(cfg, lv)
