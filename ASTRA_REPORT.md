# Beta 69 J5: modern game rules

Implemented three opt-in, owned-space writers with verifiers, a non-overwriting
CLI, assembly sources and bounded native proofs. **Every in-game outcome is
UNWITNESSED. All options are EXPERIMENTAL and OFF/Retail in every preset.**
Build/registry integration is supplied in [WIRING.md](WIRING.md), as requested;
no protected Build, GUI, registry, packaging-check or production-manifest file
was edited. Detailed instruction findings and the full witness list are in
[the research report](docs/research/nfl2k5_b69_rules.md).

Read `ASTRA_CONTEXT.md`, the J5 brief, hub beta-68 triage rows 22/25/26, and the
existing overtime, kick-rules, accelerated-clock and slow-QB tuning owners.

## Delivered behavior and limits

| Request | Delivered | Proof boundary |
| --- | --- | --- |
| BigTimeEmpire: “The ability to defer your choice on the coin toss to the second half with logic that makes it occur as often as it does in the NFL.” | **CPU winners only.** CPU defers with nominal probability 15/17. Loser chooses Kick/Receive for the first half; CPU receives in Q3. Human winners retain retail choices. | Native toss through first kickoff records and native halftime/Q3 kickoff for both human and CPU winners, both human sides and both first-half choices. No rendered menu or physical kick. |
| CER: “Is it doable to add the thing where the clock just auto goes to triple 0 in the 4th if the game isnt winnable like in one of the recent college football games?” | Optional fourth-quarter cutoff, default leading possession by >=17 points with <=60s. Selectable margin/time. Writes 0 at the next native dead ball/huddle. | Native series: live frame survives; decided dead ball zeroes the timer; undecided/trailing/OT retain it. No postgame/scorebug witness. This is a convenience cutoff, not mathematical elimination. |
| BigTimeEmpire: “And to get the CPU QB to scramble at NFL averages” | Retail/Modern experiment changes one existing conditional escape factor .25 -> .50. | 21 -> 41 escape-branch hits under the same 100 native inputs. Overall NFL-average scramble frequency is **not** established. |

CPU rate source: jpmSportsStats' [2023 regular-season coin-toss compilation](https://www.reddit.com/r/nfl/comments/198fkwh/2023_regular_season_coin_toss_data/),
240 deferrals/272 games = 15/17 = 88.2353%. This is a dated independent count,
not a claimed current 2026 average or an official NFL statistic. Modulo-17
sampling rejects `FFFFFFFF`; actual RNG/gameplay frequency still needs measurement.

The native menu supports two rows, with direction selected afterward. Attempting
row 3 computes menu `+45C` at `1BE1FD`, then **`1BE219: mov [edi],edx` overwrites
the controller field**. The test executes that exact overwrite. A fourth choice
is outside the same object. This is why the user-authorized CPU-only fallback
ships, with the explicit caption `Coin toss: CPU defer (modern, experimental; CPU winners only)`.
Human Defer needs generic menu relocation and input/render/caller proofs. The
deferrer word is runtime-only; game save/load persistence is not implemented
or proved.

## Instruction-level conclusions

PROVED by pinned bytes / bounded native execution:

* Toss phase `E602B4=0`; RNG/winner `25E9B0 -> B9930`; winner pointer `B72684`;
  native two-row menu `25E0C0`; CPU profile choice `17ED80`, default Receive;
  opening kicker/direction `E602F0/F4`; retail halftime `158643..15864C`
  reverses the opening kicker/direction. A new RW deferrer word overrides the
  Q3 receive choice without changing the real winner or OT state.
* Decided-clock hooks `B6E80` and `A03DC` compose with the accelerated-clock
  owner's earlier mapped huddle flow. State 14 stays live; state 18 is settled
  before zeroing. Only active period 4, phase 4, leading canonical possession,
  selected margin/time and finite countdown qualify. Accelerated clock's four
  hooks, latch, settings and final-two-minute exclusions are unchanged.
* CPU passing callback `19BB60`, installed at `19C849`, uses an embedded task
  countdown and effective Scramble. The mapped branch at `19C120..19C380`
  includes pressure <=.925, an upstream attempt flag and timer >.25 before
  the Scramble lottery. Hook `19C36C` changes only its multiplier for live CPU
  QBs. Escape initializer `2E36F0` sets run-task/movement state. Defensive try's
  neighboring call at `2E3786` is accepted only retail or fully verified.
* Raw Scramble `roster+4F` bit 0 is consumed by native animation selector
  `2D9290`, isolated at `2D92B1`, returned as a record at `2D9589`. Identical
  fixtures with Scramble 10/11 return `AD13E8/AD14C8`. This proves the observed
  bit consumer's animation-family role, not frequency. Numeric effective
  Scramble separately participates in the AI probability.
* Existing Slow-QB acceleration at `1DF1A5` gives attached QB carriers with
  Speed <=60 a 65% acceleration curve. It does not decide when the CPU runs.

HYPOTHESIS / unfinished measurement: interpreting `19A8B0`'s pressure output as
a specific physical metric; full AI eligibility frequencies; physical pocket
exit/animation; statistical RNG distribution; NFL-average calibration; menus,
timeouts/penalties/postgame behavior over played games. No such result is claimed.
The full upstream passing AI was mapped, not run end to end. The branch proof
supplies caller locals and executes native comparisons, RNG and destinations.

## Files, allocation and safety

