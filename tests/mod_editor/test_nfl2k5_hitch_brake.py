"""Stop man-coverage spins (coverage_trail's moving arrival brake, b780 cv1): settings, ownership, native proof.

Private tests skip unless the pinned USA retail XBE and the released SOFTDRINK 2K28 v0.8 executable are present
(see tools/replay_nfl2k5_hitch.py: NFL2K5_RETAIL_EXTRACTION, NFL2K5_V08_XBE or NFL2K5_V08_DISC). No proprietary
file or output executable is committed. Adapted from job/ai2-hitch (10/11) to the released v0.8 bytes.
"""
from pathlib import Path
import gc
import hashlib
import math
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_coverage_trail as trail  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as choices  # noqa: E402
from mod_editor.core.mod_build import BuildPlan, PRESETS, _r62_plan_options  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tools import replay_nfl2k5_hitch as replay  # noqa: E402
from tests.nfl2k5_coverage_trail_frame import TrailFrame, YARD, DT, uni, x86  # noqa: E402
from tests.mod_editor import test_nfl2k5_coverage_trail_unicorn as existing  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit  # noqa: E402

MAN = (0x1A4830, 0x1A4CF0, 0x1A4DD0)
PURSUIT = (0x1F4360, 0x1F48F0, 0x2EAB60, 0x2EB300)


