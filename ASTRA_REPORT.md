# Beta 69 J9: APF schemes, formation admission and patch delivery

Implemented eight reviewed team schemes and situational CSV, a reversible
ordinary-formation Never call control, the actual `5-2:Big` row-13 UI fix, and
managed-patch delivery into Xenia's actual launch storage. The existing Add
Formation and clone route already admit added Jacks/Jokers in the bounded
native goal-line caller. That requested negative comparison is contradicted
by the reproduced counterexample, not presented as a newly fixed game bug.

**Every in-game outcome is UNWITNESSED.** No emulator, displayed GUI, audio or
network was used. Football scheme descriptions and numeric preferences are
interpretations from general knowledge, not literature quotations or online
research. Schemes and Never call are ADVANCED, opt-in; shared MASTER changes
and executable patches remain EXPERIMENTAL. No preset enables a patch.

## Scope and delivered behavior

Read ASTRA_CONTEXT, triage row 21, all four beta-67 worktree reports, the two
playcall research models, and the hub's beta-67 design/API contract, both
September 11 beta-66.1 APF reports and Urianus' September 11 DM dump. Urianus'
quoted reports predate beta 67; he had not reacted to beta 67 as of the supplied
September 13 15:12 cutoff. This work does not portray those DMs as beta-67
feedback.

7ET asked for an “Offensive Scheme Install Package” and to “create a play call
spreadsheet.” CPU Play Calling now offers Air Coryell, Erhardt-Perkins, West
Coast, West Coast Spread, Spread-to-Run, Wide Zone, Power/Gap and Pro Spread.
Each is data: eleven intended run shares, eleven run and eleven pass weight
deltas, personnel preferences, category deltas and three formation deltas.
The available personnel comes from the selected book's actual MASTER roles.
Missing groups are reported; schemes do not manufacture formations or plays.

The team review includes a private-book plan when the original is shared,
before/after formation ratings and row weights, and missing preferred groups.
One staged receipt owns the clone and scheme together. Preview runs against
that staged book; Undo, Save Project/reopen and copied Build use the existing
recipe verifier. Team tendencies follow the team's actual ROST pointer;
aliased tendency records are refused. Reapplying adds the deltas again.

The CSV exports the current staged offense, including subsequent manual edits,
with all 23 requested buckets, actual candidate probabilities, representative
inputs/engine rows and explicit model limits. Last-applied scheme and coaching
intent are separate from stored and modeled run shares. Requested pick counts
are planning annotations, not a scripted opening series. Both the Qt button and
`playcalling_service --spreadsheet-team 0..23` use the same facade. Formula-like
names are escaped; the file uses UTF-8 BOM and csv.writer quoting.

The short guide and exact bucket-to-row table are in
`docs/mod_editor/apf_b69_schemes.md`. Data/code are
`mod_editor/core/apf2k8_offensive_schemes.py` and
`mod_editor/core/apf2k8_formation_calling.py`. Team editor integration is in
`mod_editor/apf_studio/{playcalling_service,playcalling_editor_qt,playcalling_build,facade}.py`;
launch delivery is in `launcher.py`.

## Evidence grades and native boundary

PROVED below means a pinned byte read, reproducible offline writer/readback,
or explicitly bounded native execution. It never means a played game. Native
checks use the owned USA BASE flat image SHA-256
`cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`.
The test refuses an unpinned image. Retail bytes remain private.

The beta-67 Unicorn PPC32 instrument supplies missing Xenon ABI/instruction
semantics, RNG fraction/integer inputs and the kicker-range boundary. It does
not substitute category, formation or play selection results. MASTER's native
initializer runs first. Match state is explicit, with empty history and null
player objects. The tuple sweep captures native candidate vectors and invokes
the native roulette at 84863388; it is not 10,240 complete match-engine calls.
A separate complete driver runs once per sweep state. The Hail Mary proof
executes the constructor cache block and a branch after its predicate; the
predicate and lifecycle inputs are deliberately supplied.

All new native results are BASE only. The inherited beta-67 BASE/TU mapping and
patch image proofs are cited, not relabeled as a new J9 TU execution matrix.
The hook-based profile selector discussed in P1 section 6 remains HYPOTHESIS;
J9 does not install that unproved replacement or promise independent situation
policies through it.

