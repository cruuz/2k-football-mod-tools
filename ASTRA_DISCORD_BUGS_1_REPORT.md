# r63 Discord bugs 1

2026-09-07. Base `1606ec9`, branch `astra/r63-discord-bugs-1`.
**EXPERIMENTAL / UNWITNESSED.** All ten reports have a disposition, regression
coverage and a FAQ answer. Several product fixes require the protected edits
in [WIRING.md](WIRING.md); those edits were not applied to this worktree.
The exact proposed diff is committed as a test fixture and tested in memory.
This is a completed editor investigation and protected integration handoff,
not a release sign-off or a claim that every community symptom was reproduced.

No emulator, game boot, GUI display, audio, network or push was used. Only
this worktree was edited. The original disc and extracted retail files were
read only. No full disc build or archive pack copy was made. The new tests use
small synthetic images, a bounded read of retail default.xbe and offscreen Qt.

## B3. Update available never clears

**Report:** X_Ray, September 5, says the notice remains after either update path.

**Cause and evidence:** PROVED: `_is_newer('beta-62', 'v1.0-RC86')` was true.
The same failure occurs for RC81/beta-57 and RC85/beta-61, including an older
published beta compared with the installed RC label. The display version uses
RC spelling, whereas the release identity is `beta-N`. The mappings used here
are explicit pairs in `BETA_RELEASE_NOTES.md`; a universal RC-minus-offset rule
would be wrong, since RC62 was shared by several releases. The local CI workflow
also downloads named `beta-N` releases. There is no separate release-tagging
workflow in this checkout to inspect.

HYPOTHESIS: this mismatch caused X_Ray's exact repeated banner. Current Studio
call sites already pass `BUILD_RELEASE_TAG == 'beta-62'`, and equal beta tags
work. Numeric beta ordering was fixed in `b384eaf`. A stale installed folder,
shortcut or version constant remains an alternative explanation without his
installed files. Nothing here marks a merely downloaded release as installed.

**Fix:** `self_update.canonical_release_tag` recognizes documented RC77 through
RC86 aliases, including `1.0.0rc86`, and the update worker normalizes its input.
The protected `_is_newer` handoff normalizes both sides too. Unknown identities
retain the existing fallback. Missing `.sha256` sidecars now refuse at planning
and before download, so Update now is not offered for an unverifiable asset.
Exact asset-name matching and digest verification remain mandatory. The RC81
beta-57 updater notes were checked: Windows waits for Studio to exit; portable
updates preserve a previous folder. No installer/swap protocol was weakened.

**Test:** core B3 worker/no-sidecar tests pass. The proposal suite compares
same, older and newer beta tags against three installed RC spellings. These
comparisons fail on the untouched protected comparator and pass with the exact
proposal. Existing update-check and self-update suites pass; the APF selection
fixture now includes its required sidecar.

**FAQ:** The updater compares known RC labels with their matching beta release
tags. If the notice remains after restarting, check the version and folder of
the copy you opened. Update now requires the matching verification file.

## B7. Duplicate choices allegedly corrupt the xiso

**Report:** Atomic Game Room Productions, September 5, reports selecting the
same option in Gameplay and Build/Share corrupts the output.

**Cause and evidence:** PROVED: on this stack the two panels create independent
BuildPlan objects. They do not merge lists of executable writes, and there was
no Gameplay-to-Build forwarding connection. The supplied offscreen test checks
Catching in both panels and observes one `tt.write_copy` call and one XBE step
when Build is invoked. The single-plan route was introduced by `3423cf7`.
There is no known corruption-fixing commit to cite, because this claimed cause
has not been demonstrated.

PROVED with bounded retail bytes: the real `_apply_all` dispatcher applies
Catching once and returns byte-identical bytes on replay with `already_applied`.
The lower-level Catching `apply` deliberately refuses an already-applied input;
its caller performs the status check. That refusal is not corruption. The
public copy writer refuses an entirely unchanged patch request before writing.

