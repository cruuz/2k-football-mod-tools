"""Player Contracts panel: a player with no college word no longer crashes the screen (USA retail, xemu-safe).

Report (b778-cr1, after v0.6.1): players on the released disc have a null college word (0) and the Franchise
``PLAYER CONTRACTS`` panel's COLLEGE line dereferences it: case 3 of the panel loop at 0x6E0D8 does
``mov edx,[player+0] ; mov esi,[edx]`` with no null check, so the Xbox kernel stops the game (bugcheck 0x1E,
exception 0xC0000005 at EIP 0x6E11F). The Player Card already checks (0x145D90); the Contracts panel does not.
The data fix (job b778-fr1) heals new builds and repaired rosters, but a franchise started on v0.6.1 keeps the
old null words, so the screen itself needs the guard.

What this owner adds
--------------------
One five-byte hook at 0x6E11F (the college-string load) and a 20-byte code cave. The cave keeps the retail path when
the college word is not null, and takes the panel's own missing-value fallback (0x6E14E, the ``N/A`` string) when
it is. Nothing else changes: the club, contract, position and name lines and every other panel read stay retail.
Existing saves open; no roster repair is needed first.

Allocation: a late owner (appended at the end of ``nfl2k5_xbe_space.LATE_OWNERS``), 32 bytes of code (16-aligned).
It is applied by ``mod_build`` after the other late owners; the full build regenerates the cave reservations.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_contract_college_guard"
CODE_SIZE = 32
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOK = ("contract_college", 0x0006E11F, bytes.fromhex("8b32b94000"))  # mov esi,[edx] ; mov ecx,0x40 (first 3)
RESUME = 0x0006E126          # lea eax,[esp+0xa0] (after the displaced mov ecx,0x40)
FALLBACK = 0x0006E14E        # the panel's own missing-value copy (L"N/A" at 0xE62284)
CASE_END = 0x0006E198        # end of the college case (the test hook stops here)
BUILD_CAPTION = "Player Contracts: no crash on a player without a college"
HELP_TEXT = ("Fixes the Franchise Player Contracts panel freeze on a player whose college is missing: the screen "
             "shows N/A instead of reading address zero. Existing franchises are covered without a roster repair.")
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError)


class ContractCollegeGuardError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ContractCollegeGuardError(message)


def code_for(code_va: int) -> bytes:
    """The 18-byte cave, padded with int3 to the 32-byte allocation."""
    body = bytearray()
    body += bytes.fromhex("85d2")                                   # test edx,edx
    at = code_va + len(body)
    rel = FALLBACK - (at + 6)
    require(-(1 << 31) <= rel < (1 << 31), "fallback out of rel32 range")
    body += b"\x0f\x84" + struct.pack("<i", rel)                    # jz fallback
    body += bytes.fromhex("8b32")                                   # mov esi,[edx]
    body += bytes.fromhex("b940000000")                             # mov ecx,0x40
    at = code_va + len(body)
    rel = RESUME - (at + 5)
    require(-(1 << 31) <= rel < (1 << 31), "resume out of rel32 range")
    body += b"\xe9" + struct.pack("<i", rel)                        # jmp 0x6E126
    require(len(body) == 20, "cave size")
    return bytes(body).ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    name, va, before = HOOK
    after = b"\xe9" + struct.pack("<i", code_va - va - 5)
    require(len(after) == len(before), "hook size")
    return [(name, va, before, after)]


def allocation(payload: bytes) -> dict:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "missing or foreign contract-college allocation")
    return rows[0]


def _recognize(payload: bytes):
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    state = rdata.status(payload, edits)
    if owned is None:
        require(state == "retail", "the contract-college site changed without an allocation")
        return "retail", None
    code = image.read(owned["va"], CODE_SIZE)
    require(code in (b"\xcc" * CODE_SIZE, code_for(owned["va"])), "foreign contract-college code")
    require(state == ("retail" if code == b"\xcc" * CODE_SIZE else "applied"),
            "mixed contract-college installation")
    return ("retail" if code == b"\xcc" * CODE_SIZE else "applied"), owned


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)[0]
    except _ERRORS:
        return "foreign"


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "contract_college_guard": state == "applied"}


def reservations(payload: bytes | None = None) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER] if payload is not None else []
    owned = allocation(payload) if payload is not None and any(
        r["owner"] == OWNER for r in space.layout(payload)["allocations"]) else None
    return rows + [dict(owner=OWNER, start=hex(HOOK[1]), end=hex(HOOK[1] + len(HOOK[2])), size=len(HOOK[2]),
                        basis="pinned live contract panel college line; not a cave")]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the guard and its one site. Idempotent."""
    state, owned = _recognize(payload)
    common = {"owner": OWNER, "code_bytes": 20, "owner_bytes": CODE_SIZE, "experimental": False}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if owned is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        owned = allocation(payload)
    installed, code_receipt = space.install_code(payload, OWNER, code_for(owned["va"]))
    result, site_receipt = rdata.apply(installed, sites(owned["va"]), OWNER)
    require(status(result) == "applied", "contract-college postcondition failed")
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(owned["va"]), "changed_bytes": sum(a != b for a, b in zip(before, result)),
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "RESUME", "FALLBACK", "CASE_END", "BUILD_CAPTION", "HELP_TEXT",
           "ContractCollegeGuardError", "code_for", "sites", "allocation", "status", "read_settings", "reservations",
           "apply"]
