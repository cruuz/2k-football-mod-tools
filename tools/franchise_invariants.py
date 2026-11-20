#!/usr/bin/env python3
"""Check the franchise invariants I1 to I9 and I11 (beta 81 qb34 design, section 4.3) on a save or on live memory.

    python3 tools/franchise_invariants.py SIGNED_FOLDER_OR_SAVEGAME.DAT [--strict] [--out report.json]
    python3 tools/franchise_invariants.py --memory IMAGE [--root 0x...] [--ir-store 0x... | --xbe default.xbe]

Both inputs become one small *league view* (``view_from_save`` / ``view_from_memory``) and every check is written
once, over that view (``check``). Pure Python; no game code runs. Output: a JSON document with one row per violation
(invariant, severity, club, player index and name, values), a summary line, and the exit status 0 clean, 1 warnings
only, 2 failures (``--strict`` makes a warning a failure).

The invariants, as checked here (DESIGN 4.3; the harness checks I10 itself):

I1  active count per club: more than 53 in stages 8 and 9, or more than 65 otherwise, fails; under 42 fails; under 50
    warns. The count is the club's own count byte (+0x11C).
I2  ownership: a primary player index held twice across the 32 active lists, the practice squads, the full IR (save:
    every legacy cell and extension entry; memory: the IR owner's store, else the 5-slot table) and the free-agent
    list. A player on his own club's IR and active list is I7's case and is not counted twice here; any other second
    holder (another club's IR, another active list, a practice squad, the free-agent list) is I2. A pointer that does
    not name a primary record is reported under I2 as well.
I3  payroll: each club's stored payroll (+0x124) equals the game's recount (0xC3F00: the active list's contract charge,
    players with no years left charged nothing, plus the IR charge 0x246F20 in franchise mode), failure; a club that
    is not human-controlled over the cap warns.
I4  depth rows, in stages 7, 8 and 9, on managed clubs (not human, or "CPU manages my depth chart" 0xE60140 on): at
    every position (+0x35) the 3-bit rank rows (+0x28 bits 10-12) are exactly 0..n-1, with row 7 the shared overflow
    (the sorted rows are [min(i, 7) for i in range(n)]); and no injured player (+0x20 bit 31, the standard lineup
    roles partition's own test) at row 0 while a healthy one exists at that position. A human club's chart is the
    user's and the game leaves it as shipped (the retail opening save, all 32 clubs human, has 56 positions with
    repeated rows or holes), and the offseason resorts nothing before the season-start pass (the retail year-7
    offseason save has 72 such positions on CPU clubs); every managed chart in stages 7-9 of 413 signed 128 MB saves
    is clean. Human-club anomalies are listed in ``info``, not as violations. 64 MB and retail executables have no
    injured-player partition: use ``--skip I4.injured_row0`` for their saves.
I5  every club has at least one quarterback, kicker and punter on the active list (failure); exactly one quarterback
    warns.
I6  in stages 7, 8 and 9, no player on an active list, a practice squad or IR has a contract of zero length (+0x27 & 15,
    the divisor of the release routine 0x2BCF60, which leaves both nibbles zero: the 61001 crash) -- failure; one with
    zero years left (+0x24 & 15) but a length warns: the base game keeps such expired contracts on its rosters from the
    second season on (9 to 123 a league in the recorded standard dynasties; none with length zero in 413 saves), and
    only the user-interface divide 0x323685 reads that nibble.
I7  IR: at most 20 a club and 102 extension entries league-wide, at most 8 returns a club, nobody on IR is also on an
    active list, and the IR record is sound (save: when the extension magic is present its checksum matches; memory:
    the store's magic and version).
I8  trade board: every player a record names belongs to that side's club and both clubs are league clubs. Named by
    a club that does not hold him while another club, or nobody, does -- failure. Still with his club but on its IR
    or practice squad, or now a free agent -- warning: the native board keeps such stale records (seen in clean
    standard saves) until its pruner 0x2BB9A0 drops them, and the ownership guard refuses to execute them. With a
    previous view, a quarterback-for-pick record (kind 2, one A player who is a quarterback, no B player, one B pick)
    present unchanged in both views has outlived a week (failure).
I9  the transaction ring cursor is below 600 and every row's kind is in the allowed set: default 1, 2, 4, 7, 8, 9, 10,
    11, 12 (the design's list 1, 4, 7, 8, 9, 10, 12 plus 11, written by the native CPU listing at 0x2BBE72 in every
    recorded season, and 2, in the retail year-7 offseason save); ``--allowed-kinds`` sets the control arm's own set.

I11 in stages 8 and 9, every club has at least one healthy quarterback on its active list (healthy = slice 1's
    fully_healthy: no injured bit and no weeks in +0x20, no status in +0x24 & 0x70000000) -- failure. Added after P0
    root 2508 ended 2027 week 18 with Dallas's three quarterbacks all on IR (coordinator: release blocker).

Memory images: ``B81MEMv1`` (this tool's ``dump_memory``: magic, region count, then start, size and bytes of each
region; gzip optional) or a gzip pickle of ``(bounds, regions)`` as Codex's signed_awards.check writes it (read with
an unpickler that refuses every global, so it cannot run code).
"""
from __future__ import annotations

