"""Named NFL 2K5 Main Menu inspector with the universal raw fallback intact."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, runtime_checkable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPalette
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
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
class MenuTransitionRow:
    position: int
    label: str
    initially_drawable: bool | None
    activation_kind: str
    target: str
    status: str


@dataclass(frozen=True, slots=True)
class MenuLayoutRow:
    layout: str
    relation: str
    archive: str
    status: str


@dataclass(frozen=True, slots=True)
class MenuBlockerRow:
    blocker_id: str
    status: str
    needed: str


@dataclass(frozen=True, slots=True)
class MainMenuInspectionModel:
    state_name: str
    initial_selection: str
    cold_boot_reachability: str
    transitions: tuple[MenuTransitionRow, ...]
    layouts: tuple[MenuLayoutRow, ...]
    blockers: tuple[MenuBlockerRow, ...]
    rendering_summary: str


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"Main Menu inspection is missing {label} data.")
    return value


def _sequence(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"Main Menu inspection is missing {label} rows.")
    return tuple(value)


def build_main_menu_inspection_model(
    snapshot: Mapping[str, object],
) -> MainMenuInspectionModel:
    """Validate the sanitized named state graph before rendering it."""

    state = _mapping(snapshot.get("state"), "state")
    rendering = _mapping(snapshot.get("rendering"), "rendering")
    transitions = tuple(
        MenuTransitionRow(
            position=int(row["position"]),
            label=str(row["label"]),
            initially_drawable=(
                bool(row["initially_drawable"])
                if "initially_drawable" in row else None
            ),
            activation_kind=str(activation["kind"]),
            target=str(activation["target"]),
            status=str(activation["status"]),
        )
        for item in _sequence(state.get("rows"), "transition")
        for row in (_mapping(item, "transition row"),)
        for activation in (_mapping(row.get("activation"), "activation"),)
    )
    if len(transitions) != 7:
        raise ValidationError(
            f"Expected seven named NFL Main Menu rows; received {len(transitions)}."
        )
    layouts = tuple(
        MenuLayoutRow(
            layout=str(row["layout"]),
            relation=str(row["relation"]),
            archive=str(row.get("archive", "—")),
            status=str(row["status"]),
        )
        for item in _sequence(snapshot.get("layout_reachability"), "layout")
        for row in (_mapping(item, "layout row"),)
    )
    blockers = tuple(
        MenuBlockerRow(
            blocker_id=str(row["id"]),
            status=str(row["status"]),
            needed=str(row["needed"]),
        )
        for item in _sequence(snapshot.get("known_blockers"), "limitation")
        for row in (_mapping(item, "limitation row"),)
    )
    canvas = rendering.get("logical_canvas")
    if isinstance(canvas, (list, tuple)) and len(canvas) == 2:
        canvas_text = f"{canvas[0]} × {canvas[1]} logical canvas"
    else:
        canvas_text = str(canvas)
    return MainMenuInspectionModel(
        state_name=str(state.get("name", "Main Menu")),
        initial_selection=str(state.get("initial_selection", "Unknown")),
        cold_boot_reachability=str(state.get("cold_boot_reachability", "unproved")),
        transitions=transitions,
        layouts=layouts,
        blockers=blockers,
        rendering_summary=(
            f"Default path: {str(rendering.get('default_path', 'unknown')).replace('_', ' ')}"
            f"  •  {canvas_text}"
            f"  •  framebuffer mapping: {rendering.get('physical_framebuffer_mapping', 'unproved')}"
        ),
    )


@runtime_checkable
class MenusPanelHost(Protocol):
    def inspect_main_menu(self, progress: ProgressSink) -> Mapping[str, object]: ...

    def export_main_menu_inspection(
        self, destination: Path, export_format: str, progress: ProgressSink
    ) -> Path: ...


class MenusPanel(QWidget):
    """Named state/transition inspector plus every-resource raw fallback."""

    error_raised = pyqtSignal(str)
    export_completed = pyqtSignal(str)

    def __init__(
        self,
        host: MenusPanelHost,
        *,
        raw_fallback: QWidget,
        capability_page: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(host, MenusPanelHost):
            raise TypeError("Menus panel host does not implement MenusPanelHost")
        self.host = host
        self.model: MainMenuInspectionModel | None = None
        self.setObjectName("menusInspectorPanel")
        self._build_ui(raw_fallback, capability_page)
        self._apply_style()
        self.reload()

    @staticmethod
    def _configure_table(table: QTableWidget, stretch_column: int) -> None:
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setShowGrid(True)
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
        table.horizontalHeader().setSectionResizeMode(stretch_column, QHeaderView.Stretch)

    def _build_ui(
        self, raw_fallback: QWidget, capability_page: QWidget | None
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Menus & UI")
        title.setObjectName("menuInspectionTitle")
        subtitle = QLabel(
            "Inspect the owned Main Menu state, all seven named transitions, "
            "layout reachability, and the exact research gaps that still block editing."
        )
        subtitle.setObjectName("menuInspectionMuted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.export_json_button = QPushButton("Export JSON")
        self.export_csv_button = QPushButton("Export CSV")
        # Never silent-gray: exports stay clickable; disableReason teaches walls.
        boot_tip = (
            "Named Main Menu findings are still loading. Wait for the map, then export."
        )
        for button in (self.export_json_button, self.export_csv_button):
            button.setEnabled(True)
            button.setToolTip(boot_tip)
            button.setProperty("disableReason", boot_tip)
        header.addWidget(self.export_json_button)
        header.addWidget(self.export_csv_button)
        root.addLayout(header)

        boundary = QLabel(
            "READ-ONLY NAMED INSPECTOR  •  State and transition ownership is mapped. "
            "Menu replacement remains disabled until layout/render/write semantics are bounded."
        )
        boundary.setObjectName("menuInspectionBoundary")
        boundary.setWordWrap(True)
        root.addWidget(boundary)

        self.tabs = QTabWidget()
        self.named_page = self._build_named_page()
        self.tabs.addTab(self.named_page, "Named Main Menu")
        self.tabs.addTab(raw_fallback, "All Raw Resources")
        if capability_page is not None:
            self.tabs.addTab(capability_page, "Capabilities && Limits")
        root.addWidget(self.tabs, 1)

        self.status_label = QLabel("Loading named Main Menu findings…")
        self.status_label.setObjectName("menuInspectionMuted")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(30)
        self.status_label.setContentsMargins(0, 3, 0, 2)
        self.status_label.setToolTip(self.status_label.text())
        root.addWidget(self.status_label)
        self.export_json_button.clicked.connect(lambda: self._choose_export("json"))
        self.export_csv_button.clicked.connect(lambda: self._choose_export("csv"))

    def _lock_export(self, button: QPushButton, tip: str, block: str = "") -> None:
        """Keep export clickable; non-empty block teaches why export is blocked."""
        button.setEnabled(True)
        button.setToolTip(tip if tip else block)
        button.setProperty("disableReason", block)

    def _export_blocked(self, button: QPushButton, title: str) -> bool:
        reason = str(button.property("disableReason") or "").strip()
        if not reason:
            return False
        QMessageBox.information(self, title, reason)
        return True

    def _build_named_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        self.state_summary = QLabel("Loading named state…")
        self.state_summary.setObjectName("menuInspectionNote")
        self.state_summary.setWordWrap(True)
        layout.addWidget(self.state_summary)
        self.transition_table = QTableWidget(0, 6)
        self.transition_table.setHorizontalHeaderLabels(
            ("#", "Menu row", "Initially visible", "Activation", "Destination", "Proof")
        )
        self._configure_table(self.transition_table, 1)
        layout.addWidget(self.transition_table, 3)

        split = QSplitter(Qt.Horizontal)
        layout_panel = QWidget()
        layout_box = QVBoxLayout(layout_panel)
        layout_box.setContentsMargins(0, 0, 0, 0)
        layout_box.addWidget(QLabel("Owned layout relationships"))
        self.layout_table = QTableWidget(0, 4)
        self.layout_table.setHorizontalHeaderLabels(
            ("Layout", "Relationship", "Archive", "Status")
        )
        self._configure_table(self.layout_table, 0)
        layout_box.addWidget(self.layout_table)
        split.addWidget(layout_panel)

        blocker_panel = QWidget()
        blocker_box = QVBoxLayout(blocker_panel)
        blocker_box.setContentsMargins(0, 0, 0, 0)
        blocker_box.addWidget(QLabel("Actionable limitations"))
        self.blocker_browser = QTextBrowser()
        self.blocker_browser.setOpenExternalLinks(False)
        blocker_box.addWidget(self.blocker_browser)
        split.addWidget(blocker_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 2)
        return page

    def reload(self) -> None:
        try:
            snapshot = self.host.inspect_main_menu(self._set_progress)
            self.model = build_main_menu_inspection_model(snapshot)
            self._populate()
        except BaseException as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self._set_status(f"Named Main Menu findings unavailable: {message}")
            tip = (
                f"Named Main Menu findings are unavailable: {message}. "
                "Load a retail-free dump that exposes the named menu map, then retry."
            )
            self._lock_export(self.export_json_button, tip, tip)
            self._lock_export(self.export_csv_button, tip, tip)
            self.error_raised.emit(message)

    def _set_progress(self, stage: str, _completed: int, _total: int) -> None:
        self._set_status(stage)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

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
        self.state_summary.setText(
            f"State: {model.state_name}  •  initial selection: {model.initial_selection}  •  "
            f"cold-boot reachability: {model.cold_boot_reachability}\n"
            f"{model.rendering_summary}"
        )
        self.transition_table.setRowCount(len(model.transitions))
        for index, row in enumerate(model.transitions):
            visible = "Yes" if row.initially_drawable else (
                "No" if row.initially_drawable is False else "Not reported"
            )
            self._set_row(
                self.transition_table,
                index,
                (
                    row.position,
                    row.label,
                    visible,
                    row.activation_kind.replace("_", " "),
                    row.target,
                    row.status.replace("_", " "),
                ),
            )
        self.layout_table.setRowCount(len(model.layouts))
        for index, row in enumerate(model.layouts):
            self._set_row(
                self.layout_table,
                index,
                (
                    row.layout,
                    row.relation.replace("_", " "),
                    row.archive,
                    row.status.replace("_", " "),
                ),
            )
        blockers = "".join(
            f"<p><b>{row.blocker_id.replace('_', ' ').title()}</b> "
            f"<span style='color:#ffca80'>({row.status.replace('_', ' ')})</span><br>"
            f"{row.needed}</p>"
            for row in model.blockers
        )
        self.blocker_browser.setHtml(blockers)
        self._set_status(
            f"Named map ready • {len(model.transitions)} transitions • "
            f"{len(model.layouts)} layout relationships • {len(model.blockers)} limitations"
        )
        ready_tip = (
            "Export the named Main Menu inspection (read-only report). "
            "Menu replacement remains disabled until layout/write semantics are bounded."
        )
        self._lock_export(self.export_json_button, ready_tip, "")
        self._lock_export(self.export_csv_button, ready_tip, "")

    def _choose_export(self, export_format: str) -> None:
        button = (
            self.export_json_button
            if export_format == "json"
            else self.export_csv_button
        )
        if self._export_blocked(
            button, f"Export Named Main Menu {export_format.upper()}"
        ):
            return
        suffix = ".json" if export_format == "json" else ".csv"
        label = "JSON document (*.json)" if export_format == "json" else "CSV table (*.csv)"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Named Main Menu {export_format.upper()}",
            str(Path.home() / f"nfl2k5-main-menu-inspection{suffix}"),
            label,
        )
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != suffix:
            destination = destination.with_suffix(suffix)
        try:
            output = self.host.export_main_menu_inspection(
                destination, export_format, self._set_progress
            )
        except BaseException as exc:
            message = str(exc).strip() or exc.__class__.__name__
            QMessageBox.warning(self, "Main Menu report was not exported", message)
            self.error_raised.emit(message)
            return
        self._set_status(f"Exported {output.name}")
        self.export_completed.emit(str(output))

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QLabel#menuInspectionTitle { font-size: 24px; font-weight: 800; }
            QLabel#menuInspectionMuted { color: #9eabc0; }
            QLabel#menuInspectionBoundary {
                color: #ffca80; background: #2b2118; border: 1px solid #76522b;
                border-radius: 7px; padding: 9px 11px; font-weight: 650;
            }
            QLabel#menuInspectionNote {
                color: #b9dfff; background: #14243a; border: 1px solid #31557b;
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
    "MainMenuInspectionModel",
    "MenuBlockerRow",
    "MenuLayoutRow",
    "MenuTransitionRow",
    "MenusPanel",
    "MenusPanelHost",
    "build_main_menu_inspection_model",
]
