#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tmp_root="$(mktemp -d /tmp/vc-cross-title-model-XXXXXX)"
trap 'rm -rf "$tmp_root"' EXIT
mkdir -p "$tmp_root/seed1" "$tmp_root/seed777"

generate() {
  local seed="$1"
  local destination="$2"
  PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED="$seed" \
    python3 tools/cross_title_model_compatibility.py \
      --output "$destination/report.json" \
      --matrix "$destination/matrix.tsv" \
      --bones "$destination/bones.tsv" >/dev/null
}

generate 1 "$tmp_root/seed1"
generate 777 "$tmp_root/seed777"

cmp "$tmp_root/seed1/report.json" "$tmp_root/seed777/report.json"
cmp "$tmp_root/seed1/matrix.tsv" "$tmp_root/seed777/matrix.tsv"
cmp "$tmp_root/seed1/bones.tsv" "$tmp_root/seed777/bones.tsv"

cmp "$tmp_root/seed1/report.json" \
  reports/assets/cross_title_model_compatibility.json
cmp "$tmp_root/seed1/matrix.tsv" \
  reports/assets/cross_title_model_compatibility.tsv
cmp "$tmp_root/seed1/bones.tsv" \
  reports/assets/cross_title_model_bone_candidates.tsv

PYTHONDONTWRITEBYTECODE=1 \
  python3 tools/validate_cross_title_model_compatibility.py
PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest tests/test_cross_title_model_compatibility.py
PYTHONDONTWRITEBYTECODE=1 \
  python3 tools/blender_cross_title_model_compare.py --check

echo "CROSS_TITLE_MODEL_COMPATIBILITY_SUITE_PASS assets=4 matrix=15 bones=124 deterministic=true direct_copy=false writeback=false runtime=false"
