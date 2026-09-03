"""Hor+ widescreen patch (v2, activation hook): pattern-driven, fail-closed, copy-only.

Synthetic fixture: a minimal XBE whose header carries the retail certificate key block at 0x10254
and whose .text carries the retail bytes of the dead FUN_00046ee0 cave and the hooked ``call`` at
0x2ACA1, with correct section digests.  Retail-XBE tests (pattern check, apply, and a unicorn
emulation of the patched FUN_0002ac80 against a Python model of the transform) run only when the
private retail copy exists; the emulation additionally needs the ``unicorn`` package.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_widescreen as wide  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
TABLE_OFF = 0x400                      # section table (retail: 0x370; kept clear of the cave block)
HEADER_SIZE = 0xCC4
TEXT_INDEX = 0
TEXT_VA, TEXT_RAW, TEXT_SIZE = 0x11000, 0x2000, 0x40000        # covers 0x2ACA1 and 0x46EE0..0x47220
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
RETAIL_SHA256_PREFIX = "73105b17a3161c54"

try:  # the emulation test is optional
    import unicorn  # noqa: F401
    HAVE_UNICORN = True
except Exception:  # noqa: BLE001
    HAVE_UNICORN = False


def _digest(payload: bytes, raw: int, size: int) -> bytes:
    return hashlib.sha1(struct.pack("<I", size) + payload[raw: raw + size]).digest()  # nosec B324


def build_xbe() -> bytes:
    buf = bytearray(TEXT_RAW + TEXT_SIZE)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<I", buf, 0x108, HEADER_SIZE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT, IMAGE_BASE + TABLE_OFF)
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index == TEXT_INDEX:
            fields[1], fields[3], fields[4] = TEXT_VA, TEXT_RAW, TEXT_SIZE
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    buf[wide.CAVE_VA - IMAGE_BASE: wide.CAVE_END_VA - IMAGE_BASE] = wide.RETAIL_ALT_KEYS
    hook = TEXT_RAW + (wide.HOOK_VA - TEXT_VA)
    buf[hook: hook + 5] = wide.RETAIL_HOOK
    buf[hook + 5: hook + 7] = bytes.fromhex("85c0")                       # test eax,eax (FUN_0002ac80 continues)
    cave = TEXT_RAW + (wide.CODE_VA - TEXT_VA)
    buf[cave: cave + wide.CODE_CAVE_SIZE] = wide.RETAIL_CODE_CAVE
    header = TABLE_OFF + TEXT_INDEX * strength.SECTION_HEADER_SIZE
    buf[header + 36: header + 56] = _digest(bytes(buf), TEXT_RAW, TEXT_SIZE)
    return bytes(buf)


class WidescreenPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_xbe()

    def test_stretch_constants_and_geometry(self) -> None:
        self.assertAlmostEqual(wide.stretch("16:9"), 32.0 / 27.0)
        self.assertAlmostEqual(wide.stretch("16:10"), (16.0 / 10.0) / 1.5)
        c = wide.constants("16:9")
        self.assertAlmostEqual(c["inv_stretch"], 27.0 / 32.0)
        self.assertAlmostEqual(c["shift"], 360.0 * (1 - 27.0 / 32.0))       # 56.25
        self.assertEqual((c["x0"], c["x1"], c["frame"], c["unit"], c["centre"], c["one"]), (40.0, 680.0, 720.0, 2.0, 360.0, 1.0))
        data = wide.cave_bytes()
        self.assertEqual(len(data), wide.DATA_SIZE)
        self.assertEqual(struct.unpack("<9f", data)[:3], (struct.unpack("<f", struct.pack("<f", 32 / 27))[0],
                                                         struct.unpack("<f", struct.pack("<f", 27 / 32))[0], 56.25))
        geo = wide.geometry("16:9", lens=35.0)
        self.assertAlmostEqual(geo["hud_pixel_scale"], 27.0 / 32.0)
        self.assertEqual(geo["hud_window"], (90.0, 630.0))
        self.assertAlmostEqual(geo["hfov_retail_deg"], 54.43, places=1)
        self.assertAlmostEqual(geo["hfov_wide_deg"], 62.7, places=1)
        self.assertAlmostEqual(geo["vfov_deg"], 39.6, places=1)
        self.assertAlmostEqual(wide.pillarbox_x(40.0), 90.0)
        self.assertAlmostEqual(wide.pillarbox_x(680.0), 630.0)
        self.assertEqual(wide.pillarbox_clip(40, 680), (90, 630))
        self.assertEqual(wide.pillarbox_clip(60, 260), (107, 276))
        with self.assertRaises(wide.WidescreenPatchError):
            wide.stretch("21:9")

    def test_classification_rules(self) -> None:
        cls = wide.classify
        self.assertEqual(cls(True, 640, 40, 680), "horplus")             # gameplay / studio / cutscene
        self.assertEqual(cls(True, 720, 0, 720), "horplus")              # raw-frame perspective
        self.assertEqual(cls(True, 200, 60, 260), "pillarbox")           # preview window
        self.assertEqual(cls(True, 320, 40, 360), "pillarbox")           # split-screen half
        self.assertEqual(cls(True, 512, 0, 512), "none")                 # shadow map / RTT
        self.assertEqual(cls(True, 1024, 0, 1024), "none")
        self.assertEqual(cls(False, 640, 40, 680), "pillarbox")          # HUD / menus
        self.assertEqual(cls(False, 200, 60, 260), "pillarbox")          # 2D window overlay
        self.assertEqual(cls(False, 2, 0, 720), "none")                  # unit-rect fade camera, raw
        self.assertEqual(cls(False, 2, 40, 680), "none")                 # unit-rect on the inset target
        self.assertEqual(cls(False, 1, 0, 256), "none")                  # render-to-texture
        self.assertEqual(cls(False, 256, 0, 256), "none")
        self.assertEqual(cls(True, 10000, 40, 680, wide.DIAGRAM_CAMERA_VA), "pillarbox")   # formation view
        self.assertEqual(cls(True, 10000, 40, 680, 0, wide.STAMP_DIAGRAM), "pillarbox")
        self.assertEqual(cls(False, 640, 40, 680, wide.FADE_TINT_CAMERA_VA), "none")
        self.assertEqual(cls(False, 640, 40, 680, 0, wide.STAMP_NONE), "none")

    def test_cave_shape(self) -> None:
        labels: dict[str, int] = {}
        cave = wide.code_bytes(labels=labels)
        self.assertEqual(len(cave), wide.CODE_CAVE_SIZE)
        code = cave.rstrip(b"\xcc")
        self.assertLess(len(code), wide.CODE_CAVE_SIZE)
        self.assertEqual(code[:6], bytes.fromhex("8d91c0afa600"))          # lea edx,[ecx+0xA6AFC0]
        rebuild = code.index(b"\xe8", 12)
        self.assertEqual(wide.CODE_VA + rebuild + 5 + struct.unpack_from("<i", code, rebuild + 1)[0], wide.REBUILD_VA)
        self.assertEqual(code[-5], 0xE9)                                     # tail jmp FUN_00028110
        self.assertEqual(wide.CODE_VA + len(code) + struct.unpack("<i", code[-4:])[0], wide.RENDER_LIST_VA)
        self.assertEqual(code[-8: -5], bytes.fromhex("83c414"))             # add esp,20 before it
        for name in ("ortho", "pillarbox", "pb_ortho", "pb_clip", "horplus", "composite", "done"):
            self.assertIn(name, labels)
            self.assertTrue(wide.CODE_VA <= labels[name] < wide.CODE_VA + len(code))
        self.assertEqual(labels["done"], wide.CODE_VA + len(code) - 8)
        self.assertEqual(wide.code_bytes("16:10"), cave)                     # aspect lives in the constants only
        # constants block addresses referenced by the code all fall inside the 36-byte block
        for va in (wide.STRETCH_VA, wide.INV_STRETCH_VA, wide.SHIFT_VA, wide.X0_VA, wide.X1_VA, wide.FRAME_VA,
                   wide.UNIT_VA, wide.CENTRE_VA, wide.ONE_VA):
            self.assertIn(struct.pack("<I", va), code)
            self.assertTrue(wide.CAVE_VA <= va < wide.CAVE_VA + wide.DATA_SIZE)
        # hook targets the cave entry
        self.assertEqual(wide.PATCHED_HOOK[0], 0xE8)
        self.assertEqual(wide.HOOK_VA + 5 + struct.unpack("<i", wide.PATCHED_HOOK[1:])[0], wide.CODE_VA)
        self.assertEqual(struct.unpack("<I", code[code.index(struct.pack("<I", wide.STAMP_DIAGRAM)) :][:4])[0], wide.STAMP_DIAGRAM)

    def test_apply_rewrites_every_site_and_repins_digests(self) -> None:
        self.assertEqual(wide.status(self.payload), "retail")
        self.assertIsNone(wide.applied_aspect(self.payload))
        patched, receipt = wide.apply(self.payload)
        self.assertEqual(wide.status(patched), "applied")
        self.assertEqual(wide.status(patched, "16:9"), "applied")
        self.assertEqual(wide.status(patched, "16:10"), "foreign")
        self.assertEqual(wide.applied_aspect(patched), "16:9")
        self.assertEqual(receipt["sections_repinned"], [TEXT_INDEX])
        self.assertEqual([e["label"] for e in receipt["edits"]], ["constants", "code_cave", "hook"])
        self.assertEqual(patched[wide.CAVE_VA - IMAGE_BASE:][: wide.DATA_SIZE], wide.cave_bytes())
        self.assertEqual(patched[wide.CAVE_VA - IMAGE_BASE + wide.DATA_SIZE: wide.CAVE_END_VA - IMAGE_BASE],
                         wide.RETAIL_ALT_KEYS[wide.DATA_SIZE:])                 # the throw-tuning tail is untouched
        self.assertEqual(patched[TEXT_RAW + (wide.HOOK_VA - TEXT_VA):][:5], wide.PATCHED_HOOK)
        self.assertEqual(patched[TEXT_RAW + (wide.CODE_VA - TEXT_VA):][: wide.CODE_CAVE_SIZE], wide.code_bytes())
        live = wide.read_sites(patched)
        self.assertAlmostEqual(live["constants"][0], 32.0 / 27.0, places=6)
        self.assertEqual(live["hook"], wide.PATCHED_HOOK.hex())
        header = TABLE_OFF + TEXT_INDEX * strength.SECTION_HEADER_SIZE
        self.assertEqual(patched[header + 36: header + 56], _digest(patched, TEXT_RAW, TEXT_SIZE))
        digest_bytes = {header + 36 + k for k in range(20)}
        diff = [i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b and i not in digest_bytes]
        self.assertEqual(len(diff), receipt["changed_bytes"])
        with self.assertRaises(wide.WidescreenPatchError):
            wide.apply(patched)

    def test_other_aspect_and_foreign_bytes(self) -> None:
        patched, receipt = wide.apply(self.payload, aspect="16:10")
        self.assertEqual(wide.applied_aspect(patched), "16:10")
        self.assertAlmostEqual(receipt["stretch"], 16.0 / 15.0)
        self.assertEqual(wide.status(patched), "applied")
        buf = bytearray(self.payload)
        buf[TEXT_RAW + (wide.CODE_VA - TEXT_VA) + 40] ^= 0x01
        self.assertEqual(wide.status(bytes(buf)), "foreign")
        with self.assertRaises(wide.WidescreenPatchError):
            wide.apply(bytes(buf))
        buf = bytearray(self.payload)
        buf[wide.CAVE_VA - IMAGE_BASE + 3] ^= 0x80
        self.assertEqual(wide.status(bytes(buf)), "foreign")
        self.assertEqual(wide.status(b"\x00" * 0x400), "foreign")
        with self.assertRaises(wide.WidescreenPatchError):
            wide.apply(self.payload, aspect="4:3")


@unittest.skipUnless(RETAIL_XBE.exists(), "retail default.xbe not available")
class RetailSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = RETAIL_XBE.read_bytes()

    def test_retail_is_recognised_and_documented_bytes_hold(self) -> None:
        self.assertTrue(hashlib.sha256(self.payload).hexdigest().startswith(RETAIL_SHA256_PREFIX))
        self.assertEqual(wide.status(self.payload), "retail")
        text = self.payload[0x1000:]
        # the hooked call really is `call FUN_00028110` inside FUN_0002ac80, followed by test eax,eax
        self.assertEqual(text[wide.HOOK_VA - 0x11000: wide.HOOK_VA - 0x11000 + 7], wide.RETAIL_HOOK + bytes.fromhex("85c0"))
        self.assertEqual(text[0x2AC80 - 0x11000: 0x2AC80 - 0x11000 + 5], bytes.fromhex("b8c0afa600"))   # mov eax,0xA6AFC0
        # FUN_0002b510 and FUN_00028110 start where the cave calls them
        self.assertEqual(text[wide.REBUILD_VA - 0x11000: wide.REBUILD_VA - 0x11000 + 5], bytes.fromhex("5356578bf9"))
        self.assertEqual(text[wide.RENDER_LIST_VA - 0x11000: wide.RENDER_LIST_VA - 0x11000 + 1], b"\xa1")
        # the dead function's prologue; no aligned data pointer into the cave (code references: none, by
        # the Ghidra xref scan in WIDESCREEN_2026-09-03_NIGHT.md - a byte scan of .text only finds rel32
        # displacements that happen to spell these values)
        self.assertEqual(wide.RETAIL_CODE_CAVE[:8], bytes.fromhex("558bec83e4f083ec"))
        data_start = 0x4D9000
        for delta in range(0, 0x340, 4):
            needle = struct.pack("<I", wide.CODE_VA + delta)
            at = self.payload.find(needle, data_start)
            while at != -1:
                self.assertNotEqual(at % 4, 0, f"aligned pointer to cave+0x{delta:x} at file 0x{at:x}")
                at = self.payload.find(needle, at + 1)
        self.assertEqual(self.payload.count(b"\xe8" + struct.pack("<i", wide.CODE_VA - (wide.HOOK_VA + 5))), 0)

    def test_apply_on_retail(self) -> None:
        patched, receipt = wide.apply(self.payload)
        self.assertEqual(wide.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])
        self.assertEqual(len(patched), len(self.payload))
        self.assertLess(receipt["changed_bytes"], 900)
        self.assertGreater(receipt["changed_bytes"], 700)
        # the v1 sites (rect cave hook, layout aspect words, cot operands, lens constants) stay retail
        self.assertEqual(patched[0x1BAEF: 0x1BAF4], bytes.fromhex("e91cfaffff"))
        self.assertEqual(struct.unpack_from("<f", patched, 0x4DC40C)[0], 1.0)
        self.assertEqual(patched[0x56CDA: 0x56CDE], bytes.fromhex("9c414e00"))
        self.assertAlmostEqual(struct.unpack_from("<f", patched, 0x520E04)[0], 1.0 / 18.0, places=7)

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_activation_matches_the_model(self) -> None:
        """Run the patched FUN_0002ac80 on synthetic cameras; compare the active copy with the Python model."""

        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP
        from mod_editor.core.nfl2k5_bump_strength import _sections

        STACK, SENTINEL, SCRATCH, CAM = 0x7FF00000, 0x0BADF00D, 0x00F00000, wide.CAMERA_SIZE

        def load(payload: bytes) -> Uc:
            uc = Uc(UC_ARCH_X86, UC_MODE_32)
            uc.mem_map(0x10000, 0xEC0000 - 0x10000)
            uc.mem_write(0x10000, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
            for s in _sections(payload):
                if s.virtual_address + s.raw_size <= 0xEC0000:
                    uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
            uc.mem_map(STACK - 0x100000, 0x200000)
            uc.mem_map(SCRATCH, 0x10000)
            uc.mem_map(SENTINEL & ~0xFFF, 0x1000)
            return uc

        def run(uc: Uc, entry: int, ecx: int, stop_at: int | None = None) -> None:
            esp = STACK - 0x1000
            uc.mem_write(esp, struct.pack("<I", SENTINEL))
            uc.reg_write(UC_X86_REG_ESP, esp)
            uc.reg_write(UC_X86_REG_ECX, ecx)
            hit = []
            handle = None
            if stop_at is not None:
                handle = uc.hook_add(UC_HOOK_CODE, lambda u, a, _s, _d: (hit.append(a), u.emu_stop()) if a == stop_at else None)
            uc.emu_start(entry, SENTINEL, count=200000)
            if handle is not None:
                uc.hook_del(handle)
                self.assertTrue(hit, f"never reached 0x{stop_at:x}")

        def rot_y(deg: float) -> list[float]:
            c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 3.0, -2.0, 40.0, 1]

        def camera(perspective: bool, rect, target, s: float, view=None) -> bytes:
            buf = bytearray(CAM)
            struct.pack_into("<16f", buf, 0x40, *(view or [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 12.5, -3.0, 40.0, 1]))
            struct.pack_into("<I", buf, 0x220, 1 if perspective else 0)
            x0, y0, z0, x1, y1, z1 = rect
            struct.pack_into("<8f", buf, 0x230, x0, y0, z0, 0.0, x1, y1, z1, 0.0)
            tx0, ty0, tz0, tx1, ty1, tz1 = target
            struct.pack_into("<8f", buf, 0x250, tx0, ty0, tz0, 0.0, tx1, ty1, tz1, 0.0)
            struct.pack_into("<f", buf, 0x270, s)
            return bytes(buf)

        def model(retail_copy: bytes, source_va: int) -> tuple[bytes, str]:
            g = lambda off: struct.unpack_from("<f", retail_copy, off)[0]  # noqa: E731
            persp = struct.unpack_from("<I", retail_copy, 0x220)[0]
            stamp = struct.unpack_from("<I", retail_copy, wide.STAMP_OFFSET)[0]
            kind = wide.classify(bool(persp), g(0x240) - g(0x230), g(0x250), g(0x260), source_va, stamp)
            out = bytearray(retail_copy)
            if source_va == wide.FADE_TINT_CAMERA_VA or stamp == wide.STAMP_NONE:
                struct.pack_into("<I", out, wide.STAMP_OFFSET, wide.STAMP_NONE)
            if source_va == wide.DIAGRAM_CAMERA_VA or stamp == wide.STAMP_DIAGRAM:
                struct.pack_into("<I", out, wide.STAMP_OFFSET, wide.STAMP_DIAGRAM)
            if kind == "none":
                return bytes(out), kind
            c = wide.constants()
            f32 = lambda v: struct.unpack("<f", struct.pack("<f", v))[0]  # noqa: E731
            F, inv, K = f32(c["stretch"]), f32(c["inv_stretch"]), f32(c["shift"])
            proj = list(struct.unpack_from("<16f", retail_copy, 0))
            proj[0] *= inv
            if kind == "pillarbox":
                proj[8 if persp else 12] = proj[8] * inv - K if persp else proj[12] * inv + K
                clip = struct.unpack_from("<I", retail_copy, 0x200)[0]
                a2, b2 = wide.pillarbox_clip(clip & 0xFFFF, (clip >> 16) + 1)
                struct.pack_into("<I", out, 0x200, ((b2 - 1) << 16) | (a2 & 0xFFFF))
            else:
                t = F / g(0x270)
                cs = 1.0 / math.sqrt(1.0 + t * t)
                struct.pack_into("<2f", out, 0x274, cs, t * cs)
            struct.pack_into("<16f", out, 0, *proj)
            view = struct.unpack_from("<16f", retail_copy, 0x40)
            comp = list(struct.unpack_from("<16f", retail_copy, 0xF0))
            for i in range(4):
                comp[i * 4] = sum(view[i * 4 + k] * proj[k * 4] for k in range(4))
            struct.pack_into("<16f", out, 0xF0, *comp)
            return bytes(out), kind

        def close(a: bytes, b: bytes) -> None:
            for off, count, tol in ((0x00, 16, 2e-4), (0xF0, 16, 2e-4), (0x274, 4, 2e-3)):
                for i, (x, y) in enumerate(zip(struct.unpack_from(f"<{count}f", a, off), struct.unpack_from(f"<{count}f", b, off))):
                    self.assertLessEqual(abs(x - y), tol * max(1.0, abs(x), abs(y)), f"+0x{off + 4 * i:x}: {x} vs {y}")
            self.assertEqual(struct.unpack_from("<I", a, 0x200), struct.unpack_from("<I", b, 0x200), "clip rect")
            mask = set(range(0, 0x40)) | set(range(0xF0, 0x130)) | set(range(0x200, 0x204)) | set(range(0x274, 0x284))
            self.assertEqual([i for i in range(CAM) if i not in mask and a[i] != b[i]], [], "untouched bytes changed")

        retail = self.payload
        patched, _ = wide.apply(retail)
        s35 = 35.0 / 18.0
        cases = {
            "gameplay": (True, (-320, 224, -32, 320, -224, -100000), (40, 16, 0, 680, 464, 1), s35, rot_y(20), 0, "horplus"),
            "hud": (False, (-320, 224, -0.95, 320, -224, -1000), (40, 16, 0, 680, 464, 1), 1.0, None, 0, "pillarbox"),
            "fade raw": (False, (-1, 1, -1, 1, -1, -3), (0, 0, 0, 720, 480, 1), 1.0, None, 0, "none"),
            "raw persp": (True, (-360, 240, -32, 360, -240, -100000), (0, 0, 0, 720, 480, 1), s35, rot_y(-35), 0, "horplus"),
            "diagram window": (True, (-2500, -1550, 1250, 2500, -11650, -1250), (60, 120, 0.5, 260, 400, 1), math.sqrt(3), rot_y(5), wide.DIAGRAM_CAMERA_VA, "pillarbox"),
            "diagram full": (True, (-5000, -1550, 1250, 5000, -11650, -1250), (40, 120, 0.5, 680, 400, 1), math.sqrt(3), None, wide.DIAGRAM_CAMERA_VA, "pillarbox"),
            "ortho window": (False, (-300, 360, -1, -100, 80, -2), (60, 120, 0.5, 260, 400, 1), 1.0, None, 0, "pillarbox"),
            "preview": (True, (-100, 75, -32, 100, -75, -100000), (200, 100, 0, 400, 250, 1), 1.5, rot_y(60), 0, "pillarbox"),
            "rtt ortho": (False, (0, 0, -0.001, 1, 1, 16777216), (0, 0, 0, 256, 256, 1), 1.0, None, 0, "none"),
            "rtt persp": (True, (-256, 256, -32, 256, -256, -100000), (0, 0, 0, 512, 512, 1), 1.0, None, 0, "none"),
            "fade tint": (False, (-320, 224, -1, 320, -224, -2), (40, 16, 0, 680, 464, 1), 1.0, None, wide.FADE_TINT_CAMERA_VA, "none"),
            "split half": (True, (-160, 224, -32, 160, -224, -100000), (40, 16, 0, 360, 464, 1), s35, None, 0, "pillarbox"),
        }
        for name, (persp, rect, target, s, view, src, expected_kind) in cases.items():
            with self.subTest(camera=name):
                obj = camera(persp, rect, target, s, view)
                where = src or SCRATCH
                uc = load(retail)
                uc.mem_write(where, obj)
                run(uc, wide.REBUILD_VA, where)                          # retail rebuild in place = the reference
                reference = bytes(uc.mem_read(where, CAM))
                expect, kind = model(reference, where)
                self.assertEqual(kind, expected_kind)
                uc = load(patched)
                uc.mem_write(where, obj)
                run(uc, 0x2AC80, where, stop_at=wide.RENDER_LIST_VA)     # the hooked activation
                got = bytes(uc.mem_read(wide.ACTIVE_CAMERA_VA, CAM))
                self.assertEqual(bytes(uc.mem_read(where, CAM)), obj, "the camera object must stay retail")
                esp = uc.reg_read(UC_X86_REG_ESP)
                self.assertEqual(struct.unpack("<I", uc.mem_read(esp, 4))[0], 0x2ACA6, "return address for FUN_00028110")
                close(got, expect)
                self.assertEqual(struct.unpack_from("<I", got, wide.STAMP_OFFSET), struct.unpack_from("<I", expect, wide.STAMP_OFFSET))
                # a saved copy of the active camera re-activated (FUN_0002ad80 + FUN_0002ac80) is a no-op
                uc.mem_write(SCRATCH + 0x1000, got)
                run(uc, 0x2AC80, SCRATCH + 0x1000, stop_at=wide.RENDER_LIST_VA)
                again = bytes(uc.mem_read(wide.ACTIVE_CAMERA_VA, CAM))
                close(again, got)
                if name == "gameplay":     # the numbers the report quotes
                    m00, m11 = struct.unpack_from("<f", got, 0)[0], struct.unpack_from("<f", got, 0x14)[0]
                    self.assertAlmostEqual(m00, 525.0, places=2)
                    self.assertAlmostEqual(m11, -622.2222, places=2)
                    cs, sn = struct.unpack_from("<2f", got, 0x274)
                    self.assertAlmostEqual(math.degrees(math.atan2(sn, cs)) * 2, 62.7, places=1)
                if name == "hud":
                    self.assertEqual(struct.unpack_from("<I", got, 0x200)[0], (629 << 16) | 90)
                    self.assertAlmostEqual(struct.unpack_from("<f", got, 0)[0], 27 / 32, places=6)
                    self.assertAlmostEqual(struct.unpack_from("<f", got, 0x30)[0], 360.0, places=3)
                if name == "diagram window":
                    self.assertEqual(struct.unpack_from("<I", got, 0x200)[0], (275 << 16) | 107)


if __name__ == "__main__":
    unittest.main()
