"""EXPERIMENTAL / UNWITNESSED scorebug events in owned RX/RW pages.

The companion resource compiler loads native TXTRs with the HUD collection.
Only loader-returned texture descriptors are bound; no raw pixel pointer is used.
Reserve the union of REQUESTS and other owners before applying either patch.
"""
from __future__ import annotations

import struct

from . import nfl2k5_xbe_space as space
from . import nfl2k5_scorebug_ingame as scene
from .nfl2k5_draft_ai import _Asm
from .nfl2k5_bump_strength import _sections, section_digest

OWNER = "nfl2k5_scorebug_runtime"
CODE_SIZE, DATA_SIZE = 1408, 128
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
HOOKS = {"setup": (0xFCE56, bytes.fromhex("e845f3ffff")),
         "update": (0xFCFA2, bytes.fromhex("e819faffff"))}
# State: scene, populated, two material pointers, eight resident texture pointers,
# two scores, two flash timers, down, possession, ball/line positions, phase.
SCENE, POPULATED, MATERIALS, TEXTURES = 0, 4, 8, 16
SCORES, FLASH, DOWN, POSSESSION, BALL, LINE, PHASE = 48, 56, 64, 68, 72, 76, 80
HOME_CONTEXT, AWAY_CONTEXT = 0xB30864, 0xB30A58
SCORE_POINTERS = (0xE5FC28, 0xE5FC68)
SCORE_COLORS = (0xA95958, 0xA95990)
DARK, RED, WHITE, ACCENT = 0xFF111118, 0xFFD0021B, 0xFFFFFFFF, 0xFFFFD166


def _u(value):
    return struct.pack("<I", value).hex()


def _save(a):
    # EBP anchors the saved GPR frame. FXSAVE covers x87/MMX/SSE/MXCSR.
    a.b("9c 60 8bec 81ec20020000 83e4f0 0fae0424 dbe3 fc")


def _restore(a):
    a.b("0fae0c24 8be5 61 9d")


