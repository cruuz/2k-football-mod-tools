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