HYPOTHESIS: a different option combination, different source copy, unsupported
patch transition or the known everything-on SEGA hang caused the user's output
problem. No all-owner boot, exact user image or duplicate-option corruption is
claimed. Existing RC86 composition reports were not treated as game witnesses.

**Fix/disposition:** close duplicate-checkbox execution as unproved on this
stack. The B22 handoff adds a shared last-edit-wins selection link and one
combined project build, eliminating divergent choices between the two views.
It does not invoke a writer while synchronizing controls.

**Test:** offscreen one-writer assertion passes even on the original panels;
retail dispatcher replay passes; proposal tests cover two-way selection and
project restoration. No full image was built.

**FAQ:** Selecting the same option in Gameplay and Build does not queue the
patch twice. Review the source, output and selected changes before building.

## B9. Validation refusal followed by apparent success with no changes

**Report:** muddybrowneye, September 6, first gets the retail-size/unknown-image
refusal and then reports a run that appears to succeed without applying a mod.

**Cause and evidence:** PROVED: a no-change BuildPlan can copy identical bytes
and return a successful receipt without a measured outcome; Build's completion
UI unconditionally says Disc ready and Steps written. HYPOTHESIS: that was the
user's second-run path. His file and receipt are not supplied. The initial
retail-size refusal is retained, not converted into an accepted input.

**Fix:** new `build_feedback.measure` streams source and final-output SHA-256
and sizes. The protected build handoff records the result before publication,
after every writer. Equal output says No changes written. An old receipt
without a measurement says changes not measured. The two completion panels
use that distinction. Combined project builds measure against the original
source, not just the intermediate with already-staged art. A legitimate
unchanged copy may still exist; it is explicitly described as unchanged.

**Test:** the baseline receipt lacks `outcome`; the exact proposal returns
`unchanged` for identical synthetic image bytes. A combined art/patch test
returns `changed`, with both byte markers preserved. An injected patch failure
keeps an existing output and removes the temporary partial file. Hashing never
reads more than 1 MiB at once.

**FAQ:** A build that produces identical bytes says No changes written. Check
whether the patches are already installed on your source and whether you opened
the output named in the receipt.

## B22. Gameplay selections lost from a saved project

**Report:** Smuzz, September 6, loses gameplay fixes from v2 of a roster/uniform
project and asks whether Make Disc From Project carries Gameplay selections.

**Cause and evidence:** PROVED: the project settings allowlist contained only
selected beta-62 fields and music shuffle, omitting Catching, dynamic kickoff,
Momentum and other existing options. A real `.2k5mod` save with representative
Gameplay settings refused with Unsupported Build settings. Build restoration
only restored beta-62 controls. Game Fixes had no forwarding/persistence
connection. The footer invoked the art-project builder directly, and Build
included shared project edits only under unrelated naming/music options.
These are editor paths which can lose intended work. HYPOTHESIS: which one
produced Smuzz's exact v2 output, whose source project is unavailable.

**Fix:** the unprotected settings codec now preserves all existing BuildPlan
recipe fields with type checks, detached copies and explicit plan reconstruction.
Source, target and overwrite permission are excluded. The protected handoff
connects Gameplay to Build, observes Build edits, restores controls without
feedback loops, enables the footer for selected work, and uses the combined
project operation. All staged artwork is included. The confirmation already
lists selected changes and now includes the shared project whenever it is used.

Existing external file paths are preserved, not embedded or relocated. Keep
roster JSON, playbook packs, custom artwork and other referenced files available.
Older Studio versions can reject expanded settings rather than silently drop
them. Missing choices in old project files cannot be recovered automatically.
This is not a new executable feature and changes no preset defaults.

**Test:** real small project-archive save/load passes for Catching, dynamic
kickoff, Momentum, screen timing and abilities/off-week. Type/refusal and
no-overwrite reconstruction tests pass. Offscreen proposed classes restore
flags, levels, arc, distance and uniform mode, clear an older empty project,
synchronize both views, and route the footer into one combined build. The
combined build's only patch call receives the staged artwork bytes.

