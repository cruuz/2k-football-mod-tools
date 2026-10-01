#!/bin/bash
# DESIGN: main runs this after merging and rebuilding. Astra never invokes it.
# PROVED OFFLINE provenance: Anniversary pad sequence is m1/lab/m1e/cmds.txt.
# Usage: E2_DISC=/path/rebuilt.iso E2_RECEIPT=/path/rebuilt.build.json bash e2/lab_main.sh
# E2_STACK defaults to this checkout. Each case starts once under the shared lock.
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export E2_STACK=${E2_STACK:-$(dirname "$HERE")}
DISC=${E2_DISC:?set E2_DISC to the rebuilt combined disc}
RECEIPT=${E2_RECEIPT:?set E2_RECEIPT to that discs build receipt}
LAB=${E2_LAB:-/media/noah/Storage/.b76-research/e2/lab_E_e2p3}
LOCK=/home/noah/2k-worktrees/.b76-session/xemu.lock
mkdir -p "$LAB"
while pgrep -f '[b]uild_ultimate_teams2026.py' >/dev/null; do sleep 5; done
python3 - "$DISC" "$RECEIPT" <<'PY'
import hashlib,json,os,sys
out=json.load(open(sys.argv[2]))['result']['outcome']['output']
h=hashlib.sha256()
with open(sys.argv[1],'rb') as f:
    for b in iter(lambda:f.read(1<<24),b''):h.update(b)
assert os.path.getsize(sys.argv[1])==out['size'] and h.hexdigest()==out['sha256'], 'receipt mismatch'
print('PROVED OFFLINE: disc matches build receipt',h.hexdigest())
PY
export E2_CATALOG="$LAB/catalog.json"
python3 "$HERE/lab_verify.py" catalog "$DISC" "$E2_CATALOG"
RESULTS=$(mktemp "$LAB/case-status.XXXXXX.tsv")
printf 'case\tstage\texit_code\n' > "$RESULTS"
run_case() (
    # A separate subshell preserves errexit inside the case. Do not invoke this
    # function in an if/! condition, which would disable its errexit checks.
    set -e
    case=$1
    phase=prepare
    trap 'rc=$?; printf "%s\t%s\t%d\n" "$case" "$phase" "$rc" >> "$RESULTS"' EXIT
    case "$case" in
        original|super_bowl|moment50|mixed) ;;
        *) echo "DESIGN: unknown E2 case $case"; exit 2 ;;
    esac
    run="$LAB/$case"
    test ! -e "$run" || { echo "DESIGN: refuse to overwrite existing run $run"; exit 2; }
    mkdir -p "$run"
    phase=commands
    python3 - "$case" "$run/cmds.txt" <<'PY'
from pathlib import Path
import sys
case=sys.argv[1]
if case=='mixed':
    cmds=['mixed','wait 30','shot mixed-field']
else:
    ordinal={'original':1,'super_bowl':15,'moment50':50}[case]
    cmds=['tap DOWN 0.15 0.8','tap A 0.2 5.0','down 2','tap A 0.2 6.0','shot list']
    if ordinal>1:cmds += [f'down {ordinal-1}']
    cmds += ['wait 2','shot selected-row','tap A 0.25 6.0','shot named-preview',
             'peek preview-ordinal 0xbf1858 1','witness preview preview','tap A 0.25 4.0','shot assign',
             'tap START 0.3 2.0','shot loading-intro-early','wait 6','shot loading-intro',
             'wait 12','shot field']
cmds += ['peek mode 0xe5ff80 1','peek ordinal 0xbf1858 1',
         'peek home-book-name 0xb307d0 16','peek away-book-name 0xb30810 16',
         'peek bound-books 0xe5fe80 2','peek home-book-header *(int*)0xe5fe80+0x30 16',
         'peek away-book-header *(int*)0xe5fe84+0x30 16',
         'witness loaded books','watchx gameplay 60','shot after-play','quit']
Path(sys.argv[2]).write_text('\n'.join(cmds)+'\n')
PY
    phase=probe
    (
        flock 9
        while pgrep -f '[b]uild_ultimate_teams2026.py' >/dev/null; do sleep 5; done
        while pgrep -x xemu >/dev/null; do sleep 5; done
        cd "$E2_STACK"
        nice -n 19 taskset -c 24-31 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy \
            python3 "$HERE/lab_probe.py" --xiso "$DISC" --run-dir "$run" --minutes 12 \
            > "$LAB/$case.log" 2>&1
    ) 9>"$LOCK"
    # Keep exact guest-virtual memory slices, including both full bound PLAY bodies.
    # No full-RAM snapshot is needed and no witness .bin is deleted.
    phase=verify
    python3 "$HERE/lab_verify.py" verify "$run" "$case"
    echo "DESIGN: review $LAB/$case.log and $run/screens before accepting the case."
    phase=complete
)
failed=0
for case in ${E2_ONLY:-original super_bowl moment50 mixed}; do
    set +e
    run_case "$case"
    rc=$?
    set -e
    if (( rc != 0 )); then
        failed=1
        echo "PROVED OFFLINE: case $case failed (exit $rc); recorded in $RESULTS; continuing."
    fi
done
echo "PROVED OFFLINE: case exit statuses retained at $RESULTS"
cat <<'TXT'
DESIGN acceptance: original row 1 names Bart Starr and binds E2R-DAL/E2R-GB.
DESIGN acceptance: row 15 preview names Scott Norwood, says Super Bowl XXV and Tampa Stadium.
DESIGN acceptance: row 50 says Super Bowl LVIII, enters play and binds both stock aliases.
DESIGN acceptance: mixed Quick Game binds E2R-CHI on the historical side and an ordinary modern book on the current side.
DESIGN acceptance: e2-verification.json must verify retained full PLAY contents, pointers and per-side filenames; inspect gameplay frames for player selection and stalls.
DESIGN: art and rendered-game acceptance remain main's separate review. No automatic PASS is inferred from a script exit.
TXT
exit "$failed"
