"""Home and away jerseys at any stadium: the uniform-colour rule, and an in-game colour choice (executable patch).

What the retail game does (all addresses are Xbox virtual addresses in ``default.xbe``):

* The jersey colour is decided once per game load in ``FUN_000615a0`` (0x615A0, sole caller 0x62D47
  in the asset loader).  Practice (mode 3) copies fixed names; every other mode computes
  ``swap = (home == "DAL") || (away == "DAL" && (home == "WAS" || home == "TEN"))`` with four calls
  to the wide-string equality ``FUN_00030c40`` (returns 1 when equal) on the abbreviations at
  ``[0xB30B60]`` (away) and ``[0xB3096C]`` (home) against the literals 0xE61048 "DAL", 0xE61050 "WAS",
  0xE61058 "TEN".  That block is 0x6160F..0x61670 (97 bytes) and leaves ``esi`` = swap.  The away
  texture name is then ``"%s%c%d.iff"`` with the letter ``'a' + 7*swap`` (0x6168B: ``mov eax,esi;
  neg eax; sbb eax,eax; and eax,7; add eax,0x61``) and the home letter ``'h' - 7*swap`` (0x616CA:
  ``neg esi; sbb esi,esi; and esi,-7; add esi,0x68``).  'a' = white, 'h' = dark; that is the whole
  Cowboys exception (white at home, navy in Washington and Tennessee).  No per-team data flag.
* The only thing the player chooses is the era slot 0..14 per side (home ``0xE60210``, away
  ``0xE60214``): ``FUN_000e2a90`` (eax = team, ecx = slot) says whether a slot exists (0 always;
  1..14 when the team's year pair at ``team+0x15A+4*(slot-1)`` is non-zero).  Four handlers clamp
  and skip unavailable slots without wrapping: home prev/next ``FUN_000e2f70`` / ``FUN_000e2fb0``,
  away prev/next ``FUN_000e3050`` / ``FUN_000e3090`` (team getters ``FUN_00077b00`` / ``FUN_00077b40``),
  reached from Controller Assign (0x27AF50..0x27AFB0) and the exhibition Team Select screen
  (0x2C0BA0..0x2C0C00).  The slots reset to 0 in ``FUN_000e2d80`` (0xE2D80, called from the
  game-setup initialiser ``FUN_00077d20``).

Two forms, ``BuildPlan.uniform_choice``:

``"rule"``: the 97-byte block becomes ``mov esi, RULE_SWAP`` plus NOPs.  RULE_SWAP = 0: the home
  team is always dark and the visitor always white, everywhere, Cowboys included (the imm32 at
  0x61610 is the rule word; 1 would swap every game).  Nothing else changes.

``"choice"``: the colour becomes a per-side choice on the same up/down input that picks the era.
  * Two flip words in writable memory (the alignment gap between ``.rdata`` and ``.data``; ``.text``
    is mapped read-only): ``HOME_FLIP`` 0xA69974 and ``AWAY_FLIP`` 0xA69978, each 0 or 7, cleared
    where the era slots reset (the tail of ``FUN_000e2d80``).  ``AWAY_VALUE`` 0xA6997C is scratch
    the loader writes before the away letter site reads it.
  * The four slot handlers are rewritten in place: "next" past the last available era toggles that
    side's flip and restarts at era 0; "prev" below era 0 toggles and jumps to the last available
    era.  Up/down therefore cycles 30 states (15 eras x 2 colours); no new button.
  * The rule block computes the retail swap (four equality calls, combined arithmetically:
    ``((hWAS | hTEN) & aDAL) | hDAL``), scales it to 0/7, stores ``AWAY_VALUE = 7*swap ^ AWAY_FLIP``
    and leaves ``esi = 7*swap ^ HOME_FLIP``.  The retail home letter site then yields
    ``'h' - 7*(swap ^ flip_home)`` unchanged, and the away site reads ``mov eax,[AWAY_VALUE]`` so
    ``'a' + 7*(swap ^ flip_away)`` comes out of the retail ``and eax,7; add eax,0x61``.  Both teams
    may choose white.  Practice, Xbox Live and the Team Select preview art are not covered.

Everything fits inside the freed 97 bytes and the handlers' own bodies (each handler keeps at
least eight retail padding bytes before its neighbour); no cave.  Retail bytes pinned at every
site, section digests recomputed, idempotent.  Unwitnessed in game.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000
MODES = ("rule", "choice")

# retail globals / routines
HOME_ABBR_PTR_VA = 0x00B3096C     # pointer to the home team's UTF-16 abbreviation
AWAY_ABBR_PTR_VA = 0x00B30B60     # pointer to the away team's UTF-16 abbreviation
STR_DAL_VA = 0x00E61048
STR_WAS_VA = 0x00E61050
STR_TEN_VA = 0x00E61058
FN_WCSEQ_VA = 0x00030C40          # fastcall(ecx=literal, edx=string) -> eax 1 when equal, else 0
HOME_SLOT_VA = 0x00E60210         # era slot of the home side (0..14)
AWAY_SLOT_VA = 0x00E60214
FN_HOME_TEAM_VA = 0x00077B00      # mov eax,[0xE5FE68]
FN_AWAY_TEAM_VA = 0x00077B40      # mov eax,[0xE5FE6C]
HOME_TEAM_PTR_VA = 0x00E5FE68
AWAY_TEAM_PTR_VA = 0x00E5FE6C
FN_SLOT_VALID_VA = 0x000E2A90     # eax=team, ecx=slot -> eax 1 when the era exists (ecx/edx preserved)
TEAM_YEARS_OFF = 0x15A            # word pairs per era 1..14 at team+0x15A+4*(slot-1)
LAST_SLOT = 14

# writable state: the 23-byte gap between the end of .rdata (0xA69969) and the start of .data
# (0xA69980), both writable sections on the same page; the 7-on-7 flag owns 0xA69970. No pointer in
# any section of the retail image lands in 0xA69969..0xA69980 (scan 2026-09-04).
HOME_FLIP_VA = 0x00A69974         # dword 0 or 7: the home side's colour is flipped
AWAY_FLIP_VA = 0x00A69978         # dword 0 or 7: the away side's colour is flipped
AWAY_VALUE_VA = 0x00A6997C        # dword scratch: 7*swap ^ AWAY_FLIP, written by the loader each game
FLIP_TOGGLE = 7

# edited sites
RULE_BLOCK_VA = 0x0006160F
RULE_BLOCK_SIZE = 97
RULE_BLOCK_END_VA = RULE_BLOCK_VA + RULE_BLOCK_SIZE     # 0x61670: `call FUN_000e30f0`
RULE_SWAP_VA = RULE_BLOCK_VA + 1                        # the rule word's imm32 in the "rule" form
RULE_SWAP = 0
AWAY_LETTER_VA = 0x0006168B                             # `mov eax,esi; neg eax; sbb eax,eax` (6 B)
AWAY_LETTER_CALL_VA = 0x000616B4                        # the away name's formatter call
HOME_LETTER_CALL_VA = 0x000616FA                        # the home name's formatter call
RESET_VA = 0x000E2D80                                   # FUN_000e2d80 entry
RESET_TAIL_VA = 0x000E2D91                              # its `ret` + ten alignment nops
HOME_PREV_VA = 0x000E2F70
HOME_NEXT_VA = 0x000E2FB0
AWAY_PREV_VA = 0x000E3050
AWAY_NEXT_VA = 0x000E3090
PREV_SIZE = 0x38                                        # 0x37 retail bytes + 1 nop; 8 nops stay before the next routine
NEXT_SIZE = 0x43                                        # retail body; 13 nops stay before the next routine

RETAIL_RULE_BLOCK = bytes.fromhex(
    "8b15600bb300b94810e60033f6e81ff6fcff85c074328b156c09b300b95010e600e80bf6fcff85c07405be01000000"
    "8b156c09b300b95810e600e8f2f5fcff85c07405be010000008b156c09b300b94810e600e8d9f5fcff85c07405be01000000"
)
RETAIL_AWAY_LETTER = bytes.fromhex("8bc6f7d81bc0")
RETAIL_RESET_TAIL = bytes.fromhex("c390909090909090909090")
RETAIL_HOME_PREV = bytes.fromhex(
    "e88b4bf9ff8bd0a11002e60085c074218d48ff85c97c1a8bc2e802fbffff85c075094979f2b801000000c3890d1002e600b801000000c390")
RETAIL_HOME_NEXT = bytes.fromhex(
    "e84b4bf9ff8bd0a11002e60083f80e742c8d480183f90e7f248da424000000008bc2e8b9faffff85c0750c4183f90e7eefb801000000c3"
    "890d1002e600b801000000c3")
RETAIL_AWAY_PREV = bytes.fromhex(
    "e8eb4af9ff8bd0a11402e60085c074218d48ff85c97c1a8bc2e822faffff85c075094979f2b801000000c3890d1402e600b801000000c390")
RETAIL_AWAY_NEXT = bytes.fromhex(
    "e8ab4af9ff8bd0a11402e60083f80e742c8d480183f90e7f248da424000000008bc2e8d9f9ffff85c0750c4183f90e7eefb801000000c3"
    "890d1402e600b801000000c3")
assert len(RETAIL_RULE_BLOCK) == RULE_BLOCK_SIZE
assert len(RETAIL_HOME_PREV) == len(RETAIL_AWAY_PREV) == PREV_SIZE
assert len(RETAIL_HOME_NEXT) == len(RETAIL_AWAY_NEXT) == NEXT_SIZE


class UniformChoiceError(ValueError):
    """The uniform patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UniformChoiceError(message)