class PublicTests(unittest.TestCase):
    def test_editor_defaults_presets_persistence_and_parent_dependency(self):
        self.assertFalse(BuildPlan("", "").coverage_hitch_brake)
        # r5 default: on wherever Close pursuit recovery is on (Advanced, Experimental), off in Basic.
        for name, preset in PRESETS.items():
            self.assertIs(preset["coverage_hitch_brake"], preset["coverage_trail"], name)
        self.assertFalse(PRESETS["softdrink_basic"]["coverage_hitch_brake"])
        self.assertTrue(PRESETS["softdrink_advanced"]["coverage_hitch_brake"])
        self.assertTrue(PRESETS["softdrink_experimental"]["coverage_hitch_brake"])
        self.assertEqual(trail.mapping()["moving_arrival_brake"]["presets"],
                         {"basic": False, "advanced": True, "experimental": True})
        plan = BuildPlan("a", "b", coverage_trail=True, coverage_hitch_brake=True)
        saved = choices.from_plan(plan)
        self.assertTrue(saved["coverage_hitch_brake"])
        self.assertTrue(choices.to_plan(saved, "c", "d").coverage_hitch_brake)
        # A project saved before this option keeps the earlier behavior until the box is ticked.
        self.assertFalse(choices.to_plan({"coverage_trail": True}, "c", "d").coverage_hitch_brake)
        self.assertTrue(_r62_plan_options(plan)["coverage_hitch_brake"])
        self.assertIn("coverage_hitch_brake", tt.R62_RUNTIME_KEYS)
        self.assertNotIn("coverage_hitch_brake", tt.R62_SPACE_KEYS)  # no space of its own
        self.assertFalse(tt._deferred_r62_options(_r62_plan_options(plan), True)["coverage_hitch_brake"])
        self.assertTrue(tt._deferred_r62_options(_r62_plan_options(plan), False)["coverage_hitch_brake"])
        with self.assertRaisesRegex(ValueError, "needs Close pursuit recovery"):
            tt._validate_r62_options(coverage_hitch_brake=True)
        with self.assertRaisesRegex(ValueError, "needs Close pursuit recovery"):
            choices.build_settings({"coverage_trail": False, "coverage_hitch_brake": True})
        for invalid in (1, None, "on"):
            with self.assertRaises(ValueError):
                tt._validate_r62_options(coverage_trail=True, coverage_hitch_brake=invalid)
        from mod_editor.gui import beta62_options as ui
        self.assertEqual(ui.CHILDREN["coverage_trail"], ("coverage_hitch_brake",))
        self.assertEqual(ui.KEYS[ui.KEYS.index("coverage_trail") + 1], "coverage_hitch_brake")

    def test_captions_are_short_plain_and_complete(self):
        self.assertLessEqual(len(trail.HITCH_CAPTION), 60)
        for text in (trail.HITCH_CAPTION, trail.HITCH_HELP):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)
        for words in ("Needs Close pursuit recovery", "Retail:", "Patch:", "curl", "slant", "hitch", "EXPERIMENTAL",
                      "Advanced and Experimental, off in Basic"):
            self.assertIn(words, trail.HITCH_HELP)

    def test_default_byte_template_and_capacity(self):
        from mod_editor.core import nfl2k5_coverage_trail_code as default
        from mod_editor.core import nfl2k5_coverage_hitch_code as enabled
        # The historical default template (v0.6 to v0.8 bytes, before relocation) is unchanged.
        self.assertEqual(hashlib.sha256(default.CODE).hexdigest(),
                         "6d0653a8a2950c1155dbe9e24e3c6b3f190ad688f501fdc6397fff4a7040666f")
        self.assertEqual(len(default.CODE), 520)
        self.assertEqual(len(enabled.CODE), 591)
        self.assertLessEqual(len(enabled.CODE), trail.CODE_SIZE)
        self.assertEqual(trail.REQUESTS, ((trail.OWNER, "code", 640, 16),))
        # The brake changes two short branch targets and appends its tail; everything else is the default code.
        differ = [i for i, (a, b) in enumerate(zip(default.CODE, enabled.CODE)) if a != b]
        self.assertEqual(differ, [enabled.LABELS["arrival"] - 8, enabled.LABELS["arrival"] - 1])
        self.assertEqual(enabled.LABELS["moving_man_arrival"], default.LABELS["code_end"])
        for label in ("entry", "arrival", "pivot", "restore", "native", "constants", "code_end"):
            self.assertEqual(default.LABELS[label], enabled.LABELS[label], label)
        a, b = trail.code_for(0x14DC030), trail.code_for(0x14DC030, moving_arrival_brake=True)
        self.assertEqual(len(a), trail.CODE_SIZE)
        self.assertEqual(len(b), trail.CODE_SIZE)
        self.assertEqual(b[591:], b"\xcc" * (trail.CODE_SIZE - 591))
        with self.assertRaises(ValueError):
            trail.code_for(0x14DC030, moving_arrival_brake=1)

    def test_fixture_routes_have_the_r5_shapes(self):
        for name, (kind, back, lateral) in replay.ROUTES.items():
            for speed in (6.0, 9.0):
                start = replay.route_point(name, 0, speed)
                turn = replay.route_point(name, replay.BREAK, speed)
                late = replay.route_point(name, replay.BREAK + replay.RETURN_FRAMES, speed)
                self.assertAlmostEqual((turn[1] - start[1]) / YARD, speed * replay.BREAK / 60)
                if kind == "return":
                    self.assertAlmostEqual((turn[1] - late[1]) / YARD, back)
                    self.assertAlmostEqual(late[0] / YARD, lateral)
                    self.assertEqual(late[2:], (0, 0))
                elif kind == "drift":   # the curl, then a slow sideways drift that never stops
                    self.assertAlmostEqual((turn[1] - late[1]) / YARD, back)
                    later = replay.route_point(name, replay.BREAK + replay.RETURN_FRAMES + 60, speed)
                    self.assertAlmostEqual((later[0] - late[0]) / YARD, replay.DRIFT_YARDS_S)
                    self.assertEqual(later[2:], (replay.DRIFT_YARDS_S * YARD, 0))
                else:
                    self.assertAlmostEqual(math.hypot(*late[2:]) / YARD, speed)


def _qt():
    try:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])
    except ImportError:
        return None


