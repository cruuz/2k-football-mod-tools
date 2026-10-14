# Automatic 2026 CPU coach profiles

`coach_ai` is an experimental Studio Build setting, **ON in the SOFTDRINK
experimental release preset**. The Build toggle remains editable and an
explicit `false` is preserved in saved settings. Bare plans, Basic and Advanced
retain their previous defaults.
When enabled, current NFL CPU teams use their observed coach profile without
loading a USR or making a Coach Matchup selection. It includes VIP-aware Modern
2. The human side keeps its ordinary native behavior. Cold xemu checks cover
an uninterrupted Play Now half, a PAT, kickoffs and controller reassignment.
Explicit NFL Coach and imported-VIP choices are retained. A full franchise
game, native save, cold reload and ordinary plays in the next game also pass.
Corrected imported VIP gameplay has a bounded call sample. Live coverage is
limited to the teams and modes listed below; component execution alone is
not a gameplay witness.

The automatic profile is associated with the team's existing NFL Coach entry.
That entry already uses its roster portrait. An explicit different NFL Coach
or user VIP wins. Generated coach USRs also use the matching portrait in Coach
Matchup and the VIP viewer; recognition requires both an authored identity and
the exact profile name. Legacy vp1 IDs remain accepted. Unknown personal VIPs
retain their existing logo. Portrait textures are separate art inputs; this
feature does not repaint them, and a missing portrait keeps native fallback.
The co2 art build moves Dallas and Washington to portrait slots 7031 and 7034.
Both those IDs and the original int2 IDs (7007/7029) are recognized for their
respective coach. Authored VIP rendering follows the loaded roster's supported
ID, so either build order works without changing the stored playbook profiles.

## Activation and lifetime

| Native route | Behavior |
| --- | --- |
| Play Now/exhibition, mode 4 | Automatic current-NFL CPU profile; explicit choice wins |
| Season, mode 5 | Same |
| Franchise/playoffs, modes 6–7 | Same |
| Modes below 4, mode 8 scenarios, other special modes | Original behavior |
| Celebrity challenge, replay/special state | Original behavior |
| Historic, Pro Bowl, created/custom teams | Original behavior; require current NFL roster kind and asset identity |
| Active MyCareer stages 1–6 | Original MyCareer policy |
| Paired offensive/defensive book | Existing paired-side replay suppression remains |

The eight native hooks validate both raw PLAY loading paths, attach at CPU setup, rebind
after controller changes, release at game unload, and route the two portrait
renderers. Setup runs through the game's `F7B30`/`F6E60`/`F7A90` path. Only the
eligible CPU setup's local mode register is adapted; global mode never changes.
Native selectors and mandatory decision charts remain intact.

The profile influences ordinary calls and the native decision statistics; it
does not make every snap an exact history replay. Native hurry-up sequences
bypass the ordinary VIP selector. The game also marks used pools and can
choose a native fallback on later calls. Special teams and eligible audibles
keep their existing paths. Live call comparisons must separate those paths
from sampled profile selections; short games do not prove long-run rates.
The native fallback can also name a secondary formation that its own menu
cannot reach. A franchise sample targeted non-authored Bear 46 and executed
4-3 Over instead; the same menu limit exists in the retail executable. The
authored pools exclude unreachable formations, but do not replace that
independent native fallback path.

The owner reserves 5,120 RX bytes and 128 RW bytes. It allocates at most two
8,608-byte playback contexts through the native heap. Neither uses a resident
USR slot or changes a save format. Published owned pointers are cleared before
freeing. Controller takeover removes the automatic profile from the human
side and rebinds CPU sides. The native VIP reset precedes the ownership update:
the reset hook queues a rebind, and the second hook commits it only after both
teams' human flags have been updated. Routine lineup refreshes do not rebind
or reset profile history. The witnessed franchise save/load retains the
completed result and creates fresh owned contexts in the next game.

## Exact-book data

Each of 32 final NFL PLAY resources stores an 896-byte record in its existing
unused tail. A 128-byte header pins version, book index, team/coach identity,
exact compiled-book SHA-256, raw-book fingerprint and payload checksum. The
remaining 768 bytes contain offense/defense rings and observed decision,
statistics and tempo counters. Build-time validation refuses declared strings
overlapping the tail, foreign bytes, stale tags, wrong identities or invalid
recorded indices. Validation runs before both native loading paths: the
disc resource callback's in-place relocation (`1665A0` → `E0D90`) and the
saved-book copy/relocation (`161E30`). Each marks only a valid matching payload;
missing, invalid or unallocatable profiles fall back to ordinary coach AI.

The Studio compiles profiles after final book/roster edits. The book's visible
name is insufficient: rebuild after any book edit. Existing tagged resources
must still match their pins before regeneration. Custom-team and changed-coach
inputs outside the authored directory refuse instead of receiving a guess.

