#!/usr/bin/env python3
"""Native route execution check for offense designs (beta 77, job p6s). Read only, writes only --out.

Every receiver route (WR, TE, back) of a pass play is traced with the game's own route initializer (``0x229AE0``,
the real retail ``default.xbe`` under Unicorn via ``tools/nfl2k5_back_throws_replay.NativeMachine``; the trace setup
follows ``tools/b765/d2b_route_probe``) from the formation's real alignment, giving the native lookahead path and its
times. The tracer resolves in and out as a right-side receiver does, so a left-side receiver is traced from the mirrored
spot and mirrored back (the game mirrors routes by side; ``codec.play_art`` does the same).

Flags per play:
  COLLIDE   two receivers within 0.8 yd of each other at the same moment, 0.6 to 3.0 s after the snap
  STACK     two receivers still within 1.5 yd of each other 2.8 and 3.2 s after the snap (one landmark, two men)
  OOB       a lookahead point beyond the sideline (|x| > 26.7 yd)
  BEHIND    a WR or TE route that ends behind the line (flats from an off-ball slot, screens; information only,
            the p13 linter owns backward-pass risk)
Pairs that involve a back carry a ``_BACK`` suffix: the back's side in the trace fixture is the least certain part.

    python3 tools/b77/p6s_route_check.py concepts [--concepts Mesh,Stick] [--formations "Gun Trips"] --out out.json
    python3 tools/b77/p6s_route_check.py books BOOK.play [BOOK.play ...] --out out.json

PROVED OFFLINE (native route code on fixtures); gameplay unwitnessed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core.nfl2k5_complete_offense import ordinary_indices  # noqa: E402

YD = 91.44
ROLE = {lib.HB: 1, lib.FB: 2, lib.WR: 3, lib.TE: 4}


def machine(xbe: Path | None = None):
    from tools.nfl2k5_back_throws_replay import NativeMachine, DEFAULT_XBE, read_retail
    return NativeMachine(read_retail(xbe or DEFAULT_XBE))


def trace(m, nodes: list, x_cm: float, z_cm: float, kind: int, active: int) -> list[tuple[float, float, float]]:
    """Native lookahead records (t s, x yd, z yd) of the route node ``active`` from (x, z)."""
    sign = -1.0 if x_cm < 0 else 1.0
    x_cm = abs(x_cm)
    m.call(0x1A8BC0, ecx=0x521078)
    state, descriptor, chain_addr = m.P + 0x600, m.P + 0x1900, m.P + 0x1910
    m.uc.mem_write(state, bytes(0x600))
    m.uc.mem_write(m.TEAM + 0x300, bytes(0x100))
    m.put(descriptor, len(nodes) | (0x1 << 4) | (0x10 << 8) | (0xB1 << 16))
    m.put(descriptor + 4, chain_addr)
    m.uc.mem_write(chain_addr, b"".join(n.to_bytes() for n in nodes))
    m.put(state + 0x41C, descriptor)
    m.uc.mem_write(state + 0x450, bytes([active]))
    m.put(state + 0x300, state + 0x240)
    m.put(state + 0x310, state - 0xB0)
    m.put(m.P + 0x24, m.P + 0x1A00)
    m.put(m.TEAM + 0xC, m.TEAM + 0x300)
    form = bytearray(0xB4)
    struct.pack_into("<I", form, 4, 0x00140000 | (1 << 8))
    r = 0x1A + 14 * 7
    form[r + 1] = 0xB3
    struct.pack_into("<hhh", form, r + 2, *([int(round(x_cm))] * 3))
    struct.pack_into("<hhh", form, r + 8, *([int(round(z_cm))] * 3))
    m.uc.mem_write(m.P + 0x1B00, bytes(form))
    m.put(m.TEAM + 0x34C, m.P + 0x1B00)
    m.f(m.P + 0x390, 0.8)
    for k, value in enumerate(nodes[active].operands):
        m.f(state + 0x430 + k * 4, float(value))
    m.put(state + 0x420, 0x20000 if nodes[active].flags & 2 else 0)
    m.put(0xE602B8, 14)
    m.put(0xE602B4, 4)
    slot = 7
    m.uc.mem_write(m.P + 0x2E, bytes([slot]))
    m.uc.mem_write(0xBDFCD0 + slot * 2, bytes([0]))
    m.uc.mem_write(m.P + 0x2C, bytes([ROLE[kind]]))
    m.uc.mem_write(m.P + 0x1035, bytes([ROLE[kind]]))
    m.f(m.TEAM + 0x204, 1.0)
    m.vec(m.P + 0x530, (float(x_cm), 0.0, float(z_cm), 1.0))
    m.vec(m.P + 0x540, (0.0, 0.0, 0.0, 0.0))
    m.vec(m.CTX + 0x10, (0.0, 0.0, 0.0, 1.0))
    m.uc.mem_write(0xC16590, bytes(0x98))
    m.put(0xE5FC00, 0)
    m.f(m.CLOCK + 0x10, 1.0)
    m.counts.clear()
    m.call(0x229AE0, ecx=m.P, count=200000)
    table = bytes(m.uc.mem_read(0xC16590, 0x98))
    out = []
    for offset in range(12, 12 + 8 * 16, 16):
        t, xx, zz, _flags = struct.unpack_from("<3fI", table, offset)
        if t > 0:
            out.append((round(t, 3), round(sign * xx / YD, 2), round(zz / YD, 2)))
    return out


def at(path, t):
    if t <= path[0][0]:
        return path[0][1:]
    for (t0, x0, z0), (t1, x1, z1) in zip(path, path[1:]):
        if t <= t1:
            a = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return (x0 + a * (x1 - x0), z0 + a * (z1 - z0))
    return path[-1][1:]


def check_rows(m, cache: dict, rows) -> list:
    """rows: [(slot, kind, x cm, z cm, nodes)] of one play -> flags."""
    paths = []
    for slot, kind, x, z, nodes in rows:
        if kind not in ROLE:
            continue
        idx = next((i for i, n in enumerate(nodes) if n.op == 0x12), None)
        if idx is None or any(n.op == 0x12 and int(n.operands[0]) == 9 for n in nodes):
            continue                                   # blockers and screen blocks
        key = (b"".join(n.to_bytes() for n in nodes), x, z, kind)
        if key not in cache:
            try:
                cache[key] = trace(m, nodes, x, z, kind, idx)
            except Exception:  # noqa: BLE001 - a route the fixture cannot run is reported, not fatal
                cache[key] = None
        if cache[key]:
            paths.append((slot, kind, cache[key]))
    found = []
    for slot, kind, p in paths:
        if any(abs(xx) > 26.7 for _, xx, _ in p):
            found.append(("OOB", slot))
        if kind in (lib.WR, lib.TE) and p[-1][2] < 0:
            found.append(("BEHIND", slot))
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            (si, ki, pi), (sj, kj, pj) = paths[i], paths[j]
            back = "_BACK" if {ki, kj} & {lib.HB, lib.FB} else ""
            closest = min(math.hypot(at(pi, t)[0] - at(pj, t)[0], at(pi, t)[1] - at(pj, t)[1])
                          for t in [1.6 + 0.1 * k for k in range(25)])
            if closest < 0.8:
                found.append(("COLLIDE" + back, (si, sj), round(closest, 2)))
            if all(math.hypot(at(pi, t)[0] - at(pj, t)[0], at(pi, t)[1] - at(pj, t)[1]) < 1.5 for t in (3.8, 4.2)):
                found.append(("STACK" + back, (si, sj)))
    return found


def design_rows(spec, d):
    ctx, pos = spec.context(), spec.positions_cm()
    return [(s, ctx.player(s).kind, pos[s][0], pos[s][1], codec.encode_chain(d.chains[s])) for s in range(11)]


def book_rows(raw: bytes):
    book = insp.parse_playbook_resource(raw)
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    fs, ps = ordinary_indices(book, body)
    for f in book.formations:
        if f.index not in fs:
            continue
        rec = lib.formation_record(body, f.index)
        codes = lib.category_positions(body, lib.formation_category(body, f.index))
        for link in f.play_links:
            if link.play_index not in ps:
                continue
            flags, chains = lib.play_chains(body, link.play_index)
            if flags & 0x8000:
                continue
            rows = [(s, codes[s] & 31, rec.slots[s].x[0], rec.slots[s].z[0],
                     [codec.Node.from_bytes(n) for n in chains[s][1]]) for s in range(11)]
            yield f.name.strip(), book.plays[link.play_index].name.strip(), rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("concepts")
    c.add_argument("--concepts", default="")
    c.add_argument("--formations", default="")
    c.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("books")
    b.add_argument("books", nargs="+", type=Path)
    b.add_argument("--out", type=Path, required=True)
    for p in (c, b):
        p.add_argument("--xbe", type=Path, help="retail default.xbe (default: the tools' retail extraction)")
    args = ap.parse_args(argv)
    m, cache, out = machine(args.xbe), {}, []
    if args.cmd == "concepts":
        names = [n for n in args.concepts.split(",") if n] or [n for n, cd in oc.CONCEPTS.items() if cd.family not in ("run", "trick")]
        forms = [f for f in args.formations.split(",") if f] or list(oc.FORMATIONS)
        for name in names:
            tally = Counter()
            for fname in forms:
                spec = oc.FORMATIONS[fname]
                try:
                    d = oc.design(name, spec.context())
                except oc.ConceptUnavailable:
                    continue
                found = check_rows(m, cache, design_rows(spec, d))
                tally.update({x[0] for x in found})
                out.append(dict(concept=name, formation=fname, flags=[[str(v) for v in x] for x in found]))
            print(f"{name:16s} {dict(tally)}", flush=True)
    else:
        for path in args.books:
            tally, plays = Counter(), 0
            for fname, pname, rows in book_rows(path.read_bytes()):
                plays += 1
                found = check_rows(m, cache, rows)
                tally.update({x[0] for x in found})
                if found:
                    out.append(dict(book=path.name, formation=fname, play=pname, flags=[[str(v) for v in x] for x in found]))
            print(f"{path.name}: {plays} pass plays in menus, flags {dict(tally)}", flush=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
