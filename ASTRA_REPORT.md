# Beta 70 APF-1: Book Identity, portable bundle fits and Urianus handoff

Branch `astra/b70-apf1`. Implementation checkpoint `665b1cb6`.
Read `ASTRA_CONTEXT.md`, beta-70 rows 18–20 and Carried/additional requests,
the hub's beta-69 triage, J9/J10, and all four beta-67 reports.

**Every in-game outcome is UNWITNESSED.** PROVED here means the named offline
writer/reparse, test execution or bounded native experiment. HYPOTHESIS covers
the football effect, reporter-specific cause and platform performance beyond
this host. No emulator, display, audio, network, Discord message or push was used.

## Delivered

- [Walkthrough](docs/mod_editor/apf2k8_book_identity_walkthrough.md), linked
  from Book Identity's **How this works** button and `APF2K8-README.md`.
  It distinguishes labels/resources, independent CPU books, three existing
  starting recipes, eight beta-69 calling schemes, Fine-tune, offline
  `A_PROVEN` readback and the Xenia launch/patch boundary.
- Three offscreen editor screenshots from the real replay tool. The focused
  replay loads the retail identity table, selects Wide Zone, stages a stock
  replacement through the real background worker, saves/reopens its project,
  and opens the bundled guide. No game pixels are captured; the source-path
  label is replaced with “Your built APF game folder”. The panel scrolls when
  its expanded controls exceed the available height. Screenshots were opened
  and visually inspected after fixing an overlap in the first layout.
- ADVANCED **Replace starting content of a stock book**, unchecked by default
  and reset after each successful staging. One explicit book/scheme choice
  replaces that target; other staged target choices remain. Save/reopen, Undo,
  source preservation, complete copied-build readback and allocation refusal
  use the existing Scheme Presets provider and build dispatcher.
  CPU Play Calling's staged preview also composes the replacement, reading
  every donor from the source so two target choices cannot change each other's
  inputs through their order. This integration was added during the final
  consumer review and tested against the compiled replacement hashes.
- Deduplication of pending six-mask fits, bounded transfer of fitted streams
  from preflight to package workers, and cache keys that include encoder policy.
  New `--disable-helper` and `--repeat-inputs` benchmark switches reproduce
  portable and repeated-input cases across spawned workers.
- Corrected rating help discovered during Urianus's review. Raw 0 is not
  universally strongest: neutral equal 0 ratings give category weight 3 and
  formation weight 0.5; equal 1 ratings give 2 and 2. Play X changes initial
  weight, not a guaranteed call frequency. Numeric writers remain unchanged.

## Stock replacement proof and limits

The eight target names are **O-ManBlock, O-TwoBack, O-SinglebackAce,
O-Singleback3WR, O-WestCoast, O-ZoneBlock, O-Shotgun, USER-o**. They resolve by
filename/name, never assumed archive ordinal. The user's “O-ZoneBack” and
“USER-0” are corrected to the actual resource names in the guide.

`scheme_service.SCHEME_CONTENT` explicitly maps the eight beta-69 scheme IDs
to named donors. Wide Zone, Spread-to-Run and Power/Gap apply the existing
membership/audible recipes. The other schemes start from complete named donor
content. All eight reuse beta-69 personnel preferences and formation deltas.
This is an authored starting-content mapping, **HYPOTHESIS as a coaching scheme
approximation**, not newly researched historical playbooks, new routes, blocking,
motion or a team tendency write. The guide and each receipt state that limit.

PROVED: replacement begins from the donor's whole book, so old target plays
are not merged back. Existing writers apply membership, tags, ratings, name
replacement, cache normalization and fixed-allocation H7A transport. The
independent census verifies donor play memberships, audible slots, formation
and personnel fields, allowed rating changes, rebuilt caches and the donor's
special-call tail. Every ordinary personnel row must remain covered. A repeat
compile from the same donor is identical. Conflicting Fine-tune selectors
refuse with “build those first or revert them”.

The existing build receipt, **`.apf2k8-mod-studio-build.json`** in the output
folder, includes complete before/after content, target/donor hashes, scheme,
membership recipe, ratings, compressed allocation sizes and verification.
The actual build reparses changed entries and compares unrelated bytes.
`A_PROVEN: resource reparsed` remains an offline resource/assignment status.

The read-only retail matrix tried **64 combinations: 38 fit, 26 named capacity
refusals**. Example: Air Coryell into O-Singleback3WR needs **2,448 bytes**;
that book holds **2,048**. No overflow is published, and no plays are silently
dropped to fit. Choose another stock target or copy the scheme's donor into an
independent book. Some target/recipe combinations are therefore intentionally
unavailable. Every team sharing a replaced stock book receives its new content.
Build and reopen before further Fine-tune or independent-copy work.

