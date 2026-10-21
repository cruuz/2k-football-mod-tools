#!/usr/bin/env python3
"""b77 db1: headless deep-ball model. Where does the ball land against a streaking receiver?

Read-only native evidence, not a game session. Unicorn runs the game's own pass code in the
supplied XBE: target solver FUN_002da8e0 (receiver lead, flight time, first ceiling clamp),
accuracy pass FUN_002d9700 (second ceiling clamp), launch FUN_001cbdb0 and ball flight
FUN_001cc820. Nothing in that chain is stubbed. The fixture supplies: one straight route
prediction record (the receiver keeps his speed), the QB's effective arm in the native
attribute-6 cache, every other cached rating at .8, release 7 yd behind the line, line of
scrimmage at the offense's own 15 (so the end-line clamp never decides), seeded RNG rings.

"In stride" = the ball comes down within 2 yd (downfield) of where the receiver is when it
lands. A miss beyond 2 yd short means the receiver must stop and come back into the trailing
defender. Lateral placement (the game's 1.5 yd shoulder offset) is reported, not scored.

Profiles: ``before`` is the target XBE as given; ``after`` is the same XBE with the current
arc-by-distance profile installed in memory (``apply_arc_table``). Throws that never reach
40 yd from release must be bit-identical between the two (short and intermediate game).

  python3 tools/b77/db1_deep_ball_probe.py --target DISC_OR_XBE --receipt NEW.json
  python3 tools/b77/db1_deep_ball_probe.py --scale-80 --receipt NEW.json   # retail + Studio curves
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from tools.nfl2k5_back_throws_replay import DEFAULT_XBE, read_retail  # noqa: E402

YD = tt.YD_CM
LINE_YD = -35.0           # own 15-yard line: 85 yd of field ahead of the line
RELEASE_YD = -7.0         # QB release point behind the line
ATTR_CACHE = 0xAA43B8     # effective attribute cache: slot * 0xE4 + attribute * 8 (base, fatigue term)
ARM_ATTRIBUTE = 6         # FUN_002da8e0 calls FUN_0017b010 with edx = 6
DEEP_ARMS = (0.82, 0.86, 0.90, 0.95, 0.98)   # the disc's starting QBs span Throw Power 82..99
DEEP_DEPTHS = tuple(range(12, 23))           # receiver yards past the line at release
SPEEDS = (9.0, 9.5, 10.0)                    # yd/s, 2K5 top speed 7.0 + 3.0 * Speed rating
SEEDS = (1, 7, 19)
STRIDE_YD = 2.0


def _machine_class():
    from tools.b765.d2b_passing_probe import ThrowMachine

    class DeepBallMachine(ThrowMachine):
        def ratings(self, arm: float, others: float = .8) -> None:
            for attribute in range(28):
                self.f(ATTR_CACHE + attribute * 8, others)
                self.f(ATTR_CACHE + attribute * 8 + 4, 0.)
            self.f(ATTR_CACHE + ARM_ATTRIBUTE * 8, arm)

    return DeepBallMachine


def throw(machine, *, arm: float, depth: float, speed: float, lateral: float = 0., x: float = 0.,
          hold: float = 0., seed: int = 7) -> dict:
    """One release against a receiver ``depth`` yd past the line running ``speed`` yd/s upfield."""
    machine.ratings(arm)
    line = LINE_YD * YD
    result = machine.throw(receiver=(x * YD, depth * YD), velocity=(lateral * YD, speed * YD), kind=1,
                           hold=hold, release=RELEASE_YD * YD, seed=seed, line=line)
    flight = result["target"]["time"]
    land_x, land_z = result["endpoint"][0] / YD, (result["endpoint"][2] - line) / YD
    wr_x, wr_z = x + lateral * flight, depth + speed * flight
    return {"arm": arm, "depth": depth, "speed": speed, "lateral": lateral, "hold": hold, "seed": seed,
            "flight_s": round(flight, 4), "aim_yd": round((result["target"]["point"][2] - line) / YD, 3),
            "land_yd": round(land_z, 3), "receiver_yd": round(wr_z, 3), "short_yd": round(wr_z - land_z, 3),
            "lateral_off_yd": round(land_x - wr_x, 3),
            "release_to_land_yd": round(((land_x) ** 2 + (land_z - RELEASE_YD) ** 2) ** .5, 3),
            "raw": [result["target"]["time"], *result["endpoint"][:3]]}


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    shorts = sorted(r["short_yd"] for r in rows)
    return {"throws": n,
            "in_stride_pct": round(100 * sum(abs(s) <= STRIDE_YD for s in shorts) / n, 1),
            "short_2yd_plus_pct": round(100 * sum(s > STRIDE_YD for s in shorts) / n, 1),
            "mean_short_yd": round(statistics.mean(shorts), 2),
            "p90_short_yd": round(shorts[int(.9 * n)], 2),
            "worst_short_yd": round(shorts[-1], 2),
            "max_lateral_off_yd": round(max(abs(r["lateral_off_yd"]) for r in rows), 2)}


def deep_rows(machine) -> list[dict]:
    return [throw(machine, arm=a, depth=d, speed=v, seed=s)
            for a in DEEP_ARMS for d in DEEP_DEPTHS for v in SPEEDS for s in SEEDS]


def short_rows(machine) -> list[dict]:
    """Short and intermediate game: bullets, touch and lobs to streaks, crossers and flats."""
    rows = []
    for arm in (0.75, 0.90):
        for hold in (0., .5, 1.):
            for depth in (2, 5, 8, 11, 14):
                for speed, lateral in ((9.0, 0.), (2.0, 8.0), (2.0, -8.0), (0., 6.0)):
                    rows.append(throw(machine, arm=arm, depth=depth, speed=speed, lateral=lateral,
                                      x=-5., hold=hold))
    return rows


def cpu_gap_table(profile, arm: float = .86) -> list[dict]:
    """CPU target grid estimate (FUN_001995a0: hold 0.75 blend + 1/3 s) against the real deep lob."""
    armfrac = tt.interpolate(((0., .2), (.3, .4), (.7, .6), (.9, .925), (1., 1.)), arm)
    bullet = tt.CURVES["bulletspeed"].retail
    out = []
    for yards in (40, 45, 50, 55, 60, 65):
        lob = tt.interpolate(profile, yards)
        estimate = yards / (.75 * armfrac * (tt.interpolate(bullet, yards) - lob) + lob) + 1 / 3
        actual = yards / lob
        out.append({"yards": yards, "cpu_estimate_s": round(estimate, 3), "real_lob_s": round(actual, 3),
                    "gap_s": round(actual - estimate, 3),
                    "apex_yd": round(tt.GRAVITY_YD_S2 * actual ** 2 / 8, 2)})
    return out


def read_xbe(path: Path) -> bytes:
    with Path(path).open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        if tt.is_disc_image(Path(path)):
            offset, length = tt.image_xbe_extent(stream.fileno(), size)
        else:
            offset, length = 0, size
        if not 0 < length <= 16 * 1024 * 1024:
            raise ValueError("default.xbe exceeds 16 MiB")
        stream.seek(offset)
        payload = stream.read(length)
    if len(payload) != length:
        raise ValueError("short default.xbe read")
    return payload


def studio_scale_80(retail: bytes, *, touch_band: bool) -> bytes:
    """Retail plus the Studio's 80-yard scale, realistic flight and arc by distance, in memory."""
    settings = tt.TuningSettings(80.0, 0.0, True, True)
    patched, _ = tt.plan_patch(retail, tt.curves_for(settings))
    patched, _ = tt.apply_arc_table(patched)
    if touch_band:
        buf = bytearray(patched)
        off = tt.ARC_TABLE_VA - tt.IMAGE_BASE
        buf[off:off + tt.ARC_TABLE_CURVE.size] = tt.ARC_TABLE_CURVE.encode(tt.TOUCH_BAND_20261002_LOBSPEED)
        patched = bytes(buf)
    return patched


