# PROVED OFFLINE: phase 5, native play-scoring release blocker

PROVED OFFLINE: The Dallas crash is an invalid handoff-hole operand, not book heap growth. PLAY 153, `17 Inside Zone`, encoded rush-lane **10** where native `0x2815F0` requires handoff hole **0..8**. Argument 3 mirrors that to -1, leading to the saved `0x281607` read of `0xE70C5F90`. The corrected operand is **3**, mirrored to **6**. Replaying the saved RAM with only the book replaced returns normally; the old book still reproduces the exact fault. All three comparison loads add zero heap. [Saved-state proof](receipts/phase5/fixed-snapshot.json), [original heap investigation](HEAP_REPORT.md).

PROVED OFFLINE: [SCORING_CONTRACT.md](SCORING_CONTRACT.md) documents the native readers, call sites, operands, semantic domains, flags and table bounds. Phase 1 confused the rush-lane enum with the handoff-hole enum; phases 2 through 4 reused that authoring path. Four-bit encoding, native loading and menu checks did not validate the scoring domain. The value 3 is a transform bitmask, not third down.

PROVED OFFLINE: The baseline found unsafe scoring inputs in **all 32 authored team books**, affecting **427 distinct plays** in the final composition. Counts below distinguish repeated compiler outputs from final books. The 64 packs produce 32 team resources, plus five retained utility resources.

| PROVED OFFLINE baseline scope | Resources | Play-record instances | Invalid calls | Distinct affected play instances |
| --- | ---: | ---: | ---: | ---: |
| Retail control | 37 | 9,251 | 0 | 0 |
| Each offense/defense compiler output | 64 | 16,920 | 3,004 | 854 |
| Final pack composition | 37 | 9,251 | 1,502 | 427 |

PROVED OFFLINE: [before.json](receipts/phase5/before.json) records every baseline failure, including mapped out-of-domain reads that need not fault immediately. Its matrix was narrower than the final matrix. The expanded final replay independently executes every retail and final resource and uses the native compiler execution for each of the 64 intermediate outputs. It records **zero faults or out-of-domain reads across 35,422 play-record instances**. [Independent final sweep](receipts/phase5/after-expanded-independent.json), [log](receipts/phase5/after-expanded-independent.log).

| PROVED OFFLINE native entry | Direct calls in expanded replay |
| --- | ---: |
| `0x2815F0` run scoring | 245,112 |
| `0x281620` pass scoring | 985,680 |
| `0x281580` defense game-plan filter | 283,376 |
| `0x208820` shared offense/defense scorer | 384,304 |
| `0x2B6F70` explicit handoff/fake operand decoding | 31,648 |
| Loader, validators, compatibility and category helpers | 1,624,742 |
| Total direct native entry calls | 3,554,862 |

PROVED OFFLINE: The matrix covers all four native transform values, all compatible formations, run/pass game-plan equivalence states 0/1/9, all eight defensive plan states, all receiver-role branches and both shared-profile branches. It executes native trajectory and matchup readers, including `0x204F10` and `0x205660`. It supplies roster resolution and rating values. The table guards run before the actual loads and reject mapped neighboring reads as well as access violations.

PROVED OFFLINE: All 32 offense packs were regenerated. A recursive comparison with `a7ebef06e` finds exactly **1,426 changed handoff/fake operands**; routes, blocking, names, menus, flags and intent records are unchanged. All 32 defenses only change their source fingerprints. [Intent preservation](receipts/phase5/intent-preservation.json). DESIGN: Handoff aims use the nearest native hole to each existing football target, including left/right end-arounds and centered play-action fakes.

PROVED OFFLINE: The encoder refuses handoff holes outside 0..8 before packing. The library and drawn-run authoring convert geometry to this enum; the editor labels it correctly. `apply_pack_to_resource` runs the native check on every compiled output. `mod_build._check_playbook_scoring` runs on every final disc at publication, after archive rewrites and paired owner updates. Both fail closed. The CLI and editor supply their source executable; standalone callers can supply `xbe=` or `NFL2K5_SCORING_XBE`. Release packaging includes the scorer and pins; Unicorn is already a pinned runtime dependency.

PROVED OFFLINE: The corruption regression inserts the original bad value into compiled bytes. Retail's validator accepts those bytes, while both publication gates reject them. The tests also exhaust the encoded handoff nibble with all transforms, verify missing-executable and changed-code refusal, and prevent mutation of a returned receipt from forging a later cached result. The build-order test verifies that the final gate sees a rewritten archive. [Native regression](receipts/phase5/scoring-tests-final.txt), [publication order](receipts/phase5/publication-order-tests.txt).

DESIGN: Whole-game world states are not a finite four-value argument. The outer-selector experiment additionally exercises factored down/distance/field and score/quarter/clock states with native policy and selectors. Its explicit fixtures and results are separate from the exhaustive PLAY-index proof. Initial retail-control failures identified uninitialized saved-formation inputs and non-play-call phases in that fixture; those are not attributed to authored books. No xemu or live gameplay claim is made.

PROVED OFFLINE: Completed test results follow. The owner suite's one deselected case is the separate cross-team run immediately below it; it was not omitted. The two skipped composition tests are generic opt-in disc builds; the requested full final-draft build is separate.

