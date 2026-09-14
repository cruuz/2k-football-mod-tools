# Beta 69 J1: equipment, build refusals and the Style 6 report

Branch: `astra/b69-j1-equipment`. Base: `922c009d`. Read ASTRA_CONTEXT, triage rows 1, 2, 4, 5, 6, 23 and the beta-68 T2, T1 and A1 reports. **All current in-game outcomes are UNWITNESSED.** The reporters' older observations remain evidence, including the negative Bears game report; passing these tests does not overturn it.

The granted owners contain the diagnostics, legacy no-op correction, load-preflight API, measured fit ladder and retry dialog. **Apply [WIRING.md](WIRING.md) before release.** The protected Studio/session/import hooks and Build list are supplied as exact code, with the proposed retry worker and list method exercised offscreen. J2 retains the model integration in the build service; my change in that shared file is only `_last_message`.

No larger-allocation option is shipped. An enlarged chunk passed the native loader proof, but archive relocation has not passed a disc round trip. The stronger native shoe test proves that the tested field path can bind package-local shoes10; it does not reproduce or fix the navy shoe in maumau78's game.

## 1. The failure without a reason

Coach Edwards: “The era is not descriptive as to what exact texture I should change or remove” and “there is no way to tell specifically what needs to change”.

**PROVED cause:** [the old `_last_message`](mod_editor/core/nfl2k5_build_service.py:868) concatenated stderr followed by stdout, selected the last nonempty line, and truncated it to 600 characters. The backend prints its actual refusal on stderr, while stdout contains timing markers. Consequently the last timing line replaced the refusal. `Nfl2k5BuildService.build`, at line 1316, prefixes that result with “The modded XISO could not be built.” and the Studio displays it.

The triage's interpretation of `source_validation` needs correction: [the marker at line 5473](tools/nfl2k5_visual_mod_project.py:5473) is printed **after source validation completes**. It is not evidence that source validation refused anything. A compile refusal before the next marker leaves `source_validation` as the last stdout line. This is why the exact failing check in Coach Edwards' unavailable project cannot be identified from his photograph.

Implemented:

- Prefer stderr, filter internal `NFL2K5_` progress lines, retain the complete multiline refusal and next step. An empty backend refusal has a plain fallback.
- [Track the active phase in words](tools/nfl2k5_visual_mod_project.py:2650), including load, source/path validation, compilation, source binding, copy, span writing, artifacts/directory, whole-disc comparison and receipt verification. Timing markers continue to serve the log.
- Name original, zero-based project indices, page, part, uniform selector and texture. Compilation names every edit contributing to a shared TSET; compiled span order is not substituted for project order. Input pin, source-bind, write, owned-span readback and receipt-input errors carry that context. A disc/path-wide error names its phase and cause; it does not invent a particular offending edit.
- Record `project.includes` in the receipt. The Build list uses `ProjectEditTimeline` to rank changes actually observed in the session, without changing canonical indices. Old projects contain no creation times, and the list explicitly says that their original chronology is unknown. Text, equipment and other canonical edits remain individually listed, including global consumer copies. J2's canonical model rows join this list during integration.

The deliberately refusing synthetic project goes through the real backend subprocess and build service. Its surfaced message is:

> The modded XISO could not be built. While compiling project edits: Project edit index 0: Equipment / Shoes / team or uniform set SYNTHETIC / texture tset:0:8:0:shoes01: PNG must be exactly 32x32

The test asserts all identifying fields, the cause, no marker text, and no published output. Long and multiline reasons are also checked. See [the five build tests](tests/mod_editor/test_b69_j1_build.py) and [their output](reports/b69_j1/tests/test_b69_j1_build.py.log).

## 2. Reconstructed legacy records

Coach Edwards: “shoes that I'd imported from a much older release (maybe release 49)”. Row 23 records “nope unsuccessful” after the beta-68 round-trip note. His later “5 minutes or less” successful build is a positive observation of beta-68 build speed, not evidence that the shoe import was fixed.

