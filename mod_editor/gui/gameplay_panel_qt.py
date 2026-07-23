"""Polished read-only gameplay, save, and franchise inspector for NFL 2K5.

The panel consumes only sanitized evidence returned by the Studio facade.  It
does not expose patch controls, imply that Fantasy Draft weights affect the
rookie draft, or treat fixture save values as the user's live profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, runtime_checkable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPalette
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core.errors import ValidationError


ProgressSink = Callable[[str, int, int], None]


_TABLE_BASE = "#101827"
_TABLE_ALTERNATE = "#17243a"
_TABLE_TEXT = "#e7edf7"
_TABLE_SELECTION = "#2d6ea3"
_TABLE_SELECTION_TEXT = "#ffffff"


@dataclass(frozen=True, slots=True)
class SliderInspectionRow:
    index: int
    name: str
    settings1: object
    franchise1: object


@dataclass(frozen=True, slots=True)
class DraftWeightInspectionRow:
    position_code: int
    position: str
    weight: object


@dataclass(frozen=True, slots=True)
class SaveContainerInspectionRow:
    display_name: str
    container_type: str
    savegame_size: int
    extra_size: int


@dataclass(frozen=True, slots=True)
class FranchiseInspectionRow:
    target_id: str
    title: str
    feasibility: str
    mutation_layer: str
    limitation: str
    current_proof: str
    requirements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GameplayInspectionModel:
    sliders: tuple[SliderInspectionRow, ...]
    draft_weights: tuple[DraftWeightInspectionRow, ...]
    save_containers: tuple[SaveContainerInspectionRow, ...]
    franchise_findings: tuple[FranchiseInspectionRow, ...]
    stock_range: str
    slider_warning: str
    draft_warning: str
    save_warning: str
    franchise_warning: str
    integrity_summary: str


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"Gameplay inspection is missing {label} data.")
    return value


def _sequence(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"Gameplay inspection is missing {label} rows.")
    return tuple(value)


def build_gameplay_inspection_model(
    snapshot: Mapping[str, object],
) -> GameplayInspectionModel:
    """Validate and normalize the facade snapshot without importing retail data."""

    sliders = _mapping(snapshot.get("sliders"), "slider")
    draft = _mapping(snapshot.get("fantasy_draft"), "Fantasy Draft")
    saves = _mapping(snapshot.get("saves"), "save")
    franchise = _mapping(snapshot.get("franchise"), "franchise")

    slider_rows = tuple(
        SliderInspectionRow(
            int(row["index"]),
            str(row["name"]),
            row.get("observed_settings1_value", "—"),
            row.get("observed_franchise1_value", "—"),
        )
        for item in _sequence(sliders.get("sliders"), "slider")
        for row in (_mapping(item, "slider row"),)
    )
    draft_rows = tuple(
        DraftWeightInspectionRow(
            int(row["position_code"]), str(row["position"]), row["weight"]
        )
        for item in _sequence(draft.get("position_weights"), "Fantasy Draft")
        for row in (_mapping(item, "Fantasy Draft row"),)
    )
    if len(slider_rows) != 21:
        raise ValidationError(
            f"Expected 21 mapped gameplay controls; received {len(slider_rows)}."
        )
    if len(draft_rows) != 17:
        raise ValidationError(
            f"Expected 17 Fantasy Draft weights; received {len(draft_rows)}."
        )

    save_rows = tuple(
        SaveContainerInspectionRow(
            str(row["display_name"]),
            str(row["type"]),
            int(row["savegame_size"]),
            int(row["extra_size"]),
        )
        for item in _sequence(saves.get("containers"), "save container")
        for row in (_mapping(item, "save container row"),)
    )
    franchise_rows = tuple(
        FranchiseInspectionRow(
            target_id=str(row["id"]),
            title=str(row["id"]).replace("_", " ").title(),
            feasibility=str(row["feasibility"]),
            mutation_layer=str(row["likely_mutation_layer"]),
            limitation=str(row["user_limitation"]),
            current_proof=str(row["current_proof"]),
            requirements=tuple(
                str(value)
                for value in _sequence(
                    row.get("requirements_before_write"), "writer requirement"
                )
            ),
        )
        for item in _sequence(franchise.get("targets"), "franchise")
        for row in (_mapping(item, "franchise row"),)
    )
    if len(franchise_rows) != 5:
        raise ValidationError(
            f"Expected five bounded franchise findings; received {len(franchise_rows)}."
        )

    stock = _mapping(sliders.get("stock_ui_range"), "stock slider range")
    integrity = _mapping(saves.get("integrity_boundary"), "save integrity")
    integrity_summary = (
        f"Signature owner mapped: {'Yes' if integrity.get('savegame_signature_owned') else 'No'}"
        f"  •  mode {integrity.get('signature_mode', 'unknown')}"
        f"  •  EXTRA {int(integrity.get('extra_size', 0)):,} bytes"
        f"  •  safe writer: {'Available' if integrity.get('safe_writer_available') else 'Not available'}"
    )
    return GameplayInspectionModel(
        sliders=slider_rows,
        draft_weights=draft_rows,
        save_containers=save_rows,
        franchise_findings=franchise_rows,
        stock_range=(
            f"{stock.get('minimum')} to {stock.get('maximum')} "
            f"in steps of {stock.get('step')}"
        ),
        slider_warning=str(sliders.get("warning", "Read-only mapped controls.")),
        draft_warning=str(draft.get("warning", "Fantasy Draft writer unavailable.")),
        save_warning=str(saves.get("warning", "Save writer unavailable.")),
        franchise_warning=str(
            franchise.get("warning", "Franchise writers are not available.")
        ),
        integrity_summary=integrity_summary,
    )


@runtime_checkable
class GameplayPanelHost(Protocol):
    def inspect_gameplay(self, progress: ProgressSink) -> Mapping[str, object]: ...

    def export_gameplay_inspection(
        self, destination: Path, export_format: str, progress: ProgressSink
    ) -> Path: ...


class GameplayPanel(QWidget):
    """Clickable read-only product surface for mapped gameplay evidence."""

    error_raised = pyqtSignal(str)
    export_completed = pyqtSignal(str)

    def __init__(
        self,
        host: GameplayPanelHost,
        *,
        capability_page: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(host, GameplayPanelHost):
            raise TypeError("Gameplay panel host does not implement GameplayPanelHost")
        self.host = host
        self.model: GameplayInspectionModel | None = None
        self.setObjectName("gameplayInspectorPanel")
        self._build_ui(capability_page)
        self._apply_style()
        self.reload()

    @staticmethod
    def _configure_table(table: QTableWidget, stretch_column: int) -> None:
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        palette = table.palette()
        palette.setColor(QPalette.Base, QColor(_TABLE_BASE))
        palette.setColor(QPalette.AlternateBase, QColor(_TABLE_ALTERNATE))
        palette.setColor(QPalette.Text, QColor(_TABLE_TEXT))
        palette.setColor(QPalette.Highlight, QColor(_TABLE_SELECTION))
        palette.setColor(QPalette.HighlightedText, QColor(_TABLE_SELECTION_TEXT))
        table.setPalette(palette)
        table.viewport().setPalette(palette)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(
            stretch_column, QHeaderView.Stretch
        )

    def _build_ui(self, capability_page: QWidget | None) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Sliders & Gameplay")
        title.setObjectName("inspectionTitle")
        subtitle = QLabel(
            "Browse the 21 named controls, 17 Fantasy Draft weights, observed "
            "save boundaries, and five franchise findings already mapped by research."
        )
        subtitle.setObjectName("inspectionMuted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.export_json_button = QPushButton("Export JSON")
        self.export_csv_button = QPushButton("Export CSV")
        header.addWidget(self.export_json_button)
        header.addWidget(self.export_csv_button)
        root.addLayout(header)

        boundary = QLabel(
            "READ-ONLY INSPECTOR  •  No preset, save writeback, or executable "
            "patch is enabled. Displayed save values are pinned research fixtures, "
            "not values read from your current profile."
        )
        boundary.setObjectName("inspectionBoundary")
        boundary.setWordWrap(True)
        root.addWidget(boundary)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_sliders_page(), "21 Sliders")
        self.tabs.addTab(self._build_draft_page(), "17 Fantasy Draft Weights")
        self.tabs.addTab(self._build_save_page(), "Saves && Franchise")
        if capability_page is not None:
            self.tabs.addTab(capability_page, "Capabilities && Limits")
        root.addWidget(self.tabs, 1)

        self.status_label = QLabel("Loading mapped findings…")
        self.status_label.setObjectName("inspectionMuted")
        root.addWidget(self.status_label)

        self.export_json_button.clicked.connect(lambda: self._choose_export("json"))
        self.export_csv_button.clicked.connect(lambda: self._choose_export("csv"))
        self.franchise_table.currentCellChanged.connect(
            lambda row, _column, _previous_row, _previous_column:
                self._show_franchise_details(row)
        )

    def _build_sliders_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        self.slider_note = QLabel("Mapped stock controls; loading exact rows…")
        self.slider_note.setObjectName("inspectionNote")
        self.slider_note.setWordWrap(True)
        layout.addWidget(self.slider_note)
        self.slider_table = QTableWidget(0, 4)
        self.slider_table.setHorizontalHeaderLabels(
            ("#", "Named control", "Settings1 fixture", "Franchise1 fixture")
        )
        self._configure_table(self.slider_table, 1)
        layout.addWidget(self.slider_table, 1)
        return page

    def _build_draft_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        self.draft_note = QLabel("Fantasy Draft ownership; loading exact rows…")
        self.draft_note.setObjectName("inspectionWarning")
        self.draft_note.setWordWrap(True)
        layout.addWidget(self.draft_note)
        self.draft_table = QTableWidget(0, 3)
        self.draft_table.setHorizontalHeaderLabels(
            ("Position code", "Position", "Stock weight")
        )
        self._configure_table(self.draft_table, 1)
        layout.addWidget(self.draft_table, 1)
        caveat = QLabel(
            "Important: this table is proved for CPU Fantasy Draft selection. "
            "It is not the separate Franchise rookie-draft scorer."
        )
        caveat.setObjectName("inspectionBoundary")
        caveat.setWordWrap(True)
        layout.addWidget(caveat)
        return page

    def _build_save_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        self.integrity_label = QLabel("Loading save integrity boundary…")
        self.integrity_label.setObjectName("inspectionNote")
        self.integrity_label.setWordWrap(True)
        layout.addWidget(self.integrity_label)
        split = QSplitter(Qt.Vertical)
        upper = QFrame()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.addWidget(QLabel("Observed save containers"))
        self.save_table = QTableWidget(0, 4)
        self.save_table.setHorizontalHeaderLabels(
            ("Container", "Type", "SAVEGAME.DAT", "EXTRA")
        )
        self._configure_table(self.save_table, 0)
        upper_layout.addWidget(self.save_table, 1)
        split.addWidget(upper)

        lower = QFrame()
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.addWidget(QLabel("Five bounded franchise findings"))
        self.franchise_table = QTableWidget(0, 3)
        self.franchise_table.setHorizontalHeaderLabels(
            ("Feature", "Feasibility", "Likely mutation layer")
        )
        self._configure_table(self.franchise_table, 0)
        lower_layout.addWidget(self.franchise_table, 2)
        self.franchise_details = QTextBrowser()
        self.franchise_details.setOpenExternalLinks(False)
        self.franchise_details.setMinimumHeight(110)
        lower_layout.addWidget(self.franchise_details, 1)
        split.addWidget(lower)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        return page

    def reload(self) -> None:
        try:
            snapshot = self.host.inspect_gameplay(self._set_progress)
            self.model = build_gameplay_inspection_model(snapshot)
            self._populate()
        except BaseException as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self.status_label.setText(f"Gameplay findings unavailable: {message}")
            self.export_json_button.setEnabled(False)
            self.export_csv_button.setEnabled(False)
            self.error_raised.emit(message)

    def _set_progress(self, stage: str, _completed: int, _total: int) -> None:
        self.status_label.setText(stage)

    @staticmethod
    def _set_row(table: QTableWidget, row: int, values: tuple[object, ...]) -> None:
        background = QBrush(
            QColor(_TABLE_ALTERNATE if row % 2 else _TABLE_BASE)
        )
        foreground = QBrush(QColor(_TABLE_TEXT))
        for column, value in enumerate(values):
            text = str(value)
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            item.setBackground(background)
            item.setForeground(foreground)
            table.setItem(row, column, item)

    def _populate(self) -> None:
        assert self.model is not None
        model = self.model
        self.slider_table.setRowCount(len(model.sliders))
        for index, row in enumerate(model.sliders):
            self._set_row(
                self.slider_table,
                index,
                (row.index, row.name, row.settings1, row.franchise1),
            )
        self.slider_note.setText(
            f"Stock menu range: {model.stock_range}. {model.slider_warning}"
        )

        self.draft_table.setRowCount(len(model.draft_weights))
        for index, row in enumerate(model.draft_weights):
            self._set_row(
                self.draft_table,
                index,
                (row.position_code, row.position, row.weight),
            )
        self.draft_note.setText(model.draft_warning)

        self.save_table.setRowCount(len(model.save_containers))
        for index, row in enumerate(model.save_containers):
            self._set_row(
                self.save_table,
                index,
                (
                    row.display_name,
                    row.container_type,
                    f"{row.savegame_size:,} bytes",
                    f"{row.extra_size:,} bytes",
                ),
            )
        self.integrity_label.setText(
            f"{model.integrity_summary}\n{model.save_warning}"
        )

        self.franchise_table.setRowCount(len(model.franchise_findings))
        for index, row in enumerate(model.franchise_findings):
            self._set_row(
                self.franchise_table,
                index,
                (row.title, row.feasibility, row.mutation_layer),
            )
        if model.franchise_findings:
            self.franchise_table.selectRow(0)
            self._show_franchise_details(0)
        self.status_label.setText(
            "Read-only map ready • 21 sliders • 17 Fantasy Draft weights • "
            f"{len(model.save_containers)} observed save containers • 5 franchise findings"
        )
        self.export_json_button.setEnabled(True)
        self.export_csv_button.setEnabled(True)

    def _show_franchise_details(self, row_index: int) -> None:
        if self.model is None or not 0 <= row_index < len(self.model.franchise_findings):
            self.franchise_details.clear()
            return
        row = self.model.franchise_findings[row_index]
        requirements = "".join(f"<li>{value}</li>" for value in row.requirements)
        self.franchise_details.setHtml(
            f"<b>{row.title}</b><p>{row.limitation}</p>"
            f"<p><b>Current proof:</b> {row.current_proof}</p>"
            f"<p><b>Before any writer:</b></p><ul>{requirements}</ul>"
            f"<p>{self.model.franchise_warning}</p>"
        )

    def _choose_export(self, export_format: str) -> None:
        suffix = ".json" if export_format == "json" else ".csv"
        label = "JSON document (*.json)" if export_format == "json" else "CSV table (*.csv)"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Gameplay Inspector {export_format.upper()}",
            str(Path.home() / f"nfl2k5-gameplay-inspection{suffix}"),
            label,
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != suffix:
            destination = destination.with_suffix(suffix)
        try:
            output = self.host.export_gameplay_inspection(
                destination, export_format, self._set_progress
            )
        except BaseException as exc:
            message = str(exc).strip() or exc.__class__.__name__
            QMessageBox.warning(self, "Gameplay report was not exported", message)
            self.error_raised.emit(message)
            return
        self.status_label.setText(f"Exported {output.name}")
        self.export_completed.emit(str(output))

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QLabel#inspectionTitle { font-size: 24px; font-weight: 800; }
            QLabel#inspectionMuted { color: #9eabc0; }
            QLabel#inspectionBoundary {
                color: #ffca80; background: #2b2118; border: 1px solid #76522b;
                border-radius: 7px; padding: 9px 11px; font-weight: 650;
            }
            QLabel#inspectionNote {
                color: #b9dfff; background: #14243a; border: 1px solid #31557b;
                border-radius: 6px; padding: 8px 10px;
            }
            QLabel#inspectionWarning {
                color: #ffd196; background: #2b2118; border: 1px solid #76522b;
                border-radius: 6px; padding: 8px 10px;
            }
            QTableWidget {
                color: #e7edf7;
                background-color: #101827;
                alternate-background-color: #17243a;
                selection-color: #ffffff;
                selection-background-color: #2d6ea3;
                gridline-color: #33445f;
                border: 1px solid #33445f;
                border-radius: 6px;
            }
            QTableWidget:focus { border-color: #4f82ba; }
            QTableWidget::item {
                color: #e7edf7;
                padding: 4px 7px;
                border: 0;
            }
            QTableWidget::item:selected {
                color: #ffffff;
                background-color: #2d6ea3;
            }
            QHeaderView::section {
                color: #dfe8f6;
                background-color: #1d2a40;
                border: 0;
                border-right: 1px solid #33445f;
                border-bottom: 1px solid #405272;
                padding: 6px 8px;
                font-weight: 700;
            }
            QTableCornerButton::section {
                background-color: #1d2a40;
                border: 0;
                border-right: 1px solid #33445f;
                border-bottom: 1px solid #405272;
            }
            QTextBrowser { border: 1px solid #293752; border-radius: 6px; padding: 6px; }
            """
        )


__all__ = [
    "DraftWeightInspectionRow",
    "FranchiseInspectionRow",
    "GameplayInspectionModel",
    "GameplayPanel",
    "GameplayPanelHost",
    "SaveContainerInspectionRow",
    "SliderInspectionRow",
    "build_gameplay_inspection_model",
]
