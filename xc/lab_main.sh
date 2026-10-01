#!/bin/bash
# DESIGN: main-only runtime follow-up. Astra does not run this script.
# DESIGN: regenerate the copy with tools/xdvdfs_compact.py, then set XC_DISC.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
STACK=$(dirname "$HERE")
DISC=${XC_DISC:?set XC_DISC to the compacted copy}
LAB=${XC_LAB:-/media/noah/Storage/.b76-research/xc/astra-build/lab}
LOCK=/home/noah/2k-worktrees/.b76-session/xemu.lock
python3 - "$DISC" "$HERE/evidence/disc-proof.json" <<'PY'
from pathlib import Path
import hashlib, json, shutil, sys
p = Path(sys.argv[1]).resolve()
assert p.is_relative_to(Path('/media/noah/Storage/.b76-research/xc/astra-build'))
assert shutil.disk_usage(Path.home()).free > 100_000_000_000
h = hashlib.sha256()
with p.open('rb') as f:
    for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
expected = json.loads(Path(sys.argv[2]).read_text())['output']
assert {'size': p.stat().st_size, 'sha256': h.hexdigest()} == expected
print('PROVED OFFLINE: lab input matches the verified compact copy')
PY
test ! -e "$LAB" || { echo "DESIGN: choose a fresh XC_LAB directory"; exit 2; }
mkdir -p "$LAB/moment50"
cat > "$LAB/moment50/cmds.txt" <<'CMDS'
tap DOWN 0.15 0.8
tap A 0.2 5.0
down 2
tap A 0.2 6.0
down 49
wait 2
shot selected-moment50
tap A 0.25 6.0
shot named-preview
peek preview-ordinal 0xbf1858 1
tap A 0.25 4.0
tap START 0.3 2.0
wait 18
shot loaded-field
peek mode 0xe5ff80 1
peek home-book-name 0xb307d0 16
peek away-book-name 0xb30810 16
tap A 0.2 2.0
watchx gameplay 60
shot after-play
quit
CMDS
(
    flock 9
    if pgrep -x xemu >/dev/null; then echo "DESIGN: shared xemu is busy; stop here"; exit 2; fi
    cd "$STACK"
    # PROVED OFFLINE: the shared harness uses Xvfb, an isolated writable HDD,
    # and --filesystem=DISC:ro for the DVD. Each command shuts down before the next.
    nice -n 19 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
        python3 tools/xemu_berman_probe.py --xiso "$DISC" --run-dir "$LAB/quick-falcons" \
        --home-team FALCONS --away-team-slot CHIEFS --minutes 3 --label xc-compact-mercedes-benz \
        > "$LAB/quick-falcons.log" 2>&1
    nice -n 19 env E2_STACK="$STACK" LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
        python3 e2/lab_probe.py --xiso "$DISC" --run-dir "$LAB/moment50" --minutes 10 \
        > "$LAB/moment50.log" 2>&1
) 9>"$LOCK"
echo "DESIGN: review both logs and screenshots: Falcons home at Mercedes-Benz, then moment 50's preview and live play."
echo "DESIGN: require a rendered play and advancing game clock in each case; a process exit is not runtime acceptance."