History was examined with `git log -p` for `mod_editor/core/nfl2k5_uniform_equipment_writer.py`, `mod_editor/core/nfl2k5_equipment_import_intent.py` and `tools/nfl2k5_visual_mod_project.py`, then the historical sources were read with `git show`:

| History | Actual stored shape |
|---|---|
| `93e1f6a7`, RC49 | Project edit has `kind: uniform_equipment_texture`, `asset_id`, `png`. An ordinary PNG requests the then-supported palette recolour. There was no independent-chain intent to reconstruct at RC49. |
| `adb037c0`, beta 62, through the beta-63.1/65 writer lineage | The same project fields. The PNG carries ancillary `npTC` JSON: schema `nfl2k5_equipment_import_intent/v1`, target `asset_id`, mode `independent-mip-chain`, `rgba_sha256`, and scale 1, 2 or 4. |
| Current tree | The same intent schema remains admitted. Mips are generated from the authored base, or an independently validated retail donor is preserved. Project JSON did not store a serialized mip chain or a build receipt. |

The regression constructs the old JSON and ancillary chunk manually, including its checksum, rather than using today's intent writer. Both the plain-PNG record and the v1 own-texture shoe record load, build a bounded synthetic disc and pass `verify_written`. The glove case loads and retains both complete synthetic mip levels. Invalid intent pixels and a genuinely unfit legacy group refuse in load preflight, before source-disc validation or any output. The error names the part and instructs reimport at the checked size, or removal in the older Studio and resaving.

**PROVED regression and fix:** an old own-texture copy matching retail previously appended a private chain. Beta 68 recognizes those pixels and correctly returns the exact retail span. Then [source binding](tools/nfl2k5_visual_mod_project.py:4797) refused that valid result as `replacement equals retail`. The [before-fix trace](reports/b69_j1/legacy-noop-before.log) identifies the exact check. Executing the writer source from `b2d5d0cf` on the same synthetic input produced 5,888 video bytes; current recognition preserves the original 4,480. Historical writer SHA-256: `d914d5e6224476bbc9e385aded38cf521d213f873a62cf5280032c61e73ebcd4`. [Comparison receipt](reports/b69_j1/legacy-writer-comparison.json).

That source-equal equipment edit now passes the existing span/content checks, produces zero changed bytes, and is explicitly recorded as `already_matches_source` / `exact_source_bytes`. Its output equals the source and independently verifies. It is not silently removed or described as newly changed artwork.

| Candidate check from the brief | Finding |
|---|---|
| Beta-68 retail recognition | Participates in the proved no-op regression above. The failure is in source binding, after compile. |
| Exact-fit rule for a recognized, incompatible retail chain | Retained: silently reducing an exact retail copy would break the beta-68 round-trip guarantee. Unhonourable restored groups must be rejected at load. |
| Mip shape | No historical project mip array exists to migrate. The old v1 shoe/glove records pass complete-chain checks. Invalid checksums/dimensions still refuse. |
| Compile cache | No demonstrated legacy key collision. The beta-68 input/mode/scale/origin/compiler-content key tests pass; changed compiler contents invalidate old spans. No cache schema or trust guard was relaxed. |
| Receipt verify | The old project does not import an old build receipt. Builds write a fresh receipt; publication reads it without recompilation. Tampered receipt/span tests still pass. |

**HYPOTHESIS, not Coach Edwards' diagnosed file:** his volt artwork may fail compilation for another reason, including a different consumer package's budget. The existing import compiles the selected package before fanning out to global copies; `replace_batch` validates PNGs, not every other consumer's compressed fit. WIRING adds a complete prospective-equipment preflight before atomic staging, as well as load preflight before publishing the restored session.

[The preflight helper](mod_editor/core/nfl2k5_uniform_equipment_writer.py:1447) compiles full groups but skips pack-wide receipt hashes. `read_project(path, equipment_index=pack0)` exposes it to canonical project loaders. Normal build loading and `verify_written` do not introduce an extra full preflight, preserving the compile cache and receipt-only verification. **The ordinary GUI project-load guarantee depends on the supplied protected session hook.** Pending import/archive rows use no invented build index; canonical build records use their actual indices.

