"""Model and service tests for the PS2 save editor dialog.

The dialog keeps its view model above the PyQt5 import so the gating and
capacity rules can be proved without a display.  The service tests run the
whole edit-and-verify path against a synthesized save, so no game data and no
memory card are required.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core.errors import ValidationError
from mod_editor.core.ps2_save_service import Ps2SaveService
from mod_editor.gui.ps2_save_dialog_qt import (
    PYQT5_AVAILABLE,
    PlayerNameRow,
    Ps2SaveEditorDialog,
    Ps2SaveEditorHost,
    STATUS_ALL,
    STATUS_EDITED,
    STATUS_UNCHANGED,
    filter_player_rows,
    name_capacity,
    ps2_save_action_state,
    suggested_psu_name,
)

import nfl2k5_ps2_save as save_lib
import nfl2k5_ps2_save_verify as verify_lib


def _row(index: int = 0, first: str = "Duane", last: str = "Starks",
         original_first: str | None = None, original_last: str | None = None
         ) -> PlayerNameRow:
    return PlayerNameRow(
        index=index,
        first=first,
        last=last,
        first_capacity=5,
        last_capacity=6,
        original_first=first if original_first is None else original_first,
        original_last=last if original_last is None else original_last,
    )


class NameCapacityTests(unittest.TestCase):
    def test_a_name_that_exactly_fills_the_slot_is_accepted(self) -> None:
        capacity = name_capacity(_row(), "last", "Starks")
        self.assertTrue(capacity.valid)
        self.assertEqual((capacity.used, capacity.capacity), (6, 6))

    def test_one_character_too_many_is_refused_with_both_numbers(self) -> None:
        capacity = name_capacity(_row(), "last", "Starksx")
        self.assertFalse(capacity.valid)
        self.assertIn("7 characters", capacity.message)
        self.assertIn("holds 6", capacity.message)

    def test_an_empty_name_is_allowed(self) -> None:
        self.assertTrue(name_capacity(_row(), "first", "").valid)

    def test_an_unknown_field_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "first.*last"):
            name_capacity(_row(), "middle", "X")


class FilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = (
            _row(0, "Duane", "Starks"),
            _row(1, "Renaldo", "Hill", original_last="Hilt"),
        )

    def test_search_matches_number_and_name(self) -> None:
        self.assertEqual(filter_player_rows(self.rows, search="renaldo").match_total, 1)
        self.assertEqual(filter_player_rows(self.rows, search="0").match_total, 1)

    def test_status_filters_split_edited_from_unchanged(self) -> None:
        edited = filter_player_rows(self.rows, status=STATUS_EDITED)
        unchanged = filter_player_rows(self.rows, status=STATUS_UNCHANGED)
        self.assertEqual(edited.match_total, 1)
        self.assertEqual(unchanged.match_total, 1)
        self.assertEqual(edited.player_total, 2)
        self.assertEqual(edited.edited_total, 1)

    def test_an_unknown_status_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "all, edited, or unchanged"):
            filter_player_rows(self.rows, status="whatever")

    def test_everything_is_returned_by_default(self) -> None:
        self.assertEqual(
            filter_player_rows(self.rows, status=STATUS_ALL).match_total, 2
        )


class ActionStateTests(unittest.TestCase):
    def test_nothing_is_offered_before_a_save_is_open(self) -> None:
        state = ps2_save_action_state(
            None, capacity=None, save_loaded=False, busy=False,
            edit_count=0, changed=False,
        )
        self.assertFalse(state.can_apply)
        self.assertFalse(state.can_write)
        self.assertFalse(state.can_revert_all)

    def test_apply_needs_a_changed_and_valid_name(self) -> None:
        row = _row()
        valid = name_capacity(row, "last", "Carey")
        invalid = name_capacity(row, "last", "Carey Junior")
        common = dict(save_loaded=True, busy=False, edit_count=0)
        self.assertTrue(
            ps2_save_action_state(row, capacity=valid, changed=True, **common).can_apply
        )
        self.assertFalse(
            ps2_save_action_state(row, capacity=valid, changed=False, **common).can_apply
        )
        self.assertFalse(
            ps2_save_action_state(row, capacity=invalid, changed=True, **common).can_apply
        )

    def test_writing_needs_at_least_one_staged_edit(self) -> None:
        common = dict(save_loaded=True, busy=False, changed=False, capacity=None)
        self.assertFalse(ps2_save_action_state(None, edit_count=0, **common).can_write)
        self.assertTrue(ps2_save_action_state(None, edit_count=1, **common).can_write)

    def test_a_busy_dialog_offers_nothing(self) -> None:
        row = _row()
        state = ps2_save_action_state(
            row, capacity=name_capacity(row, "last", "Carey"),
            save_loaded=True, busy=True, edit_count=1, changed=True,
        )
        self.assertFalse(state.can_apply)
        self.assertFalse(state.can_write)


class SuggestedNameTests(unittest.TestCase):
    def test_the_suggestion_is_derived_from_the_save_directory(self) -> None:
        self.assertEqual(
            suggested_psu_name("BASLUS-209192K5Roster"),
            "BASLUS-209192K5Roster-edited.psu",
        )

    def test_a_blank_directory_still_yields_a_usable_name(self) -> None:
        self.assertTrue(suggested_psu_name("").endswith(".psu"))


def _two_save_card(path: Path, *, different_first_game: bool = False) -> tuple[str, str]:
    """Create two independent, sealed saves on a small FAT-backed ECC card."""
    cluster_size = 1024
    clusters = [bytearray(cluster_size) for _ in range(3)]
    directory_mode, file_mode = 0x8427, 0x8417
    fat = [0xFFFFFFFF] * 256

    def store(data):
        start = len(clusters) - 3
        for offset in range(0, len(data), cluster_size):
            cluster = data[offset:offset + cluster_size]
            if offset:
                fat[len(clusters) - 4] = 0x80000000 | (len(clusters) - 3)
            clusters.append(bytearray(cluster.ljust(cluster_size, b"\0")))
        return start

    def entry(name, mode, length, first):
        row = bytearray(512)
        struct.pack_into("<II", row, 0, mode, length)
        struct.pack_into("<I", row, 0x10, first)
        row[0x40:0x40 + len(name)] = name.encode("ascii")
        return row

    dirs = []
    for label in ("First", "Second"):
        save = save_lib._synthetic_save()
        payload = save.files.pop(save.directory)
        save.directory = save_lib.SAVE_PREFIX + label
        save.files[save.directory] = payload
        if label == "Second":
            save_lib.set_player_name(save, 0, "first", "Delta")
        save.reseal()
        if different_first_game and label == "First":
            save.files["game.dat"] = save.files.pop(save.directory)
            save.directory = "OTHER-GAME"
        files = [entry(key, file_mode, len(data), store(data)) for key, data in save.files.items()]
        dirs.append((save.directory, len(files), store(b"".join(files))))
    root = store(entry(".", directory_mode, len(dirs) + 1, 0) + b"".join(
        entry(name, directory_mode, length, first) for name, length, first in dirs))
    clusters[0][:27] = b"Sony PS2 Memory Card Format"
    struct.pack_into("<H", clusters[0], 0x2A, 2)
    struct.pack_into("<III", clusters[0], 0x34, 3, len(clusters) - 3, root)
    struct.pack_into("<I", clusters[0], 0x50, 1)
    clusters[1][:] = struct.pack("<256I", 2, *([0xFFFFFFFF] * 255))
    clusters[2][:] = struct.pack("<256I", *fat)
    with path.open("wb") as out:
        for cluster in clusters:
            for offset in (0, 512):
                page = cluster[offset:offset + 512]
                out.write(page + b"".join(save_lib.chunk_ecc(page[n:n + 128])
                                          for n in range(0, 512, 128)) + bytes(4))
    return dirs[0][0], dirs[1][0]


class ServiceTests(unittest.TestCase):
    """Drive the real service the dialog binds to, on a synthesized save."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-save-service-")
        self.root = Path(self._temp.name)
        source = save_lib._synthetic_save()
        self.source_path = self.root / "source.psu"
        save_lib.write_psu(source, self.source_path)
        self.service = Ps2SaveService()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_opening_reports_the_save_and_its_players(self) -> None:
        summary = self.service.open(self.source_path)
        self.assertTrue(summary.checksum_valid)
        self.assertEqual(summary.player_count, 2)
        self.assertIn("checksum OK", summary.headline)
        self.assertEqual([row.first for row in self.service.players()],
                         ["Alpha", "Bravo"])

    def test_capacity_is_reported_in_characters(self) -> None:
        self.service.open(self.source_path)
        row = self.service.players()[0]
        self.assertEqual(row.first_capacity, len("Alpha"))

    def test_an_oversized_name_is_refused_before_anything_is_written(self) -> None:
        self.service.open(self.source_path)
        self.assertIsNotNone(self.service.validate_name(0, "first", "Wayovertheline"))
        with self.assertRaises(ValidationError):
            self.service.set_name(0, "first", "Wayovertheline")
        self.assertFalse(self.service.dirty)

    def test_writing_reseals_and_independently_verifies(self) -> None:
        self.service.open(self.source_path)
        self.service.set_name(0, "first", "Delta")
        self.assertTrue(self.service.dirty)
        output = self.root / "edited.psu"
        result = self.service.write(output)
        self.assertTrue(result.verified, result.detail)
        self.assertEqual(result.edits, 1)
        self.assertTrue(output.is_file())
        # The written save re-opens cleanly with the edit in place.
        reopened = Ps2SaveService()
        reopened.open(output)
        self.assertEqual(reopened.players()[0].first, "Delta")
        self.assertTrue(reopened.summary().checksum_valid)

    def test_writing_without_changes_is_refused(self) -> None:
        self.service.open(self.source_path)
        with self.assertRaises(ValidationError):
            self.service.write(self.root / "unchanged.psu")

    def test_repeated_name_edits_keep_original_allocation_and_verify(self) -> None:
        self.service.open(self.source_path)
        self.service.set_name(0, "first", "Al")
        self.assertEqual(self.service.players()[0].first_capacity, 5)
        self.service.set_name(0, "first", "D")
        self.assertTrue(self.service.write(self.root / "short.psu").verified)
        self.service.set_name(0, "first", "Delta")
        self.assertTrue(self.service.write(self.root / "restored.psu").verified)
        self.service.set_name(0, "first", "Alpha")
        self.assertFalse(self.service.dirty)

    def test_utf16_capacity_is_shared_by_the_dialog_and_writer(self) -> None:
        self.service.open(self.source_path)
        self.assertIsNotNone(self.service.validate_name(0, "first", "🏈🏈🏈"))
        row = _row(first="Alpha")
        self.assertFalse(name_capacity(row, "first", "🏈🏈🏈").valid)
        self.service.set_name(0, "first", "A🏈🏈")
        self.assertTrue(self.service.write(self.root / "unicode.psu").verified)

    def test_pcsx2_card_checksum_and_other_game_files_survive_verified_name_edit(self):
        source = self.root / "pcsx2.ps2"
        other, selected = _two_save_card(source, different_first_game=True)
        image = bytearray(source.read_bytes())
        marker = b"save-tag" + b"\xff" * 504
        image[528:2 * 528] = marker + save_lib.page_spare(b"\xff" * 512)
        selected_pages = verify_lib.decode_memcard(source, selected).card_pages[selected]
        for page in selected_pages:
            image[page * 528 + 524:page * 528 + 528] = b"keep"
        source.write_bytes(image)
        self.service.open(source, selected)
        self.service.set_name(0, "first", "Al")
        self.service.set_name(0, "first", "Echo")
        output = self.root / "verified.ps2"
        result = self.service.write(output)
        self.assertTrue(result.verified, result.detail)
        saved = output.read_bytes()
        self.assertEqual(saved[528:2 * 528], image[528:2 * 528])
        self.assertEqual(source.read_bytes(), image)
        for page in selected_pages:
            self.assertEqual(saved[page * 528 + 524:page * 528 + 528], b"keep")
        checks = verify_lib.verify_memcard_write(source, output, selected)
        self.assertEqual(checks["ecc"]["pcsx2_checksum_pages"], 1)
        self.assertEqual(checks["other_saves_untouched"], [other])
        self.assertTrue(checks["changed_card_pages"])

        altered = bytearray(saved)
        altered[528] ^= 1
        output.write_bytes(altered)
        with self.assertRaisesRegex(verify_lib.VerifyError, "outside the selected save"):
            verify_lib.verify_memcard_write(source, output, selected)
        altered = bytearray(saved)
        altered[528 + 200] ^= 1
        output.write_bytes(altered)
        with self.assertRaisesRegex(verify_lib.VerifyError, "wrong ECC"):
            verify_lib.verify_memcard_write(source, output, selected)

    def test_second_directory_survives_revert_psu_and_card_copy(self):
        card = self.root / "two-saves.ps2"
        first, second = _two_save_card(card)
        self.assertEqual(self.service.card_directories(card), (first, second))
        self.service.open(card, second)
        self.assertEqual(self.service.players()[0].first, "Delta")
        self.service.set_name(0, "first", "Al")
        self.service.revert()
        self.assertEqual(self.service.players()[0].first, "Delta")
        self.service.set_name(0, "first", "Echo")
        self.assertTrue(self.service.write(self.root / "second.psu").verified)
        copy = self.root / "new-card.ps2"
        self.assertTrue(self.service.write(copy).verified)
        self.service.open(copy, first)
        self.assertEqual(self.service.players()[0].first, "Alpha")
        self.service.open(copy, second)
        self.assertEqual(self.service.players()[0].first, "Echo")

    def test_names_that_share_storage_are_refused_before_editing(self):
        save = save_lib._synthetic_save()
        body = bytearray(save.payload)
        pointer_one = save_lib.WRAPPER_SIZE + 0x110
        pointer_two = pointer_one + 0x54
        distance, = struct.unpack_from("<i", body, pointer_one)
        struct.pack_into("<i", body, pointer_two, distance - 0x54)
        save.files[save.directory] = bytes(body)
        save.reseal()
        path = self.root / "shared.psu"
        save_lib.write_psu(save, path)
        self.service.open(path)
        self.assertEqual([row.first for row in self.service.players()], ["Alpha", "Alpha"])
        with self.assertRaises(ValidationError):
            self.service.set_name(0, "first", "Al")
        self.assertFalse(self.service.dirty)

    def test_revert_restores_the_file_on_disk(self) -> None:
        self.service.open(self.source_path)
        self.service.set_name(0, "first", "Delta")
        self.service.revert()
        self.assertFalse(self.service.dirty)
        self.assertEqual(self.service.players()[0].first, "Alpha")

    def test_the_source_file_is_never_modified(self) -> None:
        before = self.source_path.read_bytes()
        self.service.open(self.source_path)
        self.service.set_name(0, "first", "Delta")
        self.service.write(self.root / "elsewhere.psu")
        self.assertEqual(self.source_path.read_bytes(), before)

    def test_the_service_satisfies_the_dialog_host_protocol(self) -> None:
        self.assertIsInstance(self.service, Ps2SaveEditorHost)


