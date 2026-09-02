#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

static_gltf=assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_skin.gltf
static_bin=${static_gltf%.gltf}.bin
animated_gltf=assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.gltf
animated_bin=${animated_gltf%.gltf}.bin
report=reports/assets/apf_player_shadow_gltf_export.json
doc=docs/research/apf_player_shadow_gltf_export.md

for required in \
  "$static_gltf" "$static_bin" "$animated_gltf" "$animated_bin" \
  "$report" "$doc" \
  tools/apf_player_shadow_gltf.py \
  tools/validate_apf_player_shadow_gltf.py \
  tools/apf_player_shadow_assimp_validate.cpp \
  tests/apf_player_shadow_runtime_test.c \
  tests/apf_player_shadow_screenshot_test.py \
  tests/recovered_menu_screenshot_test.py \
  CMakeLists.txt \
  assets/intermediate/apf2k8/models/1310_0415_player_shadow.gltf \
  assets/intermediate/apf2k8/models/1310_0415_player_shadow.bin \
  reports/assets/apf_player_shadow_skin_semantics.json \
  reports/assets/apf_player_shadow_skin_joints.tsv \
  reports/assets/apf_player_shadow_skin_vertices.tsv \
  reports/assets/apf_animation_export_readiness.json \
  reports/assets/apf_animation_transform_semantics.json \
  reports/assets/apf_animation_export_candidate_bindings.tsv \
  reports/assets/apf_mocap_inventory.json \
  reports/assets/apf_mocap_corpus.bin; do
  test -f "$required"
done

python3 -m py_compile \
  tools/apf_player_shadow_gltf.py \
  tools/validate_apf_player_shadow_gltf.py \
  tests/apf_player_shadow_screenshot_test.py
pkg-config --exists assimp

temporary=$(mktemp -d /tmp/apf-player-shadow-gltf.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

generate() {
  local seed=$1
  local destination=$2
  mkdir -p "$destination/assets" "$destination/reports"
  PYTHONHASHSEED=$seed python3 tools/apf_player_shadow_gltf.py \
    --static-gltf "$destination/assets/1310_0415_player_shadow_skin.gltf" \
    --animated-gltf "$destination/assets/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.gltf" \
    --report "$destination/reports/apf_player_shadow_gltf_export.json"
}

generate 1 "$temporary/one"
generate 777 "$temporary/two"
for relative in \
  assets/1310_0415_player_shadow_skin.gltf \
  assets/1310_0415_player_shadow_skin.bin \
  assets/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.gltf \
  assets/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.bin \
  reports/apf_player_shadow_gltf_export.json; do
  cmp "$temporary/one/$relative" "$temporary/two/$relative"
done

cmp "$temporary/one/assets/1310_0415_player_shadow_skin.gltf" "$static_gltf"
cmp "$temporary/one/assets/1310_0415_player_shadow_skin.bin" "$static_bin"
cmp "$temporary/one/assets/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.gltf" "$animated_gltf"
cmp "$temporary/one/assets/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.bin" "$animated_bin"
cmp "$temporary/one/reports/apf_player_shadow_gltf_export.json" "$report"

python3 tools/validate_apf_player_shadow_gltf.py
python3 tools/validate_apf_player_shadow_gltf.py \
  --static-gltf "$temporary/one/assets/1310_0415_player_shadow_skin.gltf" \
  --animated-gltf "$temporary/one/assets/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.gltf" \
  --report "$temporary/one/reports/apf_player_shadow_gltf_export.json"

assimp_flags=$(pkg-config --cflags --libs assimp)
c++ -std=c++20 -O2 -Wall -Wextra -Wpedantic \
  tools/apf_player_shadow_assimp_validate.cpp $assimp_flags \
  -o "$temporary/assimp-gcc"
"$temporary/assimp-gcc" "$static_gltf" "$animated_gltf"
compiler_count=1
if command -v clang++-18 >/dev/null 2>&1; then
  clang++-18 -std=c++20 -O2 -Wall -Wextra -Wpedantic \
    tools/apf_player_shadow_assimp_validate.cpp $assimp_flags \
    -o "$temporary/assimp-clang"
  "$temporary/assimp-clang" "$static_gltf" "$animated_gltf"
  compiler_count=2
fi

expected_runtime='APF_PLAYER_SHADOW_RUNTIME_PASS static_vertices=175 animated_vertices=175 faces=306 bones=21 weights=181 channels=18 moved=175 max_delta=0.0449219383'
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude tests/apf_player_shadow_runtime_test.c \
  src/assets/model_animation.c $(pkg-config --cflags --libs assimp) -lm \
  -o "$temporary/runtime-gcc"
test "$("$temporary/runtime-gcc" "$static_gltf" "$animated_gltf")" = \
  "$expected_runtime"
if command -v clang-18 >/dev/null 2>&1; then
  clang-18 -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow \
    -Werror -Iinclude tests/apf_player_shadow_runtime_test.c \
    src/assets/model_animation.c $(pkg-config --cflags --libs assimp) -lm \
    -o "$temporary/runtime-clang"
  test "$("$temporary/runtime-clang" "$static_gltf" "$animated_gltf")" = \
    "$expected_runtime"
fi

for registered in \
  recovered_apf_player_shadow_host_semantics \
  host_gl_smoke_recovered_apf_player_shadow_static \
  host_gl_smoke_recovered_apf_player_shadow_animation \
  host_gl_recovered_apf_player_shadow_screenshot_semantics; do
  grep -Fq "$registered" CMakeLists.txt
done

test "$(sha256sum "$static_gltf" | cut -d' ' -f1)" = \
  cf93ad2660e13b7b8999350d85d4a7fdd67abaaab54da687b8b090af8644bc2d
test "$(sha256sum "$static_bin" | cut -d' ' -f1)" = \
  574229cf5c8dfa0946ad81f47585f6b01442956b32afc5fe2cbc28910d4a4bd1
test "$(sha256sum "$animated_gltf" | cut -d' ' -f1)" = \
  b2a4029383cf75d73d8a7d6a640e7b5e12bdb1290e46e0c69404f4326422ad36
test "$(sha256sum "$animated_bin" | cut -d' ' -f1)" = \
  7a21f34ebbb6bf647b837a7e57e6ed1675a3eadaeb29480a942772a3c46bd940
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  d88679b5fda5d61bb802fab285a6a5b9b8b34dc8a591fd7fd89ce56dd3c597e3

if [[ "${APF_PLAYER_SHADOW_GLTF_FULL:-0}" == 1 ]]; then
  APF_ANIMATION_BINDING_GHIDRA=1 \
    tools/validate_apf_animation_export_readiness.sh
  APF_ANIMATION_TRANSFORM_GHIDRA=1 \
    tools/validate_apf_animation_transform_semantics.sh
  APF_PLAYER_SHADOW_SKIN_GHIDRA=1 \
    tools/validate_apf_player_shadow_skin_semantics.sh
  echo APF_PLAYER_SHADOW_GLTF_FULL_PROVENANCE_REGEN_PASS
fi

echo "APF_PLAYER_SHADOW_GLTF_VALIDATION_PASS compilers=$compiler_count vertices=351 triangles=306 joints=21 one_hot=351 bake_hz=120 keys=927 channels=24"
