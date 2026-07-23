"""Embeddable PyQt5 text and historical-roster editor for 2K5 Mod Studio.

The panel owns presentation and filtering only.  Retail-derived strings stay
inside the host-owned, private catalog/session and are requested through the
small :class:`TextRosterPanelHost` protocol.  This module contains no launcher,
source extraction, project serialization, or XISO mutation code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol, runtime_checkable

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core.nfl2k5_text_catalog import (
    Nfl2k5TextCatalog,
    RosterNumberAsset,
    RosterPlayer,
    RosterTeam,
    TextAsset,
    encode_fixed_utf16le,
    utf16le_code_units,
)


StatusCallback = Callable[[str], None]
RefreshCallback = Callable[[], None]
ProgressSink = Callable[[str, int, int], None]
TextLookup = Callable[[str], str]
NumberLookup = Callable[[str], int]

STATUS_ALL = "all"
STATUS_EDITABLE = "editable"
STATUS_READ_ONLY = "read_only"
STATUS_MODIFIED = "modified"
TEXT_STATUSES = frozenset(
    {STATUS_ALL, STATUS_EDITABLE, STATUS_READ_ONLY, STATUS_MODIFIED}
)
ESPN_25TH_COMING_SOON_NOTE = (
    "ESPN 25th Anniversary: titles, history, objectives, and dates are Editable. "
    "Team selectors are Preview/Export-only; scenario setup and unlock logic are "
    "Coming Soon."
)


@runtime_checkable
class TextRosterPanelHost(Protocol):
    """The facade-sized contract consumed by :class:`TextRosterPanel`."""

    def text_catalog_snapshot(self, progress: ProgressSink) -> Nfl2k5TextCatalog: ...

    def text_value(self, asset: TextAsset | str) -> str: ...

    def number_value(self, asset: RosterNumberAsset | str) -> int: ...

    def replace_text(
        self, asset: TextAsset | str, value: str, progress: ProgressSink
    ) -> object: ...

    def replace_number(
        self, asset: RosterNumberAsset | str, value: int, progress: ProgressSink
    ) -> object: ...

    def revert_text(self, asset_id: str, progress: ProgressSink) -> object: ...

    def export_text(
        self, asset: TextAsset | str, destination: Path, progress: ProgressSink
    ) -> Path: ...

    def export_number(
        self, asset: RosterNumberAsset | str, destination: Path,
        progress: ProgressSink,
    ) -> Path: ...


@dataclass(frozen=True)
class TextFilter:
    query: str = ""
    bank_id: str | None = None
    status: str = STATUS_ALL


@dataclass(frozen=True)
class TextUsage:
    used_utf16_units: int
    character_limit: int
    allocation_bytes: int
    valid: bool
    message: str


@dataclass(frozen=True)
class HistoricalResource:
    outer_index: int
    resource_label: str
    teams: tuple[RosterTeam, ...]
    players: tuple[RosterPlayer, ...]

    @property
    def display_label(self) -> str:
        if self.teams:
            owner = " / ".join(team.display_name for team in self.teams)
        else:
            owner = "Historical roster"
        return f"{owner} · resource {self.outer_index}"


@dataclass(frozen=True)
class HistoricalPlayerRow:
    resource: HistoricalResource
    player: RosterPlayer

    @property
    def team(self) -> RosterTeam | None:
        return self.resource.teams[0] if self.resource.teams else None


@dataclass(frozen=True)
class CurrentPlayerRow:
    """One player from the current (non-historical) ROST resource."""

    player: RosterPlayer


@dataclass(frozen=True)
class RosterNumberCoverage:
    """Exact UI coverage receipt for the catalog's jersey-number assets."""

    total: int
    current: int
    historical: int
    editable: int
    current_editable: int
    historical_editable: int


def text_usage(asset: TextAsset, value: str) -> TextUsage:
    """Return allocation-aware input state without mutating the host session."""

    try:
        used = utf16le_code_units(value)
        encode_fixed_utf16le(value, asset.allocation_bytes, asset.label)
    except Exception as exc:
        try:
            used = utf16le_code_units(value)
        except Exception:
            used = 0
        return TextUsage(
            used,
            asset.character_limit,
            asset.allocation_bytes,
            False,
            str(exc).strip() or "This value does not fit its existing allocation.",
        )
    return TextUsage(
        used,
        asset.character_limit,
        asset.allocation_bytes,
        True,
        (
            f"{used} of {asset.character_limit} UTF-16 units · "
            f"{asset.allocation_bytes}-byte allocation"
        ),
    )


def text_catalog_summary(catalog: Nfl2k5TextCatalog) -> str:
    """Compact product-capability count shown above the complete text table."""

    return (
        f"{len(catalog.assets):,} strings total · "
        f"{catalog.editable_count:,} Editable · "
        f"{catalog.read_only_count:,} Preview/Export-only"
    )


def _safe_text(asset: TextAsset, lookup: TextLookup | None) -> str:
    if lookup is None:
        return asset.value
    try:
        value = lookup(asset.asset_id)
    except Exception:
        return asset.value
    return value if isinstance(value, str) else asset.value


def _safe_number(original: int, asset_id: str, lookup: NumberLookup | None) -> int:
    if lookup is None:
        return original
    try:
        value = lookup(asset_id)
    except Exception:
        return original
    return value if type(value) is int else original


def text_asset_status(
    asset: TextAsset,
    current_value: TextLookup | None = None,
) -> str:
    if _safe_text(asset, current_value) != asset.value:
        return STATUS_MODIFIED
    return STATUS_EDITABLE if asset.editable else STATUS_READ_ONLY


def filter_text_assets(
    catalog: Nfl2k5TextCatalog,
    criteria: TextFilter,
    current_value: TextLookup | None = None,
) -> tuple[TextAsset, ...]:
    """Search the complete decoded catalog by words, bank, and edit status."""

    status = criteria.status.strip().lower()
    if status not in TEXT_STATUSES:
        raise ValueError(f"Unsupported text status filter: {criteria.status!r}")
    if criteria.bank_id is not None:
        catalog.get_bank(criteria.bank_id)
    terms = tuple(word for word in criteria.query.casefold().split() if word)
    rows: list[TextAsset] = []
    for asset in catalog.assets:
        if criteria.bank_id is not None and asset.bank_id != criteria.bank_id:
            continue
        if status == STATUS_EDITABLE and not asset.editable:
            continue
        if status == STATUS_READ_ONLY and asset.editable:
            continue
        current = (
            _safe_text(asset, current_value)
            if status == STATUS_MODIFIED or terms else asset.value
        )
        actual_status = (
            STATUS_MODIFIED if current != asset.value else
            (STATUS_EDITABLE if asset.editable else STATUS_READ_ONLY)
        )
        if status == STATUS_MODIFIED and actual_status != STATUS_MODIFIED:
            continue
        if terms:
            bank = catalog.get_bank(asset.bank_id)
            haystack = "\n".join(
                (
                    asset.asset_id,
                    asset.label,
                    asset.value,
                    current,
                    bank.bank_id,
                    bank.kind,
                    bank.label,
                    actual_status,
                )
            ).casefold()
            if not all(term in haystack for term in terms):
                continue
        rows.append(asset)
    return tuple(rows)


def historical_resources(
    catalog: Nfl2k5TextCatalog,
) -> tuple[HistoricalResource, ...]:
    """Group all historical teams and players by their owning ROST resource."""

    teams: dict[int, list[RosterTeam]] = {}
    players: dict[int, list[RosterPlayer]] = {}
    labels: dict[int, str] = {}
    for team in catalog.teams:
        if team.historical:
            teams.setdefault(team.outer_index, []).append(team)
            labels[team.outer_index] = team.resource_label
    for player in catalog.players:
        if player.historical:
            players.setdefault(player.outer_index, []).append(player)
            labels[player.outer_index] = player.resource_label
    result: list[HistoricalResource] = []
    for outer_index in sorted(set(teams) | set(players)):
        result.append(HistoricalResource(
            outer_index,
            labels.get(outer_index, "historic"),
            tuple(sorted(teams.get(outer_index, ()), key=lambda item: item.team_index)),
            tuple(sorted(players.get(outer_index, ()), key=lambda item: item.player_index)),
        ))
    return tuple(result)


def current_roster_players(
    catalog: Nfl2k5TextCatalog,
) -> tuple[CurrentPlayerRow, ...]:
    """Return every current-roster player, including read-only secondary rows."""

    return tuple(
        CurrentPlayerRow(player)
        for player in sorted(
            (item for item in catalog.players if not item.historical),
            key=lambda item: (item.outer_index, item.player_index, item.group_id),
        )
    )


