"""Two native-moving actors on a supplied go command; no game/animation witness.

Both raw Speed bytes pass FUN_179840's native normalization, then feed the
effective locomotion cache. Fatigue/injury/difficulty are held neutral; the
whole roster-cache updater is not run. Both actors start at rest and use the
same synthetic straight clip from TrailFrame. The WR receives a constant go
command, not a route-script scheduler. The CB runs the real man planner.
No Python position or velocity writes occur after initialization.
"""
from __future__ import annotations

import math

from tests.nfl2k5_coverage_trail_frame import DT, YARD, TrailFrame

COLUMNS = ("frame", "wr_yards", "cb_yards", "wr_x_yards", "cb_x_yards",
           "signed_gap_yards", "distance_yards", "wr_command", "cb_command",
           "cb_throttle", "cb_heading", "wr_speed_yards_s", "cb_speed_yards_s")


class SpeedFrame(TrailFrame):
    def __init__(self, payload, *, cb_speed=83, wr_speed=93, cushion=2, direction=1):
        super().__init__(payload, defender=(0, cushion * YARD), heading=32768,
                         speed=cb_speed / 100, agility=.8, direction=direction)
        # The inherited write observer records every bone write; the measured
        # transforms are read after native completion. Disabling this observer
        # changes no instruction or guest memory. Leaf tracking remains active.
        self.uc.hook_del(self.frame_write_hook)
        self.place(self.target, 0, 0, 0, 0)
        self.place(self.p, 0, cushion * YARD * direction, 0, 0)
        self.f32(self.GAME + 0x18, 0)  # LOS in this controlled component fixture
        self.put(0xE60268, self.target)
        self.put(self.target + 0x30, self.p)
        self.put(self.p + 0x30, 0)
        for who, rating, heading in ((self.target, wr_speed, 0 if direction > 0 else 32768),
                                     (self.p, cb_speed, 32768 if direction > 0 else 0)):
            roster = self.get(who + 0x3c)
            self.uc.mem_write(roster + 0x35, bytes([3 if who == self.target else 4]))  # WR / CB
            self.uc.mem_write(who + 0x2c, bytes([9 if who == self.target else 18]))  # formation roles
            self.uc.mem_write(roster + 0x36, bytes([rating]))
            self.uc.mem_write(roster + 0x2a, bytes([50]))  # 200 lb, equal agility
            self.component(0x179840, ecx=roster, edx=1)
            self.component(self.CALLBACK + 0xe0)
            self.f32(who + 0xab4, self.readf(self.SCALAR))
            for offset in (0x954, 0x958):
                self.f32(who + offset, 0)
            self.f32(who + 0x110, 1)
            self.put(who + 0x114, heading)
            for offset in (0x90c, 0x910, 0xc28, 0xb50):
                self.put(who + offset, heading)
        self.effective_speeds = [self.readf(who + 0xab4) for who in (self.target, self.p)]

    def advance(self, frame):
        self.put(0xB71D10, frame + 1)
        self.f32(0xB71D00, frame * DT)
        self.f32(0xB71D0C, DT)
        old = [(self.readf(who + 0xb30), self.readf(who + 0xb38))
               for who in (self.target, self.p)]
        self.component(0x1A4830, ecx=self.p)
        self.component(0x1CD5D0, ecx=self.target)
        self.component(0x1CD5D0, ecx=self.p)
        self.component(0x28DFE0)
        self.component(0x218010, esi=self.target)
        self.component(0x218010, esi=self.p)
        self.component(0x28E360)
        positions = [(self.readf(who + 0xb30), self.readf(who + 0xb38))
                     for who in (self.target, self.p)]
        (wx, wz), (cx, cz) = positions
        velocities = [math.dist(a, b) / DT / YARD for a, b in zip(old, positions)]
        return [frame, wz * self.direction / YARD, cz * self.direction / YARD,
                wx * self.direction / YARD, cx * self.direction / YARD,
                (wz-cz) * self.direction / YARD, math.dist(*positions) / YARD,
                self.readf(self.target + 0x954), self.readf(self.p + 0x954),
                self.readf(self.p + 0x110), self.get(self.p + 0xb50), *velocities]


def replay(payload, **kwargs):
    m = SpeedFrame(payload, **kwargs)
    rows, samples = [], {}
    for frame in range(600):
        row = m.advance(frame)
        for mark in (10, 20, 30, 40):
            if str(mark) not in samples and row[1] >= mark:
                previous = rows[-1]
                ratio = (mark - previous[1]) / (row[1] - previous[1])
                samples[str(mark)] = dict(
                    frame=frame, time_s=(frame + ratio) * DT,
                    signed_gap_yards=previous[5] + ratio * (row[5] - previous[5]),
                    distance_yards=previous[6] + ratio * (row[6] - previous[6]))
        rows.append(row)
        if len(samples) == 4:
            break
    if len(samples) != 4 or m.executed_leaves:
        raise AssertionError(f"Incomplete native replay: samples={samples}, leaves={m.executed_leaves}")
    return dict(rows=rows, samples=samples, effective_speeds=m.effective_speeds,
                reached_stub_leaves=sorted(m.executed_leaves))
