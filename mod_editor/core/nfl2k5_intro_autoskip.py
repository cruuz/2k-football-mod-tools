"""The pregame intro skips itself when its director could not load, instead of looping on the stadium flyover.

Why (b780-mem1, 2026-11-03)
---------------------------
The pregame intro plays from a director script, DIR_INTRO (73,680 B, 73,856 B charged), which game setup loads into
heap B, the room left of the in-game block after the cutscene heap (0x125700 queues the context: file [0xAA1D20], heap
0xBB74B0, completion 0x1256D0). When heap B is too small the load gets NULL; the resource load guard
(nfl2k5_resource_load_guard) turns the old NULL write into a skipped resource, the context still completes (0x1256D0
sets bit 2 of 0xBB75F0), but no director registers. The intro can then only end two ways: a director script's end action
(dispatcher 0x1F7DF0, case 0x1F7E04 -> 0x125CD0) or the player's A/START skip, so the stadium flyover loops until A is
pressed. EMU1 measured it on the v0.9 RC and on v0.8 at Baltimore at 128 MiB (heap B 6,400 / 66,304 B), and 64 MB discs
have even less room. CPU v CPU, or a player who does not know to press A, never reaches the kickoff.

Patch: the intro's per-frame update (0x125BC0) polls each active controller (0x709B0) for A/START (0x70A10 & 0x110)
and calls the game's own skip handler 0xA2120, which for the intro phase (0xB616C0 = 2; table 0xA2494 -> 0xA2198) ends
the intro through 0x125CD0 and goes on to the coin toss. The 5-byte ``call 0x70A10`` at 0x125C37 becomes a call to a
56-byte helper that calls 0x70A10 and adds the A bit (0x10) only when the intro cannot end by itself:

    the intro is running ([0xBB75DC] == 1) and in the intro phase ([0xB616C0] == 2),
    its context has completed (bit 2 of [0xBB75F0], set by 0x1256D0 after DIR_INTRO's load), and
    heap B is empty ([0xBB74B0+0x88] free == [0xBB74B4] - [0xBB74B0]): DIR_INTRO is heap B's only allocation (made in
    the DRCT handler before the completion), so an empty heap B at that point means its load failed.

The skip is then exactly the player's A press on the first active controller (same caller, same handler, same frame
gate); 0x125CD0 moves the intro to state 2, so it fires once. With the director loaded heap B holds its block and the
helper returns 0x70A10's value unchanged: every intro that plays, plays as before. 64 MB and 128 MB alike; no memory.

Evidence: PROVED OFFLINE (Unicorn on the RC's own 0x125BC0 with the helper, the NULL and loaded directors, the native A
press). Not yet witnessed in game.
"""

from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_intro_autoskip"
CODE_SIZE = 64
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
EVIDENCE = "EXPERIMENTAL"
BUILD_CAPTION = "Skip the pregame intro when it cannot load"
HELP_TEXT = ("Retail: when the pregame intro's camera script does not fit in memory (some stadiums at 64 MB, and at "
             "128 MB without the bigger graphics memory), the stadium flyover repeats until A is pressed, and a CPU v "
             "CPU game never starts. Patch: the intro then skips itself exactly as an A press would and the game goes "
             "on to the coin toss. Intros that load play as before. Needs the resource load guard.")

SITE_VA = 0x00125C37
RETAIL_SITE = bytes.fromhex("e8d4adf4ff")        # call 0x70A10 (buttons of controller ecx)
BUTTONS = 0x00070A10                             # ecx = controller, edx = 0 -> eax = [0xB37A78 + ecx * 0x244]
INTRO_STATE = 0x00BB75DC                         # 0 off, 1 running, 2 ended (0x125CD0)
PHASE = 0x00B616C0                               # 2 = the intro (0xA2120's dispatch)
INTRO_FLAGS = 0x00BB75F0                         # bit 2: the DIR_INTRO context completed (0x1256D0)
READY_BIT = 0x04
HEAP_B = 0x00BB74B0                              # +0 start, +4 end, +0x88 free bytes (0x48640)
A_BIT = 0x10
SKIP_HANDLER = 0x000A2120
# (va, size, sha256) of the retail code the helper relies on (this owner's site masked back to retail)
GUARDS = (
    (0x00125BC0, 0x90, "0461397ac47fbbf3d6c2dc013a1d0198e094bfe2dc40e9e053302976c94df0aa"),  # the intro's per-frame update
    (0x00070A10, 0x14, "05b42dd137ed22f8c377a2477079462a049450ed314b08fafc53ae8689c6c0f1"),  # buttons
    (0x000709B0, 0x14, "5fc1b7b5070fa6b814a05291e0df39a5f4cd440da398de2402a21be8c2664582"),  # controller active
    (0x001256D0, 0x08, "d683f8aea31866e8c8d1a3e1cc185ecb31a63caea07edb57cc953df0bb9593a9"),  # completion: bit 2
    (0x000A2120, 0x39, "e888fcaf0437f9e289b2cc3eeda2951d611b400941275038f1cbbb35a2fa27c9"),  # the skip handler's dispatch
    (0x000A2470, 0x24, "e96951afac96f69f27245fe8f97a4b4c678c793577487cfe4ad08f010b93edb8"),  # its jump table
    (0x000A2494, 0x1A, "6fe027269233e215320a4112cf96d656b797f5e556d8fbd2330d36ef9ae2f742"),  # phase -> case (2 -> 0xA2198)
    (0x000A2198, 0x3E, "a0e2f5a1a4f8ab7ad23ee7682e836f569b702e198d78c003d567896f5f3794c1"),  # the intro skip (-> 0x125CD0)
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError)


