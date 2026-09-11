"""Scorebar Studio page: pick a preset, repaint each part, see it live, hand it to Build.

Offscreen-safe. No modal dialog opens without a click on a picker button, so the
page can be driven completely from code and from the keyboard. The shell connects
``folder_chosen`` to the Build tab's scorebar folder field (see WIRING.md).
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap
from PyQt5.QtWidgets import (QAction, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                             QScrollArea, QSizePolicy, QSlider, QSpinBox, QUndoCommand, QUndoStack, QVBoxLayout,
                             QWidget)

from mod_editor.core import nfl2k5_scorebug_author as author

GAME_NOTE = ("What the game draws itself: team names, scores, the down and distance, quarter, clock and play "
             "clock come from the game's own fonts at fixed positions, and the team with the ball turns yellow. "
             "This page paints the bar behind them. It cannot add cells or fonts, and every team sees the same bar.")
INTRO = ("Pick a preset, recolour each part or use your own pictures, then hand the folder to Build. "
         "Experimental and not yet tested in-game.")
TEAM_NOTE = "Preview only; the game draws one bar for every team."
PREVIEW_DELAY_MS = 80


def _qcolour(text: str) -> QColor:
    r, g, b, a = author.parse_colour(text)
    return QColor(r, g, b, a)


def _hex(colour: QColor) -> str:
    return author.colour_hex((colour.red(), colour.green(), colour.blue(), colour.alpha()))


class ColourButton(QPushButton):
    """A button that shows its colour as a swatch and its value as text."""

    def __init__(self, accessible: str, parent=None):
        super().__init__(parent)
        self.colour = "#00000000"
        self.setAccessibleName(accessible)
        self.setToolTip(f"{accessible}: choose a colour")
        self.set_colour(self.colour)

    def set_colour(self, text: str) -> None:
        self.colour = author.colour_hex(text)
        colour = _qcolour(self.colour)
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.fillRect(0, 0, 9, 9, QColor(200, 200, 200))
        painter.fillRect(9, 9, 9, 9, QColor(200, 200, 200))
        painter.fillRect(9, 0, 9, 9, QColor(120, 120, 120))
        painter.fillRect(0, 9, 9, 9, QColor(120, 120, 120))
        painter.fillRect(0, 0, 18, 18, colour)
        painter.end()
        self.setIcon(QIcon(pixmap))
        self.setIconSize(QSize(18, 18))
        self.setMinimumWidth(124)
        percent = round(colour.alpha() * 100 / 255)
        if colour.alpha() == 0:
            self.setText("None")
        else:
            self.setText(self.colour[:7] if percent == 100 else f"{self.colour[:7]} {percent}%")


class _LayerCommand(QUndoCommand):
    """One part's settings, before and after. Slider drags merge into one step."""

    def __init__(self, panel, name: str, before, after, text: str, merge_key: str | None = None):
        super().__init__(text)
        self.panel, self.name, self.before, self.after = panel, name, before, after
        self.merge_key = merge_key

    def id(self) -> int:
        return -1 if self.merge_key is None else (abs(hash(("layer", self.name, self.merge_key))) % 1000000) + 1

    def mergeWith(self, other) -> bool:  # noqa: N802 - Qt name
        if not isinstance(other, _LayerCommand) or other.name != self.name or other.id() != self.id():
            return False
        self.after = other.after
        return True

    def redo(self) -> None:
        self.panel._apply_layer(self.name, self.after)

    def undo(self) -> None:
        self.panel._apply_layer(self.name, self.before)


class _StateCommand(QUndoCommand):
    """The sample state and the centre text it writes into two parts."""

    def __init__(self, panel, before: str, after: str):
        super().__init__("Sample state")
        self.panel, self.before, self.after = panel, before, after
        self.before_layers = {name: panel.document.layers[name] for name in ("down", "clock_quarter")}
        text = author.state(after).text
        self.after_layers = {name: self.before_layers[name].with_(sample_text=text[name]) for name in self.before_layers}

    def redo(self) -> None:
        self.panel._apply_state(self.after, self.after_layers)

    def undo(self) -> None:
        self.panel._apply_state(self.before, self.before_layers)


class _SettingCommand(QUndoCommand):
    def __init__(self, panel, attribute: str, before, after, text: str):
        super().__init__(text)
        self.panel, self.attribute, self.before, self.after = panel, attribute, before, after

    def id(self) -> int:
        return (abs(hash(("setting", self.attribute))) % 1000000) + 1

    def mergeWith(self, other) -> bool:  # noqa: N802 - Qt name
        if not isinstance(other, _SettingCommand) or other.attribute != self.attribute:
            return False
        self.after = other.after
        return True

    def redo(self) -> None:
        self.panel._apply_setting(self.attribute, self.after)

    def undo(self) -> None:
        self.panel._apply_setting(self.attribute, self.before)


