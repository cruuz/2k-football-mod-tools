#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

generated='build-static-recomp-apf/ppc-filtered'
vendor='tools/vendor/XenonRecomp'
tool='tools/apf_static_recomp_all_tus.py'
report='reports/static_recomp/apf2k8_static_recomp_all_tus.json'
timing1='reports/static_recomp/apf2k8_static_recomp_all_tus_timing_run1.json'
timing2='reports/static_recomp/apf2k8_static_recomp_all_tus_timing_run2.json'
doc='docs/research/apf_static_recomp_all_tus.md'

for required in \
    "$tool" "$report" "$timing1" "$timing2" "$doc" \
    "$generated/ppc_func_mapping.cpp" "$generated/ppc_config.h" \
    "$generated/ppc_recomp_shared.h" "$vendor/XenonUtils/ppc_context.h"; do
  test -f "$required"
done
test -d "$vendor/thirdparty/simde"
test "$(command -v clang++-18)" = '/usr/bin/clang++-18'

temporary=$(mktemp -d /tmp/apf-static-recomp-all-tus.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile "$tool"

python3 "$tool" \
  --jobs 12 \
  --timing-baseline "$timing1" \
  --timing-baseline "$timing2" \
  --json "$temporary/report.json"

cmp "$temporary/report.json" "$report"

python3 - "$report" "$timing1" "$timing2" "$doc" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

report_path, timing1_path, timing2_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))

assert report["schema"] == "apf2k8_static_recomp_all_tus/v1"
assert report["result"] == {
    "all_translation_units_passed": True,
    "failed_count": 0,
    "link_success_proved": False,
    "passed_count": 237,
    "runtime_or_native_boot_proved": False,
    "semantic_correctness_proved": False,
    "syntax_only": True,
    "translation_unit_count": 237,
}

compiler = report["compiler"]
assert compiler["requested"] == "clang++-18"
assert compiler["resolved_path"] == "/usr/lib/llvm-18/bin/clang"
assert compiler["version_first_line"] == \
    "Ubuntu clang version 18.1.3 (1ubuntu1)"
assert compiler["binary_sha256"] == \
    "8ef402d453d1ba4902e4ee0f0f847f6cfa01400c95aa43c24e97818b9c0e3f45"
assert compiler["flags"] == ["-std=c++20", "-O0", "-fsyntax-only"]
assert compiler["include_paths"] == [
    "build-static-recomp-apf/ppc-filtered",
    "tools/vendor/XenonRecomp/XenonUtils",
    "tools/vendor/XenonRecomp/thirdparty/simde",
]

inputs = report["inputs"]
assert inputs["vendor_commit"] == \
    "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
assert inputs["complete_generated_tree_sha256"] == \
    "6ac280d3fa0c6f016011ff176089ddbee4df4077c366a69623d9556db0e54599"
assert inputs["cpp_manifest_sha256"] == \
    "5e90f504e1291e3bcc2ba2e3688da07d44ba7b7bfbf10ac62beffb48d1e79132"
assert inputs["cpp_total_bytes"] == 128551508
manifest = inputs["translation_units"]
assert len(manifest) == 237
assert [row["name"] for row in manifest] == [
    "ppc_func_mapping.cpp", *[f"ppc_recomp.{index}.cpp" for index in range(236)]
]
assert all(set(row) == {"name", "size", "sha256"} for row in manifest)
assert all(len(row["sha256"]) == 64 for row in manifest)

diagnostics = report["diagnostics"]
assert diagnostics == {
    "counts_by_severity": {},
    "failing_translation_units": [],
    "translation_units_with_unparsed_stderr": 0,
}
outcomes = report["outcomes"]
assert len(outcomes) == 237
assert [row["name"] for row in outcomes] == [row["name"] for row in manifest]
for row in outcomes:
    assert row["return_code"] == 0
    assert row["stdout_empty"] and row["stderr_empty"]
    assert row["diagnostic_counts"] == {}
    assert row["first_diagnostics"] == []
    assert row["unparsed_stderr"] is False

timing = report["timing"]
assert timing["assessed"] and timing["stable"]
assert timing["observation_count"] == 2 and timing["jobs"] == 12
assert timing["stability_threshold_relative_span"] == 0.05
assert timing["wall_seconds"] == {
    "minimum": 29.890839,
    "maximum": 30.166497,
    "mean": 30.028668,
    "relative_span": 0.00918,
}
assert timing["child_total_cpu_seconds"] == {
    "minimum": 325.493108,
    "maximum": 329.326151,
    "mean": 327.409629,
    "relative_span": 0.011707,
}
for path in (timing1_path, timing2_path):
    observation = json.loads(path.read_text(encoding="utf-8"))
    assert observation["canonical"] is False
    assert observation["translation_unit_count"] == 237
    assert observation["jobs"] == 12

# The report may carry hashes and normalized diagnostic metadata, never code.
serialized = report_path.read_text(encoding="utf-8")
for forbidden in ("source_text", "source_excerpt", "caret_excerpt"):
    assert forbidden not in serialized
assert report_path.stat().st_size < 150_000

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "237/237 passed, 0 failed, 0 diagnostics",
    "128,551,508-byte generated C++ corpus",
    "29.890839–30.166497",
    "325.493108–329.326151",
    "syntax is not semantics or runtime",
    "3,337 cross-function switch violations",
    "APF_STATIC_RECOMP_ALL_TUS_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

echo 'APF_STATIC_RECOMP_ALL_TUS_VALIDATION_PASS total=237 passed=237 failed=0 diagnostics=0 syntax_only=yes semantics=no runtime=no'
