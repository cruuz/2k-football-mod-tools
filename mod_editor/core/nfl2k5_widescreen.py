"""EXPERIMENTAL / UNWITNESSED hor+ widescreen for the USA NFL 2K5 XBE, v3.

Retail renders a 720x480 frame. FUN_00066670 builds the usual 640x448 target
inset at (40,16). Display stretching is F = display aspect / (720/480), or
32/27 for 16:9. Full-width perspective cameras keep their principal point and
vertical field of view; m00 is divided by F. Ordinary HUDs and subwindows map
x to 360 + (x-360)/F, preserving their apparent proportions on that display.
The regular HUD clip becomes 90..630 at 16:9. This is not a HUD layout mod.

A camera occupies 0x2B0 bytes: projection +0, view +40, composite +F0,
interlaced projection/composite +130/+170, screen plane +1B0, packed GPU clip
+200, perspective flag +220, rect +230, target +250, retail lens s +270,
horizontal frustum normals +274/+278 and bounds +284/+288. FUN_0002AC80 copies
it to the active camera at A6AFC0; the hook at 2ACA1 first calls the native
rebuild (2B510). Saved active copies are therefore safe to activate again.

V3 corrects specific consumers that v2 left inconsistent:
* Rebuild the composite with 31110 and the projection-dependent plane with
  2A9E0. Copy corrected x columns to the second interlaced field under the
  exact native mode/target condition; preserve its distinct y column.
* Recompute full-world horizontal sphere-cull normals for s/F. The shadow
  pass at 1C32FB must use its activated camera, not its rebuilt retail copy.
  Other direct 2ADC0 callers already use active or saved active cameras.
* Five 2AB40 call sites project transformed cameras into a separately
  pillarboxed pixel HUD. Undo only that prior x transform there, retaining
  native y/z/w, reciprocal depth and the calling convention. Original
  diagram/slot cameras still project retail coordinates and need no undo.
* FUN_00066950 marks pixel HUDs derived from widened full-world cameras.
  They keep 4:3 glyph size but retain the full world clip and widened ortho
  cull bounds, so edge indicators and labels are not clipped or clamped.
* The A87B60 full-width sky/tint camera covers the world target. The panorama
  load at 9E1BC uses s/F for horizontal texture angles only; 9E110 still uses
  retail s for vertical angles. Subwindow sky remains pillarboxed.
* A packed pillarbox clip always retains at least one pixel after rounding.

Original source cameras and s remain unchanged: LOD/camera-distance reports
use retail vertical size, not horizontal visibility. Unit-rect fades, AF9300
full-target tint, raw 720-wide non-marker ortho cameras and targets outside
the frame retain retail behavior. Raw ortho art and render targets that
happen to resemble screen subwindows need scene witnesses; do not assume
that every billboard or render-to-texture target follows the world camera.
See ASTRA_WIDESCREEN_POLISH_REPORT.md for the complete audit and open cases.

The existing 832-byte reserved cave at 46EE0 holds code only; its 36-byte
constant block remains at 10254 (AlternateSignatureKeys head). No new cave
or allocator budget is claimed. Runtime tags use the existing camera rect
padding at +24C, including saved copies. Eleven owned sites plus surrounding
ABI pins are validated before mutation. Mixed, older and foreign installs
refuse; exact v3 replay changes nothing. Section digests are repinned.
"""

from __future__ import annotations

