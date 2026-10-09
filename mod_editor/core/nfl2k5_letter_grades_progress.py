"""Letter grades on the player progression screen's overall row (job F4b, beta 77). EXPERIMENTAL / UNWITNESSED.

Noah, 2026-10-08, asked for the letter grade on the progression report's overall row as well. F4 left that screen out
because every row shares one ``%d`` literal.

The screen (text callback ``0x365CE0``, one row per attribute index ``esi``, 0 to 26) prints three numbers per row with the
game's ``swprintf``: "Previously" (``0x365E84``), "Currently" (``0x365ED8``) and "+/- Change" (``0x365F19``), all with the
literal ``L"%d"`` at ``0xEB92F0``. The value of a row comes from ``0x365B20`` -> ``0x365B00``, which for index 0 tail-jumps to
``0xE6660``, the player overall getter every other screen uses; indices 1 and up read the attribute rows through a jump table.

What changes (display only, 10 bytes in place plus 16 owned code bytes):

* the two ``mov edx, 0xEB92F0`` (5 bytes each, "Previously" and "Currently") become ``call stub``;
* the stub returns edx = ``0xEB92F0`` (the retail ``%d``) for every row, except row 0 where it returns F4's ``%R`` literal
  (``fmt_grade`` in the F4 owner's read-only page). F4's ``%R`` handler and band table do the rest, so the grade is the one every other
  F4 screen shows and it follows the same scale;
* "+/- Change" keeps ``%d`` (a difference of two ratings is not a rating), the sub-attribute rows keep numbers, and every getter,
  snapshot and sort stays byte-identical.

Stub (15 bytes, padded to 16)::

    ba f0 92 eb 00      mov  edx, 0xEB92F0
    85 f6               test esi, esi          ; esi = the row's attribute index, preserved by every callee
    75 05               jnz  +5
    ba <fmt_grade>      mov  edx, F4 "%R"
    c3                  ret

Allocation: a late owner after ``nfl2k5_letter_grades`` (so no existing allocation moves) with one 16 byte RX request.
It needs the F4 owner (its literal); without it the sites stay retail and the apply refuses.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_letter_grades as lg
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = lg.PROGRESS_OWNER
EVIDENCE = "EXPERIMENTAL"
REQUESTS = lg.PROGRESS_REQUESTS
CODE_SIZE = 16
UI_LABEL = "Letter grade on the progression report's overall row"
BUILD_CAPTION = UI_LABEL

FORMAT_VA = 0x00EB92F0                      # L"%d", used only by this screen's three row prints
# (label, VA of `mov edx, 0xEB92F0`): the Previously and Currently prints. The third print (+/- Change, 0x365F19) is not a site.
SITE_VAS = (("progression_previously", 0x00365E84), ("progression_currently", 0x00365ED8))
RETAIL_SITE = bytes.fromhex("baf092eb00")

GUARDS = (
    # the row getter: index 0 tail-jumps to the player overall (0xE6660), anything else indexes the attribute table
    (0x00365B00, 9, hashlib.sha256(bytes.fromhex("85d27505e9570bd8ff")).hexdigest()),
    # the three row prints, from the "Previously" value to the end of the "+/- Change" print, sites retail
    (0x00365E73, 216, "f5c515c39b3864a843d15fa47a94c2ed3190cca99db811aeb5551917d0aa4ff3"),
    (FORMAT_VA, 6, "a9edba2fc4741e8db1282ca45156f8cd7d91ab8ab4b6598a1dabd673c17986e1"),
)


class ProgressGradeError(ValueError):
    """Unsupported executable, missing F4 owner, foreign or mixed installation."""


def _require(condition, message):
    if not condition:
        raise ProgressGradeError(message)


def code_for(fmt_grade_va: int) -> bytes:
    """The 16 owned bytes: the 15 byte stub for the given address of F4's ``%R`` literal."""

    stub = (bytes.fromhex("baf092eb00" "85f6" "7505") + b"\xba" + struct.pack("<I", fmt_grade_va) + b"\xc3")
    assert len(stub) == 15
    return stub.ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes)."""

    return [(label, va, RETAIL_SITE, b"\xe8" + struct.pack("<i", code_va - (va + 5))) for label, va in SITE_VAS]


def allocation(payload: bytes) -> dict | None:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return None
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and (rows[0]["size"], rows[0]["align"]) == (CODE_SIZE, 16),
             "foreign progression allocation")
    return rows[0]


def _check_guards(image: XbeImage, checked_sites) -> None:
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _label, address, before, _after in checked_sites:
            if va <= address and address + len(before) <= va + size:
                content[address - va:address - va + len(before)] = before
        _require(hashlib.sha256(content).hexdigest() == digest, f"foreign progression screen bytes at {va:#x}")


def _fmt_grade_va(payload: bytes) -> int:
    found = lg.allocations(payload)
    _require(bool(found) and lg.status(payload) == "applied", "the letter grades (F4) patch must be applied first")
    return lg.labels(found["code"]["va"], found["read_only"]["va"])["fmt_grade"]


def _owned_state(payload: bytes):
    """-> ("retail" | "applied", allocation | None); anything else raises."""

    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocation(payload)
    if not found:
        retail_sites = sites(0x14DA000)         # the retail bytes do not depend on the page
        _require(rdata.status(payload, retail_sites) == "retail", "progression sites changed without an allocation")
        _check_guards(image, retail_sites)
        return "retail", None
    code = image.read(found["va"], CODE_SIZE)
    edits = sites(found["va"])
    if code == b"\xcc" * CODE_SIZE:
        _require(rdata.status(payload, edits) == "retail", "progression sites changed with an empty allocation")
        _check_guards(image, edits)
        return "retail", found
    _require(code == code_for(_fmt_grade_va(payload)), "foreign progression code")
    _require(rdata.status(payload, edits) == "applied", "mixed progression sites")
    _check_guards(image, edits)
    return "applied", found


def status(payload: bytes) -> str:
    try:
        return _owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    base = allocation(payload)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in sites(base["va"] if base else 0x14DA000)]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Add the progression stub to an executable that already carries F4. Idempotent."""

    state, found = _owned_state(payload)
    common = {"owner": OWNER, "experimental": True, "owner_bytes": CODE_SIZE}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    fmt = _fmt_grade_va(payload)
    before = payload
    if not found:
        payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocation(payload)
    _require(bool(found), "reserve the progression allocation first")
    installed, code_receipt = space.install_code(payload, OWNER, code_for(fmt))
    result, site_receipt = rdata.apply(installed, sites(found["va"]), OWNER)
    _require(status(result) == "applied", "progression postcondition failed")
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(found["va"]), "fmt_grade_va": hex(fmt),
                    "changed_bytes": sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before)),
                    "sites": [{"label": label, "va": hex(va), "size": len(old)} for label, va, old, _new in sites(found["va"])],
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


__all__ = ["OWNER", "REQUESTS", "UI_LABEL", "BUILD_CAPTION", "ProgressGradeError", "code_for", "sites", "allocation",
           "status", "reservations", "apply"]
