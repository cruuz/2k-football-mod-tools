"""b780 CI (macos-latest): the Studio's worker threads get an 8 MiB stack, and numpy loads on the main thread.

On macOS, Qt starts thread-pool threads with a 512 KiB stack. The Studio's prepare task imported
nfl2k5_team_sleeves, hence numpy, on a pool thread, and numpy's import-time macOS self-check (polyfit through
Accelerate) overflowed it: "Fatal Python error: Bus error", rc=138, the whole Studio gone (test_b780_uxfix_qt on
3.11 and 3.12). Every Studio pool now runs its threads with task_delivery.WORKER_STACK_BYTES, and studio_qt imports
numpy on the main thread at start-up.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from PyQt5.QtCore import QThreadPool  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.gui import task_delivery  # noqa: E402

APP = QApplication.instance() or QApplication([])


class WorkerStackTests(unittest.TestCase):
    def test_roomy_pool_gives_8_mib_and_keeps_a_larger_stack(self):
        pool = task_delivery.roomy_pool(QThreadPool())
        self.assertEqual(pool.stackSize(), 8 << 20)
        bigger = QThreadPool()
        bigger.setStackSize(16 << 20)
        self.assertEqual(task_delivery.roomy_pool(bigger).stackSize(), 16 << 20)

    def test_every_studio_pool_is_roomy(self):
        offenders = []
        for path in sorted((ROOT / "mod_editor/gui").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            wrapped = {id(node.args[0]) for node in ast.walk(tree) if isinstance(node, ast.Call)
                       and getattr(node.func, "id", "") == "roomy_pool" and node.args}
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "QThreadPool" and id(node) not in wrapped:
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [], "a Studio QThreadPool without roomy_pool runs 512 KiB threads on macOS")

    def test_the_studio_window_pool_and_numpy_on_the_main_thread(self):
        from mod_editor.gui import studio_qt
        self.assertIn("numpy", sys.modules)                    # loaded by studio_qt's import, on this (main) thread
        window = studio_qt.StudioMainWindow(eager_pages=False, facade=studio_qt.BrowseOnlyFacade(), offer_recovery=False)
        try:
            self.assertIs(window.thread_pool, QThreadPool.globalInstance())
            self.assertGreaterEqual(QThreadPool.globalInstance().stackSize(), 8 << 20)
            # the task that crashed: prepare -> mod_build.availability -> nfl2k5_team_sleeves -> numpy, on a pool thread
            from mod_editor.core import mod_build
            done = []
            from PyQt5.QtCore import QRunnable

            class Prepare(QRunnable):
                def run(self):
                    done.append(sorted(mod_build.availability())[:1])

            window.thread_pool.start(Prepare())
            self.assertTrue(window.thread_pool.waitForDone(120_000))
            self.assertEqual(len(done), 1)
        finally:
            window.close()
            window.deleteLater()
            APP.processEvents()


if __name__ == "__main__":
    unittest.main()
