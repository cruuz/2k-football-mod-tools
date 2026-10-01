"""xemu display-list stability fix: the frame list's release callback runs from the D3D ring.

Why (job b76-z2, 2026-09-22)
----------------------------
xemu 0.8.136 aborts in the pregame intro with ``pfifo.c:426 Reserved pb command`` (or
``pfifo.c:299 Dma value is out of range``), on the retail disc as well as on SOFTDRINK builds.
An instrumented xemu captured the bad word: the last word of the frame's display list, the JMP
back into the D3D ring (published as ``0x010f6695``), had been overwritten by the first float of
the next frame's list (``0x3ed9d9db``) before xemu's DMA pusher fetched it.

How the retail engine submits a frame (all Xbox virtual addresses)
------------------------------------------------------------------
``0x28DE0`` (frame submit) waits for the other list set (``0x33660`` spins on ``[set+8]``),
closes the current set's chain with ``0x334E0`` and links it into the ring with ``0x34130``:

* ``0x334E0`` appends ``[0x81d8c][0x33410][set]`` (the callback and its context in the two
  clear-value registers), ``[0x40110][0]`` (WAIT_FOR_IDLE) and ``[0x40100][7]`` (a NOP with a
  parameter: a PGRAPH software method).
* ``0x34130`` reserves eight ring dwords (``0x33D10``), writes ``[JMP list]`` into the ring,
  ``[JMP ring+4]`` into the list's end slot, then ``[0x41d8c][0xe60690]`` (the retail clear value
  back) and kicks the ring (``0x33D30``).
* D3D's software-method handler (``0x42D900``, case 7) calls ``0x33410``, which clears
  ``[set+8]``; the game records the next frame into that set's buffer at once.

On the NV2A the DMA pusher runs ahead of the puller into CACHE1 and executes JMPs itself, so
the list's return JMP has been fetched long before the software-method interrupt is serviced.
xemu's pusher and puller share one thread: the pusher stops at the NOP and reads the return JMP
only after the guest acknowledged the interrupt and the FIFO thread ran again (2.5 ms later in
the captured run). If the game has re-recorded the buffer by then, the pusher executes list data
as commands.

The patch
---------
It moves the software-method NOP from the end of the list into the ring, right after the list's
return point::

    retail   list: ... [cb ctx][WAIT_FOR_IDLE][NOP 7][JMP ring+4]   ring: [JMP list][clear value]
    patched  list: ... [cb ctx][WAIT_FOR_IDLE][JMP ring+4]          ring: [JMP list][NOP 7][clear value]

The GPU receives the same methods in the same order (a JMP is not a method), so a console
behaves as before. The pusher now waits for the callback inside the ring, which D3D only
reuses after its fences pass, instead of inside a list buffer the callback hands back to the
game. Two pinned .text spans: the two NOP stores in ``0x334E0`` are jumped over, and
``0x34130`` is re-encoded in its own 80 bytes (72 bytes of code plus 8 bytes of padding, one
caller, no cave). The ring reservation stays eight dwords; the runner now uses five.
The capture and the probe runs are in the job report ``B76_Z2_REPORT.md``.
"""

from __future__ import annotations

import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata

# --- the engine, pinned for the report and the tests (never written) ----------------------------
FRAME_SUBMIT_VA = 0x00028DE0         # the only caller of both spans below
LIST_WAIT_VA = 0x00033660            # spins while [set+8] != 0
CHAIN_END_VA = 0x000334E0            # appends the callback registers, WAIT_FOR_IDLE and NOP 7
CALLBACK_VA = 0x00033410             # mov eax,[esp+4]; mov dword [eax+8], 0; ret
RING_RESERVE_VA = 0x00033D10         # D3D push reservation of 8 dwords
RING_COMMIT_VA = 0x00033D30          # D3D push commit + kick
SOFTWARE_METHOD_DISPATCH_VA = 0x0042D900
RING_RESERVED_DWORDS = 8
CALLBACK_METHOD = 0x00081D8C         # SET_ZSTENCIL_CLEAR_VALUE, count 2 (+ SET_COLOR_CLEAR_VALUE)
WAIT_FOR_IDLE = 0x00040110
NOP_HEADER = 0x00040100
LIST_RELEASE_METHOD = 7              # the NOP parameter D3D dispatches to the callback
CLEAR_VALUE_HEADER = 0x00041D8C
RETAIL_CLEAR_VALUE = 0x00E60690

