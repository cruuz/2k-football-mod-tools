# Beta 68 T2 equipment report

Delivery branch: `astra/b68-t2-equipment`. Base: `c8783a64406ce6b062a7b287173ecbe778f43df2`.

The implementation, tests, reporter changelog bullets and exact protected-file integration edits are complete. **Apply WIRING.md before release**: the running protected GUI still needs the scope combo/forwarding and the updated Bump Maps labels. The proposed dialog and Studio method have been executed offscreen in memory; the full proposed capability row passes the registry row schema. The core already refuses explicit per-team global imports.

Git's shared worktree metadata refused `index.lock` with `Read-only file system`. Delivery is therefore the authorized `ASTRA_T2.bundle`, containing a commit on the requested branch with explicit file paths. The starter ASTRA_BRIEF/ASTRA_CONTEXT/BETA68_TRIAGE files and extracted symlink are excluded. Fetch it from this worktree and integrate its branch, then apply the protected wiring:

```sh
git fetch /home/noah/2k-worktrees/astra-b68-t2/ASTRA_T2.bundle astra/b68-t2-equipment
# Review FETCH_HEAD and cherry-pick its commit into the integration branch.
```

No network, emulator, GUI display, audio or full disc build was used. All retail inputs were opened read-only. Only small disposable spans/artwork and synthetic packs were written for proofs. Initial `df -h /` showed 82 GiB free, already below the handoff's 100 GiB large-write floor; no large writes or scratch discs were attempted. No retail payload is in the commit. T1's `mod_editor/core/nfl2k5_equipment_lz.py` is untouched.

## Evidence read

Read ASTRA_CONTEXT and triage rows 6, 10, 11, 12 and 13. Viewed the actual saved `attachments/2k5-bugs_0f742bb2_2.png` maroon smear, `attachments/2k5-bugs_0dd08a0f_3.png` white-shoe relief, and `shots/2k5-bugs_000.png`, `_001.png`, `_004.png`, `_005.png`, `_006.png` under `/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-12/`. These are reporter observations of older builds, not witnesses of this change. Their source PNG, chosen import mode and build receipt were not supplied; the screenshots cannot isolate which conversion produced their smear.

- Coach Edwards: “Only thing is that the designer socks (no the solids) are still coming through blurry in game.”
- maumau78: “texture was imported as 64x64 in theory specific for Giants but reality is also other teams shares this texture”.
- maumau78: “even If i select to import to specific team will be replaced as shared one for all the teams”.
- maumau78: “this texture was just exported then imported into another slot but still glitched in-game”.
- maumau78: “there's be a shoe normal texture to edit too” and “here you can see that a under layer is used by the game...look like a normal map but I can be wrong TBH”.

## PROVED: designed socks

`supports_own_texture` now admits the catalog's chunk-4 `socks00` and `socks00_mud` rows. The existing import default and dialog predicate consequently offer full-size own artwork for socks. The writer uses the same explicit original/half/quarter dimensions, aligned private indices, straight base RGBA, coverage-filtered distance images, fixed compressed span and sibling guards as shoes. No mandatory bump rewrite is added.

The census now validates all 634 sock spans as well as the existing 1,902 glove/shoe spans, totaling 2,536 complete pins. Every old pin is unchanged. New catalog SHA-256: `1057ef17a6680edf64d83ce563f168e5c6850c63c7b212423d70486838591295`.

The real 28H0 sock proof targets `tset:3850:4:0:socks00`, retains all four mips (64, 32, 16, 8), and decodes every imported RGBA pixel exactly, including invisible RGB at the base. It closes/reopens the saved span, checks guards, replays idempotently, and confirms the original source and dirty sibling are untouched.

| Measurement | Result |
|---|---|
| Base differing pixels | 0 |
| Compressed stored body | 6,672 bytes, unchanged |
| Encoded stream | 6,658 bytes |
| Wrapper scratch +0x14 | 16 bytes, unchanged |
| Video allocation | 7,552 to 13,056 bytes, +5,504 |
| Source span SHA-256 | `52029ea48e15dd5efc95020a5597b2be05f0d6d79247436d30d4b884f4e2fee7` |
| Built span SHA-256 | `b32add35daa5e3de88b1b5c171088e6d837049a60f570cfffe302f46bff74749` |
| Authored/decoded base RGBA SHA-256 | `a564fc810b0753f394aaa7585538de6acd6a04190860428522614adec8a5405e` |

`bump_sock` is a separate named TXTR, not part of the chunk-4 diffuse TSET or its shared indices. Its existing material type is 0xF; the pinned strength branch at `0x0008E51F` pushes zero. Diffuse design preservation needs no change to that independently bound fabric map. The retail test locates and checks the separate sock bump span. **This proves the data separation; it does not prove that zero detail scale disables every shading effect.** If Coach Edwards wants different ribbing/fabric relief, the existing Bump Maps sock slot is a separate authoring choice.

