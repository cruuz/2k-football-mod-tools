"""Reference fragment path for the captured retail HUD NV2A state.

Equations follow xemu f9b1403 pgraph/glsl/{vsh-prog,psh}.c, texture.c,
swizzle.c and gl/draw.c. This is a bounded reference, not a complete NV2A.
Missing frame state stays missing; no screenshot-fitted darkening is applied.
"""
from functools import lru_cache
import hashlib
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]


def rgba(word):
    return tuple(((word >> s) & 255)/255 for s in (16, 8, 0, 24))


def input_value(byte, registers, alpha=False):
    """xemu get_input_var: register, channel selection, then mapping."""
    value = registers[byte & 15]
    value = (value[3 if byte & 16 else 2],) if alpha else ((value[3],)*3 if byte & 16 else value[:3])
    def mapping(x):
        positive = max(x, 0)
        return (positive, 1-min(positive, 1), 2*positive-1, 1-2*positive,
                positive-.5, .5-positive, x, -x)[byte >> 5]
    return tuple(mapping(v) for v in value)


def combiner(state, texture, diffuse, fog=(0, 0, 0, 1)):
    """Evaluate the decoded single multiply stage and final E*F/fog mix.

    General stage routing beyond this observed program is refused. Constants
    remain inputs, so a future captured final C0 change is not hidden.
    """
    def get(offset):
        return state[f'0x{offset:04x}']
    expected = {0x0260:0xd8d41010, 0x0ac0:0xc8c40000,
                0x0aa0:0x100c0, 0x1e40:0x100c0, 0x1e60:0x11101,
                0x0288:0x0f030c00, 0x028c:0x11331c80}
    if any(get(k) != v for k, v in expected.items()):
        raise ValueError('Unsupported captured register-combiner program')
    regs = {0:(0,)*4, 1:rgba(get(0xa60)), 2:rgba(get(0xa80)),
            3:fog, 4:diffuse, 8:texture}
    result = []
    for alpha, offset in ((False, 0xac0), (True, 0x260)):
        word = get(offset)
        a, b, c, d = [input_value(word >> shift & 255, regs, alpha) for shift in (24, 16, 8, 0)]
        # AB routes to R0, shift-left-one, clamp [-1,1]. CD is discarded.
        result.extend(max(-1, min(1, 2*x*y)) for x, y in zip(a, b))
    regs[12] = tuple(result)
    regs[1], regs[2] = rgba(get(0x1e20)), rgba(get(0x1e24))
    e, f = [input_value(get(0x28c) >> shift & 255, regs) for shift in (24, 16)]
    regs[15] = tuple(x*y for x,y in zip(e,f))+(0,)
    a,b,c,d = [input_value(get(0x288) >> shift & 255, regs) for shift in (24,16,8,0)]
    rgb = tuple(min(1,max(0,w+x*y+(1-x)*z)) for x,y,z,w in zip(a,b,c,d))
    return rgb+input_value(get(0x28c) >> 8 & 255,regs,True)


@lru_cache(maxsize=40)
def texture(span):
    """Independent P8/BGRA decode with xemu's rectangular Morton ordering."""
    import numpy as np
    from PIL import Image
    from mod_editor.core import nfl2k5_scorebug_ingame as scene
    chunk, body, _ = scene.decode(span)
    info = scene.tx.parse_texture(body, chunk)
    if info.format_code != 11 or info.dimensions != 2 or info.mip_levels != 1:
        raise ValueError('Reference model requires the captured one-level P8 texture')
    w,h = info.width,info.height
    if w & (w-1) or h & (h-1):
        raise ValueError('P8 swizzle dimensions must be powers of two')
    yy,xx = np.indices((h,w), dtype=np.uint32)
    offsets = np.zeros((h,w), dtype=np.uint32)
    bit = 1
    target = 1
    while bit < max(w,h):
        for size,coords in ((w,xx),(h,yy)):
            if bit < size:
                offsets |= ((coords & bit) != 0).astype(np.uint32)*target
                target <<= 1
        bit <<= 1
    video = memoryview(body)[chunk.system_bytes:]
    indices = np.frombuffer(video[info.pixel_offset:info.pixel_offset+w*h], dtype=np.uint8)[offsets]
    bgra = np.frombuffer(video[info.palette_offset:info.palette_offset+1024],dtype=np.uint8).reshape(256,4)
    pixels = bgra[indices][:,:,[2,1,0,3]]
    return Image.fromarray(pixels,'RGBA'),dict(name=info.name,dimensions=[w,h],
        span_sha256=hashlib.sha256(span).hexdigest(),decode='xemu P8, Morton swizzle, BGRA palette')


