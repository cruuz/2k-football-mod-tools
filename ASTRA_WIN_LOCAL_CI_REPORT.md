# Local Windows CI: full-matrix classification and hydration

The sections preceding [Follow-up 2](#follow-up-2) record the earlier run and
delivery attempt. Follow-up 2 supersedes their forecasts, example hydration
commands and delivery status.

## Accepted Windows behavior

Claude ran the runner outside the execution sandbox on 2026-09-05 with Wine
9.0 and the installer's pinned Windows CPython 3.12.10. `--os-check` confirmed
`os.name == "nt"`, `platform.system() == "Windows"`, `O_BINARY == 32768`, and
Qt 5.15.2 using `offscreen`. Normal imports resolved to the checkout; the
isolated child resolved to its synthetic staged package. The probe took 8 s.

RED at `89938fa`: `test_modpack.py` reproduced the exact beta-60 failure in
`GrowingSpecialPackTests.test_special_round_trip_and_raw_partition`, at
`modpack.py:144 os.replace(part, target)`: `PermissionError: [WinError 5]
Access denied`, `base.iso.part` to `base.iso`. It ran 36 tests in 22.7 s,
34.8 s wall time. GREEN at `b8d55f4` passed all 36 tests in 34.0 s wall time.
Wine does reproduce this Windows handle-sharing refusal.

Commit `d28ab96` fixed the startup blocker: Wine's python.exe failed in
`init_sys_streams` with WinError 6 when stdout was a regular log file. The
runner now gives the child a PIPE and pumps output into the log. That fix is
retained, including process-tree timeout cleanup. Acceptance was recorded in
`e84fc49`; the earlier sandbox-only attempts in that report are superseded by
these external runs.

## Full matrix and classification decisions

The supplied `.scratch/matrix-logs/FULL_MATRIX.log` records the lean
`/tmp/winci-green` snapshot of `b8d55f4`, with `-j 2`:

```text
SUMMARY: files=301 passed=216 failed=73 skipped=12 tests=3376
WALL CLOCK: 1215.717s
```

That is **20.3 minutes at -j 2 for 301 files**, compared with GitHub's
approximately **20–30 minutes per job**. This is one local measurement, with
early failures and different dependencies/coverage; it is not a speedup claim.
The current branch includes one additional runner test file (302 files).

All 73 failed files are classified below: **27 LEAN CHECKOUT, 44 WINE GAP,
1 RUNNER BUG, 1 UNKNOWN**. Categories are mutually exclusive at file level;
secondary causes are recorded explicitly. A Windows CI file passing can mean
its host-specific cases skipped: Wine's Z: mapping exposes `/proc`, local
retail disc files and the local PS2 witness tree that hosted Windows lacks.
This explains several differences without claiming that native Windows ran
those same cases. No new product defect is established by these logs.

`packaging/windows/local_windows_ci_failures.json` is the reviewed data used
by the runner and pure tests: baseline totals, evidence, exact failing case
identities/statements/terminal exceptions, and gap reasons. The table is the
human-readable index. Every L-number refers to
`.scratch/matrix-logs/<test filename>.log`; full paths/tracebacks remain in
those supplied logs and the manifest. Temporary path spelling is shortened
here only for readability.

| Test file | Classification | Evidence line(s) | Decision / secondary cause |
| --- | --- | --- | --- |
| `test_2k5_audio_operation_integration.py` | WINE GAP | L22: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication`; L105: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` | Also needs catalog hydration; mixed logs remain FAIL until those failures disappear. Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_2k5_bump_retail_probe.py` | WINE GAP | L13: `FileNotFoundError: [WinError 2] File not found: '…/tmph8wnnvqr/alias.iso'` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_2k5_check_my_images.py` | LEAN CHECKOUT | L20: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_2k5_import_offers_resize.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_apf_audio_encoder_gui.py` | WINE GAP | L8: `AssertionError: WindowsPath('.') != WindowsPath('C:/users/noah/Temp/apf-audio-encoder-gui-744fjmnn/wine-stable')` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_audio_encoding.py` | WINE GAP | L23: `AssertionError: "regular file, not a link" does not match "Could not open XMA1 encoder: [WinError 2] File not found: '…/apf-audio-encoding-7vb2k9sb/linked-encoder'"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_audio_waveform_qt.py` | WINE GAP | L23: `AssertionError: "non-link" does not match "The private WAV preview is no longer available"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_digital_font.py` | WINE GAP | L23: `AssertionError: "non-symlink directory" does not match "Allowlisted APF digital_font parent is missing: linked-tools/pinned.py"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_field_art_patch.py` | WINE GAP | L32: `apf_outer.FormatError: cannot stat declared pack '0B': [WinError 2] File not found: '…/tmpci4j9mr8/vol/0B'`; L67: `apf_field_art_patch.PatchError: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 16 bytes; refusing output; optimal H7A encoder requires Linux x86_64` | Retail-only H7A cases are skipped on hosted Windows without local disc inputs; this is extra coverage exposed through Wine Z:. |
| `test_apf_helmet_crest_design_product.py` | WINE GAP | L16: `FileNotFoundError: [WinError 2] File not found: '…/tmpooz2ddn5/linked.png'` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_product_validation_wrappers.py` | WINE GAP | L27: `AssertionError: "not a regular file" does not match "field-art evidence is unavailable: C:/users/noah/Temp/tmp_ypf9914/link.json"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_project_document_workflow.py` | WINE GAP | L8: `AssertionError: False is not true` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_roster_workspace.py` | WINE GAP | L23: `AssertionError: "regular file" does not match "Reserve plan could not be opened"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_studio_safety.py` | WINE GAP | L13: `FileNotFoundError: [WinError 2] File not found: '…/tmpc09vv8dv/linked.apf2k8mod'` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_team_logo_gui.py` | WINE GAP | L15: `AssertionError: False is not true` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_apf_workspace_recovery.py` | WINE GAP | L16: `FileNotFoundError: [WinError 2] File not found: '…/apf-workspace-alias-9anmnnfg/linked-game'` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_audio_annotations_product.py` | WINE GAP | L19: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_audio_bundle.py` | WINE GAP | L23: `AssertionError: "symbolic link" does not match "The audio payload writer returned an unexpected path"` | The int is Path.write_bytes() return value from the test lambda, reached because the dangling-link guard fails; it is not an fd-path API bug. |
| `test_audio_panel_qt.py` | WINE GAP | L19: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_audio_replacement_pack.py` | WINE GAP | L19: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_audio_waveform_qt.py` | WINE GAP | L22: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication`; L111: `AssertionError: "non-link" does not match "The private WAV preview is no longer available"` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_caller_windows_pins.py` | WINE GAP | L11: `FileNotFoundError: [WinError 2] File not found: '…/tmptahu0jpg/complete.zip'`; L33: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_commentary_panel_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_core.py` | UNKNOWN | L1: `F..wine: Call from 00006FFFFFC7D3B8 to unimplemented function KERNEL32.dll.CopyFile2, aborting` | runpy is only the outer call stack. Earlier F has no traceback; preserve FAIL until it is diagnosed. |
| `test_emulator_launch_polish.py` | LEAN CHECKOUT | L20: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_facade_external_build.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_gameplay_inspection.py` | WINE GAP | L23: `AssertionError: "non-symlink" does not match "Gameplay-tuning report is missing: C:/users/noah/Temp/tmp_2mlmmse/tuning-link.json"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_gui.py` | WINE GAP | L10: `ModuleNotFoundError: No module named 'tkinter'` | the pinned embeddable Windows runtime omits tkinter (hosted CPython includes it). |
| `test_mod_build.py` | LEAN CHECKOUT | L8: `AssertionError: False is not true` | avail["scorebug"] and art.available() are false because available() requires reports/assets/scorebug_presentation_audit.json. |
| `test_models_panel_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_never_silent_gray_boot.py` | WINE GAP | L19: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_nfl2k5_audio_catalog.py` | WINE GAP | L19: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_nfl2k5_audio_source_containment.py` | WINE GAP | L18: `mod_editor.core.nfl2k5_audio_source_containment.AudioSourceContainmentError: Private containment inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_nfl2k5_audio_source_fingerprints.py` | WINE GAP | L18: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_nfl2k5_audio_source_scan.py` | WINE GAP | L18: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_nfl2k5_audo_fixed_slots.py` | LEAN CHECKOUT | L14: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_audo_import_capacity.json'` |  |
| `test_nfl2k5_create_play_wizard_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_nfl2k5_extended_visuals.py` | WINE GAP | L23: `AssertionError: "not a folder or link" does not match "Choose an existing PNG file for Portrait 0042 � Test Quarterback"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_nfl2k5_playbook_pack.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_nfl2k5_player_star_draw.py` | WINE GAP | L11: `FileNotFoundError: [Errno 2] No such file or directory: '…/tests/fixtures/nfl2k5_player_star_thin_v1.json'` | tests/fixtures is outside sibling hydration and this later fixture is not promised by beta-50; classify as host-evidence exposure, not a hydration fix. |
| `test_nfl2k5_ps2_replacement_pack_audit.py` | WINE GAP | L22: `nfl2k5_ps2_replacement_pack_audit.PackAuditError: cannot read replacement directory Z:/home/noah/Download … 7/PCSX2/textures/SLUS-20919/replacements/1Active/Real Players/Unassigned/_Retired/DT_Leati Joseph Anoa?i (Roman Reigns)'`; L31: `AssertionError: PackAuditError not raised` | Wine exposes the local PS2 witness tree with a name invalid through Win32; symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_nfl2k5_scorebug_source_art.py` | LEAN CHECKOUT | L21: `mod_editor.core.nfl2k5_scorebug_source_art.ScorebugArtError: the scorebug presentation audit is unreadable: [Errno 2] No such file or directory: '…/reports/assets/scorebug_presentation_audit.json'` |  |
| `test_nfl2k5_source_cache_privacy.py` | WINE GAP | L33: `AssertionError: "non-link directory" does not match "staging could not be inspected at '…/private-source-cache-eq_vbqn1/linked-staging': [WinError 2] File not found: '…/private-source-cache-eq_vbqn1/linked-staging'"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_nfl2k5_stadium_cache.py` | WINE GAP | L13: `mod_editor.core.platform_compat.PrivatePathError: Cannot confirm an owner-only ACL on '…/tmp88obbqpf/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/derived': DACL grants visibility to foreign SIDs: S-1-1-0`; L62: `AssertionError: "regular, non-link" does not match "archive pack F is missing: C:/users/noah/Temp/tmpvvni7k_e/cache/packs/F"` | Wine DACL verification still reports the Everyone SID S-1-1-0; symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_nfl2k5_stadium_studio.py` | WINE GAP | L23: `AssertionError: "regular file" does not match "stadium glTF manifest is missing: C:/users/noah/Temp/tmpytdsbjww/linked-manifest.json"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_nfl2k5_streaming_audio_ui.py` | WINE GAP | L19: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_nfl2k5_uniform_catalog.py` | LEAN CHECKOUT | L14: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_nfl2k5_universal_asset_index.py` | WINE GAP | L23: `AssertionError: "regular file" does not match "private NFL 2K5 asset index is missing: C:/users/noah/Temp/tmpd9pxu0zr/linked.json"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_nfl_audio.py` | WINE GAP | L12: `ModuleNotFoundError: No module named 'tkinter'` | the pinned embeddable Windows runtime omits tkinter (hosted CPython includes it). |
| `test_platform_compat.py` | WINE GAP | L10: `OSError: [Errno 0] Error`; L20: `mod_editor.core.platform_compat.PrivatePathError: Cannot confirm an owner-only ACL on '…/tmphxo3598e/derived': DACL grants visibility to foreign SIDs: S-1-1-0`; L41: `AssertionError: "non-link directory" does not match "test cache could not be inspected at '…/tmpxw2i7h44/link': [WinError 2] File not found: '…/tmpxw2i7h44/link'"` | Wine msvcrt.locking reports Errno 0 instead of a lock-contention errno; Wine DACL verification still reports the Everyone SID S-1-1-0; symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_platform_compat_durability.py` | WINE GAP | L12: `OSError: [Errno 9] Bad file descriptor` | Wine exposes host /proc; Linux-only descriptor simulation runs against Windows CRT descriptors. |
| `test_presentation_panel_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_product_inspection_panels_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_product_shell_accessibility_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_project_document_workflow.py` | WINE GAP | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'`; L110: `AssertionError: False is not true` | Also needs catalog hydration; mixed logs remain FAIL until those failures disappear. |
| `test_providers.py` | WINE GAP | L23: `AssertionError: "non-symlink" does not match "APF jersey PNG does not exist: C:/users/noah/Temp/tmp3p2hhvpw/linked.png"` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_recipes.py` | WINE GAP | L9: `AssertionError: OutputRefusedError not raised` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |
| `test_roster_editor_panel_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_security_blockers_remediation.py` | RUNNER BUG | L12: `mod_editor.core.platform_compat.PrivatePathError: The private NFL 2K5 source cache root must be created u … s/noah/AppData/Local) on Windows, which is where its other-users-excluded ACL comes from; it is at '…/tmpuog770ho/cache'` | Fix TEMP/TMP to LOCALAPPDATA/Temp/winci; preserve the real placement and ACL checks. |
| `test_share_panel_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_sounds_panel_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_stadium_editable_discovery.py` | LEAN CHECKOUT | L20: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_stage_release.py` | WINE GAP | L1: `....wine: Call from 00006FFFFFC7D3B8 to unimplemented function KERNEL32.dll.CopyFile2, aborting` | Wine 9.0 does not implement KERNEL32.dll.CopyFile2 used by CPython shutil.copy2. |
| `test_studio_qt_models.py` | LEAN CHECKOUT | L14: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_studio_session.py` | WINE GAP | L19: `mod_editor.core.nfl2k5_audio_source_fingerprints.AudioSourceFingerprintError: Private source-audio inventory changed during publication` | Inference from repeatable synthetic per-test caches; the compound check does not log which identity/metadata field differs. No evidence of cross-file contention. |
| `test_studio_shell_layout_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_studio_visual_asset_routing.py` | LEAN CHECKOUT | L15: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_team_kit_bundle.py` | LEAN CHECKOUT | L14: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_team_kit_product_integration.py` | LEAN CHECKOUT | L14: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_unif_color_control.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_ux_open_disc_hook_qt.py` | LEAN CHECKOUT | L17: `FileNotFoundError: [WinError 3] Path not found: '…/reports/assets/nfl2k5_team_select_card_inventory.json'` |  |
| `test_visual_export_and_preview.py` | LEAN CHECKOUT | L28: `mod_editor.core.nfl2k5_extended_visual_catalog.ExtendedVisualCatalogError: Player portrait report is missing: …/reports/assets/nfl2k5_player_portrait_compatibility.json` |  |
| `test_workspace_recovery.py` | WINE GAP | L9: `AssertionError: ValidationError not raised` | symlink creation succeeds but Wine cannot stat or identify the resulting link. |