import argparse
import bisect
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import gzip
import io
import json
from pathlib import Path
import pickle
import struct
import sys
from typing import Callable, Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CLUBS = 32
SLOTS = 65
TEAM_SIZE = 500
PLAYER_SIZE = 0x54
ACTIVE_COUNT = 0x11C
PAYROLL = 0x124
ABBREVIATION = 0x108
PS_VERSION, PS_COUNT, PS_MARKER, PS_MARK = 0x19B, 0x1F2, 0x1F3, 0xA5
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
QB, K, P = 0, 1, 2
INJURED = 0x80000000
WEEKS_MASK = 0xFF << 22
STATUS_MASK = 0x70000000
LEDGER_CAPACITY = 600
BOARD_SLOTS = 15
DEFAULT_KINDS = (1, 2, 4, 7, 8, 9, 10, 11, 12)
IR_CAP, IR_EXT_CAP, IR_RETURNS = 20, 102, 8

# RAM addresses (retail virtual addresses; season block names from nfl2k5_franchise_save)
LEAGUE_ROOT = 0xB72918
ARENA_SIZE_WORD = 0xB72808
MODE, STAGE, WEEK, YEAR = 0xE576A0, 0xE576A4, 0xE576B4, 0xE576B8
USER_CONTROL = 0xE5775C
CPU_DEPTH, AUTO_SIGN_CUT = 0xE60140, 0xE6013C
SALARY_CAP = 0xE3C278
BOARD, BOARD_SIZE = 0xE3C27C, 0x3C
LEDGER_CURSOR, LEDGER = 0xE3F06C, 0xE3F070
LEGACY_IR = 0xE421E0
SETTINGS_BASE = 0xE5FF80                     # the save's settings prefix is an image of RAM 0xE5FF80..
IR_CONFIG_MAGIC, IR_CONFIG_VERSION = 0x434D5249, 1
IR_STORE_MAGIC, IR_STORE_VERSION, IR_STORE_SIZE, IR_CLUB_SIZE = 0x52493236, 1, 5312, 164
RESERVE_BLOCK_TAIL, RESERVE_MAGIC = 0x400, b"2K5RSV2\0"

FAIL, WARN = "failure", "warning"


# ------------------------------------------------------------------------------------------------- the league view
@dataclass
class Holder:
    kind: str            # active, practice, ir, free
    club: int | None


@dataclass
class ClubView:
    index: int
    name: str
    count: int                                       # the club's own count byte
    active: list[int] = field(default_factory=list)  # primary indices, slot order
    practice: list[int] = field(default_factory=list)
    payroll: int = 0
    human: bool = False
    bad: list[dict] = field(default_factory=list)    # slots whose pointer names no primary record


@dataclass
class IrView:
    kind: str                         # "store", "legacy-ram", "extension", "legacy-save"
    sound: bool
    detail: str
    clubs: list[list[tuple[int, bool]]]   # per club [(player index, season-ending)]
    returns: list[int]
    extension_entries: int = 0


@dataclass
class Offer:
    slot: int
    kind: int
    club_a: int | None
    players_a: list[int | None]
    picks_a: list[int]
    club_b: int | None
    players_b: list[int | None]
    picks_b: list[int]
    raw: bytes = b""

    def key(self):
        return (self.slot, self.kind, self.club_a, tuple(self.players_a), tuple(self.picks_a), self.club_b,
                tuple(self.players_b), tuple(self.picks_b))


@dataclass
class LeagueView:
    source: str
    label: str
    mode: int
    stage: int
    week: int
    year_index: int
    player_count: int
    record: Callable[[int], bytes]
    name: Callable[[int], str]
    clubs: list[ClubView]
    cpu_manages_depth: bool
    auto_sign_cut: bool
    salary_cap: int
    free_agents: list[int]
    ir: IrView
    board: list[Offer]
    ledger_cursor: int
    ledger_kinds: list[tuple[int, int]]          # (ring slot, kind) for every row with a nonzero kind
    structural: list[dict] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def managed(self, club: int) -> bool:
        return not self.clubs[club].human or self.cpu_manages_depth


def _u16(raw, at):
    return struct.unpack_from("<H", raw, at)[0]


def _u32(raw, at):
    return struct.unpack_from("<I", raw, at)[0]