class DialogContractTests(unittest.TestCase):
    def test_the_dialog_is_a_qt_dialog_without_starting_an_application(self) -> None:
        from PyQt5.QtWidgets import QDialog

        self.assertTrue(PYQT5_AVAILABLE)
        self.assertTrue(issubclass(Ps2SaveEditorDialog, QDialog))


class MemcardEccTests(unittest.TestCase):
    """The writer and the verifier must agree on ECC without sharing code."""

    VECTORS = (
        (bytes(128), "777f7f"),
        (bytes([1]) + bytes(127), "70007f"),
        (bytes([0, 1]) + bytes(126), "70017e"),
        (bytes([0x80]) + bytes(127), "07007f"),
    )

    def test_writer_ecc_matches_known_vectors(self) -> None:
        for chunk, expected in self.VECTORS:
            self.assertEqual(save_lib.chunk_ecc(chunk).hex(), expected)

    def test_verifier_computes_the_same_ecc_independently(self) -> None:
        # Different implementations, same answer -- that is the point of the
        # verifier owning its own copy.
        for chunk, _expected in self.VECTORS:
            self.assertEqual(
                save_lib.chunk_ecc(chunk), verify_lib._chunk_ecc(chunk)
            )

    def test_line_parity_depends_on_position(self) -> None:
        # The easiest thing to get wrong: a set bit at index 0 and at index 1
        # must not produce the same ECC.
        self.assertNotEqual(
            save_lib.chunk_ecc(bytes([1]) + bytes(127)),
            save_lib.chunk_ecc(bytes([0, 1]) + bytes(126)),
        )

    def test_page_spare_is_four_chunks_then_four_unused_bytes(self) -> None:
        spare = save_lib.page_spare(bytes([0x80]) + bytes(511))
        self.assertEqual(len(spare), save_lib.MEMCARD_PAGE - save_lib.MEMCARD_PAGE_DATA)
        self.assertEqual(spare[:3].hex(), "07007f")
        self.assertEqual(spare[12:], bytes(4))


