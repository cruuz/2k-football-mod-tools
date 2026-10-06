#!/usr/bin/env python3
"""Extend p1's bounded native investigation of the reported PS/draft detour.

This developer-only probe runs actual cell construction and sorting, inherited
events, stale roster-action modes, and the native human final-cut guard. It
does not infer Noah's observed route from a negative trace. Only JSON is written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

import unicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.nfl2k5_practice_squad_screen_fixture import ScreenMachine, screen
from tools.b765.p1_timeline_proof import Machine, V04_SHA256
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

ROSTER_SHA256 = "a10aadd7f7968ef5334eb029109b199db954c7cfdd305229d24ea36beb711bb0"
P1_SHA256 = "16f312e4a5de98ea5be0c7bb9e909f2a10e5794c714bfdfbfd771f7aa9b6d00f"
WATCH = {
    0x325B90: "draft_pick", 0x325B50: "draft_sign", 0x31E0F0: "draft_choose",
    0x325A30: "draft_reset", 0x31E430: "undrafted_cleanup",
    0x2B83F0: "ordinary_roster_action", 0x323720: "free_agency_start",
    0x324600: "free_agency_day", 0x170320: "sort_setup", 0x16F570: "sort_rows",
    0x1739F0: "cell_construct", 0x170C70: "cell_lookup",
    0x6E390: "screen_push", 0x6E2E0: "screen_replace",
    0x6E400: "screen_pop", 0x2BF950: "human_cut_guard",
}
FORBIDDEN = {
    "draft_pick", "draft_sign", "draft_choose", "draft_reset",
    "undrafted_cleanup", "ordinary_roster_action", "free_agency_start", "free_agency_day",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin(data, expected, label):
    if digest(data) != expected:
        raise ValueError(f"{label}: this investigation requires the pinned evidence input")


def trace(machine):
    hits = Counter()

    def visit(_uc, address, _size, _data):
        if address in WATCH:
            hits[WATCH[address]] += 1

    machine.uc.hook_add(unicorn.UC_HOOK_CODE, visit)
    return hits


def screen_machine(xbe, roster):
    class NativeCells(ScreenMachine):
        @classmethod
        def setUpClass(cls):
            cls.patched, cls.body = xbe, roster
            cls.code, cls.data = screen.allocations(xbe)
            _, cls.labels = screen.code_for(xbe, cls.code["va"], cls.data["va"])

        def _services(self, uc, address, size, data):
            # Unlike p1, execute cell initialization, formatting/value getters,
            # callback binding, cell lookup and comparisons. Geometry alone
            # remains outside the proof; no pixels or Xbox services are used.
            if address in (0x172660, 0x1739F0):
                return
            super()._services(uc, address, size, data)

    NativeCells.setUpClass()
    machine = NativeCells()
    machine.setUp()
    machine.menu_art_stubs = {
        0xF2920, 0xF3CD0, 0xF3D60, 0xF2D40,
        0xF3680, 0xF3180, 0xF31B0, 0x14D390,
    }
    machine.UI = machine.word(machine.MANAGER + 0x10C) + 0x65C
    machine.put(machine.MANAGER, machine.MANAGER + 0x800)
    machine.put(machine.MANAGER + 8, machine.labels["descriptor"])
    machine.put(machine.MANAGER + 0x100, 1)
    return machine


def screen_case(xbe, roster, reserve_count):
    machine = screen_machine(xbe, roster)
    if reserve_count:
        machine.demote(reserve_count)
    hits = trace(machine)

    def event(value):
        return machine.call(0x6E4E0, ecx=machine.MANAGER, args=(value,))

    def rows():
        table = machine.word(machine.UI + 0x40)
        return [machine.word(table + 4 * i) for i in range(machine.word(machine.UI + 0xA4))]

    # Run the real desk callback and check the destination, then consume its
    # pending pointer exactly as the real transition's final reset does.
    machine.call(machine.labels["row"], ecx=machine.MANAGER)
    assert machine.word(0xAA2408) == machine.labels["descriptor"]
    machine.put(0xAA2408, 0)
    event(1)
    event(3)
    assert machine.word(machine.UI + 0xA4) == 52 - reserve_count
    assert machine.word(machine.UI + 0xA0) == 30
    before = machine.snapshot()
    machine.dialog_result = 0  # Cancel every A popup during the broad event sweep.
    pages = []
    for page in ("Active", "Reserves"):
        initial_rows = sorted(rows())
        columns = machine.word(machine.UI + 0xA0)
        for column in range(columns):
            machine.put(machine.UI + 0xC0, column)
            event(13)  # inherited sheet +0xDC -> 0x2B83E0 -> native sort
            event(13)  # reverse the sort
            assert sorted(rows()) == initial_rows
            event(12)  # execute sheet/page/cell activation with Cancel
            assert machine.word(0xAA2408) == 0
        pages.append({"page": page, "rows": len(initial_rows), "columns_sorted_both_ways": columns})
        if page == "Active":
            event(14)
    event(15)
    # All seven recognized ordinary-roster action modes are stale-context
    # fixtures. The custom activation must never fall through to that handler.
    for mode in range(7):
        machine.put(0xACECD0, mode)
        event(12)
    for value in (11, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26):
        event(value)
    assert machine.snapshot() == before
    assert machine.word(0xE576A4) == 7
    sort_calls = hits["sort_setup"]
    assert sort_calls == hits["sort_rows"] == 120
    machine.dialog_result = 1
    if reserve_count:
        event(12)
        assert machine.snapshot() == before  # Full reserves refuse demotion.
        event(14)
        selected = rows()[0]
        machine.put(machine.UI + 0xBC, 0)
        event(12)  # Promote from full reserves with real native cell callbacks.
        assert machine.byte(machine.team + 0x11C) == 41
        event(15)
        machine.put(machine.UI + 0xBC, rows().index(selected))
        event(12)
        assert machine.byte(machine.team + 0x11C) == 40
        assert machine.byte(machine.team + 0x1F2) == 12
        actions = ["full-reserve demotion refused", "promote", "demote the same identity"]
    else:
        selected = rows()[0]
        machine.put(machine.UI + 0xBC, 0)
        event(12)
        assert machine.byte(machine.team + 0x11C) == 51
        event(14)
        assert rows() == [selected]
        event(12)
        assert machine.byte(machine.team + 0x11C) == 52
        assert machine.byte(machine.team + 0x1F2) == 0
        actions = ["demote", "promote the same identity"]
    assert machine.word(0xAA2408) == 0
    event(10)
    assert machine.word(machine.MANAGER + 0x100) == 0
    assert not machine.heap_live
    assert not FORBIDDEN.intersection(hits)
    return {
        "reserves": reserve_count, "pages": pages, "calls": dict(sorted(hits.items())),
        "stale_roster_action_modes": list(range(7)), "roster_unchanged_on_cancel": True,
        "pending_descriptor_after_inputs": "0x0", "final_stage": 7,
        "successful_action_roundtrip": actions, "explicit_sorts": sort_calls,
        "back_freed_all_screen_allocations": True,
    }


def corrupt_screen_case(xbe, roster):
    machine = screen_machine(xbe, roster)
    machine.demote(12)
    machine.uc.mem_write(machine.team + 0x1F2, b"\x0d")
    before = machine.snapshot()
    hits = trace(machine)
    machine.call(machine.labels["row"], ecx=machine.MANAGER)
    assert machine.word(0xAA2408) == 0
    assert machine.dialogs and machine.dialogs[-1][0] == 0x5042FC
    assert machine.snapshot() == before
    assert not FORBIDDEN.intersection(hits)
    return {"fixture": "reserve count 13 with baseline maximum 12", "screen_entry_refused": True,
            "pending_descriptor": "0x0", "roster_unchanged": True, "calls": dict(hits)}


def human_cut_case(xbe, roster, automatic, active):
    machine = Machine(xbe, roster)
    machine.populate(active - machine.active())
    machine.put(0xE5775C, 1)
    machine.put(0xE3C0A0, machine.team)
    machine.put(0xE6013C, int(automatic))
    dialogs = []

    def dialog():
        pointer, chunks = machine.reg("EDX"), []
        for index in range(512):
            chunk = bytes(machine.uc.mem_read(pointer + index * 2, 2))
            if chunk == b"\0\0":
                break
            chunks.append(chunk)
        else:
            raise AssertionError("unterminated native modal text")
        dialogs.append(b"".join(chunks).decode("utf-16le"))
        machine.ret()

    for address in (0x2BF8B0, 0x27D460, 0x27EDF0):
        machine.stubs[address] = lambda: machine.ret()
    machine.stubs[0x14E520] = dialog
    hits = trace(machine)
    prepared = machine.state()
    machine.call(0x2480B0)
    final = machine.state()
    assert not FORBIDDEN.intersection(hits)
    if not automatic and active > 53:
        assert final == prepared and len(dialogs) == 1
        assert "maximum of 53 players" in dialogs[0]
    else:
        assert final["stage"] == 8 and final["zero_based_week"] == 0
        assert final["active"] == 53 and not dialogs
    return {"automatic": automatic, "prepared": prepared, "final": final,
            "dialogs": dialogs, "calls": dict(sorted(hits.items())),
            "native_human_team_enumeration": True, "native_transaction_indices": True}


def static_bindings(xbe, after):
    image = XbeImage(xbe)
    code, data = screen.allocations(xbe)
    _, labels = screen.code_for(xbe, code["va"], data["va"])
    word = lambda address: struct.unpack("<I", image.read(address, 4))[0]
    assert word(labels["sheet"] + 0xC4) == labels["activate"]
    assert word(labels["sheet"] + 0xDC) == 0x2B83E0
    assert image.read(0x2B83E0, 5) == bytes.fromhex("e99b7febff")
    columns = []
    for index in range(30):
        pointer = word(labels["active_page"] + 0x9C + index * 4)
        assert image.read(pointer + 0x20, 0x30) == bytes(0x30)
        columns.append(hex(pointer))
    assert word(labels["active_page"] + 0x94) == word(labels["reserve_page"] + 0x94) == 0
    assert XbeImage(after).read(0x5221A0, 4) == struct.pack("<I", 0x521EEC)
    return {
        "activation": hex(labels["activate"]), "secondary_action": "0x2b83e0 -> 0x170380 (sort)",
        "column_A_and_secondary_bindings_zero": columns,
        "optional_page_sort_key_pointers": [0, 0],
        "p1_desk_rows_pointer": "0x521eec (existing Schedule/Practice/Crib table)",
    }


def prove(before, after, roster):
    pin(before, V04_SHA256, "v0.4 XBE")
    pin(after, P1_SHA256, "p1 XBE")
    pin(roster, ROSTER_SHA256, "v0.4 roster")
    return {
        "schema": "b765-p2-detour-investigation/v1",
        "inputs": {"v04_xbe": digest(before), "p1_xbe": digest(after), "roster": digest(roster)},
        "bindings": static_bindings(before, after),
        "screen_cases": [screen_case(before, roster, count) for count in (0, 12)],
        "corrupt_metadata": corrupt_screen_case(before, roster),
        "human_cut_cases": [
            {"xbe": name, **human_cut_case(payload, roster, automatic, active)}
            for name, payload in (("v0.4", before), ("p1", after))
            for automatic, active in ((False, 54), (False, 53), (True, 65))
        ],
        "conclusion": "No draft/free-agency detour reproduced. Its observed cause remains unresolved; "
                      "these traces rule out the tested sorting, full-reserve, malformed-count, "
                      "stale ordinary-roster action modes and human-final-cut paths as triggers in these fixtures.",
        "limits": [
            "No Xbox boot, rendered screen, controller polling, modal event pump or game witness.",
            "Screen heap, chosen dialog result, fade, geometry and menu art/audio remain bounded services.",
            "Human cut proof executes native human-team enumeration, eligibility check, text formatting, "
            "cut transactions and phase advance; dialog display, stat/class/season initialization at "
            "0x2BF8B0 and injury/depth refresh remain substituted.",
            "The real native transition's pending-descriptor reset is represented by an explicit fixture "
            "write after checking the actual row callback destination; the transition animation is excluded.",
        ],
        "gameplay_witnessed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "roster", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    receipt = prove(args.before.read_bytes(), args.after.read_bytes(), args.roster.read_bytes())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(args.out), "screen_cases": len(receipt["screen_cases"]),
                      "human_cut_cases": len(receipt["human_cut_cases"]), "cause": "unresolved"}))


if __name__ == "__main__":
    main()
