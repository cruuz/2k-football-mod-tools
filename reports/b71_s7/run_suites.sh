#!/bin/bash
# Usage: run_suites.sh <tag> <test files...>  (sequential, one log per suite, summary in reports/b71_s7/<tag>-summary.txt)
cd /home/noah/2k-worktrees/fable-b71-s7 || exit 1
TAG=$1; shift
export PYTHONPATH=/home/noah/2k-worktrees/fable-b71-s7:/home/noah/2k-worktrees/fable-b71-s7/tools QT_QPA_PLATFORM=offscreen
: > reports/b71_s7/$TAG-summary.txt
for t in "$@"; do
  name=$(basename "$t" .py); start=$(date +%s)
  python3 "$t" > reports/b71_s7/$TAG-$name.log 2>&1; rc=$?
  line=$(grep -E "^(Ran [0-9]+ tests|OK|FAILED)" reports/b71_s7/$TAG-$name.log | tr '\n' ' ')
  echo "$name exit=$rc $(( $(date +%s) - start ))s $line" >> reports/b71_s7/$TAG-summary.txt
done
echo "ALL DONE" >> reports/b71_s7/$TAG-summary.txt