def roster_number_coverage(catalog: Nfl2k5TextCatalog) -> RosterNumberCoverage:
    """Prove every player number has exactly one row in current or history views."""

    player_ids = [player.jersey_number_asset_id for player in catalog.players]
    number_ids = [asset.asset_id for asset in catalog.number_assets]
    if len(player_ids) != len(set(player_ids)):
        raise ValueError("Roster players contain duplicate jersey-number asset IDs.")
    if len(number_ids) != len(set(number_ids)):
        raise ValueError("Roster catalog contains duplicate jersey-number asset IDs.")
    if set(player_ids) != set(number_ids):
        raise ValueError(
            "Roster player rows and jersey-number assets are not a one-to-one match."
        )
    players_by_number = {
        player.jersey_number_asset_id: player for player in catalog.players
    }
    current_ids = {
        player.jersey_number_asset_id
        for player in catalog.players if not player.historical
    }
    historical_ids = set(player_ids) - current_ids
    current_editable = sum(
        asset.editable and players_by_number[asset.asset_id].editable
        for asset in catalog.number_assets if asset.asset_id in current_ids
    )
    historical_editable = sum(
        asset.editable and players_by_number[asset.asset_id].editable
        for asset in catalog.number_assets if asset.asset_id in historical_ids
    )
    return RosterNumberCoverage(
        total=len(number_ids),
        current=len(current_ids),
        historical=len(historical_ids),
        editable=current_editable + historical_editable,
        current_editable=current_editable,
        historical_editable=historical_editable,
    )


def _player_status(
    catalog: Nfl2k5TextCatalog,
    player: RosterPlayer,
    text_value: TextLookup | None,
    number_value: NumberLookup | None,
) -> str:
    first = catalog.get_asset(player.first_name_asset_id)
    last = catalog.get_asset(player.last_name_asset_id)
    number = catalog.get_number_asset(player.jersey_number_asset_id)
    if (
        _safe_text(first, text_value) != first.value
        or _safe_text(last, text_value) != last.value
        or _safe_number(number.value, number.asset_id, number_value) != number.value
    ):
        return STATUS_MODIFIED
    return (
        STATUS_EDITABLE
        if player.editable and first.editable and last.editable and number.editable
        else STATUS_READ_ONLY
    )


def filter_current_players(
    catalog: Nfl2k5TextCatalog,
    rows: Iterable[CurrentPlayerRow],
    *,
    query: str = "",
    status: str = STATUS_ALL,
    text_value: TextLookup | None = None,
    number_value: NumberLookup | None = None,
) -> tuple[CurrentPlayerRow, ...]:
    """Search current-roster names/numbers and filter by actionable status."""

    normalized_status = status.strip().lower()
    if normalized_status not in TEXT_STATUSES:
        raise ValueError(f"Unsupported player status filter: {status!r}")
    terms = tuple(word for word in query.casefold().split() if word)
    result: list[CurrentPlayerRow] = []
    for row in rows:
        player = row.player
        actual_status = _player_status(
            catalog, player, text_value, number_value
        )
        if normalized_status != STATUS_ALL and actual_status != normalized_status:
            continue
        if terms:
            first = catalog.get_asset(player.first_name_asset_id)
            last = catalog.get_asset(player.last_name_asset_id)
            number = catalog.get_number_asset(player.jersey_number_asset_id)
            current_first = _safe_text(first, text_value)
            current_last = _safe_text(last, text_value)
            current_number = _safe_number(
                number.value, number.asset_id, number_value
            )
            haystack = "\n".join((
                player.group_id,
                player.resource_label,
                str(player.outer_index),
                player.pool,
                player.display_name,
                first.value,
                last.value,
                current_first,
                current_last,
                str(number.value),
                str(current_number),
                str(player.position_code),
                actual_status,
            )).casefold()
            if not all(term in haystack for term in terms):
                continue
        result.append(row)
    return tuple(result)


def _current_team_name(
    catalog: Nfl2k5TextCatalog,
    team: RosterTeam,
    lookup: TextLookup | None,
) -> str:
    try:
        city = catalog.get_asset(team.asset_id_for("city"))
        nickname = catalog.get_asset(team.asset_id_for("nickname"))
    except KeyError:
        return team.display_name
    return f"{_safe_text(city, lookup)} {_safe_text(nickname, lookup)}".strip()


def filter_historical_players(
    catalog: Nfl2k5TextCatalog,
    resources: Iterable[HistoricalResource],
    *,
    query: str = "",
    outer_index: int | None = None,
    text_value: TextLookup | None = None,
    number_value: NumberLookup | None = None,
) -> tuple[HistoricalPlayerRow, ...]:
    """Filter historical players using original and currently staged values."""

    terms = tuple(word for word in query.casefold().split() if word)
    rows: list[HistoricalPlayerRow] = []
    for resource in resources:
        if outer_index is not None and resource.outer_index != outer_index:
            continue
        team_names = " ".join(
            " ".join((
                team.display_name,
                _current_team_name(catalog, team, text_value),
                *(catalog.get_asset(asset_id).value
                  for _field, asset_id in team.text_asset_ids),
                *(_safe_text(catalog.get_asset(asset_id), text_value)
                  for _field, asset_id in team.text_asset_ids),
            ))
            for team in resource.teams
        ) if terms else ""
        for player in resource.players:
            if terms:
                first = catalog.get_asset(player.first_name_asset_id)
                last = catalog.get_asset(player.last_name_asset_id)
                number = catalog.get_number_asset(player.jersey_number_asset_id)
                current_first = _safe_text(first, text_value)
                current_last = _safe_text(last, text_value)
                current_number = _safe_number(
                    number.value, number.asset_id, number_value
                )
                haystack = "\n".join(
                    (
                        resource.display_label,
                        resource.resource_label,
                        str(resource.outer_index),
                        team_names,
                        player.group_id,
                        player.display_name,
                        first.value,
                        last.value,
                        current_first,
                        current_last,
                        str(number.value),
                        str(current_number),
                        str(player.position_code),
                    )
                ).casefold()
                if not all(term in haystack for term in terms):
                    continue
            rows.append(HistoricalPlayerRow(resource, player))
    return tuple(rows)


def _single_line(value: str, limit: int = 90) -> str:
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


class TextAssetTableModel(QAbstractTableModel):
    """Lazy Qt table model suitable for the complete 17,588-string catalog."""

    HEADERS = ("Text asset", "Bank", "Original", "Current", "Status", "Limit")

    def __init__(self, host: TextRosterPanelHost) -> None:
        super().__init__()
        self.host = host
        self.catalog: Nfl2k5TextCatalog | None = None
        self.rows: tuple[TextAsset, ...] = ()

    def set_rows(
        self, catalog: Nfl2k5TextCatalog, rows: Iterable[TextAsset]
    ) -> None:
        self.beginResetModel()
        self.catalog = catalog
        self.rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> object:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        asset = self.rows[index.row()]
        if role == Qt.UserRole:
            return asset.asset_id
        if role not in {
            Qt.DisplayRole, Qt.ToolTipRole, Qt.ForegroundRole, Qt.FontRole,
        }:
            return None
        current = _safe_text(asset, self.host.text_value)
        status = (
            STATUS_MODIFIED if current != asset.value else
            (STATUS_EDITABLE if asset.editable else STATUS_READ_ONLY)
        )
        bank = self.catalog.get_bank(asset.bank_id) if self.catalog else None
        if role == Qt.DisplayRole:
            return (
                asset.label,
                bank.label if bank else asset.bank_id,
                _single_line(asset.value),
                _single_line(current),
                {
                    STATUS_MODIFIED: "Modified",
                    STATUS_EDITABLE: "Editable",
                    STATUS_READ_ONLY: "Read-only",
                }[status],
                f"{asset.character_limit} units / {asset.allocation_bytes} B",
            )[index.column()]
        if role == Qt.ToolTipRole:
            return (
                f"{asset.label}\n{asset.reason}\n"
                f"Allocation: {asset.character_limit} UTF-16 units, "
                f"{asset.allocation_bytes} bytes"
            )
        if role == Qt.ForegroundRole and index.column() == 4:
            return QColor({
                STATUS_MODIFIED: "#f5c451",
                STATUS_EDITABLE: "#39d98a",
                STATUS_READ_ONLY: "#91a0b5",
            }[status])
        if role == Qt.FontRole and status == STATUS_MODIFIED:
            font = QFont()
            font.setBold(True)
            return font
        return None

    def asset_at(self, row: int) -> TextAsset | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None


