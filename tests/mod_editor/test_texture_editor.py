"""The built-in pixel editor must hand back exactly the slot's size, always.

Editing a texture used to mean exporting a PNG, opening another program, and
remembering not to change its size or flatten its alpha. Each of those has cost
someone a build: a resaved 512x256 that came back 513x256, a jersey flattened
onto white, a crest that lost its transparency.

The editor removes the round trip, and the property that makes it safe is that
there is no resize control at all -- the canvas *is* the retail size, so what
comes out cannot be the wrong shape. These tests hold that line, and hold the
behaviour of the tools that touch alpha, because alpha is what silently ruins a
crest.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import QApplication
except ImportError:  # pragma: no cover - PyQt5 ships with the app
    QApplication = None

if QApplication is not None:
    from mod_editor.gui.texture_editor import (
        MAX_UNDO, TOOLS, ZOOM_STEPS, TextureEditorDialog,
    )

_APP = None


def _function_source(path: Path, name: str) -> str:
    """Return one complete named function without a brittle character window."""

    source = path.read_text(encoding="utf-8")
    matches = [
        node
        for node in ast.walk(ast.parse(source, filename=str(path)))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one {name} function in {path}, found {len(matches)}"
        )
    block = ast.get_source_segment(source, matches[0])
    if block is None:
        raise AssertionError(f"could not recover {name} source from {path}")
    return block


def setUpModule() -> None:
    global _APP
    if QApplication is not None:
        _APP = QApplication.instance() or QApplication([])


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class TextureEditorTests(unittest.TestCase):
    WIDTH = 32
    HEIGHT = 16

    def _dialog(self, width: int | None = None, height: int | None = None):
        width = width or self.WIDTH
        height = height or self.HEIGHT
        pixels = bytearray()
        for y in range(height):
            for x in range(width):
                pixels += bytes((x * 7 % 256, y * 11 % 256, 90, 255))
        return TextureEditorDialog(bytes(pixels), width, height, "Test Slot")

    def test_the_canvas_is_the_retail_size_at_one_to_one(self) -> None:
        dialog = self._dialog()
        self.assertEqual(
            (dialog.canvas.width(), dialog.canvas.height()),
            (self.WIDTH, self.HEIGHT),
        )

    def test_zoom_only_scales_the_view_not_the_image(self) -> None:
        """The output size must be untouched by how far in you were zoomed."""
        dialog = self._dialog()
        for zoom in ZOOM_STEPS:
            with self.subTest(zoom=zoom):
                dialog.canvas.set_zoom(zoom)
                self.assertEqual(dialog.canvas.width(), self.WIDTH * zoom)
                result = dialog.result_rgba()
                self.assertEqual((result.width, result.height),
                                 (self.WIDTH, self.HEIGHT))
                self.assertEqual(len(result.rgba),
                                 self.WIDTH * self.HEIGHT * 4)

    def test_zoom_is_clamped_to_the_declared_range(self) -> None:
        dialog = self._dialog()
        dialog.canvas.set_zoom(9999)
        self.assertEqual(dialog.canvas.zoom, ZOOM_STEPS[-1])
        dialog.canvas.set_zoom(-5)
        self.assertEqual(dialog.canvas.zoom, ZOOM_STEPS[0])

    def test_a_mismatched_buffer_is_refused_rather_than_guessed(self) -> None:
        with self.assertRaises(ValueError):
            TextureEditorDialog(b"\x00" * 10, 32, 16, "Test Slot")

    def test_the_pencil_paints_the_chosen_colour(self) -> None:
        dialog = self._dialog()
        canvas = dialog.canvas
        canvas.set_tool("pencil")
        canvas.set_color(QColor(255, 0, 0, 255))
        canvas.set_brush(1)
        canvas._snapshot()
        canvas._dab(4, 4)
        self.assertEqual(canvas.image.pixelColor(4, 4).name(), "#ff0000")

    def test_the_eraser_writes_transparency_not_black(self) -> None:
        """A crest erased to opaque black is a black box on a helmet."""
        dialog = self._dialog()
        canvas = dialog.canvas
        canvas.set_tool("eraser")
        canvas.set_brush(1)
        canvas._snapshot()
        canvas._dab(6, 6)
        self.assertEqual(canvas.image.pixelColor(6, 6).alpha(), 0)

    def test_the_brush_covers_the_size_it_says(self) -> None:
        dialog = self._dialog()
        canvas = dialog.canvas
        canvas.set_tool("pencil")
        canvas.set_color(QColor(0, 0, 255, 255))
        canvas.set_brush(3)
        canvas._snapshot()
        canvas._dab(10, 8)
        painted = sum(
            1
            for y in range(self.HEIGHT)
            for x in range(self.WIDTH)
            if canvas.image.pixelColor(x, y).name() == "#0000ff"
        )
        self.assertEqual(painted, 9)

    def test_a_brush_at_the_edge_does_not_wrap_or_crash(self) -> None:
        dialog = self._dialog()
        canvas = dialog.canvas
        canvas.set_tool("pencil")
        canvas.set_color(QColor(255, 255, 0, 255))
        canvas.set_brush(5)
        canvas._snapshot()
        canvas._dab(0, 0)
        canvas._dab(self.WIDTH - 1, self.HEIGHT - 1)
        result = dialog.result_rgba()
        self.assertEqual(len(result.rgba), self.WIDTH * self.HEIGHT * 4)

    def test_fill_replaces_a_contiguous_region_and_terminates(self) -> None:
        dialog = self._dialog(8, 8)
        canvas = dialog.canvas
        for y in range(8):
            for x in range(8):
                canvas.image.setPixelColor(x, y, QColor(10, 10, 10, 255))
        canvas.set_tool("fill")
        canvas.set_color(QColor(0, 255, 0, 255))
        canvas._snapshot()
        canvas._flood(0, 0)
        filled = sum(
            1 for y in range(8) for x in range(8)
            if canvas.image.pixelColor(x, y).name() == "#00ff00"
        )
        self.assertEqual(filled, 64)

    def test_fill_on_its_own_colour_is_a_no_op(self) -> None:
        dialog = self._dialog(8, 8)
        canvas = dialog.canvas
        canvas.set_tool("fill")
        canvas.set_color(canvas.image.pixelColor(0, 0))
        before = dialog.result_rgba().rgba
        canvas._flood(0, 0)
        self.assertEqual(dialog.result_rgba().rgba, before)

    def test_undo_and_redo_return_the_exact_pixels(self) -> None:
        dialog = self._dialog()
        canvas = dialog.canvas
        original = dialog.result_rgba().rgba
        canvas.set_tool("pencil")
        canvas.set_color(QColor(1, 2, 3, 255))
        canvas._snapshot()
        canvas._dab(2, 2)
        changed = dialog.result_rgba().rgba
        self.assertNotEqual(changed, original)
        canvas.undo()
        self.assertEqual(dialog.result_rgba().rgba, original)
        canvas.redo()
        self.assertEqual(dialog.result_rgba().rgba, changed)

    def test_undo_history_is_bounded(self) -> None:
        """Whole-image snapshots are only safe because the depth is capped."""
        dialog = self._dialog()
        canvas = dialog.canvas
        canvas.set_tool("pencil")
        for step in range(MAX_UNDO + 10):
            canvas._snapshot()
            canvas._dab(step % self.WIDTH, 0)
        self.assertLessEqual(len(canvas._undo), MAX_UNDO)

    def test_undo_on_an_untouched_image_does_nothing(self) -> None:
        dialog = self._dialog()
        before = dialog.result_rgba().rgba
        dialog.canvas.undo()
        dialog.canvas.redo()
        self.assertEqual(dialog.result_rgba().rgba, before)

    def test_picking_a_colour_becomes_the_painting_colour(self) -> None:
        dialog = self._dialog()
        canvas = dialog.canvas
        canvas.image.setPixelColor(3, 3, QColor(9, 200, 30, 255))
        dialog._adopt_colour(canvas.image.pixelColor(3, 3))
        canvas.set_tool("pencil")
        canvas.set_brush(1)
        canvas._snapshot()
        canvas._dab(12, 12)
        self.assertEqual(canvas.image.pixelColor(12, 12).name(), "#09c81e")

    def test_every_declared_tool_is_selectable(self) -> None:
        dialog = self._dialog()
        for tool in TOOLS:
            with self.subTest(tool=tool):
                dialog._select_tool(tool)
                self.assertTrue(dialog._tool_buttons[tool].isChecked())

    def test_a_non_square_slot_round_trips(self) -> None:
        """The nameplate strip is 1024x32; nothing may assume squareness."""
        dialog = self._dialog(64, 8)
        result = dialog.result_rgba()
        self.assertEqual((result.width, result.height), (64, 8))
        self.assertEqual(len(result.rgba), 64 * 8 * 4)

    def test_an_untouched_image_comes_back_byte_identical(self) -> None:
        pixels = bytearray()
        for y in range(self.HEIGHT):
            for x in range(self.WIDTH):
                pixels += bytes((x * 7 % 256, y * 11 % 256, 90, 255))
        dialog = TextureEditorDialog(bytes(pixels), self.WIDTH, self.HEIGHT, "Slot")
        self.assertEqual(dialog.result_rgba().rgba, bytes(pixels))


class WiringTests(unittest.TestCase):
    """Both editors must actually offer it, or it is a module nobody reaches."""

    def test_the_2k5_visual_browser_has_an_edit_button(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        self.assertIn('edit_button = QPushButton("Edit…")', source)
        self.assertIn("actions.addWidget(edit_button)", source)
        self.assertIn("def _edit_visual_asset", source)

    def test_the_2k5_editor_routes_its_result_back_through_replace(self) -> None:
        """An edit that does not become a staged replacement changes nothing."""
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        )
        block = _function_source(source, "_edit_visual_asset")
        self.assertIn("edit_texture(", block)
        self.assertIn("self._replace_visual_asset(", block)
        self.assertIn("staged,", block)
        self.assertIn("native_canvas_edit=", block)

    def test_the_apf_crest_panel_has_an_edit_button(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "apf_studio" / "gui.py"
        ).read_text(encoding="utf-8")
        self.assertIn("self.edit_button = QPushButton(\"Edit…\")", source)
        self.assertIn("actions.addWidget(self.edit_button)", source)
        self.assertIn("def _edit_in_place", source)

    def test_the_apf_editor_continues_from_a_staged_edit(self) -> None:
        """Editing twice must not silently start over from retail."""
        source = (
            _REPO_ROOT / "mod_editor" / "apf_studio" / "gui.py"
        )
        block = _function_source(source, "_edit_in_place")
        commit = _function_source(source, "_commit_design")
        self.assertIn("source = self._staged_png", block)
        self.assertIn("_decode_source_operation", block)
        self.assertIn("if self._commit_design(staged)", block)
        self.assertIn(
            "self._staged_png = Path(modification.replacement_path)", commit
        )


if __name__ == "__main__":
    unittest.main()
