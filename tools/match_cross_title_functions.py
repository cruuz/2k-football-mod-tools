#!/usr/bin/env python3
"""Rank NFL 2K5 x86 and APF 2K8 PPC functions by exact shared strings."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FunctionEvidence:
    address: str
    name: str
    size: int
    caller_count: int
    callee_count: int
    strings: frozenset[str]
    classification: str
    pseudo_c: str


def load_nfl(path: Path) -> list[FunctionEvidence]:
    result: list[FunctionEvidence] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["game_code_candidate"] != "true":
                continue
            strings: set[str] = set()
            for encoded in filter(None, row["cross_title_strings"].split(";")):
                _, separator, value = encoded.partition("=")
                if separator and value:
                    strings.add(value)
            if not strings:
                continue
            result.append(
                FunctionEvidence(
                    address=row["address"],
                    name=row["name"],
                    size=int(row["size"]),
                    caller_count=int(row["caller_count"]),
                    callee_count=int(row["callee_count"]),
                    strings=frozenset(strings),
                    classification=row["classification"],
                    pseudo_c=row["pseudo_c_file"],
                )
            )
    return result


def load_apf(directory: Path) -> list[FunctionEvidence]:
    result: list[FunctionEvidence] = []
    for path in sorted(directory.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["classification"] in ("import", "helper"):
                    continue
                strings = {
                    reference["value"]
                    for reference in row["direct_string_references"]
                    if reference.get("cross_title_exact")
                }
                if not strings:
                    continue
                result.append(
                    FunctionEvidence(
                        address=row["address"],
                        name=row["name"],
                        size=int(row["size"]),
                        caller_count=int(row["caller_count"]),
                        callee_count=int(row["callee_count"]),
                        strings=frozenset(strings),
                        classification=row["classification"],
                        pseudo_c=row["pseudo_c_shard"],
                    )
                )
    return result


def informative(value: str) -> bool:
    return len(value) >= 6 and any(character.isalnum() for character in value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--nfl", type=Path, default=Path("research/functions/nfl2k5/functions.tsv")
    )
    parser.add_argument(
        "--apf-ledger",
        type=Path,
        default=Path("research/functions/apf2k8/ledger"),
    )
    parser.add_argument(
        "--json", type=Path, default=Path("reports/cross_title/function_candidates.json")
    )
    parser.add_argument(
        "--tsv", type=Path, default=Path("reports/cross_title/function_candidates.tsv")
    )
    args = parser.parse_args()

    nfl = load_nfl(args.nfl)
    apf = load_apf(args.apf_ledger)
    nfl_by_string: dict[str, list[FunctionEvidence]] = defaultdict(list)
    apf_by_string: dict[str, list[FunctionEvidence]] = defaultdict(list)
    for function in nfl:
        for value in function.strings:
            nfl_by_string[value].append(function)
    for function in apf:
        for value in function.strings:
            apf_by_string[value].append(function)

    shared_values = sorted(set(nfl_by_string) & set(apf_by_string))
    pair_values: dict[tuple[str, str], set[str]] = defaultdict(set)
    nfl_lookup = {function.address: function for function in nfl}
    apf_lookup = {function.address: function for function in apf}
    for value in shared_values:
        for left in nfl_by_string[value]:
            for right in apf_by_string[value]:
                pair_values[(left.address, right.address)].add(value)

    records: list[dict[str, object]] = []
    for (nfl_address, apf_address), values in pair_values.items():
        left = nfl_lookup[nfl_address]
        right = apf_lookup[apf_address]
        ordered = sorted(values)
        rarity = sum(
            1.0 / (len(nfl_by_string[value]) * len(apf_by_string[value]))
            for value in ordered
        )
        union = left.strings | right.strings
        jaccard = len(values) / len(union)
        degree_difference = abs(left.caller_count - right.caller_count) + abs(
            left.callee_count - right.callee_count
        )
        degree_similarity = 1.0 / (1.0 + degree_difference)
        size_ratio = max(left.size, right.size) / max(1, min(left.size, right.size))
        size_similarity = 1.0 / (1.0 + abs(math.log2(size_ratio)))
        rare_informative = [
            value
            for value in ordered
            if informative(value)
            and len(nfl_by_string[value]) <= 2
            and len(apf_by_string[value]) <= 2
        ]
        if len(ordered) >= 2:
            tier = "strong_multi_string"
        elif rare_informative:
            tier = "strong_rare_string"
        elif any(informative(value) for value in ordered):
            tier = "candidate"
        else:
            tier = "weak_generic"
        score = (
            10.0 * len(ordered)
            + 5.0 * rarity
            + 2.0 * jaccard
            + degree_similarity
            + size_similarity
        )
        records.append(
            {
                "tier": tier,
                "score": round(score, 6),
                "shared_string_count": len(ordered),
                "shared_strings": ordered,
                "rare_informative_strings": rare_informative,
                "rarity": round(rarity, 6),
                "string_jaccard": round(jaccard, 6),
                "degree_similarity": round(degree_similarity, 6),
                "size_similarity": round(size_similarity, 6),
                "nfl_address": left.address,
                "nfl_name": left.name,
                "nfl_size": left.size,
                "nfl_callers": left.caller_count,
                "nfl_callees": left.callee_count,
                "nfl_classification": left.classification,
                "nfl_pseudo_c": left.pseudo_c,
                "apf_address": right.address,
                "apf_name": right.name,
                "apf_size": right.size,
                "apf_callers": right.caller_count,
                "apf_callees": right.callee_count,
                "apf_classification": right.classification,
                "apf_pseudo_c": right.pseudo_c,
                "evidence": (
                    "exact normalized string reference overlap; candidate only, "
                    "not proof of identical function bodies across x86/PPC"
                ),
            }
        )
    tier_order = {
        "strong_multi_string": 0,
        "strong_rare_string": 1,
        "candidate": 2,
        "weak_generic": 3,
    }
    records.sort(
        key=lambda row: (
            tier_order[str(row["tier"])],
            -float(row["score"]),
            str(row["nfl_address"]),
            str(row["apf_address"]),
        )
    )
    tier_counts = Counter(str(record["tier"]) for record in records)
    result = {
        "schema": "vc_cross_title_function_candidates/v1",
        "method": (
            "exact shared normalized string references, then rarity/Jaccard/call-degree/"
            "size ranking; cross-ISA candidates are not byte-identical-body claims"
        ),
        "summary": {
            "nfl_functions_with_exact_shared_strings": len(nfl),
            "apf_functions_with_exact_shared_strings": len(apf),
            "exact_string_values_in_both_function_sets": len(shared_values),
            "candidate_pair_count": len(records),
            "tier_counts": dict(sorted(tier_counts.items())),
        },
        "string_function_frequencies": {
            value: {
                "nfl": len(nfl_by_string[value]),
                "apf": len(apf_by_string[value]),
            }
            for value in shared_values
        },
        "pairs": records,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "tier", "score", "shared_string_count", "shared_strings",
        "rare_informative_strings", "rarity", "string_jaccard",
        "degree_similarity", "size_similarity", "nfl_address", "nfl_name",
        "nfl_size", "nfl_callers", "nfl_callees", "nfl_classification",
        "nfl_pseudo_c", "apf_address", "apf_name", "apf_size", "apf_callers",
        "apf_callees", "apf_classification", "apf_pseudo_c", "evidence",
    ]
    with args.tsv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for record in records:
            flattened = dict(record)
            flattened["shared_strings"] = json.dumps(record["shared_strings"], ensure_ascii=False)
            flattened["rare_informative_strings"] = json.dumps(
                record["rare_informative_strings"], ensure_ascii=False
            )
            writer.writerow(flattened)

    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
