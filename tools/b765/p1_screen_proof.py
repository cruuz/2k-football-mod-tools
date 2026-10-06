"""Bounded native event proof for the retired v0.4 Practice Squad screen.

Read the supplied default.xbe and main ROST *body*. Execute the actual
screen event dispatcher, native sheet constructor, A/tab/Back routes and
transactions. Graphics, sound, kernel allocation and the modal dialog use
the existing bounded ScreenMachine services. Because that fixture stubs
rendered-cell allocation, 0x170C70 returns no graphics-cell object here.
Sorting depends on those rendered cells and is outside this proof.

Only emulated RAM changes. This never launches the game or edits an input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_practice_squad_screen_fixture import ScreenMachine, screen


def prove(xbe: bytes, roster: bytes) -> dict:
    """Run a synthetic human/manager context over the supplied native bytes."""
    code, data = screen.allocations(xbe)
    expected, labels = screen.code_for(xbe, code["va"], data["va"])
    image = XbeImage(xbe)
    if image.read(code["va"], code["size"]) != expected:
        raise ValueError("unexpected Practice Squad screen code/tables")
    if image.read(screen.fp.COACH_DESK_ROWS_PTR_VA, 4) != struct.pack("<I", labels["menu"]):
        raise ValueError("proof requires the pre-repair Practice Squad navigation pointer")
    if len(roster) < 0x80 or roster[12:16] != b"ROST":
        raise ValueError("--roster must be the extracted main ROST body, without its 32-byte resource header")

    class Machine(ScreenMachine):
        @classmethod
        def setUpClass(cls):
            cls.patched, cls.body = xbe, roster
            cls.code, cls.data, cls.labels = code, data, labels

        def _services(self, uc, address, size, userdata):
            if address == 0x170C70:
                self._return(0)  # No rendered-cell object exists in this fixture.
            else:
                super()._services(uc, address, size, userdata)

    Machine.setUpClass()
    machine = Machine()
    machine.setUp()
    machine.menu_art_stubs = {
        0xF2920, 0xF3CD0, 0xF3D60, 0xF2D40, 0xF3680, 0xF3180,
        0xF31B0, 0x14D390,
    }
    machine.UI = machine.word(machine.MANAGER + 0x10C) + 0x65C
    machine.put(machine.MANAGER, machine.MANAGER + 0x800)
    machine.put(machine.MANAGER + 8, labels["descriptor"])
    machine.put(machine.MANAGER + 0x100, 1)
    if machine.byte(machine.team + 0x11C) < 8 or machine.byte(machine.team + 0x1F2):
        raise ValueError("baseline proof needs at least eight active players and no existing reserves")

    watch = {
        0x6E4E0: "screen_dispatch", 0xF40F0: "inherited_screen_handler",
        0x176B50: "native_sheet_activation", labels["activate"]: "custom_ps_activation",
        0x14E440: "dialog", 0x325B90: "draft_pick", 0x325B50: "draft_sign",
        0x31E0F0: "draft_choose", 0x2B83F0: "retail_roster_action",
        0x174CB0: "next_tab", 0x174CE0: "previous_tab",
    }
    hits = []

    def trace(_uc, address, _size, _userdata):
        if address in watch:
            hits.append({"va": hex(address), "function": watch[address]})

    machine.uc.hook_add(machine.u.UC_HOOK_CODE, trace)
    receipt = {
        "xbe_sha256": hashlib.sha256(xbe).hexdigest(),
        "roster_body_sha256": hashlib.sha256(roster).hexdigest(),
        "input": "supplied native XBE and main ROST body; synthetic selected human/manager context",
        "services_stubbed": [
            "heap allocation/free", "dialog/fade chosen result", "cell formatting/style/geometry",
            "0x170C70 graphics-cell lookup (cell renderer stubbed)", "six menu-art setup calls",
            "0xF31B0 menu-art tick", "0x14D390 menu sound",
        ],
        "excluded": ["rendered graphics", "controller input polling", "rendered-cell sorting", "save lifecycle", "full franchise/calendar progression"],
        "synthetic_player_edit": "player+0x24 bits 8..12 (years pro) set to 20 in emulated RAM; other bits preserved. This is not an accrued-seasons field.",
        "steps": [],
    }

    def event(number):
        return machine.call(0x6E4E0, ecx=machine.MANAGER, args=(number,))

    def record(name):
        receipt["steps"].append({
            "step": name, "phase": machine.word(0xE576A4),
            "active": machine.byte(machine.team + 0x11C),
            "reserves": machine.byte(machine.team + 0x1F2),
            "sheet_rows": machine.word(machine.UI + 0xA4),
            "dialog_tables": [hex(row[0]) for row in machine.dialogs],
            "pending_descriptor": hex(machine.word(0xAA2408)), "hits": list(hits),
        })
        hits.clear()
        machine.dialogs.clear()

    event(1)
    event(3)
    active = machine.byte(machine.team + 0x11C)
    machine.assertEqual(machine.word(machine.UI + 0xA4), active)
    record("enter/construct: complete Active roster exposed")
    player = machine.word(machine.team)
    contract = machine.word(player + 0x24)
    machine.put(player + 0x24, (contract & ~0x1F00) | (20 << 8))
    event(12)
    machine.assertEqual(machine.byte(machine.team + 0x11C), active - 1)
    machine.assertEqual(machine.byte(machine.team + 0x1F2), 1)
    record("A event: demote synthetic 20-years-pro player")
    event(14)
    machine.assertEqual(machine.word(machine.UI + 0xA4), 1)
    record("next-tab event: Reserves")
    event(12)
    machine.assertEqual(machine.byte(machine.team + 0x11C), active)
    machine.assertEqual(machine.byte(machine.team + 0x1F2), 0)
    record("A event: promote back from Reserves")
    machine.put(player + 0x24, contract)
    event(15)
    machine.assertEqual(machine.word(machine.UI + 0xA4), active)
    record("previous-tab event: Active")
    for _ in range(7):
        veteran = machine.word(machine.team)
        word = machine.word(veteran + 0x24)
        machine.put(veteran + 0x24, (word & ~0x1F00) | (20 << 8))
        event(12)
    machine.assertEqual(machine.byte(machine.team + 0x11C), active - 7)
    machine.assertEqual(machine.byte(machine.team + 0x1F2), 7)
    record("seven synthetic 20-years-pro veterans demoted without a veteran quota")
    event(10)
    machine.assertEqual(machine.word(machine.MANAGER + 0x100), 0)
    machine.assertEqual(machine.heap_live, set())
    record("Back event: native teardown and pop")
    receipt["draft_code_hit"] = any(
        hit["function"].startswith("draft_") or hit["function"] == "retail_roster_action"
        for step in receipt["steps"] for hit in step["hits"]
    )
    machine.assertFalse(receipt["draft_code_hit"])
    receipt["conclusion"] = (
        "All Active players are exposed by design; seven 20-years-pro players demote with no "
        "veteran quota. A/tab/Back flow did not enter the watched draft routines in this "
        "bounded trace. The reported weird draft remains unproven."
    )
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = prove(args.xbe.read_bytes(), args.roster.read_bytes())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(args.out), "draft_code_hit": receipt["draft_code_hit"],
                      "steps": len(receipt["steps"])}))


if __name__ == "__main__":
    main()