# --- span 1: the two NOP stores at the end of the chain end ----------------------------------
CHAIN_SITE_VA = 0x0003352A
RETAIL_CHAIN = bytes.fromhex(
    "c70000010400"                   # mov dword ptr [eax], 0x40100
    "83c004"                         # add eax, 4
    "c70007000000"                   # mov dword ptr [eax], 7
    "83c004")                        # add eax, 4
PATCHED_CHAIN = bytes.fromhex("eb10") + b"\x90" * 16   # jmp 0x3353c (the write-pointer store)
assert len(RETAIL_CHAIN) == len(PATCHED_CHAIN) == 18
assert CHAIN_SITE_VA + 2 + PATCHED_CHAIN[1] == CHAIN_SITE_VA + len(RETAIL_CHAIN)

# --- span 2: the runner, re-encoded in its own 80 bytes --------------------------------------
RUNNER_VA = 0x00034130
RUNNER_SIZE = 0x50
RETAIL_RUNNER = bytes.fromhex(
    "56" "57" "6a01" "8bfa" "8bf1"   # push esi; push edi; push 1; mov edi,edx; mov esi,ecx
    "e8d3fbffff"                     # call 0x33d10 (reserve 8 dwords)
    "81e6feffff03" "83c004" "83ce01" "8970fc"   # ring[0] = JMP list
    "8bc8" "81e1feffff03" "83c901" "890f"       # end slot = JMP ring+4
    "c7008c1d0400" "83c004" "c7009006e600"      # ring[1..2] = clear value back
    "6a01" "83c004" "e8befbffff"     # push 1; add eax,4; call 0x33d30 (commit)
    "8d4704" "5f" "5e" "c3"          # lea eax,[edi+4]; pop edi; pop esi; ret
    "9090909090909090")              # padding up to 0x34180
assert len(RETAIL_RUNNER) == RUNNER_SIZE


def _rel32(source_end: int, target: int) -> str:
    return struct.pack("<i", target - source_end).hex()


def runner_code(runner_va: int = RUNNER_VA) -> bytes:
    """The runner with the list-release NOP written into the ring after the return point.

        push esi ; push edi ; push 1 ; mov edi,edx ; mov esi,ecx
        call 0x33d10                       ; eax = ring, 8 dwords reserved
        and esi,0x3fffffe ; inc esi        ; JMP form of the list address (bit 0 was cleared)
        mov [eax],esi                      ; ring[0] = JMP list
        lea ecx,[eax+4] ; and ecx,0x3fffffe ; inc ecx
        mov [edi],ecx                      ; list end slot = JMP ring+4
        mov [eax+4],0x40100 ; mov [eax+8],7          ; ring[1..2] = NOP 7 (the release callback)
        mov [eax+12],0x41d8c ; mov [eax+16],0xe60690 ; ring[3..4] = the retail clear value back
        add eax,20 ; push 1 ; call 0x33d30 ; lea eax,[edi+4] ; pop edi ; pop esi ; ret
    """

    parts = ["56", "57", "6a01", "8bfa", "8bf1"]
    code = bytes.fromhex("".join(parts))
    code += bytes.fromhex("e8" + _rel32(runner_va + len(code) + 5, RING_RESERVE_VA))
    code += bytes.fromhex(
        "81e6feffff03" "46" "8930"
        "8d4804" "81e1feffff03" "41" "890f"
        "c74004" + struct.pack("<I", NOP_HEADER).hex()
        + "c74008" + struct.pack("<I", LIST_RELEASE_METHOD).hex()
        + "c7400c" + struct.pack("<I", CLEAR_VALUE_HEADER).hex()
        + "c74010" + struct.pack("<I", RETAIL_CLEAR_VALUE).hex()
        + "83c014" "6a01")
    code += bytes.fromhex("e8" + _rel32(runner_va + len(code) + 5, RING_COMMIT_VA))
    code += bytes.fromhex("8d4704" "5f" "5e" "c3")
    if len(code) > RUNNER_SIZE:
        raise DisplayListStabilityError(f"runner is {len(code)} bytes, over {RUNNER_SIZE}")
    return code + b"\x90" * (RUNNER_SIZE - len(code))


class DisplayListStabilityError(ValueError):
    """The executable does not carry the retail chain end or the retail runner."""


