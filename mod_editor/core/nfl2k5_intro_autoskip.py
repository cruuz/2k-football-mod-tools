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

Patch: the intro's per-frame update (0x125BC0) is where a player's A/START press ends the intro: after its start block,
at L1, it gates (0x65D30 / 0x63810: the controller loop runs only in games with a human side) and polls each active
controller (0x709B0, 0x70A10 & 0x110) and calls the game's own skip handler 0xA2120, which for the intro phase
(0xB616C0 = 2; table 0xA2494 -> 0xA2198) ends the intro through 0x125CD0 and goes on to the coin toss. The 5-byte
``call 0x65D30`` at L1 (0x125C10, reached every frame) becomes a call to a 60-byte helper that makes that call and then,
only when the intro cannot end by itself, calls 0xA2120 once before returning 0x65D30's value:

    the intro is running ([0xBB75DC] == 1) and in the intro phase ([0xB616C0] == 2),
    its context has completed (bit 2 of [0xBB75F0], set by 0x1256D0 after DIR_INTRO's load), and
    heap B is empty ([0xBB74B0+0x88] free == [0xBB74B4] - [0xBB74B0]): DIR_INTRO is heap B's only allocation (made in
    the DRCT handler before the completion), so an empty heap B at that point means its load failed.

The skip is the player's A press (the same handler, in the same frame, just before the human-only gate, so CPU v CPU
games end the intro too); 0x125CD0 moves the intro to state 2 (and does nothing if called again), so it fires once.
With the director loaded heap B holds its block and the helper only makes the original call: every intro that plays,
plays as before. 64 MB and 128 MB alike; no memory.

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
UPGRADES_PREVIOUS = True   # revision 1 (int 98ddc6ba5, the 0x125C37 call) reads "previous"; apply() upgrades it in place
BUILD_CAPTION = "Skip the pregame intro when it cannot load"
HELP_TEXT = ("Retail: when the pregame intro's camera script does not fit in memory (some stadiums at 64 MB, and at "
             "128 MB without the bigger graphics memory), the stadium flyover repeats until A is pressed, and a CPU v "
             "CPU game never starts. Patch: the intro then skips itself exactly as an A press would and the game goes "
             "on to the coin toss. Intros that load play as before. Needs the resource load guard.")

SITE_VA = 0x00125C10
RETAIL_SITE = bytes.fromhex("e81b01f4ff")        # call 0x65D30 (L1 of the intro update, reached every frame)
SITE_CALLEE = 0x00065D30
# b780-mem1 rev 1 (int 98ddc6ba5, never released): the helper sat on the controller loop's ``call 0x70A10`` at 0x125C37,
# which CPU v CPU games never reach (EMU1 T3a: the gate word 0xE6002C is 0 there). An install of it reads "previous" and
# apply() upgrades it in place: 0x125C37 back to retail, the same allocation rewritten, the call at 0x125C10 hooked.
PREVIOUS_SITE_VA = 0x00125C37
PREVIOUS_RETAIL_SITE = bytes.fromhex("e8d4adf4ff")
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
    """The helper (58 bytes, padded with int3 to the 64-byte allocation), in place of L1's ``call 0x65D30``: it makes
    that call, and when the intro cannot end by itself it calls the game's skip handler 0xA2120 once, then returns
    0x65D30's value. ecx and the flags change (the caller compares eax right after and sets ecx itself before use)."""
    code = bytearray()
    code += b"\xe8" + struct.pack("<i", SITE_CALLEE - (code_va + 5))          # call 0x65D30 (the replaced call)
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
    code += b"\x50"                                                            # push eax (0x65D30's value)
    skip_at = len(code)
    code += b"\xe8" + struct.pack("<i", SKIP_HANDLER - (code_va + skip_at + 5))  # call 0xA2120 (the A skip)
    code += b"\x58"                                                            # pop eax
    done = len(code)
    code += b"\xc3"                                                            # ret
    for at in jumps:
        code[at + 1] = done - (at + 2)
    require(len(code) <= CODE_SIZE, "intro auto-skip helper exceeds its allocation")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def site_bytes(code_va: int) -> bytes:
    return b"\xe8" + struct.pack("<i", code_va - (SITE_VA + 5))


