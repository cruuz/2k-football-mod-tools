"""Unit tests for the generalized NFL 2K5 roster writer's pure logic.

These exercise plan validation and the fixed-size jersey/name preparation
without building a full copied XISO (the end-to-end copied-XISO byte-diff proof
lives in ``tools/validate_nfl_player_roster_general.sh``).
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

import nfl_player_roster_general_workflow as general  # noqa: E402
import nfl2k5_visual_mod_project as unified  # noqa: E402

SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"


def write_plan(tmp: Path, edits, schema=general.PLAN_SCHEMA, source=SOURCE_SHA256) -> Path:
    path = tmp / "plan.json"
    path.write_text(json.dumps({"schema": schema, "source_sha256": source, "edits": edits}))
    return path


class PlanValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_accepts_valid_plan(self) -> None:
        plan = write_plan(self.tmp, [
            {"pool": "primary_players", "player_index": 512,
             "field": "jersey_number", "value": 42},
        ])
        value, resolved, owned = general.load_plan(plan)
        self.assertEqual(value["schema"], general.PLAN_SCHEMA)
        self.assertEqual(len(value["edits"]), 1)

    def test_rejects_wrong_schema(self) -> None:
        plan = write_plan(self.tmp, [{"pool": "primary_players",
                                      "player_index": 0, "field": "jersey_number",
                                      "value": 1}], schema="bogus/v1")
        with self.assertRaisesRegex(general.WorkflowError, "plan schema mismatch"):
            general.load_plan(plan)

    def test_rejects_wrong_source_binding(self) -> None:
        plan = write_plan(self.tmp, [{"pool": "primary_players",
                                      "player_index": 0, "field": "jersey_number",
                                      "value": 1}], source="0" * 64)
        with self.assertRaisesRegex(general.WorkflowError,
                                    "not bound to the supported retail source"):
            general.load_plan(plan)

    def test_rejects_empty_edits(self) -> None:
        plan = write_plan(self.tmp, [])
        with self.assertRaisesRegex(general.WorkflowError, "plan has no edits"):
            general.load_plan(plan)

    def test_rejects_symlink_plan(self) -> None:
        plan = write_plan(self.tmp, [{"pool": "primary_players",
                                      "player_index": 0, "field": "jersey_number",
                                      "value": 1}])
        link = self.tmp / "link.json"
        os.symlink(plan, link)
        with self.assertRaisesRegex(general.WorkflowError, "plan must not be a symlink"):
            general.load_plan(link)


class PoolLayoutTests(unittest.TestCase):
    def test_pool_layout_matches_audit(self) -> None:
        self.assertEqual(general.POOL_LAYOUT["primary_players"],
                         {"offset": 44968, "count": 2479})
        self.assertEqual(general.POOL_LAYOUT["secondary_players"],
                         {"offset": 253204, "count": 68})

    def test_player_record_range_check(self) -> None:
        audit = {"players": []}
        with self.assertRaisesRegex(general.WorkflowError, "out of range"):
            general.player_record(audit, "secondary_players", 68)
        with self.assertRaisesRegex(general.WorkflowError, "unknown pool"):
            general.player_record(audit, "tertiary_players", 0)


class JerseyMaskTests(unittest.TestCase):
    """The jersey edit must change only masked bits 3..9 and preserve the rest."""

    def _record_with_word(self, word: int) -> tuple[int, dict]:
        tmp = tempfile.NamedTemporaryFile(delete=False)
        # record layout: 0x20 bytes of padding then the jersey word at +0x20
        tmp.write(b"\0" * 0x20 + struct.pack("<I", word))
        tmp.flush()
        fd = os.open(tmp.name, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        self.addCleanup(os.unlink, tmp.name)
        # body absolute = 0 so record offset 0 maps to file offset 0
        record = {"pool": "primary_players", "index": 0, "record_body_offset": 0}
        return fd, record

    def test_preserves_unrelated_bits(self) -> None:
        # word with non-jersey bits set: bits 0..2 = 0b101, bits 10+ = 0x12340000
        base = 0x12340000 | 0b101 | (3 << 3)
        fd, record = self._record_with_word(base)
        edit = general.prepare_jersey_edit(fd, 0, record, 42)
        expected_word = (base & ~general.JERSEY_MASK) | (42 << general.JERSEY_SHIFT)
        self.assertEqual(edit["after"], 42)
        self.assertEqual(edit["before"], 3)
        self.assertEqual(struct.unpack("<I", edit["payload"])[0], expected_word)
        # unrelated bits preserved
        self.assertEqual(expected_word & ~general.JERSEY_MASK, base & ~general.JERSEY_MASK)

    def test_rejects_out_of_range_jersey(self) -> None:
        fd, record = self._record_with_word(0)
        with self.assertRaisesRegex(general.WorkflowError, "0..99"):
            general.prepare_jersey_edit(fd, 0, record, 100)

    def test_secondary_jersey_uses_same_mechanics(self) -> None:
        base = (19 << 3)
        fd, record = self._record_with_word(base)
        record["pool"] = "secondary_players"
        edit = general.prepare_jersey_edit(fd, 0, record, 7)
        self.assertEqual(edit["pool"], "secondary_players")
        self.assertEqual(edit["before"], 19)
        self.assertEqual(edit["after"], 7)

    def test_unified_backend_builds_and_reopens_secondary_number(self) -> None:
        record_offset = 0x100
        raw = bytearray(unified.ROST_PLAYER_STRIDE)
        before_word = 0x80000 | (19 << unified.PLAYER_JERSEY_SHIFT) | 5
        struct.pack_into("<H", raw, 0x06, 1234)
        struct.pack_into("<I", raw, unified.PLAYER_JERSEY_FIELD, before_word)
        raw[0x35] = 3
        body = bytearray(0x400)
        body[record_offset:record_offset + len(raw)] = raw
        parsed = {
            "label": "main",
            "teams": [],
            "players": [{
                "pool": "secondary_players",
                "index": 0,
                "offset": record_offset,
                "raw_hex": raw.hex(),
                "team_refs": [],
                "first_name": "Reserve",
                "first_name_offset": 0x300,
                "last_name": "Player",
                "last_name_offset": 0x320,
            }],
            "stadiums": [],
            "coaches": [],
            "colleges": [],
            "historic_descriptors": [],
            "team_labels": [],
            "generated_names": [],
        }
        view = unified.RosterResourceView(
            5, "0x00000005", 0x420, 0x1000, bytes(body), parsed
        )
        project_edit = {
            "kind": "roster_player_text",
            "resource_outer_index": 5,
            "player_pool": "secondary_players",
            "player_index": 0,
            "changes": {"jersey_number": 66},
        }
        self.assertEqual(unified.validate_edit_shape(project_edit, 0), project_edit)
        built = unified.build_roster_player_text_imports(project_edit, view)
        self.assertEqual(len(built), 1)
        replacement, _previews, report, selector, target = built[0]
        self.assertIn("secondary-player:0:jersey_number", selector)
        self.assertEqual(target["player_pool"], "secondary_players")
        self.assertFalse(report["claims"]["primary_player_only"])
        rebuilt = bytearray(body)
        rebuilt[target["body_offset"]:target["body_offset"] + 4] = replacement
        reopened_word = struct.unpack_from(
            "<I", rebuilt, record_offset + unified.PLAYER_JERSEY_FIELD
        )[0]
        self.assertEqual(
            (reopened_word >> unified.PLAYER_JERSEY_SHIFT) & 0x7F, 66
        )
        self.assertEqual(
            reopened_word & ~unified.PLAYER_JERSEY_MASK,
            before_word & ~unified.PLAYER_JERSEY_MASK,
        )


class FaceShieldMaskTests(unittest.TestCase):
    """Face shield authors only bits 15..16 and never admits reserved value 3."""

    def _record_with_word(self, word: int) -> tuple[int, dict]:
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.write(b"\0" * 0x20 + struct.pack("<I", word))
        tmp.flush()
        fd = os.open(tmp.name, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        self.addCleanup(os.unlink, tmp.name)
        return fd, {
            "pool": "primary_players", "index": 0,
            "record_body_offset": 0,
        }

    def test_clear_to_dark_preserves_every_unrelated_bit(self) -> None:
        base = 0xA5A00005 | (55 << general.JERSEY_SHIFT) | (
            1 << general.FACE_SHIELD_SHIFT
        )
        fd, record = self._record_with_word(base)
        edit = general.prepare_face_shield_edit(fd, 0, record, 2)
        after = struct.unpack("<I", edit["payload"])[0]
        expected = ((base & ~general.FACE_SHIELD_MASK)
                    | (2 << general.FACE_SHIELD_SHIFT))
        self.assertEqual(after, expected)
        self.assertEqual(edit["before"], 1)
        self.assertEqual(edit["after"], 2)
        self.assertEqual(
            after & ~general.FACE_SHIELD_MASK,
            base & ~general.FACE_SHIELD_MASK,
        )

    def test_reserved_value_three_is_refused(self) -> None:
        fd, record = self._record_with_word(0)
        with self.assertRaisesRegex(general.WorkflowError, "0 None, 1 Clear, or 2 Dark"):
            general.prepare_face_shield_edit(fd, 0, record, 3)

    def test_jersey_and_face_shield_compose_into_one_word(self) -> None:
        base = 0x80000005 | (12 << general.JERSEY_SHIFT)
        fd, record = self._record_with_word(base)
        edit = general.prepare_packed_word_edit(
            fd, 0, record, {"jersey_number": 88, "face_shield": 2}
        )
        after = struct.unpack("<I", edit["payload"])[0]
        authored = general.JERSEY_MASK | general.FACE_SHIELD_MASK
        self.assertEqual(edit["packed_fields"], ["jersey_number", "face_shield"])
        self.assertEqual((after >> general.JERSEY_SHIFT) & 0x7F, 88)
        self.assertEqual((after >> general.FACE_SHIELD_SHIFT) & 0x3, 2)
        self.assertEqual(after & ~authored, base & ~authored)

    def test_unified_project_builds_and_reopens_both_fields(self) -> None:
        record_offset = 0x100
        raw = bytearray(unified.ROST_PLAYER_STRIDE)
        before_word = 0x80000005 | (19 << unified.PLAYER_JERSEY_SHIFT) | (
            1 << unified.PLAYER_FACE_SHIELD_SHIFT
        )
        struct.pack_into("<H", raw, 0x06, 1234)
        struct.pack_into("<I", raw, unified.PLAYER_JERSEY_FIELD, before_word)
        raw[0x35] = 3
        body = bytearray(0x400)
        body[record_offset:record_offset + len(raw)] = raw
        parsed = {
            "label": "main", "teams": [],
            "players": [{
                "pool": "secondary_players", "index": 0,
                "offset": record_offset, "raw_hex": raw.hex(), "team_refs": [],
                "first_name": "Reserve", "first_name_offset": 0x300,
                "last_name": "Player", "last_name_offset": 0x320,
            }],
            "stadiums": [], "coaches": [], "colleges": [],
            "historic_descriptors": [], "team_labels": [], "generated_names": [],
        }
        view = unified.RosterResourceView(
            5, "0x00000005", 0x420, 0x1000, bytes(body), parsed
        )
        project_edit = {
            "kind": "roster_player_text", "resource_outer_index": 5,
            "player_pool": "secondary_players", "player_index": 0,
            "changes": {"jersey_number": 66, "face_shield": 2},
        }
        self.assertEqual(unified.validate_edit_shape(project_edit, 0), project_edit)
        built = unified.build_roster_player_text_imports(project_edit, view)
        self.assertEqual(len(built), 1, "shared +0x20 word must be one write")
        replacement, _previews, report, selector, target = built[0]
        self.assertIn("player_word_20", selector)
        self.assertEqual(target["packed_fields"], ["jersey_number", "face_shield"])
        self.assertTrue(
            report["claims"]["face_shield_is_per_player_type_not_uniform_tint"]
        )
        rebuilt = bytearray(body)
        rebuilt[target["body_offset"]:target["body_offset"] + 4] = replacement
        reopened = struct.unpack_from(
            "<I", rebuilt, record_offset + unified.PLAYER_JERSEY_FIELD
        )[0]
        authored = unified.PLAYER_JERSEY_MASK | unified.PLAYER_FACE_SHIELD_MASK
        self.assertEqual((reopened >> unified.PLAYER_JERSEY_SHIFT) & 0x7F, 66)
        self.assertEqual((reopened >> unified.PLAYER_FACE_SHIELD_SHIFT) & 0x3, 2)
        self.assertEqual(reopened & ~authored, before_word & ~authored)

    def test_unified_project_schema_refuses_reserved_value_three(self) -> None:
        project_edit = {
            "kind": "roster_player_text", "resource_outer_index": 5,
            "player_pool": "secondary_players", "player_index": 0,
            "changes": {"face_shield": 3},
        }
        with self.assertRaisesRegex(unified.ProjectError, "invalid roster_player_text"):
            unified.validate_edit_shape(project_edit, 0)

    def test_jersey_edit_preserves_source_reserved_face_shield_three(self) -> None:
        raw = bytearray(unified.ROST_PLAYER_STRIDE)
        before_word = ((12 << unified.PLAYER_JERSEY_SHIFT)
                       | (3 << unified.PLAYER_FACE_SHIELD_SHIFT) | 5)
        struct.pack_into("<H", raw, 0x06, 1234)
        struct.pack_into("<I", raw, unified.PLAYER_JERSEY_FIELD, before_word)
        raw[0x35] = 3
        body = bytearray(0x400)
        body[:len(raw)] = raw
        view = unified.RosterResourceView(
            5, "0x00000005", 0x420, 0x1000, bytes(body), {
                "label": "main", "teams": [],
                "players": [{
                    "pool": "secondary_players", "index": 0, "offset": 0,
                    "raw_hex": raw.hex(), "team_refs": [],
                    "first_name": "Reserve", "first_name_offset": 0x300,
                    "last_name": "Player", "last_name_offset": 0x320,
                }],
                "stadiums": [], "coaches": [], "colleges": [],
                "historic_descriptors": [], "team_labels": [],
                "generated_names": [],
            },
        )
        built = unified.build_roster_player_text_imports({
            "kind": "roster_player_text", "resource_outer_index": 5,
            "player_pool": "secondary_players", "player_index": 0,
            "changes": {"jersey_number": 44},
        }, view)
        replacement = struct.unpack("<I", built[0][0])[0]
        self.assertEqual((replacement >> unified.PLAYER_JERSEY_SHIFT) & 0x7F, 44)
        self.assertEqual(
            (replacement >> unified.PLAYER_FACE_SHIELD_SHIFT) & 0x3, 3
        )
        self.assertEqual(
            replacement & ~unified.PLAYER_JERSEY_MASK,
            before_word & ~unified.PLAYER_JERSEY_MASK,
        )


class NameGuardTests(unittest.TestCase):
    def test_secondary_name_refused(self) -> None:
        record = {"pool": "secondary_players", "index": 0, "record_body_offset": 0,
                  "first_name_known_pointer_reference_count": 1,
                  "first_name_body_offset": 0}
        with self.assertRaisesRegex(general.WorkflowError, "zero-capacity"):
            general.prepare_name_edit(0, 0, record, "first_name", "X")

    def test_shared_name_refused(self) -> None:
        record = {"pool": "primary_players", "index": 0, "record_body_offset": 0,
                  "first_name_known_pointer_reference_count": 2,
                  "first_name_body_offset": 0}
        with self.assertRaisesRegex(general.WorkflowError, "not uniquely referenced"):
            general.prepare_name_edit(0, 0, record, "first_name", "X")


if __name__ == "__main__":
    unittest.main()
