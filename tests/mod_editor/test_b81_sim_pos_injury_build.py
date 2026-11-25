"""b81 slices 2 and 3 and the long-franchise stability (pos2/DESIGN.md and pos3/DESIGN.md section 6 test 4, addendum A.6
test 3): Simulated injuries through the real Studio build path, revision 4 (revision 5 since b81 game outcomes: the
kicker and punter rows; revision 4 installs, written with the frozen module, upgrade in place like slices 1-3).

The first pass is the branch's own request expression, evaluated inside mod_build._build on the resolved plan
(read-only preflight on the private retail disc). Every later step is the real installer: K128, the running-back
owner, the simulator, the lineup roles, the rookie-face generator, injured reserve through Build's own step (it
appends franchise ownership), the rookie hair, the offset toss, Backfield cards and the option through Build's own
step. The released v0.9 case runs Build's update-v09 route. In every case:

- the bank is at 0x1524000 and no allocation row moves at any step;
- 0x133CC9 holds the game's own tail under Realistic and Custom above 0, and the running-back jump otherwise;
- Realistic (or Custom) then Retail equals the same build with only the empty reservation;
- slice 1, 2 and 3 installs (QBMEDv1 to v3), each written with its frozen code module, upgraded in place equal the
  fresh revision 4 install byte for byte, and Retail from each equals the empty reservation;
- the running-back owner, the simulator and the lineup roles read as they do without the option.

Private-disc cases skip without .b77-scratch/b81/env.sh; run them with it.
"""
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_lineup_roles as lineup, nfl2k5_sim_qb_injuries as qb
from mod_editor.core import nfl2k5_sim_rb_injuries as running_backs, nfl2k5_sim_realism as simulator
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_pass_protection as pressure
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

BANK = (0x1524000, 16384, 4096)
WEEKLY_SITE = 0x133CC9
GAME_TAIL = bytes.fromhex("5f5e5bc390")
V09_XBE = "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866"
# The Studio-made slice 1 Realistic standard executable and its Retail result (beta81/evidence/nov19-qb-product).
SLICE1_STUDIO_XBE = "9f435b380a948c976cf4fe1160a8137a157f7bb93cd202b5fb04d49195c42a6a"
SLICE1_STUDIO_RETAIL = "286b83fa6eb0f5f5d0a0e5092c6bf8b051d9cc93c97cc92ad6e0c021705ce649"

# Late steps in more than one order. Build's own order (mod_build._build): the rookie step appends the hair, then
# injured reserve with franchise ownership, the offset toss, Backfield cards and the option last. The hair must be
# appended before the toss in every order (nfl2k5_xbe_space.LATE_OWNERS; test_b780_int_first_pass pins that rule):
# the toss appended first would make the hair's append move it, which extend_scaleout refuses for any build.
ORDERS = (
    ("studio order, option last", ("hair", "ownership", "toss", "cards", "option")),
    ("option first", ("option", "hair", "ownership", "toss", "cards")),
    ("option before Backfield cards", ("hair", "ownership", "toss", "option", "cards")),
    ("cards and ownership before the appends", ("cards", "option", "ownership", "hair", "toss")),
)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _rows(payload):
    return [row for row in space.layout(payload)["allocations"] if row["owner"] != space.DIRECTORY_OWNER]


def _bank(payload):
    rows = [row for row in space.layout(payload)["allocations"] if row["owner"] == qb.OWNER]
    return (rows[0]["va"], rows[0]["size"], rows[0]["align"]) if rows else None


def _running_back_jump(payload):
    row, = (r for r in space.layout(payload)["allocations"] if r["owner"] == running_backs.OWNER)
    return b"\xe9" + struct.pack("<i", row["va"] - WEEKLY_SITE - 5)


def _weekly(payload):
    return XbeImage(payload).read(WEEKLY_SITE, 5)


def _reserved(payload):
    """The source plus the empty reservation (what Retail must give back)."""
    return payload if _bank(payload) else space.extend_scaleout(payload, qb.REQUESTS)[0]


