#!/usr/bin/env python3
"""Export, edit and import the award history the Player Card honors page shows (job F5, beta 77).

Read only on every source. Input: a bare disc ROST body, a wrapped ROST resource, or (with --image) a disc image or
pack folder whose main roster is read from outer entry 5.

  export  INPUT [--image] [--base-year 2026] --csv OUT.csv      every honor in the roster, one per row
  import  INPUT [--image] --data FILE.json|.csv --output BODY   writes a NEW bare ROST body with the honors added
  check   [--data FILE]                                          validates a data document (default: the built-in one)

The CSV columns are pool,index,first,last,birth_date,season,honor,source. Honors: mvp, opoy, dpoy, oroy, droy,
super_bowl, super_bowl_mvp, pro_bowl, all_pro, rushing_title. A CSV row's source must name a source of the built-in
data (for example wiki_mvp) or "user"; the Studio's Build panel takes the same JSON or CSV under Custom data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_honors_history as hh  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as records  # noqa: E402


def _load(path: Path, image: bool) -> bytes:
    if image:
        with records._outer_image()(path) as archive:
            entry = records._entry(archive)
            resource = archive.read(entry.virtual_offset, entry.size)
        return resource[records.RESOURCE_HEADER_SIZE:]
    data = path.read_bytes()
    if len(data) == records.RESOURCE_SIZE and data[:4] == b"ROST":
        data = data[records.RESOURCE_HEADER_SIZE:]
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("input", type=Path)
    ex.add_argument("--image", action="store_true")
    ex.add_argument("--base-year", type=int, default=2026)
    ex.add_argument("--csv", type=Path, required=True)
    im = sub.add_parser("import")
    im.add_argument("input", type=Path)
    im.add_argument("--image", action="store_true")
    im.add_argument("--base-year", type=int, default=2026)
    im.add_argument("--data", required=True)
    im.add_argument("--output", type=Path, required=True)
    ck = sub.add_parser("check")
    ck.add_argument("--data", default="builtin")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            data = hh.resolve(args.data)
            print(json.dumps({"players": len(data["players"]), "honors": sum(len(p["honors"]) for p in data["players"]),
                              "sources": len(data["sources"])}))
            return 0
        body = _load(args.input, args.image)
        if args.command == "export":
            if os.path.lexists(args.csv):
                raise hh.HonorsHistoryError(f"output already exists: {args.csv}")
            rows = hh.read_body(body, args.base_year)
            args.csv.write_text(hh.to_csv(rows), encoding="utf-8", newline="\n")
            print(json.dumps({"rows": len(rows)}))
            return 0
        if os.path.lexists(args.output):
            raise hh.HonorsHistoryError(f"output already exists: {args.output}")
        data = hh.resolve(args.data, args.base_year)
        new_body, receipt = hh.apply_body(body, data)
        with args.output.open("xb") as stream:
            stream.write(new_body)
        print(json.dumps({k: receipt[k] for k in ("added", "already_present", "players")} | {"skipped": len(receipt["skipped"])}))
        return 0
    except (hh.HonorsHistoryError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
