# Beta-63 kickoff/punt muff verification

2026-09-09. Branch `astra/hf63-kickoff-muffs`, inspected base
`9c17c538847c4fc7511f127bae538f2c6bb5874a` (`beta-63`, 1.0.0rc87).

**Decision: no kickoff writer change. The reported failed catches remain
unverified, not fixed or cleared.** The v6 receipts demonstrate no late-returner,
missed-catch-window or persistent native muff-flag defect, because they supply
contact after bypassing those decisions. They cannot establish that a returner
arrives in time. There is also a separate, reproducible catch-slider interaction
at the native roll boundary that belongs in Noah's first witness comparison.
It is not evidence that shanethepain used that setting or that his returns
reached that boundary with those inputs.

The brief explicitly makes a kickoff change conditional on a demonstrated
defect. I have followed its report/witness branch rather than altering hold,
aim, catch odds, presets or allocations without the missing evidence. No new
feature, production code, protected file or historical receipt is changed.

## Report and release identity

The local Discord dump `2k5-general.jsonl`, rows 6–7, contains shanethepain's
September 8, 19:53 report about **both** kickoffs and punts and SOFTDRINKTV's
20:50 dynamic-kickoff question. There is no answer identifying his preset,
dynamic option, interception slider, returner, roster, control mode or build
hash. Beta 62 is the supplied context; the message itself contains no build
identity. This does not establish a dynamic-only failure.

The September 7 ledger B6 combines andrethealchemist's failed catches/alignment
report with other people's blocking complaints. Those are distinct symptoms.
`ASTRA_DISCORD_BUGS_2_REPORT.md:368` already separated them and explicitly left
muff rates and punts unresolved at lines 404–420.

| Revision | What was actually corrected | Failed-catch conclusion |
| --- | --- | --- |
| A–D and v2 | In-field touchback eligibility, held pose, return-blocking assignments/targets, play card | No catch/muff-rate correction |
| v3 | Collision displacement, residual movement and turn-spring writers during the hold | No arrival-to-catch replay |
| v4 | Hold from individual lineup completion; readiness and head pose | No catch-window correction |
| v5 | Receiving stance lifecycle and stale/fallback kicker pursuit by blockers | Catch supplied at carrier's root; not a muff reproduction |
| v6 | End-zone catch proceeds through native kneel animation/event; return commentary is deferred; uncaught end-zone ground contact ends the play | Post-contact presentation/rule fix, not failed-catch fix |

The brief's “beta 62 v5 / beta 63 v6” shorthand is **not** the local tagged
source history. Both release bodies were inspected in
`/home/noah/Desktop/2K5-8 Editors/`. The beta-62 body includes v5 **and v6**;
its later morning-witness entry says kickoff v6 was fine. Its earlier v6 item
still says unwitnessed. The release title embedded in Discord says v5. These
labels do not identify the executable in a tester's disc.

The peeled local tags settle the source comparison:

| Tag | Commit | Dynamic writer revision |
| --- | --- | --- |
| beta-62 | `77d1c49f682e380b75f1a7290a806a47845608a9` | v6 |
| beta-62.1 | `c736ac437a6e250e8f1c225a974778ca77ed7070` | Same |
| beta-63 | `9c17c538847c4fc7511f127bae538f2c6bb5874a` | Same |

All three have SHA-256
`0f2a618ce8ad2443a472145fa69a7d06e0f78af1e9f7ce211ed9b35b00e6a6e7`
for `mod_editor/core/nfl2k5_dynamic_kickoff.py`, and
`211063695451178000aa7088245ddef8c31973f08fad490341a378bf6e8a6b4f`
for its relocated backend. Commit `d5945c80` re-recorded the v6 receipt for
the beta-63 allocator union; it did not change either writer. Noah's “fine”
is useful historical testimony, not a controlled muff-rate measurement.

## Native producer and what the caves affect

Addresses below are retail USA Xbox VAs, checked against the read-only local
Ghidra corpus under `research/functions/nfl2k5/pseudo_c/` in
`/media/noah/Storage/for codex 1.0/`, and focused disassembly of the pinned XBE.
The XBE SHA-256 is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
No corpus or retail binary is copied into this delivery.

1. **Approach inputs.** `tools/nfl2k5_kickoff_alignment.py:85` places the two
   receiving slots at lateral ±400 cm, receiving 1 and 5 (rounded formation
   coordinates). `nfl2k5_kickoff_returns.py:32` preserves their first three
   native Start/Run To Point/Follow nodes; only the noncarrier alternate block
   changes. This preserves an assignment, not proof of successful execution.
   The hold predicate at `nfl2k5_dynamic_kickoff.py:301–338` excludes receiving
   slots 0/1 and the kicker. It applies to nineteen other roles on normal
   phase-2/type-8 kickoffs. The original planning/motion paths remain available
   to both returners. The owner's `returner` helper at line 485 requires an
   **existing ball holder** before selecting an end-zone kneel; it does not
   manufacture a catch decision.
