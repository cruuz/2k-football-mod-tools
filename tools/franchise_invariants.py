#!/usr/bin/env python3
"""Check the franchise invariants I1 to I9 and I11 (beta 81 qb34 design, section 4.3), with the trade checks I8.* and
T1.* of stage 4b (DESIGN 4.2), on a save or on live memory.

    python3 tools/franchise_invariants.py SIGNED_FOLDER_OR_SAVEGAME.DAT [--strict] [--out report.json]
    python3 tools/franchise_invariants.py --memory IMAGE [--root 0x...] [--ir-store 0x... | --xbe default.xbe]
    ... [--previous PREVIOUS_SAVE_OR_IMAGE] [--deadline-week N] [--boundary | --no-boundary]
    python3 tools/franchise_invariants.py SIGNED_FOLDER --repair-rank-locks NEW_FOLDER [--confirm] [--out receipt.json]

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
    Pick word (u16, three a side at +0x18 / +0x30): round = w & 0x3F one-based 1..7, 0 = no pick (a cancelled pick keeps
    its slot and year bits); slot = bits 6-11 (in season the original club); year = w >> 12 (0 the next draft, 1 the one
    after). Owner: byte 0xE3C094 + 32 * (7 * year + round) + slot, rows 1..14 (save: F_ORDERS). Named checks:
    I8.pick_word   a pick (round != 0) on any record outside round 1-7, slot < 32, year <= 1 (it would index outside the
                   table, 0x2BB1C0 writes unbounded) -- failure.
    I8.pick_owner  a valid pick its side's club does not own -- failure on a quarterback-for-pick record, warning on any
                   other (the native evaluator values picks and checks no owner).
    The quarterback-for-pick checks below judge slots 1-14 only: slot 0 is the user's work slot, which the 4b page never
    writes and whose records always name the user's own club.
    I8.human       a quarterback-for-pick record naming a human club (either side) -- failure.
    I8.window      a quarterback-for-pick record while stage != 8 or the window 0x247D10 is closed (Trade Deadline option
                   0xE60124 on and week >= stage_table[8].byte5, 0x5151C5: 9 with the deadline owner, 6 retail; a memory
                   view reads the byte from the loaded executable, a save takes ``deadline_week``, default 9) -- failure.
                   An unknown option skips it with a note in info.
    I8.boundary    any quarterback-for-pick record on the board of a week boundary view -- failure. The 4b page posts at
                   the pre-game call of a stage 8 advance, the native pending scan of that advance executes or refuses
                   it, and the room pass at its end cancels a leftover, so after 0x247D40 returns none is left. Judged
                   when ``check(boundary=True)``; the default is True for a memory view (the harness calls check after
                   every weekly advance) and False for a save. No other source makes one: the native CPU never lists a
                   quarterback under the economy's cap of 3 (DESIGN 1.5), and no record in the 412 signed saves of the
                   validator corpus carries any pick, so control arms hold none; a save written by this design holds none
                   either, and the harness may pass boundary=True for its closing saves. A memory state INSIDE an advance
                   (the kick-off hook 0x247DCF runs before the stage switch's trade tick, where the record legitimately
                   sits) must pass boundary=False, as kick-off checks do by skipping I8.
T2  (b81 CPU trades, nfl2k5_cpu_trades) on every trade group of exactly one player at a position other than QB and one
    pick (the native CPU trades are player swaps): T2.human and T2.position (no K or P) always; the rest only when the
    two views are one weekly advance apart (else the harness judges the trade at the call): T2.deadline (stage 8 at or past
    the deadline byte, whatever the option), T2.window (only stages 7 and 8), T2.counts (seller 50..65, buyer at most 53
    in season, 65 in the preseason), T2.player (no rookie, no first contract year, not star-tagged, fully healthy before),
    T2.seller_depth (the seller keeps its starters healthy and its cut minimum at the position), T2.load (neither club in
    three trade groups of the previous ledger), T2.repeat (the man was not signed or traded in the previous ledger),
    T2.pick (exactly that pick passes buyer to seller). All failures.
T1  trades since ``previous`` (the view one weekly advance earlier): the ring rows from previous.ledger_cursor to
    view.ledger_cursor (modulo 600: a wrap of 600 or more rows cannot be told apart, which info says; rows outside the
    span that changed are counted in info), grouped by bit 31 (the executor marks a trade's last row). Kind 7 rows: one
    per OUTGOING player (club = his old club), one per outgoing pick (no player, arg1 = round, arg2 = year, club = the
    club giving it). A quarterback-for-pick group is exactly a quarterback's row (the seller) and a pick row (the buyer).
    T1.window      a trade group between CPU clubs when the advance from ``previous`` runs no CPU trade tick: the tick
                   0x2BC960 runs in stages 1, 2 and 7 with no window test (0x247D40's switch, table 0x248088: 0x247FBD,
                   0x247DEA) and in stage 8 when the window is open (0x247E0E); never in stages 3-6 or 9 -- failure. A
                   group naming a human club is the user's own trade (his trade screen has its own rule: with the option
                   on it refuses stage 9 and stage 8 past the deadline, and allows the preseason and offseason) and is
                   listed in info, not judged here.
    T1.human       a quarterback-for-pick group with a human club on either side -- failure.
    T1.deadline    a quarterback-for-pick group in an advance from a week at or after the native deadline week
                   (stage_table[8].byte5, 0x5151C5), whatever the Trade Deadline option says (DESIGN_CHANGES C22 (c):
                   4b follows the real deadline even with the option off) -- failure; judged one weekly advance apart.
    T1.counts      after a quarterback-for-pick group the seller's or the buyer's active count outside 50..53 -- failure
                   (the native evaluator lets side B finish at 44, 0x2BB161).
    T1.seller_depth after a quarterback-for-pick group the seller has fewer than 2 quarterbacks on its active list, or
                   fewer than 2 healthy ones (I11's healthy) -- failure. A quarterback counts as healthy when he is so in
                   this view or in ``previous``: the trade runs before the week's games, so a man hurt in this week's
                   game was healthy when he was traded around (the CPU path checks no seller depth, RISKS (a) 5).
    T1.pick        for a quarterback-for-pick group, not exactly one pick-table entry changed owner between the views
                   with the pick row's round and year, from the buyer to the seller -- failure.
    T1.unexplained_pick with both views in stage 8 of the same year (no draft roll between), a pick-table entry that
                   changed owner with no pick row of a trade group in the new rows giving it (same round, year, and
                   outgoing club = old owner; each row explains one entry) -- failure.
    The T1 checks assume one advance between the views (the harness's case). T1.window is judged only when the two views
    are exactly one weekly advance apart (same year and stage, week + 1): across a season's opening (the offseason and
    camp advances, whose stages 1, 2 and 7 run the CPU trade tick) or a stage advance it is not judged, with a note
    (shadow panel trades-shadow, 2026-11-20: both arms failed T1.window at the 2027 opening on offseason CPU trades). A summary (rows, groups, quarterback-for-pick trades, pick changes, notes) goes into
    info["trades_since_previous"].
I9  the transaction ring cursor is below 600 and every row's kind is in the allowed set: default 1, 2, 4, 7, 8, 9, 10,
    11, 12 (the design's list 1, 4, 7, 8, 9, 10, 12 plus 11, written by the native CPU listing at 0x2BBE72 in every
    recorded season, and 2, in the retail year-7 offseason save); ``--allowed-kinds`` sets the control arm's own set.

I11 every club the CPU signs for (not human, or auto sign/cut 0xE6013C on; a manual human club is exempt) has at least
    one healthy quarterback on its active list (healthy = slice 1's fully_healthy: no injured bit and no weeks in
    +0x20, no status in +0x24 & 0x70000000). Stages 8 and 9, a FAILURE for every such club that has a NEXT GAME,
    wherever it is judged: at KICK-OFF (``check(view, kickoff=True)``, the harness's 0x247DCF, after the IR pass and the
    floor; DESIGN addendum F5), at the END OF EVERY ADVANCE from the state before week 1 (after the camp cut to 53)
    through the last playoff game (review of the floor F2: a game the user plays happens between advances), and on a
    SAVE (review F9). A club with no next game (eliminated in the playoffs, or at the season's end) gets a warning.
    "Next game" is read from the schedule grid (RAM 0xE57C40 / the save's S_GRID, 22 x 17 cells of 8 bytes; side flags
    at 0xE57954 / S_GRID_FLAGS): an unplayed cell that names the club on a known side (a regular-season row, or a
    playoff side whose flag byte is set; the bracket's unknown cells carry team 0 and flag 0); a club on its bye has
    one. At the end of the regular season (stage 8, every regular-season cell played) the bracket is not built until
    the next stage advance (seen in P1 2508's kept images: rows 18-21 empty at week 18, the divisional games known
    right after the wildcard round), so every club the CPU signs for may still play and counts as having a next game.
    Added after P0 root 2508 ended 2027 week 18 with Dallas's three quarterbacks all on IR (coordinator: release
    blocker).
W7  the same test in stage 7 (the preseason, kick-off or boundary): a WARNING of its own, "preseason club without a
    healthy quarterback" (coordinator 11/20: the preseason gap is accepted and reported, never folded into I11).
W12 (DESIGN addendum 2, R2 and TD10; scope by the coordinator's ruling of 11/20) from YEAR INDEX 1 on, on a club
    whose depth chart the CPU manages (not human, or "CPU manages my depth chart" 0xE60140 on): a healthy quarterback
    (no injury bit, no weeks, no status) who is rank-locked (bit 0 of +0x52) on a row below 0 while he leads the row 0
    quarterback by 6 or more overall points -- warning. Under Retail nothing re-seats such a pair. A year-one save
    (year index 0) is never warned: the shipped charts are real post-deadline choices (the released v0.9 opening
    holds ARI Brissett 89 and Carson Beck 70 behind Minshew 64 and PHI Joe Milton 76 behind Tanner McKee 67, all
    shipped locks, and they stand). A club whose chart the user manages is never warned, in any year. Overall is the
    game's 0x246D80 integer, computed here in Python (``native_overall``: nfl2k5_my_career_prospects.native_overall,
    the unboosted EDX=0 form); for healthy quarterbacks it equals 0x246D80(p, 1) run natively on three kept memory
    images (251 of 251: the 2502/2027 preseason sign_after image, P0 2508/2027 week 18, the 2505/2026 week 10
    kick-off).
    REPAIR (``--repair-rank-locks NEW_FOLDER [--confirm]``, ``repair_rank_locks``): offered, never silent. Without
    ``--confirm`` it lists each pair it would unpin (club, both players, ratings, rows) and writes nothing. With it, it
    clears bit 0 of +0x52 on exactly the W12 men (nothing else; the row 0 man keeps his lock, and the native release
    rule frees him at the next weekly sort because a better unlocked man now exists), writes a new signed copy
    through FranchiseSave.write (never over the source or an existing folder) and verifies it on reload: the EXTRA
    verifies, the only changed bytes are those +0x52 bytes and each differs by bit 0, no cleared man is still W12,
    and every other invariant's rows are unchanged. It never touches a lock on a club whose chart the user manages
    and never changes a year-one save; with no pair it writes nothing.
I3c (F5) a club with a "signed over the cap" signing (``over_cap_signings``: club, player, week boundaries since the
    signing, which the harness tracks from the owner's ring) is still over the cap at the second boundary after it,
    or over by more than that man's charge at the first -- failure.
PR1 (DESIGN_CHANGES C21, coordinator 11/20: E1/E2 never cut a star to sign a backup quarterback) an E1 or E2
    make-room release (``protected_releases``: the club as it stood at the page's release call, which the harness
    snapshots there) whose man is not all of (a) one of the club's ten lowest-rated players leaving out QB, K and P
    (fewer than ten of them rate strictly lower), (b) not first (row 0) on his position's chart, (c) a man whose
    position keeps at least its minimum of healthy players without him (the economy's cut_min, OLB and ILB one pool:
    QB 2, K 1, P 1, WR 5, CB 5, FS 2, SS 2, HB 3, FB 0, TE 3, LB 5, C 2, G 3, T 3, DT 3, DE 4); and never a QB, K or P
    -- failure. The rating is the game's unadjusted 0x246D80(p, 0) (flag 1 discounts an injured man; injured or
    healthy makes no difference to the protection), which the harness computes natively; this tool only compares.

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
PICKS, PICK_ROWS, PICK_SLOTS = 0xE3C0B4, 14, 32   # pick owners, rows 1..14 (0xE3C094 + 32 * row + slot; row 0 is not owners)
TRADE_OPTION, DEADLINE_BYTE = 0xE60124, 0x5151C5   # Trade Deadline on/off; stage_table[8].byte5 (9 with the owner)
DEFAULT_DEADLINE_WEEK = 9
CPU_TRADE_STAGES = (1, 2, 7)                 # 0x247D40's stage switch calls 0x2BC960 here with no window test
LAST_IN_GROUP = 0x80000000
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
    pick_owners: bytes | None = None             # 14 x 32 owner bytes, pick table rows 1..14 (None: not read)
    ledger_rows: list[tuple[int, int | None, int | None]] | None = None   # all 600 ring rows: (word0, player, club)
    trade_option: int | None = None              # the Trade Deadline option word (None: unknown)
    deadline_week: int = DEFAULT_DEADLINE_WEEK   # stage_table[8].byte5: the window is open while week < this

    def managed(self, club: int) -> bool:
        return not self.clubs[club].human or self.cpu_manages_depth

    def pick_owner(self, round_: int, slot: int, year: int) -> int | None:
        """Owner byte of a pick (round one-based); None without a table or outside it."""
        at = PICK_SLOTS * (7 * year + round_ - 1) + slot
        if self.pick_owners is None or not (1 <= round_ <= 7 and 0 <= slot < PICK_SLOTS and 0 <= at < len(self.pick_owners)):
            return None
        return self.pick_owners[at]


def pick_fields(word: int) -> tuple[int, int, int]:
    """(round, slot, year) of a pick word: round = bits 0-5 one-based (0 = no pick), slot = bits 6-11, year = 12-15."""
    return word & 0x3F, (word >> 6) & 0x3F, word >> 12


def pick_word_valid(word: int) -> bool:
    round_, slot, year = pick_fields(word)
    return 1 <= round_ <= 7 and slot < PICK_SLOTS and year <= 1


def trade_window(view: LeagueView) -> bool | None:
    """The native window 0x247D10 as the stage 8 case uses it: open when the Trade Deadline option is off, else while
    week < stage_table[8].byte5. Closed outside stage 8; None when the option is unknown."""
    if view.stage != 8:
        return False
    if view.trade_option is None:
        return None
    return not view.trade_option or view.week < view.deadline_week


def cpu_can_trade(view: LeagueView) -> bool | None:
    """Whether the weekly advance that starts from ``view`` runs the CPU trade tick 0x2BC960: stages 1, 2 and 7 always
    (0x247FBD, 0x247DEA), stage 8 when the window is open (0x247E0E), no other stage."""
    return True if view.stage in CPU_TRADE_STAGES else trade_window(view)


def _u16(raw, at):
    return struct.unpack_from("<H", raw, at)[0]


def _u32(raw, at):
    return struct.unpack_from("<I", raw, at)[0]


# ------------------------------------------------------------------------------------------------- saves
GRID, GRID_FLAGS, STAGE_WEEKS = 0xE57C40, 0xE57954, 0xE576B0     # RAM; the save keeps both at S_GRID / S_GRID_FLAGS
GRID_ROWS, GRID_SLOTS = 22, 17


def next_game_state(grid: bytes, flags: bytes, stage: int, stage_weeks: int) -> dict:
    """Clubs with an unplayed game on a known side of the schedule grid, and whether the bracket is still unbuilt
    (stage 8 with every regular-season cell played: everyone may still play)."""
    clubs, regular_left = set(), False
    for i in range(GRID_ROWS * GRID_SLOTS):
        kind, home, away, month = grid[8 * i], grid[8 * i + 1], grid[8 * i + 2], grid[8 * i + 3]
        if kind != 0 or not (home or away or month):
            continue                                   # played (3), filler (7) or empty
        row, fl = i // GRID_SLOTS, _u16(flags, 2 * i)
        regular = stage == 8 and row < stage_weeks
        regular_left |= regular
        if regular or fl & 0xFF:
            clubs.add(home)
        if regular or fl >> 8:
            clubs.add(away)
    return {"clubs": sorted(c for c in clubs if c < 32), "bracket_pending": stage == 8 and not regular_left}


def view_from_save(payload: bytes, *, label: str = "save", deadline_week: int = DEFAULT_DEADLINE_WEEK) -> LeagueView:
    """League view of a franchise SAVEGAME.DAT (relative pointers; IR and board in their serialized forms). The trade
    deadline byte lives in the executable, not the save: ``deadline_week`` (9 with the deadline owner, 6 retail)."""
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
    kinds, rows = [], []
    for slot in range(LEDGER_CAPACITY):
        # the writer (0x2D0966..) keeps word0 and stores the player as an index (0x2D0500: 0xFFFF when the pointer
        # names no record, a pick row's 0 among them) and the club as a byte (0x2D04B0: 0xFF for none)
        packed, player, _zero, team = struct.unpack_from("<IHHB", buf, fo + fs.F_LEDGER + slot * fs.F_LEDGER_SIZE)
        rows.append((packed, None if player == 0xFFFF else (player if player < count else -1),
                     None if team == 0xFF else team))
        if packed & 31:
            kinds.append((slot, packed & 31))
    picks = bytes(s.u32(fo + fs.F_ORDERS + 4 * k) & 0xFF for k in range(PICK_ROWS * PICK_SLOTS))
    prefix = lambda va: _u32(buf, va - SETTINGS_BASE)
    sb = s.season_block
    schedule = next_game_state(bytes(buf[sb + fs.S_GRID:sb + fs.S_GRID + 8 * GRID_ROWS * GRID_SLOTS]),
                               bytes(buf[sb + fs.S_GRID_FLAGS:sb + fs.S_GRID_FLAGS + 2 * GRID_ROWS * GRID_SLOTS]),
                               header.stage, header.stage_weeks)
    return LeagueView("save", label, header.mode, header.stage, header.week, header.year_field, count, record, name,
                      clubs, bool(prefix(CPU_DEPTH)), bool(prefix(AUTO_SIGN_CUT)), s.salary_cap, free, ir, board,
                      cursor, kinds, structural, {"save_bytes": len(payload), "next_game": schedule,
                                                  "deadline_week_source": "argument (the executable's byte)"},
                      picks, rows, prefix(TRADE_OPTION), deadline_week)


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
                     search: Callable[[bytes], Iterable[int]] | None = None, label: str = "memory",
                     deadline_week: int | None = None) -> LeagueView:
    """League view of live game memory (absolute pointers). ``read(address, size)`` reads emulated RAM; ``ir_store``
    is the IR owner's store VA (``nfl2k5_injured_reserve.store_va(xbe)``), found through ``search`` when omitted.
    ``deadline_week`` defaults to the loaded executable's own byte 0x5151C5 (9 when that is unmapped)."""
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
    # word1 a player pointer (0 for a pick row), word2 a club pointer; a pointer naming no record reads as the save's
    # writer stores it (None), so both views give equal rows
    rows = [(_u32(ring, 12 * k), index_of(_u32(ring, 12 * k + 4)),
             (lambda c: None if c is None or c < 0 else c)(club_index(_u32(ring, 12 * k + 8))))
            for k in range(LEDGER_CAPACITY)]
    source = "argument"
    if deadline_week is None:
        try:
            deadline_week, source = struct.unpack("<b", read(DEADLINE_BYTE, 1))[0], "memory 0x5151C5"
        except ValueError:
            deadline_week, source = DEFAULT_DEADLINE_WEEK, "default (0x5151C5 unmapped)"
    return LeagueView("memory", label, u32(MODE), u32(STAGE), u32(WEEK), u32(YEAR), count, record, name, clubs,
                      bool(u32(CPU_DEPTH)), bool(u32(AUTO_SIGN_CUT)), u32(SALARY_CAP), free, ir, board,
                      u32(LEDGER_CURSOR), kinds, structural,
                      {"root": hex(root), "ir_store": hex(store) if store else None, "arena_size": hex(arena_size),
                       "next_game": next_game_state(read(GRID, 8 * GRID_ROWS * GRID_SLOTS),
                                                    read(GRID_FLAGS, 2 * GRID_ROWS * GRID_SLOTS),
                                                    u32(STAGE), u32(STAGE_WEEKS)),
                       "deadline_week_source": source},
                      bytes(read(PICKS, PICK_ROWS * PICK_SLOTS)), rows, u32(TRADE_OPTION), deadline_week)


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


