#!/usr/bin/env python3
"""List, focus, or gracefully close X11 top-level windows by title."""

from __future__ import annotations

import argparse
import time

from Xlib import X, display, protocol


def title(window) -> str:
    try:
        value = window.get_wm_name()
        return str(value) if value is not None else ""
    except Exception:
        return ""


def walk(window):
    for child in window.query_tree().children:
        yield child
        yield from walk(child)


def matches(dpy, needle: str):
    needle = needle.casefold()
    return [(w, title(w)) for w in walk(dpy.screen().root)
            if needle in title(w).casefold()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("list", "id", "focus", "close", "wait"))
    parser.add_argument("pattern", nargs="?", default="")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    dpy = display.Display()

    if args.action == "list":
        for window, text in matches(dpy, args.pattern):
            print(f"0x{window.id:x}\t{text}")
        return 0

    deadline = time.monotonic() + args.timeout
    found = []
    while time.monotonic() < deadline:
        found = matches(dpy, args.pattern)
        if found:
            break
        time.sleep(0.1)
    if not found:
        return 1
    window, text = found[-1]

    if args.action in {"id", "wait"}:
        print(f"0x{window.id:x}\t{text}")
        return 0
    if args.action == "focus":
        active = dpy.intern_atom("_NET_ACTIVE_WINDOW")
        event = protocol.event.ClientMessage(
            window=window,
            client_type=active,
            data=(32, [1, X.CurrentTime, 0, 0, 0]),
        )
        dpy.screen().root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        dpy.sync()
        print(f"FOCUSED 0x{window.id:x}\t{text}")
        return 0
    wm_protocols = dpy.intern_atom("WM_PROTOCOLS")
    wm_delete = dpy.intern_atom("WM_DELETE_WINDOW")
    event = protocol.event.ClientMessage(
        window=window,
        client_type=wm_protocols,
        data=(32, [wm_delete, X.CurrentTime, 0, 0, 0]),
    )
    window.send_event(event)
    dpy.sync()
    print(f"CLOSE_SENT 0x{window.id:x}\t{text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
