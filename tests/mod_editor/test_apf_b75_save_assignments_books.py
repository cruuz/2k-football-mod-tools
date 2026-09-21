"""Beta 75: Save Assignments states its scope and refuses a stale built folder.

Aszemple reported that pointing a saved label at a cloned book type did not bring
his fine-tuned plays with it.  The feature only re-points a label; the plays come
from the built game folder.  These tests cover the pre-write comparison between
the project's staged book and the folder's own copy, and the page copy that says
what the action writes and what it does not.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.apf_studio import save_playbooks as service  # noqa: E402
from mod_editor.core import apf2k8_book_identity as identity  # noqa: E402
from mod_editor.core import apf2k8_splb_writer as splb  # noqa: E402
from tests.mod_editor.test_apf_book_unlock import book_body, iff, roster_body  # noqa: E402
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture  # noqa: E402
from tests.mod_editor.test_apf_ps3_roster_convert import Fixture  # noqa: E402
import apf_outer  # noqa: E402
import apf_roster  # noqa: E402


BOOK_TYPE = "Book"


def built_folder(root: Path, body: bytes, *, book_type: str = BOOK_TYPE) -> Path:
    """A real one-pack game folder whose offensive label 0 is ``book_type``.

    The archive, IFF container and SPLB resource are the genuine formats, so the
    service reads the folder's book through the shipping CRC lookup and parser.
    """
    disc = bytearray(roster_body())
    label = identity.parse_roster_identity(bytes(disc)).labels[0]
    target = apf_roster.resolve_relative(bytes(disc), label.offset, "label")
    text = book_type.encode("utf-16-be") + b"\0\0"
    assert len(text) <= len((label.name + "\0").encode("utf-16-be"))
    disc[target:target + len(text)] = text
    struct.pack_into(">i", disc, label.offset + 4, target - label.offset - 4 + 1)
    resources = sorted([(apf_roster.OUTER_NAME_ID, iff(bytes(disc), "roster", "ROST")),
                        (identity.filename_id(book_type), iff(body, "spb", "SPLB"))])
    archive = bytearray(2048)
    rows = []
    for name_id, resource in resources:
        rows.append((name_id, len(archive) // 2048, len(resource) // 2048))
        archive.extend(resource)
    struct.pack_into(">6I", archive, 0, apf_outer.MAGIC, 2048, 1, 0, len(rows), 0)
    struct.pack_into(">II8s", archive, 24, len(archive) // 2048, 0,
                     "0A".encode("utf-16-be").ljust(8, b"\0"))
    for index, row in enumerate(rows):
        struct.pack_into(">3I", archive, 40 + index * 12, *row)
    root.mkdir(parents=True, exist_ok=True)
    (root / "0A").write_bytes(bytes(archive))
    return root / "0A"


def fine_tuned(body: bytes) -> bytes:
    """One changed play rating, the smallest edit Fine-tune Plays can produce."""
    tuned = bytearray(body)
    struct.pack_into(">H", tuned, splb.RECORD_BASE, splb.SplbEntry(3, 0, 0).encode())
    assert bytes(tuned) != body
    return bytes(tuned)


class FolderBookCheckTests(unittest.TestCase):
    """Refuse when the selected built folder does not hold the project's book."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="apf-b75-save-assignments-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Roster.ROS"
        self.source.write_bytes(Fixture().expected())
        self.document = service.inspect_save(self.source)
        self.output = self.root / "New roster.ROS"
        self.manifest = self.output.with_name(self.output.name + ".label-type.json")
        self.folder_book = book_body(BOOK_TYPE)
        self.index = built_folder(self.root / "Built game", self.folder_book)

    def test_a_folder_built_before_the_fine_tuning_is_refused_with_no_output(self) -> None:
        message = ("The built game folder does not contain your fine-tuned Book. "
                   "Build the game folder from this project first, then save assignments.")
        self.assertEqual(
            service.PROJECT_BOOK_MISMATCH.format(book_type=BOOK_TYPE), message)
        staged = fine_tuned(self.folder_book)
        with self.assertRaises(service.SavePlaybookError) as refusal:
            service.prepare_label_type(self.document, 0, BOOK_TYPE, self.index, staged)
        self.assertEqual(str(refusal.exception), message)
        with self.assertRaises(service.SavePlaybookError) as refused_write:
            service.write_label_type(self.document, 0, BOOK_TYPE, self.index, self.output, staged)
        self.assertEqual(str(refused_write.exception), message)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.assertEqual(self.source.read_bytes(), self.document.raw_payload)

    def test_a_folder_built_from_this_project_is_accepted_and_hashed(self) -> None:
        receipt = service.write_label_type(
            self.document, 0, BOOK_TYPE, self.index, self.output, self.folder_book)
        expected = hashlib.sha256(self.folder_book).hexdigest()
        self.assertEqual(receipt["folder_book_sha256"], expected)
        self.assertEqual(receipt["built_book"]["sha256"], expected)
        self.assertEqual(receipt["built_book"]["project_book_sha256"], expected)
        self.assertTrue(receipt["built_book"]["project_book_compared"])
        self.assertFalse(receipt["runtime_in_game_proved"])
        self.assertTrue(self.output.is_file())
        identity.verify_save_label_type(
            self.document.raw_payload, self.output.read_bytes(), receipt)

    def test_a_project_with_no_edit_for_this_book_is_not_checked(self) -> None:
        _, receipt = service.prepare_label_type(self.document, 0, BOOK_TYPE, self.index)
        self.assertEqual(receipt["folder_book_sha256"],
                         hashlib.sha256(self.folder_book).hexdigest())
        self.assertIsNone(receipt["built_book"]["project_book_sha256"])
        self.assertFalse(receipt["built_book"]["project_book_compared"])
        # An unedited project reaches the same result as passing nothing at all.
        _, again = service.prepare_label_type(
            self.document, 0, BOOK_TYPE, self.index, None)
        self.assertEqual(again, receipt)


