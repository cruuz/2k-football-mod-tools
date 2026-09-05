# Defensive try implementation, 2026-09-05

**EXPERIMENTAL / UNWITNESSED. Default off in every preset.**

The executable backend implements defensive try continuation, two-point
return scoring, touchdown-team kickoff ownership, split packed scoring
history, one-point try safeties, distinct play-by-play suffixes and a narrow
CPU return override. It installs only pinned hooks and named grown RX/RW
allocations. It composes with modern kick rules and relocated kickoff.

**The complete brief is not yet satisfied:** the requested retail defensive
two-point conversion box-score row is not implemented. The actual stat-commit
hook rebuilds a separate temporary team tally, exposed by a diagnostic reader;
it is not an in-game box-score row or a saved player/season/franchise category.
Protected UI/build integration and manifest regeneration are also pending
Claude's handoff by instruction. This report does not claim a finished public
feature or any played witness.

## Inputs and constraints

Read the complete `ASTRA_BRIEF.md` and the 679-line
`the private research memo DEFENSIVE_2PT_RESEARCH_2026-09-05.md`.
Read-only instruction/decompiler evidence came from the USA retail executable
and `~/2k-football-mod-tools/research/functions/nfl2k5/`. Retail `default.xbe`
is 11,948,032 bytes, SHA-256:

```text
73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
```

Only this worktree was edited. No network, emulator, GUI display, audio or
push was used. Retail assets, generated executables, the brief and scratch
research are excluded from the commit. Modern rule behavior is the brief's
specification; no current external rulebook verification is claimed.

## Implementation and evidence

**PROVED below means pinned static instructions or bounded Unicorn execution,
not a console witness.** Synthetic player, team, ball and play objects stand
in for the game world. External presentation/animation callbacks are explicitly
stubbed in the test. Each execution is capped at 20,000 instructions and must
reach its declared return address. Mapped executable-only pages are protected
against writes; pages shared with an existing writable section retain the
retail page permissions.

| Area | Implemented behavior and proof boundary |
|---|---|
| Interception | `B9BA4: 75 27 -> EB 27` preserves possession and the ball-state store, then restores normal catch-position evaluation. The try-specific ordinary-interception stat exclusion in `B6C70` remains. |
| Fumble and kick recovery | `B9E41: 75 1E -> EB 1E` removes the common defensive-acquisition death tail. Full `B9B50` execution covers interception, fumble and blocked-placekick recovery for both teams. |
| Blocked first touch | `B7B51: 75 0A -> EB 0A` allows the touched kick to remain live before anyone holds it. Full `B78C0` writes the first-touch fields; attachment itself remains a synthetic engine boundary. |
| Return score | Existing try score path `B7610 -> 236210 -> A1B30 -> B8330`, descriptor `22EB70`, and full record applier `22E4D0` credit the runner's team. The test traverses the goal-plane and ball-shape helpers in both directions. |
| Tackled short | Full `B96B0` reaches the real `A0390 -> B7230` dead-ball coordinator. The body/touchback classifier is the geometry fixture boundary. Failed-try descriptor/applier awards zero and schedules kickoff. The same-frame guard is separately proved. |
| Kickoff owner | A call wrapper at `22EC11` executes displaced `22E050`, then for phase 3 runs `22E250` to normalize only next phase, owner and spot. Score event, scorer and actor remain intact. Both retail and modern kickoff spots are tested. The original touchdown team kicks after a return or safety. |
| Try safety | Phase-3 exclusions at `B7693`, `B76CC`, `B7D86` and `B7F06` are removed, preserving existing impetus/body/touchback decisions. The `22E330` wrapper awards one through the existing score object and avoids an ordinary safety free kick. |
| Blocked loose safety | A hook at `B7C36` routes a phase-3 placekick first touched by the other team through loose-ball end-zone handling. This covers a ball rolling out of the kicking team's own end zone before recovery. Ordinary untouched missed PATs retain the retail kick arm. Tests set the kicker as the impetus source, for both directions. |
| Packed history | The phase-3 committed writer at `CD88A` writes subtype 5 for a defensive return, 6 for a safety credited to the touchdown team, and 7 for a safety to its opponent. It updates expanded `+1C` and packed bits 29..31 together; lower 29 bits remain. Outcome 6 reverses the touchdown beneficiary. |
| Score consumers | `250360` divides points between teams; the independent `D62E0` summary's calls at `D63A9`/`D63CB` do likewise. All 8 retail outcomes x 5 retail subtypes are compared against retail for both requested teams. The custom matrix covers both drive teams, outcomes 1/6 and subtypes 5/6/7. |
| Play-by-play | Hook `BD5BE` uses the existing UTF-16 suffix appender with immutable owned strings: `. Defensive two-point return` and `. Safety on try (+1)`. Existing `. 2 PTS!` remains for an offensive conversion. Pointer selection and real `30DB0` append are executed. No resource or global string replacement is made. |
| Stat commit | Hook `1EEA96`, the real `1EDC60` epilogue, reconstructs an independent team return count from retained subtype-5 drive records. Repeated commit is a replacement, never an increment. Empty-history rebuild clears it. Ordinary offensive conversion columns are not repurposed. |
| CPU return | Retail `2EE110` already routes phase 3 to ordinary acquisition. A second selector, `2E2A90`, can still choose an end-zone wait. The wrapper at `2E3786` returns zero only for a live phase-3 CPU defender holding the ball. Full `2E36F0` then creates callback `2E2DA0` with heading 0/0x8000, instead of `2EE090`. Human-controlled fixtures retain retail behavior. |

