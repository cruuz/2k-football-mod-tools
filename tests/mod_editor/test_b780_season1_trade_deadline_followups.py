"""b780-season1: the pending-trade purge and the "Trade Deadline is upon us" inbox story follow the Week 9 deadline.

b778-tr1 moved the Front Office trade rows and the Player Trade screen to the modern deadline (trades open through
displayed Week 9), but two more native boundaries kept the retail deadline:

* the Season case of the weekly advance (FUN_00247d40) clears the 15 pending trade offers at 0xE3C27C on every tick after
  stored week 6, so the tick that ends Week 8 emptied the offer list for Week 9, the last open week;
* the weekly inbox stories (FUN_0027eb80) post story 17 ("The Trade Deadline is upon us. Will there be a deal?") when the
  new week is 5, three weeks before the deadline.

The native tests run the game's own instructions under Unicorn (the purge loop with its FUN_002bb660 clears, and the
story trigger with the story poster stubbed to a recorder) week by week, on the retail executable before and after the
patch, on the two-site shape every v0.7 to v0.9 build carries, and on the v0.9 RC executable when it is present.
"""

from __future__ import annotations

import importlib.util
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_trade_deadline as td  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_b778_tr1_trade_deadline import _raw_offset, build_synthetic_xbe  # noqa: E402

RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE", ""))
RC_XBE = Path(os.environ.get("NFL2K5_B780_RC_XBE", ""))
HAVE_UC = importlib.util.find_spec("unicorn") is not None
OPTION, WEEK, STAGE, OFFERS, OFFER_SIZE, OFFER_COUNT = 0xE60124, 0xE576B4, 0xE576A4, 0xE3C27C, 0x3C, 15
STORY_POSTER, STORY_DEADLINE = 0x27E3C0, 0x11
WEEKS = range(12)


def legacy_shape(applied: bytes) -> bytes:
    """The two-site image of beta-78 to beta-80: both follow-up immediates back to their retail values."""
    edits = [(site.label, site.va, site.patched, site.retail) for site in td.followup_sites()]
    return rdata.apply(applied, edits, "two-site trade deadline (v0.7 to v0.9)")[0]


class Machine:
    """Every section of an executable mapped at its VA, a stack and a stop page."""

    STACK, STOP = 0x4000000, 0x5000000

    def __init__(self, payload: bytes) -> None:
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({va for s in image.sections for va in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096)})
        for page in pages:
            self.uc.mem_map(page, 4096)
        for s in image.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, image.read(s.start, s.raw_size))
        self.uc.mem_map(self.STACK, 0x10000)
        self.uc.mem_map(self.STOP, 4096)
        self.posted: dict[int, list[int]] = {}
        self.uc.hook_add(u.UC_HOOK_CODE, self._poster, begin=STORY_POSTER, end=STORY_POSTER)

    def put(self, va: int, value: int) -> None:
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def _poster(self, uc, _address, _size, _data) -> None:   # record (new week -> story) and return to the caller
        self.posted.setdefault(self.get(WEEK), []).append(uc.reg_read(self.x.UC_X86_REG_EDX))
        sp = uc.reg_read(self.x.UC_X86_REG_ESP)
        uc.reg_write(self.x.UC_X86_REG_EIP, self.get(sp))
        uc.reg_write(self.x.UC_X86_REG_ESP, sp + 4)

    def run(self, start: int, stop: int) -> None:
        self.uc.reg_write(self.x.UC_X86_REG_ESP, self.STACK + 0x8000)
        self.uc.reg_write(self.x.UC_X86_REG_EBX, 1)          # the tick keeps 1 in ebx: the clear's two arguments
        self.uc.emu_start(start, stop, count=200000)
        if self.uc.reg_read(self.x.UC_X86_REG_EIP) != stop:
            raise AssertionError(f"stopped at {self.uc.reg_read(self.x.UC_X86_REG_EIP):#x}, not {stop:#x}")

    def offers_kept(self, week: int) -> int:
        """The Season tick's purge (0x247E23..0x247E56) for stored week ``week``: how many of 15 offers survive."""
        self.put(OPTION, 1)
        self.put(WEEK, week)
        offer = bytes(range(1, OFFER_SIZE + 1))
        for k in range(OFFER_COUNT):
            self.uc.mem_write(OFFERS + k * OFFER_SIZE, offer)
        self.run(0x247E23, 0x247E56)
        return sum(bytes(self.uc.mem_read(OFFERS + k * OFFER_SIZE, OFFER_SIZE)) == offer for k in range(OFFER_COUNT))

    def deadline_story_weeks(self) -> list[int]:
        """The inbox story trigger (0x27ECE7..0x27ED13) in the Season stage: the new weeks that post story 17."""
        self.posted = {}
        for week in WEEKS:
            self.put(OPTION, 1)
            self.put(STAGE, 8)
            self.put(WEEK, week)
            self.run(0x27ECE7, 0x27ED13)
        return sorted(w for w, stories in self.posted.items() if STORY_DEADLINE in stories)


