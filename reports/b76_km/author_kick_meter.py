"""Beta 76 km: author the 2026 kick meter's art and geometry (DESIGN). Developer tool; not shipped.

Writes data/nfl2k5_kick_meter_2026/{meter64,meter128,arrow32}.png and geometry.json. Every pixel is our own vector
art drawn here (Roboto Condensed Bold, Apache 2.0, renders the NO WIND and MPH labels); no retail, ESPN or Madden
pixels. The geometry follows the retail KickMeter curves, sampled by running the retail sampler 0x2F010 under
Unicorn on the user's own retail scene (``--game`` points at the extracted retail files): the band's U at each path
point s is ``U_B - uoff(s)``, so the fill front sits under the marker at every meter value.

    python3 reports/b76_km/author_kick_meter.py [--game "extracted/ESPN NFL 2K5 (USA)"]
"""
import argparse, json, math, struct, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
OUT = ROOT / "data" / "nfl2k5_kick_meter_2026"
FONT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
SS = 8
T_FULL = 3.46
HUD_START, KICKMETER_OFFSET, KICKMETER_STORED = 109895680, 566720, 22432


def retail_curves(game):
    """Bone matrices and a_meter's U offset from the retail sampler at t = 0..3.46 (347 samples)."""
    import nfl_txtr as T
    import nfl2k5_scorebug_projection as P
    pack = Path(game) / "vc_53450030" / "0"
    with pack.open("rb") as f:
        f.seek(HUD_START + KICKMETER_OFFSET); span = f.read(32 + KICKMETER_STORED)
    chunk = T.parse_chunks(span, allow_trailing=True)[0]
    decoded, _ = T.decode_chunk(span, chunk)
    m = P.StaticMachine((Path(game) / "default.xbe").read_bytes()); m.record = False
    body = m.alloc(len(decoded)); m.uc.mem_write(body, decoded)
    m.run(0x2f140, ecx=body + 256, limit=500000); m.run(0x43e30, (0,), ecx=body, edx=0, limit=500000)
    rows = []
    for i in range(347):
        t = round(i * T_FULL / 346, 6)
        m.run(0x2f010, (struct.unpack("<I", struct.pack("<f", t))[0],), ecx=body + 256, limit=2000000)
        snap = bytes(m.uc.mem_read(body, len(decoded)))
        rows.append(dict(t=t, uoff=struct.unpack_from("<f", snap, 0x2f8)[0],
                         bone=[list(struct.unpack_from("<16f", snap, 0xda0 + 0x40 * k)) for k in range(4)]))
    shape = dict(scale=struct.unpack_from("<f", decoded, 2384 + 0x10)[0], offset=struct.unpack_from("<3f", decoded, 2384 + 0x20),
                 uv_scale=struct.unpack_from("<2f", decoded, 2384 + 0x30), uv_offset=struct.unpack_from("<2f", decoded, 2384 + 0x38))
    return rows, shape

# ---------------------------------------------------------------- palette (ESPN 2026 bar language)
BODY_TOP, BODY_BOTTOM = (52, 53, 59), (15, 15, 18)
RIM_TOP, RIM_BOTTOM = (236, 239, 245), (118, 124, 138)
EDGE = (8, 8, 10)
TRACK = ((22, 22, 26), (48, 49, 55), (36, 37, 42))       # inner edge, centre, outer edge
FILL_HEAD, FILL_TAIL = (236, 239, 245), (170, 179, 195)
RED = (213, 0, 54)                                        # the bar's red play-clock cell
YELLOW = (205, 198, 0)                                    # the bar's FLAG yellow
WHITE = (255, 255, 255)

# ---------------------------------------------------------------- the retail marker path
CURVES = []
def bone1(i):
    return CURVES[i]['bone'][1]
def path_point(p, i):
    M = bone1(i); x, y = p
    return (x*M[0] + y*M[4] + M[12], x*M[1] + y*M[5] + M[13])
R0, PHI0 = 48.0, math.radians(-124.2)
P0 = (R0*math.cos(PHI0), R0*math.sin(PHI0))               # marker centre, bind pose (bone 1 pivot is the origin)
TS = UOFF = PATH = None
C = None
def load_path(rows):
    global TS, UOFF, PATH, C
    CURVES[:] = rows
    TS = np.array([r['t'] for r in CURVES]); UOFF = np.array([r['uoff'] for r in CURVES])
    PATH = np.array([path_point(P0, i) for i in range(len(CURVES))])
    A = np.c_[2*PATH[:, 0], 2*PATH[:, 1], np.ones(len(PATH))]
    cx, cy, _c = np.linalg.lstsq(A, (PATH**2).sum(1), rcond=None)[0]
    C = (float(cx), float(cy))                            # badge centre = best-fit circle of the path
