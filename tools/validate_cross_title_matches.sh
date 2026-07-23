#!/usr/bin/env bash
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"

python3 -m py_compile tools/match_cross_title_functions.py

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

python3 tools/match_cross_title_functions.py \
  --json "$tmp_dir/function_candidates.json" \
  --tsv "$tmp_dir/function_candidates.tsv" >/dev/null

cmp reports/cross_title/function_candidates.json \
    "$tmp_dir/function_candidates.json"
cmp reports/cross_title/function_candidates.tsv \
    "$tmp_dir/function_candidates.tsv"

python3 - "$tmp_dir/function_candidates.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)

assert report["summary"]["candidate_pair_count"] == 1
pair = report["pairs"][0]
assert pair["tier"] == "strong_multi_string"
assert pair["nfl_address"] == "0x000BB8D0"
assert pair["apf_address"] == "0x848A4DB8"
assert pair["shared_strings"] == ["left side", "right side"]
print("CROSS_TITLE_VALIDATION_PASS pairs=1 confirmed_semantic_pairs=1")
PY
