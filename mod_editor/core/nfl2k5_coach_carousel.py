"""Coaching carousel: CPU clubs fire and hire head coaches at Advance to offseason (job c6-carousel, beta 80).
EXPERIMENTAL.

Players asked for it (clowncollegeprofessor1 10/10 and 10/13, BigTimeEmpire 9/11, LePromisedPrince 9/06: "Coaches and
coaching carousel since it was absent"). Retail franchise never changes a head coach: its only "firing" is the Owner
Firing option, which can end the user's time with a club. Design: ``b77_session/reports/b780_r2-coach_RESEARCH.md``
section 3, Design B.

What the game does with this owner (``tools/nfl2k5_coach_carousel/runtime.c`` has the exact rules)
--------------------------------------------------------------------------------------------------
* Owner Firing (franchise options, saved with every franchise) gets three values: **Off**, **CPU Teams** (the retail
  "On" value and default: CPU clubs change coaches, the owner never fires you) and **All Teams** (CPU clubs change
  coaches and the owner can end your time with your club, as retail did).
* At Advance to offseason, after the Super Bowl notice and the retail rollover, every CPU club may change its head
  coach. The chance comes from real NFL history (nflverse games.csv, 1999-2025: 178 changes in 861 club seasons):
  the club's regular-season record, the coach's seasons with the club (first and second seasons get more patience),
  a flat 4.8% for a playoff club, times its owner's patience measured on the same history (Bengals 0.51, Ravens 0.73,
  ... Raiders 1.37, Dolphins 1.45). At most 12 changes a year; about 6 to 7 on average.
* The club hires from the hiring pool (real people: by default the 2026 defensive coordinators, with their real head
  coaching records) or, now and then, a head coach another club let go that same offseason. The new coach's name,
  picture, career numbers and ratings show on the Coach's Card, Coach Matchup and everywhere the game names coaches;
  the announcers use the generic head coach line for him. The club keeps its sideline model (colours), its play-calling
  tendencies and its playbook; its automatic 2026 CPU profile switches off because the coach changed (the game's own
  tendencies call the plays), exactly as when a coach is changed in the Studio today.
* One "COACHING CHANGES" notice for every three changes ("Raiders: Klint Kubiak out (3-14), Vic Fangio in").
* A club a user controls never changes coach here.

Where things live
-----------------
* Code: one late allocator owner (``nfl2k5_xbe_space.LATE_OWNERS``), 4,096 bytes, with the 176-byte model parameter
  block inside (``PARAMS``). No writable memory, no heap: one Advance keeps its state on the stack.
* Sites: the rollover call at 0x248632 (free on beta-79), the owner goal check's warning mark (0x2BA675, 0x2BA6BC) and
  the Owner Firing row's three callbacks plus its layout callback (.rdata 0x500C40..0x500C4C).
* The hiring pool: one checked block (magic "2K5CPOOL", ``POOL``) the Studio writes into the free tail of the roster's
  coach string region (4,278 free bytes on SOFTDRINK v0.8), so it travels inside every franchise started from that
  roster; Franchise > Upgrade writes it into an older save. A hire points the club's coach record at the pool strings;
  nothing at runtime writes a string. Without a pool (an older save, a build without the roster step) nothing changes.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import nfl2k5_coach_carousel_code as runtime
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_coach_carousel"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 4096
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Coaching carousel (experimental)"
UI_LABEL = BUILD_CAPTION
HELP_TEXT = (
    "EXPERIMENTAL. Franchise: at Advance to offseason, CPU clubs can fire their head coach and hire a new one, about "
    "6 or 7 a year, from real NFL history since 1999 (a bad record, a third season or later, an impatient owner make "
    "it likelier; a playoff club rarely changes). New coaches come from a pool of real people (the 2026 defensive "
    "coordinators) or are coaches another club let go. A notice lists every change. The game's Owner Firing option "
    "chooses: Off, CPU Teams (your club is never fired, the default) or All Teams (the owner can also end your time "
    "with your club, as the retail game did). Your clubs never change coach. A franchise started on an older build "
    "needs Franchise > Upgrade first; without it nothing changes.")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "data" / "nfl2k5_coach_carousel_2026.json"
POOL_DATA = ROOT / "data" / "nfl2k5_coach_pool_2026.json"        # c5-owners (optional; replaces the fallback pool)
SCHEMA = "nfl2k5_coach_carousel/v1"

# the game's team order (alphabetical by nickname), nflverse abbreviations
CLUBS = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARI", "LAC", "KC", "IND", "DAL", "MIA", "PHI", "ATL", "NYG",
         "JAX", "NYJ", "DET", "GB", "CAR", "NE", "LV", "LAR", "BAL", "WAS", "NO", "SEA", "PIT", "HOU", "TEN", "MIN")

# ---- the parameter block (runtime.c P_*) -------------------------------------------------------------------------
PARAM_SIZE = 176
PARAM_MAGIC = b"C6M1"
P_VERSION, P_MAXC, P_REHIRE, P_PLAYOFF, P_CURVES, P_OWNER = 4, 5, 6, 8, 12, 138
CURVE_POINTS = 21
CURVE_KEYS = ("tenure_1", "tenure_2", "tenure_3_plus")
MAX_CHANGES = 12                                               # runtime.c MAXC
OWNER_UNIT = 32

# ---- the hiring pool block ---------------------------------------------------------------------------------------
POOL_MAGIC = b"2K5CPOOL"
POOL_VERSION = 1
POOL_HEADER = 16
POOL_ENTRY = 64
MAX_POOL = 48
MAX_POOL_BYTES = 0x1000
MAX_NAME = 24
POOL_MARGIN = 256                                              # free bytes always left in the region for others
CAREER_FIELDS = ("seasons", "wins", "losses", "ties", "winning_seasons", "super_bowls", "playoff_wins",
                 "playoff_losses", "super_bowl_wins", "super_bowl_losses")
CAREER_OFFSETS = (0x1E, 0x20, 0x22, 0x24, 0x30, 0x32, 0x34, 0x36, 0x38, 0x3A)
RATINGS = ("overall", "offense", "rush_for", "pass_for", "defense", "pass_rush", "pass_coverage", "qb", "rb", "te", "wr",
           "ol", "dl", "lb", "db", "special_teams", "professionalism", "preparation", "conditioning", "motivation",
           "leadership", "discipline", "respect")
DEFAULT_RATING = 50                                            # the retail created-coach records 32 and 33
DEFAULT_PERSONALITY = 50
NO_PHOTO = 8999
KINDS = {"defensive coordinator": 1, "offensive coordinator": 2, "former head coach": 3, "assistant": 4}

OWNER_FIRING_VA = 0x00E60144
OWNER_FIRING_VALUES = ("Off", "CPU Teams", "All Teams")


class CoachCarouselError(ValueError):
    """Unsupported executable or data, a foreign or mixed installation, or a roster without room for the pool."""


def _require(condition, message):
    if not condition:
        raise CoachCarouselError(message)


# ================================================================================================= data and model
def load(path: Path | str | None = None) -> dict:
    data = json.loads(Path(path or DEFAULT_DATA).read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: Mapping) -> None:
    _require(data.get("schema") == SCHEMA, "not a coach carousel data file")
    model = data.get("model") or {}
    curves = model.get("curves") or {}
    for key in CURVE_KEYS:
        values = curves.get(key)
        _require(isinstance(values, list) and len(values) == CURVE_POINTS
                 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in values), f"curve {key} is not 21 shares")
    _require(isinstance(model.get("playoff_rate"), (int, float)) and 0 <= model["playoff_rate"] <= 1, "playoff rate")
    clubs = model.get("clubs") or {}
    _require(set(clubs) == set(CLUBS), "the owner table must name all 32 clubs")
    for club, row in clubs.items():
        _require(isinstance(row.get("owner_factor"), (int, float)) and 0.1 <= row["owner_factor"] <= 7.9,
                 f"owner factor of {club}")
    settings = data.get("settings") or {}
    _require(isinstance(settings.get("max_changes"), int) and 1 <= settings["max_changes"] <= MAX_CHANGES, "max changes")
    _require(isinstance(settings.get("rehire_percent"), int) and 0 <= settings["rehire_percent"] <= 100, "rehire percent")
    sources = data.get("sources") or []
    _require(any(s.get("sha256") for s in sources), "the model data must pin its source")


def _share(value: float) -> int:
    return max(0, min(65535, round(value * 65536)))


def pack_params(data: Mapping) -> bytes:
    """The 176-byte parameter block the native code reads (runtime.c P_*)."""

    validate(data)
    model, settings = data["model"], data["settings"]
    out = bytearray(PARAM_SIZE)
    out[0:4] = PARAM_MAGIC
    out[P_VERSION] = 1
    out[P_MAXC] = settings["max_changes"]
    out[P_REHIRE] = settings["rehire_percent"]
    struct.pack_into("<H", out, P_PLAYOFF, _share(model["playoff_rate"]))
    for row, key in enumerate(CURVE_KEYS):
        for k, value in enumerate(model["curves"][key]):
            struct.pack_into("<H", out, P_CURVES + 42 * row + 2 * k, _share(value))
    for index, club in enumerate(CLUBS):
        out[P_OWNER + index] = max(1, min(255, round(model["clubs"][club]["owner_factor"] * OWNER_UNIT)))
    return bytes(out)


def read_params(block: bytes) -> dict | None:
    """The parameter block as numbers, or None when it is not one (zero = not filled)."""

    if len(block) != PARAM_SIZE or block[:4] != PARAM_MAGIC or block[P_VERSION] != 1 or not block[P_MAXC] \
            or block[P_REHIRE] > 100:
        return None
    return dict(max_changes=block[P_MAXC], rehire_percent=block[P_REHIRE],
                playoff=struct.unpack_from("<H", block, P_PLAYOFF)[0],
                curves=[list(struct.unpack_from("<21H", block, P_CURVES + 42 * row)) for row in range(3)],
                owner=list(block[P_OWNER:P_OWNER + 32]))


def winning_share(wins: int, losses: int, ties: int) -> int:
    """Regular-season winning share in 1/1000, ties half (runtime.c Club.pct)."""

    games = wins + losses + ties
    return (2 * wins + ties) * 500 // games if games else 0


def hazard(params: bytes, *, club: int, wins: int, losses: int, ties: int, playoffs: bool, tenure: int) -> int:
    """The chance (in 1/65536) that the club changes coach: the native ``hazard`` on plain numbers. ``tenure`` is the
    coach's seasons with the club after the rollover (record +0x1C)."""

    p = read_params(params)
    _require(p is not None, "not a filled parameter block")
    if playoffs:
        base = p["playoff"]
    else:
        pct = winning_share(wins, losses, ties)
        row = 0 if tenure <= 1 else 1 if tenure == 2 else 2
        k, f = divmod(pct, 50)
        a = p["curves"][row][k]
        b = p["curves"][row][k + 1] if k < 20 else a
        step = abs(b - a) * f // 50               # C division truncates toward zero
        base = a + (step if b >= a else -step)
    base = base * p["owner"][club] // OWNER_UNIT
    return min(base, 65535)


