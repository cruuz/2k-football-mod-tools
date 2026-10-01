#!/bin/bash
# DESIGN: main launches this, SD never does. Read-only D, RAM-only fixed arm.
set -euo pipefail
LAB_SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SD2_RESEARCH=/media/noah/Storage/.b76-research/sd/lab
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$SD2_RESEARCH"
exec 9>/home/noah/2k-worktrees/.b76-session/xemu.lock
flock 9
while pgrep -f '[b]uild_ultimate_teams2026.py' >/dev/null; do sleep 10; done
while pgrep -x xemu >/dev/null; do sleep 5; done
for mode in control fixed; do
  SD2_RUN="$SD2_RESEARCH/$mode-$(date +%Y%m%d-%H%M%S)"
  mkdir "$SD2_RUN"
  export SD2_MODE="$mode" SD2_RUN SD2_LAB_SOURCE="$LAB_SOURCE"
  nice -n 19 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
    python3 "$LAB_SOURCE/sd2_lab.py" \
    --xiso '/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 candidate D 2026-09-28.xiso.iso' \
    --run-dir "$SD2_RUN" --route default --home-team GIANTS --away-team-slot COWBOYS \
    --minutes 8 --frame-seconds 6 --play-seconds 300 --label "sd2-$mode" \
    > "$SD2_RUN/probe.log" 2>&1
  python3 - "$SD2_RUN" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); r = json.loads((p/'sd2-result.json').read_text())
print(json.dumps(r, indent=2))
assert r['passed'], 'SD2 arm did not meet the witness criteria; retain frames and logs'
PY
done
