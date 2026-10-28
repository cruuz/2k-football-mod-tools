"""SOFTDRINK default game options: 7-minute quarters, 15-minute sim quarters, Chop Block on (b779 df1).

Noah (10/28): quarters should be about 6 to 7 minutes, franchise simming should always sit at 12 or 15 minutes, and
the realism switches should be on by default "for everybody".  This module changes only what a **fresh profile**
starts with; it never edits a saved value.

How retail picks defaults (USA ``default.xbe`` sha256 73105b17..., all addresses read from the binary):

* The options live in one flat 0x2E0-byte block at ``.data`` 0xE5FF80..0xE6025F (Game Options, Franchise Settings,
  difficulty, sliders, penalties, presentation, camera).  The same block is what Settings and every franchise save carry.
* ``FUN_00077D20`` (called once from the boot sequence at 0x74AA6) zeroes the block and calls ``FUN_00077C50``, the
  defaults routine.  ``FUN_00077C50`` stores the fixed values, calls ``FUN_000E3B90`` (difficulty Pro, every slider,
  the camera) and, through 0xE3330, ``FUN_000E2C70`` (penalty sliders 0.5, toggles).  ``FUN_00127A70`` (the
  restore-defaults path used when a session starts or ends, called at 0x12D4E8 and jumped to from 0x64CC1) calls the
  same ``FUN_00077C50`` and then puts back a few fields it must keep.  So one edit of ``FUN_00077C50`` covers a fresh
  profile and every reset.
* Quarter Length (Game Options, 1..15) is ``DAT_00E6000C`` and Franchise Settings > Sim. Quarter Length (3..15) is
  ``DAT_00E60010``.  Retail stores both at 0x77CAE..0x77CBC:

      mov eax, 5 ; mov [0xE6000C], eax ; mov [0xE60010], eax          (15 bytes)

  This module rewrites exactly those 15 bytes to ``push q ; pop eax ; mov [0xE6000C], eax ; add/sub al, d ;
  mov [0xE60010], eax`` (also 15 bytes), so any pair q in 1..15, s in 3..15 fits in place with no cave.
* Chop Block (Penalty Settings toggle ``DAT_00E60064``) is stored 0 by ``FUN_000E2C70`` at 0xE2CBE.  Retail never reads
  that toggle (the case-10 jump entry reuses the Clipping slider), so Off cost nothing; ``nfl2k5_penalties`` repairs the
  toggle, which then silences chop blocks on every fresh profile until a player finds the row.  With the repair
  installed the default is turned On (one immediate byte at 0xE2CC4).

What a saved profile does: the loaders (``FUN_000E2E20`` and its callers at 0x63B95, 0x844BA, 0x84D7B, 0x16D1D4,
0x16E7B1, 0x16E864, 0x28FA6E, 0x28FEBC) copy the whole 0x2E0-byte block over the live one.  A Settings or franchise save
therefore keeps whatever it stored, and these defaults are never consulted for it.  That is the rule this module
keeps: nothing here is hooked on a load path.

The Sim. Quarter Length default is only raised when the simulator pace fix (``nfl2k5_sim_stats``) is also in the build.
Without it a 15-minute sim quarter inflates simulated games to about 1.7x the plays, points and yards (b778 sim1), so
the sim default stays at the retail 5.

Retail executable only; any other bytes at the two sites make ``status`` report ``foreign`` and ``apply`` refuse.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _section_for_offset, _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_option_defaults"
BUILD_CAPTION = "SOFTDRINK default options (7:00 quarters, 15:00 sim quarters)"
HELP_TEXT = ("A fresh profile (and Reset to defaults) starts with 7 minute quarters, 15 minute Sim. Quarter Length "
             "(when the franchise pace fix is on) and the Chop Block penalty on. Saved settings and saved franchises "
             "keep what they stored; nothing here overwrites a value a player chose.")
REQUESTS = ()                     # in place: no executable cave, data or file growth

DEFAULT_QUARTER_MINUTES = 7       # Game Options > Quarter Length (retail 5)
DEFAULT_SIM_MINUTES = 15          # Franchise Settings > Sim. Quarter Length (retail 5)
QUARTER_RANGE = (1, 15)           # row callbacks 0x149190 / 0x149180
SIM_RANGE = (3, 15)               # row callbacks 0x2C6F80 / 0x2C6F70
RETAIL_MINUTES = 5

# Site A: FUN_00077C50, `mov eax,5 ; mov [0xE6000C],eax ; mov [0xE60010],eax`.
SITE_A = 0x00077CAE
SITE_A_SIZE = 15
REGION_A = 0x00077CA2             # recognition window: the two calls before, the e5ffa4 store and the xor after
REGION_A_SIZE = 0x28
RETAIL_REGION_A = bytes.fromhex(
    "e859b3060033c9e832b40600b805000000a30c00e600a31000e600c705a4ffe5000000824233c05f")
RETAIL_SITE_A = bytes.fromhex("b805000000a30c00e600a31000e600")
assert len(RETAIL_REGION_A) == REGION_A_SIZE and len(RETAIL_SITE_A) == SITE_A_SIZE
assert RETAIL_REGION_A[SITE_A - REGION_A:SITE_A - REGION_A + SITE_A_SIZE] == RETAIL_SITE_A

# Site B: FUN_000E2C70, `mov dword [0xE60064], 0` (Chop Block toggle default).
SITE_B = 0x000E2CBE
SITE_B_SIZE = 10
CHOP_IMMEDIATE = 0x000E2CC4       # the imm32 of that store
REGION_B = 0x000E2CB2
REGION_B_SIZE = 0x1A
RETAIL_REGION_B = bytes.fromhex("890d6000e600890d8000e600c7056400e60000000000890d6800")
RETAIL_SITE_B = bytes.fromhex("c7056400e60000000000")
assert len(RETAIL_REGION_B) == REGION_B_SIZE and len(RETAIL_SITE_B) == SITE_B_SIZE
assert RETAIL_REGION_B[SITE_B - REGION_B:SITE_B - REGION_B + SITE_B_SIZE] == RETAIL_SITE_B


class OptionDefaultsError(ValueError):
    """A site is foreign, a value is out of range, or the patched executable does not read back."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OptionDefaultsError(message)


