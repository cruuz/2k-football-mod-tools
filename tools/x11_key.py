#!/usr/bin/env python3
"""Send a bounded key tap through XTEST to the currently focused X11 window."""

from __future__ import annotations

import argparse
import time

from Xlib import X, XK, display, protocol
from Xlib.ext import xtest


def window_title(window) -> str:
    try:
        value = window.get_wm_name()
        return str(value) if value is not None else ""
    except Exception:
        return ""


def walk(window):
    for child in window.query_tree().children:
        yield child
        yield from walk(child)


def find_window(dpy, pattern: str):
    needle = pattern.casefold()
    matches = [window for window in walk(dpy.screen().root)
               if needle in window_title(window).casefold()]
    if not matches:
        raise SystemExit(f"no X11 window matches: {pattern}")
    return matches[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("key")
    parser.add_argument("--duration", type=float, default=0.15)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--gap", type=float, default=0.20)
    parser.add_argument("--window", help="focus a matching X11 window before XTEST")
    parser.add_argument(
        "--modifier",
        action="append",
        default=[],
        help="modifier keysym to hold during each tap (repeatable)",
    )
    args = parser.parse_args()
    dpy = display.Display()
    keysym = XK.string_to_keysym(args.key)
    if keysym == X.NoSymbol:
        raise SystemExit(f"unknown X11 keysym: {args.key}")
    keycode = dpy.keysym_to_keycode(keysym)
    if keycode == 0:
        raise SystemExit(f"no keycode for X11 keysym: {args.key}")
    modifier_codes = []
    for modifier in args.modifier:
        modifier_keysym = XK.string_to_keysym(modifier)
        modifier_code = dpy.keysym_to_keycode(modifier_keysym)
        if modifier_keysym == X.NoSymbol or modifier_code == 0:
            raise SystemExit(f"unknown X11 modifier keysym: {modifier}")
        modifier_codes.append(modifier_code)
    focus_before = dpy.get_input_focus().focus
    target = None
    if args.window:
        target = find_window(dpy, args.window)
        active = dpy.intern_atom("_NET_ACTIVE_WINDOW")
        event = protocol.event.ClientMessage(
            window=target,
            client_type=active,
            data=(32, [1, X.CurrentTime, 0, 0, 0]),
        )
        dpy.screen().root.send_event(
            event,
            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
        )
        target.set_input_focus(X.RevertToParent, X.CurrentTime)
        dpy.sync()
        time.sleep(0.1)
        focused = dpy.get_input_focus().focus
        if getattr(focused, "id", None) != target.id:
            raise SystemExit(
                f"focus verification failed: target=0x{target.id:x} "
                f"actual=0x{getattr(focused, 'id', 0):x}"
            )
    for index in range(args.count):
        for modifier_code in modifier_codes:
            xtest.fake_input(dpy, X.KeyPress, modifier_code)
        xtest.fake_input(dpy, X.KeyPress, keycode)
        dpy.sync()
        time.sleep(args.duration)
        xtest.fake_input(dpy, X.KeyRelease, keycode)
        for modifier_code in reversed(modifier_codes):
            xtest.fake_input(dpy, X.KeyRelease, modifier_code)
        dpy.sync()
        if index + 1 != args.count:
            time.sleep(args.gap)
    focus_after = dpy.get_input_focus().focus
    print(
        f"TAPPED key={args.key} modifiers={args.modifier!r} "
        f"count={args.count} duration={args.duration:.3f} "
        f"focus_before=0x{getattr(focus_before, 'id', 0):x} "
        f"target=0x{getattr(target, 'id', 0):x} "
        f"focus_after=0x{getattr(focus_after, 'id', 0):x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
