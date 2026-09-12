"""Real synthetic archive insertion/transport plus injected P3 lever contracts."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import playcalling_build, playcalling_service as service
from mod_editor.core import apf2k8_book_identity as identity, apf2k8_book_clone as clone
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture, Assignment
from tests.mod_editor.test_apf_book_unlock import archive_fixture


class BuildTests(FacadeFixture):
    def setUp(self):
        super().setUp()
        self.index = archive_fixture(self.root / "game")
        self.facade.source = self.facade.session.source = type(self.facade.source)(self.index.parent, self.index.parent, self.index, "d"*64, 0, "e"*64, "Synthetic")
        self.backend.clone.bind_roster = clone.bind_roster
        self.backend.clone.compile_unlock = Mock(wraps=clone.compile_unlock)
        self.backend.clone.build_new_folder = clone.build_new_folder
        def plan(index, rost, side):
            # Mirrors apf2k8_book_clone.own_book_plan: an offensive clone reuses the
            # team-name string and a defensive clone reuses a distinct label name, so
            # the two sides of one team never share a resource name.
            parsed = identity.parse_roster_identity(rost)
            used = {getattr(t, side) for t in parsed.teams}
            free = [r for r in parsed.labels if r.side == side and r.index not in used]
            return tuple(Assignment(t.index, t.name, label.index, parsed.labels[getattr(t, side)].kind,
                                    t.name if side == "offense" else label.name)
                         for t, label in zip(parsed.teams[:24], free))
        self.backend.clone.own_book_plan = plan
        def load(session):
            from mod_editor.apf_studio.book_content import book_catalog
            books = book_catalog(session.source.index_0a)
            rost = identity.read_disc_roster(session.source.index_0a)
            parsed = identity.parse_roster_identity(rost)
            labels = {r.index: r for r in parsed.labels}
            return service.State({b.name: b.body for b in books.values()}, self.backend.initial.master, rost,
                tuple({"team_index": t.index, "team_name": t.name, "offense": labels[t.offense].kind, "defense": labels[t.defense].kind} for t in parsed.teams[:24]),
                {**self.backend.initial.sides, **{l.kind: l.side for l in parsed.labels}},
                {"formations": [{"index": 0, "name": "Synthetic formation"}], "plays": []})
        self.backend.load = load

    def test_twenty_four_clones_insert_once_then_name_bound_rating_readback(self):
        donor_before = identity.read_resource(self.index, identity.filename_id("O-ManBlock"), "spb", "SPLB")[3]
        plan = self.facade.playcalling_plan("offense")
        self.assertEqual(len(plan["assignments"]), 24)
        self.stage(plan)
        name = plan["assignments"][0]["clone_name"]
        self.stage(dict(kind="ratings", book=name, formation=0, ratings=[7, 4, 2]))
        receipt = playcalling_build.finalize(self.index, self.facade.session.modifications[0], backend=self.facade._playcalling.backend)
        self.assertEqual(self.backend.clone.compile_unlock.call_count, 1)
        self.assertEqual(len(receipt["teams_now_own_books"]), 24)
        self.assertEqual(receipt["events"][1]["before"], [0, 0, 0])
        self.assertEqual(receipt["events"][1]["after"], [7, 4, 2])
        after = identity.read_resource(self.index, identity.filename_id(name), "spb", "SPLB")[3]
        self.assertEqual(self.backend.ratings(after, 0), (7, 4, 2))
        self.assertEqual(identity.read_resource(self.index, identity.filename_id("O-ManBlock"), "spb", "SPLB")[3], donor_before)
        disk = json.loads((self.index.parent / "book-content-receipt.json").read_text())
        self.assertTrue(disk["verification"]["content_reparsed"])
        self.assertEqual(disk["runtime_status"], "UNWITNESSED")

    def test_one_team_can_own_both_an_offensive_and_a_defensive_book(self):
        offense = self.facade.playcalling_plan("offense", 0)
        defense = self.facade.playcalling_plan("defense", 0)
        self.assertEqual([r["team_index"] for r in offense["assignments"]], [0])
        self.assertEqual([r["team_index"] for r in defense["assignments"]], [0])
        names = [offense["assignments"][0]["clone_name"], defense["assignments"][0]["clone_name"]]
        self.assertEqual(len(set(names)), 2)
        self.stage(offense)
        self.stage(defense)
        context = self.facade.playcalling_context(0, "defense")
        self.assertEqual(context["book"], names[1])
        receipt = playcalling_build.finalize(self.index, self.facade.session.modifications[0],
                                             backend=self.facade._playcalling.backend)
        # One archive transaction carries both sides of the same team.
        self.assertEqual(self.backend.clone.compile_unlock.call_count, 1)
        self.assertEqual(receipt["teams_now_own_books"], ["Synthetic Team 0"])
        for name in names:
            body = identity.read_resource(self.index, identity.filename_id(name), "spb", "SPLB")[3]
            self.assertEqual(self.backend.splb.parse_book(body, 0).name, name)

    def test_changed_review_inputs_refuse_before_archive_writes(self):
        self.stage(dict(kind="ratings", book="O-ManBlock", formation=0, ratings=[7, 4, 2]))
        original = self.backend.load
        def changed(session):
            state = original(session)
            state.books["O-ManBlock"] = self.backend.set_ratings(state.books["O-ManBlock"], 0, (1, 1, 1))
            return state
        self.backend.load = changed
        before = self.index.read_bytes()
        with self.assertRaisesRegex(ValidationError, "Build inputs changed"):
            playcalling_build.finalize(self.index, self.facade.session.modifications[0], backend=self.facade._playcalling.backend)
        self.assertEqual(self.index.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