def previous_code_for(code_va: int) -> bytes:
    """Revision 1's helper (int 98ddc6ba5): call 0x70A10, then add the A bit under the same four conditions."""
    code = bytearray()
    code += b"\xe8" + struct.pack("<i", BUTTONS - (code_va + 5))
    code += b"\x83\x3d" + struct.pack("<I", INTRO_STATE) + b"\x01"
    jumps = [len(code)]; code += b"\x75\x00"
    code += b"\x83\x3d" + struct.pack("<I", PHASE) + b"\x02"
    jumps.append(len(code)); code += b"\x75\x00"
    code += b"\xf6\x05" + struct.pack("<I", INTRO_FLAGS) + bytes([READY_BIT])
    jumps.append(len(code)); code += b"\x74\x00"
    code += b"\x8b\x0d" + struct.pack("<I", HEAP_B + 4)
    code += b"\x2b\x0d" + struct.pack("<I", HEAP_B)
    code += b"\x3b\x0d" + struct.pack("<I", HEAP_B + 0x88)
    jumps.append(len(code)); code += b"\x75\x00"
    code += b"\x83\xc8" + bytes([A_BIT])
    done = len(code)
    code += b"\xc3"
    for at in jumps:
        code[at + 1] = done - (at + 2)
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def previous_site_bytes(code_va: int) -> bytes:
    return b"\xe8" + struct.pack("<i", code_va - (PREVIOUS_SITE_VA + 5))


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
        for at, retail in ((SITE_VA, RETAIL_SITE), (PREVIOUS_SITE_VA, PREVIOUS_RETAIL_SITE)):
            if va <= at < va + size:
                content[at - va:at - va + len(retail)] = retail
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign intro auto-skip prerequisite at {va:#x}")


def _recognize(payload):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    rows = _rows(payload)
    owned = allocations(payload) if rows else None
    code_va = owned["code"]["va"] if owned else None
    site = image.read(SITE_VA, len(RETAIL_SITE))
    old_site = image.read(PREVIOUS_SITE_VA, len(PREVIOUS_RETAIL_SITE))
    blob = image.read(code_va, CODE_SIZE) if owned else None
    if owned and site == RETAIL_SITE and old_site == previous_site_bytes(code_va) and blob == previous_code_for(code_va):
        state = "previous"
    else:
        require(old_site == PREVIOUS_RETAIL_SITE, "Foreign intro auto-skip site at 0x125C37")
        states = {"retail" if site == RETAIL_SITE else "applied" if owned and site == site_bytes(code_va) else "foreign"}
        if owned:
            states.add("retail" if blob == b"\xcc" * CODE_SIZE else "applied" if blob == code_for(code_va) else "foreign")
        require(states in ({"retail"}, {"applied"}), "Foreign or mixed intro auto-skip site/code")
        state = next(iter(states))
    _check_guards(image)
    return state


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
    upgraded = state == "previous"
    if upgraded:   # revision 1 -> this one, in place: 0x125C37 back to retail, the same allocation rewritten below
        code_va = allocations(payload)["code"]["va"]
        image = XbeImage(payload)
        buf = bytearray(payload)
        off = image.offset(PREVIOUS_SITE_VA, len(PREVIOUS_RETAIL_SITE))
        buf[off:off + len(PREVIOUS_RETAIL_SITE)] = PREVIOUS_RETAIL_SITE
        for section in _sections(buf):
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
        payload = bytes(buf)
    elif not _rows(payload):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "The intro auto-skip needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocations(payload)["code"]["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va),
                                    previous=previous_code_for(code_va) if upgraded else None)
    image = XbeImage(payload)
    buf = bytearray(payload)
    off = image.offset(SITE_VA, len(RETAIL_SITE))
    require(bytes(buf[off:off + len(RETAIL_SITE)]) == RETAIL_SITE, f"Intro auto-skip site {SITE_VA:#x} is not retail")
    buf[off:off + len(RETAIL_SITE)] = site_bytes(code_va)
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "Intro auto-skip postcondition failed")
    return result, dict(common, status="applied", upgraded_from_previous=upgraded,
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt, code_va=hex(code_va),
                        edits=[dict(label="intro_buttons", va=hex(SITE_VA), before=RETAIL_SITE.hex(),
                                    after=site_bytes(code_va).hex())],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


def main(argv=None) -> int:
    """python3 -m mod_editor.core.nfl2k5_intro_autoskip {status,apply} source.xbe [--output new.xbe]"""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=BUILD_CAPTION)
    parser.add_argument("command", choices=("status", "apply"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = args.source.read_bytes()
    if args.command == "status":
        print(json.dumps({"owner": OWNER, "status": status(payload)}))
        return 0
    require(args.output is not None, "apply needs --output")
    result, receipt = apply(payload)
    with args.output.open("xb") as stream:
        stream.write(result)
    print(json.dumps({k: v for k, v in receipt.items() if k != "allocation"}, indent=2, default=str))
    return 0


__all__ = ["OWNER", "REQUESTS", "BUILD_CAPTION", "HELP_TEXT", "IntroAutoskipError", "apply", "status", "read_settings",
           "code_for", "site_bytes"]


if __name__ == "__main__":
    raise SystemExit(main())
