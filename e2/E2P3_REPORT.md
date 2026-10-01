# E2P3 delivery, 2026-09-28

**PROVED OFFLINE:** Base `e7d7aca56aff8be72cef354c7dcb2f59b71be71a`, candidate E integration. Item 1 adds historical venue text under the existing `espn25_named_previews` option. The 50-row data is [nfl2k5_moment_venues.json](../data/nfl2k5_moment_venues.json); the executable owner is [nfl2k5_moment_venues.py](../mod_editor/core/nfl2k5_moment_venues.py).

**INFERRED:** Every historical venue retains the existing audit's classification, date and source URLs. All 50 `real.classification` values in [moment_audit.json](moment_audit.json) are INFERRED. No new network was used. The shipped spellings copy that column exactly, including Municipal Stadium, Kansas City; Miami Orange Bowl; and GEHA Field at Arrowhead Stadium.

**PROVED OFFLINE:** The preview path is the SITU stadium index at record `+0x10`, selected through `20CC05..20CC2B`, then the global selected stadium pointer at `0xE5FE64`. Getter `0x77460` returns that 128-byte ROST stadium record. Preview callback `0x2C5A70` calls it at `0x2C5A71`, loads the name pointer at record `+0`, then invokes the native UTF-16 formatter `0x4A400`. The original callback is registered at `0xACFD40`. m1 intercepts the getter call only for new rows 26 through 50, so the first 25 still read the shared names.

**PROVED OFFLINE:** Stadium records have two display-name pointers: `+0` and `+0x10`. The location is `+8`, the physical asset code is `+0x0C`. The text sites covered by this patch are:

| PROVED OFFLINE site | PROVED OFFLINE reader and change |
| --- | --- |
| `0x2C5A76` | Override the preview name after m1's cell/record lookup. Native formatting remains intact. |
| `0x77540` | Selected stadium name getter, tail-called by the Stadium text callback `0x2C1640`. |
| `0x127181`, `0x1271C1` | Both stadium-name branches of the game-report formatter. |
| `0x1C08DF` | Presentation location formatter `0x1C08D0`, combines the second name with the city. |
| `0x1C0910` | Presentation venue-only bounded UTF-16 copy. |
| `0x318557` | The other name/location formatter's second-name read. |

**PROVED OFFLINE:** Every override checks mode `8` and unsigned ordinal below `50` on every read. Names and pointer cells live in a 2,304-byte allocator-owned allocation in existing RX page tails. No cache survives a mode change. The general stadium getter, stadium records, resource names, stadium slots, locations, geometry and gameplay predicates are unchanged. In particular, `0x63FB0` and `0x9A1E0` still compare the original stadium name against Texas Stadium and Reliant Stadium. These comparisons are gameplay behavior, not display readers.

**PROVED OFFLINE:** m1 recognizes the composed preview only after validating all venue hooks and the entire immutable venue allocation. Foreign hooks, mixed installations and altered names are rejected. Disabling restores every hook; re-enabling reproduces the exact installation. The full owner union fits without moving any established allocation. Strings never cross a physical span boundary. The allocator union, Build forwarding, image read-back and provider module/data pins include the new owner. The option remains off by default.

**PROVED OFFLINE:** [The native receipt](evidence/e2p3/native-venues.json) records all 50 preview names and the other native display reads. Tests import and select every real moment, execute the real preview formatter and presentation text copy, substitute a distinct modern name into both shared name fields, and require the complete stadium record to remain unchanged. Quick Game and franchise modes retain that modern name with a stale moment ordinal. Negative and out-of-range ordinals fall back. Archive I/O and presentation services are explicit harness boundaries; this is not a rendered-game witness.

**PROVED OFFLINE:** [The composition receipt](evidence/e2p3/option-composition.json) compares disabled output with the base commit's compiler on the same selected owner stack. The executable bytes are identical. The SITU compiler and its named/off data paths are unchanged by item 1. Reproduce with `python3 e2/prove_venue_composition.py`. Reproduce the 50-row text receipt with `E2P3_VENUE_PROOF=e2/evidence/e2p3/native-venues.json python3 -m pytest -q tests/mod_editor/test_nfl2k5_moment_venues.py`.