## What the book and executable actually control

| Evidence | Address / field | Finding |
|---|---|---|
| PROVED structure and native use | SPLB +70+i*B0, trailer +A8/+AC | A high byte is formation ID; bits 23..17 primary category; 3-bit ratings at shifts 14, 11, 8. B is category membership. |
| PROVED native normalization | BASE 84A8C790; inherited TU 84A8D760 | Rebuilds book caches. B=0 on an ordinary populated record survives two passes without compaction. |
| PROVED native row | 84867600; curve 820C8884 | Ordinary offense requests rows 0..10. First-and-one at the one requests row 0 at supplied neutral jitter. |
| PROVED native category lottery | 8486AEB0; distance curve 820C88A8, rating curve 820C891C | Uses advertised categories and the book's formation ratings, not a per-label hard-coded goal-line whitelist. |
| PROVED native membership | 848693F8 → 848695A0 → 84A8A330 | Formation enumeration tests B membership. Ratings affect positive weights; they do not implement a zero-weight switch. |
| PROVED native rating | 84869058; curve 820C88F0 | Both rating 0 and rating 7 have positive weight in the tested state. Lower valid ratings generally favor a formation. |
| PROVED data location | 84A89B40, specifically 84A89BB4..84A89BC0 | Book +7E0C points to MASTER; category records are MASTER+44+id*16. Eleven role bytes live there. |
| PROVED row read | 84A8B438, especially 84A8B45C..84A8B464 | Reads the category's +4 low-six-bit personnel row from MASTER. |
| PROVED XEX bytes | 820B9080 | The six independent lineup fallback offsets are +1, -1, +2, -2, +3, -3. They are not an XEX-resident per-book personnel table. |
| PROVED inherited tendency path | ROST team +F8 → record +5A, +8E/+99 | Overall run percentage and two eleven-byte optional row arrays. 8492A440 expands the latter; 84929B4C..84929E44 reads that optional cache. |

The request describes an “XEX-resident personnel-group table.” The actual
category/role records are MASTER-resident. XEX has selector curves and the
separate six-offset lineup search. This distinction matters: editing a clone
cannot create a private MASTER personnel row, and retiring a row used by the
lineup search can strand another caller.

Category and formation ratings are coupled: no independent stored category
rating exists. A scheme changes each existing formation's three ratings;
category preference changes their mean. The first two preferred groups get -1,
other listed groups 0, unlisted groups +1, combined with the scheme's three
deltas and clamped to 1..7. Plays, audibles and membership are preserved.

The eleven run percentages are **intent, not eleven independent CPU sliders**.
The 22 row bytes are real writable fields, but their optional cached category/
formation is not consumed by the traced ordinary CE88 picker. The preview uses
the overall team share and beta-67 adjustment plus the actual book lotteries.
The short doc and CSV state this rather than inventing an ordinary row override.

Openers and sudden change share the normal down/distance row. Four red-zone
bands all use row 4 in the exported first-and-10 representatives. Clock/history
can affect other paths, but there is no distinct cold-preview opener, turnover,
negative-play or four-minute row. The 2pt bucket is a scrimmage proxy; real try
phase can request row 19 or substitute down 4. Fourth-down punt/FG and urgency
paths are outside this preview. The doc lists every representative 0..10 row.

Tempo, snap count, weather run/pass ratio and coin toss: **no authoring lever
proved in the inspected book/selector surface**. The sparse read-only audit
covers the row, adjustment, category and lineup functions and records their
hashes. UTF-16BE Weather strings occur at 84604EF8, 84604F08, 84604F44 and
846116CC; Coin Toss at 84615C80; Huddle has 16 hits. Exact “Tempo” and “Snap
Count” have none. Text is not a policy field, and absence of those strings is
not absence of executable logic. No XEX-wide impossibility claim is made.
`tools/apf_b69_playcalling_audit.py` reproduces
`docs/research/apf_b69_control_audit.json`; finding actual policy callers
requires further reference/dataflow research. No such control ships invented.

## Urianus: added heavy sets

“Adding \"heavy\" run formations, like Jacks (2 RBs, 3 TEs) or Jokers (2 RBs,
2 TEs, 1 WR), to O-Singleback3WR ... doesn't trigger them in run situations,
like on GL ... instead reverting to Ace forms as usual.”