## Precise Wine skips

Every WINE GAP file in the table has an executable signature rule. No file is
skipped merely because its name appears there: it runs first, and its complete
log is retained. For a unittest report, **every** failure/error must match its
reviewed file, full test/subtest identity, failing statement and terminal
exception. Only the username, Wine temp-root layout, generated temporary
directory names and checkout prefix of the optional player-star fixture are normalized; artifact basenames and exception text remain
specific. A newly failing case, changed assertion, extra missing catalog,
unrecognized exception, inconsistent/truncated summary or timeout stays FAIL.
File skips print `SKIP name (Wine gap: <reason>)`, count as skipped files and
contribute no tests to the CI-style total. The original return code and log
are retained. Test-level skips within a passing file retain CI's existing
accounting. There is no WinError 5 skip.

The gap families are symlink visibility/identity, private inventory metadata,
ACL verification (Everyone SID), lock-contention errno, CopyFile2, the omitted
Tkinter dependency, Linux-only descriptor simulation reached through Z:, and
extra local retail/PS2 witnesses. Tkinter is an **embeddable runtime gap**, not
an unimplemented Wine API. The installer's dependency pins remain unchanged.

The recurring audio errors occur at the post-publication identity/ownership/
size/content/mtime compound checks, often in synthetic fixture setup. Their
Wine/environment classification is an inference from the supplied native CI
results and independent temporary caches. The logs do not identify which
field differs; no metadata check, ACL check, descriptor operation or product
assertion is bypassed. `test_audio_bundle.py`'s `int` is the return value of
`Path.write_bytes()` from its lambda, reached after Wine misses a dangling
symlink guard; it is not proof of a descriptor-path conversion bug.

