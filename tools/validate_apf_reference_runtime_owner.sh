#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

canonical_dir='reports/cut_content/apf_nfl_lineage/reference_runtime_owner'
canonical_report='reports/cut_content/apf_nfl_lineage/reference_runtime_owner.json'
temporary=$(mktemp -d /tmp/apf-reference-runtime-owner.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

apf_trace="$canonical_dir/apf_reference_runtime_owner_trace.txt"
apf_pseudo="$canonical_dir/apf_reference_runtime_owner_pseudo_c.c"
nfl_trace="$canonical_dir/nfl_reference_runtime_owner_trace.txt"
nfl_pseudo="$canonical_dir/nfl_reference_runtime_owner_pseudo_c.c"

if [[ ${REFERENCE_RUNTIME_OWNER_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/apf" "$temporary/nfl"
  ghidra='tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless'
  test -x "$ghidra"
  HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfReferenceRuntimeOwnerAudit.java "$temporary/apf" \
      > "$temporary/apf-ghidra.log" 2>&1
  HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    "$ghidra" "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflReferenceRuntimeOwnerAudit.java "$temporary/nfl" \
      > "$temporary/nfl-ghidra.log" 2>&1
  cmp "$apf_trace" "$temporary/apf/apf_reference_runtime_owner_trace.txt"
  cmp "$apf_pseudo" "$temporary/apf/apf_reference_runtime_owner_pseudo_c.c"
  cmp "$nfl_trace" "$temporary/nfl/nfl_reference_runtime_owner_trace.txt"
  cmp "$nfl_pseudo" "$temporary/nfl/nfl_reference_runtime_owner_pseudo_c.c"
  apf_trace="$temporary/apf/apf_reference_runtime_owner_trace.txt"
  apf_pseudo="$temporary/apf/apf_reference_runtime_owner_pseudo_c.c"
  nfl_trace="$temporary/nfl/nfl_reference_runtime_owner_trace.txt"
  nfl_pseudo="$temporary/nfl/nfl_reference_runtime_owner_pseudo_c.c"
  mode=full
else
  mode=normal
fi

python3 tools/apf_reference_runtime_owner.py \
  --apf-trace "$apf_trace" --apf-pseudo "$apf_pseudo" \
  --nfl-trace "$nfl_trace" --nfl-pseudo "$nfl_pseudo" \
  --output "$temporary/reference_runtime_owner.json"
cmp "$canonical_report" "$temporary/reference_runtime_owner.json"

python3 - "$canonical_report" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "apf_reference_runtime_owner/v1"
assert report["apf"]["classification"] == "statically_orphaned_retail_content"
assert report["apf"]["generic_refr_handler"]["registered_during_normal_boot"] is True
owner = report["apf"]["reference_owner_code"]
assert owner["loader_static_incoming_refs"] == 0
assert owner["accessor_static_incoming_refs"] == [0, 0, 0]
assert owner["accessor_fullword_occurrences"] == [0, 0, 0]
assert owner["accessor_address_materializations"] == [0, 0, 0]
scan = report["apf"]["serialized_assets"]
assert scan["pack_count"] == 4
assert scan["total_bytes_scanned"] == 3_873_511_424
outer = scan["hash_occurrences"]["reference_iff_crc32_upper_ascii"]
assert len(outer["big_endian"]) == 1 and not outer["little_endian"]
assert outer["big_endian"][0]["pack_offset"] == "0x0000358c"
assert outer["big_endian"][0]["owner"] is None
assert report["nfl"]["extras_source_row"]["label"] == "Reference Guide"
assert report["nfl"]["reference_descriptor"]["event_1_callback"] == "0x003707c0"
assert report["nfl"]["reference_descriptor"]["event_2_callback"] == "0x003708b0"
assert report["cross_title_result"].endswith("removed the owner route.")
PY

test "$(md5sum 'extracted/All-Pro Football 2K8 (USA)/default.xex' | cut -d' ' -f1)" = \
  217eea6084c3d03f0f1143802b1f5636
test "$(md5sum 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | cut -d' ' -f1)" = \
  444064a9ec984dd29d2c05a43f5c96e8

printf 'APF_REFERENCE_RUNTIME_OWNER_VALIDATION_PASS mode=%s apf=statically_orphaned nfl=menu_owned packs=4 bytes=3873511424 originals_unchanged=true\n' "$mode"