class HistoricalPlayerTableModel(QAbstractTableModel):
    HEADERS = ("Resource", "Team", "Player", "#", "Position", "Status")

    def __init__(
        self, host: TextRosterPanelHost, catalog: Nfl2k5TextCatalog
    ) -> None:
        super().__init__()
        self.host = host
        self.catalog = catalog
        self.rows: tuple[HistoricalPlayerRow, ...] = ()

    def set_catalog(self, catalog: Nfl2k5TextCatalog) -> None:
        self.catalog = catalog

    def set_rows(self, rows: Iterable[HistoricalPlayerRow]) -> None:
        self.beginResetModel()
        self.rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> object:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        player = row.player
        if role == Qt.UserRole:
            return player.group_id
        if role not in {
            Qt.DisplayRole, Qt.ForegroundRole, Qt.FontRole,
        }:
            return None
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        current_first = _safe_text(first, self.host.text_value)
        current_last = _safe_text(last, self.host.text_value)
        current_number = _safe_number(
            number.value, number.asset_id, self.host.number_value
        )
        modified = (
            current_first != first.value
            or current_last != last.value
            or current_number != number.value
        )
        team = (
            _current_team_name(self.catalog, row.team, self.host.text_value)
            if row.team else "Historical roster"
        )
        if role == Qt.DisplayRole:
            return (
                str(row.resource.outer_index),
                team,
                _single_line(f"{current_first} {current_last}"),
                str(current_number),
                f"Code {player.position_code}",
                "Modified" if modified else ("Editable" if player.editable else "Read-only"),
            )[index.column()]
        if role == Qt.ForegroundRole and index.column() == 5:
            return QColor("#f5c451" if modified else (
                "#39d98a" if player.editable else "#91a0b5"
            ))
        if role == Qt.FontRole and modified:
            font = QFont()
            font.setBold(True)
            return font
        return None

    def row_at(self, row: int) -> HistoricalPlayerRow | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None


class CurrentPlayerTableModel(QAbstractTableModel):
    """Table model for all current primary and secondary roster players."""

    HEADERS = ("Resource", "Pool", "Player", "#", "Position", "Status")

    def __init__(
        self, host: TextRosterPanelHost, catalog: Nfl2k5TextCatalog
    ) -> None:
        super().__init__()
        self.host = host
        self.catalog = catalog
        self.rows: tuple[CurrentPlayerRow, ...] = ()

    def set_catalog(self, catalog: Nfl2k5TextCatalog) -> None:
        self.catalog = catalog

    def set_rows(self, rows: Iterable[CurrentPlayerRow]) -> None:
        self.beginResetModel()
        self.rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> object:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        player = self.rows[index.row()].player
        if role == Qt.UserRole:
            return player.group_id
        if role not in {Qt.DisplayRole, Qt.ForegroundRole, Qt.FontRole}:
            return None
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        current_first = _safe_text(first, self.host.text_value)
        current_last = _safe_text(last, self.host.text_value)
        current_number = _safe_number(
            number.value, number.asset_id, self.host.number_value
        )
        status = _player_status(
            self.catalog, player, self.host.text_value, self.host.number_value
        )
        if role == Qt.DisplayRole:
            return (
                str(player.outer_index),
                player.pool.replace("_", " ").title(),
                _single_line(f"{current_first} {current_last}"),
                str(current_number),
                f"Code {player.position_code}",
                {
                    STATUS_MODIFIED: "Modified",
                    STATUS_EDITABLE: "Editable",
                    STATUS_READ_ONLY: "Read-only",
                }[status],
            )[index.column()]
        if role == Qt.ForegroundRole and index.column() == 5:
            return QColor({
                STATUS_MODIFIED: "#f5c451",
                STATUS_EDITABLE: "#39d98a",
                STATUS_READ_ONLY: "#91a0b5",
            }[status])
        if role == Qt.FontRole and status == STATUS_MODIFIED:
            font = QFont()
            font.setBold(True)
            return font
        return None

    def row_at(self, row: int) -> CurrentPlayerRow | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None


