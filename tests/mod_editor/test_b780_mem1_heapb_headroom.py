"""b780-mem1: heap B at the pregame intro on the SOFTDRINK 2K28 v0.9 release candidate, and the K128 early form's fix.

The lab (EMU1 run H1R2, 2026-11-03, the v0.9 RC disc 93c889e4 at 128 MiB, Texans at Ravens, M&T Bank Stadium) measured,
at game setup: main heap largest free block 1,495,936 B, in-game block 1,364,864 B (that minus 0x20000), heap A
1,343,360 B, heap B 6,400 B (largest allocation 6,272 B), and DIR_INTRO's DRCT load (73,680 B, 73,856 B charged) got
NULL at 0x166745; the resource load guard caught it and the pregame looped.

Model (the game's own code, read from the XBE): the arena init (0x326E0) takes the largest contiguous block it can get
(XPhysicalAlloc probe from 64 MiB down) minus [0xA6D324] = 2 MiB and builds the main heap over it (0x3908D); the
XBE's boot-loaded pages come out of the same 64 MiB first, so every resident page is one page less main heap. Game
setup's in-game block (0x84EB0) takes the main heap's largest free block minus 0x20000 (with K128's region present,
capped at the 0x180000 the game uses); 0x125700 builds heap A = min(0x148000, left) and heap B = the rest, where the
intro director loads.

Everything below runs the release candidate's own executable under Unicorn with its own main roster (the disc's ROST
resource): the stage of the two match teams, 0x84EB0 with K128's cap and the game's heap code, the size adapter and
the exporter, and 0x125700. It reproduces the lab's heap B exactly at the lab's room, finds the room DIR_INTRO needs,
and shows the K128 early form (its arena holds the room the XBE's pages took: 46.7 -> 61.6 MiB in R1's lab, and on
this RC a main heap 15,978,496 B larger in EMU1's T1) puts the in-game block at its cap, so heap B is the retail
214 KB at every stadium, while 64 MB keeps the retail block size.

Private fixtures (read only; the tests skip without them):
  NFL2K5_B780_RC_XBE   the RC disc's default.xbe (sha256 1a476d94...)
  NFL2K5_B780_RC_ROST  the RC disc's main ROST resource (outer entry 5, 827,488 B)
  NFL2K5_V08_XBE       the v0.8 disc's default.xbe (sha256 5f987568...), with NFL2K5_V08_ROST_BODY (its roster body)
"""
from pathlib import Path
import hashlib
import importlib.util
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_k128 as k128
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core.nfl2k5_cave_oracle import XbeImage


def _env_path(name):
    value = os.environ.get(name)
    return Path(value) if value else None


RC_XBE, RC_ROST = _env_path('NFL2K5_B780_RC_XBE'), _env_path('NFL2K5_B780_RC_ROST')
V08_XBE, V08_BODY = _env_path('NFL2K5_V08_XBE'), _env_path('NFL2K5_V08_ROST_BODY')
RC_XBE_SHA256 = '1a476d94ee64acf5bb287736cc06fea8f8f8181f3ee98e2b9586006c5659c9da'
RC_EARLY_XBE_SHA256 = '329842b0560aed2bd52d96107ddcf89649f28cd7740e58641d6aac8973bb4e1b'   # the second EMU1 witness disc's
V08_XBE_SHA256 = '5f987568bc88122f'

MAIN_HEAP, HEAP_A, HEAP_B = 0xB04E24, 0xBB7410, 0xBB74B0
BLOCK_SIZE, BLOCK_LEFT, BLOCK_CURSOR, EXPORT = 0xB61618, 0xB6162C, 0xB61628, 0xB61624
DIRECTOR = 73856 - 128           # DIR_INTRO: 73,680 B of payload, 73,856 B charged (R4; the lab's DRCT hit)
LAB_ROOM_RC = 1495936            # H1R2: the main heap's largest free block at setup (1,364,864 B block + 0x20000)
LAB_HEAP_B_CAP, LAB_HEAP_B_LARGEST = 6400, 6272
LAB_ROOM_V08 = 1555456           # H1V8B: the v0.8 control's largest free block at setup (block 1,424,384 B)
RESIDENT_RC, RESIDENT_V08 = 15896576, 15835136   # boot-loaded section pages (REV2; recomputed below)
HISTORY_SCREEN_BYTES = 55360     # nfl2k5_history_screen's allocations in the RC (code 18,432, read_only 36,864, data 64)
# the early form's main heap gain on this RC, measured: EMU1 T1 (the witness disc) main heap 0x802E9100..0x8314C480,
# free 33,583,232 B before START GAME, against H1R2 (RC1, late form) 0x81226100..0x8314C480, free 17,604,736 B
EARLY_ARENA_GAIN = (0x8314C480 - 0x802E9100) - (0x8314C480 - 0x81226100)
assert EARLY_ARENA_GAIN == 33583232 - 17604736 == 15978496
REGION = (0x01620030, 0x05520030)  # H1R2's K128 words 0xB018B8/BC (the >64 MB region)
TEAM_BAL, TEAM_HOU = 24, 29      # retail team indices (nfl2k5_team_history.RETAIL_TEAM_INDEX)


