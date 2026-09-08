"""EXPERIMENTAL / UNWITNESSED MyCareer draft-start reference components.

Owned separately from the parallel MyCareer mode. No XBE hook, save writer,
menu, external setup-file dependency or competing career/event codec is added.
Reservation/injection operate on copies after the final native class generator.
Temporary-team projection consumes already-fixed-up native pointers and is only
used inside the bounded instruction fixture until live launch is proved.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import struct

from . import nfl2k5_roster_records as rr
from . import nfl2k5_senior_bowl as bowl

OWNER = "nfl2k5_draft_start"
REQUESTS = ()
RUNTIME_READY = False
START_CHOICES = ("Enter the draft", "Sign as an undrafted rookie")
GENERIC_NFL_BANK = 31
GENERIC_NFL_KITS = ("31A0.IFF", "31H0.IFF")  # Existing event side 0 away / 1 home.
NATIVE_TO_EVENT_SIDES = (1, 0)  # Native side 0 home / 1 away; also its own inverse.
NATIVE_START = 0x13EE10
ADVANCE_WEEK = 0x247D40
ADVANCE_STAGE = 0x2480B0
GENERATE_CLASS = 0x2BE940
CLONE_TEAMS = 0x61730
DRAFT_PICK = 0x325B90
ROOKIE_SIGN = 0x325B50
SCOUTING_STOCK_DELTA = 0  # A scouting display is not a draft-AI score hook.


class DraftStartError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise DraftStartError(message)


def _integer(value, low, high, label):
    require(type(value) is int and low <= value <= high, f"invalid {label}")


def route(choice: str):
    require(choice in START_CHOICES, "unknown career start choice")
    if choice == START_CHOICES[1]:
        return ("create", "choose_club", "native_udfa_signing", "rookie_year_0")
    return ("create_recipe", "native_franchise_start", "simulate_year_0",
            "native_offseason_year_1", "reserve_after_final_generator",
            "senior_bowl_before_combine", "native_draft", "native_signing",
            "rookie_year_1")


@dataclass(frozen=True)
class Creation:
    first: str
    last: str
    position: int
    college: int
    ratings: tuple[tuple[str, int], ...] = ()

    def validate(self):
        _integer(self.position, 0, 16, "position")
        _integer(self.college, 0, 1023, "college")
        for name in (self.first, self.last):
            require(isinstance(name, str) and rr.validate_name(name) == name,
                    "invalid player name")
        require(type(self.ratings) is tuple, "ratings must be an immutable tuple")
        seen = set()
        for key, value in self.ratings:
            require(key in rr.RATING_BYTE_ORDER and key not in rr.STYLE_RATINGS,
                    "only ordinary rating bytes may be overridden")
            require(key not in seen, "duplicate rating")
            seen.add(key)
            _integer(value, 1, 99, "rating")
        return self

    def fingerprint(self):
        self.validate()
        return hashlib.sha256(json.dumps(
            [self.first, self.last, self.position, self.college, sorted(self.ratings)],
            ensure_ascii=True, separators=(",", ":")).encode("ascii")).digest()


@dataclass(frozen=True)
class Reservation:
    """Pointer-free reference identity; side follows the existing event's order."""
    year: int
    franchise_id: bytes
    seed: int
    scheme: str
    index: int
    position: int
    side: int
    class_hash: bytes
    recipe_hash: bytes = b""

    def validate(self):
        _integer(self.year, 0, 127, "season index")
        _integer(self.seed, 0, 0xFFFFFFFF, "seed")
        _integer(self.index, 0, bowl.MAX_PRIMARY - 1, "primary ordinal")
        _integer(self.position, 0, 16, "position")
        _integer(self.side, 0, 1, "side")
        require(self.scheme in bowl.SCHEMES, "unknown position scheme")
        require(type(self.franchise_id) is bytes and len(self.franchise_id) == 16 and
                any(self.franchise_id), "invalid franchise identity")
        require(type(self.class_hash) is bytes and len(self.class_hash) == 32,
                "invalid class fingerprint")
        require(type(self.recipe_hash) is bytes and len(self.recipe_hash) in (0, 32),
                "invalid recipe fingerprint")
        return self


def _ready(*, stage, days, untouched_hours):
    require(type(stage) is int and stage == 4 and type(days) is int and days == 4 and
            untouched_hours is True, "reserve at untouched Combine entry after the final generator")


def reserve(players, *, year, franchise_id, position, seed=1, side=0,
            scheme="retail", stage=4, days=4, untouched_hours=True):
    """Choose an already-selected ordinal, so both 53-player squads stay valid.

    Never change a class position to force inclusion: the saved seed/position
    mapping is validated by the existing Senior Bowl codec. A retired position,
    short class, owned player or late entry refuses before any mutation.
    """
    _ready(stage=stage, days=days, untouched_hours=untouched_hours)
    _integer(position, 0, 16, "position")
    _integer(side, 0, 1, "side")
    rows = bowl.current_class(players, scheme)
    squads = bowl.select_squads(rows, seed=seed, scheme=scheme)
    candidates = [p for p in squads[side] if p.position == position]
    require(bool(candidates), "requested position has no Senior Bowl slot")
    return Reservation(year, franchise_id, seed, scheme, candidates[0].index,
                       position, side, bowl.class_fingerprint(rows, scheme)).validate()


