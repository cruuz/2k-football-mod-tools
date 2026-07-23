#!/usr/bin/env python3
"""Persistent virtual Xbox 360-style controller for bounded xemu testing."""

from __future__ import annotations

import sys
import time

from evdev import AbsInfo, UInput, ecodes


BUTTONS = {
    "A": ecodes.BTN_SOUTH,
    "B": ecodes.BTN_EAST,
    "X": ecodes.BTN_WEST,
    "Y": ecodes.BTN_NORTH,
    "START": ecodes.BTN_START,
    "BACK": ecodes.BTN_SELECT,
    "LB": ecodes.BTN_TL,
    "RB": ecodes.BTN_TR,
}

DIRECTION_AXES = {
    "UP": (ecodes.ABS_HAT0Y, -1),
    "DOWN": (ecodes.ABS_HAT0Y, 1),
    "LEFT": (ecodes.ABS_HAT0X, -1),
    "RIGHT": (ecodes.ABS_HAT0X, 1),
}

TRIGGER_AXES = {
    "LT": ecodes.ABS_Z,
    "RT": ecodes.ABS_RZ,
}

stick = AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)
trigger = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
hat = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)

capabilities = {
    ecodes.EV_KEY: list(BUTTONS.values())
    + [ecodes.BTN_THUMBL, ecodes.BTN_THUMBR, ecodes.BTN_MODE],
    ecodes.EV_ABS: [
        (ecodes.ABS_X, stick),
        (ecodes.ABS_Y, stick),
        (ecodes.ABS_RX, stick),
        (ecodes.ABS_RY, stick),
        (ecodes.ABS_Z, trigger),
        (ecodes.ABS_RZ, trigger),
        (ecodes.ABS_HAT0X, hat),
        (ecodes.ABS_HAT0Y, hat),
    ],
}


def set_control(ui: UInput, name: str, active: bool) -> None:
    if name in BUTTONS:
        ui.write(ecodes.EV_KEY, BUTTONS[name], int(active))
    elif name in DIRECTION_AXES:
        code, value = DIRECTION_AXES[name]
        ui.write(ecodes.EV_ABS, code, value if active else 0)
    elif name in TRIGGER_AXES:
        ui.write(ecodes.EV_ABS, TRIGGER_AXES[name], 255 if active else 0)
    else:
        raise ValueError(f"unknown control: {name}")
    ui.syn()


def print_state(ui: UInput) -> None:
    device = ui.device
    if device is None:
        print("STATE unavailable=device-discovery-pending", flush=True)
        return
    active_keys = [
        ecodes.bytype[ecodes.EV_KEY].get(code, str(code))
        for code in device.active_keys()
    ]
    axes = {
        "HAT0X": device.absinfo(ecodes.ABS_HAT0X).value,
        "HAT0Y": device.absinfo(ecodes.ABS_HAT0Y).value,
        "Z": device.absinfo(ecodes.ABS_Z).value,
        "RZ": device.absinfo(ecodes.ABS_RZ).value,
    }
    print(f"STATE keys={active_keys!r} axes={axes!r}", flush=True)


with UInput(
    capabilities,
    name="Microsoft X-Box 360 pad",
    vendor=0x045E,
    product=0x028E,
    version=0x0114,
    bustype=ecodes.BUS_USB,
) as controller:
    deadline = time.monotonic() + 3.0
    device = controller.device
    while device is None and time.monotonic() < deadline:
        time.sleep(0.05)
        device = controller.device
    if device is None:
        raise RuntimeError("uinput event-device discovery timed out")
    print(
        "READY "
        f"path={device.path} name={device.name!r} "
        "bus=0x0003 vendor=0x045e product=0x028e version=0x0114",
        flush=True,
    )
    for raw_line in sys.stdin:
        parts = raw_line.strip().upper().split()
        if not parts:
            continue
        if parts[0] in {"QUIT", "EXIT"}:
            print("BYE", flush=True)
            break
        if parts[0] == "STATE" and len(parts) == 1:
            print_state(controller)
            continue
        if parts[0] in {"HOLD", "RELEASE"} and len(parts) == 2:
            name = parts[1]
            try:
                set_control(controller, name, parts[0] == "HOLD")
            except ValueError as error:
                print(f"ERROR {error}", flush=True)
                continue
            print(f"{parts[0]} {name}", flush=True)
            continue
        if parts[0] == "TAP" and len(parts) in {2, 3}:
            name = parts[1]
            duration = float(parts[2]) if len(parts) == 3 else 0.20
            try:
                set_control(controller, name, True)
                time.sleep(duration)
                set_control(controller, name, False)
            except ValueError as error:
                print(f"ERROR {error}", flush=True)
                continue
            print(f"TAPPED {name} {duration:.3f}", flush=True)
            continue
        print(f"ERROR unsupported command: {raw_line.strip()}", flush=True)
