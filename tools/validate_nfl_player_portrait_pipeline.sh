#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/nfl-player-portrait.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
cd "$root"

generator=tools/nfl_player_portrait_compatibility.py
targets=tools/nfl_player_portrait_targets.py
importer=tools/nfl_player_portrait_png_import.py
fixture_tool=tools/nfl_player_portrait_fixture.py
workflow=tools/nfl_player_portrait_xiso_workflow.py
verifier=tools/nfl_player_portrait_xiso_verify.py
virtual_verifier=tools/nfl_player_portrait_xiso_virtual_verify.py
virtual_test=tests/test_nfl_player_portrait_xiso_virtual_verify.py
report=reports/assets/nfl2k5_player_portrait_compatibility.json
table=reports/assets/nfl2k5_player_portrait_compatibility.tsv
doc=docs/research/nfl_player_portrait_pipeline.md
trace=reports/assets/nfl2k5_player_portrait_owner/nfl_portrait_photo_audit_trace.txt
pseudo=reports/assets/nfl2k5_player_portrait_owner/nfl_portrait_photo_audit_pseudo_c.c
fixture=assets/fixtures/nfl2k5/player_portrait/portrait_0124_nonretail.png
plan=assets/fixtures/nfl2k5/player_portrait/plan.json
proof=build/nfl2k5-player-portrait-workflow-20260712/ESPN-NFL-2K5-portrait-0124.xiso.iso
proof_manifest=build/nfl2k5-player-portrait-workflow-20260712/workflow.json
proof_previews=build/nfl2k5-player-portrait-workflow-20260712/previews

for path in "$generator" "$targets" "$importer" "$fixture_tool" "$workflow" \
  "$verifier" "$virtual_verifier" "$virtual_test" "$report" "$table" "$doc" \
  "$trace" "$pseudo" "$fixture" "$plan" "$proof_manifest"; do
  test -f "$path"
done
test -d "$proof_previews"
test ! -e "$proof"
test ! -L "$proof"

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  "$generator" "$targets" "$importer" "$fixture_tool" "$workflow" "$verifier" \
  "$virtual_verifier" "$virtual_test"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 -m unittest \
  tests.test_nfl_player_portrait_xiso_virtual_verify >/dev/null

PYTHONPATH=tools python3 "$generator" \
  --json "$tmp/compatibility.json" --tsv "$tmp/compatibility.tsv"
cmp "$tmp/compatibility.json" "$report"
cmp "$tmp/compatibility.tsv" "$table"

PYTHONPATH=tools python3 - "$report" "$fixture" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

from nfl_player_portrait_fixture import rgba_fixture
from nfl_player_portrait_targets import select_target
from nfl_tset_png_import import decode_rgba_png

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "nfl2k5_player_portrait_compatibility/v1"
summary = report["summary"]
assert summary["aggregate_resource_count"] == 4937
assert summary["numeric_portrait_count"] == 4303
assert summary["team_select_helmet_card_count"] == 634
assert summary["cross_pack_span_count"] == 1
assert summary["cross_pack_resource_name"] == "4070"
assert summary["current_roster_record_count"] == 2547
assert summary["current_roster_portrait_hit_count"] == 2248
assert summary["current_roster_fallback_count"] == 299
assert summary["all_source_xiso_spans_match"] is True
assert report["layout_contract"]["slot_size"] == 17664
assert report["layout_contract"]["post_span_zero_padding"] == 96
assert report["portrait_cacr"]["hash_list_exactly_matches_aggregate_names"] is True
assert report["asset_family_distinction"]["action_photo_classification"] == \
    "Crib Team Photo action art; not roster headshots"
assert report["xbe_runtime_binding"]["crib_team_photo_binding"]["result_example"] == \
    "00_photo_00"
action = report["crib_action_photo_contract"]
assert action["resource_count"] == 128
assert action["mip_dimensions"] == [128, 64, 32, 16, 8]
assert action["slot_size"] == 23040 and action["post_span_zero_padding"] == 32
assert action["png_import_implemented"] is False
assert len(report["crib_action_photo_resources"]) == 128
assert report["claims"]["runtime_visibility_proved"] is False
assert report["claims"]["originals_modified"] is False

