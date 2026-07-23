#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/uniform-texture-sharing.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$temporary/pycache"

python3 -m py_compile \
  tools/uniform_texture_sharing_audit.py \
  mod_editor/__main__.py \
  mod_editor/core/uniform_sharing.py \
  tests/uniform_texture_sharing_audit_test.py \
  tests/mod_editor/test_uniform_sharing.py

python3 tools/uniform_texture_sharing_audit.py \
  --report "$temporary/report.json" \
  --legacy-v1-report "$temporary/report.v1.json" \
  --nfl-tsv "$temporary/nfl.tsv" \
  --apf-tsv "$temporary/apf.tsv"

cmp reports/assets/uniform_texture_sharing.v2.json "$temporary/report.json"
cmp reports/assets/uniform_texture_sharing.json "$temporary/report.v1.json"
cmp reports/assets/nfl2k5_uniform_texture_sharing.tsv "$temporary/nfl.tsv"
cmp reports/assets/apf2k8_jersey_selector_sharing.tsv "$temporary/apf.tsv"

test "$(sha256sum reports/assets/uniform_texture_sharing.json | cut -d' ' -f1)" = \
  'eb37c92a2e2aeaf6d458028e5e5273110c80b3cdbaeb2b5925af99327f4cec6a'
test "$(sha256sum reports/assets/uniform_texture_sharing.v2.json | cut -d' ' -f1)" = \
  '9094ad0b6a199adc240dc254fdcd031573a16070c0aa80805f36fc951143b36a'
test "$(sha256sum reports/assets/nfl2k5_uniform_texture_sharing.tsv | cut -d' ' -f1)" = \
  'f4367f8fb1a3f2da3ccc20890635ff15dbd1c45c86f118627bbf2895dd7a1658'
test "$(sha256sum reports/assets/apf2k8_jersey_selector_sharing.tsv | cut -d' ' -f1)" = \
  '603c7100a3ece052652420c0102f5bd995935391e2612259bfa1e42f365b0ee5'
test "$(wc -c < reports/assets/apf_pants_family_layout.json)" = 274896
test "$(sha256sum reports/assets/apf_pants_family_layout.json | cut -d' ' -f1)" = \
  '82241aefe6728a7426552663ee69ecffbdabca01f4359e8322edf75775adf293'
test "$(wc -c < reports/assets/apf_helmet_family_layout.json)" = 280394
test "$(sha256sum reports/assets/apf_helmet_family_layout.json | cut -d' ' -f1)" = \
  '72bf3efd4495e03fb856e0fb776313c842ebfafeb8d20d19f91318d7161aba03'
test "$(wc -c < reports/assets/apf_shoulder_family_layout.json)" = 345097
test "$(sha256sum reports/assets/apf_shoulder_family_layout.json | cut -d' ' -f1)" = \
  'a2ea45adb931677ef4d9d9a37530f2acc53013050793a47f41f69c65e8319875'

python3 -m unittest -v \
  tests/uniform_texture_sharing_audit_test.py \
  tests/mod_editor/test_uniform_sharing.py

python3 -m mod_editor --inspect-nfl-uniform-sharing 10H5 > "$temporary/nfl-lookup.json"
python3 -m mod_editor --inspect-apf-jersey-sharing 23 > "$temporary/apf-lookup.json"
python3 -m mod_editor --inspect-apf-pants-sharing 13 > "$temporary/apf-pants-lookup.json"
python3 -m mod_editor --inspect-apf-helmet-sharing 16 > "$temporary/apf-helmet-lookup.json"
python3 -m mod_editor --inspect-apf-shoulder-sharing 8 > "$temporary/apf-shoulder-lookup.json"

python3 - "$temporary/nfl-lookup.json" "$temporary/apf-lookup.json" "$temporary/apf-pants-lookup.json" "$temporary/apf-helmet-lookup.json" "$temporary/apf-shoulder-lookup.json" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

nfl = json.loads(Path(sys.argv[1]).read_text())
assert nfl["schema"] == "mod_editor_nfl_uniform_sharing_lookup/v1"
assert nfl["selector"]["selector"] == "10H5"
assert nfl["selector"]["team"] == "Green Bay Packers"
assert nfl["cross_asset_code_content_alias_count"] == 4
assert {row["texture_name"] for row in nfl["cross_asset_code_content_aliases"]} == {
    "jersey00", "jersey00_mud", "sleeve00", "sleeve00_mud",
}
assert nfl["on_disc_span_is_independent"] is True
assert nfl["safe_fix"]["archive_growth_required"] is False
assert nfl["safe_fix"]["arbitrary_input_guaranteed_to_fit"] is False

