#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
report=reports/assets/apf_fsmr_inventory.json
table_a=reports/assets/apf_fsmr_table_a.tsv
table_b=reports/assets/apf_fsmr_table_b.tsv
dump=reports/assets/apf_fsmr_crowdren1.bin
trace=reports/assets/apf_fsmr_ghidra/fsmr_trace.txt
pseudo=reports/assets/apf_fsmr_ghidra/fsmr_focused_pseudo_c.c

for required in \
  "$index" tools/apf_fsmr.py tools/ghidra_scripts/apf/ApfFsmrTrace.java \
  docs/research/apf_fsmr.md "$report" "$table_a" "$table_b" "$dump" \
  "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile tools/apf_fsmr.py

temporary=$(mktemp -d /tmp/apf-fsmr-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 tools/apf_fsmr.py "$index" \
  --report "$temporary/inventory.json" \
  --table-a-tsv "$temporary/table_a.tsv" \
  --table-b-tsv "$temporary/table_b.tsv" \
  --dump "$temporary/crowdren1.bin"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/table_a.tsv" "$table_a"
cmp "$temporary/table_b.tsv" "$table_b"
cmp "$temporary/crowdren1.bin" "$dump"

test "$(sha256sum "$dump" | cut -d' ' -f1)" = \
  0b6dd34a79201186db707f38e72ceda4033f3bdc3a63b040cfa6b4626a46f4b4
test "$(wc -c < "$dump")" -eq 1792
test "$(wc -l < "$table_a")" -eq 31
test "$(wc -l < "$table_b")" -eq 48

python3 - "$report" <<'PY'
import json
from pathlib import Path
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert document["schema"] == "apf_fsmr_inventory/v1"
assert document["source"] == {
    "index_path": "extracted/All-Pro Football 2K8 (USA)/0A",
    "outer_table_index": 659,
    "outer_name_id": "0x6cb47fc1",
    "outer_stored_size": 16445440,
    "outer_stored_sha256": "7077a50912167a6c9ad06014277b9e838bb45e6d9d9dc10d5e0da5ec9f398177",
    "inner_index": 109,
    "inner_name": "crowdren1",
    "inner_type": "FSMR",
    "part_block_index": 0,
    "part_offset": 381312,
    "decoded_length": 1792,
    "decoded_sha256": "0b6dd34a79201186db707f38e72ceda4033f3bdc3a63b040cfa6b4626a46f4b4",
}
assert document["pointer_rule"] == (
    "target = pointer_field_offset + signed_be32(stored_value) - 1"
)
assert document["root"] == {
    "size": 8,
    "pointers": [
        {"field_offset": "0x0000", "stored_value": "0x00000009",
         "target": "0x0008", "target_label": "table_a"},
        {"field_offset": "0x0004", "stored_value": "0x000003c5",
         "target": "0x03c8", "target_label": "table_b"},
    ],
}
assert document["summary"] == {
    "resource_count": 1,
    "root_pointer_count": 2,
    "table_a_record_count": 30,
    "table_b_nonzero_record_count": 47,
    "zero_tail_length": 72,
}
assert document["table_a"]["offset"] == "0x0008"
assert document["table_a"]["end"] == "0x03c8"
assert document["table_a"]["stride"] == 32
assert len(document["table_a"]["records"]) == 30
assert all(row["be_words"][7] == "0x00000000" for row in document["table_a"]["records"])
assert document["table_b"]["offset"] == "0x03c8"
assert document["table_b"]["nonzero_end"] == "0x06b8"
assert document["table_b"]["stride"] == 16
assert len(document["table_b"]["records"]) == 47
assert all(row["be_words"][2] == "0x3f800000" for row in document["table_b"]["records"])
assert document["classification"]["result"].endswith("not a script VM")
assert document["worked"] and document["failed"] and document["portme"]
print("APF_FSMR_JSON_INVARIANTS_PASS")
PY

rg -q '^Program MD5: 217eea6084c3d03f0f1143802b1f5636$' "$trace"
rg -q '^0x820D2B74 raw=0x31734984 ' "$trace"
rg -q '^0x820D2C00 raw=0x84979058 ' "$trace"
rg -q '^0x84B1C718 blr ' "$trace"
rg -q '^0x8467D1BC lis r9,0x3173 ' "$trace"
rg -q '^0x8467D1C8 ori r9,r9,0x4984 ' "$trace"
rg -q '^0x84975EB8 lis r6,0x4f73 ' "$trace"
rg -q '^0x84975EC8 ori r6,r6,0xc815 ' "$trace"
rg -q '^0x84976020 bl 0x84759478 ' "$trace"
rg -q '^/\* 0x84758DD8:FSMR_TableEvaluator_Body ' "$pseudo"
rg -q '^/\* 0x84759478:FUN_84759478 ' "$pseudo"
rg -Fq '0x4f73c815,UNK_820d2b74' "$pseudo"
rg -Fq 'FUN_84759478(unaff_r29 + 0x2e4,*unaff_r27,unaff_r27[1],0);' "$pseudo"
rg -Fq '* 0x20 + iVar7' "$pseudo"
rg -Fq '* 0x10 + iVar8' "$pseudo"

if [[ ${APF_FSMR_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfFsmrTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/fsmr_trace.txt" "$trace"
  cmp "$temporary/ghidra/fsmr_focused_pseudo_c.c" "$pseudo"
  echo APF_FSMR_GHIDRA_REGEN_PASS
fi

echo 'APF_FSMR_VALIDATION_PASS resources=1 table_a=30 table_b=47 zero_tail=72'
