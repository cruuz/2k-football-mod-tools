"""Quicker deep and rollout throws, native: the game's own throw routines on supplied state (Unicorn, no game boot).

Retail and retail + nfl2k5_quick_long_release run the same fixtures.  What runs natively, from the supplied default.xbe:
the throw start's rate switch (0x2DA516..0x2DA590) for every one of the 204 throw clips in the executable's 20 tables
(descriptor type from the table, event-81 time t81 from the game's own event lookup 0xDF0D0), the throw restart's rate
(0x2DA654..0x2DA688) and the throw task tick 0x2D85D0 (with the game's own min/max helpers, the CPU hold reader 0x1992B0
and the animation slot it eases).  The fixture supplies: the task, state block, animation slot and controller record, the
CPU hold fraction (0xBE47C4), and the answer of the button reader 0x120960 (held or let go), which reads controller
tables and is replaced by that one answer.  The release timeline steps one logic frame (1/15 s, as the tick and the
animation do in the game) at a time: the clip advances by rate / 15, the tick eases the rate; event 80 (the cocked pose
and its rewrite of the stored rate) is not modelled, the release follows it within about two frames.  Skipped without
the pinned retail XBE.
"""
import struct
import sys
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_quick_long_release as q

try:
    import unicorn
    from unicorn import x86_const as x86
    from tools.nfl2k5_back_throws_replay import NativeMachine
except ImportError:  # pragma: no cover - unicorn or the shared native fixture is not in this tree
    unicorn = x86 = NativeMachine = None

# (table VA, descriptor count): the 20 throw tables the game initialises at 0x2D8840
TABLES = ((0xAD1388, 14), (0xAD1468, 14), (0xAD1548, 14), (0xAD1628, 2),
          (0xAD18C8, 10), (0xAD1828, 10), (0xAD1788, 10), (0xAD16E8, 10), (0xAD1648, 10), (0xAD1968, 10),
          (0xAD1B48, 10), (0xAD1A08, 10), (0xAD1AA8, 10), (0xAD1BE8, 10), (0xAD1DC8, 10), (0xAD1C88, 10),
          (0xAD1D28, 10), (0xAD1E68, 10), (0xAD1FA8, 10), (0xAD1F08, 10))
EVENT_RELEASE = 0x51
DT = 1.0 / 15.0                  # one logic frame
TYPE_COUNTS = {0: 14, 1: 42, 2: 146, 3: 2}


def retail_bytes():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes as _retail_bytes
    return _retail_bytes()


def clamp(value, low, high):
    return min(max(value, low), high)


def expected_start_rate(throw_type, t81, patched):
    f32 = lambda x: struct.unpack("<f", struct.pack("<f", x))[0]  # noqa: E731
    if throw_type == 1:
        return f32(3.0 * t81)
    if throw_type == 2:
        return clamp(f32(3.0 * t81), 1.0, f32(q.ROLLOUT_RATE_CAP) if patched else f32(1.2))
    if throw_type == 3:
        return q.DEEP_LOB_RATE if patched else 1.5
    return 1.0


