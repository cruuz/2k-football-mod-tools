#!/bin/bash
cd /home/noah/2k-worktrees/fable-b71-s8
export QT_QPA_PLATFORM=offscreen PYTHONPATH=/home/noah/2k-worktrees/fable-b71-s8:/home/noah/2k-worktrees/fable-b71-s8/tools
S=$(date +%s); python3 tests/mod_editor/test_nfl2k5_scorebug_sprite.py > reports/b71_s8/logs/test_nfl2k5_scorebug_sprite.log 2>&1; echo "exit $? seconds $(( $(date +%s)-S ))" >> reports/b71_s8/logs/test_nfl2k5_scorebug_sprite.log
S=$(date +%s); python3 tests/mod_editor/test_scorebug_sprite_preview_qt.py > reports/b71_s8/logs/test_scorebug_sprite_preview_qt.log 2>&1; echo "exit $? seconds $(( $(date +%s)-S ))" >> reports/b71_s8/logs/test_scorebug_sprite_preview_qt.log
echo DONE > reports/b71_s8/logs/native_sprite.done
