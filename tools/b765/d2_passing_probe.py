#!/usr/bin/env python3
"""Bounded retail/v0.4 target, flight and backward-pass component comparison.

No full game frame, live PLAY execution, accuracy error, catch or possession
simulation is claimed. All players, route motion and release positions are
supplied fixtures. No native code/results are stubbed by this probe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.nfl2k5_back_throws_replay import (
    CODE_PINS, DEFAULT_XBE, RETAIL_SHA256, NativeMachine, Scenario, read_retail, scenarios,
)
from tools.nfl2k5_deep_ball_native_probe import NativeReader
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core import nfl2k5_throw_tuning as tuning
import unicorn
from unicorn import x86_const as x86

V04_SHA256 = "5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29"
# Full release, accuracy routine and classifier plus native kind writers.
EXTRA_SPANS = ((0x2DAF10, 0x328), (0x2D9700, 0xC10),
               (0xB7450, 0xBB), (0x236810, 0x18B),
               (0xB6700, 0x33), (0xB6740, 0x18), (0x4E4180, 4))
# The phase-4 path additionally evaluates the release relative to the LOS,
# a mode/setting gate and native angle/history helpers. These are byte spans,
# including padding in some cases, rather than asserted function extents.
PHASE4_SPANS = ((0x235350, 0x60), (0x235410, 0x80), (0x235930, 0x30),
                (0x235C10, 0x40), (0x235CD0, 0x30), (0x235D30, 0x70),
                (0x235E30, 0x100), (0x1B1150, 0x20), (0x62550, 0x2C),
                (0xE9120, 0x40), (0x21040, 0x110), (0xA1D90, 0x20),
                (0x1B9E00, 0x40), (0xA7AD0, 0x70), (0xA7A40, 0x90),
                (0x510540, 4), (0x4E6C40, 4), (0x50ADDC, 0x24),
                (0x4E53E8, 0x800), (0x1B1300, 0x3C), (0x48B50, 0x69),
                (0x4E696C, 4))
CLASSIFIER_TRACE = (0x23687D, 0x235EA0, 0x235E30, 0x235350)


def classifier_inputs(machine, *, phase, option, mode, referee_random):
    """Supply explicit state inputs; option is the native Challenges toggle."""
    machine.put(0xE602B4, phase)
    machine.put(0xE60288, machine.TEAM)
    machine.put(0xE5FF80, mode)
    machine.put(0xE6003C, option)
    machine.put(0xBE4FA0, 0)
    machine.f(0xBE5034, 0.)
    machine.f(0xBE5048, referee_random)
    machine.put(machine.CTX + 0x160, 0)


def classify(machine, *, phase=0, option=0, mode=0, referee_random=0.):
    """Run B7450 through the actual kind store, stopping at the kind writer.

    Phase 0 isolates the direction-only branch. Phase 4, with the supplied
    player on the offense team, also executes the native eligibility path.
    Its history and BE5048 input are fixtures, not a captured game's state.
    Challenge registration inside 235350 runs natively; downstream event
    consumption and the remaining forward-kind notifications do not run.
    """
    classifier_inputs(machine, phase=phase, option=option, mode=mode,
                      referee_random=referee_random)
    machine.counts.clear()
    machine.trace.clear()
    reached = []

    def stop_after_store(uc, address, _size, _user):
        if address in (0xB6715, 0xB6755):
            reached.append(address)
            uc.emu_stop()

    hook = machine.uc.hook_add(unicorn.UC_HOOK_CODE, stop_after_store)
    try:
        machine.put(machine.SP, machine.STOP)
        machine.put(machine.SP + 4, machine.OUT)
        machine.uc.reg_write(x86.UC_X86_REG_ESP, machine.SP)
        machine.uc.reg_write(x86.UC_X86_REG_ECX, machine.Q)
        machine.uc.reg_write(x86.UC_X86_REG_EDX, machine.P)
        machine.uc.emu_start(0xB7450, machine.STOP, timeout=5_000_000, count=20000)
        if len(reached) != 1:
            raise AssertionError("Native classifier did not reach its kind store")
        return dict(kind=machine.get(0xE602C0),
                    classifier_calls={hex(at): machine.counts[at] for at in CLASSIFIER_TRACE},
                    classifier_flags=hex(machine.get(0xBE4FA0)))
    finally:
        machine.uc.hook_del(hook)


def sample(machine, scenario, direction, role, hold, *, phase=0, option=0,
           mode=0, referee_random=0.):
    classifier_inputs(machine, phase=phase, option=option, mode=mode,
                      referee_random=referee_random)
    machine.seed_rng(0x100000)
    machine.route(scenario.position, scenario.velocity, kind=scenario.kind,
                  direction=direction, role=role)
    target = machine.target(hold)
    # Native launch and arrival prediction; no need to sample every frame.
    machine.call(0x1CBDB0, (float(target["time"]), 0., 0., 1, 0),
                 ecx=machine.BALL, edx=machine.OUT)
    machine.call(0x1CC820, (float(target["time"]),),
                 ecx=machine.BALL, edx=machine.OUT + 0x100)
    endpoint = machine.vector(machine.OUT + 0x100)
    classification = classify(machine, phase=phase, option=option, mode=mode,
                              referee_random=referee_random)
    return dict(target=target, endpoint=endpoint, **classification)


def compare(retail, pack):
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise ValueError("Expected exact USA retail XBE")
    if hashlib.sha256(pack).hexdigest() != V04_SHA256:
        raise ValueError("Expected exact v0.4 extracted XBE")
    ri, pi = XbeImage(retail), XbeImage(pack)
    spans = []
    for va, size in (*CODE_PINS, *EXTRA_SPANS, *PHASE4_SPANS):
        old, new = ri.read(va, size), pi.read(va, size)
        if old != new:
            raise ValueError(f"Unexpected pass dependency difference at {va:#x}")
        spans.append(dict(va=hex(va), size=size, sha256=hashlib.sha256(old).hexdigest()))
    readers = [NativeReader(data) for data in (retail, pack)]
    speeds = []
    for quarter_yard in range(161):
        distance = quarter_yard / 4
        values = [reader.speed(distance) for reader in readers]
        if values[0] != values[1]:
            raise AssertionError((distance, values))
        speeds.append(dict(yards=distance, native_float32_cm_s=values[0][1]))
    machines = [NativeMachine(data) for data in (retail, pack)]
    fixtures = list(scenarios())
    for kind in (7, 9):
        for z in (-1000, -401, -400, -399, -200, 0):
            fixtures.append(Scenario("stationary" if kind == 7 else "screen_endpoint",
                                     f"z={z}", (300, z), (0, 0), kind))
    profiles = [("phase0_direction_only", dict(phase=0, option=0, mode=0)),
                ("phase4_option0", dict(phase=4, option=0, mode=4)),
                ("phase4_option1", dict(phase=4, option=1, mode=4))]
    for value in (-.99, -.5, .5, .99):
        profiles.append((f"phase4_option1_random_{value}",
                         dict(phase=4, option=1, mode=4, referee_random=value)))
    profile_results = {}
    for name, inputs in profiles:
        results = []
        for scenario in fixtures:
            for direction in (1, -1):
                for role in (1, 2, 3):
                    for hold in (0., .5, 1.):
                        before, after = [sample(m, scenario, direction, role, hold, **inputs)
                                         for m in machines]
                        if before != after:
                            raise AssertionError((name, scenario, direction, role, hold, before, after))
                        results.append(dict(scenario=scenario.__dict__, direction=direction,
                                            role=role, hold=hold, **before))
        profile_results[name] = dict(inputs={"referee_random": 0., **inputs,
                                             "offense_team": "TEAM", "fresh_history": True},
                                     identical_cases=len(results),
                                     kind3_cases=sum(row["kind"] == 3 for row in results),
                                     classifier_call_cases={hex(at): sum(row["classifier_calls"][hex(at)] > 0
                                                                        for row in results)
                                                            for at in CLASSIFIER_TRACE},
                                     results=results)
    baseline = profile_results["phase0_direction_only"]
    # Execute only the initializer's RNG/store tail (not its prior event reset)
    # with explicitly supplied valid RNG rings. This cannot establish equal
    # full-game RNG draw order, but proves identical reader/writer results.
    rng_results = []
    for mantissa in [i * 0x7FFFFF // 16 for i in range(17)]:
        values = []
        for machine in machines:
            machine.seed_rng(mantissa)
            machine.call(0x1B1319)
            values.append(bytes(machine.uc.mem_read(0xBE5048, 4)).hex())
        if values[0] != values[1]:
            raise AssertionError(("referee RNG writer", mantissa, values))
        rng_results.append(dict(rng_mantissa=mantissa, native_be5048_float32=values[0]))
    tolerance_results = []
    for value in (-.99, -.5, 0., .5, .99):
        values = []
        for machine in machines:
            machine.f(0xBE5048, value)
            values.append(machine.call(0x235E30, (6.5,), fp=True))
        if values[0] != values[1]:
            raise AssertionError(("challenge tolerance", value, values))
        tolerance_results.append(dict(referee_random=value, native_tolerance_degrees=values[0]))
    return dict(proof="bounded native components; no gameplay witness",
                limits=["synthetic healthy player/route inputs", "no accuracy pass execution",
                        "no PLAY interpreter or live route timing", "no catch/possession/fumble-stat frame",
                        "fixed .8 cached ratings, release LOS-400cm/y180cm",
                        "supplied hold scalars, not live button/input replays",
                        "phase4 uses supplied mode4, offense TEAM, fresh history and five BE5048 values",
                        "phase4 Challenges flag0/1 compared; saved settings and live referee state not captured",
                        "native challenge registration executes; no downstream event consumption",
                        "RNG writer tail tested with supplied rings; no full-game draw-order comparison"],
                setting=dict(name="Challenges", address="0xe6003c",
                             semantics_evidence="native menu descriptor 0x501d40 and handlers 0x149420/0x149440/0x149460"),
                retail_sha256=hashlib.sha256(retail).hexdigest(), pack_sha256=V04_SHA256,
                unchanged_spans=spans, arc=tuning.read_arc_table(pack),
                curves=tuning.read_curves(pack), identical_short_speed_cases=len(speeds),
                identical_target_launch_classification_cases=baseline["identical_cases"],
                backward_kind_cases=baseline["kind3_cases"],
                identical_phase4_cases=sum(profile_results[name]["identical_cases"]
                                           for name in ("phase4_option0", "phase4_option1")),
                identical_phase4_random_cases=sum(profile["identical_cases"] for name, profile
                                                  in profile_results.items() if "_random_" in name),
                referee_rng_results=rng_results, challenge_tolerances=tolerance_results,
                speed_results=speeds, results=baseline["results"], profiles=profile_results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail", type=Path, default=DEFAULT_XBE)
    parser.add_argument("--v04-xbe", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    with args.v04_xbe.open("rb") as stream:
        pack = stream.read(16 * 1024 * 1024 + 1)
    report = compare(read_retail(args.retail), pack)
    with args.receipt.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ("identical_short_speed_cases",
                     "identical_target_launch_classification_cases", "backward_kind_cases",
                     "identical_phase4_cases", "identical_phase4_random_cases")}))


if __name__ == "__main__":
    main()