def expected_changes(params: bytes, seasons: Sequence[Mapping]) -> float:
    """Sum of the native hazards over club seasons ({club, wins, losses, ties, playoffs, tenure})."""

    return sum(hazard(params, **{k: s[k] for k in ("club", "wins", "losses", "ties", "playoffs", "tenure")}) / 65536
               for s in seasons)


# ================================================================================================= the hiring pool
def _clean(text: str) -> str:
    text = " ".join(str(text or "").split())
    _require(text and len(text) <= MAX_NAME and "\0" not in text and text.isprintable(), f"pool name {text!r}")
    return text


def load_pool(data: Mapping | None = None, pool_path: Path | str | None = None) -> list[dict]:
    """The hiring pool: the c5-owners file when it is present (``POOL_DATA``), else the fallback in the model data.
    Every entry is a real person with a source."""

    path = Path(pool_path) if pool_path else POOL_DATA
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("pool") or raw.get("candidates") or raw.get("entries") or []
    else:
        rows = (data or load()).get("pool") or []
    pool = []
    for row in rows:
        first = row.get("first") or (row.get("name") or "").partition(" ")[0]
        last = row.get("last") or (row.get("name") or "").partition(" ")[2]
        _require(row.get("source") or row.get("sources"), f"pool entry {first} {last} has no source")
        pool.append(dict(first=_clean(first), last=_clean(last), kind=str(row.get("kind") or row.get("role") or ""),
                         weight=int(row.get("weight") or 10), photo=int(row.get("photo") or NO_PHOTO),
                         personality=int(row.get("personality") or DEFAULT_PERSONALITY),
                         career={k: int((row.get("career") or {}).get(k) or 0) for k in CAREER_FIELDS},
                         ratings={k: int((row.get("ratings") or {}).get(k) or DEFAULT_RATING) for k in RATINGS}))
    return pool


