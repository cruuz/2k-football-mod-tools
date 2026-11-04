"""b780 hunt3: Weekly Prep's Player Results screen keeps its own numbers under the Player Progress owner.

Retail draws two Front Office style screens through one value getter. Player Progress (descriptor 0x551800, event 4
0x365F70) and Weekly Prep's Player Results, titled "Preparation Results" (descriptor 0x551A40, reached from the Weekly
Prep menu row at 0x52032C, event 4 0x365F90) share the event 8 draw handler 0x365CE0. That handler calls the getter
0x365B20 (0x365E7A, 0x365ECA, 0x365F0E, and 0x365C7A, which fills the "previously" cache at 0xCC2390) and reads the
third column label at 0x365E34. The getter tells the screens apart by [0xCC2388]: 0x365F70 stores 0, 0x365F90 stores 1,
and with 1 the getter takes the practice values (0x2ABE60). The Player Progress owner (beta-78 on, released v0.8 and
the v0.9 RC) replaced the getter and the label with code that never read 0xCC2388. Once the season baseline existed,
Player Results showed the season baseline and the season change instead of what the practice did (and the label hook
read Player Progress's view byte there too).

The fix: when [0xCC2388] is not 0 the value hook runs the retail getter (ECX, the stack and the return address
untouched) and the label hook leaves the retail label. Player Progress is exactly as before.

Proof level: offline. The sharing is read from the retail executable; the owner's cave runs under Unicorn with the
same mocks as test_nfl2k5_player_progress_screen; and the owner applied to the retail executable runs whole (the
retail getter and the retail cache fill natively, only the list, roster and practice helpers as fixtures). Nothing
here is an in-game capture.
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_player_progress_screen as screen  # noqa: E402
from mod_editor.core import nfl2k5_player_progression as record  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

MODE = 0xCC2388                      # retail: 0 Player Progress, 1 Preparation Results
PROGRESS, PREP = 0x551800, 0x551A40  # the two screen descriptors
DRAW, PROGRESS_INIT, PREP_INIT, GETTER, CACHE_FILL = 0x365CE0, 0x365F70, 0x365F90, 0x365B20, 0x365C70
RETAIL_LABEL = 0xEB92D8              # "+/- Change"

CODE, DATA = 0x03000000, 0x03010000
ROSTER, TEAM, P0, P1, LIST, ARRAY = 0x02000000, 0x02010000, 0x02011000, 0x02011100, 0x02020000, 0x02021000
MANAGER = 0x02040000
STACK, SENTINEL, TARGETS = 0x04000000, 0x04080000, 0x06000000
RECORD = DATA + screen.RECORD_VA_DELTA
GUARD = bytes.fromhex("833d") + struct.pack("<I", MODE) + b"\x00"   # cmp dword [0xCC2388],0


def _retail():
    from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
    return retail_xbe()


class StaticTests(unittest.TestCase):
    """Runs everywhere: both hooks of the owner check the screen before anything else."""

    def test_both_hooks_read_the_screen_mode_first(self):
        labels = screen.labels()
        code = screen.code_for(0x14DA000, 0x14BB000)
        value, header = labels["value"], labels["header"]
        self.assertEqual(code[value:value + len(GUARD)], GUARD)
        self.assertEqual(code[value + len(GUARD):value + len(GUARD) + 2], b"\x0f\x85")      # jne (32-bit)
        # the label hook keeps loading the retail label first, then leaves it for Preparation Results
        self.assertEqual(code[header:header + 5], b"\xba" + struct.pack("<I", RETAIL_LABEL))
        self.assertEqual(code[header + 5:header + 5 + len(GUARD)], GUARD)
        self.assertEqual(code[header + 5 + len(GUARD)], 0x75)                              # jne (8-bit)
        # the hosted variant (the pack's franchise footer host) is the same cave
        hosted = screen.hosted_code_for(0x14DA000, 0x14BB000)
        self.assertEqual(hosted[value:value + len(GUARD)], GUARD)
        self.assertEqual(hosted[header + 5:header + 5 + len(GUARD)], GUARD)


class RetailSharingTests(unittest.TestCase):
    """The two screens and their one getter, read from the retail executable."""

    @classmethod
    def setUpClass(cls):
        cls.image = XbeImage(_retail())

    def u32(self, va):
        return struct.unpack("<I", self.image.read(va, 4))[0]

    def utf16(self, va):
        raw = self.image.read(va, 80)
        end = next(i for i in range(0, len(raw), 2) if raw[i:i + 2] == b"\0\0")
        return raw[:end].decode("utf-16-le")

    def events(self, descriptor):
        table, out = self.u32(descriptor + 4), {}
        for k in range(16):
            event, slot = struct.unpack("<II", self.image.read(table + 8 * k, 8))
            if (event, slot) == (0, 0):
                break
            out[event] = self.u32(slot + 4)
        return out

    def test_the_two_screens_share_the_draw_handler(self):
        self.assertEqual(self.utf16(self.u32(PROGRESS)), "Player Progress")
        self.assertEqual(self.utf16(self.u32(PREP)), "Preparation Results")
        progress, prep = self.events(PROGRESS), self.events(PREP)
        self.assertEqual((progress[8], prep[8]), (DRAW, DRAW))
        self.assertEqual((progress[4], prep[4]), (PROGRESS_INIT, PREP_INIT))
        # the Weekly Prep menu row "Player Results" opens Preparation Results
        self.assertEqual(self.utf16(self.u32(0x52032C)), "Player Results")
        self.assertEqual(self.u32(0x520330), PREP)

    def test_each_screen_sets_the_mode_and_the_getter_reads_it(self):
        mode = struct.pack("<I", MODE)
        self.assertEqual(self.image.read(PROGRESS_INIT + 3, 10), b"\xc7\x05" + mode + struct.pack("<I", 0))
        self.assertEqual(self.image.read(PREP_INIT + 3, 10), b"\xc7\x05" + mode + struct.pack("<I", 1))
        self.assertEqual(self.image.read(0x365B7D, 6), b"\x8b\x0d" + mode)      # mov ecx,[0xCC2388]
        self.assertEqual(self.image.read(0x365BEB, 5), b"\xa1" + mode)          # mov eax,[0xCC2388]

    def test_the_shared_draw_calls_the_getter_and_reads_the_label(self):
        for site in (0x365E7A, 0x365ECA, 0x365F0E, 0x365C7A):
            raw = self.image.read(site, 5)
            self.assertEqual((raw[0], site + 5 + struct.unpack("<i", raw[1:])[0]), (0xE8, GETTER), hex(site))
        self.assertEqual(self.image.read(screen.SITE_HEADER[0], 5), screen.SITE_HEADER[1])
        self.assertEqual(screen.SITE_VALUE[0], GETTER)
        # 0x365C70 (called by the draw at 0x365D41) caches the "previously" column for every row
        raw = self.image.read(0x365D41, 5)
        self.assertEqual(0x365D46 + struct.unpack("<i", raw[1:])[0], CACHE_FILL)
        self.assertEqual(self.image.read(0x365C7F, 7), bytes.fromhex("8904b5") + struct.pack("<I", 0xCC2390))


@unittest.skipIf(uc is None, "unicorn is not installed")
class NativeTests(unittest.TestCase):
    """The owner's cave under Unicorn (mocks as in test_nfl2k5_player_progress_screen)."""

    @classmethod
    def setUpClass(cls):
        cls.labels = screen.labels()
        cls.blob = screen.code_for(CODE, DATA, (TARGETS, TARGETS + 0x10, TARGETS + 0x20))

    def machine(self, mode):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for base, size in ((ROSTER, 0x100000), (CODE, 0x2000), (DATA, 0x10000), (TARGETS, 0x1000),
                           (0xB72000, 0x1000), (0xB37000, 0x2000), (0xE57000, 0x1000), (0xC4000, 0x4000),
                           (0xF3000, 0x2000), (0x170000, 0x2000), (0xE6000, 0x2000), (0x247000, 0x2000),
                           (0x133000, 0x2000), (0x14F000, 0x2000), (0x365000, 0x2000), (0xCC2000, 0x1000),
                           (STACK, 0x10000)):
            m.mem_map(base, size)
        m.mem_write(CODE, self.blob)
        m.mem_write(DATA, bytes(0x10000))
        m.mem_write(ROSTER + 0x1C, struct.pack("<I", TEAM))
        m.mem_write(0xB72918, struct.pack("<I", ROSTER))
        m.mem_write(TEAM, struct.pack("<II", P0, P1))
        m.mem_write(TEAM + 0x11C, bytes([2]))
        for index, player in enumerate((P0, P1)):
            m.mem_write(player, bytes(0x54))
            m.mem_write(player + 4, struct.pack("<H", 10 + index))
            m.mem_write(player + 0x20, struct.pack("<I", (index + 1) << 3))
            for field in range(record.RATING_COUNT):
                m.mem_write(player + 0x36 + field, bytes([50 + field]))
        m.mem_write(LIST, bytes(0x108))
        m.mem_write(LIST + 0xA4, struct.pack("<I", 1))
        m.mem_write(LIST + 0x40, struct.pack("<I", ARRAY))
        m.mem_write(ARRAY, struct.pack("<I", P0))
        m.mem_write(0xE576A4, struct.pack("<I", 8))
        m.mem_write(0xE576B4, struct.pack("<I", 5))
        m.mem_write(0xE576B8, struct.pack("<I", 2027))
        m.mem_write(0xE576A0, struct.pack("<I", 2))
        m.mem_write(0xB72808, struct.pack("<I", 0xB0000))

        def ret_imm(va, value):
            m.mem_write(va, b"\xb8" + struct.pack("<I", value) + b"\xc3")
        ret_imm(0xC4D70, TEAM)
        ret_imm(0xF31B0, LIST)
        ret_imm(0x170510, 0)
        ret_imm(0xC4BB0, 8)
        ret_imm(0xC4B80, 2)
        m.mem_write(0xE6660, b"\xa1\x20\x29\xb7\x00\xc3")
        m.mem_write(0xB72920, struct.pack("<I", 77))
        m.mem_write(0x247B20, b"\xc3")
        m.mem_write(0x14FCD0, b"\xf4")
        m.mem_write(0x365B00, b"\x0f\xb6\x41\x36\xc3")      # the per-attribute helper: row 5 reads rating 0
        # The retail getter's body after the displaced prologue (push ebx ; mov ebx,[esp+0xc]): report what it was
        # handed. EAX = 0x5000 + ECX's low byte + the row it read into EBX * 8, then pop ebx ; ret 0xc.
        m.mem_write(0x365B25, bytes.fromhex("0fb6c1" "8d04d8" "0500500000" "5b" "c20c00"))
        ret_imm(TARGETS, 0x165B0)
        m.mem_write(TARGETS + 0x10, b"\xc3")
        m.mem_write(TARGETS + 0x20, b"\xc3")
        m.mem_write(MODE, struct.pack("<I", mode))
        return m

    def run_label(self, m, label, ecx=0, stack=()):
        sp = STACK + 0x8000
        for value in reversed(stack):
            sp -= 4
            m.mem_write(sp, struct.pack("<I", value))
        sp -= 4
        m.mem_write(sp, struct.pack("<I", SENTINEL))
        for reg in (x86.UC_X86_REG_EAX, x86.UC_X86_REG_EDX, x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI,
                    x86.UC_X86_REG_EDI, x86.UC_X86_REG_EBP):
            m.reg_write(reg, 0)
        m.reg_write(x86.UC_X86_REG_ECX, ecx)
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        try:
            m.emu_start(CODE + self.labels[label], SENTINEL, count=200000, timeout=5_000_000)
        except uc.UcError as exc:
            self.fail(f"{label} faulted at 0x{m.reg_read(x86.UC_X86_REG_EIP):x}: {exc}")
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EIP), SENTINEL)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESP), sp + 4 + 4 * len(stack))   # ret 0xc / ret, balanced
        return m.reg_read(x86.UC_X86_REG_EAX), m.reg_read(x86.UC_X86_REG_EDX)

    def value(self, m, mode, row):
        return self.run_label(m, "value", ecx=MANAGER, stack=(mode, row, 1))[0]

    def season_with_a_practice_gain(self, mode):
        """A captured season baseline (speed 50), then the live speed rises to 55 (this week's practice)."""
        m = self.machine(mode)
        self.run_label(m, "capture_baseline")
        self.assertEqual(bytes(m.mem_read(RECORD, 4)), record.RECORD_MAGIC)
        m.mem_write(P0 + 0x36, bytes([55]))
        return m

    def test_player_progress_still_shows_the_season(self):
        m = self.season_with_a_practice_gain(0)
        self.assertEqual(self.value(m, 0, 5), 50)    # previously = the season baseline
        self.assertEqual(self.value(m, 1, 5), 55)    # currently = live
        self.assertEqual(self.value(m, 2, 5), 5)     # change since the season began

    def test_preparation_results_runs_the_retail_getter(self):
        m = self.season_with_a_practice_gain(1)
        for column in (0, 1, 2):
            for row in (0, 5):
                with self.subTest(column=column, row=row):
                    # the retail getter got the screen manager in ECX and the row from the caller's stack
                    self.assertEqual(self.value(m, column, row), 0x5000 + (MANAGER & 0xFF) + row * 8)

    def test_the_label_is_retail_on_preparation_results(self):
        for mode, stepped in ((0, True), (1, False)):
            m = self.machine(mode)
            m.mem_write(RECORD, struct.pack("<IBBHB", screen.RECORD_MAGIC, 1, 3, 2027, 30) + bytes([6, 3, 3]))
            m.mem_write(DATA, bytes([2]))                # a view stepped to "2 Wks Ago" on Player Progress
            edx = self.run_label(m, "header")[1]
            if stepped:
                self.assertEqual(edx, CODE + screen._TEXT_OFFSET + 24)
            else:
                self.assertEqual(edx, RETAIL_LABEL)



