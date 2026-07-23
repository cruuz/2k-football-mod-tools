#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_volume="$root/extracted/All-Pro Football 2K8 (USA)/0A"
report="$root/reports/assets/apf_jersey_family_layout.json"
tsv="$root/reports/assets/apf_jersey_family_layout.tsv"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/apf-jersey-family-validate.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  "$root/tools/apf_jersey_family_layout.py"

python3 "$root/tools/apf_jersey_family_layout.py" \
  --index "$source_volume" \
  --report "$tmp/apf_jersey_family_layout.json" \
  --tsv "$tmp/apf_jersey_family_layout.tsv"

cmp -- "$report" "$tmp/apf_jersey_family_layout.json"
cmp -- "$tsv" "$tmp/apf_jersey_family_layout.tsv"

python3 - "$report" "$tsv" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path = Path(sys.argv[1])
tsv_path = Path(sys.argv[2])
report = json.loads(report_path.read_text(encoding="utf-8"))
rows = list(csv.DictReader(tsv_path.open(encoding="utf-8"), delimiter="\t"))

assert report["schema"] == "apf_jersey_family_layout/v1"
source = report["source"]
expected_volume_sha = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
assert source["size"] == 1_140_850_688
assert source["sha256_before"] == expected_volume_sha
assert source["sha256_after"] == expected_volume_sha
assert source["size_mtime_ctime_unchanged"] is True
assert source["opened_for_write"] is False
assert source["copied_volume_used"] is False

equivalence = report["family_equivalence"]
assert equivalence["package_count"] == 24
for key in (
    "all_24_names_resolved_by_outer_crc",
    "all_complete_txtr_descriptors_identical",
    "all_iff_structures_two_blocks_one_file",
    "all_blocks_h7a_shift_8",
    "all_nine_level_layouts_identical",
    "all_retail_transports_bit_exact",
    "all_controlled_solid_rebuilds_fit_fixed_allocations",
):
    assert equivalence[key] is True
assert equivalence["minimum_original_allocation_slack"] == 110
assert equivalence["minimum_controlled_solid_allocation_slack"] == 1775

descriptor = equivalence["canonical_txtr_descriptor"]
assert descriptor["vc_file_id"] == "0x1ff6ec38"
assert (descriptor["width"], descriptor["height"]) == (1024, 1024)
assert descriptor["pitch_pixels"] == 1024
assert descriptor["format_name"] == "DXT4_5"
assert descriptor["endianness_name"] == "8in16"
assert descriptor["tiled"] is True
assert descriptor["swizzle_components"] == [0, 1, 2, 3]
assert descriptor["vc_base_data_length"] == 0x100000
assert descriptor["vc_mip_data_length"] == 0x60000
assert descriptor["mip_min_level"] == 0
assert descriptor["mip_max_level"] == 8
assert descriptor["packed_mips"] is True

layout = equivalence["canonical_nine_level_layout"]
assert len(layout) == 9
assert [item["data_offset"] for item in layout] == [
    0x000000,
    0x100000,
    0x140000,
    0x150000,
    0x154000,
    0x158000,
    0x15C000,
    0x15C000,
    0x15C000,
]
assert [item["allocation_length"] for item in layout] == [
    0x100000,
    0x40000,
    0x10000,
    0x4000,
    0x4000,
    0x4000,
    0x4000,
    0x4000,
    0x4000,
]
assert [
    (item["level"], item["origin_block_x"], item["origin_block_y"])
    for item in layout[6:]
] == [(6, 4, 0), (7, 2, 0), (8, 1, 0)]

expected_table_indices = [
    186, 216, 608, 535, 1420, 1277, 875, 1033,
    289, 119, 1274, 1399, 1048, 878, 196, 179,
    544, 628, 1375, 1292, 495, 671, 247, 128,
]
expected_offsets = [
    0x06B51800, 0x06B56800, 0x06B5D000, 0x06B64000,
    0x06B69000, 0x06B70800, 0x06B78000, 0x06B80000,
    0x06B87000, 0x06B8D800, 0x06B95000, 0x06B9A800,
    0x06BA1000, 0x06BA7800, 0x06BB2000, 0x06BBA800,
    0x06BC2000, 0x06BCA800, 0x06BD8800, 0x06BDF800,
    0x06BE8000, 0x06BF2800, 0x06BFB000, 0x06C03000,
]
expected_sizes = [
    20480, 26624, 28672, 20480, 30720, 30720, 32768, 28672,
    26624, 30720, 22528, 26624, 26624, 43008, 34816, 30720,
    34816, 57344, 28672, 34816, 43008, 34816, 32768, 14336,
]
expected_outer_hashes = [
    "a15b56eb5227707be63f4b7e020e509853eb5e545085deb501fcbf57e13e7073",
    "c5ca0e96916af41ef4a867f5b3cafa2fd481eac30eb3121789c33b250a9870cc",
    "5c1e588909024f2799fc72e43c4734246fd60ddcbe2362fec4ad15f176cf511f",
    "836d82a1b78f79d99ef43d161b01ab6fdd0c9f1ae3b88b9797f7a79fe5b3239f",
    "00c76bf9beb6f2e0e408f1621249d14a7142b7786e5f72b7c079653cb0f7e0de",
    "48ad1b824c553f64fe71f607b4b1e82f015bc152130e2af585ce6a8a5c226088",
    "9f4740ddbbcc86d1d7a880a50f12d9e2580e049633b9beb065fc193a78130ca2",
    "dbba289711a38c621188232e6a61c9ccdc265321b51660f8c5e506a0db249fe1",
    "507b6cc4947fc48e671acd46c38cc4a9dd19f65315c8dc24226ab974b080b4f6",
    "127bce7a8692a049e13cffa329353884d0d9c9288fd8e9cb3a8f83543bd51626",
    "6271db19528c17126dcc8b671feda89570570a4c14161869bb06d655d5727846",
    "c6431e12112ddc37d4a41cfbf40bdbc36d86a499262b3712c990e10b19d21835",
    "5b7f410fe644da641d2577e6930ccc5e88df45419c3139aa711b11e909dd3d2d",
    "49824b8cb566443d80b6d4358d113aa082e1cbd708819cfa51ccea8da10ccda6",
    "f485b7d7880289098bad006a3d767dfb63f8de9db2e8bdaa7d3e85ae1778fd70",
    "7e2f7ba97f2b404bda08e9ccff66694fe994efecbeb8ba1747ad4ce5a98e1704",
    "2b609e184052e74a4fb64aedc9e00ab2d5daf03f186f7a2ed2f1567e26472d5a",
    "e0a0eeb1501ba2a11ae9caa4cef9cbd26e4cb7df48a0d88e7e45c5515b6ec86e",
    "95116b56621ce992eefea5c0e55051bb28d977a2162f29bc268145b6f852e4ef",
    "11d3b3e278be124b05a73d214381afdc3ead12a62fd263d65582de3baa8f229c",
    "8518172b744e98225c7da5c53e647d989a9fbb25580510fb5e893695da5e1aa1",
    "e154898f02eb5935858a551d63f360dc0b44bf7114f70fd82ebb32489970d5de",
    "341c9ce0e6ea27b8eff92243f60a66675f34738d1e81e2a9eda3550fc65c7a49",
    "151c5b0c52f9734f705ad0949847ac0718bb08430108688d63e513a44c8b1ade",
]

