"""b780-cv3: defenders leap only for balls they can reach (nfl2k5_dive_window). EXPERIMENTAL / UNWITNESSED.

Static owner checks on the pinned USA retail executable, the owner's cave run at its hook ABI with crafted frames
(Unicorn), and the real ball-play decision 0x1F52C0 with the hook installed (Unicorn, private fixtures; skipped when
absent). Every number is an offline instruction result for the stated inputs, not a played game.
"""
from pathlib import Path
import hashlib
import math
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_dive_window as dive, nfl2k5_dive_window_code as assembly  # noqa: E402
from mod_editor.core import nfl2k5_db_ball_play as ball, nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit  # noqa: E402

try:
    from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine as SpyMachine, uc, x86
except ImportError:  # pragma: no cover - Unicorn is optional
    SpyMachine = uc = x86 = None

YD = 91.44


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def test_code_fits_and_relocates_inside_its_allocation(self):
        self.assertLessEqual(len(assembly.CODE), dive.CODE_SIZE)
        code = dive.code_for(0x1500000)
        self.assertEqual(len(code), dive.CODE_SIZE)
        self.assertEqual(code[len(assembly.CODE):], b"\xcc" * (dive.CODE_SIZE - len(assembly.CODE)))
        for off, kind, symbol, _value in assembly.RELOCATIONS:
            self.assertEqual((kind, symbol), (1, "code"))   # only its own constants; no native call
            target = struct.unpack_from("<I", code, off)[0]
            self.assertTrue(0x1500000 <= target < 0x1500000 + len(assembly.CODE), hex(target))
        for name in ("k_reach", "k_beyond", "k_line2", "k_one"):
            self.assertLess(assembly.LABELS[name] + 4, len(assembly.CODE) + 1)
        self.assertAlmostEqual(struct.unpack_from("<f", assembly.CODE, assembly.LABELS["k_reach"])[0], 1.5 * YD, places=3)
        self.assertAlmostEqual(struct.unpack_from("<f", assembly.CODE, assembly.LABELS["k_beyond"])[0], 0.03 / 0.3, places=6)
        self.assertAlmostEqual(struct.unpack_from("<f", assembly.CODE, assembly.LABELS["k_line2"])[0], YD * YD, places=1)

    def test_site_is_one_call_then_the_native_zero_exit(self):
        (name, va, before, after), = dive.sites(0x14DA000)
        self.assertEqual((name, va, len(before), len(after)), ("dive_window", 0x1F56FF, 21, 21))
        self.assertEqual(XbeImage(self.retail).read(va, 21), before)
        self.assertEqual(after[0], 0xE8)
        self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], 0x14DA000 + assembly.LABELS["window"])
        self.assertEqual(after[5:7], b"\x85\xc0")                  # test eax, eax
        self.assertEqual(after[7:9], b"\x0f\x84")                  # jz
        self.assertEqual(va + 13 + struct.unpack_from("<i", after, 9)[0], dive.RETURN_ZERO)
        self.assertEqual(after[13:], b"\x90" * 8)
        # The site is followed by the native "mov eax, 2" exit, which the call keeps when the window says yes.
        self.assertEqual(XbeImage(self.retail).read(va + 21, 5), bytes.fromhex("b802000000"))

    def test_apply_is_idempotent_and_reads_back(self):
        self.assertEqual(dive.status(self.retail), "retail")
        out, receipt = dive.apply(self.retail)
        self.assertEqual((receipt["status"], dive.status(out), space.status(out)), ("applied", "applied", "applied"))
        again, second = dive.apply(out)
        self.assertEqual((again, second["status"], second["changed_bytes"]), (out, "already_applied", 0))
        self.assertEqual(receipt["edits"][0]["va"], hex(0x1F56FF))

    def test_composes_after_db_ball_play_and_leaves_it_applied(self):
        both, _ = dive.apply(ball.apply(self.retail)[0])
        self.assertEqual((ball.status(both), dive.status(both)), ("applied", "applied"))
        self.assertGreater(dive.allocation(both)["va"], ball.allocation(both)["va"])

    def test_foreign_site_and_foreign_prerequisites_are_refused(self):
        site = repin_edit(self.retail, 0x1F56FF, b"\x90" * 21)
        self.assertEqual(dive.status(site), "foreign")
        with self.assertRaises(dive.DiveWindowError):
            dive.apply(site)
        window = repin_edit(self.retail, 0x4EDD28, struct.pack("<f", 4 * YD))   # a different native window size
        self.assertEqual(dive.status(window), "foreign")
        task = repin_edit(self.retail, 0x2E73C3, bytes.fromhex("c7411c60000000"))  # another queued action
        self.assertEqual(dive.status(task), "foreign")

    def test_guards_match_retail(self):
        image = XbeImage(self.retail)
        for va, size, digest in dive.GUARDS:
            self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest, hex(va))

    def test_only_the_hook_changes_in_retail_sections(self):
        final, _ = dive.apply(self.retail)
        a, b = XbeImage(self.retail), XbeImage(final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, list(range(0x1F56FF, 0x1F56FF + 21)))   # the replaced 21 bytes and nothing else


