"""b77 / a1: what each of the 51 ESPN 25th Anniversary menu entries shows and loads, by the game's own code (Unicorn).

For a menu row (the list's display row) this resolves
  * what the row shows: the list's row-draw callbacks (title and date 20C800, mini helmets 20C710 / 20C790);
  * what a click opens: the select handler 20CB30 (the physical SITU row in BF1858, the situation record, both
    teams and their rosters, the staged match) and every consumer that keys on the physical row: the details venue
    line 2C5A70, the selected stadium record, the field bundle name 62C96 (a00..a50), the era-rules profile, the
    book routing 62902 and the completed-moment test 20C390;
and states what each must be from the authored data (the retail situation.iff for rows 1 to 25, the moments data and
the venue, field and era catalogs for the rest), independently of the code under test.

Substituted boundaries are the harness's own (archive reads, list/menu service calls, spatial and clock seams). No
graphics, audio or complete game: this is offline evidence, never a played game.
"""
from __future__ import annotations

import struct

try:                                  # only the native half needs Unicorn; the expected-data half is plain Python
    from unicorn import UC_HOOK_CODE
    from unicorn import x86_const as regs
except ImportError:                   # pragma: no cover
    UC_HOOK_CODE = regs = None

from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_roster_records as rr

KICKOFF_SITE = 1410332            # nfl2k5_kick_rules.KICKOFF_SITES[0]: a kickoff spot multiplied by the era's yard
SCRATCH_CODE, BOOKS_ARENA = 0x2680000, 0x2600000


# ------------------------------------------------------------------------------------------------ disc evidence

def disc_inputs(disc, retail_iso, data):
    """(resources, context, identities, situ_chunk, extra_files, retail_situ) read from a SOFTDRINK disc image: its
    main roster, its grown situation.iff, the 75 retail historic rosters, its directory and every moment team file.
    The retail disc supplies only the 25-row situation.iff that the historic descriptors are checked against."""
    from mod_editor.core import nfl2k5_espn25_rosters as e
    with rr._outer_image()(retail_iso) as retail:
        retail_situ = retail.read_entry(22)
    with rr._outer_image()(disc) as image:
        main, situ = image.read_entry(5), image.read_entry(22)
        context = e.describe_context(main, retail_situ, image.entries)
        resources = {5: main, 22: retail_situ}
        for descriptor in context["descriptors"]:
            resources[descriptor["outer"]] = image.read_entry(descriptor["outer"])
        identities = {entry.name_id for entry in image.entries}
        by_id = {entry.name_id: entry for entry in image.entries}
        extra = {filename: image.read_entry(by_id[mm.name_id(filename)].index)
                 for _key, filename, _entry, _selector, _identity in mm.table_entries(data)}
        situ_chunk = situ[:32 + struct.unpack_from("<I", situ, 4)[0]]
    return resources, context, identities, situ_chunk, extra, retail_situ


# ------------------------------------------------------------------------------------------------ what must be true
# (moved to tools/b77/menu_facts.py so that the player-list generator can use it without an emulator)
from tools.b77.menu_facts import (MONTHS, authored_rows, display_order_from, expected_rows, iso,  # noqa: E402,F401
                                  mm_venues, retail_rows)


# ------------------------------------------------------------------------------------------------ what the game does

def record_fields(cpu, record):
    return dict(title=cpu.text(cpu.r(record)), date=cpu.text(cpu.r(record + 0xC)),
                away=(cpu.text(cpu.r(record + 0x14)), cpu.r(record + 0x1C)),
                home=(cpu.text(cpu.r(record + 0x18)), cpu.r(record + 0x20)),
                stadium=cpu.r(record + 0x10), user_side=cpu.r(record + 0x24), possession=cpu.r(record + 0x28),
                score_now=(cpu.r(record + 0x2C), cpu.r(record + 0x34)), final=(cpu.r(record + 0x30), cpu.r(record + 0x38)),
                quarter=cpu.r(record + 0x3C) + 1, ball=cpu.f(record + 0x40), distance=cpu.f(record + 0x44),
                down=cpu.r(record + 0x48), seconds=cpu.f(record + 0x4C), timeouts=(cpu.r(record + 0x50), cpu.r(record + 0x54)),
                kits=(cpu.r(record + 0x58), cpu.r(record + 0x5C)), weather=cpu.r(record + 0x60),
                time=cpu.r(record + 0x64), temp=struct.unpack("<i", cpu.read(record + 0x68, 4))[0])