class IntroAutoskipError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise IntroAutoskipError(message)


def code_for(code_va: int) -> bytes:
    """The helper (56 bytes, padded with int3 to the 64-byte allocation). Only eax, ecx and the flags change; the
    caller tests eax right after and uses neither ecx nor edx (0x70A10 clobbers both itself)."""
    code = bytearray()
    code += b"\xe8" + struct.pack("<i", BUTTONS - (code_va + 5))               # call 0x70A10
    code += b"\x83\x3d" + struct.pack("<I", INTRO_STATE) + b"\x01"            # cmp dword [state], 1
    jumps = [len(code)]; code += b"\x75\x00"                                   # jne done
    code += b"\x83\x3d" + struct.pack("<I", PHASE) + b"\x02"                  # cmp dword [phase], 2
    jumps.append(len(code)); code += b"\x75\x00"                               # jne done
    code += b"\xf6\x05" + struct.pack("<I", INTRO_FLAGS) + bytes([READY_BIT])  # test byte [flags], 4
    jumps.append(len(code)); code += b"\x74\x00"                               # jz done
    code += b"\x8b\x0d" + struct.pack("<I", HEAP_B + 4)                       # mov ecx, [heap B end]
    code += b"\x2b\x0d" + struct.pack("<I", HEAP_B)                           # sub ecx, [heap B start]
    code += b"\x3b\x0d" + struct.pack("<I", HEAP_B + 0x88)                    # cmp ecx, [heap B free]
    jumps.append(len(code)); code += b"\x75\x00"                               # jne done (something is allocated)
    code += b"\x83\xc8" + bytes([A_BIT])                                       # or eax, 0x10
    done = len(code)
    code += b"\xc3"                                                            # ret
    for at in jumps:
        code[at + 1] = done - (at + 2)
    require(len(code) <= CODE_SIZE, "intro auto-skip helper exceeds its allocation")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def site_bytes(code_va: int) -> bytes:
    return b"\xe8" + struct.pack("<i", code_va - (SITE_VA + 5))


def _rows(payload):
    from . import nfl2k5_xbe_space as space
    if space.status(payload) == "retail":
        return {}
    return {r["kind"]: r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER}


def allocations(payload):
    rows = _rows(payload)
    require(set(rows) == {"code"} and rows["code"]["size"] == CODE_SIZE, "Missing or foreign intro auto-skip allocation")
    return rows


def _check_guards(image):
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        if va <= SITE_VA < va + size:
            content[SITE_VA - va:SITE_VA - va + len(RETAIL_SITE)] = RETAIL_SITE
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign intro auto-skip prerequisite at {va:#x}")


def _recognize(payload):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    rows = _rows(payload)
    owned = allocations(payload) if rows else None
    states = set()
    raw = image.read(SITE_VA, len(RETAIL_SITE))
    states.add("retail" if raw == RETAIL_SITE else
               "applied" if owned and raw == site_bytes(owned["code"]["va"]) else "foreign")
    if owned:
        code_va = owned["code"]["va"]
        blob = image.read(code_va, CODE_SIZE)
        states.add("retail" if blob == b"\xcc" * CODE_SIZE else "applied" if blob == code_for(code_va) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed intro auto-skip site/code")
    _check_guards(image)
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def read_settings(payload):
    return {"status": status(payload)}


def apply(payload):
    """Install, or replay an identical installation. Retail, or a sealed scale-out image without this owner."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise IntroAutoskipError(f"foreign/mixed intro auto-skip input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not _rows(payload):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "The intro auto-skip needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocations(payload)["code"]["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    image = XbeImage(payload)
    buf = bytearray(payload)
    off = image.offset(SITE_VA, len(RETAIL_SITE))
    require(bytes(buf[off:off + len(RETAIL_SITE)]) == RETAIL_SITE, f"Intro auto-skip site {SITE_VA:#x} is not retail")
    buf[off:off + len(RETAIL_SITE)] = site_bytes(code_va)
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "Intro auto-skip postcondition failed")
    return result, dict(common, status="applied",
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt, code_va=hex(code_va),
                        edits=[dict(label="intro_buttons", va=hex(SITE_VA), before=RETAIL_SITE.hex(),
                                    after=site_bytes(code_va).hex())],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "BUILD_CAPTION", "HELP_TEXT", "IntroAutoskipError", "apply", "status", "read_settings",
           "code_for", "site_bytes"]
