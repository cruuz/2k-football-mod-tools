"""EXPERIMENTAL / UNWITNESSED franchise rule kernel and host transactions.

The installed XBE owner is deliberately dormant. Retail game-result consumers
still pair players by ownership slot, and no native persistent ledger transport
has landed. ``require_runtime_ready`` prevents advertising this kernel as an
enforced game patch. See ASTRA_FRANCHISE_2026_REPORT.md and WIRING.md.

R1-R5 refer to the supplied September 5 research memo. No network rule lookup
is needed to reproduce this implementation of that frozen specification.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import struct
from dataclasses import dataclass

OWNER = "nfl2k5_franchise_2026"
CODE_SIZE, DATA_SIZE = 5120, 4096
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
RUNTIME_READY = False
UI_TEXT = ("Retail: Owned players form the game roster and IR has no in-season returns. "
           "Patch: 2026 rule kernel is EXPERIMENTAL / UNWITNESSED. Game enforcement "
           "is unavailable: the MyCareer save block and reserve storage do not "
           "own these counters, and player results still need mapping.")
MAX_PLAYERS, TEAMS, IR_SLOTS = 4096, 32, 5
EMPTY = 0xffff
MAGIC = b"F26K\x01\x00\x00\x00"
TEAM_BASE, TEAM_SIZE, HISTORY_BASE, IR_BASE = 32, 16, 544, 2592
USED_END = IR_BASE + TEAMS * IR_SLOTS * 8
ELIGIBLE, CHARGED, PRACTICE, EXPIRED, CUTDOWN, LEGACY = 1, 2, 4, 8, 16, 32
COMPANION_MAGIC = b"F26HOST\x01"
COMPANION_SIZE = 8 + 32 + 32 + DATA_SIZE
OL = frozenset((12, 13, 14))  # Primary enum C, G, T, preserved by pooled defenses.
RUNTIME_PINS = (
    ("slot_result_map", 0xc5280, 121, "3514e52ea1b2c3e3294461a663358b029041657bea8614cd323a0cb0caa61bee"),
    ("parallel_award_owner", 0x27dbc0, 788, "c8e40b8ed48fd1dca6192f6afeeeb3463de4fc314c66e501a81752255ef51465"),
    ("ir_serializer", 0x2d09c1, 59, "3b0a4f39877840fc7017cb8bbd7472fe0c86b41ce556e47634a6b35222719bf2"),
    ("ir_restore", 0x2d0f3f, 48, "0606d3f6972d6b0a4c6408e731bc529e91a5231a93004a7fd6d5426d35477400"),
    ("office_size", 0x2d0780, 6, "adeb0e31cc24628c34d78764298bc3370fbc44c24d2d1b0ba58348eb26ff967c"),
    ("trade_predicate", 0x247d10, 41, "e18d7b342a89f6b081049a211754ba0d3b08ceef0c339eb7e02f6556719735ed"),
    ("pending_trade_purge", 0x247e20, 40, "5cc78dd0f89c0cc25733b5d121410d84ce87df33ed5195159532dec940a0d84a"),
)


class Franchise2026Error(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise Franchise2026Error(message)


def _integer(value, low, high, name):
    _require(type(value) is int and low <= value <= high, f"invalid {name}: {value!r}")
    return value


def require_runtime_ready():
    """Build preflight must call this before copying a disc for this option."""
    if not RUNTIME_READY:
        raise Franchise2026Error("2026 franchise enforcement is unavailable: native saved counters "
                                 "and player-result identity adapters are not implemented; "
                                 "MyCareer's 128-byte footer and the reserve arena are not a ledger")


def persistence_contract():
    """Current format ownership, not a grant to use apparently empty bytes.

    These are the shipped schemas, independent of which options are selected.
    Removing another owner from a build does not transfer its record bits.
    """
    from . import nfl2k5_my_career_save as career
    from . import nfl2k5_roster_arena as arena
    from . import nfl2k5_abilities_runtime as abilities
    from . import nfl2k5_guardian_overlay as guardian
    from . import nfl2k5_player_star as star
    occupied = star.TAG_BIT | (abilities.ABILITY_MASK >> 8) | guardian.RECORD_BIT
    return dict(
        ledger_bytes=DATA_SIZE, native_ledger_bytes_owned=0,
        mycareer=dict(owner="nfl2k5_my_career", bytes=career.SIZE,
                      native_container_sizes=list(career.BASE_SIZES),
                      career_container_sizes=list(career.SIZES),
                      # byte 82 = the MyCareer Settings bits (beta 65: first person, Spectate, star Off; values 0..7)
                      settings_byte=82,
                      reserved_zero_spans=[[83, 84], [88, 128]],
                      reusable_bytes=0, extensible=False),
        reserve_arena=dict(owner="nfl2k5_roster_arena_growth",
                           version=arena.SAVE_VERSION, bytes=arena.ARENA_SIZE,
                           growth=arena.ARENA_SIZE - arena.RETAIL_SIZE,
                           block_offset=arena.BLOCK_OFFSET, block_bytes=arena.BLOCK_SIZE,
                           reusable_bytes=0, padding_is_allocation=False),
        player_flags=dict(offset=star.TAG_RECORD_OFFSET, occupied_mask=occupied,
                          unassigned_mask=0xff & ~occupied,
                          required_history_bits=4, owned_ledger_mask=0),
        blockers=[
            dict(id="save_transport", detail="No Franchise-2026 save namespace, size admission, "
                 "serialize/restore or signed transaction owns the 4096-byte ledger. "
                 "MyCareer accepts only its fixed footer; reserve overflow owns its own block."),
            dict(id="player_lifecycle", detail="Reserve epoch changes do not remap or clear "
                 "Franchise-2026 histories on primary slot reuse, import or retirement."),
            dict(id="game_day_projection", detail="61730 and the arena_stage adapter copy the "
                 "permanent active prefix in competitive games; no accepted elevations or 47/48 selection enter it."),
            dict(id="result_identity", detail="C5280 and 27DBC0 pair match copies with permanent "
                 "ownership slots; reordering or compacting a match roster needs identity-aware writeback."),
            dict(id="week_events", detail="Native acceptance, cancellation, played/simulated completion, "
                 "IR, dated cutdown and trade events do not call the dormant rule kernel."),
        ])


def save_ownership_assessment(payload):
    """Validate a bounded raw SAVEGAME.DAT and report ownership without edits.

    Raw bytes cannot authenticate EXTRA. Existing codecs validate framing,
    overflow CRC, career identity and active/reserve/IR ownership instead.
    No zero scan, pointer gap or reserve index is offered as ledger storage.
    """
    from . import nfl2k5_my_career_save as career
    from . import nfl2k5_roster_arena as arena
    from .nfl2k5_save_rost import decode
    from .nfl2k5_franchise_save import FranchiseSave
    _require(isinstance(payload, (bytes, bytearray)) and len(payload) in career.BASE_SIZES + career.SIZES,
             "unsupported franchise container length")
    native = career.native_size(payload)
    save = FranchiseSave(payload)
    squads = save._validate_ownership()
    if native != len(payload):
        career.read(payload)  # Include identity, not only the footer checksum.
    document = decode(payload)
    auxiliary = struct.unpack_from("<I", payload, 0x2e8)[0]
    limit = (arena.ARENA_SIZE - arena.BLOCK_OFFSET - arena.BLOCK_SIZE
             if document.overflow is not None else document.layout.arena_size)
    _require(auxiliary <= limit, "native auxiliary tail overlaps owned reserve storage")
    contract = persistence_contract()
    return dict(experimental=True, runtime_witnessed=False, runtime_enforced=False,
                changed_bytes=0, signature_verified=False,
                save_sha256=hashlib.sha256(payload).hexdigest(), save_bytes=len(payload),
                native_bytes=native, career_footer_present=native != len(payload),
                arena_version=document.layout.version, arena_bytes=document.layout.arena_size,
                native_auxiliary_bytes=auxiliary,
                primary_players=save.player_table[0],
                reserve_epoch=document.overflow.epoch if document.overflow is not None else None,
                reserve_counts={str(t): len(players) for t, players in sorted(squads.items()) if t < TEAMS},
                native_ledger_bytes_owned=0, persistence=contract)


def runtime_assessment(payload):
    """Read-only byte evidence. Pin drift refuses rather than recycling old findings."""
    from .nfl2k5_cave_oracle import XbeImage
    from . import nfl2k5_xbe_space as space
    space.layout(payload)
    kernel_status = status(payload)
    _require(kernel_status != "foreign", "foreign franchise kernel")
    image = XbeImage(payload)
    for name, va, size, digest in RUNTIME_PINS:
        _require(hashlib.sha256(image.read(va, size)).hexdigest() == digest, f"foreign runtime evidence: {name}")
    contract = persistence_contract()
    return dict(experimental=True, runtime_witnessed=False, runtime_enforced=False, changed_bytes=0,
                kernel_status=kernel_status, persistence=contract,
                blockers=[b["detail"] for b in contract["blockers"]] + [
                          "2D09EC zero-extends IR index and overwrites the serialized upper halfword",
                          "Native dated cutdown and all trade acceptance guards remain unmodified"],
                pins=[dict(name=n, va=hex(v), size=s, sha256=h) for n, v, s, h in RUNTIME_PINS])


@dataclass(frozen=True)
class IRRecord:
    player: int = EMPTY
    entry_games: int = 0
    flags: int = 0
    expiry: int = 0
    entry_day: int = 0

    def pack(self):
        return struct.pack("<HBBHH", self.player, self.entry_games, self.flags, self.expiry, self.entry_day)


class RuleState:
    """4096-byte pointer-free counter schema, shared with the bounded x86 kernel.

    This is an explicitly exported HOST companion, never appended to SAVEGAME.DAT.
    Primary indices are valid only with the exact save digest in its envelope.
    Native transport, clear/retirement hooks and pool migration remain shipping gates.
    """

    def __init__(self, raw):
        self.raw = bytearray(raw)
        self.validate()

    @classmethod
    def new(cls, season, players, epoch=0):
        _integer(season, 2000, 2255, "season")
        _integer(players, 1, MAX_PLAYERS, "player count")
        _integer(epoch, 0, 0xffffffff, "pool epoch")
        raw = bytearray(DATA_SIZE)
        raw[:8] = MAGIC
        struct.pack_into("<HHI", raw, 8, season, players, epoch)
        for team in range(TEAMS):
            struct.pack_into("<HBBBBHHHHH", raw, TEAM_BASE + team * TEAM_SIZE,
                             EMPTY, 0, 0, 0, 0, EMPTY, EMPTY, EMPTY, 0, 0)
        for i in range(TEAMS * IR_SLOTS):
            raw[IR_BASE + i * 8:IR_BASE + i * 8 + 8] = IRRecord().pack()
        return cls(raw)

    @property
    def season(self):
        return struct.unpack_from("<H", self.raw, 8)[0]

    @property
    def players(self):
        return struct.unpack_from("<H", self.raw, 10)[0]

    def copy(self):
        return RuleState(self.raw)

    def team(self, team):
        _integer(team, 0, TEAMS - 1, "team")
        return list(struct.unpack_from("<HBBBBHHHHH", self.raw, TEAM_BASE + team * TEAM_SIZE))

    def _team(self, team, values):
        struct.pack_into("<HBBBBHHHHH", self.raw, TEAM_BASE + team * TEAM_SIZE, *values)

    def history(self, player):
        _integer(player, 0, self.players - 1, "player")
        v = (self.raw[HISTORY_BASE + player // 2] >> ((player & 1) * 4)) & 15
        return v & 3, v >> 2

    def _history(self, player, elevations, returns):
        off, shift = HISTORY_BASE + player // 2, (player & 1) * 4
        self.raw[off] = (self.raw[off] & ~(15 << shift)) | ((elevations | returns << 2) << shift)

    def ir(self, team):
        self.team(team)
        return [IRRecord(*struct.unpack_from("<HBBHH", self.raw, IR_BASE + (team * IR_SLOTS + i) * 8))
                for i in range(IR_SLOTS)]

    def _ir(self, team, entries):
        entries = list(entries)
        _require(len(entries) <= IR_SLOTS, "IR capacity exceeded")
        entries += [IRRecord()] * (IR_SLOTS - len(entries))
        off = IR_BASE + team * IR_SLOTS * 8
        self.raw[off:off + IR_SLOTS * 8] = b"".join(e.pack() for e in entries)

    def _find(self, team, player):
        self.history(player)
        entries = self.ir(team)
        for i, entry in enumerate(entries):
            if entry.player == player:
                return entries, i, entry
        raise Franchise2026Error("player is not on this team's IR")

    def validate(self):
        _require(len(self.raw) == DATA_SIZE and self.raw[:8] == MAGIC, "foreign rule counter schema")
        _integer(self.season, 2000, 2255, "season")
        _integer(self.players, 1, MAX_PLAYERS, "player count")
        _require(not any(self.raw[16:32]) and not any(self.raw[USED_END:]), "nonzero reserved counter bytes")
        seen, pending = set(), set()
        for p in range(MAX_PLAYERS):
            value = self.raw[HISTORY_BASE + p // 2] >> ((p & 1) * 4) & 15
            _require(value >> 2 <= 2 and (p < self.players or value == 0), "invalid player history")
        for t in range(TEAMS):
            last, games, used, cut, qualified, game, a, b, day, reserved = self.team(t)
            _require(games <= 31 and qualified in (0, 1) and used <= 8 + 2 * qualified
                     and cut <= min(2, used) and day <= 511 and reserved == 0,
                     "invalid team counters")
            _require((last == EMPTY) == (games == 0), "game count has no completion identity")
            _require(game == EMPTY or last == EMPTY or game > last, "stale pending game")
            _require((game != EMPTY or (a == b == EMPTY)) and (a != EMPTY or b == EMPTY), "invalid pending elevations")
            for player in (a, b):
                if player != EMPTY:
                    self.history(player)
                    _require(player not in pending, "duplicate pending elevation")
                    pending.add(player)
            empty = False
            charged_entries = cutdown_entries = 0
            for entry in self.ir(t):
                if entry.player == EMPTY:
                    _require(entry == IRRecord(), "foreign empty IR record")
                    empty = True
                    continue
                _require(not empty and entry.player not in seen, "IR is not uniquely packed")
                self.history(entry.player)
                _require(entry.entry_games <= games and entry.entry_day <= day and entry.flags < 64,
                         "invalid IR entry")
                f = entry.flags
                charged_entries += bool(f & CHARGED)
                cutdown_entries += bool(f & CUTDOWN)
                _require(not (f & (CHARGED | PRACTICE | CUTDOWN) and not f & ELIGIBLE), "invalid IR eligibility flags")
                _require(not (f & PRACTICE) or (f & CHARGED and not f & EXPIRED and entry.expiry > 0), "invalid practice window")
                _require(not f & CUTDOWN or f & CHARGED, "uncharged cutdown designation")
                _require(not f & LEGACY or f == LEGACY, "legacy IR cannot be eligible")
                _require(entry.expiry <= 532 and (f & (PRACTICE | EXPIRED) or entry.expiry == 0), "invalid expiry")
                seen.add(entry.player)
            _require(charged_entries <= used and cutdown_entries <= cut, "IR designation spending is missing")
        _require(not seen & pending, "IR player has pending elevation")
        return True

    def enter_ir(self, team, player, day, *, post_cutdown=True, cutdown=False, legacy=False):
        _require(all(type(v) is bool for v in (post_cutdown, cutdown, legacy)), "IR origin must be explicit")
        _integer(day, 0, 511, "day")
        self.history(player)
        values = self.team(team)
        _require(values[5] == EMPTY, "finish or cancel game preparation before an IR move")
        _require(day >= values[8], "date moved backwards")
        _require(not any(e.player == player for t in range(TEAMS) for e in self.ir(t)), "player already on IR")
        _require(not any(player in self.team(t)[6:8] for t in range(TEAMS)), "player has pending elevation")
        entries = [e for e in self.ir(team) if e.player != EMPTY]
        _require(len(entries) < IR_SLOTS, "five-slot IR storage is full")
        _require(not legacy or not cutdown, "legacy IR cannot consume a cutdown designation")
        flags = LEGACY if legacy else ELIGIBLE if post_cutdown or cutdown else 0
        if cutdown:
            _require(values[3] < 2 and values[2] < 8, "cutdown return budget exhausted")
            _require(self.history(player)[1] < 2, "player return limit reached")
            flags |= CHARGED | CUTDOWN
            values[2] += 1
            values[3] += 1
        values[8] = day
        self._ir(team, entries + [IRRecord(player, values[1], flags, 0, day)])
        self._team(team, values)

    def qualify(self, team):
        values = self.team(team)
        values[4] = 1
        self._team(team, values)

    def commit_game(self, team, key, day, elevations=(), *, postseason=False):
        """Charge accepted elevations, including a selected but inactive call-up."""
        _integer(key, 0, EMPTY - 1, "game key")
        _integer(day, 0, 511, "day")
        _require(type(postseason) is bool, "postseason must be boolean")
        elevations = tuple(elevations)
        _require(len(elevations) <= 2 and len(set(elevations)) == len(elevations), "at most two unique elevations")
        v = self.team(team)
        padded = list(elevations) + [EMPTY] * (2 - len(elevations))
        if v[5] == key:
            _require(v[6:8] == padded and day == v[8], "different preparation for an accepted game")
            return False
        _require(v[5] == EMPTY and (v[0] == EMPTY or key > v[0]), "pending or already completed game")
        _require(day >= v[8] and (not postseason or v[4]), "invalid game date or postseason qualification")
        for p in elevations:
            used, _returns = self.history(p)
            _require(postseason or used < 3, "fourth regular elevation requires permanent promotion")
            _require(not any(e.player == p for t in range(TEAMS) for e in self.ir(t)), "IR player cannot elevate")
            _require(not any(p in self.team(t)[6:8] for t in range(TEAMS)), "player already elevated elsewhere")
        for p in elevations:
            used, returns = self.history(p)
            self._history(p, used if postseason else used + 1, returns)
        v[5:8], v[8] = [key] + padded, day
        self._team(team, v)
        return True

    def complete_game(self, team, key, day, *, phase=8):
        _integer(key, 0, EMPTY - 1, "game key")
        _integer(day, 0, 511, "day")
        _require(phase in (8, 9), "only a completed regular/postseason game counts")
        v = self.team(team)
        if v[0] == key:
            _require(day == v[8], "replayed result date differs")
            return False
        _require((v[0] == EMPTY or key > v[0]) and v[1] < 31 and day >= v[8], "invalid game completion order")
        _require(v[5] in (EMPTY, key), "result does not match pending game")
        _require(phase != 9 or v[4], "team is not a postseason qualifier")
        v[0], v[1], v[5:8], v[8] = key, v[1] + 1, [EMPTY] * 3, day
        self._team(team, v)
        self.advance_day(team, day)
        return True

    def advance_day(self, team, day):
        _integer(day, 0, 511, "day")
        v = self.team(team)
        _require(day >= v[8], "date moved backwards")
        entries = self.ir(team)
        for i, e in enumerate(entries):
            if e.flags & PRACTICE and day >= e.expiry:
                entries[i] = IRRecord(e.player, e.entry_games, (e.flags & ~PRACTICE) | EXPIRED, e.expiry, e.entry_day)
        self._ir(team, entries)
        v[8] = day
        self._team(team, v)

    def designate(self, team, player, day, *, postseason=False):
        _integer(day, 0, 511, "day")
        _require(type(postseason) is bool, "postseason must be boolean")
        entries, i, e = self._find(team, player)
        v = self.team(team)
        _require(day >= v[8] and (not postseason or v[4]), "invalid practice date or postseason qualification")
        _require(e.flags & ELIGIBLE and not e.flags & (EXPIRED | LEGACY), "season-ending IR")
        _require(v[1] - e.entry_games >= 4 and self.history(player)[1] < 2, "four missed games and fewer than two returns required")
        if e.flags & PRACTICE:
            _require(day < e.expiry, "practice window expired")
            return False
        if not e.flags & CHARGED:
            _require(v[2] < (10 if postseason else 8), "team return designation budget exhausted")
            v[2] += 1
        entries[i] = IRRecord(player, e.entry_games, e.flags | CHARGED | PRACTICE, day + 21, e.entry_day)
        v[8] = day
        self._ir(team, entries)
        self._team(team, v)
        return True

    def activate(self, team, player, day, *, medically_clear, active_count, reserve_count,
                 reserve_limit=12, combined_limit=65):
        _integer(day, 0, 511, "day")
        _integer(active_count, 0, 65, "active count")
        _require((reserve_limit, combined_limit) in ((12, 65), (12, 70), (16, 70), (17, 70)), "invalid roster limits")
        _integer(reserve_count, 0, reserve_limit, "reserve count")
        entries, i, e = self._find(team, player)
        v = self.team(team)
        _require(v[5] == EMPTY and day >= v[8], "pending game or date moved backwards")
        _require(e.flags & PRACTICE and day < e.expiry and v[1] - e.entry_games >= 4, "IR return window is not open")
        _require(medically_clear is True, "medical clearance required")
        _require(active_count < 53 and active_count + reserve_count < combined_limit, "no legal active roster slot")
        used, returns = self.history(player)
        _require(returns < 2, "player return limit reached")
        self._history(player, used, returns + 1)
        self._ir(team, [x for j, x in enumerate(entries) if j != i and x.player != EMPTY])
        v[8] = day
        self._team(team, v)

    def rollover(self, season):
        _integer(season, 2000, 2255, "season")
        if season == self.season:
            return False
        _require(season == self.season + 1, "rollover must advance exactly one season")
        _require(all(self.team(t)[5] == EMPTY and all(e.player == EMPTY for e in self.ir(t)) for t in range(TEAMS)),
                 "restore IR ownership and finish pending games before rollover")
        self.raw = self.new(season, self.players, struct.unpack_from("<I", self.raw, 12)[0]).raw
        return True

    def remap(self, mapping, new_count):
        """Explicit complete pool migration; deleted live IR/call-ups refuse."""
        _integer(new_count, 1, MAX_PLAYERS, "new player count")
        _require(len(mapping) == self.players, "pool remap must cover every old slot")
        targets = [x for x in mapping if x is not None]
        for x in targets:
            _integer(x, 0, new_count - 1, "mapped player")
        _require(len(set(targets)) == len(targets), "pool remap is not injective")
        candidate = self.copy()
        candidate.raw[HISTORY_BASE:IR_BASE] = bytes(IR_BASE - HISTORY_BASE)
        struct.pack_into("<H", candidate.raw, 10, new_count)
        epoch = struct.unpack_from("<I", self.raw, 12)[0]
        _require(epoch < 0xffffffff, "pool epoch exhausted")
        struct.pack_into("<I", candidate.raw, 12, epoch + 1)
        for old, new in enumerate(mapping):
            if new is not None:
                candidate._history(new, *self.history(old))
        for t in range(TEAMS):
            entries = []
            for e in self.ir(t):
                if e.player != EMPTY:
                    _require(mapping[e.player] is not None, "cannot delete an IR owner")
                    entries.append(IRRecord(mapping[e.player], e.entry_games, e.flags, e.expiry, e.entry_day))
            candidate._ir(t, entries)
            v = self.team(t)
            for i in (6, 7):
                if v[i] != EMPTY:
                    _require(mapping[v[i]] is not None, "cannot delete an elevated owner")
                    v[i] = mapping[v[i]]
            candidate._team(t, v)
        candidate.validate()
        self.raw = candidate.raw


@dataclass(frozen=True)
class Candidate:
    player: int
    position: int
    rank: int = 0
    rating: int = 50
    available: bool = True


def select_game_day(active, reserves=(), elevations=(), previous=(), special=(), *, reserve_limit=12, combined_limit=65):
    """R1: deterministic identity list; no ownership, injury or contract writes.

    First cover primary positions and requested special roles, secure eight OL
    where available, retain legal previous choices, then fill by depth/rating.
    Explicitly refuse a usable-player shortage before the retail auto-heal path.
    """
    active, reserves, elevations = tuple(active), tuple(reserves), tuple(elevations)
    previous, special = tuple(previous), tuple(special)
    _require((reserve_limit, combined_limit) in ((12, 65), (12, 70), (16, 70), (17, 70)), "invalid roster limits")
    _require(len(active) <= 53 and len(reserves) <= reserve_limit and len(active) + len(reserves) <= combined_limit, "ownership capacity exceeded")
    _require(len(elevations) <= 2 and len(set(elevations)) == len(elevations), "at most two unique elevations")
    all_players = active + reserves
    _require(len({p.player for p in all_players}) == len(all_players), "duplicate player ownership")
    for p in all_players:
        _integer(p.player, 0, MAX_PLAYERS - 1, "player")
        _integer(p.position, 0, 16, "primary position")
        _integer(p.rank, 0, 7, "depth rank")
        _integer(p.rating, 0, 255, "rating")
        _require(type(p.available) is bool, "availability must be explicit")
    _require(len(special) <= 6 and len(previous) <= 48, "too many prior choices or special roles")
    reserve_ids = {p.player for p in reserves}
    _require(set(elevations) <= reserve_ids, "only this team's reserves may elevate")
    union = active + tuple(p for p in reserves if p.player in elevations)
    eligible = sorted((p for p in union if p.available), key=lambda p: (p.rank, -p.rating, p.player))
    by_id = {p.player: p for p in eligible}
    _require(len(eligible) >= 11, "fewer than eleven available players; repair the roster before launch")
    picked = []

    def take(player):
        if player in by_id and player not in picked:
            picked.append(player)

    for position in range(17):
        matches = [p for p in eligible if p.position == position]
        for p in matches[:2 if position == 0 else 1]:
            take(p.player)
    for player in special:
        take(player)
    for p in [p for p in eligible if p.position in OL][:8]:
        take(p.player)
    limit = 48 if sum(p.position in OL for p in eligible) >= 8 else 47
    _require(len(picked) <= limit, "required special roles exceed the active limit")
    for player in tuple(previous) + tuple(p.player for p in eligible):
        if len(picked) == limit:
            break
        take(player)
    _require(len(picked) <= 47 or sum(by_id[p].position in OL for p in picked) >= 8, "48 requires eight OL")
    return tuple(picked)


def cutdown_due(date, minute_et=18 * 60):
    """R4 frozen 2026 date; minute precision in ET, with no invented week index."""
    _integer(minute_et, 0, 1439, "ET minute")
    _require(type(date) is dt.date and date.year == 2026, "cutdown policy is for the 2026 calendar")
    return (date, minute_et) >= (dt.date(2026, 8, 30), 18 * 60)


def trades_open(date, minute_et=16 * 60, *, deadline_enabled=True):
    _integer(minute_et, 0, 1439, "ET minute")
    _require(type(date) is dt.date and date.year == 2026 and type(deadline_enabled) is bool, "invalid 2026 deadline context")
    return not deadline_enabled or (date, minute_et) < (dt.date(2026, 11, 10), 16 * 60)


def export_counters(save, state):
    state.validate()
    _validate_save_state(save, state)
    raw = bytes(state.raw)
    return COMPANION_MAGIC + hashlib.sha256(save.to_bytes()).digest() + hashlib.sha256(raw).digest() + raw


def import_counters(save, companion):
    _require(len(companion) == COMPANION_SIZE and companion[:8] == COMPANION_MAGIC, "foreign host companion")
    _require(companion[8:40] == hashlib.sha256(save.to_bytes()).digest(), "counter companion belongs to a different save")
    _require(companion[40:72] == hashlib.sha256(companion[72:]).digest(), "counter companion integrity failure")
    state = RuleState(companion[72:])
    _validate_save_state(save, state)
    return state


def _validate_save_state(save, state):
    save._validate_ownership()
    _require(save.player_table[0] == state.players, "counter primary pool differs")
    _require(save.header.display_year == state.season, "counter season differs from save")
    native = {(e.team, e.player_index) for e in save.injured_reserve()}
    ledger = {(t, e.player) for t in range(TEAMS) for e in state.ir(t) if e.player != EMPTY}
    _require(native == ledger, "counter IR ownership differs from save")


class HostSession:
    """Explicit host-only transactions; never silently resume an altered native save."""

    def __init__(self, save, companion=None):
        self.save = save
        if companion is None:
            self.state = RuleState.new(save.header.display_year, save.player_table[0])
            for entry in save.injured_reserve():
                self.state.enter_ir(entry.team, entry.player_index, 0, legacy=True)
        else:
            self.state = import_counters(save, companion)
        self._digest = hashlib.sha256(save.to_bytes()).digest()
        _validate_save_state(save, self.state)

    def _fresh(self):
        _require(hashlib.sha256(self.save.to_bytes()).digest() == self._digest,
                 "save changed outside this host session; explicit counter migration required")

    def export(self):
        self._fresh()
        return export_counters(self.save, self.state)

    def _transaction(self, operation):
        from .nfl2k5_franchise_save import FranchiseSave
        self._fresh()
        candidate = FranchiseSave(self.save.to_bytes(), base_year=self.save.base_year)
        state = self.state.copy()
        result = operation(candidate, state)
        state.validate()
        _validate_save_state(candidate, state)
        self.save.buffer, self.save._roster = candidate.buffer, None
        self.state = state
        self._digest = hashlib.sha256(self.save.to_bytes()).digest()
        return result

    def place_ir(self, team, player, day, *, post_cutdown=True, cutdown=False):
        def operation(save, state):
            # The old explicit Finn workflow uses EE. Modern eligibility does not.
            state.enter_ir(team, player, day, post_cutdown=post_cutdown, cutdown=cutdown)
            save.place_on_injured_reserve(team, player, legacy_marker=False)
        return self._transaction(operation)

    def _roster_limits(self, team):
        block = self.save.roster.overflow
        return dict(reserve_limit=block.limit(team), combined_limit=70) if block is not None and team < 32 else {}

    def activate_ir(self, team, player, day):
        def operation(save, state):
            count, _ = save._team_slots(team)
            reserves = save._validate_ownership()[team]
            off = save.player_offset(player)
            clear = not struct.unpack_from("<I", save.buffer, off + 0x24)[0] & 0x70000000
            state.activate(team, player, day, medically_clear=clear, active_count=count, reserve_count=len(reserves),
                           **self._roster_limits(team))
            save.activate_from_injured_reserve(team, player, clear_legacy_marker=False)
        return self._transaction(operation)

    def advance(self, team, day, *, game_key=None, phase=8):
        return self._transaction(lambda _save, state: state.advance_day(team, day) if game_key is None
                                 else state.complete_game(team, game_key, day, phase=phase))

    def designate(self, team, player, day, *, postseason=False):
        return self._transaction(lambda _save, state: state.designate(team, player, day, postseason=postseason))

    def qualify(self, team):
        return self._transaction(lambda _save, state: state.qualify(team))

    def prepare(self, team, key, day, *, elevations=()):
        self._fresh()
        squads = self.save._validate_ownership()
        active = self.save.team_player_indices(team)
        reserves = list(squads[team])
        def candidate(p):
            off = self.save.player_offset(p)
            buf = self.save.buffer
            return Candidate(p, buf[off + 0x35], (struct.unpack_from("<H", buf, off + 0x28)[0] >> 10) & 7,
                             max(buf[off + 0x36:off + 0x52]),
                             bool(buf[off + 8] & 4) and not bool(buf[off + 8] & 0x18)
                             and not bool(struct.unpack_from("<I", buf, off + 0x24)[0] & 0x70000000))
        selected = select_game_day([candidate(p) for p in active], [candidate(p) for p in reserves], elevations,
                                   **self._roster_limits(team))
        phase = self.save.header.stage
        _require(phase in (8, 9), "game preparation is only for regular/postseason games")
        trial = self.state.copy()
        trial.commit_game(team, key, day, elevations, postseason=phase == 9)
        # Immutable proposal bound to both save and counter state. Cancel discards it.
        return PreparedGame(team, key, day, tuple(elevations), selected, phase,
                            self._digest, hashlib.sha256(self.state.raw).digest())

    def accept(self, preparation):
        _require(type(preparation) is PreparedGame, "invalid game preparation")
        self._fresh()
        _require(preparation.save_digest == self._digest, "stale game preparation")
        current = self.prepare(preparation.team, preparation.key, preparation.day,
                               elevations=preparation.elevations)
        _require(current.selected == preparation.selected and current.phase == preparation.phase,
                 "game selection changed before acceptance")
        v = self.state.team(preparation.team)
        _require(preparation.state_digest == hashlib.sha256(self.state.raw).digest() or v[5] == preparation.key,
                 "counters changed before acceptance")
        return self._transaction(lambda _save, state: state.commit_game(preparation.team, preparation.key,
                                 preparation.day, preparation.elevations, postseason=preparation.phase == 9))


@dataclass(frozen=True)
class PreparedGame:
    team: int
    key: int
    day: int
    elevations: tuple[int, ...]
    selected: tuple[int, ...]
    phase: int
    save_digest: bytes
    state_digest: bytes


def code_for(code_va, data_va):
    from . import nfl2k5_franchise_2026_code as assembly
    symbols = {"code": code_va, "workspace": data_va}
    blob = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        value += symbols[symbol] + struct.unpack_from("<I", blob, offset)[0]
        if kind == 2:
            value -= code_va + offset
        struct.pack_into("<I", blob, offset, value & 0xffffffff)
    _require(len(blob) <= CODE_SIZE, "franchise kernel exceeds code budget")
    return bytes(blob).ljust(CODE_SIZE, b"\xcc"), {k: code_va + v for k, v in assembly.LABELS.items()}


def _inspect(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    layout = space.layout(payload)
    allocations = {a["kind"]: a for a in layout["allocations"] if a["owner"] == OWNER}
    if not allocations:
        return "retail", allocations
    _require(set(allocations) == {"code", "data"}, "incomplete franchise kernel allocation")
    for kind, size in (("code", CODE_SIZE), ("data", DATA_SIZE)):
        _require((allocations[kind]["size"], allocations[kind]["align"]) == (size, 16), "foreign franchise allocation shape")
    image = XbeImage(payload)
    code = image.read(allocations["code"]["va"], CODE_SIZE)
    _require(image.read(allocations["data"]["va"], DATA_SIZE) == bytes(DATA_SIZE), "nonzero on-disc runtime state")
    expected = code_for(allocations["code"]["va"], allocations["data"]["va"])[0]
    _require(code in (b"\xcc" * CODE_SIZE, expected), "foreign franchise kernel")
    return ("applied" if code == expected else "retail"), allocations


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    """Install a dormant proof kernel. This does NOT enable franchise rules.

    The Build flag must first call require_runtime_ready(), which currently
    refuses. Keeping allocation installation separate permits both safety gates
    to exercise real machine code without shipping an unsafe staging detour.
    """
    from . import nfl2k5_xbe_space as space
    try:
        state, allocations = _inspect(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError) as exc:
        raise Franchise2026Error(f"foreign/mixed franchise kernel input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False,
                  runtime_enforced=False, native_hooks=[], save_growth=0, code_capacity=CODE_SIZE,
                  runtime_state_bytes=DATA_SIZE, host_companion_bytes=COMPANION_SIZE)
    if state == "applied":
        return payload, dict(common, already_applied=True, changed_bytes=0, file_growth=0, edits=[])
    allocation_receipt = {}
    if space.status(payload) == "retail":
        payload_allocated, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        allocations = _inspect(payload_allocated)[1]
    else:
        _require(bool(allocations), "include franchise requests in the initial allocator union")
        payload_allocated = payload
    blob, labels = code_for(allocations["code"]["va"], allocations["data"]["va"])
    result, receipt = space.install_code(payload_allocated, OWNER, blob)
    _require(status(result) == "applied", "franchise kernel postcondition failed")
    return result, dict(common, already_applied=False, allocation=allocation_receipt, code_install=receipt,
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                        file_growth=len(result) - len(payload), before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest(),
                        labels={k: hex(v) for k, v in labels.items()}, reservations=space.reservations(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--self-check", action="store_true")
    action.add_argument("--assess-xbe")
    action.add_argument("--assess-save", help="read-only raw SAVEGAME.DAT ownership assessment")
    args = parser.parse_args()
    if args.assess_save:
        from pathlib import Path
        from . import nfl2k5_my_career_save as career
        with Path(args.assess_save).open("rb") as reader:
            payload = reader.read(max(career.SIZES) + 1)
        print(json.dumps(save_ownership_assessment(payload), indent=2))
        return
    if args.assess_xbe:
        from pathlib import Path
        with Path(args.assess_xbe).open("rb") as reader:
            payload = reader.read(12_300_289)
        _require(len(payload) <= 12_300_288, "XBE exceeds the owned allocator extent")
        print(json.dumps(runtime_assessment(payload), indent=2))
        return
    state = RuleState.new(2026, 2479)
    state.enter_ir(0, 1, 0)
    for k in range(4):
        state.complete_game(0, k, k * 7 + 7)
    state.designate(0, 1, 28)
    state.activate(0, 1, 28, medically_clear=True, active_count=52, reserve_count=12)
    state.validate()
    code_for(0x14da000, 0x14f2000)
    print(json.dumps(dict(experimental=True, runtime_enforced=False, self_check="passed",
                         requests=REQUESTS, persistence=persistence_contract())))


if __name__ == "__main__":
    main()