# ------------------------------------------------------------------------------------------------- saves
def view_from_save(payload: bytes, *, label: str = "save") -> LeagueView:
    """League view of a franchise SAVEGAME.DAT (relative pointers; IR and board in their serialized forms)."""
    from mod_editor.core import nfl2k5_franchise_save as fs
    from mod_editor.core import nfl2k5_injured_reserve_save as irsave
    s = fs.FranchiseSave(payload)
    buf = s.buffer
    header = s.header
    count, table = s.player_table
    structural = []

    def rel(at):
        value = struct.unpack_from("<i", buf, at)[0]
        return None if value == 0 else at + value - 1

    def index_of(target):
        if target is None:
            return None
        slot, rem = divmod(target - table, PLAYER_SIZE)
        return slot if not rem and 0 <= slot < count else None

    def record(i):
        return bytes(buf[table + PLAYER_SIZE * i:table + PLAYER_SIZE * (i + 1)])

    def name(i):
        try:
            return s.player_name(i) if 0 <= i < count else ""
        except Exception:                                   # a damaged name pointer must not stop a validation
            return ""

    overflow = None
    try:
        from mod_editor.core import nfl2k5_roster_arena as arena
        growth = s.arena_end - fs.ARENA_END
        if growth:
            overflow = arena.read(bytes(buf), s.arena_root, s.arena_end, arena.SAVE_VERSION)
    except Exception as exc:                                # reported, never fatal
        structural.append({"what": "reserve overflow block unreadable", "detail": str(exc)})
    humans = set(s.user_teams())
    clubs = []
    for c in range(CLUBS):
        base = s.team_offset(c)
        raw = bytes(buf[base:base + TEAM_SIZE])
        club = ClubView(c, s.team_abbreviation(c), raw[ACTIVE_COUNT], payroll=_u32(raw, PAYROLL), human=c in humans)
        n = min(club.count, SLOTS)
        for slot in range(n):
            target = rel(base + 4 * slot)
            i = index_of(target)
            if i is None:
                club.bad.append({"slot": slot, "list": "active", "pointer": None if target is None else hex(target)})
            else:
                club.active.append(i)
        if raw[PS_MARKER] == PS_MARK:
            total = n + raw[PS_COUNT]
            for slot in range(n, min(total, SLOTS)):
                target = rel(base + 4 * slot)
                i = index_of(target)
                if i is None:
                    club.bad.append({"slot": slot, "list": "practice", "pointer": None if target is None else hex(target)})
                else:
                    club.practice.append(i)
            if total > SLOTS:
                extra = [v for v in (overflow.rows[c] if overflow else ()) if v != 0xFFFF]
                if len(extra) != total - SLOTS:
                    structural.append({"what": "practice squad overflow count", "club": c,
                                       "values": {"declared": total - SLOTS, "found": len(extra)}})
                club.practice.extend(v for v in extra if v < count)
        elif (raw[PS_VERSION], raw[PS_COUNT], raw[PS_MARKER]) != (0, 0, 0):
            structural.append({"what": "unknown practice squad metadata", "club": c,
                               "values": {"version": raw[PS_VERSION], "count": raw[PS_COUNT], "marker": raw[PS_MARKER]}})
        clubs.append(club)

    free = []
    fa_count = _u32(buf, s.arena_root + 0x38)
    fa_table = rel(s.arena_root + 0x3C)
    for k in range(fa_count if fa_table is not None else 0):
        i = index_of(rel(fa_table + 4 * k))
        if i is None:
            structural.append({"what": "free agent pointer names no primary record", "values": {"slot": k}})
        else:
            free.append(i)

    # IR: the legacy cells and the b780 extension, decoded without dropping duplicates (irsave.decode drops them)
    fo = s.front_office_block
    block = bytes(buf[fo + fs.F_INJURED_RESERVE:fo + fs.F_INJURED_RESERVE + irsave.CELLS * 4])
    low = [_u16(block, 4 * k) for k in range(irsave.CELLS)]
    high = [_u16(block, 4 * k + 2) for k in range(irsave.CELLS)]
    magic = high[irsave.W_MAGIC] == irsave.MAGIC
    sums = magic and high[irsave.W_SUM] == irsave.checksum(low, high)
    ir_clubs, returns, ext_entries = [[] for _ in range(CLUBS)], [0] * CLUBS, 0
    w = irsave.W_EXT
    for c in range(CLUBS):
        for slot in range(irsave.LEGACY_SLOTS):
            cell = c * irsave.LEGACY_SLOTS + slot
            if low[cell] == irsave.EMPTY:
                continue
            state = irsave._nibble(high, irsave.W_STATES, cell) if sums else 0
            ir_clubs[c].append((low[cell], bool(state & 8)))
        if sums:
            returns[c] = irsave._nibble(high, irsave.W_RETURNS, c)
            for _ in range(irsave._nibble(high, irsave.W_COUNTS, c)):
                if w >= irsave.CELLS:
                    break
                ir_clubs[c].append((high[w] & 0xFFF, bool((high[w] >> 12) & 8)))
                w += 1
                ext_entries += 1
    ir = IrView("extension" if sums else "legacy-save", not magic or sums,
                "extension checksum matches" if sums else ("extension magic with a bad checksum" if magic else
                                                           "no extension (a retail or older writer)"),
                ir_clubs, returns, ext_entries)

    board = []
    for slot in range(BOARD_SLOTS):
        at = fo + fs.F_TRADES + slot * fs.F_TRADE_SIZE
        raw = bytes(buf[at:at + fs.F_TRADE_SIZE])
        # FUN_002d06d0 (the loader): +0 kind, +1 club A, +2 A's three players, +8 A's three picks, +0x0E club B,
        # +0x10 B's three players, +0x16 B's three picks, +0x1C six bytes; 0xFF = no club, 0xFFFF = no player.
        club = lambda b: None if b == 0xFF else b
        player = lambda v: None if v == 0xFFFF else v
        board.append(Offer(slot, raw[0], club(raw[1]), [player(_u16(raw, 2 + 2 * j)) for j in range(3)],
                           [_u16(raw, 8 + 2 * j) for j in range(3)], club(raw[0x0E]),
                           [player(_u16(raw, 0x10 + 2 * j)) for j in range(3)],
                           [_u16(raw, 0x16 + 2 * j) for j in range(3)], raw))

    cursor = s.u32(fo + fs.F_LEDGER_CURSOR)
    kinds = []
    for slot in range(LEDGER_CAPACITY):
        kind = s.u32(fo + fs.F_LEDGER + slot * fs.F_LEDGER_SIZE) & 31
        if kind:
            kinds.append((slot, kind))
    prefix = lambda va: _u32(buf, va - SETTINGS_BASE)
    return LeagueView("save", label, header.mode, header.stage, header.week, header.year_field, count, record, name,
                      clubs, bool(prefix(CPU_DEPTH)), bool(prefix(AUTO_SIGN_CUT)), s.salary_cap, free, ir, board,
                      cursor, kinds, structural, {"save_bytes": len(payload)})


