#!/usr/bin/env python3
"""Native franchise-event scenario for the Player Card TEAM column (job F3), runnable on any composed disc.

Maps a ``default.xbe`` into a Unicorn CPU, writes the ROST resource of ``vc_53450030/0`` next to it, relocates it with
the game's own ``FUN_000c0500`` and drives the game's own code:

* the history writer / reader (``FUN_0014f450`` / ``FUN_0014f430`` / ``FUN_0014ee20``),
* the real post-game loop ``FUN_00134dd0`` (the revision-2 hook sits at 0x134E0A),
* the real roster movers ``FUN_000c3eb0`` (remove) and ``FUN_000c3ee0`` (add),
* the real rollover player loops 0x247BDC..0x247CA8 (slot-count increment and the postseason wipe),
* the Player Card TEAM getter named by the column descriptor.

Only the in-game player-list iteration (``FUN_00061b60/70/90``), the per-player stat merge ``FUN_001334b0`` (its
effect, games += 1, is applied beforehand through the game's own writer) and the loading-bar update ``FUN_00177990``
are stubbed.  Actors are picked by rule from the roster (the first qualifying player of fixed clubs), so the same
script works on the retail 2004 roster and on the 2026 roster.

``--expect fixed`` (default) requires revision 2 behaviour; ``--expect legacy`` requires the revision-1 failure
signature (every current-season row ``--`` and nothing recorded), which is the cause this job removed.
No file is written unless ``--json`` is given.  Exit status 0 = every check holds.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from mod_editor.core import nfl2k5_team_column as tc  # noqa: E402

IMAGE_LO, IMAGE_HI = 0x10000, 0x1510000
MAIN, MAIN_SIZE = 0x2000000, 0x200000
STACK_TOP, STOP = 0x27F8000, 0x27FF000
FAKE = 0x2100000                                    # a stand-in for the in-game player / team objects
ROSTER_GLOBAL, CLASS_GLOBAL, STAGE_GLOBAL, MODE_GLOBAL = 0xB72918, 0xBD7F98, 0xE576A4, 0xE576A0
PLAYER_GLOBAL = 0xC90248
POST_LOOP_ENTRY, POST_LOOP_END = 0x134DD0, 0x134E1F
ROLLOVER_LOOPS = (0x247BDC, 0x247CA8)
BUDGET = 400_000_000
CLUB_CHOICES = {"trade_from": 3, "trade_to": 21, "release": 9, "ir": 28, "control": 5, "sign_to": 1}


class ScenarioError(RuntimeError):
    pass


class World:
    def __init__(self, xbe: bytes, rost_body: bytes) -> None:
        from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
        from unicorn import x86_const as regs

        self.R = regs
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc = self.uc
        uc.mem_map(IMAGE_LO, IMAGE_HI - IMAGE_LO)
        base = struct.unpack_from("<I", xbe, 0x104)[0]
        count = struct.unpack_from("<I", xbe, 0x11C)[0]
        table = struct.unpack_from("<I", xbe, 0x120)[0] - base
        for i in range(count):
            _flags, va, _vsize, raw, rawsize, _name = struct.unpack_from("<IIIIII", xbe, table + i * 0x38)
            if rawsize:
                if va + rawsize > IMAGE_HI:
                    raise ScenarioError("XBE section beyond the mapped window")
                uc.mem_write(va, xbe[raw: raw + rawsize])
        uc.mem_map(MAIN, MAIN_SIZE)
        uc.mem_map(STACK_TOP - 0x10000, 0x20000)
        self.stubs: dict[int, object] = {}
        uc.hook_add(UC_HOOK_CODE, self._hook)
        if len(rost_body) > MAIN_SIZE:
            raise ScenarioError("ROST body larger than the arena")
        self.wr(MAIN, rost_body)
        self.root = MAIN + 0x40
        self.w32(ROSTER_GLOBAL, self.root)
        self.call(0xC0500, ecx=self.root)               # the game's own relocation, in place
        self.w32(CLASS_GLOBAL, 0)
        self.w32(MODE_GLOBAL, 0)
        self.w32(STAGE_GLOBAL, 8)
        self.stub_return(0x177990, 0, pop=4)             # FUN_00177990 (loading-bar update) is `ret 4`
        for va in (0x61B60, 0x61B70, 0x61B90):
            self.stub_return(va, FAKE)
        self.stub_return(0x1334B0, 0, pop=8)
        self.players = self.u32(self.root)
        self.player_base = self.u32(self.root + 4)
        self.team_base = self.u32(self.root + 0x1C)
        self.team_count = self.u32(self.root + 0x18)

    # -- memory
    def rd(self, va: int, n: int) -> bytes:
        return bytes(self.uc.mem_read(va, n))

    def wr(self, va: int, data: bytes) -> None:
        self.uc.mem_write(va, bytes(data))

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.rd(va, 4))[0]

    def u8(self, va: int) -> int:
        return self.rd(va, 1)[0]

    def w32(self, va: int, value: int) -> None:
        self.wr(va, struct.pack("<I", value & 0xFFFFFFFF))

    def wstr(self, va: int, limit: int = 40) -> str:
        out = []
        for i in range(limit):
            ch = struct.unpack("<H", self.rd(va + 2 * i, 2))[0]
            if ch == 0:
                break
            out.append(chr(ch))
        return "".join(out)

    def reg(self, name: str) -> int:
        return self.uc.reg_read(getattr(self.R, "UC_X86_REG_" + name.upper()))

    # -- execution
    def _hook(self, _uc, address, _size, _user) -> None:
        stub = self.stubs.get(address)
        if stub is not None:
            stub()

    def stub_return(self, va: int, value: int = 0, pop: int = 0) -> None:
        def run() -> None:
            esp = self.reg("esp")
            self.uc.reg_write(self.R.UC_X86_REG_EAX, value)
            self.uc.reg_write(self.R.UC_X86_REG_EIP, self.u32(esp))
            self.uc.reg_write(self.R.UC_X86_REG_ESP, esp + 4 + pop)
        self.stubs[va] = run

    def _registers(self, **regs: int) -> None:
        for name in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
            self.uc.reg_write(getattr(self.R, "UC_X86_REG_" + name.upper()), regs.get(name, 0))

    def call(self, va: int, args: tuple[int, ...] = (), **regs: int) -> int:
        esp = STACK_TOP - 0x100 - 4 * len(args)
        for i, a in enumerate(args):
            self.w32(esp + 4 + 4 * i, a)
        self.w32(esp, STOP)
        self._registers(**regs)
        self.uc.reg_write(self.R.UC_X86_REG_ESP, esp)
        self.uc.emu_start(va, STOP, count=BUDGET)
        if self.reg("eip") != STOP:
            raise ScenarioError(f"call {va:#x} did not return (eip {self.reg('eip'):#x})")
        return self.reg("eax")

    def run_to(self, start: int, end: int, esp: int, **regs: int) -> None:
        self._registers(**regs)
        self.uc.reg_write(self.R.UC_X86_REG_ESP, esp)
        self.uc.emu_start(start, end, count=BUDGET)
        if self.reg("eip") != end:
            raise ScenarioError(f"{start:#x}..{end:#x} did not finish (eip {self.reg('eip'):#x}); instruction budget?")

    # -- roster
    def team(self, k: int) -> int:
        return self.team_base + k * 0x1F4

    def club_players(self, k: int) -> list[int]:
        return [self.u32(self.team(k) + 4 * j) for j in range(self.u8(self.team(k) + 0x11C))]

    def abbr(self, k: int) -> str:
        return self.wstr(self.u32(self.team(k) + 0x108))

    def slot(self, p: int) -> int:
        return (self.u32(p + 0x24) >> 8) & 0x1F

    def name(self, p: int) -> str:
        return f"{self.wstr(self.u32(p + 0x10))} {self.wstr(self.u32(p + 0x14))}".strip()

    def stream(self, p: int) -> list[int]:
        s = self.u32(p + 0x2C)
        out: list[int] = []
        if s == 0:
            return out
        while True:
            v = self.u32(s)
            out.append(v)
            s += 4
            if v & 0x80000000:
                break
        return out

    def field(self, p: int, field: int, slot: int):
        for v in self.stream(p):
            if (v >> 16) & 0x7F == field and (v >> 23) & 0x1F == slot and not v & 0x30000000:
                return v & 0xFFFF
        return None

    def getter(self, p: int, bank: int) -> str:
        self.w32(PLAYER_GLOBAL, p)
        return self.wstr(self.call(self.u32(tc.DESCRIPTOR_VA + 8), ecx=bank))   # the getter the descriptor names

    # -- franchise events
    def play(self, p: int) -> None:
        self.call(0x14F450, ecx=p, edx=0, args=(1,))        # games += 1, the game's own writer

    def game(self, k: int, who: list[int]) -> None:
        for p in who:
            self.play(p)
        block = FAKE + 0x1000
        self.wr(block, bytes(0x200))
        self.wr(block + 0x11C, bytes([self.u8(self.team(k) + 0x11C)]))
        esp = STACK_TOP - 0x200
        self.w32(esp, STOP)
        self.w32(esp + 4, 0)
        self.w32(esp + 8, 0)
        self.run_to(POST_LOOP_ENTRY, POST_LOOP_END, esp, eax=block, ecx=k)

    def move(self, p: int, src: int | None, dst: int | None) -> None:
        if src is not None and self.call(0xC3EB0, ecx=self.team(src), edx=p) == 0:
            raise ScenarioError("roster remove failed")
        if dst is not None and self.call(0xC3EE0, ecx=self.team(dst), edx=p) != 1:
            raise ScenarioError("roster add failed")

    def rollover(self) -> None:
        esp = STACK_TOP - 0x100
        self.w32(esp, STOP)
        self.w32(STAGE_GLOBAL, 9)
        self.run_to(ROLLOVER_LOOPS[0], ROLLOVER_LOOPS[1], esp)
        self.w32(STAGE_GLOBAL, 1)


def _rost_body(path: Path) -> bytes:
    """The main ROST body from a loose resource (32-byte wrapper + body) or bare body file, a loose pack folder
    (``<dir>/vc_53450030/``) or a disc image."""

    from mod_editor.core import nfl2k5_team_history as history

    if path.is_file() and path.stat().st_size in (history.RESOURCE_SIZE, history.BODY_SIZE):
        data = path.read_bytes()
        return data[history.RESOURCE_HEADER_SIZE:] if len(data) == history.RESOURCE_SIZE else data
    with history._outer_image()(path) as archive:
        entry = history._entry(archive)
        return archive.read(entry.virtual_offset, entry.size)[history.RESOURCE_HEADER_SIZE:]


def run_scenario(xbe: bytes, rost_body: bytes, *, rollover: bool = True) -> dict:
    w = World(xbe, rost_body)
    nonzero = sum(1 for i in range(w.players) if w.u32(w.player_base + i * 0x54 + 0x30))
    members: dict[int, int] = {}
    for k in range(34):
        for p in w.club_players(k):
            members.setdefault(p, k)

    def eligible(p: int) -> bool:        # has a finished season with a games entry, so bank 12 shows a baked row
        return w.slot(p) >= 2 and w.field(p, 0, w.slot(p) - 1) is not None
    def pick(k: int) -> int:
        for p in w.club_players(k):
            if eligible(p):
                return p
        raise ScenarioError(f"no qualifying player on club {k}")
    c = CLUB_CHOICES
    actors = {"trade": pick(c["trade_from"]), "release": pick(c["release"]), "ir": pick(c["ir"]), "control": pick(c["control"])}
    free = [w.player_base + i * 0x54 for i in range(w.players) if (w.player_base + i * 0x54) not in members
            and w.u8(w.player_base + i * 0x54 + 0x35) < 17 and eligible(w.player_base + i * 0x54)]
    if not free:
        raise ScenarioError("no free agent with a finished season")
    actors["sign"] = free[0]
    homes = {"trade": c["trade_from"], "release": c["release"], "ir": c["ir"], "control": c["control"]}
    clubs = sorted({c["trade_from"], c["trade_to"], c["release"], c["ir"], c["control"], c["sign_to"]})
    rows: list[dict] = []

    def snap(label: str) -> None:
        row = {"step": label}
        for n, p in actors.items():
            cur = w.field(p, tc.TEAM_FIELD, w.slot(p))
            row[n] = {"bank11": w.getter(p, 11), "bank12": w.getter(p, 12),
                      "recorded_current": w.abbr(cur - 1) if cur else None}
        rows.append(row)

    def week() -> None:
        for k in clubs:
            roster = w.club_players(k)
            who = [p for p in roster if p in actors.values()] + roster[:6]
            w.game(k, list(dict.fromkeys(who)))

    pool0 = w.u32(w.root + 0x40)
    snap("before any game")
    week(); week()
    snap("after week 2")
    w.move(actors["trade"], c["trade_from"], c["trade_to"])
    snap("traded, before he plays for the new club")
    week(); week()
    snap("after two games for the new club")
    w.move(actors["sign"], None, c["sign_to"])
    week(); week()
    snap("free agent signed and played two games")
    w.move(actors["release"], c["release"], None)
    w.move(actors["ir"], c["ir"], None)
    for _ in range(3):
        week()
    snap("released and injured reserve (outside every club array), more games")
    pool_before_rollover = w.u32(w.root + 0x40)
    counts_before = {n: w.slot(p) for n, p in actors.items()}
    if rollover:
        w.rollover()
        snap("after the rollover (offseason)")
        w.move(actors["trade"], c["trade_to"], c["trade_from"])
        snap("offseason trade back")
    after = {n: w.slot(p) for n, p in actors.items()}
    return {"actors": {n: {"name": w.name(p), "home": w.abbr(members[p]) if p in members else "FA"} for n, p in actors.items()},
            "clubs": {k: w.abbr(k) for k in range(34)}, "plus_0x30_nonzero_records": nonzero, "players": w.players,
            "rows": rows, "pool_before": pool0, "pool_before_rollover": pool_before_rollover,
            "pool_after": w.u32(w.root + 0x40), "slot_counts_before_rollover": counts_before, "slot_counts_after": after,
            "club_choices": c}


def check(result: dict, expect: str) -> list[str]:
    """The expectation per step; returns the list of failed checks."""

    bad: list[str] = []
    rows = {r["step"]: r for r in result["rows"]}
    c = result["club_choices"]
    clubs = result["clubs"]
    name = lambda k: clubs[k] if isinstance(k, int) else clubs[str(k)]      # noqa: E731
    if result["plus_0x30_nonzero_records"]:
        bad.append(f"player+0x30 is non-zero for {result['plus_0x30_nonzero_records']} records")
    if expect == "legacy":
        for r in result["rows"]:
            for n in ("trade", "release", "ir", "control", "sign"):
                if r[n]["bank11"] != "--" or r[n]["recorded_current"] is not None:
                    bad.append(f"{r['step']}: {n} is not the revision-1 failure signature ({r[n]})")
        return bad
    expect_cells = [
        ("before any game", "control", "bank11", name(c["control"])),
        ("before any game", "trade", "bank11", name(c["trade_from"])),
        ("after week 2", "trade", "recorded_current", name(c["trade_from"])),
        ("traded, before he plays for the new club", "trade", "bank11", name(c["trade_to"])),
        ("traded, before he plays for the new club", "trade", "recorded_current", name(c["trade_from"])),
        ("after two games for the new club", "trade", "recorded_current", name(c["trade_to"])),
        ("free agent signed and played two games", "sign", "bank11", name(c["sign_to"])),
        ("free agent signed and played two games", "sign", "recorded_current", name(c["sign_to"])),
        ("released and injured reserve (outside every club array), more games", "release", "bank11", name(c["release"])),
        ("released and injured reserve (outside every club array), more games", "ir", "bank11", name(c["ir"])),
        ("released and injured reserve (outside every club array), more games", "trade", "bank11", name(c["trade_to"])),
    ]
    if "after the rollover (offseason)" in rows:
        expect_cells += [
            ("after the rollover (offseason)", "trade", "bank12", name(c["trade_to"])),
            ("after the rollover (offseason)", "release", "bank12", name(c["release"])),
            ("after the rollover (offseason)", "ir", "bank12", name(c["ir"])),
            ("after the rollover (offseason)", "control", "bank12", name(c["control"])),
            ("after the rollover (offseason)", "sign", "bank12", name(c["sign_to"])),
            ("offseason trade back", "trade", "bank11", name(c["trade_from"])),
            ("offseason trade back", "trade", "bank12", name(c["trade_to"])),
        ]
    for step, who, cell, want in expect_cells:
        got = rows[step][who][cell]
        if got != want:
            bad.append(f"{step}: {who} {cell} = {got!r}, wanted {want!r}")
    if "after the rollover (offseason)" in rows:
        if result["pool_after"] != result["pool_before_rollover"]:
            bad.append(f"the rollover changed the pool ({result['pool_before_rollover']} -> {result['pool_after']})")
        for n, count in result["slot_counts_before_rollover"].items():
            if result["slot_counts_after"][n] != count + 1:
                bad.append(f"{n}: slot count {count} -> {result['slot_counts_after'][n]}, wanted +1")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xbe", type=Path, required=True, help="extracted default.xbe")
    ap.add_argument("--rost", type=Path, required=True,
                    help="the ROST resource (32-byte wrapper + body), a loose pack-0 folder/file, or a disc image")
    ap.add_argument("--expect", choices=("fixed", "legacy"), default="fixed")
    ap.add_argument("--no-rollover", action="store_true")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    fd = os.open(args.xbe, flags)
    with os.fdopen(fd, "rb") as handle:
        xbe = handle.read(16 * 1024 * 1024 + 1)
    result = run_scenario(xbe, _rost_body(args.rost), rollover=not args.no_rollover)
    failures = check(result, args.expect)
    result["expect"] = args.expect
    result["failures"] = failures
    result["team_column_status"] = tc.status(xbe)
    result["team_column_revision"] = tc.revision(xbe)
    for row in result["rows"]:
        print(f"{row['step']:<72s}", {n: (row[n]["bank11"], row[n]["bank12"], row[n]["recorded_current"]) for n in ("trade", "release", "ir", "control", "sign")})
    print("actors:", result["actors"])
    print("pool:", result["pool_before"], "->", result["pool_before_rollover"], "->", result["pool_after"])
    print("FAIL" if failures else "OK", *failures, sep="\n  " if failures else " ")
    if args.json:
        with args.json.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