RANK_LOCK = 0x52               # +0x52 bit 0: rank lock (nfl2k5_depth_locks: bits 0..4 rank/side/KR1/KR2/PR)
W12_LEAD = 6


def native_overall(record: bytes) -> int:
    """The game's integer overall of a 0x54 record (0x246D80, unboosted; equal to EDX=1 for healthy players)."""
    from mod_editor.core import nfl2k5_my_career_prospects as prospects
    from mod_editor.core import nfl2k5_roster_records as rr
    return prospects.native_overall(rr.PlayerRecord.decode(bytes(record[:PLAYER_SIZE])))


def _fully_healthy(record: bytes) -> bool:
    return not _u32(record, 0x20) & (INJURED | WEEKS_MASK) and not _u32(record, 0x24) & STATUS_MASK


def rank_lock_pairs(view: LeagueView) -> list[dict]:
    """W12's cases: from year index 1 on, on each club whose chart the CPU manages, every healthy quarterback
    rank-locked below row 0 who leads the (single) row 0 quarterback by W12_LEAD or more overall points."""
    out = []
    if view.year_index < 1:
        return out                                     # year one: the shipped charts stand (coordinator, 11/20)
    for c in view.clubs:
        if not view.managed(c.index):
            continue
        qbs = [(i, _row(_u16(view.record(i), 0x28))) for i in c.active if view.record(i)[0x35] == QB]
        top = [i for i, r in qbs if r == 0]
        if len(top) != 1:
            continue                                   # no single row 0 man: I4's business
        z = top[0]
        oz = native_overall(view.record(z))
        for i, r in qbs:
            rec = view.record(i)
            if r == 0 or not rec[RANK_LOCK] & 1 or not _fully_healthy(rec):
                continue
            o = native_overall(rec)
            if o - oz >= W12_LEAD:
                out.append({"club": c.index, "club_name": c.name, "player_index": i, "player_name": view.name(i),
                            "row": r, "overall": o, "row0_player": z, "row0_name": view.name(z),
                            "row0_overall": oz, "lead": o - oz, "row0_locked": bool(view.record(z)[RANK_LOCK] & 1)})
    return out


