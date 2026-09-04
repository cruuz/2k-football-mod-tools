"""Home/away jerseys anywhere: the uniform rule block, the flip words and the four era handlers.

Shape tests need nothing; the retail tests need the extraction; the unicorn tests run the patched
routines (and the retail ones as a control) on the real image bytes with the two callees that leave
the routine stubbed (the era-number lookup and the name formatter)."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import nfl2k5_uniform_choice as uc  # noqa: E402

try:
    from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESI, UC_X86_REG_ESP
except Exception:  # noqa: BLE001
    Uc = None

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
SCRATCH = 0x02000000
SENTINEL = SCRATCH                    # a `nop` the handlers return to
STR_HOME = SCRATCH + 0x1000
STR_AWAY = SCRATCH + 0x1100
TEAM = SCRATCH + 0x10000
STACK = SCRATCH + 0x80000
FN_ERA_NUMBER = 0x000E2F20            # FUN_000e2f20(team, slot): stubbed to 0
FN_FORMAT = 0x0004A410                # the "%s%c%d.iff" formatter: stubbed to `ret 8`


class ShapeTests(unittest.TestCase):
    def test_every_site_keeps_its_size_and_the_code_fits(self) -> None:
        for mode in uc.MODES:
            for label, _va, before, after in uc.sites(mode):
                self.assertEqual(len(before), len(after), label)
        report = uc.code_report()
        self.assertLessEqual(report["rule_block_code_bytes"], uc.RULE_BLOCK_SIZE)
        for name, size in report["handler_code_bytes"].items():
            cap = uc.PREV_SIZE if name.endswith("prev") else uc.NEXT_SIZE
            self.assertLessEqual(size, cap, name)
        self.assertIsNone(report["cave"])

    def test_the_rule_form_is_one_instruction_and_nops(self) -> None:
        block = uc.rule_block_bytes("rule")
        self.assertEqual(block[:5], b"\xbe" + struct.pack("<I", uc.RULE_SWAP))
        self.assertEqual(block[5:], b"\x90" * (uc.RULE_BLOCK_SIZE - 5))
        self.assertEqual(uc.RULE_SWAP_VA, uc.RULE_BLOCK_VA + 1)

    def test_the_flip_words_sit_in_the_rdata_data_gap_beside_the_seven_on_seven_flag(self) -> None:
        from mod_editor.core import nfl2k5_seven_on_seven as seven
        for va in (uc.HOME_FLIP_VA, uc.AWAY_FLIP_VA, uc.AWAY_VALUE_VA):
            self.assertTrue(seven.FLAG_VA < va and va + 4 <= 0xA69980, hex(va))
        self.assertNotEqual(uc.HOME_FLIP_VA, uc.AWAY_FLIP_VA)

    def test_the_handlers_leave_the_retail_padding_before_their_neighbours(self) -> None:
        # the cave-reference gate merges changed runs closer than 8 bytes: keep 8 retail nops
        handlers = uc.handler_bytes()
        self.assertEqual(uc.HOME_PREV_VA + uc.PREV_SIZE + 8, uc.HOME_NEXT_VA)
        self.assertEqual(uc.AWAY_PREV_VA + uc.PREV_SIZE + 8, uc.AWAY_NEXT_VA)
        self.assertEqual(uc.HOME_NEXT_VA + uc.NEXT_SIZE + 13, 0xE3000)
        self.assertEqual(uc.AWAY_NEXT_VA + uc.NEXT_SIZE + 13, 0xE30E0)
        for name, body in handlers.items():
            self.assertEqual(body[-1], 0x90, name)

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(uc.status(b"XBEH" + b"\0" * 0x200), "foreign")
        self.assertIsNone(uc.applied_mode(b"XBEH" + b"\0" * 0x200))
        with self.assertRaises(uc.UniformChoiceError):
            uc.apply(b"XBEH" + b"\0" * 0x200, "choice")
        with self.assertRaises(uc.UniformChoiceError):
            uc.sites("both")


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()

    def test_status_apply_idempotent_and_foreign_for_both_forms(self) -> None:
        self.assertEqual(uc.status(self.retail), "retail")
        self.assertIsNone(uc.applied_mode(self.retail))
        for mode in uc.MODES:
            patched, receipt = uc.apply(self.retail, mode)
            self.assertEqual(uc.status(patched), "applied")
            self.assertEqual(uc.applied_mode(patched), mode)
            self.assertEqual(receipt["mode"], mode)
            self.assertGreater(receipt["changed_bytes"], 0)
            again, receipt2 = uc.apply(patched, mode)
            self.assertEqual(again, patched)
            self.assertTrue(receipt2.get("already_applied"))
            other = "rule" if mode == "choice" else "choice"
            with self.assertRaises(uc.UniformChoiceError):
                uc.apply(patched, other)
            tampered = bytearray(patched)
            tampered[uc._offset(patched, uc.RULE_BLOCK_VA + 3)] ^= 0x01
            self.assertEqual(uc.status(bytes(tampered)), "foreign")
        # a choice image with one handler put back to retail is foreign, not "rule"
        choice, _r = uc.apply(self.retail, "choice")
        half = bytearray(choice)
        off = uc._offset(choice, uc.HOME_NEXT_VA)
        half[off: off + uc.NEXT_SIZE] = uc.RETAIL_HOME_NEXT
        self.assertEqual(uc.status(bytes(half)), "foreign")

    def test_only_the_pinned_spans_change_and_the_text_digest_is_repinned(self) -> None:
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for mode in uc.MODES:
            patched, _r = uc.apply(self.retail, mode)
            spans = [(uc._offset(self.retail, va), len(after)) for _l, va, _b, after in uc.sites(mode)]
            text = _sections(self.retail)[0]
            for off in range(text.raw_offset, text.raw_offset + text.raw_size):
                if self.retail[off] != patched[off]:
                    self.assertTrue(any(a <= off < a + n for a, n in spans), f"{mode}: stray change at file 0x{off:x}")
            for section in _sections(patched):
                d = section.header_offset + 36
                self.assertEqual(patched[d: d + 20], section_digest(patched, section), section.index)
            # the eight retail nops between prev and next handlers, and the setters after next, are untouched
            for va in (uc.HOME_PREV_VA + uc.PREV_SIZE, uc.AWAY_PREV_VA + uc.PREV_SIZE):
                off = uc._offset(patched, va)
                self.assertEqual(patched[off: off + 8], b"\x90" * 8)
            for va in (0xE3000, 0xE30E0, 0xE2DA0):
                off = uc._offset(patched, va)
                self.assertEqual(patched[off: off + 16], self.retail[off: off + 16], hex(va))

    def test_order_independence_with_the_other_xbe_patches(self) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        a, _ = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, team_column=True, position_row=True, uniform_choice="choice")
        b1, _ = uc.apply(self.retail, "choice")
        b, _ = tt._apply_all(b1, None, catch_slider=False, returner_fix=True, team_column=True, position_row=True, uniform_choice="choice")
        self.assertEqual(a, b)
        from mod_editor.core import nfl2k5_returner_fix as returner
        c1, _ = returner.apply(self.retail)
        c, _ = tt._apply_all(c1, None, catch_slider=False, returner_fix=True, team_column=True, position_row=True, uniform_choice="choice")
        self.assertEqual(a, c)
        with self.assertRaises(Exception):
            tt._apply_all(b1, None, catch_slider=False, uniform_choice="rule")


def _sections_raw(xbe: bytes) -> list[tuple[int, int, int]]:
    base = struct.unpack_from("<I", xbe, 0x104)[0]
    count = struct.unpack_from("<I", xbe, 0x11C)[0]
    header = struct.unpack_from("<I", xbe, 0x120)[0] - base
    out = []
    for i in range(count):
        _flags, vaddr, _vsize, raw, rawsize, _name = struct.unpack_from("<IIIIII", xbe, header + i * 0x38)
        out.append((vaddr, raw, rawsize))
    return out


def _machine(image: bytes) -> "Uc":
    m = Uc(UC_ARCH_X86, UC_MODE_32)
    m.mem_map(0, 0x1000000)
    m.mem_map(SCRATCH, 0x100000)
    for vaddr, raw, rawsize in _sections_raw(image):
        m.mem_write(vaddr, image[raw: raw + rawsize])
    m.mem_write(SENTINEL, b"\x90" * 16)
    return m


def _dword(m: "Uc", va: int) -> int:
    return struct.unpack("<I", m.mem_read(va, 4))[0]


@unittest.skipUnless(XBE.is_file() and Uc is not None, "retail extraction or unicorn not present")
class LoaderEmulationTests(unittest.TestCase):
    """FUN_000615a0's rule block through both letter sites."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.images = {"retail": cls.retail, "rule": uc.apply(cls.retail, "rule")[0], "choice": uc.apply(cls.retail, "choice")[0]}

    def _letters(self, image: bytes, home: str, away: str, home_flip: int = 0, away_flip: int = 0) -> tuple[str, str, int]:
        m = _machine(image)
        m.mem_write(FN_ERA_NUMBER, b"\x31\xc0\xc3")                # xor eax,eax; ret
        m.mem_write(FN_FORMAT, b"\x31\xc0\xc2\x08\x00")            # xor eax,eax; ret 8
        m.mem_write(STR_HOME, home.encode("utf-16le") + b"\0\0")
        m.mem_write(STR_AWAY, away.encode("utf-16le") + b"\0\0")
        m.mem_write(uc.HOME_ABBR_PTR_VA, struct.pack("<I", STR_HOME))
        m.mem_write(uc.AWAY_ABBR_PTR_VA, struct.pack("<I", STR_AWAY))
        m.mem_write(uc.HOME_FLIP_VA, struct.pack("<I", home_flip))
        m.mem_write(uc.AWAY_FLIP_VA, struct.pack("<I", away_flip))
        m.mem_write(uc.AWAY_VALUE_VA, b"\xee\xee\xee\xee")        # stale scratch must not matter
        m.reg_write(UC_X86_REG_ESP, STACK)
        m.reg_write(UC_X86_REG_ESI, 0x5A5A5A5A)
        m.emu_start(uc.RULE_BLOCK_VA, uc.RULE_BLOCK_END_VA, count=10_000)
        swap_reg = m.reg_read(UC_X86_REG_ESI)
        m.emu_start(uc.RULE_BLOCK_END_VA, uc.AWAY_LETTER_CALL_VA, count=10_000)
        esp = m.reg_read(UC_X86_REG_ESP)
        self.assertEqual(esp, STACK - 8)
        away_letter = chr(struct.unpack("<H", m.mem_read(esp + 0x10, 2))[0])
        m.emu_start(uc.AWAY_LETTER_CALL_VA, uc.HOME_LETTER_CALL_VA, count=10_000)
        esp = m.reg_read(UC_X86_REG_ESP)
        self.assertEqual(esp, STACK - 8)
        home_letter = chr(struct.unpack("<H", m.mem_read(esp + 0x10, 2))[0])
        return home_letter, away_letter, swap_reg

    def test_the_retail_block_reproduces_the_cowboys_exception(self) -> None:
        self.assertEqual(self._letters(self.retail, "NYG", "PHI")[:2], ("h", "a"))
        self.assertEqual(self._letters(self.retail, "DAL", "PHI")[:2], ("a", "h"))
        self.assertEqual(self._letters(self.retail, "WAS", "DAL")[:2], ("a", "h"))
        self.assertEqual(self._letters(self.retail, "TEN", "DAL")[:2], ("a", "h"))
        self.assertEqual(self._letters(self.retail, "PHI", "DAL")[:2], ("h", "a"))
        self.assertEqual(self._letters(self.retail, "NYG", "PHI", 7, 7)[:2], ("h", "a"))   # retail ignores the words

    def test_the_rule_form_is_home_dark_everywhere(self) -> None:
        for home, away in (("NYG", "PHI"), ("DAL", "PHI"), ("WAS", "DAL"), ("TEN", "DAL")):
            self.assertEqual(self._letters(self.images["rule"], home, away)[:2], ("h", "a"), (home, away))

    def test_the_choice_form_keeps_the_retail_default_and_honours_both_flips(self) -> None:
        cases = {("NYG", "PHI"): 0, ("PHI", "DAL"): 0, ("DAL", "PHI"): 1, ("WAS", "DAL"): 1, ("TEN", "DAL"): 1, ("DAL", "WAS"): 1}
        for (home, away), swap in cases.items():
            for home_flip in (0, 7):
                for away_flip in (0, 7):
                    got = self._letters(self.images["choice"], home, away, home_flip, away_flip)
                    want_home = "a" if swap ^ (home_flip and 1) else "h"
                    want_away = "h" if swap ^ (away_flip and 1) else "a"
                    self.assertEqual(got[:2], (want_home, want_away), (home, away, home_flip, away_flip))
                    self.assertEqual(got[2], (7 * swap) ^ home_flip, "esi feeds the retail home site")

    def test_a_normal_game_with_the_four_flip_states(self) -> None:
        image = self.images["choice"]
        self.assertEqual(self._letters(image, "NYG", "PHI", 0, 0)[:2], ("h", "a"))
        self.assertEqual(self._letters(image, "NYG", "PHI", 0, 7)[:2], ("h", "h"))   # visitor dark too
        self.assertEqual(self._letters(image, "NYG", "PHI", 7, 0)[:2], ("a", "a"))   # both white, allowed
        self.assertEqual(self._letters(image, "NYG", "PHI", 7, 7)[:2], ("a", "h"))
        self.assertEqual(self._letters(image, "DAL", "PHI", 7, 0)[:2], ("h", "h"))   # Cowboys fan flips to dark at home; the visitor stays dark
        self.assertEqual(self._letters(image, "DAL", "PHI", 7, 7)[:2], ("h", "a"))   # ... until the visitor flips too


