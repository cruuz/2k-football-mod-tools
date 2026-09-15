#!/bin/bash
# Run from this worktree. The waiting supervisor keeps a sandbox exec session alive.
set -u
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." || exit 1
mkdir -p .scratch
setsid nohup env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 -u reports/b71_a5/build_testdisc71.py > .scratch/testdisc71.detached.log 2>&1 < /dev/null &
build_pid=$!
echo "$build_pid" > .scratch/testdisc71.pid
wait "$build_pid"
result=$?
echo "$result" > .scratch/testdisc71.exit
exit "$result"
