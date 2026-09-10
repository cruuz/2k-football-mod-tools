"""PS3 -> Xbox 360 APF roster conversion: synthetic contract tests plus the retail-gated 1993 member."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.apf_studio import ps3_roster_convert as subject
from mod_editor.apf_studio import save_roster_players as players
from mod_editor.apf_studio.backend import ensure_tools_importable
from tests.mod_editor.test_apf_save_roster_players import roster_save
from tests.test_apf_save_custom_team_appearance import CONFIG_START, writer

ensure_tools_importable()
import apf_save_custom_team_appearance as save_layout  # noqa: E402
import apf_save_playbook_assignments as labels_reader  # noqa: E402

PS3_ZIP = Path("/home/noah/Downloads/1993 NFL Season (Update Logos).zip")
PS3_MEMBER = "1993 NFL Season (Update Logos)/BLUS30049-ROS/USERDATA"
PS3_MEMBER_SHA256 = "0b3b24f2c14f3770a6728dce1560e6534e8803d966a264ff1eaace632c44a934"
XBOX_FIXTURE = Path("/home/noah/Downloads/apfe/Roster.ROS")
CONVERTED_SHA256 = "df2658dea378bbd216e8ac452fd9d6cc9af1ebc6518177182b527f3653e4d034"

LABEL_TABLE = 0x1D31DC
PS3_ROOT_WORDS = (0x9F9C8DAD, 0x9F9C9099, 0x9F9CC351, 0x9F9D3889)
PS3_RUNTIME_BLOCK = (0x5375CFE0, 0x589898E0, 0x5398D220, 0x5398D220, 0x50400000, 0x122535A0, 0x0007B81A, 0x04FFC6A0)
PS3_BANK_WORDS = (0x32BC8580, 0x30E25303, 0x10E25303)
FIRST_BANK_MAGIC = 0x26FA70


def _relative(field: int, target: int) -> int:
    return (target + 1 - field) & 0xFFFFFFFF


def _point(data: bytearray, field: int, target: int) -> None:
    struct.pack_into(">I", data, field, _relative(field, target))


def _utf16(text: str) -> bytes:
    return text.encode("utf-16-be") + b"\0\0"


def _put(data: bytearray, offset: int, payload: bytes) -> None:
    data[offset: offset + len(payload)] = payload


class Fixture:
    """One synthetic roster described once, rendered as PS3 input and as the exact Xbox 360 result."""

    def __init__(self, *, relocate: bool = False):
        base = bytearray(roster_save())
        self.base_length = len(base)
        self.pool_start = CONFIG_START + 40 * writer.CONFIG_STRIDE
        self.private_text = self.base_length - 32
        self.empty_text = self.base_length - 2
        self.player = 0x150
        self.team = 0x0B8078
        self.relocate = relocate
        self.odd_name = self.base_length + 0x101          # team 32 name, one byte late
        self.orphan = self.base_length + 0x201            # untargeted odd string with a garbage reader
        self.label_text = self.base_length + 0x300
        self.below_pool = 0x1D3600                        # zeros below the pool
        self.data = self._common(base)

    def _record(self, index: int) -> int:
        return self.player + index * players.PLAYER_STRIDE

    def _common(self, base: bytearray) -> bytearray:
        data = bytearray(subject.ROSTER_SIZE)
        data[: len(base)] = base
        for field in (0x144, 0x148, 0x14C):
            _point(data, field, self.pool_start)
        # 69 playbook labels (36 offensive, 33 defensive) and one assignment pair per team.
        _put(data, self.label_text, _utf16("Book"))
        _put(data, self.label_text + 10, _utf16("O"))
        _point(data, 4 + 11 * 8 + 4, LABEL_TABLE)
        for label in range(69):
            offset = LABEL_TABLE + label * 12
            _point(data, offset, self.label_text)
            _point(data, offset + 4, self.label_text + 10)
            struct.pack_into(">I", data, offset + 8, 0 if label < 36 else 0x01000000)
        for team in range(40):
            record = self.team + team * players.TEAM_STRIDE
            _point(data, record + 0xE0, LABEL_TABLE)
            _point(data, record + 0xE4, LABEL_TABLE + 36 * 12)
        return data

    def ps3(self) -> bytes:
        data = bytearray(self.data)
        # Palette colours FF RR GG BB -> RR GG BB FF.
        for row in range(266):
            for colour in range(10):
                offset = 0x1DD04C + row * 0x30 + colour * 4
                data[offset: offset + 4] = data[offset + 1: offset + 4] + data[offset: offset + 1]
        for index, word in zip(subject.XBOX_ROOT_RUNTIME_TABLES, PS3_ROOT_WORDS):
            struct.pack_into(">I", data, 4 + index * 8 + 4, word)
        struct.pack_into(">8I", data, subject.RUNTIME_BLOCK_OFFSET, *PS3_RUNTIME_BLOCK)
        for bank in range(5):
            magic = FIRST_BANK_MAGIC + bank * subject.BANK_STRIDE
            _put(data, magic, subject.BANK_MAGIC)
            for relative, word in zip(subject.BANK_WORD_OFFSETS, PS3_BANK_WORDS):
                struct.pack_into(">I", data, magic + relative, word)
        struct.pack_into(">I", data, subject.TRAILING_BANK_WORD, PS3_BANK_WORDS[0])
        # Player 0's "Alpha" one byte late (odd run), pointed at by its owner.
        alpha = _utf16("Alpha")
        _put(data, self.private_text, bytes(len(alpha)))
        _put(data, self.private_text + 1, alpha)
        _point(data, self._record(0) + 0x004, self.private_text + 1)
        # Stale references: a garbage inner read, a clean suffix read, a below-pool read,
        # and a garbage read of an orphan odd string that no owner claims.
        _point(data, self._record(1) + 0x118, self.private_text + 4)
        _point(data, self._record(2) + 0x118, self.private_text + 5)
        _point(data, self._record(3) + 0x118, self.below_pool)
        _put(data, self.orphan, _utf16("Orphan"))
        _point(data, self._record(5) + 0x11C, self.orphan + 1)
        if self.relocate:
            # An owner claims the guard byte before the odd run, so it cannot shift.
            _point(data, self._record(4) + 0x118, self.private_text)
        # Team 32 display name one byte late.
        _put(data, self.odd_name, _utf16("Lions"))
        _point(data, self.team + 32 * players.TEAM_STRIDE + 0xA8, self.odd_name)
        return bytes(data)

    def expected(self) -> bytes:
        data = bytearray(self.data)
        for index in subject.XBOX_ROOT_RUNTIME_TABLES:
            span_start = {15: 0x1DCE38, 16: 0x1DD04C, 17: 0x1E022C, 18: 0x1E768C}[index]
            struct.pack_into(">I", data, 4 + index * 8 + 4, (subject.XBOX_ROOT_RUNTIME_BASE + span_start) & 0xFFFFFFFF)
        struct.pack_into(">8I", data, subject.RUNTIME_BLOCK_OFFSET, *subject.XBOX_RUNTIME_BLOCK)
        for bank in range(5):
            magic = FIRST_BANK_MAGIC + bank * subject.BANK_STRIDE
            _put(data, magic, subject.BANK_MAGIC)
            for relative, word in zip(subject.BANK_WORD_OFFSETS, subject.XBOX_BANK_WORDS):
                struct.pack_into(">I", data, magic + relative, word)
        struct.pack_into(">I", data, subject.TRAILING_BANK_WORD, subject.XBOX_BANK_WORDS[0])
        for index in (1, 2, 3, 5):
            column = 0x11C if index == 5 else 0x118
            _point(data, self._record(index) + column, self.empty_text)
        _put(data, self.orphan, _utf16("Orphan"))
        if self.relocate:
            _point(data, self._record(4) + 0x118, self.empty_text)
        _put(data, self.odd_name - 1, _utf16("Lions"))
        _point(data, self.team + 32 * players.TEAM_STRIDE + 0xA8, self.odd_name - 1)
        return bytes(data)


class SyntheticConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = Fixture()
        cls.source = cls.fixture.ps3()
        cls.output, cls.receipt = subject.convert(cls.source)

    def test_platform_detection(self) -> None:
        self.assertEqual(subject.detect_platform(self.source), subject.PLATFORM_PS3)
        self.assertEqual(subject.detect_platform(self.output), subject.PLATFORM_XBOX360)
        self.assertEqual(subject.detect_platform(self.fixture.expected()), subject.PLATFORM_XBOX360)

    def test_output_is_the_exact_xbox_layout(self) -> None:
        expected = self.fixture.expected()
        differing = [i for i in range(len(expected)) if expected[i] != self.output[i]]
        self.assertEqual(differing[:20], [])
        self.assertEqual(len(self.output), subject.ROSTER_SIZE)

    def test_strict_readers_accept_output_and_refuse_input(self) -> None:
        with self.assertRaises(players.SaveRosterPlayerError):
            players.inspect_bytes(self.source)
        document = players.inspect_bytes(self.output)
        self.assertEqual(document.player_text_values(0)["first_name"], "Alpha")
        for index in (1, 2, 3):
            self.assertEqual(document.player_text_values(index)["nickname"], "")
        self.assertEqual(document.player_text_values(5)["career_history"], "")
        self.assertEqual(len(labels_reader.parse_save(self.output).playbooks), 69)
        name_field = self.fixture.team + 32 * players.TEAM_STRIDE + 0xA8
        self.assertEqual(save_layout._decode_utf16be(
            self.output, save_layout._relative_target(self.output, name_field, "t"), "t"), "Lions")
        self.assertEqual(save_layout.parse_save(self.output).slots[0].target.display_name, "Lions")

    def test_receipt_counts_and_claims(self) -> None:
        counts = self.receipt["counts"]
        self.assertEqual((counts["players"], counts["teams"], counts["playbook_labels"]), (2254, 40, 69))
        self.assertEqual(counts["odd_runs"], 2)
        self.assertEqual(counts["odd_runs_shifted"], 2)
        self.assertEqual(counts["odd_runs_relocated"], 0)
        self.assertEqual(counts["interior_allocations"], 2)
        self.assertEqual(counts["below_pool_references"], 1)
        self.assertEqual(counts["garbage_references"], 1)
        self.assertEqual(counts["palette_colours_rotated"], 2660)
        self.assertEqual(counts["root_runtime_fields_rewritten"], 4)
        self.assertEqual(counts["bank_runtime_words_rewritten"], 16)
        self.assertEqual(self.receipt["repointed_by_kind"], {"odd": 2, "interior": 2, "below_pool": 1, "garbage": 1})
        self.assertEqual(self.receipt["source"]["platform"], subject.PLATFORM_PS3)
        self.assertFalse(self.receipt["claims"]["runtime_in_game_proved"])
        self.assertIn("UNWITNESSED", self.receipt["runtime"])
        self.assertEqual(self.receipt["output"]["sha256"], hashlib.sha256(self.output).hexdigest())

    def test_idempotence_and_refusals(self) -> None:
        with self.assertRaisesRegex(subject.PS3RosterConvertError, "already uses the Xbox 360 layout"):
            subject.convert(self.output)
        with self.assertRaisesRegex(subject.PS3RosterConvertError, "already uses the Xbox 360 layout"):
            subject.convert(self.fixture.expected())
        mixed = bytearray(self.source)
        offset = 0x1DD04C
        mixed[offset: offset + 4] = mixed[offset + 3: offset + 4] + mixed[offset: offset + 3]
        with self.assertRaisesRegex(subject.PS3RosterConvertError, "cannot tell the roster platform"):
            subject.convert(bytes(mixed))
        with self.assertRaisesRegex(subject.PS3RosterConvertError, "expected 2715908"):
            subject.convert(self.source[:-1])

    def test_round_trip_edit_through_the_roster_writer(self) -> None:
        document = players.inspect_bytes(self.output)
        patched, manifest = players.make_patch(
            document,
            field_edits=(players.PlayerFieldEdit(0, "jersey_number", 42),),
            text_edits=(players.PlayerTextEdit(0, "first_name", "Beta"),),
        )
        self.assertTrue(players.verify_patch(document, patched, manifest)["verified"])
        self.assertEqual(players.inspect_bytes(patched).player_text_values(0)["first_name"], "Beta")

    def test_relocation_when_the_guard_byte_is_owned(self) -> None:
        fixture = Fixture(relocate=True)
        output, receipt = subject.convert(fixture.ps3())
        self.assertEqual(receipt["counts"]["odd_runs_relocated"], 1)
        self.assertEqual(receipt["counts"]["odd_runs_shifted"], 1)
        document = players.inspect_bytes(output)
        self.assertEqual(document.player_text_values(0)["first_name"], "Alpha")
        self.assertEqual(document.player_text_values(4)["nickname"], "")
        run = next(row for row in receipt["odd_runs"] if row["method"] == "relocate")
        self.assertEqual(run["destination_offset"] % 2, 0)
        self.assertGreaterEqual(run["destination_offset"], fixture.pool_start)
        self.assertEqual(output[run["source_offset"]: run["source_offset"] + run["bytes"]], bytes(run["bytes"]))


class FileTests(unittest.TestCase):
    def test_zip_member_detection_write_receipt_and_no_overwrite(self) -> None:
        fixture = Fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "1993.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("Season/BLUS30049-FXG-21/USERDATA", b"not a roster")
                bundle.writestr("Season/BLUS30049-ROS/USERDATA", fixture.ps3())
                bundle.writestr("Season/BLUS30049-ROS/PARAM.SFO", b"\0")
            self.assertEqual(subject.find_roster_member(archive), "Season/BLUS30049-ROS/USERDATA")
            before = hashlib.sha256(archive.read_bytes()).hexdigest()
            output = root / "Roster.ROS"
            receipt = subject.write_conversion(archive, output)
            self.assertEqual(receipt.member, "Season/BLUS30049-ROS/USERDATA")
            self.assertEqual(receipt.receipt_path, root / "Roster.ROS.ps3-import.json")
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), receipt.output_sha256)
            self.assertEqual(output.read_bytes(), fixture.expected())
            stored = json.loads(receipt.receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["schema"], subject.RECEIPT_SCHEMA)
            self.assertEqual(stored["output"]["sha256"], receipt.output_sha256)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), before)
            with self.assertRaisesRegex(subject.PS3RosterConvertError, "refusing to overwrite"):
                subject.write_conversion(archive, output)
            other = root / "again.ROS"
            with self.assertRaisesRegex(subject.PS3RosterConvertError, "already uses the Xbox 360 layout"):
                subject.write_conversion(output, other)
            self.assertFalse(other.exists())
            self.assertFalse(subject.receipt_path_for(other).exists())


class RetailMemberTests(unittest.TestCase):
    """The real 1993 NFL Season member; skipped precisely when the archive is absent."""

    @classmethod
    def setUpClass(cls) -> None:
        if not PS3_ZIP.is_file():
            raise unittest.SkipTest(f"PS3 archive not present: {PS3_ZIP}")
        cls.source = subject.read_source(PS3_ZIP)
        if hashlib.sha256(cls.source).hexdigest() != PS3_MEMBER_SHA256:
            raise unittest.SkipTest("PS3 roster member differs from the studied 2026-09-03 file")
        cls.output, cls.receipt = subject.convert(cls.source)

    def test_member_selection_and_pointer_rule_counts(self) -> None:
        self.assertEqual(subject.find_roster_member(PS3_ZIP), PS3_MEMBER)
        counts = self.receipt["counts"]
        self.assertEqual((counts["players"], counts["teams"], counts["team_memberships"], counts["playbook_labels"]), (2254, 40, 1680, 69))
        self.assertEqual(counts["string_references"], 42825)
        self.assertEqual(counts["odd_references"], 1647)
        self.assertEqual(counts["odd_allocations"], 208)
        self.assertEqual(counts["interior_allocations_garbage_outer"], 76)
        self.assertEqual(counts["below_pool_references"], 3)
        self.assertEqual(counts["palette_colours_rotated"], 2660)
        self.assertEqual(counts["odd_runs_relocated"], 0)
        self.assertEqual((counts["odd_runs"], counts["odd_runs_shifted"], counts["odd_run_bytes"]), (5, 5, 2600))
        self.assertEqual((counts["interior_allocations"], counts["interior_references"]), (675, 1010))
        self.assertEqual((counts["garbage_allocations"], counts["garbage_references"]), (5, 9))
        self.assertEqual(counts["empty_references_canonicalised"], 3655)
        self.assertEqual(counts["references_repointed"], 4991)
        self.assertEqual(self.receipt["output"]["changed_byte_count"], 24527)
        self.assertEqual(self.receipt["output"]["sha256"], CONVERTED_SHA256)
        self.assertEqual(counts["skipped_tables"], [])
        audit = subject.inspect_structure(self.source)
        nickname_odd = sum(1 for r in audit.references if r.table == 0 and r.column == 0x118 and r.target % 2)
        self.assertEqual(nickname_odd, 1344)
        team_odd = sum(1 for r in audit.references if r.table == 4 and r.target % 2)
        self.assertEqual(team_odd, 128)

    def test_strict_readers_names_and_idempotence(self) -> None:
        with self.assertRaisesRegex(players.SaveRosterPlayerError, "not UTF-16BE aligned"):
            players.inspect_bytes(self.source)
        document = players.inspect_bytes(self.output)
        nicknames = [document.player_text_values(i)["nickname"] for i in range(players.PLAYER_COUNT)]
        self.assertEqual(sum(1 for n in nicknames if n), 11)
        self.assertEqual(len(labels_reader.parse_save(self.output).playbooks), 69)
        names = []
        for team in range(40):
            field = 0x0B8078 + team * players.TEAM_STRIDE + 0xA8
            names.append(save_layout._decode_utf16be(self.output, save_layout._relative_target(self.output, field, "t"), "t"))
        self.assertEqual((names[0], names[32], names[39]), ("Oilers", "Lions", "Cobras"))
        self.assertEqual(sum(1 for n in names if n and not n.startswith("*")), 32)
        with self.assertRaisesRegex(subject.PS3RosterConvertError, "already uses the Xbox 360 layout"):
            subject.convert(self.output)
        patched, manifest = players.make_patch(document, field_edits=(players.PlayerFieldEdit(0, "jersey_number", 7 if document.player_values(0)["jersey_number"] != 7 else 8),))
        self.assertTrue(players.verify_patch(document, patched, manifest)["verified"])

    def test_runtime_words_match_the_xbox_fixture(self) -> None:
        if not XBOX_FIXTURE.is_file():
            raise unittest.SkipTest(f"Xbox fixture not present: {XBOX_FIXTURE}")
        xbox = XBOX_FIXTURE.read_bytes()
        self.assertEqual(self.output[0x80:0xA0], xbox[0x80:0xA0])
        self.assertEqual(self.output[subject.RUNTIME_BLOCK_OFFSET: subject.RUNTIME_BLOCK_OFFSET + 32],
                         xbox[subject.RUNTIME_BLOCK_OFFSET: subject.RUNTIME_BLOCK_OFFSET + 32])
        for bank in range(5):
            magic = FIRST_BANK_MAGIC + bank * subject.BANK_STRIDE
            for relative in subject.BANK_WORD_OFFSETS:
                self.assertEqual(self.output[magic + relative: magic + relative + 4], xbox[magic + relative: magic + relative + 4])
        from mod_editor.apf_studio.ps3_roster_probe import compare_rosters
        report = compare_rosters(self.output, xbox)
        self.assertTrue(report["existing_parsers_accept_both"])
        self.assertTrue(report["root_counts_equal"])
        self.assertEqual(report["root_pointer_differences"], [])
        self.assertEqual(report["ps3"]["name_pointer_audit"]["nickname"]["odd_target_count"], 0)


if __name__ == "__main__":
    unittest.main()
