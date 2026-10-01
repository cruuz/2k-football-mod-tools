"""vb3 D2 (2026-09-23): widescreen menus stay 4:3 while gameplay keeps hor+.

Noah's recording [v1 1:17]: "the game's in widescreen now it's not perfect but as you can see it spills over the left
and right". The owner nfl2k5_widescreen_menus enters the camera activation call at 0x2ACA1 before the widescreen cave
and, in the front end (PLAY_STATE [0xE602B8] == 0, measured in the lab), stamps a full-width perspective camera's
active copy 'DIAG', which the widescreen cave pillarboxes. The native tests activate cameras through the real
FUN_0002AC80 and the real widescreen cave under Unicorn and compare the active camera with the widescreen-only
executable. Offline evidence; retail-backed classes skip without the private USA XBE.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_widescreen as w  # noqa: E402
from mod_editor.core import nfl2k5_widescreen_menus as menus  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None


class ContractTests(unittest.TestCase):
    """Retail-free."""

    def test_requests_and_constants(self):
        self.assertEqual(menus.REQUESTS, ((menus.OWNER, "code", 128, 16),))
        self.assertEqual(menus.STAMP_DIAGRAM, w.STAMP_DIAGRAM)
        self.assertEqual(menus.STAMP_NONE, w.STAMP_NONE)
        self.assertEqual(menus.ACTIVE_CAMERA_VA, w.ACTIVE_CAMERA_VA)
        self.assertEqual(menus.STAMP_VA, w.ACTIVE_CAMERA_VA + w.STAMP_OFFSET)
        self.assertEqual(struct.unpack("<f", struct.pack("<I", menus.X0_MAX))[0], 40.0)
        self.assertEqual(struct.unpack("<f", struct.pack("<I", menus.X1_MIN))[0], 680.0)
        self.assertEqual(struct.unpack("<f", struct.pack("<I", menus.X1_MAX))[0], 720.0)

    def test_the_code_forwards_every_path_to_the_cave(self):
        code, entry = menus.code_for(0x1000000, w.CODE_VA)
        self.assertEqual(struct.unpack_from("<I", code, 0)[0], w.CODE_VA)
        self.assertEqual(entry, 0x1000004)
        used = code.rstrip(b"\xcc")
        self.assertEqual(used[-5], 0xE9)
        self.assertEqual(0x1000000 + len(used) + struct.unpack_from("<i", used, len(used) - 4)[0], w.CODE_VA)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "the private USA XBE and Unicorn are required")
class NativeTests(unittest.TestCase):
    STACK = 0x7FF00000
    AREA = 0x0F00000
    STOP = 0x0BADF00D

    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        cls.wide, _ = w.apply(retail, w.DEFAULT_ASPECT)
        cls.gated, cls.receipt = menus.apply(cls.wide)

    def load(self, payload, play_state):
        import unicorn as u
        from unicorn import x86_const as r
        uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({p for s in image.sections for p in range(s.start & -4096, (s.end + 4095) & -4096, 4096)}
                       | set(range(image.base, image.base + image.headers_size + 4095, 4096)))
        runs = []
        for p in pages:
            if runs and runs[-1][1] == p:
                runs[-1][1] += 4096
            else:
                runs.append([p, p + 4096])
        for start, end in runs:
            uc.mem_map(start, end - start)
        uc.mem_write(image.base, payload[:image.headers_size])
        for s in image.sections:
            if s.raw_size:
                uc.mem_write(s.start, payload[s.raw:s.raw + min(s.raw_size, s.size)])
        uc.mem_map(self.STACK - 0x10000, 0x20000)
        uc.mem_map(self.AREA, 0x10000)
        uc.mem_map(self.STOP & ~0xFFF, 0x1000)
        uc.mem_write(0xA6A9D0, struct.pack("<II", 720, 480))
        uc.mem_write(0xA6AFB4, struct.pack("<I", w.ACTIVE_CAMERA_VA))
        uc.mem_write(menus.PLAY_STATE_VA, struct.pack("<I", play_state))
        uc.reg_write(r.UC_X86_REG_FPCW, 0x37F)
        return uc

    def activate(self, payload, camera, play_state):
        import unicorn as u
        from unicorn import x86_const as r
        uc = self.load(payload, play_state)
        uc.mem_write(self.AREA, camera)
        uc.mem_write(self.STACK, struct.pack("<I", self.STOP))
        uc.reg_write(r.UC_X86_REG_ESP, self.STACK)
        uc.reg_write(r.UC_X86_REG_ECX, self.AREA)
        hit = []

        def check(machine, address, _size, _data):
            if address == w.RENDER_LIST_VA:
                hit.append(address)
                machine.emu_stop()
        uc.hook_add(u.UC_HOOK_CODE, check)
        uc.emu_start(0x2AC80, 0, count=20000)
        self.assertEqual(hit, [w.RENDER_LIST_VA])
        self.assertEqual(bytes(uc.mem_read(self.AREA, w.CAMERA_SIZE)), camera)   # the source is never written
        return bytes(uc.mem_read(w.ACTIVE_CAMERA_VA, w.CAMERA_SIZE))

    @staticmethod
    def camera(*, perspective=True, target=(40, 16, 680, 464), stamp=0):
        b = bytearray(w.CAMERA_SIZE)
        struct.pack_into("<16f", b, 0x40, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        struct.pack_into("<I", b, 0x220, int(perspective))
        struct.pack_into("<8f", b, 0x230, -320, 224, -1, 0, 320, -224, -1000, 0)
        struct.pack_into("<I", b, w.STAMP_OFFSET, stamp)
        x0, y0, x1, y1 = target
        struct.pack_into("<8f", b, 0x250, x0, y0, 0, 0, x1, y1, 1, 0)
        struct.pack_into("<f", b, 0x270, 35 / 18)
        return bytes(b)

    def test_install_replay_and_views(self):
        self.assertEqual(menus.status(self.gated), "applied")
        self.assertEqual(w.status(self.gated), "applied")
        self.assertEqual(w.applied_aspect(self.gated), w.DEFAULT_ASPECT)
        self.assertEqual(menus.apply(self.gated)[0], self.gated)
        self.assertEqual(menus.views(self.gated), {w.HOOK_VA: w.PATCHED_HOOK})
        self.assertEqual(menus.status(self.wide), "retail")
        with self.assertRaises(menus.WidescreenMenusError):
            menus.apply(XBE.read_bytes())                       # no widescreen, no menus owner

    def test_front_end_full_width_perspective_is_pillarboxed(self):
        full = self.camera()
        front = self.activate(self.gated, full, play_state=0)
        pillar = self.activate(self.wide, self.camera(stamp=w.STAMP_DIAGRAM), play_state=0)
        horplus = self.activate(self.wide, full, play_state=0)
        self.assertEqual(front, pillar)
        self.assertNotEqual(front, horplus)

    def test_gameplay_keeps_hor_plus(self):
        full = self.camera()
        for state in (5, 0xB, 0xD, 0xE, 0x12):
            with self.subTest(play_state=state):
                self.assertEqual(self.activate(self.gated, full, play_state=state),
                                 self.activate(self.wide, full, play_state=state))

    def test_other_front_end_cameras_are_untouched(self):
        for camera in (self.camera(target=(100, 100, 300, 300)),         # sub-window: already pillarboxed
                       self.camera(target=(0, 0, 720, 480)),             # full frame at the edge (x0 0 <= 40)
                       self.camera(perspective=False),                    # ortho menu frame
                       self.camera(target=(40, 16, 760, 464)),           # outside the frame (x1 > 720)
                       self.camera(stamp=w.STAMP_NONE)):                 # the fade tint's exemption
            with self.subTest(target=struct.unpack_from("<f", camera, 0x260)[0],
                              perspective=struct.unpack_from("<I", camera, 0x220)[0]):
                expected = self.activate(self.wide, camera, play_state=0)
                got = self.activate(self.gated, camera, play_state=0)
                x0, x1 = struct.unpack_from("<f", camera, 0x250)[0], struct.unpack_from("<f", camera, 0x260)[0]
                persp = struct.unpack_from("<I", camera, 0x220)[0]
                stamp = struct.unpack_from("<I", camera, w.STAMP_OFFSET)[0]
                if persp and x0 <= 40 and 680 <= x1 <= 720 and stamp != w.STAMP_NONE:
                    self.assertEqual(got, self.activate(self.wide, camera[:w.STAMP_OFFSET]
                                                        + struct.pack("<I", w.STAMP_DIAGRAM)
                                                        + camera[w.STAMP_OFFSET + 4:], play_state=0))
                else:
                    self.assertEqual(got, expected)

    def test_a_foreign_owner_body_is_foreign_for_both(self):
        alloc = next(a for a in menus.space.layout(self.gated)["allocations"] if a["owner"] == menus.OWNER)
        broken = bytearray(self.gated)
        broken[alloc["raw"] + 10] ^= 0xFF
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for section in _sections(broken):
            broken[section.header_offset + 36:section.header_offset + 56] = section_digest(broken, section)
        self.assertEqual(menus.status(bytes(broken)), "foreign")
        self.assertEqual(w.status(bytes(broken)), "foreign")


if __name__ == "__main__":
    unittest.main()