def _imm(va: int) -> str:
    return struct.pack("<I", va).hex()


def _pad(code: bytes, size: int, what: str) -> bytes:
    _require(len(code) <= size, f"{what} is {len(code)} bytes, over {size}")
    return code + b"\x90" * (size - len(code))


def rule_block_bytes(mode: str) -> bytes:
    """The 97 bytes at 0x6160F for either form."""

    _require(mode in MODES, f"unknown uniform form {mode!r}; choose from {MODES}")
    if mode == "rule":
        return _pad(b"\xbe" + struct.pack("<I", RULE_SWAP), RULE_BLOCK_SIZE, "uniform rule")   # mov esi, RULE_SWAP
    a = _Asm(RULE_BLOCK_VA)
    for ptr_va, literal_va, combine in ((HOME_ABBR_PTR_VA, STR_WAS_VA, "8bf0"),    # mov esi,eax  : hWAS
                                        (HOME_ABBR_PTR_VA, STR_TEN_VA, "0bf0"),    # or  esi,eax  : | hTEN
                                        (AWAY_ABBR_PTR_VA, STR_DAL_VA, "23f0"),    # and esi,eax  : & aDAL
                                        (HOME_ABBR_PTR_VA, STR_DAL_VA, "0bf0")):   # or  esi,eax  : | hDAL
        a.b("8b15" + _imm(ptr_va))            # mov edx,[abbreviation pointer]
        a.b("b9" + _imm(literal_va))          # mov ecx,literal
        a.call(FN_WCSEQ_VA)                   # eax = 1 when equal
        a.b(combine)
    a.b("6bf607")                             # imul esi,esi,7        ; swap -> 0 / 7
    a.b("8bc6")                               # mov eax,esi
    a.b("3305" + _imm(AWAY_FLIP_VA))          # xor eax,[AWAY_FLIP]
    a.b("a3" + _imm(AWAY_VALUE_VA))           # mov [AWAY_VALUE],eax  ; 7*(swap ^ flip_away)
    a.b("3335" + _imm(HOME_FLIP_VA))          # xor esi,[HOME_FLIP]   ; 7*(swap ^ flip_home) for the retail home site
    return _pad(a.assemble(), RULE_BLOCK_SIZE, "uniform choice rule block")