def player_salary(record: bytes, *, active: bool = True) -> int:
    from mod_editor.core.nfl2k5_practice_squad import player_salary as charge
    return charge(record, active=active)


PR1_LOWEST = 10
PR1_MINIMUMS = (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4)   # cut_min by position; OLB (10) pools with ILB (11)


def protected_release_problems(snapshot: dict) -> list[dict]:
    """PR1's verdict on one E1/E2 make-room release. ``snapshot``: {"club", "released" (player index), "players": the
    club's whole active list at the release call, each {"index", "position" (+0x35), "row" (+0x28 bits 10..12),
    "rating" (0x246D80(p, 0), unadjusted), "healthy" (no injury bit, weeks or status)}}. Returns one row per rule
    broken ({"check", ...values}); empty when the release keeps rule 1."""
    players = {p["index"]: p for p in snapshot["players"]}
    man = players.get(snapshot["released"])
    if man is None:
        return [{"check": "the released man is not on the club's active list at the release call"}]
    out = []
    pos = man["position"]
    if pos in (QB, 1, 2):
        out.append({"check": "a quarterback, kicker or punter released to make room",
                    "position": POSITIONS[pos] if 0 <= pos < len(POSITIONS) else pos})
    rated = [p for p in players.values() if 3 <= p["position"] <= 16]
    lower = sum(1 for p in rated if p["rating"] < man["rating"])
    if lower >= PR1_LOWEST:
        out.append({"check": "not one of the club's ten lowest-rated players (QB, K and P left out)",
                    "rating": man["rating"], "rated_lower": lower})
    if man["row"] == 0:
        out.append({"check": "first (row 0) on his position's depth chart", "position": pos})
    if 0 <= pos <= 16:
        pool = 11 if pos == 10 else pos
        healthy = sum(1 for p in players.values()
                      if p["healthy"] and (11 if p["position"] == 10 else p["position"]) == pool)
        left = healthy - (1 if man["healthy"] else 0)
        if left < PR1_MINIMUMS[pool]:
            out.append({"check": "his position falls below its minimum of healthy players without him",
                        "healthy_left": left, "minimum": PR1_MINIMUMS[pool]})
    return out


