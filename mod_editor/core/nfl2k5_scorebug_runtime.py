"""EXPERIMENTAL / UNWITNESSED 2026 Monday Night Football scorebug owner in owned RX/RW pages.

Beta 70 (revision 6): the owner binds ONE 128x32 wing texture per side (the
team's current logo on its colour fading into the bar), so the resident cost
of the option is 64 small textures instead of the 264 textures and 7 fonts of
beta 69, which the intro's resource loader could not fit (a null read buffer
kernel fault after the Berman intro, reproduced 2026-09-15). Timeout marks are
text: the two retail team-name callbacks now write the remaining timeouts as
dashes. The down plate takes the possessing team's colour every frame, the
play clock turns ESPN red under five seconds, scores flash on a change and
the native slide re-fires on a new down. No private FONT is bound; the ESPN
digits live in the private HUD fonts (nfl2k5_scorebug_mnf_font).

Private textures are resolved in GAMEDATA, the resident HUD collection.
Reserve the union of REQUESTS and other owners before applying either patch.
"""
from __future__ import annotations

import struct

from . import nfl2k5_xbe_space as space
from . import nfl2k5_scorebug_fonts as fonts  # noqa: F401 - the historical beta 61 emitter test runs old code in this namespace
from . import nfl2k5_scorebug_ingame as scene
from .nfl2k5_draft_ai import _Asm
from .nfl2k5_bump_strength import _sections, section_digest

OWNER = "nfl2k5_scorebug_runtime"
CODE_SIZE, DATA_SIZE = 1408, 128
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
HOOKS = {"setup": (0xFCE56, bytes.fromhex("e845f3ffff")),
         "update": (0xFCFA2, bytes.fromhex("e819faffff"))}
REVISION = 7
# State (128 bytes): scene, populated, two wing materials, the plate material,
# two wing textures, two scores, two flash timers, down, possession, ball/line,
# phase. All state stays inside the owned RW page.
SCENE, POPULATED, MATERIALS, PLATE, TEXTURES = 0, 4, 8, 16, 20
SCORES, FLASH, DOWN, POSSESSION, BALL, LINE, PHASE = 32, 40, 48, 52, 56, 60, 64
HOME_CONTEXT, AWAY_CONTEXT = 0xB30864, 0xB30A58
SCORE_POINTERS = (0xE5FC28, 0xE5FC68)
TEAM_OBJECTS = (0xE5FC20, 0xE5FC60)  # home, away team objects; 0xE60280 holds the one with possession
SCORE_COLORS = (0xA95958, 0xA95990)
CITY_CALLBACKS = (0xA95884, 0xA958AC)  # home, away text records: retail binds 0xA95884 to 0xFC010 (getter 0x61C50 = context 0xB30864, whose +0x108 is the HOME abbreviation) and 0xA958AC to 0xFC030 (0x61C60 = 0xB30A58, away); same order as SCORE_POINTERS
PLATE_MATERIAL_NAME = 0xE6C5D4
CLOCK_FONT_NAME_VA = 0xE6B490   # UTF-16 "FirstPersonComic", the retail tenth boot font name: the clock font
QUARTER_FONT_NAME_VA = 0xE6C79A  # UTF-16 "core_bug" inside the retail "score_bug" literal: the quarter label's smaller font
CLOCK_FONT_RECORDS = (0xA95918, 0xA95940, 0xA95A80, 0xA95968, 0xA959A0, 0xA958A0, 0xA958C8, 0xA95A10)  # game clocks, play clock, scores, ticks, down text; resolved descriptors
QUARTER_FONT_RECORDS = (0xA958F0,)                   # the quarter record's resolved descriptor (+0x1C); the +4/+8 slot indices stay retail for the native init
FONT_TAG = 0x544E4F46           # 'FONT' as the lookup tag word (TXTR is 0x52545854)        # UTF-16 "dscore_buga"
WHITE, ACCENT = 0xFFFFFFFF, 0xFFFFD166
ESPN_RED, CAPSULE_INK = 0xFFE31937, 0xFF000000
PLAY_CLOCK_CELL = 0xFF780E27
SCORE_CALLBACKS = (0xA9594C, 0xA95984)
SCORE_DIGIT_BASE = 0x80
CLOCK_CELL_MATERIAL = 68
CLOCK_CELL_NAME = 0xE6C6E8  # UTF-16 score_buga, formerly the spare mark
PLAY_CLOCK_NORMAL = WHITE
RED, DARK = ESPN_RED, CAPSULE_INK  # names kept for the existing suites
# Beta 61..69 state names, kept only so the pinned historical emitter still evaluates in this namespace.
FONT_SCORE, FONT_COMPACT = 84, 88
SCORE_FONTS = (0xA95968, 0xA959A0)
HUD_COLLECTION_NAME = 0xE614B8  # UTF-16 GAMEDATA, used by the retail loader.
# The loader at 6310E opens gamedata.iff into B33D5C with ordinary context
# fields. Pin its call, both names and the named-context lookup dependency.
LOOKUP_GUARDS = (
    (0x6310E, 30, "92cf59f757d1dd7ae9d4881e2111c386dc28224035aafa39a1daa7fa0ffd8483"),
    (HUD_COLLECTION_NAME, 18, "64bf5caa58cd2d97b65e1fd6ebe6ea773d2613e0b83a109a24db9e6f94d91660"),
    (0xE614CC, 26, "9b1d922215249ee1a24d32042b258442536b1312d420248e595b44414ce698da"),
    (0x42F50, 44, "9193d3ee49c7eabfc4646ffbae6c3e12a76e43a051e890a4f8971b2dba4fc81b"),
    (0x43F50, 606, "9bf8b19d176dc9169c8d7b13af5887ce474ed202990d91f77b5601baccd21b71"),
)
# Static text-record fields this owner overrides on top of the static v3 layer
# (font slot, alignment and colours of the repurposed team-name records, the
# capsule text colours, the plate text). Recognized by nfl2k5_scorebug_ingame.
STATIC_OVERRIDES = {
    0xA95888: 7, 0xA958B0: 7,            # native fallback slot; setup binds the private tick font
    0xA9588C: 3, 0xA958B4: 3,            # centred under the scores
    0xA95894: 0xFFC8CACE, 0xA958BC: 0xFFC8CACE,    # light-grey timeout ticks
    0xA95898: 0xFFC8CACE, 0xA958C0: 0xFFC8CACE,    # no possession yellow on the dashes
    0xA958E4: 0xFF64666A, 0xA958E8: 0xFF64666A,   # quarter
    0xA9590C: CAPSULE_INK, 0xA95910: CAPSULE_INK,   # game clock
    0xA95934: CAPSULE_INK, 0xA95938: CAPSULE_INK,   # game clock (second record)
    0xA95A48: CAPSULE_INK,                          # play clock (rewritten per frame)
    0xA95904: 3, 0xA9592C: 3,                       # game clock centred in its capsule cell (retail: right-aligned)
}
LITERALS = {0xE6C404: ("Goal", "GOAL")}  # the down plate reads "1st & GOAL" like the broadcast


