#!/usr/bin/env python3
"""Development-only replay of the real APF window; fail on every modal/crash."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MOD_STUDIO_NO_UPDATE_CHECK"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(
        "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)"))
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--playcalling-contract-only", action="store_true",
                        help="Replay the beta-67 tab using the test-only contract modules through its facade")
    args = parser.parse_args(argv)
    if args.playcalling_contract_only:
        from tests.mod_editor.test_apf_playcalling_editor_qt import replay_contract
        captured = replay_contract()
        if args.receipt:
            args.receipt.write_bytes((json.dumps(captured, indent=2) + "\n").encode())
        print(json.dumps(captured, indent=2))
        return 0
    from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton
    from PyQt5.QtCore import QCoreApplication, QEvent
    from mod_editor.apf_studio.facade import ApfStudioFacade
    from mod_editor.apf_studio.gui import ApfStudioMainWindow
    from mod_editor.apf_studio.models import ApfCategory, APF_CATEGORY_ORDER
    from mod_editor.core.apf2k8_play_codec import Book
    from mod_editor.apf_studio.play_designer_qt import PlayDesignDialog, FormationDesignDialog, CpuCallDialog
    app = QApplication.instance() or QApplication([])
    captured = {"dialogs": [], "crashes": [], "steps": []}
    def record(kind):
        def called(*values, **_kwargs):
            captured["dialogs"].append({"kind": kind, "text": " | ".join(map(str, values[1:3]))})
            return QMessageBox.Cancel
        return called
    for kind in ("warning", "critical", "information", "question", "about"):
        setattr(QMessageBox, kind, staticmethod(record(kind)))
    def modal(box, *_args):
        captured["dialogs"].append({"kind": "exec", "text": box.windowTitle()+" | "+box.text()})
        return QMessageBox.Cancel
    QMessageBox.exec_ = modal
    QMessageBox.exec = modal
    QMessageBox.open = modal
    QMessageBox.show = modal
    def hook(kind, value, tb):
        captured["crashes"].append("".join(traceback.format_exception(kind, value, tb)))
    sys.excepthook = hook
    with tempfile.TemporaryDirectory(prefix="astra-apf-gui-") as directory:
        root = Path(directory)
        facade = ApfStudioFacade(cache_root=root / "cache")
        window = ApfStudioMainWindow(facade, offer_recovery=False)
        def pump(label, timeout=300):
            deadline = time.monotonic()+timeout
            quiet = 0
            while time.monotonic() < deadline:
                app.processEvents()
                if captured["dialogs"] or captured["crashes"]:
                    raise AssertionError(json.dumps(captured, indent=2))
                busy = window._workers or window._idle_callbacks or window._pending_source_load
                quiet = 0 if busy else quiet + 1
                if quiet >= 10:
                    captured["steps"].append(label)
                    print("GUI_REPLAY", label, flush=True)
                    return
                time.sleep(0.02)
            raise TimeoutError(label)
        def navigate(category):
            row = APF_CATEGORY_ORDER.index(category)
            window.navigation.setCurrentRow(row)
            window._activate_page(row)
            pump(category.value)
            return window._pages[category]
        try:
            window.show()
            pump("empty window")
            window._load_source_path(args.source)
            pump("retail source loaded")
            assert facade.source_ready
            page = navigate(ApfCategory.PLAYBOOKS)
            tabs = page.workspace_tabs
            assert tabs.count() == 10, tabs.count()
            for route, widget in (
                ("play-designer", page.play_designer),
                ("coverage-geometry", page.coverage_geometry),
                ("book-identity", page.book_identity),
                ("cpu-audibles", page.playbook_playcall),
                ("raw-assets", page.assets),
            ):
                page.open_workspace(route)
                pump(route)
                assert tabs.currentWidget() is widget
            assert page.coverage_geometry.table.rowCount() == 368
            coverage_panel = page.coverage_geometry
            index = next(i for i, r in enumerate(coverage_panel._rows) if r["node_index"] == 3223)
            coverage_panel.table.selectRow(index)
            coverage_panel.knobs["lateral_extent_yards"].setValue(8)
            coverage_panel.apply_button.click()
            pump("Coverage Apply through panel")
            assert facade.session.coverage_context()[2][0].lateral_extent_yards == 8
            coverage_panel.revert_all_button.click()
            pump("Coverage Revert through panel")
            assert not facade.session.coverage_context()[2]
            body, _plan, books = facade.play_design_context()
            book = Book.from_bytes(body)
            for dialog in (PlayDesignDialog(book, 586, window), FormationDesignDialog(book, 163, window), CpuCallDialog(book, books, window)):
                assert dialog.request()
                dialog.close()
                dialog.deleteLater()
            pump("all authoring dialogs instantiated")
            playcall = page.playbook_playcall
            page.open_workspace("cpu-audibles")
            playcall.preview()
            pump("CPU audible preview")
            assert playcall.personnel_table.rowCount() == 28
            assert playcall.stage_button.isEnabled()
            playcall.stage()
            pump("CPU audibles staged")
            assert window._document_dirty and facade.modified_count
            project = root / "gui-replay.apf2k8mod"
            facade.save_project(project)
            before = tuple(facade.session.modifications)
            facade.load_project(project)
            assert [(m.asset_id, m.replacement_sha256) for m in facade.session.modifications] == [
                (m.asset_id, m.replacement_sha256) for m in before]
            page.refresh()
            pump("Save Project and reopen")
            playcall.preview()
            pump("existing-book edits refuse rebalance")
            assert not playcall.stage_button.isEnabled()
            assert playcall.personnel_table.rowCount() == 28
            logo = navigate(ApfCategory.LOGOS)
            assert any(button.text() == "Import PS3 bundle…" for button in logo.findChildren(QPushButton))
            field = navigate(ApfCategory.FIELD_ART)
            assert field.editor.ps3_bundle_button.text() == "Import PS3 bundle…"
            page.book_identity.load_path(args.source / "0A")
            pump("Book Identity team table")
            assert page.book_identity.table.rowCount() == 80
            captured["tabs"] = [tabs.tabText(i) for i in range(tabs.count())]
            captured["status"] = "APF_GUI_REPLAY_PASS"
        except BaseException:
            captured["crashes"].append(traceback.format_exc())
            captured["status"] = "APF_GUI_REPLAY_FAIL"
        finally:
            # Drain workers before removing the private cache, including failure paths.
            deadline = time.monotonic()+300
            while window._workers and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            window._allow_close = True
            window.close()
            app.processEvents()
            # Close alone hides QWidget. Destroy its QSS proxies, pixmaps and
            # deferred dialogs while QApplication still exists.
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    text = json.dumps(captured, indent=2)+"\n"
    if args.receipt:
        args.receipt.write_text(text)
    print(text)
    return int(bool(captured["dialogs"] or captured["crashes"]))


if __name__ == "__main__":
    raise SystemExit(main())
