#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

mkdir -p /media/noah/Storage/.codex-tmp
temporary="$(mktemp -d /media/noah/Storage/.codex-tmp/apf-wrapup-followup-validate.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT

apf_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
apf_index='extracted/All-Pro Football 2K8 (USA)/0A'
nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
nfl_index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
canonical_trace='reports/cut_content/apf_nfl_lineage/wrapup_followup_ghidra/trace.txt'
canonical_json='reports/cut_content/apf_nfl_lineage/wrapup_followup.json'
canonical_tsv='reports/cut_content/apf_nfl_lineage/wrapup_followup_video_claims.tsv'

hashes_before="$temporary/originals.before"
hashes_after="$temporary/originals.after"
sha256sum "$apf_xex" "$apf_index" "$nfl_xbe" "$nfl_index" > "$hashes_before"

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$temporary/xex_extract_pe"

"$temporary/xex_extract_pe" "$apf_xex" "$temporary/apf2k8_default.pe" \
  > "$temporary/extract.stdout"
test "$(sha256sum "$temporary/apf2k8_default.pe" | awk '{print $1}')" = \
  cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_nfl_wrapup_followup.py

trace="$canonical_trace"
mode=normal
if [[ "${APF_NFL_WRAPUP_FOLLOWUP_GHIDRA:-0}" == 1 ]]; then
  ghidra=tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless
  test -x "$ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfCutContentFollowupTrace.java "$temporary/trace.txt" \
      > "$temporary/ghidra.stdout" 2>&1
  cmp "$canonical_trace" "$temporary/trace.txt"
  trace="$temporary/trace.txt"
  mode=full
fi

generate() {
  local prefix="$1"
  PYTHONPATH=tools python3 tools/apf_nfl_wrapup_followup.py \
    --apf-pe "$temporary/apf2k8_default.pe" \
    --ghidra-trace "$trace" \
    --json-out "$prefix.json" \
    --claims-tsv-out "$prefix.tsv"
}

generate "$temporary/first"
generate "$temporary/second"
cmp "$temporary/first.json" "$temporary/second.json"
cmp "$temporary/first.tsv" "$temporary/second.tsv"
cmp "$canonical_json" "$temporary/first.json"
cmp "$canonical_tsv" "$temporary/first.tsv"

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path(
    "reports/cut_content/apf_nfl_lineage/wrapup_followup.json"
).read_text())
assert report["schema"] == "vc_apf_nfl_wrapup_followup/v1"
assert report["scope"] == {
    "read_only_static_and_asset_analysis": True,
    "launches_game_or_emulator": False,
    "executes_translated_guest_code": False,
    "writes_game_images": False,
    "playable_hidden_franchise_proved": False,
}

cluster = report["wrapup_cluster"]
assert cluster["nfl_outer_indices_are_consecutive_17_through_21"] is True
assert cluster["all_five_have_exact_cross_platform_filename_hash_pairs"] is True
assert [row["nfl_outer_index"] for row in cluster["packages"]] == [17, 18, 19, 20, 21]
assert [row["apf_outer_index"] for row in cluster["packages"]] == [349, 730, 265, 1221, 941]
awards = cluster["awards_package"]
assert awards["new_filename_resolution"] == "awards.iff"
assert awards["nfl_xbe_utf16le_filename_literal_count"] == 1
assert awards["franchise_show_marker_name_witnesses"] == [
    "show_primetime_players", "show_season_awards"
]
assert awards["marker_to_awards_action_semantics_proved"] is False
assert [row["name"] for row in awards["resources"]] == ["primetimePlayers", "seasonAwards"]
assert all(row["decoded_bodies_byte_identical"] is False for row in awards["resources"])
assert awards["runtime_owner_proved"] is False
assert not any(awards["apf_pe_direct_literal_scan"].values())

director = cluster["packages"][2]
assert director["apf_instruction_record_count"] == director["nfl_instruction_record_count"] == 96
assert director["apf_fixed_record_count"] == director["nfl_fixed_record_count"] == 20
assert director["ordered_structural_signature_match_count"] == 19

