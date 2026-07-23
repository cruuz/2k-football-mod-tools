#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
volume='extracted/All-Pro Football 2K8 (USA)/0A'
vendor='tools/vendor/XenonRecomp'
opcode_patch='reports/static_recomp/apf2k8_opcode_candidates_composed.patch'
switch_patch='reports/static_recomp/apf2k8_switch_tail_dispatch_candidate.patch'
switches='reports/static_recomp/apf2k8_xenon_switch_tables_switch_tail_candidate.toml'
config='reports/static_recomp/apf2k8_xenonrecomp_opcode_switch_composed.toml'
canonical_log='reports/static_recomp/apf2k8_xenonrecomp_opcode_switch_composed.log'
generated='build-static-recomp-apf/ppc-opcode-switch-composed'
tool='tools/apf_static_recomp_opcode_switch_composed.py'
report='reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json'
doc='docs/research/apf_static_recomp_opcode_switch_composed.md'

for required in \
    "$xex" "$volume" "$opcode_patch" "$switch_patch" "$switches" \
    "$config" "$canonical_log" "$tool" "$report" "$doc" \
    "$generated/ppc_func_mapping.cpp" "$generated/ppc_context.h" \
    "$generated/ppc_recomp_shared.h" \
    "$vendor/XenonRecomp/recompiler.cpp" \
    "$vendor/XenonUtils/ppc_context.h"; do
  test -f "$required"
done

