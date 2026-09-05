"""Year-byte and moving-century DOB regression tests, with no private data required."""
import datetime as dt
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_save_writer as writer
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_save_rost as rost
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body
from tests.mod_editor.test_nfl2k5_save_rost import fixture


class YearTests(unittest.TestCase):
    def test_both_apis_write_only_one_byte_at_every_supported_index(self):
        original = bytearray(synthetic_franchise(year_field=255))
        original[0x91327] = 0xA5
        for base in (2004, 2026):
            for index in range(128):
                with self.subTest(base=base, index=index):
                    save = fs.FranchiseSave(original, base_year=base)
                    legacy = bytearray(original)
                    save.set_display_year(base + index)
                    receipt = writer.apply_franchise_year(legacy, base + index, base_year=base)
                    expected = bytearray(original)
                    expected[0x91326] = index
                    self.assertEqual(save.to_bytes(), expected)
                    self.assertEqual(legacy, expected)
                    self.assertEqual(receipt["bytes"], 1)
                    self.assertEqual(receipt["old_year_field"], 255)
                    fields = writer.read_franchise_fields(legacy, base_year=base)
                    loaded = fs.FranchiseSave(save.to_bytes(), base_year=base)
                    self.assertEqual((fields["display_year"], fields["season_ordinal"]), (base + index, index + 1))
                    self.assertEqual((loaded.header.display_year, loaded.header.season_ordinal), (base + index, index + 1))
                    self.assertEqual(loaded.buffer[0x91327], 0xA5)
        self.assertEqual(original[0x91326:0x91328], b"\xff\xa5")

    def test_index_128_and_invalid_values_refused_without_any_mutation(self):
        original = synthetic_franchise()
        for base in (2004, 2026):
            for index in (-1, 128, 255, 256, 1.5, True):
                save = fs.FranchiseSave(original, base_year=base)
                with self.assertRaises(fs.FranchiseSaveError):
                    save.set_year_field(index)
                self.assertEqual(save.to_bytes(), original)
            for year in (base - 1, base + 128, base + 255, 2053.0, True):
                save = fs.FranchiseSave(original, base_year=base)
                legacy = bytearray(original)
                with self.assertRaises(fs.FranchiseSaveError):
                    save.set_display_year(year)
                with self.assertRaises(writer.SaveWriterError):
                    writer.apply_franchise_year(legacy, year, base_year=base)
                self.assertEqual(save.to_bytes(), original)
                self.assertEqual(legacy, original)

    def test_terminal_save_is_readable_and_resigns_losslessly(self):
        original = bytearray(synthetic_franchise(year_field=128))
        original[0x91327] = 0xFF
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "source"
            source.mkdir()
            (source / "SAVEGAME.DAT").write_bytes(original)
            (source / "EXTRA").write_bytes(rr.sign_save(original))
            save = fs.FranchiseSave.load(source, base_year=2026)
            self.assertEqual((save.header.year_field, save.header.display_year), (128, 2154))
            save.write(root / "copy")
            back = fs.FranchiseSave.load(root / "copy", base_year=2026)
            self.assertEqual(back.to_bytes(), original)
            self.assertEqual(writer.read_save(root / "copy" / "SAVEGAME.DAT", base_year=2026)["franchise"]["year_field"], 128)


