#!/bin/bash
cd /home/noah/2k-worktrees/fable-b71-s8
export QT_QPA_PLATFORM=offscreen PYTHONPATH=/home/noah/2k-worktrees/fable-b71-s8:/home/noah/2k-worktrees/fable-b71-s8/tools
SHOT="/home/noah/Desktop/2K5-8 Editors/beta71_evidence/disc_n_2.png"
[ -f "$SHOT" ] || SHOT="/home/noah/Downloads/ksnip_20260916-043627.png"
S=$(date +%s)
python3 -m mod_editor.core.nfl2k5_scorebug_sprite preview --screenshot "$SHOT" --state '{}' --aspect both --output reports/b71_s8/standard.png > reports/b71_s8/logs/preview_standard.log 2>&1
python3 -m mod_editor.core.nfl2k5_scorebug_sprite preview --screenshot "$SHOT" --state '{"event":"FLAG"}' --aspect both --output reports/b71_s8/flag.png > reports/b71_s8/logs/preview_flag.log 2>&1
python3 -m mod_editor.core.nfl2k5_scorebug_sprite preview --screenshot "$SHOT" --state '{"away":"DAL","home":"KC","possession":"away","down":1,"distance":10,"quarter":1,"clock":300,"play_clock":19,"away_score":0,"home_score":0}' --aspect both --output reports/b71_s8/dal_kc.png > reports/b71_s8/logs/preview_dal.log 2>&1
echo "exit $? seconds $(( $(date +%s)-S ))" > reports/b71_s8/logs/previews.done