PROVED counterexample: native O-Shotgun (outer 1411), O-Singleback3WR (767)
with added Jacks formation 9/category 0 and Jokers formation 5/category 1
carrying the donor's play entries, and
a beta-67 clone named `J9 Heavy` all admit and select those heavy records in
the same goal-line harness. At RNG fractions .01 and .5 the category and full
8486CE88 driver return heavy formations; emergency fetch 848699D8 is not
visited. A separate pure-run test also returns valid run-flagged plays from both
Jacks and Jokers in native O-Shotgun, the added book and `J9 Heavy Run`.
Native donor goal-line category weights start at .9100000858 for
both categories. Added/clone weights are 1.0 for each, versus Ace category 2
at 1.1628571749, Kings 5 at .5642856956 and Flush 8 at .0482692309.

The existing Add Formation path compiles `MembershipChange` and
`TrailerReplace`; it already writes the donor-equivalent primary category
and B mask (1 for Jacks, 2 for Jokers). Clone preserves both. Native donor
ratings are 2/4/4 while an added record starts 2/2/2, explaining different
weights without an admission failure. The new regression compares native
normalized trailers and actual native calls; no redundant membership rewrite
was introduced. A saved malformed/old added record can still need manual
personnel correction in Play Calling, and rating equality is an explicit edit.

HYPOTHESIS for his particular game: the loaded working/saved USER book differs
from the edited disc book; an older added record lacks these masks or compatible run plays; global
merges, live history, lineup caches or a distinct run/special branch differ
from this supplied state. His exact saved book and live call have not been
observed. No claimed reproduction or universal guarantee.

## Urianus: 5-2 never selected

“Adding D forms, like 3-4 to a 4-3 PB, works as normal ... Except 5-2, which
is never selected if added.”

PROVED: defense request logic at 84869B60, called through offense-personnel
resolution 8486CAD0, does not issue ordinary request 12 in the mapped cases.
At 8486B1C4, below-request candidates receive zero (curve 820C88D4).
`5-2:Big`, MASTER category 27, is stock row 12. The beta-67 button searched
only the literal names `5-2`/`52`, so it missed the actual name. The editor now
accepts its `:Big` suffix and reports a missing category plainly if absent.
It exposes the shared row change and existing preview/Undo.

PROVED native driver 8486D0F8..8486D38C: add formation 150/category 27 to
X-43Cover2 (134), using X-34Base (618) donor plays. Offensive category 3 has
row 3; at midfield it requests defensive row 13. With 128 explicit synthetic
seed states, category 27 on row 12 yields formation 141 128 times, 5-2 zero.
Moving only the shared MASTER row to 13 yields formation 141 65 times and
formation 150 **63 times**. This proves availability under the matching
request, not an exact in-game percentage. MASTER affects every book/clone.

## Urianus: removing stock formations

“The main limitation now, besides playcalling, is REMOVING formations because
those PBs aren't blank obviously, so the CPU is going to use those stock ones
no matter what we add on top”.

PROVED ordinary path: `Never call (ordinary CPU lottery)` sets only record
trailer B to zero on every duplicate of the selected formation. A, ratings,
plays, ordering and book size remain. Original masks live in the authored
project recipe; uncheck restores them exactly, and Undo restores the compound
operation. Another surviving member must cover every affected category;
otherwise the operation refuses with a next step. This preserves supply for
the independent lineup ladder rather than globally retiring a category.

The beta-66.1 retirement proof concerned a separate personnel row search and
its trailing supply; it did not prove ordinary and special selectors share
one zero-weight control. B=0 here leaves that category covered by another
formation. Rating 0 and maximum 7 both retain positive weight and are not used
as a Never call mechanism.

PROVED final sweep: **0 selections of retired formation 68 in 10,240 tuples**,
with 40 additional complete ordinary drivers also excluding it. Selected play
flags counted 10,040 run and 200 pass among the supplied correlated quantiles;
these counts are not calibrated game run/pass rates. The full native suite
passed all five tests in 887.524 seconds.

