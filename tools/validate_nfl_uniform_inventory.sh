#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
inventory='reports/assets/nfl2k5_resource_chunks_v2.json'
txtr='reports/assets/nfl2k5_all_txtr_inventory_v2.tsv'
roster='reports/assets/nfl2k5_roster_teams.tsv'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
fresh=$(mktemp -d /tmp/nfl2k5-uniform-validate.XXXXXX)

python3 -m py_compile tools/nfl_uniform_inventory.py
python3 tools/nfl_uniform_inventory.py "$index" \
  --inventory "$inventory" \
  --txtr-tsv "$txtr" \
  --roster-teams "$roster" \
  --xbe "$xbe" \
  --output "$fresh/inventory.json" \
  --packages-tsv "$fresh/packages.tsv" \
  --tset-tsv "$fresh/tset.tsv" \
  --standalone-tsv "$fresh/standalone.tsv" \
  --name-metrics-tsv "$fresh/name.tsv" \
  --pairs-tsv "$fresh/pairs.tsv" \
  --codes-tsv "$fresh/codes.tsv" >/dev/null

cmp "$fresh/inventory.json" reports/assets/nfl2k5_uniform_inventory.json
cmp "$fresh/packages.tsv" reports/assets/nfl2k5_uniform_packages.tsv
cmp "$fresh/tset.tsv" reports/assets/nfl2k5_uniform_tset_textures.tsv
cmp "$fresh/standalone.tsv" reports/assets/nfl2k5_uniform_standalone_txtr.tsv
cmp "$fresh/name.tsv" reports/assets/nfl2k5_uniform_name_metrics.tsv
cmp "$fresh/pairs.tsv" reports/assets/nfl2k5_uniform_pairs.tsv
cmp "$fresh/codes.tsv" reports/assets/nfl2k5_uniform_codes.tsv
sha256sum -c reports/assets/nfl2k5_uniform.sha256 >/dev/null

PYTHONPATH=tools python3 - <<'PY'
import csv
import json
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path

