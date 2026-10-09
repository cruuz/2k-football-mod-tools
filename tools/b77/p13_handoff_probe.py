#!/usr/bin/env python3
"""Native handoff exchange probe: the game's own Take Handoff / Handoff To code on real plays.

Executes, unmodified, the Take Handoff initializer 0x2E41F0, the Handoff To
initializer 0x300B00 (which runs the exchange planner 0x2FFDD0) and, in the
closed loop, the per-frame callbacks they install (0x2E4030 receiver, 0x300810 /
0x2FFD00 QB). Actor objects, the team list, the play context (formation record
and play record) and the ball holder are supplied fixtures built from the real
formation positions and assignment chains. In the closed loop, the one supplied
mechanism is locomotion: each frame the movement request the native code writes
(action block +0x10 speed factor, +0x14 heading) is integrated with the native
speed curve 0x238020 and a 10 yd/s^2 acceleration cap. Animations, contact and
defenders are not emulated; no gameplay witness is claimed.

Use ``plan`` for the exchange plan (meeting point and how far each player must
travel) and ``simulate`` for the time and separation at which the native sync
gate releases the exchange.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "tools")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from tools.nfl2k5_back_throws_replay import NativeMachine, x86, uc_module  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402

YD = codec.YD_CM
ACTORS = 0x2200000
ACTOR_SIZE = 0x4000
TAKE_INIT, GIVE_INIT = 0x2E41F0, 0x300B00
SPEED_CURVE, ATAN2 = 0x238020, 0x0210B0
ROLE_BYTES = {lib.QB: 0, lib.HB: 1, lib.FB: 2, lib.WR: 3, lib.TE: 4}


class HandoffMachine(NativeMachine):
    """NativeMachine plus eleven offensive actor fixtures for one formation-play pairing."""

    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.uc.mem_map(ACTORS, 0x100000)
        self.faults: list = []

        def unmapped(uc, access, address, size, value, user):
            self.faults.append((hex(uc.reg_read(x86.UC_X86_REG_EIP)), hex(address)))
            return False

        self.uc.hook_add(uc_module.UC_HOOK_MEM_UNMAPPED, unmapped)
        self.call(0x1A8BC0, ecx=0x521078)        # native opcode metadata setter, as d2b's probe
        self.nodes: list[list[codec.Node]] = []

    @staticmethod
    def actor(slot: int) -> int:
        return ACTORS + slot * ACTOR_SIZE

    def build(self, view: lint.PlayView, *, human_slot: int | None = None, rating: float = .8) -> None:
        team, ctx = self.TEAM, self.TEAM + 0x1000
        form, record = self.TEAM + 0x1100, self.TEAM + 0x1200
        self.put(team + 4, self.actor(0))
        self.put(team + 0xC, ctx)
        self.put(ctx + 0x24, 0)                   # unflipped play-select word
        self.uc.mem_write(0xBDFC10, struct.pack("<I", 0))
        slots = [codec.FormationSlot(0, codec.NO_MIRROR, 1, [int(x)] * 3, [int(z)] * 3) for x, z in view.positions]
        fr = codec.FormationRecord(0, 0x40100, bytes(5), bytes(range(11)), 0, slots)
        self.uc.mem_write(form, fr.to_bytes())
        self.put(ctx + 8, form)
        self.uc.mem_write(record, bytes(0x60))
        self.put(record + 4, view.play_flags)
        self.put(ctx + 0xC, record)
        raw = [[n.to_bytes() for n in chain] for chain in view.chains]
        assignments = [(len(r), r) for r in raw]
        descriptors = [codec.build_descriptor(view.play_flags, assignments, s, 0) for s in range(11)]
        self.f(self.CTX + 0x10, 0.); self.f(self.CTX + 0x14, 0.); self.f(self.CTX + 0x18, 0.); self.f(self.CTX + 0x1C, 1.)
        self.f(team + 0x204, 1.)
        self.put(0xE602B8, 0xE)                   # live-play phase
        self.nodes = [list(chain) for chain in view.chains]
        for s in range(11):
            a = self.actor(s)
            self.uc.mem_write(a, bytes(ACTOR_SIZE))
            ctl, anim, desc, body, state = a + 0x400, a + 0x500, a + 0x700, a + 0x800, a + 0x900
            m24, m3c, chain, skel = a + 0x1000, a + 0x1100, a + 0x1200, a + 0x1300
            for off, ptr in ((0xC, ctl), (0x10, anim), (0x14, skel), (0x18, body), (0x20, state),
                             (0x24, m24), (0x38, team), (0x3C, m3c)):
                self.put(a + off, ptr)
            self.put(a + 0x34, self.actor(s + 1) if s < 10 else 0)
            self.put(a, 1 if human_slot == s else 0)
            self.uc.mem_write(a + 0x2C, bytes([ROLE_BYTES.get(view.codes[s] & 31, 5)]))
            self.uc.mem_write(a + 0x2E, bytes([s]))
            self.put(ctl, 0 if human_slot == s else 0xFFFFFFFF)
            self.put(anim + 4, desc); self.put(desc, 0x01000000)      # idle/locomotion class
            self.f(anim + 0x1B4, rating)
            self.put(skel + 0x34, skel + 0x40); self.vec(skel + 0x40, (0., 0., 0., 1.))
            self.put(skel + 0x74, skel + 0x80); self.f(skel + 0x88, 1.); self.put(skel + 0x80, skel + 0xA0)
            self.f(skel + 0xB8, 1.)
            x, z = view.positions[s]
            self.vec(body + 0x30, (float(x), 0., float(z), 1.)); self.vec(body + 0x40, (0., 0., 0., 0.))
            self.put(body + 0x50, 0)
            self.put(state + 0x300, state + 0x240); self.put(state + 0x310, state - 0xB0)
            self.put(chain, descriptors[s]); self.put(chain + 4, chain + 0x10)
            self.uc.mem_write(chain + 0x10, b"".join(raw[s]))
            self.put(state + 0x41C, chain)
            self.put(record + 8 + s * 8, descriptors[s]); self.put(record + 0xC + s * 8, chain + 0x10)

    def set_node(self, slot: int, index: int) -> None:
        state = self.get(self.actor(slot) + 0x20)
        nodes = self.nodes[slot]
        self.uc.mem_write(state + 0x450, bytes([index & 0xFF]))
        for k, value in enumerate(nodes[index].operands):
            self.f(state + 0x430 + k * 4, float(value))
        flags = self.get(state + 0x420) & ~0x20000
        self.put(state + 0x420, flags | (0x20000 if index == len(nodes) - 1 else 0))

    def task(self, slot: int) -> int:
        return self.get(self.get(self.actor(slot) + 0x20) + 0x310)

    def position(self, slot: int) -> tuple[float, float]:
        body = self.get(self.actor(slot) + 0x18)
        x, _, z, _ = struct.unpack("<4f", self.uc.mem_read(body + 0x30, 16))
        return x, z

    def invoke(self, address: int, slot: int, count: int = 2_000_000) -> None:
        self.faults.clear()
        self.call(address, ecx=self.actor(slot), count=count, timeout_us=60_000_000)

    def _start(self, giver: int, target: int, snap_time: float) -> None:
        take = next(i for i, n in enumerate(self.nodes[target]) if n.op == 0x16)
        g = self.actor(giver)
        self.put(0xE5FC00, self.BALL); self.put(self.BALL, g); self.put(g + 0x1C, 1)
        self.f(self.CLOCK + 0x10, 0.)
        self.set_node(target, take)
        self.invoke(TAKE_INIT, target)
        self._snap_time = snap_time
        self._give_index = next(i for i, n in enumerate(self.nodes[giver]) if n.op == 0x13)

    def _give(self, giver: int) -> None:
        self.f(self.CLOCK + 0x10, self._snap_time)
        self.set_node(giver, self._give_index)
        self.invoke(GIVE_INIT, giver)


def snap_time_for(view: lint.PlayView, giver: int) -> float:
    """Time the giver reaches his Handoff To node: a QB still has to receive the snap."""
    if view.kinds[giver] != lib.QB:
        return .25
    return .45 if view.positions[giver][1] < codec.SHOTGUN_DEPTH_THRESHOLD_CM else .25


def plan(machine: HandoffMachine, view: lint.PlayView, giver: int, target: int) -> dict:
    """Native exchange plan from the formation alignment (no movement before the giver's node)."""
    machine.build(view)
    machine._start(giver, target, snap_time_for(view, giver))
    machine._give(giver)
    tg, tt = machine.task(giver), machine.task(target)
    (gx, gz), (tx, tz) = machine.position(giver), machine.position(target)
    goal_g = (machine.rf(tg + 0x20), machine.rf(tg + 0x28))
    goal_t = (machine.rf(tt + 0x20), machine.rf(tt + 0x28))
    return dict(snap_separation_yd=round(math.hypot(gx - tx, gz - tz) / YD, 2),
                giver_travel_yd=round(math.hypot(goal_g[0] - gx, goal_g[1] - gz) / YD, 2),
                target_travel_yd=round(math.hypot(goal_t[0] - tx, goal_t[1] - tz) / YD, 2),
                giver_goal_cm=[round(v, 1) for v in goal_g], target_goal_cm=[round(v, 1) for v in goal_t],
                giver_callback=hex(machine.get(tg)), receiver_callback=hex(machine.get(tt)),
                planner_mode=machine.get(tg + 0xB0))


def simulate(machine: HandoffMachine, view: lint.PlayView, giver: int, target: int, *,
             frames: int = 240, human_giver: bool = False, freeze_giver: bool = False,
             accel_yd_s2: float = 10.0) -> dict:
    """Closed loop: native per-frame callbacks, supplied kinematic integration of their movement requests."""
    machine.build(view, human_slot=giver if human_giver else None)
    snap = snap_time_for(view, giver)
    machine._start(giver, target, snap)
    dt, given = 1 / 60., False
    velocity = {giver: [0., 0.], target: [0., 0.]}
    events, track = [], []
    for frame in range(frames):
        t = frame * dt
        machine.f(machine.CLOCK + 0x10, t)
        if not given and t >= snap:
            machine._give(giver)
            given = True
            events.append(dict(t=round(t, 3), event="giver_initialized", callback=hex(machine.get(machine.task(giver)))))
        for slot in ((target, giver) if given else (target,)):
            actor = machine.actor(slot)
            ctl = machine.get(actor + 0xC)
            machine.put(ctl + 0x1C, 0); machine.f(ctl + 0x10, 0.)
            callback = machine.get(machine.task(slot))
            if callback in (0, 0x1ABE40, 0x1AE870):
                continue
            try:
                machine.invoke(callback, slot)
            except Exception as exc:          # the exchange animation layer is not emulated
                events.append(dict(t=round(t, 3), event="stopped_in_unemulated_layer", slot=slot,
                                   callback=hex(callback), detail=repr(exc)[:80]))
                return dict(events=events, track=track, released=None)
            after = machine.get(machine.task(slot))
            if after != callback:
                gpos, tpos = machine.position(giver), machine.position(target)
                events.append(dict(t=round(t, 3), event="callback", slot=slot, before=hex(callback), after=hex(after),
                                   separation_yd=round(math.hypot(gpos[0] - tpos[0], gpos[1] - tpos[1]) / YD, 2)))
                if slot == target and after == 0x2E3DD0:
                    return dict(events=events, track=track, released=dict(
                        t=round(t, 3), separation_yd=events[-1]["separation_yd"],
                        giver_cm=[round(v, 1) for v in gpos], target_cm=[round(v, 1) for v in tpos]))
            factor = 0. if (freeze_giver and slot == giver) else machine.rf(ctl + 0x10)
            heading = (machine.get(ctl + 0x14) & 0xFFFF) / 65536. * 2 * math.pi
            speed = machine.call(SPEED_CURVE, (float(factor),), ecx=actor, fp=True) if factor > 0 else 0.
            want = (speed * math.sin(heading), speed * math.cos(heading))
            v = velocity[slot]
            for i in (0, 1):
                step = accel_yd_s2 * YD * dt
                v[i] += max(-step, min(step, want[i] - v[i]))
            body = machine.get(actor + 0x18)
            x, z = machine.position(slot)
            machine.vec(body + 0x30, (x + v[0] * dt, 0., z + v[1] * dt, 1.))
            machine.vec(body + 0x40, (v[0], 0., v[1], 0.))
        if frame % 6 == 0:
            track.append((round(t, 3), *(round(c, 1) for c in machine.position(giver)),
                          *(round(c, 1) for c in machine.position(target))))
    return dict(events=events, track=track, released=None)


def native_plan_callback(xbe: bytes):
    """A ``lint.NativePlan`` for ``lint_resource(native_plan=...)``; one machine, plans cached by geometry."""
    machine = HandoffMachine(xbe)
    cache: dict = {}

    def callback(view, giver, target):
        key = (tuple(view.positions), tuple(view.codes),
               tuple(b"".join(n.to_bytes() for n in chain) for chain in view.chains), giver, target)
        if key not in cache:
            try:
                cache[key] = plan(machine, view, giver, target)
            except Exception:                 # outside the probe's supported fixture
                cache[key] = None
        return cache[key]

    return callback


def main(argv=None):
    from mod_editor.core import nfl2k5_playbook_inspector as inspector
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xbe", type=Path)
    parser.add_argument("resource", type=Path, help="extracted fixed-size PLAY entry")
    parser.add_argument("--formation", type=int, required=True)
    parser.add_argument("--play", type=int, required=True)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--human-giver", action="store_true")
    parser.add_argument("--freeze-giver", action="store_true")
    args = parser.parse_args(argv)
    payload = args.resource.read_bytes()
    inspector.parse_playbook_resource(payload)
    view = next(v for v in lint.resource_views(payload) if v.formation == args.formation and v.play == args.play)
    machine = HandoffMachine(args.xbe.read_bytes())
    rows = []
    for giver, target, k, hole in lint.handoff_pairs(view):
        row = dict(giver=giver, target=target, k=k, hole=hole, plan=plan(machine, view, giver, target))
        if args.simulate:
            row["simulation"] = simulate(machine, view, giver, target, human_giver=args.human_giver,
                                         freeze_giver=args.freeze_giver)
        rows.append(row)
    print(json.dumps(dict(play=view.play_name, formation=view.formation_name, handoffs=rows), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