The 40 explicit states use downs 1..4, eight distances (1,2,3,5,8,10,15,20)
and five goal distances (1,3,20,50,97), correlated exactly as the test lists;
this is not their full Cartesian product. The final sweep uses run share .5,
256 supplied quantiles per state and native category/formation/play vectors.
Record 68 in O-Singleback3WR is the retired ordinary test case. Two native
normalizations preserve B=0 and stability without compaction; restoration
before normalization is byte-exact. Additional native checks cover 24 complete
drivers at pure-run/pure-pass boundaries. On defense, stock X-43Cover2 has
one formation per category, so retirement correctly refuses until replacement
supply exists. Adding same-category formation 144 first permits retiring stock
141; normalization preserves the exclusion and 128 matching native defensive
requests never return 141. The additional whole-file suite passed three tests
in 83.824 seconds. Synthetic tests also cover all duplicate records and
uncovered-category refusal.

PROVED limit, special formation 151: even B=0 and ratings 7 do not retire the
cached Hail Mary branch. Native constructor block 84864E90..84864EBC caches
the supplied Hail Mary formation/play in D+58/+5C using primary-category
resolution. Native post-predicate block 8486BE14..8486BE48 then returns the
valid cached formation/play via H+684/+680. The predicate itself is supplied,
not witnessed. A preliminary assertion that B=0 Punt 155 would survive the
supplied-play BC08 resolver failed: that path returned null. The corrected
Hail Mary test establishes a specific real bypass; it does not generalize the
failed Punt assumption. Final tests use the corrected boundary.

Special IDs 151..162 therefore stay protected. A universal special retirement
requires proving constructor/load caches, global merge repair and the live
special-call lifecycle, as P1 section 6 already identified. Saved USER books,
global merges, manual calls and the independent lineup selection remain
outside this ordinary-CPU exclusion promise. The UI uses that exact scope.

## Urianus: TEs on third down and Xenia patch destination

“Same exact issue. And the patch doesn't work either afaict. I still don't
understand what it's trying to do (pass \"fetch\"?), but the bottom line is
TEs are still not on 3rd”.

The 66.1 export derives the pinned image in memory from `default.xex` and
optional installed TU 1.1, then writes **authored Xenia TOML only** to the
selected output (historically beside the copied game). It does not change
default.xex or install an emulator patch. The inherited payload hooks BASE
84869B20 / TU 8486A820 and uses cave 84D0E000: 716 bytes, 179 instructions.
It prefers TE-compatible records only for pass fetch subtypes 2/3/4, on any
down, with zero-match fallback. BASE selector hash is `5447E5428AA2D52A`, TU
1.1 `CEA825F7C2012F5A`. The generic emergency fetch and successful ordinary
CPU calls are separate; third down itself does not forbid TE personnel.

Beta 67 added reviewed installation of the canonical file
`<Xenia executable directory>/patches/54540807-studio-pass-fetch.patch.toml`
and set `[Memory].apply_patches=true` in the selected launch config. It
verified that installation but the Studio launcher passes a **different
per-build `--storage_root`**. That was still the wrong discovery folder.

PROVED local source trace (no network or emulator execution):
`/home/noah/.codex-tmp/xenia-slot43-build/src/xenia/emulator.cc:306` constructs
Patcher(storage_root_); `patcher/patch_db.cc:35` reads `<storage_root>/patches`;
`patch_db.h` accepts `^[A-Fa-f0-9]{8}.*\.patch\.toml$`. `patch_db.cc:17`
registers `apply_patches` under **General**, and `config.cc:116` resolves
category-qualified keys. Thus the old Memory setting alone does not activate
this source version. A log's loaded patch/title count alone is not a witness
that this specific patch matched and applied.

J9 fixes both launch boundaries. Before starting the process, Studio copies
only its two canonical managed files (pass-fetch and personnel-curves) from
the reviewed install folder into the exact launch storage's `patches`,
validates and reads them back, and refuses foreign/symlink managed paths.
Removing an installation removes its old copy on that build's next Studio
launch; unrelated files remain. The reviewed Memory bool is explicitly
forwarded as `--apply_patches=true` or `false`, so a General-registered build
honors the Studio setting. Launch status names the actual patches folder.
Fake-process tests inspect the real argv-selected directory, both file
payloads, enable/disable, removal propagation and foreign-file refusal. No
change to hook payload or unsupported claim of live Xenia consumption.

## Witness steps for 7ET and Urianus

Use a copied build, keep the original project, and record BASE/TU, source book,
team, saved USER slot/override and any global merge. Start a fresh session after
book changes so the observation identifies the loaded content.