## PROVED: honest team scope and the existing local shoe route

`equipment_import_scope` is shared between the proposed dialog and `stage_equipment_import`. Every global row, including its mud name, offers only `all-teams`. Explicit `selected-package`, `per-team` or a team-name scope is refused before artwork reads or session mutation, with this exact sentence:

> All teams share this style because the game reads its texture from the most recently loaded uniform package.

Existing whole-consumer staging, combined preflight, Undo, restore, shared-span cache and home-current/away package selection remain covered by the 19-test consumer suite. The usual global variant reaches 402 sampled packages; a selected otherwise-unsampled alternate is also retained.

The route for team-specific **colour** is already present in the retail engine and roster editor. No speculative XBE patch or automatic player reassignment is needed. Use either local row in each HOME/AWAY/alternate uniform package the team will wear, then set each player's left and right shoe to its corresponding style using the existing roster editor. This only offers two local colour choices; it does not make the four global styles local or make relief per-team.

| Edit Player style | Stored value | Binding row/name | Colour scope | Relief table index/name |
|---|---:|---|---|---|
| Style 1 | 0 | 84 / shoes01 | global | 16 / bump_shoes1 |
| Style 2 | 1 | 85 / shoes04 | global | 19 / bump_shoes4 |
| Style 3 | 2 | 86 / shoes09 | selected package | 22 / bump_shoes7 |
| Style 4 | 3 | 87 / shoes02 | global | 17 / bump_shoes2 |
| Style 5 | 4 | 88 / shoes03 | global | 18 / bump_shoes3 |
| Style 6 | 5 | 89 / shoes10 | selected package | 22 / bump_shoes7 |
| Taped | 6 | 90 / shoes_taped | global resource | 22 / bump_shoes7 |

Pinned executable SHA-256: `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`. `test_nfl2k5_equipment_consumers.py` pins the row table, style table, loader order, lookup and selector ranges. The native suite additionally executes:

- Existing `PlayerRecord.set/encode` changes only record byte +0x0C, preserving bits 6/7. At `0x0008F752..0x0008F768`, the actual x86 masks extract left bits 0..2 and right bits 3..5; the fixture selects stored values 2 and 5.
- `0x004EF7C0` pairs each style with a diffuse row and a relief index. `0x004EEAF8` contains the 96 diffuse binding rows and context flags. Row 86/89 flags are 1; row 91 socks is also local.
- `FUN_0008E580` looks in `HOME`/`AWAY` for flag 1 and falls back to global only if absent. Flag 0 goes directly to global. `FUN_000449E0` is the named-resource lookup. Only that resource manager is stubbed in the bounded fixture, returning distinct package descriptors and a shared relief descriptor.
- `FUN_0008EF20` selects the appropriate cache row at `0x00B65428`; actual `FUN_0008E3F0` stores diffuse at material +0x30. `FUN_0008E4B0` and `FUN_000FD860` store the selected relief at +0x38 and the separate specular input at +0x34. Both teams' Style 3/6 colour descriptors remain distinct; their relief stays shared. The SSE strength conversion also executes natively.
- Existing tests execute `0x000451D0` wrapper allocation, `0x000450B0` descriptor relocation, `0x00031FA0` GPU command construction, and the bounded in-place LZ decoder. Native function fixtures stop at a checked return within 20,000 instructions / one second, with a 500,000-instruction cap for the separate decoder test; the bit-selector fragment has a 16-instruction cap.

Load order evidence remains `0x0006327A` HOME then `0x00063298` AWAY; `0x00043DB0` inserts newest context first; front-end preview package loading is `0x00091940`.

A broader feature making Styles 1/2/4/5 per-team is **not implemented**. Its first candidate sites are context-flag words `0x004EED9C`, `0x004EEDA4`, `0x004EEDB4`, `0x004EEDBC`, followed by `0x0008E580`, cache fill `0x0008E620` and binder `0x0008EF20`. A follow-up must pin/execute clean and all mud quadrants, both load orders, missing-package fallback, Edit Player, LOD and roster/save transport before considering such a writer. Relief would still need separate ownership research. No row flag, loader or executable byte was patched here.

## PROVED: the shoe round trip

**Test first:** the new retail Export PNG -> unchanged import -> package decode test was run before the fix. Both same-slot and other-slot own imports failed with `This equipment art cannot fit inside the retail 54,688-byte TSET`; one test, two errors, 384.924 seconds. The base exported PNG already matched retail. The default own path needlessly built a private filtered mip chain; fitting it could force refusal or colour reduction, and selecting 64x64 deliberately discards the two highest mip levels. Removing the explicit scale shift would break the chosen-size contract, so it stays.

