"""MyCareer setup and independent Crib movie cut. Offscreen-capable Qt page."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                            QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_crib_reclaim as crib
from mod_editor.core import nfl2k5_roster_records as roster


class _Signals(QObject):
    finished = pyqtSignal(object, object)


class _Task(QRunnable):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.finished.emit(self.action(), None)
        except Exception as exc:
            self.signals.finished.emit(None, str(exc))


class MyCareerPanel(QWidget):
    """Shell calls set_source(image); setup_ready supplies the Build setup path.

    Creating a setup or inspecting movies does not enable either Build option.
    Long archive work runs in a worker. No action starts merely by opening a disc.
    """
    setup_ready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task = None
        self._plan = None
        self.setup_path = ""
        # Position scheme follows the Build panel's position-pools option (wired by
        # the studio through position_pools_enabled / set_position_pools).
        self._position_scheme = "retail"
        self.position_pools_enabled = lambda: False
        layout = QVBoxLayout(self)
        title = QLabel("MyCareer")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)
        description = QLabel(career.HELP_TEXT)
        description.setWordWrap(True)
        layout.addWidget(description)

        # Beta 66 (Mud): the stat line is an in-game Settings row, not a build-time preference.
        stat_line_help = QLabel(
            "In-game MyCareer: Apartment > Settings > MyPlayer stat line. "
            "On by default; shows MyPlayer's current game stats in the top right. "
            "The choice is saved with the career."
        )
        stat_line_help.setWordWrap(True)
        layout.addWidget(stat_line_help)

        group = QGroupBox("Create MyPlayer")
        form = QFormLayout(group)
        self.save = QLineEdit()
        self.save.setPlaceholderText("A signed Franchise save at the NFL Draft")
        choose = QPushButton("Choose save")
        choose.clicked.connect(self._choose_save)
        row = QHBoxLayout()
        row.addWidget(self.save)
        row.addWidget(choose)
        form.addRow("Draft save", row)
        self.first, self.last = QLineEdit(), QLineEdit()
        self.first.setMaxLength(30)
        self.last.setMaxLength(30)
        form.addRow("First name", self.first)
        form.addRow("Last name", self.last)
        self.position = QComboBox()
        for code, short, long_name in career.position_choices(self._position_scheme):
            self.position.addItem(f"{short} ({long_name})", code)
        self.position.currentIndexChanged.connect(self._position_changed)
        form.addRow("Position", self.position)
        self.template = QComboBox()
        form.addRow("Ratings", self.template)
        self.contract = QLabel()
        self.contract.setWordWrap(True)
        form.addRow("On the field", self.contract)
        self.starter = QCheckBox("Lock MyPlayer as a starter at his first club (depth row 1 with a rank lock)")
        self.starter.setChecked(True)
        form.addRow(self.starter)
        self.port = QSpinBox()
        self.port.setRange(1, 8)
        form.addRow("Controller", self.port)
        self.camera = QComboBox()
        self.camera.addItems(["Standard", "Far"])
        form.addRow("Camera", self.camera)
        self._position_changed()
        self.output = QLineEdit()
        self.output.setPlaceholderText("A new folder for the signed save and setup")
        choose_output = QPushButton("Choose folder")
        choose_output.clicked.connect(self._choose_output)
        row = QHBoxLayout()
        row.addWidget(self.output)
        row.addWidget(choose_output)
        form.addRow("Output", row)
        self.create_button = QPushButton("Create MyPlayer")
        self.create_button.clicked.connect(self._create)
        form.addRow(self.create_button)
        layout.addWidget(group)

        group = QGroupBox("Crib movie cut")
        form = QFormLayout(group)
        help_text = QLabel(crib.HELP_TEXT)
        help_text.setWordWrap(True)
        form.addRow(help_text)
        self.image = QLineEdit()
        self.image.setPlaceholderText("Open a game image in Studio, or choose one here")
        choose_image = QPushButton("Choose image")
        choose_image.clicked.connect(self._choose_image)
        row = QHBoxLayout()
        row.addWidget(self.image)
        row.addWidget(choose_image)
        form.addRow("Game image", row)
        self.review_button = QPushButton("Review movie cut")
        self.review_button.clicked.connect(self._review)
        self.rebuild_button = QPushButton("Build smaller image")
        self.rebuild_button.setEnabled(False)
        self.rebuild_button.clicked.connect(self._rebuild)
        self.image.textChanged.connect(self._invalidate_plan)
        row = QHBoxLayout()
        row.addWidget(self.review_button)
        row.addWidget(self.rebuild_button)
        form.addRow(row)
        layout.addWidget(group)
        self.result = QLabel("Both options are off in all presets. Noah reports QB play works; this build's "
                             "position behavior still needs a gameplay witness.")
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(self.result.textInteractionFlags() | Qt.TextSelectableByMouse)
        layout.addWidget(self.result)
        layout.addStretch()

    def set_source(self, source):
        self.image.setText(str(source or ""))

    def set_position_pools(self, enabled):
        """Switch the picker between the retail 17 positions and the EDGE/LB pools."""
        scheme = "one_pool" if enabled else "retail"
        if scheme == self._position_scheme:
            return
        old_code = self.position.currentData()
        old_variant = self.template.currentData()
        self._position_scheme = scheme
        code = roster.replacement_position_code(old_code or 0, scheme)
        self.position.blockSignals(True)
        try:
            self.position.clear()
            for value, short, long_name in career.position_choices(scheme):
                self.position.addItem(f"{short} ({long_name})", value)
            self.position.setCurrentIndex(max(0, self.position.findData(code)))
        finally:
            self.position.blockSignals(False)
        self._position_changed()
        variant_index = self.template.findData(old_variant)
        if variant_index >= 0:
            self.template.setCurrentIndex(variant_index)

    def showEvent(self, event):
        self.set_position_pools(bool(self.position_pools_enabled()))
        super().showEvent(event)

    def _position_changed(self):
        """Templates follow the position: the native styles of the active scheme."""
        code = self.position.currentData()
        self.template.clear()
        for template in career.templates_for(code, scheme=self._position_scheme):
            self.template.addItem(template.label, template.variant)
        if self.template.count() == 0:
            self.template.addItem("Keep the generated prospect ratings (no retail template)", None)
        group = career.position_group(code)
        proved, hypothesis = career.POSITION_CONTRACT[group]
        self.contract.setText(f"{group}: {proved}. {hypothesis}. This build's rendered play is unwitnessed.")

    def _invalidate_plan(self):
        self._plan = None
        self.rebuild_button.setEnabled(False)

    def _choose_save(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a Franchise draft save", "",
                                             "Xbox saves (*.zip SAVEGAME.DAT);;All files (*)")
        if path:
            self.save.setText(path)

    def _choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a parent folder")
        if path:
            self.output.setText(str(Path(path) / "MyCareer"))

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose game image", "", "Game images (*.iso)")
        if path:
            self.set_source(path)

    def _run(self, action, done):
        if self._task is not None:
            return
        self.create_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self.rebuild_button.setEnabled(False)
        self.result.setText("Working. The source stays available while this copy is prepared.")
        task = _Task(action)
        self._task = task

        def finished(result, error):
            self._task = None
            self.create_button.setEnabled(True)
            self.review_button.setEnabled(True)
            self.rebuild_button.setEnabled(self._plan is not None)
            if error:
                self.result.setText(error)
            else:
                done(result)

        task.signals.finished.connect(finished)
        QThreadPool.globalInstance().start(task)

    def _create(self):
        source, output = self.save.text().strip(), self.output.text().strip()
        if not source or not output or not self.first.text().strip() or not self.last.text().strip():
            self.result.setText("Choose the draft save and output folder, and enter MyPlayer's first and last name.")
            return
        options = dict(first=self.first.text().strip(), last=self.last.text().strip(),
                       position=self.position.currentData(), template=self.template.currentData(),
                       port=self.port.value() - 1, camera=self.camera.currentIndex(),
                       starter_lock=self.starter.isChecked(), scheme=self._position_scheme)

        def done(receipt):
            self.setup_path = str(Path(receipt["output"]) / "MyCareer.json")
            self.setup_ready.emit(self.setup_path)
            self.result.setText(f"Created {receipt['myplayer']} ({receipt.get('position', '?')}). Import MyCareer.zip as a "
                                "save, then enable MyCareer in Build with the matching MyCareer.json setup. The normal "
                                "draft chooses the team; choose MyCareer from Game Modes in the built game.")

        self._run(lambda: career.prepare_save(source, output, **options), done)

    def _review(self):
        source = self.image.text().strip()
        if not source:
            self.result.setText("Choose a game image first.")
            return

        def done(planned):
            if self.image.text().strip() != source:
                self.result.setText("The selected image changed. Review the new image first.")
                return
            self._plan = planned
            self.rebuild_button.setEnabled(True)
            mib = planned["disc_bytes_reclaimed"] / 1048576
            self.result.setText(f"23 movies selected. Image saving: {mib:.2f} MiB. "
                                "Trophy Room, awards, profiles, games and furniture stay.")

        self._run(lambda: crib.plan(source), done)

    def _rebuild(self):
        if self._plan is None:
            return
        output, _ = QFileDialog.getSaveFileName(self, "Write a smaller game image", "", "Game images (*.iso)")
        if not output:
            return
        source, planned = self.image.text().strip(), self._plan

        def done(receipt):
            self.result.setText(f"Built {receipt['output']}. All retained resource hashes passed. "
                                "EXPERIMENTAL / UNWITNESSED: check the Trophy Room and movie choices in game.")

        self._run(lambda: crib.rebuild(source, output, expected_plan=planned), done)


__all__ = ["MyCareerPanel"]