**7ET schemes and spreadsheet**

1. Open CPU Play Calling, select a team sharing an offensive book and choose
   one of eight Scheme entries. Review its named private copy and before/after
   values; missing personnel must be visible. Stage once.
2. Preview first-and-10, second-and-5, third-and-8 and first-and-goal at the one.
   Compare actual candidate distributions with the original via Undo/reapply.
   Treat the row run shares as intent and the optional weights as labeled.
3. Export play call spreadsheet. Verify all 23 bucket names, planning counts,
   candidate names/probabilities, representative rows and shared-bucket notes.
   Make a manual rating edit and export again; the CSV must reflect that edit.
4. Save/reopen the project; build a new folder. Confirm the selected team's
   named copy and other teams' original assignments. Observe CPU calls across
   matching situations and record personnel/play names, rather than assuming
   the literature scheme label installs its blocking/routes. Undo restores all
   scheme changes including the copy assignment.

**Urianus heavy sets**

1. Add Jacks (9) and Jokers (5) to O-Singleback3WR via Add Formation, including
   compatible run and pass plays from O-Shotgun. Inspect
   primary categories 0/1 and membership bits 0/1. Compare O-Shotgun natively.
   Match ratings 2/4/4 manually if testing exact donor weights.
2. Test both the original edited label and a newly named private clone assigned
   to a team. Record which book/save slot is actually active. Preview first-and-
   one at the one and record the nonzero heavy candidate weights.
3. Repeat actual CPU goal-line run opportunities against an O-Shotgun control.
   Log formations and play types. If added heavy sets still never appear, keep
   that project/save and exact game context; it differs from the proved cold
   native input and is evidence for the remaining lifecycle investigation.

**Urianus 5-2**

1. Add 5-2 to the chosen defensive book. In Experimental MASTER personnel choose
   “Make 5-2 an ordinary candidate (row 13)”, inspect `5-2:Big`, review and stage.
2. Preview against offensive personnel row 3 at midfield, then compare row 12
   via Undo. Row 13 must list/select 5-2 in a nonzero share of model draws.
3. Build and play the same matchup. Count CPU 5-2 calls and retain the offensive
   personnel. This shared MASTER change affects all books, not only this team.

**Urianus Never call**

1. Choose an ordinary stock formation with another live formation covering each
   of its categories. Review “Never call (ordinary CPU lottery)” and stage.
   It must refuse the final member of a category and specials 151..162.
2. Inspect preview distributions, Save/reopen and Build. Record remains in the
   book for explicit user calls; ordinary CPU membership is zero.
3. Observe repeated matching CPU situations, with saved USER overrides and
   global merges recorded. Uncheck to restore original memberships; compare
   against the same control. A special Hail Mary is not covered by this toggle.

**Urianus TE/pass-fetch install, beta 67+**

1. Determine whether the build is BASE or TU 1.1. Export/prepare the matching
   pass-fetch file from the owned game folder (TU content when applicable).
   Inspect title ID `54540807`, the corresponding hash above and enabled=true.
2. In beta 69 use CPU Play Calling's experimental pass-fetch install control,
   review the configured Xenia folder/config, enable the reviewed patch setting,
   then fully close Xenia and **Launch through the Studio**. Each build has its
   own storage root; launching some other shortcut may use a different one.
3. For an unupdated beta-67/66.1 installation or an external launch, read
   Xenia's `Storage root:` line and place the canonical file in exactly
   `<that root>/patches/54540807-studio-pass-fetch.patch.toml`. A file beside
   default.xex or beside Xenia is insufficient when storage_root differs.
   Start with `--apply_patches=true`, or use `[General] apply_patches = true`
   for the inspected Xenia source version. A beta-67 Memory-only setting is
   insufficient there. Do not add duplicate copies of the same hook.
4. After restart check `Storage root:` and **`Patcher: Applying patch for:`**
   for this title and the TE-bias patch, and investigate any hash/parse/filename
   rejection. PatchDB's title count is only discovery. With beta 69, verify the
   file in the folder also named by Studio's launch status.
