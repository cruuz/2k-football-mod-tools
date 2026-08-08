"""APF texture import dialog and drop share one fitted path (community resize).

Mirrors ``test_2k5_import_offers_resize``: structural AST/wiring checks on the
shipped GUI so an off-size PNG is prepared via ``image_fit``, not refused.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from mod_editor.core.image_fit import FIT_MODES, fit_image

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

_GUI = (
    Path(__file__).resolve().parents[2]
    / "mod_editor"
    / "apf_studio"
    / "gui.py"
)


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(_GUI.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is no longer defined in apf_studio/gui.py")


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


class ApfImportOffersResizeTests(unittest.TestCase):
    def test_fit_slot_image_uses_image_fit(self) -> None:
        node = _function("fit_slot_image")
        calls = _calls(node)
        self.assertIn("fit_image", calls)
        self.assertIn("fit_to_png", calls)

    def test_browser_replace_from_drop_reaches_fit_slot_image(self) -> None:
        tree = ast.parse(_GUI.read_text(encoding="utf-8"))
        droppers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_replace_from_drop"
        ]
        self.assertGreaterEqual(len(droppers), 1, "expected at least one drop replace path")
        any_fit = False
        for dropper in droppers:
            calls = _calls(dropper)
            if calls & {
                "fit_slot_image",
                "fit_image",
                "fit_to_png",
                "_prepare_digital_font_mask",
                "_stage_path",
            } or any("fit" in c.lower() or "prepare" in c.lower() for c in calls):
                any_fit = True
        self.assertTrue(any_fit, "at least one _replace_from_drop must fit images")

    def test_stretch_mode_is_shipped(self) -> None:
        self.assertIn("stretch", FIT_MODES)
        self.assertIn("contain", FIT_MODES)
        self.assertIn("cover", FIT_MODES)

    @unittest.skipIf(Image is None, "Pillow missing")
    def test_stretch_drives_shipped_fit_image(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wide.png"
            Image.new("RGBA", (200, 50), (255, 0, 0, 255)).save(path)
            result = fit_image(path, 100, 100, mode="stretch")
            self.assertEqual(result.action, "stretched")
            self.assertEqual((result.width, result.height), (100, 100))
            self.assertEqual(len(result.rgba), 100 * 100 * 4)


if __name__ == "__main__":
    unittest.main()
