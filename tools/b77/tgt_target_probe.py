"""Native CPU read setup, evaluation cadence and target-score component probes.

Uses the existing Unicorn fixture. All three routines and their helpers run
unaltered. Runtime assignment operands, players, openness/projected catch
scores and release opportunity are supplied fixtures, not captured gameplay.
No throw, defender, catch, or whole-frame simulation is claimed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_cpu_money_downs_native import Machine, bits
from mod_editor.core import nfl2k5_playbook_lint as lint
from mod_editor.core import nfl2k5_playbook_inspector as inspector
from tools.nfl2k5_back_throws_replay import DEFAULT_XBE
from pb.v2.targeting import resolve_roles


class TargetMachine(Machine):
    def run(self, *args, **kwargs):
        result = super().run(*args, **kwargs)
        if getattr(self, "track_entries", False):
            self.entry_hits.update(self.hits)
        return result

    def prepare(self, reads, route_slots=range(6, 11)):
        self.targets([dict(yards=10, score=.2)] * 5, down=1, distance=10)
        self.u32(self.OFF+4, self.QB)
        self.u32(self.QB+0xD30, self.QB+0xD80)
        self.u32(self.QB+0xDA0, 0)
        self.u32(self.QB+0xD84, self.QB+0xDB0)
        self.f32(self.QB+0xDB4, .5)
        self.u32(0xE6029C, self.GAME+0x600)
        self.uc.mem_write(self.QB+0x2E, bytes([0]))
        self.u32(self.QB+0x34, self.RB)
        for i in range(5):
            player = self.RB + i*0x2000
            self.uc.mem_write(player+0x2E, bytes([6+i]))
            self.u32(player+0x34, self.RB+(i+1)*0x2000 if i < 4 else 0)
            descriptor = self.SOURCE+0x18000+i*0x20
            nodes = self.SOURCE+0x18100+i*0x20
            self.u32(descriptor, 2)
            self.u32(descriptor+4, nodes)
            self.uc.mem_write(nodes, bytes(8)+bytes([0x12 if 6+i in route_slots else 0x11])+bytes(7))
            self.u32(player+0x600+0x41C, descriptor)
            self.u32(0xBE4830+i*0xA0, 0)
        play, desc, nodes = (self.SOURCE+x for x in (0x18500, 0x18600, 0x18700))
        self.u32(self.OFF+0x10C, play)
        self.u32(play+8, 0x400)       # native ball-handler descriptor bit, QB
        self.u32(desc, 1)
        self.u32(desc+4, nodes)
        self.uc.mem_write(nodes, bytes([0x06])+bytes(7))
        state = self.QB+0x600+0x41C
        self.u32(state, desc)
        self.uc.mem_write(state+0x34, bytes([0]))
        for i, value in enumerate([s-5 for s in reads][:4]+[0]*4):
            if i >= 4:
                break
            self.f32(state+0x18+i*4, value)
        self.run(0x198E40, count=20000)
        self.order = [(self.get(0xBE4820+i*0xA0)-self.RB)//0x2000+6 for i in range(5)]
        self.u32(0xBE4810, 0)
        self.f32(0xBE47C8, 0)
        self.f32(self.GAME+0x610, 25)
        return list(self.order)

    def advance(self):
        # Native scheduler chooses the next viable read and computes its next
        # deadline from the QB's native attribute helper and curve.
        self.f32(self.GAME+0x610, self.readf(0xBE47C8)+1)
        self.run(0x199100, ecx=self.QB, count=10000)
        return self.get(0xBE4810)

    def projections(self, scores, active):
        for i, slot in enumerate(self.order):
            row = 0xBE4820+i*0xA0
            self.u32(row+8, int(slot in active))
            for j in range(4):
                self.f32(row+0x34+j*0x20, scores[slot] if j == 0 else -float("inf"))

    def pick(self, *, down=1, distance=10):
        self.configure(down=down, distance=distance)
        args = (self.GAME+0x800, self.GAME+0x804, bits(.5), self.GAME+0x808)
        self.run(0x1985E0, args=args, count=10000)
        row = self.get(self.GAME+0x800)
        return None if row == 0 else self.order[(row-0xBE4820)//0xA0]


def proof(payload):
    machine = TargetMachine(payload)
    machine.track_entries, machine.entry_hits = True, Counter()
    rows = []
    for reads in ([6, 7, 8, 9], [9, 8, 7, 6]):
        order = machine.prepare(reads)
        cycle, deadlines = [0], [machine.readf(0xBE47C8)]
        for _ in range(5):
            cycle.append(machine.advance())
            deadlines.append(machine.readf(0xBE47C8))
        machine.projections({s: .9 if s == 6 else .6 for s in range(6, 11)}, set(range(6, 11)))
        stronger = machine.pick()
        machine.projections({s: .8 for s in range(6, 11)}, {order[0]})
        first = machine.pick()
        machine.projections({s: .8 for s in range(6, 11)}, set(range(6, 11)))
        equal = machine.pick()
        rows.append(dict(reads=reads, native_order=order, native_cycle=cycle,
                         native_deadlines=deadlines,
                         strongest_target_with_all_evaluated=stronger, only_first_evaluated_target=first,
                         equal_scores_and_attributes_target=equal))
    assert rows[0]["native_order"] == [6, 7, 8, 9, 10]
    assert rows[1]["native_order"] == [9, 8, 7, 6, 10]
    assert [r["strongest_target_with_all_evaluated"] for r in rows] == [6, 6]
    assert [r["only_first_evaluated_target"] for r in rows] == [6, 9]
    assert [r["equal_scores_and_attributes_target"] for r in rows] == [6, 9]
    machine.prepare([6, 7, 8, 9])
    machine.projections({s: .2 for s in range(6, 11)}, set(range(6, 11)))
    below_threshold = machine.pick()
    assert below_threshold is None
    machine.projections({s: .6 for s in range(6, 11)}, set(range(6, 11)))
    for i in range(5):
        machine.u32(machine.RB+i*0x2000+0xDA0, i)
        machine.uc.mem_write(0xAA4498+i*0xE4, bytes([20 if i == 4 else 0]))
    rating_bias_target = machine.pick()
    assert rating_bias_target == 10
    observed = {f"{address:06X}": machine.entry_hits[address]
                for address in (0x198E40, 0x199100, 0x1985E0, 0x17AE80, 0x17B010)}
    assert all(observed.values()), observed
    return dict(schema="b77.tgt.mechanism.v1", source_sha256=hashlib.sha256(payload).hexdigest(),
                routines=["198E40", "199100", "1985E0"], native_helpers_substituted=[],
                gameplay_witness=False, supplied_state=__doc__, rows=rows,
                native_entry_hits=observed,
                read_delay_curve=[[machine.readf(0x50C54C+i*8), machine.readf(0x50C550+i*8)]
                                  for i in range(machine.get(0x50C548))],
                below_threshold_target=below_threshold, native_attribute_bias_target=rating_bias_target,
                attribute_control="Equal .6 projections; slot 10's native 17AE80 signed table byte = 20, others 0. This identifies a native per-player bias; its football meaning is not established.")


def openness_seed(team, view):
    """Pair physical inputs independently of names, indices and read operands."""
    qb = lint.qb_slot(view)
    qb_jobs = []
    for node in view.chains[qb]:
        args = list(node.operands)
        if node.op == 0x06:
            args[1:5] = [0] * 4
        qb_jobs.append([node.op, node.flags, args])
    key = json.dumps([team, view.positions, view.codes, qb_jobs,
                      [[n.to_bytes().hex() for n in chain]
                       for slot, chain in enumerate(view.chains) if slot != qb]], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def measure(payload, before, after, data, samples=16):
    missing = []
    for team in data["teams"]:
        old = inspector.parse_playbook_resource((before / f"{team}.play").read_bytes())
        new = inspector.parse_playbook_resource((after / f"{team}.play").read_bytes())
        old_names, new_names = {p.name for p in old.plays}, {p.name for p in new.plays}
        package = json.loads((ROOT / f"pb/v2/teams/{team}.json").read_text())
        named = [s["name"] for s in package.get("signature", [])]
        named += [e["name"] for menu in package.get("menus", {}).values()
                  for e in menu if isinstance(e, dict) and e.get("name")]
        for name in named:
            if name in old_names and name not in new_names:
                missing.append(f"{team}: {name}")
    if missing:
        raise ValueError("Named team plays lost during targeting rebuild: " + "; ".join(missing))
    machine = TargetMachine(payload)
    result = {}
    for team in data["teams"]:
        variants = {}
        for label, directory in (("before", before), ("after", after)):
            raw = (directory / f"{team}.play").read_bytes()
            counts, primaries, attempts, misses = Counter(), Counter(), 0, 0
            for view in lint.resource_views(raw):
                if not lint.is_pass(view):
                    continue
                qb = lint.qb_slot(view)
                node = next((n for n in view.chains[qb] if n.op == 0x06), None)
                if node is None:
                    continue
                reads = [int(v)+5 for v in node.operands[1:5] if v]
                slots = {s for s in range(6, 11) if any(n.op == 0x12 for n in view.chains[s])}
                order = machine.prepare(reads, slots)
                schedule = [0]+[machine.advance() for _ in range(4)]
                role = resolve_roles(view.codes, data["teams"][team]["depth_chart"])
                if reads:
                    primaries[role.get(reads[0], f"unresolved_kind{view.codes[reads[0]] & 31}")] += 1
                paired_seed = openness_seed(team, view)
                # Neither observed target shares nor reads generate scores.
                for sample in range(samples):
                    seed = paired_seed+sample
                    rng = random.Random(seed)
                    scores = {s: (.6+.35*rng.random()) if rng.random() < .55 else .2 for s in range(6, 11)}
                    deadline = (1, 2, 4, 5)[sample % 4]
                    active = {order[i] for i in schedule[:deadline] if order[i] in slots}
                    machine.projections(scores, active)
                    target = machine.pick()
                    attempts += 1
                    if target is None:
                        misses += 1
                    else:
                        counts[role.get(target, f"unresolved_kind{view.codes[target] & 31}")] += 1
            total = sum(counts.values())
            shares = {r: n / total for r, n in sorted(counts.items())}
            real = data["teams"][team]["role_shares"]
            error = sum(abs(shares.get(r, 0)-real.get(r, 0)) for r in set(shares) | set(real))
            error += data["teams"][team]["unmapped_targets"] / data["teams"][team]["targets"]
            variants[label] = dict(resource_sha256=hashlib.sha256(raw).hexdigest(), attempts=attempts,
                                   no_viable_target=misses, targets=dict(counts), shares=shares,
                                   unresolved_targets=sum(n for r, n in counts.items() if r.startswith("unresolved_")),
                                   first_read_links=dict(primaries),
                                   total_variation=error / 2)
        result[team] = dict(real_shares=data["teams"][team]["role_shares"], **variants)
        print(team, "TV", *(round(variants[v]["total_variation"], 4) for v in ("before", "after")), flush=True)
    return dict(schema="b77.tgt.native-components.v1", source_sha256=hashlib.sha256(payload).hexdigest(),
                mechanism=proof(payload),
                gameplay_witness=False, routines=["198E40", "199100", "1985E0"],
                limits="Equal weight for every pass formation/play link; 16 openness samples per link, paired by physical geometry, personnel and assignments (excluding names, indices and QB read operands), independent .55 viable probability and .6-.95 projected catch score; release opportunities after 1/2/4/5 native evaluations. Down 1 removes marker incentives. Missing position pools are unresolved, not attributed to guessed substitutes. No native trajectory/openness calculation, pressure or live call-mix replay. These are conditional component distributions, not predicted game shares.",
                samples_per_link=samples, teams=result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xbe", type=Path, default=DEFAULT_XBE)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--before", type=Path)
    ap.add_argument("--after", type=Path)
    ap.add_argument("--data", type=Path, default=ROOT / "pb/research/targets_2026.json")
    args = ap.parse_args()
    if bool(args.before) != bool(args.after):
        ap.error("--before and --after must be supplied together")
    payload = args.xbe.read_bytes()
    result = measure(payload, args.before, args.after, json.loads(args.data.read_text())) if args.before else proof(payload)
    result["data_sha256"] = hashlib.sha256(args.data.read_bytes()).hexdigest()
    with args.out.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
