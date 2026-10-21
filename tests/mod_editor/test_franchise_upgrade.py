"""Synthetic migration, history ownership, signing and Studio command regressions."""
import copy
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import nfl2k5_franchise_upgrade as up
from mod_editor.core import nfl2k5_save_rost as sr
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_franchise_upgrade_io as service
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
from tests.mod_editor.test_nfl2k5_team_history import entry


def fixture(*, current=False, shared=False):
    data = bytearray(synthetic_franchise(year_field=1))
    roster = sr.decode(data)
    first, second = roster.players[:2]
    pool = 0x70000
    words = [entry(1 if current else 0, 8, 321),
             entry(2 if current else 1, 96, 1, end=True, deleted=True, post=True, folded=True)]
    struct.pack_into("<I", data, roster.layout.root + 0x40, len(words))
    def pointer(field, target):
        struct.pack_into("<i", data, field, target - field + 1)
    pointer(roster.layout.root + 0x44, pool)
    pointer(first.offset + 0x2C, pool)
    if shared:
        pointer(second.offset + 0x2C, pool + 4)
    struct.pack_into("<2I", data, pool, *words)
    cohort = {"schema": "nfl2k5_b77_f12_cohort/v1",
              "columns": ["index", "first", "last", "birth_date", "old_years_pro", "basis"],
              "basis_codes": {"synthetic": "test identity"}, "counts": {"records": 2}, "records": []}
    for player in (first, second):
        old = player.record.values["years_pro"]
        cohort["records"].append([9999, *up.identity(player), old - 1, "synthetic"])
        if current:
            data[player.offset + 0x25] += 1
    return bytes(data), cohort


def signed_folder(root, payload):
    root.mkdir()
    for name, data in {"SAVEGAME.DAT": payload, "EXTRA": rr.sign_save(payload),
                       "TYPE": "FXG\0".encode("utf-16-le"), "SaveMeta.xbx": b"synthetic metadata"}.items():
        (root / name).write_bytes(data)
    return root


def with_coaches(payload, rows):
    data = bytearray(payload)
    root = sr.decode(data).layout.root
    base, cursor = 0x84000, 0x85000
    struct.pack_into("<Ii", data, root + 0x30, len(rows), base - (root + 0x34) + 1)
    for index, (first, last, body, portrait) in enumerate(rows):
        at = base + index * 0xA8
        for field, text in ((at, first), (at + 4, last)):
            raw = text.encode("utf-16-le") + b"\0\0"
            data[cursor:cursor + len(raw)] = raw
            struct.pack_into("<i", data, field, cursor - field + 1)
            cursor += len(raw)
        struct.pack_into("<I", data, at + 0x18, body)
        struct.pack_into("<H", data, at + 0x40, portrait)
        data[at + 0x20] = 83 + index  # unrelated rating sentinel
    return bytes(data)


def disc_roster(payload):
    data = bytearray(bytes(0x40) + payload[0x320:0x320 + rr.BODY_SIZE - 0x40])
    data[0x0C:0x10] = b"ROST"
    struct.pack_into("<Ii", data, 0x10, 17, 0x2D)
    return bytes(data)