PATCHED_RUNNER = runner_code()
RUNNER_CODE_BYTES = len(PATCHED_RUNNER.rstrip(b"\x90"))
RING_DWORDS_WRITTEN = 5

# The retail runner's calls really target the reservation and the commit, and the re-encoding
# keeps both targets, the prologue and the epilogue.
assert 0x34138 + 5 + struct.unpack_from("<i", RETAIL_RUNNER, 9)[0] == RING_RESERVE_VA
assert 0x3416D + 5 + struct.unpack_from("<i", RETAIL_RUNNER, 0x3E)[0] == RING_COMMIT_VA
assert PATCHED_RUNNER[:13] == RETAIL_RUNNER[:13]
assert RING_DWORDS_WRITTEN <= RING_RESERVED_DWORDS

UI_LABEL = "xemu display-list stability fix"
HELP_TEXT = ("Stops the pregame-intro crash in xemu (\"Reserved pb command\", the emulator window "
             "closes), which the retail game has too. The game frees each frame's command list with "
             "a GPU interrupt at the end of the list and starts writing the next frame into it at "
             "once; a real Xbox has already read the list's last word by then, but xemu reads it "
             "after the interrupt and can find the next frame there. The patch raises that "
             "interrupt from the D3D ring, one step later, where nothing is rewritten early. The "
             "GPU runs the same commands in the same order, so it changes nothing on a console. "
             "Root-caused with an instrumented xemu; not witnessed on a console.")
BUILD_CAPTION = UI_LABEL


def sites() -> list[tuple[str, int, bytes, bytes]]:
    return [("chain_end_release_nop", CHAIN_SITE_VA, RETAIL_CHAIN, PATCHED_CHAIN),
            ("list_runner", RUNNER_VA, RETAIL_RUNNER, PATCHED_RUNNER)]


def revert_sites() -> list[tuple[str, int, bytes, bytes]]:
    """The exact inverse: patched bytes back to retail, same two spans."""

    return [(label, va, after, before) for label, va, before, after in sites()]


def status(payload: bytes) -> str:
    return rdata.status(payload, sites())


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    try:
        patched, receipt = rdata.apply(payload, sites(), "display-list stability")
    except rdata.RdataSiteError as exc:
        raise DisplayListStabilityError(str(exc)) from exc
    return patched, {**receipt, "label": UI_LABEL, "witnessed_on_console": False,
                     "frame_submit": f"0x{FRAME_SUBMIT_VA:x}", "chain_end": f"0x{CHAIN_END_VA:x}",
                     "runner": f"0x{RUNNER_VA:x}", "release_callback": f"0x{CALLBACK_VA:x}",
                     "ring_dwords": f"{RING_DWORDS_WRITTEN} of {RING_RESERVED_DWORDS} reserved",
                     "methods_changed": "none: same methods, same order; the NOP 7 follows the return JMP"}


def revert(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Put the retail chain end and the retail runner back byte for byte."""

    if status(payload) == "retail":
        return bytes(payload), {"already_applied": True, "edits": [], "changed_bytes": 0}
    try:
        reverted, receipt = rdata.apply(payload, revert_sites(), "display-list stability revert")
    except rdata.RdataSiteError as exc:
        raise DisplayListStabilityError(str(exc)) from exc
    if status(reverted) != "retail":
        raise DisplayListStabilityError("display-list stability revert did not restore retail")
    return reverted, {**receipt, "reverted": True}


__all__ = ["BUILD_CAPTION", "CALLBACK_METHOD", "CALLBACK_VA", "CHAIN_END_VA", "CHAIN_SITE_VA",
           "CLEAR_VALUE_HEADER", "DisplayListStabilityError", "FRAME_SUBMIT_VA", "HELP_TEXT",
           "LIST_RELEASE_METHOD", "LIST_WAIT_VA", "NOP_HEADER", "PATCHED_CHAIN", "PATCHED_RUNNER",
           "RETAIL_CHAIN", "RETAIL_CLEAR_VALUE", "RETAIL_RUNNER", "RING_COMMIT_VA",
           "RING_DWORDS_WRITTEN", "RING_RESERVED_DWORDS", "RING_RESERVE_VA", "RUNNER_CODE_BYTES",
           "RUNNER_SIZE", "RUNNER_VA", "SOFTWARE_METHOD_DISPATCH_VA", "UI_LABEL", "WAIT_FOR_IDLE",
           "apply", "revert", "revert_sites", "runner_code", "sites", "status"]
