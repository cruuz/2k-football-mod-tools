# Weekly preparation: safety drills, CPU clubs and remembered plans

EXPERIMENTAL / UNWITNESSED. No game boot, GUI, audio, network or played witness.

**TE/S cause in one sentence:** Retail DB drills test only CB position 4 and
exclude FS 5 and SS 6; TE position 9 has a valid filter and drill rows matching
HB/FB, so the reported TE deficit is not root-caused.

Implemented a named XBE owner that fixes the safety filter, optionally runs
the native prep routine for CPU clubs before their games, and optionally keeps
and automatically applies a human club's existing plan across weeks and
seasons. These are native temporary game bonuses, not permanent season
development. There is no invented progression credit or new save field.

The CLI/backend and standalone proofs are delivered. Protected product
integration is specified in the R65 weekly-preparation section of `WIRING.md`.
All three product options are explicitly off in all presets pending a witness.
The brief permits an honest writeup for unproved symptoms; no speculative
TE rating bonus was added.

## What was built

- `mod_editor/core/nfl2k5_weekly_prep.py`: exact hooks, prerequisite hashes,
  complete install recognition, immutable CPU/remember settings, idempotent
  replay, refusal of mixed/foreign bytes before mutation, allocation and
  section digest sealing, status/apply/audit CLI and receipts.
- `tools/nfl2k5_weekly_prep.S` and its assembler generator; generated runtime
  template `nfl2k5_weekly_prep_code.py`. The body is 649 bytes in a 1,536-byte
  aligned RX reservation. RW and RO requests are both zero. Owner scratch is
  on the stack; native routines retain their existing Franchise/result state.
- `nfl2k5_weekly_prep_save.py`: inspect native plans and author a fixed-size
  replacement. Applied state 2, unknown states, bad activity/day/duration and
  out-of-pool targets refuse before mutation. A body edit reports unsigned;
  the CLI uses the existing verified signed-copy container writer.
- Complete decoded drill and attribute tables in
  `docs/mod_editor/weekly_preparation.md`, and a capability object ready for
  protected integration.
- Both XBE gate unions and the manifest builder include the owner. The
  committed allocator budget fixture includes its 1,536-byte RX request.
  Auto Save accepts only a fully recognized weekly-prep hook at its separate
  pre-simulation boundary. Its native save behavior was not changed.

No MyCareer, read-option, ESPN or coverage-trail implementation was edited.
The gate helper resolves the existing Historic Reload writer at call time
so ownership observation sees its real edit; its old captured adapter had
left that edit unattributed in the XBE-only recorder.

## PROVED: tables, positions and rank split

Evidence executable: the USA retail `default.xbe`, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The hub and Ghidra corpus were read only. Existing Astra reports and the RC86
changelog were reviewed before implementation; the private review inventory
is `.scratch/reports_reviewed.json`.

The drill table at `0x51D358` contains **173 rows, 32 bytes each**. Its words
are string key, category, subtype, float intensity, injury/body mask,
attribute mask, behavior flags and injury flags. The 13 category callbacks
are at `0xACD728`; the 28 setter/getter pairs start at `0xACD760`.
The audit command validates hashes before decoding and names attributes by
their native getter's player-byte offset. It does not invent localized names
from string hashes. The committed table document includes all 173 rows and
all 28 attribute channels.

Position codes are QB 0, K 1, P 2, WR 3, CB 4, FS 5, SS 6, HB 7, FB 8, TE 9,
OLB 10, ILB 11, C 12, G 13, T 14, DT 15 and DE 16. The native position masks
at `0x51E8F8` are:

| Positions | Attribute mask |
| --- | --- |
| QB | `0x202460` |
| K, P | `0x200180` |
| WR, HB, FB, TE | `0x1D410` |
| CB, FS, SS, OLB, ILB, DT, DE | `0x1E0000` |
| C, G, T | `0x18000` |

`0x2AB610` decides whether each activity applies to each player. Position
drills (category 6) use these existing ranges:

| IDs | Group | Subtype |
| --- | --- | --- |
| 35..38 | QB | 3 |
| 39..43 | HB | 8 |
| 44..48 | FB | 9 |
| 49..53 | C/G/T | 10 |
| 54..58 | TE | 11 |
| 59..63 | WR | 6 |
| 64..68 | DT/DE | 12 |
| 69..74 | OLB/ILB | 13 |
| 75..81 | CB in retail; CB/FS/SS with patch | 7 |
| 82..85 | K | 4 |
| 86..89 | P | 5 |