def is_qb_for_pick(view: LeagueView, offer: Offer) -> bool:
    """Kind 2, one A player who is a quarterback, no B player, one B pick. A pick is a word whose round (bits 0-5) is
    nonzero: a cancelled pick keeps its slot and year bits with round 0."""
    a = [p for p in offer.players_a if p is not None]
    return (offer.kind == 2 and len(a) == 1 and a[0] >= 0 and view.record(a[0])[0x35] == QB
            and not any(p is not None for p in offer.players_b) and sum(1 for w in offer.picks_b if w & 0x3F) == 1)


# b81 CPU trades (nfl2k5_cpu_trades, tools/cpu_trades/trades.c): starters per position and the economy's cut minimum
# (QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE; OLB and ILB one pool under ILB's minimum), the club load limit.
CPU_TRADE_STARTERS = (0, 0, 0, 3, 2, 1, 1, 1, 1, 1, 2, 2, 1, 2, 2, 2, 2)
CPU_TRADE_CUT_MIN = (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 0, 5, 2, 3, 3, 3, 4)
CPU_TRADE_LOAD_LIMIT = 3


def ledger_trade_load(view: LeagueView) -> list[int]:
    """Trade groups of the native ledger naming each club (an outgoing row of the group), oldest row first."""
    load = [0] * CLUBS
    if view.ledger_rows is None or not 0 <= view.ledger_cursor < LEDGER_CAPACITY:
        return load
    mask = set()
    for k in range(LEDGER_CAPACITY):
        word, _player, club = view.ledger_rows[(view.ledger_cursor + k) % LEDGER_CAPACITY]
        if word & 31 != 7:
            mask = set()
            continue
        if club is not None and 0 <= club < CLUBS:
            mask.add(club)
        if word & LAST_IN_GROUP:
            for c in mask:
                load[c] += 1
            mask = set()
    return load


