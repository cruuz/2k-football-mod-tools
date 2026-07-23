#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

TOOL=tools/nfl_audo_import_capacity_audit.py
TEST=tests/nfl_audo_import_capacity_audit_test.py
REPORT=reports/assets/nfl2k5_audo_import_capacity.json
MATRIX=reports/assets/nfl2k5_audo_import_capacity.tsv
SOURCE_XISO='ESPN NFL 2K5 (USA).xiso.iso'
EXPECTED_SOURCE_SHA=7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
EXPECTED_REPORT_SHA=1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556
EXPECTED_MATRIX_SHA=0d17908971d8c8ba4429680ab3524cabe8cd6d0ba54255eb9175dbd3a20885e9

python3 -m py_compile "$TOOL" "$TEST"
PYTHONDONTWRITEBYTECODE=1 python3 "$TEST"

test "$(sha256sum "$REPORT" | cut -d' ' -f1)" = "$EXPECTED_REPORT_SHA"
test "$(sha256sum "$MATRIX" | cut -d' ' -f1)" = "$EXPECTED_MATRIX_SHA"
source_before=$(sha256sum "$SOURCE_XISO" | cut -d' ' -f1)
test "$source_before" = "$EXPECTED_SOURCE_SHA"

stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
python3 "$TOOL" \
  --output "$stage/nfl2k5_audo_import_capacity.json" \
  --matrix "$stage/nfl2k5_audo_import_capacity.tsv"
cmp "$REPORT" "$stage/nfl2k5_audo_import_capacity.json"
cmp "$MATRIX" "$stage/nfl2k5_audo_import_capacity.tsv"

source_after=$(sha256sum "$SOURCE_XISO" | cut -d' ' -f1)
test "$source_after" = "$source_before"

jq -e '
  .schema == "nfl2k5_audo_import_capacity/v1" and
  .summary.record_count == 850 and
  .summary.channel_counts == {"1":806,"2":44} and
  .summary.classification_counts == {
    "candidate-for-separately-authorized-fixed-slot-writer":1,
    "export-only":697,
    "structurally-encodable-owner-runtime-unproved":152
  } and
  .summary.duplicate_name_group_count == 7 and
  .summary.equal_decoded_content_group_count == 53 and
  .summary.equal_payload_group_count == 53 and
  .summary.equal_resource_span_group_count == 91 and
  .claims.all_850_exported == true and
  .claims.all_850_physical_spans_exact_and_nonoverlapping == true and
  .claims.all_850_structurally_encodable_at_same_allocation == true and
  .claims.generic_audo_writer_authorized == false and
  .claims.additional_fixed_slot_writer_authorized == false and
  .claims.runtime_selector_ownership_proved_count == 0 and
  .claims.runtime_visibility_proved_count == 0 and
  .claims.source_modified == false and
  .candidate_review.additional_candidate_count == 0 and
  .candidate_review.new_candidates == [] and
  .candidate_review.next_trace.target == "outer_0009_chunk_0033" and
  .ownership_evidence["audo-static-registration"].function == "FUN_00045740" and
  .ownership_evidence["audo-static-registration"].callback_label == "LAB_00045680" and
  ([.records[].ownership.runtime_selector_owner] | all(. == "unproved")) and
  ([.records[].structural_import.same_allocation] | all(. == true)) and
  ([.records[].structural_import.metadata_change_required] | all(. == false)) and
  ([.records[] | select(.classification == "candidate-for-separately-authorized-fixed-slot-writer") | .key]
    == ["outer_0003_chunk_0101"])
' "$REPORT" >/dev/null

test "$(wc -l < "$MATRIX")" -eq 851
echo "NFL2K5_AUDO_IMPORT_CAPACITY_VALIDATION_PASS records=850 export_only=697 structural_unproved=152 existing_fixed=1 new_candidates=0 runtime=false generic_writer=false source_modified=false"
