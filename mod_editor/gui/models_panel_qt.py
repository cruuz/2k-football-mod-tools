"""★ Models: export any NFL 2K5 model to glTF for Blender and bring an edited one back.

The page lists every 3D model on the loaded disc (players, helmets, balls,
referees, coaches, cheerleaders, crowds, props, the Crib, menus, trophies,
stadiums), exports the chosen one as a glTF 2.0 file with its textures, skin
and vertex-index lane, and imports an edited glTF/GLB by fitting it back onto
the game's own vertices and writing the rebuilt resource into a COPY of the
disc.  Everything heavy runs on one background thread; the widget stays live.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
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
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import nfl2k5_models as models

IMAGE_FILTER = "Disc images (*.iso *.xiso);;All files (*)"
MODEL_FILTER = "glTF models (*.gltf *.glb);;All files (*)"

FEASIBILITY = (
    "What Models can do today\n\n"
    "EXPORT: every 3D model on the disc opens in Blender as glTF 2.0 with its triangles, UVs (each mesh's own "
    "tiling, the rule the game's vertex shaders use), vertex colours (the _NFL_COLOR attribute; COLOR_0 on "
    "request), normals, the embedded textures the game draws it with, and, for players, referees, coaches, "
    "hands and every other animated model, a skin with the game's joints. Units are metres (the game "
    "authors in centimetres; the root node carries the 0.01 scale). Images carry their nfl2k5_texture_id, so a "
    "stadium export edited in Blender feeds the Stadiums page's texture write-back.\n\n"
    "IMPORT (same-topology): move vertices freely -- sculpt, proportional edit, reshape -- and bring the file "
    "back. The game's vertex count, triangles, bones, weights and materials are kept exactly; positions "
    "(and normals / UVs / vertex colours when the file carries them for exactly matched vertices) are re-encoded "
    "into the game's fixed-point lanes. If an edit leaves the model's retail range the range is widened for you. If "
    "Blender split or re-ordered vertices, the exported vertex-index lane maps them back (tick Include > Data "
    "> Mesh > Attributes when exporting); without it the importer falls back to matching by order or by "
    "nearest vertex and says so.\n\n"
    "NOT YET: adding or removing vertices or triangles, new bones or animations, and body-type / face morph "
    "deltas (their channels are listed in the export). The player body (hi_body) and head (hi_head) are "
    "shared base meshes: editing them changes every player; faces and body types come from per-player morph "
    "weights and textures.\n\n"
    "FIT: the disc reserves a fixed compressed size per model. The importer repacks tighter than the game's "
    "own packer to make room; a very heavy edit can still exceed it, and the report says so instead of writing."
)


class _Signals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, operation: Callable[[], object]) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.signals = _Signals()
        self._operation = operation

    def run(self) -> None:
        try:
            self.signals.finished.emit(self._operation())
        except Exception as exc:  # noqa: BLE001 - one message for the status line
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class ModelsPanel(QWidget):
    """Export & Import Models."""

    def __init__(self, facade: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._task: _Task | None = None
        self._source: models.ModelSource | None = None
        self._source_paths: tuple[Path, Path] | None = None
        self._entries: list[models.ModelEntry] = []
        self._compiled: models.CompiledModelImport | None = None
        self._last_export: models.ExportResult | None = None
        self._busy = False
        self._build()

    # ------------------------------------------------------------------ lifecycle
    def wait_idle(self, timeout_ms: int = 30_000) -> bool:
        return bool(self._pool.waitForDone(timeout_ms))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.wait_idle()
        super().closeEvent(event)

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Every 3D model in the game, out to Blender and back. Pick a model, export it as glTF, edit it, "
            "then import the edited file and write a COPY of your disc. The source disc is never touched."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        top = QHBoxLayout()
        self.source_label = QLabel("Load your NFL 2K5 XISO first (File → Open XISO).")
        self.source_label.setWordWrap(True)
        top.addWidget(self.source_label, 1)
        self.reload_button = QPushButton("List the models")
        self.reload_button.setToolTip("Read every model name from the loaded disc (a few seconds the first time)")
        self.reload_button.clicked.connect(self.reload)
        top.addWidget(self.reload_button)
        help_button = QPushButton("What can I change?")
        help_button.clicked.connect(self._show_feasibility)
        top.addWidget(help_button)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.group_combo = QComboBox()
        self.group_combo.addItem("All models", "")
        for group in models.GROUP_ORDER:
            self.group_combo.addItem(models.GROUP_LABELS[group], group)
        self.group_combo.currentIndexChanged.connect(self._filter)
        filters.addWidget(self.group_combo)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search model names…")
        self.search.textChanged.connect(self._filter)
        filters.addWidget(self.search, 1)
        left_layout.addLayout(filters)
        self.model_list = QListWidget()
        self.model_list.setAccessibleName("Models on the disc")
        self.model_list.itemSelectionChanged.connect(self._selected)
        left_layout.addWidget(self.model_list, 1)
        self.count_label = QLabel("")
        left_layout.addWidget(self.count_label)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Pick a model to see its meshes, vertices, skin, morph channels and textures.")
        right_layout.addWidget(self.details, 1)

        export_box = QGroupBox("Export to glTF (opens in Blender)")
        export_layout = QHBoxLayout(export_box)
        self.export_dir = QLineEdit(str(Path.home() / "2K5 Models"))
        self.export_dir.setToolTip("Folder that receives <model>.gltf, <model>.bin and a README")
        export_layout.addWidget(self.export_dir, 1)
        choose_dir = QPushButton("Folder…")
        choose_dir.clicked.connect(self._choose_export_dir)
        export_layout.addWidget(choose_dir)
        self.export_button = QPushButton("Export selected")
        self.export_button.clicked.connect(self._export)
        export_layout.addWidget(self.export_button)
        self.open_button = QPushButton("Open folder")
        self.open_button.clicked.connect(self._open_export_folder)
        export_layout.addWidget(self.open_button)
        self.color0_check = QCheckBox("Bake vertex colours into COLOR_0")
        self.color0_check.setToolTip("Also write the game's baked vertex lighting as COLOR_0, which Blender multiplies into the "
                                     "texture (the darker in-game look). Off keeps textures at full brightness; the lane is always "
                                     "carried as the _NFL_COLOR attribute either way.")
        export_layout.addWidget(self.color0_check)
        right_layout.addWidget(export_box)

        import_box = QGroupBox("Import an edited glTF / GLB")
        import_layout = QVBoxLayout(import_box)
        row = QHBoxLayout()
        self.edited_field = QLineEdit()
        self.edited_field.setPlaceholderText("The edited .gltf or .glb exported from Blender")
        self.edited_field.textChanged.connect(self._refresh)
        row.addWidget(self.edited_field, 1)
        choose_edited = QPushButton("Choose…")
        choose_edited.clicked.connect(self._choose_edited)
        row.addWidget(choose_edited)
        self.check_button = QPushButton("Check the edited file")
        self.check_button.setToolTip("Fits the file onto the game's vertices and reports what would change; writes nothing")
        self.check_button.clicked.connect(self._check)
        row.addWidget(self.check_button)
        import_layout.addLayout(row)
        options = QHBoxLayout()
        self.normals_check = QCheckBox("Write normals from the file")
        self.normals_check.setChecked(True)
        self.normals_check.setToolTip("Shading normals for exactly matched vertices; off keeps the game's originals")
        options.addWidget(self.normals_check)
        self.uvs_check = QCheckBox("Write UVs from the file")
        self.uvs_check.setToolTip("Texture coordinates for exactly matched vertices, inverted through each mesh's own UV scale/offset "
                                  "(off by default: edit textures on the texture tabs)")
        options.addWidget(self.uvs_check)
        self.colours_check = QCheckBox("Write vertex colours from the file")
        self.colours_check.setChecked(True)
        self.colours_check.setToolTip("The _NFL_COLOR attribute (the game's baked lighting) for exactly matched vertices; "
                                      "an unedited file writes nothing")
        options.addWidget(self.colours_check)
        self.rescale_check = QCheckBox("Widen the range if the edit needs it")
        self.rescale_check.setChecked(True)
        self.rescale_check.setToolTip("Positions outside the mesh's retail range widen its scale/offset; UVs outside O ± S widen the "
                                      "mesh's UV constant the same way")
        options.addWidget(self.rescale_check)
        options.addStretch(1)
        import_layout.addLayout(options)
        row = QHBoxLayout()
        row.addWidget(QLabel("Source image"))
        self.source_field = QLineEdit()
        self.source_field.setPlaceholderText("The disc image to copy (never written)")
        self.source_field.textChanged.connect(self._refresh)
        row.addWidget(self.source_field, 1)
        choose_source = QPushButton("Choose…")
        choose_source.clicked.connect(self._choose_source)
        row.addWidget(choose_source)
        import_layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Write copy to"))
        self.target_field = QLineEdit()
        self.target_field.setPlaceholderText("Where the modified copy will be written")
        self.target_field.textChanged.connect(self._refresh)
        row.addWidget(self.target_field, 1)
        choose_target = QPushButton("Choose…")
        choose_target.clicked.connect(self._choose_target)
        row.addWidget(choose_target)
        self.write_button = QPushButton("Write the copy")
        self.write_button.clicked.connect(self._write)
        row.addWidget(self.write_button)
        import_layout.addLayout(row)
        right_layout.addWidget(import_box)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self._refresh()

    # ------------------------------------------------------------------ state
    @property
    def source_ready(self) -> bool:
        return self._source is not None

    def current_key(self) -> str | None:
        items = self.model_list.selectedItems()
        return str(items[0].data(Qt.UserRole)) if items else None

    def _refresh(self) -> None:
        loaded = self._source is not None
        key = self.current_key()
        self.reload_button.setEnabled(not self._busy and (self._source_paths is not None or self._facade_paths() is not None))
        self.export_button.setEnabled(not self._busy and loaded and key is not None)
        self.open_button.setEnabled(self._last_export is not None)
        self.check_button.setEnabled(not self._busy and loaded and key is not None and bool(self.edited_field.text().strip()))
        source = self.source_field.text().strip()
        target = self.target_field.text().strip()
        self.write_button.setEnabled(not self._busy and self._compiled is not None and bool(source) and bool(target)
                                     and Path(source) != Path(target))

    def _facade_paths(self) -> tuple[Path, Path] | None:
        paths = getattr(self._facade, "models_source_paths", None)
        if isinstance(paths, tuple) and len(paths) == 2:
            return (Path(paths[0]), Path(paths[1]))
        return None

    def set_source_paths(self, pack0_index: Path, inventory: Path) -> None:
        """Point the page at an archive + inventory directly (tests, or a research extraction)."""
        self._source_paths = (Path(pack0_index), Path(inventory))
        self._refresh()

    def _set_busy(self, busy: bool, text: str | None = None) -> None:
        self._busy = busy
        if text is not None:
            self.status_label.setText(text)
        self._refresh()

    def _run(self, operation: Callable[[], object], done: Callable[[object], None],
             failed: Callable[[str], None] | None = None) -> None:
        task = _Task(operation)

        def finish(result: object) -> None:
            self._set_busy(False)
            done(result)

        def fail(message: str) -> None:
            self._set_busy(False)
            (failed or self._failed)(message)

        task.signals.finished.connect(finish)
        task.signals.failed.connect(fail)
        self._task = task
        self._set_busy(True)
        self._pool.start(task)

    def _failed(self, message: str) -> None:
        self.status_label.setText(message)
        self.details.appendPlainText("\n" + message)
        if self.isVisible():                    # never a modal box for a widget nobody can see (tests, headless)
            QMessageBox.critical(self, "Models", message)

    # ------------------------------------------------------------------ catalog
    def reload(self) -> None:
        paths = self._source_paths or self._facade_paths()
        if paths is None:
            self.status_label.setText("Load your NFL 2K5 XISO first (File → Open XISO).")
            return
        index_path, inventory_path = paths
        self.status_label.setText("Reading the model names from your disc…")
        facade_source = getattr(self._facade, "source_path", None)
        if facade_source and not self.source_field.text().strip():
            self.source_field.setText(str(facade_source))

        def operation() -> object:
            source = models.ModelSource(index_path, inventory_path)
            return source, source.catalog()

        def done(result: object) -> None:
            source, entries = result  # type: ignore[misc]
            self._source, self._entries = source, list(entries)
            self.source_label.setText(f"{len(self._entries):,} models on the loaded disc ({index_path.parent.name}).")
            self._filter()
            self.status_label.setText("Pick a model, then export it or check an edited file.")

        self._run(operation, done)

    def apply_catalog(self, source: models.ModelSource, entries: list[models.ModelEntry]) -> None:
        """Populate synchronously (tests)."""
        self._source, self._entries = source, list(entries)
        self._filter()

    def _filter(self) -> None:
        group = str(self.group_combo.currentData() or "")
        needle = self.search.text().strip().lower()
        self.model_list.clear()
        shown = 0
        for entry in self._entries:
            if group and entry.group != group:
                continue
            if needle and needle not in entry.name.lower():
                continue
            item = QListWidgetItem(f"{entry.name}   ·   {models.GROUP_LABELS.get(entry.group, 'Other')}   ·   outer {entry.outer_index} chunk {entry.chunk_index}")
            item.setData(Qt.UserRole, entry.key)
            item.setToolTip(f"{entry.decoded_size:,} bytes decoded, {entry.stored_size:,} stored")
            self.model_list.addItem(item)
            shown += 1
        self.count_label.setText(f"{shown:,} of {len(self._entries):,} models")
        self._refresh()

    def select_key(self, key: str) -> bool:
        for row in range(self.model_list.count()):
            item = self.model_list.item(row)
            if item.data(Qt.UserRole) == key:
                self.model_list.setCurrentItem(item)
                return True
        return False

    def visible_keys(self) -> list[str]:
        return [str(self.model_list.item(i).data(Qt.UserRole)) for i in range(self.model_list.count())]

    def _selected(self) -> None:
        self._compiled = None
        key = self.current_key()
        self._refresh()
        if key is None or self._source is None:
            return
        source = self._source

        def operation() -> object:
            return describe_model(source, key)

        def done(result: object) -> None:
            if self.current_key() == key:
                self.details.setPlainText(str(result))

        self._run(operation, done, lambda message: self.details.setPlainText(message))

    # ------------------------------------------------------------------ export
    def _choose_export_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Folder for exported models", self.export_dir.text() or str(Path.home()))
        if chosen:
            self.export_dir.setText(chosen)

    def _export(self) -> None:
        key = self.current_key()
        if key is None or self._source is None:
            return
        entry = next((e for e in self._entries if e.key == key), None)
        name = entry.name if entry else key
        folder = Path(self.export_dir.text().strip() or str(Path.home() / "2K5 Models")).expanduser()
        destination = folder / f"{models.safe_file_name(name)}_{key}.gltf"
        self.export_to(destination)

    def export_to(self, destination: Path) -> None:
        key = self.current_key()
        if key is None or self._source is None:
            return
        source = self._source
        color0 = self.color0_check.isChecked()
        self.status_label.setText(f"Exporting {destination.name}…")

        def operation() -> object:
            return models.export_model(source, key, destination, include_vertex_colors_as_color0=color0)

        def done(result: object) -> None:
            assert isinstance(result, models.ExportResult)
            self._last_export = result
            self.status_label.setText(f"Exported: {result.summary()} → {result.gltf_path}")
            self.details.appendPlainText("\n" + result.readme_path.read_text(encoding="utf-8"))
            self._refresh()

        self._run(operation, done)

    def _open_export_folder(self) -> None:
        if self._last_export is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_export.gltf_path.parent)))

    # ------------------------------------------------------------------ import
    def _choose_edited(self) -> None:
        start = self.export_dir.text().strip() or str(Path.home())
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose the edited model", start, MODEL_FILTER)
        if chosen:
            self.edited_field.setText(chosen)

    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose the disc image to copy", str(Path.home()), IMAGE_FILTER)
        if chosen:
            self.source_field.setText(chosen)

    def _choose_target(self) -> None:
        chosen, _f = QFileDialog.getSaveFileName(self, "Choose where to save the copy", "ESPN NFL 2K5 (models).xiso.iso", IMAGE_FILTER)
        if chosen:
            self.target_field.setText(chosen)

    def _check(self) -> None:
        edited = self.edited_field.text().strip()
        if edited:
            self.compile_edited(Path(edited))

    def compile_edited(self, edited: Path) -> None:
        key = self.current_key()
        if key is None or self._source is None:
            return
        source = self._source
        normals, uvs, rescale = self.normals_check.isChecked(), self.uvs_check.isChecked(), self.rescale_check.isChecked()
        colours = self.colours_check.isChecked()
        self._compiled = None
        self.status_label.setText(f"Fitting {edited.name} onto the game's vertices…")

        def operation() -> object:
            return models.compile_import(source, key, edited, write_normals=normals, write_uvs=uvs, allow_rescale=rescale,
                                         write_colours=colours)

        def done(result: object) -> None:
            assert isinstance(result, models.CompiledModelImport)
            self._compiled = result
            self.details.setPlainText(import_report_text(result))
            self.status_label.setText(f"Ready to write: {result.summary()}")
            self._refresh()

        self._run(operation, done)

    def _write(self) -> None:
        source = Path(self.source_field.text().strip())
        target = Path(self.target_field.text().strip())
        if target.exists():
            answer = QMessageBox.question(self, "Replace the existing copy?",
                                          f"{target} already exists and will be replaced.",
                                          QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Ok:
                return
        self.write_copy(source, target)

    def write_copy(self, source_image: Path, target_image: Path) -> None:
        compiled, source = self._compiled, self._source
        if compiled is None or source is None:
            return
        self.status_label.setText(f"Copying the disc and writing {compiled.name}…")

        def operation() -> object:
            return models.write_import_copy(source, compiled, source_image, target_image, overwrite=True)

        def done(result: object) -> None:
            assert isinstance(result, dict)
            self.status_label.setText(f"Written: {target_image} (receipt: {result.get('receipt_path')})")
            if self.isVisible():
                QMessageBox.information(self, "Models copy written",
                                        f"{target_image}\n\n{compiled.summary()}\n\nReceipt: {result.get('receipt_path')}")

        self._run(operation, done)

    def _show_feasibility(self) -> None:
        QMessageBox.information(self, "What can I change?", FEASIBILITY)


# ---------------------------------------------------------------------- text helpers

def describe_model(source: models.ModelSource, key: str) -> str:
    """Human summary of one model: meshes, vertices, lanes, skin, morph channels, textures."""
    resource, decoded, scene = source.parse(key)
    lines = [f"{scene['name']}  (outer {resource.outer_index}, chunk {resource.chunk_index})",
             f"{len(scene['shapes'])} mesh(es), {len(scene['materials'])} material(s), "
             f"{len(scene['embedded_textures'])} embedded texture(s), {len(decoded):,} bytes decoded", ""]
    submesh_counts: dict[int, int] = {}
    for submesh in scene["submeshes"]:
        submesh_counts[int(submesh["shape_index"])] = submesh_counts.get(int(submesh["shape_index"]), 0) + 1
    for shape in scene["shapes"]:
        lanes = models._shape_lanes(scene, shape, decoded)
        parts = [f"{lanes.vertex_count:,} vertices", f"{submesh_counts.get(lanes.index, 0)} submesh(es)",
                 lanes.position_format.lower() + " positions"]
        if lanes.normal:
            parts.append("normals")
        if lanes.texcoord:
            parts.append(f"uvs (tiling x{lanes.uv_scale[0]:.2f} / x{lanes.uv_scale[1]:.2f})")
        if lanes.colour:
            parts.append("vertex colours")
        if lanes.transform_count > 1:
            parts.append(f"skin: {lanes.transform_count} joints")
        channels = models.morph_channels(decoded, lanes)
        if channels:
            parts.append("morph channels: " + ", ".join(c["name"] for c in channels))
        lines.append(f"• {lanes.name}: " + ", ".join(parts))
    lines.append("")
    lines.append("Export writes <model>.gltf + .bin + README next to each other; the README lists what can change.")
    return "\n".join(lines)


def import_report_text(compiled: models.CompiledModelImport) -> str:
    lines = [f"Import check: {compiled.summary()}", ""]
    for shape in compiled.shapes:
        lines.append(f"• {shape.name}: matched by {shape.matched_by}; {shape.covered_vertices:,}/{shape.source_vertices:,} "
                     f"game vertices covered by {shape.edited_vertices:,} in the file; {shape.positions_changed:,} moved "
                     f"(largest move {shape.max_move_cm:.2f} cm), {shape.normals_changed:,} normals, {shape.uvs_changed:,} UVs, "
                     f"{shape.colours_changed:,} vertex colours"
                     + ("; encodable range widened" if shape.rescaled else ""))
        for note in shape.notes:
            lines.append(f"    - {note}")
    if compiled.notes:
        lines.append("")
        lines.extend(f"- {note}" for note in compiled.notes)
    lines += ["", "Nothing has been written yet. Choose the source image and where to write the copy, then Write the copy."]
    return "\n".join(lines)


__all__ = ["ModelsPanel", "describe_model", "import_report_text", "FEASIBILITY"]
