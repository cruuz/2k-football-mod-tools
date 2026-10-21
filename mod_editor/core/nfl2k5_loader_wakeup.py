"""Loader wake-up fix: the disc loader thread can no longer sleep through a posted read.

Why (job b777-st1, 2026-10-20)
------------------------------
Rarely a game load sits forever on the ESPN NFL Countdown LOADING card (or another LOADING
screen) while the card loop keeps drawing. The cause is in the retail engine, not in a mod:

* All disc reads go through one worker thread (start routine ``0x4D810``, created suspended by
  ``0x4D900``, handle at ``0xA7A238``). Its state word ``0xA7D300`` is 1 when idle, 2..12 for a
  posted operation (``2`` = read through ``0x4D630``) and 13 to exit.
* After an operation the worker writes state 1, completes the request (``0x3A4F0``) and only
  then suspends itself with ``NtSuspendThread`` (``0x4B910``).
* The posters (``0x4BB50`` and its siblings) refuse unless the state is 1, write the request,
  set state 2 and call ``NtResumeThread`` (``0x4B930``).
* ``NtResumeThread`` on a thread that is not suspended yet does nothing. If the game's main
  thread posts the next read in the gap between "state = 1" and the suspend, the worker then
  suspends with state 2 pending and nothing ever wakes it. The read never runs, the stream that
  wanted it stays busy (``0xB09584``), and the loading loop (``0xF4EF0``) waits forever.

The gap is a few hundred instructions, so the stall is rare and timing dependent: more loads
(more reads) and a busy emulator host make it more likely. Inserting a yield into that gap
(guest RAM, gdb) makes the retail disc and SOFTDRINK discs stall on the first load.

The patch
---------
The worker routine is re-encoded in place (``0x4D810..0x4D900``: the routine, its jump table
and padding; nothing else refers into it except the thread creation at ``0x4D90A``). The state
machine is the same, with the same operation functions, completion call and exit path, but the
idle state waits ``KeDelayExecutionThread(KernelMode, FALSE, -1 ms)`` and reads the state again
instead of suspending. A posted request is therefore picked up within 1 ms whether or not the
resume arrived in time; the posters' ``NtResumeThread`` calls stay and become harmless no-ops.
The same call and interval are already used by the retail XPP code (``0x4E238F``).

Cost: the idle worker wakes once per millisecond (a compare and a wait), and each read can start
up to 1 ms later than before. Reads are completed by the main thread's once-per-frame pump, so
loads are paced by frames (16 to 33 ms), not by this delay.

No cave, no new memory, no file growth.

Runtime evidence (job b777-st1, xemu 0.8.136 through the gdb stub, guest RAM only): with a yield
inserted before the retail suspend, the retail disc and the b777 disc stall on the first Quick Game
load (worker state 2 frozen); resuming the worker at that point lets the same load finish. With this
routine written at 0x4D810 before the thread starts, every load reached the first play, also with
the same yield added in the old window.
"""
from __future__ import annotations

import hashlib

from . import nfl2k5_rdata_sites as rdata
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

OWNER = "nfl2k5_loader_wakeup"
BUILD_CAPTION = "Disc loader never sleeps through a read"
HELP_TEXT = ("Fixes a rare endless LOADING screen (retail engine bug): the disc loader thread could suspend "
             "itself just after a new read was posted and never wake. The loader now waits 1 ms and checks "
             "again instead. Enabled in all SOFTDRINK presets.")

START, SIZE = 0x4D810, 0xF0
RETAIL_SHA256 = "2622eed920cb9ddf0ee6d1dc0b5c9bde9d7b6695494cc22f44b72b4a3bb39fd9"

# Assembled from the routine described above (GNU as, linked at 0x4D810; see tests for the decode).
CODE = bytes.fromhex(
    "56be01000000a100d3a70083f80d743f83f8017429721fff14856cd804008b1568d3a700b970d3a700893500d3a700"
    "e8acccfeffebd0893500d3a700ebc868a0d804006a006a00ff15e43b4e00ebb7c70500d3a70000000000e8b2e0ffff"
    "5ec20400669030d6040020d7040030cf040010d20400e0cf0400e0d2040050d30400c0d3040030d4040080d40400"
    "c0d40400f0d8ffffffffffff")
PATCHED = CODE.ljust(SIZE, b"\x90")

# Retail code this routine calls or is called by, pinned unchanged (sha256 of the span).
PINS = (
    (0x4D900, 0x20, "7da46498200a31a2da2459e8ad8bc404c9d0cd07aad142ec05f58269884ab917"),  # CreateThread(0x4D810)
    (0x3A4F0, 0x30, "ad2083365a17501c2642276addcb81d1e4cf068cd07923d9ca583cdcc8f57518"),  # request completion
    (0x4B920, 0x08, "5287c881eecf216468f4a13476d4ade2a0a47b282a2badc056123aacea816dbb"),  # thread exit
    (0x4BB50, 0x90, "59aaac8abec07497c8f80868fb894bac7005b89223a6744b6ee318443c1a9521"),  # read poster
    (0x4B930, 0x10, "5709d2e1d0a137a143d84a654e66d8144718f8ceef4cfbd53699102369a3e917"),  # NtResumeThread wrapper
    (0x4E3BE4, 0x04, "1b231a8157ca52114624bc0f20826e18d6184e78504c4b56ca58833beb7c02cd"),  # thunk: ordinal 99
)


class LoaderWakeupError(rdata.RdataSiteError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _span(payload: bytes, va: int, size: int) -> bytes:
    off = rdata.offset_of(payload, va)
    data = payload[off:off + size]
    if len(data) != size:
        raise LoaderWakeupError(f"span 0x{va:x} is truncated")
    return data


def status(payload: bytes) -> str:
    """retail | applied | foreign."""
    try:
        for va, size, digest in PINS:
            if _sha(_span(payload, va, size)) != digest:
                return "foreign"
        span = _span(payload, START, SIZE)
    except (rdata.RdataSiteError, ValueError, TypeError):
        return "foreign"
    if span == PATCHED:
        return "applied"
    if _sha(span) == RETAIL_SHA256:
        return "retail"
    return "foreign"


def verify(payload: bytes) -> dict:
    state = status(payload)
    if state != "applied":
        raise LoaderWakeupError(f"Loader wake-up fix is {state}, not applied")
    return dict(status=state, start=hex(START), size=SIZE, idle="KeDelayExecutionThread -1 ms",
                runtime_witnessed=True, file_growth=0)


def apply(payload: bytes):
    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "edits": [], "changed_bytes": 0, **verify(payload), "owner": OWNER}
    if state != "retail":
        raise LoaderWakeupError("Loader worker routine is foreign; refusing to patch")
    buf = bytearray(payload)
    off = rdata.offset_of(payload, START)
    buf[off:off + SIZE] = PATCHED
    sections = _sections(payload)
    section = _section_for_offset(sections, off)
    d = section.header_offset + 36
    buf[d:d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    receipt = {"edits": [{"label": "loader worker", "va": hex(START), "file_offset": hex(off), "bytes": SIZE}],
               "changed_bytes": sum(1 for a, b in zip(payload, patched) if a != b),
               "sections_repinned": [section.index], **verify(patched), "owner": OWNER,
               "reservations": [dict(owner=OWNER, start=hex(START), end=hex(START + SIZE), size=SIZE,
                                     basis="pinned live function extent (routine, jump table, padding); not a cave")]}
    return patched, receipt


__all__ = ["BUILD_CAPTION", "HELP_TEXT", "OWNER", "LoaderWakeupError", "apply", "status", "verify"]
