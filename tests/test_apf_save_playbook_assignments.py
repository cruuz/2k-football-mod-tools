"""Offline proofs for APF 2K8 per-team save playbook assignment edits."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "tools"))

import apf_save_playbook_assignments as subject  # noqa: E402


def synthetic_save(layout: subject.Layout = subject.RAW_LAYOUT) -> bytes:
    """Build the complete pointer graph without embedding any retail data."""

    size = layout.playbook_start + subject.PLAYBOOK_COUNT * subject.PLAYBOOK_STRIDE + 0x8000
    data = bytearray(size)
    data[:4] = b"CON " if layout.signed_container else b"TEST"
    cursor = layout.playbook_start + subject.PLAYBOOK_COUNT * subject.PLAYBOOK_STRIDE

    def add_string(value: str) -> int:
        nonlocal cursor
        if cursor % 2:
            cursor += 1
        encoded = value.encode("utf-16-be") + b"\0\0"
        target = cursor
        data[target:target + len(encoded)] = encoded
        cursor += len(encoded)
        return target

    offensive_ids = set(range(32)) | set(range(64, 68))
    for playbook_id in range(subject.PLAYBOOK_COUNT):
        record = layout.playbook_start + playbook_id * subject.PLAYBOOK_STRIDE
        name_target = add_string(f"Test Book {playbook_id}")
        type_target = add_string("TEST-o" if playbook_id in offensive_ids else "TEST-d")
        struct.pack_into(">I", data, record, name_target + 1 - record)
        struct.pack_into(">I", data, record + 4, type_target + 1 - (record + 4))
        side = subject.OFFENSE_SIDE if playbook_id in offensive_ids else subject.DEFENSE_SIDE
        struct.pack_into(">I", data, record + 8, side)

    offense = sorted(offensive_ids)
    defense = sorted(set(range(subject.PLAYBOOK_COUNT)) - offensive_ids)
    for team_index in range(subject.TEAM_COUNT):
        record = layout.team_start + team_index * subject.TEAM_STRIDE
        for field_delta, playbook_id in (
            (subject.OFFENSE_FIELD, offense[team_index % len(offense)]),
            (subject.DEFENSE_FIELD, defense[team_index % len(defense)]),
        ):
            field = record + field_delta
            target = layout.playbook_start + playbook_id * subject.PLAYBOOK_STRIDE
            stored = target + 1 - field - layout.assignment_pointer_bias
            struct.pack_into(">I", data, field, stored)
    return bytes(data)


class ParseTests(unittest.TestCase):
    def test_complete_raw_table_and_all_teams_parse(self) -> None:
        parsed = subject.parse_save(synthetic_save())
        self.assertEqual(len(parsed.playbooks), 69)
        self.assertEqual(sum(book.side == subject.OFFENSE_SIDE for book in parsed.playbooks), 36)
        self.assertEqual(sum(book.side == subject.DEFENSE_SIDE for book in parsed.playbooks), 33)
        self.assertEqual(len(parsed.teams), 40)
        self.assertEqual(parsed.teams[0].offensive_playbook_id, 0)
        self.assertEqual(parsed.teams[0].defensive_playbook_id, 32)

    def test_signed_con_uses_the_cross_region_pointer_bias(self) -> None:
        parsed = subject.parse_save(synthetic_save(subject.CON_LAYOUT))
        self.assertTrue(parsed.layout.signed_container)
        self.assertEqual(parsed.teams[0].offensive_playbook_id, 0)
        self.assertEqual(parsed.teams[39].defensive_playbook_id, 38)

    def test_corrupt_team_pointer_is_rejected(self) -> None:
        data = bytearray(synthetic_save())
        field = subject.RAW_LAYOUT.team_start + subject.OFFENSE_FIELD
        struct.pack_into(">I", data, field, 1)
        with self.assertRaisesRegex(subject.SaveError, "does not target"):
            subject.parse_save(bytes(data))


class PatchTests(unittest.TestCase):
    def test_patch_verify_and_reverse_are_byte_exact(self) -> None:
        source = synthetic_save()
        changed, manifest = subject.make_patch(source, [{
            "team_index": 0,
            "offensive_playbook_id": 64,
            "defensive_playbook_id": 68,
        }])
        self.assertNotEqual(changed, source)
        self.assertLessEqual(manifest["changed_byte_count"], 8)
        result = subject.verify_patch(source, changed, manifest)
        self.assertTrue(result["verified"])
        parsed = subject.parse_save(changed)
        self.assertEqual(parsed.teams[0].offensive_playbook_id, 64)
        self.assertEqual(parsed.teams[0].defensive_playbook_id, 68)

        restored, reverse_manifest = subject.make_patch(changed, [{
            "team_index": 0,
            "offensive_playbook_id": 0,
            "defensive_playbook_id": 32,
        }])
        self.assertEqual(restored, source)
        self.assertTrue(subject.verify_patch(changed, restored, reverse_manifest)["verified"])

    def test_wrong_side_is_rejected(self) -> None:
        with self.assertRaisesRegex(subject.SaveError, "is not offensive"):
            subject.make_patch(synthetic_save(), [{
                "team_index": 0,
                "offensive_playbook_id": 32,
            }])

    def test_no_op_is_rejected(self) -> None:
        with self.assertRaisesRegex(subject.SaveError, "already matches"):
            subject.make_patch(synthetic_save(), [{
                "team_index": 0,
                "offensive_playbook_id": 0,
            }])

    def test_signed_container_write_is_refused(self) -> None:
        with self.assertRaisesRegex(subject.SaveError, "inspect-only"):
            subject.make_patch(synthetic_save(subject.CON_LAYOUT), [{
                "team_index": 0,
                "offensive_playbook_id": 64,
            }])

    def test_manifest_tampering_is_detected(self) -> None:
        source = synthetic_save()
        changed, manifest = subject.make_patch(source, [{
            "team_index": 0,
            "offensive_playbook_id": 64,
        }])
        tampered = copy.deepcopy(manifest)
        tampered["edits"][0]["after_playbook_id"] = 1
        with self.assertRaisesRegex(subject.SaveError, "after assignment differs"):
            subject.verify_patch(source, changed, tampered)

    def test_public_writer_creates_new_files_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source.ros"
            edits_path = root / "edits.json"
            output_path = root / "patched.ros"
            manifest_path = root / "receipt.json"
            source_path.write_bytes(synthetic_save())
            edits_path.write_text(json.dumps({"edits": [{
                "team_index": 0,
                "offensive_playbook_id": 64,
            }]}), encoding="utf-8")
            manifest = subject.write_patch(
                source_path, output_path, edits_path, manifest_path)
            self.assertEqual(output_path.stat().st_size, source_path.stat().st_size)
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), manifest)
            with self.assertRaisesRegex(subject.SaveError, "refusing to overwrite"):
                subject.write_patch(source_path, output_path, edits_path, root / "other.json")
            self.assertFalse((root / "other.json").exists())

    def test_duplicate_assignment_fields_in_edit_json_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "edits.json"
            path.write_text(json.dumps({"edits": [
                {"team_index": 2, "offensive_playbook_id": 4},
                {"team_index": 2, "offensive_playbook_id": 5},
            ]}), encoding="utf-8")
            with self.assertRaisesRegex(subject.SaveError, "more than once"):
                subject.load_edits(path)


if __name__ == "__main__":
    unittest.main()
