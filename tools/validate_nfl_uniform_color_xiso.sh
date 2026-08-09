#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
patch_report="$root/reports/assets/nfl2k5_lions_magenta_patch.json"
xiso_report="$root/reports/assets/nfl2k5_lions_magenta_xiso.json"
test_report="$root/reports/assets/nfl2k5_uniform_color_patch_tests.json"
listing="$root/reports/assets/nfl2k5_lions_magenta_xiso_listing.txt"
doc="$root/docs/research/nfl_uniform_color_xiso.md"
artifact=/media/noah/Storage/.codex-tmp/nfl2k5-lions-magenta-20260710
tmp=$(mktemp -d "${TMPDIR:-/tmp}/nfl-uniform-color-xiso.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

for path in "$patch_report" "$xiso_report" "$test_report" "$listing" "$doc"; do
  test -f "$path"
done

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile \
  "$root/tools/nfl_uniform_color_patch.py" \
  "$root/tools/nfl_uniform_color_xiso_verify.py" \
  "$root/tests/nfl_uniform_color_patch_test.py"

test_result=$(python3 "$root/tests/nfl_uniform_color_patch_test.py" \
  --report "$tmp/tests.json")
test "$test_result" = "NFL_UNIFORM_COLOR_PATCH_TEST_PASS cases=6"
cmp -- "$test_report" "$tmp/tests.json"

verify_result=$(python3 "$root/tools/nfl_uniform_color_xiso_verify.py" \
  --source-iso "$root/ESPN NFL 2K5 (USA).xiso.iso" \
  --source-game-root "$root/extracted/ESPN NFL 2K5 (USA)" \
  --patched-game-root "$artifact/game-tree" \
  --xiso "$artifact/ESPN-NFL-2K5-Lions-magenta.xiso.iso" \
  --reextracted-game-root "$artifact/reextracted" \
  --extract-xiso "$root/tools/vendor/extract-xiso/build/extract-xiso" \
  --patch-manifest "$patch_report" \
  --manifest "$tmp/xiso.json")
test "$verify_result" = "NFL_UNIFORM_COLOR_XISO_PROOF_PASS files=19 unrelated=17 patched_packs=2 patched_words=4 media_patch_disabled=true"
cmp -- "$xiso_report" "$tmp/xiso.json"

python3 - "$root" "$patch_report" "$xiso_report" "$test_report" "$listing" "$doc" <<'PY'
import json
from pathlib import Path
import sys

root, patch_path, xiso_path, test_path, listing_path, doc_path = map(Path, sys.argv[1:])
patch = json.loads(patch_path.read_text(encoding="utf-8"))
xiso = json.loads(xiso_path.read_text(encoding="utf-8"))
tests = json.loads(test_path.read_text(encoding="utf-8"))

assert patch["schema"] == "nfl2k5_uniform_color_patch/v1"
assert patch["scope"]["copy_only"] is True
assert patch["scope"]["texture_writer"] is False
assert patch["scope"]["model_writer"] is False
assert patch["source"]["expected_original_iso_sha256"] == "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
assert patch["source"]["default_xbe_sha256"] == "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
assert patch["source"]["archive_index_sha256"] == "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
assert patch["output"]["copied_files"] == 2
assert patch["output"]["hardlinked_files"] == 17
assert [item["outer_index"] for item in patch["targets"]] == [3685, 4002]
assert [item["logical_name"] for item in patch["targets"]] == ["09H0.IFF", "09A0.IFF"]
assert all(item["after"] == ["0xffff00ff", "0xffff00ff"] for item in patch["targets"])
assert [item["physical_slices"][0]["pack_offset"] for item in patch["targets"]] == [89958480, 255621200]
assert [item["physical_slices"][0]["after_hex"] for item in patch["targets"]] == ["ff00ffffff00ffff"] * 2
assert [item["patched_sha256"] for item in patch["packs"]] == [
    "40faed4a93fbb81065035e8f296cea701778fb65c4361a47573e4f155f3df39e",
    "81f681923c89c1a5c9460de9e70450fa29cc75ac4e9e0779a2f878060942e614",
]
assert all(patch["validation"].values())
assert all("PORTME:" in item for item in patch["portme"])

assert xiso["schema"] == "nfl2k5_uniform_color_xiso_proof/v1"
assert xiso["scope"]["texture_or_model_replacement_proved"] is False
assert xiso["scope"]["runtime_visibility_proved"] is False
assert xiso["artifacts"]["source_iso_sha256"] == "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
assert xiso["artifacts"]["patched_xiso_sha256"] == "f34cdd0ee8fd41fd9b21a075d33e229a3807b9874b9b628a90d1c8e0bd1e4c16"
assert xiso["artifacts"]["patched_xiso_size"] == 6300958720
assert xiso["extract_xiso"]["git_commit"] == "b72e5b60d598ec6df80534cda19cdcd4361aa18c"
assert xiso["extract_xiso"]["sha256"] == "222e7763df8f16d9b252c625fac5ef551cd25cdf031a785b3ec73c6e53c5d7f2"
assert xiso["extract_xiso"]["create_command"][1:3] == ["-m", "-c"]
assert xiso["extract_xiso"]["media_patch_disabled_with_m"] is True
assert len(xiso["files"]) == 19
assert sum(item["relation"] == "independent_patched_copy" for item in xiso["files"]) == 2
assert sum(item["relation"] == "unchanged_hardlink_then_byte_exact_reextract" for item in xiso["files"]) == 17
assert all(xiso["validation"].values())
assert all("PORTME:" in item for item in xiso["portme"])
assert xiso["phase_summary"]["worked"] and xiso["phase_summary"]["failed"] and xiso["phase_summary"]["blocking"]

assert tests["schema"] == "nfl2k5_uniform_color_patch_tests/v1"
assert tests["case_count"] == 6
assert all(tests["proved_invariants"].values())

listing = listing_path.read_text(encoding="utf-8")
assert "19 files; total file payload 6300413952 bytes." in listing
for name in ("/default.xbe", "/vc_53450030/A", "/vc_53450030/B"):
    assert name in listing

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "first safe fixed-size NFL 2K5 archive modification/repackage proof",
    "O_EXCL | O_RDWR",
    "`-m` is mandatory",
    "Worked, failed, and blocking",
    "f34cdd0ee8fd41fd9b21a075d33e229a3807b9874b9b628a90d1c8e0bd1e4c16",
    "texture/model import remains separate",
):
    assert phrase in doc

writer = (root / "tools/nfl_uniform_color_patch.py").read_text(encoding="utf-8")
for phrase in ("O_EXCL", "O_NOFOLLOW", "os.pwrite", "owned_path_matches", "map_virtual_write"):
    assert phrase in writer
PY

printf '%s\n' "$verify_result"
