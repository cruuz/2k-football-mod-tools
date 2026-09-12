"""Opt-in Qt heartbeat and Python stacks, without doing file I/O on the UI thread."""
from __future__ import annotations

from collections import deque
import json
import gc
import os
from pathlib import Path
import sys
import threading
import time
import traceback
import weakref

from PyQt5.QtCore import QEvent, QObject, QThreadPool, QTimer, Qt

from mod_editor.gui.crash_report import log_directory


class StallWatchdog(QObject):
    """Sample stalled event delivery from another thread; retain bounded evidence."""

    def __init__(self, owner, *, path: Path | None = None, threshold=.2):
        super().__init__(owner)
        self.path = path
        self.threshold = threshold
        self.ui_thread = threading.get_ident()
        self.last_beat = time.monotonic()
        self.max_gap = 0.0
        self.stalls = deque(maxlen=256)
        self.records = deque(maxlen=1024)
        self._stop = threading.Event()
        self._inventory_nodes = []
        self._inventory_rows = []
        self._timer_names = weakref.WeakKeyDictionary()
        self._gc_start = 0.0
        gc.callbacks.append(self._gc_event)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self.beat)
        self._timer.start()
        self._inventory_timer = QTimer(self)
        self._inventory_timer.setInterval(5000)
        self._inventory_timer.timeout.connect(lambda: self.inventory(owner))
        self._inventory_timer.start()
        # Capture no QObject in the destroyed callback. The sampler never calls Qt.
        stop, callback = self._stop, self._gc_event
        def destroyed():
            stop.set()
            if callback in gc.callbacks:
                gc.callbacks.remove(callback)
        self.destroyed.connect(destroyed)
        self._thread = threading.Thread(target=self._sample, name="studio-stall-watchdog", daemon=True)
        self._thread.start()

    def beat(self):
        now = time.monotonic()
        gap = now - self.last_beat
        self.max_gap = max(self.max_gap, gap)
        if gap > self.threshold:
            # A C extension holding the GIL can prevent the sampler running.
            # Always preserve the gap, identifying this as a recovery stack.
            self.record("heartbeat-gap", seconds=gap, stack_phase="after-stall",
                        stack="".join(traceback.format_stack()))
        self.last_beat = now

    def record(self, event, **values):
        self.records.append(dict(event=event, at=time.monotonic(), **values))

    def _gc_event(self, phase, info):
        if phase == "start":
            self._gc_start = time.monotonic()
        elif self._gc_start:
            elapsed = time.monotonic() - self._gc_start
            if elapsed > .05:
                self.record("garbage-collection", seconds=elapsed, generation=info["generation"],
                            thread=threading.get_ident())

    def inventory(self, owner):
        # Recursive findChildren(QTimer) itself held Qt's interface thread for
        # 470 ms in the retail probe. Walk a bounded batch per event instead.
        if self._inventory_nodes or self._stop.is_set():
            return
        self._inventory_nodes = [owner]
        self._inventory_rows = []
        self.record("workspace-workers", workers=[
            getattr(getattr(w, "operation", None), "__qualname__", type(w).__name__)
            for w in getattr(owner, "_workers", ())])
        self._inventory_step()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Timer and not self._stop.is_set():
            self.record("timer-fired", name=self._timer_names.get(watched, "QTimer"),
                        interval_ms=watched.interval())
        return False

    def _inventory_step(self):
        if self._stop.is_set():
            self._inventory_nodes.clear()
            return
        deadline = time.monotonic() + .005
        count = 0
        while self._inventory_nodes and count < 64 and time.monotonic() < deadline:
            item = self._inventory_nodes.pop()
            try:
                if isinstance(item, QTimer):
                    parent = item.parent()
                    name = item.objectName() or next((key for key, value in vars(parent).items()
                        if value is item), "QTimer")
                    if parent is not self and item not in self._timer_names:
                        self._timer_names[item] = name
                        item.installEventFilter(self)
                    self._inventory_rows.append(dict(interval_ms=item.interval(), active=item.isActive(),
                        owner=type(parent).__name__, name=name))
                self._inventory_nodes.extend(item.children())
            except RuntimeError:
                pass  # A page was replaced between batches.
            count += 1
        if self._inventory_nodes:
            QTimer.singleShot(0, self._inventory_step)
            return
        self.record("activity", timers=self._inventory_rows,
                    pool_threads=QThreadPool.globalInstance().activeThreadCount(),
                    threads=[t.name for t in threading.enumerate()])

    def _sample(self):
        sampled_beat = None
        next_activity = time.monotonic()
        while not self._stop.wait(.025):
            if time.monotonic() >= next_activity:
                self.record("worker-stacks", stacks={str(ident): "".join(traceback.format_stack(frame))
                    for ident, frame in sys._current_frames().items()
                    if ident not in (self.ui_thread, threading.get_ident())})
                next_activity = time.monotonic() + 5
            beat = self.last_beat
            gap = time.monotonic() - beat
            if gap > self.threshold and sampled_beat != beat:
                sampled_beat = beat
                frames = sys._current_frames()
                row = dict(event="stall", at=time.monotonic(), gap_seconds=gap,
                           stack="".join(traceback.format_stack(frames[self.ui_thread]))
                           if self.ui_thread in frames else "UI thread exited",
                           worker_stacks={str(ident): "".join(traceback.format_stack(frame))
                                          for ident, frame in frames.items()
                                          if ident not in (self.ui_thread, threading.get_ident())})
                self.stalls.append(row)
                self.records.append(row)
            self._flush()
        self._flush()

    def _flush(self):
        if self.path is None or not self.records:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > 8 * 1024 * 1024:
                os.replace(self.path, self.path.with_suffix(".previous.jsonl"))
            with self.path.open("a", encoding="utf-8") as output:
                while self.records:
                    output.write(json.dumps(self.records.popleft()) + "\n")
        except OSError:
            # Diagnostics must not turn an unwritable log folder into a GUI fault.
            self.records.clear()

    def stop(self):
        self.beat()
        self._timer.stop()
        self._inventory_timer.stop()
        self._stop.set()
        self._thread.join(timeout=1)
        if self._gc_event in gc.callbacks:
            gc.callbacks.remove(self._gc_event)


def install_stall_watchdog(owner):
    if os.environ.get("MOD_STUDIO_STALL_LOG") != "1":
        return None
    return StallWatchdog(owner, path=log_directory("2K5 Mod Studio") / "stalls.jsonl")
