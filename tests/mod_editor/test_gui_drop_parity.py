"""Drop parity: every Import/Replace surface accepts a dropped image exactly
the way its file dialog does.

A modder who drags a JPEG onto a panel must get the same automatic fit as one
who uses the Replace button -- any size, any ordinary format, converted to the
slot's exact pixels before staging.  Drops that cannot be used (several files,
links, non-images) are refused with a plain explanation instead of bouncing
silently.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt5.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PyQt5.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.apf_studio import gui  # noqa: E402
from mod_editor.apf_studio.catalog import ApfCatalog  # noqa: E402
from mod_editor.apf_studio.gui import (  # noqa: E402
    ApfTextLogoPanel,
    UniformStudioPage,
)
from mod_editor.apf_studio.models import (  # noqa: E402
    ApfAsset,
    ApfCategory,
    ApfStatus,
    ASSET_ACTION_BINDINGS,
    Modification,
    UniformAsset,
)
from mod_editor.gui.crib_panel_qt import (  # noqa: E402
    CallbackCribPanelHost,
    CribPanel,
    CribPanelCallbacks,
)
from mod_editor.core.nfl2k5_crib import load_nfl2k5_crib_catalog  # noqa: E402


# One shared application for every class in this file: recreating the
# QApplication between classes is unreliable on the offscreen platform.
_APPLICATION = QApplication.instance() or QApplication([])


def _write_jpeg(path: Path, width: int, height: int) -> Path:
    Image.new("RGB", (width, height), (200, 40, 90)).save(path, "JPEG")
    return path


def _write_webp(path: Path, width: int, height: int) -> Path:
    Image.new("RGBA", (width, height), (10, 190, 240, 255)).save(path, "WEBP")
    return path


def _drop(widget, path: Path) -> QDropEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    enter = QDragEnterEvent(
        QPoint(8, 8), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
    )
    QApplication.sendEvent(widget, enter)
    assert enter.isAccepted(), "the drop target must admit an ordinary image drag"
    dropped = QDropEvent(
        QPointF(8, 8), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
    )
    QApplication.sendEvent(widget, dropped)
    return dropped


class _RecordingRunner:
    """Synchronous task runner: operations execute immediately."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def __call__(
        self,
        label: str,
        operation: object,
        on_success: object = None,
        blocking: bool = True,
    ) -> bool:
        self.calls.append((label, operation))
        try:
            result = operation(lambda *_args: None)  # type: ignore[operator]
        except Exception:
            return True
        if on_success is not None:
            on_success(result)  # type: ignore[operator]
        return True


