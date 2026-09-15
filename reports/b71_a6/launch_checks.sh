#!/bin/bash
set -u
python3 reports/b71_a6/run.py registry-final python3 -m mod_editor.capabilities.validate_registry
python3 reports/b71_a6/run.py repin-final python3 packaging/repin.py --apply
python3 reports/b71_a6/run.py manifest-production bash reports/b71_a6/manifest_regen.sh
# Storage is read-only in this session. This explicitly non-release projection
# observes the full XBE writer stack without copying a disc.
python3 reports/b71_a6/run.py manifest-projection python3 reports/b71_a6/refresh_manifest_projection.py || exit $?
for group in fast gates presentation apf; do
    setsid nohup python3 reports/b71_a6/suites.py "$group" > "reports/b71_a6/$group-suites.log" 2>&1 < /dev/null &
    pids+=("$!")
done
status=0
for pid in "${pids[@]}"; do wait "$pid" || status=1; done
exit "$status"
