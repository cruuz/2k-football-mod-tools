"""Basileus Maximus' beta-77 Studio additions, one test per README feature.

1. Created plays show up in the in-game Playbook Manager (formation offer bits).
2. Created plays can be edited in Assignment Routes.
3. Fine-tune Plays lists created and edited plays, and can add them to CPU books.
4. Plays can be added to or taken out of any formation, at most 84 per formation.
5. Mirror assignments (one player, or the QB and the player he hands off to; K / A / hole fields).
6. Design Play/Formation can be staged and built together with Assignment Routes, Who lines up
   and Fine-tune Plays.

Synthetic tests always run.  Retail tests read the extracted retail 0A read-only and skip when absent.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mod_editor.core import apf2k8_play_codec as c
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_play_designer as designer
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio import play_design_service as design_service
from test_apf_play_designer import synthetic, play_request

INDEX = Path(os.environ.get("APF_RETAIL_INDEX", ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"))


def offered(body: bytes, formation: int, play: int) -> bool:
    """Playbook Manager bit, computed here so the test does not depend on the new helpers."""
    at = c.RELATION_BASE + formation * c.RELATION_STRIDE + (play // 32) * 4
    return bool(struct.unpack_from(">I", body, at)[0] >> (play % 32) & 1)


def formations_offering(body: bytes, play: int) -> set[int]:
    return {f for f in range(struct.unpack_from(">I", body, 0x34)[0]) if offered(body, f, play)}


def plays_offered(body: bytes, formation: int) -> set[int]:
    return {p for p in range(struct.unpack_from(">I", body, 0x38)[0]) if offered(body, formation, p)}


def play_side(body: bytes, play: int) -> int:
    return struct.unpack_from(">I", body, c.PLAY_BASE + play * c.PLAY_SIZE + 4)[0] >> 28


def overfull(retail: bytes, plan: dict, formation: int, total: int) -> dict:
    """A design whose offer set gives ``formation`` exactly ``total`` plays: offense plays and the created one."""
    offense = [p for p in range(586) if play_side(retail, p) == 0]
    return {**plan, "offer_sets": [{"formation": formation, "plays": offense[:total - 1] + [586]}]}


class SyntheticTests(unittest.TestCase):
    def setUp(self):
        self.source = synthetic()

    def test_offer_set_limit_is_84_per_formation(self):
        plan = designer.empty_plan(self.source)
        plan["offer_sets"] = [{"formation": 0, "plays": list(range(85))}]
        with self.assertRaisesRegex(ValidationError, "at most 84"):
            designer.normalize_plan(plan)
        plan["offer_sets"] = [{"formation": 0, "plays": list(range(84))}]
        self.assertEqual(len(designer.normalize_plan(plan)["offer_sets"][0]["plays"]), 84)

    def test_assign_plays_skips_what_does_not_fit_and_keeps_locked_plays(self):
        current = {0: set(range(80)), 1: {5}}
        changed, skipped = designer.assign_plays(current, {}, set(range(100, 110)), [0, 1])
        self.assertEqual(len(changed[0]), 84)
        self.assertEqual(changed[0] - current[0], {100, 101, 102, 103})
        self.assertEqual(skipped, {0: 6})
        self.assertEqual(changed[1], {5} | set(range(100, 110)))
        changed, skipped = designer.assign_plays({0: {1, 2, 3}}, {0: {2}}, {1, 2}, [0], remove=True)
        self.assertEqual(changed, {0: {2, 3}})
        self.assertEqual(skipped, {0: 1})

    def test_mirror_rules_and_new_handoff_fields(self):
        take = c.Node.from_bytes(struct.pack(">BBHI", 0x16, 0, 0, (2 << 28) | 3))
        self.assertEqual(take.with_field("hole", 7).to_bytes()[4] >> 4, 7)
        self.assertEqual(take.with_field("a", 5).to_bytes()[7] & 15, 5)
        move = c.Node.from_bytes(struct.pack(">BBHI", 0x04, 0, 0, ((128 + 6) << 24) | ((64 + 10) << 16)))
        edits, notes = c.mirror_chain_edits([move, take])
        self.assertEqual(edits, [(0, "x_ft", -6), (1, "hole", 7)])
        self.assertEqual(notes, [])
        mirrored = [move.with_field("x_ft", -6), take.with_field("hole", 7)]
        again, _ = c.mirror_chain_edits(mirrored)
        self.assertEqual(again, [(0, "x_ft", 6), (1, "hole", 2)])
        for op in (0x13, 0x14):
            node = c.Node.from_bytes(struct.pack(">BBHI", op, 0, 0, 0))
            self.assertEqual(node.with_field("k", 7).to_bytes()[7] >> 4, 7)

    def test_composition_admits_routes_maps_and_fine_tune_with_a_design(self):
        design = SimpleNamespace(kind=design_service.PROVIDER_KIND)
        for kind in ("formation_package_map", "play_assignment_route", "splb_book_membership"):
            design_service.check_composition((design, SimpleNamespace(kind=kind)))
        for kind in ("formation_alignment", "coverage_geometry", "apf_scheme_presets"):
            with self.assertRaisesRegex(ValidationError, kind):
                design_service.check_composition((design, SimpleNamespace(kind=kind)))


@unittest.skipUnless(INDEX.is_file(), f"Retail APF 0A absent: {INDEX}; set APF_RETAIL_INDEX to extracted read-only retail")
class RetailWorkflowTests(unittest.TestCase):
    """One session with a staged design that appends play 586 and calls it from CPU book 259."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.apf_studio.models import ApfSource
        from mod_editor.apf_studio.session import ApfSession
        cls.temp = Path(tempfile.mkdtemp(prefix="apf-b778-"))
        cls.source = ApfSource(INDEX, INDEX.parent, INDEX, "a" * 64, 1, "b" * 64, "Retail APF (read only)")
        cls.session = ApfSession(cls.source, SimpleNamespace(), cache_root=cls.temp / "cache")
        cls.retail = cls.session._master_play_body()
        cls.book = splb.read_book(INDEX, 259)
        cls.empty = next(r.record_index for r in cls.book.records if not r.entries)
        cls.used = next(r.record_index for r in cls.book.records if r.entries)
        plan = designer.empty_plan(cls.retail)
        plan["plays"] = [play_request("append", 586, 0, "Basileus Power")]
        plan["cpu_calls"] = [{"outer": 259, "record": cls.empty, "play": 586, "formation": 0, "donor_record": 0}]
        cls.plan = plan
        cls.session.apply_play_design(plan)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp, ignore_errors=True)

    def setUp(self):
        # Every test starts from the design alone.
        for kind in ("splb_book_membership", "formation_package_map", "play_assignment_route"):
            for item in list(self.session.modifications):
                if item.kind == kind:
                    self.session.revert(item.asset_id)

    def staged_master(self) -> bytes:
        return self.session._staged_master_play_body()

    def test_1_created_play_is_offered_by_the_donors_formations(self):
        body = self.staged_master()
        self.assertEqual(c.Book.from_bytes(body).play_name(586), "Basileus Power")
        self.assertTrue(formations_offering(self.retail, 0))
        self.assertEqual(formations_offering(body, 586), formations_offering(self.retail, 0))

    def test_2_route_edit_on_a_created_play(self):
        modification = self.session.replace_play_assignment_route(586, 5, 2, 5)
        self.assertEqual(modification.kind, "play_assignment_route")
        book = c.Book.from_bytes(self.staged_master())
        self.assertEqual([n.to_bytes() for n in book.chain(586, 5)], [n.to_bytes() for n in book.chain(2, 5)])
        self.assertEqual(self.session.master_inventory(staged=True)["plays"][586]["name"], "Basileus Power")

    def test_3_fine_tune_lists_and_adds_created_plays(self):
        designed = self.session.source_splb_book(259)
        self.assertEqual([e.play_index for e in designed.records[self.empty].entries], [586])
        change = splb.MembershipChange(259, self.used, 586, True)
        self.assertEqual(self.session.apply_splb_membership_batch((change,), replace_outer=259), 1)
        compiled = self.session.compiled_splb_book(259, (change,))
        rows = splb.parse_book(compiled.replacement, 259).records
        self.assertIn(586, [e.play_index for e in rows[self.used].entries])
        self.assertEqual([e.play_index for e in rows[self.empty].entries], [586])

    def test_4_formation_offer_sets_add_and_remove_plays(self):
        formation = 1
        before = plays_offered(self.retail, formation)
        removed = min(before)
        wanted = sorted((before - {removed}) | {586})
        plan = {**self.plan, "offer_sets": [{"formation": formation, "plays": wanted}]}
        body = designer.compile_design(self.retail, plan).replacement
        self.assertEqual(plays_offered(body, formation), set(wanted))
        self.assertNotIn(formation, formations_offering(body, removed))
        body = designer.compile_design(self.retail, overfull(self.retail, self.plan, formation, 84)).replacement
        self.assertEqual(len(plays_offered(body, formation)), 84)  # 84 fits
        with self.assertRaisesRegex(ValidationError, "at most 84"):
            designer.compile_design(self.retail, overfull(self.retail, self.plan, formation, 85))
        # Offering every offense play in a formation (the bulk unlock) overfills it and is refused.
        with self.assertRaisesRegex(ValidationError, "at most 84 plays per formation"):
            designer.compile_design(self.retail, {**self.plan, "unlock_offers": {"formations": [formation], "hidden": False}})

    def test_5_mirror_a_real_handoff_pair_round_trips(self):
        book = c.Book.from_bytes(self.retail)
        found = None
        for play in range(len(book.plays)):
            for slot in range(11):
                chain = book.chain(play, slot)
                hand = next((n for n in chain if n.op in (0x13, 0x14)), None)
                if hand is not None:
                    found = (play, chain, hand.operands[0])
                    break
            if found:
                break
        self.assertIsNotNone(found)
        play, chain, partner = found
        flipped = 0
        for target in (chain, book.chain(play, partner)):
            edits, _ = c.mirror_chain_edits(target)
            flipped += len(edits)
            mirrored = list(target)
            for index, field, value in edits:
                mirrored[index] = mirrored[index].with_field(field, value)
            back, _ = c.mirror_chain_edits(mirrored)
            restored = list(mirrored)
            for index, field, value in back:
                restored[index] = restored[index].with_field(field, value)
            self.assertEqual([n.to_bytes() for n in restored], [n.to_bytes() for n in target])
        self.assertGreater(flipped, 0)

    def test_6_design_stages_and_builds_with_routes_maps_and_fine_tune(self):
        from mod_editor.apf_studio import build
        from mod_editor.core.apf2k8_package_map_writer import PackageMapChange, list_apf_formations
        from mod_editor.core.apf2k8_play_design_build import parse_resource, read_resource
        self.session.replace_play_assignment_route(586, 5, 2, 5)
        fid, _, current = list_apf_formations(self.session._master_play_base())[0]
        swapped = (current[1], current[0], *current[2:])
        self.session.apply_package_map_batch((PackageMapChange(fid, swapped),))
        self.session.apply_splb_membership_batch((splb.MembershipChange(259, self.used, 586, True),), replace_outer=259)
        kinds = sorted(m.kind for m in self.session.modifications)
        self.assertEqual(kinds, ["apf_play_design", "formation_package_map", "play_assignment_route", "splb_book_membership"])
        by_kind = lambda kind: tuple(m for m in self.session.modifications if m.kind == kind)
        rows = build.ApfBuildService(self.source)._compile_design_combined(
            by_kind("apf_play_design")[0], by_kind("play_assignment_route"),
            by_kind("formation_package_map"), by_kind("splb_book_membership"))
        entries = {outer: entry for outer, entry, _ in rows}
        self.assertEqual(set(entries), {180, 259})
        master = parse_resource(read_resource(INDEX, 180).entry, entries[180]).body
        book = c.Book.from_bytes(master)
        self.assertEqual((len(book.plays), book.play_name(586)), (587, "Basileus Power"))
        self.assertEqual([n.to_bytes() for n in book.chain(586, 5)], [n.to_bytes() for n in book.chain(2, 5)])
        self.assertEqual(list_apf_formations(master)[0][2], swapped)
        self.assertEqual(formations_offering(master, 586), formations_offering(self.retail, 0))
        cpu = splb.parse_book(parse_resource(read_resource(INDEX, 259).entry, entries[259]).body, 259)
        self.assertEqual([e.play_index for e in cpu.records[self.empty].entries], [586])
        self.assertIn(586, [e.play_index for e in cpu.records[self.used].entries])
        for _, _, row in rows:
            self.assertEqual(row["writer_mode"], "design_then_routes_maps_and_fine_tune")
            self.assertEqual(row["runtime_status"], "UNWITNESSED")

    def test_project_with_design_route_and_fine_tune_saves_and_loads(self):
        from mod_editor.apf_studio.session import ApfSession
        self.session.replace_play_assignment_route(586, 5, 2, 5)
        self.session.apply_splb_membership_batch((splb.MembershipChange(259, self.used, 586, True),), replace_outer=259)
        path = self.temp / "stacked.apf2k8mod"
        self.session.save_project(path)
        fresh = ApfSession(self.source, SimpleNamespace(), cache_root=self.temp / "cache-fresh")
        self.assertEqual(fresh.load_project(path), 3)
        self.assertEqual(c.Book.from_bytes(fresh._staged_master_play_body()).to_bytes(), self.staged_master())

    def test_reverting_the_design_under_dependent_edits_is_refused(self):
        from mod_editor.apf_studio.session import SessionError
        self.session.replace_play_assignment_route(586, 5, 2, 5)
        with self.assertRaisesRegex(SessionError, "Revert those edits first"):
            self.session.revert(designer.SELECTOR)
        self.assertIsNotNone(self.session.staged_play_design())


