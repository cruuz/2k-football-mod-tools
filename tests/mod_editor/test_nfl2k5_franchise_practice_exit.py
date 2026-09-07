"""Practice launch/quit/completion through retail screen-stack instructions.

Unicorn runs the installed START, push, pop, pop-to, game event dispatcher,
Quit and ended-game update/teardown. Scene loading, rendering, networking and
resource destruction are explicit service boundaries, not a played witness.
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
from mod_editor.core import nfl2k5_practice_reserves as reserves
from mod_editor.core import nfl2k5_practice_squad as squad
from mod_editor.core import nfl2k5_practice_squad_screen as screen
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
HAVE_UNICORN = importlib.util.find_spec('unicorn') is not None
MAIN_MENU = 0x515660
PAUSE_MENU = 0x4E9078
FRANCHISE_GAME_FLAG = 0xE5FFE4


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail default.xbe extraction is absent')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != squad.RETAIL_SHA256:
            raise unittest.SkipTest('extraction differs from the pinned USA retail XBE')
        cls.patched, cls.receipt = fp.apply(cls.retail)

    def test_no_new_sites_allocations_or_runtime_flag(self):
        self.assertEqual(len(fp.sites()), 4)
        self.assertEqual(len(self.patched), len(self.retail))
        self.assertEqual(fp.CODE_SIZE, 107)
        self.assertFalse(self.receipt['new_runtime_flag'])
        self.assertEqual((self.receipt['pops_on_start'], self.receipt['pushes_on_start']), (1, 1))
        image = XbeImage(self.retail)
        self.assertEqual(image.read(0x4E8CA0 + 0x28, 4), struct.pack('<I', fp.QUIT_VA))
        self.assertEqual(image.read(0x4E9010 + 8, 4), struct.pack('<I', 0x4E8D70))
        # Full declared owner capacity already covers every changed cave byte.
        manifest = ReservationManifest.load(Path(os.environ.get('NFL2K5_CAVE_MANIFEST', DEFAULT_MANIFEST)), image)
        self.assertEqual(manifest.overlaps(fp.CAVE_VA, fp.CAVE_END_VA,
                                          exclude_owner='nfl2k5_franchise_practice'), [])
        self.assertTrue(any(r.start <= fp.CAVE_VA and r.end >= fp.CAVE_END_VA
                            for r in manifest.overlaps(fp.CAVE_VA, fp.CAVE_END_VA)))
        for s in _sections(self.patched):
            self.assertEqual(s.stored_digest, section_digest(self.patched, s))

    def test_old_restart_and_mixed_bytes_refuse_without_mutating_input(self):
        old = bytearray(fp.CODE[:fp.START_STUB_VA - fp.CODE_VA])
        # The shipped beta-61 START, independently encoded, lacked a game push.
        old += bytes.fromhex('568bf18b860c010000c780840a000001000000')
        at = fp.CODE_VA + len(old)
        old += b'\xe8' + struct.pack('<i', fp.SCREEN_POP_VA - at - 5) + b'\x5e'
        at = fp.CODE_VA + len(old)
        old += b'\xe9' + struct.pack('<i', fp.GAME_START_VA - at - 5)
        data = bytearray(self.patched)
        off = rdata.offset_of(data, fp.CODE_VA)
        capacity = fp.CAVE_SIZE - fp.CODE_OFFSET
        data[off:off + capacity] = old.ljust(capacity, b'\xcc')
        for candidate in (data, bytearray(self.patched)):
            if candidate is not data:
                candidate[off + len(old) - 1] ^= 1
            before = bytes(candidate)
            self.assertEqual(fp.status(candidate), 'foreign')
            with self.assertRaises(fp.FranchisePracticeError):
                fp.apply(candidate)
            self.assertEqual(bytes(candidate), before)

    def test_new_game_lifecycle_pins_refuse_foreign_bytes(self):
        for va, content in ((fp.GAME_SCREEN_VA, fp.RETAIL_GAME_SCREEN),
                            (0x4E7CD8, fp.RETAIL_GAME_HOOKS),
                            (fp.SCREEN_PUSH_VA, fp.RETAIL_SCREEN_PUSH),
                            (fp.GAME_ENTER_VA, fp.RETAIL_GAME_ENTER)):
            for within in (0, len(content) - 1):
                data = bytearray(self.retail)
                data[rdata.offset_of(data, va) + within] ^= 1
                self.assertEqual(fp.status(data), 'foreign')
                with self.assertRaises(fp.FranchisePracticeError):
                    fp.apply(data)

    def test_initial_loader_keeps_existing_reserve_staging_call_chain(self):
        image = XbeImage(self.patched)
        # Loader -> game resources -> disposable players -> reserves' staging.
        # The middle call is gated by retail EC200 returning zero (offline).
        for va, target in ((0x645AF, 0x62BE0), (0x62CFD, 0x617E0),
                           (0x617F3, reserves.STAGE_VA)):
            call = image.read(va, 5)
            self.assertEqual(call[0], 0xE8)
            self.assertEqual(va + 5 + struct.unpack('<i', call[1:])[0], target)

    def test_composition_in_both_orders_and_delegated_menu_replay(self):
        # Native reserves/screen require Franchise Practice first. Exercise both
        # installation orders for independent writes and both orders for replay.
        a = squad.apply(fp.apply(self.retail)[0])[0]
        b = fp.apply(squad.apply(self.retail)[0])[0]
        self.assertEqual(a, b)
        a = reserves.apply(a)[0]
        b = fp.apply(reserves.apply(b)[0])[0]
        self.assertEqual(a, b)
        a = space.apply(a, screen.REQUESTS, scaleout=True)[0]
        a = screen.apply(a)[0]
        b = space.apply(squad.apply(self.retail)[0], screen.REQUESTS, scaleout=True)[0]
        b = screen.apply(reserves.apply(fp.apply(b)[0])[0])[0]
        self.assertEqual(a, b)
        for order in ((fp, reserves, screen), (screen, reserves, fp)):
            result = a
            for module in order:
                self.assertEqual(module.status(result), 'applied')
                result, receipt = module.apply(result)
                self.assertEqual(receipt['changed_bytes'], 0)
            self.assertEqual(result, a)
        self.assertEqual([row['label'] for row in fp.read_rows(a)][4:6], ['Practice', 'Practice Squad'])


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN, 'pinned USA retail XBE or Unicorn is absent')
class ExitExecutionTests(unittest.TestCase):
    MEMORY = 0x2000000
    MANAGER = MEMORY + 0x100
    STATE = MEMORY + 0x1000
    STACK = MEMORY + 0x1F000
    RETURN = MEMORY + 0x1FFF0

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != squad.RETAIL_SHA256:
            raise unittest.SkipTest('extraction differs from the pinned USA retail XBE')
        cls.patched = fp.apply(cls.retail)[0]
        base = reserves.apply(squad.apply(cls.patched)[0])[0]
        cls.composed = screen.apply(space.apply(base, screen.REQUESTS, scaleout=True)[0])[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack('<I', value))

    def get(self, va):
        return struct.unpack('<I', self.uc.mem_read(va, 4))[0]

    def top(self):
        return self.get(self.MANAGER + 8 * self.get(self.MANAGER + 0x100))

    def machine(self, *, payload=None, parent=fp.COACH_DESK_DESCRIPTOR_VA, flag=0,
                mode=1, confirm=2, load_success=True):
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
        self.put(self.MANAGER + fp.MANAGER_STATE_OFFSET, self.STATE)
        self.put(self.MANAGER, MAIN_MENU)
        self.put(self.MANAGER + 8, parent)
        self.put(self.MANAGER + 16, fp.CAVE_DESCRIPTOR_VA)
        self.put(self.MANAGER + 0x100, 2)
        self.put(fp.MODE_VA, mode)
        self.put(FRANCHISE_GAME_FLAG, flag)
        self.uc.mem_write(0xE576A0, bytes((i * 17 + 3) % 256 for i in range(0x5A0)))
        self.put(0xE576A0, 1 if parent == fp.COACH_DESK_DESCRIPTOR_VA else 0)
        # Source roster/player/depth bytes are separate from the transient game copies.
        self.uc.mem_write(self.MEMORY + 0x4000, bytes((i * 7 + 11) % 256 for i in range(0x2000)))
        self.put(0xB72918, self.MEMORY + 0x4000)
        self.snapshots = [(va, bytes(self.uc.mem_read(va, n))) for va, n in
                          ((0xE576A0, 0x5A0), (0xB72918, 4), (self.MEMORY + 0x4000, 0x2000))]
        self.calls = []
        self.events = []

        def finish(value=0, args=0):
            esp = self.uc.reg_read(x.UC_X86_REG_ESP)
            self.uc.reg_write(x.UC_X86_REG_EAX, value)
            self.uc.reg_write(x.UC_X86_REG_EIP, self.get(esp))
            self.uc.reg_write(x.UC_X86_REG_ESP, esp + 4 + args)
            # A real call is allowed to clobber volatile registers.
            self.uc.reg_write(x.UC_X86_REG_ECX, 0x12345678)
            self.uc.reg_write(x.UC_X86_REG_EDX, 0x87654321)

        def hook(uc, va, size, _):
            if va == 0x6E4E0:
                event = self.get(uc.reg_read(x.UC_X86_REG_ESP) + 4)
                self.events.append((self.top(), event))
                if self.top() != fp.GAME_SCREEN_VA:
                    finish(1, 4)  # only non-game screen rendering/UI services
            elif va == fp.GAME_LOAD_VA:
                self.calls.append(va)
                self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
                finish(int(load_success), 4)  # blocking resource/scene loader
            elif va in (fp.GAME_START_VA, 0x64710):
                self.calls.append(va)
                self.put(fp.GAME_STATE_VA, 3)
                self.put(0xA83A10, 1)
                finish()
            elif va == 0x649C0:
                self.calls.append(va)
                self.put(0xA83A10, 0)
                finish()
            elif va in (0x125700, 0x645D0):
                self.calls.append(va)  # execute the real practice-mode guards
            elif va in (0x125C50, 0x64620, 0x64650, 0xCF840, 0x773F0,
                        0x834F0, 0x61950, 0xF6030, 0xF72A0, 0xC5D60,
                        0xF5C70, 0xF5170, 0xF61E0, 0x432D0, 0xF6230, 0xF6510,
                        0xDCB20, 0x72BC0, 0x12BB60, 0x12BDE0):
                self.calls.append(va)
                finish()
            elif va in (0x128C60, 0x128C70, 0xEC200):
                finish()  # offline session
            elif va == 0x77390:
                finish(1)  # exercise the real Quit confirmation branch
            elif va == 0x14E440:
                finish(confirm, 24)  # modal Yes / Cancel service, callee cleanup
        self.uc.hook_add(u.UC_HOOK_CODE, hook)

    def call(self, entry, *, edx=0):
        x = self.x
        self.put(self.STACK, self.RETURN)
        self.uc.reg_write(x.UC_X86_REG_ESP, self.STACK)
        self.uc.reg_write(x.UC_X86_REG_ECX, self.MANAGER)
        self.uc.reg_write(x.UC_X86_REG_EDX, edx)
        self.uc.reg_write(x.UC_X86_REG_ESI, 0xCAFEBABE)
        self.uc.emu_start(entry, self.RETURN, count=20000)
        self.assertEqual(self.uc.reg_read(x.UC_X86_REG_EIP), self.RETURN)
        self.assertEqual(self.uc.reg_read(x.UC_X86_REG_ESP), self.STACK + 4)
        self.assertEqual(self.uc.reg_read(x.UC_X86_REG_ESI), 0xCAFEBABE)

    def assert_preserved(self):
        for va, before in self.snapshots:
            self.assertEqual(bytes(self.uc.mem_read(va, len(before))), before, hex(va))

    def test_quit_returns_to_retained_desk_with_either_retail_franchise_flag(self):
        for payload in (self.patched, self.composed):
            for flag in (0, 1):
                for mode in (0, 1, 2):
                    with self.subTest(composed=payload is self.composed, flag=flag, mode=mode):
                        self.machine(payload=payload, flag=flag, mode=mode)
                        self.call(fp.START_STUB_VA)
                        self.assertEqual(self.get(self.MANAGER + 0x100), 2)  # one pop, one push
                        self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
                        self.assertEqual(self.get(self.MANAGER + 8), fp.COACH_DESK_DESCRIPTOR_VA)
                        self.assertEqual(self.get(self.STATE + fp.GAME_PENDING_OFFSET), 1)
                        self.assertIn(fp.GAME_LOAD_VA, self.calls)
                        self.assertNotIn(fp.GAME_START_VA, self.calls)
                        self.call(fp.SCREEN_PUSH_VA, edx=PAUSE_MENU)
                        self.call(fp.QUIT_VA)
                        self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
                        self.assertEqual(self.get(fp.GAME_STATE_VA), 0)
                        self.call(0x650A0)  # actual game update invokes the ended-state pop
                        self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
                        self.assertEqual(self.get(self.MANAGER + 0x100), 1)
                        self.assertIn((fp.GAME_SCREEN_VA, 2), self.events)
                        self.assertEqual([v for v in self.calls if v in (0x125C50, 0x649C0, 0x645D0)],
                                         [0x125C50, 0x649C0, 0x645D0])
                        self.assertEqual(self.get(0xA83A10), 0)
                        self.assertNotIn(0xC5D60, self.calls)
                        self.assertEqual(self.get(FRANCHISE_GAME_FLAG), flag)
                        self.assert_preserved()

    def test_retail_exit_with_flag_clear_keeps_its_retail_parent(self):
        self.machine(payload=self.retail, parent=MAIN_MENU, flag=0)
        # Retail initial game entry uses the same game descriptor, above its own parent.
        self.put(self.MANAGER + 0x100, 0)
        self.call(fp.SCREEN_PUSH_VA, edx=fp.GAME_SCREEN_VA)
        self.call(fp.SCREEN_PUSH_VA, edx=PAUSE_MENU)
        self.call(fp.QUIT_VA)
        self.call(0x650A0)
        self.assertEqual(self.top(), MAIN_MENU)
        self.assertEqual(self.get(self.MANAGER + 0x100), 0)
        self.assert_preserved()

    def test_completion_states_share_teardown_and_preserve_fixture_season_bytes(self):
        for state in (0, 1, 2):
            self.machine()
            self.call(fp.START_STUB_VA)
            self.put(fp.GAME_STATE_VA, state)
            self.call(0x650A0)
            self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
            self.assertEqual(self.get(self.MANAGER + 0x100), 1)
            self.assertEqual(self.get(0xA83A10), 0)
            self.assertNotIn(0xC5D60, self.calls)
            self.assert_preserved()

    def test_season_completion_guard_positive_and_negative_controls(self):
        for mode in (0, 1, 2, 4, 5, 6, 7):
            self.machine(mode=mode)
            self.call(0x645D0)
            self.assertEqual(0xC5D60 in self.calls, mode in (5, 6, 7))

    def test_franchise_postgame_return_uses_same_parent_and_season_commit_guard(self):
        self.machine(mode=5, flag=1)
        # End Game leaves state 2, the live game and its postgame menu on top.
        self.put(self.MANAGER + 16, fp.GAME_SCREEN_VA)
        self.put(fp.GAME_STATE_VA, 2)
        self.put(0xA83A10, 1)
        self.call(fp.SCREEN_PUSH_VA, edx=0x4E935C)
        self.call(0x6ED30)  # the retail postgame Quit callback
        self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
        self.call(0x650A0)
        self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
        self.assertEqual(self.get(self.MANAGER + 0x100), 1)
        self.assertIn(0xC5D60, self.calls)  # intercepted only at the commit service

    def test_failed_initial_load_returns_to_desk_without_engine_start(self):
        self.machine(load_success=False)
        self.call(fp.START_STUB_VA)
        self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
        self.assertEqual(self.get(self.MANAGER + 0x100), 1)
        self.assertNotIn(0x64710, self.calls)
        self.assertNotIn(0x649C0, self.calls)
        self.assertNotIn(0xC5D60, self.calls)
        self.assert_preserved()

    def test_cancel_and_resume_leave_game_and_parent_in_place(self):
        self.machine(confirm=3)
        self.call(fp.START_STUB_VA)
        self.call(fp.SCREEN_PUSH_VA, edx=PAUSE_MENU)
        self.call(fp.QUIT_VA)
        self.assertEqual(self.top(), PAUSE_MENU)
        self.assertEqual(self.get(fp.GAME_STATE_VA), 3)
        self.call(0x6E8B0)  # retail Resume
        self.assertEqual(self.top(), fp.GAME_SCREEN_VA)
        self.assertEqual(self.get(self.MANAGER + 0x100), 2)
        self.assertNotIn(0x649C0, self.calls)
        self.assert_preserved()

    def test_previous_restart_reproduces_unwind_through_the_desk(self):
        self.machine()
        self.call(fp.SCREEN_POP_VA)  # beta-61 START's one settings pop
        self.call(fp.GAME_START_VA)  # beta-61 tail: restart, no game-screen push
        self.assertEqual(self.top(), fp.COACH_DESK_DESCRIPTOR_VA)
        self.call(fp.SCREEN_PUSH_VA, edx=PAUSE_MENU)
        self.call(fp.QUIT_VA)
        self.assertEqual(self.top(), MAIN_MENU)
        self.assertEqual(self.get(self.MANAGER + 0x100), 0)
        self.assertNotIn((fp.GAME_SCREEN_VA, 2), self.events)  # missing game destructor too


if __name__ == '__main__':
    unittest.main()
