"""ESPN 25th Anniversary moments keep the retail kickoff (USA Xbox). EXPERIMENTAL / UNWITNESSED.

Noah's recording of 2026-09-23 [v2 11:21]: "we have the new kickoff in this mode where we're playing an old game
so that needs to be fixed". The 2024-2026 kickoff is four owners: the kick rules (kickoff from the 35, touchback
to the 35), the kickoff alignment and the return assignments (playbook data in every book), and the dynamic
kickoff mechanics. All four are global, so the 25th Anniversary moments got them too.

The 25th Anniversary is game mode 8: the moment selection handler 20CB30 stores ``[0xE5FF80] = 8`` at 0x20CB59,
and no other mode uses 8. This allocator owner adds one mode-8 test in front of each part and changes nothing
anywhere else. Every trampoline saves EFLAGS (pushfd/popfd), so outside mode 8 each site continues exactly where
it went before this owner.

1. The dynamic kickoff (nfl2k5_dynamic_kickoff, legacy cave or relocated): its 20 hook sites jump to trampolines.
   Outside mode 8 each one jumps to the same cave label as before. In mode 8 it replays the displaced retail
   instruction(s) and continues retail, so no dynamic kickoff instruction runs in the 25th Anniversary. A single
   entry point is not enough: the pre-kick hold (held/aligned_roles) runs before the launch and would hold the
   players for good if only the launch were gated, because a contact would never be latched.
2. The kick rules (nfl2k5_kick_rules): the seven kickoff-spot fmul operands call one of two trampolines (the
   retail 1828.8 cm, the kicking 30, in mode 8); the touchback call goes through a trampoline that multiplies by
   the retail 2743.2 cm (the 20) in mode 8. The PAT stays where kick_rules put it (a DESIGN follow-up).
3. The kickoff alignment (playbook data): the two live formation-slot readers 0x190520 (line-up targets and
   routes) and 0x17FE60 (the play-call diagram) swap EDX to a retail shadow of a Kickoff or Kick Return record in
   mode 8, when the record carries the 2026 alignment (type 8 with slots 1 and 2 at +25 yd; type 9 with slot 0 at
   64 yd and slot 2 at 30 yd). The pointer never leaves the reader. The clones 0x1637E0 and 0x1837B0 have no
   callers. Safety Kick and the onside formations never match.
4. The return assignments (playbook data): at the entry of 0x18B8D0, the funnel that stores the called play for a
   team, a "Return Left/Middle/Right" play that carries the 2026 chains has its 11 (descriptor, chain) pairs
   replaced in place by the retail ones in mode 8; the play record stays in its book, so play-index code sees
   nothing new. The replaced pairs are saved in RW state and put back the next time that play is stored outside
   mode 8, in case the book is still resident.

E1 (b76-vb3, nfl2k5_kickoff_blocking; Build option kickoff_return_blocking, off in every preset): when asked, the
same allocation carries the kickoff return blocking rule. Outside mode 8 the block_target trampoline then enters
that rule instead of the cave's block_target (one blocker per coverage player, and a free blocker never waits); in
mode 8 the retail selector runs. The rule's first word keeps the cave label, so the view of the site stays the
dynamic kickoff's own hook. Without the option the trampoline forwards to the cave's block_target like every other
hook, so an NFL kickoff keeps the 2026 rule exactly. An installed gate keeps its setting; switching it needs a
rebuild from the base disc.

Data derived from the user's own disc at build time (never distributed): the retail Kickoff and Kick Return slot
blocks (identical in all 36 books) and the retail chains of the three return plays (pinned by
nfl2k5_kickoff_returns.RETAIL_PINS). Parts 1 and 2 re-point sites that nfl2k5_dynamic_kickoff (legacy and
relocated) and nfl2k5_kick_rules own; those recognizers read through this owner's trampolines with
``gate_views`` and keep their own bytes and rules. The old caves are never modified.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_kickoff_blocking as blocking
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_anniversary_kickoff"
CODE_SIZE = 3584                   # b76-vb3 E1: + the return blocking rule (nfl2k5_kickoff_blocking)
DATA_SIZE = 736                    # eight saved return plays: record pointer + 11 (descriptor, chain) pairs
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
UI_LABEL = "25th Anniversary: retail kickoff"
BUILD_CAPTION = "the retail kickoff in the 25th Anniversary moments"

MODE_VA = 0xE5FF80
ANNIVERSARY_MODE = 8
MOMENT_SELECT_MODE_STORE = (0x20CB59, bytes.fromhex("c70580ffe50008000000"))  # mov dword [0xE5FF80], 8

# Part 3: the two live formation-slot readers (identical code; FUN_00190520 and FUN_0017fe60).
READER_ENTRY = bytes.fromhex("5153578b7c2410")   # push ecx; push ebx; push edi; mov edi,[esp+0x10]
READER_SITES = (("reader_lineup", 0x190520), ("reader_diagram", 0x17FE60))
KICKOFF_TYPE, KICK_RETURN_TYPE = 8, 9
RECORD_SIZE = 0xB4
SLOT_BASE, SLOT_STRIDE = 0x1A, 14
COVERAGE_Z = 2286                  # 25 yd: the 2026 coverage line (nfl2k5_kickoff_alignment COVERAGE_LINE_YD)
RETURNER_Z = 5852                  # 64 yd: the deep returner (RETURNER_DEEP_YD)
RESTRAINING_Z = 2743               # 30 yd: the restraining line (RESTRAINING_LINE_YD)

# Part 4: the play store FUN_0018b8d0 (fastcall: ECX team, EDX play record).
PLAY_SITE = ("play_store", 0x18B8D0, bytes.fromhex("83ec085355"))
PLAY_SIZE = 0x60
RETURN_PLAYS = ("Return Left", "Return Middle", "Return Right")
SAVE_ENTRIES = 8
SAVE_ENTRY = 4 + 88

GATE_CMP = b"\x83\x3d" + struct.pack("<I", MODE_VA) + bytes((ANNIVERSARY_MODE,))   # cmp dword [MODE], 8
KICK_FLAGS_KEY = "_kick_flags"     # forwards entry: the dynamic kickoff's state byte (E1 reads the kicking direction)


class AnniversaryKickoffError(ValueError):
    """Missing prerequisites, foreign sites, or disc data that is not the retail special-teams data."""


def require(condition, message):
    if not condition:
        raise AnniversaryKickoffError(message)


def _kickoff():
    from . import nfl2k5_dynamic_kickoff as kickoff
    return kickoff


def _kick_rules():
    from . import nfl2k5_kick_rules as kick_rules
    return kick_rules


def kickoff_hooks():
    """(name, va, retail bytes) of the dynamic kickoff's 20 hook sites, in the owner's order."""
    return tuple((name, va, original) for name, (va, original) in _kickoff().HOOKS.items())


def kick_rule_sites():
    """(label, va, kind) of the seven kickoff-spot fmul sites; kind 'pos' or 'neg'."""
    return tuple((label, va, kind) for label, va, _const, kind in _kick_rules().KICKOFF_SITES)


# --------------------------------------------------------------------------------------------- disc data
@dataclass(frozen=True)
class PlayTable:
    name: str
    descriptors: tuple[int, ...]           # 11 retail descriptors
    chains: tuple[bytes, ...]              # 11 retail node runs (8 bytes a node)
    fingerprint: bytes                     # the 2026 chains of slots 0 and 1 (2 x 32 bytes)


@dataclass(frozen=True)
class DiscTables:
    kickoff_record: bytes                  # 0xB4, retail slot block, +0..+3 zero (the name pointer is unused)
    return_record: bytes
    plays: tuple[PlayTable, ...]

    def digest(self):
        h = hashlib.sha256()
        h.update(self.kickoff_record + self.return_record)
        for play in self.plays:
            h.update(play.name.encode("utf-8") + struct.pack("<11I", *play.descriptors) + b"".join(play.chains)
                     + play.fingerprint)
        return h.hexdigest()


def disc_tables(source):
    """The retail special-teams data from a user's disc image or extraction (read only).

    The Kickoff and Kick Return slot blocks must agree in every book once x and depth are read as retail (the
    alignment tool only rewrites those columns). The three return plays must be at their retail pins in every
    book; the 2026 fingerprints are the chains nfl2k5_kickoff_returns compiles from them."""
    from tools import nfl2k5_kickoff_alignment as alignment
    from . import nfl2k5_kickoff_returns as returns
    from . import nfl2k5_play_codec as codec
    from . import nfl2k5_play_library as lib
    from .nfl2k5_playbook_inspector import RESOURCE_HEADER_SIZE
    shadows = {alignment.KICKOFF_NAME: set(), alignment.KICK_RETURN_NAME: set()}
    plays = {}
    with alignment.recode.OuterImage(source) as archive:
        loaded = alignment._load(archive)
        for book, refs in loaded:
            raw = archive.read_entry(book.entry_index)
            body = raw[RESOURCE_HEADER_SIZE:]
            for name, xz in ((alignment.KICKOFF_NAME, alignment.RETAIL_KICKOFF_XZ),
                             (alignment.KICK_RETURN_NAME, alignment.RETAIL_KICK_RETURN_XZ)):
                ref = refs[name]
                record = ref.body_offset - SLOT_BASE
                slots = alignment.with_xz(ref.slots, xz)
                shadows[name].add(bytes(4) + body[record + 4:record + SLOT_BASE] + slots)
            parsed, rows, state = returns._inspect(raw)
            require(state == "retail", f"{book.name}: the return plays are {state}; read the retail source disc")
            for play, _state, target in rows:
                flags, chains = lib.play_chains(body, play.index)
                new = [b"".join(n.to_bytes() for n in codec.encode_chain(c)) for c in target]
                row = (tuple(d for d, _ in chains), tuple(b"".join(nodes) for _, nodes in chains), new[0] + new[1])
                plays.setdefault(play.name, set()).add(row)
    for name, found in shadows.items():
        require(len(found) == 1, f"the {name} slot blocks differ between books")
    require(set(plays) == set(RETURN_PLAYS), "the three return plays were not found")
    tables = []
    for name in RETURN_PLAYS:
        require(len(plays[name]) == 1, f"{name} differs between books")
        descriptors, chains, fingerprint = next(iter(plays[name]))
        require(len(descriptors) == 11 and all(len(c) == 8 * (d & 0xF) for d, c in zip(descriptors, chains)),
                f"{name}: unexpected chain lengths")
        require(len(fingerprint) == 64, f"{name}: the 2026 returner chains are not four nodes each")
        tables.append(PlayTable(name, descriptors, chains, fingerprint))
    kickoff_record = next(iter(shadows[alignment.KICKOFF_NAME]))
    return_record = next(iter(shadows[alignment.KICK_RETURN_NAME]))
    require(len(kickoff_record) == RECORD_SIZE and len(return_record) == RECORD_SIZE, "formation record size")
    require(_type(kickoff_record) == KICKOFF_TYPE and _type(return_record) == KICK_RETURN_TYPE, "formation types")
    return DiscTables(kickoff_record, return_record, tuple(tables))


def _type(record):
    return (struct.unpack_from("<I", record, 4)[0] >> 8) & 0x3F


def _z(record, slot):
    return struct.unpack_from("<h", record, SLOT_BASE + SLOT_STRIDE * slot + 8)[0]


# --------------------------------------------------------------------------------------------- code
def _imm(value):
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def _kickoff_trampoline(a, name, va, original, forward, e1=False):
    a.label("k_" + name)
    a.b("9c" + GATE_CMP.hex() + "7406" + "9d")
    if name == "block_target" and e1:
        a.j32("e9", blocking.ENTRY)       # E1 (option): outside mode 8 the return blocking rule chooses the target
    else:
        a.jmp_abs(forward)
    a.b("9d")
    if original[0] == 0xE9:
        # commentary: the displaced instruction is itself a relative jmp thunk; replay its target
        a.jmp_abs(va + 5 + struct.unpack_from("<i", original, 1)[0])
    else:
        a.b(original.hex())
        a.jmp_abs(va + len(original))


def code_for(code_va, data_va, forwards, touchback, tables, *, e1=False):
    """(code bytes filling CODE_SIZE, labels) for one installation.

    ``forwards`` maps each kickoff hook name to the cave label its site jumped to; ``touchback`` is kick_rules'
    touchback label. The tables follow the code in the same RX allocation. ``e1`` adds the kickoff return blocking
    rule (nfl2k5_kickoff_blocking, a Build option for Noah's feel test): without it the block_target trampoline
    forwards to the cave's own rule outside mode 8, exactly as before E1."""
    kr = _kick_rules()
    a = _Asm(code_va)
    for name, va, original in kickoff_hooks():
        _kickoff_trampoline(a, name, va, original, forwards[name], e1)
    for label, kick_float, retail in (("kr_pos", kr.FLOAT_KICKOFF_POS, kr.RETAIL_KICKOFF_CONST),
                                      ("kr_neg", kr.FLOAT_KICKOFF_NEG, kr.RETAIL_KICKOFF_NEG_CONST)):
        a.label(label)
        a.b("9c" + GATE_CMP.hex() + "7408" + "9d" + "d80d" + _imm(kick_float) + "c3"
            + "9d" + "d80d" + _imm(retail) + "c3")
    a.label("kr_tb")
    a.b("9c" + GATE_CMP.hex() + "7406" + "9d")
    a.jmp_abs(touchback)
    a.b("9d" + "d80d" + _imm(kr.RETAIL_TOUCHBACK_CONST) + "c3")
    # Part 3: the two readers, then the shared record test (EDX in/out; EAX preserved; flags restored by the caller).
    for label, va in READER_SITES:
        a.label("f_" + label)
        a.b("9c")
        a.j32("e8", "era_formation")
        a.b("9d" + READER_ENTRY.hex())
        a.jmp_abs(va + len(READER_ENTRY))
    a.label("era_formation")
    a.b(GATE_CMP.hex()); a.j8("75", "formation_ret")
    a.b("50" + "8b4204" + "c1e808" + "83e03f" + "83f808"); a.j8("75", "formation_return")
    a.b("66817a30" + struct.pack("<H", COVERAGE_Z).hex()); a.j8("75", "formation_done")
    a.b("66817a3e" + struct.pack("<H", COVERAGE_Z).hex()); a.j8("75", "formation_done")
    a.b("ba"); a.items.append(("abs", "shadow_kickoff")); a.j8("eb", "formation_done")
    a.label("formation_return")
    a.b("83f809"); a.j8("75", "formation_done")
    a.b("66817a22" + struct.pack("<H", RETURNER_Z).hex()); a.j8("75", "formation_done")
    a.b("66817a3e" + struct.pack("<H", RESTRAINING_Z).hex()); a.j8("75", "formation_done")
    a.b("ba"); a.items.append(("abs", "shadow_return"))
    a.label("formation_done"); a.b("58")
    a.label("formation_ret"); a.b("c3")
    # Part 4: the play store. pushad keeps every register; era_play works on ESI = the play record.
    label, va, original = PLAY_SITE
    a.label("p_" + label)
    a.b("9c" + "60" + "89d6")
    a.j32("e8", "era_play")
    a.b("61" + "9d" + original.hex())
    a.jmp_abs(va + len(original))
    a.label("era_play")
    a.b("fc" + "89f2" + "85d2"); a.j32("0f84", "play_ret")
    a.b("8b1a" + "85db"); a.j32("0f84", "play_ret")
    a.b("31ed")
    a.label("play_name")
    a.b("89de" + "8b3cad"); a.items.append(("abs", "name_pointers"))
    a.b("8b0cad"); a.items.append(("abs", "name_lengths"))
    a.b("f3a6"); a.j8("74", "play_found")
    a.b("45" + "83fd03"); a.j8("72", "play_name")
    a.j32("e9", "play_ret")
    a.label("play_found")
    # Already carrying this owner's retail chains?  (slot 0's chain inside this RX allocation)
    a.b("8b420c" + "2d" + _imm(code_va) + "3d" + _imm(CODE_SIZE)); a.j32("0f82", "play_patched")
    a.b(GATE_CMP.hex()); a.j32("0f85", "play_ret")
    a.b("8b4218" + "83e00f" + "83f802"); a.j32("0f85", "play_ret")        # slot 2: the 2026 two-node chain
    a.b("6bc540" + "8db8"); a.items.append(("abs", "fingerprints"))      # edi = fingerprint[p]
    a.b("8b720c" + "b908000000" + "f3a7"); a.j32("0f85", "play_ret")
    a.b("8b7214" + "b908000000" + "f3a7"); a.j32("0f85", "play_ret")
    # Choose a save entry: this record's, else a free one, else entry 0.
    a.b("bf" + _imm(data_va) + "b908000000")
    a.label("save_same"); a.b("3917"); a.j8("74", "save_use"); a.b("83c75c" + "49"); a.j8("75", "save_same")
    a.b("bf" + _imm(data_va) + "b908000000")
    a.label("save_free"); a.b("833f00"); a.j8("74", "save_use"); a.b("83c75c" + "49"); a.j8("75", "save_free")
    a.b("bf" + _imm(data_va))
    a.label("save_use")
    a.b("8917" + "8d7208" + "83c704" + "b916000000" + "f3a5")          # key, then the 2026 pairs
    a.b("6bf558" + "81c6"); a.items.append(("abs", "retail_pairs"))
    a.b("8d7a08" + "b916000000" + "f3a5")                              # the retail pairs into the record
    a.j32("e9", "play_ret")
    a.label("play_patched")
    a.b(GATE_CMP.hex()); a.j32("0f84", "play_ret")
    a.b("bf" + _imm(data_va) + "b908000000")
    a.label("restore_find"); a.b("3917"); a.j8("74", "restore_use"); a.b("83c75c" + "49"); a.j8("75", "restore_find")
    a.j32("e9", "play_ret")
    a.label("restore_use")
    a.b("89f8" + "8d7004" + "8d7a08" + "b916000000" + "f3a5" + "c700" + _imm(0))   # restore, then free the entry
    a.label("play_ret"); a.b("c3")
    # E1 (nfl2k5_kickoff_blocking, optional): the return blocking rule, entered from the block_target trampoline
    # outside mode 8.
    if e1:
        blocking.emit(a, cave_target=forwards["block_target"], flags=forwards.get(KICK_FLAGS_KEY, 0))
    return _finish(a, code_va, data_va, tables)


class _TableAsm(_Asm):
    """_Asm plus 4-byte absolute references to labels ("abs", label)."""

    def _size(self, item):
        if isinstance(item, tuple) and item[0] == "abs":
            return 4
        return super()._size(item)


def _finish(a, code_va, data_va, tables):
    # Promote the plain assembler to one that understands absolute label words.
    t = _TableAsm(code_va)
    t.items = list(a.items)
    t.items.append(("align4",))
    blob = _tables(tables)
    for name, offset, size in blob["layout"]:
        t.items.append(("label_at", name, offset))
    t.items.append(blob["bytes"])
    out = _assemble(t, code_va)
    require(len(out[0]) <= CODE_SIZE, f"the 25th Anniversary kickoff code is {len(out[0])} bytes, over {CODE_SIZE}")
    return out[0].ljust(CODE_SIZE, b"\xcc"), out[1]


def _assemble(a, code_va):
    # Two passes: label offsets, then bytes. Table labels are relative to the aligned table start.
    pos, labels, table_start = 0, {}, None
    for item in a.items:
        if isinstance(item, tuple) and item[0] == "label":
            labels[item[1]] = pos
            continue
        if isinstance(item, tuple) and item[0] == "align4":
            pos = (pos + 3) & ~3
            table_start = pos
            continue
        if isinstance(item, tuple) and item[0] == "label_at":
            labels[item[1]] = table_start + item[2]
            continue
        pos += a._size(item)
    a.labels = labels
    out = bytearray()
    for item in a.items:
        if isinstance(item, tuple) and item[0] in ("label", "label_at"):
            continue
        if isinstance(item, tuple) and item[0] == "align4":
            out += b"\xcc" * ((-len(out)) % 4)
            continue
        here = len(out)
        if isinstance(item, bytes):
            out += item
        elif item[0] == "abs":
            out += struct.pack("<I", code_va + labels[item[1]])
        elif item[0] == "j8":
            rel = labels[item[2]] - (here + 2)
            require(-128 <= rel <= 127, f"rel8 out of range for {item[2]}")
            out += item[1] + struct.pack("<b", rel)
        elif item[0] == "j32":
            rel = labels[item[2]] - (here + len(item[1]) + 4)
            out += item[1] + struct.pack("<i", rel)
        elif item[0] == "call":
            out += b"\xe8" + struct.pack("<i", item[1] - (code_va + here + 5))
        elif item[0] == "jmpabs":
            out += b"\xe9" + struct.pack("<i", item[1] - (code_va + here + 5))
        else:
            raise AnniversaryKickoffError(f"unknown assembler item {item[0]}")
    code = bytes(out)
    return code, {name: code_va + offset for name, offset in labels.items()}


def _tables(tables):
    """The RX tables: two shadow records, three names, the fingerprints, the retail pairs and their nodes.

    Offsets are relative to the aligned table start; pointers inside the tables are written by _patch_pointers
    once the table address is known, so the layout here only reserves them."""
    parts, layout = bytearray(), []

    def put(name, data, align=4):
        parts.extend(b"\0" * ((-len(parts)) % align))
        layout.append((name, len(parts), len(data)))
        parts.extend(data)

    put("shadow_kickoff", tables.kickoff_record)
    put("shadow_return", tables.return_record)
    names = [(play.name + "\0").encode("utf-16le") for play in tables.plays]
    for i, raw in enumerate(names):
        put(f"name_{i}", raw)
    put("name_pointers", bytes(12))                   # filled with absolute pointers below
    put("name_lengths", struct.pack("<3I", *(len(raw) for raw in names)))
    put("fingerprints", b"".join(play.fingerprint for play in tables.plays))
    put("retail_pairs", bytes(88 * 3))               # descriptors plus absolute chain pointers, below
    for p, play in enumerate(tables.plays):
        for slot, chain in enumerate(play.chains):
            put(f"chain_{p}_{slot}", chain)
    return {"bytes": bytes(parts), "layout": layout}


def _patch_pointers(code, labels, tables):
    """Write the absolute pointers the tables hold (name pointers, retail chain pointers)."""
    buf = bytearray(code)
    code_va = labels["k_launch"]
    for i in range(3):
        struct.pack_into("<I", buf, labels["name_pointers"] - code_va + 4 * i, labels[f"name_{i}"])
    for p, play in enumerate(tables.plays):
        for slot in range(11):
            at = labels["retail_pairs"] - code_va + 88 * p + 8 * slot
            struct.pack_into("<II", buf, at, play.descriptors[slot], labels[f"chain_{p}_{slot}"])
    return bytes(buf)


def build_code(code_va, data_va, forwards, touchback, tables, *, e1=False):
    code, labels = code_for(code_va, data_va, forwards, touchback, tables, e1=e1)
    require(labels["k_launch"] == code_va, "the first trampoline must open the allocation")
    return _patch_pointers(code, labels, tables), labels


# --------------------------------------------------------------------------------------------- sites
def _read(image, va, size):
    return image.read(va, size)


def _owned(payload):
    """The code and data allocations, or None when the image has no allocator or no allocation for this owner.
    A foreign allocator layout raises."""
    state = space.status(payload)
    if state == "retail":
        return None
    require(state == "applied", "the executable's extra-space layout is foreign")
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    if not rows:
        return None
    code = [a for a in rows if a["kind"] == "code"]
    data = [a for a in rows if a["kind"] == "data"]
    if len(code) != 1 or len(data) != 1 or len(rows) != 2:
        return None
    require(code[0]["size"] == CODE_SIZE and data[0]["size"] == DATA_SIZE,
            "foreign 25th Anniversary kickoff allocation sizes")
    return code[0], data[0]


def _rel_target(site_va, raw):
    return site_va + 5 + struct.unpack_from("<i", raw, 1)[0]


def _kickoff_view(image, lo, hi, name, va, original):
    """The canonical dynamic-kickoff site bytes behind one of this owner's trampolines, else None."""
    raw = _read(image, va, len(original))
    if raw[0] != 0xE9:
        return None
    t = _rel_target(va, raw)
    if not lo <= t < hi:
        return None
    body = _read(image, t, 17)
    if body[:1] != b"\x9c" or body[1:8] != GATE_CMP or body[8:11] != b"\x74\x06\x9d" or body[11] != 0xE9 or body[16] != 0x9D:
        return None
    forward = t + 16 + struct.unpack_from("<i", body, 12)[0]
    if lo <= forward < hi:
        # E1: the trampoline enters the return blocking rule; the word before it keeps the cave label it replaced
        forward = struct.unpack("<I", _read(image, forward - 4, 4))[0]
    tail_len = 5 if original[0] == 0xE9 else len(original) + 5
    tail = _read(image, t + 17, tail_len)
    if original[0] == 0xE9:
        if tail[0] != 0xE9 or _rel_target(t + 17, tail) != _rel_target(va, original):
            return None
    else:
        if tail[:len(original)] != original or tail[len(original)] != 0xE9 \
                or _rel_target(t + 17 + len(original), tail[len(original):]) != va + len(original):
            return None
    return b"\xe9" + struct.pack("<i", forward - (va + 5)) + raw[5:]


def _fmul_view(image, lo, hi, va):
    raw = _read(image, va, 6)
    if raw[0] != 0xE8 or raw[5] != 0x90:
        return None
    t = _rel_target(va, raw)
    if not lo <= t < hi:
        return None
    body = _read(image, t, 26)
    if body[:1] != b"\x9c" or body[1:8] != GATE_CMP or body[8:11] != b"\x74\x08\x9d" or body[11:13] != b"\xd8\x0d" \
            or body[17] != 0xC3 or body[18] != 0x9D or body[19:21] != b"\xd8\x0d" or body[25] != 0xC3:
        return None
    return b"\xd8\x0d" + body[13:17]


def _touchback_view(image, lo, hi, va):
    raw = _read(image, va, 6)
    if raw[0] != 0xE8 or raw[5] != 0x90:
        return None
    t = _rel_target(va, raw)
    if not lo <= t < hi:
        return None
    body = _read(image, t, 24)
    if body[:1] != b"\x9c" or body[1:8] != GATE_CMP or body[8:11] != b"\x74\x06\x9d" or body[11] != 0xE9 \
            or body[16] != 0x9D or body[17:19] != b"\xd8\x0d" or body[23] != 0xC3:
        return None
    forward = t + 16 + struct.unpack_from("<i", body, 12)[0]
    return b"\xe8" + struct.pack("<i", forward - (va + 5)) + b"\x90"


def gate_views(payload):
    """{site va: the bytes the gated owner wrote there} for every dynamic-kickoff and kick-rules site that jumps
    into this owner's trampolines. Empty when this owner is not installed. Recognizers of those owners read
    their sites through this mapping, so a gated image still reads as their own installation."""
    from . import nfl2k5_era_rules as era
    try:
        payload = era.underlying_view(payload)
        owned = _owned(payload)
    except (ValueError, KeyError, IndexError, struct.error):
        return {}
    if owned is None:
        return {}
    code, _ = owned
    lo, hi = code["va"], code["va"] + CODE_SIZE
    image = XbeImage(payload)
    views = {}
    try:
        for name, va, original in kickoff_hooks():
            view = _kickoff_view(image, lo, hi, name, va, original)
            if view is not None:
                views[va] = view
        for _label, va, _kind in kick_rule_sites():
            view = _fmul_view(image, lo, hi, va)
            if view is not None:
                views[va] = view
        view = _touchback_view(image, lo, hi, _kick_rules().TOUCHBACK_SITE_VA)
        if view is not None:
            views[_kick_rules().TOUCHBACK_SITE_VA] = view
    except (ValueError, struct.error, IndexError):
        return {}
    return views


def _site_edits(payload, labels):
    """(label, va, before, after) for all 31 sites, from the ungated installation to the gated one."""
    kr = _kick_rules()
    image = XbeImage(payload)
    edits = []
    for name, va, original in kickoff_hooks():
        before = _read(image, va, len(original))
        after = b"\xe9" + struct.pack("<i", labels["k_" + name] - (va + 5)) + before[5:]
        edits.append(("kickoff_" + name, va, before, after))
    for label, va, kind in kick_rule_sites():
        before = _read(image, va, 6)
        target = labels["kr_pos" if kind == "pos" else "kr_neg"]
        edits.append(("kick_rules_" + label, va, before, b"\xe8" + struct.pack("<i", target - (va + 5)) + b"\x90"))
    va = kr.TOUCHBACK_SITE_VA
    before = _read(image, va, 6)
    edits.append(("kick_rules_touchback", va, before, b"\xe8" + struct.pack("<i", labels["kr_tb"] - (va + 5)) + b"\x90"))
    for label, va in READER_SITES:
        before = _read(image, va, len(READER_ENTRY))
        edits.append((label, va, before, b"\xe9" + struct.pack("<i", labels["f_" + label] - (va + 5)) + b"\x90\x90"))
    label, va, original = PLAY_SITE
    edits.append((label, va, _read(image, va, len(original)),
                  b"\xe9" + struct.pack("<i", labels["p_" + label] - (va + 5))))
    return edits


def _forwards(payload):
    """The cave labels the ungated dynamic-kickoff hooks and the kick-rules touchback call jump to."""
    image = XbeImage(payload)
    forwards = {}
    for name, va, original in kickoff_hooks():
        raw = _read(image, va, len(original))
        require(raw[0] == 0xE9 and raw[5:] == b"\x90" * (len(original) - 5),
                f"the dynamic kickoff's {name} hook is not a plain jump")
        forwards[name] = _rel_target(va, raw)
    # E1: the block rule reads the cave's kicking-direction flag byte (legacy data or the relocated state).
    _scope, forwards[KICK_FLAGS_KEY] = blocking.cave_parameters(image, forwards["block_target"])
    kr = _kick_rules()
    raw = _read(image, kr.TOUCHBACK_SITE_VA, 6)
    require(raw[0] == 0xE8 and raw[5] == 0x90, "the kick rules' touchback call is missing")
    return forwards, _rel_target(kr.TOUCHBACK_SITE_VA, raw)


def _ungated(payload, views):
    """The payload with every gated site read back to the gated owner's own bytes."""
    if not views:
        return payload
    image = XbeImage(payload)
    buf = bytearray(payload)
    for va, view in views.items():
        at = image.offset(va, len(view))
        buf[at:at + len(view)] = view
    for label, va in READER_SITES:
        at = image.offset(va, len(READER_ENTRY))
        buf[at:at + len(READER_ENTRY)] = READER_ENTRY
    label, va, original = PLAY_SITE
    at = image.offset(va, len(original))
    buf[at:at + len(original)] = original
    # Reseal: the allocator (and so the relocated kickoff's recognizer) verifies every section digest.
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


def _prerequisites(payload):
    state = _kickoff().status(payload)
    require(state == "applied", f"the dynamic kickoff is {state}; the 25th Anniversary gate follows it")
    rules = _kick_rules().status(payload)
    require(rules == "applied", f"the kick rules are {rules}; the 25th Anniversary gate needs the 2026 spots")
    image = XbeImage(payload)
    va, pin = MOMENT_SELECT_MODE_STORE
    require(image.read(va, len(pin)) == pin, "the moment selection no longer stores game mode 8")


def status(payload):
    """'retail' (no allocation contents and no gated site), 'applied', or 'foreign'."""
    from . import nfl2k5_era_rules as era
    try:
        payload = era.underlying_view(payload)
        owned = _owned(payload)
        if owned is None:
            return "retail"
        code, data = owned
        body = payload[code["raw"]:code["raw"] + CODE_SIZE]
        views = gate_views(payload)
        image = XbeImage(payload)
        readers = {va: image.read(va, len(READER_ENTRY)) for _label, va in READER_SITES}
        play = image.read(PLAY_SITE[1], len(PLAY_SITE[2]))
        if body == b"\xcc" * CODE_SIZE:
            ungated = all(r == READER_ENTRY for r in readers.values()) and play == PLAY_SITE[2] and not views
            return "retail" if ungated else "foreign"
        if len(views) != len(kickoff_hooks()) + len(kick_rule_sites()) + 1:
            return "foreign"
        base = _ungated(payload, views)
        _prerequisites(base)
        forwards, touchback = _forwards(base)
        for e1 in (False, True):
            try:
                tables = _tables_from_code(body, code["va"], e1)
            except AnniversaryKickoffError:
                continue
            expected, labels = build_code(code["va"], data["va"], forwards, touchback, tables, e1=e1)
            if body != expected:
                continue
            for label, va, before, after in _site_edits(base, labels):
                if image.read(va, len(after)) != after:
                    return "foreign"
            return "applied"
        return "foreign"
    except (AnniversaryKickoffError, ValueError, KeyError, IndexError, struct.error, TypeError):
        return "foreign"


def installed_blocking(payload):
    """True when the installed gate carries E1 (the return blocking option), False when not, None if not applied."""
    if status(payload) != "applied":
        return None
    code, data = _owned(payload)
    body = payload[code["raw"]:code["raw"] + CODE_SIZE]
    base = _ungated(payload, gate_views(payload))
    forwards, touchback = _forwards(base)
    for e1 in (False, True):
        try:
            tables = _tables_from_code(body, code["va"], e1)
        except AnniversaryKickoffError:
            continue
        if build_code(code["va"], data["va"], forwards, touchback, tables, e1=e1)[0] == body:
            return e1
    return None


def installed_tables(payload):
    """The DiscTables an installed gate carries (a rebuild over a built disc reuses them), else None."""
    e1 = installed_blocking(payload)
    if e1 is None:
        return None
    code, _data = _owned(payload)
    return _tables_from_code(payload[code["raw"]:code["raw"] + CODE_SIZE], code["va"], e1)


def _tables_from_code(body, code_va, e1=False):
    """Recover the DiscTables an installed allocation carries, by walking its own table layout."""
    # The layout is deterministic from the tables' sizes: rebuild it with each candidate size read back.
    # Shadows sit at the aligned table start; find it from the code length of a probe assembly.
    probe_tables = DiscTables(bytes(RECORD_SIZE), bytes(RECORD_SIZE), tuple(
        PlayTable(name, (1,) * 11, (bytes(8),) * 11, bytes(64)) for name in RETURN_PLAYS))
    forwards = {name: code_va for name, _va, _o in kickoff_hooks()}
    _code, labels = code_for(code_va, code_va, forwards, code_va, probe_tables, e1=e1)
    start = labels["shadow_kickoff"] - code_va
    kickoff_record = body[start:start + RECORD_SIZE]
    return_record = body[start + RECORD_SIZE:start + 2 * RECORD_SIZE]
    pairs_at = labels["retail_pairs"] - code_va
    fingerprints_at = labels["fingerprints"] - code_va
    plays = []
    for p, name in enumerate(RETURN_PLAYS):
        descriptors, chains = [], []
        for slot in range(11):
            descriptor, pointer = struct.unpack_from("<II", body, pairs_at + 88 * p + 8 * slot)
            at = pointer - code_va
            require(0 <= at <= CODE_SIZE - 8 * (descriptor & 0xF), "retail chain pointer outside the allocation")
            descriptors.append(descriptor)
            chains.append(body[at:at + 8 * (descriptor & 0xF)])
        plays.append(PlayTable(name, tuple(descriptors), tuple(chains),
                               body[fingerprints_at + 64 * p:fingerprints_at + 64 * (p + 1)]))
    return DiscTables(kickoff_record, return_record, tuple(plays))


def apply(payload, tables, *, blocking=False):
    """Install on an image carrying the dynamic kickoff and the kick rules, or replay an installed copy.

    ``blocking`` adds E1, the kickoff return blocking rule (Build option ``kickoff_return_blocking``, off by
    default): without it every NFL kickoff keeps the dynamic kickoff's own block_target rule."""
    require(isinstance(tables, DiscTables), "pass the DiscTables read from the user's retail disc")
    require(type(blocking) is bool, "blocking must be a boolean")
    state = status(payload)
    require(state in ("retail", "applied"), f"the 25th Anniversary kickoff gate is {state}")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, label=UI_LABEL,
                  rx_bytes=CODE_SIZE, rw_bytes=DATA_SIZE, mode_va=hex(MODE_VA), mode=ANNIVERSARY_MODE,
                  tables_sha256=tables.digest(), kickoff_return_blocking=blocking)
    if state == "applied":
        require(installed_blocking(payload) is blocking,
                "an installed 25th Anniversary gate has the other return-blocking setting; rebuild from base")
        require(installed_tables(payload) == tables, "an installed 25th Anniversary gate carries different disc data; rebuild")
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    _prerequisites(payload)
    forwards, touchback = _forwards(payload)
    image = XbeImage(payload)
    for label, va in READER_SITES:
        require(image.read(va, len(READER_ENTRY)) == READER_ENTRY, f"{label} at {va:#x} is not the retail reader")
    require(image.read(PLAY_SITE[1], len(PLAY_SITE[2])) == PLAY_SITE[2], "the play store entry is not retail")
    if space.status(payload) == "retail":
        allocated, receipt = space.apply(payload, REQUESTS)
    else:
        require(_owned(payload) is not None, "reserve the 25th Anniversary kickoff gate with the complete owner union")
        allocated, receipt = payload, {}
    code, data = _owned(allocated)
    content, labels = build_code(code["va"], data["va"], forwards, touchback, tables, e1=blocking)
    result, _ = space.install_code(allocated, OWNER, content)
    image = XbeImage(result)
    buffer = bytearray(result)
    edits = _site_edits(result, labels)
    for _label, va, before, after in edits:
        at = image.offset(va, len(before))
        buffer[at:at + len(after)] = after
    for section in _sections(buffer):
        buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    result = bytes(buffer)
    require(status(result) == "applied", "25th Anniversary kickoff gate postcondition failed")
    require(_kickoff().status(result) == "applied" and _kick_rules().status(result) == "applied",
            "the gated owners no longer read as applied")
    return result, dict(common, status="applied", allocation=receipt,
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
        code_bytes=len(content.rstrip(b"\xcc")), code_va=hex(code["va"]), data_va=hex(data["va"]),
        edits=[dict(label=label, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
               for label, va, before, after in edits]
              + [dict(label="owned_code", va=hex(code["va"]), size=CODE_SIZE),
                 dict(label="owned_state", va=hex(data["va"]), size=DATA_SIZE)],
        reservations=space.reservations(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("status")
    p.add_argument("xbe", type=Path)
    p = sub.add_parser("apply")
    p.add_argument("xbe", type=Path)
    p.add_argument("source", type=Path, help="the user's retail disc image or extraction (special-teams data)")
    p.add_argument("output", type=Path)
    p.add_argument("--return-blocking", action="store_true",
                   help="also install E1, the kickoff return blocking rule (Build option kickoff_return_blocking)")
    args = parser.parse_args(argv)
    require(args.xbe.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.xbe.read_bytes()
    if args.command == "apply":
        result, receipt = apply(payload, disc_tables(args.source), blocking=args.return_blocking)
        with args.output.open("xb") as stream:
            stream.write(result)
    else:
        receipt = dict(status=status(payload), kickoff_return_blocking=installed_blocking(payload), owner=OWNER,
                       experimental=True, runtime_witnessed=False)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
