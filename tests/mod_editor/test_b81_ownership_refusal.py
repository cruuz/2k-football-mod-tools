"""The ownership guard's refusal withdraws a refused listing too (b81 trades lane, coordinator 11/25).

The guard (tools/franchise_ownership: ownership_trade_stub in the common trade executor 0x2BC670) refuses a trade whose
outgoing men are no longer their club's. Its decline cancelled only pending offers (kind 2) with the game's own cancel
0x2BB660(offer, 0, 1, 1); a refused listing (kind 1, which the CPU's proposers pick) stayed on the board and was refused
again every week. The economy lane found such a record outlive a release by eleven weeks (74003, 2031).

- RefusedListing: on a regular-season image (CPU_TRADES_MIDSEASON_IMAGE and its executable CPU_TRADES_MIDSEASON_XBE), a
  listing and a pending offer whose man belongs to another club go through the executor: with the previous page the
  listing stays (the bug), with this revision both are withdrawn and nobody moves.
- Revision: a standard executable carrying the previous page (CPU_TRADES_STANDARD_XBE, 8b180ed5) reads applied and
  "previous"; apply() rewrites the page in place (hook sites unchanged) and reads "current"; the Studio's QB floor does
  the same on an in-place edit.
Fixtures come from the environment; without them the classes skip.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import unittest

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

MIDSEASON = os.environ.get("CPU_TRADES_MIDSEASON_IMAGE", "")
MIDSEASON_XBE = os.environ.get("CPU_TRADES_MIDSEASON_XBE", "")
STANDARD_XBE = os.environ.get("CPU_TRADES_STANDARD_XBE", "")
BOARD, RECORD = 0xE3C27C, 0x3C


def _need(*paths):
    if not all(p and Path(p).is_file() for p in paths):
        raise unittest.SkipTest("CPU_TRADES_MIDSEASON_IMAGE / _XBE / CPU_TRADES_STANDARD_XBE not set or absent")


@unittest.skipUnless(HAVE_UC, "Unicorn is required")
class RefusedListing(unittest.TestCase):
    def machine(self, page):
        from tests.mod_editor.test_b81_cpu_trades import Image
        from mod_editor.core import nfl2k5_franchise_ownership as own, nfl2k5_injured_reserve as ir
        _need(MIDSEASON, MIDSEASON_XBE)
        x = Image(MIDSEASON, MIDSEASON_XBE)
        xbe = Path(MIDSEASON_XBE).read_bytes()
        va = own._allocation(xbe)["va"]
        module = own.runtime if page == "current" else own.PREVIOUS[0]
        x.m.uc.mem_write(va, own.code_for(va, ir.store_va(xbe), module))
        x.m.uc.ctl_flush_tb()
        return x

    def refuse(self, x, kind):
        m = x.m
        slot = next(s for s in range(1, 15) if not m.get(BOARD + RECORD * s))
        seller, buyer, other = 3, 5, 9
        p = x.roster(other)[10]                                  # another club's man: the guard refuses
        rec = BOARD + RECORD * slot
        for i in range(15):
            m.put(rec + 4 * i, 0)
        m.put(rec + 8, x.club(seller))
        m.put(rec + 0xC, p)
        m.put(rec + 0x20, x.club(buyer))
        m.put(rec + 0x30, 5 | buyer << 6)
        m.put(rec, kind)
        rosters = {c: x.roster(c) for c in (seller, buyer, other)}
        m.uc.mem_write(m.STACK, struct.pack("<II", m.STOP, m.ARENA + 0x1A0000))
        for k, v in dict(ESP=m.STACK, ECX=rec, EDX=0, EFLAGS=0x202).items():
            m.reg(k, v)
        m.uc.emu_start(0x2BC670, m.STOP, count=500_000_000)
        self.assertEqual(m.reg("EAX"), 0)                        # refused
        self.assertEqual({c: x.roster(c) for c in rosters}, rosters)
        return m.get(rec)

    def test_the_previous_page_leaves_a_refused_listing(self):
        self.assertEqual(self.refuse(self.machine("previous"), 1), 1)
        self.assertEqual(self.refuse(self.machine("previous"), 2), 0)

    def test_this_revision_withdraws_a_refused_listing_and_offer(self):
        self.assertEqual(self.refuse(self.machine("current"), 1), 0)
        self.assertEqual(self.refuse(self.machine("current"), 2), 0)


class Revision(unittest.TestCase):
    def test_a_previous_page_reads_applied_and_upgrades_in_place(self):
        from mod_editor.core import nfl2k5_franchise_ownership as own, nfl2k5_injured_reserve as ir
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        _need(STANDARD_XBE)
        source = Path(STANDARD_XBE).read_bytes()
        store = ir.store_va(source)
        self.assertEqual((own.status(source, store), own.revision(source, store)), ("applied", "previous"))
        upgraded, receipt = own.apply(source, store)
        self.assertEqual((own.status(upgraded, store), own.revision(upgraded, store)), ("applied", "current"))
        self.assertEqual(receipt["upgraded_from"], "previous")
        a, b = XbeImage(source), XbeImage(upgraded)
        for at, old, _symbol, _opcode in own.HOOKS:
            self.assertEqual(a.read(at, len(old)), b.read(at, len(old)))
        again, receipt = own.apply(upgraded, store)
        self.assertEqual((again, receipt["status"]), (upgraded, "already_applied"))
        self.assertEqual(ir.status(upgraded), ir.status(source))

    def test_the_studio_qb_floor_upgrades_the_page_on_an_in_place_edit(self):
        from mod_editor.core import mod_build, nfl2k5_franchise_ownership as own, nfl2k5_injured_reserve as ir
        _need(STANDARD_XBE)
        source = Path(STANDARD_XBE).read_bytes()
        result, notes = mod_build._qb_floor_in_place(source)
        self.assertEqual(own.revision(result, ir.store_va(result)), "current")
        self.assertTrue(any("ownership safeguards" in n for n in notes))
        again, notes = mod_build._qb_floor_in_place(result)
        self.assertEqual(again, result)
        self.assertFalse(any("ownership safeguards" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