def away_letter_bytes() -> bytes:
    """``mov eax,[AWAY_VALUE]; nop``: the retail ``and eax,7; add eax,0x61`` that follow turn it into the letter."""

    return b"\xa1" + struct.pack("<I", AWAY_VALUE_VA) + b"\x90"


def reset_tail_bytes() -> bytes:
    """eax is 0 here (FUN_000e2d80 zeroes it first): clear both flips, then the retail ``ret``."""

    return b"\xa3" + struct.pack("<I", HOME_FLIP_VA) + b"\xa3" + struct.pack("<I", AWAY_FLIP_VA) + b"\xc3"


def _prev_handler(va: int, getter_va: int, slot_va: int, flip_va: int) -> bytes:
    """Era down: the previous available era; below era 0 toggle the colour and jump to the last available era."""

    a = _Asm(va)
    a.call(getter_va)                          # eax = team
    a.b("8bd0")                                # mov edx,eax
    a.b("8b0d" + _imm(slot_va))                # mov ecx,[slot]
    a.b("49")                                  # dec ecx
    a.j8("79", "search")                       # jns search            ; there was an era below
    a.b("8335" + _imm(flip_va) + "07")         # xor dword [flip],7    ; wrap: flip the colour
    a.b("6a0e")                                # push 14
    a.b("59")                                  # pop ecx               ; start from the last slot
    a.label("search")
    a.b("8bc2")                                # mov eax,edx
    a.call(FN_SLOT_VALID_VA)                   # eax = the era exists (ecx, edx preserved)
    a.b("85c0")                                # test eax,eax
    a.j8("75", "set")                          # jne set
    a.b("49")                                  # dec ecx
    a.j8("79", "search")                       # jns search
    a.b("33c9")                                # xor ecx,ecx           ; no era at all (no team): slot 0
    a.label("set")
    a.b("890d" + _imm(slot_va))                # mov [slot],ecx
    a.b("b801000000")                          # mov eax,1
    a.b("c3")                                  # ret
    return _pad(a.assemble(), PREV_SIZE, f"prev handler 0x{va:x}")