if NativeMachine is not None:
    class ThrowMachine(NativeMachine):
        TASK, CTRL, STATE, ANIM, SLOT, SLOT2, TARGET = (0x2020000, 0x2020400, 0x2020800, 0x2021000, 0x2021400,
                                                        0x2021800, 0x2021C00)

        def __init__(self, payload):
            super().__init__(payload)
            self.held = 0
            self.uc.hook_add(unicorn.UC_HOOK_CODE, self._button_reader, begin=0x120960, end=0x120960)

        def _button_reader(self, uc, _address, _size, _user):
            """0x120960 (is the throw button still down) returns one supplied answer; the caller sees a normal return."""
            esp = uc.reg_read(x86.UC_X86_REG_ESP)
            ret = struct.unpack("<I", uc.mem_read(esp, 4))[0]
            uc.reg_write(x86.UC_X86_REG_EAX, self.held)
            uc.reg_write(x86.UC_X86_REG_ESP, esp + 4)
            uc.reg_write(x86.UC_X86_REG_EIP, ret)

        # ---- the clips
        def descriptors(self):
            rows = []
            for table, count in TABLES:
                for index in range(count):
                    va = table + 16 * index
                    root, kind = self.get(va + 4), self.get(va + 8) & 7
                    rows.append((va, root, kind))
            return rows

        def release_event_time(self, root):
            """The game's own event lookup 0xDF0D0: seconds of animation event 81 (the ball release) in a clip."""
            return self.call(0xDF0D0, (0.0,), ecx=root, edx=EVENT_RELEASE, fp=True)

        # ---- the throw start's rate switch
        def start_rate(self, descriptor, t81):
            self.f(descriptor + 0xC, t81)
            self.put(self.STATE + 0xE0, 0)
            sp = self.SP - 0x100
            self.uc.mem_write(sp, bytes(0x80))
            for name, value in (("ESP", sp), ("ESI", descriptor), ("EBX", self.STATE), ("EDX", 0), ("EDI", 0)):
                self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
            self.run(0x2DA516, 0x2DA590)
            return self.rf(self.STATE + 0xE0)

        # ---- the throw restart (0x2DA5D0): the rate it pushes and the copy it stores
        def restart_rates(self):
            task, state = self.TASK, self.STATE
            self.uc.mem_write(task, bytes(0x100))
            self.uc.mem_write(state, bytes(0x400))
            self.put(task + 0x10, state)
            self.put(state + 0x28, 0)
            self.put(state + 0xD0, self.TARGET)
            self.put(self.TARGET + 4, 0)
            sp = self.SP - 0x100
            self.uc.mem_write(sp, bytes(0x80))
            for name, value in (("ESP", sp), ("EBX", task), ("EDI", state), ("EBP", 0), ("EAX", 0), ("EDX", 0),
                                ("ECX", state)):
                self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
            self.run(0x2DA654, 0x2DA688)
            esp = self.uc.reg_read(x86.UC_X86_REG_ESP)
            return self.rf(esp + 8), self.rf(state + 0xE0)

        # ---- the throw task tick
        def setup_tick(self, rate0, human, hold=1.0, seconds=0.0):
            for base in (self.TASK, self.CTRL, self.STATE, self.ANIM, self.SLOT, self.SLOT2, self.TARGET):
                self.uc.mem_write(base, bytes(0x400))
            self.put(self.TASK + 0x00, 0x2030000)           # the thrower
            self.put(self.TASK + 0x0C, self.CTRL)
            self.put(self.TASK + 0x10, self.STATE)
            self.put(self.TASK + 0x14, self.ANIM)
            self.put(self.TASK + 0x24, 0x2030400)
            self.put(self.ANIM + 0x58, self.SLOT)
            self.put(self.ANIM + 0x74, self.SLOT2)
            self.put(self.CTRL + 0x00, 0 if human else 0xFFFFFFFF)   # -1 is the CPU controller marker
            self.put(self.CTRL + 0x08, 0)
            self.put(self.CTRL + 0x1C, 7)
            self.put(self.STATE + 0x00, 7)
            self.f(self.STATE + 0x08, seconds)
            self.put(self.STATE + 0xD4, self.TARGET)
            self.f(self.STATE + 0xE0, rate0)
            self.f(self.SLOT + 0x08, rate0)
            self.f(self.SLOT2 + 0x08, rate0)
            self.f(0xBE47C4, hold)                           # the CPU passer's hold fraction

        def tick(self):
            self.call(0x2D85D0, ecx=self.TASK)
            return self.rf(self.SLOT + 8)

        def stored_rate(self):
            return self.rf(self.STATE + 0xE0)

        def release_seconds(self, rate0, t81, mode, hold=1.0, tick_first=False, frames=120):
            """Seconds from the throw start to the event-81 release for one throw, stepping the real tick.

            mode: 'bullet' (a human holds the button to the release), 'tap' (a human lets go at once: a lob),
            'cpu' (the CPU passer; ``hold`` is its hold fraction, 1.0 = a bullet)."""
            human = mode in ("bullet", "tap")
            self.setup_tick(rate0, human, hold)
            self.held = 1 if mode == "bullet" else 0
            clip, rate = 0.0, rate0
            for frame in range(1, frames + 1):
                self.f(self.STATE + 0x08, frame * DT)         # the state block's clock, read by the CPU branch
                if tick_first:
                    rate = self.tick()
                before = clip
                clip += rate * DT
                if clip >= t81 - 1e-6:
                    return ((frame - 1) + (t81 - before) / (rate * DT)) * DT
                if not tick_first:
                    rate = self.tick()
            raise AssertionError("the clip never reached its release event")