class TextRosterPanel(QWidget):
    """Universal text browser plus complete current/historical roster editor."""

    def __init__(
        self,
        host: TextRosterPanelHost,
        *,
        view: str = "combined",
        on_status: StatusCallback | None = None,
        on_refresh: RefreshCallback | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if view not in {"combined", "text", "rosters"}:
            raise ValueError(
                "TextRosterPanel view must be combined, text, or rosters"
            )
        self.host = host
        self.view = view
        self.on_status = on_status
        self.on_refresh = on_refresh
        self.catalog: Nfl2k5TextCatalog | None = None
        self.resources: tuple[HistoricalResource, ...] = ()
        self.current_rows: tuple[CurrentPlayerRow, ...] = ()
        self.selected_asset: TextAsset | None = None
        self.selected_current_row: CurrentPlayerRow | None = None
        self.selected_historical_row: HistoricalPlayerRow | None = None
        self.selected_historical_team: RosterTeam | None = None
        self._building = True
        self.setObjectName("textRosterPanel")
        self._build_ui()
        self._apply_style()
        self._building = False
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        heading_copy = {
            "combined": "Text & Rosters",
            "text": "Text & Team Identity",
            "rosters": "Roster Players",
        }
        intro_copy = {
            "combined": (
                "Search every decoded string. Editable entries preserve their existing "
                "allocation; mapped-but-unsafe banks remain export-only with an explanation."
            ),
            "text": (
                "Search every decoded string and edit safe fixed-allocation text. "
                "Shared strings show their affected owners before Apply."
            ),
            "rosters": (
                "Edit proved current and historical player names and jersey numbers. "
                "Unsafe secondary-pool rows remain visible and read-only."
            ),
        }
        heading = QLabel(heading_copy[self.view])
        heading.setObjectName("textPanelHeading")
        intro = QLabel(intro_copy[self.view])
        intro.setWordWrap(True)
        intro.setObjectName("textPanelMuted")
        layout.addWidget(heading)
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        if self.view in {"combined", "text"}:
            self._text_tab = self._build_text_tab()
            self.tabs.addTab(self._text_tab, "All Text")
        if self.view in {"combined", "rosters"}:
            self._current_tab = self._build_current_tab()
            self._historical_tab = self._build_historical_tab()
            self.tabs.addTab(self._current_tab, "Current Roster Players")
            self.tabs.addTab(
                self._historical_tab, "Historical Teams & Players"
            )
        layout.addWidget(self.tabs, 1)

        self.status_label = QLabel("Load an NFL 2K5 XISO to index its text banks.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("textPanelStatus")
        layout.addWidget(self.status_label)

    def _build_text_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        filters = QHBoxLayout()
        self.text_search = QLineEdit()
        self.text_search.setPlaceholderText("Search labels, original/current text, bank, or ID…")
        self.bank_filter = QComboBox()
        self.bank_filter.setMinimumWidth(260)
        self.bank_filter.setMaxVisibleItems(30)
        self.status_filter = QComboBox()
        for label, value in (
            ("All statuses", STATUS_ALL),
            ("Editable", STATUS_EDITABLE),
            ("Read-only", STATUS_READ_ONLY),
            ("Modified", STATUS_MODIFIED),
        ):
            self.status_filter.addItem(label, value)
        self.text_count = QLabel("0 strings")
        self.text_count.setObjectName("textPanelMuted")
        filters.addWidget(self.text_search, 1)
        filters.addWidget(self.bank_filter)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.text_count)
        layout.addLayout(filters)

        self.text_summary = QLabel("0 strings indexed")
        self.text_summary.setObjectName("textPanelSummary")
        self.anniversary_note = QLabel(ESPN_25TH_COMING_SOON_NOTE)
        self.anniversary_note.setObjectName("textPanelCallout")
        self.anniversary_note.setWordWrap(True)
        layout.addWidget(self.text_summary)
        layout.addWidget(self.anniversary_note)

        splitter = QSplitter(Qt.Horizontal)
        self.text_model = TextAssetTableModel(self.host)
        self.text_table = QTableView()
        self.text_table.setModel(self.text_model)
        self.text_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.text_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.text_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.text_table.setSortingEnabled(False)
        self.text_table.verticalHeader().setVisible(False)
        header = self.text_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        splitter.addWidget(self.text_table)
        splitter.addWidget(self._build_text_editor())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.text_search.textChanged.connect(self._apply_text_filter)
        self.bank_filter.currentIndexChanged.connect(self._apply_text_filter)
        self.status_filter.currentIndexChanged.connect(self._apply_text_filter)
        self.text_table.selectionModel().selectionChanged.connect(
            self._text_selection_changed
        )
        return page

    def _build_text_editor(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("textEditorCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(9)
        self.text_title = QLabel("Select a string")
        self.text_title.setObjectName("textEditorTitle")
        self.text_title.setWordWrap(True)
        self.text_meta = QLabel("Bank and ownership details appear here.")
        self.text_meta.setObjectName("textPanelMuted")
        self.text_meta.setWordWrap(True)
        layout.addWidget(self.text_title)
        layout.addWidget(self.text_meta)
        layout.addWidget(QLabel("Original value"))
        self.original_text = QPlainTextEdit()
        self.original_text.setReadOnly(True)
        self.original_text.setMaximumHeight(105)
        layout.addWidget(self.original_text)
        layout.addWidget(QLabel("Current value"))
        self.current_text = QPlainTextEdit()
        self.current_text.setMaximumHeight(120)
        layout.addWidget(self.current_text)
        self.text_limit = QLabel("No allocation selected")
        self.text_limit.setObjectName("textPanelMuted")
        self.text_reason = QLabel("")
        self.text_reason.setWordWrap(True)
        self.text_reason.setObjectName("textPanelMuted")
        layout.addWidget(self.text_limit)
        layout.addWidget(self.text_reason)
        layout.addStretch(1)
        buttons = QHBoxLayout()
        self.apply_text_button = QPushButton("Apply")
        self.revert_text_button = QPushButton("Revert")
        self.export_text_button = QPushButton("Export…")
        buttons.addWidget(self.apply_text_button)
        buttons.addWidget(self.revert_text_button)
        buttons.addWidget(self.export_text_button)
        layout.addLayout(buttons)
        self.current_text.textChanged.connect(self._update_text_usage)
        self.apply_text_button.clicked.connect(self._apply_selected_text)
        self.revert_text_button.clicked.connect(self._revert_selected_text)
        self.export_text_button.clicked.connect(self._export_selected_text)
        self._clear_text_editor()
        return panel

    def _build_current_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        filters = QHBoxLayout()
        self.current_search = QLineEdit()
        self.current_search.setPlaceholderText(
            "Search current player, current name, number, pool, or resource…"
        )
        self.current_status_filter = QComboBox()
        for label, value in (
            ("All statuses", STATUS_ALL),
            ("Editable", STATUS_EDITABLE),
            ("Read-only", STATUS_READ_ONLY),
            ("Modified", STATUS_MODIFIED),
        ):
            self.current_status_filter.addItem(label, value)
        self.current_count = QLabel("0 current players")
        self.current_count.setObjectName("textPanelMuted")
        filters.addWidget(self.current_search, 1)
        filters.addWidget(self.current_status_filter)
        filters.addWidget(self.current_count)
        layout.addLayout(filters)

        self.current_note = QLabel(
            "Primary current-roster players are Editable. Secondary-pool players "
            "remain Preview/Export-only until their writeback contract is proved."
        )
        self.current_note.setObjectName("textPanelCallout")
        self.current_note.setWordWrap(True)
        layout.addWidget(self.current_note)

        splitter = QSplitter(Qt.Horizontal)
        empty_catalog = Nfl2k5TextCatalog((), (), (), (), ())
        self.current_model = CurrentPlayerTableModel(self.host, empty_catalog)
        self.current_table = QTableView()
        self.current_table.setModel(self.current_model)
        self.current_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.current_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.current_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.current_table.verticalHeader().setVisible(False)
        header = self.current_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        splitter.addWidget(self.current_table)
        splitter.addWidget(self._build_current_player_editor())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.current_search.textChanged.connect(self._apply_current_filter)
        self.current_status_filter.currentIndexChanged.connect(
            self._apply_current_filter
        )
        self.current_table.selectionModel().selectionChanged.connect(
            self._current_selection_changed
        )
        return page

    def _build_current_player_editor(self) -> QWidget:
        group = QGroupBox("Current player")
        layout = QGridLayout(group)
        self.current_player_title = QLabel("Select a player")
        self.current_player_title.setWordWrap(True)
        self.current_player_title.setObjectName("textEditorTitle")
        layout.addWidget(self.current_player_title, 0, 0, 1, 3)
        layout.addWidget(QLabel("Field"), 1, 0)
        layout.addWidget(QLabel("Original"), 1, 1)
        layout.addWidget(QLabel("Current"), 1, 2)
        self.current_first_original = QLabel("—")
        self.current_last_original = QLabel("—")
        self.current_number_original = QLabel("—")
        self.current_first = QLineEdit()
        self.current_last = QLineEdit()
        self.current_number = QLineEdit()
        self.current_number.setPlaceholderText("0–99")
        self.current_first_limit = QLabel("")
        self.current_last_limit = QLabel("")
        self.current_first_limit.setObjectName("textPanelMuted")
        self.current_last_limit.setObjectName("textPanelMuted")
        fields = (
            ("First name", self.current_first_original, self.current_first),
            ("Last name", self.current_last_original, self.current_last),
            ("Jersey number", self.current_number_original, self.current_number),
        )
        for row, (label, original, current) in enumerate(fields, start=2):
            layout.addWidget(QLabel(label), row * 2 - 2, 0)
            layout.addWidget(original, row * 2 - 2, 1)
            layout.addWidget(current, row * 2 - 2, 2)
            if row == 2:
                layout.addWidget(self.current_first_limit, row * 2 - 1, 2)
            elif row == 3:
                layout.addWidget(self.current_last_limit, row * 2 - 1, 2)
        self.apply_current_button = QPushButton("Apply Player")
        self.revert_current_button = QPushButton("Revert Player")
        self.export_current_number_button = QPushButton("Export Number…")
        layout.addWidget(self.apply_current_button, 8, 0)
        layout.addWidget(self.revert_current_button, 8, 1)
        layout.addWidget(self.export_current_number_button, 8, 2)
        self.apply_current_button.clicked.connect(self._apply_current_player)
        self.revert_current_button.clicked.connect(self._revert_current_player)
        self.export_current_number_button.clicked.connect(
            self._export_current_number
        )
        self.current_first.textChanged.connect(self._update_current_controls)
        self.current_last.textChanged.connect(self._update_current_controls)
        self.current_number.textChanged.connect(self._update_current_controls)
        self._clear_current_player()
        return group

    def _build_historical_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)
        filters = QHBoxLayout()
        self.historical_search = QLineEdit()
        self.historical_search.setPlaceholderText(
            "Search historical team, player, current name, number, or resource…"
        )
        self.resource_filter = QComboBox()
        self.resource_filter.setMinimumWidth(300)
        self.resource_filter.setMaxVisibleItems(30)
        self.historical_count = QLabel("0 players · 0 resources")
        self.historical_count.setObjectName("textPanelMuted")
        filters.addWidget(self.historical_search, 1)
        filters.addWidget(self.resource_filter)
        filters.addWidget(self.historical_count)
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Horizontal)
        empty_catalog = Nfl2k5TextCatalog((), (), (), (), ())
        self.historical_model = HistoricalPlayerTableModel(
            self.host, empty_catalog
        )
        self.historical_table = QTableView()
        self.historical_table.setModel(self.historical_model)
        self.historical_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.historical_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.historical_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.historical_table.verticalHeader().setVisible(False)
        header = self.historical_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        splitter.addWidget(self.historical_table)

        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.NoFrame)
        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(4, 0, 4, 0)
        editor_layout.addWidget(self._build_historical_team_editor())
        editor_layout.addWidget(self._build_historical_player_editor())
        editor_layout.addStretch(1)
        editor_scroll.setWidget(editor)
        splitter.addWidget(editor_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.historical_search.textChanged.connect(self._apply_historical_filter)
        self.resource_filter.currentIndexChanged.connect(
            self._resource_filter_changed
        )
        self.historical_table.selectionModel().selectionChanged.connect(
            self._historical_selection_changed
        )
        return page

    def _build_historical_team_editor(self) -> QWidget:
        group = QGroupBox("Historical team identity")
        layout = QGridLayout(group)
        self.historical_team_title = QLabel("Select a historical resource")
        self.historical_team_title.setWordWrap(True)
        self.historical_team_title.setObjectName("textEditorTitle")
        layout.addWidget(self.historical_team_title, 0, 0, 1, 3)
        layout.addWidget(QLabel("Field"), 1, 0)
        layout.addWidget(QLabel("Original"), 1, 1)
        layout.addWidget(QLabel("Current"), 1, 2)
        self.team_inputs: dict[str, QLineEdit] = {}
        self.team_originals: dict[str, QLabel] = {}
        self.team_limits: dict[str, QLabel] = {}
        for row, field in enumerate(
            ("city", "nickname", "abbreviation", "city_abbreviation"), start=2
        ):
            label = QLabel(field.replace("_", " ").title())
            original = QLabel("—")
            original.setTextInteractionFlags(Qt.TextSelectableByMouse)
            current = QLineEdit()
            limit = QLabel("")
            limit.setObjectName("textPanelMuted")
            layout.addWidget(label, row * 2 - 2, 0)
            layout.addWidget(original, row * 2 - 2, 1)
            layout.addWidget(current, row * 2 - 2, 2)
            layout.addWidget(limit, row * 2 - 1, 2)
            self.team_inputs[field] = current
            self.team_originals[field] = original
            self.team_limits[field] = limit
            current.textChanged.connect(self._update_team_controls)
        button_row = 10
        self.apply_team_button = QPushButton("Apply Team")
        self.revert_team_button = QPushButton("Revert Team")
        layout.addWidget(self.apply_team_button, button_row, 1)
        layout.addWidget(self.revert_team_button, button_row, 2)
        self.apply_team_button.clicked.connect(self._apply_historical_team)
        self.revert_team_button.clicked.connect(self._revert_historical_team)
        self.apply_team_button.setEnabled(False)
        self.revert_team_button.setEnabled(False)
        return group

    def _build_historical_player_editor(self) -> QWidget:
        group = QGroupBox("Historical player")
        layout = QGridLayout(group)
        self.historical_player_title = QLabel("Select a player")
        self.historical_player_title.setWordWrap(True)
        self.historical_player_title.setObjectName("textEditorTitle")
        layout.addWidget(self.historical_player_title, 0, 0, 1, 3)
        layout.addWidget(QLabel("Field"), 1, 0)
        layout.addWidget(QLabel("Original"), 1, 1)
        layout.addWidget(QLabel("Current"), 1, 2)
        self.player_first_original = QLabel("—")
        self.player_last_original = QLabel("—")
        self.player_number_original = QLabel("—")
        self.player_first = QLineEdit()
        self.player_last = QLineEdit()
        self.player_number = QLineEdit()
        self.player_number.setPlaceholderText("0–99")
        self.player_first_limit = QLabel("")
        self.player_last_limit = QLabel("")
        self.player_first_limit.setObjectName("textPanelMuted")
        self.player_last_limit.setObjectName("textPanelMuted")
        fields = (
            ("First name", self.player_first_original, self.player_first),
            ("Last name", self.player_last_original, self.player_last),
            ("Jersey number", self.player_number_original, self.player_number),
        )
        for row, (label, original, current) in enumerate(fields, start=2):
            layout.addWidget(QLabel(label), row * 2 - 2, 0)
            layout.addWidget(original, row * 2 - 2, 1)
            layout.addWidget(current, row * 2 - 2, 2)
            if row == 2:
                layout.addWidget(self.player_first_limit, row * 2 - 1, 2)
            elif row == 3:
                layout.addWidget(self.player_last_limit, row * 2 - 1, 2)
        self.apply_player_button = QPushButton("Apply Player")
        self.revert_player_button = QPushButton("Revert Player")
        self.export_historical_number_button = QPushButton("Export Number…")
        layout.addWidget(self.apply_player_button, 8, 0)
        layout.addWidget(self.revert_player_button, 8, 1)
        layout.addWidget(self.export_historical_number_button, 8, 2)
        self.apply_player_button.clicked.connect(self._apply_historical_player)
        self.revert_player_button.clicked.connect(self._revert_historical_player)
        self.export_historical_number_button.clicked.connect(
            self._export_historical_number
        )
        self.player_first.textChanged.connect(self._update_player_controls)
        self.player_last.textChanged.connect(self._update_player_controls)
        self.player_number.textChanged.connect(self._update_player_controls)
        self.apply_player_button.setEnabled(False)
        self.revert_player_button.setEnabled(False)
        return group

    def reload(self) -> None:
        """Reload immutable catalog metadata and all current staged values."""

        selected_asset_id = self.selected_asset.asset_id if self.selected_asset else None
        selected_player_id = (
            self.selected_historical_row.player.group_id
            if self.selected_historical_row else None
        )
        selected_current_player_id = (
            self.selected_current_row.player.group_id
            if self.selected_current_row else None
        )
        try:
            catalog = self.host.text_catalog_snapshot(self._progress)
            if not isinstance(catalog, Nfl2k5TextCatalog):
                raise TypeError("text_catalog_snapshot returned an unsupported object")
        except Exception as exc:
            self.catalog = None
            self.resources = ()
            self.current_rows = ()
            if self.view != "rosters":
                self.text_summary.setText("0 strings indexed")
                self.text_model.set_rows(
                    Nfl2k5TextCatalog((), (), (), (), ()), ()
                )
                self._clear_text_editor()
            if self.view != "text":
                self.current_model.set_rows(())
                self.historical_model.set_rows(())
                self._clear_current_player()
                self._clear_historical_player()
            self._status(
                str(exc).strip()
                or "Text and roster data are unavailable until a source is loaded."
            )
            return
        self.catalog = catalog
        if self.view != "rosters":
            self.text_summary.setText(text_catalog_summary(catalog))
            self._populate_bank_filter()
            self._apply_text_filter(select_asset_id=selected_asset_id)
        else:
            self.selected_asset = None

        coverage = None
        if self.view != "text":
            self.resources = historical_resources(catalog)
            self.current_rows = current_roster_players(catalog)
            coverage = roster_number_coverage(catalog)
            if coverage.current != len(self.current_rows):
                raise ValueError(
                    "Current roster view does not cover every current number."
                )
            if coverage.historical != sum(
                len(resource.players) for resource in self.resources
            ):
                raise ValueError(
                    "Historical roster view does not cover every historical number."
                )
            self.current_model.set_catalog(catalog)
            self.historical_model.set_catalog(catalog)
            self._populate_resource_filter()
            self._apply_current_filter(
                select_player_id=selected_current_player_id
            )
            self._apply_historical_filter(select_player_id=selected_player_id)
        else:
            self.resources = ()
            self.current_rows = ()
            self.selected_current_row = None
            self.selected_historical_row = None
            self.selected_historical_team = None

        if self.view == "text":
            self._status(
                f"Text ready • {len(catalog.assets):,} strings",
                detail=(
                    f"Indexed {len(catalog.assets):,} strings "
                    f"({catalog.editable_count:,} Editable) across "
                    f"{len(catalog.banks):,} banks."
                ),
            )
            return
        assert coverage is not None
        if self.view == "rosters":
            self._status(
                f"Rosters ready • {coverage.total:,} jersey numbers",
                detail=(
                    f"Indexed all {coverage.total:,} jersey numbers: "
                    f"{coverage.current:,} current and "
                    f"{coverage.historical:,} historical."
                ),
            )
            return
        self._status(
            f"Text & rosters ready • {len(catalog.assets):,} strings • "
            f"{coverage.total:,} jersey numbers",
            detail=(
                f"Indexed {len(catalog.assets):,} strings "
                f"({catalog.editable_count:,} Editable) across "
                f"{len(catalog.banks):,} banks and all {coverage.total:,} "
                f"jersey numbers: {coverage.current:,} current and "
                f"{coverage.historical:,} historical."
            ),
        )

    def _populate_bank_filter(self) -> None:
        assert self.catalog is not None
        selected = self.bank_filter.currentData()
        self.bank_filter.blockSignals(True)
        self.bank_filter.clear()
        self.bank_filter.addItem("All banks", None)
        for bank in self.catalog.banks:
            suffix = {
                "editable": "Editable",
                "mixed": "Editable + Preview/Export-only",
                "read_only": "Preview/Export-only",
            }.get(bank.access, bank.access)
            self.bank_filter.addItem(
                f"{bank.kind} · {bank.label} · {suffix}", bank.bank_id
            )
        index = self.bank_filter.findData(selected)
        self.bank_filter.setCurrentIndex(index if index >= 0 else 0)
        self.bank_filter.blockSignals(False)

    def _populate_resource_filter(self) -> None:
        selected = self.resource_filter.currentData()
        self.resource_filter.blockSignals(True)
        self.resource_filter.clear()
        self.resource_filter.addItem(f"All historical resources ({len(self.resources)})", None)
        for resource in self.resources:
            self.resource_filter.addItem(resource.display_label, resource.outer_index)
        index = self.resource_filter.findData(selected)
        self.resource_filter.setCurrentIndex(index if index >= 0 else 0)
        self.resource_filter.blockSignals(False)

    def _apply_text_filter(
        self, *_args: object, select_asset_id: str | None = None
    ) -> None:
        if self.catalog is None:
            return
        criteria = TextFilter(
            self.text_search.text(),
            self.bank_filter.currentData(),
            self.status_filter.currentData() or STATUS_ALL,
        )
        rows = filter_text_assets(self.catalog, criteria, self.host.text_value)
        self.text_model.set_rows(self.catalog, rows)
        self.text_count.setText(f"{len(rows):,} of {len(self.catalog.assets):,} strings")
        target = next(
            (index for index, asset in enumerate(rows)
             if asset.asset_id == select_asset_id),
            0 if rows else -1,
        )
        if target >= 0:
            self.text_table.selectRow(target)
        else:
            self.selected_asset = None
            self._clear_text_editor()

    def _text_selection_changed(self, *_args: object) -> None:
        indexes = self.text_table.selectionModel().selectedRows()
        asset = self.text_model.asset_at(indexes[0].row()) if indexes else None
        self.selected_asset = asset
        if asset is None or self.catalog is None:
            self._clear_text_editor()
            return
        bank = self.catalog.get_bank(asset.bank_id)
        current = _safe_text(asset, self.host.text_value)
        self.text_title.setText(asset.label)
        self.text_meta.setText(
            f"{bank.kind} · {bank.label}\n{asset.asset_id}\n"
            f"{asset.encoding} · {asset.reference_count} known reference(s)"
        )
        self.original_text.setPlainText(asset.value)
        self.current_text.blockSignals(True)
        self.current_text.setPlainText(current)
        self.current_text.blockSignals(False)
        self.current_text.setReadOnly(not asset.editable)
        self.text_reason.setText(asset.reason)
        self.export_text_button.setEnabled(True)
        self._update_text_usage()

    def _clear_text_editor(self) -> None:
        self.selected_asset = None
        self.text_title.setText("Select a string")
        self.text_meta.setText("Bank and ownership details appear here.")
        self.original_text.clear()
        self.current_text.blockSignals(True)
        self.current_text.clear()
        self.current_text.blockSignals(False)
        self.current_text.setReadOnly(True)
        self.text_limit.setText("No allocation selected")
        self.text_reason.clear()
        self.apply_text_button.setEnabled(False)
        self.revert_text_button.setEnabled(False)
        self.export_text_button.setEnabled(False)

    def _update_text_usage(self) -> None:
        asset = self.selected_asset
        if asset is None:
            return
        current = self.current_text.toPlainText()
        usage = text_usage(asset, current)
        self.text_limit.setText(usage.message)
        self.text_limit.setStyleSheet("" if usage.valid else "color: #ff7b84;")
        original_current = _safe_text(asset, self.host.text_value)
        self.apply_text_button.setEnabled(
            asset.editable and usage.valid and current != original_current
        )
        self.revert_text_button.setEnabled(
            asset.editable and original_current != asset.value
        )

    def _apply_selected_text(self) -> None:
        asset = self.selected_asset
        if asset is None:
            return
        value = self.current_text.toPlainText()
        usage = text_usage(asset, value)
        if not asset.editable or not usage.valid:
            self._status(asset.reason if not asset.editable else usage.message)
            return
        try:
            self.host.replace_text(asset.asset_id, value, self._progress)
        except Exception as exc:
            self._status(str(exc).strip() or "Could not apply that text edit.")
            return
        self._changed(f"Applied {asset.label}.", asset_id=asset.asset_id)

    def _revert_selected_text(self) -> None:
        asset = self.selected_asset
        if asset is None:
            return
        try:
            self.host.revert_text(asset.asset_id, self._progress)
        except Exception as exc:
            self._status(str(exc).strip() or "Could not revert that text edit.")
            return
        self._changed(f"Reverted {asset.label}.", asset_id=asset.asset_id)

    def _export_selected_text(self) -> None:
        asset = self.selected_asset
        if asset is None:
            return
        suggested = asset.asset_id.replace(":", "-").replace(".", "-") + ".txt"
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Export text", suggested, "Text files (*.txt);;All files (*)"
        )
        if not selected:
            return
        try:
            destination = self.host.export_text(
                asset.asset_id, Path(selected), self._progress
            )
        except Exception as exc:
            self._status(str(exc).strip() or "Could not export that text entry.")
            return
        self._status(f"Exported {asset.label} to {destination}.")

    def _apply_current_filter(
        self, *_args: object, select_player_id: str | None = None
    ) -> None:
        if self.catalog is None:
            return
        rows = filter_current_players(
            self.catalog,
            self.current_rows,
            query=self.current_search.text(),
            status=self.current_status_filter.currentData() or STATUS_ALL,
            text_value=self.host.text_value,
            number_value=self.host.number_value,
        )
        self.current_model.set_rows(rows)
        editable = sum(
            _player_status(
                self.catalog, row.player,
                self.host.text_value, self.host.number_value,
            ) in {STATUS_EDITABLE, STATUS_MODIFIED}
            and row.player.editable
            for row in rows
        )
        self.current_count.setText(
            f"{len(rows):,} of {len(self.current_rows):,} current players · "
            f"{editable:,} writable"
        )
        target = next(
            (index for index, row in enumerate(rows)
             if row.player.group_id == select_player_id),
            0 if rows else -1,
        )
        if target >= 0:
            self.current_table.selectRow(target)
        else:
            self.selected_current_row = None
            self._clear_current_player()

    def _current_selection_changed(self, *_args: object) -> None:
        indexes = self.current_table.selectionModel().selectedRows()
        row = self.current_model.row_at(indexes[0].row()) if indexes else None
        self.selected_current_row = row
        if row is None:
            self._clear_current_player()
            return
        self._show_current_player(row)

    def _show_current_player(self, row: CurrentPlayerRow) -> None:
        assert self.catalog is not None
        player = row.player
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        access = "Editable" if (
            player.editable and first.editable and last.editable and number.editable
        ) else "Preview/Export-only"
        self.current_player_title.setText(
            f"{player.display_name} · {player.pool.replace('_', ' ')} · "
            f"resource {player.outer_index} · {access}"
        )
        self.current_first_original.setText(first.value)
        self.current_last_original.setText(last.value)
        self.current_number_original.setText(str(number.value))
        self.current_first.blockSignals(True)
        self.current_last.blockSignals(True)
        self.current_number.blockSignals(True)
        self.current_first.setText(_safe_text(first, self.host.text_value))
        self.current_last.setText(_safe_text(last, self.host.text_value))
        self.current_number.setText(str(_safe_number(
            number.value, number.asset_id, self.host.number_value
        )))
        self.current_first.blockSignals(False)
        self.current_last.blockSignals(False)
        self.current_number.blockSignals(False)
        editable = (
            player.editable and first.editable and last.editable and number.editable
        )
        self.current_first.setEnabled(editable)
        self.current_last.setEnabled(editable)
        self.current_number.setEnabled(editable)
        self.export_current_number_button.setEnabled(True)
        self._update_current_controls()

    def _clear_current_player(self) -> None:
        self.selected_current_row = None
        self.current_player_title.setText("Select a player")
        for widget in (
            self.current_first, self.current_last, self.current_number,
        ):
            widget.clear()
            widget.setEnabled(False)
        for label in (
            self.current_first_original,
            self.current_last_original,
            self.current_number_original,
        ):
            label.setText("—")
        self.current_first_limit.clear()
        self.current_last_limit.clear()
        self.apply_current_button.setEnabled(False)
        self.revert_current_button.setEnabled(False)
        self.export_current_number_button.setEnabled(False)

    def _update_current_controls(self) -> None:
        row = self.selected_current_row
        if row is None or self.catalog is None:
            return
        player = row.player
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        first_usage = text_usage(first, self.current_first.text())
        last_usage = text_usage(last, self.current_last.text())
        self.current_first_limit.setText(first_usage.message)
        self.current_last_limit.setText(last_usage.message)
        self.current_first_limit.setStyleSheet(
            "" if first_usage.valid else "color: #ff7b84;"
        )
        self.current_last_limit.setStyleSheet(
            "" if last_usage.valid else "color: #ff7b84;"
        )
        try:
            jersey = int(self.current_number.text(), 10)
        except ValueError:
            jersey_valid = False
            jersey = -1
        else:
            jersey_valid = number.minimum <= jersey <= number.maximum
        current_first = _safe_text(first, self.host.text_value)
        current_last = _safe_text(last, self.host.text_value)
        current_number = _safe_number(
            number.value, number.asset_id, self.host.number_value
        )
        changed = (
            self.current_first.text() != current_first
            or self.current_last.text() != current_last
            or jersey != current_number
        )
        modified = (
            current_first != first.value
            or current_last != last.value
            or current_number != number.value
        )
        editable = (
            player.editable and first.editable and last.editable and number.editable
        )
        self.apply_current_button.setEnabled(
            editable and first_usage.valid and last_usage.valid
            and jersey_valid and changed
        )
        self.revert_current_button.setEnabled(modified)
        self.current_number.setStyleSheet(
            "" if jersey_valid else "border: 1px solid #ff7b84;"
        )

    def _apply_current_player(self) -> None:
        row = self.selected_current_row
        if row is None or self.catalog is None:
            return
        player = row.player
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        first_value = self.current_first.text()
        last_value = self.current_last.text()
        first_usage = text_usage(first, first_value)
        last_usage = text_usage(last, last_value)
        try:
            jersey = int(self.current_number.text(), 10)
        except ValueError:
            jersey = -1
        if (
            not player.editable or not first.editable or not last.editable
            or not number.editable or not first_usage.valid
            or not last_usage.valid
            or not number.minimum <= jersey <= number.maximum
        ):
            self._status(
                player.reason if not player.editable else
                "Player names must fit their shown allocations and jersey number "
                f"must be {number.minimum} through {number.maximum}."
            )
            return
        try:
            if first_value != _safe_text(first, self.host.text_value):
                self.host.replace_text(first.asset_id, first_value, self._progress)
            if last_value != _safe_text(last, self.host.text_value):
                self.host.replace_text(last.asset_id, last_value, self._progress)
            if jersey != _safe_number(
                number.value, number.asset_id, self.host.number_value
            ):
                self.host.replace_number(number.asset_id, jersey, self._progress)
        except Exception as exc:
            self._status(
                (str(exc).strip() or "Could not apply the current player edit.")
                + " Refresh to review any fields applied before the error."
            )
            self.reload()
            return
        self._changed(
            f"Applied the current player edit for {player.display_name}.",
            current_player_id=player.group_id,
        )

    def _revert_current_player(self) -> None:
        row = self.selected_current_row
        if row is None:
            return
        player = row.player
        try:
            self.host.revert_text(player.first_name_asset_id, self._progress)
            self.host.revert_text(player.last_name_asset_id, self._progress)
            self.host.revert_text(player.jersey_number_asset_id, self._progress)
        except Exception as exc:
            self._status(str(exc).strip() or "Could not revert that current player.")
            self.reload()
            return
        self._changed(
            f"Reverted the current player edit for {player.display_name}.",
            current_player_id=player.group_id,
        )

    def _export_number_asset(self, asset: RosterNumberAsset, title: str) -> None:
        suggested = asset.asset_id.replace(":", "-").replace(".", "-") + ".txt"
        selected, _filter = QFileDialog.getSaveFileName(
            self, title, suggested, "Text files (*.txt);;All files (*)"
        )
        if not selected:
            return
        try:
            destination = self.host.export_number(
                asset.asset_id, Path(selected), self._progress
            )
        except Exception as exc:
            self._status(str(exc).strip() or "Could not export that jersey number.")
            return
        self._status(f"Exported {asset.label} to {destination}.")

    def _export_current_number(self) -> None:
        row = self.selected_current_row
        if row is None or self.catalog is None:
            return
        self._export_number_asset(
            self.catalog.get_number_asset(row.player.jersey_number_asset_id),
            "Export current-roster jersey number",
        )

    def _resource_filter_changed(self, *_args: object) -> None:
        self._apply_historical_filter()
        outer = self.resource_filter.currentData()
        if outer is not None:
            resource = next(
                (item for item in self.resources if item.outer_index == outer), None
            )
            self._show_historical_team(resource.teams[0] if resource and resource.teams else None)

    def _apply_historical_filter(
        self, *_args: object, select_player_id: str | None = None
    ) -> None:
        if self.catalog is None:
            return
        rows = filter_historical_players(
            self.catalog,
            self.resources,
            query=self.historical_search.text(),
            outer_index=self.resource_filter.currentData(),
            text_value=self.host.text_value,
            number_value=self.host.number_value,
        )
        self.historical_model.set_rows(rows)
        self.historical_count.setText(
            f"{len(rows):,} players · {len(self.resources):,} resources"
        )
        target = next(
            (index for index, row in enumerate(rows)
             if row.player.group_id == select_player_id),
            0 if rows else -1,
        )
        if target >= 0:
            self.historical_table.selectRow(target)
        else:
            self.selected_historical_row = None
            self._clear_historical_player()

    def _historical_selection_changed(self, *_args: object) -> None:
        indexes = self.historical_table.selectionModel().selectedRows()
        row = self.historical_model.row_at(indexes[0].row()) if indexes else None
        self.selected_historical_row = row
        if row is None:
            self._clear_historical_player()
            return
        self._show_historical_team(row.team)
        self._show_historical_player(row)

    def _show_historical_team(self, team: RosterTeam | None) -> None:
        self.selected_historical_team = team
        if team is None or self.catalog is None:
            self.historical_team_title.setText("Select a historical resource")
            for field, widget in self.team_inputs.items():
                widget.clear()
                widget.setEnabled(False)
                self.team_originals[field].setText("—")
                self.team_limits[field].clear()
            self.apply_team_button.setEnabled(False)
            self.revert_team_button.setEnabled(False)
            return
        self.historical_team_title.setText(
            f"{_current_team_name(self.catalog, team, self.host.text_value)} · "
            f"ROST outer {team.outer_index}"
        )
        for field, widget in self.team_inputs.items():
            asset = self.catalog.get_asset(team.asset_id_for(field))
            current = _safe_text(asset, self.host.text_value)
            self.team_originals[field].setText(asset.value)
            widget.blockSignals(True)
            widget.setText(current)
            widget.blockSignals(False)
            widget.setEnabled(asset.editable)
        self._update_team_controls()

    def _update_team_controls(self) -> None:
        team = self.selected_historical_team
        if team is None or self.catalog is None:
            return
        valid = team.editable
        changed = False
        modified = False
        for field, widget in self.team_inputs.items():
            asset = self.catalog.get_asset(team.asset_id_for(field))
            usage = text_usage(asset, widget.text())
            self.team_limits[field].setText(usage.message)
            self.team_limits[field].setStyleSheet(
                "" if usage.valid else "color: #ff7b84;"
            )
            current = _safe_text(asset, self.host.text_value)
            valid = valid and asset.editable and usage.valid
            changed = changed or widget.text() != current
            modified = modified or current != asset.value
        self.apply_team_button.setEnabled(valid and changed)
        self.revert_team_button.setEnabled(modified)

    def _apply_historical_team(self) -> None:
        team = self.selected_historical_team
        if team is None or self.catalog is None:
            return
        pending: list[tuple[TextAsset, str]] = []
        for field, widget in self.team_inputs.items():
            asset = self.catalog.get_asset(team.asset_id_for(field))
            value = widget.text()
            usage = text_usage(asset, value)
            if not asset.editable or not usage.valid:
                self._status(asset.reason if not asset.editable else usage.message)
                return
            if value != _safe_text(asset, self.host.text_value):
                pending.append((asset, value))
        try:
            for asset, value in pending:
                self.host.replace_text(asset.asset_id, value, self._progress)
        except Exception as exc:
            self._status(
                (str(exc).strip() or "Could not apply the team identity edit.")
                + " Refresh to review any fields applied before the error."
            )
            self.reload()
            return
        self._changed(
            f"Applied {len(pending)} identity field(s) for {team.display_name}.",
            player_id=(
                self.selected_historical_row.player.group_id
                if self.selected_historical_row else None
            ),
        )

    def _revert_historical_team(self) -> None:
        team = self.selected_historical_team
        if team is None:
            return
        try:
            for _field, asset_id in team.text_asset_ids:
                self.host.revert_text(asset_id, self._progress)
        except Exception as exc:
            self._status(str(exc).strip() or "Could not revert that team identity.")
            self.reload()
            return
        self._changed(
            f"Reverted the identity fields for {team.display_name}.",
            player_id=(
                self.selected_historical_row.player.group_id
                if self.selected_historical_row else None
            ),
        )

    def _show_historical_player(self, row: HistoricalPlayerRow) -> None:
        assert self.catalog is not None
        player = row.player
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        self.historical_player_title.setText(
            f"{player.display_name} · resource {row.resource.outer_index} · "
            f"position code {player.position_code}"
        )
        self.player_first_original.setText(first.value)
        self.player_last_original.setText(last.value)
        self.player_number_original.setText(str(number.value))
        self.player_first.blockSignals(True)
        self.player_last.blockSignals(True)
        self.player_number.blockSignals(True)
        self.player_first.setText(_safe_text(first, self.host.text_value))
        self.player_last.setText(_safe_text(last, self.host.text_value))
        self.player_number.setText(str(_safe_number(
            number.value, number.asset_id, self.host.number_value
        )))
        self.player_first.blockSignals(False)
        self.player_last.blockSignals(False)
        self.player_number.blockSignals(False)
        self.player_first.setEnabled(player.editable)
        self.player_last.setEnabled(player.editable)
        self.player_number.setEnabled(player.editable)
        self.export_historical_number_button.setEnabled(True)
        self._update_player_controls()

    def _clear_historical_player(self) -> None:
        self.selected_historical_row = None
        self.historical_player_title.setText("Select a player")
        for widget in (self.player_first, self.player_last, self.player_number):
            widget.clear()
            widget.setEnabled(False)
        for label in (
            self.player_first_original,
            self.player_last_original,
            self.player_number_original,
        ):
            label.setText("—")
        self.player_first_limit.clear()
        self.player_last_limit.clear()
        self.apply_player_button.setEnabled(False)
        self.revert_player_button.setEnabled(False)
        self.export_historical_number_button.setEnabled(False)

    def _update_player_controls(self) -> None:
        row = self.selected_historical_row
        if row is None or self.catalog is None:
            return
        player = row.player
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        first_usage = text_usage(first, self.player_first.text())
        last_usage = text_usage(last, self.player_last.text())
        self.player_first_limit.setText(first_usage.message)
        self.player_last_limit.setText(last_usage.message)
        self.player_first_limit.setStyleSheet(
            "" if first_usage.valid else "color: #ff7b84;"
        )
        self.player_last_limit.setStyleSheet(
            "" if last_usage.valid else "color: #ff7b84;"
        )
        try:
            jersey = int(self.player_number.text(), 10)
        except ValueError:
            jersey_valid = False
            jersey = -1
        else:
            jersey_valid = number.minimum <= jersey <= number.maximum
        current_first = _safe_text(first, self.host.text_value)
        current_last = _safe_text(last, self.host.text_value)
        current_number = _safe_number(
            number.value, number.asset_id, self.host.number_value
        )
        changed = (
            self.player_first.text() != current_first
            or self.player_last.text() != current_last
            or jersey != current_number
        )
        modified = (
            current_first != first.value
            or current_last != last.value
            or current_number != number.value
        )
        self.apply_player_button.setEnabled(
            player.editable
            and first_usage.valid
            and last_usage.valid
            and jersey_valid
            and changed
        )
        self.revert_player_button.setEnabled(modified)
        self.player_number.setStyleSheet(
            "" if jersey_valid else "border: 1px solid #ff7b84;"
        )

    def _apply_historical_player(self) -> None:
        row = self.selected_historical_row
        if row is None or self.catalog is None:
            return
        player = row.player
        first = self.catalog.get_asset(player.first_name_asset_id)
        last = self.catalog.get_asset(player.last_name_asset_id)
        number = self.catalog.get_number_asset(player.jersey_number_asset_id)
        first_value = self.player_first.text()
        last_value = self.player_last.text()
        first_usage = text_usage(first, first_value)
        last_usage = text_usage(last, last_value)
        try:
            jersey = int(self.player_number.text(), 10)
        except ValueError:
            jersey = -1
        if (
            not player.editable
            or not first_usage.valid
            or not last_usage.valid
            or not number.minimum <= jersey <= number.maximum
        ):
            self._status(
                "Player names must fit their shown allocations and jersey number "
                f"must be {number.minimum} through {number.maximum}."
            )
            return
        try:
            if first_value != _safe_text(first, self.host.text_value):
                self.host.replace_text(first.asset_id, first_value, self._progress)
            if last_value != _safe_text(last, self.host.text_value):
                self.host.replace_text(last.asset_id, last_value, self._progress)
            if jersey != _safe_number(number.value, number.asset_id, self.host.number_value):
                self.host.replace_number(number.asset_id, jersey, self._progress)
        except Exception as exc:
            self._status(
                (str(exc).strip() or "Could not apply the player edit.")
                + " Refresh to review any fields applied before the error."
            )
            self.reload()
            return
        self._changed(
            f"Applied the historical player edit for {player.display_name}.",
            player_id=player.group_id,
        )

    def _revert_historical_player(self) -> None:
        row = self.selected_historical_row
        if row is None:
            return
        player = row.player
        try:
            self.host.revert_text(player.first_name_asset_id, self._progress)
            self.host.revert_text(player.last_name_asset_id, self._progress)
            self.host.revert_text(player.jersey_number_asset_id, self._progress)
        except Exception as exc:
            self._status(str(exc).strip() or "Could not revert that player edit.")
            self.reload()
            return
        self._changed(
            f"Reverted the historical player edit for {player.display_name}.",
            player_id=player.group_id,
        )

    def _export_historical_number(self) -> None:
        row = self.selected_historical_row
        if row is None or self.catalog is None:
            return
        self._export_number_asset(
            self.catalog.get_number_asset(row.player.jersey_number_asset_id),
            "Export historical jersey number",
        )

    def _changed(
        self,
        message: str,
        *,
        asset_id: str | None = None,
        player_id: str | None = None,
        current_player_id: str | None = None,
    ) -> None:
        if self.view != "rosters":
            self._apply_text_filter(select_asset_id=asset_id)
        if self.view != "text":
            self._apply_current_filter(select_player_id=current_player_id)
            self._apply_historical_filter(select_player_id=player_id)
        if self.on_refresh is not None:
            self.on_refresh()
        self._status(message)

    def _status(self, message: str, *, detail: str | None = None) -> None:
        self.status_label.setText(message)
        self.status_label.setToolTip(detail or message)
        if self.on_status is not None:
            self.on_status(message)

    def _progress(self, stage: str, completed: int, total: int) -> None:
        if total > 0:
            percent = min(100, max(0, (completed * 100) // total))
            self._status(f"{stage} · {percent}%")
        else:
            self._status(stage)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#textRosterPanel { background: #0a111d; color: #e4ebf6; }
            QLabel#textPanelHeading { font-size: 22px; font-weight: 800; }
            QLabel#textEditorTitle { font-size: 15px; font-weight: 750; }
            QLabel#textPanelMuted { color: #91a0b5; }
            QLabel#textPanelSummary { color: #5de2d2; font-weight: 750; }
            QLabel#textPanelCallout {
                color: #f0d997; background: #261f17; border: 1px solid #594728;
                border-radius: 7px; padding: 8px 10px;
            }
            QLabel#textPanelStatus {
                color: #b8c7da; background: #111b2c; border: 1px solid #253653;
                border-radius: 7px; padding: 7px 10px;
            }
            QFrame#textEditorCard, QGroupBox {
                background: #111b2c; border: 1px solid #253653;
                border-radius: 9px; margin-top: 7px;
            }
            QGroupBox { font-weight: 700; padding-top: 8px; }
            QLineEdit, QPlainTextEdit, QComboBox, QTableView {
                background: #0e1625; color: #e4ebf6; border: 1px solid #2b3a53;
                border-radius: 5px; selection-background-color: #24425c;
            }
            QLineEdit, QComboBox { min-height: 30px; padding: 2px 7px; }
            QPlainTextEdit { padding: 6px; }
            QHeaderView::section {
                background: #18243a; color: #c9d6e7; border: 0;
                border-right: 1px solid #2b3a53; padding: 7px;
            }
            QPushButton {
                background: #1e6e70; color: white; border: 1px solid #2b9290;
                border-radius: 6px; min-height: 30px; padding: 3px 12px;
                font-weight: 650;
            }
            QPushButton:disabled { background: #202a3a; color: #69778c; border-color: #303d51; }
            QPushButton:hover:!disabled { background: #278285; }
            QTabWidget::pane { border: 1px solid #253653; border-radius: 7px; }
            QTabBar::tab { background: #111b2c; padding: 8px 16px; }
            QTabBar::tab:selected { background: #1b3147; color: #5de2d2; }
            """
        )


__all__ = [
    "ESPN_25TH_COMING_SOON_NOTE",
    "HistoricalPlayerRow",
    "HistoricalResource",
    "STATUS_ALL",
    "STATUS_EDITABLE",
    "STATUS_MODIFIED",
    "STATUS_READ_ONLY",
    "TextAssetTableModel",
    "TextFilter",
    "TextRosterPanel",
    "TextRosterPanelHost",
    "TextUsage",
    "filter_historical_players",
    "filter_text_assets",
    "historical_resources",
    "text_asset_status",
    "text_catalog_summary",
    "text_usage",
]
