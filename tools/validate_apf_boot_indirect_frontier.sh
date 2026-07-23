#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

tool=tools/apf_boot_indirect_frontier.py
ghidra_script=tools/ghidra_scripts/apf/ApfBootIndirectFrontier.java
report=reports/static_recomp/apf2k8_boot_indirect_frontier.json
ledger=reports/static_recomp/apf2k8_boot_indirect_frontier.tsv
doc=docs/research/apf_boot_indirect_frontier.md

for path in "$tool" "$ghidra_script" "$report" "$ledger" "$doc"; do
  test -f "$path"
done

temporary=$(mktemp -d "${TMPDIR:-/tmp}/apf-boot-indirect-frontier.XXXXXX")
trap 'rm -rf "$temporary"' EXIT

python3 "$tool" \
  --json "$temporary/apf2k8_boot_indirect_frontier.json" \
  --tsv "$temporary/apf2k8_boot_indirect_frontier.tsv"

cmp "$report" "$temporary/apf2k8_boot_indirect_frontier.json"
cmp "$ledger" "$temporary/apf2k8_boot_indirect_frontier.tsv"

python3 - "$report" "$ledger" "$doc" <<'PY'
import csv
import json
from pathlib import Path
import sys

report_path, ledger_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
with ledger_path.open("r", encoding="utf-8", newline="") as stream:
    ledger = list(csv.DictReader(stream, delimiter="\t"))
doc = doc_path.read_text(encoding="utf-8")

assert report["schema"] == "apf2k8_boot_indirect_frontier/v1"
result = report["result"]
assert result == {
    "all_indirect_targets_resolved": False,
    "augmented_callable_imports": 30,
    "augmented_generated_nodes_including_boundaries": 428,
    "augmented_total_nodes": 458,
    "immutable_inputs_unchanged": True,
    "newly_exposed_indirect_sites": 2,
    "original_boundary_stopped_descended_functions": 74,
    "original_indirect_sites_classified": 15,
    "original_indirect_sites_proved_bounded": 10,
    "original_indirect_sites_unresolved": 5,
    "proved_target_references": 254,
    "retail_or_decoded_bytes_embedded": False,
    "successful_boot_path_proved": False,
    "temporary_decoded_bytes_deleted": True,
    "translated_title_code_executed": False,
    "unique_proved_generated_targets": 250,
    "unique_proved_import_targets": 3,
    "unique_proved_targets": 253,
}

expected_sites = [
    "0x84BDAFA0", "0x84BDDF90", "0x84BDE678", "0x84BDE7E4",
    "0x84BDE878", "0x84BDE8AC", "0x84BDEB28", "0x84BDEB60",
    "0x84BEBDEC", "0x84BF0C94", "0x84BF1724", "0x84BF1760",
    "0x84BF17AC", "0x84BF1824", "0x84BF198C",
]
expected_counts = [0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 1, 2, 243, 2, 0]
sites = report["original_indirect_sites"]
assert [row["call_instruction_address"] for row in sites] == expected_sites
assert [row["proved_target_count"] for row in sites] == expected_counts
assert len(ledger) == 15
assert [row["call_instruction_address"] for row in ledger] == expected_sites
assert [int(row["proved_target_count"]) for row in ledger] == expected_counts

resolved = [row for row in sites if row["classification"] == "proved_bounded"]
unresolved = [row for row in sites if row["classification"] == "unresolved_dynamic"]
assert len(resolved) == 10 and len(unresolved) == 5
assert sum(row["proved_target_count"] for row in resolved) == 254
assert all(row["proved_targets"] and row["portme"] is None for row in resolved)
assert all(not row["proved_targets"] and row["portme"].startswith(
    "PORTME at " + row["call_instruction_address"]
) for row in unresolved)
target_rows = [target for row in resolved for target in row["proved_targets"]]
target_symbols = {row["symbol"] for row in target_rows}
assert len(target_rows) == 254 and len(target_symbols) == 253
assert sum(row["classification"] == "generated_implementation"
           for row in {item["symbol"]: item for item in target_rows}.values()) == 250
assert sum(row["classification"] == "callable_import"
           for row in {item["symbol"]: item for item in target_rows}.values()) == 3
assert {row["symbol"] for row in target_rows
        if row["classification"] == "callable_import"} == {
    "__imp__KeTlsFree", "__imp__KeTlsGetValue", "__imp__KeTlsSetValue"
}