def _adler(raw: bytes) -> int:
    a, b = 1, 0
    for byte in raw:
        a = (a + byte) % 65521
        b = (b + a) % 65521
    return (b << 16) | a


def pool_block(entries: Sequence[Mapping]) -> bytes:
    """The checked pool block (runtime.c find_pool): header, 64-byte entries, then every entry's five strings (first,
    last and three empty biography lines, each its own string so every string has exactly one coach record pointing
    at it once hired)."""

    _require(0 < len(entries) <= MAX_POOL, f"a pool holds 1 to {MAX_POOL} coaches")
    names = set()
    strings = bytearray()
    table = bytearray()
    base = POOL_HEADER + POOL_ENTRY * len(entries)
    for entry in entries:
        entry = dict(entry, first=_clean(entry["first"]), last=_clean(entry["last"]))
        key = (entry["first"].casefold(), entry["last"].casefold())
        _require(key not in names, f"{entry['first']} {entry['last']} is in the pool twice")
        names.add(key)
        offsets = []
        for text in (entry["first"], entry["last"], "", "", ""):
            offsets.append(base + len(strings))
            strings += text.encode("utf-16-le") + b"\0\0"
        raw = bytearray(POOL_ENTRY)
        struct.pack_into("<5H", raw, 0, *offsets)
        struct.pack_into("<H", raw, 10, entry.get("photo", NO_PHOTO))
        raw[12] = max(1, min(255, int(entry.get("weight", 10))))
        raw[13] = KINDS.get(str(entry.get("kind", "")).casefold(), 0)
        raw[14] = max(0, min(100, int(entry.get("personality", DEFAULT_PERSONALITY))))
        career = entry.get("career") or {}
        for k, field in enumerate(CAREER_FIELDS):
            struct.pack_into("<H", raw, 16 + 2 * k, max(0, min(0xFFFF, int(career.get(field, 0)))))
        ratings = entry.get("ratings") or {}
        raw[36:59] = bytes(max(0, min(99, int(ratings.get(r, DEFAULT_RATING)))) for r in RATINGS)
        table += raw
    body = bytes(table) + bytes(strings)
    size = (POOL_HEADER + len(body) + 3) & ~3
    body = body.ljust(size - POOL_HEADER, b"\0")
    _require(size <= MAX_POOL_BYTES, "the pool block exceeds 4 KB")
    header = POOL_MAGIC + bytes((POOL_VERSION, len(entries))) + struct.pack("<H", size) + struct.pack("<I", _adler(body))
    return header + body


