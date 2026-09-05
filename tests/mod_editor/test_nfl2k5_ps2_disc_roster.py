"""Conformance suite for the PS2 NFL 2K5 disc-roster on-disc writer.

**No game data.** Every image asserted against here is built in a temp
directory: a real ISO9660 volume, a real ``/VC_20919`` two-pack archive, a real
outer index, and real ``ROST`` resource chunks whose ten root tables are reached
by the engine's own ``target = field + int32le(field) - 1`` pointer rule.  A CI
runner with an empty disk runs the whole file green.

What is asserted hard, because these are the properties a roster edit can
quietly lose:

* **the arena never moves.** A name is written into the exact bytes the old one
  occupied, terminator included; a table count or offset that shifted is the
  shape of a write that broke every pointer behind it, and the verifier fails
  on it.
* a masked jersey / face-shield write **preserves every unrelated bit** of the
  word it lands in -- the two fields share a u32 with data this capability has
  not proved.
* **every refusal leaves no destination behind** -- an over-length name, an
  out-of-range player index, an unsafe (compressed) target, a zero-capacity
  placeholder slot, a catalogue that disagrees with the image, the reserved
  face-shield value 3, and a no-op.
* **the verifier can fail.** A byte changed outside every declared range, a
  declared span rewritten behind the receipt's back, a moved table pointer, and
  a receipt that lies about the stock bytes each raise.
"""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import nfl2k5_ps2_disc_roster_patch as patcher  # noqa: E402
import nfl2k5_ps2_disc_roster_target_catalog as catalog_tool  # noqa: E402
import nfl2k5_ps2_disc_roster_verify as verifier  # noqa: E402


def _recipe(*edits, roster: str = "boot") -> dict:
    return {"schema": patcher.RECIPE_SCHEMA, "roster": roster,
            "edits": list(edits)}