`test_core.py` is UNKNOWN overall: its first line is `F..wine: Call ...
CopyFile2`. The crash is a confirmed Wine gap in `shutil.copy2`, reached from
`create_staging_copy`, rather than a bootstrap/runpy fault. But the earlier
`F` never received a traceback, so the runner **keeps this file FAIL**. Its
CopyFile2 rule can apply on a later run only if there is no earlier failed/error
progress marker. `test_stage_release.py` has only `....` before the same crash
and qualifies for the narrow crash skip. Neither arbitrary crashes nor hangs
are suppressed.

## Runner fix and parallelism

The one identified runner environment bug is `test_security_blockers_remediation.py`:
Wine's default `C:\users\noah\Temp` is outside `LOCALAPPDATA`, while the tests
correctly require a private profile location. A Windows preflight now creates
`LOCALAPPDATA/Temp/winci`, and the parent supplies that Windows path as both
`TEMP` and `TMP` to all matrix processes and descendants. The path is printed
and logged. The product still verifies placement and ACLs. No bootstrap or
`._pth` defect was found in the 73 logs; the previously accepted private hook,
isolated imports and installer runtime preservation remain intact.

There is **no evidence of parallel-prefix contention** in this run. The
publication errors use independent per-test TemporaryDirectory roots, not a
shared output. Even the concurrent-reader case fails with the same private
inventory diagnostic as serial fixture setup. The lock test deliberately
acquires two handles in one test and Wine supplies Errno 0; this is not a
second matrix worker taking its lock. There are no per-file timeouts in the
supplied failed logs. No speculative serial-file list was added. `-j 1`
remains the default; `-j 2` has now completed a matrix, while correctness after
these changes still needs the external rerun.

