"""7-on-7 practice mode: a fifth Practice Type in Scrimmage Settings (executable patch, xemu-only).

What the retail game has (all addresses are Xbox virtual addresses in ``default.xbe``):

* Practice -> Scrimmage -> *Practice Type* is the option row at ``.rdata 0x501908`` whose value is
  the global ``0xE601D4``: 0 Special Move, 1 Full Scrimmage, 2 Offense Only, 3 Kickoff.  Its text
  callback ``FUN_00148a70`` reads ``[0x4F2508 + value*4]`` (four UTF-16 string pointers), the
  increment callback ``FUN_00148860`` wraps past ``2`` to ``0``, the decrement ``FUN_00148890``
  wraps below ``1`` to ``3``, and ``FUN_00148900`` registers the row with ``push 3`` (the last
  index) and the same string table.
* Every change runs ``FUN_000e33f0``: ``mov ecx,4; call FUN_00061fe0`` (the kick-practice word
  ``0xB34258`` back to its default), then ``jmp [0xE3434 + value*4]`` into four stubs that write
  the game-mode word ``0xE5FF80``: 0 -> mode 0, 1 -> mode 1, 2 -> mode 2, 3 -> kick word 2 then
  mode 1.  Mode 3 is Basic Training, modes 4+ are real games.
* Game start ``FUN_00062be0`` at ``0x62D0C`` does ``cmp [0xE5FF80],3; jne 0x62D39``: Basic
  Training formats ``PRACTICE-pb.iff`` into BOTH team book objects (``0xB307D0`` / ``0xB30810``);
  every other mode loads ``<abbr>-pb.iff`` per team through ``FUN_000628d0``.
* The pass rush is gated by *Power Pocket* (``0xE600D0``) at ``FUN_00232ce0`` (``0x232E5C``: the
  rusher-vs-blocker resolution returns "blocked" when it is on in mode 1) and ``FUN_00233320``
  (``0x2333B3``: the shed roll becomes a fixed 0.5).

The patch adds value 4, "7-On-7":

* the two wrap constants become 3 / 4 and the register call pushes 4;
* the text and register callbacks read a five-entry string table in the cave (the four retail
  pointers plus a new UTF-16 ``7-On-7``);
* the switch jumps through a five-entry table in the cave: entries 0-3 clear the 7-on-7 flag and
  jump to the retail stubs (so Special Move / Full Scrimmage / Offense Only / Kickoff are exactly
  retail, kick word included); entry 4 sets the flag and writes mode 1 (Full Scrimmage);
* the loader compare becomes ``jmp cave``: mode 3, or mode 1 with the flag set, takes the retail
  Basic Training path (``PRACTICE-pb.iff`` for both teams); anything else takes the per-team path;
* the two Power Pocket reads become calls that OR the flag into the option, so the pass rush
  behaves as if Power Pocket were on without changing the user's saved option.

The flag byte, both tables, the ``7-On-7`` string and ~90 bytes of code live in the first 256
bytes of ``FUN_001ac170`` (0x1AC170..0x1AC37D), a 525-byte routine with no call, jump or pointer
to it anywhere in the image (scan 2026-09-03; the kick-rules and overtime caves are its siblings
at 0x1AFCC0 / 0x1AFDF0).  The 7-on-7 playbook content itself is data in ``PRACTICE-pb.iff``
(``nfl2k5_seven_on_seven_book``).  Pattern-checked against the retail bytes, ``.text`` digest
recomputed, idempotent.  Unverified at runtime.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000

MODE_VA = 0x00E5FF80              # game-mode word (0 Special Move, 1 Full Scrimmage, 2 Offense Only, 3 Basic Training)
PRACTICE_TYPE_VA = 0x00E601D4     # Scrimmage Settings -> Practice Type
POWER_POCKET_VA = 0x00E600D0      # Scrimmage Settings -> Power Pocket
KICK_WORD_VA = 0x00B34258         # FUN_00061fe0's store (Kickoff practice = 2); never touched here

RETAIL_STRING_TABLE_VA = 0x004F2508   # 'Special Move', 'Full Scrimmage', 'Offense Only', 'Kickoff'
RETAIL_STRINGS = (0x00E6968C, 0x00E696A8, 0x00E696C8, 0x00E696E4)
RETAIL_JUMP_TABLE_VA = 0x000E3434
RETAIL_STUBS = (0x000E3406, 0x000E3426, 0x000E3411, 0x000E341C)   # mode 0 / mode 1 / mode 2 / kick 2 + mode 1

LOADER_PRACTICE_VA = 0x00062D15   # `push 0; mov edx,"PRACTICE-pb.iff"; ...` (the Basic Training path)
LOADER_TEAMS_VA = 0x00062D39      # `push 1; call FUN_000628d0; push 0; call FUN_000628d0`

CAVE_VA = 0x001AC170              # FUN_001ac170: dead (no call, jump or pointer to it), 525 bytes
CAVE_SIZE = 0x100
FLAG_OFFSET = 0x00                # one byte: 1 while the 7-on-7 practice type is selected
STRING_TABLE_OFFSET = 0x04        # five u32 string pointers
JUMP_TABLE_OFFSET = 0x18          # five u32 stub addresses
NAME_OFFSET = 0x2C                # UTF-16LE "7-On-7\0" (14 bytes)
CODE_OFFSET = 0x3C
PRACTICE_TYPE_NAME = "7-On-7"
NEW_VALUE = 4

RETAIL_CAVE = bytes.fromhex(
    "558bec83e4f083ec18568b356802e6005733ff3bf70f847c000000eb038d4900397e4874078b76303bf775f43bf774678b46"
    "208b88100300000f2841200f294424108b5424188b44241052508bcee82d0312008b4e208b91100300008b52308bcee80ac8"
    "ffff8bcee8733903008b460c8978108b4e0c89791c8bcee8408a06008b76303bf77410397e4874078b76303bf775f43bf775"
    "998b357402e6003bf774498b56208b82100300000f2840200f294424108b4c24188b54241051528bcee8bc0212008b46208b"
    "88100300008b51308bcee899c7ffff8b560c897a108b460c89781c8b76303bf775b75f5e8be55dc383ec085355568bf18b6e"
    "208b9d1c0400"
)
assert len(RETAIL_CAVE) == CAVE_SIZE

# (label, VA, retail bytes) of every edited site outside the cave.
MAX_SITE_VA = 0x00148860          # FUN_00148860: `cmp dword [0xE601D4],2` (imm8 at +6)
RETAIL_MAX_SITE = bytes.fromhex("833dd401e60002")
WRAP_SITE_VA = 0x00148899         # FUN_00148890: `mov dword [0xE601D4],3` (imm32 at +6)
RETAIL_WRAP_SITE = bytes.fromhex("c705d401e60003000000")
REGISTER_SITE_VA = 0x00148900     # FUN_00148900: `push 0x4F2508; push 3`
RETAIL_REGISTER_SITE = bytes.fromhex("6808254f006a03")
TEXT_SITE_VA = 0x00148A75         # FUN_00148a70: `mov eax,[eax*4+0x4F2508]`
RETAIL_TEXT_SITE = bytes.fromhex("8b048508254f00")
SWITCH_SITE_VA = 0x000E33FF       # FUN_000e33f0: `jmp dword [eax*4+0xE3434]`
RETAIL_SWITCH_SITE = bytes.fromhex("ff248534340e00")
LOADER_SITE_VA = 0x00062D0C       # FUN_00062be0: `cmp dword [0xE5FF80],3; jne 0x62D39`
RETAIL_LOADER_SITE = bytes.fromhex("833d80ffe500037524")
RUSH_GATE_SITE_VA = 0x00232E5C    # FUN_00232ce0: `mov eax,[0xE600D0]` (then test eax,eax; je; cmp [mode],1)
RETAIL_RUSH_GATE_SITE = bytes.fromhex("a1d000e600")
SHED_GATE_SITE_VA = 0x002333B3    # FUN_00233320: `cmp dword [0xE600D0],esi` (then jne -> the fixed 0.5 roll)
RETAIL_SHED_GATE_SITE = bytes.fromhex("3935d000e600")


class SevenOnSevenError(ValueError):
    """The 7-on-7 practice patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SevenOnSevenError(message)


