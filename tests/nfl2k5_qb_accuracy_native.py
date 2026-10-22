"""Bounded native fixture for the b777 QB accuracy owner (nfl2k5_qb_accuracy). No game boot.

Unicorn runs the game's own pass chain from the supplied default.xbe: target/lead solver 0x2DA8E0, accuracy routine
0x2D9700 (and, when installed, the owner's cave), launch 0x1CBDB0 and ball flight 0x1CC820. Nothing in that chain is
stubbed. The fixture supplies: one straight route segment for the receiver (he keeps his velocity), the QB's position,
his root-motion velocity on the run (animation flag 0x08 in [QB+0x14], read by 0x2D8E10), the pocket set point the
play setup stores at 0xC8F280 (state 0xC8F290 = 0), human or CPU control, cached effective ratings (Pass Accuracy =
attribute 5, arm = 6, composure = 21, scramble = 25), no pass rushers, and a seeded native RNG ring.

Field direction +1, line of scrimmage at z = 0, yards = 91.44 cm.
"""
from __future__ import annotations

import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.nfl2k5_back_throws_replay import NativeMachine  # noqa: E402

YD = 91.44
ATTR = 0xAA43B8
ACCURACY, ARM, COMPOSURE, SCRAMBLE = 5, 6, 21, 25
HOOK, RESUME = 0x2D9F18, 0x2D9F1F

# Receiver at (x, depth) yd from the line at release, moving (vx, vz) yd/s.
ROUTES = {
    "drag3": (-4., 3., 7.5, 0.), "drag5": (-6., 5., 7.5, 0.), "drag5_back": (6., 5., -7.5, 0.),
    "out5": (8., 5., 7.0, -0.5), "out10": (10., 10., 7.0, -0.5), "out14": (12., 14., 7.0, -0.5),
    "out10_left": (-10., 10., -7.0, -0.5), "slant5": (-10., 4., 5.5, 5.5), "slant8": (9., 7., -5.5, 5.5),
    "dig12": (-8., 12., 7.5, 0.), "curl10": (8., 10., 0., -1.), "flat2": (2., 1., 7., 1.), "hitch5": (15., 5., 0., 0.),
    "seam20": (-6., 20., 0., 9.), "go30": (14., 30., 0., 9.5), "post25": (-10., 25., 4., 8.),
}
DEEP_ROUTES = ("seam20", "go30", "post25")
QB_STATES = ("set", "roll_human", "roll_cpu")


SCREEN_LEAD_VA = 0x226834   # the owner's screen-lead operand inside the pinned predictor span 0x2266A0


