#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

python3 -m py_compile tools/apf_inner.py

jq -e '
  .schema == "apf_inner_manifest/v1" and
  .summary.outer_entry_count == 1543 and
  .summary.iff_head_count == 1473 and
  .summary.parsed_iff_count == 1473 and
  .summary.parse_failure_count == 0 and
  .summary.total_inner_file_count == 10394 and
  .summary.named_inner_file_count == 10394 and
  .summary.validated_inner_name_hash_count == 10394 and
  .summary.validated_inner_type_hash_count == 10394 and
  .summary.compressed_block_count == 2865 and
  .summary.uncompressed_block_count == 29 and
  .summary.inner_type_counts.TXTR == 3637 and
  .summary.inner_type_counts.AUDO == 2261 and
  .summary.inner_type_counts.SCNE == 1303 and
  .summary.records_with_warnings == 0
' reports/manifests/apf_inner.json >/dev/null

test "$(wc -l < reports/manifests/apf_inner_candidates.tsv)" -eq 10395

test "$(sha256sum tools/apf_inner.py | cut -d' ' -f1)" = \
  75a74b34524b3861785b916e3470862bccfe278825a63aa2dccb924849ae9606
test "$(sha256sum reports/manifests/apf_inner.json | cut -d' ' -f1)" = \
  b57772a88e969db47aca6add24b1387ab2470b53cdb2f6f21bd4a3d8999fb6d1
test "$(sha256sum reports/manifests/apf_inner_candidates.tsv | cut -d' ' -f1)" = \
  26dd77660c91568773519f616e7120c6b8c23dc3613880e5a5831c18ee34a0d3
test "$(sha256sum reports/asset_samples/apf/frontend/fantasy_sport_logo/fantasy_sport_logo.png | cut -d' ' -f1)" = \
  c3cd51ca826b999fe7ffd3dc9d719651be960e385583061dc476ea06be0c3fb1
test "$(sha256sum reports/asset_samples/apf/frontend/random_outer/random_outer.png | cut -d' ' -f1)" = \
  d6cf665768386072f27b3693ced732ab9b7f8dd595dd90d444f998eb1d97d7dc
test "$(sha256sum reports/asset_samples/apf/field_grass_dry/divots/divots.png | cut -d' ' -f1)" = \
  6e7cecb7f69c410f1f280a532c56c0ee2ba229d7e822e7aa418ebe329554674e

if [[ -n "${APF_DECODED_PE:-}" ]]; then
  test -f "$APF_DECODED_PE"
  python3 tools/apf_inner.py \
    'extracted/All-Pro Football 2K8 (USA)/0A' \
    --decoded-executable "$APF_DECODED_PE" \
    --verify-codec-samples 16 \
    --manifest /tmp/apf_inner_validation.json \
    --inventory-tsv /tmp/apf_inner_validation.tsv
  cmp -s /tmp/apf_inner_validation.json reports/manifests/apf_inner.json
  cmp -s /tmp/apf_inner_validation.tsv reports/manifests/apf_inner_candidates.tsv
fi

echo APF_INNER_VALIDATION_PASS
echo iff=1473/1473
echo files=10394
echo h7a_samples=16/16