import hashlib
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
SKY_CAMERA_VA = 0x00A87B60                  # FUN_0009e1a0 / 9dea0's screen-space sky and tint
SKY_LENS_HOOK_VA = 0x0009E1BC
REBUILD_VA = 0x0002B510                     # FUN_0002b510: rebuild matrices + clip rect from fields
RENDER_LIST_VA = 0x00028110                 # FUN_00028110: what the hooked call site called
STAMP_OFFSET = 0x24C                        # rect row-2 pad: written by the two constructors, read by nothing
STAMP_DIAGRAM = 0x47414944                  # 'DIAG' - the copy came from 0xBD7030 (or a copy of that copy)
STAMP_NONE = 0x454E4F4E                     # 'NONE' - the copy came from 0xAF9300 (or a copy of that copy)
STAMP_WIDE = 0x45444957                     # 'WIDE' - transformed output, including saved active copies
STAMP_PIXELS = STAMP_WIDE ^ 1               # world markers: 4:3 glyphs, full world clip
PROJECT_VA = 0x0002AB40
PLANE_VA = 0x0002A9E0                       # projection-dependent screen-space plane at +0x1B0
PIXEL_CAMERA_HOOK_VA = 0x00066A52
RECT_VA = 0x0002BAD0
POLISH_VERSION = 3
EXPERIMENTAL = True
RUNTIME_WITNESSED = False
HELP_TEXT = (
    "Retail uses a 4:3 picture. Patch: Shows more of the field on a 16:9 display, "
    "keeps the HUD at its existing size, and corrects projected markers, shadow "
    "culling, sky width and both interlaced fields. Set xemu's display aspect to 16x9. "
    "EXPERIMENTAL / UNWITNESSED. Rebuild older widescreen discs from a clean base."
)

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
# Only these consumers feed projected pixels into a separately pillarboxed HUD.
# Other callers use the projected depth or draw world-space billboards directly.
HUD_PROJECT_CALLS = (0x0007EC59, 0x000FA2A1, 0x000FA31E, 0x0032C895, 0x0032C8AC)
SHADOW_CAMERA_VA = 0x001C32FB
RETAIL_SHADOW_CAMERA = bytes.fromhex("8d8c24b4000000")  # lea ecx,[esp+0xB4], rebuilt source
PATCHED_SHADOW_CAMERA = b"\xb9" + struct.pack("<I", ACTIVE_CAMERA_VA) + b"\x90\x90"
# Unchanged instruction context at the hooks and the native ABI used by wrappers.
# These are checked together with ALL owned sites, including on exact replay.
CONTEXT_PINS = (
    (0x2AC80, bytes.fromhex("b8c0afa6002bc8eb07")),
    (0x2AC90, bytes.fromhex("0f2804010f290083c0103d70b2a60072ef")),
    (0x2ACA6, bytes.fromhex("85c074188b0085c07412")),
    (0x2AB40, bytes.fromhex("568b328bc18b4c24088931d94204d95904")),
    (0x2ABB6, bytes.fromhex("d8095ed919d9c0d84904d95904d9c0d84908d80d80604e00d95908c20400")),
    (0x7EC51, bytes.fromhex("8d442450508d5710")),
    (0x7EC5E, bytes.fromhex("d95c2440")),
    (0xFA294, bytes.fromhex("8d4c2430518bd68bc889442420")),
    (0xFA2A6, bytes.fromhex("d95c2414")),
    (0xFA311, bytes.fromhex("8d542430528d542444d95c2448")),
    (0xFA323, bytes.fromhex("8b442430ddd8")),
    (0x32C88A, bytes.fromhex("e821e5cfff8d5424248bc8")),
    (0x32C89A, bytes.fromhex("ddd88d542410")),
    (0x32C8A1, bytes.fromhex("e80ae5cfff8d5424148bc8")),
    (0x32C8B1, bytes.fromhex("ddd88d4c2440")),
    (0x1C32F2, bytes.fromhex("8b4c2410518d542464")),
    (0x1C3302, bytes.fromhex("e8b97ae6ff85c0")),
    (0x6695C, bytes.fromhex("8bf28bd9e8fb52fcff")),
    (0x669D3, bytes.fromhex("81c650020000b9080000008d7c2450f3a5")),
    (0x66A4E, bytes.fromhex("d95c2448")),
    (0x66A57, bytes.fromhex("5f5e5b8be55dc3")),
    (0x9E1AD, bytes.fromhex("8b5d085657b9607ba800e8c4caf8ff")),
    (0x9E1C2, bytes.fromhex("d95c24148b442414")),
)


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

    def jmp_short(self, label: str) -> None:
        self.code += b"\xeb"
        self.fixups.append((len(self.code), label, 1))
        self.code += b"\0"

    def jcc(self, cc: int, label: str) -> None:               # cc: 0x84 jz/je, 0x85 jnz/jne
        self.code += bytes([0x0F, cc])
        self.fixups.append((len(self.code), label, 4))
        self.code += b"\0\0\0\0"

    def jcc_short(self, cc: int, label: str) -> None:
        self.code += bytes([cc - 0x10])
        self.fixups.append((len(self.code), label, 1))
        self.code += b"\0"

    def call(self, target_va: int) -> None:
        self.code += b"\xe8" + struct.pack("<i", target_va - (self.here + 5))

    def jmp_abs(self, target_va: int) -> None:
        self.code += b"\xe9" + struct.pack("<i", target_va - (self.here + 5))

    def finish(self) -> bytes:
        for off, label, size in self.fixups:
            target = self.labels[label]
            rel = target - (self.base + off + size)
            self.code[off: off + size] = struct.pack("<b" if size == 1 else "<i", rel)
        return bytes(self.code)


