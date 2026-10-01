"""PROVED OFFLINE: execute both CPU fill gates and the retail signing body.

DESIGN: synthetic roster/cap boundary cases, using real retail records. No
financial or ownership routine is substituted. This is not a season or UI run.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_practice_squad as squad
from mod_editor.core import nfl2k5_roster_fill_composition as chain
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster
from tools.franchise_economy.probe import start

CASES = ("season_53", "physical_65", "invalid_metadata", "null_team",
         "economy_54", "no_cap_room", "zero_budget", "below_minimum",
         "exact_minimum_budget", "minimum_cap_boundary", "minimum_cap_allowed",
         "minimum_budget_allowed", "season_52_with_reserve")


def run_case(payload, name):
    m = start(retail_roster(), payload)
    team = m.team_base
    m.put(0xE576A0, 1)
    m.put(0xE576A4, 3)
    # DESIGN: isolate one low-rated rookie FA, so the native market floor and
    # strict budget comparison decide the outcome, not the FA mix on the disc.
    free_list = m.get(m.root + 0x3C)
    player = m.get(free_list)
    m.put(m.root + 0x38, 1)
    m.uc.mem_write(player + 10, b"\0\0")
    m.uc.mem_write(player + 0x24, b"\0\0\x02\x01")
    m.uc.mem_write(player + 0x35, b"\0")
    m.uc.mem_write(player + 0x38, bytes([30] * (84 - 0x38)))
    minimum = m.call(0x2BD440, ecx=player, args=(0, 1, 0))
    assert minimum == 222, minimum  # PROVED OFFLINE: ceil(885 / 4), game thousands.
    if name == "physical_65":
        # DESIGN: physical capacity fixture; pointers are real retail players.
        for i in range(12):
            m.put(team + 4 * (53 + i), m.get(team + 500 + i * 4))
        m.uc.mem_write(team + 0x19B, b"\x01")
        m.uc.mem_write(team + 0x1F2, b"\x0c\xa5")
    elif name == "invalid_metadata":
        m.uc.mem_write(team + 0x19B, b"\x02")
    elif name == "economy_54":
        m.put(team + 53 * 4, m.get(team + 500))
        m.uc.mem_write(team + 0x11C, b"\x36")
    elif name == "season_52_with_reserve":
        assert m.call(squad.SYMBOLS["ps_demote"], ecx=team, edx=m.get(team + 52 * 4)) == 1
    if name in ("season_53", "season_52_with_reserve"):
        m.put(0xE576A4, 8)
    m.call(0xC3F00, ecx=team)
    payroll = m.get(team + 0x124)
    cap, budget = payroll + 10000, 65535
    if name == "no_cap_room": cap = payroll
    if name == "zero_budget": budget = 0
    if name == "below_minimum": budget = minimum - 1
    if name == "exact_minimum_budget": budget = minimum
    if name == "minimum_cap_boundary": cap = payroll + minimum + 10
    if name == "minimum_cap_allowed": cap = payroll + minimum + 11
    if name == "minimum_budget_allowed": budget = minimum + 1
    m.put(0xE3C278, cap)
    visits = Counter()
    addresses = {"squad_guard": squad.SYMBOLS["cpu_sign_guard"],
                 "economy_gate": economy.SYMBOLS["economy_fill_gate"],
                 "retail_body": 0x322BB6, "remove_fa": 0x242580,
                 "contract": 0x3228A0, "append": 0xC3EE0, "transaction": 0x2BFDF0}
    for label, address in addresses.items():
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_, label=label: visits.update([label]),
                      begin=address, end=address)
    before = bytes(m.uc.mem_read(m.ARENA, 0x200000))
    count = m.uc.mem_read(team + 0x11C, 1)[0]
    result = m.call(chain.ENTRY, args=(0 if name == "null_team" else team, 0, budget, 0),
                    budget=5000000)
    success = name in ("minimum_cap_allowed", "minimum_budget_allowed", "season_52_with_reserve")
    assert result == int(success), (name, result, dict(visits))
    assert m.reg("ESP") == m.STACK + 20
    for register, value in (("EBX", 0x11111111), ("ESI", 0x22222222),
                            ("EDI", 0x33333333), ("EBP", 0x44444444)):
        assert m.reg(register) == value, (name, register)
    assert visits["squad_guard"] == 1
    if name in ("season_53", "physical_65", "invalid_metadata", "null_team"):
        assert visits["economy_gate"] == visits["retail_body"] == 0
    else:
        assert visits["economy_gate"] == 1
    if success:
        assert all(visits[k] == 1 for k in ("retail_body", "remove_fa", "contract", "append", "transaction"))
        assert m.uc.mem_read(team + 0x11C, 1)[0] == count + 1
        assert m.get(m.root + 0x38) == 0 and m.get(team + count * 4) == player
        assert payroll < m.get(team + 0x124) <= cap
        assert m.get(team + 0x124) - payroll >= minimum
        if name == "season_52_with_reserve":
            assert bytes(m.uc.mem_read(team + 0x1F2, 2)) == b"\x01\xa5"
    else:
        assert bytes(m.uc.mem_read(m.ARENA, 0x200000)) == before, name
        assert visits["remove_fa"] == visits["contract"] == visits["append"] == visits["transaction"] == 0
    assert not m.leaves
    return {"case": name, "result": result, "visits": dict(visits), "minimum": minimum,
            "budget": budget, "cap": cap, "payroll_before": payroll,
            "payroll_after": m.get(team + 0x124), "active_before": count,
            "active_after": m.uc.mem_read(team + 0x11C, 1)[0],
            "rejection_arena_unchanged": not success, "abi_preserved": True, "leaves": []}


def run(payload=None):
    if payload is None:
        payload = squad.apply(economy.apply(retail_bytes())[0])[0]
    assert economy.status(payload) == squad.status(payload) == "applied"
    return {"evidence": "PROVED OFFLINE", "scope": "synthetic native CPU fill boundaries",
            "xbe_sha256": hashlib.sha256(payload).hexdigest(),
            "cases": [run_case(payload, name) for name in CASES], "runtime_witnessed": False}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    result = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PROVED OFFLINE: {len(result['cases'])} native composition cases passed")