@unittest.skipUnless(_qt() is not None, "PyQt5 required")
class BuildPanelTests(unittest.TestCase):
    """The Build tab row: a child of Close pursuit recovery, ticked by the presets that tick its parent."""

    def setUp(self):
        import tempfile
        from mod_editor.core import mod_build
        from mod_editor.gui.build_panel_qt import BuildPanel
        if str(ROOT / "tests") not in sys.path:
            sys.path.insert(0, str(ROOT / "tests"))
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        self.app = _qt()
        self.tmp = tempfile.TemporaryDirectory()
        source = Path(self.tmp.name) / "default.xbe"
        source.write_bytes(_build_synthetic_xbe())
        self.panel = BuildPanel()
        self.panel.apply_state(mod_build.inspect(source))
        self.app.processEvents()
        self.trail, self.brake = self.panel.coverage_trail_check, self.panel.coverage_hitch_brake_check

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def model_disc_source(self):
        # A bare executable cannot take allocator owners ("Full disc required"); model a disc image source.
        for box in (self.trail, self.brake):
            box.setEnabled(True)

    def test_caption_help_and_parent_child_links(self):
        self.assertEqual(self.brake.text(), trail.HITCH_CAPTION)
        self.model_disc_source()
        self.trail.setChecked(False)
        self.assertFalse(self.brake.isChecked())
        self.brake.setChecked(True)
        self.assertTrue(self.trail.isChecked(), "ticking the brake ticks Close pursuit recovery")
        plan = self.panel.plan()
        self.assertTrue(plan.coverage_trail and plan.coverage_hitch_brake)
        self.trail.setChecked(False)
        self.assertFalse(self.brake.isChecked(), "unticking Close pursuit recovery clears the brake")
        plan = self.panel.plan()
        self.assertFalse(plan.coverage_trail or plan.coverage_hitch_brake)

    def test_presets_tick_the_brake_with_its_parent(self):
        for name, wanted in (("softdrink_basic", False), ("softdrink_advanced", True), ("softdrink_experimental", True),
                             ("softdrink_basic", False)):
            with self.subTest(preset=name):
                self.model_disc_source()
                result = self.panel.apply_preset(name)
                self.app.processEvents()
                if "coverage_hitch_brake" in result.get("skipped", []):
                    self.skipTest("the panel re-checked the source and skipped the row")
                self.assertEqual((self.trail.isChecked(), self.brake.isChecked()), (wanted, wanted))
                self.assertEqual(self.panel.plan().coverage_hitch_brake, wanted)