New core: `nfl2k5_rules_patch.py`, three `nfl2k5_{coin_defer,decided_clock,cpu_scrambles}.py`
owners and their three generated `_code.py` templates. Development CLI:
`tools/nfl2k5_modern_rules.py`; assembler/checker `tools/nfl2k5_rules_assemble.py`
and three `.S` sources. Tests: focused rules/CLI, native toss fixture, native
series, complete gate union and new owner pair matrix. Changelog bullets under
RC94 beta 69 quote both reporters.

Seven new allocator records request **896 RX +4 RW +140 RO bytes** before
alignment. Runtime state never enters `.text`. All own hooks are exact-pattern
checked; prerequisites are hashed, allocations/settings/code/padding reparse,
offline RW must be zero, replay is identical, and foreign/mixed/reconfigured
installs refuse. OFF skips writers and requests. The CLI opens a new output
exclusively, verifies it first, and removes a partially written new output on error.

**Allocation changed.** [allocation_delta.json](reports/b69_j5/allocation_delta.json)
records seven additions and 27 existing allocation-address moves in the full
gate union. Existing geometry is unchanged and scaleout size remains 12,300,288
bytes. **Claude must regenerate the production cave manifest** after integrated
wiring/final union and repin. The test-only manifest projection verifies new
live hooks and relocates named allocations; it is not a new disc-build manifest.
No retail XBE, disc, save or asset is committed; retail is read-only.

The first full-stack run identified the defensive-try overlap in a broad scramble
prerequisite hash at `2E3786`. The final verifier checks native slices around it
and requires that call to be retail or the complete defensive-try owner. A
foreign-call regression and both install orders pass. No older owner was changed.

## Verification

Commands run standalone from this worktree, with the private pinned USA XBE and
Unicorn/Capstone present. Missing retail/Unicorn has precise skips in the tests.
Final logs are in `reports/b69_j5/`.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_b69_rules.py` | 16 tests, OK (133.447s). |
| `NFL2K5_B69_RULES_SERIES_TRACE=reports/b69_j5/native_series.json python3 tests/mod_editor/test_nfl2k5_b69_rules_series.py` | 1 series test / four scenarios, OK (73.363s). |
| `python3 tests/mod_editor/test_nfl2k5_accelerated_clock.py` | 40 tests, OK (47.533s). |
| `python3 tools/nfl2k5_rules_assemble.py --check` | All three templates verified. |
| Proposed registry (in memory) | 164-row schema/semantics OK; all three new rows' commands and evidence files checked. Whole-registry file check stops on pre-existing missing `docs/research/apf_audio.md`. |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 119 tests, OK (1787.272s). |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 131 tests, OK (2045.808s). |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 475 tests, OK (3235.993s). |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 29 tests, OK (423.534s), normal protected manifest; no scratch-manifest override. |

Focused pairs include all new owners, accelerated clock, kick rules, overtime and
Slow-QB acceleration. The complete matrix adds all three owners to the existing
31-entry owner list; each compatible pair tests both application orders and
replay. Native clock results: ordinary 600 ->580/20 paired game/play clocks;
final-minute undecided 60/40; decided 0/40. The series's live timer is
59.866668701171875 in all four cases, and only decided Q4 zeroes at dead ball.

All four required XBE gates are green before the final commit: **754 tests, OK**.
The seven standalone suites total **811 tests, OK**, without skips.
Final repin output is recorded in `reports/b69_j5/repin.log`.

## Required player witness and roadmap

Noah / BigTimeEmpire: both human sides and toss winners, first-half Kick/Receive,
notice/winner text and controller access, actual kicks, halftime, repeated game
start and OT. Human Defer remains unavailable. Test CPU scrambles in matched
games with fast/slow QBs, pressure/coverage variation, controller handoff and
the existing acceleration/read-option options. Count actual scrambles separately
from designed runs and sacks before any NFL-average claim.

Noah / CER: completed tackles and incompletions, turnovers, PAT/kickoff phases,
timeouts, pause, both leading sides, cutoff edges, trailing possession and OT;
repeat with accelerated clock Off/On. Confirm no play is ended early, the visible
clock reaches 0:00 and native postgame/statistics complete normally. Full witness
matrix and instruction details are in the research document.

## Commit delivery in the restricted worktree

The shared worktree Git directory is read-only under this session's managed
permissions. Normal staging failed creating
`/home/noah/2k-football-mod-tools/.git/worktrees/astra-b69-j5/index.lock`.
Approval is unavailable. No other checkout or shared Git metadata was modified.

Commits therefore use a separate writable Git directory under the system temp
directory, with this worktree and read-only alternates to the base object store.
Its path is recorded in the local `ASTRA_GIT_DIR.txt`. Branch
`astra/b69-j5-rules` starts at `922c009d`; implementation commit `f17fc38d` and proof/handoff commit `8d6db047` are
already preserved there. The final delivery includes **ASTRA_J5.bundle**, containing
the branch's commits after that base. The ordinary worktree HEAD stays at the
base because its shared metadata could not be written.

Integrator, in an authorized checkout with the base present:

```sh
git fetch /absolute/path/to/ASTRA_J5.bundle astra/b69-j5-rules:astra/b69-j5-rules-import
git log --oneline 922c009d..astra/b69-j5-rules-import
git cherry-pick 922c009d..astra/b69-j5-rules-import
```

All commits use explicit paths. `packaging/repin.py --apply` runs after pinned
writer edits and immediately before commits; new owners need packaging/source-pin
integration, so this isolated job's repin reports zero existing pin updates.
Bundle verification and final commit identity are supplied with the delivery.