def _ecx(op: bytes, disp: int) -> bytes:
    """x87 / mov forms with an [ecx+disp32] operand (modrm 0x81/0x91/0x99/0xA1/0xB1...)."""
    if disp == 0:
        return op[:-1] + bytes([op[-1] - 0x80])
    if -128 <= disp <= 127:
        return op[:-1] + bytes([op[-1] - 0x40]) + struct.pack("<b", disp)
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
    a.emit(_ecx(b"\x8b\x81", STAMP_OFFSET))
    a.emit(b"\x3d" + struct.pack("<I", STAMP_NONE))
    a.jcc(0x84, "done")
    a.emit(b"\x3d" + struct.pack("<I", STAMP_DIAGRAM))
    a.jcc(0x84, "pillarbox")
    a.emit(b"\x3d" + struct.pack("<I", STAMP_PIXELS))
    a.jcc(0x84, "pillarbox")
    a.emit(b"\x8b\x44\x24\x10", _abs(b"\x3d", FADE_TINT_CAMERA_VA))
    a.jcc_short(0x84, "exempt")
    a.emit(_abs(b"\x3d", SKY_CAMERA_VA))
    a.jcc_short(0x85, "not_fade")
    a.emit(b"\x8a\xc2", b"\x24\x07", b"\x3c\x07")             # full-width sky only
    a.jcc_short(0x85, "not_fade")
    a.label("exempt")
    a.emit(_ecx(b"\xc7\x81", STAMP_OFFSET) + struct.pack("<I", STAMP_NONE))   # mov dword [ecx+0x24C],'NONE'
    a.jmp("done")
    a.label("not_fade")
    a.emit(_abs(b"\x3d", DIAGRAM_CAMERA_VA))
    a.jcc_short(0x85, "not_diagram")
    a.emit(_ecx(b"\xc7\x81", STAMP_OFFSET) + struct.pack("<I", STAMP_DIAGRAM))
    a.jmp("pillarbox")
    a.label("not_diagram")
    a.emit(_ecx(b"\x83\xb9", 0x220), b"\x00")                  # cmp dword [ecx+0x220],0
    a.jcc_short(0x84, "ortho")
    # perspective: full-screen -> hor+, sub-window -> pillarbox, else nothing
    a.emit(b"\x8a\xc2", b"\x24\x07", b"\x3c\x07")               # mov al,dl ; and al,7 ; cmp al,7
    a.jcc(0x84, "horplus")
    a.emit(b"\x8a\xc2", b"\x24\x18", b"\x3c\x18")               # mov al,dl ; and al,0x18 ; cmp al,0x18
    a.jcc_short(0x84, "pillarbox")
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
    a.emit(_ecx(b"\x83\xb9", 0x220), b"\x00")
    a.jcc_short(0x84, "pb_ortho")
    a.emit(_ecx(FLD_ECX, 0x20), _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FSUB_ABS, SHIFT_VA), _ecx(FSTP_ECX, 0x20))
    a.jmp_short("pb_clip")
    a.label("pb_ortho")
    a.emit(_ecx(FLD_ECX, 0x30), _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FADD_ABS, SHIFT_VA), _ecx(FSTP_ECX, 0x30))
    a.label("pb_clip")
    a.emit(_ecx(b"\x81\xb9", STAMP_OFFSET) + struct.pack("<I", STAMP_PIXELS))
    a.jcc(0x84, "pixel_bounds")
    # packed clip rect +0x200: a = low16, b = high16 + 1 ; a' = 360 + (a-360)/F ; b' likewise
    a.emit(_ecx(b"\x0f\xb7\x81", 0x200), b"\x89\x04\x24")       # movzx eax,word [ecx+0x200] ; mov [esp],eax
    a.emit(b"\xdb\x04\x24", _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FADD_ABS, SHIFT_VA),
           b"\xdb\x1c\x24")                                     # fild [esp] ; ... ; fistp [esp]
    a.emit(_ecx(b"\x0f\xb7\x91", 0x202), b"\x42", b"\x89\x54\x24\x04")   # movzx edx,word [ecx+0x202] ; inc edx ; mov [esp+4],edx
    a.emit(b"\xdb\x44\x24\x04", _abs(FMUL_ABS, INV_STRETCH_VA), _abs(FADD_ABS, SHIFT_VA),
           b"\xdb\x5c\x24\x04")                                 # fild [esp+4] ; ... ; fistp [esp+4]
    # A one-pixel retail interval can round to equal endpoints. Retain one pixel.
    a.emit(b"\x8b\x04\x24", b"\x8b\x54\x24\x04", b"\x3b\xd0", b"\x7f\x03", b"\x8d\x50\x01")
    a.emit(b"\x4a", b"\xc1\xe2\x10")
    a.emit(b"\x8b\x04\x24", b"\x25\xff\xff\x00\x00", b"\x0b\xc2", _ecx(b"\x89\x81", 0x200))   # mov eax,[esp] ; and eax,0xffff ; or eax,edx ; mov [ecx+0x200],eax
    a.jmp_short("composite")
    # ---- hor+: m00 /= F ; horizontal frustum pair for s/F
    a.label("horplus")
    a.emit(_ecx(FLD_ECX, 0x00), _abs(FMUL_ABS, INV_STRETCH_VA), _ecx(FSTP_ECX, 0x00))
    a.emit(_abs(FLD_ABS, STRETCH_VA), _ecx(FDIV_ECX, 0x270))    # t = F / s                        (t)
    a.emit(FLD_ST0, FMUL_ST0_ST0, FLD1, FADDP, FSQRT)            # sqrt(1 + t*t)                 (r, t)
    a.emit(FLD1, FDIVRP)                                        # c = 1 / r                        (c, t)
    a.emit(_ecx(FST_ECX, 0x274), FMULP, _ecx(FSTP_ECX, 0x278))  # cos ; sin = t * c
    # ---- native composite = view x corrected projection
    a.label("composite")
    a.emit(_ecx(b"\x8b\x81", STAMP_OFFSET), b"\x3d" + struct.pack("<I", STAMP_DIAGRAM))
    a.jcc_short(0x84, "marked")
    a.emit(b"\x3d" + struct.pack("<I", STAMP_PIXELS))
    a.jcc_short(0x84, "marked")
    a.emit(_ecx(b"\xc7\x81", STAMP_OFFSET) + struct.pack("<I", STAMP_WIDE))
    a.label("marked")
    a.emit(b"\x51", b"\x8d\x51\x40", b"\x81\xc1\xf0\x00\x00\x00")
    a.call(0x31110)                                            # native view x projection, ret 4
    a.emit(_abs(b"\xb9", A))
    # Retail builds a second field at +130/+170 only for this exact target/mode.
    # Its y column differs; both x columns must match the first field.
    a.emit(_abs(b"\x83\x3d", 0xA6A9CC), b"\x01")
    a.jcc_short(0x85, "plane")
    a.emit(_abs(b"\xa1", 0xA6AA18), _abs(b"\x8b\x15", 0xA6AA58))
    a.emit(_abs(b"\x3b\x14\x85", 0xA6AA20))
    a.jcc_short(0x85, "plane")
    a.emit(b"\x33\xd2")
    a.label("field_row")
    a.emit(b"\x8b\x04\x11", b"\x89\x84\x11\x30\x01\x00\x00")
    a.emit(b"\x8b\x84\x11\xf0\x00\x00\x00", b"\x89\x84\x11\x70\x01\x00\x00")
    a.emit(b"\x83\xc2\x10", b"\x83\xfa\x40")
    a.jcc_short(0x85, "field_row")
    a.label("plane")
    a.emit(b"\x51")                                            # callee pops camera argument
    a.call(PLANE_VA)
    a.label("done")
    a.emit(b"\x83\xc4\x14")                                     # add esp,20  (scratch + saved source)
    a.jmp_abs(RENDER_LIST_VA)                                   # tail call: FUN_00028110's eax returns to 0x2ACA6
    # Call-site wrapper: preserve native 1/w in ST(0), y/z/w and callee-saved regs.
    # The original output argument is consumed by the final ret 4.
    a.label("hud_project")
    a.emit(b"\x51", b"\xff\x74\x24\x08")                     # save source, push original output pointer
    a.call(PROJECT_VA)
    a.emit(b"\x5a")                                            # edx = source, ecx = output (native ABI)
    a.emit(b"\x8b\x82" + struct.pack("<I", STAMP_OFFSET), b"\x0c\x01",
           b"\x3d" + struct.pack("<I", STAMP_WIDE))
    a.jcc_short(0x84, "hud_unmap")
    a.emit(b"\x81\xba" + struct.pack("<II", STAMP_OFFSET, STAMP_DIAGRAM))
    a.jcc_short(0x85, "hud_return")
    a.label("hud_unmap")
    a.emit(b"\xd9\x01", _abs(FSUB_ABS, CENTRE_VA), _abs(FMUL_ABS, STRETCH_VA),
           _abs(FADD_ABS, CENTRE_VA), b"\xd9\x19")
    a.label("hud_return")
    a.emit(b"\xc2\x04\x00")
    # FUN_00066950's final setter: EBX = destination; ESI = source + 270.
    # Only pixel HUDs derived from a widened full-frame perspective camera get
    # the world clip. Diagram windows and ordinary menu/scorebug cameras do not.
    a.label("pixel_camera")
    a.call(RECT_VA)
    a.emit(b"\x81\x7e\xdc" + struct.pack("<I", STAMP_WIDE))
    a.jcc_short(0x85, "pixel_return")
    a.emit(b"\x83\x7e\xb0\x00")                             # source +220 perspective
    a.jcc_short(0x84, "pixel_return")
    a.emit(b"\x8b\x46\x90", b"\x3d" + struct.pack("<I", (679 << 16) | 40))
    a.jcc_short(0x84, "pixel_mark")
    a.emit(b"\x3d" + struct.pack("<I", 719 << 16))
    a.jcc_short(0x85, "pixel_return")
    a.label("pixel_mark")
    a.emit(b"\xc7\x83" + struct.pack("<II", STAMP_OFFSET, STAMP_PIXELS))
    a.label("pixel_return")
    a.emit(b"\xc3")
    # The panorama computes horizontal UVs from s rather than the widened matrix.
    # EBX is the saved world camera; the vertical-angle helper still needs retail s.
    a.label("sky_lens")
    a.emit(b"\xd9\x83\x70\x02\x00\x00")
    a.emit(b"\x81\xbb" + struct.pack("<II", STAMP_OFFSET, STAMP_WIDE))
    a.jcc_short(0x85, "sky_return")
    a.emit(b"\x8b\x83\x00\x02\x00\x00", b"\x3d" + struct.pack("<I", (679 << 16) | 40))
    a.jcc_short(0x84, "sky_scale")
    a.emit(b"\x3d" + struct.pack("<I", 719 << 16))
    a.jcc_short(0x85, "sky_return")
    a.label("sky_scale")
    a.emit(_abs(FMUL_ABS, INV_STRETCH_VA))
    a.label("sky_return")
    a.emit(b"\xc3")
    a.label("pixel_bounds")
    # The world-marker HUD keeps its projection/glyph sizing, but its sphere
    # cull must admit the entire world clip, too (FUN_000f9950 clamps on failure).
    for offset in (0x284, 0x288):
        a.emit(_ecx(FLD_ECX, offset), _abs(FMUL_ABS, STRETCH_VA), _ecx(FSTP_ECX, offset))
    a.jmp("composite")
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
    labels: dict[str, int] = {}
    code = code_bytes(aspect, labels)
    sites = [
        ("constants", _offset(payload, CAVE_VA), RETAIL_ALT_KEYS[: len(data)], data),
        ("code_cave", _offset(payload, CODE_VA), RETAIL_CODE_CAVE, code),
        ("hook", _offset(payload, HOOK_VA), RETAIL_HOOK, PATCHED_HOOK),
    ]
    for va in HUD_PROJECT_CALLS:
        sites.append((f"hud_project_{va:x}", _offset(payload, va),
                      b"\xe8" + struct.pack("<i", PROJECT_VA - va - 5),
                      b"\xe8" + struct.pack("<i", labels["hud_project"] - va - 5)))
    sites.append(("shadow_cull_camera", _offset(payload, SHADOW_CAMERA_VA),
                  RETAIL_SHADOW_CAMERA, PATCHED_SHADOW_CAMERA))
    sites.append(("pixel_camera", _offset(payload, PIXEL_CAMERA_HOOK_VA),
                  b"\xe8" + struct.pack("<i", RECT_VA - PIXEL_CAMERA_HOOK_VA - 5),
                  b"\xe8" + struct.pack("<i", labels["pixel_camera"] - PIXEL_CAMERA_HOOK_VA - 5)))
    sites.append(("sky_horizontal_lens", _offset(payload, SKY_LENS_HOOK_VA),
                  bytes.fromhex("d98370020000"),
                  b"\xe8" + struct.pack("<i", labels["sky_lens"] - SKY_LENS_HOOK_VA - 5) + b"\x90"))
    return sites


