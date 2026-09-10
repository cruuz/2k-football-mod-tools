"""Visual package browser. All archive decoding and staging runs in workers."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QImage, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .team_art import FAMILIES, STATUS, package_modifications, thumbnail


class LayerFileButton(QPushButton):
    pathChanged = pyqtSignal(object)

    def __init__(self, name):
        super().__init__("Choose PNG…")
        self.name, self.path = name, None
        self.setAcceptDrops(True)
        self.setObjectName("secondaryButton")
        self.setAccessibleName(f"Choose {name} PNG")
        self.clicked.connect(self.choose)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, f"Choose {self.name}", "", "PNG images (*.png)")
        if path:
            self.set_path(Path(path))

    def set_path(self, path):
        self.path = path
        self.setText(path.name)
        self.setToolTip(str(path))
        self.pathChanged.emit(path)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.casefold() == ".png":
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self.set_path(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()


class TeamArtReplaceDialog(QDialog):
    """Each PNG has an explicit semantic destination; pairs cannot be incomplete."""
    def __init__(self, package, parent=None):
        super().__init__(parent)
        self.package = package
        self.setWindowTitle(f"Replace {package.label} · entry {package.outer_index}")
        self.resize(800, 530)
        layout = QVBoxLayout(self)
        self.message = QLabel("Choose or drop a PNG onto each layer. The package and linked cache are resolved for you.")
        self.message.setObjectName("validationBanner")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        table = QTableWidget(len(package.layers), 4)
        table.setHorizontalHeaderLabels(("Layer", "PNG dimensions", "Codec", "Replacement PNG"))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.inputs = {}
        for row, layer in enumerate(package.layers):
            for column, text in enumerate((layer.name, f"{layer.width} × {layer.height}", layer.codec)):
                table.setItem(row, column, QTableWidgetItem(text))
            button = LayerFileButton(layer.name)
            self.inputs[layer.name] = button
            button.pathChanged.connect(self.validate)
            table.setCellWidget(row, 3, button)
        layout.addWidget(table, 1)
        note = QLabel("Crests keep six separate colour masks across both layers and update Team Select too."
                      if package.family == "logo" else
                      "Choose any digits to replace; all staged digits share one package budget, checked before staging."
                      if package.family == "number" else "The selected layers are staged together as one Undo action.")
        note.setWordWrap(True)
        note.setToolTip(STATUS)
        layout.addWidget(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Stage replacement")
        self.buttons.button(QDialogButtonBox.Ok).setObjectName("primaryButton")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.validate()

    def paths(self):
        return {name: button.path for name, button in self.inputs.items() if button.path is not None}

    def validate(self, *_args):
        paths = self.paths()
        complete = bool(paths) and (self.package.family == "number" or len(paths) == len(self.inputs))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(complete)
        self.message.setText(f"{len(paths)} of {len(self.inputs)} layers selected. " +
                             ("Ready to check and stage." if complete else "Choose the PNGs for the named layers below."))
        self.message.setProperty("valid", complete)
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        return complete

    def accept(self):
        if self.validate():
            super().accept()


class TeamArtBrowser(QWidget):
    modifiedChanged = pyqtSignal()

    def __init__(self, facade, run_task, parent=None):
        super().__init__(parent)
        self.facade, self.run_task = facade, run_task
        self._packages, self._items, self._session = (), {}, None
        self._epoch, self._decoding, self._loading = 0, False, False
        self._queue = []
        self._thumbs = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search team labels, entries or packages…")
        self.search.setAccessibleName("Search Team Art")
        self.search.setProperty("studioSearch", True)
        self.search.setClearButtonEnabled(True)
        self.family = QComboBox()
        for key, label in FAMILIES:
            self.family.addItem(label, key)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.family)
        layout.addLayout(toolbar)
        filters = QHBoxLayout()
        self.writable = QCheckBox("Writable only")
        self.staged = QCheckBox("Staged in this project")
        self.retail = QCheckBox("Used by a retail team")
        self.retail.setToolTip("Proved built-in team selector assignments. Unproved endzone assignments are excluded.")
        for check in (self.writable, self.staged, self.retail):
            filters.addWidget(check)
            check.toggled.connect(self.refresh)
        filters.addStretch(1)
        self.count = QLabel("Load your game to browse Team Art.")
        self.count.setObjectName("countPill")
        filters.addWidget(self.count)
        layout.addLayout(filters)
        splitter = QSplitter(Qt.Horizontal)
        self.grid = QListWidget()
        self.grid.setObjectName("teamArtGrid")
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setIconSize(QSize(208, 128))
        self.grid.setGridSize(QSize(230, 192))
        self.grid.setSpacing(6)
        self.grid.setWordWrap(True)
        self.grid.setSelectionMode(QAbstractItemView.SingleSelection)
        self.grid.setAccessibleName("Team Art packages")
        self.grid.setTextElideMode(Qt.ElideRight)
        self.grid.verticalScrollBar().valueChanged.connect(lambda _value: self._decode_next())
        self.grid.viewport().installEventFilter(self)
        splitter.addWidget(self.grid)
        inspector = QFrame()
        inspector.setObjectName("inspectorDetail")
        inspector.setMinimumWidth(280)
        inspector.setMaximumWidth(340)
        detail = QVBoxLayout(inspector)
        self.title = QLabel("Choose artwork")
        self.title.setObjectName("panelTitle")
        self.title.setWordWrap(True)
        self.preview = QLabel("Select a thumbnail to inspect its layers.")
        self.preview.setObjectName("imagePreview")
        self.preview.setFixedSize(260, 166)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setWordWrap(True)
        self.layers = QLabel("")
        self.layers.setTextFormat(Qt.PlainText)
        self.layers.setWordWrap(True)
        self.layers.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layers.setFocusPolicy(Qt.StrongFocus)
        detail.addWidget(self.title)
        detail.addWidget(self.preview, 0, Qt.AlignHCenter)
        layer_scroll = QScrollArea()
        layer_scroll.setWidgetResizable(True)
        layer_scroll.setWidget(self.layers)
        detail.addWidget(layer_scroll, 1)
        self.replace_button = QPushButton("Replace…")
        self.replace_button.setObjectName("primaryButton")
        self.replace_button.setEnabled(False)
        self.replace_button.clicked.connect(self.replace)
        detail.addWidget(self.replace_button)
        self.revert_button = QPushButton("Revert package")
        self.revert_button.setObjectName("secondaryButton")
        self.revert_button.setEnabled(False)
        self.revert_button.clicked.connect(self.revert)
        detail.addWidget(self.revert_button)
        splitter.addWidget(inspector)
        splitter.setStretchFactor(0, 1)
        layout.addWidget(splitter, 1)
        self.status = QLabel("Load your game, then choose a family and a thumbnail.")
        self.status.setObjectName("mutedLabel")
        self.status.setToolTip(STATUS)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.search.textChanged.connect(self.refresh)
        self.family.currentIndexChanged.connect(self.refresh)
        self.grid.currentItemChanged.connect(self.inspect)
        self.grid.itemActivated.connect(lambda _item: self.layers.setFocus(Qt.ShortcutFocusReason))

    def set_context(self):
        session = getattr(self.facade, "session", None) if self.facade.source_ready else None
        if session is self._session and self._packages:
            self.refresh()
            return
        if self._loading and session is self._session:
            return
        self._epoch += 1
        self._session = session
        self._packages, self._thumbs = (), {}
        self.refresh()
        if session is None:
            self._loading = False
            return
        self._loading = True
        def loaded(packages):
            if self.facade.session is not session or self._session is not session:
                return
            self._loading = False
            self._packages = packages
            self.refresh()
        self.run_task("Indexing Team Art", self.facade.team_art_packages, loaded, False)

    def refresh(self, *_args):
        self._epoch += 1
        selected = self.selected_package()
        selected_key = selected.key if selected else None
        self.grid.clear()
        self._items = {}
        self._queue = []
        edits = tuple(self._session.modifications) if self._session is not None else ()
        family = self.family.currentData()
        query = self.search.text().strip().casefold()
        for package in self._packages:
            if package.family != family or query not in package.search_text:
                continue
            modified = bool(package_modifications(package, edits))
            if self.writable.isChecked() and not package.writable or self.staged.isChecked() and not modified or self.retail.isChecked() and not package.retail_teams:
                continue
            text = f"{package.label}\nEntry {package.outer_index} · {'Staged' if modified else 'Editable' if package.writable else 'Preview'}\n{package.package_name}"
            item = QListWidgetItem(text)
            item.setToolTip(text)
            item.setData(Qt.UserRole, package)
            self.grid.addItem(item)
            self._items[package.key] = item
            cached = self._thumbs.get((package.key, tuple((m.replacement_sha256, str(m.metadata.get('detail_sha256', ''))) for m in package_modifications(package, edits))))
            if cached:
                item.setIcon(QIcon(QPixmap.fromImage(cached)))
            else:
                # Reserve image space before the first worker result arrives.
                placeholder = QPixmap(208, 128)
                placeholder.fill(Qt.transparent)
                item.setIcon(QIcon(placeholder))
                self._queue.append(package)
            if package.key == selected_key:
                self.grid.setCurrentItem(item)
        count = self.grid.count()
        total = sum(package.family == family for package in self._packages)
        self.count.setText(f"{count} / {total} packages" if self._session else "No game loaded")
        self.status.setText("Select a package to inspect and replace its layers." if count else
                            "No matching artwork. Clear search or filters." if self._session else
                            "Load your APF game to browse every Team Art package.")
        self.inspect()
        self.grid.doItemsLayout()
        self._decode_next()

    def selected_package(self):
        item = self.grid.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _decode_next(self):
        if self._decoding or not self._queue or not self.isVisible() or self._session is None:
            return
        # Decode the visible grid plus one following row. Unseen packages stay
        # indexed and searchable without keeping the studio perpetually busy.
        visible = self.grid.viewport().rect().adjusted(0, 0, 0, self.grid.gridSize().height())
        batch = [package for package in self._queue
                 if package.key in self._items and self.grid.visualItemRect(self._items[package.key]).intersects(visible)][:2]
        if not batch:
            return
        self._decoding = True
        for package in batch:
            self._queue.remove(package)
        epoch, session = self._epoch, self._session
        edits = tuple(session.modifications)
        def decode(_progress):
            results = []
            for package in batch:
                try:
                    path = thumbnail(session.asset_io, package, edits)
                    decoded_image = QImage(str(path))
                    if decoded_image.isNull():
                        raise ValueError("The decoded thumbnail is not a readable PNG")
                    results.append((package, decoded_image, None))
                except Exception as exc:
                    results.append((package, None, str(exc)))
            return results
        def decoded(results):
            self._decoding = False
            if self.facade.session is not session:
                QTimer.singleShot(0, self._decode_next)
                return
            for package, path, error in results:
                key = (package.key, tuple((m.replacement_sha256, str(m.metadata.get('detail_sha256', ''))) for m in package_modifications(package, edits)))
                if path:
                    self._thumbs[key] = path
                item = self._items.get(package.key)
                if epoch == self._epoch and item:
                    if path:
                        item.setIcon(QIcon(QPixmap.fromImage(path)))
                    else:
                        item.setToolTip(item.text() + "\nPreview unavailable: " + error)
            self.inspect()
            QTimer.singleShot(0, self._decode_next)
        self.run_task("Preparing Team Art thumbnails", decode, decoded, False)

    def inspect(self, *_args):
        package = self.selected_package()
        self.replace_button.setEnabled(bool(package and package.writable))
        self.revert_button.setEnabled(bool(package and self._session and
                                           package_modifications(package, self._session.modifications)))
        if package is None:
            self.title.setText("Choose artwork")
            self.layers.clear()
            self.preview.setText("Select a thumbnail to inspect its layers.")
            return
        self.title.setText(f"{package.label} · entry {package.outer_index}")
        lines = [package.package_name]
        if package.family == "logo":
            lines.append(f"Linked Team Select cache: catalog {package.catalog_index}")
        if package.retail_teams:
            lines.append("Retail teams: " + ", ".join(package.retail_teams))
        lines += [f"\n{layer.name}\n{layer.width} × {layer.height} · {layer.codec} · inner {layer.inner_index}" for layer in package.layers]
        self.layers.setText("\n".join(lines))
        self.layers.setToolTip(STATUS)
        item = self.grid.currentItem()
        self.preview.setPixmap(item.icon().pixmap(260, 166))

    def replace(self):
        package = self.selected_package()
        if package is None or not package.writable:
            return
        self._queue = []
        dialog = TeamArtReplaceDialog(package, self)
        if dialog.exec_() != QDialog.Accepted:
            dialog.deleteLater()
            return
        paths, session = dialog.paths(), self._session
        dialog.deleteLater()
        def stage():
            def staged(_result):
                self.modifiedChanged.emit()
                self.refresh()
                self.status.setText("Replacement staged. Build Game Folder verifies the final package allocation.")
            self.run_task("Staging Team Art", lambda progress: self.facade.replace_team_art(package, paths, progress,
                          expected_session=session), staged, True)
        window = self.window()
        if hasattr(window, "_run_when_idle"):
            window._run_when_idle(stage)
        else:
            stage()

    def revert(self):
        package, session = self.selected_package(), self._session
        if package is None or session is None:
            return
        self._queue = []
        def reverted(_result):
            self.modifiedChanged.emit()
            self.refresh()
            self.status.setText("Package reverted. Undo restores its staged layers.")
        def stage():
            self.run_task("Reverting Team Art", lambda progress: self.facade.revert_team_art(
                          package, progress, expected_session=session), reverted, True)
        window = self.window()
        if hasattr(window, "_run_when_idle"):
            window._run_when_idle(stage)
        else:
            stage()

    def showEvent(self, event):
        super().showEvent(event)
        self.set_context()
        self._decode_next()

    def eventFilter(self, watched, event):
        if watched is self.grid.viewport() and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._decode_next)
        return super().eventFilter(watched, event)