_, _, target_0124 = select_target("0124", Path(sys.argv[1]))
_, _, target_4070 = select_target("4070", Path(sys.argv[1]))
assert target_0124.selector == "portrait:0124"
assert len(target_0124.span_segments) == 1
assert target_4070.selector == "portrait:4070"
assert [item["size"] for item in target_4070.span_segments] == [8448, 9120]

payload = Path(sys.argv[2]).read_bytes()
width, height, rgba = decode_rgba_png(payload, (128, 128))
assert (width, height) == (128, 128)
assert rgba == rgba_fixture()
assert hashlib.sha256(payload).hexdigest() == \
    "4309c75573d0ae4611c15dd80ca0e4f0c404feb1322b103eb532d5793da244a4"
PY

mkdir "$tmp/import-0124" "$tmp/import-4070" "$tmp/reject-symlink" \
  "$tmp/reject-id" "$tmp/reject-forged"
PYTHONPATH=tools python3 "$importer" --portrait-id 0124 --png "$fixture" \
  --output-span "$tmp/import-0124/replacement.txtr.bin" \
  --preview "$tmp/import-0124/preview.png" \
  --manifest "$tmp/import-0124/import.json"
PYTHONPATH=tools python3 "$importer" --portrait-id 4070 --png "$fixture" \
  --output-span "$tmp/import-4070/replacement.txtr.bin" \
  --preview "$tmp/import-4070/preview.png" \
  --manifest "$tmp/import-4070/import.json"

python3 - "$tmp/import-0124/import.json" "$tmp/import-4070/import.json" <<'PY'
import json
import sys
a = json.load(open(sys.argv[1], encoding="utf-8"))
b = json.load(open(sys.argv[2], encoding="utf-8"))
assert a["target"]["selector"] == "portrait:0124"
assert a["replacement"]["span_sha256"] == \
    "d4f20e8fb349d35b59a3fe067c2cf6ae24bab60924b6664d57baec334c627fc8"
assert a["preview"]["sha256"] == \
    "4309c75573d0ae4611c15dd80ca0e4f0c404feb1322b103eb532d5793da244a4"
assert b["target"]["selector"] == "portrait:4070"
assert len(b["target"]["span_segments"]) == 2
assert b["replacement"]["span_sha256"] == \
    "0e4e9b803460762b8dc362f65e10bbf52d9c935cde81a10e2036a48e6dfc6465"
assert a["claims"]["runtime_visibility_proved"] is False
assert b["claims"]["runtime_visibility_proved"] is False
PY

# O_EXCL: a second attempt must not overwrite any retained output.
if PYTHONPATH=tools python3 "$importer" --portrait-id 0124 --png "$fixture" \
  --output-span "$tmp/import-0124/replacement.txtr.bin" \
  --preview "$tmp/import-0124/preview.png" \
  --manifest "$tmp/import-0124/import.json" >/dev/null 2>&1; then
  echo "portrait importer unexpectedly overwrote existing outputs" >&2
  exit 1
fi

# Final-component symlinks and malformed IDs fail closed.
ln -s "$root/$fixture" "$tmp/portrait-link.png"
if PYTHONPATH=tools python3 "$importer" --portrait-id 0124 \
  --png "$tmp/portrait-link.png" \
  --output-span "$tmp/reject-symlink/replacement.txtr.bin" \
  --preview "$tmp/reject-symlink/preview.png" \
  --manifest "$tmp/reject-symlink/import.json" >/dev/null 2>&1; then
  echo "portrait importer accepted a PNG symlink" >&2
  exit 1
fi
if PYTHONPATH=tools python3 "$importer" --portrait-id 124 --png "$fixture" \
  --output-span "$tmp/reject-id/replacement.txtr.bin" \
  --preview "$tmp/reject-id/preview.png" \
  --manifest "$tmp/reject-id/import.json" >/dev/null 2>&1; then
  echo "portrait importer accepted a non-four-digit ID" >&2
  exit 1
fi