def _u(value):
    return struct.pack("<I", value).hex()


def _save(a):
    # EBP anchors the saved GPR frame. FXSAVE covers x87/MMX/SSE/MXCSR.
    a.b("9c 60 8bec 81ec20020000 83e4f0 0fae0424 dbe3 fc")


def _restore(a):
    a.b("0fae0c24 8be5 61 9d")


def code_for(code_va, data_va):
    from . import nfl2k5_scorebug_exact as exact
    a = _Asm(code_va)
    def b(s): a.b(s)
    def absop(op, va): b(op + _u(va))
    def store(va, value): b("c705" + _u(va) + _u(value))
    def jump(op, label): a.j32(op, label)
    def call(label): a.j32("e8", label)
    a.label("setup")
    a.call(0xFC1A0)  # displaced native call, exactly once, original ABI
    _save(a)
    b("31c0 bf" + _u(data_va) + " 6a" + f"{DATA_SIZE // 4:02x}" + " 59 f3ab")
    absop("a1", 0xA95528); absop("a3", data_va + SCENE)
    b("85c0"); jump("0f84", "setup_done")
    # Shared binder keeps v3 within the existing legacy RX reservation.
    for side, context, name in ((0, HOME_CONTEXT, 0xE6C638), (1, AWAY_CONTEXT, 0xE6C734)):
        b("be" + _u(context) + " bf" + _u(data_va + TEXTURES + side * 4))
        b("ba" + _u(ord("h" if side == 0 else "a")) + " b8" + _u(name))
        call("setup_side")
    # The down plate material takes the possessing team's colour every frame.
    absop("8b35", 0xA95528); b("68" + _u(PLATE_MATERIAL_NAME)); a.call(0xFBC70)
    absop("a3", data_va + PLATE)
    absop("8b35", 0xA95528); b("68" + _u(CLOCK_CELL_NAME)); a.call(0xFBC70)
    absop("a3", data_va + CLOCK_CELL_MATERIAL)
    # The ESPN clock font: after the native init resolved every record's slot index into a
    # descriptor, look the appended FONT up in the HUD collection and overwrite the quarter,
    # game clock and play clock descriptors (the beta 69 owner bound its fonts the same way; a
    # missing font leaves the retail descriptors alone).
    for label, name_va, records in (("clock", CLOCK_FONT_NAME_VA, CLOCK_FONT_RECORDS), ("quarter", QUARTER_FONT_NAME_VA, QUARTER_FONT_RECORDS)):
        b("68" + _u(name_va) + " ba" + _u(FONT_TAG) + " b9" + _u(HUD_COLLECTION_NAME))
        a.call(0x449E0)
        b("85c0"); jump("0f84", f"{label}_font_done")
        for va in records:
            absop("a3", va)
        if label == "clock":
            for side in (0, 1):
                a.label(f"score_callback{side}"); store(SCORE_CALLBACKS[side], 0)
        a.label(f"{label}_font_done")
    # Hang time retains its native text and visibility, on the spare event slab
    # instead of the home-wing material that v2 had to disable.
    absop("8b35", 0xA95528); b("68" + _u(0xE6C74C)); a.call(0xFBC70)
    absop("a3", 0xA95AEC)
    # The retail team-name callbacks become the timeout marks (dashes).
    for side in (0, 1):
        a.label(f"dash_callback{side}"); store(CITY_CALLBACKS[side], 0)
    a.label("play_callback"); store(0xA95A3C, 0)
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
        absop("a1", score_ptr)
        b("bf" + _u(data_va + side*4) + " be" + _u(SCORE_COLORS[side]))
        call("update_side")
    # The native formatter reads down and both line/ball Z positions from this
    # same state; compare all bits plus possession and phase once per update.
    absop("a1", 0xE602EC); b("85c0"); jump("0f84", "plate")
    b("31d2")
    for off, state in ((4, DOWN), (0x18, BALL), (0x28, LINE)):
        b("8b48" + f"{off:02x}")
        absop("3b0d", data_va + state); b("0f95c3 08da")
        absop("890d", data_va + state)
    for ptr, state in ((0xE60280, POSSESSION), (0xE602B4, PHASE)):
        absop("8b0d", ptr); absop("3b0d", data_va + state); b("0f95c3 08da")
        absop("890d", data_va + state)
    b("84d2"); jump("0f84", "plate")
    absop("833d", data_va + POPULATED); b("00"); jump("0f84", "plate")
    absop("833d", 0xA95A00); b("00"); jump("0f84", "plate")
    # Native ramp already ran, and visibility was just written by FC9C0. Reset
    # to 1/30 open (visible, 0.2 HUD units); next updates finish the 0.2 s ramp.
    store(0xA95A04, 0x3F800000)
    # Down plate: the possessing team's colour. The possession word names one of the
    # two team objects; the colour comes from that side's context (the same validated
    # asset-code path load_side uses), so an unexpected word tints nothing.
    a.label("plate")
    absop("8b0d", data_va + PLATE); b("85c9"); jump("0f84", "clock")
    absop("a1", 0xE60280); b("85c0"); jump("0f84", "clock")
    b("be" + _u(HOME_CONTEXT))
    b("3d" + _u(TEAM_OBJECTS[0])); jump("0f84", "plate_side")
    absop("3b05", SCORE_POINTERS[0]); jump("0f84", "plate_side")
    b("be" + _u(AWAY_CONTEXT))
    b("3d" + _u(TEAM_OBJECTS[1])); jump("0f84", "plate_side")
    absop("3b05", SCORE_POINTERS[1]); jump("0f85", "clock")
    a.label("plate_side")
    b("83be2801000002"); jump("0f84", "clock")
    b("83be2801000004"); jump("0f84", "clock")
    b("8b860c010000 85c0"); jump("0f84", "clock")           # UTF-16 asset code
    b("0fb710 83ea30 83fa03"); jump("0f87", "clock")         # tens digit 0..3
    b("0fb74002 83e830 83f809"); jump("0f87", "clock")       # ones digit 0..9
    b("6bd20a 01d0 8d0440 8b80"); a.label("plate_table_ref"); b("00000000")
    b("0d000000ff 894118")
    a.label("clock")
    store(0xA95A48, PLAY_CLOCK_NORMAL)
    absop("8b0d",data_va+CLOCK_CELL_MATERIAL)
    b("85c9"); jump("0f84","populated")
    b("c74118"+_u(PLAY_CLOCK_CELL))
    absop("a1", 0xE60294); b("85c0"); jump("0f84", "populated")
    b("f6401806"); jump("0f85", "populated")
    absop("833d", 0xA95A70); b("00"); jump("0f84", "populated")
    b("8b4010 3d0000a040"); jump("0f83", "populated")
    # unsigned < 5.0 accepts +0 and positive finite seconds; -0 is harmless.
    # A red pulse lives on the cell, preserving the white digit's contrast.
    b("a900002000"); jump("0f85","populated")
    b("c74118"+_u(ESPN_RED))
    a.label("populated"); store(data_va + POPULATED, 1)
    a.label("update_done"); _restore(a); b("c20400")

    a.label("update_side")
    b("85c0"); a.j8("74", "side_done")
    b("8b4f08 85c9"); a.j8("74", "no_material")
    b("8b5714 895130 85d2"); a.j8("74", "hide")
    b("836108fe"); a.j8("eb", "no_material")
    a.label("hide"); b("83490801")
    a.label("no_material"); b("8b10")
    absop("833d",data_va+POPULATED); b("00"); a.j8("74", "seed")
    b("3b5720"); a.j8("74", "seed")
    b("c74728"+_u(0x3E3851EC))  # 0.18 seconds
    a.label("seed"); b("895720 c706"+_u(WHITE))
    b("8b4728 85c0"); a.j8("7e", "side_done")
    b("c706"+_u(ACCENT)+" d94728 d8a42414020000 d95f28")
    a.label("side_done"); b("c3")

    a.label("setup_side")
    b("56 52 50")  # context and side letter survive the native material lookup
    absop("8b35", 0xA95528); a.call(0xFBC70)
    b("5a 5e 8947f4")
    call("load_side")
    b("8b4ff4 85c9"); a.j8("74", "setup_side_end")
    b("8b07 894130 85c0"); a.j8("74", "setup_hide")
    b("836108fe c3")
    a.label("setup_hide"); b("83490801")
    a.label("setup_side_end"); b("c3")

    # Preserve the native score formatter (including its score-state rules), then
    # translate its UTF-16 digits into the private large-digit cells, U+0080 through U+0089.
    for side, callback in ((0, 0xFC050), (1, 0xFC070)):
        a.label(f"score_text{side}"); b("b8" + _u(callback))
        if side == 0: a.j8("eb", "score_common")
    a.label("score_common"); b("51 ffd0 59")
    a.label("score_loop"); b("66833900"); a.j8("74", "score_end")
    b("66830150 4141"); a.j8("eb", "score_loop")
    a.label("score_end"); b("c3")

    # One HUD-scoped TXTR lookup for this side at setup. The UTF-16 name is built
    # on the stack. Validate two numeric asset-code chars and reject created-team kinds.
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
    a.label("neutral")
    b("8d0424 50 ba54585452 b9" + _u(HUD_COLLECTION_NAME))
    a.call(0x449E0)
    # Retry neutral for a missing team texture, retaining orientation.
    b("85c0"); jump("0f85", "texture_found")
    b("817c24042d002d00"); jump("0f84", "texture_found")
    b("c74424042d002d00 8d0424 50 ba54585452 b9" + _u(HUD_COLLECTION_NAME))
    a.call(0x449E0)
    a.label("texture_found"); b("8907 83c410 c3")
    a.label("play_text")
    b("51"); a.call(0xFBE30); b("59 66833930")
    a.j8("75", "play_text_done")
    b("8b4102 8901")  # leading 0 in 04 becomes a single 4, including its NUL
    a.label("play_text_done"); b("c3")

    # Timeout marks: the team-name callbacks receive ECX = the caller's UTF-16
    # buffer. Write "~ ~ ~" trimmed to the remaining timeouts (0..3), then NUL.
    # One shared writer; each side's callback entry loads its score object (EAX) and joins it.
    a.label("dash_text0"); absop("a1", SCORE_POINTERS[0]); a.j8("eb", "dash_common")
    a.label("dash_text1"); absop("a1", SCORE_POINTERS[1])
    a.label("dash_common")
    b("31d2 85c0"); a.j8("74", "dash_write")
    b("8b5004 83fa03"); a.j8("76", "dash_write")
    b("31d2")
    a.label("dash_write")
    b("85d2"); a.j8("74", "dash_end")
    a.label("dash_loop")
    b("66c7017e00 83c102 4a"); a.j8("74", "dash_end")
    b("66c7012000 83c102"); a.j8("eb", "dash_loop")
    a.label("dash_end"); b("66c7010000 c3")
    # The plate colours packed as three bytes (B, G, R) per asset code; the lookup reads a
    # dword at 3 * code and forces the alpha byte, so the table costs 120 bytes, not 160.
    a.label("plate_table")
    for word in exact.plate_table():
        b(_u(word)[:6])
    b("00")  # the final entry's dword read stays inside the owner's bytes
    # Shorten only local branches whose whole displacement already fits.
    # Every target and external call is reassembled after each shrinking pass.
    while True:
        a.assemble()
        changed, offset = False, 0
        for index, item in enumerate(a.items):
            size = a._size(item)
            if isinstance(item, tuple) and item[0] == "j32":
                opcode, label = item[1:]
                delta = a.labels[label] - offset - size
                short = (b"\xeb" if opcode == b"\xe9" else
                         bytes((opcode[1] - 0x10,)) if len(opcode) == 2 and opcode[0] == 0x0f else None)
                if short is not None and -128 <= delta <= 127:
                    a.items[index] = ("j8", short, label)
                    changed = True
            offset += size
        if not changed: break
    content = bytearray(a.assemble())
    for side in (0, 1):
        struct.pack_into("<I", content, a.labels[f"dash_callback{side}"] + 6, code_va + a.labels[f"dash_text{side}"])
    for side in (0, 1):
        struct.pack_into("<I", content, a.labels[f"score_callback{side}"] + 6, code_va + a.labels[f"score_text{side}"])
    struct.pack_into("<I", content, a.labels["play_callback"] + 6, code_va + a.labels["play_text"])
    struct.pack_into("<I", content, a.labels["plate_table_ref"], code_va + a.labels["plate_table"])
    if len(content) > CODE_SIZE:
        raise ValueError(f"scorebug code exceeds its named allocation: {len(content)}")
    return bytes(content).ljust(CODE_SIZE, b"\xcc"), {k: code_va + v for k, v in a.labels.items()}