# ------------------------------------------------------------------------------------------------- memory
class Regions:
    """Sparse little-endian memory over (start, bytes) regions."""

    def __init__(self, regions: Iterable[tuple[int, bytes]]):
        self.regions = sorted((int(a), bytes(b)) for a, b in regions)
        self.starts = [a for a, _ in self.regions]

    def read(self, address: int, size: int) -> bytes:
        k = bisect.bisect_right(self.starts, address) - 1
        if k >= 0:
            start, data = self.regions[k]
            if address + size <= start + len(data):
                return data[address - start:address - start + size]
        raise ValueError(f"unmapped read {address:#x}+{size}")

    def find(self, needle: bytes, low: int = 0, high: int = 1 << 32) -> Iterable[int]:
        for start, data in self.regions:
            at = data.find(needle)
            while at >= 0:
                if low <= start + at < high:
                    yield start + at
                at = data.find(needle, at + 1)


class _NoGlobals(pickle.Unpickler):
    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"memory image refers to {module}.{name}; only plain data is accepted")


MEMORY_MAGIC = b"B81MEMv1"


def dump_memory(path: Path, regions: Iterable[tuple[int, bytes]]) -> None:
    """Write regions as a gzip ``B81MEMv1`` image (the harness keeps one at the first failure)."""
    regions = [(int(a), bytes(b)) for a, b in regions]
    out = io.BytesIO()
    out.write(MEMORY_MAGIC + struct.pack("<I", len(regions)))
    for start, data in regions:
        out.write(struct.pack("<II", start, len(data)))
        out.write(data)
    tmp = Path(str(path) + ".pending")
    with gzip.open(tmp, "wb", compresslevel=1) as fp:
        fp.write(out.getvalue())
    tmp.replace(path)


def load_memory(path: Path) -> Regions:
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    if raw.startswith(MEMORY_MAGIC):
        n, at, regions = _u32(raw, 8), 12, []
        for _ in range(n):
            start, size = struct.unpack_from("<II", raw, at)
            regions.append((start, raw[at + 8:at + 8 + size]))
            at += 8 + size
        return Regions(regions)
    bounds, blobs = _NoGlobals(io.BytesIO(raw)).load()          # Codex's (bounds, regions) checkpoint
    return Regions((lo, blob) for (lo, _hi), blob in zip(bounds, blobs))


def find_ir_store(read: Callable[[int, int], bytes], search: Callable[[bytes], Iterable[int]] | None) -> int | None:
    """The IR owner's store: its config ('IRMC', version 1, store VA) inside the executable's image, then the store's
    own magic. None when the owner is not installed (the 5-slot table is then the IR)."""
    if search is None:
        return None
    for at in search(struct.pack("<II", IR_CONFIG_MAGIC, IR_CONFIG_VERSION)):
        store = _u32(read(at + 8, 4), 0)
        try:
            if _u32(read(store, 4), 0) == IR_STORE_MAGIC:
                return store
        except ValueError:
            continue
    return None