class UniformDropParityTests(unittest.TestCase):
    """APF uniform slots: a dropped JPEG is fitted exactly like the dialog."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _APPLICATION

    def _facade(self):
        asset = UniformAsset(
            family="jersey",
            asset_index=3,
            asset_id="apf:uniform:jersey:03",
            title="Jersey 03",
            width=1024,
            height=1024,
            png_contract="Synthetic jersey contract.",
            status=ApfStatus.EDITABLE,
            outer_index=103,
            inner_index=0,
            affected_teams=("Synthetic Team",),
        )

        class _Facade:
            source_ready = True
            source = SimpleNamespace(source_sha256="c" * 64)
            modified_asset_ids: frozenset = frozenset()
            replace_calls: list = []

            def uniform_assets(self, family=None):
                values = (asset,)
                return values if family in (None, "jersey") else ()

            def browse_assets(self, **_kwargs):
                return ()

            def require_catalog(self):
                return SimpleNamespace(assets=())

            def capability_cards(self, _category):
                return ()

            def replace_uniform(self, asset_id, supplied_png, progress):
                progress("Synthetic uniform replacement", 1, 1)
                self.replace_calls.append((asset_id, Path(supplied_png)))
                return SimpleNamespace(asset_id=asset_id)

        return _Facade()

    def test_dropped_off_size_jpeg_is_fitted_before_the_writer(self) -> None:
        facade = self._facade()
        runner = _RecordingRunner()
        page = UniformStudioPage(facade, runner)  # type: ignore[arg-type]
        try:
            page.set_context()
            self.application.processEvents()
            page.list.setCurrentRow(0)
            self.application.processEvents()
            self.assertTrue(page.preview.acceptDrops())

            with tempfile.TemporaryDirectory() as directory:
                source = _write_jpeg(Path(directory) / "drop.jpg", 640, 480)
                original = source.read_bytes()
                with mock.patch.object(
                    gui.QInputDialog,
                    "getItem",
                    return_value=("Cover — fill the slot, crop overflow", True),
                ), mock.patch.object(gui.QMessageBox, "information"):
                    dropped = _drop(page.preview, source)
                self.application.processEvents()

                self.assertTrue(dropped.isAccepted())
                self.assertEqual(len(facade.replace_calls), 1)
                asset_id, supplied = facade.replace_calls[0]
                self.assertEqual(asset_id, "apf:uniform:jersey:03")
                self.assertNotEqual(supplied, source)
                with Image.open(supplied) as fitted:
                    self.assertEqual(fitted.size, (1024, 1024))
                    self.assertEqual(fitted.mode, "RGBA")
                    self.assertEqual(fitted.format, "PNG")
                self.assertEqual(source.read_bytes(), original)
        finally:
            page.deleteLater()
            self.application.processEvents()


class WordmarkDropParityTests(unittest.TestCase):
    """APF wordmarks: a dropped WebP enters the same prepare/preview route."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _APPLICATION

    def _facade(self):
        class _Session:
            def __init__(self):
                self.rows = {}

            def modification(self, asset_id):
                return self.rows.get(asset_id)

        class _Facade:
            source_ready = True
            source = SimpleNamespace(source_sha256="b" * 64, index_0a=Path("/game/0A"))
            modified_asset_ids: frozenset = frozenset()
            replace_calls: list = []

            def __init__(self):
                self.session = _Session()
                self.assets = tuple(
                    UniformAsset(
                        family="textlogo",
                        asset_index=index,
                        asset_id=f"apf:uniform:textlogo:{index:02d}",
                        title=f"Wordmark {index:03d}",
                        width=512,
                        height=128,
                        png_contract="Synthetic wordmark contract.",
                        status=ApfStatus.EDITABLE,
                        outer_index=500 + index,
                        inner_index=0,
                        affected_teams=(),
                    )
                    for index in range(206)
                )

            def uniform_assets(self, family=None):
                return self.assets if family in (None, "textlogo") else ()

            def require_session(self):
                return self.session

            def preview_uniform(self, asset_id, _progress):
                return Path(f"/private/{asset_id}.png")

            def replace_uniform(self, asset_id, supplied_png, progress):
                progress("Synthetic wordmark staging", 1, 1)
                self.replace_calls.append((asset_id, Path(supplied_png)))
                return SimpleNamespace(asset_id=asset_id)

        return _Facade()

    def test_dropped_webp_previews_then_stages_the_exact_wordmark(self) -> None:
        facade = self._facade()
        runner = _RecordingRunner()
        panel = ApfTextLogoPanel(facade, runner)  # type: ignore[arg-type]
        try:
            panel.slot.setValue(12)
            self.application.processEvents()
            self.assertTrue(panel.preview.acceptDrops())
            with tempfile.TemporaryDirectory() as directory:
                source = _write_webp(Path(directory) / "drop.webp", 300, 300)
                with mock.patch.object(
                    gui, "confirm_prepared_slot_image", return_value=True
                ) as preview, mock.patch.object(
                    gui.QMessageBox, "information"
                ):
                    dropped = _drop(panel.preview, source)
                self.application.processEvents()
            self.assertTrue(dropped.isAccepted())
            # The preview showed the exact fitted pixels before staging...
            preview.assert_called_once()
            previewed = Path(preview.call_args.args[1])
            with Image.open(previewed) as shown:
                self.assertEqual(shown.size, (512, 128))
                self.assertEqual(shown.mode, "RGBA")
            # ...and staging used exactly those pixels.
            self.assertEqual(len(facade.replace_calls), 1)
            self.assertEqual(facade.replace_calls[0][0],
                             "apf:uniform:textlogo:12")
            self.assertEqual(facade.replace_calls[0][1], previewed)
        finally:
            panel.deleteLater()
            self.application.processEvents()


def _pump_pool_idle(application: QApplication, panel: CribPanel, *, timeout_s: float = 10.0) -> None:
    """Drain QThreadPool work and queued finished/result slots.

    waitForDone alone is not enough: worker signals are QueuedConnection to the
    GUI thread, so _busy stays True until processEvents runs the finished slot.
    Offscreen QInputDialog also must be mocked by callers — never left open.
    """
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        panel._pool.waitForDone(50)
        application.processEvents()
        if panel._pool.activeThreadCount() == 0 and not panel._busy:
            application.processEvents()
            if not panel._busy:
                return
        time.sleep(0.01)
    raise AssertionError(
        f"Crib panel still busy after {timeout_s:.1f}s "
        f"(active={panel._pool.activeThreadCount()}, busy={panel._busy})"
    )