def _check_player_for_pick(q, view, previous, clubs, human, one_advance, changes, add, skipped):
    """T2: the rules of the CPU trades owner on one player-for-pick group at a position other than QB."""
    seller, buyer, player, pos, rows = q["seller"], q["buyer"], q["player"], q["position"], q["rows"]
    if (human(seller) or human(buyer)) and not skipped("T2.human"):
        add("T2.human", FAIL, "player-for-pick trade with a human club", club=buyer if human(buyer) else seller,
            player=player, seller=seller, buyer=buyer, rows=rows)
    if pos in (K, P) and not skipped("T2.position"):
        add("T2.position", FAIL, "player-for-pick trade of a kicker or punter", club=seller, player=player, rows=rows)
    if not one_advance:
        # Across a stage advance (the preseason runs inside the advance to the regular season) the previous view is not
        # the state the trade was made from; the season harness judges those trades at the trade call itself.
        return
    if previous.stage == 8 and previous.deadline_week is not None \
            and previous.week >= previous.deadline_week and not skipped("T2.deadline"):
        add("T2.deadline", FAIL, "player-for-pick trade at or after the deadline week", club=buyer, player=player,
            week=previous.week, deadline_week=previous.deadline_week, option=previous.trade_option, rows=rows)
    if previous.stage not in (7, 8) and not skipped("T2.window"):
        add("T2.window", FAIL, "player-for-pick trade outside the preseason and the regular season", club=buyer,
            player=player, stage=previous.stage, rows=rows)
    if not skipped("T2.counts"):
        top = 53 if previous.stage == 8 else 65
        for c, low, high in ((seller, 50, 65), (buyer, 0, top)):
            if 0 <= c < CLUBS and not low <= clubs[c].count <= high:
                add("T2.counts", FAIL, "active count outside its limits after a player-for-pick trade", club=c,
                    count=clubs[c].count, role="seller" if c == seller else "buyer", rows=rows)
    if 0 <= player < previous.player_count and not skipped("T2.player"):
        before = previous.record(player)
        reasons = []
        if before[0x25] & 31 < 2:
            reasons.append("rookie")
        if not before[0x24] & 15 or before[0x24] & 15 == before[0x27] & 15:
            reasons.append("first contract year or no years left")
        if before[0x53] & 1:
            reasons.append("star-tagged")
        if not _fully_healthy(before):
            reasons.append("not fully healthy before the trade")
        if reasons:
            add("T2.player", FAIL, "a man the CPU trades never offer", club=seller, player=player, reasons=reasons,
                rows=rows)
    if 0 <= seller < CLUBS and pos < len(CPU_TRADE_STARTERS) and not skipped("T2.seller_depth"):
        lb = pos in (10, 11)
        at_pos = [i for i in clubs[seller].active if view.record(i)[0x35] == pos]
        count = len([i for i in clubs[seller].active if view.record(i)[0x35] in ((10, 11) if lb else (pos,))])
        healthy = [i for i in at_pos if _fully_healthy(view.record(i)) or _fully_healthy(previous.record(i))]
        if len(healthy) < CPU_TRADE_STARTERS[pos] or count < CPU_TRADE_CUT_MIN[11 if lb else pos]:
            add("T2.seller_depth", FAIL, "seller left below its starters or cut minimum at the position", club=seller,
                player=player, position=pos, healthy=len(healthy), count=count, rows=rows)
    if previous.ledger_rows is not None and not skipped("T2.load"):
        load = ledger_trade_load(previous)
        named = [c for c in (seller, buyer) if 0 <= c < CLUBS and load[c] >= CPU_TRADE_LOAD_LIMIT]
        if named:
            add("T2.load", FAIL, "player-for-pick trade by a club already in three trade groups of the ledger",
                club=named[0], player=player, load=[load[c] for c in named], rows=rows)
        signed = [k for k, (word, p, _c) in enumerate(previous.ledger_rows) if p == player and word & 31 in (1, 7)]
        if signed and not skipped("T2.repeat"):
            add("T2.repeat", FAIL, "player-for-pick trade of a man the ledger shows signed or traded", club=seller,
                player=player, ledger_slots=signed, rows=rows)
    if changes is not None and not skipped("T2.pick"):
        hits = [c for c in changes if (c["round"], c["year"], c["from"], c["to"]) == (q["round"], q["year"], buyer, seller)]
        if len(hits) != 1:
            add("T2.pick", FAIL, "the pick table does not show exactly this pick passing buyer to seller", club=buyer,
                player=player, round=q["round"], year=q["year"], seller=seller, matching_changes=hits, rows=rows)


def trades_since(previous: LeagueView, view: LeagueView) -> dict:
    """The transaction rows written between two views (previous.ledger_cursor up to view.ledger_cursor), grouped by the
    last-in-group bit 31, the kind 7 (trade) groups among them, and the pick-table entries that changed owner. Kind 7:
    one row per OUTGOING player (club = his old club) and one per outgoing pick (no player, arg1 = round, arg2 = year,
    club = the club giving it). A quarterback-for-pick group is exactly a quarterback's row (seller) and a pick row
    (buyer). More than 600 new rows cannot be told from fewer: the count is taken modulo 600."""
    out = {"new_rows": None, "groups": [], "qb_for_pick": [], "player_for_pick": [], "pick_changes": None, "notes": []}
    if previous.ledger_rows is None or view.ledger_rows is None:
        out["notes"].append("a view has no ledger rows: trades not judged")
        return out
    if not (0 <= previous.ledger_cursor < LEDGER_CAPACITY and 0 <= view.ledger_cursor < LEDGER_CAPACITY):
        out["notes"].append("a ledger cursor is out of range (I9): trades not judged")
        return out
    n = (view.ledger_cursor - previous.ledger_cursor) % LEDGER_CAPACITY
    out["new_rows"] = n
    span = {(previous.ledger_cursor + k) % LEDGER_CAPACITY for k in range(n)}
    outside = sum(1 for k in range(LEDGER_CAPACITY) if k not in span and previous.ledger_rows[k] != view.ledger_rows[k])
    out["notes"].append("rows counted modulo 600 (a wrap of 600 or more new rows cannot be told apart)")
    if outside:
        out["notes"].append(f"{outside} ring rows outside the new span changed (cleared, or the ring wrapped)")
    rows = []
    for k in range(n):
        slot = (previous.ledger_cursor + k) % LEDGER_CAPACITY
        word, player, club = view.ledger_rows[slot]
        rows.append({"slot": slot, "kind": word & 31, "arg1": (word >> 5) & 0xFFFF, "arg2": (word >> 21) & 0x3FF,
                     "last": bool(word & LAST_IN_GROUP), "player": player, "club": club})
    group = []
    for r in rows:
        group.append(r)
        if r["last"]:
            trade = [x for x in group if x["kind"] == 7]
            if trade:
                out["groups"].append(trade)
            group = []
    if any(x["kind"] == 7 for x in group):
        out["notes"].append(f"trade rows without a closing bit 31 at the cursor: {[x['slot'] for x in group]}")
    for trade in out["groups"]:
        players = [x for x in trade if x["player"] is not None]
        picks = [x for x in trade if x["player"] is None and x["arg1"]]
        if (len(trade) == 2 and len(players) == 1 and len(picks) == 1 and 0 <= players[0]["player"] < view.player_count
                and view.record(players[0]["player"])[0x35] == QB and players[0]["club"] is not None
                and picks[0]["club"] is not None and players[0]["club"] != picks[0]["club"]):
            out["qb_for_pick"].append({"seller": players[0]["club"], "buyer": picks[0]["club"],
                                       "player": players[0]["player"], "round": picks[0]["arg1"],
                                       "year": picks[0]["arg2"], "rows": [x["slot"] for x in trade]})
        elif (len(trade) == 2 and len(players) == 1 and len(picks) == 1 and 0 <= players[0]["player"] < view.player_count
                and players[0]["club"] is not None and picks[0]["club"] is not None
                and players[0]["club"] != picks[0]["club"]):
            # b81 CPU trades (nfl2k5_cpu_trades): one man at any other position for one pick (native trades are swaps)
            out["player_for_pick"].append({"seller": players[0]["club"], "buyer": picks[0]["club"],
                                           "player": players[0]["player"], "round": picks[0]["arg1"],
                                           "year": picks[0]["arg2"], "rows": [x["slot"] for x in trade],
                                           "position": view.record(players[0]["player"])[0x35]})
    if previous.pick_owners is not None and view.pick_owners is not None:
        out["pick_changes"] = [{"round": k // PICK_SLOTS % 7 + 1, "year": k // PICK_SLOTS // 7, "slot": k % PICK_SLOTS,
                                "from": a, "to": b}
                               for k, (a, b) in enumerate(zip(previous.pick_owners, view.pick_owners)) if a != b]
    else:
        out["notes"].append("a view has no pick table: T1.pick and T1.unexplained_pick not judged")
    return out


