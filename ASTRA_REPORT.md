# Beta 69 J6: roster CSV and the Wide Right loading wait

Branch: `astra/b69-j6-rosters`. Base: `922c009d65e35f8195762c31106789bb353fb43c`.

Player CSV export/import is implemented on the existing ★ Rosters page with exact identity, field validation, a read-only preview and one complete Undo/Redo action. The Wide Right gameplay freeze is **UNRESOLVED**. The archive wait now has an instruction-level bounded reproduction, including the native event dispatcher, but the original failing game's asynchronous I/O and scene state are unavailable. The all-moments build hold remains effective. **Every in-game outcome is UNWITNESSED.**

## Requested context and scope

Read `ASTRA_CONTEXT.md`, beta-69 triage row 15, the hub's beta-68 triage row 28 and release FAQ answer to heaven, roster records/page/Undo, ESPN25 roster/scenario writers and `ASTRA_ESPN25_IN_GAME_REPORT.md`. The beta-68 correction remains valid: this option cannot currently produce a claimed playable all-moments result.

MacDog850: "id recommend also adding a csv roster import/export for the extension too... makes player editing easier".

heaven: "Will we be able to have every player with names on them, currently in 2k5's 25th anniversary mode it's WR CB etc".

The triage description was incomplete for this branch: a player CSV menu and partial backend already existed. Its importer fell back to name matching even after a bad pool/index, accepted other schemes' position labels and silently remapped retired OLB, applied individual cells of invalid rows, used storage rather than page bounds, and lacked a preview. An unchanged import still created an Undo command; dirty bookkeeping and complete restoration relied on overlapping record/list snapshots. This change finishes that existing lane. Career-stats and team-history importers are untouched.

## PROVED: player CSV

- Export emits one row per player in every pool (or the explicitly chosen visible list), `pool` and `index`, first/last names, loaded-scheme position label, team, jersey, years pro, inches/pounds, hand, college, date components/date view, PBP/photo IDs, all 28 `RATING_BYTE_ORDER` fields, appearance, both derived style controls, contract fields, abilities, tier, Guardian cap and five depth/returner locks. These formats all expose the contract block through `RosterDocument`.
- Import requires exact pool/index. There is no name fallback. Every occurrence of a duplicated identity refuses, including equivalent decimal spellings such as `0`/`00`. Unknown identities, malformed row widths and invalid fields appear in the refusal list. Missing/duplicate/unknown headers and malformed quoting refuse the sheet with a corrective message.
- Changed fields use `NUMERIC_LIMITS`, the card's enum tables and rating ceiling 127, then the record's own bit-width/century validators. Position edits require labels from `position_names(document.scheme)` and pass `check_position_code`; no cross-scheme conversion. An unchanged stored value outside a card's editing range is preserved, so untouched exports remain byte-exact.
- Each invalid row contributes no changes, including earlier name or team cells on that row. Name allocation and team minimum/capacity/draft-class rules remain enforced. Valid rows are applied in file order; a membership move that violates the current roster's limits refuses with that reason. This does not introduce a simultaneous team-trade solver.
- `preview_csv` works on detached candidate state and re-decodes its serialized result to verify the canonical fields. `apply_csv_preview` refuses a stale body/scheme/reference-year snapshot. The preview lists before/after values and all refused rows. A returner-lock transfer includes the previous owner's change too. Edit detection uses the initial CSV snapshot, so an unchanged later row cannot reclaim a transferred role. Conflicting edits to a raw field and its derived style/date view refuse the row.
- The page's file action requires the preview's `Apply valid rows` action. Cancel changes nothing. One nonempty import becomes one Undo entry restoring the full composed document (names and pool bytes, ratings, colleges, contracts, memberships, locks and prior franchise journal), with functioning Redo and dirty markers. An unchanged import creates no Undo entry.
- Synthetic disc-layout, genuine Xbox-save *layout* and franchise-layout documents round-trip without changing bytes. Export/import unchanged produces zero edits; changing one speed or contract cell produces exactly one field edit. A prior GUI edit survives CSV Undo, and Redo replays all CSV effects. Signed synthetic save source members remain byte-identical throughout. These are generated fixtures, never copied retail roster bytes.

### CSV and Excel format

UTF-8 text, header row, commas, standard CSV quoting and LF line endings; BOM input is accepted. Semicolon input remains supported when it includes identity pins. Names-only Finn-style sheets must add the current document's pool/index columns; re-exporting from the page is the supported starting point.