base = Path("reports/assets")
report = json.loads((base / "nfl2k5_uniform_inventory.json").read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_uniform_inventory/v1"
assert report["summary"] == {
    "uniform_package_count": 634,
    "logical_pair_count": 317,
    "asset_code_count": 85,
    "home_package_count": 317,
    "away_package_count": 317,
    "tset_count": 6340,
    "tset_texture_reference_count": 32334,
    "standalone_txtr_count": 25994,
    "name_metric_count": 18386,
    "pair_logo_rgba_match_count": 317,
    "exact_unif_body_pair_match_count": 298,
    "exact_name_body_pair_match_count": 162,
    "unif_selector_08_counts": {"0": 32, "1": 295, "2": 43, "3": 107, "4": 157},
    "unif_selector_0c_counts": {"0": 453, "1": 16, "2": 135, "3": 24, "4": 6},
    "unif_scale_counts": {"0.25": 20, "0.600000024": 18, "1": 596},
    "unif_flag_14_counts": {"0": 384, "1": 250},
    "embedded_pngs_written": 0,
}
assert report["name_id_algorithm"]["matched_ids"] == 634
assert report["xbe_evidence"]["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert report["proved_layout"]["package_chunk_sequence"] == \
    "Unif, 10*TSET, 33*TXTR, NAME, 8*TXTR"
assert len(report["packages"]) == 634
assert all(item.startswith("PORTME:") for item in report["portme"])

def rows(name):
    with (base / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))

packages = rows("nfl2k5_uniform_packages.tsv")
pairs = rows("nfl2k5_uniform_pairs.tsv")
tsets = rows("nfl2k5_uniform_tset_textures.tsv")
standalone = rows("nfl2k5_uniform_standalone_txtr.tsv")
metrics = rows("nfl2k5_uniform_name_metrics.tsv")
codes = rows("nfl2k5_uniform_codes.tsv")
assert tuple(map(len, (packages, pairs, tsets, standalone, metrics, codes))) == \
    (634, 317, 32334, 25994, 18386, 85)

def name_id(name):
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF

assert [int(row["outer_index"]) for row in packages] == list(range(3613, 4247))
by_pair_side = {}
for row in packages:
    outer = int(row["outer_index"])
    name = row["logical_name"]
    side = row["side_code"]
    assert name == f"{int(row['asset_code']):02d}{side}{int(row['variant_id'])}.IFF"
    assert int(row["outer_id"], 16) == name_id(name)
    assert row["expected_name_id"] == row["outer_id"]
    assert row["side_context"] == {"H": "HOME", "A": "AWAY"}[side]
    assert int(row["pair_outer_index"]) == outer + (317 if side == "H" else -317)
    assert (row["pair_key"], side) not in by_pair_side
    by_pair_side[row["pair_key"], side] = row
    raw = bytes.fromhex(row["unif_raw_hex"])
    assert len(raw) == 0x50 and raw[:0x0C] == bytes(0x0C) and raw[0x0C:0x10] == b"Unif"
    assert struct.unpack_from("<ii", raw, 0x10) == (17, 29)
    assert raw[0x18:0x20] == bytes(8)
    assert raw[0x20:0x30].decode("utf-16le").rstrip("\0") == "uniform"
    assert raw[0x48:0x50] == bytes(8)
    assert struct.unpack_from("<I", raw, 0x44)[0] in (0, 1)
assert len(by_pair_side) == 634

assert all(row["logo_rgba_match"] == "True" for row in pairs)
assert Counter(row["unif_body_match"] for row in pairs) == {"True": 298, "False": 19}
assert Counter(row["name_body_match"] for row in pairs) == {"True": 162, "False": 155}
for row in pairs:
    assert int(row["away_outer_index"]) - int(row["home_outer_index"]) == 317
    assert row["home_logical_name"].replace("H", "A", 1) == row["away_logical_name"]
    assert int(row["tset_reference_count"]) == 51

tset_names = {
    1: ("jersey00", "jersey00_mud"),
    2: ("pants00", "pants00_mud"),
    3: ("sleeve00", "sleeve00_mud"),
    4: ("socks00", "socks00_mud"),
    5: tuple(n for i in range(1, 8) for n in (f"elbowpad{i:02d}", f"elbowpad{i:02d}_mud")),
    6: tuple(f"glove{i:02d}" for i in range(1, 9)),
    7: tuple(n for i in range(1, 4) for n in (f"longsleeve{i:02d}", f"longsleeve{i:02d}_mud")),
    8: tuple(n for i in (1, 4, 9) for n in (f"shoes{i:02d}", f"shoes{i:02d}_mud")),
    9: tuple(n for i in (2, 3, 10) for n in (f"shoes{i:02d}", f"shoes{i:02d}_mud")),
    10: ("wristband01", "wristband02", "wristband09"),
}
tset_group = defaultdict(list)
for row in tsets:
    assert row["format_name"] == "P8"
    assert (row["dimensions"], row["depth"]) == ("2", "1")
    assert len(row["base_pixel_sha256"]) == len(row["palette_bgra_sha256"]) == 64
    tset_group[int(row["outer_index"]), int(row["tset_chunk_index"])].append(row)
assert len(tset_group) == 6340
for (outer, chunk), group in tset_group.items():
    assert [int(row["reference_index"]) for row in group] == list(range(len(tset_names[chunk])))
    assert tuple(row["name"] for row in group) == tset_names[chunk]

standalone_names = {
    11: "helmet00", 12: "helmet02",
    **{13 + i: str(48 + i) for i in range(10)},
    **{23 + i: f"hn{48 + i}" for i in range(10)},
    **{33 + i: f"an{48 + i}" for i in range(10)},
    43: "names", 45: "bump_jersey", 46: "bump_sleeve", 47: "bump_pants",
    48: "bump_sock", 49: "logo", 50: "chiclet", 51: "splayer", 52: "flipchip",
}
standalone_group = defaultdict(list)
for row in standalone:
    assert row["outer_head"] == "Unif" and row["conversion_status"] == "base_level_supported"
    assert row["name"] == standalone_names[int(row["chunk_index"])]
    assert len(row["decoded_sha256"]) == len(row["rgba_sha256"]) == 64
    standalone_group[int(row["outer_index"])].append(row)
assert len(standalone_group) == 634
for group in standalone_group.values():
    assert [int(row["chunk_index"]) for row in group] == sorted(standalone_names)

metric_group = defaultdict(list)
for row in metrics:
    metric_group[int(row["outer_index"])].append(row)
assert len(metric_group) == 634
for group in metric_group.values():
    assert [int(row["metric_index"]) for row in group] == list(range(29))
    assert group[0]["characters"] == "'" and group[1]["characters"] == "-"
    assert group[2]["characters"] == "A/a" and group[27]["characters"] == "Z/z"
    assert group[28]["characters"] == "PORTME: unmapped index 28"

assert sum(int(row["pair_count"]) for row in codes) == 317
assert len({row["asset_code"] for row in codes}) == 85
assert packages[0]["logical_name"] == "00H0.IFF"
assert packages[317]["logical_name"] == "00A0.IFF"
assert packages[0]["style_display"] == "Current Uniform"

trace = (base / "nfl2k5_uniform_ghidra/uniform_trace.txt").read_text(encoding="utf-8")
disassembly = (base / "nfl2k5_uniform_ghidra/uniform_focused_disassembly.txt").read_text(encoding="utf-8")
pseudo = (base / "nfl2k5_uniform_ghidra/uniform_focused_pseudo_c.c").read_text(encoding="utf-8")
assert "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8" in trace
assert "SCALAR_Unif_COUNT=6" in trace
for address in ("0x00038570", "0x00043D20", "0x00063270", "0x0007BD91", "0x0008E830",
                "0x00090570", "0x000E3530", "0x0011A0AC", "0x00166490", "0x001C20B0"):
    assert address in trace
for instruction in (
    "0x00043D2A  8D 44 30 0F", "0x00063270  BA 10 07 B3 00",
    "0x0007BD91  68 58 33 E6 00", "0x00166420  8B C2",
    "0x00166450  56", "0x00166495  BA 55 6E 69 66",
):
    assert instruction in disassembly
assert "// PORTME: could not decompile function at 0x00166420" in pseudo
assert "// PORTME: could not decompile function at 0x00166450" in pseudo

print("NFL2K5_UNIFORM_REPORT_ASSERTIONS_OK")
PY

PNG_DIR="$fresh/png" PYTHONPATH=tools python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

from nfl_outer import parse_archive
from nfl_uniform_inventory import (
    logical_name_candidates,
    parse_tset,
    read_and_validate_span,
)

archive = parse_archive(Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
inventory = json.loads(Path("reports/assets/nfl2k5_resource_chunks_v2.json").read_text())
items = sorted(
    (item for item in inventory["chunks"] if item["outer_index"] == 3613),
    key=lambda item: item["chunk_index"],
)
assert len(items) == 53 and [item["chunk_index"] for item in items] == list(range(53))
logical = logical_name_candidates()[archive.entries[3613].name_id]
assert logical.name == "00H0.IFF"
target = Path(os.environ["PNG_DIR"])
created = 0
for item in items[1:11]:
    record, _, body, _ = read_and_validate_span(archive, item)
    _, _, count = parse_tset(body, record, logical, target)
    created += count
pngs = sorted((target / "00H0").glob("*.png"))
assert created == len(pngs) == 51
assert all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in pngs)
smoke = target / "00H0/tset_01_00_jersey00.png"
assert hashlib.sha256(smoke.read_bytes()).hexdigest() == \
    "e9685834106ce9f592aef5fa6cb4031c83330eb66e0ee850471c0499f6d5ba3c"
print("NFL2K5_UNIFORM_PNG_SMOKE_OK count=51")
PY

echo "NFL2K5_UNIFORM_VALIDATION_OK temp=$fresh"