2. **Flight/descent.** The aim hook at `222E67` changes CPU range, elevation
   (45 degrees) and heading, normally targeting receiving 5–15 with probability
   90%. Human kicks retain their inputs. Launch is `222CA0`. The actual loose
   ball frame route is `11A7C0 -> 1CCFA0 -> 1C9A90 -> 1C78D0`.
   `1C9A90` integrates height/vertical speed using constants −490.3317566 and
   −980.6635132 cm/s². The separate launch test checks six direction/tee
   combinations and an ideal projected target within 0.02 yard (1.83 cm).
   It explicitly does **not** replay wind, collisions or returner arrival.
3. **Catch opportunity/window.** `1C78D0` enumerates eligible player collision
   objects and their positions, including a 365.76 cm broad-phase distance
   bound. This is not a guaranteed catch radius. `1C6100 -> 1C52C0` produces
   a swept ball/body contact mask. Descriptor eligibility (`1C5D30`) and
   `1C7740 -> 1C6610 -> 1E3500` then gate catch-capable contacts. The latter
   selects a mask from `50EB40` using bits 10–11 of the current animation
   record and intersects it with `0x7BC000`; `1C7740` rejects a missing eligible
   overlap and can reject an earlier noncatch body contact. Thus the relevant
   “window” is native geometry/animation eligibility, not the v6 kneel timer
   or a fixed countdown in the kickoff cave.
4. **Outcome.** At `1C8317`, the native decision draws the random value, compares
   it with the computed probability at `1C831C`, and checks a separate veto.
   Success enters `1C71D0`, calls `A0F20 -> B7820` for catch bookkeeping,
   then `DDCD0 -> 26A4A0 -> A0870` attaches the ball. Failure instead reaches
   `1CB020` and `A2CA0`/`A0F60`;
   these call native drop/contact bookkeeping `1CF6B0`/`1CF730` and `B78C0`.
   **A touch at B78C0 alone is not proof of a catch.** The failure bookkeeping
   includes `E3C010 |= 2`, a player-state `+584 |= 0x10000`, and contact history.
   These are distinct from the kickoff owner's ten-byte state. Its flags are
   contact class, active/direction/touchback preference, returned and force-40;
   none is a native muff flag. The commentary hook `A7930 -> 1E91F0` is an event
   producer downstream of this distinction, not the catch outcome producer.

The existing native role/reset tests passed. This establishes their bounded
guards and clears, not the absence of every possible stale engine flag or
interaction in a composed game.

## What the beta-63 receipt proves numerically

`docs/nfl2k5_kickoff_v6_receipts.json` is **361,273 bytes**, SHA-256
`0e9e1cfc11b42f92c11565c91b61fd515f9b4c96be07fb2da401e773746a497f`.
It contains **52 allocator request rows, 20 hooks, 1,939 code bytes, 10 state
bytes, 26 cases and 1,649 frames**. The older v6 report's 359,186-byte file and
grown hashes predate the beta-63 re-recording.

| Recorded group | Cases | Frames | Actual input |
| --- | ---: | ---: | --- |
| v6 caught end zone, 1/6 yards deep, two directions/placements | 8 | 496 | Supplied catch on frame 0; whistle frame 60; next record frame 61 at 35 |
| v6 field returns, receiving 1/3, two directions/placements | 8 | 720 | Supplied catch on frame 0; 90 live frames each |
| Historical v5 field-return comparisons | 4 | 360 | Same supplied catches; rows exactly match v6 |
| v6 uncaught end-zone ground contacts | 4 | 8 | Supplied ground callback; next record on frame 1 |
| Retail/v5 end-zone counterexamples | 2 | 65 | Supplied catches; kneel/presentation comparison |

That is **22 supplied catches, 4 supplied ground contacts, zero recorded
precontact approach frames and zero measured arrival margins**. The field-return
rows gain 14.600213 yards between frames 0 and 89; this is movement **after**
attachment. For direction +1, receiving-1 starts at an explicitly placed
4480.56 cm, is already at 4465.559570 cm in row 0, and reaches 3130.516113 cm
in row 89. Receiving-3 has the analogous 4297.68 / 4282.679688 / 2947.636230 cm
positions. These numbers cannot be used as flight/arrival measurements.