class MemcardWriteRefusalTests(unittest.TestCase):
    """Fail-closed rules that protect a user's card."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-card-")
        self.root = Path(self._temp.name)
        self.save = save_lib._synthetic_save()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_writing_over_the_source_card_is_refused(self) -> None:
        card = self.root / "card.ps2"
        card.write_bytes(b"\x00" * save_lib.MEMCARD_PAGE)
        with self.assertRaisesRegex(save_lib.SaveError, "Refusing to write over"):
            save_lib.write_into_memcard(card, self.save, card)

    def test_a_hard_link_to_the_source_card_is_refused(self) -> None:
        # A hard link has a different path but the same inode, so comparing
        # resolved paths is not enough -- writing to it writes the source.
        card = self.root / "card.ps2"
        card.write_bytes(b"\x00" * save_lib.MEMCARD_PAGE)
        link = self.root / "hard.ps2"
        try:
            os.link(card, link)
        except (OSError, NotImplementedError):  # pragma: no cover
            self.skipTest("this filesystem does not support hard links")
        with self.assertRaisesRegex(save_lib.SaveError, "Refusing to write over"):
            save_lib.write_into_memcard(card, self.save, link)

    def test_a_non_memcard_image_is_refused(self) -> None:
        card = self.root / "notacard.ps2"
        card.write_bytes(b"\x00" * (save_lib.MEMCARD_PAGE * 4))
        with self.assertRaises(save_lib.SaveError):
            save_lib.write_into_memcard(card, self.save, self.root / "out.ps2")


class ServiceVerifiesTheFileTests(unittest.TestCase):
    """A write must be checked against disk, not against the editor's memory."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-verify-")
        self.root = Path(self._temp.name)
        save_lib.write_psu(save_lib._synthetic_save(), self.root / "source.psu")
        self.service = Ps2SaveService()
        self.service.open(self.root / "source.psu")
        self.service.set_name(0, "first", "Delta")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_an_honest_write_verifies(self) -> None:
        self.assertTrue(self.service.write(self.root / "good.psu").verified)

    def test_a_write_that_lands_wrong_on_disk_is_caught(self) -> None:
        # Verifying the in-memory save would only prove the editor agrees
        # with itself; this proves the file itself is re-read.
        import mod_editor.core.ps2_save_service as service_module

        real = service_module.save_lib.write_psu
        service_module.save_lib.write_psu = lambda save, path: path.write_bytes(b"\x00" * 16)
        try:
            result = self.service.write(self.root / "bad.psu")
        finally:
            service_module.save_lib.write_psu = real
        self.assertFalse(result.verified)
        self.assertIn("verification failed", result.detail)
        self.assertFalse((self.root / "bad.psu").exists())
        self.assertTrue(self.service.write(self.root / "bad.psu").verified)

    def test_a_destination_claimed_during_verification_survives(self) -> None:
        output = self.root / "claimed.psu"
        def create_other_file(stage):
            if "Verifying" in stage:
                output.write_bytes(b"another export")
        with self.assertRaisesRegex(ValidationError, "output appeared|existing file"):
            self.service.write(output, create_other_file)
        self.assertEqual(output.read_bytes(), b"another export")
        self.assertTrue(self.service.dirty)

    def test_the_write_announces_each_stage_it_reaches(self) -> None:
        # The GUI has nothing else to show during a multi-second card write.
        stages: list[str] = []
        self.service.write(self.root / "announced.psu", stages.append)
        self.assertEqual(len(stages), 2, stages)
        self.assertIn("Writing", stages[0])
        self.assertIn("Verifying", stages[1])

    def test_progress_is_optional(self) -> None:
        # The command-line path passes nothing and must not be made to care.
        self.assertTrue(self.service.write(self.root / "quiet.psu").verified)


