#!/usr/bin/env python3
"""Persistent virtual Xbox 360-style controller for bounded Xenia testing."""

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
    "LS": ecodes.BTN_THUMBL,
    "RS": ecodes.BTN_THUMBR,
}

DIRECTION_AXES = {
    "UP": (ecodes.ABS_HAT0Y, -1),
    "DOWN": (ecodes.ABS_HAT0Y, 1),
    "LEFT": (ecodes.ABS_HAT0X, -1),
    "RIGHT": (ecodes.ABS_HAT0X, 1),
    "LS_UP": (ecodes.ABS_Y, -32768),
    "LS_DOWN": (ecodes.ABS_Y, 32767),
    "LS_LEFT": (ecodes.ABS_X, -32768),
    "LS_RIGHT": (ecodes.ABS_X, 32767),
    "RS_UP": (ecodes.ABS_RY, -32768),
    "RS_DOWN": (ecodes.ABS_RY, 32767),
    "RS_LEFT": (ecodes.ABS_RX, -32768),
    "RS_RIGHT": (ecodes.ABS_RX, 32767),
}

STICK_DIRECTIONS = {
    "LS_UP_LEFT": ((ecodes.ABS_X, -32768), (ecodes.ABS_Y, -32768)),
    "LS_UP_RIGHT": ((ecodes.ABS_X, 32767), (ecodes.ABS_Y, -32768)),
    "LS_DOWN_LEFT": ((ecodes.ABS_X, -32768), (ecodes.ABS_Y, 32767)),
    "LS_DOWN_RIGHT": ((ecodes.ABS_X, 32767), (ecodes.ABS_Y, 32767)),
    "RS_UP_LEFT": ((ecodes.ABS_RX, -32768), (ecodes.ABS_RY, -32768)),
    "RS_UP_RIGHT": ((ecodes.ABS_RX, 32767), (ecodes.ABS_RY, -32768)),
    "RS_DOWN_LEFT": ((ecodes.ABS_RX, -32768), (ecodes.ABS_RY, 32767)),
    "RS_DOWN_RIGHT": ((ecodes.ABS_RX, 32767), (ecodes.ABS_RY, 32767)),
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


def tap_button(ui: UInput, code: int, duration: float) -> None:
    ui.write(ecodes.EV_KEY, code, 1)
    ui.syn()
    time.sleep(duration)
    ui.write(ecodes.EV_KEY, code, 0)
    ui.syn()


def tap_direction(ui: UInput, code: int, value: int, duration: float) -> None:
    ui.write(ecodes.EV_ABS, code, value)
    ui.syn()
    time.sleep(duration)
    ui.write(ecodes.EV_ABS, code, 0)
    ui.syn()


def tap_stick_direction(
    ui: UInput, axes: tuple[tuple[int, int], tuple[int, int]], duration: float
) -> None:
    for code, value in axes:
        ui.write(ecodes.EV_ABS, code, value)
    ui.syn()
    time.sleep(duration)
    for code, _ in axes:
        ui.write(ecodes.EV_ABS, code, 0)
    ui.syn()


def tap_trigger(ui: UInput, code: int, duration: float) -> None:
    ui.write(ecodes.EV_ABS, code, 255)
    ui.syn()
    time.sleep(duration)
    ui.write(ecodes.EV_ABS, code, 0)
    ui.syn()


def set_named_control(ui: UInput, name: str, active: bool) -> bool:
    """Press/release one named control without sleeping."""
    if name in BUTTONS:
        ui.write(ecodes.EV_KEY, BUTTONS[name], int(active))
    elif name in DIRECTION_AXES:
        code, value = DIRECTION_AXES[name]
        ui.write(ecodes.EV_ABS, code, value if active else 0)
    elif name in STICK_DIRECTIONS:
        for code, value in STICK_DIRECTIONS[name]:
            ui.write(ecodes.EV_ABS, code, value if active else 0)
    elif name in TRIGGER_AXES:
        ui.write(ecodes.EV_ABS, TRIGGER_AXES[name], 255 if active else 0)
    else:
        return False
    ui.syn()
    return True


def tap_named_control(ui: UInput, name: str, duration: float) -> bool:
    if not set_named_control(ui, name, True):
        return False
    time.sleep(duration)
    set_named_control(ui, name, False)
    return True


with UInput(
    capabilities,
    name="Microsoft X-Box 360 pad",
    vendor=0x045E,
    product=0x028E,
    version=0x0114,
    bustype=ecodes.BUS_USB,
) as controller:
    print(f"READY {controller.device.path}", flush=True)
    for raw_line in sys.stdin:
        parts = raw_line.strip().upper().split()
        if not parts:
            continue
        if parts[0] in {"QUIT", "EXIT"}:
            print("BYE", flush=True)
            break
        if parts[0] == "AFTER_PULSE" and len(parts) == 6:
            name = parts[1]
            delay = float(parts[2])
            count = int(parts[3])
            duration = float(parts[4])
            gap = float(parts[5])
            if delay < 0 or count < 1 or duration <= 0 or gap < 0:
                print("ERROR invalid pulse timing/count", flush=True)
                continue
            time.sleep(delay)
            if name not in BUTTONS:
                print("ERROR AFTER_PULSE currently supports buttons only", flush=True)
                continue
            for pulse_index in range(count):
                tap_named_control(controller, name, duration)
                if pulse_index + 1 < count:
                    time.sleep(gap)
            print(
                f"PULSED {name} {count}x {duration:.3f} gap {gap:.3f}",
                flush=True,
            )
            continue
        if parts[0] == "AFTER_HOLD_TAP" and len(parts) == 7:
            hold_name = parts[1]
            tap_name = parts[2]
            delay = float(parts[3])
            lead = float(parts[4])
            tap_duration = float(parts[5])
            tail = float(parts[6])
            if min(delay, lead, tail) < 0 or tap_duration <= 0:
                print("ERROR invalid hold/tap timing", flush=True)
                continue
            time.sleep(delay)
            if not set_named_control(controller, hold_name, True):
                print(f"ERROR unknown control: {hold_name}", flush=True)
                continue
            time.sleep(lead)
            if not tap_named_control(controller, tap_name, tap_duration):
                set_named_control(controller, hold_name, False)
                print(f"ERROR unknown control: {tap_name}", flush=True)
                continue
            time.sleep(tail)
            set_named_control(controller, hold_name, False)
            print(
                f"HELD {hold_name}; TAPPED {tap_name} after {lead:.3f}",
                flush=True,
            )
            continue
        if parts[0] == "AFTER" and len(parts) in {3, 4}:
            name = parts[1]
            delay = float(parts[2])
            duration = float(parts[3]) if len(parts) == 4 else 0.20
            if delay < 0:
                print("ERROR delay must be non-negative", flush=True)
                continue
            time.sleep(delay)
        elif parts[0] == "TAP" and len(parts) in {2, 3}:
            name = parts[1]
            duration = float(parts[2]) if len(parts) == 3 else 0.20
        else:
            print(f"ERROR unsupported command: {raw_line.strip()}", flush=True)
            continue
        if name in BUTTONS:
            tap_button(controller, BUTTONS[name], duration)
        elif name in DIRECTION_AXES:
            tap_direction(controller, *DIRECTION_AXES[name], duration)
        elif name in STICK_DIRECTIONS:
            tap_stick_direction(controller, STICK_DIRECTIONS[name], duration)
        elif name in TRIGGER_AXES:
            tap_trigger(controller, TRIGGER_AXES[name], duration)
        else:
            print(f"ERROR unknown control: {name}", flush=True)
            continue
        print(f"TAPPED {name} {duration:.3f}", flush=True)
