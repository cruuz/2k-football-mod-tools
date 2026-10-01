# DESIGN: phase 1 Giants lab request (historical)

DESIGN: The authorized phase 2 [lab script and README](lab/README.md) supersede the launch commands, scratch location, retry allowance and expansion gate below. The original 26-case sheet is retained as an optional later sweep; the phase 2 single attempt uses ten cases in eight formations.

DESIGN: Main runs this lab after reviewing the recipe. Astra has not launched xemu. Run a headless Quick Game, NYG home versus DAL, human NYG offense, All Pro, five-minute quarters, clear weather. Use the SOFTDRINK roster and verify Isaiah Likely at TE1 before judging the TE concepts. The machine-readable [request](lab_request.json) contains 26 exact smoke plays covering all 16 concepts and 13 formation families, plus the sweep of all 26 offensive menus.

## DESIGN: build input and output

PROVED OFFLINE: The recipe uses the existing `BuildPlan.playbook_packs` path. Its source is the pinned retail NYG PLAY body, SHA-256 `8851c3093c51496b440b3cc3f833983b2c2014a6ede57e14fd0c1299e435f6ae`. A source with previous NYG PLAY changes is refused. Roster changes alone do not alter this pin. Do not reuse an already patched NYG book or stage individual v4 entries through the Playbooks dialog.

DESIGN: In main's current SOFTDRINK project Build plan, add the absolute path to `data/playbooks/softdrink_giants_modern.2k5book` to `playbook_packs`. Keep `read_option_runtime=False`. `playbook_pair` is unnecessary: this replaces the NYG club's own offense and leaves its defense in the same book. For the first smoke, leave it false and use the NYG book. Do not add another offensive pack targeting NYG. A separate defensive pack can install afterward through Build. Use a fresh output path in main's own Storage lab area.

PROVED OFFLINE: The source XISO is 6,300,499,968 bytes, larger than this job's 4 GB scratch limit. No ISO copy was made in this job. DESIGN: main stores its build outside `/media/noah/Storage/.b76-research/pb/`, for example `/media/noah/Storage/.b76-research/main-pb-lab/giants.xiso.iso`. Maintain the NVMe free-space floor and keep screenshots/logs bounded.

DESIGN: A minimal byte/menu lab build, using the retail roster only, is reproducible with the following. For Likely identity and SOFTDRINK gameplay evidence, use the project Build flow above instead of this retail-only fixture. Run these commands from the integrated repository root. The directory must be new; the build does not overwrite an existing image.

```bash
python3 - <<'PY'
import json
from pathlib import Path
from mod_editor.core.mod_build import BuildPlan, build
lab = Path('/media/noah/Storage/.b76-research/main-pb-lab')
lab.mkdir(parents=True, exist_ok=True)
target = lab / 'giants.xiso.iso'
recipe = Path('data/playbooks/softdrink_giants_modern.2k5book').resolve()
plan = BuildPlan(
    source='/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso',
    target=str(target), playbook_packs=(str(recipe),),
    playbook_pair=False, read_option_runtime=False)
receipt = build(plan, lambda message, *_: print(message, flush=True))
(lab / 'build-receipt.json').write_text(json.dumps(receipt, indent=2))
(lab / 'plan.json').write_text(json.dumps({'xiso_path': str(target)}))
PY
```

DESIGN: When using main's SOFTDRINK build, write the same `plan.json` with `xiso_path` pointing to that exact new build. Preserve its Build receipt, recipe hash and final NYG PLAY hash. The isolated pack-only NYG resource hash is `86598ce68609cace419ca2db94359d4566f49b9b16494e5327a53e0d0f961a1c`; later explicitly selected PLAY features can legitimately change it.

## DESIGN: headless launch and observed control

PROVED OFFLINE: The existing runtime driver reads `plan.json`, starts an isolated HDD overlay and accepts commands from `run/cmds.txt`. Its default automated route selects ATL. `--skip-route` is required so main can choose NYG with observed OCR gates. `xvfb-run` hosts its nested Xephyr display without a desktop window. These commands have been inspected, not executed by Astra.

```bash
xvfb-run -a -s '-screen 0 1280x720x24' \
  python3 tools/xemu_play_author_runtime.py \
  --bake-dir /media/noah/Storage/.b76-research/main-pb-lab \
  --run-dir /media/noah/Storage/.b76-research/main-pb-lab/run \
  --skip-route \
  > /media/noah/Storage/.b76-research/main-pb-lab/runtime.log 2>&1
```

