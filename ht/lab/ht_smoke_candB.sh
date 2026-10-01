#!/usr/bin/env bash
# DESIGN. Main runs this; ht must never start xemu.
# Usage: bash ht/lab/ht_smoke_candB.sh DISC BUILD_RECEIPT [LAB_DIR]
set -euo pipefail
DISC=${1:?Supply the rebuilt roster-enabled candidate B ISO}
RECEIPT=${2:?Supply its .build.json receipt}
LAB=${3:-/media/noah/Storage/.b76-research/ht/astra-build/lab}
SCRIPT=$(realpath "$(dirname "$0")/ht_lab.py")
LOCK=/home/noah/2k-worktrees/.b76-session/xemu.lock
mkdir -p "$LAB"
python3 - "$DISC" "$RECEIPT" <<'PY'
import hashlib,json,os,sys
disc,receipt=sys.argv[1:]
build=json.load(open(receipt))
assert build['overrides'].get('historic_rosters_2026') is True, 'proper season roster option must be on'
out=build['result']['outcome']['output']
h=hashlib.sha256()
with open(disc,'rb') as f:
    for b in iter(lambda:f.read(1<<24),b''):
        h.update(b)
assert os.path.getsize(disc)==out['size'] and h.hexdigest()==out['sha256'], 'disc/receipt mismatch'
print('PROVED OFFLINE: disc matches receipt',h.hexdigest(),flush=True)
PY
for plan in mixed pair; do
  run="$LAB/run-$plan"
  if [[ -e "$run" ]]; then
    echo "Existing run directory: $run. Supply a new LAB_DIR to preserve evidence." >&2
    exit 2
  fi
  mkdir -p "$run"
  echo "DESIGN: $plan. Inspect screenshots and append player-card commands to $run/card-commands.txt"
  # One VM under the shared lock. No automatic retry after a game outcome.
  flock "$LOCK" nice -n 19 taskset -c 24-31 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
    python3 "$SCRIPT" --xiso "$DISC" --run-dir "$run" --plan "$plan" --minutes 8 \
      --card-seconds "${HT_CARD_SECONDS:-240}" --label "ht-candB-$plan" > "$LAB/$plan.log" 2>&1 || {
        echo "DESIGN: inspect $LAB/$plan.log before attempting another run." >&2
        exit 1
      }
done
echo "DESIGN: coin-toss PASS alone is insufficient. Complete ht/lab/READOUT.md and retain screenshots."
