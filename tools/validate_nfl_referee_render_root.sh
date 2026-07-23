#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
root_trajectory='reports/assets/nfl_referee_root_trajectory.json'
pose_matrix='reports/assets/nfl_pose_matrix_apply.json'
trace_dir='reports/assets/nfl_referee_render_root_ghidra'
trace="$trace_dir/nfl_referee_render_root_trace.txt"
pseudo="$trace_dir/nfl_referee_render_root_focused_pseudo_c.c"
report='reports/assets/nfl_referee_render_root.json'
generator='tools/nfl_referee_render_root.py'
ghidra_script='tools/ghidra_scripts/NflRefereeRenderRootTrace.java'
doc='docs/research/nfl_referee_render_root.md'

expected_report_sha256='10d48c615240eda1e8cddb9b19e36eeb492993535d12e868a9cbb32c169caa18'
expected_trace_sha256='469f6457157978267f424020c0ca3749f9b13ece62697a894d697d0ed47a06a1'
expected_pseudo_sha256='d3dc568b0524ebcd949358cc4db2a4aa342484cff4b25f14e65095ed82866c6b'
expected_generator_sha256='9012ecf774bdcc6145ab6d9ce07f7e5f47e53de7078ab85b92692e3eb61e5b54'
expected_ghidra_script_sha256='03b9c943a7ee38b9716a0f348b58987cba414a3bb675e8d511ab13ccb1e7a001'

for path in \
  "$xbe" "$xbe_header" "$root_trajectory" "$pose_matrix" \
  "$trace" "$pseudo" "$report" "$generator" "$ghidra_script" "$doc"; do
  test -f "$path"
done

hash_of() {
  sha256sum "$1" | cut -d ' ' -f 1
}

test "$(hash_of "$report")" = "$expected_report_sha256"
test "$(hash_of "$trace")" = "$expected_trace_sha256"
test "$(hash_of "$pseudo")" = "$expected_pseudo_sha256"
test "$(hash_of "$generator")" = "$expected_generator_sha256"
test "$(hash_of "$ghidra_script")" = "$expected_ghidra_script_sha256"

