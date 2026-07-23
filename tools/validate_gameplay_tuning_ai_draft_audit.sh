#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

tmp="$(mktemp -d /tmp/gameplay-tuning-audit.XXXXXX)"
trap 'rm -rf "$tmp"' EXIT

nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
apf_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
report='reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json'
candidates='reports/gameplay_tuning/gameplay_tuning_mod_candidates.tsv'
portme='reports/gameplay_tuning/gameplay_tuning_ai_draft_portme.c'
trace='reports/gameplay_tuning/apf_gameplay_tuning_trace.txt'

before_nfl="$(sha256sum "$nfl_xbe" | cut -d' ' -f1)"
before_apf="$(sha256sum "$apf_xex" | cut -d' ' -f1)"

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$tmp/xex_extract_pe"

"$tmp/xex_extract_pe" "$apf_xex" "$tmp/apf.pe" >"$tmp/extract.txt"

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  tools/gameplay_tuning_ai_draft_audit.py

python3 tools/gameplay_tuning_ai_draft_audit.py \
  --nfl-xbe "$nfl_xbe" \
  --apf-xex "$apf_xex" \
  --apf-pe "$tmp/apf.pe" \
  --trace "$trace" \
  --json-out "$tmp/audit.json" \
  --tsv-out "$tmp/candidates.tsv" \
  --portme-c-out "$tmp/portme.c" \
  >"$tmp/generator.txt"

cmp "$report" "$tmp/audit.json"
cmp "$candidates" "$tmp/candidates.tsv"
cmp "$portme" "$tmp/portme.c"

cc -std=c11 -Wall -Wextra -Werror -c "$portme" -o "$tmp/portme.o"

python3 - <<'PY'
import csv
import json
from pathlib import Path

report = json.loads(Path("reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json").read_text())
assert report["schema"] == "vc_gameplay_tuning_ai_draft_audit/v1"
assert report["scope"] == {
    "emulator_or_game_launched": False,
    "franchise_port_claimed": False,
    "originals_modified": False,
    "out_of_range_runtime_safety_claimed": False,
    "read_only": True,
    "save_or_profile_fixture_supplied": False,
}
assert report["summary"] == {
    "apf_equivalent_draft_owner_proved": False,
    "copy_only_iso_gameplay_tuning_proved": False,
    "nfl_cpu_draft_owner_proved": True,
    "nfl_cpu_draft_weight_count": 17,
    "shared_slider_count": 21,
    "stock_ui_maximum": 1.0,
    "stock_ui_minimum": 0.0,
    "stock_ui_step": 0.025,
}
assert len(report["nfl2k5"]["sliders"]["records"]) == 21
assert len(report["apf2k8"]["sliders"]["offline_records"]) == 21
assert report["shared_slider_schema"]["labels"][3] == "Human Catching"
assert report["shared_slider_schema"]["labels"][12] == "CPU Catching"
assert report["nfl2k5"]["sliders"]["human_catching_direct_setter"]["range_clamp_observed"] is False
assert report["apf2k8"]["sliders"]["importer"]["range_clamp_observed"] is False
assert report["apf2k8"]["sliders"]["importer"]["serialized_size"] == 0x54
assert [row["label"] for row in report["apf2k8"]["sliders"]["importer"]["order"]] == [
    "Interception", "Human Blocking", "Human Passing", "Human Running",
    "Human Catching", "Human Coverage", "Human Pursuit", "Human Tackling",
    "Human Kicking", "Human Fatigue", "CPU Blocking", "CPU Passing",
    "CPU Running", "CPU Catching", "CPU Coverage", "CPU Pursuit",
    "CPU Tackling", "CPU Kicking", "CPU Fatigue", "Injury", "Fumble",
]
draft = report["nfl2k5"]["cpu_fantasy_draft"]
assert draft["priority_table"]["virtual_address"] == "0x00589588"
assert draft["priority_table"]["file_offset"] == "0x0057EAA8"
assert [(row["position"], row["weight"]) for row in draft["priority_table"]["rows"]] == [
    ("QB", 2.0), ("K", 0.1), ("P", 0.2), ("WR", 1.4), ("CB", 1.0),
    ("FS", 1.1), ("SS", 1.1), ("RB", 1.7), ("FB", 1.0), ("TE", 1.2),
    ("OLB", 1.2), ("ILB", 0.7), ("C", 0.5), ("G", 1.1), ("T", 1.3),
    ("DT", 1.4), ("DE", 1.3),
]
boundary = draft["corrected_priority_builder_boundary"]
assert boundary["range"] == "0x0036EE70-0x0036F095"
assert boundary["ledger_reported_range"] == "0x0036EE70-0x0036EE7C"
assert boundary["size"] == 550
assert boundary["table_pointer_occurrences"] == ["0x0036EEFA", "0x0036EF22"]
lineage = report["apf2k8"]["fantasy_draft_lineage"]
assert lineage["semantically_identical_to_nfl"] is True
assert lineage["cpu_selector_proved"] is False
assert lineage["direct_ghidra_references_to_table"] == []
assert lineage["aligned_fullword_pointers_to_table"] == []
assert lineage["conventional_lis_addi_or_ori_materializations"] == []
assert lineage["computed_or_toc_owner_exhaustively_excluded"] is False
assert report["nfl2k5"]["catch_drop_result"]["final_success_drop_branch_proved"] is False
assert report["apf2k8"]["catch_drop_result"]["final_computed_or_indexed_consumer_proved"] is False
assert report["executable_integrity_boundary"]["save_profile_alternative"]["writer_safe_to_release"] is False
assert len(report["portme"]) == 9

with Path("reports/gameplay_tuning/gameplay_tuning_mod_candidates.tsv").open(newline="") as stream:
    rows = list(csv.DictReader(stream, delimiter="\t"))
assert len(rows) == 9
assert all(row["copy_only_iso_feasible"] == "no" for row in rows)

doc = Path("docs/research/gameplay_tuning_ai_draft_modding.md").read_text()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
assert "does **not** prove every gameplay consumer" in doc
assert "not yet a proven live APF draft-AI" in doc

portme = Path("reports/gameplay_tuning/gameplay_tuning_ai_draft_portme.c").read_text()
assert portme.count("PORTME:") == len(report["portme"])
PY

test "$(sha256sum "$nfl_xbe" | cut -d' ' -f1)" = "$before_nfl"
test "$(sha256sum "$apf_xex" | cut -d' ' -f1)" = "$before_apf"
test "$before_nfl" = '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
test "$before_apf" = '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
test "$(sha256sum "$tmp/apf.pe" | cut -d' ' -f1)" = 'cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'

echo 'GAMEPLAY_TUNING_AI_DRAFT_VALIDATION_PASS sliders=21 range=0..1 step=.025 nfl_draft_weights=17 nfl_owner=true apf_owner=false out_of_range_safe=false copy_only=false runtime=false originals_unchanged=yes'