def _imm(va: int) -> str:
    return struct.pack("<I", va).hex()


FLAG_VA = CAVE_VA + FLAG_OFFSET
STRING_TABLE_VA = CAVE_VA + STRING_TABLE_OFFSET
JUMP_TABLE_VA = CAVE_VA + JUMP_TABLE_OFFSET
NAME_VA = CAVE_VA + NAME_OFFSET
CODE_VA = CAVE_VA + CODE_OFFSET


def _code() -> tuple[bytes, dict[str, int]]:
    """The cave code: four flag-clearing stubs, the 7-on-7 stub, the loader test, the two rush gates."""

    a = _Asm(CODE_VA)
    for k, stub in enumerate(RETAIL_STUBS):
        a.label(f"stub{k}")
        a.b("c605" + _imm(FLAG_VA) + "00")     # mov byte [flag],0
        a.jmp_abs(stub)                         # jmp retail stub (mode word / kick word exactly as retail)
    a.label("stub4")
    a.b("c605" + _imm(FLAG_VA) + "01")         # mov byte [flag],1
    a.b("c705" + _imm(MODE_VA) + "01000000")   # mov dword [0xE5FF80],1   ; Full Scrimmage
    a.b("c3")                                   # ret
    a.label("loader")
    a.b("833d" + _imm(MODE_VA) + "03")         # cmp dword [0xE5FF80],3
    a.j8("74", "practice")                      # je practice          ; Basic Training: retail path
    a.b("833d" + _imm(MODE_VA) + "01")         # cmp dword [0xE5FF80],1
    a.j8("75", "teams")                         # jne teams
    a.b("803d" + _imm(FLAG_VA) + "00")         # cmp byte [flag],0
    a.j8("74", "teams")                         # je teams
    a.label("practice")
    a.jmp_abs(LOADER_PRACTICE_VA)               # PRACTICE-pb.iff into both team book objects
    a.label("teams")
    a.jmp_abs(LOADER_TEAMS_VA)                  # <abbr>-pb.iff per team
    a.label("rush_gate")
    a.b("a1" + _imm(POWER_POCKET_VA))           # mov eax,[0xE600D0]
    a.b("0a05" + _imm(FLAG_VA))                 # or al,[flag]
    a.b("c3")                                   # ret
    a.label("shed_gate")
    a.b("3935" + _imm(POWER_POCKET_VA))         # cmp dword [0xE600D0],esi   (esi = 0 at the call site)
    a.j8("75", "shed_done")                     # jne shed_done              ; option on: not equal, as retail
    a.b("803d" + _imm(FLAG_VA) + "00")         # cmp byte [flag],0          ; flag on: not equal; off: equal
    a.label("shed_done")
    a.b("c3")                                   # ret
    code = a.assemble()
    labels = {name: CODE_VA + pos for name, pos in a.labels.items()}
    return code, labels


