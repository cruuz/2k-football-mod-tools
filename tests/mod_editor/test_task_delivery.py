"""Background-task results reach a widget only while that widget exists.

The macOS CI runner segfaulted when a studio window was deleted while its
commentary panel was still listing a disc's speech banks: the read failed
after teardown and its closure ran against the dead panel. ``bound()`` is the
fix; this file pins both the helper's contract and the original race.
"""
from __future__ import annotations

import gc
import os
from pathlib import Path
import sys
import unittest
import weakref
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

from mod_editor.gui import commentary_panel_qt as panel_module  # noqa: E402
from mod_editor.gui.commentary_panel_qt import CommentaryPanel  # noqa: E402
from mod_editor.gui.task_delivery import bound  # noqa: E402


class _Signals(QObject):
    fired = pyqtSignal(str, int)


class _Emit(QRunnable):
    """Emit from a worker thread so the delivery is queued to the GUI thread."""

    def __init__(self, signals: _Signals, *args: object) -> None:
        super().__init__()
        self._signals, self._args = signals, args

    def run(self) -> None:
        self._signals.fired.emit(*self._args)


class _RecordingHook:
    """PyQt aborts the process on an unhandled slot exception unless a hook is installed."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__(self, kind, value, _traceback) -> None:
        self.seen.append(f"{kind.__name__}: {value}")


class BoundReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.pool = QThreadPool()

    def _drain(self) -> None:
        for _ in range(3):
            self.app.processEvents()

    def test_callback_receives_the_signal_arguments_while_the_owner_lives(self) -> None:
        owner, signals, calls = QWidget(), _Signals(), []
        signals.fired.connect(bound(owner, lambda text, count: calls.append((text, count))))
        gc.collect()                       # PyQt keeps the connected closure alive through the signal's object
        signals.fired.emit("direct", 1)
        self.pool.start(_Emit(signals, "queued", 2))
        self.pool.waitForDone(5000)
        self._drain()
        self.assertEqual(calls, [("direct", 1), ("queued", 2)])
        sip.delete(owner)

    def test_queued_delivery_is_dropped_once_the_owner_is_destroyed(self) -> None:
        hook = _RecordingHook()
        for destroy in ("sip.delete", "C++ parent"):
            with self.subTest(destroy=destroy), patch.object(sys, "excepthook", hook):
                parent = QWidget()
                owner = QWidget(parent) if destroy == "C++ parent" else QWidget()
                signals, calls = _Signals(), []
                signals.fired.connect(bound(owner, lambda text, count: calls.append((text, count))))
                self.pool.start(_Emit(signals, "late", 3))
                self.pool.waitForDone(5000)        # the delivery is now queued, not yet run
                sip.delete(parent if destroy == "C++ parent" else owner)
                self._drain()
                self.assertEqual(calls, [])
                self.assertEqual(hook.seen, [])
                if destroy != "C++ parent":
                    sip.delete(parent)

    def test_a_finished_task_and_everything_its_callbacks_captured_are_collected(self) -> None:
        """No per-task retention: a callback that captures its own task is freed with the task."""

        class _Task:
            def __init__(self) -> None:
                self.signals = _Signals()

        owner, tasks = QWidget(), set()
        task = _Task()
        tasks.add(task)
        task.signals.fired.connect(bound(owner, lambda _text, _count: tasks.discard(task)))
        task.signals.fired.emit("done", 1)
        self.assertEqual(tasks, set())
        gone = weakref.ref(task)
        del task
        gc.collect()
        self.assertIsNone(gone())
        self.assertEqual([c for c in owner.children() if isinstance(c, QObject)], [])
        sip.delete(owner)

    def test_commentary_panel_survives_teardown_during_a_disc_read(self) -> None:
        """The witnessed race: the read's failure is queued when the window dies, delivered after."""

        def failing_read(_path: Path) -> list[str]:
            raise OSError("no such disc")

        hook = _RecordingHook()
        with patch.object(panel_module, "bank_names", failing_read), patch.object(sys, "excepthook", hook):
            # Positive control: while the panel lives, the very same failure reaches the status line.
            alive = CommentaryPanel()
            alive.load_source(Path("/nowhere/disc.xiso.iso"))
            alive._pool.waitForDone(5000)
            self._drain()
            self.assertIn("Could not read the disc: OSError: no such disc", alive.status_label.text())
            sip.delete(alive)

            window = QWidget()
            panel = CommentaryPanel(parent=window)
            panel.load_source(Path("/nowhere/disc.xiso.iso"))
            panel._pool.waitForDone(5000)       # the failure is queued to the GUI thread, not yet run
            sip.delete(window)                  # the window goes first and takes the panel with it
            self.assertTrue(sip.isdeleted(panel))
            self._drain()                       # ...and only now does the queued failure come up
        self.assertEqual(hook.seen, [])


if __name__ == "__main__":
    unittest.main()
