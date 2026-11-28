"""Team Select cards from the cleaned helmets: the shipped card keeps every pixel the helmet change does not touch;
where the render of the cleaned helmet differs from the render of the old helmet art, the card takes the new render
(plus the shipped card's own smooth offset from the old render around that place)."""
import sys, json, hashlib; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, final, post
from scipy import ndimage
from pathlib import Path
sys.path.insert(0, str(C.WT / 'tools'))
import b780_team_select_old_logo_cleanup as art1
R = C.WORK / 'bl' / 'r'
TAU = 6.0 / 255.0          # a render difference this large (any channel, premultiplied) is a real change
TAU_E = 14.0 / 255.0       # the shipped card differs this much from the old render: it was edited by hand there
BAR_TOP = 158
PASS_CARDS = {'29_0', '13_0'}      # cards the Washington W and Chiefs red passes repaint at build time
def premul(rgba_u8):
    a = rgba_u8.astype(np.float64) / 255.0
    a[..., :3] *= a[..., 3:4]
    return a
def unpremul_u8(pm, alpha_u8):
    al = alpha_u8.astype(np.float64)[..., None] / 255.0
    rgb = np.where(al > 1e-6, pm[..., :3] / np.maximum(al, 1e-6), 0.0)
    return np.clip(np.floor(rgb * 255.0 + 0.5), 0, 255).astype(np.uint8)
def base_card(name):
    """The card the new one starts from: the league project's PNG, or the built card for the slots a build pass
    repaints (so the pass's work is kept)."""
    fam, code, side, style, res = C.parse(name)
    return final.card(name) if f'{code}_{style}' in PASS_CARDS else C.cur(name)
_uv = {}
def uv(view, side):
    key = 'unif' if view == 'unif' else side
    if key not in _uv:
        d = np.load(C.WORK / (f'uvmap_modern_{side}_1024.npz' if view == 'helm' else 'uvmap_modern_unif_1024.npz'))
        _uv[key] = (d['pid'], np.clip((d['U'] * 256).astype(int), 0, 255), np.clip((d['V'] * 256).astype(int), 0, 255))
    return _uv[key]
def drop_specks(mask, least=4):
    """A thin drawn line stays (an outline one texel wide); lone texels of palette noise go."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3), bool))
    if not n: return mask
    sizes = ndimage.sum(mask, lab, np.arange(1, n + 1))
    return np.isin(lab, [i + 1 for i, s_ in enumerate(sizes) if s_ >= least])
def texture_change(sel):
    """Texels of the kit's helmet02 that really changed: the cleanup itself, and art a build pass redrew after the
    cards were rendered (not the importer's palette noise)."""
    import assign
    old_path = C.hindex().get(f'helmet02_{sel}') or str(C.WORK / 'final' / 'helmets' / f'helmet02_{sel}.png')
    old = C.load(old_path)[..., :3].astype(int)
    new = C.load(assign.new_tex_path('helmet02', sel))[..., :3].astype(int)
    fin_p = C.WORK / 'final' / 'helmets' / f'helmet02_{assign.REASSIGN.get(sel, sel)}.png'
    fin = C.load(fin_p)[..., :3].astype(int)
    cleaned = (new != fin).any(axis=2)
    redrawn = drop_specks(np.abs(fin - old).max(axis=2) > 44)
    return ndimage.binary_dilation(cleaned | redrawn, iterations=1)
def card_mask(sel, view, side):
    pid, u, v = uv(view, side)
    S = texture_change(sel)
    hit = (pid >= 0) & (pid <= 2) & S[v, u]
    return hit.reshape(256, 4, 256, 4).any(axis=(1, 3))
FOLLOW_GAME = set(json.load(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'follow_game.json'))))
def compose(name, follow_game=None):
    fam, code, side, style, res = C.parse(name)
    assert res == 256
    S_ = 'H' if side == 'home' else 'A'
    sel = f"{code}{S_}{style}"
    view = 'helm' if fam == 'helm' else 'unif'
    old = base_card(name)
    M = ndimage.binary_dilation(card_mask(sel, view, S_), iterations=2)
    Ro = post.layer256(R / 'old' / f'{sel}_{view}.png'); Rn = post.layer256(R / 'new' / f'{sel}_{view}.png')
    P = premul(old)
    D = Rn[..., :3] - Ro[..., :3]
    E = P[..., :3] - Ro[..., :3]
    live = np.ones((256, 256), bool)
    if fam == 'helm': live[BAR_TOP:] = False
    cov = Ro[..., 3] > 0.02
    z = M & live & cov & (np.abs(D).max(axis=2) > 1.5 / 255.0)
    z = ndimage.binary_dilation(z, iterations=1) & M & live & cov
    if follow_game is None: follow_game = name in FOLLOW_GAME
    if follow_game:
        # the shipped card shows helmet art the league project's own helmet no longer has (it was rendered from older
        # art): those places take the render of today's helmet as well. Whole blobs on the open shell only.
        pid, _u, _v = uv(view, S_)
        shell = ndimage.binary_erosion(((pid == 0) | (pid == 1)).reshape(256, 4, 256, 4).all(axis=(1, 3)), iterations=1)
        far = shell & live & (Ro[..., 3] > 0.98) & (np.abs(E).max(axis=2) > 30.0 / 255.0)
        far = ndimage.binary_opening(far, structure=np.ones((2, 2), bool))
        lab, n = ndimage.label(far, structure=np.ones((3, 3), bool))
        if n:
            sizes = ndimage.sum(far, lab, np.arange(1, n + 1))
            far = np.isin(lab, [i + 1 for i, s_ in enumerate(sizes) if s_ >= 30])
            z = z | (ndimage.binary_dilation(far, iterations=3) & shell & live)
    hand = ndimage.binary_dilation(z & (np.abs(E).max(axis=2) > TAU_E), iterations=1) & z
    # the shipped card's own smooth offset from the old render, carried across the hand-edited places
    keep = (~hand) & cov & live & (Ro[..., 3] > 0.98)
    w = ndimage.gaussian_filter(keep.astype(np.float64), 3.0)
    c = np.stack([ndimage.gaussian_filter(np.where(keep, E[..., k], 0.0), 3.0) for k in range(3)], axis=-1) / np.maximum(w, 1e-6)[..., None]
    c[w < 1e-3] = 0.0
    Ep = np.where(hand[..., None], c, E)
    newP = P[..., :3].copy()
    newP[z] = (Rn[..., :3] + Ep)[z]
    out = old.copy()
    rgb = unpremul_u8(np.clip(newP, 0, 1), old[..., 3])
    out[z, :3] = rgb[z]
    # only pixels that really change count
    return out, dict(zone=int(z.sum()), hand=int(hand.sum()), changed=int((out != old).any(axis=2).sum()))
def half(name128, new256):
    old128 = base_card(name128); old256 = base_card(name128.replace('_128', '_256'))
    return art1.derive_half(old128, old256, new256)
def sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
if __name__ == '__main__':
    from PIL import Image
    names = sys.argv[1:]
    for n in names:
        out, st = compose(n)
        b = final.card(n); q = C.quantize(out)
        print(n, st)
        Image.fromarray(C.hstack([C.up(C.over(b), 3), C.up(C.over(q), 3)])).save(C.WORK / f'view_cmp_{n}.png')