class CribDropParityTests(unittest.TestCase):
    """2K5 Crib: a dropped off-size JPEG becomes the slot's exact PNG."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _APPLICATION
        cls.catalog = load_nfl2k5_crib_catalog()

    def test_dropped_jpeg_is_fitted_to_the_crib_slot(self) -> None:
        replacements: list = []
        with tempfile.TemporaryDirectory() as preview_dir:
            preview_png = Path(preview_dir) / "crib-preview.png"
            Image.new("RGB", (8, 8), (5, 5, 5)).save(preview_png)
            host = CallbackCribPanelHost(CribPanelCallbacks(
                list_assets=lambda: self.catalog.assets,
                is_source_ready=lambda: True,
                modified_ids=lambda: (),
                preview=lambda _asset_id, _sink: preview_png,
                export=lambda _asset_id, destination, _sink: destination,
                replace=lambda asset_id, supplied, _sink: replacements.append(
                    (asset_id, Path(supplied))
                ),
                revert=lambda _asset_id, _sink: None,
            ))
            panel = CribPanel(host)
            try:
                # Drain the construction-time preview task so the replace lane
                # is free when the drop arrives.
                _pump_pool_idle(self.application, panel)
                panel.table.selectRow(0)
                _pump_pool_idle(self.application, panel)
                self.assertTrue(panel.preview._accepting)
                selected = panel._selected_asset()
                self.assertIsNotNone(selected)

                with tempfile.TemporaryDirectory() as directory:
                    source = _write_jpeg(Path(directory) / "crib.jpg", 200, 300)
                    original = source.read_bytes()
                    # Off-size JPEG → Contain/Cover/Stretch chooser (same path
                    # as the Replace dialog). Must mock getItem or offscreen
                    # hangs forever on the modal QInputDialog.
                    with mock.patch(
                        "mod_editor.gui.crib_panel_qt.QInputDialog.getItem",
                        return_value=(
                            "Cover — fill the slot, crop overflow",
                            True,
                        ),
                    ), mock.patch(
                        "mod_editor.gui.crib_panel_qt.QMessageBox.information"
                    ), mock.patch(
                        "mod_editor.gui.crib_panel_qt.QMessageBox.warning"
                    ):
                        dropped = _drop(panel.preview, source)
                    self.assertTrue(dropped.isAccepted())
                    _pump_pool_idle(self.application, panel)

                    self.assertEqual(len(replacements), 1)
                    asset_id, supplied = replacements[0]
                    self.assertEqual(asset_id, selected.asset_id)
                    self.assertNotEqual(supplied, source)
                    with Image.open(supplied) as fitted:
                        self.assertEqual(fitted.size,
                                         (selected.width, selected.height))
                        self.assertEqual(fitted.format, "PNG")
                    self.assertEqual(source.read_bytes(), original)
            finally:
                panel.close()
                panel.deleteLater()
                self.application.processEvents()


class BrowserDraftLogoDropParityTests(unittest.TestCase):
    """APF universal browser: the draft_logo row fits a dropped image too."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _APPLICATION

    def test_browser_replace_route_fits_dropped_image(self) -> None:
        binding = next(
            entry for entry in ASSET_ACTION_BINDINGS
            if entry.replace_method == "replace_draft_logo"
        )

        class _Facade:
            source_ready = False
            modified_asset_ids: frozenset = frozenset()
            replace_calls: list = []

            def replace_draft_logo(self, supplied_png, progress):
                progress("Synthetic draft logo replacement", 1, 1)
                self.replace_calls.append(Path(supplied_png))
                return SimpleNamespace(asset_id=binding.asset_id)

        facade = _Facade()
        browser = gui.AssetBrowser(
            facade,  # type: ignore[arg-type]
            ApfCategory.LOGOS,
            _RecordingRunner(),  # type: ignore[arg-type]
        )
        try:
            browser.preview.setAcceptDrops(True)
            asset = ApfAsset(
                asset_id=binding.asset_id,
                outer_index=binding.outer_index,
                inner_index=binding.inner_index,
                name=binding.name,
                type_name=binding.type_name,
                asset_class="texture",
                category=ApfCategory.LOGOS,
                status=ApfStatus.EDITABLE,
                decoded_size=32_768,
                outer_size=33_000,
                part_count=2,
            )
            with tempfile.TemporaryDirectory() as directory:
                source = _write_jpeg(Path(directory) / "draft.jpg", 500, 400)
                with mock.patch.object(
                    gui, "_asset_product_action", return_value=binding
                ), mock.patch.object(
                    browser, "_selected_asset", return_value=asset
                ), mock.patch.object(
                    gui.QInputDialog,
                    "getItem",
                    return_value=("Cover — fill the slot, crop overflow", True),
                ), mock.patch.object(
                    # Explicit mode="contain" on draft_logo still confirms via question.
                    gui.QMessageBox, "question", return_value=QMessageBox.Yes
                ), mock.patch.object(gui.QMessageBox, "information"):
                    browser._replace_from_drop(source)
            self.assertEqual(len(facade.replace_calls), 1)
            with Image.open(facade.replace_calls[0]) as fitted:
                self.assertEqual(fitted.size, (128, 128))
                self.assertEqual(fitted.format, "PNG")
        finally:
            browser.deleteLater()
            self.application.processEvents()