def path_at(s):
    """Marker centre at time s (linear interpolation of the sampled path; s may run past the ends)."""
    if s <= 0:
        d = PATH[1]-PATH[0]; return PATH[0] + d*(s/(TS[1]-TS[0]))
    if s >= T_FULL:
        d = PATH[-1]-PATH[-2]; return PATH[-1] + d*((s-T_FULL)/(TS[-1]-TS[-2]))
    return np.array([np.interp(s, TS, PATH[:, 0]), np.interp(s, TS, PATH[:, 1])])
def uoff_at(s):
    if s <= 0: return float(UOFF[0] + (UOFF[1]-UOFF[0])*(s/(TS[1]-TS[0])))
    if s >= T_FULL: return float(UOFF[-1] + (UOFF[-1]-UOFF[-2])*((s-T_FULL)/(TS[-1]-TS[-2])))
    return float(np.interp(s, TS, UOFF))
def normal_at(s):
    a, b = path_at(s-0.01), path_at(s+0.01); t = b-a; t = t/np.hypot(*t)
    n = np.array([t[1], -t[0]])                           # right of travel (CCW travel -> outward)
    q = path_at(s) - np.array(C)
    return n if n@q > 0 else -n

# ---------------------------------------------------------------- dimensions (model units = HUD pixels)
R_OUT, R_RIM, R_EDGE = 60.5, 62.5, 63.5
CH_HALF, BAND_HALF = 6.0, 7.2                             # channel (frame cut-out) and band half widths
R_FIELD = 39.0                                            # centre disc (d_middle)
FIELD_C = (-1.0, 6.0)                                     # the wind arrow's pivot (retail windmeter matrix)
PLATE = (-57.0, 23.0, -21.0, 61.0)                        # h_wind quad: x0, y0, x1, y1 (retail quad -58..-18, 26..66)
U_B = 19/64                                               # band strip: track below, fill above

# ---------------------------------------------------------------- helpers
def grid(w, h, x0, y0, sx, sy):
    """Model coordinates of a supersampled texture grid (v down)."""
    j, i = np.mgrid[0:h*SS, 0:w*SS]
    return x0 + (i+0.5)/SS*sx, y0 - (j+0.5)/SS*sy
def lerp(a, b, t):
    t = np.clip(t, 0, 1)[..., None]; return np.array(a)*(1-t) + np.array(b)*t
def compose(dst, rgb, alpha):
    a = np.clip(alpha, 0, 1)[..., None]
    out_a = a + dst[..., 3:4]*(1-a)
    dst[..., :3] = np.where(out_a > 0, (rgb*a + dst[..., :3]*dst[..., 3:4]*(1-a))/np.maximum(out_a, 1e-6), dst[..., :3])
    dst[..., 3:4] = out_a
def finish(buf, w, h):
    im = Image.fromarray(np.clip(np.round(buf*[1, 1, 1, 255]), 0, 255).astype(np.uint8), 'RGBA')
    im = premult_reduce(im)
    return im
def premult_reduce(im):
    a = np.asarray(im).astype(np.float64)
    pm = a.copy(); pm[..., :3] *= a[..., 3:4]/255
    h, w = a.shape[0]//SS, a.shape[1]//SS
    pm = pm.reshape(h, SS, w, SS, 4).mean((1, 3))
    rgb = np.where(pm[..., 3:4] > 0, pm[..., :3]*255/np.maximum(pm[..., 3:4], 1e-6), 0)
    return Image.fromarray(np.clip(np.round(np.dstack([rgb, pm[..., 3]])), 0, 255).astype(np.uint8), 'RGBA')
def seg_distance(X, Y, pts):
    """Distance from each grid point to a polyline, plus the index of the nearest segment."""
    best = np.full(X.shape, np.inf); idx = np.zeros(X.shape, int)
    for k in range(len(pts)-1):
        (ax, ay), (bx, by) = pts[k], pts[k+1]
        dx, dy = bx-ax, by-ay; L2 = dx*dx + dy*dy
        t = np.clip(((X-ax)*dx + (Y-ay)*dy)/L2, 0, 1)
        d = np.hypot(X-(ax+t*dx), Y-(ay+t*dy))
        m = d < best; best[m] = d[m]; idx[m] = k
    return best, idx
def dilate(mask, radius):
    out = mask.copy()
    for dy in range(-radius, radius+1):
        for dx in range(-radius, radius+1):
            out = np.maximum(out, np.roll(np.roll(mask, dy, 0), dx, 1))
    return out