**FAQ:** Gameplay choices are saved with your project after this update. Review
them after reopening an older project, because choices missing from an old file
cannot be recovered automatically.

## B17. Build and Check my images stay grey

**Report:** X_Ray, September 3, cannot enable either button after the obvious step.

**Cause and evidence:** PROVED: the footer tests loaded source, positive project
edit count and no busy operation. Gameplay-only selections have zero project
image/edit count. The current code already supplies Build's blocker tooltip
and accessible description, introduced in `93e1f6a`, and Check my images has a
separate reason/disableReason from `e3e974c`. The report that no enable-condition
is available is therefore outdated for this stack. HYPOTHESIS: the screenshot's
specific state; only its ledger description was supplied.

**Fix/disposition:** retain image checking's actual scope. The B22 protected
handoff also enables Make disc for selected Build work and routes it correctly.
A gameplay-only project still has no images for Check my images to inspect.
Busy/source/project-edit reasons continue to be exposed in the same refresh.

**Test:** existing `test_2k5_build_is_explainable.py` passes all 16 cases. The
new offscreen suite verifies the existing actionable messages and the proposed
footer's Gameplay build route.

**FAQ:** Open a disc and make a project edit or select a Gameplay change before
making a disc. Check my images needs staged images, and its help text explains
what is missing or whether another operation is running.

## B11. Reopened modded image shows stock pants

**Report:** maumau78, September 6, reopens a modded disc and sees stock Giants pants.

**Cause and evidence:** PROVED: `Nfl2k5SourceCache.index` used the canonical retail
SHA-256 as the cache-directory key for every recognized dump. A cache hit returned
without comparing the selected disc's archive to that cache. The inspector
can recognize an unchanged retail XBE inside a disc whose textures changed.
Thus the shared stock cache could be substituted for altered archive bytes.
The failing regression makes this substitution observable without copying a disc.
HYPOTHESIS: it explains his exact pants file; neither the file nor a write receipt
is supplied.

**Fix:** cache directories and their identity markers now use the selected
source's actual digest and size, so a different disc cannot populate the
canonical cache. Before reusing a cache, compare all 16 archive packs at that
disc's real directory offsets with its cached packs, in bounded blocks.
Different layout/padding remains supported. This may require a separate private
cache for a different container, and adds read I/O on a cache hit.
A changed pack is refused with its name and instructions to open the original
disc plus saved `.2k5mod` project. This does not claim support for editing arbitrary
modded archives. Fresh-index pack-0 refusal also names that limitation. The source
and cache stay unchanged and descriptors close on failure.

**Test:** cache-hit substitution fails before the fix and refuses afterwards;
identical synthetic packs with different offsets pass; a change in late pack B
refuses. Existing stale-original-cache, alternate-dump and cache privacy tests
are included in validation. No new persistent disc/pack cache was allocated.

**FAQ:** Open your original disc and load your saved .2k5mod project to continue
editing. A modified archive the editor cannot read is refused instead of being
shown with cached stock art.

## B14. First name limited to three letters

**Report:** Smuzz, September 4, is told to use a donor with a matching name length.

**Cause and evidence:** PROVED: native Rosters uses `RosterDocument.set_name`
and StringPool, introduced in `7f1f3b3` with beta 59/RC83. It can repoint to an
existing longer string and reuse freed space. It does not impose a three-letter
per-player field limit. The legacy fixed-span text editor and an actually full
pool remain different constraints. The native codec limits names to 15
characters and available shared allocation space. This is not unlimited name
storage.

**Fix/disposition:** no new allocator or roster writer is required. The FAQ
routes authors to native Rosters and states its real limit. The suggested
workaround is unnecessary when an existing name or adequate free block is
available; a genuinely full pool still refuses before mutation.

