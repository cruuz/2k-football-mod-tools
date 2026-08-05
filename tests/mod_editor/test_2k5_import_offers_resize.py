"""Every image import path must offer to resize, not just one of them.

A modder reported: "images don't resize when you try to import either via dialog
or drag and drop, still gives the warning. I did make a tool for myself as a
workaround lol". The resizer existed and worked -- it was simply only wired into
the visual browser. The main component replace path, which is where both the
file dialog and drag-and-drop land for most assets, went straight to the writer
and refused anything off-size.

Writing a separate tool to pre-size PNGs is exactly the work the feature was
supposed to remove, so this pins the wiring rather than the helper: every
function that accepts a user-supplied image for replacement has to consult
``_fit_for_slot`` first.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt5.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PyQt5.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

from mod_editor.gui.studio_qt import (  # noqa: E402
    BrowseOnlyFacade,
    StudioMainWindow,
)

_STUDIO = (
    Path(__file__).resolve().parents[2] / "mod_editor" / "gui" / "studio_qt.py"
)

# Functions that take a caller-supplied image path and hand it to a writer.
IMPORT_PATHS = (
    "_replace_asset",
    "_replace_visual_asset",
    "_replace_stadium_texture",
)


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(_STUDIO.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is no longer defined in studio_qt.py")


def _calls(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            target = inner.func
            if isinstance(target, ast.Attribute):
                names.add(target.attr)
            elif isinstance(target, ast.Name):
                names.add(target.id)
    return names


class ImportPathsOfferResizeTests(unittest.TestCase):
    def test_every_import_path_consults_the_resizer(self) -> None:
        for name in IMPORT_PATHS:
            with self.subTest(path=name):
                self.assertIn(
                    "_fit_for_slot", _calls(_function(name)),
                    f"{name} accepts a user image but never offers to resize it; "
                    "an off-size PNG will be refused instead of fitted",
                )

    def test_the_drop_handlers_reach_a_covered_path(self) -> None:
        """Drag-and-drop must not be a second, unfitted route in."""
        for dropper, expected in (
            ("_replace_from_drop", "_replace_asset"),
            ("_replace_visual_from_drop", "_replace_visual_asset"),
            ("_replace_stadium_texture_drop", "_replace_stadium_texture"),
        ):
            with self.subTest(dropper=dropper):
                self.assertIn(expected, _calls(_function(dropper)))

    def test_dialog_and_drop_share_the_same_fitted_uniform_path(self) -> None:
        """A fix in one entry point must automatically fix the other."""

        chooser = _calls(_function("_choose_replacement"))
        dropper = _calls(_function("_replace_from_drop"))
        replacement = _calls(_function("_replace_asset"))
        self.assertIn("_replace_asset", chooser)
        self.assertIn("_replace_asset", dropper)
        self.assertIn("_fit_for_slot", replacement)

    def test_dialog_and_drop_accept_the_same_common_image_formats(self) -> None:
        source = _STUDIO.read_text(encoding="utf-8")
        self.assertIn("IMAGE_IMPORT_FILTER", source)
        self.assertIn("IMAGE_IMPORT_EXTENSIONS", source)
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            self.assertIn(f'"{suffix}"', source)

    def test_the_resizer_still_asks_before_changing_anything(self) -> None:
        """It must offer, never silently resample what the author supplied."""
        body = ast.get_source_segment(
            _STUDIO.read_text(encoding="utf-8"), _function("_fit_for_slot")
        ) or ""
        self.assertIn("question", body)
        self.assertIn("not modified", body)


class _ResizeFacade(BrowseOnlyFacade):
    """Small active-source backend that records exactly what Qt hands it."""

    def __init__(self) -> None:
        # Keep construction browse-only so the window does not start unrelated
        # source refreshes before the synchronous test hooks are installed.
        self.source_ready = False
        self.source_display_name = "Synthetic NFL 2K5"
        self.source_path = Path("/private/NFL2K5.iso")
        self.source_sha256 = "a" * 64
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.modified_count = 0
        self.can_undo = False
        self.can_launch_xemu = False
        self.received: list[tuple[Path, tuple[int, int]]] = []
        self.authoring_master_calls: list[dict[str, object]] = []

    def replace_asset(
        self, asset: object, supplied_png: Path, progress: object
    ) -> object:
        progress("Reading fitted image", 1, 1)  # type: ignore[operator]
        with Image.open(supplied_png) as image:
            size = image.size
        self.received.append((Path(supplied_png), size))
        return SimpleNamespace(message="Fitted image accepted.")

    def save_texture_authoring_master(
        self, asset: object, **kwargs: object
    ) -> Path:
        self.authoring_master_calls.append({"asset": asset, **kwargs})
        return Path(kwargs["destination"])  # type: ignore[arg-type]


class ResizeOffscreenInteractionTests(unittest.TestCase):
    """Drive both user entry points through real Qt signals and drop events."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="2k5-resize-qt-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "oversize-number.png"
        Image.new("RGBA", (128, 128), (20, 220, 90, 173)).save(self.source)
        self.original_bytes = self.source.read_bytes()

        self.facade = _ResizeFacade()
        self.window = StudioMainWindow(
            facade=self.facade,
            offer_recovery=False,
        )
        self.window._fit_dir = self.root / "fitted"
        self.window._fit_dir.mkdir()
        self.errors: list[str] = []
        self.window._show_error = self.errors.append  # type: ignore[method-assign]
        self.window._mark_workspace_changed = (  # type: ignore[method-assign]
            lambda **_kwargs: None
        )
        self.window._load_preview = lambda _asset: None  # type: ignore[method-assign]
        self.window._load_visual_preview = (  # type: ignore[method-assign]
            lambda _asset, _preview: None
        )

        def immediate(operation: object, success: object, **_kwargs: object) -> None:
            result = operation(lambda *_args: None)  # type: ignore[operator]
            success(result)  # type: ignore[operator]

        self.window._start_task = immediate  # type: ignore[method-assign]
        self.facade.source_ready = True
        self.asset = self.window.uniform_catalog.get_asset(
            "nfl2k5.uniform.18h0.digit.arm.0"
        )
        self.assertEqual((self.asset.width, self.asset.height), (64, 64))
        self.window._selected_asset = self.asset
        self.window.replace_button.setEnabled(True)
        self.window.preview.set_replacement_enabled(True)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
        self.temporary.cleanup()

    def _assert_fitted_import(self) -> None:
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.facade.received), 1)
        fitted, size = self.facade.received[0]
        self.assertNotEqual(fitted, self.source)
        self.assertTrue(fitted.is_file())
        self.assertEqual(size, (64, 64))
        self.assertEqual(self.source.read_bytes(), self.original_bytes)
        with Image.open(self.source) as original:
            self.assertEqual(original.size, (128, 128))

    def test_file_dialog_accepts_resize_and_passes_fitted_png_to_backend(self) -> None:
        with (
            patch(
                "mod_editor.gui.studio_qt.QFileDialog.getOpenFileName",
                return_value=(str(self.source), "PNG image (*.png)"),
            ),
            patch(
                "mod_editor.gui.studio_qt.QMessageBox.question",
                return_value=QMessageBox.Yes,
            ) as question,
        ):
            QTest.mouseClick(self.window.replace_button, Qt.LeftButton)
            self.application.processEvents()

        question.assert_called_once()
        self._assert_fitted_import()

    def test_exact_size_jpeg_and_rgb_png_are_converted_to_rgba_png(self) -> None:
        for name, format_name in (("exact.jpg", "JPEG"), ("rgb.png", "PNG")):
            with self.subTest(format=format_name):
                source = self.root / name
                Image.new("RGB", (64, 64), (30, 70, 120)).save(
                    source, format=format_name
                )
                original = source.read_bytes()
                with patch(
                    "mod_editor.gui.studio_qt.QMessageBox.question",
                    return_value=QMessageBox.Yes,
                ):
                    fitted = self.window._fit_for_slot(
                        source, 64, 64, "exact-size test"
                    )
                self.assertIsNotNone(fitted)
                assert fitted is not None
                self.assertNotEqual(fitted, source)
                self.assertEqual(fitted.suffix, ".png")
                with Image.open(fitted) as converted:
                    self.assertEqual(converted.format, "PNG")
                    self.assertEqual(converted.mode, "RGBA")
                    self.assertEqual(converted.size, (64, 64))
                self.assertEqual(source.read_bytes(), original)

    def test_drag_drop_accepts_resize_and_passes_fitted_png_to_backend(self) -> None:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.source))])
        enter = QDragEnterEvent(
            QPoint(8, 8), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        dropped = QDropEvent(
            QPointF(8, 8), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )

        with patch(
            "mod_editor.gui.studio_qt.QMessageBox.question",
            return_value=QMessageBox.Yes,
        ) as question:
            QApplication.sendEvent(self.window.preview, enter)
            self.assertTrue(enter.isAccepted())
            QApplication.sendEvent(self.window.preview, dropped)
            self.application.processEvents()

        self.assertTrue(dropped.isAccepted())
        question.assert_called_once()
        self._assert_fitted_import()

    def test_extended_visual_import_can_save_exact_non_overwriting_master(self) -> None:
        asset = self.window.extended_visual_catalog.get_asset(
            "nfl2k5.portrait.0000"
        )
        state = next(
            candidate
            for candidate in self.window._visual_browsers.values()
            if any(row.asset_id == asset.asset_id for row in candidate.assets)
        )
        state.selected_asset_id = asset.asset_id
        self.window._selected_asset = asset
        original = self.root / "full-resolution-portrait.png"
        Image.new("RGBA", (320, 160), (91, 17, 230, 197)).save(
            original, compress_level=1
        )
        original_bytes = original.read_bytes()

        with patch(
            "mod_editor.gui.studio_qt.QMessageBox.question",
            return_value=QMessageBox.Yes,
        ):
            self.window._replace_visual_asset(state, asset, original)
        self.application.processEvents()

        draft = self.window._texture_master_drafts[asset.asset_id]
        self.assertNotEqual(draft.source_image, original)
        self.assertEqual(draft.source_image.read_bytes(), original_bytes)
        self.assertEqual(draft.editor_transform["action"], "cropped")
        self.assertEqual(draft.editor_transform["resample"], "lanczos")
        self.window._refresh_visual_action_states(state)
        self.assertTrue(state.master_button.isEnabled())

        destination = self.root / "portrait.2ktexmaster"
        with (
            patch.object(
                QInputDialog,
                "getItem",
                return_value=("4× (recommended)", True),
            ),
            patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(destination), "2K texture authoring master"),
            ),
        ):
            self.window._save_visual_authoring_master(state.category)
        self.application.processEvents()

        self.assertEqual(len(self.facade.authoring_master_calls), 1)
        call = self.facade.authoring_master_calls[0]
        self.assertIs(call["asset"], asset)
        self.assertEqual(call["source_image"], draft.source_image)
        self.assertEqual(call["source_sha256"], draft.source_sha256)
        self.assertEqual(call["destination"], destination)
        self.assertEqual(call["high_resolution_scale"], 4)
        self.assertEqual(original.read_bytes(), original_bytes)

        # Native-canvas painting keeps the exact original and adds an explicit
        # raster-edit layer instead of silently discarding the master.
        native_edit = self.root / "native-canvas-edit.png"
        Image.new("RGBA", (asset.width, asset.height), (1, 2, 3, 255)).save(
            native_edit
        )
        self.window._replace_visual_asset(
            state,
            asset,
            native_edit,
            native_canvas_edit={
                "changed_pixel_count_from_previous_canvas": 1,
                "operation": "native-canvas-raster-edit-after-import",
            },
        )
        self.application.processEvents()
        self.window._refresh_visual_action_states(state)
        edited_draft = self.window._texture_master_drafts[asset.asset_id]
        self.assertEqual(edited_draft.source_image.read_bytes(), original_bytes)
        self.assertTrue(edited_draft.native_canvas_edited)
        self.assertEqual(
            edited_draft.editor_transform["native_canvas_edit"]["operation"],
            "native-canvas-raster-edit-after-import",
        )
        self.assertTrue(state.master_button.isEnabled())

    def test_built_in_visual_editor_records_a_native_raster_edit_layer(self) -> None:
        body = ast.get_source_segment(
            _STUDIO.read_text(encoding="utf-8"), _function("_edit_visual_asset")
        ) or ""
        self.assertIn("native_canvas_edit=", body)
        self.assertIn("native-canvas-raster-edit-after-import", body)


if __name__ == "__main__":
    unittest.main()