case "$root" in
  /media/noah/Storage/*) ;;
  *) echo 'canonical workspace is not on /media/noah/Storage' >&2; exit 1 ;;
esac
test "$(command -v clang++-18)" = '/usr/bin/clang++-18'
test "$(command -v ld.lld-18)" = '/usr/bin/ld.lld-18'
test "$(git -C "$vendor" rev-parse HEAD)" = \
  'ddd128bcca99fe8bfbb99bea583c972351fa6ace'
git -C "$vendor" diff --quiet HEAD --
git -C "$vendor" diff --cached --quiet HEAD --

test "$(sha256sum "$xex" | cut -d' ' -f1)" = \
  '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
test "$(sha256sum "$volume" | cut -d' ' -f1)" = \
  'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$(sha256sum "$opcode_patch" | cut -d' ' -f1)" = \
  '5a6f15ebb3ff6c0ae2735e370b04e93033cd6d493be0a7a2697379d63e6f26bd'
test "$(sha256sum "$switch_patch" | cut -d' ' -f1)" = \
  '50bd52395e1510dfee9b33fedf6f65b1bc6583fa4266cf1150d15530431b7007'
test "$(sha256sum "$switches" | cut -d' ' -f1)" = \
  '07de9ad5d78cf363449291ed37d5a312c6245816ac0d3ae3a0754c961deeb759'
test "$(sha256sum "$config" | cut -d' ' -f1)" = \
  'dfd0cbc750bf3f6560e3a3e3002065b94715fba845ac92808789d6b9a8978423'

tree_summary() {
  python3 - "$1" <<'PY'
from pathlib import Path
import hashlib
import sys

directory = Path(sys.argv[1])
files = sorted((path for path in directory.iterdir() if path.is_file()),
               key=lambda path: path.name)
state = hashlib.sha256()
total = 0
for path in files:
    data = path.read_bytes()
    state.update(path.name.encode() + b"\0")
    state.update(len(data).to_bytes(8, "big"))
    state.update(hashlib.sha256(data).digest())
    total += len(data)
print(len(files), total, state.hexdigest())
PY
}

originals_before=$(sha256sum "$xex" "$volume")
vendor_before=$(sha256sum \
  "$vendor/XenonRecomp/recompiler.cpp" \
  "$vendor/XenonUtils/ppc_context.h")
canonical_before=$(tree_summary "$generated")
test "$canonical_before" = \
  '240 130724396 33bd100b5a7b358dd651b4c55ace6b41c73f9d3552a6684cede299ae9ac9532f'

mkdir -p /media/noah/Storage/.codex-tmp
temporary=$(mktemp -d \
  /media/noah/Storage/.codex-tmp/apf-opcode-switch-composed.XXXXXX)
cleanup() {
  rm -rf "$temporary"
}
trap cleanup EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"
python3 -m py_compile "$tool"

# Compose only in a disposable clone. The canonical vendor checkout and all
# retail/generated inputs stay read-only for the entire validation.
cp -a --reflink=auto "$vendor" "$temporary/vendor"
git -C "$temporary/vendor" apply "$root/$opcode_patch"
git -C "$temporary/vendor" apply "$root/$switch_patch"
test "$(sha256sum "$temporary/vendor/XenonRecomp/recompiler.cpp" | cut -d' ' -f1)" = \
  'fc7cf1c7c322589085cdab2bb9dd3e15909ff3c08e6ba4af23af3e293f8dfd3e'
test "$(sha256sum "$temporary/vendor/XenonUtils/ppc_context.h" | cut -d' ' -f1)" = \
  '0c217483f60a4c70d15de1a2ac3a652bf753fc183c2deef4f04b1f8a4727ba52'

rm -rf "$temporary/vendor/build-composed"
CC=/usr/bin/clang-18 CXX=/usr/bin/clang++-18 cmake \
  -S "$temporary/vendor" -B "$temporary/vendor/build-composed" \
  -DCMAKE_BUILD_TYPE=Release > "$temporary/cmake.log"
cmake --build "$temporary/vendor/build-composed" \
  --target XenonRecomp -j12 > "$temporary/build.log"

mkdir "$temporary/config" "$temporary/out"
ln -s "$root/$xex" "$temporary/config/default.xex"
ln -s "$root/$switches" "$temporary/config/switches.toml"
python3 - "$config" "$temporary/config/candidate.toml" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
replacements = {
    '../../extracted/All-Pro Football 2K8 (USA)/default.xex': 'default.xex',
    '../../build-static-recomp-apf/ppc-opcode-switch-composed': '../out',
    'apf2k8_xenon_switch_tables_switch_tail_candidate.toml': 'switches.toml',
}
for old, new in replacements.items():
    assert source.count(old) == 1, old
    source = source.replace(old, new)
Path(sys.argv[2]).write_text(source, encoding="utf-8")
PY

"$temporary/vendor/build-composed/XenonRecomp/XenonRecomp" \
  "$temporary/config/candidate.toml" \
  "$temporary/vendor/XenonUtils/ppc_context.h" \
  > "$temporary/composed.log" 2>&1
cmp "$temporary/composed.log" "$canonical_log"

python3 - "$generated" "$temporary/out" <<'PY'
from pathlib import Path
import hashlib
import sys

canonical, rebuilt = map(Path, sys.argv[1:])

def rows(directory):
    return [
        (path.name, len(data := path.read_bytes()), hashlib.sha256(data).hexdigest())
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
        if path.is_file()
    ]

left = rows(canonical)
right = rows(rebuilt)
assert left == right
assert len(left) == 240
assert sum(name.endswith('.cpp') for name, _, _ in left) == 237
PY

python3 "$tool" \
  --generated "$temporary/out" \
  --logical-generated "$generated" \
  --log "$temporary/composed.log" \
  --patched-recompiler \
    "$temporary/vendor/XenonRecomp/recompiler.cpp" \
  --patched-context "$temporary/vendor/XenonUtils/ppc_context.h" \
  --temp-root "$temporary/link-temp" \
  --jobs 12 \
  --json "$temporary/report.json" | grep -F \
  'APF_STATIC_RECOMP_OPCODE_SWITCH_COMPOSED_PASS tus=237 syntax=237 objects=237 link=yes opcodes_unrecognized=0 switch_resolved=2261 switch_remaining=1076 frontier_residue=0 entry_authorized=0 entry_called=0 title_executed=no'
cmp "$temporary/report.json" "$report"

python3 - "$report" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")
assert report["schema"] == \
    "apf2k8_static_recomp_opcode_switch_composed/v1"
assert report["result"] == {
    "single_composed_derived_corpus_exists": True,
    "opcode_candidate_included": True,
    "switch_tail_candidate_included": True,
    "unrecognized_instruction_count": 0,
    "resolved_switch_tail_occurrences": 2261,
    "remaining_switch_portme_occurrences": 1076,
    "remaining_switch_unique_targets": 190,
    "generated_translation_units_syntax_passed": 237,
    "generated_translation_units_object_compiled": 237,
    "mapping_only_link_succeeded": True,
    "composed_derived_corpus_blocker_resolved": True,
    "entry_authorized": False,
    "title_entry_called": False,
    "translated_title_code_executed": False,
    "native_boot_proved": False,
    "architecture_complete": False,
}
corpus = report["generated_corpus"]
assert corpus["path"] == \
    "build-static-recomp-apf/ppc-opcode-switch-composed"
assert corpus["file_count"] == 240
assert corpus["cpp_translation_unit_count"] == 237
assert corpus["generated_implementation_count"] == 60397
assert corpus["dispatch_mapping_count"] == 60731
assert corpus["tree_sha256"] == \
    "33bd100b5a7b358dd651b4c55ace6b41c73f9d3552a6684cede299ae9ac9532f"
assert corpus["cpp_manifest_sha256"] == \
    "216e11b389a0da0c808bf7a7f598cf9210e481f90477a73eacb15ea37d120079"
assert len(corpus["files"]) == 240

frontier = report["first_entry_intersection"]
assert frontier["augmented_descended_generated_nodes"] == 426
assert frontier["frontier_callable_imports"] == 30
assert frontier["opcode_candidate_sites_in_frontier"] == 0
assert frontier["unresolved_switch_occurrences_in_frontier"] == 0
assert frontier["resolved_switch_tail_occurrences_in_frontier"] == 0
assert frontier["candidate_occurrences_in_preboundary_symbols"] == 0
assert frontier["entry_called"] is False

audit = report["compile_and_link_audit"]
syntax = audit["syntax"]
objects = audit["object_build"]
link = audit["link"]
assert syntax["translation_unit_count"] == syntax["passed_count"] == 237
assert syntax["failed_count"] == syntax["diagnostic_translation_unit_count"] == 0
assert len(syntax["outcomes"]) == 237
assert objects["generated_object_count"] == 237
assert objects["compiled_object_count"] == 239
assert objects["failed_count"] == objects["diagnostic_object_count"] == 0
assert len(objects["outcomes"]) == 239
assert link["link_succeeded"] is True
assert link["mapping_only_harness_return_code"] == 0
assert link["mapping_count_checked"] == 60731
assert link["undefined_guest_symbol_count"] == 0
assert link["fail_fast_callable_import_definitions"] == 334
assert link["host_libraries"] == ["libm"]
assert link["title_entry_called"] is False
assert link["translated_title_code_executed"] is False
assert report["sources"]["report_embeds_generated_source_or_title_bytes"] \
    is False
assert len(report["portme"]) == 5
assert all("PORTME" in row for row in report["portme"])
assert report_path.stat().st_size < 160000

for phrase in (
    "## Outcome", "## Worked", "## Failed or unproved",
    "## Blocking / PORTME", "237/237 passed", "60,397",
    "2,261", "1,076", "426-node frontier", "libm",
    "Entry authorization remains false", "not an APF boot",
    "APF_STATIC_RECOMP_OPCODE_SWITCH_COMPOSED_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

test "$(sha256sum "$xex" "$volume")" = "$originals_before"
test "$(sha256sum \
  "$vendor/XenonRecomp/recompiler.cpp" \
  "$vendor/XenonUtils/ppc_context.h")" = "$vendor_before"
test "$(tree_summary "$generated")" = "$canonical_before"
git -C "$vendor" diff --quiet HEAD --
git -C "$vendor" diff --cached --quiet HEAD --

echo 'APF_STATIC_RECOMP_OPCODE_SWITCH_COMPOSED_VALIDATION_PASS tus=237 syntax=237 objects=237 link=yes opcodes_unrecognized=0 switch_resolved=2261 switch_remaining=1076 frontier_residue=0 entry_authorized=0 entry_called=0 originals_unchanged=yes vendor_unchanged=yes title_executed=no'
