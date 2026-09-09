# beta-63.1 hotfix: jersey-digit texture budget refused the whole disc

2026-09-09. Branch `astra/hf63-digits`, base tag `beta-63` (9c17c538).
Commit `ef1c6d74` (fix + tests + pins), docs commit follows.
**EXPERIMENTAL / UNWITNESSED in-game.** No xemu, no display, no audio, no
push. Qt ran offscreen. Retail inputs under `/media/noah/Storage/for codex
1.0/` were read only; nothing retail was copied into the repo, tests or
fixtures. Protected files were not edited; the two optional GUI touches are in
`WIRING.md`.

## 1. Reproduction

Reported (Coach Edwards, #2k5-bugs 2026-09-09 09:51 and 10:16, beta 63 on
Windows, screenshots `discord-dump-2026-09-09/shots/2k5-bugs_002.png` and
`_005.png`): Baltimore Ravens kit exported ("Whole kit (39 parts per uniform)
... 45 equipment textures"), edited, imported; the Uniforms page shows
"Jersey Digit 1 ... 7  64x64  Modified"; **Make disc** fails with

    Nfl2k5BuildError: The modded XISO could not be built. live_number_nameplate
    (asset_code=02, side=H, variant=0, family=arm): Digit artwork cannot fit its
    896-byte texture slot without dropping below the 16-colour quality budget. ...

`02H0` is the Ravens HOME set (`reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json`);
its digit **1** slots are the tight ones: `02H0:arm_digit:1` = resource `an49`,
`stored_size` 896, retail VC-LZ stream 895 bytes, 64x64 P8 with 4 mips (5440
index bytes + 1024 palette bytes to fit in 896), `02H0:jersey_digit:1` = 896
bytes too. Every other digit of the set has 2,592-3,296 bytes.

Measured with the real writer against the retail index
(`tools/nfl_live_numbers_nameplate_png_import.build_import`, scratch scripts,
not committed):

| input for `02H0:arm_digit:1`                                   | outcome                |
|----------------------------------------------------------------|------------------------|
| retail export as-is                                            | fits, 890 / 896 bytes  |
| hidden RGB under alpha 0 zeroed / whitened                     | fits, 890              |
| Pillow re-save (bytes differ, pixels equal)                    | pixel-equal, skipped   |
| +1 on R of every opaque texel, exact recolour, gamma 1.02      | fits, 886-896          |
| ±1 noise on visible RGB only (alpha untouched)                 | fits at the 16-colour tier, 665 |
| **±1 noise on visible RGBA (alpha dithered too)**              | **the reported error** |
| bilinear 64->65->64, Lanczos 64->62->64, 64->128->64           | fit at 16-32 colours   |

The retail digit itself has only six bytes of slack in its slot, so the
ordinary "edited in an editor and saved" drift is enough to fail. Retail uses
63 palette entries here; the writer's ladder 256/128/64/32/16 overflows at
every tier for the noisy input. An 8-colour version would fit (584 bytes) but
the 16-colour floor is the r64 quality budget the writer deliberately refuses
to go below, and 8 colours would drop the outline; "the slot's real palette
size" (63) is above the floor, so that fallback is already covered by the
ladder. "Down-sample to the slot's native size" is already done upstream: the
catalog reads each digit's authored size from the compatibility report
(`nfl2k5_uniform_catalog._digit_dimensions_for`), the Team Kit and the
number-sheet splitter deliver exactly that size, and `validate_replacement`
refuses any other. So for this slot there is no honest lower tier left; the
correct outcome is to keep the retail digit for that ONE slot and say so.

The regression test `BackendKeepsRetailTests` reproduces the failure through
the real backend (`prepare_project` with the pinned index, inventory and
report): before the fix it raised exactly

    nfl2k5_visual_mod_project.ProjectError: live_number_nameplate (asset_code=02,
    side=H, variant=0, family=arm): Digit artwork cannot fit its 896-byte texture
    slot without dropping below the 16-colour quality budget. Use flat fill and
    outline colours, remove noise or extra edge detail, and preview again. No
    lower-quality texture was accepted.

and `KitRoundTripDigitsTests.test_colour_managed_resave_noise_is_not_an_edit_of_a_digit`
showed the round trip staging all 30 digits (`Imported (30): 02H0: Jersey
Digits / Jersey Digit 0 (replaced source) ...`).

## 2. Root causes (beta-63 line numbers)

1. **Team Kit import staged noise as an edit.**
   `mod_editor/studio/uniform_bundle.py:911` — `if supplied_digest ==
   baseline_rgba:` is an exact decoded-RGBA comparison; anything else falls to
   `:926` `"imported"`. A colour-managed re-save changes most visible texels by
   one step, so every digit became a "Modified" 64x64 that later could not fit.
   (Byte-changed but pixel-equal PNGs were already skipped; verified by
   `test_reencoded_but_pixel_equal_digits_stage_nothing`.)
2. **The compile path turned the quality-budget overflow into a fatal build error.**
   `tools/nfl_tset_png_import.py:612` raised a plain `TxtrError` after the
   256..16 ladder overflowed (the digit writer asks for
   `minimum_palette_limit=16` at `tools/nfl_live_numbers_nameplate_png_import.py:403`,
   calls the ladder at `:440`). `tools/nfl2k5_visual_mod_project.py:3693`
   (`with _naming_the_failing_edit(edit):`) re-raised it as `ProjectError`
   (`:2529`), `prepare_project` had no per-slot fallback, and
   `mod_editor/core/nfl2k5_build_service.py:1265` turned the non-zero backend
   exit into "The modded XISO could not be built." Two side issues:
   `:2487` `_EDIT_COORDINATES` omitted `digit`, so the error could not even
   name which digit; `:4439` refused a project with no changed bytes, which a
   kept-retail-only project would be; `:5171` fixed the manifest key set.
   `mod_editor/core/nfl2k5_digit_preview.py:180` refused the whole sheet
   preview on the same error.

## 3. The fix (commit `ef1c6d74`)

- `tools/nfl_tset_png_import.py`: `class QualityBudgetError(TxtrError)`;
  both terminal "cannot fit" raises use it (messages unchanged). Still a
  `TxtrError`, so every existing `assertRaises(TxtrError, ...)` holds.
- `tools/nfl2k5_visual_mod_project.py`: `PreparedProject.kept_retail`;
  `kept_retail_record()` builds a deterministic row (selector, asset_code,
  side, variant, family, digit, stored_size, input_sha256, reason, message)
  only when the `ProjectError.__cause__` is a `QualityBudgetError` and the
  edit is a live jersey/helmet/arm digit; `prepare_project` records the row,
  releases the attempt's private input copy (`ownership.cleanup_owned`) so
  span orders stay contiguous, and continues; `bind_prepared_to_source`
  accepts a project whose only edits kept retail; `build()` writes
  `kept_retail` into the manifest, `read_build_manifest` accepts the optional
  key (old manifests still verify) and `verify()` requires the reconstructed
  rows to equal the manifest's; `_EDIT_COORDINATES` gains `digit`; the
  BUILD_PASS line prints `kept_retail=N`. Any other importer failure (corrupt
  PNG, changed report, codec fault) still raises as before.
- `mod_editor/core/nfl2k5_build_service.py`: `BuildResult.kept_retail`
  (validated rows from the verified manifest) and `BuildResult.message`, which
  the studio's `_result_message()` already prefers, so the status bar reads
  "Build complete — X is ready for xemu. Kept retail for 1 uniform slot: arm
  digit 1 (02H0): kept retail: could not fit its 896-byte texture slot at the
  16-colour quality budget; the retail digit was kept and the rest of the
  project was built." Empty message = unchanged wording for ordinary builds.
- `mod_editor/core/build_feedback.py`: `completion()` appends the rows from the
  `shared_project` step to the Build & Share completion dialog/status.
- `mod_editor/studio/facade.py`: `last_build_kept_retail` (rows + catalog
  `asset_id`) and `kept_retail_asset_ids` for the Uniforms page (see WIRING.md).
- `mod_editor/core/nfl2k5_digit_preview.py`: `preview_digit_sheet` shows the
  RETAIL texture for an unfit slot with a `kept_retail` receipt and the note
  "Digit N: kept retail: could not fit its ...-byte texture slot ..." — the
  same outcome the build produces.
- `mod_editor/studio/uniform_bundle.py`: `digit_reencode_equivalent()` with
  `DIGIT_REENCODE_TOLERANCE = 3` per channel per texel (RGB under alpha 0 on
  either side ignored, alpha always compared); a live digit within tolerance
  of its export baseline (destination texels when they still equal the
  baseline digest, else the private source original for a `source_derived`
  row) gets the new receipt decision `skipped_reencoded`, is not staged, and
  is listed under "Skipped, re-encoded but visually unchanged" in the receipt
  details. Torso/sleeves/pants/nameplate keep the exact rule; a ±4 step or a
  recolour on a digit is still imported.
- Pins resynced (`python3 packaging/repin.py --apply`: providers.py x6,
  check_2k5_mod_studio_runtime.py x1). **Claude: the release manifest needs
  its normal regeneration.**
- `tests/mod_editor/test_nfl2k5_digit_sheet_quality.py`: the one assertion
  that encoded the old preview refusal now asserts the kept-retail row for
  Seattle `26H0:jersey_digit:0` (1488-byte slot).

Not changed: the writer's 16-colour floor, the palette ladder, dithering
(already off), any preset, `mod_build.py`, any GUI panel.

## 4. Tests

Regression file: `tests/mod_editor/test_hotfix63_digit_budget.py` (14 tests).
Retail-gated classes skip precisely when the extracted pack 0 / inventory /
compatibility report are absent.

Red before the fix (same command, on 9c17c538 + the new test file only):

```
$ cd /home/noah/2k-worktrees/astra-hf63-digits && PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_hotfix63_digit_budget.py
ERROR: test_unfit_digit_keeps_retail_and_the_fitting_digit_still_compiles (BackendKeepsRetailTests)
nfl2k5_visual_mod_project.ProjectError: live_number_nameplate (asset_code=02, side=H, variant=0, family=arm): Digit artwork cannot fit its 896-byte texture slot without dropping below the 16-colour quality budget. ...
ERROR: test_a_project_whose_only_edit_kept_retail_still_binds ... (same ProjectError)
ERROR: test_preview_shows_the_retail_digit_for_an_unfit_slot ... ValidationError: Digit 1: Digit artwork cannot fit its 896-byte texture slot ...
FAIL: test_colour_managed_resave_noise_is_not_an_edit_of_a_digit ... AssertionError: 30 != 0 : Imported (30): 02H0: Jersey Digits / Jersey Digit 0 (replaced source) ...
FAIL: test_a_real_digit_edit_and_noise_elsewhere_are_told_apart ... 'imported' vs 'skipped_reencoded'
FAIL: test_describe_edit_names_the_digit ... 'digit=1' not found in 'live_number_nameplate (asset_code=02, side=H, variant=0, family=arm)'
FAIL: test_a_corrupt_digit_payload_still_fails_closed ... (no digit in the label)
ERROR x4: BuildResult has no attribute/keyword 'kept_retail'; FAIL: forged row not refused
Ran 14 tests in 27.618s
FAILED (failures=5, errors=7)
```

Green after (env: `NFL2K5_TEST_INDEX="/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"`,
`NFL2K5_TEST_INVENTORY=$PWD/reports/assets/nfl2k5_resource_chunks_v2.json`,
`NFL2K5_TEST_XISO="/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"`
for the retail-gated suites; every command is
`cd /home/noah/2k-worktrees/astra-hf63-digits && PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<file>.py`):

```
test_hotfix63_digit_budget                       Ran 14 tests in 58.336s OK
test_nfl2k5_digit_sheet_quality                  Ran 16 tests in 111.736s OK      (all 3 retail classes ran, incl. real session+kit+writer+disc windows)
test_nfl2k5_digit_sheet                          Ran 3 tests in 0.565s OK
test_2k5_digit_dimensions_per_target             Ran 10 tests in 2.602s OK (skipped=1)
test_number_sheet_quality_wiring                 Ran 6 tests in 3.081s OK
test_team_kit_bundle                             Ran 7 tests in 36.853s OK
test_teamkit_import_wiring                       Ran 3 tests in 0.705s OK
test_team_kit_product_integration                Ran 7 tests in 53.202s OK
test_uniform_bundle_cross_project                Ran 8 tests in 107.463s OK
test_2k5_uniform_equipment_export                Ran 16 tests in 21.946s OK (skipped=4)
test_nfl2k5_uniform_catalog                      Ran 5 tests in 1.641s OK
test_nfl2k5_uniform_choice                       Ran 18 tests in 15.827s OK
test_2k5_bounded_vclz_palette                    Ran 7 tests in 18.061s OK
test_2k5_vclz_bounded_importers                  Ran 16 tests in 0.689s OK
test_nfl2k5_build_service                        Ran 27 tests in 0.675s OK
test_2k5_build_is_explainable                    Ran 16 tests in 0.025s OK
test_providers                                   Ran 33 tests in 6.060s OK
test_caller_windows_pins                         Ran 19 tests in 0.107s OK
test_phase1_packaging                            Ran 17 tests in 2.520s OK
test_discord_bugs_1_wiring                       Ran 10 tests in 2.785s OK
test_discord_bugs_2_wiring                       Ran 6 tests in 0.970s OK (skipped=2)
test_music_simple_wiring                         Ran 3 tests in 0.734s OK
test_nfl2k5_espn25_integration_qt                Ran 13 tests in 17.018s OK
test_studio_facade                               Ran 11 tests in 0.473s OK
test_facade_external_build                       Ran 2 tests in 2.532s OK
test_emulator_launch_polish                      Ran 11 tests in 2.599s OK
test_nfl2k5_import_preflight                     Ran 17 tests in 16.494s OK
test_png_import_accepts_real_pngs                Ran 11 tests in 0.059s OK
test_2k5_stale_original_cache                    Ran 9 tests in 0.013s OK
test_shipped_tools_posix_only                    Ran 13 tests in 11.725s OK
test_local_windows_ci                            Ran 51 tests in 2.675s OK
test_all_textures_workspace                      Ran 23 tests in 6.719s OK (skipped=3)
test_nfl2k5_equipment_texture_chain              Ran 16 tests in 6.818s OK
test_unified_stadium_texture_composition         Ran 5 tests in 0.026s OK
test_unified_audio_composition                   Ran 3 tests in 1.071s OK
test_nfl2k5_audio_backend_origin                 Ran 5 tests in 0.058s OK
test_xiso_layout_tolerance                       Ran 9 tests in 1.007s OK
test_apf_digital_font                            Ran 14 tests in 0.438s OK
test_studio_shell_layout_qt                      Ran 18 tests in 109.203s OK
test_directory_publishes_are_portable            Ran 5 tests in 0.248s OK
tools/test_nfl2k5_visual_mod_project.py          Ran 45 tests in 4.582s OK      (PYTHONPATH=$PWD:$PWD/tools)
tools/test_nfl_tset_png_import.py                NFL_TSET_PNG_IMPORT_TESTS_PASS swizzle_pairs=12 png_filters=5 mips=6 ...
python3 packaging/repin.py                       would apply 0 pin update(s)
```

`tools/test_nfl_tset_png_import_dynamic_workflow.py` hard-requires
`<repo>/extracted/...` (no SkipTest) and fails the same way on the untouched
base; not related.

Product-level proof (scratch script, not committed; output XISO deleted after
checking): a real `StudioSession` on the retail cache exported the `02H0`
kit, all 30 digit PNGs were re-saved with ±1 RGBA drift + whitened hidden RGB,
imported (`Imported: 0. Skipped unchanged: 39.` — decisions
`skipped_reencoded: 30`, `skipped_unchanged: 9`, no Undo action), then
`arm digit 1` (noisy, unfit) and `jersey digit 0` (recoloured, fits) were
staged with Replace and `Nfl2k5BuildService().build()` ran the real backend
build + independent verify + publish in 87 s:

```
edit_count: 2 changed_byte_count: 3042
kept_retail: [{"selector": "02H0:arm_digit:1", "stored_size": 896, "outcome": "kept_retail", ...}]
message: Build complete — NFL 2K5 Modded.xiso.iso is ready for xemu. Kept retail for 1 uniform slot: arm digit 1 (02H0): kept retail: could not fit its 896-byte texture slot at the 16-colour quality budget; the retail digit was kept and the rest of the project was built.
02H0:arm_digit:1     retail   (span sha256 equals the source disc)
02H0:jersey_digit:0  CHANGED
```

## 5. What Noah must witness in xemu

Nothing here is proved in-game. To witness:

1. Load the retail disc, Uniforms → Baltimore Ravens HOME (`02H0`), export the
   kit, re-save the digit PNGs in a real editor (Photoshop/GIMP/Paint.NET,
   with colour management on), import: expect `Imported: 0`, details listing
   the digits under "Skipped, re-encoded but visually unchanged", no
   "Modified" rows.
2. Replace `Arm / Shoulder Digit 1` with an actual noisy/anti-aliased 64x64
   digit (or the number-sheet import with a resampled sheet) and Make disc:
   the build must finish; status bar / Build & Share dialog must say "Kept
   retail for 1 uniform slot: arm digit 1 (02H0): ...". In-game the Ravens'
   arm "1" must look retail while any other edited digit shows the edit.
3. Replace a digit with flat-fill art that fits (e.g. recolour the export):
   it must build and be visible in-game as before.

ASTRA_DONE