**DESIGN:** Main must witness the rebuilt candidate E's preview, loading/intro and visible overlays. Native text execution proves the strings delivered by these readers; it does not prove pixel layout, wrapping or which overlays a particular moment's abbreviated start presents. Baked venue signage and recorded speech are assets outside this text option.

**PROVED OFFLINE:** Item 1 was committed and bundled before item-2 work. Its private commit is `966ccae3ab43db102858d3c9f8af324caefe89ab`. The checkpoint `/media/noah/Storage/.b76-research/e2/astra-build/e2p3-item1.bundle` is 22,549 bytes, SHA256 `1916f0c618c2f16ec800c9c0485a0aeaef840bae1eb1df5e47117d907e8de64e`. Git bundle verification and a separate local fetch both reproduced the commit. It requires the supplied `e7d7aca5` base.

**PROVED OFFLINE:** The provider closure check also exposed candidate E's missing pin for its already imported `xdvdfs_compact.py`. Its existing bytes are now pinned alongside this owner. No compactor implementation changed.

**PROVED OFFLINE:** Final item-1 run: 28 passed, 1 skipped, 40 subtests passed in 123.62 seconds. The skip is the existing kickoff-v2 mechanism check, superseded by the kickoff-v3/v4 full-frame tests. The earlier m1/profile/allocator/provider run had 54 passes and two provider failures: one missing inherited compactor pin and one source hash changed while the new module was being edited. The final provider closure and exact hash checks pass after pinning the complete final sources. [Final tests](evidence/e2p3/final-item1-tests.log), [initial regression](evidence/e2p3/regression.log).

**PROVED OFFLINE:** All writes are in this checkout or e2 research storage. The private Git store is `.scratch/e2p3-private.git`; shared Git metadata, other worktrees and the user's disc folder remain untouched. No full build, xemu, push or tags were run. Native tests use a single bounded CPU state. The required builder-process check preceded the longer regression run.

**PROVED OFFLINE:** The old `eip=?` summaries did not establish failed reads. The extra-command branch of e2's GDB helper omitted `info registers`, then searched its output for an `eip` register line. All 31 legacy peeks have actual hexadecimal memory output in their raw logs. [The recovered audit](evidence/e2p3/lab-D-peek-audit.json) records those values and each log's SHA256. The retained filenames are:

| PROVED OFFLINE case | PROVED OFFLINE home filename | PROVED OFFLINE away filename |
| --- | --- | --- |
| Ice Bowl | `E2R-GB-pb.iff` | `E2R-DAL-pb.iff` |
| Wide Right | `E2R-NYG-pb.iff` | `E2R-BUF-pb.iff` |
| Moment 50 | `E2R-KC-pb.iff` | `E2R-SF-pb.iff` |
| Mixed Quick Game | `E2R-CHI-pb.iff` | `GB-pb.iff` |

**PROVED OFFLINE:** Those were separate samples, not an atomic state or full book-content proof. The deleted RAM snapshots cannot be recovered from them. This report does not upgrade their headers or names into proof of complete stock-book contents.

**PROVED OFFLINE:** [lab_memory.py](lab_memory.py) now requests EIP on every read, checks GDB's exit status and memory errors, preserves stdout/stderr and timeout output, and resumes through the existing monitor in a `finally` block. The installed GDB successfully imported the local reader both through its Python command and a `.py` command file. [The import log](evidence/e2p3/gdb-import.log) involved no target attachment. No shared k1 or tf harness file changed. The mixed-selection reader and route now live under e2 instead of importing h1's probe.

**PROVED OFFLINE:** A `witness` attaches once and reads through GDB's stopped inferior. The retained slices include EIP, mode `0xE5FF80`, ordinal `0xBF1858`, stadium pointer `0xE5FE64`, both shared display names, the installed historic venue pointer/text, static match teams at `0xB30864` and `0xB30A58`, filenames at `0xB307D0` and `0xB30810`, bound pointers at `0xE5FE80` and `0xE5FE84`, and both complete `0x13390`-byte PLAY bodies. Every slice has its guest virtual address, size and SHA256. Partial evidence survives failures. A book witness uses about 160 KB rather than a full 64 MB RAM dump.

