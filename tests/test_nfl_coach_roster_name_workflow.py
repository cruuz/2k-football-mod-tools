"""Unit tests for the NFL 2K5 coach name writer's pure logic.

These exercise plan validation, the live reference census, and the
fixed-size name preparation without building a full copied XISO (the
end-to-end copied-XISO byte-diff proof lives in
``tools/validate_nfl_coach_roster_name.sh``).
"""

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_coach_roster_name_workflow as coach  # noqa: E402

SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"


def write_plan(tmp: Path, edits, schema=coach.PLAN_SCHEMA, source=SOURCE_SHA256) -> Path:
    path = tmp / "plan.json"
    path.write_text(json.dumps({"schema": schema, "source_sha256": source, "edits": edits}))
    return path


def _put_str(body: bytearray, offset: int, value: str) -> int:
    payload = (value + "\0").encode("utf-16le")
    body[offset:offset + len(payload)] = payload
    return offset + len(payload)


def _set_ptr(body: bytearray, field: int, target: int) -> None:
    struct.pack_into("<i", body, field, target - field + 1)


def build_body() -> tuple[bytearray, dict[str, int]]:
    """Build a structurally valid retail-shaped ROST body with 35 coaches.

    Coach 0 first_name is aliased by coach 1 (reference count 2); every other
    coach name allocation is uniquely referenced.
    """

    body = bytearray(coach.ROST_BODY_SIZE)
    strings: dict[str, int] = {}

    # Preamble: inner magic, version 17, root at 0x40, structural label.
    body[0x0C:0x10] = b"ROST"
    struct.pack_into("<I", body, 0x10, 17)
    _set_ptr(body, 0x14, coach.ROST_ROOT_OFFSET)
    _put_str(body, coach.STRUCTURAL_LABEL_OFFSET, "roster")

    root = coach.ROST_ROOT_OFFSET
    tables = {
        "primary_players": (1, 0x4500, 0x54),
        "secondary_players": (1, 0x4580, 0x54),
        "stadiums": (1, 0x4400, 0x80),
        "teams": (1, 0x4200, 0x1F4),
        "colleges": (1, 0x4600, 0x08),
        "coaches": (coach.COACH_TABLE_COUNT, coach.COACH_TABLE_OFFSET, 0xA8),
        "player_pointer_vector": (0, 0xB0, 0x04),
        "team_labels": (1, 0x4610, 0x08),
        "generated_names": (1, 0x4620, 0x08),
        "historic_descriptors": (1, 0x4640, 0x10),
    }
    for name, count_offset, pointer_offset, _stride in coach.TABLE_SPECS:
        count, offset, _ = tables[name]
        struct.pack_into("<I", body, root + count_offset, count)
        _set_ptr(body, root + pointer_offset, offset)

    pool = 0x5000
    pool = _put_str(body, pool, "Alex")
    strings["coach0_first"] = 0x5000
    strings["coach0_last"] = pool
    pool = _put_str(body, pool, "Smith")
    strings["coach1_last"] = pool
    pool = _put_str(body, pool, "Jones")
    for index in range(2, coach.COACH_TABLE_COUNT):
        strings[f"coach{index}_first"] = pool
        pool = _put_str(body, pool, f"First{index}")
        strings[f"coach{index}_last"] = pool
        pool = _put_str(body, pool, f"Last{index}")

    for index in range(coach.COACH_TABLE_COUNT):
        record = coach.COACH_TABLE_OFFSET + index * coach.COACH_STRIDE
        first = strings["coach0_first"] if index <= 1 else strings[f"coach{index}_first"]
        last = strings["coach0_last"] if index == 0 else strings[f"coach{index}_last"]
        _set_ptr(body, record + 0x00, first)
        _set_ptr(body, record + 0x04, last)
        struct.pack_into("<H", body, record + 0x40, 100 + index)

    team = 0x4200
    for field, text in ((0x104, "Comets"), (0x108, "COM"), (0x10C, "42"),
                        (0x138, "Orbit City"), (0x13C, "ORB")):
        start = pool
        pool = _put_str(body, pool, text)
        _set_ptr(body, team + field, start)
    _set_ptr(body, team + coach.TEAM_COACH_POINTER_FIELD, coach.COACH_TABLE_OFFSET)

    stadium = 0x4400
    for field, text in ((0x00, "Dome"), (0x08, "Orbit City"), (0x0C, "dome01"),
                        (0x10, "Orbit Dome"), (0x14, "OD")):
        start = pool
        pool = _put_str(body, pool, text)
        _set_ptr(body, stadium + field, start)

    start = pool
    pool = _put_str(body, pool, "Orbit University")
    _set_ptr(body, 0x4600, start)

    for record, first, last in ((0x4500, "Reserve", "Player"),
                                (0x4580, "", "")):
        start = pool
        pool = _put_str(body, pool, first)
        _set_ptr(body, record + 0x10, start)
        start = pool
        pool = _put_str(body, pool, last)
        _set_ptr(body, record + 0x14, start)

    for record, nickname, abbreviation in ((0x4610, "Comets", "COM"),
                                           (0x4620, "Gen", "GEN")):
        start = pool
        pool = _put_str(body, pool, nickname)
        _set_ptr(body, record + 0x00, start)
        start = pool
        pool = _put_str(body, pool, abbreviation)
        _set_ptr(body, record + 0x04, start)

    start = pool
    _put_str(body, pool, "slug01")
    _set_ptr(body, 0x4640 + 0x0C, start)
    return body, strings