def read_pool_block(raw: bytes, at: int = 0) -> list[dict] | None:
    """The entries of the pool block at ``raw[at:]`` under the native checks, or None."""

    if raw[at:at + 8] != POOL_MAGIC or len(raw) < at + POOL_HEADER:
        return None
    version, count = raw[at + 8], raw[at + 9]
    size = struct.unpack_from("<H", raw, at + 10)[0]
    if (version != POOL_VERSION or not 0 < count <= MAX_POOL or size < POOL_HEADER + POOL_ENTRY * count
            or size > MAX_POOL_BYTES or size & 3 or at + size > len(raw)):
        return None
    block = raw[at:at + size]
    if _adler(block[POOL_HEADER:]) != struct.unpack_from("<I", block, 12)[0]:
        return None

    def text(offset):
        if offset & 1 or offset < POOL_HEADER + POOL_ENTRY * count or offset >= size:
            return None
        end = offset
        while end + 1 < size and block[end:end + 2] != b"\0\0":
            end += 2
        if end + 1 >= size or (end - offset) // 2 > MAX_NAME:
            return None
        return block[offset:end].decode("utf-16-le", "replace")

    entries = []
    for k in range(count):
        e = block[POOL_HEADER + POOL_ENTRY * k:POOL_HEADER + POOL_ENTRY * (k + 1)]
        offsets = struct.unpack_from("<5H", e, 0)
        texts = [text(o) for o in offsets]
        if any(t is None for t in texts):
            return None
        entries.append(dict(first=texts[0], last=texts[1], offsets=offsets, photo=struct.unpack_from("<H", e, 10)[0],
                            weight=e[12], kind=e[13], personality=e[14],
                            career=dict(zip(CAREER_FIELDS, struct.unpack_from("<10H", e, 16))),
                            ratings=dict(zip(RATINGS, e[36:59]))))
    return entries


