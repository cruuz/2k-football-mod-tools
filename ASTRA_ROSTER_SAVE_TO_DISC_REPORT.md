# r64 roster save to disc

2026-09-07. Branch `astra/r64-roster-save-to-disc`, base
`98d1c6a4c6491b8d2118844e9d43f1fb6ed82a51`.
**EXPERIMENTAL / UNWITNESSED.** No console, emulator, display, audio, network,
real-disc build or push was used. Qt ran offscreen. Only this worktree and
bounded, automatically cleaned temporary fixtures were written.

## Delivered

`mod_editor/core/nfl2k5_roster_save_to_disc.py` compares a complete signed
Xbox roster or franchise save with the current disc roster. It accepts a
loaded `RosterDocument`, including edits made in that session, or a directly
chosen `SAVEGAME.DAT`, save directory or ZIP. Direct containers are limited
to 32 MiB and 4,096 members before the existing save reader loads their contents.
EXTRA must verify; an ambiguous multi-save container refuses. The disc reader
uses the existing bounded outer-entry-5 reader, accepting v17 and v18 ROSTs.
The existing save codec reads v0 and v1 arenas, including reserve overflow.

The output is ordinary `2k5_mod_studio_roster_edits/v1` JSON. There is no new
Build schema, flag, disc-copy operation or executable owner. Its separate
`*.receipt.json` includes source/result hashes, exact matching decisions,
matched/added/changed/unmatched counts, skipped fields and players with reasons,
per-team active/reserve/matching counts, free-agent counts and the actual replay
receipt. `changed` counts matched/added players affected; `disc_players_affected`
also counts retained disc-only players whose depth position shifted, and
`retained_players_reordered` lists those identities. `source_players` counts
named records; total and unnamed record counts are also supplied.

The CLI is immediately usable from the checkout:

```sh
python3 -m mod_editor.core.nfl2k5_roster_save_to_disc \
  --disc source.iso --save SAVEGAME.DAT --output roster_edits.json
```

The CLI refuses existing output/receipt paths. Neither input is modified.
The edits are then selected through the existing Build roster-edits option.

The protected Rosters panel is delivered as the exact, dry-run-checked
`tests/fixtures/roster_save_to_disc_wiring.patch`. It adds **Use this save's
roster on the disc...** as a save-session button and a disc-session Tools
file-picker action. It uses the existing `save_edits_to` export path and
`roster_edits_changed` signal, leaves the loaded document/undo journal intact,
and shows counts plus full skip/team details. The entire proposed module is
executed in memory by the offscreen wiring tests; after integration those tests
execute the shipped source. The protected panel itself was not edited.

The FAQ now gives seskid both answers: **Save Xbox save copy...** and copy
`SAVEGAME.DAT` plus `EXTRA` together to the HDD to PLAY; the new action followed
by Build with **Include exported Rosters edits** to BAKE. It explains why the
older session-diff exporter produced no complete-roster edits.

`WIRING.md` contains the required dated section, exact patch command,
allowlist lines, runtime import, all dispatcher/status/preset/non-applicable
fields, and the registry insertion. A schema-valid capability object is supplied
at `docs/mod_editor/nfl2k5_roster_save_to_disc_capability.json`; the protected
registry is unchanged. No protected packaging, manifest, Build, Studio or
release-tag file was edited.

## Matching and capacity decisions

- Match case-insensitive first/last names within the same primary/secondary
  pool. Resolve duplicates through play-by-play ID, then star-tag agreement,
  then shared team membership. No star bit alone establishes identity.
- Finish name matches before considering renamed players. A rename requires
  a unique, nonzero play-by-play ID plus identical birth month/day/year bits,
  within the same pool. Ambiguous competing source claims are skipped. A
  source ordinal alone never authorizes replacing a different disc player.
  This is intentionally conservative: it cannot infer that a newly created
  modern player is the same person as an unrelated retail player in that slot.
- Added players may use an unnamed, unowned primary NFL slot with no history,
  play-by-play ID, photo or star tag. Named free agents, secondary templates,
  zero-type draft-window records and flagged prospects are not free slots.
  The record table never grows. Both names must fit before an added player is
  accepted; failure rolls back that entire addition. Ordinary matched players
  retain a name that cannot fit while carrying other supported fields.
- Use the existing name-pool writer: reuse existing strings, reclaim a solely
  owned allocation or fit an existing free span. Never truncate, normalize
  silently, enlarge the name pool or transplant pointers. Colleges resolve by
  text in the target's existing table. Missing colleges are listed as skipped.
- Carry named non-pointer fields for numbers, positions, all 28 rating/style
  bytes, appearance/equipment, contracts, birth/experience, depth assignment
  and the existing packed lock/ability/Guardian fields. Preserve the disc's
  star tag and other undecoded fields; differing excluded values are listed.
  History streams and all source-relative pointers stay with the disc.
- Team identity uses stable ordinal plus kind and asset ID, so ordinary NFL
  text renames do not break matching and absent created-team slots are reported.
  Trades, releases/signings, all-star aliases and depth order use explicit v1
  moves. Existing disc-only players remain. Existing free-agent order remains;
  the free-agent set and additions/removals carry over where representable.