def view_from_memory(read: Callable[[int, int], bytes], *, root: int | None = None, ir_store: int | None = None,
                     search: Callable[[bytes], Iterable[int]] | None = None, label: str = "memory") -> LeagueView:
    """League view of live game memory (absolute pointers). ``read(address, size)`` reads emulated RAM; ``ir_store``
    is the IR owner's store VA (``nfl2k5_injured_reserve.store_va(xbe)``), found through ``search`` when omitted."""
    u32 = lambda a: _u32(read(a, 4), 0)
    root = u32(LEAGUE_ROOT) if root is None else root
    count, table = u32(root), u32(root + 4)
    team_base = u32(root + 0x1C)
    structural = []

    def index_of(pointer):
        slot, rem = divmod(pointer - table, PLAYER_SIZE)
        return slot if pointer and not rem and 0 <= slot < count else None

    def record(i):
        return read(table + PLAYER_SIZE * i, PLAYER_SIZE)

    def text(pointer):
        if not pointer:
            return ""
        out = bytearray()
        try:
            while len(out) < 160:
                pair = read(pointer + len(out), 2)
                if pair == b"\0\0":
                    break
                out += pair
        except ValueError:
            pass
        return out.decode("utf-16-le", errors="replace")

    def name(i):
        if not 0 <= i < count:
            return ""
        base = table + PLAYER_SIZE * i
        return f"{text(u32(base + 0x10))} {text(u32(base + 0x14))}".strip()

    arena_size = u32(ARENA_SIZE_WORD)
    block = root + arena_size - RESERVE_BLOCK_TAIL
    try:
        reserve_rows = read(block + 32, 320) if read(block, 8) == RESERVE_MAGIC else None
    except ValueError:
        reserve_rows = None
    clubs = []
    for c in range(CLUBS):
        base = team_base + TEAM_SIZE * c
        raw = read(base, TEAM_SIZE)
        club = ClubView(c, text(_u32(raw, ABBREVIATION)), raw[ACTIVE_COUNT], payroll=_u32(raw, PAYROLL),
                        human=bool(u32(USER_CONTROL + 4 * c)))
        n = min(club.count, SLOTS)
        for slot in range(n):
            i = index_of(_u32(raw, 4 * slot))
            if i is None:
                club.bad.append({"slot": slot, "list": "active", "pointer": hex(_u32(raw, 4 * slot))})
            else:
                club.active.append(i)
        if raw[PS_MARKER] == PS_MARK:
            total = n + raw[PS_COUNT]
            for slot in range(n, total):
                if slot < SLOTS:
                    i = index_of(_u32(raw, 4 * slot))
                    if i is None:
                        club.bad.append({"slot": slot, "list": "practice", "pointer": hex(_u32(raw, 4 * slot))})
                        continue
                elif reserve_rows is not None:
                    i = _u16(reserve_rows, 10 * c + 2 * (slot - SLOTS))
                    if i >= count:
                        club.bad.append({"slot": slot, "list": "practice", "pointer": f"overflow index {i}"})
                        continue
                else:
                    structural.append({"what": "practice squad overflow without a reserve block", "club": c})
                    break
                club.practice.append(i)
        clubs.append(club)

    free = []
    for k in range(u32(root + 0x38)):
        i = index_of(u32(u32(root + 0x3C) + 4 * k))
        if i is None:
            structural.append({"what": "free agent pointer names no primary record", "values": {"slot": k}})
        else:
            free.append(i)

    store = ir_store if ir_store is not None else find_ir_store(read, search)
    ir_clubs, returns = [[] for _ in range(CLUBS)], [0] * CLUBS
    if store:
        magic, version = _u32(read(store, 8), 0), _u32(read(store, 8), 4)
        sound = (magic, version) == (IR_STORE_MAGIC, IR_STORE_VERSION)
        ext = 0
        for c in range(CLUBS):
            raw = read(store + 64 + IR_CLUB_SIZE * c, IR_CLUB_SIZE)
            returns[c] = raw[1]
            ext += max(0, raw[0] - 5)
            for e in range(min(raw[0], IR_CAP)):
                pointer, flags = _u32(raw, 4 + 8 * e), raw[4 + 8 * e + 6]
                i = index_of(pointer)
                if i is None:
                    structural.append({"what": "IR store entry names no primary record", "club": c,
                                       "values": {"entry": e, "pointer": hex(pointer)}})
                else:
                    ir_clubs[c].append((i, bool(flags & 1)))
            if raw[0] > IR_CAP:
                ir_clubs[c].extend([(-1, False)] * (raw[0] - IR_CAP))      # counted by I7, never resolved
        ir = IrView("store", sound, f"store at {store:#x}, magic {magic:#x} version {version}", ir_clubs, returns, ext)
    else:
        for c in range(CLUBS):
            for e in range(5):
                pointer = u32(LEGACY_IR + 20 * c + 4 * e)
                if pointer:
                    i = index_of(pointer)
                    if i is None:
                        structural.append({"what": "legacy IR cell names no primary record", "club": c,
                                           "values": {"cell": e, "pointer": hex(pointer)}})
                    else:
                        ir_clubs[c].append((i, True))
        ir = IrView("legacy-ram", True, "no IR owner store found: the retail 5-slot table", ir_clubs, returns)

    def club_index(pointer):
        if not pointer:
            return None
        c, rem = divmod(pointer - team_base, TEAM_SIZE)
        return c if not rem and 0 <= c < 64 else -1

    board = []
    for slot in range(BOARD_SLOTS):
        raw = read(BOARD + BOARD_SIZE * slot, BOARD_SIZE)
        players = lambda at: [None if not _u32(raw, at + 4 * j) else (index_of(_u32(raw, at + 4 * j))
                              if index_of(_u32(raw, at + 4 * j)) is not None else -1) for j in range(3)]
        board.append(Offer(slot, _u32(raw, 0), club_index(_u32(raw, 8)), players(0x0C),
                           [_u16(raw, 0x18 + 2 * j) for j in range(3)], club_index(_u32(raw, 0x20)), players(0x24),
                           [_u16(raw, 0x30 + 2 * j) for j in range(3)], raw))

    ring = read(LEDGER, LEDGER_CAPACITY * 12)
    kinds = [(k, _u32(ring, 12 * k) & 31) for k in range(LEDGER_CAPACITY) if _u32(ring, 12 * k) & 31]
    return LeagueView("memory", label, u32(MODE), u32(STAGE), u32(WEEK), u32(YEAR), count, record, name, clubs,
                      bool(u32(CPU_DEPTH)), bool(u32(AUTO_SIGN_CUT)), u32(SALARY_CAP), free, ir, board,
                      u32(LEDGER_CURSOR), kinds, structural,
                      {"root": hex(root), "ir_store": hex(store) if store else None, "arena_size": hex(arena_size)})