def _older_install(physical, mode, rate, revision):
    """An earlier slice's install as its settings module wrote it: the frozen code module's bank and edits, its marker.

    Slice 1 (d8ceb91e3) has no weekly edit. Slice 2 (d2abd00a5, the refit) and slice 3 (712835585) pass the running-back
    cave when that cave is installed; their edits() add the parked weekly jump only with a rate above zero."""
    from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice1 as slice1
    from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice2 as slice2
    from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice3 as slice3
    from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_v4 as v4   # b81 game outcomes: revision 5 is current
    frozen = {1: slice1, 2: slice2, 3: slice3, 4: v4}[revision]
    physical = _reserved(physical)
    image = XbeImage(physical)
    bank, = (r for r in space.layout(physical)["allocations"] if r["owner"] == qb.OWNER)
    sim, data = simulator._allocations(physical)
    addresses = (bank["va"], sim["va"], data["va"], qb._lineup_va(physical))
    marker = struct.pack("<8sIII", b"QBMEDv%d\0" % revision, 1 if mode == "realistic" else 2, rate, 0)
    body = frozen.bank_bytes(image.read, *addresses, rate=rate, marker=marker)
    extra = {}
    if revision >= 2:
        cave, = (r for r in space.layout(physical)["allocations"] if r["owner"] == running_backs.OWNER)
        extra["rb_va"] = None if image.read(cave["va"], cave["size"]) == b"\xcc" * cave["size"] else cave["va"]
    edits = (*frozen.edits(*addresses, rate=rate, **extra), ("bank", bank["va"], b"\xcc" * bank["size"], body))
    return qb._transform(physical, edits, restoring=False)


def _slice1_install(physical, mode, rate):
    return _older_install(physical, mode, rate, 1)


def _units(plan):
    return qb._setting(plan.sim_qb_injuries, plan.sim_qb_injury_rate).rate


# Optional evidence: with NFL2K5_B81_POS_BUILD_RECORD set to a file path, each case's result hashes are written there.
_RECORD = {}


