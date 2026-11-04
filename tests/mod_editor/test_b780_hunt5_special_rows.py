"""b780 hunt5: what the SPECIAL 3DRB row does on the field, proved with the game's own code.

Noah (11/03): "make sure every movement in the special part of the depth chart does something accurately, and it
doesn't permanently make someone in a special position a starter somewhere else. If I make someone a third down back,
they shouldn't be in every single play. The starting halfback should have priority."

Revision 1 of the SPECIAL rows (beta-76.4 to the beta-80 RC) drew 3DRB as chain 0: the RB rank list itself. Putting a
back at the top of 3DRB made him RB1, and RB1 is the back every shipped formation asks for first (ordinal 0 in all
1,048 passing and 516 base RB slots of the v0.9 books). Revision 3 (b780 sub1) draws 3DRB as chain 3, the RB side order
from its second place, which no formation asks for: the Offense RB order never moves, and the third-down back comes in
only through nfl2k5_lineup_roles on obvious passing downs.

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


def previous(payload: bytes, revision: int) -> bytes:
    """The same applied executable with revision ``revision``'s role records, digests repinned."""
    buf = bytearray(payload)
    for row in rows._rows_for(revision):
        legacy.put(buf, modern.record_va(row[0], row[1], table_va=rows.TABLE_VA), rows._role_record(row))
    _repin(buf)
    return bytes(buf)


def revision_1(payload: bytes) -> bytes:
    """The beta-76.4 .. beta-80 RC table (3DRB = the RB rank list itself)."""
    return previous(payload, 1)


class SpecialRowRevisionTests(unittest.TestCase):
    """Layout contract and the in-place upgrade, on the synthetic executable."""

    @classmethod
    def setUpClass(cls):
        cls.storage_pin = patch.object(storage, "RETAIL_CONTENT_SHA256", hashlib.sha256(bytes(storage.RETAIL_SIZE)).hexdigest())
        cls.storage_pin.start()
        cls.addClassCleanup(cls.storage_pin.stop)
        cls.patched = rows.apply(legacy.prepare(legacy.fixture()))[0]

    def test_every_role_row_reads_its_own_order(self):
        special = {r["abbreviation"]: (r["position"], r["chain"]) for r in modern.read_depth_chart_units(self.patched)["SPECIAL"]}
        self.assertEqual({k: special[k] for k in ("LGUN", "RGUN", "GAD", "3DRB", "PWRB")},
                         {"LGUN": (3, 6), "RGUN": (4, 6), "GAD": (3, 7), "3DRB": (RB, 3), "PWRB": (RB, 1)})
        self.assertEqual((rows.status(self.patched), rows.revision(self.patched)), ("applied", rows.REVISION))

    def test_previous_tables_read_previous_and_upgrade_only_their_role_records(self):
        changed = {1: {"LGUN", "RGUN", "GAD", "3DRB"}, 2: {"LGUN", "RGUN", "GAD", "3DRB"}}
        for revision, labels in changed.items():
            old = previous(self.patched, revision)
            self.assertEqual((rows.status(old), rows.revision(old)), ("previous", revision))
            upgraded, receipt = rows.apply(old)
            self.assertEqual(upgraded, self.patched)
            self.assertEqual(receipt["upgraded_from"], f"revision {revision}")
            self.assertEqual({e["label"][len("special_"):-len("_chain")] for e in receipt["edits"]}, labels)
            data = {modern._offset(old, int(e["va"], 16)) for e in receipt["edits"]}
            diff = [i for i, (a, b) in enumerate(zip(old, upgraded)) if a != b]
            self.assertEqual({i for i in diff if i >= 0x1000}, data)     # one chain byte each, plus the digest
            self.assertEqual(rows.apply(upgraded)[0], upgraded)


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

    def test_moving_a_back_into_3drb_never_moves_the_offense_rb_order(self):
        uc = self.boot(self.BACKS, payload=self.patched)
        self.call(uc, 0x243790, ecx=self.TEAM, limit=1000000)                    # the screen-entry compactor
        ranks = self.ranks(uc)
        top = self.lookup(uc, 0, RB, 3)                                           # 3DRB row 0 = RB side row 1
        other = next(self.player(i) for i in range(4) if self.player(i) not in (top, self.lookup(uc, 0, RB, 1)))
        self.unit(uc, *THIRD_DOWN)
        self.call(uc, 0x2442E8, until=0x244308, ecx=top, esi=other, edi=self.TEAM)
        self.assertEqual(self.ranks(uc), ranks)                                   # the Offense RB order is untouched
        self.assertEqual(self.lookup(uc, 0, RB, 3), other)                        # the new 3DRB
        self.assertEqual(self.pick(uc, 0), self.player(0))                        # every RB slot still takes the starter
        self.assertEqual(self.pick(uc, 3), other)                                 # what 3DRB itself names

    def test_revision_1_put_the_3drb_back_in_every_play(self):
        # negative control: the beta-80 RC table, a move to the top of 3DRB
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
