"""Session-backed Music tab. All audio work runs offscreen-capable workers.

The shell mounts MusicPanel and calls set_service on source/session changes.
Playback is explicit and owned; no decoder, encoder or import auto-plays audio.
"""
from __future__ import annotations

import json
from pathlib import Path
import threading

from PyQt5.QtCore import QEvent, QObject, QProcess, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QListWidget, QMessageBox,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from mod_editor.core.audio_conform import file_dialog_filter, is_supported_suffix, SUPPORTED_SUFFIXES
from mod_editor.core.nfl2k5_music_policy import MENU_TEXT
from mod_editor.core import nfl2k5_music_playlist as playlist
from mod_editor.core.nfl2k5_music_catalog import TRACKS
from mod_editor.studio.music_service import PreparedMusicBatch


class _Signals(QObject):
    done = pyqtSignal(object, object)
    progress = pyqtSignal(str, int, int)


class _Task(QRunnable):
    def __init__(self, action, cancelled):
        super().__init__()
        self.signals = _Signals()
        self.action = action
        self.cancelled = cancelled

    def run(self):
        try:
            result = self.action(self.cancelled.is_set, self.signals.progress.emit)
            self.signals.done.emit(result, None)
        except Exception as exc:
            self.signals.done.emit(None, str(exc))


class MusicTable(QTableWidget):
    files_dropped = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(0, 7, parent)
        self.setHorizontalHeaderLabels(["Slot", "Original title / artist", "Current file",
                                        "File length", "Slot length", "Where it plays", "Status"])
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSortingEnabled(False)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

    @staticmethod
    def paths(mime):
        urls = mime.urls() if mime.hasUrls() else []
        if not urls or any(not url.isLocalFile() or not is_supported_suffix(url.toLocalFile()) for url in urls):
            return ()
        return tuple(Path(url.toLocalFile()) for url in urls)

    def dragEnterEvent(self, event):
        event.acceptProposedAction() if self.paths(event.mimeData()) else event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = self.paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        row = self.rowAt(event.pos().y())
        if row < 0:
            row = self.currentRow()
        start = self.item(row, 0).data(Qt.UserRole) if row >= 0 else None
        event.acceptProposedAction()
        self.files_dropped.emit(paths, start)


class AssignmentReview(QDialog):
    """Reorder incoming files while keeping the frozen visible targets fixed."""
    def __init__(self, assignments, catalog, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review music assignments")
        self.assignments = tuple(assignments)
        layout = QVBoxLayout(self)
        note = QLabel("Files fill these slots in order. Drag files to reorder them. "
                      "Jukebox slots also replace the linked mono stadium version.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.targets = QLabel("\n".join(f"{i+1}. {catalog.get(row_id).title} "
            f"({catalog.get(row_id).duration_seconds:.3f} s)" for i,(row_id,_path) in enumerate(assignments)))
        self.targets.setTextFormat(Qt.PlainText)
        layout.addWidget(self.targets)
        self.files = QListWidget()
        self.files.setDragDropMode(QAbstractItemView.InternalMove)
        for _row_id, path in assignments:
            self.files.addItem(str(path))
        layout.addWidget(self.files)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Prepare audio")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(680, 480)

    def result_assignments(self):
        return tuple((row_id, Path(self.files.item(i).text()))
                     for i, (row_id, _path) in enumerate(self.assignments))


