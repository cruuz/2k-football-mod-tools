"""b77 / a2: the handedness apply step. No real-world handedness appears here: every answer below is a test fixture.

Retail-free classes check the answer rules and the bit write. DiscRouteTests run the three routes on the shipped
SOFTDRINK 2K28 v0.5 disc (skipped without it): the native write to main.ROST and to a moment team file, the Studio
roster-edits document for the main roster, and the CSV edit for an authored moment team.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from tools.b77 import a2_handedness as ah  # noqa: E402

RETAIL_ISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
V05_DISC = Path(os.environ.get("B77_V05_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso"))
FIXTURE_SOURCE = ["https://example.invalid/fixture-not-a-source"]


def fake_list():
    rows = []
    for i, (name, position, bit) in enumerate((("Ann Alpha", "QB", 1), ("Bob Beta", "K", 0), ("Cy Gamma", "P", 1))):
        first, last = name.split()
        rows.append(dict(id=f"main:primary:{i}", scope="main_roster_2026", name=name, first=first, last=last,
                         position=position, team="Test Team", hand=rr.HANDS[bit], hand_bit=bit,
                         record=dict(pool="primary", index=i, record_offset=100 * i, hand_byte_offset=32 + 100 * i + 24,
                                     mask=2)))
    return dict(schema=ah.LIST_SCHEMA, players=rows)


class AnswerRuleTests(unittest.TestCase):
    def test_noah_defaults_require_the_exact_rows_decision_and_right(self):
        ident = "main:primary:136"
        row = dict(fake_list()["players"][0], id=ident, name="Ryan Eckley", position="P", hand="Left", hand_bit=0)
        rows = {ident: row}
        good = dict(id=ident, hand="Right", sources=[ah.DECISION_SOURCE], basis=ah.DEFAULT_RIGHT,
                    decision_source=ah.DECISION_SOURCE)
        wrap = lambda item: dict(schema=ah.ANSWERS_SCHEMA, answers=[item])
        self.assertEqual(ah.read_answers(wrap(good), rows)[ident][0], 1)
        for bad in (dict(good, hand="Left"), dict(good, basis="guess"), dict(good, decision_source="Noah"),
                    dict(good, sources=FIXTURE_SOURCE), {k: v for k, v in good.items() if k != "basis"}):
            with self.subTest(bad=bad), self.assertRaises(ah.HandednessError):
                ah.read_answers(wrap(bad), rows)
        for wrong in (dict(row, name="Somebody Else"), dict(row, position="QB"), dict(row, hand_bit=1)):
            with self.assertRaises(ah.HandednessError):
                ah.read_answers(wrap(good), {ident: wrong})
        with self.assertRaises(ah.HandednessError):
            ah.read_answers(wrap(dict(good, id="main:primary:0")), {"main:primary:0": row})

    def test_final_json_and_answers_agree_on_twelve_estimate_defaults(self):
        final = json.loads((ROOT / "data/HANDEDNESS_FINAL.json").read_text())
        answers = json.loads((ROOT / "data/nfl2k5_handedness_answers.json").read_text())["answers"]
        defaults = [p for p in final["players"] if p.get("basis") == ah.DEFAULT_RIGHT]
        self.assertEqual(len(defaults), 12)
        self.assertEqual({i for p in defaults for i in p["applied_row_ids"]}, set(ah.DEFAULT_RIGHT_ROWS))
        self.assertTrue(all(p["tier"] == "E" and p["hand"] == "Right" and p["apply"] and
                            p["decision_source"] == ah.DECISION_SOURCE for p in defaults))
        self.assertEqual({a["id"] for a in answers if a.get("basis") == ah.DEFAULT_RIGHT}, set(ah.DEFAULT_RIGHT_ROWS))

    def test_every_answer_needs_a_known_id_a_hand_and_an_https_source(self):
        _doc, rows = ah.read_player_list(fake_list())
        good = dict(id="main:primary:0", hand="Left", sources=FIXTURE_SOURCE)
        wrap = lambda *items: dict(schema=ah.ANSWERS_SCHEMA, answers=list(items))        # noqa: E731
        self.assertEqual(ah.read_answers(wrap(good), rows), {"main:primary:0": (0, FIXTURE_SOURCE, "")})
        for bad in (dict(good, id="main:primary:9"), dict(good, hand="left"), dict(good, hand=0),
                    {k: v for k, v in good.items() if k != "sources"}, dict(good, sources=[]),
                    dict(good, sources=["http://insecure.example/x"]), dict(good, sources=["not a url"]),
                    dict(good, name="Somebody Else"), dict(good, position="K")):
            with self.subTest(bad=bad), self.assertRaises(ah.HandednessError):
                ah.read_answers(wrap(bad), rows)
        with self.assertRaises(ah.HandednessError):
            ah.read_answers(wrap(good, good), rows)                                  # two answers for one player
        with self.assertRaises(ah.HandednessError):
            ah.read_answers(dict(schema="other", answers=[]), rows)

    def test_only_answers_that_differ_from_the_disc_are_changes(self):
        _doc, rows = ah.read_player_list(fake_list())
        answers = ah.read_answers(dict(schema=ah.ANSWERS_SCHEMA, answers=[
            dict(id="main:primary:0", hand="Right", sources=FIXTURE_SOURCE),          # already Right
            dict(id="main:primary:1", hand="Right", sources=FIXTURE_SOURCE)]), rows)  # Left -> Right
        self.assertEqual([(r["id"], b) for r, b in ah.changes(rows, answers)], [("main:primary:1", 1)])

    def test_the_bit_write_touches_bit_1_and_nothing_else(self):
        for value in range(256):
            for bit in (0, 1):
                buffer = bytearray([value])
                changed = ah.set_hand_bit(buffer, 0, bit)
                self.assertEqual(buffer[0] & ~2 & 0xFF, value & ~2 & 0xFF)
                self.assertEqual((buffer[0] >> 1) & 1, bit)
                self.assertEqual(changed, ((value >> 1) & 1) != bit)
        with self.assertRaises(ah.HandednessError):
            ah.set_hand_bit(bytearray(1), 0, 2)

    def test_the_location_matches_the_record_codec(self):
        field = rr.FIELD_BY_NAME["hand"]
        self.assertEqual((field.offset, field.shift, field.width), (0x18, 1, 1))
        self.assertEqual(ah.MASK, 1 << field.shift)


@unittest.skipUnless(RETAIL_ISO.is_file() and V05_DISC.is_file(), "the private retail and v0.5 disc images are required")
class DiscRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.b77 import a2_player_list as lister
        cls.document = lister.build(V05_DISC, RETAIL_ISO)
        _doc, cls.rows = ah.read_player_list(cls.document)
        with rr._outer_image()(V05_DISC) as image:
            cls.main = image.read_entry(5)
            by_id = {e.name_id: e for e in image.entries}
            cls.team_file = image.read_entry(by_id[mm.name_id("h-13-2023-chiefs-9.iff")].index)

    def row(self, ident):
        return self.rows[ident]

    def find(self, **match):
        hits = [r for r in self.rows.values() if all(r.get(k) == v for k, v in match.items())]
        self.assertEqual(len(hits), 1, match)
        return hits[0]

    def answers_for(self, *pairs):
        return ah.read_answers(dict(schema=ah.ANSWERS_SCHEMA, answers=[
            dict(id=ident, hand=hand, sources=FIXTURE_SOURCE) for ident, hand in pairs]), self.rows)

    def test_list_matches_the_disc_and_every_location_points_at_the_bit(self):
        self.assertEqual(self.document["counts"]["main_roster_2026"]["K"], {"Left": 27, "Right": 32})
        for row in self.rows.values():
            raw = self.main if row["scope"] == "main_roster_2026" else None
            if raw is None:
                continue
            self.assertEqual((raw[row["record"]["hand_byte_offset"]] >> 1) & 1, row["hand_bit"], row["id"])
        butker = self.find(scope="main_roster_2026", name="Harrison Butker")
        self.assertEqual((butker["position"], butker["hand"], butker["retail_slot_occupant"]["name"]),
                         ("K", "Left", "Morten Andersen"))

    def test_native_write_to_main_roster_changes_only_the_listed_bits(self):
        butker = self.find(scope="main_roster_2026", name="Harrison Butker")
        mahomes = self.find(scope="main_roster_2026", name="Patrick Mahomes")
        answers = self.answers_for((butker["id"], "Right"), (mahomes["id"], "Left"))     # fixtures, not data
        rows = [butker, mahomes]
        out, receipt = ah.apply_to_resource(self.main, rows, answers)
        self.assertEqual((receipt["bytes_changed"], len(out)), (2, len(self.main)))
        after = {(p.pool, p.index): p for p in rr.RosterDocument(out[32:]).players}
        before = {(p.pool, p.index): p for p in rr.RosterDocument(self.main[32:]).players}
        for key, player in after.items():
            expected = dict(before[key].record.values)
            if key == ("primary", butker["record"]["index"]):
                expected["hand"] = 1
            if key == ("primary", mahomes["record"]["index"]):
                expected["hand"] = 0
            self.assertEqual(player.record.values, expected, key)
        again, replay = ah.apply_to_resource(out, [dict(r, hand=rr.HANDS[1 - r["hand_bit"]], hand_bit=1 - r["hand_bit"])
                                                   for r in rows], answers)
        self.assertEqual((again, replay["bytes_changed"]), (out, 0))                     # idempotent against a fresh list

    def test_a_stale_list_or_wrong_player_is_refused(self):
        butker = self.find(scope="main_roster_2026", name="Harrison Butker")
        answers = self.answers_for((butker["id"], "Right"))
        for stale in (dict(butker, first="Somebody", name="Somebody Butker"), dict(butker, hand_bit=1, hand="Right"),
                      dict(butker, position="P"),
                      dict(butker, record=dict(butker["record"], record_offset=butker["record"]["record_offset"] + 84,
                                               hand_byte_offset=butker["record"]["hand_byte_offset"] + 84))):
            with self.subTest(stale=stale["name"] + stale["position"] + str(stale["hand_bit"])):
                with self.assertRaises(ah.HandednessError):
                    ah.apply_to_resource(self.main, [stale], answers)

    def test_studio_roster_edits_route_agrees_with_the_native_route(self):
        butker = self.find(scope="main_roster_2026", name="Harrison Butker")
        mahomes = self.find(scope="main_roster_2026", name="Patrick Mahomes")
        answers = self.answers_for((butker["id"], "Right"), (mahomes["id"], "Left"))
        document = ah.main_roster_edits(self.rows, answers)
        self.assertEqual([(e["last"], e["fields"]) for e in document["edits"]],
                         [("Butker", {"hand": 1}), ("Mahomes", {"hand": 0})] if document["edits"][0]["last"] == "Butker"
                         else [("Mahomes", {"hand": 0}), ("Butker", {"hand": 1})])
        body, receipt = rr.apply_body(self.main[32:], document)
        native, _ = ah.apply_to_resource(self.main, [butker, mahomes], answers)
        studio = {(p.pool, p.index): p.record.values for p in rr.RosterDocument(body).players}
        direct = {(p.pool, p.index): p.record.values for p in rr.RosterDocument(native[32:]).players}
        self.assertEqual(studio, direct)
        existing = dict(schema=rr.EDITS_SCHEMA, edits=[dict(pool="primary", index=butker["record"]["index"], last="Butker",
                                                           fields={"speed": 50})])
        merged = ah.merge_roster_edits(existing, document)
        self.assertEqual(len(merged["edits"]), 2)
        self.assertEqual(merged["edits"][0]["fields"], {"speed": 50, "hand": 1})
        with self.assertRaises(ah.HandednessError):
            ah.merge_roster_edits(dict(existing, edits=[dict(existing["edits"][0], last="Other")]), document)

    def test_native_write_to_a_moment_team_file(self):
        mahomes = self.find(scope="moment_roster", name="Patrick Mahomes", team="Kansas City Chiefs '23")
        answers = self.answers_for((mahomes["id"], "Left"))
        out, receipt = ah.apply_to_resource(self.team_file, [mahomes], answers)
        self.assertEqual((receipt["bytes_changed"], len(out)), (1, len(self.team_file)))
        doc = rr.RosterDocument(out[32:32 + struct.unpack_from("<I", out, 4)[0]])
        hand = {p.index: p.record.values["hand"] for p in doc.players}
        self.assertEqual(hand[mahomes["record"]["index"]], 0)

    def test_authored_csv_route_changes_one_cell_and_the_compiler_writes_it(self):
        mahomes = self.find(scope="moment_roster", name="Patrick Mahomes", team="Kansas City Chiefs '23")
        answers = self.answers_for((mahomes["id"], "Left"))
        with tempfile.TemporaryDirectory() as folder:
            teams = Path(folder) / "teams"
            shutil.copytree(mm.TEAMS_DIR, teams)
            updates = ah.authored_csv_updates(self.rows, answers, teams)
            self.assertEqual([p.name for p in updates], ["chiefs_2023.csv"])
            path = teams / "chiefs_2023.csv"
            old, new = path.read_bytes().decode("utf-8"), updates[path]
            changed = [i for i, (a, b) in enumerate(zip(old.splitlines(), new.splitlines())) if a != b]
            self.assertEqual((len(old.splitlines()), changed), (len(new.splitlines()), [mahomes["record"]["index"] + 1]))
            old_cells = next(csv.reader([old.splitlines()[changed[0]]]))
            new_cells = next(csv.reader([new.splitlines()[changed[0]]]))
            self.assertEqual([(a, b) for a, b in zip(old_cells, new_cells) if a != b], [("Right", "Left")])
            self.assertEqual(new.count("\r"), old.count("\r"))
            path.write_bytes(new.encode("utf-8"))
            data = mm.Data.load(mm.MOMENTS_JSON, teams)
            rows = data.rosters["chiefs_2023"]
            self.assertEqual(rows[mahomes["record"]["index"]]["hand"], "Left")
            self.assertEqual([r["hand"] for i, r in enumerate(rows) if i != mahomes["record"]["index"]],
                             [r["hand"] for i, r in enumerate(mm.Data.load().rosters["chiefs_2023"])
                              if i != mahomes["record"]["index"]])


@unittest.skipUnless(V05_DISC.is_file() and RETAIL_ISO.is_file(), "the v0.5 disc and the retail disc are private inputs")
class FinalAnswersTests(unittest.TestCase):
    """The sourced answers (data/nfl2k5_handedness_answers.json, from reports/a2_swarm/HANDEDNESS_FINAL.json tiers A and B)
    on the v0.5 files: the file repair, and the Studio-side source change they produced."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_historic_styles as hs
        from mod_editor.core import nfl2k5_music_archive as archive
        from tools.b77 import a2_player_list as lister
        cls.document = lister.build(V05_DISC, RETAIL_ISO)
        _doc, cls.rows = ah.read_player_list(cls.document)
        cls.answers = ah.read_answers(ROOT / "data/nfl2k5_handedness_answers.json", cls.rows)
        cls.todo = ah.changes(cls.rows, cls.answers)
        cls.names = sorted({r["record"]["resource"] for r, _b in cls.todo})
        cls.inputs = {}
        with archive.Disc(V05_DISC, descriptors=()) as disc:
            target = hs.Target(disc)
            for name in cls.names:
                cls.inputs[name] = target.get(identity=hs.ROSTER_OUTER_ID) if name == ah.MAIN_RESOURCE else target.get(name)

    def test_the_answers_are_sourced_and_cover_the_known_cases(self):
        self.assertEqual(len(self.answers), 459)
        for ident, (bit, sources, note) in self.answers.items():
            self.assertTrue(sources == [ah.DECISION_SOURCE] if ident in ah.DEFAULT_RIGHT_ROWS else
                            sources and all(u.startswith("https://") for u in sources), ident)
            if ident in ah.DEFAULT_RIGHT_ROWS:
                self.assertIn("Default Right by Noah", note)
            else:
                self.assertRegex(note, r"^tier [AB] ", ident)
        by_name = {}
        for ident, (bit, _s, _n) in self.answers.items():
            by_name.setdefault((self.rows[ident]["name"], self.rows[ident]["position"]), set()).add(rr.HANDS[bit])
        self.assertEqual(by_name[("Harrison Butker", "K")], {"Right"})        # the bug Noah saw
        self.assertEqual(by_name[("Tua Tagovailoa", "QB")], {"Left"})
        self.assertEqual(by_name[("Ben Sauls", "K")], {"Left"})
        self.assertEqual(by_name[("Ken Walter", "P")], {"Left"})
        self.assertTrue(all(len(v) == 1 for v in by_name.values()))            # one hand per person across rows

    def test_47_rows_change_in_27_files(self):
        self.assertEqual((len(self.todo), len(self.names)), (47, 27))
        self.assertEqual(sum(1 for r, _b in self.todo if r["scope"] == "main_roster_2026"), 20)

    def test_file_repair_changes_only_the_hand_bits_and_replays(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "in").mkdir()
            for name, raw in self.inputs.items():
                (folder / "in" / name).write_bytes(raw)
            receipt = ah.native_repair(folder / "in", folder / "out", self.document, self.rows, self.answers)
            self.assertEqual((receipt["rows_changed"], sorted(receipt["resources_written"])), (47, self.names))
            for name, raw in self.inputs.items():
                new = (folder / "out" / name).read_bytes()
                diff = [i for i in range(len(raw)) if raw[i] != new[i]]
                self.assertEqual(len(diff), receipt["files"][name]["bytes_changed"])
                self.assertTrue(all(raw[i] ^ new[i] == 0x02 for i in diff))
            after = {p.index: p.record.values["hand"] for p in rr.RosterDocument(
                (folder / "out" / ah.MAIN_RESOURCE).read_bytes()[32:]).players if p.pool == "primary"}
            for row, bit in self.todo:
                if row["scope"] == "main_roster_2026":
                    self.assertEqual(after[row["record"]["index"]], bit, row["name"])
            butker = [r for r, _b in self.todo if r["name"] == "Harrison Butker"][0]
            self.assertEqual(after[butker["record"]["index"]], 1)
            # replay: the repaired files are only accepted through a manifest naming them (a stacked input), then identical
            manifest = {"files": {name: v["after_sha256"] for name, v in receipt["files"].items()}}
            (folder / "accept.json").write_text(__import__("json").dumps(manifest))
            accepted = ah.accepted_input_hashes(folder / "accept.json", self.document)
            again = ah.native_repair(folder / "out", folder / "out2", self.document, self.rows, self.answers, accepted)
            self.assertEqual(sorted(again["resources_written"]), self.names)
            for name in self.names:                                              # replay: nothing left to change, bytes equal
                self.assertEqual(again["files"][name]["bytes_changed"], 0, name)
                self.assertEqual((folder / "out2" / name).read_bytes(), (folder / "out" / name).read_bytes(), name)
            with self.assertRaises(ah.HandednessError):                          # the repaired file is not a v0.5 input
                ah.native_repair(folder / "out", folder / "out3", self.document, self.rows, self.answers)
            (folder / "in" / ah.MAIN_RESOURCE).write_bytes(self.inputs[ah.MAIN_RESOURCE][:-1]
                                                             + bytes([self.inputs[ah.MAIN_RESOURCE][-1] ^ 1]))
            with self.assertRaises(ah.HandednessError):                          # a foreign main roster
                ah.native_repair(folder / "in", folder / "out4", self.document, self.rows, self.answers)

    def test_studio_source_change_agrees_with_the_answers(self):
        import json
        from tools.b77 import data_sync
        spec = json.loads((ROOT / ah.SPEC_PATH).read_text(encoding="utf-8"))
        expected = ah.authored_answers(self.rows, self.answers)
        expected.update({ah.hand_key(self.rows[i]["first"], self.rows[i]["last"], self.rows[i]["position"]): "Right"
                         for i in ah.DEFAULT_RIGHT_ROWS})
        self.assertEqual(spec["handedness"]["answers"], expected)
        self.assertEqual(spec["handedness"]["answers"]["Tony Graziani|QB"], "Left")
        # every sourced authored player carries his answer in the team CSV the compiler reads
        data = mm.Data.load()
        for ident, (bit, _s, _n) in self.answers.items():
            row = self.rows[ident]
            if row["scope"] == "moment_roster" and row.get("team_key"):
                self.assertEqual(data.rosters[row["team_key"]][row["record"]["index"]]["hand"], rr.HANDS[bit], ident)
        # the 2026 main-roster document carries every answered main-roster row and applies to the v0.5 roster
        document = json.loads((ROOT / ah.EDITS_PATH).read_text(encoding="utf-8"))
        main_answers = {i for i in self.answers if self.rows[i]["scope"] == "main_roster_2026"}
        self.assertEqual(len(document["edits"]), len(main_answers))
        body, _receipt = rr.apply_body(self.inputs[ah.MAIN_RESOURCE][32:], document)
        hands = {(p.pool, p.index): p.record.values["hand"] for p in rr.RosterDocument(body).players}
        for ident in main_answers:
            self.assertEqual(hands[("primary", self.rows[ident]["record"]["index"])], self.answers[ident][0], ident)
        self.assertEqual(data_sync.sync(ROOT), {})                              # the manifests are in step with spec and CSVs
        for path, text in ah.apply_source(ROOT, self.rows, self.answers).items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, str(path))

    def test_a1x_stack_changes_exactly_twelve_bits_and_refuses_stale_identity(self):
        previous = {i: v for i, v in self.answers.items() if i not in ah.DEFAULT_RIGHT_ROWS}
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            incoming = folder / "a1x"
            incoming.mkdir()
            accepted = {}
            for name, raw in self.inputs.items():
                old, _ = ah.apply_to_resource(raw, [r for r in self.rows.values() if r["record"]["resource"] == name], previous)
                (incoming / name).write_bytes(old)
                accepted[name] = {ah.sha(old)}
            receipt = ah.native_repair(incoming, folder / "out", self.document, self.rows, self.answers, accepted)
            self.assertEqual(sum(f["bytes_changed"] for f in receipt["files"].values()), 12)
            changed_ids = {c["id"] for f in receipt["files"].values() for c in f["changed"]}
            self.assertEqual(changed_ids, set(ah.DEFAULT_RIGHT_ROWS))
            for name in self.names:
                before, after = (incoming / name).read_bytes(), (folder / "out" / name).read_bytes()
                allowed = {r["record"]["hand_byte_offset"] for i, r in self.rows.items()
                           if i in ah.DEFAULT_RIGHT_ROWS and r["record"]["resource"] == name}
                diff = {j for j in range(len(before)) if before[j] != after[j]}
                self.assertEqual(diff, allowed)
                self.assertTrue(all(before[j] ^ after[j] == 2 for j in diff))
            row = dict(self.rows["main:primary:136"], first="Foreign")
            with self.assertRaises(ah.HandednessError):
                ah.apply_to_resource(self.inputs[ah.MAIN_RESOURCE], [row], self.answers)
            with self.assertRaises(ah.HandednessError):
                ah.native_repair(incoming, folder / "out", self.document, self.rows, previous, accepted)

    def test_historic_studio_hand_cells_compile_only_the_nine_hand_bits(self):
        from mod_editor.core import nfl2k5_espn25_rosters as historic
        manifest, sheets = historic.dataset()
        with rr._outer_image()(RETAIL_ISO) as image:
            resources = {t["outer"]: image.read_entry(t["outer"]) for t in manifest["resources"]}
            for target in manifest["resources"]:
                name = target["filename"]
                ids = [i for i in ah.DEFAULT_RIGHT_ROWS if self.rows[i]["record"]["resource"] == name]
                if not ids:
                    continue
                cells = sheets[target["outer"]]
                template = image.read_entry(target["outer"])
                before_cells = [dict(c, hand="") for c in cells]
                before = historic.compile_resource(template, before_cells, manifest["colleges"])
                after = historic.compile_resource(template, cells, manifest["colleges"])
                offsets = {self.rows[i]["record"]["hand_byte_offset"] for i in ids}
                self.assertEqual({j for j in range(len(before)) if before[j] != after[j]}, offsets, name)
                self.assertTrue(all(before[j] ^ after[j] == 2 for j in offsets))
                self.assertEqual(historic.resource_status(after, target), "applied")
        compiled, _ = historic._compile_resources(resources)
        replay, _ = historic._compile_resources(compiled)
        self.assertEqual(replay, compiled)

    def test_q1_repair_commutes_on_all_touched_resources(self):
        import importlib.util
        q1_root = Path(os.environ.get("B77_Q1_ROOT", "/home/noah/2k-worktrees/b77-int"))
        if not (q1_root / "tools/b77/q1_repair.py").is_file():
            self.skipTest("q1 worktree required for the cross-job proof (B77_Q1_ROOT)")

        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

        old_path = list(sys.path)
        try:
            load("mod_editor.core.nfl2k5_qb_throw_power", q1_root / "mod_editor/core/nfl2k5_qb_throw_power.py")
            q1 = load("a2r_q1_repair", q1_root / "tools/b77/q1_repair.py")
        finally:
            sys.path[:] = old_path
        baseline = q1.load_baseline(q1_root / "data/nfl2k5_qb_throw_power_baseline_v05.json")
        by_id = {f["name_id"]: f for f in baseline["files"]}
        previous = {i: v for i, v in self.answers.items() if i not in ah.DEFAULT_RIGHT_ROWS}
        for name, raw in self.inputs.items():
            rows = [r for r in self.rows.values() if r["record"]["resource"] == name]
            raw, _ = ah.apply_to_resource(raw, rows, previous)  # a1x output in both orders
            entry = next(f for f in baseline["files"] if f["outer_index"] == 5) if name == ah.MAIN_RESOURCE else by_id[mm.name_id(name)]
            def power(value):
                return q1.repair_resource(value, entry, 4, 99, {name: {ah.sha(value)}}, False, name)[0]
            hand, _ = ah.apply_to_resource(raw, rows, self.answers)
            power_then_hand, _ = ah.apply_to_resource(power(raw), rows, self.answers)
            hand_then_power = power(hand)
            self.assertEqual(power_then_hand, hand_then_power, name)
            self.assertEqual(power(hand_then_power), hand_then_power, name)
            replay, _ = ah.apply_to_resource(hand_then_power, rows, self.answers)
            self.assertEqual(replay, hand_then_power, name)


if __name__ == "__main__":
    unittest.main()