class AccuracyMachine(NativeMachine):
    def __init__(self, payload):
        # NativeMachine pins the retail predictor (0x2266A0) and lead solver (0x2DA8E0) spans; the owner edits one
        # operand in the first (screen lead) and the solver's placement tail in the second (b777 qb4 quick lead).
        # Load retail bytes for the pin check, then the payload's own bytes (retail or the owner's exact edit).
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core.nfl2k5_qb_accuracy import LEAD
        image = XbeImage(payload)
        buf = bytearray(payload)
        restore = []
        offset = image.offset(SCREEN_LEAD_VA, 1)
        operand = payload[offset:offset + 1]
        if operand not in (b"\x09", b"\x20"):
            raise ValueError("foreign screen-lead operand")
        buf[offset:offset + 1] = b"\x09"
        restore.append((SCREEN_LEAD_VA, operand))
        _name, lead_va, lead_retail, _label = LEAD
        offset = image.offset(lead_va, len(lead_retail))
        tail = payload[offset:offset + len(lead_retail)]
        if tail != lead_retail and not (tail[0] == 0xE9 and tail[5:] == b"\x90" * (len(lead_retail) - 5)):
            raise ValueError("foreign quick-lead placement tail")
        buf[offset:offset + len(lead_retail)] = lead_retail
        restore.append((lead_va, tail))
        super().__init__(bytes(buf))
        self.uc.mem_protect(0x11000, 0x410000, __import__("unicorn").UC_PROT_ALL)
        for va, raw in restore:
            self.uc.mem_write(va, raw)
        self.uc.mem_protect(0x11000, 0x410000, __import__("unicorn").UC_PROT_READ | __import__("unicorn").UC_PROT_EXEC)
        self.put(self.TEAM + 12, self.TEAM + 0x1000)
        self.put(self.TEAM + 0x100C, self.TEAM + 0x1100)
        self.capture = {}
        self.uc.hook_add(__import__("unicorn").UC_HOOK_CODE, self._capture, begin=HOOK, end=RESUME)

    def _capture(self, uc, address, _size, _user):
        from unicorn import x86_const as x86
        if address not in (HOOK, RESUME):
            return
        esp = uc.reg_read(x86.UC_X86_REG_ESP)
        regs = {name: uc.reg_read(getattr(x86, "UC_X86_REG_" + name)) for name in
                ("EAX", "ECX", "EDX", "EBX", "ESP", "EBP", "ESI", "EDI")}
        fpsw = uc.reg_read(x86.UC_X86_REG_FPSW)
        if address == HOOK:
            self.capture["entry"] = dict(regs=regs, top=(fpsw >> 11) & 7, pass_accuracy=self.rf(esp + 0x30))
        else:
            self.capture["exit"] = dict(regs=regs, top=(fpsw >> 11) & 7, miss_cm=self.rf(esp + 0x14),
                                        height_error=self.rf(esp + 0x18), heading=regs["ESI"] & 0xFFFF)

    def seed_complete_rng(self, seed):
        self.put(0xE5FCA0, 54)
        self.put(0xE5FCA4, 23)
        values = []
        for _ in range(55):
            seed = (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
            values.append(seed)
        self.uc.mem_write(0xE5FCA8, struct.pack("<55Q", *values))

    def ratings(self, accuracy=.8, arm=.9, composure=.8, scramble=.3, others=.8):
        for attribute in range(28):
            self.f(ATTR + attribute * 8, others)
            self.f(ATTR + attribute * 8 + 4, 0.)
        for attribute, value in ((ACCURACY, accuracy), (ARM, arm), (COMPOSURE, composure), (SCRAMBLE, scramble)):
            self.f(ATTR + attribute * 8, value)

    def quarterback(self, state):
        """set: in the pocket at the set point; roll_*: 6 yd/s to the right, 3 yd from the set point."""
        if state == "set":
            x, z, vx, human = 0., -7 * YD, 0., False
        elif state in ("roll_human", "roll_cpu"):
            x, z, vx, human = -3 * YD, -6 * YD, 6 * YD, state == "roll_human"
        else:
            raise ValueError(state)
        self.vec(self.Q + 0x530, (x, 0., z, 1.))
        self.vec(self.BALL + 0x100, (x, 180., z, 1.))
        animation = self.Q + 0x400
        self.uc.mem_write(animation, bytes([0x08 if vx else 0x00]))
        self.put(animation + 0x74, self.Q + 0x1900)
        self.put(self.Q + 0x1900, self.Q + 0x1940)
        self.f(self.Q + 0x1908, 1.)
        self.f(self.Q + 0x1940 + 0x1C, vx)
        self.f(self.Q + 0x1940 + 0x20, 0.)
        self.f(animation + 0x2C, 0.)
        self.f(animation + 0x30, 1.)
        self.vec(0xC8F280, (0., 0., -7 * YD, 1.))
        self.put(0xC8F290, 0)
        self.put(self.Q + 0x100, 0 if human else 0xFFFFFFFF)
        self.put(0xE5FEA0, 1 if human else 0)

    def throw(self, route, *, state="set", accuracy=.8, seed=7):
        rx, rz, rvx, rvz = ROUTES[route]
        self.ratings(accuracy=accuracy)
        self.quarterback(state)
        hold = 0. if route in ("go30", "post25") else 1.
        self.route((rx * YD, rz * YD), (rvx * YD, rvz * YD), kind=1, role=3, direction=1, line=0.)
        self.put(self.P + 0x2C, 3)
        self.uc.mem_write(self.P + 0x1035, bytes([3]))
        self.put(0xE5FC00, self.BALL)
        self.seed_complete_rng(seed)
        self.capture = {}
        time = self.call(0x2DA8E0, (self.BALL, 0., self.OUT + 0x20, self.OUT, self.OUT + 0x30, float(hold),
                                    self.OUT + 0x34, 0), ecx=self.Q, edx=self.P, fp=True)
        aim = self.vector(self.OUT)
        radius = self.rf(self.OUT + 0x20)
        self.put(self.TEAM + 12, self.TEAM + 0x1000)
        self.put(self.TEAM + 0x100C, self.TEAM + 0x1100)
        self.call(0x2D9700, (self.P, radius, self.OUT, self.OUT + 0x200, self.OUT + 0x220, self.OUT + 0x224,
                             self.OUT + 0x228, float(hold)), eax=self.Q)
        launch = (self.get(self.OUT + 0x220), self.rf(self.OUT + 0x224), self.get(self.OUT + 0x228))
        self.call(0x1CBDB0, (time, *launch, 0), ecx=self.BALL, edx=self.OUT + 0x200)
        self.call(0x1CC820, (time,), ecx=self.BALL, edx=self.OUT + 0x300)
        end = self.vector(self.OUT + 0x300)
        wx, wz = rx + rvx * time, rz + rvz * time
        ex, ez = end[0] / YD, end[2] / YD
        speed = math.hypot(rvx, rvz) or 1.
        ux, uz = rvx / speed, rvz / speed
        dx, dz = ex - wx, ez - wz
        return {"route": route, "state": state, "accuracy": accuracy, "seed": seed, "flight_s": time,
                "radius_yd": radius / YD, "aim": (aim[0] / YD, aim[2] / YD), "land": (ex, ez), "receiver": (wx, wz),
                "miss_yd": math.hypot(dx, dz), "ahead_yd": dx * ux + dz * uz, "ball_height_cm": end[1],
                "launch": launch, "raw": (time, *end[:3]), "capture": dict(self.capture)}


def screen_target(machine, position, velocity, hold=1., *, spot=None, due=None):
    """A screen receiver (route kind 9, HB role) at ``position`` yd moving ``velocity`` yd/s; QB set 9 yd deep.

    b778 qa1: a moving receiver carries the game's moving animation flag (0x08 at [P+0x14]), as every running player
    does in the game; the retail kind-9 shortcut then leaves the lead to the target routine's root-motion velocity
    fallback 0x2F4350 (the clip velocity this fixture sets equals ``velocity``). ``spot`` (yd) and ``due`` (seconds from
    now) replace the default far straight route segment with one that ends at his screen spot."""
    machine.ratings()
    machine.quarterback("set")
    machine.vec(machine.Q + 0x530, (0., 0., -9 * YD, 1.))
    machine.vec(machine.BALL + 0x100, (0., 180., -9 * YD, 1.))
    machine.route((position[0] * YD, position[1] * YD), (velocity[0] * YD, velocity[1] * YD), kind=9, role=1,
                  direction=1, line=0.)
    if spot is not None:
        record = 0xC16590
        machine.f(record + 12, 1. + due)
        machine.f(record + 16, spot[0] * YD)
        machine.f(record + 20, spot[1] * YD)
    machine.put(machine.P + 0x2C, 1)
    machine.uc.mem_write(machine.P + 0x1035, bytes([1]))
    machine.uc.mem_write(machine.P + 0x400, bytes([0x08 if any(velocity) else 0x00]))
    result = machine.target(hold)
    time = result["time"]
    return {"flight_s": time, "aim": (result["point"][0] / YD, result["point"][2] / YD),
            "receiver": (position[0] + velocity[0] * time, position[1] + velocity[1] * time),
            "velocity_fallback": result["fallback_calls"]}


def summary(rows):
    import statistics
    n = len(rows)
    misses = sorted(r["miss_yd"] for r in rows)
    return {"throws": n, "mean_miss_yd": round(statistics.mean(misses), 3),
            "mean_ahead_yd": round(statistics.mean(r["ahead_yd"] for r in rows), 3),
            "p90_miss_yd": round(misses[int(.9 * n)], 3),
            "within_1yd_pct": round(100 * sum(m <= 1. for m in misses) / n, 1),
            "below_waist_pct": round(100 * sum(r["ball_height_cm"] < 100 for r in rows) / n, 1)}
