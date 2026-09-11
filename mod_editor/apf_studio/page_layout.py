"""Shared APF workspace spacing, responsive controls and persistent actions."""
from __future__ import annotations

from PyQt5.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFrame, QHBoxLayout, QLabel,
    QHeaderView, QLayout, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTabWidget, QToolButton, QVBoxLayout, QWidget,
)


class FlowLayout(QLayout):
    """Wrap a toolbar without shrinking button labels or hiding controls."""
    def __init__(self):
        super().__init__()
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Horizontal)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, True)

    def sizeHint(self):
        return QSize(320, self.heightForWidth(640))

    def minimumSize(self):
        return QSize(0, 0)

    def _arrange(self, rect, apply):
        x, y, height = rect.x(), rect.y(), 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            width = min(size.width(), rect.width())
            if x > rect.x() and x + width > rect.right() + 1:
                x, y, height = rect.x(), y + height + self.spacing(), 0
            h = item.heightForWidth(width) if item.hasHeightForWidth() else size.height()
            if apply:
                item.setGeometry(QRect(x, y, width, h))
            x += width + self.spacing()
            height = max(height, h)
        return y - rect.y() + height


class WorkspaceTabs(QTabWidget):
    """An inactive workspace must not set the active workspace's minimum size."""
    def minimumSizeHint(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(760, 420)


def _responsive_layout(layout):
    """Only flat control toolbars wrap; content splitters keep their identities."""
    for index in range(layout.count()):
        item = layout.itemAt(index)
        child = item.layout()
        if child is None:
            continue
        widgets = [child.itemAt(i).widget() for i in range(child.count())
                   if child.itemAt(i).widget() is not None]
        controls = (QPushButton, QToolButton, QComboBox, QLineEdit, QLabel)
        if (isinstance(child, QHBoxLayout) and len(widgets) >= 3
                and all(isinstance(w, controls) for w in widgets)
                and sum(w.sizeHint().width() for w in widgets) > 540
                and all(child.itemAt(i).layout() is None for i in range(child.count()))):
            replacement = FlowLayout()
            while child.count():
                replacement.addItem(child.takeAt(0))
            layout.removeItem(child)
            child.setParent(None)
            if isinstance(layout, QVBoxLayout):
                layout.insertLayout(index, replacement)
            else:
                layout.addItem(replacement)
        else:
            _responsive_layout(child)


def prepare_page(page):
    layout = QWidget.layout(page)
    if layout:
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(8)
    for widget in (page, *page.findChildren(QWidget)):
        if isinstance(widget, QHeaderView):
            continue
        child_layout = QWidget.layout(widget)
        if child_layout:
            child_layout.setSizeConstraint(QLayout.SetNoConstraint)
            _responsive_layout(child_layout)
        if isinstance(widget, QTabWidget):
            widget.setUsesScrollButtons(True)
            widget.setElideMode(Qt.ElideRight)
            widget.tabBar().setExpanding(False)
            widget.setMinimumWidth(0)
        elif isinstance(widget, QComboBox):
            widget.setMinimumWidth(min(widget.minimumWidth(), 100))
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        elif isinstance(widget, QAbstractItemView):
            widget.setMinimumSize(0, 80)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        elif isinstance(widget, QLabel):
            if widget.minimumWidth() > 0 and widget.minimumWidth() == widget.maximumWidth():
                continue  # Fixed artwork previews and data swatches keep their canvas.
            if len(widget.text()) > 65 or widget.wordWrap():
                widget.setMinimumWidth(0)
                widget.setWordWrap(True)
                widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
                if widget.objectName() in ("findingText", "contractText", "metadataText", "mutedLabel", "pageSummary"):
                    widget.setMaximumHeight(42)
                    widget.setProperty("apfCompact", len(widget.text()) > 160)
                    if widget.text() and not widget.toolTip():
                        widget.setToolTip(widget.text())
        elif isinstance(widget, QSplitter):
            widget.setChildrenCollapsible(False)
            for i in range(widget.count()):
                child = widget.widget(i)
                child.setMinimumWidth(0)
                child.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
    page.setMinimumWidth(0)


class EmptyState(QFrame):
    """A list viewport owns its empty guidance; model rows remain untouched."""
    def __init__(self, view, window):
        super().__init__(view.viewport())
        self.view, self.window = view, window
        self.setObjectName("emptyState")
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 12)
        self.text = QLabel("Load your APF game to browse this list.")
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setWordWrap(True)
        self.load = QToolButton()
        self.load.setText("Load APF Game")
        self.load.setObjectName("primaryButton")
        self.load.setPopupMode(QToolButton.InstantPopup)
        self.load.setMenu(window.open_source_button.menu())
        box.addWidget(self.text)
        box.addWidget(self.load, 0, Qt.AlignHCenter)
        view.viewport().installEventFilter(self)
        model = view.model()
        if model:
            model.rowsInserted.connect(self.update_state)
            model.rowsRemoved.connect(self.update_state)
            model.modelReset.connect(self.update_state)
        self.update_state()

    def update_state(self, *_args):
        ready = self.window.facade.source_ready
        self.text.setText("No matching items. Clear the search or change the filters." if ready
                          else "Load your APF game to browse this list.")
        self.load.setVisible(not ready)
        model = self.view.model()
        self.setVisible(not ready or model is not None and model.rowCount() == 0)
        width = min(360, max(0, self.parentWidget().width() - 16))
        self.resize(width, min(self.sizeHint().height(), self.parentWidget().height()))
        self.move(max(0, (self.parentWidget().width() - width) // 2),
                  max(0, (self.parentWidget().height() - self.height()) // 2))

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self.update_state()
        return False


class PageViewport(QScrollArea):
    """Bounded workspace with a fixed action footer and an adaptive page width.

    Scroll only when the selected editor needs more vertical room. Every page
    shares the same footer; its buttons delegate to the existing writer actions,
    retaining the source gates, progress runner and error handling.
    """
    def __init__(self, page, window):
        super().__init__()
        self.page, self.window = page, window
        self.setObjectName("pageScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        prepare_page(page)
        self.setWidget(page)
        page.setAutoFillBackground(False)
        self.footer = QFrame(self)
        self.footer.setObjectName("footer")
        row = QHBoxLayout(self.footer)
        row.setContentsMargins(16, 6, 16, 6)
        self.status = QLabel("Select an item to inspect it.")
        self.status.setObjectName("mutedLabel")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.status, 1)
        self.actions = []
        for _ in range(3):
            button = QPushButton()
            button.setProperty("apfActionProxy", True)
            row.addWidget(button)
            self.actions.append(button)
        self._targets = []
        self.header_action = next((button for button in page.findChildren(QPushButton)
                                   if button.property("apfActionProxy")), None)
        if self.header_action:
            self.header_action.clicked.connect(lambda: self._trigger(0))
        for i, button in enumerate(self.actions):
            button.clicked.connect(lambda _checked=False, index=i: self._trigger(index))
        views = []
        for view in page.findChildren(QAbstractItemView):
            ancestor = view.parentWidget()
            while ancestor is not None and not isinstance(ancestor, QComboBox):
                ancestor = ancestor.parentWidget()
            if ancestor is None and not isinstance(view, QHeaderView) and view.objectName() != "workspaceLauncher":
                views.append(view)
                view.activated.connect(lambda _index, selected=view: self.focus_inspector(selected))
        self.empty_states = [EmptyState(view, window) for view in views if view.model() is not None]
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh_actions)
        self.refresh_actions()

    def _trigger(self, index):
        if index < len(self._targets):
            self._targets[index].click()

    def focus_inspector(self, view):
        """Selection already opens the record; Enter transfers keyboard focus."""
        child = view
        while child is not self.page and child.parentWidget() is not None:
            parent = child.parentWidget()
            if isinstance(parent, QSplitter):
                position = parent.indexOf(child)
                if 0 <= position < parent.count() - 1:
                    inspector = parent.widget(position + 1)
                    fields = [widget for widget in inspector.findChildren(QWidget)
                              if widget.isVisibleTo(self.page) and widget.isEnabled()
                              and widget.focusPolicy() & Qt.TabFocus]
                    target = fields[0] if fields else inspector
                    if not fields:
                        target.setFocusPolicy(Qt.StrongFocus)
                    target.setFocus(Qt.ShortcutFocusReason)
                    self.ensureWidgetVisible(target)
                    return
            child = parent

    def refresh_actions(self):
        buttons = [b for b in self.page.findChildren(QPushButton)
                   if b.isVisibleTo(self.page) and not b.property("apfActionProxy")
                   and b.objectName() in ("primaryButton", "secondaryButton", "dangerQuietButton")]
        primary = [b for b in buttons if b.objectName() == "primaryButton"]
        primary.sort(key=lambda b: (not b.text().casefold().startswith(("replace", "apply", "stage", "design")),
                                    not b.isEnabled()))
        chosen = primary[:1]
        chosen += [b for b in buttons if b.objectName() != "primaryButton"
                   and b.text().casefold().startswith(("export", "revert", "preview"))][:2]
        self._targets = chosen
        if self.header_action is not None:
            self.header_action.setVisible(bool(chosen))
            if chosen:
                self.header_action.setText(chosen[0].text())
                self.header_action.setToolTip(chosen[0].toolTip())
                self.header_action.setEnabled(chosen[0].isEnabled())
        for index, button in enumerate(self.actions):
            button.setVisible(index < len(chosen))
            if index < len(chosen):
                target = chosen[index]
                button.setText(target.text())
                button.setEnabled(target.isEnabled())
                button.setToolTip(target.toolTip())
                if button.objectName() != target.objectName():
                    button.setObjectName(target.objectName())
                    button.style().unpolish(button)
                    button.style().polish(button)
        self.status.setText("Select an item to inspect it.  Ctrl+F Search · Enter Inspect" if self.window.facade.source_ready
                            else "Load your APF game to begin.")
        for state in self.empty_states:
            state.update_state()

    def resizeEvent(self, event):
        self.setViewportMargins(0, 0, 0, 48)
        super().resizeEvent(event)
        self.footer.setGeometry(0, max(0, self.height() - 48), self.width(), 48)
        self.page.setMaximumWidth(self.viewport().width())
        # Top-level tab stacks get the available height. Long individual
        # inspectors retain their own vertical scroll areas.
        if self.page.findChildren(WorkspaceTabs):
            self.page.setMaximumHeight(self.viewport().height())
        self.page.resize(self.viewport().width(), self.page.height())

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_actions()
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)