Defensive pools also require native VIP menu reachability. The menu visits
only the first formation in a personnel category, so a callable secondary
formation can otherwise turn into a different play during navigation. The
compiler filters those formations before fitting coverage and pressure rates.
The native verifier checks menu traversal as well as low-level selection.

`data/vip/coaches/*.json` occupies 1,496,799 bytes, reduced from 25,478,735.
It retains every native compiler input, measured count, provenance and source
hash. Full descriptive grids are regenerated with the `derive` command in
[the coach VIP documentation](nfl2k5_coach_vip.md#build-the-tendencies), then
compacted deterministically into a new directory:

```sh
python3 tools/nfl2k5_coach_vip.py compact \
  --source /private/new-coach-tendencies \
  --out /private/new-compact-coach-tendencies
```

Pass/run counts are jointly quantized below 254 because native game-start
history decay otherwise halves those two counters independently. Other
counters retain the native paired decay. This preserves ratios within the
reported integer quantization limits. Native pool size, play availability,
charting gaps and optional-decision eligibility still limit fidelity; see
the manual VIP documentation and per-profile build receipts.

## Repair an existing private v0.6.1 disc

The repository development repair tool prepares and verifies the XBE and all 32 resources
before writing. Use a private disc copy; it performs fixed-span writes in place:

```sh
python3 tools/b77/vp2_repair.py apply-disc \
  --image /private/test-copy.xiso.iso \
  --receipt /private/coach-ai-repair.json
```

The accepted base hashes are the original int2 executable
`ffc5a33c99819d83017d75b2e4173d988328870834fd465ce67af0674d9b4118`
and the VIP-aware Modern 2 executable
`30adaffa0c75efc790f551f229dbef4e072ef636082f23184d7ee3ed54c6d589`.
For a reviewed composition with other native repairs, supply its exact
`--approved-input-xbe-sha256`. Approval of a hash does not bypass native hook,
allocator, policy, size or profile recognition. Foreign/mixed inputs refuse.
Existing allocator addresses must remain unchanged. The receipt records input
and output hashes, every permitted span, readback, unchanged outside-span
hash and idempotence. Reapplying the same command preserves the first receipt.

The `apply-xbe --xbe INPUT --output NEW --receipt NEW.json` subcommand creates
only a private executable. It does not install the required PLAY resources.
Generated executables, profiles, discs and save templates are never shipped.

## Verification

Cold xemu acceptance on co2 + VIP-aware Modern 2 + coach AI covers:

- DAL/WAS Play Now, native mode 4, through a complete half and the Q3
  kickoff: fourth downs, a touchdown, PAT, field goals, punts and kickoffs.
  CPU profiles remain distinct; controller takeover leaves the human side
  untouched, and explicit NFL Coach and imported-VIP choices survive.
- Imported DAL/WAS coach portraits on Coach Matchup and detailed VIP pages.
  The corrected explicit DAL VIP sample has 16 profile-to-field call
  matches. The automatic Play Now sample has 51.
- IND at TEN in an existing 2027 franchise, native mode 7, through a full
  two-minute-quarter game, final TEN 7, IND 0, with 46 profile-to-field call
  matches. Native Save MyNFL writes a valid signed save. Cold reload shows
  TEN 1-0 and the 7-0 result, then advances to DEN at TEN and ordinary plays
  with both teams' own automatic contexts active.

The private `vt1/REPORT.md` records frame paths, hashes, original failures,
corrected retests and unmatched calls. Call counts are sampled retained
changes, not a complete snap census or proof of long-run rates. All 32 teams
and modes 4-7 have native component checks; other teams, Season/playoffs as
distinct live routes, overtime, long-term franchise progression and physical
Xbox hardware are not established by this live sample.

```sh
python3 tools/nfl2k5_coach_ai_assemble.py --check
python3 tests/mod_editor/test_nfl2k5_coach_ai.py
python3 packaging/repin.py --apply --include-tests
python3 packaging/repin.py --check --include-tests
```

Private resource/native unit checks use `NFL2K5_COACH_AI_IMAGE` and
`NFL2K5_COACH_AI_XBE`. The latter points to the VIP-aware base executable.
`tools/b77/vp1_verify.py --automatic --profiles PRIVATE_PROFILES
--baseline-xbe PRIVATE_BASELINE ...` executes all four supported modes with
zero preselected VIPs, actual native offense/defense selectors, retail and
no-feature controls, human negatives and explicit choices. Its report states
the environment fixtures and distinguishes component execution from live
gameplay. Heap services and named portrait texture lookup are fixtures;
selectors, setup, compatibility checks and the native RNG are not replaced.

Native regeneration requires a 32-bit freestanding GCC/binutils toolchain.
The C/assembly sources and reproducible assembler are development tools;
Studio uses the checked-in generated code template. Derivation, manual USR
export, native repair and Unicorn verification commands run from the source
repository; they are not runtime dependencies of the packaged Studio.
