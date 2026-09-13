"""Optional fourth-quarter convenience cutoff. EXPERIMENTAL / UNWITNESSED.

This is a selected margin/time rule, not a proof of mathematical elimination.
The next native dead-ball or huddle boundary zeros only the game timer. The
native period-end dispatcher finishes the game. Live plays and OT are excluded.
"""
from __future__ import annotations
import struct
import sys
from . import nfl2k5_rules_patch as patch
from . import nfl2k5_decided_clock_code as assembly

OWNER = "nfl2k5_decided_clock"
REQUESTS = ((OWNER, "code", 384, 16), (OWNER, "read_only", 8, 4))
DEFAULTS = dict(margin=17, seconds=60)
MARGINS, SECONDS = (9, 17, 25, 33), (15, 30, 60, 90, 120)
BUILD_CAPTION = "Run out the clock when the game is decided (experimental)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. Off in every preset. In the fourth quarter, "
             "at the next dead ball, end the remaining clock if the team with the ball "
             "leads by your selected margin with no more than your selected time left. "
             "Default: at least 17 points and at most 60 seconds. This is a convenience "
             "cutoff, not mathematical elimination. Live plays, the trailing team's "
             "possession and overtime are excluded. Accelerated clock keeps its own rules.")
HOOKS = (("huddle", 0xB6E80, bytes.fromhex("a1b402e600"), b"\xe9"),
         ("dead_ball", 0xA03DC, bytes.fromhex("e89f8c0e00"), b"\xe8"))
GUARDS = (
    (0xb6e80, 47, "b6d0fa1e67fcd7e4190559edd5d68b1233a57dafa5789ebf91ee2893ea830204"),
    (0xa0390, 172, "6aff258270c3e90a2cb79205391a34cb0b9a664da140c9c44ccd80c2e3e1a49e"),
    (0xb7230, 244, "3814ca0d24a0324b7eebae7f19683cd57212822db2e917e991d21b7a287e0b12"),
)


def encode_options(*, margin=17, seconds=60):
    if type(margin) is not int or margin not in MARGINS or type(seconds) is not int or seconds not in SECONDS:
        raise ValueError("Choose a margin of 9, 17, 25 or 33 and a time of 15, 30, 60, 90 or 120 seconds")
    return struct.pack("<If", margin, seconds)


def decode_options(content):
    margin, seconds = struct.unpack("<If", content)
    selected = dict(margin=margin, seconds=int(seconds))
    if encode_options(**selected) != content:
        raise ValueError("Foreign decided-clock options")
    return selected


def code_for(places):
    return patch.relocate(assembly, places, dict(options=places["read_only"]["va"],
                          huddle_tail=0xB6E85, native_lineup=0x189080))


def sites(places):
    return patch.hook_sites(HOOKS, assembly, places)


def status(payload):
    return patch.status(payload, sys.modules[__name__])


def verify(payload, **expected):
    return patch.verify(payload, sys.modules[__name__], expected or None)


def apply(payload, *, margin=None, seconds=None):
    old = patch.inspect(payload, sys.modules[__name__]) or DEFAULTS
    selected = dict(margin=old["margin"] if margin is None else margin,
                    seconds=old["seconds"] if seconds is None else seconds)
    return patch.apply(payload, sys.modules[__name__], selected)
