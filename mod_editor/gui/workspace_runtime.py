"""Responsiveness policy for the metadata-heavy 2K5 Qt process."""
import gc
import platform

from .stall_watchdog import install_stall_watchdog


def install(owner):
    # Catalogs retain hundreds of thousands of long-lived, mostly acyclic
    # records. The default ten generation-1 collections repeatedly sweep this
    # whole graph during source preparation (measured 0.2–0.3 s with the GIL).
    # Keep young-cycle collection and reference counting unchanged; sweep old
    # cycles less often. Do not lower a host's already more relaxed setting.
    if platform.python_implementation() == "CPython":
        young, middle, old = gc.get_threshold()
        gc.set_threshold(young, middle, max(old, 100))
    return install_stall_watchdog(owner)