The exact missing-safety instruction is `cmp eax,4` at `0x2AB703`. The new
detour admits the inclusive range 4..6 and resumes at `0x2AB709`. All 17
positions were exercised through the native filter. TE's five table rows
have the same intensity, masks and flags as the corresponding HB/FB rows.
Full native calculations on identical player inputs give identical TE,
HB and FB rating results with their corresponding position drills.

The full-team drill split at `0x2AB72E` reads rank bits 10..12 of player word
`+0x28`. For a paired role selected by `0xC40F0` (which also reads the team's
formation field `+0x150`), it uses the smaller of that rank and bits 13..15.
Subtype 15 selects rank 0, subtype 16 rank 1, and subtype 17 rank 2 or later.
This is a real starter/backup partition, not a table ending before TE or S.
The native matrix tests exercise all positions, all eight ranks and multiple
other-side ranks. Seven-on-seven excludes C/G/T/DT/DE; it includes TE and
both safety codes.

`0x2A8E10` initializes the 28-channel prep context. Native category routines
combine activity and position masks, current player/team inputs and random
draws. Initial losses, fatigue, morale, rounding and position-dependent
positive caps (+5 in the position mask, +3 otherwise) remain native. Equal
booked activity time does not promise equal displayed changes for different
players. The safety repair fixes eligibility, not every negative result.

## PROVED: CPU path and default plan

The native per-team routine `0x2AC460` obtains the club, calls the human-team
predicate at `0x2AC483` and jumps over every player for CPU clubs. The retail
CPU skip and patched CPU/human parity were both executed on the signed
Franchise fixture. The forward player routine is `0x2AB8F0`; the inverse is
`0x2ABE60`. Both traverse seven days, 500 plan words and 28 attributes.

The week-advance path `0x247D40` snapshots three ratings, updates injuries
and the calendar, increments the week through `0xC4E60` at `0x24801D`, and
sorts depth. It supplies no separate CPU preparation pass. Applying an
unconditional permanent credit there would not reproduce native prep.

Instead, the simulation hook is the existing call at `0xC7B47`, after native
`0xC7A20` selects its actual week and game slot and before `0x10B9C0` simulates
the game. Played games enter through `0xC73B0` and its call to `0x134040`;
the latter's first instruction is the played prep hook. Bounded tests execute
both real caller paths to the game-setup/simulation boundary. Controller and
simulation progress-display services are the named substitutes in those
routing tests; the full rating tests execute native prep without substitutes.

The wrapper requires Franchise mode 2, 32 clubs, stages 7..9, a valid
22-by-17 schedule cell, two distinct club ordinals below 32, an unfinished
game, and the game's existing Weekly Preparation setting On. For each
participant it validates roster count/position and basic plan fields. State
2 means already applied and prevents reentry/load/cancel stacking; unknown
states also prevent automatic application.

With **CPU teams prepare too** enabled, every CPU club gets the same default
for each game week: low full drills for the first, second and third teams,
duration field 2 each, Monday through Friday; Day Off on Saturday and Sunday.
The native rank partition gives every player one of those equal-intensity
drill entries per training day. Native time accounting charges **36 of 40
units per training day**, and 0 of 0 on Day Off. This default fits the game's
budget, covers linemen and specialists, and gives backups the same workload
as starters. It is a conservative workload, not a tuned promise of +5 gains.

All 32 CPU ordinals were dispatched across two successive game weeks in the
routing proof. Byes have no game to receive a temporary bonus; a bye club is
prepared when its next game starts. That timing preserves the native
apply-for-game/remove-after-game contract.

Both original seed lookups used the currently selected human club, even
inside a routine operating on another club. The two seed-call hooks use the
actual team at EBP, then retain native seed-plus-jersey behavior. Forward and
inverse use the same saved team seed.

Played and simulated results reach native `0x135310`; it calls `0x2AC520`
for both clubs at `0x13538F` and `0x135398`. That checks state 2, inverses the
bonuses, cleans the plan and reseeds the team. CPU inverse admission remains
enabled when the CPU Build option is off so a saved applied plan can finish
cleanup. No global master toggle suppresses necessary inverse cleanup.

## PROVED: remembering and saving

There are existing fields for every required persistent value:

| Value | Runtime VA | Offset from front-office block |
| --- | --- | --- |
| 32 plans, 500 words per club | `0xE42460` | `0x5250 + team*2000` |
| 32 prep states | `0xE51E60` | `0x14C50 + team*4` |
| 32 random seeds | `0xE51EE0` | `0x14CD0 + team*4` |
| 65 snapshots of 3 ratings per club | `0xE51F60` | `0x14D50 + team*195` |

