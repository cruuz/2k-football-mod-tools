"""b81 qb34: the quarterback room through the Studio's real first pass, real installers and the Build page.

T11: the room's pages sit at 0x1529000 and no installed row moves, through the Build tab's own first-pass expression
(captured from mod_build._build) and the real late installers: the on-disk standard recipe, Experimental and Basic
(with the room's dependencies), and in place on the released v0.9 executable and the reviewed v0.10 test executable.
Each case runs the room last (the Studio order), first, and before the cards, with and without the franchise
ownership page, always with the slice 1 quarterback bank. T12: in each case Realistic then Retail is the image before
the room plus the empty reservation, and every neighbouring owner reads the same status before, after and after Retail.
Studio rule (DESIGN_CHANGES C1, lead 2026-11-20): a recipe without the key follows sim_qb_injuries, and a followed
Realistic is installed only where its needs are met (the plan for a full build, the source executable in place),
otherwise it is left out with one note; an explicit key wins and an explicit Realistic without its needs is refused; the
Experimental preset names it; the Build page's quarterback injury control sets both. Private fixtures (b81 env.sh) gate the
executable cases; without them those skip.
"""
from __future__ import annotations

import ast
from dataclasses import replace
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from mod_editor.core import mod_build, modpack_sources  # noqa: E402
from mod_editor.core import nfl2k5_sim_qb_injuries as _sim_qb_injuries  # noqa: E402  b81 merge
from mod_editor.core import nfl2k5_build_settings as settings  # noqa: E402


def room_module():
    from mod_editor.core import nfl2k5_qb_room as room
    return room


def _room():
    from mod_editor.core import nfl2k5_qb_room as room
    return room
import tests.mod_editor.test_b780_int_first_pass as first_pass  # noqa: E402

ROOM_ROW = (0x1529000, 0x3000, 0x1000)
# Neighbours whose status() must not change when the room is installed or removed (rev-qb neighbours_status).
EXTRA_NEIGHBOURS = ("nfl2k5_sim_qb_injuries", "nfl2k5_sim_rb_injuries", "nfl2k5_sim_cb_tackles", "nfl2k5_senior_bowl",
                    "nfl2k5_k128", "nfl2k5_backfield_cards", "nfl2k5_offset_toss", "nfl2k5_injured_reserve",
                    "nfl2k5_franchise_ownership", "nfl2k5_depth_locks", "nfl2k5_lineup_roles", "nfl2k5_sim_realism")


def _handover(bits):
    """Run piece 3's rule C1a as it will be once ``bits`` are handed over (REALISTIC_STAGES is 0 at the floor handover)."""
    from unittest.mock import patch
    from mod_editor.core import nfl2k5_qb_room as room
    return patch.object(room, "REALISTIC_STAGES", bits)


def _neighbour_status(payload):
    from mod_editor.core import nfl2k5_qb_room as room
    names = [n for n, _l, _w in mod_build._LATE_OWNER_OPTIONS if n != room.OWNER] + list(EXTRA_NEIGHBOURS)
    out = {}
    for name in dict.fromkeys(names):
        module = importlib.import_module("mod_editor.core." + name)
        try:
            out[name] = module.status(payload)
        except Exception as exc:  # noqa: BLE001 - the reading itself is what is compared
            out[name] = "raises " + type(exc).__name__
    return out


class RoomInstallationOrderTests(first_pass.QuarterbackInstallationOrderTests):
    """The slice 1 installation-order harness with the room added in three positions (T11, T12)."""

    with_ir = True

    def both_orders(self, payload, plan):
        from mod_editor.core import nfl2k5_backfield_cards as cards, nfl2k5_depth_locks as locks
        from mod_editor.core import nfl2k5_offset_toss as toss, nfl2k5_rookie_faces as faces
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_xbe_space as space

        from mod_editor.core import nfl2k5_franchise_economy as economy, nfl2k5_practice_squad as squad
        level, stages, _note = mod_build._qb_room_plan(plan, payload)
        # Coordinator's rule: injuries above zero always carry the floor; Custom 0 does not.
        floor = room.FLOOR_STUDIO_STAGES
        self.assertEqual(stages & (floor | room.STAGE_OVER_CAP), floor if mod_build._qb_injuries_above_zero(plan) else 0)
        studio = level == "realistic"
        if not studio:
            # No Studio stage set on this path (Custom 0 while no piece 3 bit ships): place a D1 page through the
            # calibration path; placement and order do not depend on the bits.
            stages = room._code().STAGE_D1
        # In-place owners the Studio installs long before these late steps (the floor needs the economy and squad).
        payload, _ = locks.apply(payload)
        if stages & floor:
            payload, _ = squad.apply(payload)
            payload, _ = economy.apply(payload)

        def studio_ir(current):
            target = self.folder / "working.xbe"
            target.write_bytes(current)
            mod_build._apply_injured_reserve(plan, target, {"steps": [], "result": {}}, lambda *_: None)
            return target.read_bytes()

        def studio_room(current):
            if not studio:
                return room.install_stages(current, stages)[0]
            # The Build step itself, on a file, as the full build calls it after the quarterback injury step.
            target = self.folder / "room.xbe"
            target.write_bytes(current)
            receipt = {"steps": [], "result": {}}
            mod_build._apply_qb_room(plan, target, receipt, lambda *_: None)
            self.assertEqual(receipt["result"]["qb_room"], "realistic")
            return target.read_bytes()

        steps = {"IR": studio_ir, "hair": lambda x: faces.apply_hair(x)[0], "toss": lambda x: toss.apply(x)[0],
                 "cards": lambda x: cards.apply(x)[0],
                 "QB": lambda x: qb.apply(x, plan.sim_qb_injuries, custom_rate=plan.sim_qb_injury_rate)[0],
                 "ROOM": studio_room}
        # The floor needs modern IR and the ownership page first, so with injuries above zero the earliest place for the
        # room is right after IR; without the floor (Custom 0) it also goes first of all.
        first = ("IR", "ROOM") if stages & floor else ("ROOM", "IR")
        orders = (("IR", "hair", "toss", "cards", "QB", "ROOM"), (*first, "hair", "toss", "cards", "QB"),
                  ("IR", "hair", "toss", "ROOM", "cards", "QB"))
        if not self.with_ir:
            orders = tuple(tuple(s for s in order if s != "IR") for order in orders)
        initial = space.layout(payload)["allocations"]
        finals = []
        for order in orders:
            with self.subTest(install_order=order, ownership=self.with_ir):
                current, rows = payload, initial
                for name in order:
                    before = current
                    current = steps[name](current)
                    rows = self.preserved(rows, current, name)
                    if name == "ROOM":
                        row, = (r for r in rows if r["owner"] == room.OWNER)
                        self.assertEqual((row["va"], row["size"], row["align"]), ROOM_ROW)
                        reserved = (before if room.read_settings(before).get("reserved")
                                    else space.extend_scaleout(before, room.REQUESTS)[0])
                        # The trades review's F1: the Studio adds 4b (bit 16) where its needs are on at this step;
                        # Retail then leaves the trades page's reservation too.
                        trades_on = studio and stages & room.E_BITS == room.E_BITS and room.trade_needs_met(before)
                        installed = stages | (room.STUDIO_TRADE_BITS if trades_on else 0)
                        if trades_on:
                            from mod_editor.core import nfl2k5_qb_trades as trades
                            reserved = space.extend_scaleout(reserved, trades.REQUESTS)[0]
                        self.assertEqual(room.apply(current, "retail")[0], reserved, "T12 at the room step")
                        if order[-1] == "ROOM":
                            neighbours = _neighbour_status(before)
                            self.assertEqual(_neighbour_status(current), neighbours)
                    if name == "QB":
                        bank, = (r for r in rows if r["owner"] == qb.OWNER)
                        self.assertEqual((bank["va"], bank["size"]), (0x1524000, 16384))
                ownership = [r for r in rows if r["owner"] == "nfl2k5_franchise_ownership"]
                self.assertEqual(bool(ownership), self.with_ir or any(
                    r["owner"] == "nfl2k5_franchise_ownership" for r in initial))
                if ownership:
                    self.assertEqual((ownership[0]["va"], ownership[0]["size"]), (0x1528000, 4096))
                self.assertEqual(room.status(current), "applied")
                self.assertEqual(room.read_settings(current)["stages"], installed)
                self.assertEqual(qb.read_settings(current)["mode"], plan.sim_qb_injuries)
                self.assertEqual((faces.hair_status(current), toss.status(current), cards.status(current)),
                                 ("applied", "applied", "applied"))
                retail, _ = room.apply(current, "retail")
                self.assertEqual(room.read_settings(retail)["reserved"], True)
                again = (room.apply(retail, "realistic", stages=installed) if studio
                         else room.install_stages(retail, stages))[0]
                self.assertEqual(again, current)
                if order[-1] == "ROOM":
                    self.assertEqual(_neighbour_status(retail), _neighbour_status(current))
                finals.append((rows, current))
        self.assertEqual(len(finals), 3)
        for rows, current in finals[1:]:
            self.assertEqual(rows, finals[0][0], "the layout depends on install order")
            self.assertEqual(current, finals[0][1], "the bytes depend on install order")

    def test_basic_custom_zero_with_dependencies_and_late_installation_orders(self):
        self.fresh(replace(self.preset("softdrink_basic"), k128_memory=True, sim_realism=True, sim_qb_injuries="custom",
                           sim_qb_injury_rate=0.0, depth_locks=True, depth_chart_rows=True))