@unittest.skipIf(NativeMachine is None, "unicorn and tools/nfl2k5_back_throws_replay.py are required for the native probe")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = retail_bytes()
        cls.retail = ThrowMachine(retail)
        cls.patched = ThrowMachine(q.apply(retail)[0])
        cls.clips = []
        for va, root, kind in cls.retail.descriptors():
            cls.clips.append(dict(va=va, root=root, type=kind, t81=cls.retail.release_event_time(root)))

    # ---- the rate switch, all 204 clips
    def test_the_tables_are_the_204_clips_of_four_types(self):
        counts = {}
        for clip in self.clips:
            counts[clip["type"]] = counts.get(clip["type"], 0) + 1
            self.assertGreater(clip["t81"], 0.3, hex(clip["va"]))
            self.assertLess(clip["t81"], 1.3, hex(clip["va"]))
        self.assertEqual(counts, TYPE_COUNTS)
        # the same clip tables in the patched image (the owner touches no table)
        self.assertEqual(self.patched.descriptors(), self.retail.descriptors())

    def test_start_rates_retail_and_patched_for_every_clip(self):
        for clip in self.clips:
            for label, machine, patched in (("retail", self.retail, False), ("patched", self.patched, True)):
                got = machine.start_rate(clip["va"], clip["t81"])
                want = expected_start_rate(clip["type"], clip["t81"], patched)
                self.assertAlmostEqual(got, want, places=5, msg=f"{label} {hex(clip['va'])} type {clip['type']}")

    def test_pocket_throws_and_the_plain_on_the_run_rows_keep_their_rates(self):
        for clip in self.clips:
            if clip["type"] in (0, 1):
                self.assertEqual(self.retail.start_rate(clip["va"], clip["t81"]),
                                 self.patched.start_rate(clip["va"], clip["t81"]), hex(clip["va"]))
                if clip["type"] == 1:
                    # a short or medium throw: 3 x t81, the ball is out in exactly five frames (1/3 s)
                    rate = self.patched.start_rate(clip["va"], clip["t81"])
                    self.assertAlmostEqual(clip["t81"] / rate, 1 / 3, places=5)

    def test_release_without_the_ease_never_comes_later_and_the_numbers_in_the_help_hold(self):
        rows = {kind: [] for kind in TYPE_COUNTS}
        for clip in self.clips:
            old = self.retail.start_rate(clip["va"], clip["t81"])
            new = self.patched.start_rate(clip["va"], clip["t81"])
            self.assertLessEqual(clip["t81"] / new, clip["t81"] / old + 1e-9, hex(clip["va"]))
            rows[clip["type"]].append((clip["t81"] / old, clip["t81"] / new))
        for kind in (0, 1):
            self.assertTrue(all(abs(a - b) < 1e-9 for a, b in rows[kind]), kind)
        deep = rows[3][0]
        self.assertAlmostEqual(deep[0], 0.726, places=2)
        self.assertAlmostEqual(deep[1], 0.544, places=2)
        run = sorted(rows[2])
        self.assertAlmostEqual(max(a for a, _b in run), 0.96, places=2)       # the slowest throw on the run, retail
        self.assertAlmostEqual(max(b for _a, b in run), 0.72, places=2)       # ... and with the owner
        self.assertLess(sorted(b for _a, b in run)[len(run) // 2], 0.34)      # the median is the pocket 1/3 s
        self.assertGreater(sorted(a for a, _b in run)[len(run) // 2], 0.41)

    # ---- the restart rate
    def test_the_restart_pushes_and_stores_the_new_rate(self):
        self.assertEqual(self.retail.restart_rates(), (1.5, 1.5))
        self.assertEqual(self.patched.restart_rates(), (2.0, 2.0))

    # ---- the tick
    def trajectory(self, machine, rate0, human, held=0, hold=1.0, frames=16):
        machine.setup_tick(rate0, human, hold)
        machine.held = held
        out = []
        for frame in range(1, frames + 1):
            machine.f(machine.STATE + 0x08, frame * DT)
            out.append(machine.tick())
        return out

    @staticmethod
    def lob_path(rate0, floor, frames):
        """What the tick does to a lob: down a twentieth a frame to the floor, never up, never past it."""
        path, rate = [], rate0
        for _ in range(frames):
            rate = max(floor, rate - 0.05) if rate > floor else rate
            path.append(rate)
        return path

    def test_a_lob_eases_by_a_twentieth_a_frame_down_to_the_new_floor_and_never_below(self):
        for rate0 in (2.6, 2.083, 2.0, 1.6, 1.55, 1.5, 1.2, 1.0):
            old = self.trajectory(self.retail, rate0, True)
            new = self.trajectory(self.patched, rate0, True)
            for got, want in zip(old, self.lob_path(rate0, 1.0, 16)):
                self.assertAlmostEqual(got, want, places=4, msg=("retail", rate0))
            for got, want in zip(new, self.lob_path(rate0, q.EASE_FLOOR, 16)):
                self.assertAlmostEqual(got, want, places=4, msg=("patched", rate0))
            self.assertTrue(all(n >= o - 1e-4 for o, n in zip(old, new)), rate0)     # never slower at any frame
        # the new floor: a rate already at or under 1.5 is not eased at all
        for rate0 in (1.5, 1.2, 1.0):
            self.assertEqual(self.trajectory(self.patched, rate0, True), [float(struct.unpack("<f", struct.pack("<f", rate0))[0])] * 16)
        self.assertAlmostEqual(self.trajectory(self.patched, 2.0, True)[-1], 1.5, places=4)
        self.assertAlmostEqual(self.trajectory(self.retail, 2.0, True)[-1], 1.2, places=4)    # 16 frames, still on its way to 1.0
        self.assertAlmostEqual(self.trajectory(self.retail, 1.5, True)[-1], 1.0, places=4)

    def test_a_held_button_is_never_eased(self):
        for machine in (self.retail, self.patched):
            for rate0 in (2.083, 2.0, 1.6, 1.2):
                for rate in self.trajectory(machine, rate0, True, held=1):
                    self.assertAlmostEqual(rate, rate0, places=4)

    def test_the_cpu_eases_toward_the_floor_plus_its_hold_share_of_the_excess(self):
        for rate0, hold in ((2.083, 0.2), (2.0, 0.2), (2.0, 0.6), (2.0, 0.0), (1.6, 0.0), (1.3, 0.3)):
            old = self.trajectory(self.retail, rate0, False, hold=hold, frames=26)
            new = self.trajectory(self.patched, rate0, False, hold=hold, frames=26)
            for path, floor in ((old, 1.0), (new, q.EASE_FLOOR)):
                want = floor + (rate0 - floor) * hold
                self.assertAlmostEqual(path[-1], min(rate0, want), places=3, msg=(rate0, hold, floor, path))
                self.assertTrue(all(b <= a + 1e-4 for a, b in zip(path, path[1:])), (rate0, hold, path))
            self.assertTrue(all(n >= o - 1e-4 for o, n in zip(old, new)), (rate0, hold))
        # a bullet (hold 1.0) keeps its rate in both
        for machine in (self.retail, self.patched):
            for rate in self.trajectory(machine, 2.083, False, hold=1.0):
                self.assertAlmostEqual(rate, 2.083, places=4)

    # ---- the release timeline
    def test_the_patched_release_is_never_later_for_any_clip_and_any_passer(self):
        gains = {}
        for tick_first in (False, True):
            for clip in self.clips:
                start_old = self.retail.start_rate(clip["va"], clip["t81"])
                start_new = self.patched.start_rate(clip["va"], clip["t81"])
                for mode, hold in (("bullet", 1.0), ("tap", 1.0), ("cpu", 1.0), ("cpu", 0.2)):
                    old = self.retail.release_seconds(start_old, clip["t81"], mode, hold, tick_first)
                    new = self.patched.release_seconds(start_new, clip["t81"], mode, hold, tick_first)
                    self.assertLessEqual(new, old + 1e-6, (hex(clip["va"]), mode, hold, tick_first))
                    gains.setdefault((clip["type"], mode, hold, tick_first), []).append((old, new))
        for (kind, mode, hold, tick_first), pairs in gains.items():
            if kind == 0 or (kind == 1 and hold == 1.0 and mode in ("bullet", "cpu")):
                # the plain on-the-run rows and every pocket throw that is not eased: byte for byte the same release
                self.assertTrue(all(abs(o - n) < 1e-6 for o, n in pairs), (kind, mode, hold))
            if kind == 1 and mode == "bullet":
                self.assertTrue(all(abs(o - 1 / 3) < 1e-6 for o, _n in pairs))              # the 1/3 s pocket release
        for tick_first in (False, True):
            deep = {key[1:3]: pairs[0] for key, pairs in gains.items() if key[0] == 3 and key[3] == tick_first}
            self.assertAlmostEqual(deep[("bullet", 1.0)][0] - deep[("bullet", 1.0)][1], 0.726 - 0.544, places=2)
            self.assertGreater(deep[("tap", 1.0)][0] - deep[("tap", 1.0)][1], 0.28)         # a tapped bomb
            self.assertGreater(deep[("cpu", 0.2)][0] - deep[("cpu", 0.2)][1], 0.25)         # a CPU lob
            self.assertLess(deep[("bullet", 1.0)][1], 0.55)
            run = sorted(gains[(2, "bullet", 1.0, tick_first)])
            self.assertAlmostEqual(run[-1][0], 0.96, places=2)                            # the slowest, retail
            self.assertAlmostEqual(max(n for _o, n in run), 0.72, places=2)               # ... and with the owner
            self.assertLess(sorted(n for _o, n in run)[len(run) // 2], 0.34)              # most are the pocket 1/3 s
            self.assertGreater(sorted(o for o, _n in run)[len(run) // 2], 0.41)
            taps = sorted(o - n for o, n in gains[(2, "tap", 1.0, tick_first)])
            self.assertGreater(taps[len(taps) // 2], 0.12)                                # a lob on the run
            self.assertGreater(taps[-1], 0.33)


if __name__ == "__main__":
    unittest.main()