def early_from_late(payload: bytes) -> bytes:
    """The K128 late install (k128 + roster heap + 128 MB entry) turned into the early form in place: 0x327D1 back
    to retail, the owned code rebuilt for the options plus OPT_EARLY (sealed through the space directory), the
    section digests repinned. Same allocation; the entry stays the 128 MB entry (it runs the early phase itself),
    or moves from k128_entry to the early entry without it."""
    code_va = k128.allocations(payload)['code']['va']
    flags = struct.unpack_from('<I', XbeImage(payload).read(code_va, k128.CODE_SIZE), k128.OPTIONS_OFFSET)[0]
    assert not flags & k128.OPT_EARLY
    buf = bytearray(payload)
    at = rdata.offset_of(payload, k128.HOOK2_VA)
    assert bytes(buf[at:at + 10]) == k128.hook2_bytes(code_va)
    buf[at:at + 10] = k128.RETAIL_HOOK2
    # the entry: the 128 MB entry either way; without it, the early entry at +0x1A0 replaces k128_entry at +0
    buf[k128.ENTRY_FIELD:k128.ENTRY_FIELD + 4] = k128.encode_entry(code_va + k128.entry_offset(flags | k128.OPT_EARLY))
    k128._repin(buf)
    out, _ = space.install_code(bytes(buf), k128.OWNER, k128.code_for(code_va, flags | k128.OPT_EARLY),
                                previous=k128.code_for(code_va, flags))
    buf = bytearray(out)
    k128._repin(buf)
    return bytes(buf)


def resident_bytes(payload: bytes) -> int:
    base, count, table = (struct.unpack_from('<I', payload, o)[0] for o in (0x104, 0x11C, 0x120))
    total = 0
    for i in range(count):
        flags, va, vsize = struct.unpack_from('<3I', payload, table - base + i * 0x38)
        if flags & 2:       # preload: loaded at boot
            total += ((va + vsize + 0xFFF) & ~0xFFF) - (va & ~0xFFF)
    return total


