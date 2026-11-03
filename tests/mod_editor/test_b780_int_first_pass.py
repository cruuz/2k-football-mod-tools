"""b780-int: a plan whose only executable work belongs to in-place or late owners builds.

Before beta-80 such a plan (only "Quicker deep and rollout throws", only the simulated stats, only the contract college
guard) entered the first-pass writer with nothing for it to write and stopped with "nothing requested" (c-release found
it; reproduced with sim_stats). ``_build`` now asks ``_first_pass_requested`` and copies the image instead, and the
in-place owners patch the copy. The retail cases skip when the pinned USA retail default.xbe is not in the private
fixtures.
"""

from __future__ import annotations

# Standalone invocation must not depend on a caller's PYTHONPATH.
import sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

import ast
import tempfile
import unittest

from mod_editor.core import mod_build

ROOT = Path(__file__).resolve().parents[2]


def _first_pass_keys() -> set[str]:
    """The keys of the kwargs dict ``_build`` hands the first-pass writer, read from the source."""
    tree = ast.parse((ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8"))
    build = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_build")
    keys: set[str] = set()
    for node in ast.walk(build):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "kwargs" \
                and isinstance(node.value, ast.Dict):
            keys |= {key.value for key in node.value.keys if isinstance(key, ast.Constant)}
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript) \
                and isinstance(node.targets[0].value, ast.Name) and node.targets[0].value.id == "kwargs" \
                and isinstance(node.targets[0].slice, ast.Constant):
            keys.add(node.targets[0].slice.value)
    keys.discard("_consume_source")     # how to read the source, not a request
    return keys


def _retail_bytes() -> bytes | None:
    try:
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        return retail_bytes()
    except (unittest.SkipTest, ImportError, OSError, FileNotFoundError, ValueError):
        return None


class FirstPassDecisionTests(unittest.TestCase):
    def test_every_first_pass_key_is_either_a_request_or_plumbing(self):
        keys = _first_pass_keys()
        self.assertTrue(keys, "the first-pass kwargs dict was not found in _build")
        self.assertEqual(sorted(keys), sorted(set(mod_build._FIRST_PASS_FLAGS) | set(mod_build._FIRST_PASS_PLUMBING)))
        self.assertFalse(set(mod_build._FIRST_PASS_FLAGS) & set(mod_build._FIRST_PASS_PLUMBING))

    def test_nothing_asked_of_the_first_pass_means_no_first_pass(self):
        idle = {name: False for name in mod_build._FIRST_PASS_FLAGS}
        idle.update(overwrite=False, progress=None, _defer_image_resources=True, music_policy="retail",
                    uniform_choice="", prospect_names="", dynamic_kickoff_settings=None)
        self.assertFalse(mod_build._first_pass_requested(idle))
        for name in mod_build._FIRST_PASS_FLAGS:
            with self.subTest(name=name):
                self.assertTrue(mod_build._first_pass_requested({**idle, name: True}))
        self.assertTrue(mod_build._first_pass_requested({**idle, "settings": object()}))
        self.assertTrue(mod_build._first_pass_requested({**idle, "music_policy": "shuffle"}))
        self.assertTrue(mod_build._first_pass_requested({**idle, "uniform_choice": "choice"}))


class InPlaceOnlyBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail_bytes()
        if cls.retail is None:
            raise unittest.SkipTest("the pinned USA retail default.xbe is not in the private fixtures")

    def _build_only(self, **options):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        source = Path(temp.name) / "default.xbe"
        source.write_bytes(self.retail)
        target = Path(temp.name) / "built.xbe"
        receipt = mod_build.build(mod_build.BuildPlan(str(source), str(target), **options))
        return receipt, target

    def test_quick_long_release_alone_builds(self):
        from mod_editor.core import nfl2k5_quick_long_release as q
        receipt, target = self._build_only(quick_long_release=True)
        steps = [row.get("step") for row in receipt["steps"]]
        self.assertIn("copy", steps)
        self.assertNotIn("xbe", steps)
        self.assertEqual(receipt["result"]["quick_long_release"], "applied")
        self.assertEqual(target.read_bytes(), q.apply(self.retail)[0])

    def test_sim_stats_alone_builds(self):
        from mod_editor.core import nfl2k5_sim_stats as sim_stats
        receipt, target = self._build_only(sim_stats=True)
        self.assertIn("copy", [row.get("step") for row in receipt["steps"]])
        self.assertEqual(sim_stats.status(target.read_bytes()), "applied")

    def test_a_first_pass_option_still_takes_the_first_pass(self):
        receipt, _target = self._build_only(catch_slider=True, quick_long_release=True)
        steps = [row.get("step") for row in receipt["steps"]]
        self.assertIn("xbe", steps)
        self.assertNotIn("copy", steps)
        self.assertEqual(receipt["result"]["quick_long_release"], "applied")


class CoachCareerFixWiringTests(unittest.TestCase):
    """b780-int wires c1-coachdata's nfl2k5_coach_career_fix (c1 report section 7): a Build option on in every
    preset, validated, inspected, applied after the Contracts guard and read back after the final passes."""

    def test_option_presets_settings_and_panel(self):
        from mod_editor.core import nfl2k5_build_settings as settings
        from mod_editor.core import nfl2k5_coach_career_fix as fix
        self.assertIs(mod_build.BuildPlan("", "").coach_career_fix, False)
        self.assertEqual({name: preset["coach_career_fix"] for name, preset in mod_build.PRESETS.items()},
                         {name: True for name in mod_build.PRESETS})
        self.assertIn("coach_career_fix", settings.FEATURE_KEYS)
        self.assertIs(mod_build.BuildPlan("a.iso", "b.iso", coach_career_fix=True).wants_xbe_patch(), True)
        self.assertIs(mod_build.availability()["coach_career_fix"], True)
        source = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('("coach_career_fix", _coach_career_fix.BUILD_CAPTION, _coach_career_fix.HELP_TEXT)', source)
        self.assertNotIn("\u2014", fix.HELP_TEXT + fix.BUILD_CAPTION)
        with self.assertRaises(ValueError):
            mod_build.build(mod_build.BuildPlan("in.xbe", "out.xbe", coach_career_fix=1))

    def test_a_retail_build_with_only_the_fix_applies_it(self):
        retail = _retail_bytes()
        if retail is None:
            self.skipTest("the pinned USA retail default.xbe is not in the private fixtures")
        from mod_editor.core import nfl2k5_coach_career_fix as fix
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "default.xbe"
            source.write_bytes(retail)
            target = Path(temp) / "built.xbe"
            receipt = mod_build.build(mod_build.BuildPlan(str(source), str(target), coach_career_fix=True))
            self.assertEqual(receipt["result"]["coach_career_fix"], "applied")
            self.assertEqual(target.read_bytes(), fix.apply(retail)[0])
            self.assertEqual(mod_build.inspect(target)["coach_career_fix"], "applied")
            self.assertEqual(mod_build.inspect(source)["coach_career_fix"], "retail")


class LateOwnerReservationTests(unittest.TestCase):
    """b780-int: every b780 late owner a plan selects is reserved by the first space pass, in LATE_OWNERS order. An owner
    that appended itself when applied (the History screen, the franchise footer and history capture, speed separation)
    moved the later owners that pass had already placed, and the Experimental build stopped at the History screen with
    "appending the owner would move an existing allocation"."""

    WAVE = dict(coach_carousel=True, franchise_history=True, history_screen=True, standings_records=True,
                cpu_passer_iq=True, cpu_clock2=True, cpu_runner_vision=True, db_dive_window=True, catch_snap_limit=True,
                speed_threshold=35, scramble_blocking=True, protection_calls=True, audible_legend=True)

    def test_the_first_pass_reserves_every_wave_owner(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt, nfl2k5_xbe_space as space
        owners = {row[0] for row in tt._selected_space_requests(**self.WAVE)}
        late = list(space.LATE_OWNERS)
        wave = late[late.index("nfl2k5_sim_realism_state") + 1:]
        self.assertEqual(sorted(set(wave) - owners), [])

    def test_speed_after_a_later_owner_does_not_move_it(self):
        retail = _retail_bytes()
        if retail is None:
            self.skipTest("the pinned USA retail default.xbe is not in the private fixtures")
        from mod_editor.core import nfl2k5_throw_tuning as tt, nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_protection_calls as calls, nfl2k5_speed_threshold as speed
        payload, _ = space.apply(retail, tt._selected_space_requests(protection_calls=True, speed_threshold=35),
                                 scaleout=True)
        payload = calls.apply(payload)[0]           # the build applies protection calls ...
        placed = {r["owner"]: r["va"] for r in space.layout(payload)["allocations"]}
        payload = speed.apply(payload, value=35)[0]  # ... and speed separation (earlier in LATE_OWNERS) after it
        after = {r["owner"]: r["va"] for r in space.layout(payload)["allocations"]}
        self.assertEqual({k: after[k] for k in placed}, placed)
        self.assertEqual((calls.status(payload), speed.verify(payload, value=35)["value"]), ("applied", 35))


if __name__ == "__main__":
    unittest.main()