class StagedBookAccessorTests(FacadeFixture):
    """The page reads the session's existing staged view, it never reparses."""

    def test_no_session_no_edit_and_one_staged_edit(self) -> None:
        unedited = self.backend.initial.books["O-ManBlock"]
        self.assertIsNone(self.facade.staged_book_body("O-ManBlock"))
        self.assertIsNone(self.facade.staged_book_body("not a book"))
        self.stage(dict(kind="ratings", book="O-ManBlock", formation=62, ratings=[7, 4, 1]))
        staged = self.facade.staged_book_body("O-ManBlock")
        self.assertIsNotNone(staged)
        self.assertNotEqual(staged, unedited)
        self.assertEqual(staged, self.backend.set_ratings(unedited, 62, (7, 4, 1)))
        # A book this project never touched still reports no edit.
        self.assertIsNone(self.facade.staged_book_body("X-43Cover2"))
        session, self.facade.session = self.facade.session, None
        self.assertIsNone(self.facade.staged_book_body("O-ManBlock"))
        self.facade.session = session


class PageCopyTests(unittest.TestCase):
    """The Save Assignments page and its confirmation say what the action writes."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication
        cls.application = QApplication.instance() or QApplication([])

    @staticmethod
    def _runner(label, operation, on_success=None, blocking=True):
        del label, blocking
        result = operation(lambda *_args: None)
        if on_success is not None:
            on_success(result)
        return True

    def test_the_page_states_the_boundary_and_the_order_that_works(self) -> None:
        from mod_editor.apf_studio import save_playbooks_qt as qt
        panel = qt.SavePlaybookAssignmentsPanel(self._runner)
        try:
            copy = panel.scope.text()
            self.assertEqual(copy, service.SAVE_ASSIGNMENTS_SCOPE)
            self.assertIn("What this writes", copy)
            self.assertIn("What it does not write", copy)
            self.assertIn("Build Game Folder", copy)
            self.assertNotIn("\N{EM DASH}", copy)
            self.assertIsNone(panel.project_book("Book"))
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_the_confirmation_repeats_the_scope_and_carries_the_staged_book(self) -> None:
        from mod_editor.apf_studio import save_playbooks_qt as qt
        from tests.test_apf_save_playbook_assignments import synthetic_save
        with tempfile.TemporaryDirectory(prefix="apf-b75-page-") as temporary:
            source = Path(temporary) / "Roster.ROS"
            source.write_bytes(synthetic_save())
            facade = SimpleNamespace(staged_book_body=lambda name: b"staged " + name.encode())
            panel = qt.SavePlaybookAssignmentsPanel(self._runner, facade)
            try:
                panel.load_path(source)
                label = panel.document.playbooks[0]
                selection = f"00: {label.name} ({label.side}, {label.kind})"
                receipt = {"affected_team_indices": [0], "output": "new.ROS",
                           "manifest": "new.json", "changed_byte_count": 2,
                           "folder_book_sha256": "a" * 64, "runtime_status": "UNWITNESSED"}
                with patch.object(qt.QInputDialog, "getItem",
                                  side_effect=[(selection, True), ("Book", True)]), \
                        patch.object(qt.QFileDialog, "getOpenFileName", return_value=("built/0A", "")), \
                        patch.object(qt.QFileDialog, "getSaveFileName", return_value=("new.ROS", "")), \
                        patch.object(qt, "built_label_types", return_value=("Book",)), \
                        patch.object(qt, "prepare_label_type", return_value=(b"", receipt)) as prepare, \
                        patch.object(qt.QMessageBox, "question", return_value=qt.QMessageBox.Yes) as confirm, \
                        patch.object(qt.QMessageBox, "information") as done, \
                        patch.object(qt, "write_label_type", return_value=receipt) as write:
                    panel.label_type_button.click()
                self.assertEqual(prepare.call_args.args[-1], b"staged Book")
                self.assertEqual(write.call_args.args[-1], b"staged Book")
                self.assertIn(service.SAVE_ASSIGNMENTS_SCOPE, confirm.call_args.args[2])
                self.assertIn("a" * 16, confirm.call_args.args[2])
                self.assertIn("a" * 16, done.call_args.args[2])
            finally:
                panel.deleteLater()
                self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
