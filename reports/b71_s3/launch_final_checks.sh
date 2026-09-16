#!/bin/bash
set -u
setsid nohup python3 reports/b71_s3/run_final_suites.py > reports/b71_s3/final-suites.log 2>&1 &
suites_pid=$!
python3 reports/b71_s3/run_logged.py manifest-release python3 reports/b71_s3/refresh_manifest.py
manifest_result=$?
if [ "$manifest_result" = 0 ]; then
  setsid nohup python3 reports/b71_s3/run_logged.py xbe-memory-release python3 tests/mod_editor/test_xbe_patch_memory_writes.py > reports/b71_s3/xbe-memory-release.launch.log 2>&1 &
  memory_pid=$!
  setsid nohup python3 reports/b71_s3/run_logged.py xbe-caves-release python3 tests/mod_editor/test_xbe_patch_cave_references.py > reports/b71_s3/xbe-caves-release.launch.log 2>&1 &
  caves_pid=$!
  wait "$memory_pid"
  memory_result=$?
  wait "$caves_pid"
  caves_result=$?
else
  memory_result=1
  caves_result=1
fi
wait "$suites_pid"
suites_result=$?
[ "$manifest_result" = 0 ] && [ "$memory_result" = 0 ] && [ "$caves_result" = 0 ] && [ "$suites_result" = 0 ]
