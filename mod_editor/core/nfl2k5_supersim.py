"""EXPERIMENTAL / UNWITNESSED native-simulator stop-policy prototype.

This is a host reference component, not an installed XBE patch. The retail
simulator can import part of a live game and step to a boundary. Its finalizer
ends that game; its scenario restore is not a complete live-state inverse.
Consequently this module deliberately provides no apply() or live-state writer.
See ASTRA_MYCAREER_SUPERSIM_DRAFT_REPORT.md for the bounded instruction proofs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import struct
from typing import Callable

OWNER = "nfl2k5_supersim"
REQUESTS = ()  # No installed code, hook, allocator state or budget claim.
RUNTIME_READY = False
INIT = 0x10B280
STEP = 0x10B250
FINALIZE = 0x1053B0
SCENARIO_RESTORE = 0x10BD80
PAUSE_HANDLER = 0x6EFE0
SIM_TEAMS = (0xA96B68, 0xA96E80)
MAX_STEPS = 1024
TICKER_ROWS = 32
LIVE_BLOCKER = (
    "Live resume is not proved: native initialization clears existing stat "
    "fields, and the scenario helper does not restore all stats, injuries, "
    "penalties, timeouts, fatigue and momentum or re-enter live play safely."
)


class SupersimError(ValueError):
    pass


class StopAt(str, Enum):
    NEXT_POSSESSION = "next_possession"
    NEXT_QUARTER = "next_quarter"
    END_OF_HALF = "end_of_half"


@dataclass(frozen=True)
class Snapshot:
    """Abstract sim state. Quarter/down are zero based; clock is a fraction.

    ``spot`` is yards from the opponent's end line, not the live field's cm.
    ``kind == 0`` means scrimmage; special-team transitions are separate ticks.
    A native tick may traverse multiple internal callbacks and is not a frame.
    """
    quarter: int
    clock: float
    offense: int
    kind: int
    down: int
    distance: float
    spot: float
    score: tuple[int, int]
    log_count: int

    def validate(self):
        if not (type(self.quarter) is int and 0 <= self.quarter <= 5 and
                type(self.offense) is int and self.offense in (0, 1) and
                type(self.kind) is int and 0 <= self.kind <= 4 and
                type(self.down) is int and 0 <= self.down <= 4 and
                type(self.log_count) is int and 0 <= self.log_count <= 768):
            raise SupersimError("invalid native simulator state")
        if not all(type(n) in (int, float) and math.isfinite(n)
                   for n in (self.clock, self.distance, self.spot)):
            raise SupersimError("non-finite native simulator state")
        # The native terminal tick can retain a negative clock overrun. Keep
        # it as evidence; clamping it would hide why this is not live state.
        if not (-1 <= self.clock <= 1.01 and -200 <= self.spot <= 200 and
                -200 <= self.distance <= 200):
            raise SupersimError("native simulator scalar outside probe bounds")
        if not (type(self.score) is tuple and len(self.score) == 2 and
                all(type(n) is int and 0 <= n <= 999 for n in self.score)):
            raise SupersimError("invalid native score")
        return self


def read_snapshot(read: Callable[[int, int], bytes],
                  score: Callable[[int], int]) -> Snapshot:
    """Read RAM; use native 0x250DD0(side, category=0) for each score.

    All reads are fixed and bounded. No native address is allocated or written.
    The caller must already own and pin its instruction/memory environment.
    """
    def word(address):
        return struct.unpack("<I", read(address, 4))[0]

    def real(address):
        return struct.unpack("<f", read(address, 4))[0]

    pointer = word(0xA9719C)
    if pointer not in SIM_TEAMS:
        raise SupersimError("simulator is not initialized")
    return Snapshot(word(0xA971F0), real(0xA971F8), SIM_TEAMS.index(pointer),
                    word(0xA971C0), word(0xA971E8), real(0xA971FC),
                    real(0xA97200), (score(0), score(1)),
                    word(0xE53804)).validate()


@dataclass(frozen=True)
class Tick:
    number: int
    native_result: int
    state: Snapshot


@dataclass(frozen=True)
class Run:
    reason: str
    steps: int
    initial: Snapshot
    final: Snapshot
    ticker: tuple[Tick, ...]
    resume_proved: bool = False


def advance(tick: Callable[[], int], read: Callable[[], Snapshot], *,
            until: StopAt | str, target_side: int | None = None,
            max_steps: int = 512, cancelled: Callable[[], bool] = lambda: False) -> Run:
    """Bound native ticks at a possession, quarter or half in abstract state.

    For possession, target the player's club for an offensive MyPlayer and the
    opponent for a defensive MyPlayer. Kickoffs/tries never count as scrimmage.
    A budget/cancel/error outcome may have advanced sim RAM and must not resume
    live play. The caller owns rollback. This function never calls FINALIZE.
    """
    try:
        until = StopAt(until)
    except (TypeError, ValueError) as exc:
        raise SupersimError("unknown stop condition") from exc
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS:
        raise SupersimError("step budget must be 1..1024")
    if until == StopAt.NEXT_POSSESSION and (type(target_side) is not int or target_side not in (0, 1)):
        raise SupersimError("possession requires a target side")
    initial = read().validate()
    period = (initial.quarter + 1 if until == StopAt.NEXT_QUARTER else
              2 if initial.quarter < 2 else 4 if initial.quarter < 4 else None)

    def reached(state):
        if until == StopAt.NEXT_POSSESSION:
            return state.offense == target_side and state.kind == 0
        # In overtime, "end of half" means the native end of the game.
        return period is not None and state.quarter >= period

    if reached(initial):
        return Run("already_at_target", 0, initial, initial, ())
    rows: list[Tick] = []
    current = initial
    for number in range(1, max_steps + 1):
        if cancelled():
            return Run("cancelled", number - 1, initial, current, tuple(rows))
        result = tick()
        current = read().validate()
        rows.append(Tick(number, result, current))
        rows = rows[-TICKER_ROWS:]
        if result == 5:
            reason = "game_end"
        elif result not in (1, 2, 3, 4):
            reason = "native_error"
        elif reached(current):
            reason = "target"
        else:
            continue
        return Run(reason, number, initial, current, tuple(rows))
    return Run("budget", max_steps, initial, current, tuple(rows))


def require_live_resume():
    raise SupersimError(LIVE_BLOCKER)
