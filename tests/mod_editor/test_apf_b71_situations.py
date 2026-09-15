"""Book-selected previews, portable refits and explicit candidate edits."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_splb_writer as splb, apf2k8_book_clone as clone
from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio import playcalling_service as service
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture


class RefitTests(unittest.TestCase):
    def test_portable_refit_decodes_exactly_and_keeps_a_fitting_stream(self):
        body = b"authored book entries" * 1600
        literal = b"".join(b"\0" + body[i:i + 8] for i in range(0, len(body), 8))
        greedy = splb.apf_texture_patch.compress_h7a(body, 11)
        with patch.object(splb.apf_texture_patch, "_optimal_binary", return_value=None):
            fitted, receipt = splb.fit_book_h7a(literal, body, 11, len(greedy))
        self.assertEqual(fitted, greedy)
        self.assertEqual(receipt["strategy"], "greedy-refit")
        self.assertEqual(splb.apf_inner.decompress_h7a(fitted, len(body), 11), body)
        tokens, _ = splb.apf_inner._parse_h7a_tokens(fitted, len(body), 11)
        self.assertTrue(all(t.distance is None or t.length <= t.distance for t in tokens))
        with patch.object(splb.apf_texture_patch, "compress_h7a", side_effect=AssertionError("unneeded refit")):
            self.assertEqual(splb.fit_book_h7a(literal, body, 11, len(literal))[0], literal)

    def test_true_overflow_reports_measured_shortfall_and_next_step(self):
        body = bytes(range(128))
        literal = b"".join(b"\0" + body[i:i + 8] for i in range(0, len(body), 8))
        with patch.object(splb.apf_texture_patch, "_optimal_binary", return_value=None):
            with self.assertRaisesRegex(ValidationError, "bytes over.*Remove an added formation"):
                splb.fit_book_h7a(literal, body, 11, 10)


class BookWorkflowTests(FacadeFixture):
    def membership_backend(self):
        self.backend.splb.formation_ratings = splb.formation_ratings
        book = splb.parse_book(self.backend.initial.books["O-ManBlock"], 130)
        def load(session):
            state = self.backend.initial.copy()
            changes = session.staged_splb_changes()
            if changes:
                state.books["O-ManBlock"] = splb.compile_book(book, changes).replacement
            return state
        self.backend.load = load
        changes = [splb.MembershipChange(130, 2, p, True) for p in (10, 11, 12, 13, 14)]
        changes.append(splb.TrailerReplace(130, 2, 64, 3))
        return book, changes

    def test_fine_tune_after_cpu_edit_replays_receipt_and_exports_project(self):
        book, changes = self.membership_backend()
        self.stage(dict(kind="audibles", book="O-ManBlock"))
        old = self.facade._playcalling.events(self.facade.session)[0]
        with patch("mod_editor.apf_studio.session.read_splb_book", return_value=book):
            self.facade.stage_splb_membership(changes, replace_outer=130)
        context = self.facade.playcalling_context()
        fresh = context["events"][0]
        self.assertEqual(fresh["request"], old["request"])
        self.assertNotEqual(fresh["before"], old["before"])
        self.assertIn(64, [f["id"] for f in context["formations"]])
        path = self.facade.session.save_project(self.root / "mixed.apf2k8mod")
        with patch("mod_editor.apf_studio.session.read_splb_book", return_value=book):
            self.facade.session.load_project(path)
        self.assertEqual(self.facade.playcalling_context()["events"], context["events"])

    def test_without_receipt_replay_the_old_export_path_rejects_additions(self):
        book, changes = self.membership_backend()
        self.stage(dict(kind="audibles", book="O-ManBlock"))
        with patch("mod_editor.apf_studio.session.read_splb_book", return_value=book), \
             patch.object(self.facade._playcalling, "rebase_membership", side_effect=lambda session, updated: updated):
            self.facade.stage_splb_membership(changes, replace_outer=130)
        with self.assertRaisesRegex(ValidationError, "earlier book edit changed"):
            self.facade.playcalling_context()

    def test_conflicting_membership_change_is_atomic(self):
        book, changes = self.membership_backend()
        with patch("mod_editor.apf_studio.session.read_splb_book", return_value=book):
            self.facade.stage_splb_membership(changes, replace_outer=130)
            self.stage(dict(kind="ratings", book="O-ManBlock", formation=64, ratings=[7, 7, 7]))
            snapshot = self.facade.playcalling_snapshot()
            with self.assertRaisesRegex(ValueError, "conflict with a CPU Play Calling edit"):
                self.facade.stage_splb_membership((), replace_outer=130)
        self.assertEqual(self.facade.playcalling_snapshot(), snapshot)
        self.assertIn(64, [f["id"] for f in self.facade.playcalling_context()["formations"]])

    def test_explicit_addition_roundtrips_recipe_without_preset(self):
        donor = bytearray(self.backend.initial.books["USER-o"])
        # Existing synthetic primary pair 62/63 becomes donor pair 64/65.
        for index, formation in enumerate((64, 65)):
            at = splb.RECORD_BASE + index * splb.RECORD_STRIDE + splb.TRAILER_OFFSET
            word = struct.unpack_from(">I", donor, at)[0]
            struct.pack_into(">I", donor, at, (word & 0xFFFFFF) | formation << 24)
        self.backend.initial.books["USER-o"] = bytes(donor)
        self.assertFalse(self.facade.session.modifications)
        self.stage(dict(kind="add", book="O-ManBlock", donor="USER-o", formation=64))
        path = self.facade.session.save_project(self.root / "addition.apf2k8mod")
        self.facade.undo()
        self.facade.session.load_project(path)
        context = self.facade.playcalling_context(book="O-ManBlock")
        self.assertIn(64, [f["id"] for f in context["formations"]])
        self.assertEqual([e["request"]["kind"] for e in context["events"]], ["add"])
        with self.assertRaisesRegex(ValidationError, "already in"):
            self.facade.playcalling_review(dict(kind="add", book="O-ManBlock", donor="USER-o", formation=64))

    def test_preview_uses_selected_book_and_explicit_run_share(self):
        self.backend.initial.rost = bytes([10, 90]) + self.backend.initial.rost[2:]
        contexts = [self.facade.playcalling_context(team, "offense", book="USER-o", preview_tendency=60) for team in (0, 1)]
        rows = [("Neutral", dict(down=1, distance_yards=10, yards_to_goal=50, period=1,
                                 clock_seconds=900, score_margin=0, timeouts=3))]
        self.facade.playcalling_predict(contexts[0], "offense", rows)
        count = len(self.backend.calls)
        self.facade.playcalling_predict(contexts[1], "offense", rows)
        self.assertEqual(len(self.backend.calls), count, "team change must reuse the book preview cache")
        self.assertEqual(self.backend.calls[-1][2], .6)


class RetailAdditionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_apf_playcall_research_native import INDEX
        if not INDEX.is_file():
            raise unittest.SkipTest("Owned APF_RETAIL_INDEX absent; retail addition proof needs the APF archive")
        cls.index = INDEX
        cls.donor = splb.read_book(INDEX, 1411)

    def test_fine_tune_additions_export_inside_original_allocations_without_helper(self):
        from mod_editor.core import apf2k8_book_identity as identity
        for outer, count in ((767, 23), (130, 18), (369, 19)):
            book = splb.read_book(self.index, outer)
            present = {r.formation_index for r in book.records if r.populated}
            additions = [r for r in self.donor.records if r.populated and r.formation_index not in present]
            self.assertEqual(len(additions), count)
            first = next(r.record_index for r in book.records if not r.populated)
            changes = []
            for i, r in enumerate(additions):
                changes.extend(splb.MembershipChange(outer, first + i, e.play_index, True) for e in r.entries)
                changes.append(splb.TrailerReplace(outer, first + i, r.formation_index, r.category_index))
            with patch.object(splb.apf_texture_patch, "_optimal_binary", return_value=None):
                compiled = splb.build_book_patch(self.index, changes)
                source = identity.read_resource(self.index, identity.filename_id(book.name), "spb", "SPLB")
                rebuilt, transport = clone.rebuild_resource(source, compiled.replacement)
            self.assertEqual(len(rebuilt), source[1].size)
            self.assertEqual(len(compiled.entry_bytes), source[1].size)
            self.assertEqual(compiled.report["h7a_transport"]["strategy"], "greedy-refit")
            self.assertEqual(transport["h7a_overlapping_matches"], 0)
            splb.verify_book(book.body, compiled.replacement, changes)
            reparsed = splb.parse_book(compiled.replacement, outer)
            self.assertEqual([r.formation_index for r in reparsed.records[first:first + count]],
                             [r.formation_index for r in additions])
            self.assertEqual(splb.read_book(self.index, outer).body, book.body)

    def test_candidates_include_minimum_weight_and_exclude_removed_membership(self):
        from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
        master = read_master_play_body(self.index)
        book = splb.read_book(self.index, 130).body
        book = splb.set_formation_ratings(book, 14, (7, 7, 7))
        situation = model.Situation(3, 8, 50, 1, 900, 0, 3)
        before = model.situation_candidates(book, master, situation)
        queens = next(r for r in before if r["formation"] == 14 and r["category"] == 6)
        self.assertEqual(queens["tight_ends"], 0)
        self.assertAlmostEqual(queens["formation_weight"], .1, delta=1e-6)
        removed = splb.remove_formation(book, 14).book
        self.assertNotIn(14, [r["formation"] for r in model.situation_candidates(removed, master, situation)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