def cave_labels() -> dict[str, int]:
    _code_bytes, labels = _code()
    return {"flag": FLAG_VA, "string_table": STRING_TABLE_VA, "jump_table": JUMP_TABLE_VA, "name": NAME_VA, **labels}


def cave_bytes() -> bytes:
    """Flag byte, string table, jump table, the name and the code, int3-padded to 256 bytes."""

    code, labels = _code()
    body = bytearray(b"\xcc" * CAVE_SIZE)
    body[FLAG_OFFSET] = 0
    name = PRACTICE_TYPE_NAME.encode("utf-16le") + b"\0\0"
    _require(NAME_OFFSET + len(name) <= CODE_OFFSET, "the practice-type name does not fit before the code")
    struct.pack_into("<5I", body, STRING_TABLE_OFFSET, *RETAIL_STRINGS, NAME_VA)
    struct.pack_into("<5I", body, JUMP_TABLE_OFFSET, *(labels[f"stub{k}"] for k in range(5)))
    body[NAME_OFFSET: NAME_OFFSET + len(name)] = name
    _require(CODE_OFFSET + len(code) <= CAVE_SIZE, f"7-on-7 cave code is {len(code)} bytes, over {CAVE_SIZE - CODE_OFFSET}")
    body[CODE_OFFSET: CODE_OFFSET + len(code)] = code
    return bytes(body)


