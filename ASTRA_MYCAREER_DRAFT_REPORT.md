# MyCareer M3: draft, Senior Bowl preparation and upgrades

EXPERIMENTAL / UNWITNESSED. No played witness, emulator boot, display, audio
or network was used. Work remains confined to this worktree. Protected
integration is specified in the final MyCareer M3 section of `WIRING.md`.

## Implementation

The generic Game Modes entry now prepares a native first draft, creates
MyPlayer with the existing CAP templates, places that record in the rookie
class, and opens Senior Bowl preparation. Default seed-1 selection in the
existing Senior Bowl data tier includes MyPlayer. Continuing runs the
existing ratings/need draft AI and native pick/signing/cleanup routines;
the acquired player returns to the same Apartment. An undrafted player uses
the existing club-selection and native free-agent signing path without
reinitializing the franchise or changing the career token.
Native preseason leaves all 32 clubs at 54 players. An undrafted career
therefore offers an explicit confirmation to let the chosen club make room.
After confirmation, the pinned native cut routine reduces that club to 53
and the existing signing routines add MyPlayer as its 54th player. Released
players enter the native free-agent list. Cancellation changes no roster;
other clubs keep their players. With Practice Squad installed, its validated
capacity helper supplies the 53-player limit and preserves the reserve tail.
Fresh free-agent entry retains its existing full-roster refusal. No franchise
reset or forced draft pick is involved.

The Apartment adds Upgrades and the next fixture's week, date and time.
Purchases use the existing played-appearance award of 25 XP. Ordinary
attribute bytes cost 10/15/25/40/60 XP at the documented rating thresholds.
Role skills cap at 99, physical/general skills at 90, unrelated specialist
skills at 75. These caps constrain purchases, never lower a native or
template rating. Styles, identity, position and contracts are excluded.
Quotes validate manager, primary ordinal, creation token, rating and XP
again at confirmation; cancellation, stale input and replay consume the
quote without purchasing. Save/load reuses the existing 128-byte footer.

## Reservation and compatibility

M3 requests 16,384 RX bytes and 8,192 RW bytes split across two named
4,096-byte allocations. The extra owner is `nfl2k5_my_career_m3`, fixed at
`0x1505000`, the previously spare final RW page. The allocator packs all
existing owners using the previous MyCareer footprint, then places M3's
expanded code after them. It adds no page and leaves every other owner's
raw offset, VA, size and alignment unchanged. The old MyCareer state also
stays at its original address. Old 8 KiB code reservations refuse before
mutation and must rebuild from base.

The exact emitted size, before/after plans, peer allocations and available
capacity are in `tools/mycareer_mode/m3_budget.json`. Reproduce them with
`python3 tools/mycareer_mode/measure_m3.py`. The older pre-M3 shortfall receipt
in `docs/nfl2k5_my_career_m3_budget.json` remains historical evidence.

| Full budget union | Before | M3 |
| --- | --- | --- |
| MyCareer RX VA / bytes | `0x14DDEF0` / 8,192 | `0x14E5270` / 16,384 |
| Original RW VA / bytes | `0x14F33D0` / 4,096 | unchanged |
| Additional RW VA / bytes | none | `0x1505000` / 4,096 |
| RX requested / capacity | 52,631 / 106,496 | 60,823 / 106,496 |
| RW requested / capacity | 79,226 / 86,016 | 83,322 / 86,016 |
| General RO plus directory | 12,376 / 20,480 | unchanged |
| XBE bytes | 12,300,288 | unchanged |

The emitted machine code is 10,666 bytes; code plus immutable tables and
templates is 14,893 bytes, followed by padding and a 17-byte format tag.
M3 has 1,474 spare RX bytes. The union has 36,240 allocatable RX bytes,
8,104 RO bytes and no allocatable RW span. The remaining 2,694 RW bytes are
fragmented padding. The receipt compares all 45 pre-existing allocation
records other than the moved MyCareer code, including its old state and
Senior Bowl's unchanged 65,536-byte state. The budget tests also compare
minimal, full gate and every peer-pair union.

## PROVED and limits

PROVED means bounded execution or exact bytes, never a played witness.
The validation receipt and standalone test table below identify the exact
sources, commands, outcomes and memory bounds. These cover all-position CAP
placement and seed-1 selection, native AI signing and cold identity,
all-position purchase caps, unchanged peer allocations, and native glyph
submission for the calendar and upgrade screens.

Placement preserves all generated prospects. It adds the created player as
the 381st eligible record and, when necessary, exchanges its complete
84-byte record with the same-position record at the seed-1 selection index.
Both records retain their name/history pointers; no generated prospect is
deleted, rerated or renamed. Membership scans run before the exchange.
This is a deliberate index placement, not an invented Senior Bowl outcome.

