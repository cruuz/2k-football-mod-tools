"""b780 hunt6 (fix wave Q36): the one-pool positions give OLB no draft need.

FUN_0031dea0 orders the 17 positions by need for every CPU pick, the human auto-pick and the draft AI's need tilt:
(target + per-round weight - count) * (100 - average overall), or the weight alone for the first round's top picks.
The pools set OLB's target and maximum to 0 and draft no OLB, but OLB kept its retail weights, so a full roster with no
OLB put OLB first in rounds 2, 4 and 7. nfl2k5_position_pools now writes -50 into the eight OLB weights; the real
routine runs in Unicorn on a pools build without them (the v0.8 and v0.9 RC state) and with them.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_bump_strength as strength
from mod_editor.core import nfl2k5_edge_rename as edge
from mod_editor.core import nfl2k5_modern_positions as modern
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_CPU = importlib.util.find_spec("unicorn") is not None
OLB = pools.ENUM_OLB
FN_NEED = 0x31DEA0
STOP, STACK, SCRATCH = 0x3100000, 0x3008000, 0x3010000
# a 53-man one-pool roster with no OLB: QB K P WR CB FS SS HB FB TE OLB LB C G T DT EDGE
ROSTER = (3, 1, 1, 6, 5, 2, 2, 4, 1, 3, 0, 6, 2, 4, 4, 4, 5)


def _env(name):
    value = os.environ.get(name, "")
    return Path(value) if value else None


def without_need_fix(patched: bytes) -> bytes:
    """A pools build as v0.8 and the v0.9 RC have it: everything but the eight OLB weights."""
    buf = bytearray(patched)
    for site in pools.draft_need_sites():
        at = pools._offset(patched, site.va)
        buf[at: at + site.size] = site.befores[0]
    for section in strength._sections(bytes(buf)):
        if section.raw_size:
            d = section.header_offset + 36
            buf[d: d + 20] = strength.section_digest(bytes(buf), section)
    return bytes(buf)


class SiteTests(unittest.TestCase):
    def test_eight_weights_one_value(self):
        sites = pools.draft_need_sites()
        self.assertEqual(len(sites), 8)
        self.assertEqual(sites[0].va, 0x532060 + 4 * OLB)
        self.assertEqual([s.va for s in sites[1:]], [0x5320A4 + 68 * r + 4 * OLB for r in range(7)])
        self.assertTrue(all(s.after == struct.pack("<f", -50.0) and s.group == "draft_need" for s in sites))
        self.assertEqual(pools.new_targets()[OLB], 0)
        self.assertEqual(pools.new_maxima()[OLB], 0)


@unittest.skipUnless(XBE.is_file(), "retail extraction required")
class UpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = pools.apply(modern.apply(edge.apply(cls.retail)[0])[0])
        cls.older = without_need_fix(cls.patched)

    def test_retail_holds_the_retail_weights(self):
        image = XbeImage(self.retail)
        for site, value in zip(pools.draft_need_sites(), pools.RETAIL_OLB_NEED):
            self.assertEqual(struct.unpack("<f", image.read(site.va, 4))[0], struct.unpack("<f", struct.pack("<f", value))[0])
        self.assertEqual((pools.status(self.retail), pools.draft_need_status(self.retail)), ("retail", "retail"))

    def test_a_new_install_writes_them(self):
        self.assertEqual((pools.status(self.patched), pools.draft_need_status(self.patched)), ("applied", "applied"))
        self.assertEqual(self.receipt["draft_need"], "applied")
        labels = {e["label"] for e in self.receipt["edits"]}
        self.assertTrue({s.label for s in pools.draft_need_sites()} <= labels)

    def test_an_older_install_still_reads_applied_and_upgrades_in_place(self):
        self.assertEqual((pools.status(self.older), pools.draft_need_status(self.older)), ("applied", "retail"))
        upgraded, receipt = pools.apply(self.older)
        self.assertEqual(upgraded, self.patched)
        self.assertEqual([e["label"] for e in receipt["edits"]], [s.label for s in pools.draft_need_sites()])
        self.assertEqual(pools.apply(upgraded)[1]["edits"], [])

    def test_a_partial_or_foreign_weight_refuses(self):
        for site in pools.draft_need_sites()[::3]:
            broken = bytearray(self.patched)
            at = pools._offset(self.patched, site.va)
            broken[at: at + 4] = struct.pack("<f", 1.0)
            self.assertEqual(pools.status(bytes(broken)), "foreign", site.label)
        lone = bytearray(self.retail)
        site = pools.draft_need_sites()[0]
        at = pools._offset(self.retail, site.va)
        lone[at: at + 4] = site.after
        self.assertEqual(pools.status(bytes(lone)), "foreign")        # the weights without the pools are not ours

    def test_released_executables_read_applied_without_the_weights(self):
        for name in ("NFL2K5_V08_XBE", "NFL2K5_B780_RC_XBE"):
            path = _env(name)
            if path is None or not path.is_file():
                continue
            raw = path.read_bytes()
            self.assertEqual((pools.status(raw), pools.draft_need_status(raw)), ("applied", "retail"), name)


@unittest.skipUnless(XBE.is_file() and HAVE_CPU, "retail extraction and Unicorn required")
class NeedOrderTests(unittest.TestCase):
    """FUN_0031dea0 itself; the three leaves it calls are replaced by tiny stubs in emulator memory only."""

    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        cls.fixed = pools.apply(modern.apply(edge.apply(retail)[0])[0])[0]
        cls.older = without_need_fix(cls.fixed)

    def _order(self, payload, rnd, pick, roster):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn import x86_const as x
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x10000, 0xFF0000)
        image = XbeImage(payload)
        for s in image.sections:
            if s.raw_size:
                uc.mem_write(s.start, image.read(s.start, min(s.size, s.raw_size)))
        uc.mem_map(0x3000000, 0x20000)
        uc.mem_map(STOP, 0x1000)
        overall, entry, team, players, need = SCRATCH, SCRATCH + 0x10, SCRATCH + 0x100, SCRATCH + 0x1000, SCRATCH + 0x400
        uc.mem_write(overall, struct.pack("<f", 0.70))
        uc.mem_write(0x246D80, b"\xd9\x05" + struct.pack("<I", overall) + b"\xc3")      # fld dword [overall]; ret
        uc.mem_write(0x322840, b"\xb8" + struct.pack("<I", entry) + b"\xc3")            # the signing slot
        uc.mem_write(0x322BA0, b"\x31\xc0\xc3")                                          # not in use
        uc.mem_write(0xB72918, struct.pack("<I", SCRATCH + 0x20))                       # the drafted list: empty
        n = 0
        for position, count in enumerate(roster):
            for _ in range(count):
                record = players + 0x40 * n
                uc.mem_write(record + 0x35, bytes((position,)))
                uc.mem_write(team + 4 * n, struct.pack("<I", record))
                n += 1
        uc.mem_write(team + 0x11C, bytes((n,)))
        uc.mem_write(STACK, struct.pack("<III", STOP, pick, need))
        uc.reg_write(x.UC_X86_REG_ESP, STACK)
        uc.reg_write(x.UC_X86_REG_ECX, team)
        uc.reg_write(x.UC_X86_REG_EDX, rnd)
        uc.emu_start(FN_NEED, STOP, count=500000)
        self.assertEqual(uc.reg_read(x.UC_X86_REG_ESP), STACK + 12)                   # ret 8
        order = list(struct.unpack("<17I", bytes(uc.mem_read(need, 68))))
        self.assertEqual(sorted(order), list(range(17)))
        return order

    def test_olb_is_always_last_and_the_real_positions_keep_their_order(self):
        older_top = []
        for roster in (ROSTER, (0,) * 17):
            for rnd in range(7):
                for pick in ((0, 10) if rnd == 0 else (10,)):
                    with self.subTest(roster=sum(roster), round=rnd + 1, pick=pick):
                        old = self._order(self.older, rnd, pick, roster)
                        new = self._order(self.fixed, rnd, pick, roster)
                        self.assertEqual(new.index(OLB), 16)
                        self.assertEqual([p for p in old if p != OLB], new[:16])
                        if roster == ROSTER and old.index(OLB) == 0:
                            older_top.append(rnd + 1)
        # without the fix a full roster with no OLB put OLB first in rounds 2, 4 and 7
        self.assertEqual(older_top, [2, 4, 7])


if __name__ == "__main__":
    unittest.main()
