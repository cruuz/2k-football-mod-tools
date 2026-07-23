#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

tool='tools/apf_static_recomp_link_probe.py'
report='reports/static_recomp/apf2k8_static_recomp_link_probe.json'
doc='docs/research/apf_static_recomp_link_probe.md'
for required in "$tool" "$report" "$doc" \
    reports/headers/apf2k8_xex_report.json \
    reports/static_recomp/apf2k8_static_recomp_all_tus.json \
    build-static-recomp-apf/ppc-filtered/ppc_func_mapping.cpp; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-static-recomp-link-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile "$tool"

before=$(find .codex-tmp -maxdepth 1 -type d -name 'apf-link-probe-*' | wc -l)
python3 "$tool" --jobs 12 --json "$temporary/report.json"
after=$(find .codex-tmp -maxdepth 1 -type d -name 'apf-link-probe-*' | wc -l)
test "$before" -eq "$after"
cmp "$temporary/report.json" "$report"

python3 - "$report" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_recomp_link_probe/v1"
assert report["result"] == {
    "generated_cpp_object_count": 237,
    "support_object_count": 2,
    "compiled_object_count": 239,
    "compile_failure_count": 0,
    "link_succeeded": True,
    "mapping_only_harness_return_code": 0,
    "undefined_guest_symbol_count": 0,
    "fail_fast_import_definition_count": 334,
    "guest_import_semantics_implemented": False,
    "title_entry_called": False,
    "native_game_boot_proved": False,
}
assert report["toolchain"] == {
    "compiler": "clang++-18",
    "compiler_version_first_line": "Ubuntu clang version 18.1.3 (1ubuntu1)",
    "linker": "ld.lld-18",
    "linker_version": "Ubuntu LLD 18.1.3 (compatible with GNU linkers)",
    "compile_flags": ["-std=c++20", "-O0", "-c"],
    "link_flags": ["-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie"],
    "jobs": 12,
}
observation = report["build_observation"]
assert observation["total_object_bytes"] == 96113576
assert observation["temporary_executable_bytes"] == 78439080
assert observation["temporary_outputs_deleted"] is True
assert observation["executable_preserved"] is False
assert observation["mapping_count_checked_by_harness"] == 60731
boundary = report["import_boundary"]
assert boundary["callable_thunks"] == 334
assert boundary["imported_data_slots_not_satisfied_by_linking"] == 13
assert boundary["stub_behavior"] == "unconditional abort if any guest import is called"
assert boundary["stub_source_embedded_in_report"] is False
assert len(report["portme"]) == 4
assert all("PORTME" in row for row in report["portme"])

serialized = report_path.read_text(encoding="utf-8")
for forbidden in ("source_text", "replacement_bytes", "executable_path", "object_path"):
    assert forbidden not in serialized

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "237 generated APF C++ files", "zero unresolved",
    "definition unconditionally aborts", "Title entry calls",
    "not a title boot", "APF_STATIC_RECOMP_LINK_PROBE_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

echo 'APF_STATIC_RECOMP_LINK_PROBE_VALIDATION_PASS objects=239 link=yes guest_undefined=0 imports=334 title_entry=no runtime=no'