Fast draft tests declare their input: the pinned f0 franchise is loaded
natively, then supplied with year 1, Combine stage 4, week 0 and end 1,
plus a declared prior-season club order of 0 through 31.
Most cases set Preseason on to bound execution; the low-rated kicker case
sets it off and executes all five native preseason weeks and roster cuts.
They use native CAP and the native RNG seeded with 2. The all-position
placement cases keep template ratings; separate AI experiments explicitly
set ordinary attributes to 99 or 0 after CAP's last template application.
Those experiments measure selection under actual ratings/need logic,
not a forced pick. A zero-rated quarterback can still be selected for need;
the undrafted test therefore uses a zero-rated kicker.

These fast tests do not prove the prior-season bootstrap. A separate
continuous native replay starts from retail ROST and advances the actual
league with seed 12345. It passed in 28 progress frames, completed native
CAP, placed MyPlayer at primary index 1991, and selected him among 106
Senior Bowl participants from the 381-player class. The receipt is
`tools/mycareer_mode/m3_bootstrap_receipt.json`: 1,683.518 seconds and
155,580 KiB peak RSS. Signing, purchase and cold load are separate bounded
proofs. Scene/device/font
submission seams and supplied played-game event inputs are documented in
the fixtures. No physical match, Xbox disk completion or visual witness is
claimed by those seams.

The native draft proof required a fixture correction: the existing harness
mapped XBE sections but omitted its header page, where the applied draft-AI
constants and another existing free-agent hook live. The harness now maps
the bounded header, and the positive AI test checks its 80-byte constants
against the installed owner's bytes. Early AI outcomes and the earlier
bootstrap fault before this correction are excluded from final proof.
No change to the existing draft-AI implementation was needed.

The long preseason test exposed another fixture precondition: f0's absent
prior-season ordering is 32 `FF` bytes. Advancing its supplied year-one state
through preseason and into next-schedule generation treated 255 as a club
at native `0x2BF1E6`. Supplying an explicit valid 0..31 ordering fixes the
native schedule diagnostic without replacing any schedule routine. This is
declared fixture input, not a fabricated standings result. The continuous
ROST replay computes its actual ordering through native season processing.

The continuous replay also corrected one input assumption: the first native
Combine has end value 1, not 4. M3 admits that exact native state, and the
fast fixture supplies the same value. Earlier attempts ending at CAP are
diagnostics, not the final continuous creation proof.

The undrafted continuation initially refused every club because all native
post-preseason rosters were full. The final route calls native `0x2BF9A0`
only for the chosen club, after native Yes/No confirmation at `0x14E540`.
Its entire 245-byte body is hash-pinned. In the standard 54-player case,
exactly one existing club member becomes a free agent, then MyPlayer signs;
all other clubs' roster pointer arrays stay identical. A separate diagnostic
also exercised the native cut policy on a 58-player preseason roster. The
final low-rated kicker case covers all five native preseason weeks, cancel,
confirmed signing and cold reload with unchanged career index, token and XP.
It also reloads that native undrafted result with Practice Squad installed,
demotes one existing club member through that owner's routine, then tests
cancellation and signing at its 53-player limit while retaining the reserve.
The signed career and reserve survive another cold load. Capacity calls use
the owner's stable `ps_limit` entry, which also dispatches arena-grown state.
The full-owner gates check the arena-grown installation; this reserve-native
case uses the original Practice Squad storage. Partial append/cut hooks and
a damaged retail cut body refuse before installation.

The complete-owner manifest test also needed its observer to wrap static
adapter aliases. ESPN's existing `XbePatch.apply` retained the original
function after the module-level writer was wrapped, leaving its actual
`0xC2319` write unattributed. The test now observes the actual adapter entry;
the attribution check stays strict, and no ESPN implementation was edited.

Native input processing precedes each automatic league/pick step. Saving
or quitting therefore cannot silently advance another pick. Creation
cancellation preserves the already prepared class for retry. Native draft
round/pick state is serialized with the franchise, and cold routing derives
the preparation/draft/unsigned/Apartment destination from that state and
the existing career footer. The cross-allocation cold test saves after ten
picks and resumes exactly the next native pick with a relocated M3 code
and original-state allocation.

HYPOTHESIS: pacing, cap balance, control feel, progress responsiveness and
the complete played experience remain unwitnessed. No preset is enabled.

The protected generic Build selector currently reserves only the two
legacy request rows. It must use `my_career_mode.REQUESTS` and enable the
existing draft-AI option as detailed in `WIRING.md`. Until Claude wires that
selector, a generic Build correctly refuses the incomplete M3 allocation.
The standalone owner and explicitly composed union are the tested surfaces;
this report does not claim a completed release build.

