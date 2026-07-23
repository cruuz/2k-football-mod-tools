#!/usr/bin/env python3
"""Hash-stable virtual Xbox controller for the queued APF selector replay.

This helper intentionally accepts only the three controls used by the frozen
APF replay transcript: A, START, and RT.  Keeping it separate from the shared
general-purpose controller prevents unrelated emulator work from changing the
queued APF evidence toolchain.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import sys
import time

from evdev import AbsInfo, UInput, ecodes


BUTTONS = {
    "A": ecodes.BTN_SOUTH,
    "START": ecodes.BTN_START,
}
TRIGGERS = {
    "RT": ecodes.ABS_RZ,
}
ALLOWED_CONTROLS = frozenset(BUTTONS | TRIGGERS)

STICK = AbsInfo(
    value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0
)
TRIGGER = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
HAT = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)

# Advertise a complete Xbox-style layout so SDL/Xenia recognizes the device as
# a gamepad even though this bounded replay accepts only A, START, and RT.
CAPABILITIES = {
    ecodes.EV_KEY: [
        ecodes.BTN_SOUTH,
        ecodes.BTN_EAST,
        ecodes.BTN_WEST,
        ecodes.BTN_NORTH,
        ecodes.BTN_START,
        ecodes.BTN_SELECT,
        ecodes.BTN_TL,
        ecodes.BTN_TR,
        ecodes.BTN_THUMBL,
        ecodes.BTN_THUMBR,
        ecodes.BTN_MODE,
    ],
    ecodes.EV_ABS: [
        (ecodes.ABS_X, STICK),
        (ecodes.ABS_Y, STICK),
        (ecodes.ABS_RX, STICK),
        (ecodes.ABS_RY, STICK),
        (ecodes.ABS_Z, TRIGGER),
        (ecodes.ABS_RZ, TRIGGER),
        (ecodes.ABS_HAT0X, HAT),
        (ecodes.ABS_HAT0Y, HAT),
    ],
}


@dataclass(frozen=True)
class Tap:
    control: str
    duration_seconds: float


def parse_command(line: str) -> Tap | None:
    """Parse one replay command; return ``None`` for QUIT/EXIT.

    The bounded duration rejects accidental indefinitely held inputs and keeps
    the helper unsuitable for unrelated interactive emulator sessions.
    """

    parts = line.strip().upper().split()
    if parts in (["QUIT"], ["EXIT"]):
        return None
    if len(parts) != 3 or parts[0] != "TAP":
        raise ValueError("expected: TAP {A|START|RT} SECONDS, or QUIT")
    control = parts[1]
    if control not in ALLOWED_CONTROLS:
        raise ValueError(f"control is outside the APF replay contract: {control}")
    try:
        duration = float(parts[2])
    except ValueError as exc:
        raise ValueError("tap duration is not numeric") from exc
    if not math.isfinite(duration) or not 0.01 <= duration <= 5.00:
        raise ValueError("tap duration must be finite and between 0.01 and 5.00")
    return Tap(control=control, duration_seconds=duration)


def tap(controller: UInput, command: Tap) -> None:
    if command.control in BUTTONS:
        event_type = ecodes.EV_KEY
        code = BUTTONS[command.control]
        active = 1
    else:
        event_type = ecodes.EV_ABS
        code = TRIGGERS[command.control]
        active = 255
    controller.write(event_type, code, active)
    controller.syn()
    time.sleep(command.duration_seconds)
    controller.write(event_type, code, 0)
    controller.syn()


def main() -> int:
    with UInput(
        CAPABILITIES,
        name="Microsoft X-Box 360 pad",
        vendor=0x045E,
        product=0x028E,
        version=0x0114,
        bustype=ecodes.BUS_USB,
    ) as controller:
        print(f"READY {controller.device.path}", flush=True)
        for raw_line in sys.stdin:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                command = parse_command(stripped)
            except ValueError as exc:
                print(f"ERROR {exc}", flush=True)
                continue
            if command is None:
                print("BYE", flush=True)
                return 0
            tap(controller, command)
            print(
                f"TAPPED {command.control} {command.duration_seconds:.3f}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
