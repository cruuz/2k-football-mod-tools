#!/usr/bin/env python3
"""Recover the explicit 2K3..2K8 animation-generation tags in APF's XEX.

The input PE is the independently decrypted/decompressed memory image emitted
by ``tools/xex_extract_pe.cpp``.  This scanner is deliberately narrower than a
generic strings pass: it accepts only NUL-terminated UTF-16BE animation names
beginning with ``ANM_`` and then proves that every selected 2K6 name is backed
by at least one aligned big-endian pointer in the retail image.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import struct


SCHEMA = "apf2k8_2k6_animation_lineage/v1"
EXPECTED_APF_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_APF_PE_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_NFL_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
UTF16_BE_ASCII = re.compile(rb"(?:\x00[\x20-\x7e]){4,}\x00\x00")
UTF16_LE_ASCII = re.compile(rb"(?:[\x20-\x7e]\x00){4,}\x00\x00")
YEAR_TAG = re.compile(r"2K[0-9]+", re.IGNORECASE)
REGISTRY_BASE = 0x84D75500
REGISTRY_RECORD_SIZE = 0x2C
REGISTRY_RECORD_COUNT = 5884
REGISTRY_END = REGISTRY_BASE + REGISTRY_RECORD_SIZE * REGISTRY_RECORD_COUNT


class LineageError(ValueError):
    """Raised when a pinned executable or recovered invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LineageError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": sha256(data)}


def utf16_ascii(data: bytes, endian: str) -> list[tuple[int, str]]:
    pattern = UTF16_BE_ASCII if endian == "big" else UTF16_LE_ASCII
    character_slice = slice(1, -2, 2) if endian == "big" else slice(0, -2, 2)
    return [
        (match.start(), match.group()[character_slice].decode("ascii"))
        for match in pattern.finditer(data)
    ]


def pe_image_base(data: bytes) -> int:
    require(data[:2] == b"MZ" and len(data) >= 0x100, "APF PE has no MZ header")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    require(pe_offset + 0x38 <= len(data), "APF PE header is truncated")
    require(data[pe_offset : pe_offset + 4] == b"PE\0\0", "APF PE signature differs")
    optional = pe_offset + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    require(magic == 0x10B, "APF executable is not the expected PE32 image")
    return struct.unpack_from("<I", data, optional + 28)[0]


def utf16be_at(data: bytes, image_base: int, address: int) -> str:
    offset = address - image_base
    require(0 <= offset < len(data), "UTF-16BE pointer is outside APF image")
    characters: list[str] = []
    while offset + 1 < len(data) and data[offset] == 0 and \
            0x20 <= data[offset + 1] <= 0x7E:
        characters.append(chr(data[offset + 1]))
        offset += 2
    require(offset + 1 < len(data) and data[offset : offset + 2] == b"\0\0",
            "APF UTF-16BE string is not terminated")
    return "".join(characters)


def category(name: str) -> str:
    upper = name.upper()
    if "BUMPANDRUN" in upper:
        return "bump_and_run"
    if "CATCH" in upper:
        return "receiver_catch"
    if "_QB_" in upper:
        return "quarterback"
    if "BLOCK" in upper:
        return "blocking"
    if "CUT" in upper or "MOVEMENT" in upper:
        return "movement_and_cuts"
    return "other"


