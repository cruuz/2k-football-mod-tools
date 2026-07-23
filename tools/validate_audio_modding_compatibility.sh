#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

export PYTHONDONTWRITEBYTECODE=1
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

inputs=(
  reports/assets/nfl2k5_audo_wav_all.json
  reports/assets/nfl2k5_resource_chunks_v2.json
  extracted/ESPN\ NFL\ 2K5\ \(USA\)/vc_53450030/0
  reports/assets/apf_audio_inventory.json
  reports/assets/apf_audio_unique_decode.json
  reports/assets/apf_ausb_inventory.json
  reports/assets/scorebug_presentation_audit.json
  reports/cut_content/apf_nfl_lineage/wrapup_followup.json
)

sha256sum "${inputs[@]}" >"$temporary/before.sha256"
python3 -m py_compile tools/audio_modding_compatibility.py

expect_rejected() {
  local label=$1
  local expected=$2
  shift 2
  if python3 tools/audio_modding_compatibility.py "$@" \
      >"$temporary/$label.stdout" 2>"$temporary/$label.stderr"; then
    echo "audio compatibility unsafe output case unexpectedly succeeded: $label" >&2
    return 1
  fi
  rg -F -q -- "$expected" "$temporary/$label.stdout" "$temporary/$label.stderr"
}

touch "$temporary/existing.json" "$temporary/symlink-target"
mkdir "$temporary/real-parent"
ln -s "$temporary/symlink-target" "$temporary/symlink.json"
ln -s "$temporary/real-parent" "$temporary/linked-parent"

expect_rejected wrong_suffix "JSON output must use .json suffix" \
  --output "$temporary/wrong.txt" \
  --matrix "$temporary/wrong-matrix.tsv" \
  --banks "$temporary/wrong-banks.tsv"
expect_rejected existing_output "JSON output path must be absent and not a symlink" \
  --output "$temporary/existing.json" \
  --matrix "$temporary/existing-matrix.tsv" \
  --banks "$temporary/existing-banks.tsv"
expect_rejected symlink_output "JSON output path must be absent and not a symlink" \
  --output "$temporary/symlink.json" \
  --matrix "$temporary/symlink-matrix.tsv" \
  --banks "$temporary/symlink-banks.tsv"
expect_rejected symlink_parent "JSON output parent must be a non-symlink directory" \
  --output "$temporary/linked-parent/report.json" \
  --matrix "$temporary/linked-parent/matrix.tsv" \
  --banks "$temporary/linked-parent/banks.tsv"
expect_rejected missing_parent "JSON output parent must already exist" \
  --output "$temporary/missing/report.json" \
  --matrix "$temporary/missing/matrix.tsv" \
  --banks "$temporary/missing/banks.tsv"
expect_rejected duplicate_output "output paths must be distinct" \
  --output "$temporary/distinct.json" \
  --matrix "$temporary/duplicate.tsv" \
  --banks "$temporary/duplicate.tsv"
expect_rejected source_alias "an output aliases pinned input" \
  --output reports/assets/apf_audio_inventory.json \
  --matrix "$temporary/alias-matrix.tsv" \
  --banks "$temporary/alias-banks.tsv"

python3 tools/audio_modding_compatibility.py \
  --output "$temporary/compatibility.json" \
  --matrix "$temporary/compatibility.tsv" \
  --banks "$temporary/banks.tsv"
sha256sum "${inputs[@]}" >"$temporary/after.sha256"

cmp "$temporary/before.sha256" "$temporary/after.sha256"
cmp reports/assets/audio_modding_compatibility.json "$temporary/compatibility.json"
cmp reports/assets/audio_modding_compatibility.tsv "$temporary/compatibility.tsv"
cmp reports/assets/audio_modding_banks.tsv "$temporary/banks.tsv"

python3 - "$temporary/compatibility.json" "$temporary/compatibility.tsv" \
  "$temporary/banks.tsv" <<'PY'
import csv
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
with Path(sys.argv[2]).open(encoding="utf-8", newline="") as stream:
    matrix = list(csv.DictReader(stream, delimiter="\t"))
with Path(sys.argv[3]).open(encoding="utf-8", newline="") as stream:
    banks = list(csv.DictReader(stream, delimiter="\t"))

assert report["schema"] == "vc_audio_modding_compatibility/v1"
assert len(matrix) == 16
assert len(banks) == 41
assert {row["schema"] for row in matrix} == {"vc_audio_modding_matrix/v1"}
assert {row["schema"] for row in banks} == {"vc_audio_bank_inventory/v1"}

nfl = report["nfl2k5"]
assert nfl["standalone_audo"]["record_count"] == 850
assert nfl["standalone_audo"]["decoded_pcm_bytes"] == 34_922_624
assert nfl["streaming_banks"]["descriptor_count"] == 17
assert nfl["streaming_banks"]["substream_count"] == 53_571
assert nfl["bounded_writer"] == {
    "available": True,
    "codec": "deterministic Xbox IMA ADPCM, 89 x 36-byte blocks",
    "generic": False,
    "input": "strict RIFF PCM16LE mono 16000 Hz, exactly 5696 frames",
    "metadata": "wrapper, 128-byte system region, descriptor, and 12-byte unknown tail preserved",
    "output": "exclusively created layout-identical copied XISO",
    "runtime_visibility_proved": False,
    "target": "outer 3 / chunk 101 / menu-back_01",
}

apf = report["apf2k8"]
assert apf["standalone_audo"]["record_count"] == 2_261
assert apf["standalone_audo"]["decoder_verified_record_count"] == 2_229
assert apf["standalone_audo"]["decoder_blocked_record_count"] == 32
assert apf["standalone_audo"]["owned_overlay_sfx_count"] == 17
assert apf["standalone_audo"]["owned_overlay_outer_index"] == 1_410
assert apf["streaming_banks"]["descriptor_count"] == 20
assert apf["streaming_banks"]["substream_count"] == 45_514
assert apf["bounded_writer"]["available"] is False

assert report["claims"] == {
    "apf_audio_writeback_available": False,
    "apf_audo_wav_extract_partially_available": True,
    "apf_xma1_encoder_available": False,
    "direct_flac_import_available": False,
    "emulator_started": False,
    "nfl_generic_audo_import_available": False,
    "nfl_music_commentary_bank_import_available": False,
    "nfl_one_fixed_slot_wav_import_available": True,
    "nfl_standalone_audo_wav_extract_available": True,
    "retail_audio_in_report": False,
    "retail_original_modified": False,
    "runtime_visibility_tested": False,
}
assert len(report["portme"]) == 6
assert all(item.startswith("PORTME:") for item in report["portme"])
assert {row["status"] for row in matrix} >= {
    "proved", "copy-only writer", "blocked", "not tested"
}
assert sum(row["title"] == "nfl2k5" for row in banks) == 21
assert sum(row["title"] == "apf2k8" for row in banks) == 20

doc = Path("docs/research/audio_modding_compatibility.md").read_text(encoding="utf-8")
normalized = " ".join(doc.lower().split())
for phrase in (
    "one exact slot has a copy-only wav writer",
    "no writeback is authorized",
    "not a generic `audo` editor",
    "no legally usable, bitstream-validated xma1 encoder",
    "lineage matches, not interchangeable serialized payloads",
):
    assert phrase in normalized, phrase
PY

echo "AUDIO_MODDING_COMPATIBILITY_VALIDATION_PASS matrix=16 banks=41 nfl_fixed_writer=1 apf_writer=0 runtime=false originals_unchanged=yes"
