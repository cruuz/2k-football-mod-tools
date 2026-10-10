"""Final-disc selection scope and native environment/alias isolation, all 51 rows."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import mvx_venues as mvx
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_espn25_more_moments as moments
from mod_editor.core import nfl2k5_historic_styles as historic
from mod_editor.core import nfl2k5_espn25_rosters as rosters
from mod_editor.core import nfl2k5_moment_venues as venues

DISC = Path(os.environ.get("MVX_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6 (2026-10-08 final).xiso.iso"))


class Data(unittest.TestCase):
    def test_compiler_and_plan_cover_all_51_and_preserve_scene_donors(self):
        self.assertEqual(mvx.compile_catalog(), fields.DATA.read_text())
        rows = mvx.plan()["selections"]
        self.assertEqual(len(rows), 51)
        self.assertEqual([r["row"] for r in rows if r["before"] != r["after"]],
                         [2, 4, 5, 6, 12, 13, 21, 27, 30, 36, 51])
        for row, decision in zip(fields.catalog(), rows):
            self.assertEqual(row["native_stadium_index"], decision["after"])
            self.assertEqual((row["source_kind"], row["source_prefix"]),
                             (decision["source_kind"], decision["source_prefix"]))
        # The two Titans games already had the correct available buildings.
        self.assertEqual(rows[21]["before"], rows[21]["after"])
        self.assertEqual(rows[31]["before"], rows[31]["after"])

    def test_both_dated_profiles_recognized_without_granting_other_dates(self):
        data = moments.Data.load()
        current = moments._historical_stadiums(data)
        old = moments._historical_stadiums(data, previous=True)
        for row in mvx.plan()["selections"]:
            self.assertEqual(current[row["row"] - 1], row["after"])
            self.assertEqual(old[row["row"] - 1], row["before"])
        changed = json.loads(fields.DATA.read_text())
        changed["moments"][26]["date"] = "2009-02-03"
        with mock.patch.object(moments, "_read_json", return_value=changed):
            self.assertNotIn(26, moments._historical_stadiums(data))
            self.assertNotIn(26, moments._historical_stadiums(data, previous=True))


@unittest.skipUnless(DISC.is_file(), "final v0.6 disc required")
class FinalDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with historic.Source(DISC) as source:
            cls.situ = source.get("situation.iff")
            cls.main = source.get(identity=historic.ROSTER_OUTER_ID)
        cls.xbe = rosters.read_xbe(DISC)
        cls.fixed, cls.receipt = mvx.repair(cls.situ)

    def test_native_repair_11_bytes_only_and_all_51_words_verified(self):
        self.assertEqual(self.receipt["changed_bytes"], 11)
        self.assertEqual(len(self.receipt["edits"]), 11)
        self.assertTrue(self.receipt["outside_scope_identical"])
        restored = bytearray(self.fixed)
        for row in mvx.plan()["selections"]:
            # Independent dated audit expectations, checked on the shared main
            # ROST actually shipped, including unchanged selections.
            metadata_at = 0xD0 + row["after"] * 0x80
            self.assertEqual(struct.unpack_from("<II", self.main, metadata_at + 0x18),
                             (row["expected_indoor"], row["expected_grass"]), row["row"])
            at = 32 + 0x44 + (row["row"] - 1) * 0x6C + 0x10
            self.assertEqual(struct.unpack_from("<I", self.fixed, at)[0], row["after"])
            restored[at:at + 4] = self.situ[at:at + 4]
            self.assertEqual(fields.variant(self.fixed, row["row"] - 1), fields.variant(self.situ, row["row"] - 1))
        self.assertEqual(restored, self.situ)
        self.assertEqual(mvx.repair(self.fixed)[0], self.fixed)
        self.assertEqual(mvx.repair(self.fixed)[1]["changed_bytes"], 0)

    def test_foreign_unowned_byte_mixed_profile_and_foreign_word_refused(self):
        for at in (32 + 0x44 + 0x58, len(self.situ) - 1, 32 + 0x44 + 0x10):
            bad = bytearray(self.situ)
            bad[at] ^= 1
            with self.assertRaises(ValueError):
                mvx.repair(bytes(bad))
        mixed = bytearray(self.situ)
        edit = self.receipt["edits"][0]
        struct.pack_into("<I", mixed, edit["offset"], edit["after"])
        with self.assertRaisesRegex(ValueError, "mixed"):
            mvx.repair(bytes(mixed))

    def test_explicit_stacked_hash_retains_other_jobs_kit_byte(self):
        stacked = bytearray(self.situ)
        stacked[32 + 0x44 + 0x58] ^= 1
        raw = bytes(stacked)
        after, _ = mvx.repair(raw, expected_input_sha256=mvx.sha(raw))
        self.assertEqual(after[32 + 0x44 + 0x58], raw[32 + 0x44 + 0x58])
        with self.assertRaises(ValueError):
            mvx.repair(raw, expected_input_sha256="0" * 64)

    @unittest.skipUnless(importlib.util.find_spec("unicorn"), "existing native harness needs Unicorn")
    def test_real_filename_hook_all_51_and_reentry_to_normal_play(self):
        from nfl2k5_sofi_dome_probe import M
        self.assertEqual(venues.status(self.xbe), "applied")
        machine = M(self.xbe)
        for row in fields.catalog():
            index = row["row"] - 1
            for mode in (8, 0, 1, 4, 5, 6):
                machine.put(0xE5FF80, mode)
                machine.put(0xBF1858, index)
                suffix = fields.variant(self.fixed, index)
                normal = f"{row['source_prefix']}{suffix}.iff"
                machine.u.mem_write(0xB306D0, (normal + "\0").encode("utf-16le"))
                machine.run(0x62C96, 0x62C9B, esi=0x69)
                expected = f"a{index:02d}{suffix}.iff" if mode == 8 else normal
                self.assertEqual(machine.wstr(0xB306D0), expected)
        # No main ROST, XBE or ordinary bundle is an output of this repair.
        with historic.Source(DISC) as source:
            self.assertEqual(source.get(identity=historic.ROSTER_OUTER_ID), self.main)
        self.assertEqual(rosters.read_xbe(DISC), self.xbe)

    @unittest.skipUnless(importlib.util.find_spec("unicorn"), "existing native harness needs Unicorn")
    def test_real_environment_reset_for_changed_rows_keeps_period_alias(self):
        from nfl2k5_sofi_dome_probe import M, ROW, STR, row_bytes
        expected = {2: (0, 1), 4: (0, 0), 5: (0, 1), 6: (0, 0), 12: (0, 0), 13: (0, 0),
                    21: (0, 1), 27: (1, 1), 30: (1, 0), 36: (0, 0), 51: (0, 0)}
        machine = M(self.xbe)
        for row in mvx.plan()["selections"]:
            if row["row"] not in expected:
                continue
            metadata, strings = row_bytes(self.main, row["after"])
            self.assertEqual(struct.unpack_from("<II", metadata, 0x18), expected[row["row"]])
            machine.u.mem_write(ROW, metadata)
            cursor = STR
            for key in (0, 8, 12, 16, 20):
                text = (strings[key] + "\0").encode("utf-16le")
                machine.u.mem_write(cursor, text)
                cursor = (cursor + len(text) + 3) & ~3
            machine.put(0xE5FE64, ROW)
            machine.put(0xE5FF80, 8)
            machine.put(0xBF1858, row["row"] - 1)
            machine.put(0xE60184, 0)
            for at, val in ((0xE5FFA4, 60), (0xE5FFAC, 0.9), (0xE600C0, 500), (0xE600C4, 0.3)):
                machine.f32(at, val)
            machine.skip = {0xE2DB0}
            machine.run(0x62BE0, 0x62CF4)
            # Retail names the bundle before clamping the indoor weather.
            self.assertEqual(machine.wstr(0xB306D0), f"a{row['row'] - 1:02d}dr.iff")
            if expected[row["row"]][0]:
                self.assertEqual(machine.rf(0xE5FFAC), 0)
            else:
                self.assertAlmostEqual(machine.rf(0xE5FFAC), 0.9)


if __name__ == "__main__":
    unittest.main()