def parse_fixture() -> tuple[bytes, dict[str, dict[str, int]], list[dict], dict[int, int]]:
    body, _strings = build_body()
    body = bytes(body)
    tables = coach.parse_roster_body(body)
    references = coach.known_string_pointer_references(body, tables)
    records = coach.parse_coach_records(body, tables, references)
    return body, tables, records, references


class CoachBodyFixtureTests(unittest.TestCase):
    def test_parses_35_coaches_with_expected_names(self) -> None:
        body, tables, records, references = parse_fixture()
        self.assertEqual(len(records), coach.COACH_TABLE_COUNT)
        self.assertEqual(records[0]["first_name"], "Alex")
        self.assertEqual(records[0]["last_name"], "Smith")
        self.assertEqual(records[0]["identity_code_u16_40"], 100)
        self.assertEqual(records[34]["first_name"], "First34")
        self.assertEqual(records[34]["last_name"], "Last34")
        refs = coach.coach_team_refs(body, tables)
        self.assertEqual(refs, {0: [0]})

    def test_alias_census_matches_catalog_ownership_contract(self) -> None:
        _body, _tables, records, _references = parse_fixture()
        self.assertEqual(
            records[0]["first_name_known_pointer_reference_count"], 2)
        self.assertEqual(
            records[1]["first_name_known_pointer_reference_count"], 2)
        for index in range(coach.COACH_TABLE_COUNT):
            self.assertEqual(
                records[index]["last_name_known_pointer_reference_count"], 1,
                f"coach {index} last name must be uniquely referenced")
            if index >= 2:
                self.assertEqual(
                    records[index]["first_name_known_pointer_reference_count"], 1)

    def test_tampered_coach_table_layout_is_refused(self) -> None:
        body, _strings = build_body()
        root = coach.ROST_ROOT_OFFSET
        spec = next(item for item in coach.TABLE_SPECS if item[0] == "coaches")
        struct.pack_into("<I", body, root + spec[1], coach.COACH_TABLE_COUNT + 1)
        with self.assertRaisesRegex(coach.WorkflowError, "coach table layout changed"):
            coach.parse_roster_body(bytes(body))


class CoachNameEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body, self.tables, self.records, self.references = parse_fixture()

    def test_same_value_round_trip_is_byte_identical(self) -> None:
        edit = coach.prepare_name_edit(self.body, self.records[0],
                                       "last_name", "Smith")
        self.assertEqual(edit["changed_relative_bytes"], [])
        self.assertEqual(edit["before_hex"], edit["after_hex"])
        self.assertEqual(edit["before"], "Smith")
        self.assertEqual(edit["after"], "Smith")
        span = len(("Smith" + "\0").encode("utf-16le"))
        self.assertEqual(edit["allocation_bytes"], span)
        self.assertEqual(len(edit["payload"]), span)

    def test_shorter_value_zero_fills_and_preserves_span(self) -> None:
        original = coach.prepare_name_edit(self.body, self.records[2],
                                           "last_name", "Last2")
        edit = coach.prepare_name_edit(self.body, self.records[2],
                                       "last_name", "L2")
        self.assertEqual(edit["allocation_bytes"], original["allocation_bytes"])
        self.assertEqual(len(edit["payload"]), original["allocation_bytes"])
        self.assertEqual(
            edit["payload"],
            "L2".encode("utf-16le") + b"\0\0" +
            bytes(original["allocation_bytes"] - len("L2".encode("utf-16le")) - 2))
        self.assertEqual(edit["known_pointer_reference_count"], 1)

    def test_longer_value_is_refused_with_clear_error(self) -> None:
        with self.assertRaisesRegex(coach.WorkflowError,
                                    "full-allocation writer"):
            coach.prepare_name_edit(self.body, self.records[0],
                                    "last_name", "Smithsonian")

    def test_shared_allocation_is_refused(self) -> None:
        with self.assertRaisesRegex(coach.WorkflowError,
                                    "not uniquely referenced"):
            coach.prepare_name_edit(self.body, self.records[1],
                                   "first_name", "Al")

    def test_empty_and_nul_values_are_refused(self) -> None:
        with self.assertRaisesRegex(coach.WorkflowError, "non-empty string"):
            coach.prepare_name_edit(self.body, self.records[0], "last_name", "")
        with self.assertRaisesRegex(coach.WorkflowError, "NUL"):
            coach.prepare_name_edit(self.body, self.records[0],
                                    "last_name", "Sm\0ith")

    def test_unsupported_field_is_refused(self) -> None:
        with self.assertRaisesRegex(coach.WorkflowError, "unsupported field"):
            coach.prepare_name_edit(self.body, self.records[0],
                                    "description_1", "X")

    def test_moved_pointer_target_is_refused(self) -> None:
        record = dict(self.records[0])
        record["last_name_body_offset"] = record["first_name_body_offset"]
        with self.assertRaisesRegex(coach.WorkflowError, "pointer target moved"):
            coach.prepare_name_edit(self.body, record, "last_name", "Smith")


class PrepareEditsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body, self.tables, self.records, self.references = parse_fixture()

    def _plan(self, edits) -> dict:
        return {"schema": coach.PLAN_SCHEMA, "source_sha256": SOURCE_SHA256,
                "edits": edits}

    def test_absolute_offsets_and_allowed_set(self) -> None:
        prepared, allowed = coach.prepare_edits(
            0x1000, self.body, self.records, self._plan([
                {"coach_index": 0, "field": "last_name", "value": "Sm"},
                {"coach_index": 2, "field": "first_name", "value": "First2"},
            ]))
        self.assertEqual(len(prepared), 2)
        self.assertEqual(prepared[0]["xiso_absolute_offset"],
                         0x1000 + prepared[0]["body_string_offset"])
        identity = next(edit for edit in prepared if edit["field"] == "first_name")
        self.assertEqual(identity["changed_relative_bytes"], [])
        expected = {0x1000 + prepared[0]["body_string_offset"] + i
                    for i in range(len(prepared[0]["payload"]))
                    if prepared[0]["payload"][i] != bytes.fromhex(
                        prepared[0]["before_hex"])[i]}
        self.assertEqual(allowed, expected)

    def test_duplicate_edit_is_refused(self) -> None:
        with self.assertRaisesRegex(coach.WorkflowError, "duplicate edit"):
            coach.prepare_edits(0, self.body, self.records, self._plan([
                {"coach_index": 0, "field": "last_name", "value": "Sm"},
                {"coach_index": 0, "field": "last_name", "value": "S"},
            ]))

    def test_identity_only_plan_changes_no_bytes(self) -> None:
        with self.assertRaisesRegex(coach.WorkflowError, "plan changes no bytes"):
            coach.prepare_edits(0, self.body, self.records, self._plan([
                {"coach_index": 0, "field": "last_name", "value": "Smith"},
            ]))

    def test_out_of_range_coach_and_bad_field_are_refused(self) -> None:
        with self.assertRaisesRegex(coach.WorkflowError, "outside the main roster"):
            coach.prepare_edits(0, self.body, self.records, self._plan([
                {"coach_index": 35, "field": "last_name", "value": "X"},
            ]))
        with self.assertRaisesRegex(coach.WorkflowError, "unsupported field"):
            coach.prepare_edits(0, self.body, self.records, self._plan([
                {"coach_index": 0, "field": "nickname", "value": "X"},
            ]))


class PlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_accepts_valid_plan(self) -> None:
        plan = write_plan(self.tmp, [
            {"coach_index": 0, "field": "first_name", "value": "Denny"},
        ])
        value, resolved, owned = coach.load_plan(plan)
        self.assertEqual(value["schema"], coach.PLAN_SCHEMA)
        self.assertEqual(len(value["edits"]), 1)

    def test_rejects_wrong_schema(self) -> None:
        plan = write_plan(self.tmp, [
            {"coach_index": 0, "field": "first_name", "value": "D"},
        ], schema="bogus/v1")
        with self.assertRaisesRegex(coach.WorkflowError, "plan schema mismatch"):
            coach.load_plan(plan)

    def test_rejects_wrong_source_binding(self) -> None:
        plan = write_plan(self.tmp, [
            {"coach_index": 0, "field": "first_name", "value": "D"},
        ], source="0" * 64)
        with self.assertRaisesRegex(coach.WorkflowError,
                                    "not bound to the supported retail source"):
            coach.load_plan(plan)

    def test_rejects_empty_edits(self) -> None:
        plan = write_plan(self.tmp, [])
        with self.assertRaisesRegex(coach.WorkflowError, "plan has no edits"):
            coach.load_plan(plan)

    def test_rejects_symlink_plan(self) -> None:
        plan = write_plan(self.tmp, [
            {"coach_index": 0, "field": "first_name", "value": "D"},
        ])
        link = self.tmp / "link.json"
        os.symlink(plan, link)
        with self.assertRaisesRegex(coach.WorkflowError, "plan must not be a symlink"):
            coach.load_plan(link)


if __name__ == "__main__":
    unittest.main()