**Test:** a first name changed to Tom can then become Michael and survive
serialization, without growing the ROST body. A Christopher allocation with
insufficient room reports required bytes/largest free block and keeps all bytes
unchanged. The existing 108-test roster suite passes with one missing-catalog skip.

**FAQ:** Use the native Rosters editor. Names can be up to 15 characters when
the shared pool has room; reuse an existing name or follow the pool-space
message if it is full.

## B16. WinError 193 launching xemu

**Report:** brack, September 4, gets WinError 193 after staging/building.

**Cause and evidence:** PROVED: configuration checked file existence and X_OK,
which does not identify a Windows PE executable. Launch wrapped WinError 193 in
a generic error without an actionable binary-selection explanation. HYPOTHESIS:
whether his selection was a shortcut, archive, wrong CPU build or corrupt binary.
A 32-bit Studio can launch a 64-bit xemu on 64-bit Windows; Studio's own pointer
size is not the test used here.

**Fix:** the launcher checks Windows .exe/MZ/PE headers, executable/DLL flags,
section/header completeness, CPU kind and PE bitness before storing or launching
a selected executable. It distinguishes 32-bit Windows and ARM64-on-x64; the
WOW64 host variable avoids mistaking 32-bit Python for a 32-bit OS. A remaining
OS refusal with WinError 193/216 gets a clear xemu.exe/extraction/CPU message.
POSIX executables and Flatpak invocation behavior are unchanged.

**Test:** synthetic bounded PE fixtures exercise accepted x64, refused x64 on
32-bit Windows, WOW64 host detection, shortcuts, ELF/archive/truncated bytes;
a mocked OS launch failure checks the exact actionable message. No emulator
process was started and no native Windows execution is claimed.

**FAQ:** Extract the Windows xemu download and choose xemu.exe in Set up xemu.
Choose a build for your PC's CPU type. A 64-bit xemu needs 64-bit Windows.

## B12. Portraits absent after roster edits

**Report:** Smuzz, September 6, cannot get Maye/Brown portraits to register.

**Cause and evidence:** PROVED: roster `photo_id` at +0x06 survives the native
roster edit recipe and renaming. It does not select an image by the new name.
Find player images still matched portraits by historical name and claimed there
was no record link, although the native Rosters codec already exposed it. Build's
shared-project omission could separately discard staged portrait artwork while
applying roster edits. HYPOTHESIS: either explains the reported in-game result;
no original project/save/portrait was supplied and no game was run.

**Fix:** explicit Photo ID joins win over name fallback in the asset helper.
The proposed Studio caller supplies that selector from the text catalog's +0x06
field. The new native roster confirmation reports the selected numbered image,
catalog presence/absence and the need to include art plus roster edits in one
build. Its protected `_after_edit` hook is specified and tested as proposal
source. The existing Find player images page still reads the loaded source
catalog; the new native Rosters message is the authority for an unsaved changed
Photo ID. The B22 combined project path carries the staged portrait too.

The [FAQ and portrait procedure](docs/mod_editor/discord_bugs_1_faq.md) explains
128x128 PNG import, fixed palette storage, selecting an existing Photo ID,
roster JSON plus artwork in one build, retained external file paths and existing
in-game saves. It never calls a staged choice an in-game success.

**Test:** roster recipe plus rename preserves Photo 1234; explicit 1234 selects
its image despite an old owner label; missing IDs never fall back to a different
person by name. Confirmation distinguishes available, missing and unavailable
catalog evidence. Baseline shared-project inclusion fails without unrelated
naming/music selections; the proposal includes it and preserves the artwork.

**FAQ:** Photo ID chooses a numbered portrait. Changing a player's name does
not change the picture. Replace that portrait and include both the portrait
project and roster edits in the same disc build; edit an existing save's ID too
if you use that save.

## B10. Photoshop PNG/DDS imports

**Report:** maumau78 and Atomic Game Room Productions, September 5-6, hit shoe
and pants import failures; Paint.net worked for one author.