The five A1 defects remain fixed: registry counts/closures are unchanged, palette-only ignores retail-chain hints, malformed cache envelopes become misses, and unchanged transport retains its actual bytes/statistics. All ten A1 audit cases pass. Its StopLookup test still checks the real cache key and original exception cause through the new context wrapper.

## 3. The fit wall and the growth investigation

maumau78: “if i use 128x128 or 256x256 I got this error”.

The attachment `discord-dump-2026-09-13/attachments/2k5-bugs_3f58becf_3.png` is actually JPEG-encoded despite its extension. Pillow decoded its 256x256 orange Nike atlas and a temporary canonical PNG supplied the encoder. Source file SHA-256: `c9b845b09f70a9bb60ae2462dbceddf975f6b303109894565307b05019c7f7ae`. The attachment and all retail payloads remain outside the repository.

**PROVED measurements:** target `tset:3734:9:4:shoes10`, uniform `15H0`, supplies the reported **58,432-byte compressed body budget**. It is a budget-matched stand-in, not a claim that this was his selected package. Every candidate includes unchanged sibling images and the complete new private chain. “Colours” means the maximum palette count (some quantizations use fewer distinct entries). The table reports optimal token-parse stream size, before fixed-span filling, taking the smallest stream across the retail geometry and the writer's allowed 10/11/12-bit tiers. The separate 32-byte wrapper is not charged against this body budget.

| Game image | Colour limit | Optimal bytes | Over 58,432 by |
|---|---:|---:|---:|
| 256 x 256 | 256 | 128,885 | 70,453 |
| 256 x 256 | 64 | 97,441 | 39,009 |
| 256 x 256 | 16 | 81,017 | 22,585 |
| 128 x 128 | 256 | 75,521 | 17,089 |
| 128 x 128 | 64 | 69,064 | 10,632 |
| 128 x 128 | 16 | 63,947 | 5,515 |
| 64 x 64 | 256 | 62,948 | 4,516 |
| 64 x 64 | 64 | 61,127 | 2,695 |
| 64 x 64 | 16 | 59,521 | 1,089 |

[Full measured streams and attempted palettes](reports/b69_j1/fit-baseline.json). Bears `05H0` actually has a **55,008-byte** shoes10 body; its separate [nine measurements](reports/b69_j1/bears-fit-baseline.json) must not be compared against 58,432 as though they were the same package.

The new fit error for a requested full-size own import is measured, not an estimate:

> Equipment art cannot fit: it missed the 58,432-byte span by 6,110 bytes (64,542 bytes required at the smallest measured encoding). 64 x 64 at 4 colours would fit for tset:3734:9:4:shoes10. Choose Try that to check and import that size. Fine detail and shades will change.

The 64,542-byte minimum here is the requested full-size image at **two colours** after the full ladder, not the 256-colour table entry. The checked alternative uses four colours and 58,423 encoded bytes. 128x128 was tried first and did not fit even at the ladder's lowest colour count.

[The writer](mod_editor/core/nfl2k5_uniform_equipment_writer.py:584) tries greedy transport, then the existing beta-68 optimal helper, then fewer shades (256,128,64,32,16,8,4,2). On a miss it checks smaller sizes in descending order, compiling the full group with all other edits retained. It offers only an alternative that passes scratch, mip, sibling and decode checks. Recognized exact retail copies retain their exact-fit rule. The helper now receives enough bounded output space to return the actual optimal size on overflow; the old bounded miss discarded that size and could needlessly retry the same search in Python. No LZ algorithm or binary was replaced.

The real retry dialog carries the checked size. The supplied Studio worker catches the structured fit result and, on Try that, resubmits the same authored image, scope and pending master with that size. It defers submission until the first blocking worker finishes; otherwise the Studio's busy guard would discard the retry. Cancel and failed checks stage nothing. Both that proposed method and the Build list method run in offscreen Qt tests. The original/half/quarter chooser remains an explicit user choice; reduced art is still lossy.

### Growth route findings