class FriendlyDropRefusalTests(unittest.TestCase):
    """Links, multi-file drops and non-images are refused with guidance."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _APPLICATION

    def _label(self) -> gui.ImageDropLabel:
        label = gui.ImageDropLabel("preview")
        label.setAcceptDrops(True)
        label.resize(320, 240)
        return label

    def test_multiple_files_are_refused_with_a_plain_fix(self) -> None:
        label = self._label()
        try:
            with tempfile.TemporaryDirectory() as directory:
                first = _write_jpeg(Path(directory) / "a.jpg", 64, 64)
                second = _write_jpeg(Path(directory) / "b.jpg", 64, 64)
                mime = QMimeData()
                mime.setUrls([
                    QUrl.fromLocalFile(str(first)),
                    QUrl.fromLocalFile(str(second)),
                ])
                enter = QDragEnterEvent(
                    QPoint(4, 4), Qt.CopyAction, mime, Qt.LeftButton,
                    Qt.NoModifier,
                )
                with mock.patch.object(
                    gui.QMessageBox, "information"
                ) as information:
                    QApplication.sendEvent(label, enter)
                    self.assertTrue(enter.isAccepted())
                    dropped = QDropEvent(
                        QPointF(4, 4), Qt.CopyAction, mime, Qt.LeftButton,
                        Qt.NoModifier,
                    )
                    QApplication.sendEvent(label, dropped)
                self.assertFalse(dropped.isAccepted())
                self.assertEqual(
                    information.call_args.args[1], "That drop can't be used yet"
                )
                self.assertIn(
                    "one file at a time", information.call_args.args[2]
                )
        finally:
            label.deleteLater()
            self.application.processEvents()

    def test_a_dropped_link_is_refused_with_a_plain_fix(self) -> None:
        label = self._label()
        try:
            mime = QMimeData()
            mime.setUrls([QUrl("https://example.invalid/logo.png")])
            enter = QDragEnterEvent(
                QPoint(4, 4), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
            )
            with mock.patch.object(
                gui.QMessageBox, "information"
            ) as information:
                QApplication.sendEvent(label, enter)
                self.assertTrue(enter.isAccepted())
                dropped = QDropEvent(
                    QPointF(4, 4), Qt.CopyAction, mime, Qt.LeftButton,
                    Qt.NoModifier,
                )
                QApplication.sendEvent(label, dropped)
            self.assertFalse(dropped.isAccepted())
            self.assertIn("link or a web address",
                          information.call_args.args[2])
            self.assertIn("drop the real file", information.call_args.args[2])
        finally:
            label.deleteLater()
            self.application.processEvents()

    def test_a_non_image_file_is_refused_with_a_plain_fix(self) -> None:
        label = self._label()
        try:
            with tempfile.TemporaryDirectory() as directory:
                notes = Path(directory) / "notes.txt"
                notes.write_text("not an image", encoding="utf-8")
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(str(notes))])
                enter = QDragEnterEvent(
                    QPoint(4, 4), Qt.CopyAction, mime, Qt.LeftButton,
                    Qt.NoModifier,
                )
                with mock.patch.object(
                    gui.QMessageBox, "information"
                ) as information:
                    QApplication.sendEvent(label, enter)
                    dropped = QDropEvent(
                        QPointF(4, 4), Qt.CopyAction, mime, Qt.LeftButton,
                        Qt.NoModifier,
                    )
                    QApplication.sendEvent(label, dropped)
                self.assertFalse(dropped.isAccepted())
                self.assertIn("not an image", information.call_args.args[2])
                self.assertIn("resizes it for you",
                              information.call_args.args[2])
        finally:
            label.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