class _RosterTestCase(unittest.TestCase):
    """Base class: a private temp directory and one synthetic stock image."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ps2rost-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.source = self.work / "stock.iso"
        self.source.write_bytes(catalog_tool.build_synthetic_iso())
        self.catalog = catalog_tool.build_catalog(str(self.source))
        self.boot = catalog_tool.boot_roster(self.catalog)

    def edited(self, *edits, name: str = "edited.iso", roster: str = "boot",
               pinned=None):
        destination = self.work / name
        receipt = patcher.apply(
            self.source, destination,
            patcher.parse_recipe(_recipe(*edits, roster=roster)),
            pinned_catalog=self.catalog if pinned is None else pinned)
        return destination, receipt

    def refused(self, *edits, name: str = "refused.iso", roster: str = "boot",
                pinned=None):
        destination = self.work / name
        with self.assertRaises(patcher.RosterPatchError) as caught:
            patcher.apply(self.source, destination,
                          patcher.parse_recipe(_recipe(*edits, roster=roster)),
                          pinned_catalog=pinned)
        self.assertFalse(destination.exists(),
                         "a refusal must not leave a destination behind")
        return str(caught.exception)


class CatalogueTests(_RosterTestCase):
    def test_exactly_one_rost_is_the_boot_roster(self) -> None:
        self.assertEqual(self.catalog["summary"]["boot_rosters"], 1)
        self.assertEqual(self.boot["label"], "roster")
        self.assertEqual(self.catalog["summary"]["historic_rosters"], 1)

    def test_the_arena_decodes_at_the_disc_version_and_root(self) -> None:
        self.assertEqual(self.boot["version"], catalog_tool.DISC_VERSION)
        self.assertEqual(self.boot["root"], catalog_tool.DISC_ROOT)
        self.assertEqual(self.boot["tables"]["primary_players"], 3)
        self.assertEqual(self.boot["tables"]["secondary_players"], 1)

    def test_a_compressed_rost_never_reaches_the_catalogue(self) -> None:
        self.assertEqual(self.catalog["summary"]["compressed"], 0)
        self.assertEqual(self.catalog["summary"]["rejected"], 1)
        self.assertIn("compressed", self.catalog["rejected"][0]["reason"])

    def test_name_capacity_is_the_stored_bytes_plus_a_terminator(self) -> None:
        player = catalog_tool.find_player(self.catalog, 0)
        self.assertEqual(player["first_name"], "Duane")
        self.assertEqual(player["first_name_capacity"], len("Duane") * 2 + 2)
        self.assertEqual(player["last_name_capacity"], len("Starks") * 2 + 2)

    def test_a_zero_capacity_placeholder_is_not_writable(self) -> None:
        placeholder = catalog_tool.find_player(self.catalog, 0,
                                               "secondary_players")
        self.assertEqual(placeholder["first_name_capacity"], 2)
        self.assertFalse(placeholder["first_name_writable"])

    def test_the_catalogue_carries_no_packed_equipment_word(self) -> None:
        for player in self.catalog["players"]:
            self.assertNotIn("face_shield", player)
            self.assertEqual(len(player["packed_word_sha256"]), 64)
        self.assertFalse(self.catalog["retail_free"]
                         ["packed_equipment_word_included"])

    def test_every_decoded_jersey_is_in_range(self) -> None:
        for player in self.catalog["players"]:
            self.assertGreaterEqual(player["jersey_number"], 0)
            self.assertLessEqual(player["jersey_number"],
                                 catalog_tool.JERSEY_MAX)


class WriteTests(_RosterTestCase):
    def _word(self, blob: bytes, player: dict) -> int:
        return struct.unpack_from(
            "<I", blob, self.boot["body_offset_in_iso"] + player["packed_word_offset"])[0]

    def test_a_name_and_a_jersey_write_keep_the_image_length(self) -> None:
        destination, receipt = self.edited(
            {"player": 0, "first_name": "Dwane", "jersey_number": 7})
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)
        self.assertEqual(len(receipt["edits"]), 2)
        kinds = sorted(row["kind"] for row in receipt["edits"])
        self.assertEqual(kinds, ["name", "packed"])

    def test_a_masked_write_preserves_every_unrelated_bit(self) -> None:
        player = catalog_tool.find_player(self.catalog, 0)
        destination, _receipt = self.edited({"player": 0, "jersey_number": 7})
        before = self._word(self.source.read_bytes(), player)
        after = self._word(destination.read_bytes(), player)
        self.assertEqual((after >> patcher.JERSEY_SHIFT) & 0x7F, 7)
        self.assertEqual(after & ~patcher.JERSEY_MASK,
                         before & ~patcher.JERSEY_MASK)

    def test_a_face_shield_write_preserves_the_jersey(self) -> None:
        player = catalog_tool.find_player(self.catalog, 0)
        destination, _receipt = self.edited({"player": 0, "face_shield": 2})
        before = self._word(self.source.read_bytes(), player)
        after = self._word(destination.read_bytes(), player)
        self.assertEqual((after >> patcher.FACE_SHIELD_SHIFT) & 0x3, 2)
        self.assertEqual((after >> patcher.JERSEY_SHIFT) & 0x7F,
                         (before >> patcher.JERSEY_SHIFT) & 0x7F)

    def test_a_shorter_name_fills_its_whole_allocation_with_zeros(self) -> None:
        player = catalog_tool.find_player(self.catalog, 2)   # "Coby Rhinehart"
        destination, _receipt = self.edited({"player": 2, "last_name": "Ryn"})
        at = self.boot["body_offset_in_iso"] + player["last_name_offset"]
        capacity = player["last_name_capacity"]
        written = destination.read_bytes()[at:at + capacity]
        self.assertEqual(written,
                         "Ryn".encode("utf-16le") + b"\x00" * (capacity - 6))

    def test_the_arena_geometry_is_untouched(self) -> None:
        destination, _receipt = self.edited(
            {"player": 0, "first_name": "Dwane", "jersey_number": 7})
        after = catalog_tool.build_catalog(str(destination))
        before_boot = self.boot
        after_boot = catalog_tool.boot_roster(after)
        self.assertEqual(after_boot["tables"], before_boot["tables"])
        self.assertEqual(after_boot["table_offsets"], before_boot["table_offsets"])
        self.assertEqual(after_boot["stored_size"], before_boot["stored_size"])
        self.assertEqual(catalog_tool.find_player(after, 0)["first_name"], "Dwane")

    def test_the_source_image_is_never_written(self) -> None:
        before = self.source.read_bytes()
        self.edited({"player": 0, "jersey_number": 7})
        self.assertEqual(self.source.read_bytes(), before)


class RefusalTests(_RosterTestCase):
    def test_an_over_length_name_is_refused(self) -> None:
        message = self.refused({"player": 0, "first_name": "Bartholomewcubbins"})
        self.assertIn("may not grow the arena", message)

    def test_an_out_of_range_player_index_is_refused(self) -> None:
        message = self.refused({"player": 99, "jersey_number": 1})
        self.assertIn("out-of-range index", message)

    def test_an_unsafe_compressed_roster_is_refused(self) -> None:
        message = self.refused({"player": 0, "jersey_number": 1},
                               roster="outer:2")
        self.assertIn("unsafe target", message)
        self.assertIn("recompressed back into the stored span", message)

    def test_a_zero_capacity_placeholder_slot_is_refused(self) -> None:
        message = self.refused({"pool": "secondary_players", "player": 0,
                                "first_name": "Al"})
        self.assertIn("zero-capacity slot is refused", message)

    def test_a_catalogue_that_disagrees_with_the_image_is_refused(self) -> None:
        forged = json.loads(json.dumps(self.catalog))
        for row in forged["rosters"]:
            row["body_sha256"] = "0" * 64
        message = self.refused({"player": 0, "jersey_number": 3}, pinned=forged)
        self.assertIn("not the stock disc", message)

    def test_a_no_op_edit_is_refused(self) -> None:
        message = self.refused({"player": 0, "jersey_number": 28})
        self.assertIn("already carries those packed values", message)

    def test_the_reserved_face_shield_value_is_refused(self) -> None:
        with self.assertRaises(patcher.RosterPatchError) as caught:
            patcher.parse_recipe(_recipe({"player": 0, "face_shield": 3}))
        self.assertIn("reserved value 3 is refused", str(caught.exception))

    def test_an_out_of_range_jersey_number_is_refused(self) -> None:
        with self.assertRaises(patcher.RosterPatchError) as caught:
            patcher.parse_recipe(_recipe({"player": 0, "jersey_number": 100}))
        self.assertIn("0..99", str(caught.exception))

    def test_a_recipe_may_not_name_an_unproved_field(self) -> None:
        with self.assertRaises(patcher.RosterPatchError) as caught:
            patcher.parse_recipe(_recipe({"player": 0, "speed": 99}))
        self.assertIn("unknown keys", str(caught.exception))

    def test_an_existing_destination_is_refused(self) -> None:
        destination, _receipt = self.edited({"player": 0, "jersey_number": 7})
        with self.assertRaises(patcher.RosterPatchError) as caught:
            patcher.apply(self.source, destination,
                          patcher.parse_recipe(_recipe({"player": 1,
                                                        "jersey_number": 9})))
        self.assertIn("already exists", str(caught.exception))


class VerifierTests(_RosterTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.destination, self.receipt = self.edited(
            {"player": 0, "first_name": "Dwane", "jersey_number": 7},
            {"player": 1, "face_shield": 2})

    def _poke(self, offset: int, value: bytes, name: str) -> Path:
        candidate = self.work / name
        candidate.write_bytes(self.destination.read_bytes())
        with open(str(candidate), "r+b") as handle:
            handle.seek(offset)
            handle.write(value)
        return candidate

    def test_a_correct_write_verifies(self) -> None:
        report = verifier.verify(self.source, self.destination, self.receipt)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["edits_checked"], 3)
        self.assertEqual(report["name_edits_checked"], 1)
        self.assertEqual(report["packed_edits_checked"], 2)
        self.assertEqual(report["target_label"], "roster")
        self.assertGreater(report["unchanged_bytes_compared"], 0)

    def test_a_json_round_trip_of_the_receipt_verifies_identically(self) -> None:
        report = verifier.verify(self.source, self.destination,
                                 json.loads(json.dumps(self.receipt)))
        self.assertEqual(report["result"], "PASS")

    def test_a_byte_outside_every_declared_range_fails(self) -> None:
        stray = (self.boot["body_offset_in_iso"]
                 + catalog_tool.find_player(self.catalog, 2)["packed_word_offset"])
        candidate = self._poke(stray, b"\x00\x00\x00\x00", "stray.iso")
        with self.assertRaises(verifier.RosterVerifyError) as caught:
            verifier.verify(self.source, candidate, self.receipt)
        self.assertIn("outside every declared range", str(caught.exception))

    def test_a_declared_span_rewritten_behind_the_receipt_fails(self) -> None:
        player = catalog_tool.find_player(self.catalog, 0)
        candidate = self._poke(
            self.boot["body_offset_in_iso"] + player["first_name_offset"],
            "Zed\x00".encode("utf-16le"), "forged.iso")
        with self.assertRaises(verifier.RosterVerifyError):
            verifier.verify(self.source, candidate, self.receipt)

    def test_a_moved_table_pointer_fails(self) -> None:
        candidate = self._poke(
            self.boot["body_offset_in_iso"] + self.boot["root"] + 0x04,
            b"\x99\x99\x00\x00", "moved.iso")
        with self.assertRaises(verifier.RosterVerifyError):
            verifier.verify(self.source, candidate, self.receipt)

    def test_a_receipt_that_lies_about_the_stock_bytes_fails(self) -> None:
        forged = json.loads(json.dumps(self.receipt))
        forged["edits"][0]["before_sha256"] = "0" * 64
        with self.assertRaises(verifier.RosterVerifyError):
            verifier.verify(self.source, self.destination, forged)

    def test_a_packed_edit_claiming_no_fields_fails(self) -> None:
        forged = json.loads(json.dumps(self.receipt))
        for row in forged["edits"]:
            if row["kind"] == "packed":
                row["fields"] = []
        with self.assertRaises(verifier.RosterVerifyError):
            verifier.verify(self.source, self.destination, forged)

    def test_dropping_a_declared_range_fails(self) -> None:
        forged = json.loads(json.dumps(self.receipt))
        forged["declared_ranges"] = forged["declared_ranges"][:1]
        with self.assertRaises(verifier.RosterVerifyError):
            verifier.verify(self.source, self.destination, forged)

    def test_the_verifier_does_not_import_the_writer_or_its_parsers(self) -> None:
        source = (_REPO_ROOT / "tools" / "nfl2k5_ps2_disc_roster_verify.py").read_text(
            encoding="utf-8")
        head = source.split("def selftest", 1)[0]
        for forbidden in ("import nfl2k5_ps2_disc_roster_patch",
                          "import nfl2k5_ps2_disc_roster_target_catalog",
                          "import nfl_roster",
                          "import ps2_iso9660_writer",
                          "import ps2_iso9660 as"):
            self.assertNotIn(forbidden, head)


class SelfTestTests(unittest.TestCase):
    def test_every_module_self_test_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ps2rost-selftest-") as work:
            self.assertEqual(catalog_tool.selftest(work), 0)
            self.assertEqual(patcher.selftest(work), 0)
            self.assertEqual(verifier.selftest(work), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