@unittest.skipUnless(XBE.is_file() and Uc is not None, "retail extraction or unicorn not present")
class HandlerEmulationTests(unittest.TestCase):
    """The four era handlers, the reset, and the 30-state cycle."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.choice = uc.apply(cls.retail, "choice")[0]

    def _run(self, image: bytes, va: int, eras: set[int] | None, slot: int, flip: int, side: str) -> tuple[int, int]:
        slot_va = uc.HOME_SLOT_VA if side == "home" else uc.AWAY_SLOT_VA
        flip_va = uc.HOME_FLIP_VA if side == "home" else uc.AWAY_FLIP_VA
        other_flip = uc.AWAY_FLIP_VA if side == "home" else uc.HOME_FLIP_VA
        m = _machine(image)
        team = 0 if eras is None else TEAM
        for k in (eras or ()):
            m.mem_write(TEAM + uc.TEAM_YEARS_OFF + 4 * (k - 1), struct.pack("<HH", 1990 + k, 1991 + k))
        m.mem_write(uc.HOME_TEAM_PTR_VA, struct.pack("<I", team))
        m.mem_write(uc.AWAY_TEAM_PTR_VA, struct.pack("<I", team))
        m.mem_write(slot_va, struct.pack("<I", slot))
        m.mem_write(flip_va, struct.pack("<I", flip))
        m.mem_write(other_flip, struct.pack("<I", 0x77))
        m.mem_write(STACK, struct.pack("<I", SENTINEL))
        m.reg_write(UC_X86_REG_ESP, STACK)
        m.emu_start(va, SENTINEL, count=100_000)
        self.assertEqual(m.reg_read(UC_X86_REG_EAX), 1, "the handler returns 1 like retail")
        self.assertEqual(m.reg_read(UC_X86_REG_ESP), STACK + 4, "balanced stack")
        self.assertEqual(_dword(m, other_flip), 0x77, "the other side's flip is untouched")
        return _dword(m, slot_va), _dword(m, flip_va)

    def test_retail_handlers_clamp_without_wrapping(self) -> None:
        eras = {1, 2, 5}
        self.assertEqual(self._run(self.retail, uc.HOME_NEXT_VA, eras, 5, 0, "home"), (5, 0))
        self.assertEqual(self._run(self.retail, uc.HOME_PREV_VA, eras, 0, 0, "home"), (0, 0))
        self.assertEqual(self._run(self.retail, uc.HOME_NEXT_VA, eras, 2, 0, "home"), (5, 0))
        self.assertEqual(self._run(self.retail, uc.AWAY_PREV_VA, eras, 5, 0, "away"), (2, 0))

    def test_next_walks_the_available_eras_then_flips_and_restarts(self) -> None:
        eras = {1, 2, 5}
        for side, va in (("home", uc.HOME_NEXT_VA), ("away", uc.AWAY_NEXT_VA)):
            self.assertEqual(self._run(self.choice, va, eras, 0, 0, side), (1, 0), side)
            self.assertEqual(self._run(self.choice, va, eras, 1, 0, side), (2, 0), side)
            self.assertEqual(self._run(self.choice, va, eras, 2, 0, side), (5, 0), side)
            self.assertEqual(self._run(self.choice, va, eras, 5, 0, side), (0, 7), side)    # past the last era: flip, restart
            self.assertEqual(self._run(self.choice, va, eras, 5, 7, side), (0, 0), side)    # and back
            self.assertEqual(self._run(self.choice, va, eras, 2, 7, side), (5, 7), side)    # a flip does not change the walk

    def test_prev_walks_down_then_flips_and_jumps_to_the_last_era(self) -> None:
        eras = {1, 2, 5}
        for side, va in (("home", uc.HOME_PREV_VA), ("away", uc.AWAY_PREV_VA)):
            self.assertEqual(self._run(self.choice, va, eras, 5, 0, side), (2, 0), side)
            self.assertEqual(self._run(self.choice, va, eras, 2, 0, side), (1, 0), side)
            self.assertEqual(self._run(self.choice, va, eras, 1, 0, side), (0, 0), side)
            self.assertEqual(self._run(self.choice, va, eras, 0, 0, side), (5, 7), side)    # below era 0: flip, last era
            self.assertEqual(self._run(self.choice, va, eras, 0, 7, side), (5, 0), side)

    def test_a_team_with_no_throwbacks_just_toggles_the_colour(self) -> None:
        for va, side in ((uc.HOME_NEXT_VA, "home"), (uc.HOME_PREV_VA, "home"), (uc.AWAY_NEXT_VA, "away"), (uc.AWAY_PREV_VA, "away")):
            self.assertEqual(self._run(self.choice, va, set(), 0, 0, side), (0, 7), hex(va))
            self.assertEqual(self._run(self.choice, va, set(), 0, 7, side), (0, 0), hex(va))
        # no team object at all (FUN_000e2a90 says no era exists, era 0 included): slot 0, colour toggles
        self.assertEqual(self._run(self.choice, uc.HOME_NEXT_VA, None, 0, 0, "home"), (0, 7))
        self.assertEqual(self._run(self.choice, uc.HOME_PREV_VA, None, 0, 0, "home"), (0, 7))

    def test_up_and_down_cycle_thirty_states(self) -> None:
        eras = set(range(1, 15))
        state = (0, 0)
        seen = []
        for _ in range(30):
            state = self._run(self.choice, uc.AWAY_NEXT_VA, eras, state[0], state[1], "away")
            seen.append(state)
        self.assertEqual(len(set(seen)), 30)
        self.assertEqual(state, (0, 0))
        self.assertEqual(seen[:15], [(k, 0) for k in range(1, 15)] + [(0, 7)])
        back = (0, 0)
        for expected in reversed(seen[:-1]):
            back = self._run(self.choice, uc.AWAY_PREV_VA, eras, back[0], back[1], "away")
            self.assertEqual(back, expected)

    def test_the_reset_clears_the_slots_and_both_flips(self) -> None:
        m = _machine(self.choice)
        for va in (uc.HOME_SLOT_VA, uc.AWAY_SLOT_VA, 0xB9C160):
            m.mem_write(va, struct.pack("<I", 5))
        for va in (uc.HOME_FLIP_VA, uc.AWAY_FLIP_VA):
            m.mem_write(va, struct.pack("<I", 7))
        m.mem_write(STACK, struct.pack("<I", SENTINEL))
        m.reg_write(UC_X86_REG_ESP, STACK)
        m.emu_start(uc.RESET_VA, SENTINEL, count=1_000)
        for va in (uc.HOME_SLOT_VA, uc.AWAY_SLOT_VA, 0xB9C160, uc.HOME_FLIP_VA, uc.AWAY_FLIP_VA):
            self.assertEqual(_dword(m, va), 0, hex(va))
        self.assertEqual(m.reg_read(UC_X86_REG_ESP), STACK + 4)


if __name__ == "__main__":
    unittest.main()
