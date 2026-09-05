"""Commentary tab: put one of your own recorded lines into a copied disc image.

Sits next to Throw Distance & Arc and the ESPN scorebug tab in the Sliders &
Gameplay workspace.  It reads the speech banks (``lines``, ``cutsceneaudio``,
``teams``, ``players`` ...) straight out of any NFL 2K5 disc image, lists a
page of sub-streams with their durations, takes any audio file, cuts/resamples
it to the slot's exact shape with FFmpeg, encodes it to Xbox IMA and writes it
into a COPY of the disc.  The source image is never modified.  Everything the
tool does is the same as ``tools/nfl2k5_commentary_swap.py``.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
from collections.abc import Callable
import os
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mod_editor.gui.ux_text import XEMU_LINE, plain_failure, show_operation_error, suggest_copy_name

IMAGE_FILTER = "Disc images (*.iso *.xiso);;All files (*)"
AUDIO_FILTER = "Audio (*.wav *.mp3 *.flac *.ogg *.m4a *.aac);;All files (*)"
SPEECH_BANKS = ("cutsceneaudio", "lines", "teams", "players", "coacha", "halftimeaudio",
                "overlayaudio", "animationaudio")
DEFAULT_RETAIL_PACKS = (Path(os.environ["NFL2K5_RETAIL_PACKS"]) if os.environ.get("NFL2K5_RETAIL_PACKS") else None)   # extracted retail packs, developer machines only


def swap_module():
    tools = Path(__file__).resolve().parents[2] / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module("nfl2k5_commentary_swap")


def list_streams(disc_path: Path, bank: str, start: int, count: int) -> list[dict[str, object]]:
    """Rows for the stream list: id, seconds, bytes (read-only disc walk)."""

    module = swap_module()
    with module.DiscBanks(disc_path) as disc:
        return [stream.describe() for stream in disc.iter_streams(bank, start, count)]


def bank_names(disc_path: Path) -> list[str]:
    module = swap_module()
    with module.DiscBanks(disc_path) as disc:
        names = list(disc.banks)
    ordered = [name for name in SPEECH_BANKS if name in names]
    return ordered + sorted(name for name in names if name not in ordered)


def perform_write(source: Path, target: Path, stream_id: str, audio: Path,
                  retail_packs: Path | None, *, start_seconds: float = 0.0,
                  gain_db: float = 0.0, loudnorm_lufs: float | None = None,
                  target_rms_db: float | None = None) -> dict[str, object]:
    """Copy the disc, conform the clip to the slot, encode and write it in place."""

    module = swap_module()
    with module.DiscBanks(source) as disc:
        stream = disc.stream_by_id(stream_id)
    shutil.copyfile(source, target)
    with tempfile.TemporaryDirectory(prefix="commentary-") as folder:
        clip = Path(folder) / "clip.wav"
        conformed = module.conform_clip(audio, clip, channels=stream.channels,
                                        max_seconds=stream.duration, start=start_seconds,
                                        gain_db=gain_db, loudnorm_lufs=loudnorm_lufs,
                                        target_rms_db=target_rms_db)
        receipt = module.replace_stream(
            target, stream_id, clip,
            retail_packs=retail_packs if retail_packs and retail_packs.is_dir() else None,
            force=not (retail_packs and retail_packs.is_dir()),
            guards=[],
        )
    receipt["conformed"] = conformed
    return receipt


class _Signals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, operation: Callable[[], object]) -> None:
        super().__init__()
        self.signals = _Signals()
        self._operation = operation

    def run(self) -> None:
        try:
            self.signals.finished.emit(self._operation())
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class CommentaryPanel(QWidget):
    """One recorded line into one speech slot of a copied disc image."""

    def __init__(self, facade: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._task: _Task | None = None
        self._source_loaded = False
        self._target_generated = False
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Replace one commentary / studio line with your own voice. The speech banks are read from "
            "the disc, one sub-stream is chosen, your clip is cut to that slot's length (shorter clips "
            "are padded with silence), encoded to the game's Xbox IMA ADPCM and written into a COPY of "
            "the disc. Nothing else on the disc changes; the source image is never touched."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        source_box = QGroupBox("1. Game disc (.iso)")
        source_layout = QHBoxLayout(source_box)
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setPlaceholderText("Filled in when you open a disc (top right), or choose one here")
        source_button = QPushButton("Choose…")
        source_button.clicked.connect(self._choose_source)
        source_layout.addWidget(self.source_field, 1)
        source_layout.addWidget(source_button)
        layout.addWidget(source_box)

        pick_box = QGroupBox("2. Line to replace")
        pick_layout = QVBoxLayout(pick_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Bank"))
        self.bank_combo = QComboBox()
        self.bank_combo.addItems(list(SPEECH_BANKS))
        row.addWidget(self.bank_combo)
        row.addWidget(QLabel("From #"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 40_000)
        row.addWidget(self.start_spin)
        row.addWidget(QLabel("Show"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 500)
        self.count_spin.setValue(25)
        row.addWidget(self.count_spin)
        self.list_button = QPushButton("List streams")
        self.list_button.clicked.connect(self._list_streams)
        row.addWidget(self.list_button)
        row.addStretch(1)
        pick_layout.addLayout(row)
        self.stream_list = QListWidget()
        self.stream_list.setMaximumHeight(160)
        self.stream_list.itemSelectionChanged.connect(self._stream_picked)
        pick_layout.addWidget(self.stream_list)
        row = QHBoxLayout()
        row.addWidget(QLabel("Stream id"))
        self.stream_field = QLineEdit()
        self.stream_field.setPlaceholderText("bank:index, e.g. cutsceneaudio:12")
        self.stream_field.textChanged.connect(self._refresh)
        row.addWidget(self.stream_field, 1)
        pick_layout.addLayout(row)
        layout.addWidget(pick_box)

        clip_box = QGroupBox("3. Your recording")
        clip_layout = QHBoxLayout(clip_box)
        self.audio_field = QLineEdit()
        self.audio_field.setPlaceholderText("Any audio file; cut from 'start' to the slot length")
        self.audio_field.textChanged.connect(self._refresh)
        audio_button = QPushButton("Choose…")
        audio_button.clicked.connect(self._choose_audio)
        clip_layout.addWidget(self.audio_field, 1)
        clip_layout.addWidget(audio_button)
        clip_layout.addWidget(QLabel("Start (s)"))
        self.start_field = QLineEdit("0")
        self.start_field.setMaximumWidth(70)
        clip_layout.addWidget(self.start_field)
        clip_layout.addWidget(QLabel("Gain (dB)"))
        self.gain_field = QLineEdit("0")
        self.gain_field.setMaximumWidth(60)
        clip_layout.addWidget(self.gain_field)
        self.loudnorm_check = QCheckBox("Match game loudness")
        self.loudnorm_check.setChecked(True)
        self.loudnorm_check.setToolTip("Retail speech is hard-normalised to -14.3 dBFS RMS with peaks at "
                                       "0 dBFS; home recordings are usually 10-20 dB quieter. This applies "
                                       "gain plus a look-ahead limiter so your line sits at the game's level.")
        clip_layout.addWidget(self.loudnorm_check)
        layout.addWidget(clip_box)

        target_box = QGroupBox("4. Save disc copy as")
        target_layout = QVBoxLayout(target_box)
        row = QHBoxLayout()
        self.target_field = QLineEdit()
        self.target_field.setPlaceholderText("Where the new disc goes (never the source)")
        self.target_field.textChanged.connect(self._refresh)
        self.target_field.textEdited.connect(lambda _t: setattr(self, "_target_generated", False))
        target_button = QPushButton("Choose…")
        target_button.clicked.connect(self._choose_target)
        row.addWidget(self.target_field, 1)
        row.addWidget(target_button)
        target_layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Retail packs (optional, verifies the slot before writing)"))
        self.retail_field = QLineEdit(str(DEFAULT_RETAIL_PACKS) if DEFAULT_RETAIL_PACKS is not None and DEFAULT_RETAIL_PACKS.is_dir() else "")
        row.addWidget(self.retail_field, 1)
        target_layout.addLayout(row)
        layout.addWidget(target_box)

        row = QHBoxLayout()
        self.write_button = QPushButton("Make disc with this line")
        self.write_button.clicked.connect(self._write)
        row.addWidget(self.write_button)
        self.status_label = QLabel("Open your game disc (top right), or choose one above, to begin.")
        self.status_label.setWordWrap(True)
        row.addWidget(self.status_label, 1)
        layout.addLayout(row)
        layout.addStretch(1)
        self._refresh()

    # ------------------------------------------------------------------ state
    def apply_source(self, path: Path, banks: list[str] | None, loaded: bool) -> None:
        """Populate from a disc walk result (also used by tests)."""

        self._source_loaded = loaded
        self.source_field.setText(str(path))
        if loaded and (not self.target_field.text().strip() or self._target_generated):
            self.target_field.setText(suggest_copy_name(path, suffix="commentary"))
            self._target_generated = True
        if banks:
            self.bank_combo.clear()
            self.bank_combo.addItems(banks)
        self.status_label.setText(
            f"{len(banks or [])} speech/music banks found; list a bank and pick a line." if loaded
            else "Not an NFL 2K5 disc image (no speech banks found)."
        )
        self._refresh()

    def apply_streams(self, rows: list[dict[str, object]]) -> None:
        self.stream_list.clear()
        for row in rows:
            item = QListWidgetItem(f"{row['stream']:<22}  {row['duration_seconds']:.3f} s   {row['bytes']:,} bytes")
            item.setData(Qt.UserRole, row["stream"])
            self.stream_list.addItem(item)

    def ready(self) -> bool:
        stream = self.stream_field.text().strip()
        target = self.target_field.text().strip()
        return (self._source_loaded and ":" in stream and bool(self.audio_field.text().strip())
                and bool(target) and Path(target) != Path(self.source_field.text()))

    def _refresh(self) -> None:
        self.write_button.setEnabled(self.ready())
        self.list_button.setEnabled(self._source_loaded)

    # ------------------------------------------------------------------ actions
    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose your game disc (.iso)", str(Path.home()), IMAGE_FILTER)
        if chosen:
            self.load_source(Path(chosen))

    def load_source(self, path: Path | str) -> None:
        """List the speech banks of ``path`` in the background (also the open-disc hook)."""

        path = Path(path)
        self.source_field.setText(str(path))
        self.status_label.setText("Reading the speech banks…")

        def operation() -> object:
            return bank_names(path)

        def done(result: object) -> None:
            assert isinstance(result, list)
            self.apply_source(path, result, True)

        def failed(message: str) -> None:
            self.apply_source(path, None, False)
            self.status_label.setText(f"Could not read the disc: {message}")

        self._run(operation, done, failed)

    def _list_streams(self) -> None:
        source = Path(self.source_field.text())
        bank = self.bank_combo.currentText()
        start, count = self.start_spin.value(), self.count_spin.value()
        self.status_label.setText(f"Listing {bank} {start}…{start + count - 1}")

        def operation() -> object:
            return list_streams(source, bank, start, count)

        def done(result: object) -> None:
            assert isinstance(result, list)
            self.apply_streams(result)
            self.status_label.setText(f"{len(result)} streams listed from {bank}. Pick one.")

        self._run(operation, done, self._failed)

    def _stream_picked(self) -> None:
        items = self.stream_list.selectedItems()
        if items:
            self.stream_field.setText(str(items[0].data(Qt.UserRole)))

    def _choose_audio(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose your recording", str(Path.home()), AUDIO_FILTER)
        if chosen:
            self.audio_field.setText(chosen)

    def _choose_target(self) -> None:
        chosen, _f = QFileDialog.getSaveFileName(self, "Where should the new disc go?",
                                                 "ESPN NFL 2K5 (commentary).xiso.iso", IMAGE_FILTER)
        if chosen:
            self.target_field.setText(chosen)
            self._target_generated = False

    def _write(self) -> None:
        source = Path(self.source_field.text())
        target = Path(self.target_field.text())
        if target.exists() and target.resolve() == source.resolve():
            QMessageBox.warning(self, "Same file", "Source and output are the same file. Fix: choose a different output file.")
            return
        try:
            start_seconds = float(self.start_field.text() or 0)
            gain_db = float(self.gain_field.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Numbers needed", "Start and gain must be numbers.")
            return
        stream_id = self.stream_field.text().strip()
        audio = Path(self.audio_field.text())
        retail = Path(self.retail_field.text()) if self.retail_field.text().strip() else None
        answer = QMessageBox.question(
            self, "Make disc with this line?",
            f"Source (unchanged): {source}\n"
            + (f"Replace existing disc copy: {target}" if target.exists() else f"New disc: {target}")
            + f"\n\nLine {stream_id} will be replaced with {audio.name} (cut from {start_seconds:g}s "
              "to the slot length; a shorter recording is padded with silence).\n\n" + XEMU_LINE,
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Ok:
            return

        match = swap_module().RETAIL_SPEECH_RMS_DB if self.loudnorm_check.isChecked() else None

        def operation() -> object:
            return perform_write(source, target, stream_id, audio, retail,
                                 start_seconds=start_seconds, gain_db=gain_db, target_rms_db=match)

        self.write_button.setEnabled(False)
        self.status_label.setText("Copying the disc image and writing the line…")
        self._run(operation, self._done, self._failed)

    def _run(self, operation: Callable[[], object], done: Callable[[object], None],
             failed: Callable[[str], None]) -> None:
        task = _Task(operation)
        task.signals.finished.connect(done)
        task.signals.failed.connect(failed)
        self._task = task
        self._pool.start(task)

    def _done(self, receipt: object) -> None:
        assert isinstance(receipt, dict)
        target = Path(self.target_field.text())
        self.status_label.setText(
            f"Written: {target.name}. {receipt.get('stream')} now holds {receipt.get('clip_seconds')} s of your clip "
            f"(+{receipt.get('padded_silence_frames')} silent frames), gate={receipt.get('retail_gate')}, "
            f"SNR {receipt.get('encode_snr_db')} dB. Read-back verified."
        )
        QMessageBox.information(self, "Disc ready",
                                f"{target}\n\nOpen it in xemu. " + XEMU_LINE)
        self._refresh()

    def _failed(self, message: str) -> None:
        self.status_label.setText(plain_failure("make the disc", message))
        show_operation_error(self, "make the disc", message)
        self._refresh()


__all__ = ["CommentaryPanel", "bank_names", "list_streams", "perform_write"]
