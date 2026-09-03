"""Hor+ widescreen for NFL 2K5's ``default.xbe`` (executable patch, xemu-only) - v2, activation hook.

Retail geometry (VAs, image base 0x10000).  The frame is 720x480 (every video-mode candidate in
``FUN_000292e0``); every full-screen camera keeps a 640x448-unit rect on the 640x448-pixel target
inset by (40, 16) (``FUN_00066670``).  A camera object is 0x2B0 bytes: +0x00 projection matrix,
+0x40 view matrix, +0xF0 composite (= view x projection, ``FUN_00031110``), +0x200 packed clip rect
(``(x1-1) << 16 | x0`` from the target, ``FUN_0002a6e0``), +0x220 perspective flag, +0x230 rect
(x0 y0 z0 - x1 y1 z1), +0x250 target (pixels), +0x270 ``s`` = horizontal projection scale,
+0x274/+0x278 = (cos, sin) of the horizontal frustum half-angle, +0x27C/+0x280 the vertical pair.
Projections are hand-rolled straight into screen space (``FUN_0002b1e0`` perspective: m00 = TW/2*s,
m11 = -(W/2*s)*TH/H, m20 = -(TW/2+tx0); ``FUN_0002a850`` ortho: m00 = TW/W, m30 = tx0-x0*m00) and
rebuilt from those fields by ``FUN_0002b510`` after every rect / target / view / ``s`` change.

The one fact v2 is built on: **nothing renders from a camera object**.  ``FUN_0002ac80`` (activate)
memcpys the object into the single active camera at 0xA6AFC0 (pointer 0xA6AFB4, the only readers
are the render-list stamp in FUN_0002ac80, the copy constructor FUN_0002ad80 and the getter
FUN_0002adb0) and the GPU, the clip rect and the frustum cull (``FUN_0002adc0`` on FUN_0002adb0's
result at 0xF998B / 0x28B7FE) all consume that copy.  So the whole widescreen treatment is a hook
in FUN_0002ac80: after the copy, rebuild the copy's matrices from its own (retail) fields with
FUN_0002b510, then classify the copy and transform its outputs only:

* **hor+** (perspective camera on a full-screen target: 0..720 raw or the 40..680 inset): m00 and
  the composite's x column shrink by 1/F (F = display aspect / (720/480) = 32/27 for 16:9), the
  horizontal frustum pair is recomputed for s/F; the vertical FOV, the principal point and the clip
  rect are untouched.  The display stretches every pixel by F, so the world shows F times more
  horizontal FOV at unchanged proportions - gameplay, replay, cutscenes, the studio.
* **pillarbox** (any ortho camera with a non-unit rect on an inset target, any perspective camera on
  a sub-window inside 40..680, and the play-diagram camera 0xBD7030 by address): the output x is
  mapped px -> 360 + (px - 360)/F: m00 /= F, the principal point (m20) or ortho offset (m30) moves,
  the composite x column is recomputed, and the packed clip rect shrinks to the same window.  2D art
  keeps its retail proportions centred inside a 4:3 window (90..630 of 720), elements parked past
  x = +-320 are clipped again, sub-window scenes (play art strips, formation view, previews) keep
  their retail framing inside the pillarbox.
* **untouched**: unit-rect cameras (the full-frame fade quads of FUN_00057ce0 / FUN_00011a80 on
  0xB28730 and 0xAF9300 - 0xAF9300 by address), raw 720-wide ortho targets, and anything whose
  target is not inside the frame (render-to-texture: 0..W textures, shadow maps).

Because camera objects stay byte-for-byte retail, every helper that reads a camera object
(FOV/LOD reports, the diagram's icon billboards, anything projecting player positions through a
slot camera) keeps retail numbers - which is exactly what a 2D overlay drawn through the pillarboxed
HUD camera needs to land on a player rendered hor+ (retail px - 360 = (true px - 360) * F).
Copies made from the active camera (FUN_0002ad80) carry transformed matrices, but the hook always
rebuilds from fields first, so re-activating a saved copy is idempotent.

Sites (three): the code cave in ``FUN_00046ee0`` (dead debug draw routine: zero references by
Ghidra xref scan and no imm32 in the image, 0x53E bytes; the cave uses its first 0x340), the nine-float constant block at the head
of the certificate's AlternateSignatureKeys (0x10254, the block the v1 cave executed from in game;
the throw-tuning lob table owns its tail from 0x10310), and the 5-byte ``call FUN_00028110`` at
0x2ACA1 inside FUN_0002ac80 redirected into the cave (which tail-jumps to FUN_00028110 so its
return value still flows back).  Section digests are repinned.
"""

