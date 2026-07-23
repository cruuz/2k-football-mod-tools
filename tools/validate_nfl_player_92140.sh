#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

temporary=$(mktemp -d /tmp/nfl-player-92140-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 -m py_compile \
  tools/nfl_player_92140_native_validate.py \
  tools/nfl_player_92140_xbe_oracle.py

python3 - <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import re

source = Path("src/recovered/nfl2k5/player_local_postprocess.c").read_text(encoding="utf-8")
header = Path("include/recovered/nfl2k5/player_local_postprocess.h").read_text(encoding="utf-8")
with Path("reports/assets/nfl_player_postprocess_calls.tsv").open(
    encoding="utf-8", newline=""
) as stream:
    expected = [
        (int(row["sequence"]), int(row["callsite"], 16))
        for row in csv.DictReader(stream, delimiter="\t")
        if row["owner"] == "0x00092140"
    ]

actual = [
    (int(sequence), int(address, 16))
    for sequence, address in re.findall(
        r"vc_trace\(observer, observer_user_data,\s*(\d+)u,\s*"
        r"UINT32_C\(0x([0-9a-fA-F]+)\)\);",
        source,
    )
]
assert len(expected) == 127
assert expected == actual
assert [sequence for sequence, _address in actual] == list(range(1, 128))
assert "VC_NFL_PLAYER_92140_OPERATION_COUNT 127u" in header
for address in ("0x0008D630", "0x00020B20/0x0008D550", "0x00091D90/0x00091E70/0x00091F60"):
    assert f"PORTME({address})" in header
assert "PORTME(0x0008D630)" in source

report = json.loads(
    Path("reports/assets/nfl_player_92140_native.json").read_text(encoding="utf-8")
)
assert report["schema"] == "nfl2k5_player_92140_native/v1"
assert report["executable"]["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert report["ordered_graph"]["helper_call_count"] == 127
assert report["matrix_contract"]["all_high_lanes_have_a_writer"] is True
assert report["matrix_contract"]["low_input_is_unchanged"] is True
assert report["validation"]["bit_identity_claimed"] is False
for path, digest in report["portable_artifacts"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
for key in ("calls", "constants", "transforms"):
    path = Path(report["ordered_graph"][f"{key}_tsv"])
    expected_digest = report["ordered_graph"][f"{key}_tsv_sha256"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_digest
print("NFL_PLAYER_92140_ORDERED_GRAPH_STATIC_PASS operations=127")
PY

common=(
  -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Wconversion -Wshadow
  -Wstrict-prototypes -ffp-contract=off -Iinclude
)

gcc "${common[@]}" \
  src/recovered/nfl2k5/player_local_postprocess.c \
  tests/nfl_player_local_postprocess_test.c \
  -lm -o "$temporary/player-92140-gcc"
"$temporary/player-92140-gcc"

clang-18 "${common[@]}" \
  src/recovered/nfl2k5/player_local_postprocess.c \
  tests/nfl_player_local_postprocess_test.c \
  -lm -o "$temporary/player-92140-clang"
"$temporary/player-92140-clang"

gcc "${common[@]}" -fPIC -shared \
  src/recovered/nfl2k5/player_local_postprocess.c \
  -lm -o "$temporary/libplayer-92140-gcc.so"
PYTHONPATH=tools python3 tools/nfl_player_92140_native_validate.py \
  --library "$temporary/libplayer-92140-gcc.so"

clang-18 "${common[@]}" -fPIC -shared \
  src/recovered/nfl2k5/player_local_postprocess.c \
  -lm -o "$temporary/libplayer-92140-clang.so"
PYTHONPATH=tools python3 tools/nfl_player_92140_native_validate.py \
  --library "$temporary/libplayer-92140-clang.so"

gcc "${common[@]}" -O1 -g -fsanitize=undefined \
  -fno-sanitize-recover=all -fPIC -shared \
  src/recovered/nfl2k5/player_local_postprocess.c \
  -lm -o "$temporary/libplayer-92140-ubsan.so"
PYTHONPATH=tools python3 tools/nfl_player_92140_native_validate.py \
  --library "$temporary/libplayer-92140-ubsan.so"

if [[ ${NFL_PLAYER_92140_XBE_ORACLE:-0} == 1 ]]; then
  unicorn_path=${NFL_PLAYER_92140_UNICORN_PATH:-}
  oracle_pythonpath=tools
  if [[ -n $unicorn_path ]]; then
    oracle_pythonpath="$unicorn_path:$oracle_pythonpath"
  fi
  PYTHONPATH="$oracle_pythonpath" python3 tools/nfl_player_92140_xbe_oracle.py \
    --library "$temporary/libplayer-92140-gcc.so"
  PYTHONPATH="$oracle_pythonpath" python3 tools/nfl_player_92140_xbe_oracle.py \
    --library "$temporary/libplayer-92140-clang.so"
fi

echo NFL_PLAYER_92140_VALIDATION_PASS compilers=2 sanitizer=ubsan cases_per_run=8 operations=127
