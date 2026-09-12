# Beta 67 P2: defensive call, removal, USER/global books, Xenia patch installation

PROVED: the two product changes are implemented and pass the standalone offline suites below. The defensive research has pinned-byte evidence and repeatable bounded BASE witnesses. **All gameplay remains UNWITNESSED.** HYPOTHESIS: the complete per-team profile producer, full live paired-play scoring, every saved-user override transition and warm cache lifetime remain follow-up work; this job does not claim full CPU play-calling control.

PROVED delivery scope: branch `astra/b67-p2-defense`, base `3f76aee84a872033c0e4ba85fb94be2a819e6bb2`. The environment makes this worktree's Git metadata read-only, so delivery uses the explicitly permitted **bundle**, `ASTRA_B67_P2.bundle`, generated from an isolated Git index/object directory. Only the listed product/research/test/report paths enter the commit. No push, network, emulator, display, audio, disc copy or retail payload output was used. The checked-out branch remains at its original commit until the integrator imports the bundle.

## Defensive model and Urianus's reports

PROVED details, exact edit, limitations and commands: [defensive model](docs/research/apf_defense_playcall_model.md), [machine-readable receipt](docs/research/apf_defense_playcall_receipt.json), [bounded probe](tools/apf_defense_native_probe.py).

| Grade | BASE address | Finding |
|---|---|---|
| PROVED bytes + bounded prefix | `8486D0F8..D38C` | Real defensive driver chooses category and formation, then calls two defensive component pickers. It is not the offensive four-retry loop. |
| PROVED bytes + bounded ordinary path | `8486CAD0`, especially `CCA4..CCC0` | Reads the chosen offensive CATEGORY's low-six-bit personnel row and maps it for the defense. This is the handoff to sibling P1's offensive selector research. |
| PROVED bytes + bounded row 3 | `84869B60` | Ordinary offense rows 0..4 request defense row 13, or 11 close to the goal line. No ordinary request arm returns 12. |
| PROVED bytes + bounded | `8486AEB0`, `8486B1C4`, `820C88D4` | Category weight zero below the request; otherwise curve 1/.01/0 at gaps 0/1/2, then cubed. |
| PROVED bytes + bounded | `8486BC08`, `848693F8`, `84869058` | Formation/category membership and component supply, trailer rating weight, power-one lottery. |
| PROVED bytes; candidate helpers bounded | `8486C448`, `8486C6C8` | First and compatible second defensive PLAY components; validity and formation filters, score, two power-three draws. 192 compatible pairs enumerated natively for stock 4-3. |
| PROVED bytes only | `8486A860`, `84865AE0`, `84863F58` | Profile/lineup feature scoring plus two entry weights and situation/flag factors. Full game-world evaluator not executed. |
| PROVED bytes + 120 native/reference transitions | `84863388`, `84B3E858`, `84B3E8B8` | Shared weighted lottery and 55-word 64-bit additive RNG at `8505CD00`; tie and zero-sum behavior matter. |
| PROVED bytes | `84B3E9B8`, `846918C0..D4`, `8470C4C8` | RNG initialization and reseeding; startup reads the time-base register, match initialization accepts stored seed from `8501FAD0+804`. |
| PROVED bytes + bounded record/cache region | `84A8C790`, `84A8A258`, `84A8A330` | First-hole lookup boundary; record compaction; category caches rebuilt from primary and all B bits. Compact removal remains absent. |
| PROVED bytes | `84A8D740`, `849D40E8..4220` | Another source/global merge can add records. A removed disc template is not authoritative over a saved bank or another merged source. |
| PROVED bytes + resource/roster reparse | `849D6208`, `849D80B0`, `849D8160`, `84AE8948` | Name-resolved labels, USER overrides/banks and directly loaded global supplements. |

Urianus row 2:

> “Adding D forms, like 3-4 to a 4-3 PB, works as normal. It selects between them randomly whenever they both 'fit' the personnel matchup, as it does with 4-3 and Bear. Except 5-2, which is never selected if added.”