franchise_name = report["franchise_filename_resolution"]
assert franchise_name["previously_unresolved_nfl_outer_index"] == 23
assert franchise_name["nfl_filename"] == "fr.iff"
assert franchise_name["nfl_outer_id"] == "0xc59d46a8"
assert franchise_name["nfl_xbe_utf16le_literal_count"] == 1
assert franchise_name["nfl_xbe_literal_file_offset"] == "0x00b0b6f8"
assert franchise_name["apf_descendant_outer_index"] == 810
assert franchise_name["apf_descendant_filename"] == "franchise.iff"
assert franchise_name["apf_descendant_outer_id"] == "0x852e246f"

frontend = report["frontend_lineage"]
assert frontend["apf_comparable_resource_count"] == 57
assert frontend["nfl_comparable_resource_count"] == 57
assert frontend["shared_exact_name_type_count"] == 52
assert frontend["audio_name_count"] == 23
assert frontend["probable_common_source_transcoded_audio_count"] == 17
assert len(frontend["front_office_cues"]) == 2
for cue in frontend["front_office_cues"]:
    assert cue["probable_common_source_transcode"] is True
    assert cue["apf_sample_rate"] == cue["nfl_sample_rate"] == 22050
    assert cue["apf_channels"] == cue["nfl_channels"] == 1
    assert cue["sample_delta_apf_minus_nfl"] == -128
    assert cue["global_stft_magnitude_cosine"] > 0.998

drafta = report["drafta_bank_lineage"]
assert drafta["same_name_type_external_filename_and_four_track_shape"] is True
assert drafta["decoded_common_source_audio_proved"] is False
assert drafta["apf"]["entry_count"] == drafta["nfl"]["entry_count"] == 4
assert len(drafta["apf"]["substreams"]) == 4
assert all(row["decoder_verified"] is True for row in drafta["apf"]["substreams"])
assert abs(drafta["apf"]["total_duration_seconds_candidate"] - 295.2624626159668) < 1e-9

tournament = report["tournament_false_friend"]
assert tournament["playoff_setup"]["record_count"] == 32
assert tournament["playoff_setup"]["record_name_counts"] == {
    "tourney_game": 8,
    "tourney_selector_lg": 8,
    "tourney_selector_sm": 16,
}
assert tournament["compiled_hash_table"]["address"] == "0x820FABB0"
assert tournament["compiled_hash_table"]["resource_call"] == "0x84A719B8 -> 0x84B16398"
assert tournament["online_iff_outer_index"] == 899
assert tournament["online_live_draft_static_strings"] == {
    "0x8451618C": "Live Draft",
    "0x845161A4": "OnlineLiveDraft_Menu",
    "0x845161D0": "live_draft",
}
assert "not evidence for an offline franchise" in tournament["classification"]

assert [row["grade"] for row in report["video_claims"]] == [
    "A_PROVEN", "A_PROVEN", "A_PROVEN", "B_STRUCTURAL_LINEAGE", "BOUNDARY_PROVEN"
]
assert len(report["portme"]) == 4

doc = Path("docs/research/apf_nfl_wrapup_followup.md").read_text()
for phrase in (
    "five-package lineage closure",
    "NFL outer 23 is now exactly named `fr.iff`",
    "common-source transcodes",
    "tournament false friend",
    "Nothing here makes a hidden franchise playable",
):
    assert phrase in doc
PY

sha256sum "$apf_xex" "$apf_index" "$nfl_xbe" "$nfl_index" > "$hashes_after"
cmp "$hashes_before" "$hashes_after"

echo "APF_NFL_WRAPUP_FOLLOWUP_VALIDATION_PASS mode=$mode cluster=5 fr_name=fr.iff awards=2 frontend_shared=52 frontend_audio=17 drafta_tracks=4 tournament_online=true runtime=false originals_unchanged=true"
