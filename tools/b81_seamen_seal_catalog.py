#!/usr/bin/env python3
"""b81-seamen: bring the lane's authored PNGs into the reviewed release PNG catalog and reseal it.

Idempotent and order-independent (the alg_seal_catalog way), so integration can re-run it on the merged tree after any
other job reseals the same catalog: it upserts exactly the rows of the PNGs below (size, SHA-256, PNG width and height
read from the files), writes the catalog in its canonical form (``json.dumps(indent=2, sort_keys=True)`` plus a newline),
moves the one ``SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256`` pin in ``packaging/check_2k5_mod_studio_release.py`` and checks
that each PNG is in ``packaging/release-allowlist.txt``. It never removes or relaxes another row.

* data/nfl2k5_scorebug_mnf/logos/seamen.png: the Seamen's scorebug mark (tools/b77/ss2_scorebug.py);
* data/nfl2k5_stadium_shared_art/venues/s48/{espnwall01,wall_fance01}{,_4x}.png: ESPN Stadium's plain white walls
  (tools/nfl2k5_s48_white_walls.py).

    python3 tools/b81_seamen_seal_catalog.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
CHECKER = ROOT / "packaging" / "check_2k5_mod_studio_release.py"
ALLOWLIST = ROOT / "packaging" / "release-allowlist.txt"
PIN = re.compile(r'(?m)^(SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = ")[0-9a-f]{64}(")')
PNGS = ("data/nfl2k5_scorebug_mnf/logos/seamen.png",
        "data/nfl2k5_stadium_shared_art/venues/s48/espnwall01.png",
        "data/nfl2k5_stadium_shared_art/venues/s48/espnwall01_4x.png",
        "data/nfl2k5_stadium_shared_art/venues/s48/wall_fance01.png",
        "data/nfl2k5_stadium_shared_art/venues/s48/wall_fance01_4x.png")


def row(relative: str) -> dict:
    data = (ROOT / relative).read_bytes()
    if data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR":
        raise SystemExit(f"not a PNG: {relative}")
    width, height = struct.unpack_from(">II", data, 16)
    return dict(height=height, sha256=hashlib.sha256(data).hexdigest(), size=len(data), width=width)


def sealed_texts():
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    if document.get("schema") != "nfl2k5_scorebug_template_pngs/v1":
        raise SystemExit("unexpected PNG catalog schema")
    document["files"].update({relative: row(relative) for relative in PNGS})
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checker = CHECKER.read_text(encoding="utf-8")
    if len(PIN.findall(checker)) != 1:
        raise SystemExit("the checker pin line is not unique")
    checker = PIN.sub(lambda m: m.group(1) + hashlib.sha256(payload).hexdigest() + m.group(2), checker)
    listed = set(ALLOWLIST.read_text(encoding="utf-8").split("\n"))
    missing = [p for p in PNGS if p not in listed]
    if missing:
        raise SystemExit(f"not in the release allowlist: {missing}")
    return payload, checker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report whether the catalog and pin are current")
    args = parser.parse_args()
    payload, checker = sealed_texts()
    current = CATALOG.read_bytes() == payload and CHECKER.read_text(encoding="utf-8") == checker
    if args.check:
        print(json.dumps(dict(sealed=current, pngs=len(PNGS))))
        return 0 if current else 1
    CATALOG.write_bytes(payload)
    CHECKER.write_text(checker, encoding="utf-8", newline="\n")
    print(json.dumps(dict(pngs=len(PNGS), catalog_sha256=hashlib.sha256(payload).hexdigest())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
