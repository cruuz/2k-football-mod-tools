PROVED OFFLINE: FB2 delivers shared u4 fan-banner wiring, residual sponsor art, tests, review sheets and an event-slot memo against candidate E integration head `c1a8a769580afefcb8d7bb6c6e5391f83faa9f8e`. Work is isolated in `/media/noah/Storage/.b76-research/fb/work`, using `fb/private.git`. The supplied b76-m2 checkout, other worktrees and game files were not modified.

PROVED OFFLINE: the model writers now use the selected venue-art folder's existing `banner_home_player`, `banner_home_team` and `banner_away_team` items through [one shared helper](../mod_editor/core/nfl2k5_model_fan_art.py). The evidence uses `/media/noah/Storage/.b76-research/main/freeze/candC/root_final_v2`. u4's existing manifest checks, native PNGs, masters, rectangles, weather transfer, mip generation and P8 quantization are reused. There is no new fan art, chant authoring, roster generator or copied per-model banner collection.

PROVED OFFLINE: [the contact-sheet index](review/model_banners.html) contains retail against u4 for all 39 retained banner textures. [The first sheet](review/model_banners_00.png) shows Arizona and Atlanta. [fan_inventory.json](evidence/fan_inventory.json) records each native PNG hash, master hash, size and material.

| Evidence | Slot and team | Owner module with the shared texture step |
| --- | --- | --- |
| PROVED OFFLINE | s00 ARI | `nfl2k5_state_farm_model.py` |
| PROVED OFFLINE | s01 ATL | `nfl2k5_mercedes_benz_model.py` |
| PROVED OFFLINE | s03 BUF | `nfl2k5_highmark_model.py` |
| PROVED OFFLINE | s07 DAL | `nfl2k5_att_model.py` |
| PROVED OFFLINE | s10 GB | `nfl2k5_lambeau_model.py` |
| PROVED OFFLINE | s11 IND | `nfl2k5_lucas_oil_model.py` |
| PROVED OFFLINE | s12 JAX | `nfl2k5_everbank_model.py` |
| PROVED OFFLINE | s14 MIA | `nfl2k5_hard_rock_model.py` |
| PROVED OFFLINE | s15 MIN | `nfl2k5_usbank_model.py` |
| PROVED OFFLINE | s20 LV | `nfl2k5_allegiant_model.py` |
| PROVED OFFLINE | s23 LAR and s24 LAC | `nfl2k5_sofi_model.py` |
| PROVED OFFLINE | s25 SF | `nfl2k5_levis_model.py` |

PROVED OFFLINE: the owner-built day scenes retain all three fan materials in those 13 venues. Lambeau and Allegiant therefore join the eleven venues named in the brief. Gillette's generated scene retains none: the retail fan group is outside its keep filter. MetLife's explicit shape keep set removes its retail field banners and then compacts unused materials; neither s18 nor s19 needs a fan edit. Those two owner modules are unchanged. SoFi's neutral s40 has no team-art manifest and is unchanged by the fan helper. The special-slot identities remain a design decision.

PROVED OFFLINE: the texture step runs after the owner compiles its model, before archive writes. Only `apply_to_image`, `bundle_state` and `image_status` change in each affected owner module. Source comparison proves every geometry, camera, model compiler and base texture-generator function is identical to E. SoFi additionally receives the selected art root from `mod_build.py`. No geometry constants, filters, vertices, UVs, materials, camera tables or base model pin files change. [integration_pins.json](evidence/integration_pins.json) records the function and pin checks.

PROVED OFFLINE: [prove_fans.py](prove_fans.py) applies the production helper to three pinned model bundles in an in-memory image. Every changed banner allocation equals the independent u4 venue painter byte for byte, including every mip index and the full palette. The mask comparison preserves every other decoded byte, including all system/geometry bytes. The 32-byte scene wrapper, bytes outside the compressed stadium span and untouched image entries also match exactly. Compression bytes inside the changed stadium span necessarily differ; no claim is made that those bytes can stay identical while changing their decoded textures.

| Evidence | In-memory model bundle | Banner allocations equal u4 | Other decoded stadium bytes unchanged |
| --- | --- | --- | --- |
| PROVED OFFLINE | s00dd.iff, State Farm | 3, totaling 90,368 bytes | 1,382,912 |
| PROVED OFFLINE | s03dd.iff, Highmark | 3, totaling 90,368 bytes | 1,427,456 |
| PROVED OFFLINE | s23dd.iff, SoFi Rams | 3, totaling 90,368 bytes | 1,616,256 |

PROVED OFFLINE: [fan_proof.json](evidence/fan_proof.json) contains the before/after hashes and per-texture proofs. [fan_variant_selectors.json](evidence/fan_variant_selectors.json) checks 351 exact-name P8 selectors across all 117 time/weather bundles against sn's descriptor-verified ledger. This is a selector audit for every variant; the full compressed-image equality proof covers the three bundles above. Appearance in a running game is INFERRED, not witnessed.

PROVED OFFLINE: [SPONSOR_AUDIT.md](SPONSOR_AUDIT.md) lists every residual atlas, old brand, replacement and native size. Nine home-atlas candidates from the previous prep were already repainted by u4 and have been excluded. The actual home residuals are Chicago's two small ESPN publishing cells and the top of Cincinnati's Reebok vector left above u4's rectangle. [This sheet](review/home_sponsors_E_before_after.png) compares E's u4 composition with the residual-only result. Chicago's tiny publishing sublabels have an INFERRED transcription, identified explicitly in the audit; both use the approved ESPN replacement.

