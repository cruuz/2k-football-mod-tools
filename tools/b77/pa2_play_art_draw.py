#!/usr/bin/env python3
"""b776 pa2: run the game's own play-art draw path on a real play and return its draw list.

Unicorn executes the executable's setup FUN_001807F0 and the per-slot drawer FUN_00182480 (chain
drawer 0x181940, art filter 0x1812A0, opcode draw callbacks) for one formation and play of a PLAY
book, and records every immediate-mode primitive (begin 0x2D2A0, vertex 0x2CB50, end 0x2CA00) in
world centimetres (x across, z downfield from the ball). Block marks of route kinds 8/9 are model
instances (0x164E80 / 0x164DD0): recorded as a point, not submitted. A slot that reaches an
unstubbed named-model marker stops there and is reported in ``errors``. Read only; offline proof
tool, not a build step. Unicorn is an optional dependency.

    python3 tools/b77/pa2_play_art_draw.py --xbe default.xbe --book CHI.play --formation "I-Form Pro" --play "Flea Flicker"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as inspector, nfl2k5_play_library as lib  # noqa: E402

HEAP, STACK, STOP = 0x6000000, 0x7000000, 0x7100000
# Calibrated play-call panel (b775 frame, 1080p): px per cm across / deep, panel size, LOS row.
PANEL = dict(sx=0.192, sz=0.1149, width=410, height=243, los_y=148)


def inside_panel(x: float, z: float) -> bool:
    px = PANEL["width"] / 2 - x * PANEL["sx"]
    py = PANEL["los_y"] - z * PANEL["sz"]
    return 0 <= px <= PANEL["width"] and 0 <= py <= PANEL["height"]


class Machine:
    def __init__(self, xbe: bytes):
        import unicorn as U
        from unicorn import x86_const as X
        self.U, self.X = U, X
        image = XbeImage(xbe)
        self.uc = U.Uc(U.UC_ARCH_X86, U.UC_MODE_32)
        top = max(s.end for s in image.sections)
        self.uc.mem_map(image.base, ((top - image.base) + 0xFFFF) & ~0xFFF)
        self.uc.mem_write(image.base, xbe[:image.headers_size])
        for s in image.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, xbe[s.raw:s.raw + min(s.raw_size, s.size)])
        self.uc.mem_map(HEAP, 0x400000)
        self.uc.mem_map(STACK, 0x40000)
        self.uc.mem_map(STOP, 0x1000)
        self.uc.mem_write(STOP, b"\xf4")
        self.cursor = HEAP
        self.put(0xBE4E20, 0x521078)  # runtime opcode-table pointer (the game sets it at load)
        for va in range(0xBD92D0, 0xBD9310, 4):  # marker sprite objects: scratch, their submit is skipped
            self.put(va, self.alloc(0x100))
        self.scratch = self.alloc(0x400)
        self.prims, self.cur = [], None
        hook = lambda va, fn: self.uc.hook_add(U.UC_HOOK_CODE, fn, begin=va, end=va)
        hook(0x164910, lambda *a: self._ret(8))
        hook(0x21970, self._matrix)
        hook(0x164E80, lambda *a: self._mark(0xC))
        hook(0x164DD0, lambda *a: self._mark(0))
        hook(0x2D2A0, self._begin)
        hook(0x2CB50, self._vertex)
        hook(0x2CA00, self._end)

    def _ret(self, n):
        X = self.X
        esp = self.uc.reg_read(X.UC_X86_REG_ESP)
        self.uc.reg_write(X.UC_X86_REG_EIP, self.get(esp))
        self.uc.reg_write(X.UC_X86_REG_ESP, esp + 4 + n)

    def _args(self, n):
        return self.uc.mem_read(self.uc.reg_read(self.X.UC_X86_REG_ESP) + 4, 4 * n)

    def _row(self, kind):
        return {"kind": kind, "shadow": self.get(0xBDFC18), "slot": self.get(0xBDFC5C),
                "node": self.get(0xBDFC50), "v": []}

    def _begin(self, *a):
        self.cur = self._row(struct.unpack("<I", self._args(1))[0])
        self._ret(0xC)

    def _vertex(self, *a):
        if self.cur is not None:
            self.cur["v"].append(struct.unpack("<3f", self._args(3)))
        self._ret(0xC)

    def _end(self, *a):
        if self.cur is not None:
            self.prims.append(self.cur)
        self.cur = None
        self._ret(0)

    def _mark(self, n):
        row = self._row("mark")
        row["v"].append(struct.unpack("<3f", self.uc.mem_read(self.uc.reg_read(self.X.UC_X86_REG_ECX), 12)))
        self.prims.append(row)
        self._ret(n)

    def _matrix(self, *a):
        ecx = self.uc.reg_read(self.X.UC_X86_REG_ECX)
        value = self.get(ecx + 0x14) if ecx >= 0x10000 else 0
        self.uc.reg_write(self.X.UC_X86_REG_EAX, value or self.scratch)
        self._ret(0)

    def alloc(self, n):
        at = (self.cursor + 15) & ~15
        self.cursor = at + n
        return at

    def put(self, va, v):
        self.uc.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def call(self, va, args=(), **regs):
        X = self.X
        stack = struct.pack("<I", STOP) + b"".join(struct.pack("<I", a & 0xFFFFFFFF) for a in args)
        esp = STACK + 0x30000 - len(stack)
        self.uc.mem_write(esp, stack)
        self.uc.reg_write(X.UC_X86_REG_ESP, esp)
        self.uc.reg_write(X.UC_X86_REG_EBP, 0)
        for r in ("eax", "ebx", "ecx", "edx", "esi", "edi"):
            self.uc.reg_write(getattr(X, "UC_X86_REG_" + r.upper()), regs.get(r, 0) & 0xFFFFFFFF)
        self.uc.emu_start(va, STOP, count=5_000_000)


def find_play(book, formation_name, play_name):
    for f in book.formations:
        if f.name.strip() == formation_name:
            for link in f.play_links:
                if book.plays[link.play_index].name.strip() == play_name:
                    return f.index, link.play_index
    raise KeyError(f"{formation_name} / {play_name}")


def _name(m, body, field):
    """Copy a self-relative UTF-16 name into the machine; return its address."""
    start = field - 1 + struct.unpack_from("<i", body, field)[0]
    end = start
    while body[end:end + 2] != b"\0\0":
        end += 2
    va = m.alloc(end - start + 2)
    m.uc.mem_write(va, body[start:end + 2])
    return va


def draw(xbe: bytes, book_raw: bytes, formation_index: int, play_index: int, *, flip: int = 0) -> dict:
    """The play's draw list on the play-call diagram path (context 0, quantized columns, ball at 0)."""
    body = book_raw[32:]
    m = Machine(xbe)
    fo = lib.FORMATION_BASE + formation_index * lib.FORMATION_SIZE
    form = m.alloc(0x100)
    m.uc.mem_write(form, body[fo:fo + lib.FORMATION_SIZE])
    m.put(form, _name(m, body, fo))  # the loader relocates the self-relative name (the art reads it by name)
    co = lib.CATEGORY_BASE + lib.formation_category(body, formation_index) * lib.CATEGORY_SIZE
    cat = m.alloc(0x20)
    m.uc.mem_write(cat, body[co:co + lib.CATEGORY_SIZE])
    flags, chains = lib.play_chains(body, play_index)
    play = m.alloc(0x100)
    m.put(play + 4, flags)
    for slot, (desc, nodes) in enumerate(chains):
        nodes_va = m.alloc(8 * len(nodes) + 8)
        m.uc.mem_write(nodes_va, b"".join(nodes))
        m.put(play + 8 + slot * 8, desc)
        m.put(play + 12 + slot * 8, nodes_va)
    origin = m.alloc(16)
    m.uc.mem_write(origin, struct.pack("<4f", 0, 0, 0, 1))
    m.call(0x1807F0, (origin, 1, 1), ecx=0, edx=flip)
    errors = []
    for slot in range(11):
        try:
            m.call(0x182480, (0, cat, form, 0, 0), ecx=slot, edx=play)
        except m.U.UcError as exc:
            errors.append(dict(slot=slot, node=m.get(0xBDFC50), error=str(exc)))
            m.cur = None
    return dict(prims=m.prims, chains=chains, errors=errors)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--book", type=Path, required=True, help="a team PLAY resource (raw .play bytes)")
    parser.add_argument("--formation", required=True)
    parser.add_argument("--play", required=True)
    parser.add_argument("--flip", type=int, default=0)
    args = parser.parse_args(argv)
    raw = args.book.read_bytes()
    fi, pi = find_play(inspector.parse_playbook_resource(raw), args.formation, args.play)
    result = draw(args.xbe.read_bytes(), raw, fi, pi, flip=args.flip)
    print(json.dumps(dict(prims=result["prims"], errors=result["errors"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
