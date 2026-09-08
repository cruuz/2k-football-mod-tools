"""Senior Bowl preparation and native component proofs. EXPERIMENTAL / UNWITNESSED.

This revision deliberately installs NO retail hook. The native save transport,
complete simulator write set and menu bridge are unresolved. ``apply`` installs
sealed, dormant component code; it does not enable an in-game event. ``simulate``
refuses. Host event files are development/project artifacts, never Xbox saves.
See docs/mod_editor/senior_bowl.md for the binary contract and remaining work.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import zlib

from . import nfl2k5_roster_records as rr
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_senior_bowl"
CODE_SIZE, DATA_SIZE = 4096, 65536
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 4096))
NATIVE_EVENT_AVAILABLE = False
RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: Franchise has no Senior Bowl. Patch: "
    "Prepares two rookie squads and an event record. In-game simulation, saving "
    "and menus are not available yet. This page previews squads and kit choices."
)
NATIVE_BLOCKER = (
    "Senior Bowl simulation is unavailable: native save transport, simulator "
    "stat isolation and menu routing have not been proved. No game was simulated."
)
EVENT_SIZE, HEADER_SIZE, MAX_CLASS, MAX_PRIMARY = 16384, 256, 512, 4096
CLASS_OFFSET = HEADER_SIZE
ROWS_OFFSET, ROW_SIZE, PARTICIPANTS = 2304, 80, 106
USED_END = ROWS_OFFSET + PARTICIPANTS * ROW_SIZE
STAGING_OFFSET, TEAMS_OFFSET, PLAYERS_OFFSET = 0x4000, 0x9000, 0x9400
COACHES_OFFSET = 0xB800
SCHEMES = rr.POSITION_SCHEMES
STATES = ("empty", "pending", "running", "complete", "skipped")
QUOTAS = (3, 1, 1, 6, 5, 2, 2, 3, 2, 3, 4, 3, 2, 4, 4, 4, 4)
assert sum(QUOTAS) == 53
PLAYER_STATS = (
    "pass_attempts", "completions", "pass_yards", "pass_td", "pass_int",
    "rush_attempts", "rush_yards", "rush_td", "targets", "receptions",
    "receiving_yards", "receiving_td", "tackles", "assists", "half_sacks",
    "interceptions", "interception_yards", "passes_defended", "forced_fumbles",
    "fumbles_recovered", "fg_attempts", "fg_made", "fg_long", "xp_attempts",
    "xp_made", "punts", "punt_yards", "punt_long", "inside_20", "kick_returns",
    "kick_return_yards", "kick_return_long", "kick_return_td", "punt_returns",
    "punt_return_yards", "punt_return_td",
)
TEAM_STATS = ("score", "first_downs", "pass_yards", "rush_yards", "total_yards",
              "turnovers", "penalties", "penalty_yards", "possession_seconds",
              "third_down_attempts", "third_down_made", "sacks_allowed")
SIGNED_STATS = {"pass_yards", "rush_yards", "receiving_yards", "interception_yards",
                "kick_return_yards", "punt_return_yards"}
PROJECT_SCHEMA = "nfl2k5_senior_bowl_project/v1"
CAVES = RUNTIME_GLOBALS = ()


class SeniorBowlError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise SeniorBowlError(message)


def _integer(value, low, high, label):
    _require(type(value) is int and low <= value <= high, f"invalid {label}")
    return value


@dataclass(frozen=True)
class Kit:
    bank: int
    side: str
    era: int = 0

    def validate(self):
        # Only these four packages have independently checked inventory evidence.
        _require(type(self.bank) is int and self.bank in (50, 51), "supported kit banks are 50 and 51")
        _require(self.side in ("A", "H"), "kit side must be A or H")
        _require(type(self.era) is int and self.era == 0, "only current kit era 0 is verified")
        return self

    @property
    def package(self):
        self.validate()
        return f"{self.bank}{self.side}{self.era}.IFF"


@dataclass(frozen=True)
class Settings:
    scheme: str = "retail"
    away: Kit = Kit(50, "A")
    home: Kit = Kit(51, "H")

    def validate(self):
        _require(self.scheme in SCHEMES, "unknown position scheme")
        self.away.validate()
        self.home.validate()
        _require(self.away != self.home, "choose different away and home kits")
        return self

    def to_dict(self):
        self.validate()
        return {"scheme": self.scheme, "away": vars(self.away), "home": vars(self.home)}

    @classmethod
    def from_dict(cls, value):
        _require(isinstance(value, dict) and set(value) == {"scheme", "away", "home"}, "invalid Senior Bowl settings")
        kits = []
        for key in ("away", "home"):
            row = value[key]
            _require(isinstance(row, dict) and set(row) == {"bank", "side", "era"}, "invalid kit settings")
            kits.append(Kit(**row).validate())
        return cls(value["scheme"], *kits).validate()


def quotas(scheme):
    _require(scheme in SCHEMES, "unknown position scheme")
    result = list(QUOTAS)
    if scheme == "one_pool":
        result[11] += result[10]
        result[10] = 0
    return tuple(result)


@dataclass(frozen=True)
class Prospect:
    index: int
    position: int
    flags: int
    owned: bool = False
    name: str = ""
    identity: bytes = b""

    def validate(self):
        _integer(self.index, 0, MAX_PRIMARY - 1, "primary player index")
        _integer(self.position, 0, 16, "position code")
        _integer(self.flags, 0, 255, "player flags")
        _require(type(self.owned) is bool, "invalid player ownership")
        _require(isinstance(self.name, str) and len(self.name) <= 256, "invalid player name")
        _require(type(self.identity) is bytes and len(self.identity) <= 1024, "invalid prospect identity")
        return self

    @property
    def eligible(self):
        # Allocated primary + current prospect, not drafted, not owned elsewhere.
        return self.flags & 0x34 == 0x14 and not self.owned


def current_class(players, scheme="retail"):
    rows = tuple(players)
    _require(len(rows) <= MAX_PRIMARY, "primary pool exceeds 4096 records")
    _require(scheme in SCHEMES, "unknown position scheme")
    seen = set()
    result = []
    for p in rows:
        p.validate()
        _require(p.index not in seen, "duplicate primary index")
        seen.add(p.index)
        if p.eligible:
            _require(not (scheme == "one_pool" and p.position == 10),
                     "class contains retired OLB code 10; reclassify before selection")
            result.append(p)
    result.sort(key=lambda p: p.index)
    _require(len(result) <= MAX_CLASS, "class exceeds the 512-prospect event capacity")
    return tuple(result)


def class_fingerprint(players, scheme="retail"):
    rows = current_class(players, scheme)
    digest = hashlib.sha256(b"Senior Bowl class v1\0" + scheme.encode("ascii"))
    for p in rows:
        name = p.name.encode("utf-8")
        digest.update(struct.pack("<HBBHH", p.index, p.position, p.flags, len(name), len(p.identity)))
        digest.update(name)
        digest.update(p.identity)
    return digest.digest()


def select_squads(players, *, seed=1, scheme="retail"):
    _integer(seed, 0, 0xFFFFFFFF, "seed")
    rows = current_class(players, scheme)
    counts = Counter(p.position for p in rows)
    required = quotas(scheme)
    shortages = [f"{rr.SCHEME_POSITION_NAMES[scheme][pos]}: need {2*n}, found {counts[pos]}"
                 for pos, n in enumerate(required) if counts[pos] < 2*n]
    _require(not shortages, "not enough prospects for two complete squads; " + "; ".join(shortages))
    squads = [[], []]
    # Stable index order, alternating teams; rotate the start within each position
    # by the saved seed so nonparticipants can change without re-generating anyone.
    for pos, n in enumerate(required):
        if not n:
            continue
        pool = [p for p in rows if p.position == pos]
        offset = ((seed ^ (pos * 0x9E3779B9)) & 0xFFFFFFFF) % len(pool)
        for i in range(2*n):
            side = (i + ((seed ^ pos) & 1)) & 1
            squads[side].append(pool[(offset + i) % len(pool)])
    return tuple(tuple(s) for s in squads)


def prospects_from_document(document):
    """Read all current primary records and all club/reserve/FA/IR ownership.

    Do not use the historic first-year index window or RosterDocument's cached
    membership labels, which intentionally tolerate some malformed lists.
    """
    from . import nfl2k5_practice_squad as ps
    from . import nfl2k5_franchise_save as fs
    body = document.body
    primary = [p for p in document.players if p.pool == "primary"]
    _require(len(primary) <= MAX_PRIMARY, "primary pool exceeds 4096 records")
    offsets = {p.offset: p.index for p in primary}
    occupied = set()
    for team in document.teams:
        _require(team.clean_parse, "malformed active team list")
        raw = bytes(body[team.offset:team.offset + rr.TEAM_SIZE])
        # Validate the entire live prefix, including reserves, never the opaque tail.
        active = raw[ps.ACTIVE_COUNT]
        version, reserves, marker = raw[ps.VERSION_OFFSET], raw[ps.COUNT], raw[ps.MARKER_OFFSET]
        _require((version, reserves, marker) == (0, 0, 0) or
                 (version == ps.VERSION and marker == ps.MARKER and reserves <= 12), "foreign reserve metadata")
        _require(active + reserves <= 65, "team exceeds 65 slots")
        owned_here = []
        for slot in range(active + reserves):
            target = document.rel(team.offset + slot * 4)
            _require(target in offsets, "team references a missing primary player")
            owned_here.append(offsets[target])
        _require(len(owned_here) == len(set(owned_here)), "duplicate player within a team")
        # All-star aliases do not grant eligibility to a prospect who appears there.
        occupied.update(owned_here)
    ob = document.obj_base
    count = document.u32(ob + rr.FREE_AGENT_COUNT_FIELD)
    table = document.rel(ob + rr.FREE_AGENT_LIST_FIELD)
    _require(count <= rr.FREE_AGENT_LIST_CAP and
             (not count or table is not None and 0 <= table <= len(body) - count * 4), "invalid free-agent list")
    for i in range(count):
        target = document.rel(table + i*4)
        _require(target in offsets, "free-agent list references a missing primary player")
        occupied.add(offsets[target])
    if document.base == rr.SAVE_BLOCK_OFFSET:
        _require(len(body) in (fs.FRANCHISE_SAVE_SIZE, fs.FRANCHISE_SAVE_SIZE + 4096), "unsupported franchise save size")
        growth = len(body) - fs.FRANCHISE_SAVE_SIZE
        for i in range(32 * 5):
            index = struct.unpack_from("<H", body, fs.FRONT_OFFICE_BLOCK + growth + fs.F_INJURED_RESERVE + 4*i)[0]
            _require(index == 0xFFFF or index < len(primary), "invalid injured-reserve index")
            if index != 0xFFFF:
                occupied.add(index)
    result = []
    for p in primary:
        raw = bytes(body[p.offset:p.offset + 84])
        # No pointers in the fingerprint. Name, college, birth and appearance
        # identity survive relocation; class ratings/flags are included too.
        identity = raw[8:0x2C] + raw[0x34:0x54] + p.college.encode("utf-8")
        result.append(Prospect(p.index, raw[0x35], raw[8], p.index in occupied, p.display, identity))
    return tuple(result)


def read_franchise(path, *, scheme="retail"):
    """Bounded, signed SAVEGAME.DAT input; no recursive container/pack reads."""
    from . import nfl2k5_franchise_save as fs
    from . import nfl2k5_my_career_save as career
    source = Path(path).expanduser().resolve(strict=True)
    if source.is_dir():
        source = source / "SAVEGAME.DAT"
    size = source.stat().st_size
    _require(size in career.BASE_SIZES + career.SIZES, "unsupported franchise save size")
    payload = _read_exact(source, size)
    signature = _read_exact(source.with_name("EXTRA"), 20)
    _require(rr.verify_extra(payload, signature), "EXTRA does not match SAVEGAME.DAT")
    block = career.read(payload) if size in career.SIZES else None
    if block is not None:
        payload = payload[:-career.SIZE]
    document = rr.RosterDocument(payload, base=rr.SAVE_BLOCK_OFFSET, scheme=scheme, source=str(source))
    document.mycareer = block
    players = prospects_from_document(document)
    return document, players


def _read_exact(path, size):
    with Path(path).open("rb") as stream:
        _require(os.fstat(stream.fileno()).st_size == size, f"expected exactly {size} bytes in {Path(path).name}")
        value = stream.read(size + 1)
    _require(len(value) == size, "file changed or was truncated during read")
    return value


@dataclass(frozen=True)
class PlayerLine:
    index: int
    position: int
    side: int
    stats: tuple[int, ...] = (0,) * len(PLAYER_STATS)


@dataclass(frozen=True)
class Event:
    year: int
    seed: int
    franchise_id: bytes
    class_hash: bytes
    settings: Settings = Settings()
    state: str = "pending"
    class_rows: tuple[tuple[int, int], ...] = ()
    lines: tuple[PlayerLine, ...] = ()
    quarters: tuple[int, ...] = (0,) * 10
    totals: tuple[tuple[int, ...], ...] = ((0,) * 12,) * 2

    def validate(self):
        _integer(self.year, 0, 127, "season index")
        _integer(self.seed, 0, 0xFFFFFFFF, "seed")
        _require(type(self.franchise_id) is bytes and len(self.franchise_id) == 16 and any(self.franchise_id), "invalid franchise identity")
        _require(type(self.class_hash) is bytes and len(self.class_hash) == 32 and any(self.class_hash), "invalid class fingerprint")
        self.settings.validate()
        _require(self.state in STATES[1:], "invalid event state")
        _require(type(self.class_rows) is tuple and len(self.class_rows) <= MAX_CLASS, "invalid class map")
        seen = set()
        previous = -1
        for index, pos in self.class_rows:
            _integer(index, 0, MAX_PRIMARY - 1, "class index")
            _integer(pos, 0, 16, "class position")
            _require(index > previous, "class indices must be unique and sorted")
            _require(not (self.settings.scheme == "one_pool" and pos == 10), "retired OLB in class map")
            seen.add(index)
            previous = index
        _require(len(self.lines) in (0, PARTICIPANTS), "event needs exactly 106 participant lines")
        _require(bool(self.lines) or self.state == "skipped", "pending/running/complete event needs squads")
        mapping = dict(self.class_rows)
        participants = set()
        for row in self.lines:
            _integer(row.index, 0, MAX_PRIMARY - 1, "participant index")
            _integer(row.position, 0, 16, "participant position")
            _integer(row.side, 0, 1, "participant side")
            _require(mapping.get(row.index) == row.position and row.index not in participants, "duplicate/missing participant identity")
            participants.add(row.index)
            _require(len(row.stats) == len(PLAYER_STATS), "invalid player stat width")
            for key, value in zip(PLAYER_STATS, row.stats):
                _integer(value, -32768 if key in SIGNED_STATS else 0, 32767, key)
            s = dict(zip(PLAYER_STATS, row.stats))
            for made, attempts in (("completions", "pass_attempts"), ("receptions", "targets"), ("fg_made", "fg_attempts"), ("xp_made", "xp_attempts")):
                _require(s[made] <= s[attempts], f"{made} exceeds {attempts}")
        if self.lines:
            for side in range(2):
                counts = Counter(row.position for row in self.lines if row.side == side)
                _require(tuple(counts[p] for p in range(17)) == quotas(self.settings.scheme), "incomplete positional squad")
            # Require the saved seed to select exactly this mapping, in order.
            pool = [Prospect(i, p, 0x14) for i, p in self.class_rows]
            expected = [(p.index, p.position, side) for side, team in enumerate(select_squads(pool, seed=self.seed, scheme=self.settings.scheme)) for p in team]
            _require([(r.index, r.position, r.side) for r in self.lines] == expected, "saved squads differ from the class and seed")
        _require(len(self.quarters) == 10 and len(self.totals) == 2, "invalid score dimensions")
        for n in self.quarters:
            _integer(n, 0, 999, "quarter score")
        for side, total in enumerate(self.totals):
            _require(len(total) == 12, "invalid team stat width")
            for key, n in zip(TEAM_STATS, total):
                _integer(n, -32768 if key in {"pass_yards", "rush_yards", "total_yards"} else 0, 100000, key)
            _require(total[0] == sum(self.quarters[side*5:side*5+5]), "score does not match quarters")
            _require(total[4] == total[2] + total[3], "team yards do not add up")
            _require(total[10] <= total[9], "third downs made exceed attempts")
        if self.state != "complete":
            _require(not any(self.quarters) and not any(n for t in self.totals for n in t)
                     and not any(n for row in self.lines for n in row.stats), "unfinished event cannot contain results")
        return self

    def to_bytes(self):
        self.validate()
        blob = bytearray(EVENT_SIZE)
        struct.pack_into("<4sHHIII III", blob, 0, b"SBN1", 1, HEADER_SIZE, EVENT_SIZE, 0,
                         STATES.index(self.state), self.year, self.seed, SCHEMES.index(self.settings.scheme))
        blob[32:48], blob[48:80] = self.franchise_id, self.class_hash
        struct.pack_into("<HH", blob, 80, len(self.class_rows), len(self.lines))
        for off, kit in ((84, self.settings.away), (87, self.settings.home)):
            blob[off:off+3] = bytes((kit.bank, ord(kit.side), kit.era))
        struct.pack_into("<10H", blob, 100, *self.quarters)
        struct.pack_into("<24i", blob, 120, *(n for t in self.totals for n in t))
        for i, (index, pos) in enumerate(self.class_rows):
            struct.pack_into("<HBB", blob, CLASS_OFFSET + i*4, index, pos, 0)
        for i, row in enumerate(self.lines):
            struct.pack_into("<HBB36h", blob, ROWS_OFFSET + i*ROW_SIZE, row.index, row.position, row.side, *row.stats)
        struct.pack_into("<I", blob, 12, zlib.crc32(blob[16:]))
        return bytes(blob)

    @classmethod
    def from_bytes(cls, blob, *, franchise_id=None, class_hash=None, year=None, recover=True):
        _require(type(blob) is bytes and len(blob) == EVENT_SIZE, "invalid event length")
        magic, version, header, length, crc = struct.unpack_from("<4sHHII", blob)
        _require((magic, version, header, length) == (b"SBN1", 1, HEADER_SIZE, EVENT_SIZE), "unsupported event schema")
        _require(crc == zlib.crc32(blob[16:]), "event checksum mismatch")
        state, saved_year, seed, scheme = struct.unpack_from("<4I", blob, 16)
        _require(1 <= state <= 4 and scheme < 3, "invalid event enum")
        count, lines = struct.unpack_from("<HH", blob, 80)
        _require(count <= MAX_CLASS and lines in (0, PARTICIPANTS), "invalid event counts")
        kits = [Kit(blob[off], chr(blob[off+1]), blob[off+2]) for off in (84, 87)]
        rows = tuple(struct.unpack_from("<HB", blob, CLASS_OFFSET+i*4) for i in range(count))
        result = []
        for i in range(lines):
            index, pos, side, *stats = struct.unpack_from("<HBB36h", blob, ROWS_OFFSET+i*ROW_SIZE)
            result.append(PlayerLine(index, pos, side, tuple(stats)))
        total = struct.unpack_from("<24i", blob, 120)
        event = cls(saved_year, seed, blob[32:48], blob[48:80], Settings(SCHEMES[scheme], *kits),
                    STATES[state], rows, tuple(result), struct.unpack_from("<10H", blob, 100), (total[:12], total[12:]))
        # Re-encoding also requires all reserved/unused bytes to be zero.
        _require(event.to_bytes() == blob, "noncanonical event data or reserved bytes")
        _require(franchise_id is None or event.franchise_id == franchise_id, "event belongs to another franchise")
        _require(class_hash is None or event.class_hash == class_hash, "event belongs to another draft class")
        _require(year is None or event.year == year, "event belongs to another season")
        return replace(event, state="pending") if recover and event.state == "running" else event

    def scouting_line(self, index):
        """Separate event line; no draft-stock/ratings/CPU-score mutation."""
        self.validate()
        if self.state != "complete":
            return None
        row = next((r for r in self.lines if r.index == index), None)
        if row is None:
            return None
        return {"label": "Senior Bowl", "side": "Away" if row.side == 0 else "Home",
                "player_index": index, **dict(zip(PLAYER_STATS, row.stats))}


def prepare_event(players, *, year, franchise_id, seed=1, settings=Settings(), stage=4, days=4, untouched_hours=True):
    _integer(stage, 1, 9, "franchise stage")
    _integer(days, 0, 4, "combine days")
    _require(type(untouched_hours) is bool, "invalid combine-hours state")
    settings.validate()
    rows = current_class(players, settings.scheme)
    fingerprint = class_fingerprint(rows, settings.scheme)
    skipped = stage > 4 or stage == 4 and (days < 4 or not untouched_hours)
    teams = () if skipped else select_squads(rows, seed=seed, scheme=settings.scheme)
    lines = tuple(PlayerLine(p.index, p.position, side) for side, team in enumerate(teams) for p in team)
    return Event(year, seed, franchise_id, fingerprint, settings, "skipped" if skipped else "pending",
                 tuple((p.index, p.position) for p in rows), lines).validate()


def stage_preamble(event, *, year, stage, days=4, untouched_hours=True, franchise_id=None, class_hash=None):
    """Policy component only: True holds stage 4. It never ticks weeks or days.

    A terminal record persists through drafting and changing class flags for the
    rest of its year. A stale pending record refuses until deliberately rebuilt.
    """
    event.validate()
    _integer(year, 0, 127, "season index")
    _integer(stage, 1, 9, "franchise stage")
    _integer(days, 0, 4, "combine days")
    _require(type(untouched_hours) is bool, "invalid combine-hours state")
    _require(year == event.year, "new season requires a new event record")
    _require(franchise_id is None or franchise_id == event.franchise_id, "event belongs to another franchise")
    if event.state in ("complete", "skipped"):
        return event, False
    _require(class_hash is None or class_hash == event.class_hash, "pending class changed")
    if stage > 4 or stage == 4 and (days < 4 or not untouched_hours):
        return replace(event, state="skipped"), False
    event = replace(event, state="pending") if event.state == "running" else event
    return event, stage == 4


def skip_event(event):
    event.validate()
    _require(event.state == "pending", "only a pending event can be skipped")
    return replace(event, state="skipped")


def simulate(event, *args, **kwargs):
    event.validate()
    raise SeniorBowlError(NATIVE_BLOCKER)


def atomic_write(path, content):
    """Small project/event artifacts only; close descriptors before replace."""
    _require(type(content) is bytes and len(content) <= 131072, "artifact exceeds 128 KiB")
    target = Path(path).expanduser().resolve()
    _require(target.name.upper() not in {"SAVEGAME.DAT", "EXTRA", "DEFAULT.XBE"}, "use a separate Senior Bowl project/event file")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="sb-", suffix=".tmp", dir=target.parent)
    temporary = Path(name).resolve()
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def save_event(path, event):
    blob = event.to_bytes()
    atomic_write(path, blob)
    return {"schema": "SBN1", "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
            "native_save": False, "state": event.state, "year": event.year}


def load_event(path, **expected):
    return Event.from_bytes(_read_exact(path, EVENT_SIZE), **expected)


def project_bytes(settings, seed, source="", event=None):
    settings.validate()
    _integer(seed, 0, 0xFFFFFFFF, "seed")
    _require(type(source) is str and len(source) <= 8192, "invalid source path")
    if event is not None:
        event.validate()
        _require(event.settings == settings and event.seed == seed, "project choices differ from the saved event")
    value = {"schema": PROJECT_SCHEMA, "settings": settings.to_dict(), "seed": seed,
             "source": source, "event": None if event is None else event.to_bytes().hex()}
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def read_project(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(131073)
    _require(len(raw) <= 131072, "project exceeds 128 KiB")
    def unique(items):
        out = {}
        for key, value in items:
            _require(key not in out, "duplicate project key")
            out[key] = value
        return out
    value = json.loads(raw, object_pairs_hook=unique)
    _require(type(value) is dict and set(value) == {"schema", "settings", "seed", "source", "event"}
             and value["schema"] == PROJECT_SCHEMA, "unsupported Senior Bowl project")
    settings = Settings.from_dict(value["settings"])
    encoded = value["event"]
    _require(encoded is None or type(encoded) is str and len(encoded) == EVENT_SIZE*2, "invalid embedded event")
    event = None if encoded is None else Event.from_bytes(bytes.fromhex(encoded))
    project_bytes(settings, value["seed"], value["source"], event)  # semantic preflight
    return settings, value["seed"], value["source"], event


# These are evidence/dependency guards, NOT patched hook sites. All guards are
# literal USA retail pins. A different serializer or sim core refuses install.
GUARDS = (
    (0xC5310, 0x90, "b85edf1f475e2aa5f464792b06c50e31da9389d883a16b48cb4643e15eb2f8c9"),
    (0xC5800, 0x45, "95cc2eb589c286ec312600ac858a7237bf1dc6d7e3926082d0da972c20632259"),
    (0x10B940, 0xB0, "6804a5bf2a2e3c46fdcb5db7f1c393b4e34b30782d4bebf2acd0f91033d44cfe"),
)


def code_for(code_va, data_va):
    from . import nfl2k5_senior_bowl_code as assembly
    symbols = {"code": code_va, "state_data": data_va}
    blob = bytearray(assembly.CODE)
    for off, kind, symbol, addend in assembly.RELOCATIONS:
        value = symbols[symbol] + addend + struct.unpack_from("<I", blob, off)[0]
        if kind == 2:
            value -= code_va + off
        struct.pack_into("<I", blob, off, value & 0xFFFFFFFF)
    _require(len(blob) <= CODE_SIZE, "Senior Bowl component exceeds code budget")
    return bytes(blob) + b"\xcc" * (CODE_SIZE-len(blob)), {k: code_va+v for k, v in assembly.LABELS.items()}


def allocations(payload):
    found = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    if found:
        _require(set(found) == {"code", "data"}, "incomplete Senior Bowl request union")
        for _, kind, size, align in REQUESTS:
            _require((found[kind]["size"], found[kind]["align"]) == (size, align), "foreign Senior Bowl allocation")
    return found


def _inspect(payload):
    found = allocations(payload)  # allocator validates all section digests/seals
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        _require(hashlib.sha256(image.read(va, size)).hexdigest() == digest, f"foreign Senior Bowl dependency at {va:#x}")
    if not found:
        return "retail", found
    _require(image.read(found["data"]["va"], DATA_SIZE) == bytes(DATA_SIZE), "nonzero initial Senior Bowl state")
    got = image.read(found["code"]["va"], CODE_SIZE)
    expected = code_for(found["code"]["va"], found["data"]["va"])[0]
    _require(got in (b"\xcc"*CODE_SIZE, expected), "foreign/mixed Senior Bowl component code")
    return ("applied" if got == expected else "retail"), found


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, KeyError, TypeError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    """Install dormant proof components; NEVER claim this enables the native MVP."""
    state, found = _inspect(payload)
    common = {"owner": OWNER, "experimental": True, "runtime_witnessed": False,
              "native_event_available": False, "retail_hooks": 0, "save_growth": 0,
              "tier": "preparation-and-dormant-components", "blocker": NATIVE_BLOCKER,
              "code_capacity": CODE_SIZE, "runtime_state_bytes": DATA_SIZE, "event_bytes": EVENT_SIZE}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0, "edits": []}
    if space.status(payload) == "retail":
        result, receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        _require(bool(found), "reserve Senior Bowl in the complete owner union first")
        result, receipt = payload, {}
    found = allocations(result)
    code, labels = code_for(found["code"]["va"], found["data"]["va"])
    result, install = space.install_code(result, OWNER, code)
    _require(status(result) == "applied", "Senior Bowl component postcondition failed")
    return result, {**common, "already_applied": False, "allocation": receipt, "code_install": install,
                    "edits": [], "labels": {k: hex(v) for k, v in labels.items()},
                    "reservations": space.reservations(result),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result)-len(payload),
                    "file_growth": len(result)-len(payload),
                    "before_sha256": hashlib.sha256(payload).hexdigest(), "after_sha256": hashlib.sha256(result).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capability", help="show availability and limits")
    check = sub.add_parser("check-event", help="validate a development event file")
    check.add_argument("path", type=Path)
    preview = sub.add_parser("preview", help="read a signed franchise save and preview squads")
    preview.add_argument("path", type=Path)
    preview.add_argument("--scheme", choices=SCHEMES, default="retail")
    preview.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    try:
        if args.command == "capability":
            result = {"owner": OWNER, "native_event_available": False, "experimental": True,
                      "runtime_witnessed": False, "reason": NATIVE_BLOCKER, "requests": REQUESTS,
                      "default_kits": [Settings().away.package, Settings().home.package]}
        elif args.command == "check-event":
            event = load_event(args.path)
            result = {"state": event.state, "year": event.year, "class_count": len(event.class_rows),
                      "participants": len(event.lines), "native_save": False}
        else:
            _doc, players = read_franchise(args.path, scheme=args.scheme)
            teams = select_squads(players, seed=args.seed, scheme=args.scheme)
            result = {"native_event_available": False, "class_count": len(current_class(players, args.scheme)),
                      "class_sha256": class_fingerprint(players, args.scheme).hex(),
                      "squads": [[{"index": p.index, "name": p.name,
                                   "position": rr.SCHEME_POSITION_NAMES[args.scheme][p.position]} for p in t] for t in teams]}
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, struct.error) as exc:
        print(f"Senior Bowl: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