The standard front-office block starts at file offset `0x996FC`.
`FranchiseSave.front_office_block` handles the supported grown layout.
The existing Weekly Preparation master dword is at file `0x19C`, runtime
`0xE6011C`. A plan word has activity bits 0..8, target bits 9..23, native
duration bits 24..27, day bits 28..30 and the existing repeat flag at bit 31.
Targets 0..18 select native groups; larger values encode player-pool index
plus 18. The host editor preserves this contract and does not assign any
unproved spare bit. The field named `hours` in the codec is the native
duration value; the scheduler applies category-specific time charges.

**Remember my weekly prep** applies a valid nonempty human plan before the
game unless it was already applied. The wrapper refreshes the native three
rating snapshots before automatic application, then records native state 2.
Postgame and season cleanup mark valid activities with the native repeat
flag and call the existing cleaner with its retain-repeat mode. Native
cleanup still drops targets who left the roster and completed rehab.
The fresh-Franchise initialization call at `0x13EE47` retains its full wipe.
The season hook is at `0x2483F7`; the postgame hook is at `0x2AC53F`.

The native serializer `0x2D0790` and loader `0x2D0CE0` already copy these
plans, states, seeds and snapshots. The cold-reload proof runs the native
settings, roster, season and front-office serializers, signs the resulting
body using the existing signature implementation, and loads it into a new
instruction instance. The plan/state/seed/snapshot survive and state 2
prevents another automatic dispatch. The separate signed-copy test verifies
EXTRA, output readback and source preservation.

CPU and remember options are immutable **Build/XBE settings**, not hidden
save flags. Each can be switched off independently on a clean rebuild; the
game's existing Weekly Preparation Off setting stops automatic application
immediately. An empty human plan is reported explicitly by the reader and
is not auto-applied. The protected Franchise UI wiring requires an empty-plan
message, actual installed-option status, and signed-copy confirmation.

## Evidence scope, tests and limits

Native instruction fixture: signed hub f0 `SAVEGAME.DAT`, 720,044 bytes,
SHA-256 `56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8`.
Its original plans are empty and all 32 human-control flags are set. Tests
author plans and CPU flags in copies or bounded RAM; these are not a captured
played-prep save. The hub's f1 and year-7 Franchise1 files were also inspected
and signature-checked during research, but the native proof uses f0.

The f0 roster already contains ratings above 100. The native setter clamps
them; bonuses at the normal upper boundary can also lose information during
inverse cleanup. In the inspected CPU/default-plan run, six rating bytes
did not return to their starting values, including existing values above
100. The full-roster control test proves the same forward and postgame
results for native human and CPU treatment. This patch does not repair the
retail clamp/inverse limitation, promise permanent progression, or equalize
different players' starting ratings.

Validation uses plain standalone `python3 tests/mod_editor/<file>.py`.
Manifest-dependent suites use
`NFL2K5_CAVE_MANIFEST=.scratch/weekly-prep-manifest.json`.

| Standalone suite | Result |
| --- | --- |
| `test_nfl2k5_weekly_prep.py` | 11 passed |
| `test_nfl2k5_weekly_prep_unicorn.py` | 17 passed |
| `test_nfl2k5_guardian_manifest.py` | 1 passed; observed full current XBE owner stack |
| `test_nfl2k5_franchise_autosave.py` | 7 passed |
| `test_nfl2k5_franchise_autosave_unicorn.py` | 15 passed |
| `test_nfl2k5_music_playlist_manifest.py` | 2 passed |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 passed |
| `test_nfl2k5_defensive_try_manifest.py` | 3 passed |
| `test_nfl2k5_my_career_manifest.py` | 3 passed |
| `test_xbe_patch_memory_writes.py` | 95 passed, including both installation orders and allocator selections |
| `test_xbe_patch_cave_references.py` | 107 passed, including both installation orders and allocator selections |
| `test_nfl2k5_cave_oracle.py` | 27 passed in the full run; remaining ownership test passed on targeted rerun after the XBE-only manifest assertion update |

`python3 tools/nfl2k5_weekly_prep_assemble.py --check` reproduced the committed
template. The allocator `plan --requests
tests/fixtures/nfl2k5_allocator_beta62_requests.json` passed before/after the
owner addition. CLI status/apply with both options off and signed-save
inspect/set-plan were exercised in a deleted `TemporaryDirectory`.
The complete native suite used at most 398,616 KiB RSS (about 389 MiB), measured
with `/usr/bin/time -v`, comfortably below the 2 GB limit.