def find_pool(arena: bytes, start: int = 0) -> tuple[int, list[dict]] | None:
    """(offset, entries) of the first valid pool block on a 4-byte step from ``start``, as the native search does
    over the arena (``start`` = the arena root, body offset 0x40)."""

    at = arena.find(POOL_MAGIC, start)
    while at >= 0:
        if (at - start) % 4 == 0:
            entries = read_pool_block(arena, at)
            if entries is not None:
                return at, entries
        at = arena.find(POOL_MAGIC, at + 1)
    return None


# ---- the coach string region of a roster body ----------------------------------------------------------------------
OBJ_OFF = 0x40
COACH_STRIDE = 0xA8
REFERENCE_DOMAINS = (                                          # tools/nfl_coach_roster_name_workflow.REFERENCE_DOMAINS
    (0x18, 0x1C, 0x1F4, (0x104, 0x108, 0x10C, 0x138, 0x13C)),  # teams
    (0x10, 0x14, 0x80, (0x00, 0x08, 0x0C, 0x10, 0x14)),        # stadiums
    (0x30, 0x34, COACH_STRIDE, (0x00, 0x04, 0x08, 0x0C, 0x10)),  # coaches
    (0x20, 0x24, 0x08, (0x00,)),                               # colleges
    (0x00, 0x04, 0x54, (0x10, 0x14)),                          # primary players
    (0x08, 0x0C, 0x54, (0x10, 0x14)),                          # secondary players
    (0x48, 0x4C, 0x08, (0x00, 0x04)),                          # team labels
    (0x50, 0x54, 0x08, (0x00, 0x04)),                          # generated names
    (0x58, 0x5C, 0x10, (0x0C,)),                               # historic descriptors
)


def _rel(body: bytes, field: int) -> int | None:
    value = struct.unpack_from("<i", body, field)[0]
    if not value:
        return None
    target = field + value - 1
    _require(0 <= target < len(body), f"pointer at {field:#x} leaves the roster")
    return target


def _utf16_end(body: bytes, at: int) -> int:
    end = at
    while end + 1 < len(body) and body[end:end + 2] != b"\0\0":
        end += 2
    _require(end + 1 < len(body), f"unterminated string at {at:#x}")
    return end + 2


def coach_region(body: bytes, root: int = OBJ_OFF) -> dict:
    """The coach strings of a ROST body: where they start, where the used part ends, and where the next roster string
    begins (the free tail is [used_end, next_string)). Any string pointer of a known table (teams, stadiums, players,
    colleges, labels, names) bounds the tail; nothing is assumed about what follows. ``root`` is the roster object's
    offset in ``body``: 0x40 in a disc ROST body (version 17/18), 0x20 in a franchise save's (version 0/1)."""

    table = _rel(body, root + 0x34)
    count = struct.unpack_from("<I", body, root + 0x30)[0]
    _require(table is not None and 0 < count <= 64, "the roster has no coach table")
    coach_strings = []
    for index in range(count):
        for field in (0x00, 0x04, 0x08, 0x0C, 0x10):
            target = _rel(body, table + index * COACH_STRIDE + field)
            _require(target is not None, f"coach {index} +0x{field:x} has no string")
            coach_strings.append((target, _utf16_end(body, target)))
    start = min(a for a, _ in coach_strings)
    used_end = max(b for _, b in coach_strings)
    pool = find_pool(body, root)
    if pool and start <= pool[0] < used_end + 0x2000:
        used_end = max(used_end, pool[0] + struct.unpack_from("<H", body, pool[0] + 10)[0])
    following = []
    for count_off, ptr_off, stride, fields in REFERENCE_DOMAINS:
        n = struct.unpack_from("<I", body, root + count_off)[0]
        base = _rel(body, root + ptr_off)
        if base is None:
            continue
        for index in range(n):
            for field in fields:
                at = base + index * stride + field
                if at + 4 > len(body):
                    continue
                target = _rel(body, at)
                if target is not None and target >= used_end:
                    following.append(target)
    next_string = min(following) if following else len(body)
    tail = body[used_end:next_string]
    return dict(start=start, used_end=used_end, next_string=next_string, free=next_string - used_end,
                tail_is_zero=not any(tail), pool_offset=pool[0] if pool else None)