| PROVED OFFLINE suite | Result |
| --- | --- |
| [Scoring and rejection gates](receipts/phase5/scoring-tests-final.txt) | 8 passed; 82 subtests |
| [Team books and defense pipeline](receipts/phase5/book-tests-final.txt) | 36 passed; 5,685 subtests |
| [Owner regression](receipts/phase5/owner-tests-final.txt) | 129 passed; 1 separately run; 1,692 subtests |
| [Every supported pack/target menu](receipts/phase5/cross-team-native-tests.txt) | 1 passed; 5,744 subtests |
| [Build integration](receipts/phase5/build-tests-final.txt) | 32 passed; 33 subtests |
| [Final publication order](receipts/phase5/publication-order-tests.txt) | 20 passed; 7 subtests |
| [Composition, intents and pack UI](receipts/phase5/composition-ui-tests-final.txt) | 42 passed; 2 opt-in skips; 60 subtests |
| [Authoring UI and writer](receipts/phase5/authoring-ui-tests.txt) | 14 passed |
| [CLI with extracted source and no environment override](receipts/phase5/cli-check.txt) | GREEN |

PROVED OFFLINE: Initial build-fixture failures were caused by synthetic test images containing no PLAY archive. Those owner-specific fixtures now model the gate separately; real retail corruption tests still execute it. The first serial cross-team regression was interrupted and replaced by the complete parallel run. Native gate execution was retained.

PROVED OFFLINE: The completed outer-selector experiment executes **54,096 world states** across 37 retail and 32 authored variants, plus **33,282 direct offensive-selector calls** across formations, families and both situational inputs. All authored variants have **zero faults**. Native execution reaches `0x20B820` / `0x20B400` 54,096 times and the shared scorer 1,288,278 times. [Validated selector summary](receipts/phase5/selectors-summary.json), [per-book receipts](receipts/phase5/selectors).

PROVED OFFLINE: Retail PRACTICE produces **51 null-formation faults** at `0x2045F0` in forced full-match fourth-down/kick fixtures. This utility book has no special-teams formations. These control faults are retained, not counted as passes; all other retail variants are clean, and all 37 retail resources pass the separate per-play scoring sweep. The aggregator verifies every resource hash against the independent matrix and rejects any authored or other unexpected fault. The world fixture contains 784 explicitly recorded states per variant; it is factored coverage, not an exhaustive Cartesian game simulation.

PROVED OFFLINE: The **full final-draft build completed**, producing a **7,475,951,616-byte** disc under the authorized Storage directory. The builder reports **93 applied settings, zero not-applied settings and zero skipped pending options**, with 4,702 seconds in its build receipt. Both sets of 32 playbook packs, QB Spy and screen D report applied. The completed-disc reader verifies **6,628 play names and 1,670 handoff/fake operands** against all 64 source packs, including the 1,426 corrected operands. [Full-build receipt](receipts/phase5/full-build.json), [production log](receipts/phase5/full-build.log), [complete inspection](receipts/phase5/full-summary.json).

PROVED OFFLINE: The summary retains two expected foreign-inspection results: depth roles on custom books and the static scorebar inspector on the sprite HUD. Eight child settings have no separate inspection row. These are recorded individually, not silently recast as applied. The only recipe changes are `playbook_packs`, `playbook_pair` and `read_option_runtime`; the production recipe is unchanged.

PROVED OFFLINE: The expanded native gate independently reopens the finished disc and passes **all 37 final books with zero faults across 906,398 direct native calls**, using patched executable SHA-256 `759539440bce073d03d2bdcb7040aca6e54c10512f793fd03c3a9214d1d55750`. The build began with the initial gate; this completion replay uses the final expanded gate after all writers. All 64 pack input hashes are unchanged since launch. The [final source manifest](receipts/phase5/final-source-inputs.json) and full-build receipt identify the exact gate sources. The previous build remains available as [phase 4 history](PB_REPORT_PHASE4.md), not phase 5 proof.

PROVED OFFLINE: The full-build driver exited **0** and deleted the disposable disc. No disc or executable payload remains in this build's session directory. The source recipe hash is unchanged. The minimum recorded NVMe free space is **112,035,262,464 bytes**, above both 100 GB and 100 GiB. [Cleanup and disk proof](receipts/phase5/disc-cleanup.json).

DESIGN: Delivery uses a pathspec commit with the Astra co-author in private git metadata at `.scratch/pb.git`, because the shared git metadata is read-only. The bundle is `.scratch/pb-phase5.bundle`; `.scratch/pb-phase5-delivery.json` records its verification, prerequisite commit, final commit and SHA-256. No push, tags, other worktrees or xemu are used. This release proof is offline; live gameplay is not claimed.

DESIGN: Reproduce the native matrix with `python3 pb/scoring_sweep.py --image <retail.iso> --xbe <default.xbe> --output <receipt.json>`. Reproduce the production build with `bash pb/recipes/full_build.sh`; it composes the actual final-draft recipe, retains only the authorized three playbook overrides, writes its disposable disc under `/media/noah/Storage/.b76-research/pb/astra-build/`, verifies the finished disc and deletes it on exit. The source recipe is not edited.

DESIGN: Reproduce the additional selector experiment with `python3 pb/scoring_selectors.py --image <retail.iso> --xbe <default.xbe> --compiled <compiled-directory> --team <TEAM> --output <TEAM.json>` for each key in `BOOK_ENTRIES`. The compiled directory contains `<TEAM>.bin` for each of the 32 final team compositions. It can be regenerated from `pb.phase4.compile_books()`, saving each returned final `replacement`; these game resources are deliberately excluded from the bundle. `pb/collect_scoring_selectors.py` checks the 37 receipt files and their resource hashes against the independent sweep. The [evidence index](receipts/phase5/README.md) distinguishes final results from retained development experiments.