from __future__ import annotations

import math
import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
FRAMEBUFFER_ASPECT = 720.0 / 480.0          # the retail back buffer (all NTSC mode candidates)
ASPECTS: dict[str, float] = {"16:9": 16.0 / 9.0, "16:10": 16.0 / 10.0}
DEFAULT_ASPECT = "16:9"
ACTIVE_WIDTH = 640.0                        # the 640x448 active-area rect every full-screen camera uses
FRAME_WIDTH = 720.0
FRAME_CENTRE_X = 360.0
INSET_X0 = 40.0
INSET_X1 = 680.0
UNIT_RECT_MAX = 2.0                         # |x1-x0| <= 2 -> a +-1 overlay camera (fades)
CAMERA_SIZE = 0x2B0

# --- runtime objects -----------------------------------------------------------------------------
ACTIVE_CAMERA_VA = 0x00A6AFC0               # FUN_0002ac80 copies the activated camera here
DIAGRAM_CAMERA_VA = 0x00BD7030              # play-call diagram camera (FUN_00144360 / FUN_00144ba0)
FADE_TINT_CAMERA_VA = 0x00AF9300            # FUN_00011a80's full-target colour quad camera
REBUILD_VA = 0x0002B510                     # FUN_0002b510: rebuild matrices + clip rect from fields
RENDER_LIST_VA = 0x00028110                 # FUN_00028110: what the hooked call site called
STAMP_OFFSET = 0x24C                        # rect row-2 pad: written by the two constructors, read by nothing
STAMP_DIAGRAM = 0x47414944                  # 'DIAG' - the copy came from 0xBD7030 (or a copy of that copy)
STAMP_NONE = 0x454E4F4E                     # 'NONE' - the copy came from 0xAF9300 (or a copy of that copy)

# --- constants: certificate AlternateSignatureKeys head (kernel-only at launch) ------------------
CAVE_VA = 0x00010254
CAVE_END_VA = 0x00010354
RETAIL_ALT_KEYS = bytes.fromhex(
    "d480d5adc860f3b4d900c8a169acd59084b4fffb5cb4667c8d81d5e22364026681fac9ad696b7b6e36b83667"
    "a0d263910e0c0ec63f59fce1d07c7658f0349fba68f2f71d82bbc9321fb19656a849cb90cf9095ac1883f8e2"
    "c43a2574de06da46d707f1068ccd17381d4aa4913fccb046d12935f01b2f96624a2a4421f00caaf37387b302"
    "a3639f6c9beec92dcb45b9b1a0c645f9c837ebbfbaff5d1f666cbc68f4bdbd28814621104769db5ebd69dde7"
    "693cd6a0ab7538e88a596dddc09cbb6a33852f02452921d764c3eded0c779b160e924109bea4df8c738d157c"
    "7f7ee92d71ec2122d72bc761cb35a365b87f6eda0d2028c6db35afce174764ef0cb25c7c")
assert len(RETAIL_ALT_KEYS) == CAVE_END_VA - CAVE_VA
STRETCH_VA = CAVE_VA            # F
INV_STRETCH_VA = CAVE_VA + 4    # 1/F
SHIFT_VA = CAVE_VA + 8          # K = 360 * (1 - 1/F)
X0_VA = CAVE_VA + 12            # 40.0
X1_VA = CAVE_VA + 16            # 680.0
FRAME_VA = CAVE_VA + 20         # 720.0
UNIT_VA = CAVE_VA + 24          # 2.0
CENTRE_VA = CAVE_VA + 28        # 360.0
ONE_VA = CAVE_VA + 32           # 1.0
DATA_SIZE = 36

