"""EXPERIMENTAL / UNWITNESSED: expand Coverage's direct ball-reaction range.

FUN_001f4250 adds two unchanged context curves to the slider contribution.
Retail: (C + .25) * .15. Patch: C * .225. At 50 the contribution stays .1125.
Zero does NOT prevent all reactions and 100 does NOT double total reaction
odds. Shared retail constants and the separate Receiving-v-Coverage roll in
FUN_002e91f0 stay intact. No interception/catch roll is changed.
"""
from __future__ import annotations

import struct
import sys

from . import nfl2k5_gameplay_lever as lever

OWNER = "nfl2k5_coverage_slider"
CODE_SIZE = 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
# Match the retail float32 store at C=.5 exactly. Rounding decimal .225
# directly picks the neighboring float and slightly moves that neutral point.
RETAIL_SLOPE = struct.unpack("<f", bytes.fromhex("9a99193e"))[0]
PATCH_SLOPE = 2 * struct.unpack("<f", struct.pack("<f", .75 * RETAIL_SLOPE))[0]
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail Coverage adds a small amount to a defender's "
    "chance to react to the ball. Patch: 0 removes that added amount, 50 keeps the "
    "retail contribution at 50, and 100 doubles that contribution. Facing and player "
    "state still affect reactions at every setting. This does not set interception odds."
)
GUARDS = (
    (0x1f4250, 265, "ce0a092d613c2f64eb94dd9f3b9ec51cfa0df2105cc240e57bfbeab8e3f8731c"),
    (0x17b8f0, 21, "69de4b0afd6ef65c3d6336cff7c41431b48c2bd6454f145642b04cf248bdfe20"),
    (0x50b32c, 88, "5996652ced4767f29e4cdac5f5b85a2bf4511ee906a5c63a027e4971b320eb2c"),
    (0x1b0ae0, 124, "85257e0d17fc30f87b44015e57a7951be3785ef634995aafaec65c9f5fc2bc7c"),
    (0x4e696c, 4, "75e253f50979177eba47b2d0805ad36038789108924514d2a761a70de057d16f"),
    (0x4e88d8, 4, "5059b35a51a066cc88e72daa9017c4e126068c6368cd3b9f45b4d8d5cc94b3e5"),
)


def sites(va):
    return [("reaction_offset", 0x1F4282, bytes.fromhex("d8056c694e00"), b"\xd8\x05" + struct.pack("<I", va)),
            ("reaction_slope", 0x1F432C, bytes.fromhex("d80dd8884e00"), b"\xd8\x0d" + struct.pack("<I", va + 4))]


def code_for(va):
    return struct.pack("<2f", 0.0, PATCH_SLOPE) + b"\xcc" * 8


def mapping():
    return {"runtime_slider_index": 6, "human_table_va": "0xaab8c0", "cpu_table_va": "0xaab8e8",
            "consumer_va": "0x1f4250", "formula_retail": "(C + 0.25) * 0.15 + context",
            "formula_patch": "C * 0.225 + context",
            "patch_slope_float32": PATCH_SLOPE,
            "points": [{"slider": c, "retail_contribution": (c / 100 + .25) * .15,
                        "patch_contribution": c / 100 * .225} for c in (0, 50, 100)],
            "other_consumer": "0x2e91f0 compares offense Receiving (3) with defense Coverage (6); unchanged"}


def status(payload):
    return lever.status(payload, sys.modules[__name__])


def apply(payload):
    return lever.apply(payload, sys.modules[__name__])
