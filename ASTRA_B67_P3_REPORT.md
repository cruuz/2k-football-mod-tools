# Beta 67 P3 game-side handoff

Base: `653cb708`. Delivery branch: `astra/b67-p3-game`.

This is an **incomplete integration handoff**, not a claim that beta 67 is
ready to release. Every name in `BETA67_API_CONTRACT.md` is implemented with
its specified signature. The bounded proofs below establish the implemented
ordinary selector arithmetic and authoring bytes. The full live defensive
model, caller lifecycle classification, and saved Studio art-project rebuild
and reopening requirements remain open. No emulator, displayed GUI, network,
or retail-in-place write was used.

## PROVED

- `apf2k8_playcall_model.py` implements the cold offensive situation row,
  category distance/mean-rating lottery, formation weights, X play weights,
  assignment-based history-free suitability, run/pass gates, defensive
  request rows and directional distance curve, and paired-component supply.
  Float operations and roulette accumulation use the native rounding order.
  Preview samples use Python seeds; native proofs inject the same uniform
  into the retail roulette, not a claim of equal game RNG states.
- The requested heavy raw **7/7/7** recipe has the opposite category effect
  from the brief's intended result: the native category rating is **0.1**;
  raw **0/0/0** gives **3.0**, before distance and cubing. These values are
  directly observed at the native category candidate buffer. The raw API
  keeps the agreed shifts and values. P4 may display a reversed strength
  control only with an explicit conversion.
- SPLB setters preserve independent rating/tag fields, edit all duplicate
  formation records, rebuild category caches, retire references with a
  surviving primary, and compact whole records for removal. Removal equals
  two native `84A8C790` passes byte for byte, allowing only the runtime
  MASTER pointer at `+7E0C`. Native ordinary offense and defense selectors
  exclude a removed formation in **64 seeds × 20 situations per side**.
- After the tested removals from stock outers 767 and 134, **every** ordinary
  row in `row_coverage` has a nonempty category set. The real `84860730`
  search reaches a nonnull category at `8486088C` for every one of those
  rows, and that category belongs to the returned set. Arbitrary books may
  still have empty rows; this API reports them rather than asserting safety.
- The full eleven-player builder, **`84860020` entry through return**, reads
  edited Flush roles, requests one TE, and writes all eleven role and slot
  fields. The fixture supplies an eligible player per requested slot at
  `847B29E8` and bounds presentation refresh at `847C1728/847C16D0`.
  Roster depth selection is outside this proof. Moving 5-2 category 27 from
  MASTER row 12 to row 13 gives native ordinary defensive weight **1**.
  **MASTER is shared by every book on the disc, including all clones.**
- The ROST writer follows each team's relative `+F8` tendency pointer. Its
  `+5A` byte is converted by native `8492A440` to `(pass, run)` halfwords;
  `84929A48` through the `84929AE4` calculation witnesses run shares
  **0, 0.5 and 1**. Stored row bytes `+8E/+99` expand to runtime halfword
  arrays `P+9E/P+B4`. Both arrays **are read** in the optional tendency cache
  path `84929B4C..84929E44`, so their API is implemented. They do not replace
  the ordinary CPU `AEB0` category lottery.
- Experimental category curve payloads are pinned to the existing BASE and
  TU 1.1 profiles. They change only y ordinates at `820C88A8/820C88D4`
  (TU **+20**). Native candidate weights agree with the patched model to
  **1e-6 on both images**. Canonical TOML verification rejects foreign or
  duplicate writes. A fake-folder installer test exercises P2's atomic
  write/config primitives, keeps the independent pass-fetch file, and checks
  idempotence. P4's actual installer dispatch still needs the WIRING change.
- `own_book_plan` plans **24 offensive plus 24 defensive** disc-team copies.
  A read-only compile of all 48 against the real retail archive fits its
  existing directory and reparses all clones. Distinct existing ROST strings
  supply the resource names; no string-pool
  capacity is guessed. Existing saved-team label readers are protected.
  `compile_unlock(..., asset_replacements=...)` composes ROST/donor/other IFF
  overlays by filename hash and inserts all clones in one archive pass.
  The synthetic two-volume build reparses all 48 clones, resolves every team
  label to its own resource, compares every unrelated original pack byte,
  verifies idempotence, and resolves every original asset after ordinals move.
  The crest and field allocations in this test are synthetic transport
  payloads, **not** a saved Studio project or real art-writer output.

