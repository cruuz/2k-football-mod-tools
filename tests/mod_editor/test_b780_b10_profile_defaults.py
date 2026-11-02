"""b780 b10-profile (bug row D8): a saved profile or franchise takes the build's new default game settings, once, on request.

A new profile starts from the defaults inside default.xbe (b779 df1), but a Settings save and every franchise save carry
the whole 0x2E0-byte options block and the game copies all of it over the live options on load, so old profiles keep
5 / 5 / Off.  These tests cover the pure planner (which settings may change), the signed-copy writer (Studio's Saves panel
and the command line), the Franchise > Upgrade step, and the Saves panel itself.  Fixtures are synthetic; real saves are
read only when the environment names them (B780_B10_SETTINGS), and are never written.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_option_defaults as defaults  # noqa: E402
from mod_editor.core import nfl2k5_profile_defaults as profile  # noqa: E402
from mod_editor.core import nfl2k5_save_writer as writer  # noqa: E402
import nfl2k5_save_writer_test as fixtures  # noqa: E402

NEW = {"state": "applied", "values": {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1}}
RETAIL = {"state": "retail", "values": {"quarter_minutes": 5, "sim_minutes": 5, "chop_block": 0}}
QUARTER, SIM, CHOP = 0xE6000C, 0xE60010, 0xE60064
BLOCK = 0xE5FF80
REAL_SETTINGS = Path(os.environ.get("B780_B10_SETTINGS", ""))


def settings_save(quarter=5, sim=5, chop=0, *, filler=True) -> bytes:
    """A 736-byte Settings save: a deterministic non-zero filler (so a stray write shows) and the three options."""
    block = bytearray((i * 37 + 11) % 251 for i in range(writer.SETTINGS_SAVE_SIZE)) if filler \
        else bytearray(writer.SETTINGS_SAVE_SIZE)
    for va, value in ((QUARTER, quarter), (SIM, sim), (CHOP, chop)):
        struct.pack_into("<I", block, va - BLOCK, value)
    return bytes(block)


class TableTests(unittest.TestCase):
    def test_offsets_follow_the_ram_image_and_match_the_defaults_owner(self):
        self.assertEqual([(o.key, o.offset) for o in profile.OPTIONS],
                         [("quarter_minutes", 0x8C), ("sim_minutes", 0x90), ("chop_block", 0xE4)])
        self.assertEqual((profile.BLOCK_VA, profile.BLOCK_SIZE), (BLOCK, 0x2E0))
        by = profile.BY_KEY
        self.assertEqual((by["quarter_minutes"].low, by["quarter_minutes"].high), defaults.QUARTER_RANGE)
        self.assertEqual((by["sim_minutes"].low, by["sim_minutes"].high), defaults.SIM_RANGE)
        self.assertEqual({o.retail for o in profile.OPTIONS[:2]}, {defaults.RETAIL_MINUTES})
        self.assertEqual(profile.OPTIONS[2].retail, 0)
        # the owner's own constants name the same three dwords
        self.assertEqual((by["quarter_minutes"].va, by["sim_minutes"].va, by["chop_block"].va), (QUARTER, SIM, CHOP))

    def test_the_text_is_plain_words(self):
        for text in (profile.HELP_TEXT, *(o.label + o.where for o in profile.OPTIONS)):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)
        self.assertEqual(profile.BY_KEY["quarter_minutes"].show(7), "7 minutes")
        self.assertEqual(profile.BY_KEY["quarter_minutes"].show(1), "1 minute")
        self.assertEqual(profile.BY_KEY["chop_block"].show(1), "On")
        self.assertEqual(profile.BY_KEY["chop_block"].show(0), "Off")

    def test_the_build_defaults_decode_from_an_executable(self):
        with mock.patch.object(defaults, "settings", return_value={"state": "applied", "quarter_minutes": 7,
                                                                   "sim_minutes": 15, "chop_block": True}):
            self.assertEqual(profile.build_targets(b"x"), NEW)
        with mock.patch.object(defaults, "settings", return_value={"state": "retail", "quarter_minutes": 5,
                                                                   "sim_minutes": 5, "chop_block": False}):
            self.assertEqual(profile.build_targets(b"x"), RETAIL)
        with mock.patch.object(defaults, "settings", return_value={"state": "foreign"}):
            self.assertEqual(profile.build_targets(b"x"), {"state": "foreign", "values": {}})


class PlanTests(unittest.TestCase):
    def actions(self, payload, targets=NEW):
        return {row["key"]: row["action"] for row in profile.plan(payload, targets)["rows"]}

    def test_an_old_profile_takes_all_three(self):
        report = profile.plan(settings_save(), NEW)
        self.assertEqual(report["block"], "settings")
        self.assertEqual(self.actions(settings_save()), {"quarter_minutes": "change", "sim_minutes": "change",
                                                         "chop_block": "change"})
        self.assertEqual(profile.values_from_plan(report), {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        text = profile.lines(report)
        self.assertEqual(text[0], "Quarter Length: 5 minutes -> 7 minutes  (Options > Game Options)")
        self.assertIn("Chop Block penalty: Off -> On", text[2])

    def test_a_profile_that_already_has_them_is_left_alone(self):
        self.assertEqual(set(self.actions(settings_save(7, 15, 1)).values()), {"same"})
        self.assertEqual(profile.values_from_plan(profile.plan(settings_save(7, 15, 1), NEW)), {})

    def test_a_value_the_player_set_is_kept_unless_he_ticks_it(self):
        payload = settings_save(10, 12, 0)                  # 10 minute quarters, 12 minute sim: his choices; chop still old
        report = profile.plan(payload, NEW)
        self.assertEqual(self.actions(payload), {"quarter_minutes": "kept", "sim_minutes": "kept", "chop_block": "change"})
        self.assertIn("set to 10 minutes by the player", report["rows"][0]["note"])
        self.assertEqual(profile.values_from_plan(report), {"chop_block": 1})
        self.assertEqual(profile.values_from_plan(report, also=("quarter_minutes",)),
                         {"quarter_minutes": 7, "chop_block": 1})
        self.assertEqual(report["kept"], ["quarter_minutes", "sim_minutes"])

    def test_a_value_the_menu_cannot_set_is_kept_and_said_so(self):
        payload = settings_save(0, 99, 2)
        report = profile.plan(payload, NEW)
        self.assertEqual({row["action"] for row in report["rows"]}, {"kept"})
        self.assertTrue(all("cannot set" in row["note"] for row in report["rows"]))
        self.assertEqual(profile.values_from_plan(report), {})

    def test_a_retail_build_changes_nothing(self):
        self.assertEqual(set(self.actions(settings_save(), RETAIL).values()), {"same"})
        payload = settings_save(10, 5, 0)
        self.assertEqual(self.actions(payload, RETAIL), {"quarter_minutes": "kept", "sim_minutes": "same",
                                                         "chop_block": "same"})

    def test_a_build_that_installs_only_some_defaults_plans_only_those(self):
        # the pace fix is not in the build: Sim. Quarter Length stays 5 while Quarter Length moves to 7
        targets = {"state": "applied", "values": {"quarter_minutes": 7, "sim_minutes": 5, "chop_block": 0}}
        self.assertEqual(self.actions(settings_save(), targets),
                         {"quarter_minutes": "change", "sim_minutes": "same", "chop_block": "same"})

    def test_an_unreadable_build_gives_no_values_and_nothing_to_write(self):
        report = profile.plan(settings_save(), {"state": "foreign", "values": {}})
        self.assertEqual({row["action"] for row in report["rows"]}, {"kept"})
        self.assertEqual(profile.values_from_plan(report), {})

    def test_a_franchise_sized_save_reads_the_same_block(self):
        franchise = bytearray(fixtures._franchise_save())
        franchise[:writer.SETTINGS_BLOCK_SIZE] = settings_save()
        report = profile.plan(bytes(franchise), NEW)
        self.assertEqual(report["block"], "franchise")
        self.assertEqual(report["changes"], 3)

    def test_other_sizes_refuse(self):
        with self.assertRaises(profile.ProfileDefaultsError):
            profile.plan(bytes(1000), NEW)
        with self.assertRaises(profile.ProfileDefaultsError):
            profile.read_options(bytes(100))

    def test_typed_targets_are_range_checked(self):
        self.assertEqual(profile.explicit_targets(6, 12, True)["values"], {"quarter_minutes": 6, "sim_minutes": 12,
                                                                           "chop_block": 1})
        for bad in ({"quarter_minutes": 0}, {"quarter_minutes": 16}, {"sim_minutes": 2}, {"sim_minutes": 16},
                    {"chop_block": 2}):
            with self.subTest(bad), self.assertRaises(profile.ProfileDefaultsError):
                profile.check_values(bad)
        for bad in (7.0, "7", True, None):
            with self.subTest(bad), self.assertRaises(profile.ProfileDefaultsError):
                profile.check_values({"quarter_minutes": bad})
        with self.assertRaises(profile.ProfileDefaultsError):
            profile.check_values({"difficulty": 1})


class EditTests(unittest.TestCase):
    def test_only_the_three_dwords_change_and_it_reads_back(self):
        source = settings_save()
        out, rows = profile.edit(source, {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        self.assertEqual(len(out), len(source))
        self.assertEqual([r["key"] for r in rows], ["quarter_minutes", "sim_minutes", "chop_block"])
        changed = {i for i, (a, b) in enumerate(zip(source, out)) if a != b}
        self.assertTrue(changed <= {0x8C + k for k in range(4)} | {0x90 + k for k in range(4)} | {0xE4 + k for k in range(4)})
        self.assertEqual(profile.read_options(out), {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        # sliders, difficulty, camera and every other option are the filler bytes still
        for k in range(writer.SETTINGS_SAVE_SIZE):
            if k not in changed:
                self.assertEqual(out[k], source[k], k)

    def test_writing_the_same_value_is_not_a_change(self):
        source = settings_save(7, 15, 1)
        out, rows = profile.edit(source, {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        self.assertEqual((out, rows), (source, []))

    def test_a_second_run_changes_nothing(self):
        once, _ = profile.edit(settings_save(), profile.values_from_plan(profile.plan(settings_save(), NEW)))
        again = profile.values_from_plan(profile.plan(once, NEW))
        self.assertEqual(again, {})

    def test_bad_values_refuse_before_any_byte_moves(self):
        payload = bytearray(settings_save())
        before = bytes(payload)
        with self.assertRaises(profile.ProfileDefaultsError):
            profile.apply_values(payload, {"quarter_minutes": 7, "sim_minutes": 99})
        self.assertEqual(bytes(payload), before)


class SignedCopyTests(unittest.TestCase):
    """The writer Studio's Saves panel and the command line use: a fresh EXTRA, the source never written."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.xbe = self.root / "default.xbe"
        self.xbe.write_bytes(fixtures._build_synth_xbe())
        self.sig_key = writer.derive_sig_key(self.xbe.read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, payload):
        path = self.root / "SAVEGAME.DAT"
        path.write_bytes(payload)
        return path

    def test_options_alone_make_a_signed_copy(self):
        src = self.source(settings_save())
        out, extra = self.root / "out" / "SAVEGAME.DAT", self.root / "out" / "EXTRA"
        result = writer.edit_save_file(src, out, extra, xbe_path=self.xbe,
                                       options={"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        self.assertEqual([c["after"] for c in result["option_changes"]], [7, 15, 1])
        self.assertEqual(result["slider_changes"], [])
        self.assertEqual(src.read_bytes(), settings_save())                     # the source is never written
        new = out.read_bytes()
        self.assertEqual(profile.read_options(new), {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        self.assertEqual(extra.read_bytes(), hmac.new(self.sig_key, new, hashlib.sha1).digest())
        self.assertTrue(writer.verify_extra(self.sig_key, new, extra.read_bytes()))

    def test_options_sliders_and_year_share_one_copy(self):
        franchise = bytearray(fixtures._franchise_save())
        franchise[:writer.SETTINGS_BLOCK_SIZE] = settings_save()
        src = self.source(bytes(franchise))
        out, extra = self.root / "a" / "SAVEGAME.DAT", self.root / "a" / "EXTRA"
        result = writer.edit_save_file(src, out, extra, xbe_path=self.xbe, sliders={"Human Catching": 0.5},
                                       franchise_year=2031, options={"quarter_minutes": 7})
        self.assertEqual(len(result["option_changes"]), 1)
        self.assertEqual(len(result["slider_changes"]), 2)
        self.assertEqual(result["franchise_year_change"]["new_display_year"], 2031)
        self.assertEqual(profile.read_options(out.read_bytes())["quarter_minutes"], 7)

    def test_no_edit_at_all_still_refuses(self):
        src = self.source(settings_save())
        with self.assertRaises(writer.SaveWriterError):
            writer.edit_save_file(src, self.root / "x.dat", self.root / "x.extra", xbe_path=self.xbe, options={})
        # an option that is already there is not an edit either
        with self.assertRaises(writer.SaveWriterError):
            writer.edit_save_file(src, self.root / "x.dat", self.root / "x.extra", xbe_path=self.xbe,
                                  options={"quarter_minutes": 5})
        self.assertFalse((self.root / "x.dat").exists())

    def test_a_bad_option_is_a_save_writer_error_and_writes_nothing(self):
        src = self.source(settings_save())
        for options in ({"quarter_minutes": 16}, {"nonsense": 1}, {"chop_block": 5}):
            with self.subTest(options), self.assertRaises(writer.SaveWriterError):
                writer.edit_save_file(src, self.root / "y.dat", self.root / "y.extra", xbe_path=self.xbe, options=options)
        self.assertFalse((self.root / "y.dat").exists())

    def test_read_save_reports_the_options(self):
        info = writer.read_save(self.source(settings_save(10, 12, 1)))
        self.assertEqual(info["options"], {"quarter_minutes": 10, "sim_minutes": 12, "chop_block": 1})
        self.assertEqual(info["kind"], "settings")

    def test_the_hdd_copy_route_takes_options_too(self):
        payload = settings_save()
        extra = writer.sign_save(self.sig_key, payload)
        image = fixtures._build_fatx_image(payload, extra)
        source, target = self.root / "hdd.img", self.root / "hdd-copy.img"
        source.write_bytes(image)
        target.write_bytes(image)
        result = writer.write_back_to_hdd(source, target, container=("53450030",), xbe_path=self.xbe, partition="X",
                                          options={"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        self.assertEqual([c["after"] for c in result["option_changes"]], [7, 15, 1])
        self.assertTrue(result["post_write_readback_matches"])
        self.assertEqual(source.read_bytes(), image)                            # the source image is never written
        self.assertNotEqual(target.read_bytes(), image)


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.xbe = self.root / "default.xbe"
        self.xbe.write_bytes(fixtures._build_synth_xbe())
        self.dat = self.root / "SAVEGAME.DAT"
        self.dat.write_bytes(settings_save())

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch.object(profile, "build_targets", return_value=NEW):
            code = profile.main([str(a) for a in argv])
        return code, out.getvalue()

    def test_show_lists_the_comparison_and_writes_nothing(self):
        code, text = self.run_main("show", self.dat, "--xbe", self.xbe)
        self.assertEqual(code, 0)
        report = json.loads(text)
        self.assertEqual(report["changes"], 3)
        self.assertEqual(report["lines"][0], "Quarter Length: 5 minutes -> 7 minutes  (Options > Game Options)")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["SAVEGAME.DAT", "default.xbe"])

    def test_apply_writes_a_signed_copy_and_keeps_player_choices(self):
        self.dat.write_bytes(settings_save(10, 5, 0))
        code, text = self.run_main("apply", self.dat, "--xbe", self.xbe, "--out-dat", self.root / "o.dat",
                                   "--out-extra", self.root / "o.extra")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(text)["written"])
        self.assertEqual(profile.read_options((self.root / "o.dat").read_bytes()),
                         {"quarter_minutes": 10, "sim_minutes": 15, "chop_block": 1})

    def test_apply_with_also_replaces_a_player_choice(self):
        self.dat.write_bytes(settings_save(10, 5, 0))
        code, _text = self.run_main("apply", self.dat, "--xbe", self.xbe, "--out-dat", self.root / "o.dat",
                                    "--out-extra", self.root / "o.extra", "--also", "quarter_minutes")
        self.assertEqual(code, 0)
        self.assertEqual(profile.read_options((self.root / "o.dat").read_bytes())["quarter_minutes"], 7)

    def test_apply_with_nothing_to_change_writes_nothing(self):
        self.dat.write_bytes(settings_save(7, 15, 1))
        code, text = self.run_main("apply", self.dat, "--xbe", self.xbe, "--out-dat", self.root / "o.dat",
                                   "--out-extra", self.root / "o.extra")
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(text)["written"])
        self.assertFalse((self.root / "o.dat").exists())

    def test_the_save_writer_command_line_takes_option_flags(self):
        out, extra = self.root / "w.dat", self.root / "w.extra"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = writer.main(["edit", str(self.dat), "--out-dat", str(out), "--out-extra", str(extra), "--xbe",
                                str(self.xbe), "--option", "quarter_minutes", "6", "--option", "chop_block", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(profile.read_options(out.read_bytes()), {"quarter_minutes": 6, "sim_minutes": 5, "chop_block": 1})


@unittest.skipUnless(REAL_SETTINGS.is_file(), "a real game-written Settings1 SAVEGAME.DAT is not named in B780_B10_SETTINGS")
class RealSettingsTests(unittest.TestCase):
    """A Settings1 the released game wrote (read only)."""

    def test_the_real_profile_is_the_old_defaults_and_takes_the_new_ones_in_three_bytes(self):
        payload = REAL_SETTINGS.read_bytes()
        self.assertEqual(len(payload), 736)
        self.assertEqual(profile.read_options(payload), {"quarter_minutes": 5, "sim_minutes": 5, "chop_block": 0})
        out, rows = profile.edit(payload, profile.values_from_plan(profile.plan(payload, NEW)))
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(a != b for a, b in zip(payload, out)), 3)        # 5 -> 7, 5 -> 15, 0 -> 1: one byte each
        self.assertEqual(profile.read_options(out), {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})


class UpgradeStepTests(unittest.TestCase):
    """Franchise > Upgrade also takes the disc's defaults into the franchise's own copy of the options."""

    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
        cls.base = synthetic_franchise()

    def franchise(self, quarter=5, sim=5, chop=0):
        data = bytearray(self.base)
        for va, value in ((QUARTER, quarter), (SIM, sim), (CHOP, chop)):
            struct.pack_into("<I", data, va - BLOCK, value)
        return bytes(data)

    def test_the_franchise_takes_the_new_defaults_and_only_those_bytes_change(self):
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        source = self.franchise()
        out, receipt = up.sync_game_settings(source, NEW)
        self.assertEqual(receipt["operation"], "game_settings")
        self.assertEqual([c["after"] for c in receipt["changes"]], [7, 15, 1])
        self.assertTrue(receipt["outside_declared_fields_identical"])
        self.assertLessEqual(receipt["changed_bytes"], 3)
        self.assertEqual(profile.read_options(out), {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})
        self.assertEqual(out[0x2E0:], source[0x2E0:])                             # the roster, season and front office
        again, replay = up.sync_game_settings(out, NEW)
        self.assertEqual((again, replay["changes"]), (out, []))

    def test_a_franchise_the_player_tuned_keeps_his_numbers_and_lists_them(self):
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        out, receipt = up.sync_game_settings(self.franchise(10, 12, 0), NEW)
        self.assertEqual(profile.read_options(out), {"quarter_minutes": 10, "sim_minutes": 12, "chop_block": 1})
        self.assertEqual(receipt["kept"], ["quarter_minutes", "sim_minutes"])

    def test_a_retail_disc_or_an_unreadable_one_changes_nothing_and_says_why(self):
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        source = self.franchise()
        out, receipt = up.sync_game_settings(source, RETAIL)
        self.assertEqual((out, receipt["changes"]), (source, []))
        self.assertIn("retail settings", receipt["reason"])
        out, receipt = up.sync_game_settings(source, {"state": "unreadable", "values": {}, "error": "no such disc"})
        self.assertEqual((out, receipt["changes"]), (source, []))
        self.assertIn("could not be read", receipt["reason"])
        self.assertIn("no such disc", receipt["reason"])

    def test_the_command_exists_and_upgrade_includes_it_unless_told_not_to(self):
        from mod_editor.core import nfl2k5_franchise_upgrade_io as service
        self.assertIn("game-settings", service.COMMANDS)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            from tests.mod_editor.test_franchise_upgrade import signed_folder
            folder = signed_folder(root / "source", self.franchise())
            disc = root / "disc.iso"
            disc.write_bytes(b"synthetic disc fingerprint")
            from mod_editor.core import nfl2k5_franchise_upgrade as up
            with mock.patch.object(service, "load_disc", return_value=(b"", {})), \
                    mock.patch.object(service, "load_disc_defaults", return_value=NEW) as read, \
                    mock.patch.object(up, "validate_save", return_value={}):
                plan = service.plan_upgrade(folder, disc, command="game-settings")
                self.assertEqual([s["operation"] for s in plan.receipt["steps"]], ["game_settings"])
                self.assertEqual(plan.receipt["changed_fields"], 3)
                self.assertEqual(plan.receipt["disc_default_settings"], NEW)
                self.assertEqual(profile.read_options(plan.payload)["sim_minutes"], 15)
                read.assert_called_once_with(disc)

    def test_an_unreadable_disc_file_is_not_fatal(self):
        from mod_editor.core import nfl2k5_franchise_upgrade_io as service
        with tempfile.TemporaryDirectory() as td:
            disc = Path(td) / "disc.iso"
            disc.write_bytes(b"not a disc")
            found = service.load_disc_defaults(disc)
        self.assertEqual(found["state"], "unreadable")
        self.assertEqual(found["values"], {})


class SavesPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.xbe = self.root / "default.xbe"
        self.xbe.write_bytes(fixtures._build_synth_xbe())
        from mod_editor.gui.save_panel_qt import SavePanel
        self.panel = SavePanel()
        self.addCleanup(self.panel.deleteLater)

    def tearDown(self):
        self.tmp.cleanup()

    def open_save(self, payload):
        path = self.root / "SAVEGAME.DAT"
        path.write_bytes(payload)
        self.panel._save_info = writer.read_save(path)
        self.panel.save_field.setText(str(path))
        self.panel.xbe_field.setText(str(self.xbe))
        self.panel._targets = NEW
        self.panel._refresh_defaults()
        return path

    def test_an_old_profile_shows_three_ticked_rows_and_a_plain_prompt(self):
        self.open_save(settings_save())
        table = self.panel.defaults_table
        self.assertEqual(table.rowCount(), 3)
        self.assertEqual([table.item(r, 1).text() for r in range(3)], ["5 minutes", "5 minutes", "Off"])
        self.assertEqual([table.item(r, 2).text() for r in range(3)], ["7 minutes", "15 minutes", "On"])
        self.assertTrue(all(box.isChecked() and box.isEnabled() for box in self.panel._default_checks.values()))
        self.assertIn("still has the old defaults", self.panel.defaults_status.text())
        self.assertEqual(self.panel._collect_option_edits(), {"quarter_minutes": 7, "sim_minutes": 15, "chop_block": 1})

    def test_a_player_choice_is_unticked_and_can_be_ticked(self):
        self.open_save(settings_save(10, 5, 0))
        boxes = self.panel._default_checks
        self.assertFalse(boxes["quarter_minutes"].isChecked())
        self.assertTrue(boxes["quarter_minutes"].isEnabled())
        self.assertEqual(self.panel._collect_option_edits(), {"sim_minutes": 15, "chop_block": 1})
        boxes["quarter_minutes"].setChecked(True)
        self.assertEqual(self.panel._collect_option_edits()["quarter_minutes"], 7)
        boxes["sim_minutes"].setChecked(False)
        self.assertNotIn("sim_minutes", self.panel._collect_option_edits())

    def test_a_profile_that_has_them_says_so_and_offers_nothing(self):
        self.open_save(settings_save(7, 15, 1))
        self.assertIn("already has this build's default game settings", self.panel.defaults_status.text())
        self.assertEqual(self.panel._collect_option_edits(), {})
        self.assertFalse(any(box.isEnabled() for box in self.panel._default_checks.values()))

    def test_an_unknown_executable_says_the_defaults_are_unknown(self):
        self.open_save(settings_save())
        self.panel._targets = {"state": "foreign", "values": {}}
        self.panel._refresh_defaults()
        self.assertIn("not a build the tool recognises", self.panel.defaults_status.text())
        self.assertEqual(self.panel._collect_option_edits(), {})

    def test_the_signed_copy_carries_the_ticked_rows_only(self):
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QMessageBox
        path = self.open_save(settings_save(10, 5, 0))
        self.panel._default_checks["chop_block"].setChecked(False)
        out = self.root / "out" / "SAVEGAME.DAT"
        self.panel.out_field.setText(str(out))
        self.panel._refresh_controls()
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Ok), \
                mock.patch.object(QMessageBox, "information") as done:
            self.panel._apply_clicked()
            deadline = 50
            while self.panel._busy and deadline:
                QTest.qWait(100)
                deadline -= 1
            QTest.qWait(50)
        self.assertFalse(self.panel._busy)
        self.assertTrue(out.is_file(), "the signed copy was not written")
        self.assertEqual(profile.read_options(out.read_bytes()), {"quarter_minutes": 10, "sim_minutes": 15, "chop_block": 0})
        self.assertTrue(done.called)
        self.assertIn("Sim. Quarter Length: 5 minutes -> 15 minutes", done.call_args[0][2])
        self.assertEqual(path.read_bytes(), settings_save(10, 5, 0))

    def test_nothing_ticked_and_nothing_else_edited_does_not_write(self):
        from PyQt5.QtWidgets import QMessageBox
        self.open_save(settings_save(7, 15, 1))
        self.panel.out_field.setText(str(self.root / "none" / "SAVEGAME.DAT"))
        with mock.patch.object(QMessageBox, "information") as note, mock.patch.object(QMessageBox, "question") as ask:
            self.panel._apply_clicked()
        note.assert_called_once()
        ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