def run_to(cpu, at, stop, **registers):
    """cpu.run for a fragment that ends at `stop` inside a function rather than at its return."""
    cpu.w(cpu.STACK, cpu.STOP)
    for name in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        cpu.uc.reg_write(getattr(regs, "UC_X86_REG_" + name.upper()), registers.get(name, 0))
    cpu.uc.reg_write(regs.UC_X86_REG_ESP, cpu.STACK)
    cpu.uc.reg_write(regs.UC_X86_REG_EFLAGS, 0x202)
    cpu.uc.emu_start(at, stop, count=cpu.instruction_budget)
    assert cpu.reg("eip") == stop, f"stopped at {cpu.reg('eip'):x}, not {stop:x}"
    return cpu.reg("eax")


def field_bundle_name(cpu, suffix="ds"):
    """The stadium bundle file name 62C96 leaves for the physical row in BF1858 (base name s10<suffix>.iff)."""
    cpu.write(0xB306D0, ("s10" + suffix + ".iff\0").encode("utf-16le"))
    run_to(cpu, 0x62C96, 0x62C9B, esi=0x69)
    return cpu.text(0xB306D0)


def era_kickoff_multiplier(cpu):
    """The era profile's kickoff spot for the physical row in BF1858: 1.0 * (50 - yard) * 91.44 (the rules owner)."""
    raw = bytes(cpu.read(KICKOFF_SITE, 5))
    assert raw[0] in (0xE8, 0xE9), "the kickoff site is not a call"
    target = KICKOFF_SITE + 5 + struct.unpack_from("<i", raw, 1)[0]
    code = b"\xd9\xe8" + b"\xe8" + struct.pack("<i", target - SCRATCH_CODE - 2 - 5)
    code += b"\xd9\x1d" + struct.pack("<I", SCRATCH_CODE + 256) + b"\xc3"
    cpu.write(SCRATCH_CODE, code)
    cpu.uc.ctl_remove_cache(SCRATCH_CODE, SCRATCH_CODE + 256)
    cpu.run(SCRATCH_CODE)
    return cpu.f(SCRATCH_CODE + 256)


def book_is_modern(cpu, home):
    """The default-book decision of 62902 for this match team in Anniversary mode: True = the franchise's current
    (modern) book, False = the preserved retail bank. Reads BF1858 and the loaded situation record, as the game does."""
    from mod_editor.core import nfl2k5_stock_books as books
    a = BOOKS_ARENA
    cpu.write(a, bytes(0x1000))
    cpu.w(a + 0x110, a + 0x300)
    cpu.w(a + 0x304, a + 0x400)
    cpu.write(a + 0x400, "BUF\0".encode("utf-16le"))
    cpu.w(a + 0x128, 4)                       # this side's category: Anniversary teams are category 4
    cpu.w(a + 0x508, int(home))
    cpu.write(a + 0x600, b"\xA5" * 32)
    cpu.w(0xE5FF80, 8)
    stops = (0x62A1B, 0x62A37)
    seen = {}

    def stop(uc, at, size, data):
        if at in stops:
            seen["at"] = at
            uc.emu_stop()
    handle = cpu.uc.hook_add(UC_HOOK_CODE, stop, begin=0x62A1B, end=0x62A37)
    try:
        cpu.w(cpu.STACK, cpu.STOP)
        for name, value in dict(eax=a, ebx=0x1234, edi=0, esi=a + 0x600, ebp=a + 0x500).items():
            cpu.uc.reg_write(getattr(regs, "UC_X86_REG_" + name.upper()), value)
        cpu.uc.reg_write(regs.UC_X86_REG_ESP, cpu.STACK)
        cpu.uc.reg_write(regs.UC_X86_REG_EFLAGS, 0x202)
        cpu.uc.emu_start(books.SITE, cpu.STOP, count=2000)
    finally:
        cpu.uc.hook_del(handle)
    assert seen, "the book resolver did not reach the default or the stock exit"
    return seen["at"] == 0x62A1B


def roster_names(cpu, side):
    """Sorted 'First Last' of every player pointer in the staged team of this side (home 77B00, away 77B40)."""
    team = cpu.run(0x77B00 if side == "home" else 0x77B40)
    names = []
    for i in range(65):
        pointer = cpu.r(team + 4 * i)
        if pointer:
            person = cpu.person(pointer)
            names.append(f"{person['first']} {person['last']}")
    return sorted(names)


