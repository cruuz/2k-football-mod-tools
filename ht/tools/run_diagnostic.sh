#!/usr/bin/env bash
# PROVED OFFLINE build workflow. No emulator, network, or public-disc-folder writes.
# Requires the prepared runner and both recipe copies under this private build root.
set -euo pipefail
HT_BUILD_ROOT=/media/noah/Storage/.b76-research/ht/astra-build
HT_STACK=$(realpath "$(dirname "$0")/../..")
HT_TARGET="$HT_BUILD_ROOT/ht-accessibility.xiso.iso"
mkdir -p "$HT_BUILD_ROOT/tmp" "$HT_BUILD_ROOT/evidence"
test ! -e "$HT_TARGET"
export TMPDIR="$HT_BUILD_ROOT/tmp"
export PYTHONDONTWRITEBYTECODE=1
export ULTIMATE_NO_REEXEC=1
python3 - "$HT_BUILD_ROOT" <<'PY'
import json,shutil,sys,time
from pathlib import Path
root=Path(sys.argv[1])
while True:
    space={p:shutil.disk_usage(p).free for p in ['/media/noah/Storage','/home/noah']}
    if space['/media/noah/Storage']>=30_000_000_000 and space['/home/noah']>100_000_000_000:
        (root/'evidence/full-build-start-space.json').write_text(json.dumps(space,indent=2)+'\n')
        print('PROVED OFFLINE: starting space',space,flush=True)
        break
    print('DESIGN: waiting for Storage >=30 GB and NVMe >100 GB',space,flush=True)
    time.sleep(30)
PY
# The existing shared lock is opened read-only; no other worktree file is written.
if [[ -f /home/noah/2k-worktrees/.b76-session/xemu.lock ]]; then
  exec 9</home/noah/2k-worktrees/.b76-session/xemu.lock
  flock -x 9
fi
python3 - <<'PY'
import shutil
assert shutil.disk_usage('/media/noah/Storage').free>=30_000_000_000
assert shutil.disk_usage('/home/noah').free>100_000_000_000
PY
# Delete only this workflow's target, including a published output after a failed check.
cleanup() {
  python3 - "$HT_TARGET" "$HT_BUILD_ROOT/evidence/iso-deletion.json" <<'PY'
import json,sys,time
from pathlib import Path
p=Path(sys.argv[1]); existed=p.exists(); size=p.stat().st_size if existed else 0
if existed:
    p.unlink()
Path(sys.argv[2]).write_text(json.dumps(dict(label='PROVED OFFLINE',path=str(p),
    existed=existed,size=size,exists_after=p.exists(),time_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())),indent=2)+'\n')
PY
}
trap cleanup EXIT
nice -n 10 taskset -c 0-23 python3 "$HT_BUILD_ROOT/build_ultimate_teams2026.py" "$HT_STACK" "$HT_TARGET" \
  --recipe "$HT_BUILD_ROOT/candidate_B_ht_accessibility_diagnostic.json" \
  --project /media/noah/Storage/.b76-research/main/freeze/candB/league_project_k2_v52_frozen.json \
  --roster-edits /media/noah/Storage/.b76-research/main/freeze/candB/league_roster_edits_candB_nofc.json
nice -n 10 taskset -c 0-23 python3 "$HT_STACK/ht/tools/check_build.py" "$HT_TARGET" \
  --summary "$HT_BUILD_ROOT/ht-accessibility.xiso.summary.json" \
  --output "$HT_BUILD_ROOT/evidence/full_build.json"
