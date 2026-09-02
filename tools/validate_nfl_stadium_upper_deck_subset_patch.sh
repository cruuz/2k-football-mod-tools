#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
pack='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'
catalog='reports/specs/nfl2k5_stadium_static_target_catalog.v1.json'
boundary='reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json'
recipe_schema='reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json'
prefix8='reports/asset_samples/nfl_scne/stadium_upper_deck_prefix8_source_subset_recipe.v1.json'
nonidentity4='reports/asset_samples/nfl_scne/stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json'
closure='reports/specs/nfl2k5_upper_deck_source_subset_writeback_closure.v1.json'
roundtrip='reports/assets/nfl_stadium_upper_deck_source_subset_roundtrip.v1.json'
doc='docs/research/nfl_upper_deck_source_subset_writeback.md'
temporary=$(mktemp -d "$root/.nfl-upper-deck-subset-validate.XXXXXX")
trap 'rm -rf "$temporary"' EXIT

for required in "$index" "$pack" "$catalog" "$boundary" "$recipe_schema" \
  "$prefix8" "$nonidentity4" "$closure" "$roundtrip" "$doc" \
  tools/nfl_stadium_upper_deck_subset_patch.py \
  tools/nfl_stadium_upper_deck_subset_verify.py \
  tests/test_nfl_stadium_upper_deck_subset_patch.py \
  tests/test_nfl_stadium_upper_deck_subset_verify.py \
  tests/nfl_stadium_upper_deck_subset_patch_test.py; do
  test -f "$required"
done

test "$(stat -c %s "$catalog")" = 858600
test "$(sha256sum "$catalog" | cut -d' ' -f1)" = \
  'f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa'
test "$(stat -c %s "$boundary")" = 25285
test "$(sha256sum "$boundary" | cut -d' ' -f1)" = \
  'e583dde9bca86971eb7355fd07b6a6646a09af8356623b4114c3003998ea4bdb'
test "$(stat -c %s "$recipe_schema")" = 2209
test "$(sha256sum "$recipe_schema" | cut -d' ' -f1)" = \
  '4fac01c6cffe03481b456899ec2b2f3cd25f74954d5db94ccb3b8351f841ca4b'

test "$(stat -c %s tools/nfl_stadium_upper_deck_subset_patch.py)" = 49632
test "$(sha256sum tools/nfl_stadium_upper_deck_subset_patch.py | cut -d' ' -f1)" = \
  'a3fdd538d9d8873d20e45739b85df65684f4674f576b74afab2c78e571d35740'
test "$(stat -c %s tools/nfl_stadium_upper_deck_subset_verify.py)" = 64069
test "$(sha256sum tools/nfl_stadium_upper_deck_subset_verify.py | cut -d' ' -f1)" = \
  'bd8a7561e809fcd29296fcaa8123176b1bc7a3bbe3ac3ad1d30457d03404799c'
test "$(stat -c %s tests/test_nfl_stadium_upper_deck_subset_patch.py)" = 15840
test "$(sha256sum tests/test_nfl_stadium_upper_deck_subset_patch.py | cut -d' ' -f1)" = \
  '741ed78b40871d0f8fda68031852a37407b28eef697970583fce4ea0eda340f3'
test "$(stat -c %s tests/test_nfl_stadium_upper_deck_subset_verify.py)" = 13955
test "$(sha256sum tests/test_nfl_stadium_upper_deck_subset_verify.py | cut -d' ' -f1)" = \
  '31b0dfd851f00de7be295c3fc70b86803d03ddd2d1357c77a53201d22022116b'
test "$(stat -c %s tests/nfl_stadium_upper_deck_subset_patch_test.py)" = 11830
test "$(sha256sum tests/nfl_stadium_upper_deck_subset_patch_test.py | cut -d' ' -f1)" = \
  '3674494bfcb9ee5364613b3ab60f7b7631ee59edeea58518076c12ff931d5b70'

test "$(stat -c %s "$prefix8")" = 310
test "$(sha256sum "$prefix8" | cut -d' ' -f1)" = \
  '6ab4313098939202f528820cc25862cc8a289907562d61c1d5431b57a9c511e6'
test "$(stat -c %s "$nonidentity4")" = 284
test "$(sha256sum "$nonidentity4" | cut -d' ' -f1)" = \
  '546700178dfd2bf116beaa9bcd534c4be38a0b2f2d450590c809d605b428b311'
test "$(stat -c %s "$roundtrip")" = 12554
test "$(sha256sum "$roundtrip" | cut -d' ' -f1)" = \
  'dd9858e01e571a6bfc7fc9577caa1cf218390cb1f19b1436d1bb099805aeb4e0'
test "$(stat -c %s "$closure")" = 13933
test "$(sha256sum "$closure" | cut -d' ' -f1)" = \
  '6f9b18450cef7b2fea6d64fd7972cb3381170f3b453885519c5407622e29f026'
test "$(stat -c %s "$doc")" = 7025
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  'eb8254c3ed5939377010d9e4966b501dd36ad2410505ed3f860080ecce3d2ec8'

