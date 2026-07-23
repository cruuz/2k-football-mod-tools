#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

source_xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
source_sha='73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
before=$(sha256sum "$source_xbe" | cut -d' ' -f1)
test "$before" = "$source_sha"

python3 -m unittest -v tests/test_nfl_main_menu_label_patch.py

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

python3 - "$tmp/edits.json" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "schema": "nfl2k5_main_menu_label_edits/v1",
    "labels": {
        "quick_game": "Play Now",
        "game_modes": "Modes",
        "the_crib": "My Room",
        "features": "Customize",
        "xbox_live": "Online",
        "extras": "Bonus",
    },
}, indent=2) + "\n", encoding="utf-8")
PY

python3 tools/nfl_main_menu_label_patch.py \
  --source-xbe "$source_xbe" \
  --edits "$tmp/edits.json" \
  --output-xbe "$tmp/default.xbe" \
  --manifest "$tmp/manifest.json"

python3 tools/nfl_main_menu_label_patch_verify.py \
  --source-xbe "$source_xbe" \
  --output-xbe "$tmp/default.xbe" \
  --edits "$tmp/edits.json" \
  --manifest "$tmp/manifest.json"

# Exclusive output ownership is part of the public contract.
if python3 tools/nfl_main_menu_label_patch.py \
  --source-xbe "$source_xbe" \
  --edits "$tmp/edits.json" \
  --output-xbe "$tmp/default.xbe" \
  --manifest "$tmp/manifest-again.json" >"$tmp/existing.out" 2>"$tmp/existing.err"; then
  echo "writer accepted an existing output XBE" >&2
  exit 1
fi
grep -q 'output XBE/manifest already exists\|output already exists' "$tmp/existing.err"

python3 - "$tmp/too-long.json" "$tmp/non-ascii.json" <<'PY'
import json
import sys
from pathlib import Path

schema = "nfl2k5_main_menu_label_edits/v1"
Path(sys.argv[1]).write_text(json.dumps({
    "schema": schema, "labels": {"options": "EightChar"}
}) + "\n", encoding="utf-8")
Path(sys.argv[2]).write_text(json.dumps({
    "schema": schema, "labels": {"extras": "Café"}
}) + "\n", encoding="utf-8")
PY

for bad in too-long non-ascii; do
  if python3 tools/nfl_main_menu_label_patch.py \
    --source-xbe "$source_xbe" \
    --edits "$tmp/$bad.json" \
    --output-xbe "$tmp/$bad.xbe" \
    --manifest "$tmp/$bad-manifest.json" >"$tmp/$bad.out" 2>"$tmp/$bad.err"; then
    echo "writer accepted unsafe $bad edit" >&2
    exit 1
  fi
  test ! -e "$tmp/$bad.xbe"
  test ! -e "$tmp/$bad-manifest.json"
done

# The independent verifier must reject an otherwise well-formed output whose
# route table was tampered after the writer completed.
cp "$tmp/default.xbe" "$tmp/tampered.xbe"
python3 - "$tmp/tampered.xbe" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = bytearray(path.read_bytes())
data[0x50A9E4] ^= 1
path.write_bytes(data)
PY
if python3 tools/nfl_main_menu_label_patch_verify.py \
  --source-xbe "$source_xbe" \
  --output-xbe "$tmp/tampered.xbe" \
  --edits "$tmp/edits.json" \
  --manifest "$tmp/manifest.json" >"$tmp/tampered.out" 2>"$tmp/tampered.err"; then
  echo "verifier accepted a tampered source-row pointer" >&2
  exit 1
fi

# Prove why STRG/TXT is not the transport for this screen: none of the shipped
# menu labels has a record in any of the four STRG or two APF TXT tables, while
# both route traces explicitly carry direct executable pointers.
python3 - <<'PY'
import json
from pathlib import Path

state = json.loads(Path("reports/assets/menu_state_trace.json").read_text())
nfl_labels = [row["label"] for row in state["nfl2k5"]["navigation_rows"]]
apf_labels = [row["label"] for row in state["apf2k8"]["navigation_rows"]]
assert nfl_labels == [
    "Quick Game", "Game Modes", "The Crib|TM|", "Features",
    "Options", "Xbox Live", "Extras",
]
assert apf_labels == [
    "Quick Game", "Teams", "Season", "Practice", "Options",
    "Features", "Xbox Live",
]
assert state["nfl2k5"]["localization"]["storage"] == \
    "direct UTF-16LE literal pointers at source row +0x04"
assert state["apf2k8"]["localization"]["storage"] == \
    "direct UTF-16BE literal pointers at source row +0x04; 0x846F40B8 copies them to runtime row +0x08"

strg = json.loads(Path("reports/assets/cross_title_string_tables.json").read_text())
strg_texts = {row["text"] for table in strg["tables"] for row in table["records"]}
txt = json.loads(Path("reports/assets/apf_txt_localization.json").read_text())
txt_texts = {
    row["text"] for table in txt["tables"] for row in table["records"]
    if not row["is_control_record"]
}
for label in set(nfl_labels + apf_labels):
    assert label not in strg_texts
    assert label not in txt_texts
PY

after=$(sha256sum "$source_xbe" | cut -d' ' -f1)
test "$after" = "$source_sha"

echo 'NFL_MAIN_MENU_LABEL_PATCH_VALIDATION_PASS rows=7 tests=3 source_unchanged=true strg_txt_ids=0 apf_writer=false runtime=false'