class RoomWithoutOwnershipTests(RoomInstallationOrderTests):
    """The same cases with no franchise ownership page anywhere (no IR guard, no modern IR, no IR step)."""

    with_ir = False

    def preset(self, name):
        return replace(super().preset(name), injured_reserve_guard=False, modern_injured_reserve=False)

    def both_orders(self, payload, plan):
        # Without the ownership page there is no floor (it needs modern IR and that page), so these cases are Custom 0:
        # piece 3 only, placed before every other owner, IR included.
        super().both_orders(payload, replace(plan, sim_qb_injuries="custom", sim_qb_injury_rate=0.0,
                                             injured_reserve_guard=False, modern_injured_reserve=False))

    def fresh(self, plan):
        # The base fresh() asserts the ownership page; this copy asserts its absence and is otherwise the same.
        import hashlib
        from mod_editor.core import nfl2k5_k128 as k128, nfl2k5_lineup_roles as lineup
        from mod_editor.core import nfl2k5_modern_positions as positions, nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_rookie_faces as faces, nfl2k5_sim_realism as sim, nfl2k5_xbe_space as space
        from tests.nfl2k5_supersim_draft_fixture import RETAIL_SHA256, retail_roster

        # Custom 0 from the start: injuries above zero would pull modern IR and its ownership page back in (C7).
        plan = replace(plan, injured_reserve_guard=False, modern_injured_reserve=False, sim_qb_injuries="custom",
                       sim_qb_injury_rate=0.0)
        retail, requests, plan = self.studio_first_pass(plan)
        self.assertEqual(hashlib.sha256(retail).hexdigest(), RETAIL_SHA256)
        self.assertIn(space.QB_INJURY_REQUEST, requests)
        self.assertFalse(any(r[0] == "nfl2k5_franchise_ownership" for r in requests))
        if any(r[0] == "nfl2k5_qb_room" for r in requests):  # Custom 0 reserves the room only for piece 3 (C1a)
            self.assertTrue(mod_build._piece3_bits())
        current, _ = space.apply(retail, requests, scaleout=True)
        rows = space.layout(current)["allocations"]
        current, _ = k128.apply(current, require=True, early=plan.k128_early, roster_heap=plan.k128_roster_heap)
        current, _ = sim.apply(current)
        if plan.depth_chart_rows:
            current, _ = positions.apply(current)
            current, _ = pools.apply(current)
            current, _ = lineup.apply(current)
        table = faces.tables(*faces.pool_names(retail_roster()), faces.load_bank())
        current, _ = faces.xbe_apply(current, table)
        self.preserved(rows, current, "base simulator, selected lineup roles and rookie faces")
        self.both_orders(current, plan)

    def test_actual_standard_recipe_first_pass_and_late_installation_orders(self):
        self.skipTest("the standard recipe always reserves the ownership page; covered with ownership")

    def test_released_v09_standard_upgrades_in_either_order(self):
        self.upgrade("NFL2K5_V09_XISO", "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866")

    def test_reviewed_v10_standard_upgrades_in_either_order(self):
        self.upgrade("NFL2K5_B81_REVIEWED_TEST_DISC", "98dd732945fb665a8d7fe771650d61c1098015cda4917ac83037059db477008e")


