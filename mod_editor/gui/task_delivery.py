"""Deliver background-task results to a widget only while that widget exists.

Every panel runs disc reads and writes on a ``QThreadPool`` and connects the
task's signals to small closures that update the panel.  PyQt invokes such a
closure even after the widget it captured has been destroyed: a queued
delivery (worker thread to GUI thread) that lands after the panel is torn down
runs against a dead C++ object.  That is a segmentation fault, not a Python
error -- the macOS CI runner died exactly this way when a window was deleted
while its commentary panel was still listing the speech banks of a disc.

``bound(owner, callback)`` returns a closure to connect in the callback's
place.  It delivers exactly as before while ``owner`` lives and becomes a
no-op the moment Qt reports the owner destroyed (``QObject.destroyed`` fires
synchronously inside the destructor, before any later event delivery), with
``sip.isdeleted`` as a second check.  It is deliberately still a closure, not
a QObject: PyQt ties a connected closure's lifetime to the signal's own
object, so a finished task and everything its callbacks captured are
collected exactly as they were.  One liveness flag is shared by every
callback of an owner, so nothing accumulates per task.
"""
from __future__ import annotations

from typing import Callable

from PyQt5 import sip
from PyQt5.QtCore import QObject

_FLAG = "_task_delivery_alive"


def _liveness(owner: QObject) -> list[bool]:
    """The owner's shared ``[alive]`` flag, created on first use and cleared by ``destroyed``."""
    flag = owner.__dict__.get(_FLAG)
    if flag is None:
        flag = [True]
        owner.__dict__[_FLAG] = flag

        def gone(*_args: object) -> None:
            flag[0] = False

        owner.destroyed.connect(gone)
    return flag


def bound(owner: QObject, callback: Callable[..., object]) -> Callable[..., None]:
    """``callback``, delivered only while ``owner`` exists.

    Connect the result instead of the bare closure::

        task.signals.finished.connect(bound(self, done))

    While the owner lives the callback is invoked with the signal's arguments
    exactly as before; after the owner's C++ object is destroyed the delivery
    is dropped instead of touching a dead widget.
    """
    alive = _liveness(owner)

    def deliver(*payload: object) -> None:
        if alive[0] and not sip.isdeleted(owner):
            callback(*payload)

    return deliver


__all__ = ["bound"]