# A canonical-looking but changed compatibility report must fail its hash pin.
python3 - "$report" "$tmp/forged.json" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
value["claims"]["runtime_visibility_proved"] = True
open(sys.argv[2], "w", encoding="utf-8").write(
    json.dumps(value, indent=2, sort_keys=True) + "\n")
PY
if PYTHONPATH=tools python3 "$importer" --compatibility "$tmp/forged.json" \
  --portrait-id 0124 --png "$fixture" \
  --output-span "$tmp/reject-forged/replacement.txtr.bin" \
  --preview "$tmp/reject-forged/preview.png" \
  --manifest "$tmp/reject-forged/import.json" >/dev/null 2>&1; then
  echo "portrait importer accepted a forged compatibility report" >&2
  exit 1
fi

# The physical-output verifier remains strict and must reject the cleaned XISO.
if PYTHONPATH=tools python3 "$verifier" \
  --source-xiso "ESPN NFL 2K5 (USA).xiso.iso" \
  --output-xiso "$proof" --manifest "$proof_manifest" \
  --preview-dir "$proof_previews" --plan "$plan" >/dev/null 2>&1; then
  echo "physical portrait verifier accepted an absent output XISO" >&2
  exit 1
fi

virtual_result=$(PYTHONPATH=tools python3 "$virtual_verifier" \
  --source-xiso "ESPN NFL 2K5 (USA).xiso.iso" \
  --absent-output-xiso "$proof" --manifest "$proof_manifest" \
  --preview-dir "$proof_previews" --plan "$plan")
test "$virtual_result" = \
  '{"all_other_xiso_bytes_identical": true, "changed_byte_count": 17401, "default_xbe_unchanged": true, "edit_count": 1, "historical_compatibility_receipt_reconstructed": true, "output_xiso_absent": true, "output_xiso_written": false, "runtime_visibility_proved": false, "schema": "nfl2k5_player_portrait_xiso_virtual_verify/v1", "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9", "virtual_output_sha256": "bb96a267077d670bb1fb206e3e523dec0934827739fa09e8cf36ec29ef0946a7", "xdvdfs_identical": true}'

test "$(sha256sum 'ESPN NFL 2K5 (USA).xiso.iso' | cut -d' ' -f1)" = \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
test "$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | cut -d' ' -f1)" = \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
grep -Fq "Crib's \`team_photo\` object" "$doc"
grep -Fq '`0x000E7181`' "$doc"
grep -Fq '4,303 numeric P8' "$doc"
grep -Fq '17,401 changed bytes' "$doc"
grep -Fq 'PORTME(runtime)' "$doc"
grep -Fq '0x0026F520 MOV EDX,0xe8ed50' "$trace"
grep -Fq '0x000E7181 MOVZX EAX,word ptr [EDX + 0x6]' "$trace"
grep -Fq 'FUN_0026f4a0' "$pseudo"
grep -Fq 'FUN_000e7170' "$pseudo"

if [[ "${NFL_PLAYER_PORTRAIT_GHIDRA:-0}" == 1 ]]; then
  ghidra=tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless
  test -x "$ghidra"
  mkdir "$tmp/ghidra"
  "$ghidra" ghidra_projects nfl2k5 -process default.xbe -readOnly -noanalysis \
    -scriptPath tools/ghidra_scripts \
    -postScript NflPortraitPhotoAudit.java "$tmp/ghidra"
  cmp "$tmp/ghidra/nfl_portrait_photo_audit_trace.txt" "$trace"
  cmp "$tmp/ghidra/nfl_portrait_photo_audit_pseudo_c.c" "$pseudo"
fi

echo "NFL_PLAYER_PORTRAIT_PIPELINE_VALIDATION_PASS portraits=4303 current_hits=2248 current_fallback=299 crib_action_photos=128 cross_pack=4070 xiso_changed=17401 output_sha=bb96a267077d670bb1fb206e3e523dec0934827739fa09e8cf36ec29ef0946a7 absent_output_virtualized=true physical_absent_output_refused=true historical_compatibility_receipt_reconstructed=true output_xiso_written=false forged_refused=true symlink_refused=true malformed_id_refused=true originals_unchanged=true runtime=false"