class WiringTests(unittest.TestCase):
    def test_presets_options_and_late_owner_order(self):
        from mod_editor.core import mod_build, nfl2k5_build_settings as settings, nfl2k5_throw_tuning as tt
        self.assertEqual(space.LATE_OWNERS[-1], dive.OWNER)                  # after every other late owner
        self.assertLess(space.LATE_OWNERS.index(ball.OWNER), space.LATE_OWNERS.index(dive.OWNER))
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).db_dive_window, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["db_dive_window"], False, name)               # EXPERIMENTAL: off in every preset
        self.assertIn("db_dive_window", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_dive_window", "Defenders leap only for balls they can reach"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        self.assertIn(dive.REQUESTS[0], tt._selected_space_requests(db_dive_window=True))
        self.assertNotIn(dive.REQUESTS[0], tt._selected_space_requests())
        text = (ROOT / "mod_editor/core/nfl2k5_dive_window.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", dive.HELP_TEXT + dive.BUILD_CAPTION)

    def test_build_step_installs_after_the_other_late_owners_and_reads_back(self):
        import tempfile
        from mod_editor.core import mod_build
        retail = retail_xbe()
        plan = mod_build.BuildPlan(Path("source.xbe"), Path("target.xbe"), db_dive_window=True)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(retail)
            mod_build._dive_window_preflight(source, lambda *a: None)
            receipt = {"steps": [], "result": {}}
            mod_build._apply_dive_window(plan, source, receipt, lambda *a: None)
            self.assertEqual(receipt["result"]["db_dive_window"], "applied")
            self.assertEqual(dive.status(source.read_bytes()), "applied")
            mod_build._dive_window_preflight(source, lambda *a: None)          # an installed owner is not foreign
            foreign = Path(tmp) / "foreign.xbe"
            foreign.write_bytes(repin_edit(retail, 0x1F56FF, b"\x90" * 21))
            with self.assertRaises(ValueError):
                mod_build._dive_window_preflight(foreign, lambda *a: None)
            off = mod_build.BuildPlan(Path("source.xbe"), Path("target.xbe"))
            untouched = Path(tmp) / "untouched.xbe"
            untouched.write_bytes(retail)
            mod_build._apply_dive_window(off, untouched, {"steps": [], "result": {}}, lambda *a: None)
            self.assertEqual(untouched.read_bytes(), retail)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class CaveTests(unittest.TestCase):
    """The cave entered at its hook ABI: [ESP] return address, the decision's frame at ESP + 4, ESI the defender."""

    A, C = (0.0, 150.0, 900.0), (0.0, 120.0, 1500.0)   # the ball 0.3 s and 0.6 s ahead: +z at 2000 cm/s

    @classmethod
    def setUpClass(cls):
        cls.payload, _ = dive.apply(retail_xbe())
        cls.code = dive.allocation(cls.payload)["va"] + assembly.LABELS["window"]

    def run_window(self, *, side=2.0 * YD, depth=1200.0, velocity=(0.0, 0.0), cpu=True, catch=None,
                   catch_flag=1, receiver=True, a=None, c=None, fpu_depth=0):
        """side = the defender's x (cm); the ball's path is x = 0, so dist = |side| at depth inside [900, 1500]."""
        m = SpyMachine(self.payload, patched=False)
        a, c = a or self.A, c or self.C
        frame = m.STACK - 0x100
        fraction = (depth - a[2]) / (c[2] - a[2]) if c[2] != a[2] else 0.0
        fraction = min(max(fraction, 0.0), 1.0)
        q = (a[0] + (c[0] - a[0]) * fraction, a[1] + (c[1] - a[1]) * fraction, a[2] + (c[2] - a[2]) * fraction)
        dist = math.hypot(side - q[0], depth - q[2])
        m.uc.mem_write(frame + 0x18, struct.pack("<f", dist))
        m.uc.mem_write(frame + 0x20, struct.pack("<4f", *q, 1.0))
        m.uc.mem_write(frame + 0x30, struct.pack("<4f", side, 198.12, depth, 1.0))
        m.uc.mem_write(frame + 0x40, struct.pack("<4f", *a, 1.0))
        m.uc.mem_write(frame + 0x50, struct.pack("<4f", *c, 1.0))
        m.u32(frame - 4, m.STOP)
        m.u32(m.P + 0x100, 0xFFFFFFFF if cpu else 0)
        m.f32(m.P + 0x400 + 0x40, velocity[0]); m.f32(m.P + 0x400 + 0x48, velocity[1])
        catch = catch if catch is not None else (0.0, 1500.0)
        m.uc.mem_write(0xBF0DF0, struct.pack("<4f", catch[0], 142.04, catch[1], 1.0))
        m.u32(0xBF0E08, catch_flag)
        m.u32(0xE3C000, m.RB if receiver else 0)
        for name, value in (("ESP", frame - 4), ("ESI", m.P), ("EDI", 0x1234), ("EBX", 0x3456), ("EBP", 0x6789),
                            ("ECX", 0x1111), ("EDX", 0x2222), ("EAX", 0x789A)):
            m.uc.reg_write(getattr(x86, "UC_X86_REG_" + name), value)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        if fpu_depth:   # values the caller left on the x87 stack must survive
            m.uc.mem_write(m.SOURCE, struct.pack("<f", 12.5))
            for _ in range(fpu_depth):
                m.uc.mem_write(m.SOURCE + 0x100, bytes.fromhex("d905") + struct.pack("<I", m.SOURCE) + b"\xf4")
                m.uc.emu_start(m.SOURCE + 0x100, m.SOURCE + 0x106, count=10)
        top = (m.uc.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7
        m.uc.emu_start(self.code, m.STOP, timeout=1_000_000, count=2000)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EIP), m.STOP)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), frame)
        for name, value in (("ESI", m.P), ("EDI", 0x1234), ("EBX", 0x3456), ("EBP", 0x6789), ("ECX", 0x1111),
                            ("EDX", 0x2222)):
            self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_" + name)), value, name)
        self.assertEqual((m.uc.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7, top)
        result = m.uc.reg_read(x86.UC_X86_REG_EAX)
        self.assertIn(result, (0, 1))
        return result

    def test_retail_outside_three_yards_and_within_a_yard(self):
        self.assertEqual(self.run_window(side=3.1 * YD), 0)
        self.assertEqual(self.run_window(side=0.8 * YD), 1)
        self.assertEqual(self.run_window(side=float("nan")), 0)            # unordered: retail result 0

    def test_standing_still_beyond_a_yard_and_a_half_keeps_running(self):
        self.assertEqual(self.run_window(side=2.0 * YD), 0)
        self.assertEqual(self.run_window(side=1.2 * YD), 1)                # inside the reach: retail

    def test_closing_on_the_ball_fast_enough_still_leaps(self):
        # Q at depth 1200 is 0.45 s ahead; 2 yd out he must close 0.5 yd: 9 yd/s toward the path does it.
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=(-9 * YD, 0.0)), 1)
        self.assertEqual(self.run_window(side=2.9 * YD, velocity=(-9 * YD, 0.0)), 1)
        self.assertEqual(self.run_window(side=-2.0 * YD, velocity=(9 * YD, 0.0)), 1)   # other side, mirrored

    def test_reach_boundary_is_the_closing_distance(self):
        # 0.5 yd to close in 0.45 s needs 1.11 yd/s toward the path.
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=(-1.0 * YD, 0.0)), 0)
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=(-1.25 * YD, 0.0)), 1)

    def test_running_away_or_alongside_does_not_leap(self):
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=(9 * YD, 0.0)), 0)
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=(0.0, 9 * YD)), 0)

    def test_receiver_first_refuses_a_ball_past_the_catch_point(self):
        fast = (-9 * YD, 0.0)
        # The catch point 100 cm before his closest point: 0.05 s of flight earlier, more than 0.03 s.
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=fast, catch=(0.0, 1100.0)), 0)
        self.assertEqual(self.run_window(side=1.2 * YD, catch=(0.0, 1100.0)), 0)
        # 20 cm (0.01 s) before it, or after it: the reach test decides.
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=fast, catch=(0.0, 1180.0)), 1)
        self.assertEqual(self.run_window(side=1.2 * YD, catch=(0.0, 1400.0)), 1)
        # Within a yard stays retail even past the catch point.
        self.assertEqual(self.run_window(side=0.8 * YD, catch=(0.0, 1000.0)), 1)

    def test_receiver_first_needs_a_valid_catch_point_on_the_ball_line(self):
        early = (0.0, 1100.0)
        self.assertEqual(self.run_window(side=1.2 * YD, catch=early, catch_flag=0), 1)
        self.assertEqual(self.run_window(side=1.2 * YD, catch=early, receiver=False), 1)
        self.assertEqual(self.run_window(side=1.2 * YD, catch=(1.2 * YD, 1100.0)), 1)   # off the line: a tipped ball
        self.assertEqual(self.run_window(side=1.2 * YD, catch=(0.8 * YD, 1100.0)), 0)   # within a yard of the line

    def test_human_defenders_and_degenerate_paths_stay_retail(self):
        self.assertEqual(self.run_window(side=2.0 * YD, cpu=False), 1)
        self.assertEqual(self.run_window(side=2.0 * YD, cpu=False, catch=(0.0, 1100.0)), 1)
        self.assertEqual(self.run_window(side=2.0 * YD, a=(0.0, 150.0, 1200.0), c=(0.0, 120.0, 1200.0)), 1)
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=(float("nan"), 0.0)), 1)

    def test_caller_x87_stack_survives(self):
        self.assertEqual(self.run_window(side=2.0 * YD, fpu_depth=2), 0)
        self.assertEqual(self.run_window(side=2.0 * YD, velocity=(-9 * YD, 0.0), fpu_depth=1), 1)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class DecisionTests(unittest.TestCase):
    """The real ball-play decision 0x1F52C0 (retail bytes, then with the hook): a CPU man defender, a flat ball flying
    +z at 20 yd/s at the height of his hands (below his reach) that crosses his line 0.45 s from now."""

    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_nfl2k5_db_ball_play_unicorn import atl_body, coverage_nodes
        from tests.nfl2k5_cpu_ai_native import ball_frame_class
        node = next(n for _s, n in coverage_nodes(atl_body(), 183) if n.op == 0x0E)
        retail = retail_xbe()
        cls.machines = {}
        for label, payload in (("retail", retail), ("patched", dive.apply(retail)[0])):
            m = ball_frame_class()(payload, node, direction=1)
            snap = [(s, bytes(m.uc.mem_read(s, e - s + 1))) for s, e, _ in m.uc.mem_regions()]
            cls.machines[label] = (m, snap)

    def decide(self, label, x, z, vx=0.0, vz=0.0, *, cpu=True, catch=None):
        m, snap = self.machines[label]
        for start, data in snap:
            m.uc.mem_write(start, data)
        m.place(m.p, x * YD, z * YD, vx * YD, vz * YD)
        m.put(m.steer, 0xFFFFFFFF if cpu else 0)
        m.uc.mem_write(0x2010100, struct.pack("<8f", 0, 150.0, 0, 1, 0, 0, 20 * YD, 0))
        m.put(0x2010000, 0); m.put(0xE602C0, 4); m.put(m.GAME + 0x1B4, 0)
        if catch is None:
            m.put(0xBF0E08, 0)
        else:
            m.uc.mem_write(0xBF0DF0, struct.pack("<4f", catch[0] * YD, 142.04, catch[1] * YD, 1.0))
            m.put(0xBF0E08, 1); m.put(0xE3C000, m.target)
        point = 0x2058F00
        m.uc.mem_write(point, struct.pack("<4f", 0, 0, 0, 1))
        m.component(0x1F52C0, ecx=point, edx=m.p, args=(0,))
        return m.uc.reg_read(x86.UC_X86_REG_EAX)

    def both(self, *args, **kwargs):
        return self.decide("retail", *args, **kwargs), self.decide("patched", *args, **kwargs)

    def test_retail_commits_from_where_he_stands_whatever_his_motion(self):
        self.assertEqual(self.decide("retail", 2.0, 9.0), 2)
        self.assertEqual(self.decide("retail", 2.0, 9.0, vx=9.0), 2)      # running away from the ball's path
        self.assertEqual(self.decide("retail", 2.9, 9.0), 2)
        self.assertEqual(self.decide("retail", 3.1, 9.0), 0)
        self.assertEqual(self.decide("retail", 4.0, 9.0, vx=-9.0), 0)     # no look-ahead of his own run

    def test_long_leaps_need_him_closing_on_the_ball(self):
        self.assertEqual(self.both(2.0, 9.0), (2, 0))                    # standing still 2 yd away
        self.assertEqual(self.both(2.0, 9.0, vx=9.0), (2, 0))            # running away
        self.assertEqual(self.both(2.0, 9.0, vz=9.0), (2, 0))            # running alongside the ball's line
        self.assertEqual(self.both(2.0, 9.0, vx=-9.0), (2, 2))           # sprinting at the path
        self.assertEqual(self.both(2.9, 9.0, vx=-9.0), (2, 2))

    def test_close_plays_and_human_defenders_are_retail(self):
        for x in (0.5, 1.2):
            retail, patched = self.both(x, 9.0)
            self.assertEqual(patched, retail, x)
            self.assertIn(retail, (2, 3), x)
        self.assertEqual(self.both(2.0, 9.0, cpu=False), (2, 2))
        self.assertEqual(self.both(3.1, 9.0), (0, 0))
        self.assertEqual(self.both(2.0, 4.0), (0, 0))                    # the ball crosses his line in 0.2 s

    def test_no_leap_at_a_ball_the_receiver_catches_first(self):
        # catch point 2 yd before his line on the ball's path: the ball reaches the receiver 0.1 s earlier
        self.assertEqual(self.both(1.2, 9.0, catch=(0.0, 7.0)), (2, 0))
        self.assertEqual(self.both(2.0, 9.0, vx=-9.0, catch=(0.0, 7.0)), (2, 0))
        # catch point at or beyond his line: unchanged
        self.assertEqual(self.both(2.0, 9.0, vx=-9.0, catch=(0.0, 12.0)), (2, 2))
        self.assertEqual(self.both(1.2, 9.0, catch=(0.0, 9.2)), (2, 2))


if __name__ == "__main__":
    unittest.main()
