#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

spec=reports/specs/apf2k8_scne_draw_topology.v1.json
corpus=reports/assets/apf_scne_draw_topology_corpus.v1.json
roundtrip=reports/assets/apf_stadium_node17_same_footprint_topology_roundtrip.json
changed_verify=reports/assets/apf_stadium_node17_same_footprint_topology_verification.json
noop_verify=reports/assets/apf_stadium_node17_same_footprint_topology_noop_verification.json
sample=reports/asset_samples/apf_scene/stadium_node17_nonretail_permuted_strip_recipe.json

for required in \
  tools/apf_scne_draw_topology_spec.py \
  tools/apf_stadium_node17_topology_patch.py \
  tools/apf_stadium_node17_topology_verify.py \
  tools/apf_stadium_node17_topology_proof.py \
  tools/apf_stadium_node17_topology_proof_recipes.py \
  tests/test_apf_stadium_node17_topology_patch.py \
  reports/specs/apf2k8_scne_same_footprint_topology_recipe.schema.json \
  "$sample" "$spec" "$corpus" "$roundtrip" "$changed_verify" "$noop_verify" \
  docs/research/apf_scne_draw_topology_writeback.md; do
  test -f "$required"
done

python3 -m py_compile \
  tools/apf_scne_draw_topology_spec.py \
  tools/apf_stadium_node17_topology_patch.py \
  tools/apf_stadium_node17_topology_verify.py \
  tools/apf_stadium_node17_topology_proof.py \
  tools/apf_stadium_node17_topology_proof_recipes.py
bash -n "$0"

temporary=$(mktemp -d /tmp/apf-node17-topology.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONHASHSEED=1 python3 tools/apf_scne_draw_topology_spec.py --spec-output "$temporary/spec-one.json"
PYTHONHASHSEED=777 python3 tools/apf_scne_draw_topology_spec.py --spec-output "$temporary/spec-two.json"
cmp "$temporary/spec-one.json" "$temporary/spec-two.json"
cmp "$temporary/spec-one.json" "$spec"
python3 -m unittest tests.test_apf_stadium_node17_topology_patch

python3 - "$spec" "$corpus" "$roundtrip" "$changed_verify" "$noop_verify" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

spec_path, corpus_path, report_path, changed_path, noop_path = map(Path, sys.argv[1:])
spec = json.loads(spec_path.read_text())
corpus = json.loads(corpus_path.read_text())
report = json.loads(report_path.read_text())
changed = json.loads(changed_path.read_text())
noop = json.loads(noop_path.read_text())

assert spec["schema"] == "apf2k8_scne_draw_topology/v1"
assert corpus["schema"] == "apf2k8_scne_draw_topology_corpus/v1"
assert report["schema"] == "apf2k8_scne_same_footprint_topology_roundtrip/v1"
assert corpus["coverage"] == {
    "decoded_block_bytes": 819738940,
    "decoded_unique_blocks": 783,
    "draw_records": 47112,
    "index_width_nodes": {"16": 13003, "32": 3},
    "mesh_nodes": 13006,
    "partitioned_nodes": 13006,
    "scne_resources": 1303,
    "serialized_indices": 24519417,
}
assert all(corpus["proved_invariants"].values())
assert spec["claim_flags"]["node17_writer_implemented"] is True
assert spec["claim_flags"]["node17_independent_offline_verifier_proved"] is True
assert spec["claim_flags"]["runtime_proved"] is False
assert spec["claim_flags"]["hardware_proved"] is False
assert report["no_op"]["complete_1a_byte_identical"] is True
assert report["no_op"]["h7a_recompressed"] is False
assert report["changed_nonretail_permutation"]["changed_decoded_dram_bytes"] == 2
assert report["changed_nonretail_permutation"]["authorized_decoded_bytes"] == 8
assert report["changed_nonretail_permutation"]["native_triangle_count"] == 2
assert report["changed_nonretail_permutation"]["native_degenerate_triangle_count"] == 0
assert report["changed_nonretail_permutation"]["allocation_slack_after_bytes"] == 1403
assert all(changed["checks"].values()) and all(noop["checks"].values())
assert changed["claims"]["emulator_runtime_visibility_proved"] is False
assert noop["claims"]["xbox_360_hardware_proved"] is False
for document in (spec, corpus, report, changed, noop):
    assert document == json.loads(json.dumps(document))
for policy in (spec["data_policy"], corpus["data_policy"], report["data_policy"]):
    assert policy["contains_retail_vertex_coordinates"] is False
    assert policy["contains_retail_index_sequences"] is False

print("APF_NODE17_TOPOLOGY_PINNED_ARTIFACTS_PASS")
PY

if [[ ${APF_SCNE_DRAW_TOPOLOGY_FULL:-0} == 1 ]]; then
  python3 tools/apf_scne_draw_topology_spec.py \
    --full \
    --corpus-output "$temporary/full-corpus.json" \
    --spec-output "$temporary/full-spec.json"
  cmp "$temporary/full-corpus.json" "$corpus"
  cmp "$temporary/full-spec.json" "$spec"
fi

if [[ ${APF_NODE17_TOPOLOGY_FULL:-0} == 1 ]]; then
  game=extracted/'All-Pro Football 2K8 (USA)'
  python3 tools/apf_stadium_node17_topology_proof_recipes.py \
    --game-dir "$game" \
    --noop-output "$temporary/noop.recipe.json" \
    --changed-output "$temporary/changed.recipe.json"
  cmp "$temporary/changed.recipe.json" "$sample"
  python3 tools/apf_stadium_node17_topology_patch.py \
    --game-dir "$game" --recipe "$temporary/noop.recipe.json" \
    --output-dir "$temporary/noop-output"
  python3 tools/apf_stadium_node17_topology_patch.py \
    --game-dir "$game" --recipe "$temporary/changed.recipe.json" \
    --output-dir "$temporary/changed-output"
  python3 tools/apf_stadium_node17_topology_verify.py \
    --game-dir "$game" --recipe "$temporary/noop.recipe.json" \
    --output-dir "$temporary/noop-output" \
    --verification-out "$temporary/noop.verify.json"
  python3 tools/apf_stadium_node17_topology_verify.py \
    --game-dir "$game" --recipe "$temporary/changed.recipe.json" \
    --output-dir "$temporary/changed-output" \
    --verification-out "$temporary/changed.verify.json"
  cmp "$temporary/noop.verify.json" "$noop_verify"
  cmp "$temporary/changed.verify.json" "$changed_verify"
fi

report_sha=$(sha256sum "$roundtrip" | awk '{print $1}')
printf '%s\n' \
  "APF_SCNE_NODE17_TOPOLOGY_VALIDATION_PASS schema=v1 scne=1303 nodes=13006 draws=47112 indices=24519417 changed_decoded=2 authorized=8 triangles=2 degenerates=0 slack=1403 noop_exact=true noop_recompress=false independent_verify=true runtime=false hardware=false production=false report_sha256=$report_sha"