def book_fixture():
    from tests.mod_editor.test_nfl2k5_team_history import synthetic_body, TEAM_ABBRS
    from tests.mod_editor.test_nfl2k5_roster_records import synthetic_save_v0
    from tests.mod_editor.test_nfl2k5_playbook_inspector import _fixture, STRING_BASE
    from mod_editor.core import nfl2k5_franchise_save as fs
    body = bytearray(synthetic_body([{"first": "Test", "last": "Player", "birth": None,
                                      "position": 0, "count": 2, "stream": None}]))
    struct.pack_into("<i", body, 0x14, 0x2D)
    labels, strings = 0x4000, 0x80000
    struct.pack_into("<Ii", body, 0x40 + 0x48, 32, labels - (0x40 + 0x4C) + 1)
    resources = {}
    for index, key in enumerate(TEAM_ABBRS[:32]):
        label = labels + index * 8
        text_at = strings + index * 16
        raw = key.encode("utf-16-le") + b"\0\0"
        body[text_at:text_at + len(raw)] = raw
        struct.pack_into("<i", body, label + 4, text_at - (label + 4) + 1)
        team = 0x41C8 + index * 0x1F4
        struct.pack_into("<i", body, team + 0x110, label - (team + 0x110) + 1)
        struct.pack_into("<I", body, team + 0x118, index)
        struct.pack_into("<I", body, team + 0x150, index % 3)
        book = bytearray(_fixture())
        book[0x20 + STRING_BASE:0x20 + STRING_BASE + len(raw)] = raw
        name_id = zlib.crc32(f"{key}-pb.iff".upper().encode("utf-16-le")) & 0xFFFFFFFF
        resources[name_id] = bytes(book)
    save = synthetic_save_v0(bytes(body), suffix=synthetic_franchise(year_field=1)[fs.SEASON_BLOCK:])
    return save, bytes(body), resources


class ExperienceTests(unittest.TestCase):
    def test_identity_migration_keeps_stats_flags_and_generated_records(self):
        before, cohort = fixture()
        after, receipt = up.upgrade_years(before, cohort)
        a, b = sr.decode(before), sr.decode(after)
        self.assertEqual(receipt["changed_players"], 2)
        self.assertEqual(receipt["shifted_honors_words"], 1)
        self.assertEqual(len(receipt["changes"]), 4)
        self.assertEqual(b.history_words[a.players[0].key],
                         tuple(w + (1 << 23) for w in a.history_words[a.players[0].key]))
        allowed = {p.offset + 0x25 for p in a.players[:2]} | {0x70002, 0x70003, 0x70006, 0x70007}
        self.assertTrue(all(x == y or i in allowed for i, (x, y) in enumerate(zip(before, after))))
        for player in a.players[2:]:
            self.assertEqual(before[player.offset:player.offset + 84], after[player.offset:player.offset + 84])
        again, receipt = up.upgrade_years(after, cohort)
        self.assertEqual(again, after)
        self.assertEqual(receipt["changes"], [])

    def test_year_edit_after_an_upgrade_does_not_bump_experience_again(self):
        """fx1 (review r2-franchise MAJOR 1): +1 year on an upgraded save made every player look 'old' again."""
        from mod_editor.core import nfl2k5_franchise_save as fs
        before, cohort = fixture()
        after, _receipt = up.upgrade_years(before, cohort)
        save = fs.FranchiseSave(after)
        save.set_year_field(save.header.year_field + 1)
        edited = save.to_bytes()
        with self.assertRaisesRegex(Exception, "slot 0"):
            up.upgrade_years(edited, cohort)

    def test_current_shared_history_is_read_only_and_idempotent(self):
        before, cohort = fixture(current=True, shared=True)
        after, receipt = up.upgrade_years(before, cohort)
        self.assertEqual(after, before)
        self.assertEqual(receipt["changes"], [])

    def test_old_shared_history_refuses_before_writing(self):
        before, cohort = fixture(shared=True)
        with self.assertRaisesRegex(up.UpgradeRefused, "shared/overlapping"):
            up.upgrade_years(before, cohort)

    def test_mixed_custom_and_unrecognized_identities_refuse(self):
        before, cohort = fixture()
        roster = sr.decode(before)
        for delta in (1, 3):
            data = bytearray(before)
            data[roster.players[0].offset + 0x25] += delta
            with self.assertRaises(up.UpgradeRefused):
                up.upgrade_years(bytes(data), cohort)
        other = copy.deepcopy(cohort)
        for pin in other["records"]:
            pin[1] = "Replacement"
        with self.assertRaisesRegex(up.UpgradeRefused, "no pinned"):
            up.upgrade_years(before, other)

    def test_slot_overflow_and_non_franchise_refuse(self):
        before, cohort = fixture()
        data = bytearray(before)
        struct.pack_into("<I", data, 0x70000, entry(31, 8, 321))
        with self.assertRaisesRegex(up.UpgradeRefused, "history slot"):
            up.upgrade_years(bytes(data), cohort)
        with self.assertRaises(up.UpgradeRefused):
            up.upgrade_years(bytes(736), cohort)


class StudioCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_franchise_exposes_upgrade_command(self):
        from mod_editor.gui.franchise_panel_qt import FranchisePanel
        panel = FranchisePanel()
        self.assertEqual(panel.upgrade_button.text(), "Upgrade franchise save to the current build")
        self.assertFalse(panel.upgrade_button.isEnabled())
        panel.deleteLater()

    def test_command_opens_for_saved_source_and_refuses_unwritten_edits(self):
        from mod_editor.gui.franchise_panel_qt import FranchisePanel
        with tempfile.TemporaryDirectory() as td:
            source = signed_folder(Path(td) / "source", fixture()[0])
            container = rr.SaveContainer.load(source)
            panel = FranchisePanel()
            self.assertTrue(panel.load(container, container.document()))
            with patch("mod_editor.gui.franchise_upgrade_dialog_qt.FranchiseUpgradeDialog") as dialog:
                panel.upgrade_button.click()
                dialog.assert_called_once_with(source, panel)
                dialog.return_value.exec_.assert_called_once()
                dialog.reset_mock()
                panel._document.players[0].record.set("speed", 77)
                panel.upgrade_button.click()
                dialog.assert_not_called()
                self.assertIn("Write your edits", panel.status_label.text())
            panel.deleteLater()

    def test_dialog_previews_before_write_and_invalidates_changed_disc(self):
        from mod_editor.gui.franchise_upgrade_dialog_qt import FranchiseUpgradeDialog
        from PyQt5.QtTest import QTest
        import time
        payload, cohort = fixture()
        upgraded, years = up.upgrade_years(payload, cohort)
        receipt = {"steps": [years], "changed_fields": len(years["changes"]),
                   "validation": {"after": {"findings": []}}}
        plan = service.UpgradePlan(None, Path("synthetic.iso"), upgraded, receipt)
        dialog = FranchiseUpgradeDialog(Path("source"))
        def finish():
            deadline = time.monotonic() + 5
            while dialog.worker.isRunning() and time.monotonic() < deadline:
                QTest.qWait(5)
            self.assertFalse(dialog.worker.isRunning())
            self.app.processEvents()
        with patch.object(service, "plan_upgrade", return_value=plan) as preview, \
                patch.object(service, "write_plan", return_value={}) as write:
            dialog.disc_edit.setText("synthetic.iso")
            self.assertFalse(dialog.write_button.isEnabled())
            dialog.preview_button.click()
            finish()
            preview.assert_called_once()
            write.assert_not_called()
            self.assertTrue(dialog.write_button.isEnabled())
            self.assertIn("Players with corrected experience: 2", dialog.details.toPlainText())
            dialog.disc_edit.setText("changed.iso")
            self.assertFalse(dialog.write_button.isEnabled())
            dialog.preview_button.click()
            finish()
            dialog.output_edit.setText("new-save")
            dialog.write_button.click()
            finish()
            write.assert_called_once_with(plan, Path("new-save"), Path("new-save.upgrade.json"))
            self.assertFalse(dialog.write_button.isEnabled())
            self.assertIn("Signed save written", dialog.details.toPlainText())
        dialog.deleteLater()


