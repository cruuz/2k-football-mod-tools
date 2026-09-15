#!/bin/bash
set -u
setsid nohup python3 reports/b71_s3/run_suites.py > reports/b71_s3/all-suites.log 2>&1 &
suites_pid=$!
wait "$suites_pid"