The descriptor wrapper preserves the displaced builder's GPR outputs, flags,
stack, x87 control/status/tag and SSE state. It uses `FNSAVE`/`FRSTOR` around
the extra builder, not just PUSHAD. Other added arithmetic is integer-only.
History/points/stat paths save GPRs and flags before scratch work; intentional
return values and retail epilogues are restored. CPU and blocked-out wrappers
preserve their scratch register and incoming flags. The text hook preserves
incoming flags on its new suffix path and replays the retail comparison on
ordinary paths. Summary wrappers intentionally adjust EAX/score destinations
while preserving flags from the displaced reader. Small branch changes leave
the preceding comparisons intact. No try hook writes runtime data to `.text`.

## Storage, representation and writer contract

Owner: `nfl2k5_defensive_try`. Requests:

```python
(("nfl2k5_defensive_try", "code", 1440, 16),
 ("nfl2k5_defensive_try", "data", 1040, 16))
```

The allocator supplies separate preloaded code/data pages. With relocated
kickoff the boot logo occupies code `14BA000..14BA2B2`; this owner occupies
code `14BA2C0..14BA860` and data `14BB000..14BB410`. Relocated kickoff follows
at code `14BA860` (1939 bytes), data `14BB410` (10 bytes). Only 13 code bytes
remain after the complete union; future features must request capacity and
refuse if it does not fit. Padding stays reserved by the parent allocator.

Data offsets 0..1023 contain 128 replacement records of scoring-team and actor
pointers. Snapshot offsets `+354/+358/+35C` are event/team/actor, unlike the
descriptor's event/actor/team order. Records are indexed by the committed
packed-drive slot, so replay replaces and ring wrap reuses a slot. These are
current-process pointers, **not serialized player IDs**. Offsets 1024/1028
hold team-0/team-1 counts, and 1032 is the committed schema marker (1).
All disk data is zero. Labels live in the read-only code reservation.

`read_runtime_stats(installed_xbe, read_memory)` exposes:

```text
label: Defensive two-point conversions
teams: [team_0_count, team_1_count]
points: [2 * team_0_count, 2 * team_1_count]
committed: whether the stat hook has committed
scope: current game, retained drive history
persistent: false
```

This interface does not connect itself to the retail box score. After more
than 128 drives, only retained records contribute, matching the explicit
scope rather than claiming lifetime totals. A fresh process starts at zero;
the empty-history stat rebuild clears a previous game's count. No unproved
retail stat/save field is used for storage.

`status` reports `retail`, `applied`, or `foreign`. `apply` validates all
complete instruction spans, normalized neighboring instruction hashes,
dependency pins, section digests, allocator metadata and exact owned code
before mutation. Every individual mixed or foreign hook is rejected, including
resealed foreign bytes. Uninstalled reserved code must be all `CC`; installed
code must match exactly. Partial hooks/code, unknown allocations and an absent
owner in an already-grown XBE require rebuilding from base.