# --- code cave: FUN_00046ee0 (dead) -------------------------------------------------------------
CODE_VA = 0x00046EE0
CODE_CAVE_SIZE = 0x340
RETAIL_CODE_CAVE = bytes.fromhex(
    "558bec83e4f083ec7c663d200056750c8b078b400c5e8be55dc20c008b17e8fdf2ffff8bf085f675075e8be5"
    "5dc20c008b451085c074608b4e108b550c528bc150894c2424e886a1fdffd946208b4d08d866102bc8894d08"
    "8b4d0cd95c241c8b54241c5152e866a1fdff8b4d082bc8894c24188b0fe8362400008b5424188944241cdb44"
    "241cd86d0cd84614d95d0cd94634d8450ceb478b46108b4d0c518bd05289442424e826a1fdffd94620d86610"
    "8b550803d08b450cd95c241c8b4c241c5051895508e806a1fdffd9450cd866148bd0035508d95d0cd94634d8"
    "6d0c8d44241cd86614508d4c241c518b4d08d95c2414e8b9fdffff8d442414508d4c2414518bcae8a8fdffff"
    "d9442418d84d0c8b53088bca8bc2d803894c24688b0fd95c2440d944241c89542448d84d0c89442458895424"
    "78d86b04d95c2444d9442410d84d0cd803d95c2450d9442414d84d0cd86b04d95c2454d944240cd84c2410d8"
    "03d95c2460d944240cd84c2414d86b04d95c2464d944240cd84c2418d803d95c2470d944240cd84c241cd86b"
    "04d95c2474e85a2300008b4f6051506a0633d233c9e81a62feff8b4728480f843f010000480f8570020000d9"
    "47508b4f40d84710d95c2430d94714d84754d95c2434d94718d84758d95c2438d9471cd8475cd95c243ce819"
    "5bfeff8b56548b46505250e8bc5afeffd9442430d846108d4c2420d95c2420d94614d8442434d95c2424d946"
    "18d8442438d95c2428d9461cd844243cd95c242ce86759feff8b4e548b56585152e87a5afeffd9442430d846"
    "208d4c2420d95c2420d94624d8442434d95c2424d94628d8442438d95c2428d9462cd844243cd95c242ce825"
    "59feff8b465c8b4e505051e8385afeffd94424308d4c2420d84630d95c2420d94634d8442434d95c2424d946"
    "38d8442438d95c2428d9463cd844243cd95c242ce8e358feff8b565c8b46585250e8f659feffd9442430d846"
    "408d4c2420d95c2420d94644d8442434d95c2424d94648d8442438d95c2428d9464cd844243cd95c242ce8a1"
    "58feffd947108b4f2cd84730d95c2430d94734d84714d95c2434d94738d84718d95c2438d9473cd8471cd95c"
    "243ce8e159feff8b4e548b56505152e88459feffd9442430d846108d4c2420d95c2420d94614d844")
assert len(RETAIL_CODE_CAVE) == CODE_CAVE_SIZE

# --- hook: the call FUN_00028110 inside FUN_0002ac80 (after the memcpy to 0xA6AFC0) ---------------
HOOK_VA = 0x0002ACA1
RETAIL_HOOK = bytes.fromhex("e86ad4ffff")            # call 0x28110


