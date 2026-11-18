"""Optional graphical front ends."""


def locate_qt_plugins() -> None:
    """Let Qt load its wheel’s platform plugin when its built-in path loses Unicode."""
    from pathlib import Path
    from PyQt5 import QtCore
    from PyQt5.QtCore import QCoreApplication, QLibraryInfo

    if (Path(QLibraryInfo.location(QLibraryInfo.PluginsPath)) / "platforms").is_dir():
        return
    for directory in ("Qt5", "Qt"):
        plugins = Path(QtCore.__file__).parent / directory / "plugins"
        if (plugins / "platforms").is_dir():
            QCoreApplication.addLibraryPath(str(plugins))
            return


def pointer_screen_area(window=None):
    """The work area of the monitor under the pointer.

    Before show(), QWidget.screen() can still name the monitor containing (0, 0), which on a two-monitor desktop is
    often not the one the window manager opens a new window on."""
    from PyQt5.QtGui import QCursor, QGuiApplication
    from PyQt5.QtWidgets import QApplication

    screen = QApplication.screenAt(QCursor.pos())
    if screen is None:
        screen = window.screen() if window is not None else QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def first_window_usable(available):
    """The largest first-run window for a work area, leaving room for the frame and title bar."""
    from PyQt5.QtCore import QSize

    return QSize(max(1, available.width() - 24), max(1, available.height() - 48))


def fit_first_window(window, available=None) -> None:
    """Fit a window that has no remembered geometry to the work area under the pointer, centred on it.

    Both Studios use this for their first window; a returning user's saved geometry is restored separately."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QStyle

    if available is None:
        available = pointer_screen_area(window)
    usable = first_window_usable(available)
    window.setMinimumSize(window.minimumSize().boundedTo(usable))
    window.resize(window.size().boundedTo(usable))
    window.move(QStyle.alignedRect(Qt.LeftToRight, Qt.AlignCenter, window.size(), available).topLeft())
