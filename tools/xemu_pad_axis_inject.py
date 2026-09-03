#!/usr/bin/env python3
"""Push a stick on the harness's virtual pad from outside the harness process.

Writing to an evdev node injects events into the input core (the device must not be
grabbed; SDL/xemu never grab), so a running xemu_virtual_gamepad.py device can be driven
by a second process.  usage:
    xemu_pad_axis_inject.py /dev/input/eventN AXIS VALUE [SECONDS]
AXIS in X Y RX RY (stick, -32767..32767) or Z RZ (trigger 0..255).  With SECONDS the axis is
held that long, then released to 0.
"""
from __future__ import annotations

import sys
import time

from evdev import InputDevice, ecodes

AXES = {"X": ecodes.ABS_X, "Y": ecodes.ABS_Y, "RX": ecodes.ABS_RX, "RY": ecodes.ABS_RY,
        "Z": ecodes.ABS_Z, "RZ": ecodes.ABS_RZ}


def main() -> int:
    path, axis, value = sys.argv[1], sys.argv[2].upper(), int(sys.argv[3])
    secs = float(sys.argv[4]) if len(sys.argv) > 4 else None
    dev = InputDevice(path)
    code = AXES[axis]
    dev.write(ecodes.EV_ABS, code, value)
    dev.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
    print(f"{axis}={value}", flush=True)
    if secs is not None:
        time.sleep(secs)
        dev.write(ecodes.EV_ABS, code, 0)
        dev.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
        print(f"{axis}=0 after {secs}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