class FitReview(QDialog):
    def __init__(self, batch, catalog, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review fitted music")
        layout = QVBoxLayout(self)
        label = QLabel("All files and linked versions are ready. Apply changes together or cancel.")
        label.setWordWrap(True)
        layout.addWidget(label)
        table = QTableWidget(len(batch.rows), 5)
        table.setHorizontalHeaderLabels(["Slot", "File / slot seconds", "Trim / silence seconds", "Linked versions", "Volume / notes"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i, row in enumerate(batch.rows):
            fit = row["fit"]
            values = (catalog.get(row["row_id"]).title,
                      f"{fit['source_seconds']:.3f} / {fit['slot_seconds']:.3f}",
                      f"{fit['trimmed_seconds']:.3f} / {fit['padded_seconds']:.3f}",
                      "Stereo and mono" if len(row["targets"]) == 2 else "One slot",
                      f"Gain {fit['gain_db']:+.2f} dB. " + " ".join(row["notes"]))
            for j, value in enumerate(values):
                table.setItem(i, j, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(1050, 440)


class PlaylistPage(QWidget):
    """Personal build choices; the shell owns BuildPlan/project persistence."""
    changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.enabled = QCheckBox("Shuffle selected songs in menus, Crib and games")
        self.outtakes = QCheckBox("Include spoken outtakes")
        self.outtakes.setChecked(True)
        self.beds = QCheckBox("Include 10 background music beds")
        for widget in (self.enabled, self.outtakes, self.beds):
            layout.addWidget(widget)
        note = QLabel("Choose up to 100 songs to shuffle. Songs you add on the Songs page appear here. "
                      "Loading and shows keep their own music.")
        note.setWordWrap(True)
        layout.addWidget(note)
        more = QCheckBox("More about playback")
        details = QLabel(playlist.HELP_TEXT)
        details.setWordWrap(True)
        details.hide()
        more.toggled.connect(details.setVisible)
        layout.addWidget(more)
        layout.addWidget(details)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self._catalog = playlist.catalog_for_counts(playlist.BANK_COUNTS)
        self._populate(set(playlist.CORE + playlist.BEDS))
        layout.addWidget(self.list)
        row = QHBoxLayout()
        for text, callback in (("Select all", lambda: self.select_all(True)),
                               ("Clear selection", lambda: self.select_all(False)),
                               ("Browse library image", self.browse_library),
                               ("Save playlist choices", self.save_choices),
                               ("Open playlist choices", self.open_choices)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        for widget in (self.enabled, self.outtakes, self.beds):
            widget.toggled.connect(self.refresh)
        self.list.itemChanged.connect(self.refresh)
        self.refresh()

    def _populate(self, checked):
        from PyQt5.QtWidgets import QListWidgetItem
        self.list.blockSignals(True)
        self.list.clear()
        for row in self._catalog:
            item = QListWidgetItem(row["title"], self.list)
            record = (row["bank"], row["index"])
            item.setData(Qt.UserRole, record)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if record in checked else Qt.Unchecked)
        self.list.blockSignals(False)

    def selected(self):
        return playlist.from_options(self.options())

    def options(self):
        checked = [i for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.Checked]
        records = [(r["bank"], r["index"]) for i, r in enumerate(self._catalog) if i in checked
                   and (self.outtakes.isChecked() or not r["spoken"])
                   and (self.beds.isChecked() or not r["bed"])]
        return {"schema": 2, "music_shuffle": self.enabled.isChecked(),
                "include_outtakes": self.outtakes.isChecked(), "include_beds": self.beds.isChecked(),
                "catalog": [dict(r) for r in self._catalog], "checked": checked,
                "records": [list(r) for r in records], "enabled": list(range(len(records)))}

    def set_options(self, value):
        value = playlist.copy_options(value)  # validate before changing any widget
        if value is None:
            raise ValueError("Expected playlist choices")
        catalog = (playlist.catalog_for_counts(playlist.BANK_COUNTS) if value["schema"] == 1
                   else value["catalog"])
        checked = {(catalog[i]["bank"], catalog[i]["index"]) for i in value["checked"]}
        for widget in (self.enabled, self.outtakes, self.beds):
            widget.blockSignals(True)
        self.enabled.setChecked(value["music_shuffle"])
        self.outtakes.setChecked(value["include_outtakes"])
        self.beds.setChecked(value["include_beds"])
        self._catalog = catalog
        self._populate(checked)
        for widget in (self.enabled, self.outtakes, self.beds):
            widget.blockSignals(False)
        self.refresh()

    def set_library(self, counts, *, library_plan=None):
        """Shell feeds a validated preview; the image browser uses actual AUSB counts."""
        catalog = playlist.catalog_for_counts(counts, library_plan=library_plan)
        self.set_catalog(catalog)

    def set_catalog(self, catalog):
        catalog = [dict(row) for row in playlist.validate_catalog(catalog)]
        chosen = {tuple(self.list.item(i).data(Qt.UserRole)) for i in range(self.list.count())
                  if self.list.item(i).checkState() == Qt.Checked}
        visible = [r for r in catalog if (r['bank'], r['index']) in chosen
                   and (self.outtakes.isChecked() or not r['spoken'])
                   and (self.beds.isChecked() or not r['bed'])]
        if len(visible) > playlist.MAX_ITEMS:
            raise ValueError("This library would select more than 100 recordings. Clear the selection first.")
        self._catalog = catalog
        self._populate(chosen)
        self.refresh()

    def browse_library(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a music library image", "", "Disc images (*.iso)")
        if not path:
            return
        try:
            from mod_editor.core.nfl2k5_music_banks import read_playlist_catalog
            self.set_catalog(read_playlist_catalog(path))
        except (OSError, ValueError) as exc:
            self.summary.setText(str(exc))

    def refresh(self, changed=None):
        if len(self.options()['records']) > playlist.MAX_ITEMS:
            # Undo only the extra click; never emit an invalid Build document.
            self.list.blockSignals(True)
            if changed is not None and hasattr(changed, "setCheckState"):
                changed.setCheckState(Qt.Unchecked)
            self.list.blockSignals(False)
            if not hasattr(changed, "setCheckState"):
                self.set_options(self._last_options)
            self.summary.setText("Choose at most 100 recordings. Clear a song before adding another.")
            return
        for i, row in enumerate(self._catalog):
            self.list.item(i).setHidden((row["bed"] and not self.beds.isChecked()) or
                                       (row["spoken"] and not self.outtakes.isChecked()))
        n = len(self.selected().enabled)
        state = "Shuffle selected for the next build." if self.enabled.isChecked() else "Shuffle is off."
        self.summary.setText(f"{state} {n} recordings selected, up to 100 from {len(self._catalog)} available. " +
            ("No background songs will play." if n == 0 else "The selected song will repeat." if n == 1
             else "Each song plays once per cycle, with no repeat at the cycle boundary.") +
            " Loading and shows keep their timing. Short presentation cues are excluded.")
        self._last_options = self.options()
        self.changed.emit(self.options())

    def select_all(self, checked):
        available = [i for i in range(self.list.count()) if not self.list.item(i).isHidden()]
        if checked and len(available) > playlist.MAX_ITEMS:
            self.summary.setText("Choose at most 100 recordings. Select songs individually from this library.")
            return
        self.list.blockSignals(True)
        for i in available:
            self.list.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.list.blockSignals(False)
        self.refresh()

    def save_choices(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save playlist choices", "playlist.json", "Playlist choices (*.json)")
        if not path:
            return
        try:
            # Atomic publication, with the writer closed before replace on Windows.
            import os
            from mod_editor.core.platform_compat import temporary_sibling
            destination = Path(path).resolve()
            temporary = temporary_sibling(destination)
            try:
                with temporary.open("x", encoding="utf-8") as handle:
                    json.dump(self.options(), handle, indent=2)
                    handle.write("\n")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            self.summary.setText(str(exc))

    def open_choices(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open playlist choices", "", "Playlist choices (*.json)")
        if not path:
            return
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                text = handle.read(2097153)
            if len(text) > 2097152:
                raise ValueError("Playlist choices file is too large")
            self.set_options(json.loads(text))
        except (OSError, ValueError, TypeError) as exc:
            self.summary.setText(str(exc))


class MusicPanel(QWidget):
    changed = pyqtSignal()
    policy_changed = pyqtSignal(object)
    playlist_changed = pyqtSignal(object)
    receipt_ready = pyqtSignal(object)
    operation_state_changed = pyqtSignal(bool)
    library_changed = pyqtSignal(object)  # Existing BuildPlan.music_library path, or None.

    def __init__(self, service=None, parent=None):
        super().__init__(parent)
        self.service = None
        self._playlist_source_ready = False
        self.operation_guard = None
        self._epoch = 0
        self._play_request = 0
        self._task = None
        self._closing = False
        self._cancel = threading.Event()
        self._song_order = []
        self.setAcceptDrops(True)
        self.player = QProcess(self)
        self.player.errorOccurred.connect(lambda _error: self.status.setText("Audio preview failed. Install FFplay or choose another player."))
        layout = QVBoxLayout(self)
        warning = QLabel("Experimental / unwitnessed: not yet tested in game.")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.controls = QWidget()
        controls = QVBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        policy_row = QHBoxLayout()
        self.menu_policy = QComboBox()
        self.menu_policy.addItem("Keep source menu policy", "retail")
        self.menu_policy.setToolTip("Retail default: keep the source policy. A source with a music patch already applied keeps that patch.")
        self.menu_policy.addItem("Jukebox songs in menus", "jukebox_menus")
        self.unlock = QCheckBox("Make every music collection available")
        self.userlist = QCheckBox("Use jukebox bank instead of user playlists")
        self.userlist.setToolTip("Replaces disc and HDD playlist choices in UserList contexts. This does not enable every screen.")
        for widget in (self.menu_policy, self.unlock, self.userlist):
            policy_row.addWidget(widget)
        controls.addLayout(policy_row)
        browse = QHBoxLayout()
        self.presentation = QCheckBox("Show presentation music")
        self.match_volume = QCheckBox("Match original volume")
        self.match_volume.setChecked(True)
        self.mono = QCheckBox("Preview linked mono stadium version")
        browse.addWidget(self.presentation)
        browse.addWidget(self.match_volume)
        browse.addWidget(self.mono)
        browse.addStretch()
        controls.addLayout(browse)
        self.table = MusicTable()
        controls.addWidget(self.table)
        self.detail = QLabel("Open a game source to browse music. Original slot lengths are fixed.")
        self.detail.setTextFormat(Qt.PlainText)
        self.detail.setWordWrap(True)
        controls.addWidget(self.detail)
        self.buttons = {}
        for specs in (
            (("Play current", lambda: self.play(False)), ("Play original", lambda: self.play(True)),
             ("Stop", self.stop_preview), ("Replace", self.choose_replace), ("Restore", self.restore),
             ("Undo", self.undo), ("Redo", self.redo), ("Export WAV", self.choose_export)),
            (("Export current set", self.export_set), ("Save Music project", self.save_project),
             ("Open Music project", self.load_project), ("Build music copy", self.build),
             ("Export .2k5patch", self.patch))):
            line = QHBoxLayout()
            for caption, callback in specs:
                button = QPushButton(caption)
                button.clicked.connect(callback)
                line.addWidget(button)
                self.buttons[caption] = button
            controls.addLayout(line)
        self.pages = QTabWidget()
        self.songs_page = QWidget()
        songs_layout = QVBoxLayout(self.songs_page)
        heading = QLabel("Add your music")
        heading.setStyleSheet("font-size: 22px; font-weight: bold;")
        songs_layout.addWidget(heading)
        help_text = QLabel("Choose your original music files or drop them anywhere on this page. "
                          "We prepare the sound and match the volume to the game's songs.")
        help_text.setWordWrap(True)
        songs_layout.addWidget(help_text)
        song_actions = QHBoxLayout()
        self.add_songs_button = QPushButton("Add songs...")
        self.add_songs_button.setMinimumHeight(36)
        self.add_songs_button.clicked.connect(self.choose_songs)
        song_actions.addWidget(self.add_songs_button)
        for caption, callback in (("Stop", self.stop_preview), ("Save Music project", self.save_project),
                                  ("Open Music project", self.load_project)):
            button = QPushButton(caption)
            button.clicked.connect(callback)
            song_actions.addWidget(button)
        song_actions.addStretch()
        songs_layout.addLayout(song_actions)
        self.songs_table = QTableWidget(0, 5)
        self.songs_table.setHorizontalHeaderLabels(["Title", "Artist (optional)", "Added by", "Length", "Listen"])
        self.songs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.songs_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.songs_table.setSortingEnabled(False)
        self.songs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.songs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.songs_table.verticalHeader().hide()
        self.songs_table.setAlternatingRowColors(True)
        self.songs_table.itemChanged.connect(self._song_text_changed)
        self.songs_table.itemSelectionChanged.connect(self._song_selected)
        songs_layout.addWidget(self.songs_table, 1)
        self.songs_summary = QLabel("Open a game source to add your music.")
        self.songs_summary.setWordWrap(True)
        songs_layout.addWidget(self.songs_summary)
        edit_row = QHBoxLayout()
        self.song_buttons = {}
        for caption, change in (("Remove", {"remove": True}), ("Move up", {"move": -1}), ("Move down", {"move": 1})):
            button = QPushButton(caption)
            button.clicked.connect(lambda _checked=False, change=change: self.change_song(**change))
            edit_row.addWidget(button)
            self.song_buttons[caption] = button
        edit_row.addStretch()
        songs_layout.addLayout(edit_row)
        self.song_note = QLabel("Play lets you hear the prepared sound. Double-click your title or artist to edit it.")
        self.song_note.setWordWrap(True)
        self.song_note.setTextFormat(Qt.PlainText)
        songs_layout.addWidget(self.song_note)
        self.pages.addTab(self.songs_page, "Songs")
        self.pages.addTab(self.controls, "Recordings")
        self.playlist_page = PlaylistPage()
        self.pages.addTab(self.playlist_page, "Playlist")
        self.playlist_page.changed.connect(self.playlist_changed.emit)
        self.playlist_page.changed.connect(lambda _value: self.changed.emit())
        layout.addWidget(self.pages)
        self.advanced = QCheckBox("Advanced: edit existing recordings")
        self.advanced.toggled.connect(lambda value: self.pages.setTabVisible(1, value))
        self.pages.setTabVisible(1, False)
        layout.addWidget(self.advanced)
        foot = QHBoxLayout()
        self.status = QLabel("Ready")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        self.cancel_button = QPushButton("Cancel work")
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self._cancel.set)
        foot.addWidget(self.status, 1)
        foot.addWidget(self.progress)
        foot.addWidget(self.cancel_button)
        layout.addLayout(foot)
        self.presentation.toggled.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.files_dropped.connect(self.drop_files)
        self.menu_policy.currentIndexChanged.connect(self._policy_changed)
        self.unlock.toggled.connect(self._policy_changed)
        self.userlist.toggled.connect(self._policy_changed)
        self.pages.currentChanged.connect(lambda _index: self.stop_preview())
        for widget in [self.songs_page]+self.songs_page.findChildren(QWidget):
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)
        self.set_service(service)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop) and MusicTable.paths(event.mimeData()):
            if event.type() == QEvent.Drop:
                self.dropEvent(event)
            else:
                event.acceptProposedAction()
            return True
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event):
        event.acceptProposedAction() if MusicTable.paths(event.mimeData()) else event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = MusicTable.paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.add_songs(paths)
        else:
            event.ignore()

    def choose_songs(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add songs", "",
            "Music files (*.mp3 *.m4a *.flac *.ogg *.wav);;All audio files ("+
            " ".join("*"+s for s in SUPPORTED_SUFFIXES)+")")
        if paths:
            self.add_songs(paths)

    def add_songs(self, paths):
        service = self.service
        if service is None:
            self.status.setText("Open a game source to add your songs.")
            return
        def ready(batch):
            if self._cancel.is_set():
                batch.close()
                return
            def committed(_rows):
                self._songs_changed()
                if batch.rows:
                    self._select_song(batch.rows[0]["id"])
                    notes = [f"{r['title']}: {note}" for r in batch.rows for note in r["fit"]["notes"]]
                    self.song_note.setText("\n".join(notes[:3]+(["Select each song to read its warnings."] if len(notes) > 3 else []))
                                          or "Your songs are ready. Play to check the prepared sound.")
            if not self._run(lambda cancel, progress: service.commit_songs(batch, cancelled=cancel), committed):
                batch.close()
        self._run(lambda cancel, progress: service.prepare_songs(paths, cancelled=cancel, progress=progress), ready)

    def library_recipe_path(self):
        return self.service.library_recipe_path() if self.service else None

    def _songs_changed(self):
        self._sync_song_playlist()
        self.refresh()
        self.library_changed.emit(self.library_recipe_path())
        self.changed.emit()

    def _sync_song_playlist(self):
        if self.service is None:
            return
        songs = self.service.library_songs()
        order = [r["id"] for r in songs]
        page = self.playlist_page
        checked = set()
        for i in range(page.list.count()):
            item = page.list.item(i)
            if item.checkState() != Qt.Checked:
                continue
            bank, index = item.data(Qt.UserRole)
            if bank == "cribmusic" and index >= 59:
                if index-59 < len(self._song_order):
                    checked.add(self._song_order[index-59])
            else:
                checked.add((bank, index))
        added = set(order)-set(self._song_order)
        checked.update(added)
        catalog = playlist.catalog_for_counts(playlist.BANK_COUNTS)
        insert = 66
        for i, song in enumerate(songs):
            catalog.insert(insert+i, dict(bank="cribmusic", index=59+i,
                title=song["title"]+(" / "+song["artist"] if song["artist"] else "")+" (yours)", spoken=False, bed=False))
        active = []
        for row in catalog:
            key = order[row["index"]-59] if row["bank"] == "cribmusic" and row["index"] >= 59 else (row["bank"], row["index"])
            if key in checked and (page.outtakes.isChecked() or not row["spoken"]) and (page.beds.isChecked() or not row["bed"]):
                active.append(key)
        # Existing executable holds 100 shuffle records. Give the newest songs
        # priority, retaining every song in the larger editable library.
        priority = [key for key in reversed(order) if key in added]
        priority += [key for key in active if key not in added]
        overflow = set(priority[playlist.MAX_ITEMS:])
        checked -= overflow
        records = {(r["bank"], r["index"]) for r in catalog if
            (order[r["index"]-59] if r["bank"] == "cribmusic" and r["index"] >= 59 else (r["bank"], r["index"])) in checked}
        page._catalog = catalog
        page._populate(records)
        self._song_order = order
        page.refresh()
        if overflow:
            page.summary.setText("Shuffle plays up to 100 selected songs. Your newest songs are checked first; "
                                 "the other songs stay in your library. Choose which 100 to play here.")

    def _selected_song(self):
        item = self.songs_table.item(self.songs_table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def _select_song(self, key):
        for i in range(self.songs_table.rowCount()):
            if self.songs_table.item(i, 0).data(Qt.UserRole) == key:
                self.songs_table.selectRow(i)
                self.songs_table.scrollToItem(self.songs_table.item(i, 0))
                break

    def _song_selected(self):
        self.stop_preview()
        key = self._selected_song()
        songs = self.service.library_songs() if self.service else []
        index = next((i for i, r in enumerate(songs) if r["id"] == key), None)
        self.song_buttons["Remove"].setEnabled(index is not None)
        self.song_buttons["Move up"].setEnabled(index is not None and index > 0)
        self.song_buttons["Move down"].setEnabled(index is not None and index < len(songs)-1)
        if index is not None:
            self.song_note.setText("\n".join(songs[index]["fit"]["notes"]) or
                                  "Play lets you hear the prepared sound. Double-click your title or artist to edit it.")
        elif key:
            self.song_note.setText("The game's songs are kept. You can remove or move songs marked yours.")

    def change_song(self, **change):
        if self.service is None or self._task is not None:
            return
        key = self._selected_song()
        if key not in [r["id"] for r in self.service.library_songs()]:
            return
        denial = self.operation_guard() if self.operation_guard else None
        if denial:
            self.status.setText(denial)
            return
        self.stop_preview()
        try:
            self.service.edit_song(key, **change)
            self._songs_changed()
            self._select_song(key)
        except (OSError, ValueError) as exc:
            self.refresh()
            self.status.setText(str(exc))

    def _song_text_changed(self, item):
        if item.column() in (0, 1):
            self._select_song(item.data(Qt.UserRole))
            self.change_song(**{("title" if item.column() == 0 else "artist"): item.text()})

    def play_song(self, key):
        service = self.service
        request = []
        def ready(path):
            if self._cancel.is_set() or not request or request[0] != self._play_request:
                return
            from .audio_panel_qt import audio_player_command
            command = audio_player_command(path)
            if command is None:
                self.status.setText("Install FFmpeg with FFplay from ffmpeg.org/download.html to listen here.")
                return
            self.player.start(command[0], list(command[1]))
        if self._run(lambda cancel, progress: service.playback_path(key, cancelled=cancel, progress=progress)
                     if ":" in key else service.song_playback_path(key, cancelled=cancel, progress=progress), ready):
            request.append(self._play_request)

    def _refresh_songs(self):
        selected = self._selected_song()
        self.songs_page.setEnabled(self.service is not None and self._task is None)
        self.songs_table.blockSignals(True)
        self.songs_table.setRowCount(0)
        if self.service:
            rows = [(r.row_id, r.title, r.artist, "Game", r.duration_seconds, False)
                    for r in self.service.catalog.visible_rows(False)]
            rows += [(r["id"], r["title"], r["artist"], "yours", r["fit"]["seconds"], True)
                     for r in self.service.library_songs()]
            self.songs_table.setRowCount(len(rows))
            for i, (key, title, artist, owner, seconds, editable) in enumerate(rows):
                for j, value in enumerate((title, artist, owner, f"{int(seconds)//60}:{int(seconds)%60:02}")):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, key)
                    if not editable or j > 1:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.songs_table.setItem(i, j, item)
                play = QPushButton("Play")
                play.setAcceptDrops(True)
                play.installEventFilter(self)
                play.setAccessibleName(f"Play {title}")
                play.clicked.connect(lambda _checked=False, key=key: self.play_song(key))
                self.songs_table.setCellWidget(i, 4, play)
            count = len(self.service.library_songs())
            self.songs_summary.setText(f"{count} of your songs will be added; the game keeps its 66.")
        else:
            self.songs_summary.setText("Open a game source to add your music.")
        self.songs_table.blockSignals(False)
        self._select_song(selected)
        self._song_selected()

    def playlist_options(self):
        return self.playlist_page.options()

    def set_playlist_options(self, value):
        self.playlist_page.set_options(value)

    def set_playlist_library(self, counts, *, library_plan=None):
        """A grown library can be browsed even when fixed-slot audio editing is unavailable."""
        self.playlist_page.set_library(counts, library_plan=library_plan)
        self._playlist_source_ready = True
        self.refresh()

    def set_playlist_catalog(self, catalog):
        self.playlist_page.set_catalog(catalog)
        self._playlist_source_ready = True
        self.refresh()

    @property
    def operation_in_progress(self):
        return self._task is not None

    def invalidate_audio_content(self):
        """Shell hook for shared Undo, project reopen or Audio Cues changes."""
        self.stop_preview()
        self._cancel.set()
        self._epoch += 1
        self.refresh()

    def set_service(self, service):
        had_songs = self.library_recipe_path() is not None
        self.stop_preview()
        self._cancel.set()
        self._epoch += 1
        if self.service is not None and self.service is not service:
            self.service.invalidate()
        self.service = service
        self._song_order = []
        if service is not None:
            self._sync_song_playlist()
        if service is None:
            self._playlist_source_ready = False
        self.refresh()
        if had_songs or self.library_recipe_path() is not None:
            self.library_changed.emit(self.library_recipe_path())

    def refresh(self):
        self._refreshing = True
        try:
            self._refresh_contents()
        finally:
            self._refreshing = False

    def _refresh_contents(self):
        self._refresh_songs()
        selected = self.selected_id()
        self.table.setRowCount(0)
        self.controls.setEnabled(self.service is not None and self._task is None)
        self.playlist_page.setEnabled((self.service is not None or self._playlist_source_ready) and self._task is None)
        if self.service is None:
            return
        for widget in (self.menu_policy, self.unlock, self.userlist):
            widget.blockSignals(True)
        self.menu_policy.setCurrentIndex(self.menu_policy.findData(self.service.policy["music_policy"]))
        self.unlock.setChecked(self.service.policy["music_unlock"])
        self.userlist.setChecked(self.service.policy["music_userlist"])
        self.userlist.setEnabled(self.menu_policy.currentData() == "jukebox_menus")
        for widget in (self.menu_policy, self.unlock, self.userlist):
            widget.blockSignals(False)
        rows = self.service.catalog.visible_rows(self.presentation.isChecked())
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            metadata = self.service.metadata(row.row_id)
            fit = metadata["fit"] if metadata else None
            values = (row.row_id, row.display_name,
                      metadata["source_name"] if metadata else ("Original" if self.service.row_state(row.row_id) == "Original" else "Session audio"),
                      f"{fit['source_seconds']:.3f} s" if fit else "",
                      f"{row.duration_seconds:.3f} s", row.context, self.service.row_state(row.row_id))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row.row_id)
                self.table.setItem(index, column, item)
            if row.row_id == selected:
                self.table.selectRow(index)
        self.status.setText("Ready. Add songs, listen, then open Build & Share.")

    def selected_id(self):
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def visible_ids(self):
        return tuple(self.table.item(i, 0).data(Qt.UserRole) for i in range(self.table.rowCount()))

    def selection_changed(self):
        self.stop_preview()
        if self.service is None or self.selected_id() is None:
            return
        row = self.service.catalog.get(self.selected_id())
        metadata = self.service.metadata(row.row_id)
        text = f"{row.display_name}. Slot {row.duration_seconds:.3f} seconds. "
        if row.twin:
            text += "Stereo jukebox and mono stadium versions change together. "
        if row.spoken:
            text += "Spoken outtake. "
        if row.presentation:
            text += "Presentation timing and exact cue identity remain untested. "
        if metadata:
            fit = metadata["fit"]
            text += (f"Dropped file {fit['source_seconds']:.3f} seconds; trimmed {fit['trimmed_seconds']:.3f}; "
                     f"silence added {fit['padded_seconds']:.3f}; fade {fit['fade_seconds']:.3f} seconds. " +
                     " ".join(metadata["notes"]))
        self.detail.setText(text)

    def _policy_changed(self):
        if self.service is None:
            return
        is_jukebox = self.menu_policy.currentData() == "jukebox_menus"
        if not is_jukebox:
            self.userlist.blockSignals(True)
            self.userlist.setChecked(False)
            self.userlist.blockSignals(False)
        self.service.set_policy(music_policy=self.menu_policy.currentData(),
            music_unlock=self.unlock.isChecked(), music_userlist=self.userlist.isChecked())
        self.userlist.setEnabled(is_jukebox)
        self.policy_changed.emit(dict(self.service.policy))

    def _run(self, action, completed=None):
        denial = self.operation_guard() if self.operation_guard is not None else None
        if denial:
            self.status.setText(denial)
            return
        if self.service is None or self._task is not None:
            return
        self.stop_preview()
        epoch = self._epoch
        self._cancel = threading.Event()
        task = _Task(action, self._cancel)
        self._task = task
        self.operation_state_changed.emit(True)
        self.controls.setEnabled(False)
        self.songs_page.setEnabled(False)
        self.playlist_page.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.progress.show()
        def progress(stage, done, total):
            if epoch != self._epoch:
                return
            self.status.setText(stage)
            self.progress.setRange(0, 1000)
            self.progress.setValue(round(1000*done/max(total,1)))
        def done(result, error):
            self._task = None
            self.operation_state_changed.emit(False)
            self.cancel_button.setEnabled(False)
            self.cancel_button.hide()
            self.progress.hide()
            self.refresh()
            if epoch != self._epoch or self._closing:
                if isinstance(result, PreparedMusicBatch):
                    result.close()
            elif error:
                self.status.setText(error)
            elif completed:
                try:
                    completed(result)
                except Exception as exc:
                    self.status.setText(str(exc))
            else:
                self.status.setText("Music operation completed.")
                self.changed.emit()
                self.selection_changed()
            if self._closing:
                self.close()
        task.signals.progress.connect(progress)
        task.signals.done.connect(done)
        QThreadPool.globalInstance().start(task)
        return True

    def drop_files(self, paths, start_id=None):
        if self.service is None or self._task is not None:
            return
        try:
            assignments = self.service.catalog.assignments(paths, self.visible_ids(), start_id)
            review = AssignmentReview(assignments, self.service.catalog, self)
            if review.exec_() != QDialog.Accepted:
                return
            frozen = review.result_assignments()
            service, match = self.service, self.match_volume.isChecked()
            def ready(batch):
                try:
                    if self._cancel.is_set() or FitReview(batch, service.catalog, self).exec_() != QDialog.Accepted:
                        batch.close()
                        return
                    self._run(lambda cancel,progress: service.commit_batch(batch, cancelled=cancel))
                except BaseException:
                    batch.close()
                    raise
            self._run(lambda cancel,progress: service.prepare_batch(frozen,
                match_volume=match, cancelled=cancel, progress=progress), ready)
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))

    def choose_replace(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Replace music", "", file_dialog_filter())
        if paths:
            self.drop_files(tuple(Path(p) for p in paths), self.selected_id())

    def play(self, original=False):
        row_id = self.selected_id()
        if row_id is None:
            return
        service, mono = self.service, self.mono.isChecked()
        request = []
        def ready(path):
            if (self._cancel.is_set() or row_id != self.selected_id() or
                    not request or request[0] != self._play_request):
                return
            from .audio_panel_qt import audio_player_command
            command = audio_player_command(path)
            if command is None:
                self.status.setText("Install FFplay for audio preview, or export the WAV to listen.")
                return
            program, arguments = command
            self.player.start(program, list(arguments))
        if self._run(lambda cancel,progress: service.playback_path(row_id, original=original,
                mono=mono, cancelled=cancel, progress=progress), ready):
            request.append(self._play_request)

    def stop_preview(self):
        if not getattr(self, "_refreshing", False):
            self._play_request += 1
        if self.player.state() != QProcess.NotRunning:
            self.player.terminate()
            if not self.player.waitForFinished(500):
                self.player.kill()
                self.player.waitForFinished(1000)

    def restore(self):
        service, row_id = self.service, self.selected_id()
        if row_id:
            self._run(lambda cancel,progress: None if cancel() else service.restore(row_id))

    def undo(self):
        service = self.service
        self._run(lambda cancel,progress: None if cancel() else service.undo())

    def redo(self):
        service = self.service
        self._run(lambda cancel,progress: None if cancel() else service.redo())

    def _destination(self, title, suffix):
        path, _ = QFileDialog.getSaveFileName(self, title, "", f"{title} (*{suffix})")
        if not path:
            return None
        return Path(path if path.lower().endswith(suffix) else path+suffix)

    def choose_export(self):
        service, row_id, mono = self.service, self.selected_id(), self.mono.isChecked()
        if row_id:
            path = self._destination("Export current WAV", ".wav")
            if path:
                self._run(lambda cancel,progress: service.export_wav(row_id, path, mono=mono,
                    cancelled=cancel, progress=progress))

    def export_set(self):
        path = self._destination("Export current music set", ".zip")
        service, ids = self.service, self.visible_ids()
        if path:
            self._run(lambda cancel,progress: service.export_set(path, ids, cancelled=cancel, progress=progress))

    def save_project(self):
        path = self._destination("Save authored Music project", ".2k5music")
        service = self.service
        if path:
            choices = self.playlist_options()
            self._run(lambda cancel,progress: service.save_project(path, cancelled=cancel, progress=progress,
                                                                  playlist_options=choices))

    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Music project", "", "Music project (*.2k5music)")
        service = self.service
        if path:
            def ready(_result):
                self._songs_changed()
                if service.library_playlist is not None:
                    self.set_playlist_options(service.library_playlist)
                self.policy_changed.emit(dict(service.policy))
            self._run(lambda cancel,progress: service.load_project(path, cancelled=cancel, progress=progress), ready)

    def _source_image(self):
        path = Path(self.service.session.cache.source.selected_path)
        if not path.is_file() or path.suffix.lower() not in (".iso", ".xiso", ".img"):
            raise ValueError("Build music copy requires an XISO source. Use the shared Build tab for other source types.")
        return path

    def build(self):
        try:
            source = self._source_image()
            path = self._destination("Build music copy", ".iso")
            service = self.service
            if path:
                def ready(receipt):
                    self.receipt_ready.emit(receipt)
                    receipt_path = Path(str(path)+".music-receipt.json")
                    with receipt_path.open("x", encoding="utf-8") as out:
                        json.dump(receipt, out, indent=2)
                        out.write("\n")
                    self.status.setText(f"Built {path.name}. Receipt: {receipt_path.name}")
                self._run(lambda cancel,progress: service.build_copy(source, path, cancelled=cancel, progress=progress), ready)
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))

    def patch(self):
        try:
            source = self._source_image()
            path = self._destination("Export authored music patch", ".2k5patch")
            service = self.service
            if path:
                self._run(lambda cancel,progress: service.export_patch(source, path, cancelled=cancel, progress=progress),
                          self.receipt_ready.emit)
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))

    def closeEvent(self, event):
        self.stop_preview()
        self._cancel.set()
        if self._task is not None:
            self._closing = True
            event.ignore()
        else:
            event.accept()