class WidescreenPatchError(ValueError):
    """The widescreen patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WidescreenPatchError(message)


def stretch(aspect: str = DEFAULT_ASPECT) -> float:
    """Horizontal pixel stretch the display applies: display aspect / framebuffer aspect."""

    _require(aspect in ASPECTS, f"unknown display aspect {aspect!r} (known: {sorted(ASPECTS)})")
    return ASPECTS[aspect] / FRAMEBUFFER_ASPECT


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _f32_round(value: float) -> float:
    return struct.unpack("<f", _f32(value))[0]


def constants(aspect: str = DEFAULT_ASPECT) -> dict[str, float]:
    factor = stretch(aspect)
    inv = 1.0 / factor
    return {"stretch": factor, "inv_stretch": inv, "shift": FRAME_CENTRE_X * (1.0 - inv), "x0": INSET_X0,
            "x1": INSET_X1, "frame": FRAME_WIDTH, "unit": UNIT_RECT_MAX, "centre": FRAME_CENTRE_X, "one": 1.0}


def cave_bytes(aspect: str = DEFAULT_ASPECT) -> bytes:
    """The nine-float constant block written at the head of the certificate key block."""

    c = constants(aspect)
    return b"".join(_f32(c[k]) for k in ("stretch", "inv_stretch", "shift", "x0", "x1", "frame", "unit", "centre", "one"))


# --- a tiny x86 emitter (only the forms the cave needs) ------------------------------------------

class _Asm:
    def __init__(self, base: int) -> None:
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, int]] = []   # (offset of rel32, label, size)

    @property
    def here(self) -> int:
        return self.base + len(self.code)

    def label(self, name: str) -> None:
        self.labels[name] = self.here

    def emit(self, *chunks: bytes) -> None:
        for chunk in chunks:
            self.code += chunk

    def jmp(self, label: str) -> None:
        self.code += b"\xe9"
        self.fixups.append((len(self.code), label, 4))
        self.code += b"\0\0\0\0"

    def jcc(self, cc: int, label: str) -> None:               # cc: 0x84 jz/je, 0x85 jnz/jne
        self.code += bytes([0x0F, cc])
        self.fixups.append((len(self.code), label, 4))
        self.code += b"\0\0\0\0"

    def call(self, target_va: int) -> None:
        self.code += b"\xe8" + struct.pack("<i", target_va - (self.here + 5))

    def jmp_abs(self, target_va: int) -> None:
        self.code += b"\xe9" + struct.pack("<i", target_va - (self.here + 5))

    def finish(self) -> bytes:
        for off, label, size in self.fixups:
            target = self.labels[label]
            rel = target - (self.base + off + size)
            self.code[off: off + size] = struct.pack("<i", rel)
        return bytes(self.code)


def _ecx(op: bytes, disp: int) -> bytes:
    """x87 / mov forms with an [ecx+disp32] operand (modrm 0x81/0x91/0x99/0xA1/0xB1...)."""
    return op + struct.pack("<i", disp)


def _abs(op: bytes, va: int) -> bytes:
    return op + struct.pack("<I", va)


# x87 opcode fragments
FLD_ECX = b"\xd9\x81"        # fld dword [ecx+d32]
FST_ECX = b"\xd9\x91"        # fst dword [ecx+d32]
FSTP_ECX = b"\xd9\x99"       # fstp dword [ecx+d32]
FADD_ECX = b"\xd8\x81"       # fadd dword [ecx+d32]
FMUL_ECX = b"\xd8\x89"       # fmul dword [ecx+d32]
FSUB_ECX = b"\xd8\xa1"       # fsub dword [ecx+d32]
FDIV_ECX = b"\xd8\xb1"       # fdiv dword [ecx+d32]
FLD_ABS = b"\xd9\x05"        # fld dword [abs]
FADD_ABS = b"\xd8\x05"       # fadd dword [abs]
FMUL_ABS = b"\xd8\x0d"       # fmul dword [abs]
FSUB_ABS = b"\xd8\x25"       # fsub dword [abs]
FCOMP_ABS = b"\xd8\x1d"      # fcomp dword [abs]
FNSTSW_AX = b"\xdf\xe0"
FABS = b"\xd9\xe1"
FSQRT = b"\xd9\xfa"
FLD1 = b"\xd9\xe8"
FLD_ST0 = b"\xd9\xc0"
FMUL_ST0_ST0 = b"\xd8\xc8"
FADDP = b"\xde\xc1"          # faddp st(1),st(0)
FMULP = b"\xde\xc9"          # fmulp st(1),st(0)
FDIVRP = b"\xde\xf1"         # st(1) = st(0)/st(1), pop  (verified numerically by the emulation test)
FSTP_ST0 = b"\xdd\xd8"


def code_bytes(aspect: str = DEFAULT_ASPECT, labels: dict[str, int] | None = None) -> bytes:
    """The activation-hook cave (entered by ``call`` from 0x2ACA1; ecx = camera - 0xA6AFC0).

    The code reads every aspect-dependent number from the constant block, so it is the same for
    every aspect; ``labels`` (optional) receives the cave's label addresses.
    """

    del aspect
    a = _Asm(CODE_VA)
    A = ACTIVE_CAMERA_VA
    # prologue: keep the source camera address on the stack, 16 bytes of scratch below it
    a.emit(_ecx(b"\x8d\x91", A))                      # lea edx,[ecx+0xA6AFC0]   (source camera)
    a.emit(b"\x52")                                   # push edx
    a.emit(b"\x83\xec\x10")                           # sub esp,16               [esp+16] = source
    a.emit(_abs(b"\xb9", A))                          # mov ecx,0xA6AFC0
    a.call(REBUILD_VA)                                # FUN_0002b510: matrices/clip from retail fields
    a.emit(_abs(b"\xb9", A))                          # mov ecx,0xA6AFC0
    # ---- classification flags in dl: 1 tx0<=40, 2 tx1>=680, 4 tx1<=720, 8 tx0>=40, 16 tx1<=680
    a.emit(b"\x33\xd2")                               # xor edx,edx
    a.emit(_ecx(FLD_ECX, 0x250), _abs(FCOMP_ABS, X0_VA), FNSTSW_AX)
    a.emit(b"\xf6\xc4\x41", b"\x74\x03", b"\x80\xca\x01")       # test ah,0x41 ; jz +3 ; or dl,1
    a.emit(b"\xf6\xc4\x01", b"\x75\x03", b"\x80\xca\x08")       # test ah,0x01 ; jnz +3 ; or dl,8
    a.emit(_ecx(FLD_ECX, 0x260), _abs(FCOMP_ABS, X1_VA), FNSTSW_AX)
    a.emit(b"\xf6\xc4\x01", b"\x75\x03", b"\x80\xca\x02")       # test ah,0x01 ; jnz +3 ; or dl,2
    a.emit(b"\xf6\xc4\x41", b"\x74\x03", b"\x80\xca\x10")       # test ah,0x41 ; jz +3 ; or dl,16
    a.emit(_ecx(FLD_ECX, 0x260), _abs(FCOMP_ABS, FRAME_VA), FNSTSW_AX)
    a.emit(b"\xf6\xc4\x41", b"\x74\x03", b"\x80\xca\x04")       # test ah,0x41 ; jz +3 ; or dl,4
    # ---- by address (or by the stamp a previous activation left in the copy's rect pad) first
    a.emit(_ecx(b"\x81\xb9", STAMP_OFFSET) + struct.pack("<I", STAMP_NONE))   # cmp dword [ecx+0x24C],'NONE'
    a.jcc(0x84, "done")
    a.emit(_ecx(b"\x81\xb9", STAMP_OFFSET) + struct.pack("<I", STAMP_DIAGRAM))
    a.jcc(0x84, "pillarbox")
    a.emit(_abs(b"\x81\x7c\x24\x10", FADE_TINT_CAMERA_VA))      # cmp dword [esp+16],0xAF9300
    a.jcc(0x85, "not_fade")
    a.emit(_ecx(b"\xc7\x81", STAMP_OFFSET) + struct.pack("<I", STAMP_NONE))   # mov dword [ecx+0x24C],'NONE'
    a.jmp("done")
    a.label("not_fade")
    a.emit(_abs(b"\x81\x7c\x24\x10", DIAGRAM_CAMERA_VA))        # cmp dword [esp+16],0xBD7030
    a.jcc(0x85, "not_diagram")
    a.emit(_ecx(b"\xc7\x81", STAMP_OFFSET) + struct.pack("<I", STAMP_DIAGRAM))
    a.jmp("pillarbox")
    a.label("not_diagram")
    a.emit(_ecx(b"\x8b\x81", 0x220), b"\x85\xc0")               # mov eax,[ecx+0x220] ; test eax,eax
    a.jcc(0x84, "ortho")
    # perspective: full-screen -> hor+, sub-window -> pillarbox, else nothing
    a.emit(b"\x8a\xc2", b"\x24\x07", b"\x3c\x07")               # mov al,dl ; and al,7 ; cmp al,7
    a.jcc(0x84, "horplus")
    a.emit(b"\x8a\xc2", b"\x24\x18", b"\x3c\x18")               # mov al,dl ; and al,0x18 ; cmp al,0x18
    a.jcc(0x84, "pillarbox")
    a.jmp("done")
    a.label("ortho")
    a.emit(_ecx(FLD_ECX, 0x240), _ecx(FSUB_ECX, 0x230), FABS, _abs(FCOMP_ABS, UNIT_VA), FNSTSW_AX)
    a.emit(b"\xf6\xc4\x41")                                     # test ah,0x41   (width <= 2 -> unit rect)
    a.jcc(0x85, "done")
    a.emit(b"\x8a\xc2", b"\x24\x18", b"\x3c\x18")               # within the inset frame?
    a.jcc(0x85, "done")
    # ---- pillarbox: m00 /= F ; m20 = m20/F - K (perspective) | m30 = m30/F + K (ortho) ; clip rect
    a.label("pillarbox")
    a.emit(_ecx(FLD_ECX, 0x00), _abs(FMUL_ABS, INV_STRETCH_VA), _ecx(FSTP_ECX, 0x00))
    a.emit(_ecx(b"\x8b\x81", 0x220), b"\x85\xc0")
    a.jcc(0x84, "pb_ortho")
    a.emit(_ecx(FLD_ECX, 0x20), _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FSUB_ABS, SHIFT_VA), _ecx(FSTP_ECX, 0x20))
    a.jmp("pb_clip")
    a.label("pb_ortho")
    a.emit(_ecx(FLD_ECX, 0x30), _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FADD_ABS, SHIFT_VA), _ecx(FSTP_ECX, 0x30))
    a.label("pb_clip")
    # packed clip rect +0x200: a = low16, b = high16 + 1 ; a' = 360 + (a-360)/F ; b' likewise
    a.emit(_ecx(b"\x0f\xb7\x81", 0x200), b"\x89\x04\x24")       # movzx eax,word [ecx+0x200] ; mov [esp],eax
    a.emit(b"\xdb\x04\x24", _abs(FSUB_ABS, CENTRE_VA), _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FADD_ABS, CENTRE_VA),
           b"\xdb\x1c\x24")                                     # fild [esp] ; ... ; fistp [esp]
    a.emit(_ecx(b"\x0f\xb7\x91", 0x202), b"\x42", b"\x89\x54\x24\x04")   # movzx edx,word [ecx+0x202] ; inc edx ; mov [esp+4],edx
    a.emit(b"\xdb\x44\x24\x04", _abs(FSUB_ABS, CENTRE_VA), _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FADD_ABS, CENTRE_VA),
           b"\xdb\x5c\x24\x04")                                 # fild [esp+4] ; ... ; fistp [esp+4]
    a.emit(b"\x8b\x54\x24\x04", b"\x4a", b"\xc1\xe2\x10")       # mov edx,[esp+4] ; dec edx ; shl edx,16
    a.emit(b"\x8b\x04\x24", b"\x25\xff\xff\x00\x00", b"\x0b\xc2", _ecx(b"\x89\x81", 0x200))   # mov eax,[esp] ; and eax,0xffff ; or eax,edx ; mov [ecx+0x200],eax
    a.jmp("composite")
    # ---- hor+: m00 /= F ; horizontal frustum pair for s/F
    a.label("horplus")
    a.emit(_ecx(FLD_ECX, 0x00), _abs(FMUL_ABS, INV_STRETCH_VA), _ecx(FSTP_ECX, 0x00))
    a.emit(_abs(FLD_ABS, STRETCH_VA), _ecx(FDIV_ECX, 0x270))    # t = F / s                        (t)
    a.emit(FLD_ST0, FMUL_ST0_ST0, _abs(FADD_ABS, ONE_VA), FSQRT)   # sqrt(1 + t*t)                 (r, t)
    a.emit(FLD1, FDIVRP)                                        # c = 1 / r                        (c, t)
    a.emit(_ecx(FST_ECX, 0x274), FMULP, _ecx(FSTP_ECX, 0x278))  # cos ; sin = t * c
    # ---- composite x column: C[i][0] = sum_k View[i][k] * Proj[k][0]  (rows i = 0..3)
    a.label("composite")
    for row in range(4):
        v = 0x40 + row * 16
        a.emit(_ecx(FLD_ECX, v + 0), _ecx(FMUL_ECX, 0x00))
        a.emit(_ecx(FLD_ECX, v + 4), _ecx(FMUL_ECX, 0x10), FADDP)
        a.emit(_ecx(FLD_ECX, v + 8), _ecx(FMUL_ECX, 0x20), FADDP)
        a.emit(_ecx(FLD_ECX, v + 12), _ecx(FMUL_ECX, 0x30), FADDP)
        a.emit(_ecx(FSTP_ECX, 0xF0 + row * 16))
    a.label("done")
    a.emit(b"\x83\xc4\x14")                                     # add esp,20  (scratch + saved source)
    a.jmp_abs(RENDER_LIST_VA)                                   # tail call: FUN_00028110's eax returns to 0x2ACA6
    blob = a.finish()
    if labels is not None:
        labels.update(a.labels)
        labels["entry"] = CODE_VA
        labels["end"] = CODE_VA + len(blob)
    _require(len(blob) <= CODE_CAVE_SIZE, f"widescreen cave is {len(blob)} bytes, over {CODE_CAVE_SIZE}")
    return blob + b"\xcc" * (CODE_CAVE_SIZE - len(blob))


PATCHED_HOOK = b"\xe8" + struct.pack("<i", CODE_VA - (HOOK_VA + 5))


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise WidescreenPatchError(f"VA 0x{va:x} is in no file-backed section")


def _sites(payload: bytes, aspect: str) -> list[tuple[str, int, bytes, bytes]]:
    """(label, file offset, retail bytes, patched bytes) for every site."""

    data = cave_bytes(aspect)
    return [
        ("constants", _offset(payload, CAVE_VA), RETAIL_ALT_KEYS[: len(data)], data),
        ("code_cave", _offset(payload, CODE_VA), RETAIL_CODE_CAVE, code_bytes(aspect)),
        ("hook", _offset(payload, HOOK_VA), RETAIL_HOOK, PATCHED_HOOK),
    ]


def _site_state(payload: bytes, sites: list[tuple[str, int, bytes, bytes]]) -> str:
    states = set()
    for _label, off, before, after in sites:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def status(payload: bytes, aspect: str | None = None) -> str:
    """'retail', 'applied' (for ``aspect``, or any known aspect when None), or 'foreign'."""

    aspects = [aspect] if aspect is not None else list(ASPECTS)
    try:
        first = _site_state(payload, _sites(payload, aspects[0]))
        if first != "foreign":
            return first
        for other in aspects[1:]:
            if _site_state(payload, _sites(payload, other)) == "applied":
                return "applied"
    except (WidescreenPatchError, ValueError, struct.error, IndexError):
        return "foreign"
    return "foreign"


def applied_aspect(payload: bytes) -> str | None:
    """Which display aspect the payload carries, or None (retail / foreign)."""

    for aspect in ASPECTS:
        try:
            if _site_state(payload, _sites(payload, aspect)) == "applied":
                return aspect
        except (WidescreenPatchError, ValueError, struct.error, IndexError):
            return None
    return None


def read_sites(payload: bytes) -> dict[str, object]:
    """The live values at every site, for inspection."""

    data = payload[_offset(payload, CAVE_VA):][:DATA_SIZE]
    return {
        "constants": [struct.unpack_from("<f", data, i)[0] for i in range(0, DATA_SIZE, 4)],
        "hook": payload[_offset(payload, HOOK_VA):][:5].hex(),
        "code_head": payload[_offset(payload, CODE_VA):][:16].hex(),
    }


# --- the transform, in Python, for tests and the report ----------------------------------------

def classify(perspective: bool, rect_width: float, tx0: float, tx1: float, source_va: int = 0,
             stamp: int = 0) -> str:
    """What the cave does to an activated camera: 'horplus', 'pillarbox' or 'none'."""

    if stamp == STAMP_NONE or source_va == FADE_TINT_CAMERA_VA:
        return "none"
    if stamp == STAMP_DIAGRAM or source_va == DIAGRAM_CAMERA_VA:
        return "pillarbox"
    full = tx0 <= INSET_X0 and tx1 >= INSET_X1 and tx1 <= FRAME_WIDTH
    within = tx0 >= INSET_X0 and tx1 <= INSET_X1
    if perspective:
        if full:
            return "horplus"
        return "pillarbox" if within else "none"
    if abs(rect_width) <= UNIT_RECT_MAX:
        return "none"
    return "pillarbox" if within else "none"


def pillarbox_x(px: float, aspect: str = DEFAULT_ASPECT) -> float:
    """Frame pixel x -> the pillarboxed pixel the display stretches back to its retail place."""

    inv = 1.0 / stretch(aspect)
    return FRAME_CENTRE_X + (px - FRAME_CENTRE_X) * inv


def pillarbox_clip(x0: int, x1: int, aspect: str = DEFAULT_ASPECT) -> tuple[int, int]:
    """The cave's integer clip transform on a packed (x0, x1) pair (x1 exclusive, as FUN_0002a6e0 stores it)."""

    inv = 1.0 / _f32_round(stretch(aspect))
    inv = _f32_round(inv)
    a = int(round(FRAME_CENTRE_X + (x0 - FRAME_CENTRE_X) * inv))
    b = int(round(FRAME_CENTRE_X + (x1 - FRAME_CENTRE_X) * inv))
    return a, b


