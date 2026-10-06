"""Select frozen league artwork for a customized full Studio build."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from mod_editor.core import modpack as m, modpack_files as f


class SourceSelection(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = f._path(project)
        self.document = json.loads(m._read_small_file(self.project, "league project", m.MAX_MANIFEST_BYTES))
        m._require(isinstance(self.document, dict) and isinstance(self.document.get("edits"), list), "League project has no edits")
        m._require(len(self.document["edits"]) <= 20000 and all(isinstance(edit, dict) for edit in self.document["edits"]),
                   "League project has invalid or too many edits")
        self.setWindowTitle("Choose SOFTDRINK league artwork")
        self.resize(760, 600)
        layout = QVBoxLayout(self)
        label = QLabel("Check the artwork to include in your full build. Build options also control stadiums, gameplay and the roster.")
        label.setWordWrap(True)
        layout.addWidget(label)
        search = QLineEdit()
        search.setPlaceholderText("Filter by artwork family, team code or player…")
        layout.addWidget(search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Artwork", "Source"])
        layout.addWidget(self.tree)
        groups = {}
        self.items = []
        for index, edit in enumerate(self.document["edits"]):
            kind = str(edit.get("kind", "other"))
            if kind not in groups:
                group = QTreeWidgetItem(self.tree, [kind.replace("_", " ")])
                group.setFlags(group.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsTristate)
                groups[kind] = group
            text = ", ".join(f"{key}: {edit[key]}" for key in ("asset_code", "side", "variant", "family", "portrait_id", "texture", "digit") if key in edit)
            image = next((str(edit[k]) for k in ("png", "clean_png", "source") if edit.get(k)), "")
            item = QTreeWidgetItem(groups[kind], [text or f"Edit {index + 1}", Path(image).name])
            item.setToolTip(0, json.dumps(edit, indent=1))
            item.setToolTip(1, image)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            self.items.append(item)
        self.tree.resizeColumnToContents(0)
        def filter_items(text):
            query = text.casefold()
            for item in self.items:
                item.setHidden(query not in (item.parent().text(0) + " " + item.text(0) + " " + item.text(1)).casefold())
            for group in groups.values():
                group.setHidden(all(group.child(i).isHidden() for i in range(group.childCount())))
                group.setExpanded(bool(query))
        search.textChanged.connect(filter_items)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self, output, *, overwrite=False):
        edits = [edit for edit, item in zip(self.document["edits"], self.items) if item.checkState(0) == Qt.Checked]
        m._require(edits, "Choose at least one edit, or turn off Include SOFTDRINK league artwork in Build.")
        with f._transaction(output, (self.project,), overwrite) as part:
            part.write_text(json.dumps(dict(self.document, edits=edits), indent=2, sort_keys=True) + "\n",
                            encoding="utf-8", newline="\n")
        return len(edits)