- A retail/EDGE code scheme and a pooled code scheme cannot mix. The refusal
  names both schemes, explains retired OLB code 10 and pooled 11/15/16 meanings,
  and says no conversion was exported. EDGE-only label changes are compatible
  with retail codes. Direct file loads use the existing data-based detection;
  a loaded document uses its selected scheme. Detection remains the existing
  heuristic, not a new proof of a save's executable provenance.
- Reserve ownership changes cannot be represented by ordinary roster edits.
  Preserve target reserves, carry matched reserve attributes, and list each
  unsupported ownership change. Franchise IR ownership is also outside the
  roster arena: retain target membership/status and report the omitted IR
  conversion. Season, schedule, progression, stats and salary ledgers are not
  transplanted. The receipt explicitly says a franchise uses its roster arena.
- The existing move batch's minimum-roster rule remains. If a complete desired
  membership batch cannot replay, omit that batch and report the reason for
  affected source players; independently supported field edits still export.
  The receipt and result dialog make this partial result explicit.

Two narrow shared replay changes were necessary. `replay_moves` now derives
its end-state ceiling from `membership_limit()` instead of the obsolete fixed
54: 65 active pointers, reserve storage accounted for, 70 combined storage in
a grown arena, and the existing regular-season 53 limit where applicable.
It also refuses ordinary moves on a reserve, preventing a second owner. Pure
depth rotations are supplied explicitly by the new exporter because the older
session-diff exporter omits reorder-only entries. Depth rank, side and lock bits
are pinned in mover entries to undo the replay's automatic reranking exactly.

## PROVED

Every returned export is applied with `nfl2k5_roster_records.apply_body` to a
private copy of the exact current disc body. Its log must be empty and the
complete resulting body must equal the planned body before the result is
returned. This detects partial membership replay, silently skipped name writes,
automatic reranking and other dropped fields. Two exports from identical
inputs produce identical edits and receipts, with no time/path-dependent data.

Standalone tests cover an already completed save with zero session edits,
trades, releases, signings, first/last renames, numbers, position, ratings,
equipment, contracts, college, depth-only reorder, stale load baselines,
ambiguous identities, star/team disambiguation, shifted record order, oversized
names, additions with/without a free slot, failed addition rollback, signature
refusal, direct directory/ZIP/loose saves, CLI output, position mismatch,
65-slot capacity, minimum-roster batch refusal, reserves, franchise IR and
season bytes, v18/v1 overflow, and a schema-valid registry proposal.

A synthetic XDVDFS image smaller than 1 MiB passes the real disc writer and
re-reader. Every carried player field/name and team/depth list round-trips.
The test compares all image bytes outside the roster body and applies the same
JSON twice, proving unchanged wrapper/neighbors and identical replay bytes.
All synthetic images live under resolved `TemporaryDirectory` roots and are
removed on exit. No whole retail disc or pack is loaded into RAM.

A bounded retail ROST and its real reclassified variant pass the exporter and
replay. Three preserved, signature-verified franchise saves were also compared
read-only with retail. These are offline data witnesses, not played witnesses:

| Preserved save | Named records | Matched | Added | Changed matched players | Unmatched | Skipped items |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| f0 / 0B8506889D40 | 2,472 | 609 | 0 | 524 | 1,863 | 3,255 |
| f1 / 0B8506889D40 | 2,472 | 609 | 0 | 524 | 1,863 | 3,255 |
| Franchise1 / 256B40374FD6 | 2,479 | 666 | 0 | 666 | 1,813 | 3,432 |

All three replay logs are empty. The large unmatched counts matter: modern
community players absent from retail are not silently assigned occupied retail
slots. A save import can be partial and its receipt must be reviewed. Many
skipped items are fields on otherwise matched players, so skipped-item counts
are not unmatched-player counts.

Retail body SHA-256:
`b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae`.
The f0/f1 input save hashes are respectively
`56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8` and
`255da39178695a69c01efad9237764cbbd88c63aa78cfe911c8e3b070b6215ed`.
Both produce body
`582560c6c8bc66bcb847dc91a68b5396b28c35a7b87afab4bdb1d5f3537ccecd`.
Franchise1 input is
`0db746fe2c8ae2102fdd420863a5e5bcddec4b83ac3e234568824c337e4422a7`;
its resulting disc body is
`ddb41097f3768d625b24c33bc367bb0c3b0e0b1593b543839040741c2a639af6`.
Full receipts and the reproducible probe script are scratch-only, not committed.

## Exact validation

Every suite below ran as a standalone plain-Python unittest process, with
`QT_QPA_PLATFORM=offscreen` for Qt. `/usr/bin/time -v` measured memory.

