#!/usr/bin/env python3
"""b777 qb3: short and on-the-run throws, before and after the QB accuracy owner. Read-only native evidence.

Unicorn runs the game's own target/lead solver (0x2DA8E0), accuracy routine (0x2D9700, plus the owner's cave when
installed), launch (0x1CBDB0) and ball flight (0x1CC820) from the supplied default.xbe; the fixture is
tests/nfl2k5_qb_accuracy_native.py (straight route segments, QB set in the pocket or rolling right at 6 yd/s, human or
CPU control, cached ratings, no rushers, seeded RNG). "Miss" = where the ball comes down against where the receiver
is when it lands; "ahead" = the part of the miss along his run. Not a game session.

  python3 tools/b77/qb3_short_throw_probe.py --target default.xbe --receipt NEW.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_qb_accuracy as accuracy  # noqa: E402
from nfl2k5_qb_accuracy_native import AccuracyMachine, DEEP_ROUTES, QB_STATES, ROUTES, summary  # noqa: E402

ACCURACIES = (.55, .7, .8, .9, .97)
SEEDS = tuple(range(1, 9))


def rows(machine) -> list[dict]:
    out = []
    for state in QB_STATES:
        for route in ROUTES:
            for value in ACCURACIES:
                for seed in SEEDS:
                    row = machine.throw(route, state=state, accuracy=value, seed=seed)
                    row.pop("capture")
                    out.append(row)
    return out


def table(all_rows: list[dict]) -> dict:
    result = {}
    for state in QB_STATES:
        sub = [r for r in all_rows if r["state"] == state]
        short = [r for r in sub if r["route"] not in DEEP_ROUTES]
        result[state] = {"short": summary(short), "deep": summary([r for r in sub if r["route"] in DEEP_ROUTES]),
                         "short_by_pass_accuracy": {str(v): summary([r for r in short if r["accuracy"] == v])
                                                    for v in ACCURACIES},
                         "by_route_at_80": {route: summary([r for r in sub if r["route"] == route and r["accuracy"] == .8])
                                            for route in ROUTES}}
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", type=Path, required=True, help="a default.xbe (read only)")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.receipt.exists() or args.receipt.is_symlink():
        parser.error("receipt must be a new file")
    with args.target.open("rb") as stream:
        before = stream.read(16 * 1024 * 1024 + 1)
    if len(before) > 16 * 1024 * 1024:
        parser.error("expected a default.xbe under 16 MiB")
    state = accuracy.status(before)
    if state == "foreign":
        parser.error("the accuracy routine in this executable is neither retail nor the QB accuracy owner")
    after = before if state == "applied" else accuracy.apply(before)[0]
    profiles = {}
    raw = {}
    for name, payload in (("before", before), ("after", after)):
        machine = AccuracyMachine(payload)
        all_rows = rows(machine)
        raw[name] = [r["raw"] for r in all_rows]
        profiles[name] = {"xbe_sha256": hashlib.sha256(payload).hexdigest(), "qb_accuracy": accuracy.status(payload),
                          **table(all_rows)}
    same = sum(a == b for a, b in zip(raw["before"], raw["after"]))
    result = {"schema": "b777.qb3.short_throw_probe.v1", "claim": "native components on supplied geometry; no game frame",
              "fixture": {"routes": ROUTES, "qb_states": QB_STATES, "pass_accuracy": ACCURACIES, "seeds": SEEDS,
                          "yard_cm": 91.44, "line_of_scrimmage_z": 0},
              "profiles": profiles, "identical_throws": same, "throws": len(raw["before"])}
    with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    for name, profile in profiles.items():
        for qb_state in QB_STATES:
            print(name, qb_state, "short", json.dumps(profile[qb_state]["short"]), "deep", json.dumps(profile[qb_state]["deep"]))
    print("identical throws", same, "of", len(raw["before"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
