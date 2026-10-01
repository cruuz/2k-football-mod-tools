"""DESIGN: canonical practice-squad -> economy -> retail CPU fill chain.

PROVED OFFLINE: both complete owners must validate before shared bytes can be
projected. A branch alone is never evidence of an installed dependency.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_franchise_economy_code import SYMBOLS as ECONOMY
from .nfl2k5_practice_squad_runtime import SYMBOLS as SQUAD, CAVES

ENTRY = 0x322BB0
RETAIL = bytes.fromhex("81ec14010000")


def jump(address, target, size=5):
    return b"\xe9" + struct.pack("<i", target - address - 5) + b"\x90" * (size - 5)


ECONOMY_ENTRY = jump(ENTRY, ECONOMY["economy_fill_gate"], 6)
SQUAD_ENTRY = jump(ENTRY, SQUAD["cpu_sign_guard"], 6)
# DESIGN: replace only the guard's successful displaced-prologue continuation.
_cave = next((a, code) for a, _, code in CAVES
             if a <= SQUAD["cpu_sign_guard"] < a + len(code))
CONTINUATION = _cave[0] + _cave[1].index(RETAIL, SQUAD["cpu_sign_guard"] - _cave[0])
STANDALONE = RETAIL + jump(CONTINUATION + len(RETAIL), ENTRY + len(RETAIL))
CHAIN = jump(CONTINUATION, ECONOMY["economy_fill_gate"], len(STANDALONE))
assert _cave[1][CONTINUATION - _cave[0]:CONTINUATION - _cave[0] + len(STANDALONE)] == STANDALONE


def replace(payload, edits, *, repin=False):
    image, out = XbeImage(payload), bytearray(payload)
    sections, touched = _sections(payload), set()
    for address, code in edits:
        offset = image.offset(address, len(code))
        out[offset:offset + len(code)] = code
        touched.add(_section_for_offset(sections, offset).index)
    if repin:
        for section in sections:
            if section.index in touched:
                offset = section.header_offset + 36
                out[offset:offset + 20] = section_digest(bytes(out), section)
    return bytes(out), sorted(touched)


def project(payload, owner):
    """DESIGN: return the owner's standalone inspection view, or fail closed."""
    from . import nfl2k5_franchise_economy as economy
    from . import nfl2k5_practice_squad as squad
    from . import nfl2k5_roster_arena_growth as growth
    if owner == "economy":
        payload = growth.project(payload)
    image = XbeImage(payload)
    entry = image.read(ENTRY, 6)
    tail = image.read(CONTINUATION, len(CHAIN))
    if entry == SQUAD_ENTRY:
        if tail not in (STANDALONE, CHAIN):
            raise ValueError("foreign CPU signing guard continuation")
        standalone = replace(payload, [(CONTINUATION, STANDALONE)])[0]
        if squad._standalone_status(standalone) != "applied":
            raise ValueError("incomplete practice-squad dependency")
        if tail == CHAIN:
            econ_view = replace(standalone, [(ENTRY, ECONOMY_ENTRY)])[0]
            if economy._standalone_status(econ_view) != "applied":
                raise ValueError("incomplete economy dependency")
            return econ_view if owner == "economy" else standalone
        return replace(payload, [(ENTRY, RETAIL)])[0] if owner == "economy" else payload
    if tail == CHAIN:
        raise ValueError("orphaned CPU fill chain")
    if entry == ECONOMY_ENTRY and owner == "squad":
        if economy._standalone_status(payload) != "applied":
            raise ValueError("incomplete economy dependency")
        return replace(payload, [(ENTRY, RETAIL)])[0]
    return payload


def installation_edits(payload, owner):
    from . import nfl2k5_franchise_economy as economy
    from . import nfl2k5_practice_squad as squad
    other = squad if owner == "economy" else economy
    if other.status(payload) == "applied":
        return [(ENTRY, SQUAD_ENTRY), (CONTINUATION, CHAIN)]
    return []


def revert(payload, retail, owner):
    """DESIGN: restore pinned source spans while preserving the other owner."""
    from . import nfl2k5_franchise_economy as economy
    from . import nfl2k5_practice_squad as squad
    from . import nfl2k5_roster_arena_growth as growth
    module, other = (economy, squad) if owner == "economy" else (squad, economy)
    if hashlib.sha256(retail).hexdigest() != squad.RETAIL_SHA256:
        raise ValueError("revert requires the hash-pinned retail XBE")
    state = module.status(payload)
    if state == "foreign":
        raise ValueError("foreign owner; refusing to revert")
    if state == "retail":
        return payload, {"already_reverted": True, "changed_bytes": 0}
    if owner == "squad" and growth.status(payload) != "retail":
        raise ValueError("revert arena growth before its practice-squad dependency")
    image = XbeImage(retail)
    edits = [(s.va, image.read(s.va, len(s.patched))) for s in module.sites()]
    other_state = other.status(payload)
    if other_state == "applied":
        edits.append((ENTRY, SQUAD_ENTRY if owner == "economy" else ECONOMY_ENTRY))
        if owner == "economy":
            edits.append((CONTINUATION, STANDALONE))
    result, touched = replace(payload, edits, repin=True)
    if module.status(result) != "retail" or other.status(result) != other_state:
        raise ValueError("revert post-verification failed")
    return result, {"evidence": "PROVED OFFLINE", "reverted": True,
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)),
                    "sections_repinned": touched}
