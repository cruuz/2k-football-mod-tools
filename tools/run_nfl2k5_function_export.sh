#!/usr/bin/env bash
set -euo pipefail

workspace="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$workspace"

total="${1:-20131}"
shard_size="${2:-512}"
timeout_seconds="${3:-5}"
output_root="research/functions/nfl2k5"
ghidra="tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless"
config_root="/tmp/codex-ghidra-nfl2k5-export-config"

mkdir -p "$config_root" "$output_root/ledger_shards" "$output_root/pseudo_c" "$output_root/manifests"

start=0
while (( start < total )); do
    end=$((start + shard_size))
    if (( end > total )); then
        end="$total"
    fi
    last=$((end - 1))
    manifest=$(printf '%s/manifests/shard_%06d_%06d.json' "$output_root" "$start" "$last")
    if [[ -f "$manifest" ]]; then
        printf 'NFL2K5_EXPORT_SKIP existing=%s\n' "$manifest"
    else
        env \
            XDG_CONFIG_HOME="$config_root" \
            JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
            "$ghidra" ghidra_projects nfl2k5 \
            -process default.xbe \
            -noanalysis \
            -readOnly \
            -scriptPath tools/ghidra_scripts \
            -postScript Nfl2k5FunctionExport.java \
                "$output_root" \
                reports/headers/nfl2k5_xbsdb_symbols.txt \
                reports/cross_title/common_strings.tsv \
                "$start" "$end" "$timeout_seconds"
    fi
    start="$end"
done

python3 tools/merge_nfl2k5_function_exports.py \
    "$output_root" \
    --xbsdb reports/headers/nfl2k5_xbsdb_symbols.txt