**(a) In-place slack: insufficient.** The measured `15H0` IFF is 1,513,424 bytes with no trailing space and only 48 alignment bytes before the next archive entry. Bears is 1,498,832 bytes, no tail, 304 alignment bytes. TSETs and subsequent chunks are contiguous. Beta-68 refits fill their original spans to preserve overlap requirements; unused-looking compressed padding is not a new allocation. The full 4,323-entry / 16-pack census finds 1,216 bytes between the index table and first entry, a largest inter-entry gap of 2,032 bytes, and zero bytes after the final entry. [Allocation census](reports/b69_j1/allocation-census.json).

**(b) Larger allocation: isolated loader proof passes; archive/disc route remains unproved.** The full-size, 256-colour stream can be aligned to a 128,896-byte compressed body. Native `0x45280` calls `0x451D0`: the grown wrapper declares system 640, video 180,992, scratch 32; the allocator receives 181,664 and the read receives 128,896. The original scratch word at wrapper +0x14 is unchanged. `0x45100` and `0x4DC00` decode the stream, and all six native `0x450B0` texture descriptor callbacks relocate pointers correctly. Video bytes, pixel/palette pointers and memory guards match. The bound is eight million instructions and one second per native call. [Native growth receipt](reports/b69_j1/grown-loader.json).

Only allocator/I/O, resource registration's shell and a context-state query are stubbed in this grown-loader proof; it uses the pinned retail XBE. It does not run the archive manager or the GPU. No code at `0x451D0` was patched: the loader reads the updated declared sizes from the candidate wrapper.

A `vc_53450030/0` index entry is a 12-byte name/size/sector record for an entire IFF, not a pointer to an interior TSET ([`tools/nfl_outer.py`](tools/nfl_outer.py:19)). Moving only the TSET and changing that entry would point the package loader at an incomplete package. The grown full package needs another 70,464 bytes. There is no unallocated larger slot in the census; overwriting an occupied larger package would destroy another live asset. Appending a whole IFF requires updated entry/volume sizes and offsets and, if a volume grows, XDVDFS file extents.

The current writer refuses that operation at `bind_prepared_to_source`: source pack size/hash and `replacement_end <= pack_end` are mandatory. `verify_union` compares the existing, source-sized disc and insists all bytes outside approved spans remain identical. The build service also requires output size to equal source size. Relaxing those guards without implementing and proving archive/directory growth would not establish a safe route.

**No append-and-repoint or larger-slot disc `verify_union` proof was completed. No grown disc is claimed.** Fixed-span synthetic builds run the real `verify_union` and receipt checks; the grown proof ends at the isolated chunk loader. This is the precise reason “Larger equipment art (experimental)” is not offered, has no registry row, no preset, and no flag. The fit dialog and Build caption explain the limit and offer only checked fitting imports. Future archive work must prove package lookup, entry/volume/directory updates, every preserved entry and the grown disc round trip before enabling that option.

## 4. Bears Style 6: selector to field binding

maumau78: “Using shoe slot 10 the texture was replaced correctly” in Edit Player, then “shoe slot 10 / style 6 is not show in-game”. This is a negative field witness for beta 68 and remains unresolved.

