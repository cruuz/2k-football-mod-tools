#!/usr/bin/env python3
"""Native catch-selection fixture for the defender catch snap limit. NOT a game frame.

Runs the game's own catch metadata initializer (0x1E3070), the catch selector (0x1E78A0), the plan setup (0x1E57B0),
the catch action's begin callback (0x1E7B80), the animation sampler (0x218010) and the catch update with its alignment
helper (0x1E2CF0 / 0x1A8940) on supplied objects in Unicorn. Nothing is replaced: no callee, no RNG. Collision, task
scheduling, locomotion, catch probability production and possession are outside this fixture, so a selected plan is
an eligible catch attempt, never a completed interception.

Positions are supplied: a CPU cornerback (or receiver) facing +Z, uniform cached ratings, catch context 0.8, a 0.45 s
forward-pass flight from (0, 180, 2200) to (0, 137.16, 1000) cm; "front", "beside" and "behind" place the player
that many yards from the arrival point, relative to his heading (the ai3-pickwarp grid of 10/11, job/ai3-pickwarp
6a1f09ad9, which this module extends to run on any executable image and to take the owner's gates as parameters).

Any default.xbe image is accepted (retail, a released SOFTDRINK executable, or one with the owner applied); the
image's sha256 is recorded, never trusted. The machine's entry-span pins still apply (a foreign executable fails).
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import nfl2k5_back_throws_replay as _base  # noqa: E402
from tools.nfl2k5_back_throws_replay import NativeMachine, uc_module, x86  # noqa: E402

# The shared machine pins fourteen routine spans of the retail executable. Only the ones this fixture runs are
# enforced here (catch metadata, ball flight, catch families); the target-planning spans belong to the back-throw
# probes and are changed by released SOFTDRINK owners, which must not stop the catch fixture from running on them.
CATCH_PIN_ADDRESSES = frozenset((0x1CBDB0, 0x1CC820, 0x1E7410, 0x1E6600, 0x1E38D0, 0x1E3070, 0x1E2660, 0x1E6310,
                                 0x1E6360, 0x1C6100))


def _machine(payload: bytes) -> NativeMachine:
    saved = dict(_base.CODE_PINS)
    kept = {key: digest for key, digest in saved.items() if key[0] in CATCH_PIN_ADDRESSES}
    _base.CODE_PINS.clear()
    _base.CODE_PINS.update(kept)
    try:
        return NativeMachine(payload)
    finally:
        _base.CODE_PINS.clear()
        _base.CODE_PINS.update(saved)

CM_PER_YARD = 91.44
DIRECTIONS = ("front", "beside", "behind")
DISTANCES = (1, 2, 3, 4)
# Record layout of a catch plan (20 dwords, filled by the selector 0x1E78A0).
REC_CLIP, REC_RATE, REC_TIME, REC_HEADING = 0x00, 0x04, 0x08, 0x0C
REC_CORRECTION_X, REC_CORRECTION_Y, REC_CORRECTION_Z = 0x10, 0x14, 0x18
REC_TARGET = 0x20
REC_ACCEPTED = 0x40
# Player locomotion block ([P+0x10]) fields the setup fills (the fixture maps [P+0x10] to P+0x200).
LOCO_CORRECTION_X, LOCO_CORRECTION_Z, LOCO_DURATION = 0x2DC, 0x2E0, 0x2E4


def displacement(a, b, *, horizontal=True):
    axes = (0, 2) if horizontal else (0, 1, 2)
    return math.sqrt(sum((b[i] - a[i]) ** 2 for i in axes)) / CM_PER_YARD


class CatchSnapReplay:
    """One native machine with the catch metadata initialized; every case restores memory and CPU state first."""

    def __init__(self, payload: bytes, *, patches=()):
        """`patches` = (virtual address, bytes) written into guest memory after the catch metadata initialized and before the
        snapshot every case restores: it lets a test run ONE of the owner's hooks alone (the other restored to retail bytes)."""
        if uc_module is None:
            raise RuntimeError("unicorn is required for native instruction probes")
        self.sha256 = hashlib.sha256(payload).hexdigest()
        self.m = m = _machine(payload)
        records = m.initialize_catches()
        self.initialization = {"records_including_aliases": len(records), "native_init_calls": m.catch_init_calls}
        for address, data in patches:
            m.uc.mem_write(address, data)
        flush = getattr(m.uc, "ctl_flush_tb", None)
        if patches and flush is not None:
            flush()                                            # translated blocks must not outlive the patched bytes
        m.put(m.TEAM + 0x400, m.TEAM)
        m.put(m.TEAM + 0x408, m.TEAM + 0x500)
        m.put(m.TEAM + 0x50C, m.TEAM + 0x600)
        m.f(m.TEAM + 0x604, -1)
        m.put(0xE602C0, 4)
        m.put(0xE602B8, 14)
        m.put(m.BALL + 0x1C, 4)
        self.snapshot = [(start, bytes(m.uc.mem_read(start, end - start + 1))) for start, end, _ in m.uc.mem_regions()]
        self.cpu = m.uc.context_save()

    def reset(self):
        for address, data in self.snapshot:
            self.m.uc.mem_write(address, data)
        self.m.uc.context_restore(self.cpu)

    # ---- fixture pieces -------------------------------------------------------------------------------------------
    def channels(self):
        """Supplied idle pose and writable animation buffers, not a live dump."""
        m = self.m
        base = m.P + 0xA000
        m.put(m.P + 0x24, base + 0x3000)
        m.put(m.P + 4, base + 0x4000)
        m.put(m.P + 0x434, base + 0x1900)
        m.vec(m.P + 0x42C, (0, 1))
        m.put(m.P + 0x404, 0x1FFFFFF)
        m.put(m.P + 0x408, 0x1FFFFFF)
        m.put(m.P + 0x41C, 1)
        m.f(m.P + 0x448, 100)
        m.put(m.P + 0x5C4, 0x5CA6B8)
        for index, (field, offset) in enumerate(((0x58, 0), (0x5C, 0x40), (0x74, 0x80), (0x78, 0xC0))):
            channel = base + offset
            m.put(m.P + 0x400 + field, channel)
            m.put(channel, 0x5CA6B8)
            m.f(channel + 8, 1)
            for field2, offset2 in ((0x24, 0), (0x28, 0x100), (0x2C, 0x2A0)):
                m.put(channel + field2, base + 0x500 + index * 0x500 + offset2)

    def arrange(self, direction: str, yards: float, *, defender=True, cpu=True, human_team=False, ball_kind=4,
                heading_turn=0):
        """Restore the machine and place the player and the ball. Returns the arrival point (cm)."""
        self.reset()
        m = self.m
        cm = yards * CM_PER_YARD
        px, pz = {"front": (0, 1000 - cm), "beside": (-cm, 1000), "behind": (0, 1000 + cm)}[direction]
        team = m.TEAM + (0x400 if defender else 0)
        m.put(m.P + 0x38, team)
        m.put(team + 0x30, m.P + 0xE000 if human_team else 0)
        role = 18 if defender else 3
        m.put(m.P + 0x2C, role)
        m.uc.mem_write(m.P + 0x1035, bytes([role]))
        m.put(m.P + 0x100, 0xFFFFFFFF if cpu else 0)         # [[P+0xC]] = controller marker, -1 = CPU
        m.put(0xE602C0, ball_kind)
        m.vec(m.P + 0x530, (px, 100, pz, 1))
        m.vec(m.BALL + 0x100, (0, 180, 2200, 1))
        m.vec(m.OUT, (0, 137.16, 1000, 1))
        self.flight, self.arrival = .45, (0, 137.16, 1000)
        m.call(0x1CBDB0, (.45, 0., 0., 1, 0), ecx=m.BALL, edx=m.OUT)
        m.call(0x1CC820, (.45,), ecx=m.BALL, edx=m.OUT + 0x100)
        endpoint = m.vector(m.OUT + 0x100)
        if displacement(endpoint, (0, 137.16, 1000), horizontal=False) > .0001:
            raise AssertionError("Native flight missed the supplied arrival")
        m.seed_rng(0x100000)
        return endpoint

    def advance_ball(self, ticks: int):
        """The ball `ticks` 60 Hz ticks later on the same flight, re-aimed at the same arrival point. The player stays
        where he is, so this isolates what a plan cached `ticks` ticks ago sees when the begin callback plans it again."""
        if ticks <= 0:
            return
        m = self.m
        t = ticks / 60
        remaining = max(self.flight - t, 1 / 60)
        m.call(0x1CC820, (float(t),), ecx=m.BALL, edx=m.OUT + 0x100)
        m.vec(m.BALL + 0x100, m.vector(m.OUT + 0x100))
        m.vec(m.OUT, (*self.arrival, 1))
        m.call(0x1CBDB0, (float(remaining), 0., 0., 1, 0), ecx=m.BALL, edx=m.OUT)
        m.call(0x1CC820, (float(remaining),), ecx=m.BALL, edx=m.OUT + 0x100)

    def arrange_at(self, player_cm, arrival_cm=(0.0, 137.16, 1000.0), *, flight=0.45, context=0.8, defender=True,
                   cpu=True, human_team=False, ball_kind=4):
        """Like arrange(), with the player's ground position, the ball's arrival point, the flight time and the catch
        context supplied freely (cm, seconds, 0..1)."""
        self.reset()
        m = self.m
        team = m.TEAM + (0x400 if defender else 0)
        m.put(m.P + 0x38, team)
        m.put(team + 0x30, m.P + 0xE000 if human_team else 0)
        role = 18 if defender else 3
        m.put(m.P + 0x2C, role)
        m.uc.mem_write(m.P + 0x1035, bytes([role]))
        m.put(m.P + 0x100, 0xFFFFFFFF if cpu else 0)
        m.put(0xE602C0, ball_kind)
        m.f(m.P + 0x390, context)
        m.vec(m.P + 0x530, (player_cm[0], 100, player_cm[1], 1))
        m.vec(m.BALL + 0x100, (0, 180, 2200, 1))
        m.vec(m.OUT, (*arrival_cm, 1))
        self.flight, self.arrival = float(flight), tuple(arrival_cm)
        m.call(0x1CBDB0, (float(flight), 0., 0., 1, 0), ecx=m.BALL, edx=m.OUT)
        m.call(0x1CC820, (float(flight),), ecx=m.BALL, edx=m.OUT + 0x100)
        m.seed_rng(0x100000)

    def record(self, address=None) -> dict:
        m = self.m
        address = m.OUT + 0x200 if address is None else address
        clip = m.get(address + REC_CLIP)
        return {"clip": clip, "flags": m.get(clip + 4) if clip else None,
                "rate": m.rf(address + REC_RATE), "time": m.rf(address + REC_TIME),
                "correction": (m.rf(address + REC_CORRECTION_X), m.rf(address + REC_CORRECTION_Y),
                               m.rf(address + REC_CORRECTION_Z)),
                "accepted": m.get(address + REC_ACCEPTED), "raw": bytes(m.uc.mem_read(address, 80)).hex()}

    def select(self, request=0x55) -> dict:
        """The real selector 0x1E78A0 (ECX = player, EDX = request, one stack argument = the record)."""
        m = self.m
        out = m.OUT + 0x200
        returned = m.call(0x1E78A0, (out,), ecx=m.P, edx=request)
        row = self.record(out)
        row["returned"] = bool(returned)
        # request 0 (the probe) leaves infinities in its scratch fields by design; real catch requests never do
        if request != 0 and not all(math.isfinite(v) for v in (*row["correction"], row["rate"], row["time"])):
            raise AssertionError("Non-finite native selection")
        return row

    def plan_effects(self, out=None) -> dict:
        """What the setup left on the player's locomotion block."""
        m = self.m
        return {"stored_correction": (m.rf(m.P + LOCO_CORRECTION_X), m.rf(m.P + LOCO_CORRECTION_Z)),
                "duration": m.rf(m.P + LOCO_DURATION), "action_flags": m.get(m.P + 0x228)}

    def setup(self, replan=False):
        """The real plan setup 0x1E57B0 on the selected record (stack argument 0 = as selected, 1 = re-plan)."""
        m = self.m
        self.channels()
        m.call(0x1E57B0, (1 if replan else 0,), ecx=m.P, edx=m.OUT + 0x200)

    def run_ticks(self, ticks=42) -> dict:
        """The animation sampler and the catch update (alignment helper) at 60 Hz until the clip would complete."""
        m = self.m
        m.f(0xB71D0C, 1 / 60)
        samples = []
        stopped = False

        def stop_before_completion(uc, address, size, user):
            if address == 0x1E2F20:
                uc.emu_stop()

        boundary = m.uc.hook_add(uc_module.UC_HOOK_CODE, stop_before_completion)
        try:
            for tick in range(ticks):
                before = m.vector(m.P + 0x530)
                try:
                    m.call(0x218010, esi=m.P)
                except Exception as exc:  # the clip completion callback is outside this fixture
                    if m.uc.reg_read(x86.UC_X86_REG_EIP) == 0x1E2F20:
                        stopped = True
                        break
                    raise RuntimeError(f"native catch tick {tick} failed; trace={list(map(hex, m.trace))}") from exc
                animation = m.vector(m.P + 0x530)
                m.call(0x1E2CF0, ecx=m.P)
                after = m.vector(m.P + 0x530)
                if not all(math.isfinite(v) for v in (*animation, *after)):
                    raise AssertionError("Non-finite native motion")
                samples.append({"tick": tick, "animation_yards": displacement(before, animation),
                                "alignment_yards": displacement(animation, after),
                                "combined_yards": displacement(before, after)})
        finally:
            m.uc.hook_del(boundary)
        return {"stopped_before_completion": stopped, "ticks": len(samples),
                "max_alignment_step_yards": max((s["alignment_yards"] for s in samples), default=0.0),
                "total_alignment_yards": sum(s["alignment_yards"] for s in samples),
                "samples": samples}

    def case(self, direction, yards, *, defender=True, request=0x55, **arrange) -> dict:
        """arrange, select, and (when a plan with the accepted flag came back) set up and run the catch."""
        self.arrange(direction, yards, defender=defender, **arrange)
        selection = self.select(request)
        row = {"direction": direction, "distance_yards": yards, "defender": defender, "selection": selection,
               "motion": None}
        if selection["returned"] and selection["accepted"]:
            self.setup()
            motion = self.run_ticks()
            row["motion"] = {**self.plan_effects(), **motion}
            row["motion"]["correction_yards"] = math.hypot(*selection["correction"][::2]) / CM_PER_YARD
        return row

    def grid(self, **arrange) -> list[dict]:
        return [self.case(direction, yards, defender=defender, **arrange)
                for defender in (True, False) for direction in DIRECTIONS for yards in DISTANCES]


__all__ = ["CatchSnapReplay", "DIRECTIONS", "DISTANCES", "CM_PER_YARD", "displacement"]
