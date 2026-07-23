#!/usr/bin/env python3
"""Close the static ownership boundary around APF 2K8 ``reference.iff``.

This is deliberately read-only.  It joins focused Ghidra traces with a
complete byte search of the four retail APF pack files and an exact NFL 2K5
menu-descriptor witness.  It does not launch either game or modify an image.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import mmap
import struct
from pathlib import Path
from typing import Any


APF_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
APF_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
NFL_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"

APF_PACK_SIZES = {
    "0A": 1_140_850_688,
    "0B": 1_073_838_080,
    "1A": 1_140_850_688,
    "1B": 517_971_968,
}


class EvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def hx(value: int, width: int = 8) -> str:
    return f"0x{value:0{width}x}"


def all_hits(view: mmap.mmap, needle: bytes) -> list[int]:
    result: list[int] = []
    cursor = 0
    while True:
        cursor = view.find(needle, cursor)
        if cursor < 0:
            return result
        result.append(cursor)
        cursor += 1


def scan_packs(game: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    packs = manifest["packs"]
    entries = manifest["entries"]
    require([pack["name"] for pack in packs] == ["0A", "0B", "1A", "1B"],
            "APF pack order changed")
    require({pack["name"]: pack["actual_size"] for pack in packs} == APF_PACK_SIZES,
            "APF pack sizes changed")
    require(manifest["format"]["table_start"] == 0x58, "outer table start changed")
    require(manifest["format"]["entry_record_size"] == 12,
            "outer entry size changed")

    ranges = sorted((entry["virtual_offset"], entry["virtual_end"],
                     entry["table_index"], entry["name_id"])
                    for entry in entries)
    starts = [item[0] for item in ranges]

    hash_values = {
        "reference_iff_crc32_upper_ascii": 0xBE047DD2,
        "reference_data_crc32_upper_ascii": 0xF0D95EFA,
        "refr_crc32_upper_ascii": 0x15578F45,
    }
    literal_values = {
        "reference_iff_ascii": b"reference.iff",
        "reference_iff_utf16be": "reference.iff".encode("utf-16be"),
        "reference_data_utf16be": "reference_data".encode("utf-16be"),
        "closed_book_utf16be": "closed_book".encode("utf-16be"),
        "open_book_utf16be": "open_book".encode("utf-16be"),
    }
    hash_hits: dict[str, dict[str, list[dict[str, Any]]]] = {
        label: {"big_endian": [], "little_endian": []}
        for label in hash_values
    }
    literal_hits: dict[str, list[dict[str, Any]]] = {
        label: [] for label in literal_values
    }

    def occurrence(pack: dict[str, Any], offset: int) -> dict[str, Any]:
        virtual = int(pack["virtual_start"]) + offset
        index = bisect.bisect_right(starts, virtual) - 1
        owner: dict[str, Any] | None = None
        if index >= 0:
            first, after, ordinal, name_id = ranges[index]
            if first <= virtual < after:
                owner = {
                    "outer_index": ordinal,
                    "outer_name_id": name_id,
                    "relative_offset": hx(virtual - first),
                }
        return {
            "pack": pack["name"],
            "pack_offset": hx(offset),
            "virtual_offset": hx(virtual),
            "owner": owner,
        }

    for pack in packs:
        path = game / pack["name"]
        require(path.stat().st_size == APF_PACK_SIZES[pack["name"]],
                f"{path} size changed")
        with path.open("rb") as source, mmap.mmap(
                source.fileno(), 0, access=mmap.ACCESS_READ) as view:
            for label, value in hash_values.items():
                for byte_order in ("big_endian", "little_endian"):
                    order = "big" if byte_order == "big_endian" else "little"
                    for offset in all_hits(view, value.to_bytes(4, order)):
                        hash_hits[label][byte_order].append(occurrence(pack, offset))
            for label, needle in literal_values.items():
                for offset in all_hits(view, needle):
                    literal_hits[label].append(occurrence(pack, offset))

    outer = hash_hits["reference_iff_crc32_upper_ascii"]
    require(len(outer["big_endian"]) == 1 and not outer["little_endian"],
            "reference.iff hash occurrence count changed")
    require(outer["big_endian"][0]["pack"] == "0A" and
            outer["big_endian"][0]["pack_offset"] == "0x0000358c" and
            outer["big_endian"][0]["owner"] is None,
            "reference.iff hash is no longer confined to its outer-table row")
    refr = hash_hits["refr_crc32_upper_ascii"]
    require(len(refr["big_endian"]) == 1 and not refr["little_endian"],
            "REFR hash occurrence count changed")
    require(refr["big_endian"][0]["owner"] == {
        "outer_index": 1135,
        "outer_name_id": "0xbe047dd2",
        "relative_offset": "0x00000098",
    }, "REFR hash escaped reference.iff's own footer")
    resource_hash = hash_hits["reference_data_crc32_upper_ascii"]
    require(not resource_hash["big_endian"] and not resource_hash["little_endian"],
            "serialized reference_data hash edge appeared")

    require(not literal_hits["reference_iff_ascii"] and
            not literal_hits["reference_iff_utf16be"],
            "serialized reference.iff literal appeared")
    require([hit["owner"]["outer_index"] for hit in
             literal_hits["reference_data_utf16be"]] == [1135],
            "reference_data literal escaped its own footer")
    require([hit["owner"]["outer_index"] for hit in
             literal_hits["closed_book_utf16be"]] == [1135],
            "closed_book literal escaped its own footer")
    require([hit["owner"]["outer_index"] for hit in
             literal_hits["open_book_utf16be"]] == [499, 700, 1135],
            "open_book literal owners changed")

    return {
        "pack_count": len(packs),
        "total_bytes_scanned": sum(APF_PACK_SIZES.values()),
        "total_bytes_scanned_hex": hx(sum(APF_PACK_SIZES.values())),
        "hash_occurrences": hash_hits,
        "literal_occurrences": literal_hits,
        "interpretation": (
            "The sole reference.iff filename hash is its own outer-table row; "
            "the sole REFR hash and all reference-specific names are self-footer "
            "metadata. No other serialized owner edge exists in the retail packs."
        ),
    }


def utf16le_at(data: bytes, offset: int) -> str:
    cursor = offset
    while cursor + 1 < len(data) and data[cursor:cursor + 2] != b"\0\0":
        cursor += 2
    return data[offset:cursor].decode("utf-16le")


def nfl_route(xbe_path: Path) -> dict[str, Any]:
    data = xbe_path.read_bytes()
    require(hashlib.md5(data).hexdigest() == NFL_XBE_MD5, "NFL XBE MD5 changed")
    require(hashlib.sha256(data).hexdigest() == NFL_XBE_SHA256,
            "NFL XBE SHA-256 changed")

    extras_row = struct.unpack_from("<III", data, 0x00535CF8)
    require(extras_row == (0, 0x00EA48C4, 0x00583B18),
            "NFL Extras Reference Guide row changed")
    require(utf16le_at(data, 0x00B335A4) == "Reference Guide",
            "NFL Reference Guide label changed")
    descriptor = struct.unpack_from("<III", data, 0x00579038)
    require(descriptor == (0x00EB89A4, 0x00583AE8, 0x000F3DA0),
            "NFL Reference descriptor changed")
    require(utf16le_at(data, 0x00B47684) == "Reference",
            "NFL Reference descriptor label changed")
    event_map = list(struct.iter_unpack("<II", data[0x00579008:0x00579038]))
    require(event_map == [(6, 0x00583980), (7, 0x005839C8),
                          (12, 0x00583A10), (1, 0x00583A58),
                          (2, 0x00583AA0), (0, 0)],
            "NFL Reference event map changed")
    event_one = struct.unpack_from("<IIII", data, 0x00578F78)
    event_two = struct.unpack_from("<IIII", data, 0x00578FC0)
    require(event_one == (3, 0, 0, 0x003707C0),
            "NFL Reference event-1 callback changed")
    require(event_two == (3, 0, 0, 0x003708B0),
            "NFL Reference event-2 callback changed")

    strings = {
        "reference_playbook_owner": (0x00B4B6C0, "REFERENCEPLAYBOOK"),
        "reference_playbook_archive": (0x00B4B6E4, "reference-pb.iff"),
        "reference_owner": (0x00B4B708, "REFERENCE"),
        "reference_archive": (0x00B4B71C, "reference.iff"),
        "reference_data": (0x00B4B738, "reference_data"),
        "closed_book": (0x00B4B758, "closed_book"),
        "open_book": (0x00B4B770, "open_book"),
    }
    for offset, expected in strings.values():
        require(utf16le_at(data, offset) == expected,
                f"NFL string {expected} changed")

    return {
        "extras_source_row": {
            "address": "0x005407d8",
            "type": 0,
            "label_pointer": "0x00ea48c4",
            "label": "Reference Guide",
            "target_descriptor": "0x00583b18",
        },
        "reference_descriptor": {
            "address": "0x00583b18",
            "label": "Reference",
            "event_map": "0x00583ae8",
            "generic_callback": "0x000f3da0",
            "event_pairs": [[event, hx(record)] for event, record in event_map],
            "event_1_action": "0x00583a58",
            "event_1_callback": "0x003707c0",
            "event_2_action": "0x00583aa0",
            "event_2_callback": "0x003708b0",
        },
        "event_1_initializer": {
            "archive_pairs": [
                ["REFERENCEPLAYBOOK", "reference-pb.iff"],
                ["REFERENCE", "reference.iff"],
            ],
            "resources": ["reference_data", "closed_book:SCNE", "open_book:SCNE"],
            "node_names": ["book", "tab1", "tab2", "tab3", "tab4"],
        },
        "interpretation": (
            "NFL 2K5 has a serialized Extras row, state descriptor, event-1 "
            "initializer, and event-2 teardown route for the Reference Guide."
        ),
    }


def require_trace(trace: str, phrases: tuple[str, ...], label: str) -> None:
    for phrase in phrases:
        require(phrase in trace, f"{label} trace lacks {phrase!r}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--apf-trace", type=Path, default=root /
                        "reports/cut_content/apf_nfl_lineage/reference_runtime_owner/"
                        "apf_reference_runtime_owner_trace.txt")
    parser.add_argument("--apf-pseudo", type=Path, default=root /
                        "reports/cut_content/apf_nfl_lineage/reference_runtime_owner/"
                        "apf_reference_runtime_owner_pseudo_c.c")
    parser.add_argument("--nfl-trace", type=Path, default=root /
                        "reports/cut_content/apf_nfl_lineage/reference_runtime_owner/"
                        "nfl_reference_runtime_owner_trace.txt")
    parser.add_argument("--nfl-pseudo", type=Path, default=root /
                        "reports/cut_content/apf_nfl_lineage/reference_runtime_owner/"
                        "nfl_reference_runtime_owner_pseudo_c.c")
    parser.add_argument("--output", type=Path, default=root /
                        "reports/cut_content/apf_nfl_lineage/"
                        "reference_runtime_owner.json")
    args = parser.parse_args()

    apf_xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
    nfl_xbe = root / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
    require(digest(apf_xex, "md5") == APF_XEX_MD5, "APF XEX MD5 changed")
    require(digest(apf_xex) == APF_XEX_SHA256, "APF XEX SHA-256 changed")

    apf_trace = args.apf_trace.read_text(encoding="utf-8")
    apf_pseudo = args.apf_pseudo.read_text(encoding="utf-8")
    nfl_trace = args.nfl_trace.read_text(encoding="utf-8")
    nfl_pseudo = args.nfl_pseudo.read_text(encoding="utf-8")
    require_trace(apf_trace, (
        "Program MD5: 217eea6084c3d03f0f1143802b1f5636",
        "0x84AB0FA8 section=.text",
        "fullwords=0x844F6828(.pdata,none)",
        "0x84AB1028 section=.text",
        "0x84AB1040 section=.text",
        "0x84AB1058 section=.text",
        "0x8469170C raw=0x4841FA05",
        "instruction=bl 0x84ab1110",
        "0x84691114 bl 0x84ab1148",
        "reference.iff ASCII=",
        "reference_data UTF16BE=",
    ), "APF")
    require_trace(apf_pseudo, (
        "DAT_85234eb0 = Function_84B16398",
        "return *(undefined4 *)(param_1 * 4 + DAT_85234eb0);",
        "param_2 * 0x1c",
    ), "APF pseudo-C")
    require_trace(nfl_trace, (
        "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
        "Extras row 0x005407D8",
        "target descriptor 0x00583B18",
        "0x00583A64 raw=0x003707C0",
        "0x00583AAC raw=0x003708B0",
        "FUNCTION 0x003707C0",
    ), "NFL")
    require_trace(nfl_pseudo, (
        "/* 0x003707C0:",
        "FUN_00043f50",
        "FUN_000449e0",
        "/* 0x003708B0:",
    ), "NFL pseudo-C")

    pack_scan = scan_packs(
        root / "extracted/All-Pro Football 2K8 (USA)",
        root / "reports/manifests/apf_outer.json")
    nfl = nfl_route(nfl_xbe)

    canonical = "reports/cut_content/apf_nfl_lineage/reference_runtime_owner/"
    report: dict[str, Any] = {
        "schema": "apf_reference_runtime_owner/v1",
        "date": "2026-07-11",
        "scope": "read-only static ownership/reachability comparison",
        "source_pins": {
            "apf_xex": {"path": "extracted/All-Pro Football 2K8 (USA)/default.xex",
                        "md5": APF_XEX_MD5, "sha256": APF_XEX_SHA256},
            "nfl_xbe": {"path": "extracted/ESPN NFL 2K5 (USA)/default.xbe",
                        "md5": NFL_XBE_MD5, "sha256": NFL_XBE_SHA256},
            "apf_trace": {"path": canonical +
                          "apf_reference_runtime_owner_trace.txt",
                          "sha256": hashlib.sha256(apf_trace.encode()).hexdigest()},
            "apf_pseudo": {"path": canonical +
                           "apf_reference_runtime_owner_pseudo_c.c",
                           "sha256": hashlib.sha256(apf_pseudo.encode()).hexdigest()},
            "nfl_trace": {"path": canonical +
                          "nfl_reference_runtime_owner_trace.txt",
                          "sha256": hashlib.sha256(nfl_trace.encode()).hexdigest()},
            "nfl_pseudo": {"path": canonical +
                           "nfl_reference_runtime_owner_pseudo_c.c",
                           "sha256": hashlib.sha256(nfl_pseudo.encode()).hexdigest()},
        },
        "apf": {
            "generic_refr_handler": {
                "registered_during_normal_boot": True,
                "boot_route": [
                    "0x84be9e9c -> 0x84b8b1d0",
                    "0x84b8b1e0 -> 0x84691c68",
                    "0x84691cc0 -> 0x84691650",
                    "0x8469170c -> 0x84ab1110 (link 0x84eab870)",
                ],
                "shutdown_route": [
                    "0x84691cdc -> 0x84690fa0",
                    "0x84691114 -> 0x84ab1148 (unlink 0x84eab870)",
                ],
                "type_hash": "0x15578f45",
                "load_callback": "0x84ab10c0",
            },
            "reference_owner_code": {
                "loader": "0x84ab0fa8",
                "loader_static_incoming_refs": 0,
                "loader_only_fullword": "0x844f6828 (.pdata unwind metadata)",
                "accessors": ["0x84ab1028", "0x84ab1040", "0x84ab1058"],
                "accessor_static_incoming_refs": [0, 0, 0],
                "accessor_fullword_occurrences": [0, 0, 0],
                "accessor_address_materializations": [0, 0, 0],
                "inverse_serializer": "0x84ab0e98 (0 incoming refs)",
                "node_constructors": ["0x84ab1090 (0 incoming refs)",
                                      "0x84ab1210 (0 incoming refs)"],
                "loaded_body_global": "0x85234eb0",
                "loaded_body_global_code_accesses": [
                    "0x84ab100c write", "0x84ab1030 read",
                    "0x84ab104c read", "0x84ab1060 read",
                ],
            },
            "serialized_assets": pack_scan,
            "classification": "statically_orphaned_retail_content",
            "conclusion": (
                "APF registers generic REFR format support at boot, but no retail "
                "code or serialized asset owns or requests reference.iff."
            ),
            "boundary": (
                "This exhausts direct calls, stored fullword pointers, ordinary "
                "address materializations, executable literals/hashes, and all four "
                "serialized packs. It is not a proof against deliberately synthesized "
                "runtime addresses or externally injected state."
            ),
        },
        "nfl": nfl,
        "cross_title_result": (
            "NFL 2K5 has a normal Extras -> Reference Guide lifecycle. APF retained "
            "the converted package and generic loader but removed the owner route."
        ),
        "portme": [
            "// PORTME: re-create an APF state descriptor and menu row before treating the retained screen as reachable.",
            "// PORTME: call 0x84AB0FA8-equivalent ownership code and the three bounded REFR accessors in the native port.",
            "// PORTME: preserve the current orphan classification unless a new serialized or runtime owner edge is proved.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("APF_REFERENCE_RUNTIME_OWNER_REPORT_COMPLETE "
          "apf=statically_orphaned nfl=menu_owned packs=4 "
          f"bytes={pack_scan['total_bytes_scanned']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