The reason is explicit in `test_nfl2k5_kickoff_v6.py:46–91`: `begin_catch`
launches, places the returner at the chosen spot, aliases the caught ball's
position to that player's root, and injects `B78C0`, `DDCD0`, `2EE1F0` during
the frame. The row's `height_cm` is **player-root height**, not falling-ball
height. `tests/nfl2k5_kickoff_frame.py:62` also leaves ball-list `E537F0` empty.
Instrumenting `1C78D0` in a complete v6 legacy end-zone catch replay (62 frames)
and ground replay (2 frames) produced **zero calls** in both; `1CCFA0` still
ran as a frame phase. Counting all 27 phase entries therefore does not prove
the native catch path ran. V5's 580/604-frame return runs also start from an
explicitly supplied catch (`test_nfl2k5_kickoff_v5.py:325`).

Current receipt output identities, not full-disc identities:

- Legacy kickoff output: `9b0481a73c03f43bc3b1162d21dd7a51f32e668464c83110a741984c24618164`.
- Allocated union input: `189623ac1633846b174a90f01a06b4410b3863104a51bcacd3b6cb2b6e1072c2`.
- Relocated kickoff output: `1b94b5cd73dd24830d692532d559641ff85c3f9081373dcfe301729dd74cd504`.

The allocated union reserves other owners' space; this receipt does not install
and exercise all preset owners, notably the catch-slider hook.

## Separate interception-slider diagnostic

`mod_editor/core/nfl2k5_catch_slider.py:92–115` hooks the shared `1C8317`
random call. A catcher whose team differs from `E60280` takes its “defender”
branch, which returns `random / (2 * Interception)`. It has no kickoff, punt
or forward-pass discriminator. At Interception 0 a positive draw becomes
infinity; a zero draw produces an unordered result. Both reject even a
supplied catch probability of 1 in the real subsequent native comparison.
Interception 50 restores the original draw. A kick receiver can have that
opposite-team identity before possession changes; the kickoff fixture starts
with the kicking team at `E60280`, and its successful catch is injected before
the normal decision could test this.

This is a **bounded decision-boundary counterexample**, not a full kick/punt
reproduction. The probe supplies probability 1, no veto, opposite-team catcher,
kicked-ball kind 3, phase 2 or 4, and draws 0/0.05/0.5/0.99. It executes the
installed RNG hook and unmodified `1C8312` success/failure branch with the code
section read/execute protected, stopping before outcome handlers. It does not
produce the incoming geometry, animation mask, probability or team state from
a live kick. The reporter's interception setting is unknown. This provides
a specific witness discriminator, not grounds for a speculative kickoff fix.

All **128 bounded decisions** completed. Each cell below counts the native
success branch out of eight supplied decisions (four draws × two phases).
These are deterministic probe counts, not estimated gameplay catch rates.

| Installed owners | INT 0 | INT 25 | INT 50 | INT 100 |
| --- | ---: | ---: | ---: | ---: |
| Retail | 8/8 | 8/8 | 8/8 | 8/8 |
| Dynamic kickoff only | 8/8 | 8/8 | 8/8 | 8/8 |
| Catch-slider only | 0/8 | 4/8 | 8/8 | 8/8 |
| Dynamic kickoff + catch-slider | 0/8 | 4/8 | 8/8 | 8/8 |

The standalone probe and its complete results are retained locally at
`.scratch/hf63-kickoff-muffs/probe.py` and `probe-results.json`. Its arithmetic
can also be reproduced with the repository's existing private-fixture helper:

```sh
PYTHONPATH=. python3 - <<'PY'
from tests.nfl2k5_catch_cave_emulation_test import RETAIL_XBE, _run
from mod_editor.core import nfl2k5_catch_slider as cs
p, _ = cs.apply(RETAIL_XBE.read_bytes())
for slider in (0.0, 0.25, 0.5, 1.0):
    value, _ = _run(p, 0.5, human_catching=0.5, cpu_catching=0.5,
                    interception=slider, catcher_on_offense=False,
                    offense_is_human=False)
    print(slider, value, value < 1.0)
PY
```

Observed output: `0.0 inf False`, `0.25 1.0 False`, `0.5 0.5 True`,
`1.0 0.25 True`.

## Presets and exact witness for Noah

The beta-63 definitions in `mod_editor/core/mod_build.py:317–370` give:

| Preset | Dynamic / alignment | Catch-slider fix | CPU returner fix | Kicking option |
| --- | --- | --- | --- | --- |
| Basic (`softdrink_basic`) | Off / off | On | On | More power, 2004 spots |
| Advanced (`softdrink_advanced`) | Off / off | On | On | Modern spots/power |
| Experimental (`softdrink_experimental`) | On / on | On | On | Modern spots/power |

Relocated kickoff is off in all three. Enabling dynamic implies alignment and
modern kick rules, and disables the separate kick-power option
(`mod_build.py:1084`). The CPU-returner fix is franchise depth-chart selection
at `2BDE70`; it does not change the native catch probability. The kickoff PLAY
writer changes normal Kick Return books, not punt-return assignments. Thus
no observed preset can be blamed yet; a shared catch-slider interaction could
affect traditional kickoffs and punts as well as dynamic kickoffs.

