#!/bin/bash
set -u
python3 reports/b71_s3/run_logged.py manifest python3 reports/b71_s3/refresh_manifest.py || exit $?
setsid nohup python3 reports/b71_s3/run_logged.py xbe-memory python3 tests/mod_editor/test_xbe_patch_memory_writes.py > reports/b71_s3/xbe-memory.launch.log 2>&1 &
memory_pid=$!
setsid nohup python3 reports/b71_s3/run_logged.py xbe-caves python3 tests/mod_editor/test_xbe_patch_cave_references.py > reports/b71_s3/xbe-caves.launch.log 2>&1 &
caves_pid=$!
wait "$memory_pid"
memory_result=$?
wait "$caves_pid"
caves_result=$?
[ "$memory_result" = 0 ] && [ "$caves_result" = 0 ]
