#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
inventory=reports/assets/nfl2k5_team_select_card_inventory.json
inventory_tsv=reports/assets/nfl2k5_team_select_card_inventory.tsv
fixtures=reports/assets/nfl2k5_team_select_card_fixtures
unif_bundle=reports/assets/nfl2k5_team_select_card_import_unif_a09_0
helm_bundle=reports/assets/nfl2k5_team_select_card_import_helm_a09_0
proof=build/nfl2k5-team-select-card-workflow-20260711
output_xiso="$proof/ESPN-NFL-2K5-Detroit-away-style0-Team-Select-cards.xiso.iso"
workflow_manifest="$proof/workflow.json"
previews="$proof/previews"
temporary=$(mktemp -d "$root/build/nfl-team-select-card-validate.XXXXXX")
cleanup() {
  rm -rf -- "$temporary"
}
trap cleanup EXIT

regular_files=(
  "$source_xiso"
  "$index"
  "$inventory"
  "$inventory_tsv"
  "$fixtures/detroit_away_style0_unif_nonretail.png"
  "$fixtures/detroit_away_style0_helm_nonretail.png"
  "$fixtures/plan.json"
  "$fixtures/fixtures.json"
  "$unif_bundle/replacement.txtr.bin"
  "$unif_bundle/preview.png"
  "$unif_bundle/import.json"
  "$helm_bundle/replacement.txtr.bin"
  "$helm_bundle/preview.png"
  "$helm_bundle/import.json"
  "$output_xiso"
  "$workflow_manifest"
)
for required in "${regular_files[@]}"; do
  [[ -f "$required" && ! -L "$required" ]] || {
    echo "missing/non-regular Team Select card artifact: $required" >&2
    exit 1
  }
done
[[ -d "$previews" && ! -L "$previews" ]] || {
  echo "missing/non-regular Team Select preview directory: $previews" >&2
  exit 1
}

printf '%s  %s\n' 21a7254ee1c1be9f7fbd39596b50d5bb0e72939872e6c0ac822320c55d748ac9 "$inventory" | sha256sum -c - >/dev/null
printf '%s  %s\n' 04511643c45ac2d8fa3c1c51ce700d40f91bec2e123c4e80ee9063a36adc4773 "$inventory_tsv" | sha256sum -c - >/dev/null
printf '%s  %s\n' f4f9663f415abe6bf2ba201c8e478a5db77708bd4b93ddb627c83225c07e479c "$fixtures/plan.json" | sha256sum -c - >/dev/null
printf '%s  %s\n' 060dfb02da437e81d506aa9d2a7d7d12a48c6a047424df0a8a43934124005acf "$fixtures/fixtures.json" | sha256sum -c - >/dev/null
printf '%s  %s\n' 93b7d65002f2fdd508efc9d2419daf2820fad5bf01ea90448f6ee767998650d0 "$fixtures/detroit_away_style0_unif_nonretail.png" | sha256sum -c - >/dev/null
printf '%s  %s\n' aaa6f6520ca5040f20780b5b8105e1babf8728c7e002dd38bb754285102f5092 "$fixtures/detroit_away_style0_helm_nonretail.png" | sha256sum -c - >/dev/null
printf '%s  %s\n' 5f11da8f27d45f71f86d4c6f93c15832a38fe2606fbf7705e1de5dc302ee0cec "$unif_bundle/replacement.txtr.bin" | sha256sum -c - >/dev/null
printf '%s  %s\n' cd13e69f6d899ae9041326b29486f11c92664f21d4d7d34d62db1ea6da39da5c "$helm_bundle/replacement.txtr.bin" | sha256sum -c - >/dev/null
printf '%s  %s\n' e9a11e482620595eaf173a0d210039fdf51d275251ed49ffac28023cfe705eea "$workflow_manifest" | sha256sum -c - >/dev/null

python3 -m py_compile \
  tools/nfl_team_select_card_inventory.py \
  tools/nfl_team_select_card_targets.py \
  tools/nfl_team_select_card_fixture.py \
  tools/nfl_team_select_card_png_import.py \
  tools/nfl_team_select_card_import_verify.py \
  tools/nfl_team_select_card_xiso_workflow.py \
  tools/nfl_team_select_card_xiso_verify.py \
  tools/test_nfl_team_select_card_pipeline.py

PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_team_select_card_inventory.py \
  --json "$temporary/inventory.json" \
  --tsv "$temporary/inventory.tsv"
cmp -- "$temporary/inventory.json" "$inventory"
cmp -- "$temporary/inventory.tsv" "$inventory_tsv"

PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_team_select_card_fixture.py \
  --output-dir "$temporary/fixtures"
cmp -- \
  "$temporary/fixtures/detroit_away_style0_unif_nonretail.png" \
  "$fixtures/detroit_away_style0_unif_nonretail.png"
cmp -- \
  "$temporary/fixtures/detroit_away_style0_helm_nonretail.png" \
  "$fixtures/detroit_away_style0_helm_nonretail.png"
python3 - "$temporary/fixtures" "$fixtures" <<'PY'
import json
from pathlib import Path
import sys

fresh = Path(sys.argv[1])
canonical = Path(sys.argv[2])
fresh_report = json.loads((fresh / "fixtures.json").read_bytes())
canonical_report = json.loads((canonical / "fixtures.json").read_bytes())
assert fresh_report["schema"] == canonical_report["schema"]
assert fresh_report["algorithm"] == canonical_report["algorithm"]
assert fresh_report["retail_artwork_included"] is False
assert fresh_report["plan_file"] == "plan.json"
for left, right in zip(fresh_report["fixtures"], canonical_report["fixtures"]):
    assert {key: value for key, value in left.items() if key != "path"} == \
           {key: value for key, value in right.items() if key != "path"}
    assert Path(left["path"]).name == Path(right["path"]).name