| Command (`python3` from this worktree) | Tests | Result |
| --- | ---: | --- |
| `tests/mod_editor/test_roster_save_to_disc.py` | 21 | PASS |
| `tests/mod_editor/test_roster_save_to_disc_wiring.py` | 6 | PASS |
| `tests/mod_editor/test_nfl2k5_roster_records.py` | 108 | PASS, 1 skip |
| `tests/mod_editor/test_roster_editor_panel_qt.py` | 50 | PASS, 1 skip |
| `tests/mod_editor/test_mod_build.py` | 11 | PASS |
| `tests/mod_editor/test_build_panel_qt.py` | 11 | PASS |
| `tests/mod_editor/test_mod_build_beta62_integration.py` | 8 | PASS |
| `tests/mod_editor/test_rosters_reserves_abilities.py` | 13 | PASS |
| `tests/mod_editor/test_roster_editor_panel_franchise.py` | 2 | PASS |
| `tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 | PASS |
| `tests/mod_editor/test_rosters_data.py` | 10 | PASS |
| `tests/mod_editor/test_rosters_reserves_abilities_qt.py` | 7 | PASS |

Total: **260 tests, 258 passed, two existing evidence skips, zero failures**.
The skips are the unavailable private portrait catalog in the records suite
and unavailable private uniform catalog for the Studio mount test. The highest
measured suite RSS was **408,524 KiB**, in the existing Rosters editor suite,
well below 2 GiB. The exporter suite was below 128 MiB. Logs are under
`.scratch/roster-save-to-disc/`. Initial fixture/implementation failures were
corrected and have passing final runs; these included all-star/free-agent
aliases, unmatched depth anchors, in-session free-agent counts, and the registry's
required writer classification/operation pairing and canonical ID ordering.

Also run: `python3 -m py_compile` on the new core/test modules,
`git apply --check tests/fixtures/roster_save_to_disc_wiring.patch`, and
`git diff --check`. The whole proposed GUI module compiles and runs in its wiring
suite. No XBE owner changed, so no new union-gate entry, allocator budget or
manifest update is needed; the unrelated executable gates were not rerun.
No staged product release was built. Protected packaging/registry integration
must precede its normal release closure checks.

## HYPOTHESIS, limits and Noah's witness list

Identity recovery for a renamed player assumes a unique play-by-play ID plus
birth bits continues to identify that player. It cannot recover identity after
all such anchors change, nor safely distinguish two otherwise identical records.
The user's actual community save and reported Josh Allen session were not
supplied; no exact-match percentage is claimed for that roster. Source-body
hashes are receipts; the general v1 Build consumer still permits application to
other rosters, so regenerate the export whenever the source disc changes.

Game-visible effects of carried ratings, contracts, appearance, depth and
membership remain UNWITNESSED. A copied portrait/voice ID requires the matching
disc asset, and ability/Guardian/lock bits require their corresponding runtime
patches. This importer does not install assets or gameplay patches. Source saves
can override the built disc roster in game. New name allocations, roster-pool
growth, arbitrary slot replacement, reserve/IR ownership import, franchise-state
migration and translating pooled positions are outside this export's proven lane.

Noah's pending witness list:

1. Apply the protected wiring and package it with the specified closure entries.
   Open the reported signed community save with the intended project disc.
   Run the new action, inspect every unmatched/added/skipped player and compare
   the displayed team counts. Confirm Build receives the saved path.
2. Build with **Include exported Rosters edits**, reopen that disc in Rosters,
   and compare carried names, numbers, ratings, equipment, contracts, teams,
   free agents and depth order with the save/receipt. Confirm skipped names are
   unchanged rather than truncated and all partial membership batches are clear.
3. Load the disc roster in the game without an HDD roster overriding it. Check
   team/player menus and take a practice snap with several changed players,
   including a trade, a released player, an acquired free agent and reordered
   depth. Record actual appearance and position selection.
4. Separately use **Save Xbox save copy...**, restore SAVEGAME.DAT and EXTRA
   together to the HDD and load it. Confirm that PLAY workflow retains the
   franchise season and reserve/IR ownership, distinct from the disc seed.
5. Check a 65-active offseason roster and a grown reserve roster with the
   appropriate runtime support. Confirm skipped reserve/IR changes and an
   added player using an eligible free slot behave exactly as receipted.
6. Re-export after another save edit and after changing the project source.
   Confirm the Build path and receipt refresh, while the editor document and
   undo history remain available. Confirm a pooled/retail mismatch refuses with
   its exact explanation and publishes no new Build file.

## Delivery

The authorized bundle fallback is used. Initial explicit-path staging succeeded,
but the final update failed with a read-only `index.lock` error. The shared
index may retain that earlier staging snapshot. Final files remain in this
worktree. Isolated Git metadata under `.scratch/roster-save-to-disc/git` holds
the explicit-path commit on `astra/r64-roster-save-to-disc`, with parent
`98d1c6a4c6491b8d2118844e9d43f1fb6ed82a51`. The verified bundle is
`.scratch/r64-roster-save-to-disc.bundle`. No push occurred. `ASTRA_BRIEF.md`
and `.scratch/` are excluded from the commit. Protected source files are
unchanged; the GUI/release integration is the requested exact handoff. No
acceptance disc or archive copy remains. Scratch is below the 200 MiB limit.
