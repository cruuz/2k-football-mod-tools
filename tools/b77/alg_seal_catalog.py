#!/usr/bin/env python3
"""Beta 77 ALG: bring the Allegiant Stadium art into the reviewed release PNG catalog and reseal it.

Idempotent and order-independent, so integration can re-run it on the merged tree after any other job reseals the
same catalog: it upserts exactly the PNG rows under ``data/nfl2k5_allegiant_model/art`` (size, SHA-256, PNG width and
height read from the files), drops rows for Allegiant PNGs that no longer exist, writes the catalog in its canonical
form (``json.dumps(indent=2, sort_keys=True)`` plus a newline), moves the one ``SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256``
pin in ``packaging/check_2k5_mod_studio_release.py``, lists every Allegiant PNG in ``packaging/release-allowlist.txt``
and sets the PNG count in the capability registry's Allegiant row. It never removes or relaxes another row.

    python3 tools/b77/alg_seal_catalog.py [--check]
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
ALLOWLIST = ROOT / "packaging" / "release-allowlist.txt"
REGISTRY = ROOT / "mod_editor" / "capabilities" / "registry.v1.json"
ART = "data/nfl2k5_allegiant_model/art/"
PIN = re.compile(r'(?m)^SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "[0-9a-f]{64}"$')
COUNT = re.compile(r"\d+ authored PNGs in " + re.escape(ART.rstrip("/")) + r" ")


def row(relative: str) -> dict:
    data = (ROOT / relative).read_bytes()
    if data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR":
        raise SystemExit(f"not a PNG: {relative}")
    width, height = struct.unpack_from(">II", data, 16)
    return dict(height=height, sha256=hashlib.sha256(data).hexdigest(), size=len(data), width=width)


def wanted_rows() -> dict:
    return {p.relative_to(ROOT).as_posix(): row(p.relative_to(ROOT).as_posix()) for p in sorted((ROOT / ART).rglob("*.png"))}


def sealed_texts(wanted: dict):
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    if document.get("schema") != "nfl2k5_scorebug_template_pngs/v1":
        raise SystemExit("unexpected PNG catalog schema")
    files = {k: v for k, v in document["files"].items() if not k.startswith(ART)}
    files.update(wanted)
    document["files"] = files
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checker = CHECKER.read_text(encoding="utf-8")
    if len(PIN.findall(checker)) != 1:
        raise SystemExit("the checker pin line is not unique")
    checker = PIN.sub(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{hashlib.sha256(payload).hexdigest()}"', checker)
    lines = ALLOWLIST.read_text(encoding="utf-8").split("\n")
    present = [i for i, line in enumerate(lines) if line.startswith(ART) and line.endswith(".png")]
    if not present:
        raise SystemExit("the allowlist has no Allegiant art block")
    kept = [line for line in lines if not (line.startswith(ART) and line.endswith(".png"))]
    at = present[0] - sum(1 for i in range(present[0]) if lines[i].startswith(ART) and lines[i].endswith(".png"))
    allow = "\n".join(kept[:at] + sorted(wanted) + kept[at:])
    registry = REGISTRY.read_text(encoding="utf-8")
    if len(COUNT.findall(registry)) != 1:
        raise SystemExit("the registry's Allegiant PNG count is not unique")
    registry = COUNT.sub(f"{len(wanted)} authored PNGs in {ART.rstrip('/')} ", registry)
    return payload, checker, allow, registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report whether the catalog, pin, allowlist and count are current")
    args = parser.parse_args()
    wanted = wanted_rows()
    payload, checker, allow, registry = sealed_texts(wanted)
    current = (CATALOG.read_bytes() == payload and CHECKER.read_text(encoding="utf-8") == checker
               and ALLOWLIST.read_text(encoding="utf-8") == allow and REGISTRY.read_text(encoding="utf-8") == registry)
    if args.check:
        print(json.dumps(dict(sealed=current, pngs=len(wanted))))
        return 0 if current else 1
    CATALOG.write_bytes(payload)
    for path, text in ((CHECKER, checker), (ALLOWLIST, allow), (REGISTRY, registry)):
        path.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(dict(pngs=len(wanted), catalog_sha256=hashlib.sha256(payload).hexdigest())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
