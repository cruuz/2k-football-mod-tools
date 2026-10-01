"""Historic teams keep their retail art on spare styles: census, spare choice, aggregate members, team files and the
archive layout, from the private retail extraction (read-only). EXPERIMENTAL / UNWITNESSED.

The disc transaction itself (packs rewritten at the image end, nodes switched, rollback) runs on a private copy of
the retail image in the job's scratch proof; these tests keep to bounded reads.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_historic_styles as hs  # noqa: E402

RETAIL = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
RETAIL_ISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")


class RulesTests(unittest.TestCase):
    """Retail-free."""

    def test_spare_choice(self):
        styles = {"18": 8, "19": 7, "21": 15, "01": 14}
        self.assertEqual(hs.spare_style("18", styles), 8)
        self.assertEqual(hs.spare_style("19", styles, {"19": {7}}), 8)       # the Jets' orphan style-7 art
        self.assertEqual(hs.spare_style("21", styles), hs.EAGLES_SPARE)
        self.assertEqual(hs.spare_style("01", styles), 14)
        with self.assertRaises(hs.HistoricStylesError):
            hs.spare_style("01", styles, {"01": {14}})

    def test_member_hash_is_the_plain_utf16_crc(self):
        # CACR member hashes are CRC-32 of the name as written; outer names hash upper case
        self.assertNotEqual(hs.member_hash("logo_18_0"), hs.name_id("logo_18_0"))


@unittest.skipUnless((RETAIL / "vc_53450030/0").is_file(), "user-owned USA disc folder absent")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = hs.Source(RETAIL)
        cls.main = cls.src.get(identity=hs.ROSTER_OUTER_ID)
        cls.styles = hs.franchise_styles(cls.main)

    @classmethod
    def tearDownClass(cls):
        cls.src.__exit__(None, None, None)

    def test_styles_and_taken(self):
        self.assertEqual(len(self.styles), 32)
        self.assertEqual(self.styles["21"], 15)                               # the Eagles use every index
        self.assertEqual(hs.taken_styles(self.src, self.styles), {"06": {6, 7}, "19": {7}})

    def test_aggregate_records_match_their_slots(self):
        for aggregate in hs.AGGREGATES:
            record = self.src.get(identity=aggregate["record"])
            cdf = self.src.get(identity=aggregate["cdf"])
            count, slot, hashes = hs.parse_record(record)
            self.assertEqual(len(cdf), count * slot)
            for i in (0, count // 2, count - 1):
                self.assertEqual(hs.member_hash(hs.slot_name(cdf[i * slot:(i + 1) * slot])), hashes[i])

    def test_renamed_copies_keep_the_texture_and_are_found(self):
        import nfl_txtr as tx
        for aggregate in hs.AGGREGATES:
            record = self.src.get(identity=aggregate["record"])
            cdf = self.src.get(identity=aggregate["cdf"])
            added = {}
            for pattern in aggregate["members"]:
                old = hs.member_slot(record, cdf, pattern.format(c="18", s=0))
                new = hs.rename_slot(old, pattern.format(c="18", s=8))
                decoded = []
                for raw in (old, new):
                    chunk = tx.parse_chunks(raw, allow_trailing=True)[0]
                    out, _ = tx.decode_chunk(raw, chunk)
                    info = tx.parse_texture(out, chunk)
                    decoded.append(((info.width, info.height, info.format_name), tx.texture_to_rgba(out, chunk, info)))
                self.assertEqual(decoded[0], decoded[1], pattern)
                added[pattern.format(c="18", s=8)] = new
            grown_record, grown_cdf = hs.grow_aggregate(record, cdf, added)
            count, slot, _ = hs.parse_record(grown_record)
            self.assertEqual(count, hs.parse_record(record)[0] + len(added))
            for name, data in added.items():
                self.assertEqual(hs.member_slot(grown_record, grown_cdf, name), data)
            first = aggregate["members"][0].format(c="18", s=0)
            self.assertEqual(hs.member_slot(grown_record, grown_cdf, first), hs.member_slot(record, cdf, first))
            with self.assertRaises(hs.HistoricStylesError):
                hs.grow_aggregate(grown_record, grown_cdf, added)

    def test_team_file_edit_and_its_inverse(self):
        raw = self.src.get("h-18-2003-giants-0.iff")
        self.assertEqual(hs.historic_style(raw), ("18", 0))
        new = hs.with_spare(raw, 8)
        self.assertEqual(hs.historic_style(new), ("18", 8))
        (at, _code), = hs.team_records(new)[:1]
        self.assertEqual(struct.unpack_from("<HH", new, 32 + at + hs.TABLE + 4 * 7), hs.SPARE_YEARS)
        self.assertEqual(hs.undo_spare(new, "18", 8), raw)
        eagles = self.src.get("h-21-2004-eagles-0.iff")
        (at, _code), = hs.team_records(eagles)[:1]
        pair = struct.unpack_from("<HH", eagles, 32 + at + hs.TABLE + 4 * (hs.EAGLES_SPARE - 1))
        moved = hs.with_spare(eagles, hs.EAGLES_SPARE)
        self.assertEqual(struct.unpack_from("<HH", moved, 32 + at + hs.TABLE + 4 * (hs.EAGLES_SPARE - 1)), pair)
        self.assertEqual(hs.historic_style(moved), ("21", hs.EAGLES_SPARE))

    @unittest.skipUnless(RETAIL_ISO.is_file(), "user-owned USA disc image absent")
    def test_retail_plan_and_layout(self):
        from mod_editor.core import nfl2k5_music_archive as archive
        with archive.Disc(RETAIL_ISO, descriptors=()) as disc:
            target = hs.Target(disc)
            plan = hs.plan_spares(target, self.src)
            self.assertEqual(len(plan["affected"]), 15)                      # retail: 18 files and rows 20..25
            self.assertEqual(plan["spares"]["19"], 8)
            self.assertEqual(plan["spares"]["21"], hs.EAGLES_SPARE)
            edits, appended = hs.compile_spares(target, self.src, plan)
            layout = hs.rewrite_plan(disc, edits, appended)
            self.assertEqual(appended[-1][0], hs.FILLER)
            self.assertEqual(layout["count_after"] - layout["count_before"], len(appended))
            self.assertEqual(sum(layout["sizes"]) % 2048, 0)
            self.assertEqual(layout["changed"], ["0", "3", "A", "B", "F"])


if __name__ == "__main__":
    unittest.main()
