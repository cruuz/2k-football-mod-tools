"""Modern injured reserve in a franchise save (b780 IR1): the format and the Studio API. EXPERIMENTAL.

The game side is ``nfl2k5_injured_reserve`` (runtime ``tools/injured_reserve/runtime.c``); keep the two in step.

Where it lives
--------------
The retail IR block of the franchise front office, ``FRONT_OFFICE_BLOCK + 0x4FD0`` (``nfl2k5_franchise_save``
``F_INJURED_RESERVE``): 160 cells = 32 clubs x 5 slots x {u16 low, u16 high}. No save size, footer or admission change.

* Low halves: exactly what every build reads (``FUN_002d0540``: primary player index, 0xFFFF empty). A modern save
  keeps each club's first five IR players here, packed from slot 0, so an older build loads them as its own
  season-ending IR.
* High halves (always 0 from retail and older writers; the native loader never reads them): the extension, 160 words,
  word ``w`` = high half of cell ``w``:

  ======  ======================================================================================================
  word    content
  ======  ======================================================================================================
  0       magic 0x5249 ("IR", format 1)
  1       checksum: a = 1, b = 0; for each u16 of the 160 low halves, then of high words 2..159:
          a = (a + w) % 65521, b = (b + a) % 65521; value = (a ^ (b << 1) ^ (b >> 15)) & 0xFFFF
  2..9    returns used this season, 4 bits a club (club c: word 2 + c // 4, bits 4 * (c % 4))
  10..17  extended entries a club (beyond its first five), 4 bits a club, 0..15
  18..57  the first five entries' states, 4 bits a cell (cell k = club * 5 + slot: word 18 + k // 4, bits 4 * (k % 4))
  58..159 extended entries, club 0's first, then club 1's, ...: bits 0-11 player index, bits 12-15 state
  ======  ======================================================================================================

  State (4 bits): bits 0-2 games missed (the club's played games since the placement, 0..7, saturating; 4 or more
  meets the minimum), bit 3 stays on injured reserve for the season.

Capacity: 20 a club (5 + 15) and 102 extended entries league-wide. The game refuses a placement past either limit
(the player stays on the 53, as when the retail list was full), so every IR player is always saved.
A save without the magic, or with a checksum that does not match (an older build or another tool wrote the block), is
a legacy save: its low halves are the IR players with 0 games missed and no returns used; the game upgrades it on
load (the 4-game clock starts then).
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from . import nfl2k5_franchise_save as fs
from . import nfl2k5_roster_records as rr

CELLS = 160
CLUBS = 32
LEGACY_SLOTS = 5
CAP = 20
EXTENDED_CAP = 102
MAGIC = 0x5249
W_MAGIC, W_SUM, W_RETURNS, W_COUNTS, W_STATES, W_EXT = 0, 1, 2, 10, 18, 58
MIN_GAMES = 4
RETURNS = 8
LONG_WEEKS = 4
ACTIVE = 53
SEASON = 8
EMPTY = 0xFFFF
INJURED = 0x80000000
WEEKS_SHIFT = 22
STATUS_OUT = 0x40000000
STATUS_MASK = 0x70000000

# The game's own refusal texts (tools/injured_reserve/runtime.c), word for word.
REASONS = {
    "not_injured": "Only an injured player can go on injured reserve.",
    "full": "Your injured reserve list is full.",
    "too_soon": "This player must miss at least 4 games on injured reserve before he can return.",
    "still_injured": "This player is still injured. He can return once he is healthy.",
    "season": ("Your club has used all 8 returns from injured reserve this season. This player stays on injured "
               "reserve until the season ends."),
    "roster_full": "Your roster is full. Release a player before bringing this player back from injured reserve.",
    "not_on_team": "This player is not on that club's roster.",
    "not_on_ir": "This player is not on that club's injured reserve.",
    "legacy_full": ("This save has no modern injured reserve yet (an older build wrote it), so it holds 5 players a "
                    "club. Load and save it once in a build with modern injured reserve."),
}


class InjuredReserveError(ValueError):
    """A refused IR edit; str(error) is the game's own text, fit to show as is."""


@dataclass(frozen=True)
class IrEntry:
    team: int
    slot: int                  # 0..19 in the club's list; 0..4 are the legacy cells
    player_index: int
    name: str
    games_missed: int          # 0..7 (saturating); MIN_GAMES or more meets the minimum
    season_ending: bool
    injured: bool
    weeks_out: int
    can_return: bool
    reason: str | None         # None when he can return now, else the game's text


