"""Synthetic archive/roster adversarial tests; retail is never a fixture."""
from __future__ import annotations

from dataclasses import replace
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core import apf2k8_scheme_presets as presets
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError
import apf_inner
import apf_outer
import apf_roster
import apf_texture_patch


def book_body(name="O-ZoneBlock"):
    body = bytearray(splb.RESOURCE_SIZE)
    body[12:16] = b"BLPS"
    body[0x30:0x68] = (name.encode("utf-16-be") + b"\0\0").ljust(56, b"\0")
    for record in range(176):
        at = 0x70 + record * 176
        body[at:at + 168] = b"\x13\xff" * 84
    # Four tags initially on plays 0..3, two untagged alternatives.
    for slot in range(6):
        value = (2 << 13) | (min(slot, 4) << 10) | slot
        struct.pack_into(">H", body, 0x70 + slot * 2, value)
    return bytes(body)


def roster_body():
    body = bytearray(apf_roster.EXPECTED_LENGTH)
    offsets = []
    at = apf_roster.ROOT_SIZE
    for index, (count, stride) in enumerate(zip(apf_roster.EXPECTED_COUNTS, apf_roster.EXPECTED_STRIDES)):
        offsets.append(at)
        struct.pack_into(">II", body, index * 8, count, at - (index * 8 + 4) + 1)
        at += count * (stride or 0) + (2 if index == 18 else 0)
    for field in (0x140, 0x144, 0x148):
        struct.pack_into(">I", body, field, at - field + 1)
    strings = {}

    def text_pointer(field, text):
        nonlocal at
        if text not in strings:
            strings[text] = at
            encoded = text.encode("utf-16-be") + b"\0\0"
            body[at:at + len(encoded)] = encoded
            at += len(encoded)
        struct.pack_into(">I", body, field, strings[text] - field + 1)

    offense = sorted(x for x in splb.STOCK_BOOKS.values() if x.startswith("O-"))
    defense = sorted(x for x in splb.STOCK_BOOKS.values() if x.startswith("X-"))
    for index in range(69):
        base = offsets[11] + index * 12
        is_offense = index < 32 or 64 <= index < 68
        text_pointer(base, f"Label{index:02d}")
        text_pointer(base + 4, offense[index % 7] if is_offense else defense[index % 4])
        struct.pack_into(">I", body, base + 8, 0 if is_offense else 0x01000000)
    for index in range(40):
        base = offsets[4] + index * 384
        text_pointer(base + 0xA8, f"Synthetic Team {index}")
        for delta, label in ((0xE0, 0), (0xE4, 32)):
            field = base + delta
            struct.pack_into(">I", body, field, offsets[11] + 12 * label - field + 1)
    return bytes(body)


