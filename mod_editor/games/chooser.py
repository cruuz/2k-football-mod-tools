"""Qt-free model for the studio's one game-module seam: "Select other games…".

The Xbox studio hosts N games through a single File-menu action.  Its handler
opens a small core-owned chooser that lists every discovered game module --
name, platform, module version, contract version and load status -- and, for
a loadable one, the windows it offers.  Choosing a window asks the module to
open it; the core never imports a module's internals beyond the contract.

This module is the chooser's whole behaviour.  The dialog in
:mod:`mod_editor.games.chooser_qt` only draws it, so everything a test needs
to prove -- a refused module degrades to an explanatory row, a window that
needs the Xbox session is withheld when there is none, a factory that raises
becomes a sentence and not a crash -- is provable here without a display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from . import DiscoveryReport, RefusedGame
from .contract import GameModule, Refusal, WindowSpec

STATUS_LOADABLE = "loadable"
STATUS_REFUSED = "refused"

BOUNDARY_NOTE = (
    "Each game module hosts its own windows and works on your own files. "
    "Choosing one here changes nothing until you act inside its window; a "
    "module that cannot be loaded is listed with the reason and cannot be opened."
)


@dataclass(frozen=True)
class WindowRow:
    window_id: str
    menu_label: str
    tooltip: str
    flag: str
    needs_studio_session: bool

    @classmethod
    def from_spec(cls, spec: WindowSpec) -> "WindowRow":
        return cls(spec.window_id, spec.menu_label, spec.tooltip, spec.flag,
                   spec.needs_studio_session)


@dataclass(frozen=True)
class ChooserRow:
    """One line of the chooser: a hosted game or a refused package."""

    game_id: str
    title: str
    platform: str
    version: str
    contract: str
    status: str
    reason: str
    windows: tuple[WindowRow, ...]
    lanes: int

    @property
    def loadable(self) -> bool:
        return self.status == STATUS_LOADABLE

    @property
    def status_text(self) -> str:
        return "Ready" if self.loadable else "Cannot load"

    @property
    def detail(self) -> str:
        if not self.loadable:
            return f"{self.title} cannot be loaded: {self.reason}"
        windows = ", ".join(row.menu_label for row in self.windows) or "no windows"
        return (
            f"{self.title} — {self.platform} · module {self.version} · "
            f"{self.contract} · {self.lanes} lane(s) · windows: {windows}"
        )


def _row_for_game(game: GameModule) -> ChooserRow:
    return ChooserRow(
        game_id=game.game_id,
        title=game.identity.title,
        platform=game.identity.platform,
        version=game.version,
        contract=game.contract,
        status=STATUS_LOADABLE,
        reason="",
        windows=tuple(WindowRow.from_spec(spec) for spec in game.windows),
        lanes=len(game.lanes),
    )


def _row_for_refused(item: RefusedGame) -> ChooserRow:
    return ChooserRow(
        game_id=item.game_id,
        title=item.title if item.title != "?" else item.directory,
        platform=item.platform,
        version=item.version,
        contract=item.contract,
        status=STATUS_REFUSED,
        reason=item.reason,
        windows=(),
        lanes=0,
    )


def chooser_rows(report: DiscoveryReport) -> tuple[ChooserRow, ...]:
    """Loadable games first, then refused packages; each group by title."""

    loadable = sorted((_row_for_game(game) for game in report.games),
                      key=lambda row: (row.title.casefold(), row.game_id))
    refused = sorted((_row_for_refused(item) for item in report.refused),
                     key=lambda row: (row.title.casefold(), row.game_id))
    return tuple(loadable) + tuple(refused)


def chooser_headline(rows: tuple[ChooserRow, ...]) -> str:
    hosted = sum(1 for row in rows if row.loadable)
    refused = len(rows) - hosted
    if not rows:
        return "No game modules are installed."
    text = f"{hosted} game module{'s' if hosted != 1 else ''} ready"
    if refused:
        text += f" · {refused} cannot be loaded (select one to see why)"
    return text


def openable_windows(row: ChooserRow, *, has_studio_session: bool) -> tuple[WindowRow, ...]:
    """The windows a row can open right now."""

    if not row.loadable:
        return ()
    return tuple(
        window for window in row.windows
        if has_studio_session or not window.needs_studio_session
    )


def open_window(
    report: DiscoveryReport,
    game_id: str,
    window_id: str,
    *,
    parent: Any = None,
    context: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Ask a hosted module to open one of its windows; every failure is a Refusal."""

    game = report.game(game_id)
    spec = game.window(window_id)
    extra = dict(context or {})
    if spec.needs_studio_session and extra.get("facade") is None:
        raise Refusal(
            f"{spec.menu_label} works on the open Xbox project, so it needs the "
            "studio's session; open it from the studio, not on its own."
        )
    try:
        return spec.factory(parent=parent, **extra)
    except Refusal:
        raise
    except Exception as exc:
        raise Refusal(
            f"{game.identity.title}: its {spec.menu_label} window could not open "
            f"({exc.__class__.__name__}: {exc}). Nothing was changed."
        ) from exc


__all__ = [
    "BOUNDARY_NOTE",
    "ChooserRow",
    "STATUS_LOADABLE",
    "STATUS_REFUSED",
    "WindowRow",
    "chooser_headline",
    "chooser_rows",
    "open_window",
    "openable_windows",
]
