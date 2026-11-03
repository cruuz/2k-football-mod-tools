"""b780 n2: MyCareer "play the moments" hung at the punt and the CPU never snapped (Mike Oneal, 2026-11-02).

Supersim (Sim to next appearance, or No at the backup prompt) arms a wait while MyPlayer is off the field. When he
comes on for a punt, mode_ff_hold_snap holds both native CPU snap entries (2D37E0, 2ED020) until mode_ff_settled sees
every on-field actor settled. The settled test used the native readiness check 1FF940 for every actor, and 1FF940
counts the 0x50F1BC stance as ready only for role byte 0. On the released v0.8 disc (emulator run N2H, a CPU punt in
MyCareer fast forward) both punt-return jammers stood in that stance with role byte 18 for the whole pre-snap, so a
punt could never settle: the snap stayed held and the game sat at the punt.

The fix: the 0x50F1BC stance with no pending clip (+0x110) settles like the 0x50F1E4 stance (the native stance
family of 1FFBC0), and the snap is never held into the last 3 seconds of the play clock, so a pre-snap that does not
settle can no longer stop the game. Installed owner on the retail executable, native binder, manager dispatch and
readiness under Unicorn; the actors are the scheduler fixture's declared pre-snap scene.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes

CLOCK = 0x42200000          # native initial play clock, 40 seconds
JAMMER_STANCE, SET_STANCE = 0x50F1BC, 0x50F1E4


def f32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; native x86 proofs require it")
class PuntSettleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.payload = mode.apply(cls.retail)[0]

    @staticmethod
    def machine():
        from tests.nfl2k5_supersim_scheduler import Machine
        return Machine

    @staticmethod
    def jammers(m, pending=0):
        """Two set punt-return jammers as the released disc showed them: stance 0x50F1BC, role byte 18."""
        for actor in m.actors[9:11]:
            desc = m.get(actor + 0x10)
            m.put(desc + 4, JAMMER_STANCE)
            m.put(desc + 0x110, pending)
            m.uc.mem_write(actor + 0x2C, bytes((18,)))

    def test_native_readiness_refuses_a_set_jammer(self):
        """The cause: retail 1FF940 says not ready for a jammer's stance, ready for the same stance at role 0."""
        with self.machine()(self.payload) as m:
            m.setup()
            self.jammers(m)
            self.assertEqual(m.call(0x1FF940, ecx=m.actors[9]), 0)
            m.uc.mem_write(m.actors[9] + 0x2C, b"\0")
            self.assertEqual(m.call(0x1FF940, ecx=m.actors[9]), 1)

    def test_set_jammers_settle_but_a_pending_clip_or_other_stance_does_not(self):
        with self.machine()(self.payload) as m:
            m.setup()
            self.assertEqual(m.call("mode_ff_settled"), 1)
            self.jammers(m)
            self.assertEqual(m.call("mode_ff_settled"), 1)
            # A queued clip still blocks, exactly as 1FF940 blocks the 0x50F1E4 stance.
            self.jammers(m, pending=m.OUT + 0x1234)
            self.assertEqual(m.call("mode_ff_settled"), 0)
            self.jammers(m)
            # Any other class 1FF940 refuses still blocks (a walking actor is not settled).
            m.put(m.get(m.actors[10] + 0x10) + 4, 0x50F4EC)
            self.assertEqual(m.call("mode_ff_settled"), 0)
            m.put(m.get(m.actors[10] + 0x10) + 4, SET_STANCE)
            self.assertEqual(m.call("mode_ff_settled"), 1)
            # The other settled conditions are unchanged: a queued native snap (event 28) still refuses the hand-back.
            m.call(0x1CF5E0, ecx=m.actors[3])
            self.assertEqual(m.call("mode_ff_settled"), 0)

    def test_punt_appearance_hands_back_with_the_jammers_set(self):
        """MyPlayer off the field, then on for a punt with both jammers set: the wait ends at the settled frame,
        the controller is his and the play clock is full, for punt units on both sides."""
        for position in (2, 4, 10, 11):        # P, CB, OLB, ILB: kicking and return units
            for away in (False, True):
                with self.subTest(position=position, away=away), self.machine()(self.payload) as m:
                    m.setup(position, away)
                    m.absent()
                    self.jammers(m)
                    m.put(0xE602BC, 6)                       # play kind: punt
                    m.put(m.state + 2736, 2)                 # this fixture has no play-call scene
                    def update():
                        step = m.counts["updates"]
                        if step == 2:
                            m.present(); m.put(0xE602B8, 12)
                        if step == 4:
                            m.put(0xE602B8, 13)
                        self.assertEqual(m.get(0xBD8210), 0xFFFFFFFF)
                    m.on_update = update
                    m.presented_frame()
                    self.assertEqual(m.counts["updates"], 4)
                    self.assertEqual((m.get(m.state + 2708), m.get(m.state + 2716)), (0, 0))
                    self.assertEqual(m.get(m.get(0xE60294) + 16), CLOCK)
                    self.assertEqual(m.get(0xBD8210), 0)
                    self.assertEqual(m.call("mode_ff_hold_snap"), 0)

    def test_unsettled_pre_snap_never_holds_the_snap_into_the_last_three_seconds(self):
        """A pre-snap that never settles (here a jammer with a pending clip) keeps the wait, but the snap guard lets
        both native CPU snap entries run once the play clock is under 3 seconds."""
        with self.machine()(self.payload) as m:
            m.setup()
            self.jammers(m, pending=m.OUT + 0x1234)
            m.put(m.state + 2708, 1)
            m.put(m.state + 2716, 1)
            clock = m.get(0xE60294) + 16
            self.assertEqual(m.call("mode_ff_settled"), 0)
            for seconds, held in ((40.0, 1), (12.4, 1), (3.5, 1), (3.0, 0), (2.0, 0), (0.0, 0)):
                with self.subTest(seconds=seconds):
                    m.put(clock, f32(seconds))
                    self.assertEqual(m.call("mode_ff_hold_snap"), held)
            m.put(clock, f32(40.0))
            for entry in (0x2D37E0, 0x2ED020):
                self.assertEqual(m.call(entry, ecx=m.body), 0)       # held: returns before the native body
            m.put(clock, f32(2.0))
            # Released: each entry reaches its own native body (the first instruction after the guard).
            for entry, body in ((0x2D37E0, 0x2D37E6), (0x2ED020, 0x2ED025)):
                with self.subTest(entry=hex(entry)):
                    m.call(entry, ecx=m.body, stop=body)
                    self.assertEqual(m.reg("EIP"), body)

    def test_sources_carry_the_fix(self):
        source = (ROOT / "tools/mycareer_mode/runtime.c").read_text()
        settled = source[source.index("static NI u32 mode_ff_settled"):source.index("u32 mode_ff_hold_snap")]
        self.assertIn("0x50f1bc", settled)
        self.assertIn("0x110", settled)
        hold = source[source.index("u32 mode_ff_hold_snap"):source.index("u32 FC mode_ff_ready")]
        self.assertIn("0x40400000", hold)


if __name__ == "__main__":
    unittest.main()