Receipts include exact hook before/after spans, code installation, allocations,
source/result SHA-256, actual changed-byte count, experimental/unwitnessed
flags and explicit limitations. Idempotent replay is byte-identical and
reports zero changes. Section digests are repinned through existing helpers.
The complete union must be allocated before installing either defensive try
or relocated kickoff; both orders are byte-identical, with and without modern
kick rules. The backend can also allocate its own standalone union explicitly.

## Known gaps and hypotheses

1. **Unimplemented requirement:** there is no new retail box-score row or
   persistent defensive-conversion category. `1EDC60`'s existing offensive
   conversion attempt column at team `+250` does not prove a spare defensive
   category. Reader descriptors at `A8A510` have 28-byte stride and feed both
   current-game and season readers. Existing conversion labels at `E7B088`,
   `EAA380`, `EB1B1C` and `EB8D70` have distinct table consumers. Replacing a
   label or an offensive counter would corrupt another category. Adding the
   row requires a proved UI table extension plus player/team category and save
   lifetime work; neither is supplied here. The temporary tally is expressly
   not completion of this requirement.
2. **HYPOTHESIS:** the visible score bug and quarter/drive totals agree during
   a played game. Their numerical inputs and independent history summary
   paths are proved; the renderer was not run. Full `1EDC60` event/stat replay
   is not executed; its new epilogue is bounded separately. Custom subtypes
   need save/reload and simulation compatibility evidence before persistence
   support can be claimed. Existing offensive attempt accounting for a failed
   try that instead becomes a defensive score also needs a complete stat audit.
3. **HYPOTHESIS:** CPU movement continues to the end zone under pursuit. The
   return callback and heading are proved, including bypassing the end-zone
   wait selector. Running animation, navigation, later possession changes and
   ordinary kick/return AI interactions need gameplay witnesses.
4. **HYPOTHESIS:** every presentation is appropriate. Only the existing text
   suffix path is patched. Full play-event rendering, line width, narration,
   overlays and a visible dedicated box-score line are not witnessed. No new
   speech or archive strings are authored.
5. Period endings, overtime, penalties/accepted retries, reviews, repeated
   turnovers on one try, own-team recoveries after multiple changes, and
   impetus changes caused by an intentional bat remain unwitnessed. Ordinary
   dead-ball and impetus logic is retained, but these are not proved by one
   successful branch fixture.
6. Kernel loading of the grown sections remains the allocator's prior
   UNWITNESSED boundary. This session did not create or play a witness disc.

The protected integration is specified concretely in the new top section of
`WIRING.md`; all earlier handoffs are retained. Every preset stays false.
The capability entry is supplied as a standalone JSON object for later
canonical registry merge, with runtime `not-tested` and the missing stat row
disclosed. No protected production/UI/release file or manifest JSON was edited.

## Verification

Final standalone commands and results (Python 3, Capstone 5.0.7, Unicorn 2.1.4):

| Command | Result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_defensive_try.py` | PASS, 23 tests, 28.209 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | PASS, 11 tests, 11.534 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | PASS, 11 tests, 29.180 s |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py CaveOracleTests.test_manifest_hash_completeness_and_source_drift_refused CaveOracleTests.test_recorder_refuses_unattributed_patch CaveOracleTests.test_reservation_precedence_including_coincident_and_zero_bytes` | PASS, 3 tests, 0.036 s |
| `python3 tests/mod_editor/test_nfl2k5_xbe_space.py PublicTests.test_owned_code_installation_and_manifest_builder` | PASS, 1 test, 0.937 s |
| Capability object against the existing JSON Schema capability definition, and all evidence paths | PASS |
| `git diff --check` | PASS |

That is 49 passing unittest cases, including parameterized branch matrices.
No game witness is included in that count. Initial fixtures exposed and fixed
the snapshot team/actor field order, shared writable-page protection, end-line
test coordinates and blocked-kick impetus setup. The cave gate initially
rejected the old manifest's shifted child addresses; the historical-layout
validation and in-memory union described below resolved it without editing
the protected JSON or discarding unknown owners.