## Hydration behavior

`--hydrate-from DIR` copies regular files from `reports/`, `mod_editor/assets/`,
`tools/vendor/`, and `docs/research/` in a separate sibling checkout. Missing
source trees are reported individually. It recursively fills only absent
leaves, even under existing directories; existing files, tracked deletions,
symlinks (including dangling links), obstructing parents and tracked paths
are preserved. Source links are not followed. The source checkout is read-only.
Same/nested source and target directories are refused. Every copied relative path, each tree's copied
count and a total are printed. Missing parts of an incomplete source are not
mistaken for successful full hydration.

`--hydrate-release` runs `gh release download beta-50 --repo
cruuz/2k-football-mod-tools` with CI's exact two archive patterns:

| Archive | SHA-256 |
| --- | --- |
| `2K5-Mod-Studio-v1.0-RC74-20260822.tar.gz` | `1dd5762329203dcde152b48e8f1543c6eff26ad067f25ed1124642c48bdcba1f` |
| `apf2k8-mod-studio-0.1.0-alpha.81-20260822.tar.gz` | `8e4fe2ac2b0adc521dd2606e0cf5da67d357220e1ecc9904600d831c024bc8b7` |

Both SHA-256 values are verified before any bytes reach the target. As in CI,
one top-level archive directory is stripped and absent regular files are
copied, preserving permission bits. Release hydration uses all absent archive
paths, matching CI; sibling hydration is limited to the four evidence trees.
Traversal, Windows drive paths, `.git` and nonregular archive members are
refused; destination symlink ancestors are never followed. Git's index also
protects tracked paths that are currently deleted, beyond CI's existence-only
check. Archive snapshots without `.git` have no index to consult, but every
existing target is still protected. Temporary downloads are removed afterward.
The two hydration options are mutually exclusive and opt-in. `gh` credentials
must already be configured; no release download was attempted in this sandbox.