def code_for(code_va, data_va):
    a = _Asm(code_va)
    def b(s): a.b(s)
    def absop(op, va): b(op + _u(va))
    def store(va, value): b("c705" + _u(va) + _u(value))
    def jump(op, label): a.j32(op, label)
    def call(label): a.j32("e8", label)
    a.label("setup")
    a.call(0xFC1A0)  # displaced native call, exactly once, original ABI
    _save(a)
    b("31c0 bf" + _u(data_va) + " b9" + _u(DATA_SIZE // 4) + " f3ab")
    absop("a1", 0xA95528); absop("a3", data_va + SCENE)
    b("85c0"); jump("0f84", "setup_done")
    # Home is hscore_buga on the right; away is zscore_buga on the left.
    for side, context, name in ((0, HOME_CONTEXT, 0xE6C638), (1, AWAY_CONTEXT, 0xE6C734)):
        absop("8b35", 0xA95528); b("68" + _u(name)); a.call(0xFBC70)
        absop("a3", data_va + MATERIALS + side * 4)
        b("be" + _u(context) + " bf" + _u(data_va + TEXTURES + side * 16))
        b("ba" + _u(ord("h" if side == 0 else "a")))
        call("load_side")
        absop("8b0d", data_va + MATERIALS + side * 4)
        b("85c9"); jump("0f84", f"setup_side_done{side}")
        absop("a1", SCORE_POINTERS[side]); b("31d2 85c0"); jump("0f84", f"setup_count{side}")
        b("8b5004 83fa03"); jump("0f86", f"setup_count{side}")
        b("31d2")
        a.label(f"setup_count{side}")
        b("8b0495" + _u(data_va + TEXTURES + side * 16) + " 894130 85c0")
        jump("0f84", f"setup_hide{side}")
        b("836108fe"); jump("e9", f"setup_side_done{side}")
        a.label(f"setup_hide{side}"); b("83490801")
        a.label(f"setup_side_done{side}")
    store(0xA95B00, 0)  # stop native hangtime from hiding the repurposed home panel
    a.label("setup_done"); _restore(a); b("c3")

    # A real stdcall call site: forward its float argument, native RET 4 consumes
    # the copy; our RET 4 consumes the original. Save AFTER native side effects.
    a.label("update")
    b("ff742404"); a.call(0xFC9C0)
    _save(a)
    absop("a1", 0xA95528); b("85c0"); jump("0f84", "update_done")
    absop("3b05", data_va + SCENE); jump("0f85", "update_done")
    absop("833d", 0xA95520); b("00"); jump("0f84", "update_done")
    # Positive, finite dt <= 1 second only. Integer compare also rejects NaNs.
    b("8b4528 3d0000803f"); jump("0f86", "dt_ok")
    b("31c0")
    a.label("dt_ok")
    # Frame dt scratch belongs in the private aligned stack, not the saved frame.
    b("89842410020000")
    for side, score_ptr in enumerate(SCORE_POINTERS):
        absop("a1", score_ptr); b("85c0"); jump("0f84", f"side_done{side}")
        b("8b5004 83fa03"); jump("0f86", f"count_ok{side}")
        b("31d2")  # invalid counts dim all; never show fictitious remaining timeouts
        a.label(f"count_ok{side}")
        absop("8b0d", data_va + MATERIALS + side * 4)
        b("85c9"); jump("0f84", f"no_material{side}")
        b("8b1495" + _u(data_va + TEXTURES + side * 16))
        b("895130 85d2"); jump("0f84", f"hide{side}")
        b("836108fe"); jump("e9", f"no_material{side}")
        a.label(f"hide{side}"); b("83490801")
        a.label(f"no_material{side}")
        b("8b10")
        absop("833d", data_va + POPULATED); b("00"); jump("0f84", f"seed{side}")
        absop("3b15", data_va + SCORES + side * 4); jump("0f84", f"seed{side}")
        store(data_va + FLASH + side * 4, struct.unpack("<I", struct.pack("<f", .18))[0])
        a.label(f"seed{side}"); absop("8915", data_va + SCORES + side * 4)
        store(SCORE_COLORS[side], WHITE)
        absop("a1", data_va + FLASH + side * 4); b("85c0"); jump("0f8e", f"side_done{side}")
        store(SCORE_COLORS[side], ACCENT)
        absop("d905", data_va + FLASH + side * 4); b("d8a42410020000")
        absop("d91d", data_va + FLASH + side * 4)
        a.label(f"side_done{side}")
    # The native formatter reads down and both line/ball Z positions from this
    # same state; compare all bits plus possession and phase once per update.
    absop("a1", 0xE602EC); b("85c0"); jump("0f84", "clock")
    b("31d2")
    for off, state in ((4, DOWN), (0x18, BALL), (0x28, LINE)):
        b("8b48" + f"{off:02x}")
        absop("3b0d", data_va + state); b("0f95c3 08da")
        absop("890d", data_va + state)
    for ptr, state in ((0xE60280, POSSESSION), (0xE602B4, PHASE)):
        absop("8b0d", ptr); absop("3b0d", data_va + state); b("0f95c3 08da")
        absop("890d", data_va + state)
    b("84d2"); jump("0f84", "clock")
    absop("833d", data_va + POPULATED); b("00"); jump("0f84", "clock")
    absop("833d", 0xA95A00); b("00"); jump("0f84", "clock")
    # Native ramp already ran, and visibility was just written by FC9C0. Reset
    # to 1/30 open (visible, 0.2 HUD units); next updates finish the 0.2 s ramp.
    store(0xA95A04, 0x3F800000)
    a.label("clock")
    store(0xA95A48, DARK)
    absop("a1", 0xE60294); b("85c0"); jump("0f84", "populated")
    b("f6401806"); jump("0f85", "populated")
    absop("833d", 0xA95A70); b("00"); jump("0f84", "populated")
    b("8b4010 3d0000a040"); jump("0f83", "populated")
    # unsigned < 5.0 accepts +0 and positive finite seconds; -0 is harmless.
    store(0xA95A48, RED)
    a.label("populated"); store(data_va + POPULATED, 1)
    a.label("update_done"); _restore(a); b("c20400")

    # Four native TXTR lookups for this side at setup. UTF-16 names are built on
    # stack. Validate two numeric asset-code chars and reject created-team kinds.
    a.label("load_side")
    b("83ec10 c7042473006200 c74424042d002d00 6689542408 c744240a30000000")
    b("83be2801000002"); jump("0f84", "neutral")
    b("83be2801000004"); jump("0f84", "neutral")
    b("8b860c010000 85c0"); jump("0f84", "neutral")
    b("6683780400"); jump("0f85", "neutral")
    b("0fb708 83e930 83f903"); jump("0f87", "neutral")
    b("0fb75002 83ea30 83fa09"); jump("0f87", "neutral")
    b("6bc90a 03ca 83f91e"); jump("0f86", "identity_ok")
    b("83f925"); jump("0f85", "neutral")
    a.label("identity_ok"); b("8b00 89442404")
    a.label("neutral"); b("31f6")
    a.label("texture_loop")
    b("8d4630 668944240a 8d0424 50 ba54585452 31c9")
    a.call(0x449E0)
    # Retry neutral for a missing team texture, retaining count and orientation.
    b("85c0"); jump("0f85", "texture_found")
    b("817c24042d002d00"); jump("0f84", "texture_found")
    b("8b542404 52 c74424082d002d00 8d442404 50 ba54585452 31c9")
    a.call(0x449E0); b("5a 89542404")
    a.label("texture_found"); b("8904b7 46 83fe04"); jump("0f82", "texture_loop")
    b("83c410 c3")
    content = a.assemble()
    if len(content) > CODE_SIZE:
        raise ValueError(f"scorebug code exceeds its named allocation: {len(content)}")
    return content.ljust(CODE_SIZE, b"\xcc"), {k: code_va + v for k, v in a.labels.items()}


def sites(payload):
    owned = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    space._require(set(owned) == {"code", "data"}, "missing scorebug allocations; reserve the owner union first")
    for kind, size, align in (("code", CODE_SIZE, 16), ("data", DATA_SIZE, 16)):
        space._require((owned[kind]["size"], owned[kind]["align"]) == (size, align), "foreign scorebug allocation")
    return owned["code"], owned["data"]


def hook_bytes(name, labels):
    va, original = HOOKS[name]
    return b"\xe8" + struct.pack("<i", labels[name] - va - 5)


def _abi_valid(payload):
    from .nfl2k5_scorebug_resources import RUNTIME_ABI_GUARDS
    normal = [(va, old) for va, old, _, _ in scene.xbe_specs()]
    normal += list(HOOKS.values())
    for va, size, sha in RUNTIME_ABI_GUARDS:
        off = scene.layout.sbpos.va_to_off(payload, va)
        body = bytearray(payload[off:off + size])
        for address, old in normal:
            if va <= address and address + len(old) <= va + size:
                body[address-va:address-va+len(old)] = old
        if scene.digest(body) != sha:
            return False
    return True


def status(payload):
    try:
        ss = space.status(payload)
        if ss == "foreign" or scene.xbe_status(payload) == "foreign" or not _abi_valid(payload):
            return "foreign"
        expected = {name: original for name, (_, original) in HOOKS.items()}
        code_state = "retail"
        if ss == "applied" and any(a["owner"] == OWNER for a in space.layout(payload)["allocations"]):
            code, data = sites(payload)
            content, labels = code_for(code["va"], data["va"])
            have = payload[code["raw"]:code["raw"] + CODE_SIZE]
            if have == content:
                code_state = "applied"
                expected = {n: hook_bytes(n, labels) for n in HOOKS}
            elif have != b"\xcc" * CODE_SIZE:
                return "foreign"
        for name, (va, _) in HOOKS.items():
            off = scene.layout.sbpos.va_to_off(payload, va)
            if payload[off:off + 5] != expected[name]:
                return "foreign"
        if code_state == "applied" and scene.xbe_status(payload) != "applied":
            return "foreign"
        return code_state
    except (ValueError, KeyError, IndexError, struct.error, SystemExit):
        return "foreign"


def apply(payload):
    before = status(payload)
    space._require(before != "foreign", "foreign/mixed scorebug runtime; rebuild from supported base")
    if before == "applied":
        return payload, {"status": "already_applied", "changed_bytes": 0,
                         "experimental": True, "runtime_witnessed": False}
    prepared, sr = scene.apply_xbe(payload)
    if space.status(prepared) == "retail":
        prepared, ar = space.apply(prepared, REQUESTS)
    else:
        ar = {}
    code, data = sites(prepared)
    content, labels = code_for(code["va"], data["va"])
    installed, ir = space.install_code(prepared, OWNER, content)
    buf = bytearray(installed)
    edits = []
    for name, (va, original) in HOOKS.items():
        off = scene.layout.sbpos.va_to_off(installed, va)
        after = hook_bytes(name, labels)
        buf[off:off + 5] = after
        edits.append(dict(label=name, va=hex(va), size=5, before=original.hex(), after=after.hex()))
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    result = bytes(buf)
    space._require(status(result) == "applied", "scorebug runtime postcondition failed")
    return result, dict(status="applied", experimental=True, runtime_witnessed=False,
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                        code_va=hex(code["va"]), data_va=hex(data["va"]), edits=edits,
                        allocation=ar, installation=ir, scorebug=sr,
                        reservations=space.reservations(result),
                        requires_resources="scorebug-runtime-v1; XBE alone does not install logos")