@unittest.skipUnless(uni is not None and existing.capstone is not None, "Unicorn and Capstone required")
class PrivateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.builds = replay.load_builds()
        except FileNotFoundError as exc:
            raise unittest.SkipTest(f"Private pinned inputs absent: {exc.filename}") from exc
        cls.final = cls.builds["v08"]
        cls.enabled, cls.receipt = trail.apply(cls.final, moving_arrival_brake=True)

    def tearDown(self):
        gc.collect()

    def test_released_bytes_are_the_default_and_both_modes_are_idempotent(self):
        self.assertEqual(trail.read_settings(self.final), {"status": "applied", "moving_arrival_brake": False})
        self.assertEqual(trail.apply(self.final)[0], self.final)
        self.assertEqual(trail.apply(self.enabled, moving_arrival_brake=True)[0], self.enabled)
        self.assertEqual(trail.apply(self.enabled)[0], self.final)  # the direct owner API can restore the default
        self.assertEqual(self.receipt["after_sha256"], hashlib.sha256(self.enabled).hexdigest())
        self.assertEqual(self.receipt["before_sha256"], replay.V08_SHA256)
        self.assertEqual(trail.read_settings(self.enabled), {"status": "applied", "moving_arrival_brake": True})
        a = next(a for a in space.layout(self.enabled)["allocations"] if a["owner"] == trail.OWNER)
        self.assertEqual(a["va"], replay.V08_VA)
        self.assertEqual(XbeImage(self.enabled).read(a["va"], a["size"]),
                         trail.code_for(a["va"], moving_arrival_brake=True))
        retail = self.builds["retail"]
        self.assertEqual(trail.read_settings(retail), {"status": "retail", "moving_arrival_brake": False})

    def test_only_the_owner_code_and_allocator_seals_change_and_foreign_bytes_refuse(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        a = next(a for a in space.layout(self.final)["allocations"] if a["owner"] == trail.OWNER)
        self.assertEqual(space.layout(self.final), space.layout(self.enabled))
        allowed = [(a["raw"], a["raw"] + a["size"]),
                   (space.DIRECTORY, space.LIB_COPY),
                   (space.SCALE_DIRECTORY, space.SCALE_DIRECTORY + space.PAGE)]
        for section in _sections(self.enabled):
            self.assertEqual(section.stored_digest, section_digest(self.enabled, section))
            allowed.append((section.header_offset + 36, section.header_offset + 56))
        self.assertFalse(XbeImage(self.enabled).runtime_writable(a["va"], a["size"]))
        self.assertEqual(len(self.final), len(self.enabled))
        changed = [i for i, (x, y) in enumerate(zip(self.final, self.enabled)) if x != y]
        self.assertTrue(changed)
        self.assertEqual([i for i in changed if not any(lo <= i < hi for lo, hi in allowed)], [])
        # The executable's code changes only inside the owner's reservation, at the two branches and the tail.
        code = [i - a["raw"] for i in changed if a["raw"] <= i < a["raw"] + a["size"]]
        self.assertEqual(code[:2], [439, 446])
        self.assertTrue(all(520 <= i < 591 for i in code[2:]))
        for payload in (self.final, self.enabled):
            for va in (trail.HOOK_VA, a["va"] + 438, a["va"] + 530, trail.GUARDS[1][0]):
                byte = XbeImage(payload).read(va, 1)
                broken = repin_edit(payload, va, bytes([byte[0] ^ 1]))
                self.assertEqual(trail.status(broken), "foreign")
                with patch.object(trail, "_reconfigure", side_effect=AssertionError("mutated foreign input")):
                    with self.assertRaises(ValueError):
                        trail.apply(broken, moving_arrival_brake=True)

    def test_cave_manifest_records_both_modes_in_the_same_reservation(self):
        from mod_editor.core import nfl2k5_cave_manifest as manifest
        from mod_editor.core.nfl2k5_cave_oracle import absolute_writes
        from mod_editor.core import nfl2k5_coverage_hitch_code as code
        retail = self.builds["retail"]
        recorder = manifest.Recorder(retail)
        allocated, receipt = space.apply(retail, trail.REQUESTS, scaleout=True)
        recorder.observe(space, "apply", retail, allocated, receipt)
        default, receipt = trail.apply(allocated)
        recorder.observe(trail, "apply:default", allocated, default, receipt)
        enabled, receipt = trail.apply(default, moving_arrival_brake=True)
        recorder.observe(trail, "apply:moving_arrival_brake", default, enabled, receipt)
        spans = recorder.finish(enabled)
        a = next(a for a in space.layout(enabled)["allocations"] if a["owner"] == trail.OWNER)
        self.assertTrue(any(s["owner"] == trail.OWNER and int(s["start"], 0) == a["va"]
                            and s["size"] == trail.CODE_SIZE for s in spans))
        self.assertTrue(any(s["owner"] == trail.OWNER and int(s["start"], 0) <= trail.HOOK_VA
                            and int(s["end"], 0) >= trail.HOOK_VA + 6 for s in spans))
        writes = absolute_writes(enabled, [(a["va"], a["va"] + code.LABELS["constants"]),
                                          (a["va"] + code.LABELS["moving_man_arrival"], a["va"] + len(code.CODE))])
        self.assertTrue(writes)
        self.assertTrue(all(w["target"] is None for w in writes))  # no absolute runtime data write

    def test_dispatcher_builds_both_modes_reports_them_and_refuses_a_silent_removal(self):
        retail = self.builds["retail"]
        built = {}
        for enabled in (False, True):
            out, receipt = tt._apply_all(retail, None, False, coverage_trail=True, coverage_hitch_brake=enabled)
            self.assertEqual(trail.read_settings(out), {"status": "applied", "moving_arrival_brake": enabled})
            status = tt._grown_status_fields(out)
            self.assertEqual(status["coverage_trail"], "applied")
            self.assertEqual(status["coverage_hitch_brake"], "applied" if enabled else "retail")
            self.assertEqual(receipt["coverage_trail_patch"]["moving_arrival_brake"], enabled)
            built[enabled] = out
        # The installed brake cannot be silently dropped by a later build; keeping it (or adding it) is accepted.
        # (A released v0.8 executable gains the brake in place through the owner API: see the round-trip test. The full
        # dispatcher also checks every other installed v0.8 setting against the plan first.)
        with_brake = _r62_plan_options(BuildPlan("", "", coverage_trail=True, coverage_hitch_brake=True))
        without = _r62_plan_options(BuildPlan("", "", coverage_trail=True))
        with self.assertRaisesRegex(ValueError, "rebuild from a verified base"):
            tt._check_installed_runtime_settings(built[True], without)
        with self.assertRaisesRegex(ValueError, "rebuild from a verified base"):
            tt._check_installed_runtime_settings(self.enabled, without)
        tt._check_installed_runtime_settings(built[True], with_brake)
        tt._check_installed_runtime_settings(built[False], with_brake)

    def moving_machine(self, payload, *, distance=.1, callback=0x1A4830, velocity=100):
        m = TrailFrame(payload, planner="man", defender=(0, 0), heading=0)
        m.place(m.target, 0, -distance * YARD, 0, velocity)
        m.put(m.task, callback)
        m.f32(m.steer + 0x10, 1)
        m.put(m.steer + 0x14, 32768)
        m.f32(0xB71D0C, DT)
        return m

    def turn(self, m, **registers):
        m.component(trail.HOOK_VA, ecx=m.p, args=(existing.bits(20000),), **registers)
        self.assertEqual(m.executed_leaves, set())
        return bytes(m.uc.mem_read(m.p, 0x1000))

    def test_only_a_moving_man_arrival_changes_and_the_next_tick_resumes(self):
        for callback in MAN + PURSUIT:
            with self.subTest(callback=hex(callback)):
                a, b = self.moving_machine(self.final, callback=callback), self.moving_machine(self.enabled, callback=callback)
                self.turn(a)
                self.turn(b)
                wanted = 0 if callback in MAN else 1
                self.assertEqual(a.readf(a.steer + 0x10), 1)  # shipped: he keeps running and pivots
                self.assertEqual(a.get(a.transform + 0x50), 32768)
                self.assertEqual(b.readf(b.steer + 0x10), wanted)
                if not wanted:
                    self.assertEqual(b.get(b.transform + 0x50), 0)  # held: no half turn this tick
                    b.place(b.target, 0, -2 * YARD, 0, -100)
                    b.component(0x1A4830, ecx=b.p)
                    self.assertGreater(b.readf(b.steer + 0x10), 0)  # the next native plan moves him again
                    self.turn(b)
                    self.assertEqual(b.get(b.transform + 0x50), b.get(b.steer + 0x14))
                else:
                    self.assertEqual(self.turn(a), self.turn(b))
                del a, b
                gc.collect()

    def test_moving_gate_register_fpu_and_write_contract(self):
        m = self.moving_machine(self.enabled)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x27F)
        saved = {r: 0x12345670 + i for i, r in enumerate((x86.UC_X86_REG_EBX, x86.UC_X86_REG_EBP,
                                                         x86.UC_X86_REG_ESI, x86.UC_X86_REG_EDI))}
        for register, value in saved.items():
            m.uc.reg_write(register, value)
        a = next(a for a in space.layout(self.enabled)["allocations"] if a["owner"] == trail.OWNER)
        writes = []

        def observe(uc, access, address, size, value, data):
            if a["va"] <= uc.reg_read(x86.UC_X86_REG_EIP) < a["va"] + a["size"]:
                writes.append((address, size))

        m.uc.hook_add(uni.UC_HOOK_MEM_WRITE, observe)
        self.turn(m, esi=saved[x86.UC_X86_REG_ESI])
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW), 0x27F)
        for register, value in saved.items():
            self.assertEqual(m.uc.reg_read(register), value)
        self.assertIn((m.steer + 0x10, 4), writes)
        self.assertTrue(all(m.STACK - 256 <= va < va + n <= m.STACK + 8 or (va, n) == (m.steer + 0x10, 4)
                            for va, n in writes))

    def test_scope_invalid_geometry_and_special_states_match_the_shipped_bytes(self):
        controls = {
            "outside_arrival": lambda m: m.place(m.target, 0, -.351 * YARD, 0, 100),
            "human": lambda m: m.put(m.steer, 0),
            "offense": lambda m: m.put(m.p + 0x38, m.KICK_TEAM),
            "dead_ball": lambda m: m.put(0xE602B8, 13),
            "unknown_task": lambda m: m.put(m.task, 0x1A0000),
            "queued_lapse": lambda m: m.put(m.steer + 0x1C, 0x12),
            "strafe": lambda m: m.put(m.state + 0x28, 1),
            "transition": lambda m: m.put(m.state + 0x28, 2),
            "special_clip": lambda m: m.put(m.state + 4, 0x510458),
            "forward": lambda m: m.put(m.steer + 0x14, 1000),
            "nan_velocity": lambda m: m.f32(m.target + 0xB40, math.nan),
            "inf_velocity": lambda m: m.f32(m.target + 0xB48, math.inf),
            "nan_position": lambda m: m.f32(m.target + 0xB30, math.nan),
            "zero_dt": lambda m: m.f32(0xB71D0C, 0),
            "slow_frame_dt": lambda m: m.f32(0xB71D0C, .2),
        }
        for label, change in controls.items():
            with self.subTest(label=label):
                a, b = self.moving_machine(self.final), self.moving_machine(self.enabled)
                change(a)
                change(b)
                self.assertEqual(self.turn(a), self.turn(b))
                del a, b
                gc.collect()

    def test_existing_x87_values_and_native_lapse_controls_with_the_brake(self):
        control = existing.NativeTests()
        control.retail = self.builds["retail"]
        control.patched = trail.apply(trail.apply(control.retail)[0], moving_arrival_brake=True)[0]
        control.machine = lambda payload, **kw: self.moving_machine(payload, distance=kw.get("distance", 2))
        control.test_x87_values_callee_saved_registers_and_owner_write_bounds()
        control.test_one_genuine_native_lapse_is_preserved_with_identical_rng()



