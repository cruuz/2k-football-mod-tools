#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
SMOKE=/tmp/nfl2k5_scene_probe_validation.json

python3 -m py_compile tools/nfl_scene_probe.py
python3 tools/nfl_scene_probe.py "$INDEX" \
  --select 3:16 \
  --select 3:100 \
  --select 3:116 \
  --select 2368:0 \
  --select 2660:0 \
  --output "$SMOKE"

jq -e '
  .source_inventory == "reports/assets/nfl2k5_resource_chunks_v2.json" and
  .source_inventory_summary.resource_chunk_count == 86882 and
  .source_inventory_summary.resource_kind_counts.TXTR == 57208 and
  .source_inventory_summary.resource_kind_counts.SCNE == 4616 and
  .source_inventory_summary.resource_kind_counts.SHAP == 1251 and
  .source_inventory_summary.padded_successor_count == 12355 and
  .summary.record_count == 5 and
  .summary.status_counts.blocked == null
' "$SMOKE" >/dev/null

jq -e '
  .source_inventory_summary.resource_chunk_count == 86882 and
  .summary.record_count == 850 and
  .summary.status_counts.parsed == 850 and
  .summary.audo_channel_counts == {"1":806,"2":44} and
  .summary.audo_codec_word_counts == {"0x00000011":850} and
  ([.records[].semantic.block_remainder] | all(. == 0)) and
  ([.records[].semantic.first_block_step_indices_valid] | all(. == true)) and
  ([.records[].semantic.codec_inference] | all(. == "Xbox IMA ADPCM (high confidence)") )
' reports/assets/nfl2k5_audo_probe.json >/dev/null

jq -e '
  .summary.record_count == 32 and
  .summary.status_counts.decoded == 32 and
  .summary.tset_reference_total == 146 and
  ([.records[].semantic.references[].root_offset] | all(. == 0)) and
  ([.records[].semantic.references[].descriptor.format_name] | all(. == "P8"))
' reports/assets/nfl2k5_tset_probe.json >/dev/null

jq -e '
  .summary.record_count == 1251 and
  .summary.status_counts.parsed == 1247 and
  .summary.status_counts.blocked == 4 and
  .padded_arrays[0].outer_index == 3108 and
  .padded_arrays[0].slot_count == 624 and
  .padded_arrays[0].all_padding_zero == true
' reports/assets/nfl2k5_shap_probe.json >/dev/null

jq -e '
  .summary.record_count == 258 and
  .summary.status_counts.parsed == 248 and
  .summary.status_counts.decoded == 10 and
  .padded_arrays[0].outer_index == 4291 and
  .padded_arrays[0].slot_count == 236 and
  .padded_arrays[0].all_padding_zero == true and
  ([.records[] | select(.kind == "SKEL") | .semantic.record_count] == [25])
' reports/assets/nfl2k5_scene_audio_probe.json >/dev/null

ffprobe -v error \
  -show_entries stream=codec_name,channels,sample_rate \
  -of json \
  assets/intermediate/nfl2k5/audio_samples/outer_0003_chunk_0100_espn-ticker_01.wav \
  | jq -e '.streams[0] == {"codec_name":"pcm_s16le","sample_rate":"15000","channels":1}' \
  >/dev/null

ffprobe -v error \
  -show_entries stream=codec_name,channels,sample_rate \
  -of json \
  assets/intermediate/nfl2k5/audio_samples/outer_0023_chunk_0001_draft_computer_to_draftboard1.wav \
  | jq -e '.streams[0] == {"codec_name":"pcm_s16le","sample_rate":"22050","channels":2}' \
  >/dev/null

rg -q '^TSET raw=1 scalar_operands=1$' \
  research/functions/nfl2k5/focused/asset_fourcc_trace.txt
rg -q '^AUDO raw=7 scalar_operands=7$' \
  research/functions/nfl2k5/focused/asset_fourcc_trace.txt
rg -q '^SCNE raw=135 scalar_operands=120$' \
  research/functions/nfl2k5/focused/asset_fourcc_trace.txt
rg -q '^CANDIDATE_FUNCTIONS count=102$' \
  research/functions/nfl2k5/focused/asset_fourcc_trace.txt

sha256sum --check reports/assets/nfl2k5_scene_audio.sha256
echo 'NFL2K5_SCENE_AUDIO_VALIDATION_PASS'
