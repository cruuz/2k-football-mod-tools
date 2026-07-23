#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

REPORT=reports/assets/nfl2k5_audo_wav_all.json
HASHES=reports/assets/nfl2k5_audo_wav_all.sha256

python3 -m py_compile tools/nfl_scene_probe.py
test "$(sha256sum "$REPORT" | cut -d' ' -f1)" = \
  08bc999ec2f2ca0af87933817e8e8fec912da2c2e43dbe1b3a4c70baee815b9f
test "$(sha256sum "$HASHES" | cut -d' ' -f1)" = \
  bf362c4a0e70eff61577130f3e20fdffd7f689a2d56bc768fb106a1b48170491

jq -e '
  .schema == "nfl2k5_scene_probe/v1" and
  .source_inventory == "reports/assets/nfl2k5_resource_chunks_v2.json" and
  .summary.record_count == 850 and
  .summary.status_counts == {"parsed":850} and
  .summary.audo_channel_counts == {"1":806,"2":44} and
  .summary.audo_codec_word_counts == {"0x00000011":850} and
  ([.records[].semantic.fully_read] | all(. == true)) and
  ([.records[].semantic.codec_inference] |
    all(. == "Xbox IMA ADPCM (high confidence)")) and
  ([.records[].wav_output] | unique | length) == 850
' "$REPORT" >/dev/null

sha256sum --check "$HASHES" >/dev/null

python3 - "$REPORT" <<'PY'
import json
import pathlib
import sys
import wave

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)

paths = []
pcm_bytes = 0
for record in report["records"]:
    semantic = record["semantic"]
    path = pathlib.Path(record["wav_output"])
    paths.append(path)
    with wave.open(str(path), "rb") as wav:
        assert wav.getcomptype() == "NONE"
        assert wav.getsampwidth() == 2
        assert wav.getnchannels() == semantic["channels"]
        assert wav.getframerate() == semantic["sample_rate"]
        assert wav.getnframes() == semantic["xbox_ima_block_count"] * 64
        pcm_bytes += wav.getnframes() * wav.getnchannels() * 2

assert len(paths) == len(set(paths)) == 850
assert len(list(pathlib.Path("assets/intermediate/nfl2k5/audio").glob("*.wav"))) == 850
assert pcm_bytes == 34_922_624
print("NFL2K5_FULL_AUDIO_VALIDATION_PASS files=850 pcm_bytes=34922624")
PY

bash tools/validate_nfl_audo_import_capacity_audit.sh