## Model boundaries and unmet acceptance items

1. **Offensive tuple sweep: PASS.** All 10,240 category/formation/play tuples
   agree with native draws, and candidate vectors agree to 1e-6, across
   40 situations and four stock/edited books.
   The earlier broad sweep found a stale global play cache in the P1 added
   book. Native Jacks had 8 candidates before normalization and 28 after.
   The model now honors that cache and notes missing memberships. A separate
   native regression proves both cache states, run/pass endpoints and 384
   supplied draws. The four-book sweep uses normalized additions. Native
   play vectors may be memoized for identical book/formation/category and
   rounded distance: down is not read by the empty-history `68C70` arm.
2. **Live/default defense is not fully modeled.** `8486A9D0` calls the lineup
   evaluator `84865AE0` even with empty learned history. It reads the
   opponent's play assignments and player objects before passing its scalar
   to `84863F58`. Those inputs are absent from the contract's defensive
   preview signature. The full category/formation/component matrix agrees on **40 situations × 4
   books × 64 supplied draws** with the native feature evaluator bounded to
   four. The preview uses feature **4**, clearly marked
   **HYPOTHESIS** in `.notes`. Conditional native agreement does not prove
   that four is the retail default. Clock-management urgency, saved USER
   banks, previous-call caches and global merges are also not reconstructed;
   their limits are present in both preview notes and the user guide. The
   special request branches also assume down one and a 50-yard kicker range;
   neither assumption supplies live player attributes.
3. **Resolver caller lifecycle is UNCLASSIFIED.** The pinned full aligned-word
   scan finds exactly two direct callsites: BASE `84A0504C/84A0505C`, TU
   `84A05F04/84A05F14`. They are in BASE `84A04FF0` / TU `84A05EA8`, which
   supplies both team managers unconditionally, selecting their order from
   argument r6. The only absolute resolver/parent references found are unwind
   table entries. No direct caller of that parent is found. Its computed or
   indirect entry and human/CPU lifecycle are not established. This cannot
   support a human-only classification or a CPU exclusion claim. **Keep the
   66.1 refusal.** See the regenerated static receipt; no downgrade is
   authorized by this evidence.
4. **Special formation removal is refused** for IDs 151..162. P2's ordinary
   whole-record compaction is reused; special-tail and merge repair is not
   inferred from it.
5. **Archive insertion open item 4 is only partly closed.** Core transport and
   saved name bindings are implemented and tested. Authored donor ratings
   also survive a scheme preset before cloning. Studio project manifest
   persistence, family-specific asset-id/metadata rebinding, and final build
   receipt wiring are still required in P4-owned files. `WIRING.md` identifies
   the exact integration points and core calls. A real saved crest + field-art
   + 48-clone project has not been built and reopened. `/` has 85 GB free,
   below the handoff's 100 GB floor; writable roots do not include the required
   Storage scratch area. No retail disc copy was made to bypass that limit.

## Exact gameplay witnesses for Urianus and Noah

Everything in this section is **UNWITNESSED** in the game. Complete P4's
staging/build integration first; a core API or registry row is not a usable
Studio control.

1. Start a fresh project from an owned retail folder. Give the intended CPU
   team its own offensive book using O-Singleback3WR. Add ordinary Jacks or
   Jokers plays from O-Shotgun if absent. Rebuild the stored book caches.
2. Preserve the brief's exact requested values as a **negative control**:
   heavy raw **7/7/7**, every Ace record raw **0/0/0**. Build a separate game
   folder, reload a match without a saved USER-book override, and observe
   first-and-goal at the one. Record team, loaded book name, BASE/TU, down,
   distance, score, clock and formation. These raw values favor Ace, so a
   heavy goal-line call is not the expected or guaranteed result.
3. For the intended positive witness, use heavy raw **0/0/0**, every Ace
   record raw **7/7/7**, build a new folder and reload. Repeat fresh
   first-and-goal calls and record a selected heavy formation and visible
   personnel. This remains a lottery. If P4 exposes “strength 7”, record its
   converted raw triple as well. Remove that formation, rebuild and reload;
   verify it stays absent. Repeat removal on defense when testing that side.
