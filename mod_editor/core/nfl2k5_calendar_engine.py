"""EXPERIMENTAL / UNWITNESSED: bounded franchise calendar and live DOB repair.

The current schedule encodes year minus 2000. Historical/template helpers keep
retail source-year decoding. All internal date arithmetic uses full Gregorian
years and day numbers relative to 2000-01-01. No persistent data or save changes.
Install the complete allocator union before this owner. The patch coordinates
existing season/preseason/playoffs14 owners; it never allocates their padding.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import struct

from . import nfl2k5_calendar_engine_code as assembly
from . import nfl2k5_preseason as preseason
from . import nfl2k5_playoffs14 as playoffs
from . import nfl2k5_season_length as season
from . import nfl2k5_season_cap as cap
from . import nfl2k5_xbe_space as space
from . import nfl2k5_rdata_sites as rdata
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_calendar"
CODE_SIZE, RO_SIZE = 1024, 2048
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "read_only", RO_SIZE, 16))
SUPPORTED_BASE_YEARS = (2004, 2026)
UI_TEXT = (
    "Retail: Franchise dates and birth dates use a fixed century. Patch: Repairs "
    "dates, weekdays, live player birth years and season labels through index 127, "
    "with the final postseason in the following year. EXPERIMENTAL / UNWITNESSED. "
    "Natural rollovers and save reloads still need testing. History keeps its existing limits."
)
EPOCH = dt.date(2000, 1, 1)
YEAR_TABLE_OFFSET = 32
MONTH_TABLE_OFFSET = YEAR_TABLE_OFFSET + 357 * 4
FORMAT_OFFSET = MONTH_TABLE_OFFSET + 52
PLAYOFF_TABLE_OFFSET = (FORMAT_OFFSET + 10 + 15) & ~15
PLAYOFF_CODE_OFFSET = (len(assembly.CODE) + 15) & ~15
MAGIC = b"C128\x01\x00\x00\x00"
RUNTIME_GLOBALS = ()
CAVES = ()
# Source context of the shipped immutable playoff date table. Not the current season year.
POSTSEASON_SOURCE_YEAR = 2026


class CalendarEngineError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise CalendarEngineError(message)


def opening_date(year: int) -> dt.date:
    first = dt.date(year, 11, 1)
    return first + dt.timedelta(days=(3 - first.weekday()) % 7 + 21 - 77)


POSTSEASON_OFFSETS = tuple((dt.date(POSTSEASON_SOURCE_YEAR + 1, m, d)
                           - opening_date(POSTSEASON_SOURCE_YEAR)).days
                          for m, d, _h, _n in playoffs.CALENDAR_2026_14)


def read_only_for(base_year: int) -> bytes:
    _require(base_year in SUPPORTED_BASE_YEARS, "calendar starting year must be 2004 or 2026")
    blob = bytearray(MAGIC + struct.pack("<I", base_year))
    blob.extend(bytes(YEAR_TABLE_OFFSET - len(blob)))
    blob.extend(b"".join(struct.pack("<i", (dt.date(y, 1, 1) - EPOCH).days)
                         for y in range(1900, 2257)))
    for year in (2001, 2000):
        starts = [(dt.date(year, m, 1) - dt.date(year, 1, 1)).days for m in range(1, 13)]
        starts.append((dt.date(year + 1, 1, 1) - dt.date(year, 1, 1)).days)
        blob.extend(struct.pack("<13H", *starts))
    blob.extend("%04d\0".encode("utf-16le"))
    blob.extend(bytes(PLAYOFF_TABLE_OFFSET - len(blob)))
    blob.extend(playoffs.game_table_bytes())
    blob.extend(playoffs.date_table_14(playoffs.CALENDAR_2026_14))
    blob.extend(struct.pack("<13i", *POSTSEASON_OFFSETS))
    _require(len(blob) <= RO_SIZE, "calendar immutable tables exceed budget")
    return bytes(blob) + bytes(RO_SIZE - len(blob))


def code_for(code_va: int, ro_va: int, base_year: int) -> tuple[bytes, dict[str, int]]:
    read_only_for(base_year)
    symbols = {"code": code_va, "year_starts": ro_va + YEAR_TABLE_OFFSET,
               "month_starts": ro_va + MONTH_TABLE_OFFSET, "base_year": base_year,
               "mode_getter": 0xC4B80, "retail_weekday": 0x1C18B0}
    blob = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        value += symbols[symbol] + struct.unpack_from("<I", blob, offset)[0]
        if kind == 2:
            value -= code_va + offset
        struct.pack_into("<I", blob, offset, value & 0xFFFFFFFF)
    blob.extend(b"\xcc" * (PLAYOFF_CODE_OFFSET - len(blob)))
    blob.extend(playoffs.builder_bytes(redate=code_va + assembly.LABELS["redate"],
                  date_offsets=POSTSEASON_OFFSETS, code_va=code_va + PLAYOFF_CODE_OFFSET,
                  tables_va=ro_va + PLAYOFF_TABLE_OFFSET))
    _require(len(blob) <= CODE_SIZE, "calendar helper exceeds RX budget")
    return bytes(blob) + b"\xcc" * (CODE_SIZE - len(blob)), {k: code_va + v for k, v in assembly.LABELS.items()}


def _branch(va, target, size=5, opcode=0xE8):
    return bytes([opcode]) + struct.pack("<i", target - va - 5) + b"\x90" * (size - 5)


# Whole displaced instructions. The two .text entries are detours, not caves.
HOOK_PINS = (
    ("gregorian_leap", 0x1C1880, "8bc881e103000080", "leap", 0xE9),
    ("template_ordinal", 0x1C19F0, "518a410553", "legacy_ordinal", 0xE9),
    ("date_line_weekday", 0x1C1940, "e86bffffff", "display_weekday", 0xE8),
    ("current_grid_weekday", 0x8B0E7, "e894691300", "grid_weekday", 0xE8),
    ("current_weekday_accessor", 0xD22AC, "e9cff70e00", "grid_weekday", 0xE9),
    ("thanksgiving_label", 0xD2356, "e825f70e00", "grid_weekday", 0xE8),
    ("regular_weekday", 0x2BF5CA, "e8e122f0ff", "weekday", 0xE8),
    ("regular_thanksgiving", 0x2BF60E, "e81d25f0ff", "add_days", 0xE8),
    ("regular_opening", 0x2BF61C, "e88f25f0ff", "sub_days", 0xE8),
    ("regular_thursday", 0x2BF646, "e8e524f0ff", "add_days", 0xE8),
    ("regular_saturday", 0x2BF661, "e8ca24f0ff", "add_days", 0xE8),
    ("regular_sunday", 0x2BF67C, "e8af24f0ff", "add_days", 0xE8),
    ("regular_monday", 0x2BF697, "e89424f0ff", "add_days", 0xE8),
    ("contract_projection_year", 0x347714, "e897d7d7ff", "projection_year", 0xE8),
    ("cap_projection_year", 0x3663E4, "e8c7ead5ff", "projection_year", 0xE8),
)


def sites(code_va: int, ro_va: int, base_year: int):
    """Exact predecessor is the installed season owner, never guessed retail slack."""
    _, labels = code_for(code_va, ro_va, base_year)
    result = [(name, va, bytes.fromhex(before), _branch(va, labels[helper], len(bytes.fromhex(before)), op))
              for name, va, before, helper, op in HOOK_PINS]
    va = 0x2BF5BB
    before = bytes.fromhex("e8f058e0ff04") + bytes([base_year - 2000]) + bytes.fromhex("8d4c241088442412")
    after = bytes.fromhex("8d4c2410") + _branch(va + 4, labels["regular_anchor"], len(before) - 4)
    result += [("full_regular_year", va, before, after),
               ("preseason_calendar", preseason.GENERATOR_VA, preseason.generator_bytes(),
                preseason.generator_bytes(calendar=labels)),
               ("postseason_calendar", playoffs.BUILDER_VA, playoffs.builder_bytes(),
                _branch(playoffs.BUILDER_VA, code_va + PLAYOFF_CODE_OFFSET, 5, 0xE9) + playoffs.RETAIL_BUILDER[5:]),
               ("moving_birth_year", season.DOB_FORMATTER_VA, season.dob_formatter_bytes(base_year),
                season.dob_formatter_bytes(base_year, birth_year_helper=labels["birth_year"]))]
    # The shipped 2026 templates open 77 days before Thanksgiving (Sep 10),
    # with the HOF game 35 days earlier. Retail later-year generation used 84,
    # a one-week mismatch with the installed 18-week/2026 template. Keep all
    # three phases on the configured template's 77-day rule, including the
    # Thanksgiving matchup selection, swaps, and prime-time exclusions.
    result.append(("regular_opening_offset", 0x2BF613, bytes.fromhex("ba54000000"), bytes.fromhex("ba4d000000")))
    for va, before in ((0x2BF498, "be0c000000"), (0x2BF4CF, "83fe0c"),
                       (0x2BF4D4, "ba0c000000"), (0x2BF4E0, "ba0c000000"),
                       (0x2BF4F7, "be0c000000"), (0x2BF505, "ba0c000000"),
                       (0x2BF51F, "be0c000000"), (0x2BF556, "83fe0c"),
                       (0x2BF69E, "83fe0c")):
        raw = bytes.fromhex(before)
        result.append((f"thanksgiving_week_{va:x}", va, raw, raw.replace(b"\x0c", b"\x0b")))
    for name, va in (("player_history_year", 0x3204AD), ("player_history_detail_year", 0x3218A7)):
        result.append((name, va, struct.pack("<I", 2015), struct.pack("<I", base_year + 11)))
    for name, va, old in (("contract_year_format", 0x34772B, 0xEAD010),
                          ("cap_year_format", 0x3663F3, 0xEB9494)):
        result.append((name, va, struct.pack("<I", old), struct.pack("<I", ro_va + FORMAT_OFFSET)))
    return tuple(result)


def _write_sites(payload, selected, *, restore=False):
    buf = bytearray(payload)
    touched = set()
    sections = _sections(payload)
    for _name, va, before, after in selected:
        off = rdata.offset_of(payload, va)
        data = before if restore else after
        buf[off:off + len(data)] = data
        touched.update(s.index for s in sections if s.raw_offset <= off < s.raw_offset + s.raw_size)
    for s in sections:
        if s.index in touched:
            off = s.header_offset + 36
            buf[off:off + 20] = section_digest(bytes(buf), s)
    return bytes(buf), sorted(touched)


def _allocations(payload):
    layout = space.layout(payload)
    found = {a["kind"]: a for a in layout["allocations"] if a["owner"] == OWNER}
    if found:
        _require(set(found) == {"code", "read_only"}, "incomplete calendar reservation")
        for kind, size in (("code", CODE_SIZE), ("read_only", RO_SIZE)):
            _require((found[kind]["size"], found[kind]["align"]) == (size, 16), "foreign calendar allocation")
    return found


def _prerequisites(payload, base_year):
    # Direct site reader avoids recursion through the public season projections.
    sections = _sections(payload)
    states = {}
    for group in season.GROUPS:
        values = set()
        for site in season.group_sites(group, year=base_year):
            off = season._offset(payload, site.va, sections)
            got = payload[off:off + site.size]
            if site.retail == site.patched and got == site.retail:
                continue
            values.add("retail" if got == site.retail else "applied" if got == site.patched else "foreign")
        _require(values in ({"retail"}, {"applied"}), f"calendar prerequisite {group} is mixed/foreign")
        states[group] = next(iter(values))
    _require(cap.status(payload) in ("retail", "applied"), "foreign completion gate")
    return states


def _inspect(payload):
    allocations = _allocations(payload)  # validates digests and all owner seals first
    image = XbeImage(payload)
    base = struct.unpack("<I", image.read(0x247AC7, 4))[0]
    _require(base in SUPPORTED_BASE_YEARS, "unsupported calendar starting year")
    code_va = allocations["code"]["va"] if allocations else 0
    ro_va = allocations["read_only"]["va"] if allocations else 0
    selected = sites(code_va, ro_va, base)
    installed = False
    if allocations:
        code = image.read(code_va, CODE_SIZE)
        ro = image.read(ro_va, RO_SIZE)
        installed = code != b"\xcc" * CODE_SIZE or ro != bytes(RO_SIZE)
        if installed:
            _require(code == code_for(code_va, ro_va, base)[0] and ro == read_only_for(base),
                     "foreign/incomplete calendar code or tables")
    if installed:
        _require(all(image.read(va, len(after)) == after for _, va, _, after in selected),
                 "mixed/foreign calendar hooks")
        original, _ = _write_sites(payload, selected, restore=True)
        _require(set(_prerequisites(original, base).values()) == {"applied"}, "calendar dependencies missing")
        _require(cap.status(payload) == "applied", "calendar completion gate missing")
        _guards(original, base)
        return "applied", base, allocations, selected
    states = _prerequisites(payload, base)
    # Accept each complete existing season group; never accept a half-upgraded calendar.
    owned = {"preseason_calendar": "preseason", "postseason_calendar": "playoffs_14", "moving_birth_year": "year"}
    for name, va, before, _ in selected:
        if name in owned and states[owned[name]] == "retail":
            continue
        if name == "full_regular_year" and states["year"] == "retail":
            before = before[:6] + b"\x04" + before[7:]
        _require(image.read(va, len(before)) == before, f"foreign calendar site: {name}")
    _guards(payload, base)
    return "retail", base, allocations, selected


def status(payload: bytes) -> str:
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def predecessor(payload: bytes) -> bytes:
    """Validated overlay projection for the existing season owner's status readers.

    Returns identical input unless a complete calendar overlay is installed.
    Does not uninstall or mutate an image or remove its allocator seals.
    """
    state, _base, _a, selected = _inspect(payload)
    return _write_sites(payload, selected, restore=True)[0] if state == "applied" else payload


def apply(payload: bytes) -> tuple[bytes, dict[str, object]]:
    state, base, allocations, _ = _inspect(payload)  # all refusals precede any mutation
    common = {"owner": OWNER, "experimental": True, "witnessed": False, "runtime_witnessed": False,
              "calendar_repaired": True, "base_year": base, "max_season_index": 127,
              "terminal_index": 128, "persistent_data_bytes": 0, "runtime_state_bytes": 0,
              "schedule_year_encoding": "year - 2000", "template_context": "original source year",
              "helper_code_bytes": len(assembly.CODE), "code_budget": CODE_SIZE, "read_only_budget": RO_SIZE,
              "used_code_bytes": PLAYOFF_CODE_OFFSET + len(playoffs.builder_bytes(
                  redate=1, code_va=1, tables_va=1, date_offsets=POSTSEASON_OFFSETS)),
              "used_read_only_bytes": PLAYOFF_TABLE_OFFSET + 260,
              "opening_rule": "Thursday 77 days before Thanksgiving; preseason starts 35 days earlier"}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0, "edits": [], "sections_repinned": []}
    if space.status(payload) == "retail":
        result, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        _require(bool(allocations), "reserve calendar in the complete owner union before allocation")
        result, allocation_receipt = payload, {}
    prerequisites = _prerequisites(result, base)
    groups = tuple(group for group, value in prerequisites.items() if value == "retail")
    if groups:
        result, dependency_receipt = season.apply(result, groups=groups, year=base)
    else:
        dependency_receipt = {}
    result, cap_receipt = cap.apply(result)
    allocations = _allocations(result)
    code_va, ro_va = allocations["code"]["va"], allocations["read_only"]["va"]
    code, _ = code_for(code_va, ro_va, base)
    selected = sites(code_va, ro_va, base)
    image = XbeImage(result)
    _require(all(image.read(va, len(before)) == before for _, va, before, _ in selected), "calendar predecessor changed")
    result, _ = space.install_code(result, OWNER, code)
    result, _ = space.install_read_only(result, OWNER, read_only_for(base))
    result, touched = _write_sites(result, selected)
    _require(status(result) == "applied", "calendar postcondition failed")
    edits = [{"label": name, "va": hex(va), "file_offset": hex(rdata.offset_of(result, va)),
              "before": before.hex(), "after": after.hex(), "bytes": len(after)} for name, va, before, after in selected]
    return result, {**common, "already_applied": False, "edits": edits, "sections_repinned": touched,
                    "allocation": allocation_receipt, "season_dependencies": dependency_receipt,
                    "completion_gate": cap_receipt, "reservations": space.reservations(result),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                    "file_growth": len(result) - len(payload),
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


# Pinned retail context, including all displaced continuations.
GUARDS = (
    (0xc4b80, 6, "ea571d62a509b72a0a8afeb1ce87e10afb9b23fe864a4f34521e3a467052a60a"),
    (0x1c1880, 48, "b38d122107ed94fc8f4326493b7313d7476203a94c434ae7f15d62dded5b4d66"),
    (0x1c18b0, 132, "4edbddc1cf188bea10e13e3d51382014978cdf06eee4f83232ac58061a474f6a"),
    (0x1c19f0, 144, "93f09253e12abcc2c32695c03014d812b2ffad3cd8f2900d5dd0a1862dedaec5"),
    (0x1c1940, 13, "6f883cbe39ebd894c129c47977f4d6e2126c46bc1445f8c01b721a42fbb5aefa"),
    (0x8b0b0, 87, "ceec1cbf56606205c841f05cba93f4fef7452e23e475337edb210a8256cc861f"),
    (0xd2280, 55, "3eabef32da5f33351f67bf7ae2d642c827e095d9492ed97d7a6c00029960a300"),
    (0xd2354, 55, "21b594e78e8c3dbf3da8fb501af9c26aa3e186984826da46d20439e880ee8a1e"),
    (0x2bf5b1, 239, "56995a8791373dd8dcb6a0a9296af43f67b418f431a9a6132883aba2b2c6b314"),
    (0x347714, 37, "d80df4a2c2c519f81ada0978d1cf30964424402460b3f53430fe327bc3f09e0e"),
    (0x3663e0, 45, "6804143ffc8226117dcc36cee97bae0088dbb061d92361bca7af5aff20f7785c"),
    (0x3204a3, 24, "2ed15dbf70a13dfe5116b285a42667689ea38ad878daae464da62de73e8899e9"),
    (0x32189d, 24, "f25fe7ef65750af3ee1362ef0628bf01da229950f9800d0e0a12c0b9b28d2248"),
    (0xc4ea0, 24, "ff96587627f4332aab79c401709e069a191aef68164c965d6a77a54de8fbd4f9"),
    (0x260a80, 18, "dee93b13a4bd05cf44f7a78c838ec0b539ade2d1b0f9aa9ec475cfe3d3ba4d1b"),
    (0xa8e548, 24, "71a25c37281aecfac177757ac72567b0121de1faa6ecab365958242327786454"),
)


def _guards(payload, base_year):
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for operand, original in ((0x2BF5C1, b"\x04"), (0x3204AD, struct.pack("<I", 2015)), (0x3218A7, struct.pack("<I", 2015))):
            if va <= operand and operand + len(original) <= va + size:
                blob[operand - va:operand - va + len(original)] = original
        _require(hashlib.sha256(blob).hexdigest() == digest, f"foreign calendar context at {va:#x}")
