"""b77 q1: every quarterback's Throw Power up a bit (GOAL R1); synthetic rosters, no game bytes.

Throw Power is record byte +0x38 (pass_arm_strength).  The tests pin the field offset to the codec, the rule
(min(cap, old + add), never lower, QB records only, blank spares untouched), the roster-edits directive, the image
step, the native repair (hashes, idempotence, stacked inputs, partial-run refusal) and the committed v0.5 baseline.
The one test that reads the real v0.5 disc runs only when B77_Q1_DISC names it (it takes about a minute).
"""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import mod_build as build  # noqa: E402
from mod_editor.core import nfl2k5_qb_throw_power as qp  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402
import test_nfl2k5_roster_records as fixtures  # noqa: E402
from tools.b77 import q1_repair as repair  # noqa: E402

TEMPLATE_ARMS = (95, 96, 53, 50)         # the retail QB templates: pos*4+v and pos*4+v+2 bracket a rolled prospect


def body_with(arms: dict[int, int], *, blank_qb: bool = True, templates=TEMPLATE_ARMS) -> bytes:
    """The synthetic roster with chosen arms for primary players, four QB templates and one blank QB spare."""
    body = bytearray(fixtures.synthetic_body())
    obj = rr.OBJ_OFF
    count = struct.unpack_from("<I", body, obj)[0]
    for index, arm in arms.items():
        body[fixtures.PLAYERS_OFF + index * rr.PLAYER_SIZE + qp.BYTE_IN_RECORD] = arm
    secondary = fixtures.PLAYERS_OFF + count * rr.PLAYER_SIZE
    struct.pack_into("<I", body, obj + 8, len(templates))
    for i, arm in enumerate(templates):
        at = secondary + i * rr.PLAYER_SIZE
        body[at + 0x35] = 0
        for rating in range(0x36, 0x52):
            body[at + rating] = 60
        body[at + qp.BYTE_IN_RECORD] = arm
    if blank_qb:                                           # primary slot 7 (the draft prospect) becomes a blank spare QB
        at = fixtures.PLAYERS_OFF + 7 * rr.PLAYER_SIZE
        body[at + 0x35] = 0
        for rating in range(0x36, 0x52):
            body[at + rating] = 0
    return bytes(body)


def resource(body: bytes) -> bytes:
    return fixtures.synthetic_resource(body)


ARMS = {0: 97, 1: 80, 2: 70, 3: 75, 4: 90, 5: 40, 6: 99}     # Manning QB, Harrison WR, James HB, Vick QB, ...


class FieldTests(unittest.TestCase):
    def test_throw_power_is_record_byte_0x38_read_as_rating_over_100(self) -> None:
        self.assertEqual(qp.FIELD, "pass_arm_strength")
        self.assertEqual(rr.RATING_OFFSETS["pass_arm_strength"], 0x38)
        self.assertEqual(qp.BYTE_IN_RECORD, 0x38)
        self.assertEqual(rr.FIELD_BY_NAME["pass_arm_strength"].offset, 0x38)
        self.assertEqual((rr.FIELD_BY_NAME["pass_arm_strength"].size, rr.FIELD_BY_NAME["pass_arm_strength"].width), (1, 8))
        self.assertEqual(rr.POSITIONS[qp.QB_CODE], "QB")
        for scheme in ("retail", "edge", "one_pool"):
            self.assertEqual(rr.position_code("QB", scheme), qp.QB_CODE)
        self.assertEqual(qp.DEFAULT_CAP, rr.RATING_MAX)

    def test_the_rule(self) -> None:
        self.assertEqual([qp.raised(v, 4, 99) for v in (0, 50, 94, 95, 96, 99)], [4, 54, 98, 99, 99, 99])
        self.assertEqual(qp.raised(100, 4, 99), 100)               # already past the cap: never lowered
        self.assertEqual(qp.raised(120, 4, 99), 120)
        self.assertEqual(qp.raised(70, 0, 99), 70)
        values = list(range(0, 100))
        mapped = [qp.raised(v, 4, 99) for v in values]
        self.assertEqual(mapped, sorted(mapped))                    # order preserved (ties only at the cap)
        self.assertTrue(all(b > a for a, b in zip(mapped[:95], mapped[1:96])))
        self.assertEqual(sum(1 for v in values if qp.raised(v, 4, 99) == 99), 5)    # 95..99 tie at 99

    def test_generator_draw_range_moves_with_both_templates(self) -> None:
        """FUN_002BE6F0 -> 0xE6780 rolls each rating between two templates: value = b + r * (a - b), r in [0, 1)."""
        def draws(a: int, b: int) -> list[float]:
            return [b + r / 100 * (a - b) for r in range(100)]
        for high, low in ((95, 53), (96, 50)):
            before = draws(high, low)
            after = draws(qp.raised(high, 4, 99), qp.raised(low, 4, 99))
            self.assertEqual((round(min(after) - min(before), 6), max(after) <= 99), (4, True))
            self.assertGreater(sum(after) / 100, sum(before) / 100 + 3)


