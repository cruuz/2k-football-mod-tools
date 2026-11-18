"""One CPU pocket escape lottery threshold. EXPERIMENTAL / UNWITNESSED.

At 0x19C36C in the passing AI 0x19BB60, the timer-gated pressure branch
uses 0.25 * effective Scramble as its escape probability. Modern uses 0.3125
for pressured CPU QBs, keeps early clean-pocket reads, and restores the retail
lottery after 2.5 seconds in a clean pocket. This is not calibrated to NFL game averages.
Neither the roster parity bit nor the slow-QB acceleration owner is changed.
"""
from __future__ import annotations
import struct
import sys
from types import SimpleNamespace
from . import nfl2k5_rules_patch as patch
from . import nfl2k5_cpu_scrambles_code as assembly

OWNER = "nfl2k5_cpu_scrambles"
REQUESTS = ((OWNER, "code", 128, 16), (OWNER, "read_only", 4, 4))
DEFAULTS = {}
RETAIL_FACTOR, MODERN_FACTOR = 0.25, 0.3125
BETA80_FACTOR = struct.pack("<f", 0.50)
BUILD_CAPTION = "CPU QB scrambles: retail / modern (experimental)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. Modern keeps a CPU quarterback reading a clean pocket for the first "
             "2.5 seconds after the snap. After that it uses the retail escape chance. Under pressure the lottery "
             "factor rises from 0.25 to 0.3125 times effective Scramble. NFL-average scrambles per game are not established.")
HOOKS = (("threshold", 0x19C36C, bytes.fromhex("d80d6c694e00"), b"\xe8"),)
GUARDS = (
    (0x19bb60, 2510, "fdc6a3131d3475c3583cbbc91857d24c02599ef3b29772f8b3e9dedd15cb7aef"),
    (0x197de0, 34, "52a717fa87327f72b042ad47877fc27d7778ed08b64b811fa9e07b69c56508ee"),
    (0x48b90, 41, "093cf53c774b31825b84db51c0e070a603606c6f6b4cce2ee7a9381e9e9f004e"),
    (0x198530, 14, "0bea881549322f1a27f9d2797abb2ab06773a3121c0aa00186e0975c94a7d693"),
    (0x198540, 154, "19a02acb3a9aa11f62959327dba672e681420dfcb8bf91ca66f34d39f1a9f87b"),
    # Defensive try owns the intervening five-byte call at 0x2E3786.
    (0x2e36f0, 150, "25c860230ce2276fd5d8eefb18d6e2959f057e013c69305d179d3714499b7371"),
    (0x2e378b, 79, "62a564fd710e1dfbf70828c3bf68b17ee4bcf8d63e73b2194fdd4ce0764e4fd2"),
    (0x4e696c, 4, "75e253f50979177eba47b2d0805ad36038789108924514d2a761a70de057d16f"),
)


def validate_neighbors(payload, image):
    # The five-byte call excluded from GUARDS must be retail or the complete
    # verified defensive-try owner; a plausible branch alone is insufficient.
    if image.read(0x2E3786, 5) != bytes.fromhex("e805f3ffff"):
        from . import nfl2k5_defensive_try as defensive_try
        if defensive_try.status(payload) != "applied":
            raise ValueError("Foreign defensive-try neighbor at 0x2E3786")


def neighbor_sites(payload):
    # b776-ai2: the CPU QB reads owner hooks 0x19B7D3 (outside), 0x19BC72 and 0x19BD8C (inside
    # the guarded QB tick). Only its own completely verified installation is normalized.
    # b780 a-passer: so are the CPU passer owner's pump operands (0x19BFD1, 0x19C1C2, 0x19C194).
    from . import nfl2k5_cpu_qb_reads as reads
    from . import nfl2k5_cpu_passer_iq as passer
    return reads.normalized_sites(payload) + passer.normalized_sites(payload)


def encode_options():
    return struct.pack("<f", MODERN_FACTOR)


def decode_options(content):
    if content not in (encode_options(), BETA80_FACTOR):
        raise ValueError("Foreign CPU scramble threshold")
    return {}


def code_for(places):
    return patch.relocate(assembly, places, dict(factor=places["read_only"]["va"]))


def sites(places):
    return patch.hook_sites(HOOKS, assembly, places)


def previous(places):
    legacy = SimpleNamespace(CODE=assembly.CODE_BETA80, RELOCATIONS=assembly.RELOCATIONS_BETA80)
    return [(patch.relocate(legacy, places, dict(factor=places["read_only"]["va"])), sites(places))]


def _revision(payload):
    from .nfl2k5_cave_oracle import XbeImage
    module = sys.modules[__name__]
    revision = patch.installed_revision(payload, module)
    if revision:
        row = patch.allocations(payload, module)["read_only"]
        expected = BETA80_FACTOR if revision == "previous" else encode_options()
        if XbeImage(payload).read(row["va"], 4) != expected:
            raise ValueError("Mixed CPU scramble revision and threshold")
    return revision


def status(payload):
    try:
        return "applied" if _revision(payload) else "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def verify(payload):
    revision = _revision(payload)
    return dict(status="applied" if revision else "retail", settings={} if revision else None,
                experimental=True, runtime_witnessed=False, option_source="build_time",
                retail_factor=RETAIL_FACTOR, modern_factor=0.50 if revision == "previous" else MODERN_FACTOR,
                nfl_average_calibrated=False)


def apply(payload):
    from . import nfl2k5_xbe_space as space
    module = sys.modules[__name__]
    if _revision(payload) == "previous":
        places = patch.allocations(payload, module)
        old_code, _ = previous(places)[0]
        result, code = space.install_code(payload, OWNER, code_for(places), previous=old_code)
        result, factor = space._install_scaleout(result, OWNER, encode_options(), "read_only", previous=BETA80_FACTOR)
        return result, dict(**verify(result), owner=OWNER, upgraded=True, edits=code["edits"] + factor["edits"],
                            changed_bytes=space.count_differing_bytes(payload, result))
    return patch.apply(payload, module)
