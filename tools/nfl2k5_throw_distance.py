#!/usr/bin/env python3
"""Command-line front end for ``mod_editor.core.nfl2k5_throw_tuning``.

Read or rewrite the NFL 2K5 throw-distance and pass-arc curve tables on a COPY
of ``default.xbe`` or of a disc image (the source is never written).  The GUI
equivalent is Sliders & Gameplay -> Throw Distance & Arc.

  read      PATH                                    show the five curves + inferred sliders
  sliders   SOURCE TARGET --ceiling YD [--arc PCT]  write a copy from the two sliders
  curves    SOURCE TARGET --bullet SPEC ...         write a copy from explicit curve points
  preview   --ceiling YD [--arc PCT]                print the per-arm ceiling / hang / apex

SPEC is ``x:y,x:y,...`` with exactly the retail point count (distance tables:
x = arm 0..1, y = yards; speed tables: x = yards, y = yd/s).  Output is
xemu-only: the RSA signature stays stale.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402


def _parse_spec(curve: tt.Curve, spec: str) -> tuple[tuple[float, float], ...]:
    pairs = []
    for item in spec.split(","):
        item = item.strip()
        if ":" not in item:
            raise tt.ThrowTuningError(f"{curve.name}: bad point {item!r}, want x:y")
        x, y = item.split(":", 1)
        pairs.append((float(x), float(y)))
    return tt.validate_pairs(curve, pairs)


def _fmt(curve: tt.Curve, pairs) -> str:
    xu = "yd" if curve.x_unit == "yd" else ""
    return "  ".join(f"{x:g}{xu}->{y:g}{curve.y_unit}" for x, y in pairs)


def _progress(stage: str, done: int, total: int) -> None:
    if total:
        print(f"\r{stage}: {done * 100 // total}%", end="", file=sys.stderr, flush=True)
    else:
        print(f"\r{stage}", end="", file=sys.stderr, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    r = sub.add_parser("read")
    r.add_argument("path")

    s = sub.add_parser("sliders")
    s.add_argument("source")
    s.add_argument("target")
    s.add_argument("--ceiling", type=float, required=True,
                   help="deep-ball ceiling in yards at 99 arm (55 = retail .. 100)")
    s.add_argument("--arc", type=float, default=0.0, help="pass arc percent (0 = retail .. 100)")
    s.add_argument("--overwrite", action="store_true")

    c = sub.add_parser("curves")
    c.add_argument("source")
    c.add_argument("target")
    c.add_argument("--overwrite", action="store_true")
    for name in tt.EDITABLE_CURVES:
        curve = tt.CURVES[name]
        c.add_argument(f"--{name}", help=f"{curve.count} points, x in {curve.x_unit}, y in {curve.y_unit}")

    p = sub.add_parser("preview")
    p.add_argument("--ceiling", type=float, required=True)
    p.add_argument("--arc", type=float, default=0.0)

    args = ap.parse_args()
    try:
        if args.mode == "read":
            report = tt.read_any(args.path)
            settings = report["settings"]
            print(f"{report['container']}: {report['path']}")
            print(f"default.xbe sha256 {report['xbe_sha256'][:16]}... "
                  f"{'(retail)' if report['matches_retail_sha256'] else '(not retail)'}; "
                  f"sliders: ceiling {settings.max_deep_yards:g} yd, arc {settings.arc * 100:.0f} %")
            for name, entry in report["curves"].items():
                curve = tt.CURVES[name]
                print(f"  {name:11s} {entry['file_offset']:>9s} {'RETAIL' if entry['retail'] else 'EDITED'}: "
                      f"{_fmt(curve, entry['points'])}")
        elif args.mode == "sliders":
            settings = tt.TuningSettings(args.ceiling, args.arc / 100.0)
            result = tt.write_copy(args.source, args.target, settings=settings,
                                   overwrite=args.overwrite, progress=_progress)
            print(file=sys.stderr)
            print(json.dumps({k: v for k, v in result.items() if k != "changes"}, indent=1, default=str))
        elif args.mode == "curves":
            wanted = {}
            for name in tt.EDITABLE_CURVES:
                spec = getattr(args, name)
                if spec:
                    wanted[name] = _parse_spec(tt.CURVES[name], spec)
            result = tt.write_copy(args.source, args.target, curves=wanted,
                                   overwrite=args.overwrite, progress=_progress)
            print(file=sys.stderr)
            print(json.dumps({k: v for k, v in result.items() if k != "changes"}, indent=1, default=str))
        else:
            settings = tt.TuningSettings(args.ceiling, args.arc / 100.0)
            curves = tt.curves_for(settings)
            for name, pairs in curves.items():
                print(f"  {name:11s} {_fmt(tt.CURVES[name], pairs)}")
            print("  arm  ceiling  hang   apex")
            for row in tt.preview(curves):
                print(f"  {row.arm * 100:3.0f}  {row.deep_cap_yards:5.1f}yd  {row.hang_seconds:4.2f}s  {row.apex_yards:4.1f}yd")
    except tt.ThrowTuningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