def _check_minutes(quarter: int, sim: int) -> None:
    _require(type(quarter) is int and QUARTER_RANGE[0] <= quarter <= QUARTER_RANGE[1],
             f"Quarter Length must be a whole number from {QUARTER_RANGE[0]} to {QUARTER_RANGE[1]}")
    _require(type(sim) is int and SIM_RANGE[0] <= sim <= SIM_RANGE[1],
             f"Sim. Quarter Length must be a whole number from {SIM_RANGE[0]} to {SIM_RANGE[1]}")


def site_a(quarter: int, sim: int) -> bytes:
    """15 in-place bytes: eax = quarter, store it, nudge al to sim, store it (eax stays below 256)."""
    _check_minutes(quarter, sim)
    delta = sim - quarter
    step = b"\x90\x90" if delta == 0 else (b"\x04" + bytes([delta]) if delta > 0 else b"\x2c" + bytes([-delta]))
    body = (b"\x6a" + bytes([quarter]) + b"\x58"                  # push q ; pop eax
            + b"\xa3" + struct.pack("<I", 0x00E6000C)             # mov [Quarter Length], eax
            + step                                                # add/sub al, |sim - q|
            + b"\xa3" + struct.pack("<I", 0x00E60010))            # mov [Sim. Quarter Length], eax
    assert len(body) == SITE_A_SIZE
    return body


def site_b(chop_block: bool) -> bytes:
    body = b"\xc7\x05" + struct.pack("<I", 0x00E60064) + struct.pack("<I", 1 if chop_block else 0)
    assert len(body) == SITE_B_SIZE
    return body


def _read(payload: bytes, va: int, size: int) -> bytes:
    return XbeImage(payload).read(va, size)


def _decode_a(site: bytes):
    """(quarter, sim) for any site this module writes (or the retail pair), else None."""
    if site == RETAIL_SITE_A:
        return RETAIL_MINUTES, RETAIL_MINUTES
    if site[0] == 0x6A and site[2] == 0x58:
        quarter = site[1]
        for sim in range(SIM_RANGE[0], SIM_RANGE[1] + 1):
            if QUARTER_RANGE[0] <= quarter <= QUARTER_RANGE[1] and site == site_a(quarter, sim):
                return quarter, sim
    return None


