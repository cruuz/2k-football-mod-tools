"""b81 trades-all (ruling R6): computer trades at every position in the Studio (owner nfl2k5_cpu_trades).

Its own control (Realistic / Retail) that follows the quarterback control when a recipe names neither: unnamed, it is
Realistic where the quarterback room plan includes the quarterback trades (stage bit 16) or wanted them, Retail where the
room plan is Retail or leaves them out by choice, and None (the source kept) where the plan names no quarterback setting.
An explicit level wins. Realistic is installed only where the owner's needs are met (in the executable when one is
given, else in the plan); otherwise it is left out with the owner's LEFT_OUT note, never a refused build.

Its own build step ("cpu_trades", right after the quarterback room) in the full build, the in-place quarterback copy
(edit-sim-qb) and the v0.9 update (update-v09, both chains), with read-back. The CLI, the Build page, the recipe keys, the
memory model, the cave manifest recorder and the release package carry it.

Executable cases use CPU_TRADES_STANDARD_XBE (a standard build at 383 that carries the needs; the trades-all lane's
env-cpu-trades.sh), NFL2K5_B81_QB_STANDARD_XBE (a standard build without them) and NFL2K5_V09_XISO (the released v0.9
disc) from the b81 test environment; without them those cases skip. Every class fails on e7a29195b, where the Studio has
no CPU trades plan field, step, option or control.
"""
from __future__ import annotations

import ast
import contextlib
from dataclasses import replace
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from mod_editor.core import mod_build, modpack_sources  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as settings  # noqa: E402
from mod_editor.core import nfl2k5_cpu_trades as trades  # noqa: E402

STANDARD_XBE = os.environ.get("CPU_TRADES_STANDARD_XBE", "")
WITHOUT_NEEDS_XBE = os.environ.get("NFL2K5_B81_QB_STANDARD_XBE", "")
V09_XISO = os.environ.get("NFL2K5_V09_XISO", "")
HELP = ("Computer clubs trade players for draft picks when one club has a hole and another has a spare man: about 16 "
        "trades up to the Week 9 deadline and about 13 to 15 in each preseason after the first (a new franchise's first "
        "preseason has none). Clubs you control are never part of a computer trade. Retail keeps the original game's few "
        "player swaps.")


def _fixture(path, what):
    if not path or not Path(path).is_file():
        raise unittest.SkipTest(f"{what} is absent")
    return Path(path).read_bytes()


def _full(**fields):
    """A full build plan: the Experimental preset (quarterback injuries Realistic, the room's needs on) plus fields."""
    return replace(mod_build.apply_preset(mod_build.BuildPlan("s.iso", "t.iso"), "softdrink_experimental"), **fields)


class _Disc:
    """A bare executable standing in for the private disc copy (mod_build reads and writes default.xbe through it)."""

    def __init__(self, payload):
        self.payload = payload

    def patches(self):
        return (patch.object(mod_build, "_xbe_bytes", lambda _target: self.payload),
                patch.object(mod_build, "_write_xbe_bytes", lambda _target, data: setattr(self, "payload", bytes(data))))