jerseys = report["jerseys"]
assert len(jerseys) == len(rows) == 24
assert [item["asset_index"] for item in jerseys] == list(range(24))
assert [item["outer_table_index"] for item in jerseys] == expected_table_indices
assert [item["physical"]["pack_offset"] for item in jerseys] == expected_offsets
assert [item["outer_allocation"]["size"] for item in jerseys] == expected_sizes
assert [item["outer_allocation"]["sha256"] for item in jerseys] == expected_outer_hashes

for index, (item, row) in enumerate(zip(jerseys, rows)):
    assert item["outer_name"] == f"uniform_jersey_{index:02d}.iff"
    assert item["physical"]["pack_name"] == "0A"
    assert item["outer_allocation"]["slack_tail_all_zero"] is True
    assert item["iff"]["header_size"] == 120
    assert item["iff"]["block_count"] == 2
    assert item["iff"]["file_count"] == 1
    assert item["iff"]["warnings"] == []
    assert [block["h7a"]["shift"] for block in item["iff"]["blocks"]] == [8, 8]
    assert item["inner_file"]["index"] == 0
    assert item["inner_file"]["name"] == "jersey_color"
    assert item["inner_file"]["type_name"] == "TXTR"
    assert len(item["inner_file"]["parts"]) == 2
    assert item["txtr_descriptor"] == descriptor
    assert len(item["nine_level_layout"]) == 9
    assert all("linear_bc3_sha256" in level for level in item["nine_level_layout"])
    assert item["transport"]["retail_extract_reinsert_bit_exact"] is True
    assert item["transport"]["active_blocks_non_aliasing"] is True
    assert item["transport"]["packed_tail_origins_blocks"] == [[4, 0], [2, 0], [1, 0]]
    controlled = item["controlled_solid_rebuild_in_memory"]
    assert len(controlled["levels"]) == 9
    assert all(level["extract_after_insert_bit_exact"] for level in controlled["levels"])
    assert controlled["inactive_padding_bit_exact"] is True
    assert controlled["transport_bit_exact"] is True
    assert controlled["rebuilt_entry_length"] == item["outer_allocation"]["size"]
    assert controlled["fixed_outer_allocation"] is True
    assert controlled["iff"]["h7a_decode_encode_decode_exact"] is True
    assert controlled["iff"]["rebuilt_iff_reparsed"] is True
    assert controlled["iff"]["footer_bit_exact"] is True
    assert controlled["iff"]["unrelated_dram_part_preserved"] is True
    assert controlled["iff"]["allocation_slack_after"] >= 0
    assert controlled["entry_or_volume_written"] is False
    assert row["asset_index"] == str(index)
    assert row["allocation_sha256"] == expected_outer_hashes[index]
    assert row["retail_transport_bit_exact"] == "true"
    assert row["controlled_h7a_roundtrip_exact"] == "true"
    assert row["controlled_transport_bit_exact"] == "true"
    assert row["entry_or_volume_written"] == "false"

fixture = report["controlled_fixture"]
assert fixture["bc3_block_decode_exact"] is True
assert fixture["contains_retail_pixels"] is False
assert fixture["contains_replacement_entry_bytes"] is False
boundary = report["claim_boundary"]
assert boundary["structural_layout_generalizes_across_all_24_jerseys"] is True
assert boundary["in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24"] is True
assert boundary["general_writer_complete"] is False
assert boundary["runtime_visibility_proved"] is False
assert boundary["xenia_rendering_proved"] is False
assert boundary["xbox_360_hardware_rendering_proved"] is False
assert boundary["production_quality_bc3_encoder_proved"] is False
assert boundary["retail_or_copied_game_volume_written"] is False

# The evidence artifacts contain structure and hashes, never an encoded entry.
assert report_path.stat().st_size < 500_000
assert tsv_path.stat().st_size < 20_000
PY

echo "APF_JERSEY_FAMILY_LAYOUT_VALIDATION_PASS packages=24 levels=9 solid_in_memory=24 runtime_visibility=false"
