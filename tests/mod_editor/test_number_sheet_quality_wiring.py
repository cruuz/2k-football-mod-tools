"""Execute the exact protected GUI patch in memory; never edit the panel."""
from __future__ import annotations

import ast
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/fixtures")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_digit_preview import DigitSheetPreview
from mod_editor.core.nfl2k5_digit_sheet import SHEET_LAYOUTS
from number_sheet_quality_cases import author_sheet


def proposed_source():
    path = "mod_editor/gui/studio_qt.py"
    original = (ROOT / path).read_text()
    if "def _review_digit_sheet_preview(" in original:
        return original
    return apply_fixture(original, path, "number_sheet_quality_wiring.patch")


def apply_fixture(original, path, fixture):
    source = original.splitlines(True)
    sections = (ROOT / "tests/fixtures" / fixture).read_text().split("--- a/")[1:]
    section = next(s for s in sections if s.startswith(path + "\n"))
    lines = ("--- a/" + section).splitlines(True)
    assert lines[:2] == [f"--- a/{path}\n", f"+++ b/{path}\n"]
    output, cursor, i = [], 0, 2
    while i < len(lines):
        start = int(re.match(r"@@ -(\d+)", lines[i])[1]) - 1
        assert start >= cursor
        output.extend(source[cursor:start]); cursor = start; i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            line = lines[i]
            if line == "\n":
                line = " \n"
            if line[0] in " -":
                assert source[cursor] == line[1:], (cursor, line)
                cursor += 1
            if line[0] in " +": output.append(line[1:])
            i += 1
    return "".join(output + source[cursor:])


class NumberSheetRuntimeWiringTests(unittest.TestCase):
    def proposal(self, path):
        original = (ROOT / path).read_text()
        if ('"mod_editor.core.nfl2k5_digit_preview"' in original
                or 'mod_editor/core/nfl2k5_digit_texture.py' in original):
            return original
        return apply_fixture(original, path, "number_sheet_quality_runtime.patch")

    def test_frozen_provider_closures_accept_every_exact_source_hash(self):
        from mod_editor.core import providers
        tree = ast.parse(self.proposal("mod_editor/core/providers.py"))
        for name in ("Nfl2k5UnifiedVisualProvider", "Nfl2k5ScorebugProvider"):
            owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
            assignment = next(n for n in owner.body if isinstance(n, ast.AnnAssign)
                              and n.target.id == "module_pins")
            pins = eval(compile(ast.Expression(assignment.value), "<proposed provider pins>", "eval"),
                        {}, dict(vars(getattr(providers, name))))
            providers._validate_pin_set(ROOT, pins, name)
            if name == "Nfl2k5UnifiedVisualProvider":
                self.assertIn("mod_editor/core/nfl2k5_digit_texture.py", pins)

    def test_release_allowlist_imports_and_runtime_hashes_cover_the_proposal(self):
        allowlist = self.proposal("packaging/release-allowlist.txt").splitlines()
        runtime = self.proposal("packaging/check_2k5_mod_studio_runtime.py")
        for module in ("nfl2k5_digit_texture", "nfl2k5_digit_preview"):
            self.assertIn(f"mod_editor/core/{module}.py", allowlist)
            self.assertIn(f'"mod_editor.core.{module}"', runtime)
        tree = ast.parse(runtime)
        pins = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
                                     and any(isinstance(t, ast.Name) and t.id == "RC29_AUDIO_ANNOTATION_RUNTIME_PINS"
                                             for t in n.targets)))
        self.assertEqual(pins["mod_editor/gui/studio_qt.py"], hashlib.sha256(proposed_source().encode()).hexdigest())
        self.assertEqual(pins["mod_editor/studio/facade.py"], hashlib.sha256((ROOT / "mod_editor/studio/facade.py").read_bytes()).hexdigest())


class NumberSheetQualityWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from mod_editor.gui import studio_qt
            from PyQt5.QtWidgets import QApplication
        except ImportError as exc:
            raise unittest.SkipTest(f"Offscreen Qt dependencies unavailable: {exc}")
        cls.app = QApplication.instance() or QApplication([])
        tree = ast.parse(proposed_source())
        owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "StudioMainWindow")
        cls.ns = dict(studio_qt.__dict__)
        methods = [n for n in owner.body if isinstance(n, ast.FunctionDef)
                   and n.name in {"_review_digit_sheet_preview", "_choose_digit_sheet_import"}]
        exec(compile(ast.Module(body=methods, type_ignores=[]), "<number quality proposal>", "exec"), cls.ns)

    def preview(self):
        stream = BytesIO(); Image.new("RGB", (730, 850), "white").save(stream, "PNG")
        return DigitSheetPreview(stream.getvalue(), "horizontal: 62x62 cell to 64x64 slot.\nInspect all levels.", ())

    def test_preview_dialog_keeps_encoded_pixels_at_native_display_size_and_notes(self):
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QLabel, QWidget
        preview = self.preview()
        def inspect(dialog):
            self.assertEqual(dialog.windowTitle(), "Number sheet: encoded game preview")
            text = dialog.findChild(QPlainTextEdit)
            self.assertTrue(text.isReadOnly())
            self.assertEqual(text.toPlainText(), preview.details)
            labels = dialog.findChildren(QLabel)
            picture = next(label for label in labels if label.pixmap() is not None)
            self.assertEqual((picture.pixmap().width(), picture.pixmap().height()), (730, 850))
            self.assertEqual(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).text(), "Import all ten digits")
            return QDialog.Accepted
        host = QWidget()
        try:
            with patch.object(QDialog, "exec_", inspect):
                self.assertTrue(self.ns["_review_digit_sheet_preview"](host, preview))
        finally:
            host.close(); host.deleteLater()

    def run_flow(self, *, accept=True, encode_error=False, change_source=False):
        from mod_editor.core.nfl2k5_uniform_catalog import DEFAULT_REPORT, load_nfl2k5_uniform_catalog
        if not DEFAULT_REPORT.is_file():
            self.skipTest(f"Private uniform catalog absent: {DEFAULT_REPORT}")
        catalog = load_nfl2k5_uniform_catalog()
        target_set = catalog.get_uniform_set("26H0")
        events = []
        with tempfile.TemporaryDirectory() as directory:
            source = author_sheet(Path(directory) / "sheet.png", "crisp")
            facade = SimpleNamespace(source_ready=True, source_sha256="source")
            def encode(outputs, progress):
                events.append("encode")
                if encode_error: raise ValidationError("Digit 7 cannot fit")
                self.assertEqual(len(outputs), 10)
                return self.preview()
            def export(selectors, destination, *, container, progress):
                events.append("export")
                self.assertEqual(tuple(selectors), ("26H0",))
                destination.mkdir()
                rows = []
                for asset in catalog.assets_for_set("26H0"):
                    if asset.family == "jersey" and asset.digit is not None:
                        path = f"{asset.digit}.png"
                        (destination / path).write_bytes(b"placeholder")
                        rows.append({"asset_id": asset.asset_id, "path": path})
                (destination / "team-kit.json").write_text(json.dumps({"assets": rows}))
                # Use the production contract's actual manifest name.
                from mod_editor.studio.uniform_bundle import TEAM_KIT_MANIFEST
                (destination / TEAM_KIT_MANIFEST).write_text(json.dumps({"assets": rows}))
            def stage(kit, progress, *, expected_set_selectors):
                events.append("import")
                self.assertEqual(expected_set_selectors, ("26H0",))
                for digit in range(10):
                    with Image.open(kit / f"{digit}.png") as image:
                        self.assertEqual(image.size, (64, 64))
                return SimpleNamespace(changed_count=10)
            def review(preview):
                events.append("review")
                # Changing the source PNG after preview must not change what
                # is imported: the split PNG tuple is the accepted snapshot.
                source.write_bytes(b"external save while reviewing")
                if change_source: facade.source_sha256 = "changed"
                return accept
            facade.preview_digit_sheet = encode
            facade.export_team_kit_sets = export
            facade.import_team_kit = stage
            host = SimpleNamespace(
                facade=facade, uniform_catalog=catalog, _selected_set=target_set, _selected_asset=None,
                _review_digit_sheet_preview=review, _show_error=Mock(),
                _mark_workspace_changed=Mock(), _refresh_edit_state=Mock(),
                team_kit_imported=SimpleNamespace(emit=Mock()), _show_team_kit_import_result=Mock(),
                _blocking=False, _post_blocking_continuations=[],
            )
            from mod_editor.gui.studio_qt import StudioMainWindow
            host._defer_until_blocking_task_finished = lambda action: (
                StudioMainWindow._defer_until_blocking_task_finished(host, action))
            def start_task(operation, done, **kwargs):
                # Match _start_task: result is delivered before finished clears
                # the busy state. A nested blocking operation would be refused.
                self.assertFalse(host._blocking)
                host._blocking = True
                result = operation(lambda *_: None)
                done(result)
                host._blocking = False
                StudioMainWindow._drain_post_blocking_continuations(host)
            host._start_task = start_task
            ns = self.ns
            with patch.dict(ns, {
                "QFileDialog": SimpleNamespace(getOpenFileName=lambda *a: (str(source), "")),
                "QInputDialog": SimpleNamespace(getItem=Mock(side_effect=[("Jersey numbers", True), (SHEET_LAYOUTS[0][0], True)])),
            }):
                if encode_error:
                    with self.assertRaises(ValidationError): ns["_choose_digit_sheet_import"](host)
                else: ns["_choose_digit_sheet_import"](host)
            if change_source:
                self.assertIn("game source changed", host._show_error.call_args[0][0])
            self.assertEqual(host._mark_workspace_changed.call_count, int(accept and not encode_error and not change_source))
        return events

    def test_encoded_review_precedes_single_atomic_team_kit_import(self):
        self.assertEqual(self.run_flow(), ["encode", "review", "export", "import"])

    def test_cancel_or_encoder_failure_or_source_change_cannot_stage(self):
        self.assertEqual(self.run_flow(accept=False), ["encode", "review"])
        self.assertEqual(self.run_flow(encode_error=True), ["encode"])
        self.assertEqual(self.run_flow(change_source=True), ["encode", "review"])

    def test_facade_encoding_holds_source_session_lock(self):
        from mod_editor.studio.facade import Nfl2k5StudioFacade
        from threading import RLock
        gate = RLock()
        session = SimpleNamespace(cache=SimpleNamespace(pack0=Path("index")))
        outputs = (SimpleNamespace(asset_id="digit"),)
        target = object()
        host = SimpleNamespace(_lock=gate, _require_session=lambda: session,
                               uniform_catalog=SimpleNamespace(get_asset=lambda _: target))
        def encode(index, selected, supplied, progress):
            if hasattr(gate, "_is_owned"): self.assertTrue(gate._is_owned())
            self.assertEqual((index, selected, supplied), (Path("index"), (target,), outputs))
            return "preview"
        with patch("mod_editor.core.nfl2k5_digit_preview.preview_digit_sheet", encode):
            self.assertEqual(Nfl2k5StudioFacade.preview_digit_sheet(host, outputs, Mock()), "preview")


if __name__ == "__main__":
    unittest.main()
