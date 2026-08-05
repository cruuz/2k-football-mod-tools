#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
boundary='reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json'
catalog='reports/specs/nfl2k5_stadium_static_target_catalog.v1.json'
recipe_schema='reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json'
recipe='reports/asset_samples/nfl_scne/stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json'
native_dir='build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/native-nonidentity4'
pure_xiso='build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/ESPN-NFL-2K5-upper-deck-nonidentity4.xiso.iso'
pure_manifest='build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/xiso-workflow.json'
pure_verify='build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/xiso-verification.json'
runtime_authority='reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json'
control_xiso='build/nfl2k5-stadium-group36-geometry-xiso-20260713/ESPN-NFL-2K5-s42-visible-night-control.xiso.iso'
diagnostic_xiso='build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/ESPN-NFL-2K5-upper-deck-nonidentity4-s42-visible-night.xiso.iso'
diagnostic_manifest='build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/s42-workflow.json'
diagnostic_verify='build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/s42-verification.json'
closure='reports/specs/nfl2k5_upper_deck_subset_xiso_runtime_closure.v1.json'
runtime='reports/assets/nfl2k5_upper_deck_subset_xemu_runtime.v1.json'
doc='docs/research/nfl_upper_deck_subset_xiso_runtime.md'
temporary=$(mktemp -d "$root/.nfl-upper-deck-xiso-validate.XXXXXX")
trap 'rm -rf "$temporary"' EXIT

required=(
  "$source_xiso" "$index" "$boundary" "$catalog" "$recipe_schema" "$recipe"
  "$native_dir/9" "$native_dir/manifest.json"
  "$pure_xiso" "$pure_manifest" "$pure_verify"
  "$runtime_authority" "$control_xiso"
  "$diagnostic_xiso" "$diagnostic_manifest" "$diagnostic_verify"
  "$closure" "$runtime" "$doc"
  tools/nfl_stadium_upper_deck_subset_xiso_patch.py
  tools/nfl_stadium_upper_deck_subset_xiso_verify.py
  tools/nfl_stadium_upper_deck_s42_xiso_patch.py
  tools/nfl_stadium_upper_deck_s42_xiso_verify.py
  tests/test_nfl_stadium_upper_deck_subset_xiso.py
  tests/test_nfl_stadium_upper_deck_s42_xiso.py
)
for path in "${required[@]}"; do
  test -f "$path"
done

test "$(stat -c %s tools/nfl_stadium_upper_deck_subset_xiso_patch.py)" = 17125
test "$(sha256sum tools/nfl_stadium_upper_deck_subset_xiso_patch.py | cut -d' ' -f1)" = \
  '8d13c324c1cf46d29c69810a1421721eda66021986dbd674d3cd1dbbaffbf03c'
test "$(stat -c %s tools/nfl_stadium_upper_deck_subset_xiso_verify.py)" = 15734
test "$(sha256sum tools/nfl_stadium_upper_deck_subset_xiso_verify.py | cut -d' ' -f1)" = \
  'e22cc5476a65ee83457082a061e29a49dd15bd646dbc69ad0686c9e350c5d038'
test "$(stat -c %s tools/nfl_stadium_upper_deck_s42_xiso_patch.py)" = 19457
test "$(sha256sum tools/nfl_stadium_upper_deck_s42_xiso_patch.py | cut -d' ' -f1)" = \
  '2b04808c327da082109534916ccdcfc1141d746b3fd020f00baf47bdc8001f49'
test "$(stat -c %s tools/nfl_stadium_upper_deck_s42_xiso_verify.py)" = 18113
test "$(sha256sum tools/nfl_stadium_upper_deck_s42_xiso_verify.py | cut -d' ' -f1)" = \
  'a1c2513b48c5f06badbf5b33f0f3a751b7ba1673342f57d4ae5893a2db5144c8'
test "$(stat -c %s tests/test_nfl_stadium_upper_deck_subset_xiso.py)" = 7372
test "$(sha256sum tests/test_nfl_stadium_upper_deck_subset_xiso.py | cut -d' ' -f1)" = \
  '81ae789fc20f9cedb2cf9b10b030b23331e2ae0eec34824feecd6e12b3d1f912'
test "$(stat -c %s tests/test_nfl_stadium_upper_deck_s42_xiso.py)" = 4250
test "$(sha256sum tests/test_nfl_stadium_upper_deck_s42_xiso.py | cut -d' ' -f1)" = \
  '85a9d92b4b63121a1e7cb67970c571a75289d42504cdc7885f2cda19ba9f4850'

test "$(stat -c %s "$closure")" = 9320
test "$(sha256sum "$closure" | cut -d' ' -f1)" = \
  'a921dfd6b0abcafbcb341a81f6c1179e8f7252b5ec16bf2f58842f1654abf2b2'
test "$(stat -c %s "$runtime")" = 7849
test "$(sha256sum "$runtime" | cut -d' ' -f1)" = \
  'ca2fdcc324b0da6e63df23152ab04cf3ac35d7f30ab842b9146e0e75d6d23b8b'
test "$(stat -c %s "$doc")" = 5580
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  '0568a6a34497a30fe51d86e560bd4834f0ba25ebdda3da500c7982b4bbdd10c9'

PYTHONDONTWRITEBYTECODE=1 python3 - "$closure" "$runtime" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


root = Path.cwd()


def load_canonical(path: Path) -> dict:
    raw = path.read_bytes()
    value = json.loads(raw)
    expected = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    assert raw == expected, f"noncanonical JSON: {path}"
    return value


