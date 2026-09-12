# H3 beta 66.1: APF CPU playbook content control

Implemented the O-ManBlock Queens retirement fix, explained Book Identity, kept preset controls editable, and added a direct clone-to-Fine-tune editing route with named recipes and verified copied-folder builds. Play-calling logic and executable bytes are unchanged.

Read `ASTRA_CONTEXT.md`, triage rows 13–17, the ordered DM thread and both requested screenshots. Urianus's 12:26 report, “prevents me from swapping all formations of a specific personnel type, like all Queens,” is reproduced by the old advertisement surviving every swap. His direction at 6:25, “I wouldn't mess with the general playcalling logic at all until we figure out how to take full control of CPU PBs,” governs this implementation. The changelog quotes both reports and his preset complaint.

## PROVED

- O-ManBlock's Queens records are 2 / I Spread, 9 / Strong I Spread, and 14 / Weak I Spread. Moving all three to Quads / Flush succeeds. The before advertisement is `[0, 1, 3, 6, 26]`; after is `[0, 1, 3, 8, 26]`. The receipt and visible Fine-tune status say **“Queens retired from this book's ladder”**; the build completion dialog repeats it.
- The same rule handles a safe trailing formation removal. The compiler and verifier derive retirement from reachable record supply. It rejects holes, empty books, emptied required twins, loss of every ordinary play, hidden/duplicate bits that normalization could restore, and a retirement that strands the native fallback. The category picker model accounts for multiple categories sharing one row, including the exact-row last-match versus fallback first-match behavior.
- The BASE native harness executes the personnel row picker to `0x8486088C`, its row search, bit walk, formation reverse lookup and category membership test. All 28 requested rows run before/after. Queens is never returned after retirement; every previously served request retains a populated, reachable record. The stale-mask negative control returns Queens for row 7 and finds no usable record. The Python retirement validator matches native category results for both books.
- The harness uses the pinned flat BASE image, SHA-256 `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`. Unicorn's PPC32 core runs the original selection instructions. A narrow adapter implements the Xenon 64-bit register save/restore thunks and three inline saves/restores; it does not stub any picker/search result. Book/MASTER pointers and the current-book global are supplied as harness state. Each call has a 50,000-instruction bound.
- The 15-book retail census still reads 209 populated records and the same three formation/package alternatives. The move sweep now reparses **200 accepted moves**, with **9 unsafe bounded-fallback refusals**. This census is data proof; the native execution matrix specifically covers the reported O-ManBlock bulk Queens operation.
- The writer explicitly rejects H7A matches with length greater than distance, independently decodes its output, and reports zero overlapping matches. `tools/apf_h7a_optimal` remains mode 0755. Repeated `python3 packaging/repin.py --apply` runs report **0 pin updates**; no integrity pin was left stale.
- Stock and independent book reads validate decoded name against the filename CRC. The separate content editor resolves book and MASTER resources by name and saves recipes bound to source book and MASTER hashes. It accepts archive ordinals beyond the former retail bound after validating actual ownership.
- Offscreen tests open an actual `BookContentDialog` containing the existing `ApfPlaybookMembershipPanel`, select a clone, move an audible slot, remove a play, change a formation, save/reload its recipe and build a new synthetic two-volume game. The built clone reparses correctly; its shared donor, roster and executable stay identical. A late stock-book load cannot replace the selected clone. Same-source refresh still avoids rereading the catalog.
- The new builder writes each edited entry's actual volume segments, preserves the archive directory, reparses the published books, compares all untouched pack bytes and checks the executable. It refuses source/output aliasing and existing output folders. Failed publication removes only the newly created destination.
- Book Identity presets fill the donor and the independent copy's membership/audibles while leaving team, label and donor editable. A changed donor clears an incompatible recipe. The three recipes are explained; “All three” is removed from this single-team form. Original-project shared-book staging remains separately labeled. Both real retail preset compilation and synthetic preset-copy publication/idempotence pass.
- Existing identity evidence was found under `ASTRA_APF_BOOK_UNLOCK_REPORT_2026-09-09.md` in the handoff archive, not the optional filename `ASTRA_APF_BOOK_IDENTITY_REPORT.md`. The six retail identity tests reprove fifteen resource names, five clones creating twelve CPU offensive resources, three authored presets, the BASE executable/CRC pin, eight raw-save template slots, and preset content in an independent clone.

## UNWITNESSED and integration boundaries

- Full BASE/TU game loading of an expanded archive, actual team consumption of the edited clone, on-field personnel, audible usage, and behavior in every game mode. The native proof establishes the bounded personnel/record path, not an entire Quick Game or the ordinary weighted play picker. Already unserved baseline requests are shown in the receipt; the assertion is no new null path for previously served requests.
- General play-calling randomness, third-down selection probabilities, save overrides, substitutions, shared-play instance selection, and runtime cache-normalization invocation are not claimed fixed. No calling heuristic or XEX patch was changed.
- Independent defensive cloning and reopening a mixed-asset Studio project against an expanded archive remain outside the proved path. Cloning shifts sorted directory indices. Finish the original project first; the named book-edit session is the supported continuation after cloning.
- Full staged release/runtime gates require the protected integration in `WIRING.md`: one new module/document allowlist entry, runtime import closure, three existing capability-description replacements, and the complete `gui.py` blurb block. The Book Identity page/button wiring already exists and the owned panel implements the route directly.
- Full registry file validation currently stops at baseline missing `reports/assets/apf_ausb_inventory.json`. The temporary merged registry passes schema validation; every replacement row backend/evidence path was checked to exist. The protected registry was not changed.
- No retail game folder was built here. `/` was already below the handoff's 100 GB free threshold (89 GB available), so all full publication tests used small synthetic archives. Retail tests compile/read/decode in memory. No retail bytes were committed or distributed. No emulator, GUI display, audio, network, push or external messages were used.