def _next_handler(va: int, getter_va: int, slot_va: int, flip_va: int) -> bytes:
    """Era up: the next available era; past the last one toggle the colour and restart at era 0."""

    a = _Asm(va)
    a.call(getter_va)                          # eax = team
    a.b("8bd0")                                # mov edx,eax
    a.b("8b0d" + _imm(slot_va))                # mov ecx,[slot]
    a.label("search")
    a.b("41")                                  # inc ecx
    a.b("83f90e")                              # cmp ecx,14
    a.j8("7f", "wrap")                         # jg wrap
    a.b("8bc2")                                # mov eax,edx
    a.call(FN_SLOT_VALID_VA)
    a.b("85c0")                                # test eax,eax
    a.j8("74", "search")                       # je search             ; this era is unavailable
    a.j8("eb", "set")                          # jmp set
    a.label("wrap")
    a.b("8335" + _imm(flip_va) + "07")         # xor dword [flip],7    ; flip the colour
    a.b("33c9")                                # xor ecx,ecx           ; era 0
    a.label("set")
    a.b("890d" + _imm(slot_va))                # mov [slot],ecx
    a.b("b801000000")                          # mov eax,1
    a.b("c3")                                  # ret
    return _pad(a.assemble(), NEXT_SIZE, f"next handler 0x{va:x}")


def handler_bytes() -> dict[str, bytes]:
    return {
        "home_prev": _prev_handler(HOME_PREV_VA, FN_HOME_TEAM_VA, HOME_SLOT_VA, HOME_FLIP_VA),
        "home_next": _next_handler(HOME_NEXT_VA, FN_HOME_TEAM_VA, HOME_SLOT_VA, HOME_FLIP_VA),
        "away_prev": _prev_handler(AWAY_PREV_VA, FN_AWAY_TEAM_VA, AWAY_SLOT_VA, AWAY_FLIP_VA),
        "away_next": _next_handler(AWAY_NEXT_VA, FN_AWAY_TEAM_VA, AWAY_SLOT_VA, AWAY_FLIP_VA),
    }


