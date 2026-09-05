"""Qt-free model for the studio's one game-module seam: "Select other games…".

The Xbox studio hosts N games through a single File-menu action.  Its handler
opens a small core-owned chooser that lists every discovered game module as
one row: **the studio it opens**.  One row per module, labelled the way the
core composes every studio label -- ``<Console> <Game> <Year> Studio`` -- with
its status and a detail line, sorted by console, game and year.  Choosing one
opens that module's ``studio_window``; the core never imports a module's
internals beyond the contract.

The other windows a module offers are still reachable -- by id through
:func:`open_window`, from the command line, and from the studio's own Windows
menu -- but they are no longer a list the chooser draws: a user picks a game,
not a window.

This module is the chooser's whole behaviour.  The dialog in
:mod:`mod_editor.games.chooser_qt` only draws it, so everything a test needs
to prove -- a refused module degrades to an explanatory row, a window that
needs the Xbox session is withheld when there is none, a factory that raises
becomes a sentence and not a crash -- is provable here without a display.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Optional

from . import DiscoveryReport, RefusedGame
from .contract import GameModule, Refusal, WindowSpec

STATUS_LOADABLE = "loadable"
STATUS_REFUSED = "refused"

#: How a menu spells a studio.  Every menu that offers one -- the Xbox
#: studio's File menu, the chooser's Open, ``show``'s window list -- reads the
#: label from here, so the label rule ("<Console> <Game> <Year> Studio") is
#: applied in exactly one place and a module that spelled its own would still
#: be displayed by the composed one.
STUDIO_MENU_SUFFIX = "\u2026"

BOUNDARY_NOTE = (
    "Each game has one studio and works on your own files. Choosing one here "
    "changes nothing until you act inside it; a module that cannot be loaded is "
    "listed with the reason and cannot be opened."
)


def studio_menu_label(studio_label: str) -> str:
    """The menu caption for a studio: the composed label plus the menu ellipsis."""

    return f"{studio_label}{STUDIO_MENU_SUFFIX}"


def studio_window_spec(game: GameModule) -> WindowSpec:
    """The module's studio window, relabelled with the label the core composes.

    A module may not type its own studio label -- conformance refuses it -- so
    the ``menu_label`` a module gives its studio window is whatever that window
    is called *inside* the studio ("Disc Studio\u2026").  Everywhere the studio is
    offered from outside, the core substitutes the composed label, so the user
    reads one name for one game in every menu.
    """

    return replace(game.studio, menu_label=studio_menu_label(game.manifest.studio_label))


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
    """One line of the chooser: one game's studio, hosted or refused.

    ``studio_label`` is what the user reads -- composed by the core from the
    manifest for a hosted module, and read leniently from ``game.json`` for a
    refused one so a broken module is still recognisable.  ``studio_window``
    is the window :func:`open_studio` opens, empty for a refused module.
    """

    game_id: str
    studio_label: str
    console: str
    game: str
    year: str
    title: str
    platform: str
    version: str
    contract: str
    status: str
    reason: str
    windows: tuple[WindowRow, ...]
    lanes: int
    studio_window: str = ""

    @property
    def loadable(self) -> bool:
        return self.status == STATUS_LOADABLE

    @property
    def status_text(self) -> str:
        return "Ready" if self.loadable else "Cannot load"

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        """Console, game, year, then the id: the order studios are listed in."""

        return (self.console.casefold(), self.game.casefold(), self.year.casefold(), self.game_id)

    @property
    def detail(self) -> str:
        if not self.loadable:
            return f"{self.title} cannot be loaded: {self.reason}"
        return (
            f"{self.title} — {self.platform} · module {self.version} · "
            f"{self.contract} · {self.lanes} lane(s)"
        )


def _row_for_game(game: GameModule) -> ChooserRow:
    manifest = game.manifest
    return ChooserRow(
        game_id=game.game_id,
        studio_label=manifest.studio_label,
        console=manifest.console,
        game=manifest.game,
        year=manifest.year,
        title=game.identity.title,
        platform=game.identity.platform,
        version=game.version,
        contract=game.contract,
        status=STATUS_LOADABLE,
        reason="",
        windows=tuple(
            WindowRow.from_spec(
                studio_window_spec(game) if spec.window_id == game.studio_window else spec
            )
            for spec in game.windows
        ),
        lanes=len(game.lanes),
        studio_window=game.studio_window,
    )


def _row_for_refused(item: RefusedGame) -> ChooserRow:
    return ChooserRow(
        game_id=item.game_id,
        studio_label=item.studio_label,
        console=item.console,
        game=item.game,
        year=item.year,
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
    """One row per module -- its studio -- sorted by console, game, year."""

    rows = [_row_for_game(game) for game in report.games]
    rows += [_row_for_refused(item) for item in report.refused]
    return tuple(sorted(rows, key=lambda row: row.sort_key))


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


def open_studio(
    report: DiscoveryReport,
    game_id: str,
    *,
    parent: Any = None,
    context: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Open one module's studio -- the window its ``studio_window`` names.

    This is what the chooser's Open does and what ``python -m mod_editor.games
    open <game>`` does without ``--window``.  Every failure is a
    :class:`~mod_editor.games.contract.Refusal`, as with any other window.
    """

    game = report.game(game_id)
    return open_window(report, game_id, game.studio_window, parent=parent, context=context)


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
    "STUDIO_MENU_SUFFIX",
    "WindowRow",
    "chooser_headline",
    "chooser_rows",
    "open_studio",
    "open_window",
    "openable_windows",
    "studio_menu_label",
    "studio_window_spec",
]