class Pipeline:
    """Compile the observed shader to its equivalent per-fragment expression."""
    def __init__(self, trace):
        self.rows = {r['name']:r for r in trace['rows']}
        self.assumptions = list(trace['fixture_assumptions'])
        self.assumptions += ['Preceding logic-op, depth-test enable, depth surface, shade mode and scissor state not captured',
                             'Pixel centres and CPU-projected geometry; surface_scale=4 coverage not emulated']
        self.state = None

    def select(self, name):
        row = self.rows[name]
        state = row['state']
        expected = {0x0300:1,0x0304:1,0x033c:0x206,0x0340:2,
                    0x0344:0x302,0x0348:0x303,0x0350:0x8006,0x0358:0x01010101,
                    0x1b0c:0x4003ffc0,0x1b14:0x02062000,0x1e70:1,
                    0x176c:0xa40,0x1778:0xa21}
        for key,value in expected.items():
            if state.get(f'0x{key:04x}') != value:
                raise ValueError(f'Unsupported captured HUD state {key:#x}')
        fmt = state['0x1b04']
        self.address = tuple(state['0x1b08'] >> shift & 15 for shift in (0,8))
        if any(mode not in (1,3) for mode in self.address):
            raise ValueError('Unsupported texture address mode')
        if (fmt & 0xffff) != 0x0b29 or (fmt >> 16 & 15) != 1 or fmt >> 28:
            raise ValueError('Unsupported texture format/LOD')
        program = row['vertex_program']
        if hashlib.sha256(struct.pack('<'+'I'*len(program),*program)).hexdigest() != 'd2f8707d23d3e86d3d0f0e8d097292495c6701df9f51e3dc037dbae7d2d63867':
            raise ValueError('Unsupported native vertex program')
        # The captured oD0 write is MUL oD0, v3, c6, with identity swizzles.
        colour = [program[i:i+4] for i in range(0,len(program),4)
                  if (program[i+3] >> 11 & 1) and (program[i+3] >> 3 & 255) == 3
                  and (program[i+3] >> 12 & 15)]
        if colour != [[0,0x0040c61b,0x3836d800,0x20b0f818]]:
            raise ValueError('Unsupported native vertex colour program')
        constants = row['vertex_constants']
        self.multiplier = tuple(struct.unpack('<f',struct.pack('<I',constants[str(i)]))[0] for i in range(24,28))
        self.uv_transform = tuple(struct.unpack('<f',struct.pack('<I',constants[str(i)]))[0] for i in range(28,32))
        # Validate the stage program through the literal interpreter before
        # using the algebraically reduced hot path. No luminance fitting.
        combiner(state,(1,1,1,1),self.multiplier)
        if state['0x1e20'] >> 24:
            raise ValueError('Final C0 alpha requires the missing live fog inputs')
        self.state = state

    def vertex_uv(self, packed):
        # VSH MAD oT0.xy,v6.xy,c7.xy,c7.zw; MOV oT0.zw,v6.zw.
        # The two-component S1 array supplies default z=0,w=1, so PROJECT2D
        # divides by one. Use uploaded c7, not an assumed atlas transform.
        return tuple(v/(32768 if v < 0 else 32767)*self.uv_transform[k]+self.uv_transform[k+2]
                     for k,v in enumerate(packed))

    def texel(self, pixels, x, y, width, height):
        x = x % width if self.address[0] == 1 else min(width-1,max(0,x))
        y = y % height if self.address[1] == 1 else min(height-1,max(0,y))
        return pixels[x,y]

    def fragment(self, sample, colour, destination):
        # VSH v3*c6, stage AB*2, final pass-through when final C0.a == 0.
        source = [min(255,max(0,sample[k]*colour[k]/255*self.multiplier[k]*2)) for k in range(4)]
        if source[3] < 2:  # NV097 alpha GEQUAL reference 2
            return None
        a = source[3]/255
        return tuple(round(source[k]*a+destination[k]*(1-a)) for k in range(4))

    def receipt(self):
        return dict(model='xemu f9b1403 observed HUD fragment path',
                    gpu_state_proved=False,calibration_passed=False,
                    assumptions=self.assumptions,
                    equation='P8 fetch; oD0=v3*c6; R0=clamp(2*T0*oD0); final C0.a=0 passes R0; alpha>=2; SRC_ALPHA/ONE_MINUS_SRC_ALPHA ADD',
                    reason='Bounded native state does not reproduce the dark screenshots; no cause-specific fix proved.')