class _BuildPath(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        target = os.environ.get("NFL2K5_B81_POS_BUILD_RECORD")
        if target and _RECORD:
            Path(target).write_text(json.dumps(_RECORD, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        super().tearDownClass()

    def record(self, case, **payloads):
        _RECORD[f"{type(self).__name__}.{self._testMethodName}: {case}"] = {
            name: _sha(payload)[:16] for name, payload in payloads.items()}
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def private_path(self, variable):
        path = Path(os.environ.get(variable, ""))
        if not path.is_file():
            self.skipTest(f"private disc fixture {variable} is absent")
        return path

    def studio_first_pass(self, plan):
        """Stop _build in read-only preflight and evaluate its own first-pass expression on its resolved plan."""
        from mod_editor.core import nfl2k5_throw_tuning as tt

        build = inspect.unwrap(mod_build._build)
        body = ast.parse(inspect.getsource(build)).body[0].body
        assignment, = (statement for statement in body if isinstance(statement, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "all_requests" for t in statement.targets))
        self.assertEqual(ast.unparse(assignment.value.func), "tt._selected_space_requests")
        expression = compile(ast.Expression(assignment.value), mod_build.__file__, "eval")
        verify = tt._check_installed_runtime_settings

        class Captured(Exception):
            pass

        def capture(payload, options):
            verify(payload, options)
            frame = sys._getframe(1)
            if frame.f_code is build.__code__:
                self.assertIs(frame.f_locals["r62"], options)
                raise Captured(payload, eval(expression, frame.f_globals, frame.f_locals), frame.f_locals["plan"])

        with patch.object(mod_build, "check_playbook_pack_fit", return_value=None), \
                patch.object(tt, "_check_installed_runtime_settings", new=capture), self.assertRaises(Captured) as found:
            mod_build._build(plan, _preflight_only=True)
        self.assertFalse(Path(plan.target).exists())
        return found.exception.args

    def keep_rows(self, before, payload, step):
        rows = _rows(payload)
        self.assertEqual([row for row in before if row not in rows], [], f"an allocation row moved at {step}")
        return rows

    def studio_steps(self, plan):
        from mod_editor.core import nfl2k5_backfield_cards as cards, nfl2k5_offset_toss as toss
        from mod_editor.core import nfl2k5_rookie_faces as faces

        def through_build(step):
            def run(current):
                target = self.folder / "working.xbe"
                target.write_bytes(current)
                step(target)
                return target.read_bytes()
            return run

        receipt = lambda: {"steps": [], "result": {}}  # noqa: E731
        quiet = lambda *_: None  # noqa: E731
        return {
            # Build's real mode selection, including the standard-only stock guard; it appends franchise ownership.
            "ownership": through_build(lambda t: mod_build._apply_injured_reserve(plan, t, receipt(), quiet)),
            "hair": lambda x: faces.apply_hair(x)[0],
            "toss": lambda x: toss.apply(x)[0],
            "cards": lambda x: cards.apply(x)[0],
            # Build's own step: the installer, the written-file readback and _verify_sim_qb_injuries (revision 4).
            "option": through_build(lambda t: mod_build._apply_sim_qb_injuries(plan, t, receipt(), quiet)),
        }

    def run_order(self, start, order, option):
        current, rows = start, _rows(start)
        for name in order:
            current = option(current) if name == "option" else self.steps[name](current)
            rows = self.keep_rows(rows, current, name)
            if name == "option":
                self.assertEqual(_bank(current), BANK)
        self.assertEqual(_bank(current), BANK)
        return current

    def check_orders(self, start, plan, orders=ORDERS):
        """Every order: fresh revision 4, the empty reservation only, and slice 1, 2 and 3 installs upgraded in place."""
        units = _units(plan)
        self.steps = self.studio_steps(plan)
        self.assertEqual(running_backs.status(start), "applied")
        finals = {}
        for label, order in orders:
            with self.subTest(order=label):
                fresh = self.run_order(start, order, self.steps["option"])
                blank = self.run_order(start, order, _reserved)
                older = {revision: self.run_order(start, order, lambda x, r=revision: _older_install(
                    x, plan.sim_qb_injuries, units, r)) for revision in (1, 2, 3, 4)}
                self.assertEqual(_rows(fresh), _rows(blank))
                for old in older.values():
                    self.assertEqual(_rows(old), _rows(blank))
                self.assertEqual(_weekly(fresh), GAME_TAIL if units else _running_back_jump(fresh))
                self.assertEqual(_weekly(blank), _running_back_jump(blank))
                # Realistic (or Custom) then Retail: the source plus the empty reservation, byte for byte.
                self.assertEqual(qb.physical_view(fresh), blank)
                restored, receipt = qb.apply(fresh, "retail")
                self.assertEqual(restored, blank)
                self.assertEqual(receipt["status"], "retail")
                for reader in (running_backs.status, simulator.status, lineup.read_settings):
                    self.assertEqual(reader(fresh), reader(blank), reader.__module__)
                self.assertEqual(running_backs.status(fresh), "applied")
                self.assertEqual(simulator.status(fresh), "applied")
                # Slice 1, 2 and 3 installs of the same choice are upgraded in place to the fresh bytes. Revision 4
                # writes other bank bytes than slice 3 at every rate (the stability piece), the same rows and sites.
                self.assertNotEqual(older[3], fresh)
                self.assertEqual(_weekly(older[1]), _running_back_jump(older[1]))
                self.assertEqual(_weekly(older[2]), _weekly(fresh))
                self.assertEqual(_weekly(older[3]), _weekly(fresh))
                for revision, old in older.items():
                    self.assertEqual(running_backs.status(old), "applied")
                    upgraded, receipt = qb.apply(old, plan.sim_qb_injuries, custom_rate=plan.sim_qb_injury_rate)
                    self.assertEqual(receipt.get("upgraded_from"), f"slice{revision}")
                    self.assertEqual(upgraded, fresh)
                    self.assertEqual(qb.apply(old, "retail")[0], blank)
                    self.assertEqual(qb.read_settings(old).get("revision"), revision)
                settings = qb.read_settings(fresh)
                self.assertEqual((settings["status"], settings["mode"], settings.get("revision"),
                                  settings.get("positions")), ("applied", plan.sim_qb_injuries, qb.REVISION, units > 0))
                self.assertEqual(round(settings["custom_rate"] * 1000), units)
                self.assertEqual(qb.apply(restored, plan.sim_qb_injuries, custom_rate=plan.sim_qb_injury_rate)[0], fresh)
                finals[label] = fresh
                self.record(f"{plan.sim_qb_injuries} {units} / {label}", option=fresh, retail=blank, slice1=older[1],
                            slice2=older[2], slice3=older[3])
        # The option's position among the late steps never changes the result (only the other appends may).
        same = [finals[label] for label, order in orders if label in finals and [s for s in order if s != "option"]
                == [s for s in ORDERS[0][1] if s != "option"]]
        self.assertEqual(len(same), sum(1 for label, order in orders if [s for s in order if s != "option"]
                                        == [s for s in ORDERS[0][1] if s != "option"]))
        self.assertTrue(all(final == same[0] for final in same))
        return finals


class FreshStandardBuilds(_BuildPath):
    """Fresh builds from the private retail disc with the standard recipe, the Experimental preset and Custom."""

    def fresh(self, plan, orders=ORDERS):
        from mod_editor.core import nfl2k5_k128 as k128, nfl2k5_modern_positions as positions
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_rookie_faces as faces
        from tests.nfl2k5_supersim_draft_fixture import RETAIL_SHA256, retail_roster

        retail, requests, plan = self.studio_first_pass(plan)
        self.assertEqual(hashlib.sha256(retail).hexdigest(), RETAIL_SHA256)
        self.assertIn(space.QB_INJURY_REQUEST, requests)
        self.assertTrue(plan.sim_rb_injuries and plan.sim_realism and plan.k128_memory)
        current, _ = space.apply(retail, requests, scaleout=True)
        rows = _rows(current)
        self.assertEqual(_bank(current), BANK)
        current, _ = k128.apply(current, require=True, early=plan.k128_early, roster_heap=plan.k128_roster_heap)
        current, _ = running_backs.apply(current)  # Build: the running-back owner, then the simulator
        current, _ = simulator.apply(current)
        if plan.depth_chart_rows:
            current, _ = positions.apply(current)
            current, _ = pools.apply(current)
            current, _ = lineup.apply(current)
        table = faces.tables(*faces.pool_names(retail_roster()), faces.load_bank())
        current, _ = faces.xbe_apply(current, table)
        self.keep_rows(rows, current, "first-pass owners")
        return self.check_orders(current, plan, orders)

    def preset(self, name, **overrides):
        initial = mod_build.BuildPlan(str(self.private_path("NFL2K5_RETAIL_XISO")),
                                      str(self.folder / "unused.xiso.iso"), console_memory=128)
        return replace(mod_build.apply_preset(initial, name), **overrides)

    def test_standard_recipe_with_realistic(self):
        import json
        from mod_editor.core import modpack_sources
        root = os.environ.get("NFL2K5_B81_STANDARD_SOURCES")
        if not root:
            self.skipTest("private standard source recipe is absent")
        recipe = json.loads((Path(root) / "SOFTDRINK-build-recipe.json").read_bytes())
        plan = modpack_sources.build_plan(recipe, str(self.private_path("NFL2K5_RETAIL_XISO")),
                                          str(self.folder / "unused.xiso.iso"))
        self.assertEqual(plan.sim_qb_injuries, "realistic")
        self.fresh(plan)

    def test_experimental_preset_with_realistic(self):
        plan = self.preset("softdrink_experimental")
        self.assertEqual(plan.sim_qb_injuries, "realistic")
        self.fresh(plan)

    def test_custom_zero_and_one_hundred_percent(self):
        for rate in (0.0, 100.0):
            with self.subTest(custom_rate=rate):
                self.fresh(self.preset("softdrink_experimental", sim_qb_injuries="custom", sim_qb_injury_rate=rate),
                           ORDERS[:2])

    def test_running_back_owner_precedes_the_option_in_build(self):
        # The weekly edit exists only when the running-back cave is installed, so Build must install that owner first.
        source = inspect.getsource(inspect.unwrap(mod_build._build))
        self.assertLess(source.index("_apply_sim_rb_injuries(plan, target"),
                        source.index("_apply_sim_qb_injuries(plan, target"))


class InPlaceUpgrades(_BuildPath):
    def v09_route(self, path, mode, rate):
        """Build's update-v09 route (title guard, modern IR with ownership, cards, simulator, option) in preflight."""
        written = []
        verify = mod_build._verify_sim_qb_injuries

        def keep(plan, module, payload):
            written.append(payload)
            return verify(plan, module, payload)

        plan = mod_build.v09_disc_update(str(path), str(self.folder / "copy.iso"), save_list_type_guard=True,
                                         modern_injured_reserve=True, backfield_cards=True, sim_qb_injuries=mode,
                                         custom_rate=rate)
        release = mod_build._v09_reference(path, mod_build._xbe_bytes(path))
        # The released image hash is pinned by the update tests; here only the executable bytes are under test.
        with patch.object(mod_build, "_verify_sim_qb_injuries", new=keep), \
                patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
            receipt = mod_build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
        self.assertIn("sim_qb_injuries", receipt["v09_update"])
        self.assertFalse((self.folder / "copy.iso").exists())
        return written[-1]

    def test_released_v09_update_route(self):
        path = self.private_path("NFL2K5_V09_XISO")
        source = mod_build._xbe_bytes(path)
        self.assertEqual(_sha(source), V09_XBE)
        self.assertEqual(running_backs.status(source), "applied")
        self.assertIsNone(_bank(source))
        without = self.v09_route(path, "retail", .310)
        self.assertIsNone(_bank(without))
        legacy_blank = space.extend_scaleout(simulator.apply(without)[0], qb.REQUESTS)[0]
        # b81 combined calibration: Realistic and Custom also update v0.9's pass protection (its centre read the retail
        # .rdata float) to this release's centre float; Retail leaves it as v0.9 shipped it.
        self.assertEqual((pressure.status(source), pressure.status(without)), ("legacy", "legacy"))
        # b81 game outcomes: with Simulated season realism the route also installs the simulated-outcomes page (after
        # the simulator, before pass protection: _update_v09_disc's order)
        outcomes = lambda payload: mod_build._sim_outcomes_with_realism(payload)[0]
        blank = space.extend_scaleout(pressure.apply(outcomes(simulator.apply(without)[0]))[0], qb.REQUESTS)[0]
        rows = _rows(source)
        for mode, rate in (("realistic", .310), ("custom", 0.0), ("custom", 100.0)):
            with self.subTest(mode=mode, custom_rate=rate):
                fresh = self.v09_route(path, mode, rate)
                units = qb._setting(mode, rate).rate
                self.keep_rows(rows, fresh, "update-v09")
                self.assertEqual(_bank(fresh), BANK)
                self.assertEqual(_rows(fresh), _rows(blank))
                self.assertEqual(_weekly(fresh), GAME_TAIL if units else _running_back_jump(fresh))
                self.assertEqual(qb.apply(fresh, "retail")[0], blank)
                self.assertEqual(pressure.status(fresh), "applied")
                for reader in (running_backs.status, simulator.status, lineup.read_settings):
                    self.assertEqual(reader(fresh), reader(blank), reader.__module__)
                # The same route as slices 1 and 2 wrote it, upgraded in place (the route updates pass protection
                # before the option); Retail from each.
                older = {revision: _older_install(simulator.apply(without)[0], mode, units, revision)
                         for revision in (1, 2, 3, 4)}
                self.assertNotEqual(older[3], fresh)
                for revision, old in older.items():
                    self.assertEqual(pressure.status(old), "legacy")
                    upgraded, receipt = qb.apply(pressure.apply(outcomes(old))[0], mode, custom_rate=rate)
                    self.assertEqual(receipt.get("upgraded_from"), f"slice{revision}")
                    self.assertEqual(upgraded, fresh)
                    self.assertEqual(qb.apply(old, "retail")[0], legacy_blank)
                    self.assertEqual(qb.read_settings(old).get("revision"), revision)
                settings = qb.read_settings(fresh)
                self.assertEqual((settings["mode"], settings.get("revision"), settings.get("positions")),
                                 (mode, qb.REVISION, units > 0))
                self.record(f"update-v09 {mode} {units}", option=fresh, retail=blank, slice1=older[1], slice2=older[2],
                            slice3=older[3])

    def test_released_v09_late_steps_in_every_order(self):
        path = self.private_path("NFL2K5_V09_XISO")
        source = mod_build._xbe_bytes(path)
        self.assertEqual(_sha(source), V09_XBE)
        current, _ = simulator.apply(source)
        self.keep_rows(_rows(source), current, "source simulator upgrade")
        plan = mod_build.apply_preset(mod_build.BuildPlan(str(path), str(self.folder / "unused.xiso.iso")),
                                      "softdrink_experimental")
        self.check_orders(current, plan, ORDERS[:3])

    def test_studio_made_slice1_standard_executable(self):
        root = os.environ.get("NFL2K5_B81_OWNERSHIP_FIXTURES")
        path = Path(root or "") / "evidence/nov19-qb-product/realistic.xbe"
        if not root or not path.is_file():
            self.skipTest("the Studio-made slice 1 standard executable is absent")
        source = path.read_bytes()
        self.assertEqual(_sha(source), SLICE1_STUDIO_XBE)
        retail, _ = qb.apply(source, "retail")
        self.assertEqual(_sha(retail), SLICE1_STUDIO_RETAIL)
        # The helper above writes exactly what the slice 1 Studio wrote.
        self.assertEqual(_slice1_install(retail, "realistic", 310), source)
        upgraded, receipt = qb.apply(source, "realistic")
        self.assertEqual((_weekly(source), _weekly(upgraded)), (_running_back_jump(source), GAME_TAIL))
        self.assertEqual(receipt.get("upgraded_from"), "slice1")
        settings = qb.read_settings(source)
        self.assertEqual((settings["mode"], settings.get("revision"), settings.get("positions")), ("realistic", 1, False))
        self.assertEqual(qb.read_settings(upgraded).get("revision"), 4)
        self.assertEqual(qb.apply(retail, "realistic")[0], upgraded)
        # Slice 2 and slice 3 installs on the same executable upgrade to the same bytes.
        later = {revision: _older_install(retail, "realistic", 310, revision) for revision in (2, 3)}
        for revision, install in later.items():
            self.assertEqual(qb.read_settings(install).get("revision"), revision)
            self.assertEqual(qb.apply(install, "realistic")[0], upgraded)
            self.assertEqual(qb.apply(install, "retail")[0], retail)
        self.assertEqual(qb.apply(upgraded, "realistic")[0], upgraded)
        self.assertEqual(qb.apply(upgraded, "retail")[0], retail)
        self.assertEqual((_weekly(source), _weekly(upgraded), _weekly(retail)),
                         (_running_back_jump(source), GAME_TAIL, _running_back_jump(retail)))
        self.assertEqual(_rows(upgraded), _rows(source))
        self.assertEqual(_bank(upgraded), BANK)
        self.record("Studio slice 1 9f435b38 upgraded", option=upgraded, retail=retail, slice1=source, slice2=later[2],
                    slice3=later[3])
        for payload in (source, upgraded, retail):
            self.assertEqual(running_backs.status(payload), "applied")
            # b81 fb-targets: season realism from before the fullback target rule reads "legacy"; the QB option's own
            # apply leaves it alone (the Studio's in-place route updates it first, as test_b81_sim_qb_injury_build shows)
            self.assertEqual(simulator.status(payload), "legacy")
            self.assertEqual(lineup.read_settings(payload), lineup.read_settings(retail))


if __name__ == "__main__":
    unittest.main()