class DirectiveTests(unittest.TestCase):
    def test_defaults_and_refusals(self) -> None:
        self.assertEqual(qp.normalise_directive({}), {"add": 4, "cap": 99, "scope": "all"})
        self.assertEqual(qp.normalise_directive({"add": 3, "scope": "main"}), {"add": 3, "cap": 99, "scope": "main"})
        for bad in ({"add": -1}, {"add": 4.5}, {"add": True}, {"add": 31}, {"cap": 0}, {"cap": 128}, {"scope": "some"},
                    {"extra": 1}, "4", None, [4]):
            with self.assertRaises(qp.QbThrowPowerError, msg=repr(bad)):
                qp.normalise_directive(bad)

    def test_the_roster_edits_reader_checks_the_directive(self) -> None:
        document = {"schema": rr.EDITS_SCHEMA, "edits": [], "qb_throw_power": {"add": 4}}
        self.assertEqual(rr.read_edits(document)["qb_throw_power"], {"add": 4})
        with self.assertRaises(qp.QbThrowPowerError):
            rr.read_edits({**document, "qb_throw_power": {"add": 99}})
        self.assertIsNone(qp.directive_of({"schema": rr.EDITS_SCHEMA, "edits": []}))
        self.assertEqual(qp.directive_of(document), {"add": 4, "cap": 99, "scope": "all"})

    def test_merge_into_the_league_edits_keeps_everything_else(self) -> None:
        league = {"schema": rr.EDITS_SCHEMA, "name": "league", "edits": [{"pool": "primary", "index": 1, "fields": {"hand": 0}}]}
        merged = qp.merge_into_edits(league, {"add": 5})
        self.assertEqual(merged["edits"], league["edits"])
        self.assertEqual(merged["qb_throw_power"], {"add": 5, "cap": 99, "scope": "all"})
        self.assertNotIn("qb_throw_power", league)
        with self.assertRaises(qp.QbThrowPowerError):
            qp.merge_into_edits({"schema": "other", "edits": []})

    def test_the_shipped_directive_file_is_valid_and_default(self) -> None:
        document = json.loads((ROOT / "data" / "nfl2k5_qb_throw_power_roster_edits.json").read_text(encoding="utf-8"))
        self.assertEqual(rr.read_edits(document)["edits"], [])
        self.assertEqual(qp.directive_of(document), qp.DEFAULT_DIRECTIVE)


class ResourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = resource(body_with(ARMS))

    def test_only_qb_records_with_content_are_listed(self) -> None:
        rows = qp.quarterbacks(self.raw)
        self.assertEqual([(r["pool"], r["index"]) for r in rows],
                         [("primary", 0), ("primary", 3), ("secondary", 0), ("secondary", 1), ("secondary", 2), ("secondary", 3)])
        self.assertEqual([r["value"] for r in rows], [97, 75, 95, 96, 53, 50])
        for row in rows:
            self.assertEqual(self.raw[row["offset"]], row["value"])
            self.assertEqual((row["offset"] - qp.WRAPPER) % rr.PLAYER_SIZE,
                             (fixtures.PLAYERS_OFF + qp.BYTE_IN_RECORD) % rr.PLAYER_SIZE)

    def test_apply_changes_exactly_the_throw_power_bytes(self) -> None:
        new, changes = qp.apply_resource(self.raw, 4)
        diff = [i for i in range(len(self.raw)) if self.raw[i] != new[i]]
        self.assertEqual(diff, sorted(c["offset"] for c in changes))
        self.assertEqual(len(new), len(self.raw))
        self.assertEqual([(c["before"], c["after"]) for c in changes],
                         [(97, 99), (75, 79), (95, 99), (96, 99), (53, 57), (50, 54)])
        # the roster still parses and every non-QB and the blank spare are byte-identical
        document = rr.RosterDocument(new[qp.WRAPPER:])
        self.assertEqual([p.record.values["pass_arm_strength"] for p in document.players if p.pool == "primary"][:7],
                         [99, 80, 70, 79, 90, 40, 99])
        blank = [p for p in document.players if p.pool == "primary" and p.index == 7][0]
        self.assertFalse(any(blank.record.values[name] for name in rr.RATING_BYTE_ORDER))

    def test_templates_move_together_so_generated_classes_follow(self) -> None:
        new, _ = qp.apply_resource(self.raw, 4)
        arms = {(r["pool"], r["index"]): r["value"] for r in qp.quarterbacks(new)}
        self.assertEqual([arms[("secondary", i)] for i in range(4)], [99, 99, 57, 54])

    def test_add_zero_and_a_capped_roster_change_nothing(self) -> None:
        self.assertEqual(qp.apply_resource(self.raw, 0)[0], self.raw)
        capped = resource(body_with({0: 99, 3: 99}, templates=(99, 99, 99, 99)))
        self.assertEqual(qp.apply_resource(capped, 4), (capped, []))

    def test_foreign_resources_are_refused(self) -> None:
        with self.assertRaises(qp.QbThrowPowerError):
            qp.quarterbacks(b"NOPE" + bytes(0x400))
        self.assertFalse(qp.is_rost(b"ROST"))


class ImageTests(unittest.TestCase):
    def image(self, directory: Path) -> SyntheticXiso:
        return SyntheticXiso(directory, [(100 + i, b"DUMY" + bytes(256)) for i in range(5)] +
                             [(5, resource(body_with(ARMS))), (6, resource(body_with({0: 60, 3: 91}, templates=(70, 70, 40, 40)))),
                              (7, b"TAIL" + bytes(256))], pack_sizes=(0x140000,), pack_sectors=(96,))

    def arms(self, path: Path) -> dict[int, list[int]]:
        out = {}
        with rr._outer_image()(path) as archive:
            for entry in archive.entries:
                raw = archive.read(entry.virtual_offset, entry.size)
                if qp.is_rost(raw):
                    out[entry.index] = [r["value"] for r in qp.quarterbacks(raw)]
        return out

    def test_scope_all_raises_every_rost_and_leaves_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.image(Path(tmp))
            before = Path(fixture.path).read_bytes()
            receipt = qp.apply_image(fixture.path, {"add": 4})
            self.assertEqual((receipt["status"], receipt["files_changed"], receipt["bytes_changed"]), ("applied", 2, 6 + 6))
            self.assertEqual(self.arms(fixture.path), {5: [99, 79, 99, 99, 57, 54], 6: [64, 95, 74, 74, 44, 44]})
            after = Path(fixture.path).read_bytes()
            self.assertEqual(len(after), len(before))
            changed = [i for i in range(len(before)) if before[i] != after[i]]
            self.assertEqual(len(changed), 12)                       # one byte per changed QB, nothing else
            self.assertTrue(after.count(b"DUMY") == before.count(b"DUMY") and after.count(b"TAIL") == before.count(b"TAIL"))

    def test_scope_main_leaves_team_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.image(Path(tmp))
            receipt = qp.apply_image(fixture.path, {"add": 4, "scope": "main"})
            self.assertEqual(receipt["files_changed"], 1)
            self.assertEqual(self.arms(fixture.path)[6], [60, 91, 70, 70, 40, 40])

    def test_it_matches_the_pure_function_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self.image(Path(tmp))
            expected = qp.apply_resource(resource(body_with(ARMS)), 4)[0]
            qp.apply_image(fixture.path, {"add": 4})
            with rr._outer_image()(fixture.path) as archive:
                entry = archive.entries[5]
                self.assertEqual(archive.read(entry.virtual_offset, entry.size), expected)