PROVED OFFLINE: the catalog contains 60 native P8-target items and 60 four-times masters: two home atlases plus 58 sponsor items across s31, s36, s39, s41, s42, s43, s44, s45, s48 and s50 through s59. The 19 corporate sheets reproduce u4's approved league sheet pixel for pixel. Other panels use u4's approved type policy and installed Roboto fonts. All exported pixels outside approved rectangles are clear. Current-brand panels remain under those masks; normal whole-texture P8 quantization can slightly alter their colors. The ten board-kit venues have no fb2 item.

PROVED OFFLINE: [sponsor_proof.json](evidence/sponsor_proof.json) checks all 60 changed allocations in the 21 affected dry-day stadium scenes and verifies all nine source bundle hashes for each slot. Every other decoded byte is unchanged relative to the u4 baseline. Complete compressed refits and read-back checks for Chicago and s31 preserve every byte outside the stadium span, including all event field bytes. [The sponsor review gallery](review/sponsors/index.html) shows raw retail against the supplement alone; use the separate home sheet for the complete layered Chicago/Cincinnati result. No event-field art or executable routing is changed.

DESIGN: [EVENT_SLOTS.md](EVENT_SLOTS.md) is the requested memo. It documents the two Pro Bowl selectors, the franchise Super Bowl rotation and the Create a Team route. It proposes plain type with no marks, including an explicit literal 2026 exhibition set and a more durable yearless option for rotating franchise slots. Main decides.

PROVED OFFLINE: the memo identifies a source-level conflict in E: season zero redirects to s44, while the SoFi neutral LXI model occupies s40. The later retail rotation is s42, s43, s41, s44, then s45 for every season index at least five. E's 18-week patch skips the scheduled Pro Bowl record. Executable bytes, disassembly and source references are in the memo's evidence. Actual Quick Game menus and the final candidate executable were not run or inspected; their behavior is INFERRED where stated in the memo.

PROVED OFFLINE: 97 distinct focused tests passed: eight final fan/receipt tests, four final sponsor/catalog tests, 18 venue-art tests and 67 existing owner contract tests. These cover all 12 status readers, unknown-parent/tampered-span rejection, optional art, neutral s40, receipt survival through the compactor's sidecar list, sprite hashes/sizes/transparency, exclusions, source pins, registry pins and existing composition contracts. Logs: [initial suites](evidence/tests_fb2.log), [final fan suite](evidence/tests_fan_final.log), [final catalog suite](evidence/tests_catalog_final.log). The real model and sponsor proofs above are additional checks. No full build or xemu run was performed.

PROVED OFFLINE: [PIN_LIST.md](PIN_LIST.md) lists every affected model, unchanged model pin file, changed source fingerprint, registry pin addition and packaging hash change. No model pin is replaced. The venue-art registry keeps its four hashes and adds the sponsor design and special-slot table hashes. Composed model span pins live in the model receipt and are also retained inside the already-exported `.venues-2026.json` sidecar. The receipt checks its pinned parent, offset, length and resulting bytes, so copying a model receipt onto other bytes does not accept them.

DESIGN: integrate the whole private commit, including the shared helpers, twelve owner texture/verification hooks, SoFi art-root argument, venue-art supplement, catalog, packaging and tests. Regenerate the observed-build cave reservation manifest afterward: 14 fingerprinted sources change, and its generator performs the full build forbidden to this job. The exact stale fingerprints are listed in [cave_source_changes_fb2.json](evidence/cave_source_changes_fb2.json). Do not manually repin a historical manifest. Preserve the venue-art sidecar beside exported discs for composed-model recognition.

PROVED OFFLINE: every long run used one process with a 1,843,200 KiB virtual-memory ceiling and numerical-library thread limits of one. The fan proof peaked at 773,492 KiB RSS and the sponsor proof at 823,132 KiB. Work and artifacts remain below 1 GB under the fb area; the observed nvme free space stayed above 100 GB. No full disc build, xemu, push or tag was used. The commit uses pathspecs and the requested Astra co-author trailer. Delivery is `fb2.bundle`, verified against its E prerequisite and fetched into a separate private verification repository.

PROVED OFFLINE: 15-line delivery summary follows.
1. PROVED OFFLINE: u4's existing fan art is reused directly from the selected art root.
2. PROVED OFFLINE: one helper serves twelve model writers and thirteen club venues.
3. PROVED OFFLINE: thirty-nine retained fan textures receive the same u4 pipeline.
4. PROVED OFFLINE: Lambeau and Allegiant are included after checking their retained props.
5. PROVED OFFLINE: Gillette and MetLife have no retained fan props requiring this edit.
6. PROVED OFFLINE: three in-memory model bundles match u4's complete banner allocations.
7. PROVED OFFLINE: their geometry and every other decoded byte remain unchanged.
8. PROVED OFFLINE: all 351 fan selectors resolve across 117 time/weather bundles.
9. PROVED OFFLINE: sixty residual sponsor items cover two home atlases and nineteen special slots.
10. PROVED OFFLINE: nine already-replaced home candidates and all ten board-kit venues are excluded.
11. PROVED OFFLINE: event field logos, schedules and executable routing are unchanged.
12. DESIGN: main chooses the plain-type event identities and resolves the s44/s40 conflict.
13. PROVED OFFLINE: ninety-seven focused tests pass, plus the model and sponsor byte proofs.
14. PROVED OFFLINE: model pins stay unchanged; receipt pins survive the supported compaction path.
15. DESIGN: main regenerates the cave manifest after integrating the verified private bundle.
ASTRA_DONE
