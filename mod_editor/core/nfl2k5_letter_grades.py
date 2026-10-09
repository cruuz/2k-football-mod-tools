"""Letter grades in Franchise (job F4, beta 77): player and team ratings as A+ ... F-. EXPERIMENTAL.

Noah, 2026-10-07: "in franchise, let's do something radical: take player ratings and team ratings and go
letter grades", on his "2K Player Grade System" scale: 95+ A+, 90-94 A, 85-89 B+, 80-84 B, 75-79 C+, 70-74 C,
65-69 D+, 60-64 D, 55-59 F+, 50-54 F, 0-49 F- (eleven grades; there is no A-, B-, C- or D-).

What changes (all in ``default.xbe``; display only)
---------------------------------------------------
The game shows a rating as an integer and never stores one: the player overall is computed on demand
(``0xE6660`` -> ``0x246D90`` = ``round(100 x template overall)``) and the team offense, defense and overall are
``FUN_000C4830/4860/48A0`` x 100. This patch changes only how those integers become text.

* ``%R``: the game's ``swprintf`` (``0x49F00``, entered through ``0x4A400/0x4A410``) is table driven: one handler per
  conversion character, registered from the static list at ``.rdata 0x4E6978``. The ``%n`` row (write the
  character count through a pointer: nothing in the game uses it, and the only ``%n`` bytes in the executable are
  binary noise) becomes ``%R``: it consumes an ``int`` argument and writes the grade. A text site then needs only
  a different format literal.
* Text sites (one 4-byte format-literal swap each, except the weekly prep OVERALL; the value, buffer, font and
  position are untouched):
  team select OFFENSE / DEFENSE / OVERALL (``0x31F71E``, six numbers), the Franchise Player Card overall
  (``0x3206BD``), the depth chart player panel OVERALL (``0x243605``), the contract panel ``Overall:%d``
  (``0x347419``), the weekly prep Matchups panel (``0x2AF267``, its overall branch) and the weekly prep panel OVERALL
  (``0x2B0A29``: it shares a formatting tail with an attribute, so it gets the same tail with its own literal).
* The Player Card number is not drawn with a bitmap font: ``FUN_000F1F20`` (its only caller is the card) draws it from
  the 41-mesh ``geometry_font`` glyph set and silently skips ``+`` and ``-``. Five immediates in that drawer
  (``0xF200B .. 0xF2052``) make it draw the ``minus`` and ``plus`` meshes the glyph table already names (the width
  routine that centres the text already measured them); without them A+ and A would look the same on the card.
* The Trading Block's "Add Guidelines" thresholds: the sentence ``A %s with rating %d or better.`` (``0x349CDF``)
  and the seven menu labels "90 or better" .. "30 or better" (``.string_ 0xEAD4F8``, the thresholds stay numbers):
  the labels read "A or better" .. "F or better", then "F- (40+)" and "F- (30+)" below the last named grade.
* Spreadsheet columns (every roster, trade, free agent, contract and "Select ..." list): the cell formatter
  ``FUN_00173120`` switches on a kind byte, descriptor ``+1``, with kinds 0..8. Kind 9 is new: the formatter's
  ``ja`` to the unknown-kind exit (``0x173126``) is retargeted to a stub that writes the grade for kind 9 and
  otherwise falls into the retail exit. The four player-overall columns (``OVR`` / ``RTG`` / ``Rating``, getter
  ``0xE6660``) and the three team columns (``Overall Defense`` / ``Pass Defense`` / ``Rush Defense``) get kind 9
  (descriptor flags ``5`` -> ``0x905``).

What does not change: every getter, sort key and row builder (a column sorts on the number, not on its text),
the sub-attribute columns and bars (speed, strength, ... stay numbers), the in-game Substitution list's ``RTG``
(not a Franchise screen), and any colour, font, width or position.

The band table is data: eleven ``{minimum, label}`` rows in the owner's read-only page (``bands``), so the Studio
can offer other scales; the default is Noah's. The guideline labels follow the table.

Allocation: a late owner (placed after every other owner and after K128, so adding it to a union or to a sealed
v0.5 image moves no existing address; see ``nfl2k5_xbe_space.LATE_OWNERS``): 160 RX bytes (the grade function, the
``%R`` handler, the kind 9 handler and the weekly prep stub) and 240 read-only bytes (the band table and three
format literals: ``%R``, ``Overall:%R`` and the Trading Block sentence). The two requests fit even the complete dormant owner union, whose RX tail has only 192 bytes left.

Evidence (job F4 report): static RE of the retail executable, then the real code under Unicorn: the real swprintf
with the registered ``%R``, the real spreadsheet cell formatter with kind 9, and every patched site from the
player record (a real roster) to the text. Not witnessed in game.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping, Sequence

from . import nfl2k5_letter_grades_code as assembly
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_letter_grades"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 160
RO_SIZE = 240
F4_REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "read_only", RO_SIZE, 16))
# b77-f4b: the progression screen's overall row (module nfl2k5_letter_grades_progress): one more late owner, 16 RX bytes.
PROGRESS_OWNER = "nfl2k5_letter_grades_progress"
PROGRESS_REQUESTS = ((PROGRESS_OWNER, "code", 16, 16),)
REQUESTS = F4_REQUESTS + PROGRESS_REQUESTS

UI_LABEL = "Letter grades in Franchise"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: Franchise shows a player's overall and a team's offense, defense and "
    "overall as numbers. Patch: the same numbers are shown as letter grades on Noah's 2K scale (95+ A+, 90-94 A, "
    "85-89 B+, 80-84 B, 75-79 C+, 70-74 C, 65-69 D+, 60-64 D, 55-59 F+, 50-54 F, 0-49 F-): roster, trade, free "
    "agent and contract lists, the player card, the depth chart panel, team select and the defense lists. Only the "
    "text changes: lists still sort by the number, and the individual attributes (speed, strength, ...) stay "
    "numbers. Off in the Basic preset, which keeps the 2004 numbers.")
BUILD_CAPTION = UI_LABEL

BAND_ROWS = 11
LABEL_MAX = 3
INT_MIN = -(1 << 31)
# Noah's 2K Player Grade System (reports/F4_2K_PLAYER_GRADE_SYSTEM_noah.png), highest first. The last row is the
# catch-all (minimum None): everything below the row above it.
DEFAULT_BANDS: tuple[tuple[int | None, str], ...] = (
    (95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (75, "C+"), (70, "C"),
    (65, "D+"), (60, "D"), (55, "F+"), (50, "F"), (None, "F-"),
)


class LetterGradesError(ValueError):
    """Unsupported executable, foreign or mixed installation, or an invalid band table."""


def _require(condition, message):
    if not condition:
        raise LetterGradesError(message)


# --- the band table (data) ------------------------------------------------------------------------------
_LABEL_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-*#")


def normalize_bands(bands: Sequence[tuple[int | None, str]]) -> tuple[tuple[int | None, str], ...]:
    """Validate a band table: 1..11 rows, minimums strictly descending, labels 1..3 characters, the last row open."""

    _require(isinstance(bands, (tuple, list)) and 1 <= len(bands) <= BAND_ROWS,
             f"a band table has 1 to {BAND_ROWS} rows")
    rows, previous = [], None
    for index, row in enumerate(bands):
        _require(isinstance(row, (tuple, list)) and len(row) == 2, "each band is (minimum rating, label)")
        minimum, label = row
        _require(isinstance(label, str) and 1 <= len(label) <= LABEL_MAX and set(label) <= _LABEL_CHARS,
                 f"band {index + 1}: a label is 1 to {LABEL_MAX} letters, digits, + - * or #")
        last = index == len(bands) - 1
        if last:
            _require(minimum is None, "the last band is the open one (minimum None)")
        else:
            _require(type(minimum) is int and -1000 <= minimum <= 1000, f"band {index + 1}: minimum is a whole number")
            _require(previous is None or minimum < previous, f"band {index + 1}: minimums must descend")
            previous = minimum
        rows.append((None if last else int(minimum), label))
    return tuple(rows)


def grade_for(rating: int, bands: Sequence[tuple[int | None, str]] = DEFAULT_BANDS) -> str:
    """The pure reference the cave must reproduce for every integer rating."""

    for minimum, label in normalize_bands(bands):
        if minimum is None or rating >= minimum:
            return label
    raise AssertionError("unreachable: the last band is open")


def band_table_bytes(bands: Sequence[tuple[int | None, str]] = DEFAULT_BANDS) -> bytes:
    """The 132-byte table: eleven { int32 minimum, 4 x UTF-16 } rows; short tables repeat their open row."""

    rows = list(normalize_bands(bands))
    rows += [rows[-1]] * (BAND_ROWS - len(rows))
    out = bytearray()
    for minimum, label in rows:
        out += struct.pack("<i", INT_MIN if minimum is None else minimum)
        out += label.encode("utf-16le").ljust(8, b"\0")
    return bytes(out)


def decode_band_table(table: bytes) -> tuple[tuple[int | None, str], ...]:
    _require(len(table) == BAND_ROWS * 12, "band table has the wrong size")
    rows = []
    for i in range(BAND_ROWS):
        minimum = struct.unpack_from("<i", table, i * 12)[0]
        raw = table[i * 12 + 4:i * 12 + 12]
        label = raw.decode("utf-16le").rstrip("\0")
        _require(1 <= len(label) <= LABEL_MAX and set(label) <= _LABEL_CHARS and raw[len(label) * 2:] == bytes(8 - len(label) * 2),
                 "foreign band label")
        rows.append((None if minimum == INT_MIN else minimum, label))
    while len(rows) > 1 and rows[-1] == rows[-2] and rows[-1][0] is None:
        rows.pop()
    return normalize_bands(tuple(rows))


# --- the retail anchors ---------------------------------------------------------------------------------
# swprintf conversion registration list (FUN_00049ED0 walks .rdata 0x4E6978..0x4E6A18: u16 character, u16 pad, u32 handler).
CONVERSION_ROW_VA = 0x004E69B8                       # the "%n" row
RETAIL_CONVERSION_ROW = bytes.fromhex("6e000000009b0400")   # 'n' -> handler 0x49B00 (write the count through an argument)
CONVERSION_CHAR = "R"
FN_OVERALL = 0x000E6660
FN_SWPRINTF = 0x0004A400
NAN_EXIT = 0x001732CA
KIND_BRANCH_VA = 0x00173128                          # rel32 of the formatter's "ja 0x1732CA" (0F 87 at 0x173126)
RETAIL_KIND_BRANCH = bytes.fromhex("9e010000")

# Spreadsheet column descriptors (0xB0 bytes each; +0 is the flags dword: low byte format class, byte 1 the cell kind).
# Player overall (getter 0xE6660) and team defense (getters 0x34BB60 / 80 / A0).
PLAYER_COLUMNS = (("sheet_ovr_roster", 0x00540BA8), ("sheet_rating_select", 0x0055AD00),
                  ("sheet_rtg_rosters", 0x0057DBF8), ("sheet_ovr_free_agents", 0x0058B710))
TEAM_COLUMNS = (("sheet_overall_defense", 0x0055B1D0), ("sheet_pass_defense", 0x0055B280),
                ("sheet_rush_defense", 0x0055B330))
RETAIL_FLAGS = bytes.fromhex("05000000")
GRADE_FLAGS = bytes.fromhex("05090000")             # kind 9 in byte 1

# Text sites: (label, VA of the 4-byte immediate, retail immediate, which literal).
LITERAL_SITES = (
    ("team_select_numbers", 0x0031F71E, bytes.fromhex("d42cea00"), "grade"),    # push 0xEA2CD4  L"%d"
    ("player_card_overall", 0x003206BD, bytes.fromhex("582eea00"), "grade"),    # push 0xEA2E58  L"%d"
    ("depth_chart_overall", 0x00243605, bytes.fromhex("a089e800"), "grade"),    # mov edx, 0xE889A0  L"%d"
    ("contract_panel_overall", 0x00347419, bytes.fromhex("28cfea00"), "overall"),  # mov edx, 0xEACF28  L"Overall:%d"
    ("trade_block_sentence", 0x00349CDF, bytes.fromhex("24d8ea00"), "sentence"),   # mov edx, 0xEAD824  L"A %s with rating %d or better."
    ("matchups_overall", 0x002AF267, bytes.fromhex("e867e900"), "grade"),          # mov edx, 0xE967E8  L"%d" (the overall branch only)
)

# The Trading Block "Add Guidelines" menu ("At what skill level are you looking for?"): seven static labels over the
# rating thresholds 90 .. 30 (the table at .rdata 0x557F18 pairs each label pointer with its threshold; the thresholds
# stay numbers). Each .string_ slot is 28 bytes ("NN or better" + NUL + 2 pad). The retail text is pinned.
GUIDELINE_THRESHOLDS = (90, 80, 70, 60, 50, 40, 30)
GUIDELINE_SLOTS = tuple((0x00EAD4F8 + 0x1C * i, t) for i, t in enumerate(GUIDELINE_THRESHOLDS))
GUIDELINE_SLOT_BYTES = 0x1C
MATCHUP_SITE_VA = 0x002B0A29                          # call 0xE6660 ; jmp 0x2B0A74 (the tail it shares with an attribute)
RETAIL_MATCHUP_SITE = bytes.fromhex("e8325ce3ffeb44")

# The Franchise Player Card draws its big number with FUN_000F1F20, whose only caller is the card (0x3206F6). It is a
# 41-glyph "geometry_font" drawer (glyph table .data 0xA90F10: A-Z, number_0..9, colon, apostrophe, minus, plus, dollar;
# all 41 meshes exist in the geometry_font scene) that draws only a-z, A-Z, 0-9, ':' and quote marks and silently skips
# every other character, although its width routine FUN_000EFA60 (used to centre the text) already measures '-' (glyph
# 38, "minus") and '+' (glyph 39, "plus"). A grade needs the sign, so five immediates retarget the colon test and glyph
# to '-' / minus and the apostrophe and quote tests and glyph to '+' / plus. The card draws nothing but digits and grade
# labels, so the colon, apostrophe and quote glyphs are not used there.
DRAWER_SITES = (
    ("card_drawer_minus_test", 0x000F200B, bytes.fromhex("3a00"), bytes.fromhex("2d00")),            # cmp ax, ':' -> '-'
    ("card_drawer_minus_glyph", 0x000F201D, bytes.fromhex("24000000"), bytes.fromhex("26000000")),   # mov eax, 36 (colon) -> 38 (minus)
    ("card_drawer_plus_test", 0x000F2025, bytes.fromhex("2700"), bytes.fromhex("2b00")),             # cmp ax, "'" -> '+'
    ("card_drawer_quote_test", 0x000F202B, bytes.fromhex("2200"), bytes.fromhex("2b00")),            # cmp ax, '"' -> '+' (never matches a second character)
    ("card_drawer_plus_glyph", 0x000F2052, bytes.fromhex("25000000"), bytes.fromhex("27000000")),    # mov eax, 37 (apostrophe) -> 39 (plus)
)

# Dependency entry bytes the cave assumes (retail, pinned): the overall thunk, the swprintf thunks and handler
# registration, the spreadsheet formatter's prologue and its unknown-kind exit, and the tail the matchup stub repeats.
GUARDS = (
    (0x000E6660, 10, hashlib.sha256(bytes.fromhex("ba01000000e926071600")).hexdigest()),
    (0x0004A3E0, 20, hashlib.sha256(bytes.fromhex("8b4424045052baffffff7fe810fbffffc2040090")).hexdigest()),
    (0x0004A400, 5, hashlib.sha256(bytes.fromhex("e9dbffffff")).hexdigest()),
    (0x00173120, 8, hashlib.sha256(bytes.fromhex("83ec0883f8080f87")).hexdigest()),
    (0x001732CA, 16, hashlib.sha256(bytes.fromhex("ba983ae800e8dcd7ebff83c408c20400")).hexdigest()),
    (0x002B0A74, 28, hashlib.sha256(bytes.fromhex("8d4c2404518b4c2410bae867e90089442408e87599d9ff5e59c20c00")).hexdigest()),
    # the card drawer's colon, apostrophe/quote and space handling, from the colon test to the shared glyph call
    (0x000F2009, 77, hashlib.sha256(bytes.fromhex(
        "663d3a0075148b4424108b4c24185750535551b824000000eb33663d2700741b663d2200741583c602663d2000752e"
        "d9442418d805847f4e00eb1e8b5424108b4424185752535550b825000000")).hexdigest()),
)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def code_for(code_va: int, ro_va: int, bands: Sequence[tuple[int | None, str]] = DEFAULT_BANDS) -> tuple[bytes, bytes]:
    """The owned content: (RX code, read-only table and literals) with the template's relocations applied."""

    symbols = dict(code=code_va, ro=ro_va, fn_overall=FN_OVERALL, fn_swprintf=FN_SWPRINTF, nan_default=NAN_EXIT)
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    ro = bytearray(assembly.RODATA)
    at = assembly.RO_LABELS["bands"]
    ro[at:at + BAND_ROWS * 12] = band_table_bytes(bands)
    _require(len(result) <= CODE_SIZE and len(ro) <= RO_SIZE, "letter grades exceed the fixed owner budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc"), bytes(ro).ljust(RO_SIZE, b"\0")