@unittest.skipUnless(uni is not None and existing.capstone is not None, "Unicorn and Capstone required")
class ReleasedReplayTests(unittest.TestCase):
    """Eight 240-tick native replays (a few minutes): the released spins and the brake's single turn."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.builds = replay.load_builds()
        except FileNotFoundError as exc:
            raise unittest.SkipTest(f"Private pinned inputs absent: {exc.filename}") from exc
        cls.final = cls.builds["v08"]
        cls.enabled, _ = trail.apply(cls.final, moving_arrival_brake=True)

    def test_released_curl_and_go_spins_become_at_most_one_turn(self):
        for route, matrix, allowed in (("curl_1_5", "r5", 1), ("go", "fast", 0)):
            for direction in (1, -1):
                with self.subTest(route=route, direction=direction):
                    old = replay.replay_case(self.final, route, direction=direction, matrix=matrix)["summary"]
                    new = replay.replay_case(self.enabled, route, direction=direction, matrix=matrix)["summary"]
                    self.assertGreaterEqual(len(old["pre_break_large_pivot_frames"] + old["large_pivot_frames"]), 4)
                    self.assertEqual(new["pre_break_large_pivot_frames"], [])
                    self.assertLessEqual(len(new["large_pivot_frames"]), allowed)
                    self.assertEqual(new["reversal_pairs"], 0)
                    self.assertLess(new["tail_total_degrees"], 5)
                    self.assertLess(new["final_gap_yards"], .35)
                    gc.collect()


if __name__ == "__main__":
    unittest.main()
