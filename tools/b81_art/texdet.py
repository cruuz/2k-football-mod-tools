"""Texture-level old-logo detector (prototype): untouched retail decal pixels left beside a repainted logo."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np
from scipy import ndimage
ZONE = {'helmet02': (6, 16, 146, 240), 'helmet00': (6, 16, 150, 240)}   # x0,y0,x1,y1 of the two side panels
def zone_mask(fam):
    x0, y0, x1, y1 = ZONE[fam]; m = np.zeros((256, 256), bool); m[y0:y1, x0:x1] = True; return m
_hw = {}
def hardware(fam):
    """Everything that is not flat shell on the blank (Cleveland) retail helmet of this shell: screws, vents, ear
    holes, creases, the flag; grown by 1."""
    if fam not in _hw:
        t = C.hretail(f'{fam}_30H0')[..., :3].astype(float)
        z = zone_mask(fam)
        shell = np.median(t[z], axis=0)
        dev = np.abs(t - shell).max(axis=2)
        _hw[fam] = (ndimage.binary_dilation(dev > 8, iterations=2), dev)
    return _hw[fam]
def shell_colour(rgb, fam):
    z = zone_mask(fam) & ~hardware(fam)[0]
    return np.median(rgb[z], axis=0)
def decal_mask(rgb, fam, thr=40.0):
    """Pixels of the side panels that are neither shell nor the blank helmet's own hardware."""
    z = zone_mask(fam) & ~hardware(fam)[0]
    shell = shell_colour(rgb, fam)
    dev = np.linalg.norm(rgb.astype(float) - shell, axis=2)
    return z & (dev > thr), dev
def analyse(name, tol=3):
    fam = name.split('_')[0]
    cur = C.hcur(name)[..., :3].astype(int); ret = C.hretail(name)[..., :3].astype(int)
    same = (np.abs(cur - ret).max(axis=2) <= tol)
    rdecal, rdev = decal_mask(ret, fam)
    cdecal, cdev = decal_mask(cur, fam)
    z = zone_mask(fam)
    modified = z & ~same
    left = rdecal & same & cdecal          # retail decal pixel, untouched, and still not shell in the current art
    return dict(fam=fam, same_frac=float(same.mean()), zone_same=float(same[z].mean()), modified=int(modified.sum()),
                rdecal=int(rdecal.sum()), cdecal=int(cdecal.sum()), left=int(left.sum()), mask=left, modmask=modified,
                rdecal_mask=rdecal, cdecal_mask=cdecal)
if __name__ == '__main__':
    rows = []
    for name in sorted(C.hindex()):
        a = analyse(name)
        rows.append((name, a))
    print('name same zone_same modified rdecal cdecal left')
    for name, a in rows:
        print(name, round(a['same_frac'], 3), round(a['zone_same'], 3), a['modified'], a['rdecal'], a['cdecal'], a['left'])