def labels(code_va: int, ro_va: int) -> dict[str, int]:
    return {**{name: code_va + offset for name, offset in assembly.LABELS.items()},
            **{name: ro_va + offset for name, offset in assembly.RO_LABELS.items()}}


def guideline_label(threshold: int, bands: Sequence[tuple[int | None, str]] = DEFAULT_BANDS) -> str:
    """The menu text for "threshold or better": the grade that starts at it; below the last named grade, "F- (40+)"."""

    rows = normalize_bands(bands)
    grade = grade_for(threshold, rows)
    if rows[-1][1] == grade and (len(rows) == 1 or threshold < rows[-2][0]):
        return f"{grade} ({threshold}+)"
    return f"{grade} or better"


def guideline_slot_bytes(threshold: int, bands: Sequence[tuple[int | None, str]] = DEFAULT_BANDS) -> bytes:
    raw = guideline_label(threshold, bands).encode("utf-16le") + b"\0\0"
    _require(len(raw) <= GUIDELINE_SLOT_BYTES, "guideline label exceeds its string slot")
    return raw.ljust(GUIDELINE_SLOT_BYTES, b"\0")


def retail_guideline_slot(threshold: int) -> bytes:
    return f"{threshold} or better".encode("utf-16le").ljust(GUIDELINE_SLOT_BYTES, b"\0")