@unittest.skipUnless(INDEX.is_file(), f"Retail APF 0A absent: {INDEX}; set APF_RETAIL_INDEX to extracted read-only retail")
class RetailWindowTests(unittest.TestCase):
    """The two new Design Play/Formation windows and the mirror buttons, offscreen."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        from mod_editor.core.apf2k8_play_design_build import read_resource
        cls.app = QApplication.instance() or QApplication([])
        cls.retail = read_resource(INDEX, 180).body
        cls.book = c.Book.from_bytes(cls.retail)

    def test_formation_plays_window_caps_at_84_and_requests_an_offer_set(self):
        from PyQt5.QtCore import Qt
        from mod_editor.apf_studio.play_designer_qt import FormationOfferDialog
        dialog = FormationOfferDialog(self.book, self.retail, self.retail, {})
        self.addCleanup(dialog.close)
        dialog.formation.setCurrentIndex(dialog.formation.findData(1))
        items = [dialog.list.item(i) for i in range(dialog.list.count())]
        unchecked = [item for item in items if item.checkState() == Qt.Unchecked]
        checked = [item for item in items if item.checkState() == Qt.Checked]
        self.assertEqual({item.data(Qt.UserRole) for item in checked}, plays_offered(self.retail, 1))
        checked[0].setCheckState(Qt.Unchecked)
        for item in unchecked:
            item.setCheckState(Qt.Checked)
        self.assertEqual(dialog._checked(), 84)
        self.assertIn("Limit reached", dialog.count.text())
        request = dialog.request()
        self.assertEqual([entry["formation"] for entry in request], [1])
        self.assertEqual(len(request[0]["plays"]), 84)
        self.assertNotIn(checked[0].data(Qt.UserRole), request[0]["plays"])
        plan = designer.empty_plan(self.retail)
        plan["offer_sets"] = request
        body = designer.compile_design(self.retail, plan).replacement
        self.assertEqual(plays_offered(body, 1), set(request[0]["plays"]))

    def test_assign_plays_window_by_personnel_and_family(self):
        from PyQt5.QtCore import Qt
        from mod_editor.apf_studio.play_designer_qt import AssignPlaysDialog
        dialog = AssignPlaysDialog(self.book, self.retail, self.retail, {})
        self.addCleanup(dialog.close)
        target = next(p for p in range(586) if play_side(self.retail, p) == 0 and 1 not in formations_offering(self.retail, p))
        for i in range(dialog.plays.count()):
            if dialog.plays.item(i).data(Qt.UserRole) == target:
                dialog.plays.item(i).setCheckState(Qt.Checked)
        family = next(i for i in range(dialog.family.count()) if dialog.family.item(i).data(Qt.UserRole) == "I")
        dialog.family.item(family).setCheckState(Qt.Checked)
        dialog._apply_matches(False)
        chosen = set(AssignPlaysDialog._checked(dialog.targets))
        self.assertIn(1, chosen)
        self.assertTrue(all(designer.formation_family(self.book.formation_name(f)) == "I" for f in chosen))
        request = dialog.request()
        for entry in request:
            self.assertIn(target, entry["plays"])
            self.assertLessEqual(len(entry["plays"]), 84)
        self.assertIn(1, [entry["formation"] for entry in request])

    def test_mirror_buttons_stage_the_qb_and_handoff_partner(self):
        from unittest.mock import patch
        from PyQt5.QtWidgets import QMessageBox
        from mod_editor.apf_studio.play_designer_qt import PlayDesignDialog
        play, slot, partner = next((p, s, n.operands[0]) for p in range(586) for s in range(11)
                                   for n in self.book.chain(p, s) if n.op in (0x13, 0x14))
        dialog = PlayDesignDialog(self.book, 586)
        self.addCleanup(dialog.close)
        dialog.mode.setCurrentIndex(dialog.mode.findData("edit"))
        dialog.target.setCurrentIndex(dialog.target.findData(play))
        dialog.donor.setCurrentIndex(dialog.donor.findData(play))
        dialog.slot.setCurrentIndex(dialog.slot.findData(slot))
        with patch.object(QMessageBox, "information") as shown:
            dialog._mirror(True)
        self.assertIn(f"{slot}, {partner}", shown.call_args.args[2])
        staged_slots = {key[0] for key in dialog.nodes}
        self.assertTrue(staged_slots <= {slot, partner} and staged_slots)
        with patch.object(QMessageBox, "information"):
            dialog._mirror(True)  # a second press undoes it
        plan = designer.empty_plan(self.retail)
        plan["plays"] = [dialog.request()]
        after = c.Book.from_bytes(designer.compile_design(self.retail, plan).replacement)
        for s in (slot, partner):
            self.assertEqual([n.to_bytes() for n in after.chain(play, s)], [n.to_bytes() for n in self.book.chain(play, s)])


if __name__ == "__main__":
    unittest.main()
