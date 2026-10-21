#!/usr/bin/env python3
"""Beta 77 st2: bring the U.S. Bank Stadium art and pins into the release catalog and the capability registry.

Idempotent and order-independent (the alg_seal_catalog way), so integration can re-run it on the merged tree after any
other job reseals the same catalog: it upserts exactly the PNG rows under ``data/nfl2k5_usbank_model/art`` (size,
SHA-256, PNG width and height read from the files), drops rows for U.S. Bank PNGs that no longer exist, writes the
catalog in its canonical form (``json.dumps(indent=2, sort_keys=True)`` plus a newline), moves the one
``SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256`` pin in ``packaging/check_2k5_mod_studio_release.py``, lists every U.S. Bank
PNG in ``packaging/release-allowlist.txt``, and in the capability registry's U.S. Bank row sets the authored PNG count
(the tree's PNGs and the official marks' externalized ones) and the hash pins (the first and last bundles' retail and
model stretch SHA-256 from ``data/nfl2k5_usbank_model/pins.json``). It never removes or relaxes another row.

    python3 tools/b77/st2_seal.py [--check]
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
PINS = ROOT / "data" / "nfl2k5_usbank_model" / "pins.json"
ART = "data/nfl2k5_usbank_model/art/"
ROW_ID = "nfl2k5.stadiums_fields.modern_usbank"
#: the drawings that carry an official mark: externalized to the official marks pack, counted but not in the tree
OFFICIAL = ("usb_header", "usb_letters", "usb_prow_letters", "LIGHT_usb_blue_sign", "LIGHT_usb_panels")
PIN = re.compile(r'(?m)^SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "[0-9a-f]{64}"$')
COUNT = re.compile(r"\d+ authored PNGs in " + re.escape(ART.rstrip("/")) + r" ")
HASH_PINS = re.compile(r'("id": "' + re.escape(ROW_ID) + r'".*?"hash_pins": \[)([^\]]*)(\])', re.S)


def row(relative: str) -> dict:
    data = (ROOT / relative).read_bytes()
    if data[:16] != b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR":
        raise SystemExit(f"not a PNG: {relative}")
    width, height = struct.unpack_from(">II", data, 16)
    return dict(height=height, sha256=hashlib.sha256(data).hexdigest(), size=len(data), width=width)


def wanted_rows() -> dict:
    return {p.relative_to(ROOT).as_posix(): row(p.relative_to(ROOT).as_posix()) for p in sorted((ROOT / ART).rglob("*.png"))}


def hash_pins() -> list:
    bundles = {b["name"]: b for b in json.loads(PINS.read_text(encoding="utf-8"))["bundles"]}
    first, last = bundles["s15dd.iff"], bundles["s15ns.iff"]
    return [first["retail_sha256"], first["model_sha256"], last["retail_sha256"], last["model_sha256"]]


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
        raise SystemExit("the allowlist has no U.S. Bank art block")
    # the block keeps its order: rows of removed PNGs go, a new PNG goes before the first row that sorts after it
    block = [lines[i] for i in present if lines[i] in wanted]
    for name in sorted(set(wanted) - set(block)):
        at = next((k for k, line in enumerate(block) if line > name), len(block))
        block.insert(at, name)
    kept = [line for line in lines if not (line.startswith(ART) and line.endswith(".png"))]
    at = present[0]
    allow = "\n".join(kept[:at] + block + kept[at:])
    registry = REGISTRY.read_text(encoding="utf-8")
    if len(COUNT.findall(registry)) != 1:
        raise SystemExit("the registry's U.S. Bank PNG count is not unique")
    registry = COUNT.sub(f"{len(wanted) + len(OFFICIAL)} authored PNGs in {ART.rstrip('/')} ", registry)
    found = HASH_PINS.search(registry)
    if not found:
        raise SystemExit("the registry's U.S. Bank row has no hash pins")
    old = found.group(2)
    have = re.findall(r'"([0-9a-f]{64})"', old)
    if len(have) != 4:
        raise SystemExit("the registry's U.S. Bank hash pins are not four digests")
    body = old
    for a, b in zip(have, hash_pins()):
        body = body.replace(f'"{a}"', f'"{b}"', 1)
    registry = registry[:found.start(2)] + body + registry[found.end(2):]
    return payload, checker, allow, registry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report whether the catalog, pin, allowlist and registry row are current")
    args = parser.parse_args()
    wanted = wanted_rows()
    payload, checker, allow, registry = sealed_texts(wanted)
    current = (CATALOG.read_bytes() == payload and CHECKER.read_text(encoding="utf-8") == checker
               and ALLOWLIST.read_text(encoding="utf-8") == allow and REGISTRY.read_text(encoding="utf-8") == registry)
    if args.check:
        print(json.dumps(dict(sealed=current, pngs=len(wanted))))
        return 0 if current else 1
    with open(CATALOG, "wb") as f:
        f.write(payload)
    for path, text in ((CHECKER, checker), (ALLOWLIST, allow), (REGISTRY, registry)):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(json.dumps(dict(sealed=True, pngs=len(wanted), hash_pins=hash_pins())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
