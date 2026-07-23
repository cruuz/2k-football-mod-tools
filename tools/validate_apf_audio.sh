#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$root"

index="${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}"
manifest="${APF_INNER_MANIFEST:-reports/manifests/apf_inner.json}"
inventory_json="reports/assets/apf_audio_inventory.json"
inventory_tsv="reports/assets/apf_audio_inventory.tsv"
unique_decode="reports/assets/apf_audio_unique_decode.json"
ausb_inventory="reports/assets/apf_ausb_inventory.json"
checksums="reports/assets/apf_audio.sha256"

for required in "$index" "$manifest" tools/apf_audio.py tools/apf_ausb_audio.py "$inventory_json" "$inventory_tsv" "$unique_decode" "$ausb_inventory" "$checksums"; do
  if [[ ! -f "$required" ]]; then
    echo "APF_AUDIO_VALIDATION_FAIL missing=$required" >&2
    exit 1
  fi
done
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
sha256sum -c "$checksums"

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

python3 -m py_compile tools/apf_audio.py
python3 -m py_compile tools/apf_ausb_audio.py
python3 tools/apf_audio.py "$index" \
  --manifest "$manifest" \
  --inventory-json "$temporary/inventory.json" \
  --inventory-tsv "$temporary/inventory.tsv"
cmp "$inventory_json" "$temporary/inventory.json"
cmp "$inventory_tsv" "$temporary/inventory.tsv"

python3 tools/apf_audio.py "$index" \
  --manifest "$manifest" \
  --ausb-json "$temporary/ausb.json"
cmp "$ausb_inventory" "$temporary/ausb.json"

python3 -c '
import json, pathlib, re, sys
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text())
s = d["summary"]
assert d["schema"] == "apf_audo_inventory/v1"
assert s["manifest_audo_count"] == 2261
assert s["parsed_audo_count"] == 2261
assert s["failure_count"] == 0
assert s["invariant_failure_count"] == 0
assert s["total_encoded_bytes"] == 62513152
assert s["total_packet_count"] == 30524
assert s["metadata_size_distribution"] == {"44": 2261}
assert s["codec_or_version_distribution"] == {"1": 2261}
assert s["unknown_04_distribution"] == {"5": 2261}
assert s["channel_layout_code_distribution"] == {"2": 2088, "5": 173}
assert s["derived_channel_count_distribution"] == {"1": 2088, "2": 173}
assert s["packet_classification_distribution"] == {"xma1": 2261}
assert s["all_packet_sequences_zero_record_count"] == 2261
assert s["all_packet_skips_zero_record_count"] == 2261
assert len(d["records"]) == 2261 and not d["failures"]
hex64 = re.compile(r"^[0-9a-f]{64}$")
for row in d["records"]:
    assert all(row["invariants"].values())
    assert row["metadata"]["encoded_size"] == row["payload_part"]["length"]
    assert row["packet_summary"]["packet_count"] * 2048 == row["payload_part"]["length"]
    assert row["packet_summary"]["classification_distribution"] == {"xma1": row["packet_summary"]["packet_count"]}
    assert row["packet_summary"]["xma1_metadata_distribution"] == {"2": row["packet_summary"]["packet_count"]}
    assert row["packet_summary"]["xma1_sequence_distribution"] == {"0": row["packet_summary"]["packet_count"]}
    assert row["packet_summary"]["xma1_packet_skip_distribution"] == {"0": row["packet_summary"]["packet_count"]}
    assert hex64.fullmatch(row["payload_sha256"])
print("APF_AUDIO_INVENTORY_CHECK_PASS")
' "$inventory_json"

python3 -c '
import json, pathlib, sys
inventory = json.loads(pathlib.Path(sys.argv[1]).read_text())
decode = json.loads(pathlib.Path(sys.argv[2]).read_text())
s = decode["summary"]
assert decode["schema"] == "apf_audo_unique_decode_verification/v1"
assert s["audo_record_count"] == 2261
assert s["unique_payload_count"] == 1268
assert s["duplicate_record_count"] == 993
assert s["decoder_verified_unique_payload_count"] == 1261
assert s["not_decoder_verified_unique_payload_count"] == 7
assert s["decoder_verified_audo_record_count"] == 2229
assert s["not_decoder_verified_audo_record_count"] == 32
assert s["status_distribution"] == {
    "decode_failed": 7,
    "decoder_verified_exact_declared_samples": 20,
    "decoder_verified_with_declared_tail_gap": 641,
    "decoder_verified_with_padding_tail": 600,
}
assert s["failed_sample_rate_distribution"] == {"22050": 1, "32000": 2, "48000": 4}
assert len(decode["results"]) == 1268
inventory_hashes = {row["payload_sha256"] for row in inventory["records"]}
decode_hashes = {row["payload_sha256"] for row in decode["results"]}
assert decode_hashes == inventory_hashes
failed = [row for row in decode["results"] if row["status"] == "decode_failed"]
assert len(failed) == 7
assert all(row["stderr"] for row in failed)
assert all("0xADDR" in row["stderr"] for row in failed)
print("APF_AUDIO_UNIQUE_DECODE_CHECK_PASS")
' "$inventory_json" "$unique_decode"