Private-retail/Capstone/Unicorn requirements use precise `unittest` skips when
absent. No pytest-only behavior or mandatory production disassembler was added.

The feature writer suite includes retail pinning, idempotent receipts, every
hook's mixed/foreign refusal, code/data/metadata corruption, complete instruction
spans, resealed neighboring corruption, kick/relocation composition and the
real manifest `Recorder`. It checks new hook ownership against the protected
historical reservations and records both zero-initialized owned data and code.

Both existing safety gates compose this feature after allocating the complete
owner union. The write gate checks the new absolute writes and RW ownership.
The cave gate checks every grown owner. Because the protected JSON records the
old kickoff-only addresses, it first proves that historical allocation, then
constructs the new named reservation set in memory; unknown historical owners
still refuse. Once Claude regenerates the JSON it uses that directly. No
closed-world cave rule is weakened, and unknown storage is never offered.

The complete multi-gigabyte manifest disc build was not run; the actual pure
writer/Recorder path was. Claude must regenerate the protected manifest after
wiring so its source fingerprints and relocated addresses match that final
stack. This distinction is separate from the passing bounded manifest test.

## Commit delivery

The explicit-path `git add` failed because the shared worktree metadata at
`.git/worktrees/astra-r61b-defensive-2pt-build`
is read-only (`index.lock` could not be created). Per the brief's fallback,
the same branch is committed through isolated local Git metadata under
`.scratch/r61b-defensive-2pt-build.git`, with the eight deliverable paths
explicitly named for both add and commit. The incremental bundle is
`.scratch/r61b-defensive-2pt-build.bundle`; the original worktree files remain
in place. Its prerequisite is this worktree's starting HEAD. No push, shared
branch update, brief or scratch inclusion is part of that commit.

## Noah's witness list

Use a disposable **exhibition** disc with `defensive_try=true` manually,
initially with modern kick rules. Record score before/after, both team totals,
the event text, drive/quarter summary and the next kickoff. Run each in both
field directions; include both CPU and human defensive possession.

- Blocked PAT: touch while still loose, scoop, return across the goal line.
  Expect +2 defense, no ordinary defensive TD, and kickoff by the original
  touchdown team. Also let the touched kick fall without immediate recovery.
- Intercept a two-point try and return it. Expect +2 to the interceptor's
  team, touchdown drive worth 6 to its original scorer and 2 to the opponent.
- Recover an offensive fumble on a try and return it. Check possession,
  running control, scorer, history, PBP and kickoff ownership.
- For all three acquisition types, tackle the defender short, force an
  in-bounds dead ball, and force a sideline exit. Expect zero points and a
  completed try, followed by the original touchdown team's kickoff.
- Safety on a try: retreat with possession, loose fumble out of the own end,
  and a blocked PAT rolling out of the kicking team's own end before recovery.
  Expect exactly +1 to the correct opponent and no safety free kick. Contrast
  with a touchback, ordinary untouched missed PAT, and a recovery without
  new impetus in the end zone. Inspect kickoff after every case.
- Let a CPU defender possess in its own end zone. It should attempt a return
  instead of taking the end-zone wait/kneel path. Observe actual running and
  pursuit; choosing the callback offline is not this witness.
- Check the score bug immediately, scoring/drive/quarter summaries later,
  full PBP text width and commentary. Check the box score explicitly: the
  missing defensive-conversion row is an implementation gap, not something
  Noah is expected to discover or approve away. Diagnostic counts alone do
  not satisfy that acceptance item.
- Repeat a failed and successful try after a penalty/retry or review. Check
  no duplicate points/history/tally. Include an interception followed by a
  fumble back, an end-of-half try, regulation-winning try and both OT roles.
- Repeat with relocated kickoff enabled; check kick owner, spot, lineup,
  landing-zone hold and contact release. Verify boot logo and new-section
  loading. Repeat with retail spots as a separate compatibility witness.
- Start a fresh game and inspect reset behavior. Keep franchise/postseason
  use out of acceptance until saved categories and custom-history reload
  have separate implementation and proof.

Integration 3 release note: workstation paths in this historical handoff are
shown symbolically; the original evidence scope and missing-stat limitation
are unchanged.
