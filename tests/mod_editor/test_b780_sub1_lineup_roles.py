"""b780 sub1: situational lineup roles (nfl2k5_lineup_roles), with the game's own lineup builder and picker.

The released v0.9 executable (with and without the owner) and its roster run under Unicorn (NFL2K5_V09_XBE and
NFL2K5_V09_ROST_BODY; one-pool positions pair the running back orders, which the owner needs). One club's backs and
receivers get chosen depth rows and ratings in memory, then the native ctx builder (0xE80D0) and lineup builder
(0xE89F0) fill real formation personnel:
- Rule 1: the SPECIAL 3DRB (RB side row 1) plays the lead back on obvious passing downs when he is at least as good
  a receiver as the starter, on every club (MyCareer and old saves included).
- Rule 2: with no fullback, RB2 plays fullback, and the power back keeps his own slot.
- Rule 3: the SPECIAL GAD (WR side row 3) takes the carrier spot of a play that hands a receiver the ball when he is
  at least as fast as the slot's own pick, on every club.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, Machine, retail_bytes  # noqa: E402
from mod_editor.core import nfl2k5_lineup_roles as lr  # noqa: E402

I_FORM = bytes.fromhex("2b8d0000040005250607270809290b0a")      # X 7, Z 8, FB 9, lead back 10
GOAL_LINE = bytes.fromhex("398d0000000005250607272808480b2a")   # FB 9, power back 10 (RB ordinal 1)
SCR = 0x3009000
CTX, OUT, CAT, SIT, LIVE, L1, L2, PLAY, NODES = (SCR, SCR + 0x800, SCR + 0x900, SCR + 0xA00, SCR + 0xB00,
                                                 SCR + 0xB80, SCR + 0xC00, SCR + 0xD00, SCR + 0xE00)
HB, FB, TE, WR = 7, 8, 9, 3                                       # roster position bytes (+0x35)
CLUB = 0
V09_XBE = Path(os.environ.get("NFL2K5_V09_XBE", "") or "missing")
V09_ROST = Path(os.environ.get("NFL2K5_V09_ROST_BODY", "") or "missing")


def machine(payload: bytes, body: bytes) -> Machine:
    m = Machine(payload, trace_writes=False)
    m.uc.mem_write(0x10000, payload[:struct.unpack_from("<I", payload, 0x108)[0]])
    m.uc.mem_write(Machine.ARENA + 0x300, body)
    m.put(0xB72804, Machine.ARENA + 0x300)
    m.put(0xB72808, len(body) - 0x40)
    m.put(0xB7280C, len(body) - 0x40)
    m.fixup_roster(Machine.ARENA + 0x340)
    return m


class RetailRefusedTests(unittest.TestCase):
    def test_an_executable_without_paired_running_back_orders_is_refused(self):
        with self.assertRaisesRegex(lr.LineupRolesError, "paired running back orders"):
            lr.apply(retail_bytes())


@unittest.skipUnless(V09_XBE.is_file(), "NFL2K5_V09_XBE required")
class ReservationTests(unittest.TestCase):
    def test_a_first_pass_reservation_is_reused(self):
        from mod_editor.core import nfl2k5_sim_cb_tackles as tackles, nfl2k5_xbe_space as space
        xbe = V09_XBE.read_bytes()
        reserved, _ = space.extend_scaleout(xbe, lr.REQUESTS)       # what the build's first space pass does
        self.assertEqual(lr.status(reserved), "retail")
        installed, receipt = lr.apply(reserved)
        self.assertTrue(receipt["allocation"]["reserved_by_first_pass"])
        self.assertEqual(installed, lr.apply(xbe)[0])
        # the neighbouring cornerback tackle owner reads exactly as it did on the input (b780-int: on int the v0.9 RC's own
        # champions, honors, defensive try and so cornerback tackles read foreign since season1 Q73 rewrote the champions
        # owner; only the beta-79 revision reads previous, and no released disc carries the RC's)
        self.assertEqual((lr.status(installed), tackles.status(installed)), ("applied", tackles.status(xbe)))
        self.assertEqual(lr.apply(installed)[0], installed)


@unittest.skipUnless(HAVE_UC and V09_XBE.is_file() and V09_ROST.is_file(),
                     "Python unicorn, NFL2K5_V09_XBE and NFL2K5_V09_ROST_BODY required")
class LineupRolesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe, cls.body = V09_XBE.read_bytes(), V09_ROST.read_bytes()
        cls.native, cls.owner = machine(cls.xbe, cls.body), machine(lr.apply(cls.xbe)[0], cls.body)
        cls.team = cls.native.team_base + 500 * CLUB
        players = [cls.native.get(cls.team + 4 * i) for i in range(cls.native.get(cls.team + 0x11C) & 0xFF)]
        kind = {p: cls.native.uc.mem_read(p + 0x35, 1)[0] for p in players}
        spare = [p for p in players if kind[p] not in (0, 1, 2)]
        cls.backs = [p for p in players if kind[p] == HB][:4]
        cls.backs += [p for p in spare if p not in cls.backs and kind[p] not in (HB, FB, TE, WR)][:4 - len(cls.backs)]
        cls.fbs = [p for p in players if kind[p] == FB]
        cls.wrs = [p for p in players if kind[p] == WR][:5]
        cls.others = [p for p in players if kind[p] == HB and p not in cls.backs]
        assert len(cls.backs) == 4 and len(cls.wrs) == 5

    def setUp(self):
        # backs A (starter), P (power), T (3DRB), D: rank A P T D, side P T A D
        for m in (self.native, self.owner):
            for p in self.others:
                m.uc.mem_write(p + 0x35, bytes([WR + 1]))           # keep the club to these four backs
            for (rank, side, catch), p in zip(((0, 2, 80), (1, 0, 40), (2, 1, 60), (3, 3, 50)), self.backs):
                self.depth(m, p, HB, rank, side)
                m.uc.mem_write(p + 0x44, bytes([catch]))
                m.uc.mem_write(p + 0x3F, bytes([catch]))
            for p in self.fbs:
                m.uc.mem_write(p + 0x35, bytes([FB]))
            # receivers: rank WR1..WR5, the 2026 side order WR2, WR3, WR1, WR4 (GAD), WR5
            for rank, p in enumerate(self.wrs):
                self.depth(m, p, WR, rank, {0: 2, 1: 0, 2: 1}.get(rank, rank))
                m.uc.mem_write(p + 0x36, bytes([80]))
        self.A, self.P, self.T, self.D = self.backs
        self.X, self.Z, self.gad = self.wrs[0], self.wrs[1], self.wrs[3]

    @staticmethod
    def depth(m, p, position, rank, side):
        m.uc.mem_write(p + 0x35, bytes([position]))
        value = struct.unpack("<H", m.uc.mem_read(p + 0x28, 2))[0] & 0x3FF
        m.uc.mem_write(p + 0x28, struct.pack("<H", value | rank << 10 | side << 13))

    def lineup(self, m, cat, down=1, togo=10, human=True, play=0):
        m.put(0xE5FF80, 6)
        m.put(0xE602B4, 0)
        m.put(SIT + 4, down)
        m.uc.mem_write(SIT + 0x10, struct.pack("<4f", 0, 0, 0, 0))
        m.uc.mem_write(SIT + 0x20, struct.pack("<4f", 0, 0, togo * 91.44, 0))
        m.put(0xE602EC, SIT)
        m.put(LIVE + 0x1C, self.team); m.put(LIVE + 8, L1); m.put(L1 + 0xC, L2); m.f32(L2 + 4, 1.0)
        m.put(0xE60280, LIVE)
        m.put(0xE5775C + 4 * CLUB, 1 if human else 0)
        m.uc.mem_write(CTX, bytes(0x800))
        m.call(0xE80D0, ecx=self.team, edx=CTX, args=(0, 0), budget=50_000_000)
        m.uc.mem_write(CAT, cat)
        m.uc.mem_write(OUT, bytes(44))
        m.call(0xE89F0, ecx=CTX, edx=0, args=(CAT, play, OUT, 0), budget=20_000_000)
        return [m.get(OUT + 4 * i) for i in range(11)]

    def both(self, cat, **kw):
        return self.lineup(self.native, cat, **kw), self.lineup(self.owner, cat, **kw)

    # ------------------------------------------------------------------------------------------------ rule 1
    def receiver(self, p, value):
        for m in (self.native, self.owner):
            m.uc.mem_write(p + 0x44, bytes([value]))
            m.uc.mem_write(p + 0x3F, bytes([value]))

    def test_a_weaker_receiving_3drb_stays_out_on_every_club(self):
        # the 2026 / old-save layout: RB3 (T) at side row 1, a weaker receiver than the starter
        for human in (True, False):
            with self.subTest(human=human):
                native, owner = self.both(I_FORM, down=3, togo=8, human=human)
                self.assertEqual((native[10], owner[10]), (self.A, self.A))
                self.assertEqual(owner, native)

    def test_a_better_receiving_3drb_plays_3rd_and_8(self):
        self.receiver(self.T, 95)
        for human in (True, False):
            with self.subTest(human=human):
                native, owner = self.both(I_FORM, down=3, togo=8, human=human)
                self.assertEqual((native[10], owner[10]), (self.A, self.T))
                self.assertEqual(owner[:10], native[:10])          # every other slot as native

    def test_mycareer_keeps_its_starting_back(self):
        # MyCareer marks its club human and rewrites RB side = rank, so the 3DRB row is RB2 (P)
        for m in (self.native, self.owner):
            for rank, p in enumerate(self.backs):
                self.depth(m, p, HB, rank, rank)
        self.assertEqual(self.lineup(self.owner, I_FORM, down=3, togo=8)[10], self.A)   # P is the weaker receiver
        self.receiver(self.P, 95)
        self.assertEqual(self.lineup(self.owner, I_FORM, down=3, togo=8)[10], self.P)

    def test_only_obvious_passing_downs(self):
        self.receiver(self.T, 95)
        for down, togo, third in ((1, 10, False), (2, 9, False), (2, 10, True), (3, 4, False), (3, 5, True),
                                  (4, 5, True), (4, 2, False)):
            with self.subTest(down=down, togo=togo):
                lead = self.lineup(self.owner, I_FORM, down=down, togo=togo)[10]
                self.assertEqual(lead, self.T if third else self.A)

    def test_rule_1_off_and_native(self):
        payload = lr.apply(self.xbe, third_down=False)[0]
        off = machine(payload, self.body)
        self.assertEqual(lr.read_settings(payload)["third_down"], False)
        self.setUp_on(off)
        for p in (self.T,):
            off.uc.mem_write(p + 0x44, bytes([95]))
            off.uc.mem_write(p + 0x3F, bytes([95]))
        self.assertEqual(self.lineup(off, I_FORM, down=3, togo=8)[10], self.A)

    def setUp_on(self, m):
        saved = (self.native, self.owner)
        self.native = self.owner = m
        try:
            self.setUp()
        finally:
            self.native, self.owner = saved

    # ------------------------------------------------------------------------------------------------ rule 2
    def no_fullback(self):
        for m in (self.native, self.owner):
            for p in self.fbs:
                m.uc.mem_write(p + 0x35, bytes([TE]))

    def test_rb2_plays_fullback_not_the_deepest_back(self):
        self.no_fullback()
        native, owner = self.both(I_FORM)
        self.assertEqual((native[9], native[10]), (self.D, self.A))          # retail: the deepest back
        self.assertEqual((owner[9], owner[10]), (self.P, self.A))            # RB2
        self.assertEqual(owner[:9], native[:9])

    def test_the_power_back_keeps_his_slot(self):
        self.no_fullback()
        owner = self.lineup(self.owner, GOAL_LINE)
        self.assertEqual((owner[9], owner[10]), (self.T, self.P))            # the next back at FB

    def test_the_picker_outside_the_builder_keeps_retail(self):
        # the scheduled simulator calls the picker itself (0x102472..): an FB request keeps the retail order there
        self.no_fullback()
        picks = []
        for m in (self.native, self.owner):
            self.lineup(m, I_FORM)                                     # a fresh ctx for this club
            m.uc.mem_write(OUT, bytes(44))
            picks.append(m.call(0xE8790, ecx=CTX, edx=0, args=(4, 9, OUT, 11, 0, 11, 0), budget=5_000_000))
        self.assertEqual(picks[0], picks[1])

    # ------------------------------------------------------------------------------------------------ rule 3
    def play(self, m, *, handoff_to=8, family=0):
        """A play whose QB (slot 0) hands the ball to ``handoff_to`` and whose slot 8 carries (0x16)."""
        record = bytearray(0x60)
        struct.pack_into("<I", record, 4, family << 6)
        nodes = bytearray(8 * 13)
        nodes[0] = 0x13
        nodes[4] = handoff_to
        nodes[8] = 0x16
        for slot in range(11):
            start = {0: 0, 8: 1}.get(slot, 2)
            struct.pack_into("<II", record, 8 + slot * 8, 1, NODES + 8 * start)
        m.uc.mem_write(NODES, bytes(nodes))
        m.uc.mem_write(PLAY, bytes(record))
        return PLAY

    def test_the_gad_takes_the_carrier_spot(self):
        play = self.play(self.owner)
        self.play(self.native)
        native, owner = self.both(I_FORM, play=play)
        self.assertEqual((native[8], owner[8]), (self.Z, self.gad))
        self.assertEqual([s for s in range(11) if owner[s] != native[s]], [8])

    def test_every_club_needs_the_faster_man(self):
        play = self.play(self.owner)
        for human in (True, False):                                  # MyCareer and old saves: one rule
            with self.subTest(human=human):
                self.owner.uc.mem_write(self.gad + 0x36, bytes([80]))
                self.assertEqual(self.lineup(self.owner, I_FORM, play=play, human=human)[8], self.gad)  # as fast
                self.owner.uc.mem_write(self.gad + 0x36, bytes([70]))
                self.assertEqual(self.lineup(self.owner, I_FORM, play=play, human=human)[8], self.Z)
                self.owner.uc.mem_write(self.gad + 0x36, bytes([90]))
                self.assertEqual(self.lineup(self.owner, I_FORM, play=play, human=human)[8], self.gad)

    def test_other_plays_keep_their_receivers(self):
        for kw in (dict(handoff_to=7), dict(family=1)):              # the carrier is not this WR; a defensive play
            with self.subTest(**kw):
                play = self.play(self.owner, **kw)
                owner = self.lineup(self.owner, I_FORM, play=play)
                self.assertEqual(owner[8], self.Z)
        self.assertEqual(self.lineup(self.owner, I_FORM)[8], self.Z)  # no play


if __name__ == "__main__":
    unittest.main()