**PROVED, bounded field path:** the new [native test](tests/mod_editor/test_b69_j1_native.py) reads Bears `05H0` catalog/package names, uses distinct HOME/AWAY/GLOBAL descriptors, executes cache fill and the actual field selector on both feet, and repeats both context-list load orders and both clean/mud states. Executable SHA-256: `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.

| Native location | Tested meaning |
|---|---|
| Player byte +0x0C; `0x8F752..0x8F792` | Stored value 5 in left bits 0..2 and right bits 3..5 means Style 6 for both feet. The field fragment reaches the real material binder. |
| `0x4EF7C0` style table | Style 6 selects row 89, shoes10, and relief index 22, bump_shoes7. |
| `0x4EEAF8` diffuse rows; `0x8E620` | Row 89's local-context flag reaches real cache fill. `0x8E5C0` selects shoes10 or shoes10_mud. |
| `0x8E580`, `0x449E0`, `0x42F50` | The selected team context HOME or AWAY is searched first. The real context-name walk and fallback walk execute. If HOME clean shoes10 is absent, the tested newest-first list returns AWAY's copy. GLOBAL is not unconditionally selected. |
| `0x8EF23..0x8EF4E` | Colour cache address is `0xB65428 + 4*(mud*192 + team*96 + row)`. EAX is the mud argument; the last stack argument is team. The beta-68 test's team/mud axes were mislabeled. |
| `0x8E3F0` | Each foot's selected colour descriptor is written to material +0x30. Both HOME and AWAY bindings remain distinct in both list orders. |
| `0x8E4B0` / `0xB65A28` | Relief cache uses `team*28 + bump_index`; the corrected existing native test retains the separate global relief assertions. |

Only the formatter `0x4A410` and per-context resource hash lookup `0x443D0` are doubles in the new field test. The hash lookup returns distinguishable descriptors for names verified in the Bears package; it does not recreate a whole gameplay resource session from disc. Thus this proves that shoes10 **can** be bound by the tested field path, rather than only by Edit Player. It does not prove which package/dirty state/cache contents maumau78's recorded play actually had.

The earlier Style 3/shoes09 selector proof remains narrower than the new Style 6 cache-fill test. The original beta-68 report is historical evidence, not a certificate for this change. The shipped changelog now clarifies its hand-populated cache fixture, the owned dialog describes the unresolved game report, and WIRING replaces both registry evidence/constraint rows and the old core help alias. No speculative XBE or roster reassignment is included. The global-row All teams rule for shoes01/02/03/04 is retained. Colour and global relief remain separate.

**PROVED sources of “looks bad”, not a proof of the navy field shoe:** the actual stand-in was compiled into Bears shoes10 through both reported modes. [Appearance measurements](reports/b69_j1/appearance.json):

| Mode | Encoded result | Measured colour loss |
|---|---|---|
| Palette-only | Retail 256x256 shared index shape, six mips, 94 palette entries; pixel offset stays 0 | Max channel difference 249, mean DeltaE76 9.196, 4,690 distinct colour merges. It cannot place the new logo's shape. |
| Own texture, 64x64 | Four regenerated mips, four colours, new pixel offset 93,568 | Max channel difference 106, mean DeltaE76 7.419, 1,587 distinct colour merges. Downsampling and quantization both discard detail. |

These statistics compare against the corresponding authored images, not against a rendered shoe. **HYPOTHESES requiring the player's actual build/session:** a different worn uniform/alternate, dirty versus clean texture, missing local name with fallback, stale loaded context, or roster/save selection. The native proof does not select among them or assert that colour quantization caused the dark navy screenshot.

## 5. Validation, integration and reporter retests

[Standalone commands/results](reports/b69_j1/test-results.md) and [machine-readable results](reports/b69_j1/test-results.json) contain all 21 test files, timings and full log links. **20 files pass, covering 187 cases.** The remaining export suite runs 13 cases and reports two skips and six errors (one from class setup) caused by missing `reports/assets/nfl2k5_player_portrait_compatibility.json` during catalog loading. Its failure is retained. The beta-68 audit's former portable-archive hydration path no longer exists. No test was weakened to hide this missing generated input. This is not a full packaged-release certification or a Windows-host run.

The native retail binding, retail round-trip and relief tests ran rather than skipping. New build, fit, legacy, timeline and offscreen wiring tests all pass. The third wiring test inserts the exact load hook into the current production session method, then uses a real unfit synthetic group to prove refusal and archive cleanup before session mutation. The beta-68 compile-cache and receipt-tampering suites pass. Registry structural validation with the two proposed rows substituted passes at 161 shared rows / 91 NFL 2K5 rows; file-reference checks are explicitly outside that structural run. **Zero rows added.** The research probe is not a runtime dependency or an allowlist addition.

Reproduce the nine-way fit table and grown-loader probe (metadata outputs only):

```sh
python3 tools/nfl2k5_b69_equipment_probe.py fit --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --art '/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-13/attachments/2k5-bugs_3f58becf_3.png' --output /tmp/j1-fit.json --set-selector 15H0
python3 tools/nfl2k5_b69_equipment_probe.py growth --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --art '/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-13/attachments/2k5-bugs_3f58becf_3.png' --output /tmp/j1-growth.json
python3 tools/nfl2k5_b69_equipment_probe.py appearance --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --art '/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-13/attachments/2k5-bugs_3f58becf_3.png' --output /tmp/j1-appearance.json --set-selector 05H0
```

The growth mode is the bounded `15H0` experiment. Python/Pillow and the repository's optional Unicorn native-test dependencies are required. No reporter PNG, retail span, pack, XBE or disc is distributed in these artifacts.

**Coach Edwards, after integration:**

1. Keep the old project, open it in beta 69 and confirm either a successful restore or an immediate inline refusal naming the shoe/glove and the required action. It must not start a build to discover an unfit restored group.
2. Review What this build includes. Import one new shoe or glove and confirm its rows move to the top while original project indices remain visible. Restore the old shoe records and build; an exact retail-matching record should be explicitly unchanged, not a failure.
3. If the volt art still refuses, save the full named message plus project/edit index, uniform selector, import mode and chosen size. The diagnostic must contain the actual reason and no `NFL2K5_BUILD_PHASE`. This is the missing evidence needed to identify his specific compilation failure.
4. Repeat a warm build and report elapsed time alongside his beta-68 “5 minutes or less” witness. Play the edited kit before calling appearance fixed.

**maumau78, after integration:**

1. Import the orange atlas as own artwork at 256 and 128. Record the exact package and arithmetic, accept Try that if offered, and check the resulting dimensions/colour report. Expect heavy loss at four colours; palette-only is suitable only when retaining the retail shape is intended.
2. For the field comparison, edit Bears **05H0 shoes10 and shoes10_mud**, then any away/alternate set actually used. Give clean and dirty variants unmistakably different, simple colours that both pass the fit check. Keep both player shoes at Style 6.
3. Start a fresh game loading the new disc/project result, record the actual HOME/AWAY/alternate kit and roster/save, and compare Edit Player with field shoes at kickoff and after the player becomes dirty. Repeat with Bears as away and with the opponent/load order changed. This distinguishes context, dirty-row and fallback hypotheses; it is not a claim that restarting fixes the issue.
4. Supply that comparison and the receipt/selected texture names if the shoe remains navy. A played negative is still a negative even when this bounded native test passes.

**Integrator:** apply the complete WIRING hooks, merge its Build caption with J2, hydrate the reviewed public metadata for the broader export/release gates, then repin and run the packaged checks. `python3 packaging/repin.py --apply` was run after pinned edits and again before commits. No pin was weakened. ASTRA_CONTEXT explicitly requests a cave-manifest regeneration after pinned-writer changes, so **regenerate it during integration**; no XBE bytes, REQUESTS, allocations or cave ownership changed here, and no reservation change is expected.

All retail access was read-only. Only small temporary synthetic discs/spans and metadata were written; no emulator, display, audio, network or full retail disc build was used. The root filesystem was about 82 GiB free initially and later 78 GiB; no large write was attempted at the below-80-GiB reading. There is no scratch retail disc to delete. A grown archive remains a research follow-up, not a released feature.

## Commit delivery

The shared worktree Git metadata is read-only, so the commit database is private at `/tmp/astra-b69-j1-git`, using the shared objects read-only and this worktree as its worktree. Commits use the requested branch and explicit file paths. `ASTRA_J1.bundle` is the integration deliverable; the shared worktree HEAD cannot be advanced from this sandbox. Starter briefs/context, the extracted symlink and private inputs are excluded.

```sh
git fetch /home/noah/2k-worktrees/astra-b69-j1/ASTRA_J1.bundle astra/b69-j1-equipment
# Inspect FETCH_HEAD; cherry-pick the commits after 922c009d into the integration branch.
```

The early implementation commit is `cc61e59d`. The remaining implementation/evidence commits and bundle verification are recorded with the final handoff. No push was performed.
