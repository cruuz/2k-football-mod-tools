#!/usr/bin/env python3
"""Beta 76 p2: add the fourteen ESPN 2026 wipes and boards PNGs to the reviewed release PNG catalog and reseal it.

Idempotent and order-independent, so integration can re-run it on the merged tree after any other job
(the sprite scorebug job and p1's ESPN marks reseal the same catalog): it upserts exactly the fourteen
``data/nfl2k5_espn_wipes_boards/*.png`` rows (size, SHA-256, PNG width and height read from the files), writes the
catalog in its canonical form (``json.dumps(indent=2, sort_keys=True)`` plus a newline) and moves the one
``SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256`` pin in ``packaging/check_2k5_mod_studio_release.py`` to the new
catalog bytes. It never removes or relaxes another row.

    python3 reports/b76_p2/seal_png_catalog.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
CHECKER = ROOT / "packaging" / "check_2k5_mod_studio_release.py"
ART = tuple(f"data/nfl2k5_espn_wipes_boards/{name}.png" for name in (
    "electricity_background1", "electricity_lightning", "helmetbumper_monitor", "helmetbumper_monitorcolors",
    "playercard_znfl_shield", "redflashy_logo1", "replay_wipe_logo_glow", "replay_wipe_pattern_flash",
    "replay_wipe_rays", "replay_wipe_streaks", "scoreboard_backboard01", "scoreboard_dot", "scoreboard_sign01",
    "scoreboard_sign02"))
PIN = re.compile(r'(?m)^SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "[0-9a-f]{64}"$')


def row(relative: str) -> dict:
    data = (ROOT / relative).read_bytes()
    if data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR":
        raise SystemExit(f"not a PNG: {relative}")
    width, height = struct.unpack_from(">II", data, 16)
    return dict(height=height, sha256=hashlib.sha256(data).hexdigest(), size=len(data), width=width)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report whether the catalog and pin are current")
    args = parser.parse_args()
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    if document.get("schema") != "nfl2k5_scorebug_template_pngs/v1":
        raise SystemExit("unexpected PNG catalog schema")
    wanted = {relative: row(relative) for relative in ART}
    current = all(document["files"].get(k) == v for k, v in wanted.items())
    document["files"].update(wanted)
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    checker = CHECKER.read_text(encoding="utf-8")
    if len(PIN.findall(checker)) != 1:
        raise SystemExit("the checker pin line is not unique")
    pinned = f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{digest}"'
    sealed = current and pinned in checker and CATALOG.read_bytes() == payload
    if args.check:
        print(json.dumps(dict(sealed=sealed, catalog_sha256=digest)))
        return 0 if sealed else 1
    CATALOG.write_bytes(payload)
    CHECKER.write_text(PIN.sub(pinned, checker), encoding="utf-8", newline="\n")
    print(json.dumps(dict(rows=sorted(wanted), catalog_sha256=digest, files=len(document["files"]))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
