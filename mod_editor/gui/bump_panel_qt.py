"""Jersey bump-map editor for NFL 2K5 uniform packages.

The panel browses the per-uniform ``bump_jersey/pants/sleeve/sock`` chunks
proved editable by the A10 research: pick a disc image, pick a uniform
package, export the retail bump to PNG, author a replacement, preview
before/after, and write the exact fixed span into a COPY of the image.  The
retail image itself is browse/export only: when the chosen file hashes to the
known retail ISO the panel says so loudly, and the writer core additionally
refuses to treat a source as its own target.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
import hashlib
from typing import Any

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core.nfl2k5_bump_strength import (
    read_strengths,
    write_strengths,
)
from mod_editor.core.nfl2k5_bump_texture_writer import (
    RETAIL_XISO_SHA256,
    RETAIL_XISO_SIZE,
    authoring_template,
    export_bump,
    import_bump,
    list_packages,
    package_bump_slots,
    preview_import,
    verify_write,
)


ProgressSink = Callable[[str, int, int], None]

IMAGE_FILTER = "Xbox disc images (*.xiso *.iso *.img);;All files (*)"
PNG_FILTER = "PNG images (*.png)"
XBE_FILTER = "Xbox executables (default.xbe *.xbe);;All files (*)"


class _TaskSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal()


class _Task(QRunnable):
    def __init__(self, operation: Callable[[ProgressSink], object]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.operation(self.signals.progress.emit)
        except BaseException as exc:
            self.signals.error.emit(str(exc).strip() or exc.__class__.__name__)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


# A full 4.7 GB SHA-256 every time a source or target is re-picked is the
# panel's most expensive interaction.  The verdict is memoized per file
# identity (resolved path, size, mtime): the same file picked again answers
# from the cache, and any rewrite moves the identity and re-hashes.  Bounded,
# because a long session may visit many images.
_RETAIL_PROBE_CACHE_LIMIT = 16
_RETAIL_PROBE_CACHE: "OrderedDict[tuple[str, int, int], bool]" = OrderedDict()


def clear_retail_probe_cache() -> None:
    """Forget every memoized retail-image verdict (tests and fresh sessions)."""

    _RETAIL_PROBE_CACHE.clear()


def _retail_probe(path: Path, progress: ProgressSink) -> bool:
    """Full SHA-256, only after the size already matches the retail image."""

    info = path.stat()
    if info.st_size != RETAIL_XISO_SIZE:
        return False
    key = (str(path.expanduser().resolve(strict=True)), info.st_size,
           info.st_mtime_ns)
    cached = _RETAIL_PROBE_CACHE.get(key)
    if cached is not None:
        _RETAIL_PROBE_CACHE.move_to_end(key)
        return cached
    digest = hashlib.sha256()
    read = 0
    size = RETAIL_XISO_SIZE
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
            read += len(chunk)
            progress("Checking image identity", read, size)
    result = digest.hexdigest() == RETAIL_XISO_SHA256
    _RETAIL_PROBE_CACHE[key] = result
    _RETAIL_PROBE_CACHE.move_to_end(key)
    while len(_RETAIL_PROBE_CACHE) > _RETAIL_PROBE_CACHE_LIMIT:
        _RETAIL_PROBE_CACHE.popitem(last=False)
    return result


class BumpPanel(QWidget):
    """Browse, export, and same-footprint-replace uniform bump maps."""

    error_raised = pyqtSignal(str)
    operation_state_changed = pyqtSignal(bool)

    def __init__(
        self,
        facade: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.facade = facade
        self._busy = False
        self._tasks: set[_Task] = set()
        self._pool = QThreadPool(self)
        self._packages: list[dict[str, object]] = []
        self._slots: dict[str, dict[str, object]] = {}
        self._preview: dict[str, object] | None = None
        self._preview_png_path: Path | None = None
        self._target_is_retail = False
        self._syncing_strengths = False
        self.setObjectName("bumpPanel")
        self._build_ui()
        self._connect()
        self._refresh_controls()
        initial_source = getattr(facade, "source_path", None)
        if isinstance(initial_source, Path) and initial_source.is_file():
            self._load_source(initial_source)

    @property
    def operation_in_progress(self) -> bool:
        return self._busy

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        header = QVBoxLayout()
        title = QLabel("Jersey Bump Maps")
        title.setObjectName("bumpTitle")
        subtitle = QLabel(
            "Per-uniform tangent-space bump maps (bump_jersey, bump_pants, "
            "bump_sleeve, bump_sock). Export the retail art, author a PNG at "
            "the slot's exact size (or start from the marked authoring "
            "template), and write it into a copy of the disc image at the "
            "same footprint. Bump strength (the per-material detail scale in "
            "default.xbe) is edited in the section below."
        )
        subtitle.setObjectName("bumpMuted")
        subtitle.setWordWrap(True)
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        self.retail_warning = QLabel(
            "This is the retail disc image. It stays read-only: browse and "
            "export here, and point the write target at your own copy."
        )
        self.retail_warning.setObjectName("bumpRetailWarning")
        self.retail_warning.setWordWrap(True)
        self.retail_warning.setVisible(False)
        root.addWidget(self.retail_warning)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source image"))
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setPlaceholderText(
            "Choose the NFL 2K5 XISO to browse (read-only)"
        )
        source_row.addWidget(self.source_field, 1)
        self.source_button = QPushButton("Choose…")
        source_row.addWidget(self.source_button)
        root.addLayout(source_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Write target"))
        self.target_field = QLineEdit()
        self.target_field.setReadOnly(True)
        self.target_field.setPlaceholderText(
            "Choose your COPY of the image to write into"
        )
        target_row.addWidget(self.target_field, 1)
        self.target_button = QPushButton("Choose…")
        target_row.addWidget(self.target_button)
        root.addLayout(target_row)

        splitter = QSplitter(Qt.Horizontal)
        package_card = QFrame()
        package_card.setObjectName("bumpCard")
        package_layout = QVBoxLayout(package_card)
        package_layout.setContentsMargins(0, 0, 0, 0)
        self.package_table = QTableWidget(0, 3)
        self.package_table.setHorizontalHeaderLabels(("Outer", "Uniform", "Size"))
        self._configure_table(self.package_table, stretch=1)
        package_layout.addWidget(self.package_table, 1)
        splitter.addWidget(package_card)

        slot_card = QFrame()
        slot_card.setObjectName("bumpCard")
        slot_layout = QVBoxLayout(slot_card)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        self.slot_table = QTableWidget(0, 5)
        self.slot_table.setHorizontalHeaderLabels(
            ("Chunk", "Name", "Size", "Mips", "Stored")
        )
        self._configure_table(self.slot_table, stretch=1)
        slot_layout.addWidget(self.slot_table, 1)
        splitter.addWidget(slot_card)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        preview_row = QHBoxLayout()
        before_box = QVBoxLayout()
        self.before_label = QLabel("Retail bump (before)")
        self.before_label.setObjectName("bumpMuted")
        self.before_image = QLabel("Select a bump slot to preview")
        self.before_image.setAlignment(Qt.AlignCenter)
        self.before_image.setMinimumSize(256, 140)
        self.before_image.setObjectName("bumpPreview")
        before_box.addWidget(self.before_label)
        before_box.addWidget(self.before_image, 1)
        after_box = QVBoxLayout()
        self.after_label = QLabel("Authored PNG (after)")
        self.after_label.setObjectName("bumpMuted")
        self.after_image = QLabel("Import a PNG to preview the replacement")
        self.after_image.setAlignment(Qt.AlignCenter)
        self.after_image.setMinimumSize(256, 140)
        self.after_image.setObjectName("bumpPreview")
        after_box.addWidget(self.after_label)
        after_box.addWidget(self.after_image, 1)
        preview_row.addLayout(before_box, 1)
        preview_row.addLayout(after_box, 1)
        root.addLayout(preview_row, 1)

        actions = QHBoxLayout()
        self.template_button = QPushButton("Save authoring template")
        self.export_button = QPushButton("Export PNG")
        self.import_button = QPushButton("Import PNG")
        self.write_button = QPushButton("Write to copy")
        actions.addWidget(self.template_button)
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        actions.addWidget(self.import_button)
        actions.addWidget(self.write_button)
        root.addLayout(actions)

        root.addWidget(self._build_strength_section())

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("bumpMuted")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        progress_row.addWidget(self.progress_label, 1)
        progress_row.addWidget(self.progress_bar)
        root.addLayout(progress_row)

        self.status_label = QLabel("Choose a source disc image to begin.")
        self.status_label.setObjectName("bumpMuted")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

    def _build_strength_section(self) -> QGroupBox:
        box = QGroupBox("Bump strength (default.xbe detail scale)")
        layout = QVBoxLayout(box)

        note = QLabel(
            "The game multiplies each material's bump scale into a 0..255 "
            "byte. Jersey and sleeve share one float in the retail XBE, so "
            "they change together. Sock is stored as a fixed 0 and cannot be "
            "raised. The patched XBE is xemu-only (its signature cannot be "
            "regenerated), so this stays a local/experimental control."
        )
        note.setObjectName("bumpMuted")
        note.setWordWrap(True)
        layout.addWidget(note)

        xbe_row = QHBoxLayout()
        xbe_row.addWidget(QLabel("Source default.xbe"))
        self.xbe_field = QLineEdit()
        self.xbe_field.setReadOnly(True)
        self.xbe_field.setPlaceholderText("Choose the default.xbe to read")
        xbe_row.addWidget(self.xbe_field, 1)
        self.xbe_button = QPushButton("Choose…")
        xbe_row.addWidget(self.xbe_button)
        layout.addLayout(xbe_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Patched copy"))
        self.xbe_out_field = QLineEdit()
        self.xbe_out_field.setReadOnly(True)
        self.xbe_out_field.setPlaceholderText(
            "Choose where to save the patched COPY (must not exist yet)"
        )
        out_row.addWidget(self.xbe_out_field, 1)
        self.xbe_out_button = QPushButton("Choose…")
        out_row.addWidget(self.xbe_out_button)
        layout.addLayout(out_row)

        values_row = QHBoxLayout()
        self.jersey_spin = self._strength_spin()
        self.pants_spin = self._strength_spin()
        self.sleeve_spin = self._strength_spin()
        values_row.addWidget(QLabel("Jersey"))
        values_row.addWidget(self.jersey_spin)
        values_row.addWidget(QLabel("Pants"))
        values_row.addWidget(self.pants_spin)
        values_row.addWidget(QLabel("Sleeve"))
        values_row.addWidget(self.sleeve_spin)
        values_row.addWidget(QLabel("Sock (fixed 0)"))
        values_row.addStretch(1)
        layout.addLayout(values_row)

        apply_row = QHBoxLayout()
        self.xbe_apply_button = QPushButton("Write patched copy")
        apply_row.addStretch(1)
        apply_row.addWidget(self.xbe_apply_button)
        layout.addLayout(apply_row)

        self.xbe_status = QLabel("Choose a default.xbe to read its strengths.")
        self.xbe_status.setObjectName("bumpMuted")
        self.xbe_status.setWordWrap(True)
        layout.addWidget(self.xbe_status)

        self.xbe_button.clicked.connect(self._choose_xbe)
        self.xbe_out_button.clicked.connect(self._choose_xbe_out)
        self.xbe_apply_button.clicked.connect(self._apply_strengths)
        return box

    @staticmethod
    def _strength_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setSingleStep(0.05)
        spin.setDecimals(2)
        return spin

    def _configure_table(self, table: QTableWidget, *, stretch: int) -> None:
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(stretch, QHeaderView.Stretch)

    def _connect(self) -> None:
        self.source_button.clicked.connect(self._choose_source)
        self.target_button.clicked.connect(self._choose_target)
        self.package_table.itemSelectionChanged.connect(self._package_selected)
        self.slot_table.itemSelectionChanged.connect(self._slot_selected)
        self.export_button.clicked.connect(self._export_clicked)
        self.import_button.clicked.connect(self._import_clicked)
        self.write_button.clicked.connect(self._write_clicked)
        self.template_button.clicked.connect(self._template_clicked)
        self.jersey_spin.valueChanged.connect(self._sync_sleeve_from_jersey)
        self.sleeve_spin.valueChanged.connect(self._sync_jersey_from_sleeve)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _run(
        self,
        operation: Callable[[ProgressSink], object],
        on_success: Callable[[object], None],
    ) -> None:
        if self._busy:
            return
        self._busy = True
        self.operation_state_changed.emit(True)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self._refresh_controls()
        task = _Task(operation)
        self._tasks.add(task)
        task.signals.progress.connect(self._progress)
        task.signals.result.connect(on_success)
        task.signals.error.connect(self._failed)

        def finished() -> None:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
                self.operation_state_changed.emit(False)
            self.progress_bar.hide()
            self._refresh_controls()

        task.signals.finished.connect(finished)
        try:
            self._pool.start(task)
        except BaseException:
            self._tasks.discard(task)
            if self._busy:
                self._busy = False
                self.operation_state_changed.emit(False)
            self.progress_bar.hide()
            self._refresh_controls()
            raise

    def _progress(self, stage: str, completed: int, total: int) -> None:
        self.progress_label.setText(stage)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(max(0, min(total, completed)))
        else:
            self.progress_bar.setRange(0, 0)

    def _failed(self, message: str) -> None:
        self._set_status(f"Failed: {message}")
        self.error_raised.emit(message)
        QMessageBox.warning(self, "Bump map editor", message)

    def _refresh_controls(self) -> None:
        ready = not self._busy
        source = bool(self.source_field.text())
        target = bool(self.target_field.text())
        slot_selected = self._selected_slot_name() is not None
        self.source_button.setEnabled(ready)
        self.target_button.setEnabled(ready)
        self.package_table.setEnabled(ready and source)
        self.slot_table.setEnabled(ready and source)
        self.export_button.setEnabled(ready and source and slot_selected)
        self.import_button.setEnabled(ready and source and slot_selected)
        self.write_button.setEnabled(
            ready and source and target and slot_selected
            and self._preview is not None and not self._target_is_retail
        )
        self.template_button.setEnabled(ready)
        self.xbe_button.setEnabled(ready)
        self.xbe_out_button.setEnabled(ready)
        self.xbe_apply_button.setEnabled(
            ready and bool(self.xbe_field.text())
            and bool(self.xbe_out_field.text())
        )

    def _selected_package(self) -> dict[str, object] | None:
        row = self.package_table.currentRow()
        if row < 0 or row >= len(self._packages):
            return None
        return self._packages[row]

    def _selected_slot_name(self) -> str | None:
        row = self.slot_table.currentRow()
        if row < 0:
            return None
        item = self.slot_table.item(row, 1)
        return item.text() if item is not None else None

    def _choose_source(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Choose the NFL 2K5 disc image", str(Path.home()),
            IMAGE_FILTER,
        )
        if chosen:
            self._load_source(Path(chosen))

    def _load_source(self, path: Path) -> None:
        def load(progress: ProgressSink) -> dict[str, object]:
            is_retail = _retail_probe(path, progress)
            rows = list_packages(path)
            return {"path": path, "retail": is_retail, "rows": rows}

        def done(result: object) -> None:
            assert isinstance(result, dict)
            self.retail_warning.setVisible(bool(result["retail"]))
            self.source_field.setText(str(result["path"]))
            self._packages = list(result["rows"])  # type: ignore[arg-type]
            self.slot_table.setRowCount(0)
            self._slots = {}
            self._preview = None
            self._preview_png_path = None
            self._show_packages()
            suffix = " — retail image is read-only" if result["retail"] else ""
            self._set_status(f"{len(self._packages)} uniform package(s) found{suffix}")

        self._set_status("Reading the entry table…")
        self._run(load, done)

    def _show_packages(self) -> None:
        self.package_table.setRowCount(len(self._packages))
        for row, package in enumerate(self._packages):
            outer = QTableWidgetItem(str(package["outer_index"]))
            outer.setData(Qt.UserRole, package["outer_index"])
            label = str(package["logical_name"] or package["name_id"])
            if package.get("cross_extent"):
                label += f"  [{package['pack_name']}+ next pack]"
            name = QTableWidgetItem(label)
            size = QTableWidgetItem(f"{int(package['size']):,}")
            self.package_table.setItem(row, 0, outer)
            self.package_table.setItem(row, 1, name)
            self.package_table.setItem(row, 2, size)

    def _choose_target(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Choose your copy of the disc image", str(Path.home()),
            IMAGE_FILTER,
        )
        if not chosen:
            return
        target = Path(chosen)

        def done(is_retail: object) -> None:
            self._target_is_retail = bool(is_retail)
            self.target_field.setText(str(target))
            if self._target_is_retail:
                self._set_status(
                    "The write target IS the retail image. Choose a copy "
                    "instead — writes to the retail image are refused."
                )
            else:
                self._set_status("Write target set.")

        self._run(lambda progress: _retail_probe(target, progress), done)

    def _package_selected(self) -> None:
        package = self._selected_package()
        if package is None or self._busy:
            return
        source = Path(self.source_field.text())
        outer_index = int(package["outer_index"])

        def done(result: object) -> None:
            assert isinstance(result, dict)
            chunks = result.get("chunks") or []
            self._slots = {str(chunk["name"]): chunk for chunk in chunks}
            self.slot_table.setRowCount(len(chunks))
            for row, chunk in enumerate(chunks):
                values = (
                    str(chunk["chunk_index"]),
                    str(chunk["name"]),
                    f"{chunk['width']}x{chunk['height']}",
                    str(chunk["mip_levels"]),
                    f"{int(chunk['stored_size']):,}",
                )
                for column, value in enumerate(values):
                    self.slot_table.setItem(row, column, QTableWidgetItem(value))
            self._preview = None
            self._preview_png_path = None
            self.before_image.setText("Select a bump slot to preview")
            self.before_image.setPixmap(QPixmap())
            self.after_image.setText("Import a PNG to preview the replacement")
            self.after_image.setPixmap(QPixmap())
            self._set_status(
                f"{result.get('logical_name') or result.get('name_id')}: "
                f"{len(chunks)} bump chunk(s)"
            )

        self._run(lambda progress: package_bump_slots(source, outer_index), done)

    def _slot_selected(self) -> None:
        name = self._selected_slot_name()
        package = self._selected_package()
        if name is None or package is None or self._busy:
            self._refresh_controls()
            return
        source = Path(self.source_field.text())
        outer_index = int(package["outer_index"])
        self._preview = None
        self._preview_png_path = None

        def done(result: object) -> None:
            png, metadata = result  # type: ignore[misc]
            pixmap = QPixmap()
            if not pixmap.loadFromData(png):
                self._set_status("The retail bump could not be previewed.")
                return
            self.before_image.setPixmap(
                pixmap.scaled(
                    self.before_image.size(), Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            self._set_status(
                f"{name}: {metadata['width']}x{metadata['height']}, "
                f"{metadata['mip_levels']} mips — export it or import a PNG"
            )

        self._run(lambda progress: export_bump(source, outer_index, name), done)

    def _export_clicked(self) -> None:
        name = self._selected_slot_name()
        package = self._selected_package()
        if name is None or package is None:
            return
        source = Path(self.source_field.text())
        outer_index = int(package["outer_index"])
        destination, _filter = QFileDialog.getSaveFileName(
            self, "Export bump PNG", f"outer{outer_index}_{name}.png", PNG_FILTER,
        )
        if not destination:
            return
        output = Path(destination)

        def save(progress: ProgressSink) -> Path:
            png, _metadata = export_bump(source, outer_index, name)
            output.write_bytes(png)
            return output

        def done(path: object) -> None:
            self._set_status(f"Exported {name} to {path}")

        self._run(save, done)

    def _import_clicked(self) -> None:
        name = self._selected_slot_name()
        package = self._selected_package()
        if name is None or package is None:
            return
        slot = self._slots.get(name)
        if slot is None:
            return
        source = Path(self.source_field.text())
        outer_index = int(package["outer_index"])
        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose a {slot['width']}x{slot['height']} PNG for {name}",
            str(Path.home()), PNG_FILTER,
        )
        if not chosen:
            return
        png_path = Path(chosen)

        def done(result: object) -> None:
            assert isinstance(result, dict)
            self._preview = result
            self._preview_png_path = png_path
            after = QPixmap()
            if after.loadFromData(result["authored_png"]):  # type: ignore[arg-type]
                self.after_image.setPixmap(
                    after.scaled(
                        self.after_image.size(), Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
            self._set_status(
                f"{name}: preview ready — write it into your copy when ready"
            )

        self._run(
            lambda progress: preview_import(source, outer_index, name, png_path),
            done,
        )

    def _write_clicked(self) -> None:
        name = self._selected_slot_name()
        package = self._selected_package()
        if (
            name is None or package is None or self._preview is None
            or self._preview_png_path is None
        ):
            return
        if self._target_is_retail:
            QMessageBox.warning(
                self, "Bump map editor",
                "The write target is the retail image. Choose a copy first.",
            )
            return
        source = Path(self.source_field.text())
        target = Path(self.target_field.text())
        outer_index = int(package["outer_index"])
        label = str(package.get("logical_name") or outer_index)
        authored_rgba = bytes(self._preview["authored_rgba"])  # type: ignore[arg-type]
        png_path = self._preview_png_path
        confirmation = QMessageBox.question(
            self,
            "Write the bump map into your copy?",
            f"Replace {name} in uniform {label} inside:\n{target}\n\n"
            "The source image is not touched.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirmation != QMessageBox.Ok:
            return

        def write(progress: ProgressSink) -> dict[str, object]:
            progress("Writing bump span", 0, 0)
            evidence = import_bump(source, target, outer_index, name, png_path)
            progress("Verifying written span", 0, 0)
            verification = verify_write(target, outer_index, name, authored_rgba)
            return {"evidence": evidence, "verification": verification}

        def done(result: object) -> None:
            assert isinstance(result, dict)
            evidence = result["evidence"]
            verification = result["verification"]
            if not verification.get("ok"):
                self._set_status("Write finished but verification FAILED.")
                QMessageBox.critical(
                    self, "Bump map editor",
                    "The span was written but did not verify. Restore your "
                    "copy from a clean backup.",
                )
                return
            statistics = evidence["statistics"]
            stored = (
                statistics["recompressed_bytes"]
                + statistics["zero_padding_bytes"]
            )
            absolute = evidence["target"]["absolute_span_offset"]
            location = (
                f"at offset {absolute:,}"
                if isinstance(absolute, int)
                else "split across pack extents "
                + " + ".join(
                    f"{row['pack_name']}@0x{int(row['pack_offset']):x}"
                    for row in evidence["target"]["span_extents"]
                )
            )
            self._set_status(f"Wrote {name} into {target.name} — verified.")
            QMessageBox.information(
                self,
                "Bump map written and verified",
                f"{name} replaced in {evidence['logical_name']} "
                f"(outer {outer_index}).\n\n"
                f"Span: {evidence['target']['span_size']:,} bytes {location}\n"
                f"Changed bytes: {evidence['changed_byte_count']:,}\n"
                f"Recompressed: {statistics['recompressed_bytes']:,} of "
                f"{stored:,} stored bytes\n"
                f"Replacement span sha256:\n"
                f"{evidence['replacement_span_sha256']}\n"
                "Independent re-decode: verified",
            )

        self._run(write, done)

    def _template_clicked(self) -> None:
        name = self._selected_slot_name() or "bump_jersey"
        destination, _filter = QFileDialog.getSaveFileName(
            self, "Save authoring template",
            f"template_{name}.png", PNG_FILTER,
        )
        if not destination:
            return
        output = Path(destination)

        def save(progress: ProgressSink) -> tuple[Path, dict[str, object]]:
            png, metadata = authoring_template(name)
            output.write_bytes(png)
            return output, metadata

        def done(result: object) -> None:
            path, metadata = result  # type: ignore[misc]
            zones = metadata.get("zones") or []
            self._set_status(
                f"Saved {name} template to {path} "
                f"({len(zones)} marked zone(s))"
            )

        self._run(save, done)

    def _choose_xbe(self) -> None:
        chosen, _filter = QFileDialog.getOpenFileName(
            self, "Choose default.xbe", str(Path.home()), XBE_FILTER,
        )
        if not chosen:
            return
        source = Path(chosen)

        def done(result: object) -> None:
            assert isinstance(result, dict)
            strengths = result["strengths"]
            assert isinstance(strengths, dict)
            self._syncing_strengths = True
            try:
                self.jersey_spin.setValue(float(strengths.get("jersey", 0.0)))
                self.pants_spin.setValue(float(strengths.get("pants", 0.0)))
                self.sleeve_spin.setValue(float(strengths.get("sleeve", 0.0)))
            finally:
                self._syncing_strengths = False
            self.xbe_field.setText(str(source))
            retail = " (matches retail sha256)" if result.get(
                "matches_retail_sha256") else ""
            self.xbe_status.setText(
                f"Read strengths from {source.name}{retail}. Jersey and "
                "sleeve share one float; sock is fixed at 0."
            )

        self._run(lambda progress: read_strengths(source), done)

    def _choose_xbe_out(self) -> None:
        chosen, _filter = QFileDialog.getSaveFileName(
            self, "Choose where to save the patched copy",
            "default_patched.xbe", XBE_FILTER,
        )
        if chosen:
            self.xbe_out_field.setText(chosen)

    def _sync_sleeve_from_jersey(self, value: float) -> None:
        if getattr(self, "_syncing_strengths", False):
            return
        self._syncing_strengths = True
        try:
            self.sleeve_spin.setValue(value)
        finally:
            self._syncing_strengths = False

    def _sync_jersey_from_sleeve(self, value: float) -> None:
        if getattr(self, "_syncing_strengths", False):
            return
        self._syncing_strengths = True
        try:
            self.jersey_spin.setValue(value)
        finally:
            self._syncing_strengths = False

    def _apply_strengths(self) -> None:
        source_text = self.xbe_field.text()
        target_text = self.xbe_out_field.text()
        if not source_text or not target_text:
            return
        source = Path(source_text)
        target = Path(target_text)
        jersey = self.jersey_spin.value()
        pants = self.pants_spin.value()
        sleeve = self.sleeve_spin.value()
        overwrite = target.exists()
        target_line = (
            f"New copy: {target}"
            if not overwrite
            else f"REPLACING existing copy: {target}"
        )
        confirmation = QMessageBox.question(
            self,
            "Write a patched default.xbe copy?",
            f"jersey/sleeve {jersey:.2f}, pants {pants:.2f}\n\n"
            f"Source (untouched): {source}\n"
            f"{target_line}\n\n"
            "The copy is xemu-only: its RSA signature stays stale.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirmation != QMessageBox.Ok:
            return

        def write(progress: ProgressSink) -> dict[str, object]:
            progress("Patching bump strengths", 0, 0)
            return write_strengths(
                source, target, jersey=jersey, pants=pants, sleeve=sleeve,
                overwrite=overwrite,
            )

        def done(result: object) -> None:
            assert isinstance(result, dict)
            verified = result.get("verified_strengths") or {}
            changes = result.get("changes") or []
            summary = ", ".join(
                f"{change['slot']} {float(change['old']):.2f}"
                f" -> {float(change['new']):.2f}"
                for change in changes
            )
            self.xbe_status.setText(
                f"Patched copy written to {target.name}: {summary}. "
                "Verified strengths: "
                + ", ".join(
                    f"{slot} {float(value):.2f}"
                    for slot, value in verified.items()
                )
            )
            QMessageBox.information(
                self,
                "Patched default.xbe copy written",
                f"{target}\n\n{summary}\n\n"
                "Keep this xemu-only: the RSA signature cannot be "
                "regenerated, so real hardware will reject it.",
            )

        self._run(write, done)


__all__ = ["BumpPanel"]
