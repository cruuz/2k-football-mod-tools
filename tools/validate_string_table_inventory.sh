#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

python3 -m py_compile tools/string_table_inventory.py
tmp=$(mktemp -d /tmp/vc-string-table-validate.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

PYTHONPATH=tools python3 tools/string_table_inventory.py \
  --apf-index 'extracted/All-Pro Football 2K8 (USA)/0A' \
  --nfl-index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --json "$tmp/string_tables.json" \
  --tsv "$tmp/string_table_translation.tsv"

cmp "$tmp/string_tables.json" reports/assets/cross_title_string_tables.json
cmp "$tmp/string_table_translation.tsv" \
  reports/assets/cross_title_string_tables_id_translation.tsv

PYTHONPATH=tools python3 - <<'PY'
import csv
import json
from pathlib import Path

import string_table_inventory as strings

report = json.loads(
    Path("reports/assets/cross_title_string_tables.json").read_text(encoding="utf-8")
)
assert report["schema"] == "vc_cross_title_string_tables/v1"
assert report["summary"] == {
    "all_bodies_rebuild_byte_identically": True,
    "all_references_bounded": True,
    "all_string_pools_contiguous_and_fully_referenced": True,
    "apf_record_count": 1505,
    "apf_table_count": 2,
    "id_a_mapping_bijective": True,
    "id_b_mapping_bijective": True,
    "id_pair_mapping_bijective": True,
    "nfl_record_count": 1501,
    "nfl_table_count": 2,
    "primary_distinct_id_a_count": 219,
    "primary_distinct_id_b_count": 254,
    "primary_distinct_id_pair_count": 740,
    "primary_ordered_text_match_count": 1492,
    "primary_ordered_texts_identical": True,
    "primary_pool_entry_count": 1106,
    "primary_pools_identical": True,
    "primary_record_count": 1492,
    "shared_numeric_id_a_count": 0,
    "shared_numeric_id_b_count": 0,
}
assert len(report["tables"]) == 4
assert len(report["primary_translation"]) == 1492
assert len(report["id_a_bijection"]) == 219
assert len(report["id_b_bijection"]) == 254
assert len(report["id_pair_bijection"]) == 740
assert all(table["byte_identical_rebuild"] for table in report["tables"])
assert all("PORTME:" in item for item in report["portme"])

identities = {
    (item["platform"], item["outer_index"], item["inner_index"]): (
        item["name"], item["byte_size"], item["count"], item["pool_entry_count"]
    )
    for item in report["tables"]
}
assert identities == {
    ("apf2k8", 185, 20): ("artist_bio_english", 43136, 13, 13),
    ("apf2k8", 810, 87): ("strings", 160384, 1492, 1106),
    ("nfl2k5", 23, 65): ("strings", 160432, 1492, 1106),
    ("nfl2k5", 4248, 1): ("strings", 6080, 9, 9),
}
assert report["primary_translation"][0]["text"] == "Front Office"
assert report["primary_translation"][-1]["text"] == (
    "The most effective meetings have a consistent tone."
)

with Path(
    "reports/assets/cross_title_string_tables_id_translation.tsv"
).open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 1492
assert rows[0]["apf_id_a"] == "0xf0eb8ddc"
assert rows[0]["nfl_id_a"] == "0x59831791"

# Reparse the source bodies and independently invoke the serializer.  This is
# deliberately stronger than trusting the JSON flags produced above.
apf = strings.parse_apf(
    Path("extracted/All-Pro Football 2K8 (USA)/0A"), 64 * 1024 * 1024
)
nfl = strings.parse_nfl(
    Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"),
    Path("reports/assets/nfl2k5_resource_chunks_v2.json"),
)
assert len(apf) == len(nfl) == 2
assert all(strings.rebuild_table(table) == table.body for table in apf + nfl)

xbe = Path("extracted/ESPN NFL 2K5 (USA)/default.xbe").read_bytes()
def at(va: int, size: int) -> bytes:
    # Proven XBE .text mapping for this executable: file offset = VA - 0x10000.
    offset = va - 0x10000
    return xbe[offset : offset + size]

# STRG registration, including loader/body callbacks.
registration = bytes.fromhex(
    "566810921600ba53545247b98cb9bd00e81ba4edff"
    "68609216006850921600ba53545247b9a0b9bd008bf0"
    "e880a4edff23c65ec3"
)
assert at(0x00169270, len(registration)) == registration
assert at(0x00169250, 4) == bytes.fromhex("8d4120c3")  # lea eax,[ecx+0x20]; ret

# Lookup entry obtains STRG, and its return path computes
# text_pool_base + stored_code_unit_offset * 2.
lookup_entry = bytes.fromhex(
    "83ec0889542400689019e800ba53545247e8fab6edff8bc885c9750683c408c2"
)
lookup_return = bytes.fromhex("8b4cb1088b5424145f5e5d8d044a5b83c408c2")
assert at(0x001692D0, len(lookup_entry)) == lookup_entry
assert at(0x00169377, len(lookup_return)) == lookup_return
PY

echo 'STRING_TABLE_VALIDATION_PASS apf=2/1505 nfl=2/1501 matched=1492 pool=1106 id_pairs=740'
