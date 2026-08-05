#!/usr/bin/env python3
"""Build the compact, retail-payload-free 2K5 equipment texture catalog.

The research TSV contains all 51 embedded TSET references for each of the 634
uniform packages. Jersey, pants, and sleeve already have product writers, so
this catalog carries only chunks 4..10: socks, elbow pads, gloves, long sleeves,
shoes, and wristbands. Every reviewed row is swizzled P8 with a shared index
chain and an independent palette. The bounded writer changes only a selected
palette, preserving every sibling reference exactly. This catalog contains
descriptors and hashes, never pixel or compressed resource bytes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "reports/assets/nfl2k5_uniform_tset_textures.tsv"
DEFAULT_OUTPUT = (
    ROOT / "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json"
)
SCHEMA = "nfl2k5_uniform_equipment_export_catalog/v1"
SOURCE_SHA256 = "f8c60d618cab8326d7a215936a2e66a75d9f399c13c0087608fbc2010bcd3abd"
SOURCE_ROWS = 32_334
OUTPUT_ROWS = 28_530
PACKAGE_COUNT = 634
COLUMNS = (
    "outer_index",
    "set_selector",
    "tset_chunk_index",
    "reference_index",
    "name",
    "width",
    "height",
    "pixel_offset",
    "palette_offset",
    "packed_format",
    "packed_size",
    "descriptor_flags",
    "base_pixel_sha256",
    "palette_bgra_sha256",
)
EXPECTED_PER_PACKAGE = {
    4: 2,
    5: 14,
    6: 8,
    7: 6,
    8: 6,
    9: 6,
    10: 3,
}


class CatalogBuildError(ValueError):
    """The source inventory no longer matches the reviewed export contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogBuildError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: Path) -> dict[str, object]:
    payload = source.read_bytes()
    _require(_sha256(payload) == SOURCE_SHA256, "source TSV hash changed")
    text = payload.decode("utf-8")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    source_rows = list(reader)
    _require(len(source_rows) == SOURCE_ROWS, "source TSV row count changed")
    rows: list[list[object]] = []
    selectors: set[tuple[int, int, int]] = set()
    packages: dict[int, dict[int, int]] = {}
    for number, row in enumerate(source_rows, 2):
        try:
            outer = int(row["outer_index"])
            chunk = int(row["tset_chunk_index"])
            reference = int(row["reference_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogBuildError(f"invalid selector at TSV line {number}") from exc
        if chunk < 4:
            continue
        _require(chunk in EXPECTED_PER_PACKAGE, f"unexpected TSET chunk {chunk}")
        selector = (outer, chunk, reference)
        _require(selector not in selectors, f"duplicate selector {selector}")
        selectors.add(selector)
        by_chunk = packages.setdefault(outer, {})
        by_chunk[chunk] = by_chunk.get(chunk, 0) + 1
        name = row["name"]
        _require(name and all(0x20 <= ord(char) < 0x7F for char in name),
                 f"unsafe texture name at TSV line {number}")
        try:
            values: list[object] = [
                outer,
                row["logical_name"].removesuffix(".IFF"),
                chunk,
                reference,
                name,
                int(row["width"]),
                int(row["height"]),
                int(row["pixel_offset"]),
                int(row["palette_offset"]),
                int(row["packed_format"], 16),
                int(row["packed_size"]),
                int(row["descriptor_flags"], 16),
                row["base_pixel_sha256"],
                row["palette_bgra_sha256"],
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogBuildError(f"invalid descriptor at TSV line {number}") from exc
        _require(
            isinstance(values[1], str)
            and len(values[1]) >= 4
            and values[1][2] in {"H", "A"},
            f"invalid uniform selector at TSV line {number}",
        )
        _require(values[5] in {64, 128, 256} and values[6] in {64, 128, 256},
                 f"unexpected dimensions at TSV line {number}")
        _require(all(
            isinstance(value, str) and len(value) == 64
            and set(value) <= set("0123456789abcdef")
            for value in values[-2:]
        ), f"invalid source hash at TSV line {number}")
        rows.append(values)
    _require(len(rows) == OUTPUT_ROWS, "export catalog row count changed")
    _require(len(packages) == PACKAGE_COUNT, "uniform package count changed")
    for outer, counts in packages.items():
        _require(counts == EXPECTED_PER_PACKAGE,
                 f"uniform package {outer} equipment inventory is incomplete")
    return {
        "columns": list(COLUMNS),
        "contract": {
            "access": "preview-export-and-palette-import",
            "import_mode": "fixed-shared-index-palette",
            "import_supported": True,
            "retail_payload_bytes": False,
            "source_rows": SOURCE_ROWS,
            "source_tsv_sha256": SOURCE_SHA256,
        },
        "rows": rows,
        "schema": SCHEMA,
        "summary": {
            "package_count": PACKAGE_COUNT,
            "target_count": OUTPUT_ROWS,
            "targets_per_package": sum(EXPECTED_PER_PACKAGE.values()),
        },
    }


def serialize(document: dict[str, object]) -> bytes:
    """Keep the catalog compact while leaving no blob-like multi-megabyte line."""

    rows = document["rows"]
    assert isinstance(rows, list)
    lines = [
        "{",
        '"columns":' + json.dumps(
            document["columns"], separators=(",", ":"), sort_keys=True
        ) + ",",
        '"contract":' + json.dumps(
            document["contract"], separators=(",", ":"), sort_keys=True
        ) + ",",
        '"rows":[',
    ]
    lines.extend(
        json.dumps(row, separators=(",", ":"), sort_keys=True)
        + ("," if number + 1 < len(rows) else "")
        for number, row in enumerate(rows)
    )
    lines.extend((
        "],",
        '"schema":' + json.dumps(document["schema"]) + ",",
        '"summary":' + json.dumps(
            document["summary"], separators=(",", ":"), sort_keys=True
        ),
        "}",
    ))
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    _require(
        max(map(len, payload.splitlines())) <= 4096,
        "serialized catalog contains an unsafe blob-like line",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    document = build(args.source)
    payload = serialize(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if args.replace else "xb"
    with args.output.open(mode) as stream:
        stream.write(payload)
    print(
        f"NFL2K5_UNIFORM_EQUIPMENT_EXPORT_CATALOG_PASS "
        f"rows={len(document['rows'])} bytes={len(payload)} sha256={_sha256(payload)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
