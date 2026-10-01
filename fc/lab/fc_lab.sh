#!/usr/bin/env bash
# DESIGN: Main reviews and runs this non-interactive lab. Astra never runs it.
# DESIGN: stop before building unless the complete contract fragment exists.
# DESIGN: all generated discs, overlays and captures stay on Storage.
set -euo pipefail
FC_WORK=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
FC_LAB=${FC_LAB:-/media/noah/Storage/.b76-research/fc/lab2}
FC_BASE=${FC_BASE:-/media/noah/Storage/.b76-research/main/freeze/league_roster_edits_u7_names.json}
FC_RATINGS=${FC_RATINGS:-/media/noah/Storage/.b76-research/r1/deliver/v2.4/r1_ratings_v2.4_fragment.json}
FC_FRAGMENT=${FC_FRAGMENT:-$FC_WORK/fc/data/fc_contract_fragment.json}
FC_LOCK=/home/noah/2k-worktrees/.b76-session/xemu.lock
FC_BUILDER='/home/noah/Desktop/2K5-8 Editors/ultimate/build_ultimate.py'
test -f "$FC_FRAGMENT" || { echo 'DESIGN: blocked, complete real-contract fragment is absent'; exit 2; }
python3 - "$FC_LAB" <<'PY'
from pathlib import Path
import shutil,sys
p=Path(sys.argv[1]).resolve()
if not p.is_relative_to('/media/noah/Storage'):
    raise SystemExit('DESIGN: lab output must be on Storage')
while not p.exists(): p=p.parent
if shutil.disk_usage('/').free < 100 * 1024**3 or shutil.disk_usage(p).free < 20 * 1024**3:
    raise SystemExit('DESIGN: require 100 GiB free on root and 20 GiB on Storage')
PY
mkdir -p "$FC_LAB"
FC_RUN=$(mktemp -d "$FC_LAB/fc-run-XXXXXXXX")
FC_DISC=$FC_RUN/fc-lab.xiso.iso
trap 'rm -f -- "$FC_DISC"' EXIT
cd -- "$FC_WORK"
python3 tools/franchise_economy/prepare_lab.py --base "$FC_BASE" --ratings "$FC_RATINGS" \
  --fragment "$FC_FRAGMENT" --out "$FC_RUN"
python3 tools/franchise_economy/money_probe.py --base "$FC_BASE" --ratings "$FC_RATINGS" \
  --fragment "$FC_FRAGMENT" --out "$FC_RUN/offline_money_strings.json" >"$FC_RUN/offline_money_strings.txt"
# DESIGN: hardware review compares currency units and clipping against the
# native text dump. This fitted-contract experiment does not prove exact APY.
exec 9>"$FC_LOCK"
flock -x 9
if pgrep -x xemu >/dev/null; then
  echo 'DESIGN: another xemu is active; leave it alone and stop this lab'
  exit 3
fi
nice -n 10 python3 "$FC_BUILDER" "$FC_WORK" "$FC_DISC" --recipe "$FC_RUN/recipe.json" >"$FC_RUN/build.log" 2>&1
rg -q 'ULTIMATE_BUILD_OK' "$FC_RUN/build.log"
python3 - "$FC_DISC" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]).with_suffix('.summary.json')
s=json.loads(p.read_text())
if s.get('not_applied') or s.get('applied',{}).get('franchise_economy') != 'applied':
    raise SystemExit('PROVED OFFLINE: final disc inspection did not verify the economy option')
PY
# DESIGN: the route records an explicit miss if any required menu is unreadable.
# DESIGN: it opens a trade screen only; it never submits a trade.
nice -n 19 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
  python3 tools/franchise_economy/lab_route.py --xiso "$FC_DISC" --run-dir "$FC_RUN/runtime" >"$FC_RUN/route.log" 2>&1
printf 'DESIGN: Main lab artifacts: %s\n' "$FC_RUN"