The example beta-53 sibling was checked read-only and contains all five
catalogs singled out in the logs, including the 62 MB all-TXTR evidence marker.
Hydrating that marker enables CI's original 12 lean-skipped files. It does not
promise every remaining private input those files might need.

```bash
python3 packaging/windows/local_windows_ci.py --repo /tmp/winci-green --hydrate-from ~/2k-worktrees/beta-53 -j 2
python3 packaging/windows/local_windows_ci.py --repo /tmp/winci-green --hydrate-release -j 2
```

## Expected results and external follow-up

Replaying the supplied outputs against the new classifier, without executing
Wine or changing any outcomes, yields **216 passed, 31 failed, 54 skipped**
(42 observed Wine skips plus the original 12). The mixed catalog/Wine files
`test_2k5_audio_operation_integration.py` and `test_project_document_workflow.py`
correctly remain failed until their catalog failures disappear.

Conditional projection after hydration and the TEMP fix, assuming no newly
exposed failures: **244 passed, 1 failed, 56 skipped** if the original 12 lean
skips remain, or **256 passed, 1 failed, 44 skipped** if the all-TXTR marker is
hydrated and all 12 newly enabled files pass. The remaining failure is
`test_core.py`'s unreported pre-crash `F`. For this 302-file branch add one pass
if the runner's own tests pass. These are forecasts, not measured acceptance.
Actual test totals and post-change wall time cannot be derived from old logs:
hydration enables test bodies and file skips remove their counts. A zero-fail
summary is neither promised nor manufactured.

Follow-up for Claude, with no test edits made here:

- Symlink cases: after creating a probe link, require `lstat` to identify it and
  require a valid target to round-trip. Wine can report creation success yet
  leave an unusable link, so catching `os.symlink` exceptions alone is not
  enough. Gate only the symlink case/subtest; preserve ordinary exclusive
  output, validation and race tests. This is especially useful in digital-font,
  audio-bundle, provider, project/recovery and waveform tests.
- `test_platform_compat_durability.py`: require `sys.platform == "linux"` as
  well as `/proc/self/fdinfo` for the Linux simulation. Wine's exposed `/proc`
  uses Unix descriptors, whereas CPython supplies CRT descriptor numbers.
  Keep the native Windows tests and POSIX tests separately guarded.
- Local-retail H7A tests: guard the optimal encoder capability for those exact
  retail cases. Do not treat missing Linux-only compression as a Windows
  product regression or weaken fixed-allocation checks.
- Player-star/PS2 witness tests: validate the optional fixture set and platform
  before enabling local-only witnesses. Native CI skips these without local
  retail files. Do not silently fetch private retail material.
- Tkinter: guard only tests that require this optional legacy dependency when
  it cannot import; do not inject fake tkinter modules into the pinned runtime.
- Inventory/ACL/lock gaps: no cheap assertion-preserving test change is proved.
  Instrument the failing identity fields and rerun one affected file at `-j 1`
  outside the sandbox before proposing product/test changes.