class PlanResolutionTests(unittest.TestCase):
    """R6: the resolution table, explicit or followed, needs met or not (plan-based, no executable)."""

    def test_the_levels(self):
        self.assertEqual(settings.CPU_TRADES_LEVELS, (None, "retail", "realistic"))
        for good in settings.CPU_TRADES_LEVELS:
            settings.validate_cpu_trades(good)
        for bad in ("custom", "on", True, 1, "Realistic"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                settings.validate_cpu_trades(bad)

    def test_followed_and_explicit_with_the_needs_in_the_plan(self):
        # The Experimental preset: the room resolves to a stage set with the quarterback trades (bit 16) once the full
        # build adds the floor's needs, so a followed level is Realistic, and the needs are in the plan.
        plan = _full()
        self.assertIsNone(plan.cpu_trades)
        self.assertTrue(settings.cpu_trades_needs_met(lambda name: getattr(mod_build._with_qb_floor_needs(plan)[0], name)))
        self.assertEqual(mod_build._cpu_trades_plan(plan), ("realistic", None))
        self.assertEqual(mod_build._cpu_trades_plan(replace(plan, cpu_trades="realistic")), ("realistic", None))
        self.assertEqual(mod_build._cpu_trades_plan(replace(plan, cpu_trades="retail")), ("retail", None))

    def test_followed_retail_and_keep(self):
        # The quarterback option Retail: the room plan is Retail, so are the computer trades.
        self.assertEqual(mod_build._cpu_trades_plan(_full(sim_qb_injuries="retail")), ("retail", None))
        # The room named Retail beside Realistic injuries: the floor alone, no quarterback trades, so Retail.
        self.assertEqual(mod_build._cpu_trades_plan(_full(qb_room="retail")), ("retail", None))
        # Custom 0 percent: no floor and no quarterback trades, so Retail.
        self.assertEqual(mod_build._cpu_trades_plan(_full(sim_qb_injuries="custom", sim_qb_injury_rate=0.0)),
                         ("retail", None))
        # No quarterback setting named: the source is kept.
        self.assertEqual(mod_build._cpu_trades_plan(_full(sim_qb_injuries=None)), (None, None))
        self.assertEqual(mod_build._cpu_trades_plan(mod_build.BuildPlan("s", "t")), (None, None))

    def test_needs_not_met_leaves_them_out_with_the_owners_note(self):
        # Without the 2026 season (its week 9 trade deadline) neither trades can be installed: the room leaves the
        # quarterback trades out, and a followed or explicit Realistic is left out with the owner's note.
        for named in (None, "realistic"):
            with self.subTest(cpu_trades=named):
                plan = _full(season_2026=False, cpu_trades=named)
                self.assertEqual(mod_build._cpu_trades_plan(plan), (None, trades.LEFT_OUT))
                self.assertEqual(mod_build.validate_plan(plan), [])  # never a refused build
        # 64 MB: no 128 MB standard edition.
        small = replace(mod_build.BuildPlan("s", "t", console_memory=64), cpu_trades="realistic")
        self.assertEqual(mod_build._cpu_trades_plan(small), (None, trades.LEFT_OUT))
        # An explicit Retail never needs anything.
        self.assertEqual(mod_build._cpu_trades_plan(_full(season_2026=False, cpu_trades="retail")), ("retail", None))

    def test_needs_judged_on_the_executable_when_one_is_given(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        bare = _fixture(WITHOUT_NEEDS_XBE, "NFL2K5_B81_QB_STANDARD_XBE")
        self.assertTrue(trades.needs_met(source))
        self.assertFalse(trades.needs_met(bare))
        for named in (None, "realistic"):
            edit = mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic", cpu_trades=named)
            with self.subTest(cpu_trades=named):
                self.assertEqual(mod_build._cpu_trades_plan(edit, source), ("realistic", None))
                self.assertEqual(mod_build._cpu_trades_plan(edit, bare), (None, trades.LEFT_OUT))
        # Where an earlier build placed another option in the pages' range (an owner that reports it), the trades are
        # left out with a plain note instead of a refused build.
        edit = mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic")
        with patch.object(trades, "unowned_problem", create=True, return_value="another owner is allocated there"):
            level, note = mod_build._cpu_trades_plan(edit, source)
        self.assertEqual((level, note), (None, mod_build._CPU_TRADES_OCCUPIED))
        self.assertNotIn("\u2014", note)
        # A full build judges the written executable too (the step passes it), whatever its plan says.
        self.assertEqual(mod_build._cpu_trades_plan(_full(season_2026=False, cpu_trades="realistic"), source),
                         ("realistic", None))


class RecipeTests(unittest.TestCase):
    def test_to_recipe_omits_an_unnamed_level_and_round_trips_a_named_one(self):
        self.assertNotIn("cpu_trades", _full().to_recipe())
        for level in ("retail", "realistic"):
            with self.subTest(level=level):
                recipe = {"preset": "softdrink_experimental", "overrides": {"cpu_trades": level}}
                plan = modpack_sources.build_plan(recipe)
                self.assertEqual(plan.cpu_trades, level)
                self.assertEqual(plan.to_recipe()["cpu_trades"], level)
                self.assertEqual(settings.to_plan(settings.from_plan(plan), "s", "t").cpu_trades, level)
                self.assertEqual(settings.build_settings({"cpu_trades": level})["cpu_trades"], level)
        unnamed = modpack_sources.build_plan({"preset": "softdrink_experimental", "overrides": {}})
        self.assertIsNone(unnamed.cpu_trades)
        with self.assertRaises(ValueError):
            modpack_sources.build_plan({"preset": "softdrink_experimental", "overrides": {"cpu_trades": "custom"}})
        with self.assertRaises(ValueError):
            settings.build_settings({"cpu_trades": "on"})
        self.assertIn("cpu_trades", settings.FEATURE_KEYS)
        self.assertIn("cpu_trades=None", "".join(f"{f.name}={f.default}" for f in __import__("dataclasses").fields(
            mod_build.BuildPlan) if f.name == "cpu_trades"))

    def test_presets_leave_it_unnamed_so_it_follows(self):
        for name in mod_build.PRESETS:
            for memory in (64, 128):
                plan = mod_build.apply_preset(replace(mod_build.BuildPlan("s", "t", console_memory=memory),
                                                      cpu_trades="retail"), name)
                with self.subTest(preset=name, memory=memory):
                    self.assertIsNone(plan.cpu_trades)
        self.assertEqual(mod_build._cpu_trades_plan(_full())[0], "realistic")

    def test_a_named_level_asks_for_an_executable_patch(self):
        self.assertTrue(mod_build.BuildPlan("s", "t", cpu_trades="retail").wants_xbe_patch())
        self.assertIs(mod_build.availability()["cpu_trades"], True)
        self.assertIn("nfl2k5_cpu_trades", [row[0] for row in mod_build._LATE_OWNER_OPTIONS])


class RouteTests(unittest.TestCase):
    """The step's place and the plan constructors of the in-place routes."""

    def test_the_step_label(self):
        from mod_editor.core import build_steps
        labels = next(v for v in vars(build_steps).values() if isinstance(v, dict) and "qb_room" in v)
        self.assertEqual(labels["cpu_trades"], "Computer trades at every position")

    def test_each_route_calls_the_step_right_after_the_quarterback_room(self):
        tree = ast.parse((ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8"))
        for function in ("_build", "_update_v09_disc", "_edit_installed_sim_qb"):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
            calls = sorted((c.lineno, c.func.id) for c in ast.walk(node)
                           if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id.startswith("_apply_"))
            names = [name for _line, name in calls]
            with self.subTest(function=function):
                self.assertEqual(names.count("_apply_cpu_trades"), 1)
                self.assertEqual(names[names.index("_apply_qb_room") + 1], "_apply_cpu_trades")

    def test_the_v09_expected_chain_writes_them_right_after_the_room(self):
        tree = ast.parse((ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_update_v09_disc")
        appended = [name for _line, name in sorted(
            (c.lineno, ast.literal_eval(c.args[0])) for c in ast.walk(node) if isinstance(c, ast.Call)
            and ast.unparse(c.func) == "receipt['v09_update'].append" and isinstance(c.args[0], ast.Constant))]
        self.assertEqual(appended[appended.index("qb_room") + 1], "cpu_trades")

    def test_the_in_place_plans_carry_it(self):
        edit = mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic")
        self.assertIsNone(edit.cpu_trades)
        self.assertTrue(mod_build._only_sim_qb_changes(edit))
        named = mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic", cpu_trades="retail")
        self.assertEqual(named.cpu_trades, "retail")
        self.assertTrue(mod_build._only_sim_qb_changes(named))
        self.assertEqual(mod_build.validate_plan(named), [])
        update = mod_build.v09_disc_update("s.iso", "t.iso", sim_qb_injuries="realistic", cpu_trades="realistic")
        self.assertEqual(update.cpu_trades, "realistic")
        self.assertEqual(mod_build.v09_disc_update("s.iso", "t.iso", cpu_trades="retail").cpu_trades, "retail")
        for bad in ("custom", True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic", cpu_trades=bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                mod_build.v09_disc_update("s.iso", "t.iso", sim_qb_injuries="realistic", cpu_trades=bad)

    def test_the_command_line(self):
        from tools import nfl2k5_modpack as cli
        for command, extra in (("update-v09", ["--sim-qb-injuries", "realistic"]), ("edit-sim-qb", ["--mode", "realistic"])):
            for level in (None, "retail", "realistic"):
                args = [command, "--source", "old.iso", "--out", "new.iso", "--json", *extra]
                if level:
                    args += ["--cpu-trades", level]
                with (self.subTest(command=command, level=level), patch.object(mod_build, "build", return_value={}) as run,
                      contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                    self.assertEqual(cli.main(args), 0)
                    self.assertEqual(run.call_args.args[0].cpu_trades, level)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            cli.main(["edit-sim-qb", "--source", "a", "--out", "b", "--mode", "realistic", "--cpu-trades", "custom"])
        text = (ROOT / "tools/nfl2k5_modpack.py").read_text(encoding="utf-8")
        self.assertEqual(text.count('add_argument("--cpu-trades"'), 3)  # build-sources, update-v09, edit-sim-qb


class InPlaceTests(unittest.TestCase):
    """The real in-place quarterback copy (preflight: nothing is written) on standard executables from the env."""

    def _edit(self, plan, image):
        receipt = {"steps": [], "result": {}}
        seen = []
        real = trades.apply

        def spy(payload, level="realistic"):
            result = real(payload, level)
            seen.append((payload, level, result[0]))
            return result
        with patch.object(trades, "apply", spy):
            self.assertTrue(mod_build._edit_installed_sim_qb(plan, Path("source.iso"), Path("copy.iso"), image, receipt,
                                                             lambda *_: None, preflight=True, consume=False,
                                                             reference=None))
        return receipt, seen

    def test_the_copy_adds_them_after_the_room_where_the_needs_are(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        for named in (None, "realistic"):
            with self.subTest(cpu_trades=named):
                receipt, seen = self._edit(mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic", cpu_trades=named),
                                           source)
                (before, level, after), = seen
                self.assertEqual(level, "realistic")
                # Judged and written on the executable the room step leaves (the floor's needs included).
                self.assertEqual(hashlib.sha256(before).hexdigest(), receipt["qb_room_source_update"]["result_sha256"])
                update = receipt["cpu_trades_source_update"]
                self.assertEqual((update["level"], update["result_sha256"]),
                                 ("realistic", hashlib.sha256(after).hexdigest()))
                self.assertEqual((update["settings"]["status"], update["settings"]["stages"], update["settings"]["va"]),
                                 ("applied", trades.REALISTIC_STAGES, 0x152E000))
                self.assertEqual(trades.read_settings(after)["status"], "applied")
                self.assertEqual(trades.read_settings(before)["status"], "retail")
                self.assertNotIn(trades.LEFT_OUT, receipt.get("user_notes", []))

    def test_retail_removes_them(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        installed, _ = trades.apply(source, "realistic")
        empty = trades._retail(installed)[0]
        for mode, named in (("realistic", "retail"), ("retail", None)):
            with self.subTest(mode=mode, cpu_trades=named):
                receipt, seen = self._edit(mod_build.sim_qb_disc_edit("s.iso", "t.iso", mode, cpu_trades=named),
                                           installed)
                (before, level, after), = seen
                self.assertEqual(level, "retail")
                self.assertEqual(trades.read_settings(before)["status"], "applied")
                self.assertEqual(trades.read_settings(after), {"status": "retail", "mode": "retail", "reserved": True,
                                                               "va": 0x152E000})
                self.assertEqual(receipt["cpu_trades_source_update"]["level"], "retail")
                if mode == "realistic":
                    # Only the computer trades changed after the room: the reservation stays, the pages are empty.
                    self.assertEqual(after, trades._retail(before)[0])
        self.assertEqual(trades.read_settings(empty)["status"], "retail")

    def test_left_out_where_the_needs_are_missing_never_refused(self):
        bare = _fixture(WITHOUT_NEEDS_XBE, "NFL2K5_B81_QB_STANDARD_XBE")
        # Custom 0 percent adds no floor (so no modern IR): the computer trades' needs stay missing.
        plan = mod_build.sim_qb_disc_edit("s.iso", "t.iso", "custom", custom_rate=0.0, cpu_trades="realistic")
        receipt, seen = self._edit(plan, bare)
        self.assertEqual(seen, [])
        self.assertIn(trades.LEFT_OUT, receipt["user_notes"])
        self.assertEqual(receipt["cpu_trades_source_update"]["level"], None)
        self.assertEqual(receipt["cpu_trades_source_update"]["user_notes"], [trades.LEFT_OUT])


class StepTests(unittest.TestCase):
    """_apply_cpu_trades: receipt and read-back on the written executable (a full build's plan)."""

    def _step(self, plan, payload):
        disc = _Disc(payload)
        receipt = {"steps": [], "result": {}}
        reading, writing = disc.patches()
        with reading, writing:
            mod_build._apply_cpu_trades(plan, Path("t.iso"), receipt, lambda *_: None)
        return disc.payload, receipt

    def test_realistic_receipt_and_readback(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        written, receipt = self._step(_full(), source)
        self.assertEqual(written, trades.apply(source, "realistic")[0])
        step, = [s for s in receipt["steps"] if s["step"] == "cpu_trades"]
        self.assertEqual((step["status"], step["settings"]["status"], step["settings"]["stages"], step["allocated"]),
                         ("applied", "applied", trades.REALISTIC_STAGES, True))
        self.assertEqual(receipt["result"]["cpu_trades"], "realistic")
        # Again on the result: already applied, nothing written.
        again, receipt = self._step(_full(), written)
        self.assertEqual(again, written)
        self.assertEqual(receipt["steps"][0]["status"], "already_applied")
        self.assertEqual(mod_build._verify_cpu_trades(_full(), trades, written)["status"], "applied")

    def test_retail_removes_them_and_the_reservation_stays(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        installed, _ = trades.apply(source, "realistic")
        written, receipt = self._step(_full(cpu_trades="retail"), installed)
        self.assertEqual(trades.read_settings(written)["status"], "retail")
        self.assertTrue(trades.read_settings(written)["reserved"])
        self.assertEqual(receipt["result"]["cpu_trades"], "retail")
        self.assertEqual(receipt["steps"][0]["status"], "retail")

    def test_left_out_and_nothing_to_do(self):
        bare = _fixture(WITHOUT_NEEDS_XBE, "NFL2K5_B81_QB_STANDARD_XBE")
        written, receipt = self._step(_full(cpu_trades="realistic"), bare)
        self.assertEqual(written, bare)
        self.assertEqual(receipt["steps"], [{"step": "cpu_trades", "status": "left_out", "user_notes": [trades.LEFT_OUT]}])
        self.assertEqual((receipt["result"]["cpu_trades"], receipt["user_notes"]), ("left_out", [trades.LEFT_OUT]))
        # A plan without any quarterback or trades setting never reads the executable.
        receipt = {"steps": [], "result": {}}
        with patch.object(mod_build, "_xbe_bytes", side_effect=AssertionError("read")):
            mod_build._apply_cpu_trades(mod_build.BuildPlan("s", "t"), Path("t.iso"), receipt, lambda *_: None)
        self.assertEqual(receipt, {"steps": [], "result": {}})

    def test_a_readback_that_differs_is_refused(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        with self.assertRaisesRegex(ValueError, "[Cc]omputer trades"):
            mod_build._verify_cpu_trades(_full(), trades, source)  # Realistic wanted, the executable is retail
        installed, _ = trades.apply(source, "realistic")
        with self.assertRaisesRegex(ValueError, "[Cc]omputer trades"):
            mod_build._verify_cpu_trades(_full(cpu_trades="retail"), trades, installed)
        disc = _Disc(source)
        receipt = {"steps": [], "result": {}}
        with (patch.object(mod_build, "_xbe_bytes", lambda _t: disc.payload),
              patch.object(mod_build, "_write_xbe_bytes", lambda _t, data: setattr(disc, "payload", source)),
              self.assertRaisesRegex(ValueError, "computer trades")):
            mod_build._apply_cpu_trades(_full(), Path("t.iso"), receipt, lambda *_: None)

    def test_a_foreign_source_is_refused_before_any_write(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        installed = bytearray(trades.apply(source, "realistic")[0])
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        at = XbeImage(bytes(installed)).offset(0x152E000 + 0x10, 1)
        installed[at] ^= 0xFF
        self.assertEqual(trades.status(bytes(installed)), "foreign")
        self.assertEqual(mod_build.inspect_cpu_trades(bytes(installed))["cpu_trades"], "foreign")
        with self.assertRaisesRegex(ValueError, "computer trades"):
            mod_build._cpu_trades_preflight(_full(), bytes(installed))


class V09UpdateTests(unittest.TestCase):
    """The released v0.9 disc: the update's expected chain installs them right after the room (preflight only)."""

    def _preflight(self, plan, disc):
        xbe = mod_build._xbe_bytes(disc)
        release = mod_build._v09_reference(disc, xbe)
        with patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
            return mod_build._update_v09_disc(replace(plan, source=str(disc)), lambda *_: None, preflight=True,
                                              project=False)

    def test_the_expected_chain_includes_them(self):
        if not V09_XISO or not Path(V09_XISO).is_file():
            self.skipTest("the released v0.9 disc is absent")
        disc = Path(V09_XISO)
        receipt = self._preflight(mod_build.v09_disc_update(str(disc), "t.iso", sim_qb_injuries="realistic"), disc)
        steps = receipt["v09_update"]
        self.assertEqual(steps[steps.index("qb_room") + 1], "cpu_trades")
        self.assertNotIn(trades.LEFT_OUT, receipt.get("user_notes", []))
        # Retail on the quarterback option: the trades follow it (nothing to remove on v0.9, still the same step).
        receipt = self._preflight(mod_build.v09_disc_update(str(disc), "t.iso", sim_qb_injuries="retail"), disc)
        self.assertIn("cpu_trades", receipt["v09_update"])
        # Named Realistic without modern injured reserve (not ticked, no injuries): left out with the note.
        receipt = self._preflight(mod_build.v09_disc_update(str(disc), "t.iso", backfield_cards=True,
                                                            cpu_trades="realistic"), disc)
        self.assertNotIn("cpu_trades", receipt["v09_update"])
        self.assertIn(trades.LEFT_OUT, receipt["user_notes"])


class MemoryAndPackagingTests(unittest.TestCase):
    def test_the_memory_model_counts_the_fixed_pages(self):
        from mod_editor.core import nfl2k5_memory_budget as budget, nfl2k5_xbe_space as space
        options = budget.options(_full())
        self.assertIn("cpu_trades", budget.owners(options, 128))
        self.assertNotIn("cpu_trades", budget.owners(budget.options(_full(cpu_trades="retail")), 128))
        self.assertNotIn("cpu_trades", budget.owners(budget.options(_full(season_2026=False)), 128))
        pool_end = space.CPU_TRADES_VA + space.CPU_TRADES_SIZE - space.POOL_VA
        resident = budget.xbe_resident(options, 128)
        without = budget.xbe_resident(budget.options(_full(cpu_trades="retail")), 128)
        self.assertGreaterEqual(resident - without, 0)
        self.assertGreaterEqual(resident, budget.RETAIL_RESIDENT + budget.LEGACY_SPACE + budget.SCALEOUT_V3 + pool_end)

    def test_the_release_package_ships_the_owner(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").split()
        from mod_editor.core import providers
        pinned = (ROOT / "mod_editor/core/providers.py").read_text(encoding="utf-8")
        for module in ("mod_editor/core/nfl2k5_cpu_trades.py", "mod_editor/core/nfl2k5_cpu_trades_code.py"):
            with self.subTest(module=module):
                self.assertIn(module, allow)
                digest = hashlib.sha256((ROOT / module).read_bytes()).hexdigest()
                self.assertIn(f'"{module}": "{digest}"', pinned)
        self.assertTrue(providers)

    def test_the_cave_manifest_recorder_observes_the_owner(self):
        text = (ROOT / "mod_editor/core/nfl2k5_cave_manifest.py").read_text(encoding="utf-8")
        self.assertIn("nfl2k5_cpu_trades as cpu_trades", text)
        self.assertIn("modules[cpu_trades.__name__] = cpu_trades", text)
        self.assertIn("cpu_trades.OWNER", text)
        self.assertIn('if owner == "nfl2k5_cpu_trades":', text)

    def test_inspect_reports_them(self):
        source = _fixture(STANDARD_XBE, "CPU_TRADES_STANDARD_XBE")
        self.assertEqual(mod_build.inspect_cpu_trades(source)["cpu_trades"], "retail")
        installed, _ = trades.apply(source, "realistic")
        report = mod_build.inspect_cpu_trades(installed)
        self.assertEqual((report["cpu_trades"], report["cpu_trades_settings"]["stages"]),
                         ("applied", trades.REALISTIC_STAGES))


class BuildPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.panel = BuildPanel(available={})
        self.addCleanup(self.panel.deleteLater)
        source = Path(self.temp.name) / "game.iso"
        source.write_bytes(bytes(4096))
        state = {key: "retail" for key in self.panel._boxes()}
        state.update(path=str(source), container="xiso", throw=None, sim_qb_injuries="retail",
                     sim_qb_injury_settings={"status": "retail", "mode": "retail", "custom_rate": .310},
                     qb_room="retail", qb_room_settings={"status": "retail", "mode": "retail"},
                     cpu_trades="retail", cpu_trades_settings={"status": "retail", "mode": "retail"})
        self.state = state
        self.panel.apply_state(dict(state))

    def test_the_control_its_choices_and_help(self):
        combo = self.panel.cpu_trades_mode
        self.assertEqual([(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())],
                         [("Same as the quarterback option", None), ("Realistic", "realistic"), ("Retail", "retail")])
        self.assertEqual(combo.toolTip(), HELP)
        self.assertEqual(self.panel.cpu_trades_help.text(), HELP)
        self.assertNotIn("—", HELP)

    def test_the_control_reaches_the_plan_and_the_follow_rule(self):
        combo, mode = self.panel.cpu_trades_mode, self.panel.qb_injury_mode
        self.panel.apply_preset("softdrink_experimental")
        self.assertIsNone(combo.currentData())
        for value in (None, "realistic", "retail"):
            with self.subTest(cpu_trades=value):
                combo.setCurrentIndex(combo.findData(value))
                plan = self.panel._plan_for_build()
                self.assertEqual(plan.cpu_trades, value)
                self.assertEqual(mod_build._cpu_trades_plan(plan)[0], value or "realistic")
        combo.setCurrentIndex(combo.findData("retail"))
        mode.setCurrentIndex(mode.findData("retail"))
        self.panel.apply_preset("softdrink_experimental")
        self.assertIsNone(combo.currentData())  # a preset leaves it unnamed (it follows)

    def test_it_rides_with_the_in_place_copies(self):
        plan = self.panel.plan()
        self.assertEqual(self.panel._sim_qb_companion_choices(replace(plan, cpu_trades="retail")),
                         self.panel._sim_qb_companion_choices(plan))
        self.assertEqual(self.panel._v09_companion_choices(replace(plan, cpu_trades="retail")),
                         self.panel._v09_companion_choices(plan))

    def test_a_trades_only_difference_counts_as_a_change(self):
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        slice_now = {"status": "applied", "mode": "realistic", "custom_rate": .310, "revision": qb.REVISION}
        from mod_editor.core import nfl2k5_qb_room as room
        on_disc = dict(self.state, sim_qb_injuries="applied", sim_qb_injury_settings=slice_now, qb_room="applied",
                       qb_room_settings={"status": "applied", "mode": "realistic",
                                         "stages": room.studio_stages(True, True, True)},
                       depth_locks="applied", depth_chart_rows="applied", trade_deadline="applied",
                       franchise_economy="applied", practice_squad="applied", modern_injured_reserve="applied")
        combo, mode = self.panel.cpu_trades_mode, self.panel.qb_injury_mode
        for installed, named, change in (("retail", None, "Computer trades (Realistic)"), ("applied", None, ""),
                                         ("applied", "retail", "Computer trades (Retail)"), ("retail", "retail", ""),
                                         ("applied", "realistic", "")):
            with self.subTest(installed=installed, named=named):
                self.panel.apply_state(dict(on_disc, cpu_trades=installed, cpu_trades_settings={"status": installed}))
                mode.setCurrentIndex(mode.findData("realistic"))
                combo.setCurrentIndex(combo.findData(named))
                self.assertEqual(self.panel._sim_qb_injury_change(), change)

    def test_a_foreign_disc_disables_the_controls(self):
        self.panel.apply_state(dict(self.state, cpu_trades="foreign", cpu_trades_settings={"status": "foreign"}))
        self.assertFalse(self.panel.qb_injury_mode.isEnabled())
        self.assertFalse(self.panel.cpu_trades_mode.isEnabled())
        self.assertIn("computer trades", self.panel.qb_injury_help.text())

    def test_a_saved_project_restores_it(self):
        from mod_editor.gui import gameplay_project_ui
        self.panel.cpu_trades_mode.setCurrentIndex(self.panel.cpu_trades_mode.findData("retail"))
        state = gameplay_project_ui.capture(self.panel)
        self.assertEqual(state["cpu_trades"], "retail")
        self.panel.cpu_trades_mode.setCurrentIndex(0)
        gameplay_project_ui.restore(self.panel, state)
        self.assertEqual(self.panel.cpu_trades_mode.currentData(), "retail")


class FaqTests(unittest.TestCase):
    def test_one_plain_faq_paragraph_beside_the_quarterback_trades(self):
        text = (ROOT / "docs/mod_editor/2k5_mod_studio_faq.md").read_text(encoding="utf-8")
        section = text.split("## How do quarterback injuries work when I simulate a franchise game?", 1)[1].split("\n## ", 1)[0]
        paragraphs = section.split("\n\n")
        quarterback = next(i for i, p in enumerate(paragraphs) if "trade for a quarterback" in p)
        trades_text = paragraphs[quarterback + 1]
        for words in ("Computer trades", "Same as the quarterback option", "about 16 trades", "about 13 to 15 in each preseason after the first",
                      "first preseason has none",
                      "never part of a computer trade", "Retail keeps the original game's few player swaps",
                      "--cpu-trades"):
            with self.subTest(words=words):
                self.assertIn(words, trades_text)
        self.assertNotIn("—", trades_text)


if __name__ == "__main__":
    unittest.main()