class CoachTests(unittest.TestCase):
    def test_identity_matched_shuffle_changes_only_body_and_portrait(self):
        source = with_coaches(fixture()[0], [("First", "Coach", 7, 7007),
                                            ("Second", "Coach", 29, 7029), ("Generated", "Coach", 50, 90)])
        target = disc_roster(with_coaches(fixture()[0], [("Second", "Coach", 49, 7034),
                                                      ("First", "Coach", 47, 7031)]))
        result, receipt = up.sync_coaches(source, target)
        self.assertEqual(len(receipt["changes"]), 4)
        self.assertEqual(receipt["unmatched_preserved"][0]["coach"], "Generated Coach")
        allowed = {0x84000 + i * 0xA8 + d for i in (0, 1) for d in (0x18, 0x19, 0x1A, 0x1B, 0x40, 0x41)}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(source, result))))
        self.assertEqual(struct.unpack_from("<H", result, 0x84040)[0], 7031)
        self.assertEqual(struct.unpack_from("<H", result, 0x84000 + 0xA8 + 0x40)[0], 7034)
        self.assertEqual(up.sync_coaches(result, target)[1]["changes"], [])

    def test_duplicate_named_coaches_refuse(self):
        payload = with_coaches(fixture()[0], [("First", "Coach", 7, 7007)] * 2)
        with self.assertRaisesRegex(up.UpgradeRefused, "duplicate coach"):
            up.sync_coaches(payload, disc_roster(payload))


class PlaybookTests(unittest.TestCase):
    def test_all_teams_resolve_and_changed_choice_and_scheme_are_restored(self):
        payload, body, resources = book_fixture()
        roster = sr.decode(payload)
        edited = bytearray(payload)
        team = roster.teams[30]
        wrong_label = roster.tables["team_labels"].offset
        struct.pack_into("<i", edited, team.offset + 0x110, wrong_label - (team.offset + 0x110) + 1)
        struct.pack_into("<I", edited, team.offset + 0x150, 2)
        result, receipt = up.sync_playbooks(bytes(edited), body, resources)
        self.assertEqual(result, payload)
        self.assertEqual(len(receipt["teams"]), 32)
        self.assertEqual(len(receipt["changes"]), 2)
        self.assertEqual(receipt["teams"][30]["offense"], "TEN")
        self.assertEqual(receipt["teams"][30]["defense"], "TEN")
        self.assertEqual(up.sync_playbooks(result, body, resources)[1]["changes"], [])

    def test_missing_compiled_book_refuses(self):
        payload, body, resources = book_fixture()
        resources.pop(next(iter(resources)))
        with self.assertRaises(up.UpgradeRefused):
            up.sync_playbooks(payload, body, resources)