def sites(code_va: int, ro_va: int, bands: Sequence[tuple[int | None, str]] = DEFAULT_BANDS) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes); relative to the owned pages."""

    at = labels(code_va, ro_va)
    literals = {"grade": at["fmt_grade"], "overall": at["fmt_overall"], "sentence": at["fmt_rating_sentence"]}
    out = [
        ("printf_conversion_R", CONVERSION_ROW_VA, RETAIL_CONVERSION_ROW,
         struct.pack("<II", ord(CONVERSION_CHAR), at["convert_R"])),
        ("sheet_cell_kind9", KIND_BRANCH_VA, RETAIL_KIND_BRANCH,
         _rel32(KIND_BRANCH_VA + 4, at["cell_kind9"])),
    ]
    for label, va in PLAYER_COLUMNS + TEAM_COLUMNS:
        out.append((label, va, RETAIL_FLAGS, GRADE_FLAGS))
    for label, va, before, which in LITERAL_SITES:
        out.append((label, va, before, struct.pack("<I", literals[which])))
    out.append(("weekly_prep_overall", MATCHUP_SITE_VA, RETAIL_MATCHUP_SITE,
                b"\xe9" + _rel32(MATCHUP_SITE_VA + 5, at["matchup_overall"]) + b"\x90\x90"))
    out.extend(DRAWER_SITES)
    for va, threshold in GUIDELINE_SLOTS:
        out.append((f"trade_guideline_{threshold}", va, retail_guideline_slot(threshold),
                    guideline_slot_bytes(threshold, bands)))
    return out


def allocations(payload: bytes) -> dict[str, dict]:
    """{"code": row, "read_only": row} of an installed allocation, {} when the owner is not allocated."""

    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    found = {r["kind"]: r for r in rows}
    _require(len(rows) == len(found) == 2 and set(found) == {"code", "read_only"}
             and all((found[k]["size"], found[k]["align"]) == (size, align) for _o, k, size, align in F4_REQUESTS),
             "foreign letter grades allocation")
    return found


def _check_guards(image: XbeImage, checked_sites) -> None:
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _label, address, before, _after in checked_sites:
            if va <= address and address + len(before) <= va + size:
                content[address - va:address - va + len(before)] = before
        _require(hashlib.sha256(content).hexdigest() == digest, f"foreign letter grades dependency at {va:#x}")


def _owned_state(payload: bytes):
    """-> ("retail" | "applied", allocations | None, bands | None); anything else raises."""

    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocations(payload)
    if not found:
        retail_sites = sites(0x14DA000, 0x1506000)   # the retail bytes do not depend on the pages or the bands
        _require(rdata.status(payload, retail_sites) == "retail", "letter grade sites changed without an allocation")
        _check_guards(image, retail_sites)
        return "retail", None, None
    code_va, ro_va = found["code"]["va"], found["read_only"]["va"]
    code, ro = image.read(code_va, CODE_SIZE), image.read(ro_va, RO_SIZE)
    if code == b"\xcc" * CODE_SIZE and ro == bytes(RO_SIZE):
        edits = sites(code_va, ro_va)
        _require(rdata.status(payload, edits) == "retail", "letter grade sites changed with an empty allocation")
        _check_guards(image, edits)
        return "retail", found, None
    at = assembly.RO_LABELS["bands"]
    bands = decode_band_table(ro[at:at + BAND_ROWS * 12])
    _require((code, ro) == code_for(code_va, ro_va, bands), "foreign letter grades code")
    edits = sites(code_va, ro_va, bands)
    _require(rdata.status(payload, edits) == "applied", "mixed letter grade sites")
    _check_guards(image, edits)
    return "applied", found, bands


def status(payload: bytes) -> str:
    try:
        return _owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    if state != "applied":
        return {"status": state, "letter_grades": False, "bands": None}
    from . import nfl2k5_letter_grades_progress as progress
    bands = _owned_state(payload)[2]
    return {"status": state, "letter_grades": True, "progression": progress.status(payload),   # b77-f4b
            "bands": [{"minimum": m, "label": label} for m, label in bands]}


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    base = allocations(payload)
    edits = sites(base["code"]["va"] if base else 0x14DA000, base["read_only"]["va"] if base else 0x1506000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes, *, bands: Sequence[tuple[int | None, str]] = DEFAULT_BANDS,
          progression: bool = True) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner and its sites, then (default) the progression screen's overall row (b77-f4b).

    ``progression=False`` is exactly the F4 patch (the native repair ``tools/b77/f4_repair.py`` asks for it).
    Idempotent for the same bands; a different band table needs a rebuild."""

    result, receipt = _apply_f4(payload, bands=bands, requests=REQUESTS if progression else F4_REQUESTS)
    if not progression:
        return result, receipt
    from . import nfl2k5_letter_grades_progress as progress
    final, progress_receipt = progress.apply(result)
    return final, {**receipt, "progression": progress_receipt,
                   "already_applied": bool(receipt["already_applied"] and progress_receipt["already_applied"]),
                   "changed_bytes": int(receipt["changed_bytes"]) + int(progress_receipt["changed_bytes"])}


