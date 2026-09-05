#!/usr/bin/env python3
"""Read-only XBE cave scanner and disposable-stack reservation manifest builder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.nfl2k5_cave_oracle import (
    DEFAULT_MANIFEST, RETAIL_SHA256, CaveOracle, OracleError, ReservationManifest, XbeImage,
)


def summary(report: dict) -> str:
    lines = [f"XBE {report['xbe_sha256']}", report["reservation_model"],
             f"Decoded {report['instruction_count']} instructions; {report['unresolved_count']} unresolved effects.",
             "Free means free-under-closed-world; unknown is never available."]
    exhausted = [name for name, value in report["budget_exhausted"].items() if value]
    if exhausted:
        lines.append("Incomplete analysis: exhausted " + ", ".join(exhausted) + " budget(s); unexamined bytes remain unknown.")
    for section in report["sections"]:
        name = section["name"]
        lines.append(f"{name} flags={section['flags']:#x}: " + ", ".join(f"{k}={v}" for k, v in section["coverage"].items()))
        free = sorted((r for r in report["ranges"] if r["section"] == name and r["allocatable"]),
                      key=lambda r: (-r["size"], int(r["start"], 0)))[:20]
        if not free:
            lines.append("  No free candidates meeting the size and permission requirements.")
        for row in free:
            lines.append(f"  {row['start']}..{row['end']} ({row['size']} bytes) free-under-closed-world")
            lines.append("    left: " + row["left"]["reason"])
            lines.append("    right: " + row["right"]["reason"])
    return "\n".join(lines)


def write_json(path: Path, document: dict, inputs: list[Path]):
    target = path.resolve()
    if any(target == p.resolve() or (target.exists() and p.exists() and target.samefile(p)) for p in inputs):
        raise OracleError("JSON output must not overwrite an input")
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="classify mapped byte ranges; never writes the XBE")
    scan.add_argument("xbe", type=Path)
    scan.add_argument("--min-size", type=int, default=64)
    scan.add_argument("--kind", choices=("code", "data"), default="code")
    scan.add_argument("--json", type=Path)
    scan.add_argument("--manifest", type=Path)
    scan.add_argument("--retail-only", action="store_true", help="explicitly omit patch ownership")
    scan.add_argument("--instruction-budget", type=int, default=250_000)
    scan.add_argument("--reference-budget", type=int, default=2_000_000)
    scan.add_argument("--range", action="append", default=[], metavar="VA:SIZE", help="include exact candidate verdict (integers or hex); repeatable")
    manifest = commands.add_parser("manifest", help="build all current owners on a disposable retail disc copy")
    manifest.add_argument("xbe", type=Path)
    manifest.add_argument("--xiso", type=Path, required=True)
    manifest.add_argument("--work-dir", type=Path, required=True, help="existing writable directory for disposable 6+ GB image")
    manifest.add_argument("--json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = args.xbe.read_bytes()
        image = XbeImage(data)
        if args.command == "manifest":
            from mod_editor.core.nfl2k5_cave_manifest import build_manifest
            report = build_manifest(data, args.xiso, work_dir=args.work_dir,
                                    progress=lambda text: print(text, file=sys.stderr, flush=True))
            write_json(args.json, report, [args.xbe, args.xiso])
            print(f"Wrote {len(report['spans'])} reservations from {len(report['steps'])} observed XBE writer calls.")
            return 0
        if args.retail_only and args.manifest:
            raise OracleError("--retail-only and --manifest are exclusive")
        path = args.manifest
        if path is None and not args.retail_only and image.sha256 == RETAIL_SHA256:
            path = DEFAULT_MANIFEST
        ownership = ReservationManifest.load(path, image, source_root=ROOT) if path else None
        oracle = CaveOracle(data, manifest=ownership, instruction_budget=args.instruction_budget,
                            reference_budget=args.reference_budget)
        report = oracle.scan(min_size=args.min_size, kind=args.kind)
        report["queries"] = []
        for value in args.range:
            start, size = (int(n, 0) for n in value.split(":"))
            row = oracle.assess(start, size, kind=args.kind)
            row.update(left=oracle.neighbour(start - 1), right=oracle.neighbour(start + size))
            report["queries"].append(row)
        if args.json:
            write_json(args.json, report, [args.xbe] + ([path] if path else []))
        print(summary(report))
        for row in report["queries"]:
            print(f"Query {row['start']}..{row['end']}: {row['verdict']}; {row['permission_reason']}")
            for e in row["witnesses"]:
                print(f"  {e['source']}: {e['kind']}: {e['detail']}")
        return 0
    except (OracleError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"cave oracle: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