def text_mask(text, cap_px, box_w, box_h, *, italic=0.0, tracking=0.0):
    """White text mask (float 0..1) at SS resolution, centred in a box of box_w x box_h texels."""
    size = cap_px/0.711*SS
    font = ImageFont.truetype(FONT, int(round(size)))
    im = Image.new('L', (box_w*SS, box_h*SS), 0); d = ImageDraw.Draw(im)
    widths = [d.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking*SS*(len(text)-1)
    x = (box_w*SS - total)/2
    top = (box_h*SS - cap_px*SS)/2
    asc = font.getbbox('H')[1]
    for ch, w in zip(text, widths):
        d.text((x, top - asc), ch, fill=255, font=font); x += w + tracking*SS
    return np.asarray(im).astype(np.float64)/255

# ---------------------------------------------------------------- 128 x 128: badge + centre field (c_frame, d_middle)
def meter128():
    N = 128
    X, Y = grid(N, N, C[0]-64, C[1]+64, 1, 1)
    buf = np.zeros(X.shape + (4,))
    Xr, Yr = X - C[0], Y - C[1]
    r = np.hypot(Xr, Yr)
    # outer edge, rim, body
    compose(buf, np.broadcast_to(np.array(EDGE, float), X.shape+(3,)), (r < R_EDGE).astype(float))
    rim = lerp(RIM_BOTTOM, RIM_TOP, (Yr/R_RIM+1)/2)
    compose(buf, rim, ((r < R_RIM)).astype(float))
    body = lerp(BODY_BOTTOM, BODY_TOP, (Yr/R_OUT+1)/2)
    compose(buf, body, (r < R_OUT).astype(float))
    # a soft inner bevel just inside the rim
    bevel = np.clip(1-(R_OUT-r)/3.0, 0, 1)*(r < R_OUT)
    compose(buf, np.broadcast_to(np.array((0, 0, 0), float), X.shape+(3,)), 0.35*bevel)
    # the power channel: the marker's own path, round-capped, cut out (the band shows through)
    pts = [tuple(path_at(s)) for s in np.linspace(0, T_FULL, 140)]
    d, k = seg_distance(X, Y, pts)
    # channel lips: light on the outer side, dark on the inner side
    q = np.stack([X, Y], -1); cen = np.array(C)
    outer = (np.hypot(*(q - cen).transpose(2, 0, 1)) > np.interp(k, np.arange(len(pts)), [np.hypot(p[0]-C[0], p[1]-C[1]) for p in pts]))
    lip = (d < CH_HALF+1.3) & (d >= CH_HALF)
    compose(buf, np.where(outer[..., None], np.array((104, 109, 121), float), np.array((4, 4, 6), float)), lip.astype(float)*0.9)
    # the MAX window: the last 2 percent of the sweep (v >= 0.98), outlined in red round the channel's end
    s_win = 0.98*T_FULL
    win_pts = [tuple(path_at(s)) for s in np.linspace(s_win, T_FULL, 8)]
    dw, _ = seg_distance(X, Y, win_pts)
    ring = (dw < CH_HALF+1.8) & (d >= CH_HALF-0.01)
    compose(buf, np.broadcast_to(np.array(RED, float), X.shape+(3,)), ring.astype(float))
    # cut the channel
    buf[..., 3] *= (d >= CH_HALF)
    # centre field disc (d_middle samples r < R_FIELD + 1)
    F = (FIELD_C[0], FIELD_C[1])
    fx, fy = X - F[0], Y - F[1]
    disc = np.hypot(Xr, Yr) < R_FIELD + 1.2
    sky = lerp((34, 37, 47), (12, 13, 17), np.hypot(Xr, Yr+10)/48)
    field = np.zeros(X.shape + (4,)); compose(field, sky, np.ones(X.shape))
    # perspective field: far edge y=+15 half width 16, near edge y=-23 half width 33
    yf, yn, hf, hn = 15.0, -23.0, 16.0, 33.0
    tt = (fy - yn)/(yf - yn)
    half = hn + (hf - hn)*tt
    inside = (tt >= 0) & (tt <= 1) & (np.abs(fx) <= half)
    grass = lerp((30, 116, 62), (18, 76, 42), tt)
    compose(field, grass, inside.astype(float))
    # stripes for depth (alternating shades between yard lines), yard lines, end zones
    zone = inside & ((tt < 0.12) | (tt > 0.88))
    compose(field, np.broadcast_to(np.array((12, 60, 33), float), X.shape+(3,)), zone.astype(float)*0.85)
    for yl in np.linspace(0.12, 0.88, 6):
        # perspective-correct spacing: lines bunch toward the far end
        tl = 1 - (1-yl)**1.35
        line = inside & (np.abs(tt - tl) < 0.012 + 0.006*(1-tl))
        compose(field, np.broadcast_to(np.array(WHITE, float), X.shape+(3,)), line.astype(float)*0.42)
    side = (tt >= 0) & (tt <= 1) & (np.abs(np.abs(fx) - half) < 0.55)
    compose(field, np.broadcast_to(np.array(WHITE, float), X.shape+(3,)), side.astype(float)*0.9)
    # far goalpost (FLAG yellow): base post, crossbar, uprights
    gp = ((np.abs(fx) < 0.45) & (fy > yf) & (fy < yf+3.5)) | ((np.abs(fx) < 5.0) & (np.abs(fy-(yf+3.5)) < 0.45)) \
        | ((np.abs(np.abs(fx)-5.0) < 0.45) & (fy > yf+3.5) & (fy < yf+10.0))
    compose(field, np.broadcast_to(np.array(YELLOW, float), X.shape+(3,)), gp.astype(float))
    # inner shadow at the disc edge
    edge_shadow = np.clip((np.hypot(Xr, Yr) - (R_FIELD-5))/5, 0, 1)
    compose(field, np.broadcast_to(np.array((0, 0, 0), float), X.shape+(3,)), 0.55*edge_shadow)
    buf = np.where(disc[..., None], field, buf)
    return finish(buf, N, N)

# ---------------------------------------------------------------- 64 x 64: band strip, marker, NO WIND, wind plate
REG_NOWIND = (0, 0, 32, 30)          # x, y, w, h in texels
REG_PLATE = (32, 0, 32, 38)
REG_MARKER = (0, 38, 12, 12)
REG_BAND = (0, 50, 64, 14)
def meter64():
    buf = np.zeros((64*SS, 64*SS, 4))
    def region(reg):
        x, y, w, h = reg; return (slice(y*SS, (y+h)*SS), slice(x*SS, (x+w)*SS))
    # band strip: columns carry time-behind-the-marker; rows carry the band's cross section
    x, y, w, h = REG_BAND
    j, i = np.mgrid[0:h*SS, 0:w*SS]
    col = (i+0.5)/SS; row = (j+0.5)/SS                     # texel units inside the region
    cross = np.clip((row-1.0)/(h-2.0), 0, 1)               # 0 at the inner edge row, 1 at the outer edge row
    track = np.where((cross < 0.5)[..., None], lerp(TRACK[0], TRACK[1], cross*2), lerp(TRACK[1], TRACK[2], (cross-0.5)*2))
    sheen = 1 - 0.18*np.abs(cross-0.38)*2
    ub = U_B*64
    fill = lerp(FILL_HEAD, FILL_TAIL, (col-ub)/(37-ub))*np.clip(sheen, 0, 1)[..., None]
    red = lerp((150, 0, 38), (236, 24, 72), 1-np.abs(cross-0.4)*1.6)
    strip = np.where((col < ub)[..., None], track, np.where((col < 40)[..., None], fill, red))
    sub = np.ones((h*SS, w*SS, 4)); sub[..., :3] = strip
    buf[region(REG_BAND)] = sub
    # marker: a white slider thumb with a dark keyline (long axis = texture v = radial)
    x, y, w, h = REG_MARKER
    j, i = np.mgrid[0:h*SS, 0:w*SS]
    px = (i+0.5)/SS - w/2; py = (j+0.5)/SS - h/2
    def rrect(px, py, hw, hh, rad):
        qx, qy = np.abs(px)-(hw-rad), np.abs(py)-(hh-rad)
        return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - rad
    dist = rrect(px, py, 4.6, 5.6, 2.2)
    sub = np.zeros((h*SS, w*SS, 4))
    compose(sub, np.broadcast_to(np.array((22, 21, 23), float), px.shape+(3,)), (dist < 0).astype(float))
    compose(sub, lerp((255, 255, 255), (228, 231, 238), (py+5)/10), (dist < -1.45).astype(float))
    buf[region(REG_MARKER)] = sub
    # NO WIND: two lines, white with a dark keyline
    x, y, w, h = REG_NOWIND
    m1 = text_mask('NO', 10, w, 13); m2 = text_mask('WIND', 10, w, 13)
    mask = np.zeros((h*SS, w*SS)); mask[1*SS:14*SS] = m1; mask[15*SS:28*SS] = m2
    sub = np.zeros((h*SS, w*SS, 4))
    halo = dilate(mask, (SS+3)//2)
    compose(sub, np.broadcast_to(np.array((10, 10, 12), float), mask.shape+(3,)), halo*0.75)
    compose(sub, np.broadcast_to(np.array(WHITE, float), mask.shape+(3,)), mask)
    buf[region(REG_NOWIND)] = sub
    # wind plate: a black capsule tab with the bar's bright rim; MPH under the (font3) digits
    x, y, w, h = REG_PLATE
    j, i = np.mgrid[0:h*SS, 0:w*SS]
    px = (i+0.5)/SS - w/2; py = (j+0.5)/SS - h/2
    dist = rrect(px, py, w/2-0.6, h/2-0.6, 8.0)
    sub = np.zeros((h*SS, w*SS, 4))
    compose(sub, lerp(RIM_TOP, RIM_BOTTOM, (py+h/2)/h), (dist < 0).astype(float))
    compose(sub, lerp((46, 47, 53), (14, 14, 17), (py+h/2)/h), (dist < -1.3).astype(float))
    mph = text_mask('MPH', 5.5, w, 8)
    mm = np.zeros((h*SS, w*SS)); mm[(h-10)*SS:(h-2)*SS] = mph
    compose(sub, np.broadcast_to(np.array((210, 214, 222), float), mm.shape+(3,)), mm)
    buf[region(REG_PLATE)] = sub
    return premult_reduce(Image.fromarray(np.clip(np.round(buf*[1, 1, 1, 255]), 0, 255).astype(np.uint8), 'RGBA'))

def arrow32():
    im = Image.new('RGBA', (32, 32), (0, 0, 0, 255))
    ImageDraw.Draw(im).rectangle((0, 0, 31, 15), fill=(250, 250, 252, 255))
    return im

# ---------------------------------------------------------------- geometry
def uv128(x, y):
    return ((64 + (x - C[0]))/128, (64 - (y - C[1]))/128)
def uv64(reg, fx, fy):
    x, y, w, h = reg
    return ((x + fx*w)/64, (y + fy*h)/64)
def strip_disc(cx, cy, rad, rows):
    """A disc as one triangle strip of horizontal rows: returns vertex list (left/right pairs, top to bottom)."""
    out = []
    for k in range(rows):
        yy = rad*math.cos(math.pi*k/(rows-1))
        xx = math.sqrt(max(rad*rad - yy*yy, 0))
        out += [(cx - xx, cy + yy), (cx + xx, cy + yy)]
    return out
def ring(cx, cy, r0, r1, segs, a0=0.0, a1=2*math.pi):
    out = []
    for k in range(segs+1):
        a = a0 + (a1-a0)*k/segs
        out += [(cx + r0*math.cos(a), cy + r0*math.sin(a)), (cx + r1*math.cos(a), cy + r1*math.sin(a))]
    return out
def quad(cx, cy, hw, hh):
    return [(cx-hw, cy+hh), (cx+hw, cy+hh), (cx-hw, cy-hh), (cx+hw, cy-hh)]   # strip order TL, TR, BL, BR
def seq(n, first):
    return list(range(first, first+n))
def join(strips):
    """Concatenate strips with degenerate joins; each strip keeps its own winding parity."""
    out = []
    for s in strips:
        if out:
            out += [out[-1], s[0]]
            if len(out) % 2 == 1: out.append(s[0])
        out += s
    if len(out) % 2: out.append(out[-1])
    return out

LETTER_H, STROKE, SLANT = 20.0, 5.2, 0.21
def max_quads():
    """MAX as nine quads (strip order), bold italic, centred on bone 2's pivot."""
    H, w = LETTER_H, STROKE
    Wm, Wa, Wx, gap = 22.0, 20.0, 19.0, 2.4
    q = []
    x = 0.0
    # M: stems and the two diagonals meeting at 22 percent height
    q.append([(x, H), (x+w, H), (x, 0), (x+w, 0)])
    q.append([(x+Wm-w, H), (x+Wm, H), (x+Wm-w, 0), (x+Wm, 0)])
    q.append([(x, H), (x+w*1.25, H), (x+Wm/2-w*0.62, H*0.22), (x+Wm/2+w*0.62, H*0.22)])
    q.append([(x+Wm-w*1.25, H), (x+Wm, H), (x+Wm/2-w*0.62, H*0.22), (x+Wm/2+w*0.62, H*0.22)])
    x += Wm + gap
    # A: two legs meeting at the apex, crossbar at 26 percent
    q.append([(x+Wa/2-w*0.62, H), (x+Wa/2+w*0.2, H), (x, 0), (x+w*1.12, 0)])
    q.append([(x+Wa/2-w*0.2, H), (x+Wa/2+w*0.62, H), (x+Wa-w*1.12, 0), (x+Wa, 0)])
    cb0, cb1 = H*0.24, H*0.24 + w*0.78
    def leg_x(y, left):
        t = y/H
        return (x + w*1.12*(1-t) + (Wa/2+w*0.2)*t) if left else (x + (Wa-w*1.12)*(1-t) + (Wa/2-w*0.2)*t)
    q.append([(leg_x(cb1, True)-0.3, cb1), (leg_x(cb1, False)+0.3, cb1), (leg_x(cb0, True)-0.3, cb0), (leg_x(cb0, False)+0.3, cb0)])
    x += Wa + gap
    # X: two crossing diagonals
    q.append([(x+Wx-w*1.2, H), (x+Wx, H), (x, 0), (x+w*1.2, 0)])
    q.append([(x, H), (x+w*1.2, H), (x+Wx-w*1.2, 0), (x+Wx, 0)])
    width = x + Wx
    return q, width
def shear_centre(quads, width, cx, cy):
    out = []
    for qd in quads:
        out.append([(px + SLANT*(py - LETTER_H/2) - width/2 + cx, py - LETTER_H/2 + cy) for px, py in qd])
    return out

def build_geometry():
    V = [None]*575               # (x, y, z, u, v, argb, selector)
    idx = {}
    def put(first, verts, z, uvs, colours, sel):
        for k, (p, uv, c) in enumerate(zip(verts, uvs, colours)):
            V[first+k] = (p[0], p[1], z, uv[0], uv[1], c, sel)
    def orient(strips):
        """Every sub-strip starts front-facing like the retail scene (positive area in model x, y). The kick meter's
        textured materials cull back faces (material +0x60 bit 26 set: retail 0x2FC80 enables CULL_FACE), so a
        reversed strip does not draw at all (km lab 1: the centre disc, NO WIND and the MPH tab were missing)."""
        out = []
        for strip in strips:
            area = 0.0
            for i in range(len(strip) - 2):
                a, b, c = V[strip[i]], V[strip[i + 1]], V[strip[i + 2]]
                t = ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2
                if abs(t) > 1e-9:
                    area = t if i % 2 == 0 else -t
                    break
            if area < 0:
                strip = [strip[k ^ 1] for k in range(len(strip))]   # swap within each pair: every triangle flips
            out.append(strip)
        return out
    # 0. a_meter: the band, one strip along the marker path, 40 pairs (s from -0.22 to 3.68)
    ss = np.linspace(-0.22, T_FULL+0.22, 40)
    verts, uvs = [], []
    v_in, v_out = (REG_BAND[1]+0.6)/64, (REG_BAND[1]+REG_BAND[3]-0.6)/64
    for s in ss:
        c = path_at(s); n = normal_at(s); u = U_B - uoff_at(s)
        verts += [tuple(c - n*BAND_HALF), tuple(c + n*BAND_HALF)]
        uvs += [(u, v_in), (u, v_out)]
    put(0, verts, 0.0, uvs, [0xFFFFFFFF]*80, 0)
    idx['a_meter'] = join(orient([seq(80, 0)]))
    # 1. b_ball: the marker, a radial slider thumb centred on P0 (bind pose; bone 1 carries it)
    er = np.array(P0) - np.array(C); er /= np.hypot(*er); et = np.array([-er[1], er[0]])
    hw_t, hw_r = 5.0, 8.2
    corners = [np.array(P0) + a*et*hw_t + b*er*hw_r for a, b in ((-1, 1), (1, 1), (-1, -1), (1, -1))]
    mx, my, mw, mh = REG_MARKER
    uvm = [((mx+0.5+(0 if a < 0 else mw-1))/64, (my+0.5+(0 if b > 0 else mh-1))/64) for a, b in ((-1, 1), (1, 1), (-1, -1), (1, -1))]
    put(80, [tuple(c) for c in corners], 10.0, uvm, [0xFFFFFFFF]*4, 3)
    idx['b_ball'] = join(orient([seq(4, 80)]))
    # 2. c_frame: the badge ring, planar-mapped (51 segments, 104 vertices)
    verts = ring(C[0], C[1], R_FIELD - 0.5, R_EDGE + 0.4, 51)
    put(84, verts, 17.8, [uv128(*p) for p in verts], [0xFFFFFFFF]*104, 0)
    idx['c_frame'] = join(orient([seq(104, 84)]))
    # 3. d_middle: the centre field disc (34 rows, 68 vertices; one spare)
    verts = strip_disc(C[0], C[1], R_FIELD + 1.0, 34)
    put(188, verts + [verts[-1]], 19.4, [uv128(*p) for p in verts + [verts[-1]]], [0xFFFFFFFF]*69, 0)
    idx['d_middle'] = join(orient([seq(68, 188)]))
    # 4. e_nowind: one quad over the field (spares collapse onto it)
    nx, ny, nw, nh = REG_NOWIND
    verts = quad(FIELD_C[0], FIELD_C[1] - 3.0, 18.0, 16.9)
    uvs = [uv64(REG_NOWIND, 0, 0), uv64(REG_NOWIND, 1, 0), uv64(REG_NOWIND, 0, 1), uv64(REG_NOWIND, 1, 1)]
    put(257, verts + [verts[-1]]*24, 20.5, uvs + [uvs[-1]]*24, [0xFFFFFFFF]*28, 0)
    idx['e_nowind'] = join(orient([seq(4, 257)]))
    # 5. f_frame1: the MAX disc (tint 150,0,12 from the retail curve), glossy top-to-bottom shade
    verts = strip_disc(C[0], C[1], R_FIELD + 1.0, 50)
    cols = []
    for (px, py) in verts:
        t = (py - (C[1] - R_FIELD))/(2*R_FIELD); g = int(round(96 + 159*max(0, min(1, t))))
        cols.append(0xFF000000 | (g << 16) | (g << 8) | g)
    put(285, verts, 24.7, [(0, 0)]*100, cols, 0)
    idx['f_frame1'] = join(orient([seq(100, 285)]))
    # 6. g_frame2: black vignette ring over the MAX disc (alpha rises toward the edge)
    verts = ring(C[0], C[1], 18.0, R_FIELD + 1.0, 36)
    cols = [0x00000000 if k % 2 == 0 else 0xB4000000 for k in range(74)]
    put(385, verts, 25.2, [(0, 0)]*74, cols, 0)
    idx['g_frame2'] = join(orient([seq(74, 385)]))
    # 7. h_wind: the wind plate tab (upper left)
    x0, y0, x1, y1 = PLATE
    verts = [(x0, y1), (x1, y1), (x0, y0), (x1, y0)]
    px_, py_, pw_, ph_ = REG_PLATE
    uvs = [((px_+0.3)/64, (py_+0.3)/64), ((px_+pw_-0.3)/64, (py_+0.3)/64), ((px_+0.3)/64, (py_+ph_-0.3)/64), ((px_+pw_-0.3)/64, (py_+ph_-0.3)/64)]
    put(459, verts, 28.9, uvs, [0xFFFFFFFF]*4, 0)
    idx['h_wind'] = join(orient([seq(4, 459)]))
    # 8. i_lambert5: the MAX pulse ring on bone 3 (pivot -1.0945, 2.1552): FLAG yellow through the retail tint
    piv3 = (-1.0945, 2.1552)
    verts = ring(piv3[0], piv3[1], 9.0, 12.5, 10)
    cols = [0x00CDF600 if k % 2 == 0 else 0xC8CDF600 for k in range(22)]
    put(463, verts, 34.3, [(0, 0)]*22, cols, 9)
    idx['i_lambert5'] = join(orient([seq(22, 463)]))
    # 9..12. MAX: letters (l_max), their shadow (j_max1), the red underline (m_max) and its shadow (k_max1), bone 2
    piv2 = (-0.1230, 0.8527)
    quads, width = max_quads()
    letters = shear_centre(quads, width, piv2[0], piv2[1] + 1.5)
    shadow = [[(px + 1.3, py - 1.3) for px, py in qd] for qd in letters]
    def letter_block(first, qs, z, colour_fn, sel):
        verts, cols = [], []
        for qd in qs:
            verts += qd; cols += [colour_fn(py) for _, py in qd]
        verts += [verts[-1]]*(41 - len(verts)); cols += [cols[-1]]*(41 - len(cols))
        put(first, verts, z, [(0, 0)]*41, cols, sel)
        return join(orient([seq(4, first + 4*k) for k in range(len(qs))]))
    top, bot = piv2[1] + 1.5 + LETTER_H/2, piv2[1] + 1.5 - LETTER_H/2
    def white_grad(py):
        t = (py - bot)/(top - bot); g = int(round(214 + 41*max(0, min(1, t))))
        return 0xFF000000 | (g << 16) | (g << 8) | g
    idx['j_max1'] = letter_block(485, shadow, 41.0, lambda py: 0xA2000000, 6)
    idx['l_max'] = letter_block(530, letters, 44.1, white_grad, 6)
    ubar = [(px + SLANT*(py - (bot - 4.2)), py) for px, py in
            [(-width/2 + piv2[0] - 1, bot - 3.0), (width/2 + piv2[0] - 1, bot - 3.0), (-width/2 + piv2[0] - 1, bot - 6.2), (width/2 + piv2[0] - 1, bot - 6.2)]]
    put(526, [(px + 1.3, py - 1.3) for px, py in ubar], 42.2, [(0, 0)]*4, [0xA2000000]*4, 6)
    idx['k_max1'] = join(orient([seq(4, 526)]))
    put(571, ubar, 45.2, [(0, 0)]*4, [0xFF000000 | (RED[0] << 16) | (RED[1] << 8) | RED[2]]*4, 6)
    idx['m_max'] = join(orient([seq(4, 571)]))
    assert all(v is not None for v in V), [k for k, v in enumerate(V) if v is None]
    return V, idx

WIND_SHADES = {0xFF3F3F00: 0xFF3C3E46, 0xFF4C4C00: 0xFF585C66, 0xFFB2B200: 0xFFCDD0D8, 0xFFE5E54C: 0xFFFFFFFF}


DIGIT_ATLAS = (64, 64)
DIGIT_TOP, DIGIT_BOTTOM = 6.0, 23.0          # the retail font3 line box: glyphs 17 px tall under the anchor
def digits_font():
    """The wind digits (0-9) from the sprite scorebug's traced score numerals (the bar's own face), scaled to the
    retail font3 height, packed into a 64x64 alpha atlas (two rows); plus our own minus bar. Returns (image, metrics)."""
    layout = json.loads((ROOT / "data" / "nfl2k5_scorebug_sprite" / "layout.json").read_text(encoding="utf-8"))
    template = Image.open(ROOT / "data" / "nfl2k5_scorebug_sprite" / "template.png").convert("RGBA")
    height = int(DIGIT_BOTTOM - DIGIT_TOP)
    atlas = Image.new("L", DIGIT_ATLAS, 0)
    glyphs = {}
    x, y = 1, 1
    for ch in "0123456789":
        if ch == "5":
            x, y = 1, 1 + height + 2
        cell = template.crop(tuple(layout["cells"]["score_" + ch]["box"])).getchannel("A")
        width = max(3, round(cell.width * height / cell.height))
        glyph = cell.resize((width, height), Image.LANCZOS)
        atlas.paste(glyph, (x, y))
        glyphs[ch] = dict(atlas=[x, y, x + width, y + height], quad=[1, DIGIT_TOP, 1 + width, DIGIT_BOTTOM], advance=width + 2)
        x += width + 2
        assert x <= DIGIT_ATLAS[0], (ch, x)
    y = 1 + 2 * (height + 2)
    atlas.paste(Image.new("L", (6, 3), 255), (1, y))
    glyphs["-"] = dict(atlas=[1, y, 7, y + 3], quad=[1, 14.0, 7, 17.0], advance=8)
    # 16 alpha levels (the FONT palette: white, alpha 0x00..0xFF in steps of 0x11)
    levels = atlas.point(lambda a: round(a / 17) * 17)
    image = Image.merge("RGBA", (Image.new("L", DIGIT_ATLAS, 255),) * 3 + (levels,))
    return image, dict(atlas=list(DIGIT_ATLAS), glyphs=glyphs, space_advance=6, line_advance=24,
                       source="data/nfl2k5_scorebug_sprite template.png score_0..score_9 (traced 2026 bar numerals)")

def quantize(V, shape):
    """Retail lanes: positions NORMSHORT3 through the shape's scale and offset, UVs NORMSHORT2 through its UV constant."""
    def ns(x):
        s = x*32767.0 if x >= 0 else x*32768.0
        return max(-32768, min(32767, int(round(s))))
    out = []
    for x, y, z, u, v, argb, sel in V:
        q = [ns((val - o)/shape['scale']) for val, o in zip((x, y, z), shape['offset'])]
        uq = [ns((u - shape['uv_offset'][0])/shape['uv_scale'][0]), ns((v - shape['uv_offset'][1])/shape['uv_scale'][1])]
        out.append([*q, *uq, argb, sel])
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game", default=str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)"))
    args = ap.parse_args()
    rows, shape = retail_curves(args.game)
    load_path(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    meter128().save(OUT/'meter128.png', optimize=True); meter64().save(OUT/'meter64.png', optimize=True)
    arrow32().save(OUT/'arrow32.png', optimize=True)
    digits_image, digits_metrics = digits_font()
    digits_image.save(OUT/'digits.png', optimize=True)
    V, idx = build_geometry()
    doc = dict(schema="nfl2k5_kick_meter_2026_geometry/v1",
               design=dict(badge_centre=[round(c, 4) for c in C], marker_bind_centre=[round(p, 4) for p in P0], u_b=U_B,
                           band_half_width=BAND_HALF, channel_half_width=CH_HALF, field_radius=R_FIELD,
                           wind_plate=list(PLATE), note="DESIGN; the geometry follows the retail curves (bone 1, a_meter +0x28)"),
               kick_meter=dict(vertices=quantize(V, shape), strips=idx),
               windmeter=dict(shades={"0x%08x" % k: "0x%08x" % v for k, v in sorted(WIND_SHADES.items())}),
               digits=digits_metrics)
    (OUT/'geometry.json').write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print('centre', C, {k: len(v) for k, v in idx.items()})

if __name__ == "__main__":
    main()
