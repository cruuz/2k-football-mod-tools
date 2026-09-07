"""Read-only review for the Build naming option in Text & Team Identity."""
from __future__ import annotations

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtWidgets import QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

from mod_editor.core import nfl2k5_modern_naming as naming


class ModernNamingModel(QAbstractTableModel):
    HEADERS = ("Where", "Before", "After", "Text limit", "Source ID")
    KEYS = ("location", "before", "after", "character_limit", "asset_id")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.DisplayRole:
            return str(row[self.KEYS[index.column()]])
        if role == Qt.ToolTipRole:
            return (f"{row['before']}\n\nAfter: {row['after']}\n\n"
                    f"{row.get('location_evidence', '')}\n"
                    f"{row['allocation_bytes']} bytes; "
                    + ("uses a documented short form" if row["fallback"] else "full name fits"))
        return None


class ModernNamingPanel(QWidget):
    """Optional host callback returns {enabled, rows} after source preflight.

    Without that callback this remains an explicitly unverified manifest preview,
    so a protected-facade wiring omission cannot masquerade as an enabled Build.
    """
    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.model = ModernNamingModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        for column in (0, 1, 2):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)
        self.career_note = QLabel(
            "MyCareer menu and title: MyCareer. The career feature installs those screens. "
            "Practice, Tournament, Season, Coach's Desk and The Crib keep their names. "
            "Team Create keeps its name; MyTeam is a card mode.")
        self.career_note.setWordWrap(True)
        layout.addWidget(self.career_note)
        self.reload()

    def reload(self):
        try:
            provider = getattr(self.host, "modern_naming_preview", None)
            if callable(provider):
                snapshot = provider()
                rows = snapshot["rows"]
                enabled = snapshot["enabled"]
                if not all(row["source_verified"] for row in rows):
                    raise ValueError("Naming source has not been verified")
                label = "On in Build" if enabled else "Off in Build; original names will be used"
            else:
                rows = naming.preview_rows()
                label = "Mapping preview only; source and Build selection are not connected"
            self.model.set_rows(rows)
            changed = sum(row["before"] != row["after"] for row in rows)
            self.summary.setText(f"{label}. {len(rows)} strings reviewed, {changed} changes. "
                                 "Experimental / Unwitnessed.")
            self.table.resizeRowsToContents()
            labels = {cell["role"]: naming.career_text(cell["role"]).decode("utf-16le").rstrip("\0")
                      for cell in naming.manifest()["career_labels"]}
            self.career_note.setText(
                f"MyCareer menu: {labels['menu_row']}. Title: {labels['screen_title']}. "
                "The career feature installs those screens. Practice, Tournament, Season, "
                "Coach's Desk and The Crib keep their names. Team Create keeps its name; MyTeam is a card mode.")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.model.set_rows([])
            self.summary.setText(f"Modern names unavailable: {exc}")