class BirthTests(unittest.TestCase):
    def test_moving_century_sentinels_and_gregorian_birth_dates(self):
        self.assertGreaterEqual(rr.NUMERIC_LIMITS["birth_year"][1], 2153)
        self.assertEqual(rr.encode_birth_year(2031, 2053), 31)
        for current in (2004, 2026, 2053, 2098, 2099, 2100, 2101, 2104, 2125, 2126, 2153):
            for age in (0, 20, 21, 22, 23, 50, 99):
                year = current - age
                raw = rr.encode_birth_year(year, current)
                self.assertEqual(raw, year % 100)
                self.assertEqual(rr.decode_birth_year(raw, current), year)
                record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), reference_year=current)
                record.birth_date = dt.date(year, 3, 1)
                restored = rr.PlayerRecord.decode(record.encode(), reference_year=current)
                self.assertEqual(restored.birth_date, dt.date(year, 3, 1))
                self.assertEqual(record.copy().birth_date, record.birth_date)
                for invalid in (current + 1, current - 100):
                    before = record.encode()
                    with self.assertRaises(rr.RosterRecordError):
                        record.birth_date = dt.date(invalid, 7, 4)
                    self.assertEqual(record.encode(), before)
        record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), reference_year=2126)
        for birth, valid in ((2096, True), (2100, False), (2104, True)):
            record.birth_year = birth
            record.values.update(birth_month=2, birth_day=29)
            self.assertEqual(record.birth_date, dt.date(birth, 2, 29) if valid else None)

    def test_all_legacy_encodings_remain_lossless_and_noop_edits_preserve_them(self):
        for raw in range(128):
            record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE))
            record.values.update(birth_year_low=raw & 7, birth_year_high=raw >> 3,
                                 birth_month=3, birth_day=24)
            original = record.encode()
            expected = 1900 + raw if raw > 54 else 2000 + raw
            self.assertEqual(record.birth_year, expected)
            record.birth_year = expected
            self.assertEqual(record.encode(), original)
            record.reference_year = 2126
            self.assertEqual(record.birth_year % 100, raw % 100)
            self.assertTrue(2027 <= record.birth_year <= 2126)
            record.birth_year = record.birth_year
            self.assertEqual(record.encode(), original)

    def test_documents_carry_current_year_through_copy_edit_and_reload(self):
        original = bytearray(synthetic_franchise(year_field=27))
        original[0x91327] = 0xEE
        legacy = rr.RosterDocument(original, base=0x300, base_year=2026)
        modern = rost.decode(original, base_year=2026)
        self.assertEqual(legacy.reference_year, 2053)
        self.assertEqual(modern.reference_year, 2053)
        player = legacy.players[0]
        player.record.birth_year = 2031
        modern.edit_player(player.pool, player.index, {"birth_year": 2031})
        self.assertEqual(legacy.to_body(), modern.to_bytes())
        changed = {i for i, (a, b) in enumerate(zip(original, modern.to_bytes())) if a != b}
        self.assertTrue(changed <= {player.offset + 0x1A, player.offset + 0x1B})
        self.assertTrue(changed)
        self.assertEqual(rost.decode(modern.to_bytes(), base_year=2026).by_key[player.pool, player.index].record.birth_year, 2031)
        save = fs.FranchiseSave(modern.to_bytes(), base_year=2026)
        self.assertEqual(save.roster.players[0].record.birth_year, 2031)
        save.set_year_field(127)
        self.assertEqual(save.roster.reference_year, 2153)
        self.assertEqual(save.buffer[0x91327], 0xEE)

    def test_no_year_inferred_from_opaque_suffix_and_context_edits_are_atomic(self):
        doc = rost.decode(fixture(), reference_year=2104)
        doc.edit_player("primary", 0, {"birth_year": 2082})
        self.assertEqual(rost.decode(doc.to_bytes(), reference_year=2104).players[0].record.birth_year, 2082)
        before = doc.to_bytes()
        with self.assertRaises(rost.SaveRostError):
            doc.edit_player("primary", 0, {"speed": 99, "birth_year": 2105})
        self.assertEqual(doc.to_bytes(), before)
        self.assertIsNone(rost.decode(fixture()).reference_year)
        legacy = rr.load_body(synthetic_body())
        before = legacy.to_body()
        legacy.set_reference_year(2104)
        self.assertEqual(legacy.to_body(), before)
        for year in (True, 99, 10000, 2053.0):
            with self.assertRaises(rost.SaveRostError):
                rost.decode(fixture(), reference_year=year)


if __name__ == "__main__":
    unittest.main()