PROVED bounded BASE: production-compile X-43Cover2 with an added 3-4 record and then with an added 5-2 record, using the same 51 X-34Base donor memberships in both to isolate the category. Execute actual defense driver/category/formation selection for 128 explicit synthetic RNG states. Added 3-4: **65 × 4-3, 63 × 3-4**. Added 5-2: **128 × 4-3**. The request is row 13; 4-3 and 3-4 both fit at row 13; 5-2 is row 12 and receives zero weight. Bit 27 is advertised and considered. It is not a missing mask bit or the offensive ladder bound.

PROVED bounded BASE: a constructed high draw near the goal line selects 5-2 (category 27/form 150), where its gap-one weight is approximately .01 cubed against Goal Line's 1. HYPOTHESIS: ordinary zero weight and rare near-goal weight explain Urianus's observation. His exact edited file and live states were not supplied, so “5-2 can never be selected” would overstate the evidence.

Urianus row 5:

> “The main limitation now, besides playcalling, is REMOVING formations because those PBs aren't blank obviously, so the CPU is going to use those stock ones no matter what we add on top.”

PROVED bounded BASE: deleting every whole record for a formation, compacting survivors before normalisation and rebuilding caches from surviving primary/B memberships keeps removal removed. X-43Cover2 form 141 is absent from reverse lookup and sixteen ordinary defensive calls; its category mask is `00003400`. USER-o form 0 is absent, other records remain and mask is `000001EF`. Both normalize twice identically. Merely emptying a first record hides later records before normalization and can alter a surviving B word during native compaction (`CAF4..CB1C`); X-43Cover2 then advertises `000037FF`. That is not stock-record resurrection. Saved USER banks and global merges are separately authoritative sources. HYPOTHESIS: hot cache/special-tail behavior still requires a lifetime witness. No new removal product writer is shipped.

PROVED TU comparison: 16 functions compared on both full hash-pinned images; 14 normalized-equal, merge byte-identical, loader's residual difference `+1758` versus `+1780`. HYPOTHESIS: normalized equality is insufficient to assert equivalent callees/data or live TU compatibility. TU native execution was not run.

## USER/global identification and product changes

| Grade | Pinned outer | Resolved name | Header filename ID |
|---|---|---|---|
| PROVED | 293 | USER-d | `2F551CF1` |
| PROVED | 656 | global-d | `6C4EBF6F` |
| PROVED | 1037 | USER-o | `AD00822C` |
| PROVED | 1439 | global-o | `EE1B21B2` |

PROVED: all are 32,288-byte SPLBs. Roster label IDs 25..31,64..67 use USER-o; 56..63,68 use USER-d; globals have no roster labels. The loader formats the selected label type as `{type}-spb.iff`. A CPU assigned a USER label uses that same filename path unless a working-book override is active. USER A/B can use buffers directly, and eight saved user banks are initialized from USER templates and later serialized. Human control alone does not determine the disc filename. USER-d uses the same defensive category/formation/paired-play constraints as the four CPU defensive books; no USER bypass was found in that path. HYPOTHESIS: every UI transition activating those overrides has not been witnessed.

PROVED authored change and offline checks: Fine-tune and CPU Play Calling enumerate name-resolved resources after shifted directory indices; Book Identity accepts all 15 named donor types. Same-side label checks allow offensive and defensive USER/global clones and reject cross-side assignment. CPU Play Calling can review defensive personnel while directing defensive play/audible edits to Fine-tune; its offensive run/pass balancing accepts USER-o/global-o. Tests clone all four new donor types, verify donor content and the roster reparse, and perform a USER-o Fine-tune edit through the real panel that reparses from the rebuilt synthetic archive. Seven-stock behavior suites also pass.

PROVED authored change and offscreen fake-folder checks: launcher settings persist the chosen Xenia config; patches live beside the configured executable under `patches/54540807-studio-pass-fetch.patch.toml`. Both a newly compiled patch and an existing canonical Studio export can be installed. The dialog defaults to No and identifies the destination/config before consent to set `Memory.apply_patches = true`. Other TOML settings are preserved and reparsed. The launcher explicitly supplies `--config=...` and uses Xenia's folder as cwd. Status reports installed/enabled/disabled, and removal deletes only the managed patch, retaining other files and the shared toggle. Failed config writes restore the prior patch. The patch still has the exact authored BASE/TU payload checks.