class ContainerTests(unittest.TestCase):
    def test_signed_copy_preserves_metadata_and_refuses_stale_input(self):
        payload, cohort = fixture()
        result, years = up.upgrade_years(payload, cohort)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = signed_folder(root / "source", payload)
            disc = root / "disc.iso"
            disc.write_bytes(b"synthetic disc fingerprint")
            container = service.load_container(source)
            plan = service.UpgradePlan(container, disc, result,
                                       {"disc_sha256": service.hash_file(disc), "steps": [years]})
            receipt = service.write_plan(plan, root / "copy", root / "receipt.json")
            written = service.load_container(root / "copy")
            self.assertTrue(written.verified)
            self.assertEqual(written.savegame, result)
            self.assertEqual(written.members["SaveMeta.xbx"], container.members["SaveMeta.xbx"])
            self.assertEqual((source / "SAVEGAME.DAT").read_bytes(), payload)
            self.assertFalse(receipt["dry_run"])
            (source / "SaveMeta.xbx").write_bytes(b"changed since preview")
            with self.assertRaisesRegex(up.UpgradeRefused, "changed since preview"):
                service.write_plan(plan, root / "copy2", root / "receipt2.json")
            self.assertFalse((root / "copy2").exists())
            self.assertFalse((root / "receipt2.json").exists())

    def test_failed_receipt_write_leaves_no_published_copy(self):
        """fx1 (review pr67 nit, r2-franchise MINOR 3): the receipt used to be written after the rename."""
        payload, cohort = fixture()
        result, years = up.upgrade_years(payload, cohort)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = signed_folder(root / "source", payload)
            disc = root / "disc.iso"
            disc.write_bytes(b"synthetic disc fingerprint")
            plan = service.UpgradePlan(service.load_container(source), disc, result,
                                       {"disc_sha256": service.hash_file(disc), "steps": [years]})
            with patch.object(service.json, "dumps", side_effect=OSError(28, "No space left on device")):
                with self.assertRaises(OSError):
                    service.write_plan(plan, root / "copy", root / "receipt.json")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["disc.iso", "source"])
            with patch.object(Path, "rename", side_effect=OSError(5, "I/O error")):
                with self.assertRaises(OSError):
                    service.write_plan(plan, root / "copy", root / "receipt.json")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["disc.iso", "source"])
            receipt = service.write_plan(plan, root / "copy", root / "receipt.json")
            on_disk = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["write"]["target"], str(root / "copy"))
            self.assertEqual(on_disk, json.loads(json.dumps(receipt)))
            self.assertTrue(service.load_container(root / "copy").verified)

    def test_loose_savegame_means_its_signed_folder(self):
        """fx1 (review r2-franchise MAJOR 2): Studio's Open dialog hands over SAVEGAME.DAT itself."""
        payload, _ = fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = signed_folder(root / "source", payload)
            loose = rr.SaveContainer.load(source / "SAVEGAME.DAT")
            self.assertEqual(loose.kind, "loose")
            self.assertEqual(service.upgrade_source(loose.path), source)
            self.assertEqual(service.upgrade_source(source), source)
            self.assertEqual(len(service.load_container(service.upgrade_source(loose.path)).members), 4)
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])
            from mod_editor.gui.franchise_upgrade_dialog_qt import FranchiseUpgradeDialog
            dialog = FranchiseUpgradeDialog(loose.path)
            self.assertEqual(dialog.source, source)
            self.assertEqual(Path(dialog.output_edit.text()), root / "source-upgraded")
            dialog.plan = object()
            for text in ("", "   ", "/"):
                dialog.output_edit.setText(text)
                with patch.object(service, "write_plan") as write:
                    dialog._write()     # an empty field is a refusal, not an exception in the UI slot
                    write.assert_not_called()
                self.assertIn("Choose a new save folder", dialog.details.toPlainText())
            dialog.deleteLater()
            app.processEvents()

    def test_changed_disc_refuses_and_dry_run_never_writes_a_save(self):
        payload, _ = fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = signed_folder(root / "source", payload)
            disc = root / "disc.iso"
            disc.write_bytes(b"current")
            plan = service.UpgradePlan(service.load_container(source), disc, payload,
                                       {"disc_sha256": service.hash_file(disc)})
            receipt = service.write_plan(plan, None, root / "preview.json")
            self.assertTrue(receipt["dry_run"])
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["disc.iso", "preview.json", "source"])
            disc.write_bytes(b"different")
            with self.assertRaisesRegex(up.UpgradeRefused, "disc changed"):
                service.write_plan(plan, root / "copy", root / "copy.json")
            self.assertFalse((root / "copy").exists())
            self.assertFalse((root / "copy.json").exists())

    def test_zip_export_path_guards_signature_and_type_refusals(self):
        payload, _ = fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = signed_folder(root / "source", payload)
            for output, receipt in ((source / "copy", root / "r.json"),
                                    (root / "copy", source / "receipt.json"),
                                    (root / "copy", root / "copy/receipt.json")):
                with self.assertRaises(up.UpgradeRefused):
                    service.check_paths(source, root / "disc.iso", output, receipt)
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                for member in source.iterdir():
                    handle.writestr("UDATA/test/" + member.name, member.read_bytes())
            container = service.load_container(archive)
            service.write_copy(container, payload, root / "from-zip")
            self.assertEqual(service.load_container(root / "from-zip").members, container.members)
            (source / "TYPE").write_bytes("STG\0".encode("utf-16-le"))
            with self.assertRaisesRegex(up.UpgradeRefused, "TYPE"):
                service.load_container(source)
            (source / "EXTRA").write_bytes(bytes(20))
            with self.assertRaises(ValueError):
                service.load_container(source)


if __name__ == "__main__":
    unittest.main()