- `test_core.py`: recover the earlier failing test by running its cases
  individually/verbosely outside this sandbox, then classify that evidence.
  Preserve the real WinError 5 RED/GREEN regression test.

## Validation and delivery

This follow-up uses supplied Wine logs and code inspection only. Wine cannot
execute in the sandbox and was not invoked for validation. Pure runner tests,
log replay, hydration fixtures and static checks completed successfully. No product code, product test, workflow, installer builder,
dependency pin or release allowlist was changed. The supplied brief and
`.scratch/` evidence are excluded from the explicit commit paths. No push.

Validation performed in this sandbox:

```text
$ python3 tests/mod_editor/test_local_windows_ci.py PlanTests OutputTests ClassificationTests HydrationTests PathTests CacheTests ProcessTests
Ran 40 tests in 1.201s
OK
```

The existing WineAvailabilityTests class was deliberately excluded: the brief
requires pure validation and says Wine cannot execute here. The tests cover
classification/report parity, exact positive and negative skip signatures,
mixed failures, the hidden pre-crash failure, CI pin/command parity, both
hashes before any copy, source/destination links, tracked staged and unstaged
deletions, existing files, nested paths, archive traversal/nonregular entries,
file modes, main's hydration ordering/TEMP propagation, native path startup,
PIPE output and process-tree timeout cleanup.

Full saved-log replay (no Wine):

```text
SUMMARY: files=301 passed=216 failed=31 skipped=54 tests=2790
REVIEWED_UNITTEST_SIGNATURES_REPLAYED 198
ALL 73 FILE EVIDENCE ROWS MATCH THE REFERENCED LOG LINES
```

Replay was also checked with the new LOCALAPPDATA temp-root spelling and a
different username. `python3 -m py_compile` for the runner and its tests,
`python3 packaging/windows/local_windows_ci.py --help`, and `git diff --check`
passed. Release download/real hydrated Wine execution were not performed.

## Explicit-path commit blocked by the filesystem

The requested staging and commit operations were attempted with only these
five deliverable paths. The shared worktree Git metadata is mounted read-only
by this session's permission profile; the workspace files themselves are
writable. Staging failed before any path could be added:

```text
$ git add -- packaging/windows/local_windows_ci.py packaging/windows/local_windows_ci_failures.json tests/mod_editor/test_local_windows_ci.py packaging/README.md ASTRA_WIN_LOCAL_CI_REPORT.md
fatal: Unable to create '/home/noah/2k-football-mod-tools/.git/worktrees/astra-win-local-ci/index.lock': Read-only file system

$ git commit -m 'Classify Wine matrix failures and hydrate local Windows CI inputs' -- packaging/windows/local_windows_ci.py packaging/windows/local_windows_ci_failures.json tests/mod_editor/test_local_windows_ci.py packaging/README.md ASTRA_WIN_LOCAL_CI_REPORT.md
error: pathspec 'packaging/windows/local_windows_ci_failures.json' did not match any file(s) known to git
```

**No commit was created.** HEAD remains `e84fc49`; all five deliverables are
present in the worktree for an explicit-path commit outside this restriction.
No permission escalation, Git-directory relocation or push was attempted.

## Follow-up 2

The continuation reviewed and retained the prior session's uncommitted
runner, classifier and fixture changes, then completed the output-drain fix,
validation and documentation. The baseline is the supplied
`.scratch/matrix5-logs/FULL_MATRIX5.log`, testing `b8d55f4` in
`/tmp/winci-green` with `--hydrate-release -j 2`:

```text
HYDRATED_RETAIL_FREE_BETA_INPUTS files=4
SUMMARY: files=301 passed=246 failed=14 skipped=41 tests=2948
WALL CLOCK: 1682.202s
```

### Why hydration copied zero and the checkout was not lean

A read-only inspection on 2026-09-05 found **625 regular source files under
`/home/noah/2k-football-mod-tools/reports/assets` and all 625 target leaves
already present**. Running each relative path through `hydration_target`
returned `existing=625`; they were not refused because the parent directory
existed, because they were tracked, or because the real source was a link.
Both inventory files are regular files of **62,137,803 bytes**, SHA-256
`5295168a4596b7be273e534b36efd2b53f44c7ed5f16893110a63413397f4929`.
The target lacks `docs/research`, consistent with an earlier partial hydration;
the available evidence does not identify the exact invocation that copied it.

The old runner already checked the correct `--repo` inventory after hydration,
but checked it again for every file. The retained full inventory explains why
matrix5 ran all 12 developer-audit files: eight failed and four passed.
Release hydration preserves existing leaves and cannot undo that state.
GitHub's release-only checkout lacks this inventory and skips all 12.