## Exact test commands and output

Every suite below ran standalone. Environment:

```bash
export PYTHONPATH=/home/noah/2k-worktrees/astra-b66-apf-gameplay
export QT_QPA_PLATFORM=offscreen
export APF_BOOK_RETAIL_INDEX='/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'
export APF_BOOK_FLAT_PE=/home/noah/.codex-tmp/franchise-2026-08-28/apf.pe
export APF_BOOK_RAW_SAVE=/home/noah/Downloads/apfe/Roster.ROS
```

| Command | Observed output |
|---|---|
| `python3 tests/mod_editor/test_apf_b661_ladder.py` | Ran 6 tests; OK |
| `python3 tests/mod_editor/test_apf_b661_book_content.py` | Ran 5 tests; OK |
| `python3 tests/mod_editor/test_apf_b66_personnel.py` | Ran 3 tests; OK |
| `python3 tests/mod_editor/test_apf_book_identity_qt.py` | Ran 5 tests; OK |
| `python3 tests/mod_editor/test_apf_book_unlock.py` | Ran 19 tests; OK |
| `python3 tests/mod_editor/test_apf_book_unlock_retail.py` | Ran 6 tests; OK |
| `python3 tests/mod_editor/test_apf_cpu_audibles.py` | Ran 18 tests; OK |
| `python3 tests/mod_editor/test_apf_splb_writer.py` | Ran 22 tests; OK |
| `python3 tests/mod_editor/test_apf_splb_tag_reassignment.py` | Ran 86 tests; OK (skipped=1) |
| `python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py` | Ran 14 tests; OK |
| `python3 tests/mod_editor/test_apf_splb_formation_personnel.py` | Ran 11 tests; OK |
| `python3 tests/mod_editor/test_apf_wave_integration.py` | Ran 8 tests; OK |
| `python3 tests/mod_editor/test_apf_capability_action_parity.py` | Ran 11 tests; OK |

**214 tests: 213 passed, one preexisting skip.** The skipped test uses an unavailable historical PE path (“decompressed APF PE is not on this machine”); the new native test and retail BASE identity test use the available pinned image and pass. [Machine-readable results](reports/apf_b661/test_results.json) contain commands, environment and output tails. `git diff --check` and `py_compile` for changed product modules pass.

Native reproduction (the report destination must be new):

```bash
python3 tools/apf_personnel_native_probe.py \
  --index '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A' \
  --image /home/noah/.codex-tmp/franchise-2026-08-28/apf.pe \
  --report /tmp/apf-h3-native-recheck.json
```

Output: `PASS: Queens retired; 28 native row requests; no new null record path`.
[Committed native receipt](reports/apf_b661/personnel_native.json) contains category/record selections and hashes, not executable or archive payloads.

The updated legacy census was also run as `tools.apf_b66_gameplay_witness.personnel(Path(<retail 0A>))`; output counts were `retail_records=209`, `multiple_word_b_bits=37`, `moves_reparsed=200`, `primary_differs_from_master=19`, `unsafe_ladder_refusals=9`.

## Witness and next job

The exact step-by-step witness for Urianus, including the three stock formation names, Beasts/Browns clone assignment, donor control comparison, recipe reopening, preset control check and requested observations, is in [CPU book control and witness](docs/mod_editor/apf_b661_cpu_book_control.md#exact-witness-for-urianus). The same document separates proved content writers from the next work: BASE clone-consumption witness, the remaining picker/cache/audible chain, defensive clones/save bindings, and eventual insertion-safe mixed-asset project identities. No new calling heuristics are proposed.

## Commit handoff

The checked-out branch is `astra/b661-apf`, based on `1d38df5e782ffe8115ed38e82c4c639c04b1d3b5`. Its linked Git metadata is outside the writable sandbox. The normal explicit-path `git add` failed creating `/home/noah/2k-football-mod-tools/.git/worktrees/astra-hf63-music-verify/index.lock` with **Read-only file system**. The checkout's actual branch ref could not be advanced.

Instead, an isolated Git metadata directory under `/tmp` borrows the existing read-only objects and records explicit-path commits on a branch also named `astra/b661-apf`. `ASTRA_H3_COMMITS.bundle` contains those commits above the stated base; source changes remain visible in this worktree. No main checkout or other worktree was written. The bundle is a handoff artifact, not a release asset.

To integrate in a writable repository containing the base:

```bash
git fetch /absolute/path/to/ASTRA_H3_COMMITS.bundle refs/heads/astra/b661-apf
git cherry-pick 1d38df5e782ffe8115ed38e82c4c639c04b1d3b5..FETCH_HEAD
```

The initial ladder commit is `1c88a1b0`. The implementation commit is `ba1df90a`. The documentation commit is listed by `git bundle list-heads ASTRA_H3_COMMITS.bundle` and `git log` after fetching. Untracked briefing/context files and the retail `extracted` symlink were not committed. `WIRING.md` contains complete protected-file blocks; the new alpha.87 changelog section is at the top of the APF changelog.