DESIGN: In a second main terminal, append one command at a time after observing the prior screenshot/OCR. Start with `ocr`, then use the driver's `tap`, `hold`, `release` and `shot` commands. Example command-file write:

```bash
python3 - <<'PY'
from pathlib import Path
commands = Path('/media/noah/Storage/.b76-research/main-pb-lab/run/cmds.txt')
with commands.open('a') as stream:
    stream.write('ocr\nshot 00-current\n')
PY
```

DESIGN: Observe PRESS START, settings/main menu, team selection, NYG home/DAL away, coach matchup and kickoff in order. Do not assume a fixed trigger-pulse count. Capture the team/book identity and TE1 depth-chart occupant. Enter formation play call, sweep both pages of every ordinary offensive formation, exit and re-enter, then execute each requested case through the snap and a dead ball. Return to play call after each. A selected diagram alone is not a played snap. Use the exact menu names/indices below and the screenshots to choose the displayed call button; do not hard-code an unobserved controller legend.

DESIGN: This first game is a smoke lab. If a single game cannot cover all cases, finish them in a second game or Practice and label the mode per case. Do not count missing cases as passes. Execute FG, punt, kickoff and defensive goal-line calls, plus default offensive audibles. For zone/screen/transfer behavior, supplement the smoke with even/odd fronts and both hashes in Practice.

## DESIGN: required case results and go/no-go

DESIGN: For each case save `{formation_index, play_index, mode, opponent_front, hash, menu_opened, snapped, assignment_observations, dead_ball, returned_to_menu, evidence_paths, result}`. Record successful actor behavior as well as failures. On runs inspect actual OL targets and HB/WR handoff; on counter/boot inspect pulling/rollout clearance; on screens inspect three releases, two protectors, HB location and throw/catch timing; on seams/drags inspect actual Likely identity and eligibility. A yardage gain does not excuse a broken assignment.

DESIGN: Return a lab report with menu freezes, failed transfers, frozen actors, wrong snap animation and mismatched roster roles called out. Main grants an explicit go before other team books are generated. Production approval should follow execution of all 148 catalog plays, not just this smoke or the offline replay. Middle screens, true duo and automatic jet motion remain held even if all included calls pass.

## DESIGN: smoke call sheet

PROVED OFFLINE: IDs below are zero-based PLAY indices. Page and position are one-based display coordinates from the authored menu.

| DESIGN formation | PROVED OFFLINE play ID | DESIGN concept | PROVED OFFLINE page / position |
| --- | ---: | --- | --- |
| Gun Trips R | 59 | Inside Zone | 1 / 1 |
| Gun Trips R | 60 | Counter | 1 / 2 |
| Gun Trips R | 61 | TE Seam | 1 / 3 |
| Gun Trips R | 62 | Levels | 2 / 1 |
| Gun Trips R | 63 | Flood | 2 / 2 |
| Gun Trips R | 64 | TE Drag | 2 / 3 |
| Gun Trips L | 65 | Outside Zone | 1 / 1 |
| Gun Trips L | 66 | Downhill | 1 / 2 |
| Gun Trips L | 68 | Y Cross | 2 / 1 |
| Gun Trips L | 69 | Drive | 2 / 2 |
| Gun Trips L | 70 | RB Slip | 2 / 3 |
| Gun Bunch R | 72 | End Around | 1 / 2 |
| Gun Bunch R | 74 | Dagger | 2 / 1 |
| Gun Bunch R | 75 | Stick | 2 / 2 |
| Gun Bunch R | 76 | Mesh | 2 / 3 |
| Singleback Ace R | 99 | PA Boot | 2 / 2 |
| Gun Empty R | 87 | TE Seam | 2 / 2 |
| Ace Wing R | 109 | TE Seam | 1 / 3 |
| Pistol Ace R | 121 | TE Seam | 1 / 3 |
| Gun Doubles R | 133 | TE Seam | 1 / 3 |
| Gun Y Trips R | 145 | TE Seam | 1 / 3 |
| Gun Wing R | 157 | TE Seam | 1 / 3 |
| Ace Bunch R | 169 | TE Seam | 1 / 3 |
| Pistol Wing R | 179 | TE Seam | 1 / 3 |
| UC Tight R | 207 | TE Seam | 1 / 3 |
| Pistol Strong R | 223 | TE Seam | 1 / 3 |
