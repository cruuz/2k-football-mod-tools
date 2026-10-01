#!/usr/bin/env bash
# DESIGN: main reviews and runs; one retail build and one CPU-v-CPU attempt.
set -Eeuo pipefail
umask 077
STACK=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
LAB=/media/noah/Storage/.b76-research/pb/lab
LOCK=/home/noah/2k-worktrees/.b76-session/xemu.lock
BUILDER='/home/noah/Desktop/2K5-8 Editors/ultimate/build_ultimate.py'
RETAIL='/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'
mkdir -p -- "$LAB"
SESSION=$(mktemp -d "$LAB/defense.XXXXXX")
DISC="$SESSION/league.xiso.iso"
CHILD=''
cleanup() {
  local code=$?
  trap - EXIT HUP INT TERM
  if [[ -n "$CHILD" ]]; then
    kill -TERM -- "-$CHILD" 2>/dev/null || true
    for _ in {1..10}; do kill -0 "$CHILD" 2>/dev/null || break; sleep 1; done
    kill -KILL -- "-$CHILD" 2>/dev/null || true
    wait "$CHILD" 2>/dev/null || true
  fi
  rm -f -- "$DISC" "$SESSION/run/xbox_hdd.qcow2"
  # DESIGN: raw memory is temporary; frames, native-stat JSON and logs survive.
  if [[ -d "$SESSION/run/snaps" ]]; then
    find "$SESSION/run/snaps" -maxdepth 1 -type f -name '*.bin' -delete
  fi
  printf 'DESIGN: lab exit %s; disposable disc removed; evidence %s\n' "$code" "$SESSION"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
printf 'DESIGN: lab evidence %s\n' "$SESSION"
setsid flock "$LOCK" nice -n 10 taskset -c 0-23 env ULTIMATE_NO_REEXEC=1 \
  python3 "$BUILDER" "$STACK" "$DISC" --source "$RETAIL" \
  --recipe "$STACK/pb/lab/defense.recipe.json" --strict-pending > "$SESSION/build.log" 2>&1 &
CHILD=$!
wait "$CHILD"
CHILD=''
[[ -s "$DISC" ]]
# DESIGN: shared probe provides isolated config, mem_limit 128, COW HDD and loopback gdb.
setsid flock "$LOCK" bash -c '
  set -euo pipefail
  while pgrep -x xemu >/dev/null; do sleep 5; done
  exec nice -n 19 taskset -c 24-31 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
    python3 "$1/pb/lab/pb_def_probe.py" --xiso "$2/league.xiso.iso" --run-dir "$2/run" \
    --route default --home-team GIANTS --away-team-slot COWBOYS --minutes 8 \
    --frame-seconds 2 --play-seconds 4200 --label pb-defense
' pb-defense "$STACK" "$SESSION" > "$SESSION/runtime.log" 2>&1 &
CHILD=$!
set +e
wait "$CHILD"
RUN_STATUS=$?
set -e
CHILD=''
shopt -s nullglob
STATS=("$SESSION"/run/stats/*.json)
if (( ! ${#STATS[@]} )); then
  echo 'INFERRED: no native-stat JSON; lab evidence incomplete' >&2
  exit 4
fi
exit "$RUN_STATUS"
