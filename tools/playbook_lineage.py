#!/usr/bin/env python3
"""Prove the NFL/APF PLAY assignment-descriptor packing relationship.

This consumes the exhaustive playbook inventory rather than reparsing game
archives.  It validates a reversible bit/byte permutation over every observed
descriptor, then uses same-named plays only as a semantic corroboration layer.
Unknown descriptor meanings and route-chain opcodes remain unknown.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path


SCHEMA = "vc_cross_title_playbook_descriptor_lineage/v1"


class LineageError(ValueError):
    """The canonical report violates the proved descriptor relationship."""


def word(value: str) -> int:
    return int(value, 16)


def apf_to_nfl(value: int) -> int:
    """Convert the observed APF packed descriptor into NFL numeric layout."""
    byte_0 = (value >> 24) & 0xFF
    byte_1 = (value >> 16) & 0xFF
    byte_2 = (value >> 8) & 0xFF
    byte_3 = value & 0xFF
    if byte_3 != 0 or byte_2 not in (0xB0, 0xB4, 0xB8, 0xBC):
        raise LineageError(f"unsupported APF descriptor 0x{value:08x}")
    nibble_swapped_0 = ((byte_0 & 0x0F) << 4) | (byte_0 >> 4)
    return (
        ((1 if byte_2 & 0x04 else 0) << 24)
        | ((0xB0 | (1 if byte_2 & 0x08 else 0)) << 16)
        | (byte_1 << 8)
        | nibble_swapped_0
    )


def nfl_to_apf(value: int) -> int:
    """Inverse conversion for every descriptor layout observed in NFL 2K5."""
    byte_0 = (value >> 24) & 0xFF
    byte_1 = (value >> 16) & 0xFF
    byte_2 = (value >> 8) & 0xFF
    byte_3 = value & 0xFF
    if byte_0 not in (0, 1) or byte_1 not in (0xB0, 0xB1):
        raise LineageError(f"unsupported NFL descriptor 0x{value:08x}")
    nibble_swapped_3 = ((byte_3 & 0x0F) << 4) | (byte_3 >> 4)
    apf_byte_2 = 0xB0 | ((byte_1 & 1) << 3) | (byte_0 << 2)
    return (nibble_swapped_3 << 24) | (byte_2 << 16) | (apf_byte_2 << 8)


def descriptor_signature(play: dict[str, object]) -> tuple[int, ...]:
    slots = play["slots"]
    assert isinstance(slots, list)
    if len(slots) != 11:
        raise LineageError("play does not have exactly eleven assignment slots")
    return tuple(word(str(slot["descriptor_word"])) for slot in slots)


def first_node_signature(
    book: dict[str, object], play: dict[str, object]
) -> tuple[tuple[str, int], ...]:
    blob = bytes.fromhex(str(book["route_node_blob_hex"]))
    endian = ">" if book["platform"] == "apf2k8" else "<"
    result: list[tuple[str, int]] = []
    for slot in play["slots"]:
        index = int(slot["route_node_index"])
        offset = index * 8
        node = blob[offset : offset + 8]
        if len(node) != 8:
            raise LineageError(f"route node {index} is outside retained blob")
        # The leading four bytes are packed byte fields and compare literally;
        # the following word is platform-endian and compares numerically.
        result.append((node[:4].hex(), struct.unpack(endian + "I", node[4:])[0]))
    return tuple(result)


def hex_signature(values: tuple[int, ...]) -> list[str]:
    return [f"0x{value:08x}" for value in values]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("reports/assets/cross_title_playbook_inventory.json"),
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    source = json.loads(args.inventory.read_text(encoding="utf-8"))
    if source.get("schema") != "vc_cross_title_playbook_inventory/v1":
        raise LineageError("unsupported playbook inventory schema")
    books = source["playbooks"]
    apf_books = [book for book in books if book["platform"] == "apf2k8"]
    nfl_books = [book for book in books if book["platform"] == "nfl2k5"]
    if len(apf_books) != 1 or len(nfl_books) != 37:
        raise LineageError("expected one APF and 37 NFL playbooks")
    apf_book = apf_books[0]

    apf_counts: Counter[int] = Counter()
    nfl_counts: Counter[int] = Counter()
    for book in apf_books:
        for play in book["plays"]:
            apf_counts.update(descriptor_signature(play))
    for book in nfl_books:
        for play in book["plays"]:
            nfl_counts.update(descriptor_signature(play))

    for value in apf_counts:
        if nfl_to_apf(apf_to_nfl(value)) != value:
            raise LineageError(f"APF descriptor does not round-trip: 0x{value:08x}")
    for value in nfl_counts:
        if apf_to_nfl(nfl_to_apf(value)) != value:
            raise LineageError(f"NFL descriptor does not round-trip: 0x{value:08x}")

    mapping = []
    for value in sorted(apf_counts):
        converted = apf_to_nfl(value)
        mapping.append(
            {
                "apf_descriptor": f"0x{value:08x}",
                "nfl_descriptor": f"0x{converted:08x}",
                "apf_occurrences": apf_counts[value],
                "nfl_occurrences": nfl_counts.get(converted, 0),
                "observed_in_both": converted in nfl_counts,
            }
        )

    nfl_by_name: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
    for book in nfl_books:
        for play in book["plays"]:
            nfl_by_name[str(play["name"]).casefold()].append((book, play))

    matches: list[dict[str, object]] = []
    for apf_play in apf_book["plays"]:
        converted = tuple(apf_to_nfl(value) for value in descriptor_signature(apf_play))
        candidates = [
            (book, play)
            for book, play in nfl_by_name.get(str(apf_play["name"]).casefold(), [])
            if descriptor_signature(play) == converted
        ]
        if not candidates:
            continue
        apf_nodes = first_node_signature(apf_book, apf_play)
        node_candidates = [
            (book, play)
            for book, play in candidates
            if first_node_signature(book, play) == apf_nodes
        ]
        candidates.sort(key=lambda item: (int(item[0]["outer_index"]), int(item[1]["index"])))
        node_candidates.sort(
            key=lambda item: (int(item[0]["outer_index"]), int(item[1]["index"]))
        )
        representative_book, representative_play = (
            node_candidates[0] if node_candidates else candidates[0]
        )
        matches.append(
            {
                "name": apf_play["name"],
                "casefolded_name": str(apf_play["name"]).casefold(),
                "apf_play_index": apf_play["index"],
                "apf_flags_or_id_04": apf_play["flags_or_id_04"],
                "nfl_descriptor_match_count": len(candidates),
                "nfl_first_node_match_count": len(node_candidates),
                "all_eleven_first_nodes_match": bool(node_candidates),
                "representative_nfl_outer_index": representative_book["outer_index"],
                "representative_nfl_book": representative_book["book_name"],
                "representative_nfl_play_index": representative_play["index"],
                "representative_nfl_flags_or_id_04": representative_play["flags_or_id_04"],
                "converted_descriptor_signature": hex_signature(converted),
                "first_node_signature": [
                    {"packed_prefix_hex": prefix, "endian_word": f"0x{tail:08x}"}
                    for prefix, tail in apf_nodes
                ],
                "matching_nfl_books": sorted(
                    {str(book["book_name"]) for book, _ in candidates}
                ),
                "first_node_matching_nfl_books": sorted(
                    {str(book["book_name"]) for book, _ in node_candidates}
                ),
            }
        )

    descriptor_names = {str(row["casefolded_name"]) for row in matches}
    node_names = {
        str(row["casefolded_name"])
        for row in matches
        if row["all_eleven_first_nodes_match"]
    }
    shared_mapped_values = sum(bool(row["observed_in_both"]) for row in mapping)
    report = {
        "schema": SCHEMA,
        "source": {
            "inventory": str(args.inventory),
            "sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        },
        "descriptor_conversion": {
            "apf_constraints": "bytes [A,B,C,00], C in {b0,b4,b8,bc}",
            "nfl_constraints": "numeric bytes [H,L,B,nibble_swap(A)], H in {0,1}, L in {b0,b1}",
            "formula": (
                "H=(C&0x04)!=0; L=0xb0|((C&0x08)!=0); "
                "NFL=(H<<24)|(L<<16)|(B<<8)|nibble_swap(A)"
            ),
            "inverse_is_exact_for_every_observed_descriptor": True,
        },
        "summary": {
            "apf_descriptor_occurrence_count": sum(apf_counts.values()),
            "nfl_descriptor_occurrence_count": sum(nfl_counts.values()),
            "apf_unique_descriptor_count": len(apf_counts),
            "nfl_unique_descriptor_count": len(nfl_counts),
            "mapped_unique_descriptors_observed_in_both": shared_mapped_values,
            "apf_play_occurrences_with_same_name_and_exact_converted_eleven_descriptor_signature": len(matches),
            "distinct_names_with_exact_converted_eleven_descriptor_signature": len(descriptor_names),
            "apf_play_occurrences_with_all_eleven_first_nodes_matching": sum(
                bool(row["all_eleven_first_nodes_match"]) for row in matches
            ),
            "distinct_names_with_all_eleven_first_nodes_matching": len(node_names),
            "descriptor_conversion_roundtrip_complete": True,
        },
        "portme": [
            "PORTME: assign semantic bit names to the reversible descriptor fields through executable consumers.",
            "PORTME: decode route-node opcode, link, termination, coordinate, and branching semantics.",
            "PORTME: compare complete node chains only after chain boundaries are executable-proven.",
            "PORTME: same names and signatures do not authorize blind record replacement or archive writing.",
        ],
        "unique_apf_to_nfl_descriptor_mapping": mapping,
        "same_name_exact_signature_matches": matches,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fields = [
        "name", "apf_play_index", "nfl_descriptor_match_count",
        "nfl_first_node_match_count", "all_eleven_first_nodes_match",
        "representative_nfl_outer_index", "representative_nfl_book",
        "representative_nfl_play_index", "converted_descriptor_signature",
        "matching_nfl_books", "first_node_matching_nfl_books",
    ]
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fields,
            dialect="excel-tab",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in matches:
            writer.writerow(
                {
                    **row,
                    "converted_descriptor_signature": ",".join(
                        row["converted_descriptor_signature"]
                    ),
                    "matching_nfl_books": ",".join(row["matching_nfl_books"]),
                    "first_node_matching_nfl_books": ",".join(
                        row["first_node_matching_nfl_books"]
                    ),
                }
            )
    print(
        "PLAYBOOK_LINEAGE_COMPLETE "
        f"descriptors={len(apf_counts)}/{len(nfl_counts)}/{shared_mapped_values} "
        f"plays={len(matches)}/{len(descriptor_names)} "
        f"nodes={sum(bool(row['all_eleven_first_nodes_match']) for row in matches)}/{len(node_names)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, LineageError, KeyError, ValueError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