# ------------------------------------------------------------------------------------------------- the checks
@dataclass
class Report:
    view: LeagueView
    violations: list[dict]
    skipped: list[str]

    def counts(self):
        return Counter(v["severity"] for v in self.violations)

    def status(self, strict: bool = False) -> int:
        n = self.counts()
        return 2 if n[FAIL] or (strict and n[WARN]) else 1 if n[WARN] else 0

    def summary_line(self, strict: bool = False) -> str:
        v, n = self.view, self.counts()
        by = Counter(f"{x['invariant']}" for x in self.violations)
        word = {0: "CLEAN", 1: "WARNINGS", 2: "FAILURES"}[self.status(strict)]
        detail = ", ".join(f"{k} {by[k]}" for k in sorted(by)) or "none"
        return (f"franchise_invariants {word}: {v.label} ({v.source}, stage {v.stage}, week {v.week}, year index "
                f"{v.year_index}): {n[FAIL]} failures, {n[WARN]} warnings [{detail}]"
                + (" (strict)" if strict else ""))

    def document(self, strict: bool = False) -> dict:
        v = self.view
        return {"tool": "franchise_invariants", "label": v.label, "source": v.source,
                "state": {"mode": v.mode, "stage": v.stage, "week": v.week, "year_index": v.year_index},
                "info": v.info, "ir": {"kind": v.ir.kind, "sound": v.ir.sound, "detail": v.ir.detail},
                "status": self.status(strict), "strict": strict,
                "counts": {"failures": self.counts()[FAIL], "warnings": self.counts()[WARN]},
                "skipped": self.skipped, "structural_notes": v.structural, "violations": self.violations,
                "summary": self.summary_line(strict)}


def _row(field28: int) -> int:
    return (field28 >> 10) & 7


def player_salary(record: bytes, *, active: bool = True) -> int:
    from mod_editor.core.nfl2k5_practice_squad import player_salary as charge
    return charge(record, active=active)


def is_qb_for_pick(view: LeagueView, offer: Offer) -> bool:
    a = [p for p in offer.players_a if p is not None]
    return (offer.kind == 2 and len(a) == 1 and a[0] >= 0 and view.record(a[0])[0x35] == QB
            and not any(p is not None for p in offer.players_b) and sum(1 for w in offer.picks_b if w) == 1)


