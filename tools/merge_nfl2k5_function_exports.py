#!/usr/bin/env python3
"""Validate and merge NFL 2K5 Ghidra function-export shards."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


SHARD_RE = re.compile(r"shard_(\d{6})_(\d{6})\.tsv$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--xbsdb", type=Path, required=True)
    args = parser.parse_args()

    root = args.root
    ledger_dir = root / "ledger_shards"
    pseudo_dir = root / "pseudo_c"
    manifest_dir = root / "manifests"
    shards: list[tuple[int, int, Path]] = []
    for path in ledger_dir.glob("shard_*.tsv"):
        match = SHARD_RE.fullmatch(path.name)
        if match:
            shards.append((int(match.group(1)), int(match.group(2)), path))
    shards.sort()
    if not shards:
        raise SystemExit("no NFL ledger shards found")

    xbsdb_count = sum(1 for line in args.xbsdb.read_text(encoding="utf-8").splitlines() if line.strip())
    if xbsdb_count != 651:
        raise SystemExit(f"expected 651 XbSymbolDatabase candidates, found {xbsdb_count}")

    expected_index = 0
    expected_total: int | None = None
    header: list[str] | None = None
    raw_header: str | None = None
    output_lines: list[str] = []
    status_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    section_counts: Counter[str] = Counter()
    sdk_status_counts: Counter[str] = Counter()
    portme_rows: list[dict[str, str]] = []
    xbsdb_function_rows = 0
    xtlid_function_rows = 0
    game_candidate_rows = 0
    external_rows = 0
    thunk_rows = 0
    kernel_import_caller_rows = 0
    direct_string_rows = 0
    cross_title_string_rows = 0

    for start, last, path in shards:
        if start != expected_index:
            raise SystemExit(f"ledger gap/overlap: expected index {expected_index}, got shard {start}..{last}")
        manifest_path = manifest_dir / path.with_suffix(".json").name
        if not manifest_path.is_file():
            raise SystemExit(f"missing manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["start_index"] != start or manifest["end_index_exclusive"] != last + 1:
            raise SystemExit(f"manifest range mismatch: {manifest_path}")
        total = int(manifest["total_recovered_functions"])
        if expected_total is None:
            expected_total = total
        elif expected_total != total:
            raise SystemExit(f"inconsistent total function counts: {expected_total} vs {total}")
        pseudo_path = root / manifest["pseudo_c"]
        if not pseudo_path.is_file():
            raise SystemExit(f"missing pseudo-C shard: {pseudo_path}")

        raw_lines = path.read_text(encoding="utf-8", errors="strict").splitlines(keepends=True)
        if not raw_lines:
            raise SystemExit(f"empty shard: {path}")
        if raw_header is None:
            raw_header = raw_lines[0]
        elif raw_lines[0] != raw_header:
            raise SystemExit(f"header mismatch: {path}")
        output_lines.extend(raw_lines[1:])

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if header is None:
                header = reader.fieldnames
            elif reader.fieldnames != header:
                raise SystemExit(f"parsed header mismatch: {path}")
            row_count = 0
            for row in reader:
                index = int(row["index"])
                if index != expected_index:
                    raise SystemExit(f"row index mismatch: expected {expected_index}, got {index} in {path}")
                expected_index += 1
                row_count += 1
                status_counts[row["decompile_status"]] += 1
                class_counts[row["classification"]] += 1
                section_counts[row["section"]] += 1
                sdk_status_counts[row["sdk_status"]] += 1
                xbsdb_function_rows += row["xbsdb_signature"] == "true"
                xtlid_function_rows += row["xtlid_target"] == "true"
                game_candidate_rows += row["game_code_candidate"] == "true"
                external_rows += row["external"] == "true"
                thunk_rows += row["thunk"] == "true"
                kernel_import_caller_rows += bool(row["kernel_imports_called"])
                direct_string_rows += int(row["direct_string_ref_count"]) > 0
                cross_title_string_rows += int(row["cross_title_string_ref_count"]) > 0
                if row["decompile_status"] not in {"success", "not_applicable_external"}:
                    if not row["portme"].startswith("PORTME:"):
                        raise SystemExit(f"missing PORTME text at function index {index}")
                    portme_rows.append(row)
            if row_count != last - start + 1:
                raise SystemExit(f"row count mismatch in {path}: {row_count}")

    if expected_total is None or expected_index != expected_total:
        raise SystemExit(f"incomplete export: recovered {expected_index} of {expected_total}")

    merged = root / "functions.tsv"
    with merged.open("w", encoding="utf-8", newline="") as handle:
        assert raw_header is not None
        handle.write(raw_header)
        handle.writelines(output_lines)

    portme_path = root / "portme.tsv"
    with portme_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["index", "address", "name", "section", "decompile_status", "portme", "pseudo_c_file"])
        for row in portme_rows:
            writer.writerow([
                row["index"], row["address"], row["name"], row["section"],
                row["decompile_status"], row["portme"], row["pseudo_c_file"],
            ])

    summary = {
        "program": "ESPN NFL 2K5 (USA)/default.xbe",
        "program_md5": "444064a9ec984dd29d2c05a43f5c96e8",
        "total_recovered_functions": expected_total,
        "ledger_shard_count": len(shards),
        "pseudo_c_shard_count": len(shards),
        "xbsdb_input_candidate_count": xbsdb_count,
        "xbsdb_candidate_function_entry_rows": xbsdb_function_rows,
        "xtlid_target_function_rows": xtlid_function_rows,
        "sdk_status_counts": dict(sorted(sdk_status_counts.items())),
        "game_or_engine_candidate_rows": game_candidate_rows,
        "external_function_rows": external_rows,
        "internal_function_rows": expected_total - external_rows,
        "automated_pseudo_c_rows": status_counts["success"],
        "manual_pseudo_c_rows": status_counts["manual_recovery_from_disassembly"],
        "pseudo_c_body_rows": (
            status_counts["success"]
            + status_counts["manual_recovery_from_disassembly"]
        ),
        "unrecovered_internal_function_rows": (
            expected_total
            - external_rows
            - status_counts["success"]
            - status_counts["manual_recovery_from_disassembly"]
        ),
        "thunk_function_rows": thunk_rows,
        "functions_calling_kernel_imports": kernel_import_caller_rows,
        "functions_with_direct_string_refs": direct_string_rows,
        "functions_with_cross_title_string_refs": cross_title_string_rows,
        "decompile_status_counts": dict(sorted(status_counts.items())),
        "classification_counts": dict(sorted(class_counts.items())),
        "section_counts": dict(sorted(section_counts.items())),
        "portme_count": len(portme_rows),
        "complete_index_range": [0, expected_total - 1],
        "ledger": "functions.tsv",
        "portme_ledger": "portme.tsv",
    }
    (root / "export_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"NFL2K5_MERGE_COMPLETE rows={expected_total} shards={len(shards)} "
        f"success={status_counts['success']} "
        f"manual={status_counts['manual_recovery_from_disassembly']} "
        f"portme={len(portme_rows)} external={external_rows}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