One inherited creation boundary remains: `mode_create` refuses a roster
containing version-2 reserve metadata. M3 does not remove that existing
overflow-membership guard. Start a new career without those reserve records;
the signed-reader support and unchanged allocator addresses do not prove
creation with arena-grown reserve overflow. The capacity helper supports
that owner's dispatch for continuing careers, but a complete native run with
arena-grown reserves remains on Noah's witness list.

## Senior Bowl boundary and deferred work

The Senior Bowl game remains unavailable. The footer owns MyPlayer's token,
primary identity, XP and career preferences. It does **not** carry the
16,384-byte Senior Bowl event record, transport that owner's 65,536-byte
working state, or isolate the native simulator's global/stat writes from
the franchise. A saved MyPlayer identity does not solve these three
ownership problems. The signed input reader now accepts and validates
ordinary and arena-grown inline career containers before passing their
native body to the existing preparation tier. No simulation is advertised.

Requests and trades remain out of M3. Live Supersim resume remains out;
off-field play and mode-5 controls retain their existing behavior. No read
option, ESPN or coverage-trail implementation was changed.

## Noah's witness list

1. Enter the draft from Game Modes, wait through league preparation, cancel
   creation and retry, then create MyPlayer at offensive, defensive, line
   and specialist positions.
2. Save at preparation; open that signed save in Senior Bowl preparation
   with seed 1 and verify MyPlayer's name, position and unchanged ratings.
3. Finish the draft, inspect the actual draft log and contract, then verify
   the correct club, one roster membership and the Apartment. Also test an
   undrafted player, cancellation and confirmation of a full club's roster
   cuts, the released player's free-agent entry, and signing. Check fresh
   free-agent entry still refuses a full club. Repeat with Practice Squad and
   arena growth enabled, verifying active and reserve counts independently.
4. Save during the draft and after signing; cold reload each and continue.
   Try another current M3 build with a different complete allocation union.
5. Play a completed game, earn XP once, cancel and confirm purchases, reach
   a position cap, save and cold reload the rating and remaining balance.
   Quit a game and bench MyPlayer to check that neither invents XP.
6. Check the date/opponent card around a bye, preseason and year rollover.
   Verify the native menu highlight, scrolling, Save, Quit and back paths.
7. Repeat mode-5 kickoff, snap, substitutions, injuries, turnovers, punts,
   overtime and postgame return; confirm input never transfers to a teammate.

## Validation and delivery

**PROVED: 42 standalone files, 569 tests passed, 1 pre-existing skip.** Both XBE
gates include the complete owner union in both orders; pairwise composition
and all mode-5 suites pass. The table lists each exact standalone file. Run
each as `python3 tests/mod_editor/<filename>` with
`QT_QPA_PLATFORM=offscreen` and
`NFL2K5_CAVE_MANIFEST=.scratch/m3-manifest-delivery.json`.

Peak standalone-suite RSS was 913,044 KiB; the separate continuous
probe peaked at 155,580 KiB. Every process stayed below 2 GiB.
Summed suite time was 6,298.313 seconds; suites ran concurrently.
`tools/mycareer_mode/m3_validation.json` records all commands, exact core
and fixture source hashes, per-suite times/RSS, log hashes, and the bootstrap
and budget receipts. Only the final `m3-delivery-*` groups are included;
failed diagnostics and interrupted earlier runs are excluded.

The one skip is the unchanged allocator test
`test_relocated_lineup_hold_and_contact_release_in_both_directions`,
explicitly superseded by kickoff-v3/v4 full-frame fixtures in the base.
No MyCareer, new M3, or private-evidence check was skipped.

