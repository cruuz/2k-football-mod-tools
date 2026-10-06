#!/usr/bin/env python3
"""Bounded native final-cuts timeline on SOFTDRINK v0.4 and its p1 repair.

Run with explicit --before XBE --after XBE --roster ROST --out JSON paths.
Only the JSON receipt is written. Fixture setup extends one real club using
real free agents. There is no Xbox boot, controller interaction, or played
witness. Independent external services are explicitly stubbed below.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import unicorn as u
from unicorn import x86_const as x

from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

V04_SHA256 = "5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29"
CALLEE_SAVED = {
    "EBX": 0x11111111,
    "ESI": 0x22222222,
    "EDI": 0x33333333,
    "EBP": 0x44444444,
}
STUBS = {
    0x13EC40: "return zero human-controlled clubs; all NFL teams use automatic cuts",
    0x2BF8B0: "skip global stat reset and prospect generation",
    0x27D460: "skip global injury refresh",
    0x27EDF0: "skip depth refresh",
    0x2BFDD0: "skip external UI notifications",
}


class Machine:
    BASE = 0x2000000
    STACK = 0x3008000
    STOP = 0x3100000

    def __init__(self, payload: bytes, roster: bytes):
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.image = XbeImage(payload)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        for section in self.image.sections:
            if section.raw_size:
                self.uc.mem_write(
                    section.start,
                    payload[section.raw:section.raw + section.raw_size],
                )
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        for section in self.image.sections:
            if section.start >= 0x1000000:
                permissions = (
                    u.UC_PROT_READ
                    | (u.UC_PROT_WRITE if section.writable else 0)
                    | (u.UC_PROT_EXEC if section.executable else 0)
                )
                start = section.start & ~4095
                end = (section.end + 4095) & ~4095
                self.uc.mem_protect(start, end - start, permissions)
        self.uc.mem_map(self.BASE, 0x200000)
        self.uc.mem_map(0x3000000, 0x10000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.mem_write(self.BASE, roster)
        self.root = self.BASE + 0x40
        self.put(0xB72918, self.root)
        self.stubs = {}
        self.visits = {}
        self.uc.hook_add(u.UC_HOOK_CODE, self.visit)
        self.call(0xC0500, ecx=self.root)
        self.teams = self.word(self.root + 0x1C)
        self.team = self.teams
        self.pool = self.word(self.root + 4)

        # Boundary fixture: Franchise, preseason, four weeks already completed,
        # initial year and Front Office automatic roster cuts enabled.
        for address, value in (
            (0xE576A0, 2), (0xE576A4, 7), (0xE576AC, 32),
            (0xE576B0, 4), (0xE576B4, 4), (0xE576B8, 0),
            (0xE6013C, 1),
        ):
            self.put(address, value)
        self.uc.mem_write(0xE5775C, bytes(34 * 4))
        self.uc.mem_write(0xE421E0, bytes(160 * 4))
        for team in range(32):
            self.put(0xE5786C + 4 * team, self.teams + 500 * team)

    def word(self, address):
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def put(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def byte(self, address):
        return self.uc.mem_read(address, 1)[0]

    def reg(self, name, value=None):
        register = getattr(x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xFFFFFFFF)

    def ret(self, value=0):
        stack = self.reg("ESP")
        self.reg("EAX", value)
        self.reg("EIP", self.word(stack))
        self.reg("ESP", stack + 4)

    def visit(self, _uc, address, _size, _data):
        watched = (
            0x2BFAA0, 0x2BF9A0, 0x2BD900,
            ps.SYMBOLS["ps_cut"], ps.SYMBOLS["ps_demote"],
            0x247B20, 0xC4BA0, 0xC4E40, 0xC4E60,
        )
        if address in self.stubs:
            self.visits[address] = self.visits.get(address, 0) + 1
            self.stubs[address]()
        elif address in watched:
            self.visits[address] = self.visits.get(address, 0) + 1

    def call(self, address, *, ecx=0, edx=0, args=(), budget=8000000):
        self.put(self.STACK, self.STOP)
        for index, value in enumerate(args, 1):
            self.put(self.STACK + 4 * index, value)
        registers = {
            **CALLEE_SAVED, "ESP": self.STACK, "ECX": ecx, "EDX": edx,
            "EAX": 0, "EFLAGS": 0x202,
        }
        for name, value in registers.items():
            self.reg(name, value)
        try:
            self.uc.emu_start(address, self.STOP, count=budget)
        except u.UcError as error:
            raise AssertionError(
                f"{address:#x} fault at {self.reg('EIP'):#x}: {error}"
            ) from error
        assert self.reg("EIP") == self.STOP, "instruction budget exhausted"
        assert self.reg("ESP") == self.STACK + 4 + len(args) * 4, "unbalanced stack"
        for name, value in CALLEE_SAVED.items():
            assert self.reg(name) == value, f"clobbered callee-saved {name}"
        return self.reg("EAX")

    def active(self):
        return self.byte(self.team + ps.ACTIVE_COUNT)

    def reserves(self):
        return self.byte(self.team + ps.COUNT)

    def free_agents(self):
        return self.word(self.root + 0x38)

    def identities(self):
        active, reserves = self.active(), self.reserves()
        return (
            tuple((self.word(self.team + 4 * i) - self.pool) // 84
                  for i in range(active)),
            tuple((self.word(self.team + 4 * i) - self.pool) // 84
                  for i in range(active, active + reserves)),
        )

    def populate(self, count):
        for _ in range(count):
            available = self.free_agents()
            table = self.word(self.root + 0x3C)
            player = self.word(table)
            self.uc.mem_write(
                table,
                bytes(self.uc.mem_read(table + 4, (available - 1) * 4)) + bytes(4),
            )
            self.put(self.root + 0x38, available - 1)
            # Fixture contract makes the acquired FA a normal signed player.
            # Its actual identity, appearance and ratings remain unchanged.
            self.put(player + 0x24,
                     (self.word(player + 0x24) & ~0x0F00000F) | 0x02000002)
            assert self.call(0xC3EE0, ecx=self.team, edx=player) == 1

    def advance(self):
        self.stubs = {address: self.ret for address in STUBS}
        self.call(0x2480B0)

    def save_reload(self, size):
        before = bytes(self.uc.mem_read(self.BASE, size))
        self.call(0xC0730, ecx=self.root)
        saved = bytes(self.uc.mem_read(self.BASE, size))
        ps.validate_roster(saved)
        self.call(0xC0500, ecx=self.root)
        assert bytes(self.uc.mem_read(self.BASE, size)) == before
        return hashlib.sha256(saved).hexdigest()

    def state(self):
        return {
            "stage": self.word(0xE576A4),
            "stage_weeks": self.word(0xE576B0),
            "zero_based_week": self.word(0xE576B4),
            "active": self.active(), "reserves": self.reserves(),
            "free_agents": self.free_agents(),
        }


def scope_receipt(machine, before, after, before_ids, after_ids):
    club_ids = set(before_ids[0] + before_ids[1])
    untouched = 0
    for player in range(machine.word(machine.root)):
        if player in club_ids:
            continue
        offset = machine.pool - machine.BASE + player * 84
        assert before[offset:offset + 84] == after[offset:offset + 84], (
            "unrelated player changed", player,
        )
        untouched += 1
    for team in range(1, 32):
        offset = machine.teams - machine.BASE + team * 500
        assert before[offset:offset + 500] == after[offset:offset + 500], (
            "unrelated team changed", team,
        )
    released = set(before_ids[0]) - set(after_ids[0]) - set(after_ids[1])
    table = machine.word(machine.root + 0x3C)
    free_agents = [(machine.word(table + i * 4) - machine.pool) // 84
                   for i in range(machine.free_agents())]
    assert all(free_agents.count(player) == 1 for player in released)
    assert not set(after_ids[1]).intersection(free_agents)
    return {
        "unrelated_primary_records_identical": untouched,
        "unrelated_nfl_team_records_identical": 31,
        "released_players_owned_once_by_free_agent_pool": len(released),
        "changed_bytes_in_arena": sum(a != b for a, b in zip(before, after)),
    }


def run_case(name, payload, roster, existing_reserve):
    machine = Machine(payload, roster)
    initial = machine.state()
    if existing_reserve:
        player = machine.word(machine.team + 4 * (machine.active() - 1))
        assert machine.call(ps.SYMBOLS["ps_demote"], ecx=machine.team, edx=player) == 1
    machine.populate(65 - machine.reserves() - machine.active())
    prepared, prepared_ids = machine.state(), machine.identities()
    prepared_arena = bytes(machine.uc.mem_read(machine.BASE, len(roster)))
    machine.advance()
    final, final_ids = machine.state(), machine.identities()
    final_arena = bytes(machine.uc.mem_read(machine.BASE, len(roster)))
    scope = scope_receipt(machine, prepared_arena, final_arena, prepared_ids, final_ids)
    assert (final["stage"], final["stage_weeks"], final["zero_based_week"],
            final["active"]) == (8, 18, 0, 53)
    if name == "v04_hidden_demotions":
        assert final["reserves"] == 12
        assert final["free_agents"] == prepared["free_agents"]
    else:
        assert final["reserves"] == int(existing_reserve)
        assert final["free_agents"] - prepared["free_agents"] == prepared["active"] - 53
        if existing_reserve:
            assert final_ids[1] == prepared_ids[1]
    return {
        "name": name, "initial": initial, "prepared": prepared, "final": final,
        "visits": {hex(address): count for address, count in sorted(machine.visits.items())},
        "saved_roster_sha256": machine.save_reload(len(roster)),
        "reserve_ids_preserved": bool(existing_reserve and final_ids[1] == prepared_ids[1]),
        "scope": scope,
    }


def main():
    if not __debug__:
        raise SystemExit("Run this proof without Python -O so assertions remain enabled.")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "roster", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    before, after, roster = (path.read_bytes() for path in
                            (args.before, args.after, args.roster))
    assert hashlib.sha256(before).hexdigest() == V04_SHA256, "requires exact v0.4 XBE"
    assert XbeImage(before).read(0x2BFA6E, 5) == bytes.fromhex("e83d871200")
    assert XbeImage(after).read(0x2BFA6E, 5) == bytes.fromhex("e88ddeffff")
    proof = {
        "inputs": {"v04_xbe": hashlib.sha256(before).hexdigest(),
                   "final_xbe": hashlib.sha256(after).hexdigest(),
                   "roster": hashlib.sha256(roster).hexdigest()},
        "stubs": {hex(address): description for address, description in STUBS.items()},
        "cases": [run_case(name, payload, roster, reserve) for name, payload, reserve in (
            ("v04_hidden_demotions", before, False),
            ("fixed_direct_cuts", after, False),
            ("fixed_preserves_existing_reserve", after, True),
        )],
        "limits": [
            "Actual x86 final-cut selection, release/demotion, ownership, stage setters, "
            "and save/load execute in Unicorn.",
            "Fixture setup chooses the final preseason boundary (stage 7/week 4), "
            "transfers real free agents to one real club up to 65 total owned players, "
            "and normalizes acquired contract length; ratings and identities come "
            "from the supplied roster.",
            "The five listed stubs exclude other franchise work. No Xbox boot, "
            "controller interaction, Week 1 game, or played witness is claimed.",
        ],
    }
    args.out.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print("PASS: three bounded native final-cuts timelines; receipt:", args.out)


if __name__ == "__main__":
    main()
