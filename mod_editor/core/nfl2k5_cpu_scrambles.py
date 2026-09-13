"""One CPU pocket escape lottery threshold. EXPERIMENTAL / UNWITNESSED.

At 0x19C36C in the passing AI 0x19BB60, the timer-gated pressure branch
uses 0.25 * effective Scramble as its escape probability. Modern uses 0.50
for CPU QBs in live scrimmage only. This is not calibrated to NFL game averages.
Neither the roster parity bit nor the slow-QB acceleration owner is changed.
"""
from __future__ import annotations
import struct
import sys
from . import nfl2k5_rules_patch as patch
from . import nfl2k5_cpu_scrambles_code as assembly

OWNER = "nfl2k5_cpu_scrambles"
REQUESTS = ((OWNER, "code", 128, 16), (OWNER, "read_only", 4, 4))
DEFAULTS = {}
RETAIL_FACTOR, MODERN_FACTOR = 0.25, 0.50
BUILD_CAPTION = "CPU QB scrambles: retail / modern (experimental)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. Retail in every preset. Modern doubles "
             "one existing CPU pocket escape lottery threshold from 0.25 to 0.50 "
             "times effective Scramble. Its pressure and timer conditions remain. "
             "More branch hits are proved under identical native inputs; NFL-average "
             "scrambles per game are not established. Human steering and acceleration "
             "are unchanged.")
HOOKS = (("threshold", 0x19C36C, bytes.fromhex("d80d6c694e00"), b"\xe8"),)
GUARDS = (
    (0x19bb60, 2510, "fdc6a3131d3475c3583cbbc91857d24c02599ef3b29772f8b3e9dedd15cb7aef"),
    (0x197de0, 34, "52a717fa87327f72b042ad47877fc27d7778ed08b64b811fa9e07b69c56508ee"),
    (0x48b90, 41, "093cf53c774b31825b84db51c0e070a603606c6f6b4cce2ee7a9381e9e9f004e"),
    (0x198530, 14, "0bea881549322f1a27f9d2797abb2ab06773a3121c0aa00186e0975c94a7d693"),
    (0x198540, 154, "19a02acb3a9aa11f62959327dba672e681420dfcb8bf91ca66f34d39f1a9f87b"),
    (0x2e36f0, 234, "a25ce6373a7ebc5ae2adeed41699c4b4c145edb25fea4b59020e5c180d3ce3ba"),
    (0x4e696c, 4, "75e253f50979177eba47b2d0805ad36038789108924514d2a761a70de057d16f"),
)


def encode_options():
    return struct.pack("<f", MODERN_FACTOR)


def decode_options(content):
    if content != encode_options():
        raise ValueError("Foreign CPU scramble threshold")
    return {}


def code_for(places):
    return patch.relocate(assembly, places, dict(factor=places["read_only"]["va"]))


def sites(places):
    return patch.hook_sites(HOOKS, assembly, places)


def status(payload):
    return patch.status(payload, sys.modules[__name__])


def verify(payload):
    return dict(**patch.verify(payload, sys.modules[__name__]),
                retail_factor=RETAIL_FACTOR, modern_factor=MODERN_FACTOR,
                nfl_average_calibrated=False)


def apply(payload):
    return patch.apply(payload, sys.modules[__name__])
