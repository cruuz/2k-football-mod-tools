"""Discoverable, accurately bounded APF helmet/player glTF round-trip panel."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .model_export import (
    MODEL_EXPORT_BOUNDARY,
    ModelExportReceipt,
    TARGETS,
    export_model,
)
from .model_import import (
    MODEL_IMPORT_BOUNDARY,
    ModelImportReceipt,
    import_model,
)


Progress = Callable[[str, int, int], None]
TaskRunner = Callable[[str, Callable[[Progress], object], Callable[[object], None] | None, bool], bool]


class PlayerEquipmentModelExportPanel(QWidget):
    """Two known SCNE POSITION round trips with unsupported lanes explicit."""

    def __init__(self, facade: object, run_task: TaskRunner):
        super().__init__()
        self.facade = facade
        self.run_task = run_task
        self.buttons: dict[str, QPushButton] = {}
        self.import_buttons: dict[str, QPushButton] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading = QLabel("Player & helmet model round trip")
        heading.setObjectName("panelTitle")
        intro = QLabel(
            "Export the stock helmet/equipment assembly or player body as glTF, edit "
            "vertex positions without changing topology, then build a new verified 0A."
        )
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(intro)

        warning = QFrame()
        warning.setObjectName("warningPanel")
        warning_layout = QVBoxLayout(warning)
        warning_layout.setContentsMargins(12, 9, 12, 9)
        warning_title = QLabel("Bounded import — positions only, topology locked")
        warning_title.setObjectName("fieldLabel")
        self.boundary_note = QLabel(f"{MODEL_EXPORT_BOUNDARY} {MODEL_IMPORT_BOUNDARY}")
        self.boundary_note.setObjectName("mutedLabel")
        self.boundary_note.setWordWrap(True)
        warning_layout.addWidget(warning_title)
        warning_layout.addWidget(self.boundary_note)
        layout.addWidget(warning)

        for target in TARGETS:
            card = QFrame()
            card.setObjectName("panel")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            text = QVBoxLayout()
            title = QLabel(target.title)
            title.setObjectName("fieldLabel")
            description = QLabel(target.description)
            description.setObjectName("mutedLabel")
            description.setWordWrap(True)
            text.addWidget(title)
            text.addWidget(description)
            button = QPushButton("Export glTF…")
            button.setObjectName("secondaryButton")
            button.setAccessibleName(f"Export {target.title} glTF")
            button.clicked.connect(
                lambda _checked=False, key=target.key: self._choose_export(key)
            )
            self.buttons[target.key] = button
            import_button = QPushButton("Import edited glTF…")
            import_button.setObjectName("secondaryButton")
            import_button.setAccessibleName(
                f"Import same-topology {target.title} POSITION glTF"
            )
            import_button.clicked.connect(
                lambda _checked=False, key=target.key: self._choose_import(key)
            )
            self.import_buttons[target.key] = import_button
            card_layout.addLayout(text, 1)
            card_layout.addWidget(button)
            card_layout.addWidget(import_button)
            layout.addWidget(card)
        layout.addStretch(1)
        self.set_context()

    def set_context(self) -> None:
        ready = bool(getattr(self.facade, "source_ready", False))
        for button in (*self.buttons.values(), *self.import_buttons.values()):
            button.setEnabled(ready)

    def _choose_export(self, key: str) -> None:
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None)
        if index_0a is None:
            return
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            f"Export APF {key} reference model",
            str(Path.home() / f"apf-{key}-reference.gltf"),
            "glTF model (*.gltf)",
        )
        if not destination:
            return
        path = Path(destination)
        if path.suffix.casefold() != ".gltf":
            path = path.with_suffix(".gltf")
        self.run_task(
            f"Exporting APF {key} reference model",
            lambda progress: export_model(Path(index_0a), key, path, progress),
            self._complete,
            True,
        )

    def _choose_import(self, key: str) -> None:
        source = getattr(self.facade, "source", None)
        index_0a = getattr(source, "index_0a", None)
        if index_0a is None:
            return
        edited, _filter = QFileDialog.getOpenFileName(
            self,
            f"Choose edited APF {key} glTF",
            str(Path.home()),
            "glTF model (*.gltf)",
        )
        if not edited:
            return
        output, _filter = QFileDialog.getSaveFileName(
            self,
            "Save verified replacement 0A",
            str(Path.home() / f"apf-{key}-model-import" / "0A"),
            "APF first archive volume (0A)",
        )
        if not output:
            return
        output_path = Path(output)
        if output_path.name != "0A":
            output_path = output_path.parent / "0A"
        self.run_task(
            f"Importing same-topology APF {key} positions",
            lambda progress: import_model(
                Path(index_0a), key, Path(edited), output_path, progress=progress
            ),
            self._complete,
            True,
        )

    def _complete(self, result: object) -> None:
        if isinstance(result, ModelExportReceipt):
            QMessageBox.information(
                self,
                f"{result.target.title} exported",
                f"Saved {result.gltf.name}, {result.binary.name}, and its source-bound "
                f"manifest to:\n{result.gltf.parent}\n\n{result.mesh_count} meshes · "
                f"{result.vertex_count:,} vertices · {result.triangle_count:,} triangles.\n\n"
                "Edit positions only. Keep the companion manifest and exact topology; "
                "the importer rejects materials, rig/skin edits, extra attributes, and "
                "changed vertex/index counts.",
            )
            return
        if isinstance(result, ModelImportReceipt):
            QMessageBox.information(
                self,
                f"{result.target.title} import verified",
                f"Saved a new {result.output_0a.name} and receipt to:\n"
                f"{result.output_0a.parent}\n\n"
                f"{result.changed_vertex_count:,} vertices changed · maximum POSITION "
                f"quantization error {result.maximum_quantization_error:.8g}.\n\n"
                "Put this 0A beside copies of your unchanged 0B, 1A, 1B, default.xex, "
                "and $SystemUpdate. The source game was not modified.",
            )
            return
        raise ValueError("model round-trip task returned an invalid receipt")


__all__ = ["PlayerEquipmentModelExportPanel"]
