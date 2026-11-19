#!/usr/bin/env python3
"""b81-uniforms audit sheets: per kit a GAME sheet (renders + decoded textures) and per look a REFS sheet (kept 2026
highlight frames, reference only). usage: sheets.py RENDERS ART OUT"""
import sys, json, hashlib, collections
from pathlib import Path
from PIL import Image, ImageDraw
REFS = Path('/home/noah/Projects/2K5-8 Editors/refs/uniforms_2026')
TEAMS = {'00':'ARI','01':'ATL','02':'BAL','03':'BUF','04':'CAR','05':'CHI','06':'CIN','07':'DAL','08':'DEN','09':'DET','10':'GB','11':'IND','12':'JAX','13':'KC','14':'MIA','15':'MIN','16':'NE','17':'NO','18':'NYG','19':'NYJ','20':'LV','21':'PHI','22':'PIT','23':'LAR','24':'LAC','25':'SF','26':'SEA','27':'TB','28':'TEN','29':'WAS','30':'CLE','37':'HOU'}
REFTEAM = {'ARI': 'ARZ', 'WAS': 'WSH'}
# kit selector -> reference look (hand mapping from data/nfl2k5_uniform_slots_2026.json and the library's INDEX files)
LOOK = {'00H6': 'alternate-black', '00A6': 'alternate-black', '00H7': 'alternate-desert', '00A7': 'alternate-desert',
        '02A2': 'alternate-white-noise', '03H8': 'alternate-nickel-city', '03A8': 'alternate-nickel-city',
        '04H0': 'primary-black-alternate-helmet', '04H2': 'alternate-blue-black-helmet', '04A2': 'alternate-blue-black-helmet',
        '06H6': 'alternate-orange', '06A6': 'alternate-orange', '30H3': 'alternate-brown-helmet', '30A3': 'alternate-brown-helmet',
        '08H6': 'alternate-navy', '08A6': 'alternate-navy', '08A5': 'alternate-summit-white',
        '10H5': 'alternate-rivalries', '10A5': 'alternate-rivalries', '11H3': 'alternate-rivalries', '11A3': 'alternate-rivalries',
        '23H10': 'alternate-classic-sol', '23A10': 'alternate-classic-sol', '16H4': 'throwback-pat-patriot', '16A4': 'throwback-pat-patriot'}
def look_for(sel):
    if sel in LOOK: return LOOK[sel]
    if sel[3:] == '0': return 'primary-home' if sel[2] == 'H' else 'primary-away'
    return None
def flat(im, bg=(70, 74, 88)):
    im = im.convert('RGBA'); b = Image.new('RGBA', im.size, bg + (255,)); b.alpha_composite(im); return b.convert('RGB')
def game_sheet(sel, renders, art, out):
    names = ['front', 'back', 'left', 'tq', 'tb']
    ims = [flat(Image.open(renders / f'{sel}_{n}.png')) for n in names]
    W = sum(i.width for i in ims); H = 560
    row = Image.new('RGB', (W, H), (70, 74, 88)); x = 0
    for i in ims: row.paste(i, (x, 0)); x += i.width
    a = art / sel
    t = flat(Image.open(a / 'torso.png')); p = flat(Image.open(a / 'pants.png'))
    s = flat(Image.open(a / 'sleeve.png')).resize((256, 256), 0); k = flat(Image.open(a / 'socks00.png')).resize((128, 128), 0)
    dig = Image.new('RGB', (64 * 10, 64 * 2), (70, 74, 88))
    for d in range(10):
        dig.paste(flat(Image.open(a / f'digit_jersey_{d}.png'), (40, 110, 60)), (64 * d, 0))
        dig.paste(flat(Image.open(a / f'digit_arm_{d}.png'), (40, 110, 60)), (64 * d, 64))
    nm = flat(Image.open(a / 'names.png'), (40, 110, 60)).crop((0, 0, 640, 32)).resize((640, 32))
    tex = Image.new('RGB', (W, 262), (40, 42, 50))
    tex.paste(t, (0, 3)); tex.paste(p, (516, 3)); tex.paste(s, (1032, 3)); tex.paste(k, (1292, 3)); tex.paste(dig, (1424, 3)); tex.paste(nm, (1424, 140))
    sheet = Image.new('RGB', (W, H + 262 + 18), (20, 20, 24))
    sheet.paste(row, (0, 18)); sheet.paste(tex, (0, H + 18))
    ImageDraw.Draw(sheet).text((4, 3), f'{TEAMS[sel[:2]]} {sel} GAME (v0.9 disc textures rendered offline: front, back, left, 3/4, back close; below: torso, pants, sleeve x2, socks, digits, name letters)', fill='white')
    sheet = sheet.resize((1300, round(sheet.height * 1300 / W)), Image.LANCZOS)
    sheet.save(out / f'{TEAMS[sel[:2]]}_{sel}_game.png')
def refs_sheet(team, look, frames, out):
    want = ['jersey_front', 'jersey_back', 'sleeve_shoulder', 'pants', 'socks', 'helmet_left', 'helmet_front', 'helmet_back']
    pick = []
    for el in want:
        for f in frames:
            if f['element'] == el and f not in pick: pick.append(f); break
    for el in want:        # second of the key elements
        if len(pick) >= 6: break
        c = [f for f in frames if f['element'] == el and f not in pick]
        if c: pick.append(c[0])
    pick = pick[:6]
    sheet = Image.new('RGB', (512 * 3, 306 * 2), (20, 20, 24)); d = ImageDraw.Draw(sheet)
    for i, f in enumerate(pick):
        im = Image.open(REFS / f['path']).convert('RGB').resize((512, 288), Image.LANCZOS)
        x, y = (i % 3) * 512, (i // 3) * 306
        sheet.paste(im, (x, y + 18)); d.text((x + 4, y + 3), f"{f['path'].split('/')[-1]} : {f['description'][:60]}", fill='white')
    sheet.save(out / f'{team}_{look}_refs.jpg', quality=88)
    return [f['path'] for f in pick]
def main():
    renders, art, out = map(Path, sys.argv[1:4]); out.mkdir(parents=True, exist_ok=True)
    m = json.load(open(REFS / 'manifest.json'))
    by = collections.defaultdict(list)
    for f in m['frames']: by[(f['team'], f['look'])].append(f)
    index = {}
    for (team, look), frames in sorted(by.items()):
        index[f'{team}|{look}'] = dict(sheet=str(out / f'{team}_{look}_refs.jpg'), picked=refs_sheet(team, look, frames, out),
                                       all=[dict(path=str(REFS / f['path']), element=f['element'], description=f['description']) for f in frames])
    kits = {}
    for d in sorted(art.iterdir()):
        sel = d.name
        if not all((renders / f'{sel}_{n}.png').exists() for n in ('front','back','left','tq','tb')): continue
        game_sheet(sel, renders, art, out)
        team = TEAMS[sel[:2]]; lk = look_for(sel)
        key = f'{REFTEAM.get(team, team)}|{lk}'
        kits[sel] = dict(team=team, game_sheet=str(out / f'{team}_{sel}_game.png'), look=lk if key in index else None, refs=key if key in index else None)
    json.dump(dict(kits=kits, refs=index), open(out / 'index.json', 'w'), indent=1)
    print(len(kits), 'game sheets', len(index), 'ref sheets')
if __name__ == '__main__':
    main()