class _BlockingHost:
    """A host whose write parks until the test releases it.

    Blocking on an event rather than on real work makes the concurrency
    deterministic: the test can inspect the dialog at a moment when the write
    is provably still running.
    """

    is_open = True
    dirty = True
    edit_count = 1
    opened_from_card = False

    def __init__(self) -> None:
        self.released = threading.Event()
        self.entered = threading.Event()
        self.write_thread: str | None = None

    def open(self, path: Path, directory: str | None = None) -> object:
        return None

    def summary(self) -> object:
        return SimpleNamespace(directory="BASLUS-209192K5Roster")

    def players(self) -> list:
        return []

    def validate_name(self, index: int, field: str, value: str) -> str | None:
        return None

    def set_name(self, index: int, field: str, value: str) -> None:
        return None

    def revert(self) -> object:
        return None

    def write(self, output: Path, progress=None) -> object:
        self.write_thread = threading.current_thread().name
        if progress is not None:
            progress("Writing the memory-card image…")
        self.entered.set()
        if not self.released.wait(20):  # pragma: no cover - test would hang
            raise AssertionError("the test never released the write")
        return SimpleNamespace(verified=True, detail="Wrote 1 change.", output=output)


def _qt_application():
    """A shared offscreen QApplication, or None if Qt cannot start one."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception:  # pragma: no cover - PyQt5 is a hard dependency here
        return None
    return QApplication.instance() or QApplication([])


class WriteIsAsynchronousTests(unittest.TestCase):
    """A card write must not hold the Qt thread.

    Writing an 8 MB card and verifying every page's ECC takes seconds. Run in
    the click handler it stopped the event loop for the whole duration and the
    window was marked unresponsive, so the write belongs on a pool thread.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qt_application()
        if cls.app is None:  # pragma: no cover - environment guard
            raise unittest.SkipTest("no QApplication is available")

    def setUp(self) -> None:
        import mod_editor.gui.ps2_save_dialog_qt as dialog_module

        self.dialog_module = dialog_module
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-async-")
        self.output = Path(self._temp.name) / "written.psu"
        self.host = _BlockingHost()
        self.dialog = dialog_module.Ps2SaveEditorDialog(host=self.host)
        self._real_picker = dialog_module.QFileDialog.getSaveFileName
        self._real_info = dialog_module.QMessageBox.information
        self._real_warning = dialog_module.QMessageBox.warning
        dialog_module.QFileDialog.getSaveFileName = staticmethod(
            lambda *args, **kwargs: (str(self.output), "PS2 save file (*.psu)")
        )
        dialog_module.QMessageBox.information = staticmethod(
            lambda *args, **kwargs: None
        )

    def tearDown(self) -> None:
        self.host.released.set()
        self._settle()
        self.dialog_module.QFileDialog.getSaveFileName = self._real_picker
        self.dialog_module.QMessageBox.information = self._real_info
        self.dialog_module.QMessageBox.warning = self._real_warning
        self.dialog.deleteLater()
        self._temp.cleanup()

    def _settle(self, timeout: float = 20.0) -> None:
        """Pump the event loop until the write reports itself finished."""
        deadline = time.monotonic() + timeout
        while self.dialog._busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def test_the_click_handler_returns_while_the_write_is_still_running(self) -> None:
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10), "the write never started")
        self.assertTrue(self.dialog._busy, "the handler waited for the write")
        self.assertTrue(self.dialog.progress_bar.isVisibleTo(self.dialog))

    def test_nothing_that_touches_the_save_stays_live_during_a_write(self) -> None:
        # The worker owns the host for the duration; the Qt thread must not be
        # able to open another save or stage another edit underneath it.
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        for name in (
            "open_file_button", "open_folder_button", "first_edit",
            "last_edit", "table", "search", "apply_button", "write_button",
        ):
            self.assertFalse(
                getattr(self.dialog, name).isEnabled(), f"{name} stayed live"
            )

    def test_the_write_runs_on_a_worker_thread(self) -> None:
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        self.assertIsNotNone(self.host.write_thread)
        self.assertNotEqual(self.host.write_thread, threading.main_thread().name)

    def test_the_stage_message_reaches_the_status_line(self) -> None:
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        deadline = time.monotonic() + 5
        while "memory-card" not in self.dialog.status_label.text():
            if time.monotonic() > deadline:  # pragma: no cover - timing guard
                break
            self.app.processEvents()
            time.sleep(0.01)
        self.assertIn("memory-card", self.dialog.status_label.text())

    def test_closing_is_refused_while_a_write_is_in_flight(self) -> None:
        rejections = []
        self.dialog.rejected.connect(lambda: rejections.append(True))
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        self.dialog.reject()
        self.app.processEvents()
        self.assertEqual(rejections, [], "the dialog closed during a write")
        self.assertTrue(self.dialog._busy)

    def test_a_second_write_cannot_be_started_while_one_runs(self) -> None:
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        self.host.entered.clear()
        self.dialog._write_save()
        self.assertFalse(
            self.host.entered.wait(0.3), "a second write started concurrently"
        )

    def test_the_dialog_settles_once_the_write_returns(self) -> None:
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        self.host.released.set()
        self._settle()
        self.assertFalse(self.dialog._busy)
        self.assertFalse(self.dialog.progress_bar.isVisibleTo(self.dialog))
        self.assertIsNone(self.dialog._write_task)
        self.assertIn("Wrote 1 change.", self.dialog.status_label.text())

    def test_the_dialog_has_settled_before_the_report_is_shown(self) -> None:
        # A modal raised while the progress bar still spins would ask the user
        # to answer a window that claims to be working.
        # Recorded as a list, not a dict: a second report would otherwise
        # overwrite the first and hide a premature one.
        seen = []
        self.dialog_module.QMessageBox.information = staticmethod(
            lambda *args, **kwargs: seen.append(
                {
                    "busy": self.dialog._busy,
                    "spinning": self.dialog.progress_bar.isVisibleTo(self.dialog),
                }
            )
        )
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        self.host.released.set()
        self._settle()
        self.assertEqual(seen, [{"busy": False, "spinning": False}])

    def test_a_failed_write_is_reported_and_the_dialog_recovers(self) -> None:
        boom = _BlockingHost()

        def explode(output, progress=None):
            raise RuntimeError("the card is write protected")

        boom.write = explode
        dialog = self.dialog_module.Ps2SaveEditorDialog(host=boom)
        warnings = []
        self.dialog_module.QMessageBox.warning = staticmethod(
            lambda *args, **kwargs: warnings.append(args[2])
        )
        try:
            dialog._write_save()
            deadline = time.monotonic() + 10
            while dialog._busy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
            self.app.processEvents()
        finally:
            dialog.deleteLater()
        self.assertFalse(dialog._busy, "a failed write left the dialog busy")
        self.assertFalse(dialog.progress_bar.isVisibleTo(dialog))
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("the card is write protected"))
        self.assertIn("try again", warnings[0])
        self.assertNotIn("RuntimeError:", warnings[0])
        self.assertIn("write protected", dialog.status_label.text())

    def test_closing_is_allowed_again_once_the_write_finishes(self) -> None:
        rejections = []
        self.dialog.rejected.connect(lambda: rejections.append(True))
        self.dialog._write_save()
        self.assertTrue(self.host.entered.wait(10))
        self.host.released.set()
        self._settle()
        self.dialog.reject()
        self.app.processEvents()
        self.assertEqual(rejections, [True])


if __name__ == "__main__":
    unittest.main()
