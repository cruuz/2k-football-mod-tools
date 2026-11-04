#!/bin/bash
# b780 rst2: a roster-edits document plus a nflverse pull -> the final 128 MB release roster (Q41-Q49, Q42 rerun).
#   rst2_pipeline.sh BASE.json NFLVERSE_DIR OUT_DIR AS_OF      (NFLVERSE_DIR holds roster_2026.csv, depth_charts_2026.csv, injuries_2026.csv)
# Steps: create (a record, ratings and headshot tone for every ACT/INA player the plan lacks; idempotent), update (every club's
# membership, chart and specialists from the pull, healthy starters), finalize (stale special_teams, Ole Miss fold, birth
# date, Nelson's contract, room_policy "ir", special row defaults), coach records (32/0/0), capacity receipts for the grown base.
# Then derive the 64 MB variant: python3 tools/nfl2k5_roster_retail_fit.py fit --edits OUT/final128.json --base $BASELINE --out OUT/final64.json --drop-xbe-sections
# New players that appear in a later pull need their headshots first (tools/b780/rst2_headshots.py fetch/convert/append) and a tones file.
set -e
BASE=$1; NV=$2; OUT=$3; ASOF=$4
REPO=$(cd "$(dirname "$0")/../.." && pwd)
BODY=${RST2_V08_ROST_BODY:-/home/noah/2k-worktrees/.b77-scratch/b780/c6-carousel/state/v08_rost_body.bin}
BASELINE=${RST2_REFRESH_BASE:-/home/noah/2k-worktrees/.b77-scratch/i4/inputs/ro1/baseline.body}
HS=${RST2_HEADSHOT_WORK:-/home/noah/2k-worktrees/.b77-scratch/b780/rst2/hs}
mkdir -p "$OUT"; cd "$REPO"
RUN="nice -n 19 ionice -c2 -n7 taskset -c 16-31 timeout 1800"
$RUN python3 tools/b780/rst2_create_players.py create "$BASE" "$NV/roster_2026.csv" "$NV/depth_charts_2026.csv" "$OUT/created.json" --body "$BODY" --as-of "$ASOF" --work "$HS/work" --tones "$HS/tones.json" --report "$OUT/created_report.json"
$RUN python3 tools/b780/roster1_refresh_update.py "$OUT/created.json" "$NV/roster_2026.csv" "$NV/depth_charts_2026.csv" "$OUT/updated.json" --as-of "$ASOF" --body "$BODY" --summary "$OUT/updated_summary.json" --injuries "$NV/injuries_2026.csv" > "$OUT/update.log"
$RUN python3 tools/b780/rst2_create_players.py finalize "$OUT/updated.json" "$NV/roster_2026.csv" --out "$OUT/finalized.json" > "$OUT/finalize.log"
$RUN python3 tools/nfl2k5_coach_2026_data.py edits "$OUT/finalized.json" "$OUT/coach.json" > "$OUT/coach.log"
$RUN python3 tools/b780/rst2_create_players.py capacity "$OUT/coach.json" --base "$BASELINE" --out "$OUT/final128.json" > "$OUT/capacity.log"
sha256sum "$OUT/final128.json"