@dataclass(frozen=True)
class IrState:
    extension: bool            # False: a legacy save (retail / v0.8 / v0.9 or an older build wrote it)
    returns_used: tuple[int, ...]
    entries: tuple[IrEntry, ...]
    extended_used: int

    @property
    def legacy(self) -> bool:
        return not self.extension

    def club(self, team: int) -> list[IrEntry]:
        return [e for e in self.entries if e.team == team]

    def returns_left(self, team: int) -> int:
        return max(0, RETURNS - self.returns_used[team])


# ---------------------------------------------------------------------------------------------- the block codec
def checksum(low: list[int], high: list[int]) -> int:
    a, b = 1, 0
    for word in list(low) + list(high[W_RETURNS:]):
        a = (a + word) % 65521
        b = (b + a) % 65521
    return (a ^ (b << 1) ^ (b >> 15)) & 0xFFFF


def _nibble(high, base, i):
    return (high[base + i // 4] >> (4 * (i % 4))) & 15


def _set_nibble(high, base, i, value):
    word = base + i // 4
    shift = 4 * (i % 4)
    high[word] = (high[word] & ~(15 << shift) & 0xFFFF) | ((value & 15) << shift)


def decode(block: bytes, *, players: int | None = None) -> tuple[bool, list[int], list[list[tuple[int, int, bool]]]]:
    """(extension, returns used per club, per club [(player index, games missed, season-ending)]) of a 640-byte block."""
    if len(block) != CELLS * 4:
        raise InjuredReserveError("the injured reserve block is 640 bytes")
    low = [struct.unpack_from("<H", block, 4 * k)[0] for k in range(CELLS)]
    high = [struct.unpack_from("<H", block, 4 * k + 2)[0] for k in range(CELLS)]
    extension = high[W_MAGIC] == MAGIC and high[W_SUM] == checksum(low, high)
    clubs: list[list[tuple[int, int, bool]]] = [[] for _ in range(CLUBS)]
    returns = [0] * CLUBS
    w = W_EXT
    for c in range(CLUBS):
        seen = set()
        for i in range(LEGACY_SLOTS):
            index = low[c * LEGACY_SLOTS + i]
            if index == EMPTY or (players is not None and index >= players) or index in seen:
                continue
            seen.add(index)
            state = _nibble(high, W_STATES, c * LEGACY_SLOTS + i) if extension else 0
            clubs[c].append((index, state & 7, bool(state & 8)))
        if extension:
            returns[c] = _nibble(high, W_RETURNS, c)
            for _ in range(_nibble(high, W_COUNTS, c)):
                if w >= CELLS:
                    break
                value = high[w]
                w += 1
                index, state = value & 0xFFF, value >> 12
                if (players is not None and index >= players) or index in seen or len(clubs[c]) >= CAP:
                    continue
                seen.add(index)
                clubs[c].append((index, state & 7, bool(state & 8)))
    return extension, returns, clubs


def encode(clubs: list[list[tuple[int, int, bool]]], returns: list[int], *, extension: bool) -> bytes:
    """The 640-byte block for these entries. extension=False writes only the low halves (legacy, 5 a club)."""
    if len(clubs) != CLUBS or len(returns) != CLUBS:
        raise InjuredReserveError("one list per club (32)")
    low = [EMPTY] * CELLS
    high = [0] * CELLS
    extended = []
    for c, entries in enumerate(clubs):
        if len(entries) > (CAP if extension else LEGACY_SLOTS):
            raise InjuredReserveError(REASONS["full"] if extension else REASONS["legacy_full"])
        if not 0 <= returns[c] <= RETURNS:
            raise InjuredReserveError(f"club {c}: returns used must be 0..{RETURNS}")
        for i, (index, games, season) in enumerate(entries):
            if not 0 <= index < (0xFFFF if i < LEGACY_SLOTS else 0x1000):
                raise InjuredReserveError(f"club {c}: player index {index} cannot be stored")
            state = min(max(int(games), 0), 7) | (8 if season else 0)
            if i < LEGACY_SLOTS:
                low[c * LEGACY_SLOTS + i] = index
                _set_nibble(high, W_STATES, c * LEGACY_SLOTS + i, state)
            else:
                extended.append(index | state << 12)
        _set_nibble(high, W_RETURNS, c, returns[c])
        _set_nibble(high, W_COUNTS, c, max(0, len(entries) - LEGACY_SLOTS))
    if len(extended) > EXTENDED_CAP:
        raise InjuredReserveError(REASONS["full"])
    if extension:
        high[W_EXT:W_EXT + len(extended)] = extended
        high[W_MAGIC] = MAGIC
        high[W_SUM] = checksum(low, high)
    else:
        high = [0] * CELLS
    return b"".join(struct.pack("<HH", low[k], high[k]) for k in range(CELLS))


# ---------------------------------------------------------------------------------------------- saves
def _save(save) -> fs.FranchiseSave:
    if isinstance(save, fs.FranchiseSave):
        return save
    return fs.FranchiseSave(bytes(save))


def _block_offset(save: fs.FranchiseSave) -> int:
    return save.front_office_block + fs.F_INJURED_RESERVE


def _players(save: fs.FranchiseSave) -> int:
    return save.roster.tables["primary"].count if hasattr(save.roster, "tables") else len(save.roster.players)


def injury(save: fs.FranchiseSave, index: int) -> tuple[bool, int]:
    word = save.u32(save.player_offset(index) + 0x20)
    return bool(word & INJURED), (word >> WEEKS_SHIFT) & 0xFF


def _why(save, games: int, season: bool, returns: int, index: int) -> str | None:
    if season:
        return REASONS["season"]
    if games < MIN_GAMES:
        return REASONS["too_soon"]
    if injury(save, index)[0]:
        return REASONS["still_injured"]
    if returns >= RETURNS:
        return REASONS["season"]
    return None


def read_state(save) -> IrState:
    """Every club's IR list, returns used and each player's standing (games missed, can he return now and why not)."""
    save = _save(save)
    off = _block_offset(save)
    try:
        players = save.roster.tables["primary"].count
    except (AttributeError, KeyError):
        players = None
    extension, returns, clubs = decode(bytes(save.buffer[off:off + CELLS * 4]), players=players)
    entries = []
    for c, rows in enumerate(clubs):
        for slot, (index, games, season) in enumerate(rows):
            hurt, weeks = injury(save, index)
            reason = _why(save, games, season, returns[c], index) if extension else REASONS["legacy_full"]
            name = save.player_name(index) if c < save.league_team_count else ""
            entries.append(IrEntry(c, slot, index, name, games, season, hurt, weeks, reason is None, reason))
    used = sum(max(0, len(rows) - LEGACY_SLOTS) for rows in clubs)
    return IrState(extension, tuple(returns), tuple(entries), used)


def _clubs_of(state: IrState) -> list[list[tuple[int, int, bool]]]:
    clubs: list[list[tuple[int, int, bool]]] = [[] for _ in range(CLUBS)]
    for e in sorted(state.entries, key=lambda e: (e.team, e.slot)):
        clubs[e.team].append((e.player_index, e.games_missed, e.season_ending))
    return clubs


def write_block(buffer: bytearray, front_office_block: int, clubs, returns, *, extension: bool) -> None:
    off = front_office_block + fs.F_INJURED_RESERVE
    buffer[off:off + CELLS * 4] = encode(clubs, returns, extension=extension)


def write_state(save, clubs, returns, *, extension: bool | None = None) -> bytes:
    """New save bytes with this IR content ([(index, games missed, season-ending)] per club, returns used per club).
    extension None keeps the save's own kind (a legacy save stays legacy: 5 a club)."""
    save = _save(save)
    if extension is None:
        extension = read_state(save).extension
    buffer = bytearray(save.to_bytes())
    write_block(buffer, save.front_office_block, clubs, returns, extension=extension)
    return bytes(buffer)


def can_place(save, team: int, player_index: int) -> str | None:
    """None when the game would accept this placement now, else its text."""
    save = _save(save)
    state = read_state(save)
    if player_index not in save.team_player_indices(team):
        return REASONS["not_on_team"]
    if not injury(save, player_index)[0]:
        return REASONS["not_injured"]
    mine = state.club(team)
    if len(mine) >= (CAP if state.extension else LEGACY_SLOTS):
        return REASONS["full"] if state.extension else REASONS["legacy_full"]
    if len(mine) >= LEGACY_SLOTS and (state.extended_used >= EXTENDED_CAP or player_index > 0xFFF):
        return REASONS["full"]
    return None


def place(save, team: int, player_index: int) -> bytes:
    """Put an injured player on his club's IR (off the 53, salary still counted). Returns the new save bytes;
    raises InjuredReserveError with the game's text."""
    save = _save(save)
    reason = can_place(save, team, player_index)
    if reason:
        raise InjuredReserveError(reason)
    state = read_state(save)
    clubs = _clubs_of(state)
    clubs[team].append((player_index, 0, False))
    candidate = _remove_from_team(save, team, player_index)
    write_block(candidate, save.front_office_block, clubs, list(state.returns_used), extension=state.extension)
    return _recount(candidate, team)


def can_activate(save, team: int, player_index: int) -> str | None:
    save = _save(save)
    state = read_state(save)
    entry = next((e for e in state.club(team) if e.player_index == player_index), None)
    if entry is None:
        return REASONS["not_on_ir"]
    if not state.extension:
        return REASONS["legacy_full"]
    if entry.reason:
        return entry.reason
    limit = ACTIVE if save.header.stage >= 8 else 65
    if len(save.team_player_indices(team)) >= limit:
        return REASONS["roster_full"]
    return None


def activate(save, team: int, player_index: int) -> bytes:
    """Bring a player back from IR (uses one of the club's 8 returns). Returns the new save bytes."""
    save = _save(save)
    reason = can_activate(save, team, player_index)
    if reason:
        raise InjuredReserveError(reason)
    state = read_state(save)
    clubs = _clubs_of(state)
    clubs[team] = [row for row in clubs[team] if row[0] != player_index]
    returns = list(state.returns_used)
    returns[team] += 1
    candidate = _add_to_team(save, team, player_index)
    write_block(candidate, save.front_office_block, clubs, returns, extension=True)
    return _recount(candidate, team)


def _remove_from_team(save: fs.FranchiseSave, team: int, player_index: int) -> bytearray:
    """The game's own removal (0x2BD900 with 0, 0): off the list, specialist roles follow (0xC3A90), salary kept."""
    count, slots = save._team_slots(team)
    target = save.player_offset(player_index)
    squads = save._validate_ownership()
    candidate = bytearray(save.buffer)
    removed = slots[:count].index(target)
    active = [save.player_index(o) for o in slots[:count] if o != target]
    save._repack_candidate(candidate, team, active, squads[team])
    candidate[target + 0x52] &= ~0x1F
    roles = slice(save.team_offset(team) + 0x194, save.team_offset(team) + 0x19A)
    candidate[roles] = bytes(rr.specialists_after_removal(candidate[roles], removed))
    return candidate


def _add_to_team(save: fs.FranchiseSave, team: int, player_index: int) -> bytearray:
    count, slots = save._team_slots(team)
    squads = save._validate_ownership()
    candidate = bytearray(save.buffer)
    active = [save.player_index(o) for o in slots[:count]] + [player_index]
    save._repack_candidate(candidate, team, active, squads[team])
    return candidate


def _recount(candidate: bytearray, team: int) -> bytes:
    """The club's payroll (+0x124) as the game's 0xC3F00 sums it: the 53 plus 0x246F20, the club's IR players. Run
    after the IR block is written, so the player just placed still counts and the one just activated counts once
    (FC3: the recount ran first, so a Studio placement saved the payroll without him until the game's next recount)."""
    from . import nfl2k5_practice_squad as ps
    try:
        return ps.recompute_salary(bytes(candidate), team)
    except ValueError as exc:
        raise InjuredReserveError(str(exc)) from exc


# ---------------------------------------------------------------------------------------------- roster bodies (RST2)
def long_injury_words(word20: int, word24: int, weeks: int) -> tuple[int, int]:
    """Player +0x20 / +0x24 for a player a franchise start puts on IR: injured, ``weeks`` out (4..255), status Out.
    The same fields the game's own injuries use (0xE6680 clears them; the weekly tick counts the weeks down)."""
    if not LONG_WEEKS <= weeks <= 255:
        raise InjuredReserveError(f"a player who starts on injured reserve is out {LONG_WEEKS}..255 weeks")
    word20 = (word20 & ~(0xFF << WEEKS_SHIFT) & 0xFFFFFFFF) | INJURED | (weeks << WEEKS_SHIFT)
    word24 = (word24 & ~STATUS_MASK & 0xFFFFFFFF) | STATUS_OUT
    return word20, word24


def mark_long_injury(buffer: bytearray, player_offset: int, weeks: int) -> None:
    """In a roster or save buffer: the player at ``player_offset`` starts the franchise on his club's IR."""
    w20, w24 = struct.unpack_from("<II", buffer, player_offset + 0x20)
    struct.pack_into("<II", buffer, player_offset + 0x20, *long_injury_words(w20, w24, weeks))


def starts_on_ir(word20: int) -> bool:
    """True when a franchise start (modern IR) puts this player on his club's IR: injured with 4 or more weeks out."""
    return bool(word20 & INJURED) and (word20 >> WEEKS_SHIFT) & 0xFF >= LONG_WEEKS


__all__ = ["CAP", "LEGACY_SLOTS", "EXTENDED_CAP", "MIN_GAMES", "RETURNS", "LONG_WEEKS", "ACTIVE", "REASONS",
           "InjuredReserveError", "IrEntry", "IrState", "checksum", "decode", "encode", "read_state", "write_state",
           "write_block", "can_place", "place", "can_activate", "activate", "injury", "long_injury_words",
           "mark_long_injury", "starts_on_ir"]