The runner now freezes `not (repo / EVIDENCE).is_file()` **once after hydration**,
matching `ci.yml`'s exact `-f` path and timing. It prints `CHECKOUT: repo=...;
lean_checkout=...; inventory=...; inventory_before_hydration=...` and saves it
to `WORK/logs/checkout.log`. An inventory created or removed by a test cannot
change selection midway through the matrix. Existing inventories remain
protected; a fresh snapshot is the documented route to CI-equivalent inputs.

Hydration now reports omission counts: existing/tracked targets, destination
symlinks, obstructing parents, source symlinks/nonregular files and VCS
metadata. The beta-53 `reports/assets`, `tools/vendor` and `docs/research`
symlinks remain unfollowed; use their real source checkout for maintainer
evidence. Claude's `c6f99d4` TMPDIR correction and `2a2ed1e`/`75d7635`
VCS-directory/`.git`-file exclusions are retained and covered by tests.

### The six remaining logs

Line numbers below refer to `.scratch/matrix5-logs/<test filename>.log`.
The manifest's `follow_up_2` records these decisions separately from the
historical 73-file classifications. The committed six-log fixture preserves
the audio truncation and the first core fatal traceback; the other four logs
are complete, with line endings normalized.

| Test file | Updated outcome | Evidence and decision |
| --- | --- | --- |
| `test_2k5_audio_operation_integration.py` | Fail; test follow-up | L22 and three other cases have the reviewed private-inventory identity error. L91–109 adds **WinError 32 on `next.xiso` during TemporaryDirectory cleanup**. Preserve failure even after the log is complete. Close/drain window source readers before that temporary directory exits; teardown occurs too late for this scoped fixture. |
| `test_apf_audio_encoder_gui.py` | Skip; Wine gap | L3–8: the same exact symlink-picker case/statement now reports `WindowsPath('.') != WindowsPath('<TEMP>/ap[37 chars]ble')`. The longer TMPDIR path triggers unittest shortening. Add this observed terminal variant only; a different suffix/count or case remains a failure. |
| `test_core.py` | Fail; unknown preceding failure | L1 starts `F..` before the known CopyFile2 crash. L9–11 traces it through `create_source_copy`, `create_staging_copy`, and `test_extracted_directory_copy_is_manifest_verified`. The earlier `F` has no traceback. The first alphabetic case is `test_broken_output_symlink_is_refused`; run it alone and report its actual diagnostic. Keep the pre-crash failure guard. |
| `test_nfl2k5_audo_fixed_slots.py` | Skip; Wine gap | L3–17: hydration gets past the missing capacity catalog and exposes `Private source-audio inventory changed during publication` in the exact service/session logical-ID case. Add that reviewed identity signature. |
| `test_nfl2k5_scorebug_source_art.py` | Fail; test follow-up | L3–27: `digital_font` TXTR spans differ, `score_buga` regenerates with SHA-256 `bbf446bf...2f9e5a` instead of `67b7c0a1...634b70`, and the reference-match receipt is false. Wine exposes local retail inputs. Compare decoded pixels separately from PNG bytes and record Pillow/zlib/FreeType/font versions before deciding whether generation or the test contract needs correction. The log does not prove a font or compression cause; do not replace golden hashes or add a Wine skip. |
| `test_platform_compat.py` | Skip; Wine gap | L13–20 adds the exact Everyone-SID (`S-1-1-0`) ACL error on `LOCALAPPDATA/2k5-mod-studio`, after TMPDIR fixes placement. Normalize only that profile prefix. Existing Errno 0 locking, temporary-root ACL and symlink signatures account for the other three blocks. |

All skips still require the reviewed file, case, statement, terminal exception
and a complete matching failure count. Mixed failures, arbitrary path/hash
changes, truncated logs, timeouts and WinError 5/32 remain failures. No product
code or product test assertions were changed. The three failed files above
are the concrete handoff for Claude; the identity compound check may also
benefit from field-level diagnostics before any product change.

### Output truncation was also a runner defect

The audio log is exactly **8,192 bytes**, ending at `Ran 17 tests in 71.`.
The reader used buffered `read(4096)`, which can retain the last partial chunk
until EOF. After launcher exit, `run_process` joined the reader for 30 seconds
and then returned even if a descendant still held stdout open. A native pipe
regression reproduced the buffering defect before the fix. This is consistent
with the supplied truncation; its exact Wine process history is unavailable.

The pump now uses `read1(4096)` to write available bytes immediately. A file
finishes only when the launcher has exited and output reaches EOF; the same
per-file deadline covers both. A descendant retaining stdout triggers the
existing timeout/process-tree cleanup, never a successful truncated result.
Native tests verify partial output before EOF and timeout after an exited
launcher leaves a child holding stdout. This does not fix or skip the audio
test's actual sharing violation.

### Replay and expected clean numbers

These are **saved-log replays and conditional forecasts**, not a fresh Wine
matrix. They retain the 301-file baseline so the arithmetic is comparable:

| Scenario | Files | Passed | Failed | Skipped | Counted tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| Supplied matrix5 | 301 | 246 | 14 | 41 | 2948 |
| Updated signatures, same already hydrated tree | 301 | 246 | 11 | 44 | 2905 |
| Same logs with CI's lean selection | 301 | 242 | 3 | 56 | 2824 |
| Conditional clean result after the three follow-ups | 301 | 243 | 0 | 58 | 2807 |

The three newly recognized gap files remove 8 + 4 + 31 = 43 counted tests.
All 12 lean files remove another 81 tests, including four previously passing
files (`test_apf_logo_surface_ownership`, `test_apf_product_findings`,
`test_nfl2k5_crib`, `test_nfl2k5_stock_midfield_logo_boundary`), not just the
eight reported failures.

The clean forecast assumes audio cleanup is fixed and its complete output
contains only the four known identity errors (then its 17 tests are excluded
as a file skip); core's earlier failure is resolved/diagnosed so only the
reviewed CopyFile2 crash remains; scorebug's 13-case file passes, possibly with
properly scoped optional retail skips; and all other outcomes are unchanged.
It predicts **243 passes and 58 skips**, not an unconditional zero-failure run.
This branch has 302 files: if its additional runner file passes, the clean
file totals become **244 passed, 0 failed, 58 skipped**, adding that file's
Windows-reported test count. Different retail visibility, fresh release inputs
or a newly detected output-drain timeout can change the actual totals.

### Exact developer commands

For a targeted file in this working tree, with CI's release inputs added:

```bash
cd /home/noah/2k-worktrees/astra-win-local-ci
python3 packaging/windows/local_windows_ci.py \
  --repo "$PWD" --work /tmp/winci-followup2-runtime \
  --hydrate-release --only test_modpack.py -j 1
