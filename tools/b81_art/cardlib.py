"""b81-art authoring helpers: the league project's Team Select cards and helmets, their retail twins and the Studio's
own 256-colour card compile. Authoring only (needs the user's own disc and the SOFTDRINK pack); nothing here ships."""
import sys, json, os
from pathlib import Path
import numpy as np
from PIL import Image
WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WT / 'tools')); sys.path.insert(0, str(WT))
INDEX = Path(__import__('os').environ.get('NFL2K5_RETAIL_INDEX', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
INV = WT / 'reports/assets/nfl2k5_team_select_card_inventory.json'
WORK = Path(__import__('os').environ.get('B81_ART_WORK', '/home/noah/2k-worktrees/.b77-scratch/b81/art/work'))
TEAMS = {'00':'ARI','01':'ATL','02':'BAL','03':'BUF','04':'CAR','05':'CHI','06':'CIN','07':'DAL','08':'DEN','09':'DET','10':'GB','11':'IND','12':'JAX','13':'KC','14':'MIA','15':'MIN','16':'NE','17':'NO','18':'NYG','19':'NYJ','20':'LV','21':'PHI','22':'PIT','23':'LAR','24':'LAC','25':'SF','26':'SEA','27':'TB','28':'TEN','29':'WAS','30':'CLE','37':'HOU'}
_idx = None
def index():
    global _idx
    if _idx is None: _idx = json.load(open(WORK / 'card_index.json'))
    return _idx
def load(path):
    return np.asarray(Image.open(path).convert('RGBA'), dtype=np.uint8).copy()
def cur(name):
    return load(index()[name])
def parse(name):
    fam, rest, style, res = name.split('_')
    return fam, rest[1:], ('home' if rest[0]=='h' else 'away'), int(style), int(res)
_arch = None; _targets = None
def retail(name):
    cache = WORK / 'retail' / (name + '.png')
    if cache.exists(): return load(cache)
    global _arch, _targets
    from nfl_outer import parse_archive, read_entry_range
    from nfl_txtr import texture_to_rgba
    import nfl_team_select_card_png_import as ci
    import nfl_team_select_card_targets as ct
    if _arch is None:
        _arch = parse_archive(INDEX)
        _, _, value = ct.load_report(INV)
        _targets = {r['selector']: r for r in value['targets']}
    fam, code, side, style, res = parse(name)
    t = ct.CardTarget.from_record(_targets[ct.normalize(fam, code, side, style, res)])
    entry = _arch.entries[t.outer_index]
    span = read_entry_range(_arch, entry, t.chunk_offset, t.span_size)
    chunk, decoded, texture = ci.validate_template(span, t)
    rgba = np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(res, res, 4).copy()
    cache.parent.mkdir(exist_ok=True)
    Image.fromarray(rgba, 'RGBA').save(cache)
    return rgba
def quantize(rgba):
    """What the Studio importer stores: 256-entry median cut P8 (RGBA palette)."""
    import nfl_tset_png_import as pt
    h, w = rgba.shape[:2]
    level = pt.MipLevel(0, w, h, rgba.tobytes())
    palette, index_levels, q = pt.quantize_levels([level])
    out = pt.rgba_from_indices(index_levels[0], palette)
    return np.frombuffer(out, np.uint8).reshape(h, w, 4).copy()
def over(rgba, bg=(128,128,128)):
    a = rgba[...,3:4].astype(np.float64)/255.0
    return np.clip(np.floor(rgba[...,:3]*a + np.array(bg)*(1-a) + 0.5),0,255).astype(np.uint8)
def up(rgb, s, resample=Image.NEAREST):
    im = Image.fromarray(rgb)
    return np.asarray(im.resize((im.width*s, im.height*s), resample))
def hstack(arrs, gap=6, bg=(60,60,60)):
    H = max(a.shape[0] for a in arrs); W = sum(a.shape[1] for a in arrs) + gap*(len(arrs)-1)
    out = np.zeros((H, W, 3), np.uint8); out[:] = bg; x = 0
    for a in arrs:
        out[:a.shape[0], x:x+a.shape[1]] = a; x += a.shape[1] + gap
    return out

_hidx = None
def hindex():
    global _hidx
    if _hidx is None: _hidx = json.load(open(WORK / 'helmet_index.json'))
    return _hidx
def hcur(name):
    return load(hindex()[name])
_harch = None
def hretail(name):
    """name like helmet02_02H0 -> retail RGBA."""
    cache = WORK / 'retail_helmet' / (name + '.png')
    if cache.exists(): return load(cache)
    global _harch
    from nfl_outer import parse_archive, read_entry_range
    from nfl_txtr import decode_chunk
    import nfl_live_helmet_txtr_png_import as hi
    import nfl_live_helmet_txtr_targets as ht
    if _harch is None: _harch = parse_archive(INDEX)
    fam, rest = name.split('_'); code, side, variant = rest[:2], rest[2], int(rest[3:])
    _, _, _, t = ht.select_target(code, side, variant, fam)
    entry = _harch.entries[t.outer_index]
    span = read_entry_range(_harch, entry, t.chunk_offset, t.span_size)
    decoded, info = decode_chunk(span, hi.as_chunk(t))
    base = hi.decode_levels(decoded)[0]
    rgba = np.frombuffer(base.rgba, np.uint8).reshape(base.height, base.width, 4).copy()
    cache.parent.mkdir(exist_ok=True)
    Image.fromarray(rgba, 'RGBA').save(cache)
    return rgba