The fix preserves a recognized retail source's actual palette and entire index/mip chain. Fresh exports carry a small portable `npRS` PNG hint containing only the source asset ID and base RGBA digest. The compiler independently loads the catalog target, checks the full source span pin and compares the base pixels. A forged hint cannot provide bytes; stale hints are ignored. The project-only `npTC` import choice still names its target and is stripped for export, while the portable source survives export, consumer copies, save/reopen and Undo. A matching old PNG without the hint is also recognized against unambiguous retail rows in the destination TSET.

An identical shared chain is reused and only the selected palette changes. A same-slot no-op returns the **entire original compressed span**, including unused retail tail bytes. An incompatible chain is appended exactly if it fits; otherwise it refuses without reducing the retail palette. Synthetic tests cover this append/refusal branch. The private retail proof exports 28H0 shoes01 and imports into shoes01 and shoes09, with and without the portable hint: all six mip RGBA byte strings and all 1,024 palette bytes match the source; every sibling, allocation and wrapper remains exact. This does not promise arbitrary incompatible retail copies fit every fixed slot.

When an import loses detail, the reason is now explicit:

- Half/quarter size deliberately drops top levels; the result names the original and encoded dimensions.
- New own artwork regenerates distance images from its base. P8 allows 256 palette entries, and the compressed slot may force further colour merges; the existing measured colour/coverage report gives the reason and changed colours.
- Palette-only mode projects onto the retail shared shape and cannot add a design.
- An old exported PNG with no origin hint and no recognizable destination-row match cannot reconstruct unknown original lower mips; it follows the selected ordinary import mode. Export fresh to preserve the portable source.
- The GUI fitter can resize a source image that is not the slot's size; that remains its existing explicit fit step. A correct-size RGBA export is returned untouched by `_fit_for_slot`.

No data test proves the cause of every pixel in maumau78's screenshot or proves the in-game smear has disappeared.

## PROVED: shoe relief exists and is bound

`GLOBAL.IFF` is discovered from the entry-table CRC32 name ID `0x8EE9EEED`; in the private retail index it is outer 3, pack 0. Seven independent TXTRs are chunks 194..200, named `bump_shoes1`..`bump_shoes7`. Each is swizzled P8, 128x128, five levels (128, 64, 32, 16, 8), system 128 bytes, video 22,848 bytes, palette offset 21,824. Full source span hashes are pinned in `test_nfl2k5_shoe_relief.py`. I also decoded and viewed bump_shoes1 privately: it contains the shoe's raised contours and stitching in a normal-map atlas; the temporary PNG was deleted.

The relief name table begins at `0x004EEDF8`; the seven shoe entries start at `0x004EEE38`. The cache at `0x00B65A28` is filled by `0x0008E6D4..0x0008E715`. The native tests follow the style's relief index through the real material binder to +0x38. The normal map is distinct from diffuse +0x30 and specular input +0x34. A standalone `specularmap` also exists at global chunk 90, but no speculative specular editor or identity claim for that pointer is added. The mapped relief is sufficient to answer this report.

Bump Maps now has the writer support for all seven shoe maps, with the existing dynamic package/slot adapter. Original-dimension imports use exact P8 colours across every generated mip and refuse more than 256 colours; there is no lossy normal-map quantization fallback. Recompression is filled back to the retail scratch allowance with `nfl_vc_lz_fill`, keeping wrapper +0x14 exact. This same scratch preservation now applies to the four existing uniform bump maps. Preview compiles before offering a write. The build reparses every mip, write readback is exact, and `verify_write` checks every distance image as well as the base. A synthetic production import into a separate pack copy proves that corrupting only a lower mip makes verification fail while the base still passes.

All seven retail relief spans pass exact authored-pattern decode after close/reopen, with original headers, unrelated bytes and sources preserved. Styles 1/2/4/5 select maps 1/4/2/3; Styles 3/6 and taped select map 7. Maps 5/6 exist but are not selected by this reviewed style table. Do not describe their mere presence as a usable style. Relief is league-wide, including for the package-local colour rows.

## Validation

