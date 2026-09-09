"""Check my rosters on the ★ Rosters page (beta 63.1): the dialog rows, the repair with undo, the export.

Every fixture is generated in memory; a container written to a temp folder is the only file involved.
The core (``nfl2k5_college_check``) owns the byte contract; these tests prove the page installs its
candidate through the page's own undo, dirty state, Build & Share export and signed-copy paths, refuses
what the WIRING spec says it refuses, and never writes over a source.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_college_check as check  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as codec  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import CollegeCheckDialog, RosterEditorPanel  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402
from test_nfl2k5_college_check import corrupt, rel  # noqa: E402
from test_nfl2k5_franchise_save import synthetic_franchise  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body, synthetic_resource, synthetic_save_v0  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402


def rename_college(payload: bytes, index: int, name: str) -> bytes:
    """Overwrite college ``index``'s name string in place (the new name must not be longer)."""

    data = bytearray(payload)
    doc = codec.decode(data)
    table = doc.tables["colleges"].offset
    target = doc.rel(table + 8 * index)
    current = rr.RosterDocument(payload, base=rr.find_block_base(payload)).colleges[index]
    encoded = name.encode("utf-16-le") + b"\0\0"
    room = len(current.encode("utf-16-le")) + 2
    assert len(encoded) <= room, (name, current)
    data[target:target + room] = encoded + bytes(room - len(encoded))
    return bytes(data)


def word(payload: bytes, offset: int) -> bytes:
    return bytes(payload[offset:offset + 4])


class CollegeCheckPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.app.processEvents()

    def disc(self, td: Path, body: bytes) -> SyntheticXiso:
        dummies = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(5)]
        return SyntheticXiso(td, dummies + [(5, synthetic_resource(body)), (200, b"TAIL" + bytes(0x100))],
                             pack_sizes=(0xA0000,), pack_sectors=(64,))

    # ------------------------------------------------------------------ the button and the dialog
    def test_the_checks_tab_offers_the_button_with_nothing_loaded(self) -> None:
        panel = self.panel
        self.assertEqual(panel.college_check_button.text(), "Check my rosters…")
        self.assertTrue(panel.college_check_button.isEnabled())
        self.assertIs(panel.college_check_button.parentWidget(), panel.repair_button.parentWidget())
        session = panel.college_check_session()
        self.assertEqual((session["kind"], session["repairable"], session["scan"]), ("none", False, None))
        dialog = CollegeCheckDialog(panel, session)
        try:
            self.assertFalse(dialog.repair_button.isEnabled())
            self.assertTrue(dialog.choose_save_button.isEnabled() and dialog.choose_disc_button.isEnabled())
            self.assertIn("No roster is loaded", dialog.summary.text())
            self.assertEqual(dialog.college_combo.count(), 0)
        finally:
            dialog.deleteLater()

    def test_rows_list_invalid_and_missing_references_in_both_pools(self) -> None:
        data = bytearray(synthetic_save_v0(synthetic_body()))
        doc = codec.decode(data)
        struct.pack_into("<I", data, doc.layout.root + 8, 1)            # one zero-initialised template record
        rel(data, doc.players[0].offset, doc.layout.end + 16)            # primary #0: outside the arena
        rel(data, doc.players[1].offset, None)                           # primary #1: null (missing)
        bad = bytes(data)
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "MyRoster", bad)
            self.assertTrue(self.panel.load_save(source), self.panel.status_label.text())
            session = self.panel.college_check_session()
            self.assertEqual(session["kind"], "document")
            self.assertTrue(session["repairable"], session["guidance"])
            scan = session["scan"]
            self.assertEqual(scan.sha256, hashlib.sha256(self.panel.document.to_body()).hexdigest())
            dialog = CollegeCheckDialog(self.panel, session)
            try:
                invalid = dialog.rows(dialog.invalid_table)
                missing = dialog.rows(dialog.missing_table)
                self.assertEqual(len(invalid), 1)
                self.assertEqual(invalid[0][:7], ["MyRoster", "Peyton Manning", "primary", "0",
                                                  f"0x{doc.players[0].offset:X}",
                                                  f"0x{struct.unpack_from('<I', bad, doc.players[0].offset)[0]:08X}",
                                                  "outside_arena"])
                self.assertTrue(invalid[0][7].startswith("Unknown"))
                self.assertEqual(invalid[0][8], "Tennessee")               # no None / blank entry: entry 0
                self.assertEqual([(row[2], row[3], row[6]) for row in missing],
                                 [("primary", "1", "null_reference"), ("secondary", "0", "null_reference")])
                self.assertEqual(missing[1][1], "#0")
                self.assertIn("(1)", dialog.invalid_label.text())
                self.assertIn("(2)", dialog.missing_label.text())
                self.assertEqual(dialog.college_combo.count(), 5)
                self.assertEqual(dialog.college_combo.currentData(), 0)
                self.assertTrue(dialog.repair_button.isEnabled())
                self.assertEqual(dialog.issues.toPlainText(), "No college table issues.")
                # the proposed column follows the combo
                dialog.college_combo.setCurrentIndex(3)
                self.assertEqual(dialog.rows(dialog.invalid_table)[0][8], "Marshall")
                self.assertEqual(dialog.rows(dialog.missing_table)[1][8], "Marshall")
            finally:
                dialog.deleteLater()

    # ------------------------------------------------------------------ repair, undo, redo, signed copy
    def test_repair_installs_with_undo_redo_and_the_signed_copy_reads_back(self) -> None:
        bad, field = corrupt(synthetic_save_v0(synthetic_body()), "outside")
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "source", bad)
            self.assertTrue(self.panel.load_save(source))
            panel, document = self.panel, self.panel.document
            player = document.players[0]
            self.assertEqual(player.college, "")
            with self.assertRaisesRegex(codec.SaveRostError, "college pointer"):
                panel.write_copy_to(Path(td) / "blocked")
            session = panel.college_check_session()
            dialog = CollegeCheckDialog(panel, session)
            try:
                receipt = dialog.repair()
                assert receipt is not None
                self.assertEqual((receipt["changed"], receipt["installed"], receipt["college_index"]), (1, True, 0))
                self.assertFalse(receipt["saved"])
                self.assertIn("Saved: no", dialog.receipt_text.toPlainText())
                self.assertIn("EXTRA recomputed", dialog.receipt_text.toPlainText())
                self.assertFalse(dialog.repair_button.isEnabled())          # the fresh check has nothing left
                self.assertIn("0 invalid, 0 missing", dialog.summary.text())
            finally:
                dialog.deleteLater()
            after = document.to_body()
            self.assertEqual(word(after, field), struct.pack("<I", receipt["repairs"][0]["new_raw"]))
            self.assertEqual(after[:field] + after[field + 4:], bad[:field] + bad[field + 4:])
            self.assertIs(document.players[0], player)                      # object identity retained
            self.assertEqual((player.college, player.college_index), ("Tennessee", 0))
            self.assertEqual(panel._dirty, {("primary", 0)})
            self.assertTrue(panel.is_dirty())
            self.assertIn(("primary", 0), panel._college_repairs)
            self.assertEqual(panel.college_combo.currentIndex(), 0 if panel.selected_player() is player else
                             panel.college_combo.currentIndex())
            self.assertIn("repaired 1 college reference", panel.report.toPlainText())
            self.assertEqual(panel.undo(), "college repair (1)")
            undone = document.to_body()
            self.assertEqual(undone, bad)                                   # the exact prior word
            self.assertEqual((player.college, panel._dirty, panel._college_repairs), ("", set(), {}))
            self.assertFalse(panel.is_dirty())
            self.assertEqual(panel.redo(), "college repair (1)")
            self.assertEqual(document.to_body(), after)                     # the exact candidate word
            self.assertEqual(panel._dirty, {("primary", 0)})
            written = panel.write_copy_to(Path(td) / "fixed")
            self.assertTrue(written["signed"] and written["readback_verified"])
            copy = rr.SaveContainer.load(Path(td) / "fixed")
            self.assertEqual(copy.savegame, after)
            self.assertEqual(hashlib.sha256(copy.savegame).hexdigest(), receipt["after_sha256"])
            self.assertEqual(check.scan(copy.savegame).findings, ())
            self.assertEqual(rr.SaveContainer.load(source).savegame, bad)   # never the source
            meta = {name: data for name, data in copy.members.items() if name.endswith("SaveMeta.xbx")}
            self.assertEqual(meta, {name: data for name, data in rr.SaveContainer.load(source).members.items()
                                    if name.endswith("SaveMeta.xbx")})
            self.assertEqual(len(meta), 1)

    def test_a_stale_check_or_a_reloaded_roster_is_refused_and_nothing_changes(self) -> None:
        bad, field = corrupt(synthetic_save_v0(synthetic_body()), "outside")
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(self.panel.load_save(write_container(Path(td) / "source", bad)))
            panel = self.panel
            session = panel.college_check_session()
            player = panel.document.players[1]
            panel.set_field(player, "speed", 77)                            # the composed bytes moved on
            before = panel.document.to_body()
            depth = panel.undo_stack.depth
            with self.assertRaisesRegex(rr.RosterRecordError, "changed since this check"):
                panel.repair_college_references(session, 0)
            self.assertEqual(panel.document.to_body(), before)
            self.assertEqual((panel._college_repairs, panel.undo_stack.depth), ({}, depth))
            dialog = CollegeCheckDialog(panel, session)
            try:
                self.assertIsNone(dialog.repair())
                self.assertIn("Refused", dialog.receipt_text.toPlainText())
                self.assertFalse(dialog.repair_button.isEnabled())
            finally:
                dialog.deleteLater()
            fresh = panel.college_check_session()
            receipt = panel.repair_college_references(fresh, 0)
            self.assertEqual(receipt["changed"], 1)
            self.assertEqual(panel.document.players[1].record.values["speed"], 77)   # the rating stays
            # a reload invalidates a check even when the bytes happen to match
            stale = panel.college_check_session()
            self.assertTrue(panel.load_save(write_container(Path(td) / "again", bad)))
            with self.assertRaisesRegex(rr.RosterRecordError, "reloaded"):
                panel.repair_college_references(stale, 0)
            self.assertEqual(panel.document.to_body(), bad)

    # ------------------------------------------------------------------ tables that refuse
    def test_a_broken_college_table_disables_repair_and_a_failed_load_is_still_checked(self) -> None:
        panel = self.panel
        with tempfile.TemporaryDirectory() as td:
            # (a) an unaligned name: the legacy document still loads, the check names the table entry
            data = bytearray(synthetic_save_v0(synthetic_body()))
            doc = codec.decode(data)
            table = doc.tables["colleges"].offset
            rel(data, table, doc.rel(table) + 1)
            self.assertTrue(panel.load_save(write_container(Path(td) / "unaligned", bytes(data))))
            session = panel.college_check_session()
            self.assertFalse(session["repairable"])
            self.assertEqual(len(session["scan"].table_issues), 1)
            self.assertEqual(len(session["scan"].findings), 3)              # three players use entry 0
            self.assertIn("college table", session["guidance"])
            dialog = CollegeCheckDialog(panel, session)
            try:
                self.assertFalse(dialog.repair_button.isEnabled())
                self.assertIn("unaligned UTF-16 string", dialog.issues.toPlainText())
                self.assertIn("(1)", dialog.issues_label.text())
                self.assertEqual(len(dialog.rows(dialog.invalid_table)), 3)
            finally:
                dialog.deleteLater()
            with self.assertRaisesRegex(rr.RosterRecordError, "college table"):
                panel.repair_college_references(session, 0)
            # (b) a name outside the file: the page cannot load it, the verified container is still checked
            data = bytearray(synthetic_franchise())
            doc = codec.decode(data)
            rel(data, doc.tables["colleges"].offset, len(data) + 100)
            panel.load_document(rr.load_body(synthetic_body()), label="other")   # something else loaded first
            self.assertFalse(panel.load_save(write_container(Path(td) / "outside", bytes(data))))
            self.assertIn("string offset", panel.status_label.text())
            self.assertIn("Check my rosters", panel.status_label.text())
            self.assertIsNotNone(panel._college_check_container)
            self.assertIsNotNone(panel.document)                               # the earlier roster stays loaded
            self.assertEqual(panel.college_check_session()["kind"], "document")
            panel = RosterEditorPanel()
            try:
                self.assertFalse(panel.load_save(Path(td) / "outside"))
                session = panel.college_check_session()
                self.assertEqual((session["kind"], session["repairable"]), ("save", False))
                self.assertEqual(len(session["scan"].findings), 3)
                self.assertEqual(len(session["scan"].table_issues), 1)
                self.assertIn("Load this file after repair", session["guidance"])
                with self.assertRaisesRegex(rr.RosterRecordError, "read-only"):
                    panel.repair_college_references(session, 0)
            finally:
                panel.deleteLater()
            # (c) no college table at all: the layout diagnostic is kept and Repair is not offered
            data = bytearray(synthetic_save_v0(synthetic_body()))
            struct.pack_into("<I", data, codec.decode(data).layout.root + 0x20, 0)
            self.assertTrue(self.panel.load_save(write_container(Path(td) / "notable", bytes(data))))
            session = self.panel.college_check_session()
            self.assertIn("no local college table", session["error"])
            self.assertFalse(session["repairable"])
            dialog = CollegeCheckDialog(self.panel, session)
            try:
                self.assertFalse(dialog.repair_button.isEnabled())
                self.assertIn("no local college table", dialog.summary.text())
            finally:
                dialog.deleteLater()

    # ------------------------------------------------------------------ disc: blank, duplicates, export
    def test_repair_to_blank_persists_in_dirty_state_and_the_disc_export(self) -> None:
        body = rename_college(synthetic_body(), 1, "")                     # a valid blank entry, no None entry
        bad, field = corrupt(body, "past_table")
        with tempfile.TemporaryDirectory() as td:
            fixture = self.disc(Path(td), bad)
            source_bytes = Path(fixture.path).read_bytes()
            panel = self.panel
            self.assertTrue(panel.load_disc(fixture.path), panel.status_label.text())
            session = panel.college_check_session()
            self.assertTrue(session["repairable"])
            self.assertEqual(session["scan"].findings[0].reason, "off_table")
            receipt = panel.repair_college_references(session)              # the core's policy: first blank
            self.assertEqual((receipt["college_index"], receipt["college"]), (1, ""))
            document = panel.document
            self.assertEqual((document.players[0].college, document.players[0].college_index), ("", 1))
            self.assertEqual(document.diff(), [])                             # the text diff is empty...
            self.assertEqual(panel._dirty, {("primary", 0)})                  # ...the journal keeps it dirty
            self.assertTrue(panel.is_dirty())
            edits = panel.edits_document()
            self.assertEqual([(e["pool"], e["index"], e["fields"], e["names"]) for e in edits["edits"]],
                             [("primary", 0, {}, {"college": ""})])
            self.assertEqual((edits["edits"][0]["first"], edits["edits"][0]["last"]), ("Peyton", "Manning"))
            export = receipt["export"]
            self.assertEqual((export["verified"], export["entry"], export["matched"], export["note"]), (True, 1, 1, ""))
            self.assertIn("Export replay on the original disc body: 1/1", panel.college_repair_text(receipt))
            replayed, log = rr.apply_body(bad, edits)
            self.assertEqual(replayed, document.to_body())
            self.assertEqual(word(replayed, field), struct.pack("<I", receipt["repairs"][0]["new_raw"]))
            # a rating edit after the repair keeps the journal entry in the export
            speed = 66 if document.players[0].record.values["speed"] != 66 else 65
            panel.set_field(document.players[0], "speed", speed)
            edits = panel.edits_document()
            self.assertEqual((edits["edits"][0]["fields"], edits["edits"][0]["names"]), ({"speed": speed}, {"college": ""}))
            saved = panel.save_edits_to(Path(td) / "roster_edits.json")
            self.assertEqual(saved["edits"][0]["names"], {"college": ""})
            written = panel.write_copy_to(Path(td) / "copy.xiso.iso")
            self.assertEqual(written["fields_written"], 2)
            copy = rr.load_image(Path(td) / "copy.xiso.iso")
            self.assertEqual((copy.players[0].college_index, copy.players[0].record.values["speed"]), (1, speed))
            self.assertEqual(check.scan(copy.original).findings, ())
            self.assertEqual(Path(fixture.path).read_bytes(), source_bytes)   # the source disc is untouched
            # undo of the rating leaves the repair; undo of the repair restores the off-table word
            panel.undo()
            self.assertEqual(panel._dirty, {("primary", 0)})
            self.assertEqual(panel.undo(), "college repair (1)")
            self.assertEqual(document.to_body(), bad)
            self.assertEqual((panel._dirty, panel._college_repairs, panel.edits_document()["edits"]), (set(), {}, []))

    def test_duplicate_college_names_export_the_first_matching_entry_and_say_so(self) -> None:
        body = rename_college(synthetic_body(), 4, "Marshall")             # entries 3 and 4 share a name
        bad, field = corrupt(body, "outside")
        with tempfile.TemporaryDirectory() as td:
            fixture = self.disc(Path(td), bad)
            panel = self.panel
            self.assertTrue(panel.load_disc(fixture.path), panel.status_label.text())
            session = panel.college_check_session()
            receipt = panel.repair_college_references(session, 4)
            document = panel.document
            self.assertEqual((document.players[0].college, document.players[0].college_index), ("Marshall", 4))
            export = receipt["export"]
            self.assertEqual((export["verified"], export["entry"], export["selected_entry"]), (True, 3, 4))
            self.assertIn("first of that name", export["note"])
            text = panel.college_repair_text(receipt)
            self.assertIn("college table entry 3 'Marshall'", text)
            self.assertIn("entries 3 and 4 are both named 'Marshall'", text)
            self.assertIn(text, panel.report.toPlainText())
            edits = panel.edits_document()
            self.assertEqual(edits["edits"][0]["names"], {"college": "Marshall"})
            self.assertNotIn("college_pointer", edits["edits"][0]["fields"])
            replayed, _log = rr.apply_body(bad, edits)
            self.assertEqual(word(replayed, field), struct.pack("<i", document.college_offsets[3] - field + 1))
            panel.write_copy_to(Path(td) / "copy.xiso.iso")
            copy = rr.load_image(Path(td) / "copy.xiso.iso")
            self.assertEqual((copy.players[0].college, copy.players[0].college_index), ("Marshall", 3))
            self.assertEqual(check.scan(copy.original).findings, ())

    # ------------------------------------------------------------------ franchise
    def test_franchise_repair_undoes_and_redoes_around_a_schedule_and_a_rating_edit(self) -> None:
        bad, field = corrupt(synthetic_franchise(), "outside")
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "source", bad)
            panel = self.panel
            self.assertTrue(panel.load_save(source))
            page = panel.franchise_panel
            self.assertTrue(page.active)
            self.assertTrue(page.edit_game(0, 1, hour=8, minute=30), page.last_error)
            player = panel.document.players[0]
            panel.set_field(player, "speed", 77)
            with self.assertRaisesRegex(ValueError, "college pointer"):
                panel.write_copy_to(Path(td) / "blocked")
            session = panel.college_check_session()
            self.assertEqual(session["source_kind"], "save")
            edited = panel.document.to_body()                               # schedule + rating, bad college
            receipt = panel.repair_college_references(session)
            after = panel.document.to_body()
            self.assertEqual(after[:field] + after[field + 4:], edited[:field] + edited[field + 4:])
            self.assertEqual(word(after, field), struct.pack("<I", receipt["repairs"][0]["new_raw"]))
            self.assertEqual(page.edit_labels(), [page.edit_labels()[0]])   # the franchise journal is unchanged
            self.assertEqual(len(page.edit_labels()), 1)
            self.assertEqual(panel._dirty, {("primary", 0)})
            self.assertEqual(panel.undo(), "college repair (1)")
            self.assertEqual(panel.document.to_body(), edited)              # the exact prior word, edits intact
            self.assertEqual(panel.document.players[0].record.values["speed"], 77)
            self.assertEqual(len(page.edit_labels()), 1)
            with self.assertRaisesRegex(ValueError, "college pointer"):
                panel.write_copy_to(Path(td) / "blocked2")
            self.assertEqual(panel.redo(), "college repair (1)")
            self.assertEqual(panel.document.to_body(), after)
            self.assertEqual(panel.undo(), "college repair (1)")
            self.assertEqual(panel.undo(), "Peyton Manning: speed")
            self.assertEqual(len(page.edit_labels()), 1)
            self.assertTrue(panel.undo())                                    # the schedule edit
            self.assertEqual(panel.document.to_body(), bad)
            self.assertEqual((panel._dirty, page.edit_labels()), (set(), []))
            for _ in range(3):
                self.assertTrue(panel.redo())
            self.assertEqual(panel.document.to_body(), after)
            written = panel.write_copy_to(Path(td) / "copy")
            self.assertTrue(written["signed"])
            self.assertEqual(written["franchise_edits"], page.edit_labels())
            copy = rr.SaveContainer.load(Path(td) / "copy")
            self.assertEqual(copy.savegame, after)
            self.assertEqual(copy.document().players[0].record.values["speed"], 77)
            self.assertEqual(rr.SaveContainer.load(source).savegame, bad)

    def test_an_inline_mycareer_footer_refuses_a_different_college_and_keeps_the_recorded_one(self) -> None:
        from mod_editor.core import nfl2k5_my_career_save as career
        payload = synthetic_franchise()
        doc = codec.decode(payload)
        player = doc.players[0].offset
        block = bytearray(career.SIZE)
        block[:8] = career.MAGIC
        struct.pack_into("<HH", block, 8, 1, career.SIZE)
        block[16] = 1
        block[36:40] = bytes((3, 0, 0, payload[player + 0x35]))
        for field, stored in ((0, 44), (16, 48), (20, 52)):
            struct.pack_into("<I", block, stored, doc.rel(player + field) - doc.layout.root)
        block[56:60] = payload[player + 4:player + 8]
        struct.pack_into("<I", block, 60, career.word(payload, player + 0x18) & career.BIRTH_MASK)
        block[74] = 255
        original, _ = career.append(payload, career.seal(block))
        bad, field = corrupt(original, "outside")
        with tempfile.TemporaryDirectory() as td:
            panel = self.panel
            self.assertTrue(panel.load_save(write_container(Path(td) / "career", bad)), panel.status_label.text())
            session = panel.college_check_session()
            self.assertTrue(session["repairable"])
            depth = panel.undo_stack.depth
            with self.assertRaisesRegex(rr.RosterRecordError, "MyPlayer name or college reference changed"):
                panel.repair_college_references(session, 1)
            self.assertEqual(panel.document.to_body(), bad)                 # shown, not bypassed
            self.assertEqual((panel._college_repairs, panel.undo_stack.depth), ({}, depth))
            dialog = CollegeCheckDialog(panel, session)
            try:
                dialog.college_combo.setCurrentIndex(1)
                self.assertIsNone(dialog.repair())
                self.assertIn("MyCareer footer", dialog.receipt_text.toPlainText())
            finally:
                dialog.deleteLater()
            receipt = panel.repair_college_references(panel.college_check_session(), 0)
            self.assertEqual(receipt["changed"], 1)
            self.assertEqual(panel.document.to_body(), original)            # the recorded college, footer untouched
            career.read(panel.document.to_body())
            self.assertTrue(panel.write_copy_to(Path(td) / "copy")["signed"])

    # ------------------------------------------------------------------ chosen files, read-only
    def test_choose_save_and_choose_disc_scan_read_only_and_refuse_an_unsigned_save(self) -> None:
        bad, field = corrupt(synthetic_save_v0(synthetic_body()), "outside")
        disc_bad, _f = corrupt(synthetic_body(), "misaligned")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            panel = self.panel
            panel.load_document(rr.load_body(synthetic_body()), label="loaded")
            loaded = panel.document.to_body()
            source = write_container(td / "chosen", bad)
            session = panel.college_check_path(source)
            self.assertEqual((session["kind"], session["repairable"], session["source"]), ("save", False, "chosen"))
            self.assertEqual([(f.pool, f.index, f.reason) for f in session["scan"].findings],
                             [("primary", 0, "outside_arena")])
            self.assertIn("Read-only", session["guidance"])
            dialog = CollegeCheckDialog(panel, session)
            try:
                self.assertFalse(dialog.repair_button.isEnabled())
                self.assertEqual(len(dialog.rows(dialog.invalid_table)), 1)
                self.assertEqual(dialog.college_combo.count(), 5)
            finally:
                dialog.deleteLater()
            with self.assertRaisesRegex(rr.RosterRecordError, "read-only"):
                panel.repair_college_references(session, 0)
            # the loose SAVEGAME.DAT inside the folder is the same container
            loose = panel.college_check_path(td / "chosen" / "53450030" / "0001" / "SAVEGAME.DAT")
            self.assertEqual(loose["sha256"], session["sha256"])
            # an unsigned save is refused by the signature policy, not scanned around it
            (td / "unsigned").mkdir()
            (td / "unsigned" / "SAVEGAME.DAT").write_bytes(bad)
            refused = panel.college_check_path(td / "unsigned")
            self.assertIn("EXTRA", refused["error"])
            self.assertIsNone(refused["scan"])
            self.assertFalse(refused["repairable"])
            # a disc: the main roster resource is read through the archive reader, never load_image
            fixture = self.disc(td, disc_bad)
            disc = panel.college_check_path(fixture.path)
            self.assertEqual((disc["kind"], disc["repairable"]), ("disc", False))
            self.assertEqual([(f.pool, f.index, f.reason) for f in disc["scan"].findings],
                             [("primary", 0, "off_table")])
            self.assertEqual(disc["scan"].player_count, 8)
            bogus = SyntheticXiso(td / "bogus", [(100 + k, b"DUMY" + bytes(0x100)) for k in range(6)],
                                  pack_sizes=(0xA0000,), pack_sectors=(64,))
            foreign = panel.college_check_path(bogus.path)
            self.assertIn("not the main roster", foreign["error"])
            # nothing loaded on the page moved
            self.assertEqual(panel.document.to_body(), loaded)
            self.assertFalse(panel.is_dirty())
            self.assertEqual(rr.SaveContainer.load(source).savegame, bad)


if __name__ == "__main__":
    unittest.main()