class BuildStepTests(unittest.TestCase):
    def test_the_build_applies_the_directive_after_the_roster_edits(self) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            fixture = ImageTests().image(root)
            stack.enter_context(patch.object(build, "inspect", return_value={"path": "unused", "container": "xiso"}))
            stack.enter_context(patch.object(build, "_xbe_bytes", side_effect=lambda path: b"XBE-retail"))
            stack.enter_context(patch.object(build, "_write_xbe_bytes", side_effect=lambda path, data: None))
            stack.enter_context(patch.object(build, "_check_playbook_scoring",
                                             return_value={"status": "applied", "books": 0, "faults": 0}))
            calls = []
            stack.enter_context(patch.object(rr, "apply", new=lambda path, *args, **kwargs: calls.append(path) or {"log": []}))
            edits = root / "edits.json"
            edits.write_text(json.dumps({"schema": rr.EDITS_SCHEMA, "edits": [], "qb_throw_power": {"add": 4}}), encoding="utf-8")
            target = root / "built.iso"
            receipt = build.build(build.BuildPlan(str(fixture.path), str(target), roster_edits=str(edits)))
            steps = [s["step"] for s in receipt["steps"]]
            self.assertEqual(steps, ["copy", "roster_edits", "qb_throw_power", "commentary_final"])  # i1: c2's final commentary pass runs after the last roster writer
            self.assertEqual(receipt["steps"][-2]["bytes_changed"], 12)
            self.assertEqual(ImageTests().arms(target)[5], [99, 79, 99, 99, 57, 54])
            self.assertEqual(ImageTests().arms(fixture.path)[5], [97, 75, 95, 96, 53, 50])     # the source copy is untouched

    def test_no_directive_no_step(self) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            fixture = ImageTests().image(root)
            stack.enter_context(patch.object(build, "inspect", return_value={"path": "unused", "container": "xiso"}))
            stack.enter_context(patch.object(build, "_xbe_bytes", side_effect=lambda path: b"XBE-retail"))
            stack.enter_context(patch.object(build, "_write_xbe_bytes", side_effect=lambda path, data: None))
            stack.enter_context(patch.object(build, "_check_playbook_scoring",
                                             return_value={"status": "applied", "books": 0, "faults": 0}))
            stack.enter_context(patch.object(rr, "apply", new=lambda path, *args, **kwargs: {"log": []}))
            edits = root / "edits.json"
            edits.write_text(json.dumps({"schema": rr.EDITS_SCHEMA, "edits": []}), encoding="utf-8")
            receipt = build.build(build.BuildPlan(str(fixture.path), str(root / "built.iso"), roster_edits=str(edits)))
            self.assertEqual([s["step"] for s in receipt["steps"]], ["copy", "roster_edits", "commentary_final"])  # i1: c2 final pass
            self.assertEqual(ImageTests().arms(root / "built.iso")[5], [97, 75, 95, 96, 53, 50])

    def test_a_bad_directive_stops_the_build_before_any_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            fixture = ImageTests().image(root)
            stack.enter_context(patch.object(build, "inspect", return_value={"path": "unused", "container": "xiso"}))
            stack.enter_context(patch.object(build, "_xbe_bytes", side_effect=lambda path: b"XBE-retail"))
            stack.enter_context(patch.object(build, "_write_xbe_bytes", side_effect=lambda path, data: None))
            stack.enter_context(patch.object(build, "_check_playbook_scoring",
                                             return_value={"status": "applied", "books": 0, "faults": 0}))
            edits = root / "edits.json"
            edits.write_text(json.dumps({"schema": rr.EDITS_SCHEMA, "edits": [], "qb_throw_power": {"add": 500}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                build.build(build.BuildPlan(str(fixture.path), str(root / "built.iso"), roster_edits=str(edits)))
            self.assertFalse((root / "built.iso").exists())


def baseline_for(files: dict[str, bytes], add: int = 4, cap: int = 99) -> dict:
    out = []
    for name, raw in files.items():
        index = qp.MAIN_OUTER_INDEX if name == "main.ROST" else int(name[6:10])
        rows = qp.quarterbacks(raw)
        after, changes = qp.apply_resource(raw, add, cap)
        out.append(dict(outer_index=index, name_id=1000 + index, name=name, size=len(raw), sha256=qp.sha256(raw),
                        sha256_after=qp.sha256(after), qb_count=len(rows), bytes_changed=len(changes),
                        quarterbacks=[{k: r[k] for k in ("pool", "index", "first", "last", "group", "offset", "value")}
                                      for r in rows]))
    return dict(schema=repair.BASELINE_SCHEMA, add=add, cap=cap, files=out)


class RepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.files = {"main.ROST": resource(body_with(ARMS)),
                      "outer_0150.ROST": resource(body_with({0: 60, 3: 91}, templates=(70, 70, 40, 40)))}
        self.baseline = baseline_for(self.files)
        self.input, self.output = root / "in", root / "out"
        self.input.mkdir()
        for name, raw in self.files.items():
            (self.input / name).write_bytes(raw)

    def run_repair(self, input_dir=None, output=None, **kwargs):
        return repair.native_repair(input_dir or self.input, output or self.output, baseline=self.baseline, **kwargs)

    def test_repair_writes_exactly_the_rule_and_a_receipt(self) -> None:
        receipt = self.run_repair()
        self.assertEqual(sorted(receipt["resources_written"]), ["main.ROST", "outer_0150.ROST"])
        self.assertEqual(receipt["bytes_changed"], 12)
        for name, raw in self.files.items():
            written = (self.output / name).read_bytes()
            self.assertEqual(written, qp.apply_resource(raw, 4)[0])
            info = receipt["files"][name]
            self.assertEqual((info["before_sha256"], info["after_sha256"]), (qp.sha256(raw), qp.sha256(written)))
            self.assertTrue(info["outside_scope_identical"])
            self.assertEqual(info["after_sha256"], next(f["sha256_after"] for f in self.baseline["files"] if f["name"] == name))
        self.assertTrue((self.output / "q1_receipt.json").is_file())

    def test_replay_is_identical_and_its_own_output_is_a_no_op(self) -> None:
        first = self.run_repair()
        self.run_repair()                                       # same output directory again: identical files accepted
        second = self.run_repair(input_dir=self.output, output=Path(self.tmp.name) / "out2")
        self.assertEqual((second["resources_written"], second["bytes_changed"]), ([], 0))
        self.assertTrue(all(f["already_applied"] for f in second["files"].values()))
        self.assertEqual(first["bytes_changed"], 12)

    def test_unexpected_input_hash_is_refused_unless_named_or_stacked(self) -> None:
        raw = bytearray(self.files["main.ROST"])
        raw[qp.WRAPPER + fixtures.PLAYERS_OFF + 4 * rr.PLAYER_SIZE + 0x18] ^= 0x02      # another job flips a hand bit
        (self.input / "main.ROST").write_bytes(bytes(raw))
        with self.assertRaisesRegex(repair.RepairError, "unexpected input hash"):
            self.run_repair()
        named = Path(self.tmp.name) / "accepted.json"
        named.write_text(json.dumps({"files": {"main.ROST": {"sha256": qp.sha256(bytes(raw))}}}), encoding="utf-8")
        receipt = self.run_repair(accepted=repair.accepted_hashes(named))
        self.assertFalse(receipt["files"]["main.ROST"]["stacked_input"])
        stacked = self.run_repair(output=Path(self.tmp.name) / "out3", allow_stacked=True)
        self.assertEqual(stacked["bytes_changed"], 12)
        out = (self.output / "main.ROST").read_bytes()
        diff = [i for i in range(len(raw)) if raw[i] != out[i]]
        self.assertTrue(all(i - qp.WRAPPER >= fixtures.PLAYERS_OFF and (i - qp.WRAPPER - fixtures.PLAYERS_OFF) % rr.PLAYER_SIZE == qp.BYTE_IN_RECORD
                            for i in diff))                      # the hand bit stays; only throw bytes differ

    def test_stacking_with_another_jobs_bits_commutes(self) -> None:
        """Another job's byte (a1x's hand bit, +0x18 mask 0x02) and ours are disjoint, in either order."""
        hand = qp.WRAPPER + fixtures.PLAYERS_OFF + 3 * rr.PLAYER_SIZE + 0x18
        theirs = bytearray(self.files["main.ROST"])
        theirs[hand] ^= 0x02
        ours_first = bytearray(qp.apply_resource(self.files["main.ROST"], 4)[0])
        ours_first[hand] ^= 0x02
        (self.input / "main.ROST").write_bytes(bytes(theirs))
        self.run_repair(allow_stacked=True)
        self.assertEqual((self.output / "main.ROST").read_bytes(), bytes(ours_first))

    def test_a_partly_applied_file_is_refused(self) -> None:
        new, changes = qp.apply_resource(self.files["main.ROST"], 4)
        half = bytearray(self.files["main.ROST"])
        half[changes[0]["offset"]] = changes[0]["after"]
        (self.input / "main.ROST").write_bytes(bytes(half))
        with self.assertRaisesRegex(repair.RepairError, "partly applied"):
            self.run_repair(allow_stacked=True)

    def test_a_new_qb_unknown_to_the_baseline_is_raised_too(self) -> None:
        body = bytearray(body_with(ARMS))
        at = fixtures.PLAYERS_OFF + 5 * rr.PLAYER_SIZE                  # a stacked job turns the free agent into a QB
        body[at + 0x35] = 0
        (self.input / "main.ROST").write_bytes(resource(bytes(body)))
        receipt = self.run_repair(allow_stacked=True)
        self.assertEqual(receipt["files"]["main.ROST"]["states"].get("new"), 1)
        self.assertEqual(receipt["files"]["main.ROST"]["bytes_changed"], 7)

    def test_scope_main_and_missing_files(self) -> None:
        receipt = self.run_repair(scope="main")
        self.assertEqual(receipt["resources_written"], ["main.ROST"])
        (self.input / "outer_0150.ROST").unlink()
        receipt = self.run_repair(output=Path(self.tmp.name) / "o4")
        self.assertEqual(receipt["resources_missing"], ["outer_0150.ROST"])

    def test_a_different_existing_output_is_never_replaced(self) -> None:
        self.output.mkdir()
        (self.output / "main.ROST").write_bytes(b"something else")
        with self.assertRaisesRegex(repair.RepairError, "refusing to replace"):
            self.run_repair()

    def test_input_and_output_must_differ(self) -> None:
        with self.assertRaises(repair.RepairError):
            self.run_repair(output=self.input)


class CommittedBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = repair.load_baseline()

    def test_shape(self) -> None:
        files = self.baseline["files"]
        self.assertEqual(len(files), 201)
        self.assertEqual(sum(f["qb_count"] for f in files), 650)
        self.assertEqual(sum(f["bytes_changed"] for f in files), 649)          # one QB already sits at 99
        self.assertEqual(files[0]["outer_index"], 5)
        self.assertEqual(files[0]["sha256"], "b3dd88e2b51824b368e78f99f17d7aea7d64b26316c60fee5c0767f31261f501")
        self.assertEqual(len({f["outer_index"] for f in files}), 201)
        self.assertTrue(all(len(f["sha256"]) == len(f["sha256_after"]) == 64 for f in files))
        main = files[0]["quarterbacks"]
        self.assertEqual(sum(1 for q in main if q["pool"] == "secondary"), 4)
        self.assertEqual(sorted(q["value"] for q in main if q["pool"] == "secondary"), [50, 53, 95, 96])
        self.assertEqual(self.baseline["disc_sha256"], repair.V05_DISC_SHA256)
        self.assertTrue(all(q["offset"] >= qp.WRAPPER for f in files for q in f["quarterbacks"]))

    def test_known_players(self) -> None:
        main = {(q["first"], q["last"]): q["value"] for q in self.baseline["files"][0]["quarterbacks"]}
        self.assertEqual((main[("Josh", "Allen")], qp.raised(main[("Josh", "Allen")], 4, 99)), (94, 98))
        self.assertEqual(qp.raised(main[("Patrick", "Mahomes")], 4, 99), 90)
        self.assertEqual(qp.raised(main[("Cam", "Ward")], 4, 99), 86)


@unittest.skipUnless(os.environ.get("B77_Q1_DISC") and Path(os.environ.get("B77_Q1_DISC", "")).is_file(),
                     "set B77_Q1_DISC to the v0.5 disc to compare the baseline with it (about a minute)")
class RealDiscTests(unittest.TestCase):
    def test_the_baseline_matches_the_disc_and_the_repair_output_hashes_replay(self) -> None:
        self.assertEqual(repair.build_baseline(Path(os.environ["B77_Q1_DISC"])), repair.load_baseline())


if __name__ == "__main__":
    unittest.main()