## PS3 bundle measurements and byte proof

Aszemple: “only thing is its very slow to import and build the logos from the
PS3 Bundle”. The carried statement that the PS3 path never uses the helper is
stale: J10 added that Linux path. This job measures with it **disabled in the
parent and spawn workers**. The helper itself remains unchanged, 0755,
18,568 bytes, SHA-256 `d081d19c0078f768d2cb935732c910945c55d372dd9e1cc2b3e16ef9cfcf86a0`.

| Synthetic pipeline | Before, seconds | After, seconds |
| --- | ---: | ---: |
| One six-mask crest | 17.179 | 14.171 |
| 32 distinct six-mask crests | 102.174 | 72.916 |
| 32 destinations repeating one six-mask input | 58.212 | 49.507 |

For 32 distinct crests, measurement fell **36.647 → 28.197 s**, package
compilation **28.890 → 12.911 s**, linked cache **28.583 → 25.197 s**.
For the repeated-input case, measurement fell **23.393 → 12.929 s**. The
baseline already reused worker-local results in some later phases; deduplication
does not imply a 32-fold end-to-end speedup. The linked cache remains about
24 seconds in that repeated case. No greater speed claim is made.

These are single, shared-host Linux/Python 3.12.3 runs using J10's generated
512×512 pairs, independent l0/l1 RGB masks, shade ladder, package writer,
linked cache, span application, fsync and readback. Fixture generation, full
game-folder copying, actual reporter files and normal source opening are
outside the timer. Windows/macOS native execution and wall times are
**UNWITNESSED**; equivalent improvement there is **HYPOTHESIS**. Inventory
timings cover synthetic layouts, not a scan of all retail destination sources.

PROVED in [synthetic parity](reports/b70_apf1/synthetic_parity.json): all
packages, complete fit receipts, written archive hashes and linked-cache
directory/payload hashes match the beta-69 portable baseline for `[1,32]`,
and for the separate repeated 32 case. The canonical native `[1,32]` outputs
also match J10's committed `after_complete.json` exactly. The retained J10
retail parity tool passes full packages at **36, 1133, 712** and linked-cache
catalog **1**, including forced Python packages. No retail parity case skipped.

### Encoder policy, explicitly preserved

The shipped beta-69 `compress_h7a_best` returns greedy without the Linux helper
unless `APF_H7A_PYTHON_OPTIMAL=1`. Its broad changelog wording claiming default
portable optimal was inaccurate. This job preserves the actual beta-69 output
policy, rather than silently changing selected fit rungs on Windows/macOS.
Greedy always runs first; the optimal rung is requested only after a miss and
uses the established native/explicit portable policy. The optional portable
optimal transcription remains byte-tested against the helper. Enabling it by
default would be a separate behavior change and can take minutes on difficult
art; that change is not included in these helper-disabled speed measurements.

Pending jobs now group by both input image hashes, the encoder policy, exact
destination-layout signatures, minimum budgets, descriptors, offsets and all
preserved seed bytes. Fits remain pairs of three region masks; no layer is
mirrored or replaced by the other. Fitted streams are bounded to 64 MiB and
keyed by the exact encoded block, shift, candidate limit, parse and policy.
Package workers reread/hash the source before using them, then retain existing
independent package verification. Altered masks, layout, source or policy miss
the corresponding cache. No persistent disk cache or new binary was added.

## Claude → Noah: ready-to-send Urianus DM handoff

Urianus's September 15 reply was “Not yet, got caught up with RL stuff. I'll do
it in an hour or so”. His September 11 reports predate beta 67; this is not a
claim that he tested and rejected beta 67/69. Nothing was sent to him by this
job. The text below can be handed to Noah for the DM.

**Before all four checks:** build a new folder, fully close Xenia, launch that
folder through Studio and start a fresh matchup. Record BASE or TU 1.1, team,
book name, saved roster/USER A/B override, down/distance, field position, score
and clock. Keep the project and build receipt. The checks below are all
**UNWITNESSED in game**; offline previews alone do not close them.

### 1. “REMOVING formations”

Beta 67 already removes all ordinary records for a formation, compacts complete
surviving records and rebuilds caches. Beta 69 adds reversible **Never call
(ordinary CPU lottery)**: it clears the formation's B membership masks while
retaining its plays for explicit calls. It requires another surviving formation
for every affected category. Special formations **151–162** stay protected;
a cached Hail Mary can bypass ordinary membership.