def sites(mode: str = "choice") -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, retail bytes, patched bytes) for every span the form edits."""

    _require(mode in MODES, f"unknown uniform form {mode!r}; choose from {MODES}")
    out = [("uniform_rule", RULE_BLOCK_VA, RETAIL_RULE_BLOCK, rule_block_bytes(mode))]
    if mode == "choice":
        handlers = handler_bytes()
        out += [
            ("away_letter", AWAY_LETTER_VA, RETAIL_AWAY_LETTER, away_letter_bytes()),
            ("slot_reset", RESET_TAIL_VA, RETAIL_RESET_TAIL, reset_tail_bytes()),
            ("home_prev", HOME_PREV_VA, RETAIL_HOME_PREV, handlers["home_prev"]),
            ("home_next", HOME_NEXT_VA, RETAIL_HOME_NEXT, handlers["home_next"]),
            ("away_prev", AWAY_PREV_VA, RETAIL_AWAY_PREV, handlers["away_prev"]),
            ("away_next", AWAY_NEXT_VA, RETAIL_AWAY_NEXT, handlers["away_next"]),
        ]
    for _label, _va, before, after in out:
        _require(len(before) == len(after), f"{_label}: patched span size differs")
    return out


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise UniformChoiceError(f"VA 0x{va:x} is in no section")


def _site_states(payload: bytes) -> dict[str, str]:
    """Per site: retail | rule | choice | foreign (the rule block is the only one with two patched forms)."""

    states: dict[str, str] = {}
    rule_form = rule_block_bytes("rule")
    for label, va, before, after in sites("choice"):
        off = _offset(payload, va)
        got = payload[off: off + len(before)]
        if got == before:
            states[label] = "retail"
        elif got == after:
            states[label] = "choice"
        elif label == "uniform_rule" and got == rule_form:
            states[label] = "rule"
        else:
            states[label] = "foreign"
    return states


def applied_mode(payload: bytes) -> str | None:
    """``"rule"`` / ``"choice"`` when the executable carries that form, else None."""

    try:
        states = _site_states(payload)
    except (UniformChoiceError, ValueError, struct.error):
        return None
    values = set(states.values())
    if values == {"choice"}:
        return "choice"
    if states["uniform_rule"] == "rule" and values == {"rule", "retail"}:
        return "rule"
    return None


def status(payload: bytes) -> str:
    try:
        states = _site_states(payload)
    except (UniformChoiceError, ValueError, struct.error):
        return "foreign"
    if set(states.values()) == {"retail"}:
        return "retail"
    return "applied" if applied_mode(payload) is not None else "foreign"


def apply(payload: bytes, mode: str = "choice") -> tuple[bytes, Mapping[str, object]]:
    _require(mode in MODES, f"unknown uniform form {mode!r}; choose from {MODES}")
    state = status(payload)
    if state == "applied":
        have = applied_mode(payload)
        if have == mode:
            return payload, {"already_applied": True, "mode": mode, "edits": [], "changed_bytes": 0}
        raise UniformChoiceError(f"the executable already carries the uniform {have!r} form; refusing to write {mode!r} over it")
    _require(state == "retail", f"uniform sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, va, _before, after in sites(mode):
        off = _offset(payload, va)
        buf[off: off + len(after)] = after
        touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "va": f"0x{va:x}", "file_offset": f"0x{off:x}", "bytes": len(after)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied" and applied_mode(patched) == mode, "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    receipt: dict[str, object] = {"mode": mode, "edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched)}
    if mode == "rule":
        receipt["rule_swap"] = RULE_SWAP
    else:
        receipt.update({"home_flip": f"0x{HOME_FLIP_VA:x}", "away_flip": f"0x{AWAY_FLIP_VA:x}", "away_value": f"0x{AWAY_VALUE_VA:x}",
                        "states_per_side": (LAST_SLOT + 1) * 2})
    return patched, receipt


def code_report() -> dict[str, object]:
    strip = lambda b: len(b.rstrip(b"\x90"))  # noqa: E731
    handlers = handler_bytes()
    return {"rule_block_code_bytes": strip(rule_block_bytes("choice")), "rule_block_capacity": RULE_BLOCK_SIZE,
            "handler_code_bytes": {k: strip(v) for k, v in handlers.items()},
            "handler_capacity": {"prev": PREV_SIZE, "next": NEXT_SIZE},
            "cave": None, "runtime_verified": False}


__all__ = ["UniformChoiceError", "MODES", "RULE_BLOCK_VA", "RULE_BLOCK_SIZE", "RULE_BLOCK_END_VA", "RULE_SWAP_VA", "RULE_SWAP",
           "RETAIL_RULE_BLOCK", "AWAY_LETTER_VA", "AWAY_LETTER_CALL_VA", "HOME_LETTER_CALL_VA", "RESET_VA", "RESET_TAIL_VA",
           "HOME_PREV_VA", "HOME_NEXT_VA", "AWAY_PREV_VA", "AWAY_NEXT_VA", "PREV_SIZE", "NEXT_SIZE",
           "HOME_FLIP_VA", "AWAY_FLIP_VA", "AWAY_VALUE_VA", "FLIP_TOGGLE", "HOME_SLOT_VA", "AWAY_SLOT_VA",
           "HOME_TEAM_PTR_VA", "AWAY_TEAM_PTR_VA", "HOME_ABBR_PTR_VA", "AWAY_ABBR_PTR_VA", "TEAM_YEARS_OFF", "LAST_SLOT",
           "apply", "applied_mode", "away_letter_bytes", "code_report", "handler_bytes", "reset_tail_bytes",
           "rule_block_bytes", "sites", "status"]
