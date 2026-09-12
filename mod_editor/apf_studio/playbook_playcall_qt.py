"""CPU audible balancing, personnel receipts, and pass-fetch patch export.

Standalone workspace panel. Protected gui/build/registry integration is given
in WIRING.md. All book changes use the existing facade and project payload.
"""
from __future__ import annotations

from pathlib import Path
import tempfile

from PyQt5.QtCore import QStandardPaths, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem, QMessageBox,
                             QVBoxLayout, QWidget)

from mod_editor.core import apf2k8_audibles as audibles
from mod_editor.core import apf2k8_playcall_patch as code_patch
from mod_editor.core import apf2k8_xex as game_image
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from mod_editor.core.errors import ValidationError


def prepare_book(index: Path, outer: int, existing=()) -> dict:
    """Preview the current project without silently replacing existing edits."""
    original = splb.read_book(index, outer)
    catalog = audibles.play_catalog(read_master_play_body(index))
    existing = tuple(c for c in existing if c.outer_index == outer)
    if existing:
        compiled = splb.build_book_patch(index, existing)
        current = splb.parse_book(compiled.replacement, outer)
        census = audibles.audible_census(current, catalog)
        balanced = all(row["balanced"] for row in census if row["possible"])
        return {"outer": outer, "book_name": original.name, "changes": (), "existing": existing,
                "before": audibles.audible_census(original, catalog), "after": census,
                "personnel": compiled.report["personnel_availability"],
                "stageable": False, "transport": compiled.report,
                "message": ("Current project already balances every eligible record." if balanced else
                            "Build or revert this book's current edits before balancing audibles.")}
    if splb.BOOK_SIDES.get(original.name) == "defense":
        census = audibles.audible_census(original, catalog)
        personnel = splb.personnel_availability(original)
        return {"outer": outer, "book_name": original.name, "changes": (), "existing": (), "before": census,
                "after": census, "stageable": False, "transport": {},
                "personnel": {"before": personnel, "after": personnel},
                "message": "Defensive book: review personnel here; edit plays and audibles in Fine-tune."}
    plan = audibles.plan_audibles(original, catalog)
    compiled = splb.build_book_patch(index, plan.changes) if plan.changes else None
    return {"outer": outer, "book_name": original.name, "changes": plan.changes, "existing": (),
            "before": plan.report["before"], "after": plan.report["after"],
            "stageable": bool(plan.changes), "transport": compiled.report if compiled else {},
            "personnel": (compiled.report["personnel_availability"] if compiled else
                          {"before": splb.personnel_availability(original),
                           "after": splb.personnel_availability(original)}),
            "message": f"{len(plan.changes)} tag moves; {len(plan.report['impossible_records'])} records lack a run or pass."}