fresh_plan = json.loads((fresh / "plan.json").read_bytes())
canonical_plan = json.loads((canonical / "plan.json").read_bytes())
assert fresh_plan["schema"] == canonical_plan["schema"]
assert fresh_plan["purpose"] == canonical_plan["purpose"]
for left, right in zip(fresh_plan["edits"], canonical_plan["edits"]):
    assert {key: value for key, value in left.items() if key != "png"} == \
           {key: value for key, value in right.items() if key != "png"}
    assert Path(left["png"]).name == Path(right["png"]).name
PY

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/test_nfl_team_select_card_pipeline.py

PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_team_select_card_import_verify.py \
  --family unif --asset-code 09 --side away --style 0 --resolution 256 \
  --png "$fixtures/detroit_away_style0_unif_nonretail.png" \
  --replacement "$unif_bundle/replacement.txtr.bin" \
  --preview "$unif_bundle/preview.png" \
  --manifest "$unif_bundle/import.json"
PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_team_select_card_import_verify.py \
  --family helm --asset-code 09 --side away --style 0 --resolution 256 \
  --png "$fixtures/detroit_away_style0_helm_nonretail.png" \
  --replacement "$helm_bundle/replacement.txtr.bin" \
  --preview "$helm_bundle/preview.png" \
  --manifest "$helm_bundle/import.json"

verify_output=$(PYTHONDONTWRITEBYTECODE=1 \
  python3 tools/nfl_team_select_card_xiso_verify.py \
    --source-xiso "$source_xiso" \
    --output-xiso "$output_xiso" \
    --manifest "$workflow_manifest" \
    --preview-dir "$previews" \
    --plan "$fixtures/plan.json" \
    --index "$index" \
    --compatibility "$inventory")
python3 - "$verify_output" <<'PY'
import json
import sys

value = json.loads(sys.argv[1])
assert value == {
    "changed_bytes": 131816,
    "edit_count": 2,
    "output_sha256": "0c368e253421dc97d35dd49324f89e4caf8994f8c10f67d9c5685907c46bdba6",
    "runtime_visibility_proved": False,
    "schema": "nfl2k5_team_select_card_xiso_verify/v1",
    "selectors": ["unif:09:away:0:256", "helm:09:away:0:256"],
    "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
    "verified_workflow_schema": "nfl2k5_team_select_card_xiso_workflow/v1",
    "xdvdfs_file_count": 19,
}
PY

# Existing final outputs must stop both writers before any output mutation.
before_xiso=$(stat -c '%d:%i:%s:%Y:%Z' "$output_xiso")
before_workflow=$(sha256sum "$workflow_manifest" | awk '{print $1}')
set +e
PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_team_select_card_xiso_workflow.py \
  --source-xiso "$source_xiso" \
  --output-xiso "$output_xiso" \
  --manifest "$workflow_manifest" \
  --preview-dir "$previews" \
  --plan "$fixtures/plan.json" \
  --index "$index" \
  --compatibility "$inventory" \
  >"$temporary/xiso-o-excl.stdout" 2>"$temporary/xiso-o-excl.stderr"
xiso_status=$?
set -e
[[ $xiso_status -ne 0 ]]
rg -q 'already exists' "$temporary/xiso-o-excl.stderr"
[[ $(stat -c '%d:%i:%s:%Y:%Z' "$output_xiso") == "$before_xiso" ]]
[[ $(sha256sum "$workflow_manifest" | awk '{print $1}') == "$before_workflow" ]]

before_unif=$(sha256sum "$unif_bundle"/*)
set +e
PYTHONDONTWRITEBYTECODE=1 python3 tools/nfl_team_select_card_png_import.py \
  --family unif --asset-code 09 --side away --style 0 --resolution 256 \
  --png "$fixtures/detroit_away_style0_unif_nonretail.png" \
  --output-span "$unif_bundle/replacement.txtr.bin" \
  --preview "$unif_bundle/preview.png" \
  --manifest "$unif_bundle/import.json" \
  >"$temporary/import-o-excl.stdout" 2>"$temporary/import-o-excl.stderr"
import_status=$?
set -e
[[ $import_status -ne 0 ]]
rg -q 'already exist' "$temporary/import-o-excl.stderr"
[[ $(sha256sum "$unif_bundle"/*) == "$before_unif" ]]

rg -q '1,902 concrete cards' docs/research/nfl_team_select_card_pipeline.md
rg -q 'runtime_visibility_proved.*false|not evidence that the title loaded' \
  docs/research/nfl_team_select_card_pipeline.md
rg -q 'nfl_team_select_card_pipeline' README.md docs/phases/phase3.md \
  docs/phases/phase4.md docs/research/nfl_actual_jersey_binding.md \
  docs/research/nfl_team_select_preview_owner.md

echo "NFL_TEAM_SELECT_CARD_PIPELINE_VALIDATION_PASS resources=1902 selector_keys=634 layouts=2 unif=unif_a09_0 helm=helm_a09_0 imports_reconstructed=true helm128=true inventory_regenerated=true fixtures_regenerated=true raw_vc_lz_na=true forged_refused=true symlink_refused=true plan_types_refused=true source_sha=7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 output_sha=0c368e253421dc97d35dd49324f89e4caf8994f8c10f67d9c5685907c46bdba6 changed_bytes=131816 xdvdfs_identical=true o_excl=true runtime_visibility=false xemu_started=false title_executed=false"