4. For a third-down TE, give **Straight** formations high preference through
   low raw category ratings and reduce competing Flush/Queens/5 Wide
   preference. Preview and witness third-and-3, third-and-8 and third-and-15.
   Optionally export/install the experimental curve to “make the CPU stick
   closer to the situation's personnel”. Alternatively change a Flush WR
   role to TE in shared MASTER, preserving depth bits. Witness the visible
   TE, assignment, alignment and route behavior; check other teams because
   the MASTER edit affects every book.
5. For defense, add 5-2, move its shared category from row 12 to 13, build and
   reload. Record an ordinary native-selected 5-2 call and its on-field
   lineup. Keep the separate curve and pass-fetch patch statuses explicit.

## Validation actually run

All commands below are standalone unittest modules with the repository on
Python's import path. Native tests use owned files and skip precisely when
inputs or optional dependencies are absent. No retail fixture is shipped.

| Command (`python3 -m tests.mod_editor.` prefix) | Result |
| --- | --- |
| `test_apf_b67_model_native` | 4 PASS, 1188.259 s; 10,240 native category/formation/play tuples |
| `test_apf_b67_model_edges_native` | 1 PASS, 21.453 s; 8/28 candidates, 384 draws |
| `test_apf_b67_defense_model_native` | 4 PASS, 82.955 s; 10,240 conditional full tuples and 51 special-row cases |
| `test_apf_b67_writers` | 6 PASS, 0.203 s |
| `test_apf_b67_writers_native` | 5 PASS, 253.636 s; both images, full builder, nonnull covered rows, removal 64×20 per side |
| `test_apf_b67_static_audit` | 1 PASS, 6.379 s; exact BASE/TU receipt regeneration |
| `test_apf_b67_clone` | 3 PASS, 38.133 s; synthetic build, saved name manifest, real 48-clone compile, donor/preset composition |
| `test_apf_book_unlock` | 19 PASS, 23.428 s |
| `test_apf_book_unlock_retail` | 5 PASS, 1 SKIP, 17.416 s; raw-save path not supplied |
| `test_apf_splb_writer` | 22 PASS, 0.215 s |
| `test_apf_splb_formation_personnel` | 11 PASS, 1.028 s; Qt offscreen |
| `test_apf_splb_add_multiple_formations` | 14 PASS, 0.455 s |
| `test_apf_splb_tag_reassignment` | 85 PASS, 1 SKIP, 2.373 s |
| `test_apf_playcall_patch` | 11 PASS, 1.865 s |
| `test_apf_b67_xenia_patch` | 3 PASS, 0.107 s; fake Xenia folder |

Retail clone tests were given `APF_BOOK_RETAIL_INDEX` and
`APF_BOOK_FLAT_PE`. Native flat-image overrides are `APF_RETAIL_PE` and
`APF_RETAIL_TU_PE`; `APF_RETAIL_INDEX` controls the owned index.
The native model setup reuses P1's MASTER initializer and harness, and
P2's added-book/defensive harness rather than re-deriving their findings.
The 256-seed preview measured **0.0201 s** in the final full suite (also 0.0452 s during parallel native tests), below the required 0.5 s.

## Integration and delivery

`WIRING.md` contains eleven `apf2k8.playbooks.*` registry rows, each with
an evidence path and a `python3 -m tests.mod_editor.<module>` validation
command, APF allowlist additions, curve installer dispatch, and archive/project
integration boundaries. The 2K5 allowlist and Studio are unchanged.

The workspace git metadata is read-only and points outside the writable root.
Delivery therefore uses explicit-path commits in an isolated git directory and
a bundle based on `653cb708`. `python3 packaging/repin.py --apply` is run last
before every commit. Explicit-path commits so far: `045667e9` (model/writers/native proofs),
`691add51` (48 clones and named asset composition). Each repin run reported
`applied 0 pin update(s)`. The delivery file is `astra-b67-p3-game.bundle`; it contains these commits
and the final documentation commit, with `653cb708` as its prerequisite.
Verify and integrate from an integration checkout:

```sh
git bundle verify /path/to/astra-b67-p3-game.bundle
git fetch /path/to/astra-b67-p3-game.bundle astra/b67-p3-game
git cherry-pick 653cb708..FETCH_HEAD
```

The bundle is not a release artifact and must not enter the APF allowlist.
The original worktree's git HEAD remains at the supplied base because its
metadata is read-only; the explicit-path commits are carried by the bundle.