def apply_body(body: bytes, data: Mapping | None = None, *, pool: Sequence[Mapping] | None = None,
               root: int = OBJ_OFF) -> tuple[bytes, dict]:
    """Write (or replace) the hiring pool in the free tail of the coach string region of a ROST body. The tail must be
    zero; the pool goes at the first 4-aligned offset after the used strings and leaves ``POOL_MARGIN`` bytes free."""

    data = data if data is not None else load()
    entries = list(pool) if pool is not None else load_pool(data)
    block = pool_block(entries)
    out = bytearray(body)
    found = find_pool(bytes(out), root)
    if found is not None:                                       # a rebuild: take the old block out first
        at = found[0]
        out[at:at + struct.unpack_from("<H", out, at + 10)[0]] = bytes(struct.unpack_from("<H", out, at + 10)[0])
    region = coach_region(bytes(out), root)
    _require(region["tail_is_zero"], "the free tail of the coach strings holds other bytes; the pool was not written")
    at = root + ((region["used_end"] - root + 3) & ~3)
    _require(at + len(block) + POOL_MARGIN <= region["next_string"],
             f"the coach string region has {region['free']} free bytes; the pool needs {len(block) + POOL_MARGIN}")
    out[at:at + len(block)] = block
    check = find_pool(bytes(out), root)
    _require(check is not None and check[0] == at and len(check[1]) == len(entries), "the pool does not read back")
    return bytes(out), dict(status="applied", pool_offset=hex(at), pool_bytes=len(block), pool_entries=len(entries),
                            region_free_before=region["free"], region_free_after=region["next_string"] - at - len(block),
                            replaced=found is not None, block_sha256=hashlib.sha256(block).hexdigest())


ROST_OUTER_INDEX = 5
RESOURCE_HEADER = 0x20


def _outer_image():
    from . import nfl2k5_team_history as team_history
    return team_history._outer_image()


def _main_roster(archive):
    entries = archive.entries
    _require(len(entries) > ROST_OUTER_INDEX, f"the archive has no outer entry {ROST_OUTER_INDEX}")
    entry = entries[ROST_OUTER_INDEX]
    raw = archive.read(entry.virtual_offset, entry.size)
    _require(len(raw) == entry.size and raw[:4] == b"ROST", "the main roster resource is foreign")
    return entry, raw[:RESOURCE_HEADER], raw[RESOURCE_HEADER:]


def read_image(path) -> list[dict] | None:
    """The pool in the main roster of the disc image (or pack folder) at ``path``, or None."""

    with _outer_image()(path) as archive:
        found = find_pool(_main_roster(archive)[2], OBJ_OFF)
    return found[1] if found else None


def apply_image(path, data: Mapping | None = None) -> dict:
    """Write the pool into the main roster of the disc image at ``path`` (a COPY), in place, with a read-back."""

    with _outer_image()(path, writable=True) as archive:
        entry, header, body = _main_roster(archive)
        new_body, receipt = apply_body(body, data)
        replacement = header + new_body
        _require(len(replacement) == entry.size, "the roster size changed")
        if new_body != body:
            count = archive.write(entry.virtual_offset, replacement)
            _require(count == len(replacement), "short write of the main roster")
            _require(archive.read(entry.virtual_offset, entry.size) == replacement, "read-back of the main roster differs")
        found = find_pool(archive.read(entry.virtual_offset, entry.size)[RESOURCE_HEADER:], OBJ_OFF)
    _require(found is not None and len(found[1]) == receipt["pool_entries"], "the pool does not read back from the disc")
    return {**receipt, "rost_outer": ROST_OUTER_INDEX, "rost_virtual_offset": hex(entry.virtual_offset),
            "rost_size": entry.size}


