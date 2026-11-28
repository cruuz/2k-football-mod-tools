"""Texture-level old-logo detector v2: current pixels that lie between the current shell colour and the retail decal
pixel at the same place (old ink at some strength), outside the new logo's footprint."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np
from scipy import ndimage
import texdet
def refs_for(name):
    fam, rest = name.split('_'); code, side = rest[:2], rest[2]
    out = [name]
    for s in (side, 'A' if side == 'H' else 'H'):
        n = f'{fam}_{code}{s}0'
        if n not in out: out.append(n)
    return out
def explained(cur, ret, shell_cur, shell_ret, thr_decal=40.0, tol=22.0):
    """alpha (0..1) of retail ink left at each pixel, and whether the pixel is explained by it."""
    d_ret = ret - shell_cur            # where a full-strength leftover would sit relative to today's shell
    d_cur = cur - shell_cur
    n2 = (d_ret ** 2).sum(axis=2)
    alpha = np.clip((d_cur * d_ret).sum(axis=2) / np.maximum(n2, 1e-6), 0.0, 1.2)
    resid = np.linalg.norm(d_cur - alpha[..., None] * d_ret, axis=2)
    is_decal_ret = np.linalg.norm(ret - shell_ret, axis=2) > thr_decal
    cur_dev = np.linalg.norm(d_cur, axis=2)
    ok = is_decal_ret & (n2 > thr_decal ** 2) & (alpha > 0.12) & (resid <= np.maximum(tol * 0.5, 0.18 * cur_dev)) & (cur_dev > 14.0)
    return alpha, ok
def analyse(name, grow_f=1):
    fam = name.split('_')[0]
    cur = C.hcur(name)[..., :3].astype(float)
    hw = texdet.hardware(fam)[0]
    z = texdet.zone_mask(fam) & ~hw
    shell_cur = np.median(cur[z], axis=0)
    cur_dev = np.linalg.norm(cur - shell_cur, axis=2)
    ink = z & (cur_dev > 30.0)
    exp = np.zeros(cur.shape[:2], bool); strength = np.zeros(cur.shape[:2])
    for r in refs_for(name):
        ret = C.hretail(r)[..., :3].astype(float)
        shell_ret = np.median(ret[z], axis=0)
        a, ok = explained(cur, ret, shell_cur, shell_ret)
        strength = np.where(ok & ~exp, a, strength); exp |= ok
    exp &= z
    new_ink = ink & ~exp
    # the new logo's footprint: the new ink closed and filled (per panel), then grown by one pixel
    foot = ndimage.binary_closing(new_ink, structure=np.ones((3, 3), bool), iterations=2)
    foot = ndimage.binary_fill_holes(foot)
    foot = ndimage.binary_opening(foot, structure=np.ones((2, 2), bool)) | new_ink
    footg = ndimage.binary_dilation(foot, iterations=grow_f) if grow_f else foot
    left = exp & ~footg
    kept_design = new_ink.sum() < 0.05 * max(int(exp.sum()), 1) or new_ink.sum() < 40
    return dict(fam=fam, shell=shell_cur, ink=ink, exp=exp, new_ink=new_ink, foot=foot, left=left, kept_design=bool(kept_design),
                n_left=int(left.sum()), n_exp=int(exp.sum()), n_new=int(new_ink.sum()), strength=strength)
if __name__ == '__main__':
    for name in sorted(C.hindex()):
        a = analyse(name)
        print(name, 'left', a['n_left'], 'exp', a['n_exp'], 'new', a['n_new'], 'KEPT' if a['kept_design'] else '')
