#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tmp_json="$(mktemp /tmp/vc-cross-cfg-XXXXXX.json)"
tmp_tsv="$(mktemp /tmp/vc-cross-cfg-XXXXXX.tsv)"
trap 'rm -f "$tmp_json" "$tmp_tsv"' EXIT

python3 tools/match_cross_title_cfg.py --json "$tmp_json" --tsv "$tmp_tsv" >/dev/null
cmp reports/cross_title/cfg_candidates.json "$tmp_json"
cmp reports/cross_title/cfg_candidates.tsv "$tmp_tsv"

jq -e '
  .schema == "vc_cross_title_cfg_candidates/v2" and
  .summary.nfl_functions_fingerprinted == 16810 and
  .summary.apf_functions_fingerprinted == 21079 and
  .summary.candidate_pairs_before_threshold == 9782 and
  .summary.candidate_source_memberships.confirmed_anchor_neighborhood == 784 and
  .summary.candidate_source_memberships.exact_control_multiset == 5702 and
  .summary.candidate_source_memberships.rare_constant == 3778 and
  .summary.machine_candidates_above_threshold == 4123 and
  .summary.machine_candidates_emitted == 256 and
  .summary.manual_confirmed_pairs == 23 and
  .summary.manual_additional_pairs == 22 and
  .summary.ambiguous_manual_families == 1 and
  .summary.manual_pairs_reached_by_candidate_generation == 22 and
  .summary.manual_pairs_generated_and_above_threshold == 15 and
  ([.manual_confirmed_pairs[] | select(.status != "manual_semantic_match")] | length) == 0 and
  ([.machine_candidates[] | select(.status != "candidate_unreviewed")] | length) == 0 and
  ([.manual_confirmed_pairs[] | select(.finding_kind == "calibration_anchor")] | length) == 1 and
  ([.manual_confirmed_pairs[] | select(.finding_kind == "additional")] | length) == 22 and
  ([.manual_confirmed_pairs[] | (.nfl.address + ":" + .apf.address)] | unique | length) == 23 and
  any(.manual_confirmed_pairs[];
      .nfl.address == "0x000BB830" and .apf.address == "0x848A4CD8") and
  any(.manual_confirmed_pairs[];
      .nfl.address == "0x000BBB80" and .apf.address == "0x848A5250") and
  any(.manual_confirmed_pairs[];
      .nfl.address == "0x001EC770" and .apf.address == "0x84960588") and
  any(.manual_confirmed_pairs[];
      .nfl.address == "0x001163C0" and .apf.address == "0x84969FF0") and
  .manual_ambiguous_families[0].status == "manual_family_match_not_one_to_one"
' reports/cross_title/cfg_candidates.json >/dev/null

echo "CROSS_TITLE_CFG_VALIDATION_PASS nfl=16810 apf=21079 confirmed=23 additional=22 candidates=256"