def _rel32(opcode: bytes, site: int, target: int) -> bytes:
    return opcode + struct.pack("<i", target - (site + 5))


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise SevenOnSevenError(f"VA 0x{va:x} is in no section")


def sites() -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, retail bytes, patched bytes) for every edited span."""

    labels = cave_labels()
    return [
        ("practice_type_max", MAX_SITE_VA, RETAIL_MAX_SITE, RETAIL_MAX_SITE[:6] + bytes([NEW_VALUE - 1])),
        ("practice_type_wrap", WRAP_SITE_VA, RETAIL_WRAP_SITE, RETAIL_WRAP_SITE[:6] + struct.pack("<I", NEW_VALUE)),
        ("practice_type_register", REGISTER_SITE_VA, RETAIL_REGISTER_SITE,
         b"\x68" + struct.pack("<I", STRING_TABLE_VA) + b"\x6a" + bytes([NEW_VALUE])),
        ("practice_type_text", TEXT_SITE_VA, RETAIL_TEXT_SITE, bytes.fromhex("8b0485") + struct.pack("<I", STRING_TABLE_VA)),
        ("practice_type_switch", SWITCH_SITE_VA, RETAIL_SWITCH_SITE, bytes.fromhex("ff2485") + struct.pack("<I", JUMP_TABLE_VA)),
        ("book_loader", LOADER_SITE_VA, RETAIL_LOADER_SITE, _rel32(b"\xe9", LOADER_SITE_VA, labels["loader"]) + b"\x90" * 4),
        ("rush_gate", RUSH_GATE_SITE_VA, RETAIL_RUSH_GATE_SITE, _rel32(b"\xe8", RUSH_GATE_SITE_VA, labels["rush_gate"])),
        ("shed_gate", SHED_GATE_SITE_VA, RETAIL_SHED_GATE_SITE, _rel32(b"\xe8", SHED_GATE_SITE_VA, labels["shed_gate"]) + b"\x90"),
        ("cave", CAVE_VA, RETAIL_CAVE, cave_bytes()),
    ]


def _located(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    return [(label, _offset(payload, va), before, after) for label, va, before, after in sites()]


def status(payload: bytes) -> str:
    try:
        located = _located(payload)
    except (SevenOnSevenError, ValueError, struct.error):
        return "foreign"
    states = set()
    for _label, off, before, after in located:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    _require(state == "retail", f"7-on-7 practice sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, off, before, after in _located(payload):
        _require(len(before) == len(after), f"{label}: patched span size differs")
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "bytes": len(after)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    code, _labels = _code()
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "code_bytes": len(code), "cave": f"0x{CAVE_VA:x}..0x{CAVE_VA + CAVE_SIZE:x}",
                     "practice_type_value": NEW_VALUE, "practice_type_name": PRACTICE_TYPE_NAME}


def code_report() -> dict[str, object]:
    code, labels = _code()
    return {"code_bytes": len(code), "code_capacity": CAVE_SIZE - CODE_OFFSET, "labels": {k: f"0x{v:x}" for k, v in labels.items()},
            "runtime_verified": False}


__all__ = ["SevenOnSevenError", "CAVE_VA", "CAVE_SIZE", "RETAIL_CAVE", "FLAG_VA", "STRING_TABLE_VA", "JUMP_TABLE_VA",
           "NAME_VA", "MODE_VA", "PRACTICE_TYPE_VA", "POWER_POCKET_VA", "KICK_WORD_VA", "NEW_VALUE", "PRACTICE_TYPE_NAME",
           "LOADER_SITE_VA", "LOADER_PRACTICE_VA", "LOADER_TEAMS_VA", "SWITCH_SITE_VA", "apply", "cave_bytes", "cave_labels",
           "code_report", "sites", "status"]