apf = json.loads(Path(sys.argv[2]).read_text())
assert apf["schema"] == "mod_editor_apf_jersey_sharing_lookup/v1"
assert apf["asset"]["asset_index"] == 23
assert apf["asset"]["selector_owner_count"] == 26
assert apf["asset"]["team_count"] == 13
assert {row["bank"] for row in apf["asset"]["owners"]} == {0, 1}
assert apf["safe_dealias_writer_available"] is True
assert apf["safe_offline_cli_dealias_writer_available"] is True
assert apf["public_gui_dealias_writer_available"] is False
assert "home" not in json.dumps(apf["asset"]).lower()
assert "away" not in json.dumps(apf["asset"]).lower()

pants = json.loads(Path(sys.argv[3]).read_text())
assert pants["schema"] == "mod_editor_apf_pants_sharing_lookup/v1"
assert pants["asset_index"] == 13
assert pants["team_bank_use_count"] == 34
assert {row["bank"] for row in pants["team_bank_uses"]} == {0, 1}
assert pants["physical_asset_writer_proved"] is True
assert pants["selector_or_roster_writer_available"] is False
assert "offset" not in json.dumps(pants).lower()

helmet = json.loads(Path(sys.argv[4]).read_text())
assert helmet["schema"] == "mod_editor_apf_helmet_sharing_lookup/v1"
assert helmet["asset_index"] == 16
assert helmet["team_bank_use_count"] == 34
assert {row["bank"] for row in helmet["team_bank_uses"]} == {0, 1}
assert helmet["physical_asset_writer_proved"] is True
assert helmet["selector_or_roster_writer_available"] is False
assert helmet["two_channel_data_contract"]["shader_meanings_named"] is False
assert "offset" not in json.dumps(helmet).lower()

shoulder = json.loads(Path(sys.argv[5]).read_text())
assert shoulder["schema"] == "mod_editor_apf_shoulder_sharing_lookup/v1"
assert shoulder["asset_index"] == 8
assert shoulder["team_bank_use_count"] == 36
assert {row["bank"] for row in shoulder["team_bank_uses"]} == {0, 1}
assert shoulder["physical_color_asset_writer_proved"] is True
assert shoulder["paired_normal_writer_available"] is False
assert shoulder["selector_or_roster_writer_available"] is False
assert "offset" not in json.dumps(shoulder).lower()
PY

if python3 -m mod_editor --inspect-nfl-uniform-sharing offset:123 \
    >"$temporary/raw.stdout" 2>"$temporary/raw.stderr"; then
  echo 'public editor accepted a raw NFL selector' >&2
  exit 1
fi
if python3 -m mod_editor --inspect-apf-jersey-sharing 24 \
    >"$temporary/apf24.stdout" 2>"$temporary/apf24.stderr"; then
  echo 'public editor accepted APF asset 24' >&2
  exit 1
fi
if python3 -m mod_editor --inspect-apf-pants-sharing 24 \
    >"$temporary/pants24.stdout" 2>"$temporary/pants24.stderr"; then
  echo 'public editor accepted APF pants asset 24' >&2
  exit 1
fi
if python3 -m mod_editor --inspect-apf-helmet-sharing 24 \
    >"$temporary/helmet24.stdout" 2>"$temporary/helmet24.stderr"; then
  echo 'public editor accepted APF helmet asset 24' >&2
  exit 1
fi
if python3 -m mod_editor --inspect-apf-shoulder-sharing 24 \
    >"$temporary/shoulder24.stdout" 2>"$temporary/shoulder24.stderr"; then
  echo 'public editor accepted APF shoulder asset 24' >&2
  exit 1
fi

help="$(python3 -m mod_editor --help)"
rg -q -- '--inspect-nfl-uniform-sharing SELECTOR' <<<"$help"
rg -q -- '--inspect-apf-jersey-sharing ASSET_INDEX' <<<"$help"
rg -q -- '--inspect-apf-pants-sharing ASSET_INDEX' <<<"$help"
rg -q -- '--inspect-apf-helmet-sharing ASSET_INDEX' <<<"$help"
rg -q -- '--inspect-apf-shoulder-sharing ASSET_INDEX' <<<"$help"
if rg -q -- '--offset|--outer-index|--selector-record-offset' <<<"$help"; then
  echo 'public editor exposed a raw uniform-sharing offset' >&2
  exit 1
fi

rg -q '3,170 writer targets have 3,170 distinct' \
  docs/research/uniform_texture_sharing.md
rg -q 'does \*\*not\*\* expose it as a writer' \
  docs/research/uniform_texture_sharing.md
rg -q 'does not claim a fix for the PS2 disc layout used by PCSX2' \
  docs/research/uniform_texture_sharing.md

echo 'UNIFORM_TEXTURE_SHARING_VALIDATION_PASS nfl_selectors=634 nfl_physical=3170 nfl_cross_team_groups=32 nfl_cross_team_owners=396 apf_jersey_assets=24 apf_jersey_asset23_owners=26 apf_pants_assets=24 apf_pants_asset13_owners=34 apf_helmet_assets=24 apf_helmet_asset16_owners=34 apf_shoulder_assets=24 apf_shoulder_asset8_owners=36 apf_selectors=80 editor_lookup=true writes=false'
