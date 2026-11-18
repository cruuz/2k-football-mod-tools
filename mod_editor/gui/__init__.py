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
