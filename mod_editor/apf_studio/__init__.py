"""APF 2K8 Mod Studio product package.

The package contains no game assets.  Every catalog and preview is generated
from a user-owned All-Pro Football 2K8 game image or extracted game directory.
"""

from .models import (
    ApfAsset,
    ApfCategory,
    ApfSource,
    ApfStatus,
    UniformAsset,
)

__version__ = "0.1.0-alpha.87"


def _delete_qt_widgets_before_exit():
    """Delete top-level Qt widgets while the QApplication still exists.

    Interpreter finalization destroys module globals in an unspecified order; a
    widget that outlives the QApplication crashes Qt at shutdown (a segmentation
    fault after every test has passed). Deleting the widgets first is harmless
    for the studio, whose windows are already closed by then.
    """
    import sys
    if "PyQt5.QtWidgets" not in sys.modules:
        return
    try:
        from PyQt5.QtCore import QCoreApplication, QEvent
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return
        for widget in app.topLevelWidgets():
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    except Exception:
        return


import atexit as _atexit  # noqa: E402

_atexit.register(_delete_qt_widgets_before_exit)

__all__ = [
    "ApfAsset",
    "ApfCategory",
    "ApfSource",
    "ApfStatus",
    "UniformAsset",
    "__version__",
]
