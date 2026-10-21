"""b777 qb4: quick-throw placement, native before/after (Unicorn on the game's own lead solver 0x2DA8E0, accuracy
0x2D9700, launch 0x1CBDB0, flight 0x1CC820 and, for the catch family, the bucket chooser 0x1E51A0 reached through the
real catch-select entry 0x1E78A0). Development tool; the shipped fixture is tests/nfl2k5_qb_accuracy_native.py.

Usage: python3 tools/b77/qb4_quick_throw_probe.py RETAIL_OR_B776.xbe OWNER_APPLIED.xbe OUT.json
For each route: where the ball lands relative to the receiver at arrival (yd): 'off_path' = sideways distance from
his running line (positive = toward the QB side / underneath), 'ahead' = along his run; 'reach' = how many of the
game's 68 side-catch (bucket 1) running catch records reach that far sideways (|hand x| >= off_path).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_qb_accuracy_native import AccuracyMachine, ROUTES, YD  # noqa: E402

QUICK = {
    "slant3": (-10., 2., 5.5, 5.5), "slant5": (-10., 4., 5.5, 5.5), "slant8": (9., 7., -5.5, 5.5),
    "qout2": (7., 2., 7.0, -0.5), "qout5": (8., 5., 7.0, -0.5), "qout7": (10., 7., 7.0, -0.5),
    "qout5_left": (-8., 5., -7.0, -0.5), "hitch5": (15., 5., 0., 0.), "hitch7": (12., 7., 0., -0.5),
    "flat1": (2., 1., 7., 1.), "flat3": (4., 2., 7., 0.5), "flat_wide": (6., 0.5, 7.5, 1.),
    "bubble": (9., -1., 2.5, 2.5), "swing": (-3., -3., -6., 2.),
}
LONGER = {
    "out10": (10., 10., 7.0, -0.5), "out12_wide": (14., 11., 7.0, -0.3), "out14": (12., 14., 7.0, -0.5),
    "dig12": (-8., 12., 7.5, 0.), "curl10": (8., 10., 0., -1.), "comeback15": (15., 15., 1., -2.),
    "seam20": (-6., 20., 0., 9.), "go30": (14., 30., 0., 9.5), "post25": (-10., 25., 4., 8.),
    "fade18": (16., 14., 1., 8.5), "wheel20": (12., 16., 1.5, 8.5), "corner18": (8., 14., 5., 6.),
}
STATES = ("set", "roll_human", "roll_cpu")


def side_reach():
    rows = json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None
    return rows


def measure(machine, name, geom, state, accuracy, seed):
    ROUTES[name] = geom
    r = machine.throw(name, state=state, accuracy=accuracy, seed=seed)
    rx, rz, rvx, rvz = geom
    speed = math.hypot(rvx, rvz)
    wx, wz = r["receiver"]
    ex, ez = r["land"]
    ax, az = r["aim"]
    if speed:
        ux, uz = rvx / speed, rvz / speed
    else:  # a stopped receiver: measure against the QB-to-receiver line
        qz = -4.37
        d = math.hypot(wx, wz - qz)
        ux, uz = wx / d, (wz - qz) / d
    # sideways: positive toward the QB side of his path
    qx, qz = 0., -4.37
    px, pz = -uz, ux
    if (qx - wx) * px + (qz - wz) * pz < 0:
        px, pz = -px, -pz
    return dict(route=name, state=state, accuracy=accuracy, seed=seed, flight_s=round(r["flight_s"], 3),
                aim=[round(ax, 3), round(az, 3)], land=[round(ex, 3), round(ez, 3)], receiver=[round(wx, 3), round(wz, 3)],
                aim_off_path=round((ax - wx) * px + (az - wz) * pz, 3), aim_ahead=round((ax - wx) * ux + (az - wz) * uz, 3),
                off_path=round((ex - wx) * px + (ez - wz) * pz, 3), ahead=round((ex - wx) * ux + (ez - wz) * uz, 3),
                miss=round(r["miss_yd"], 3), ball_height_cm=round(r["ball_height_cm"], 1), raw=list(r["raw"]))


def main():
    before, after, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    result = {}
    for label, path in (("before", before), ("after", after)):
        machine = AccuracyMachine(path.read_bytes())
        rows = []
        for group, routes in (("quick", QUICK), ("longer", LONGER)):
            for name, geom in routes.items():
                for state in STATES:
                    for seed in ((7,) if state == "set" else (7, 11, 23, 31)):
                        row = measure(machine, name, geom, state, .85, seed)
                        row["group"] = group
                        rows.append(row)
        result[label] = {"xbe_sha256": machine.source_sha256, "rows": rows}
    table = []
    for b, a in zip(result["before"]["rows"], result["after"]["rows"]):
        assert (b["route"], b["state"], b["seed"]) == (a["route"], a["state"], a["seed"])
        table.append(dict(group=b["group"], route=b["route"], state=b["state"], seed=b["seed"],
                          off_path=(b["off_path"], a["off_path"]), aim_off_path=(b["aim_off_path"], a["aim_off_path"]),
                          ahead=(b["ahead"], a["ahead"]), miss=(b["miss"], a["miss"]),
                          identical=b["raw"] == a["raw"]))
    result["pairs"] = table
    out.write_text(json.dumps(result, indent=1))
    print("route        state       seed  aim off-path yd (before->after)  land off-path  ahead  miss  identical")
    for t in table:
        print(f'{t["group"]:6s} {t["route"]:11s} {t["state"]:10s} {t["seed"]:3d}  {t["aim_off_path"][0]:6.2f} -> {t["aim_off_path"][1]:6.2f}'
              f'   {t["off_path"][0]:6.2f} -> {t["off_path"][1]:6.2f}  {t["ahead"][0]:5.2f} -> {t["ahead"][1]:5.2f}'
              f'  {t["miss"][0]:4.2f} -> {t["miss"][1]:4.2f}  {t["identical"]}')
    for group in ("quick", "longer"):
        for state in STATES:
            sel = [t for t in table if t["group"] == group and t["state"] == state]
            print(group, state, "mean |off-path| %.2f -> %.2f" % (statistics.mean(abs(t["off_path"][0]) for t in sel),
                                                                  statistics.mean(abs(t["off_path"][1]) for t in sel)),
                  "mean miss %.2f -> %.2f" % (statistics.mean(t["miss"][0] for t in sel), statistics.mean(t["miss"][1] for t in sel)),
                  "byte-identical %d/%d" % (sum(t["identical"] for t in sel), len(sel)))


if __name__ == "__main__":
    main()