| Standalone file under `tests/mod_editor/` | Passed | Skipped | Seconds | Peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| `test_nfl2k5_cave_oracle.py` | 28 | 0 | 218.581 | 913,044 |
| `test_nfl2k5_defensive_try_manifest.py` | 3 | 0 | 4.230 | 157,716 |
| `test_nfl2k5_franchise_autosave.py` | 7 | 0 | 8.800 | 117,284 |
| `test_nfl2k5_franchise_autosave_unicorn.py` | 15 | 0 | 7.735 | 389,180 |
| `test_nfl2k5_guardian_manifest.py` | 1 | 0 | 181.784 | 238,704 |
| `test_nfl2k5_music_playlist_manifest.py` | 2 | 0 | 3.735 | 131,592 |
| `test_nfl2k5_my_career.py` | 13 | 0 | 20.270 | 132,188 |
| `test_nfl2k5_my_career_completion.py` | 6 | 0 | 27.906 | 259,496 |
| `test_nfl2k5_my_career_control.py` | 2 | 0 | 13.907 | 213,924 |
| `test_nfl2k5_my_career_cpu_choice.py` | 1 | 0 | 18.483 | 145,860 |
| `test_nfl2k5_my_career_cpu_frame.py` | 1 | 0 | 63.342 | 133,512 |
| `test_nfl2k5_my_career_cpu_injury.py` | 1 | 0 | 20.534 | 133,596 |
| `test_nfl2k5_my_career_cpu_period.py` | 2 | 0 | 36.830 | 168,460 |
| `test_nfl2k5_my_career_cpu_timeout.py` | 1 | 0 | 18.965 | 133,364 |
| `test_nfl2k5_my_career_cpu_turnover.py` | 3 | 0 | 62.675 | 168,396 |
| `test_nfl2k5_my_career_creation_boundary.py` | 4 | 0 | 2.080 | 184,212 |
| `test_nfl2k5_my_career_draft.py` | 6 | 0 | 1265.957 | 304,508 |
| `test_nfl2k5_my_career_frontend.py` | 7 | 0 | 57.057 | 226,560 |
| `test_nfl2k5_my_career_generic_build.py` | 5 | 0 | 15.273 | 173,228 |
| `test_nfl2k5_my_career_inline.py` | 8 | 0 | 11.947 | 290,648 |
| `test_nfl2k5_my_career_m3_budget.py` | 5 | 0 | 4.040 | 125,992 |
| `test_nfl2k5_my_career_m3_menus.py` | 4 | 0 | 35.163 | 158,712 |
| `test_nfl2k5_my_career_manifest.py` | 3 | 0 | 6.093 | 138,660 |
| `test_nfl2k5_my_career_mode4.py` | 8 | 0 | 411.569 | 322,408 |
| `test_nfl2k5_my_career_mode5.py` | 4 | 0 | 287.832 | 427,196 |
| `test_nfl2k5_my_career_mode_audit.py` | 6 | 0 | 0.062 | 65,768 |
| `test_nfl2k5_my_career_mode_routes.py` | 7 | 0 | 2.831 | 229,616 |
| `test_nfl2k5_my_career_panel.py` | 4 | 0 | 0.170 | 68,744 |
| `test_nfl2k5_my_career_played.py` | 4 | 0 | 70.296 | 221,560 |
| `test_nfl2k5_my_career_season.py` | 1 | 0 | 160.133 | 192,568 |
| `test_nfl2k5_my_career_unicorn.py` | 18 | 0 | 12.277 | 298,632 |
| `test_nfl2k5_my_career_upgrades.py` | 4 | 0 | 261.418 | 391,080 |
| `test_nfl2k5_my_career_week.py` | 1 | 0 | 346.028 | 167,464 |
| `test_nfl2k5_owner_pairwise_composition.py` | 115 | 0 | 700.354 | 191,812 |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 | 0 | 3.929 | 132,864 |
| `test_nfl2k5_senior_bowl.py` | 26 | 0 | 4.802 | 118,344 |
| `test_nfl2k5_senior_bowl_unicorn.py` | 9 | 0 | 2.451 | 88,768 |
| `test_nfl2k5_supersim.py` | 12 | 0 | 8.012 | 264,628 |
| `test_nfl2k5_xbe_space.py` | 12 | 1 | 35.195 | 216,380 |
| `test_senior_bowl_panel_qt.py` | 5 | 0 | 0.084 | 65,648 |
| `test_xbe_patch_cave_references.py` | 107 | 0 | 1008.278 | 533,512 |
| `test_xbe_patch_memory_writes.py` | 95 | 0 | 877.205 | 342,092 |

Additional exact development commands:

```text
python3 tools/mycareer_mode/build_runtime.py --check
python3 tools/mycareer_mode/measure_m3.py --output tools/mycareer_mode/m3_budget.json
python3 tools/mycareer_mode/refresh_m3_manifest.py '<private retail extraction>/default.xbe' --output .scratch/m3-manifest-delivery.json
python3 tools/mycareer_mode/probe_m3_bootstrap.py --finish-creation --output .scratch/m3-delivery-bootstrap.json
git diff --check
```

The generator check and whitespace check pass. The bounded scratch manifest
validates source freshness and reservations while retaining explicitly
historical parent disc fields. The protected release manifest is unchanged;
Claude must regenerate it after the integration in `WIRING.md`. The receipt
does not claim a release build or a played witness.

No disc or archive copy was created. Available space could not accommodate a
disposable 6.3 GB disc while preserving Noah's 100 GB floor. Scratch contains
only development text, logs and JSON receipts, below the 200 MB limit.
Private input reads remain bounded to the pinned XBE and individual
resources; tests specify precise skips when that evidence is absent.

Base revision: `be99b324f34d536c625efcba7e7ea5d4f104fd2b`. Delivery uses the explicit
34-path changeset on this worktree's branch. `ASTRA_BRIEF.md` and `.scratch/`
are excluded. Git metadata is writable, so no bundle fallback is needed.
No push is performed. Protected files and other worktrees were not edited.