# ================================================================================================= the executable
SITE_STAGE = 0x00248632
SITE_GATE = 0x002BA675
SITE_MARK = 0x002BA6BC
ROW_SITES = (                                    # (label, VA, retail callback, entry)
    ("owner_firing_left", 0x00500C40, 0x001486B0, "carousel_toggle_left"),
    ("owner_firing_right", 0x00500C44, 0x001486D0, "carousel_toggle_right"),
    ("owner_firing_text", 0x00500C48, 0x00148A40, "carousel_value_text"),
    ("owner_firing_width", 0x00500C4C, 0x00148730, "carousel_widest"),
)
RETAIL_STAGE = bytes.fromhex("e809f5ffff")       # call 0x247B40
RETAIL_GATE = bytes.fromhex("8b06a804743b")      # mov eax,[esi]; test al,4; je 0x2BA6B6
RETAIL_MARK = bytes.fromhex("85c97405")          # test ecx,ecx; je 0x2BA6C5
PATCHED_MARK = bytes.fromhex("49497505")         # dec ecx; dec ecx; jne 0x2BA6C5 (the mark only at All Teams)
# Dependencies the runtime calls or reads, pinned by SHA-256 of their retail bytes (sites masked).
GUARDS = (
    ("stage 9 rollover tail", 0x0024862D, 0x0C, "7a1bd88760192910f4be291324962bb8d10fb3da3959c52aa8c119f8b4de232c"),
    ("rollover coach loop", 0x00247CA8, 0x50, "279a7629d2b8f9bf1cb7f6116be3b4989ea1a395cead2640aef7c0c892764691"),
    ("owner goal check", 0x002BA670, 0x5B, "c9f0c4c9d4ec88c8f5d32674ac0d63380e0c0c81b2bfd051abcdd7f9efaf3267"),
    ("Owner Firing row", 0x00500C28, 0x34, "f9d5c2cd7d8974a5e3ee22577d4b2c0c8978535dae4fc45928ca891cc217f2ea"),
    ("team count", 0x000C4BE0, 0x20, "a8dcd5f93c040f380e85bf8c5d13cebbeb19636178895aa7267b0abfdef9185e"),
    ("team by index", 0x000C4C50, 0x2E, "f421059ce4ea9ac33e94e9e1541b8fcbbd4c7b28da07038136d5586a526b1dcf"),
    ("user club flag tail", 0x000C4D55, 0x12, "dd4c2e1f26a2e8a313985c3247a82c965942c1f0001c7ddf606ba8483f417460"),   # its first 5 bytes are MyCareer's cpu_management hook
    ("win counter", 0x000C75A0, 0x60, "cbe4cab6a80f68a09980c88ad0abd67a8ec737a01adf3457db9b1dbfe960d094"),
    ("loss counter", 0x000C7620, 0x60, "bc10e4d0f3c0550618ceb2b1d6250e4170e1bf62b9370f59c1bc9acd57f3f68b"),
    ("tie counter", 0x000C76A0, 0x60, "4594d45858da1bc87c39e6acf7fb4ef022f162d1302509242d43b4656bd178b3"),
    ("league random", 0x00048B50, 0x80, "da450e1b2683852dc88619b35a8bd8188a471851d3641b56f35d7d88fdd32d98"),
    ("information notice", 0x0014E520, 0x19, "3546625976e5bf1c782ad583cbc3f5bf3646469daace6d13f8907e2719a5c18f"),
    ("value width", 0x000771A0, 0x43, "17b97effc87f387627d31ab33af389de09735c0ef81b8751afaa270c334cc8ed"),
)
SUPER_BOWL_ROW_VA = 0x00133A41
SUPER_BOWL_ROWS = (0x14, 0x15)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def labels(code_va: int) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def code_for(code_va: int, params: bytes) -> bytes:
    """The owned RX content: the template with its relocations applied and ``params`` in its parameter block, padded
    to CODE_SIZE with int3."""

    _require(len(params) == PARAM_SIZE, "the parameter block is 176 bytes")
    result = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        _require(symbol == "code", "unexpected carousel relocation")
        target = code_va + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    at = runtime.LABELS["carousel_params"]
    _require(result[at:at + PARAM_SIZE] == bytes(PARAM_SIZE), "the template's parameter block is not empty")
    result[at:at + PARAM_SIZE] = params
    _require(len(result) <= CODE_SIZE, "the carousel runtime exceeds its fixed budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes)."""

    at = labels(code_va)
    out = [("stage9_rollover", SITE_STAGE, RETAIL_STAGE, b"\xe8" + _rel32(SITE_STAGE + 5, at["carousel_advance"])),
           ("owner_user_gate", SITE_GATE, RETAIL_GATE, b"\xe8" + _rel32(SITE_GATE + 5, at["carousel_user_gate"]) + b"\x90"),
           ("owner_warning_mark", SITE_MARK, RETAIL_MARK, PATCHED_MARK)]
    out += [(label, va, struct.pack("<I", retail), struct.pack("<I", at[entry])) for label, va, retail, entry in ROW_SITES]
    return out


def _guard_digest(image: XbeImage, va: int, size: int, checked_sites) -> str:
    content = bytearray(image.read(va, size))
    for _label, address, before, _after in checked_sites:
        for i in range(len(before)):
            if va <= address + i < va + size:
                content[address + i - va] = before[i]
    return hashlib.sha256(content).hexdigest()


def guard_digests(payload: bytes) -> dict[str, str]:
    """The masked digests of every guarded span (used to pin GUARDS from the retail executable)."""

    image = XbeImage(payload)
    return {name: _guard_digest(image, va, size, sites(0x14DA000)) for name, va, size, _d in GUARDS}


def _check_guards(image: XbeImage, checked_sites) -> None:
    for name, va, size, digest in GUARDS:
        _require(_guard_digest(image, va, size, checked_sites) == digest, f"foreign carousel dependency: {name} ({va:#x})")
    _require(image.read(SUPER_BOWL_ROW_VA, 1)[0] in SUPER_BOWL_ROWS, "foreign Super Bowl row predicate")


def allocations(payload: bytes) -> dict[str, dict]:
    """{"code": row} of an installed allocation, {} when the owner is not allocated."""

    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and (rows[0]["size"], rows[0]["align"]) == (CODE_SIZE, 16),
             "foreign carousel allocation")
    return {"code": rows[0]}