class StudioRuleTests(unittest.TestCase):
    """DESIGN_CHANGES C1: explicit value wins; otherwise the room follows the quarterback injury option."""

    def test_the_rule(self):
        for mode, expected in ((None, None), ("retail", "retail"), ("realistic", "realistic"), ("custom", "realistic")):
            with self.subTest(sim_qb_injuries=mode):
                self.assertEqual(settings.qb_room_level(None, mode), expected)
                for explicit in ("retail", "realistic"):
                    self.assertEqual(settings.qb_room_level(explicit, mode), explicit)
        for bad in ("custom", "on", True, 1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                settings.qb_room_level(bad, "realistic")

    def test_recipe_without_the_key_follows_and_an_explicit_key_wins(self):
        base = {"preset": "softdrink_experimental", "overrides": {"sim_qb_injuries": "realistic"}}
        self.assertEqual(mod_build._qb_room_level(modpack_sources.build_plan(base)), "realistic")
        for mode, expected in (("retail", "retail"), ("custom", "realistic")):
            recipe = {"preset": "softdrink_experimental", "overrides": {"sim_qb_injuries": mode}}
            with self.subTest(sim_qb_injuries=mode):
                plan = modpack_sources.build_plan(recipe)
                self.assertIsNone(plan.qb_room)  # the preset's own value does not override a recipe without the key
                self.assertEqual(mod_build._qb_room_level(plan), expected)
                self.assertNotIn("qb_room", plan.to_recipe())
        for explicit in ("retail", "realistic"):
            recipe = {"preset": "softdrink_experimental",
                      "overrides": {"sim_qb_injuries": "realistic", "qb_room": explicit}}
            with self.subTest(explicit=explicit):
                plan = modpack_sources.build_plan(recipe)
                # The key names piece 3's rules; the floor follows the injuries (coordinator's rule, 2026-11-20).
                self.assertEqual(mod_build._qb_room_resolution(plan)[0], explicit)
                piece3 = mod_build._piece3_bits() if explicit == "realistic" else 0
                e_bits = room_module().REALISTIC_STAGES & room_module().E_BITS if piece3 else 0  # C21: E1/E2 with both
                self.assertEqual(mod_build._qb_room_plan(plan)[:2], ("realistic", 64 | piece3 | e_bits))
                self.assertEqual(plan.to_recipe()["qb_room"], explicit)
        old = {"preset": "softdrink_experimental", "overrides": {}}
        self.assertIsNone(mod_build._qb_room_level(modpack_sources.build_plan(old)))
        with self.assertRaises(ValueError):
            modpack_sources.build_plan({"preset": "softdrink_basic", "overrides": {"qb_room": "custom"}})

    def test_a_pack_records_the_room_only_where_the_rule_would_not_reproduce_the_disc(self):
        with _handover(1):
            self._pack_cases((("softdrink_basic", "retail", None), ("softdrink_experimental", "applied", None),
                              ("softdrink_experimental", "retail", "retail"), ("softdrink_basic", "applied", "realistic")))
        # Floor alone: no piece 3 bit ships, so a pack never records the key.
        with _handover(0):
            self._pack_cases((("softdrink_basic", "retail", None), ("softdrink_experimental", "retail", None)))

    def _pack_cases(self, cases):
        from unittest.mock import MagicMock, patch
        from mod_editor.core import nfl2k5_backfield_cards as cards
        qb_state = {"status": "applied", "mode": "realistic", "custom_rate": 0.31}
        for preset, room_status, recorded in cases:
            with self.subTest(preset=preset, room=room_status), tempfile.TemporaryDirectory() as t:
                root = Path(t)
                (root / "league.json").write_text('{"edits":[]}', encoding="utf-8")
                recipe = root / "frozen.json"
                recipe.write_text(json.dumps({"preset": preset, "overrides": {},
                                              "inputs": {"teams_2026": {"project": str(root / "league.json")}}}))
                qb, room, scoring = MagicMock(), MagicMock(), MagicMock()
                qb.read_settings.return_value = qb_state
                # b81 integration (scoring merged): a pack also reads the disc's simulated scoring sites
                scoring.installed.return_value = ("retail", None)
                room.read_settings.return_value = {"status": room_status, "stages": 1 if room_status == "applied" else 0}
                from mod_editor.core import nfl2k5_qb_room as real_room
                room.PIECE3_BITS, room.REALISTIC_STAGES = real_room.PIECE3_BITS, real_room.REALISTIC_STAGES
                modules = {"nfl2k5_sim_qb_injuries": qb, "nfl2k5_qb_room": room, "nfl2k5_sim_scoring": scoring}
                with patch.object(mod_build, "_xbe_bytes", return_value=b"standard executable"), \
                        patch.object(cards, "status", return_value="retail"), \
                        patch.object(mod_build, "_core_module", side_effect=lambda name: modules.get(name)):
                    portable, _assets = modpack_sources.prepare(recipe, root / "work", patched_image=root / "copy.iso")
                self.assertEqual(portable["overrides"].get("qb_room"), recorded)

    def test_the_standard_source_recipes_on_disk_resolve_to_realistic(self):
        directory = os.environ.get("NFL2K5_B81_STANDARD_SOURCES")
        if not directory:
            self.skipTest("private SOFTDRINK standard source documents are absent")
        for name in ("SOFTDRINK-build-recipe.json", "recipe.json", "assets/documents/frozen-recipe.json"):
            with self.subTest(document=name):
                recipe = json.loads((Path(directory) / name).read_text(encoding="utf-8"))
                plan = modpack_sources.build_plan(recipe)
                self.assertEqual(mod_build._qb_room_level(plan), "realistic")
                self.assertEqual(mod_build.validate_plan(plan), [])

    def test_presets(self):
        for name in mod_build.PRESETS:
            for memory in (64, 128):
                plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t", console_memory=memory), name)
                expected = "realistic" if name == "softdrink_experimental" and memory == 128 else None
                with self.subTest(preset=name, memory=memory):
                    # No preset names the room (C1): it follows the injury option, Realistic where its needs are met.
                    self.assertIsNone(plan.qb_room)
                    self.assertEqual(mod_build._qb_room_level(plan), expected)
                    if memory == 128:
                        self.assertEqual(mod_build.validate_plan(plan), [])

    def test_basic_with_realistic_quarterback_injuries_leaves_the_room_out_with_a_note(self):
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        plan = replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries="realistic")
        with _handover(0):
            self.assertEqual(mod_build._qb_room_resolution(plan), ("realistic", None))  # floor alone: nothing left out
        with _handover(1):
            self._basic_left_out()

    def _basic_left_out(self):
        from mod_editor.core import nfl2k5_memory_budget as budget
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        for mode in ("realistic", "custom"):
            plan = replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries=mode)
            with self.subTest(mode=mode):
                self.assertEqual(mod_build.validate_plan(plan), [])
                level, note = mod_build._qb_room_resolution(plan)
                self.assertIsNone(level)
                self.assertIn("were not added", note)
                self.assertNotIn("\u2014", note)
                self.assertIn("qb_room", budget.owners(budget.options(plan), 128))  # the floor
                self.assertEqual(mod_build._qb_room_plan(plan)[:2], ("realistic", 64))
                ready = replace(plan, depth_locks=True, depth_chart_rows=True)
                self.assertEqual(mod_build._qb_room_resolution(ready), ("realistic", None))
                self.assertIn("qb_room", budget.owners(budget.options(ready), 128))

    def test_the_build_step_writes_nothing_and_says_so_when_the_room_is_left_out(self):
        retail = Path(os.environ.get("NFL2K5_RETAIL_XBE", ""))
        if not retail.is_file():
            self.skipTest("the private retail default.xbe is absent")
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        # Custom 0: no floor (coordinator's rule), and piece 3's needs are missing, so nothing is installed.
        plan = replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries="custom", sim_qb_injury_rate=0.0)
        for bits, notes in ((0, 0), (1, 1)):  # the floor handover, then as it will be with D1 handed over
            with self.subTest(piece3=bits), _handover(bits), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "default.xbe"
                target.write_bytes(retail.read_bytes())
                receipt = {"steps": [], "result": {}}
                mod_build._apply_qb_room(plan, target, receipt, lambda *_: None)
                self.assertEqual(target.read_bytes(), retail.read_bytes())
                self.assertEqual(receipt["result"]["qb_room"], "retail")
                self.assertEqual(len(receipt.get("user_notes", [])), notes)
                if notes:
                    self.assertIn("who-starts quarterback rules", receipt["user_notes"][0])

    def test_an_explicit_realistic_on_basic_is_refused(self):
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        plan = replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries="realistic", qb_room="realistic")
        with _handover(0):
            self.assertEqual(mod_build.validate_plan(plan), [])  # floor alone: no piece 3 rule to need anything
        with _handover(1):
            self._explicit_refused(plan)

    def _explicit_refused(self, plan):
        message, = mod_build.validate_plan(plan)
        self.assertIn("who-starts quarterback rules need", message)
        self.assertEqual(mod_build.validate_plan(replace(plan, qb_room="retail")), [])

    def test_validation_refuses_realistic_without_the_rooms_needs_in_plain_words(self):
        with _handover(1):
            self._validation_refuses()

    def _validation_refuses(self):
        plan = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_experimental")
        named = replace(plan, sim_qb_injuries=None, qb_room="realistic")  # the room alone, so its own message shows
        for field in ("depth_locks", "depth_chart_rows", "k128_memory"):
            with self.subTest(missing=field):
                message, = mod_build.validate_plan(replace(named, **{field: False}))
                self.assertIn("who-starts quarterback rules", message)
                if field != "k128_memory":
                    followed = replace(plan, **{field: False}, sim_realism=True, qb_room=None)
                    self.assertEqual(mod_build.validate_plan(followed), [])
                    self.assertIsNone(mod_build._qb_room_resolution(followed)[0])  # piece 3 left out
                    self.assertEqual(mod_build._qb_room_plan(followed)[:2], ("realistic", 64))  # the floor stays
                self.assertNotIn("—", message)
        self.assertEqual(mod_build.validate_plan(replace(plan, depth_locks=False, qb_room="retail")), [])
        self.assertTrue(mod_build.validate_plan(replace(plan, qb_room="custom")))

    def test_edits_and_the_v09_update_carry_the_room(self):
        edit = mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic")
        self.assertEqual((edit.qb_room, mod_build._qb_room_level(edit)), (None, "realistic"))
        self.assertTrue(mod_build._only_sim_qb_changes(edit))
        self.assertEqual(mod_build.validate_plan(edit), [])
        named = mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic", qb_room="retail")
        self.assertEqual(mod_build._qb_room_resolution(named)[0], "retail")
        self.assertEqual(mod_build._qb_room_plan(named)[:2], ("realistic", 64))  # the floor rides with the injuries
        self.assertTrue(mod_build._only_sim_qb_changes(named))
        update = mod_build.v09_disc_update("s.iso", "t.iso", sim_qb_injuries="custom")
        self.assertEqual(mod_build._qb_room_level(update), "realistic")
        self.assertEqual(mod_build.validate_plan(update), [])
        # The rules named alone: piece 3's handed-over bits (none at the floor handover, so nothing to install).
        self.assertEqual(mod_build._qb_room_level(mod_build.v09_disc_update("s.iso", "t.iso", qb_room="realistic")),
                         "realistic" if mod_build._piece3_bits() else "retail")
        with self.assertRaises(ValueError):
            mod_build.v09_disc_update("s.iso", "t.iso", sim_qb_injuries="realistic", qb_room="custom")

    def test_settings_round_trip_and_inventory(self):
        self.assertIn("qb_room", settings.FEATURE_KEYS)
        plan = mod_build.BuildPlan("s", "t", sim_qb_injuries="realistic", k128_memory=True, sim_realism=True,
                                   qb_room="retail")
        self.assertEqual(settings.to_plan(settings.from_plan(plan), "s", "t").qb_room, "retail")
        self.assertIs(mod_build.availability()["qb_room"], True)
        self.assertIn("nfl2k5_qb_room", [row[0] for row in mod_build._LATE_OWNER_OPTIONS])
        self.assertTrue(mod_build.BuildPlan("s", "t", qb_room="retail").wants_xbe_patch())
        from mod_editor.core import build_steps
        self.assertIn("qb_room", build_steps.STEP_LABELS if hasattr(build_steps, "STEP_LABELS") else
                      next(v for v in vars(build_steps).values() if isinstance(v, dict) and "sim_qb_injuries" in v))

    def test_the_build_calls_the_room_right_after_the_quarterback_injury_step(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for function in ("_build", "_update_v09_disc", "_edit_installed_sim_qb"):
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
            calls = [c.func.id for c in ast.walk(node) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
            with self.subTest(function=function):
                self.assertIn("_apply_qb_room", calls)
                qb_at = max(c.lineno for c in ast.walk(node) if isinstance(c, ast.Call)
                            and isinstance(c.func, ast.Name) and c.func.id == "_apply_sim_qb_injuries")
                room_at = min(c.lineno for c in ast.walk(node) if isinstance(c, ast.Call)
                              and isinstance(c.func, ast.Name) and c.func.id == "_apply_qb_room")
                self.assertGreater(room_at, qb_at)
                between = [c for c in ast.walk(node) if isinstance(c, ast.Call) and qb_at < c.lineno < room_at]
                # b81 integration (scoring merged): the v0.9 update writes the CPU kick aim after the quarterback step, in
                # the order of its expected executable; it touches only the kicking sites (the room and the aim commute
                # byte for byte), so it is the one call allowed in between.
                allowed = {"_apply_cpu_kick_aim_in_place"} if function == "_update_v09_disc" else set()
                self.assertEqual([ast.unparse(c.func) for c in between
                                  if not (isinstance(c.func, ast.Name) and c.func.id in allowed)], [])


class FloorRuleTests(unittest.TestCase):
    """Coordinator's product rule (2026-11-20): quarterback injuries above zero are never installed without the floor.
    Each Studio path either completes the floor's needs or refuses in plain words; the installed stage set is pinned."""

    FLOOR = 64  # bit 128 (over the cap) is retired: floor review F1(b)

    @property
    def P3(self):
        from mod_editor.core import nfl2k5_qb_room as room
        return room.REALISTIC_STAGES & room.PIECE3_BITS  # 0 at the floor handover

    @property
    def E(self):
        """E1/E2 (C21 hand-over): installed only where the floor and piece 3 are both installed."""
        from mod_editor.core import nfl2k5_qb_room as room
        return room.REALISTIC_STAGES & room.E_BITS

    def plan_set(self, plan, payload=None):
        return mod_build._qb_room_plan(plan, payload)[:2]

    def test_full_builds_pull_in_the_floors_needs(self):
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        experimental = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_experimental")
        cases = (("Basic Realistic", replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries="realistic"),
                  ["modern injured reserve", "the franchise economy", "reserve save compatibility (the practice squad)"],
                  ("realistic", self.FLOOR)),
                 ("Basic Custom 0.5", replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries="custom",
                                              sim_qb_injury_rate=0.5),
                  ["modern injured reserve", "the franchise economy", "reserve save compatibility (the practice squad)"],
                  ("realistic", self.FLOOR)),
                 # The Experimental preset has the 2026 season, so with the floor's needs 4b's are met too: 383.
                 ("Experimental Realistic", experimental, ["the franchise economy"],
                  ("realistic", self.FLOOR | self.P3 | self.E | 16)),
                 ("Experimental, rules named Retail", replace(experimental, qb_room="retail"), ["the franchise economy"],
                  ("realistic", self.FLOOR)))
        for name, plan, added, expected in cases:
            with self.subTest(case=name):
                self.assertEqual(mod_build.validate_plan(plan), [])
                completed, note = mod_build._with_qb_floor_needs(plan)
                self.assertTrue(completed.modern_injured_reserve and completed.franchise_economy and completed.practice_squad)
                for label in added:
                    self.assertIn(label, note)
                self.assertIn("so a club is never left without a quarterback", note)
                self.assertNotIn("\u2014", note)
                self.assertEqual(self.plan_set(completed), expected)
                from mod_editor.core import nfl2k5_qb_room as room
                self.assertEqual(room.stage_names(expected[1])[-1:], ["floor"])  # no over-cap rung (floor review F1(b))
                self.assertEqual(bool(expected[1] & 16), bool(completed.season_2026 and expected[1] & self.E))
                self.assertEqual(expected[1] & room.PIECE3_BITS, self.P3 if name.startswith("Experimental R") else 0)

    def test_no_floor_without_injuries(self):
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        experimental = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_experimental")
        cases = (("Basic Custom 0", replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries="custom",
                                            sim_qb_injury_rate=0.0), ("retail", 0)),
                 ("Experimental Custom 0", replace(experimental, sim_qb_injuries="custom", sim_qb_injury_rate=0.0),
                  ("realistic", self.P3) if self.P3 else ("retail", 0)),
                 ("Experimental Retail", replace(experimental, sim_qb_injuries="retail", qb_room=None), ("retail", 0)),
                 ("Basic, keep the source", basic, (None, 0)))
        for name, plan, expected in cases:
            with self.subTest(case=name):
                completed, note = mod_build._with_qb_floor_needs(plan)
                self.assertIsNone(note)
                self.assertEqual(completed, plan)
                self.assertEqual(self.plan_set(plan), expected)

    def test_a_need_the_studio_cannot_add_is_refused_in_plain_words(self):
        from unittest.mock import patch
        basic = mod_build.apply_preset(mod_build.BuildPlan("s", "t"), "softdrink_basic")
        plan = replace(basic, k128_memory=True, sim_realism=True, sim_qb_injuries="realistic")
        offered = dict(mod_build.availability(), franchise_economy=False)
        with patch.object(mod_build, "availability", return_value=offered):
            message, = mod_build.validate_plan(plan)
            self.assertIn("the franchise economy", message)
            self.assertIn("Choose Retail or Custom 0 percent", message)
            self.assertEqual(mod_build.validate_plan(replace(plan, sim_qb_injuries="custom", sim_qb_injury_rate=0.0)), [])
        self.assertIn("128 MB", mod_build.validate_plan(replace(plan, console_memory=64))[0])

    def _private(self):
        disc = Path(os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC", ""))
        if not disc.is_file():
            self.skipTest("the private reviewed test disc is absent")
        return mod_build._xbe_bytes(disc)

    def _edit(self, plan, original):
        receipt = {"steps": [], "result": {}}
        self.assertTrue(mod_build._edit_installed_sim_qb(plan, Path("source.iso"), Path("copy.iso"), original, receipt,
                                                         lambda *_: None, preflight=True, consume=False, reference=None))
        return receipt

    def test_an_in_place_edit_brings_slice_1_up_to_the_floor(self):
        import hashlib
        from mod_editor.core import nfl2k5_injured_reserve as ir, nfl2k5_qb_room as room
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_cpu_kick_aim as aim, nfl2k5_pass_protection as pressure
        source = self._private()
        slice1, _ = qb.apply(source, "realistic")  # 9f435b38: slice 1 without the floor (an earlier private test disc)
        # b81 integration (scoring merged): the in-place edit also writes the CPU kick aim, as a full build would; and
        # (combined levers) it updates the disc's legacy pass protection to this release's centre float first
        # b81 fb-targets: and the disc's season realism from before the fullback target rule, beneath the QB option
        from mod_editor.core import nfl2k5_sim_realism as realism
        aimed, _ = aim.apply(qb.apply(pressure.apply(realism.apply(source)[0])[0], "realistic")[0])
        # b81 history-pool: and this release's career history pool (the disc carries the v0.9 revision), after
        # b81 rookie-faces: rookie faces' current revision (a GEN1 disc is upgraded in place; others are unchanged)
        aimed = mod_build._history_pool_upgrade(mod_build._rookie_faces_upgrade(aimed)[0])[0]
        aimed = mod_build._overtime_crash_fix_upgrade(aimed)[0]   # b81 ot-crash review D3: and the overtime crash fix
        # b81 integration (practice squad merge): and upgrades the disc's revision 7 economy before the floor
        from mod_editor.core import nfl2k5_franchise_economy as economy
        prepared = ir.apply(economy.apply(aimed)[0], "modern", standard_guard=True)[0]
        # The trades review's F1: this disc carries 4b's needs once modern IR is in, so the Studio's set is 383.
        stages = self.FLOOR | self.P3 | self.E | (16 if room.trade_needs_met(prepared) else 0)
        self.assertEqual(stages, room.realistic_stages(prepared))
        expected, _ = room.apply(prepared, "realistic", stages=stages)
        for name, original in (("98dd7329", source), ("9f435b38", slice1)):
            with self.subTest(source=name):
                receipt = self._edit(mod_build.sim_qb_disc_edit("s.iso", "t.iso", "realistic"), original)
                update = receipt["qb_room_source_update"]
                self.assertEqual((update["level"], update["stages"]), ("realistic", stages))
                self.assertEqual(update["result_sha256"], hashlib.sha256(expected).hexdigest())
                self.assertIn("added modern injured reserve", update["added"][0])
                self.assertIn("updated the franchise economy", update["added"][1])  # practice squad merge: revision 7 -> 8
                self.assertIn(update["added"][0], receipt["user_notes"])
                self.assertEqual(update["settings"]["stage_names"], room.stage_names(stages))
                self.assertEqual(update["settings"]["stage_names"][-1:], ["floor"])
                self.assertEqual(receipt["sim_qb_source_update"]["result_sha256"], hashlib.sha256(aimed).hexdigest())
        receipt = self._edit(mod_build.sim_qb_disc_edit("s.iso", "t.iso", "custom", custom_rate=0.0), source)
        self.assertEqual(receipt["qb_room_source_update"]["stages"], self.P3)  # Custom 0: piece 3 only, no floor or IR

    def test_inspect_reports_a_build_with_injuries_but_no_floor(self):
        from mod_editor.core import nfl2k5_injured_reserve as ir, nfl2k5_qb_room as room
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_franchise_economy as economy
        slice1, _ = qb.apply(self._private(), "realistic")
        # b81 integration (practice squad merge): the floor needs the current economy (revision 8) under it
        floor, _ = room.apply(ir.apply(economy.apply(slice1)[0], "modern", standard_guard=True)[0], "realistic",
                              stages=self.FLOOR | 1)
        with tempfile.TemporaryDirectory() as directory:
            for name, payload, expected in (("9f435b38", slice1, "missing"), ("floor", floor, "applied")):
                with self.subTest(executable=name):
                    path = Path(directory) / f"{name}.xbe"
                    path.write_bytes(payload)
                    self.assertEqual(mod_build.inspect(path)["qb_floor"], expected)

    def test_an_in_place_edit_without_the_economy_is_refused(self):
        from mod_editor.core import nfl2k5_k128 as k128, nfl2k5_sim_realism as sim, nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_xbe_space as space
        retail = Path(os.environ.get("NFL2K5_RETAIL_XBE", ""))
        if not retail.is_file():
            self.skipTest("the private retail default.xbe is absent")
        image, _ = space.apply(retail.read_bytes(), k128.REQUESTS + sim.REQUESTS + qb.REQUESTS, scaleout=True)
        image, _ = k128.apply(image, require=True)
        image, _ = sim.apply(image)
        for mode, rate in (("realistic", 0.31), ("custom", 0.2)):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "Choose Retail or Custom 0 percent"):
                self._edit(mod_build.sim_qb_disc_edit("s.iso", "t.iso", mode, custom_rate=rate), image)
        receipt = self._edit(mod_build.sim_qb_disc_edit("s.iso", "t.iso", "custom", custom_rate=0.0), image)
        self.assertEqual(receipt["qb_room_source_update"]["level"], "retail")

    def test_the_v09_update_ticks_modern_ir_and_installs_the_floor(self):
        from mod_editor.core import nfl2k5_injured_reserve as ir, nfl2k5_sim_realism as sim
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        for mode, rate, ticked in (("realistic", 0.31, True), ("custom", 0.5, True), ("custom", 0.0, False),
                                   ("retail", 0.31, False)):
            with self.subTest(mode=mode, rate=rate):
                plan = mod_build.v09_disc_update("s.iso", "t.iso", sim_qb_injuries=mode, custom_rate=rate)
                self.assertIs(plan.modern_injured_reserve, ticked)
        disc = Path(os.environ.get("NFL2K5_V09_XISO", ""))
        if not disc.is_file():
            self.skipTest("the released v0.9 disc is absent")
        v09 = mod_build._xbe_bytes(disc)
        expected = qb.apply(sim.apply(ir.apply(v09, "modern", standard_guard=True)[0])[0], "realistic")[0]
        plan = mod_build.v09_disc_update("s.iso", "t.iso", sim_qb_injuries="realistic")
        self.assertEqual(self.plan_set(plan, expected), ("realistic", self.FLOOR | self.P3 | self.E))


