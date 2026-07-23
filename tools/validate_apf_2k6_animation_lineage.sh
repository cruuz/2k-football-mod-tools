#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
header='reports/headers/apf2k8_xex_report.json'
motion='reports/assets/nfl2k5_motion_inventory.json'
report='reports/cut_content/apf_nfl_lineage/apf_2k6_animation_lineage.json'
table='reports/cut_content/apf_nfl_lineage/apf_2k6_animation_identifiers.tsv'
doc='docs/research/apf_2k6_animation_lineage.md'

for required in "$xex" "$xbe" "$header" "$motion" "$report" "$table" \
  "$doc" tools/apf_2k6_animation_lineage.py tools/xex_extract_pe.cpp; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-2k6-lineage.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_2k6_animation_lineage.py

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$temporary/xex_extract_pe"

"$temporary/xex_extract_pe" "$xex" "$temporary/apf.pe" | \
  grep -F 'blocks=642 chunks=1648 lzx_bytes=37717546 image_bytes=54001664 window_size=32768'

python3 tools/apf_2k6_animation_lineage.py \
  --apf-pe "$temporary/apf.pe" \
  --apf-xex "$xex" \
  --apf-header "$header" \
  --nfl-xbe "$xbe" \
  --nfl-motion-inventory "$motion" \
  --json "$temporary/report.json" \
  --tsv "$temporary/identifiers.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/identifiers.tsv" "$table"

python3 - "$report" "$table" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, table_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_2k6_animation_lineage/v1"
assert report["result"] == {
    "apf_animation_identifier_count": 8850,
    "apf_unique_animation_identifier_count": 8849,
    "apf_2k6_animation_identifier_count": 519,
    "apf_2k6_unique_identifier_count": 519,
    "apf_2k6_pointer_reference_total": 597,
    "all_apf_2k6_identifiers_pointer_backed": True,
    "static_animation_definition_record_count": 5884,
    "static_animation_definition_record_size": 44,
    "apf_2k6_primary_definition_count": 309,
    "apf_2k6_paired_name_reference_count": 288,
    "apf_2k6_unique_animation_filename_count": 225,
    "all_apf_2k6_references_are_definition_name_fields": True,
    "nfl2k5_xbe_2k6_animation_identifier_count": 0,
    "nfl2k5_motion_catalog_2k6_name_count": 0,
    "formal_nfl_2k6_product_identity_proved": False,
    "runtime_consumption_of_every_identifier_proved": False,
}
assert report["annual_tag_counts"] == {
    "2K3": 26, "2K4": 168, "2K5": 453,
    "2K6": 519, "2K7": 195, "2K8": 3710,
}
assert report["registry_primary_annual_tag_counts"] == {
    "2K3": 13, "2K4": 102, "2K5": 296,
    "2K6": 309, "2K7": 122, "2K8": 2119,
}
assert report["category_counts"] == {
    "blocking": 159,
    "bump_and_run": 69,
    "movement_and_cuts": 101,
    "quarterback": 124,
    "receiver_catch": 66,
}
assert report["pointer_reference_count_distribution"] == {
    "1": 450, "2": 60, "3": 9,
}
assert len(report["identifiers"]) == 519
assert len(report["portme"]) == 3
assert all(value.startswith("// PORTME") for value in report["portme"])

with table_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 519
assert [int(row["index"]) for row in rows] == list(range(519))
assert all(row["name"].startswith("ANM_") and "2K6" in row["name"] for row in rows)
assert all(int(row["pointer_reference_count"]) >= 1 for row in rows)
assert rows[0] == {
    "index": "0",
    "name": "ANM_BLOCK_2K6_PASS_LOW_B(0)",
    "category": "blocking",
    "pe_offset": "0x02548A9C",
    "virtual_address": "0x84548A9C",
    "pointer_reference_count": "1",
    "primary_definition_count": "1",
    "paired_name_reference_count": "0",
    "definition_record_addresses": "0x84D7E6C0",
    "animation_filenames": "cb300_fa_ply_01.ani",
    "pointer_reference_addresses": "0x84D7E6C4",
}

for value in report["sources"].values():
    path = Path(value["path"])
    data = path.read_bytes()
    assert len(data) == value["size"]
    assert hashlib.sha256(data).hexdigest() == value["sha256"]

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "519 distinct", "597 aligned", "2K6-era gameplay/animation lineage",
    "5,884", "225", "formal product identity", "NFL 2K6 build",
    "APF_2K6_ANIMATION_LINEAGE_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

echo 'APF_2K6_ANIMATION_LINEAGE_VALIDATION_PASS identifiers=519 pointers=597 annual_generations=6 nfl_product_identity=unproved'
