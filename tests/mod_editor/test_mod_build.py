"""One build plan applies every executable patch to one copy and returns one receipt."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build, nfl2k5_throw_tuning as tt  # noqa: E402
from nfl2k5_edge_rename_test import build_edge_synthetic_xbe  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402


class ModBuildTests(unittest.TestCase):
    def test_plan_applies_all_xbe_patches_in_one_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(build_edge_synthetic_xbe())     # seeds the throw, cave and EDGE retail sites
            target = Path(tmp) / "built.xbe"
            plan = mod_build.BuildPlan(str(source), str(target), throw=True, max_deep_yards=80.0, realistic_flight=True,
                                       catch_slider=True, accel_ramp=True, draft_ai=True, edge_rename=True,
                                       returner_fix=True, name="test")
            events = []
            receipt = mod_build.build(plan, lambda msg, a, b: events.append(msg))
            self.assertEqual(receipt["steps"][0]["step"], "xbe")
            self.assertEqual(receipt["steps"][0]["catch_slider"], "applied")
            self.assertEqual(receipt["steps"][0]["accel_ramp"], "applied")
            self.assertEqual(receipt["steps"][0]["draft_ai"], "applied")
            self.assertEqual(receipt["steps"][0]["edge_rename"], "applied")
            self.assertEqual(receipt["steps"][0]["returner_fix"], "applied")
            state = mod_build.inspect(target)
            self.assertEqual(state["throw"], tt.TuningSettings(80.0, 0.0, True))
            self.assertEqual(state["draft_ai"], "applied")
            self.assertEqual(state["edge_rename"], "applied")
            self.assertEqual(state["returner_fix"], "applied")
            self.assertEqual(state["progression"], "foreign")      # the EDGE fixture has no aging tables
            self.assertTrue(events)
            self.assertEqual(receipt["plan"]["name"], "test")
            self.assertNotIn("source", receipt["plan"])

    def test_refuses_same_file_and_scorebug_on_bare_xbe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_synthetic_xbe())
            with self.assertRaises(ValueError):
                mod_build.build(mod_build.BuildPlan(str(source), str(source), throw=True))
            with self.assertRaises(ValueError):
                mod_build.build(mod_build.BuildPlan(str(source), str(Path(tmp) / "x.xbe"), scorebug=True))

    def test_availability_reports_optional_modules(self) -> None:
        avail = mod_build.availability()
        self.assertTrue(avail["throw"] and avail["catch_slider"])
        # the ESPN scorebug needs its repainted art and the retail mesh, which developer trees have and
        # release trees / CI checkouts deliberately do not: availability must say so, never fail later
        scorebug_inputs = ((mod_build.ROOT / "mod_editor" / "assets" / "nfl2k5_scorebug_espn" / "shield_espn_modern.png").exists()
                           and (mod_build.ROOT / "assets" / "intermediate" / "nfl2k5" / "models" / "0346_0078_score_bug.gltf").exists())
        self.assertEqual(avail["scorebug"], scorebug_inputs)
        self.assertIn("edge_rename", avail)
        self.assertIn("commentary", avail)


if __name__ == "__main__":
    unittest.main()


class PresetTests(unittest.TestCase):
    """SOFTDRINK presets: basic = the 2004 game + the 2K5 fixes; advanced = everything modern; experimental = + rough edges."""

    def test_basic_keeps_the_game_in_2004(self) -> None:
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_basic")
        self.assertTrue(plan.throw and plan.realistic_flight and plan.catch_slider and plan.draft_ai
                        and plan.returner_fix and plan.kick_power)
        # nothing that changes the 2004 rules, names or presentation
        self.assertFalse(plan.edge_rename or plan.kick_rules or plan.overtime or plan.accel_ramp or plan.progression
                         or plan.scorebug or plan.arc_by_distance or plan.scheme_labels or plan.camera
                         or plan.position_pools or plan.season_2026 or plan.widescreen or plan.kickoff_alignment or plan.seven_on_seven)
        self.assertEqual(plan.max_deep_yards, 80.0)
        self.assertEqual((plan.source, plan.target), ("s", "t"))
        self.assertIn("basic", plan.name)

    def test_advanced_is_a_superset_of_basic_except_the_kick_split(self) -> None:
        basic = mod_build.PRESETS["softdrink_basic"]
        advanced = mod_build.PRESETS["softdrink_advanced"]
        for key, value in basic.items():
            if value is True and key != "kick_power":
                self.assertTrue(advanced.get(key), key)
        # advanced carries the modern spots (which include the power re-spacing), not the power-only fix
        self.assertTrue(advanced["kick_rules"]); self.assertFalse(advanced["kick_power"])
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_advanced")
        self.assertTrue(plan.accel_ramp and plan.progression and plan.scorebug and plan.arc_by_distance and plan.position_pools
                        and plan.season_2026 and plan.edge_rename and plan.overtime and plan.camera and plan.scheme_labels)
        self.assertFalse(plan.widescreen or plan.kickoff_alignment or plan.seven_on_seven)

    def test_experimental_is_advanced_plus_widescreen_and_kickoff_lineup(self) -> None:
        advanced = mod_build.PRESETS["softdrink_advanced"]
        experimental = mod_build.PRESETS["softdrink_experimental"]
        for key, value in advanced.items():
            if value is True:
                self.assertTrue(experimental.get(key), key)
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_experimental")
        self.assertTrue(plan.widescreen and plan.kickoff_alignment)
        self.assertEqual(plan.seven_on_seven, mod_build.SEVEN_ON_SEVEN_RELEASED)
        self.assertIn("experimental", plan.name)

    def test_every_preset_names_every_toggle(self) -> None:
        toggles = {k for k in mod_build.PRESETS["softdrink_experimental"]}
        for name, values in mod_build.PRESETS.items():
            self.assertEqual(set(values), toggles, name)
            self.assertIn(name, mod_build.PRESET_TITLES)

    def test_playbook_packs_are_off_by_default_and_need_a_disc(self) -> None:
        """A community book is a user choice like commentary: never in a preset."""

        plan = mod_build.BuildPlan(source="s", target="t")
        self.assertEqual(plan.playbook_packs, ())
        self.assertIn("playbook_packs", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            self.assertNotIn("playbook_packs", values, name)
        self.assertTrue(mod_build.availability()["playbook_packs"])
        self.assertEqual(mod_build.inspect.__doc__ is None, False)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, "playbook packs need a disc image"):
                mod_build.build(mod_build.BuildPlan(
                    str(source), str(Path(tmp) / "out.xbe"),
                    playbook_packs=(str(ROOT / "data" / "playbooks" / "modern_gun_core.2k5book"),),
                ))

    def test_playbook_pack_step_lands_in_the_receipt(self) -> None:
        from mod_editor.core import nfl2k5_playbook_pack as packs

        seed = ROOT / "data" / "playbooks" / "modern_gun_core.2k5book"
        calls: list[tuple[str, list[str]]] = []

        def fake_apply(target, paths, progress=None):
            calls.append((str(target), [Path(p).name for p in paths]))
            if progress:
                progress("Installing “Modern Gun Core” into ATL")
            pack = packs.load_pack(seed)
            return {"status": "applied", "packs": [{
                "pack": seed.name, "name": pack.book.name, "author": pack.book.author,
                "version": pack.book.version, "license": pack.book.license,
                "authored_on": pack.book.team, "book_fingerprint": pack.base.book_fingerprint,
                "formations": len(pack.formations), "plays": len(pack.plays),
                "books": [{"team": "ATL", "outer_index": 308, "retargeted": False,
                           "formations": 39, "plays": 254, "nodes": 2746, "changed_bytes": 2450}],
            }]}

        real_apply = packs.apply_packs_to_image
        real_is_image = mod_build.tt.is_disc_image
        real_inspect = mod_build.inspect
        pretend_image = lambda _path: True   # noqa: E731 - only the plan's image gate

        def inspect_for_real(target):
            # inspect() reads the real container; only the plan gate is pretending
            mod_build.tt.is_disc_image = real_is_image
            try:
                return real_inspect(target)
            finally:
                mod_build.tt.is_disc_image = pretend_image

        packs.apply_packs_to_image = fake_apply
        mod_build.tt.is_disc_image = pretend_image
        mod_build.inspect = inspect_for_real
        try:
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "default.xbe"
                source.write_bytes(_build_synthetic_xbe())
                target = Path(tmp) / "out.xbe"
                messages: list[str] = []
                receipt = mod_build.build(
                    mod_build.BuildPlan(str(source), str(target), playbook_packs=(str(seed),)),
                    lambda msg, a, b: messages.append(msg),
                )
        finally:
            packs.apply_packs_to_image = real_apply
            mod_build.tt.is_disc_image = real_is_image
            mod_build.inspect = real_inspect
        step = next(s for s in receipt["steps"] if s["step"] == "playbook_packs")
        self.assertEqual(step["status"], "applied")
        self.assertEqual(len(step["packs"]), 1)
        entry = step["packs"][0]
        self.assertEqual(entry["pack"], "modern_gun_core.2k5book")
        self.assertEqual(entry["name"], "Modern Gun Core")
        self.assertEqual(entry["license"], "CC0-1.0")
        self.assertEqual(entry["authored_on"], "ATL")
        self.assertEqual([b["team"] for b in entry["books"]], ["ATL"])
        self.assertEqual(list(receipt["plan"]["playbook_packs"]), [str(seed)])
        self.assertEqual(calls[0][1], ["modern_gun_core.2k5book"])
        self.assertTrue(any("playbook packs" in m for m in messages))
        self.assertEqual(receipt["result"]["playbook_packs"], "n/a")

    def test_unknown_preset_is_refused_and_names_are_kept(self) -> None:
        with self.assertRaises(KeyError):
            mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "nope")
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t", name="mine"), "softdrink_basic")
        self.assertEqual(plan.name, "mine")
