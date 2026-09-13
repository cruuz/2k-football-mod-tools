# Beta 69 J5: toss deferral, decided clock, CPU escapes

All player-visible outcomes are **UNWITNESSED**. PROVED below means pinned USA
instructions or the named bounded Unicorn execution, not a boot, rendered menu,
physical kickoff, full AI simulation, or played game. Retail SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.

## Opening toss: CPU-only deferral

BigTimeEmpire requested “The ability to defer your choice on the coin toss to the
second half with logic that makes it occur as often as it does in the NFL.”

**Delivered fallback:** `Coin toss: CPU defer (modern, experimental; CPU winners only)`.
Human winners retain Kick/Receive. EXPERIMENTAL, OFF in every preset. Do not
advertise a human Defer option or recommend ADVANCED yet.

### PROVED retail map

| Site/state | Native meaning |
| --- | --- |
| `E602B4 = 0`, `B8170`, `B8260` | Toss phase, initialization, accepted heads/tails call. Period `E602C4` distinguishes opening toss from OT. |
| `25E9B0`, RNG `48B50` | Coin outcome; calls native winner assignment `B9930`. |
| `B72684` | Actual winner team pointer. `B993E/B9969` write home/away. |
| `C39188`, `C3918C`; `25E780..25E7B5` | Called face and result; equality selects away, inequality home. ESI is team, EDI side 1/2. |
| `B72688`, `B72680` | Choice team and its counterpart during the two-stage choice protocol. |
| `25DFC0`, `771F0` | Query assigned controllers for EDI side; nonzero means a human controls that side. |
| `17ED80`, `25E7E8..25E7F3` | Learned profile choice, if profile mode is 2 and counters exist. Draw modulo sum of words `profile+E9C/+E9E`; result chooses a row. Without a usable profile, default row 1, Receive. |
| `25E0C0` | Constructs two rows: Kick callback `25E580`, Receive callback `25E660`. The other team subsequently selects a direction. There is no existing third “Side” row in this menu. |
| `B82B0`, `E602F0` | Kick/receive callback records opening kicker; `B82F0`, `E602F4` record direction. |
| `B8200`, `E9460` | Finish toss and establish first kickoff possession/defense/direction. |
| `B8B30`, `B88C0`, `B8910` | End-of-Q2, halftime, advance to Q3 and native kickoff initialization. |
| `158643..15864C` | Retail second-half kickoff negates opening direction and selects the opponent of the opening kicker. It has no independent deferrer state. |
| `25EAF0` | Boolean toss-result consumer comparing called face/result. |

The owner hooks `25E7B5` (7 bytes), `25E81F` (5), `15864C` (5), and
`25EAF0` (6). It retains the real winner, records the CPU deferrer in its own
four-byte RW allocation, and transfers first-half kick/receive choice to the loser.
The menu notice becomes “CPU deferred. Choose for the first half.” A parity change
lets existing direction/choice callbacks follow the loser; the result wrapper
restores the original winner interpretation for `25EAF0`.

At halftime the deferring CPU chooses Receive, even if the first-half chooser
chose Kick. Direction and kickoff spot still use native initialization. The owned
state clears at each toss-menu initialization, including OT; only period 1,
phase 0 can set it. OT's possession-seen state and modified scoring rules are
untouched. Native kickoff has phase 2; PAT phase 3 and modern kick-rule spot
operands remain under the existing kick-rules owner.

### Attributed rate