Use fresh retail-based images built by **beta-63**, with recorded build receipt
and XBE hash. Do not layer patches onto the reporter's old disc. Keep the same
stock teams/roster, explicitly selected KR/PR, All-Pro difficulty, clear weather,
fatigue/sliders and camera; record actual player identity and ratings. Set both
Human and CPU Catching to 50. Count **20 catchable kicks and 20 catchable punts
per row**, ten in each direction, using CPU fielding first and no user catch,
dive or fair-catch input. Record clean catches, touched-but-loose muffs,
untouched misses and post-possession fumbles separately. Exclude direct end-zone
ground touchbacks and out-of-bounds kicks from catch opportunities.

| Image / setup | Exact option differences | Interception | Purpose |
| --- | --- | ---: | --- |
| Unmodified retail control | No Studio owners | 50 | Establish ordinary kickoff and punt behavior |
| Basic default | `dynamic_kickoff=false`, `kickoff_alignment=false`, `catch_slider=true` | 50, then 0 | First test of shared-slider explanation on traditional kicks and punts |
| Basic, slider fix disabled | Uncheck **Fix Catching & Interception sliders**; other Basic options identical | 0, then 50 | Does removing only this hook remove the failure? |
| Experimental default | **Dynamic kickoff: ready stance and close blocks** and alignment on; slider fix on | 50, then 0 | Same test with dynamic alignment/hold |
| Experimental, slider fix disabled | Same dynamic settings; uncheck only **Fix Catching & Interception sliders** | 0, then 50 | Separate catch hook from dynamic behavior |
| Experimental, traditional control | Dynamic, **Dynamic kickoff alignment**, and relocated option all off; other options match the preceding row | 50 | Separate dynamic behavior from remaining Experimental owners |

For a dynamic-only failure at neutral Interception with the catch hook off,
repeat Advanced default and Advanced with only dynamic enabled. Use Return
Middle first, then Return Left/Right; central normal kicks landing at receiving
5, 10 and 15, plus 1/3 and end-zone controls. Film launch, returner travel,
descent, first touch and the following possession. Include both deep slots,
then repeat human-controlled receiving without extra input and kickoff practice
after a prior diving catch. For punts, use the ordinary Punt Return Middle
call, clear-lane high punts, and repeat separately from kickoffs.

If Int 0 fails with the catch hook on for both kick types and succeeds with
only that hook off (or Int 50), pursue the **catch-slider owner**, not the
kickoff hold. If only dynamic kicks fail, a trace must capture ball position
and vertical velocity, both returners' positions, selected descriptor/animation
mask, `1C78D0` eligibility/probability/roll, actual holder and failure flags
through first contact. If every controlled row succeeds, the universal symptom
is not reproduced under those settings; it does not prove other settings safe.

## Validation and handoff

| Command / check | Result |
| --- | --- |
| `PYTHONPATH=. python3 -u tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 tests, 41.065 s, OK; no skips |
| `PYTHONPATH=. python3 -u tests/mod_editor/test_nfl2k5_kickoff_v6.py` | 9 tests, 128.676 s, OK; no skips; compares all saved cases and exact patch receipt |
| Additional `1C78D0` entry observation | Caught 62-frame and grounded 2-frame v6 legacy runs: 0 entries each |
| `PYTHONPATH=. python3 -u .scratch/hf63-kickoff-muffs/probe.py` | 128 native decision-boundary runs completed; results above; exit 0 |
| Tag/source comparison | Both kickoff writer hashes identical at beta-62, beta-62.1, beta-63 and this base |

There is no red/green production regression to claim: the report's failed
catch was not reproduced through its full producer, and no fix was applied.
No `--record`, repin, or complete XBE gate rerun is called for on this
documentation-only branch. The 32 existing tests passed without weakening
fixtures or assertions. The scratch probe's first run stopped on an inspection
helper mistake (`_Section` has no `name`); the corrected probe locates the code
section by VA. An intermediate run using the old page-at-a-time fixture loader
was interrupted for runtime; the completed run maps the same bounded address
space in one allocation and removes its hook after each case. No product or
existing test source changed. Final report whitespace and unchanged-writer/
receipt hash checks passed.

**Claude handoff:** retain the muff item as unresolved, with the slider
comparison first. Do not describe v6 or its 52-request receipt as a muff fix.
No protected integration change, `WIRING.md`, provider repin or manifest
regeneration is needed **from this branch**. Reopen the relevant writer only
with a reproduced producer-level defect. No emulator, GUI, audio, network,
retail mutation, disc build or push was performed. Delivery uses an explicit
path commit of this report; the supplied brief/context and local scratch
evidence are excluded.
