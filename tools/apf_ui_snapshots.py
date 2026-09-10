#!/usr/bin/env python3
"""Offline APF visual audit. Screenshots stay in a caller-owned private directory.

This development tool uses synthetic dialog fixtures from the test suite. Page
captures optionally load a read-only retail source; no game bytes are committed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MOD_STUDIO_NO_UPDATE_CHECK"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "mod_editor"))


def dialog_fixtures(window, root):
    """Every studio-owned modal, including both ad-hoc dialog constructors."""
    from PIL import Image
    from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox, QInputDialog
    from mod_editor.apf_studio import gui
    from mod_editor.apf_studio.models import ApfCategory
    from mod_editor.apf_studio.play_designer_qt import PlayDesignDialog, FormationDesignDialog, CpuCallDialog
    from mod_editor.apf_studio.helmet_logo_regions_qt import NormalLogoRegionDialog
    from mod_editor.apf_studio.helmet_logo_placement_qt import HelmetLogoPlacementDialog
    from mod_editor.apf_studio.ps3_texture_bundle_qt import Ps3BundleMappingDialog
    from mod_editor.apf_studio.ps3_texture_bundle import read_bundle
    from mod_editor.apf_studio.team_art import ArtLayer, ArtPackage
    from mod_editor.apf_studio.team_art_qt import TeamArtReplaceDialog
    from mod_editor.core.apf2k8_play_codec import Book
    from mod_editor.core.apf2k8_splb_writer import parse_book
    from test_apf_play_designer import synthetic, synthetic_cpu
    from test_apf_ps3_texture_bundle import bundle_files, slot, write_folder
    from test_apf_helmet_logo_regions_qt import _source_three_colours
    book = Book.from_bytes(synthetic())
    yield PlayDesignDialog(book, 4)
    yield FormationDesignDialog(book, 2)
    yield CpuCallDialog(book, {259: parse_book(synthetic_cpu(), 259)})
    bundle_root = root / "bundle"
    bundle_root.mkdir(exist_ok=True)
    files = bundle_files()
    files.update({k.replace("/selected_", "/Alternative/selected_"): v for k, v in bundle_files().items()})
    write_folder(bundle_root, files)
    yield Ps3BundleMappingDialog(read_bundle(bundle_root), [slot()])
    yield TeamArtReplaceDialog(ArtPackage("logo", 836, "uniform_logo_12.iff", 12, "Entry 836", (),
                              tuple(ArtLayer(name, name, i, 512, 512, "RGBA 4:4:4:4", True)
                                    for i, name in enumerate(("logo_l0", "logo_l1")))))
    rgba = _source_three_colours()
    yield NormalLogoRegionDialog(rgba)
    yield HelmetLogoPlacementDialog(rgba, auto_fit=False)
    png = root / "synthetic-logo.png"
    Image.frombytes("RGBA", (512, 512), rgba).save(png)
    yield gui.SlotImagePreviewDialog(png, width=512, height=512, title="Preview replacement")
    preview = SimpleNamespace(replacement_count=3, revert_count=2, unchanged_count=63,
                              conflict_count=0, source_conflict_count=0, project_conflict_count=0,
                              error_count=0, conflicts=(), errors=(), private_data=True)
    yield gui.RatingSheetImportPreviewDialog(Path("ratings.csv"), preview)
    yield gui.ExternalXma1EncoderDialog()
    yield gui.Xma1EncoderSetupWizard()
    yield window._pages[ApfCategory.ROSTERS].inspector._build_roster_alias_dialog()
    membership = window._pages[ApfCategory.PLAYBOOKS].playbook_membership
    captured = []
    with patch.object(QDialog, "exec", lambda dialog: captured.append(dialog) or QDialog.Rejected):
        membership._trailer_dialog("Formation and personnel", (0, 0), True)
    yield from captured
    for page in window._pages.values():
        capabilities = getattr(page, "capabilities", None)
        if capabilities is not None and hasattr(capabilities, "create_details_dialog"):
            yield capabilities.create_details_dialog()
    message = QMessageBox(QMessageBox.Information, "APF Mod Studio", "Your project is ready to save.",
                          QMessageBox.Ok | QMessageBox.Cancel)
    yield message
    file_dialog = QFileDialog(None, "Choose a PNG", str(root), "PNG images (*.png)")
    file_dialog.setOption(QFileDialog.DontUseNativeDialog)
    yield file_dialog
    choice = QInputDialog()
    choice.setWindowTitle("Choose stock assignment")
    choice.setLabelText("Choose a decoded assignment to copy.")
    choice.setComboBoxItems(("Keep current assignment", "Copy selected stock assignment"))
    yield choice


def pump(app, window, timeout=600):
    deadline = time.monotonic() + timeout
    quiet = 0
    while time.monotonic() < deadline:
        app.processEvents()
        busy = window._workers or window._idle_callbacks or window._pending_source_load
        quiet = 0 if busy else quiet + 1
        if quiet >= 5:
            return
        time.sleep(.02)
    raise TimeoutError("APF window did not become idle")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dialogs-only", action="store_true")
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--audit", action="store_true", help="Fail on contrast or workspace overflow")
    parser.add_argument("--team-art-families", action="store_true")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from mod_editor.apf_studio.facade import ApfStudioFacade
    from mod_editor.apf_studio.gui import ApfStudioMainWindow
    from mod_editor.apf_studio.models import APF_CATEGORY_ORDER, ApfCategory
    from mod_editor.apf_studio.team_art import FAMILIES
    from mod_editor.apf_studio.project import WorkspaceStateStore
    from mod_editor.apf_studio.ui_audit import contrast_failures, page_layout_failures
    app = QApplication.instance() or QApplication([])
    args.output.mkdir(parents=True, exist_ok=True)
    receipt = {"pages": [], "dialogs": []}
    errors = []
    def modal(box, *_args, **_kwargs):
        errors.append(box.windowTitle() + ": " + box.text())
        print("UNEXPECTED MODAL", errors[-1], flush=True)
        return QMessageBox.Cancel
    original_modal = QMessageBox.exec_
    QMessageBox.exec_ = modal
    QMessageBox.exec = modal
    with tempfile.TemporaryDirectory(prefix="apf-ui-audit-") as temporary:
        root = Path(temporary)
        window = ApfStudioMainWindow(ApfStudioFacade(cache_root=args.cache_root or root / "cache"),
                                    workspace_store=WorkspaceStateStore(root / "state"), offer_recovery=False)
        window.resize(args.width, args.height)
        window.show()
        try:
            pump(app, window)
            for state in (() if args.dialogs_only else ("empty", "loaded") if args.source else ("empty",)):
                if state == "loaded":
                    window._load_source_path(args.source)
                    pump(app, window)
                    if errors:
                        raise AssertionError(errors)
                    assert window.facade.source_ready
                folder = args.output / state
                folder.mkdir(exist_ok=True)
                for row, category in enumerate(APF_CATEGORY_ORDER):
                    window.navigation.setCurrentRow(row)
                    pump(app, window)
                    if args.audit:
                        failures = contrast_failures(window._pages[category]) + page_layout_failures(window)
                        assert not failures, (state, category.value, failures)
                    path = folder / f"{row:02d}-{category.value}.png"
                    assert window.grab().save(str(path))
                    receipt["pages"].append(str(path))
                    print("CAPTURE", path, flush=True)
            if args.team_art_families and args.source:
                window.navigation.setCurrentRow(APF_CATEGORY_ORDER.index(ApfCategory.LOGOS))
                browser = window._pages[ApfCategory.LOGOS].team_art
                folder = args.output / "team-art"
                folder.mkdir(exist_ok=True)
                receipt["team_art"] = []
                for family, label in FAMILIES:
                    browser.family.setCurrentIndex(browser.family.findData(family))
                    pump(app, window)
                    browser.grid.setCurrentRow(0)
                    app.processEvents()
                    if args.audit:
                        assert not contrast_failures(browser), contrast_failures(browser)
                        assert not page_layout_failures(window), page_layout_failures(window)
                    path = folder / f"{family}.png"
                    assert window.grab().save(str(path))
                    receipt["team_art"].append({"family": family, "count": browser.grid.count(), "path": str(path)})
                    print("CAPTURE", path, flush=True)
            folder = args.output / "dialogs"
            QMessageBox.exec_ = original_modal
            folder.mkdir(exist_ok=True)
            for number, dialog in enumerate(dialog_fixtures(window, root)):
                dialog.show()
                app.processEvents()
                if args.audit:
                    assert not contrast_failures(dialog), (dialog.windowTitle(), contrast_failures(dialog))
                path = folder / f"{number:02d}-{type(dialog).__name__}.png"
                assert dialog.grab().save(str(path))
                receipt["dialogs"].append({"path": str(path), "title": dialog.windowTitle(),
                                            "width": dialog.width(), "height": dialog.height()})
                print("CAPTURE", path, flush=True)
                dialog.close()
                dialog.deleteLater()
                app.processEvents()
        finally:
            pump(app, window)
            window._allow_close = True
            window.close()
            app.processEvents()
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
