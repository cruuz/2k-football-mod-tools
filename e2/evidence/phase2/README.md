# Phase 2 evidence

**PROVED OFFLINE:** These files report source, archive and native x86 checks. They are not xemu witnesses. Build outputs and private game resources stay in `/media/noah/Storage/.b76-research/e2/astra-build/`.

| Evidence | PROVED OFFLINE result |
| --- | --- |
| `recipe.json` | Only four option overrides differ from candidate B; records recipe, driver and frozen input hashes. |
| `build-source-provenance.json`, `build-code-hashes.json` | All 370 frozen code/data files match private implementation commit `4ef666dde`; explains the shared base HEAD in the builder receipt. |
| `run-command.txt`, `cache-cleanup.json` | Records the full-build invocation, initial free space and cleanup of the completed project source cache. |
| `rules-coverage.json` | All 50 installed rule rows preserve every value from the phase 1 map; 14 modeled fields and three explicitly unimplemented fields. |
| `allocation-proof.json` | Complete live owner union fits the shared allocator. |
| `runtime-owners.json` | Composed candidate-B executable inspection and later art routing fields. Final-disc inspection supersedes this intermediate executable. |
| `full-build-tail.log` | FULL build completed with 96 applied options, zero unapplied options, and 69 native PLAY scoring checks without faults. |
| `full-disc-proof.json`, `full-disc.log` | Independent finished-disc hashes, 4,451 directory entries, complete stock bank, 50 moments, named text, era rules and original roster readback. |
| `stock-native-proof.json`, `full-native.log` | Final-disc native suite: 17 tests passed, covering all 75 historic descriptors, all 100 moment sides, 32 current franchises, mixed sides, release and re-entry. |
| `postbuild-reader-fix.json` | AST comparison limits post-build production changes to the original-roster and screen-timing readers, plus their provider hashes. Built-disc bytes did not change. |
| `fresh-inspection.json`, `final-inspection.log` | Fresh final-reader inspection reports all 96 selected options applied and zero unapplied; active owners cover the two existing legacy-reader exceptions. |
| `final-reader-regression.log` | 43 tests and 219 subtests passed, with two optional input checks skipped. |
| `final-scope-regression.log` | 27 tests and 165 subtests passed, including the complete stock-bank screen scope and corruption refusal. |
| `finished-validation.json` | Final build, native, independent disc, reader and scope checks all exited successfully. |
| `disc-cleanup.json` | Finished disc and temporary executable probes deleted; NVMe remained above 100 GB. |
| `build-provider-tests.log` | 21 tests and nine subtests passed. |
| `profiles-provider-tests.log` | 46 tests and 432 subtests passed. |
| `profile-style-tests.log` | 12 tests and nine subtests passed after the original roster inspector learned the exact historic spare-style transform. |
| `era-final-regression.log` | 79 tests and nine subtests passed after correcting recognition of compressed allocator owner names. |
| `roster-regression.log` | 22 tests and 77 subtests passed; one private historical-source check skipped because its external input is absent. |
| `native-crc-test.log` | Native current-book, reversed mixed-side and filename CRC check passed. The final-disc native run supersedes this intermediate run. |
| `allocator-corrections.log` | 26 tests and 138 subtests passed. One test failed because its old 1,024-byte synthetic read-only payload exceeded the newly sized 512-byte test allocation. |
| `allocator-seals.log` | That exact failed test passed after using the declared allocation size. Its integrity and changed-request refusal assertions remain. |

**PROVED OFFLINE:** Earlier capacity failures came from stale test-only reservations for the nonexistent `nfl2k5_guardian_cap_overlay`. The fixture now equals the production dormant-owner union, retains the real guardian overlay, and passes the two original request-union assertions. No production owner was removed to make room. The allocator run above includes those repaired assertions.

**PROVED OFFLINE:** The first final-disc native run had two fixture failures because it sliced the SITU resource at the old 25-row length. Reading the wrapper's declared span fixed both; the complete 17-test suite then passed. Independent inspection also found the two fixed-layout reader assumptions documented in `postbuild-reader-fix.json`. The corrected readers recognize the existing finished disc without rewriting it.

**PROVED OFFLINE:** The final reader regression's two skips are the absent user-supplied nflverse historical CSV input and an unset optional legacy e1 disc variable. The actual full image built for this job passed the separate final-disc native suite. The full build receipt and log, recipe copy and delivery bundle remain in the build folder; the disc and private source cache have been removed.

**PROVED OFFLINE:** `era-tests.log` and `rules-provider-tests.log` retain earlier passing focused results. `era-final-regression.log` is the later result for the final recognizer code. Test counts across these logs overlap and must not be added as a count of unique tests.