python3 -c '
import json, pathlib, sys
d = json.loads(pathlib.Path(sys.argv[1]).read_text())
s = d["summary"]
assert d["schema"] == "apf_ausb_external_bank_inventory/v1"
assert s["manifest_ausb_count"] == 20
assert s["parsed_ausb_count"] == 20
assert s["failure_count"] == 0 and s["invariant_failure_count"] == 0
assert s["unique_external_bin_count"] == 19
assert s["total_substream_count"] == 45514
assert s["unique_external_encoded_bytes"] == 1144270848
assert s["sample_rate_distribution"] == {"22050": 14, "48000": 6}
assert s["channel_layout_code_distribution"] == {"2": 7, "5": 13}
assert len(d["records"]) == 20 and not d["failures"]
for row in d["records"]:
    assert all(row["invariants"].values())
    a = row["ausb"]
    ext = row["linked_external_outer_entry"]
    assert a["terminal_boundary"]["packet_offset"] == ext["size"]
    assert len(a["entries"]) == a["entry_count"]
    assert all(entry["external_range"]["first_packet"]["classification"] == "xma1" for entry in a["entries"])
    assert all(entry["external_range"]["length"] % 2048 == 0 for entry in a["entries"])
    assert a["entries"][0]["value_bits"] == (a["entries"][1]["value_bits"] if len(a["entries"]) > 1 else a["terminal_boundary"]["value_bits"])
print("APF_AUSB_INVENTORY_CHECK_PASS")
' "$ausb_inventory"

if [[ "${APF_AUDIO_FULL_DECODE:-0}" == "1" ]]; then
  python3 tools/apf_audio.py "$index" \
    --manifest "$manifest" \
    --verify-unique-json "$temporary/unique_decode.json" \
    --jobs 8
  cmp "$unique_decode" "$temporary/unique_decode.json"
  echo "APF_AUDIO_FULL_DECODE_REPRODUCTION_PASS"
fi

python3 tools/apf_audio.py "$index" \
  --export-entry 23 --export-file 10 \
  --output-xma "$temporary/player-breath-slow_01.xma" \
  --verify-wav "$temporary/player-breath-slow_01.wav" \
  --export-report "$temporary/player-breath-slow_01.json"
cmp reports/asset_samples/apf/audio/player_breath_slow/player-breath-slow_01.xma \
  "$temporary/player-breath-slow_01.xma"
cmp reports/asset_samples/apf/audio/player_breath_slow/player-breath-slow_01.wav \
  "$temporary/player-breath-slow_01.wav"

python3 tools/apf_audio.py "$index" \
  --export-entry 5 --export-file 0 \
  --output-xma "$temporary/clap-loop-front_01.xma" \
  --verify-wav "$temporary/clap-loop-front_01.wav" \
  --export-report "$temporary/clap-loop-front_01.json"
cmp reports/asset_samples/apf/audio/clap_loop_front/clap-loop-front_01.xma \
  "$temporary/clap-loop-front_01.xma"
cmp reports/asset_samples/apf/audio/clap_loop_front/clap-loop-front_01.wav \
  "$temporary/clap-loop-front_01.wav"

python3 tools/apf_ausb_audio.py "$index" \
  --entry 659 --file 132 --substream 0 \
  --output-xma "$temporary/halftimeaudio_00000.xma" \
  --verify-wav "$temporary/halftimeaudio_00000.wav" \
  --report "$temporary/halftimeaudio_00000.json"
cmp reports/asset_samples/apf/audio/ausb_halftime_0/halftimeaudio_00000.xma \
  "$temporary/halftimeaudio_00000.xma"
cmp reports/asset_samples/apf/audio/ausb_halftime_0/halftimeaudio_00000.wav \
  "$temporary/halftimeaudio_00000.wav"

if python3 tools/apf_audio.py "$index" \
  --export-entry 5 --export-file 13 \
  --output-xma "$temporary/cheer-front_01.xma" \
  --verify-wav "$temporary/cheer-front_01.wav" \
  --export-report "$temporary/cheer-front_01.json"; then
  echo "APF_AUDIO_VALIDATION_FAIL expected_32khz_decoder_rejection" >&2
  exit 1
fi
test ! -e "$temporary/cheer-front_01.wav"
python3 -c '
import json, pathlib, sys
d = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert d["metadata"]["sample_rate"] == 32000
assert d["metadata"]["derived_channel_count"] == 2
assert d["xma"]["status"] == "decode_failed"
assert d["wav"]["status"] == "failed"
assert d["wav"].get("partial_output_removed") is True
print("APF_AUDIO_EXPECTED_BLOCKER_CHECK_PASS")
' "$temporary/cheer-front_01.json"

echo "APF_AUDIO_VALIDATION_PASS"
echo "audo_records=2261"
echo "xma1_packets=30524"
echo "encoded_bytes=62513152"
echo "ausb_substreams=45514"
echo "ausb_external_bytes=1144270848"
