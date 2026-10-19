"""Bounded native proofs for defenders breaking on the thrown ball. No game boot or witnessed pass.

Step 0 (the gate for this owner): with real retail defensive plays (ATL book, outer entry 308), every coverage
defender's real initializer maps release event 0x27 to behavior 37, and the real release, event queue, 0x27 handler,
dispatcher and behavior switch start behavior 37 for the man defender on the target. Then the owner's change: the
run-to point becomes the stored catch point and the reaction task runs at full throttle. Player skeletons, the
receiver registry row, the receiver and ball paths and the catch point are supplied inputs; private data is skipped
when absent.
"""
from pathlib import Path
import math
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_db_ball_play as ball, nfl2k5_db_ball_play_code as assembly
from mod_editor.core import nfl2k5_play_library as lib, nfl2k5_play_codec as codec
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.nfl2k5_cpu_ai_native import SpyMachine, uc, x86, YD, ball_frame_class

PLAYS = {11: "Key Zone", 25: "2 Man", 183: "Bear Man 1", 187: "Bear Deep Zone 3"}


def atl_body():
    from tests.mod_editor.test_nfl2k5_screen_hooks_unicorn import atl_resource
    return atl_resource()[32:]


def coverage_nodes(body, play):
    for slot, (_desc, nodes) in enumerate(lib.play_chains(body, play)[1]):
        found = [codec.Node.from_bytes(raw) for raw in nodes if raw[0] in (0x0D, 0x0E)]
        if found:
            yield slot, found[0]


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class StepZeroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.body = atl_body()
        cls.Frame = ball_frame_class()

    def test_every_coverage_defender_maps_release_to_behavior_37(self):
        seen = {13: 0, 14: 0}
        for play in PLAYS:
            for slot, node in coverage_nodes(self.body, play):
                m = self.Frame(self.retail, node)
                self.assertEqual(m.uc.mem_read(m.gameplay + 0x3E8 + 0x27, 1)[0], 37, (play, slot))
                seen[node.op] += 1
        self.assertGreaterEqual(seen[13], 15)
        self.assertGreaterEqual(seen[14], 10)

    def test_man_defender_on_the_target_runs_behavior_37_and_others_do_not(self):
        for play in (25, 183):
            for slot, node in coverage_nodes(self.body, play):
                if node.op != 0x0E:
                    continue
                m = self.Frame(self.retail, node)
                self.assertTrue(m.release(), (play, slot))
                self.assertIn(0x2E95F0, m.inits)
                self.assertEqual(m.get(m.task + 0x40), m.target)
                m = self.Frame(self.retail, node)
                m.place(m.players[2], -8 * YD, 12 * YD, 0, 0)
                self.assertFalse(m.release(receiver=m.players[2]), (play, slot))
                self.assertNotIn(0x2E95F0, m.inits)

    def test_zone_defender_reaction_is_the_native_coverage_lottery(self):
        slot, node = next(coverage_nodes(self.body, 11))
        reacted = {c: sum(self.Frame(self.retail, node, coverage=c, seed=7919 * k + 1).release() for k in range(12))
                   for c in (0.0, 1.0)}
        self.assertEqual(reacted, {0.0: 12, 1.0: 0})


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class CatchPointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = ball.apply(cls.retail)
        cls.node = next(n for _s, n in coverage_nodes(atl_body(), 183) if n.op == 0x0E)
        cls.Frame = ball_frame_class()

    def react(self, payload, direction, catch):
        m = self.Frame(payload, self.node, direction=direction)
        self.assertTrue(m.release(catch=catch(m)))
        return m

    def test_run_to_point_is_the_catch_point_and_the_timer_is_unchanged(self):
        for direction in (1, -1):
            catch = lambda m: (m.readf(m.target + 0xB30) + 3 * YD, m.readf(m.target + 0xB38) + 15 * YD * direction)
            old, new = self.react(self.retail, direction, catch), self.react(self.patched, direction, catch)
            target = catch(new)
            self.assertAlmostEqual(new.point()[0], target[0], places=2)
            self.assertAlmostEqual(new.point()[2], target[1], places=2)
            self.assertEqual(new.point()[1::2], old.point()[1::2])          # y and w keep the retail values
            self.assertNotAlmostEqual(old.point()[2], target[1], places=0)  # retail: receiver + 0.25 s, held depth
            self.assertEqual(new.readf(new.task + 0x60), old.readf(old.task + 0x60))
            self.assertEqual(new.get(new.task + 0x40), old.get(old.task + 0x40))

    def test_first_reaction_frame_runs_at_full_throttle(self):
        for payload, expected in ((self.retail, 0.84), (self.patched, 1.0)):
            m = self.react(payload, 1, lambda m: (m.readf(m.target + 0xB30), m.readf(m.target + 0xB38) + 15 * YD))
            m.put(0xE602C0, 4)
            m.put(0x2010000, 0)
            m.component(0x214FB0, ecx=m.p)
            self.assertAlmostEqual(m.readf(m.steer + 0x10), expected, places=6)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class CaveConditionTests(unittest.TestCase):
    """The owner's cave entered at its hook ABI: ESI task, EDI defender, the retail point at [ESP+0x24]."""

    @classmethod
    def setUpClass(cls):
        cls.payload, _ = ball.apply(retail_xbe())

    def run_point(self, *, flag=1, intended=True, catch=(300.0, 2400.0), defender=(0.0, 1800.0), direction=1):
        m = SpyMachine(self.payload, patched=False, direction=direction)
        code = ball.allocation(self.payload)["va"] + assembly.LABELS["point"]
        task, frame = m.SOURCE + 0x2000, m.STACK - 0x40
        retail_point = (111.0, 0.0, 1300.0 * direction, 1.0)
        m.uc.mem_write(frame + 0x24, struct.pack("<4f", *retail_point))  # 16-aligned at the hook
        m.u32(frame, m.STOP)
        receiver = m.RB
        m.u32(0xE3C000, receiver)
        m.u32(task + 0x40, receiver if intended else m.OTHER)
        m.u32(0xBF0E08, flag)
        m.uc.mem_write(0xBF0DF0, struct.pack("<4f", catch[0], 142.24, catch[1] * direction, 1.0))
        m.f32(m.P + 0x400 + 0x30, defender[0]); m.f32(m.P + 0x400 + 0x38, defender[1] * direction)
        m.f32(m.GAME + 0x18, 1200 * direction)
        for name, value in (("ESP", frame), ("ESI", task), ("EDI", m.P), ("EBX", 0x3456), ("EBP", 0x6789),
                            ("EAX", 0x789A), ("ECX", 0x1111), ("EDX", 0x2222), ("EFLAGS", 0x246)):
            m.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        m.uc.emu_start(code, m.STOP, timeout=1_000_000, count=2000)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), frame + 4)
        for name, value in (("ESI", task), ("EDI", m.P), ("EBX", 0x3456), ("EBP", 0x6789), ("EAX", 0x789A),
                            ("ECX", 0x1111), ("EDX", 0x2222)):
            self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_" + name)), value, name)
        self.assertEqual((m.uc.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7, 0)
        stored = struct.unpack("<4f", m.uc.mem_read(task + 0x20, 16))
        return stored, retail_point

    def test_valid_catch_point_replaces_x_and_z_only(self):
        for direction in (1, -1):
            stored, retail_point = self.run_point(direction=direction)
            self.assertEqual(stored, (300.0, 0.0, 2400.0 * direction, 1.0))

    def test_every_refusal_keeps_the_retail_point(self):
        cases = dict(no_catch_point=dict(flag=0), other_receiver=dict(intended=False),
                     behind_the_line=dict(catch=(300.0, 1100.0)), beyond_25_yd=dict(catch=(300.0, 1800.0 + 2300.0)),
                     not_a_number=dict(catch=(float("nan"), 2400.0)))
        for label, kwargs in cases.items():
            stored, retail_point = self.run_point(**kwargs)
            self.assertEqual(struct.pack("<4f", *stored), struct.pack("<4f", *retail_point), label)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class FrameTests(unittest.TestCase):
    """Native reaction task, steering and locomotion over the whole flight (synthetic clips and paths)."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = ball.apply(cls.retail)
        cls.node = next(n for _s, n in coverage_nodes(atl_body(), 183) if n.op == 0x0E)
        cls.Frame = ball_frame_class()

    def flight(self, payload, route, direction=1, seconds=1.5):
        from tests.nfl2k5_coverage_trail_frame import DT
        m = self.Frame(payload, self.node, direction=direction)
        d = direction
        paths = {"go": lambda t: (8 * YD, (12 + 8.5 * t) * YD * d, 0, 8.5 * YD * d),
                 "out": lambda t: ((8 + 8 * t) * YD, 12 * YD * d, 8 * YD, 0),
                 "curl": lambda t: (8 * YD, (12 - t) * YD * d, 0, -YD * d)}
        path = paths[route]
        x, z, vx, vz = path(0)
        m.place(m.target, x, z, vx, vz)
        start = {"go": (x, z - YD * d, 0, 8.5 * YD * d), "out": (x - YD, z, 8 * YD, 0), "curl": (x, z + YD * d, 0, 0)}
        m.place(m.p, *start[route])
        cx, cz, _, _ = path(seconds)
        qx, qz = 0.0, -5 * YD * d
        self.assertTrue(m.release(catch=(cx, cz)))
        m.put(0xE602C0, 4)
        m.put(0x2010000, 0)
        throttles = []
        for frame in range(int(seconds / DT) + 1):
            t = frame * DT
            x, z, vx, vz = path(t)
            m.uc.mem_write(m.target + 0xB30, struct.pack("<8f", x, 0, z, 1, vx, 0, vz, 0))
            s = t / seconds
            m.uc.mem_write(0x2010100, struct.pack("<8f", qx + (cx - qx) * s, 180 + 3600 * s * (1 - s) - 38 * s,
                                                  qz + (cz - qz) * s, 1, (cx - qx) / seconds,
                                                  3600 * (1 - 2 * s) / seconds - 38 / seconds, (cz - qz) / seconds, 0))
            m.f32(0xB71D00, 0.5 + t); m.f32(0xB71D0C, DT); m.put(0xB71D10, 100 + frame)
            m.component(0x214FB0, ecx=m.p)
            throttles.append(m.readf(m.steer + 0x10))
            for va, kwargs in ((0x1CD5D0, dict(ecx=m.p)), (0x28DFE0, {}), (0x218010, dict(esi=m.p)), (0x28E360, {})):
                m.component(va, **kwargs)
        px, pz = m.readf(m.transform + 0x30), m.readf(m.transform + 0x38)
        return math.hypot(px - cx, pz - cz) / YD, throttles

    def test_defender_ends_closer_to_the_catch_point_on_go_out_and_curl(self):
        for route in ("go", "out", "curl"):
            old, old_throttles = self.flight(self.retail, route)
            new, new_throttles = self.flight(self.patched, route)
            self.assertLess(new, old, route)
            self.assertLessEqual(max(old_throttles), 1.0)
            self.assertAlmostEqual(new_throttles[0], 1.0, places=6)
        old, _ = self.flight(self.retail, "out", direction=-1)
        new, _ = self.flight(self.patched, "out", direction=-1)
        self.assertLess(new, old)


if __name__ == "__main__":
    unittest.main()
