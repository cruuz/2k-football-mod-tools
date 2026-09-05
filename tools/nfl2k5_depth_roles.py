#!/usr/bin/env python3
"""Audit/normalise depth roles in PLAY books or a disc COPY (never runs xemu)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_depth_roles as roles  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "status", "normalise", "apply"):
        command = sub.add_parser(name, help={
            "audit": "histograms, exceptions and the output gate (read-only)",
            "status": "pinned retail/applied/foreign per book (read-only)",
            "normalise": "write a new book/image, or export a folder's books",
            "apply": "edit an existing disc COPY in place, idempotently",
        }[name])
        command.add_argument("source", type=Path, help="wrapped PLAY book, XISO, or extracted pack folder")
        command.add_argument("--json", metavar="PATH", help="full report (use - for stdout)")
        if name in ("normalise", "apply"):
            command.add_argument("--allow-custom", action="store_true",
                                 help="accept authored role geometry; structural/play validation still required")
        if name == "normalise":
            command.add_argument("-o", "--output", required=True, type=Path,
                                 help="new output file, or new directory for exported PLAY books")
    return parser


def _normalise(args: argparse.Namespace) -> dict:
    source, output = args.source, args.output
    if output.exists() or source.resolve() == output.resolve():
        raise roles.DepthRolesError("Output must be a new path; use apply on a disc copy to edit in place.")
    if source.is_dir() or source.stat().st_size == roles.RESOURCE_SIZE:
        resources = roles._resources(source)
        results = []
        for key, raw in resources.items():
            if not args.allow_custom and roles.book_status(raw) == "foreign":
                raise roles.DepthRolesError(f"{key}: foreign role data; use --allow-custom for authored books.")
            results.append((key, roles.normalise(raw)))
        # Compile ALL resources before creating an output.
        if source.is_dir():
            output.mkdir(parents=True)
            for key, result in results:
                # Entry numbers are safe filenames; private book names need
                # not be trusted as paths on either platform.
                with (output / f"book-{key}.PLAY").open("xb") as handle:
                    handle.write(result.replacement)
        else:
            with output.open("xb") as handle:
                handle.write(results[0][1].replacement)
        return {"schema": roles.SCHEMA, "status": "applied", "output": str(output),
                "books": [{"source_key": key, **r.report} for key, r in results],
                "changed_bytes": sum(r.report["changed_bytes"] for _, r in results),
                "refused_groups": sum(len(r.report["refused_groups"]) + len(r.report["special"]["refused"]) for _, r in results),
                "gate_ok": all(r.report["gate"]["ok"] and r.report["special"]["gate"]["ok"] for _, r in results)}
    with source.open("rb") as reader, output.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=8 << 20)
    return {**roles.apply(output, allow_custom=args.allow_custom), "output": str(output)}


def _summary(report: dict) -> None:
    if "totals" in report:
        totals = report["totals"]
        print(f"{totals['books']} books; {totals['formations']} formations; {totals['plays']} plays; {totals['nodes']} nodes")
        for key, hist in totals["histograms"].items():
            print(f"{key}: {json.dumps(hist, sort_keys=True)}")
        print(f"Gate: {totals['gate_checked']} checked, {totals['gate_excluded']} excluded, ok={totals['gate_ok']}")
        for key, book in report["books"].items():
            print(f"{key} {book['name']}: {book['status']}")
            print(f"  SPECIAL: classified={book['special']['classified']}; accepted={book['special']['accepted']}")
            for entry in book["special"]["refused"]:
                print(f"  {entry['role']} group {entry['group']}: {entry['refused_reason']}; formations={entry['formations']}")
            for group in book["groups"]:
                if group["refused_reason"] or group["disagreeing"] or any(r["bunch_or_tied"] for r in group["formations"]):
                    why = group["refused_reason"] or "bunch/tied/disagreeing within tolerance"
                    forms = ", ".join(f"{r['index']} {r['name']}" for r in group["formations"]) or "no formations"
                    print(f"  group {group['index']} {group['name']}: {why} ({forms})")
    elif isinstance(report.get("books"), dict):
        print(report["status"])
        for key, state in report["books"].items():
            print(f"  {key}: {state}")
    else:
        print(f"{report['status']}: {len(report['books'])} books, {report['changed_bytes']} changed bytes, "
              f"{report['refused_groups']} role assignments refused; gate ok={report['gate_ok']}")
        for book in report["books"]:
            refused = len(book["refused_groups"]) + len(book["special"]["refused"])
            print(f"  {book['name']}: {book['changed_bytes']} bytes; {refused} role assignments refused")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.json and args.json != "-":
            receipt = Path(args.json)
            if receipt.exists() or (getattr(args, "output", None) is not None
                                    and receipt.resolve() == args.output.resolve()):
                raise roles.DepthRolesError("JSON report must be a new path separate from the output.")
        if args.command == "audit":
            report = roles.audit(args.source)
        elif args.command == "status":
            report = roles.status(args.source)
        elif args.command == "normalise":
            report = _normalise(args)
        else:
            report = roles.apply(args.source, allow_custom=args.allow_custom)
        if args.json:
            document = json.dumps(report, indent=2) + "\n"
            if args.json == "-":
                print(document, end="")
            else:
                # Never let a receipt overwrite an input, output, or an
                # existing user file. Reports can contain private book names.
                with Path(args.json).open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(document)
        if args.json != "-":
            _summary(report)
        return 1 if args.command == "status" and report["status"] == "foreign" else 0
    except (OSError, ValueError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
