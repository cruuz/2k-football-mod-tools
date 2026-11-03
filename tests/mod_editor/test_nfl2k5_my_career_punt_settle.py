"""b780 n2: MyCareer "play the moments" hung at the punt and the CPU never snapped (Mike Oneal, 2026-11-02).

"Play the moments" is Supersim to MyPlayer's snaps (No at the backup prompt, or Sim to next appearance). While he is
off the field Supersim runs and arms a wait; when he comes on, the hand-back gives him his controller at a settled
pre-snap and, if his policy lets him call this side's play ("You call every play", the default), reopens the native
play-call screen for his side. At a punt the kicking unit's roles have already started the kick meter, and the
play-call screen's camera (state 6) cancels it: the per-frame kick HUD update BAFA0 treats every camera state other
than 8, 9, 10 and 12 as "no kick" and calls BACF0, which clears B72694. The CPU punter's pre-snap task 2ED020 snaps
only when the meter is done (B72710 == 8) AND armed (B72694 != 0), and nothing re-arms it for a call that is not
re-committed, so the punter waits forever. A backup CB, safety or linebacker whose first appearance is the punt return
on the opponent's first possession hits this every game.

The fix: at a punt or field goal (play kind E602BC 6 or 3) the hand-back never reopens the play-call screen;
MyPlayer plays the CPU's call with his own controller. And the snap hold never reaches into the last 3 seconds of
the play clock, so a pre-snap that never settles can no longer stop the game either. Installed owner on the retail
executable; native binder, manager dispatch, readiness and kick HUD code under Unicorn; the play-call screen entries
are counted boundaries (this fixture has no menu scene).
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
PUNT, FIELD_GOAL, RUN = 6, 3, 5
PLAY_CALL_ENTRIES = (0xACB90, 0x9FBE0)


def f32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; native x86 proofs require it")
class PuntHandbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.payload = mode.apply(cls.retail)[0]

    @staticmethod
    def machine():
        from tests.nfl2k5_supersim_scheduler import Machine
        return Machine

    def handback(self, kind, position=4, away=True):
        """MyPlayer off the field, then on at a settled pre-snap of play kind `kind`, default call policy ("You call
        every play"). Returns the machine state after the presented frame and the play-call screen entries reached."""
        m = self.machine()(self.payload)
        m.setup(position, away)
        m.absent()
        m.put(0xE602BC, kind)
        calls = []
        for va in PLAY_CALL_ENTRIES:
            m.replace_stub(va, lambda va=va: (calls.append(va), m.ret()))
        def update():
            step = m.counts["updates"]
            if step == 2:
                m.present(); m.put(0xE602B8, 12)
            if step == 4:
                m.put(0xE602B8, 13)
        m.on_update = update
        m.presented_frame()
        return m, calls

    def test_kick_meter_is_cancelled_by_the_play_call_camera(self):
        """The cause, native code only: with the meter armed for a punt, one kick HUD update in the punt camera keeps
        it armed; one update in the play-call camera (state 6) cancels it (B72694 cleared, B72710 forced done)."""
        for camera, armed in ((10, 1), (6, 0), (11, 0)):
            with self.subTest(camera=camera), self.machine()(self.payload) as m:
                m.setup()
                for va, value in ((0xB72690, 1), (0xB72694, 1), (0xB72710, 1), (0xB726E8, 2),
                                  (0xB726DC, 0xFFFFFFFF), (0xB726E0, 0xFFFFFFFF), (0xB616C0, camera)):
                    m.put(va, value)
                m.replace_stub(0x70910, lambda: m.ret())     # pad rumble stop: a device service, not game state
                m.replace_stub(0x8A430, lambda: m.ret())     # HUD scene update: presentation only
                m.call(0xBAFA0, args=(0x3C888889,), budget=2000000)
                self.assertEqual(m.get(0xB72694), armed)
                if not armed:
                    self.assertEqual(m.get(0xB72710), 8)

    def test_cpu_punter_waits_while_the_meter_is_cancelled(self):
        """2ED020 (the CPU kicker's pre-snap task) takes its snap path only with the meter armed; cancelled, it
        returns through its wait branch (2ECD60) on every call and never reaches the snap request (1CF5E0)."""
        with self.machine()(self.payload) as m:
            m.setup()
            punter = m.actors[5]
            sub = m.ARENA + 0xC0000
            m.put(m.get(punter + 0x20) + 0x310, sub)
            m.put(sub, 0x2ED020)
            reached = []
            for va in (0x2ECD60, 0x1CF5E0):
                m.replace_stub(va, lambda va=va: (reached.append(va), m.ret()))
            m.put(0xB72710, 8)
            m.put(0xB72694, 0)
            for _ in range(5):
                self.assertEqual(m.call(0x2ED020, ecx=punter), 0)
            self.assertEqual(reached, [0x2ECD60] * 5)

    def test_punt_and_field_goal_handbacks_keep_the_cpu_call(self):
        """A defensive-side MyPlayer (CB on the return or block unit) under the default policy: at a punt or field
        goal the wait ends, his controller is bound and the play clock is full, but the play-call screen is not
        reopened, so the kick meter the kicking unit started stays alive."""
        for kind in (PUNT, FIELD_GOAL):
            with self.subTest(kind=kind):
                m, calls = self.handback(kind)
                try:
                    self.assertEqual(m.counts["updates"], 4)
                    self.assertEqual((m.get(m.state + 2708), m.get(m.state + 2716)), (0, 0))
                    self.assertEqual(m.get(m.state + 2740), 0)
                    self.assertEqual(calls, [])
                    self.assertEqual(m.get(m.get(0xE60294) + 16), CLOCK)
                    self.assertEqual(m.get(0xBD8210), 0)
                finally:
                    m.close()

    def test_scrimmage_handback_still_reopens_the_play_call(self):
        """Unchanged for an ordinary snap: the same appearance at a run play re-enters the native play-call screen
        for MyPlayer's side (the hand-back latch holds his side until the new call is accepted)."""
        m, calls = self.handback(RUN)
        try:
            self.assertEqual(m.get(m.state + 2708), 0)
            self.assertEqual(m.get(m.state + 2740), 0xE5FC60)
            self.assertEqual(calls, list(PLAY_CALL_ENTRIES))
        finally:
            m.close()

    def test_unsettled_pre_snap_never_holds_the_snap_into_the_last_three_seconds(self):
        """A pre-snap that never settles keeps the wait, but the snap guard lets both native CPU snap entries run
        once the play clock is under 3 seconds."""
        with self.machine()(self.payload) as m:
            m.setup()
            m.put(m.get(m.actors[9] + 0x10) + 4, 0x50F4EC)   # an actor 1FF940 never counts as set
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
            for entry, body in ((0x2D37E0, 0x2D37E6), (0x2ED020, 0x2ED025)):
                with self.subTest(entry=hex(entry)):
                    m.call(entry, ecx=m.body, stop=body)
                    self.assertEqual(m.reg("EIP"), body)

    def test_sources_carry_the_fix(self):
        source = (ROOT / "tools/mycareer_mode/runtime.c").read_text()
        ready = source[source.index("u32 FC mode_ff_ready"):source.index("u32 FC mode_ff_frame")]
        self.assertIn("G(0xE602BC)!=6 && G(0xE602BC)!=3 && mode_human", ready)
        hold = source[source.index("u32 mode_ff_hold_snap"):source.index("u32 FC mode_ff_ready")]
        self.assertIn("0x40400000", hold)


if __name__ == "__main__":
    unittest.main()
