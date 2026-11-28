"""CPU place-kick aim repair for games a person plays (executable patch, in place, xemu-only).

Root cause (retail ``default.xbe``; the bytes are identical in released v0.9 and the beta 81 standard edition).
The place-kick aim routine ``0x2EF2D0`` (one caller, ``0x2F14BF``) works out a wind-adjusted heading and keeps it
at ``[esp+0x20]``.  When the kicking controller is unassigned (``cmp eax,-1`` at ``0x2EF4ED``; a person's port jumps
to ``0x2EF62A`` and never runs the bytes below) the CPU branch asks ``0x2EB6F0`` for an error bound from the
kicker's ratings and the curve at ``0x50B544``, draws a whole number between minus and plus that bound from the
match generator ``0xE5FCA0`` (``0x2EF5E7..0x2EF5F3``), multiplies it by 1.5 when ``[[ebp+8]+0x38]+0x30`` is set
(``0x2EF5F5..0x2EF60E``) and adds it to the heading (``0x2EF614``).  That error was sized for 2004 kicks.  With the
modern extra point from the 15 (a 32-yard kick) and the longer field-goal power curve of the kicking fixes, a CPU
kicker misses wide far too often: on 704 authentic native kick states Joshua Karty made 46/64 extra points and 44/64
field goals from 35 yards (NFL 2021-25: 95.1% and about 90%).  Scaling only the error to two thirds gave 60/64 and
57/64 with no make turned into a miss (beta 81 evidence ``e16-kickers/played-aim-nov19``).

The patch rewrites the 27 bytes ``0x2EF5F5..0x2EF60F`` in place with the same length: the drawn error is multiplied
by ``AIM_SCALE / 128`` (85/128, about two thirds) and the original 1.5x case keeps its ratio to the ordinary case.
The draw, the heading add and every byte a person's kick executes are unchanged.  The Studio applies it with the
kicking fixes (``kick_rules`` or ``kick_power``), whose longer kicks are what expose the error.
"""
from __future__ import annotations

from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_cpu_kick_aim"
SITE_VA = 0x002EF5F5
SITE_SIZE = 27
RESUME_VA = SITE_VA + SITE_SIZE           # 0x2EF610: mov ecx,[esp+0x20]; add ecx,edx (the heading), unchanged
RETAIL_SITE = bytes.fromhex("8b45088b403885c074118b483085c9740a8d0452992bc2d1f88bd0")
AIM_SCALE = 85                            # the CPU error is multiplied by AIM_SCALE / 128
# Guard bytes that must stay retail: the CPU/human branch, the error draw and the heading add.
GUARDS = ((0x002EF4ED, bytes.fromhex("83f8ff")), (0x002EF4F4, bytes.fromhex("0f8530010000")),
          (0x002EF5E7, bytes.fromhex("e86495d5ff")), (0x002EF5F3, bytes.fromhex("03d7")),
          (0x002EF610, bytes.fromhex("8b4c242003ca")))
BUILD_CAPTION = "CPU kicker aim (with the kicking fixes)"


class CpuKickAimError(ValueError):
    """The executable's CPU kick aim bytes are not the retail or the repaired bytes."""


def _require(condition, message):
    if not condition:
        raise CpuKickAimError(message)


def site_bytes(scale: int = AIM_SCALE) -> bytes:
    """The repaired 27 bytes (source: ``tools/scoring/cpu_kick_aim.S``)."""
    _require(type(scale) is int and 1 <= scale <= 127, "the CPU aim scale is a whole number from 1 to 127 (/128)")
    code = (bytes.fromhex("6bd2") + bytes([scale])     # imul edx, edx, scale
            + bytes.fromhex("8b4508")                  # mov eax, [ebp+8]
            + bytes.fromhex("8b4038")                  # mov eax, [eax+0x38]
            + bytes.fromhex("85c0740b")                # test eax, eax ; je .scale
            + bytes.fromhex("8378300074 05".replace(" ", ""))  # cmp dword [eax+0x30], 0 ; je .scale
            + bytes.fromhex("8d1452")                  # lea edx, [edx+edx*2]   (the original 1.5x case)
            + bytes.fromhex("d1fa")                    # sar edx, 1
            + bytes.fromhex("c1fa07"))                 # .scale: sar edx, 7
    assert len(code) == SITE_SIZE
    return code


def _offset(payload: bytes, va: int, size: int) -> int:
    return XbeImage(payload).offset(va, size)


def status(payload: bytes) -> str:
    """``retail``, ``applied`` (the shipped scale) or ``foreign``."""
    try:
        image = XbeImage(payload)
        if any(image.read(va, len(raw)) != raw for va, raw in GUARDS):
            return "foreign"
        site = image.read(SITE_VA, SITE_SIZE)
    except Exception:  # noqa: BLE001 - an unreadable image is foreign
        return "foreign"
    if site == RETAIL_SITE:
        return "retail"
    if site == site_bytes():
        return "applied"
    return "foreign"


def read_settings(payload: bytes) -> Mapping[str, object]:
    state = status(payload)
    return {"status": state, "scale": f"{AIM_SCALE}/128" if state == "applied" else None}


def _write(payload: bytes, data: bytes) -> bytes:
    buf = bytearray(payload)
    off = _offset(payload, SITE_VA, SITE_SIZE)
    buf[off:off + SITE_SIZE] = data
    sections = _sections(payload)
    section = _section_for_offset(sections, off)
    digest_at = section.header_offset + 36
    buf[digest_at:digest_at + 20] = section_digest(bytes(buf), section)
    return bytes(buf)


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the repair on a retail site; an installed repair is left as it is."""
    state = status(payload)
    if state == "applied":
        return bytes(payload), {"owner": OWNER, "already_applied": True, "changed_bytes": 0}
    _require(state == "retail", f"CPU kick aim bytes are {state}; refusing to patch")
    patched = _write(payload, site_bytes())
    _require(status(patched) == "applied", "CPU kick aim post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"owner": OWNER, "site": f"0x{SITE_VA:X}", "bytes": SITE_SIZE, "scale": f"{AIM_SCALE}/128",
                     "changed_bytes": changed}


def restore(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Put the retail bytes back (and the section digest); a retail site is left as it is."""
    state = status(payload)
    if state == "retail":
        return bytes(payload), {"owner": OWNER, "already_retail": True, "changed_bytes": 0}
    _require(state == "applied", f"CPU kick aim bytes are {state}; refusing to restore")
    restored = _write(payload, RETAIL_SITE)
    _require(status(restored) == "retail", "CPU kick aim restore verification failed")
    return restored, {"owner": OWNER, "restored": True,
                      "changed_bytes": sum(1 for a, b in zip(payload, restored) if a != b)}


__all__ = ["AIM_SCALE", "BUILD_CAPTION", "CpuKickAimError", "OWNER", "RETAIL_SITE", "SITE_SIZE", "SITE_VA",
           "apply", "read_settings", "restore", "site_bytes", "status"]
