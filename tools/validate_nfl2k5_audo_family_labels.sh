#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

TOOL=tools/nfl2k5_audo_family_labels.py
TEST=tests/test_nfl2k5_audo_family_labels.py
AUDIT=reports/assets/nfl2k5_audo_import_capacity.json
REPORT=reports/assets/nfl2k5_audo_family_labels.json
EXPECTED_AUDIT_SHA=1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556
EXPECTED_REPORT_SHA=ea66da8ea539114563de5694599a6046bde78661556846a34f8addeb31d544dd

python3 -m py_compile "$TOOL" "$TEST"
PYTHONDONTWRITEBYTECODE=1 python3 "$TEST"

test "$(sha256sum "$AUDIT" | cut -d' ' -f1)" = "$EXPECTED_AUDIT_SHA"
test "$(sha256sum "$REPORT" | cut -d' ' -f1)" = "$EXPECTED_REPORT_SHA"

stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
python3 "$TOOL" \
  --audit "$AUDIT" \
  --output "$stage/nfl2k5_audo_family_labels.json"
cmp "$REPORT" "$stage/nfl2k5_audo_family_labels.json"

jq -e '
  .schema == "nfl2k5_audo_family_labels/v2" and
  .source_audit_sha256 == "1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556" and
  .summary.record_count == 850 and
  .summary.reviewed_label_count == 152 and
  .summary.proved_fixed_slot_count == 1 and
  .summary.provisional_record_count == 697 and
  .summary.promoted_cue_count == (.promotions | length) and
  .summary.provisional_remaining_count ==
    (.summary.provisional_record_count - .summary.promoted_cue_count) and
  .claims.equal_pcm_means_equal_sound == true and
  .claims.equal_pcm_means_equal_runtime_trigger == false and
  .claims.family_label_is_inference_not_runtime_proof == true and
  .claims.reviewed_labels_overwritten == false and
  .claims.runtime_ownership_proved == false and
  ([.promotions[].label] | all(startswith("family: "))) and
  ([.promotions[].confidence] | all(. == "family-reviewed"))
' "$REPORT" >/dev/null

echo "NFL2K5_AUDO_FAMILY_LABELS_VALIDATION_PASS reviewed=152 proved_fixed=1 promoted=$(jq -r '.summary.promoted_cue_count' "$REPORT") provisional_remaining=$(jq -r '.summary.provisional_remaining_count' "$REPORT")"