def installed_params(payload: bytes) -> bytes | None:
    """The parameter block of an installed carousel, or None."""

    found = allocations(payload)
    if not found:
        return None
    at = found["code"]["va"] + runtime.LABELS["carousel_params"]
    return XbeImage(payload).read(at, PARAM_SIZE)


def owned_state(payload: bytes):
    """-> ("retail" | "applied", allocations | None); anything else raises."""

    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocations(payload)
    if not found:
        retail_sites = sites(0x14DA000)
        _require(rdata.status(payload, retail_sites) == "retail", "carousel sites changed without an allocation")
        _check_guards(image, retail_sites)
        return "retail", None
    code_va = found["code"]["va"]
    code = image.read(code_va, CODE_SIZE)
    edits = sites(code_va)
    if code == b"\xcc" * CODE_SIZE:
        _require(rdata.status(payload, edits) == "retail", "carousel sites changed with an empty allocation")
        _check_guards(image, edits)
        return "retail", found
    params = installed_params(payload)
    _require(read_params(params) is not None, "foreign carousel parameter block")
    _require(code == code_for(code_va, params), "foreign carousel code")
    _require(rdata.status(payload, edits) == "applied", "mixed carousel sites")
    _check_guards(image, edits)
    return "applied", found


def status(payload: bytes) -> str:
    try:
        return owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    base = allocations(payload)
    edits = sites(base["code"]["va"] if base else 0x14DA000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes, data: Mapping | None = None) -> tuple[bytes, Mapping[str, object]]:
    """Reserve (scale-out late owner), fill and patch. Idempotent; an installed carousel with other parameters refuses
    (the allocator never reconfigures filled code: rebuild from the retail dump)."""

    params = pack_params(data if data is not None else load())
    state, found = owned_state(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": len(runtime.CODE), "owner_bytes": CODE_SIZE,
              "params_sha256": hashlib.sha256(params).hexdigest()}
    before = payload
    if state == "applied":
        _require(installed_params(payload) == params, "the coaching carousel is installed with other parameters; "
                 "build from your unmodified retail dump")
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    if not found:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            _require(space.is_scaleout(payload), "the coaching carousel needs the scale-out allocator")
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocations(payload)
    _require(bool(found), "reserve the carousel allocation first")
    code_va = found["code"]["va"]
    installed, code_receipt = space.install_code(payload, OWNER, code_for(code_va, params))
    result, site_receipt = rdata.apply(installed, sites(code_va), OWNER)
    _require(status(result) == "applied", "carousel postcondition failed")
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(code_va), "changed_bytes": space.count_differing_bytes(before, result),
                    "sites": [{"label": label, "va": hex(va), "size": len(b)} for label, va, b, _a in sites(code_va)]}


def main(argv=None) -> int:
    """python3 -m mod_editor.core.nfl2k5_coach_carousel {status,apply} source.xbe [output.xbe]"""

    import argparse

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
        receipt = {"owner": OWNER, "status": status(payload), "experimental": True}
    print(json.dumps(receipt, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "BUILD_CAPTION", "HELP_TEXT", "UI_LABEL", "CoachCarouselError", "load",
           "validate", "pack_params", "read_params", "winning_share", "hazard", "expected_changes", "load_pool",
           "pool_block", "read_pool_block", "find_pool", "coach_region", "apply_body", "read_image", "apply_image",
           "code_for", "sites", "labels", "guard_digests", "allocations", "installed_params", "owned_state", "status",
           "reservations", "apply", "OWNER_FIRING_VA", "OWNER_FIRING_VALUES"]