**PROVED offline:** beta-67 native normalization retains compact removal;
beta-69's prior 10,240-tuple test excludes ordinary formation 68. This job reruns
the ordinary run/pass boundary and defensive exclusion suites, with real
normalization. Saved working books, global merges and hot special caches remain
outside that exclusion promise.

**Your exact check:** in O-Singleback3WR, remove an ordinary stock formation
with surviving row coverage, build/restart and check both its menu absence and
repeated CPU calls at 1st-and-10, 3rd-and-8 and goal line. Separately try Never
call on a covered ordinary formation: it should remain available for explicit
calls and disappear from the ordinary CPU preview/calls. Uncheck it and compare
again. If it reappears, retain the active saved book and matchup context so we
can identify the load/merge source. A special-call result does not test the
ordinary Never call promise.

### 2. Added heavy sets and situational personnel gating

You reported added Jacks/Jokers “doesn't trigger them in run situations, like
on GL”. Beta 67/69 already uses per-book category, formation and play lotteries;
the separate seven-step lineup search is not that CPU selector. Add Formation
already writes the required primary category and membership. USER-o copies use
the same selector and do not bypass situations. Category roles are in shared
MASTER, not a private per-book XEX personnel table.

**PROVED offline:** native O-Shotgun, O-Singleback3WR with added Jacks/Jokers,
and a named clone select heavy run plays in the supplied goal-line state.
This is a counterexample to a universal admission restriction; it does not
reproduce your exact loaded-game result. Team tendency, history, loaded USER
content and distinct special callers remain possible explanations, **HYPOTHESIS**.

**Your exact check:** add Jacks formation 9/category 0 and Jokers formation
5/category 1 from O-Shotgun to O-Singleback3WR, carrying compatible run and pass
plays. For a donor comparison, set their raw ratings to **2/4/4**. Preview
1st-and-goal at the one, neutral tied first-quarter state. Build/restart, compare
O-Shotgun, the edited stock book and an independently assigned copy, and log
CPU goal-line run calls and visible personnel. If only the added/copy version
fails, keep that saved book/project. Do not use 7/7/7 to favor heavy categories;
the rating direction and the special 0-versus-1 distinction are now explicit.

### 3. “Except 5-2, which is never selected if added”

Beta 67 proved the ordinary defense request is row 13 in the mapped midfield
matchup, while `5-2:Big` is stock row 12 and gets zero below-request weight.
Beta 69 fixed the row-13 button to recognize the actual `5-2:Big` name.
The EXPERIMENTAL MASTER edit affects every book carrying that category.

**PROVED offline:** the prior beta-69 native 128-state comparison selected
5-2 **0 times at row 12, 63 times after changing only its row to 13**. That is
a supplied-state availability proof, not an in-game percentage. Near-goal
requests differ, so “never in any situation” is too broad.

**Your exact check:** add formation 150/5-2 to X-43Cover2 from X-34Base. In
Experimental MASTER personnel choose **Make 5-2 an ordinary candidate (row 13)**.
Compare the defense preview against offensive personnel row 3 at midfield with
Undo/reapply. Build/restart and repeat that matchup, recording actual 5-2 calls
and its on-field lineup. Keep the MASTER edit separate from any executable
curve or pass-fetch experiment so the result identifies the change.

### 4. “TEs are still not on 3rd”

Beta 67 proved third down itself does not forbid TEs: in a neutral cold native
state, O-Shotgun uses Straight with a TE on 3rd-and-8/15, while the compared
O-Singleback3WR chooses Flush without one. Ordinary category/formation ratings
are the relevant book controls. Editing a MASTER role is shared by all books.

Beta 69 also fixed patch delivery: Studio copies its managed files into the
actual launch storage's `patches` folder and forwards `--apply_patches`.
The pass-fetch experiment affects only pass fetch subtypes 2/3/4, on any down.
It does not intercept a successful ordinary third-down selection, or generic
emergency subtype -1. Correct installation can therefore leave ordinary
third-down calls unchanged.

**PROVED offline:** native third-down tuples/TE role requests; authored role
writer and bounded eleven-player-builder work in beta 67; fake-process argv,
file placement, readback, enable/disable/removal tests in beta 69. Actual Xenia
module application, depth eligibility and rendered substitutions are still
UNWITNESSED.

