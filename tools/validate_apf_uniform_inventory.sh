#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
report=reports/assets/apf_uniform_inventory.json
packages=reports/assets/apf_uniform_packages.tsv
textures=reports/assets/apf_uniform_textures.tsv
team_assets=reports/assets/apf_uniform_team_assets.tsv
logo_cache=reports/assets/apf_uniform_logo_cache.tsv
samples=reports/assets/apf_uniform_samples
trace=reports/assets/apf_uniform_ghidra/uniform_trace.txt
pseudo=reports/assets/apf_uniform_ghidra/uniform_focused_pseudo_c.c

for required in \
  "$index" tools/apf_uniform_inventory.py tools/apf_inner.py tools/apf_outer.py \
  tools/apf_roster.py tools/ghidra_scripts/apf/ApfUniformTrace.java \
  docs/research/apf_uniforms.md "$report" "$packages" "$textures" \
  "$team_assets" "$logo_cache" "$trace" "$pseudo" \
  reports/assets/apf_uniform.sha256; do
  test -f "$required"
done
test -d "$samples"

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile tools/apf_uniform_inventory.py
sha256sum --check reports/assets/apf_uniform.sha256

temporary=$(mktemp -d /tmp/apf-uniform-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/samples"

PYTHONDONTWRITEBYTECODE=1 python3 tools/apf_uniform_inventory.py "$index" \
  --report "$temporary/inventory.json" \
  --packages-tsv "$temporary/packages.tsv" \
  --textures-tsv "$temporary/textures.tsv" \
  --team-assets-tsv "$temporary/team-assets.tsv" \
  --logo-cache-tsv "$temporary/logo-cache.tsv" \
  --sample-dir "$temporary/samples"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/packages.tsv" "$packages"
cmp "$temporary/textures.tsv" "$textures"
cmp "$temporary/team-assets.tsv" "$team_assets"
cmp "$temporary/logo-cache.tsv" "$logo_cache"

mapfile -t canonical_pngs < <(
  find "$samples" -maxdepth 1 -type f -name '*.png' -printf '%f\n' | LC_ALL=C sort
)
mapfile -t regenerated_pngs < <(
  find "$temporary/samples" -maxdepth 1 -type f -name '*.png' -printf '%f\n' | LC_ALL=C sort
)
test "${#canonical_pngs[@]}" -eq 6
test "${canonical_pngs[*]}" = "${regenerated_pngs[*]}"
for png in "${canonical_pngs[@]}"; do
  cmp "$temporary/samples/$png" "$samples/$png"
done

python3 - "$report" <<'PY'
from collections import Counter
import json
from pathlib import Path
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert document["schema"] == "apf_uniform_inventory/v1"
assert document["summary"] == {
    "built_in_team_count": 24,
    "corresponding_bank_selector_record_pair_count": 560,
    "decoded_block_bytes": 644009624,
    "different_corresponding_bank_records_by_slot": {
        "4": 40, "6": 39, "7": 39, "8": 40,
        "9": 15, "11": 40, "12": 2, "13": 7,
    },
    "different_corresponding_bank_selector_record_pairs": 222,
    "family_count": 12,
    "identical_corresponding_bank_selector_record_pairs": 338,
    "inner_file_count": 1367,
    "known_family_package_mapping_count": 960,
    "known_filename_selector_use_count": 880,
    "logo_cache_aggregate_slot_count": 236,
    "logo_cache_contiguous_auxiliary_stream_size": 10355878,
    "logo_cache_directory_count": 1,
    "logo_cache_entry_count": 236,
    "non_txtr_inner_file_count": 35,
    "outer_stored_bytes": 132577280,
    "sample_png_count": 6,
    "selector_bank_count": 80,
    "selector_pointer_use_count": 1120,
    "team_config_record_count": 40,
    "team_count": 40,
    "teams_with_identical_bank_asset_index_vectors": 40,
    "texture_format_counts": {
        "4_4_4_4": 236, "DXN": 444, "DXT1": 508, "DXT4_5": 144,
    },
    "txtr_count": 1332,
    "txtr_vc_id_differs_from_iff_file_id": 22,
    "txtr_vc_id_matches_iff_file_id": 1310,
    "uniform_package_count": 517,
    "uniform_related_outer_resource_count": 518,
    "unique_referenced_selector_record_bytes": 373,
    "unique_referenced_selector_record_count": 1120,
}

families = document["family_specs"]
assert [(row["family"], row["catalog_count"], row["selector_slot"])
        for row in families] == [
    ("font", 11, 7), ("number", 24, 8), ("sock", 24, 12),
    ("shoe", 11, 10), ("glove", 3, 2), ("textlogo", 206, 6),
    ("logo", 118, 5), ("helmet", 24, 3), ("pants", 24, 9),
    ("jersey", 24, 4), ("shoulder", 24, 11),
    ("shoulder_normal", 24, 11),
]
expected_templates = {
    row["family"]: f"uniform_{row['family']}_{{0:D2}}.iff"
    for row in families
}
assert all(row["xex_template"] == expected_templates[row["family"]]
           for row in families)

packages = document["packages"]
assert len(packages) == 517
assert len({row["outer_name"] for row in packages}) == 517
assert len({row["outer_table_index"] for row in packages}) == 517
assert len({(row["family"], row["asset_index"]) for row in packages}) == 517
assert all(row["stored_name_id"] == row["computed_name_id"] for row in packages)
assert Counter(row["family"] for row in packages) == Counter({
    row["family"]: row["catalog_count"] for row in families
})
inner = [file for package in packages for file in package["files"]]
assert len(inner) == 1367
assert Counter(file["type_name"] for file in inner) == {
    "TXTR": 1332, "NumberFont": 24, "NameFont": 11,
}
txtr = [file for file in inner if file["type_name"] == "TXTR"]
assert Counter(file["txtr"]["format_name"] for file in txtr) == {
    "DXT1": 508, "DXT4_5": 144, "DXN": 444, "4_4_4_4": 236,
}
assert Counter(file["txtr"]["vc_file_id_matches_iff_file_id"]
               for file in txtr) == {True: 1310, False: 22}

teams = document["team_selector_graph"]["teams"]
assert len(teams) == 40
assert [team["team_index"] for team in teams] == list(range(40))
assert [team["config_record_index"] for team in teams] == list(range(40))
assert Counter(team["slot_kind"] for team in teams) == {
    "built_in_team": 24, "online_slot": 8, "user_slot": 8,
}
slot_families = {
    2: ["glove"], 3: ["helmet"], 4: ["jersey"], 5: ["logo"],
    6: ["textlogo"], 7: ["font"], 8: ["number"], 9: ["pants"],
    10: ["shoe"], 11: ["shoulder", "shoulder_normal"], 12: ["sock"],
}
family_limits = {row["family"]: row["catalog_count"] for row in families}
selector_indices = []
raw_values = set()
differences = Counter()
for team in teams:
    assert [bank["bank"] for bank in team["banks"]] == [0, 1]
    assert all([row["slot"] for row in bank["selectors"]] == list(range(14))
               for bank in team["banks"])
    first, second = (bank["selectors"] for bank in team["banks"])
    assert [row["asset_index_byte_0"] for row in first] == [
        row["asset_index_byte_0"] for row in second
    ]
    for slot, (left, right) in enumerate(zip(first, second)):
        if left["raw_record_hex"] != right["raw_record_hex"]:
            differences[slot] += 1
    for bank in team["banks"]:
        for selector in bank["selectors"]:
            selector_indices.append(selector["selector_record_index"])
            raw_values.add(selector["raw_record_hex"])
            slot = selector["slot"]
            assert selector["families"] == slot_families.get(slot, [])
            for family in selector["families"]:
                assert selector["asset_index_byte_0"] < family_limits[family]
assert len(selector_indices) == len(set(selector_indices)) == 1120
assert len(raw_values) == 373
assert differences == Counter({4: 40, 6: 39, 7: 39, 8: 40,
                               9: 15, 11: 40, 12: 2, 13: 7})

americans = teams[0]
assert (americans["display_name"], americans["abbreviation"]) == ("Americans", "PHI")
assert [[row["asset_index_byte_0"] for row in bank["selectors"][2:13]]
        for bank in americans["banks"]] == [[
    1, 1, 6, 30, 8, 2, 5, 6, 6, 5, 7,
]] * 2

cache = document["logo_cache"]
assert (cache["outer_table_index"], cache["outer_name_id"], cache["magic"]) == (
    171, "0x1c247977", "0xf0985030",
)
assert (cache["header_size"], cache["file_length"], cache["file_count"]) == (
    0x2924, 0x2924, 236,
)
assert cache["internal_cache_name"] == "uniform_logocache.cdf"
assert cache["aggregate_slot_count"] == 236
assert cache["contiguous_auxiliary_stream_size"] == 10355878
assert cache["zero_alignment_tail_bytes"] == 132
entries = cache["entries"]
assert len(entries) == 236
assert sorted(row["aggregate_slot"] for row in entries) == list(range(236))
assert {(row["catalog_index"], row["logo_level"]) for row in entries} == {
    (catalog, level) for catalog in range(118) for level in range(2)
}
for row in entries:
    catalog = row["catalog_index"]
    level = row["logo_level"]
    assert row["cache_name"] == f"{catalog:02d}_logo_l{level}"
    assert row["package_outer_name"] == f"uniform_logo_{catalog:02d}.iff"
    assert row["package_inner_name"] == f"logo_l{level}"

samples = document["representative_loose_pngs"]
assert len(samples) == 6
assert {row["family"] for row in samples} == {
    "jersey", "logo", "number", "pants", "shoulder", "textlogo",
}
assert all(row["team_index"] == 0 and row["bank"] == 0 for row in samples)
assert all("/" not in row["path"] for row in samples)
assert all(row.startswith("PORTME:") for row in document["portme"])
assert all(row.startswith("PORTME:") for row in cache["portme"])
print("APF_UNIFORM_JSON_INVARIANTS_PASS")
PY

test "$(wc -l < "$packages")" -eq 518
test "$(wc -l < "$textures")" -eq 1333
test "$(wc -l < "$team_assets")" -eq 1121
test "$(wc -l < "$logo_cache")" -eq 237

rg -q '^Program MD5: 217eea6084c3d03f0f1143802b1f5636$' "$trace"
rg -q '^0x845F1C44 value=uniform_logo_\{0:D2\}\.iff ' "$trace"
rg -q '^0x845F1D48 value=uniform_shoulder_normal_\{0:D2\}\.iff ' "$trace"
rg -q '^0x84687D88 rlwinm r11,r4,0x2,0x0,0x1d$' "$trace"
rg -q '^0x847080C8 addi r11,r4,0xe$' "$trace"
rg -q '^/\* 0x849D6BD0:' "$pseudo"
rg -q 'uniform_logocache\.iff' docs/research/apf_uniforms.md
rg -q 'PORTME' docs/research/apf_uniforms.md

if [[ ${APF_UNIFORM_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfUniformTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/uniform_trace.txt" "$trace"
  cmp "$temporary/ghidra/uniform_focused_pseudo_c.c" "$pseudo"
  echo APF_UNIFORM_GHIDRA_REGEN_PASS
fi

echo 'APF_UNIFORM_VALIDATION_PASS resources=518 packages=517 textures=1332 teams=40 selectors=1120 cache=236 samples=6'
