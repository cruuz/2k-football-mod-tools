#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
report="$root/reports/assets/apf_writer_path_safety.json"
doc="$root/docs/research/apf_writer_path_safety.md"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/apf-writer-path-safety.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

test -f "$report"
test -f "$doc"

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  "$root/tools/apf_texture_patch.py" \
  "$root/tools/apf_uniform_mip_patch.py" \
  "$root/tools/apf_jersey_family_patch.py" \
  "$root/tests/apf_writer_path_safety_test.py"

result=$(python3 "$root/tests/apf_writer_path_safety_test.py" \
  --report "$tmp/apf_writer_path_safety.json")
case "$result" in
  "APF_WRITER_PATH_SAFETY_PASS writers=3 cli_cases=18 manifest_swap_cases=3 output_entry_swap_cases=2 fd_swap_cases=1 existing_volume_preserved=true unintended_outputs=0") ;;
  *)
    echo "unexpected path-safety result: $result" >&2
    exit 1
    ;;
esac
cmp -- "$report" "$tmp/apf_writer_path_safety.json"

python3 - "$root" "$report" "$doc" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root, report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf_writer_path_safety/v1"
assert report["scope"] == {
    "writers": ["texture", "uniform_mip", "jersey_family"],
    "retail_inputs_opened_by_regression_test": False,
    "retail_inputs_written": False,
}
assert report["case_counts"] == {
    "manifest_alias_or_existing_cli": 15,
    "manifest_post_preflight_reservation_race_cli": 3,
    "manifest_post_reservation_inode_swap_cli": 3,
    "output_entry_inode_path_swap": 2,
    "existing_volume_destination": 1,
    "output_inode_path_swap": 1,
    "total": 25,
}
assert len(report["manifest_cases_per_writer"]) == 7
invariants = report["proved_invariants"]
assert invariants["rejected_cli_unintended_outputs"] == 0
assert all(value is True for key, value in invariants.items()
           if key != "rejected_cli_unintended_outputs")

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

for original in report["canonical_originals"]:
    path = root / original["path"]
    assert path.stat().st_size == original["size"]
    assert sha256_file(path) == original["sha256"]

summary = report["phase_summary"]
assert summary["worked"] and summary["failed"] and summary["blocking"]
doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "25 deterministic cases",
    "O_EXCL | O_RDWR",
    "device/inode",
    "manifest and output-entry",
    "Worked, failed, and blocking",
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
):
    assert phrase in doc
PY

printf '%s\n' "$result"