def draw_all(cpu, display_row):
    return {kind: cpu.draw_row(kind, display_row) for kind in ("title", "home_helmet", "away_helmet")}


def resolve_entry(cpu, display_row, *, named_venues=True, era=True, books=True):
    """Everything the game does for one menu row, as plain data (display_row is zero-based)."""
    shown = draw_all(cpu, display_row)
    completed_flag = cpu.run(0x20C390, ecx=display_row)
    cpu.events.clear()
    loads_before = len(cpu.extra_loads)
    cpu.select(display_row)
    physical = cpu.r(0xBF1858)
    record = cpu.run(0x20C6F0)
    opened = record_fields(cpu, record)
    match = cpu.match()
    staged = cpu.selected()
    out = dict(display_row=display_row + 1, physical=physical + 1, completed_flag=completed_flag,
               shown=shown, record=record, opened=opened,
               teams=dict(away=staged["away"]["name"], home=staged["home"]["name"],
                          active=(staged["away"]["active"], staged["home"]["active"])),
               rosters=dict(away=roster_names(cpu, "away"), home=roster_names(cpu, "home")),
               files=[e["filename"] for e in cpu.events if e.get("filename")],
               new_files=sorted(cpu.extra_loads[loads_before:]),
               scenario=match["scenario"], export_players=match["export_players"],
               kit_files={side: match["sides"][side]["kit"] for side in ("away", "home")},
               kit_exists={side: match["sides"][side]["kit_exists"] for side in ("away", "home")},
               field_qbs={side: (match["sides"][side]["quarterback"] or {}).get("first", "") + " " +
                          (match["sides"][side]["quarterback"] or {}).get("last", "") for side in ("away", "home")})
    stadium = cpu.run(0x77460)
    table = cpu.r(cpu.r(0xB72918) + 0x14)                   # the 82-record stadium table, 128 bytes a record
    out["stadium_record"] = dict(name=cpu.text(cpu.r(stadium)), code=cpu.text(cpu.r(stadium + 0x0C)),
                                 index=(stadium - table) // 128, aligned=(stadium - table) % 128 == 0)
    cpu.w(0x2500800, 0)
    cpu.run(0x2C5A70, args=(0x2500800, 0, 0))
    out["details_venue"] = cpu.text(0x2500800)
    out["field_bundle"] = field_bundle_name(cpu)
    if era:
        out["era_kickoff"] = era_kickoff_multiplier(cpu)
    if books:
        out["book_modern"] = dict(away=book_is_modern(cpu, False), home=book_is_modern(cpu, True))
    cpu.run(0x20C3C0)                              # leave the details screen: releases both imported teams
    return out


def proof_table(entries, expected, order):
    """One compact, readable row per menu entry (for the report's evidence files)."""
    rows = []
    for entry in entries:
        d = entry["display_row"] - 1
        want = expected[order[d] - 1]
        shown = entry["shown"]
        rows.append(dict(
            display_row=entry["display_row"], physical_row=entry["physical"],
            drawn_title=shown["title"]["title"], drawn_date=shown["title"]["date"],
            title_cell_asked_for_row=shown["title"]["asked"][0] + 1,
            helmets=dict(away=[shown["away_helmet"]["team"], shown["away_helmet"]["kit"]],
                         home=[shown["home_helmet"]["team"], shown["home_helmet"]["kit"]]),
            opened_title=entry["opened"]["title"], opened_date=entry["opened"]["date"],
            drawn_matches_opened=(shown["title"]["title"], shown["title"]["date"]) ==
                                 (entry["opened"]["title"], entry["opened"]["date"]),
            expected_title=want["title"], opened_matches_expected=entry["opened"]["title"] == want["title"],
            teams=[entry["teams"]["away"], entry["teams"]["home"]], new_team_files=entry["new_files"],
            field_qbs=entry["field_qbs"], scenario=entry["scenario"], stadium_index=entry["stadium_record"]["index"],
            details_venue=entry["details_venue"], field_bundle=entry["field_bundle"],
            era_kickoff_spot=round(entry["era_kickoff"], 2) if "era_kickoff" in entry else None,
            book_modern=entry.get("book_modern")))
    return rows
