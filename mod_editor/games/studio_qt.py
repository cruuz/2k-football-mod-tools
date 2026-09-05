"""The game studio shell: one window per game, every page present and honest.

Core-owned and game-blind.  ``GameStudioDialog(module)`` opens *the* studio of
one game module: the label the core composes from the manifest, the module's
title and platform, and the fourteen pages of :data:`~mod_editor.games.contract.PAGE_ORDER`
in the Xbox studio's order.  A game writes lanes; it never writes this window.

**This file is the A1 skeleton.**  Every page is a placeholder panel today: a
page with no lane says exactly that, and a page whose lanes exist lists them
with their registry classification and no controls.  Work package A2 replaces
the placeholders with the real lane pages (catalogue, target table, the editor
built from ``Target.fields``, Check, Add to build) and the Build & Share page
over the ``lane`` command-line verb.  The structure it will fill in is:

* :meth:`GameStudioDialog.page_widget` -- the widget of one page id, the thing
  A2 swaps for a live lane page;
* :meth:`GameStudioDialog.lanes_for_page` -- which lanes belong to a page,
  through :func:`~mod_editor.games.contract.lane_page`;
* :meth:`GameStudioDialog.unavailable_sentence` -- the core's honest sentence
  for a page with no lane, plus the module's own ``page_notes`` sentence.

Qt is imported at module level here, as in ``chooser_qt``: this module *is*
the window, so a caller that imports it has already decided to draw one.  A
game package must still import it lazily (the boundary check enforces that).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .contract import PAGE_ORDER, GameModule, lane_page

BOUNDARY_NOTE = (
    "Your image is opened read-only; every edit lands in a new file. Nothing on "
    "a page changes anything until you build, and a build never writes over "
    "what you opened."
)

#: What a page says when the module has no lane for it yet.  The game's own
#: reason, if it has one, is added underneath from the manifest's ``page_notes``.
UNAVAILABLE_TEMPLATE = "No {title} lane in {studio} yet."


class GameStudioDialog(QDialog):
    """One game's studio: the composed label, the module's identity, 14 pages."""

    def __init__(
        self,
        module: GameModule,
        *,
        parent: Optional[QWidget] = None,
        initial_source: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self.module = module
        self.studio_label = module.manifest.studio_label
        self.initial_source = Path(initial_source) if initial_source else None
        self._pages: dict[str, QWidget] = {}
        self.setObjectName("gameStudioDialog")
        self.setWindowTitle(self.studio_label)
        self.setMinimumSize(880, 560)
        self._build_ui()

    # -- construction --------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.header = QLabel(self.studio_label)
        self.header.setObjectName("gameStudioHeader")
        self.header.setAccessibleName("Studio")
        layout.addWidget(self.header)

        self.identity = QLabel(
            f"{self.module.identity.title} — {self.module.identity.platform} · "
            f"module {self.module.version} · {len(self.module.lanes)} lane(s)"
        )
        self.identity.setObjectName("gameStudioIdentity")
        self.identity.setAccessibleName("Game module identity")
        self.identity.setWordWrap(True)
        layout.addWidget(self.identity)

        self.source = QLabel(
            f"Source: {self.initial_source.name}" if self.initial_source else "No source opened yet."
        )
        self.source.setObjectName("gameStudioSource")
        self.source.setAccessibleName("Open source")
        self.source.setWordWrap(True)
        layout.addWidget(self.source)

        body = QHBoxLayout()
        self.navigation = QListWidget()
        self.navigation.setObjectName("gameStudioPages")
        self.navigation.setAccessibleName("Studio pages")
        self.navigation.setAccessibleDescription(
            "Every page this studio has. A page whose lane does not exist yet is still here and says why."
        )
        self.navigation.setSelectionMode(QAbstractItemView.SingleSelection)
        self.navigation.setMaximumWidth(240)
        body.addWidget(self.navigation)

        self.stack = QStackedWidget()
        self.stack.setObjectName("gameStudioStack")
        body.addWidget(self.stack, 1)
        layout.addLayout(body, 1)

        for page_id, title in PAGE_ORDER:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, page_id)
            self.navigation.addItem(item)
            widget = self._build_page(page_id, title)
            self._pages[page_id] = widget
            self.stack.addWidget(widget)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        note = QLabel(BOUNDARY_NOTE)
        note.setObjectName("gameStudioBoundaryNote")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_page(self, page_id: str, title: str) -> QWidget:
        """One placeholder page.  A2 replaces this with the real lane page."""

        widget = QWidget()
        widget.setObjectName(f"gameStudioPage_{page_id}")
        widget.setAccessibleName(title)
        page_layout = QVBoxLayout(widget)

        heading = QLabel(title)
        heading.setObjectName(f"gameStudioPageTitle_{page_id}")
        page_layout.addWidget(heading)

        lanes = self.lanes_for_page(page_id)
        if lanes:
            for lane in lanes:
                row = QLabel(f"{lane.title} — {lane.classification}")
                row.setObjectName(f"gameStudioLane_{lane.lane_id}")
                row.setWordWrap(True)
                page_layout.addWidget(row)
            pending = QLabel(
                "This page's controls arrive with the shell's lane pages; the lane itself "
                "is already on the contract and usable from the command line."
            )
            pending.setObjectName(f"gameStudioPagePending_{page_id}")
            pending.setWordWrap(True)
            page_layout.addWidget(pending)
        else:
            sentence = QLabel(self.unavailable_sentence(page_id))
            sentence.setObjectName(f"gameStudioPageUnavailable_{page_id}")
            sentence.setWordWrap(True)
            sentence.setTextInteractionFlags(Qt.TextSelectableByMouse)
            page_layout.addWidget(sentence)
        page_layout.addStretch(1)
        return widget

    # -- state ---------------------------------------------------------

    def page_ids(self) -> tuple[str, ...]:
        """Every page this studio has, in the studio's order."""

        return tuple(page_id for page_id, _title in PAGE_ORDER)

    def page_widget(self, page_id: str) -> Optional[QWidget]:
        """The widget of one page, or None when the id is not a page."""

        return self._pages.get(page_id)

    def lanes_for_page(self, page_id: str) -> tuple[object, ...]:
        """The module's lanes that this page hosts, in the module's own order."""

        return tuple(lane for lane in self.module.lanes if lane_page(lane) == page_id)

    def unavailable_sentence(self, page_id: str) -> str:
        """The core's honest sentence for a page with no lane, plus the game's own."""

        title = dict(PAGE_ORDER).get(page_id, page_id)
        sentence = UNAVAILABLE_TEMPLATE.format(title=title, studio=self.studio_label)
        note = self.module.manifest.page_note(page_id)
        return f"{sentence} {note}".strip() if note else sentence

    def select_page(self, page_id: str) -> bool:
        """Show one page by id; False when the id is not a page."""

        for index, (candidate, _title) in enumerate(PAGE_ORDER):
            if candidate == page_id:
                self.navigation.setCurrentRow(index)
                return True
        return False

    def current_page_id(self) -> Optional[str]:
        item = self.navigation.currentItem()
        return item.data(Qt.UserRole) if item is not None else None


__all__ = ["BOUNDARY_NOTE", "UNAVAILABLE_TEMPLATE", "GameStudioDialog"]