Text beginning with a digit, apostrophe, `=`, `+`, `-`, `@`, tab or line break receives one protective apostrophe; import removes that prefix. Thus textual `007` and a long numeric name survive the CSV round trip, and formula-looking text is never emitted as a spreadsheet formula. A literal leading apostrophe is doubled on export. Excel can show the protective prefix; the menu explains **Data > From Text/CSV**, UTF-8 and Text columns for names/college/date. Ordinary numeric fields are small integer values with no significant leading zeros; raw pointers and long numeric identifiers are not exported. Actual Excel application behavior is a witness item, not claimed from Python tests.

The shared page is edited under the explicit grant. No source writer is invoked by import. CSV export refuses the loaded source path or a path inside its save directory. Existing copy/saved-edits actions remain the publication routes.

## PROVED: native wait, importer, and bounds

Private evidence is read-only. The original `bn` image is absent at `NFL2K5_ESPN25_BN_IMAGE`'s default September 8 path, so the old bn native class skips precisely. This job does **not** claim to replay that full Experimental-minus-merged-positions executable. Instead it reads the pinned retail USA XBE/main ROST/SITU and all 35 real-rosters resources, compiles those resources privately through the existing research function, and tests these two executable recipes in memory:

| Input | SHA-256 |
| --- | --- |
| Retail USA XBE | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| Retail + existing 12-byte repair | `015080844a17f4b5a6162f204be2d31a37277a574039fb949e00661dd3234003` |
| Retail + existing repair + Practice Squad | `0ca8590c3543ea181e9837e8a98717d31aa974aea6b3db014be9924141c1e30b` |
| Unchanged historic dataset manifest | `9f2c1d1d67ef630300a081410129c71a53f9de54f4b02a89ec0cbe7087656ba8` |

The existing repair remains the same 12 bytes at `C2319` in `C2300`: store zero into the just-released pointer, advance the counter and repeat up to the team's byte count. No executable instructions, XBE allocation request, resource dataset or game-code writer behavior were changed by J6. The production ESPN-rosters module changed only its help/hold wording.

The new trace executes the actual archive waiter rather than the old unconditional success stub:

```text
2D1829  call 43F50             acquire historic resource (bounded archive boundary)
2D182E  call 432D0             return address 2D1833
432C0  mov ecx, [B09584]       busy word
432C6  xor eax, eax
432C8  test ecx, ecx
432CA  sete al                 ready only when busy == 0
432E0  call 38F50              event pump
432E5  call 432C0              poll again
432EA  test eax, eax
432EC  je 432E0                EXACT reproduced wait back edge
432EE  ret
2D1891  call C1030             native team import, only after the wait returned
2D1896  test eax, eax           native import success/failure branch
```

With Ice Bowl already staged, withhold Wide Right's completion and the bounded watchdog stops **at `432EC` with `[B09584] == 1` and no Wide Right `C1030` call yet**. Supply completion by tail-calling the native `42FC0` busy setter with ECX=0. Resuming the same suspended stack returns through the wait, imports both teams and publishes distinct Giants/Bills teams through `20CB30`; native QB picks are Hostetler and Kelly.

The additional event-table probe executes native `38F50 -> 38CD0`, registers the fixture callback through native `38D20`, and verifies dispatch at `38CF6: call [esi*8+B04D24]`. `[B04D1C]` is the event count; `[esi*8+B04D20]` is the re-entry guard. A callback that returns without delivering completion leaves the busy word set and loops for 64 observed back edges. Let that callback deliver and native `42FC0` clears busy; the same stack completes both imports and resets the dispatch guard. The callback models OS completion only; no actual Xbox asynchronous file request is delivered.

The unrepaired retail-plus-Practice-Squad recipe also reproduces the original stale-team fault: Ice Bowl -> Wide Right gives import returns `[1, 1, 0, 0]`, the released team has count zero but 53 nonzero pointers, and both getters publish the previous Cowboys team. All four archive completions have already returned and `[B09584] == 0`. This separates that known importer defect from an archive completion wait; it does not diagnose a downstream scene freeze.

With supplied completions, **each repaired recipe** executes sequence `0..24, 0, 14, 0` in one persistent arena: 28 selections, 56 imports, 56 native archive waits/completions and 54 releases. Every import succeeds; released pointer tails are zero; every selected match exports 106 players, uses distinct team pointers and resolves both kit names. Native scenario setup, depth rebuild and QB selection run with the same explicit world/clock/spatial boundaries as the existing live harness. This is bounded selection/import/setup/export proof, **not complete scene-load proof**.