**Cause and evidence:** PROVED: broad PNG type/interlace support already landed
in `cc0bd49`. Current RGB, RGBA, indexed and grayscale support must not be
regressed to requiring only noninterlaced RGBA8. A remaining 16-bit transparency
bug was reproduced: the decoder discarded the low sample byte before comparing
against a full 16-bit tRNS key, making transparent pixels opaque. HYPOTHESIS:
that variant or a size/compression refusal explains either screenshot. Their
actual Photoshop files were not supplied.

**Fix:** retain full samples until transparency comparison, then convert the
channels to eight bits. The uniform and extended-visual PNG lanes now explicitly
refuse DDS and name the required dimensions, PNG export and alpha-preserving
conversion. Standard ancillary metadata including profiles remains accepted;
ICC color transformation is not performed. Dimension/CRC/critical-chunk and
bounded-data refusals are retained with their exact reason.

**Test:** grayscale and RGB16 tRNS keys with identical high bytes but different
low bytes distinguish transparent from opaque pixels. A truly Adam7-interlaced
RGB fixture with profile metadata decodes exactly; the DDS refusal names size
and format. This fixture sets IHDR interlace=1 directly, since passing an
interlace option to Pillow does not establish that an interlaced file was written.
The existing PNG suite passes all 11 cases.

**FAQ:** Photoshop PNGs are supported when they keep the texture's exact
size. DDS import is not supported in this PNG lane; export the base image as
PNG and preserve its alpha channel. The error names the failed requirement.

## Validation and limits

Every new test is a standalone unittest script with ROOT inserted into sys.path.
Qt ran with `QT_QPA_PLATFORM=offscreen`. The proposal loader applies exact unified
hunks in memory and fails if their original source context drifts. It is not
pytest-only and does not edit protected files or depend on `.scratch`.

