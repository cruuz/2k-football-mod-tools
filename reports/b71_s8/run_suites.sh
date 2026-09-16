#!/bin/bash
cd /home/noah/2k-worktrees/fable-b71-s8
export QT_QPA_PLATFORM=offscreen PYTHONPATH=/home/noah/2k-worktrees/fable-b71-s8:/home/noah/2k-worktrees/fable-b71-s8/tools
: > reports/b71_s8/logs/suites.summary
for t in tests/mod_editor/test_nfl2k5_scorebug_sprite.py tests/mod_editor/test_scorebug_sprite_preview_qt.py tests/mod_editor/test_nfl2k5_scorebug_mnf.py tests/mod_editor/test_nfl2k5_scorebug_runtime.py tests/mod_editor/test_nfl2k5_scorebug_exact.py tests/mod_editor/test_nfl2k5_scorebug_resources.py tests/mod_editor/test_nfl2k5_scorebug_assets.py tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py tests/mod_editor/test_nfl2k5_scorebug_native.py; do
  n=$(basename $t .py); S=$(date +%s); python3 $t > reports/b71_s8/logs/$n.log 2>&1; rc=$?; echo "$n exit $rc seconds $(( $(date +%s)-S )) $(grep -E '^Ran ' reports/b71_s8/logs/$n.log | tail -1)" >> reports/b71_s8/logs/suites.summary
done
echo DONE >> reports/b71_s8/logs/suites.summary
