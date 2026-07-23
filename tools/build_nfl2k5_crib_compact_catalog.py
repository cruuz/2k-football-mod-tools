#!/usr/bin/env python3
"""Generate the retail-free runtime catalog for 2K5 Mod Studio's Crib tab."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.nfl2k5_crib import (
    COMPACT_CATALOG_PATH,
    COMPACT_CATALOG_SCHEMA,
    Nfl2k5CribCatalog,
)


def document() -> dict[str, object]:
    catalog = Nfl2k5CribCatalog.from_reports()
    rows: list[dict[str, object]] = []
    for asset in catalog.assets:
        row = asdict(asset)
        row["status"] = asset.status.value
        row["storage"] = asset.storage.value
        row["material_names"] = list(asset.material_names)
        rows.append(row)
    return {
        "assets": rows,
        "expectations": asdict(catalog.expectations),
        "payload_policy": "metadata-only-no-retail-bytes",
        "schema": COMPACT_CATALOG_SCHEMA,
    }


def write_catalog(destination: Path) -> Path:
    catalog_document = document()
    payload = (
        json.dumps(catalog_document, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    loaded = Nfl2k5CribCatalog.from_compact_catalog(destination)
    if len(loaded.assets) != len(catalog_document["assets"]):
        raise SystemExit("generated compact catalog failed its count recheck")
    return destination.resolve(strict=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=COMPACT_CATALOG_PATH)
    args = parser.parse_args()
    print(write_catalog(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