def check(view: LeagueView, *, previous: LeagueView | None = None, allowed_kinds: Iterable[int] = DEFAULT_KINDS,
          skip: Iterable[str] = (), kickoff: bool = False, over_cap_signings: Iterable[dict] = (),
          boundary: bool | None = None, protected_releases: Iterable[dict] = ()) -> Report:
    """The week-boundary checks; with ``kickoff`` only I11, as a failure (the harness's 0x247DCF check). I11 is also a
    failure on a save view (stages 8 and 9); stage 7 gives the warning W7 in every case. ``boundary``: the view is a
    week boundary (after 0x247D40 returns), where I8.boundary allows no quarterback-for-pick record; default True for
    a memory view, False for a save. ``previous`` (the view one advance earlier) adds the T1 checks. Skipping "I8" or
    "T1" skips every named check under it."""
    skip = set(skip)
    if kickoff:
        skip |= {"I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "W12", "T1"}
    if boundary is None:
        boundary = view.source == "memory"
    skipped = lambda name: name in skip or name.split(".")[0] in skip
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
    if "I3c" not in skip:
        for sig in over_cap_signings:
            c = clubs[sig["club"]]
            over = c.payroll - view.salary_cap
            charge = player_salary(view.record(sig["player"])) if 0 <= sig["player"] < view.player_count else 0
            if sig["boundaries"] >= 2 and over > 0:
                add("I3c", FAIL, "still over the cap at the second boundary after a signing over the cap",
                    club=c.index, player=sig["player"], over=over, boundaries=sig["boundaries"])
            elif sig["boundaries"] == 1 and over > charge:
                add("I3c", FAIL, "over the cap by more than the over-cap signing's charge at the first boundary",
                    club=c.index, player=sig["player"], over=over, charge=charge)

    if "PR1" not in skip:
        for snapshot in protected_releases:
            for row in protected_release_problems(snapshot):
                add("PR1", FAIL, row.pop("check"), club=snapshot["club"], player=snapshot["released"], **row)

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

    # I8 named checks: pick words and owners on every record; the 4b page's own shape (slots 1-14) ----------------
    window, notes = trade_window(view), []
    for o in view.board:
        if not o.kind:
            continue
        ours = o.slot != 0 and is_qb_for_pick(view, o)      # slot 0 is the user's work slot, never the page's
        qb = next((p for p in o.players_a if p is not None), None)
        for side, club, words in (("A", o.club_a, o.picks_a), ("B", o.club_b, o.picks_b)):
            for j, w in enumerate(words):
                if not w & 0x3F:
                    continue                                # no pick (a cancelled one keeps slot and year bits)
                r, s, y = pick_fields(w)
                if not pick_word_valid(w):
                    if not skipped("I8.pick_word"):
                        add("I8.pick_word", FAIL, f"side {side} pick word outside round 1-7, slot < 32, year <= 1",
                            slot=o.slot, kind=o.kind, pick=j, word=hex(w), round=r, pick_slot=s, year=y)
                    continue
                owner = view.pick_owner(r, s, y)
                if skipped("I8.pick_owner") or owner is None or club is None or not 0 <= club < CLUBS or owner == club:
                    continue
                add("I8.pick_owner", FAIL if ours else WARN, f"side {side} offers a pick its club does not own",
                    club=club, slot=o.slot, kind=o.kind, word=hex(w), round=r, pick_slot=s, year=y, owner=owner,
                    qb_for_pick=ours)
        if not ours:
            continue
        humans = [c for c in (o.club_a, o.club_b) if c is not None and 0 <= c < CLUBS and clubs[c].human]
        if humans and not skipped("I8.human"):
            add("I8.human", FAIL, "quarterback-for-pick record names a human club", club=humans[0], slot=o.slot,
                player=qb, seller=o.club_a, buyer=o.club_b)
        if not skipped("I8.window"):
            if window is None:
                notes.append(f"I8.window not judged for slot {o.slot}: the Trade Deadline option is unknown")
            elif not window:
                add("I8.window", FAIL, "quarterback-for-pick record outside stage 8's open trade window", club=o.club_b,
                    slot=o.slot, player=qb, stage=stage, week=view.week, option=view.trade_option,
                    deadline_week=view.deadline_week)
        if boundary and not skipped("I8.boundary"):
            add("I8.boundary", FAIL, "quarterback-for-pick record on the board at a week boundary", club=o.club_b,
                slot=o.slot, player=qb, seller=o.club_a, buyer=o.club_b, picks=[hex(w) for w in o.picks_b])
    if notes:
        view.info["i8_notes"] = notes

    # T1: the trades since the previous view ----------------------------------------------------------------------
    if previous is not None and not skipped("T1"):
        t1 = trades_since(previous, view)
        human = lambda c: c is not None and 0 <= c < CLUBS and (clubs[c].human or previous.clubs[c].human)
        cpu_path = cpu_can_trade(previous)
        one_advance = (previous.year_index == view.year_index and previous.stage == view.stage
                       and view.week == previous.week + 1)
        user_groups = []
        for g in t1["groups"]:
            named = sorted({x["club"] for x in g if x["club"] is not None})
            if any(human(c) for c in named):
                user_groups.append({"rows": [x["slot"] for x in g], "clubs": named})
            elif not one_advance:
                t1["notes"].append("T1.window not judged: the views are not one weekly advance apart")
            elif cpu_path is None:
                t1["notes"].append("T1.window not judged: the previous view's Trade Deadline option is unknown")
            elif not cpu_path and not skipped("T1.window"):
                add("T1.window", FAIL, "trade between CPU clubs in an advance that runs no CPU trade tick",
                    club=named[0] if named else None, rows=[x["slot"] for x in g], clubs=named,
                    stage=previous.stage, week=previous.week, option=previous.trade_option,
                    deadline_week=previous.deadline_week)
        if user_groups:
            t1["user_trades"] = user_groups                 # the user's own (his screen's rules), not judged here
        changes = t1["pick_changes"]
        for q in t1["qb_for_pick"]:
            seller, buyer = q["seller"], q["buyer"]
            if (human(seller) or human(buyer)) and not skipped("T1.human"):
                add("T1.human", FAIL, "quarterback-for-pick trade with a human club", club=buyer if human(buyer)
                    else seller, player=q["player"], seller=seller, buyer=buyer, rows=q["rows"])
            # C22 (c): 4b posts only before the native deadline week, whatever the Trade Deadline option says
            if (one_advance and previous.deadline_week is not None and previous.week >= previous.deadline_week
                    and not skipped("T1.deadline")):
                add("T1.deadline", FAIL, "quarterback-for-pick trade at or after the deadline week (C22 (c))",
                    club=buyer, player=q["player"], seller=seller, week=previous.week,
                    deadline_week=previous.deadline_week, option=previous.trade_option, rows=q["rows"])
            if not skipped("T1.counts"):
                for c in (seller, buyer):
                    if 0 <= c < CLUBS and not 50 <= clubs[c].count <= 53:
                        add("T1.counts", FAIL, "active count outside 50..53 after a quarterback-for-pick trade",
                            club=c, count=clubs[c].count, role="seller" if c == seller else "buyer", rows=q["rows"])
            if not skipped("T1.buyer_qbs") and 0 <= buyer < CLUBS:      # C22 addendum (1): at most 2 before, never 4 after
                qbs = [i for i in clubs[buyer].active if view.record(i)[0x35] == QB]
                if len(qbs) > 3:
                    before = [i for i in previous.clubs[buyer].active if previous.record(i)[0x35] == QB]
                    add("T1.buyer_qbs", FAIL, "buyer above 3 active quarterbacks after a quarterback-for-pick trade",
                        club=buyer, player=q["player"], quarterbacks=len(qbs), before=len(before), rows=q["rows"])
            if not skipped("T1.seller_depth") and 0 <= seller < CLUBS:
                qbs = [i for i in clubs[seller].active if view.record(i)[0x35] == QB]
                # healthy now, or at the previous boundary: a man hurt in this week's game was hurt after the trade
                healthy = [i for i in qbs if _fully_healthy(view.record(i)) or _fully_healthy(previous.record(i))]
                if len(qbs) < 2 or len(healthy) < 2:
                    add("T1.seller_depth", FAIL, "seller left with fewer than 2 quarterbacks or 2 healthy ones",
                        club=seller, player=q["player"], quarterbacks=len(qbs), healthy=len(healthy), rows=q["rows"])
            if changes is not None and not skipped("T1.pick"):
                hits = [c for c in changes if (c["round"], c["year"], c["from"], c["to"]) ==
                        (q["round"], q["year"], buyer, seller)]
                if len(hits) != 1:
                    add("T1.pick", FAIL, "the pick table does not show exactly this pick passing buyer to seller",
                        club=buyer, player=q["player"], round=q["round"], year=q["year"], seller=seller,
                        matching_changes=hits, rows=q["rows"])
        for q in t1["player_for_pick"]:
            _check_player_for_pick(q, view, previous, clubs, human, one_advance, changes, add, skipped)
        if (changes is not None and previous.stage == stage == 8 and previous.year_index == view.year_index
                and not skipped("T1.unexplained_pick")):        # within one regular season no draft roll moves picks
            pool = [(x["arg1"], x["arg2"], x["club"]) for g in t1["groups"] for x in g
                    if x["player"] is None and x["arg1"]]
            for c in changes:
                key = (c["round"], c["year"], c["from"])
                if key in pool:
                    pool.remove(key)
                else:
                    add("T1.unexplained_pick", FAIL, "pick changed owner with no trade row giving it",
                        club=c["from"] if 0 <= c["from"] < CLUBS else None, round=c["round"], year=c["year"],
                        pick_slot=c["slot"], owner_before=c["from"], owner_after=c["to"])
        view.info["trades_since_previous"] = {k: t1[k] for k in ("new_rows", "qb_for_pick", "player_for_pick", "notes")} | {
            "groups": len(t1["groups"]), "pick_changes": None if changes is None else len(changes),
            **({"user_trades": t1["user_trades"]} if "user_trades" in t1 else {})}

    # I11 -----------------------------------------------------------------------------------------------------------
    if "I11" not in skip and playing:
        preseason = stage == 7
        schedule = view.info.get("next_game")
        for c in clubs:
            if c.human and not view.auto_sign_cut:
                continue                               # a manual human club is the user's (F5)
            qbs = [i for i in c.active if view.record(i)[0x35] == QB]
            healthy = [i for i in qbs if not _u32(view.record(i), 0x20) & (INJURED | WEEKS_MASK)
                       and not _u32(view.record(i), 0x24) & STATUS_MASK]
            if not healthy:
                if schedule is None:
                    nxt = True                         # no schedule in this view: judge as before F2, every club
                else:
                    nxt = c.index in schedule["clubs"] or schedule["bracket_pending"]
                add("W7" if preseason else "I11", FAIL if nxt and not preseason else WARN,
                    ("preseason club without a healthy quarterback" if preseason else
                     "no healthy quarterback on the active list" + ("" if nxt else " (no next game)"))
                    + (" at kick-off" if kickoff else ""),
                    club=c.index, quarterbacks=len(qbs),
                    next_game=None if schedule is None else ("bracket not built yet" if schedule["bracket_pending"]
                                                             and c.index not in schedule["clubs"] else nxt),
                    on_ir=sum(1 for i, _ in view.ir.clubs[c.index] if view.record(i)[0x35] == QB),
                    hurt=[{"index": i, "injured": bool(_u32(view.record(i), 0x20) & INJURED),
                           "weeks": (_u32(view.record(i), 0x20) >> 22) & 0xFF,
                           "status": (_u32(view.record(i), 0x24) >> 28) & 7} for i in qbs])

    # W12 -----------------------------------------------------------------------------------------------------------
    if "W12" not in skip:
        for pair in rank_lock_pairs(view):
            add("W12", WARN, "healthy quarterback rank-locked behind a row 0 man he leads by 6 or more",
                club=pair["club"], player=pair["player_index"],
                **{k: pair[k] for k in ("row", "overall", "row0_player", "row0_name", "row0_overall", "lead",
                                        "row0_locked")})

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
def load_target(path: Path, *, label: str | None = None,
                deadline_week: int = DEFAULT_DEADLINE_WEEK) -> tuple[LeagueView, dict]:
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
    view = view_from_save(payload, label=label or str(path), deadline_week=deadline_week)
    view.info.update(facts)
    return view, facts


class RepairError(RuntimeError):
    pass


def repair_rank_locks(source: Path, target: Path, *, confirm: bool = False, overwrite: bool = False) -> dict:
    """W12's repair. Lists the pairs; only with ``confirm`` clears bit 0 of +0x52 on exactly W12's men and writes a new
    signed copy at ``target``, verified on reload."""
    import hashlib
    from mod_editor.core import nfl2k5_franchise_save as fs
    from mod_editor.core import nfl2k5_roster_records as rr
    source, target = Path(source), Path(target)
    save = fs.FranchiseSave.load(source)               # refuses a save whose EXTRA does not verify
    before = save.to_bytes()
    view = view_from_save(before, label=str(source))
    pairs = rank_lock_pairs(view)
    for pair in pairs:
        if not view.managed(pair["club"]):             # never a club whose chart the user manages
            raise RepairError(f"{pair['club_name']}: the user manages this depth chart")
    receipt = {"tool": "franchise_invariants --repair-rank-locks", "source": str(source),
               "source_sha256": hashlib.sha256(before).hexdigest(), "year_index": view.year_index,
               "confirmed": bool(confirm), "pairs": pairs, "target": str(target), "written": None, "verified": None}
    if view.year_index < 1:
        receipt["note"] = "first season: the shipped depth charts stand; nothing listed or written"
        return receipt
    if not pairs:
        receipt["note"] = "no W12 pair: nothing to repair, nothing written"
        return receipt
    if not confirm:
        receipt["note"] = "listed only: nothing written (confirm to write the repaired copy)"
        return receipt
    if target.exists() and not overwrite:
        raise RepairError(f"{target} already exists; choose a new folder for the repaired copy")
    offsets = []
    for pair in pairs:
        at = save.player_offset(pair["player_index"])
        if bytes(save.buffer[at:at + PLAYER_SIZE]) != view.record(pair["player_index"]):
            raise RepairError(f"player {pair['player_index']}: the save API's record is not the view's")
        save.buffer[at + RANK_LOCK] &= 0xFE
        offsets.append(at + RANK_LOCK)
    receipt["writer"] = save.write(target, overwrite=overwrite)
    receipt["written"] = str(target)
    after = rr.SaveContainer.load(target, require_signature=True).savegame
    problems = []
    if len(after) != len(before):
        problems.append("the copy's length differs")
    changed = [k for k in range(min(len(before), len(after))) if before[k] != after[k]]
    if changed != sorted(offsets):
        problems.append(f"changed bytes {[hex(k) for k in changed][:12]} are not the cleared +0x52 bytes")
    if any(before[k] ^ after[k] != 1 for k in changed):
        problems.append("a changed byte differs by more than bit 0")
    again = view_from_save(after, label=str(target))
    still = {p["player_index"] for p in rank_lock_pairs(again)} & {p["player_index"] for p in pairs}
    if still:
        problems.append(f"still W12 after the repair: {sorted(still)}")
    if check(again, skip=["W12"]).violations != check(view, skip=["W12"]).violations:
        problems.append("another invariant's rows changed")
    receipt.update(target_sha256=hashlib.sha256(after).hexdigest(), changed_bytes=[hex(k) for k in changed],
                   verified=not problems, problems=problems)
    if problems:
        raise RepairError("; ".join(problems) + f" (the copy at {target} must not be used)")
    return receipt


def repair_text(receipt: dict) -> str:
    """The user-visible lines of the repair (evidence/owner/USER_TEXT.md lists them)."""
    pairs, target = receipt["pairs"], receipt["target"]
    if receipt["year_index"] < 1:
        return ("Rank-lock repair: this save is in its first season. The shipped depth charts stand, so nothing is "
                "listed or changed.")
    if not pairs:
        return ("Rank-lock repair: no quarterback is locked behind a starter he outrates by 6 or more. "
                "Nothing to change.")
    done = receipt["written"] is not None
    count = f"{len(pairs)} quarterback" + ("s" if len(pairs) != 1 else "")
    lines = [f"Rank-lock repair: unlocked {count} and wrote a new signed copy to {target}. "
             "The copy was read back and verified. Your original save was not changed." if done else
             f"Rank-lock repair (nothing written yet): {count} would be unlocked:"]
    for p in pairs:
        lines.append(f"  {p['club_name']}: {p['player_name']} ({p['overall']} overall, No. {p['row'] + 1} on the "
                     f"depth chart) is locked behind the starter {p['row0_name']} ({p['row0_overall']} overall). "
                     + ("His depth chart lock was cleared." if done else "His depth chart lock would be cleared."))
    if not done:
        lines.append(f"To write a repaired copy to {target}, run the same command with --confirm. Your original "
                     "save is never changed, and clubs whose depth chart you manage are never touched.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", type=Path, help="signed franchise folder or SAVEGAME.DAT")
    ap.add_argument("--memory", type=Path, help="memory image (B81MEMv1 or Codex's (bounds, regions) pickle)")
    ap.add_argument("--root", type=lambda s: int(s, 0), help="league root (default: the word at 0xB72918)")
    ap.add_argument("--ir-store", type=lambda s: int(s, 0), help="IR owner's store VA (default: found in memory)")
    ap.add_argument("--xbe", type=Path, help="executable: the IR store VA comes from its layout")
    ap.add_argument("--previous", type=Path, help="the previous week's save or memory image (I8 one-week rule, T1)")
    ap.add_argument("--deadline-week", type=int, default=None,
                    help="the executable's trade deadline byte 0x5151C5 (default: read from a memory image; 9 for a "
                         "save, the deadline owner's value; retail is 6)")
    ap.add_argument("--boundary", action=argparse.BooleanOptionalAction, default=None,
                    help="the view is a week boundary: no quarterback-for-pick record may be on the board "
                         "(I8.boundary; default on for --memory, off for a save)")
    ap.add_argument("--allowed-kinds", default=",".join(map(str, DEFAULT_KINDS)))
    ap.add_argument("--skip", action="append", default=[],
                    help="I1..I9, I3c, I11, W12, I4.injured_row0, an I8.* or T1.* name, or T1 (repeatable)")
    ap.add_argument("--kickoff", action="store_true", help="judge I11 alone, as a failure (the state at a kick-off)")
    ap.add_argument("--over-cap", action="append", default=[], metavar="CLUB:PLAYER:BOUNDARIES",
                    help="I3c: a signing over the cap, the week boundaries since it (repeatable)")
    ap.add_argument("--strict", action="store_true", help="warnings count as failures")
    ap.add_argument("--repair-rank-locks", type=Path, metavar="NEW_FOLDER",
                    help="list quarterbacks whose depth chart lock keeps them behind a starter they outrate by 6 or "
                         "more (from the second season, clubs the computer manages); with --confirm, write a "
                         "repaired copy of the save to NEW_FOLDER (your original save is never changed)")
    ap.add_argument("--confirm", action="store_true",
                    help="with --repair-rank-locks: write the repaired copy; without it the quarterbacks are only "
                         "listed and nothing is written")
    ap.add_argument("--out", type=Path, help="write the JSON here and print only the summary line")
    a = ap.parse_args(argv)
    if bool(a.target) == bool(a.memory):
        ap.error("give a save target or --memory, not both")
    if a.confirm and not a.repair_rank_locks:
        ap.error("--confirm goes with --repair-rank-locks")
    if a.repair_rank_locks:
        if not a.target:
            ap.error("--repair-rank-locks repairs a signed save folder, not a memory image")
        try:
            receipt = repair_rank_locks(a.target, a.repair_rank_locks, confirm=a.confirm)
        except Exception as exc:                       # RepairError, FranchiseSaveError, RosterRecordError
            print(f"Rank-lock repair refused: {exc}. Nothing was written." if "must not be used" not in str(exc)
                  else f"Rank-lock repair failed its read-back check: {exc}.")
            return 2
        if a.out:
            a.out.write_text(json.dumps(receipt, indent=1) + "\n")
        print(repair_text(receipt))
        return 0

    def load(path):
        if a.memory:
            memory = load_memory(path)
            store = a.ir_store
            if store is None and a.xbe:
                from mod_editor.core import nfl2k5_injured_reserve as ir
                store = ir.store_va(a.xbe.read_bytes()) or 0
            return view_from_memory(memory.read, root=a.root, ir_store=store,
                                    search=lambda n: memory.find(n, 0x10000, 0x2000000), label=str(path),
                                    deadline_week=a.deadline_week)
        return load_target(path, deadline_week=a.deadline_week or DEFAULT_DEADLINE_WEEK)[0]

    view = load(a.memory or a.target)
    previous = load(a.previous) if a.previous else None
    over = [dict(zip(("club", "player", "boundaries"), map(int, x.split(":")))) for x in a.over_cap]
    report = check(view, previous=previous, allowed_kinds=[int(k) for k in a.allowed_kinds.split(",") if k],
                   skip=a.skip, kickoff=a.kickoff, over_cap_signings=over, boundary=a.boundary)
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
