#!/bin/bash
set -u
cd "$(dirname "$0")/../.."
pids=()
setsid nohup python3 reports/b71_a7/run.py final-test_nfl2k5_owner_pairwise_composition python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -v >reports/b71_a7/owner-pairwise.launch.log 2>&1 </dev/null &
pids+=("$!")
echo "owner-pairwise pid=$!"
for group in presentation apf closure_units; do
    setsid nohup python3 reports/b71_a7/run.py "$group-suites" python3 reports/b71_a7/suites.py "$group" >"reports/b71_a7/$group.launch.log" 2>&1 </dev/null &
    pids+=("$!")
    echo "$group pid=$!"
done
setsid nohup python3 reports/b71_a7/run.py final-colour-all-pins python3 tools/verify_colour_lighting_pins.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --workers 4 >reports/b71_a7/colour-pins.launch.log 2>&1 </dev/null &
pids+=("$!")
echo "colour-pins pid=$!"
result=0
for pid in "${pids[@]}"; do
    wait "$pid" || result=1
done
python3 reports/b71_a7/run.py closures python3 reports/b71_a7/closures.py || result=1
exit "$result"