Use **240/272 = 15/17 = 88.2353%**, the 2023 regular-season deferrals counted by
jpmSportsStats in [the author's 2023 coin-toss compilation](https://www.reddit.com/r/nfl/comments/198fkwh/2023_regular_season_coin_toss_data/).
The compilation reports 240 deferrals and 32 receives. This is a dated,
independently compiled season count, not an official NFL statistic or an asserted
2026 average. The native 32-bit generator's word modulo 17 defers in buckets
0–14; rejecting `FFFFFFFF` removes modulo bias under a uniform-word assumption.
The RNG's long-run distribution and actual in-game deferral frequency are not
calibrated by this test. Only CPU winners consume this additional random draw.

### Exact human-menu blocker

The native generic menu at `C38490` stores count at `+8` and rows at `+C`, stride
`228`. Only two rows fit before controller storage at `+45C`.
`1BE1FD: lea edi,[eax+esi+0xc]` computes row 2's address as menu `+45C`;
**`1BE219: mov [edi],edx` overwrites the controller with its callback**.
The test calls the real row constructor with two existing rows and observes that
overwrite. A fourth row is further outside the menu storage. This is a native
layout limit, not a missing harness renderer. A safe human Defer choice needs
relocation and verification of the generic menu, controller/input/render fields,
and all affected callers. No extra human row ships.

### Bounded native proof

`test_nfl2k5_b69_rules.py` executes native RNG, winner assignment, controller query,
two-row construction, actual callbacks, kickoff record/spot and halftime. Both
human sides and both human Kick/Receive choices run for CPU-wins and human-wins.
CPU deferral gives the loser the first choice and the CPU the Q3 receive. Human
winners match retail first/second kickoff teams. All 17 lottery buckets and OT
state reset are checked. The first kickoff's native spot magnitude is 1828.8 game
units. A toss-result-consumer assertion proves the real winner remains correct.

Accepted heads/tails, menu-row selection, scene acknowledgement and an end-of-Q2
situation are supplied input boundaries. Announcer, overlay and scene leaves are
explicitly stubbed in `tests/nfl2k5_b69_rules_native.py` and its clock base fixture.
No physical kick or rendered fourth option is claimed.

## Run out the clock when the game is decided (experimental)

CER asked “Is it doable to add the thing where the clock just auto goes to triple
0 in the 4th if the game isnt winnable like in one of the recent college football games?”

**Rule:** selected convenience cutoff, default **lead at least 17 points and
remaining time at most 60 seconds**. Margin choices 9/17/25/33; time choices
15/30/60/90/120 seconds. This does not calculate timeout-adjusted possessions or
prove mathematical elimination; a turnover comeback may still be possible.
The Build help must say so. EXPERIMENTAL, OFF in every preset.

The game must be active (`A83A18 == 3`), period exactly 4, phase 4 (scrimmage),
state 12 (huddle) or 18 (dead ball), and the canonical possession/defense teams
must be opponents. Score words come from `[team+8]`; the possessing team must
lead by the selected margin. The positive finite countdown is `[E6028C]+10`.
Paused/count-up timers, malformed scores, other phases, live state 14, ready
state 13, trailing possession and every OT period bypass the writer.

### PROVED hooks and composition

* `B6E80` displaces `mov eax,[E602B4]`. Huddle `B8650` calls this native helper
  at `B86A0`, before the accelerated-clock owner's `B86E0` hook. Replay the load
  and continue at `B6E85`.
* `A03DC` wraps the call to native `189080`. Native dead-ball command `A0390`
  has already called `B7230`, settling state 18 and possession before this hook.
* Both wrappers preserve flags/general registers; the decision uses no x87
  operations and writes only the game-clock float to zero. Retail dispatch owns
  period/game completion. No live-frame hook is installed.

Accelerated clock keeps its own four hooks, RX code, RW latch and RO settings.
Its final-two-minute exclusions are unchanged. Paired native huddle results:
Q4 60s, margin 16 => 60/40 game/play clocks; Q4 60s, margin 17 => 0/40;
ordinary 600s => 580/20 with accelerated On/20. Both application orders match.

The native series fixture runs scene selection, ready input, snap, one native
presented frame and native dead-ball command. After the live frame every case is
state 14 at 59.8666687s. Only decided Q4 becomes state 18 at 0s; margin 16,
trailing possession and period 5 stay at 59.8666687s. See
`reports/b69_j5/native_series.json`. Existing scene/device/animation seams remain
declared by `tests/nfl2k5_b68_series.py`. The fixture supplies a completed-play
command; it does not simulate a tackle, referee, scoreboard, or postgame flow.

## CPU QB scrambles: retail / modern (experimental)

BigTimeEmpire asked “And to get the CPU QB to scramble at NFL averages”.

**Delivered bounded lever:** Modern changes one conditional escape probability
factor from .25 to .50. It does **not** claim NFL-average scrambles per game.
EXPERIMENTAL, Retail in every preset.

### PROVED passing-AI map

* Task initializer around `19C700` installs callback `19BB60` at `19C849`.
  Player `+20` points to task state, active task pointer at `+310`.
* Its embedded countdown timer is at task `+50`, remaining float at `+60`.
  Initialization `19C7D4..19C7F6` derives duration from effective attribute `15`
  (composure), sets it, clears count-up bit 8, then starts it through `AF510`.
  The duration formula in that path is .5 + .5 times effective composure.
* `19BBA8` obtains effective Scramble (attribute `19`) through `17B010`, stored
  in the routine's local `+20`. Receiver candidate/coverage scorer `1985E0` and
  tests `19BDAD..19BDCE` precede the no-acceptable-candidate path `19BF19`.
  A current target and profile-specific bypass also affect eligibility.
* Pressure helper `19A8B0`, called at `19C077`, contributes a float and output
  flags. A composure curve at `50C884` also contributes upstream. The helper's
  physical pressure metric is not fully characterized; calling it “number of
  rushers” or a particular distance threshold would be a HYPOTHESIS.
* `19C120` compares the pressure local against `.925`; the `test ah,41` path to
  `19C352` is taken for values at or below that threshold. An earlier lottery
  supplies the attempt flag; `19C352` requires ESI nonzero.
* `19C356..19C365` requires the timer local **greater than .25**, not expired or
  less than .25. `19C367` loads effective Scramble. `19C36C` multiplies by the
  retail .25 word at `4E696C`. `19C375` calls lottery `197DE0`, using native
  float RNG `48B90`. Success branches through `19C380` to `2E36F0`.
* Escape initializer `2E36F0` sets task flag `+584 |= 200`, movement mode `+18C`
  to the appropriate masked `820` bits, callback `+194 = 2E0B30`, calls `1D1EF0`
  with mode 8, and sets task byte `+3FE = 30`. Subsequent gates install run
  tasks `2E3650` or `2EE090`. Physical tucking/running is UNWITNESSED.
* Global `BE47EC` is a throw/pump-action holdoff deadline: reset `1984B5`, set
  at `19BFD8/19C1C9` to current time plus 1.5 after action `46+id`, read in
  passing-action gates including `19BAE0/19C315`. It is not a general scramble
  timer and this writer does not shorten it.

Only the six-byte multiply at `19C36C` is hooked. Modern applies for state 14,
phase 4, native CPU steering sentinel `[player+C][0] == -1`, raw roster position
`[player+3C]+35 == 0` (QB). Other callers use the original .25. General flags,
EAX and x87 depth are preserved. Timer, pressure, coverage and roster words are
unchanged. The adjacent defensive-try call at `2E3786` must be either retail or
the complete verified defensive-try owner; a foreign branch is refused.

Under identical supplied caller locals (effective Scramble .8, pressure .9,
timer .5, attempt true), the native comparison/RNG/branch region has **21/100
retail vs 41/100 modern** escape-initializer entries, with every retail hit
retained. The 100 draws are a deterministic grid, not sampled games; inclusive
comparison explains the endpoints. Human, non-QB and non-live inputs match
retail. Timer <= .25 and false attempt remain excluded. The complete upstream
AI routine is mapped but not executed end to end by this proof.

### The roster bit and Slow-QB acceleration are different mechanisms

`2D92A4` loads raw Scramble byte `roster+4F`; `2D92B1` isolates bit 0.
The surrounding native `2D9290` selects an animation/blend record. A separate
sum of normalized Scramble and Agility chooses another tier. Bit 0 selects
directional table families `AD2048/AD2068/AD2088` or stationary families
`AD1388/AD1468`. It returns the record pointer at `2D9589`; caller `2DA497`
stores the selection at descriptor `+D0` at `2DA4B1`.

The complete native selector and its rating/interpolation helpers execute with
identical supplied player/roster/vector state: raw Scramble 10 => `AD13E8`,
11 => `AD14C8`. There is no lottery call in this selector run. Thus the observed
bit consumer proves animation-family selection, **not scramble frequency**.
This corrects any suggestion that the bit alone was an established frequency
control; it does not claim an exhaustive absence of all other consumers.

Existing `nfl2k5_scramble_tuning.py` hooks acceleration interpolation at
`1DF1A5`: attached live QB carriers with raw Speed <=60 receive a private
65% acceleration curve, retaining first-step floor/top speed and native factors.
Human and CPU carriers are both affected. It does not change the leave-pocket
decision; the new probability owner composes with it in both orders.

Roadmap: run matched games across QB ratings, pressure and coverage settings;
count dropbacks, escape entries, sacks, designed runs and actual QB scrambles
separately. Only then fit a factor to an attributed season-level scramble rate.
The .50 experiment establishes one causal branch lever, not that calibration.

## Owned-space contract and witness plan

Three new owners request 896 RX instruction bytes, 4 RW state bytes and 140 RO
bytes, before alignment. There are seven allocation records. No runtime state
is stored in `.text`. All hooks, dependencies, settings, relocation/padding,
allocator seals and offline-zero RW state are checked. `status/apply/verify`
reparse the output, replay byte-identically, and refuse partial/foreign installs
or a changed installed setting. Reserve the complete selected union before
applying any owner. All Off means no writer/no allocation.

`reports/b69_j5/allocation_delta.json` compares the complete gate union with and
without these requests: 27 existing allocation addresses move; their geometries
are unchanged. The existing scaleout file extent remains 12,300,288 bytes.
Production cave manifest regeneration is required after integration. The gate's
strict test projection verifies new live hooks and relocates named children;
it does not regenerate or claim a new disc-build manifest.

Witness each option on a freshly integrated test build:

1. CPU defer: both human home/away, both toss winners, loser Kick and Receive,
   notice/menu controller access, direction selection, actual first kickoff,
   halftime and actual second kickoff; repeat nondeferral and OT. Check the
   announcer/winner text and controller prompts. Human Defer is unavailable.
2. Decided clock: a completed tackle/incompletion, possession change, score/PAT,
   all timeouts, paused/unpaused, clock/scorebug/postgame statistics, both leading
   sides, margin/time edges, OT and a trailing offense. Repeat with accelerated
   clock Off/On and the final-two-minute rule. Confirm no physical play is cut
   short and postgame starts normally after the zero.
3. CPU scrambles: matched retail/modern games, human control and controller
   handoff, slow/fast QBs, pressure/coverage variation, designed runs separately;
   observe actual pocket exit and tucking, sacks, animation and carried-ball
   speed. Repeat with Slow-QB acceleration and read option/defensive try enabled.
