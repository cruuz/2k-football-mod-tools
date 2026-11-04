"""Read-only native man-coverage replay: the corner spins and the moving arrival brake (b780 cv1).

Adapted from job/ai2-hitch (f592ef09c, 10/11) and the b780 r5 research replays. No game, route script, renderer,
contact solver or full task scheduler runs. Python supplies only the receiver path. The defender's planner
(man 0x1A4830 or close pursuit 0x2E8730), steering, navigation, ordinary dispatcher, turn allowance, turn
integrator 0x2FC9F0 (and the coverage owner it jumps to), root sampler and world transform execute XBE code in
Unicorn through the TrailFrame fixture. The brake variant exists only in memory unless a built executable is
supplied with --extra. Never writes an XBE, never touches an emulator.

Builds: retail (pinned USA XBE), the released SOFTDRINK 2K28 v0.8 executable (read from the released disc image
or an extracted copy), v0.8 with the brake applied in memory, and any --extra NAME=PATH executable (for example a
pure-XBE build from this branch).

Matrices (60 Hz, 240 ticks, 91.44 world units per yard, both field directions):
* r5 matrix: receiver 6 yd/s for a six-yard stem, then hitch, curls back 1/1.5/2 yd, comeback, slant, go;
  defender Speed .90, Agility .80, one yard behind and .35 yd to the side (the worst case: a fast closing corner).
* fast matrix: receiver 9 yd/s, defender Speed .85 (about 9.55 yd/s top), same start (a realistic closing speed).
* pursuit controls (the close pursuit planner on a hitch and a 1.5-yard curl) and the hook ablation.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_coverage_trail as trail  # noqa: E402
from mod_editor.core import nfl2k5_coverage_trail_code as template  # noqa: E402
from mod_editor.core import nfl2k5_coverage_hitch_code as hitch_template  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from tests import nfl2k5_coverage_trail_frame as frame_fixture  # noqa: E402
from tests.nfl2k5_coverage_trail_frame import TrailFrame, YARD, DT, uni  # noqa: E402

RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
V08_SHA256 = "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"
V08_VA = 0x14DC030  # coverage_trail's allocation in the released v0.8 executable
RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) \
    / "ESPN NFL 2K5 (USA)/default.xbe"
V08_XBE = os.environ.get("NFL2K5_V08_XBE", "")
V08_DISC = Path(os.environ.get("NFL2K5_V08_DISC",
                               "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.8 (2026-10-31).xiso.iso"))

HZ = 60  # simulation ticks per second (the game's dt is 1 / HZ); --hz replays a slower frame rate
FRAMES, BREAK, RETURN_FRAMES = 240, 60, 20  # four seconds, a one-second stem, a one-third-second return
TAIL = 120  # the last two seconds
GAP_FRAMES = (30, 59, 70, 80, 100, 140, 239)


def set_rate(hz):
    """Replay at `hz` ticks per second: same seconds and yards, dt = 1 / hz in the game's frame-time global."""
    global HZ, FRAMES, BREAK, RETURN_FRAMES, TAIL, GAP_FRAMES
    if type(hz) is not int or not 10 <= hz <= 60 or 60 % hz and hz % 10:
        raise ValueError("hz must be a whole number of ticks per second from 10 to 60")
    HZ, FRAMES, BREAK, RETURN_FRAMES, TAIL = hz, 4 * hz, hz, max(1, round(hz / 3)), 2 * hz
    GAP_FRAMES = tuple(min(FRAMES - 1, round(f * hz / 60)) for f in (30, 59, 70, 80, 100, 140, 239))
    frame_fixture.DT = 1 / hz
# name: (kind, back yards, lateral yards); the stem is six yards at the matrix speed
ROUTES = {"hitch": ("return", 0, 0), "curl_1": ("return", 1, 0), "curl_1_5": ("return", 1.5, 0),
          "curl_2": ("return", 2, 0), "comeback": ("return", 1.5, 1),
          "slant": ("slant", 0, 0), "go": ("go", 0, 0),
          # exploratory (not in the acceptance): after the 1.5-yard curl the receiver drifts sideways at 0.5 yd/s
          "curl_drift": ("drift", 1.5, 0)}
