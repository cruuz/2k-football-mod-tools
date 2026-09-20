#!/usr/bin/env bash
# Run the Coach Edwards workflow gate on the retail disc before a release.
#
# Import equipment art, save and reload the project, build a real disc through
# the real child builder and verifier, read the receipts back. Runs at the
# lowest CPU and I/O priority so it can go while the machine is in use, and
# writes 6 GB beside .scratch/coach-edwards-gate which it deletes again.
#
#   tools/coach_edwards_gate.sh            # runs and prints the log path
#   NFL2K5_RETAIL_XISO=/path/to.iso tools/coach_edwards_gate.sh
set -u
here="$(cd "$(dirname "$0")/.." && pwd)"
log="${NFL2K5_GATE_LOG:-$here/.scratch/coach-edwards-gate/last-run.log}"
mkdir -p "$(dirname "$log")"
echo "coach edwards gate -> $log"
cd "$here" || exit 2
NFL2K5_COACH_EDWARDS_GATE=1 nice -n 19 ionice -c3 \
  python3 -m pytest -q -s tests/mod_editor/test_b74_coach_edwards_gate.py 2>&1 | tee "$log"
exit "${PIPESTATUS[0]}"