jq -e '
  .schema == "nfl2k5_upper_deck_source_subset_writeback_closure/v1" and
  .authority.changed_count_boundary.implementation_claims_are_intentionally_frozen_false == true and
  .format_contract.outer_resource_chain.resource_count == 11 and
  .format_contract.outer_resource_chain.resource_offsets[5] == 387648 and
  .format_contract.shape.vertex_count_u16le_decoded_offset == 30540 and
  .format_contract.shape.draw_arrays_count_byte_decoded_offset == 69887 and
  (.format_contract.streams | map([.stream_index,.stride_bytes])) == [[0,12],[1,10]] and
  .implementation_contract.changed_modes.admitted_vertex_counts == [4,8] and
  .implementation_contract.changed_modes.external_positions_or_attributes_admitted == false and
  .results.identity_noop.decoded_changed_byte_count == 0 and
  .results.identity_noop.output_volume_sha256 == "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a" and
  .results.count_only_prefix8.decoded_changed_byte_count == 2 and
  .results.count_only_prefix8.decoded_sha256 == "dffa0cc9aa4599c94fe436ec8599c8b9597eacb0d377865c6454a733cf56f272" and
  .results.nonidentity_source_subset4.decoded_changed_byte_count == 64 and
  .results.nonidentity_source_subset4.decoded_sha256 == "5503271598c6f55edb0f4d19b5232cadd55a9869029bf343287cb2157c4b9f93" and
  .results.nonidentity_source_subset4.output_volume_sha256 == "65f3775e804db6c93a9f560737c6879d2fa8fb81e21559f33e755c5f8173d290" and
  (.results.refusals | all(. == true)) and
  .claim_flags.changed_count_source_subset_writer_implemented == true and
  .claim_flags.independent_changed_count_verifier_implemented == true and
  .claim_flags.static_non_skinned_target_specific_writeback_proved == true and
  .claim_flags.arbitrary_external_vertex_authoring_proved == false and
  .claim_flags.bounds_or_culling_serializer_proved == false and
  .claim_flags.runtime_visibility_proved == false and
  .claim_flags.original_xbox_hardware_proved == false and
  .claim_flags.production_ready == false and
  .claim_flags.gui_exposed == false
' "$closure" >/dev/null

jq -e '
  .schema == "nfl2k5_upper_deck_source_subset_roundtrip/v1" and
  .source.retail_modified == false and
  .identity_noop.output.pack_changed_byte_count == 0 and
  .identity_noop.compression.consumed_bytes == 908864 and
  .identity_noop.compression.scratch_bytes == 16 and
  .count_only_prefix8.decoded.decoded_changed_byte_count == 2 and
  .count_only_prefix8.decoded.stream_prefix_changed_byte_counts == [0,0] and
  .count_only_prefix8.compression.consumed_bytes == 908863 and
  .count_only_prefix8.compression.scratch_bytes == 32 and
  .nonidentity_source_subset4.decoded.decoded_changed_byte_count == 64 and
  .nonidentity_source_subset4.decoded.stream_prefix_changed_byte_counts == [34,28] and
  .nonidentity_source_subset4.output.volume_sha256 == "65f3775e804db6c93a9f560737c6879d2fa8fb81e21559f33e755c5f8173d290" and
  .nonidentity_source_subset4.compression.consumed_bytes == 908822 and
  .nonidentity_source_subset4.compression.scratch_bytes == 64 and
  (.refusals | all(. == true)) and
  .claims.independent_changed_count_verifier_implemented == true and
  .claims.arbitrary_external_vertex_authoring_proved == false and
  .claims.runtime_visibility_proved == false and
  .claims.production_ready == false
' "$roundtrip" >/dev/null

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_stadium_upper_deck_subset_patch.py \
  tools/nfl_stadium_upper_deck_subset_verify.py \
  tests/test_nfl_stadium_upper_deck_subset_patch.py \
  tests/test_nfl_stadium_upper_deck_subset_verify.py \
  tests/nfl_stadium_upper_deck_subset_patch_test.py

PYTHONDONTWRITEBYTECODE=1 python3 tests/test_nfl_stadium_upper_deck_subset_patch.py >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_nfl_stadium_upper_deck_subset_verify >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 tests/nfl_stadium_upper_deck_subset_patch_test.py \
  --report "$temporary/roundtrip.json" >/dev/null
cmp "$roundtrip" "$temporary/roundtrip.json"

if ! bash tools/validate_nfl_upper_deck_changed_count_spec.sh; then
  echo 'upper-deck changed-count authority validation failed' >&2
  exit 1
fi

test "$(sha256sum "$index" | cut -d' ' -f1)" = \
  '34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d'
test "$(sha256sum "$pack" | cut -d' ' -f1)" = \
  '779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a'

echo 'NFL_UPPER_DECK_SUBSET_PATCH_VALIDATION_PASS target=3280/5/2648/1:upper_deck source_vertices=12 changed_counts=8,4 streams=12,10 identity_pack_exact=true prefix8_decoded_changes=2 nonidentity4_decoded_changes=64 consumed=908822/908864 scratch=64 fixed_tail=16 outside_chunk_exact=true inode_races_refused=true independent_verify=true runtime=false external_geometry=false bounds=false hardware=false production=false tests=21'