class InPlacePreflightTests(unittest.TestCase):
    """The real in-place Studio path (sim_qb_disc_edit, preflight only: no disc is written) on the helmet test disc."""

    def test_the_edit_installs_the_room_with_the_quarterback_option(self):
        import hashlib
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        disc = Path(os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC", ""))
        if not disc.is_file():
            self.skipTest("the private reviewed test disc is absent")
        source = mod_build._xbe_bytes(disc)
        from mod_editor.core import nfl2k5_cpu_kick_aim as aim, nfl2k5_injured_reserve as ir
        from mod_editor.core import nfl2k5_pass_protection as pressure
        # The edit updates the legacy pass protection (combined levers), applies the option and writes the CPU kick aim
        from mod_editor.core import nfl2k5_sim_realism as realism   # b81 fb-targets: the pre-rule season realism first
        slice1, _ = qb.apply(pressure.apply(realism.apply(source)[0])[0], "realistic")
        slice1, _ = aim.apply(slice1)  # b81 integration (scoring merged): the edit writes the CPU kick aim too
        slice1 = mod_build._rookie_faces_upgrade(slice1)[0]   # b81 rookie-faces: the GEN1 disc's rookie faces upgraded
        slice1 = mod_build._history_pool_upgrade(slice1)[0]   # b81 history-pool: and this release's history pool
        slice1 = mod_build._overtime_crash_fix_upgrade(slice1)[0]   # b81 ot-crash review D3
        # The helmet disc has the economy and the practice squad; the edit adds modern IR for the floor and (practice
        # squad merge) upgrades the disc's revision 7 economy to the current one first.
        from mod_editor.core import nfl2k5_franchise_economy as economy
        prepared = ir.apply(economy.apply(slice1)[0], "modern", standard_guard=True)[0]
        stages = room.realistic_stages(prepared)       # 383 where 4b's needs are installed (the trades review's F1)
        expected, _ = room.apply(prepared, "realistic", stages=stages)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "copy.iso"
            receipt = mod_build.preflight_plan(mod_build.sim_qb_disc_edit(str(disc), str(target), "realistic"))
            self.assertFalse(target.exists())
        self.assertEqual(receipt["sim_qb_source_update"]["result_sha256"], hashlib.sha256(slice1).hexdigest())
        update = receipt["qb_room_source_update"]
        self.assertEqual((update["level"], update["result_sha256"]), ("realistic", hashlib.sha256(expected).hexdigest()))
        self.assertEqual((update["settings"]["status"], update["settings"]["va"]), ("applied", 0x1529000))
        # D1 + D2 plus the coordinator's floor rule (the floor alone since the floor review), shadow off.
        self.assertEqual((update["settings"]["stages"], update["settings"]["shadow"]), (stages, False))
        trades_note = [] if stages & 16 else [room.TRADES_LEFT_OUT]
        self.assertEqual(receipt["user_notes"], update["added"] + trades_note)


class InPlaceWithoutDependenciesTests(unittest.TestCase):
    """The in-place edit on a 128 MB executable without depth chart locks: slice 1 changes, the room is left out."""

    def test_the_edit_leaves_the_room_out(self):
        import hashlib
        from mod_editor.core import nfl2k5_k128 as k128, nfl2k5_sim_realism as sim, nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_xbe_space as space
        retail = Path(os.environ.get("NFL2K5_RETAIL_XBE", ""))
        if not retail.is_file():
            self.skipTest("the private retail default.xbe is absent")
        image, _ = space.apply(retail.read_bytes(), k128.REQUESTS + sim.REQUESTS + qb.REQUESTS, scaleout=True)
        image, _ = k128.apply(image, require=True)
        image, _ = sim.apply(image)
        self.assertEqual(len(room.requirements(image, room._code().STAGE_D1)), 2)  # no depth locks, no lineup roles
        # Custom 0 (no floor, coordinator's rule); Realistic here is refused for the floor (FloorRuleTests).
        plan = mod_build.sim_qb_disc_edit("source.iso", "copy.iso", "custom", custom_rate=0.0)
        # Piece 3 is left out here once its bits ship; at the floor handover there is nothing to leave out.
        self.assertEqual(mod_build._qb_room_resolution(plan, image)[0], None if mod_build._piece3_bits() else "realistic")
        with _handover(1):
            self.assertIsNone(mod_build._qb_room_resolution(plan, image)[0])
        receipt = {"steps": [], "result": {}}
        self.assertTrue(mod_build._edit_installed_sim_qb(plan, Path("source.iso"), Path("copy.iso"), image, receipt,
                                                         lambda *_: None, preflight=True, consume=False, reference=None))
        slice1, _ = qb.apply(image, "custom", custom_rate=0.0)
        self.assertEqual(receipt["sim_qb_source_update"]["result_sha256"], hashlib.sha256(slice1).hexdigest())
        update = receipt["qb_room_source_update"]
        # Nothing to install and no page to remove: Retail on a source without the room changes nothing.
        self.assertEqual((update["level"], update["stages"], update["result_sha256"]),
                         ("retail", 0, hashlib.sha256(slice1).hexdigest()))
        self.assertEqual(receipt.get("user_notes"), update.get("user_notes"))
        named = mod_build.sim_qb_disc_edit("source.iso", "copy.iso", "custom", custom_rate=0.0, qb_room="realistic")
        with _handover(1), self.assertRaisesRegex(ValueError, "depth chart locks"):
            mod_build._edit_installed_sim_qb(named, Path("source.iso"), Path("copy.iso"), image, {"steps": []},
                                             lambda *_: None, preflight=True, consume=False, reference=None)


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
                     qb_room="retail", qb_room_settings={"status": "retail", "mode": "retail"})
        self.state = state
        self.panel.apply_state(dict(state))

    def test_the_quarterback_injury_control_sets_both(self):
        mode = self.panel.qb_injury_mode
        self.panel.apply_preset("softdrink_experimental")  # depth chart locks and SPECIAL rows on
        for value, expected in ((None, None), ("retail", "retail"), ("realistic", "realistic"), ("custom", "realistic")):
            with self.subTest(mode=value):
                mode.setCurrentIndex(mode.findData(value))
                plan = self.panel._plan_for_build()
                self.assertEqual((plan.sim_qb_injuries, plan.qb_room), (value, None))
                self.assertEqual(mod_build._qb_room_level(plan), expected)
        self.panel.apply_preset("softdrink_basic")
        mode.setCurrentIndex(mode.findData("realistic"))
        plan = self.panel._plan_for_build()
        # Basic + Realistic: the floor (needs ticked by the control), no piece 3 (no locks or SPECIAL rows).
        self.assertEqual((plan.sim_qb_injuries, mod_build._qb_room_plan(plan)[:2]), ("realistic", ("realistic", 64)))
        self.assertTrue(plan.modern_injured_reserve and plan.franchise_economy)
        self.assertEqual(mod_build.validate_plan(plan), [])

    def test_one_sentence_of_help_and_a_foreign_room_disables_the_control(self):
        text = self.panel.qb_injury_help.text()
        # The who-starts sentence appears only once piece 3 bits ship; the floor sentence is always there.
        self.assertEqual("who starts at quarterback ride with Realistic and Custom" in text, bool(mod_build._piece3_bits()))
        self.assertIn("so a club is never left without a quarterback", text)
        self.assertNotIn("—", text)
        self.panel.apply_state(dict(self.state, qb_room="foreign", qb_room_settings={"status": "foreign"}))
        self.assertFalse(self.panel.qb_injury_mode.isEnabled())
        self.assertIn("quarterback room", self.panel.qb_injury_help.text())

    def test_a_disc_with_slice_1_but_no_room_counts_as_a_change(self):
        self.panel.apply_state(dict(self.state, sim_qb_injuries="applied",
                                    sim_qb_injury_settings={"status": "applied", "mode": "realistic",
                                                            "custom_rate": .310,
                                                            # b81 merge: the current slice revision, so only the room differs
                                                            "revision": _sim_qb_injuries.REVISION}))
        mode = self.panel.qb_injury_mode
        self.panel.depth_locks_check.setChecked(True)
        self.panel.depth_chart_rows_check.setChecked(True)
        mode.setCurrentIndex(mode.findData("realistic"))
        self.assertTrue(self.panel._sim_qb_injury_change())
        self.panel.apply_state(dict(self.state, sim_qb_injuries="applied",
                                    sim_qb_injury_settings={"status": "applied", "mode": "realistic",
                                                            "custom_rate": .310,
                                                            # b81 merge: the current slice revision, so only the room differs
                                                            "revision": _sim_qb_injuries.REVISION},
                                    qb_room="applied", qb_room_settings={"status": "applied", "mode": "realistic",
                                                                         "stages": _room().realistic_stages()},
                                    depth_locks="applied", depth_chart_rows="applied"))
        mode.setCurrentIndex(mode.findData("realistic"))
        self.assertFalse(self.panel._sim_qb_injury_change())

    def test_a_disc_with_an_earlier_stage_set_counts_as_a_change(self):
        """b81 qb34 D3/D4 hand-over: a disc whose room carries the floor hand-over's Realistic (67) is a change while
        the Studio's Realistic is 327, so Build rewrites the set; the current set is not."""
        slice_now = {"status": "applied", "mode": "realistic", "custom_rate": .310, "revision": _sim_qb_injuries.REVISION}
        mode = self.panel.qb_injury_mode
        for stages, change in ((67, True), (_room().realistic_stages(), False)):
            with self.subTest(stages=stages):
                self.panel.apply_state(dict(self.state, sim_qb_injuries="applied", sim_qb_injury_settings=slice_now,
                                            qb_room="applied",
                                            qb_room_settings={"status": "applied", "mode": "realistic", "stages": stages},
                                            depth_locks="applied", depth_chart_rows="applied"))
                self.panel.depth_locks_check.setChecked(True)
                self.panel.depth_chart_rows_check.setChecked(True)
                mode.setCurrentIndex(mode.findData("realistic"))
                self.assertEqual(bool(self.panel._sim_qb_injury_change()), change)


    def test_with_4bs_needs_on_a_disc_without_trades_counts_as_a_change(self):
        """The trades review's F1: where 4b's needs are on (the 2026 season ticked or its trade deadline on the disc;
        the economy, reserve save compatibility and modern IR), the Studio's Realistic is 383, so a disc at 367 is a
        change and a disc at 383 is not; without them 367 is the current set."""
        slice_now = {"status": "applied", "mode": "realistic", "custom_rate": .310, "revision": _sim_qb_injuries.REVISION}
        mode = self.panel.qb_injury_mode
        for needs, stages, change in (("ticked", 367, True), ("ticked", 383, False), ("on the disc", 367, True),
                                      ("on the disc", 383, False), ("off", 367, False), ("off", 383, True)):
            with self.subTest(needs=needs, stages=stages):
                extra = {"trade_deadline": "applied", "franchise_economy": "applied", "practice_squad": "applied",
                         "modern_injured_reserve": "applied"} if needs == "on the disc" else {}
                self.panel.apply_state(dict(self.state, sim_qb_injuries="applied", sim_qb_injury_settings=slice_now,
                                            qb_room="applied",
                                            qb_room_settings={"status": "applied", "mode": "realistic", "stages": stages},
                                            depth_locks="applied", depth_chart_rows="applied", **extra))
                self.panel.depth_locks_check.setChecked(True)
                self.panel.depth_chart_rows_check.setChecked(True)
                mode.setCurrentIndex(mode.findData("realistic"))
                if needs == "ticked":
                    self.panel.season_check.setChecked(True)
                    for key in ("franchise_economy", "practice_squad", "modern_injured_reserve"):
                        getattr(self.panel, key + "_check").setChecked(True)
                elif needs == "off":
                    self.panel.season_check.setChecked(False)
                self.assertEqual(self.panel._qb_trades_needs_on(), needs != "off")
                self.assertEqual(bool(self.panel._sim_qb_injury_change()), change)