```

For CI-equivalent **committed source, release inputs and file selection**,
start from a new archive rather than reusing `/tmp/winci-green`. Run the
following after the deliverables have been committed; the runner still uses
the installer's Windows runtime under Wine, not the hosted Python environment:

```bash
cd /home/noah/2k-worktrees/astra-win-local-ci
winci_snapshot=$(mktemp -d /tmp/winci-ci-equivalent.XXXXXX)
git archive --format=tar HEAD --output="$winci_snapshot/source.tar"
tar -xf "$winci_snapshot/source.tar" -C "$winci_snapshot"
python3 "$winci_snapshot/packaging/windows/local_windows_ci.py" \
  --repo "$winci_snapshot" --work /tmp/winci-followup2-runtime \
  --hydrate-release --keep-going -j 1
```

Expect `inventory_before_hydration=absent` and `lean_checkout=1` for this
branch and the pinned beta-50 archives. Serial `-j 1` matches CI's file loop;
`-j 2` is the optional throughput setting used in matrix5. Keep the snapshot
and `WORK/logs` for diagnosis. Both commands require Wine and the existing
`gh` authentication/download prerequisites. For maintainer evidence instead,
use `--hydrate-from /home/noah/2k-football-mod-tools`; expect the inventory to
enable all 12 developer-audit files without promising their other inputs.

### Validation and delivery

`python3 tests/mod_editor/test_local_windows_ci.py` ran **51 tests in 2.354 s:
OK (skipped=1)**. The skip is Wine startup, denied by the sandbox with SIGSYS.
An actual runner `--os-check` with work under `/tmp` independently exited 2
at `wine --version` (`rc=-31`); no downloads or live matrix were attempted
after that failure. No permission bypass or Wine API substitution was used.

The tests cover the new six-log signatures and negative mutations, mixed
sharing violations, all 12 lean files, hydration before sentinel evaluation
on a selected repository, test-time sentinel mutation, TMPDIR propagation,
VCS and source/destination link refusal, omission diagnostics, partial pipe
output and descendant timeouts, plus the existing runner contracts.
All six evidence entries match their supplied log lines, and full 301-file
replays reproduce the two updated rows above. The brief and `.scratch/`
remain outside the deliverable paths. No push.

`py_compile` for the runner/tests, runner `--help`, and `git diff --check`
also passed. The explicit commit scope is `packaging/windows/local_windows_ci.py`,
`packaging/windows/local_windows_ci_failures.json`,
`tests/mod_editor/test_local_windows_ci.py`,
`tests/fixtures/local_windows_ci_followup2.json`, `packaging/README.md`, and
this report. Explicit-path staging succeeded in this continuation, superseding
the earlier filesystem limitation recorded above.