**PROVED OFFLINE:** [lab_verify.py](lab_verify.py) prepares a read-only catalog from the candidate disc. It requires installed venue/stock owners, pins all 32 stock aliases against the existing raw or one-pool hashes, records all 32 corresponding modern books, and rejects identical stock/modern contents. Bound PLAY comparison reverses field-relative pointer relocation, excludes the resource framework preamble, and clears only formation bit 30 and play bit 31. Native instructions at `0xE0EDE` and `0x1A9A8C` set those flags during decoding. All remaining content bits, including personnel and assignments, participate in the comparison.

**PROVED OFFLINE:** [The lab tests](evidence/e2p3/lab-tests.log) passed all 4 tests in 18.59 seconds. They exercise native selection, staging, decoding and binding for the Ice Bowl and a mixed Quick Game. [Their receipt](evidence/e2p3/lab-native-proof.json) records home GB / away DAL stock bodies, then home CHI stock / away CHI current-filename bodies, with distinct canonical hashes. The ordinary filename uses the retail fixture body; its stock alias uses the pinned one-pool body. Candidate E's actual modern recipe contents remain a main-only catalog/lab check. Changed football payload bytes and a deleted retained dump are rejected. GDB transport is mocked in these tests; the native venue table in this book fixture is a bounded fixture cell. The separate 50-row native venue test executes the installed venue owner.

**PROVED OFFLINE:** The final venue rerun includes actual Quick Game mode `4` alongside modes `0`, `1`, `5` and `6`: 7 passed in 82.86 seconds. It updates the 50-row receipt without changing any compiler source after the checkpoint. Shell syntax and Python compilation pass for the lab files. Item-2 changes are confined to e2 evidence/lab/report and tests, outside the compile key.

**DESIGN:** Main runs `E2_DISC=/path/candidate-E.iso E2_RECEIPT=/path/candidate-E.build.json bash e2/lab_main.sh`. Its default output is `/media/noah/Storage/.b76-research/e2/lab_E_e2p3`. The script waits for the builder, checks the disc against its receipt, creates the catalog, and uses the existing xemu lock. Each case refuses to overwrite an existing run. `E2_ONLY=super_bowl` selects a single case; use a fresh `E2_LAB` for a rerun.

**DESIGN:** Main's four cases retain named-preview, loading/intro, field and later frames, plus exact book witnesses at load and after the 60-second watch. `lab_verify.py` requires both captured book contents and the expected side bindings. Moments also require a preview witness and venue OCR. Wide Right must read Tampa Stadium; Ice Bowl must read Lambeau Field; moment 50 must read Allegiant Stadium. Missing OCR is an explicit review failure, not an inferred visual pass. Screenshots remain necessary for layout, presentation, player selection and stalls. Mixed Quick Game must remain mode `4`, with historical Bears and a current opponent.

**PROVED OFFLINE:** The final cumulative bundle is `/media/noah/Storage/.b76-research/e2/astra-build/e2p3-final.bundle`; the lab follow-up alone is `e2p3-item2.bundle` in that directory. The latter requires the item-1 commit. Their verified heads, hashes, sizes and fetch checks are recorded in `e2p3-delivery.json` beside them. All private commits carry the requested co-author trailer. The checkpoint bundle remains unchanged.

1. PROVED OFFLINE: All 50 native previews read the audited venue names.
2. PROVED OFFLINE: Presentation and report readers use the same moment-only names.
3. PROVED OFFLINE: The existing named-previews option controls the new owner.
4. PROVED OFFLINE: Disabled compilation matches the base executable bytes.
5. PROVED OFFLINE: Quick Game and franchise retain shared modern names.
6. INFERRED: All 50 historical venue claims retain the audit's classification.
7. PROVED OFFLINE: The complete owner union fits without moving existing owners.
8. PROVED OFFLINE: Item 1 passed 28 tests and 40 subtests; one existing test skipped.
9. PROVED OFFLINE: The additional venue run passed all 7 tests with Quick Game mode 4.
10. PROVED OFFLINE: Old unknown-EIP summaries concealed successful raw memory reads.
11. PROVED OFFLINE: The local reader retains checked EIP and complete per-side PLAY slices.
12. PROVED OFFLINE: Native book tests verify Ice Bowl and mixed-side content identities.
13. PROVED OFFLINE: The first verified checkpoint is commit 966ccae3ab43.
14. PROVED OFFLINE: Separate verified lab and cumulative bundles preserve that checkpoint.
15. DESIGN: Main runs candidate E's lab and judges the rendered frames; Astra launched no game.
ASTRA_DONE