**Your exact check:** compare 3rd-and-3, 3rd-and-8 and 3rd-and-15 at midfield
with O-Shotgun and the edited book carrying Straight/TE groups. Record formation,
category, called play and visible TE count. Compare rating changes through
preview and a fresh build. If testing pass-fetch separately, install the
matching BASE/TU file, restart via Studio, and check Xenia's **Storage root:**
and **Patcher: Applying patch for:** the intended TE-bias patch. The title count
only proves discovery. BASE selector hash is `5447E5428AA2D52A`; TU 1.1 is
`CEA825F7C2012F5A`. Retain rejection/hash logs if it does not apply.

## Validation and integration

Exact standalone commands, exit codes, counts and output tails are collected
in [the test receipt](reports/b70_apf1/tests/results.json). The focused replay
receipt is [here](reports/b70_apf1/book_identity_replay.json). Final test totals
and gate output are listed below. Reproduction commands are in
[the measurement recipe](reports/b70_apf1/REPRODUCE.md).

Protected packaging/registry implementation files are unchanged in this
worktree. [WIRING.md](WIRING.md) contains the exact existing capability-row
replacement, four allowlist paths and narrowly pinned editor-image checks for
both APF gates. **New capability rows: 0; shared/APF counts remain 172/72.**
The tests use a temporary release stage with precisely that wiring applied.
Its missing vendored extractors and their two accompanying text files are
copied from the read-only alpha.69 release under the hub. The binaries are
checked against the current exact pins; none of those four files is committed.
Reports, test fixtures and game data do not enter the public stage.

`packaging/repin.py --apply` is run after APF writer edits and last before each
explicit-path commit; it has reported **applied 0 pin update(s)**. The helper
mode remains 0755. No complete retail game folder or disc image was built;
the stock build proof uses tiny synthetic archives. Retail matrix/parity/native
inputs are read directly or decoded in memory. The existing mandatory
`test_apf_logo_patch.py` source-preservation test does create and delete one
temporary retail `0A` volume copy; its before/after source hashes agree. This
is an exception to the supplied no-large-root-scratch rule, not an assertion
that no retail bytes reached test scratch. The measured root free space was
134 GB after the suites, above the context's reported initial state. Temporary
test/staging files are removed when verification finishes.

### Final results

- **35 standalone suites, 343 cases: 342 passed, 1 skipped, 0 failures.**
  The single skip is the core suite's missing worktree extractors; both
  reviewed extractors are exercised by the staged release gate. All five
  stock-replacement tests pass, including the 64-case retail matrix and a
  copied synthetic build. The synthetic MASTER fixture is fully parseable;
  the production compiler retains its strict upstream MASTER validation.
- **22 native play-call research tests and 3 beta-69 retirement tests pass**,
  included in the totals above. They remain bounded offline executions.
  Offscreen UI, Undo/persistence, preview/build composition, source
  preservation, crest fit, package and cache regressions also pass.
- **Release gate: PASS**, 278 files, 10,260,794 bytes. **Runtime gate: PASS**,
  156 modules and 72 APF capabilities. [Exact commands and output](reports/b70_apf1/gates.json)
  record the temporary staging scope. A final comparison found 270 identical
  product files, precisely the four protected WIRING differences, and the
  four reviewed vendor files absent from this worktree. The guide and image
  files in that stage match the committed product files.
- [Synthetic parity](reports/b70_apf1/synthetic_parity.json) and
  [retail parity](reports/b70_apf1/retail_parity.json) pass with no skips.
  These establish byte preservation for the recorded fixtures and policies;
  actual Windows/macOS execution and gameplay remain **UNWITNESSED**.

Implementation checkpoint on `astra/b70-apf1`: `665b1cb6`. The final explicit-path commit includes
the preview integration, strict-fixture regression, this report, and all
measurement/test/gate receipts. No protected packaging or registry edits, user
context files, retail data or temporary release tree are included. The remaining
integration action is to apply **WIRING.md** in the owning packaging job; the
remaining gameplay action is to run the four DM checks above in Xenia.

The last `git add -- <explicit paths>` was blocked with **Read-only file system**
at `/home/noah/2k-football-mod-tools/.git/worktrees/astra-b70-apf1/index.lock`.
No approval or protected metadata write was attempted after that rejection.
The final commit is therefore delivered using separate writable Git metadata in
[the commit bundle](reports/b70_apf1-final.bundle), with an equivalent
[mail patch](reports/b70_apf1-final.patch). The checked-out branch remains at
the implementation checkpoint; the verified final files remain in the worktree.
The bundle's `astra/b70-apf1-final` ref descends directly from `665b1cb6`.
From a writable integration checkout at that checkpoint, fetch the bundle's
`astra/b70-apf1-final` ref and merge `FETCH_HEAD` with `--ff-only`, or apply the
mail patch with `git am`. Do not apply it over the same uncommitted changes.