PROVED scope label in product code: **“Last-resort fetch only; not a CPU play-calling fix.”** EXPERIMENTAL; no automatic preset enablement. HYPOTHESIS/UNWITNESSED: real Xenia module matching, patch discovery and its football effect must be witnessed. This fixes Studio installation/configuration, not Urianus's third-down call selection.

PROVED protected-file boundary: main-window launch-result text and existing capability-row metadata updates are supplied in [WIRING.md](WIRING.md). `gui.py`, the registry and other protected implementation files were not edited. The installer/status/removal UI itself is implemented in the owned CPU Play Calling panel. No additional release allowlist entry is needed for a new runtime module; the only new tool is research tooling.

## Tests run

PROVED command form for every product suite below: `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/<file>`. Each file ran standalone, not pytest. Research native additionally set `APF_RETAIL_PE` and `APF_RETAIL_TU_PE` to the two pinned, read-only scratch flat images named in the research document.

| File | Actual unittest output |
|---|---|
| `test_apf_b67_books_qt.py` | Ran 3 tests in 61.826s; OK |
| `test_apf_b67_xenia_patch.py` | Ran 3 tests in 0.104s; OK |
| `test_apf_pass_fetch_export_qt.py` | Ran 7 tests in 0.292s; OK |
| `test_apf_defense_research_native.py` | Ran 3 tests in 66.042s; OK |
| `test_apf_defense_research_identity.py` | Ran 1 test in 0.418s; OK |
| `test_apf_cpu_audibles.py` | Ran 18 tests in 2.979s; OK |
| `test_apf_book_unlock.py` | Ran 19 tests in 23.137s; OK |
| `test_apf_book_identity_qt.py` | Ran 5 tests in 0.036s; OK |
| `test_apf_b661_book_content.py` | Ran 5 tests in 25.046s; OK |
| `test_apf_splb_writer.py` | Ran 22 tests in 0.207s; OK |
| `test_apf_splb_formation_personnel.py` | Ran 11 tests in 1.283s; OK |
| `test_apf_studio_safety.py` | Ran 27 tests in 0.117s; OK |
| `test_apf_studio_core.py` | Ran 9 tests in 0.027s; OK (skipped=1, missing local release artifact) |
| `test_apf_wave_integration.py` | Ran 8 tests in 16.739s; OK |
| `test_apf_playcall_patch.py` | Ran 11 tests in 1.807s; OK |

PROVED: **152 tests, one skip**, with no failures in these final suite runs. The explicit no-retail runs, using `APF_RETAIL_0A=/nonexistent/APF/0A`, also return `OK (skipped=1)` for each new research file. `git diff --check` passes. Repin dry-run reports `would apply 0 pin update(s)`; the required `python3 packaging/repin.py --apply` is run immediately before the explicit-path commit in the isolated Git directory.

## Follow-up contract and witness

HYPOTHESIS, design input for the per-team profile job: P1 must hand over its actually selected offense category and formation at the `CAD0` read, not a guessed book/personnel label. Identify the defense team and resolved active book after save/override/global merging. Category weights, formation ratings and paired-play scores are distinct controls (lottery powers 3,1,3,3). Preserve both defensive output PLAY pointers, special calls, component supply and native behavior for teams with no profile. The producer/lifetime of `851595D0`'s side profiles and complete `A860/65AE0` game-world scoring are still needed for a trustworthy live play policy.

HYPOTHESIS, witness checklist for Noah/integration: import the bundle and apply only the new P2 WIRING section; clone USER-o and USER-d to unused labels, edit the clones and verify team isolation with both disc assignments and loaded user saves; replay the 3-4/5-2 additions and a compact removal in BASE/TU with fixed saved state; install a matching pass-fetch export into a fake/test Xenia setup first, inspect the selected config and patch status, restart the real emulator, verify the matched module/log, then remove it and verify absence after restart. A third-down TE outcome would not on its own prove which selector path ran.
