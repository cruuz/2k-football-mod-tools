#!/usr/bin/env python3
"""Read-only native component probes for throws to backs.

EXPERIMENTAL / UNWITNESSED. This is a research tool, not an XBE patch owner.
The route segments, player objects, release position and clock are supplied
fixtures. There is no PLAY interpreter, full 11A7C0 frame, accuracy pass,
catch-task transition, possession, tackle or YAC simulation here. Sampling
native ball prediction at 60 Hz does not make this a full-frame replay.

No pass, animation, catch, attribute, interpolation or RNG callee is stubbed.
The two native hand-twist inputs come from the shipped lo_body/LO_res axes
already pinned by tools/nfl_player_pose_native_validate.py. Catch metadata is
computed by the actual 1E3070 initializer, never fabricated from envelopes.
No proprietary executable or animation payload is included in the repository.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.nfl2k5_bump_strength import _sections

try:
    import unicorn as uc_module
    from unicorn import x86_const as x86
except ImportError:
    uc_module = x86 = None

NativeExecutionError = uc_module.UcError if uc_module is not None else RuntimeError

RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
MAX_XBE_BYTES = 16 * 1024 * 1024
DEFAULT_XBE = (Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                    "/media/noah/Storage/for codex 1.0/extracted")) /
               "ESPN NFL 2K5 (USA)" / "default.xbe")
HOLD_REASON = (
    "No gameplay patch: the four reported defects lack a native full-frame "
    "reproducer and a proved standing-versus-dive selection contract."
)
CODE_PINS = {
    (0x2DA8E0, 1580): "2fa96051127785d54f6c44946bd3e12e0081c9cfd5a8a00a401423bedbb68c93",
    (0x2F43E0, 1387): "14037c5abaa8fbe996c90de496e6e58e8b5868ee1d447e5a0d838888fd41a3df",
    (0x2266A0, 1065): "e2801e152a366ce1276175628d2c40b801d0195a600ed16df846c32f3d10bc87",
    (0x1CBDB0, 398): "38b8c19012425cb11487fe5a71c3f89443e790472d0b011ff8bd621308a315cc",
    (0x1CC820, 618): "a13d11fe0a5d6559fb8c7268d751d3ba0e95690d8a223808e4ea9bb34267c90b",
    (0x1E7410, 689): "53e27654048d26be8ded21860dd1f152798f834798b22900ac21606f931dc299",
    (0x1E6600, 3595): "fad59095ba1df1eabba981f5d9b3f137b8e340b296905b961664e2732a745623",
    (0x1E38D0, 1475): "f47c982392ec2e7a203ac2bd2dca19c20b5f5484292998ecd8ca89584b8f088f",
    (0x1E3070, 120): "1408a5931035c68a3e79f5e265eb08496e48b633a73b98f901ce10ebed331a91",
    (0x1E2660, 551): "93e92c2970a580cda76492169a6497c814bcf9a066e946531bcfb5ac59e71ed5",
    (0x1E6310, 73): "e19fe9a7a417e5b7d52f65ed872c11a43cac62da7f64af7e72410d548580b17c",
    (0x1E6360, 154): "c6508d15c12b0ff19e71b7aaa2a511ed48fadaa71f226cd5937348464ed41e63",
    (0x1C6100, 79): "bc0f08d259fe134130dfdd5a84690561e0d91662b896b3d208b78fb7370655a2",
    (0x2DB0F7, 192): "9b4af71e1a6424dfabe160e02f60c83ca940db5e1575b28f9c500b679af6deb5",
}


def read_retail(path: Path) -> bytes:
    """Bound the read before hashing; never accept an archive or disc image."""
    with Path(path).open("rb") as stream:
        if os.fstat(stream.fileno()).st_size > MAX_XBE_BYTES:
            raise ValueError("Expected a default.xbe under 16 MiB, not a disc or pack")
        payload = stream.read(MAX_XBE_BYTES + 1)
    if hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
        raise ValueError("Native evidence requires the pinned USA retail default.xbe")
    return payload


@dataclass(frozen=True)
class Scenario:
    route: str
    timing: str
    position: tuple[float, float]
    velocity: tuple[float, float]
    kind: int = 1


def scenarios() -> tuple[Scenario, ...]:
    """Fifteen supplied local motion segments; names describe geometry only.

    Early/on_time/late means position along these supplied paths, NOT a
    measured release time in a named retail play. Hold strength is separate.
    The stationary checkdown uses kind 7, the stopped/end-point branch; screen
    kind 9 is tested separately and must not be substituted for a swing.
    """
    routes = (
        ("swing_right", ((100, -350), (400, -150), (750, 50)), (450, 100), 1),
        ("swing_left", ((-100, -350), (-400, -150), (-750, 50)), (-450, 100), 1),
        ("flat", ((250, -50), (550, 0), (850, 50)), (500, 0), 1),
        ("angle", ((400, -200), (250, 100), (50, 400)), (-250, 400), 1),
        ("checkdown", ((100, 100), (100, 250), (100, 400)), (0, 0), 7),
    )
    return tuple(Scenario(name, timing, pos, velocity, kind)
                 for name, positions, velocity, kind in routes
                 for timing, pos in zip(("early", "on_time", "late"), positions))


class NativeMachine:
    """Bounded x86 calls in loaded XBE sections, with explicit synthetic inputs.

    The CLI validates the whole retail file. Tests may pass images produced by
    existing owners to compare composition; entry-span pins still apply. Such
    variants are recorded by their own hash and are not labelled retail.
    """
    P = 0x2000000
    Q = 0x2002000
    BALL = 0x2004000
    TEAM = 0x2005000
    CTX = 0x2006000
    CLOCK = 0x2007000
    OUT = 0x2008000
    SP = 0x3008000
    STOP = 0x3009000

    def __init__(self, payload: bytes):
        if uc_module is None:
            raise RuntimeError("unicorn is required for native instruction probes")
        if len(payload) > MAX_XBE_BYTES:
            raise ValueError("XBE fixture exceeds the 16 MiB bound")
        self.source_sha256 = hashlib.sha256(payload).hexdigest()
        self.uc = uc_module.Uc(uc_module.UC_ARCH_X86, uc_module.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x15F0000)
        self.uc.mem_map(self.P, 0x100000)
        self.uc.mem_map(0x3000000, 0x10000)
        self.uc.mem_write(0x10000, payload[:0x1000])
        for section in _sections(payload):
            self.uc.mem_write(section.virtual_address,
                              payload[section.raw_offset:section.raw_offset + section.raw_size])
        for (address, size), digest in CODE_PINS.items():
            if hashlib.sha256(self.uc.mem_read(address, size)).hexdigest() != digest:
                raise ValueError(f"Foreign native entry span at {address:#x}")
        # All retail .text pages are RX, including the final shared boundary
        # page. No input object or runtime metadata lives on these pages.
        self.uc.mem_protect(0x11000, 0x410000,
                            uc_module.UC_PROT_READ | uc_module.UC_PROT_EXEC)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.trace = deque(maxlen=32)
        self.counts = Counter()
        self.uc.hook_add(uc_module.UC_HOOK_CODE, self._instruction)
        self._objects()
        self.catch_initialized = False

    def _instruction(self, machine, address, size, user):
        self.trace.append(address)
        self.counts[address] += 1

    def put(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def f(self, address, value):
        self.uc.mem_write(address, struct.pack("<f", value))

    def vec(self, address, values):
        self.uc.mem_write(address, struct.pack(f"<{len(values)}f", *values))

    def get(self, address):
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def rf(self, address):
        return struct.unpack("<f", self.uc.mem_read(address, 4))[0]

    def vector(self, address):
        return struct.unpack("<4f", self.uc.mem_read(address, 16))

    def _objects(self):
        self.put(0xE60280, self.TEAM)
        self.put(0xE60284, self.TEAM + 0x400)
        self.put(0xE602EC, self.CTX)
        self.put(0xE6029C, self.CLOCK)
        self.put(self.TEAM, self.TEAM + 0x400)  # empty opposition list
        self.put(self.TEAM + 8, self.TEAM + 0x100)
        self.put(self.TEAM + 0x10C, self.TEAM + 0x200)
        self.f(self.TEAM + 0x204, 1)
        self.put(0xE5FC00, self.BALL)
        self.put(self.BALL + 0x14, self.BALL + 0x100)
        self.vec(self.BALL + 0x100, (0, 180, -400, 1))
        self.f(self.CLOCK + 0x10, 1)
        self.put(self.CTX + 0x134, 1)
        for who, role in ((self.P, 1), (self.Q, 0)):
            for offset, target in ((0xC, 0x100), (0x10, 0x200), (0x14, 0x400),
                                   (0x18, 0x500), (0x20, 0x600), (0x3C, 0x1000)):
                self.put(who + offset, who + target)
            self.put(who + 0x38, self.TEAM)
            self.put(who + 0x100, -1)  # CPU-controlled fixture
            self.put(who + 0x1C, 1)  # player skeleton
            self.f(who + 8, 1)
            self.put(who + 0x204, who + 0x1200)
            self.uc.mem_write(who + 0x1203, b"\x11")  # supplied action descriptor class
            self.f(who + 0x3B4, .8)
            self.f(who + 0x390, .8)
            self.put(who + 0x474, who + 0x1300)
            self.put(who + 0x1300, who + 0x1400)
            self.f(who + 0x1308, 1)
            self.f(who + 0x430, 1)
            self.put(who + 0x2C, role)
            self.uc.mem_write(who + 0x102B, bytes([72]))
            self.uc.mem_write(who + 0x1035, bytes([role]))
            self.put(who + 0x1030, who + 0x1500)
            self.put(who + 0x1504, who + 0x1600)
            self.f(who + 0x1604, 1)
            self.uc.mem_write(who + 0x1034, b"\x01")
            self.put(who + 0xA1C, who + 0x1700)
            self.put(who + 0x1704, who + 0x1710)
            self.uc.mem_write(who + 0x1710, b"\x12")
            self.put(who + 0x910, who + 0x1800)
            self.vec(who + 0x530, (0, 0, -400 if who == self.Q else -200, 1))
        # Uniform cached ratings/fatigue inputs; 17B010 itself runs natively.
        for attribute in range(28):
            self.f(0xAA43B8 + attribute * 32, .8)
        self.uc.mem_write(0xAAB8C0, struct.pack("<20f", *([.5] * 20)))
        self.seed_rng(0x100000)

    def seed_rng(self, mantissa):
        """Supply a valid 55-word native RNG ring, not a replacement RNG callee."""
        self.put(0xE5FCA0, 1)
        self.put(0xE5FCA4, 0)
        self.uc.mem_write(0xE5FCA8, bytes(55 * 8))
        self.put(0xE5FCA8, mantissa)

    def run(self, start, end, *, count=200000, timeout_us=5_000_000):
        self.trace.clear()
        self.counts.clear()
        self.uc.emu_start(start, end, timeout=timeout_us, count=count)
        if self.uc.reg_read(x86.UC_X86_REG_EIP) != end:
            raise AssertionError(f"Native probe exceeded its bound: {list(map(hex, self.trace))}")

    def call(self, address, args=(), *, fp=False, count=200000,
             timeout_us=5_000_000, **registers):
        self.uc.mem_write(self.STOP, (b"\xd9\x1d" + struct.pack("<I", self.OUT + 0xF0) +
                                     b"\xf4") if fp else b"\xf4")
        self.put(self.SP, self.STOP)
        for index, value in enumerate(args):
            writer = self.f if isinstance(value, float) else self.put
            writer(self.SP + 4 + index * 4, value)
        self.uc.reg_write(x86.UC_X86_REG_ESP, self.SP)
        for name, value in registers.items():
            self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name.upper()), value)
        self.run(address, self.STOP + (7 if fp else 1), count=count, timeout_us=timeout_us)
        return self.rf(self.OUT + 0xF0) if fp else self.uc.reg_read(x86.UC_X86_REG_EAX)

    def route(self, position, velocity, *, kind=1, role=1, direction=1, line=0):
        if direction not in (-1, 1) or role not in (1, 2, 3):
            raise ValueError("Use field direction -1/1 and HB/FB/WR role 1/2/3")
        px, pz = position[0] * direction, line + position[1] * direction
        vx, vz = velocity[0] * direction, velocity[1] * direction
        self.f(self.TEAM + 0x204, direction)
        self.f(self.CTX + 0x18, line)
        self.vec(self.BALL + 0x100, (0, 180, line - 400 * direction, 1))
        self.vec(self.Q + 0x530, (0, 0, line - 400 * direction, 1))
        self.put(self.P + 0x2C, role)
        self.uc.mem_write(self.P + 0x1035, bytes([role]))
        self.vec(self.P + 0x530, (px, 0, pz, 1))
        self.vec(self.P + 0x540, (vx, 0, vz, 0))
        self.vec(self.OUT, (px, 0, pz, 1))
        # One native prediction segment, current clock 1.0, end clock 10.0.
        record = 0xC16590
        self.f(record + 8, 0)
        self.f(record + 12, 10)
        self.f(record + 16, px + vx * 9)
        self.f(record + 20, pz + vz * 9)
        self.put(record + 24, kind)
        self.f(record + 0x8C, 0)
        self.f(record + 0x90, 0)
        self.put(record + 0x94, 0)
        # Native fallback uses clip average velocity, rate and facing.
        self.f(self.P + 0x141C, vx)
        self.f(self.P + 0x1420, vz)

    def target(self, hold=.5):
        time = self.call(0x2DA8E0, (self.BALL, 0., self.OUT + 0x20, self.OUT,
                         self.OUT + 0x30, float(hold), self.OUT + 0x34, 0),
                         ecx=self.Q, edx=self.P, fp=True)
        return {"time": time, "point": self.vector(self.OUT),
                "heading": self.get(self.OUT + 0x30),
                "predictor_calls": self.counts[0x2266A0],
                "fallback_calls": self.counts[0x2F4350]}

    def flight(self, time):
        self.call(0x1CBDB0, (float(time), 0., 0., 1, 0), ecx=self.BALL, edx=self.OUT)
        self.call(0x1CC820, (float(time),), ecx=self.BALL, edx=self.OUT + 0x100)
        endpoint = self.vector(self.OUT + 0x100)
        samples = []
        for frame in range(math.ceil(time * 60) + 1):
            at = min(frame / 60, time)
            self.call(0x1CC820, (float(at),), ecx=self.BALL, edx=self.OUT + 0x100)
            samples.append({"time": at, "ball": self.vector(self.OUT + 0x100)})
        return {"endpoint": endpoint, "samples_60hz": samples}

    def initialize_catches(self):
        # Exact LO_res transforms lhand=17,parent=16 and rhand=22,parent=21.
        # See EXPECTED_AXIS_BITS and extract_player_axes in the existing pose
        # validator. Zero BSS here produces NaNs, not a valid catch envelope.
        axes = ((0x410FACE0, 0xBEB8A406, 0x40D16DA0, 17, 16),
                (0xC10F9F2E, 0xBEB8B701, 0x40D190E9, 22, 21))
        for side, (a, b, c, hand, parent) in enumerate(axes):
            self.uc.mem_write(0xB65BA0 + side * 32,
                              struct.pack("<8I", a, b, c, 0, hand, parent, 0, 0))
        self.put(0xE60268, self.P)
        self.call(0x1E3070, count=20_000_000, timeout_us=55_000_000)
        self.catch_init_calls = self.counts[0x1E2660]
        self.catch_initialized = True
        rows = self.catch_records()
        if not all(all(math.isfinite(v) for v in row["hand_point"]) for row in rows):
            raise AssertionError("Native catch metadata contains non-finite hand positions")
        return rows

    def catch_records(self):
        if not self.catch_initialized:
            raise ValueError("Run the native catch metadata initializer first")
        rows = []
        for table in (0xABE100, 0xAC0E70, 0xABE830):
            for bucket in range(6):
                count, start = self.get(table + bucket * 8), self.get(table + bucket * 8 + 4)
                for index in range(count):
                    address = start + index * 0x70
                    rows.append({"table": table, "bucket": bucket, "record": address,
                                 "animation": self.get(address), "flags": self.get(address + 4),
                                 "hand_point": self.vector(address + 0x20),
                                 "event_gap": self.rf(address + 0x4C),
                                 "event_31": self.rf(address + 0x5C)})
        return rows

    def select(self, *, flag=False, role=1, ball=(0, 137.16, 100), velocity=(0, 0, -250)):
        if not self.catch_initialized:
            raise ValueError("Run the native catch metadata initializer first")
        self.put(self.P + 0x2C, role)
        self.uc.mem_write(self.P + 0x1035, bytes([role]))
        self.put(self.P + 0x28C, 0x800000 if flag else 0)
        self.vec(self.BALL + 0x100, (*ball, 1))
        self.vec(self.BALL + 0x110, (*velocity, 0))
        self.seed_rng(0x100000)
        found = self.call(0x1E7410, (self.P, 0, self.BALL, 0, 0, self.OUT + 0x200))
        record = self.get(self.OUT + 0x200)
        return {"accepted": bool(found), "record": record,
                "event_gap": self.rf(record + 0x4C) if record else None,
                "selection": bytes(self.uc.mem_read(self.OUT + 0x200, 80)).hex()}

    def event_gate(self, delta, mask=0x8000, *, role=1, action=5, flags=0x400000):
        record = self.OUT + 0x500  # deliberately supplied gate-only record
        self.put(self.P + 0x2C, role)
        self.uc.mem_write(self.P + 0x1203, bytes([action]))
        self.put(self.P + 0x2D0, record)
        self.put(record + 4, flags)
        self.f(record + 0x4C, 0)
        self.f(self.P + 0x2E4, delta)
        self.f(self.P + 0x208, 0)
        return self.call(0x1E6360, ecx=self.P, edx=mask)

    def release_filter(self, mantissa, *, role=1, depth=0):
        """Actual 2DAF10 basic-block slice, not a complete throw release."""
        self.seed_rng(mantissa)
        self.put(self.P + 0x2C, role)
        self.uc.mem_write(self.P + 0x1035, bytes([role]))
        self.put(self.P + 0x28C, 0)
        self.put(self.SP + 0xC, self.P)
        self.f(self.SP + 0x38, depth)
        self.uc.reg_write(x86.UC_X86_REG_ESP, self.SP)
        self.run(0x2DB0F7, 0x2DB1B7)
        return {"probability": self.rf(self.SP + 8),
                "flag": bool(self.get(self.P + 0x28C) & 0x800000)}


def replay(payload: bytes) -> dict:
    machine = NativeMachine(payload)
    rows = []
    for scenario in scenarios():
        for direction in (1, -1):
            for role in (1, 2, 3):
                machine.route(scenario.position, scenario.velocity, kind=scenario.kind,
                              role=role, direction=direction)
                target = machine.target()
                flight = machine.flight(target["time"])
                rows.append({"route": scenario.route, "timing": scenario.timing,
                             "role": role, "direction": direction, "hold": .5,
                             "supplied_position_cm": scenario.position,
                             "supplied_velocity_cm_s": scenario.velocity,
                             "supplied_segment_kind": scenario.kind,
                             "target": target, "flight": flight})
    records = machine.initialize_catches()
    machine.route((0, 0), (0, 0))
    selections = [{"role": role, "filter_flag": flag, **machine.select(role=role, flag=flag)}
                  for role in (1, 2, 3) for flag in (False, True)]
    event_gates = [{"role": role, "delta": delta,
                    "accepted": bool(machine.event_gate(delta, role=role))}
                   for role in (1, 2, 3) for delta in (-.151, -.149, 0., .149, .151)]
    release_filters = [{"role": role, "rng_mantissa": mantissa,
                        **machine.release_filter(mantissa, role=role)}
                       for role in (1, 2, 3) for mantissa in (0, 0x700000)]
    return {"schema": "nfl2k5.back_throws.native_components.v1",
            "label": "EXPERIMENTAL / UNWITNESSED", "source_sha256": machine.source_sha256,
            "gameplay_patch": False, "hold_reason": HOLD_REASON, "full_frame_replays": 0,
            "supplied_route_scenarios": 15, "native_target_launch_runs": len(rows),
            "limits": __doc__, "trajectories": rows, "catch_records": records,
            "fixture": {"snap_clock_s": 1., "receiver_height_inches": 72,
                        "cached_rating_inputs": .8, "factor_inputs": .5,
                        "controller": "CPU", "manual_lead": False,
                        "release_y_cm": 180, "line_z_cm": 0},
            "catch_record_init_calls": machine.catch_init_calls,
            "selections": selections, "event_gates": event_gates,
            "release_filter_block_probes": release_filters}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xbe", nargs="?", type=Path, default=DEFAULT_XBE)
    parser.add_argument("--json", type=Path, required=True, help="new evidence receipt, never an XBE")
    args = parser.parse_args(argv)
    try:
        # Exclusive output creation refuses aliases, symlinks and existing
        # files before expensive work. All source handles close in read_retail.
        if args.json.exists() or args.json.is_symlink() or args.json.resolve() == args.xbe.resolve():
            raise ValueError("Receipt output must be a new file distinct from the input")
        payload = read_retail(args.xbe)
        result = replay(payload)
        with args.json.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
        print(f"Wrote {result['native_target_launch_runs']} native component runs; "
              "0 full-frame replays. " + HOLD_REASON)
        return 0
    except (OSError, ValueError, RuntimeError, AssertionError, NativeExecutionError) as exc:
        print(f"back throws research: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
