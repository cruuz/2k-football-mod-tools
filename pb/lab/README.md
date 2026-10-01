# DESIGN: main-only two-turn Giants lab

DESIGN: This phase 2 operator procedure is historical. Main uses the non-interactive [defense lab](DEFENSE_LAB.md) for current work. Phase 4 replaces `v7.pb.json` with the real v7 recipe plus only the current playbook keys, preserving production owners. Astra does not run xemu.

DESIGN: Turn 1 runs `bash pb/lab/pb_lab.sh build` from this worktree. Keep that process alive after it prints `build ready`. It owns the disposable disc and its EXIT/HUP/INT/TERM cleanup trap. From a second terminal, turn 2 runs the printed `bash pb/lab/pb_lab.sh run SESSION` command. The first process remains the owner until the lab ends. A 30-minute timeout between turns also deletes the disc. Uncatchable SIGKILL or power loss cannot execute any shell trap; in that event main must remove the abandoned session ISO before another attempt.

PROVED OFFLINE: `v7.source.json` is the byte-for-byte v7 source copy; `v7.pb.json` is the edited lab copy. It resets unrelated assets and gameplay patches to this stack's `BuildPlan` defaults, retains the two defense packs and ATL gun pack after an in-memory composition check, and adds the approved Giants pack. `read_option_runtime` and `playbook_pair` are false, and the option pack is omitted. No original Desktop recipe was edited. This is a minimal retail-roster fixture: it does not install Likely or establish his identity. The league recipe in `../recipes/all_teams.json` is separate and keeps defense/special teams retail.

DESIGN: The build uses Desktop `ultimate/build_ultimate.py` with this worktree as STACK, retail as SOURCE and a new disc under `/media/noah/Storage/.b76-research/pb/lab/session.*/`. The disc is never placed on NVMe. Turn 1 holds `/home/noah/2k-worktrees/.b76-session/xemu.lock` and uses `nice -n 10 taskset -c 0-23`. The builder enforces its 100 GB NVMe and 20 GB Storage free-space floors. The requested disposable disc temporarily exceeds the phase 1 4 GB scratch cap because retail alone is 6.3 GB; this is the phase 2 disc placement explicitly requested by main. Logs and small receipts remain after cleanup; the ISO and HDD overlay are removed.

DESIGN: Turn 2 reacquires that lock and waits while `pgrep -x xemu` succeeds. It then makes one launch at `nice -n 19 taskset -c 24-31 env LP_NUM_THREADS=4 SDL_AUDIODRIVER=dummy`. The runtime uses Xvfb, isolated config/firmware, `mem_limit = '128'`, localhost gdb and QMP, and a verified qcow2 overlay over Noah's HDD. The flatpak sees the backing HDD read-only. The shared u5 probe's historic-team rejection and observed home/away selection are reused. Its weather/RAM hooks are disabled. No automatic retry or second game is allowed.

DESIGN: Stages check the following:

1. Build: recipe resolution, pack composition and final Build menu validation. Build/summary receipts and `plan.json` remain in SESSION.
2. Team Select: current GIANTS at home, current COWBOYS away, virtual human controller returned to home. Keep the team-select frame. Main sets All Pro, five-minute quarters and clear weather through observed menus if the copied settings differ.
3. Opening possession: main advances the coin toss, kickoff and any Dallas possession with observed `tap`, `hold`, `release`, `shot` and `ocr` commands. Stay in the same game; a missing Giants possession is incomplete, never a pass.
4. Play-call page: main navigates to each listed formation/page and appends `case N`. All three numbered play labels and the formation header must OCR correctly before selection. Failure stops the attempt. `X/A/B` select the left/middle/right card, as on the inspected retail page. The selected page is saved as `NN-playcall.png`.
5. Snap: after seeing the correct Giants lineup, append `snap N`. The macro saves a pre-snap frame, taps A once, keeps four frames around the snap input and a mid-play frame. For a pass, main appends the observed receiver button in time to throw. Capture timings do not prove a snap, throw or catch occurred.
6. Review: after the dead ball and return to menu, append `result N NOTES` describing the actual actor behavior, snap, possession, freeze status and result. This saves an after frame. Main inspects zone blocks, transfers, TE routes and screen releases. Ten recorded cases with operator notes permit `finish`; `quit`, any error or any missing case leaves the attempt incomplete.

PROVED OFFLINE: Ten requested cases use eight distinct formations:

| DESIGN case | PROVED OFFLINE formation | PROVED OFFLINE play | PROVED OFFLINE page / button |
| ---: | --- | --- | --- |
| 1 | Gun Trips R | 59: Inside Zone | 1 / X |
| 2 | Gun Trips L | 65: Outside Zone | 1 / X |
| 3 | Gun Bunch R | 76: Mesh | 2 / B |
| 4 | Gun Trips L | 68: Y Cross | 2 / X |
| 5 | Gun Empty R | 87: TE Seam | 2 / A |
| 6 | Ace Wing R | 109: TE Seam | 1 / B |
| 7 | Pistol Ace R | 124: TE Drag | 2 / B |
| 8 | Gun Y Trips R | 147: RB Slip | 2 / A |
| 9 | Gun Bunch R | 72: End Around | 1 / A |
| 10 | Singleback Ace R | 99: PA Boot | 2 / A |

DESIGN: Example commands, appended only after observing the prior frame:

```bash
# DESIGN: SESSION is the directory printed by the still-running coordinator.
printf '%s\n' 'ocr' 'shot current' >> "$SESSION/run/cmds.txt"
printf '%s\n' 'tap DOWN 0.15' >> "$SESSION/run/cmds.txt"
# DESIGN: after navigation to case 1's exact page:
printf '%s\n' 'case 1' >> "$SESSION/run/cmds.txt"
# DESIGN: after observing the Giants pre-snap lineup:
printf '%s\n' 'snap 1' >> "$SESSION/run/cmds.txt"
# DESIGN: replace the notes below with main's actual observations:
printf '%s\n' 'result 1 NOTES_FROM_MAIN' >> "$SESSION/run/cmds.txt"
```

DESIGN: The watchdog samples a reduced frame each second. An unchanged frame or failed captures for over 60 seconds stops the attempt and records an INFERRED freeze candidate. A stage that makes no confirmed progress for over 60 seconds also stops, even if background animation continues; this can be an operator timeout, so the reason is recorded separately. Inputs do not reset the deadline. The one-hour outer attempt limit and signal cleanup bound failures. `result.json` keeps all attempted cases, timings and evidence paths, but its `CAPTURED_FOR_REVIEW` outcome is not gameplay approval.

PROVED OFFLINE: Checks executed by Astra are shell syntax, Python compilation, protocol/watchdog unit tests and the in-memory recipe composition gate. Neither stage of `pb_lab.sh`, the runtime driver, `build_ultimate.py` nor xemu was executed by Astra. The actual launcher, OCR route and captures await main's run.
