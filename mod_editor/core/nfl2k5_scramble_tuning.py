"""EXPERIMENTAL / UNWITNESSED native acceleration curve for slow QB carriers.

At the one interpolator call in FUN_001df190, select a private 65% copy of the
native curve when live phase == 14, attached holder == this player, roster
position == QB (0), and raw Speed <= 60. Keep native weight/Agility factors,
first-step floor, top speed, animation coupling and every AI decision intact.
The raw rating avoids the legacy acceleration envelope reclassifying fast QBs.
No new runtime history; valid CPU steering marker -1 receives the same rule.
"""
from __future__ import annotations

import struct
import sys

from . import nfl2k5_gameplay_lever as lever
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_scramble_tuning"
CODE_SIZE, TABLE_OFFSET = 160, 112
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
SPEED_THRESHOLD, CURVE_FACTOR = 60, 0.65
HOOK_VA, INTERPOLATOR_VA = 0x1DF1A5, 0x1B0AE0
RETAIL_HOOK = bytes.fromhex("e83619fdff")
RETAIL_CURVE = bytes.fromhex(
    "050000000000003f0000803fcdcc4c3f0000403f6666663f0000003f"
    "3333733fcdcc4c3d0000803f00000000")
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail already has acceleration. Patch: a QB "
    "with Speed 60 or lower gains speed more slowly while carrying the ball in live play. "
    "The added acceleration is 65% of retail; the first-step floor and top speed stay the same. "
    "Human and CPU carriers use the same rule. This does not change when the CPU decides to run."
)
GUARDS = (
    (0x1df190, 128, "bb272967d68eccb3c4463ba1c6a9d2592194ff4a0a88d740a779d16f34c4f38b"),
    (0x50a5b4, 44, "f2bc43da3c45a02bef455b931c73cb738f7fc445280afe35292ee10757b1f5f1"),
    (0x1b0ae0, 124, "85257e0d17fc30f87b44015e57a7951be3785ef634995aafaec65c9f5fc2bc7c"),
    (0x1ce280, 24, "24b68bb260aa7d47af8e6dad375b7db175639f4f260363d2f6d43493c09a9e69"),
    (0x4efdf4, 4, "ffcd594324296033e35bb6b3ea4a3d6e9b3b4db169f4e1968861c5746a9bf958"),
    (0x4f6774, 4, "0cd78fc5bf341032fcadb03079458783bac2e3e616c7da1603d8788205a13bd0"),
    (0x4f003c, 4, "8b35fe1a9b331dc0217e0419be35288af59676e9c57022a334110ab0e4799df4"),
    (0x4f6b48, 4, "2bf14e785577603fda60476e5e5cfd313b95b39166647c4fa6b0b00fcd6d46b3"),
)


def table_bytes():
    out = bytearray(RETAIL_CURVE)
    for off in range(8, len(out), 8):
        struct.pack_into("<f", out, off, struct.unpack_from("<f", out, off)[0] * CURVE_FACTOR)
    return bytes(out)


def code_for(va):
    a = _Asm(va)
    a.b("9c50")  # preserve flags/EAX; no x87 or SSE work in the selector
    a.b("833db802e6000e")
    a.j8("75", "done")
    a.b("a100fce50085c0")
    a.j8("74", "done")
    a.b("83f8ff")
    a.j8("74", "done")
    a.b("83781c01")  # retail attached-player ball kind
    a.j8("75", "done")
    a.b("3938")  # ball's holder == EDI
    a.j8("75", "done")
    a.b("8b473c85c0")
    a.j8("74", "done")
    a.b("83f8ff")
    a.j8("74", "done")
    a.b("80783500")  # roster position, not formation role/archetype
    a.j8("75", "done")
    a.b("807836" + bytes([SPEED_THRESHOLD]).hex())
    a.j8("77", "done")
    a.b("b9" + struct.pack("<I", va + TABLE_OFFSET + 4).hex())
    a.label("done")
    a.b("589d")
    a.jmp_abs(INTERPOLATOR_VA)  # tail call retains original return address / ret-4 ABI
    code = a.assemble()
    if len(code) > TABLE_OFFSET:
        raise ValueError("scramble selector exceeded its reservation")
    return code + b"\xcc" * (TABLE_OFFSET - len(code)) + table_bytes() + b"\xcc" * 4


def sites(va):
    return [("acceleration_curve_call", HOOK_VA, RETAIL_HOOK,
             b"\xe8" + struct.pack("<i", va - HOOK_VA - 5))]


def mapping():
    return {"speed_threshold_inclusive": SPEED_THRESHOLD, "raw_position": 0,
            "raw_position_offset": "0x35", "raw_speed_offset": "0x36", "live_phase": 14,
            "requires_ball_holder": True, "factor": CURVE_FACTOR,
            "retail_table_va": "0x50a5b4", "retail_table_bytes": RETAIL_CURVE.hex(),
            "patch_table_bytes": table_bytes().hex(), "cpu_decision_changed": False,
            "first_step_floor_changed": False, "top_speed_changed": False}


def status(payload):
    return lever.status(payload, sys.modules[__name__])


def apply(payload):
    return lever.apply(payload, sys.modules[__name__])
