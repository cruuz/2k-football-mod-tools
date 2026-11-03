"""b780-cv3: the b776 defender-ball-play flights with nfl2k5_dive_window (Unicorn, private fixtures; skipped when absent).

The flights of tests/mod_editor/test_nfl2k5_db_ball_play_unicorn.FrameTests (Bear Man 1 man defender, real release,
event dispatch, behavior 37, the reaction task 0x2E7240 with the ball-play decision 0x1F52C0 every tick, native
steering and locomotion on synthetic clips; supplied receiver and ball paths): with Defenders break on the thrown
ball, the curl ball draws a leap from 2.73 yd while the defender is moving away from the ball's path; with the dive
window he keeps running and finishes on the catch point. Go and out balls draw no leap either way. Offline
instruction results for the stated inputs, not a played game.
"""
from pathlib import Path
import math
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_db_ball_play as ball, nfl2k5_dive_window as dive  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe  # noqa: E402

try:
    from tests.nfl2k5_cpu_ai_native import ball_frame_class, uc, x86, YD
except ImportError:  # pragma: no cover - Unicorn is optional
    uc = None


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class FlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_nfl2k5_db_ball_play_unicorn import atl_body, coverage_nodes
        cls.node = next(n for _s, n in coverage_nodes(atl_body(), 183) if n.op == 0x0E)
        cls.Frame = ball_frame_class()
        cls.dbp, _ = ball.apply(retail_xbe())
        cls.both, _ = dive.apply(cls.dbp)

    def flight(self, payload, route, seconds=1.5):
        """The b776 flight (same paths, ball and component order); returns the decisions and the end distance."""
        from tests.nfl2k5_coverage_trail_frame import DT
        m = self.Frame(payload, self.node, direction=1)
        paths = {"go": lambda t: (8 * YD, (12 + 8.5 * t) * YD, 0, 8.5 * YD),
                 "out": lambda t: ((8 + 8 * t) * YD, 12 * YD, 8 * YD, 0),
                 "curl": lambda t: (8 * YD, (12 - t) * YD, 0, -YD)}
        path = paths[route]
        x, z, vx, vz = path(0)
        m.place(m.target, x, z, vx, vz)
        start = {"go": (x, z - YD, 0, 8.5 * YD), "out": (x - YD, z, 8 * YD, 0), "curl": (x, z + YD, 0, 0)}
        m.place(m.p, *start[route])
        cx, cz, _, _ = path(seconds)
        qx, qz = 0.0, -5 * YD
        self.assertTrue(m.release(catch=(cx, cz)))
        m.put(0xE602C0, 4)
        m.put(0x2010000, 0)
        decisions, log = [], {}
        hooks = [m.uc.hook_add(uc.UC_HOOK_CODE, lambda u, a, s, d: log.__setitem__(
                     "result", u.reg_read(x86.UC_X86_REG_EAX)), begin=0x2E729A, end=0x2E729A),
                 m.uc.hook_add(uc.UC_HOOK_CODE, lambda u, a, s, d: log.__setitem__(
                     "dist", struct.unpack("<f", u.mem_read(u.reg_read(x86.UC_X86_REG_ESP) + 0x18, 4))[0]),
                     begin=0x1F56CB, end=0x1F56CB)]
        for frame in range(int(seconds / DT) + 1):
            t = frame * DT
            x, z, vx, vz = path(t)
            m.uc.mem_write(m.target + 0xB30, struct.pack("<8f", x, 0, z, 1, vx, 0, vz, 0))
            s = t / seconds
            m.uc.mem_write(0x2010100, struct.pack("<8f", qx + (cx - qx) * s, 180 + 3600 * s * (1 - s) - 38 * s,
                                                  qz + (cz - qz) * s, 1, (cx - qx) / seconds,
                                                  3600 * (1 - 2 * s) / seconds - 38 / seconds, (cz - qz) / seconds, 0))
            m.f32(0xB71D00, 0.5 + t); m.f32(0xB71D0C, DT); m.put(0xB71D10, 100 + frame)
            log.clear()
            m.component(0x214FB0, ecx=m.p)
            if log.get("result") is not None:
                decisions.append((frame, log["result"], log.get("dist")))
            for va, kwargs in ((0x1CD5D0, dict(ecx=m.p)), (0x28DFE0, {}), (0x218010, dict(esi=m.p)), (0x28E360, {})):
                m.component(va, **kwargs)
        for h in hooks:
            m.uc.hook_del(h)
        px, pz = m.readf(m.transform + 0x30), m.readf(m.transform + 0x38)
        return decisions, math.hypot(px - cx, pz - cz) / YD

    def commits(self, decisions):
        return [(f, r, None if d is None else round(d / YD, 2)) for f, r, d in decisions if r >= 2]

    def test_curl_leap_from_far_becomes_a_run_to_the_catch_point(self):
        old, old_end = self.flight(self.dbp, "curl")
        new, new_end = self.flight(self.both, "curl")
        self.assertEqual([(f, r) for f, r, _d in self.commits(old)], [(62, 2)])
        self.assertGreater(self.commits(old)[0][2], 2.5)                  # the db_ball_play leap from 2.73 yd
        self.assertEqual(self.commits(new), [])
        self.assertLess(new_end, 0.5)                                      # on the catch point at the catch
        self.assertLess(new_end, old_end)

    def test_go_and_out_balls_are_unchanged(self):
        for route in ("go", "out"):
            old, old_end = self.flight(self.dbp, route)
            new, new_end = self.flight(self.both, route)
            self.assertEqual(self.commits(old), [], route)
            self.assertEqual([(f, r) for f, r, _d in new], [(f, r) for f, r, _d in old], route)
            self.assertAlmostEqual(new_end, old_end, places=3, msg=route)


if __name__ == "__main__":
    unittest.main()
