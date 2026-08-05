"""Headless tests for the APF full-shell helmet-logo placement canvas."""

from __future__ import annotations

import os
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt5.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QMouseEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from mod_editor.apf_studio import gui  # noqa: E402
from mod_editor.apf_studio.gui import ApfTeamLogoPanel  # noqa: E402
from mod_editor.apf_studio.helmet_logo_placement import (  # noqa: E402
    AUTO_TARGET_BOUNDS,
    HelmetLogoPlacementError,
    Placement,
    active_bbox,
    auto_fit_placement,
    compose_contained_master_transform,
    import_mask_nearest,
    render_placement,
    reset_placement,
)
from mod_editor.apf_studio.helmet_logo_placement_qt import (  # noqa: E402
    HelmetLogoPlacementCanvas,
    HelmetLogoPlacementDialog,
    HelmetLogoPlacementEdit,
)
from mod_editor.apf_studio.helmet_logo_regions import TwoRegionPalette  # noqa: E402


def _rectangle_mask(
    bounds: tuple[int, int, int, int] = (120, 210, 391, 301),
) -> bytes:
    rgba = bytearray(512 * 512 * 4)
    x_min, y_min, x_max, y_max = bounds
    for y_value in range(y_min, y_max + 1):
        for x_value in range(x_min, x_max + 1):
            offset = (y_value * 512 + x_value) * 4
            colour = (255, 0, 0, 255) if x_value < 256 else (0, 255, 0, 255)
            rgba[offset : offset + 4] = bytes(colour)
    return bytes(rgba)