temporary=$(mktemp -d /tmp/nfl-referee-render-root.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"

python3 -m py_compile "$generator"
python3 "$generator" --json "$temporary/report.json"
cmp "$temporary/report.json" "$report"

python3 - "$report" "$trace" "$pseudo" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, trace_path, pseudo_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_referee_render_root/v1"

result = report["result"]
assert result == {
    "actor_transform_to_renderer_external_root_edge_proved": True,
    "closed_upstream_gap": "the final actor+0x18 to renderer external-root ownership edge",
    "confidence": "instruction_exact_static_ownership",
    "gameplay_equivalent_gltf_root_track_ready": False,
    "reason_root_track_remains_withheld": (
        "the render edge is closed, but the selected clip still lacks a "
        "concrete one-of-seven actor instance and captured live actor, "
        "controller, and transform-state values"
    ),
    "selected_clip_to_concrete_actor_instance_proved": False,
}

fields = report["object_fields"]
assert set(fields) == {
    "actor_transform", "controller", "referee_actor", "render_object"
}
assert fields["referee_actor"]["+0x18"] == "live actor-transform pointer"
assert "hierarchy-expanded in place" in fields["referee_actor"]["+0x04"]
assert "alternate" in fields["actor_transform"]["+0x34"]
assert "not main" in fields["actor_transform"]["+0x34"]
assert fields["render_object"]["+0x14"].startswith("current matrix-array")

rows = report["referee_render_rows"]
assert rows["count"] == 7 and rows["stride_bytes"] == 28
assert rows["low_render_object"] == {
    "loader_store_va": "0x000969af",
    "name": "ref_low",
    "name_va": "0x00e65cbc",
    "row_field_va": "0x00b661c4 + row*0x1c",
}
assert rows["high_render_object"] == {
    "loader_store_va": "0x0009698a",
    "name": "ref_high",
    "name_va": "0x00e65ccc",
    "row_field_va": "0x00b661c8 + row*0x1c",
}
assert "0 selects ref_low and 1 selects ref_high" in rows["queued_variant_flag"]

builders = report["external_root_builders"]
assert [row["function_va"] for row in builders] == [
    "0x001d2d90", "0x0028ea10"
]
assert builders[0]["translation"] == {
    "x": "(actor+0x18)+0x30",
    "y": "(actor+0x14)+0x48 multiplied by actor+0x08",
    "z": "(actor+0x18)+0x38",
}
assert builders[1]["translation"] == {
    "x": "(actor+0x18)+0x30",
    "y": "(actor+0x18)+0x34",
    "z": "(actor+0x18)+0x38",
}
assert "not read" in builders[0]["important_y_boundary"]
assert all("actor+0x04" in row["local_pose_preparation"] for row in builders)

chain = report["ownership_chain"]
assert [row["step"] for row in chain] == list(range(1, 7))
assert [row["function_va"] for row in chain] == [
    "0x002cc570",
    "0x001d2d90/0x0028ea10",
    "0x00096b20",
    "0x00074dd0 -> 0x00096b50",
    "0x00096b90",
    "0x00021860 -> 0x000243d0 -> 0x00022c00",
]
assert chain[2]["hierarchy_equation"] == (
    "current[i] = local[i] * (current[parent] or external_root)"
)
assert chain[5]["palette_equation"].startswith("skin = T(-serialized")
assert len(report["draw_order_proof"]) == 2
assert all(row["order"] == "enqueue precedes draw" for row in report["draw_order_proof"])

spans = report["executable"]["function_image_spans"]
assert len(spans) == 24
assert len({row["name"] for row in spans}) == 24
assert sum(row["size"] for row in spans) == 6501
by_name = {row["name"]: row for row in spans}
assert by_name["referee_trajectory_callback"]["sha256"] == (
    "5fa00a474133d7fb286cfe373d104c30d2b641cbbad2a4aed740041ab834c344"
)
assert by_name["gameplay_referee_pose_root_builder"]["sha256"] == (
    "06698fb0e017fba2e328ba26cc0b1fc7874aceb542fe20034441ee3079551851"
)
assert by_name["alternate_referee_pose_root_builder"]["sha256"] == (
    "fc58386a1a560b53b80eb1a358951f8ae162241d7704ad4a922de9d368369239"
)
assert by_name["referee_hierarchy_bridge"]["sha256"] == (
    "24484165f9eaf0fcc742022a8dd3e45c929516001c780b9c3fb8019f8ccbff48"
)
assert by_name["referee_draw_queue"]["sha256"] == (
    "e59d8946eb5b9a9ff435617f4d4e9f2e2ad02f97b3d13e6a0e3cda64f2780285"
)
assert by_name["skin_palette_builder"]["sha256"] == (
    "55e7b14873c75c21ffaa53456246b515bf6795c6ac20e2b5414a5d668330f053"
)

sources = report["sources"]
assert sources["generator"]["sha256"] == (
    "9012ecf774bdcc6145ab6d9ce07f7e5f47e53de7078ab85b92692e3eb61e5b54"
)
assert sources["ghidra_script"]["sha256"] == (
    "03b9c943a7ee38b9716a0f348b58987cba414a3bb675e8d511ab13ccb1e7a001"
)
assert sources["ghidra_trace"]["sha256"] == (
    "469f6457157978267f424020c0ca3749f9b13ece62697a894d697d0ed47a06a1"
)
assert sources["ghidra_pseudo_c"]["sha256"] == (
    "d3dc568b0524ebcd949358cc4db2a4aa342484cff4b25f14e65095ed82866c6b"
)

assert len(report["remaining_boundaries"]) == 4
assert len(report["portme"]) == 4
assert all(line.startswith("// PORTME:") for line in report["portme"])
assert len(report["worked"]) == 5

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
doc = doc_path.read_text(encoding="utf-8")
assert trace.count("\nFUNCTION 0x") == 32
assert pseudo.count("/* 0x") == 32
assert "// PORTME: could not decompile function at" not in pseudo
for token in (
    "0x001D2E28 MOV ECX,dword ptr [ESI + 0x18]",
    "0x001D2E84 CALL 0x00096b20",
    "0x0028EB52 CALL 0x00096b20",
    "0x00074E03 MOV EDX,dword ptr [ESI + 0x4]",
    "0x00096BD8 CALL 0x00021900",
    "0x00096CA6 CALL 0x00021860",
    "0x000246B1 CALL 0x00022c00",
):
    assert token in trace, token
for portme in report["portme"]:
    assert portme in doc, portme
for token in (
    "0x001D2D90", "0x0028EA10", "0x00096B20", "ref_low",
    "ref_high", "one-of-seven", "root_track_ready=0",
):
    assert token in doc, token

print("NFL_REFEREE_RENDER_ROOT_JSON_XBE_GHIDRA_ASSERTIONS_PASS")
PY

expect_rejected() {
  local label=$1
  shift
  if "$@" >"$temporary/$label.log" 2>&1; then
    echo "negative test unexpectedly succeeded: $label" >&2
    return 1
  fi
}

python3 - "$root_trajectory" "$temporary/bad-root.json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
value["confidence_boundary"]["unproved"].remove(
    "the final actor+0x18 to renderer external-root ownership edge"
)
json.dump(value, open(sys.argv[2], "w", encoding="utf-8"))
PY
expect_rejected bad_root \
  python3 "$generator" --root-trajectory "$temporary/bad-root.json" \
    --json "$temporary/rejected.json"

python3 - "$pose_matrix" "$temporary/bad-pose.json" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
value["renderer_boundary"]["current_space"] = "world-space"
json.dump(value, open(sys.argv[2], "w", encoding="utf-8"))
PY
expect_rejected bad_pose \
  python3 "$generator" --pose-matrix "$temporary/bad-pose.json" \
    --json "$temporary/rejected.json"

python3 - "$trace" "$temporary/bad-trace.txt" <<'PY'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text(encoding="utf-8")
needle = "0x00096BD8 CALL 0x00021900"
assert needle in text
Path(sys.argv[2]).write_text(text.replace(needle, "REMOVED", 1), encoding="utf-8")
PY
expect_rejected bad_trace \
  python3 "$generator" --trace "$temporary/bad-trace.txt" \
    --json "$temporary/rejected.json"

if [[ ${NFL_REFEREE_RENDER_ROOT_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflRefereeRenderRootTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_referee_render_root_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_referee_render_root_focused_pseudo_c.c" \
      "$pseudo"
fi

echo 'NFL_REFEREE_RENDER_ROOT_VALIDATION_PASS edge_proved=1 builders=2 functions=24 focused=32 negative_tests=3 root_track_ready=0'