Every test file below was run standalone, with the exact invocation pattern:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/<file-from-table>
```

| File | Tests | Elapsed | Output |
|---|---:|---:|---|
| `test_nfl2k5_equipment_texture_chain.py` | 19 | 4.212 s | OK |
| `test_nfl2k5_equipment_import.py` | 13 | 0.914 s | OK |
| `test_nfl2k5_equipment_consumers.py` | 19 | 30.030 s | OK |
| `test_nfl2k5_equipment_retail_roundtrip.py` | 2 | 16.817 s | OK |
| `test_nfl2k5_equipment_texture_native.py` | 7 | 0.340 s | OK |
| `test_nfl2k5_shoe_relief.py` | 5 | 5.183 s | OK |
| `test_nfl2k5_bump_texture_writer.py` | 25 | 6.649 s | OK |
| `test_nfl2k5_equipment_scope_wiring.py` | 3 | 1.829 s | OK |
| `test_nfl2k5_equipment_import_wiring.py` | 6 | 0.664 s | OK |
| `test_nfl2k5_extended_visuals.py` | 9 | 0.150 s | OK |
| `test_studio_session.py` | 18 | 0.535 s | OK |
| `test_nfl2k5_bump_strength.py` | 11 | 0.012 s | OK (skipped=1) |
| `test_providers.py` | 33 | 3.855 s | OK |
| `test_provider_integrity.py` | 7 | 8.502 s | OK |

Total: 177 tests across these 14 complete suites, one skip, zero failures. The skip is the pre-existing optional retail bump-strength fixture lookup; the separate pinned native equipment tests all ran.

The older aggregate export suite was also run in full:

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_2k5_uniform_equipment_export.py
```

Output: `Ran 13 tests in 0.791s`, `FAILED (errors=6, skipped=2)`. Root cause is `mod_editor/core/nfl2k5_extended_visual_catalog.py:1113` -> `metadata_cache.source_key`, opening absent `reports/assets/nfl2k5_player_portrait_compatibility.json`. That pre-existing generated report is not present in this worktree. No test was weakened or made green by hiding this error. The new retail round-trip suite uses the actual equipment exporter directly without requiring unrelated portrait/face catalogs and passes. Claude must supply the existing generated reports and rerun the aggregate suite after applying the protected GUI wiring.

Additional commands actually run:

```sh
PYTHONPATH=. python3 tools/nfl2k5_equipment_chain_census.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --output /tmp/b68-t2-chain-pins.json
PYTHONPATH=. python3 tests/fixtures/prove_equipment_texture_chain.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --texture socks00 --scale 1 --output /tmp/b68-t2-sock-proof.json
python3 packaging/repin.py --apply
python3 packaging/repin.py --include-tests
git diff --check
```

Census output: 2,536 rows; the checked-in JSON retains the existing indentation. Sock proof output: `all_levels_exact: true`, 6,658 encoded / 6,672 stored. The final include-tests dry run identified the test's one expected data digest, which was updated to the new census hash without relaxing the pin. Provider integrity then passed all seven tests. Final bundle preparation repeats `python3 packaging/repin.py --apply --include-tests` immediately before its explicit-path commit and verifies the resulting Git bundle.

Repin changes are four generated entries in `mod_editor/core/providers.py` and the facade digest in `packaging/check_2k5_mod_studio_runtime.py`, plus the matching exact test expectation. No release-check logic changed. **These writers edit archive data, not the XBE. No cave manifest regeneration is needed for T2.** No cave, runtime-data placement, allocator or game-code write site is introduced. The imported private chain and the new relief edit remain EXPERIMENTAL / UNWITNESSED; no new build patch is enabled in BASIC, ADVANCED or EXPERIMENTAL presets.

## UNWITNESSED: precise retest requests

**Coach Edwards:** import the same designed sock into socks00 at original 64x64 with own texture enabled, build, and inspect the logo/stripe edges at close range and as the player/camera moves away. Check the clean sock and separately imported dirty sock, both teams and home/away uniforms. Check the solid sock still looks correct and that fabric ribbing remains the original unless bump_sock was deliberately edited. Send the import receipt with encoded dimensions/colour merges and close/distant images. No automatic normal map was generated from his design.

**maumau78:** first export a retail shoe again, import unchanged at original size into the same slot and shoes09, build, and compare the toe, heel, side stripe, maroon/grey/black colours and distance transitions against the original. Select Style 3 on the copied player's left and right shoes. Then use visibly different shoes09 or shoes10 colour artwork in two teams' actual uniform packages and play them against each other with the home/away order swapped. They should retain distinct local colours; Styles 1/2/4/5 should display the All teams scope and stay shared. Compare an explicitly selected 64x64 copy separately to distinguish expected detail loss.

For his white Nike shoe, export the mapped global relief and test a neutral flat template in bump_shoes1 when wearing Style 1, or bump_shoes7 when wearing Style 3/6. Look specifically for the old raised logo/stripe and stitching beneath the new flat colour image, close up and under changing light; restore the original relief for an A/B comparison. Map 7 changes both local styles and both teams. Do not expect a team-local colour import to change that shared relief. Send the style number, diffuse slot, relief slot, chosen dimensions and import receipt.

Remaining release work is exactly the protected WIRING integration, the generated-report-dependent aggregate export rerun, and those in-game witnesses. No GPU appearance, game memory residency, full XISO build, render quality or played stability is claimed from these bounded proofs.