def iff(body, name, kind):
    encoded = apf_texture_patch.compress_h7a(body, 10)
    packed = struct.pack(">5I", apf_inner.H7A_MAGIC, len(body), len(encoded) + 20, 0, 10) + encoded
    header_size = 0x54
    header = bytearray(header_size)
    struct.pack_into(">8I", header, 0, apf_inner.IFF_MAGIC, header_size,
                     header_size + len(packed), 0, 1, 0xD, 1, 0x25)
    struct.pack_into(">8I", header, 0x20, 0, 0, 0, len(body), 0, header_size, len(packed), 0)
    struct.pack_into(">5I", header, 0x40, 5, zlib.crc32(name.encode()), zlib.crc32(kind.encode()), 1, 0)
    name_bytes = name.encode("utf-16-le") + b"\0\0"
    footer = struct.pack("<5I", 1, 5, 5, 9, len(name_bytes) + 5) + name_bytes + kind.encode("utf-16-le") + b"\0\0"
    data = bytes(header) + packed + struct.pack(">I", apf_inner.NAME_FOOTER_MAGIC) + struct.pack("<I", len(footer)) + footer
    # Leave synthetic compression headroom for deliberately different names.
    return data.ljust(((len(data) + 4095) // 2048) * 2048, b"\0")


def archive_fixture(root):
    resources = [(identity.filename_id(name), iff(book_body(name), "spb", "SPLB"))
                 for name in splb.STOCK_BOOKS.values()]
    resources.append((apf_roster.OUTER_NAME_ID, iff(roster_body(), "roster", "ROST")))
    resources.sort()
    prefix = bytearray(2048)
    whole = bytearray(prefix)
    rows = []
    for key, body in resources:
        rows.append((key, len(whole) // 2048, len(body) // 2048))
        whole.extend(body)
    split = (len(whole) // 2 // 2048) * 2048  # deliberately splits the ROST IFF
    struct.pack_into(">6I", whole, 0, apf_outer.MAGIC, 2048, 2, 0, len(rows), 0)
    for index, (name, size) in enumerate((("0A", split), ("1B", len(whole) - split))):
        struct.pack_into(">II8s", whole, 0x18 + 16 * index, size // 2048, 0,
                         name.encode("utf-16-be").ljust(8, b"\0"))
    for index, row in enumerate(rows):
        struct.pack_into(">3I", whole, 0x38 + 12 * index, *row)
    root.mkdir()
    (root / "0A").write_bytes(whole[:split])
    (root / "1B").write_bytes(whole[split:])
    (root / "default.xex").write_bytes(b"synthetic executable")
    return root / "0A"


class IdentityAndBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = roster_body()

    def test_identity_lists_every_team_and_other_resource_sharers(self):
        report = identity.book_identity_report(identity.parse_roster_identity(self.body))
        self.assertEqual(len(report["assignments"]), 80)
        row = report["assignments"][0]
        self.assertTrue(row["shared"])
        self.assertEqual(len(row["shared_with_team_indices"]), 39)
        self.assertFalse(report["archive_inspected"])

    def test_binding_reuses_strings_and_changes_only_two_pointers(self):
        request = clone.CloneRequest(5, 3, "O-ZoneBlock")
        after, receipt = clone.bind_roster(self.body, [request])
        parsed = identity.parse_roster_identity(after)
        self.assertEqual(parsed.labels[5].kind, "Label05")
        self.assertEqual(parsed.teams[3].offense, 5)
        self.assertLessEqual(receipt["changed_byte_count"], 8)
        self.assertEqual(clone.bind_roster(after, [request])[0], after)

    def test_raw_save_binding_and_missing_resource_are_honest(self):
        raw = b"\0" * 4 + self.body
        after, _ = clone.bind_roster(raw, [clone.CloneRequest(5, 3, "O-ZoneBlock")], raw_save=True)
        parsed = identity.parse_roster_identity(after, raw_save=True)
        report = identity.book_identity_report(parsed)
        row = next(x for x in report["assignments"] if x["team_index"] == 3 and x["side"] == "offense")
        self.assertIsNone(row["resolved_book"])
        self.assertIn("UNKNOWN", row["status"])

    def test_shared_label_and_wrong_side_refused(self):
        for label in (0, 32):
            with self.subTest(label=label), self.assertRaises(ValidationError):
                clone.bind_roster(self.body, [clone.CloneRequest(label, 3, "O-ZoneBlock")])

    def test_duplicate_targets_and_boolean_indices_refused(self):
        with self.assertRaises(ValidationError):
            clone.CloneRequest(True, 0, "O-ZoneBlock")
        with self.assertRaises(ValidationError):
            clone.bind_roster(self.body, [clone.CloneRequest(5, 3, "O-ZoneBlock"),
                                         clone.CloneRequest(6, 3, "O-ZoneBlock")])
        with self.assertRaises(ValidationError):
            clone.requests_from_json(b'{"schema":"a","schema":"b","clones":[]}')
        with self.assertRaises(ValidationError):
            identity.filename_id("Straße")

    def test_clone_verifier_rejects_trailer_tampering_and_long_names(self):
        donor = book_body()
        output = clone.clone_body(donor, "Panthers")
        self.assertTrue(clone.verify_clone_body(donor, output, "Panthers")["identical_except_name"])
        forged = bytearray(output)
        forged[0x118] ^= 1
        with self.assertRaises(ValidationError):
            clone.verify_clone_body(donor, bytes(forged), "Panthers")
        for name in ("a" * 28, "../outside", "snow☃"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                clone.clone_body(donor, name)

    def test_cli_validation_errors_are_refusals_without_outputs(self):
        from tools import apf_book_unlock, apf_book_resolution_probe
        with tempfile.TemporaryDirectory(prefix="book-cli-test-") as temporary:
            root = Path(temporary)
            bad = root / "invalid.json"
            bad.write_text('{"schema":"unknown","clones":[]}')
            output = root / "output"
            with redirect_stderr(io.StringIO()) as errors:
                code = apf_book_unlock.main(["clone", "--source", str(root / "0A"),
                                            "--requests", str(bad), "--output", str(output)])
            self.assertEqual(code, 2)
            self.assertIn("refused", errors.getvalue())
            self.assertFalse(output.exists())
            with redirect_stderr(io.StringIO()):
                code = apf_book_resolution_probe.main(["--pe", str(bad), "--source", str(root / "0A"),
                                                       "--receipt", str(output)])
            self.assertEqual(code, 2)
            self.assertFalse(output.exists())


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="apf-book-test-")
        cls.root = Path(cls.temporary.name)
        cls.index = archive_fixture(cls.root / "source")
        cls.requests = [clone.CloneRequest(5, 3, "O-ZoneBlock"), clone.CloneRequest(6, 4, "O-WestCoast")]
        cls.plan = clone.compile_unlock(cls.index, cls.requests)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_append_sorted_directory_full_byte_verifier_and_repeat(self):
        target = self.root / "built"
        try:
            report = clone.build_new_folder(self.plan, target)
            self.assertTrue(report["verification"]["idempotent_reapply"])
            self.assertEqual(report["verification"]["clone_count_added"], 2)
            self.assertEqual((target / "default.xex").read_bytes(), b"synthetic executable")
            # Tampering with an unrelated pack byte must invalidate the build.
            with (target / "0A").open("r+b") as stream:
                stream.seek(2048 + 0x100)
                value = stream.read(1)
                stream.seek(-1, 1)
                stream.write(bytes([value[0] ^ 1]))
            with self.assertRaises((ValidationError, apf_inner.FormatError)):
                clone.verify_unlock(self.plan, target / "0A")
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_preexisting_destination_and_changed_source_directory_refused(self):
        existing = self.root / "existing"
        existing.mkdir()
        with self.assertRaises(FileExistsError):
            clone.build_new_folder(self.plan, existing)
        with self.assertRaises(ValidationError):
            clone.build_new_folder(self.plan, self.root)
        forged = replace(self.plan, directory_before=b"bad")
        with self.assertRaises(ValidationError):
            clone.build_new_folder(forged, self.root / "must-not-exist")
        self.assertFalse((self.root / "must-not-exist").exists())

    def test_verification_failure_removes_only_owned_output(self):
        forged = replace(self.plan, roster_entry=b"x" * len(self.plan.roster_entry))
        target = self.root / "bad-build"
        with self.assertRaises((ValidationError, apf_inner.FormatError)):
            clone.build_new_folder(forged, target)
        self.assertFalse(target.exists())
        self.assertTrue(self.index.exists())

    def test_changed_source_roster_refused_even_if_rebinding_would_match(self):
        source = self.root / "changed-roster-source"
        target = self.root / "changed-roster-output"
        shutil.copytree(self.index.parent, source)
        try:
            entry = next(x for x in apf_outer.parse_archive(source / "0A").entries
                         if x.name_id == apf_roster.OUTER_NAME_ID)
            cursor = 0
            for segment in entry.segments:
                with (source / segment.pack_name).open("r+b") as stream:
                    stream.seek(segment.pack_offset)
                    stream.write(self.plan.roster_entry[cursor:cursor + segment.size])
                cursor += segment.size
            changed_body = identity.read_disc_roster(source / "0A")
            self.assertEqual(clone.bind_roster(changed_body, self.requests)[0], self.plan.roster_body)
            stale_plan = replace(self.plan, source_index=source / "0A")
            with self.assertRaisesRegex(ValidationError, "roster allocation changed since compilation"):
                clone.build_new_folder(stale_plan, target)
            self.assertFalse(target.exists())
        finally:
            shutil.rmtree(source)

    def test_nonzero_directory_slack_is_not_free_space(self):
        target = self.root / "bad-source"
        shutil.copytree(self.index.parent, target)
        try:
            archive = apf_outer.parse_archive(target / "0A")
            with (target / "0A").open("r+b") as stream:
                stream.seek(archive.table_end)
                stream.write(b"occupied")
            with self.assertRaisesRegex(ValidationError, "zero directory"):
                clone.compile_unlock(target / "0A", self.requests)
        finally:
            shutil.rmtree(target)

    def test_filename_hash_collision_is_refused(self):
        real_hash = clone.filename_id
        def collision(name):
            return real_hash("O-ZoneBlock") if name == "Label05" else real_hash(name)
        with patch.object(clone, "filename_id", side_effect=collision):
            with self.assertRaisesRegex(ValidationError, "collides"):
                clone.compile_unlock(self.index, self.requests)

    def test_round_tripping_overlapping_h7a_is_still_refused(self):
        source = identity.read_resource(self.index, identity.filename_id("O-ZoneBlock"), "spb", "SPLB")
        body = source[3]
        # First twelve bytes are zero. One literal plus length-11/distance-1
        # legally round-trips in the local decoder, but is forbidden for APF.
        tokens = [(False, b"\0"), (True, struct.pack(">H", ((11 - 3) << 10) | 1))]
        tokens.extend((False, bytes([x])) for x in body[12:])
        encoded = bytearray()
        for at in range(0, len(tokens), 8):
            group = tokens[at:at + 8]
            encoded.append(sum((1 << bit) for bit, (match, _) in enumerate(group) if match))
            for _match, value in group:
                encoded.extend(value)
        self.assertEqual(apf_inner.decompress_h7a(bytes(encoded), len(body), 10), body)
        with patch.object(apf_inner, "encode_h7a_preserving_tokens", return_value=(bytes(encoded), {})):
            with self.assertRaisesRegex(ValidationError, "longer than its distance"):
                clone.rebuild_resource(source, body)

    def test_preset_review_mismatch_is_refused_before_creating_output(self):
        result = presets.CompiledPreset(0, b"synthetic", b"synthetic", {"source_sha256": "changed"})
        target = self.root / "preset-not-created"
        with patch.object(presets, "compile_preset", return_value=result):
            with self.assertRaisesRegex(ValidationError, "changed since review"):
                presets.build_presets_folder(self.index, ("wide-zone",), target,
                                             expected_reports=[{"source_sha256": "reviewed"}])
        self.assertFalse(target.exists())


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.body = book_body()
        self.book = splb.parse_book(self.body, 943)
        self.master = {"plays": [{"index": i, "name": f"Play {i}"} for i in range(6)],
                       "formations": [{"index": 0, "name": "I Test"}]}
        self.recipe = {"schema": presets.RECIPE_SCHEMA, "id": "test", "name": "Synthetic preset",
                       "book_type": "O-ZoneBlock", "intent": "Test dependent audible swaps", "limitations": "UNWITNESSED",
                       "play_names": {str(x): f"Play {x}" for x in [1, 2, 3, 4, 5]},
                       "groups": [{"records": [[0, 0, "I Test"]], "keep": [1, 2, 3, 4, 5], "tags": [2, 4, 5, 1]}]}

    def test_dependent_tag_swaps_membership_and_idempotence(self):
        after, report = presets.apply_preset(self.book, self.recipe, self.master)
        self.assertEqual(report["verification"]["changed_records"][0]["removed_play_indices"], [0])
        self.assertEqual(after[0x118:], self.body[0x118:])
        again, repeated = presets.apply_preset(splb.parse_book(after, 943), self.recipe, self.master)
        self.assertEqual(again, after)
        self.assertEqual(repeated["writer_steps"], 0)

    def test_verifier_rejects_wrong_tags_opaque_bits_or_other_records(self):
        after, _ = presets.apply_preset(self.book, self.recipe, self.master)
        for offset in (0x70, 0x118, 0x200, 0x7E04):
            forged = bytearray(after)
            forged[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValidationError):
                presets.verify_preset(self.body, bytes(forged), self.recipe, 943)

    def test_changed_catalog_missing_plays_duplicate_and_empty_recipes_refused(self):
        self.master["plays"][4]["name"] = "Different"
        with self.assertRaises(ValidationError):
            presets.apply_preset(self.book, self.recipe, self.master)
        self.recipe["groups"][0]["keep"] = []
        with self.assertRaises(ValidationError):
            presets.validate_recipe(self.recipe)
        with self.assertRaises(ValidationError):
            presets.decode_recipe(b'{"schema":"a","schema":"b"}')

    def test_shipped_recipe_census_and_no_formation_emptying(self):
        expected = {"wide-zone": 13, "spread-to-run": 21, "pro-power": 20}
        for slug in presets.PRESET_IDS:
            recipe = presets.load_preset(slug)
            self.assertEqual(sum(len(g["records"]) for g in recipe["groups"]), expected[slug])
            self.assertIn("UNWITNESSED", recipe["limitations"])


if __name__ == "__main__":
    unittest.main()