def geometry(aspect: str = DEFAULT_ASPECT, lens: float = 35.0) -> dict[str, float]:
    """What the patch does to a gameplay camera with the given lens word (Standard = 35)."""

    factor = stretch(aspect)
    s_retail = lens / 18.0
    s_wide = s_retail / factor
    return {
        "stretch": factor,
        "hud_pixel_scale": 1.0 / factor,
        "hud_window": (pillarbox_x(INSET_X0, aspect), pillarbox_x(INSET_X1, aspect)),
        "hfov_retail_deg": 2.0 * math.degrees(math.atan(1.0 / s_retail)),
        "hfov_wide_deg": 2.0 * math.degrees(math.atan(1.0 / s_wide)),
        "vfov_deg": 2.0 * math.degrees(math.atan((448.0 / ACTIVE_WIDTH) / s_retail)),
    }


def apply(payload: bytes, aspect: str = DEFAULT_ASPECT) -> tuple[bytes, Mapping[str, object]]:
    """Apply the hor+ patch for ``aspect``; refuses anything that is not byte-for-byte retail."""

    sites = _sites(payload, aspect)
    state = _site_state(payload, sites)
    _require(state == "retail", f"widescreen sites are {state}, not retail")
    header = _header_size(payload)
    sections = _sections(payload)
    buf = bytearray(payload)
    edits = []
    touched: set[int] = set()
    changed = 0
    for label, off, before, after in sites:
        _require(len(before) == len(after), f"{label}: length mismatch")
        buf[off: off + len(after)] = after
        changed += sum(1 for a, b in zip(before, after) if a != b)
        edits.append({"label": label, "offset": f"0x{off:x}", "length": len(after),
                      "before": before.hex() if len(before) <= 64 else f"<{len(before)} retail bytes>",
                      "after": after.hex() if len(after) <= 64 else f"<{len(after)} bytes>"})
        if off >= header:
            touched.add(_section_for_offset(sections, off).index)
    for section in sections:
        if section.index in touched:
            digest_at = section.header_offset + 36
            buf[digest_at: digest_at + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(_site_state(patched, sites) == "applied", "post-write verification failed")
    return patched, {
        "aspect": aspect,
        "stretch": stretch(aspect),
        "edits": edits,
        "changed_bytes": changed,
        "sections_repinned": sorted(touched),
        "status": "applied",
        "code_cave": {"va": f"0x{CODE_VA:x}", "bytes": len(code_bytes(aspect).rstrip(b"\xcc"))},
        "xemu": {"display.ui.aspect_ratio": "16x9" if aspect == "16:9" else aspect.replace(":", "x"),
                 "eeprom_video_flags": "leave 0 (no widescreen/letterbox flag)"},
    }


__all__ = [
    "ASPECTS", "ACTIVE_CAMERA_VA", "CAVE_VA", "CODE_VA", "CODE_CAVE_SIZE", "DEFAULT_ASPECT", "DIAGRAM_CAMERA_VA",
    "FADE_TINT_CAMERA_VA", "HOOK_VA", "STAMP_OFFSET", "STAMP_DIAGRAM", "STAMP_NONE", "PATCHED_HOOK", "RETAIL_ALT_KEYS", "RETAIL_CODE_CAVE", "RETAIL_HOOK",
    "REBUILD_VA", "RENDER_LIST_VA", "WidescreenPatchError", "apply", "applied_aspect", "cave_bytes", "classify",
    "code_bytes", "constants", "geometry", "pillarbox_clip", "pillarbox_x", "read_sites", "status", "stretch",
]