def squads_for(players, reservation):
    reservation.validate()
    rows = bowl.current_class(players, reservation.scheme)
    require(bowl.class_fingerprint(rows, reservation.scheme) == reservation.class_hash,
            "draft class changed; do not overwrite a stale ordinal")
    squads = bowl.select_squads(rows, seed=reservation.seed, scheme=reservation.scheme)
    require(any(p.index == reservation.index and p.position == reservation.position
                for p in squads[reservation.side]), "reserved player left the selected squad")
    return tuple(tuple(p.index for p in squad) for squad in squads)


def inject(document, reservation, creation, *, year, franchise_id,
           stage=4, days=4, untouched_hours=True):
    """Return (candidate document, updated reservation, receipt); never save.

    Whole-class pin, franchise/year and existing eligibility are checked before
    mutation. Repeating the same recipe with the updated reservation is a no-op.
    Calling this on a save does not install a generator guard or runtime identity
    storage. The mode owner must implement those using its existing career state.
    """
    _ready(stage=stage, days=days, untouched_hours=untouched_hours)
    reservation.validate()
    creation.validate()
    require(year == reservation.year and franchise_id == reservation.franchise_id,
            "reservation belongs to a different career or season")
    require(document.scheme == reservation.scheme and creation.position == reservation.position,
            "creation position/scheme must match the reserved slot")
    require(creation.college < len(document.colleges), "college is absent from this roster")
    before = document.to_body()
    require(len(before) <= 1024**2, "reference document exceeds 1 MiB")
    candidate = rr.RosterDocument(before, base=document.base, scheme=document.scheme,
                                  reference_year=document.reference_year, base_year=document.base_year)
    original_teams = tuple(bytes(candidate.body[t.offset:t.offset+rr.TEAM_SIZE]) for t in candidate.teams)
    original_free_agents = tuple(candidate.free_agents)
    original_squads = squads_for(bowl.prospects_from_document(candidate), reservation)
    fingerprint = creation.fingerprint()
    if reservation.recipe_hash:
        require(reservation.recipe_hash == fingerprint, "a different recipe already owns this reservation")
        return candidate, reservation, {"changed": False, "index": reservation.index,
                                         "sha256": hashlib.sha256(before).hexdigest()}
    player = candidate.by_pool("primary")[reservation.index]
    candidate.set_name(player, "first", creation.first)
    candidate.set_name(player, "last", creation.last)
    candidate.set_college(player, creation.college)
    for key, value in creation.ratings:
        player.record.set(key, value)
    after = candidate.to_body()
    candidate = rr.RosterDocument(after, base=document.base, scheme=document.scheme,
                                  reference_year=document.reference_year, base_year=document.base_year)
    players = bowl.prospects_from_document(candidate)
    updated = replace(reservation, class_hash=bowl.class_fingerprint(players, reservation.scheme),
                      recipe_hash=fingerprint)
    require(squads_for(players, updated) == original_squads, "creation changed squad selection")
    # Names may reuse/move within the owned pool. Roster membership never changes.
    require(len(after) == len(before) and
            tuple(bytes(candidate.body[t.offset:t.offset+rr.TEAM_SIZE]) for t in candidate.teams) == original_teams and
            tuple(candidate.free_agents) == original_free_agents,
            "injection changed roster geometry or membership")
    return candidate, updated, {
        "changed": before != after, "index": updated.index,
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "sha256": hashlib.sha256(after).hexdigest(),
        "changed_bytes": sum(a != b for a, b in zip(before, after)),
        "generic_kits": GENERIC_NFL_KITS, "runtime_ready": False,
        "stock_delta": SCOUTING_STOCK_DELTA,
    }


def project_native_team(template: bytes, indices: tuple[int, ...], *,
                        primary_base: int, primary_count: int) -> bytes:
    """500-byte caller-owned donor for native 0x61730, not a franchise team edit.

    The caller supplies the real NFL generic template after native pointer fixup.
    Its name/asset/coach pointers must remain alive. The native cloner copies all
    53 player records but initially aliases their history pointers; the proof
    explicitly checks the simulator's later stat rebinding. Live-game history,
    injuries, coaches and restoration still require a separate owned sandbox.
    """
    from . import nfl2k5_practice_squad as ps
    require(type(template) is bytes and len(template) == rr.TEAM_SIZE,
            "expected one fixed-up 500-byte native team")
    require(struct.unpack_from("<H", template, 0x118)[0] == GENERIC_NFL_BANK,
            "v1 requires the retail generic NFL template")
    _integer(primary_count, 106, bowl.MAX_PRIMARY, "primary count")
    _integer(primary_base, 0x10000, 0xFFFFFFFF - primary_count * rr.PLAYER_SIZE, "primary base")
    require(primary_base % 4 == 0, "unaligned primary pool")
    require(type(indices) is tuple and len(indices) == 53 and len(set(indices)) == 53,
            "temporary team requires 53 distinct primary ordinals")
    for index in indices:
        _integer(index, 0, primary_count - 1, "primary ordinal")
    require(all(template[p] == 0 for p in (ps.VERSION_OFFSET, ps.COUNT, ps.MARKER_OFFSET)),
            "generic donor contains foreign reserve metadata")
    out = bytearray(template)
    out[:65*4] = bytes(65*4)
    for slot, index in enumerate(indices):
        struct.pack_into("<I", out, slot*4, primary_base + index*rr.PLAYER_SIZE)
    out[ps.ACTIVE_COUNT] = 53
    out[0x194:0x19A] = b"\xff" * 6  # Rebuild kicker/returner selection for these prospects.
    return bytes(out)
