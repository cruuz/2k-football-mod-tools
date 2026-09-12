"""Synthetic beta-67 contract modules injected only through the product facade."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import struct
import sys
import tempfile
import json
from types import SimpleNamespace as NS
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.session import ApfSession
from mod_editor.apf_studio import playcalling_service as service
from mod_editor.core import apf2k8_splb_writer as splb, apf2k8_book_clone as clone, apf2k8_audibles as audibles
from tests.mod_editor.test_apf_cpu_audibles import book_bytes, metadata


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    row: int
    roles: tuple
    tight_ends: int = 1


@dataclass(frozen=True)
class Assignment:
    team_index: int
    team_name: str
    label_id: int
    donor_name: str
    clone_name: str


class FakeBackend:
    """The absent P3 behavior is deliberately confined to this test module."""
    def __init__(self):
        self.lineup_callers = "non_cpu"
        self.holes = False
        self.calls = []
        self.curves = NS(PROFILES=(NS(name="base"), NS(name="tu1")), build_curve_patch=self.curve_patch)
        master = bytearray(0x300)
        for i in range(28):
            master[0x48 + i*16] = min(i, 16)
            master[0x49 + i*16:0x54 + i*16] = bytes((0, 1, 2, 3, 4, 8, 9, 9, 8, 10, 10))
        self.initial = service.State(
            {name: clone.clone_body(book_bytes(), name) for name in ("O-ManBlock", "USER-o", "global-o", "X-43Cover2", "USER-d", "global-d")},
            bytes(master), bytes([50]*24 + [0]*104),
            tuple({"team_index": i, "team_name": f"Team {i}", "offense": "O-ManBlock", "defense": "X-43Cover2"} for i in range(24)),
            {name: side for side, names in (("offense", ("O-ManBlock", "USER-o", "global-o")), ("defense", ("X-43Cover2", "USER-d", "global-d"))) for name in names},
            {"formations": [{"index": 62, "name": "Ace"}, {"index": 63, "name": "Ace Flip"}],
             "plays": [{"index": i, "name": f"Play {i}"} for i in range(30)]})
        self.splb = NS(**{key: value for key, value in vars(splb).items() if not key.startswith("__")})
        self.splb.formation_ratings = self.ratings
        self.splb.set_formation_ratings = self.set_ratings
        self.splb.play_rating = lambda book, form, play: next(e.x for e in self.record(book, form).entries if e.play_index == play)
        self.splb.set_play_rating = self.set_play
        self.splb.set_formation_categories = self.set_categories
        self.splb.remove_formation = self.remove
        self.splb.retire_category = self.retire
        self.splb.row_coverage = lambda book, master: {i: (() if self.holes and i in (8, 9, 10) else (3,)) for i in range(11)}
        self.tendency = NS(team_tendency=lambda rost, team: rost[team], set_team_tendency=lambda rost, team, value: rost[:team] + bytes([value]) + rost[team+1:])
        self.master = NS(set_category_row=self.set_row, set_category_roles=self.set_roles, verify_master=lambda data: None)
        self.model = NS(Situation=lambda **kwargs: NS(**kwargs), predict_offense=self.offense, predict_defense=self.defense,
                        category_table=self.categories, personnel_roles=lambda master, category: self.categories(master)[category].roles)
        self.clone = NS(own_book_plan=self.plan, CloneRequest=clone.CloneRequest, clone_body=clone.clone_body, bind_roster=self.bind)
        self.audibles = NS(plan_audibles=audibles.plan_audibles, play_catalog=lambda master: metadata())

    def load(self, session):
        return self.initial.copy()

    @staticmethod
    def curve_patch(profile, *, offense_category_curve, defense_category_curve):
        # Authored fake TOML, no game words. It exists only behind facade injection.
        side = "offense" if offense_category_curve is not None else "defense"
        payload = (f'title_name = "Synthetic APF"\nhash = "{profile.name}"\n[[patch]]\n'
                   f'name = "{side}"\nis_enabled = true\n[[patch.be32]]\naddress = 4096\nvalue = 0\n')
        return NS(as_toml=lambda: payload)

    @staticmethod
    def record(book, formation):
        return next(r for r in splb.parse_book(book, 0).records if r.populated and r.formation_index == formation)

    def ratings(self, book, formation):
        word = struct.unpack_from(">I", self.record(book, formation).trailer)[0]
        return tuple((word >> shift) & 7 for shift in (14, 11, 8))

    def set_ratings(self, book, formation, values):
        data = bytearray(book)
        for record in splb.parse_book(book, 0).records:
            if record.populated and record.formation_index == formation:
                at = splb.RECORD_BASE + record.record_index * splb.RECORD_STRIDE + 0xA8
                word = struct.unpack_from(">I", data, at)[0]
                for value, shift in zip(values, (14, 11, 8)):
                    word = (word & ~(7 << shift)) | value << shift
                struct.pack_into(">I", data, at, word)
        return bytes(data)

    def set_play(self, book, formation, play, x):
        data = bytearray(book)
        record = self.record(book, formation)
        for i, entry in enumerate(record.entries):
            if entry.play_index == play:
                struct.pack_into(">H", data, splb.RECORD_BASE + record.record_index * splb.RECORD_STRIDE + 2*i, splb.SplbEntry(x, entry.y, play).encode())
        return bytes(data)

    def set_categories(self, book, formation, primary, secondary):
        data = bytearray(book)
        r = self.record(book, formation)
        at = splb.RECORD_BASE + r.record_index * splb.RECORD_STRIDE + 0xA8
        word = struct.unpack_from(">I", data, at)[0]
        struct.pack_into(">II", data, at, (word & ~(127 << 17)) | primary << 17, sum(1 << i for i in set(secondary)))
        return bytes(data)

    def remove(self, book, formation):
        data = bytearray(book)
        blocks = [book[splb.RECORD_BASE+r.record_index*splb.RECORD_STRIDE:splb.RECORD_BASE+(r.record_index+1)*splb.RECORD_STRIDE]
                  for r in splb.parse_book(book, 0).records if r.populated and r.formation_index != formation]
        empty = struct.pack(">H", splb.FILLER) * splb.ENTRY_CAPACITY + struct.pack(">Q", 0x920000000000)
        data[splb.RECORD_BASE:splb.RECORD_BASE+splb.RECORD_COUNT*splb.RECORD_STRIDE] = b"".join(blocks + [empty]*(splb.RECORD_COUNT-len(blocks)))
        return NS(book=bytes(data), retired_categories=(3,), row_coverage=self.splb.row_coverage(data, b""))

    def retire(self, book, category):
        # A synthetic donor advertises category 3; this fake transfers it to 4.
        for record in splb.parse_book(book, 0).records:
            if record.populated and record.category_index == category:
                book = self.set_categories(book, record.formation_index, 4, (4,))
        return book

    @staticmethod
    def set_row(master, category, row):
        data = bytearray(master); data[0x48 + category*16] = row
        return bytes(data)

    @staticmethod
    def set_roles(master, category, roles):
        data = bytearray(master); data[0x49+category*16:0x54+category*16] = bytes(roles)
        return bytes(data)

    @staticmethod
    def categories(master):
        role_names = {8: "Tight end", 9: "Wide receiver", 10: "Running back"}
        return tuple(Category(i, "5-2" if i == 12 else f"Personnel {i}", master[0x48+i*16],
                              tuple(role_names.get(x & 31, f"Role {x & 31}") for x in master[0x49+i*16:0x54+i*16])) for i in range(28))

    def offense(self, book, master, tendency, situation, *, seeds):
        self.calls.append(("offense", service.digest(book), tendency, situation.distance_yards, seeds))
        return NS(categories=[(3, "Ace personnel", .8)], formations=[(62, "Ace", .75), (63, "Ace Flip", .25)],
                  plays=[(10, "Play 10", .6)], requested_row=8, notes=("Flush carries no tight end",))

    def defense(self, book, master, row, yards, *, seeds):
        self.calls.append(("defense", row, yards, seeds))
        return NS(categories=[(13, "4-3", 1.)], formations=[(62, "4-3", 1.)], plays=[(10, "Cover 2", 1.)], requested_row=13, notes=("Offensive personnel determines the request.",))

    @staticmethod
    def plan(index, rost, side):
        offset = 24 if side == "offense" else 48
        return tuple(Assignment(i, f"Team {i}", i + (24 if side == "defense" else 0), "O-ManBlock" if side == "offense" else "X-43Cover2", f"Team {i} {'O' if side == 'offense' else 'D'}")
                     for i in range(24) if not rost[offset+i])

    @staticmethod
    def bind(rost, requests):
        data = bytearray(rost)
        for r in requests:
            offset = 24 if splb.BOOK_SIDES[r.donor_type] == "offense" else 48
            data[offset+r.team_index] = 1
        return bytes(data), {}


class FacadeFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="apf-playcalling-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeBackend()
        self.facade = ApfStudioFacade(cache_root=self.root / "cache", playcalling_backend=self.backend)
        source = ApfSource(self.root, self.root, self.root / "0A", "d"*64, 0, "e"*64, "Synthetic")
        self.facade.source = source
        self.facade.catalog = NS(assets=(), capabilities=(), by_id={})
        self.facade.session = ApfSession(source, self.facade.catalog, cache_root=self.root / "cache")
        self.addCleanup(self.facade.close)

    def stage(self, request):
        review = self.facade.playcalling_review(request)
        return self.facade.stage_playcalling(review)


class FacadeTests(FacadeFixture):
    def test_capability_handoff_schema_and_new_file_closure(self):
        from mod_editor.capabilities import validate_registry as registry
        root = Path(__file__).resolve().parents[2]
        rows = json.loads((root / "docs/mod_editor/apf_b67_playcalling_capabilities.json").read_text())
        document = json.loads((root / "mod_editor/capabilities/registry.v1.json").read_text())
        # The JSON file is a merge input: a row replaces the canonical row of the same
        # id rather than joining it, which is how the integration merged these four.
        merged = {row["id"]: row for row in document["capabilities"]}
        for row in rows:
            self.assertIn(row["id"], merged, "each proposed row must be merged into the registry")
            merged[row["id"]] = {**row, "evidence": sorted(set(merged[row["id"]]["evidence"]) | set(row["evidence"]))}
        document["capabilities"] = sorted(merged.values(), key=lambda r: r["id"])
        registry.validate_data(document, check_files=False)
        for row in rows:
            self.assertTrue(row["validation_command"].startswith("python3 -m tests.mod_editor.test_apf_playcalling_editor_"))
            for path in row["evidence"] + [row["backend"]["module"]]:
                self.assertTrue((root / path).is_file(), path)
            self.assertEqual(registry._command_module(row["backend"]["command"], "P4"), row["backend"]["module"])

    def test_ratings_preview_cache_undo_and_project_roundtrip(self):
        c = self.facade.playcalling_context()
        self.assertEqual(len(c["state"].teams), 24)
        self.assertIn("USER-o", c["donors"])
        self.assertIn("global-o", c["donors"])
        rows = [("3rd and 8", dict(down=3, distance_yards=8, yards_to_goal=50, period=2, clock_seconds=400, score_margin=0, timeouts=3))]
        first = self.facade.playcalling_predict(c, "offense", rows)
        self.assertIs(first, self.facade.playcalling_predict(c, "offense", rows))
        self.assertEqual(len(self.backend.calls), 1)
        self.stage(dict(kind="ratings", book="O-ManBlock", formation=62, ratings=[7, 4, 1]))
        self.assertEqual(self.facade.playcalling_context()["formations"][0]["ratings"], (7, 4, 1))
        self.facade.playcalling_predict(self.facade.playcalling_context(), "offense", rows)
        self.assertEqual(len(self.backend.calls), 2)
        project = self.facade.session.save_project(self.root / "calls.apf2k8mod")
        with zipfile.ZipFile(project) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            self.assertNotIn(self.backend.initial.books["O-ManBlock"], b"".join(archive.read(n) for n in archive.namelist()))
        self.facade.undo()
        self.assertFalse(self.facade.session.modifications)
        self.assertEqual(self.facade.session.load_project(project), 1)
        self.assertEqual(self.facade.playcalling_context()["formations"][0]["ratings"], (7, 4, 1))

    def test_all_levers_are_replayable_events(self):
        edits = [dict(kind="ratings", book="O-ManBlock", formation=62, ratings=[6, 5, 4]),
                 dict(kind="play_rating", book="O-ManBlock", formation=62, play=10, value=0),
                 dict(kind="categories", book="O-ManBlock", formation=62, primary=4, secondary=[4]),
                 dict(kind="retire", book="O-ManBlock", category=3),
                 dict(kind="tendency", team=0, value=72), dict(kind="master_row", category=12, row=13),
                 dict(kind="master_roles", category=0, roles=[9]*11),
                 dict(kind="remove", book="O-ManBlock", formation=63)]
        for request in edits:
            self.stage(request)
        events = self.facade._playcalling.events(self.facade.session)
        self.assertEqual(len(events), len(edits))
        context = self.facade.playcalling_context()
        self.assertEqual(context["tendency"], 72)
        self.assertEqual(context["categories"][12].row, 13)
        self.assertEqual(context["categories"][0].roles, ("Wide receiver",)*11)
        self.assertEqual(len(context["formations"]), 1)
        self.assertTrue(self.facade.undo())
        self.assertEqual(len(self.facade.playcalling_context()["formations"]), 2)

    def test_single_and_all_clone_plans_preserve_shared_donor(self):
        for every in (False, True):
            with self.subTest(every=every):
                plan = self.facade.playcalling_plan("offense", None if every else 0, None if every else "USER-o")
                self.assertEqual(len(plan["assignments"]), 24 if every else 1)
                self.stage(plan)
                context = self.facade.playcalling_context()
                self.assertEqual(context["book"], "Team 0 O")
                self.assertFalse(context["sharing"])
                self.stage(dict(kind="ratings", book="Team 0 O", formation=62, ratings=[7, 7, 7]))
                state = self.facade.playcalling_context()["state"]
                self.assertEqual(state.books["O-ManBlock"], self.backend.initial.books["O-ManBlock"])
                self.facade.revert_all()

    def test_warning_refusal_and_stale_reviews(self):
        self.backend.holes = True
        request = dict(kind="remove", book="O-ManBlock", formation=62)
        for callers in ("cpu", "unclassified", "non_cpu"):
            self.backend.lineup_callers = callers
            review = self.facade.playcalling_review(request)
            self.assertEqual(review["refused"], callers != "non_cpu")
            self.assertEqual(review["event"]["coverage"]["8"], [])
            self.assertEqual(review["retired_names"], ["Personnel 3"])
            if review["refused"]:
                with self.assertRaisesRegex((ValueError, ValidationError), "Cannot safely retire"):
                    self.facade.stage_playcalling(review)
        review = self.facade.playcalling_review(request)
        self.stage(dict(kind="tendency", team=0, value=60))
        with self.assertRaisesRegex((ValueError, ValidationError), "Project changed"):
            self.facade.stage_playcalling(review)

    def test_audibles_and_defense_contract(self):
        self.stage(dict(kind="audibles", book="O-ManBlock"))
        context = self.facade.playcalling_context(0, "defense")
        result = self.facade.playcalling_predict(context, "defense", [("Ace", {"offense_category_row": 2, "yards_to_goal": 40})])
        self.assertEqual(result[0][1].requested_row, 13)
        self.assertEqual(self.backend.calls[-1], ("defense", 2, 40, 256))

    def test_invalid_recipes_and_tampered_payload_fail_closed(self):
        for request in (dict(kind="ratings", book="O-ManBlock", formation=62, ratings=[8, 0, 0]),
                        dict(kind="tendency", team=0, value=True), dict(kind="unknown")):
            with self.assertRaises((ValueError, ValidationError)):
                self.facade.playcalling_review(request)
        self.stage(dict(kind="tendency", team=0, value=60))
        modification = self.facade.session.modifications[0]
        modification.replacement_path.write_bytes(b"{}")
        with self.assertRaisesRegex((ValueError, ValidationError), "changed after staging"):
            self.facade.playcalling_context()


if __name__ == "__main__":
    unittest.main()
