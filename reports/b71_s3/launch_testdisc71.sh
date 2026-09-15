#!/bin/bash
set -u
mkdir -p .scratch/testdisc71h
setsid nohup python3 reports/b71_s3/build_testdisc71.py > .scratch/testdisc71h/build.log 2>&1 &
build_pid=$!
echo "$build_pid" > .scratch/testdisc71h/pid
wait "$build_pid"
result=$?
echo "$result" > .scratch/testdisc71h/exit
exit "$result"
