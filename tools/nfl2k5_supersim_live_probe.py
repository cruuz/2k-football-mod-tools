"""Bounded live-engine research; no console, renderer, disc build or install.

Run with --output to record derived evidence, never retail bytes. Grouping
inner updates is a state-equivalence experiment, not a measured speedup.
"""
from pathlib import Path
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Function/dispatch spans used by the research. The executable itself
# is hash-pinned by retail_bytes(); these coordinates are NOT reservations.
SPANS = {
    "main_frame": (0x74790, 0x10f), "input_rng": (0x74730, 0x55),
    "manager_update": (0x6e6a0, 0x38), "manager_render": (0x6e6e0, 0x58),
    "outer_update": (0x64cd0, 0x1a4), "inner_update": (0x11a7c0, 0x128),
    "game_descriptor": (0x4e7ec0, 44), "game_events": (0x4e7e88, 56),
    "game_update_command": (0x4e7df8, 72), "late_modal": (0x11ef60, 0x1c8),
    "render": (0x64f80, 0x60), "player_render": (0x11a8f0, 0x2d),
    "replay_screen": (0x13610, 0x580), "highlight_screen": (0x1124e0, 0xa17),
    "skip_request": (0xa2120, 0x34d), "skip_table": (0xa2470, 0x40),
    "skip_pending": (0x89780, 0x43), "period_ready": (0xb8db0, 0xc0),
    "dialog": (0x14e070, 0x328), "present_region": (0x27ca0, 0x590),
}


def frame_probe(payload):
    """Eight identical fixed updates, grouped 1/2/4/8, with declared leaves.

    All 27 phase functions execute. Synthetic looping clips, skeletons and
    kickoff actors cannot establish a full drive, audio queue capacity or a
    console performance claim. The inherited fixture substitutes random draws.
    """
    if importlib.util.find_spec("capstone") is None:
        raise unittest.SkipTest("Capstone is absent; kickoff frame probe requires it")
    from tests.nfl2k5_kickoff_frame import FrameMachine, PHASES
    from tests.mod_editor.test_nfl2k5_dynamic_kickoff import uni
    class ProbeMachine(FrameMachine):
        def __init__(self, *args, **kwargs):
            self.boundaries = defaultdict(Counter)
            super().__init__(*args, **kwargs)

        def _hook(self, uc, address, size, data):
            if address in self.stub_pops or address in self.fpu_stubs:
                self.boundaries[self.phase][address] += 1
            super()._hook(uc, address, size, data)

    rows = []
    for group in (1, 2, 4, 8):
        m = ProbeMachine(payload)
        phase_writes = Counter()
        def observe(_uc, _access, _address, _size, _value, _data):
            # Tags follow the latest phase entry. Dispatcher stack stores
            # between phases retain that tag; this is not a purity analysis.
            phase_writes[m.phase] += 1
        handle = m.uc.hook_add(uni.UC_HOOK_MEM_WRITE, observe)
        start = time.perf_counter()
        for _ in range(8 // group):
            for _ in range(group):
                m.frame()
        seconds = time.perf_counter() - start
        m.uc.hook_del(handle)
        snapshot = m.snapshot()
        rows.append(dict(
            updates_per_group=group, updates=8, groups=8 // group,
            host_seconds=round(seconds, 6), presented_frames=0,
            state_sha256=hashlib.sha256(b"".join(snapshot[k] for k in sorted(snapshot))).hexdigest(),
            clock_seconds=m.readf(m.CLOCK + 16),
            phase_entries=[dict(va=hex(p), calls=m.visited[p], writes=phase_writes[p],
                                substituted_calls={hex(a): n for a, n in sorted(m.boundaries[p].items())})
                           for p in PHASES],
            substituted_calls={hex(p): m.calls.count(p) for p in sorted(set(m.calls))},
        ))
    return rows


def pins(payload):
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    im = XbeImage(payload)
    return {name: dict(va=hex(va), size=size,
                       sha256=hashlib.sha256(im.read(va, size)).hexdigest())
            for name, (va, size) in SPANS.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes
    if not HAVE_UC:
        raise unittest.SkipTest("Unicorn is absent; native live-engine probe requires it")
    payload = retail_bytes()
    result = dict(schema="nfl2k5.supersim-live.v1", runtime_witnessed=False,
                  accelerated_runtime_ready=False, shipped_updates_per_frame=1,
                  spans=pins(payload), frames=frame_probe(payload),
                  limitations=["No rendered frames or audio devices in the harness",
                               "Synthetic clips do not prove automatic snaps or complete drives",
                               "FrameMachine's declared input, attribute, audio and RNG leaves retained",
                               "Equal grouped state is not a safe scheduler or a real-time speed measurement"])
    args.output.write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    print("Recorded bounded 1/2/4/8 grouping evidence; shipped speed remains 1x")


if __name__ == "__main__":
    main()
