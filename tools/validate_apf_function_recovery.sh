#!/usr/bin/env bash
set -euo pipefail

workspace=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
root=${1:-"$workspace/research/functions/apf2k8"}
manifest="$root/manifest.json"

fail() {
    printf 'APF_VALIDATION_FAIL: %s\n' "$1" >&2
    exit 1
}

[[ -f "$manifest" ]] || fail "missing manifest: $manifest"
jq -e '.complete == true and .program_path == "/default.xex" and
    .executable_md5 == "217eea6084c3d03f0f1143802b1f5636" and
    .function_count == 21347 and .exported_function_count == 21347' \
    "$manifest" >/dev/null || fail "manifest identity or completeness check"

mapfile -t ledger_files < <(jq -r --arg root "$root" '$root + "/" + .ledger_files[]' "$manifest")
mapfile -t pseudo_files < <(jq -r --arg root "$root" '$root + "/" + .pseudo_c_files[]' "$manifest")
[[ ${#ledger_files[@]} -eq 42 ]] || fail "expected 42 ledger shards"
[[ ${#pseudo_files[@]} -eq 84 ]] || fail "expected 84 pseudo-C shards"
for file in "${ledger_files[@]}" "${pseudo_files[@]}"; do
    [[ -f "$file" ]] || fail "manifest names missing shard: $file"
done

jq -e 'has("address") and has("size") and has("body_ranges") and
    has("name") and has("namespace") and has("is_entry") and has("is_pdata") and
    has("is_import") and has("callers") and has("callees") and
    has("direct_string_references") and has("classification") and
    has("classification_evidence") and has("decompile_status") and has("portme") and
    has("pseudo_c_warning_count") and has("hard_pseudo_c_warning_count") and
    (.caller_count == (.callers | length)) and (.callee_count == (.callees | length)) and
    ((.direct_string_references | length) <= 32) and
    (.pseudo_c_warning_count >= .hard_pseudo_c_warning_count) and
    ((.hard_pseudo_c_warning_count == 0) or
        ((.portme | type) == "string" and (.portme | startswith("// PORTME:")))) and
    ((.decompile_status | startswith("success")) or
        ((.portme | type) == "string" and (.portme | startswith("// PORTME:"))))' \
    "${ledger_files[@]}" >/dev/null || fail "ledger schema/count/PORTME invariant"

row_count=$(wc -l "${ledger_files[@]}" | tail -n 1 | awk '{print $1}')
[[ "$row_count" -eq 21347 ]] || fail "ledger row count is $row_count"

unique_addresses=$(jq -r '.address' "${ledger_files[@]}" | sort -u | wc -l)
[[ "$unique_addresses" -eq 21347 ]] || fail "unique ledger address count is $unique_addresses"

read -r first_index last_index unique_indices < <(
    jq -r '.index' "${ledger_files[@]}" | sort -nu |
        awk 'NR == 1 { first = $1 } { last = $1 } END { print first, last, NR }')
[[ "$first_index" -eq 0 && "$last_index" -eq 21346 && "$unique_indices" -eq 21347 ]] ||
    fail "index coverage is first=$first_index last=$last_index unique=$unique_indices"

if ! diff -u \
    <(jq -r '.address' "${ledger_files[@]}" | sort) \
    <(rg --no-filename -o 'APF2K8_FUNCTION 0x[0-9A-F]{8}' "${pseudo_files[@]}" |
        awk '{print $2}' | sort); then
    fail "ledger and pseudo-C address sets differ"
fi

end_markers=$(rg --no-filename -c 'APF2K8_END_FUNCTION 0x[0-9A-F]{8}' "${pseudo_files[@]}" |
    awk -F: '{sum += $NF} END {print sum + 0}')
[[ "$end_markers" -eq 21347 ]] || fail "pseudo-C end marker count is $end_markers"

status_counts=$(jq -s -c -S 'group_by(.decompile_status) |
    map({(.[0].decompile_status): length}) | add' "${ledger_files[@]}")
manifest_status_counts=$(jq -c -S '.decompile_status_counts' "$manifest")
[[ "$status_counts" == "$manifest_status_counts" ]] || fail "status counts disagree with manifest"

classification_counts=$(jq -s -c -S 'group_by(.classification) |
    map({(.[0].classification): length}) | add' "${ledger_files[@]}")
manifest_classification_counts=$(jq -c -S '.classification_counts' "$manifest")
[[ "$classification_counts" == "$manifest_classification_counts" ]] ||
    fail "classification counts disagree with manifest"

for file in "$root/pdata_starts_without_functions.tsv" \
            "$root/import_thunks_without_functions.tsv" \
            "$root/known_warnings.tsv"; do
    awk -F '\t' 'NR > 1 && $NF !~ /^\/\/ PORTME:/ { bad++ }
        END { exit bad != 0 }' "$file" || fail "non-PORTME row in $file"
done

pdata_displaced=$(($(wc -l < "$root/pdata_starts_without_functions.tsv") - 1))
imports_displaced=$(($(wc -l < "$root/import_thunks_without_functions.tsv") - 1))
known_warnings=$(($(wc -l < "$root/known_warnings.tsv") - 1))
[[ "$pdata_displaced" -eq 1389 ]] || fail "displaced pdata count is $pdata_displaced"
[[ "$imports_displaced" -eq 198 ]] || fail "displaced import count is $imports_displaced"
[[ "$known_warnings" -eq 33 ]] || fail "known warning count is $known_warnings"

portme_rows=$(($(wc -l < "$root/portme.tsv") - 1))
manifest_portme=$(jq -r '.portme_count' "$manifest")
[[ "$portme_rows" -eq "$manifest_portme" ]] || fail "PORTME row count disagrees with manifest"

printf '%s\n' \
    'APF_VALIDATION_PASS' \
    "functions=$row_count" \
    "pseudo_c_function_blocks=$end_markers" \
    "ledger_shards=${#ledger_files[@]}" \
    "pseudo_c_shards=${#pseudo_files[@]}" \
    "decompile_status_counts=$status_counts" \
    "classification_counts=$classification_counts" \
    "displaced_pdata=$pdata_displaced" \
    "displaced_import_thunks=$imports_displaced" \
    "known_warnings=$known_warnings" \
    "portme_rows=$portme_rows"