5. Compare third-and-3/8/15 with a book carrying TE groups (for example Straight),
   and use Play Calling ratings/personnel to inspect the ordinary CPU lottery.
   Record category/formation, TE count and called play. A correctly applied
   subtype-fetch experiment can still leave ordinary third-down calls unchanged;
   it is not a forced-TE third-down selector. Logs prove delivery/application,
   while on-field calls provide the separate gameplay witness.

## Verification and integration

Final standalone test commands/results are recorded in
`reports/apf_b69_test_receipt.json`. All Qt runs use
`QT_QPA_PLATFORM=offscreen`, with `PYTHONPATH=.`. New suites cover real core
scheme writers, actual model distributions, reviewed cloning, Save/reopen,
Undo, real synthetic-archive copied builds, reversible duplicate masks,
actual 5-2 category names, and fake-process patch argv/storage. Backend loading
is injected for synthetic source fixtures; core writer modules are real.
The native matrix loads owned retail inputs separately, never checked-in game
fixtures. Optional retail absence is a precise SkipTest.

**25 standalone suites: 201 test cases, 200 passed, 1 skipped.** The existing
Studio core skipped its vendored extract-xiso pin check because the gitignored
release-build binaries are absent in this source tree. No native J9 test skipped. The 16
regression suites contribute 173 cases; nine J9 suites contribute 28.

| New standalone suite (run as `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/<name>.py`) | Result | Seconds |
|---|---|---:|
| `test_apf_b69_schemes` | 5 passed | 42.730 |
| `test_apf_b69_build` | 1 passed | 35.722 |
| `test_apf_b69_editor_qt` | 4 passed | 109.904 |
| `test_apf_b69_formation_calling` | 2 passed | 0.152 |
| `test_apf_b69_launch_patches` | 5 passed | 0.295 |
| `test_apf_b69_wiring` | 2 passed | 0.101 |
| `test_apf_b69_control_audit` | 1 passed | 0.337 |
| `test_apf_b69_native` | 5 passed | 887.524 |
| `test_apf_b69_retirement_native` | 3 passed | 83.824 |

The full command, output tail and new test-source hashes are in the receipt.
The prior Punt bypass assumption and temporary test-fixture mistakes are
recorded there; the results above are the final whole-file runs.

Exact native/audit reproduction commands (point the variables to owned inputs):

```sh
APF_RETAIL_INDEX='<owned game>/0A' APF_RETAIL_PE='<owned pinned BASE flat PE>' PYTHONPATH=. python3 tests/mod_editor/test_apf_b69_native.py
APF_RETAIL_PE='<owned pinned BASE flat PE>' PYTHONPATH=. python3 tests/mod_editor/test_apf_b69_control_audit.py
python3 tools/apf_b69_playcalling_audit.py --image '<owned pinned BASE flat PE>' --report '<new receipt.json>'
```

On this machine the index was the existing
`/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A` and
the existing flat image `/tmp/astra-coverage-17votk5s/base_reextracted.pe`.
No new disc/image copies were made. Root free space was already 78 GiB, below
the requested 80 GiB floor, so work used small authored scratch files only.
`tools/apf_h7a_optimal` remains executable mode 0755.

`WIRING.md` contains three complete registry rows, exact simultaneous product
bindings, two existing-row description corrections, APF allowlist/import
additions and all count pins. J9 adds 3: shared 161→164 and APF 69→72 before
other jobs. Protected files are unchanged. The proposed cards/bindings are
tested on a temporary registry. Full baseline registry validation stops at
`capabilities[0].evidence[0]`: missing `docs/research/apf_audio.md`; the
unchanged 161-row schema passes with `--skip-file-checks`, and every new J9
reference is checked. This existing evidence-path failure needs hub repair; final integrated packaging/release gates are
Claude's pending protected merge, not claimed completed here.

Git's worktree metadata lies outside the writable roots and rejected `git add`
with permission denied. Commits use isolated `/tmp` metadata on the requested
branch and base, with explicit file paths; original metadata is unchanged.
Import `ASTRA_B69_J9.bundle` into the hub to obtain those commits. The first
implementation commit is `ab07a4e7`. The final proof commit is the branch tip
listed by `git bundle list-heads ASTRA_B69_J9.bundle`; it includes this report
and the test receipt.
Repin runs immediately before each commit (`applied 0 pin update(s)`).
The final bundle is verified against the existing base prerequisite. No network, push, live emulator or release publish.
