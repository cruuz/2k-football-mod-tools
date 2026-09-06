"""Service, view-model and dialog tests for the PS2 disc inventory window.

The service tests run the whole open-filter-join-export path over the
inventory tool's synthetic two-pack disc, so no game data is required.  The
dialog's Qt-free view model is tested without a display; the dialog itself is
exercised against an offscreen QApplication and skipped where PyQt5 is absent.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.ps2_disc_service import (  # noqa: E402
    EXPORT_COLUMNS,
    PRESENCE_BOTH,
    PRESENCE_PS2_ONLY,
    PRESENCE_UNKNOWN,
    Ps2DiscService,
    RowFilter,
)

import nfl2k5_ps2_disc_inventory as inventory_lib  # noqa: E402

try:
    import mod_editor.gui.ps2_disc_dialog_qt as dialog_module
except ImportError:  # PyQt5 is not installed here
    dialog_module = None


def _write_synthetic_disc(directory: Path) -> tuple[Path, dict]:
    image, expected = inventory_lib._build_synthetic_disc()
    path = directory / "selftest_slus_20919.iso"
    path.write_bytes(image)
    return path, expected


def _write_xbox_inventory(directory: Path, names: list[str]) -> Path:
    path = directory / "xbox_names.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["name", "fourcc", "format", "width", "height"])
        for name in names:
            writer.writerow([name, "TXTR", "P8", "64", "64"])
    return path


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="ps2-disc-service-")
        cls.root = Path(cls._temp.name)
        cls.iso, cls.expected = _write_synthetic_disc(cls.root)
        cls.report, _side = inventory_lib.inventory(str(cls.iso), jobs=1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def setUp(self) -> None:
        self.service = Ps2DiscService(jobs=1)
        self.stages: list[str] = []
        self.service.open(self.iso, self.stages.append)

    def tearDown(self) -> None:
        self.service.close()

    def test_opening_reports_the_identity(self) -> None:
        identity = self.service.identity()
        self.assertEqual(identity.serial, "SLUS-20919")
        self.assertTrue(identity.serial_matches)
        self.assertFalse(identity.retail_boot_elf, "a synthetic ELF is not retail")
        self.assertEqual(identity.boot_sha256, self.expected["boot_sha256"])
        self.assertIn("SLUS-20919", identity.headline)
        self.assertIn("differs from retail", identity.headline)
        self.assertTrue(self.stages and any("entry" in s or "Indexing" in s for s in self.stages))

    def test_the_summary_matches_the_tool_report(self) -> None:
        summary = self.service.summary()
        self.assertEqual(summary.rows, self.report["resources"]["row_count"])
        self.assertEqual(summary.textures, self.report["resources"]["txtr_rows"])
        self.assertEqual(summary.name_keys, self.report["resources"]["distinct_name_keys"])
        self.assertEqual(summary.entries, self.expected["entries"])
        self.assertFalse(summary.xbox_loaded)
        self.assertIn("rows", summary.headline)

    def test_every_row_is_stored_and_counted(self) -> None:
        self.assertEqual(self.service.count(), self.service.summary().rows)
        self.assertEqual(self.service.count(RowFilter(fourcc="TXTR")),
                         sum(1 for row in self._all_rows() if row.fourcc == "TXTR"))
        self.assertEqual(self.service.count(RowFilter(role="tset_texture")), 3)
        self.assertEqual(self.service.count(RowFilter(pack="1")) +
                         self.service.count(RowFilter(pack="0")), self.service.count())

    def _all_rows(self):
        return self.service.rows(RowFilter(), 0, 10_000)

    def test_search_matches_names_case_insensitively_and_entry_numbers(self) -> None:
        names = {row.name for row in self.service.rows(RowFilter(search="tset_"), 0, 50)}
        self.assertEqual(names, {"tset_helmet", "tset_jersey", "tset_pants"})
        entry_rows = self.service.rows(RowFilter(search="5"), 0, 50)
        self.assertTrue(entry_rows and all(row.entry_index == 5 or "5" in row.name_key
                                           for row in entry_rows))

    def test_rows_come_back_in_disc_order_with_geometry(self) -> None:
        first = self.service.rows(RowFilter(), 0, 1)[0]
        self.assertEqual((first.name, first.format, first.dimensions),
                         ("selftest_logo", "PSMT8", "512x256"))
        self.assertEqual(first.role, "chunk")
        window = self.service.rows(RowFilter(), 2, 3)
        self.assertEqual(len(window), 3)

    def test_distinct_values_feed_the_filter_combos(self) -> None:
        self.assertEqual(self.service.distinct("pack"), ["0", "1"])
        self.assertIn("TSET", self.service.distinct("fourcc"))
        self.assertIn("scne_material", self.service.distinct("role"))
        with self.assertRaises(ValidationError):
            self.service.distinct("name")

    def test_presence_is_unknown_until_an_xbox_inventory_is_loaded(self) -> None:
        named = sum(1 for row in self._all_rows() if row.name_key)
        self.assertEqual(self.service.count(RowFilter(presence=PRESENCE_UNKNOWN)), named)
        self.assertEqual(self.service.count(RowFilter(presence=PRESENCE_BOTH)), 0)

    def test_loading_xbox_names_marks_each_row(self) -> None:
        xbox = _write_xbox_inventory(self.root, ["selftest_logo", "TSET_HELMET", "xbox_only"])
        summary = self.service.load_xbox_inventory(xbox)
        self.assertTrue(summary.xbox_loaded)
        self.assertEqual((summary.shared, summary.xbox_only), (2, 1))
        both = {row.name for row in self.service.rows(RowFilter(presence=PRESENCE_BOTH), 0, 50)}
        self.assertEqual(both, {"selftest_logo", "tset_helmet"})
        self.assertEqual(self.service.count(RowFilter(presence=PRESENCE_UNKNOWN)), 0)
        self.assertGreater(self.service.count(RowFilter(presence=PRESENCE_PS2_ONLY)), 0)
        self.assertIn("Xbox:", summary.headline)
        self.assertEqual(self.service.report()["name_join"]["shared"], 2)

    def test_an_invalid_presence_filter_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.count(RowFilter(presence="maybe"))

    def test_export_csv_writes_the_filtered_rows_and_never_overwrites(self) -> None:
        output = self.root / "rows.csv"
        if output.exists():
            output.unlink()
        written = self.service.export_csv(output, RowFilter(fourcc="TXTR"))
        with output.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], list(EXPORT_COLUMNS))
        self.assertEqual(len(rows) - 1, written)
        self.assertEqual(written, self.service.count(RowFilter(fourcc="TXTR")))
        with self.assertRaisesRegex(ValidationError, "Refusing to overwrite"):
            self.service.export_csv(output)
        output.unlink()

    def test_export_report_is_the_tool_report(self) -> None:
        output = self.root / "report.json"
        if output.exists():
            output.unlink()
        self.service.export_report(output)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], inventory_lib.SCHEMA)
        self.assertEqual(report["image"]["name"], self.iso.name)
        with self.assertRaisesRegex(ValidationError, "Refusing to overwrite"):
            self.service.export_report(output)
        output.unlink()

    def test_no_output_carries_the_payload_sentinel(self) -> None:
        output = self.root / "all.csv"
        if output.exists():
            output.unlink()
        self.service.export_csv(output)
        self.assertNotIn(inventory_lib.PAYLOAD_SENTINEL, output.read_bytes())
        output.unlink()

    def test_the_disc_image_is_never_modified(self) -> None:
        before = self.iso.stat()
        self.service.close()
        self.service.open(self.iso)
        after = self.iso.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))

    def test_close_removes_the_private_sidecar(self) -> None:
        workspace = self.service._workspace
        self.assertIsNotNone(workspace)
        self.assertTrue(Path(workspace).is_dir())
        self.service.close()
        self.assertFalse(Path(workspace).exists())
        self.assertFalse(self.service.is_open)
        with self.assertRaises(ValidationError):
            self.service.count()

    def test_a_disc_without_the_resource_packs_is_refused(self) -> None:
        import ps2_iso9660 as iso_lib

        other = self.root / "not_2k5.iso"
        other.write_bytes(iso_lib.build_synthetic_iso())
        service = Ps2DiscService(jobs=1)
        with self.assertRaisesRegex(ValidationError, "VC_20919"):
            service.open(other)
        self.assertFalse(service.is_open)

    def test_the_service_satisfies_the_dialog_host_protocol(self) -> None:
        if dialog_module is None:
            self.skipTest("PyQt5 is not installed")
        self.assertIsInstance(self.service, dialog_module.Ps2DiscInventoryHost)


@unittest.skipIf(dialog_module is None, "PyQt5 is not installed")
class ViewModelTests(unittest.TestCase):
    def test_nothing_but_open_is_offered_before_a_disc_is_open(self) -> None:
        state = dialog_module.ps2_disc_action_state(disc_open=False, busy=False, row_count=0)
        self.assertTrue(state.can_open)
        self.assertFalse(state.can_load_xbox or state.can_filter
                         or state.can_export_rows or state.can_export_report)

    def test_a_busy_dialog_offers_nothing(self) -> None:
        state = dialog_module.ps2_disc_action_state(disc_open=True, busy=True, row_count=9)
        self.assertEqual(
            (state.can_open, state.can_load_xbox, state.can_filter,
             state.can_export_rows, state.can_export_report),
            (False, False, False, False, False),
        )

    def test_exporting_rows_needs_rows(self) -> None:
        empty = dialog_module.ps2_disc_action_state(disc_open=True, busy=False, row_count=0)
        some = dialog_module.ps2_disc_action_state(disc_open=True, busy=False, row_count=1)
        self.assertFalse(empty.can_export_rows)
        self.assertTrue(empty.can_export_report)
        self.assertTrue(some.can_export_rows)

    def test_presence_labels_and_refusals(self) -> None:
        self.assertEqual(dialog_module.presence_label(PRESENCE_BOTH), "Has an Xbox counterpart")
        with self.assertRaises(ValidationError):
            dialog_module.presence_label("maybe")

    def test_suggested_export_names_derive_from_the_image(self) -> None:
        self.assertEqual(dialog_module.suggested_export_name("ESPN NFL 2K5 (USA).iso", "rows"),
                         "ESPN NFL 2K5 (USA)-inventory.csv")
        self.assertEqual(dialog_module.suggested_export_name("", "report"),
                         "nfl2k5-ps2-inventory.json")
        with self.assertRaises(ValidationError):
            dialog_module.suggested_export_name("x.iso", "pixels")

    def test_the_status_line_says_when_xbox_names_are_missing(self) -> None:
        self.assertIn("load an Xbox inventory",
                      dialog_module.row_status_text(5, 10, xbox_loaded=False))
        self.assertEqual(dialog_module.row_status_text(5, 10, xbox_loaded=True), "5 of 10 rows")


def _qt_application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception:
        return None
    return QApplication.instance() or QApplication([])


@unittest.skipIf(dialog_module is None, "PyQt5 is not installed")
class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qt_application()
        if cls.app is None:  # pragma: no cover - environment guard
            raise unittest.SkipTest("no QApplication is available")
        cls._temp = tempfile.TemporaryDirectory(prefix="ps2-disc-dialog-")
        cls.root = Path(cls._temp.name)
        cls.iso, cls.expected = _write_synthetic_disc(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def _settle(self, dialog, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while dialog._busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(dialog._busy, "the background operation never finished")

    def test_the_dialog_is_a_qt_dialog(self) -> None:
        from PyQt5.QtWidgets import QDialog

        self.assertTrue(dialog_module.PYQT5_AVAILABLE)
        self.assertTrue(issubclass(dialog_module.Ps2DiscInventoryDialog, QDialog))

    def test_opening_off_thread_fills_the_virtualized_table(self) -> None:
        service = Ps2DiscService(jobs=1)
        dialog = dialog_module.Ps2DiscInventoryDialog(host=service)
        try:
            self.assertFalse(dialog.xbox_button.isEnabled())
            dialog._open_path(self.iso)
            self.assertTrue(dialog._busy)
            self.assertFalse(dialog.open_button.isEnabled())
            self._settle(dialog)
            total = service.summary().rows
            self.assertEqual(dialog.model.rowCount(), total)
            self.assertIn("SLUS-20919", dialog.info_label.text())
            self.assertIn(f"{total:,} of {total:,} rows", dialog.status_label.text())
            self.assertTrue(dialog.xbox_button.isEnabled())
            self.assertTrue(dialog.export_rows_button.isEnabled())
            self.assertFalse(dialog.presence_filter.isEnabled())
            self.assertEqual(
                [dialog.pack_filter.itemData(i) for i in range(dialog.pack_filter.count())],
                ["", "0", "1"],
            )
            from PyQt5.QtCore import Qt

            first = dialog.model.data(dialog.model.index(0, 2), Qt.DisplayRole)
            self.assertEqual(first, "selftest_logo")

            dialog.search.setText("tset_")
            dialog._apply_filters()
            self.assertEqual(dialog.model.rowCount(), 3)
            dialog.search.setText("")
            dialog.type_filter.setCurrentIndex(
                dialog.type_filter.findData("TSET")
            )
            self.assertEqual(dialog.model.rowCount(), service.count(RowFilter(fourcc="TSET")))
            dialog.type_filter.setCurrentIndex(0)

            xbox = _write_xbox_inventory(self.root, ["selftest_logo"])
            dialog._load_xbox_path(xbox)
            self._settle(dialog)
            self.assertTrue(dialog.presence_filter.isEnabled())
            dialog.presence_filter.setCurrentIndex(
                dialog.presence_filter.findData(PRESENCE_BOTH)
            )
            self.assertEqual(dialog.model.rowCount(), 1)
            self.assertIn("Xbox:", dialog.info_label.text())
        finally:
            dialog._busy = False
            dialog.done(0)

    def test_closing_is_refused_while_an_operation_runs(self) -> None:
        service = Ps2DiscService(jobs=1)
        dialog = dialog_module.Ps2DiscInventoryDialog(host=service)
        try:
            dialog._busy = True
            dialog._busy_verb = "Inventorying the disc"
            dialog.reject()
            self.assertIn("still running", dialog.status_label.text())
            self.assertEqual(dialog.result(), 0)
        finally:
            dialog._busy = False
            dialog.done(0)

    def test_a_refused_disc_is_reported_not_raised(self) -> None:
        import ps2_iso9660 as iso_lib

        other = self.root / "not_2k5.iso"
        other.write_bytes(iso_lib.build_synthetic_iso())
        service = Ps2DiscService(jobs=1)
        dialog = dialog_module.Ps2DiscInventoryDialog(host=service)
        real_warning = dialog_module.QMessageBox.warning
        warnings: list[str] = []
        dialog_module.QMessageBox.warning = staticmethod(
            lambda *args, **kwargs: warnings.append(str(args[1]))
        )
        try:
            dialog._open_path(other)
            self._settle(dialog)
            self.assertEqual(len(warnings), 1)
            self.assertIn("VC_20919", dialog.status_label.text())
            self.assertFalse(service.is_open)
            self.assertTrue(dialog.open_button.isEnabled())
        finally:
            dialog_module.QMessageBox.warning = real_warning
            dialog._busy = False
            dialog.done(0)


if __name__ == "__main__":
    unittest.main()