A scratch registry with the new object passed strict schema validation
(`python3 -m mod_editor.capabilities.validate_registry --registry
.scratch/weekly-prep-registry.json --skip-file-checks`), and every new evidence,
backend and module-command file reference was checked. Full inherited
registry file-check mode stops on an already missing
`docs/research/apf_audio.md`; this unrelated registry content was not edited.
Final whitespace/diff and protected-path checks are included before commit.

The oracle ownership test now distinguishes observed XBE-only manifests from
disc manifests: the former must contain real changed-writer receipts for
scorebug runtime and season length, while the latter still require their
image-step labels. All address, source-hash and ownership checks remain. The
initial full oracle run failed only its disc-only image-step assumption.

The scratch manifest was generated by the real pure-XBE gate recorder,
observing actual writer outputs and rejecting unattributed changes. It is
explicitly an XBE-only proof, with current source fingerprints and no new
disc/resource-build claim. The system drive had 93 GiB free at the capacity
check, already below Noah's 100 GB reserve. No disc/pack copy was made.
The protected production manifest must be regenerated after integration.
No test reads a whole disc or archive into RAM. Scratch remained under 200 MB.

## HYPOTHESIS / known gaps

The expert's TE symptom may involve unequal effective rank, current fatigue,
initial ratings, rounding, injury or a different plan. No supplied video or
captured before/after TE prep state establishes that cause. Same-input
TE/HB/FB parity narrows the problem but does not refute the player's report.
There is no promise that every ordinary plan gives positive changes or that
the CPU default is competitively optimal.

Automatic replay and the host writer conservatively accept duration-field
values 1..8. The field has four bits, but higher encodings are not claimed as
proved UI-authored plans; they are rejected by the host reader/writer and
skipped by automatic replay. The default uses 2 and passes native budget
validation. No captured human prep plan was present in the supplied saves.

The native instruction tests do not establish a played Xbox session, UI
appearance, injury balance over a full season, performance on the console,
or compatibility with every external save editor. Basic plan/roster guards
are not a general repair for a corrupt native Franchise. Protected GUI,
dispatcher, packaging and registry changes remain concrete integration work
for Claude, as required by the brief. No release version/tag was changed.

## Noah's witness list

1. Use separate copies of a normal signed Franchise and two builds: retail
   control and weekly-prep patch. Keep all unrelated settings identical.
2. Use the same DB drill on CB, FS and SS, starters and backups. Record
   before/after attributes, depth ranks, health, fatigue and exact schedule.
   Confirm both safeties now receive DB drill effects.
3. Capture the reported TE failure with the same details. Compare the
   corresponding HB/FB drills; do not assume the safety fix explains TE.
4. Enable CPU prep with Weekly Preparation On. Play against a CPU club and
   simulate CPU-versus-CPU games. Confirm prep precedes play, both clubs
   clean up afterward, and a bye causes no permanent extra credit.
5. Enable remember, make a human plan, finish a game and start the next.
   Confirm the plan remains, applies once, and can be changed after cleanup.
6. Save and quit both before applying and with state 2 already applied.
   Cold-load each copy, reenter game setup, and confirm no duplicate bonus.
7. Carry the Franchise through a season boundary. Check plan retention,
   removal of departed-player targets/completed rehab, and normal new-season
   application. A fresh Franchise must start with an empty plan.
8. Test CPU Off, Remember Off and the game's Weekly Preparation Off, including
   cleanup of a previously applied saved CPU plan. Verify displayed settings
   agree with the built executable and saves still sign/load normally.
9. Compare injuries, fatigue, clamped high ratings and CPU/user balance over
   several weeks. Record elapsed setup time on the console. Keep the feature
   experimental until these observations support release decisions.

## Commit delivery

The final explicit-path add/commit attempt failed because the linked Git
metadata became read only. The authorized fallback is `.scratch/weekly-prep.bundle`,
containing one commit based on `be99b324f34d536c625efcba7e7ea5d4f104fd2b`.
The final files remain in this worktree; no push was attempted. Earlier
staging succeeded, so the original index can retain an older staged version
of the report. Use the bundle commit for integration. The bundle is made and
verified with isolated metadata in this worktree, without changing other
branches or worktrees. `ASTRA_BRIEF.md` and `.scratch/` are excluded.