def check(view: LeagueView, *, previous: LeagueView | None = None, allowed_kinds: Iterable[int] = DEFAULT_KINDS,
          skip: Iterable[str] = ()) -> Report:
    skip = set(skip)
    out: list[dict] = []
    clubs = view.clubs

    def add(inv, severity, what, *, club=None, player=None, **values):
        row = {"invariant": inv, "severity": severity, "check": what}
        if club is not None:
            row.update(club=club, club_name=clubs[club].name if 0 <= club < CLUBS else None)
        if player is not None:
            row.update(player_index=player, player_name=view.name(player) if player >= 0 else "")
        if values:
            row["values"] = values
        out.append(row)

    stage = view.stage
    regular = stage in (8, 9)
    playing = stage in (7, 8, 9)

    # I1 ------------------------------------------------------------------------------------------------------------
    if "I1" not in skip:
        limit = 53 if regular else 65
        for c in clubs:
            if c.count > limit:
                add("I1", FAIL, f"active count above {limit}", club=c.index, count=c.count, stage=stage)
            elif c.count < 42:
                add("I1", FAIL, "active count under 42", club=c.index, count=c.count, stage=stage)
            elif c.count < 50:
                add("I1", WARN, "active count under 50", club=c.index, count=c.count, stage=stage)

    # holders (I2, I7) ----------------------------------------------------------------------------------------------
    holders: dict[int, list[Holder]] = defaultdict(list)
    for c in clubs:
        for i in c.active:
            holders[i].append(Holder("active", c.index))
        for i in c.practice:
            holders[i].append(Holder("practice", c.index))
    for c, rows in enumerate(view.ir.clubs):
        for i, _season in rows:
            if i >= 0:
                holders[i].append(Holder("ir", c))
    for i in view.free_agents:
        holders[i].append(Holder("free", None))

    if "I2" not in skip:
        for i, owned in sorted(holders.items()):
            rest = list(owned)
            for h in owned:                         # own club's IR + active: I7's case, not a second owner here
                if h.kind == "active" and any(o.kind == "ir" and o.club == h.club for o in rest):
                    rest.remove(next(o for o in rest if o.kind == "ir" and o.club == h.club))
            if len(rest) > 1:
                add("I2", FAIL, "player held more than once", player=i,
                    holders=[{"list": h.kind, "club": h.club} for h in owned])
        for c in clubs:
            for bad in c.bad:
                add("I2", FAIL, "roster pointer names no primary player", club=c.index, **bad)

    # I3 ------------------------------------------------------------------------------------------------------------
    if "I3" not in skip:
        for c in clubs:
            total = sum(player_salary(view.record(i)) for i in c.active)
            if view.mode == 2:
                total += sum(player_salary(view.record(i), active=False) for i, _ in view.ir.clubs[c.index] if i >= 0)
            if c.bad:
                continue                               # I2 reports the unreadable slots; no recount is possible
            if total != c.payroll:
                add("I3", FAIL, "stored payroll differs from the recount", club=c.index, stored=c.payroll,
                    recomputed=total, difference=c.payroll - total)
            if not c.human and c.payroll > view.salary_cap:
                add("I3", WARN, "club over the salary cap", club=c.index, payroll=c.payroll, cap=view.salary_cap)

    # I4 ------------------------------------------------------------------------------------------------------------
    human_rows = []
    if "I4" not in skip and playing:
        for c in clubs:
            by_position = defaultdict(list)
            for i in c.active:
                rec = view.record(i)
                by_position[rec[0x35]].append((i, _row(_u16(rec, 0x28)), _u32(rec, 0x20)))
            for pos, members in sorted(by_position.items()):
                rows = sorted(r for _, r, _ in members)
                expected = [min(k, 7) for k in range(len(members))]
                if rows != expected and not view.managed(c.index):
                    human_rows.append({"club": c.index, "position": POSITIONS[pos] if pos < len(POSITIONS) else pos,
                                       "rows": rows})
                elif rows != expected:
                    add("I4", FAIL, "depth rows are not 0..n-1", club=c.index,
                        position=POSITIONS[pos] if pos < len(POSITIONS) else pos, rows=rows, expected=expected,
                        players=[{"index": i, "row": r} for i, r, _ in sorted(members, key=lambda m: m[1])])
                if "I4.injured_row0" in skip or not view.managed(c.index):
                    continue
                healthy = [i for i, _, w in members if not w & INJURED]
                for i, r, w in members:
                    if r == 0 and w & INJURED and healthy:
                        add("I4", FAIL, "injured player at row 0 while a healthy one exists (managed club)",
                            club=c.index, player=i, position=POSITIONS[pos] if pos < len(POSITIONS) else pos,
                            healthy=healthy)

    # I5 ------------------------------------------------------------------------------------------------------------
    if "I5" not in skip:
        for c in clubs:
            have = Counter(view.record(i)[0x35] for i in c.active)
            for pos in (QB, K, P):
                if not have[pos]:
                    add("I5", FAIL, f"no {POSITIONS[pos]} on the active list", club=c.index, count=0)
            if have[QB] == 1:
                add("I5", WARN, "only one QB on the active list", club=c.index, count=1)

    # I6 ------------------------------------------------------------------------------------------------------------
    if "I6" not in skip and playing:
        for i, owned in sorted(holders.items()):
            kept = [h for h in owned if h.kind in ("active", "practice", "ir")]
            word = _u32(view.record(i), 0x24)
            if not kept or word & 15:
                continue
            if (word >> 24) & 15 == 0:
                add("I6", FAIL, "rostered player with a zero-length contract", club=kept[0].club, player=i,
                    holders=[{"list": h.kind, "club": h.club} for h in kept], contract_word=hex(word))
            else:
                add("I6", WARN, "rostered player with zero contract years left", club=kept[0].club, player=i,
                    holders=[{"list": h.kind, "club": h.club} for h in kept], contract_word=hex(word))

    # I7 ------------------------------------------------------------------------------------------------------------
    if "I7" not in skip:
        if not view.ir.sound:
            add("I7", FAIL, "IR record unsound", detail=view.ir.detail)
        if view.ir.extension_entries > IR_EXT_CAP:
            add("I7", FAIL, "more IR extension entries than the league-wide limit", count=view.ir.extension_entries)
        active_of = {i: c.index for c in clubs for i in c.active}
        for c, rows in enumerate(view.ir.clubs):
            if len(rows) > IR_CAP:
                add("I7", FAIL, "more than 20 on IR", club=c, count=len(rows))
            if view.ir.returns[c] > IR_RETURNS:
                add("I7", FAIL, "more than 8 IR returns", club=c, returns=view.ir.returns[c])
            for i, _season in rows:
                if i >= 0 and i in active_of:
                    add("I7", FAIL, "IR player also on an active list", club=c, player=i, active_club=active_of[i])

    # I8 ------------------------------------------------------------------------------------------------------------
    if "I8" not in skip:
        members = {c.index: set(c.active) for c in clubs}
        kept_by = defaultdict(set)                     # player -> clubs holding him on IR or a practice squad
        for c in clubs:
            for i in c.practice:
                kept_by[i].add(c.index)
        for c, rows in enumerate(view.ir.clubs):
            for i, _ in rows:
                kept_by[i].add(c)
        active_of = {i: c.index for c in clubs for i in c.active}
        free = set(view.free_agents)
        for o in view.board:
            if not o.kind:
                continue
            for side, club, players in (("A", o.club_a, o.players_a), ("B", o.club_b, o.players_b)):
                named = [p for p in players if p is not None]
                if club is None:
                    if named:
                        add("I8", FAIL, f"side {side} names players but no club", slot=o.slot, kind=o.kind, players=named)
                    continue
                if not 0 <= club < CLUBS:
                    add("I8", FAIL, f"side {side} club is not a league club", slot=o.slot, kind=o.kind, club_value=club)
                    continue
                for p in named:
                    if p >= 0 and p in members[club]:
                        continue
                    if p >= 0 and (club in kept_by[p] or (p in free and p not in active_of and not kept_by[p])):
                        where = "free agent" if p in free else "IR or practice squad of the same club"
                        add("I8", WARN, f"side {side} names a stale player ({where})", club=club, player=p,
                            slot=o.slot, kind=o.kind)
                    else:
                        add("I8", FAIL, f"side {side} names a player his club does not have", club=club,
                            player=p if p >= 0 else None, slot=o.slot, kind=o.kind,
                            now_active_with=active_of.get(p), now_kept_by=sorted(kept_by[p]) if p >= 0 else None)
        if previous is not None:
            before = {o.key() for o in previous.board if o.kind}
            for o in view.board:
                if o.kind and o.key() in before and is_qb_for_pick(view, o):
                    add("I8", FAIL, "quarterback-for-pick record outlived a week", club=o.club_b, slot=o.slot,
                        player=o.players_a[0])

    # I11 -----------------------------------------------------------------------------------------------------------
    if "I11" not in skip and regular:
        for c in clubs:
            qbs = [i for i in c.active if view.record(i)[0x35] == QB]
            healthy = [i for i in qbs if not _u32(view.record(i), 0x20) & (INJURED | WEEKS_MASK)
                       and not _u32(view.record(i), 0x24) & STATUS_MASK]
            if not healthy:
                add("I11", FAIL, "no healthy quarterback on the active list", club=c.index, quarterbacks=len(qbs),
                    on_ir=sum(1 for i, _ in view.ir.clubs[c.index] if view.record(i)[0x35] == QB),
                    hurt=[{"index": i, "injured": bool(_u32(view.record(i), 0x20) & INJURED),
                           "weeks": (_u32(view.record(i), 0x20) >> 22) & 0xFF,
                           "status": (_u32(view.record(i), 0x24) >> 28) & 7} for i in qbs])

    # I9 ------------------------------------------------------------------------------------------------------------
    if "I9" not in skip:
        if not 0 <= view.ledger_cursor < LEDGER_CAPACITY:
            add("I9", FAIL, "transaction ring cursor out of range", cursor=view.ledger_cursor)
        allowed = set(allowed_kinds)
        odd = Counter(k for _, k in view.ledger_kinds if k not in allowed)
        for kind, n in sorted(odd.items()):
            add("I9", FAIL, "transaction row kind not in the allowed set", kind=kind, rows=n,
                slots=[s for s, k in view.ledger_kinds if k == kind][:10], allowed=sorted(allowed))
    if human_rows:
        view.info["human_club_row_anomalies"] = human_rows
    return Report(view, out, sorted(skip))


