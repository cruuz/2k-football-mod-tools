"""Native START input, launch dispatch, pause rows, Quit, teardown and Desk resume.

The old fixture is the exact b5301a7 feature-only cave. The complete route tests enter
through native input events, never a launch or Quit callback. Explicit service boundaries below
cover engine simulation/resources, UI layouts, controller hardware and modal UI.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_practice as fp
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_practice_squad as squad
from mod_editor.core import nfl2k5_practice_reserves as reserves
from mod_editor.core import nfl2k5_practice_squad_screen as screen
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
HAVE_UNICORN = importlib.util.find_spec('unicorn') is not None
MAIN = 0x515660
PAUSE = 0x4E9078
QUIT_MENU = 0x4E8D70
TEAM_SELECT = 0x5275F8
OLD_CAVE = bytes.fromhex(
    '04000000381d520006000000c81d520008000000101e520001000000581e520002000000a01e520005000000801d5200'
    '000000000b000000f81550000100000018831d0000000000030000000000000000000000aa831d000000000000000000'
    '00000000000000000000000000000000b0d8e70004831d00c03f0f0000000000c816500000000000e0d7e7000098ac00'
    '4400400252008d015500000001000000d6831d0000000000000000000000000000000000000000000000000000000000'
    '68000070416800005041e801a4f6ffc7050824aa0040831d00c3e82107f7ffe8bcc9eeff85c0741d508bc8e820f7e9ff'
    '59e85af7e9ffc705d401e60001000000e81bb0f0ffc3568bf18b860c010000c780840a000001000000e81260e9ff8bce'
    'bac07e4e005ee9955fe9ffcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
    'cccccccccccccccccccccccccccccccc'
)


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN, 'pinned USA retail XBE or Unicorn is absent')
class RouteTests(unittest.TestCase):
    MEMORY = 0x2000000
    MANAGER = MEMORY + 0x100
    STATE = MEMORY + 0x1000
    STACK = MEMORY + 0x1F000
    RETURN = MEMORY + 0x1FFF0

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != squad.RETAIL_SHA256:
            raise unittest.SkipTest('extraction differs from pinned USA retail XBE')
        cls.patched = fp.apply(cls.retail)[0]
        old_sites = [(label, va, before, OLD_CAVE if va == fp.CAVE_VA else after)
                     for label, va, before, after in fp.sites()
                     if va != fp.LAUNCH_TARGET_SITE_VA]
        cls.old = rdata.apply(cls.retail, old_sites, 'Historical b5301a7 fixture')[0]
        if hashlib.sha256(cls.old).hexdigest() != '6a9008b9e3aaf6c83a60418a72c8fd8dc1cf3cc90059a385d39addea17b871c9':
            raise AssertionError('historical regression fixture is not the prior feature-only XBE')
        base = reserves.apply(squad.apply(cls.patched)[0])[0]
        cls.composed = screen.apply(space.apply(base, screen.REQUESTS, scaleout=True)[0])[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack('<I', value))

    def get(self, va):
        return struct.unpack('<I', self.uc.mem_read(va, 4))[0]

    def depth(self):
        return self.get(self.MANAGER + 0x100)

    def top(self):
        return self.get(self.MANAGER + 8 * self.depth())

    def machine(self, payload=None, *, mode=1, flag=0, desk_depth=1, confirm=2, load=True):
        import unicorn as u
        import unicorn.x86_const as x
        self.x = x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1600000 - 0x10000)
        for s in _sections(payload or self.patched):
            data = payload or self.patched
            self.uc.mem_write(s.virtual_address, data[s.raw_offset:s.raw_offset + s.raw_size])
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.uc.mem_map(self.MEMORY, 0x20000)
        self.put(self.MANAGER + 0x10C, self.STATE)
        self.put(self.MANAGER, MAIN)
        self.put(self.MANAGER + 8 * desk_depth, fp.COACH_DESK_DESCRIPTOR_VA)
        self.put(self.MANAGER + 8 * (desk_depth + 1), fp.CAVE_DESCRIPTOR_VA)
        self.put(self.MANAGER + 0x100, desk_depth + 1)
        self.put(fp.MODE_VA, mode)
        self.put(0xE5FFE4, flag)
        self.put(0xBD8050, 1)  # native list-input handler enabled
        self.put(0xE576A0, 1)
        self.put(0xE576AC, 32)
        self.put(0xE576B4, 7)
        self.put(0xE576BC, 4)
        self.put(0xB72918, self.MEMORY + 0x4000)
        self.uc.mem_write(self.MEMORY + 0x4000, bytes((i * 7 + 11) % 256 for i in range(0x2000)))
        self.snapshots = [(va, bytes(self.uc.mem_read(va, n))) for va, n in
                          ((0xE576A0, 0x5A0), (0xB72918, 4), (self.MEMORY + 0x4000, 0x2000))]
        self.trace = []
        self.events = []
        self.inputs = 0
        self.confirm = confirm

        def finish(value=0, args=0):
            esp = self.uc.reg_read(x.UC_X86_REG_ESP)
            self.uc.reg_write(x.UC_X86_REG_EAX, value)
            self.uc.reg_write(x.UC_X86_REG_EIP, self.get(esp))
            self.uc.reg_write(x.UC_X86_REG_ESP, esp + 4 + args)
            self.uc.reg_write(x.UC_X86_REG_ECX, 0x12345678)
            self.uc.reg_write(x.UC_X86_REG_EDX, 0x87654321)

        # These boundaries have no screen-stack authority. Dispatchers, screen
        # handlers, list construction/activation, mode guards and pops run native.
        services = {
            # Rendering/layout setup and release, UI sounds.
            0xF2920, 0xF3CD0, 0xF37E0, 0xF2660, 0x14D310, 0x14D390,
            0x14FF70, 0x14FC20, 0x6B730, 0x6B740, 0x2C8810, 0x2C8880,
            0x27C040, 0x27C050, 0x27C2C0, 0x27C4D0, 0x6F290, 0x6EAD0,
            0x142FB0, 0x165C10, 0x142B40, 0x27D3A0,
            # Team Select team-preview/controller setup and teardown.
            0x77200, 0x2C1780, 0x2C17C0, 0x2C0AE0, 0x2C0A70, 0x2C2220,
            0x2C2240, 0x2C21F0, 0x31F760, 0xED540,
            # Scene resources and staging; reserves staging has its own native suite.
            0xF6510, 0xF6290, 0xF6210, 0xF5FE0, 0xF53C0, 0x62BE0,
            0xF5380, 0xF5D30, 0x125C50, 0x64620, 0x64650,
            0x834F0, 0x61950, 0xF6030, 0xF72A0, 0xF5C70, 0xF5170,
            0xF61E0, 0x432D0, 0xF6230, 0xF5C80,
            # Offline engine pause/input/audio helpers.
            0xCF840, 0x773F0, 0x9FC40, 0x9FCD0, 0x8AA30, 0x8AA40,
            0x14F9E0, 0x128D60, 0x128A70, 0x8BEA0, 0x8C0C0,
            0x146790,  # Main Menu network sign-in service in the old-route control
            0x8BE90, 0x8BEF0, 0x131500,
        }

        def hook(uc, va, size, _):
            self.trace.append(va)
            if va == 0x6E4E0:
                self.events.append((self.top(), self.get(uc.reg_read(x.UC_X86_REG_ESP) + 4)))
            elif va in services:
                # 8C0C0 is a single float-argument audio update.
                finish(args=4 if va == 0x8C0C0 else 0)
            elif va in (0x709B0, 0x128670, 0x131A10):
                finish(int(uc.reg_read(x.UC_X86_REG_ECX) == 0))
            elif va in (0xF3750, 0xF3780, 0xF3720):
                finish(self.inputs if uc.reg_read(x.UC_X86_REG_EDX) == 0 else 0, 4)
            elif va == 0x70A10:
                finish(self.inputs if uc.reg_read(x.UC_X86_REG_ECX) == 0 else 0)
            elif va == 0x70A50:
                self.inputs &= ~self.get(uc.reg_read(x.UC_X86_REG_ESP) + 4)
                finish(args=4)
            elif va in (0x2498A0, 0x128C70, 0x128C60, 0xEC200, 0x771F0):
                finish()  # normal offline frame; no disconnect/modal lock
            elif va in (0x33BFB0, 0x2C1230, 0x2C0EE0, 0x192020):
                finish(1)  # Team Select ready, both chosen teams valid
            elif va == 0xED5E0:
                finish(args=4)
            elif va == 0xF5430:
                finish(int(load))  # synchronous scene-resource loading
            elif va == 0x64710:
                self.put(fp.GAME_STATE_VA, 3)
                self.put(0xA83A10, 1)
                finish()
            elif va == 0x649C0:
                self.put(0xA83A10, 0)
                finish()
            elif va == fp.GAME_UPDATE_VA and self.get(fp.GAME_STATE_VA) == 3:
                finish()  # active rep simulation; pause detection in 650A0 runs
            elif va == 0x77390:
                finish(1)  # enable retail Quit confirmation
            elif va == 0x14E440:
                finish(self.confirm, 24)
            elif va in (0xC5D60, 0x13F1B0):
                self.fail(f'practice reached season commit/fresh franchise init at {va:#x}')
        self.uc.hook_add(u.UC_HOOK_CODE, hook)

    def call(self, entry, *, event=None):
        x = self.x
        self.put(self.STACK, self.RETURN)
        if event is not None:
            self.put(self.STACK + 4, event)
        self.uc.reg_write(x.UC_X86_REG_ESP, self.STACK)
        self.uc.reg_write(x.UC_X86_REG_ECX, self.MANAGER)
        self.uc.reg_write(x.UC_X86_REG_EAX, self.MANAGER)
        self.uc.reg_write(x.UC_X86_REG_EDX, 0)
        for reg in (x.UC_X86_REG_ESI, x.UC_X86_REG_EDI, x.UC_X86_REG_EBX, x.UC_X86_REG_EBP):
            self.uc.reg_write(reg, 0xCAFEBABE)
        try:
            self.uc.emu_start(entry, self.RETURN, count=30000)
        except Exception as exc:
            self.fail(f'{exc}; EIP={self.uc.reg_read(x.UC_X86_REG_EIP):#x}; tail={list(map(hex, self.trace[-25:]))}')
        self.assertEqual(self.uc.reg_read(x.UC_X86_REG_EIP), self.RETURN, list(map(hex, self.trace[-20:])))
        self.assertEqual(self.uc.reg_read(x.UC_X86_REG_ESP), self.STACK + (8 if event is not None else 4))
        for reg in (x.UC_X86_REG_ESI, x.UC_X86_REG_EDI, x.UC_X86_REG_EBX, x.UC_X86_REG_EBP):
            self.assertEqual(self.uc.reg_read(reg), 0xCAFEBABE)

    def frame(self, buttons=0):
        self.inputs = buttons
        self.call(0x6E4E0, event=6)
        self.inputs = 0

    def select(self, index):
        self.put(self.MANAGER + self.depth() * 8 + 4, index)
        self.frame(0x100)  # controller A, decoded by native list-input handler

    def launch(self):
        self.frame(0x10)
        self.assertEqual(self.top(), TEAM_SELECT)
        self.assertEqual(self.get(0xACF614), 3)
        self.frame(0x10)

    def quit_from_rep(self):
        self.frame(0x10)  # controller START: native game update opens pause
        self.assertEqual(self.top(), PAUSE)
        self.select(12)  # pause Quit is a type-0 row: push submenu via +8
        self.assertEqual(self.top(), QUIT_MENU)
        self.select(2)   # submenu Quit is type 9: invoke row's +0x28 callback

    def assert_preserved(self):
        for va, before in self.snapshots:
            self.assertEqual(bytes(self.uc.mem_read(va, len(before))), before, hex(va))

    def test_real_start_then_pause_quit_resumes_desk(self):
        for payload in (self.patched, self.composed):
            for mode in (0, 1, 2):
                for flag in (0, 1):
                    for depth in (0, 1):
                        with self.subTest(composed=payload is self.composed, mode=mode, flag=flag, depth=depth):
                            self.machine(payload, mode=mode, flag=flag, desk_depth=depth)
                            self.launch()
                            self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
                            self.assertEqual(self.depth(), depth + 1)
                            self.assertIn(fp.LAUNCH_TARGET_STUB_VA, self.trace)
                            self.assertIn(0x148B40, self.trace)
                            self.assertIn(0x2C0E70, self.trace)
                            self.quit_from_rep()
                            self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
                            self.assertEqual(self.get(fp.GAME_STATE_VA), 0)
                            self.frame()
                            self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
                            self.assertEqual(self.depth(), depth)
                            self.assertEqual(self.trace.count(fp.GAME_TEARDOWN_VA), 1)
                            self.assertIn((fp.COACH_DESK_DESCRIPTOR_VA, 3), self.events)
                            self.assertIn(0x14FF80, self.trace)  # native Desk menu rows rebuilt on resume
                            self.assertIn(fp.QUIT_VA, self.trace)
                            self.assertNotIn(0x6EC90, self.trace)
                            self.assertNotIn(0x6EDA0, self.trace)
                            self.assertEqual(self.get(0xE5FFE4), flag)
                            self.assert_preserved()

    def test_old_fix_start_is_unreachable_and_actual_route_returns_main_menu(self):
        self.machine(self.old)
        self.frame(0x10)
        self.assertEqual(self.top(), TEAM_SELECT)
        self.assertEqual(self.get(0xACF614), 3)  # native 2C21C0 -> 2C1950 store
        self.assertNotIn(0x1D83D6, self.trace)   # old unreferenced START stub
        self.frame(0x10)
        self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
        self.assertEqual(self.depth(), 1)
        self.assertEqual(self.get(self.MANAGER), MAIN)
        self.assertIn(0x2C0E7C, self.trace)  # fixed Main Menu unwind is at LAUNCH
        self.assertIn((fp.COACH_DESK_DESCRIPTOR_VA, 2), self.events)
        self.quit_from_rep()
        self.frame()
        self.assertEqual(self.top(), MAIN)
        self.assertEqual(self.depth(), 0)

    def test_cancel_resume_then_quit(self):
        self.machine(confirm=3)
        self.launch()
        self.quit_from_rep()
        self.assertEqual(self.top(), QUIT_MENU)
        self.assertEqual(self.get(fp.GAME_STATE_VA), 3)
        self.select(0)  # submenu Cancel
        self.assertEqual(self.top(), PAUSE)
        self.select(0)  # Resume
        self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
        self.confirm = 2
        self.quit_from_rep()
        self.frame()
        self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
        self.assert_preserved()

    def test_back_from_pregame_does_not_launch(self):
        self.machine()
        self.frame(0x200)  # native Back, event 10 has no custom handler
        self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
        self.assertNotIn(fp.LAUNCH_TARGET_STUB_VA, self.trace)
        self.assertNotIn(fp.GAME_ENTER_VA, self.trace)
        self.assert_preserved()

    def test_failed_scene_load_resumes_desk_through_real_start(self):
        self.machine(load=False)
        self.launch()
        self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
        self.assertNotIn(0x64710, self.trace)
        self.assert_preserved()

    def test_retail_practice_keeps_main_menu_destination_with_patch_installed(self):
        self.machine()
        self.put(self.MANAGER + 8, fp.SCRIM_DESCRIPTOR_VA)
        self.put(self.MANAGER + 0x100, 1)
        self.launch()
        self.assertEqual(self.depth(), 1)
        self.quit_from_rep()
        self.frame()
        self.assertEqual(self.top(), MAIN)
        self.assertEqual(self.depth(), 0)

    def test_target_guard_requires_mode_and_exact_bounded_stack(self):
        cases = [(1, 3, TEAM_SELECT, fp.CAVE_DESCRIPTOR_VA, fp.COACH_DESK_DESCRIPTOR_VA, True)]
        cases += [(mode, 3, TEAM_SELECT, fp.CAVE_DESCRIPTOR_VA, fp.COACH_DESK_DESCRIPTOR_VA, False)
                  for mode in (3, 4, 5, 6, 7, 8, 0xFFFFFFFF)]
        cases += [(1, depth, TEAM_SELECT, fp.CAVE_DESCRIPTOR_VA, fp.COACH_DESK_DESCRIPTOR_VA, False)
                  for depth in (0, 1, 32, 0xFFFFFFFF)]
        cases += [(1, 3, top, settings, parent, False) for top, settings, parent in
                  ((PAUSE, fp.CAVE_DESCRIPTOR_VA, fp.COACH_DESK_DESCRIPTOR_VA),
                   (TEAM_SELECT, fp.SCRIM_DESCRIPTOR_VA, fp.COACH_DESK_DESCRIPTOR_VA),
                   (TEAM_SELECT, fp.CAVE_DESCRIPTOR_VA, MAIN))]
        for mode, depth, top, settings, parent, scoped in cases:
            with self.subTest(mode=mode, depth=depth, top=top, settings=settings, parent=parent):
                self.machine(mode=mode)
                self.put(self.MANAGER + 8, parent)
                self.put(self.MANAGER + 16, settings)
                self.put(self.MANAGER + 24, top)
                self.put(self.MANAGER + 0x100, depth)
                before = bytes(self.uc.mem_read(self.MANAGER, 0x110))
                x = self.x
                self.put(self.STACK, self.RETURN)
                self.uc.reg_write(x.UC_X86_REG_ESP, self.STACK)
                self.uc.reg_write(x.UC_X86_REG_ESI, self.MANAGER)
                self.uc.reg_write(x.UC_X86_REG_ECX, 0x1234ABCD)
                self.uc.emu_start(fp.LAUNCH_TARGET_STUB_VA, self.RETURN, count=100)
                self.assertEqual(self.uc.reg_read(x.UC_X86_REG_EIP), self.RETURN)
                self.assertEqual(self.uc.reg_read(x.UC_X86_REG_ESP), self.STACK + 4)
                self.assertEqual(self.uc.reg_read(x.UC_X86_REG_EDX), fp.COACH_DESK_DESCRIPTOR_VA if scoped else MAIN)
                self.assertEqual(self.uc.reg_read(x.UC_X86_REG_ESI), self.MANAGER)
                self.assertEqual(self.uc.reg_read(x.UC_X86_REG_ECX), 0x1234ABCD)
                self.assertEqual(bytes(self.uc.mem_read(self.MANAGER, 0x110)), before)
                self.assert_preserved()

    def test_old_and_partial_target_installations_refuse(self):
        self.assertEqual(fp.status(self.old), 'foreign')
        for va, size in ((fp.LAUNCH_TARGET_SITE_VA, 5), (fp.CODE_VA, fp.CODE_SIZE)):
            data = bytearray(self.patched)
            off = rdata.offset_of(data, va)
            data[off:off + size] = self.old[off:off + size]
            before = bytes(data)
            self.assertEqual(fp.status(data), 'foreign')
            with self.assertRaises(fp.FranchisePracticeError):
                fp.apply(data)
            self.assertEqual(bytes(data), before)


if __name__ == '__main__':
    unittest.main()