class ApfPlaycallPanel(QWidget):
    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task):
        super().__init__()
        self.facade, self.run_task = facade, run_task
        self._preview = None
        self._catalog_index = None
        self._generation = 0
        self._busy = False
        self._title_update = None
        root = QVBoxLayout(self)
        intro = QLabel("Balance CPU audibles using plays already in each formation. "
                       "Records without both a run and a pass are listed below. "
                       "Personnel and CPU behavior remain unwitnessed in game.")
        intro.setWordWrap(True); root.addWidget(intro)
        row = QHBoxLayout()
        self.book_picker = QComboBox()
        for outer, name in getattr(facade, "book_choices", splb.STOCK_BOOKS).items():
            self.book_picker.addItem(name, outer)
        self.book_picker.setAccessibleName("CPU playbook")
        self.preview_button = QPushButton("Preview CPU audibles and personnel")
        self.stage_button = QPushButton("Stage balanced CPU audibles")
        self.preview_button.clicked.connect(self.preview)
        self.stage_button.clicked.connect(self.stage)
        self.book_picker.currentIndexChanged.connect(self.set_context)
        for widget in (self.book_picker, self.preview_button, self.stage_button):
            row.addWidget(widget)
        root.addLayout(row)
        self.notice = QLabel(); self.notice.setWordWrap(True); root.addWidget(self.notice)
        self.audible_table = QTableWidget(0, 5)
        self.audible_table.setHorizontalHeaderLabels(("Record / formation", "Before run / pass",
                                                      "After run / pass", "Audible slots", "Result"))
        self.audible_table.setAccessibleName("CPU audible preview")
        root.addWidget(self.audible_table)
        self.personnel_table = QTableWidget(0, 5)
        self.personnel_table.setHorizontalHeaderLabels(("Personnel category", "Row", "Records before / after",
                                                        "Advertised before / after", "TE in stock MASTER"))
        self.personnel_table.setAccessibleName("Personnel availability before and after")
        root.addWidget(self.personnel_table)
        patch_row = QHBoxLayout()
        self.image_picker = QComboBox()
        self.image_picker.addItem("Choose game folder", "folder")
        self.image_picker.addItem("Choose flat image (expert)", "flat")
        self.image_picker.setAccessibleName("Pass-fetch patch input")
        self.update_button = QPushButton("Choose Title Update 1.1…")
        self.update_button.clicked.connect(self.choose_title_update)
        self.auto_update_button = QPushButton("Detect installed update")
        self.auto_update_button.clicked.connect(self.reset_title_update)
        self.image_picker.currentIndexChanged.connect(self._update_input_controls)
        for widget in (self.image_picker, self.update_button, self.auto_update_button):
            patch_row.addWidget(widget)
        root.addLayout(patch_row)
        self.update_notice = QLabel("Title Update: detect the studio's configured update or installed Xenia content.")
        self.update_notice.setWordWrap(True)
        root.addWidget(self.update_notice)
        self.patch_button = QPushButton("Install TE bias for last-resort fetch…")
        self.patch_button.clicked.connect(self.export_patch)
        root.addWidget(self.patch_button)
        self.patch_note = QLabel(
            "The studio reads your game's executable, checks it is the retail BASE or Title Update 1.1, "
            "and installs the chosen patch in Xenia’s patches folder after your consent. If your update is installed elsewhere, "
            "choose its content file above. Your game files are only read. "
            "Last-resort fetch only, at every down including user calls. This is not a CPU play-calling fix. "
            "The main CPU weighted picker uses another path. Personnel selection and Subs can still "
            "choose a lineup without a TE. In-game behavior is unwitnessed.")
        self.patch_note.setWordWrap(True); root.addWidget(self.patch_note)
        self.patch_notice = QLabel("Choose game folder to check your executable, then review Xenia patch installation.")
        self.patch_notice.setWordWrap(True); root.addWidget(self.patch_notice)
        row = QHBoxLayout()
        self.install_existing_button = QPushButton("Install an exported pass-fetch patch…")
        self.remove_patch_button = QPushButton("Remove Studio pass-fetch patch")
        self.config_button = QPushButton("Choose Xenia config…")
        self.patch_status_button = QPushButton("Check patch status")
        for widget in (self.install_existing_button, self.remove_patch_button, self.config_button, self.patch_status_button):
            row.addWidget(widget)
        self.install_existing_button.clicked.connect(self.install_existing_patch)
        self.remove_patch_button.clicked.connect(self.remove_patch)
        self.config_button.clicked.connect(self.choose_xenia_config)
        self.patch_status_button.clicked.connect(self.refresh_patch_status)
        root.addLayout(row)
        self.set_context()

    def _source(self):
        source = getattr(self.facade, "source", None)
        return getattr(source, "index_0a", None)

    def set_context(self, *args):
        if self._catalog_index != self._source():
            self._catalog_index = self._source()
            selected = self.book_picker.currentText()
            self.book_picker.blockSignals(True)
            self.book_picker.clear()
            for outer, name in getattr(self.facade, "book_choices", splb.STOCK_BOOKS).items():
                self.book_picker.addItem(name, outer)
            if self.book_picker.findText(selected) >= 0:
                self.book_picker.setCurrentIndex(self.book_picker.findText(selected))
            self.book_picker.blockSignals(False)
        self._generation += 1
        self._preview = None
        self.stage_button.setEnabled(False)
        self.preview_button.setEnabled(bool(getattr(self.facade, "source_ready", False)) and not self._busy)
        self.audible_table.setRowCount(0); self.personnel_table.setRowCount(0)
        self.notice.setText("Preview a CPU book to see audible slots and personnel availability.")

    def set_busy(self, busy):
        self._busy = busy
        self.book_picker.setEnabled(not busy)
        self.preview_button.setEnabled(not busy and bool(getattr(self.facade, "source_ready", False)))
        self.stage_button.setEnabled(not busy and bool(self._preview and self._preview["stageable"]))
        self.patch_button.setEnabled(not busy)
        self.image_picker.setEnabled(not busy)
        for widget in (self.install_existing_button, self.remove_patch_button, self.config_button, self.patch_status_button):
            widget.setEnabled(not busy)
        self._update_input_controls()

    def _update_input_controls(self, *args):
        enabled = not self._busy and self.image_picker.currentData() == "folder"
        self.update_button.setEnabled(enabled)
        self.auto_update_button.setEnabled(enabled)

    def choose_title_update(self):
        source, _ = QFileDialog.getOpenFileName(
            self, "Choose installed Title Update 1.1 content", "",
            "Title Update content (TU_* *.xexp);;All files (*)")
        if source:
            self._title_update = Path(source)
            self.update_notice.setText(f"Title Update: {source}")

    def reset_title_update(self):
        self._title_update = None
        self.update_notice.setText("Title Update: detect the studio's configured update or installed Xenia content.")

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                from PyQt5.QtCore import Qt
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                table.setItem(row, column, item)
        table.resizeColumnsToContents()

    def preview(self):
        index = self._source()
        if index is None or not getattr(self.facade, "source_ready", False):
            return
        self._preview = None; self.stage_button.setEnabled(False)
        self._generation += 1
        generation, outer = self._generation, int(self.book_picker.currentData())
        existing = self.facade.staged_splb_changes()
        scheme_snapshot = self._scheme_snapshot()

        def operation(progress):
            result = prepare_book(Path(index), outer, existing)
            if scheme_snapshot is not None:
                from . import scheme_service
                recipes = scheme_service.read_profile(scheme_snapshot)
                if any(recipe["book_type"] == result["book_name"] for recipe in recipes):
                    result["stageable"] = False
                    result["message"] = "Build or revert this book's staged Scheme Presets before balancing audibles."
            return result

        def done(result):
            if (generation != self._generation or self._source() != index
                    or scheme_snapshot != self._scheme_snapshot()):
                return
            self._preview = result
            self.stage_button.setEnabled(result["stageable"] and not self._busy)
            self.notice.setText(result["message"] + " Preview verified offline; in-game result unwitnessed.")
            self._fill(self.audible_table, [(
                f"{a['record_index']} / {a['formation_index']}",
                f"{b['counts']['run']} / {b['counts']['pass']}",
                f"{a['counts']['run']} / {a['counts']['pass']}",
                ", ".join(f"{s['tag']}: {s['kind']}" for s in a["slots"]), a["reason"])
                for b, a in zip(result["before"], result["after"])])
            self._fill(self.personnel_table, [(
                a["name"], a["personnel_row"], f"{len(b['record_indices'])} / {len(a['record_indices'])}",
                f"{b['advertised']} / {a['advertised']}", "Yes" if a["te_offense"] else "No")
                for b, a in zip(result["personnel"]["before"]["categories"],
                                result["personnel"]["after"]["categories"])])
        self.run_task("Preview CPU audibles and personnel", operation, done, False)

    def stage(self):
        if not self._preview or not self._preview["stageable"]:
            return
        preview, index, generation = self._preview, self._source(), self._generation

        def operation(progress):
            if index != self._source() or generation != self._generation:
                raise ValidationError("Source changed; preview this book again")
            existing = tuple(c for c in self.facade.staged_splb_changes() if c.outer_index == preview["outer"])
            if existing != preview["existing"]:
                raise ValidationError("This book's staged edits changed; preview it again")
            profile = self._scheme_snapshot()
            if profile is not None:
                from . import scheme_service
                if any(r["book_type"] == preview["book_name"]
                       for r in scheme_service.read_profile(profile)):
                    raise ValidationError("Build or revert this book's Scheme Presets before balancing audibles")
            # Rebuild from the source immediately before staging; no stale plan.
            fresh = prepare_book(Path(index), preview["outer"], existing)
            if fresh["changes"] != preview["changes"]:
                raise ValidationError("Book data changed; preview it again")
            return self.facade.stage_splb_membership(fresh["changes"], progress,
                                                    replace_outer=preview["outer"])

        def done(result):
            if generation == self._generation:
                self._preview = None; self.stage_button.setEnabled(False)
                self.modifiedChanged.emit()
                self.notice.setText("Balanced audible tags staged. Save Project or use the studio Build action. "
                                    "Records lacking a run or pass remain listed; CPU behavior is unwitnessed.")
        self.run_task("Stage balanced CPU audibles", operation, done, True)

    def _scheme_snapshot(self):
        session = getattr(self.facade, "session", None)
        return next((m for m in getattr(session, "modifications", ())
                     if m.kind == "apf_scheme_presets"), None)

    def refresh_patch_status(self):
        try:
            self.patch_notice.setText(self.facade.xenia_patch_status()["message"])
        except (AttributeError, ValueError, OSError) as exc:
            self.patch_notice.setText(f"Configure Xenia in the launcher first. {exc}")

    def choose_xenia_config(self):
        source, _ = QFileDialog.getOpenFileName(self, "Choose the Xenia config to use at launch", "", "Xenia config (*.toml)")
        if source:
            try:
                self.facade.configure_xenia_patch_config(Path(source))
                self.refresh_patch_status()
            except (ValueError, OSError) as exc:
                self.patch_notice.setText(str(exc))

    def _install_consent(self):
        try:
            status = self.facade.xenia_patch_status()
            if "patch_path" not in status:
                self.patch_notice.setText(status["message"])
                return False
            answer = QMessageBox.question(
                self, "Install and enable the pass-fetch experiment?",
                f"Install the selected patch at:\n{status['patch_path']}\n\n"
                f"Set apply_patches = true in:\n{status['config_path']}\n\n"
                "This also enables any other patches marked enabled in Xenia’s patches folder. "
                "The Studio will use this config when launching Xenia. Restart Xenia after changing patches. "
                "You can remove this patch here. Last-resort fetch only; not a CPU play-calling fix. "
                "In-game result unwitnessed.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return answer == QMessageBox.Yes
        except (AttributeError, ValueError, OSError) as exc:
            self.patch_notice.setText(f"Configure Xenia first. {exc}")
            return False

    def install_existing_patch(self):
        source, _ = QFileDialog.getOpenFileName(self, "Choose a Studio pass-fetch patch", "", "Xenia patch (*.patch.toml)")
        if not source or not self._install_consent():
            return
        try:
            self.patch_notice.setText(self.facade.install_xenia_patch(Path(source), consent=True)["message"])
        except (ValueError, OSError) as exc:
            self.patch_notice.setText(str(exc))

    def remove_patch(self):
        try:
            result = self.facade.remove_xenia_patch()
            self.patch_notice.setText(result["message"] + " Restart Xenia. Other patches and the global setting are unchanged.")
        except (AttributeError, ValueError, OSError) as exc:
            self.patch_notice.setText(str(exc))

    def export_patch(self):
        folder_mode = self.image_picker.currentData() == "folder"
        built = getattr(getattr(self.facade, "last_build", None), "output_game", None)
        initial = built or getattr(getattr(self.facade, "source", None), "game_root", None)
        if folder_mode:
            source = QFileDialog.getExistingDirectory(self, "Choose game folder", str(initial or ""))
        else:
            source, _ = QFileDialog.getOpenFileName(
                self, "Choose flat image (expert)", "", "Flat image (*.pe);;All files (*)")
        if not source:
            return
        settings = getattr(getattr(self.facade, "launcher", None), "settings", None)
        update = (self._title_update or getattr(settings, "title_update_path", None)) if folder_mode else None
        xenia = getattr(settings, "xenia_path", None)
        user_storage = tuple(Path(path) / "Xenia" for kind in
                             (QStandardPaths.DocumentsLocation, QStandardPaths.GenericDataLocation)
                             if (path := QStandardPaths.writableLocation(kind)))
        self.set_busy(True)
        self.patch_notice.setText("Reading your game's executable and checking retail BASE / Title Update 1.1. Game files are only read.")

        def prepare(progress):
            try:
                roots = game_image.xenia_content_roots(xenia, user_storage=user_storage) if folder_mode and xenia else ()
                image, receipt = game_image.derive_image(Path(source), title_update=update,
                                                         content_roots=roots, progress=progress)
                return code_patch.compile_patch(image), receipt, None
            except (ValidationError, OSError) as exc:
                return None, None, str(exc)

        def prepared(result):
            self.set_busy(False)
            patch, receipt, error = result
            if error:
                self.patch_notice.setText(error)
                return
            name = "retail BASE" if patch.profile.name == "base" else "Title Update 1.1"
            if not self._install_consent():
                self.patch_notice.setText(f"Checked {name}; installation cancelled. No patch or config written.")
                return
            self.set_busy(True)

            def write(progress):
                try:
                    with tempfile.TemporaryDirectory(prefix="apf-pass-fetch-") as temporary:
                        output = Path(temporary) / "pass-fetch.patch.toml"
                        code_patch.export_patch(patch, output, receipt)
                        return self.facade.install_xenia_patch(output, consent=True), None
                except (ValidationError, ValueError, OSError) as exc:
                    return None, str(exc)

            def done(result):
                self.set_busy(False)
                installed, error = result
                self.patch_notice.setText(error if error else installed["message"] + " Restart Xenia to load the patch.")
            self.run_task("Write pass-fetch Xenia patch", write, done, False)

        self.run_task("Read game executable for pass-fetch patch", prepare, prepared, False)
