"""CPU audible balancing, personnel receipts, and pass-fetch patch export.

Standalone workspace panel. Protected gui/build/registry integration is given
in WIRING.md. All book changes use the existing facade and project payload.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from mod_editor.core import apf2k8_audibles as audibles
from mod_editor.core import apf2k8_playcall_patch as code_patch
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
        return {"outer": outer, "changes": (), "existing": existing,
                "before": audibles.audible_census(original, catalog), "after": census,
                "personnel": compiled.report["personnel_availability"],
                "stageable": False, "transport": compiled.report,
                "message": ("Current project already balances every eligible record." if balanced else
                            "Build or revert this book's current edits before balancing audibles.")}
    plan = audibles.plan_audibles(original, catalog)
    compiled = splb.build_book_patch(index, plan.changes) if plan.changes else None
    return {"outer": outer, "changes": plan.changes, "existing": (),
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
        self._generation = 0
        self._busy = False
        root = QVBoxLayout(self)
        intro = QLabel("Balance CPU audibles using plays already in each formation. "
                       "Records without both a run and a pass are listed below. "
                       "Personnel and CPU behavior remain unwitnessed in game.")
        intro.setWordWrap(True); root.addWidget(intro)
        row = QHBoxLayout()
        self.book_picker = QComboBox()
        for outer in audibles.CPU_OFFENSE_BOOKS:
            self.book_picker.addItem(splb.STOCK_BOOKS[outer], outer)
        self.book_picker.setAccessibleName("CPU offensive book")
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
        self.patch_button = QPushButton("Export TE bias for pass fetches…")
        self.patch_button.clicked.connect(self.export_patch)
        root.addWidget(self.patch_button)
        note = QLabel("Patch experiment: applies to pass fetches at every down, including user calls. "
                      "The main CPU weighted picker uses another path. Choose a flat BASE or reconstructed "
                      "TU 1.1 image; export a Xenia patch into a separate file. "
                      "Personnel selection and Subs can still choose a lineup without a TE.")
        note.setWordWrap(True); root.addWidget(note)
        self.set_context()

    def _source(self):
        source = getattr(self.facade, "source", None)
        return getattr(source, "index_0a", None)

    def set_context(self, *args):
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

        def operation(progress):
            return prepare_book(Path(index), outer, existing)

        def done(result):
            if generation != self._generation or self._source() != index:
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

    def export_patch(self):
        source, _ = QFileDialog.getOpenFileName(self, "Choose flat BASE or reconstructed TU 1.1 image", "", "Flat image (*.pe);;All files (*)")
        if not source:
            return
        output, _ = QFileDialog.getSaveFileName(self, "Export TE bias for pass fetches", "54540807-pass-fetch-te.patch.toml", "Xenia patch (*.patch.toml)")
        if not output:
            return
        def done(receipt):
            self.notice.setText(f"Exported {receipt['image']} pass-fetch patch. Status: unwitnessed. "
                                "Disable it by removing the exported patch or setting is_enabled = false.")
        self.run_task("Export TE bias for pass fetches", lambda progress: code_patch.write_patch(Path(source), Path(output)), done, False)
