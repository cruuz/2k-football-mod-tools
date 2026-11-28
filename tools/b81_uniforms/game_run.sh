#!/bin/bash
# game_run.sh TAG DISC SECONDS [route args...] : one private xemu run (own Xvfb display, keyboard pad, qcow2 overlay over the
# read-only HDD baseline), stills in emu/<TAG>/shots. Run through slot.sh emu.
set -uo pipefail
E=/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/emu
TAG="$1"; DISC="$2"; SECS="$3"; shift 3
D=157; while [ -e /tmp/.X11-unix/X$D ]; do D=$((D+1)); done
cd "$E"; mkdir -p evidence
export RG3_ID="b81uni$TAG" RG7_MEM=128 EMU1_CAP_S=${EMU_CAP:-840} OMP_THREAD_LIMIT=1 LP_NUM_THREADS=4
rm -f "drv$RG3_ID.sock"
taskset -c 16-31 nice -n 19 python3 -u drv.py serve --name "$TAG" --disc "$DISC" --display $D > "evidence/$TAG-session.log" 2>&1 &
SVC=$!
for i in $(seq 1 225); do [ -S "drv$RG3_ID.sock" ] && break; kill -0 $SVC 2>/dev/null || break; sleep 0.4; done
if [ -S "drv$RG3_ID.sock" ]; then
  timeout $((EMU1_CAP_S - 40)) python3 -u game_route.py "$TAG" "$SECS" "$@" > "evidence/$TAG-route.log" 2>&1; RC=$?
  python3 drv.py cmd '{"op":"stop"}' > /dev/null 2>&1
else RC=97; fi
wait $SVC 2>/dev/null
echo "EMU_EXIT $RC" >> "evidence/$TAG-route.log"
exit $RC