def settings(payload: bytes) -> dict:
    """What the executable installs: {"state", "quarter_minutes", "sim_minutes", "chop_block"}; foreign refuses to decode."""
    try:
        region_a = _read(payload, REGION_A, REGION_A_SIZE)
        region_b = _read(payload, REGION_B, REGION_B_SIZE)
    except (ValueError, struct.error, IndexError, OSError):
        return {"state": "foreign"}
    head_a = region_a[:SITE_A - REGION_A]
    tail_a = region_a[SITE_A - REGION_A + SITE_A_SIZE:]
    head_b = region_b[:SITE_B - REGION_B]
    tail_b = region_b[SITE_B - REGION_B + SITE_B_SIZE:]
    ref_a, ref_b = RETAIL_REGION_A, RETAIL_REGION_B
    if (head_a != ref_a[:SITE_A - REGION_A] or tail_a != ref_a[SITE_A - REGION_A + SITE_A_SIZE:]
            or head_b != ref_b[:SITE_B - REGION_B] or tail_b != ref_b[SITE_B - REGION_B + SITE_B_SIZE:]):
        return {"state": "foreign"}
    decoded = _decode_a(region_a[SITE_A - REGION_A:SITE_A - REGION_A + SITE_A_SIZE])
    site_b_bytes = region_b[SITE_B - REGION_B:SITE_B - REGION_B + SITE_B_SIZE]
    if decoded is None or site_b_bytes not in (site_b(False), site_b(True)):
        return {"state": "foreign"}
    chop = site_b_bytes == site_b(True)
    retail = (region_a[SITE_A - REGION_A:SITE_A - REGION_A + SITE_A_SIZE] == RETAIL_SITE_A
              and site_b_bytes == RETAIL_SITE_B)
    return {"state": "retail" if retail else "applied", "quarter_minutes": decoded[0],
            "sim_minutes": decoded[1], "chop_block": chop}


def status(payload: bytes) -> str:
    return settings(payload)["state"]


def _repin(payload: bytes, offset: int) -> bytes:
    section = _section_for_offset(_sections(payload), offset)
    out = bytearray(payload)
    digest_at = section.header_offset + 36
    out[digest_at:digest_at + 20] = section_digest(bytes(out), section)
    return bytes(out)


def apply(payload: bytes, *, quarter_minutes: int = DEFAULT_QUARTER_MINUTES,
          sim_minutes: int = DEFAULT_SIM_MINUTES, chop_block: bool = True) -> tuple[bytes, dict]:
    """Write the defaults in place (retail or an earlier application of this owner; anything else refuses)."""
    _check_minutes(quarter_minutes, sim_minutes)
    _require(type(chop_block) is bool, "chop_block must be true or false")
    current = settings(payload)
    _require(current["state"] != "foreign",
             "foreign default-options routine around 0x77CAE / 0xE2CBE; rebuild from a supported USA retail source")
    wanted = {"quarter_minutes": quarter_minutes, "sim_minutes": sim_minutes, "chop_block": chop_block}
    if current["state"] == "applied" and all(current.get(k) == v for k, v in wanted.items()):
        return payload, {"already_applied": True, "changed_bytes": 0, **wanted}
    image = XbeImage(payload)
    out = bytearray(payload)
    off_a = image.offset(SITE_A, SITE_A_SIZE)
    off_b = image.offset(SITE_B, SITE_B_SIZE)
    out[off_a:off_a + SITE_A_SIZE] = site_a(quarter_minutes, sim_minutes)
    out[off_b:off_b + SITE_B_SIZE] = site_b(chop_block)
    result = _repin(_repin(bytes(out), off_a), off_b)
    check = settings(result)
    _require(check.get("state") == "applied" and all(check.get(k) == v for k, v in wanted.items()),
             "default options read-back failed")
    return result, {
        **wanted,
        "site_a_va": hex(SITE_A), "site_b_va": hex(SITE_B),
        "edits": [{"label": "quarter_and_sim_quarter_length", "va": hex(SITE_A), "bytes": SITE_A_SIZE},
                  {"label": "chop_block_default", "va": hex(SITE_B), "bytes": SITE_B_SIZE}],
        "code_bytes": 0, "writable_bytes": 0, "readonly_bytes": 0,
        "changed_bytes": sum(a != b for a, b in zip(payload, result)),
        "region_sha256": hashlib.sha256(_read(result, REGION_A, REGION_A_SIZE)
                                        + _read(result, REGION_B, REGION_B_SIZE)).hexdigest(),
    }


__all__ = ["BUILD_CAPTION", "DEFAULT_QUARTER_MINUTES", "DEFAULT_SIM_MINUTES", "HELP_TEXT", "OWNER",
           "OptionDefaultsError", "QUARTER_RANGE", "REQUESTS", "SIM_RANGE", "apply", "settings", "site_a",
           "site_b", "status"]
