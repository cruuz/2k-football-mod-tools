#!/usr/bin/env bash
# DESIGN: main-only two-turn lab coordinator. Astra must not execute this file.
set -Eeuo pipefail
umask 077
STACK=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
LAB=/media/noah/Storage/.b76-research/pb/lab
LOCK=/home/noah/2k-worktrees/.b76-session/xemu.lock
BUILDER='/home/noah/Desktop/2K5-8 Editors/ultimate/build_ultimate.py'
RETAIL='/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'

case "${1:-}" in
  run)
    # DESIGN: turn 2 signals the still-running owner from turn 1. No second build or VM.
    SESSION=$(realpath -e -- "${2:?DESIGN: supply the session directory printed by build}")
    [[ "$SESSION" == "$LAB"/session.* && -f "$SESSION/build-ready" && ! -e "$SESSION/finished.json" ]]
    kill -0 "$(cat "$SESSION/owner.pid")"
    (set -o noclobber; : > "$SESSION/run-turn-2")
    echo "DESIGN: run requested once; follow $SESSION/runtime.log and run/cmds.txt"
    exit 0
    ;;
  build) ;;
  *) echo 'DESIGN: usage: pb/lab/pb_lab.sh build | run SESSION' >&2; exit 2 ;;
esac

mkdir -p -- "$LAB"
SESSION=$(mktemp -d "$LAB/session.XXXXXX")
DISC="$SESSION/giants.xiso.iso"
CHILD=''
STAGE=build
cleanup() {
  local result=$?
  trap - EXIT HUP INT TERM
  if [[ -n "$CHILD" ]]; then
    # DESIGN: only our setsid process group; never kill another lab's xemu.
    kill -TERM -- "-$CHILD" 2>/dev/null || true
    for _ in {1..10}; do kill -0 "$CHILD" 2>/dev/null || break; sleep 1; done
    kill -KILL -- "-$CHILD" 2>/dev/null || true
    wait "$CHILD" 2>/dev/null || true
  fi
  rm -f -- "$DISC" "$SESSION/run/xbox_hdd.qcow2"
  python3 - "$SESSION" "$STAGE" "$result" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);p.joinpath('finished.json').write_text(json.dumps(dict(status='INFERRED',stage=sys.argv[2],exit_code=int(sys.argv[3]),disc_exists=p.joinpath('giants.xiso.iso').exists(),runtime_witness=False),indent=2)+'\n')
PY
  exit "$result"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
printf '%s\n' "$$" > "$SESSION/owner.pid"
printf 'DESIGN: session %s\n' "$SESSION"

# DESIGN: turn 1 builds from retail using this stack, under the shared exclusion lock.
setsid flock "$LOCK" nice -n 10 taskset -c 0-23 env ULTIMATE_NO_REEXEC=1 \
  python3 "$BUILDER" "$STACK" "$DISC" --source "$RETAIL" \
  --recipe "$STACK/pb/lab/v7.pb.json" --strict-pending > "$SESSION/build.log" 2>&1 &
CHILD=$!
wait "$CHILD"
CHILD=''
python3 - "$STACK" "$SESSION" <<'PY'
import json,shutil,sys
from pathlib import Path
stack,session=map(Path,sys.argv[1:]);run=session/'run';run.mkdir()
plan=json.loads((stack/'pb/lab/plan.template.json').read_text());plan['xiso_path']=str(session/'giants.xiso.iso')
(session/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
shutil.copyfile(stack/'pb/lab/cmds.template.txt',run/'cmds.txt')
(session/'build-ready').touch()
PY
STAGE=awaiting-turn-2
printf 'DESIGN: build ready. Keep this coordinator alive. Turn 2: bash %q run %q\n' "$STACK/pb/lab/pb_lab.sh" "$SESSION"
# DESIGN: a continuous owner is necessary: an EXIT trap must not leave a disc between turns.
DEADLINE=$((SECONDS + 1800))
while [[ ! -f "$SESSION/run-turn-2" ]]; do
  if (( SECONDS >= DEADLINE )); then echo 'DESIGN: turn 2 timeout; deleting disc' >&2; exit 124; fi
  sleep 2
done
STAGE=run
# DESIGN: exactly one runtime attempt. Wait for Noah's VM after acquiring the lock.
setsid flock "$LOCK" bash -c '
  set -euo pipefail
  while pgrep -x xemu >/dev/null; do sleep 5; done
  exec nice -n 19 taskset -c 24-31 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
    python3 "$1/pb/lab/pb_runtime.py" --bake-dir "$2" --run-dir "$2/run"
' pb-run "$STACK" "$SESSION" > "$SESSION/runtime.log" 2>&1 &
CHILD=$!
wait "$CHILD"
CHILD=''
STAGE=complete
# DESIGN: normal completion also runs cleanup and deletes the lab disc.
