"""b76-k1: the in-game block's managed budget at game setup, with 16 reserves and two extra created teams.

Game setup's in-game block (0x84EB0, called from 0x64942 with ecx=0x180000, edx=0x20000) manages
left = min(block, 0x180000). It carves the 0x2E0-byte header and the match roster export, sized by
0xC0B50 -> 0xBFC30 (the arena growth's size adapter); 0x125700 then builds heap A = min(0x148000, left)
and heap B = the rest, where the pregame intro director (DIR_INTRO) loads. The growth's earlier export
was a fixed full arena (0x92000 bytes), which left heap B empty, and the intro's load read into NULL:
the lab's U2 bugcheck (KeBugCheckEx 0x1E, C0000005 at 0x8001DBD4; block 0x180000, left 0xEDD20, heap A
974,080, heap B 0, read from the RAM snapshot at the crash).

Everything below runs the executable's own code under Unicorn on the real main roster: the growth's
stage of the two match teams (the practice-projection site), 0x84EB0 with the game's heap code
(0x48640, 0x48960, 0x48700), the size adapter and the exporter, and 0x125700's heap construction.
Hooks only return what the setup's UI and context calls would (0x84C80/0x84C50's game object, the
context queue 0x43F50, 0xF9310, 0x4A400, 0x65D30). The main heap's largest free block at setup is the
lab's: v7 at 64 MB (in-game block 1,469,900 B, m1's run) and U2 on K128 (675,328 B free after the
capped block, the RAMS crash snapshot). DIR_INTRO needs 73,856 B of heap B (R4's retail measurement).
"""
from pathlib import Path
import hashlib
import importlib.util
import os
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_k128 as k128
from mod_editor.core import nfl2k5_practice_squad_screen as screen
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'

MAIN_HEAP, HEAP_A, HEAP_B = 0xB04E24, 0xBB7410, 0xBB74B0
BLOCK_SIZE, BLOCK_LEFT, BLOCK_CURSOR, EXPORT = 0xB61618, 0xB6162C, 0xB61628, 0xB61624
DIRECTOR = 73856 - 128          # R4 (retail): heap B holds one 73,856-byte block, the intro director
ROOM_64 = (1469900 + 0x20000) & ~127   # largest free at setup, v7 at 64 MB: the block is 1,469,900 B (m1, lab);
                                        # the heap works in 128-byte units
ROOM_K128 = 0x180000 + 675328   # largest free at setup, U2 on K128: 675,328 B stayed free after the capped block


@unittest.skipUnless(XBE.is_file() and importlib.util.find_spec('unicorn'),
                     'in-game budget proofs require the pinned retail XBE and Unicorn')