@unittest.skipIf(uc is None, "unicorn is not installed")
class AppliedExecutableTests(unittest.TestCase):
    """The owner applied to the retail executable, mapped whole. The getter site 0x365B20, the retail getter after it
    and the retail cache fill 0x365C70 run natively; only the list, roster and practice helpers below are fixtures.

    The player: a season baseline of 50 (captured at the season start), 52 after last week, 55 after this week's
    practice. Weekly Prep's practice record (0x2ABE60 puts the pre-practice ratings on the player, 0x2AB8F0 takes
    them off again) holds 52. Player Progress shows the season (50, 55, +5); Player Results must show the practice
    (52, 55, +3)."""

    BASELINE, BEFORE_PRACTICE, LIVE = 50, 52, 55
    SCRATCH = 0x06100000            # practice stub state: saved rating, call count
    ROW = 5

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        applied, receipt = screen.apply(cls.retail)
        if receipt.get("status") != "applied":
            raise unittest.SkipTest(f"the owner did not apply: {receipt}")
        cls.applied = applied
        cls.code_va, cls.data_va = int(receipt["code_va"], 16), int(receipt["data_va"], 16)
        cls.labels = screen.labels()
        image = XbeImage(applied)
        cls.image = image
        # what beta-78 to the v0.9 RC run: the same image without the two guards
        value = cls.code_va + cls.labels["value"]
        header = cls.code_va + cls.labels["header"] + 5
        unguarded = bytearray(applied)
        for va, size in ((value, len(GUARD) + 6), (header, len(GUARD) + 2)):
            off = image.offset(va, size)
            unguarded[off:off + size] = b"\x90" * size
        cls.unguarded = bytes(unguarded)

    def machine(self, payload, mode):
        image = XbeImage(payload)
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        pages = sorted({p for s in image.sections for p in range(s.start & ~0xFFF, (s.end + 0xFFF) & ~0xFFF, 0x1000)})
        start = None
        for i, page in enumerate(pages):
            if start is None:
                start = page
            if i + 1 == len(pages) or pages[i + 1] != page + 0x1000:
                m.mem_map(start, page + 0x1000 - start)
                start = None
        for s in image.sections:
            m.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for base, size in ((ROSTER, 0x100000), (TARGETS, 0x1000), (self.SCRATCH, 0x1000), (STACK, 0x10000),
                           (SENTINEL, 0x1000)):
            m.mem_map(base, size)
        # the roster: two players of the user team
        m.mem_write(ROSTER + 0x1C, struct.pack("<I", TEAM))
        m.mem_write(0xB72918, struct.pack("<I", ROSTER))
        m.mem_write(TEAM, struct.pack("<II", P0, P1))
        m.mem_write(TEAM + 0x11C, bytes([2]))
        for index, player in enumerate((P0, P1)):
            m.mem_write(player, bytes(0x54))
            m.mem_write(player + 4, struct.pack("<H", 10 + index))
            m.mem_write(player + 0x20, struct.pack("<I", (index + 1) << 3))
            m.mem_write(player + 0x24, struct.pack("<I", 0x100))   # retail getter: a rated player (bits 8..12)
            for field in range(record.RATING_COUNT):
                m.mem_write(player + 0x36 + field, bytes([50 + field]))
        m.mem_write(LIST, bytes(0x108))
        m.mem_write(LIST + 0xA4, struct.pack("<I", 1))
        m.mem_write(LIST + 0x40, struct.pack("<I", ARRAY))
        m.mem_write(ARRAY, struct.pack("<I", P0))
        m.mem_write(0xE576A4, struct.pack("<I", 8))       # regular season
        m.mem_write(0xE576B4, struct.pack("<I", 5))
        m.mem_write(0xE576B8, struct.pack("<I", 2027))
        m.mem_write(0xE576A0, struct.pack("<I", 2))
        m.mem_write(0xB72808, struct.pack("<I", 0xB0000))
        m.mem_write(0xB72920, struct.pack("<I", 77))
        m.mem_write(0xE3C0A0, struct.pack("<I", TEAM))    # read by the retail 0x13EC80

        def ret_imm(va, value):
            m.mem_write(va, b"\xb8" + struct.pack("<I", value) + b"\xc3")
        ret_imm(0xC4D70, TEAM)
        ret_imm(0xF31B0, LIST)
        ret_imm(0x170510, 0)
        ret_imm(0xC4BB0, 8)
        ret_imm(0xC4B80, 2)
        m.mem_write(0xE6660, b"\xa1\x20\x29\xb7\x00\xc3")
        m.mem_write(0x247B20, b"\xc3")
        m.mem_write(0x14FCD0, b"\xf4")
        m.mem_write(0x365B00, b"\x0f\xb6\x41\x36\xc3")    # the per-attribute helper: every row reads rating 0
        save, count = struct.pack("<I", self.SCRATCH), struct.pack("<I", self.SCRATCH + 4)
        # 0x2ABE60 (ecx = player, edx = team, one stack word): put the pre-practice rating on the player
        m.mem_write(0x2ABE60, b"\x8a\x41\x36" + b"\xa2" + save + b"\xc6\x41\x36" + bytes([self.BEFORE_PRACTICE])
                    + b"\xff\x05" + count + b"\xc2\x04\x00")
        # 0x2AB8F0: take it off again
        m.mem_write(0x2AB8F0, b"\xa0" + save + b"\x88\x41\x36" + b"\xc2\x04\x00")
        ret_imm(TARGETS, 0x165B0)
        m.mem_write(MODE, struct.pack("<I", mode))
        return m

    def exec_at(self, m, va, ecx=0, edi=0, stack=()):
        sp = STACK + 0x8000
        for value in reversed(stack):
            sp -= 4
            m.mem_write(sp, struct.pack("<I", value))
        sp -= 4
        m.mem_write(sp, struct.pack("<I", SENTINEL))
        for reg in (x86.UC_X86_REG_EAX, x86.UC_X86_REG_EDX, x86.UC_X86_REG_EBX, x86.UC_X86_REG_ESI,
                    x86.UC_X86_REG_EBP):
            m.reg_write(reg, 0)
        m.reg_write(x86.UC_X86_REG_ECX, ecx)
        m.reg_write(x86.UC_X86_REG_EDI, edi)
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        try:
            m.emu_start(va, SENTINEL, count=2_000_000, timeout=20_000_000)
        except uc.UcError as exc:
            self.fail(f"0x{va:x} faulted at 0x{m.reg_read(x86.UC_X86_REG_EIP):x}: {exc}")
        self.assertEqual(m.reg_read(x86.UC_X86_REG_EIP), SENTINEL)
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESP), sp + 4 + 4 * len(stack))
        return m.reg_read(x86.UC_X86_REG_EAX)

    def season(self, payload, mode):
        m = self.machine(payload, mode)
        self.exec_at(m, self.code_va + self.labels["capture_baseline"])
        self.assertEqual(bytes(m.mem_read(self.data_va + screen.RECORD_VA_DELTA, 4)), record.RECORD_MAGIC)
        self.assertEqual(m.mem_read(P0 + 0x36, 1)[0], self.BASELINE)
        m.mem_write(P0 + 0x36, bytes([self.LIVE]))
        return m

    def columns(self, m):
        """The three cells of one row as the shared draw asks for them: getter(column, row, 1) on the screen manager."""
        return tuple(self.exec_at(m, GETTER, ecx=MANAGER, stack=(column, self.ROW, 1)) for column in (0, 1, 2))

    def practice_calls(self, m):
        return struct.unpack("<I", m.mem_read(self.SCRATCH + 4, 4))[0]

    def test_the_image_reads_applied_and_the_site_enters_the_value_hook(self):
        self.assertEqual(screen.status(self.applied), "applied")
        raw = self.image.read(GETTER, 5)
        self.assertEqual(GETTER + 5 + struct.unpack("<i", raw[1:])[0], self.code_va + self.labels["value"])

    def test_player_progress_shows_the_season(self):
        m = self.season(self.applied, 0)
        self.assertEqual(self.columns(m), (self.BASELINE, self.LIVE, self.LIVE - self.BASELINE))
        self.assertEqual(self.practice_calls(m), 0)

    def test_player_results_shows_the_practice(self):
        m = self.season(self.applied, 1)
        self.exec_at(m, CACHE_FILL, edi=MANAGER)          # the draw's own cache fill: getter(0, row, 0) for rows 0..26
        self.assertEqual(self.practice_calls(m), 27, "every row took the retail practice path")
        self.assertEqual(m.mem_read(P0 + 0x36, 1)[0], self.LIVE, "the practice ratings came off again")
        self.assertEqual(self.columns(m), (self.BEFORE_PRACTICE, self.LIVE, self.LIVE - self.BEFORE_PRACTICE))

    def test_without_the_guards_player_results_showed_the_season(self):
        """What beta-78 to the v0.9 RC run: the practice path is never taken and the season numbers show."""
        m = self.season(self.unguarded, 1)
        self.exec_at(m, CACHE_FILL, edi=MANAGER)
        self.assertEqual(self.practice_calls(m), 0)
        self.assertEqual(self.columns(m), (self.BASELINE, self.LIVE, self.LIVE - self.BASELINE))


if __name__ == "__main__":
    unittest.main()
