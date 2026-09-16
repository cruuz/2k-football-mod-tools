#!/bin/bash
set -u
cd "$(dirname "$0")/../.."
pids=()
for suite in test_nfl2k5_cave_oracle test_nfl2k5_allocator_scaleout test_xbe_patch_memory_writes test_xbe_patch_cave_references; do
    setsid nohup python3 reports/b71_a7/run.py "final-$suite" python3 "tests/mod_editor/$suite.py" -v >"reports/b71_a7/$suite.launch.log" 2>&1 </dev/null &
    pids+=("$!")
    echo "$suite pid=$!"
done
result=0
for pid in "${pids[@]}"; do
    wait "$pid" || result=1
done
exit "$result"