cross = report["cross_checks"]
assert cross["decoded_xex_and_ghidra_call_sites_match"] is True
assert cross["decoded_xex_and_ghidra_words_match"] is True
assert cross["generated_mapping_exact_for_every_proved_target"] is True
assert cross["bctrl_opcode"] == "0x4E800421"
assert cross["call_sites_checked"] == 17 and cross["words_checked"] == 261

tables = report["table_evidence"]
assert [(row["site"], row["entry_count"], row["null_entry_count"],
         row["non_null_target_count"]) for row in tables] == [
    ("0x84BF1724", 1, 0, 1),
    ("0x84BF1760", 3, 1, 2),
    ("0x84BF17AC", 244, 1, 243),
    ("0x84BF1824", 3, 1, 2),
]

augmented = report["augmented_frontier"]
for key, value in {
    "generated_nodes_including_opaque_boundaries": 428,
    "opaque_boundary_nodes": 2,
    "descended_generated_nodes": 426,
    "callable_import_nodes": 30,
    "total_nodes_including_imports": 458,
    "new_generated_nodes": 352,
    "new_callable_imports": 3,
    "direct_call_sites_from_descended_nodes": 1484,
    "unique_direct_edges_from_descended_nodes": 796,
    "unique_generated_direct_edges": 721,
    "unique_callable_import_direct_edges": 75,
    "callable_import_direct_call_sites": 87,
    "proved_indirect_caller_target_edges": 254,
    "syntactic_indirect_sites_in_descended_nodes": 17,
    "descended_nodes_with_indirect_dispatch": 13,
}.items():
    assert augmented[key] == value, (key, augmented[key])
assert augmented["new_callable_import_symbols"] == [
    "__imp__ExCreateThread", "__imp__KeBugCheck", "__imp__RtlInitAnsiString"
]
new_sites = augmented["newly_exposed_indirect_sites"]
assert [row["call_instruction_address"] for row in new_sites] == [
    "0x8468CF4C", "0x84BDAA00"
]
assert all(row["portme"].startswith(
    "PORTME at " + row["call_instruction_address"]
) for row in new_sites)

portmes = report["portme"]
for address in expected_sites[:2] + expected_sites[8:10] + [expected_sites[-1]] + [
    "0x8468CF4C", "0x84BDAA00"
]:
    assert sum(text.startswith("PORTME at " + address) for text in portmes) == 1

assert report["inputs"]["retail_xex"]["sha256"] == (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
assert report["inputs"]["decoded_image"]["preserved_after_run"] is False
assert report["inputs"]["ghidra_script"]["project_opened_read_only"] is True
assert report["inputs"]["xenonrecomp_vendor"]["tracked_diff_empty"] is True

for heading in (
    "## Result", "## Exact method", "## The original 15 sites",
    "## Augmented frontier", "## Worked", "## Failed or unproved",
    "## Blocking", "## Integration text", "## Validation",
):
    assert heading in doc
compact = " ".join(doc.split())
for phrase in (
    "Ten sites have entry-context target proofs and five remain deliberately unresolved",
    "from 103 nodes to 458 nodes",
    "254 caller/target edges",
    "250 generated implementations and three callable XDK imports",
    "This is not yet a boot proof",
    "APF_BOOT_INDIRECT_FRONTIER_VALIDATION_PASS",
):
    assert phrase in compact, phrase
for address in [
    "0x84BDAFA0", "0x84BDDF90", "0x84BEBDEC", "0x84BF0C94",
    "0x84BF198C", "0x8468CF4C", "0x84BDAA00",
]:
    assert "// PORTME at " + address in doc
PY

test "$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/default.xex' | cut -d' ' -f1)" = \
  981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f
test "$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/0A' | cut -d' ' -f1)" = \
  dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e
test "$(git -C tools/vendor/XenonRecomp rev-parse HEAD)" = \
  ddd128bcca99fe8bfbb99bea583c972351fa6ace
git -C tools/vendor/XenonRecomp diff --quiet

echo "APF_BOOT_INDIRECT_FRONTIER_VALIDATION_PASS original_sites=15 proved=10 unresolved=5 target_edges=254 unique_targets=253 augmented_nodes=458 imports=30 newly_exposed=2"