class InGameBlockBudgetTests(unittest.TestCase):
    BASE, MAIN, MAIN_SIZE, STACK, STOP = 0x02000000, 0x05000000, 0x00400000, 0x03008000, 0x03100000

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise AssertionError('retail XBE hash mismatch')
        from mod_editor.core import nfl2k5_team_history as history
        if not (XBE.parent / 'vc_53450030/0').is_file():
            raise unittest.SkipTest('in-game budget proofs require the preserved ROST pack')
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(XBE.parent)
        with history._outer_image()(XBE.parent) as archive:
            entry = history._entry(archive)
            raw = archive.read(entry.virtual_offset, entry.size)
        cls.body = arena.migrate(raw, created_teams_extra=2)[0][0x20:]

        def compose():
            # the U2 executable's memory owners: the arena growth (16 reserves, 2 extra created teams) and K128
            # with the roster heap (its cap at 0x84EC2 only acts while the >64 MB region exists)
            base, _ = space.apply(cls.retail, growth.REQUESTS + k128.REQUESTS + screen.REQUESTS, scaleout=True)
            out, _ = growth.apply(base, reserves_16=True, created_teams_extra=2)
            out, _ = k128.apply(out, roster_heap=True)
            return out
        cls.current = compose()
        from tests import nfl2k5_roster_arena_legacy_runtime as legacy
        with mock.patch.object(growth, 'assembly', legacy), \
                mock.patch.object(growth, 'OPTION_OFFSET', (len(legacy.CODE) + 3) & ~3):
            cls.legacy = compose()

    # -- machine -------------------------------------------------------------------------------------------------
    def boot(self, xbe):
        import unicorn as uni
        self.uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        for section in ps._sections(xbe):
            self.uc.mem_write(section.virtual_address, xbe[section.raw_offset:section.raw_offset + section.raw_size])
        for address, size in ((self.BASE, 0x200000), (0x03000000, 0x10000), (self.STOP, 0x1000),
                              (self.MAIN, self.MAIN_SIZE)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(self.BASE, self.body)
        self.root = self.BASE + 0x40
        self.put(0xB72918, self.root)
        self.put(0xB72808, arena.ARENA_SIZE)
        self.put(0xB72804, self.root)
        self.put(0xB7280C, arena.ARENA_SIZE)
        self.call(0xC0500, ecx=self.root)
        self.teams = self.word(self.root + 0x1C)
        hooks = {0x84C80: self._game_object, 0x84C50: self._release_object, 0x43F50: lambda: self._return(0, 0x10),
                 0xF9310: lambda: self._return(0), 0x4A400: lambda: self._return(0, 4), 0x65D30: lambda: self._return(0)}
        for address, fn in hooks.items():
            self.uc.hook_add(uni.UC_HOOK_CODE, lambda _uc, _a, _s, f: f(), begin=address, end=address, user_data=fn)

    def word(self, a):
        return struct.unpack('<I', self.uc.mem_read(a, 4))[0]

    def put(self, a, v):
        self.uc.mem_write(a, struct.pack('<I', v))

    def _return(self, value, pop=0):
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP
        esp = self.uc.reg_read(UC_X86_REG_ESP)
        self.uc.reg_write(UC_X86_REG_EIP, self.word(esp))
        self.uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
        self.uc.reg_write(UC_X86_REG_EAX, value)

    def _game_object(self):
        # 0x84C80 keeps a game object at the block cursor ([0xB61638]); 0x84C50 clears it again before the heaps
        self.put(0xB61638, self.word(BLOCK_CURSOR))
        self._return(1)

    def _release_object(self):
        self.put(0xB61638, 0)
        self._return(self.word(BLOCK_CURSOR))

    def call(self, address, *, ecx=0, edx=0, args=(), budget=40000000):
        import unicorn as uni
        from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX,
                                       UC_X86_REG_EDI, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)
        self.uc.mem_write(self.STACK, struct.pack('<' + 'I' * (1 + len(args)), self.STOP, *args))
        for reg, value in ((UC_X86_REG_ESP, self.STACK), (UC_X86_REG_ECX, ecx), (UC_X86_REG_EDX, edx),
                           (UC_X86_REG_EAX, 0), (UC_X86_REG_EBX, 0x11111111), (UC_X86_REG_ESI, 0x22222222),
                           (UC_X86_REG_EDI, 0x33333333), (UC_X86_REG_EBP, 0x44444444)):
            self.uc.reg_write(reg, value)
        try:
            self.uc.emu_start(address, self.STOP, count=budget)
        except uni.UcError as exc:
            raise AssertionError(f'{address:#x} fault at {self.uc.reg_read(UC_X86_REG_EIP):#x}: {exc}') from exc
        self.assertEqual(self.uc.reg_read(UC_X86_REG_EIP), self.STOP, f'{address:#x}: exhausted {budget} instructions')
        return self.uc.reg_read(UC_X86_REG_EAX)

    # -- the setup ---------------------------------------------------------------------------------------------
    def main_heap(self, largest):
        """The game's own heap (0x48640) over a region whose largest free block (0x48960) is `largest`."""
        size = largest
        for _ in range(3):
            self.call(0x48640, ecx=MAIN_HEAP, edx=self.MAIN, args=(size,))
            got = self.call(0x48960, ecx=MAIN_HEAP)
            if got == largest:
                return
            size += largest - got
        self.fail(f'could not model a {largest:,}-byte largest free block (got {got:,})')

    def setup_game(self, xbe, room, *, k128_region):
        self.boot(xbe)
        home, away = self.teams, self.teams + 500
        for address, value in ((0xE576A0, 0), (0xE5FF80, 4), (0xB9C290, 0), (0xB9E230, 1), (0xE5FFE4, 0),
                               (0xE5FE64, self.word(home + 0x114)), (0xB018B8, 0x01610030 if k128_region else 0)):
            self.put(address, value)
        self.call(pr.STAGE_VA, ecx=away, edx=home)           # the two match teams, 0xB30864 and 0xB30A58
        self.main_heap(room)
        size = self.call(0xC0B50, ecx=0xB30864, edx=0xB30A58, args=(self.word(0xE5FE64),))
        self.assertEqual(self.call(0x84EB0, ecx=0x180000, edx=0x20000), 1)
        block, left = self.word(BLOCK_SIZE), self.word(BLOCK_LEFT)
        export = self.word(EXPORT)
        # the exporter wrote nothing past the size the block reserved for it (fresh heap memory is 0x86 filled)
        self.assertEqual(bytes(self.uc.mem_read(export + size, 256)), b'\x86' * 256)
        self.call(0x125700)
        signed = lambda value: value - (1 << 32) if value & 0x80000000 else value
        heap_a = signed(self.call(0x48960, ecx=HEAP_A))
        heap_b = signed(self.call(0x48960, ecx=HEAP_B))     # a heap built with no room reads as -128
        director = self.call(0x48700, ecx=HEAP_B, edx=DIRECTOR)
        return dict(export=size, block=block, left=left, heap_a=heap_a, heap_b=heap_b, director=director,
                    main_free=signed(self.call(0x48960, ecx=MAIN_HEAP)))

    # -- the proofs --------------------------------------------------------------------------------------------
    def assert_retail_shaped(self, got, block):
        self.assertLess(got['export'], 0x8000, got)                     # retail's match export is about 14 KB
        self.assertEqual(got['block'], block, got)
        self.assertGreaterEqual(got['heap_a'], 0x148000 - 0x100, got)   # heap A keeps its retail 0x148000
        self.assertGreaterEqual(got['heap_b'], DIRECTOR, got)
        self.assertNotEqual(got['director'], 0, got)                    # DIR_INTRO fits

    def test_k128_layout_keeps_heap_a_and_b_retail_sized_and_the_room_free(self):
        got = self.setup_game(self.current, ROOM_K128, k128_region=True)
        self.assert_retail_shaped(got, 0x180000)                         # the cap: the block stops at 1.5 MB
        self.assertGreaterEqual(got['heap_b'], 200000, got)             # retail heap B is 214,656 B
        self.assertGreaterEqual(got['main_free'], 600000, got)          # the room stays free for the game

    def test_without_the_cap_the_block_would_take_that_room(self):
        # the same room with the retail formula (no extra region, so the cap stays out): the block takes the largest
        # free block minus 128 KB and the room is gone; the heaps inside it are the same
        capped = self.setup_game(self.current, ROOM_K128, k128_region=True)
        retail = self.setup_game(self.current, ROOM_K128, k128_region=False)
        self.assertEqual(retail['block'], ROOM_K128 - 0x20000, retail)
        self.assertEqual((retail['heap_a'], retail['heap_b']), (capped['heap_a'], capped['heap_b']))
        self.assertLess(retail['main_free'], 0x20000 + 0x100, retail)
        self.assertGreaterEqual(capped['main_free'] - retail['main_free'], 500000)

    def test_64_mb_layout_keeps_heap_a_retail_sized_and_director_fits(self):
        got = self.setup_game(self.current, ROOM_64, k128_region=False)
        self.assert_retail_shaped(got, ROOM_64 - 0x20000)               # retail sizing without the extra region

    def test_the_earlier_full_arena_export_empties_heap_b_on_both_layouts(self):
        for room, region in ((ROOM_K128, True), (ROOM_64, False)):
            with self.subTest(k128=region):
                got = self.setup_game(self.legacy, room, k128_region=region)
                self.assertEqual(got['export'], arena.ARENA_SIZE, got)
                self.assertLess(got['heap_a'], 0x148000 - 0x10000, got)
                self.assertLess(got['heap_b'], DIRECTOR, got)
                self.assertEqual(got['director'], 0, got)               # the NULL the intro's load read into
        # the lab's crash numbers exactly: block 0x180000, left 0xEDD20 after the header and the export, and the
        # zero-room heap B written just past the block, which is the "bad block" the crash snapshot's main heap walk hit
        got = self.setup_game(self.legacy, ROOM_K128, k128_region=True)
        self.assertEqual((got['block'], got['left']), (0x180000, 0xEDD20), got)
        self.assertLess(got['main_free'], 0, got)


if __name__ == '__main__':
    unittest.main()
