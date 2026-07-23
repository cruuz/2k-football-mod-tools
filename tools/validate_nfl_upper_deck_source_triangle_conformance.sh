#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_nfl_upper_deck_source_triangle_conform >/dev/null

summary4="$({
  PYTHONDONTWRITEBYTECODE=1 python3 \
    tools/nfl_upper_deck_source_triangle_conform.py \
    --input reports/asset_samples/nfl_scne/stadium_upper_deck_nonidentity4_source_triangle_mesh.v1.json \
    --output "$temporary/recipe4.json"
})"

test "$summary4" = '{"attribute_policy":"copy_complete_source_records","contains_retail_geometry":false,"edited_gltf_import_proved":false,"input_sha256":"d5648c12e168d616934946cf12fcf6ab7b8b22010079ecfd8ab1faaadaf5df7e","native_quad_count":1,"new_vertex_count":4,"oriented_triangle_multiset_preserved":true,"output_recipe_schema":"nfl2k5_upper_deck_source_subset_recipe/v1","output_recipe_sha256":"546700178dfd2bf116beaa9bcd534c4be38a0b2f2d450590c809d605b428b311","runtime_visibility_proved":false,"schema":"nfl2k5_upper_deck_source_triangle_conformance/v1","target_id":"nfl2k5/stadium/o3280/c5/s1"}'

cmp -s \
  "$temporary/recipe4.json" \
  reports/asset_samples/nfl_scne/stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json

PYTHONDONTWRITEBYTECODE=1 python3 \
  tools/nfl_upper_deck_source_triangle_conform.py \
  --input reports/asset_samples/nfl_scne/stadium_upper_deck_prefix8_source_triangle_mesh.v1.json \
  > "$temporary/recipe8.json"

cmp -s \
  "$temporary/recipe8.json" \
  reports/asset_samples/nfl_scne/stadium_upper_deck_prefix8_source_subset_recipe.v1.json

echo "NFL_UPPER_DECK_SOURCE_TRIANGLE_CONFORMANCE_PASS tests=12 target=upper_deck input=TRIANGLES source_ids=0..11 native=QUADS counts=4,8 exact_recipes=true external_values=false edited_gltf=false runtime=false"
