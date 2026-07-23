#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

python3 -m py_compile tools/playbook_lineage.py
tmp=$(mktemp -d /tmp/vc-playbook-lineage.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

python3 tools/playbook_lineage.py \
  --json "$tmp/playbook_lineage.json" \
  --tsv "$tmp/playbook_lineage.tsv"

cmp "$tmp/playbook_lineage.json" reports/assets/playbook_descriptor_lineage.json
cmp "$tmp/playbook_lineage.tsv" reports/assets/playbook_descriptor_lineage.tsv

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("reports/assets/playbook_descriptor_lineage.json").read_text())
assert report["schema"] == "vc_cross_title_playbook_descriptor_lineage/v1"
assert report["summary"] == {
    "apf_descriptor_occurrence_count": 6446,
    "apf_play_occurrences_with_all_eleven_first_nodes_matching": 101,
    "apf_play_occurrences_with_same_name_and_exact_converted_eleven_descriptor_signature": 161,
    "apf_unique_descriptor_count": 88,
    "descriptor_conversion_roundtrip_complete": True,
    "distinct_names_with_all_eleven_first_nodes_matching": 101,
    "distinct_names_with_exact_converted_eleven_descriptor_signature": 155,
    "mapped_unique_descriptors_observed_in_both": 78,
    "nfl_descriptor_occurrence_count": 101761,
    "nfl_unique_descriptor_count": 94,
}
assert report["descriptor_conversion"]["inverse_is_exact_for_every_observed_descriptor"]
assert len(report["unique_apf_to_nfl_descriptor_mapping"]) == 88
assert len(report["same_name_exact_signature_matches"]) == 161
assert all("PORTME:" in item for item in report["portme"])

by_name = {
    row["name"]: row for row in report["same_name_exact_signature_matches"]
}
assert by_name["Strong Iso"]["converted_descriptor_signature"][0] == "0x00b12913"
assert by_name["Strong Iso"]["all_eleven_first_nodes_match"]
assert by_name["90 F Speed Under"]["converted_descriptor_signature"][0] == "0x00b12d14"
assert by_name["90 F Speed Under"]["all_eleven_first_nodes_match"]
PY

echo 'PLAYBOOK_LINEAGE_VALIDATION_PASS descriptors=88/94/78 plays=161/155 first_nodes=101/101'