def compare(before: bytes, *, retail: bytes | None = None, after: bytes | None = None) -> dict:
    state = tt.arc_table_status(before)
    if after is None:
        if state not in ("retail", "legacy_high_arc", "applied"):
            raise ValueError(f"arc-by-distance sites are {state}")
        after = tt.apply_arc_table(before)[0] if state != "applied" else before
    machine = _machine_class()
    profiles = {"before": before, "after": after}
    if retail is not None:
        profiles = {"retail": retail, **profiles}
    out = {"schema": "b77.db1.deep_ball_probe.v1", "claim": "native components on supplied geometry; no game frame",
           "fixture": {"line_yd_from_own_goal": 50 + LINE_YD, "release_yd": RELEASE_YD,
                       "deep_arms": DEEP_ARMS, "deep_depths_yd": [DEEP_DEPTHS[0], DEEP_DEPTHS[-1]],
                       "speeds_yd_s": SPEEDS, "seeds": SEEDS, "in_stride_yd": STRIDE_YD,
                       "other_cached_ratings": .8},
           "profiles": {}, "cpu_gap": {}}
    raw_short = {}
    for name, payload in profiles.items():
        arc = tt.read_arc_table(payload)
        points = arc["points"] or tt.CURVES["lobspeed"].retail
        m = machine(payload)
        deep = deep_rows(m)
        short = short_rows(m)
        raw_short[name] = [row["raw"] for row in short]
        by_arm = {str(a): summary([r for r in deep if r["arm"] == a]) for a in DEEP_ARMS}
        out["profiles"][name] = {"xbe_sha256": hashlib.sha256(payload).hexdigest(), "arc_table": arc["label"],
                                 "lobspeed": points, "deep": summary(deep), "deep_by_arm": by_arm,
                                 "short_intermediate": summary(short),
                                 "short_max_release_to_land_yd": max(r["release_to_land_yd"] for r in short)}
        out["cpu_gap"][name] = cpu_gap_table(points)
        del m
    pairs = list(zip(raw_short["before"], raw_short["after"]))
    out["short_intermediate_identical"] = sum(a == b for a, b in pairs)
    out["short_intermediate_cases"] = len(pairs)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retail", type=Path, default=DEFAULT_XBE)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--target", type=Path, help="a disc image or default.xbe (read only)")
    source.add_argument("--scale-80", action="store_true",
                        help="retail + the Studio's 80-yard scale; before = the 76.2 touch band")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.receipt.exists() or args.receipt.is_symlink():
        parser.error("receipt must be a new file")
    retail = read_retail(args.retail)
    if args.scale_80:
        result = compare(studio_scale_80(retail, touch_band=True), retail=retail,
                         after=studio_scale_80(retail, touch_band=False))
    else:
        result = compare(read_xbe(args.target), retail=retail)
        result["target"] = str(args.target)
    with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for name, profile in result["profiles"].items():
        print(name, json.dumps(profile["deep"]), "| short", json.dumps(profile["short_intermediate"]))
    print("short/intermediate identical", result["short_intermediate_identical"], "of",
          result["short_intermediate_cases"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
