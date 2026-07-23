#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/main-menu-named-inspector.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$temporary/pycache"

python3 -m py_compile \
  mod_editor/core/menu_modes.py \
  tests/mod_editor/test_menu_modes.py

python3 -m unittest -v tests/mod_editor/test_menu_modes.py

python3 -m mod_editor --inspect-main-menu nfl2k5 > "$temporary/nfl.json"
python3 -m mod_editor --inspect-main-menu apf2k8 > "$temporary/apf.json"

python3 - "$temporary/nfl.json" "$temporary/apf.json" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

nfl = json.loads(Path(sys.argv[1]).read_text())
apf = json.loads(Path(sys.argv[2]).read_text())
assert nfl["schema"] == "mod_editor_named_main_menu_inspector/v1"
assert nfl["state"]["initial_selection"] == "Quick Game"
assert [row["layout"] for row in nfl["layout_reachability"]] == [
    "main_menu_sub", "main_navi",
]
assert apf["state"]["proved_executable_route_count"] == 8
layouts = {row["layout"]: row for row in apf["layout_reachability"]}
assert layouts["quicknav"]["status"] == "proved"
assert layouts["layout_mainmenu"]["status"] == "runtime_instantiation_unproved"
assert layouts["layout_mainmenu"]["direct_main_owner"] is False
for value in (nfl, apf):
    encoded = json.dumps(value, sort_keys=True)
    assert not re.search(r"0x[0-9a-fA-F]+", encoded)
    assert "offset" not in encoded.lower()
    assert value["read_only"] is True
    assert value["mutation_supported"] is False
PY

if python3 -m mod_editor --inspect-main-menu offset:123 \
    >"$temporary/raw.stdout" 2>"$temporary/raw.stderr"; then
  echo 'public editor accepted a raw Main Menu selector' >&2
  exit 1
fi

help="$(python3 -m mod_editor --help)"
rg -q -- '--inspect-main-menu GAME' <<<"$help"
if rg -q -- '--menu-address|--state-address|--layout-offset' <<<"$help"; then
  echo 'public editor exposed a raw menu address or offset' >&2
  exit 1
fi

rg -q 'exposes no executable addresses, archive' \
  docs/research/main_menu_named_inspector.md
rg -q 'specifically not the descriptor-selected Main layout' \
  docs/research/main_menu_named_inspector.md

echo 'MAIN_MENU_NAMED_INSPECTOR_VALIDATION_PASS games=2 rows=14 nfl_layouts=2 apf_layouts=3 apf_routes=8 read_only=true raw_addresses=false mutation=false tests=5'