class ConstantsTests(unittest.TestCase):
    def test_follow_ups_are_the_two_retail_deadline_immediates(self) -> None:
        sites = td.followup_sites()
        self.assertEqual([(s.label, s.va, s.retail, s.patched) for s in sites],
                         [("pending_trade_purge_week", 0x247E33, b"\x06", b"\x08"),
                          ("deadline_story_week", 0x27ECF8, b"\x05", b"\x08")])
        # retail's purge starts after its screen limit and its story comes in the last week its rows show
        self.assertEqual((td.RETAIL_PURGE_WEEK, td.RETAIL_STORY_WEEK), (td.RETAIL_SCREEN_WEEK, td.RETAIL_PREDICATE_WEEK - 1))
        self.assertEqual((td.PURGE_WEEK_LIMIT, td.STORY_WEEK), (td.SCREEN_WEEK_LIMIT, td.PREDICATE_WEEK_LIMIT - 1))
        self.assertEqual(td.STORY_WEEK + 1, td.DEADLINE_WEEK)    # stored week 8 = displayed Week 9

    def test_contexts_are_the_retail_instruction_runs(self) -> None:
        for _label, context_va, context, va, retail, _patched, _note in td.FOLLOWUPS:
            self.assertEqual(context[va - context_va], retail)
            self.assertEqual(context[va - context_va - 2:va - context_va], b"\x83\xf8")   # cmp eax,imm8
        purge, story = td.PURGE_CONTEXT_RETAIL, td.STORY_CONTEXT_RETAIL
        self.assertEqual(purge[:5], bytes.fromhex("a12401e600"))                   # the Trade Deadline option
        self.assertIn(bytes.fromhex("833d2401e60001"), story)
        self.assertEqual(story[story.index(b"\xba") + 1], STORY_DEADLINE)          # mov edx,0x11 (story 17)
        for blob, base, calls in ((purge, td.PURGE_CONTEXT_VA, (9,)), (story, td.STORY_CONTEXT_VA, (0, 10, 39))):
            targets = [base + at + 5 + struct.unpack_from("<i", blob, at + 1)[0] for at in calls]
            self.assertTrue(all(blob[at] == 0xE8 for at in calls))
            self.assertEqual(targets, [0xC4E70] if blob is purge else [0xC4BB0, 0xC4E70, STORY_POSTER])