def _apply_f4(payload: bytes, *, bands, requests) -> tuple[bytes, Mapping[str, object]]:
    bands = normalize_bands(bands)
    state, found, installed_bands = _owned_state(payload)
    common = {"owner": OWNER, "experimental": True, "bands": [list(b) for b in bands],
              "code_bytes": len(assembly.CODE), "read_only_bytes": len(assembly.RODATA),
              "owner_bytes": CODE_SIZE + RO_SIZE}
    if state == "applied":
        _require(installed_bands == bands, "the band table differs; rebuild from the original")
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if not found:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, requests, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, F4_REQUESTS)
        found = allocations(payload)
    _require(bool(found), "reserve the letter grades allocation first")
    code_va, ro_va = found["code"]["va"], found["read_only"]["va"]
    code, ro = code_for(code_va, ro_va, bands)
    installed, code_receipt = space.install_code(payload, OWNER, code)
    installed, ro_receipt = space.install_read_only(installed, OWNER, ro)
    result, site_receipt = rdata.apply(installed, sites(code_va, ro_va, bands), OWNER)
    _require(status(result) == "applied", "letter grades postcondition failed")
    changed = sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before))
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "read_only_install": ro_receipt, "code_va": hex(code_va), "read_only_va": hex(ro_va),
                    "changed_bytes": changed,
                    "sites": [{"label": label, "va": hex(va), "size": len(before_bytes)}
                              for label, va, before_bytes, _after in sites(code_va, ro_va, bands)],
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def main(argv=None) -> int:
    """python3 -m mod_editor.core.nfl2k5_letter_grades {status,apply} source.xbe [output.xbe]"""

    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=UI_LABEL)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    _require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "apply":
        result, receipt = apply(payload)
        with args.output.open("xb") as stream:
            stream.write(result)
    else:
        receipt = {**read_settings(payload), "owner": OWNER, "experimental": True}
    print(json.dumps(receipt, indent=2, default=str))
    return 0


__all__ = ["OWNER", "REQUESTS", "F4_REQUESTS", "PROGRESS_OWNER", "PROGRESS_REQUESTS", "UI_LABEL", "HELP_TEXT", "BUILD_CAPTION", "DEFAULT_BANDS", "LetterGradesError",
           "normalize_bands", "grade_for", "band_table_bytes", "decode_band_table", "code_for", "sites", "labels",
           "allocations", "apply", "status", "read_settings", "reservations"]


if __name__ == "__main__":
    raise SystemExit(main())