class HelmetLogoPlacementCoreTests(unittest.TestCase):
    def test_nonsquare_master_composes_contain_active_center_and_final_affine(self) -> None:
        """Raw dimensions must not receive the semantic-canvas Placement directly."""

        normalized = _rectangle_mask((100, 180, 300, 280))
        placement = Placement(
            center_x=260.0,
            center_y=250.0,
            scale_x=1.5,
            scale_y=0.6,
            rotation_degrees=30.0,
        )
        result = compose_contained_master_transform(
            1000, 400, normalized, placement, resample="bicubic"
        )
        # 1000x400 contains to 512x205 at (0,153). Its centre (256,255.5)
        # differs from this mask's active centre (200.5,230.5); that offset is
        # independently scaled and rotated before it reaches the final centre.
        local_x = (256.0 - 200.5) * 1.5
        local_y = (255.5 - 230.5) * 0.6
        expected_x = 260.0 + math.cos(math.radians(30)) * local_x - 0.5 * local_y
        expected_y = 250.0 + 0.5 * local_x + math.cos(math.radians(30)) * local_y
        self.assertAlmostEqual(result.center_x, expected_x)
        self.assertAlmostEqual(result.center_y, expected_y)
        self.assertEqual(result.width, 512 * 1.5)
        self.assertEqual(result.height, 205 * 0.6)
        self.assertEqual(result.rotation_degrees, 30.0)
        self.assertNotEqual(result.center_x, placement.center_x)
        self.assertNotEqual(result.center_y, placement.center_y)

    def test_auto_fit_spans_the_proved_front_crown_rear_envelope(self) -> None:
        source = _rectangle_mask()
        placement = auto_fit_placement(source)
        result = render_placement(source, placement)
        self.assertEqual(result.active_bbox, AUTO_TARGET_BOUNDS)
        self.assertEqual(len(result.rgba), 512 * 512 * 4)
        self.assertTrue(result.palette_values_preserved)

    def test_width_height_rotation_and_xy_are_independent(self) -> None:
        source = _rectangle_mask((180, 220, 331, 291))
        identity = reset_placement(source)
        placed = Placement(
            center_x=identity.center_x + 24,
            center_y=identity.center_y - 18,
            scale_x=1.5,
            scale_y=0.75,
            rotation_degrees=12.0,
        )
        result = render_placement(source, placed)
        x_min, y_min, x_max, y_max = result.active_bbox
        self.assertGreater(x_max - x_min, 151)
        self.assertLess(y_max - y_min, 100)
        self.assertGreater((x_min + x_max) / 2, 256)
        self.assertLess((y_min + y_max) / 2, 256)

    def test_empty_and_off_canvas_masks_fail_closed(self) -> None:
        with self.assertRaisesRegex(HelmetLogoPlacementError, "mask is empty"):
            auto_fit_placement(bytes(512 * 512 * 4))
        source = _rectangle_mask((200, 220, 311, 291))
        with self.assertRaisesRegex(HelmetLogoPlacementError, "clips visible art"):
            render_placement(
                source,
                Placement(20.0, 20.0, 3.0, 3.0, 45.0),
            )

    def test_nearest_import_preserves_region_mask_palette(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two-colour.png"
            image = Image.new("RGBA", (2, 1), (255, 0, 0, 255))
            image.putpixel((1, 0), (0, 255, 0, 255))
            image.save(path)
            imported = import_mask_nearest(path)
        self.assertEqual(imported.action, "nearest-contained")
        self.assertEqual(len(imported.rgba), 512 * 512 * 4)
        palette = {
            imported.rgba[offset : offset + 4]
            for offset in range(0, len(imported.rgba), 4)
        }
        self.assertEqual(
            palette,
            {bytes((0, 0, 0, 0)), bytes((255, 0, 0, 255)), bytes((0, 255, 0, 255))},
        )


class HelmetLogoPlacementQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_dialog_exposes_direct_and_exact_controls(self) -> None:
        dialog = HelmetLogoPlacementDialog(_rectangle_mask(), auto_fit=True)
        try:
            self.assertEqual(dialog.windowTitle(), "Place full-shell helmet logo")
            self.assertEqual(dialog.canvas.size().width(), 512)
            self.assertEqual(dialog.canvas.size().height(), 512)
            self.assertEqual(dialog.canvas.accessibleName(),
                             "Helmet logo front, crown, and rear placement canvas")
            self.assertTrue(dialog.auto_fit_button.text().startswith("Auto-fit"))
            self.assertEqual(dialog.reset_button.text(), "Reset")
            self.assertNotEqual(dialog.scale_x.value(), dialog.scale_y.value())
            self.assertTrue(
                dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
            )
            self.assertIn("exact 512×512", dialog.status.text())
        finally:
            dialog.deleteLater()
            self.application.processEvents()

    def test_canvas_drag_updates_xy_without_changing_scale_or_rotation(self) -> None:
        source = _rectangle_mask((200, 220, 311, 291))
        original = reset_placement(source)
        canvas = HelmetLogoPlacementCanvas(source, original)
        dragged: list[Placement] = []
        canvas.placementDragged.connect(dragged.append)
        canvas.show()
        self.application.processEvents()
        try:
            canvas.mousePressEvent(
                QMouseEvent(
                    QEvent.MouseButtonPress,
                    QPointF(256, 256),
                    Qt.LeftButton,
                    Qt.LeftButton,
                    Qt.NoModifier,
                )
            )
            canvas.mouseMoveEvent(
                QMouseEvent(
                    QEvent.MouseMove,
                    QPointF(276, 241),
                    Qt.NoButton,
                    Qt.LeftButton,
                    Qt.NoModifier,
                )
            )
            canvas.mouseReleaseEvent(
                QMouseEvent(
                    QEvent.MouseButtonRelease,
                    QPointF(276, 241),
                    Qt.LeftButton,
                    Qt.NoButton,
                    Qt.NoModifier,
                )
            )
            self.application.processEvents()
            self.assertTrue(dragged)
            latest = dragged[-1]
            self.assertAlmostEqual(latest.center_x, original.center_x + 20)
            self.assertAlmostEqual(latest.center_y, original.center_y - 15)
            self.assertEqual(latest.scale_x, original.scale_x)
            self.assertEqual(latest.scale_y, original.scale_y)
            self.assertEqual(latest.rotation_degrees, original.rotation_degrees)
        finally:
            canvas.close()
            canvas.deleteLater()
            self.application.processEvents()

    def test_canvas_drag_never_leaves_the_canvas(self) -> None:
        """Drags clamp to the canvas so preview and spinboxes always agree."""
        source = _rectangle_mask((200, 220, 311, 291))
        canvas = HelmetLogoPlacementCanvas(source, reset_placement(source))
        dragged: list[Placement] = []
        canvas.placementDragged.connect(dragged.append)
        canvas.show()
        self.application.processEvents()
        try:
            canvas.mousePressEvent(
                QMouseEvent(
                    QEvent.MouseButtonPress,
                    QPointF(256, 256),
                    Qt.LeftButton,
                    Qt.LeftButton,
                    Qt.NoModifier,
                )
            )
            canvas.mouseMoveEvent(
                QMouseEvent(
                    QEvent.MouseMove,
                    QPointF(5000, -4000),
                    Qt.NoButton,
                    Qt.LeftButton,
                    Qt.NoModifier,
                )
            )
            self.assertTrue(dragged)
            latest = dragged[-1]
            self.assertGreaterEqual(latest.center_x, 0.0)
            self.assertLessEqual(latest.center_x, 512.0)
            self.assertGreaterEqual(latest.center_y, 0.0)
            self.assertLessEqual(latest.center_y, 512.0)
            # The controls can express exactly what the canvas shows.
            self.assertEqual(canvas.placement, latest)
        finally:
            canvas.close()
            canvas.deleteLater()
            self.application.processEvents()

    def test_repeated_renders_always_start_from_the_original_source(self) -> None:
        """No resample compounding: every preview re-renders the import basis."""
        from mod_editor.apf_studio.helmet_logo_placement_qt import _display_image

        source = _rectangle_mask((180, 180, 330, 330))
        first = Placement(center_x=256.0, center_y=256.0,
                          scale_x=1.0, scale_y=1.0)
        canvas = HelmetLogoPlacementCanvas(source, first)
        canvas.show()
        self.application.processEvents()
        try:
            moved = Placement(center_x=300.0, center_y=200.0,
                              scale_x=0.8, scale_y=1.25, rotation_degrees=12.0)
            canvas.set_placement(moved)
            canvas.set_placement(first)
            canvas.set_placement(moved)
            # The import basis is untouched by any number of re-renders...
            self.assertEqual(canvas._source_rgba, source)
            # ...and the visible pixels are exactly one clean render of it.
            expected = _display_image(
                render_placement(source, moved, allow_clipping=True).rgba
            )
            self.assertEqual(
                canvas._preview.constBits().asstring(expected.sizeInBytes()),
                expected.constBits().asstring(expected.sizeInBytes()),
            )
        finally:
            canvas.close()
            canvas.deleteLater()
            self.application.processEvents()


class _Source:
    index_0a = "/nonexistent/APF/0A"


class _Facade:
    source_ready = True
    source = _Source()
    modified_asset_ids: frozenset[str] = frozenset()


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def __call__(self, *args: object) -> bool:
        self.calls.append(args)
        return True


class HelmetLogoPlacementPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _panel(self) -> ApfTeamLogoPanel:
        panel = ApfTeamLogoPanel(_Facade(), _Runner())  # type: ignore[arg-type]
        panel.set_context()
        self.application.processEvents()
        return panel

    def test_full_shell_import_auto_fits_then_stages_exact_pre_guard_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wide-mask.png"
            Image.frombytes("RGBA", (512, 512), _rectangle_mask()).save(source)
            panel = self._panel()
            try:
                panel.coverage.setCurrentIndex(
                    panel.coverage.findData(gui.FULL_SHELL_CREST_PROFILE)
                )
                panel.import_mode.setCurrentIndex(
                    panel.import_mode.findData(gui.REGION_MASK_IMPORT_MODE)
                )
                expected = render_placement(
                    import_mask_nearest(source).rgba,
                    auto_fit_placement(import_mask_nearest(source).rgba),
                ).rgba
                with mock.patch.object(
                    gui,
                    "place_helmet_logo",
                    return_value=HelmetLogoPlacementEdit(
                        expected,
                        auto_fit_placement(import_mask_nearest(source).rgba),
                    ),
                ) as place:
                    panel._stage_path(source)
                place.assert_called_once()
                self.assertTrue(place.call_args.kwargs["auto_fit"])
                self.assertIsNotNone(panel._staged_png)
                staged = import_mask_nearest(Path(panel._staged_png))
                self.assertEqual(staged.rgba, expected)
                self.assertEqual(active_bbox(staged.rgba), AUTO_TARGET_BOUNDS)
                self.assertFalse(panel.fit_visible_mask.isChecked())
                self.assertFalse(panel.fit_visible_mask.isVisible())
                self.assertFalse(panel.fit_visible_mask.isEnabled())
                self.assertTrue(panel.place_button.isEnabled())
                self.assertIn("front/crown/rear", panel.place_button.toolTip())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_retail_import_keeps_existing_path_and_never_opens_placement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "retail-mask.png"
            Image.frombytes("RGBA", (512, 512), _rectangle_mask()).save(source)
            panel = self._panel()
            try:
                self.assertEqual(panel.coverage.currentData(), gui.RETAIL_CREST_PROFILE)
                self.assertFalse(panel.place_button.isEnabled())
                with mock.patch.object(gui, "place_helmet_logo") as place:
                    panel._stage_path(source)
                place.assert_not_called()
                self.assertEqual(panel._staged_png, source)
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_normal_mode_converts_before_the_placement_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "normal-rams-logo.png"
            Image.new("RGBA", (8, 4), (255, 199, 44, 255)).save(source)
            semantic = _rectangle_mask((140, 220, 371, 291))
            placed_rgba = render_placement(
                semantic, auto_fit_placement(semantic)
            ).rgba
            panel = self._panel()
            try:
                panel.coverage.setCurrentIndex(
                    panel.coverage.findData(gui.FULL_SHELL_CREST_PROFILE)
                )
                self.assertEqual(
                    panel.import_mode.currentData(), gui.NORMAL_LOGO_IMPORT_MODE
                )
                with mock.patch.object(
                    gui,
                    "convert_normal_logo",
                    return_value=mock.Mock(
                        mask_rgba=semantic,
                        mapping="test source to semantic weights",
                        palette=TwoRegionPalette(
                            shell=(0, 53, 98),
                            red_region=(165, 172, 175),
                            green_region=(255, 255, 255),
                        ),
                    ),
                ) as convert, mock.patch.object(
                    gui,
                    "place_helmet_logo",
                    return_value=HelmetLogoPlacementEdit(
                        placed_rgba, auto_fit_placement(semantic)
                    ),
                ) as place:
                    panel._stage_path(source)
                convert.assert_called_once()
                self.assertEqual(len(convert.call_args.args[0]), 512 * 512 * 4)
                self.assertEqual(place.call_args.args[0], semantic)
                self.assertEqual(panel._placement_source_rgba, semantic)
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_normal_import_uses_an_immutable_snapshot_across_dialogs(self) -> None:
        """A source changed while dialogs are open cannot alter staged metadata."""

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "dialog-race-logo.png"
            Image.new("RGBA", (1000, 400), (0, 53, 98, 255)).save(source)
            original_bytes = source.read_bytes()
            semantic = _rectangle_mask((140, 220, 371, 291))
            placement = auto_fit_placement(semantic)
            placed_rgba = render_placement(semantic, placement).rgba
            conversion = mock.Mock(
                mask_rgba=semantic,
                mapping="test source to semantic weights",
                palette=TwoRegionPalette(
                    shell=(0, 53, 98),
                    red_region=(165, 172, 175),
                    green_region=(255, 255, 255),
                ),
            )
            panel = self._panel()
            try:
                panel.coverage.setCurrentIndex(
                    panel.coverage.findData(gui.FULL_SHELL_CREST_PROFILE)
                )

                def mutate_after_snapshot(_rgba: bytes, *, parent: object):
                    self.assertIs(parent, panel)
                    source.write_bytes(b"changed while palette dialog was open")
                    return conversion

                with mock.patch.object(
                    gui,
                    "convert_normal_logo",
                    side_effect=mutate_after_snapshot,
                ), mock.patch.object(
                    gui,
                    "place_helmet_logo",
                    return_value=HelmetLogoPlacementEdit(placed_rgba, placement),
                ):
                    panel._stage_path(source)

                draft = panel._texture_master_draft
                self.assertIsNotNone(draft)
                assert draft is not None
                self.assertNotEqual(draft.source_image, source)
                self.assertEqual(draft.source_image.read_bytes(), original_bytes)
                self.assertEqual(source.read_bytes(), b"changed while palette dialog was open")
                self.assertIsNotNone(draft.native_baseline_png)
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_advanced_mode_rejects_literal_rgb_before_placement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "literal-yellow.png"
            Image.new("RGBA", (512, 512), (255, 209, 0, 255)).save(source)
            panel = self._panel()
            try:
                panel.coverage.setCurrentIndex(
                    panel.coverage.findData(gui.FULL_SHELL_CREST_PROFILE)
                )
                panel.import_mode.setCurrentIndex(
                    panel.import_mode.findData(gui.REGION_MASK_IMPORT_MODE)
                )
                with mock.patch.object(
                    gui.QMessageBox, "information"
                ) as information, mock.patch.object(
                    gui, "place_helmet_logo"
                ) as place:
                    panel._stage_path(source)
                place.assert_not_called()
                self.assertIsNone(panel._staged_png)
                self.assertIn("4-bit", information.call_args.args[2])
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_reopen_uses_original_basis_and_last_transform_without_double_resampling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wing-mask.png"
            original_rgba = _rectangle_mask((120, 210, 391, 301))
            Image.frombytes("RGBA", (512, 512), original_rgba).save(source)
            panel = self._panel()
            try:
                panel.coverage.setCurrentIndex(
                    panel.coverage.findData(gui.FULL_SHELL_CREST_PROFILE)
                )
                panel.import_mode.setCurrentIndex(
                    panel.import_mode.findData(gui.REGION_MASK_IMPORT_MODE)
                )
                normalized = import_mask_nearest(source).rgba
                first_placement = auto_fit_placement(normalized)
                first_rgba = render_placement(normalized, first_placement).rgba
                second_placement = Placement(
                    center_x=first_placement.center_x,
                    center_y=first_placement.center_y + 8,
                    scale_x=first_placement.scale_x * 0.9,
                    scale_y=first_placement.scale_y * 0.9,
                    rotation_degrees=3.0,
                )
                second_rgba = render_placement(normalized, second_placement).rgba
                with mock.patch.object(
                    gui,
                    "place_helmet_logo",
                    side_effect=(
                        HelmetLogoPlacementEdit(first_rgba, first_placement),
                        HelmetLogoPlacementEdit(second_rgba, second_placement),
                    ),
                ) as place:
                    panel._stage_path(source)
                    panel._place_current_logo()
                self.assertEqual(place.call_count, 2)
                first_call, second_call = place.call_args_list
                self.assertEqual(first_call.args[0], normalized)
                self.assertEqual(second_call.args[0], normalized)
                self.assertIsNone(first_call.kwargs["initial_placement"])
                self.assertEqual(
                    second_call.kwargs["initial_placement"], first_placement
                )
                self.assertEqual(panel._placement_source_rgba, normalized)
                self.assertEqual(panel._placement_state, second_placement)

                # The hidden legacy checkbox cannot trigger a recommit or
                # replace the authored placement transform.
                with mock.patch.object(panel, "_commit_design") as commit:
                    panel.fit_visible_mask.setChecked(True)
                    self.application.processEvents()
                commit.assert_not_called()
                self.assertEqual(panel._placement_state, second_placement)
            finally:
                panel.deleteLater()
                self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