# b780 modes2 (Q6): r5 lists its seven routes. tuple(ROUTES) took in curl_drift once the drift case was added (5d6f363,
# "outside the acceptance"), so the CV1 acceptance checked the exploratory drift with r5's rules; it has its own matrix.
MATRICES = {"r5": {"receiver_yards_s": 6.0, "speed": .90, "agility": .80,
                   "routes": tuple(r for r in ROUTES if ROUTES[r][0] != "drift")},
            "fast": {"receiver_yards_s": 9.0, "speed": .85, "agility": .80,
                     "routes": ("hitch", "curl_1_5", "slant", "go")},
            "drift": {"receiver_yards_s": 6.0, "speed": .90, "agility": .80, "routes": ("curl_drift",)}}
ACCEPTANCE = ("r5", "fast")  # the matrices the CV1 acceptance is checked on
RETURN_ROUTES = {name for name, (kind, back, _l) in ROUTES.items() if kind == "return" and back}
DRIFT_YARDS_S = 0.5


def _read_bounded(path):
    with Path(path).open("rb") as stream:
        payload = stream.read(16 * 1024**2 + 1)
    if len(payload) > 16 * 1024**2:
        raise ValueError(f"{path}: expected an executable, not a disc or archive")
    return payload


def _read_disc_xbe(disc):
    from mod_editor.core import nfl2k5_throw_tuning as tt
    fd = os.open(disc, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        offset, length = tt.image_xbe_extent(fd, os.fstat(fd).st_size)
        return os.pread(fd, length, offset)
    finally:
        os.close(fd)


def load_builds():
    """Pinned retail and released v0.8 executables. FileNotFoundError when a private input is absent."""
    retail = _read_bounded(RETAIL_XBE)
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise ValueError("retail: input does not match the pinned USA executable")
    if V08_XBE:
        v08 = _read_bounded(V08_XBE)
    else:
        if not V08_DISC.is_file():
            raise FileNotFoundError(2, "released v0.8 disc image absent", str(V08_DISC))
        v08 = _read_disc_xbe(V08_DISC)
    if hashlib.sha256(v08).hexdigest() != V08_SHA256:
        raise ValueError("v08: input does not match the released SOFTDRINK 2K28 v0.8 executable")
    return {"retail": retail, "v08": v08}


def route_point(name, frame, speed_yards_s=6.0):
    """(x, z, vx, vz) of the receiver at a tick, world units; the stem runs straight down the field (+z)."""
    kind, back, lateral = ROUTES[name]
    step = speed_yards_s / HZ * YARD
    velocity = speed_yards_s * YARD
    stem = 800 + BREAK * step
    if kind == "go" or frame < BREAK:
        return (0, 800 + frame * step, 0, velocity)
    n = frame - BREAK
    if kind == "slant":  # 45 degrees inside (-x) at the same speed, never stops
        d = step * n / math.sqrt(2)
        return (-d, stem + d, -velocity / math.sqrt(2), velocity / math.sqrt(2))
    k = min(n, RETURN_FRAMES)
    moving = n < RETURN_FRAMES
    seconds = RETURN_FRAMES / HZ
    if kind == "drift" and not moving:
        drift = DRIFT_YARDS_S * (n - RETURN_FRAMES) / HZ
        return (drift * YARD, stem - back * YARD, DRIFT_YARDS_S * YARD, 0)
    return (lateral * k / RETURN_FRAMES * YARD, stem - back * YARD * k / RETURN_FRAMES,
            lateral / seconds * YARD if moving else 0, -back / seconds * YARD if moving else 0)


def _longest(flags):
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def summarize(rows, name):
    kind = ROUTES[name][0]
    stop = BREAK if name == "hitch" else BREAK + RETURN_FRAMES
    angles = [math.atan2(r["defender_x"] - r["target_x"], r["defender_z"] - r["target_z"]) for r in rows[stop:]]
    winding = sum((b - a + math.pi) % (2 * math.pi) - math.pi for a, b in zip(angles, angles[1:]))
    # b780 modes2 (Q6): the winding after the defender first comes to rest at the target (speed 0 inside the native
    # arrival distance). An orbit never rests (retail circles the stopped receiver for the whole tail); a defender
    # closing at full speed when the receiver stops slides past him once by momentum and then holds, and that one
    # close pass is no orbit (the fixture has no contact solver, which in the game stops him at the receiver's body).
    rest = next((i for i, r in enumerate(rows[stop:]) if r["speed_yards_s"] == 0 and r["distance_yards"] <= .35), None)
    rest_winding = (sum((b - a + math.pi) % (2 * math.pi) - math.pi for a, b in zip(angles[rest:], angles[rest + 1:]))
                    if rest is not None else winding)
    pivots = [r["frame"] for r in rows if abs(r["turn_degrees"]) >= 90]
    return {
        "kind": kind,
        "rotation_total_degrees": sum(abs(r["turn_degrees"]) for r in rows),
        "pre_break_total_degrees": sum(abs(r["turn_degrees"]) for r in rows[:BREAK]),
        "post_break_total_degrees": sum(abs(r["turn_degrees"]) for r in rows[BREAK:]),
        "post_break_signed_degrees": sum(r["turn_degrees"] for r in rows[BREAK:]),
        "pre_break_large_pivot_frames": [f for f in pivots if f < BREAK],
        "large_pivot_frames": [f for f in pivots if f >= BREAK],
        "pivots_45_frames": [r["frame"] for r in rows if abs(r["turn_degrees"]) >= 45],
        # a there-and-back pair: two large pivots of opposite sign within three ticks (the "jag")
        "reversal_pairs": sum(
            1 for i, r in enumerate(rows) if abs(r["turn_degrees"]) >= 90 and any(
                abs(s["turn_degrees"]) >= 90 and (s["turn_degrees"] > 0) != (r["turn_degrees"] > 0)
                for s in rows[i + 1:i + 4])),
        "tail_total_degrees": sum(abs(r["turn_degrees"]) for r in rows[TAIL:]),
        "tail_max_speed_yards_s": max(r["speed_yards_s"] for r in rows[TAIL:]),
        "stationary_target_winding_degrees": math.degrees(winding),
        "winding_after_rest_degrees": math.degrees(rest_winding),
        "first_rest_frame": None if rest is None else stop + rest,
        "final_gap_yards": rows[-1]["distance_yards"],
        "max_gap_yards": max(r["distance_yards"] for r in rows),
        "max_post_break_gap_yards": max(r["distance_yards"] for r in rows[BREAK:]),
        "mean_gap_yards": sum(r["distance_yards"] for r in rows) / len(rows),
        "gap_at": {f: rows[f]["distance_yards"] for f in GAP_FRAMES},
        "held_ticks_after_break": sum(1 for r in rows[BREAK:] if r["final_throttle"] == 0 and r["throttle"] != 0),
        "longest_hold_ticks": _longest(r["final_throttle"] == 0 and r["throttle"] != 0 for r in rows),
        "lapse_calls": sum(r["lapse_calls"] for r in rows),
        "rng_calls": sum(len(r["lapse_words"]) for r in rows),
    }


def _owner_labels(payload):
    settings = trail.read_settings(payload)
    if settings["status"] != "applied":
        return settings, None, {}
    allocation = next(a for a in space.layout(payload)["allocations"] if a["owner"] == trail.OWNER)
    labels = (hitch_template if settings["moving_arrival_brake"] else template).LABELS
    return settings, allocation, labels


def replay_case(payload, name, *, direction=1, planner="man", disable_trail=False, matrix="r5"):
    spec = MATRICES[matrix]
    m = TrailFrame(payload, planner=planner, direction=direction, defender=(.35 * YARD, 800 - YARD), heading=0,
                   speed=spec["speed"], agility=spec["agility"])
    settings, allocation, labels = _owner_labels(payload)
    if settings["status"] == "foreign":
        raise ValueError("Unknown coverage recovery owner")
    if disable_trail:
        if settings["status"] != "applied":
            raise ValueError("The isolation control needs a verified installed owner")
        # Test-only ablation after loading: no output XBE, no other instruction changes.
        m.uc.mem_write(trail.HOOK_VA, trail.RETAIL_HOOK)
    visits = {}
    if allocation and not disable_trail:
        for label in ("entry", "arrival", "pivot", "moving_man_arrival"):
            if label not in labels:
                continue
            visits[label] = 0

            def observe(uc, address, size, data, label=label):
                visits[label] += 1

            va = allocation["va"] + labels[label]
            m.uc.hook_add(uni.UC_HOOK_CODE, observe, begin=va, end=va)
    rows = []
    for frame in range(FRAMES):
        row = m.step(frame, route_point(name, frame, spec["receiver_yards_s"]))
        if m.get(m.state + 0xC) != row["heading"] or m.get(m.p + 0xC28) != row["heading"]:
            raise AssertionError("Native body and animation orientation disagree")
        rows.append(row)
    if m.executed_leaves:
        raise AssertionError(f"Reached substituted leaves: {sorted(m.executed_leaves)}")
    result = {"summary": summarize(rows, name), "owner_visits": visits, "rows": rows}
    del m
    gc.collect()
    return result


def jobs(builds):
    """Every case the verifier needs: (build, matrix, route, direction, planner, ablation)."""
    plan = []
    for build in builds:
        for matrix, spec in MATRICES.items():
            if matrix not in ACCEPTANCE and build == "retail":
                continue
            for route in spec["routes"]:
                for direction in (1, -1):
                    plan.append((build, matrix, route, direction, "man", False))
    for build in builds:
        if build == "retail":
            continue
        for route in ("hitch", "curl_1_5"):
            for direction in (1, -1):
                plan.append((build, "r5", route, direction, "pursuit", False))
    for route in ("hitch", "curl_1_5", "slant", "go"):
        plan.append(("v08", "r5", route, 1, "man", True))
    return plan


def case_key(build, matrix, route, direction, planner, disabled):
    return f"{build}{'_without_trail' if disabled else ''}/{matrix}/{planner}/{route}/{direction}"


def twin_of(build):
    """The same executable without the brake: v08 for v08_brake, NAME_nobrake for an --extra NAME_brake."""
    return "v08" if build == "v08_brake" else build[:-len("_brake")] + "_nobrake" if build.endswith("_brake") else None


def verify_document(document, brake_builds=("v08_brake",)):
    """Assert the CV1 acceptance over the complete matrix (never a selected case)."""
    cases = document["cases"]
    failures = []

    def need(ok, message):
        if not ok:
            failures.append(message)

    for build in brake_builds:
        for matrix in ACCEPTANCE:
            for route in MATRICES[matrix]["routes"]:
                for direction in (1, -1):
                    key = case_key(build, matrix, route, direction, "man", False)
                    s = cases[key]["summary"]
                    allowed = 1 if route in RETURN_ROUTES else 0
                    need(not s["pre_break_large_pivot_frames"], f"{key}: pivots on the straight stem")
                    need(len(s["large_pivot_frames"]) <= allowed,
                         f"{key}: {len(s['large_pivot_frames'])} pivots after the break (allowed {allowed})")
                    need(s["reversal_pairs"] == 0, f"{key}: a there-and-back pivot pair (jag)")
                    need(s["tail_total_degrees"] < 5, f"{key}: {s['tail_total_degrees']:.2f} degrees in the last 2 s")
                    need(s["final_gap_yards"] < .35, f"{key}: final gap {s['final_gap_yards']:.3f} yd")
        for matrix in ACCEPTANCE:
            for direction in (1, -1):
                s = cases[f"{build}/{matrix}/man/hitch/{direction}"]["summary"]
                need(s["post_break_total_degrees"] < 10 and abs(s["winding_after_rest_degrees"]) < 45,
                     f"{build}/{matrix} hitch {direction}: the stationary orbit is back")
        twin = twin_of(build)
        if twin is None or not any(k.startswith(f"{twin}/") for k in cases):
            # b780 modes2: an --extra brake build without a NAME_nobrake twin has nothing to compare pursuit with
            continue
        for route in ("hitch", "curl_1_5"):
            for direction in (1, -1):
                a = cases.get(f"{twin}/r5/pursuit/{route}/{direction}")
                b = cases[f"{build}/r5/pursuit/{route}/{direction}"]
                need(a is not None and a.get("rows") == b.get("rows") and a.get("error") == b.get("error"),
                     f"{build} pursuit {route} {direction}: the man-only brake changed pursuit (twin {twin})")
    # The shipped bug and the controls must still reproduce, or the fixture proves nothing.
    for direction in (1, -1):
        s = cases[f"v08/r5/man/curl_1_5/{direction}"]["summary"]
        need(len(s["pre_break_large_pivot_frames"]) >= 4 and len(s["large_pivot_frames"]) >= 4,
             f"v08 curl_1_5 {direction}: the shipped spins no longer reproduce")
        s = cases[f"v08/r5/man/go/{direction}"]["summary"]
        need(len(s["large_pivot_frames"]) >= 10, f"v08 go {direction}: the shipped go-route spins no longer reproduce")
        s = cases[f"retail/r5/man/hitch/{direction}"]["summary"]
        need(s["post_break_total_degrees"] > 720, f"retail hitch {direction}: the retail orbit no longer reproduces")
        need(abs(s["winding_after_rest_degrees"]) >= 45,
             f"retail hitch {direction}: the orbit check no longer sees the retail orbit")
    need(cases["v08_without_trail/r5/man/hitch/1"]["summary"]["post_break_total_degrees"] > 720,
         "ablation: restoring the retail hook no longer brings back the orbit")
    for key, case in cases.items():
        if "summary" in case:
            need(not case["summary"]["rng_calls"] and not case["summary"]["lapse_calls"],
                 f"{key}: RNG or a lapse was reached in the ordinary-motion fixture")
    if failures:
        raise AssertionError("; ".join(failures))
    return {"cases": len(cases), "brake_builds": list(brake_builds), "passed": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--extra", action="append", default=[], metavar="NAME=PATH",
                        help="another executable to replay (and verify as a brake build when it has the brake)")
    parser.add_argument("--only", choices=("all", "man", "pursuit"), default="all")
    parser.add_argument("--hz", type=int, default=60, help="simulation ticks per second (robustness replays; no verify)")
    parser.add_argument("--builds", default="", help="comma list to replay (default all)")
    args = parser.parse_args(argv)
    set_rate(args.hz)
    builds = load_builds()
    builds["v08_brake"], receipt = trail.apply(builds["v08"], moving_arrival_brake=True)
    brake_builds = ["v08_brake"]
    for item in args.extra:
        name, _, path = item.partition("=")
        if not name or not path or name in builds:
            parser.error(f"--extra wants a new NAME=PATH, got {item!r}")
        builds[name] = _read_bounded(path)
        if trail.read_settings(builds[name]).get("moving_arrival_brake"):
            brake_builds.append(name)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    document = {"schema": 2, "runtime_witnessed": False, "scope": __doc__, "frames_per_case": FRAMES, "dt": 1 / HZ, "hz": HZ,
                "world_units_per_yard": YARD, "break_frame": BREAK, "return_frames": RETURN_FRAMES,
                "matrices": MATRICES, "routes": ROUTES,
                "inputs": {name: {"sha256": hashlib.sha256(p).hexdigest(), "bytes": len(p),
                                  "coverage_trail": trail.read_settings(p)} for name, p in builds.items()},
                "brake_receipt": {k: v for k, v in receipt.items() if k not in ("reservations", "mapping")},
                "cases": {}}
    wanted = set(filter(None, args.builds.split(",")))
    for build, matrix, route, direction, planner, disabled in jobs(builds):
        if args.only != "all" and planner != args.only or wanted and build not in wanted:
            continue
        key = case_key(build, matrix, route, direction, planner, disabled)
        try:
            case = replay_case(builds[build], route, direction=direction, planner=planner,
                               disable_trail=disabled, matrix=matrix)
        except AssertionError as exc:
            document["cases"][key] = {"error": str(exc)}
            print(f"{key}: FIXTURE REFUSED: {exc}", flush=True)
            continue
        rows = case.pop("rows")
        document["columns"] = list(rows[0])
        case["rows"] = [list(row.values()) for row in rows]
        document["cases"][key] = case
        s = case["summary"]
        print(f"{key}: total={s['rotation_total_degrees']:.1f} stem_pivots={len(s['pre_break_large_pivot_frames'])} "
              f"post_pivots={len(s['large_pivot_frames'])} pairs={s['reversal_pairs']} tail={s['tail_total_degrees']:.2f} "
              f"gap_final={s['final_gap_yards']:.3f} gap_max_post={s['max_post_break_gap_yards']:.3f} "
              f"held={s['held_ticks_after_break']} longest_hold={s['longest_hold_ticks']} visits={case['owner_visits']}", flush=True)
    if args.only == "all" and args.hz == 60 and not wanted:
        try:
            document["verification"] = verify_document(document, tuple(brake_builds))
        except AssertionError as exc:
            document["verification"] = {"passed": False, "failures": str(exc)}
        print("VERIFY", json.dumps(document["verification"])[:4000], flush=True)
    (output / "frames.json").write_text(json.dumps(document, separators=(",", ":")) + "\n", encoding="utf-8")
    summary = {k: v for k, v in document.items() if k not in ("cases", "columns")}
    summary["cases"] = {k: {f: v for f, v in c.items() if f != "rows"} for k, c in document["cases"].items()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(document['cases'])} cases; no XBE written.", flush=True)
    return 0 if document.get("verification", {}).get("passed", not (args.only == "all" and args.hz == 60 and not wanted)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