def _site_state(payload: bytes, sites: list[tuple[str, int, bytes, bytes]]) -> str:
    for va, expected in CONTEXT_PINS:
        off = _offset(payload, va)
        if payload[off:off + len(expected)] != expected:
            return "foreign"
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
    if stamp in (STAMP_DIAGRAM, STAMP_PIXELS) or source_va == DIAGRAM_CAMERA_VA:
        return "pillarbox"
    full = tx0 <= INSET_X0 and tx1 >= INSET_X1 and tx1 <= FRAME_WIDTH
    if source_va == SKY_CAMERA_VA and full:
        return "none"
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
    b = max(a + 1, int(round(FRAME_CENTRE_X + (x1 - FRAME_CENTRE_X) * inv)))
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
    """Install or exactly replay v3; refuse mixed, older or foreign installations."""

    sites = _sites(payload, aspect)
    state = _site_state(payload, sites)
    _require(state in {"retail", "applied"}, f"widescreen sites are {state}; rebuild from a clean base")
    if state == "applied":
        return payload, {"aspect": aspect, "status": "applied", "version": POLISH_VERSION,
                         "experimental": True, "runtime_witnessed": False,
                         "edits": [], "changed_bytes": 0, "sections_repinned": []}
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
        edits.append({"label": label, "offset": f"0x{off:x}", "file_offset": f"0x{off:x}", "length": len(after),
                      "before": before.hex(), "after": after.hex(),
                      "before_sha256": hashlib.sha256(before).hexdigest(),
                      "after_sha256": hashlib.sha256(after).hexdigest()})
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
        "version": POLISH_VERSION,
        "experimental": True,
        "runtime_witnessed": False,
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
    "EXPERIMENTAL", "RUNTIME_WITNESSED", "POLISH_VERSION", "HELP_TEXT",
    "SKY_CAMERA_VA", "SKY_LENS_HOOK_VA", "STAMP_WIDE", "STAMP_PIXELS", "HUD_PROJECT_CALLS",
    "FADE_TINT_CAMERA_VA", "HOOK_VA", "STAMP_OFFSET", "STAMP_DIAGRAM", "STAMP_NONE", "PATCHED_HOOK", "RETAIL_ALT_KEYS", "RETAIL_CODE_CAVE", "RETAIL_HOOK",
    "REBUILD_VA", "RENDER_LIST_VA", "WidescreenPatchError", "apply", "applied_aspect", "cave_bytes", "classify",
    "code_bytes", "constants", "geometry", "pillarbox_clip", "pillarbox_x", "read_sites", "status", "stretch",
]