class ScorebugStudioPanel(QWidget):
    """Left: parts and their controls. Centre: the live preview. Right: presets, folders, Build."""

    folder_chosen = pyqtSignal(str)
    document_changed = pyqtSignal()

    def __init__(self, parent=None, *, registry=None, defer_preview=False):
        super().__init__(parent)
        self.registry = registry
        self.presets = author.presets(registry)
        self.document = author.Document.from_preset(self.presets[0], registry)
        self.folder: Path | None = None
        self.undo_stack = QUndoStack(self)
        self._loading = False
        self._preview_pending = False
        self.preview_image = None
        self.analysis = None
        self._build_ui()
        self.layer_list.setCurrentRow(0)
        self._load_document_controls()
        self._load_layer_controls()
        self._deferred_preview = defer_preview
        if not defer_preview:
            self.refresh_preview()
        self.undo_stack.cleanChanged.connect(lambda _clean: self._refresh_dirty())
        self._refresh_dirty()

    def showEvent(self, event):
        super().showEvent(event)
        if self._deferred_preview:
            self._deferred_preview = False
            QTimer.singleShot(0, self.refresh_preview)

    # ---------------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        title = QLabel("Scorebar Studio")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title.setAccessibleName("Scorebar Studio page title")
        root.addWidget(title)
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        root.addWidget(intro)
        columns = QHBoxLayout()
        root.addLayout(columns, 1)
        columns.addLayout(self._build_left(), 0)
        columns.addLayout(self._build_centre(), 1)
        columns.addLayout(self._build_right(), 0)

        self.undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcuts([QKeySequence.Redo, QKeySequence("Ctrl+Y")])
        self.redo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.addAction(self.undo_action)
        self.addAction(self.redo_action)

    def _build_left(self) -> QVBoxLayout:
        column = QVBoxLayout()
        heading = QLabel("Parts of the bar")
        heading.setStyleSheet("font-weight: bold;")
        column.addWidget(heading)
        self.layer_list = QListWidget()
        self.layer_list.setAccessibleName("Scorebar parts")
        self.layer_list.setAccessibleDescription("Choose the part of the bar to repaint. Up and Down move between parts.")
        self.layer_list.setToolTip("Choose the part of the bar to repaint")
        for name in author.LAYER_ORDER:
            item = QListWidgetItem(author.LAYER_TITLES[name])
            item.setData(Qt.UserRole, name)
            item.setToolTip(author.LAYER_NOTES[name])
            self.layer_list.addItem(item)
        self.layer_list.setFixedHeight(8 * 26 + 8)
        self.layer_list.setMaximumWidth(380)
        self.layer_list.currentRowChanged.connect(lambda _row: self._load_layer_controls())
        column.addWidget(self.layer_list)
        self.layer_note = QLabel()
        self.layer_note.setWordWrap(True)
        self.layer_note.setAccessibleName("About this part")
        self.layer_note.setMaximumWidth(380)
        column.addWidget(self.layer_note)

        group = QGroupBox("This part")
        group.setMaximumWidth(380)
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignLeft)

        fill_row = QHBoxLayout()
        self.fill_button = ColourButton("Fill colour")
        self.fill_button.clicked.connect(lambda: self._pick_colour("fill"))
        fill_row.addWidget(self.fill_button, 1)
        self.clear_fill_button = QPushButton("Clear")
        self.clear_fill_button.setAccessibleName("Clear the fill colour")
        self.clear_fill_button.setToolTip("Make this part see-through")
        self.clear_fill_button.clicked.connect(lambda: self.set_fill(self.current_layer_name, "#00000000"))
        fill_row.addWidget(self.clear_fill_button)
        form.addRow("Colour", fill_row)

        self.gradient_check = QCheckBox("Blend two or three colours")
        self.gradient_check.setAccessibleName("Blend two or three colours")
        self.gradient_check.toggled.connect(self._gradient_toggled)
        form.addRow(self.gradient_check)
        self.stop_buttons = [ColourButton("Blend start colour"), ColourButton("Blend middle colour"), ColourButton("Blend end colour")]
        self.stop_labels = [QLabel("Start colour"), QLabel("Middle colour"), QLabel("End colour")]
        for index, (label, button) in enumerate(zip(self.stop_labels, self.stop_buttons)):
            button.clicked.connect(lambda _checked=False, i=index: self._pick_colour(("stop", i)))
            form.addRow(label, button)
        self.middle_check = QCheckBox("Add a middle colour")
        self.middle_check.setAccessibleName("Add a middle colour to the blend")
        self.middle_check.toggled.connect(self._middle_toggled)
        form.addRow(self.middle_check)
        self.angle_label = QLabel("Blend direction")
        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(0, 359)
        self.angle_spin.setSuffix(" degrees")
        self.angle_spin.setAccessibleName("Blend direction in degrees")
        self.angle_spin.setToolTip("0 runs left to right, 90 top to bottom, 180 right to left")
        self.angle_spin.valueChanged.connect(self._angle_changed)
        form.addRow(self.angle_label, self.angle_spin)

        self.radius_slider, radius_row = self._slider("Corner rounding", 0, author.MAX_RADIUS, self._radius_changed)
        form.addRow("Corner rounding", radius_row)

        self.border_check = QCheckBox("Draw a border")
        self.border_check.setAccessibleName("Draw a border")
        self.border_check.toggled.connect(self._border_toggled)
        form.addRow(self.border_check)
        self.border_button = ColourButton("Border colour")
        self.border_button.clicked.connect(lambda: self._pick_colour("border"))
        self.border_row_label = QLabel("Border colour")
        form.addRow(self.border_row_label, self.border_button)
        self.border_width_spin = QSpinBox()
        self.border_width_spin.setRange(1, author.MAX_BORDER)
        self.border_width_spin.setSuffix(" tile px")
        self.border_width_spin.setAccessibleName("Border width in tile pixels")
        self.border_width_spin.setToolTip("One tile pixel is about 7 x 6 screen pixels on the frame and 2 x 2 on the centre cells")
        self.border_width_spin.valueChanged.connect(self._border_width_changed)
        self.border_width_label = QLabel("Border width")
        form.addRow(self.border_width_label, self.border_width_spin)

        self.opacity_slider, opacity_row = self._slider("Opacity", 0, 100, self._opacity_changed)
        form.addRow("Opacity", opacity_row)

        self.image_label = QLabel("No picture")
        self.image_label.setWordWrap(True)
        self.image_label.setAccessibleName("Picture on this part")
        form.addRow("Picture", self.image_label)
        image_row = QHBoxLayout()
        self.image_button = QPushButton("Use my image...")
        self.image_button.setAccessibleName("Use my image on this part")
        self.image_button.setToolTip("Choose a PNG, JPEG, BMP or GIF. It is fitted into this part's on-screen shape.")
        self.image_button.clicked.connect(self._choose_image)
        image_row.addWidget(self.image_button)
        self.remove_image_button = QPushButton("Use colours instead")
        self.remove_image_button.setAccessibleName("Remove the picture and paint this part with colours")
        self.remove_image_button.clicked.connect(self.remove_image)
        image_row.addWidget(self.remove_image_button)
        form.addRow(image_row)
        self.fit_combo = QComboBox()
        self.fit_combo.setAccessibleName("How the picture fits this part")
        for mode in ("contain", "cover", "stretch", "tile"):
            self.fit_combo.addItem(author.FIT_TITLES[mode], mode)
        self.fit_combo.currentIndexChanged.connect(self._fit_changed)
        self.fit_label = QLabel("Picture fit")
        form.addRow(self.fit_label, self.fit_combo)
        self.clip_check = QCheckBox("Round the picture's corners with this part")
        self.clip_check.setAccessibleName("Round the picture's corners with this part")
        self.clip_check.toggled.connect(self._clip_toggled)
        form.addRow(self.clip_check)

        self.sample_edit = QLineEdit()
        self.sample_edit.setAccessibleName("Sample text shown in the preview")
        self.sample_edit.setToolTip("Preview only. The game writes the real text. For the clock strip use quarter|clock|play clock.")
        self.sample_edit.setMaxLength(24)
        self.sample_edit.editingFinished.connect(self._sample_text_changed)
        self.sample_label = QLabel("Sample text")
        form.addRow(self.sample_label, self.sample_edit)

        self.reset_button = QPushButton("Reset this part")
        self.reset_button.setAccessibleName("Reset this part to the preset")
        self.reset_button.clicked.connect(self.reset_layer)
        form.addRow(self.reset_button)
        column.addWidget(group)
        column.addStretch(1)
        return column

    def _slider(self, accessible: str, low: int, high: int, handler) -> tuple[QSlider, QHBoxLayout]:
        row = QHBoxLayout()
        slider = QSlider(Qt.Horizontal)
        slider.setRange(low, high)
        slider.setAccessibleName(accessible)
        slider.setPageStep(1)
        value = QLabel(str(low))
        value.setMinimumWidth(30)
        value.setAccessibleName(f"{accessible} value")
        slider.valueChanged.connect(lambda v: value.setText(str(v)))
        slider.valueChanged.connect(handler)
        row.addWidget(slider, 1)
        row.addWidget(value)
        return slider, row

    def _build_centre(self) -> QVBoxLayout:
        column = QVBoxLayout()
        toolbar = QHBoxLayout()
        self.zoom_check = QCheckBox("2x zoom")
        self.zoom_check.setAccessibleName("Show the preview at 2x zoom")
        self.zoom_check.toggled.connect(lambda _on: self.refresh_preview())
        toolbar.addWidget(self.zoom_check)
        self.wide_check = QCheckBox("Widescreen 16:9")
        self.wide_check.setAccessibleName("Preview the widescreen 16:9 layout instead of 4:3")
        self.wide_check.setToolTip("Widescreen contracts the bar by 27/32 about the centre before the 16:9 stretch")
        self.wide_check.toggled.connect(lambda _on: self.refresh_preview())
        toolbar.addWidget(self.wide_check)
        toolbar.addWidget(QLabel("Sample state"))
        self.state_combo = QComboBox()
        self.state_combo.setAccessibleName("Sample game state for the preview")
        for item in author.STATES:
            self.state_combo.addItem(item.title, item.id)
        self.state_combo.currentIndexChanged.connect(self._state_changed)
        toolbar.addWidget(self.state_combo)
        toolbar.addStretch(1)
        column.addLayout(toolbar)

        team_row = QHBoxLayout()
        self.team_check = QCheckBox("Team colours")
        self.team_check.setAccessibleName("Recolour the team blocks in the preview only")
        self.team_check.toggled.connect(lambda _on: self.refresh_preview())
        team_row.addWidget(self.team_check)
        self.away_combo, self.home_combo = QComboBox(), QComboBox()
        self.away_combo.setAccessibleName("Away team for the preview")
        self.home_combo.setAccessibleName("Home team for the preview")
        for combo in (self.away_combo, self.home_combo):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
            combo.setMinimumContentsLength(14)
        for row in author.teams():
            label = f"{row['abbr']}  {row.get('city', '')} {row.get('nickname', '')}".strip()
            self.away_combo.addItem(label, row["abbr"])
            self.home_combo.addItem(label, row["abbr"])
        self.away_combo.setCurrentIndex(max(0, self.away_combo.findData("KC")))
        self.home_combo.setCurrentIndex(max(0, self.home_combo.findData("BUF")))
        self.away_combo.currentIndexChanged.connect(lambda _i: self.refresh_preview())
        self.home_combo.currentIndexChanged.connect(lambda _i: self.refresh_preview())
        team_row.addWidget(self.away_combo)
        team_row.addWidget(QLabel("at"))
        team_row.addWidget(self.home_combo)
        team_note = QLabel(TEAM_NOTE)
        team_note.setAccessibleName("Team colours note")
        team_note.setWordWrap(True)
        team_row.addWidget(team_note, 1)
        column.addLayout(team_row)

        self.preview_label = QLabel()
        self.preview_label.setAccessibleName("Scorebar preview")
        self.preview_label.setAccessibleDescription("The bar on a drawn field with stand-in text at the game's live text positions.")
        self.preview_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setMinimumSize(660, 320)
        self.preview_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        column.addWidget(self.preview_scroll, 1)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Colours, game slot estimate and warnings")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        column.addWidget(self.status_label)
        self.game_note = QLabel(GAME_NOTE)
        self.game_note.setWordWrap(True)
        self.game_note.setAccessibleName("What the game draws itself")
        column.addWidget(self.game_note)
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setAccessibleName("Latest result")
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        column.addWidget(self.result)
        return column

    def _build_right(self) -> QVBoxLayout:
        column = QVBoxLayout()
        heading = QLabel("Presets")
        heading.setStyleSheet("font-weight: bold;")
        column.addWidget(heading)
        self.preset_list = QListWidget()
        self.preset_list.setAccessibleName("Scorebar presets")
        for item in self.presets:
            row = QListWidgetItem(item.title)
            row.setData(Qt.UserRole, item.id)
            row.setToolTip(item.summary)
            self.preset_list.addItem(row)
        self.preset_list.setFixedHeight(max(4, len(self.presets)) * 26 + 8)
        self.preset_list.setMaximumWidth(300)
        self.preset_list.currentRowChanged.connect(lambda _row: self._show_preset_summary())
        self.preset_list.itemActivated.connect(lambda _item: self.apply_preset())
        column.addWidget(self.preset_list)
        self.preset_summary = QLabel()
        self.preset_summary.setWordWrap(True)
        self.preset_summary.setMaximumWidth(300)
        self.preset_summary.setMinimumHeight(64)
        self.preset_summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.preset_summary.setAccessibleName("About the selected preset")
        column.addWidget(self.preset_summary)
        self.apply_preset_button = QPushButton("Start from this preset")
        self.apply_preset_button.setAccessibleName("Start from the selected preset")
        self.apply_preset_button.clicked.connect(lambda: self.apply_preset())
        column.addWidget(self.apply_preset_button)

        folder_group = QGroupBox("Folder")
        folder_group.setMaximumWidth(300)
        folder_layout = QVBoxLayout(folder_group)
        self.folder_label = QLabel("Not saved yet")
        self.folder_label.setWordWrap(True)
        self.folder_label.setAccessibleName("Current scorebar folder")
        folder_layout.addWidget(self.folder_label)
        self.open_button = QPushButton("Open folder...")
        self.open_button.setAccessibleName("Open a scorebar folder")
        self.open_button.setToolTip("Open a folder saved here, or any scorebar template folder")
        self.open_button.clicked.connect(self._choose_open_folder)
        folder_layout.addWidget(self.open_button)
        self.save_button = QPushButton("Save folder...")
        self.save_button.setAccessibleName("Save this scorebar as a folder")
        self.save_button.setToolTip("Writes layout.json, the 1x and 2x PNGs, your pictures and the Studio settings")
        self.save_button.clicked.connect(lambda: self.save_folder())
        folder_layout.addWidget(self.save_button)
        self.save_as_button = QPushButton("Save to another folder...")
        self.save_as_button.setAccessibleName("Save this scorebar to another folder")
        self.save_as_button.clicked.connect(lambda: self.save_folder(ask=True))
        folder_layout.addWidget(self.save_as_button)
        self.build_button = QPushButton("Use in Build")
        self.build_button.setAccessibleName("Use this scorebar folder in Build")
        self.build_button.setToolTip("Saves the folder and fills in the scorebar folder on the Build tab")
        self.build_button.clicked.connect(self.use_in_build)
        folder_layout.addWidget(self.build_button)
        self.dirty_label = QLabel()
        self.dirty_label.setAccessibleName("Unsaved changes")
        folder_layout.addWidget(self.dirty_label)
        column.addWidget(folder_group)

        history = QHBoxLayout()
        self.undo_button = QPushButton("Undo")
        self.undo_button.setAccessibleName("Undo the last scorebar change")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_stack.undo)
        self.undo_stack.canUndoChanged.connect(self.undo_button.setEnabled)
        history.addWidget(self.undo_button)
        self.redo_button = QPushButton("Redo")
        self.redo_button.setAccessibleName("Redo the last undone scorebar change")
        self.redo_button.setEnabled(False)
        self.redo_button.clicked.connect(self.undo_stack.redo)
        self.undo_stack.canRedoChanged.connect(self.redo_button.setEnabled)
        history.addWidget(self.redo_button)
        column.addLayout(history)

        advanced = QGroupBox("Game fit")
        advanced.setMaximumWidth(300)
        advanced_form = QFormLayout(advanced)
        self.colour_limit_spin = QSpinBox()
        self.colour_limit_spin.setRange(8, author.MAX_COLOURS)
        self.colour_limit_spin.setAccessibleName("Colour limit for the saved bar")
        self.colour_limit_spin.setToolTip("The game allows 256 colours in the whole bar; fewer colours pack smaller. Blends are reduced to fit.")
        self.colour_limit_spin.valueChanged.connect(self._colour_limit_changed)
        advanced_form.addRow("Colour limit", self.colour_limit_spin)
        column.addWidget(advanced)
        column.addStretch(1)
        return column

    # ------------------------------------------------------------ properties
    @property
    def current_layer_name(self) -> str:
        item = self.layer_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else author.LAYER_ORDER[0]

    @property
    def is_dirty(self) -> bool:
        return not self.undo_stack.isClean()

    def select_layer(self, name: str) -> None:
        for row in range(self.layer_list.count()):
            if self.layer_list.item(row).data(Qt.UserRole) == name:
                self.layer_list.setCurrentRow(row)
                return
        raise author.AuthorError(f"Unknown scorebar layer {name!r}.")

    # -------------------------------------------------------- control loading
    def _load_layer_controls(self) -> None:
        name = self.current_layer_name
        layer = self.document.layers[name]
        self._loading = True
        try:
            self.layer_note.setText(author.LAYER_NOTES[name])
            self.fill_button.set_colour(layer.fill)
            has_gradient = layer.gradient is not None
            self.gradient_check.setChecked(has_gradient)
            three = has_gradient and len(layer.gradient.stops) == 3
            for widget in (self.stop_buttons[0], self.stop_labels[0], self.stop_buttons[2], self.stop_labels[2],
                           self.middle_check, self.angle_spin, self.angle_label):
                widget.setVisible(has_gradient)
            self.stop_buttons[1].setVisible(three)
            self.stop_labels[1].setVisible(three)
            if has_gradient:
                stops = layer.gradient.stops
                self.middle_check.setChecked(three)
                self.stop_buttons[0].set_colour(stops[0])
                if three:
                    self.stop_buttons[1].set_colour(stops[1])
                self.stop_buttons[2].set_colour(stops[-1])
                self.angle_spin.setValue(layer.gradient.angle)
            self.radius_slider.setValue(layer.radius)
            has_border = layer.border is not None and layer.border.width > 0
            self.border_check.setChecked(has_border)
            for widget in (self.border_button, self.border_row_label, self.border_width_spin, self.border_width_label):
                widget.setVisible(has_border)
            if has_border:
                self.border_button.set_colour(layer.border.colour)
                self.border_width_spin.setValue(layer.border.width)
            self.opacity_slider.setValue(layer.opacity)
            has_image = layer.image is not None
            if has_image:
                sizes = ", ".join(f"{s.scale} {author.decode_image(s.data).size[0]}x{author.decode_image(s.data).size[1]}"
                                  for s in layer.image.sources)
                self.image_label.setText(f"{layer.image.name or 'picture'} ({sizes})")
                self.fit_combo.setCurrentIndex(max(0, self.fit_combo.findData(layer.image.fit)))
                self.clip_check.setChecked(layer.image.clip)
            else:
                self.image_label.setText("No picture")
            self.fit_combo.setVisible(has_image)
            self.fit_label.setVisible(has_image)
            self.clip_check.setVisible(has_image)
            self.remove_image_button.setVisible(has_image)
            is_text = name in author.TEXT_LAYERS
            self.sample_label.setVisible(is_text)
            self.sample_edit.setVisible(is_text)
            self.sample_edit.setText(layer.sample_text or author.DEFAULT_SAMPLE_TEXT.get(name, "") if is_text else "")
        finally:
            self._loading = False

    def _show_preset_summary(self) -> None:
        item = self.preset_list.currentItem()
        if item is None:
            self.preset_summary.setText("")
            return
        chosen = next(p for p in self.presets if p.id == item.data(Qt.UserRole))
        self.preset_summary.setText(chosen.summary)
        self.preset_summary.setToolTip(chosen.note or chosen.summary)

    def _refresh_dirty(self) -> None:
        self.dirty_label.setText("Unsaved changes" if self.is_dirty else "")
        self.folder_label.setText(str(self.folder) if self.folder else "Not saved yet")

    # ------------------------------------------------------- document edits
    def edit_layer(self, name: str, text: str, merge_key: str | None = None, **changes) -> None:
        """Change one part through the undo stack. Keyword names are Layer fields."""
        before = self.document.layers[name]
        after = before.with_(**changes)
        if after == before:
            return
        self.undo_stack.push(_LayerCommand(self, name, before, after, text, merge_key))

    def _apply_layer(self, name: str, layer) -> None:
        self.document.layers[name] = layer
        if name == self.current_layer_name:
            self._load_layer_controls()
        self._schedule_preview()
        self.document_changed.emit()

    def _apply_state(self, state_id: str, layers: dict) -> None:
        self.document.state_id = state_id
        for name, layer in layers.items():
            self.document.layers[name] = layer
        self._loading = True
        try:
            self.state_combo.setCurrentIndex(max(0, self.state_combo.findData(state_id)))
        finally:
            self._loading = False
        self._load_layer_controls()
        self._schedule_preview()
        self.document_changed.emit()

    def _apply_setting(self, attribute: str, value) -> None:
        setattr(self.document, attribute, value)
        self._loading = True
        try:
            if attribute == "colour_limit":
                self.colour_limit_spin.setValue(value)
        finally:
            self._loading = False
        self._schedule_preview()
        self.document_changed.emit()

    def set_fill(self, name: str, colour: str) -> None:
        self.edit_layer(name, f"{author.LAYER_TITLES[name]} colour", fill=author.colour_hex(colour))

    def set_gradient(self, name: str, stops, angle: int | None = None) -> None:
        layer = self.document.layers[name]
        current_angle = layer.gradient.angle if layer.gradient else 90
        gradient = author.Gradient(tuple(author.colour_hex(s) for s in stops), current_angle if angle is None else angle)
        self.edit_layer(name, f"{author.LAYER_TITLES[name]} blend", gradient=gradient)

    def set_border(self, name: str, colour: str | None, width: int = 1) -> None:
        border = None if colour is None else author.Border(author.colour_hex(colour), width)
        self.edit_layer(name, f"{author.LAYER_TITLES[name]} border", border=border)

    def use_image(self, path, fit: str = "contain") -> None:
        """Fit a picture file into the current part (the dialog-free entry point)."""
        name = self.current_layer_name
        try:
            source = author.load_picture(path)
        except author.AuthorError as exc:
            self._report(str(exc), error=True)
            return
        ref = author.ImageRef((source,), fit, None, False, Path(path).name)
        self.edit_layer(name, f"{author.LAYER_TITLES[name]} picture", image=ref)
        self._report(f"{Path(path).name} placed on the {author.LAYER_TITLES[name].lower()}. "
                     "It is fitted to the part's on-screen shape and reduced to the game's tile size.")

    def remove_image(self) -> None:
        name = self.current_layer_name
        layer = self.document.layers[name]
        if layer.image is None:
            return
        changes = {"image": None}
        if author.parse_colour(layer.fill)[3] == 0 and layer.gradient is None:
            default = author.DEFAULT_PAINT[name]
            changes.update(fill=default.fill, gradient=default.gradient, radius=default.radius, border=default.border)
        self.edit_layer(name, f"{author.LAYER_TITLES[name]} colours", **changes)

    def reset_layer(self) -> None:
        name = self.current_layer_name
        try:
            chosen = next((p for p in self.presets if p.id == self.document.preset_id), self.presets[0])
            fresh = author.Document.from_preset(chosen, self.registry).layers[name]
        except author.AuthorError as exc:
            self._report(str(exc), error=True)
            return
        before = self.document.layers[name]
        if fresh == before:
            return
        self.undo_stack.push(_LayerCommand(self, name, before, fresh, f"Reset {author.LAYER_TITLES[name].lower()}"))

    # ----------------------------------------------------------- handlers
    def _pick_colour(self, target) -> None:
        name = self.current_layer_name
        layer = self.document.layers[name]
        if target == "fill":
            initial, title = layer.fill, "Choose the fill colour"
        elif target == "border":
            initial, title = (layer.border.colour if layer.border else "#FFFFFFFF"), "Choose the border colour"
        else:
            stops = layer.gradient.stops if layer.gradient else ("#FFFFFFFF", "#000000FF")
            index = target[1]
            initial = stops[min(index, len(stops) - 1)] if index != 1 or len(stops) == 3 else stops[0]
            title = "Choose a blend colour"
        colour = QColorDialog.getColor(_qcolour(initial), self, title, QColorDialog.ShowAlphaChannel)
        if not colour.isValid():
            return
        self.apply_picked_colour(target, _hex(colour))

    def apply_picked_colour(self, target, colour: str) -> None:
        name = self.current_layer_name
        layer = self.document.layers[name]
        if target == "fill":
            self.set_fill(name, colour)
        elif target == "border":
            width = layer.border.width if layer.border else self.border_width_spin.value()
            self.set_border(name, colour, max(1, width))
        else:
            stops = list(layer.gradient.stops) if layer.gradient else [layer.fill, "#000000FF"]
            index = target[1]
            if index == 1 and len(stops) == 2:
                stops.insert(1, colour)
            elif index == 2 or (index == 1 and len(stops) == 3):
                stops[index if len(stops) == 3 else 1] = colour
            else:
                stops[0] = colour
            self.set_gradient(name, stops)

    def _gradient_toggled(self, on: bool) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        layer = self.document.layers[name]
        if on and layer.gradient is None:
            base = author.parse_colour(layer.fill)
            if base[3] == 0:
                base = author.parse_colour(author.DEFAULT_PAINT[name].fill)
            darker = author.colour_hex((base[0] * 55 // 100, base[1] * 55 // 100, base[2] * 55 // 100, 255))
            self.set_gradient(name, (author.colour_hex(base), darker), 90)
        elif not on and layer.gradient is not None:
            self.edit_layer(name, f"{author.LAYER_TITLES[name]} colour", gradient=None,
                            fill=layer.fill if author.parse_colour(layer.fill)[3] else layer.gradient.stops[0])

    def _middle_toggled(self, on: bool) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        layer = self.document.layers[name]
        if layer.gradient is None:
            return
        stops = list(layer.gradient.stops)
        if on and len(stops) == 2:
            a, b = author.parse_colour(stops[0]), author.parse_colour(stops[1])
            stops.insert(1, author.colour_hex(tuple((x + y) // 2 for x, y in zip(a, b))))
        elif not on and len(stops) == 3:
            del stops[1]
        else:
            return
        self.set_gradient(name, stops)

    def _angle_changed(self, value: int) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        layer = self.document.layers[name]
        if layer.gradient is not None and layer.gradient.angle != value:
            self.edit_layer(name, f"{author.LAYER_TITLES[name]} blend direction", "angle",
                            gradient=author.Gradient(layer.gradient.stops, value))

    def _radius_changed(self, value: int) -> None:
        if not self._loading:
            self.edit_layer(self.current_layer_name, "Corner rounding", "radius", radius=value)

    def _border_toggled(self, on: bool) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        layer = self.document.layers[name]
        if on and (layer.border is None or layer.border.width == 0):
            self.set_border(name, "#FFFFFFFF", 1)
        elif not on and layer.border is not None:
            self.set_border(name, None)

    def _border_width_changed(self, value: int) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        layer = self.document.layers[name]
        if layer.border is not None and layer.border.width != value:
            self.edit_layer(name, "Border width", "border_width", border=author.Border(layer.border.colour, value))

    def _opacity_changed(self, value: int) -> None:
        if not self._loading:
            self.edit_layer(self.current_layer_name, "Opacity", "opacity", opacity=value)

    def _fit_changed(self, _index: int) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        layer = self.document.layers[name]
        mode = self.fit_combo.currentData()
        if layer.image is not None and mode in author.FIT_MODES and layer.image.fit != mode:
            self.edit_layer(name, "Picture fit", image=author.ImageRef(layer.image.sources, mode, layer.image.crop,
                                                                       layer.image.clip, layer.image.name))

    def _clip_toggled(self, on: bool) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        layer = self.document.layers[name]
        if layer.image is not None and layer.image.clip != on:
            self.edit_layer(name, "Picture corners", image=author.ImageRef(layer.image.sources, layer.image.fit,
                                                                           layer.image.crop, on, layer.image.name))

    def _sample_text_changed(self) -> None:
        if self._loading:
            return
        name = self.current_layer_name
        if name in author.TEXT_LAYERS:
            self.edit_layer(name, "Sample text", "sample_text", sample_text=self.sample_edit.text().strip() or None)

    def _state_changed(self, _index: int) -> None:
        if self._loading:
            return
        after = self.state_combo.currentData()
        if after and after != self.document.state_id:
            self.undo_stack.push(_StateCommand(self, self.document.state_id, after))

    def _colour_limit_changed(self, value: int) -> None:
        if not self._loading and value != self.document.colour_limit:
            self.undo_stack.push(_SettingCommand(self, "colour_limit", self.document.colour_limit, value, "Colour limit"))

    def _choose_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Choose a picture for this part", "",
                                                    "Pictures (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*)")
        if path:
            self.use_image(path, "contain")

    def _choose_open_folder(self) -> None:
        start = str(self.folder) if self.folder else str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "Open a scorebar folder", start)
        if path:
            self.open_folder(path)

    # ---------------------------------------------------- presets and folders
    def apply_preset(self, preset_id: str | None = None) -> None:
        if preset_id is None:
            item = self.preset_list.currentItem()
            preset_id = item.data(Qt.UserRole) if item is not None else self.presets[0].id
        try:
            document = author.Document.from_preset(preset_id, self.registry)
        except author.AuthorError as exc:
            self._report(str(exc), error=True)
            return
        self._replace_document(document, None)
        self._report(f"Started from {document.title}. Choose a part on the left to repaint it.")

    def open_folder(self, path) -> None:
        try:
            document = author.Document.open_folder(path)
        except author.AuthorError as exc:
            self._report(str(exc), error=True)
            return
        self._replace_document(document, Path(path))
        self._report(f"Opened {Path(path).name}. Pictures keep their exact pixels until you repaint a part.")

    def _load_document_controls(self) -> None:
        """Document-wide controls follow the document: state, colour limit, preset row."""
        document = self.document
        self._loading = True
        try:
            self.state_combo.setCurrentIndex(max(0, self.state_combo.findData(document.state_id)))
            self.colour_limit_spin.setValue(document.colour_limit)
            for row in range(self.preset_list.count()):
                if self.preset_list.item(row).data(Qt.UserRole) == document.preset_id:
                    self.preset_list.setCurrentRow(row)
        finally:
            self._loading = False
        self._show_preset_summary()

    def _replace_document(self, document, folder) -> None:
        self.document = document
        self.folder = folder
        self.undo_stack.clear()
        self._load_document_controls()
        self._load_layer_controls()
        self._refresh_dirty()
        self.refresh_preview()
        self.document_changed.emit()

    def save_folder(self, path=None, *, ask: bool = False) -> bool:
        """Save to path, the current folder, or a folder the user picks. True on success."""
        target = Path(path) if path else (None if ask else self.folder)
        if target is None:
            start = str(self.folder.parent) if self.folder else str(Path.home())
            chosen = QFileDialog.getExistingDirectory(self, "Choose a folder for this scorebar", start)
            if not chosen:
                return False
            target = Path(chosen)
            if target.is_dir() and any(target.iterdir()) and not (target / "layout.json").is_file():
                answer = QMessageBox.question(self, "Folder is not empty",
                                              f"{target.name} already has files in it. Save the scorebar there anyway?")
                if answer != QMessageBox.Yes:
                    return False
        try:
            receipt = self.document.save_folder(target)
        except author.AuthorError as exc:
            self._report(str(exc), error=True)
            return False
        self.folder = target
        self.undo_stack.setClean()
        self._refresh_dirty()
        slot = receipt["slot"]
        self._report(f"Saved {target.name}: {receipt['colours']} colours, about {slot['estimated_bytes']} of "
                     f"{slot['budget_bytes']} bytes of the game's scorebar slot.")
        return True

    def use_in_build(self) -> None:
        if self.folder is None or self.is_dirty:
            if not self.save_folder():
                return
        try:
            author.check_folder(self.folder)
        except author.AuthorError as exc:
            self._report(str(exc), error=True)
            return
        self.folder_chosen.emit(str(self.folder))
        self._report(f"Handed to Build: {self.folder}. On the Build tab, tick Experimental ESPN scorebar; "
                     "the scorebar folder is filled in.")

    # ------------------------------------------------------------- preview
    def _schedule_preview(self) -> None:
        if self._preview_pending:
            return
        self._preview_pending = True
        QTimer.singleShot(PREVIEW_DELAY_MS, self.refresh_preview)

    def refresh_preview(self) -> None:
        self._preview_pending = False
        team = None
        if self.team_check.isChecked():
            team = (self.away_combo.currentData(), self.home_combo.currentData())
        try:
            image = author.preview(self.document, widescreen=self.wide_check.isChecked(), team_preview=team)
            self.analysis = self.document.analysis()
        except author.AuthorError as exc:
            self.status_label.setText(f"Cannot draw this bar: {exc}")
            self.status_label.setStyleSheet("color: #ffb347;")
            return
        self.preview_image = image
        pixmap = QPixmap()
        pixmap.loadFromData(author.encode_png(image), "PNG")
        if self.zoom_check.isChecked():
            pixmap = pixmap.scaled(pixmap.width() * 2, pixmap.height() * 2, Qt.KeepAspectRatio, Qt.FastTransformation)
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setMinimumSize(pixmap.size())
        slot = self.analysis["slot"]
        fits = "fits" if slot["fits"] else "does not fit"
        text = (f"Colours: {self.analysis['colours']} of {self.analysis['colour_limit']} chosen (game limit "
                f"{self.analysis['max_colours']}). Game slot estimate: {slot['estimated_bytes']} of "
                f"{slot['budget_bytes']} bytes, {fits}. The build's exact check is final.")
        if self.analysis["warnings"]:
            text += " " + " ".join(self.analysis["warnings"])
            self.status_label.setStyleSheet("color: #ffb347;")
        else:
            self.status_label.setStyleSheet("")
        self.status_label.setText(text)

    def _report(self, message: str, *, error: bool = False) -> None:
        self.result.setText(message)
        self.result.setStyleSheet("color: #ff8080;" if error else "")


__all__ = ["ScorebugStudioPanel", "ColourButton", "GAME_NOTE"]