# ------------------------------------------------------------------------------------------------- command line
def load_target(path: Path, *, label: str | None = None) -> tuple[LeagueView, dict]:
    """A signed folder (SAVEGAME.DAT and EXTRA) or a SAVEGAME.DAT file; returns the view and signature facts."""
    path = Path(path)
    save = path / "SAVEGAME.DAT" if path.is_dir() else path
    payload = save.read_bytes()
    extra = save.with_name("EXTRA")
    facts = {"save": str(save), "signature": "absent"}
    if extra.is_file():
        from mod_editor.core import nfl2k5_roster_records as rr
        facts["signature"] = "verified" if rr.verify_extra(payload, extra.read_bytes()) else "BAD"
    import hashlib
    facts["save_sha256"] = hashlib.sha256(payload).hexdigest()
    view = view_from_save(payload, label=label or str(path))
    view.info.update(facts)
    return view, facts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", type=Path, help="signed franchise folder or SAVEGAME.DAT")
    ap.add_argument("--memory", type=Path, help="memory image (B81MEMv1 or Codex's (bounds, regions) pickle)")
    ap.add_argument("--root", type=lambda s: int(s, 0), help="league root (default: the word at 0xB72918)")
    ap.add_argument("--ir-store", type=lambda s: int(s, 0), help="IR owner's store VA (default: found in memory)")
    ap.add_argument("--xbe", type=Path, help="executable: the IR store VA comes from its layout")
    ap.add_argument("--previous", type=Path, help="the previous week's save or memory image (I8 one-week rule)")
    ap.add_argument("--allowed-kinds", default=",".join(map(str, DEFAULT_KINDS)))
    ap.add_argument("--skip", action="append", default=[], help="I1..I9, I11 or I4.injured_row0 (repeatable)")
    ap.add_argument("--strict", action="store_true", help="warnings count as failures")
    ap.add_argument("--out", type=Path, help="write the JSON here and print only the summary line")
    a = ap.parse_args(argv)
    if bool(a.target) == bool(a.memory):
        ap.error("give a save target or --memory, not both")

    def load(path):
        if a.memory:
            memory = load_memory(path)
            store = a.ir_store
            if store is None and a.xbe:
                from mod_editor.core import nfl2k5_injured_reserve as ir
                store = ir.store_va(a.xbe.read_bytes()) or 0
            return view_from_memory(memory.read, root=a.root, ir_store=store,
                                    search=lambda n: memory.find(n, 0x10000, 0x2000000), label=str(path))
        return load_target(path)[0]

    view = load(a.memory or a.target)
    previous = load(a.previous) if a.previous else None
    report = check(view, previous=previous, allowed_kinds=[int(k) for k in a.allowed_kinds.split(",") if k],
                   skip=a.skip)
    document = report.document(a.strict)
    text = json.dumps(document, indent=1) + "\n"
    if a.out:
        a.out.write_text(text)
        print(report.summary_line(a.strict))
    else:
        sys.stdout.write(text)
        print(report.summary_line(a.strict), file=sys.stderr)
    return report.status(a.strict)


if __name__ == "__main__":
    raise SystemExit(main())