def sites(payload):
    owned = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    space._require(set(owned) == {"code", "data"}, "missing scorebug allocations; reserve the owner union first")
    for kind, size, align in (("code", CODE_SIZE, 16), ("data", DATA_SIZE, 16)):
        space._require((owned[kind]["size"], owned[kind]["align"]) == (size, align), "foreign scorebug allocation")
    return owned["code"], owned["data"]


def hook_bytes(name, labels):
    va, original = HOOKS[name]
    return b"\xe8" + struct.pack("<i", labels[name] - va - 5)


def override_edits():
    """(va, static bytes, owner bytes, label) for the text-record overrides and literals."""
    from . import nfl2k5_scorebug_exact as exact
    static = {va: new for va, _old, new, _ in exact.xbe_specs(scene.xbe_specs(baseline_v8=True))}
    rows = [(va, static.get(va), struct.pack("<I", value), "mnf text record") for va, value in STATIC_OVERRIDES.items()]
    for va, (old, new) in LITERALS.items():
        rows.append((va, (old + "\0").encode("utf-16le"), (new + "\0").encode("utf-16le"), "mnf literal"))
    return rows


def _abi_valid(payload):
    from .nfl2k5_scorebug_resources import RUNTIME_ABI_GUARDS
    for va, callback in zip(CITY_CALLBACKS, (0xfc010, 0xfc030)):
        off = scene.layout.sbpos.va_to_off(payload, va)
        if payload[off:off+4] != struct.pack('<I', callback):
            return False
    normal = [(va, old) for va, old, _, _ in scene.xbe_specs()]
    normal += list(HOOKS.values())
    for va, size, sha in (*RUNTIME_ABI_GUARDS, *LOOKUP_GUARDS):
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
        if code_state == "applied" and scene.xbe_status(payload, scorebug_folder=None) != "applied":
            return "foreign"
        if code_state == "applied":
            for va, _old, new, _ in override_edits():
                off = scene.layout.sbpos.va_to_off(payload, va)
                if payload[off:off + len(new)] != new:
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
    # Build-time descriptor defaults on top of the static layer: the repurposed
    # team-name records, the capsule text colours and the GOAL literal.
    for va, _old, new, label in override_edits():
        off = scene.layout.sbpos.va_to_off(installed, va)
        edits.append(dict(label=label, va=hex(va), size=len(new), before=bytes(buf[off:off+len(new)]).hex(), after=new.hex()))
        buf[off:off+len(new)] = new
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    result = bytes(buf)
    space._require(status(result) == "applied", "scorebug runtime postcondition failed")
    return result, dict(status="applied", experimental=True, runtime_witnessed=False,
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                        code_va=hex(code["va"]), data_va=hex(data["va"]), edits=edits,
                        binding_collection="GAMEDATA", binding_revision=REVISION,
                        allocation=ar, installation=ir, scorebug=sr,
                        reservations=space.reservations(result),
                        requires_resources="scorebug-mnf-2026-v3; XBE alone does not install art or fonts")