class Machine:
    """The setup's in-game block and intro heaps on an executable's own code (after test_nfl2k5_ingame_block_budget)."""

    BASE, MAIN, STACK, STOP = 0x02000000, 0x06000000, 0x03008000, 0x03100000
    MAIN_SIZE = 0x01400000          # up to 20 MiB of modelled main heap

    def __init__(self, xbe: bytes, body: bytes):
        import unicorn as uni
        self.uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        top = (0x10000 + struct.unpack_from('<I', xbe, 0x10C)[0] + 0xFFFF) & ~0xFFFF
        self.uc.mem_map(0x10000, top - 0x10000)
        for section in ps._sections(xbe):
            self.uc.mem_write(section.virtual_address, xbe[section.raw_offset:section.raw_offset + section.raw_size])
        for address, size in ((self.BASE, 0x200000), (0x03000000, 0x10000), (self.STOP, 0x1000),
                              (self.MAIN, self.MAIN_SIZE)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(self.BASE, body)
        self.root = self.BASE + 0x40
        arena_size = len(body) - 0x40
        for address, value in ((0xB72918, self.root), (0xB72808, arena_size), (0xB72804, self.root),
                               (0xB7280C, arena_size)):
            self.put(address, value)
        self.call(0xC0500, ecx=self.root)
        self.teams = self.word(self.root + 0x1C)
        self.ret_65d30 = 0          # 0x65D30's answer (the intro update's loop gate wants 8)
        hooks = {0x84C80: self._game_object, 0x84C50: self._release_object, 0x43F50: lambda: self._return(0, 0x10),
                 0xF9310: lambda: self._return(0), 0x4A400: lambda: self._return(0, 4),
                 0x65D30: lambda: self._return(self.ret_65d30)}
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
        if self.uc.reg_read(UC_X86_REG_EIP) != self.STOP:
            raise AssertionError(f'{address:#x}: exhausted {budget} instructions')
        return self.uc.reg_read(UC_X86_REG_EAX)

    def main_heap(self, largest):
        size = largest
        for _ in range(4):
            self.call(0x48640, ecx=MAIN_HEAP, edx=self.MAIN, args=(size,))
            got = self.call(0x48960, ecx=MAIN_HEAP)
            if got == largest:
                return
            size += largest - got
        raise AssertionError(f'could not model a {largest:,}-byte largest free block (got {got:,})')

    @staticmethod
    def _signed(value):
        return value - (1 << 32) if value & 0x80000000 else value

    def setup_game(self, room, *, region, home=TEAM_BAL, away=TEAM_HOU):
        """One game setup at a main heap whose largest free block is `room`; region = K128's >64 MB region present."""
        home, away = self.teams + home * 500, self.teams + away * 500
        for address, value in ((0xE576A0, 0), (0xE5FF80, 4), (0xB9C290, 0), (0xB9E230, 1), (0xE5FFE4, 0),
                               (0xE5FE64, self.word(home + 0x114)), (0xB018B8, REGION[0] if region else 0),
                               (0xB018BC, REGION[1] if region else 0)):
            self.put(address, value)
        self.call(pr.STAGE_VA, ecx=away, edx=home)
        self.main_heap(room)
        export = self.call(0xC0B50, ecx=0xB30864, edx=0xB30A58, args=(self.word(0xE5FE64),))
        ok = self.call(0x84EB0, ecx=0x180000, edx=0x20000)
        got = dict(room=room, ok=ok, export=export, block=self.word(BLOCK_SIZE), left=self.word(BLOCK_LEFT))
        if ok != 1:
            return got
        self.call(0x125700)
        got.update(heap_a=self._signed(self.call(0x48960, ecx=HEAP_A)),
                   heap_b=self._signed(self.call(0x48960, ecx=HEAP_B)),
                   heap_b_free=self._signed(self.word(HEAP_B + 0x88)),
                   director=self.call(0x48700, ecx=HEAP_B, edx=DIRECTOR),
                   main_free=self._signed(self.call(0x48960, ecx=MAIN_HEAP)))
        return got


def _fixtures_ready():
    return bool(RC_XBE and RC_XBE.is_file() and RC_ROST and RC_ROST.is_file()
                and importlib.util.find_spec('unicorn'))


RETAIL_XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) \
    / 'ESPN NFL 2K5 (USA)/default.xbe'


@unittest.skipUnless(RETAIL_XBE.is_file(), 'the conversion check needs the pinned retail XBE')
class EarlyConversionTests(unittest.TestCase):
    def test_turning_a_late_install_into_the_early_form_gives_the_fresh_early_install_byte_for_byte(self):
        """The witness disc's executable was made from the RC by early_from_late; on the K128 owner alone (retail
        plus its allocation) that conversion is exactly what a fresh build with k128_early writes, so the release
        build's K128 bytes are the witness's."""
        retail = RETAIL_XBE.read_bytes()
        self.assertEqual(hashlib.sha256(retail).hexdigest(), ps.RETAIL_SHA256)
        base, _ = space.apply(retail, k128.REQUESTS, scaleout=True)
        for roster_heap in (False, True):
            for require in (False, True):
                with self.subTest(roster_heap=roster_heap, require=require):
                    late, _ = k128.apply(base, roster_heap=roster_heap, require=require)
                    fresh, _ = k128.apply(base, roster_heap=roster_heap, early=True, require=require)
                    self.assertEqual(early_from_late(late), fresh)
                    self.assertEqual(k128.read_settings(fresh)['early'], True)


