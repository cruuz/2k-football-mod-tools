#!/usr/bin/env python3
"""Bounded legacy-reserve lifecycle evidence on the actual p1-repaired v0.4.

This deliberately does not claim modern PS signing, accrued seasons, played
games, a full franchise save, or a complete simulated season. The input ROST
provides real identities/ratings. Contract lengths in the rollover probe are
explicit RAM-only fixtures. Only the requested JSON receipt is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.b765.p1_timeline_proof import Machine, STUBS
from tools.b765.p1_repair import FIXED_SHA256
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_practice_reserves as projection
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from mod_editor.core import nfl2k5_xbe_space as space

ROSTER_SHA256 = "a10aadd7f7968ef5334eb029109b199db954c7cfdd305229d24ea36beb711bb0"
# p1 called 2BFDD0 an external notification service; disassembly shows only
# rotation of three franchise globals. Execute it instead of inheriting that
# unnecessary stub and incorrect description.
CUT_STUBS = {address: reason for address, reason in STUBS.items() if address != 0x2BFDD0}
WEEK_STUBS = {
    0x27D460: "global injury refresh",
    0x2BDCF0: "global depth-chart rebuild; match/team fixture is not a loaded franchise",
    0x2BE020: "weekly injury update",
    0x2BC960: "CPU trades",
    0xC7CB0: "scheduled game simulation; no games are played or simulated",
    0x323870: "CPU free-agent transactions (callee pops eight argument bytes)",
    0x2BFBE0: "CPU cap cuts; front-office state is not a loaded franchise",
    0x27EB80: "end-of-week external refresh",
}
ROLLOVER_STUBS = {
    0x31E210: "draft order from postseason schedule/standings; absent from the ROST-only fixture",
    0x2BFBE0: "CPU cap cuts; front-office state is not a loaded franchise",
}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def validate_inputs(xbe, roster):
    if digest(xbe) != FIXED_SHA256:
        raise ValueError("expected the exact p1-repaired v0.4 XBE")
    if digest(roster) != ROSTER_SHA256:
        raise ValueError("expected the exact v0.4 main ROST body")


def identities(machine, players):
    return [(player - machine.pool) // 84 for player in players]


def contract(machine, player):
    word = machine.word(player + 0x24)
    return {"primary_index": (player - machine.pool) // 84,
            "remaining": word & 15, "length": (word >> 24) & 15,
            "years_pro": (word >> 8) & 31,
            "retired": bool(machine.byte(player + 8) & 8)}


def competition_projection(machine, roster_size):
    """Run the installed game staging/copy code and compare every active row."""
    original = bytes(machine.uc.mem_read(machine.BASE, roster_size))
    machine.put(projection.MODE_VA, 5)
    machine.call(projection.STAGE_VA, ecx=machine.team, edx=machine.team)
    active = machine.active()
    for side, (team, pool) in enumerate(zip(projection.TEAM_COPIES,
                                          projection.PLAYER_COPIES), 1):
        assert machine.byte(team + ps.ACTIVE_COUNT) == active
        for index in range(active):
            source = machine.word(machine.team + index * 4)
            expected = bytearray(machine.uc.mem_read(source, 84))
            expected[0x34] = side
            assert machine.word(team + index * 4) == pool + index * 84
            assert bytes(machine.uc.mem_read(pool + index * 84, 84)) == expected
    assert bytes(machine.uc.mem_read(machine.BASE, roster_size)) == original
    return {"mode": 5, "active_rows_per_side": active,
            "reserve_rows_in_active_copy": 0, "source_arena_identical": True}


def next_offseason(machine):
    # Boundary fixture only: no playoff games/standings are manufactured.
    machine.put(0xE576A4, 9)
    machine.put(0xE576AC, 34)
    for index in (32, 33):
        machine.put(0xE5786C + index * 4, machine.teams + index * 500)
    machine.stubs = {address: machine.ret for address in ROLLOVER_STUBS}
    machine.call(0x247B40)
    assert machine.word(0xE576A4) == 1


def timeline(xbe, roster):
    machine = Machine(xbe, roster)
    # Existing real, contracted club players. Reserve ownership is established
    # through the actual installed helper, not by writing hidden list bytes.
    players = [machine.word(machine.team + index * 4) for index in (0, 1)]
    for player in players:
        assert machine.call(ps.SYMBOLS["ps_demote"], ecx=machine.team, edx=player) == 1
    machine.populate(65 - machine.active() - machine.reserves())
    before = machine.state()
    machine.stubs = {address: machine.ret for address in CUT_STUBS}
    machine.call(0x2480B0)
    week_one = machine.state()
    assert (week_one["active"], week_one["reserves"], week_one["stage"],
            week_one["zero_based_week"]) == (53, 2, 8, 0)
    assert week_one["free_agents"] - before["free_agents"] == before["active"] - 53
    assert machine.identities()[1] == tuple(identities(machine, players))
    projection_before = competition_projection(machine, len(roster))
    saves = [machine.save_reload(len(roster))]

    def ret_eight():
        stack = machine.reg("ESP")
        machine.ret()
        machine.reg("ESP", stack + 12)

    machine.stubs = {address: machine.ret for address in WEEK_STUBS}
    machine.stubs[0x323870] = ret_eight
    weeks = []
    for week in range(1, 8):
        machine.call(0x247D40)
        assert machine.word(0xE576B4) == week
        assert machine.identities()[1] == tuple(identities(machine, players))
        assert machine.active() == 53
        weeks.append(machine.state())
    full = bytes(machine.uc.mem_read(machine.BASE, len(roster)))
    assert machine.call(ps.SYMBOLS["ps_promote"], ecx=machine.team, edx=players[0]) == 0
    assert bytes(machine.uc.mem_read(machine.BASE, len(roster))) == full
    released = machine.word(machine.team)
    machine.call(0x2BD900, ecx=machine.team, edx=released, args=(1, 1))
    assert machine.active() == 52
    assert machine.call(ps.SYMBOLS["ps_promote"], ecx=machine.team, edx=players[0]) == 1
    active_ids, reserve_ids = machine.identities()
    assert (len(active_ids), len(reserve_ids)) == (53, 1)
    assert identities(machine, players)[0] in active_ids
    assert reserve_ids == tuple(identities(machine, players[1:]))
    fa_table = machine.word(machine.root + 0x3C)
    fa = [machine.word(fa_table + 4 * index) for index in range(machine.free_agents())]
    assert fa.count(released) == 1 and all(player not in fa for player in players)
    projection_after = competition_projection(machine, len(roster))
    saves.append(machine.save_reload(len(roster)))
    after_promotion = machine.state()
    next_offseason(machine)
    assert machine.identities()[1] == reserve_ids
    assert identities(machine, players)[0] in machine.identities()[0]
    saves.append(machine.save_reload(len(roster)))
    return {"prepared": before, "week_one": week_one, "weekly_boundaries": weeks,
            "after_promotion": after_promotion, "next_offseason": machine.state(),
            "reserve_primary_indices": identities(machine, players),
            "full_active_promotion_refused_without_writes": True,
            "released_primary_index": identities(machine, [released])[0],
            "native_release_owned_once_by_fa": True,
            "competition_projection_before": projection_before,
            "competition_projection_after": projection_after,
            "serialized_roster_sha256": saves,
            "cut_stubs": {hex(k): v for k, v in CUT_STUBS.items()},
            "week_stubs": {hex(k): v for k, v in WEEK_STUBS.items()},
            "rollover_stubs": {hex(k): v for k, v in ROLLOVER_STUBS.items()}}


def rollover_contracts(xbe, roster):
    machine = Machine(xbe, roster)
    players = [machine.word(machine.team + index * 4) for index in range(4)]
    for player, length in zip(players, (1, 3, 1, 3)):
        machine.put(player + 0x24,
                    (machine.word(player + 0x24) & ~0x0F00000F) | length * 0x1000001)
    for player in players[:2]:
        assert machine.call(ps.SYMBOLS["ps_demote"], ecx=machine.team, edx=player) == 1
    before = [contract(machine, player) for player in players]
    next_offseason(machine)
    after = [contract(machine, player) for player in players]
    assert machine.word(0xE576A4) == 1
    assert machine.identities()[1] == tuple(identities(machine, players[:2]))
    for index, (old, new) in enumerate(zip(before, after)):
        assert not new["retired"]
        assert new["years_pro"] == (old["years_pro"] + 1) & 31
        assert new["remaining"] == old["remaining"] - int(index >= 2)
    saved = machine.save_reload(len(roster))
    return {"fixture": "RAM-only contract lengths 1/3 years on two real reserve and two real active players",
            "before": before, "after": after, "final": machine.state(),
            "serialized_roster_sha256": saved,
            "stubs": {hex(k): v for k, v in ROLLOVER_STUBS.items()},
            "finding": "Surviving reserves gain years pro but retain their remaining contract years; active controls decrement. This is legacy ownership persistence, not modern PS contract/accrual behavior."}


def prove(xbe, roster):
    validate_inputs(xbe, roster)
    allocations = space.layout(xbe)["allocations"]
    assert not any(row["owner"] == growth.OWNER for row in allocations)
    try:
        growth.apply(xbe)
    except growth.ArenaGrowthError as error:
        growth_refusal = str(error)
    else:
        raise AssertionError("actual p1 image unexpectedly has the arena-growth allocation")
    return {"inputs": {"xbe_sha256": digest(xbe), "roster_sha256": digest(roster)},
            "timeline": timeline(xbe, roster), "rollover": rollover_contracts(xbe, roster),
            "sixteen_slot_install_refusal": growth_refusal,
            "limits": ["Native x86 executes privately in Unicorn; no emulator or gameplay witness.",
                       "Final cuts, ownership helpers, competitive player copying, week-counter control, promotion and roster relocation execute; listed services are stubbed.",
                       "Weekly game simulation, CPU acquisition/cap policy and full signed franchise save loading are excluded.",
                       "The same timeline ownership is carried into a postseason boundary fixture and native rollover; the remaining season and playoffs are not simulated. A separate paired-control case isolates contract behavior.",
                       "Existing reserves are preserved. No PS sign/release screen, CPU PS fill, 16-slot native migration or accrued-season history is implemented by this proof."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", required=True)
    parser.add_argument("--roster", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    receipt = prove(Path(args.xbe).read_bytes(), Path(args.roster).read_bytes())
    output = json.dumps(receipt, indent=2) + "\n"
    Path(args.out).write_text(output)
    print(output)


if __name__ == "__main__":
    main()