Every native call retains the 40-million-instruction cap; the deliberately withheld wait also has a 64-branch watchdog. XBE reads are bounded to 16 MiB, each resource to the existing 1 MiB limit. No disc/pack copy, console, GUI display, audio or network was used. No retail bytes were added to fixtures or reports. The new native suite observes only the explicitly listed substitution/trace boundaries instead of invoking Python at every instruction; a new substitution outside that set refuses. The native instruction caps and executed game routines are unchanged. Both the original full-hook run (259.164 s) and final bounded-hook run (23.715 s) pass all four tests and produce six identical complete JSON receipts. Local derived receipts are under `/tmp/b69-j6-wait-fast/`; their outputs contain native observations, not resource binaries.

## HYPOTHESIS and unresolved gameplay state

The observed music freeze may involve this archive wait or a later scene/GPU/audio wait. **Its actual PC is still unobserved.** It would be false to equate an intentionally withheld completion with Noah's failing console state. The exact loop above is PROVED for the supplied state, not assigned to his report by inference.

The harness initially has no registered OS event consumers (`[B04D1C] == 0`) and no real pending Xbox I/O request. To diagnose the reported freeze, the missing evidence is the failing PC/stack, `[B09584]`, `[B04D1C]`, the `B04D20/B04D24` guard/callback slots, pending loader-list head `[B09578]`, active resource context/queued completion, and the later scene/renderer/audio state from the actual failing recipe and profile. If the game is at `432EC`, its real callback must complete and clear the busy word; clearing it unconditionally would assert readiness without the resource and is not a repair. If it is elsewhere, that PC must be investigated on its own evidence.

The build block remains in all five build entry points, including the private-copy preflight. Its new reason says native reload completes with supplied archive completions and asks for the failing archive/scene state. The direct BuildPlan refusal regression passes. Basic, Advanced and Experimental all resolve `espn25_rosters=False`; status remains EXPERIMENTAL / UNWITNESSED. The writer touches every moment, so omitting Wide Right is not a valid implementation of this option.

## Required witnesses

All items below remain UNWITNESSED in game/application where stated:

1. MacDog850: export every player from a real disc roster, signed Xbox save and franchise save; change one rating/name/contract field, inspect preview, Undo/Redo, write a copy and load that copy in game. Check a secondary-pool record and two same-name players remain distinct.
2. Excel: open and resave UTF-8 CSV using the documented Text columns, including `007`, long numeric text, literal apostrophes and non-ASCII names. Confirm protected text and identities remain unchanged, then import one edited cell with exactly one change.
3. Noah/heaven: capture the actual failing disc/XBE recipe, profile, controller side, fresh boot versus return visit and paused PC/stack/event state. Restore the pinned bn evidence if that is the failing build. Do not treat the local retail-plus-Practice-Squad recipe as bn.
4. For a separately authorized diagnostic candidate: Ice Bowl -> Wide Right -> Ice Bowl, both controller sides, distinct teams/names/kits, loading completion, first snap, moment ending and return to menu. Check Hostetler #15 and Kelly #12; recheck the earlier reported Packers #14 separately.
5. All 25 moments: fresh and repeat visits, names/numbers/eligible starters, existing shared-file lineup exceptions, scenario state, play, exit and profile save/reload. The 35 shared roster files still cannot provide every moment's exact historic lineup.

## Integration and delivery

`WIRING.md` contains the implemented page text, a schema-valid new player-CSV capability row (**+1**) and corrected fields for the existing historic-rosters row (**+0**). The protected registry currently claims availability and “no XBE edit”; the handoff corrects both. `studio_qt.py`, `mod_build.py`, registry rows, release checks and the release cave manifest were not edited. The existing career-stats/team-history lanes are unchanged.

`packaging/repin.py --apply` updates only the two existing roster module SHA pins in `mod_editor/core/providers.py`. Claude must regenerate the protected cave manifest for those source fingerprints. The four local XBE gates use the release manifest with exactly those two source hashes refreshed at `/tmp/b69-j6-manifest.json`; no span, ownership, allocation or game byte is changed, and that scratch file is not a newly observed real-disc manifest.

The new registry row validates against `#/$defs/capability`. Whole-registry JSON schema validation also reveals an existing unrelated mismatch: `registry.schema.json` allows at most two games while the checked-in registry has three. The protected schema/registry were left to integration.