class FloorBuildPageTests(BuildPageTests):
    def test_injuries_above_zero_tick_the_floors_needs_and_unticking_one_turns_them_to_retail(self):
        panel, mode = self.panel, self.panel.qb_injury_mode
        boxes = [getattr(panel, key + "_check") for key in ("modern_injured_reserve", "franchise_economy", "practice_squad")]
        panel.apply_preset("softdrink_basic")
        for box in boxes:
            box.setChecked(False)
        panel.qb_injury_rate.setValue(0.0)
        mode.setCurrentIndex(mode.findData("custom"))
        self.assertFalse(any(box.isChecked() for box in boxes if box.isEnabled()))  # Custom 0 needs no floor
        mode.setCurrentIndex(mode.findData("realistic"))
        self.assertTrue(all(box.isChecked() for box in boxes if box.isEnabled()))
        enabled = [box for box in boxes if box.isEnabled()]
        self.assertTrue(enabled)
        enabled[0].click()  # untick a floor need while injuries are on
        self.assertEqual(mode.currentData(), "retail")
        self.assertIn("never left without a quarterback", panel.qb_injury_help.text())
        self.assertIn("modern injured reserve, the franchise economy and reserve save compatibility",
                      panel.qb_injury_mode.toolTip())


class FaqTests(unittest.TestCase):
    def test_the_faq_claims_only_what_the_studio_installs(self):
        # Review F4 (rev-qb34): the text must match the installed stage set and say what Retail leaves behind.
        from mod_editor.core import nfl2k5_qb_room as room
        text = (ROOT / "docs/mod_editor/2k5_mod_studio_faq.md").read_text(encoding="utf-8")
        section = text.split("## How do quarterback injuries work when I simulate a franchise game?", 1)[1].split("\n## ", 1)[0]
        # D3 (benched for poor play) is bit 256 since the designer's addendum 2 (R5); D2 (the kid's turn) keeps bit 2.
        claims = {"who starts at quarterback": 1 | 2 | 4 | 256, "start of the season": 1, "kid's turn": 2,
                  "benched": 256, "poor play": 256, "back from injury": 4, "returning starter": 4,
                  # E1/E2 hand-over (C21): the backup signing, the better quarterback while the starter is out, and the
                  # protected make-room release
                  "healthy backup quarterback": 8, "starter is out for weeks": 32, "lowest-rated players": 8 | 32,
                  # 4b trades (bit 16): in the Studio's set where their needs are installed (the trades review's F1)
                  "trade for a quarterback": 16, "never trade with a club you manage": 16}
        for words, bits in claims.items():
            with self.subTest(claim=words):
                self.assertEqual(words in section, bool(room.studio_stages(True, True, True) & bits))
        floor, = [p for p in section.split("\n\n") if "never left without a quarterback" in p]
        self.assertIn("keeps the empty space reserved", floor)
        self.assertNotIn("restores the original executable bytes", text)
        self.assertNotIn("restores the original executable byte for byte", text)

    def test_one_plain_faq_paragraph(self):
        text = (ROOT / "docs/mod_editor/2k5_mod_studio_faq.md").read_text(encoding="utf-8")
        floor, = [p for p in text.split("\n\n") if "never left without a quarterback" in p]
        self.assertIn("Retail removes the floor", floor)
        self.assertIn("Custom 0 percent, which needs no floor", floor)
        self.assertNotIn("\u2014", floor)


if __name__ == "__main__":
    unittest.main()
