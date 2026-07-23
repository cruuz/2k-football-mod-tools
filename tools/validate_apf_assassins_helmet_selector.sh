#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

source_0a='extracted/All-Pro Football 2K8 (USA)/0A'
source_sha='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
before=$(sha256sum "$source_0a" | cut -d' ' -f1)
test "$before" = "$source_sha"

PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  tools/apf_assassins_helmet_selector_patch.py \
  tools/apf_assassins_helmet_selector_verify.py

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_apf_assassins_helmet_selector -q

PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

root = Path.cwd()
report = json.loads(
    (root / "reports/assets/apf_assassins_helmet_selector_checkpoint.v1.json").read_text(
        encoding="utf-8"
    )
)
assert report["schema"] == "apf_assassins_helmet_selector_checkpoint/v1"
assert report["status"] == "offline_two_byte_witness_ready_runtime_not_executed"
assert report["offline_result"]["decoded_changed_byte_count"] == 2
assert report["runtime_boundary"]["status"] == "not_executed"
assert report["runtime_boundary"]["current_v1_queue_still_pins_all_family_output"] is True

def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()

for section, records in (
    ("tooling", ["writer", "independent_verifier"]),
    ("evidence", ["writer_manifest", "independent_verification"]),
):
    for name in records:
        record = report[section][name]
        path = root / record["path"]
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == record["size_bytes"]
        assert digest(path) == record["sha256"]

tree = ast.parse(
    (root / report["tooling"]["independent_verifier"]["path"]).read_text(
        encoding="utf-8"
    )
)
modules: set[str] = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        modules.update(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        modules.add(node.module)
assert "apf_assassins_helmet_selector_patch" not in modules
assert "apf_uniform_selector_patch" not in modules
assert "apf_uniform_selector_allocation" not in modules
PY

temporary=$(mktemp -d "${TMPDIR:-/tmp}/apf-assassins-helmet-selector.XXXXXX")
cleanup() {
  rm -rf -- "$temporary"
}
trap cleanup EXIT HUP INT TERM

PYTHONDONTWRITEBYTECODE=1 python3 tools/apf_assassins_helmet_selector_patch.py \
  --index "$source_0a" \
  --output-volume "$temporary/output-0A" \
  --manifest "$temporary/manifest.json"

PYTHONDONTWRITEBYTECODE=1 python3 tools/apf_assassins_helmet_selector_verify.py \
  --source-index "$source_0a" \
  --output-volume "$temporary/output-0A" \
  --manifest "$temporary/manifest.json" \
  --json "$temporary/verify.json"

test "$(wc -c < "$temporary/output-0A")" -eq 1140850688
test "$(sha256sum "$temporary/output-0A" | cut -d' ' -f1)" = \
  '939f5d9bbe546b041b04ae2a76e55c01eaf3063d933ecccb72d90fa3e87be7a8'
cmp -s \
  "$temporary/manifest.json" \
  reports/cut_content/apf_nfl_lineage/assassins_helmet_selector_xenia/helmet_only_writer_manifest.json
cmp -s \
  "$temporary/verify.json" \
  reports/cut_content/apf_nfl_lineage/assassins_helmet_selector_xenia/helmet_only_independent_verify.json

after=$(sha256sum "$source_0a" | cut -d' ' -f1)
test "$after" = "$before"

echo 'APF_ASSASSINS_HELMET_SELECTOR_VALIDATION_PASS changed_bytes=2 payload=435226 output=939f5d9b runtime=false hardware=false'