def verify_small_artifact(record: dict) -> None:
    path = root / record["path"]
    assert path.is_file() and not path.is_symlink(), path
    assert path.stat().st_size == record["size"], path
    if record["size"] <= 16 * 1024 * 1024:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"], path


closure = load_canonical(Path(sys.argv[1]))
runtime = load_canonical(Path(sys.argv[2]))
assert closure["schema"] == "nfl2k5_upper_deck_subset_xiso_runtime_closure/v1"
assert runtime["schema"] == "nfl2k5_upper_deck_subset_xemu_runtime/v1"
assert closure["claims"]["changed_count_disc_transport_proved"] is True
assert closure["claims"]["changed_count_archive_runtime_acceptance_proved"] is True
assert closure["claims"]["runtime_upper_deck_board_visibility_proved"] is False
assert closure["claims"]["original_xbox_hardware_proved"] is False
assert closure["claims"]["production_ready"] is False
assert runtime["claims"]["xemu_boot_proved"] is True
assert runtime["claims"]["changed_count_archive_runtime_acceptance_proved"] is True
assert runtime["claims"]["upper_deck_board_visibility_proved"] is False
assert runtime["runs"]["nonidentity4_changed_count"]["runtime"]["gameplay_pause_reached"] is True
assert runtime["runs"]["nonidentity4_changed_count"]["runtime"]["upper_deck_board_in_evidence_frame"] is False
assert closure["difference_ledger"]["changed_byte_count"] == 868180
assert closure["difference_ledger"]["changed_run_count"] == 27413
assert closure["difference_ledger"]["outside_authorized_span_exact"] is True
assert closure["format"]["native_edit"]["decoded_changed_byte_count"] == 64
assert closure["format"]["native_edit"]["source_vertex_count"] == 12
assert closure["format"]["native_edit"]["output_vertex_count"] == 4

for record in closure["artifacts"].values():
    for suffix in ("manifest", "output", "verification"):
        path_key = f"{suffix}_path"
        if path_key in record:
            verify_small_artifact({
                "path": record[path_key],
                "sha256": record[f"{suffix}_sha256"],
                "size": record[f"{suffix}_size"],
            })
    if set(record) == {"path", "sha256", "size"}:
        verify_small_artifact(record)

for run in runtime["runs"].values():
    for name, record in run["artifacts"].items():
        records = record if isinstance(record, list) else [record]
        for item in records:
            verify_small_artifact(item)

for path in (
    Path("build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/xiso-workflow.json"),
    Path("build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/xiso-verification.json"),
    Path("build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/s42-workflow.json"),
    Path("build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/s42-verification.json"),
):
    load_canonical(path)
PY

qemu-img check \
  .codex-tmp/nfl2k5-upper-deck-xemu-20260716/xbox_hdd-upper-deck.qcow2 >/dev/null
qemu-img check \
  .codex-tmp/nfl2k5-upper-deck-xemu-20260716/xbox_hdd-control-after-upper-deck.qcow2 >/dev/null

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_stadium_upper_deck_subset_xiso_patch.py \
  tools/nfl_stadium_upper_deck_subset_xiso_verify.py \
  tools/nfl_stadium_upper_deck_s42_xiso_patch.py \
  tools/nfl_stadium_upper_deck_s42_xiso_verify.py \
  tests/test_nfl_stadium_upper_deck_subset_xiso.py \
  tests/test_nfl_stadium_upper_deck_s42_xiso.py

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_nfl_stadium_upper_deck_subset_xiso \
  tests.test_nfl_stadium_upper_deck_s42_xiso >/dev/null

PYTHONDONTWRITEBYTECODE=1 python3 \
  tools/nfl_stadium_upper_deck_subset_xiso_verify.py \
  --source-xiso "$source_xiso" \
  --index "$index" \
  --boundary "$boundary" \
  --catalog "$catalog" \
  --recipe-schema "$recipe_schema" \
  --recipe "$recipe" \
  --subset-output-dir "$native_dir" \
  --output-xiso "$pure_xiso" \
  --manifest "$pure_manifest" >"$temporary/pure-verification.json"
cmp "$pure_verify" "$temporary/pure-verification.json"

PYTHONDONTWRITEBYTECODE=1 python3 \
  tools/nfl_stadium_upper_deck_s42_xiso_verify.py \
  --source-xiso "$control_xiso" \
  --runtime-authority "$runtime_authority" \
  --index "$index" \
  --boundary "$boundary" \
  --catalog "$catalog" \
  --recipe-schema "$recipe_schema" \
  --recipe "$recipe" \
  --subset-output-dir "$native_dir" \
  --output-xiso "$diagnostic_xiso" \
  --manifest "$diagnostic_manifest" >"$temporary/diagnostic-verification.json"
cmp "$diagnostic_verify" "$temporary/diagnostic-verification.json"

bash tools/validate_nfl_stadium_upper_deck_subset_patch.sh >/dev/null

echo 'NFL_UPPER_DECK_SUBSET_XISO_VALIDATION_PASS pure_xiso=7b718365b935e8b42dc4afcf98205b8ffe16ef71b4e58ad29238b3cfdbd4944c diagnostic_xiso=e46cf9ab97e0c3c55b24355947a0ca336523bc3ceb5402964af0bda35239012f target=3280/5/2648/1 vertices=12->4 decoded_changes=64 disc_changes=868180 runs=27413 outside_span_exact=true tests=12 native_tests=21 xemu_boot=true runtime_archive_acceptance=true board_visibility=false hardware=false production=false'