def nfl_motion_names(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    require(document.get("schema") == "nfl2k5_motion_inventory/v1", (
        "NFL motion inventory schema differs"
    ))
    resources = document.get("resources")
    require(isinstance(resources, list), "NFL motion inventory has no resources")
    names = [row.get("name") for row in resources if isinstance(row, dict)]
    require(all(isinstance(name, str) for name in names), (
        "NFL motion inventory contains an invalid name"
    ))
    return names


def build_report(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]]]:
    apf_pe = args.apf_pe.read_bytes()
    apf_xex = args.apf_xex.read_bytes()
    nfl_xbe = args.nfl_xbe.read_bytes()
    require(sha256(apf_pe) == EXPECTED_APF_PE_SHA256, "APF decompressed PE changed")
    require(sha256(apf_xex) == EXPECTED_APF_XEX_SHA256, "APF retail XEX changed")
    require(sha256(nfl_xbe) == EXPECTED_NFL_XBE_SHA256, "NFL 2K5 XBE changed")

    header = json.loads(args.apf_header.read_text(encoding="utf-8"))
    require(header["inputs"]["decompressed_pe_sha256"] == EXPECTED_APF_PE_SHA256,
            "APF header report does not pin the recovered PE")
    image_base = pe_image_base(apf_pe)
    require(image_base == 0x82000000, "APF PE image base changed")

    apf_strings = utf16_ascii(apf_pe, "big")
    apf_animation = [row for row in apf_strings if row[1].startswith("ANM_")]
    year_counts: Counter[str] = Counter()
    for _, name in apf_animation:
        year_counts.update(tag.upper() for tag in YEAR_TAG.findall(name))

    selected = [
        (offset, name) for offset, name in apf_animation
        if "2K6" in (tag.upper() for tag in YEAR_TAG.findall(name))
    ]
    require(len(selected) == 519, "APF 2K6 animation identifier count changed")
    require(len({name for _, name in selected}) == len(selected), (
        "APF 2K6 animation identifiers are no longer unique"
    ))

    targets = {image_base + offset for offset, _ in selected}
    references: dict[int, list[int]] = defaultdict(list)
    aligned_size = len(apf_pe) - len(apf_pe) % 4
    for index, (word,) in enumerate(struct.iter_unpack(">I", apf_pe[:aligned_size])):
        if word in targets:
            references[word].append(image_base + index * 4)
    require(all(references[target] for target in targets), (
        "one or more APF 2K6 identifiers lost their aligned pointer evidence"
    ))

    registry: list[dict[str, object]] = []
    registry_year_counts: Counter[str] = Counter()
    for index in range(REGISTRY_RECORD_COUNT):
        address = REGISTRY_BASE + index * REGISTRY_RECORD_SIZE
        offset = address - image_base
        words = struct.unpack_from(">11I", apf_pe, offset)
        filename = utf16be_at(apf_pe, image_base, words[0])
        primary_name = utf16be_at(apf_pe, image_base, words[1])
        require(primary_name.startswith("ANM_"), (
            f"animation-definition record {index} has no ANM_ primary name"
        ))
        registry_year_counts.update(
            tag.upper() for tag in YEAR_TAG.findall(primary_name)
        )
        registry.append({
            "index": index, "address": address, "filename": filename,
            "primary_name": primary_name, "words": words,
        })
    require(REGISTRY_END == 0x84DB4850, "animation-definition registry end differs")
    require((registry[0]["filename"], registry[0]["primary_name"]) ==
            ("a004c.ani", "ANM_CELEBRATE_TD_SIGNAL"), (
                "animation-definition registry first record differs"
            ))
    require((registry[-1]["filename"], registry[-1]["primary_name"]) ==
            ("fs371di2m.ani", "ANM_TOLINEQB_QB_POINT"), (
                "animation-definition registry last record differs"
            ))

    rows: list[dict[str, object]] = []
    for offset, name in selected:
        va = image_base + offset
        locations = references[va]
        associations: list[tuple[int, int, str]] = []
        for location in locations:
            require(REGISTRY_BASE <= location < REGISTRY_END, (
                "2K6 name pointer is outside the animation-definition registry"
            ))
            field_offset = (location - REGISTRY_BASE) % REGISTRY_RECORD_SIZE
            require(field_offset in (0x04, 0x08), (
                "2K6 name pointer is not a primary/paired registry-name field"
            ))
            record_address = location - field_offset
            record_index = (record_address - REGISTRY_BASE) // REGISTRY_RECORD_SIZE
            filename = str(registry[record_index]["filename"])
            require(filename.lower().endswith(".ani"), (
                "2K6 definition record has no .ani filename"
            ))
            associations.append((record_address, field_offset, filename))
        rows.append({
            "index": len(rows),
            "name": name,
            "category": category(name),
            "pe_offset": f"0x{offset:08X}",
            "virtual_address": f"0x{va:08X}",
            "pointer_reference_count": len(locations),
            "primary_definition_count": sum(
                field == 0x04 for _, field, _ in associations
            ),
            "paired_name_reference_count": sum(
                field == 0x08 for _, field, _ in associations
            ),
            "definition_record_addresses": ",".join(
                f"0x{record:08X}" for record, _, _ in associations
            ),
            "animation_filenames": ",".join(
                dict.fromkeys(filename for _, _, filename in associations)
            ),
            "pointer_reference_addresses": ",".join(
                f"0x{location:08X}" for location in locations
            ),
        })

    nfl_animation = [
        name for _, name in utf16_ascii(nfl_xbe, "little")
        if name.startswith("ANM_")
    ]
    nfl_2k6_animation = [name for name in nfl_animation if "2K6" in name.upper()]
    motion_names = nfl_motion_names(args.nfl_motion_inventory)
    nfl_2k6_motion = [name for name in motion_names if "2K6" in name.upper()]

    category_counts = Counter(row["category"] for row in rows)
    reference_distribution = Counter(row["pointer_reference_count"] for row in rows)
    require(sum(reference_distribution.values()) == 519, "pointer distribution differs")
    require(sum(count * multiplicity for count, multiplicity in reference_distribution.items()) == 597,
            "APF 2K6 pointer reference total changed")
    primary_count = sum(row["primary_definition_count"] for row in rows)
    paired_count = sum(row["paired_name_reference_count"] for row in rows)
    animation_filenames = {
        filename
        for row in rows
        for filename in str(row["animation_filenames"]).split(",")
    }
    require((primary_count, paired_count, len(animation_filenames)) == (309, 288, 225),
            "APF 2K6 definition-record association changed")

    report: dict[str, object] = {
        "schema": SCHEMA,
        "result": {
            "apf_animation_identifier_count": len(apf_animation),
            "apf_unique_animation_identifier_count": len({name for _, name in apf_animation}),
            "apf_2k6_animation_identifier_count": len(rows),
            "apf_2k6_unique_identifier_count": len({row["name"] for row in rows}),
            "apf_2k6_pointer_reference_total": sum(
                row["pointer_reference_count"] for row in rows
            ),
            "all_apf_2k6_identifiers_pointer_backed": True,
            "static_animation_definition_record_count": len(registry),
            "static_animation_definition_record_size": REGISTRY_RECORD_SIZE,
            "apf_2k6_primary_definition_count": primary_count,
            "apf_2k6_paired_name_reference_count": paired_count,
            "apf_2k6_unique_animation_filename_count": len(animation_filenames),
            "all_apf_2k6_references_are_definition_name_fields": True,
            "nfl2k5_xbe_2k6_animation_identifier_count": len(nfl_2k6_animation),
            "nfl2k5_motion_catalog_2k6_name_count": len(nfl_2k6_motion),
            "formal_nfl_2k6_product_identity_proved": False,
            "runtime_consumption_of_every_identifier_proved": False,
        },
        "annual_tag_counts": dict(sorted(year_counts.items())),
        "registry_primary_annual_tag_counts": dict(sorted(registry_year_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "pointer_reference_count_distribution": {
            str(count): multiplicity
            for count, multiplicity in sorted(reference_distribution.items())
        },
        "interpretation": {
            "proved": (
                "The retail APF 2K8 executable contains 5,884 contiguous static "
                "animation-definition records. Their exact +0x04 primary-name and "
                "+0x08 paired-name fields reference 519 distinct identifiers tagged "
                "2K6 a total of 597 times and associate them with 225 .ani filenames."
            ),
            "lineage_claim": (
                "This is direct evidence of a 2K6-era gameplay/animation generation "
                "inside APF's NFL code lineage."
            ),
            "boundary": (
                "The internal 2K6 tag does not by itself prove that Visual Concepts "
                "had a formally titled, complete, or releasable product named NFL 2K6; "
                "nor does a definition filename prove that its matching motion payload "
                "ships or is selected by a reachable retail path."
            ),
            "nfl_comparison_scope": (
                "The zero comparison covers the supplied NFL 2K5 XBE's UTF-16LE "
                "ANM_ strings and the complete recovered 5,198-resource NFL motion "
                "name catalog; it is not an absence claim over every anonymous byte."
            ),
        },
        "pe": {
            "image_base": f"0x{image_base:08X}",
            "memory_image_size": len(apf_pe),
            "memory_image_sha256": sha256(apf_pe),
            "derivation": (
                "tools/xex_extract_pe.cpp: retail AES decrypt, SHA-1 chain verify, "
                "and LZX decompress; no import-thunk patching"
            ),
        },
        "animation_definition_registry": {
            "start": f"0x{REGISTRY_BASE:08X}",
            "end_exclusive": f"0x{REGISTRY_END:08X}",
            "record_size": REGISTRY_RECORD_SIZE,
            "record_count": REGISTRY_RECORD_COUNT,
            "filename_pointer_field": "+0x00",
            "primary_identifier_pointer_field": "+0x04",
            "paired_identifier_pointer_field": "+0x08 when nonzero",
            "first_record": {
                "address": f"0x{registry[0]['address']:08X}",
                "filename": registry[0]["filename"],
                "primary_name": registry[0]["primary_name"],
            },
            "last_record": {
                "address": f"0x{registry[-1]['address']:08X}",
                "filename": registry[-1]["filename"],
                "primary_name": registry[-1]["primary_name"],
            },
        },
        "identifiers": rows,
        "sources": {
            "apf_xex": pin(args.apf_xex),
            "apf_header_report": pin(args.apf_header),
            "nfl_xbe": pin(args.nfl_xbe),
            "nfl_motion_inventory": pin(args.nfl_motion_inventory),
            "generator": pin(Path(__file__)),
        },
        "portme": [
            "// PORTME(0x84D75500): finish executable ownership from the 5,884-record static definition registry to its retail consumer before claiming live use of each 2K6 definition.",
            "// PORTME(0x84D7E6C0): map the 225 referenced .ani filenames to concrete APF archive motion payloads; a compiled definition is not itself a shipped animation clip.",
            "// PORTME: an exact product/build identifier is still required before calling APF a cancelled NFL 2K6 build without qualification.",
        ],
    }
    return report, rows


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]),
                                dialect="excel-tab", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apf-pe", type=Path, required=True)
    parser.add_argument("--apf-xex", type=Path, required=True)
    parser.add_argument("--apf-header", type=Path, required=True)
    parser.add_argument("--nfl-xbe", type=Path, required=True)
    parser.add_argument("--nfl-motion-inventory", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args()
    report, rows = build_report(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_tsv(args.tsv, rows)
    print(
        "APF_2K6_ANIMATION_LINEAGE_COMPLETE "
        f"identifiers={len(rows)} pointers={sum(r['pointer_reference_count'] for r in rows)} "
        f"annual_tags={report['annual_tag_counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
