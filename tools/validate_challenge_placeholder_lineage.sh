#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

nfl_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
apf_xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
report='reports/cut_content/apf_nfl_lineage/challenge_placeholder_lineage.json'

before_nfl="$(sha256sum "$nfl_xbe" | cut -d' ' -f1)"
before_apf="$(sha256sum "$apf_xex" | cut -d' ' -f1)"

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$tmp/xex_extract_pe"

"$tmp/xex_extract_pe" "$apf_xex" "$tmp/apf2k8_default.pe" >/dev/null

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  tools/challenge_placeholder_lineage.py

python3 tools/challenge_placeholder_lineage.py \
  --nfl-xbe "$nfl_xbe" \
  --nfl-header reports/headers/nfl2k5_xbe_header.json \
  --apf-xex "$apf_xex" \
  --apf-pe "$tmp/apf2k8_default.pe" \
  --json-out "$tmp/challenge_placeholder_lineage.json" \
  >"$tmp/generator.txt"

cmp "$report" "$tmp/challenge_placeholder_lineage.json"

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("reports/cut_content/apf_nfl_lineage/challenge_placeholder_lineage.json").read_text())
assert report["schema"] == "vc_challenge_placeholder_lineage/v1"
assert report["scope"]["read_only_static_audit"] is True
assert report["scope"]["runtime_visibility_claimed"] is False
assert report["scope"]["formal_nfl_2k6_proof_claimed"] is False
assert report["cross_title_findings"]["exact_challenge_copy_shared"] is True
assert report["cross_title_findings"]["challenge_copy_code_connected_in_both"] is True
assert report["cross_title_findings"]["hello_world_direct_static_callers_found"] is False
assert len(report["nfl2k5"]["bounded_call_chain"]) == 3
assert len(report["apf2k8"]["bounded_call_chain"]) == 2
assert report["nfl2k5"]["challenge_formatter"] == {
    "name": "challenge presentation formatter",
    "first": "0x001B1420",
    "after_last": "0x001B1500",
    "size": 224,
    "sha256": "cc8334016d5b6da4d8df60934a5e5c47c144de48f1e791091a4bfa1f2c722aad",
}
assert report["nfl2k5"]["hello_world_getter"]["direct_rel32_call_or_jump_sites_in_text"] == []
assert report["apf2k8"]["hello_world_getter"]["immediate_branch_sites_in_text"] == []
assert len(report["portme"]) == 4
PY

after_nfl="$(sha256sum "$nfl_xbe" | cut -d' ' -f1)"
after_apf="$(sha256sum "$apf_xex" | cut -d' ' -f1)"
test "$before_nfl" = "$after_nfl"
test "$before_apf" = "$after_apf"

echo "CHALLENGE_PLACEHOLDER_LINEAGE_VALIDATION_PASS challenge_shared=yes code_connected=yes hello_direct_callers=0 runtime=false nfl2k6_claim=false originals_unchanged=yes"
