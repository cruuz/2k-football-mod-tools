"""b780 hunt5: what the SPECIAL 3DRB row does on the field, proved with the game's own code.

Noah (11/03): "make sure every movement in the special part of the depth chart does something accurately, and it
doesn't permanently make someone in a special position a starter somewhere else. If I make someone a third down back,
they shouldn't be in every single play. The starting halfback should have priority."

Revision 1 of the SPECIAL rows (beta-76.4 to the beta-80 RC) drew 3DRB as chain 0: the RB rank list itself. Putting a
back at the top of 3DRB made him RB1, and RB1 is the back every shipped formation asks for first (ordinal 0 in all
1,048 passing and 516 base RB slots of the v0.9 books). Revision 2 draws 3DRB as chain 2, RB rank row 1: the starter is
not in the row, the back put at its top becomes RB2, and the RB slot still takes the starter first.

The native tests run the real SPECIAL swap path (0x2442E8), the chart getter (0x242AE0) and the on-field picker
(0xE8790 with its 0xE7530 ordinal decoder, 0xE7810 list reader, 0xE7580 used-player check and 0xE8340 starter gate)
on the retail executable with the SPECIAL rows applied, in Unicorn (the bounded harness of
tests/nfl2k5_depth_chart_rows_test.py). They need NFL2K5_RETAIL_EXTRACTION and Python unicorn; the layout tests run
anywhere on the synthetic executable.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]
import nfl2k5_depth_chart_rows_test as legacy  # noqa: E402
from mod_editor.core import nfl2k5_depth_chart_rows as rows  # noqa: E402
from mod_editor.core import nfl2k5_depth_chart_storage as storage  # noqa: E402
from mod_editor.core import nfl2k5_modern_positions as modern  # noqa: E402
from nfl2k5_position_pools_test import _repin  # noqa: E402

RB, RB_KIND = 7, 10
THIRD_DOWN = (3, 11)                       # SPECIAL unit 3, row 11
OFFENSE_RB = (0, 1)


def revision_1(payload: bytes) -> bytes:
    """The same applied executable with the beta-76.4..beta-80 RC 3DRB record (chain 0), digests repinned."""
    buf = bytearray(payload)
    for row in rows.LEGACY_ROLE_ROWS:
        legacy.put(buf, modern.record_va(row[0], row[1], table_va=rows.TABLE_VA), rows._role_record(row))
    _repin(buf)
    return bytes(buf)


class SpecialRowRevisionTests(unittest.TestCase):
    """Layout contract and the in-place upgrade, on the synthetic executable."""

    @classmethod
    def setUpClass(cls):
        cls.storage_pin = patch.object(storage, "RETAIL_CONTENT_SHA256", hashlib.sha256(bytes(storage.RETAIL_SIZE)).hexdigest())
        cls.storage_pin.start()
        cls.addClassCleanup(cls.storage_pin.stop)
        cls.patched = rows.apply(legacy.prepare(legacy.fixture()))[0]

    def test_3drb_is_rb_rank_row_one(self):
        special = {r["abbreviation"]: (r["position"], r["chain"]) for r in modern.read_depth_chart_units(self.patched)["SPECIAL"]}
        self.assertEqual(special["3DRB"], (RB, 2))
        self.assertEqual(special["PWRB"], (RB, 1))
        self.assertEqual(rows.revision(self.patched), rows.REVISION)

    def test_a_revision_1_table_reads_applied_and_upgrades_one_dword_in_place(self):
        old = revision_1(self.patched)
        self.assertEqual((rows.status(old), rows.revision(old)), ("applied", 1))
        upgraded, receipt = rows.apply(old)
        self.assertEqual(upgraded, self.patched)
        self.assertEqual(receipt["upgraded_from"], "revision 1")
        va = modern.record_va(*THIRD_DOWN, table_va=rows.TABLE_VA) + 0x44
        self.assertEqual([e["va"] for e in receipt["edits"]], [f"0x{va:x}"])
        changed = [i for i, (a, b) in enumerate(zip(old, upgraded)) if a != b]
        data = modern._offset(old, va)
        self.assertEqual([i for i in changed if i >= 0x1000], [data])          # the chain byte 0 -> 2
        self.assertTrue(all(i < 0x1000 for i in changed if i != data))         # the rest: the section digest only
        self.assertEqual(rows.apply(upgraded)[0], upgraded)                     # replay is a no-op


@unittest.skipUnless(legacy.XBE.is_file() and legacy.HAVE_UNICORN,
                     "private retail default.xbe and Unicorn required for bounded native-code tests")
class ThirdDownBackNativeTests(unittest.TestCase):
    TEAM, STACK, STOP = legacy.ExecutionTests.TEAM, legacy.ExecutionTests.STACK, legacy.ExecutionTests.STOP
    boot = legacy.ExecutionTests.boot
    player = legacy.ExecutionTests.player
    call = legacy.ExecutionTests.call
    unit = legacy.ExecutionTests.unit
    lookup = legacy.ExecutionTests.lookup
    # four backs: the starter, RB2, RB3, RB4 (rank 0..3; side order as the weekly sort writes it)
    BACKS = [(RB, 0, 2), (RB, 1, 0), (RB, 2, 1), (RB, 3, 3)]

    @classmethod
    def setUpClass(cls):
        cls.retail = legacy.XBE.read_bytes()
        cls.patched = rows.apply(legacy.prepare(cls.retail))[0]
        cls.old = revision_1(cls.patched)

    def ranks(self, uc):
        return [(struct.unpack("<H", uc.mem_read(self.player(i) + 0x28, 2))[0] >> 10) & 7 for i in range(len(self.BACKS))]

    def swap_in_row(self, uc, row_unit_slot, a, b):
        """The SPECIAL screen's swap of two players in one row (what moving a player to a row's top does)."""
        self.unit(uc, *row_unit_slot)
        self.call(uc, 0x2442E8, until=0x244308, ecx=self.player(a), esi=self.player(b), edi=self.TEAM)

    def pick(self, uc, ordinal, used=()):
        """The on-field picker for an RB slot asking for ``ordinal``, with ``used`` players already placed."""
        context, lists, assigned = self.TEAM + 0x8000, self.TEAM + 0x9000, self.TEAM + 0x9800
        uc.mem_write(context, struct.pack("<II", self.TEAM, 0))
        fields = [struct.unpack("<H", uc.mem_read(self.player(i) + 0x28, 2))[0] for i in range(len(self.BACKS))]
        cursor = lists
        for channel in range(29):
            uc.mem_write(context + 0x9C + channel * 4, struct.pack("<I", cursor))
            if channel in (1, 15):     # the RB rank list and the independent power list (position pools)
                shift = 10 if channel == 1 else 13
                order = sorted(range(len(self.BACKS)), key=lambda i: (fields[i] >> shift) & 7)
                uc.mem_write(cursor, bytes(order))
                cursor += len(order)
        uc.mem_write(cursor, b"\xff")
        uc.mem_write(0xAC26B8, bytes(4))  # no saved formation substitution
        for n, i in enumerate(used):
            uc.mem_write(assigned + 4 * n, struct.pack("<I", self.player(i)))
        return self.call(uc, 0xE8790, ecx=context, edx=0, stack=(0, 0, assigned, len(used), 0, RB_KIND, ordinal),
                         limit=50000)

    def test_the_starter_is_not_in_3drb_and_its_top_is_rb2(self):
        uc = self.boot(self.BACKS, payload=self.patched)
        self.call(uc, 0x243790, ecx=self.TEAM, limit=1000000)                    # the screen-entry compactor
        self.assertEqual(self.lookup(uc, 0, RB, 0), self.player(0))              # Offense RB row: the starter
        self.assertEqual([self.lookup(uc, r, RB, 2) for r in range(3)],
                         [self.player(1), self.player(2), self.player(3)])       # 3DRB: RB2, RB3, RB4
        self.assertNotIn(self.player(0), [self.lookup(uc, r, RB, 2) for r in range(4)])

    def test_moving_a_back_into_3drb_makes_him_rb2_and_the_starter_keeps_every_rb_slot(self):
        uc = self.boot(self.BACKS, payload=self.patched)
        self.swap_in_row(uc, THIRD_DOWN, 1, 2)            # put RB3 at the top of 3DRB
        self.assertEqual(self.ranks(uc), [0, 2, 1, 3])     # the starter keeps rank 0; RB3 is now rank 1 (RB2)
        self.assertEqual(self.lookup(uc, 0, RB, 2), self.player(2))
        # every shipped passing and base set asks for RB ordinal 0: the starter, then the 3DRB back behind him
        self.assertEqual(self.pick(uc, 0), self.player(0))
        self.assertEqual(self.pick(uc, 0, used=(0,)), self.player(2))
        self.assertEqual(self.pick(uc, 2), self.player(2))  # what 3DRB itself names
        self.assertEqual(self.pick(uc, 1), self.lookup(uc, 0, RB, 1))  # PWRB (the power order) is untouched

    def test_revision_1_put_the_3drb_back_in_every_play(self):
        # negative control: the beta-80 RC table, the same move to the top of 3DRB
        uc = self.boot(self.BACKS, payload=self.old)
        self.assertEqual(self.lookup(uc, 0, RB, 0), self.player(0))
        self.swap_in_row(uc, THIRD_DOWN, 0, 2)            # 3DRB row 0 was the starter himself
        self.assertEqual(self.ranks(uc)[:3], [2, 1, 0])
        self.assertEqual(self.pick(uc, 0), self.player(2))  # the 3DRB back took the RB slot of every formation

    def test_power_back_moves_only_the_power_order(self):
        uc = self.boot(self.BACKS, payload=self.patched)
        self.call(uc, 0x243790, ecx=self.TEAM, limit=1000000)
        top = self.lookup(uc, 0, RB, 1)
        other = next(self.player(i) for i in range(1, 4) if self.player(i) != top)
        ranks = self.ranks(uc)
        self.unit(uc, 3, 12)
        self.call(uc, 0x2442E8, until=0x244308, ecx=top, esi=other, edi=self.TEAM)
        self.assertEqual(self.ranks(uc), ranks)             # the RB rank order (and so RB1) is unchanged
        self.assertEqual(self.pick(uc, 0), self.player(0))
        self.assertEqual(self.lookup(uc, 0, RB, 1), other)


if __name__ == "__main__":
    unittest.main()