| Standalone command, preceded by `QT_QPA_PLATFORM=offscreen` | Result |
| --- | --- |
| `python3 tests/mod_editor/test_discord_bugs_1.py` | 17 tests, PASS |
| `python3 tests/mod_editor/test_discord_bugs_1_wiring.py` | 10 tests, PASS against exact proposal |
| `python3 tests/mod_editor/test_self_update.py` | 26 tests, PASS |
| `python3 tests/mod_editor/test_update_check.py` | 20 tests, PASS |
| `python3 tests/mod_editor/test_png_import_accepts_real_pngs.py` | 11 tests, PASS |
| `python3 tests/mod_editor/test_player_assets.py` | 15 tests, PASS |
| `python3 tests/mod_editor/test_music_playlist_project.py` | 4 tests, PASS |
| `python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 tests, PASS, 1 skip for missing portrait catalog |
| `python3 tests/mod_editor/test_beta62_integration3_qt.py` | 8 tests, PASS |
| `python3 tests/mod_editor/test_2k5_build_is_explainable.py` | 16 tests, PASS |
| `python3 tests/mod_editor/test_2k5_stale_original_cache.py` | 9 tests, PASS |

Additional validation: `python3 tests/mod_editor/test_mod_build_beta62_integration3.py`
passes 11 tests; `python3 tests/mod_editor/test_source_accepts_any_dump.py` passes
15 tests with two precise missing-retail-image skips. The existing cache privacy
suite has the same standalone sys.path issue described below; with `PYTHONPATH=.`
it passes all 7 tests. The passing suites total 277 test cases, including three
explicit skips and ten tests of the protected proposal. `git diff --check` and `git apply --check` for the proposed fixture
pass. The targeted loop ran with a 2 GiB address-space limit per process. Final
new-suite measurements using `/usr/bin/time -v`: core 124,188 KiB maximum RSS;
proposal 179,800 KiB maximum RSS (measured before the final additional namespace
assertion, which uses only a tiny fixture). No disc or pack was loaded wholesale into RAM.

Two pre-existing suites, `test_project_document_workflow.py` and
`test_emulator_launch_polish.py`, fail as plain scripts before tests because they
do not add the repository to sys.path. Supplemental runs with `PYTHONPATH=.`
reach 13 and 11 tests respectively, then have 6 and 3 errors caused by absent
`reports/assets` catalogs. These are not counted as passing, and no synthetic
catalog was substituted for their real evidence. The separate new tests supply
bounded collaborators explicitly. Full packaged runtime/provider checks require
protected repinning and Claude's complete release tree; they were not represented
as green. No owner changed, so the full XBE safety compositions were not rerun.

Initial red runs are retained in `.scratch/discord-bugs-1/baseline.log` and
`wiring-baseline.log`. The former records the five proved failure areas, the
already-working portrait recipe, and an initially overlong name request which
correctly exhausted the synthetic pool. The final name tests distinguish that
valid refusal from the obsolete three-letter limit. The latter uses untouched
protected code: missing RC normalization, settings restoration/forwarding,
project inclusion and no-op outcome fail; duplicate execution and existing
blocker messages already pass.

## Noah's witness list and known gaps

After Claude integrates and re-pins the exact protected changes:

1. Update an actual packaged RC85 install to the next release on Windows and a
   portable installation. Reopen through the same shortcut, inspect About and
   the running folder, and confirm equal/older tags never show Update available.
   Check a release with no sidecar offers only the manual path.
2. Select Catching in Gameplay, verify Build reflects it, toggle it off in Build
   and verify Gameplay reflects that. Repeat with Momentum level and screen
   timing, save, close, reopen and review the exact selected list.
3. Make a project with a changed Giants pants image, a numbered portrait,
   roster names/Photo IDs and Gameplay selections. Save it, reopen it, build once
   and inspect the confirmation/receipt. Boot that named output and check each
   specific change. This is the required in-game witness for B7/B11/B12/B22.
4. Exercise no source, no edits, gameplay-only, image edits and busy-operation
   states. Confirm Make disc routes correctly and Check my images explains its
   image-only scope. Verify an unchanged copy is visibly identified as such.
5. Reopen a modified-art disc with a populated retail cache. Confirm it refuses
   the changed archive rather than showing stock art. Open the original plus
   saved project and confirm the staged pants/portrait preview is restored.
6. In native Rosters, replace a three-letter first name with a longer supported
   one, then verify a pool-full refusal leaves the roster intact. Check both a
   newly created game roster and an existing save's Photo ID independently.
7. On actual Windows, select a shortcut, archive, wrong CPU executable and the
   correct xemu.exe. Confirm wrong files never launch and the correct program
   opens the latest output. CPU/header tests here are simulations, not a Windows
   install or emulator witness.
8. Import the reporters' actual Photoshop pants/shoe files if available. Compare
   alpha, palette reduction and colors, including RGB16+tRNS and Adam7 PNGs. DDS
   should say how to export PNG, rather than claiming the file is a valid input.

The original corruption, SEGA hang, in-game portrait failure and exact updater
installation remain HYPOTHESIS until those witnesses. This job makes no runtime
patch, changes no allocator budget, does not regenerate the cave manifest and
does not enable an experimental preset option.

## Delivery

Changes are limited to this worktree. The commit uses explicit file paths, excludes
ASTRA_BRIEF.md and all of `.scratch`, and is not pushed. The direct explicit-path `git add` failed because the worktree's `index.lock`
is on read-only Git metadata. The same explicit-path commit is therefore made
in a scratch metadata clone on `astra/r63-discord-bugs-1` and delivered as
`.scratch/r63-discord-bugs-1.bundle`, with the files left here. The bundle contains
only this job's commit above the base and requires that base history to import.
The original worktree branch/index could not be advanced. The final response
identifies the resulting commit.

Disk was 107,811,856,384 bytes free when checked during implementation, above
the 100 GB floor. Only temporary tiny fixtures and a bounded XBE buffer were used;
no acceptance disc needs cleanup. Scratch contains only logs, proposal-generation
notes and, when required, Git metadata and the bundle, below the 200 MB cap.
