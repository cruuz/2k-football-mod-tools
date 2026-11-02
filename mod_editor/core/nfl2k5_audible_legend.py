"""At-line audible panel: an on-screen button legend, and the panel lifted clear of the bottom score bar (USA retail).

Players asked what the buttons do on the audible panel at the line (b780 r3: "In the In-Game Audibles menu you get three
buttons. X, A, and B.... L1, L2, L3, R1, R2, R3, Even Y ain't doing shit"), and on SOFTDRINK builds the 2026 score bar
covers the bottom of that panel (its play name and the bottom of the diagram). This owner fixes both with the game's own
HUD text and button icons. Nothing it adds reads or changes game state; it only draws and moves pixels.

How the panel works (PROVED, retail default.xbe; unchanged in the shipped v0.8 executable)
---------------------------------------------------------------------------------------------
* Two panel records at 0xBA3178 (0x4C bytes each; record 0 is the team with the ball [0xE60280], record 1 the defense
  [0xE60284]): +0 open, +4 controller (0xFF = opened by the CPU), +5 selection, +6 entry count (3 or 5), +8 0 = AUDIBLE,
  1 = NO HUDDLE, +0x14 the pane object built by 0xABED0.
* 0xFF130 (called once by the in-game HUD setup 0x64710, at 0x648C5) builds both panes from the SCNE resource
  ``playcallframe_audible`` (gamedata.iff chunk 85). Each pane's root node (``a_o`` / ``a_d``, identity transform in the
  resource) is placed by 0xAA440, which adds (320, 240, 700) to its translation: the root's y word is node+0x54 = 240.0.
  The diagram corners, the play and receiver labels, the button icon and the AUDIBLE header are all drawn from the world
  matrices of that root's joints (0x145230 / 0x144BA0 / 0xFF360), so moving the root moves the whole panel.
* 0xFF360 draws every open panel each frame. Its last draw is the header word ("audible" / "no huddle") with the native
  text object at [esp+0x30]: font slot 6, centred, colour 0xFFC0C0C0, drop shadow, at the play-name joint's x and
  y - 165 (record 0) or y - 145 (record 1), by ``call 0xF1C70`` at 0xFF60B. At that call ESI is the record offset (0 or
  0x4C) and EDI the record's team.
* The native text renderer draws inline button icons for ``|TAG|`` names (table 0xA91100, atlas ``buttonicons``). On
  Xbox: CROSS = A, CIRCLE = B, SQUARE = X, TRIANGLE = Y, L1 / R1 = the L and R triggers, L2 = White, R2 = Black,
  L3 / R3 = the stick clicks, DPAD = the D-pad. The panel itself already uses them for its own button icons.
* What the buttons do while the panel is open (control map 0xA99EC0 context 2 in all three controller setups, handler
  table 0xAABEF8, and the game's own manual pages in vc_53450030/0): left/right on the D-pad or left stick cycle the
  audibles (0xFEF70), X / A / B (and L / R on five-entry panels) call one (0xFEFA0), Y closes the panel, Black flips the
  play (0x18FAB0), R3 flips the routes on offense and the assignments on defense (0x18FA60), White calls the play from the
  huddle again (0x18F950, the manual's "Last Play" bluff; on NO HUDDLE it first clears both flips). Black and R3 do
  nothing in Basic Training (game mode 3), on a NO HUDDLE panel or in a kicking formation (0x18FA20), and only flip an
  offensive or defensive play (0x18DCB0); White does nothing in Basic Training. L and R do nothing on the three-entry
  offense panel in retail; the slide-call owner (b780 p1-slide) gives them the protection slide.

What this owner adds (two hooks, one late code allocation)
-----------------------------------------------------------
* ``lift`` (0x648C5, ``call 0xFF130`` -> owner): after the native setup, each pane root whose y word is exactly 240.0
  (the value 0xAA440 just wrote) gets 240.0 - LIFT. The panel moves up LIFT units, clear of the bottom score bar (its top
  tab is HUD y 390.8; the panel's bottom edge is y 435 in retail, 381 lifted). Applied whenever the build has the bar.
* ``legend`` (0xFF60B, ``call 0xF1C70`` -> owner): the native header is drawn exactly as before, then up to three rows
  of button legend above the panel with the same text object (font slot 3, line height 14, left aligned, light grey,
  drop shadow), anchored to the header position, only for a panel a person opened (controller byte != 0xFF). The rows
  follow the native gates above, so the legend never names a button that does nothing at that moment.
* The 2026 score bar's own owner and every other pre-play screen stay untouched.

Allocation: one late owner (appended at the end of ``nfl2k5_xbe_space.LATE_OWNERS``), CODE_SIZE bytes of code holding
the two entry points, the row tables and the UTF-16 strings. No mutable state. Applied by ``mod_build`` after the other
late owners; the release build regenerates the cave reservations.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_audible_legend"
CODE_SIZE = 1280
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)

# --- native addresses (PROVED, retail) -------------------------------------------------------------------------------
PANEL_INIT = 0xFF130            # builds both panes (only caller: 0x64710 at LIFT_SITE)
TEXT_DRAW = 0xF1C70             # fastcall (ecx = text object, edx = UTF-16 string); |TAG| icons inline
FONT_FOR_SLOT = 0xEF850         # ecx = slot -> font object ([0xA90ECC + 4 * slot])
TEXT_SET_FONT = 0x469B0         # ecx = text, edx = font (also takes the font's line height)
TEXT_SET_LINE_HEIGHT = 0x469E0  # ecx = text, [esp+4] = float; ret 4 (icons are 1.5 x the line height)
TEXT_SET_ALIGN = 0x46A00        # ecx = text, edx = 1 left / 2 right / 3 centred
TEXT_SET_COLOUR = 0x46B50       # ecx = text, edx = ARGB
TEXT_SET_POSITION = 0x46A70     # ecx = text, [esp+4..12] = x, y, z (floats); ret 0xC
PANEL_RECORDS = 0xBA3178        # two 0x4C-byte records
PANE_ROOTS = (0xBA318C, 0xBA31D8)   # record 0 / 1 pane object +0 = root node (0xABED0 stores 0xAA440's result)
ROOT_Y_OFFSET = 0x54            # node + 0x20 local matrix, + 0x34 translation y (0xAA440: fadd [0x4F0318])
POSSESSION_TEAM = 0xE60280      # team with the ball (record 0's team)
GAME_MODE = 0xE5FF80            # 0..2 practice, 3 Basic Training, 4 Quick Game, 5..7 league, 8 Anniversary

LIFT_SITE = ("audible_panel_lift", 0x000648C5, bytes.fromhex("e866a80900"))      # call 0xFF130 in 0x64710
LEGEND_SITE = ("audible_panel_legend", 0x000FF60B, bytes.fromhex("e86026ffff"))  # call 0xF1C70 in 0xFF360

# --- design -----------------------------------------------------------------------------------------------------------
LIFT = 54.0                     # HUD units; the same lift the 2026 bar gives the play-call screen
ROOT_Y = 240.0                  # 0xAA440's settled root y ([0x4F0318]); only this exact value is lifted
FONT_SLOT = 3                   # font4: the narrowest retail font that reads at this size
LINE_HEIGHT = 14.0              # button icons 21 units tall (1.5 x), rows 21 units apart
COLOUR = 0xFFE6E6E6             # light grey like the panel's own header (0xFFC0C0C0), a little brighter over grass
ROW_DY = (-20.5, -41.5, -62.5)  # row tops relative to the header text position; row 1 ends one unit above it
COLUMN_DX = (-110.0, 10.0)      # left-aligned columns relative to the header x (panel left edge = header x - 111)
RIGHT_SIDE_X = 320.0            # a header right of the screen centre (the defense's panel) shifts the block left
RIGHT_SHIFT = -23.0             # so the block's right edge sits as far right of the header as the left edge sits left

BROWSE, BACK = "|DPAD| BROWSE", "|TRIANGLE| BACK"
FLIP_PLAY, FLIP_ROUTES, FLIP = "|R2| FLIP PLAY", "|R3| FLIP ROUTES", "|R2| FLIP"
LAST_PLAY, SLIDE = "|L2| LAST PLAY", "|L1||R1| SLIDE"
SLIDE_LEFT, SLIDE_RIGHT = "|L1| SLIDE LEFT", "|R1| SLIDE RIGHT"   # the active call, lit (with the slide-call owner)
HIGHLIGHT = 0xFFFFD040          # warm yellow, like the panel's own receiver name
COND_ALWAYS, COND_ROUTES, COND_SLIDE = 0, 1, 2
# b780 p1-slide's published call state (its 16-byte "data" allocation): +0 the offense team that called it
# ([0xE60280] at the press), +4 the play log counter 0xE53804 at the press, +8 byte 0 none / 1 left / 2 right.
# A call is active for the panel on screen when +8 != 0, +0 == [0xE60280] and +4 == [0xE53804].
SLIDE_OWNER = "nfl2k5_protection_calls"
PLAY_LOG = 0xE53804

# (row 1..3, column 0..1, string, condition). Row 1 is nearest the panel.
TABLES = {
    "offense": ((1, 0, BROWSE, COND_ALWAYS), (1, 1, BACK, COND_ALWAYS),
                (2, 0, FLIP_PLAY, COND_ALWAYS), (2, 1, FLIP_ROUTES, COND_ROUTES),
                (3, 0, LAST_PLAY, COND_ALWAYS)),
    "defense": ((1, 0, BROWSE, COND_ALWAYS), (1, 1, BACK, COND_ALWAYS),
                (2, 0, FLIP, COND_ALWAYS), (2, 1, LAST_PLAY, COND_ALWAYS)),
    "reduced": ((1, 0, BROWSE, COND_ALWAYS), (1, 1, BACK, COND_ALWAYS),
                (2, 0, LAST_PLAY, COND_ALWAYS)),
    "basic": ((1, 0, BROWSE, COND_ALWAYS), (1, 1, BACK, COND_ALWAYS)),
}
SLIDE_ROW = (3, 1, SLIDE, COND_ALWAYS)   # offense only, and only when the slide-call owner is in the build
TABLE_ORDER = ("offense", "defense", "reduced", "basic")

BUILD_CAPTION = "Audible panel: on-screen button legend"
HELP_TEXT = ("At the line, the audible panel shows what its other buttons do: browse, back, flip play, flip routes, "
             "last play (and the line slide when protection calls are on). Rows appear only when that button works.")
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError)

# Retail spans this owner relies on, pinned (SHA-256 of the retail bytes with this owner's own hook normalized).
GUARDS = (
    (0x000648B0, 0x30, "9d11d875a9ff43aede9637ad80995882abf4a7861b6e6c4f62fa1b38a502f96b", "HUD setup around the panel init"),
    (0x000FF130, 0x208, "bce3dea3caaaac418023aa54e8989e0111ed0f21331ea4bb23637ac85e3678f1", "panel pane setup"),
    (0x000FF360, 0x2F0, "974741dfc24e43de98d816541cbeab188d986f5a3833f2eca56a4c03d8a607e9", "panel draw"),
    (0x000AA440, 0x4B, "599d1697be97636d999ccf271f115de0cae90e36f37414dfcc24fd19523a72c6", "pane root placement"),
    (0x004F0318, 0x4, "7860020e90116183228640760ff7502f4df0088992b456e3f0d7b44c9950db7e", "root y 240.0"),
    (0x00046920, 0x192, "0345180e1baa3f38cb3ec120b031d5b19656251cb57c553ca168f952b2504180", "text object setters"),
    (0x00046B50, 0x14, "ecb8404406a92e7668cf47c3de06f763e6c46532e67474013cd81de23266dff2", "text colour / shadow"),
    (0x000F1C70, 0x10, "65f6ef40cd75472c38615e4ecf846fc3b3f8bbf6744062b29f2befcd66ade68f", "text draw"),
    (0x000EF850, 0x8, "2b749cc28858f48edd6c85faf49916486d941f55a861696947a0ab14cb1946e4", "font slots"),
    (0x000FEE40, 0x24, "cf19df1a00f1e31039a9c244ad09ad1be5440c449895a07083dee7f739f384a5", "kicking-formation test"),
    (0x00A91100, 0x828, "516140ce38727431a44187fe049a18f3b0921b46b2152b2a79086d3e2057b96d", "button icon tags"),
)


class AudibleLegendError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise AudibleLegendError(message)


def _f(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def _u(value: int) -> str:
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def tables(slide: bool, indicator: bool = False) -> dict:
    out = {name: list(rows) for name, rows in TABLES.items()}
    if slide:
        row, col, text, _cond = SLIDE_ROW
        out["offense"].append((row, col, text, COND_SLIDE if indicator else COND_ALWAYS))
    return out


def slide_state_va(payload: bytes) -> int | None:
    """VA of the slide-call owner's 16-byte call state in this executable's allocator layout, or None."""
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == SLIDE_OWNER and r["kind"] == "data"]
    return rows[0]["va"] if len(rows) == 1 and rows[0]["size"] >= 16 else None


def _emit(code_va: int, lift: bool, legend: bool, slide: bool, data: Mapping[str, int], state_va: int | None = None):
    """One assembly pass; ``data`` maps data labels to VAs (zeros on the sizing pass)."""
    a = _Asm(code_va)
    if lift:
        a.label("lift")
        a.call(PANEL_INIT)                       # the native setup, exactly once, original ABI (no arguments)
        a.b("9c 50")                             # pushfd ; push eax
        for root in PANE_ROOTS:
            a.b("a1" + _u(root))                 # mov eax, [pane root]
            a.j32("e8", "lift_root")
        a.b("58 9d c3")                          # pop eax ; popfd ; ret
        a.label("lift_root")
        a.b("85c0")
        a.j8("74", "lift_done")                  # no pane
        a.b("817854" + _u(_f(ROOT_Y)))           # cmp dword [eax+0x54], 240.0
        a.j8("75", "lift_done")                  # anything else is not ours to move
        a.b("c74054" + _u(_f(ROOT_Y - LIFT)))    # mov dword [eax+0x54], 240.0 - LIFT
        a.label("lift_done")
        a.b("c3")
    if legend:
        a.label("legend")
        a.b("9c 60")                             # pushfd ; pushad
        a.b("83ec18")                            # sub esp, 24: the 16-byte alignment of 0xFF360's own call site
        a.b("c744240c00000000")                  # routes flag = 0
        # Anchor = the header's x, y, z as 0xFF360 placed it; the native draw advances y by a line afterwards.
        a.b("8b4110 890424 8b4114 89442404 8b4118 89442408")
        a.call(TEXT_DRAW)                        # the native header; ECX/EDX are still 0xFF360's
        a.b("8b6c2430")                          # mov ebp, [esp+0x30]  (entry ECX: the text object)
        a.b("80be" + _u(PANEL_RECORDS + 4) + "ff")   # cmp byte [esi+record+4], 0xFF  (opened by the CPU)
        a.j32("0f84", "legend_done")
        a.b("bb" + _u(data["t_basic"]))
        a.b("833d" + _u(GAME_MODE) + "03")       # Basic Training: White, Black and R3 do nothing
        a.j32("0f84", "chosen")
        a.b("bb" + _u(data["t_reduced"]))
        a.b("83be" + _u(PANEL_RECORDS + 8) + "00")   # NO HUDDLE panel: no flips
        a.j32("0f85", "chosen")
        a.b("8b470c 85c0")                       # mov eax, [edi+0xC] (team context) ; test
        a.j32("0f84", "chosen")
        a.b("8b5008 85d2")                       # mov edx, [eax+8] (formation) ; test
        a.j32("0f84", "chosen")
        a.b("8b5204 c1ea08 83e23f 83ea08 83fa05")  # (flags >> 8) & 0x3F in 8..13: a kicking formation (0xFEE40)
        a.j32("0f86", "chosen")
        a.b("8b480c 85c9")                       # mov ecx, [eax+0xC] (current play) ; test
        a.j32("0f84", "chosen")
        a.b("8b5104 c1ea06 83e207 83fa01")       # play side (flags >> 6) & 7: 0 offense, 1 defense (0x18DCB0)
        a.j32("0f87", "chosen")
        a.b("bb" + _u(data["t_defense"]))
        a.b("3b3d" + _u(POSSESSION_TEAM))
        a.j32("0f85", "chosen")
        a.b("bb" + _u(data["t_offense"]))
        a.b("f6410510")                          # current play flags & 0x1000: no route flip (0x18DCB0)
        a.j8("75", "chosen")
        a.b("8b5010 85d2")                       # [ctx+0x10] flags & 0x1000: no route flip (0x18FA60)
        a.j8("74", "routes_ok")
        a.b("f6420510")
        a.j8("75", "chosen")
        a.label("routes_ok")
        a.b("c744240c01000000")                  # routes flag = 1
        a.label("chosen")
        a.b("b9" + _u(FONT_SLOT))
        a.call(FONT_FOR_SLOT)
        a.b("8bd0 8bcd")                         # mov edx, eax ; mov ecx, ebp
        a.call(TEXT_SET_FONT)
        a.b("68" + _u(_f(LINE_HEIGHT)) + "8bcd")
        a.call(TEXT_SET_LINE_HEIGHT)
        a.b("ba01000000 8bcd")                   # left aligned
        a.call(TEXT_SET_ALIGN)
        a.b("813c24" + _u(_f(RIGHT_SIDE_X)))     # positive floats order like signed integers
        a.j8("7c", "anchored")
        a.b("d90424 d805" + _u(data["right_shift"]) + "d91c24")
        a.label("anchored")
        a.b("8bf3")                              # mov esi, ebx (row table)
        a.label("item")
        a.b("8b7e08 85ff")                       # edi = this item's string (0 ends the table)
        a.j32("0f84", "legend_done")
        a.b("bb" + _u(COLOUR))                   # ebx = this item's colour
        a.b("8b4e0c 85c9")                       # condition
        a.j8("74", "draw")
        a.b("49")                                # COND_ROUTES (1) -> 0
        if state_va:
            a.j8("75", "slide")
        a.b("837c240c00")                        # routes flag
        a.j8("74", "next")
        a.j8("eb", "draw")
        if state_va:
            # COND_SLIDE: the call this offense made on this play lights its own item; otherwise the static row.
            a.label("slide")
            a.b("0fb60d" + _u(state_va + 8) + "85c9")       # movzx ecx, byte [state+8] ; test
            a.j8("74", "draw")
            a.b("a1" + _u(state_va) + "3b05" + _u(POSSESSION_TEAM))
            a.j8("75", "draw")
            a.b("a1" + _u(state_va + 4) + "3b05" + _u(PLAY_LOG))
            a.j8("75", "draw")
            a.b("83f901")
            a.j8("75", "slide_right")
            a.b("bf" + _u(data["s_slide_left"]))
            a.j8("eb", "slide_lit")
            a.label("slide_right")
            a.b("83f902")
            a.j8("75", "draw")
            a.b("bf" + _u(data["s_slide_right"]))
            a.label("slide_lit")
            a.b("bb" + _u(HIGHLIGHT))
        a.label("draw")
        a.b("8bd3 8bcd")                         # colour
        a.call(TEXT_SET_COLOUR)
        a.b("ff742408 d9442408 d84604 83ec04 d91c24")   # push z ; y + dy
        a.b("d9442408 d806 83ec04 d91c24 8bcd")         # x + dx ; ecx = text
        a.call(TEXT_SET_POSITION)
        a.b("8bd7 8bcd")                         # edx = string
        a.call(TEXT_DRAW)
        a.label("next")
        a.b("83c610")
        a.j32("e9", "item")
        a.label("legend_done")
        a.b("83c418 61 9d c3")                   # add esp, 24 ; popad ; popfd ; ret
    return a


def _data_blob(base_va: int, slide: bool, indicator: bool = False):
    """Row tables (16-byte items: dx, dy, string VA, condition; string 0 ends a table), the shift and the strings."""
    rows = tables(slide, indicator)
    strings = []
    for name in TABLE_ORDER:
        for _row, _col, text, _cond in rows[name]:
            if text not in strings:
                strings.append(text)
    if indicator:
        strings += [SLIDE_LEFT, SLIDE_RIGHT]
    table_bytes = sum(16 * (len(rows[name]) + 1) for name in TABLE_ORDER)
    labels, at = {}, base_va
    for name in TABLE_ORDER:
        labels["t_" + name] = at
        at += 16 * (len(rows[name]) + 1)
    labels["right_shift"] = at
    at += 4
    text_va = {}
    for text in strings:
        text_va[text] = at
        at += 2 * (len(text) + 1)
    blob = bytearray()
    for name in TABLE_ORDER:
        for row, col, text, cond in rows[name]:
            blob += struct.pack("<ffII", COLUMN_DX[col], ROW_DY[row - 1], text_va[text], cond)
        blob += bytes(16)
    blob += struct.pack("<f", RIGHT_SHIFT)
    for text in strings:
        blob += (text + "\0").encode("utf-16le")
    require(len(blob) == at - base_va and table_bytes + 4 + sum(2 * (len(t) + 1) for t in strings) == len(blob),
            "legend data layout")
    if indicator:
        labels["s_slide_left"], labels["s_slide_right"] = text_va[SLIDE_LEFT], text_va[SLIDE_RIGHT]
    return bytes(blob), labels


def code_for(code_va: int, *, lift: bool = True, legend: bool = True, slide: bool = False,
             slide_state: int | None = None) -> tuple[bytes, dict]:
    """(CODE_SIZE bytes, entry labels). Code first, then 4-aligned data, int3 padding.

    ``slide_state`` is the slide-call owner's call-state VA (``slide_state_va``); with it the slide item shows the
    active call, lit, instead of the static row."""
    require(lift or legend, "nothing to install")
    require(legend or not slide, "the slide row belongs to the legend")
    require(slide or slide_state is None, "a call state without the slide row")
    indicator = slide_state is not None
    zero = {k: 0 for k in ("t_offense", "t_defense", "t_reduced", "t_basic", "right_shift", "s_slide_left",
                           "s_slide_right")}
    sizing = _emit(code_va, lift, legend, slide, zero, slide_state)
    code = sizing.assemble()
    data_va = code_va + ((len(code) + 3) & ~3)
    blob, data = _data_blob(data_va, slide, indicator) if legend else (b"", {})
    final = _emit(code_va, lift, legend, slide, data, slide_state) if legend else sizing
    code = final.assemble()
    require(code_va + len(code) <= data_va, "legend code grew between passes")
    content = code + (b"\xcc" * (data_va - code_va - len(code)) + blob if legend else b"")
    require(len(content) <= CODE_SIZE, f"audible legend exceeds its allocation: {len(content)}")
    labels = {k: code_va + v for k, v in final.labels.items()}
    labels.update(data)
    return content.ljust(CODE_SIZE, b"\xcc"), labels


def sites(labels: Mapping[str, int], *, lift: bool, legend: bool) -> list[tuple[str, int, bytes, bytes]]:
    rows = []
    for wanted, (name, va, before), entry in ((lift, LIFT_SITE, "lift"), (legend, LEGEND_SITE, "legend")):
        if wanted:
            rows.append((name, va, before, b"\xe8" + struct.pack("<i", labels[entry] - va - 5)))
    return rows


def allocation(payload: bytes) -> dict:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "missing or foreign audible-legend allocation")
    return rows[0]


def guards_valid(payload: bytes) -> bool:
    image = XbeImage(payload)
    normal = [(LIFT_SITE[1], LIFT_SITE[2]), (LEGEND_SITE[1], LEGEND_SITE[2])]
    for start, size, digest, _label in GUARDS:
        body = bytearray(image.read(start, size))
        for va, old in normal:
            if start <= va and va + len(old) <= start + size and body[va - start] == 0xE8:
                body[va - start:va - start + len(old)] = old
        if hashlib.sha256(body).hexdigest() != digest:
            return False
    return True


VARIANTS = tuple((lift, legend, slide) for lift in (False, True) for legend in (False, True)
                 for slide in (False, True) if (lift or legend) and (legend or not slide))


def _recognize(payload: bytes):
    """(state, variant, allocation, lit slide call): state retail | applied; raises on anything foreign or mixed."""
    require(guards_valid(payload), "the audible panel code is not the retail code this owner was built for")
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    site_bytes = {name: image.read(va, len(before)) for name, va, before in (LIFT_SITE, LEGEND_SITE)}
    retail_sites = {LIFT_SITE[0]: site_bytes[LIFT_SITE[0]] == LIFT_SITE[2],
                    LEGEND_SITE[0]: site_bytes[LEGEND_SITE[0]] == LEGEND_SITE[2]}
    if not present:
        require(all(retail_sites.values()), "an audible panel site changed without an allocation")
        return "retail", None, None, False
    owned = allocation(payload)
    have = image.read(owned["va"], CODE_SIZE)
    if have == b"\xcc" * CODE_SIZE:
        require(all(retail_sites.values()), "an audible panel site changed without its code")
        return "retail", None, owned, False
    state_va = slide_state_va(payload)
    for variant in VARIANTS:
        lift, legend, slide = variant
        # A slide row built with the slide-call owner's state lights the active call; one built before that owner was
        # placed (an owner appended later by hand) is the static row. Both are whole, recognized installs.
        for state in ((state_va, None) if slide and state_va is not None else (None,)):
            content, labels = code_for(owned["va"], lift=lift, legend=legend, slide=slide, slide_state=state)
            if have != content:
                continue
            expected = {name: before for name, _va, before in (LIFT_SITE, LEGEND_SITE)}
            expected.update({name: after for name, _va, _before, after in sites(labels, lift=lift, legend=legend)})
            require(site_bytes == expected, "mixed audible panel installation")
            return "applied", variant, owned, state is not None
    raise AudibleLegendError("foreign audible-legend code")


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)[0]
    except _ERRORS:
        return "foreign"


def read_settings(payload: bytes) -> dict:
    try:
        state, variant, _owned, lit = _recognize(payload)
    except _ERRORS:
        return {"status": "foreign", "audible_panel_lift": False, "audible_legend": False, "audible_legend_slide": False,
                "slide_call_shown": False}
    lift, legend, slide = variant or (False, False, False)
    return {"status": state, "audible_panel_lift": lift, "audible_legend": legend, "audible_legend_slide": slide,
            "slide_call_shown": bool(lit)}


def reservations(payload: bytes | None = None) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER] if payload is not None else []
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis=f"pinned call site ({name}); not a cave") for name, va, before in (LIFT_SITE, LEGEND_SITE)]


def apply(payload: bytes, *, lift: bool = True, legend: bool = True, slide: bool = False) -> tuple[bytes, Mapping[str, object]]:
    """Install the lift and/or the legend. Idempotent for the same choices; a different choice needs a clean build."""
    require(lift or legend, "choose the panel lift, the legend or both")
    require(legend or not slide, "the slide row belongs to the legend")
    state, variant, owned, _lit = _recognize(payload)
    wanted = (bool(lift), bool(legend), bool(slide))
    common = {"owner": OWNER, "owner_bytes": CODE_SIZE, "lift_units": LIFT, "experimental": True,
              "audible_panel_lift": wanted[0], "audible_legend": wanted[1], "audible_legend_slide": wanted[2]}
    if state == "applied":
        require(variant == wanted, f"this executable already carries a different audible panel choice {variant}; "
                                   "rebuild from your retail dump")
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if owned is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        owned = allocation(payload)
    state_va = slide_state_va(payload) if wanted[2] else None
    content, labels = code_for(owned["va"], lift=wanted[0], legend=wanted[1], slide=wanted[2], slide_state=state_va)
    installed, code_receipt = space.install_code(payload, OWNER, content)
    result, site_receipt = rdata.apply(installed, sites(labels, lift=wanted[0], legend=wanted[1]), OWNER)
    require(status(result) == "applied" and _recognize(result)[1] == wanted, "audible legend postcondition failed")
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(owned["va"]), "entries": {k: hex(v) for k, v in labels.items()
                                                             if k in ("lift", "legend")},
                    "slide_call_state": hex(state_va) if state_va else None,
                    "changed_bytes": sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before)),
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def _read_source(path: str) -> bytes:
    """default.xbe bytes from an extracted executable or a disc image."""
    from pathlib import Path
    source = Path(path)
    if source.suffix.lower() == ".xbe":
        return source.read_bytes()
    from .nfl2k5_espn25_rosters import read_xbe
    return read_xbe(str(source))


def main(argv=None) -> int:
    """``status <source>`` prints the owner state; ``apply <in.xbe> <out.xbe> [--no-lift] [--no-legend] [--slide]``."""
    import argparse
    import json
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_audible_legend", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status", help="read the owner state of a default.xbe or a disc image")
    st.add_argument("source")
    ap = sub.add_parser("apply", help="install the lift and/or the legend into a copy of default.xbe")
    ap.add_argument("source"); ap.add_argument("output")
    ap.add_argument("--no-lift", action="store_true"); ap.add_argument("--no-legend", action="store_true")
    ap.add_argument("--slide", action="store_true", help="show the L/R slide row (with the slide-call owner)")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(read_settings(_read_source(args.source)), indent=2))
        return 0
    from pathlib import Path
    out = Path(args.output)
    if out.exists() or out.resolve() == Path(args.source).resolve():
        parser.error("the output must be a new file")
    result, receipt = apply(_read_source(args.source), lift=not args.no_lift, legend=not args.no_legend, slide=args.slide)
    with open(out, "xb") as stream:
        stream.write(result)
    print(json.dumps({k: v for k, v in receipt.items() if k != "code_install"}, indent=2, default=str))
    return 0


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "LIFT", "LIFT_SITE", "LEGEND_SITE", "TABLES", "SLIDE_ROW", "BUILD_CAPTION",
           "HELP_TEXT", "AudibleLegendError", "tables", "code_for", "sites", "allocation", "guards_valid", "status",
           "read_settings", "reservations", "apply"]


if __name__ == "__main__":
    raise SystemExit(main())