class SyntheticTests(unittest.TestCase):
    def test_apply_writes_all_four_bytes_and_stays_idempotent(self) -> None:
        retail = build_synthetic_xbe()
        self.assertEqual((td.status(retail), td.followups_status(retail)), ("retail", "retail"))
        applied, receipt = td.apply(retail)
        self.assertEqual((td.status(applied), td.followups_status(applied)), ("applied", "applied"))
        self.assertEqual([e["label"] for e in receipt["edits"]],
                         ["trade_screen_week_limit", "stage_table_season_deadline", "pending_trade_purge_week",
                          "deadline_story_week"])
        self.assertEqual(applied[_raw_offset(td.PURGE_VA)], 8)
        self.assertEqual(applied[_raw_offset(td.STORY_VA)], 8)
        self.assertEqual(td.repair_followups(applied), (applied, td.repair_followups(applied)[1]))
        self.assertTrue(td.repair_followups(applied)[1]["already_applied"])

    def test_two_site_images_are_repaired_in_place(self) -> None:
        legacy = legacy_shape(td.apply(build_synthetic_xbe())[0])
        self.assertEqual((td.status(legacy), td.followups_status(legacy)), ("applied", "retail"))
        self.assertEqual(td.apply(legacy)[0], legacy)              # apply leaves a moved deadline alone, as before
        repaired, receipt = td.repair_followups(legacy)
        self.assertFalse(receipt["already_applied"])
        self.assertEqual(receipt["changed_bytes"], 2 + 20)         # two immediates and the .text digest
        self.assertEqual(repaired, td.apply(build_synthetic_xbe())[0])
        self.assertEqual(td.repair_followups(repaired)[0], repaired)
        # one follow-up already moved: the other one is added
        one = rdata.apply(repaired, [("story", td.STORY_VA, b"\x08", b"\x05")], "partial")[0]
        self.assertEqual(td.followups_status(one), "partial")
        self.assertEqual(td.repair_followups(one)[0], repaired)

    def test_refusals(self) -> None:
        retail = build_synthetic_xbe()
        with self.assertRaises(td.TradeDeadlineError):
            td.repair_followups(retail)                            # the deadline itself is not moved
        bare = build_synthetic_xbe(followups=False)
        self.assertEqual(td.followups_status(bare), "foreign")
        with self.assertRaises(td.TradeDeadlineError):
            td.apply(bare)
        odd = bytearray(td.apply(retail)[0])
        odd[_raw_offset(td.PURGE_VA)] = 7
        self.assertEqual(td.followups_status(bytes(odd)), "foreign")
        with self.assertRaises(td.TradeDeadlineError):
            td.repair_followups(bytes(odd))
        self.assertEqual(td.followups_status(b"not an xbe"), "foreign")

    def test_the_build_moves_the_follow_ups_on_moved_images(self) -> None:
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertIn("deadline.repair_followups(xbe)", text)


@unittest.skipUnless(HAVE_UC and RETAIL_XBE.is_file(), "Unicorn and the private retail executable are needed")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()
        cls.fixed = td.apply(cls.retail)[0]
        cls.legacy = legacy_shape(cls.fixed)

    def assert_deadline(self, payload: bytes, purge_after: int, story_week: int) -> None:
        m = Machine(payload)
        kept = [m.offers_kept(week) for week in WEEKS]
        # ticks up to purge_after keep all 15 offers; every later tick clears them all
        self.assertEqual(kept, [OFFER_COUNT if week <= purge_after else 0 for week in WEEKS])
        self.assertEqual(m.deadline_story_weeks(), [story_week])

    def assert_retail_weeks(self, payload: bytes) -> None:
        self.assert_deadline(payload, td.RETAIL_PURGE_WEEK, td.RETAIL_STORY_WEEK)

    def assert_week_nine(self, payload: bytes) -> None:
        self.assert_deadline(payload, td.PURGE_WEEK_LIMIT, td.STORY_WEEK)

    def test_retail_purges_after_week_seven_and_warns_at_week_six(self) -> None:
        self.assert_retail_weeks(self.retail)

    def test_two_site_builds_still_used_the_retail_weeks(self) -> None:
        self.assertEqual((td.status(self.legacy), td.followups_status(self.legacy)), ("applied", "retail"))
        self.assert_retail_weeks(self.legacy)

    def test_fixed_offers_survive_through_week_nine_and_the_story_comes_at_week_nine(self) -> None:
        self.assert_week_nine(self.fixed)
        self.assert_week_nine(td.repair_followups(self.legacy)[0])

    def test_retail_bytes_and_receipt(self) -> None:
        image = XbeImage(self.retail)
        for _label, context_va, context, _va, _retail, _patched, _note in td.FOLLOWUPS:
            self.assertEqual(image.read(context_va, len(context)), context)
        self.assertEqual(td.apply(self.retail)[1]["changed_bytes"], 44)

    @unittest.skipUnless(RC_XBE.is_file(), "the v0.9 RC executable is not present")
    def test_v09_rc_carries_the_bug_and_repairs_in_place(self) -> None:
        rc = RC_XBE.read_bytes()
        self.assertEqual((td.status(rc), td.followups_status(rc)), ("applied", "retail"))
        self.assert_retail_weeks(rc)
        repaired, receipt = td.repair_followups(rc)
        self.assertEqual(receipt["changed_bytes"], 2 + 20)
        self.assert_week_nine(repaired)


if __name__ == "__main__":
    unittest.main()