@unittest.skipUnless(_fixtures_ready(), 'heap B proofs need NFL2K5_B780_RC_XBE, NFL2K5_B780_RC_ROST and Unicorn')
class ReleaseCandidateHeapBTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rc = RC_XBE.read_bytes()
        if hashlib.sha256(cls.rc).hexdigest() != RC_XBE_SHA256:
            raise AssertionError('RC default.xbe hash mismatch')
        rost = RC_ROST.read_bytes()
        assert rost[:4] == b'ROST' and len(rost) == 827488, len(rost)
        cls.body = rost[0x20:]
        cls.early = early_from_late(cls.rc)

    def setup(self, xbe, room, *, region=True, **kw):
        return Machine(xbe, self.body).setup_game(room, region=region, **kw)

    def needed_room(self, xbe, *, region=True, lo=1300000, hi=1700000):
        """The smallest main-heap room (128-byte steps) at which DIR_INTRO's load gets memory."""
        lo, hi = lo & ~127, (hi + 127) & ~127
        self.assertEqual(self.setup(xbe, lo, region=region).get('director', 0), 0)
        self.assertNotEqual(self.setup(xbe, hi, region=region).get('director', 0), 0)
        while hi - lo > 128:
            mid = ((lo + hi) // 2) & ~127
            if self.setup(xbe, mid, region=region).get('director', 0):
                hi = mid
            else:
                lo = mid
        return hi

    # -- the measurement, reproduced ------------------------------------------------------------------------------------
    def test_the_rc_reproduces_the_lab_heap_b_and_the_null_director_at_baltimore(self):
        self.assertEqual(k128.read_settings(self.rc), {'status': 'applied', 'k128': True, 'roster_heap': True,
                                                       'early': False, 'require_128': True})
        got = self.setup(self.rc, LAB_ROOM_RC)
        self.assertEqual(got['block'], LAB_ROOM_RC - 0x20000, got)          # 1,364,864 B, the lab's in-game block
        self.assertEqual(got['heap_a'] + 128, 1343360, got)                 # the lab's heap A capacity
        self.assertEqual(got['heap_b_free'], LAB_HEAP_B_CAP, got)           # the lab's heap B: 6,400 B ...
        self.assertEqual(got['heap_b'], LAB_HEAP_B_LARGEST, got)            # ... largest allocation 6,272 B
        self.assertEqual(got['director'], 0, got)                           # DIR_INTRO's NULL at 0x166745

    def test_the_rc_needs_67_kb_more_room_than_the_lab_saw(self):
        need = self.needed_room(self.rc)
        self.assertEqual(need, 1563392, need)          # the game's heap works in 128-byte units: 1,563,264 B still fails
        self.assertEqual(need - LAB_ROOM_RC, 67456, need)

    def test_resident_growth_v08_to_rc_is_the_scaleout_section(self):
        self.assertEqual(resident_bytes(self.rc), RESIDENT_RC)
        rows = [a for a in space.layout(self.rc)['allocations'] if a['owner'] == 'nfl2k5_history_screen']
        self.assertEqual(sum(a['size'] for a in rows), HISTORY_SCREEN_BYTES)

    def test_history_off_alone_does_not_fit_dir_intro_at_baltimore(self):
        # mitigation (c): the History screen's 55,360 B come back as at most 14 pages of main heap; DIR_INTRO still
        # does not fit at the lab's Baltimore setup (it needs 67,392 B)
        got = self.setup(self.rc, LAB_ROOM_RC + 14 * 4096)
        self.assertEqual(got['director'], 0, got)
        self.assertLess(got['heap_b_free'], DIRECTOR + 128, got)

    # -- the fix: the K128 early form ---------------------------------------------------------------------------------
    def test_the_early_form_is_the_late_install_plus_the_early_bit_with_0x327d1_retail(self):
        self.assertEqual(hashlib.sha256(self.early).hexdigest(), RC_EARLY_XBE_SHA256)
        self.assertEqual(len(self.early), len(self.rc))
        self.assertEqual(k128.read_settings(self.early), {'status': 'applied', 'k128': True, 'roster_heap': True,
                                                          'early': True, 'require_128': True})
        self.assertEqual(XbeImage(self.early).read(k128.HOOK2_VA, 10), k128.RETAIL_HOOK2)
        self.assertEqual(k128.decode_entry(self.early), k128.decode_entry(self.rc))     # the 128 MB entry either way
        self.assertEqual(resident_bytes(self.early), resident_bytes(self.rc))           # no section grows
        code_va = k128.allocations(self.rc)['code']['va']
        changed = [i for i in range(len(self.rc)) if self.rc[i] != self.early[i]]
        hook = rdata.offset_of(self.rc, k128.HOOK2_VA)
        blob = rdata.offset_of(self.rc, code_va)
        header = struct.unpack_from('<I', self.rc, 0x108)[0]
        directory = [a for a in space.layout(self.rc)['allocations'] if a['owner'] == 'nfl2k5_xbe_space_directory']
        dir_ranges = [(rdata.offset_of(self.rc, a['va']), a['size']) for a in directory]
        end_imm = blob + k128.EARLY_END_IMM_OFFSET
        for i in changed:
            self.assertTrue(i < header or hook <= i < hook + 10 or end_imm <= i < end_imm + 4
                            or blob + k128.EARLY_OFFSET <= i < blob + k128.CODE_SIZE
                            or any(o <= i < o + n for o, n in dir_ranges), hex(i))
        # before the early entry (the stubs, the roster heap pick and the in-game block cap) only the end page of
        # MiAddPhysicalPages differs: 0x7FF0 for 0x8000, so the top 64 KB never reaches the free lists
        self.assertEqual(self.early[blob:end_imm], self.rc[blob:end_imm])
        self.assertEqual(struct.unpack_from('<I', self.early, end_imm)[0], k128.EARLY_LAST_PFN)
        self.assertEqual(struct.unpack_from('<I', self.rc, end_imm)[0], 0x8000)
        self.assertEqual(self.early[end_imm + 4:blob + k128.EARLY_OFFSET], self.rc[end_imm + 4:blob + k128.EARLY_OFFSET])
        self.assertEqual(len(changed), 196)

    def test_with_the_early_forms_arena_heap_b_is_retail_sized_and_dir_intro_fits_with_margin(self):
        for room in (LAB_ROOM_RC + EARLY_ARENA_GAIN, LAB_ROOM_RC + 0x40000):
            with self.subTest(room=room):
                got = self.setup(self.early, room)
                self.assertEqual(got['block'], 0x180000, got)                     # the cap: the block stops at 1.5 MB
                self.assertEqual(got['heap_a'] + 128, 1343360, got)
                self.assertGreaterEqual(got['heap_b_free'], 214000, got)          # retail heap B is 214,656 B
                self.assertNotEqual(got['director'], 0, got)
                self.assertGreaterEqual(got['heap_b_free'] - (DIRECTOR + 128), 140000, got)   # DIR_INTRO's margin
        # the cap holds from a room of 0x1A0000: any arena gain of 208,320 B or more gives the same heaps
        self.assertEqual(self.setup(self.early, 0x1A0000)['block'], 0x180000)
        self.assertLess(0x1A0000 - LAB_ROOM_RC, EARLY_ARENA_GAIN // 50)

    def test_the_early_form_runs_the_same_in_game_block_code_as_the_late_form(self):
        # the early form changes only where the upper 64 MB arrives; at any room both executables give the same heaps
        for room in (LAB_ROOM_RC, LAB_ROOM_RC + 67456, 0x1A0000, LAB_ROOM_RC + EARLY_ARENA_GAIN):
            for region in (True, False):
                with self.subTest(room=room, region=region):
                    self.assertEqual(self.setup(self.early, room, region=region),
                                     self.setup(self.rc, room, region=region))

    def test_at_64_mb_both_forms_keep_the_retail_block_size(self):
        # no >64 MB region (64 MB or another kernel): the block is the retail largest free minus 128 KB, uncapped
        room = 0x1A0000 + 0x40000
        for xbe in (self.rc, self.early):
            got = self.setup(xbe, room, region=False)
            self.assertEqual(got['block'], room - 0x20000, got)

    def test_the_arena_init_builds_the_main_heap_over_the_largest_contiguous_block_less_2_mib(self):
        """0x326E0 on the RC's own code, XPhysicalAlloc (0x20694) modelled as 'succeeds up to L bytes': the arena the
        main heap is built over ([0xB018B0]..[0xB018B4], read at 0x3907F) is L - [0xA6D324] (2 MiB), page-rounded, so
        every page the XBE keeps resident is a page less main heap. Run up to K128's hook site 0x327D1 (both forms)."""
        import unicorn as uni
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP
        base = 0x81000000
        self.assertEqual(struct.unpack('<I', XbeImage(self.rc).read(0xA6D324, 4))[0], 0x200000)
        sizes = {}
        for xbe in (self.rc, self.early):
            for largest in (0x00400000, 0x00400000 - 61440, 0x00400000 - 61440 - 1):
                uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
                top = (0x10000 + struct.unpack_from('<I', xbe, 0x10C)[0] + 0xFFFF) & ~0xFFFF
                uc.mem_map(0x10000, top - 0x10000)
                for section in ps._sections(xbe):
                    uc.mem_write(section.virtual_address, xbe[section.raw_offset:section.raw_offset + section.raw_size])
                uc.mem_map(0x03000000, 0x10000)
                uc.mem_map(base, 0x00400000)
                word = lambda a: struct.unpack('<I', uc.mem_read(a, 4))[0]

                def stdcall_return(value, args):
                    esp = uc.reg_read(UC_X86_REG_ESP)
                    uc.reg_write(UC_X86_REG_EAX, value)
                    uc.reg_write(UC_X86_REG_EIP, word(esp))
                    uc.reg_write(UC_X86_REG_ESP, esp + 4 + 4 * args)

                def alloc(_uc, _a, _s, limit):      # XPhysicalAlloc(size, highest, alignment, protect)
                    size = word(uc.reg_read(UC_X86_REG_ESP) + 4)
                    stdcall_return(base if size <= limit else 0, 4)

                uc.hook_add(uni.UC_HOOK_CODE, alloc, begin=0x20694, end=0x20694, user_data=largest)
                uc.hook_add(uni.UC_HOOK_CODE, lambda *_: stdcall_return(1, 1), begin=0x2071A, end=0x2071A)  # XPhysicalFree
                uc.hook_add(uni.UC_HOOK_CODE, lambda *_: stdcall_return(0, 1), begin=0x3783B0, end=0x3783B0)  # lock init
                uc.mem_write(0xB018C0, struct.pack('<I', 0))
                uc.reg_write(UC_X86_REG_ESP, 0x03008000)
                uc.mem_write(0x03008000, struct.pack('<I', 0x03100000))
                uc.emu_start(k128.ARENA_INIT_VA, k128.HOOK2_VA, count=5000000)
                self.assertEqual(uc.reg_read(UC_X86_REG_EIP), k128.HOOK2_VA)
                arena, size = word(0xB018B0), word(0xB018C8)
                self.assertEqual((arena, word(0xB018CC), word(0xB018D0)), (base, base, base + size))
                self.assertEqual(size, (largest - 0x200000) & ~0xFFF)
                sizes[(xbe is self.early, largest)] = size
        for early in (False, True):
            self.assertEqual(sizes[(early, 0x00400000)] - sizes[(early, 0x00400000 - 61440)], 61440)
            self.assertEqual(sizes[(early, 0x00400000)] - sizes[(early, 0x00400000 - 61441)], 65536)


@unittest.skipUnless(_fixtures_ready() and V08_XBE and V08_XBE.is_file() and V08_BODY and V08_BODY.is_file(),
                     'the v0.8 comparison needs NFL2K5_V08_XBE and NFL2K5_V08_ROST_BODY too')
class V08ComparisonTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.v08 = V08_XBE.read_bytes()
        if hashlib.sha256(cls.v08).hexdigest()[:16] != V08_XBE_SHA256:
            raise AssertionError('v0.8 default.xbe hash mismatch')
        cls.body = V08_BODY.read_bytes()

    def test_v08_resident_is_15_pages_smaller_and_still_short_at_baltimore(self):
        self.assertEqual(resident_bytes(self.v08), RESIDENT_V08)
        self.assertEqual(RESIDENT_RC - RESIDENT_V08, 61440)
        # EMU1's v0.8 control (H1V8B, same Baltimore setup): largest free 1,555,456 B at setup (59,520 B more than the
        # RC: 61,440 B of resident pages less 1,920 B of other main-heap use), block 1,424,384 B, heap B 66,304 B
        # (largest 66,176 B), DIR_INTRO NULL: v0.8, as shipped, loops at Baltimore at 128 MiB too
        got = Machine(self.v08, self.body).setup_game(LAB_ROOM_V08, region=True)
        self.assertEqual(got['block'], 1424384, got)
        self.assertEqual((got['heap_b_free'], got['heap_b']), (66304, 66176), got)
        self.assertEqual(got['director'], 0, got)
        self.assertEqual(LAB_ROOM_V08 - LAB_ROOM_RC, 61440 - 1920)


if __name__ == '__main__':
    unittest.main()
