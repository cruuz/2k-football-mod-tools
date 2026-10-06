#!/usr/bin/env python3
"""Execute target, accuracy, launch and lateral classification on supplied geometry.

This is bounded native instruction evidence. The route records, release pose,
ratings, complete RNG ring and elapsed time are fixtures, not captured gameplay.
No pass arithmetic or classification callee is replaced. A real backward
launch must remain a lateral. Actual PLAY route evidence is collected separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.nfl2k5_back_throws_replay import NativeMachine, DEFAULT_XBE, read_retail
from tools.b765.d2_passing_probe import classify, V04_SHA256
from tools.b765.d2_repair import COMBINED_SHA256


class ThrowMachine(NativeMachine):
    def __init__(self, payload):
        super().__init__(payload)
        # Native accuracy's team rule context. No active opponent actors.
        self.put(self.TEAM + 12, self.TEAM + 0x1000)
        self.put(self.TEAM + 0x100C, self.TEAM + 0x1100)

    def seed_complete_rng(self, seed):
        """Supply all 55 64-bit words; the native RNG performs every draw."""
        self.put(0xE5FCA0, 54)
        self.put(0xE5FCA4, 23)
        values = []
        for _ in range(55):
            seed = (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
            values.append(seed)
        self.uc.mem_write(0xE5FCA8, struct.pack('<55Q', *values))

    def throw(self, *, receiver, velocity=(0., 0.), release=-400., kind=7,
              direction=1, role=1, hold=.5, seed=1, challenges=1,
              referee_random=0., line=0.):
        self.route(receiver, velocity, kind=kind, direction=direction, role=min(role, 3), line=line)
        self.put(self.P + 0x2C, role)
        self.uc.mem_write(self.P + 0x1035, bytes([role]))
        return self.throw_from_route(release=release, direction=direction, hold=hold,
                                     seed=seed, challenges=challenges,
                                     referee_random=referee_random, line=line)

    def throw_from_route(self, *, release=-400., direction=1, hold=.5,
                         seed=1, challenges=1, referee_random=0., line=0.):
        """Consume existing native prediction records without replacing them.

        Caller initializes the exact assignment, current receiver pose/velocity
        and native clock. Only release pose, ball pointer and accuracy rule
        context are supplied here, as in the synthetic component matrix.
        """
        self.put(0xE5FC00, self.BALL)
        self.vec(self.Q + 0x530, (0., 0., line + release * direction, 1.))
        self.vec(self.BALL + 0x100, (0., 180., line + release * direction, 1.))
        self.seed_complete_rng(seed)
        solved = self.target(hold)
        radius = self.rf(self.OUT + 0x20)
        self.put(self.TEAM + 12, self.TEAM + 0x1000)
        self.put(self.TEAM + 0x100C, self.TEAM + 0x1100)
        self.call(0x2D9700, (self.P, radius, self.OUT, self.OUT + 0x200,
                  self.OUT + 0x220, self.OUT + 0x224, self.OUT + 0x228, float(hold)), eax=self.Q)
        accuracy_point = self.vector(self.OUT + 0x200)
        accuracy_instructions = sum(self.counts.values())
        errors = (self.get(self.OUT + 0x220), self.rf(self.OUT + 0x224), self.get(self.OUT + 0x228))
        self.call(0x1CBDB0, (solved['time'], *errors, 0),
                  ecx=self.BALL, edx=self.OUT + 0x200)
        # Native launch ABI: time, heading u32, scalar float, flags u32, side u32.
        launch_velocity = self.vector(self.BALL + 0x110)
        self.call(0x1CC820, (solved['time'],), ecx=self.BALL, edx=self.OUT + 0x300)
        endpoint = self.vector(self.OUT + 0x300)
        ruling = classify(self, phase=4, option=challenges, mode=4,
                          referee_random=referee_random)
        return dict(target=solved, accuracy_point=accuracy_point,
                    native_accuracy_launch_parameters=errors,
                    accuracy_instructions=accuracy_instructions,
                    launch_velocity=launch_velocity, endpoint=endpoint,
                    downfield_velocity=launch_velocity[2] * direction, **ruling)


def compare(retail, pack):
    if hashlib.sha256(pack).hexdigest() not in {V04_SHA256, COMBINED_SHA256}:
        raise ValueError('Expected exact v0.4 or composed d2 XBE')
    machines = [ThrowMachine(data) for data in (retail, pack)]
    rows = []
    for kind in (1, 7, 9):
        for release in (-45.72, -182.88, -365.76, -457.2, -640.08):
            for depth in (-640.08, -457.2, -365.76, -137.16, 0., 182.88):
                for direction in (-1, 1):
                    for hold in (0., .5, 1.):
                        inputs = dict(receiver=(800., depth), release=release, kind=kind,
                                      direction=direction, hold=hold, seed=7)
                        results = [machine.throw(**inputs) for machine in machines]
                        # Modified rating wrappers can add instructions; compare outcomes.
                        outcomes = [{k: v for k, v in result.items() if k != 'accuracy_instructions'}
                                    for result in results]
                        if outcomes[0] != outcomes[1]:
                            raise AssertionError((inputs, outcomes))
                        rows.append(dict(inputs=inputs, **results[1]))
    return dict(schema='b765.d2b.passing-components.v1',
                retail_sha256=hashlib.sha256(retail).hexdigest(),
                pack_sha256=hashlib.sha256(pack).hexdigest(),
                supplied_geometry=True, gameplay_witness=False, full_game_frame=False,
                limits=__doc__, paired_cases=len(rows),
                backward_launches=sum(row['downfield_velocity'] < 0 for row in rows),
                backward_kind3=sum(row['downfield_velocity'] < 0 and row['kind'] == 3 for row in rows),
                forward_kind3=sum(row['downfield_velocity'] > 0 and row['kind'] == 3 for row in rows),
                rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retail', type=Path, default=DEFAULT_XBE)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists() or args.receipt.is_symlink():
        parser.error('Receipt must be a new file')
    with args.pack.open('rb') as stream:
        pack = stream.read(16 * 1024 * 1024 + 1)
    result = compare(read_retail(args.retail), pack)
    with args.receipt.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('paired_cases', 'backward_launches', 'backward_kind3', 'forward_kind3')}))


if __name__ == '__main__':
    main()
