"""Byte preservation and probability/decision semantics, with optional real USR."""
from pathlib import Path
import csv
import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_vip as v
from mod_editor.core import nfl2k5_coach_tendencies as t
from mod_editor.core.nfl2k5_save_writer import derive_sig_key, sign_save, verify_extra
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES


class DataTests(unittest.TestCase):
    def test_save_container_names_match_real_xbox_vectors(self):
        for name, expected in (("Noah", "006F00611262"), ("MyNFL1", "12051C2F122B"),
                               ("Franchise1", "256B40374FD6"), ("Settings1", "83C3760943CB"),
                               ("NYG Harbaugh", "3F5FD433F703")):
            self.assertEqual(v.save_container_id(name), expected)
        self.assertNotEqual(v.save_container_id("08Lions"), v.save_container_id("08lions"))
        with self.assertRaises(v.VipError):
            v.save_container_id("Name\r\nOther")

    def test_scramble_is_a_called_pass_and_kneel_is_excluded(self):
        row = dict(down=1, play_type="run", rush_attempt=1, qb_scramble=1)
        self.assertTrue(t.scrimmage(row))
        c = t.Counter()
        t.observe(c, row)
        self.assertEqual(t.summarize(c)["pass_rate"], dict(numerator=1, denominator=1, rate=1))
        self.assertEqual(t.summarize(c)["shotgun"]["rate"], None)
        self.assertFalse(t.scrimmage(dict(row, qb_kneel=1)))
        self.assertFalse(t.scrimmage(dict(row, no_play=1)))

    def test_role_cutoffs_do_not_attribute_successor_games(self):
        interval = dict(team="BUF", first_season=2023, last_season=2025, first_date="2023-11-14")
        self.assertFalse(t.matches(dict(posteam="BUF", season=2023, game_date="2023-11-13"), [interval], "posteam"))
        self.assertTrue(t.matches(dict(posteam="BUF", season=2023, game_date="2023-11-19"), [interval], "posteam"))

    def test_run_projection_combines_guard_tackle_but_excludes_unknown_gaps(self):
        c = t.Counter()
        for location, gap in (("left", "guard"), ("left", "tackle"), ("right", "end"), ("middle", None), ("right", None)):
            t.observe(c, dict(play_type="run", rush_attempt=1, run_location=location, run_gap=gap))
        rates = t.summarize(c)
        self.assertEqual(rates["run_lane"]["left_inside"], t.rate(2, 4))
        self.assertEqual(rates["run_lane"]["middle"], t.rate(1, 4))
        self.assertEqual(rates["run_lane"]["right_inside"], t.rate(0, 4))
        self.assertEqual(rates["run_lane_unknown"], 1)

    def test_optional_decisions_exclude_native_mandatory_cases(self):
        row = dict(score_differential=-2, qtr=1, half_seconds_remaining=900)
        self.assertFalse(t.optional_two_point(row))
        self.assertFalse(t.optional_two_point(dict(row, score_differential=5, qtr=4, half_seconds_remaining=299)))
        self.assertTrue(t.optional_two_point(dict(row, score_differential=5, qtr=4, half_seconds_remaining=300)))
        self.assertFalse(t.neutral_fourth(dict(ydstogo=6, yardline_100=70, half_seconds_remaining=400)))
        self.assertTrue(t.neutral_fourth(dict(ydstogo=5, yardline_100=70, half_seconds_remaining=400)))

    def test_native_pool_boundaries_and_sparse_denominators(self):
        row = dict(down=1, ydstogo=10, yardline_100=50, score_differential=0, qtr=2, half_seconds_remaining=300)
        self.assertEqual(t.projected_pool(row), 2)
        self.assertEqual(t.projected_pool(dict(row, down=3, ydstogo=2)), 8)
        self.assertEqual(t.projected_pool(dict(row, down=3, ydstogo=3)), 14)
        self.assertEqual(t.projected_pool(dict(row, yardline_100=99)), 18)
        self.assertEqual(t.projected_pool(dict(row, yardline_100=3)), 19)
        self.assertEqual(t.rate(0, 0)["rate"], None)

    def test_ring_does_not_repeat_a_play_to_fake_extra_precision(self):
        choices = tuple(v.Choice(i, i + 40, bool(i % 2), bool((i // 2) % 2), "f", "p") for i in range(20))
        row, selected, counts = v.make_pool(choices, dict.fromkeys(v.CATEGORIES, 0.25))
        self.assertEqual(row[:2], b"\x01\x00")
        self.assertEqual(len({(c.formation, c.play) for c in selected}), 8)
        self.assertEqual(list(counts.values()), [2, 2, 2, 2])
        with self.assertRaises(v.VipError):
            v.make_pool(choices[:1], dict.fromkeys(v.CATEGORIES, 0.25))

    def test_charting_joins_keys_and_excludes_unknowns(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            def write(name, rows):
                path = folder / name
                with path.open("w", newline="") as f:
                    writer = csv.DictWriter(f, list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                return path
            common = dict(season=2025, season_type="REG", game_id="g1", game_date="2025-09-01",
                          posteam="LA", defteam="NYG", down=1, ydstogo=10, yardline_100=50,
                          score_differential=0, qtr=1, half_seconds_remaining=600,
                          play_type="pass", pass_attempt=1, shotgun=1)
            pbp = write("pbp.csv", [dict(common, play_id=i) for i in (1, 2, 3)])
            chart = write("chart.csv", [dict(nflverse_game_id="g1", nflverse_play_id=i,
                                              is_play_action=value, is_screen_pass=0, n_blitzers=value)
                                        for i, value in ((2, 0), (1, 1))])
            part = write("part.csv", [dict(nflverse_game_id="g1", play_id=1,
                                            defense_man_zone_type="MAN_COVERAGE", defense_coverage_type="COVER_1")])
            spec = dict(team="NYG", coach="Test", offense_history=[dict(team="LAR", first_season=2025, last_season=2025)],
                        defense_history=[dict(team="NYG", first_season=2025, last_season=2025)])
            result, = t.build([pbp], [spec], [chart], [part])
            self.assertEqual(result["overall"]["calls"], 3)
            self.assertEqual(result["play_action"], t.rate(1, 2))
            self.assertEqual(result["defense"]["blitz"], t.rate(1, 2))
            self.assertEqual(result["defense"]["man"], t.rate(1, 1))
            self.assertEqual(result["defense"]["man_blitz_joint"]["man_pressure"], t.rate(1, 1))
            self.assertEqual(result["charting_join"]["matched_pbp_rows"], 2)
            self.assertEqual(result["participation_join"]["matched_pbp_rows"], 1)


class RealSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source, xbe, image = [os.environ.get(k) for k in ("NFL2K5_VIP_TEMPLATE", "NFL2K5_VIP_XBE", "NFL2K5_VIP_IMAGE")]
        if not all((source, xbe, image)):
            raise unittest.SkipTest("Set explicit private USR, XBE and image paths for real-save checks")
        cls.folder = Path(source)
        cls.xbe = Path(xbe).read_bytes()
        cls.original = v.load_signed(cls.folder, cls.xbe)
        with OuterImage(image) as archive:
            cls.book = archive.read_entry(BOOK_ENTRIES["NYG"])

    def test_real_save_roundtrip_and_no_ts_magic_requirement(self):
        payload = self.original.payload
        self.assertEqual(v.VipSave.decode(payload).encode(), payload)
        altered = bytearray(payload)
        struct.pack_into("<I", altered, 0, 0x12345678)
        self.assertEqual(v.VipSave.decode(altered).encode(), bytes(altered))
        with self.assertRaises(v.VipError):
            v.VipSave.decode(payload[:-1])

    def test_real_copy_scope_signature_and_no_overwrite(self):
        tendency = dict(schema=t.SCHEMA, team="NYG", coach="John Harbaugh",
                        native_offense_pools=[dict(index=i, joint=dict.fromkeys(v.CATEGORIES, 0.25)) for i in range(20)])
        result, receipt = v.build_offense(self.original, self.book, tendency, "NYG Harbaugh", 15)
        allowed = {i for span in receipt["allowed_spans"] for i in range(span["offset"], span["offset"] + span["size"])}
        self.assertTrue(all(a == b for i, (a, b) in enumerate(zip(self.original.payload, result.payload)) if i not in allowed))
        key = derive_sig_key(self.xbe)
        self.assertTrue(verify_extra(key, result.payload, sign_save(key, result.payload)))
        self.assertFalse(verify_extra(key, result.payload, (self.folder / "EXTRA").read_bytes()))
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new"
            v.write_signed(output, result, self.xbe)
            self.assertEqual(v.load_signed(output, self.xbe).payload, result.payload)
            with self.assertRaises(FileExistsError):
                v.write_signed(output, self.original, self.xbe)
            self.assertEqual(v.load_signed(output, self.xbe).payload, result.payload)
        self.assertEqual((self.folder / "SAVEGAME.DAT").read_bytes(), self.original.payload)

    def test_full_coach_export_preserves_unknown_bytes_and_exposes_missing_plays(self):
        tendency = json.loads((ROOT / "data/vip/coaches/NYG.json").read_text())
        result, receipt = v.build_coach(self.original, self.book, tendency, "NYG Harbaugh", 15)
        allowed = {i for span in receipt["allowed_spans"] for i in range(span["offset"], span["offset"] + span["size"])}
        self.assertTrue(all(a == b for i, (a, b) in enumerate(zip(self.original.payload, result.payload)) if i not in allowed))
        for row in receipt["pools"]:
            self.assertEqual(len({(c["formation"], c["play"]) for c in row["choices"]}), 8)
            original = v.allocate_eight(row["target"]["joint"])
            self.assertEqual(sum(c["passed"] for c in row["choices"]), original["pass_under"] + original["pass_gun"])
            shotgun_target = row["target"]["joint"]["run_gun"] + row["target"]["joint"]["pass_gun"]
            self.assertLessEqual(abs(row["quantized_shotgun"] - shotgun_target), .125 + 1e-12)
            self.assertEqual(row["counts"], {k: sum(v.Choice(**c).category == k for c in row["choices"]) for k in v.CATEGORIES})
        for row in receipt["defense_pools"]:
            self.assertEqual(len({(c["formation"], c["coverage"]) for c in row["choices"]}), 4)
        for key in ("fourth_down", "two_point", "no_huddle"):
            counter = receipt["decisions"][key]
            self.assertTrue(counter["written"])
            self.assertTrue(counter["projection_scope"])
            self.assertEqual(struct.unpack_from("<HH", result.payload, counter["offset"]),
                             (counter["denominator"], counter["numerator"]))
        stats = tendency["native_statistics"]
        self.assertEqual(struct.unpack_from("<HH", result.payload, v.CONTEXT + 0x20B8),
                         (stats["pass_calls"], stats["run_calls"]))
        self.assertTrue(any(c["flipped"] for p in receipt["pools"] for c in p["choices"]))
        # The exact test book can vary, so only assert declared deficiencies
        # agree with its compiled callable assignments.
        if receipt["compiled_availability"]["screens"] == 0:
            self.assertIn("screen", [r["feature"] for r in receipt["unrepresented_observed_features"]])
        self.assertIn("unmapped_statistics", receipt["preserved_template_features"])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "new"
            v.write_signed(output, result, self.xbe)
            self.assertEqual(v.load_signed(output, self.xbe), result)

    def test_transfer_package_uses_name_matched_container_and_preserves_signed_bytes(self):
        from tools.nfl2k5_coach_vip import package_exports
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "exports"
            source.mkdir()
            v.write_signed(source / "NYG", self.original, self.xbe)
            import hashlib
            receipt = dict(name=self.original.name, save_sha256=hashlib.sha256(self.original.payload).hexdigest())
            (source / "NYG.json").write_text(json.dumps(receipt))
            output = root / "package"
            manifest = package_exports(source, self.xbe, output)
            relative = manifest["profiles"][0]["path"]
            self.assertEqual(relative, "UDATA/53450030/006F00611262")
            for name in ("SAVEGAME.DAT", "TYPE", "EXTRA", "SaveMeta.xbx"):
                self.assertEqual((output / relative / name).read_bytes(), (source / "NYG" / name).read_bytes())
            with self.assertRaises(v.VipError):
                package_exports(source, self.xbe, output)


if __name__ == "__main__":
    unittest.main()
