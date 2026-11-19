"""Review sheet: the Standard shell on the game's own model, both sides, retail art | released (v0.9) | beta 81, for six
clubs. Offline render with the model's own UVs (not an emulator frame)."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, flat, geom, final
from PIL import Image, ImageDraw
g, parts = geom.load_gltf('retail'); views = {}
for yaw in (-90, 90):
    view = {"yaw": yaw, "pitch": 5, "roll": 0, "dist": 1.0, "target": [0, -0.03, 0.79], "fov": 22}
    views[yaw] = geom.raster(parts, ['HI_HELMET_A', 'LOGO_helmet'], view, 384)
def tile(tex, yaw, label):
    pid, U, V, z = views[yaw]; s = flat.bilinear(tex.astype(float), U, V); img = np.full((384, 384, 3), 128.0); mm = pid >= 0; img[mm] = s[mm, :3]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)[36:258, 54:330]); ImageDraw.Draw(im).text((3, 3), label, fill=(255, 255, 0)); return np.asarray(im)
rows = []
for sel in sys.argv[1:]:
    n = 'helmet00_' + sel; t = C.TEAMS[sel[:2]]; R = C.hretail(n); B = final.helmet(n); A = C.load(C.WORK.parent / 'out' / 'helmets_compiled' / f'{n}.png')
    rows.append(np.concatenate([tile(R, -90, f'{t} retail 2004, right'), tile(B, -90, f'{t} released v0.9, right'), tile(A, -90, f'{t} beta 81, right'),
                                tile(R, 90, f'{t} retail 2004, left'), tile(B, 90, f'{t} released v0.9, left'), tile(A, 90, f'{t} beta 81, left')], axis=1))
Image.fromarray(np.concatenate(rows, axis=0)).save(C.WORK.parent / 'review' / 'standard_shell_tilt_after.png'); print(rows[0].shape, len(rows))
