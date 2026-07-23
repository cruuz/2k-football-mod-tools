#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

python3 -m py_compile tools/playbook_inventory.py
tmp=$(mktemp -d /tmp/vc-playbook-validate.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

PYTHONPATH=tools python3 tools/playbook_inventory.py \
  --apf-index 'extracted/All-Pro Football 2K8 (USA)/0A' \
  --nfl-index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --json "$tmp/playbooks.json" \
  --tsv "$tmp/playbook_records.tsv"

cmp "$tmp/playbooks.json" reports/assets/cross_title_playbook_inventory.json
cmp "$tmp/playbook_records.tsv" reports/assets/cross_title_playbook_records.tsv

python3 - <<'PY'
import csv
import json
from pathlib import Path
import zlib

report = json.loads(
    Path("reports/assets/cross_title_playbook_inventory.json").read_text(
        encoding="utf-8"
    )
)
assert report["schema"] == "vc_cross_title_playbook_inventory/v1"
assert report["summary"] == {
    "all_name_pointers_bounded": True,
    "all_name_pools_exact_and_fully_referenced": True,
    "all_play_slot_counts_equal_eleven": True,
    "all_route_references_bounded_and_node_aligned": True,
    "all_unused_named_record_capacity_padding_zero": True,
    "apf_category_count": 28,
    "apf_distinct_category_name_count": 28,
    "apf_distinct_formation_name_count": 163,
    "apf_distinct_play_name_count": 556,
    "apf_formation_count": 163,
    "apf_play_count": 586,
    "apf_playbook_count": 1,
    "apf_route_node_count": 4948,
    "nfl_category_count": 835,
    "nfl_distinct_category_name_count": 45,
    "nfl_distinct_formation_name_count": 185,
    "nfl_distinct_play_name_count": 1479,
    "nfl_formation_count": 1533,
    "nfl_play_count": 9251,
    "nfl_playbook_count": 37,
    "nfl_route_node_count": 91833,
    "shared_casefolded_category_name_count": 23,
    "shared_casefolded_formation_name_count": 114,
    "shared_casefolded_play_name_count": 428,
}
assert len(report["playbooks"]) == 38
assert len(report["shared_casefolded_names"]["categories"]) == 23
assert len(report["shared_casefolded_names"]["formations"]) == 114
assert len(report["shared_casefolded_names"]["plays"]) == 428
assert "ace" in report["shared_casefolded_names"]["formations"]
assert "strong iso" in report["shared_casefolded_names"]["plays"]
assert "field goal" in report["shared_casefolded_names"]["categories"]
assert all("PORTME:" in item for item in report["portme"])

apf = report["playbooks"][0]
assert (apf["platform"], apf["outer_index"], apf["inner_index"]) == (
    "apf2k8", 180, 0
)
assert apf["inner_name"] == "mpb"
assert apf["book_name"] == "MASTER"
assert apf["byte_size"] == 182096
assert apf["sha256"] == (
    "2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891"
)
assert apf["root_counts"] == {
    "category_count": 28,
    "formation_count": 163,
    "play_count": 586,
    "route_node_count": 4948,
}
assert apf["regions"]["formation_size"] == 0xB8
assert apf["regions"]["play_size"] == 0x64
assert apf["regions"]["route_node_size"] == 8
assert len(apf["name_pool"]) == 778

nfl = report["playbooks"][1:]
assert [book["outer_index"] for book in nfl] == list(range(307, 344))
assert [book["book_name"] for book in nfl] == [
    "ARZ", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL",
    "DEN", "DET", "Editor", "GB", "GEN", "HOU", "IND", "JAX", "KC",
    "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "OAK", "PHI", "PIT",
    "PRACTICE", "reference", "SD", "SEA", "SF", "STL", "TB", "TEN",
    "WAS", "WCO",
]
assert all(book["byte_size"] == 78736 for book in nfl)
assert all(book["regions"]["formation_size"] == 0xB4 for book in nfl)
assert all(book["regions"]["play_size"] == 0x60 for book in nfl)
assert all(book["regions"]["category_size"] == 0x10 for book in nfl)
assert all(book["regions"]["formation_aux_size"] == 0x50 for book in nfl)

for book in report["playbooks"]:
    counts = book["root_counts"]
    expected_names = (
        1 + counts["formation_count"] + counts["play_count"]
        + counts["category_count"]
    )
    assert len(book["name_pool"]) == expected_names
    route_count = counts["route_node_count"]
    assert len(book["route_node_blob_hex"]) == route_count * 8 * 2
    for play in book["plays"]:
        assert len(play["slots"]) == 11
        assert all(0 <= slot["route_node_index"] < route_count for slot in play["slots"])

with Path("reports/assets/cross_title_playbook_records.tsv").open(
    encoding="utf-8", newline=""
) as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 12396
assert sum(row["kind"] == "formation" for row in rows) == 1696
assert sum(row["kind"] == "play" for row in rows) == 9837
assert sum(row["kind"] == "category" for row in rows) == 863

xbe = Path("extracted/ESPN NFL 2K5 (USA)/default.xbe").read_bytes()
def at(va: int, size: int) -> bytes:
    # This XBE's complete .text mapping is file offset = VA - 0x10000.
    offset = va - 0x10000
    return xbe[offset : offset + size]

# PLAY registration and object callback marker.
registration = bytes.fromhex(
    "6810661600ba504c4159b91cb7bd00e8fccfedffc3"
)
marker_callback = bytes.fromhex(
    "8bca68b0651600baa0651600c7410c504c4159e808d8edffc20800"
)
assert at(0x00166690, len(registration)) == registration
assert at(0x001665F0, len(marker_callback)) == marker_callback

# Root self-relative relocations at +30/+60/+44/+48/+64/+68.
root_relocator = bytes.fromhex(
    "5355568bf18b463085c05774078d44302f894630"
    "8b466085c074078d4c305f894e60"
    "8b464485c074078d543043895644"
    "8b464885c074078d443047894648"
    "8b466485c074078d4c3063894e64"
    "8b466885c074078d543067895668"
)
assert at(0x000E0D90, len(root_relocator)) == root_relocator

# Per-play name followed by exactly eleven pointer fixups at +0c, stride 8.
play_relocator = bytes.fromhex(
    "8b0785c074068d4438ff89078d470cba0b000000eb038d4900"
    "8b0885c974068d4c01ff890883c0084a75ee"
)
assert at(0x000E0DF7, len(play_relocator)) == play_relocator

# Formation and category name loops prove 0xb4 and 0x10 strides.
formation_loop = bytes.fromhex(
    "8b463433ff85c0762233d28b46448b0c1003c285c97406"
    "8d4c01ff89088b46344781c2b40000003bf872e0"
)
category_loop = bytes.fromhex(
    "8b463c33ff85c0762133d28bff8b46648b0c1003c285c97406"
    "8d4c01ff89088b463c4783c2103bf872e3"
)
assert at(0x000E0E38, len(formation_loop)) == formation_loop
assert at(0x000E0E63, len(category_loop)) == category_loop

# Independent indexed accessors prove category/formation/play/aux strides.
assert at(0x000E05E0, 11) == bytes.fromhex("8bc28b5164c1e00403c2c3")
assert at(0x000E0660, 14) == bytes.fromhex("8bc28b514469c0b400000003c2c3")
assert at(0x000E06E0, 12) == bytes.fromhex("8d04528b5160c1e00503c2c3")
assert at(0x000E0830, 24) == bytes.fromhex(
    "85d27c11395134760c8d04928b5148c1e00403c2c333c0c3"
)

assert zlib.crc32(b"PLAY") & 0xFFFFFFFF == 0x681C330E
apf_pseudo = Path(
    "research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_16384_16639.c"
).read_text(errors="replace")
assert "/* APF2K8_FUNCTION 0x84AE8C40" in apf_pseudo
assert "0x33cdf8e3,0x681c330e" in apf_pseudo
assert "Function_84B16398" in apf_pseudo
PY

echo 'PLAYBOOK_VALIDATION_PASS apf=1/163/586/4948 nfl=37/1533/9251/91833 shared=23/114/428'