The shared Git metadata at `/home/noah/2k-football-mod-tools/.git/worktrees/astra-b69-j6` is mounted read-only. Normal explicit-path staging failed with `index.lock: Read-only file system`. Commits therefore use isolated metadata at `/tmp/b69-j6-delivery.git`, the same base and branch name, and explicit file paths; the original worktree branch ref is not advanced. `ASTRA_J6.bundle` carries the resulting commit chain for integration. Code commits are `c50edfcb` (CSV preview and bounded wait) and `2bfe709c` (CSV snapshot semantics and native dispatch/efficient observation); the bundle also contains the final documentation commit. No push, unrelated worktree edit or original metadata write occurred. Initial root free space was about 79 GiB; only small source/test/report/receipt files were written, and no scratch disc was created.

## Exact validation

Validation commands/results follow below. All tests run standalone with plain Python and Qt offscreen; skips are not treated as native or gameplay proof.

For each filename below, the full command is `QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD" python3 tests/mod_editor/<filename>`. The native wait run additionally sets `ESPN25_WAIT_RECEIPTS=/tmp/b69-j6-wait-fast`. Logs are `/tmp/b69-j6-*.log`.

| Standalone suite | Tests | Time | Result |
| --- | ---: | ---: | --- |
| `test_nfl2k5_roster_csv.py` | 14 | 1.950 s | OK |
| `test_nfl2k5_roster_records.py` | 108 | 14.437 s | OK (skipped=1) |
| `test_mod_build_beta62_integration3.py` | 11 | 160.583 s | OK |
| `test_nfl2k5_abilities_v2.py` | 15 | 34.169 s | OK |
| `test_nfl2k5_espn25_exact_lineups.py` | 2 | 0.089 s | OK (skipped=1) |
| `test_nfl2k5_espn25_in_game.py` | 4 | 2.918 s | OK (skipped=1) |
| `test_nfl2k5_espn25_integration_qt.py` | 13 | 17.047 s | OK |
| `test_nfl2k5_espn25_native.py` | 7 | 4.718 s | OK |
| `test_nfl2k5_espn25_rosters.py` | 23 | 209.788 s | OK (skipped=1) |
| `test_nfl2k5_espn25_rosters_native.py` | 1 | 45.371 s | OK |
| `test_nfl2k5_espn25_scenarios.py` | 17 | 31.014 s | OK |
| `test_roster_editor_panel_franchise.py` | 2 | 0.469 s | OK |
| `test_roster_editor_panel_qt.py` | 50 | 4.325 s | OK (skipped=1) |
| `test_rosters_data.py` | 10 | 4.507 s | OK |
| `test_rosters_data_qt.py` | 6 | 0.691 s | OK |
| `test_rosters_reserves_abilities.py` | 13 | 12.269 s | OK |
| `test_rosters_reserves_abilities_qt.py` | 7 | 3.619 s | OK |
| `test_nfl2k5_espn25_loading_wait.py` | 4 | 23.715 s | OK |

The roster-records skip is the absent optional portrait catalogue. The page suite skips the full Studio-shell check without the private uniform catalogue under `reports/assets`. The historic dataset's private source check and exact-lineups PFR source class skip when their original source material is absent. The old bn in-game suite runs its four publication/patch tests but skips the bn-dependent native class because that private image is absent. The new retail-backed native wait suite has no skips. No skipped test is used to assert a native result.

Other checks: six full-instruction/sparse-observation native receipts compare equal; all three preset plans keep the historic option off; the new registry row passes its capability schema; final scratch-manifest source fingerprints validate; `git diff --check` passes; final repin reports zero further pin updates.

### All four XBE gates green

For each filename below, the exact command is `NFL2K5_CAVE_MANIFEST=/tmp/b69-j6-manifest.json python3 tests/mod_editor/<filename>`. This is the documented scratch source-fingerprint refresh; the executable writes and manifest spans are unchanged. The final CSV-only ordering refinement does not change any XBE owner behavior, and final manifest freshness was checked separately.

| Gate | Tests | Time | Result |
| --- | ---: | ---: | --- |
| `test_xbe_patch_memory_writes.py` | 115 | 1620.507 s | OK, no skips |
| `test_xbe_patch_cave_references.py` | 127 | 1889.719 s | OK, no skips |
| `test_nfl2k5_cave_oracle.py` | 29 | 352.444 s | OK, no skips |
| `test_nfl2k5_owner_pairwise_composition.py` | 388 | 2366.509 s | OK, no skips |

The committed source has no new XBE instructions or runtime state. These gates validate the existing game-code composition; they do not provide a gameplay witness or authorize lifting the historic-rosters block. All required standalone suites are green, with the precise private-evidence/catalogue skips listed above. The code and documentation are delivered through explicit-path commits in the verified bundle.
